# Installing Alfred

Windows is the main platform. macOS is supported too ([jump to macOS](#macos)).
It takes about 15 minutes. At the end you type `alfred wakeup` in any terminal, hold **right Alt**, and talk.

---

## Windows

### Fast path (one command)
Install **Python 3.11+** (tick "Add python.exe to PATH"), **Node.js 18+** and **Git**, open a **new** PowerShell, then:
```powershell
cd $HOME\Documents
git clone https://github.com/Romes8/AlfredAI.git
cd AlfredAI
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```
The script sets up the venv and packages (plus GPU speech-to-text if you have an NVIDIA card), the Claude CLI and login
(a browser opens; paste the token back), the voice, a `config.yaml` for this PC, the tests, and the `alfred` command.
Then it **starts Alfred**. Hold right Alt and talk. The step-by-step version of the same thing is below.

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

### 7b. Shortcuts (no terminal needed)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1
```
- **Alfred** on your Desktop and in the Start menu: click once to wake him up, click again to put him to sleep.
  No console window appears. He says "online" when he's up, and a small notification confirms when he's asleep.
- **Ctrl+Alt+A** does the same from anywhere (pass `-Hotkey "Ctrl+Shift+F12"` to pick another).
- The script asks whether he should **start automatically when you log in** (`-Startup` / `-NoStartup` to skip the question).
- `alfred toggle` is the same thing from a terminal.

### 8. Use him
- **Hold right Alt**, talk, let go. The screen edges glow purple while he's listening.
- Hold right Alt while he's talking to **cut him off** and ask something else.
- When he asks permission (write a file, open a page), **tap right Alt** to approve. If you do nothing, the answer is no.
- Games: use **borderless windowed** mode, because exclusive fullscreen hides the overlay.

### Voice, speed and apps
- **Voice:** Kokoro is the default. It's free, runs on your PC and sounds natural (open-source, Apache 2.0).
  Try voices before picking one:
  ```
  alfred say "Yo, what are we getting into today?" --voice am_michael
  alfred say "Right then, what's the plan?" --voice bm_george --rate 1.2
  ```
  Then set `tts.voice` (and `tts.rate`) in `config.yaml`. Voices: British male `bm_george bm_lewis bm_daniel bm_fable`,
  British female `bf_emma bf_isabella bf_alice bf_lily`, American male `am_michael am_adam am_puck am_liam am_eric
  am_echo am_onyx am_fenrir`, American female `af_heart af_bella af_nicole af_sarah af_sky af_nova af_river`.
  `engine: piper` is lighter but more robotic. `engine: pyttsx3` uses the built-in Windows voices.
- **Speed:** `tts.rate`. 1.0 is normal, 1.1 is the default, 1.2–1.3 is brisk.
- **Pages:** when you ask him to find something and the page is worth seeing (tickets, shops, maps, a few options),
  he opens it in a **new Chrome window**, one tab per link. For simple facts he just answers.
  Pages from his own web search open straight away; any other link asks for a tap first (`links.auto_open`).
- **Apps:** "Alfred, open Spotify / Steam / VS Code". Only installed apps (from the Start menu) can be opened,
  never arbitrary commands. Set `apps.auto_open: false` to make him ask first, or `apps.enabled: false` to turn it off.

### Windows and terminal commands
**Windows (on by default):** "put Chrome on the left and Spotify on the right", "move VS Code to my second monitor",
"maximise Outlook", "minimise everything Discord". Monitors are numbered from the left. Closing a window asks first,
because the app could lose unsaved work.

**Terminal commands (off by default):** turn them on per machine in `config.yaml`:
```yaml
commands:
  enabled: true
  on_read_file: ask     # reading a file's contents (cat / Get-Content)
  on_change: ask        # adding, creating, installing, moving, stopping
  on_delete: ask        # deleting, uninstalling      (each: ask | deny)
```
Every command is checked before it runs. On Windows they run in PowerShell, hidden, and he tells you the result:
| Command type | Examples | What happens |
|---|---|---|
| Just looking | `git status`, `dir`, `ipconfig`, `Get-Process`, `pip list`, `nvidia-smi` | runs straight away |
| Reads a file | `cat`, `type`, `Get-Content` | `on_read_file` |
| Adds / changes | `mkdir`, `pip install`, `git commit`, `git push`, `> file`, `Stop-Process` | `on_change` |
| Deletes | `del`, `rm`, `Remove-Item`, `uninstall`, `git branch -D` | `on_delete` |
| Destructive | format, diskpart, registry edits, `shutdown`, `rm -rf /`, deleting a whole drive, `git push --force`, `git reset --hard`, download-and-run, encoded commands, `sudo`/admin | **never runs** |

Anything Alfred doesn't recognise counts as a change, so it asks. For a chain like `dir; del x`, the riskiest part decides.
When he asks, he reads out the **actual command**, not a description of it.

### Browser control (click, play videos, fill forms)
Off by default. Turn it on in `config.yaml` (needs Node.js, which you already have for Claude):
```yaml
browser_control:
  enabled: true
```
Alfred then drives **his own Chrome window**, using Microsoft's Playwright MCP and a separate profile in `~/.alfred/browser-profile`.
Your everyday Chrome isn't touched. Log in to sites (YouTube, etc.) in *his* window once and he stays logged in there.
The first use downloads the tool (~20 s).

Try: "Alfred, play some lofi on YouTube", "pause it", "fill in the contact form on this page with my details".

| Action | What happens |
|---|---|
| Open pages, click links / play / next, scroll, read the page | automatic |
| Type anything, fill forms, choose options, press Enter | asks (he says what he'll type, and where) |
| Click buy / pay / order / send / delete / confirm / subscribe / continue / proceed / add to cart / yes… | asks (`on_risky_click: deny` = never) |
| **Any** click or key press while on a checkout, cart, payment, billing, login or account-security page | asks |
| Run JavaScript on the page, upload files from your PC | blocked |

He never completes a purchase or payment: he stops at the last step for you to finish.
`use_my_chrome: true` lets him drive your real Chrome (with all your logins) through the "Playwright MCP Bridge"
extension. That's more convenient but riskier, so leave it off unless you need it.

### Your details for forms
Put them in `config.yaml` once and Alfred uses them whenever he fills something in, instead of asking you:
```yaml
profile:
  name: Roman Zvoda
  email: you@example.com
  phone: "+45 12 34 56 78"
  address:
    street: Example Street 1
    postal_code: "2100"
    city: Copenhagen
    country: Denmark
```
- They're only sent to Claude when he's actually filling in a form, not with every question.
- He never reads them out loud. Filling the form still asks for your tap ("Want me to fill in the form with your details?").
- Card numbers, CVV, passwords, PINs, bank/IBAN and ID numbers (CPR, passport…) are **refused**, even if you add them.
  You always type those yourself.

### He talks less
He speaks at most **2 sentences** per answer (`style.max_spoken_sentences`). The rest of a longer answer is on the overlay.
Say "explain", "tell me more", "in detail" or "walk me through" and he says up to 8 (`style.detail_spoken_sentences`).

### Shorter approval prompts
By default he doesn't read out links or button names when asking ("Want me to open that page?", "Want me to click that?").
The details are on the overlay. Terminal commands are the exception: he always says those exactly, for safety.
Set `approvals.say_details: true` to hear everything.

### Memory (between sessions)
Alfred keeps long-term notes in **`memory.md`** in his folder (`agent.workspace`, e.g. `Documents\Alfred\memory.md`).
- "Alfred, remember that Anna's birthday is March 3rd" saves a line. "Alfred, forget Anna's birthday" removes it.
- "What do you remember about me?" makes him sum up his notes.
- He also saves lasting preferences you mention (e.g. "I prefer metric"), but never anything he read on a page,
  in an email, in a file or on screen, and never passwords, keys or card numbers (those are refused).
- `alfred memory` shows the list. `alfred memory edit` opens the file. It's plain text, so add, fix or delete lines yourself.
  Changes load on his next start or when you say "new chat".
- `memory.confirm: true` makes him ask for a tap before every save. `memory.enabled: false` turns memory off.
- Everything in memory is sent to Claude with every question, so keep it to facts you're happy for him to know.

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

**Example: Google Calendar** (uses the open-source `@cocal/google-calendar-mcp` server)
1. One time in Google Cloud (free, about 5 min):
   - <https://console.cloud.google.com>: create a project (e.g. "Alfred").
   - *APIs & Services → Library*: **Google Calendar API**, then **Enable**.
   - *APIs & Services → OAuth consent screen*: External, app name + your email. Under *Audience / Test users*, add your Gmail.
   - *APIs & Services → Credentials → Create credentials → OAuth client ID*: type **Desktop app**, then **Download JSON**.
2. Run:
   ```powershell
   .venv\Scripts\python -m alfred connect google-calendar
   ```
   It picks up the `client_secret_….json` from your Downloads folder, opens Google sign-in once and adds the connector to `config.yaml`.
3. `alfred sleep`, `alfred wakeup`. Then: *"What's on my calendar tomorrow?"*, *"Am I free Friday at 3?"*,
   *"Put dentist on Thursday at 2pm"*. Creating, moving, deleting and answering invites asks first
   ("Want me to add "Dentist" on Thu 13 Nov at 14:00 to your calendar?").
4. Tip: on the OAuth consent screen, click **Publish app** (no verification needed for personal use). Otherwise Google
   makes you sign in again every 7 days. To re-sign-in: `alfred connect google-calendar`.

**Google Maps**
- **Directions & showing places (free, nothing to set up):** "Directions to Tivoli by bike" or "show me Nyhavn on the map"
  opens Google Maps in your browser straight away.
- **Your saved places** (starred, Want to go, your lists, Home/Work). Google has no API for these, so import an export:
  1. <https://takeout.google.com>: *Deselect all*, then tick **Saved** and **Maps (your places)**, then export and download the zip.
  2. `.venv\Scripts\python -m alfred import-places "C:\Users\roman\Downloads\takeout-....zip"`
  3. Ask: "what's on my Rome list?", "that bar I saved in Copenhagen?". Re-import whenever you've saved new places.
- **Live Maps data** (places, opening hours, travel times, weather) via Google's official *Maps Grounding Lite* server:
  `.venv\Scripts\python -m alfred connect google-maps` walks you through it. It needs **billing enabled** on the Google
  Cloud project, so set a budget alert. It's read-only.

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
