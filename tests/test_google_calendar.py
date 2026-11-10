import json

import yaml

from alfred.config import load_config
from alfred.connectors import load_connectors
from alfred.agent.permissions import PermissionPolicy
from alfred.setup_google import add_connector_to_config, validate_client_file


def test_validate_client_file(tmp_path):
    good = tmp_path / "c.json"
    good.write_text(json.dumps({"installed": {"client_id": "x"}}))
    web = tmp_path / "w.json"
    web.write_text(json.dumps({"web": {}}))
    junk = tmp_path / "j.json"
    junk.write_text("nope")
    assert validate_client_file(good) is None
    assert "Desktop app" in validate_client_file(web)
    assert validate_client_file(junk)


def test_config_edit_keeps_comments_and_loads(tmp_path):
    example = open("config.example.yaml", encoding="utf-8").read()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(example, encoding="utf-8")
    creds = tmp_path / "it's here" / "gcp-oauth.keys.json"  # apostrophe + space in the path
    assert add_connector_to_config(cfg_file, creds) == "added to config.yaml"
    assert add_connector_to_config(cfg_file, creds) == "already in config.yaml"
    text = cfg_file.read_text(encoding="utf-8")
    assert "# Per-machine config" in text  # comments survive
    cfg = load_config(cfg_file)
    conn = {c.name: c for c in load_connectors(cfg)}["google_calendar"]
    assert conn.server["env"]["GOOGLE_OAUTH_CREDENTIALS"] == str(creds)
    assert conn.server["args"] == ["-y", "@cocal/google-calendar-mcp"]


def test_config_without_connectors_section(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("name: Alfred\n", encoding="utf-8")
    add_connector_to_config(f, tmp_path / "c.json")
    assert "google_calendar" in yaml.safe_load(f.read_text())["connectors"]


def test_calendar_permissions(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("connectors: {}\n", encoding="utf-8")
    add_connector_to_config(f, tmp_path / "c.json")
    p = PermissionPolicy(load_config(f))
    for t in ["list-events", "search-events", "get-freebusy", "get-current-time", "list-calendars"]:
        assert p.decide(f"mcp__google_calendar__{t}", {}).action == "allow", t
    for t in ["create-event", "update-event", "delete-event", "respond-to-event", "manage-accounts"]:
        assert p.decide(f"mcp__google_calendar__{t}", {}).action == "ask", t


def test_calendar_spoken_prompts():
    from alfred.agent.permissions import summarize

    s = lambda t, a: summarize(f"mcp__google_calendar__{t}", a)[0]  # noqa: E731
    assert s("create-event", {"summary": "Dentist", "start": "2026-11-13T14:00:00"}) == \
        'Want me to add "Dentist" on Fri 13 Nov at 14:00 to your calendar?'
    assert s("delete-event", {"eventId": "x"}) == "Want me to delete that event from your calendar?"
    assert s("respond-to-event", {"response": "accepted"}) == "Want me to answer that invite with accepted?"
    assert s("update-event", {"summary": "Gym", "start": {"dateTime": "2026-11-14T07:30:00+01:00"}}) == \
        'Want me to change "Gym" to Sat 14 Nov at 07:30?'


def test_windows_paths_with_backslashes(tmp_path):
    # Regression: re.sub treated C:\Users\... in the replacement as escape sequences ("bad escape \U")
    from pathlib import PureWindowsPath

    f = tmp_path / "config.yaml"
    f.write_text("name: Alfred\nconnectors: {}\n", encoding="utf-8")
    creds = PureWindowsPath(r"C:\Users\roman\.alfred\google\gcp-oauth.keys.json")
    add_connector_to_config(f, creds)
    cfg = load_config(f)
    assert cfg["connectors"]["google_calendar"]["env"]["GOOGLE_OAUTH_CREDENTIALS"] == str(creds)
    f.write_text("connectors:\n  other: {command: x}\n", encoding="utf-8")
    add_connector_to_config(f, creds)
    assert "google_calendar" in load_config(f)["connectors"]
