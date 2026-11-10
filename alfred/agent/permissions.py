"""Alfred's permission model.

  auto   - Read / Glob / Grep inside readable_dirs, web search, Alfred's own tools (iRacing, screen)
  ask    - Write / Edit / Bash -> Roman confirms out loud (or types y/n in text mode)
  deny   - anything outside the allowed folders, secrets files, destructive commands

Enforced twice: a PreToolUse hook (fires for EVERY tool call, can't be bypassed by Claude Code's own
auto-approvals) handles hard denies, and the can_use_tool callback handles the ask-first flow.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from alfred.config import expand

READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash"}
WEB_TOOLS = {"WebSearch", "WebFetch"}
ALFRED_PREFIX = "mcp__alfred__"
# Alfred tools that change something and therefore need a yes (none yet - placeholder for future tools)
ALFRED_ASK: set[str] = set()

DESTRUCTIVE = [
    r"\brm\s+-[a-z]*r", r"\brmdir\b", r"\bdel\s+/[sq]", r"\bformat\s+[a-z]:", r"\bmkfs\b",
    r"\bdd\s+if=", r"Remove-Item\b.*-Recurse", r"\bshutdown\b", r"\breg\s+delete\b", r":\(\)\s*\{",
    r"\bgit\s+push\b.*--force", r"\bcurl\b.*\|\s*(ba)?sh", r"\biwr\b.*\|\s*iex",
]

AskFn = Callable[[str, str], Awaitable[bool]]


@dataclass
class Decision:
    action: str  # allow | ask | deny
    reason: str = ""


class PermissionPolicy:
    def __init__(self, cfg: dict) -> None:
        p = cfg["permissions"]
        self.readable = [expand(d) for d in p["readable_dirs"]]
        self.writable = [expand(d) for d in p["writable_dirs"]]
        self.workspace = expand(cfg["agent"]["workspace"])
        self.deny_patterns = [s.lower() for s in p["deny_patterns"]]

    # ---------- path helpers ----------
    @staticmethod
    def _inside(path: Path, roots: list[Path]) -> bool:
        for root in roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    def _is_secret(self, raw: str) -> bool:
        low = raw.replace("\\", "/").lower()
        return any(pat in low for pat in self.deny_patterns)

    @staticmethod
    def _path_arg(tool: str, args: dict[str, Any]) -> str | None:
        if tool in ("Read", "Write", "Edit", "MultiEdit"):
            return args.get("file_path")
        if tool == "NotebookEdit":
            return args.get("notebook_path")
        if tool in ("Glob", "Grep"):
            return args.get("path")  # may be None -> cwd (workspace)
        return None

    # ---------- the decision ----------
    def decide(self, tool: str, args: dict[str, Any]) -> Decision:
        if tool.startswith(ALFRED_PREFIX):
            return Decision("ask" if tool in ALFRED_ASK else "allow")
        if tool in WEB_TOOLS:
            return Decision("allow")

        if tool in READ_TOOLS or tool in WRITE_TOOLS:
            raw = self._path_arg(tool, args)
            if raw and self._is_secret(raw):
                return Decision("deny", f"{raw} looks like a secrets file - that's off limits.")
            if tool == "Grep" or tool == "Glob":
                pattern = str(args.get("pattern", ""))
                if self._is_secret(pattern):
                    return Decision("deny", "Searching for secrets files is off limits.")
            path = self._resolve(raw) if raw else self.workspace
            if tool in READ_TOOLS:
                if self._inside(path, self.readable + self.writable + [self.workspace]):
                    return Decision("allow")
                return Decision("deny", f"{path} is outside the folders Roman allowed me to read.")
            # write tools
            if self._inside(path, self.writable + [self.workspace]):
                return Decision("ask")
            return Decision("deny", f"{path} is outside the folders I'm allowed to write to.")

        if tool in SHELL_TOOLS:
            cmd = str(args.get("command", ""))
            for pat in DESTRUCTIVE:
                if re.search(pat, cmd, flags=re.I):
                    return Decision("deny", f"Blocked a destructive command: {cmd}")
            if self._is_secret(cmd):
                return Decision("deny", "That command touches secrets files - not doing that.")
            return Decision("ask")

        # Anything unknown: ask rather than silently allow
        return Decision("ask")


def summarize(tool: str, args: dict[str, Any]) -> tuple[str, str]:
    """(short spoken summary, longer detail for the overlay)."""
    if tool == "Write":
        content = str(args.get("content", ""))
        lines = content.count("\n") + 1 if content else 0
        name = Path(str(args.get("file_path", "?"))).name
        return f"I want to write {name}, {lines} lines. Cool?", f"WRITE {args.get('file_path')}\n\n{content[:1500]}"
    if tool in ("Edit", "MultiEdit"):
        name = Path(str(args.get("file_path", "?"))).name
        old = str(args.get("old_string", ""))[:600]
        new = str(args.get("new_string", ""))[:600]
        return f"I want to edit {name}. Good to go?", f"EDIT {args.get('file_path')}\n\n- {old}\n+ {new}"
    if tool == "Bash":
        cmd = str(args.get("command", ""))
        desc = args.get("description") or "run a command"
        return f"I want to {desc.rstrip('.').lower()}. Yes or no?", f"RUN\n\n{cmd}"
    return f"I want to use {tool}. Yes or no?", f"{tool}\n\n{args}"


class PermissionGate:
    """Wires the policy into the Agent SDK (hook + can_use_tool)."""

    def __init__(self, policy: PermissionPolicy, ask: AskFn, bus=None) -> None:
        self.policy = policy
        self.ask = ask
        self.bus = bus
        self._lock = asyncio.Lock()  # one question at a time

    async def pre_tool_hook(self, input_data: dict, tool_use_id: str | None, context: Any) -> dict:  # noqa: ARG002
        tool = input_data.get("tool_name", "")
        args = input_data.get("tool_input", {}) or {}
        d = self.policy.decide(tool, args)
        if d.action == "deny":
            if self.bus:
                self.bus.emit("permission", tool=tool, summary="Blocked", detail=d.reason, result="denied")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": d.reason,
                }
            }
        return {}

    async def can_use_tool(self, tool: str, args: dict[str, Any], context: ToolPermissionContext):  # noqa: ARG002
        d = self.policy.decide(tool, args)
        if d.action == "allow":
            return PermissionResultAllow()
        if d.action == "deny":
            return PermissionResultDeny(message=d.reason)
        summary, detail = summarize(tool, args)
        async with self._lock:
            if self.bus:
                self.bus.emit("permission", tool=tool, summary=summary, detail=detail, result="pending")
            ok = await self.ask(summary, detail)
            if self.bus:
                self.bus.emit("permission", tool=tool, summary=summary, detail=detail,
                              result="approved" if ok else "denied")
        if ok:
            return PermissionResultAllow()
        return PermissionResultDeny(message="Roman said no. Don't retry it - carry on without it or ask what he'd prefer.")
