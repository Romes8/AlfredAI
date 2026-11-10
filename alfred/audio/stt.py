"""Speech to text with faster-whisper (local, GPU)."""
from __future__ import annotations

import numpy as np

# Words whisper often gets wrong in Roman's world - nudges recognition.
HOTWORDS = "Alfred, Claude, GEOScan, screenshot"


class Transcriber:
    def __init__(self, cfg: dict) -> None:
        from faster_whisper import WhisperModel

        s = cfg["stt"]
        try:
            self.model = WhisperModel(s["model"], device=s["device"], compute_type=s["compute_type"])
        except Exception:  # no CUDA available -> fall back to CPU
            self.model = WhisperModel(s["model"], device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) < 1600:  # < 0.1 s
            return ""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=HOTWORDS,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
