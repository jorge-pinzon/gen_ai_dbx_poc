"""Offline reliability harness tests. Never contact Databricks."""
import csv
import json
import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import stress_Test.Scripts.stress_test_DBX_3 as harness
from mariner_genai_dbx.models import ConversationHistory, SupervisorConfig


class Response:
    def __init__(self, payload=None, status=200, events=None):
        self.payload, self.status_code = payload, status
        self.headers = {"x-request-id": "request-test"}
        self.events = events
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError("secret error body must never be saved")
            error.response = self
            raise error

    def json(self):
        return self.payload

    def iter_lines(self, **kwargs):
        for event in self.events or []:
            yield "data: " + (event if isinstance(event, str) else json.dumps(event))

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def message(text="Answer"):
    return {"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": text}]}


def stream(*items):
    return Response(events=[*({"type": "response.output_item.done", "item": item}
                              for item in items), "[DONE]"])


def fake_worker(connection, settings):
    """A real child process exercises termination and event persistence offline."""
    connection.send({"kind": "ready"})
    while True:
        job = connection.recv()
        common = {"workflow_id": job["workflow_id"], "phase": job["phase"],
                  "timestamp": harness.utc_now(), "stage": "stream", "invocation": 1}
        connection.send({**common, "kind": "invocation", "event": "START", "attempt": 0})
        connection.send({**common, "kind": "attempt", "event": "START", "attempt": 1})
        if job["question"] == "hang":
            time.sleep(30)
        else:
            connection.send({**common, "kind": "attempt", "event": "END", "attempt": 1,
                             "outcome": "SUCCESS", "elapsed_seconds": .001})
            connection.send({**common, "kind": "invocation", "event": "END", "attempt": 1,
                             "outcome": "SUCCESS", "elapsed_seconds": .002})
            connection.send({"kind": "workflow", "outcome": "SUCCESS_WITHIN_TARGET"})


class ObserverTests(unittest.TestCase):
    def make_service(self, *responses, oauth=False, resolver=None):
        config = SupervisorConfig(workspace_host="https://example.test", endpoint_name="test",
                                  token=None if oauth else "secret-token",
                                  client_id="id" if oauth else None,
                                  client_secret="secret" if oauth else None)
        service = harness.ObservedSupervisor(config, http_session=Session(*responses),
                                             citation_resolver=resolver)
        self.events = []
        service.configure_observer(self.events.append)
        service.begin({"workflow_id": "test", "phase": "measurement"})
        return service

    def test_live_mode_required(self):
        with self.assertRaises(ValueError):
            harness.require_live(SimpleNamespace(supervisor_mode="mock"))

    def test_success_and_complete_event_pairing(self):
        service = self.make_service(stream(message()))
        self.assertEqual(service.answer("question", "id", ConversationHistory()).answer, "Answer")
        slot = {"active": {}, "invocations": [], "citations": []}
        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                for event in self.events:
                    harness.record_event(slot, event, results)
                self.assertEqual(slot["active"], {})
                self.assertEqual(len(results.invocations), 1)
                self.assertEqual(len(results.attempts), 1)
            finally:
                results.close()

    def test_http_error_preserves_status_without_message(self):
        service = self.make_service(Response(status=429))
        with self.assertRaises(Exception) as caught:
            service.answer("question", "id", ConversationHistory())
        details = harness.error_details(caught.exception)
        self.assertEqual(details["http_status"], 429)
        self.assertEqual(details["error_category"], "RATE_LIMITED")
        self.assertNotIn("secret", json.dumps(self.events))
        self.assertEqual(self.events[-1]["outcome"], "FAILED")

    def test_authentication_retry_is_separate_attempt(self):
        token = lambda: Response({"access_token": "secret-access-token", "expires_in": 3600})
        service = self.make_service(token(), Response(status=401), token(), stream(message()), oauth=True)
        service.answer("question", "id", ConversationHistory())
        attempts = [e for e in self.events if e["kind"] == "attempt" and e["event"] == "END"]
        self.assertEqual([e["outcome"] for e in attempts], ["FAILED", "SUCCESS"])
        self.assertEqual([e["attempt"] for e in attempts], [1, 2])
        self.assertEqual(len([e for e in self.events if e["kind"] == "invocation" and e["event"] == "END"]), 1)
        self.assertNotIn("secret", json.dumps(self.events))

    def test_truncated_stream_with_text_is_failure(self):
        service = self.make_service(Response(events=[{"type": "response.output_text.delta", "delta": "partial"}]))
        with self.assertRaises(Exception) as caught:
            service.answer("question", "id", ConversationHistory())
        self.assertEqual(harness.error_details(caught.exception)["error_category"], "INCOMPLETE_STREAM")

    def test_explicit_stream_failure_is_not_success(self):
        service = self.make_service(Response(events=[{"type": "response.failed"}, "[DONE]"]))
        with self.assertRaises(Exception) as caught:
            service.answer("question", "id", ConversationHistory())
        self.assertEqual(harness.error_details(caught.exception)["error_category"], "STREAM_ERROR")

    def test_worker_continuation_is_another_invocation(self):
        approval = {"type": "mcp_approval_request", "id": "approval-1",
                    "name": "app-agent-mariner-branch-worker"}
        service = self.make_service(stream(approval), stream(message()))
        service.answer("question", "id", ConversationHistory())
        ends = [e for e in self.events if e["kind"] == "invocation" and e["event"] == "END"]
        self.assertEqual([e["invocation"] for e in ends], [1, 2])

    def test_citation_failure_preserves_invocation_success(self):
        class FailingResolver:
            def resolve_labels(self, labels, answer):
                raise RuntimeError("secret SQL text")
        service = self.make_service(stream(message("Answer\n\nSource: policy")), resolver=FailingResolver())
        with self.assertRaises(Exception):
            service.answer("question", "id", ConversationHistory())
        ends = [e for e in self.events if e["event"] == "END"]
        self.assertEqual(next(e for e in ends if e["kind"] == "invocation")["outcome"], "SUCCESS")
        self.assertEqual(ends[-1]["kind"], "citation")
        self.assertEqual(ends[-1]["outcome"], "FAILED")
        self.assertEqual(service.stage, "citation_resolution")
        self.assertNotIn("secret", json.dumps(self.events))

    def test_invalid_arguments(self):
        for argv in (["--concurrency", "0"], ["--duration-seconds", "nan"],
                     ["--warmup-seconds", "-1"], ["--min-reliability-percent", "101"],
                     ["--target-seconds", "5", "--deadline-seconds", "1"]):
            with self.subTest(argv=argv), patch("sys.stderr"), self.assertRaises(SystemExit):
                harness.parse_args(argv)

    def test_metrics_separate_success_failure_and_warmup(self):
        args = harness.parse_args([])
        rows = [dict(phase="measurement", outcome="SUCCESS_WITHIN_TARGET", elapsed_seconds=20, minute=0),
                dict(phase="measurement", outcome="FAILED", elapsed_seconds=1, minute=0,
                     error_category="HTTP_ERROR"),
                dict(phase="warmup", outcome="SUCCESS_WITHIN_TARGET", elapsed_seconds=1000, minute=0)]
        results = SimpleNamespace(rows=rows, invocations=[], attempts=[])
        phases = [{"phase": "measurement", "elapsed_with_drain_seconds": 20}]
        summary = harness.summarize(results, phases, args, "COMPLETE")
        self.assertEqual(summary["successful_latency_seconds"]["mean"], 20)
        self.assertEqual(summary["failed_latency_seconds"]["mean"], 1)
        self.assertEqual(summary["reliability_percent"], 50)
        self.assertFalse(summary["passed"])
        args.min_reliability_percent = 0
        self.assertFalse(harness.summarize(results, phases, args, "INTERRUPTED")["passed"])


class RunnerTests(unittest.TestCase):
    def test_main_sustained_load_and_warmup_outputs_offline(self):
        settings = SimpleNamespace(supervisor_mode="databricks", supervisor_endpoint="offline",
                                   request_timeout_seconds=60, databricks_warehouse_id=None)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(harness, "load_settings", return_value=settings), \
                 patch.object(harness, "worker_main", fake_worker), patch("builtins.print"):
                code = harness.main(["--output-dir", directory, "--question", "success",
                                     "--concurrency", "2", "--duration-seconds", ".12",
                                     "--warmup-seconds", ".05", "--target-seconds", "1",
                                     "--deadline-seconds", "2"])
            self.assertEqual(code, 0)
            run_directory = next(Path(directory).iterdir())
            summary = json.loads((run_directory / "summary.json").read_text())
            self.assertTrue(summary["passed"])
            self.assertGreater(summary["workflows_started"], 2)
            self.assertEqual([p["phase"] for p in summary["phases"]],
                             ["preflight", "warmup", "measurement"])
            for name in ("invocations", "attempts", "events", "workflows"):
                with (run_directory / (name + ".csv")).open() as handle:
                    rows = list(csv.DictReader(handle))
                self.assertTrue(rows)
                self.assertIn("measurement", {r["phase"] for r in rows})

    def test_interrupt_preserves_active_workflow(self):
        args = harness.parse_args(["--question", "hang"])
        context = mp.get_context("spawn")
        slots = []
        original = harness.record_event

        def interrupt_after_start(slot, event, results):
            original(slot, event, results)
            if event["kind"] == "attempt" and event["event"] == "START":
                raise KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                with patch.object(harness, "worker_main", fake_worker):
                    slots.append(harness.spawn_slot(context, None))
                    with patch.object(harness, "record_event", interrupt_after_start):
                        with self.assertRaises(KeyboardInterrupt):
                            harness.run_phase(slots, context, None, args, results, "OFFLINE",
                                              "measurement", 10, limit=1)
                self.assertEqual(results.rows[0]["outcome"], "INTERRUPTED")
                self.assertFalse(slots[0]["process"].is_alive())
                self.assertEqual(results.invocations[0]["outcome"], "INTERRUPTED")
            finally:
                for slot in slots:
                    harness.stop_slot(slot)
                results.close()

    def run_fake(self, question):
        args = harness.parse_args(["--question", question, "--target-seconds", "0.05",
                                   "--deadline-seconds", "0.15", "--startup-timeout-seconds", "10"])
        context = mp.get_context("spawn")
        slots = []
        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                with patch.object(harness, "worker_main", fake_worker):
                    slots.append(harness.spawn_slot(context, None))
                    phase = harness.run_phase(slots, context, None, args, results, "OFFLINE",
                                              "measurement", 10, limit=1)
                self.assertEqual(phase["started"], 1)
                self.assertEqual(len(results.rows), 1)
                with (Path(directory) / "workflows.csv").open() as handle:
                    self.assertEqual(len(list(csv.DictReader(handle))), 1)
                return results.rows[0], list(results.invocations), list(results.attempts)
            finally:
                for slot in slots:
                    harness.stop_slot(slot)
                results.close()

    def test_actual_process_deadline_stops_blocked_worker(self):
        start = time.monotonic()
        row, invocations, attempts = self.run_fake("hang")
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(row["outcome"], "DEADLINE_EXCEEDED")
        self.assertEqual(invocations[0]["outcome"], "DEADLINE_EXCEEDED")
        self.assertEqual(attempts[0]["outcome"], "DEADLINE_EXCEEDED")

    def test_process_result_has_no_unclosed_invocation(self):
        row, invocations, attempts = self.run_fake("success")
        self.assertIn(row["outcome"], harness.SUCCESS)
        self.assertEqual(len(invocations), 1)
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
