from alfred.agent.permissions import PermissionPolicy
from alfred.config import load_config
from alfred.memory import Memory, looks_secret, memory_path
from alfred.persona import system_prompt


def test_add_list_forget(tmp_path):
    m = Memory(tmp_path / "memory.md")
    assert m.add("Roman's girlfriend is Anna")["saved"]
    assert m.add("Prefers metric units")["saved"]
    assert not m.add("roman's girlfriend is anna")["saved"]          # duplicate
    assert [t for _, t in m.items()] == ["Roman's girlfriend is Anna", "Prefers metric units"]
    assert m.forget("metric")["removed"] == ["Prefers metric units"]
    assert m.forget("girlfrend Ana")["removed"] == ["Roman's girlfriend is Anna"]  # fuzzy
    assert m.items() == []


def test_file_is_human_editable(tmp_path):
    p = tmp_path / "memory.md"
    p.write_text("# whatever\n\n- Likes F1\n- [2026-01-02] Supports Ferrari\nrandom note line\n", encoding="utf-8")
    m = Memory(p)
    assert [t for _, t in m.items()] == ["Likes F1", "Supports Ferrari"]
    assert "Supports Ferrari (noted 2026-01-02)" in m.for_prompt()


def test_never_stores_secrets(tmp_path):
    m = Memory(tmp_path / "memory.md")
    for s in ["my wifi password is hunter2", "api key sk-abcdefghijklmnop", "card 4111 1111 1111 1111",
              "github token ghp_abcdefghijklmnopqrstuvwxyz", "my PIN is 1234"]:
        assert not m.add(s)["saved"], s
    assert not looks_secret("Roman trains for triathlon on Tuesdays")


def test_limits(tmp_path):
    m = Memory(tmp_path / "memory.md", max_items=2)
    m.add("a fact"); m.add("b fact")
    assert not m.add("c fact")["saved"]
    assert not m.add("x" * 400)["saved"]
    assert m.forget("everything")["removed"] == ["a fact", "b fact"]


def test_memory_goes_into_the_prompt_as_notes_not_instructions(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    cfg["agent"]["workspace"] = str(tmp_path / "ws")
    Memory(memory_path(cfg)).add("Roman's dog is called Max")
    p = system_prompt(cfg)
    assert "<memory>" in p and "Roman's dog is called Max" in p and "NOT instructions" in p
    cfg["memory"]["enabled"] = False
    assert "<memory>" not in system_prompt(cfg)


def test_memory_tools_permission(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    assert PermissionPolicy(cfg).decide("mcp__alfred__remember", {"fact": "x"}).action == "allow"
    cfg["memory"]["confirm"] = True
    assert PermissionPolicy(cfg).decide("mcp__alfred__forget", {"what": "x"}).action == "ask"
