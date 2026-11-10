"""Live iRacing telemetry via pyirsdk (iRacing's shared-memory SDK). Exact numbers, no screen reading.

A background poller records every completed lap so Alfred can answer "what was my third lap?" or
"how's my pace this stint?".
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


def fmt_lap(seconds: float | None) -> str | None:
    """83.456 -> '1:23.456'. None / <= 0 -> None (no valid time)."""
    if seconds is None or seconds <= 0:
        return None
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}" if m else f"{s:.3f}"


@dataclass
class LapRecord:
    lap: int
    time_s: float
    fuel_used_l: float | None = None


@dataclass
class IRacingState:
    laps: list[LapRecord] = field(default_factory=list)
    last_completed: int = -1
    fuel_at_lap_start: float | None = None


class IRacing:
    def __init__(self) -> None:
        self._ir = None
        self.state = IRacingState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        try:
            import irsdk  # pyirsdk

            self._ir = irsdk.IRSDK()
        except Exception as e:
            print(f"[iracing] pyirsdk not available: {e}")

    # ---- connection ----
    def connected(self) -> bool:
        if self._ir is None:
            return False
        if not (self._ir.is_initialized and self._ir.is_connected):
            self._ir.shutdown()
            self._ir.startup()
        return bool(self._ir.is_initialized and self._ir.is_connected)

    def _get(self, key: str) -> Any:
        try:
            return self._ir[key]
        except Exception:
            return None

    # ---- lap recorder ----
    def start_poller(self) -> None:
        if self._ir is None or self._thread:
            return
        self._thread = threading.Thread(target=self._poll, daemon=True, name="iracing-poller")
        self._thread.start()

    def _poll(self) -> None:
        pending: tuple[int, float] | None = None  # (lap number, when it completed)
        while True:
            try:
                if not self.connected():
                    self.state = IRacingState()
                    time.sleep(2)
                    continue
                self._ir.freeze_var_buffer_latest()
                completed = self._get("LapCompleted")
                fuel = self._get("FuelLevel")
                if completed is not None and completed != self.state.last_completed:
                    if self.state.last_completed >= 0 and completed > self.state.last_completed:
                        pending = (completed, time.monotonic())
                    else:
                        self.state.fuel_at_lap_start = fuel
                    self.state.last_completed = completed
                # LapLastLapTime updates a moment after the line - record ~1.5 s later
                if pending and time.monotonic() - pending[1] > 1.5:
                    t = self._get("LapLastLapTime")
                    used = None
                    if fuel is not None and self.state.fuel_at_lap_start is not None:
                        used = round(self.state.fuel_at_lap_start - fuel, 2)
                    with self._lock:
                        if t and t > 0:
                            self.state.laps.append(LapRecord(pending[0], float(t), used))
                    self.state.fuel_at_lap_start = fuel
                    pending = None
                self._ir.unfreeze_var_buffer_latest()
            except Exception as e:
                print(f"[iracing] poll error: {e}")
            time.sleep(0.25)

    # ---- queries ----
    def snapshot(self) -> dict[str, Any]:
        if not self.connected():
            return {"connected": False, "message": "iRacing isn't running or no session is loaded."}
        g = self._get
        info: dict[str, Any] = {"connected": True}
        try:
            weekend = g("WeekendInfo") or {}
            sessions = (g("SessionInfo") or {}).get("Sessions", [])
            num = g("SessionNum")
            info["track"] = weekend.get("TrackDisplayName")
            if sessions and num is not None and num < len(sessions):
                info["session_type"] = sessions[num].get("SessionType")
        except Exception:
            pass
        fuel = g("FuelLevel")
        with self._lock:
            laps = list(self.state.laps)
        used = [l.fuel_used_l for l in laps[-5:] if l.fuel_used_l and l.fuel_used_l > 0]
        per_lap = round(sum(used) / len(used), 2) if used else None
        info.update({
            "best_lap": fmt_lap(g("LapBestLapTime")),
            "last_lap": fmt_lap(g("LapLastLapTime")),
            "current_lap": g("Lap"),
            "laps_completed": g("LapCompleted"),
            "position": g("PlayerCarPosition"),
            "class_position": g("PlayerCarClassPosition"),
            "delta_to_best_s": round(g("LapDeltaToBestLap"), 3) if g("LapDeltaToBestLap_OK") else None,
            "incidents": g("PlayerCarMyIncidentCount"),
            "fuel_l": round(fuel, 2) if fuel is not None else None,
            "fuel_pct": round(g("FuelLevelPct") * 100, 1) if g("FuelLevelPct") is not None else None,
            "fuel_per_lap_l": per_lap,
            "laps_of_fuel_left": round(fuel / per_lap, 1) if fuel and per_lap else None,
            "session_time_remaining_s": round(g("SessionTimeRemain")) if g("SessionTimeRemain") else None,
        })
        return {k: v for k, v in info.items() if v is not None}

    def laps(self) -> dict[str, Any]:
        with self._lock:
            laps = list(self.state.laps)
        if not laps:
            return {"laps": [], "message": "No completed laps recorded yet this session."}
        best = min(laps, key=lambda l: l.time_s)
        avg5 = sum(l.time_s for l in laps[-5:]) / min(5, len(laps))
        return {
            "laps": [{"lap": l.lap, "time": fmt_lap(l.time_s), "fuel_used_l": l.fuel_used_l} for l in laps[-30:]],
            "best": {"lap": best.lap, "time": fmt_lap(best.time_s)},
            "avg_last_5": fmt_lap(avg5),
            "count": len(laps),
        }

    def is_racing(self) -> bool:
        return self.connected() and bool(self._get("IsOnTrack"))
