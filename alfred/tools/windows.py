"""Move, snap and arrange application windows ("Alfred, put Spotify on the right half", "move Chrome to my
second monitor", "maximise VS Code"). Windows only for now (Win32 API via ctypes - no extra packages).
"""
from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass

ACTIONS = ["focus", "maximize", "minimize", "restore", "left", "right", "top", "bottom", "top_left", "top_right",
           "bottom_left", "bottom_right", "center", "move_to_monitor", "close"]


@dataclass
class Win:
    handle: int
    title: str
    process: str


@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def target_rect(action: str, area: Rect) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) for a snap action inside a monitor's work area (the screen minus the taskbar)."""
    x, y, w, h = area.left, area.top, area.width, area.height
    hw, hh = w // 2, h // 2
    return {
        "left": (x, y, hw, h), "right": (x + hw, y, w - hw, h),
        "top": (x, y, w, hh), "bottom": (x, y + hh, w, h - hh),
        "top_left": (x, y, hw, hh), "top_right": (x + hw, y, w - hw, hh),
        "bottom_left": (x, y + hh, hw, h - hh), "bottom_right": (x + hw, y + hh, w - hw, h - hh),
        "center": (x + w // 6, y + h // 8, w * 2 // 3, h * 3 // 4),
    }.get(action)


def best_window(query: str, windows: list[Win]) -> tuple[Win | None, list[str]]:
    """Match what Roman said against window titles and app (process) names."""
    q = re.sub(r"^(the|my)\s+|\s+(window|app)$", "", query.lower().strip())
    if not q or not windows:
        return None, []
    for w in windows:  # exact app name first: "chrome" -> chrome.exe
        if w.process.lower().removesuffix(".exe") == q:
            return w, []
    hits = [w for w in windows if q in w.title.lower() or q in w.process.lower()]
    if hits:
        return hits[0], [h.title for h in hits[1:4]]
    names = {w.title.lower(): w for w in windows}
    close = difflib.get_close_matches(q, list(names), n=3, cutoff=0.5)
    if close:
        return names[close[0]], [names[c].title for c in close[1:]]
    return None, [w.title for w in windows[:8]]


# --------------------------------------------------------------------------- Win32
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
    WM_CLOSE = 0x0010

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    def _process_name(hwnd: int) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            import psutil

            return psutil.Process(pid.value).name()
        except Exception:
            return ""

    def list_windows() -> list[Win]:
        out: list[Win] = []
        PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # skip owned popups
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if title in ("Program Manager", "Windows Input Experience") or "Alfred" == title:
                return True
            out.append(Win(int(hwnd), title, _process_name(hwnd)))
            return True

        user32.EnumWindows(PROC(cb), 0)
        return out

    def monitors() -> list[Rect]:
        areas: list[Rect] = []
        PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                  wintypes.LPARAM)

        def cb(hmon, _hdc, _rect, _):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
            r = mi.rcWork
            areas.append(Rect(r.left, r.top, r.right, r.bottom))
            return True

        user32.EnumDisplayMonitors(0, 0, PROC(cb), 0)
        return sorted(areas, key=lambda a: (a.left, a.top))  # monitor 1 = leftmost

    def _monitor_of(hwnd: int) -> int:
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        for i, a in enumerate(monitors()):
            if a.left <= cx < a.right and a.top <= cy < a.bottom:
                return i
        return 0

    def _focus(hwnd: int) -> None:
        # Windows blocks background apps from stealing focus; a tap of Alt lifts that restriction.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)

    def _place(hwnd: int, x: int, y: int, w: int, h: int) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004 | 0x0040)  # NOZORDER | SHOWWINDOW
        _focus(hwnd)

    def arrange(query: str, action: str, monitor: int | None = None) -> dict:
        if action not in ACTIONS:
            return {"ok": False, "message": f"Unknown action. Use one of: {', '.join(ACTIONS)}"}
        win, alts = best_window(query, list_windows())
        if not win:
            return {"ok": False, "message": f"No open window matches '{query}'.", "open_windows": alts}
        h, mons = win.handle, monitors()
        idx = (monitor - 1) if monitor else _monitor_of(h)
        if not 0 <= idx < len(mons):
            return {"ok": False, "message": f"There are only {len(mons)} monitor(s)."}
        area = mons[idx]
        if action == "focus":
            _focus(h)
        elif action == "minimize":
            user32.ShowWindow(h, SW_MINIMIZE)
        elif action == "restore":
            user32.ShowWindow(h, SW_RESTORE)
            _focus(h)
        elif action == "close":
            user32.PostMessageW(h, WM_CLOSE, 0, 0)  # asks the app to close normally (it can still prompt to save)
        elif action in ("maximize", "move_to_monitor"):
            _place(h, area.left + 40, area.top + 40, area.width - 80, area.height - 80)  # move onto that monitor
            if action == "maximize" or monitor:
                user32.ShowWindow(h, SW_MAXIMIZE)
        else:
            _place(h, *target_rect(action, area))
        return {"ok": True, "window": win.title, "app": win.process, "action": action, "monitor": idx + 1,
                "monitors": len(mons)}

    def describe() -> dict:
        wins = list_windows()
        return {"monitors": len(monitors()),
                "windows": [{"title": w.title[:80], "app": w.process} for w in wins[:25]]}

else:
    def arrange(query: str, action: str, monitor: int | None = None) -> dict:  # noqa: ARG001
        return {"ok": False, "message": "Moving windows is only supported on Windows for now."}

    def describe() -> dict:
        return {"message": "Listing windows is only supported on Windows for now."}
