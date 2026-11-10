"""Alfred's permission model.

  auto   - Read / Glob / Grep inside readable_dirs, web SEARCH, Alfred's own tools (screen)
  ask    - Write / Edit, fetching a specific URL (WebFetch - a URL can smuggle data out),
           Bash (only if agent.allow_commands is on) -> Roman approves (key tap / voice / y-n)
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

from alfred import connectors as conn_mod
from alfred.config import expand

READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash"}
WEB_TOOLS = {"WebSearch"}
FETCH_TOOLS = {"WebFetch"}
ALFRED_PREFIX = "mcp__alfred__"
OPEN_URL = "mcp__alfred__open_url"
OPEN_APP = "mcp__alfred__open_app"
MEMORY_TOOLS = {"mcp__alfred__remember", "mcp__alfred__forget"}
RUN_COMMAND = "mcp__alfred__run_command"
ARRANGE = "mcp__alfred__arrange_window"

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
        # links.auto_open: "search_results" (default) = open automatically only pages that came back from his own
        # web search this session; true = any link; false = always ask
        self.auto_open_links = cfg.get("links", {}).get("auto_open", "search_results")
        self.search_urls: set[str] = set()
        self.auto_open_apps = bool(cfg.get("apps", {}).get("auto_open", True))
        self.confirm_memory = bool(cfg.get("memory", {}).get("confirm", False))
        c = cfg.get("commands", {})
        self.cmd_on = {"sensitive": c.get("on_read_file", "ask"), "change": c.get("on_change", "ask"),
                       "delete": c.get("on_delete", "ask")}
        self.connectors = {c.prefix: c for c in conn_mod.load_connectors(cfg)}

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
        if tool == OPEN_URL:
            urls = _urls(args)
            bad = [u for u in urls if not re.match(r"^https?://[^\s/]+", u, flags=re.I)]
            if not urls or bad:
                return Decision("deny", f"Not a web link: {(bad or [''])[0][:80]}")
            # A URL can smuggle data out in the link itself. Pages his own web search returned are safe to open
            # without asking; anything else (a link he made up, or found inside a page/email) needs a tap.
            if self.auto_open_links is True:
                return Decision("allow")
            if self.auto_open_links == "search_results" and all(_norm_url(u) in self.search_urls for u in urls):
                return Decision("allow")
            return Decision("ask")
        if tool == RUN_COMMAND:
            from alfred.tools.commands import classify

            level, why = classify(str(args.get("command", "")), self.deny_patterns)
            if level == "read":
                return Decision("allow")
            if level == "blocked":
                return Decision("deny", f"Blocked - that command {why}. Not running it.")
            mode = self.cmd_on.get(level, "ask")
            if mode == "deny":
                return Decision("deny", f"That command {why}, and this machine is set to never allow that.")
            return Decision("allow" if mode == "allow" else "ask")
        if tool == ARRANGE:
            return Decision("ask" if args.get("action") == "close" else "allow")  # closing can lose unsaved work
        if tool in MEMORY_TOOLS:
            return Decision("ask" if self.confirm_memory else "allow")
        if tool == OPEN_APP:
            # Only installed apps by name, no arguments - low risk, so no tap needed unless apps.auto_open is off.
            return Decision("allow" if self.auto_open_apps else "ask")
        if tool.startswith(ALFRED_PREFIX):
            return Decision("allow")
        if tool.startswith("mcp__"):
            for prefix, c in self.connectors.items():
                if tool.startswith(prefix):
                    action, reason = conn_mod.decide(c, tool[len(prefix):])
                    return Decision(action, reason)
            return Decision("deny", f"{tool} isn't from a connector enabled on this machine.")
        if tool in WEB_TOOLS:
            return Decision("allow")
        if tool in FETCH_TOOLS:
            return Decision("ask")

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


URL_RE = re.compile(r"https?://[^\s\"'<>)\]}\\]+", re.I)


def _norm_url(u: str) -> str:
    return u.strip().rstrip("/.,;").lower()


def _urls(args: dict[str, Any]) -> list[str]:
    urls = [str(u) for u in (args.get("urls") or [])]
    if args.get("url"):
        urls.insert(0, str(args["url"]))
    return [u.strip() for u in urls if str(u).strip()]


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
        # Speak the REAL command, never Claude's own description of it (that could be made to lie).
        cmd = str(args.get("command", ""))
        spoken = cmd if len(cmd) <= 120 else cmd[:120] + " and more, check the overlay"
        return f"I want to run this command: {spoken}.", f"RUN\n\n{cmd}"
    if tool == RUN_COMMAND:
        from alfred.tools.commands import classify

        cmd = str(args.get("command", ""))
        level, why = classify(cmd)
        spoken = cmd if len(cmd) <= 100 else cmd[:100] + "... the rest is on the overlay"
        verb = {"delete": "This one deletes stuff", "change": "This one changes things",
                "sensitive": "This one reads a file"}.get(level, "")
        return f"I want to run: {spoken}. {verb}.".replace(". .", "."), f"RUN ({level}: {why})\n\n{cmd}"
    if tool == ARRANGE:
        return f"Want me to close {args.get('window', 'that window')}?", f"CLOSE WINDOW\n\n{args.get('window')}"
    if tool == "mcp__alfred__remember":
        return f"Want me to remember: {args.get('fact', '')}?", f"REMEMBER\n\n{args.get('fact')}"
    if tool == "mcp__alfred__forget":
        return f"Want me to forget {args.get('what', '')}?", f"FORGET\n\n{args.get('what')}"
    if tool == OPEN_APP:
        return f"Want me to open {args.get('name', 'that app')}?", f"OPEN APP\n\n{args.get('name')}"
    if tool == OPEN_URL:
        urls = _urls(args)
        hosts = list(dict.fromkeys(re.sub(r"^https?://", "", u).split("/")[0] for u in urls))
        what = hosts[0] if len(hosts) == 1 else f"{len(urls)} pages"
        return f"Want me to open {what}?", "OPEN IN NEW WINDOW\n\n" + "\n".join(urls)
    if tool == "WebFetch":
        url = str(args.get("url", ""))
        host = re.sub(r"^https?://", "", url).split("/")[0]
        return f"I want to open a page on {host}.", f"FETCH\n\n{url}"
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        _, service, short = tool.split("__", 2)
        import json

        detail = json.dumps(args, indent=2, ensure_ascii=False, default=str)[:1500]
        action = re.sub(rf"^{re.escape(service)}[_\-.]+", "", short, flags=re.I)  # hubspot-create-x -> create-x
        return f"I want to {conn_mod.pretty(action)} in {service}.", f"{service.upper()}: {short}\n\n{detail}"
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

    async def post_tool_hook(self, input_data: dict, tool_use_id: str | None, context: Any) -> dict:  # noqa: ARG002
        """Remember the links his web searches returned - those may be opened without a tap."""
        if input_data.get("tool_name") == "WebSearch":
            import json

            text = json.dumps(input_data.get("tool_response"), default=str)
            for u in URL_RE.findall(text):
                self.policy.search_urls.add(_norm_url(u))
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
