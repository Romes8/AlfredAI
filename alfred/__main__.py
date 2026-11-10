"""Alfred's command line.

  alfred wakeup     start Alfred in the background (voice + overlay) - terminal stays free
  alfred sleep      stop him
  alfred status     is he running?
  alfred logs       last lines of his log
  alfred run        run in this terminal (foreground, Ctrl+C to stop)
  alfred text       type instead of talk (foreground)
  alfred connectors which outside services (HubSpot, email, ...) Alfred can use on this machine

`python -m alfred` with no command = `alfred run` (same as before). Old `--text` still works.
"""
from __future__ import annotations

import argparse
import asyncio
import faulthandler
import os
import sys
import threading

from alfred.config import load_config
from alfred.events import EventBus

COMMANDS = ("wakeup", "sleep", "status", "logs", "run", "text", "connectors")


def _find_config(explicit: str | None) -> str | None:
    """--config > $ALFRED_CONFIG > ./config.yaml > <project>/config.yaml (so `alfred` works from any folder)."""
    if explicit or os.environ.get("ALFRED_CONFIG"):
        return explicit
    if os.path.exists("config.yaml"):
        return None
    from alfred.daemon import PROJECT_ROOT

    candidate = PROJECT_ROOT / "config.yaml"
    if candidate.exists():
        os.chdir(PROJECT_ROOT)  # relative paths in the config (models/...) resolve from the project
        return str(candidate)
    return None


def _run(args) -> None:
    cfg = load_config(_find_config(args.config))
    bus = EventBus()

    if args.command == "text" or args.text:
        from alfred.app import run_text

        asyncio.run(run_text(cfg, bus))
        return

    from alfred.app import run_voice

    if cfg["overlay"]["enabled"] and not args.no_overlay:
        try:
            from alfred.overlay.overlay import run_overlay
        except ImportError:
            print("[alfred] PyQt6 not installed - running without overlay (pip install PyQt6)")
        else:
            events = bus.subscribe()
            # Qt must own the main thread; Alfred's brain + audio run in a worker thread.
            worker = threading.Thread(target=lambda: asyncio.run(run_voice(cfg, bus)), daemon=True)
            worker.start()
            sys.exit(run_overlay(cfg, events))

    asyncio.run(run_voice(cfg, bus))


def main(argv: list[str] | None = None) -> None:
    faulthandler.enable()  # print a Python traceback if a native library crashes
    parser = argparse.ArgumentParser(prog="alfred", description="Alfred - your voice buddy on Claude")
    parser.add_argument("command", nargs="?", default="run", choices=COMMANDS)
    parser.add_argument("--text", action="store_true", help="(old style) same as `alfred text`")
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--config", default=None, help="defaults to $ALFRED_CONFIG or config.yaml")
    args = parser.parse_args(argv)

    if args.command == "connectors":
        from alfred.connectors import describe_all

        print(describe_all(load_config(_find_config(args.config))))
        return
    if args.command in ("wakeup", "sleep", "status", "logs"):
        from alfred import daemon

        if args.command == "wakeup":
            extra = (["--no-overlay"] if args.no_overlay else []) + (["--config", args.config] if args.config else [])
            sys.exit(daemon.wakeup(extra))
        if args.command == "sleep":
            sys.exit(daemon.sleep())
        if args.command == "status":
            sys.exit(daemon.status())
        print(daemon.tail())
        return
    _run(args)


if __name__ == "__main__":
    main()
