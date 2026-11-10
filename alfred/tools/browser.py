"""Open pages in ALFRED'S OWN Chrome window: the first link opens the window, every later link becomes a new tab
in that same window.

How: Alfred's links use their own Chrome profile folder (~/.alfred/chrome-links). Chrome runs one process per
profile folder, so new links are handed to the already-open Alfred window as tabs - never into your own Chrome
windows. (Being a separate profile, sites aren't logged in there until you log in once in that window.)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

DEFAULT_PROFILE = Path.home() / ".alfred" / "chrome-links"


def find_chrome() -> str | None:
    """Path to Chrome on this machine, or None."""
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return None
    if sys.platform == "darwin":
        app = Path("/Applications/Google Chrome.app")
        return str(app) if app.exists() else None
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def chrome_command(chrome: str, urls: list[str], profile_dir: Path | None = DEFAULT_PROFILE,
                   new_window: bool = False) -> list[str]:
    flags = ["--no-first-run", "--no-default-browser-check"]
    if profile_dir:
        flags.insert(0, f"--user-data-dir={profile_dir}")
    if new_window:
        flags.append("--new-window")
    if sys.platform == "darwin":
        return ["open", "-na", chrome, "--args", *flags, *urls]
    return [chrome, *flags, *urls]


def open_in_alfred_window(urls: list[str], browser: str = "chrome", window: str = "alfred") -> str:
    """window: 'alfred' = Alfred's own window, new links as tabs (default); 'new' = a new window every time
    (in your normal Chrome profile). Returns which browser was used."""
    if browser == "chrome":
        chrome = find_chrome()
        if chrome:
            if window == "new":
                cmd = chrome_command(chrome, urls, profile_dir=None, new_window=True)
            else:
                DEFAULT_PROFILE.mkdir(parents=True, exist_ok=True)
                cmd = chrome_command(chrome, urls, profile_dir=DEFAULT_PROFILE)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "Chrome"
    for u in urls:  # fallback: default browser, as tabs
        webbrowser.open_new_tab(u)
    return "your default browser"


open_in_new_window = open_in_alfred_window  # backwards compatible name
