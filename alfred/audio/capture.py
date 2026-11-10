"""Microphone capture with voice-activity detection.

`Microphone.utterances()` yields one numpy float32 array per spoken phrase (speech start -> N ms of silence).
While Alfred is speaking the mic is muted so he doesn't hear himself.
"""
from __future__ import annotations

import collections
import queue
import threading
import time
from typing import Iterator

import numpy as np

FRAME_MS = 30  # webrtcvad supports 10/20/30 ms frames


class Microphone:
    def __init__(self, cfg: dict, gated: bool = False) -> None:
        """gated=True (hold-to-talk): audio is thrown away unless `capturing` is set - Alfred hears nothing
        while the key isn't held."""
        import sounddevice as sd  # imported lazily so tests run without audio hardware
        import webrtcvad

        a = cfg["audio"]
        self.sr = int(a["sample_rate"])
        self.frame_len = int(self.sr * FRAME_MS / 1000)
        self.silence_frames = max(1, int(a["silence_ms"] / FRAME_MS))
        self.max_frames = int(a["max_utterance_s"] * 1000 / FRAME_MS)
        self.vad = webrtcvad.Vad(int(a["vad_aggressiveness"]))
        self.muted = threading.Event()
        self.interrupt = threading.Event()
        self.gated = gated
        self.capturing = threading.Event()  # hold-to-talk: key is down, keep the audio
        self._frames: queue.Queue[bytes] = queue.Queue(maxsize=2000)
        self._stream = sd.RawInputStream(
            samplerate=self.sr,
            blocksize=self.frame_len,
            channels=1,
            dtype="int16",
            device=a.get("input_device"),
            callback=self._on_audio,
        )

    # sounddevice callback - runs on the audio thread
    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        if self.muted.is_set() or (self.gated and not self.capturing.is_set()):
            return
        try:
            self._frames.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()

    def flush(self) -> None:
        while not self._frames.empty():
            try:
                self._frames.get_nowait()
            except queue.Empty:
                break

    def raw_frames(self, timeout: float = 0.5) -> Iterator[bytes]:
        """Yield raw 30 ms int16 frames (used by openwakeword / porcupine backends)."""
        while True:
            try:
                yield self._frames.get(timeout=timeout)
            except queue.Empty:
                yield b""

    def record_held(self, released: threading.Event, max_s: float = 60.0) -> np.ndarray | None:
        """Collect audio from key-down until `released` is set (hold-to-talk). None if too short."""
        chunks: list[bytes] = []
        t0 = time.monotonic()
        while not released.is_set() and time.monotonic() - t0 < max_s:
            try:
                chunks.append(self._frames.get(timeout=0.05))
            except queue.Empty:
                pass
        time.sleep(0.15)  # grab the tail of the last word
        self.capturing.clear()
        while True:
            try:
                chunks.append(self._frames.get_nowait())
            except queue.Empty:
                break
        pcm = np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0
        return pcm if len(pcm) > self.sr * 0.3 else None

    def record_utterance(self, start_timeout_s: float | None = None) -> np.ndarray | None:
        """Block until one phrase has been spoken, return it as float32 [-1, 1].

        start_timeout_s: give up (return None) if no speech starts within this many seconds.
        """
        self.interrupt.clear()
        pre_roll: collections.deque[bytes] = collections.deque(maxlen=10)  # keep ~300 ms before speech
        voiced: list[bytes] = []
        speaking = False
        silent = 0
        t0 = time.monotonic()
        while True:
            if self.interrupt.is_set():
                self.interrupt.clear()
                return None
            try:
                frame = self._frames.get(timeout=0.5)
            except queue.Empty:
                frame = b""
            if not frame:
                if not speaking and start_timeout_s and time.monotonic() - t0 > start_timeout_s:
                    return None
                continue
            if len(frame) < self.frame_len * 2:
                continue
            is_speech = self.vad.is_speech(frame, self.sr)
            if not speaking:
                pre_roll.append(frame)
                if is_speech:
                    speaking = True
                    voiced.extend(pre_roll)
                elif start_timeout_s and time.monotonic() - t0 > start_timeout_s:
                    return None
                continue
            voiced.append(frame)
            silent = 0 if is_speech else silent + 1
            if silent >= self.silence_frames or len(voiced) >= self.max_frames:
                break
        pcm = np.frombuffer(b"".join(voiced), dtype=np.int16).astype(np.float32) / 32768.0
        return pcm
