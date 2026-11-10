from alfred.audio.hotkey import is_solo_tap, key_names


def test_right_alt_maps_to_right_option_and_altgr():
    assert key_names("right_alt") == {"alt_r", "alt_gr"}
    assert key_names("right_option") == {"alt_r", "alt_gr"}


def test_tap_fires_but_altgr_combo_and_long_hold_dont():
    assert is_solo_tap(0.0, 0.2, other_key_used=False)
    assert not is_solo_tap(0.0, 0.2, other_key_used=True)   # AltGr+2 typing '@'
    assert not is_solo_tap(0.0, 2.5, other_key_used=False)  # held down for ages


class K:
    def __init__(self, name):
        self.name = name


def test_trigger_key_sequence():
    from alfred.audio.hotkey import TriggerKey

    fired = []
    t = TriggerKey("right_alt", lambda: fired.append(1))
    t._on_press(K("alt_r")); t._on_release(K("alt_r"))
    assert fired == [1]
    # AltGr + a character key = typing, not a trigger (Windows also sends a fake ctrl_l)
    t._on_press(K("ctrl_l")); t._on_press(K("alt_gr")); t._on_press(K(None)); t._on_release(K("alt_gr"))
    assert fired == [1]
    t._on_press(K("alt_gr")); t._on_release(K("alt_gr"))
    assert fired == [1, 1]


def test_macos_modifier_tables_cover_triggers():
    from alfred.audio.hotkey import MAC_DEVICE_FLAG, MAC_MODIFIER_KEYCODES

    assert MAC_MODIFIER_KEYCODES[61] == "alt_r"  # right Option
    for name in MAC_MODIFIER_KEYCODES.values():
        assert name in MAC_DEVICE_FLAG


def test_hold_to_talk_callbacks():
    from alfred.audio.hotkey import TriggerKey

    events = []
    t = TriggerKey("right_alt", on_down=lambda: events.append("down"), on_up=lambda: events.append("up"),
                   on_cancel=lambda: events.append("cancel"))
    t._on_press(K("alt_r")); t._on_press(K("alt_r"))  # key auto-repeat must not re-trigger
    t._on_release(K("alt_r"))
    assert events == ["down", "up"]
    events.clear()
    t._on_press(K("alt_gr")); t._on_press(K(None)); t._on_release(K("alt_gr"))  # AltGr typing
    assert events == ["down", "cancel"]


def test_gated_mic_records_only_while_held():
    import threading

    import numpy as np

    from alfred.audio.capture import Microphone

    mic = Microphone.__new__(Microphone)  # no audio hardware in CI
    import queue
    mic.sr, mic.gated, mic.muted = 16000, True, threading.Event()
    mic.capturing, mic._frames = threading.Event(), queue.Queue()
    frame = (np.ones(480, dtype=np.int16) * 1000).tobytes()
    mic._on_audio(frame, 480, None, None)
    assert mic._frames.empty()  # key not held -> nothing heard
    mic.capturing.set()
    for _ in range(40):
        mic._on_audio(frame, 480, None, None)
    released = threading.Event(); released.set()
    audio = mic.record_held(released)
    assert audio is not None and len(audio) == 40 * 480 and not mic.capturing.is_set()
