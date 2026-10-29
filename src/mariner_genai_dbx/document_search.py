"""Keyword search inside the approved document chunks, for the document reader.

Searches the chunk text the citation resolver already preloads, so a search
adds no Vector Search or model call. Results point at a document page (a sheet
number for spreadsheets), with a short snippet around the first match.
"""

from __future__ import annotations

import re

MAX_RESULTS = 20
SNIPPET_BEFORE = 80
SNIPPET_AFTER = 180

_TAGS = re.compile(r"<[^>]+>")
_WORDS = re.compile(r"\w+")


class DocumentTextSearch:
    def __init__(self, resolver):
        self._resolver = resolver

    def search(self, query: str) -> list[dict]:
        return search_chunks(self._resolver.chunk_rows(), query)


def search_chunks(rows, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Return the best match per document page, ranked by exact phrase, then term count.

    Every query word must appear in the chunk. Single-letter words (the "E" in
    "E-Form") are ignored unless the query has nothing else.
    """
    phrase = " ".join(query.casefold().split())
    words = _WORDS.findall(phrase)
    terms = [word for word in words if len(word) > 1] or words
    if not terms:
        return []
    best: dict[tuple[str, int | None], dict] = {}
    for row in rows:
        volume_path, title, page, text = row[2], row[1], row[3], row[4]
        if not isinstance(volume_path, str) or not isinstance(text, str):
            continue
        # Word chunks keep parsed tables as HTML; search and show plain text.
        flat = " ".join(_TAGS.sub(" ", text).split())
        lowered = flat.casefold()
        if not all(term in lowered for term in terms):
            continue
        phrase_at = lowered.find(phrase)
        at = phrase_at if phrase_at >= 0 else min(lowered.find(term) for term in terms)
        score = (phrase_at >= 0, sum(lowered.count(term) for term in terms))
        key = (volume_path, page)
        if key in best and best[key]["score"] >= score:
            continue
        start, end = max(0, at - SNIPPET_BEFORE), at + SNIPPET_AFTER
        best[key] = {
            "score": score,
            "volumePath": volume_path,
            "title": title,
            "page": page,
            "snippet": ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else ""),
        }
    ranked = sorted(best.values(), key=lambda hit: (-hit["score"][0], -hit["score"][1],
                                                    str(hit["title"]).casefold(), hit["page"] or 0))
    return [{k: v for k, v in hit.items() if k != "score"} for hit in ranked[:limit]]
