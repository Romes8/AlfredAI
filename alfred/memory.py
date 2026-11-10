"""Alfred's long-term memory: a plain markdown file you can read and edit yourself.

    # Alfred's memory
    - [2026-11-10] Roman's girlfriend is called Anna
    - [2026-11-10] Prefers metric units

Loaded into Alfred's instructions at every start (and on "new chat"). Alfred adds lines with `remember` and
removes them with `forget`. Kept short on purpose: everything in it is sent to Claude with every question.
"""
from __future__ import annotations

import difflib
import re
import threading
import time
from pathlib import Path

from alfred.config import expand

HEADER = "# Alfred's memory\n\nThings Roman asked me to remember. Edit freely - one fact per line.\n\n"
LINE = re.compile(r"^\s*-\s*(?:\[(\d{4}-\d{2}-\d{2})\]\s*)?(.+?)\s*$")

# Never store secrets: passwords, API keys, tokens, card/bank numbers, ID numbers
SECRET_PATTERNS = [
    r"\bpass(word|wd|code)\b", r"\bpin\b", r"\bapi[ _-]?key\b", r"\bsecret\b", r"\btoken\b",
    r"\bsk-[A-Za-z0-9_-]{10,}", r"\bghp_[A-Za-z0-9]{20,}", r"\bpat-[a-z0-9-]{10,}", r"\bAKIA[0-9A-Z]{16}\b",
    r"\b(?:\d[ -]?){13,19}\b",  # card / account-like numbers
    r"\biban\b", r"\bcpr\b", r"\bssn\b", r"\bpassport\b",
]


def memory_path(cfg: dict) -> Path:
    m = cfg.get("memory", {})
    if m.get("path"):
        return expand(m["path"])
    return expand(cfg["agent"]["workspace"]) / "memory.md"


def looks_secret(text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in SECRET_PATTERNS)


class Memory:
    def __init__(self, path: Path, max_items: int = 200, max_chars: int = 6000) -> None:
        self.path = Path(path)
        self.max_items = max_items
        self.max_chars = max_chars
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ file
    def items(self) -> list[tuple[str, str]]:
        """[(date, text)] in file order."""
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            m = LINE.match(line)
            if m:
                out.append((m.group(1) or "", m.group(2)))
        return out

    def _write(self, items: list[tuple[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"- [{d}] {t}\n" if d else f"- {t}\n" for d, t in items)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(HEADER + body, encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------ actions
    def add(self, fact: str) -> dict:
        fact = re.sub(r"\s+", " ", (fact or "")).strip().lstrip("-").strip()
        if not fact:
            return {"saved": False, "message": "Nothing to remember."}
        if len(fact) > 300:
            return {"saved": False, "message": "Too long - remember one short fact at a time."}
        if looks_secret(fact):
            return {"saved": False, "message": "That looks like a password, key or number - not storing secrets."}
        with self._lock:
            items = self.items()
            for d, t in items:
                if t.lower() == fact.lower():
                    return {"saved": False, "message": "Already remembered."}
            if len(items) >= self.max_items:
                return {"saved": False, "message": f"Memory is full ({self.max_items} items) - forget something first."}
            items.append((time.strftime("%Y-%m-%d"), fact))
            self._write(items)
        return {"saved": True, "fact": fact}

    def forget(self, what: str) -> dict:
        q = (what or "").strip().lower()
        if not q:
            return {"removed": []}
        with self._lock:
            items = self.items()
            if q in ("everything", "all", "all of it"):
                self._write([])
                return {"removed": [t for _, t in items]}
            hits = [i for i, (_, t) in enumerate(items) if q in t.lower()]
            if not hits:
                texts = [t.lower() for _, t in items]
                close = difflib.get_close_matches(q, texts, n=1, cutoff=0.5)
                hits = [texts.index(close[0])] if close else []
            removed = [items[i][1] for i in hits]
            self._write([it for i, it in enumerate(items) if i not in hits])
        return {"removed": removed}

    def for_prompt(self) -> str:
        """The memory as it goes into Alfred's instructions (newest kept if it's too long)."""
        lines, total = [], 0
        for d, t in reversed(self.items()):
            line = f"- {t}" + (f" (noted {d})" if d else "")
            if total + len(line) > self.max_chars:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(reversed(lines))
