"""Purple glow around the edges of every screen while Alfred is actively listening.

One frameless, transparent, click-through, always-on-top window per monitor. It never takes focus.
"""
from __future__ import annotations

import math
import sys
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

PURPLE = (168, 85, 247)  # tailwind purple-500


class _EdgeWindow(QWidget):
    def __init__(self, screen, thickness: int, color: tuple[int, int, int], intensity: float) -> None:
        super().__init__()
        self.thickness = thickness
        self.color = color
        self.intensity = max(0.0, min(1.0, intensity))
        self.level = 0.0  # 0..1, animated by EdgeGlow
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint  # macOS draws a dark shadow line around frameless windows
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def _grad(self, x1, y1, x2, y2) -> QLinearGradient:
        r, g, b = self.color
        grad = QLinearGradient(QPointF(x1, y1), QPointF(x2, y2))
        peak = 230 * self.level * self.intensity
        # smooth ease-out falloff (many stops) so there's no visible band where the glow ends
        for i in range(9):
            t = i / 8
            grad.setColorAt(t, QColor(r, g, b, int(peak * (1 - t) ** 2.2)))
        return grad

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        if self.level <= 0.01:
            return
        w, h, t = self.width(), self.height(), self.thickness
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._grad(0, 0, 0, t)); p.drawRect(QRectF(0, 0, w, t))            # top
        p.setBrush(self._grad(0, h, 0, h - t)); p.drawRect(QRectF(0, h - t, w, t))    # bottom
        p.setBrush(self._grad(0, 0, t, 0)); p.drawRect(QRectF(0, 0, t, h))            # left
        p.setBrush(self._grad(w, 0, w - t, 0)); p.drawRect(QRectF(w - t, 0, t, h))    # right
        # soft extra bloom in the corners
        r, g, b = self.color
        for cx, cy in ((0, 0), (w, 0), (0, h), (w, h)):
            rg = QRadialGradient(QPointF(cx, cy), t * 2.2)
            for i in range(7):
                k = i / 6
                rg.setColorAt(k, QColor(r, g, b, int(100 * self.level * self.intensity * (1 - k) ** 2)))
            p.setBrush(rg)
            p.drawEllipse(QPointF(cx, cy), t * 2.2, t * 2.2)
        p.end()


class EdgeGlow:
    """Call set_active(True/False). Fades in, pulses gently while active, fades out."""

    def __init__(self, thickness: int = 36, color: tuple[int, int, int] = PURPLE, intensity: float = 0.8) -> None:
        self.windows = [_EdgeWindow(s, thickness, color, intensity) for s in QGuiApplication.screens()]
        self.active = False
        self.level = 0.0
        self._t0 = time.monotonic()
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 fps while visible

    def set_active(self, active: bool) -> None:
        if active and not self.active:
            self._t0 = time.monotonic()
            for w in self.windows:
                w.show()
                w.raise_()
                if sys.platform == "darwin":
                    _mac_above_menu_bar(w)
        self.active = active

    def _tick(self) -> None:
        target = 0.0
        if self.active:
            pulse = 0.5 + 0.5 * math.sin((time.monotonic() - self._t0) * 2 * math.pi / 1.6)
            target = 0.7 + 0.3 * pulse
        step = 0.12 if target > self.level else 0.08  # fade in faster than out
        self.level += max(-step, min(step, target - self.level))
        if self.level <= 0.01 and not self.active:
            self.level = 0.0
            for w in self.windows:
                if w.isVisible():
                    w.hide()
            return
        for w in self.windows:
            w.level = self.level
            w.update()


def _mac_above_menu_bar(widget: QWidget) -> None:
    """macOS keeps normal windows below the menu bar, which hid the top edge of the glow.
    Raise the window above the menu bar, make it cover the whole screen, and show it on every Space
    (including fullscreen apps)."""
    try:
        import objc
        from AppKit import (
            NSScreenSaverWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
        )

        view = objc.objc_object(c_void_p=int(widget.winId()))
        win = view.window()
        if win is None:
            return
        win.setLevel_(NSScreenSaverWindowLevel)
        win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                   | NSWindowCollectionBehaviorStationary
                                   | NSWindowCollectionBehaviorFullScreenAuxiliary)
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(False)
        screen = win.screen()
        if screen is not None:
            win.setFrame_display_(screen.frame(), True)  # full frame, menu bar area included
    except Exception as e:  # never let cosmetics crash Alfred
        print(f"[glow] couldn't lift glow above the menu bar: {e}")
