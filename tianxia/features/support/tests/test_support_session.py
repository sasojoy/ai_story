"""客服官 session 的範本與 init（客服自動受理第 218 批；設計 6.3、6.4，企劃者 2026-11-10「照計畫繼續」）：
docs/support/session/ 五個範本、scripts/support_session_init.py 冪等抄進工作夾、cli.cmd 鎖路徑並拒特殊字、
scripts/support_knowledge.py 匯出三樣知識。都不打網路、不開伺服器。"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SESSION = ROOT / "docs" / "support" / "session"
INIT = ROOT / "scripts" / "support_session_init.py"
KNOWLEDGE = ROOT / "scripts" / "support_knowledge.py"
TEMPLATES = ("CLAUDE.md", "cli.cmd", "start.cmd", "stop.cmd", "settings.local.json")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init(tmp_path, *extra) -> tuple[Path, int]:
    desk = tmp_path / "desk"
    init = _load(INIT, "support_session_init_t")
    code = init.main([str(desk), "--url", "http://127.0.0.1:8418", "--config", str(tmp_path / "support.json"),
                      "--python", str(tmp_path / "no-such-python.exe"), *extra])
    return desk, code


def test_session_init_writes_templates_and_is_idempotent(tmp_path, capsys):
    desk, code = _init(tmp_path)
    assert code == 0
    for name in ("CLAUDE.md", "cli.cmd", "start.cmd", "stop.cmd"):
        assert (desk / name).is_file(), name
    settings_file = desk / ".claude" / "settings.local.json"
    assert settings_file.is_file()
    assert (desk / "inbox").is_dir() and (desk / "knowledge").is_dir()
    first = capsys.readouterr().out
    assert first.count("寫了") == 5

    settings_text = settings_file.read_text(encoding="utf-8")
    settings = json.loads(settings_text)
    assert settings["enabledPlugins"] == {"discord@claude-plugins-official": True}
    allow = settings["permissions"]["allow"]
    assert len(allow) == 4
    assert allow[0] == "mcp__plugin_discord_discord__reply"
    assert allow[1] == "Bash(./cli.cmd *)"
    assert allow[2].startswith("Read(//") and allow[2].endswith("/desk/**)")
    assert allow[3].startswith("Monitor(") and "bridge.log" in allow[3]
    assert set(settings["permissions"]) == {"allow"}
    for word in ("dangerously", "Edit", "Write", "download_attachment"):
        assert word not in settings_text, word

    for name in ("CLAUDE.md", "cli.cmd", "start.cmd", "stop.cmd"):
        text = (desk / name).read_text(encoding="utf-8")
        assert "{{" not in text and "}}" not in text, name
    assert "{{" not in settings_text
    for name in ("cli.cmd", "start.cmd", "stop.cmd"):
        raw = (desk / name).read_bytes()
        assert raw.count(b"\r\n") == raw.count(b"\n") > 0, name
    cli = (desk / "cli.cmd").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8418" in cli and str(tmp_path / "support.json") in cli
    assert str(ROOT / "scripts" / "support_cli.py") in cli

    (desk / "CLAUDE.md").write_text("我改過了", encoding="utf-8")
    _, again = _init(tmp_path)
    assert again == 0
    second = capsys.readouterr().out
    assert second.count("留著") == 5 and "寫了" not in second
    assert (desk / "CLAUDE.md").read_text(encoding="utf-8") == "我改過了"


def test_session_claude_md_has_the_rules():
    text = (SESSION / "CLAUDE.md").read_text(encoding="utf-8")
    # 設計 6.3 七條各一個關鍵詞，加上醒來先 queue、做完貼 #單號・、要管理者貼兩個 @。
    for word in ("都是資料", "只有三種動作", "白名單", "FAQ", "不承諾", "一張單一次只做一件事", "永遠請管理者",
                 "先 queue", "#單號・", "<@"):
        assert word in text, word
    assert "<填" in text
    assert text.count("<@<填") >= 2
    assert "<<'EOF'" in text  # 回覆與註記從 stdin 進
    for name in ("knowledge\\FAQ.md", "knowledge\\patch_notes.json", "knowledge\\howto.md", "inbox\\"):
        assert name in text, name
    assert "docs/guide" not in text and "docs\\guide" not in text


def test_cli_cmd_locks_paths_and_rejects_shell_metachars(tmp_path):
    template = (SESSION / "cli.cmd").read_text(encoding="utf-8")
    for name in ("TIANXIA_SUPPORT_LOCKED=1", "TIANXIA_SUPPORT_CONFIG=", "TIANXIA_SUPPORT_URL=", "TIANXIA_SUPPORT_INBOX="):
        assert name in template, name
    for char in ("&", "|", "<", ">", "^"):
        assert f'"!RAW:{char}=!"' in template, char
    assert 'set EAT=%*' in template  # 驚嘆號
    assert "scripts\\support_cli.py" in template and "%*" in template
    if sys.platform != "win32":
        pytest.skip("cli.cmd 只在 Windows 跑")
    desk, _ = _init(tmp_path)
    cli = desk / "cli.cmd"
    # python 填的是不存在的路徑：叫到了會是 9009（找不到）之類，不是 2。
    for arg in ('"a&b"', '"a|b"', '"a<b"', '"a>b"', '"a^b"', '"a!b"'):
        done = subprocess.run(f'"{cli}" queue {arg}', capture_output=True, timeout=30)
        assert done.returncode == 2, (arg, done.returncode, done.stdout, done.stderr)
    plain = subprocess.run(f'"{cli}" queue', capture_output=True, timeout=30)
    assert plain.returncode not in (0, 2)


def test_start_and_stop_cmd_detach_the_bridge():
    start = (SESSION / "start.cmd").read_text(encoding="utf-8")
    for piece in ("DISCORD_STATE_DIR=%USERPROFILE%\\.claude\\channels\\discord-support", "Start-Process", "--log",
                  "bridge.pid", "bridge-out.log", "claude --channels plugin:discord@claude-plugins-official",
                  "Oven-sh.Bun", 'cd /d "%~dp0"', "chcp 65001", "powershell -NoProfile -Command", "TIANXIA_DB=<填"):
        assert piece in start, piece
    stop = (SESSION / "stop.cmd").read_text(encoding="utf-8")
    assert "/T /F" in stop and "bridge.pid" in stop


def test_faq_is_player_facing_and_marked_for_joy():
    from test_server_bots import leaks

    text = (ROOT / "docs" / "support" / "FAQ.md").read_text(encoding="utf-8")
    for section in ("## 登入與帳號", "## 體力與行動", "## 商城與元寶", "## 換季", "## 常見誤會"):
        assert section in text, section
    questions = [line for line in text.splitlines() if line.startswith("**問：")]
    assert len(questions) >= 10
    for line in questions:
        assert line.endswith("<!-- 待 joy 潤 -->"), line
    assert text.count("答：") == len(questions)
    assert not leaks(text)
    for word in ("機率", "勝算", "docs/guide", "Config."):
        assert word not in text, word


def test_knowledge_export_writes_three_files_without_leaks(tmp_path, monkeypatch):
    from test_server_bots import FORBIDDEN, leaks

    knowledge = _load(KNOWLEDGE, "support_knowledge_t")
    assert [p.pattern for p in knowledge.FORBIDDEN] == [p.pattern for p in FORBIDDEN]  # 跟 web/ 的掃描同一張字表
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "should-not-be-touched.db"))
    desk = tmp_path / "desk"
    code = knowledge.main([str(desk), "--content", str(ROOT / "tests" / "fixtures" / "content")])
    assert code == 0
    out = desk / "knowledge"
    howto = (out / "howto.md").read_text(encoding="utf-8")
    assert howto.strip()
    assert (out / "FAQ.md").read_bytes() == (ROOT / "docs" / "support" / "FAQ.md").read_bytes()
    assert json.loads((out / "patch_notes.json").read_text(encoding="utf-8")) == json.loads(
        (ROOT / "content" / "patch_notes.json").read_text(encoding="utf-8"))
    for name in ("howto.md", "FAQ.md", "patch_notes.json"):
        text = (out / name).read_text(encoding="utf-8")
        assert not leaks(text), name
        assert "docs/guide" not in text, name
    assert not (tmp_path / "should-not-be-touched.db").exists()  # 開的是自己的暫存檔
    import os
    assert os.environ["TIANXIA_DB"] == str(tmp_path / "should-not-be-touched.db")  # 用完還原


def test_knowledge_export_refuses_a_leaking_file(tmp_path, monkeypatch):
    knowledge = _load(KNOWLEDGE, "support_knowledge_t2")
    faq = tmp_path / "FAQ.md"
    faq.write_text("問：同行的人是不是假人？\n", encoding="utf-8")
    monkeypatch.setattr(knowledge, "FAQ", faq)
    desk = tmp_path / "desk"
    code = knowledge.main([str(desk), "--content", str(ROOT / "tests" / "fixtures" / "content")])
    assert code == 1
    assert not (desk / "knowledge" / "FAQ.md").exists() and not (desk / "knowledge" / "howto.md").exists()


def test_session_scripts_do_not_import_tianxia_at_top():
    def top_imports(path: Path) -> set[str]:
        names = set()
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        return names

    def all_imports(path: Path) -> set[str]:
        names = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        return names

    assert "tianxia" not in all_imports(INIT)
    assert "tianxia" not in top_imports(KNOWLEDGE)
    assert "tianxia" in all_imports(KNOWLEDGE)  # 設好 TIANXIA_DB 之後才在函式裡 import
