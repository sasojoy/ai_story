"""親衛隊長第三批：核心唯讀掛鉤 core/guard_base（Joy 2026-11-09「好」）。數字預設全 0：開著也不動；填了才動、而且只在投效了、帶在身邊時。"""
from __future__ import annotations

import pytest

from tianxia import team
from tianxia.core import guard_base
from tianxia.features.guard import actions
from tianxia.state import GuardBook


@pytest.fixture
def armed(game):
    t = game.content.config.guard
    t.enabled = True
    t.perks = {k: dict.fromkeys(v, 0.0) for k, v in t.perks.items()}  # 各原位的測試從 0 起算（正式數字由下面那一條守）
    t.band_perks = {k: dict.fromkeys(v, 0.0) for k, v in t.band_perks.items()}
    game.state.player.guard = GuardBook(stage="sworn", name="阿牛", sex="男", path="醫者", title="回春", qing=8, along=True)
    return game


def test_the_measured_numbers_stay_under_half_a_seal_shard(game):
    """第四批（Joy 2026-11-10「全部做完一起上」）照 scripts/measure_guard.py 量過填：人人養得到，一格不超過玉璽碎片的一半
    （碎片威力 ×1.10、閃避 +0.03）。改數字先重跑量表。"""
    t = game.content.config.guard
    flat = {k: v for table in t.perks.values() for k, v in table.items()}
    assert all(v > 0 for v in flat.values())
    assert flat["raid"] <= 0.05 and flat["ambush"] <= 0.05  # 威力倍數：碎片 0.10 的一半
    assert flat["fight_pp"] <= 3 and flat["big_fight"] <= 3
    assert flat["toll_cut"] <= 0.05
    assert all(0 < table["dodge"] <= 0.02 for table in t.band_perks.values())  # 碎片金角 0.03
    for path in t.perks:
        b = GuardBook(stage="sworn", name="阿牛", sex="男", path=path, title="試", qing=0, along=True)
        game.state.player.guard = b
        t.enabled = True
        assert all(guard_base.perk(game.state, game.content, k) == t.perks[path][k] for k in t.perks[path])


def test_every_path_has_a_perk_and_only_known_keys(game):
    t = game.content.config.guard
    known = {"big_fight", "ambush", "bounty_pct", "forge_points", "stamina_day", "tavern_asks", "raid", "fight_pp", "toll_cut",
             "explore_legend", "dodge"}
    assert set(t.perks) == {p for p, _ in t.paths}
    assert all(set(v) <= known for v in (*t.perks.values(), *t.band_perks.values()))


def test_perk_reads_path_and_band(armed):
    t = armed.content.config.guard
    t.perks["醫者"]["toll_cut"] = 0.1
    t.band_perks["敬重"]["dodge"] = 0.05
    assert guard_base.perk(armed.state, armed.content, "toll_cut") == pytest.approx(0.1)
    assert guard_base.perk(armed.state, armed.content, "dodge") == pytest.approx(0.05)
    armed.state.player.guard.qing = -15  # 恨極：不擋刀
    assert guard_base.perk(armed.state, armed.content, "dodge") == 0.0


@pytest.mark.parametrize("change", ["off", "home", "not_sworn"])
def test_no_perk_when_off_left_home_or_not_sworn(armed, change):
    armed.content.config.guard.perks["醫者"]["toll_cut"] = 0.1
    b = armed.state.player.guard
    if change == "off":
        armed.content.config.guard.enabled = False
    elif change == "home":
        b.along = False
    else:
        b.stage = "grow"
    assert guard_base.perk(armed.state, armed.content, "toll_cut") == 0.0


def test_the_dodge_site_adds_the_band_perk(armed):
    before = team.dodge_chance(armed.state, armed.content)
    armed.content.config.guard.band_perks["敬重"]["dodge"] = 0.04
    assert team.dodge_chance(armed.state, armed.content) == pytest.approx(min(1.0, before + 0.04))


def test_the_farmer_gives_stamina_each_day(armed):
    armed.state.player.guard.path = "農夫"
    p = armed.state.player
    p.stamina = 10.0
    actions.on_day(armed)
    assert p.stamina == 10.0  # 預設 0：不動
    armed.content.config.guard.perks["農夫"]["stamina_day"] = 3
    actions.on_day(armed)
    assert p.stamina == 13.0


def test_the_beggar_asks_the_tavern_more(armed):
    from tianxia.features.tavern import rules as tavern_rules

    c = armed.content
    c.config.xinshen.enabled = True
    if c.config.xinshen.ask_per_day <= 0:
        c.config.xinshen.ask_per_day = 3
    armed.state.player.guard.path = "乞丐"
    base = tavern_rules.asks_left(armed.state, c, 1)
    c.config.guard.perks["乞丐"]["tavern_asks"] = 2
    assert tavern_rules.asks_left(armed.state, c, 1) == base + 2
