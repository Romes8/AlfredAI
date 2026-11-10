"""Open installed applications by name ("Alfred, open Spotify").

Only apps that are installed and listed by the OS can be opened - Windows Start menu apps (Get-StartApps) or
macOS .app bundles - with no arguments. Alfred can't run arbitrary programs or commands this way.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_cache: tuple[float, dict[str, str]] | None = None  # (timestamp, {display name: launch id})
CACHE_S = 300

# Things people say vs. what the app is called
ALIASES = {
    "chrome": "google chrome", "vs code": "visual studio code", "vscode": "visual studio code",
    "code": "visual studio code", "word": "microsoft word", "excel": "microsoft excel",
    "powerpoint": "microsoft powerpoint", "outlook": "microsoft outlook", "teams": "microsoft teams",
    "edge": "microsoft edge", "terminal": "terminal", "explorer": "file explorer", "files": "file explorer",
    "calculator": "calculator", "settings": "settings", "notepad": "notepad",
}


def _windows_apps() -> dict[str, str]:
    ps = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
          "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    data = json.loads(out or "[]")
    if isinstance(data, dict):
        data = [data]
    return {d["Name"]: d["AppID"] for d in data if d.get("Name") and d.get("AppID")}


def _mac_apps() -> dict[str, str]:
    apps: dict[str, str] = {}
    for root in (Path("/Applications"), Path("/System/Applications"), Path("/System/Applications/Utilities"),
                 Path.home() / "Applications"):
        if root.is_dir():
            for app in root.glob("*.app"):
                apps[app.stem] = str(app)
    return apps


def installed_apps(refresh: bool = False) -> dict[str, str]:
    global _cache
    if not refresh and _cache and time.time() - _cache[0] < CACHE_S:
        return _cache[1]
    if sys.platform == "win32":
        apps = _windows_apps()
    elif sys.platform == "darwin":
        apps = _mac_apps()
    else:
        apps = {}
    _cache = (time.time(), apps)
    return apps


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def match_app(query: str, apps: dict[str, str]) -> tuple[str | None, list[str]]:
    """Best installed app for what was said -> (name or None, close alternatives)."""
    q = _norm(query)
    q = re.sub(r"^(the|my)\s+", "", q)
    q = re.sub(r"\s+(app|application|program)$", "", q)
    q = ALIASES.get(q, q)
    names = {_norm(n): n for n in apps}
    if q in names:
        return names[q], []
    # whole-word containment: "spotify" -> "Spotify Premium", "word" doesn't match "WordPad"
    hits = [n for k, n in names.items() if re.search(rf"\b{re.escape(q)}\b", k)]
    if len(hits) == 1:
        return hits[0], []
    if hits:
        hits.sort(key=len)  # shortest = most likely the main app ("Steam" over "Steam Support Center")
        return hits[0], hits[1:4]
    close = difflib.get_close_matches(q, list(names), n=3, cutoff=0.75)
    if close:
        return names[close[0]], [names[c] for c in close[1:]]
    return None, [names[c] for c in difflib.get_close_matches(q, list(names), n=3, cutoff=0.5)]


def open_app(query: str) -> dict:
    apps = installed_apps()
    if not apps:
        apps = installed_apps(refresh=True)
    name, alts = match_app(query, apps)
    if not name:
        return {"opened": False, "message": f"No installed app matches '{query}'.", "did_you_mean": alts}
    target = apps[name]
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-a", target])
    else:
        return {"opened": False, "message": "Opening apps isn't supported on this OS yet."}
    return {"opened": True, "app": name, "other_matches": alts}
