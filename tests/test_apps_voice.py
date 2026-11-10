from alfred.agent.permissions import PermissionPolicy, summarize
from alfred.audio.tts import KOKORO_VOICES, kokoro_lang
from alfred.config import load_config
from alfred.tools.apps import match_app

APPS = {"Spotify": "SpotifyAB.Spotify", "Steam": "steam", "Steam Support Center": "steam-support",
        "Visual Studio Code": "vscode", "Discord": "discord", "WordPad": "wordpad", "Microsoft Word": "word",
        "Google Chrome": "chrome", "Calculator": "calc"}


def test_match_app():
    assert match_app("Spotify", APPS)[0] == "Spotify"
    assert match_app("the spotify app", APPS)[0] == "Spotify"
    assert match_app("steam", APPS)[0] == "Steam"            # shortest wins over "Steam Support Center"
    assert match_app("vs code", APPS)[0] == "Visual Studio Code"
    assert match_app("word", APPS)[0] == "Microsoft Word"     # not WordPad
    assert match_app("chrome", APPS)[0] == "Google Chrome"
    assert match_app("discrod", APPS)[0] == "Discord"         # typo / mishearing
    name, alts = match_app("photoshop", APPS)
    assert name is None


def test_open_app_auto_by_default_and_can_ask(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    assert PermissionPolicy(cfg).decide("mcp__alfred__open_app", {"name": "Spotify"}).action == "allow"
    cfg["apps"]["auto_open"] = False
    assert PermissionPolicy(cfg).decide("mcp__alfred__open_app", {"name": "Spotify"}).action == "ask"
    assert summarize("mcp__alfred__open_app", {"name": "Spotify"})[0] == "Want me to open Spotify?"


def test_voices_and_accents():
    assert "bm_george" in KOKORO_VOICES["british_male"] and "am_michael" in KOKORO_VOICES["american_male"]
    assert kokoro_lang("bm_george") == "en-gb" and kokoro_lang("af_heart") == "en-us"


def test_defaults_are_faster_and_natural(tmp_path):
    t = load_config(tmp_path / "none.yaml")["tts"]
    assert t["engine"] == "kokoro" and t["rate"] > 1.0
