import io
import sys

from alfred.__main__ import force_utf8
from alfred.tools.commands import classify, shell_argv


def test_force_utf8_fixes_cp1252_streams(monkeypatch):
    raw = io.BytesIO()
    cp1252 = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", cp1252)
    monkeypatch.setattr(sys, "stderr", None)  # pythonw: no stderr at all -> must not crash
    force_utf8()
    print("Ľubica z Košíc ľúbi 🚲")  # failed before with: 'charmap' codec can't encode character 'ľ'
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8") == "Ľubica z Košíc ľúbi 🚲\n"


def test_powershell_outputs_utf8_and_safety_check_ignores_prefix(monkeypatch):
    monkeypatch.setattr("alfred.tools.commands.sys.platform", "win32")
    argv = shell_argv("Get-ChildItem")
    assert argv[-1].startswith("[Console]::OutputEncoding") and argv[-1].endswith("Get-ChildItem")
    assert classify("Get-ChildItem")[0] == "read"


def test_files_with_slovak_text(tmp_path):
    from alfred.memory import Memory

    m = Memory(tmp_path / "memory.md")
    assert m.add("Mama býva v Žiline, volá sa Ľudmila")["saved"]
    assert "Ľudmila" in m.for_prompt()
