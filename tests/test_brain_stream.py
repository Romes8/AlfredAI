import asyncio

from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock

from alfred.agent.brain import Brain


def delta(text):
    return StreamEvent(uuid="u", session_id="s", event={"type": "content_block_delta",
                                                         "delta": {"type": "text_delta", "text": text}},
                       parent_tool_use_id=None)


class FakeClient:
    def __init__(self, msgs):
        self.msgs = msgs

    async def query(self, text):
        pass

    async def set_model(self, m):
        pass

    async def receive_response(self):
        for m in self.msgs:
            yield m


def make_brain(msgs):
    b = Brain.__new__(Brain)
    b.bus, b.model, b.smart_model, b.triggers = None, "haiku", "sonnet", []
    b.client = FakeClient(msgs)
    return b


def result():
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id="s", total_cost_usd=0, usage={}, result="")


def test_speaks_sentence_by_sentence_without_duplicates():
    text = "Official site is colosseo.it, mate. Tickets are about 18 euros. Book ahead!"
    msgs = [delta("Official site is colosseo.it, "), delta("mate. Tickets are "), delta("about 18 euros. Book ahead!"),
            StreamEvent(uuid="u", session_id="s", event={"type": "content_block_stop"}, parent_tool_use_id=None),
            AssistantMessage(content=[TextBlock(text=text)], model="haiku"), result()]
    spoken = []

    async def on_text(t):
        spoken.append(t)

    full = asyncio.run(make_brain(msgs).ask("tickets?", on_text))
    assert spoken == ["Official site is colosseo.it, mate.", "Tickets are about 18 euros.", "Book ahead!"]
    assert full == text


def test_falls_back_to_full_text_without_stream_events():
    msgs = [AssistantMessage(content=[TextBlock(text="Sorted, mate.")], model="haiku"), result()]
    spoken = []

    async def on_text(t):
        spoken.append(t)

    asyncio.run(make_brain(msgs).ask("hi", on_text))
    assert spoken == ["Sorted, mate."]
