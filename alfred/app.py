"""Wires everything together: wake -> listen -> Claude -> speak, with voice-approved writes."""
from __future__ import annotations

import asyncio
import re
import sys

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
    hold = cfg["wake"].get("trigger_mode", "hold") == "hold"
    mic = Microphone(cfg, gated=hold)  # hold-to-talk: mic audio is dropped unless the key is held
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

    mode = cfg["permissions"].get("approval", "key")  # key | voice | both
    key_name = "right Option" if sys.platform == "darwin" else "right Alt"

    async def ask_hold(summary: str, detail: str) -> bool:  # noqa: ARG001
        """Hold-to-talk approval: a press of the key = yes. Doing nothing = no. The mic stays off."""
        bus.state("waiting_tap")
        wake.hotkey_pressed.clear()
        await say(f"{summary} Tap {key_name} to approve, or just leave it.")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if wake.hotkey_pressed.is_set():
                await asyncio.sleep(0.4)  # let the tap finish
                wake.hotkey_pressed.clear()
                wake.reset_hold()  # that press was a "yes", not the start of a new question
                await say("Sorted.")
                return True
            await asyncio.sleep(0.05)
        await say("Leaving it then.")
        return False

    async def ask(summary: str, detail: str) -> bool:
        """Approval. key: tap the trigger key = yes (a voice can't approve - a video or someone else in the room
        could say "yes"). voice: say yes/no. both: either. Saying "no" or silence always = no."""
        bus.state("waiting_confirm")
        how = {"key": f"Tap {key_name} to approve, or say no.",
               "voice": "Yes or no?",
               "both": f"Tap {key_name} or say yes. Or no."}[mode]
        wake.hotkey_pressed.clear()  # ignore taps from before the question
        await say(f"{summary} {how}")
        for attempt in range(2):
            # a tap while Alfred was still talking counts; a tap while listening cuts the recording short
            heard = "" if wake.hotkey_pressed.is_set() else await listen(timeout)
            if wake.hotkey_pressed.is_set():
                wake.hotkey_pressed.clear()
                if mode in ("key", "both"):
                    await say("Sorted.")
                    return True
            answer = parse_answer(heard)
            if answer == "no":
                await say("No worries, leaving it.")
                return False
            if answer == "yes" and mode in ("voice", "both"):
                await say("Sorted.")
                return True
            if answer == "show" and attempt == 0:
                bus.emit("permission", summary=summary, detail=detail, result="pending", expand=True)
                await say(f"It's up on the overlay. {how}")
                continue
            if answer == "yes" and mode == "key":
                await say(f"Need a tap on {key_name} for that one, mate.")
                continue
            if not heard:
                break  # silence = no
            if attempt == 0:
                await say(f"Didn't catch that. {how}")
        await say("I'll take that as a no.")
        return False

    gate = PermissionGate(PermissionPolicy(cfg), ask_hold if hold else ask, bus)
    server, names = build_server(cfg)
    brain = Brain(cfg, gate, server, names, bus)
    await brain.start()

    backend = cfg["wake"]["backend"]
    if hold:
        hint = f"hold {key_name} while you talk"
    else:
        hint = f"tap {key_name}" + ("" if backend == "none" else f" or say \"{name}\"")
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
            if woke.held:
                bus.state("listening")  # purple glow for exactly as long as the key is held
                audio = await asyncio.to_thread(wake.record_hold)
                bus.state("idle")
                command = (await asyncio.to_thread(stt.transcribe, audio)).strip() if audio is not None else ""
            elif not command:
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
