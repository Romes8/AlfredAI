import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from alfred.agent.permissions import PermissionGate, PermissionPolicy, summarize
from alfred.config import load_config


@pytest.fixture
def cfg(tmp_path: Path):
    c = load_config(tmp_path / "missing.yaml")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "out").mkdir()
    c["permissions"]["readable_dirs"] = [str(tmp_path / "docs")]
    c["permissions"]["writable_dirs"] = [str(tmp_path / "docs" / "out")]
    c["agent"]["workspace"] = str(tmp_path / "ws")
    return c


@pytest.fixture
def policy(cfg):
    return PermissionPolicy(cfg)


def test_read_inside_allowed(policy, tmp_path):
    assert policy.decide("Read", {"file_path": str(tmp_path / "docs" / "a.md")}).action == "allow"


def test_read_outside_denied(policy, tmp_path):
    assert policy.decide("Read", {"file_path": str(tmp_path / "elsewhere.txt")}).action == "deny"


def test_path_traversal_denied(policy, tmp_path):
    sneaky = str(tmp_path / "docs" / ".." / "elsewhere.txt")
    assert policy.decide("Read", {"file_path": sneaky}).action == "deny"


def test_secrets_denied_even_inside(policy, tmp_path):
    assert policy.decide("Read", {"file_path": str(tmp_path / "docs" / ".env")}).action == "deny"
    assert policy.decide("Glob", {"pattern": "**/.ssh/*", "path": str(tmp_path / "docs")}).action == "deny"


def test_write_asks_inside_writable(policy, tmp_path):
    assert policy.decide("Write", {"file_path": str(tmp_path / "docs" / "out" / "n.md")}).action == "ask"


def test_write_in_readonly_dir_denied(policy, tmp_path):
    assert policy.decide("Edit", {"file_path": str(tmp_path / "docs" / "a.md")}).action == "deny"


def test_bash_asks_and_destructive_denied(policy):
    assert policy.decide("Bash", {"command": "dir"}).action == "ask"
    assert policy.decide("Bash", {"command": "rm -rf /"}).action == "deny"
    assert policy.decide("Bash", {"command": "Remove-Item C:\\x -Recurse -Force"}).action == "deny"


def test_web_and_alfred_tools_allowed(policy):
    assert policy.decide("WebSearch", {"query": "f1"}).action == "allow"
    assert policy.decide("mcp__alfred__get_race_data", {}).action == "allow"


def test_unknown_tool_asks(policy):
    assert policy.decide("SomethingNew", {}).action == "ask"


def test_summaries_are_short():
    s, d = summarize("Write", {"file_path": "C:/x/notes.md", "content": "a\nb"})
    assert "notes.md" in s and "2 lines" in s and "notes.md" in d


def test_gate_asks_and_respects_answer(cfg, tmp_path):
    asked = []

    async def say_no(summary, detail):
        asked.append(summary)
        return False

    async def say_yes(summary, detail):
        return True

    target = {"file_path": str(tmp_path / "docs" / "out" / "n.md"), "content": "hi"}
    no_gate = PermissionGate(PermissionPolicy(cfg), say_no)
    yes_gate = PermissionGate(PermissionPolicy(cfg), say_yes)
    r1 = asyncio.run(no_gate.can_use_tool("Write", target, None))
    r2 = asyncio.run(yes_gate.can_use_tool("Write", target, None))
    r3 = asyncio.run(no_gate.can_use_tool("Read", {"file_path": str(tmp_path / "docs" / "a")}, None))
    assert isinstance(r1, PermissionResultDeny) and asked
    assert isinstance(r2, PermissionResultAllow)
    assert isinstance(r3, PermissionResultAllow)


def test_hook_blocks_outside_reads(cfg, tmp_path):
    async def never(summary, detail):
        raise AssertionError("should not ask")

    gate = PermissionGate(PermissionPolicy(cfg), never)
    out = asyncio.run(gate.pre_tool_hook({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "x")}}, None, None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    ok = asyncio.run(gate.pre_tool_hook({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "docs" / "a")}}, None, None))
    assert ok == {}
