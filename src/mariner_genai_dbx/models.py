"""Typed application configuration and service results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class DirectRoute:
    """A slash command answered by its specialist endpoint without the Supervisor."""

    endpoint: str
    api: str  # "responses" (Responses API agents) or "chat" (ChatAgent endpoints)
    agent: str  # name recorded in agents_used and used for fallback source labels
    stream: bool = False  # stream the answer live (Responses agents that support streaming)


@dataclass(frozen=True)
class SupervisorConfig:
    workspace_host: str = field(repr=False)
    endpoint_name: str
    token: str | None = field(default=None, repr=False)
    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    request_timeout_seconds: int = 60
    direct_routes: tuple[tuple[str, DirectRoute], ...] = ()


@dataclass(frozen=True)
class VolumeCatalog:
    id: str
    label: str
    volume_path: str = field(repr=False)
    # Volume holding PDF copies of Word documents at the same relative path,
    # e.g. Lending/Loan Policy.docx -> <rendition_path>/Lending/Loan Policy.docx.pdf
    rendition_path: str | None = field(default=None, repr=False)


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
    inference_ms: int | None = None
    citations_ms: int | None = None


@dataclass(frozen=True)
class PendingAgentAnswer:
    """Completed model text with references still awaiting source validation."""

    answer: str
    source_labels: tuple[str, ...] = ()
    citation_references: tuple[dict, ...] | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    agents_used: tuple[str, ...] = ()
    inference_ms: int = 0

    @property
    def citations_pending(self) -> bool:
        return bool(self.source_labels or self.citation_references)


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
