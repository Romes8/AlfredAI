"""Turn Claude's token stream into speakable sentences as early as possible.

Alfred starts talking after the first sentence arrives instead of waiting for the whole answer.
"""
from __future__ import annotations

import re

# end of a sentence: . ! ? (or : ;) followed by whitespace - but not "e.g." / "1.5" / "Mr."
_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+")
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|mr|mrs|ms|dr|st|no|approx|ca)\.$", re.I)
MIN_CHARS = 12   # don't speak tiny fragments like "Yo." on their own... unless it's all there is
MAX_CHARS = 220  # very long sentence without punctuation: speak at a comma so there's no long silence


class SentenceStreamer:
    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> list[str]:
        """Add streamed text, return any complete sentences ready to speak."""
        self.buf += delta
        out: list[str] = []
        while True:
            cut = self._find_cut()
            if cut is None:
                break
            sentence, self.buf = self.buf[:cut].strip(), self.buf[cut:].lstrip()
            if sentence:
                out.append(sentence)
        return out

    def flush(self) -> list[str]:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []

    def _find_cut(self) -> int | None:
        for m in _BOUNDARY.finditer(self.buf):
            head = self.buf[: m.start()]
            if len(head.strip()) < MIN_CHARS or _ABBREV.search(head):
                continue
            return m.end()
        if len(self.buf) > MAX_CHARS:
            comma = self.buf.rfind(", ", 0, MAX_CHARS)
            if comma > MIN_CHARS:
                return comma + 2
        return None
