"""Databricks Responses API client for the multi-agent Supervisor."""

from __future__ import annotations

import json
import logging
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
from .errors import (
    CitationResolutionError,
    DatabricksAuthenticationError,
    InvalidQuestionError,
    SupervisorInvocationError,
)


logger = logging.getLogger(__name__)

from .models import (
    AgentAnswer,
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
APPROVED_WORKER_TOOLS = frozenset(
    {
        "app-agent-mariner-branch-worker",
        "app-agent-mariner-handbook-worker",
        "app-agent-mariner-benefits-worker",
        "endpoint-benefits-agent-endpoint",
    }
)
WORKSPACE_API_SCOPES = ["sql", "files"]
SUPERVISOR_OAUTH_SCOPE = "model-serving"
FALLBACK_SOURCE_LABELS_BY_AGENT = {
    "mariner-handbook-assistant": ("2026 Employee Handbook v1",),
    "mariner-performance-assistant": ("INSTRUCTIONS_PERFORMANCE.pdf",),
}

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
    ):
        self.config = config
        self._citation_resolver = citation_resolver or NullCitationResolver()
        self._http = http_session or requests.Session()
        self._clock = clock
        self._token_lock = threading.Lock()
        self._access_token_value = config.token
        self._access_token_expires_at = float("inf") if config.token else 0.0

    def answer(
        self,
        message: str,
        session_id: str,
        history: ConversationHistory,
    ) -> AgentAnswer:
        del session_id  # History is sent explicitly; the Responses endpoint is stateless.
        if not isinstance(message, str) or not message.strip():
            raise InvalidQuestionError("Question must be a non-empty string")

        response_input = _responses_input(history, message.strip())
        body = {"input": response_input}
        url = (
            f"{self.config.workspace_host.rstrip('/')}"
            f"/serving-endpoints/{quote(self.config.endpoint_name, safe='')}"
            "/invocations"
        )
        try:
            response = self._invoke(url, body)
            response, usage, agents_used = self._continue_approved_worker_calls(
                url, response_input, response
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

        answer = _final_assistant_text(response)
        labels = _source_labels(answer, agents_used, response)
        try:
            sources = tuple(self._citation_resolver.resolve_labels(labels, answer))
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
        if labels and not sources:
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
            usage=usage,
            agents_used=agents_used,
        )

    def _continue_approved_worker_calls(
        self,
        url: str,
        response_input: list[dict],
        response: dict,
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
            response = self._invoke(url, {"input": continued_input})
            usage = _add_token_usage(usage, _token_usage(response))

        raise SupervisorInvocationError(
            "The Supervisor exceeded the worker approval continuation limit"
        )

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

    def _invoke(self, url: str, body: dict) -> dict:
        """Invoke the Supervisor using streaming while preserving the existing app contract."""
        response = self._post_invocation(url, body, self._access_token())

        logger.debug(
            "Supervisor HTTP response received; status=%s headers=%s",
            response.status_code,
            dict(getattr(response, "headers", {}) or {}),
        )

        if response.status_code == 401 and not self.config.token:
            self._invalidate_token()
            response = self._post_invocation(url, body, self._access_token())
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
            payload = self._parse_stream_response(response)
        else:
            payload = response.json()

        if not isinstance(payload, dict):
            raise SupervisorInvocationError(
                "The Databricks Supervisor returned invalid JSON"
            )
        return payload

    def _post_invocation(self, url: str, body: dict, access_token: str):
        request_body = dict(body)
        request_body["stream"] = True
        return self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=request_body,
            stream=True,
            timeout=self.config.request_timeout_seconds,
        )

    def _parse_stream_response(self, response) -> dict:
        """Parse Databricks SSE events and return the same dict shape used before streaming."""
        collected_text: list[str] = []
        completed_items: list[dict] = []
        final_response: dict | None = None

        try:
            for line in response.iter_lines(decode_unicode=True):
                # This is the raw response line from Databricks. DEBUG logging
                # is used so it can be enabled during troubleshooting without
                # making every production request noisy.
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

                elif event_type == "response.output_text.done":
                    text = event.get("text", "")
                    if isinstance(text, str) and text and not text.startswith("<name>"):
                        collected_text = [text]

                elif event_type == "response.output_item.done":
                    item = event.get("item")
                    if isinstance(item, dict):
                        completed_items.append(item)

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


def _responses_input(history: ConversationHistory, message: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for turn in history.turns:
        items.extend(
            (
                {"role": "user", "content": turn.question},
                {"role": "assistant", "content": turn.answer},
            )
        )
    items.append({"role": "user", "content": message})
    return items


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
