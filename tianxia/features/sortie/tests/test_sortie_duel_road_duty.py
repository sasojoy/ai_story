"""約戰動作層的幾條路（dev/sortie-2 審查：純規則 test_sortie_duel_rules 驗了 open_problem／answer_problem 的 traveling=True，可是動作層有沒有把
journey 傳下去、同去多驗的在路上那一條、巡哨那一點貢獻，原本都沒有 pytest 守，突變了包裡包外都不紅）。只加新的、不改舊斷言：
在路上貼、應戰、同去都回「在路上，到了再說」、什麼都不扣（卡上也灰著寫同一句）；約戰開著時巡哨（act:duty）收進此地，一天第一次記一點貢獻、
同一天第二次不記，隔天照記。"""
from __future__ import annotations

import pytest

from duel_kit import FAR, LOC, MOVES, NOW, do, duel_content, duel_world, game_of, load, seat
from tianxia import conquest, sortie_duel
from tianxia.calendar import DAY

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _pair():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    return c, world


def _go(c, world, name="甲", now=NOW):
    return do(c, world, name, lambda g: g.choose(f"sortie:go:{MOVES}"), now)


def _on_the_road(c, world, name: str, now: float) -> float:
    """從汝南荒野往南陽官道上路（Game.travel，同 /api/travel）、還沒到；回上路之後的體力。"""
    msgs, _ = do(c, world, name, lambda g: g.travel(FAR), now)
    p = load(world, name).player
    assert p.journey is not None, msgs
    return p.stamina


def _only(world):
    duels = world.sortie_duels()
    assert len(duels) == 1, duels
    return next(iter(duels.values()))


# ── 在路上 ──


def test_on_the_road_posting_is_refused_and_costs_nothing():
    """sortie_go_problem 傳 traveling=p.journey is not None 給 open_problem：在路上貼不了、不扣次數與體力、不起冷卻。"""
    c, world = _pair()
    stamina = _on_the_road(c, world, "甲", NOW)
    msgs, _ = _go(c, world, now=NOW + 30)
    assert msgs == [f"（{sortie_duel.WHY_ROAD}。）"]
    assert world.sortie_duels() == {}
    p = load(world, "甲").player
    assert (p.sorties_today, p.stamina, p.sortie_cooldown_until) == (0, stamina, None)


def test_on_the_road_answering_is_refused_and_costs_nothing():
    """sortie_answer 傳 traveling=p.journey is not None 給 answer_problem：同一大區出發、還在路上的對面應不了戰（不是「不在那個大區」那一句），
    卡上的應戰鈕也灰著寫同一句；什麼都不扣。"""
    c, world = _pair()
    _go(c, world)
    duel = _only(world)
    stamina = _on_the_road(c, world, "乙", NOW + 30)
    card = game_of(c, world, "乙", NOW + 60).sortie_cards()[0]
    assert card["role"] == "answer" and not card["can_answer"] and card["why_not"] == sortie_duel.WHY_ROAD
    msgs, _ = do(c, world, "乙", lambda g: g.choose(f"sortie:answer:{duel.id}:固守,固守,固守"), NOW + 60)
    assert msgs == [f"（{sortie_duel.WHY_ROAD}。）"]
    assert _only(world).status == "open" and _only(world).defender is None
    p = load(world, "乙").player
    assert (p.answers_today, p.stamina) == (0, stamina)


def test_on_the_road_joining_is_refused_and_costs_nothing():
    """duel_join_extra 第一條：同袍在路上同去不了（不是「才同得了去」那一句），卡上的同去鈕也灰著寫同一句；不扣次數、體力，不記進 allies。"""
    c, world = _pair()
    seat(c, world, "丙", "guan")
    _go(c, world)
    duel = _only(world)
    stamina = _on_the_road(c, world, "丙", NOW + 30)
    card = game_of(c, world, "丙", NOW + 60).sortie_cards()[0]
    assert card["role"] == "join" and not card["can_join"] and card["why_not"] == sortie_duel.WHY_ROAD
    msgs, _ = do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel.id}"), NOW + 60)
    assert msgs == [f"（{sortie_duel.WHY_ROAD}。）"]
    assert _only(world).attacker.allies == []
    p = load(world, "丙").player
    assert (p.sorties_today, p.stamina, p.sortie_cooldown_until) == (0, stamina, None)


# ── 巡哨那一點貢獻（duty_credit）──


def _own_block(c, world) -> str:
    season = world.get_season()
    return next(b for b in conquest.blocks(c) if conquest.capturable(c, b) and conquest.holder(season, c, b) == "guan")


def _duty(c, world, name: str, now: float):
    game = game_of(c, world, name, now)
    cell = next((o for o in game.options() if o.id == "act:duty"), None)
    assert cell is not None and cell.enabled, cell
    return do(c, world, name, lambda g: g.choose("act:duty"), now)


def test_duty_in_a_duel_season_credits_one_point_once_a_day():
    c, world = _pair()
    cfg = c.config.sortie
    seat(c, world, "甲", "guan", _own_block(c, world))
    first, _ = _duty(c, world, "甲", NOW)
    p = load(world, "甲").player
    assert f"貢獻 +{cfg.duty_contribution}" in first
    assert (p.contrib, p.duties_today, p.sorties_today) == (cfg.duty_contribution, 1, 0)  # 收進此地：不佔出陣的次數
    seat(c, world, "甲", "guan", _own_block(c, world))  # 體力補滿（同一天第二次）
    second, _ = _duty(c, world, "甲", NOW + 60)
    p = load(world, "甲").player
    assert not any(m.startswith("貢獻 +") for m in second)
    assert (p.contrib, p.duties_today) == (cfg.duty_contribution, 1)
    seat(c, world, "甲", "guan", _own_block(c, world))
    third, _ = _duty(c, world, "甲", NOW + DAY)  # 隔天（_pill_day 換了）：照記
    p = load(world, "甲").player
    assert f"貢獻 +{cfg.duty_contribution}" in third
    assert (p.contrib, p.duties_today) == (2 * cfg.duty_contribution, 1)
