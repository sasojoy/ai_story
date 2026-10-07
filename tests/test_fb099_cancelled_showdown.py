"""FB-099（QA 驗管理者觸發鈕時發現）：管理者按了一場大戲的「立刻開這一場」再按「⚠ 取消決戰」，管理者工具的三場大戲那一列一直寫
「（長社火攻已經開打過了。）」、時刻表那一列寫「開打了」——可是這一仗沒打成、時間軸上也沒有結果，只能用「定結果」收尾，畫面上卻沒說。

裁決照舊：開過的記號（WorldState.showdowns_opened）留著，提早開的決戰不會再開。只改字（只有管理者看得到）：開打後被取消、
時間軸上還沒有結果的那一場，三場大戲那一列與時刻表那一列都說「開打後被取消，還沒有結果；要收尾請用「定結果」」；定了結果之後照平常的
「已經結算了」；真的打完的照舊。真實內容、週末設定的開關；管理者是「管」。"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia import timetable
from tianxia.engine import Game

NOW = 1000.0
CANCELLED = "（長社火攻開打後被取消，還沒有結果；要收尾請用「定結果」。）"


@pytest.fixture
def on(monkeypatch):
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.admins = ["管"]
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 250
    monkeypatch.setattr(server, "CONTENT", c)  # 伺服器整理管理者資料讀的是 server.CONTENT
    return c


def _admin(content):
    game = Game.new(content, "管", rng=random.Random(0))
    game.client = None
    game.sync(NOW)
    return game


def _notes(game):
    return {event.id: why for event, why in game.admin_showdowns()}


def _row(game, event_id="changshe_fire"):
    return next(r for r in server.timetable_choices(game)["timetable"] if r["id"] == event_id)


def test_open_then_cancel_says_cancelled_in_both_places(on):
    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    season = admin.world.get_season()
    assert "changshe_fire" in season.showdowns_opened and "changshe_fire" not in season.timeline  # 記號照舊、沒有結果
    assert _notes(admin)["changshe_fire"] == CANCELLED
    assert admin.admin_start_showdown("changshe_fire", NOW) == [CANCELLED]  # 照舊開不了（不會再開），按下去也是這一句
    row = _row(admin)
    assert row["state"] == "cancelled" and row["state_text"] == "開打後取消・待定結果" and row["result"] is None
    assert not row["schedulable"]  # 開過了：照舊不能再排時間


def test_open_cancel_then_set_a_result_says_settled(on):
    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    admin.admin_resolve_event("changshe_fire", "guan:大勝")
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經結算了。）"
    row = _row(admin)
    assert (row["state"], row["state_text"], row["result"]) == ("done", "已結算", "官軍大勝")


def test_a_running_battle_keeps_its_wording(on):
    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經開打過了。）"
    row = _row(admin)
    assert (row["state"], row["state_text"]) == ("running", "開打了")


def test_a_battle_that_was_fought_to_the_end_keeps_its_wording(on):
    """真的打完的（沒人上陣，回合逾時、照保底收場，時刻表照戰局判結果）：照舊「已經結算了」「已結算」。"""
    from conftest import at

    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    deadline = admin.world.get_battle().muster_deadline_real
    for now in (deadline, deadline + on.battles["changshe_fire"].round_seconds):  # 集結截止開打，再過一回合逾時照保底收場
        with at(admin, now):
            admin.options()
    assert admin.world.get_battle().phase == "ended" and "changshe_fire" in admin.world.get_season().timeline
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經結算了。）"
    assert (_row(admin)["state"], _row(admin)["state_text"]) == ("done", "已結算")


def test_a_cancelled_battle_beside_another_live_one_still_says_cancelled(on):
    """取消了長社、之後開了廣宗（另一場在打）：長社那一列照樣說取消了；廣宗是開打中。"""
    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    admin.admin_start_showdown("guangzong", NOW)
    assert admin.world.get_battle() is not None and admin.world.get_battle().phase != "ended"
    rows = {r["id"]: r["state"] for r in timetable.status_rows(admin.state, on, cancelled=admin.cancelled_showdowns())}
    assert rows["changshe_fire"] == "cancelled" and rows["guangzong"] == "running"
    assert _notes(admin)["changshe_fire"] == CANCELLED


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_drawer_shows_the_cancelled_wording(on):
    """設定抽屜的管理者工具（node 假瀏覽器，伺服器給的真資料）：三場大戲那一列與時刻表那一列都寫取消了、待定結果。"""
    admin = _admin(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    m = server.main_view(admin)
    assert m["admin"] is True
    drawer = run(m, "return H.sheetHtml();", S={"sheet": True, "admin": server.admin_choices(admin)})
    assert CANCELLED in drawer
    assert re.search(r'<span class="tt-name">第\d+週　長社火攻</span><span class="tt-state">開打後取消・待定結果</span>', drawer)
