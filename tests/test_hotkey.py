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
