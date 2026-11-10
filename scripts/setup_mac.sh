#!/usr/bin/env bash
# One-shot macOS setup for Alfred. Run from anywhere:  bash scripts/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== Alfred setup (macOS) =="

# 1) GitHub: this repo always uses the Romes8 account (repo-local only - your other account is untouched)
git remote set-url origin https://Romes8@github.com/Romes8/AlfredAI.git
git config credential.https://github.com.username Romes8
echo "[ok] this repo pushes as Romes8 (global gh/git accounts unchanged)"

# 2) Python 3.11+
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "[x] Need Python 3.11+  ->  brew install python@3.12"; exit 1; fi
echo "[ok] using $($PY --version)"

# 3) virtualenv + dependencies
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q -U pip
python -m pip install -q -e ".[all,dev]"
echo "[ok] python packages installed"

# 4) Claude Code CLI (the Agent SDK runs on it)
if ! command -v claude >/dev/null 2>&1; then
  if command -v npm >/dev/null 2>&1; then npm install -g @anthropic-ai/claude-code; else echo "[!] install Node.js, then: npm install -g @anthropic-ai/claude-code"; fi
fi
command -v claude >/dev/null 2>&1 && echo "[ok] claude CLI: $(claude --version 2>/dev/null | head -1)"

# 5) Piper voice
mkdir -p models
for f in en_GB-alan-medium.onnx en_GB-alan-medium.onnx.json; do
  [ -s "models/$f" ] || curl -sSfL -o "models/$f" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/$f"
done
echo "[ok] Piper voice in models/"

# 6) config + Alfred's writable folder
[ -f config.yaml ] || cp config.example.yaml config.yaml
mkdir -p "$HOME/Documents/Personal/Alfred"

# 7) tests
python -m pytest -q

cat <<'EOF'

== Almost there ==
1. Claude login (uses your subscription, not the API):
     claude setup-token
   then add to ~/.zshrc:   export CLAUDE_CODE_OAUTH_TOKEN="<token it printed>"
   and make sure ANTHROPIC_API_KEY is NOT set.
2. System Settings > Privacy & Security - allow your terminal app:
     Microphone, Input Monitoring, Accessibility, Screen Recording
   (then quit and reopen the terminal)
3. Test:
     source .venv/bin/activate
     python -m alfred --text     # typed chat first
     python -m alfred            # voice: tap RIGHT OPTION, watch for the purple glow
EOF
