"""Speech to text with faster-whisper (local, GPU when it works, CPU otherwise)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

# Words whisper often gets wrong in Roman's world - nudges recognition.
HOTWORDS = "Alfred, Claude, GEOScan, screenshot"


def register_nvidia_dlls() -> list[str]:
    """Windows: the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12 put their DLLs in
    site-packages/nvidia/*/bin, which Windows doesn't search. Add those folders so CTranslate2 can load
    cublas64_12.dll / cudnn*.dll. No-op elsewhere."""
    if sys.platform != "win32":
        return []
    added: list[str] = []
    for base in {Path(p) for p in sys.path if p and "site-packages" in p}:
        nv = base / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in nv.glob("*/bin"):
            if bin_dir.is_dir():
                try:
                    os.add_dll_directory(str(bin_dir))
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                added.append(str(bin_dir))
    return added


def _is_gpu_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("cublas", "cudnn", "cuda", "cudart", ".dll", "libcu"))


class Transcriber:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg["stt"]
        if self.cfg["device"] == "cuda":
            register_nvidia_dlls()
        self.device = self.cfg["device"]
        self.model = self._load(self.device, self.cfg["compute_type"])

    def _load(self, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        try:
            return WhisperModel(self.cfg["model"], device=device, compute_type=compute_type)
        except Exception as e:  # no CUDA available -> fall back to CPU
            if device == "cpu":
                raise
            print(f"[stt] GPU unavailable ({e}) - using the CPU instead", flush=True)
            self.device = "cpu"
            return WhisperModel(self.cfg["model"], device="cpu", compute_type="int8")

    def _run(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=HOTWORDS,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) < 1600:  # < 0.1 s
            return ""
        try:
            return self._run(audio)
        except RuntimeError as e:
            # The GPU model can load fine and still fail on first use when a CUDA DLL is missing
            # (e.g. "cublas64_12.dll is not found"). Switch to the CPU once and carry on.
            if self.device != "cpu" and _is_gpu_error(e):
                print(f"[stt] GPU speech-to-text failed ({e}) - switching to the CPU. "
                      "Fix: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12, or set stt.device: cpu", flush=True)
                self.device = "cpu"
                from faster_whisper import WhisperModel

                self.model = WhisperModel(self.cfg["model"], device="cpu", compute_type="int8")
                return self._run(audio)
            raise
