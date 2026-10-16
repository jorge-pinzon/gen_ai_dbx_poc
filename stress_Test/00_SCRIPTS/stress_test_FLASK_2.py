"""Sustained HTTP reliability test for local or deployed Flask.

Local baseline:
  python3 stress_test_FLASK_2.py --concurrency 1 --duration-seconds 300
Deployed:
  python3 stress_test_FLASK_2.py --base-url https://your-app.example.com --auth bearer

Defaults to http://127.0.0.1:5000. Only requests and the standard library are
required; the tested Flask server must already be running. Credentials come from
FLASK_TEST_USERNAME / FLASK_TEST_PASSWORD / FLASK_TEST_BEARER_TOKEN. Databricks
Apps can instead use --auth databricks with the installed SDK's authentication.

One persistent process/session per client allows the parent to stop blocked local
requests at an overall deadline. Disconnecting does not cancel remote server work.
No network calls occur on import. Requests are never automatically retried.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import multiprocessing as mp
import os
import re
import statistics
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

SUCCESS = {"SUCCESS_WITHIN_TARGET", "SUCCESS_LATE"}
QUESTION = "/policy What does the policy say about record retention?"
FIELDS = ["timestamp", "workflow_id", "phase", "event", "stage", "outcome",
          "started_at", "finished_at", "elapsed_seconds", "http_seconds", "offset_seconds", "minute",
          "conversation_id", "request_id", "header_request_id", "request_id_matches_header", "http_status", "content_type",
          "response_bytes", "error_category", "app_error_code", "exception_chain", "source_count",
          "has_sources", "mock_response_detected"]


class TestFailure(Exception):
    def __init__(self, category, stage):
        self.category, self.stage = category, stage
        super().__init__(category)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def diagnostics(error):
    chain, seen = [], set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    if isinstance(error, TestFailure):
        category = error.category
    elif isinstance(error, requests.exceptions.SSLError) or any("ssl" in name.lower() for name in chain):
        category = "TLS_ERROR"
    elif isinstance(error, requests.exceptions.Timeout) or any("timeout" in name.lower() for name in chain):
        category = "NETWORK_TIMEOUT"
    elif isinstance(error, requests.exceptions.ConnectionError):
        category = "CONNECTION_ERROR"
    else:
        category = "CLIENT_ERROR"
    # No exception text, response bodies, credentials, or cookies are persisted.
    return {"error_category": category, "exception_chain": " -> ".join(chain)}


def question_with_id(question, workflow_id):
    marker = f"[STRESS_TEST_ID={workflow_id}]"
    command, _, rest = question.strip().partition(" ")
    if command.startswith("/"):
        return f"{command} {marker} {rest}".strip()
    return f"{marker}\n\n{question}"


def public_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value) else ""


def setup_session(args):
    session = requests.Session()
    session.verify = str(args.ca_bundle) if args.ca_bundle else True
    session.headers.update({"Accept": "application/json", "User-Agent": "FlaskReliabilityTest/2"})
    # Explicitly disable retries for POSTs: duplicate chat requests have side effects.
    session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
    provider = None
    try:
        if args.auth == "bearer":
            session.headers["Authorization"] = "Bearer " + os.environ[args.token_env]
        elif args.auth == "databricks":
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(profile=args.databricks_profile) if args.databricks_profile else WorkspaceClient()
            provider = client.config.authenticate
        elif args.auth == "password":
            login_url = args.base_url + "/login"
            with session.post(login_url, data={"username": os.environ[args.username_env],
                                               "password": os.environ[args.password_env]},
                              timeout=(args.connect_timeout_seconds, args.read_timeout_seconds),
                              allow_redirects=False, stream=True) as response:
                location = urlsplit(urljoin(login_url, response.headers.get("Location", "")))
                origin = urlsplit(args.base_url)
                if (response.status_code not in (302, 303) or not response.headers.get("Location")
                        or (location.scheme, location.netloc) != (origin.scheme, origin.netloc)
                        or not session.cookies):
                    raise TestFailure("LOGIN_FAILED", "authentication")
        return session, provider
    except BaseException:
        session.close()
        raise


def execute_request(session, provider, args, job, emit):
    """One HTTP attempt with strict chat-response validation and metadata only."""
    start = time.monotonic()
    row = {"workflow_id": job["workflow_id"], "phase": job["phase"],
           "conversation_id": str(uuid.uuid4()), "stage": "authentication"}
    emit({**row, "event": "START", "timestamp": utc_now()})
    response = None
    http_start = None
    try:
        remaining = lambda: max(.001, args.deadline_seconds - (time.monotonic() - job["started_monotonic"]))
        headers = provider() if provider else None
        if remaining() <= .001:
            raise TestFailure("WORKFLOW_DEADLINE", "authentication")
        row["stage"] = "http_request"
        http_start = time.monotonic()
        response = session.post(args.base_url + "/api/v1/chat",
                                json={"message": question_with_id(args.question, job["workflow_id"]),
                                      "conversationId": row["conversation_id"]},
                                headers=headers, allow_redirects=False, stream=True,
                                timeout=(min(args.connect_timeout_seconds, remaining()),
                                         min(args.read_timeout_seconds, remaining())))
        row.update(http_status=response.status_code,
                   header_request_id=response.headers.get("X-Request-ID", "")[:256],
                   content_type=response.headers.get("Content-Type", "").split(";", 1)[0].lower())
        emit({**row, "event": "HEADERS", "timestamp": utc_now()})
        if 300 <= response.status_code < 400:
            raise TestFailure("UNEXPECTED_REDIRECT", "http_response")
        row["stage"] = "response_body"
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=16384):
            if remaining() <= .001:
                raise TestFailure("WORKFLOW_DEADLINE", "response_body")
            size += len(chunk)
            if size > args.max_response_bytes:
                raise TestFailure("RESPONSE_TOO_LARGE", "response_body")
            chunks.append(chunk)
        row.update(response_bytes=size, http_seconds=time.monotonic() - http_start)
        row["stage"] = "response_validation"
        is_json = row["content_type"] == "application/json" or row["content_type"].endswith("+json")
        try:
            payload = json.loads(b"".join(chunks)) if is_json else None
        except (ValueError, UnicodeError):
            payload = None
        if isinstance(payload, dict):
            if isinstance(payload.get("requestId"), str):
                row["request_id"] = payload["requestId"][:256]
            if isinstance(payload.get("error"), dict):
                row["app_error_code"] = public_code(payload["error"].get("code"))
        if response.status_code != 200:
            category = ("AUTHENTICATION" if response.status_code in (401, 403) else
                        "RATE_LIMITED" if response.status_code == 429 else "HTTP_ERROR")
            raise TestFailure(category, "http_response")
        if not is_json or not isinstance(payload, dict):
            raise TestFailure("INVALID_JSON_RESPONSE", "response_validation")
        if (payload.get("error") or not isinstance(payload.get("answer"), str)
                or not payload["answer"].strip() or not isinstance(payload.get("sources"), list)
                or payload.get("conversationId") != row["conversation_id"]
                or not isinstance(payload.get("requestId"), str) or not payload["requestId"].strip()):
            raise TestFailure("INVALID_CHAT_RESPONSE", "response_validation")
        # Proxies may replace the header ID. Preserve both; a mismatch alone
        # does not invalidate a correctly correlated application response.
        row["request_id_matches_header"] = (row["header_request_id"] == row["request_id"]
                                            if row["header_request_id"] else None)
        mock_detected = "running in mock mode" in payload["answer"].lower()
        row.update(source_count=len(payload["sources"]), has_sources=bool(payload["sources"]),
                   mock_response_detected=mock_detected)
        if args.backend_mode == "databricks" and mock_detected:
            raise TestFailure("MOCK_BACKEND_RESPONSE", "response_validation")
        row["outcome"] = "SUCCESS_WITHIN_TARGET"
        row["stage"] = "complete"
    except Exception as error:
        details = diagnostics(error)
        row.update(details, outcome="DEADLINE_EXCEEDED" if details["error_category"] == "WORKFLOW_DEADLINE"
                   else "FAILED", stage=error.stage if isinstance(error, TestFailure) else row["stage"])
        if http_start is not None:
            row.setdefault("http_seconds", time.monotonic() - http_start)
    finally:
        if response is not None:
            response.close()
    row.update(event="END", timestamp=utc_now(), elapsed_seconds=time.monotonic() - start)
    emit(row)
    return row


def worker_main(connection, args):
    session = None
    try:
        session, provider = setup_session(args)
        connection.send({"kind": "ready"})
        while True:
            job = connection.recv()
            if job is None:
                break
            result = execute_request(session, provider, args, job,
                                     lambda event: connection.send({"kind": "attempt", **event}))
            connection.send({"kind": "workflow", **result})
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        connection.send({"kind": "worker_error", "stage": "authentication", **diagnostics(error)})
    finally:
        if session is not None:
            session.close()
        connection.close()


class Results:
    def __init__(self, directory):
        self.rows, self.attempts, self.handles, self.writers = [], [], {}, {}
        for name in ("workflows", "attempts", "events"):
            handle = (directory / (name + ".csv")).open("w", encoding="utf-8", newline="")
            self.handles[name] = handle
            self.writers[name] = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            self.writers[name].writeheader()
            handle.flush()

    def write(self, name, row):
        self.writers[name].writerow(row)
        self.handles[name].flush()
        if name == "workflows":
            self.rows.append(dict(row))
        elif name == "attempts":
            self.attempts.append(dict(row))

    def close(self):
        for handle in self.handles.values():
            handle.close()


def spawn_slot(context, args):
    parent, child = context.Pipe()
    process = context.Process(target=worker_main, args=(child, args), daemon=True)
    process.start()
    child.close()
    return {"process": process, "connection": parent, "spawned": time.monotonic(),
            "ready": False, "job": None, "last": {}, "attempt_done": False}


def stop_slot(slot):
    process = slot["process"]
    if process.is_alive():
        process.terminate()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)
    slot["connection"].close()


def finalize(slot, row, results):
    job = slot["job"]
    row = {**slot["last"], **row}
    elapsed = time.monotonic() - job["started_monotonic"]
    if row["outcome"] in SUCCESS:
        row["outcome"] = ("DEADLINE_EXCEEDED" if elapsed >= job["deadline_seconds"] else
                          "SUCCESS_WITHIN_TARGET" if elapsed <= job["target_seconds"] else "SUCCESS_LATE")
        if row["outcome"] == "DEADLINE_EXCEEDED":
            row.update(error_category="WORKFLOW_DEADLINE", stage="completion_delivery")
    row.update(workflow_id=job["workflow_id"], phase=job["phase"], event="END", timestamp=utc_now(),
               started_at=job["started_at"], finished_at=utc_now(), elapsed_seconds=elapsed,
               offset_seconds=job["offset_seconds"], minute=int(job["offset_seconds"] // 60))
    if not slot["attempt_done"]:
        results.write("attempts", row)
        results.write("events", row)
    results.write("workflows", row)
    print(f"{row['workflow_id']} | {row['outcome']} | HTTP {row.get('http_status', '—')} | {elapsed:.3f}s", flush=True)
    slot.update(job=None, last={}, attempt_done=False)


def collect(slot, results):
    while slot["connection"].poll():
        try:
            event = slot["connection"].recv()
        except (EOFError, OSError):
            raise TestFailure("WORKER_EXIT", "worker")
        kind = event.pop("kind")
        if kind == "ready":
            slot["ready"] = True
        elif kind == "worker_error":
            results.write("events", {**event, "timestamp": utc_now(), "event": "WORKER_ERROR"})
            raise TestFailure(event["error_category"], event["stage"])
        elif kind == "workflow":
            finalize(slot, event, results)
        elif kind == "attempt":
            slot["last"].update(event)
            results.write("events", event)
            if event["event"] == "END":
                results.write("attempts", event)
                slot["attempt_done"] = True


def abandon(slot, results, outcome, category):
    stop_slot(slot)
    finalize(slot, {"outcome": outcome, "error_category": category,
                    "stage": slot["last"].get("stage", "dispatch")}, results)


def check_worker(slot, args):
    if not slot["ready"] and time.monotonic() - slot["spawned"] > args.startup_timeout_seconds:
        raise TestFailure("WORKER_STARTUP_TIMEOUT", "authentication")
    if not slot["process"].is_alive():
        raise TestFailure("WORKER_EXIT", "worker")


def run_phase(slots, context, args, results, run_id, phase, duration, limit=None):
    start, submitted = time.monotonic(), 0
    end = start + duration
    try:
        while True:
            for index, slot in enumerate(slots):
                try:
                    collect(slot, results)
                    check_worker(slot, args)
                except TestFailure as error:
                    if slot["job"]:
                        abandon(slot, results, "FAILED", error.category)
                    raise
                if slot["job"] and time.monotonic() - slot["job"]["started_monotonic"] >= args.deadline_seconds:
                    abandon(slot, results, "DEADLINE_EXCEEDED", "WORKFLOW_DEADLINE")
                    slots[index] = slot = spawn_slot(context, args)
                if (slot["ready"] and slot["job"] is None and time.monotonic() < end
                        and (limit is None or submitted < limit)):
                    submitted += 1
                    now = time.monotonic()
                    job = {"workflow_id": f"{run_id}-{phase}-{submitted:06d}", "phase": phase,
                           "started_monotonic": now, "started_at": utc_now(), "offset_seconds": now - start,
                           "target_seconds": args.target_seconds, "deadline_seconds": args.deadline_seconds}
                    slot["job"] = job
                    results.write("events", {"workflow_id": job["workflow_id"], "phase": phase,
                                             "event": "WORKFLOW_START", "timestamp": job["started_at"]})
                    slot["connection"].send(job)
            if ((time.monotonic() >= end or (limit is not None and submitted >= limit))
                    and not any(slot["job"] for slot in slots)):
                break
            time.sleep(.02)
    finally:
        for slot in slots:
            if slot["job"]:
                abandon(slot, results, "INTERRUPTED", "RUN_ABORTED")
    return {"phase": phase, "started": submitted,
            "submission_window_seconds": min(duration, time.monotonic() - start),
            "elapsed_with_drain_seconds": time.monotonic() - start}


def latency_stats(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    values = sorted(values)
    return {"count": len(values), "mean": statistics.mean(values), "max": max(values),
            **{key: values[math.ceil(len(values) * p) - 1]
               for key, p in (("p50", .5), ("p95", .95), ("p99", .99))}}


def summarize(results, phases, args, status):
    rows = [r for r in results.rows if r["phase"] == "measurement"]
    good = [r for r in rows if r["outcome"] in SUCCESS]
    bad = [r for r in rows if r["outcome"] not in SUCCESS]
    outcomes = Counter(r["outcome"] for r in rows)
    reliability = 100 * outcomes["SUCCESS_WITHIN_TARGET"] / len(rows) if rows else None
    phase = next((p for p in phases if p["phase"] == "measurement"), None)
    elapsed = phase["elapsed_with_drain_seconds"] if phase else None
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["minute"]].append(row)
    attempts = [r for r in results.attempts if r["phase"] == "measurement"]
    return {"test_type": "flask_http", "run_status": status,
            "measurement_complete": bool(phase) and status == "COMPLETE",
            "passed": bool(phase and status == "COMPLETE" and reliability is not None
                           and reliability >= args.min_reliability_percent),
            "target_seconds": args.target_seconds, "deadline_seconds": args.deadline_seconds,
            "required_reliability_percent": args.min_reliability_percent,
            "reliability_percent": reliability, "workflows_started": len(rows), "outcomes": dict(outcomes),
            "successful_latency_seconds": latency_stats([r["elapsed_seconds"] for r in good]),
            "failed_latency_seconds": latency_stats([r["elapsed_seconds"] for r in bad]),
            "completed_workflows_per_second_including_drain": len(rows) / elapsed if elapsed else None,
            "successful_workflows_per_second_including_drain": len(good) / elapsed if elapsed else None,
            "http_attempt_outcomes": dict(Counter(r["outcome"] for r in attempts)),
            "http_status_counts": dict(Counter(str(r.get("http_status", "NO_RESPONSE")) for r in rows)),
            "failure_categories": dict(Counter(r.get("error_category", "UNKNOWN") for r in bad)),
            "app_error_codes": dict(Counter(r["app_error_code"] for r in bad if r.get("app_error_code"))),
            "per_minute_start_cohorts": [
                {"minute": minute, "started": len(group),
                 "outcomes": dict(Counter(r["outcome"] for r in group)),
                 "successful_latency_seconds": latency_stats([
                     r["elapsed_seconds"] for r in group if r["outcome"] in SUCCESS])}
                for minute, group in sorted(buckets.items())],
            "phases": phases,
            "notes": ["One process and persistent HTTP session per simulated client; no think time.",
                      "Backend mode is operator-declared; HTTP success does not prove live inference or answer quality.",
                      "Each workflow uses a fresh conversation UUID; correlation marker preserves slash routing.",
                      "No automatic chat retries; internal Databricks invocations are not observable here.",
                      "HTTP attempts can finish before parent receipt; workflow timing includes dispatch/collection.",
                      "Stopping a local worker does not cancel Flask or Databricks work already running.",
                      "Remote proxy, Flask, backend, persistence and analytics latency are included.",
                      "Interrupted or errored runs cannot pass; small samples do not prove long-term reliability."]}


def positive_float(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--auth", choices=("none", "password", "bearer", "databricks"), default="none")
    parser.add_argument("--username-env", default="FLASK_TEST_USERNAME")
    parser.add_argument("--password-env", default="FLASK_TEST_PASSWORD")
    parser.add_argument("--token-env", default="FLASK_TEST_BEARER_TOKEN")
    parser.add_argument("--databricks-profile")
    parser.add_argument("--ca-bundle", type=Path)
    parser.add_argument("--backend-mode", choices=("unknown", "databricks", "mock"), default="unknown",
                        help="Operator declaration, not remote configuration verification")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--duration-seconds", type=positive_float, default=600)
    parser.add_argument("--warmup-seconds", type=float, default=60)
    parser.add_argument("--target-seconds", type=positive_float, default=60)
    parser.add_argument("--deadline-seconds", type=positive_float, default=180)
    parser.add_argument("--startup-timeout-seconds", type=positive_float, default=60)
    parser.add_argument("--connect-timeout-seconds", type=positive_float, default=10)
    parser.add_argument("--read-timeout-seconds", type=positive_float, default=180)
    parser.add_argument("--min-reliability-percent", type=float, default=99)
    parser.add_argument("--max-response-bytes", type=int, default=2_000_000)
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--output-dir", type=Path, default=Path("stress_Test/FLASK"))
    parser.add_argument("--run-note", default="", help="Server configuration/stage notes; no secrets")
    args = parser.parse_args(argv)
    try:
        url = urlsplit(args.base_url)
        _ = url.port
    except ValueError:
        parser.error("--base-url is invalid")
    if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        parser.error("--base-url must be an http(s) origin with optional path prefix and no credentials/query")
    args.base_url = args.base_url.rstrip("/")
    if args.base_url.endswith("/api/v1/chat"):
        parser.error("--base-url must omit /api/v1/chat")
    if args.concurrency <= 0 or args.max_response_bytes <= 0:
        parser.error("--concurrency and --max-response-bytes must be positive")
    if not math.isfinite(args.warmup_seconds) or args.warmup_seconds < 0:
        parser.error("--warmup-seconds must be finite and nonnegative")
    if not 0 <= args.min_reliability_percent <= 100:
        parser.error("--min-reliability-percent must be between 0 and 100")
    if args.deadline_seconds < args.target_seconds:
        parser.error("--deadline-seconds must be at least --target-seconds")
    if not args.question.strip():
        parser.error("--question cannot be empty")
    if args.ca_bundle and not args.ca_bundle.is_file():
        parser.error("--ca-bundle must be an existing CA certificate bundle")
    for name in ((args.username_env, args.password_env) if args.auth == "password" else
                 (args.token_env,) if args.auth == "bearer" else ()):
        if not os.environ.get(name, "").strip():
            parser.error(f"Required authentication environment variable is unset: {name}")
    return args


def main(argv=None):
    args = parse_args(argv)
    run_id = f"STRESS-{datetime.now(timezone.utc):%Y%m%d_%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = args.output_dir / run_id
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"test_type": "flask_http", "run_id": run_id, "started_at": utc_now(),
                "base_url": args.base_url, "endpoint": args.base_url + "/api/v1/chat", "auth": args.auth,
                "backend_mode_declared": args.backend_mode, "concurrency": args.concurrency,
                "duration_seconds": args.duration_seconds, "warmup_seconds": args.warmup_seconds,
                "target_seconds": args.target_seconds, "deadline_seconds": args.deadline_seconds,
                "network_timeout_seconds": args.read_timeout_seconds,
                "connect_timeout_seconds": args.connect_timeout_seconds,
                "min_reliability_percent": args.min_reliability_percent,
                "max_response_bytes": args.max_response_bytes, "custom_ca_bundle": bool(args.ca_bundle),
                "question_characters": len(args.question),
                "question_sha256": hashlib.sha256(args.question.encode()).hexdigest(), "run_note": args.run_note}
    (directory / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2), flush=True)
    print("The Flask server must already be running. Local debug-server results describe that setup.", flush=True)
    results, context = Results(directory), mp.get_context("spawn")
    slots, phases, status, run_error = [], [], "COMPLETE", None
    try:
        slots.append(spawn_slot(context, args))
        phases.append(run_phase(slots, context, args, results, run_id, "preflight",
                                args.startup_timeout_seconds + args.deadline_seconds, limit=1))
        if not results.rows or results.rows[-1]["outcome"] not in SUCCESS:
            raise TestFailure("PREFLIGHT_FAILED", "preflight")
        slots.extend(spawn_slot(context, args) for _ in range(args.concurrency - 1))
        while not all(slot["ready"] for slot in slots):
            for slot in slots:
                collect(slot, results)
                check_worker(slot, args)
            time.sleep(.02)
        if args.warmup_seconds:
            phases.append(run_phase(slots, context, args, results, run_id,
                                    "warmup", args.warmup_seconds))
        phases.append(run_phase(slots, context, args, results, run_id,
                                "measurement", args.duration_seconds))
    except KeyboardInterrupt:
        status = "INTERRUPTED"
    except Exception as error:
        status, run_error = "ERROR", diagnostics(error)
        print(f"Run stopped: {run_error['error_category']}. Inspect events.csv and server logs.", flush=True)
    finally:
        for slot in slots:
            stop_slot(slot)
        summary = summarize(results, phases, args, status)
        summary.update(run_error=run_error, finished_at=utc_now())
        (directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        results.close()
        print(json.dumps(summary, indent=2), flush=True)
        print(f"Results: {directory.resolve()}", flush=True)
    return 130 if status == "INTERRUPTED" else 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
