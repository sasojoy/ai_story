"""減法季批 3b QA 之後的修正：約戰開著的季，兩處說法跟著規則（QA 順帶的小字；新字待 joy 潤）。

- 守軍迎戰那一場，戰報三處（回合、對面那一行、戰報的對手）寫法一樣，都是「守軍」（跟約戰卡的 defender、行狀一致）。
- 攻城軍令卡寫「打贏一場記一次」（約戰打贏真人、補位的人、守軍都記），不寫「守軍」。
子開關關著（舊出陣）兩處一個字都不變。"""
from __future__ import annotations

import pytest

from duel_kit import FAR, LOC, NOW, WINDOW, do, duel_content, duel_world, game_of, load, rounds_go, seat, text_of, tick
from tianxia import atlas, conquest, orders, sortie_duel
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


# ── 守軍迎戰：三處寫法一樣 ──


def test_the_garrison_is_called_the_garrison_everywhere_in_the_report(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang", FAR)  # 對面同區沒有人：守軍迎戰
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"), NOW)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    duel = next(iter(world.sortie_duels().values()))
    assert duel.status == "settled" and duel.defender.garrison
    squad = duel.defender.name  # 駐軍那一路的名字（潰營悍卒）：只在內部用，玩家看到的一律是「守軍」
    assert squad != sortie_duel.GARRISON
    a = load(world, "甲")
    record = a.battles[0]
    assert record.opponent == sortie_duel.GARRISON
    assert all(f"{sortie_duel.GARRISON}" in line and squad not in line for line in record.rounds)
    assert sortie_duel.vs_line(duel) in record.notes and squad not in sortie_duel.vs_line(duel)
    assert sortie_duel.vs_line(duel) == f"甲約戰，{sortie_duel.GARRISON}迎戰。"
    assert squad not in text_of(a)


def test_a_real_defender_keeps_his_own_name(monkeypatch):
    """守軍以外的應戰者（真人、補位的人）照舊寫名號。"""
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    do(c, world, "甲", lambda g: g.choose("sortie:go:強攻,固守,奇襲"), NOW)
    duel = next(iter(world.sortie_duels().values()))
    do(c, world, "乙", lambda g: g.choose(f"sortie:answer:{duel.id}:固守,固守,固守"), NOW + 60)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    record = load(world, "甲").battles[0]
    assert record.opponent == "乙" and any("乙" in line for line in record.rounds)
    assert sortie_duel.vs_line(next(iter(world.sortie_duels().values()))) == "甲約戰，乙應戰。"


# ── 攻城軍令卡：打贏一場記一次，不寫守軍 ──


NANYANG = "nanyang_road"  # 南陽官道：官軍在南陽一線能攻的中立地有四處（超過 SIEGE_NAMED_MAX，卡上寫「一帶」）

# （出陣的地點, 先在那裡推一程）：汝南荒野推過一程是只有一處的那一種，沒推過是兩處（荒丘或汝南荒野），南陽是四處
CARDS = [(LOC, True), (LOC, False), (NANYANG, False)]


def _siege_card(c, world, loc: str, push: bool) -> str:
    game = game_of(c, world, "甲")
    season = game.state.world
    if push:
        conquest.push(season, c, loc, "guan", "某", 10.0, "attack")
    front = conquest.line_of(season, c, loc)
    order = Order(id="t:guan:siege", template="siege", faction="guan", week=orders.period_of(game.state, c), front=front, quota=99, text="（測試）")
    season.orders.append(order)
    return atlas.siege_how(game.state, c, order)


@pytest.mark.parametrize(("loc", "push"), CARDS)
def test_the_siege_card_says_win_one_while_duels_are_on(loc, push):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    text = _siege_card(c, world, loc, push)
    assert "打贏一場記一次" in text and "守軍" not in text
    assert "出陣" in text


@pytest.mark.parametrize(("loc", "push"), CARDS)
def test_the_siege_card_is_unchanged_when_duels_are_off(loc, push):
    c = duel_content(off=True)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    assert "守軍記一次" in _siege_card(c, world, loc, push)
