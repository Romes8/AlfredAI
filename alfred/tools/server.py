"""Alfred's own tools, exposed to Claude as an in-process MCP server named 'alfred'."""
from __future__ import annotations

import asyncio

from claude_agent_sdk import create_sdk_mcp_server, tool

from alfred.tools import screen


def build_server(cfg: dict):
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

    tools = [look_at_screen]
    return create_sdk_mcp_server(name="alfred", version="0.2.0", tools=tools), [f"mcp__alfred__{t.name}" for t in tools]
