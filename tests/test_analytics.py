import json
import unittest
from datetime import datetime, timezone

from mariner_genai_dbx.analytics import ChatLogEvent, DatabricksAnalyticsService
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
            )
        )

        call = client.statement_execution.calls[0]
        self.assertEqual(call["warehouse_id"], "warehouse")
        self.assertIn("workspace`.`default`.`flask_app_logs", call["statement"])
        self.assertNotIn("Question?", call["statement"])
        values = {
            (item.get("name") if isinstance(item, dict) else item.name):
            (item.get("value") if isinstance(item, dict) else item.value)
            for item in call["parameters"]
        }
        sources = json.loads(values["sources_json"])
        self.assertEqual(sources[0]["page"], 45)
        self.assertNotIn("location", sources[0])
        self.assertNotIn("url", sources[0])
        self.assertEqual(values["input_tokens"], "100")
        self.assertEqual(values["output_tokens"], "50")
        self.assertEqual(values["total_tokens"], "150")
        self.assertEqual(
            json.loads(values["agents_used_json"]),
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

        parameters = client.statement_execution.calls[0]["parameters"]
        values = {
            (item.get("name") if isinstance(item, dict) else item.name):
            (item.get("value") if isinstance(item, dict) else item.value)
            for item in parameters
        }
        self.assertNotIn("input_tokens", values)
        self.assertNotIn("output_tokens", values)
        self.assertNotIn("total_tokens", values)
        self.assertEqual(json.loads(values["agents_used_json"]), [])
        statement = client.statement_execution.calls[0]["statement"]
        self.assertIn("NULL, NULL, NULL", statement)


if __name__ == "__main__":
    unittest.main()
