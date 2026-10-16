"""Offline HTTP-contract and runner tests; no live Databricks or app requests."""
import io
import json
import multiprocessing as mp
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests
import stress_Test.Scripts.stress_test_FLASK_2 as harness


def job():
    return {"workflow_id": "STRESS-OFFLINE-measurement-000001", "phase": "measurement",
            "started_monotonic": time.monotonic(), "started_at": harness.utc_now(),
            "offset_seconds": 0, "target_seconds": 1, "deadline_seconds": 2}


class Response:
    def __init__(self, status=200, body=b"", mime="application/json", request_id="request-test"):
        self.status_code, self.body = status, body
        self.headers = {"Content-Type": mime, "X-Request-ID": request_id}
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Session:
    def __init__(self, response=None, transform=None, error=None):
        self.response, self.transform, self.error = response, transform, error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        if self.response is not None:
            return self.response
        payload = {"answer": "Policy answer", "conversationId": kwargs["json"]["conversationId"],
                   "sources": [], "requestId": "request-test"}
        if self.transform:
            self.transform(payload)
        return Response(body=json.dumps(payload).encode())


def fake_worker(connection, args):
    connection.send({"kind": "ready"})
    while True:
        request = connection.recv()
        common = {"kind": "attempt", "workflow_id": request["workflow_id"],
                  "phase": request["phase"], "stage": "http_request", "timestamp": harness.utc_now()}
        connection.send({**common, "event": "START"})
        connection.send({**common, "event": "HEADERS", "http_status": 200, "request_id": "offline"})
        if args.question == "hang":
            time.sleep(30)
        row = {**common, "event": "END", "outcome": "SUCCESS_WITHIN_TARGET",
               "elapsed_seconds": .001, "http_status": 200, "request_id": "offline"}
        connection.send(row)
        connection.send({**row, "kind": "workflow"})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.args = harness.parse_args(["--target-seconds", "1", "--deadline-seconds", "2"])
        self.events = []

    def run_request(self, session, provider=None):
        return harness.execute_request(session, provider, self.args, job(), self.events.append)

    def test_default_local_url(self):
        self.assertEqual(self.args.base_url, "http://127.0.0.1:5000")

    def test_valid_chat_preserves_route_and_correlation(self):
        session = Session()
        row = self.run_request(session)
        self.assertEqual(row["outcome"], "SUCCESS_WITHIN_TARGET")
        self.assertEqual(row["request_id"], row["header_request_id"])
        url, kwargs = session.calls[0]
        self.assertEqual(url, "http://127.0.0.1:5000/api/v1/chat")
        self.assertTrue(kwargs["json"]["message"].startswith("/policy [STRESS_TEST_ID="))
        self.assertFalse(kwargs["allow_redirects"])
        self.assertNotIn("answer", row)

    def test_deployed_url_preserves_path_prefix(self):
        self.args.base_url = "https://example.test/apps/chat"
        session = Session()
        self.run_request(session)
        self.assertEqual(session.calls[0][0], "https://example.test/apps/chat/api/v1/chat")

    def test_html_login_page_is_failure(self):
        response = Response(body=b"<html>Login</html>", mime="text/html")
        row = self.run_request(Session(response))
        self.assertEqual(row["error_category"], "INVALID_JSON_RESPONSE")
        self.assertTrue(response.closed)

    def test_malformed_json_is_failure(self):
        row = self.run_request(Session(Response(body=b"{broken")))
        self.assertEqual(row["error_category"], "INVALID_JSON_RESPONSE")

    def test_redirect_is_not_followed(self):
        row = self.run_request(Session(Response(status=302)))
        self.assertEqual(row["error_category"], "UNEXPECTED_REDIRECT")

    def test_bad_chat_contract(self):
        changes = [lambda p: p.update(answer=""), lambda p: p.update(conversationId="different"),
                   lambda p: p.update(sources="bad"), lambda p: p.pop("requestId"),
                   lambda p: p.update(error={"code": "ERROR"})]
        for change in changes:
            with self.subTest(change=change):
                row = self.run_request(Session(transform=change))
                self.assertEqual(row["error_category"], "INVALID_CHAT_RESPONSE")

    def test_proxy_request_id_mismatch_is_observed(self):
        row = self.run_request(Session(transform=lambda p: p.update(requestId="different")))
        self.assertEqual(row["outcome"], "SUCCESS_WITHIN_TARGET")
        self.assertFalse(row["request_id_matches_header"])

    def test_http_error_has_app_code_without_body(self):
        response = Response(status=502, body=json.dumps({"error": {
            "code": "CITATIONS_UNAVAILABLE", "message": "secret response text"},
            "requestId": "request-test"}).encode())
        row = self.run_request(Session(response))
        self.assertEqual(row["app_error_code"], "CITATIONS_UNAVAILABLE")
        self.assertEqual(row["http_status"], 502)
        self.assertNotIn("secret", json.dumps(self.events))

    def test_http_auth_and_rate_limit_failures(self):
        for status, category in ((401, "AUTHENTICATION"), (403, "AUTHENTICATION"), (429, "RATE_LIMITED")):
            with self.subTest(status=status):
                self.assertEqual(self.run_request(Session(Response(status=status)))["error_category"], category)

    def test_network_failures(self):
        for error, category in ((requests.exceptions.SSLError("secret"), "TLS_ERROR"),
                                (requests.exceptions.ReadTimeout("secret"), "NETWORK_TIMEOUT"),
                                (requests.exceptions.ConnectionError("secret"), "CONNECTION_ERROR")):
            with self.subTest(category=category):
                row = self.run_request(Session(error=error))
                self.assertEqual(row["error_category"], category)
                self.assertNotIn("secret", json.dumps(row))

    def test_credential_provider_failure_before_http(self):
        def provider():
            raise RuntimeError("secret token text")
        session = Session()
        row = self.run_request(session, provider)
        self.assertEqual(row["stage"], "authentication")
        self.assertEqual(len(session.calls), 0)
        self.assertNotIn("secret", json.dumps(row))

    def test_response_size_limit(self):
        self.args.max_response_bytes = 4
        self.assertEqual(self.run_request(Session())["error_category"], "RESPONSE_TOO_LARGE")

    def test_declared_live_backend_rejects_known_mock(self):
        self.args.backend_mode = "databricks"
        row = self.run_request(Session(transform=lambda p: p.update(answer="The Flask shell is running in mock mode.")))
        self.assertEqual(row["error_category"], "MOCK_BACKEND_RESPONSE")

    def test_bearer_session_and_missing_credentials(self):
        with patch.dict(os.environ, {"FLASK_TEST_BEARER_TOKEN": "secret-token"}):
            args = harness.parse_args(["--auth", "bearer"])
            session, provider = harness.setup_session(args)
            try:
                self.assertEqual(session.headers["Authorization"], "Bearer secret-token")
                self.assertIsNone(provider)
            finally:
                session.close()
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr"), self.assertRaises(SystemExit):
            harness.parse_args(["--auth", "bearer"])

    def test_password_login_cookies_and_no_redirect_following(self):
        response = Response(status=302)
        response.headers["Location"] = "/"
        session = SimpleNamespace(headers={}, cookies={"session": "cookie"}, verify=True,
                                  mount=lambda *args: None, close=lambda: None)
        calls = []
        session.post = lambda *a, **kw: (calls.append((a, kw)) or response)
        with patch.dict(os.environ, {"FLASK_TEST_USERNAME": "employee", "FLASK_TEST_PASSWORD": "secret"}):
            args = harness.parse_args(["--auth", "password"])
            with patch.object(harness.requests, "Session", return_value=session):
                result, _ = harness.setup_session(args)
        self.assertFalse(calls[0][1]["allow_redirects"])
        self.assertEqual(calls[0][0][0], "http://127.0.0.1:5000/login")
        self.assertEqual(result.cookies["session"], "cookie")

    def test_databricks_sdk_authentication_provider(self):
        provider = lambda: {"Authorization": "Bearer secret-sdk-token"}
        with patch("databricks.sdk.WorkspaceClient") as client:
            client.return_value.config.authenticate = provider
            args = harness.parse_args(["--auth", "databricks", "--databricks-profile", "test-profile"])
            session, actual_provider = harness.setup_session(args)
            try:
                client.assert_called_once_with(profile="test-profile")
                self.assertIs(actual_provider, provider)
                fake = Session()
                row = self.run_request(fake, actual_provider)
                self.assertEqual(fake.calls[0][1]["headers"]["Authorization"], "Bearer secret-sdk-token")
                self.assertNotIn("secret", json.dumps(row))
            finally:
                session.close()

    def test_failed_login_closes_session(self):
        response = Response(status=401)
        calls = []
        session = SimpleNamespace(headers={}, cookies={}, verify=True,
                                  mount=lambda *args: None, close=lambda: calls.append("closed"),
                                  post=lambda *args, **kwargs: response)
        with patch.dict(os.environ, {"FLASK_TEST_USERNAME": "employee", "FLASK_TEST_PASSWORD": "secret"}):
            args = harness.parse_args(["--auth", "password"])
            with patch.object(harness.requests, "Session", return_value=session):
                with self.assertRaises(harness.TestFailure) as caught:
                    harness.setup_session(args)
        self.assertEqual(caught.exception.category, "LOGIN_FAILED")
        self.assertEqual(calls, ["closed"])

    def test_bad_urls_and_settings(self):
        invalid = [["--base-url", "https://user:secret@example.test"],
                   ["--base-url", "https://example.test/api/v1/chat"],
                   ["--base-url", "ftp://example.test"], ["--base-url", "http://example.test:bad"],
                   ["--concurrency", "0"], ["--warmup-seconds", "nan"],
                   ["--target-seconds", "4", "--deadline-seconds", "2"],
                   ["--min-reliability-percent", "101"]]
        for argv in invalid:
            with self.subTest(argv=argv), patch("sys.stderr"), self.assertRaises(SystemExit):
                harness.parse_args(argv)

    def test_real_flask_route_in_process(self):
        # Exercise the real route without binding a port or calling Databricks.
        from mariner_genai_dbx.config import Settings
        from mariner_genai_dbx.models import AgentAnswer
        from mariner_genai_dbx.web import create_app
        seen = []
        class Supervisor:
            def answer(self, message, session_id, history):
                seen.append(message)
                return AgentAnswer(answer="Keep records according to approved policy.")
        app = create_app(Settings(app_env="test"), supervisor_service=Supervisor())
        client = app.test_client()
        class FlaskAdapter(requests.adapters.BaseAdapter):
            def send(self, request, **kwargs):
                result = client.open(request.path_url, method=request.method,
                                     headers=dict(request.headers), data=request.body)
                response = requests.Response()
                response.status_code = result.status_code
                response.headers.update(result.headers)
                response.raw = io.BytesIO(result.data)
                response.request = request
                response.url = request.url
                return response
            def close(self):
                pass
        session = requests.Session()
        session.mount("http://", FlaskAdapter())
        try:
            row = self.run_request(session)
        finally:
            session.close()
        self.assertEqual(row["outcome"], "SUCCESS_WITHIN_TARGET")
        self.assertEqual(row["request_id"], row["header_request_id"])
        self.assertIn("Mandatory application routing directive", seen[0])
        self.assertIn("[STRESS_TEST_ID=", seen[0])


class RunnerTests(unittest.TestCase):
    def test_late_result_classification(self):
        request = job()
        request["started_monotonic"] -= 1.2
        slot = {"job": request, "last": {}, "attempt_done": False}
        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                harness.finalize(slot, {"outcome": "SUCCESS_WITHIN_TARGET"}, results)
                self.assertEqual(results.rows[0]["outcome"], "SUCCESS_LATE")
            finally:
                results.close()

    def test_sustained_run_and_results(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(harness, "worker_main", fake_worker), patch("builtins.print"):
                code = harness.main(["--output-dir", directory, "--concurrency", "2",
                                     "--duration-seconds", ".1", "--warmup-seconds", ".05",
                                     "--target-seconds", "1", "--deadline-seconds", "2"])
            self.assertEqual(code, 0)
            folder = next(Path(directory).iterdir())
            summary = json.loads((folder / "summary.json").read_text())
            self.assertTrue(summary["passed"])
            self.assertGreater(summary["workflows_started"], 2)
            self.assertEqual([p["phase"] for p in summary["phases"]], ["preflight", "warmup", "measurement"])
            for name in ("workflows.csv", "attempts.csv", "events.csv", "run.json"):
                self.assertTrue((folder / name).exists())
            self.assertNotIn("invocation_outcomes", summary)

    def test_blocked_worker_deadline(self):
        args = harness.parse_args(["--question", "hang", "--target-seconds", ".05",
                                   "--deadline-seconds", ".15", "--startup-timeout-seconds", "10"])
        context, slots = mp.get_context("spawn"), []
        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                with patch.object(harness, "worker_main", fake_worker):
                    slots.append(harness.spawn_slot(context, args))
                    harness.run_phase(slots, context, args, results, "OFFLINE", "measurement", 10, limit=1)
                self.assertEqual(results.rows[0]["outcome"], "DEADLINE_EXCEEDED")
                self.assertEqual(results.rows[0]["http_status"], 200)
                self.assertEqual(results.attempts[0]["outcome"], "DEADLINE_EXCEEDED")
            finally:
                for slot in slots:
                    harness.stop_slot(slot)
                results.close()

    def test_metrics_and_interrupted_verdict(self):
        args = harness.parse_args([])
        results = SimpleNamespace(rows=[
            dict(phase="measurement", outcome="SUCCESS_WITHIN_TARGET", elapsed_seconds=20, minute=0),
            dict(phase="measurement", outcome="SUCCESS_LATE", elapsed_seconds=70, minute=0),
            dict(phase="measurement", outcome="FAILED", elapsed_seconds=1, minute=0),
            dict(phase="warmup", outcome="FAILED", elapsed_seconds=999, minute=0)], attempts=[])
        phases = [dict(phase="measurement", elapsed_with_drain_seconds=100)]
        summary = harness.summarize(results, phases, args, "COMPLETE")
        self.assertAlmostEqual(summary["reliability_percent"], 100 / 3)
        self.assertEqual(summary["successful_latency_seconds"]["mean"], 45)
        self.assertEqual(summary["failed_latency_seconds"]["mean"], 1)
        self.assertEqual(summary["successful_workflows_per_second_including_drain"], .02)
        args.min_reliability_percent = 0
        self.assertFalse(harness.summarize(results, phases, args, "INTERRUPTED")["passed"])

    def test_interruption_preserves_partial_results(self):
        args = harness.parse_args(["--question", "hang"])
        context, slots = mp.get_context("spawn"), []
        original = harness.Results.write
        def interrupt(results, name, row):
            original(results, name, row)
            if row.get("event") == "HEADERS":
                raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as directory:
            results = harness.Results(Path(directory))
            try:
                with patch.object(harness, "worker_main", fake_worker):
                    slots.append(harness.spawn_slot(context, args))
                    with patch.object(harness.Results, "write", interrupt), self.assertRaises(KeyboardInterrupt):
                        harness.run_phase(slots, context, args, results, "OFFLINE", "measurement", 10, limit=1)
                self.assertEqual(results.rows[0]["outcome"], "INTERRUPTED")
                self.assertFalse(slots[0]["process"].is_alive())
            finally:
                for slot in slots:
                    harness.stop_slot(slot)
                results.close()


if __name__ == '__main__':
    unittest.main()
