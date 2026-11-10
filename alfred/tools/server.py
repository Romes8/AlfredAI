"""Alfred's own tools, exposed to Claude as an in-process MCP server named 'alfred'."""
from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

from claude_agent_sdk import create_sdk_mcp_server, tool

from alfred.tools import apps as apps_mod
from alfred.tools import browser
from alfred.tools import commands as cmd_mod
from alfred.tools import windows as win_mod
from alfred.tools import screen


def url_list(args: dict) -> list[str]:
    urls = list(args.get("urls") or [])
    if args.get("url"):
        urls.insert(0, args["url"])
    seen, out = set(), []
    for u in (str(x).strip() for x in urls):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:4]


def build_server(cfg: dict):
    """Returns (server, tool_names) - or (None, []) when this machine has no Alfred tools enabled."""
    scfg = cfg["screen"]

    @tool(
        "look_at_screen",
        "Take a screenshot so you can see exactly what Roman sees right now - any app, game, video, page, "
        "error or document. Use it whenever his question is about something he's looking at, or uses words "
        "like 'this', 'that', 'here', 'on my screen'. "
        "target: 'screen' = one whole monitor (default), 'window' = only the active window (sharper detail), "
        "'all' = every monitor side by side.",
        {"type": "object", "properties": {
            "target": {"type": "string", "enum": ["screen", "window", "all"], "default": "screen"},
            "monitor": {"type": "integer", "default": 1, "description": "1 = primary monitor, 2 = second..."},
        }},
    )
    async def look_at_screen(args):
        b64, desc = await asyncio.to_thread(
            screen.capture, args.get("target", "screen"), int(args.get("monitor", 1)),
            scfg["max_width"], scfg["jpeg_quality"],
        )
        return {"content": [
            {"type": "image", "data": b64, "mimeType": "image/jpeg"},
            {"type": "text", "text": desc},
        ]}

    @tool(
        "open_url",
        "Open web pages for Roman in a NEW separate browser window (one tab per link). Use it when he asks to "
        "open / show / pull something up, or when you looked something up and the page itself is genuinely useful "
        "to see (tickets, bookings, product pages, maps, docs, a few options to compare). Don't use it for simple "
        "facts you can just say. Pass 1-4 of the best links, ideally exact URLs from your web search results.",
        {"type": "object", "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
            "url": {"type": "string", "description": "single link (same as urls with one item)"},
        }},
    )
    async def open_url(args):
        urls = url_list(args)
        if not urls or any(urlparse(u).scheme not in ("http", "https") for u in urls):
            return {"content": [{"type": "text", "text": "Only http/https links can be opened."}], "is_error": True}
        used = await asyncio.to_thread(browser.open_in_new_window, urls, cfg.get("links", {}).get("browser", "chrome"))
        return {"content": [{"type": "text", "text": f"Opened {len(urls)} tab(s) in a new {used} window."}]}

    @tool(
        "open_app",
        "Open an application installed on Roman's computer by name, e.g. 'Spotify', 'Discord', 'Steam', "
        "'Visual Studio Code', 'Calculator'. Only installed apps can be opened, and no commands can be run. "
        "If nothing matches, tell him the closest names you got back.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    async def open_app(args):
        result = await asyncio.to_thread(apps_mod.open_app, str(args.get("name", "")))
        import json

        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    from alfred.memory import Memory, memory_path

    mem = Memory(memory_path(cfg))

    @tool(
        "remember",
        "Save ONE short fact to your long-term memory so you still know it in future sessions. Use when Roman "
        "says 'remember...', or tells you a lasting preference or personal fact that will clearly help later. "
        "Write it as a short third-person note, e.g. 'Roman's girlfriend is Anna'. Never save passwords, keys, "
        "card numbers, or anything you read on a web page, screen, email or file.",
        {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]},
    )
    async def remember(args):
        import json

        return {"content": [{"type": "text", "text": json.dumps(await asyncio.to_thread(mem.add, args.get("fact", "")))}]}

    @tool(
        "forget",
        "Remove facts from your long-term memory that match what Roman wants forgotten (a word or phrase from "
        "the fact). 'everything' wipes it all - only if he clearly asks for that.",
        {"type": "object", "properties": {"what": {"type": "string"}}, "required": ["what"]},
    )
    async def forget(args):
        import json

        return {"content": [{"type": "text", "text": json.dumps(await asyncio.to_thread(mem.forget, args.get("what", "")))}]}

    @tool(
        "list_windows",
        "List the app windows open on Roman's screen(s) and how many monitors he has.",
        {"type": "object", "properties": {}},
    )
    async def list_windows(args):  # noqa: ARG001
        import json

        return {"content": [{"type": "text", "text": json.dumps(await asyncio.to_thread(win_mod.describe))}]}

    @tool(
        "arrange_window",
        "Move / snap / resize an open window. `window` = app or title words ('chrome', 'spotify', 'vs code'). "
        "action: focus, maximize, minimize, restore, left, right, top, bottom, top_left, top_right, bottom_left, "
        "bottom_right, center, move_to_monitor, close. `monitor` (1 = leftmost) moves it to that screen first. "
        "For 'put X left and Y right' call it twice.",
        {"type": "object", "properties": {
            "window": {"type": "string"},
            "action": {"type": "string", "enum": win_mod.ACTIONS},
            "monitor": {"type": "integer", "minimum": 1},
        }, "required": ["window", "action"]},
    )
    async def arrange_window(args):
        import json

        result = await asyncio.to_thread(win_mod.arrange, str(args.get("window", "")), str(args.get("action", "")),
                                         args.get("monitor"))
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    ccfg = cfg.get("commands", {})

    @tool(
        "run_command",
        "Run a terminal command on Roman's computer (" + ("PowerShell" if sys.platform == "win32" else "zsh/bash")
        + ") and get its output. Read-only commands (status, listing, versions, network info) run straight away; "
        "anything that adds, changes, installs, deletes or stops something needs his approval or is blocked; "
        "destructive commands never run. Prefer read-only commands, one clear command at a time.",
        {"type": "object", "properties": {"command": {"type": "string"},
                                          "cwd": {"type": "string", "description": "folder to run in (optional)"}},
         "required": ["command"]},
    )
    async def run_command(args):
        import json
        import os

        from alfred.config import expand

        cwd = args.get("cwd") or ccfg.get("cwd") or cfg["agent"]["workspace"]
        cwd = str(expand(cwd))
        if not os.path.isdir(cwd):
            cwd = str(expand(cfg["agent"]["workspace"]))
        result = await asyncio.to_thread(cmd_mod.run, str(args.get("command", "")), cwd,
                                         int(ccfg.get("timeout_s", 60)))
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    tools = []
    if cfg.get("windows", {}).get("enabled", True):
        tools += [list_windows, arrange_window]
    if ccfg.get("enabled", False):
        tools.append(run_command)
    if cfg.get("memory", {}).get("enabled", True):
        tools += [remember, forget]
    if cfg.get("apps", {}).get("enabled", True):
        tools.append(open_app)
    if scfg.get("enabled", True):
        tools.append(look_at_screen)
    if cfg.get("links", {}).get("enabled", True):
        tools.append(open_url)
    if not tools:
        return None, []
    return create_sdk_mcp_server(name="alfred", version="0.2.0", tools=tools), [f"mcp__alfred__{t.name}" for t in tools]
