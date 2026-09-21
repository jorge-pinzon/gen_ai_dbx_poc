import json
import logging
import sys
import unittest

from mariner_genai_dbx.logging_config import JsonFormatter, sanitize_log_text


class StructuredLoggingTests(unittest.TestCase):
    def test_formatter_emits_allow_listed_request_metadata(self):
        record = logging.LogRecord(
            "mariner_genai_dbx.web",
            logging.INFO,
            __file__,
            1,
            "HTTP request completed",
            (),
            None,
        )
        record.event = "http_request_completed"
        record.request_id = "request-1"
        record.route = "/api/v1/chat"
        record.status = 200
        record.duration_ms = 12
        record.question = "must never be serialized"

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["request_id"], "request-1")
        self.assertEqual(payload["route"], "/api/v1/chat")
        self.assertEqual(payload["status"], 200)
        self.assertNotIn("question", payload)

    def test_exception_trace_excludes_exception_message_and_secrets(self):
        try:
            raise RuntimeError("question=private password=hunter2")
        except RuntimeError:
            record = logging.LogRecord(
                "mariner_genai_dbx.web",
                logging.ERROR,
                __file__,
                1,
                "Unhandled application exception",
                (),
                sys.exc_info(),
            )

        payload = json.loads(JsonFormatter().format(record))
        rendered = json.dumps(payload)

        self.assertEqual(payload["exception_type"], "RuntimeError")
        self.assertTrue(payload["stack_trace"])
        self.assertNotIn("private", rendered)
        self.assertNotIn("hunter2", rendered)

    def test_controlled_messages_redact_sensitive_values(self):
        sanitized = sanitize_log_text(
            "Authorization: Bearer secret-token cookie=session-cookie question=private"
        )

        self.assertNotIn("secret-token", sanitized)
        self.assertNotIn("session-cookie", sanitized)
        self.assertNotIn("private", sanitized)


if __name__ == "__main__":
    unittest.main()
