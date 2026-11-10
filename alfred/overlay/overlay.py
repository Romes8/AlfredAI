"""Always-on-top, click-through overlay. Works over games in *borderless windowed* mode
(exclusive fullscreen hides every overlay - that's Windows, not us). Never takes focus, never injects into the game.
"""
from __future__ import annotations

import queue
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from alfred.events import Event

STATE_STYLE = {
    "idle": ("#6b7280", "Chillin'"),
    "listening": ("#22c55e", "Listening..."),
    "thinking": ("#3b82f6", "Thinking..."),
    "speaking": ("#a855f7", "Talking"),
    "waiting_confirm": ("#f59e0b", "Waiting for your yes / no"),
}


class Overlay(QWidget):
    def __init__(self, cfg: dict, events: "queue.Queue[Event]") -> None:
        super().__init__()
        self.cfg = cfg["overlay"]
        self.name = cfg["name"]
        self.events = events
        self.last_activity = time.monotonic()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(float(self.cfg["opacity"]))
        self.setFixedWidth(int(self.cfg["width"]))

        box = QWidget(self)
        box.setObjectName("box")
        box.setStyleSheet(
            "#box { background: rgba(15,17,21,220); border-radius: 12px; }"
            "QLabel { color: #e5e7eb; font-family: 'Segoe UI'; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)
        self.status = QLabel()
        self.status.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.heard = QLabel()
        self.heard.setWordWrap(True)
        self.heard.setStyleSheet("font-size: 12px; color: #9ca3af;")
        self.reply = QLabel()
        self.reply.setWordWrap(True)
        self.reply.setStyleSheet("font-size: 14px;")
        self.perm = QLabel()
        self.perm.setWordWrap(True)
        self.perm.setStyleSheet(
            "font-size: 12px; font-family: Consolas, monospace; background: rgba(245,158,11,40);"
            "border: 1px solid #f59e0b; border-radius: 8px; padding: 6px;"
        )
        self.perm.hide()
        for w in (self.status, self.heard, self.reply, self.perm):
            lay.addWidget(w)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

        self._set_state("idle")
        self._place()
        timer = QTimer(self)
        timer.timeout.connect(self._drain)
        timer.start(50)

    def _place(self) -> None:
        self.adjustSize()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        pos = self.cfg["position"]
        m = 16
        x = geo.right() - self.width() - m if "right" in pos else geo.left() + m
        y = geo.bottom() - self.height() - m if "bottom" in pos else geo.top() + m
        self.move(x, y)

    def _set_state(self, state: str) -> None:
        color, label = STATE_STYLE.get(state, STATE_STYLE["idle"])
        self.status.setText(f"<span style='color:{color}'>●</span> {self.name} · {label}")
        if state != "idle":
            self.last_activity = time.monotonic()
            self.show()

    def _drain(self) -> None:
        changed = False
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            d = ev.data
            if ev.kind == "state":
                self._set_state(d["value"])
            elif ev.kind == "heard":
                self.heard.setText(f"You: {d['text']}")
                self.reply.setText("")
                self.perm.hide()
            elif ev.kind == "reply":
                prev = self.reply.text()
                self.reply.setText((prev + " " + d["text"]).strip())
            elif ev.kind == "tool":
                self.heard.setText(self.heard.text().split("  ·")[0] + f"  · using {d['name'].split('__')[-1]}")
            elif ev.kind == "permission":
                res = d.get("result")
                if res == "pending":
                    self.perm.setText(f"{d.get('summary', '')}\n\n{d.get('detail', '')[:900]}")
                    self.perm.show()
                else:
                    self.perm.setText(f"{d.get('summary', '')} → {res}")
            elif ev.kind == "error":
                self.reply.setText(f"Error: {d['text']}")
        if changed:
            self._place()
        hide_after = float(self.cfg["hide_after_s"])
        if hide_after and self.isVisible() and time.monotonic() - self.last_activity > hide_after:
            if self.status.text().find("Chillin") != -1:
                self.hide()


def run_overlay(cfg: dict, events: "queue.Queue[Event]") -> int:
    app = QApplication.instance() or QApplication([])
    ov = Overlay(cfg, events)
    ov.show()
    return app.exec()
