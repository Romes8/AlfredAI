"""Alfred's command line.

  alfred wakeup     start Alfred in the background (voice + overlay) - terminal stays free
  alfred sleep      stop him
  alfred toggle     wake him if he's asleep, put him to sleep if he's awake (what the desktop shortcut runs)
  alfred status     is he running?
  alfred logs       last lines of his log
  alfred run        run in this terminal (foreground, Ctrl+C to stop)
  alfred text       type instead of talk (foreground)
  alfred connect google-calendar   one-time Google Calendar setup (sign-in + config)
  alfred connect google-maps       live Google Maps (places, routes, weather) via Google's official MCP server
  alfred import-places <takeout>   load your saved Google Maps places from a Google Takeout export
  alfred connectors which outside services (HubSpot, email, ...) Alfred can use on this machine
  alfred memory     show what Alfred remembers (alfred memory edit = open the file)
  alfred say "hi"   hear a sentence in Alfred's voice (try voices: --voice am_michael, --rate 1.2)

`python -m alfred` with no command = `alfred run` (same as before). Old `--text` still works.
"""
from __future__ import annotations

import argparse
import asyncio
import faulthandler
import os
import sys
import threading
import traceback

from alfred.config import load_config
from alfred.events import EventBus

COMMANDS = ("wakeup", "sleep", "toggle", "status", "logs", "run", "text", "connectors", "connect", "import-places",
            "say", "memory")


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

            def core() -> None:
                try:
                    asyncio.run(run_voice(cfg, bus))
                except BaseException:  # noqa: BLE001
                    traceback.print_exc()
                    print("[alfred] crashed - shutting down", flush=True)
                    os._exit(1)  # don't leave the overlay running with no Alfred behind it

            # Qt must own the main thread; Alfred's brain + audio run in a worker thread.
            worker = threading.Thread(target=core, daemon=True)
            worker.start()
            sys.exit(run_overlay(cfg, events))

    asyncio.run(run_voice(cfg, bus))


def main(argv: list[str] | None = None) -> None:
    faulthandler.enable()  # print a Python traceback if a native library crashes
    parser = argparse.ArgumentParser(prog="alfred", description="Alfred - your voice buddy on Claude")
    parser.add_argument("command", nargs="?", default="run", choices=COMMANDS)
    parser.add_argument("words", nargs="*", help="text for `alfred say`")
    parser.add_argument("--voice", default=None, help="voice for `alfred say`, e.g. bm_george, am_michael")
    parser.add_argument("--rate", type=float, default=None, help="speed for `alfred say`, e.g. 1.2")
    parser.add_argument("--reauth", action="store_true", help="`alfred connect`: sign in again")
    parser.add_argument("--text", action="store_true", help="(old style) same as `alfred text`")
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--config", default=None, help="defaults to $ALFRED_CONFIG or config.yaml")
    args = parser.parse_args(argv)

    if args.command == "say":
        from alfred.audio.tts import Speaker

        cfg = load_config(_find_config(args.config))
        if args.voice:
            cfg["tts"]["voice"] = args.voice
        if args.rate:
            cfg["tts"]["rate"] = args.rate
        text = " ".join(args.words) or "Yo, it's Alfred. What are we getting into today?"
        Speaker(cfg).say(text)
        return
    if args.command == "memory":
        from alfred.memory import HEADER, Memory, memory_path

        cfg = load_config(_find_config(args.config))
        path = memory_path(cfg)
        if args.words[:1] == ["edit"]:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(HEADER, encoding="utf-8")
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            else:
                import subprocess

                subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
            return
        items = Memory(path).items()
        print(f"Alfred's memory ({len(items)} items) - {path}")
        for d, t in items:
            print(f"  - {t}" + (f"   [{d}]" if d else ""))
        if not items:
            print("  (empty) - say \"Alfred, remember that ...\"")
        print("Changes take effect on his next start or after you say \"new chat\".")
        return
    if args.command == "import-places":
        from alfred.places import PLACES_FILE, import_places

        if not args.words:
            print("Usage: alfred import-places <Google Takeout .zip or unzipped folder>\n"
                  "Get it at takeout.google.com -> select 'Saved' and 'Maps (your places)' -> export.")
            sys.exit(1)
        n = import_places(" ".join(args.words))
        print(f"Imported {n} saved places -> {PLACES_FILE}" + ("" if n else "  (nothing found - is it the right export?)"))
        print("Restart isn't needed - Alfred reads the file when you ask about your places.")
        return
    if args.command == "connect":
        what = (args.words[:1] or [""])[0].lower().replace("_", "-")
        if what in ("google-maps", "maps", "gmaps"):
            from pathlib import Path

            from alfred.daemon import PROJECT_ROOT
            from alfred.setup_google import connect_maps

            cfg_path = Path(args.config or os.environ.get("ALFRED_CONFIG") or PROJECT_ROOT / "config.yaml")
            sys.exit(connect_maps(cfg_path))
        if what not in ("google-calendar", "gcal", "calendar"):
            print("Usage: alfred connect google-calendar [client_secret.json]  |  alfred connect google-maps")
            sys.exit(1)
        from pathlib import Path

        from alfred.daemon import PROJECT_ROOT
        from alfred.setup_google import connect

        cfg_path = Path(args.config or os.environ.get("ALFRED_CONFIG") or PROJECT_ROOT / "config.yaml")
        sys.exit(connect(cfg_path, args.words[1] if len(args.words) > 1 else None, reauth=args.reauth))
    if args.command == "connectors":
        from alfred.connectors import describe_all

        print(describe_all(load_config(_find_config(args.config))))
        return
    if args.command == "toggle":
        from alfred import daemon

        sys.exit(daemon.toggle(["--config", args.config] if args.config else []))
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
