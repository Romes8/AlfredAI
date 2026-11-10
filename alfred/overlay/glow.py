"""Purple glow around the edges of every screen while Alfred is actively listening.

One frameless, transparent, click-through, always-on-top window per monitor. It never takes focus.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

PURPLE = (168, 85, 247)  # tailwind purple-500


class _EdgeWindow(QWidget):
    def __init__(self, screen, thickness: int, color: tuple[int, int, int]) -> None:
        super().__init__()
        self.thickness = thickness
        self.color = color
        self.level = 0.0  # 0..1, animated by EdgeGlow
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def _grad(self, x1, y1, x2, y2) -> QLinearGradient:
        r, g, b = self.color
        grad = QLinearGradient(QPointF(x1, y1), QPointF(x2, y2))
        grad.setColorAt(0.0, QColor(r, g, b, int(210 * self.level)))
        grad.setColorAt(0.35, QColor(r, g, b, int(110 * self.level)))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
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
            rg.setColorAt(0.0, QColor(r, g, b, int(120 * self.level)))
            rg.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(rg)
            p.drawEllipse(QPointF(cx, cy), t * 2.2, t * 2.2)
        p.end()


class EdgeGlow:
    """Call set_active(True/False). Fades in, pulses gently while active, fades out."""

    def __init__(self, thickness: int = 36, color: tuple[int, int, int] = PURPLE) -> None:
        self.windows = [_EdgeWindow(s, thickness, color) for s in QGuiApplication.screens()]
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
