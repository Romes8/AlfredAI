"""On-demand screenshots for Claude's vision. Never runs unless Claude asks for it."""
from __future__ import annotations

import base64
import io
import sys


def _foreground_window_rect() -> dict | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        hwnd = user32.GetForegroundWindow()
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w > 50 and h > 50:
            return {"left": rect.left, "top": rect.top, "width": w, "height": h}
    except Exception:
        pass
    return None


def capture(target: str = "screen", monitor: int = 1, max_width: int = 1280, quality: int = 70) -> tuple[str, str]:
    """Return (base64 jpeg, description). target: 'screen' (one monitor) or 'window' (active window)."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        region = _foreground_window_rect() if target == "window" else None
        if region is None:
            mons = sct.monitors
            region = mons[monitor] if 0 < monitor < len(mons) else mons[1]
        shot = sct.grab(region)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    desc = f"{target} capture {img.width}x{img.height}"
    return base64.b64encode(buf.getvalue()).decode(), desc
