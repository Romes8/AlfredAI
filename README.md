# Alfred

Your voice-first buddy on top of Claude. Ask about **anything you see or want to know**, like "Alfred, what's this error?", "who's this player?" or "how do I get past this boss?", and he looks at your screen, searches the web if he needs to, and tells you. You never have to leave what you're doing.

- **Wake word:** "Alfred" (or push-to-talk `Ctrl+Alt+A`). You can say the question in the same breath.
- **Runs on your Claude subscription** through the Claude Agent SDK, with Haiku by default. Say "think hard" or "research" to switch to Sonnet for that one question.
- **Read-only by default.** He reads files in folders you allow. Any write, edit or command makes him ask out loud, and nothing happens until you say "yes".
- **Sees your screen:** when your question is about something you're looking at, he takes a screenshot (one monitor, the active window or all monitors) and answers from what he sees. He only does this when you ask.
- **Web search** for anything current. He can combine it with the screen: look first, then search for what's on it.
- **Overlay:** a small always-on-top, click-through panel showing what he heard, his answer and permission prompts.
- **Buddy personality:** casual, a bit of slang, short spoken answers. Edit `alfred/persona.py` to change it.

```
"Alfred" ──► faster-whisper ──► Claude Agent SDK (Haiku) ──► Piper voice + overlay
                                     │
                         permission gate (hook + can_use_tool)
                     read: auto · write/run: asks you · secrets/outside: blocked
                                     │
                 Files · Web search · look_at_screen
```

## Setup (Windows)

1. **Python 3.11+** and **Node.js 18+**, then the Claude Code CLI, which the Agent SDK runs on:
   ```powershell
   npm install -g @anthropic-ai/claude-code
   claude setup-token        # log in with your Claude Pro/Max account
   ```
   Then set the token it prints as a user environment variable `CLAUDE_CODE_OAUTH_TOKEN`.
   **Don't** set `ANTHROPIC_API_KEY`, because that bills the API instead. Alfred removes it at startup anyway.

2. **Install Alfred:**
   ```powershell
   git clone https://github.com/Romes8/AlfredAI && cd AlfredAI
   python -m venv .venv; .venv\Scripts\activate
   pip install -e ".[all]"
   ```
   For GPU speech-to-text you need the CUDA 12 + cuDNN runtime (`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`). Without it, Alfred falls back to the CPU.

3. **Voice (free):** download a Piper voice into `models/`. For example, `en_GB-alan-medium.onnx` plus its `.onnx.json` from
   <https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium>. If there's no model, Alfred uses Windows' built-in voices.

4. **Config:** `copy config.example.yaml config.yaml` and set `readable_dirs` / `writable_dirs`.

5. **Run:**
   ```powershell
   python -m alfred --text     # type to Alfred first: checks the Claude login, tools and permissions
   python -m alfred            # the real thing: voice + overlay
   ```

### Games and fullscreen apps
- Run games in **borderless windowed** mode. Exclusive fullscreen hides every overlay, and some games also block screenshots in that mode.
- Nothing is injected into the game. Alfred just takes a normal screenshot when you ask.
- Try: "Alfred, what's this?", "what does this error mean?", "who's the guy on screen?", "is this a good deal?"

### Spoken commands
- **"yes" / "nah" / "show me"** when he asks for permission. Silence or anything unclear counts as no.
- **"new chat"** wipes the conversation. **"never mind"** cancels.

## Wake word options
| backend | setup | cost to your PC |
|---|---|---|
| `whisper` (default) | none | transcribes speech while you talk, uses the GPU |
| `openwakeword` | train a "hey alfred" model (free notebook in the openWakeWord repo) → `models/hey_alfred.onnx` | tiny |
| `porcupine` | make "Hey Alfred" in the free Picovoice console → `.ppn` + `PICOVOICE_ACCESS_KEY` | tiny |

## Project layout
```
alfred/
  __main__.py        entry point (voice / --text)
  app.py             main loop: wake → listen → think → speak, spoken yes/no
  persona.py         Alfred's personality (system prompt)
  agent/brain.py     Claude Agent SDK session, model routing
  agent/permissions.py   read / ask / deny policy, hook + can_use_tool
  audio/             mic + VAD, wake word, faster-whisper, Piper TTS, yes/no parsing
  tools/             screenshots, MCP server
  overlay/           PyQt6 overlay
tests/               pytest -q
```

## Personal use only
Alfred logs in with your own Claude subscription. Don't share a running instance with other people. Anyone else needs their own login or an API key.
