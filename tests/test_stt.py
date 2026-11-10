import numpy as np

from alfred.audio import stt as stt_mod


class GPUBroken:
    def transcribe(self, audio, **kw):
        raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")


class Seg:
    text = " hello mate "


class CPUFine:
    def transcribe(self, audio, **kw):
        return [Seg()], None


def test_falls_back_to_cpu_when_cuda_dll_missing(monkeypatch):
    t = stt_mod.Transcriber.__new__(stt_mod.Transcriber)
    t.cfg = {"model": "small.en", "device": "cuda", "compute_type": "float16"}
    t.device, t.model = "cuda", GPUBroken()
    import faster_whisper
    monkeypatch.setattr(faster_whisper, "WhisperModel", lambda *a, **k: CPUFine())
    assert t.transcribe(np.zeros(16000, dtype=np.float32)) == "hello mate"
    assert t.device == "cpu"


def test_non_gpu_errors_still_raise():
    t = stt_mod.Transcriber.__new__(stt_mod.Transcriber)
    t.cfg = {"model": "small.en", "device": "cpu", "compute_type": "int8"}

    class Broken:
        def transcribe(self, audio, **kw):
            raise RuntimeError("something else")

    t.device, t.model = "cpu", Broken()
    import pytest
    with pytest.raises(RuntimeError):
        t.transcribe(np.zeros(16000, dtype=np.float32))


def test_register_dlls_is_noop_off_windows():
    import sys
    if sys.platform != "win32":
        assert stt_mod.register_nvidia_dlls() == []
