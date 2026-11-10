import pytest

from alfred import __main__ as cli
from alfred import daemon


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "STATE_DIR", tmp_path)
    monkeypatch.setattr(daemon, "PID_FILE", tmp_path / "alfred.pid")
    monkeypatch.setattr(daemon, "LOG_FILE", tmp_path / "alfred.log")
    return tmp_path


def test_status_and_sleep_when_not_running(state, capsys):
    assert daemon.status() == 0 and "Asleep" in capsys.readouterr().out
    assert daemon.sleep() == 0 and "isn't running" in capsys.readouterr().out


def test_stale_pid_file_is_cleaned(state):
    (state / "alfred.pid").write_text("999999")
    assert daemon.running_pid() is None
    assert not (state / "alfred.pid").exists()


def test_wakeup_reports_a_crash_with_the_log(state, capsys, monkeypatch):
    # make the background process fail instantly, like a broken config would
    monkeypatch.setattr(daemon, "_python_for_background", lambda: "python-that-does-not-exist-xyz")
    with pytest.raises(FileNotFoundError):
        daemon.wakeup([])
    monkeypatch.setattr(daemon, "_python_for_background", lambda: __import__("sys").executable)
    monkeypatch.setattr(daemon, "PROJECT_ROOT", state)  # no alfred package here -> instant exit
    assert daemon.wakeup([]) == 1
    out = capsys.readouterr().out
    assert "failed to start" in out and not (state / "alfred.pid").exists()


def test_wakeup_and_sleep_a_real_background_process(state, capsys, monkeypatch):
    import sys
    script = state / "alfred_fake.py"
    script.write_text("import time\nprint('fake alfred up', flush=True)\nprint('[alfred] READY', flush=True)\ntime.sleep(60)\n")
    monkeypatch.setattr(daemon, "PROJECT_ROOT", state)
    real_popen = daemon.subprocess.Popen
    monkeypatch.setattr(daemon.subprocess, "Popen",
                        lambda cmd, **kw: real_popen([sys.executable, str(script), "alfred"], **kw))
    assert daemon.wakeup([]) == 0
    pid = daemon.running_pid()
    assert pid
    assert daemon.wakeup([]) == 0 and "already awake" in capsys.readouterr().out
    assert daemon.sleep() == 0
    assert daemon.running_pid() is None
    assert "fake alfred up" in daemon.tail()


def test_cli_parses_commands(monkeypatch):
    called = []
    monkeypatch.setattr(daemon, "status", lambda: called.append("status") or 0)
    with pytest.raises(SystemExit):
        cli.main(["status"])
    assert called == ["status"]
    with pytest.raises(SystemExit):
        cli.main(["dance"])


def test_brain_pipes_cli_stderr_instead_of_inheriting():
    # Regression: inheriting stderr in a windowless Windows process -> WinError 50 when starting the Claude CLI
    from alfred.agent.brain import Brain
    from alfred.agent.permissions import PermissionGate, PermissionPolicy
    from alfred.config import load_config

    cfg = load_config("does-not-exist.yaml")

    async def ask(s, d):
        return False

    b = Brain(cfg, PermissionGate(PermissionPolicy(cfg), ask), None, [])
    assert callable(b.options.stderr)


def test_toggle_wakes_then_sleeps(state, monkeypatch):
    calls = []
    monkeypatch.setattr(daemon, "_notify", lambda *a: calls.append("notify"))
    monkeypatch.setattr(daemon, "wakeup", lambda extra: calls.append("wakeup") or 0)
    monkeypatch.setattr(daemon, "running_pid", lambda: None)
    assert daemon.toggle([]) == 0 and calls == ["wakeup"]
    monkeypatch.setattr(daemon, "running_pid", lambda: 123)
    monkeypatch.setattr(daemon, "sleep", lambda: calls.append("sleep") or 0)
    assert daemon.toggle([]) == 0 and calls[-2:] == ["sleep", "notify"]


def test_icon(tmp_path):
    from alfred.icon import make_icon

    p = make_icon(tmp_path / "a.ico")
    assert p.exists() and p.stat().st_size > 1000
