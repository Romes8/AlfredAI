import asyncio

from alfred.agent.permissions import PermissionGate, PermissionPolicy, summarize
from alfred.config import load_config
from alfred.tools import browser
from alfred.tools.server import url_list


def gate(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    cfg["agent"]["workspace"] = str(tmp_path / "ws")

    async def ask(s, d):
        return False

    return PermissionGate(PermissionPolicy(cfg), ask)


def search_result(*urls):
    return {"tool_name": "WebSearch", "tool_input": {"query": "colosseum tickets"},
            "tool_response": {"results": [{"title": "t", "url": u} for u in urls]}}


def test_search_result_links_open_without_a_tap_others_ask(tmp_path):
    g = gate(tmp_path)
    asyncio.run(g.post_tool_hook(search_result("https://ticketing.colosseo.it/en/", "https://www.coopculture.it/x"),
                                 None, None))
    d = g.policy.decide
    assert d("mcp__alfred__open_url", {"urls": ["https://ticketing.colosseo.it/en"]}).action == "allow"
    assert d("mcp__alfred__open_url", {"urls": ["https://ticketing.colosseo.it/en/",
                                                "https://www.coopculture.it/x"]}).action == "allow"
    # one link not from the search -> ask for the lot
    assert d("mcp__alfred__open_url", {"urls": ["https://ticketing.colosseo.it/en/",
                                                "https://evil.example/?d=secret"]}).action == "ask"
    assert d("mcp__alfred__open_url", {"url": "https://evil.example/?d=secret"}).action == "ask"
    assert d("mcp__alfred__open_url", {"urls": ["file:///c:/secret.txt"]}).action == "deny"


def test_other_tools_dont_teach_the_allowlist(tmp_path):
    g = gate(tmp_path)
    asyncio.run(g.post_tool_hook({"tool_name": "Read", "tool_response": "see https://evil.example/x"}, None, None))
    assert g.policy.decide("mcp__alfred__open_url", {"url": "https://evil.example/x"}).action == "ask"


def test_auto_open_modes(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    cfg["links"]["auto_open"] = True
    assert PermissionPolicy(cfg).decide("mcp__alfred__open_url", {"url": "https://a.b"}).action == "allow"
    cfg["links"]["auto_open"] = False
    p = PermissionPolicy(cfg)
    p.search_urls.add("https://a.b")
    assert p.decide("mcp__alfred__open_url", {"url": "https://a.b"}).action == "ask"


def test_summaries_and_url_list():
    assert summarize("mcp__alfred__open_url", {"urls": ["https://a.com/1", "https://a.com/2"]})[0] == \
        "Want me to open a.com?"
    assert summarize("mcp__alfred__open_url", {"urls": ["https://a.com", "https://b.com"]})[0] == \
        "Want me to open 2 pages?"
    assert url_list({"url": "https://a", "urls": ["https://a", "https://b"]}) == ["https://a", "https://b"]


def test_links_go_to_alfreds_own_window(monkeypatch, tmp_path):
    monkeypatch.setattr(browser.sys, "platform", "win32")
    prof = tmp_path / "chrome-links"
    cmd = browser.chrome_command("C:/chrome.exe", ["https://a", "https://b"], prof)
    # same profile folder every time -> Chrome hands new links to the already-open Alfred window as tabs
    assert cmd[0] == "C:/chrome.exe" and f"--user-data-dir={prof}" in cmd and "--new-window" not in cmd
    assert cmd[-2:] == ["https://a", "https://b"]
    monkeypatch.setattr(browser.sys, "platform", "darwin")
    mac = browser.chrome_command("/Applications/Google Chrome.app", ["https://a"], prof)
    assert mac[:4] == ["open", "-na", "/Applications/Google Chrome.app", "--args"] and f"--user-data-dir={prof}" in mac


def test_window_new_mode_uses_normal_profile(monkeypatch):
    launched = []
    monkeypatch.setattr(browser, "find_chrome", lambda: "C:/chrome.exe")
    monkeypatch.setattr(browser.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))
    monkeypatch.setattr(browser.sys, "platform", "win32")
    browser.open_in_alfred_window(["https://a"], window="new")
    assert "--new-window" in launched[-1] and not any(a.startswith("--user-data-dir") for a in launched[-1])
    browser.open_in_alfred_window(["https://a"])
    assert any(a.startswith("--user-data-dir") for a in launched[-1])


def test_falls_back_to_default_browser_tabs(monkeypatch):
    opened = []
    monkeypatch.setattr(browser, "find_chrome", lambda: None)
    monkeypatch.setattr(browser.webbrowser, "open_new_tab", lambda u: opened.append(u))
    assert browser.open_in_alfred_window(["https://a", "https://b"]) == "your default browser"
    assert opened == ["https://a", "https://b"]
