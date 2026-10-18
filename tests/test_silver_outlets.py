"""正式季整合第 9 批：銀兩出口（設計 6.5；12.3 第 39、40、42 條）。只在 21 天季（season21 設定），週末與 14 天一個字都不變。
畫面這一批不做新版面：五樣都放在「此地還能做」。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import economy, silver
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(profile="season21", at="changshe", faction="guan", money=500):
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)  # 同一個測試第二次開：季已經開著（同一份暫存資料庫），照用
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = money
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


# ── Task 1：捐銀兩 ──


def test_donating_silver_counts_ten_to_a_point():
    game = _game()
    p, w = game.state.player, game.state.world
    option = _ids(game)["act:silver_donate"]
    assert option.enabled and "100 兩" in option.label
    msgs = game.choose("act:silver_donate")
    assert p.stats["silver"] == 400 and p.donated_today == 10
    assert game.state.world.armaments["guan"]["慢"] == 10 and p.contrib == 10
    assert any("銀兩 -100" in m for m in msgs)


def test_silver_and_materials_share_the_daily_cap():
    game = _game()
    p = game.state.player
    p.donate_day, p.donated_today = game.econ_day(), 95
    day = game.econ_day()
    assert silver.donate_amount(game.state, game.content, day, economy.donate_room(game.state, game.content, day)) == 50
    game.choose("act:silver_donate")
    assert p.stats["silver"] == 450 and p.donated_today == 100


def test_silver_donate_refused():
    game = _game(money=5)
    option = _ids(game)["act:silver_donate"]
    assert not option.enabled and "還差" in option.label
    game.choose("act:silver_donate")
    assert game.state.player.stats["silver"] == 5
    rich = _game()
    rich.state.player.donate_day, rich.state.player.donated_today = rich.econ_day(), 100
    assert not _ids(rich)["act:silver_donate"].enabled


# ── Task 2：名師指點 ──


def test_mentor_adds_ten_within_the_cap_once():
    from tianxia import cultivation

    game = _game(at="yingchuan")  # 潁川有醫館、是城鎮
    s, c = game.state, game.content
    before = cultivation.odds_for(s, c, "上品", 0)
    msgs = game.choose("act:mentor")
    assert s.player.mentor_ready and s.player.stats["silver"] == 450 and any("銀兩 -50" in m for m in msgs)
    assert cultivation.odds_for(s, c, "上品", 0) == before + 10
    c.config.cultivate_cap["上品"] = before + 4
    assert cultivation.odds_for(s, c, "上品", 0) == before + 4  # 不超過那一階的上限
    assert silver.take_mentor(s, c) == 10 and silver.take_mentor(s, c) == 0  # 擲過一次就用掉
    assert not s.player.mentor_ready


def test_mentor_once_a_day_and_refused_without_silver():
    game = _game(at="yingchuan")
    game.choose("act:mentor")
    silver.take_mentor(game.state, game.content)
    option = _ids(game)["act:mentor"]
    assert not option.enabled and silver.MENTOR_TODAY in option.label
    poor = _game(at="yingchuan", money=10)
    assert not _ids(poor)["act:mentor"].enabled
    poor.choose("act:mentor")
    assert poor.state.player.stats["silver"] == 10 and not poor.state.player.mentor_ready


def test_mentor_only_at_a_clinic_town():
    game = _game(at="changshe")
    assert "act:mentor" not in _ids(game)


# ── Task 3：看火候 ──


def test_furnace_shifts_the_base_odds_once():
    from tianxia import fusion, smithing

    game = _game(at="yingchuan")
    s, c, w = game.state, game.content, game.world
    s.player.materials = {"gang_1": 4}
    plain = smithing.forge_odds(s, c, w, "劍", "gang_1", "gang_1")
    game.choose("act:furnace")
    assert s.player.furnace_ready and s.player.stats["silver"] == 450
    warm = smithing.forge_odds(s, c, w, "劍", "gang_1", "gang_1")
    assert warm.odds["上品"] > plain.odds["上品"] and warm.odds["下品"] < plain.odds["下品"]
    assert fusion._points(c, [], s).odds == fusion.odds_from_points([], c.config.fuse_quality, c.config.silver_outlets.furnace_odds).odds
    smithing.forge(s, c, w, "劍", "gang_1", "gang_1", rng=random.Random(0))
    assert not s.player.furnace_ready  # 打一爐就用掉：之後照原本的基準
    base = c.config.weapons.quality.odds
    assert silver.furnace_base(s, c, base) is base


def test_furnace_refused_in_the_prologue_and_twice_a_day():
    game = _game(at="yingchuan")
    day = game.econ_day()
    assert silver.furnace_problem(game.state, game.content, day, in_prologue=True) == silver.FURNACE_PROLOGUE
    game.choose("act:furnace")
    assert silver.FURNACE_READY in _ids(game)["act:furnace"].label
    silver.use_furnace(game.state)
    option = _ids(game)["act:furnace"]
    assert not option.enabled and silver.FURNACE_TODAY in option.label


# ── Task 4：買破境丹 ──


def test_buying_a_legend_pill_at_the_clinic_two_a_season():
    game = _game(at="yingchuan", money=1000)
    p = game.state.player
    before = p.legend_items
    assert "這一季還能買 2 枚" in _ids(game)["act:buy_legend"].label
    game.choose("act:buy_legend")
    game.choose("act:buy_legend")
    assert p.legend_items == before + 2 and p.stats["silver"] == 400 and p.legend_bought == 2
    option = _ids(game)["act:buy_legend"]
    assert not option.enabled and silver.LEGEND_FULL in option.label
    game.choose("act:buy_legend")
    assert p.legend_items == before + 2 and p.stats["silver"] == 400


def test_picked_up_pills_do_not_count():
    game = _game(at="yingchuan", money=299)
    p = game.state.player
    p.legend_items += 3  # 撿到的
    assert p.legend_bought == 0 and "還差 1 兩" in _ids(game)["act:buy_legend"].label


# ── Task 5：打點門路（塞門房）──


def _at_a_figure(money=500):
    from tianxia import figures

    game = _game(money=money)
    s, c = game.state, game.content
    for loc in c.locations:
        here = [f for f in figures.present_at(s, c, loc) if c.figures[f].character]
        if here:
            s.player.location = loc
            return game, here[0], c.figures[here[0]].character
    raise AssertionError("沒有談得上話的大勢人物站在任何地點")


def test_bribing_adds_five_up_to_forty():
    game, fid, cid = _at_a_figure()
    p = game.state.player
    p.affinities[cid] = 10
    game.choose(f"act:bribe:{fid}")
    assert p.affinities[cid] == 15 and p.stats["silver"] == 470
    p.affinities[cid], p.bribed = 38, {}
    game.choose(f"act:bribe:{fid}")
    assert p.affinities[cid] == 40  # 只加到 40


def test_bribe_once_a_day_per_figure():
    game, fid, _ = _at_a_figure()
    game.choose(f"act:bribe:{fid}")
    option = _ids(game)[f"act:bribe:{fid}"]
    assert not option.enabled and silver.BRIBE_TODAY in option.label


def test_bribe_refused_at_forty():
    game, fid, cid = _at_a_figure()
    p = game.state.player
    p.affinities[cid] = 40
    option = _ids(game)[f"act:bribe:{fid}"]
    assert not option.enabled and silver.BRIBE_TOP in option.label
    game.choose(f"act:bribe:{fid}")
    assert p.affinities[cid] == 40 and p.stats["silver"] == 500


def test_weekend_has_no_silver_outlets():
    game = _game("weekend")
    assert not silver.on(game.content, game.state.world)
    assert not any(i.startswith(("act:silver_donate", "act:mentor", "act:furnace", "act:buy_legend", "act:bribe")) for i in _ids(game))


def test_old_save_without_outlet_fields_loads():
    from tianxia.state import PlayerState

    raw = _game().state.player.model_dump()
    for key in ("mentor_day", "mentor_ready", "furnace_day", "furnace_ready", "legend_bought", "bribed"):
        raw.pop(key, None)
    p = PlayerState.model_validate(raw)
    assert not p.mentor_ready and not p.furnace_ready and p.legend_bought == 0 and p.bribed == {}
