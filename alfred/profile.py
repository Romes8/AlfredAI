"""Roman's details for filling in forms - kept in config.yaml under `profile:` (per machine, never committed).

Alfred fetches them with the get_my_details tool only when he's filling something in, so they're not sent to
Claude with every question. Anything that looks like a payment card, password, PIN, bank account or national ID
number is dropped - those you always type yourself.
"""
from __future__ import annotations

import re
from typing import Any

FORBIDDEN_KEYS = re.compile(r"(card|cvv|cvc|password|passwd|pin\b|iban|account[_ ]?number|bank|cpr|ssn|social|"
                            r"passport|national[_ ]?id|tax[_ ]?id|secret|token|security[_ ]?code)", re.I)
CARD_LIKE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        elif v not in (None, ""):
            out[key] = str(v)
    return out


def load_profile(cfg: dict) -> dict[str, str]:
    """Flattened, safe-to-share profile, e.g. {'name': 'Roman', 'address.city': 'Copenhagen'}."""
    clean: dict[str, str] = {}
    for k, v in _flatten(cfg.get("profile") or {}).items():
        if FORBIDDEN_KEYS.search(k) or CARD_LIKE.search(v):
            print(f"[profile] ignoring '{k}' - payment / password / ID details aren't shared with Alfred", flush=True)
            continue
        clean[k] = v
    return clean
