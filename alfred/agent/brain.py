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
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)

from alfred.agent.permissions import PermissionGate
from alfred.audio.stream import SentenceStreamer
from alfred.config import expand
from alfred.persona import system_prompt

BASE_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "WebFetch"]


def builtin_tools(cfg: dict) -> list[str]:
    """Shell commands are off unless this machine's config turns them on."""
    return BASE_TOOLS + (["Bash"] if cfg["agent"].get("allow_commands") else [])

OnText = Callable[[str], Awaitable[None]]


def wants_smart_model(text: str, triggers: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in triggers)


class Brain:
    def __init__(self, cfg: dict, gate: PermissionGate, mcp_server, mcp_tool_names: list[str], bus=None) -> None:
        self.cfg = cfg
        self.bus = bus
        a = cfg["agent"]
        self.model = a["model"]
        self.smart_model = a["smart_model"]
        self.triggers = a["smart_triggers"]

        if os.environ.pop("ANTHROPIC_API_KEY", None):
            print("[brain] ANTHROPIC_API_KEY was set - ignoring it so Alfred runs on your Claude subscription.")
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            print("[brain] CLAUDE_CODE_OAUTH_TOKEN isn't set. If you see 'Not logged in', run `claude setup-token` "
                  "and export the token (see README).")

        workspace = expand(a["workspace"])
        workspace.mkdir(parents=True, exist_ok=True)
        extra_dirs = [str(expand(d)) for d in cfg["permissions"]["readable_dirs"] + cfg["permissions"]["writable_dirs"]
                      if expand(d).exists()]

        self.options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt(cfg),
            tools=builtin_tools(cfg),
            # Alfred's own read-only tools (screenshots) are approved by the permission policy itself,
            # so no allowed_tools entry is needed (one would bypass the gate entirely).
            mcp_servers=self._servers(cfg, mcp_server),
            can_use_tool=gate.can_use_tool,
            hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[gate.pre_tool_hook])],
                   "PostToolUse": [HookMatcher(matcher="WebSearch", hooks=[gate.post_tool_hook])]},
            permission_mode="default",
            cwd=str(workspace),
            add_dirs=extra_dirs,
            setting_sources=[],
            max_turns=a["max_turns"],
            include_partial_messages=True,  # live text deltas -> speak sentence by sentence
            # Capture the Claude CLI's stderr instead of letting it inherit Alfred's. In a windowless background
            # process on Windows there's no valid handle to inherit -> "WinError 50: The request is not supported".
            stderr=lambda line: print(f"[claude] {line.rstrip()}", flush=True),
        )
        self.client = ClaudeSDKClient(options=self.options)
        self._connected = False

    @staticmethod
    def _servers(cfg: dict, alfred_server) -> dict:
        from alfred.connectors import load_connectors

        servers = {c.name: c.server for c in load_connectors(cfg)}
        if alfred_server:
            servers["alfred"] = alfred_server
        return servers

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

    async def interrupt(self) -> None:
        """Stop the answer being generated (Roman talked over Alfred)."""
        try:
            await self.client.interrupt()
        except Exception as e:
            print(f"[brain] interrupt failed: {e}")

    async def ask(self, text: str, on_text: OnText) -> str:
        """Ask Claude. on_text is called with each SENTENCE as soon as it has been generated,
        so Alfred can start speaking while the rest of the answer is still being written."""
        smart = wants_smart_model(text, self.triggers)
        if smart:
            await self.client.set_model(self.smart_model)
        full: list[str] = []
        streamer = SentenceStreamer()
        streamed = False  # got live text deltas for the current assistant message
        try:
            await self.client.query(text)
            async for msg in self.client.receive_response():
                if isinstance(msg, StreamEvent):
                    ev = msg.event or {}
                    etype = ev.get("type")
                    if etype == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        streamed = True
                        for sentence in streamer.feed(ev["delta"].get("text", "")):
                            await on_text(sentence)
                    elif etype in ("content_block_stop", "message_stop"):
                        for sentence in streamer.flush():
                            await on_text(sentence)
                elif isinstance(msg, AssistantMessage):
                    for sentence in streamer.flush():
                        await on_text(sentence)
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            full.append(block.text)
                            if not streamed:  # no live deltas (e.g. streaming unavailable): speak it now
                                await on_text(block.text)
                        elif isinstance(block, ToolUseBlock) and self.bus:
                            self.bus.emit("tool", name=block.name)
                    streamed = False
                elif isinstance(msg, ResultMessage):
                    for sentence in streamer.flush():
                        await on_text(sentence)
                    if msg.is_error and not full:
                        err = msg.result or "something went wrong"
                        await on_text(f"Ah mate, hit a snag: {err}")
            if any("Not logged in" in t for t in full):
                print("[brain] Claude login missing: run `claude setup-token`, then "
                      "`export CLAUDE_CODE_OAUTH_TOKEN=...` in this terminal (and ~/.zshrc).")
        finally:
            if smart:
                await self.client.set_model(self.model)
        return "\n".join(full)
