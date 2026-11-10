"""Alfred's own tools, exposed to Claude as an in-process MCP server named 'alfred'."""
from __future__ import annotations

import asyncio
import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from alfred.tools import screen
from alfred.tools.iracing import IRacing


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]}


def build_server(cfg: dict, iracing: IRacing | None):
    scfg = cfg["screen"]

    @tool(
        "look_at_screen",
        "Take a screenshot so you can see what Roman sees. Use only when the question is about something "
        "visible on screen. target='window' captures just the active window, 'screen' the whole monitor.",
        {"type": "object", "properties": {
            "target": {"type": "string", "enum": ["screen", "window"], "default": "screen"},
            "monitor": {"type": "integer", "default": 1, "description": "1 = primary monitor"},
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
        "get_race_data",
        "Live iRacing telemetry: best lap, last lap, current lap, position, class position, delta to best, "
        "incidents, fuel (litres, %, per lap, laps left), session type, track, time remaining. "
        "ALWAYS use this for questions about the current race.",
        {"type": "object", "properties": {}},
    )
    async def get_race_data(args):  # noqa: ARG001
        if iracing is None:
            return _text({"connected": False, "message": "iRacing support is disabled in config."})
        return _text(await asyncio.to_thread(iracing.snapshot))

    @tool(
        "get_session_laps",
        "All laps Roman completed this iRacing session with times and fuel used, plus best lap and "
        "average of the last 5. Use for pace / consistency / 'what was lap N' questions.",
        {"type": "object", "properties": {}},
    )
    async def get_session_laps(args):  # noqa: ARG001
        if iracing is None:
            return _text({"laps": [], "message": "iRacing support is disabled in config."})
        return _text(await asyncio.to_thread(iracing.laps))

    tools = [look_at_screen, get_race_data, get_session_laps]
    return create_sdk_mcp_server(name="alfred", version="0.1.0", tools=tools), [f"mcp__alfred__{t.name}" for t in tools]
