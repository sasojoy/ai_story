"""鎖外工作的掛鉤（全部拆包第 69 批；計畫 docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md 第七節第 8 條）。

走過每一條路的（模型真的回話、佇列三種回法、半舊半新）是 same_behavior 的 relay 與各包那幾軌；這裡只守搬完之後的形狀：
六格的先後與歸屬、十一個 op 的歸屬與不跟別的表撞名、問在鎖內、開在鎖外、畫面丟例外一條都不開、op 不包在 act 裡。
合併工具的規矩（撞名、格不在表上、表上沒人登記）在 tests/core/test_contract_core.py。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.core import features as features_core
from tianxia.core.features import OutlockJob
from tianxia.engine import Game

JOB_OWNERS = {  # 照 act 原本那六行的先後
    "tale": "tale", "crowd": "bout", "chatter": "tavern", "letter": "companions", "yuedan": "figure_acts", "xingshi": "territory_acts",
}
OP_OWNERS = {
    "outing_say": "explore", "outing_tale": "explore", "battle_text": "battle", "seal_text": "seal", "duel_text": "bout",
    "create_intent": "craft", "create_reread": "craft", "ascend_line": "cultivation", "tavern_ask": "tavern", "feast_text": "feast",
    "persuade_text": "companions",
}


def _routes_of(pack: str) -> str:
    return f"tianxia.features.{pack}.routes"


@pytest.fixture(autouse=True)
def season_already_open(monkeypatch):
    """server.CONTENT 是正式內容（預設要管理者開季）；這裡要一季已經開打，動作才不會被擋。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)


@pytest.fixture
def game():
    return Game.new(server.CONTENT, "測試")


def _record_jobs(monkeypatch, *answers: tuple[str, object]) -> list[tuple]:
    """假的 OUTLOCK_JOBS：每一格問的時候、開的時候都記下那一刻握不握著行動鎖。"""
    calls: list[tuple] = []

    def job(slot: str, got: object) -> OutlockJob:
        def waiting(g):
            calls.append(("ask", slot, g.world.db.writing()))
            return got

        def start(g, value):
            calls.append(("start", slot, value, g.world.db.writing()))

        return OutlockJob(slot, waiting, start)

    monkeypatch.setattr(server, "OUTLOCK_JOBS", tuple(job(slot, got) for slot, got in answers))
    return calls


ASKED_THEN_STARTED = [
    ("ask", "first", True), ("ask", "second", True), ("ask", "third", True),  # 三格都在鎖內照順序問，問到沒有的不影響下一格
    ("start", "first", True, False), ("start", "third", "地點", False),  # 鎖放掉才照順序開，開的時候拿到 waiting 回的那個值
]


def test_the_six_slots_keep_the_written_order_and_each_lives_in_its_package():
    assert [job.slot for job in server.OUTLOCK_JOBS] == list(JOB_OWNERS) == list(features_core.OUTLOCK_ORDER)
    for job in server.OUTLOCK_JOBS:
        assert job.waiting.__module__ == _routes_of(JOB_OWNERS[job.slot]), job.slot
        assert job.start.__module__ == _routes_of(JOB_OWNERS[job.slot]), job.slot


def test_the_eleven_ops_live_in_their_packages_and_collide_with_no_other_table():
    assert {op: fn.__module__ for op, fn in server.OUTLOCK_OPS.items()} == {op: _routes_of(pack) for op, pack in OP_OWNERS.items()}
    others = set(server.MAIN_ACTIONS) | set(server.FEATURE_ADMIN_ACTIONS)
    assert not set(server.OUTLOCK_OPS) & others  # 同名的話 api_do 的先後會把其中一條整個蓋掉（FB-609 那一類）


def test_act_asks_inside_the_lock_and_starts_after_it(game, monkeypatch):
    calls = _record_jobs(monkeypatch, ("first", True), ("second", None), ("third", "地點"))
    assert server.act(game, lambda g: ["做了。"]) == ["做了。"]
    assert calls == ASKED_THEN_STARTED


def test_act_starts_nothing_when_the_action_raises(game, monkeypatch):
    calls = _record_jobs(monkeypatch, ("first", True))

    def boom(g):
        raise server.GameError("不行。")

    with pytest.raises(server.GameError):
        server.act(game, boom)
    assert calls == []  # 動作丟例外時整筆撤回，連問都不問


def test_act_look_asks_inside_the_lock_and_starts_after_it(game, monkeypatch):
    calls = _record_jobs(monkeypatch, ("first", True), ("second", None), ("third", "地點"))
    assert server.act_look(game, lambda g: ["做了。"], lambda g: "畫面") == (["做了。"], "畫面")
    assert calls == ASKED_THEN_STARTED


def test_act_look_starts_nothing_when_the_view_raises(game, monkeypatch):
    calls = _record_jobs(monkeypatch, ("first", True))

    def boom(g):
        raise ValueError("畫面壞了")

    with pytest.raises(ValueError):
        server.act_look(game, lambda g: None, boom)
    assert calls == []  # 畫面丟例外：一條都不問、不開（同步與存檔照舊留著，test_server 守那一半）


def test_an_outlock_op_runs_outside_the_lock_after_the_admin_tools_and_before_main_actions(monkeypatch):
    """api_do 先後：管理者工具 → ADMIN → 這裡 → MAIN → 404；B 段要叫模型，所以不包在 act 裡（鎖是 op 自己拿的）。"""
    held = []

    def fake(g, body):
        held.append(g.world.db.writing())
        return [f"收到{body['text']}"]

    monkeypatch.setitem(server.OUTLOCK_OPS, "fake_text", fake)
    monkeypatch.setitem(server.MAIN_ACTIONS, "fake_text", lambda g, b: ["不該走到這一條。"])
    client = TestClient(server.app)
    client.post("/api/register", json={"login": "outlock_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "沈青衫"})
    client.post("/api/do/skip_tutorial", json={})
    assert "收到了" in client.post("/api/do/fake_text", json={"text": "了"}).json()["message"]
    assert held == [False]
