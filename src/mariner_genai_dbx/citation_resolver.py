"""Extract Supervisor source labels and resolve them to approved documents."""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from threading import Lock, Thread

from .errors import CitationResolutionError
from .models import CitationTableConfig, Source

logger = logging.getLogger(__name__)

SOURCE_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?\*{0,2}Source\*{0,2}\s*:\s*(?P<label>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SOURCE_MATCH_STOP_WORDS = {
    "about", "after", "all", "and", "are", "for", "from", "has", "have",
    "including", "into", "must", "not", "that", "the", "their", "this",
    "was", "were", "what", "when", "will", "with",
}


def extract_source_labels(answer: str) -> tuple[str, ...]:
    labels = []
    seen = set()
    for match in SOURCE_LINE.finditer(answer):
        label = re.sub(
            r"^[*_`]+|[*_`]+$", "", match.group("label").strip()
        ).strip()
        key = label.casefold()
        if label and key not in seen:
            labels.append(label)
            seen.add(key)
    return tuple(labels)


def remove_source_lines(answer: str) -> str:
    """Remove model-emitted source lines after their labels are resolved."""
    if not isinstance(answer, str) or not answer:
        return answer
    cleaned = SOURCE_LINE.sub("", answer)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


class NullCitationResolver:
    """Temporary resolver until the three approved chunk tables are configured."""

    def resolve_labels(self, labels, answer=None):
        del labels, answer
        return ()

    def resolve_citations(self, citations):
        if citations:
            raise CitationResolutionError("Structured citation registry is not configured")
        return ()


class DatabricksCitationResolver:
    """Resolve model-emitted document labels through approved chunk tables."""

    def __init__(
        self,
        *,
        workspace_client,
        warehouse_id: str,
        tables: tuple[CitationTableConfig, ...],
        timeout_seconds: int = 60,
        clock=time.monotonic,
        cache_ttl_seconds: float = 60,
        cache_max_entries: int = 128,
        registry=None,
        preload_chunks: bool = False,
        preload_max_rows: int = 5000,
        max_stale_seconds: float = 600,
    ):
        if not warehouse_id:
            raise ValueError("warehouse_id is required")
        self._workspace_client = workspace_client
        self._warehouse_id = warehouse_id
        self._tables = tables
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_entries = cache_max_entries
        self._cache = OrderedDict()
        self._cache_lock = Lock()
        self._registry = registry
        # The approved chunk tables are small, so each worker can keep them in
        # memory and match labels without a warehouse query per answer.
        self._preload_chunks = preload_chunks
        self._preload_max_rows = preload_max_rows
        self._max_stale_seconds = max_stale_seconds
        self._chunks = None
        self._chunks_loaded_at = None
        self._chunks_refreshing = False
        self._chunks_lock = Lock()

    def start_background_refresh(self):
        if self._registry is not None:
            self._registry.start_background_refresh()
        if self._preload_chunks:
            self._refresh_chunks_in_background()

    def _refresh_chunks_in_background(self):
        # Called at the start of each chat, so a refresh overlaps model inference.
        with self._chunks_lock:
            fresh = (
                self._chunks_loaded_at is not None
                and self._clock() - self._chunks_loaded_at < self._cache_ttl_seconds
            )
            if fresh or self._chunks_refreshing:
                return
            self._chunks_refreshing = True
        Thread(target=self._refresh_chunks_quietly, name="citation-chunks", daemon=True).start()

    def _refresh_chunks_quietly(self):
        try:
            self._load_chunks()
        except Exception as error:
            logger.warning("Citation chunk refresh failed; error_type=%s", type(error).__name__)
        finally:
            with self._chunks_lock:
                self._chunks_refreshing = False

    def _load_chunks(self):
        rows = self._execute(_preload_statement(self._tables), [])
        if len(rows) > self._preload_max_rows:
            raise CitationResolutionError("Citation chunk tables exceed preload capacity")
        chunks = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6 or not isinstance(row[1], str):
                continue
            title = _normalized_title(row[1])
            chunks.append((title, _without_policy_suffix(title), row))
        with self._chunks_lock:
            self._chunks = tuple(chunks)
            self._chunks_loaded_at = self._clock()

    def _preloaded_chunks(self):
        """Return chunk rows no older than the staleness limit, loading them if needed."""
        with self._chunks_lock:
            if (self._chunks is not None
                    and self._clock() - self._chunks_loaded_at <= self._max_stale_seconds):
                return self._chunks
        try:
            self._load_chunks()
        except Exception as error:
            logger.warning(
                "Citation chunk preload unavailable; using per-label query; error_type=%s",
                type(error).__name__,
            )
            return None
        with self._chunks_lock:
            return self._chunks

    def chunk_rows(self):
        """Return the preloaded rows: (domain, title, volume path, page, chunk text, count)."""
        chunks = self._preloaded_chunks()
        if chunks is None:
            raise CitationResolutionError("Document text is unavailable")
        return [row for _title, _short_title, row in chunks]

    def resolve_citations(self, citations):
        if self._registry is None:
            if citations:
                raise CitationResolutionError("Structured citation registry is not configured")
            return ()
        return self._registry.resolve(citations)

    def resolve_labels(self, labels, answer=None) -> tuple[Source, ...]:
        resolved = []
        seen_paths = set()
        for label in tuple(labels)[:10]:
            if not isinstance(label, str) or not label.strip() or len(label) > 300:
                continue
            source_label = _canonical_source_label(label.strip(), self._tables)
            for match in self._resolve_label(source_label, answer):
                path_key = match["volume_path"].casefold()
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                resolved.append(
                    Source(
                        number=len(resolved) + 1,
                        label=match["document_title"],
                        domain=match["domain"] or None,
                        location=match["volume_path"],
                        page=match["page"],
                    )
                )
        return tuple(resolved)

    def _resolve_label(self, label: str, answer: str | None) -> list[dict]:
        if self._preload_chunks:
            chunks = self._preloaded_chunks()
            if chunks is not None:
                normalized = _normalized_label(label)
                policy_label = _without_policy_suffix(normalized)
                rows = [
                    row for title, policy_title, row in chunks
                    if _label_matches(title, policy_title, normalized, policy_label)
                ]
                return self._matches_from_rows(rows, answer)
        # Cache only approved document rows, never answers, signed URLs or
        # employee data. Page selection must run again for each answer.
        key = label.casefold()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] > self._clock():
                self._cache.move_to_end(key)
                rows = cached[1]
            else:
                self._cache.pop(key, None)
                rows = None
        if rows is None:
            rows = self._query_label(label)
            if rows and self._cache_ttl_seconds > 0 and self._cache_max_entries > 0:
                with self._cache_lock:
                    self._cache[key] = (
                        self._clock() + self._cache_ttl_seconds, rows
                    )
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._cache_max_entries:
                        self._cache.popitem(last=False)
        return self._matches_from_rows(rows, answer)

    def _query_label(self, label: str):
        return self._execute(
            _resolution_statement(self._tables),
            [_string_parameter("source_label", label)],
        )

    def _execute(self, statement: str, parameters: list):
        deadline = self._clock() + self._timeout_seconds
        try:
            response = self._workspace_client.statement_execution.execute_statement(
                statement=statement,
                warehouse_id=self._warehouse_id,
                parameters=parameters,
                wait_timeout="50s",
            )
            while _statement_state(response) in {"PENDING", "RUNNING"}:
                if self._clock() >= deadline:
                    raise CitationResolutionError("Citation query timed out")
                time.sleep(min(0.1, max(0, deadline - self._clock())))
                response = self._workspace_client.statement_execution.get_statement(
                    _field(response, "statement_id")
                )
        except CitationResolutionError:
            raise
        except Exception as error:
            raise CitationResolutionError("Citation query failed") from error

        if _statement_state(response) != "SUCCEEDED":
            raise CitationResolutionError("Citation query did not succeed")
        return _nested_field(response, "result", "data_array") or []

    @staticmethod
    def _matches_from_rows(rows, answer):
        matches_by_path = {}
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            domain, title, volume_path, page_value, chunk_text, _chunk_count = row[:6]
            if not isinstance(title, str) or not isinstance(volume_path, str):
                continue
            match = matches_by_path.setdefault(
                volume_path.casefold(),
                {
                    "domain": str(domain or ""),
                    "document_title": title,
                    "volume_path": volume_path,
                    "chunks": [],
                },
            )
            match["chunks"].append(
                (_positive_integer(page_value), str(chunk_text or ""))
            )

        matches = []
        for match in matches_by_path.values():
            chunks = match.pop("chunks")
            match["page"] = _best_supported_page(answer, chunks)
            matches.append(match)
        return matches


def _chunk_columns(table: CitationTableConfig) -> str:
    page_number = (
        f"TRY_CAST(`{table.page_number_column}` AS INT)"
        if table.page_number_column
        else (
            "TRY_CAST(REGEXP_EXTRACT("
            f"CAST(`{table.chunk_text_column}` AS STRING), "
            f"'{_sql_literal(table.page_number_pattern)}', 1) AS INT)"
            if table.page_number_pattern
            else "CAST(NULL AS INT)"
        )
    )
    return f"""
                '{_sql_literal(table.domain)}' AS domain,
                `{table.document_title_column}` AS document_title,
                `{table.volume_path_column}` AS volume_path,
                {page_number} AS page_number,
                LEFT(CAST(`{table.chunk_text_column}` AS STRING), 12000) AS chunk_text,
                1 AS chunk_count"""


def _preload_statement(tables: tuple[CitationTableConfig, ...]) -> str:
    return "\nUNION ALL\n".join(
        f"SELECT{_chunk_columns(table)}\n            "
        f"FROM `{table.table_name.replace('.', '`.`')}`"
        for table in tables
    )


def _resolution_statement(tables: tuple[CitationTableConfig, ...]) -> str:
    queries = []
    for table in tables:
        title_without_metadata = (
            "REGEXP_REPLACE("
            "REGEXP_REPLACE("
            f"REGEXP_REPLACE(LOWER(TRIM(`{table.document_title_column}`)), "
            "'\\\\.(pdf|docx?|xlsx?)$', ''), "
            "'[0-9]{4}\\\\s+', ''), "
            "'\\\\s+v[0-9]+', '')"
        )
        label_without_metadata = (
            "REGEXP_REPLACE("
            "REGEXP_REPLACE("
            "REGEXP_REPLACE(LOWER(TRIM(:source_label)), '\\\\.(pdf|docx?|xlsx?)', ''), "
            "'[0-9]{4}\\\\s+', ''), "
            "'\\\\s+v[0-9]+', '')"
        )
        # Knowledge Assistant citations use human-readable spaces, while some
        # ingestion pipelines store the same document title as an uppercase
        # filename stem with underscores. Normalize both forms before matching.
        normalized_title = (
            "TRIM(REGEXP_REPLACE("
            f"REGEXP_REPLACE({title_without_metadata}, '[_()-]+', ' '), "
            "'\\\\s+', ' '))"
        )
        normalized_label = (
            "TRIM(REGEXP_REPLACE("
            f"REGEXP_REPLACE({label_without_metadata}, '[_()-]+', ' '), "
            "'\\\\s+', ' '))"
        )
        normalized_policy_title = (
            f"REGEXP_REPLACE({normalized_title}, '\\\\s+policy$', '')"
        )
        normalized_policy_label = (
            f"REGEXP_REPLACE({normalized_label}, '\\\\s+policy$', '')"
        )
        queries.append(
            f"""
            SELECT{_chunk_columns(table)}
            FROM `{table.table_name.replace('.', '`.`')}`
            WHERE (
                {normalized_title} = {normalized_label}
                OR {normalized_policy_title} = {normalized_policy_label}
                -- Filename separators are normalized to spaces above. These
                -- boundary-aware prefix/suffix rules therefore cover labels
                -- such as "Document Title - Section Name" regardless of
                -- whether the agent used a hyphen, underscore, or whitespace.
                OR {normalized_label} LIKE CONCAT({normalized_title}, ' %')
                OR {normalized_label} LIKE CONCAT('% ', {normalized_title})
                OR {normalized_label} LIKE CONCAT({normalized_title}, ',%')
                OR {normalized_label} LIKE CONCAT({normalized_title}, ' - %')
                OR {normalized_label} LIKE CONCAT({normalized_title}, ' – %')
                OR {normalized_label} LIKE CONCAT({normalized_title}, ' — %')
                OR {normalized_label} LIKE CONCAT({normalized_title}, ':%')
                OR {normalized_label} LIKE CONCAT({normalized_title}, ' (%')
                OR {normalized_label} LIKE CONCAT('%, ', {normalized_title})
                OR {normalized_label} LIKE CONCAT('% - ', {normalized_title})
                OR {normalized_label} LIKE CONCAT('%: ', {normalized_title})
            )
            """.strip()
        )
    return "\nUNION ALL\n".join(queries)


# Python equivalents of the SQL normalization above, for preloaded chunk rows.
# re.ASCII keeps \s identical to Spark's Java regex whitespace class.
_TITLE_PDF_SUFFIX = re.compile(r"\.(pdf|docx?|xlsx?)$")
_LABEL_PDF = re.compile(r"\.(pdf|docx?|xlsx?)")
_YEAR = re.compile(r"[0-9]{4}\s+", re.ASCII)
_VERSION = re.compile(r"\s+v[0-9]+", re.ASCII)
_SEPARATORS = re.compile(r"[_()-]+")
_WHITESPACE = re.compile(r"\s+", re.ASCII)
_POLICY_SUFFIX = re.compile(r"\s+policy$", re.ASCII)


def _normalized(value: str, pdf_pattern) -> str:
    # Spark TRIM strips spaces only, not other whitespace.
    value = pdf_pattern.sub("", value.strip(" ").lower())
    value = _VERSION.sub("", _YEAR.sub("", value))
    return _WHITESPACE.sub(" ", _SEPARATORS.sub(" ", value)).strip(" ")


def _normalized_title(title: str) -> str:
    return _normalized(title, _TITLE_PDF_SUFFIX)


def _normalized_label(label: str) -> str:
    return _normalized(label, _LABEL_PDF)


def _without_policy_suffix(value: str) -> str:
    return _POLICY_SUFFIX.sub("", value)


def _label_matches(title: str, policy_title: str, label: str, policy_label: str) -> bool:
    """Same rules as the WHERE clause in _resolution_statement."""
    return (
        title == label
        or policy_title == policy_label
        or label.startswith((title + " ", title + ",", title + " - ", title + " – ",
                             title + " — ", title + ":", title + " ("))
        or label.endswith((" " + title, ", " + title, " - " + title, ": " + title))
    )


def _string_parameter(name: str, value: str):
    try:
        from databricks.sdk.service.sql import StatementParameterListItem
    except ImportError:
        return {"name": name, "value": value, "type": "STRING"}
    return StatementParameterListItem(name=name, value=value, type="STRING")


def _statement_state(response) -> str:
    state = _nested_field(response, "status", "state")
    state = getattr(state, "value", state)
    return str(state or "").upper().rsplit(".", 1)[-1]


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _nested_field(value, *names):
    for name in names:
        value = _field(value, name)
        if value is None:
            return None
    return value


def _positive_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _best_supported_page(answer: str | None, chunks: list[tuple[int | None, str]]):
    pages = {page for page, _text in chunks if page}
    if len(pages) == 1:
        return next(iter(pages))
    if not pages or not isinstance(answer, str) or not answer.strip():
        return None

    answer_tokens = _meaningful_tokens(answer)
    scores = {}
    tokens_by_page: dict[int, set[str]] = {}
    for page, chunk_text in chunks:
        if not page:
            continue
        chunk_tokens = _meaningful_tokens(chunk_text)
        tokens_by_page.setdefault(page, set()).update(chunk_tokens)
        score = len(answer_tokens & chunk_tokens)
        scores[page] = max(scores.get(page, 0), score)
    if not scores:
        return None
    highest_score = max(scores.values())
    winners = [page for page, score in scores.items() if score == highest_score]
    if highest_score <= 0:
        return None
    if len(winners) == 1:
        return winners[0]

    # When ordinary overlap ties, prefer the page matching terms that occur on
    # fewer pages in the document. This gives a specific acronym such as "PPO"
    # more weight than repeated words such as "plan", while retaining the
    # fail-closed behavior if distinctiveness also ties.
    page_count = len(tokens_by_page)
    token_page_frequency = {
        token: sum(token in page_tokens for page_tokens in tokens_by_page.values())
        for token in answer_tokens
    }
    distinctive_scores = {
        page: sum(
            page_count - token_page_frequency[token] + 1
            for token in answer_tokens & tokens_by_page[page]
        )
        for page in winners
    }
    highest_distinctive_score = max(distinctive_scores.values())
    distinctive_winners = [
        page
        for page, score in distinctive_scores.items()
        if score == highest_distinctive_score
    ]
    return distinctive_winners[0] if len(distinctive_winners) == 1 else None


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 2 and token not in SOURCE_MATCH_STOP_WORDS
    }


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _canonical_source_label(
    label: str, tables: tuple[CitationTableConfig, ...]
) -> str:
    normalized = label.casefold()
    for table in tables:
        for alias, canonical_label in table.source_label_aliases:
            if normalized == alias.casefold():
                return canonical_label
    return label
