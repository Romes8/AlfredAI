# Alfred

Your voice-first buddy on top of Claude. Ask about **anything you see or want to know**, like "Alfred, what's this error?", "who's this player?" or "how do I get past this boss?", and he looks at your screen, searches the web if he needs to, and tells you. You never have to leave what you're doing.

- **Push-to-talk:** **hold right Alt** (Windows) / **right Option** (macOS) while you talk and let go when you're done. He hears nothing while the key isn't held, so surrounding voices are ignored. (Prefer tap-then-talk? Set `wake.trigger_mode: tap`.)
- **Tap mode (optional):** tap the key and just talk. AltGr shortcuts like AltGr+2 for `@` are ignored. Saying "Alfred" works too (optional), and you can say the question in the same breath.
- **Talks while he thinks:** he starts speaking as soon as the first sentence is ready, instead of waiting for the whole answer.
- **Interrupt him:** hold the key while he's talking and he stops right away and listens.
- **Opens websites:** "Alfred, open the Colosseum ticket page" opens it in your default browser. He asks first (tap to approve) unless you set `links.auto_open: true`.
- **Purple edge glow** around every monitor while he's actively listening, so you always know when he's hearing you.
- **Runs on your Claude subscription** through the Claude Agent SDK, with Haiku by default. Say "think hard" or "research" to switch to Sonnet for that one question.
- **Locked down by default.** He reads only the folders you allow on that machine. Writes and opening URLs need your approval, terminal commands are off, and secrets files are always blocked.
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

## Setup (Windows or macOS)

1. **Python 3.11+** and **Node.js 18+**, then the Claude Code CLI, which the Agent SDK runs on:
   ```powershell
   npm install -g @anthropic-ai/claude-code
   claude setup-token        # log in with your Claude Pro/Max account
   ```
   Then set the token it prints as an environment variable `CLAUDE_CODE_OAUTH_TOKEN` (Windows: user env var; macOS: `export` it in `~/.zshrc`).
   **Don't** set `ANTHROPIC_API_KEY`, because that bills the API instead. Alfred removes it at startup anyway.

2. **Install Alfred:**
   ```powershell
   git clone https://github.com/Romes8/AlfredAI && cd AlfredAI
   python -m venv .venv; .venv\Scripts\activate        # macOS: source .venv/bin/activate
   pip install -e ".[all]"
   ```
   **macOS permissions:** in System Settings → Privacy & Security, give your terminal (or Python) **Microphone**, **Input Monitoring** + **Accessibility** (for the right Option key) and **Screen Recording** (for screenshots). On Apple Silicon, set `stt.device: cpu` and `stt.compute_type: int8`.
   For GPU speech-to-text you need the CUDA 12 + cuDNN runtime (`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`). Without it, Alfred falls back to the CPU.

3. **Voice (free):** download a Piper voice into `models/`. For example, `en_GB-alan-medium.onnx` plus its `.onnx.json` from
   <https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium>. If there's no model, Alfred uses Windows' built-in voices.

4. **Config (per machine):** `copy config.example.yaml config.yaml` and set what Alfred may do on *this* computer:
   which folders he can read/write, whether he can take screenshots (`screen.enabled`) and whether he can run
   commands (`agent.allow_commands`, off by default). `config.yaml` is git-ignored, so each PC keeps its own.

5. **Run:**
   ```powershell
   python -m alfred --text     # type to Alfred first: checks the Claude login, tools and permissions
   python -m alfred            # the real thing: voice + overlay
   ```

### Games and fullscreen apps
- Run games in **borderless windowed** mode. Exclusive fullscreen hides every overlay, and some games also block screenshots in that mode.
- Nothing is injected into the game. Alfred just takes a normal screenshot when you ask.
- Try: "Alfred, what's this?", "what does this error mean?", "who's the guy on screen?", "is this a good deal?"

### Triggering and the glow
- Hold right Alt / right Option → the screen edges glow purple → ask your question → let go. The glow is on exactly while he's hearing you.
- The glow also comes on while he waits for your yes/no on a permission prompt.
- To use only the key (no always-on wake word, lowest CPU/GPU), set `wake.backend: none`.
- To use a different key, change `wake.trigger_key` (`right_ctrl`, `right_cmd`, `f13`).
- macOS: the glow doesn't show over apps in native fullscreen Spaces. Use a normal or maximised window.

### Approving things
- Writes and opening a specific URL need approval. By default you **tap right Alt / right Option** to approve,
  so a "yes" from a video or another person can't approve anything. Saying "no" or staying silent means no.
  Set `permissions.approval: voice` or `both` to approve by saying "yes".
- Web *searches* run without asking. Opening a specific page asks first, because a URL can carry data out.

### Spoken commands
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
  audio/             mic + VAD, trigger key, wake word, faster-whisper, Piper TTS, yes/no parsing
  tools/             screenshots, MCP server
  overlay/           PyQt6 info panel + purple listening glow
tests/               pytest -q
```

## Personal use only
Alfred logs in with your own Claude subscription. Don't share a running instance with other people. Anyone else needs their own login or an API key.
