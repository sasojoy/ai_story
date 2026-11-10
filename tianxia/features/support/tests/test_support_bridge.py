"""客服的橋（客服自動受理第 217 批；設計 6.1、第七節，企劃者 2026-11-10「照計畫繼續」）：scripts/support_bridge.py 唯讀開旁檔，
把新單、玩家再回、找真人、補圖貼到 #客服。用 support_kit 開著的伺服器造真的旁檔與單，橋自己用 sqlite3 唯讀開。
兩支腳本不在 sys.path（scripts/），用 importlib 照路徑載。"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, staffer, support_isolated, support_on, ticket  # noqa: F401
from test_server_bots import leaks

from tianxia import database
from tianxia.features.support import routes, rules

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

ROOT = Path(__file__).resolve().parents[4]
PNG = b"\x89PNG\r\n\x1a\n"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass 要在 sys.modules 裡找得到自己的模組
    spec.loader.exec_module(mod)
    return mod


bridge = _load("support_bridge")


def _up(c, tid, data: bytes = PNG + b"x"):
    r = c.post(f"/api/support/file?id={tid}", content=data, headers={"Content-Type": "image/png"})
    assert r.status_code == 200, r.text
    return r


def _ro() -> sqlite3.Connection:
    sidecar, _ = bridge.paths(database.default_path())
    return sqlite3.connect("file:" + sidecar.as_posix() + "?mode=ro", uri=True)


def _created(tid: int) -> float:
    with contextlib.closing(_ro()) as conn:
        return conn.execute("SELECT created FROM tickets WHERE id = ?", (tid,)).fetchone()[0]


def _row(tid: int) -> dict:
    conn = _ro()
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM tickets WHERE id = ?", (tid,)).fetchone())
    finally:
        conn.close()


def _scan(state: dict, now: float, grace: float = 60.0) -> list:
    conn = _ro()
    try:
        return bridge.scan(conn, state, now, grace)
    finally:
        conn.close()


def _empty() -> dict:
    return {"new": [], "reply": 0, "flag": 0, "file": 0}


def _kinds(events) -> list[tuple[str, int]]:
    return [(e.kind, e.ticket_id) for e in events]


# ── task 1：掃描 ──

def test_bridge_paths_and_categories_match_the_package():
    sidecar, files = bridge.paths(database.default_path())
    assert sidecar == routes.sidecar_path() and files == routes.files_path()
    assert bridge.CATEGORIES == rules.CATEGORIES  # 橋不能 import 包，自己一份；這裡釘死不漂


def test_bridge_scan_finds_new_reply_human_and_file_in_order(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    t1 = ticket(c, "帳號登不進去").json()["id"]
    t2 = ticket(c, "商城買了沒到", "mall").json()["id"]
    state = _empty() | {"new": [t1]}  # 單 1 貼過了
    _up(c, t1)  # 貼過的單補一張圖 → FILE
    assert c.post("/api/support/reply", json={"id": t1, "body": "還是不行"}).status_code == 200
    assert s.post("/api/support/answer", json={"id": t1, "body": "試試重登", "then": "wait"}).status_code == 200  # 客服的不貼
    assert c.post("/api/support/human", json={"id": t2}).status_code == 200
    events = _scan(state, _created(t2) + 60)
    assert _kinds(events) == [("NEW", t2), ("REPLY", t1), ("HUMAN", t2), ("FILE", t1)]
    new, reply, human, file = events
    assert new.ref == t2 and new.text == "商城買了沒到" and new.files == [] and not new.mention
    assert reply.text == "還是不行" and not reply.mention
    assert human.mention and human.files == []
    assert file.files and file.files[0].name == "1.png" and file.files[0].read_bytes() == PNG + b"x"
    with contextlib.closing(_ro()) as conn:
        assert reply.ref == conn.execute("SELECT id FROM replies WHERE staff = 0").fetchone()[0]
        assert human.ref == conn.execute("SELECT id FROM flags WHERE kind = 'human'").fetchone()[0]
        assert file.ref == conn.execute("SELECT id FROM files").fetchone()[0]


def test_bridge_new_waits_for_grace_unless_a_file_is_there():
    c = player()
    t1 = ticket(c).json()["id"]
    born = _created(t1)
    assert _scan(_empty(), born + 59) == []
    assert _kinds(_scan(_empty(), born + 60)) == [("NEW", t1)]
    t2 = ticket(c, "截圖在這").json()["id"]
    _up(c, t2)
    events = _scan(_empty() | {"new": [t1]}, _created(t2))  # 有圖：馬上貼、圖跟著 NEW 一起上，不另發 FILE
    assert _kinds(events) == [("NEW", t2)]
    assert [p.name for p in events[0].files] == ["1.png"]


def test_bridge_does_not_skip_a_ticket_still_in_grace():
    c = player()
    t1 = ticket(c, "還在等").json()["id"]
    t2 = ticket(c, "有圖先貼").json()["id"]
    _up(c, t2)
    assert c.post("/api/support/reply", json={"id": t1, "body": "補一句"}).status_code == 200
    state = _empty()
    first = _scan(state, _created(t1) + 1)
    assert _kinds(first) == [("NEW", t2)]  # 單 1 還在等，它的回覆也先停著不越過
    for e in first:
        bridge.advance(state, e)
    later = _scan(state, _created(t1) + 60)
    assert _kinds(later) == [("NEW", t1), ("REPLY", t1)]  # 時間過了，單 1 照樣貼


def test_bridge_render_has_no_login_email_phone():
    c = player("shen_01", "沈青衫")
    tid = ticket(c, "帳號登不進去").json()["id"]
    assert c.post("/api/support/human", json={"id": tid}).status_code == 200
    _up(c, tid)
    assert c.post("/api/support/reply", json={"id": tid, "body": "再試一次"}).status_code == 200
    row = _row(tid)
    events = _scan(_empty(), _created(tid))
    assert [e.kind for e in events] == ["NEW", "REPLY", "HUMAN"]
    file_event = bridge.Event("FILE", tid, 1, "", [], False)
    for e in [*events, file_event]:
        text = bridge.render(e, row, mention_ids=("111", "222"))
        assert text.startswith(f"#{tid}・帳號・沈青衫・")
        assert "shen_01" not in text and not re.search(r"09\d{8}", text) and leaks(text) == []
        if e.kind == "HUMAN":
            assert "<@111>" in text and "<@222>" in text
        else:
            assert "@" not in text
    assert "帳號登不進去" in bridge.render(events[0], row)
    long = bridge.render(bridge.Event("NEW", tid, tid, "長" * 3000, [], False), row)
    assert len(long) <= 1900 and long.endswith("…")


def test_bridge_does_not_repost_after_restart(tmp_path):
    c = player()
    tid = ticket(c).json()["id"]
    _up(c, tid)
    assert c.post("/api/support/reply", json={"id": tid, "body": "還在嗎"}).status_code == 200
    assert c.post("/api/support/human", json={"id": tid}).status_code == 200
    state = _empty()
    now = _created(tid) + 60
    events = _scan(state, now)
    assert len(events) == 3
    path = tmp_path / "support_bridge.json"
    for e in events:
        bridge.advance(state, e)
        bridge.save_state(path, state)
    again = bridge.load_state(path)
    assert again == json.loads(path.read_text(encoding="utf-8"))
    assert _scan(again, now + 600) == []
