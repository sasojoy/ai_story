"""客服官的手（客服自動受理第 217 批；設計 6.2、第七節，企劃者 2026-11-10「照計畫繼續」）：scripts/support_cli.py 只打 HTTP（Bearer），
queue、ticket、answer、note、close。測試注入一個沒有 cookie 的新 TestClient、--url http://testserver，金鑰檔是 support_kit 造的暫存檔。"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest
import server
from fastapi.testclient import TestClient
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import FAKE_TOKEN, bot_setup, player, staffer, support_isolated, support_on, ticket  # noqa: F401
from test_server_bots import leaks

from tianxia.core import identity_base
from tianxia.features.support import rules

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

ROOT = Path(__file__).resolve().parents[4]
PNG = b"\x89PNG\r\n\x1a\n"
URL = "http://testserver"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cli = _load("support_cli")


class _Spy:
    """包一層新的 TestClient（沒有 cookie）：記下打過的 (方法, 路徑, json)。"""

    def __init__(self):
        self.client = TestClient(server.app, raise_server_exceptions=False)
        self.calls: list[tuple[str, str, object]] = []

    def request(self, method, url, headers=None, json=None):
        self.calls.append((method, url.removeprefix(URL), json))
        return self.client.request(method, url, headers=headers, json=json)


def _desk(monkeypatch, local) -> Path:
    player("desk_01", "青鸞")
    bot_setup(monkeypatch, local)
    return local / identity_base.SUPPORT_BOT_FILE


def _run(cfg: Path, *argv, stdin: str | None = None, monkeypatch=None, spy=None):
    spy = spy or _Spy()
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8")), encoding="utf-8"))
    code = cli.main(["--config", str(cfg), "--url", URL, *argv], session=spy)
    return code, spy


def test_cli_queue_labels_four_kinds(monkeypatch, support_isolated, capsys):
    cfg = _desk(monkeypatch, support_isolated)
    a, b = player(), player("wang_03", "王小二")
    s = staffer(monkeypatch)
    t_admin = ticket(a, "請管理者看").json()["id"]
    t_human = ticket(a, "要找真人").json()["id"]
    t_wait = ticket(b, "等玩家回").json()["id"]
    t_desk = ticket(b, "還沒人回\n第二行").json()["id"]
    assert s.post("/api/support/answer", json={"id": t_admin, "body": "轉管理者", "then": "admin"}).status_code == 200
    assert a.post("/api/support/human", json={"id": t_human}).status_code == 200
    assert s.post("/api/support/answer", json={"id": t_wait, "body": "試試重登", "then": "wait"}).status_code == 200
    capsys.readouterr()
    code, spy = _run(cfg, "queue")
    assert code == 0
    assert [c[:2] for c in spy.calls] == [("POST", "/api/support/sweep"), ("GET", "/api/support/queue")]
    out = capsys.readouterr().out
    line = {int(m.group(1)): m.group(0) for m in re.finditer(r"^#(\d+) .*$", out, re.M)}
    assert cli.LABELS["admin"] in line[t_admin] and cli.LABELS["human"] in line[t_human]
    assert cli.LABELS["answered"] in line[t_wait] and cli.LABELS["desk"] in line[t_desk]
    assert "還沒人回 第二行" in line[t_desk] and "沈青衫" in line[t_admin] and "帳號" in line[t_admin]
    assert out.strip().splitlines()[-1] == cli.COUNTS.format(admin=1, human=1, answered=1, desk=1)
    assert "shen_01" not in out and "wang_03" not in out


def test_cli_ticket_prints_card_and_saves_files(monkeypatch, support_isolated, capsys, tmp_path):
    cfg = _desk(monkeypatch, support_isolated)
    c = player("shen_01", "沈青衫")
    tid = ticket(c, "截圖在這").json()["id"]
    assert c.post(f"/api/support/file?id={tid}", content=PNG + b"pic", headers={"Content-Type": "image/png"}).status_code == 200
    assert c.post("/api/support/reply", json={"id": tid, "body": "補一句"}).status_code == 200
    capsys.readouterr()
    inbox = tmp_path / "inbox"
    code, spy = _run(cfg, "--inbox", str(inbox), "ticket", str(tid))
    assert code == 0
    saved = inbox / str(tid) / "1.png"
    assert saved.read_bytes() == PNG + b"pic"
    out = capsys.readouterr().out
    assert str(saved.resolve()) in out
    assert "截圖在這" in out and "補一句" in out and cli.WHO["player"] in out
    assert "沈青衫" in out and rules.PROVIDER_NAMES["password"] in out  # 帳號卡：名號、綁了哪幾種
    assert "shen_01" not in out and "@" not in out and not re.search(r"09\d{8}", out)
    assert ("GET", f"/api/support/file/{tid}/1", None) in spy.calls


def test_cli_answer_note_close_read_stdin(monkeypatch, support_isolated, capsys):
    cfg = _desk(monkeypatch, support_isolated)
    c = player()
    tid = ticket(c).json()["id"]
    code, spy = _run(cfg, "answer", str(tid), stdin="試試重登\n", monkeypatch=monkeypatch)
    assert code == 0 and spy.calls == [("POST", "/api/support/answer", {"id": tid, "body": "試試重登", "then": "wait"})]
    code, spy = _run(cfg, "answer", str(tid), "--human", "227500", stdin="管理者說好", monkeypatch=monkeypatch)
    assert code == 0 and spy.calls[0][2] == {"id": tid, "body": "管理者說好", "then": "wait", "relay_from": "227500"}
    code, spy = _run(cfg, "note", str(tid), stdin="要查金流", monkeypatch=monkeypatch)
    assert code == 0 and spy.calls[0][2] == {"id": tid, "body": "要查金流", "then": "admin"}
    code, spy = _run(cfg, "answer", str(tid), "--close", stdin="好了", monkeypatch=monkeypatch)
    assert code == 0 and spy.calls[0][2]["then"] == "close"
    tid2 = ticket(c, "第二張").json()["id"]
    code, spy = _run(cfg, "close", str(tid2))
    assert code == 0 and spy.calls == [("POST", "/api/support/close", {"id": tid2})]
    for argv in (("answer", str(tid)), ("note", str(tid))):
        code, spy = _run(cfg, *argv, stdin=" \n\t", monkeypatch=monkeypatch)
        assert code == 1 and spy.calls == []
    assert cli.EMPTY in capsys.readouterr().out
    code, spy = _run(cfg, "answer", str(tid), "--human", "abc", stdin="x", monkeypatch=monkeypatch)
    assert code == 2 and spy.calls == []


def test_cli_locked_mode_refuses_path_flags(monkeypatch, support_isolated, capsys, tmp_path):
    cfg = _desk(monkeypatch, support_isolated)
    monkeypatch.setenv("TIANXIA_SUPPORT_LOCKED", "1")
    monkeypatch.setenv("TIANXIA_SUPPORT_CONFIG", str(cfg))
    monkeypatch.setenv("TIANXIA_SUPPORT_URL", URL)
    monkeypatch.setenv("TIANXIA_SUPPORT_INBOX", str(tmp_path / "inbox"))
    for argv in (["--inbox", "x", "queue"], ["--inbox=x", "queue"], ["--config", "x", "queue"], ["--config=x", "queue"],
                 ["--url", "http://127.0.0.1:9", "queue"], ["--url=http://127.0.0.1:9", "queue"], ["--conf", "x", "queue"],
                 ["ticket", "1", "--inbox", "x"]):
        spy = _Spy()
        assert cli.main(argv, session=spy) == 2, argv
        assert spy.calls == []
    assert cli.LOCKED in capsys.readouterr().out
    spy = _Spy()
    assert cli.main(["queue"], session=spy) == 0  # 路徑照環境變數
    assert [c[1] for c in spy.calls] == ["/api/support/sweep", "/api/support/queue"]


def test_cli_refusal_and_bad_token_messages(monkeypatch, support_isolated, capsys):
    cfg = _desk(monkeypatch, support_isolated)
    c = player()
    tid = ticket(c).json()["id"]
    long = "長" * (server.CONTENT.config.support.body_max + 1)
    capsys.readouterr()
    code, _ = _run(cfg, "answer", str(tid), stdin=long, monkeypatch=monkeypatch)
    assert code == 1 and rules.body_problem(long, server.CONTENT.config.support.body_max) in capsys.readouterr().out
    code, _ = _run(cfg, "ticket", str(tid + 99))
    assert code == 1 and rules.NOT_FOUND in capsys.readouterr().out
    wrong = support_isolated / "wrong.json"
    wrong.write_text(json.dumps({"bot_token": "not-the-right-one"}), encoding="utf-8")
    code, _ = _run(wrong, "queue")
    assert code == 2 and cli.BAD_TOKEN in capsys.readouterr().out
    none = support_isolated / "none.json"
    none.write_text(json.dumps({"server_url": URL}), encoding="utf-8")
    code, spy = _run(none, "queue")
    assert code == 2 and spy.calls == [] and cli.BAD_TOKEN in capsys.readouterr().out
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", False)  # 開關關著：每條路 404 → token 那一句
    code, _ = _run(cfg, "queue")
    assert code == 2 and cli.BAD_TOKEN in capsys.readouterr().out


def test_cli_output_never_leaks(monkeypatch, support_isolated, capsys, tmp_path):
    cfg = _desk(monkeypatch, support_isolated)
    c = player()
    tid = ticket(c).json()["id"]
    assert c.post(f"/api/support/file?id={tid}", content=PNG + b"x", headers={"Content-Type": "image/png"}).status_code == 200
    assert c.post("/api/support/human", json={"id": tid}).status_code == 200
    runs = [("queue",), ("--inbox", str(tmp_path / "in"), "ticket", str(tid)), ("note", str(tid)), ("answer", str(tid)),
            ("--inbox", str(tmp_path / "in"), "ticket", str(tid)), ("close", str(tid)), ("queue",)]
    for argv in runs:
        _run(cfg, *argv, stdin="知道了", monkeypatch=monkeypatch)
    out = capsys.readouterr()
    text = out.out + out.err
    assert cli.WHO["auto"] in text and cli.WHO["internal"] in text
    assert leaks(text) == [] and FAKE_TOKEN not in text and "shen_01" not in text


def test_bridge_and_cli_do_not_import_tianxia():
    for name in ("support_bridge", "support_cli"):
        tree = ast.parse((ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] in ("tianxia", "server") for a in node.names), name
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in ("tianxia", "server") and node.level == 0, name
