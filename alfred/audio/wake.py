"""Wake word detection.

Backends
- whisper:       transcribe each phrase and look for "Alfred". Zero setup. Bonus: "Alfred, what's this on my screen?"
                 works in ONE breath - the text after the wake word is used as the command.
- openwakeword:  custom "hey alfred" .onnx model, very light on CPU.
- porcupine:     custom "Hey Alfred" .ppn from the Picovoice console, lightest.
- none:          no wake word - only the trigger key.
The trigger key (right Alt on Windows / right Option on macOS) works with every backend.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass

import numpy as np


@dataclass
class WakeResult:
    command: str = ""  # text spoken after the wake word (whisper backend), may be empty
    held: bool = False  # hold-to-talk: record until the key is released


def find_wake(text: str, words: list[str]) -> WakeResult | None:
    """Return WakeResult if `text` contains a wake word; command = everything after it."""
    if not text:
        return None
    lowered = text.lower()
    best = None
    for w in words:
        m = re.search(r"\b" + re.escape(w.lower()) + r"\b", lowered)
        if m and (best is None or m.start() < best.start()):
            best = m
    if best is None:
        return None
    rest = text[best.end():]
    rest = re.sub(r"^[\s,.!?:;-]+", "", rest).strip()
    return WakeResult(command=rest)


class WakeListener:
    def __init__(self, cfg: dict, mic, transcriber) -> None:
        self.cfg = cfg
        self.mic = mic
        self.stt = transcriber
        w = cfg["wake"]
        self.backend = w["backend"]
        self.words = w["words"]
        self.hotkey_pressed = threading.Event()  # any press of the key (also used to approve permissions)
        self.hold = w.get("trigger_mode", "hold") == "hold"
        if self.hold:
            self.backend = "none"  # hold-to-talk = only the key, never ambient listening
        self.key_down = threading.Event()
        self.key_up = threading.Event()
        self.cancelled = False
        self.on_hold_start = None  # app hook: called the moment the key goes down (barge-in)
        self._setup_trigger_key(w.get("trigger_key"))
        self._oww = None
        self._porcupine = None
        if self.backend == "openwakeword":
            from openwakeword.model import Model

            self._oww = Model(wakeword_models=[w["openwakeword_model"]], inference_framework="onnx")
        elif self.backend == "porcupine":
            import pvporcupine

            self._porcupine = pvporcupine.create(
                access_key=os.environ[w["porcupine_access_key_env"]],
                keyword_paths=[w["porcupine_keyword_path"]],
            )

    def _setup_trigger_key(self, trigger: str | None) -> None:
        if not trigger:
            return
        from alfred.audio.hotkey import TriggerKey

        if self.hold:
            def down() -> None:
                self.cancelled = False
                self.key_up.clear()
                self.mic.capturing.set()  # start hearing NOW
                self.hotkey_pressed.set()
                self.key_down.set()
                if self.on_hold_start:
                    self.on_hold_start()

            def up() -> None:
                self.key_up.set()

            def cancel() -> None:  # AltGr typing, not talking
                self.cancelled = True
                self.key_up.set()

            self._trigger = TriggerKey(trigger, on_down=down, on_up=up, on_cancel=cancel)
        else:
            def fire() -> None:
                self.hotkey_pressed.set()
                self.mic.interrupt.set()  # cut off whatever the wake-word listener was recording

            self._trigger = TriggerKey(trigger, on_trigger=fire)
        self._trigger.start()

    def record_hold(self):
        """Hold-to-talk: audio from key-down to key-up (None if cancelled or too short)."""
        audio = self.mic.record_held(self.key_up)
        return None if self.cancelled else audio

    def reset_hold(self) -> None:
        """Forget a press that wasn't meant as talking (e.g. a tap used to approve something)."""
        self.key_down.clear()
        self.mic.capturing.clear()
        self.mic.flush()

    def wait(self) -> WakeResult:
        """Block until Alfred is summoned."""
        if self.hold:
            self.key_down.wait()
            self.key_down.clear()
            return WakeResult(held=True)
        if self.backend == "whisper":
            return self._wait_whisper()
        if self.backend == "none":
            self.hotkey_pressed.wait()
            self.hotkey_pressed.clear()
            self.mic.flush()
            return WakeResult()
        return self._wait_frames()

    def _wait_whisper(self) -> WakeResult:
        while True:
            if self.hotkey_pressed.is_set():
                self.hotkey_pressed.clear()
                self.mic.flush()
                return WakeResult()
            audio = self.mic.record_utterance(start_timeout_s=0.5)
            if audio is None:
                continue
            text = self.stt.transcribe(audio)
            hit = find_wake(text, self.words)
            if hit:
                return hit

    def _wait_frames(self) -> WakeResult:
        buf = b""
        for frame in self.mic.raw_frames():
            if self.hotkey_pressed.is_set():
                self.hotkey_pressed.clear()
                return WakeResult()
            if not frame:
                continue
            buf += frame
            if self._oww is not None:
                chunk = 1280 * 2  # 80 ms @16 kHz int16
                while len(buf) >= chunk:
                    pcm = np.frombuffer(buf[:chunk], dtype=np.int16)
                    buf = buf[chunk:]
                    scores = self._oww.predict(pcm)
                    if max(scores.values()) > 0.5:
                        self._oww.reset()
                        return WakeResult()
            elif self._porcupine is not None:
                n = self._porcupine.frame_length * 2
                while len(buf) >= n:
                    pcm = np.frombuffer(buf[:n], dtype=np.int16)
                    buf = buf[n:]
                    if self._porcupine.process(pcm) >= 0:
                        return WakeResult()
        return WakeResult()
