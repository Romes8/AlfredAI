"""Terminal commands with a safety gate.

Every command is classified BEFORE it runs:
  read      just looks (git status, dir, ipconfig, Get-Process ...)          -> runs automatically
  sensitive reads a file's contents (cat, type, Get-Content ...)             -> asks
  change    adds / creates / installs / modifies / moves / stops something  -> asks (or blocked: commands.on_change)
  delete    removes / uninstalls / wipes something                          -> asks (or blocked: commands.on_delete)
  blocked   destructive or uninspectable (format, registry, force push,
            download-and-run, encoded commands, elevation ...)              -> never runs
Anything not recognised counts as a change. When a command has several parts (; && || |), the worst part wins.
"""
from __future__ import annotations

import re
import subprocess
import sys

LEVELS = ["read", "sensitive", "change", "delete", "blocked"]

BLOCKED = [
    (r"\bformat(-volume)?\s+[a-z]:", "formats a drive"), (r"\bformat-volume\b", "formats a drive"),
    (r"\bdiskpart\b", "disk partitioning"), (r"\b(clear|initialize)-disk\b", "wipes a disk"),
    (r"\bbcdedit\b", "boot configuration"), (r"\bcipher\s+/w", "wipes free space"),
    (r"\bvssadmin\s+delete\b", "deletes backups"), (r"\bwmic\s+shadowcopy\b", "deletes backups"),
    (r"\bshutdown\b", "shuts the computer down"), (r"\b(restart|stop)-computer\b", "restarts / shuts down"),
    (r"\breg(\.exe)?\s+(delete|add|import)\b", "edits the registry"),
    (r"\b(set|new|remove)-itemproperty\b.*\b(hklm|hkcu|registry::)", "edits the registry"),
    (r"\bset-executionpolicy\b", "changes script security"), (r"\bset-mppreference\b|\badd-mppreference\b",
                                                              "changes antivirus settings"),
    (r"\bnetsh\s+(advfirewall|firewall)\b", "changes the firewall"), (r"\bnet\s+(user|localgroup)\b", "changes accounts"),
    (r"\b(iex|invoke-expression)\b", "runs code it can't inspect"),
    (r"\s-e(nc|ncodedcommand)?\s+[a-z0-9+/=]{16,}", "runs an encoded command"), (r"frombase64string", "runs encoded code"),
    (r"\b(curl|wget|iwr|invoke-webrequest|irm|invoke-restmethod)\b.*\|\s*(sh|bash|zsh|iex|powershell|pwsh|python)\b",
     "downloads and runs a script"),
    (r"\bsudo\b|\brunas\b|-verb\s+runas", "asks for admin rights"),
    (r"\bmkfs\b|\bdd\s+if=", "writes raw disk data"), (r":\(\)\s*\{", "fork bomb"),
    (r"\bchmod\s+-r\b|\bchown\s+-r\b", "changes permissions recursively"),
    (r"\bgit\s+push\b.*(\s--force\b|\s-f\b|--force-with-lease)", "force-pushes git history"),
    (r"\bgit\s+reset\s+--hard\b", "throws away git changes"), (r"\bgit\s+clean\s+-[a-z]*f", "deletes untracked files"),
    (r"\bschtasks\s+/(create|delete|change)\b|\bregister-scheduledtask\b", "creates scheduled tasks"),
    (r"\b(new|remove|set)-service\b|\bsc(\.exe)?\s+(create|delete|config)\b", "changes system services"),

]

# targets that make a recursive delete catastrophic: root, home, a whole drive, "everything here"
BIG_TARGET = re.compile(r"^(/|/\*|~|~[/\\]|~[/\\]\*|\$home|\$env:userprofile|\$env:systemroot|[a-z]:[/\\]?|"
                        r"[a-z]:[/\\]\*|\*|\*\.\*|\.|\.[/\\]\*?|\.\.)$", re.I)
RECURSIVE = re.compile(r"(^|\s)(-r\w*|-\w*r\w*f?|-recurse\w*|/s)(\s|$)", re.I)


def _big_recursive_delete(seg: str) -> bool:
    if _first_word(seg) not in DELETE_WORDS or not RECURSIVE.search(" " + seg):
        return False
    tokens = [t.strip("'\"") for t in seg.split()[1:]]
    return any(BIG_TARGET.match(t) for t in tokens if not t.startswith("-") and not re.fullmatch(r"/[a-z]", t, re.I))

DELETE_WORDS = {"rm", "del", "erase", "rd", "rmdir", "remove-item", "ri", "unlink", "shred", "clear-content",
                "clear-recyclebin", "uninstall-package", "uninstall-module"}
DELETE_SUB = [r"^git\s+(rm|branch\s+-[dD]|stash\s+(drop|clear)|tag\s+-d|remote\s+(rm|remove))\b",
              r"^(npm|pnpm|yarn)\s+(uninstall|remove|rm|un)\b", r"^pip3?\s+uninstall\b",
              r"^(winget|choco|scoop|brew)\s+(uninstall|remove)\b", r"^docker\s+(rm|rmi|system\s+prune|volume\s+rm)\b",
              r"^kubectl\s+delete\b", r"^remove-", r"^python3?\s+-m\s+pip\s+uninstall\b"]

FILE_READERS = {"cat", "type", "gc", "get-content", "more", "less", "head", "tail", "bat", "nl", "strings",
                "select-string", "sls", "findstr", "grep", "rg", "certutil"}
READ_WORDS = {
    "ls", "dir", "gci", "get-childitem", "pwd", "get-location", "cd", "set-location", "sl", "echo", "write-output",
    "write-host", "whoami", "hostname", "ipconfig", "ifconfig", "ping", "test-connection", "tracert", "traceroute",
    "nslookup", "resolve-dnsname", "systeminfo", "tasklist", "ps", "uptime", "df", "du", "free", "nvidia-smi",
    "where", "where.exe", "which", "get-command", "gcm", "netstat", "arp", "date", "wc", "measure-object", "measure",
    "select-object", "select", "where-object", "?", "sort-object", "sort", "format-table", "ft", "format-list", "fl",
    "out-string", "group-object", "sort", "uniq", "tree", "ver", "env", "printenv", "top", "free", "lsof", "id",
    "uname", "sw_vers", "fastfetch", "neofetch", "help", "get-help", "man", "find", "fd", "file", "stat", "foreach-object",
    "%", "test-path", "resolve-path", "split-path", "join-path", "convertto-json", "convertfrom-json", "format-wide",
}
READ_SUB = [r"^git\s+(status|log|diff|show|branch(\s+(-a|-r|-v|-vv|--list))*\s*$|remote\s+-v|rev-parse|describe|"
            r"blame|shortlog|ls-files|config\s+--(get|list)|tag\s*$|stash\s+list)\b",
            r"^(python3?|py|node|npm|pip3?|git|java|go|cargo|rustc|dotnet|docker|kubectl|claude)\s+(--?version|-v|-V)\s*$",
            r"^(pip3?|python3?\s+-m\s+pip)\s+(list|show|freeze)\b", r"^(npm|pnpm|yarn)\s+(ls|list|outdated|view|info)\b",
            r"^(winget|choco|scoop|brew)\s+(list|search|show|info)\b", r"^docker\s+(ps|images|version|info)\b",
            r"^kubectl\s+(get|describe|logs|version|config\s+(view|get-contexts|current-context))\b",
            r"^wsl\s+(-l|--list|--status)\b", r"^route\s+print\b", r"^gh\s+(pr|issue|repo|run)\s+(list|view|status)\b"]
WRITE_TO_FILE = [r"(?<![0-9])>{1,2}(?!\s*\$null)(?!\s*/dev/null)(?!&)", r"\b(out-file|set-content|add-content|tee|tee-object)\b"]


def _strip_harmless(cmd: str) -> str:
    cmd = re.sub(r"\d?>\s*(\$null|/dev/null|nul)\b", " ", cmd, flags=re.I)
    return re.sub(r"\d>&\d", " ", cmd)


def _segments(cmd: str) -> list[tuple[str, bool]]:
    """Split on ; && || | newlines -> [(segment, came_after_a_pipe)]."""
    parts = re.split(r"(\|\||&&|;|\n|\|)", cmd)
    out, after_pipe = [], False
    for p in parts:
        if p in ("||", "&&", ";", "\n"):
            after_pipe = False
            continue
        if p == "|":
            after_pipe = True
            continue
        if p.strip():
            out.append((p.strip(), after_pipe))
    return out


def _first_word(seg: str) -> str:
    seg = re.sub(r"^[&.]\s+", "", seg.strip())
    word = seg.split()[0].strip("'\"") if seg.split() else ""
    word = re.split(r"[\\/]", word)[-1].lower()
    return re.sub(r"\.(exe|cmd|bat|ps1)$", "", word)


def classify_segment(seg: str, after_pipe: bool) -> tuple[str, str]:
    low = seg.lower().strip()
    w = _first_word(seg)
    if w in DELETE_WORDS or any(re.search(p, low) for p in DELETE_SUB):
        return "delete", "deletes or removes something"
    if any(re.search(p, low) for p in WRITE_TO_FILE):
        return "change", "writes to a file"
    if w in FILE_READERS:
        return ("read", "") if after_pipe else ("sensitive", "reads a file's contents")
    if any(re.search(p, low) for p in READ_SUB):
        return "read", ""
    if w in READ_WORDS or (w.startswith("get-") and w not in ("get-content", "get-credential")):
        return "read", ""
    return "change", "changes, adds or installs something"


def classify(cmd: str, secret_patterns: list[str] | None = None) -> tuple[str, str]:
    """(level, reason) for the whole command - the worst part wins."""
    if not cmd or not cmd.strip():
        return "blocked", "empty command"
    low = cmd.lower()
    for pat, why in BLOCKED:
        if re.search(pat, low, flags=re.I | re.M):
            return "blocked", why
    for s in secret_patterns or []:
        if s and s.lower() in low:
            return "blocked", "touches secrets / credentials"
    if re.search(r"`|\$\(", cmd):
        return "change", "contains a sub-command"  # can't fully inspect -> at least ask
    worst, reason = "read", ""
    for seg, _ in _segments(_strip_harmless(cmd)):
        if _big_recursive_delete(seg):
            return "blocked", "deletes a whole drive, home folder or everything in a folder"
    for seg, after_pipe in _segments(_strip_harmless(cmd)):
        lvl, why = classify_segment(seg, after_pipe)
        if LEVELS.index(lvl) > LEVELS.index(worst):
            worst, reason = lvl, why
    return worst, reason


UTF8_PREFIX = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
               "$OutputEncoding = [System.Text.Encoding]::UTF8; ")


def shell_argv(cmd: str) -> list[str]:
    if sys.platform == "win32":
        # make PowerShell emit UTF-8 so names like 'Košice' / 'Ľubica' come back intact (the safety check runs on
        # the user's command only, before this prefix is added)
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", UTF8_PREFIX + cmd]
    return ["/bin/zsh" if sys.platform == "darwin" else "/bin/bash", "-lc", cmd]


def run(cmd: str, cwd: str, timeout_s: int = 60, max_chars: int = 6000) -> dict:
    try:
        p = subprocess.run(shell_argv(cmd), cwd=cwd, capture_output=True, text=True, timeout=timeout_s,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "error": f"timed out after {timeout_s}s"}
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n... ({len(out) - max_chars} more characters cut)"
    return {"exit_code": p.returncode, "output": out}
