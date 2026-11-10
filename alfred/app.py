"""Wires everything together: wake -> listen -> Claude -> speak, with voice-approved writes."""
from __future__ import annotations

import asyncio
import re

from alfred.agent.brain import Brain
from alfred.agent.permissions import PermissionGate, PermissionPolicy
from alfred.audio.confirm import parse_answer
from alfred.events import EventBus
from alfred.tools.server import build_server

RESET_PHRASES = ("new chat", "forget that", "start over", "fresh start")
CANCEL_PHRASES = ("never mind", "nevermind", "forget it", "cancel")


def _is(text: str, phrases: tuple[str, ...]) -> bool:
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    return any(t == p or t.startswith(p) for p in phrases)


# --------------------------------------------------------------------------- text mode
async def run_text(cfg: dict, bus: EventBus | None = None) -> None:
    """Keyboard chat - handy for testing without a mic."""
    bus = bus or EventBus()

    async def ask(summary: str, detail: str) -> bool:
        print(f"\n[{cfg['name']} wants permission] {summary}\n{detail}\n")
        ans = await asyncio.to_thread(input, "Approve? (y/n) > ")
        return ans.strip().lower() in ("y", "yes")

    gate = PermissionGate(PermissionPolicy(cfg), ask, bus)
    server, names = build_server(cfg)
    brain = Brain(cfg, gate, server, names, bus)
    await brain.start()
    print(f"{cfg['name']} is online (text mode). Type 'exit' to quit, 'new chat' to reset.\n")

    async def on_text(t: str) -> None:
        print(f"{cfg['name']}: {t}\n")

    try:
        while True:
            text = (await asyncio.to_thread(input, "You: ")).strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break
            if _is(text, RESET_PHRASES):
                await brain.reset()
                print(f"{cfg['name']}: Clean slate, mate.\n")
                continue
            await brain.ask(text, on_text)
    finally:
        await brain.stop()


# --------------------------------------------------------------------------- voice mode
async def run_voice(cfg: dict, bus: EventBus) -> None:
    from alfred.audio.capture import Microphone
    from alfred.audio.stt import Transcriber
    from alfred.audio.tts import Speaker
    from alfred.audio.wake import WakeListener

    name = cfg["name"]
    print(f"[{name}] loading speech models...")
    mic = Microphone(cfg)
    stt = Transcriber(cfg)
    speaker = Speaker(cfg, mic)
    wake = WakeListener(cfg, mic, stt)
    mic.start()

    async def say(text: str) -> None:
        bus.state("speaking")
        await asyncio.to_thread(speaker.say, text)

    async def listen(timeout_s: float) -> str:
        bus.state("listening")
        audio = await asyncio.to_thread(mic.record_utterance, timeout_s)
        if audio is None:
            return ""
        return (await asyncio.to_thread(stt.transcribe, audio)).strip()

    timeout = cfg["permissions"]["confirm_timeout_s"]

    async def ask(summary: str, detail: str) -> bool:
        bus.state("waiting_confirm")
        await say(summary)
        for attempt in range(2):
            answer = parse_answer(await listen(timeout))
            if answer == "yes":
                await say("Sorted.")
                return True
            if answer == "no":
                await say("No worries, leaving it.")
                return False
            if answer == "show" and attempt == 0:
                bus.emit("permission", summary=summary, detail=detail, result="pending", expand=True)
                await say("It's up on the overlay. Yes or no?")
                continue
            if attempt == 0:
                await say("Didn't catch that. Yes or no?")
        await say("I'll take that as a no.")
        return False

    gate = PermissionGate(PermissionPolicy(cfg), ask, bus)
    server, names = build_server(cfg)
    brain = Brain(cfg, gate, server, names, bus)
    await brain.start()

    import sys

    key = "right Option" if sys.platform == "darwin" else "right Alt"
    backend = cfg["wake"]["backend"]
    hint = f"tap {key}" + ("" if backend == "none" else f" or say \"{name}\"")
    print(f"[{name}] online - {hint}. The screen edge glows purple while I'm listening.")
    await say(f"{name}'s online. What's good?")

    async def on_text(t: str) -> None:
        bus.emit("reply", text=t)
        await say(t)

    try:
        while True:
            bus.state("idle")
            woke = await asyncio.to_thread(wake.wait)
            command = woke.command
            if not command:
                command = await listen(6)  # purple edge glow = listening, no need to talk
            if not command:
                continue
            bus.emit("heard", text=command)
            print(f"You: {command}")
            if _is(command, CANCEL_PHRASES):
                await say("All good.")
                continue
            if _is(command, RESET_PHRASES):
                await brain.reset()
                await say("Clean slate, mate.")
                continue
            bus.state("thinking")
            try:
                reply = await brain.ask(command, on_text)
                print(f"{name}: {reply}\n")
            except Exception as e:  # keep Alfred alive whatever happens
                bus.emit("error", text=str(e))
                await say("Ah, something broke on my side. Check the console.")
                print(f"[{name}] error: {e}")
    finally:
        await brain.stop()
        mic.stop()
