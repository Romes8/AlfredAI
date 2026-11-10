"""Text to speech - all free and local.

  kokoro  - most natural (default). Open-source Kokoro-82M model, ~340 MB, downloaded automatically on first use.
  piper   - lighter and faster, a bit more robotic.
  pyttsx3 - the operating system's built-in voices (fallback when nothing else is available).
"""
from __future__ import annotations

import re
import threading
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


KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_VOICES = {  # free voices in voices-v1.0.bin (English)
    "british_male": ["bm_george", "bm_lewis", "bm_daniel", "bm_fable"],
    "british_female": ["bf_emma", "bf_isabella", "bf_alice", "bf_lily"],
    "american_male": ["am_michael", "am_adam", "am_puck", "am_liam", "am_eric", "am_echo", "am_onyx", "am_fenrir"],
    "american_female": ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_nova", "af_river"],
}


def kokoro_lang(voice: str) -> str:
    return "en-gb" if voice.startswith("b") else "en-us"


def _download(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[tts] downloading {dest.name} (one time)...", flush=True)
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


class Speaker:
    def __init__(self, cfg: dict, mic=None) -> None:
        self.cfg = cfg["tts"]
        self.mic = mic  # muted while speaking
        self._piper = None
        self._engine = self.cfg["engine"]
        self.stopped = threading.Event()  # set by stop(): abandon whatever is being said
        self._pyttsx = None
        self._kokoro = None
        if self._engine == "kokoro":
            try:
                self._load_kokoro()
            except Exception as e:  # missing package / no internet for the first download
                print(f"[tts] Kokoro unavailable ({e}) - falling back to Piper", flush=True)
                self._engine = "piper"
        if self._engine == "piper":
            model = Path(self.cfg["piper_model"])
            if model.exists():
                from piper import PiperVoice

                self._piper = PiperVoice.load(str(model))
            else:
                print(f"[tts] Piper model not found at {model} - using Windows voices. See README to download one.")
                self._engine = "pyttsx3"

    def _load_kokoro(self) -> None:
        from kokoro_onnx import Kokoro

        model = Path(self.cfg.get("kokoro_model", "./models/kokoro-v1.0.onnx"))
        voices = Path(self.cfg.get("kokoro_voices", "./models/voices-v1.0.bin"))
        for f in (model, voices):
            if not f.exists():
                _download(KOKORO_URL + f.name, f)
        self._kokoro = Kokoro(str(model), str(voices))
        self.voice = self.cfg.get("voice", "bm_george")

    def stop(self) -> None:
        """Cut Alfred off mid-sentence (called from the key listener thread)."""
        self.stopped.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        if self._pyttsx is not None:
            try:
                self._pyttsx.stop()
            except Exception:
                pass
        if self.mic:
            self.mic.muted.clear()

    def say(self, text: str) -> None:
        text = clean_for_speech(text)
        if not text or self.stopped.is_set():
            return
        if self.mic and not self.mic.capturing.is_set():
            self.mic.muted.set()
        try:
            if self._engine == "kokoro" and self._kokoro is not None:
                self._say_kokoro(text)  # text is already one sentence when streaming
            elif self._engine == "piper" and self._piper is not None:
                for sentence in split_sentences(text):
                    if self.stopped.is_set():
                        break
                    self._say_piper(sentence)
            else:
                self._say_pyttsx3(text)
        finally:
            if self.mic:
                # don't throw away audio if the user is already holding the key to talk over Alfred
                if not self.mic.capturing.is_set():
                    self.mic.flush()
                self.mic.muted.clear()

    def _say_kokoro(self, text: str) -> None:
        import sounddevice as sd

        samples, sr = self._kokoro.create(text, voice=self.voice, speed=float(self.cfg.get("rate", 1.1)),
                                          lang=kokoro_lang(self.voice))
        if self.stopped.is_set():
            return
        sd.play(samples, sr)
        sd.wait()

    def _say_piper(self, text: str) -> None:
        import numpy as np
        import sounddevice as sd

        voice = self._piper
        if hasattr(voice, "synthesize_stream_raw"):  # piper-tts <= 1.2
            audio = b"".join(voice.synthesize_stream_raw(text, length_scale=1.0 / self.cfg.get("rate", 1.0)))
            sr = voice.config.sample_rate
        else:  # piper-tts >= 1.3 (rate was ignored here before - that's why he sounded slow)
            from piper import SynthesisConfig

            chunks = list(voice.synthesize(text, syn_config=SynthesisConfig(length_scale=1.0 / self.cfg.get("rate", 1.1))))
            audio = b"".join(c.audio_int16_bytes for c in chunks)
            sr = chunks[0].sample_rate if chunks else 22050
        pcm = np.frombuffer(audio, dtype=np.int16)
        sd.play(pcm, sr)
        sd.wait()

    def _say_pyttsx3(self, text: str) -> None:
        import pyttsx3

        eng = pyttsx3.init()
        self._pyttsx = eng
        eng.setProperty("rate", int(185 * self.cfg.get("rate", 1.1)))
        eng.say(text)
        eng.runAndWait()
        self._pyttsx = None
