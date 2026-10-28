import json
import unittest
import threading
from datetime import datetime, timezone

from mariner_genai_dbx.analytics import (
    BackgroundAnalyticsService, ChatLogEvent, DatabricksAnalyticsService,
)
from mariner_genai_dbx.models import Source, TokenUsage


class FakeStatementExecution:
    def __init__(self):
        self.calls = []

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)


class FakeWorkspaceClient:
    def __init__(self):
        self.statement_execution = FakeStatementExecution()


class AnalyticsTests(unittest.TestCase):
    def test_background_logging_does_not_wait_for_sql_and_bounds_backlog(self):
        entered = threading.Event()
        release = threading.Event()
        delivered = []

        class BlockingService:
            def record(self, event):
                entered.set()
                release.wait(3)
                delivered.append(event)

        service = BackgroundAnalyticsService(
            BlockingService(), max_pending=1, flush_seconds=0
        )
        try:
            service.record("first")
            self.assertTrue(entered.wait(1))
            service.record("second")
            with self.assertLogs("mariner_genai_dbx.analytics", level="WARNING"):
                service.record("dropped")
            self.assertEqual(delivered, [])
            self.assertEqual(service._queue.qsize(), 1)
        finally:
            release.set()
        service._queue.join()
        self.assertEqual(delivered, ["first", "second"])

    def test_background_logging_continues_after_failure(self):
        calls = []

        class FailingService:
            def record(self, event):
                calls.append(event)
                if event == "fail":
                    raise RuntimeError("SQL unavailable")

        service = BackgroundAnalyticsService(FailingService(), flush_seconds=0)
        with self.assertLogs("mariner_genai_dbx.analytics", level="WARNING"):
            service.record("fail")
            service.record("success")
            service._queue.join()
        self.assertEqual(calls, ["fail", "success"])

    def test_background_logging_writes_queued_events_in_one_batch(self):
        batches = []
        release = threading.Event()

        class BatchingService:
            def record_many(self, events):
                release.wait(3)
                batches.append(list(events))

        service = BackgroundAnalyticsService(
            BatchingService(), batch_size=3, flush_seconds=0.5
        )
        for event in ("a", "b", "c", "d"):
            service.record(event)
        release.set()
        service._queue.join()
        self.assertEqual(batches, [["a", "b", "c"], ["d"]])

    def test_failed_batch_is_dropped_without_stopping_delivery(self):
        batches = []

        class FailingBatchService:
            def record_many(self, events):
                batches.append(list(events))
                if events == ["fail"]:
                    raise RuntimeError("SQL unavailable")

        service = BackgroundAnalyticsService(FailingBatchService(), flush_seconds=0)
        with self.assertLogs("mariner_genai_dbx.analytics", level="WARNING"):
            service.record("fail")
            service._queue.join()
        service.record("next")
        service._queue.join()
        self.assertEqual(batches, [["fail"], ["next"]])

    def test_inserts_parameterized_safe_event(self):
        client = FakeWorkspaceClient()
        service = DatabricksAnalyticsService(
            workspace_client=client,
            warehouse_id="warehouse",
            table_name="workspace.default.flask_app_logs",
        )
        service.record(
            ChatLogEvent(
                user_id="user",
                session_id="session",
                app_version="1.2.3",
                latency_ms=123,
                event_id="event",
                event_timestamp=datetime(2026, 9, 17, tzinfo=timezone.utc),
                question="Question?",
                answer="Answer.",
                sources=(
                    Source(
                        number=1,
                        label="Handbook",
                        domain="Employee Handbook",
                        location="/Volumes/private/Handbook.pdf",
                        url="https://temporary.example/source",
                        page=45,
                    ),
                ),
                status="success",
                agents_used=("app-agent-mariner-handbook-worker",),
                usage=TokenUsage(
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                ),
                inference_ms=900,
                citations_ms=40,
            )
        )

        call = client.statement_execution.calls[0]
        self.assertEqual(call["warehouse_id"], "warehouse")
        self.assertIn("workspace`.`default`.`flask_app_logs", call["statement"])
        self.assertNotIn("Question?", call["statement"])
        self.assertEqual(len(call["parameters"]), 1)
        [row] = _event_rows(call)
        self.assertEqual(row["question"], "Question?")
        sources = json.loads(row["sources_json"])
        self.assertEqual(sources[0]["page"], 45)
        self.assertNotIn("location", sources[0])
        self.assertNotIn("url", sources[0])
        self.assertEqual(row["source_count"], 1)
        self.assertEqual(row["input_tokens"], 100)
        self.assertEqual(row["output_tokens"], 50)
        self.assertEqual(row["total_tokens"], 150)
        self.assertEqual(row["inference_ms"], 900)
        self.assertEqual(row["citations_ms"], 40)
        self.assertEqual(
            json.loads(row["agents_used_json"]),
            ["app-agent-mariner-handbook-worker"],
        )

    def test_failed_event_writes_null_token_counts(self):
        client = FakeWorkspaceClient()
        service = DatabricksAnalyticsService(
            workspace_client=client,
            warehouse_id="warehouse",
            table_name="workspace.default.flask_app_logs",
        )

        service.record(
            ChatLogEvent(
                user_id="user",
                session_id="session",
                app_version="1.2.3",
                latency_ms=123,
                event_id="event",
                event_timestamp=datetime(2026, 9, 18, tzinfo=timezone.utc),
                question="Question?",
                answer="",
                sources=(),
                status="error",
                error_message="supervisor_unavailable",
            )
        )

        [row] = _event_rows(client.statement_execution.calls[0])
        for name in ("input_tokens", "output_tokens", "total_tokens",
                     "inference_ms", "citations_ms"):
            self.assertIsNone(row[name])
        self.assertEqual(row["error_message"], "supervisor_unavailable")
        self.assertEqual(json.loads(row["agents_used_json"]), [])

    def test_batch_is_one_statement_with_one_parameter(self):
        client = FakeWorkspaceClient()
        service = DatabricksAnalyticsService(
            workspace_client=client,
            warehouse_id="warehouse",
            table_name="workspace.default.flask_app_logs",
        )
        events = [
            ChatLogEvent(
                user_id="user", session_id="session", app_version="1.2.3",
                latency_ms=10 + index, event_id=f"event-{index}",
                event_timestamp=datetime(2026, 10, 23, tzinfo=timezone.utc),
                question=f"Question {index}?", answer="Answer.", sources=(),
                status="success",
            )
            for index in range(3)
        ]
        service.record_many(events)
        self.assertEqual(len(client.statement_execution.calls), 1)
        rows = _event_rows(client.statement_execution.calls[0])
        self.assertEqual([row["event_id"] for row in rows],
                         ["event-0", "event-1", "event-2"])

    def test_stage_timings_are_written_only_when_enabled(self):
        def event(stage_ms):
            return ChatLogEvent(user_id="u", session_id="s", app_version="1", latency_ms=1, event_id="e",
                                event_timestamp=datetime(2026, 10, 26, tzinfo=timezone.utc), question="Q",
                                answer="A", sources=(), status="success", stage_ms=stage_ms)
        for enabled in (False, True):
            client = FakeWorkspaceClient()
            DatabricksAnalyticsService(workspace_client=client, warehouse_id="w", table_name="workspace.default.flask_app_logs",
                                       stage_timings=enabled).record(event({"tool": 4400, "result": 26400}))
            call = client.statement_execution.calls[0]
            self.assertEqual("citations_ms, stage_timings_json, ingested_at" in call["statement"], enabled)
            row = json.loads(call["parameters"][0].value)[0]
            self.assertEqual(row["stage_timings_json"], '{"tool":4400,"result":26400}')

    def test_empty_batch_sends_nothing(self):
        client = FakeWorkspaceClient()
        DatabricksAnalyticsService(
            workspace_client=client, warehouse_id="warehouse",
            table_name="workspace.default.flask_app_logs",
        ).record_many([])
        self.assertEqual(client.statement_execution.calls, [])


def _event_rows(call):
    [parameter] = call["parameters"]
    name = parameter.get("name") if isinstance(parameter, dict) else parameter.name
    value = parameter.get("value") if isinstance(parameter, dict) else parameter.value
    assert name == "events_json"
    return json.loads(value)


if __name__ == "__main__":
    unittest.main()
