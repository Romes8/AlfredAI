"""Alfred's own tools, exposed to Claude as an in-process MCP server named 'alfred'."""
from __future__ import annotations

import asyncio
import webbrowser
from urllib.parse import urlparse

from claude_agent_sdk import create_sdk_mcp_server, tool

from alfred.tools import apps as apps_mod
from alfred.tools import screen


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
        "Open a web page in Roman's default browser so he can see it - official sites, ticket pages, maps, "
        "videos, docs. Use it when he says 'open', 'show me', 'take me to', 'pull up', or when a link would "
        "clearly help (offer it). Only http/https URLs. Prefer official sources you found via web search.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    )
    async def open_url(args):
        url = str(args.get("url", "")).strip()
        if urlparse(url).scheme not in ("http", "https"):
            return {"content": [{"type": "text", "text": "Only http/https links can be opened."}], "is_error": True}
        ok = await asyncio.to_thread(webbrowser.open, url, 2)
        return {"content": [{"type": "text", "text": f"Opened {url}" if ok else f"Couldn't open {url}"}]}

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

    tools = []
    if cfg.get("apps", {}).get("enabled", True):
        tools.append(open_app)
    if scfg.get("enabled", True):
        tools.append(look_at_screen)
    if cfg.get("links", {}).get("enabled", True):
        tools.append(open_url)
    if not tools:
        return None, []
    return create_sdk_mcp_server(name="alfred", version="0.2.0", tools=tools), [f"mcp__alfred__{t.name}" for t in tools]
