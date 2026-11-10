"""Run Alfred in the background: `alfred wakeup`, `alfred sleep`, `alfred status`, `alfred logs`.

State lives in ~/.alfred/ (pid file + log). Works on Windows and macOS.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # where config.yaml and models/ live
STATE_DIR = Path.home() / ".alfred"
PID_FILE = STATE_DIR / "alfred.pid"
LOG_FILE = STATE_DIR / "alfred.log"


def running_pid() -> int | None:
    """PID of the background Alfred, or None. Cleans up a stale pid file."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    try:
        proc = psutil.Process(pid)
        cmd = " ".join(proc.cmdline()).lower()
        if proc.is_running() and "alfred" in cmd and proc.status() != psutil.STATUS_ZOMBIE:
            return pid
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    PID_FILE.unlink(missing_ok=True)
    return None


def _python_for_background() -> str:
    exe = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = exe.with_name("pythonw.exe")  # no console window
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def wakeup(extra_args: list[str]) -> int:
    pid = running_pid()
    if pid:
        print(f"Alfred's already awake (pid {pid}). `alfred sleep` to stop him.")
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8")
    log.write(f"\n===== wakeup {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    log.flush()
    cmd = [_python_for_background(), "-u", "-m", "alfred", "run", *extra_args]
    kwargs: dict = {"cwd": str(PROJECT_ROOT), "stdout": log, "stderr": subprocess.STDOUT,
                    "stdin": subprocess.DEVNULL, "env": {**os.environ, "PYTHONUNBUFFERED": "1"}}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True  # keeps running after the terminal closes
    proc = subprocess.Popen(cmd, **kwargs)
    PID_FILE.write_text(str(proc.pid))
    time.sleep(2.0)  # catch instant crashes (bad config, missing login...)
    if proc.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        print(f"Alfred failed to start (exit {proc.returncode}). Last log lines:\n")
        print(tail(20))
        return 1
    key = "right Option" if sys.platform == "darwin" else "right Alt"
    print(f"Alfred's up (pid {proc.pid}). Hold {key} and talk. `alfred sleep` to stop, `alfred logs` to peek.")
    return 0


def sleep() -> int:
    pid = running_pid()
    if not pid:
        print("Alfred isn't running.")
        return 0
    proc = psutil.Process(pid)
    for p in proc.children(recursive=True) + [proc]:  # the Claude CLI runs as a child process
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs([proc], timeout=5)
    for p in alive:
        p.kill()
    PID_FILE.unlink(missing_ok=True)
    print("Alfred's asleep. Night, mate.")
    return 0


def status() -> int:
    pid = running_pid()
    if pid:
        p = psutil.Process(pid)
        up = int(time.time() - p.create_time())
        print(f"Awake - pid {pid}, up {up // 3600}h {up % 3600 // 60}m. Log: {LOG_FILE}")
    else:
        print("Asleep. `alfred wakeup` to start him.")
    return 0


def tail(n: int = 40) -> str:
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return "(no log yet)"
    return "\n".join(lines[-n:])
