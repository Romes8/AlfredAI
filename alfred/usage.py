"""Usage & cost tracking.

Every question is logged to ~/.alfred/usage.jsonl: tokens, web searches, the model, the context size and the cost.
The cost is the SDK's API-price ESTIMATE (`total_cost_usd`). On a Pro/Max subscription you aren't billed per
question - it shows how much of your plan's usage Alfred eats, in API-dollar terms.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

USAGE_FILE = Path.home() / ".alfred" / "usage.jsonl"


@dataclass
class Turn:
    ts: float = field(default_factory=time.time)
    model: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_searches: int = 0
    context_tokens: int = 0  # how full the conversation is (what gets re-sent with the next question)
    context_window: int = 0


def turn_from_result(msg, context_tokens: int, model: str) -> Turn:
    """Build a Turn from the SDK's ResultMessage (cost + usage for THIS question)."""
    u = msg.usage or {}
    t = Turn(model=model, cost_usd=float(msg.total_cost_usd or 0.0),
             input_tokens=int(u.get("input_tokens", 0) or 0), output_tokens=int(u.get("output_tokens", 0) or 0),
             cache_read_tokens=int(u.get("cache_read_input_tokens", 0) or 0),
             cache_write_tokens=int(u.get("cache_creation_input_tokens", 0) or 0), context_tokens=context_tokens)
    for name, mu in (msg.model_usage or {}).items():
        t.web_searches += int(mu.get("webSearchRequests", 0) or 0)
        t.context_window = max(t.context_window, int(mu.get("contextWindow", 0) or 0))
        t.model = t.model or name
    return t


def context_from_usage(usage: dict | None) -> int:
    """Prompt size of one model call = how much context the conversation currently takes."""
    u = usage or {}
    return int(u.get("input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0) + \
        int(u.get("cache_creation_input_tokens", 0) or 0)


def record(turn: Turn, path: Path = USAGE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(turn)) + "\n")


def load(path: Path = USAGE_FILE) -> list[Turn]:
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(Turn(**json.loads(line)))
            except (ValueError, TypeError):
                continue
    except FileNotFoundError:
        pass
    return out


def _total(turns: list[Turn]) -> dict:
    return {"questions": len(turns), "cost_usd": round(sum(t.cost_usd for t in turns), 4),
            "tokens_in": sum(t.input_tokens + t.cache_read_tokens + t.cache_write_tokens for t in turns),
            "tokens_out": sum(t.output_tokens for t in turns), "web_searches": sum(t.web_searches for t in turns)}


def summary(path: Path = USAGE_FILE, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    turns = load(path)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week = start_today - timedelta(days=6)
    start_month = start_today.replace(day=1)

    def since(d: datetime) -> list[Turn]:
        return [t for t in turns if t.ts >= d.timestamp()]

    last = turns[-1] if turns else None
    return {
        "today": _total(since(start_today)), "last_7_days": _total(since(start_week)),
        "this_month": _total(since(start_month)), "all_time": _total(turns),
        "conversation_context_tokens": last.context_tokens if last else 0,
        "context_window": last.context_window if last else 0,
        "note": "Costs are API-price estimates. On a Claude Pro/Max subscription you're not billed per question - "
                "this is how much of your plan's usage Alfred uses.",
    }


def fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def report(path: Path = USAGE_FILE) -> str:
    s = summary(path)
    lines = ["Alfred usage (cost = API-price estimate; on a subscription it counts toward your plan, not billed)", ""]
    for label, key in (("Today", "today"), ("Last 7 days", "last_7_days"), ("This month", "this_month"),
                       ("All time", "all_time")):
        t = s[key]
        lines.append(f"  {label:<12} {t['questions']:>4} questions   ${t['cost_usd']:>7.3f}   "
                     f"{fmt_tokens(t['tokens_in']):>7} in / {fmt_tokens(t['tokens_out']):>6} out   "
                     f"{t['web_searches']} searches")
    ctx, win = s["conversation_context_tokens"], s["context_window"]
    if ctx:
        pct = f" ({ctx * 100 / win:.0f}% of {fmt_tokens(win)})" if win else ""
        lines += ["", f"  Current conversation: {fmt_tokens(ctx)} tokens of context{pct} - say \"new chat\" to reset"]
    return "\n".join(lines)
