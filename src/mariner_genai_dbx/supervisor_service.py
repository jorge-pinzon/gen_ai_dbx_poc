"""Databricks Responses API client for the multi-agent Supervisor."""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from urllib.parse import quote

import requests

from .citation_resolver import (
    NullCitationResolver,
    extract_source_labels,
    remove_source_lines,
)
from .citation_registry import validate_citations
from .errors import (
    CitationResolutionError,
    DatabricksAuthenticationError,
    InvalidQuestionError,
    SupervisorInvocationError,
)


logger = logging.getLogger(__name__)

from .models import (
    AgentAnswer,
    PendingAgentAnswer,
    ConversationHistory,
    ReadinessResult,
    SupervisorConfig,
    TokenUsage,
)


MOCK_ANSWER = (
    "The Databricks Supervisor connection has not been configured yet. "
    "The Flask application shell is running in mock mode."
)
MAX_MCP_APPROVAL_ROUNDS = 5
# Throttling and gateway errors are usually short bursts. Retry once, before any
# answer bytes are read, so the user does not have to resubmit. Read timeouts
# are not retried: the endpoint is slow, and a second attempt doubles the wait.
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
MAX_TRANSIENT_RETRIES = 1
MAX_RETRY_AFTER_SECONDS = 5
CONNECT_TIMEOUT_SECONDS = 10
# Above the Gunicorn thread count so concurrent chats reuse warm TLS
# connections instead of discarding them; idle slots cost nothing.
HTTP_POOL_SIZE = 32
# Every Supervisor hop and approval continuation resends the history, so keep it
# to recent context. The latest answer stays whole for follow-ups such as
# "make that a table"; older answers are shortened to about the p90 length.
SUPERVISOR_HISTORY_TURNS = 6
OLDER_ANSWER_MAX_CHARACTERS = 2500
SHORTENED_ANSWER_NOTE = "\n[Earlier answer shortened for context.]"
APPROVED_WORKER_TOOLS = frozenset(
    {
        "app-agent-mariner-branch-worker",
        "app-agent-mariner-handbook-worker",
        "app-agent-mariner-benefits-worker",
        "endpoint-benefits-agent-endpoint",
        "endpoint-perf-policy-citations-dev",
        # Prod name of the same read-only worker (dbx_to_prod/notebooks/05_custom_agents.py).
        "endpoint-perf-policy-citations",
    }
)
WORKSPACE_API_SCOPES = ["sql", "files"]
SUPERVISOR_OAUTH_SCOPE = "model-serving"
FALLBACK_SOURCE_LABELS_BY_AGENT = {
    "mariner-handbook-assistant": ("2026 Employee Handbook v1",),
    "mariner-performance-assistant": ("INSTRUCTIONS_PERFORMANCE.pdf",),
}

# Evidence markers the performance specialist adds for the Supervisor
# (agent_descriptions/performance_policy_agent.md). Users never see them.
_SPECIALIST_EVIDENCE_TAGS = re.compile(r"\[(?:POLICY|EMPLOYEE DATA)\] ?")

# The Supervisor's own <name> marker (its tile name is spelled "supevisor").
_SUPERVISOR_NAME = re.compile(r"supe(?:r)?visor", re.IGNORECASE)

_AGENT_NAME_TAG_PATTERN = re.compile(
    r"<name>\s*(?P<name>[^<]{1,200}?)\s*</name>",
    re.IGNORECASE,
)


def _merge_agent_names(*agent_groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return unique agent names in first-seen order."""
    merged: list[str] = []
    seen: set[str] = set()
    for group in agent_groups:
        for raw_name in group:
            name = raw_name.strip()
            normalized = name.casefold()
            if not name or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(name)
    return tuple(merged)


def _response_agent_names(response: dict[str, object]) -> tuple[str, ...]:
    """Extract specialist names emitted by Databricks supervisor responses."""
    names: list[str] = []
    output = response.get("output", [])
    if not isinstance(output, list):
        return ()

    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        if item.get("role") != "assistant":
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            value = block.get("text")
            if not isinstance(value, str):
                continue
            for match in _AGENT_NAME_TAG_PATTERN.finditer(value):
                name = match.group("name").strip()
                normalized = name.casefold()
                if normalized == "supervisor" or normalized.startswith("supervisor-agent"):
                    continue
                names.append(name)
    return _merge_agent_names(names)


def _response_source_labels(response: dict[str, object]) -> tuple[str, ...]:
    """Recover citations from grounded specialist messages in the response."""
    labels: list[str] = []
    output = response.get("output", [])
    if not isinstance(output, list):
        return ()
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        if item.get("role") != "assistant":
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            value = block.get("text")
            if isinstance(value, str):
                labels.extend(extract_source_labels(value))
    return _merge_agent_names(labels)


def _source_labels(
    answer: str, agents_used: tuple[str, ...], response: dict[str, object]
) -> tuple[str, ...]:
    labels = extract_source_labels(answer) or _response_source_labels(response)
    fallback_labels: list[str] = []
    for agent_name in agents_used:
        fallback_labels.extend(
            FALLBACK_SOURCE_LABELS_BY_AGENT.get(agent_name.casefold(), ())
        )
    return _merge_agent_names(labels, fallback_labels)


class MockSupervisorService:
    """Development-only service used before the live connection is enabled."""

    def answer(
        self,
        message: str,
        session_id: str,
        history: ConversationHistory,
    ) -> AgentAnswer:
        del message, session_id, history
        return AgentAnswer(answer=MOCK_ANSWER)

    def check_readiness(self) -> ReadinessResult:
        return ReadinessResult(ready=True)


class DatabricksSupervisorService:
    """Invoke a ResponsesAgent hosted on a Databricks serving endpoint."""

    def __init__(
        self,
        config: SupervisorConfig,
        *,
        http_session=None,
        citation_resolver=None,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.config = config
        self._citation_resolver = citation_resolver or NullCitationResolver()
        self._http = http_session or _pooled_session()
        self._clock = clock
        self._sleep = sleep
        self._token_lock = threading.Lock()
        self._access_token_value = config.token
        self._access_token_expires_at = float("inf") if config.token else 0.0

    def answer(
        self,
        message: str,
        session_id: str,
        history: ConversationHistory,
    ) -> AgentAnswer:
        return self.resolve_answer(self.prepare_answer(message, session_id, history))

    def prepare_answer(
        self,
        message: str,
        session_id: str,
        history: ConversationHistory,
        *,
        on_event=None,
    ) -> PendingAgentAnswer:
        """on_event(kind, value), when given, receives live "progress", "text" and
        "reset" events while the Supervisor works; the returned answer is unchanged."""
        del session_id  # History is sent explicitly; the Responses endpoint is stateless.
        if not isinstance(message, str) or not message.strip():
            raise InvalidQuestionError("Question must be a non-empty string")

        start_refresh = getattr(self._citation_resolver, "start_background_refresh", None)
        if start_refresh is not None:
            start_refresh()

        response_input = _responses_input(history, message.strip())
        inference_started_at = self._clock()
        body = {"input": response_input}
        url = (
            f"{self.config.workspace_host.rstrip('/')}"
            f"/serving-endpoints/{quote(self.config.endpoint_name, safe='')}"
            "/invocations"
        )
        try:
            response = self._invoke(url, body, on_event=on_event)
            response, usage, agents_used = self._continue_approved_worker_calls(
                url, response_input, response, on_event=on_event
            )
            agents_used = _merge_agent_names(
                agents_used,
                _response_agent_names(response),
            )
        except Exception as error:
            if _looks_like_authentication_error(error):
                raise DatabricksAuthenticationError(
                    "Databricks rejected the configured identity"
                ) from error
            raise SupervisorInvocationError(
                "The Databricks Supervisor request failed"
            ) from error

        answer, citations = _parse_answer_contract(_final_assistant_text(response))
        labels = _source_labels(answer, agents_used, response) if citations is None else ()
        inference_ms = round((self._clock() - inference_started_at) * 1000)
        return PendingAgentAnswer(
            answer=remove_source_lines(answer), source_labels=labels,
            citation_references=tuple(citations) if citations is not None else None,
            usage=usage, agents_used=agents_used, inference_ms=inference_ms,
        )

    def resolve_answer(self, pending: PendingAgentAnswer) -> AgentAnswer:
        answer = pending.answer
        labels = pending.source_labels
        citations = pending.citation_references
        citations_started_at = self._clock()
        try:
            if citations is None:
                sources = tuple(self._citation_resolver.resolve_labels(labels, answer))
            else:
                sources = tuple(self._citation_resolver.resolve_citations(list(citations)))
        except CitationResolutionError as error:
            logger.error(
                "Citation resolution failed; error_type=%s",
                type(error).__name__,
            )
            raise
        except Exception as error:
            logger.error(
                "Unexpected citation resolver failure; error_type=%s",
                type(error).__name__,
            )
            raise CitationResolutionError(
                "The Supervisor citations could not be resolved"
            ) from error
        finally:
            citations_ms = round((self._clock() - citations_started_at) * 1000)
            logger.info(
                "Supervisor stages completed; inference_ms=%s citations_ms=%s source_labels=%s",
                pending.inference_ms,
                citations_ms,
                len(labels),
            )
        if (labels or citations) and not sources:
            logger.error(
                "Supervisor source labels did not resolve; label_count=%s",
                len(labels),
            )
            raise CitationResolutionError(
                "The Supervisor source labels did not resolve to approved documents"
            )
        return AgentAnswer(
            answer=remove_source_lines(answer),
            sources=sources,
            usage=pending.usage,
            agents_used=pending.agents_used,
            inference_ms=pending.inference_ms,
            citations_ms=citations_ms,
        )

    def prepare_direct_answer(
        self,
        command: str,
        question: str,
        supervisor_message: str,
        session_id: str,
        *,
        on_event=None,
    ) -> PendingAgentAnswer:
        """Answer a slash command from its specialist, skipping the Supervisor hops.

        Unconfigured commands and failed direct calls use the Supervisor route,
        so a slash command never ends with less than it would have had before.
        """
        route = dict(self.config.direct_routes).get(command)
        if route is None:
            return self.prepare_answer(supervisor_message, session_id, ConversationHistory(), on_event=on_event)
        start_refresh = getattr(self._citation_resolver, "start_background_refresh", None)
        if start_refresh is not None:
            start_refresh()
        started_at = self._clock()
        url = (
            f"{self.config.workspace_host.rstrip('/')}"
            f"/serving-endpoints/{quote(route.endpoint, safe='')}/invocations"
        )
        body = (
            {"messages": [{"role": "user", "content": question}]}
            if route.api == "chat"
            else {"input": [{"role": "user", "content": question}]}
        )
        if on_event is not None:
            on_event("progress", route.agent)
        try:
            if route.stream and route.api == "responses":
                response = self._invoke(url, body, on_event=on_event, all_text=True)
            else:
                response = self._invoke_json(url, body)
            text = _direct_text(response, route.api)
        except Exception as error:
            if _looks_like_authentication_error(error):
                raise DatabricksAuthenticationError(
                    "Databricks rejected the configured identity"
                ) from error
            logger.warning(
                "Direct specialist call failed; using the Supervisor; command=%s error_type=%s",
                command,
                type(error).__name__,
            )
            return self.prepare_answer(supervisor_message, session_id, ConversationHistory(), on_event=on_event)

        answer, citations = _parse_answer_contract(text)
        answer = _SPECIALIST_EVIDENCE_TAGS.sub("", answer)
        agents_used = (route.agent,)
        labels = (
            _source_labels(answer, agents_used, response if route.api == "responses" else {})
            if citations is None
            else ()
        )
        inference_ms = round((self._clock() - started_at) * 1000)
        logger.info(
            "Direct specialist answered; command=%s inference_ms=%s", command, inference_ms
        )
        return PendingAgentAnswer(
            answer=remove_source_lines(answer), source_labels=labels,
            citation_references=tuple(citations) if citations is not None else None,
            usage=_token_usage(response), agents_used=agents_used, inference_ms=inference_ms,
        )

    def _invoke_json(self, url: str, body: dict) -> dict:
        response = self._post_with_retry(url, body, stream=False)
        if response.status_code == 401 and not self.config.token:
            self._invalidate_token()
            response = self._post_invocation(url, body, self._access_token(), stream=False)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise SupervisorInvocationError("The specialist returned invalid JSON")
        return payload

    def _continue_approved_worker_calls(
        self,
        url: str,
        response_input: list[dict],
        response: dict,
        *,
        on_event=None,
    ) -> tuple[dict, TokenUsage, tuple[str, ...]]:
        """Approve known read-only worker calls and finish the Supervisor loop."""
        continued_input = list(response_input)
        usage = _token_usage(response)
        agents_used: list[str] = []
        for _ in range(MAX_MCP_APPROVAL_ROUNDS):
            output = response.get("output")
            if not isinstance(output, list):
                raise SupervisorInvocationError(
                    "The Supervisor returned an invalid output array"
                )
            approval_requests = [
                item
                for item in output
                if isinstance(item, dict)
                and item.get("type") == "mcp_approval_request"
            ]
            if not approval_requests:
                if usage.total_tokens == 0:
                    raw_usage = response.get("usage")
                    logger.warning(
                        "Supervisor returned no token usage; usage_present=%s usage_field_count=%s",
                        isinstance(raw_usage, dict),
                        len(raw_usage) if isinstance(raw_usage, dict) else 0,
                    )
                return response, usage, tuple(agents_used)

            approval_responses = []
            for item in approval_requests:
                request_id = item.get("id")
                tool_name = item.get("name")
                if (
                    not isinstance(request_id, str)
                    or not request_id
                    or tool_name not in APPROVED_WORKER_TOOLS
                ):
                    raise SupervisorInvocationError(
                        "The Supervisor requested an unapproved tool"
                    )
                if tool_name not in agents_used:
                    agents_used.append(tool_name)
                approval_responses.append(
                    {
                        "type": "mcp_approval_response",
                        "id": request_id,
                        "approval_request_id": request_id,
                        "approve": True,
                    }
                )

            continued_input.extend(output)
            continued_input.extend(approval_responses)
            response = self._invoke(url, {"input": continued_input}, on_event=on_event)
            usage = _add_token_usage(usage, _token_usage(response))

        raise SupervisorInvocationError(
            "The Supervisor exceeded the worker approval continuation limit"
        )

    def warm_up(self) -> None:
        """Fetch the OAuth token and start the citation cache before the first chat."""
        start_refresh = getattr(self._citation_resolver, "start_background_refresh", None)
        if start_refresh is not None:
            start_refresh()
        self._access_token()

    def check_readiness(self) -> ReadinessResult:
        try:
            self._access_token()
        except Exception as error:
            if _looks_like_authentication_error(error):
                raise DatabricksAuthenticationError(
                    "Databricks rejected the configured identity"
                ) from error
            raise SupervisorInvocationError(
                "The Databricks Supervisor readiness check failed"
            ) from error
        return ReadinessResult(ready=True)

    def _invoke(self, url: str, body: dict, *, on_event=None, all_text: bool = False) -> dict:
        """Invoke the Supervisor using streaming while preserving the existing app contract."""
        response = self._post_with_retry(url, body)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Supervisor HTTP response received; status=%s headers=%s",
                response.status_code,
                dict(getattr(response, "headers", {}) or {}),
            )

        if response.status_code == 401 and not self.config.token:
            self._invalidate_token()
            response = self._post_invocation(url, body, self._access_token())
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Supervisor HTTP response received after token refresh; status=%s headers=%s",
                    response.status_code,
                    dict(getattr(response, "headers", {}) or {}),
                )

        response.raise_for_status()

        # Production requests use the Responses API streaming format. Keep a
        # JSON fallback so local/unit-test fakes and non-streaming endpoints
        # continue to work with the existing service.
        if hasattr(response, "iter_lines"):
            payload = self._parse_stream_response(response, _LiveEvents(on_event, all_text))
        else:
            payload = response.json()

        if not isinstance(payload, dict):
            raise SupervisorInvocationError(
                "The Databricks Supervisor returned invalid JSON"
            )
        return payload

    def _post_with_retry(self, url: str, body: dict, *, stream: bool = True):
        for attempt in range(MAX_TRANSIENT_RETRIES + 1):
            last_attempt = attempt == MAX_TRANSIENT_RETRIES
            try:
                response = self._post_invocation(url, body, self._access_token(), stream=stream)
            except requests.ConnectionError as error:
                if last_attempt:
                    raise
                logger.warning(
                    "Supervisor connection failed; retrying; error_type=%s",
                    type(error).__name__,
                )
                self._sleep(_retry_delay(None))
                continue
            if last_attempt or response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            delay = _retry_delay(response)
            logger.warning(
                "Supervisor returned a transient error; retrying; status=%s delay_ms=%s",
                response.status_code,
                round(delay * 1000),
            )
            close = getattr(response, "close", None)
            if callable(close):
                close()
            self._sleep(delay)
        raise AssertionError("unreachable")

    def _post_invocation(self, url: str, body: dict, access_token: str, *, stream: bool = True):
        request_body = dict(body)
        if stream:
            request_body["stream"] = True
        return self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=request_body,
            stream=stream,
            # Fail fast when the endpoint is unreachable; the read timeout is
            # the longest allowed silence between streamed events.
            timeout=(
                min(CONNECT_TIMEOUT_SECONDS, self.config.request_timeout_seconds),
                self.config.request_timeout_seconds,
            ),
        )

    def _parse_stream_response(self, response, live=None) -> dict:
        """Parse Databricks SSE events and return the same dict shape used before streaming."""
        live = live or _LiveEvents(None)
        collected_text: list[str] = []
        completed_items: list[dict] = []
        final_response: dict | None = None
        debug_stream = logger.isEnabledFor(logging.DEBUG)

        try:
            for line in response.iter_lines(decode_unicode=True):
                # This is the raw response line from Databricks. DEBUG logging
                # is used so it can be enabled during troubleshooting without
                # making every production request noisy.
                if debug_stream:
                    logger.debug("SUPERVISOR RAW STREAM: %s", line)

                if not line:
                    continue

                # Some proxies/clients may return bytes despite decode_unicode=True.
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")

                if not line.startswith("data:"):
                    continue

                payload_text = line[5:].strip()
                if not payload_text:
                    continue
                if payload_text == "[DONE]":
                    break

                try:
                    event = json.loads(payload_text)
                except ValueError:
                    logger.debug("Ignoring non-JSON Supervisor stream event")
                    continue

                error_code = (
                    event.get("error_code") if isinstance(event, dict) else None
                )
                if isinstance(error_code, str) and error_code:
                    logger.error(
                        "Supervisor stream returned an error; error_code=%s",
                        error_code,
                    )
                    raise SupervisorInvocationError(
                        f"The Supervisor stream failed with {error_code}"
                    )

                event_type = event.get("type", "") if isinstance(event, dict) else ""

                if event_type == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if isinstance(delta, str):
                        collected_text.append(delta)
                        live.text(delta)

                elif event_type == "response.output_text.done":
                    text = event.get("text", "")
                    if isinstance(text, str) and text and not text.startswith("<name>"):
                        collected_text = [text]

                elif event_type == "response.output_item.done":
                    item = event.get("item")
                    if isinstance(item, dict):
                        completed_items.append(item)
                        live.item_done(item)

                elif event_type == "response.done":
                    response_obj = event.get("response")
                    if isinstance(response_obj, dict):
                        final_response = response_obj

            if final_response is not None:
                return final_response

            # Agent Bricks streams completed messages and MCP approval requests as
            # output-item events, then terminates with [DONE] without necessarily
            # sending a response.done envelope. Preserve those structured items so
            # the approval continuation loop can authorize known worker endpoints.
            if completed_items:
                return {
                    "object": "response",
                    "output": completed_items,
                }

            final_text = "".join(collected_text).strip()
            if final_text:
                return {
                    "object": "response",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": final_text,
                                }
                            ],
                        }
                    ],
                }

            raise SupervisorInvocationError(
                "The Databricks Supervisor returned no usable streamed response"
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def _access_token(self) -> str:
        with self._token_lock:
            now = self._clock()
            if self._access_token_value and now < self._access_token_expires_at:
                return self._access_token_value
            if not self.config.client_id or not self.config.client_secret:
                raise DatabricksAuthenticationError(
                    "Databricks OAuth client credentials are not configured"
                )
            token_url = f"{self.config.workspace_host.rstrip('/')}/oidc/v1/token"
            response = self._http.post(
                token_url,
                auth=(self.config.client_id, self.config.client_secret),
                data={
                    "grant_type": "client_credentials",
                    # Worker tools can invoke other serving endpoints, so the
                    # Supervisor token must authorize nested model serving too.
                    "scope": SUPERVISOR_OAUTH_SCOPE,
                },
                timeout=min(30, self.config.request_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(access_token, str) or not access_token:
                raise DatabricksAuthenticationError(
                    "Databricks OAuth returned no access token"
                )
            expires_in = _nonnegative_integer(payload.get("expires_in")) or 3600
            refresh_margin = min(60, max(5, expires_in // 10))
            self._access_token_value = access_token
            self._access_token_expires_at = now + max(1, expires_in - refresh_margin)
            return access_token

    def _invalidate_token(self) -> None:
        with self._token_lock:
            self._access_token_value = None
            self._access_token_expires_at = 0.0


class _LiveEvents:
    """Turn Supervisor stream events into live "progress", "result", "text" and "reset" callbacks.

    In Supervisor mode only the final answer is forwarded as text: text after the
    Supervisor's own <name> marker. Routing notes are never forwarded. A tool's
    output is passed as a "result" event, (tool name, output text), and the
    caller decides whether to show it. A tool call after the final marker means
    the text was not final, so the preview is reset. In all_text mode (a
    specialist called directly) every assistant delta is the answer.
    """

    def __init__(self, on_event, all_text=False):
        self._on_event = on_event
        self._final = all_text
        self._all_text = all_text
        self._sent_text = False
        self._tool_names = {}  # call_id -> tool name

    def text(self, delta):
        if self._on_event is not None and self._final and delta:
            self._sent_text = True
            self._on_event("text", delta)

    def item_done(self, item):
        if self._on_event is None or self._all_text:
            return
        kind = item.get("type")
        if kind in {"function_call", "mcp_approval_request"}:
            if isinstance(item.get("name"), str):
                self._on_event("progress", item["name"])
                if isinstance(item.get("call_id"), str):
                    self._tool_names[item["call_id"]] = item["name"]
            self._leave_final()
        elif kind == "message":
            content = item.get("content")
            text = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            ) if isinstance(content, list) else ""
            tool = self._tool_names.get(item.get("call_id"))
            if tool and text.strip():
                self._on_event("result", (tool, text))
                return
            match = _AGENT_NAME_TAG_PATTERN.fullmatch(text.strip())
            if not match:
                return
            name = match.group("name").strip()
            if _SUPERVISOR_NAME.search(name):
                self._final = True
            else:
                self._on_event("progress", name)
                self._leave_final()

    def _leave_final(self):
        if self._sent_text:
            self._on_event("reset", None)
        self._final = False
        self._sent_text = False


def create_workspace_client(config: SupervisorConfig):
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError as error:
        raise SupervisorInvocationError(
            "databricks-sdk is required for Databricks Supervisor mode"
        ) from error

    options = {"host": config.workspace_host}
    if config.token:
        options["token"] = config.token
    elif config.client_id and config.client_secret:
        options.update(
            client_id=config.client_id,
            client_secret=config.client_secret,
            auth_type="oauth-m2m",
            scopes=WORKSPACE_API_SCOPES,
        )
    try:
        return WorkspaceClient(**options)
    except Exception as error:
        if _looks_like_authentication_error(error):
            raise DatabricksAuthenticationError(
                "Databricks credentials could not be loaded"
            ) from error
        raise SupervisorInvocationError(
            "The Databricks client could not be initialized"
        ) from error


def _pooled_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=4, pool_maxsize=HTTP_POOL_SIZE
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _retry_delay(response) -> float:
    """Honor a short Retry-After; otherwise jitter so bursts do not retry in step."""
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        seconds = float(retry_after)
    except (TypeError, ValueError):
        seconds = None
    if seconds is not None and 0 <= seconds <= MAX_RETRY_AFTER_SECONDS:
        return seconds
    return random.uniform(0.5, 1.5)


def _responses_input(history: ConversationHistory, message: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    turns = history.turns[-SUPERVISOR_HISTORY_TURNS:]
    for index, turn in enumerate(turns):
        answer = turn.answer
        if index < len(turns) - 1 and len(answer) > OLDER_ANSWER_MAX_CHARACTERS:
            answer = answer[:OLDER_ANSWER_MAX_CHARACTERS].rstrip() + SHORTENED_ANSWER_NOTE
        items.extend(
            (
                {"role": "user", "content": turn.question},
                {"role": "assistant", "content": answer},
            )
        )
    items.append({"role": "user", "content": message})
    return items


def _direct_text(response: dict, api: str) -> str:
    """Final assistant text from a specialist endpoint, joined exactly as returned."""
    if api == "chat":
        messages = response.get("messages")
        texts = [
            message.get("content") for message in messages or []
            if isinstance(message, dict) and message.get("role") == "assistant"
            and isinstance(message.get("content"), str)
        ] if isinstance(messages, list) else []
        text = texts[-1] if texts else ""
    else:
        text = ""
        for item in response.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") != "assistant":
                continue
            # Knowledge Assistants split one answer into cited fragments; the
            # fragments already carry their own spacing.
            parts = [
                content.get("text") for content in item.get("content") or []
                if isinstance(content, dict) and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ]
            if any(part.strip() for part in parts):
                text = "".join(parts)
    if not text.strip():
        raise SupervisorInvocationError("The specialist returned no answer")
    return text.strip()


def _parse_answer_contract(text):
    """Accept legacy Markdown; reject malformed structured envelopes closed."""
    candidate = text.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    if not candidate.startswith("{"):
        return text, None
    try:
        payload = json.loads(candidate)
    except ValueError as error:
        if re.search(r'"(?:answer|citations)"\s*(?::|$)', candidate):
            raise CitationResolutionError("Malformed structured answer") from error
        return text, None
    # Other specialists can legitimately return JSON examples or data. Only
    # an answer/citations envelope opts into the structured citation contract.
    if not isinstance(payload, dict) or not {"answer", "citations"}.intersection(payload):
        return text, None
    if not isinstance(payload, dict) or set(payload) != {"answer", "citations"}:
        raise CitationResolutionError("Invalid structured answer fields")
    answer = payload["answer"]
    if not isinstance(answer, str) or not answer.strip():
        raise CitationResolutionError("Missing structured answer text")
    citations = validate_citations(payload["citations"])
    if extract_source_labels(answer) and not citations:
        raise CitationResolutionError("Structured answer omits referenced citations")
    return answer, citations


def _final_assistant_text(response) -> str:
    if not isinstance(response, dict):
        raise SupervisorInvocationError("The Supervisor returned an invalid response")

    final_text = None
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        parts = []
        for content in item.get("content", []):
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if parts:
            final_text = "\n".join(parts)

    if not final_text:
        raise SupervisorInvocationError(
            "The Supervisor returned no final assistant output"
        )
    return final_text


def _token_usage(response: dict) -> TokenUsage:
    usage = response.get("usage") if isinstance(response, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _nonnegative_integer(
        usage.get("input_tokens", usage.get("prompt_tokens"))
    )
    output_tokens = _nonnegative_integer(
        usage.get("output_tokens", usage.get("completion_tokens"))
    )
    total_tokens = _nonnegative_integer(usage.get("total_tokens"))
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens or input_tokens + output_tokens,
    )


def _add_token_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    input_tokens = left.input_tokens + right.input_tokens
    output_tokens = left.output_tokens + right.output_tokens
    reported_total = left.total_tokens + right.total_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=reported_total or input_tokens + output_tokens,
    )


def _nonnegative_integer(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _looks_like_authentication_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    text = f"{type(error).__name__} {error}".casefold()
    return status_code in {401, 403} or any(
        marker in text
        for marker in (
            "401",
            "403",
            "authentication",
            "unauthenticated",
            "permission denied",
            "permissiondenied",
        )
    )
