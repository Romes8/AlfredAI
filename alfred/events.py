"""Tiny thread-safe event bus. The core (asyncio thread) publishes, the overlay (Qt thread) polls."""
from __future__ import annotations

import queue
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    kind: str  # state | heard | reply | permission | error
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[Event]] = []

    def subscribe(self) -> "queue.Queue[Event]":
        q: queue.Queue[Event] = queue.Queue()
        self._subscribers.append(q)
        return q

    def emit(self, kind: str, **data: Any) -> None:
        ev = Event(kind, data)
        for q in self._subscribers:
            q.put(ev)

    # convenience
    def state(self, value: str) -> None:  # idle | listening | thinking | speaking | waiting_confirm
        self.emit("state", value=value)
