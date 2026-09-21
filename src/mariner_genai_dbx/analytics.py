"""Best-effort Databricks SQL event logging for chat requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from .models import Source, TokenUsage


@dataclass(frozen=True)
class ChatLogEvent:
    user_id: str
    session_id: str
    app_version: str
    latency_ms: int
    event_id: str
    event_timestamp: datetime
    question: str
    answer: str
    sources: tuple[Source, ...]
    status: str
    agents_used: tuple[str, ...] = ()
    error_message: str = ""
    usage: TokenUsage | None = None


class NullAnalyticsService:
    def record(self, event: ChatLogEvent) -> None:
        del event


class DatabricksAnalyticsService:
    def __init__(self, *, workspace_client, warehouse_id: str, table_name: str):
        self._workspace_client = workspace_client
        self._warehouse_id = warehouse_id
        self._table_name = table_name

    def record(self, event: ChatLogEvent) -> None:
        sources_json = json.dumps(
            [
                {
                    "number": source.number,
                    "label": source.label,
                    **({"domain": source.domain} if source.domain else {}),
                    **({"page": source.page} if source.page else {}),
                }
                for source in event.sources
            ],
            separators=(",", ":"),
        )
        agents_used_json = json.dumps(event.agents_used, separators=(",", ":"))
        usage_values = (
            ":input_tokens, :output_tokens, :total_tokens"
            if event.usage is not None
            else "NULL, NULL, NULL"
        )
        parameters = [
            _parameter("user_id", event.user_id),
            _parameter("session_id", event.session_id),
            _parameter("app_version", event.app_version),
            _parameter("latency_ms", str(max(0, event.latency_ms)), "BIGINT"),
            _parameter("event_id", event.event_id),
            _parameter("event_timestamp", event.event_timestamp.isoformat()),
            _parameter("question", event.question),
            _parameter("answer", event.answer),
            _parameter("sources_json", sources_json),
            _parameter("source_count", str(len(event.sources)), "INT"),
            _parameter("agents_used_json", agents_used_json),
            _parameter("status", event.status),
            _parameter("error_message", event.error_message),
        ]
        if event.usage is not None:
            parameters.extend(
                (
                    _integer_parameter("input_tokens", event.usage.input_tokens),
                    _integer_parameter("output_tokens", event.usage.output_tokens),
                    _integer_parameter("total_tokens", event.usage.total_tokens),
                )
            )

        self._workspace_client.statement_execution.execute_statement(
            warehouse_id=self._warehouse_id,
            statement=f"""
                INSERT INTO `{self._table_name.replace('.', '`.`')}` (
                    user_id, session_id, app_version, latency_ms, event_id,
                    event_timestamp, question, answer, sources_json, source_count,
                    agents_used_json, status, error_message, input_tokens, output_tokens,
                    total_tokens, ingested_at
                ) VALUES (
                    :user_id, :session_id, :app_version, :latency_ms, :event_id,
                    CAST(:event_timestamp AS TIMESTAMP), :question, :answer,
                    :sources_json, :source_count, :agents_used_json, :status, :error_message,
                    {usage_values}, CURRENT_TIMESTAMP()
                )
            """.strip(),
            parameters=parameters,
            wait_timeout="0s",
        )


def _parameter(name: str, value: str, parameter_type: str = "STRING"):
    try:
        from databricks.sdk.service.sql import StatementParameterListItem
    except ImportError:
        return {"name": name, "value": value, "type": parameter_type}
    return StatementParameterListItem(name=name, value=value, type=parameter_type)


def _integer_parameter(name: str, value: int):
    return _parameter(name, str(max(0, value)), "BIGINT")
