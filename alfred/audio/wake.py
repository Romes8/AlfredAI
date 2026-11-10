"""Wake word detection.

Backends
- whisper:       transcribe each phrase and look for "Alfred". Zero setup. Bonus: "Alfred, what's this on my screen?"
                 works in ONE breath - the text after the wake word is used as the command.
- openwakeword:  custom "hey alfred" .onnx model, very light on CPU.
- porcupine:     custom "Hey Alfred" .ppn from the Picovoice console, lightest.
A push-to-talk hotkey works alongside any backend.
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
        self.hotkey_pressed = threading.Event()
        self._setup_hotkey(w.get("hotkey"))
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

    def _setup_hotkey(self, combo: str | None) -> None:
        if not combo:
            return
        try:
            import keyboard

            keyboard.add_hotkey(combo, self.hotkey_pressed.set)
        except Exception as e:  # needs admin on some systems / not available on Linux without root
            print(f"[wake] hotkey disabled: {e}")

    def wait(self) -> WakeResult:
        """Block until Alfred is summoned."""
        if self.backend == "whisper":
            return self._wait_whisper()
        return self._wait_frames()

    def _wait_whisper(self) -> WakeResult:
        while True:
            if self.hotkey_pressed.is_set():
                self.hotkey_pressed.clear()
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
