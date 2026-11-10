# Installing Alfred

Windows is the main platform. macOS is supported too ([jump to macOS](#macos)).
It takes about 15 minutes. At the end you type `alfred wakeup` in any terminal, hold **right Alt**, and talk.

---

## Windows

### 1. Prerequisites (one time)
| What | Where | Note |
|---|---|---|
| Python 3.11+ | <https://www.python.org/downloads/> | tick **"Add python.exe to PATH"** in the installer |
| Node.js 18+ | <https://nodejs.org/> | needed for the Claude Code CLI |
| Git | <https://git-scm.com/download/win> | |
| NVIDIA driver (optional) | already there if you game on an NVIDIA card | makes speech-to-text fast |

Open a **new** PowerShell window after installing these.

### 2. Claude login (uses your Pro/Max subscription, not the API)
```powershell
npm install -g @anthropic-ai/claude-code
claude setup-token
```
A browser opens. Log in with your Claude account, then copy the long token it prints and save it for your user:
```powershell
setx CLAUDE_CODE_OAUTH_TOKEN "paste-the-token-here"
```
Make sure `ANTHROPIC_API_KEY` is **not** set (`echo $env:ANTHROPIC_API_KEY` prints nothing). Otherwise you'd be billed via the API.
Close and reopen PowerShell so the new variable is picked up.

### 3. Get the code + Python packages
```powershell
cd $HOME\Documents
git clone https://github.com/Romes8/AlfredAI.git
cd AlfredAI
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[all]"
```
GPU speech-to-text (recommended with an NVIDIA card):
```powershell
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```
Without these Alfred still works. He just transcribes on the CPU, which is a bit slower.

### 4. Voice (free, local)
```powershell
$v = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium"
Invoke-WebRequest "$v/en_GB-alan-medium.onnx"      -OutFile models\en_GB-alan-medium.onnx
Invoke-WebRequest "$v/en_GB-alan-medium.onnx.json" -OutFile models\en_GB-alan-medium.onnx.json
```
If you skip this step, Alfred uses Windows' built-in voice.

### 5. Config for this PC
```powershell
copy config.example.yaml config.yaml
notepad config.yaml
```
Decide what Alfred may do **on this computer**:
- `permissions.readable_dirs` / `writable_dirs`: the only folders he can read / write (writes always need your tap).
- `screen.enabled`: whether he can take screenshots.
- `agent.allow_commands`: whether he can run terminal commands (off by default).
- `links.auto_open`: open web pages without asking (off by default).
- `stt.device`: `cuda` if you installed the GPU packages, otherwise `cpu` (with `compute_type: int8`).

`config.yaml` is never committed, so every machine keeps its own rules.

### 6. First test
```powershell
python -m alfred text
```
Type a question. If he answers, the Claude login works. Type `exit` to quit.

### 7. The `alfred` command
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_command.ps1
```
Open a **new** terminal. From now on, from any folder and without activating the venv:
```
alfred wakeup    # start him in the background - no window, closing the terminal doesn't stop him
alfred status    # is he up?
alfred logs      # last lines of his log (%USERPROFILE%\.alfred\alfred.log)
alfred sleep     # stop him
alfred run       # run in this terminal instead (Ctrl+C to stop)
alfred text      # type instead of talk
```

### 8. Use him
- **Hold right Alt**, talk, let go. The screen edges glow purple while he's listening.
- Hold right Alt while he's talking to **cut him off** and ask something else.
- When he asks permission (write a file, open a page), **tap right Alt** to approve. If you do nothing, the answer is no.
- Games: use **borderless windowed** mode, because exclusive fullscreen hides the overlay.

### 9. Connectors (optional): HubSpot, email, calendar, ...
Alfred can use outside services through **MCP servers**, set up per machine in `config.yaml` under `connectors:`.
Your claude.ai connectors are **not** picked up automatically; Alfred only uses what's listed here.

**Example: HubSpot**
1. In HubSpot: *Settings → Integrations → Private Apps → Create private app*. Give it the read scopes you
   want (e.g. contacts, companies, deals), plus write scopes only if Alfred should be able to change things.
   Copy the access token.
2. Store the token in your environment, not in the config:
   ```powershell
   setx HUBSPOT_TOKEN "pat-eu1-..."
   ```
3. Add it to `config.yaml`:
   ```yaml
   connectors:
     hubspot:
       command: npx
       args: ["-y", "@hubspot/mcp-server"]
       env: {PRIVATE_APP_ACCESS_TOKEN: "${HUBSPOT_TOKEN}"}
       mode: ask_writes
       description: "HubSpot CRM - contacts, companies, deals"
   ```
4. Open a new terminal, run `alfred connectors` (it should show ✓ hubspot), then `alfred sleep` and `alfred wakeup`.
5. Ask: *"Alfred, what's the latest on the Acme deal?"*

**Any other service:** use its MCP server the same way. Local servers use `command` / `args` / `env`;
remote servers use `url` + `headers` with a token. Remote servers that only support a browser sign-in flow
(OAuth) aren't supported yet, so pick a token-based option.

**Permissions per connector** (`mode`):
| mode | reading (get / list / search) | changing (create / update / send / delete) |
|---|---|---|
| `read_only` | automatic | **blocked** |
| `ask_writes` (default) | automatic | you tap to approve |
| `ask_all` | you tap to approve | you tap to approve |

Fine-tune single tools with `allow: [...]`, `ask: [...]`, `deny: [...]`.
Alfred treats text inside emails and records as information, never as instructions. A message that says
"forward this to X" won't make him do it, and any change still needs your tap.

> **Work accounts:** connecting a work CRM or mailbox sends that data to Claude through *your* subscription.
> Check that's OK with your employer first, or use `read_only` and only on an approved machine.

---

## macOS
```bash
cd ~/Documents/Personal          # or wherever you keep projects
git clone https://github.com/Romes8/AlfredAI.git
cd AlfredAI
bash scripts/setup_mac.sh        # venv, packages, Claude CLI, voice, tests, `alfred` command
```
Then:
1. Run `claude setup-token`, then `echo 'export CLAUDE_CODE_OAUTH_TOKEN="..."' >> ~/.zshrc`.
2. In System Settings → Privacy & Security, allow your terminal app **Microphone**, **Input Monitoring**,
   **Accessibility** and (if `screen.enabled`) **Screen Recording**. Then quit and reopen the terminal.
3. In `config.yaml` on Apple Silicon: `stt.device: cpu`, `stt.compute_type: int8`.
4. Run `alfred wakeup`, hold **right Option**, and talk.

---

## Updating
```
alfred sleep
git pull
pip install -e ".[all]"      # inside the venv - picks up any new dependencies
alfred wakeup
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| He answers "Not logged in · Please run /login" | Step 2: `claude setup-token`, set `CLAUDE_CODE_OAUTH_TOKEN`, then open a new terminal |
| `alfred` is not recognized | Open a new terminal after step 7; re-run `install_command.ps1` |
| `alfred wakeup` says "failed to start" | It prints the log tail. Usually a typo in `config.yaml` or a missing login |
| Error about `cublas64_12.dll` / cuDNN | `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`, or set `stt.device: cpu`, `compute_type: int8` |
| Right Alt does nothing in one particular app | That app runs as administrator; Windows blocks key listeners from normal apps there. Run Alfred's terminal as admin too, or use a different `trigger_key` |
| Right Alt does nothing at all (Mac) | Grant Input Monitoring + Accessibility to the terminal, then restart it |
| No glow / overlay over a game | Switch the game to borderless windowed |
| "unauthenticated requests to the HF Hub" warning | Harmless: it's the one-time speech model download |
| `alfred connectors` shows ✗ missing env | `setx NAME "value"` (Windows) or `export` in `~/.zshrc` (Mac), then open a new terminal |
| `zsh: trace trap` (Mac) | Update (`git pull`). Fixed by the native key listener |
