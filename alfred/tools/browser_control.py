"""Browser control: Alfred clicks, types and fills forms in Chrome through Microsoft's Playwright MCP server.

Alfred drives his OWN Chrome window with a separate profile (~/.alfred/browser-profile), so he never touches your
everyday Chrome. Log in to sites in that window once and he stays logged in there.

Safety rules (on top of everything else):
  automatic   open pages, click ordinary things (links, play, next, tabs), scroll, read the page, screenshots
  asks you    typing anything, filling forms, choosing options, pressing Enter, uploading,
              clicking buttons that buy / pay / send / delete / confirm / subscribe / post ..., accepting dialogs,
              opening a page whose address carries a lot of data
  blocked     running JavaScript on the page
"""
from __future__ import annotations

import re
from typing import Any

from alfred.config import expand

PREFIX = "mcp__browser__"
SERVER_NAME = "browser"

# tool names as served by @playwright/mcp (checked against v0.0.85)
AUTO = {"browser_navigate_back", "browser_snapshot", "browser_take_screenshot", "browser_tabs", "browser_wait_for",
        "browser_hover", "browser_resize", "browser_close", "browser_console_messages", "browser_network_requests",
        "browser_network_request", "browser_find", "browser_emulate_media", "browser_install", "browser_drag",
        "browser_navigate_forward"}
TYPING = {"browser_type", "browser_fill_form", "browser_select_option"}
BLOCKED = {"browser_evaluate", "browser_run_code", "browser_run_code_unsafe"}
RISKY_CLICK = re.compile(
    r"\b(buy|pay|payment|purchase|order|checkout|check out|place order|submit|send|delete|remove|erase|confirm|"
    r"subscribe|unsubscribe|sign up|register|book|reserve|transfer|donate|post|publish|tweet|reply|share|accept|"
    r"agree|approve|allow|log ?out|sign ?out|cancel (my )?(subscription|order|account)|close account|install|"
    r"download|upload|save changes|apply|continue|proceed|complete|finish|finali[sz]e|pay now|add to (cart|basket|bag)|"
    r"go to checkout|review order|authori[sz]e|verify|activate|redeem|claim|enroll|join|yes)\b", re.I)

# Once the page itself is a checkout / payment / account-danger page, EVERY click and key press asks.
SENSITIVE_PAGE = re.compile(r"(checkout|/cart\b|basket|payment|/pay\b|billing|purchase|/order|subscri|"
                            r"delete[-_]?account|close[-_]?account|transfer|wallet|paypal\.com|stripe\.com|"
                            r"klarna|mobilepay|/bank|netbank|login\.|signin|/account/security)", re.I)
PAGE_URL = re.compile(r"Page URL:\s*(\S+)")


class PageTracker:
    """Remembers which page Alfred's browser is on (read from the tool results)."""

    def __init__(self) -> None:
        self.url = ""

    def update_from(self, tool_response) -> None:
        import json

        text = tool_response if isinstance(tool_response, str) else json.dumps(tool_response, default=str)
        found = PAGE_URL.findall(text)
        if found:
            self.url = found[-1].strip("\\\"',")

    def sensitive(self) -> bool:
        return bool(self.url and SENSITIVE_PAGE.search(self.url))


page = PageTracker()


def server_config(cfg: dict) -> dict:
    b = cfg.get("browser_control", {})
    args = ["-y", "@playwright/mcp@latest", "--browser", b.get("browser", "chrome")]
    if b.get("use_my_chrome"):
        args.append("--extension")  # attaches to your real Chrome via the "Playwright MCP Bridge" extension
    else:
        args += ["--user-data-dir", str(expand(b.get("profile_dir") or "~/.alfred/browser-profile"))]
    return {"type": "stdio", "command": "npx", "args": args}


def decide(short: str, args: dict[str, Any], cfg: dict) -> tuple[str, str]:
    b = cfg.get("browser_control", {})
    if short in BLOCKED:
        return "deny", "Running code inside web pages is blocked."
    if args.get("filename"):
        return "ask", ""  # the tool would save a file on this computer
    if short == "browser_drop" and args.get("paths"):
        return ("ask" if b.get("allow_uploads") else "deny"), "Uploading files from this computer is off."
    if short == "browser_file_upload":
        return ("ask" if b.get("allow_uploads") else "deny"), "Uploading files from this computer is off."
    if short in TYPING:
        mode = b.get("on_type", "ask")
        return ("deny", "Typing into web pages is turned off on this machine.") if mode == "deny" else (mode, "")
    on_sensitive_page = page.sensitive()
    if short == "browser_press_key":
        key = str(args.get("key", ""))
        return ("ask", "") if key.lower() in ("enter", "return", " ", "space") or on_sensitive_page else ("allow", "")
    if short == "browser_handle_dialog":
        return ("ask", "") if args.get("accept") else ("allow", "")
    if short in ("browser_click", "browser_mouse_click_xy"):
        label = str(args.get("element", ""))
        if not label or RISKY_CLICK.search(label) or on_sensitive_page:
            mode = b.get("on_risky_click", "ask")
            return ("deny", "Clicking buttons that buy/send/delete is off.") if mode == "deny" else ("ask", "")
        return "allow", ""
    if short == "browser_navigate":
        url = str(args.get("url", ""))
        if not re.match(r"^https?://", url, re.I):
            return "deny", "Only http/https pages."
        query = url.split("?", 1)[1] if "?" in url else ""
        return ("ask", "") if len(query) > 150 else ("allow", "")  # long query strings can smuggle data out
    if short in AUTO:
        return "allow", ""
    return "ask", ""  # new / unknown browser tools: ask


def summarize(short: str, args: dict[str, Any]) -> tuple[str, str]:
    el = str(args.get("element", "") or "the page")
    if short == "browser_type":
        text = str(args.get("text", ""))
        shown = text if len(text) <= 60 else text[:60] + "..."
        extra = " and hit enter" if args.get("submit") else ""
        return f"I want to type \"{shown}\" into {el}{extra}.", f"TYPE into {el}\n\n{text}"
    if short == "browser_fill_form":
        fields = args.get("fields") or []
        names = ", ".join(str(f.get("name", "?")) for f in fields[:5])
        detail = "\n".join(f"{f.get('name')}: {f.get('value')}" for f in fields)
        return f"I want to fill in the form: {names}.", f"FILL FORM\n\n{detail}"
    if short == "browser_select_option":
        return f"I want to pick {args.get('values')} in {el}.", f"SELECT {args.get('values')} in {el}"
    if short in ("browser_click", "browser_mouse_click_xy"):
        where = " - we're on a payment or account page" if page.sensitive() else ""
        return f"I want to click \"{el}\"{where}.", f"CLICK {el}\n\npage: {page.url}"
    if short == "browser_press_key":
        return "I want to press Enter on the page.", f"KEY {args.get('key')}"
    if short == "browser_handle_dialog":
        return "The page is asking to confirm something - want me to accept?", f"DIALOG accept\n\n{args}"
    if short == "browser_navigate":
        return "I want to open a page with a long address.", f"NAVIGATE\n\n{args.get('url')}"
    if short in ("browser_file_upload", "browser_drop"):
        return "I want to upload a file to the page.", f"UPLOAD\n\n{args.get('paths')}"
    if args.get("filename"):
        return f"I want to save {args.get('filename')} from the browser.", f"SAVE FILE\n\n{args.get('filename')}"
    return f"I want to use the browser: {short.replace('browser_', '').replace('_', ' ')}.", f"{short}\n\n{args}"
