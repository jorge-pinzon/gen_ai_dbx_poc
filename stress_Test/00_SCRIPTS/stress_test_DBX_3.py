"""Sustained reliability test of the real Supervisor workflow.

Run: PYTHONPATH=src python3 stress_test_DBX_3.py --help
No network calls occur on import. Only this harness subclasses the production
client. Each persistent process owns its session/token cache; the parent enforces
workflow deadlines by terminating overdue workers. Server-side operations may
continue after disconnect (including SQL statements); termination only stops the
local client. CSV files contain metadata, never raw questions/answers/credentials.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import multiprocessing as mp
import re
import statistics
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from mariner_genai_dbx.bootstrap import create_supervisor_service
from mariner_genai_dbx.config import load_settings
from mariner_genai_dbx.models import ConversationHistory
from mariner_genai_dbx.supervisor_service import DatabricksSupervisorService

QUESTION = (
    "Mandatory application routing directive: Call the Branch Operations specialist "
    "named mariner-policy-assistant subagent/tool now and wait for it to complete. "
    "Return the worker's final grounded answer and source information. "
    "Do not answer from general model knowledge. "
    "Employee question: What does the policy say about record retention?"
)
SUCCESS = {"SUCCESS_WITHIN_TARGET", "SUCCESS_LATE"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


# Exceptions whose messages are fixed strings written by the app or this harness (plus, at most,
# an endpoint error code), so they can be recorded. Any other message is never written.
SAFE_MESSAGE_TYPES = {"SupervisorInvocationError", "CitationResolutionError", "StreamFailureError",
                      "IncompleteStreamError"}
SAFE_MESSAGE = re.compile(r"[A-Za-z0-9 _.,:;'()/=-]{1,200}")


def safe_code(value):
    """An endpoint error code or event type, or '' if it does not look like one."""
    text = str(value or "")
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", text) else ""


def error_details(error):
    """Allowlist diagnostics; exception messages/response bodies can contain secrets."""
    chain, seen, status, detail = [], set(), None, ""
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(type(error).__name__)
        message = str(error)
        if type(error).__name__ in SAFE_MESSAGE_TYPES and SAFE_MESSAGE.fullmatch(message):
            detail = message  # the innermost (most specific) safe message wins
        response = getattr(error, "response", None)
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            status = code
        error = error.__cause__ or error.__context__
    category = "CLIENT_ERROR"
    if status == 429:
        category = "RATE_LIMITED"
    elif status in (401, 403):
        category = "AUTHENTICATION"
    elif status is not None:
        category = "HTTP_ERROR"
    elif any("timeout" in name.lower() for name in chain):
        category = "NETWORK_TIMEOUT"
    elif any("connection" in name.lower() for name in chain):
        category = "CONNECTION_ERROR"
    elif "IncompleteStreamError" in chain:
        category = "INCOMPLETE_STREAM"
    elif "StreamFailureError" in chain:
        category = "STREAM_ERROR"
    return {"error_category": category, "exception_chain": " -> ".join(chain),
            "http_status": status, "error_detail": detail}


class IncompleteStreamError(RuntimeError):
    pass


class StreamFailureError(RuntimeError):
    pass


class StreamObserver:
    """Recognize both response.done and Agent Bricks' [DONE] termination."""
    def __init__(self, response):
        self.response = response
        self.terminal = ""

    def __getattr__(self, name):
        return getattr(self.response, name)

    def iter_lines(self, **kwargs):
        for line in self.response.iter_lines(**kwargs):
            decoded = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
            if decoded and decoded.startswith("data:"):
                data = decoded[5:].strip()
                if data == "[DONE]":
                    self.terminal = "DONE"
                else:
                    try:
                        event = json.loads(data)
                    except ValueError:
                        event = {}
                    if isinstance(event, dict):
                        kind = event.get("type")
                        if kind in {"error", "response.failed", "response.incomplete"} or event.get("error_code"):
                            error = event.get("error") if isinstance(event.get("error"), dict) else {}
                            payload = event.get("response") if isinstance(event.get("response"), dict) else {}
                            failure = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                            code = (safe_code(event.get("error_code")) or safe_code(error.get("code"))
                                    or safe_code(failure.get("code")))
                            raise StreamFailureError(f"Endpoint reported a stream failure: type={safe_code(kind)} code={code}")
                        if kind in {"response.done", "response.completed"}:
                            payload = event.get("response", {})
                            if isinstance(payload, dict) and payload.get("status") in {"failed", "incomplete", "cancelled"}:
                                failure = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                                raise StreamFailureError("Endpoint reported unsuccessful completion: "
                                                         f"status={safe_code(payload.get('status'))} code={safe_code(failure.get('code'))}")
                            self.terminal = kind
            yield line


class ObservedCitations:
    def __init__(self, resolver, service):
        self.resolver, self.service = resolver, service

    def resolve_labels(self, labels, answer=None):
        service = self.service
        service.stage = "citation_resolution"
        start = time.monotonic()
        service.emit("citation", "START")
        try:
            sources = tuple(self.resolver.resolve_labels(labels, answer))
            # Match the production service's unresolved-label failure rule.
            if labels and not sources:
                raise RuntimeError("Source labels did not resolve")
        except Exception as error:
            service.emit("citation", "END", outcome="FAILED",
                         elapsed_seconds=time.monotonic() - start, **error_details(error))
            raise
        service.emit("citation", "END", outcome="SUCCESS",
                     elapsed_seconds=time.monotonic() - start)
        return sources


class ObservedSupervisor(DatabricksSupervisorService):
    """Production invocation/approval logic with test-only telemetry."""
    def configure_observer(self, send):
        self.send = send
        self._citation_resolver = ObservedCitations(self._citation_resolver, self)

    def begin(self, job):
        self.job = job
        self.stage = "response_validation"
        self.invocation = 0
        self.attempt = 0
        self.open_attempt = None
        self.last_status = None
        self.last_request_id = ""
        self.stream_terminal = ""

    def emit(self, kind, event, **fields):
        self.send({"kind": kind, "event": event, "timestamp": utc_now(),
                   "workflow_id": self.job["workflow_id"], "phase": self.job["phase"],
                   "invocation": self.invocation, "attempt": self.attempt,
                   "invocation_kind": "worker_continuation" if self.invocation > 1 else "initial",
                   "stage": self.stage, **fields})

    # Overrides forward extra keyword arguments (on_event, stream, live, ...) so they keep
    # matching the production client as it gains options.
    def _continue_approved_worker_calls(self, url, response_input, response, **kwargs):
        try:
            return super()._continue_approved_worker_calls(url, response_input, response, **kwargs)
        except Exception:
            if self.stage == "response_validation":
                self.stage = "worker_continuation"
            raise

    def _access_token(self):
        self.stage = "authentication"
        start = time.monotonic()
        self.emit("authentication", "START")
        try:
            value = super()._access_token()
        except Exception as error:
            self.emit("authentication", "END", outcome="FAILED",
                      elapsed_seconds=time.monotonic() - start, **error_details(error))
            raise
        self.emit("authentication", "END", outcome="SUCCESS",
                  elapsed_seconds=time.monotonic() - start)
        self.stage = "invocation_http"
        return value

    def finish_attempt(self, outcome, **fields):
        if self.open_attempt is not None:
            fields = {key: value for key, value in fields.items() if value is not None}
            self.emit("attempt", "END", outcome=outcome,
                      elapsed_seconds=time.monotonic() - self.open_attempt,
                      stream_terminal=self.stream_terminal,
                      **{"http_status": self.last_status, "request_id": self.last_request_id, **fields})
            self.open_attempt = None

    def _post_invocation(self, url, body, access_token, **kwargs):
        self.stage = "invocation_http"
        self.attempt += 1
        self.last_status = None
        self.last_request_id = ""
        self.stream_terminal = ""
        self.open_attempt = time.monotonic()
        self.emit("attempt", "START")
        try:
            response = super()._post_invocation(url, body, access_token, **kwargs)
            self.last_status = response.status_code
            # Headers are metadata only; never emit Authorization or all headers.
            headers = getattr(response, "headers", {}) or {}
            request_id = headers.get("x-databricks-request-id") or headers.get("x-request-id", "")
            self.last_request_id = str(request_id)[:256]
            self.emit("attempt", "HEADERS", http_status=response.status_code,
                      request_id=self.last_request_id)
            if response.status_code >= 400:
                category = "RATE_LIMITED" if response.status_code == 429 else (
                    "AUTHENTICATION" if response.status_code in (401, 403) else "HTTP_ERROR")
                self.finish_attempt("FAILED", http_status=response.status_code,
                                    error_category=category)
                response.close()
            return response
        except Exception as error:
            self.finish_attempt("FAILED", **error_details(error))
            raise

    def _parse_stream_response(self, response, *args, **kwargs):
        self.stage = "stream"
        start = time.monotonic()
        self.emit("stream", "START")
        observed = StreamObserver(response)
        try:
            payload = super()._parse_stream_response(observed, *args, **kwargs)
            if not observed.terminal:
                raise IncompleteStreamError("Stream ended without a completion marker")
            self.emit("stream", "END", outcome="SUCCESS", stream_terminal=observed.terminal,
                      elapsed_seconds=time.monotonic() - start)
            return payload
        except Exception as error:
            self.emit("stream", "END", outcome="FAILED",
                      elapsed_seconds=time.monotonic() - start, **error_details(error))
            raise
        finally:
            self.stream_terminal = observed.terminal

    def _invoke(self, url, body, **kwargs):
        self.invocation += 1
        self.attempt = 0
        self.stage = "invocation_http"
        self.last_status = None
        self.last_request_id = ""
        start = time.monotonic()
        self.emit("invocation", "START")
        try:
            result = super()._invoke(url, body, **kwargs)
        except Exception as error:
            details = error_details(error)
            self.finish_attempt("FAILED", **details)
            self.emit("invocation", "END", outcome="FAILED",
                      request_id=self.last_request_id,
                      elapsed_seconds=time.monotonic() - start,
                      **{**details, "http_status": details["http_status"] or self.last_status})
            raise
        self.finish_attempt("SUCCESS", http_status=self.last_status)
        self.emit("invocation", "END", outcome="SUCCESS", http_status=self.last_status,
                  request_id=self.last_request_id,
                  stream_terminal=self.stream_terminal, elapsed_seconds=time.monotonic() - start)
        self.stage = "response_validation"
        return result


def worker_main(connection, settings):
    # Avoid production DEBUG stream logging exposing content or distorting timings.
    logging.disable(logging.CRITICAL)
    try:
        service = create_supervisor_service(settings)
        if not isinstance(service, DatabricksSupervisorService):
            raise RuntimeError("Live Supervisor service required")
        observed = ObservedSupervisor(service.config, http_session=service._http,
                                      citation_resolver=service._citation_resolver)
        observed.configure_observer(connection.send)
        connection.send({"kind": "ready"})
    except Exception as error:
        connection.send({"kind": "startup_error", **error_details(error)})
        return
    try:
        while True:
            job = connection.recv()
            if job is None:
                return
            observed.begin(job)
            start = time.monotonic()
            row = {"kind": "workflow", "workflow_id": job["workflow_id"],
                   "phase": job["phase"], "started_at": utc_now()}
            try:
                result = observed.answer(
                    f"[STRESS_TEST_ID={job['workflow_id']}]\n\n{job['question']}",
                    job["workflow_id"], ConversationHistory())
                elapsed = time.monotonic() - job["started_monotonic"]
                outcome = "SUCCESS_WITHIN_TARGET" if elapsed <= job["target_seconds"] else "SUCCESS_LATE"
                row.update(outcome=outcome, agents_used=list(result.agents_used),
                           source_count=len(result.sources), usage=asdict(result.usage),
                           expected_agent_reported=(job["expected_agent"] in result.agents_used
                                                    if job["expected_agent"] else None),
                           has_sources=bool(result.sources))
            except Exception as error:
                row.update(outcome="FAILED", stage=observed.stage, **error_details(error))
            row.update(elapsed_seconds=time.monotonic() - start,
                       invocation_count=observed.invocation, finished_at=utc_now())
            connection.send(row)
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


EVENT_FIELDS = ["timestamp", "workflow_id", "phase", "kind", "event", "invocation", "attempt",
                "invocation_kind", "stage", "outcome", "elapsed_seconds", "http_status", "request_id",
                "stream_terminal", "error_category", "exception_chain", "error_detail"]
WORKFLOW_FIELDS = ["workflow_id", "phase", "started_at", "finished_at", "offset_seconds", "minute",
                   "outcome", "elapsed_seconds", "stage", "error_category", "exception_chain", "error_detail",
                   "http_status", "invocation_count", "inference_outcome", "inference_seconds",
                   "citation_outcome", "citation_seconds", "agents_used", "source_count",
                   "has_sources", "expected_agent_reported", "usage"]


class Results:
    """Only the parent writes files. Start records survive interrupted workflows."""
    def __init__(self, directory):
        self.directory = directory
        self.files = []
        self.writers = {}
        self.rows = []
        self.invocations = []
        self.attempts = []
        for name, fields in (("events", EVENT_FIELDS), ("workflows", WORKFLOW_FIELDS),
                             ("invocations", EVENT_FIELDS), ("attempts", EVENT_FIELDS)):
            handle = (directory / f"{name}.csv").open("w", newline="", encoding="utf-8")
            self.files.append(handle)
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            self.writers[name] = writer
        self.flush()

    def write(self, name, row):
        self.writers[name].writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                                    for key, value in row.items() if key in self.writers[name].fieldnames})
        if name == "workflows":
            self.rows.append(row)
        elif name == "events" and row.get("kind") == "invocation" and row.get("event") == "END":
            self.invocations.append(row)
            self.write("invocations", row)
        elif name == "events" and row.get("kind") == "attempt" and row.get("event") == "END":
            self.attempts.append(row)
            self.write("attempts", row)
        self.flush()

    def flush(self):
        for handle in self.files:
            handle.flush()

    def close(self):
        for handle in self.files:
            handle.close()


def spawn_slot(context, settings):
    parent, child = context.Pipe()
    process = context.Process(target=worker_main, args=(child, settings), daemon=True)
    process.start()
    child.close()
    return {"process": process, "connection": parent, "ready": False,
            "spawned": time.monotonic(), "job": None, "active": {}, "invocations": [],
            "citations": []}


def stop_slot(slot):
    process = slot["process"]
    if process.is_alive():
        process.terminate()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)
    slot["connection"].close()


def record_event(slot, event, results):
    # Invocation START precedes attempt 1; its END can follow a retry (attempt 2).
    key = (event["kind"], event.get("invocation"),
           event.get("attempt") if event["kind"] in {"attempt", "stream"} else 0)
    if event["event"] == "START":
        slot["active"][key] = (event, time.monotonic())
    elif event["event"] == "HEADERS" and key in slot["active"]:
        original, received = slot["active"][key]
        slot["active"][key] = ({**original, "http_status": event.get("http_status"),
                                "request_id": event.get("request_id")}, received)
    elif event["event"] == "END":
        slot["active"].pop(key, None)
        if event["kind"] == "invocation":
            slot["invocations"].append(event)
        elif event["kind"] == "citation":
            slot["citations"].append(event)
    results.write("events", event)


def finish_workflow(slot, row, results):
    job = slot["job"]
    elapsed = time.monotonic() - job["started_monotonic"]
    row.update(workflow_id=job["workflow_id"], phase=job["phase"],
               started_at=job["started_at"], elapsed_seconds=elapsed,
               offset_seconds=job["offset_seconds"], minute=int(job["offset_seconds"] // 60),
               finished_at=utc_now())
    if row["outcome"] in SUCCESS:
        row["outcome"] = ("DEADLINE_EXCEEDED" if elapsed >= job["deadline_seconds"] else
                          "SUCCESS_WITHIN_TARGET" if elapsed <= job["target_seconds"] else "SUCCESS_LATE")
        if row["outcome"] == "DEADLINE_EXCEEDED":
            row.update(error_category="WORKFLOW_DEADLINE", stage="completion_delivery")
    invocations, citations = slot["invocations"], slot["citations"]
    inference_ok = (invocations and all(event["outcome"] == "SUCCESS" for event in invocations)
                    and (row["outcome"] in SUCCESS or row.get("stage") == "citation_resolution"))
    row.update(inference_outcome="SUCCESS" if inference_ok else "FAILED",
        inference_seconds=sum(event["elapsed_seconds"] for event in invocations),
        invocation_count=len(invocations),
        citation_outcome=citations[-1]["outcome"] if citations else "NOT_REACHED",
        citation_seconds=sum(event["elapsed_seconds"] for event in citations))
    results.write("workflows", row)
    print(f"{row['workflow_id']} | {row['outcome']} | {elapsed:.3f}s", flush=True)
    slot["job"] = None
    slot["active"].clear()
    slot["invocations"].clear()
    slot["citations"].clear()


def abandon_workflow(slot, results, outcome, category):
    # Finalize every started attempt/invocation even if a child is killed mid-stream.
    active = list(slot["active"].values())
    stage = active[-1][0]["stage"] if active else "response_validation"
    for event, received in active:
        record_event(slot, {**event, "event": "END", "timestamp": utc_now(),
                           "outcome": outcome, "error_category": category,
                           "elapsed_seconds": time.monotonic() - received}, results)
    finish_workflow(slot, {"outcome": outcome, "error_category": category,
                           "stage": stage}, results)


def run_phase(slots, context, settings, args, results, run_id, phase, duration, limit=None):
    start = time.monotonic()
    deadline = start + duration
    submitted = 0
    try:
        while True:
            now = time.monotonic()
            accepting = now < deadline and (limit is None or submitted < limit)
            for index, slot in enumerate(slots):
                connection = slot["connection"]
                try:
                    while connection.poll():
                        event = connection.recv()
                        if event["kind"] == "ready":
                            slot["ready"] = True
                        elif event["kind"] == "startup_error":
                            raise RuntimeError(f"Worker startup failed: {event['exception_chain']}")
                        elif event["kind"] == "workflow":
                            finish_workflow(slot, event, results)
                        else:
                            record_event(slot, event, results)
                except (EOFError, OSError):
                    if slot["job"]:
                        abandon_workflow(slot, results, "FAILED", "WORKER_EXIT")
                    raise RuntimeError("Worker connection closed unexpectedly")
                now = time.monotonic()
                if slot["job"] and now - slot["job"]["started_monotonic"] >= args.deadline_seconds:
                    stop_slot(slot)
                    abandon_workflow(slot, results, "DEADLINE_EXCEEDED", "WORKFLOW_DEADLINE")
                    slots[index] = slot = spawn_slot(context, settings)
                if not slot["ready"] and now - slot["spawned"] > args.startup_timeout_seconds:
                    raise RuntimeError("Worker initialization exceeded startup timeout")
                if not slot["process"].is_alive() and not slot["connection"].poll():
                    raise RuntimeError("Worker exited unexpectedly")
                if (slot["ready"] and slot["job"] is None and time.monotonic() < deadline
                        and (limit is None or submitted < limit)):
                    submitted += 1
                    now = time.monotonic()
                    job = {"workflow_id": f"{run_id}-{phase}-{submitted:06d}", "phase": phase,
                           "started_at": utc_now(), "started_monotonic": now,
                           "offset_seconds": now - start, "target_seconds": args.target_seconds,
                           "deadline_seconds": args.deadline_seconds,
                           "question": args.question, "expected_agent": args.expected_agent}
                    slot["job"] = job
                    results.write("events", {"kind": "workflow", "event": "START",
                                             "timestamp": job["started_at"],
                                             "workflow_id": job["workflow_id"], "phase": phase})
                    slot["connection"].send(job)
            if not accepting and not any(slot["job"] for slot in slots):
                break
            time.sleep(0.02)
    finally:
        for slot in slots:
            if slot["job"]:
                stop_slot(slot)
                abandon_workflow(slot, results, "INTERRUPTED", "RUN_ABORTED")
    return {"phase": phase, "submission_window_seconds": min(duration, time.monotonic() - start),
            "elapsed_with_drain_seconds": time.monotonic() - start, "started": submitted}


def latency_stats(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    values = sorted(values)
    # Explicit nearest-rank convention; retain original float precision in files.
    return {"count": len(values), "mean": statistics.mean(values),
            **{label: values[max(0, math.ceil(len(values) * p) - 1)]
               for label, p in (("p50", .5), ("p95", .95), ("p99", .99))}, "max": max(values)}


def summarize(results, phases, args, run_status):
    rows = [row for row in results.rows if row["phase"] == "measurement"]
    good = [row for row in rows if row["outcome"] in SUCCESS]
    failed = [row for row in rows if row["outcome"] not in SUCCESS]
    counts = Counter(row["outcome"] for row in rows)
    reliability = 100 * counts["SUCCESS_WITHIN_TARGET"] / len(rows) if rows else None
    phase = next((p for p in phases if p["phase"] == "measurement"), None)
    elapsed = phase["elapsed_with_drain_seconds"] if phase else None
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["minute"]].append(row)
    invocations = [r for r in results.invocations if r["phase"] == "measurement"]
    attempts = [r for r in results.attempts if r["phase"] == "measurement"]
    return {"run_status": run_status, "measurement_complete": bool(phase) and run_status == "COMPLETE",
            "target_seconds": args.target_seconds, "deadline_seconds": args.deadline_seconds,
            "required_reliability_percent": args.min_reliability_percent,
            "reliability_percent": reliability,
            "passed": bool(phase and run_status == "COMPLETE" and reliability is not None
                           and reliability >= args.min_reliability_percent),
            "workflows_started": len(rows), "outcomes": dict(counts),
            "successful_latency_seconds": latency_stats([r["elapsed_seconds"] for r in good]),
            "failed_latency_seconds": latency_stats([r["elapsed_seconds"] for r in failed]),
            "completed_workflows_per_second_including_drain": len(rows) / elapsed if elapsed else None,
            "successful_workflows_per_second_including_drain": len(good) / elapsed if elapsed else None,
            "invocation_outcomes": dict(Counter(r["outcome"] for r in invocations)),
            "invocation_success_percent": (100 * sum(r["outcome"] == "SUCCESS" for r in invocations)
                                           / len(invocations) if invocations else None),
            "http_attempt_outcomes": dict(Counter(r["outcome"] for r in attempts)),
            "successful_invocation_latency_seconds": latency_stats([
                r["elapsed_seconds"] for r in invocations if r["outcome"] == "SUCCESS"]),
            "failed_invocation_latency_seconds": latency_stats([
                r["elapsed_seconds"] for r in invocations if r["outcome"] != "SUCCESS"]),
            "failure_categories": dict(Counter(r.get("error_category", "UNKNOWN") for r in failed)),
            "failure_details": dict(Counter(r.get("error_detail") or "(none)" for r in failed).most_common()),
            "per_minute_start_cohorts": [
                {"minute": minute, "started": len(group),
                 "outcomes": dict(Counter(r["outcome"] for r in group)),
                 "successful_latency_seconds": latency_stats([
                     r["elapsed_seconds"] for r in group if r["outcome"] in SUCCESS])}
                for minute, group in sorted(buckets.items())], "phases": phases,
            "notes": ["One persistent process/session/token cache per concurrent client.",
                      "Inference includes authentication, retries and approval continuations; citations are separate.",
                      "Deadline termination stops local work; remote operations may continue.",
                      "Agent/source flags are observations, not proof of grounded answer quality.",
                      "Endpoint capacity/configuration and background traffic must be recorded externally.",
                      "Interrupted runs preserve outcomes but have no passing reliability verdict."]}


def positive_float(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration-seconds", type=positive_float, default=600)
    parser.add_argument("--warmup-seconds", type=float, default=30)
    parser.add_argument("--target-seconds", type=positive_float, default=60)
    parser.add_argument("--deadline-seconds", type=positive_float, default=180)
    parser.add_argument("--startup-timeout-seconds", type=positive_float, default=60)
    parser.add_argument("--min-reliability-percent", type=float, default=99)
    parser.add_argument("--output-dir", type=Path, default=Path("stress_Test"))
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--expected-agent", default="mariner-policy-assistant")
    parser.add_argument("--run-note", default="", help="Endpoint configuration/background traffic notes; no secrets")
    args = parser.parse_args(argv)
    if args.concurrency <= 0:
        parser.error("--concurrency must be greater than zero")
    if not math.isfinite(args.warmup_seconds) or args.warmup_seconds < 0:
        parser.error("--warmup-seconds must be finite and nonnegative")
    if not 0 <= args.min_reliability_percent <= 100:
        parser.error("--min-reliability-percent must be between 0 and 100")
    if args.deadline_seconds < args.target_seconds:
        parser.error("--deadline-seconds must be at least --target-seconds")
    if not args.question.strip():
        parser.error("--question cannot be empty")
    return args


def require_live(settings):
    if settings.supervisor_mode != "databricks":
        raise ValueError("Refusing to run: SUPERVISOR_MODE must be databricks")


def main(argv=None):
    args = parse_args(argv)
    settings = load_settings()
    require_live(settings)
    run_id = f"STRESS-{datetime.now(timezone.utc):%Y%m%d_%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = args.output_dir / run_id
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"run_id": run_id, "started_at": utc_now(), "endpoint": settings.supervisor_endpoint,
                "concurrency": args.concurrency, "duration_seconds": args.duration_seconds,
                "warmup_seconds": args.warmup_seconds, "target_seconds": args.target_seconds,
                "deadline_seconds": args.deadline_seconds,
                "network_timeout_seconds": settings.request_timeout_seconds,
                "citation_lookup_enabled": bool(settings.databricks_warehouse_id),
                "min_reliability_percent": args.min_reliability_percent,
                "expected_agent": args.expected_agent, "question_characters": len(args.question),
                "question_sha256": hashlib.sha256(args.question.encode("utf-8")).hexdigest(),
                "run_note": args.run_note}
    (directory / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2), flush=True)
    results = Results(directory)
    context = mp.get_context("spawn")
    slots, phases, status, run_error = [], [], "COMPLETE", None
    try:
        slots.append(spawn_slot(context, settings))
        # Preflight is excluded from measured outcomes and warms one client's auth.
        phases.append(run_phase(slots, context, settings, args, results, run_id,
                                "preflight", args.startup_timeout_seconds + args.deadline_seconds, limit=1))
        if not results.rows or results.rows[-1]["outcome"] not in SUCCESS:
            raise RuntimeError("Preflight failed; inspect events.csv before applying load")
        slots.extend(spawn_slot(context, settings) for _ in range(args.concurrency - 1))
        # Finish process initialization before beginning warm-up/measurement.
        startup_end = time.monotonic() + args.startup_timeout_seconds
        while not all(slot["ready"] for slot in slots):
            for slot in slots:
                if not slot["ready"] and slot["connection"].poll():
                    event = slot["connection"].recv()
                    if event["kind"] != "ready":
                        raise RuntimeError("Worker initialization failed")
                    slot["ready"] = True
            if time.monotonic() > startup_end:
                raise RuntimeError("Worker initialization exceeded startup timeout")
            time.sleep(.02)
        if args.warmup_seconds:
            phases.append(run_phase(slots, context, settings, args, results, run_id,
                                    "warmup", args.warmup_seconds))
        phases.append(run_phase(slots, context, settings, args, results, run_id,
                                "measurement", args.duration_seconds))
    except KeyboardInterrupt:
        status = "INTERRUPTED"
    except Exception as error:
        status = "ERROR"
        run_error = error_details(error)
        print(f"Run stopped: {type(error).__name__}. Inspect saved events.", flush=True)
    finally:
        for slot in slots:
            stop_slot(slot)
        summary = summarize(results, phases, args, status)
        summary["run_error"] = run_error
        summary["finished_at"] = utc_now()
        (directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        results.close()
        print(json.dumps(summary, indent=2), flush=True)
        print(f"Results: {directory.resolve()}", flush=True)
    return 130 if status == "INTERRUPTED" else (0 if summary["passed"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
