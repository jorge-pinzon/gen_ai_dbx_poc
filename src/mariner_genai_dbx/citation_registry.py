"""Validate structured citations against approved, versioned document metadata."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from pathlib import PurePosixPath

from .citation_resolver import _nested_field, _statement_state, _field, _string_parameter
from .errors import CitationResolutionError
from .models import Source

logger = logging.getLogger(__name__)
FIELDS = ("document_id", "document_version", "chunk_id", "document_title")
COLUMNS = (
    "document_id, document_version, chunk_id, document_title, domain, "
    "source_volume_path, page_start, page_end"
)


def validate_citations(citations):
    if not isinstance(citations, list) or len(citations) > 10:
        raise CitationResolutionError("Invalid structured citation list")
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {*FIELDS, "page"}:
            raise CitationResolutionError("Invalid structured citation fields")
        if any(not isinstance(citation[f], str) or not citation[f].strip()
               or len(citation[f]) > 300 for f in FIELDS):
            raise CitationResolutionError("Invalid structured citation identifiers")
        if type(citation["page"]) is not int or citation["page"] < 1:
            raise CitationResolutionError("Invalid structured citation page")
    return citations


def _key(citation):
    return tuple(citation[f] for f in FIELDS[:3])


class CitationRegistry:
    """One cache per configured workspace principal and approved Volume set.

    Only shared policy metadata belongs here. Entries expire; stale data is
    never served after refresh failures. Unknown references fail closed.
    """

    def __init__(self, *, workspace_client, warehouse_id, table_name,
                 volume_roots, ttl_seconds=60, timeout_seconds=10,
                 max_entries=10000, idle_seconds=900, clock=time.monotonic,
                 sleep=time.sleep):
        if not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+", table_name):
            raise ValueError("Registry table must be fully qualified")
        if not volume_roots or min(ttl_seconds, timeout_seconds, max_entries) <= 0:
            raise ValueError("Registry requires approved roots and positive limits")
        self._client = workspace_client
        self._warehouse = warehouse_id
        self._table = "`" + table_name.replace(".", "`.`") + "`"
        self._roots = tuple(root.rstrip("/") + "/" for root in volume_roots)
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._max_entries = max_entries
        self._idle_seconds = idle_seconds
        self._clock = clock
        self._sleep = sleep
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._worker = None
        self._last_used = clock()

    def start_background_refresh(self):
        # Lazy startup: safe for Gunicorn preload; retrieval overlaps inference.
        with self._lock:
            self._last_used = self._clock()
            if self._worker is None:
                self._worker = threading.Thread(target=self._refresh_loop,
                                                name="citation-registry", daemon=True)
                self._worker.start()

    def _refresh_loop(self):
        # Stop refreshing once chats go quiet so the warehouse can auto-stop;
        # the next chat restarts the loop, and expired entries are re-read on demand.
        while True:
            try:
                self.warm()
            except Exception as error:
                logger.warning("Citation registry refresh failed; error_type=%s",
                               type(error).__name__)
            self._sleep(self._ttl / 2)
            with self._lock:
                if self._clock() - self._last_used > self._idle_seconds:
                    self._worker = None
                    return

    def warm(self):
        rows = self._query(f"SELECT {COLUMNS} FROM {self._table} LIMIT {self._max_entries + 1}", [])
        if len(rows) > self._max_entries:
            raise CitationResolutionError("Registry exceeds preload capacity")
        entries = self._entries(rows)
        with self._lock:
            expires = self._clock() + self._ttl
            self._cache = OrderedDict((key, (expires, value)) for key, value in entries.items())

    def resolve(self, citations):
        validate_citations(citations)
        if not citations:
            return ()
        requested = {_key(c): c for c in citations}
        found = {}
        with self._lock:
            for key in requested:
                entry = self._cache.get(key)
                if entry is not None and entry[0] > self._clock():
                    found[key] = entry[1]
                    self._cache.move_to_end(key)
                else:
                    self._cache.pop(key, None)
        missing = [key for key in requested if key not in found]
        if missing:
            clauses, parameters = [], []
            for i, key in enumerate(missing):
                clauses.append("(" + " AND ".join(
                    f"{field} = :c{i}_{j}" for j, field in enumerate(FIELDS[:3])) + ")")
                parameters.extend(_string_parameter(f"c{i}_{j}", value)
                                  for j, value in enumerate(key))
            rows = self._query(f"SELECT {COLUMNS} FROM {self._table} WHERE "
                               + " OR ".join(clauses) + " LIMIT 101", parameters)
            if len(rows) > 100:
                raise CitationResolutionError("Ambiguous registry references")
            fetched = self._entries(rows)
            found.update({key: value for key, value in fetched.items() if key in requested})
            with self._lock:
                expires = self._clock() + self._ttl
                for key, value in fetched.items():
                    if key in requested:
                        self._cache[key] = (expires, value)
                while len(self._cache) > self._max_entries:
                    self._cache.popitem(last=False)
        sources, seen = [], set()
        for citation in citations:
            record = found.get(_key(citation))
            if (record is None or record[3] != citation["document_title"]
                    or not record[6] <= citation["page"] <= record[7]):
                raise CitationResolutionError("Citation does not match approved metadata")
            identity = (record[5], citation["page"])
            if identity not in seen:
                seen.add(identity)
                sources.append(Source(number=len(sources) + 1, label=record[3],
                                      domain=record[4], location=record[5], page=citation["page"]))
        return tuple(sources)

    def _entries(self, rows):
        entries = {}
        for row in rows:
            if (not isinstance(row, (list, tuple)) or len(row) != 8
                    or any(not isinstance(v, str) or not v for v in row[:6])):
                raise CitationResolutionError("Invalid registry metadata")
            path = row[5]
            if (not path.startswith(self._roots) or ".." in PurePosixPath(path).parts
                    or "\\" in path or "\x00" in path or not path.lower().endswith(".pdf")):
                raise CitationResolutionError("Registry document outside approved Volumes")
            try:
                start, end = int(row[6]), int(row[7])
            except (TypeError, ValueError) as error:
                raise CitationResolutionError("Invalid registry page range") from error
            if start < 1 or end < start:
                raise CitationResolutionError("Invalid registry page range")
            record = tuple(row[:6]) + (start, end)
            key = tuple(row[:3])
            if key in entries and entries[key] != record:
                raise CitationResolutionError("Conflicting registry records")
            entries[key] = record
        return entries

    def _query(self, statement, parameters):
        deadline = self._clock() + self._timeout
        statement_id = None
        try:
            response = self._client.statement_execution.execute_statement(
                statement=statement, warehouse_id=self._warehouse,
                parameters=parameters, wait_timeout="10s")
            statement_id = _field(response, "statement_id")
            while _statement_state(response) in {"PENDING", "RUNNING"}:
                if self._clock() >= deadline:
                    if statement_id:
                        self._client.statement_execution.cancel_execution(statement_id)
                    raise CitationResolutionError("Registry query timed out")
                time.sleep(0.1)
                response = self._client.statement_execution.get_statement(statement_id)
            if (_statement_state(response) != "SUCCEEDED"
                    or _nested_field(response, "manifest", "truncated")
                    or _nested_field(response, "result", "next_chunk_index") is not None):
                raise CitationResolutionError("Registry query incomplete or failed")
            return _nested_field(response, "result", "data_array") or []
        except CitationResolutionError:
            raise
        except Exception as error:
            raise CitationResolutionError("Registry query failed") from error
