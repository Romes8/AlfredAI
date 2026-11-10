# Alfred

Your voice-first buddy on top of Claude. Ask about **anything you see or want to know**, like "Alfred, what's this error?", "who's this player?" or "how do I get past this boss?", and he looks at your screen, searches the web if he needs to, and tells you. You never have to leave what you're doing.

- **Push-to-talk:** **hold right Alt** (Windows) / **right Option** (macOS) while you talk and let go when you're done. He hears nothing while the key isn't held, so surrounding voices are ignored. (Prefer tap-then-talk? Set `wake.trigger_mode: tap`.)
- **Tap mode (optional):** tap the key and just talk. AltGr shortcuts like AltGr+2 for `@` are ignored. Saying "Alfred" works too (optional), and you can say the question in the same breath.
- **Talks while he thinks:** he starts speaking as soon as the first sentence is ready, instead of waiting for the whole answer.
- **Interrupt him:** hold the key while he's talking and he stops right away and listens.
- **Connectors:** plug in HubSpot, email, calendar and other services through MCP servers, set up per machine. He reads automatically, and any change needs your tap. See [docs/INSTALL.md](docs/INSTALL.md#9-connectors-optional-hubspot-email-calendar-).
- **Remembers you:** "Alfred, remember that ..." saves to a plain `memory.md` you can edit (`alfred memory`).
- **Opens apps:** "Alfred, open Spotify" works with installed apps only, never commands.
- **Natural free voice:** Kokoro (local, open source). Try voices with `alfred say "hi" --voice am_michael`.
- **Shows you what he found:** when the page is worth seeing, he opens it in a new Chrome window. Pages from his own search open straight away; other links ask first.
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

## Install

**Full step-by-step guide: [docs/INSTALL.md](docs/INSTALL.md)** (Windows first, then macOS, updating, troubleshooting).

Quickest (Windows): clone, then `powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1`. It installs everything and starts him.

Manual quick version (Windows):
```powershell
npm install -g @anthropic-ai/claude-code; claude setup-token      # then: setx CLAUDE_CODE_OAUTH_TOKEN "<token>"
git clone https://github.com/Romes8/AlfredAI.git; cd AlfredAI
python -m venv .venv; .venv\Scripts\activate; pip install -e ".[all]"
copy config.example.yaml config.yaml                               # edit what Alfred may do on this PC
powershell -ExecutionPolicy Bypass -File scripts\install_command.ps1
alfred wakeup                                                      # new terminal; hold right Alt and talk
```
macOS: `bash scripts/setup_mac.sh` does it all (see the guide for the permissions).

| Command | |
|---|---|
| `alfred wakeup` | start in the background |
| `alfred sleep` | stop |
| `alfred status` / `alfred logs` | running? / last log lines |
| `alfred run` / `alfred text` | foreground voice / typed chat |
| `alfred connectors` | which outside services he can use on this machine |
| `alfred memory` / `alfred memory edit` | what he remembers / open the file |

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
  __main__.py        the `alfred` command (wakeup / sleep / status / logs / run / text)
  daemon.py          background start/stop, pid + log in ~/.alfred
  app.py             main loop: wake → listen → think → speak, spoken yes/no
  persona.py         Alfred's personality (system prompt)
  agent/brain.py     Claude Agent SDK session, model routing
  agent/permissions.py   read / ask / deny policy, hook + can_use_tool
  audio/             mic + VAD, trigger key, wake word, faster-whisper, Piper TTS, yes/no parsing
  tools/             screenshots, MCP server
  overlay/           PyQt6 info panel + purple listening glow
docs/INSTALL.md      full install guide
scripts/             setup_mac.sh, install_command.ps1 / .sh
tests/               pytest -q
```

## Personal use only
Alfred logs in with your own Claude subscription. Don't share a running instance with other people. Anyone else needs their own login or an API key.
