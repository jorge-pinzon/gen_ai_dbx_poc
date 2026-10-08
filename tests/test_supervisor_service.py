import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from mariner_genai_dbx.errors import (
    CitationResolutionError,
    DatabricksAuthenticationError,
    SupervisorInvocationError,
)
from mariner_genai_dbx.models import (
    ConversationHistory,
    ConversationTurn,
    Source,
    SupervisorConfig,
)
from mariner_genai_dbx.supervisor_service import (
    DatabricksSupervisorService,
    create_workspace_client,
)


class FakeHttpError(RuntimeError):
    def __init__(self, response):
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHttpError(self)

    def json(self):
        return self.payload


class FakeStreamingResponse(FakeResponse):
    def __init__(self, *events, status_code=200):
        super().__init__(None, status_code=status_code)
        self.events = events
        self.closed = False

    def iter_lines(self, decode_unicode=False):
        del decode_unicode
        for event in self.events:
            yield f"data: {json.dumps(event)}"
        yield "data: [DONE]"

    def close(self):
        self.closed = True


class FakeHttpSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeCitationResolver:
    def __init__(self):
        self.labels = None

    def resolve_labels(self, labels, answer=None):
        self.labels = labels
        self.answer = answer
        return (
            Source(
                number=1,
                label="Record Retention.pdf",
                location="/Volumes/main/policy/Record Retention.pdf",
                page=4,
            ),
        )


def config():
    return SupervisorConfig(
        workspace_host="https://dbc-957e994b-63c5.cloud.databricks.com",
        endpoint_name="mas-53dbd2d7-endpoint",
        client_id="client-id",
        client_secret="client-secret",
    )


def token_response():
    return FakeResponse(
        {"access_token": "oauth-access-token", "expires_in": 3600}
    )


def successful_payload():
    return {
        "id": "resp_test",
        "object": "response",
        "output": [
            {"type": "function_call", "name": "internal_retrieval", "arguments": "{}"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Intermediate response"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Paid loan files must be retained.\n\nSource: Record Retention",
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }


def approval_payload(tool_name="app-agent-mariner-branch-worker"):
    return {
        "id": "resp_approval",
        "object": "response",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I'll query the Branch Operations specialist.",
                    }
                ],
            },
            {
                "type": "mcp_approval_request",
                "id": "approval-request-1",
                "arguments": "{}",
                "name": tool_name,
                "server_label": "mariner-workers",
            },
        ],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    }


def output_item_done(item):
    return {
        "type": "response.output_item.done",
        "id": "stream-event",
        "item": item,
    }


def performance_payload():
    payload = successful_payload()
    payload["output"].insert(
        1,
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "<name>mariner-performance-assistant</name>",
                }
            ],
        },
    )
    payload["output"].insert(
        2,
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "<name>supervisor-agent-2026-09-17-06-32-38</name>",
                }
            ],
        },
    )
    return payload


class SupervisorServiceTests(unittest.TestCase):
    @patch("databricks.sdk.WorkspaceClient")
    def test_workspace_client_uses_least_privilege_data_scopes(self, workspace_client):
        create_workspace_client(config())

        workspace_client.assert_called_once_with(
            host="https://dbc-957e994b-63c5.cloud.databricks.com",
            client_id="client-id",
            client_secret="client-secret",
            auth_type="oauth-m2m",
            scopes=["sql", "files"],
        )

    def test_mints_token_and_sends_responses_input(self):
        http = FakeHttpSession(token_response(), FakeResponse(successful_payload()))
        resolver = FakeCitationResolver()
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=resolver
        )
        prior = ConversationTurn(
            conversation_id="conversation",
            request_id="request",
            user_id="user",
            created_at=datetime.now(timezone.utc),
            question="Earlier question",
            answer="Earlier answer",
        )

        result = service.answer(
            "How long must paid loan files be retained?",
            "private-session",
            ConversationHistory(turns=(prior,)),
        )

        self.assertEqual(
            result.answer,
            "Paid loan files must be retained.",
        )
        self.assertEqual(result.usage.total_tokens, 150)
        self.assertEqual(result.sources[0].page, 4)
        self.assertEqual(resolver.labels, ("Record Retention",))
        self.assertIn("Paid loan files", resolver.answer)

        token_url, token_call = http.calls[0]
        self.assertEqual(
            token_url,
            "https://dbc-957e994b-63c5.cloud.databricks.com/oidc/v1/token",
        )
        self.assertEqual(token_call["auth"], ("client-id", "client-secret"))
        self.assertEqual(token_call["data"]["grant_type"], "client_credentials")
        self.assertEqual(token_call["data"]["scope"], "model-serving")

        endpoint_url, endpoint_call = http.calls[1]
        self.assertEqual(
            endpoint_url,
            "https://dbc-957e994b-63c5.cloud.databricks.com/serving-endpoints/mas-53dbd2d7-endpoint/invocations",
        )
        self.assertEqual(
            endpoint_call["headers"]["Authorization"],
            "Bearer oauth-access-token",
        )
        self.assertEqual(
            endpoint_call["json"]["input"],
            [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {
                    "role": "user",
                    "content": "How long must paid loan files be retained?",
                },
            ],
        )

    def test_streaming_response_is_requested_and_parsed(self):
        stream = FakeStreamingResponse(
            {"type": "response.created", "response": {"id": "resp_test"}},
            {"type": "response.done", "response": successful_payload()},
        )
        http = FakeHttpSession(token_response(), stream)
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=FakeCitationResolver()
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(result.answer, "Paid loan files must be retained.")
        endpoint_call = http.calls[1][1]
        self.assertTrue(endpoint_call["json"]["stream"])
        self.assertTrue(endpoint_call["stream"])
        self.assertTrue(stream.closed)

    def test_streaming_worker_approval_is_preserved_and_continued(self):
        approval = approval_payload("endpoint-benefits-agent-endpoint")
        announcement, approval_request = approval["output"]
        approval_stream = FakeStreamingResponse(
            output_item_done(announcement),
            output_item_done(approval_request),
        )
        completed_stream = FakeStreamingResponse(
            {"type": "response.done", "response": successful_payload()}
        )
        http = FakeHttpSession(token_response(), approval_stream, completed_stream)
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=FakeCitationResolver()
        )

        result = service.answer("What is the PPO plan?", "session", ConversationHistory())

        self.assertEqual(result.answer, "Paid loan files must be retained.")
        self.assertEqual(result.agents_used, ("endpoint-benefits-agent-endpoint",))
        continuation_input = http.calls[2][1]["json"]["input"]
        self.assertEqual(continuation_input[1], announcement)
        self.assertEqual(continuation_input[2], approval_request)
        self.assertEqual(
            continuation_input[3],
            {
                "type": "mcp_approval_response",
                "id": "approval-request-1",
                "approval_request_id": "approval-request-1",
                "approve": True,
            },
        )
        self.assertTrue(approval_stream.closed)
        self.assertTrue(completed_stream.closed)

    def test_streaming_error_payload_is_reported_and_closed(self):
        stream = FakeStreamingResponse(
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "Upstream detail that must remain private",
            }
        )
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(token_response(), stream),
        )

        with self.assertRaises(SupervisorInvocationError) as raised:
            service.answer("Question", "session", ConversationHistory())

        self.assertEqual(
            str(raised.exception.__cause__),
            "The Supervisor stream failed with INVALID_PARAMETER_VALUE",
        )
        self.assertTrue(stream.closed)

    def test_reuses_cached_oauth_token(self):
        http = FakeHttpSession(
            token_response(),
            FakeResponse(successful_payload()),
            FakeResponse(successful_payload()),
        )
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=FakeCitationResolver()
        )

        service.answer("First", "session", ConversationHistory())
        service.answer("Second", "session", ConversationHistory())

        token_calls = [call for call in http.calls if call[0].endswith("/oidc/v1/token")]
        self.assertEqual(len(token_calls), 1)

    def test_readiness_verifies_required_oauth_scope(self):
        http = FakeHttpSession(token_response())
        service = DatabricksSupervisorService(config(), http_session=http)

        result = service.check_readiness()

        self.assertTrue(result.ready)
        self.assertEqual(http.calls[0][1]["data"]["scope"], "model-serving")

    def test_readiness_reports_oauth_rejection(self):
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(FakeResponse({}, status_code=403)),
        )

        with self.assertRaises(DatabricksAuthenticationError):
            service.check_readiness()

    def test_approves_known_worker_and_returns_completed_answer(self):
        http = FakeHttpSession(
            token_response(),
            FakeResponse(approval_payload()),
            FakeResponse(successful_payload()),
        )
        resolver = FakeCitationResolver()
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=resolver
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(
            result.answer,
            "Paid loan files must be retained.",
        )
        self.assertEqual(result.usage.input_tokens, 120)
        self.assertEqual(result.usage.output_tokens, 60)
        self.assertEqual(result.usage.total_tokens, 180)
        self.assertEqual(
            result.agents_used, ("app-agent-mariner-branch-worker",)
        )
        continuation_input = http.calls[2][1]["json"]["input"]
        self.assertEqual(continuation_input[0], {"role": "user", "content": "Question"})
        self.assertEqual(continuation_input[1]["type"], "message")
        self.assertEqual(continuation_input[2]["type"], "mcp_approval_request")
        self.assertEqual(
            continuation_input[3],
            {
                "type": "mcp_approval_response",
                "id": "approval-request-1",
                "approval_request_id": "approval-request-1",
                "approve": True,
            },
        )

    def test_records_each_distinct_worker_used_across_approval_rounds(self):
        second_approval = approval_payload("app-agent-mariner-benefits-worker")
        second_approval["output"][1]["id"] = "approval-request-2"
        http = FakeHttpSession(
            token_response(),
            FakeResponse(approval_payload()),
            FakeResponse(second_approval),
            FakeResponse(successful_payload()),
        )
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=FakeCitationResolver()
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(
            result.agents_used,
            (
                "app-agent-mariner-branch-worker",
                "app-agent-mariner-benefits-worker",
            ),
        )

    def test_records_performance_specialist_from_response_metadata(self):
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(
                token_response(), FakeResponse(performance_payload())
            ),
            citation_resolver=FakeCitationResolver(),
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(result.agents_used, ("mariner-performance-assistant",))

    def test_merges_approved_worker_and_performance_specialist(self):
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(
                token_response(),
                FakeResponse(approval_payload()),
                FakeResponse(performance_payload()),
            ),
            citation_resolver=FakeCitationResolver(),
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(
            result.agents_used,
            (
                "app-agent-mariner-branch-worker",
                "mariner-performance-assistant",
            ),
        )

    def test_uses_approved_performance_source_when_agent_omits_source_line(self):
        payload = performance_payload()
        payload["output"][-1]["content"][0]["text"] = (
            "Managers must conduct one documented performance meeting per quarter."
        )
        resolver = FakeCitationResolver()
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(token_response(), FakeResponse(payload)),
            citation_resolver=resolver,
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(resolver.labels, ("INSTRUCTIONS_PERFORMANCE.pdf",))
        self.assertEqual(result.sources[0].label, "Record Retention.pdf")

    def test_recovers_source_from_specialist_when_final_answer_omits_it(self):
        payload = successful_payload()
        payload["output"][-2]["content"][0]["text"] = (
            "The grounded specialist response.\n\n"
            "Source: 2026 Employee Handbook v1, Section II.B – Appropriate Attire"
        )
        payload["output"][-1]["content"][0]["text"] = (
            "Employees should follow the documented dress code."
        )
        resolver = FakeCitationResolver()
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(token_response(), FakeResponse(payload)),
            citation_resolver=resolver,
        )

        result = service.answer("dress code", "session", ConversationHistory())

        self.assertEqual(
            resolver.labels,
            ("2026 Employee Handbook v1, Section II.B – Appropriate Attire",),
        )
        self.assertEqual(
            result.answer,
            "Employees should follow the documented dress code.",
        )

    def test_rejects_unknown_worker_tool(self):
        http = FakeHttpSession(
            token_response(),
            FakeResponse(approval_payload("unapproved-tool")),
        )
        service = DatabricksSupervisorService(config(), http_session=http)

        with self.assertRaises(SupervisorInvocationError):
            service.answer("Question", "session", ConversationHistory())

        self.assertEqual(len(http.calls), 2)

    def test_rejects_unresolved_source_labels(self):
        http = FakeHttpSession(token_response(), FakeResponse(successful_payload()))
        service = DatabricksSupervisorService(config(), http_session=http)

        with self.assertRaises(CitationResolutionError):
            service.answer("Question", "session", ConversationHistory())

    def test_rejects_output_without_final_assistant_text(self):
        http = FakeHttpSession(
            token_response(),
            FakeResponse({"output": [{"type": "function_call"}]}),
        )
        service = DatabricksSupervisorService(config(), http_session=http)

        with self.assertRaises(SupervisorInvocationError):
            service.answer("Question", "session", ConversationHistory())

    def test_accepts_chat_completions_usage_names(self):
        payload = successful_payload()
        payload["usage"] = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        }
        service = DatabricksSupervisorService(
            config(),
            http_session=FakeHttpSession(token_response(), FakeResponse(payload)),
            citation_resolver=FakeCitationResolver(),
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertEqual(result.usage.input_tokens, 11)
        self.assertEqual(result.usage.output_tokens, 7)
        self.assertEqual(result.usage.total_tokens, 18)

    def test_translates_oauth_errors(self):
        service = DatabricksSupervisorService(
            config(), http_session=FakeHttpSession(FakeResponse({}, status_code=401))
        )

        with self.assertRaises(DatabricksAuthenticationError):
            service.answer("Question", "session", ConversationHistory())

    def test_translates_other_upstream_errors(self):
        http = FakeHttpSession(
            token_response(), FakeResponse({}, status_code=500)
        )
        service = DatabricksSupervisorService(config(), http_session=http)

        with self.assertRaises(SupervisorInvocationError):
            service.answer("Question", "session", ConversationHistory())


if __name__ == "__main__":
    unittest.main()
