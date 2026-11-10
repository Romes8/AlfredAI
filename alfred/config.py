"""Config loading: config.yaml merged over built-in defaults."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DENY_PATTERNS = [
    ".env", ".ssh", "id_rsa", "id_ed25519", "id_ecdsa", "credentials", "secret", ".aws", ".azure", ".gcloud",
    ".kube", "kubeconfig", ".pem", ".key", ".p12", ".pfx", ".crt", ".jks", "token", "password", "passwd",
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".git/config", ".docker/config.json", ".gnupg",
    ".keychain", "1password", "bitwarden", "wallet", ".tfstate", ".tfvars",
]

DEFAULTS: dict[str, Any] = {
    "name": "Alfred",
    "agent": {
        "model": "haiku",
        "smart_model": "sonnet",
        "smart_triggers": ["think hard", "think harder", "deep dive", "research", "take your time"],
        "max_turns": 12,
        "workspace": "~/Documents/Alfred",
        "allow_commands": False,
    },
    "permissions": {
        "readable_dirs": ["~/Documents/Alfred"],
        "writable_dirs": ["~/Documents/Alfred"],
        "confirm_timeout_s": 15,
        "approval": "key",
        "deny_patterns": DENY_PATTERNS,
    },
    "wake": {
        "backend": "whisper",
        "words": ["alfred", "alfie", "al fred", "alfredo"],
        "openwakeword_model": "./models/hey_alfred.onnx",
        "porcupine_keyword_path": "./models/hey_alfred_windows.ppn",
        "porcupine_access_key_env": "PICOVOICE_ACCESS_KEY",
        "trigger_key": "right_alt",
        "trigger_mode": "hold",
    },
    "audio": {
        "input_device": None,
        "sample_rate": 16000,
        "vad_aggressiveness": 2,
        "silence_ms": 800,
        "max_utterance_s": 20,
    },
    "stt": {"model": "small.en", "device": "cuda", "compute_type": "float16"},
    "tts": {"engine": "kokoro", "voice": "bm_lewis", "rate": 1.1,
            "kokoro_model": "./models/kokoro-v1.0.onnx", "kokoro_voices": "./models/voices-v1.0.bin",
            "piper_model": "./models/en_GB-alan-medium.onnx"},
    "apps": {"enabled": True, "auto_open": True},
    "overlay": {"enabled": True, "glow": True, "glow_thickness": 36, "glow_intensity": 0.8, "panel": True, "position": "top-right", "width": 420, "opacity": 0.85, "hide_after_s": 12},
    "links": {"enabled": True, "auto_open": False},
    "connectors": {},
    "screen": {"enabled": True, "max_width": 1280, "jpeg_quality": 70},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def expand(p: str | os.PathLike) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Per-machine config: --config path > $ALFRED_CONFIG > ./config.yaml (git-ignored) > built-in defaults."""
    path = Path(path or os.environ.get("ALFRED_CONFIG") or "config.yaml")
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULTS, data)
