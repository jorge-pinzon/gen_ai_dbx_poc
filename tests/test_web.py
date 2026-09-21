import unittest
import io
from uuid import UUID

from werkzeug.security import generate_password_hash

from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.errors import CitationResolutionError, SupervisorInvocationError
from mariner_genai_dbx.models import AgentAnswer, ReadinessResult, Source
from mariner_genai_dbx.web import ReadinessCache, create_app


def test_settings(max_message_characters=4000):
    return Settings(app_env="test", max_message_characters=max_message_characters)


def password_settings():
    return Settings(
        app_env="test",
        auth_mode="password",
        login_username="prototype-user",
        login_password_hash=generate_password_hash("prototype-password"),
        session_secret_key="test-session-secret-key-with-32-characters",
    )


class FakeSupervisor:
    def __init__(self):
        self.answer_calls = []
        self.answer_error = None
        self.readiness_calls = 0

    def answer(self, message, session_id, history):
        self.answer_calls.append((message, session_id, history))
        if self.answer_error:
            raise self.answer_error
        return AgentAnswer(
            answer="The employee support answer.",
            agents_used=("app-agent-mariner-benefits-worker",),
            sources=(
                Source(
                    number=1,
                    label="policy.pdf",
                    location="/Volumes/main/hr/handbook/policy.pdf",
                    url="https://documents.example.test/policy.pdf",
                    page=3,
                ),
            ),
        )

    def check_readiness(self):
        self.readiness_calls += 1
        return ReadinessResult(ready=True)


class FakeAnalytics:
    def __init__(self):
        self.events = []
        self.error = None

    def record(self, event):
        if self.error:
            raise self.error
        self.events.append(event)


class FakeSourceCatalog:
    def catalogs(self):
        return [{"id": "handbook", "label": "Employee handbook"}]

    def list_children(self, catalog_id, path, cursor):
        return {
            "catalogId": catalog_id,
            "path": path,
            "entries": [
                {
                    "type": "document",
                    "name": "policy.pdf",
                    "path": "policy.pdf",
                    "embeddable": True,
                }
            ],
        }

    def open_document(self, catalog_id, path):
        return {
            "label": path,
            "url": "https://documents.example.test/policy.pdf",
            "embeddable": True,
        }

    def search(self, query):
        return {
            "query": query,
            "results": [
                {
                    "catalogId": "handbook",
                    "catalogLabel": "Employee handbook",
                    "name": "policy.pdf",
                    "path": "policy.pdf",
                    "embeddable": True,
                }
            ],
            "truncated": False,
        }

    def reference_for_location(self, location):
        if location == "/Volumes/main/hr/handbook/policy.pdf":
            return {"catalogId": "handbook", "path": "policy.pdf"}
        return None


class SignedSourceCatalog(FakeSourceCatalog):
    def open_document(self, catalog_id, path):
        return {
            "catalogId": catalog_id,
            "path": path,
            "label": path,
            "embeddable": True,
        }

    def download_document(self, catalog_id, path):
        return {
            "contents": io.BytesIO(b"%PDF-test"),
            "content_length": 9,
            "last_modified": None,
        }


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = FakeSupervisor()
        self.app = create_app(test_settings(), supervisor_service=self.supervisor)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_page_health_and_readiness(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        UUID(page.headers["X-Request-ID"])
        self.assertIn(b"MultiAgentic Employee Support", page.data)
        self.assertEqual(self.client.get("/health").get_json(), {"status": "ok"})
        self.assertEqual(self.client.get("/ready").status_code, 200)

    def test_password_mode_requires_login_for_page_and_api(self):
        app = create_app(password_settings(), supervisor_service=self.supervisor)
        client = app.test_client()

        page = client.get("/")
        api = client.post("/api/v1/chat", json={"message": "Question"})

        self.assertEqual(page.status_code, 302)
        self.assertEqual(page.headers["Location"], "/login")
        self.assertEqual(api.status_code, 401)
        self.assertEqual(api.get_json()["error"]["code"], "AUTHENTICATION_REQUIRED")
        self.assertEqual(self.supervisor.answer_calls, [])

    def test_password_login_rejects_invalid_credentials(self):
        app = create_app(password_settings(), supervisor_service=self.supervisor)
        client = app.test_client()

        response = client.post(
            "/login",
            data={"username": "prototype-user", "password": "incorrect"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn(b"username or password is incorrect", response.data)
        self.assertNotIn(b"prototype-password", response.data)

    def test_password_login_opens_chat_and_logout_closes_it(self):
        app = create_app(password_settings(), supervisor_service=self.supervisor)
        client = app.test_client()

        login = client.post(
            "/login",
            data={
                "username": "prototype-user",
                "password": "prototype-password",
            },
        )

        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/")
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn(b"Log out", client.get("/").data)
        self.assertEqual(
            client.post("/api/v1/chat", json={"message": "Question"}).status_code,
            200,
        )
        self.assertEqual(client.post("/logout").headers["Location"], "/login")
        self.assertEqual(client.get("/").headers["Location"], "/login")

    def test_chat_returns_stable_public_contract(self):
        response = self.client.post("/api/v1/chat", json={"message": "Policy?"})
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        UUID(payload["conversationId"])
        UUID(payload["requestId"])
        self.assertEqual(payload["answer"], "The employee support answer.")
        self.assertNotIn("location", payload["sources"][0])

    def test_success_is_logged_without_private_source_links(self):
        analytics = FakeAnalytics()
        app = create_app(
            test_settings(),
            supervisor_service=self.supervisor,
            analytics_service=analytics,
        )

        response = app.test_client().post(
            "/api/v1/chat", json={"message": "Policy?"}
        )

        self.assertEqual(response.status_code, 200)
        event = analytics.events[0]
        self.assertEqual(event.status, "success")
        self.assertEqual(event.question, "Policy?")
        self.assertEqual(event.sources[0].page, 3)
        self.assertEqual(event.agents_used, ("app-agent-mariner-benefits-worker",))
        self.assertIsNone(event.usage)

    def test_analytics_failure_never_breaks_chat(self):
        analytics = FakeAnalytics()
        analytics.error = RuntimeError("private analytics failure")
        app = create_app(
            test_settings(),
            supervisor_service=self.supervisor,
            analytics_service=analytics,
        )

        response = app.test_client().post(
            "/api/v1/chat", json={"message": "Policy?"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private analytics failure", response.get_data(as_text=True))

    def test_same_conversation_reuses_private_session_and_loads_history(self):
        first = self.client.post("/api/v1/chat", json={"message": "First"}).get_json()
        second = self.client.post(
            "/api/v1/chat",
            json={"message": "Follow-up", "conversationId": first["conversationId"]},
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.supervisor.answer_calls[0][1], self.supervisor.answer_calls[1][1])
        self.assertEqual(len(self.supervisor.answer_calls[1][2].turns), 1)

    def test_direct_command_adds_supervisor_routing_instruction(self):
        self.client.post(
            "/api/v1/chat", json={"message": "/benefits When can I enroll?"}
        )

        supervisor_input = self.supervisor.answer_calls[0][0]
        self.assertIn("Call the Benefits Agent", supervisor_input)
        self.assertIn("wait for it to complete", supervisor_input)
        self.assertIn("Do not merely announce", supervisor_input)

    def test_invalid_requests_are_rejected_before_supervisor_call(self):
        responses = (
            self.client.post("/api/v1/chat", data="not-json"),
            self.client.post("/api/v1/chat", json={"message": "  "}),
            self.client.post(
                "/api/v1/chat",
                json={"message": "Question", "conversationId": "not-a-uuid"},
            ),
        )

        self.assertTrue(all(response.status_code == 400 for response in responses))
        self.assertEqual(self.supervisor.answer_calls, [])

    def test_agent_errors_are_sanitized(self):
        self.supervisor.answer_error = SupervisorInvocationError("private backend detail")
        response = self.client.post("/api/v1/chat", json={"message": "Question"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"]["code"], "AGENT_UNAVAILABLE")
        self.assertNotIn("private backend detail", response.get_data(as_text=True))

    def test_unexpected_errors_return_sanitized_response(self):
        self.supervisor.answer_error = RuntimeError(
            "question=private-question answer=private-answer password=private-password"
        )

        response = self.client.post("/api/v1/chat", json={"message": "Question"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("private-question", response.get_data(as_text=True))

    def test_citation_errors_are_identified_and_sanitized(self):
        self.supervisor.answer_error = CitationResolutionError("private SQL detail")
        response = self.client.post("/api/v1/chat", json={"message": "Question"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json()["error"]["code"], "CITATIONS_UNAVAILABLE"
        )
        message = response.get_json()["error"]["message"]
        self.assertIn("Options:", message)
        self.assertIn("/policy, /handbook, or /benefits", message)
        self.assertNotIn("The answer sources could not be verified", message)
        self.assertNotIn("private SQL detail", response.get_data(as_text=True))

    def test_citation_recovery_is_specific_to_direct_command(self):
        self.supervisor.answer_error = CitationResolutionError("private SQL detail")
        response = self.client.post(
            "/api/v1/chat", json={"message": "/handbook jury duty"}
        )

        message = response.get_json()["error"]["message"]
        self.assertIn(
            "/handbook What does the handbook say about jury duty leave?", message
        )

    def test_source_endpoints_retain_ui_contract(self):
        catalog = FakeSourceCatalog()
        app = create_app(
            test_settings(),
            supervisor_service=self.supervisor,
            source_catalog_service=catalog,
        )
        client = app.test_client()

        self.assertEqual(client.get("/api/v1/sources").status_code, 200)
        self.assertEqual(client.get("/api/v1/sources/search?q=policy").status_code, 200)
        self.assertEqual(
            client.get("/api/v1/sources/handbook/children?path=").status_code, 200
        )
        self.assertEqual(
            client.post(
                "/api/v1/sources/handbook/open", json={"path": "policy.pdf"}
            ).status_code,
            200,
        )

    def test_document_link_is_signed_user_bound_and_hides_volume_path(self):
        settings = Settings(
            app_env="test",
            session_secret_key="test-session-secret-key-with-32-characters",
        )
        app = create_app(
            settings,
            supervisor_service=self.supervisor,
            source_catalog_service=SignedSourceCatalog(),
            identity_provider=lambda: "user-one",
        )
        client = app.test_client()

        opened = client.post(
            "/api/v1/sources/handbook/open", json={"path": "policy.pdf"}
        )
        payload = opened.get_json()
        document = client.get(payload["url"])

        self.assertEqual(document.status_code, 200)
        self.assertEqual(document.data, b"%PDF-test")
        self.assertNotIn("/Volumes/", opened.get_data(as_text=True))
        self.assertEqual(document.headers["Cache-Control"], "private, no-store")

    def test_databricks_auth_mode_requires_injected_identity(self):
        settings = Settings(app_env="test", auth_mode="databricks")
        app = create_app(settings, supervisor_service=self.supervisor)

        response = app.test_client().post(
            "/api/v1/chat", json={"message": "Question"}
        )

        self.assertEqual(response.status_code, 401)

    def test_databricks_forwarded_user_header_supplies_identity(self):
        settings = Settings(app_env="test", auth_mode="databricks")
        app = create_app(settings, supervisor_service=self.supervisor)

        response = app.test_client().post(
            "/api/v1/chat",
            json={"message": "Question"},
            headers={"X-Forwarded-User": "opaque-user-id"},
        )

        self.assertEqual(response.status_code, 200)

    def test_readiness_is_cached(self):
        now = [0]
        app = create_app(
            test_settings(),
            supervisor_service=self.supervisor,
            readiness_cache=ReadinessCache(ttl_seconds=30, clock=lambda: now[0]),
        )
        client = app.test_client()
        client.get("/ready")
        now[0] = 10
        client.get("/ready")

        self.assertEqual(self.supervisor.readiness_calls, 1)


if __name__ == "__main__":
    unittest.main()
