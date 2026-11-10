import asyncio
from datetime import datetime, timedelta

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from alfred import usage


def result(cost, inp, out, cache_read=0, searches=0, window=200000):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id="s", total_cost_usd=cost,
                         usage={"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cache_read},
                         model_usage={"claude-haiku-5-5": {"webSearchRequests": searches, "contextWindow": window,
                                                           "costUSD": cost}}, result="")


def test_turn_from_result():
    t = usage.turn_from_result(result(0.0021, 1200, 80, cache_read=9000, searches=1), 10300, "haiku")
    assert (t.cost_usd, t.input_tokens, t.output_tokens, t.cache_read_tokens, t.web_searches, t.context_window) == \
        (0.0021, 1200, 80, 9000, 1, 200000)
    assert usage.context_from_usage({"input_tokens": 5, "cache_read_input_tokens": 100,
                                     "cache_creation_input_tokens": 20}) == 125


def test_summary_periods(tmp_path):
    f = tmp_path / "usage.jsonl"
    now = datetime(2026, 11, 10, 19, 0)
    for days_ago, cost in [(0, 0.01), (0, 0.02), (3, 0.05), (20, 1.0), (40, 2.0)]:
        usage.record(usage.Turn(ts=(now - timedelta(days=days_ago)).timestamp(), cost_usd=cost,
                                context_tokens=1500, context_window=200000), f)
    s = usage.summary(f, now)
    assert s["today"]["questions"] == 2 and abs(s["today"]["cost_usd"] - 0.03) < 1e-9
    assert s["last_7_days"]["questions"] == 3
    assert s["this_month"]["questions"] == 3          # Nov 1-10 (20 days ago was October)
    assert s["all_time"]["questions"] == 5
    assert "subscription" in s["note"]
    assert "Today" in usage.report(f) and "context" in usage.report(f)


def test_brain_logs_each_question(tmp_path, monkeypatch):
    from alfred.agent.brain import Brain

    monkeypatch.setattr(usage, "USAGE_FILE", tmp_path / "u.jsonl")
    monkeypatch.setattr(usage.record, "__defaults__", (tmp_path / "u.jsonl",))
    monkeypatch.setattr(usage.summary, "__defaults__", (tmp_path / "u.jsonl", None))

    class Client:
        async def query(self, t): pass
        async def set_model(self, m): pass
        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="Sorted.")], model="haiku",
                                   usage={"input_tokens": 300, "cache_read_input_tokens": 8000}, message_id="m1")
            yield result(0.0013, 300, 12, cache_read=8000)

    events = []

    class Bus:
        def emit(self, kind, **d): events.append((kind, d))

    b = Brain.__new__(Brain)
    b.cfg, b.bus, b.model, b.smart_model, b.triggers, b.client = {"usage": {}}, Bus(), "haiku", "sonnet", [], Client()

    async def on_text(t): pass

    asyncio.run(b.ask("hi", on_text))
    turns = usage.load(tmp_path / "u.jsonl")
    assert len(turns) == 1 and turns[0].cost_usd == 0.0013 and turns[0].context_tokens == 8300
    ev = dict(events)["usage"]
    assert ev["context"] == 8300 and ev["today_questions"] == 1
