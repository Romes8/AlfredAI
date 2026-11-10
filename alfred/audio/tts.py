"""Text to speech. Piper (free, local, good quality) with Windows' built-in voices as fallback."""
from __future__ import annotations

import re
from pathlib import Path


def clean_for_speech(text: str) -> str:
    """Strip markdown / urls so the voice doesn't read symbols out loud."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in (s.strip() for s in parts) if p]


class Speaker:
    def __init__(self, cfg: dict, mic=None) -> None:
        self.cfg = cfg["tts"]
        self.mic = mic  # muted while speaking
        self._piper = None
        self._engine = self.cfg["engine"]
        if self._engine == "piper":
            model = Path(self.cfg["piper_model"])
            if model.exists():
                from piper import PiperVoice

                self._piper = PiperVoice.load(str(model))
            else:
                print(f"[tts] Piper model not found at {model} - using Windows voices. See README to download one.")
                self._engine = "pyttsx3"

    def say(self, text: str) -> None:
        text = clean_for_speech(text)
        if not text:
            return
        if self.mic:
            self.mic.muted.set()
        try:
            if self._engine == "piper" and self._piper is not None:
                for sentence in split_sentences(text):
                    self._say_piper(sentence)
            else:
                self._say_pyttsx3(text)
        finally:
            if self.mic:
                self.mic.flush()
                self.mic.muted.clear()

    def _say_piper(self, text: str) -> None:
        import numpy as np
        import sounddevice as sd

        voice = self._piper
        if hasattr(voice, "synthesize_stream_raw"):  # piper-tts <= 1.2
            audio = b"".join(voice.synthesize_stream_raw(text, length_scale=1.0 / self.cfg.get("rate", 1.0)))
            sr = voice.config.sample_rate
        else:  # piper-tts >= 1.3
            chunks = list(voice.synthesize(text))
            audio = b"".join(c.audio_int16_bytes for c in chunks)
            sr = chunks[0].sample_rate if chunks else 22050
        pcm = np.frombuffer(audio, dtype=np.int16)
        sd.play(pcm, sr)
        sd.wait()

    def _say_pyttsx3(self, text: str) -> None:
        import pyttsx3

        eng = pyttsx3.init()
        eng.setProperty("rate", int(185 * self.cfg.get("rate", 1.0)))
        eng.say(text)
        eng.runAndWait()
