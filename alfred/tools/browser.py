"""Open pages in a NEW, separate browser window (Chrome by default), one tab per link."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


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


def chrome_command(chrome: str, urls: list[str]) -> list[str]:
    if sys.platform == "darwin":
        return ["open", "-na", chrome, "--args", "--new-window", *urls]
    return [chrome, "--new-window", *urls]


def open_in_new_window(urls: list[str], browser: str = "chrome") -> str:
    """Open all urls as tabs in one new window. Returns which browser was used."""
    if browser == "chrome":
        chrome = find_chrome()
        if chrome:
            subprocess.Popen(chrome_command(chrome, urls), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "Chrome"
    # fallback: default browser, first link in a new window, the rest as tabs
    webbrowser.open_new(urls[0])
    for u in urls[1:]:
        webbrowser.open_new_tab(u)
    return "your default browser"
