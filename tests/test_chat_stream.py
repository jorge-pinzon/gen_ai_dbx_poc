import json
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit

from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.errors import CitationResolutionError, SupervisorInvocationError
from mariner_genai_dbx.models import AgentAnswer, PendingAgentAnswer, Source
from mariner_genai_dbx.web import create_app, LOCAL_USER_ID
from types import SimpleNamespace


def event(chunk):
    lines = chunk.decode().strip().splitlines()
    return lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))


class ProgressiveService:
    def __init__(self):
        self.text = "Managers document quarterly coaching."
        self.resolve_calls = 0
        self.prepare_error = None
        self.resolve_error = None

    def prepare_answer(self, message, session_id, history):
        if self.prepare_error:
            raise self.prepare_error
        return PendingAgentAnswer(answer=self.text, source_labels=("Policy",))

    def resolve_answer(self, pending):
        self.resolve_calls += 1
        if self.resolve_error:
            raise self.resolve_error
        return AgentAnswer(answer=pending.answer, sources=(Source(number=1, label="Policy", page=2),))

    def answer(self, *args):
        return self.resolve_answer(self.prepare_answer(*args))


class ChatStreamTests(unittest.TestCase):
    def setUp(self):
        self.service = ProgressiveService()
        self.app = create_app(Settings(app_env="test"), supervisor_service=self.service)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_page_loads_stream_helper_before_chat_and_serves_both_assets(self):
        class Scripts(HTMLParser):
            def __init__(self):
                super().__init__()
                self.scripts = []

            def handle_starttag(self, tag, attrs):
                if tag == "script":
                    self.scripts.append(dict(attrs))

        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        parser = Scripts()
        parser.feed(page.get_data(as_text=True))
        scripts = parser.scripts
        paths = [urlsplit(script.get("src", "")).path for script in scripts]
        helper = paths.index("/static/chat-stream.js")
        chat = paths.index("/static/chat.js")
        self.assertLess(helper, chat)
        for index in (helper, chat):
            self.assertIn("defer", scripts[index])
            self.assertNotIn("async", scripts[index])
            with self.client.get(scripts[index]["src"]) as asset:
                self.assertEqual(asset.status_code, 200)
                self.assertIn("javascript", asset.content_type)

    def test_checked_answer_is_yielded_before_citation_lookup_and_persistence(self):
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"}, buffered=False)
        self.addCleanup(response.close)
        chunks = iter(response.response)
        self.assertEqual(event(next(chunks))[0], "status")
        kind, draft = event(next(chunks))
        self.assertEqual(kind, "answer")
        self.assertEqual(draft["citationStatus"], "pending")
        self.assertEqual(self.service.resolve_calls, 0)
        persistence = self.app.extensions["conversation_persistence"]
        self.assertEqual(persistence.load_history(LOCAL_USER_ID, draft["conversationId"]).turns, ())
        kind, sources = event(next(chunks))
        self.assertEqual(kind, "sources")
        self.assertEqual(sources["sources"][0]["page"], 2)
        self.assertEqual(self.service.resolve_calls, 1)
        self.assertEqual(event(next(chunks))[0], "done")
        self.assertEqual(len(persistence.load_history(LOCAL_USER_ID, draft["conversationId"]).turns), 1)
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")

    def test_citation_failure_marks_draft_unverified_and_does_not_save_it(self):
        self.service.resolve_error = CitationResolutionError("Private SQL detail")
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"})
        self.addCleanup(response.close)
        frames = [event(chunk) for chunk in response.response]
        self.assertEqual([kind for kind, _ in frames], ["status", "answer", "error"])
        self.assertEqual(frames[-1][1]["code"], "CITATIONS_UNAVAILABLE")
        self.assertNotIn("Private SQL detail", str(frames))
        conversation_id = frames[1][1]["conversationId"]
        self.assertEqual(self.app.extensions["conversation_persistence"].load_history(
            LOCAL_USER_ID, conversation_id).turns, ())

    def test_output_is_masked_before_it_is_streamed(self):
        self.service.text = "The employee SSN is 123-45-6789."
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"})
        self.addCleanup(response.close)
        self.assertNotIn(b"123-45-6789", response.data)

    def test_blocked_output_skips_citation_lookup(self):
        self.service.text = "You are terminated effective immediately."
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"})
        self.addCleanup(response.close)
        frames = [event(chunk) for chunk in response.response]
        self.assertNotIn("terminated", frames[1][1]["answer"].lower())
        self.assertEqual(frames[1][1]["citationStatus"], "none")
        self.assertEqual(self.service.resolve_calls, 0)
        self.assertEqual(frames[2][1]["sources"], [])

    def test_generation_failure_never_emits_an_answer(self):
        self.service.prepare_error = SupervisorInvocationError("Private upstream detail")
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"})
        self.addCleanup(response.close)
        frames = [event(chunk) for chunk in response.response]
        self.assertEqual([kind for kind, _ in frames], ["status", "error"])
        self.assertNotIn("Private upstream detail", str(frames))

    def test_disconnected_draft_does_not_resolve_or_persist(self):
        response = self.client.post("/api/v1/chat/stream", json={"message": "Explain coaching"}, buffered=False)
        chunks = iter(response.response)
        next(chunks)
        _, draft = event(next(chunks))
        response.close()
        self.assertEqual(self.service.resolve_calls, 0)
        self.assertEqual(self.app.extensions["conversation_persistence"].load_history(
            LOCAL_USER_ID, draft["conversationId"]).turns, ())

    def test_stream_route_enforces_input_validation_and_identity(self):
        response = self.client.post("/api/v1/chat/stream", json={"message": ""})
        self.assertEqual(response.status_code, 400)
        app = create_app(Settings(app_env="test"), supervisor_service=self.service,
                         identity_provider=lambda: None)
        self.assertEqual(app.test_client().post("/api/v1/chat/stream", json={"message": "Coaching"}).status_code, 401)

    def test_legacy_json_endpoint_still_returns_complete_verified_answer(self):
        response = self.client.post("/api/v1/chat", json={"message": "Explain coaching"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["answer"], self.service.text)
        self.assertEqual(len(response.json["sources"]), 1)
        self.assertEqual(self.service.resolve_calls, 1)

    def test_closing_after_done_does_not_record_a_cancelled_turn(self):
        events = []
        app = create_app(Settings(app_env="test"), supervisor_service=self.service,
                         analytics_service=SimpleNamespace(record=events.append))
        response = app.test_client().post("/api/v1/chat/stream", json={"message": "Coaching"}, buffered=False)
        chunks = iter(response.response)
        for _ in range(4):
            kind, _data = event(next(chunks))
        self.assertEqual(kind, "done")
        response.close()
        self.assertEqual([entry.status for entry in events], ["success"])


if __name__ == "__main__":
    unittest.main()
