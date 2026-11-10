#!/usr/bin/env bash
# Makes `alfred` work from any terminal on macOS / Linux.   Run once:  bash scripts/install_command.sh
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
py="$repo/.venv/bin/python"
[ -x "$py" ] || { echo "No virtualenv at $py - run scripts/setup_mac.sh first."; exit 1; }

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/alfred" <<EOF
#!/bin/sh
exec "$py" -m alfred "\$@"
EOF
chmod +x "$HOME/.local/bin/alfred"
echo "[ok] created ~/.local/bin/alfred"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
     echo "[ok] added ~/.local/bin to PATH in ~/.zshrc - open a new terminal (or: source ~/.zshrc)";;
esac
echo
echo "Try:  alfred wakeup   |   alfred status   |   alfred sleep"
