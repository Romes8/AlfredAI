"""Connectors: let Alfred use outside services (HubSpot, email, calendar, ...) through MCP servers.

Configured per machine in config.yaml under `connectors:`. Secrets never go in the file itself - write
${ENV_VAR} and keep the value in your environment.

    connectors:
      hubspot:
        command: npx
        args: ["-y", "@hubspot/mcp-server"]
        env: {PRIVATE_APP_ACCESS_TOKEN: "${HUBSPOT_TOKEN}"}
        mode: ask_writes          # read_only | ask_writes (default) | ask_all
        description: "HubSpot CRM - contacts, companies, deals"

Permission modes (on top of everything else Alfred enforces):
  read_only   reads run automatically, anything that changes data is BLOCKED
  ask_writes  reads run automatically, changes need your tap        (default)
  ask_all     every call needs your tap
Per-tool overrides: allow: [...], ask: [...], deny: [...] (tool names without the mcp__<name>__ prefix).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

RESERVED = {"alfred"}  # Alfred's own built-in tool server
MODES = {"read_only", "ask_writes", "ask_all"}

# Words that mean "just looking" vs "changing something". A tool is a READ only if its name has a read word
# and no change word: hubspot-list-objects = read, hubspot-batch-create-objects = change, send_email = change.
READ_WORDS = {"get", "list", "search", "find", "read", "fetch", "query", "describe", "lookup", "count", "show",
              "view", "retrieve", "check", "summarize", "summarise", "export", "download", "browse", "whoami",
              "me", "info", "status", "properties", "schema"}
WRITE_WORDS = {"create", "update", "delete", "remove", "send", "post", "add", "set", "put", "patch", "write",
               "move", "archive", "merge", "upload", "cancel", "assign", "reply", "forward", "draft", "schedule",
               "invite", "edit", "modify", "insert", "upsert", "trash", "mark", "label", "accept", "decline",
               "approve", "submit", "publish", "share", "transfer", "pay", "book", "rename", "copy", "associate",
               "unsubscribe", "subscribe", "enroll", "close", "complete"}
_TOKEN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class Connector:
    name: str
    server: dict[str, Any]
    mode: str = "ask_writes"
    description: str = ""
    allow: set[str] = field(default_factory=set)
    ask: set[str] = field(default_factory=set)
    deny: set[str] = field(default_factory=set)
    missing_env: list[str] = field(default_factory=list)

    @property
    def prefix(self) -> str:
        return f"mcp__{self.name}__"


def _expand(value: Any, missing: list[str]) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            v = os.environ.get(m.group(1))
            if v is None:
                missing.append(m.group(1))
                return ""
            return v
        return _TOKEN.sub(repl, value)
    if isinstance(value, list):
        return [_expand(v, missing) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, missing) for k, v in value.items()}
    return value


_warned: set[str] = set()


def _warn(msg: str) -> None:
    if msg not in _warned:  # policy, brain and persona all load connectors - say each thing once
        _warned.add(msg)
        print(msg)


def load_connectors(cfg: dict, quiet: bool = False) -> list[Connector]:
    """Parse cfg['connectors'] into server configs for the Agent SDK. Skips (with a warning) bad entries."""
    out: list[Connector] = []
    say = (lambda m: None) if quiet else _warn
    for name, c in (cfg.get("connectors") or {}).items():
        if not isinstance(c, dict) or c.get("enabled", True) is False:
            continue
        if name in RESERVED or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            say(f"[connectors] skipping '{name}': use letters, digits, - or _ and not 'alfred'")
            continue
        missing: list[str] = []
        if c.get("url"):
            server: dict[str, Any] = {"type": c.get("type", "http"), "url": _expand(c["url"], missing)}
            if c.get("headers"):
                server["headers"] = _expand(c["headers"], missing)
        elif c.get("command"):
            server = {"type": "stdio", "command": _expand(c["command"], missing),
                      "args": _expand(list(c.get("args", [])), missing)}
            if c.get("env"):
                server["env"] = _expand(c["env"], missing)
        else:
            say(f"[connectors] skipping '{name}': needs either `command` (local server) or `url` (remote)")
            continue
        mode = c.get("mode", "ask_writes")
        if mode not in MODES:
            say(f"[connectors] '{name}': unknown mode '{mode}', using ask_writes")
            mode = "ask_writes"
        conn = Connector(name, server, mode, c.get("description", ""), set(c.get("allow", [])),
                         set(c.get("ask", [])), set(c.get("deny", [])), sorted(set(missing)))
        if conn.missing_env:
            say(f"[connectors] '{name}' is missing environment variable(s): {', '.join(conn.missing_env)} "
                  "- skipping it until they're set")
            continue
        out.append(conn)
    return out


def is_read_tool(tool_short_name: str) -> bool:
    words = set(re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", tool_short_name).lower()))
    return bool(words & READ_WORDS) and not (words & WRITE_WORDS)


def decide(conn: Connector, tool_short_name: str) -> tuple[str, str]:
    """(action, reason) for one connector tool: allow | ask | deny."""
    t = tool_short_name
    if t in conn.deny:
        return "deny", f"{conn.name}: {t} is blocked in config."
    if t in conn.allow:
        return "allow", ""
    if t in conn.ask or conn.mode == "ask_all":
        return "ask", ""
    if is_read_tool(t):
        return "allow", ""
    if conn.mode == "read_only":
        return "deny", f"{conn.name} is read-only on this machine - {t} would change data."
    return "ask", ""


def pretty(tool_short_name: str) -> str:
    """hubspot-create-contact / create_contact -> 'create contact'"""
    return re.sub(r"[_\-.]+", " ", tool_short_name).strip().lower()


def describe_all(cfg: dict) -> str:
    """Human summary for `alfred connectors`."""
    raw = cfg.get("connectors") or {}
    if not raw:
        return "No connectors configured on this machine. Add them under `connectors:` in config.yaml (see docs)."
    loaded = {c.name: c for c in load_connectors(cfg, quiet=True)}
    lines = []
    for name, c in raw.items():
        if name in loaded:
            k = loaded[name]
            where = k.server.get("url") or " ".join([k.server["command"], *k.server.get("args", [])])
            lines.append(f"  ✓ {name:<14} {k.mode:<11} {where}")
        elif isinstance(c, dict) and c.get("enabled", True) is False:
            lines.append(f"  - {name:<14} disabled")
        else:
            missing: list[str] = []
            _expand(c, missing) if isinstance(c, dict) else None
            why = f"missing env: {', '.join(sorted(set(missing)))}" if missing else "invalid entry (see warnings)"
            lines.append(f"  ✗ {name:<14} {why}")
    return "Connectors on this machine:\n" + "\n".join(lines)
