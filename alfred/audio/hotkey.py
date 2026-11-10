"""Global trigger key: tap RIGHT ALT (Windows / Linux) or RIGHT OPTION (macOS) to make Alfred listen.

Windows/Linux use pynput. macOS uses a tiny native Quartz event tap instead, because pynput's keyboard
listener crashes the process ("zsh: trace trap") on recent macOS when it runs off the main thread.
- macOS: give your terminal / Python "Input Monitoring" (and "Accessibility") permission in
  System Settings > Privacy & Security, otherwise key presses are invisible to Alfred.
- Windows with a Danish/German/... layout: right Alt is AltGr. That's handled too.
"""
from __future__ import annotations

import sys
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
    def __init__(self, trigger: str, on_trigger: Callable[[], None] | None = None,
                 on_down: Callable[[], None] | None = None, on_up: Callable[[], None] | None = None,
                 on_cancel: Callable[[], None] | None = None) -> None:
        """on_trigger: clean tap.  on_down / on_up: key held / released (hold-to-talk).
        on_cancel: another key was pressed while holding (AltGr typing) - throw the recording away."""
        self.names = key_names(trigger)
        self.on_trigger = on_trigger
        self.on_down, self.on_up, self.on_cancel = on_down, on_up, on_cancel
        self._down_at: float | None = None
        self._other_used = False
        self._listener = None
        self._lock = threading.Lock()

    def _name(self, key) -> str | None:
        return getattr(key, "name", None)  # special keys have .name ('alt_r'); characters don't

    def _on_press(self, key) -> None:
        call = None
        with self._lock:
            if self._name(key) in self.names:
                if self._down_at is None:
                    self._down_at = time.monotonic()
                    self._other_used = False
                    call = self.on_down
            elif self._down_at is not None and self._name(key) not in ("ctrl_l", "ctrl"):
                # another key while holding right Alt -> it's an AltGr combo, not a trigger
                # (Windows sends a fake ctrl_l together with AltGr, so ignore that one)
                if not self._other_used:
                    call = self.on_cancel
                self._other_used = True
        if call:
            call()

    def _on_release(self, key) -> None:
        fire = up = False
        with self._lock:
            if self._name(key) in self.names and self._down_at is not None:
                fire = is_solo_tap(self._down_at, time.monotonic(), self._other_used)
                up = not self._other_used
                self._down_at = None
        if up and self.on_up:
            self.on_up()
        if fire and self.on_trigger:
            self.on_trigger()

    def start(self) -> bool:
        if sys.platform == "darwin":
            return self._start_macos()
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

    # ------------------------------------------------------------------ macOS
    def _start_macos(self) -> bool:
        try:
            import Quartz  # pyobjc-framework-Quartz (installed with pynput on macOS)
        except Exception as e:
            print(f"[hotkey] trigger key unavailable (pyobjc Quartz missing): {e}")
            return False
        t = threading.Thread(target=self._run_macos_tap, args=(Quartz,), daemon=True, name="trigger-key")
        t.start()
        return True

    def _run_macos_tap(self, Q) -> None:  # noqa: N803
        def callback(proxy, etype, event, refcon):  # noqa: ARG001
            try:
                if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                    Q.CGEventTapEnable(tap, True)
                    return event
                keycode = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                if etype == Q.kCGEventFlagsChanged:
                    name = MAC_MODIFIER_KEYCODES.get(keycode)
                    if name is None:
                        if self._down_at is not None:
                            self._on_press(_Key("other_mod"))
                        return event
                    down = bool(Q.CGEventGetFlags(event) & MAC_DEVICE_FLAG[name])
                    (self._on_press if down else self._on_release)(_Key(name))
                elif etype == Q.kCGEventKeyDown:
                    self._on_press(_Key(MAC_PLAIN_KEYCODES.get(keycode)))
                elif etype == Q.kCGEventKeyUp:
                    name = MAC_PLAIN_KEYCODES.get(keycode)
                    if name:
                        self._on_release(_Key(name))
            except Exception as e:  # never let an exception escape into Quartz
                print(f"[hotkey] {e}")
            return event

        mask = (Q.CGEventMaskBit(Q.kCGEventFlagsChanged) | Q.CGEventMaskBit(Q.kCGEventKeyDown)
                | Q.CGEventMaskBit(Q.kCGEventKeyUp))
        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
                                 mask, callback, None)
        if tap is None:
            print("[hotkey] macOS blocked the key listener. Allow your terminal in System Settings > "
                  "Privacy & Security > Input Monitoring (and Accessibility), then restart it.")
            return
        source = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
        Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(tap, True)
        Q.CFRunLoopRun()


class _Key:
    def __init__(self, name: str | None) -> None:
        self.name = name


# macOS virtual keycodes for modifier keys and the device-specific flag bit that says "this one is down"
MAC_MODIFIER_KEYCODES = {61: "alt_r", 58: "alt_l", 62: "ctrl_r", 59: "ctrl_l", 54: "cmd_r", 55: "cmd_l",
                         60: "shift_r", 56: "shift_l"}
MAC_DEVICE_FLAG = {"alt_r": 0x40, "alt_l": 0x20, "ctrl_r": 0x2000, "ctrl_l": 0x01, "cmd_r": 0x10,
                   "cmd_l": 0x08, "shift_r": 0x04, "shift_l": 0x02}
MAC_PLAIN_KEYCODES = {105: "f13"}
