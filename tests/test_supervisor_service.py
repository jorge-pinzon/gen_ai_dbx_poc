import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from mariner_genai_dbx.errors import (
    CitationResolutionError,
    DatabricksAuthenticationError,
    SupervisorInvocationError,
)
from mariner_genai_dbx.models import (
    ConversationHistory,
    ConversationTurn,
    DirectRoute,
    Source,
    SupervisorConfig,
)
from mariner_genai_dbx.supervisor_service import (
    DatabricksSupervisorService,
    create_workspace_client,
    _parse_answer_contract,
    _responses_input,
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
    def test_prepare_answer_defers_actual_citation_lookup(self):
        resolver = FakeCitationResolver()
        service = DatabricksSupervisorService(
            config(), http_session=FakeHttpSession(token_response(), FakeResponse(successful_payload())),
            citation_resolver=resolver)
        pending = service.prepare_answer("Explain the policy", "session", ConversationHistory())
        self.assertTrue(pending.citations_pending)
        self.assertIsNone(resolver.labels)
        self.assertNotIn("Source:", pending.answer)
        result = service.resolve_answer(pending)
        self.assertEqual(result.sources[0].page, 4)
        self.assertEqual(resolver.labels, ("Record Retention",))
        self.assertEqual(result.inference_ms, pending.inference_ms)
        self.assertIsInstance(result.citations_ms, int)

    def test_structured_answer_uses_registry_without_label_lookup(self):
        ref = {"document_id": "doc", "document_version": "v1", "chunk_id": "chunk",
               "document_title": "Policy", "page": 4}
        payload = successful_payload()
        payload["output"][-1]["content"][0]["text"] = json.dumps(
            {"answer": "Grounded policy guidance.", "citations": [ref]})

        class RegistryResolver:
            def resolve_labels(self, *args):
                raise AssertionError("Legacy lookup should not run")

            def resolve_citations(self, citations):
                self.citations = citations
                return (Source(number=1, label="Policy", page=4),)

        resolver = RegistryResolver()
        service = DatabricksSupervisorService(
            config(), http_session=FakeHttpSession(token_response(), FakeResponse(payload)),
            citation_resolver=resolver)
        result = service.answer("Question", "session", ConversationHistory())
        self.assertEqual(result.answer, "Grounded policy guidance.")
        self.assertEqual(result.sources[0].page, 4)
        self.assertEqual(resolver.citations, [ref])

    def test_invalid_structured_answers_do_not_fall_back_to_legacy(self):
        for text in ('{"answer":', '{"answer":"text"}',
                     '{"answer":"text","citations":"bad"}',
                     '{"answer":"text\\nSource: Policy","citations":[]}'):
            with self.subTest(text=text):
                with self.assertRaises(CitationResolutionError):
                    _parse_answer_contract(text)

    def test_legacy_and_fenced_json_contract(self):
        self.assertEqual(_parse_answer_contract("Markdown answer"), ("Markdown answer", None))
        self.assertEqual(_parse_answer_contract(
            '```json\n{"answer":"No policy claims.","citations":[]}\n```'),
            ("No policy claims.", []))

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

    def test_policy_endpoint_approval_continues_to_structured_citations(self):
        tool_name = "endpoint-perf-policy-citations-dev"
        ref = {"document_id": "doc", "document_version": "v1", "chunk_id": "chunk",
               "document_title": "Policy", "page": 4}
        payload = successful_payload()
        payload["output"][-1]["content"][0]["text"] = json.dumps(
            {"answer": "Grounded policy guidance.", "citations": [ref]})
        http = FakeHttpSession(token_response(), FakeResponse(approval_payload(tool_name)),
                               FakeResponse(payload))
        observed = []

        class RegistryResolver:
            def resolve_citations(self, citations):
                observed.extend(citations)
                return (Source(number=1, label="Policy", page=4),)

        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=RegistryResolver())
        result = service.answer("Explain the policy", "session", ConversationHistory())
        self.assertEqual(result.answer, "Grounded policy guidance.")
        self.assertEqual(result.agents_used, (tool_name,))
        self.assertEqual(observed, [ref])
        self.assertTrue(http.calls[2][1]["json"]["input"][-1]["approve"])

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

    def test_retries_once_after_throttling_and_honors_retry_after(self):
        throttled = FakeResponse({}, status_code=429)
        throttled.headers = {"Retry-After": "2"}
        throttled.closed = False
        throttled.close = lambda: setattr(throttled, "closed", True)
        delays = []
        http = FakeHttpSession(
            token_response(), throttled, FakeResponse(successful_payload())
        )
        service = DatabricksSupervisorService(
            config(), http_session=http, sleep=delays.append,
            citation_resolver=FakeCitationResolver(),
        )

        result = service.answer("Question", "session", ConversationHistory())

        self.assertTrue(result.answer)
        self.assertEqual(delays, [2.0])
        self.assertTrue(throttled.closed)
        self.assertEqual(len(http.calls), 3)

    def test_retries_once_after_connection_error(self):
        delays = []
        http = FakeHttpSession(
            token_response(),
            requests.ConnectionError("reset"),
            FakeResponse(successful_payload()),
        )
        service = DatabricksSupervisorService(
            config(), http_session=http, sleep=delays.append,
            citation_resolver=FakeCitationResolver(),
        )

        service.answer("Question", "session", ConversationHistory())

        self.assertEqual(len(delays), 1)
        self.assertTrue(0.5 <= delays[0] <= 1.5)

    def test_gives_up_after_one_retry(self):
        delays = []
        http = FakeHttpSession(
            token_response(),
            FakeResponse({}, status_code=503),
            FakeResponse({}, status_code=503),
        )
        service = DatabricksSupervisorService(
            config(), http_session=http, sleep=delays.append
        )

        with self.assertRaises(SupervisorInvocationError):
            service.answer("Question", "session", ConversationHistory())
        self.assertEqual(len(delays), 1)

    def test_does_not_retry_read_timeouts(self):
        http = FakeHttpSession(token_response(), requests.ReadTimeout("slow"))
        service = DatabricksSupervisorService(
            config(), http_session=http, sleep=lambda _: self.fail("retried")
        )

        with self.assertRaises(SupervisorInvocationError):
            service.answer("Question", "session", ConversationHistory())

    def test_default_session_pools_enough_connections_for_all_threads(self):
        service = DatabricksSupervisorService(config())
        adapter = service._http.get_adapter("https://example.cloud.databricks.com")
        self.assertGreaterEqual(adapter._pool_maxsize, 32)

    def test_warm_up_fetches_token_and_starts_citation_refresh(self):
        started = []

        class RefreshingResolver(FakeCitationResolver):
            def start_background_refresh(self):
                started.append(True)

        http = FakeHttpSession(token_response())
        service = DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=RefreshingResolver()
        )

        service.warm_up()

        self.assertEqual(started, [True])
        self.assertIn("/oidc/v1/token", http.calls[0][0])
        self.assertEqual(service._access_token(), "oauth-access-token")
        self.assertEqual(len(http.calls), 1)  # the token is reused, not refetched

    def test_history_sends_recent_turns_and_keeps_latest_answer_whole(self):
        turns = tuple(
            ConversationTurn(
                conversation_id="conversation", request_id=f"request-{index}",
                user_id="user", created_at=datetime(2026, 10, 23, 12, index, tzinfo=timezone.utc),
                question=f"Question {index}", answer=f"{index}" * 4000,
            )
            for index in range(8)
        )

        items = _responses_input(ConversationHistory(turns=turns), "Make that a table")

        questions = [item["content"] for item in items if item["role"] == "user"]
        self.assertEqual(questions, [f"Question {i}" for i in range(2, 8)] + ["Make that a table"])
        answers = [item["content"] for item in items if item["role"] == "assistant"]
        self.assertEqual(answers[-1], "7" * 4000)
        for answer in answers[:-1]:
            self.assertTrue(answer.endswith("[Earlier answer shortened for context.]"))
            self.assertLess(len(answer), 2600)

    def test_short_history_is_sent_unchanged(self):
        turn = ConversationTurn(
            conversation_id="conversation", request_id="request", user_id="user",
            created_at=datetime.now(timezone.utc), question="Q", answer="Short answer",
        )
        items = _responses_input(ConversationHistory(turns=(turn, turn)), "Next")
        self.assertEqual([item["content"] for item in items],
                         ["Q", "Short answer", "Q", "Short answer", "Next"])

    def test_uses_short_connect_timeout(self):
        http = FakeHttpSession(token_response(), FakeResponse(successful_payload()))
        DatabricksSupervisorService(
            config(), http_session=http, citation_resolver=FakeCitationResolver()
        ).answer(
            "Question", "session", ConversationHistory()
        )
        self.assertEqual(http.calls[-1][1]["timeout"][0], 10)



def direct_config():
    return SupervisorConfig(
        workspace_host="https://dbc-957e994b-63c5.cloud.databricks.com",
        endpoint_name="mas-53dbd2d7-endpoint",
        client_id="client-id",
        client_secret="client-secret",
        direct_routes=(
            ("/policy", DirectRoute("ka-policy-endpoint", "responses", "mariner-policy-assistant")),
            ("/benefits", DirectRoute("benefits-agent-endpoint", "chat", "endpoint-benefits-agent-endpoint")),
            ("/performance", DirectRoute("perf-policy-endpoint", "responses", "endpoint-perf-policy-citations-dev")),
        ),
    )


def knowledge_assistant_payload():
    # Knowledge Assistants return one message split into cited fragments.
    return {"output": [{"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": "Paid loan files must be kept for five years ",
         "annotations": [{"type": "url_citation", "url": "", "title": "Record Retention"}]},
        {"type": "output_text", "text": "after payoff.\n\nSource: Record Retention"},
    ]}], "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}


class LiveEventTests(unittest.TestCase):
    def supervisor_stream(self, *extra):
        def done(item):
            return {"type": "response.output_item.done", "item": item}

        def message(text):
            return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}

        def delta(text):
            return {"type": "response.output_text.delta", "item_id": "x", "delta": text}

        return FakeStreamingResponse(
            delta("I'll route your question to the handbook."),
            done(message("I'll route your question to the handbook.")),
            done({"type": "function_call", "name": "ka-56b296c2-4004", "arguments": "{}"}),
            done(message("<name>mariner-handbook-assistant</name>")),
            delta("Specialist raw answer."),
            done(message("Specialist raw answer.")),
            done(message("<name>mariner-supevisor_agent</name>")),
            delta("Final "), delta("answer."),
            *extra,
            done(message("Final answer.")),
        )

    def test_only_the_supervisors_final_answer_is_forwarded(self):
        events = []
        http = FakeHttpSession(token_response(), self.supervisor_stream())
        service = DatabricksSupervisorService(config(), http_session=http, citation_resolver=FakeCitationResolver())
        pending = service.prepare_answer("Dress code?", "s", ConversationHistory(),
                                         on_event=lambda kind, value: events.append((kind, value)))
        self.assertEqual(events, [("progress", "ka-56b296c2-4004"), ("progress", "mariner-handbook-assistant"),
                                  ("text", "Final "), ("text", "answer.")])
        self.assertEqual(pending.answer, "Final answer.")

    def test_tool_call_after_final_text_resets_the_preview(self):
        events = []
        extra = ({"type": "response.output_item.done",
                  "item": {"type": "function_call", "name": "genie-01", "arguments": "{}"}},)
        http = FakeHttpSession(token_response(), self.supervisor_stream(*extra))
        service = DatabricksSupervisorService(config(), http_session=http, citation_resolver=FakeCitationResolver())
        service.prepare_answer("Q", "s", ConversationHistory(), on_event=lambda k, v: events.append((k, v)))
        self.assertEqual(events[-2:], [("progress", "genie-01"), ("reset", None)])

    def test_tool_output_is_passed_as_a_result_event(self):
        events = []
        stream = FakeStreamingResponse(
            {"type": "response.output_item.done", "item": {"type": "function_call", "name": "coaching360_branch_data",
                                                            "call_id": "toolu_1", "arguments": "{}"}},
            {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant",
                                                            "content": [{"type": "output_text", "text": "<name>coaching360_branch_data</name>"}]}},
            {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "call_id": "toolu_1",
                                                            "content": [{"type": "output_text", "text": "||employee|\n|-|-|\n|0|Isaac|"}]}},
            {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant",
                                                            "content": [{"type": "output_text", "text": "<name>mariner-supevisor_agent</name>"}]}},
            {"type": "response.output_text.delta", "item_id": "x", "delta": "Isaac has tasks."},
            {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant",
                                                            "content": [{"type": "output_text", "text": "Isaac has tasks."}]}},
        )
        http = FakeHttpSession(token_response(), stream)
        service = DatabricksSupervisorService(config(), http_session=http, citation_resolver=FakeCitationResolver())
        pending = service.prepare_answer("Q", "s", ConversationHistory(), on_event=lambda k, v: events.append((k, v)))
        self.assertEqual(events, [("progress", "coaching360_branch_data"), ("progress", "coaching360_branch_data"),
                                  ("result", ("coaching360_branch_data", "||employee|\n|-|-|\n|0|Isaac|")),
                                  ("text", "Isaac has tasks.")])
        self.assertEqual(pending.answer, "Isaac has tasks.")

    def test_answers_are_unchanged_without_live_events(self):
        http = FakeHttpSession(token_response(), self.supervisor_stream())
        service = DatabricksSupervisorService(config(), http_session=http, citation_resolver=FakeCitationResolver())
        self.assertEqual(service.prepare_answer("Q", "s", ConversationHistory()).answer, "Final answer.")

    def test_streaming_direct_route_forwards_every_specialist_delta(self):
        cfg = SupervisorConfig(workspace_host="https://w.example", endpoint_name="mas", client_id="c", client_secret="s",
                               direct_routes=(("/handbook", DirectRoute("ka-h", "responses", "mariner-handbook-assistant", True)),))
        stream = FakeStreamingResponse(
            {"type": "response.output_text.delta", "item_id": "a", "delta": "Jury duty is paid. "},
            {"type": "response.output_text.delta", "item_id": "b", "delta": "Notify HR."},
            {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "Jury duty is paid. "}, {"type": "output_text", "text": "Notify HR."}]}},
        )
        http = FakeHttpSession(token_response(), stream)
        events = []
        service = DatabricksSupervisorService(cfg, http_session=http, citation_resolver=FakeCitationResolver())
        pending = service.prepare_direct_answer("/handbook", "Jury duty?", "S", "s",
                                                on_event=lambda k, v: events.append((k, v)))
        self.assertEqual(events, [("progress", "mariner-handbook-assistant"),
                                  ("text", "Jury duty is paid. "), ("text", "Notify HR.")])
        self.assertEqual(http.calls[1][1]["json"]["stream"], True)
        self.assertEqual(pending.answer, "Jury duty is paid. Notify HR.")


class DirectSpecialistTests(unittest.TestCase):
    def test_policy_command_calls_specialist_once_without_supervisor(self):
        resolver = FakeCitationResolver()
        http = FakeHttpSession(token_response(), FakeResponse(knowledge_assistant_payload()))
        service = DatabricksSupervisorService(direct_config(), http_session=http, citation_resolver=resolver)

        pending = service.prepare_direct_answer("/policy", "How long are paid loan files kept?",
                                                "SUPERVISOR MESSAGE", "session")
        result = service.resolve_answer(pending)

        url, call = http.calls[1]
        self.assertTrue(url.endswith("/serving-endpoints/ka-policy-endpoint/invocations"))
        self.assertEqual(call["json"], {"input": [{"role": "user", "content": "How long are paid loan files kept?"}]})
        self.assertNotIn("stream", call["json"])
        self.assertEqual(len(http.calls), 2)  # token + one specialist call
        self.assertEqual(result.answer, "Paid loan files must be kept for five years after payoff.")
        self.assertEqual(resolver.labels, ("Record Retention",))
        self.assertEqual(result.agents_used, ("mariner-policy-assistant",))
        self.assertEqual(result.usage.total_tokens, 15)

    def test_chat_agent_route_uses_messages_and_returns_last_reply(self):
        http = FakeHttpSession(token_response(), FakeResponse(
            {"messages": [{"role": "assistant", "content": "PPO plans are offered."}]}))
        service = DatabricksSupervisorService(direct_config(), http_session=http,
                                              citation_resolver=FakeCitationResolver())
        pending = service.prepare_direct_answer("/benefits", "What are the PPO plans?", "S", "session")
        self.assertEqual(http.calls[1][1]["json"], {"messages": [{"role": "user", "content": "What are the PPO plans?"}]})
        self.assertEqual(pending.answer, "PPO plans are offered.")
        self.assertEqual(pending.agents_used, ("endpoint-benefits-agent-endpoint",))

    def test_structured_citations_are_kept_and_evidence_tags_removed(self):
        ref = {"document_id": "doc", "document_version": "v1", "chunk_id": "chunk",
               "document_title": "INSTRUCTIONS_PERFORMANCE.pdf", "page": 2}
        payload = {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text",
                   "text": json.dumps({"answer": "[POLICY] Ratings run from 1 to 5. [EMPLOYEE DATA] Rated 3.",
                                       "citations": [ref]})}]}]}
        http = FakeHttpSession(token_response(), FakeResponse(payload))
        service = DatabricksSupervisorService(direct_config(), http_session=http,
                                              citation_resolver=FakeCitationResolver())
        pending = service.prepare_direct_answer("/performance", "What do ratings mean?", "S", "session")
        self.assertEqual(pending.answer, "Ratings run from 1 to 5. Rated 3.")
        self.assertEqual(pending.citation_references, (ref,))

    def test_unconfigured_command_uses_the_supervisor(self):
        http = FakeHttpSession(token_response(), FakeResponse(successful_payload()))
        service = DatabricksSupervisorService(direct_config(), http_session=http,
                                              citation_resolver=FakeCitationResolver())
        service.prepare_direct_answer("/handbook", "Jury duty?", "SUPERVISOR MESSAGE", "session")
        url, call = http.calls[1]
        self.assertIn("mas-53dbd2d7-endpoint", url)
        self.assertEqual(call["json"]["input"][-1]["content"], "SUPERVISOR MESSAGE")

    def test_failed_direct_call_falls_back_to_the_supervisor(self):
        http = FakeHttpSession(token_response(), FakeResponse({}, status_code=500),
                               FakeResponse(successful_payload()))
        service = DatabricksSupervisorService(direct_config(), http_session=http,
                                              citation_resolver=FakeCitationResolver())
        with self.assertLogs("mariner_genai_dbx.supervisor_service", level="WARNING"):
            pending = service.prepare_direct_answer("/policy", "Q", "SUPERVISOR MESSAGE", "session")
        self.assertIn("mas-53dbd2d7-endpoint", http.calls[2][0])
        self.assertIn("Paid loan files", pending.answer)

    def test_empty_specialist_answer_falls_back_to_the_supervisor(self):
        http = FakeHttpSession(token_response(), FakeResponse({"output": []}),
                               FakeResponse(successful_payload()))
        service = DatabricksSupervisorService(direct_config(), http_session=http,
                                              citation_resolver=FakeCitationResolver())
        with self.assertLogs("mariner_genai_dbx.supervisor_service", level="WARNING"):
            service.prepare_direct_answer("/policy", "Q", "SUPERVISOR MESSAGE", "session")
        self.assertIn("mas-53dbd2d7-endpoint", http.calls[2][0])

    def test_rejected_identity_is_not_hidden_by_the_fallback(self):
        http = FakeHttpSession(token_response(), FakeResponse({}, status_code=403))
        service = DatabricksSupervisorService(direct_config(), http_session=http)
        with self.assertRaises(DatabricksAuthenticationError):
            service.prepare_direct_answer("/policy", "Q", "S", "session")


if __name__ == "__main__":
    unittest.main()
