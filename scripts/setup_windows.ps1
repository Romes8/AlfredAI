# One-shot Windows setup for Alfred: installs everything and starts him.
# From the repo folder:   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
Write-Host "== Alfred setup (Windows) ==" -ForegroundColor Magenta

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Host "[x] $cmd not found - $hint" -ForegroundColor Red; exit 1 }
}

# 1) Prerequisites
Need git  "install Git from https://git-scm.com/download/win, then open a new PowerShell"
Need node "install Node.js 18+ from https://nodejs.org, then open a new PowerShell"
$py = $null
foreach ($c in @("py -3.13", "py -3.12", "py -3.11", "python")) {
    $parts = $c.Split(" ")
    try {
        & $parts[0] $parts[1..9] -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $parts; break }
    } catch {}
}
if (-not $py) { Write-Host "[x] Need Python 3.11+ from https://www.python.org (tick 'Add python.exe to PATH')" -ForegroundColor Red; exit 1 }
Write-Host "[ok] Python: $(& $py[0] $py[1..9] --version)"

# 2) This repo always pushes as Romes8 (repo-local, your other GitHub account is untouched)
git remote set-url origin https://Romes8@github.com/Romes8/AlfredAI.git
git config credential.https://github.com.username Romes8
Write-Host "[ok] repo pinned to GitHub account Romes8"

# 3) Virtualenv + packages
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $py[0] $py[1..9] -m venv .venv }
$vpy = Join-Path $repo ".venv\Scripts\python.exe"
& $vpy -m pip install -q -U pip
& $vpy -m pip install -q -e ".[all,dev]"
$gpu = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($gpu) {
    & $vpy -m pip install -q nvidia-cublas-cu12 nvidia-cudnn-cu12
    Write-Host "[ok] packages installed (+ NVIDIA GPU speech-to-text)"
} else {
    Write-Host "[ok] packages installed (no NVIDIA GPU found - speech-to-text on CPU)"
}

# 4) Claude Code CLI + login on your subscription
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { npm install -g @anthropic-ai/claude-code }
if ($env:ANTHROPIC_API_KEY) { Write-Host "[!] ANTHROPIC_API_KEY is set - Alfred ignores it, but remove it to be safe" -ForegroundColor Yellow }
$token = [Environment]::GetEnvironmentVariable("CLAUDE_CODE_OAUTH_TOKEN", "User")
if (-not $token) {
    Write-Host "`nLogging in to Claude (a browser opens - use your Claude Pro/Max account)..." -ForegroundColor Cyan
    claude setup-token
    $token = Read-Host "Paste the token it printed (starts with sk-ant-)"
    if (-not $token) { Write-Host "[x] No token - run this script again when ready" -ForegroundColor Red; exit 1 }
    [Environment]::SetEnvironmentVariable("CLAUDE_CODE_OAUTH_TOKEN", $token.Trim(), "User")
}
$env:CLAUDE_CODE_OAUTH_TOKEN = $token.Trim()
Write-Host "[ok] Claude login saved"

# 5) Piper voice (free, local)
New-Item -ItemType Directory -Force -Path models | Out-Null
$v = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium"
foreach ($f in @("en_GB-alan-medium.onnx", "en_GB-alan-medium.onnx.json")) {
    if (-not (Test-Path "models\$f")) { Invoke-WebRequest "$v/$f" -OutFile "models\$f" -UseBasicParsing }
}
$k = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
foreach ($f in @("kokoro-v1.0.onnx", "voices-v1.0.bin")) {
    if (-not (Test-Path "models\$f")) { Write-Host "  downloading $f ..."; Invoke-WebRequest "$k/$f" -OutFile "models\$f" -UseBasicParsing }
}
Write-Host "[ok] voices downloaded (Kokoro natural voice + Piper backup)"

# 6) Config for THIS PC (only created if missing - your edits are never overwritten)
$alfredDir = Join-Path $env:USERPROFILE "Documents\Alfred"
New-Item -ItemType Directory -Force -Path $alfredDir | Out-Null
if (-not (Test-Path "config.yaml")) {
    $c = Get-Content config.example.yaml -Raw
    $c = $c -replace "(?m)^  backend: whisper\s*$", "  backend: none"
    if (-not $gpu) {
        $c = $c -replace "device: cuda ", "device: cpu  " -replace "compute_type: float16", "compute_type: int8"
    }
    Set-Content config.yaml $c -Encoding UTF8
    Write-Host "[ok] created config.yaml (Alfred's folder: $alfredDir) - edit it to change what he may do on this PC"
} else {
    Write-Host "[ok] keeping your existing config.yaml"
}

# 7) Tests
& $vpy -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "[!] some tests failed - Alfred may still run, send me the output" -ForegroundColor Yellow }

# 8) `alfred` command for every terminal
& (Join-Path $PSScriptRoot "install_command.ps1")

# 9) Start him
Write-Host "`nStarting Alfred..." -ForegroundColor Magenta
& $vpy -m alfred wakeup
Write-Host "`nHold RIGHT ALT and talk. In NEW terminals:  alfred status | alfred logs | alfred sleep" -ForegroundColor Green
