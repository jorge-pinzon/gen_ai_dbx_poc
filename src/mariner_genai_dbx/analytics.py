"""Best-effort Databricks SQL event logging for chat requests."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from .models import Source, TokenUsage


logger = logging.getLogger(__name__)


class BackgroundAnalyticsService:
    """Bounded, best-effort delivery without SQL calls on the request thread.

    Events are written in batches so a burst of chats becomes a few INSERTs
    instead of one per chat, which keeps the shared warehouse free for reads.
    Start lazily so Gunicorn workers own their thread even with preloading.
    Pending events may be lost on process exit, just like other best-effort logs.
    """

    def __init__(
        self,
        service,
        *,
        max_pending: int = 256,
        batch_size: int = 25,
        flush_seconds: float = 5.0,
        clock=time.monotonic,
    ):
        if max_pending < 1 or batch_size < 1 or flush_seconds < 0:
            raise ValueError("Analytics queue limits must be positive")
        self._service = service
        self._queue = queue.Queue(maxsize=max_pending)
        self._batch_size = batch_size
        self._flush_seconds = flush_seconds
        self._clock = clock
        self._start_lock = threading.Lock()
        self._worker = None

    def record(self, event: ChatLogEvent) -> None:
        with self._start_lock:
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, name="chat-analytics", daemon=True
                )
                self._worker.start()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("Analytics queue full; event dropped")

    def _run(self):
        while True:
            batch = self._next_batch()
            try:
                self._deliver(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _next_batch(self) -> list:
        batch = [self._queue.get()]
        deadline = self._clock() + self._flush_seconds
        while len(batch) < self._batch_size:
            remaining = deadline - self._clock()
            try:
                batch.append(
                    self._queue.get(timeout=remaining)
                    if remaining > 0
                    else self._queue.get_nowait()
                )
            except queue.Empty:
                break
        return batch

    def _deliver(self, batch: list) -> None:
        record_many = getattr(self._service, "record_many", None)
        if callable(record_many):
            try:
                record_many(batch)
            except Exception as error:
                logger.warning(
                    "Background analytics failed; error_type=%s event_count=%s",
                    type(error).__name__,
                    len(batch),
                )
            return
        for event in batch:
            try:
                self._service.record(event)
            except Exception as error:
                logger.warning(
                    "Background analytics failed; error_type=%s", type(error).__name__
                )


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
    inference_ms: int | None = None
    citations_ms: int | None = None
    stage_ms: dict | None = None  # milliseconds per stage, e.g. {"tool": 4400, "result": 26400}


class NullAnalyticsService:
    def record(self, event: ChatLogEvent) -> None:
        del event


# One typed JSON parameter carries the whole batch, so the statement text and
# parameter count stay fixed no matter how many events are written.
EVENT_SCHEMA = (
    "ARRAY<STRUCT<user_id: STRING, session_id: STRING, app_version: STRING, "
    "latency_ms: BIGINT, event_id: STRING, event_timestamp: STRING, question: STRING, "
    "answer: STRING, sources_json: STRING, source_count: INT, agents_used_json: STRING, "
    "status: STRING, error_message: STRING, input_tokens: BIGINT, output_tokens: BIGINT, "
    "total_tokens: BIGINT, inference_ms: BIGINT, citations_ms: BIGINT, stage_timings_json: STRING>>"
)


class DatabricksAnalyticsService:
    def __init__(self, *, workspace_client, warehouse_id: str, table_name: str, stage_timings: bool = False):
        self._workspace_client = workspace_client
        self._warehouse_id = warehouse_id
        self._table_name = table_name
        # The stage_timings_json column exists only after sql/add_flask_app_logs_stage_timings.sql.
        self._stage_column = ", stage_timings_json" if stage_timings else ""

    def record(self, event: ChatLogEvent) -> None:
        self.record_many([event])

    def record_many(self, events) -> None:
        if not events:
            return
        events_json = json.dumps([_event_row(event) for event in events], separators=(",", ":"))
        self._workspace_client.statement_execution.execute_statement(
            warehouse_id=self._warehouse_id,
            statement=f"""
                INSERT INTO `{self._table_name.replace('.', '`.`')}` (
                    user_id, session_id, app_version, latency_ms, event_id,
                    event_timestamp, question, answer, sources_json, source_count,
                    agents_used_json, status, error_message, input_tokens, output_tokens,
                    total_tokens, inference_ms, citations_ms{self._stage_column}, ingested_at
                )
                SELECT
                    e.user_id, e.session_id, e.app_version, e.latency_ms, e.event_id,
                    CAST(e.event_timestamp AS TIMESTAMP), e.question, e.answer,
                    e.sources_json, e.source_count, e.agents_used_json, e.status,
                    e.error_message, e.input_tokens, e.output_tokens, e.total_tokens,
                    e.inference_ms, e.citations_ms{self._stage_column.replace(", ", ", e.")}, CURRENT_TIMESTAMP()
                FROM (SELECT inline(from_json(:events_json, '{EVENT_SCHEMA}'))) e
            """.strip(),
            parameters=[_parameter("events_json", events_json)],
            wait_timeout="0s",
        )


def _event_row(event: ChatLogEvent) -> dict:
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
    usage = event.usage
    return {
        "user_id": event.user_id,
        "session_id": event.session_id,
        "app_version": event.app_version,
        "latency_ms": max(0, event.latency_ms),
        "event_id": event.event_id,
        "event_timestamp": event.event_timestamp.isoformat(),
        "question": event.question,
        "answer": event.answer,
        "sources_json": sources_json,
        "source_count": len(event.sources),
        "agents_used_json": json.dumps(event.agents_used, separators=(",", ":")),
        "status": event.status,
        "error_message": event.error_message,
        "input_tokens": max(0, usage.input_tokens) if usage is not None else None,
        "output_tokens": max(0, usage.output_tokens) if usage is not None else None,
        "total_tokens": max(0, usage.total_tokens) if usage is not None else None,
        "inference_ms": _optional_milliseconds(event.inference_ms),
        "citations_ms": _optional_milliseconds(event.citations_ms),
        "stage_timings_json": json.dumps(event.stage_ms, separators=(",", ":")) if event.stage_ms else None,
    }


def _optional_milliseconds(value):
    return max(0, value) if value is not None else None


def _parameter(name: str, value: str, parameter_type: str = "STRING"):
    try:
        from databricks.sdk.service.sql import StatementParameterListItem
    except ImportError:
        return {"name": name, "value": value, "type": parameter_type}
    return StatementParameterListItem(name=name, value=value, type=parameter_type)
