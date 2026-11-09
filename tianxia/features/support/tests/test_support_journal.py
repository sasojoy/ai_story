"""「客服」紀錄先存檔成功再標（帳號與客服第 212 批；計畫「J 波落地時 PM 加的」第 3 條）：寫進存檔那一下只記成 pending，
下一輪在重讀的存檔裡看到那一則才標 journaled；那一輪存檔沒成（下一輪的存檔裡沒有）就補寫一次，之後不重複。第 211 批建的舊旁檔照讀。"""
from __future__ import annotations

import contextlib
import sqlite3

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, sidecar, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.characters import open_characters
from tianxia.database import open_database
from tianxia.engine import Game
from tianxia.features.support import accounts_view, notes, rules

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]

NAME = "沈青衫"

# 第 211 批的旁檔（只有 tickets、replies 兩張表）
OLD_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, account_created REAL NOT NULL, "
    "login TEXT NOT NULL, character TEXT NOT NULL, version TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL, "
    "status TEXT NOT NULL, admin_flag INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS tickets_status ON tickets (account_id, status)",
    "CREATE INDEX IF NOT EXISTS tickets_created ON tickets (account_id, created)",
    "CREATE TABLE IF NOT EXISTS replies (id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, by_account_id INTEGER NOT NULL, "
    "staff INTEGER NOT NULL, internal INTEGER NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, "
    "seen INTEGER NOT NULL DEFAULT 0, journaled INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS replies_ticket ON replies (ticket_id)",
)


def _load() -> Game:
    """伺服器每次進鎖從資料庫重讀角色（server._locked）：這裡也照資料庫那一份開一個 Game。"""
    return Game(server.CONTENT, open_characters().load(NAME))


def _entries(game: Game) -> list:
    return [e for e in game.state.journal if e.title == rules.JOURNAL_TITLE]


def _side(sql: str) -> list[tuple]:
    with contextlib.closing(sqlite3.connect(sidecar())) as conn:
        return conn.execute(sql).fetchall()


def _answered(monkeypatch) -> int:
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    assert s.post("/api/support/answer", json={"id": tid, "body": "已處理", "then": "wait"}).status_code == 200
    return tid


def test_entry_rewritten_when_the_save_failed(monkeypatch):
    tid = _answered(monkeypatch)
    lost = _load()
    notes.journal_replies(lost)  # 寫進了這一份，但這一輪存檔沒成（不存）
    assert len(_entries(lost)) == 1
    assert _side("SELECT journaled FROM replies WHERE staff = 1") == [(0,)]  # 旁檔不先標 1
    assert _side("SELECT ticket_id FROM pending_notes") == [(tid,)]
    again = _load()
    assert _entries(again) == []
    notes.journal_replies(again)  # 下一輪：存檔裡沒有 → 補寫
    assert [e.lines for e in _entries(again)] == [[rules.JOURNAL_LINE.format(id=tid)]]
    open_characters().save(again.state)
    after = _load()
    notes.journal_replies(after)
    notes.journal_replies(after)
    assert len(_entries(after)) == 1
    assert _side("SELECT journaled FROM replies WHERE staff = 1") == [(1,)] and _side("SELECT * FROM pending_notes") == []


def test_saved_entry_confirmed_once(monkeypatch):
    _answered(monkeypatch)
    game = _load()
    notes.journal_replies(game)
    open_characters().save(game.state)
    for _ in range(3):
        game = _load()
        notes.journal_replies(game)
        open_characters().save(game.state)
    assert len(_entries(_load())) == 1
    assert _side("SELECT journaled FROM replies WHERE staff = 1") == [(1,)] and _side("SELECT * FROM pending_notes") == []


def test_old_sidecar_still_reads(monkeypatch):
    c = player()
    who = accounts_view.by_key(open_database(), "shen_01")
    path = sidecar()
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path)) as conn:
        for sql in OLD_SCHEMA:
            conn.execute(sql)
        conn.execute("INSERT INTO tickets VALUES (1, ?, ?, 'shen_01', ?, '', 'mall', '月卡沒到', 'answered', 0, 100.0, 200.0)",
                     (who.id, who.created, NAME))
        conn.execute("INSERT INTO replies VALUES (1, 1, 99, 1, 0, '已補上', 200.0, 1, 1)")  # 舊程式寫過紀錄了
        conn.commit()
    game = _load()
    notes.journal_replies(game)
    assert _entries(game) == []  # journaled=1 的不重寫
    mine = c.get("/api/support/mine").json()["tickets"]
    assert [(t["id"], t["body"], [r["body"] for r in t["replies"]]) for t in mine] == [(1, "月卡沒到", ["已補上"])]
    tables = {r[0] for r in _side("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"tickets", "replies", "lookups", "pending_notes"} <= tables
