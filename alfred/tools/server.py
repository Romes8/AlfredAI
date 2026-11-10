"""Alfred's own tools, exposed to Claude as an in-process MCP server named 'alfred'."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from claude_agent_sdk import create_sdk_mcp_server, tool

from alfred.tools import apps as apps_mod
from alfred.tools import browser
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
