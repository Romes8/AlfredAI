"""`alfred connect google-calendar` - one-time Google Calendar setup.

1. Finds your Google OAuth client file (the JSON you download from Google Cloud) and stores it in ~/.alfred/google/
2. Opens the Google sign-in once (via @cocal/google-calendar-mcp auth) - the token is stored on this PC
3. Adds the `google_calendar` connector to config.yaml (reads automatic, changes ask)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = "@cocal/google-calendar-mcp"
GOOGLE_DIR = Path.home() / ".alfred" / "google"
CREDS = GOOGLE_DIR / "gcp-oauth.keys.json"

CONNECTOR_BLOCK = """  google_calendar:
    command: npx
    args: ["-y", "{package}"]
    env: {{GOOGLE_OAUTH_CREDENTIALS: '{creds}'}}
    mode: ask_writes            # reading your calendar is automatic; creating / moving / deleting events asks
    description: "Roman's Google Calendar - events, availability, invitations"
"""

INSTRUCTIONS = """
You need a Google OAuth client file first (one time, ~5 minutes, free):
  1. https://console.cloud.google.com -> create a project (e.g. "Alfred")
  2. APIs & Services -> Library -> "Google Calendar API" -> Enable
  3. APIs & Services -> OAuth consent screen -> External -> fill in the app name + your email
     -> Audience / Test users -> add your own Gmail address
  4. APIs & Services -> Credentials -> Create credentials -> OAuth client ID -> Application type: Desktop app
     -> Create -> Download JSON
Then run:  alfred connect google-calendar "C:\\path\\to\\client_secret_....json"
(or just run it again - it finds the newest client_secret_*.json in your Downloads folder)
"""


def validate_client_file(path: Path) -> str | None:
    """None if OK, else what's wrong."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"couldn't read it as JSON ({e})"
    if "installed" in data:
        return None
    if "web" in data:
        return "that's a 'Web application' client - create one of type 'Desktop app' instead"
    return "it doesn't look like a Google OAuth client file"


def find_downloaded_client() -> Path | None:
    downloads = Path.home() / "Downloads"
    files = sorted(downloads.glob("client_secret_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def add_connector_to_config(config_path: Path, creds: Path) -> str:
    """Insert the google_calendar connector into config.yaml, keeping the user's comments. Returns what happened."""
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if re.search(r"^\s{2}google_calendar:\s*$", text, flags=re.M):
        return "already in config.yaml"
    block = CONNECTOR_BLOCK.format(package=PACKAGE, creds=str(creds).replace("'", "''"))
    insert = "connectors:\n" + block.rstrip("\n")
    # a function as the replacement, so Windows backslashes (C:\Users\...) are taken literally
    if re.search(r"^connectors:\s*\{\s*\}\s*$", text, flags=re.M):
        text = re.sub(r"^connectors:\s*\{\s*\}\s*$", lambda _m: insert, text, count=1, flags=re.M)
    elif re.search(r"^connectors:\s*$", text, flags=re.M):
        text = re.sub(r"^connectors:\s*$", lambda _m: insert, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n\nconnectors:\n" + block
    config_path.write_text(text, encoding="utf-8")
    return "added to config.yaml"


def _npx() -> str:
    return "npx.cmd" if sys.platform == "win32" else "npx"


def connect(config_path: Path, client_file: str | None = None, reauth: bool = False) -> int:
    print("== Google Calendar for Alfred ==")
    src = Path(client_file).expanduser() if client_file else None
    if src is None and not CREDS.exists():
        found = find_downloaded_client()
        if found:
            ans = input(f"Use {found}? [Y/n] ").strip().lower()
            src = found if ans in ("", "y", "yes") else None
    if src is not None:
        if not src.exists():
            print(f"[x] {src} doesn't exist")
            return 1
        problem = validate_client_file(src)
        if problem:
            print(f"[x] {src.name}: {problem}")
            return 1
        GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, CREDS)
        print(f"[ok] client file saved to {CREDS}")
    if not CREDS.exists():
        print(INSTRUCTIONS)
        return 1
    if not shutil.which(_npx()):
        print("[x] npx not found - install Node.js from https://nodejs.org and open a new terminal")
        return 1

    token = Path.home() / ".config" / "google-calendar-mcp" / "tokens.json"
    if token.exists() and not reauth:
        print(f"[ok] already signed in ({token}) - use --reauth to sign in again")
        code = 0
    else:
        print("[..] opening Google sign-in in your browser - pick your account and allow calendar access")
        env = {**os.environ, "GOOGLE_OAUTH_CREDENTIALS": str(CREDS)}
        code = subprocess.run([_npx(), "-y", PACKAGE, "auth"], env=env).returncode
    if code != 0:
        print("[x] sign-in didn't finish. If Google says 'access blocked', add your Gmail as a Test user on the "
              "OAuth consent screen, then run this again.")
        return 1
    print("[ok] signed in - the token is stored on this PC")
    print(f"[ok] connector {add_connector_to_config(config_path, CREDS)}")
    print("\nDone. Restart Alfred (alfred sleep / alfred wakeup) and try: \"Alfred, what's on my calendar tomorrow?\"")
    print("Tip: on the OAuth consent screen, 'Publish app' (no verification needed for personal use) stops Google "
          "asking you to sign in again every 7 days.")
    return 0


MAPS_BLOCK = """  google_maps:
    url: https://mapstools.googleapis.com/mcp
    headers: {X-Goog-Api-Key: "${GOOGLE_MAPS_API_KEY}"}
    mode: read_only
    allow: [compute_routes, resolve_names, search_places, lookup_weather]
    description: "Google Maps - find places, opening hours, routes and travel times, weather"
"""

MAPS_INSTRUCTIONS = """
Live Google Maps uses Google's official "Maps Grounding Lite" MCP server. One time in Google Cloud:
  1. Same project as Calendar is fine. Billing -> link a billing account (Google requires it for Maps;
     set a budget alert, e.g. 5 EUR, under Billing -> Budgets & alerts so there are no surprises).
  2. APIs & Services -> Library -> "Maps Grounding Lite API" -> Enable
  3. APIs & Services -> Credentials -> Create credentials -> API key -> Edit key ->
     API restrictions -> Restrict key -> tick "Maps Grounding Lite API" -> Save. Copy the key.
"""


def add_block(config_path: Path, name: str, block: str) -> str:
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if re.search(rf"^\s{{2}}{name}:\s*$", text, flags=re.M):
        return "already in config.yaml"
    insert = "connectors:\n" + block.rstrip("\n")
    if re.search(r"^connectors:\s*\{\s*\}\s*$", text, flags=re.M):
        text = re.sub(r"^connectors:\s*\{\s*\}\s*$", lambda _m: insert, text, count=1, flags=re.M)
    elif re.search(r"^connectors:\s*$", text, flags=re.M):
        text = re.sub(r"^connectors:\s*$", lambda _m: insert, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n\nconnectors:\n" + block
    config_path.write_text(text, encoding="utf-8")
    return "added to config.yaml"


def save_user_env(name: str, value: str) -> None:
    os.environ[name] = value
    if sys.platform == "win32":
        subprocess.run(["setx", name, value], stdout=subprocess.DEVNULL)
    else:
        rc = Path.home() / ".zshrc"
        with open(rc, "a", encoding="utf-8") as f:
            f.write(f'\nexport {name}="{value}"\n')


def connect_maps(config_path: Path) -> int:
    print("== Google Maps for Alfred ==")
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        print(MAPS_INSTRUCTIONS)
        key = input("Paste the API key (or press Enter to stop here): ").strip()
        if not key:
            return 1
        if not re.fullmatch(r"AIza[0-9A-Za-z_\-]{35}", key):
            print("[!] that doesn't look like a Google API key (they start with 'AIza') - saving it anyway")
        save_user_env("GOOGLE_MAPS_API_KEY", key)
        print("[ok] key saved as the GOOGLE_MAPS_API_KEY environment variable (not in config.yaml)")
    print(f"[ok] connector {add_block(config_path, 'google_maps', MAPS_BLOCK)}")
    print("\nOpen a NEW terminal, then: alfred sleep / alfred wakeup. Try: \"How long to Tivoli by bike?\"")
    return 0
