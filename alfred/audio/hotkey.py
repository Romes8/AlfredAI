"""Global trigger key: tap RIGHT ALT (Windows / Linux) or RIGHT OPTION (macOS) to make Alfred listen.

Uses pynput, which works on Windows and macOS.
- macOS: give your terminal / Python "Input Monitoring" (and "Accessibility") permission in
  System Settings > Privacy & Security, otherwise key presses are invisible to Alfred.
- Windows with a Danish/German/... layout: right Alt is AltGr. That's handled too.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

# Key names (pynput Key attribute names) accepted for each config value
KEY_ALIASES = {
    # right Alt on Windows/Linux == right Option on macOS (pynput calls both alt_r; AltGr layouts send alt_gr)
    "right_alt": {"alt_r", "alt_gr"},
    "right_option": {"alt_r", "alt_gr"},
    "right_ctrl": {"ctrl_r"},
    "right_cmd": {"cmd_r"},
    "f13": {"f13"},
}


def key_names(trigger: str) -> set[str]:
    return KEY_ALIASES.get(trigger, {trigger})


def is_solo_tap(pressed_at: float, released_at: float, other_key_used: bool, max_hold_s: float = 1.0) -> bool:
    """Only trigger on a clean tap - not when right Alt is used as AltGr to type @, {, [ etc."""
    return not other_key_used and 0 <= released_at - pressed_at <= max_hold_s


class TriggerKey:
    def __init__(self, trigger: str, on_trigger: Callable[[], None]) -> None:
        self.names = key_names(trigger)
        self.on_trigger = on_trigger
        self._down_at: float | None = None
        self._other_used = False
        self._listener = None
        self._lock = threading.Lock()

    def _name(self, key) -> str | None:
        return getattr(key, "name", None)  # special keys have .name ('alt_r'); characters don't

    def _on_press(self, key) -> None:
        with self._lock:
            if self._name(key) in self.names:
                if self._down_at is None:
                    self._down_at = time.monotonic()
                    self._other_used = False
            elif self._down_at is not None and self._name(key) not in ("ctrl_l", "ctrl"):
                # another key while holding right Alt -> it's an AltGr combo, not a trigger
                # (Windows sends a fake ctrl_l together with AltGr, so ignore that one)
                self._other_used = True

    def _on_release(self, key) -> None:
        fire = False
        with self._lock:
            if self._name(key) in self.names and self._down_at is not None:
                fire = is_solo_tap(self._down_at, time.monotonic(), self._other_used)
                self._down_at = None
        if fire:
            self.on_trigger()

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as e:  # no display / not installed
            print(f"[hotkey] trigger key unavailable: {e}")
            return False
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()
        return True

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
