"""Alfred's brain: a persistent Claude Agent SDK session running on Roman's Claude subscription."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from alfred.agent.permissions import PermissionGate
from alfred.config import expand
from alfred.persona import system_prompt

BUILTIN_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "WebSearch", "WebFetch"]

OnText = Callable[[str], Awaitable[None]]


def wants_smart_model(text: str, triggers: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in triggers)


class Brain:
    def __init__(self, cfg: dict, gate: PermissionGate, mcp_server, mcp_tool_names: list[str], bus=None,
                 racing_check: Callable[[], bool] | None = None) -> None:
        self.cfg = cfg
        self.bus = bus
        self.racing_check = racing_check
        a = cfg["agent"]
        self.model = a["model"]
        self.smart_model = a["smart_model"]
        self.triggers = a["smart_triggers"]

        if os.environ.pop("ANTHROPIC_API_KEY", None):
            print("[brain] ANTHROPIC_API_KEY was set - ignoring it so Alfred runs on your Claude subscription.")

        workspace = expand(a["workspace"])
        workspace.mkdir(parents=True, exist_ok=True)
        extra_dirs = [str(expand(d)) for d in cfg["permissions"]["readable_dirs"] + cfg["permissions"]["writable_dirs"]
                      if expand(d).exists()]

        self.options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt(cfg["name"]),
            tools=BUILTIN_TOOLS,
            allowed_tools=mcp_tool_names,  # Alfred's own read-only tools run without asking
            mcp_servers={"alfred": mcp_server},
            can_use_tool=gate.can_use_tool,
            hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[gate.pre_tool_hook])]},
            permission_mode="default",
            cwd=str(workspace),
            add_dirs=extra_dirs,
            setting_sources=[],
            max_turns=a["max_turns"],
        )
        self.client = ClaudeSDKClient(options=self.options)
        self._connected = False

    async def start(self) -> None:
        await self.client.connect()
        self._connected = True

    async def stop(self) -> None:
        if self._connected:
            await self.client.disconnect()
            self._connected = False

    async def reset(self) -> None:
        """Forget the conversation (new session)."""
        await self.stop()
        self.client = ClaudeSDKClient(options=self.options)
        await self.start()

    async def ask(self, text: str, on_text: OnText) -> str:
        smart = wants_smart_model(text, self.triggers)
        if smart:
            await self.client.set_model(self.smart_model)
        prompt = text
        if self.racing_check and self.racing_check():
            prompt = f"[Roman is on track in iRacing right now - answer in a few words]\n{text}"
        full: list[str] = []
        try:
            await self.client.query(prompt)
            async for msg in self.client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            full.append(block.text)
                            await on_text(block.text)
                        elif isinstance(block, ToolUseBlock) and self.bus:
                            self.bus.emit("tool", name=block.name)
                elif isinstance(msg, ResultMessage):
                    if msg.is_error and not full:
                        err = msg.result or "something went wrong"
                        await on_text(f"Ah mate, hit a snag: {err}")
        finally:
            if smart:
                await self.client.set_model(self.model)
        return "\n".join(full)
