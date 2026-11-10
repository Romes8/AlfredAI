"""python -m alfred            -> voice mode (+ overlay if enabled)
python -m alfred --text     -> keyboard chat, no mic needed
"""
from __future__ import annotations

import argparse
import asyncio
import faulthandler
import sys
import threading

from alfred.config import load_config
from alfred.events import EventBus


def main() -> None:
    faulthandler.enable()  # print a Python traceback if a native library crashes
    parser = argparse.ArgumentParser(prog="alfred")
    parser.add_argument("--text", action="store_true", help="type instead of talk")
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    bus = EventBus()

    if args.text:
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


if __name__ == "__main__":
    main()
