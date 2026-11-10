"""Cheap guard rails on app.py's nested helpers (the voice loop itself needs real audio hardware)."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "alfred" / "app.py"


def _nested_funcs():
    tree = ast.parse(SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_voice":
            return {f.name: f for f in ast.walk(node) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and f is not node}
    raise AssertionError("run_voice not found")


def test_no_nested_helper_calls_itself():
    for name, fn in _nested_funcs().items():
        calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert name not in calls, f"{name}() calls itself - infinite recursion"


def test_transcribe_helper_uses_the_real_transcriber():
    fn = _nested_funcs()["transcribe"]
    attrs = {f"{a.value.id}.{a.attr}" for a in ast.walk(fn) if isinstance(a, ast.Attribute)
             and isinstance(a.value, ast.Name)}
    assert "stt.transcribe" in attrs
