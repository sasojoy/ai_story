"""減法季批 3b 收尾：約戰結算記一則行狀（annals.DUEL；計畫 8.0 的「3b 約戰結算 → DUEL」，給 7b-1 剩下的那一小步〔列傳讀約戰〕認得出來）。

攻方與應戰的人各記一則「在某地約戰某某，結果。」，地點是約戰的那一塊（結算時人已經走了也一樣）；同去的人沒下場不記。行狀頁的小標與
季末的傳的段落都跟其他單挑一樣（KINDS 寫「交手」、GROUPS 歸 FIGHT），畫面上看不出差別。"""
from __future__ import annotations

import pytest

from duel_kit import FAR, LOC, MOVES, NOW, WINDOW, do, duel_content, duel_world, load, rounds_go, seat, tick
from tianxia import annals

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _settled(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    seat(c, world, "丙", "guan")
    rounds_go(monkeypatch, "大勝")
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    duel_id = next(iter(world.sortie_duels()))
    do(c, world, "乙", lambda g: g.choose(f"sortie:answer:{duel_id}:固守,固守,固守"), NOW + 60)
    do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel_id}"), NOW + 90)
    seat(c, world, "乙", "huang", FAR)  # 應戰之後走了：行狀的地點照樣寫約戰的那一塊
    tick(c, world, NOW + WINDOW + 1)
    return c, world


def _duels(world, name):
    return [e for e in load(world, name).player.annals if e.kind == annals.DUEL]


def test_both_fighters_get_a_duel_annal_at_the_duel_place(monkeypatch):
    c, world = _settled(monkeypatch)
    place = c.locations[LOC].name
    mine, theirs = _duels(world, "甲"), _duels(world, "乙")
    assert [e.text for e in mine] == [f"在{place}約戰乙，大勝。"]
    assert [e.text for e in theirs] == [f"在{place}約戰甲，落敗。"]
    assert mine[0].place == theirs[0].place == place
    assert _duels(world, "丙") == []  # 同去的人沒下場


def test_duel_annals_read_like_any_other_fight(monkeypatch):
    assert annals.KINDS[annals.DUEL] == annals.KINDS[annals.FIGHT]
    assert annals.GROUPS[annals.DUEL] == annals.FIGHT
    assert annals.heard(annals.AnnalEntry(kind=annals.DUEL, time=0, when="", text="x"))  # 酒肆照樣打聽得到（同其他單挑）
