"""通知（帳號與客服第 211 批；設計 6.6）：客服回覆了 → 本人下一輪寫一則「客服」紀錄（只寫一次）；推播經 WEB_PUSH 送一則（None 就跳過），
notify 包多一種「客服」讓玩家能關；客服關著時 notify 的種類一個字不變。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.characters import open_characters
from tianxia.features.notify import notices
from tianxia.features.notify.webpush import PushStore
from tianxia.features.support import rules

pytestmark = pytest.mark.whole_content


class FakePush:
    def __init__(self, path):
        self.store = PushStore(path)
        self.vapid = SimpleNamespace(public="k")
        self.sent: list[tuple] = []

    def send(self, account, title, body, *, tag="", url="/", now=None):
        self.sent.append((account, title, body, tag))
        return 1


@pytest.fixture
def fake_push(monkeypatch, tmp_path):
    push = FakePush(tmp_path / "push.sqlite")
    monkeypatch.setattr(server, "WEB_PUSH", push)
    return push


def _support_entries(name="沈青衫"):
    return [e for e in open_characters().load(name).journal if e.title == rules.JOURNAL_TITLE]


@pytest.mark.usefixtures("support_on")
def test_a_staff_reply_writes_one_support_entry_once(monkeypatch):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    c.get("/api/main")
    assert _support_entries() == []
    s.post("/api/support/answer", json={"id": tid, "body": "已處理", "then": "wait"})
    s.post("/api/support/answer", json={"id": tid, "body": "補一句", "then": "admin"})  # 內部註記不寫
    c.get("/api/main")
    entries = _support_entries()
    assert [(e.title, e.tag, e.lines) for e in entries] == [("客服", "回覆了你的單", [f"客服回覆了你的第 {tid} 號單，到「設定 › 客服」看。"])]
    c.get("/api/main")
    assert len(_support_entries()) == 1
    assert "已處理" not in str(entries[0])  # 客服回的字只在客服那一格


@pytest.mark.usefixtures("support_on")
def test_no_web_push_is_fine(monkeypatch):
    monkeypatch.setattr(server, "WEB_PUSH", None)
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    assert s.post("/api/support/answer", json={"id": tid, "body": "好", "then": "wait"}).status_code == 200


@pytest.mark.usefixtures("support_on")
def test_a_reply_pushes_once_and_the_kind_can_be_turned_off(monkeypatch, fake_push):
    c = player()
    s = staffer(monkeypatch)
    tid = ticket(c).json()["id"]
    s.post("/api/support/answer", json={"id": tid, "body": "好", "then": "wait"})
    assert fake_push.sent == [("shen_01", server.NOTICE_TITLE, "客服回覆了你的單。", "support")]
    s.post("/api/support/answer", json={"id": tid, "body": "內部", "then": "admin"})
    assert len(fake_push.sent) == 1  # 內部註記不推
    assert c.get("/api/push").json()["kinds"]["support"] is True
    assert c.post("/api/push/prefs", json={"kind": "support", "on": False}).json()["kinds"]["support"] is False
    s.post("/api/support/answer", json={"id": tid, "body": "再一則", "then": "wait"})
    assert len(fake_push.sent) == 1


def test_notify_kinds_unchanged_while_closed(fake_push):
    assert notices.kinds(server.CONTENT.config) == notices.KINDS
    c = player()
    assert c.get("/api/push").json()["kinds"] == {k: True for k in ("letter", "duel", "rally", "raid", "xingshi")}
    assert c.post("/api/push/prefs", json={"kind": "support", "on": False}).status_code == 400


def test_notify_kinds_add_support_when_open(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)
    assert notices.kinds(server.CONTENT.config) == (*notices.KINDS, "support")


@pytest.mark.usefixtures("support_on")
def test_bots_never_open_the_sidecar(monkeypatch, game):
    """假人：on_own_turn 第一行就回去，旁檔的路徑一次都不問。"""
    from tianxia.features.support import notes, store

    asked = []
    monkeypatch.setattr(store, "open_store", lambda *a, **k: asked.append(a))
    game.state.player.bot = object()
    from tianxia.features import support as package

    package.FEATURE.on_own_turn(game)
    assert asked == []
    assert notes  # 模組在
