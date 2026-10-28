"""Checked live preview of an answer while it is still being generated.

The final answer is always checked in full and replaces the preview. The
preview only shows text that has already passed the same output checks:

- whole lines only, at least ``hold`` characters behind the newest text, so a
  pattern split across chunks is complete before its line is shown;
- personal data masked, and the masked lines must stay unchanged when the
  rest of the current text is masked too;
- any blocked category stops the preview and clears what was shown;
- Source lines and structured JSON answers are never previewed.

A complete intermediate result (a data table from a tool) can be shown with
``interim`` until the answer starts streaming; it passes the same checks and is
cleared by the first previewed answer text or a reset.
"""

from __future__ import annotations

from .citation_resolver import SOURCE_LINE

PREVIEW_HOLD_CHARACTERS = 200
_STRUCTURED_PREFIXES = ("{", "```json")


class LivePreview:
    def __init__(self, *, check, mask, hold=PREVIEW_HOLD_CHARACTERS):
        self._check = check  # text -> (filtered_text, categories, blocked)
        self._mask = mask  # text -> text with personal data masked
        self._hold = hold
        self._raw = ""
        self._shown = ""  # answer text on screen
        self._interim = False  # an intermediate result is on screen instead
        self._stopped = False

    def interim(self, text: str) -> list[tuple[str, dict]]:
        """Show a complete, checked intermediate result until the answer preview has text."""
        if self._stopped or self._shown or not text.strip() or self._check(text)[2]:
            return []
        out = self._clear()
        self._interim = True
        return out + [("delta", {"text": self._mask(text)})]

    def feed(self, delta: str) -> list[tuple[str, dict]]:
        """Add model text; return the SSE events to send (delta or preview_reset)."""
        if self._stopped or not delta:
            return []
        out = self._feed(delta)
        if self._interim and any(event == "delta" for event, _ in out):
            self._interim = False  # the answer replaces the intermediate result
            return [("preview_reset", {})] + out
        return out

    def _feed(self, delta):
        self._raw += delta
        start = self._raw.lstrip()
        if any(start.startswith(prefix) for prefix in _STRUCTURED_PREFIXES):
            return self._stop()
        if len(start) < len(_STRUCTURED_PREFIXES[-1]) and any(
                prefix.startswith(start) for prefix in _STRUCTURED_PREFIXES):
            return []  # could still become a structured answer
        if self._check(self._raw)[2]:
            return self._stop()
        cut = self._raw.rfind("\n", 0, max(0, len(self._raw) - self._hold) + 1)
        if cut < 0:
            return []
        masked = self._mask(self._raw[: cut + 1])
        if not self._mask(self._raw).startswith(masked):
            return []  # a masked value spans the cut; wait for more text
        visible = "".join(
            line for line in masked.splitlines(keepends=True)
            if not SOURCE_LINE.fullmatch(line.rstrip("\n"))
        )
        if not visible.startswith(self._shown) or not visible[len(self._shown):].strip():
            return []
        added, self._shown = visible[len(self._shown):], visible
        return [("delta", {"text": added})]

    def reset(self) -> list[tuple[str, dict]]:
        """The streamed text was not the final answer; clear it and start again."""
        self._raw = ""
        if self._stopped or not self._shown:
            return []  # an intermediate result stays until the answer streams
        return self._clear()

    def _stop(self):
        self._stopped = True
        return self._clear()

    def _clear(self):
        if not self._shown and not self._interim:
            return []
        self._shown, self._interim = "", False
        return [("preview_reset", {})]


def tidy_table(text: str) -> str | None:
    """A Genie result table made readable: no row-number column, no midnight times.

    Returns None when the text is not a Markdown table.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2 or not all(line.startswith("|") and line.endswith("|") for line in lines):
        return None
    rows = [line[1:-1].split("|") for line in lines]
    if rows[0][0].strip() == "":  # pandas-style index column
        rows = [row[1:] for row in rows]
    cells = lambda row: [cell.strip().removesuffix(" 00:00:00") for cell in row]
    return "\n".join("| " + " | ".join(cells(row)) + " |" for row in rows)
