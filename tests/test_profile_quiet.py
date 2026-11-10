import asyncio
import json

from alfred.agent.permissions import PermissionGate, PermissionPolicy, summarize
from alfred.config import load_config
from alfred.profile import load_profile


def test_profile_flattens_and_refuses_secrets():
    cfg = {"profile": {"name": "Roman", "email": "r@x.dk", "address": {"city": "Copenhagen", "postal_code": "2100"},
                       "card_number": "4111 1111 1111 1111", "password": "hunter2", "cpr": "010198-1234",
                       "notes": "4111111111111111", "empty": ""}}
    assert load_profile(cfg) == {"name": "Roman", "email": "r@x.dk", "address.city": "Copenhagen",
                                 "address.postal_code": "2100"}


def test_get_my_details_tool(tmp_path):
    from alfred.tools.server import build_server

    cfg = load_config(tmp_path / "none.yaml")
    cfg["profile"] = {"name": "Roman", "email": "r@x.dk", "address": {"city": "Copenhagen"}}
    server, names = build_server(cfg)
    assert "mcp__alfred__get_my_details" in names
    # get_my_details is auto-allowed (one of Alfred's own tools)
    assert PermissionPolicy(cfg).decide("mcp__alfred__get_my_details", {}).action == "allow"


def test_quiet_prompts_by_default(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    spoken = []

    async def ask(summary, detail):
        spoken.append((summary, detail))
        return False

    gate = PermissionGate(PermissionPolicy(cfg), ask)
    asyncio.run(gate.can_use_tool("mcp__alfred__open_url", {"url": "https://evil.example/very/long/link"}, None))
    assert spoken[-1][0] == "Want me to open that page?" and "evil.example" in spoken[-1][1]
    cfg["browser_control"]["enabled"] = True
    gate = PermissionGate(PermissionPolicy(cfg), ask)
    asyncio.run(gate.can_use_tool("mcp__browser__browser_click", {"element": "Proceed to the next step"}, None))
    assert spoken[-1][0] == "Want me to click that?" and "Proceed" in spoken[-1][1]
    asyncio.run(gate.can_use_tool("mcp__browser__browser_fill_form",
                                  {"fields": [{"name": "Email", "value": "r@x.dk"}]}, None))
    assert spoken[-1][0] == "Want me to fill in the form with your details?" and "r@x.dk" in spoken[-1][1]


def test_commands_are_always_read_out(tmp_path):
    assert "del old.txt" in summarize("mcp__alfred__run_command", {"command": "del old.txt"}, say_details=False)[0]


def test_details_can_be_switched_back_on():
    assert summarize("mcp__alfred__open_url", {"url": "https://colosseo.it"}, True)[0] == "Want me to open colosseo.it?"
    assert json  # keep import used
