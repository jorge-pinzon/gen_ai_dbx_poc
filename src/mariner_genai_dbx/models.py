"""Typed application configuration and service results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SupervisorConfig:
    workspace_host: str = field(repr=False)
    endpoint_name: str
    token: str | None = field(default=None, repr=False)
    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    request_timeout_seconds: int = 60


@dataclass(frozen=True)
class VolumeCatalog:
    id: str
    label: str
    volume_path: str = field(repr=False)


@dataclass(frozen=True)
class CitationTableConfig:
    table_name: str
    domain: str
    document_title_column: str = "document_title"
    volume_path_column: str = "volume_path"
    page_number_column: str | None = "page_start"
    chunk_text_column: str = "chunk_text"
    page_number_pattern: str | None = None
    source_label_aliases: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Source:
    number: int
    label: str
    domain: str | None = None
    location: str | None = field(default=None, repr=False)
    url: str | None = field(default=None, repr=False)
    page: int | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class AgentAnswer:
    answer: str
    sources: tuple[Source, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    agents_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool


@dataclass(frozen=True)
class ConversationTurn:
    conversation_id: str
    request_id: str
    user_id: str = field(repr=False)
    created_at: datetime
    question: str = field(repr=False)
    answer: str = field(repr=False)
    sources: tuple[Source, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True)
class ConversationHistory:
    turns: tuple[ConversationTurn, ...] = ()
    version: int = 0
