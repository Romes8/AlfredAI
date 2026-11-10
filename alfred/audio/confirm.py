"""Parse a spoken yes / no answer. Strict on purpose: anything unclear counts as NO."""
from __future__ import annotations

import re

YES = {"yes", "yeah", "yep", "yup", "sure", "do it", "go ahead", "go for it", "confirm", "confirmed",
       "approve", "approved", "ok", "okay", "send it", "say less", "affirmative"}
NO = {"no", "nope", "nah", "don't", "do not", "stop", "cancel", "deny", "denied", "negative", "hold on", "wait"}
SHOW = {"show me", "what", "details", "explain"}


def parse_answer(text: str) -> str:
    """Return 'yes', 'no', 'show' or 'unclear'. 'No' wins over 'yes' if both appear."""
    t = re.sub(r"[^a-z' ]", " ", (text or "").lower())
    t = f" {re.sub(r'\s+', ' ', t).strip()} "

    def has(words: set[str]) -> bool:
        return any(f" {w} " in t for w in words)

    if has(NO):
        return "no"
    if has(YES):
        return "yes"
    if has(SHOW):
        return "show"
    return "unclear"
