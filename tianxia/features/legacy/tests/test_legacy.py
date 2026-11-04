"""傳承（features/legacy；架構方向 v2 第六、七節）：正氣、邪氣、機緣換季那一刻結算一次（平方根、留七成、只給門路），
識海帶一份神品意境到下一季、解封（開季一天、15 級、心得）才回到身上；名字照這一季登記、不算首創；假人也照真人。"""
from __future__ import annotations

import math
import random

import pytest
from legacy_kit import give_god, god_game, next_season

from conftest import real_content
from tianxia.core import features as features_core
from tianxia.engine import Game
from tianxia.features.legacy import actions, bots
from tianxia.features.legacy import rules as R
from tianxia.sqlite_world import open_world
from tianxia.state import ErrandState, LegacyBook


def _unsealable(game) -> None:
    p = game.state.player
    p.member.level, p.stats["xinde"] = 15, 500
    game.state.world.time = game.content.config.legacy.shihai_after


def test_gains_are_square_roots_of_the_weighted_season():
    r = real_content("season21").config.legacy
    raw = {"tasks": 4, "merit": 30, "fame": 10, "relations": 20, "good": 49, "evil": 0}
    got = R.gains(raw, r)
    assert got == {"zheng": 7.0, "xie": 0.0, "luck": round(math.sqrt(64), 2)}
    r.curve = "log"
    assert R.gains(raw, r)["zheng"] == round(math.log1p(49), 2)


def test_every_weight_starts_equal():
    weights = real_content("season21").config.legacy.weights
    assert set(weights) == {"tasks", "merit", "fame", "relations", "good", "evil"} and len(set(weights.values())) == 1


def test_settle_keeps_seventy_percent_then_adds():
    r = real_content("season21").config.legacy
    book = LegacyBook(zheng=10.0, xie=0.0, luck=5.0)
    out = R.settle(book, {"zheng": 3.0, "xie": 0.0, "luck": 0.0}, r, season=3)
    assert (out.zheng, out.xie, out.luck, out.settled) == (10.0, 0.0, 3.5, 3)
    assert book.zheng == 10.0  # 不改傳進來的那一份


def test_steady_play_leads_but_the_gap_is_bounded():
    """連續認真玩的人一直領先，但差距收斂在增量 / (1 − 七成)；停一季的人往回落。"""
    r = real_content("season21").config.legacy
    keen, rest = LegacyBook(), LegacyBook()
    for season in range(1, 30):
        keen = R.settle(keen, {"zheng": 10.0, "xie": 0.0, "luck": 0.0}, r, season)
    assert keen.zheng < 10.0 / (1 - r.keep) + 1e-6
    rest = R.settle(keen, {"zheng": 0.0, "xie": 0.0, "luck": 0.0}, r, 30)
    assert rest.zheng == pytest.approx(keen.zheng * r.keep, abs=0.01)


def test_inputs_read_the_last_season():
    game, _ = god_game()
    p = game.state.player
    p.bounties_done, p.contrib, p.showdowns, p.top_merits = 2, 40, 3, 1
    p.errands = [ErrandState(id="e1", figure="x", errand="y", kind="letter", target="yingshui", week=1, at=0, expires=1, letter=1, status="done")]
    p.stats.update(fame=9, good=16, evil=4)
    known = next(iter(game.content.figures))
    p.affinities = {known: 30, "沒這個人": 99}
    assert R.inputs(game.state, game.content) == {
        "tasks": 3.0, "merit": 44.0, "fame": 9.0, "relations": 30.0, "good": 16.0, "evil": 4.0}


def test_the_season_change_settles_once_gives_flags_and_writes_a_note():
    game, _ = god_game()
    p = game.state.player
    p.stats.update(good=100, evil=0, fame=0)
    next_season(game)
    p = game.state.player
    assert p.legacy.zheng == 10.0 and p.legacy.settled == p.season_number
    assert {"legacy_zheng_1", "legacy_zheng_2"} <= p.flags and "legacy_zheng_3" not in p.flags
    entry = next(e for e in game.state.journal if e.title == "傳承")
    assert any("正氣 10（+10）" in line for line in entry.lines) and any("這一季給了你" in line for line in entry.lines)
    actions.on_season_start(game, game.state)  # 同一季再叫一次：不再結算
    assert p.legacy.zheng == 10.0


def test_a_quiet_season_falls_back_and_drops_the_old_doors():
    game, _ = god_game()
    game.state.player.legacy = LegacyBook(zheng=10.0, settled=1)
    next_season(game)
    p = game.state.player
    assert p.legacy.zheng == 7.0 and "legacy_zheng_2" not in p.flags and "legacy_zheng_1" in p.flags


def test_nothing_carries_without_a_pick_or_once_the_pick_is_gone():
    game, iid = god_game()
    next_season(game)
    assert game.state.player.legacy.sealed is None
    game, iid = god_game()
    game.choose(f"legacy:keep:{iid}")
    del game.state.player.own_insights[iid]  # 季末之前熔掉了
    next_season(game)
    assert game.state.player.legacy.sealed is None


def test_keep_and_drop_options():
    game, iid = god_game()
    ids = [o.id for o in game.options() if o.id.startswith("legacy:")]
    assert ids == [f"legacy:keep:{iid}"]
    game.choose(f"legacy:keep:{iid}")
    assert [o.id for o in game.options() if o.id.startswith("legacy:")] == ["legacy:drop"]
    game.choose("legacy:drop")
    assert game.state.player.legacy.pick is None


def test_unsealing_waits_a_day_level_fifteen_and_xinde():
    game, iid = god_game()
    game.choose(f"legacy:keep:{iid}")
    next_season(game)
    p = game.state.player
    p.member.level, p.stats["xinde"] = 14, 0
    game.state.world.time = 0.0
    option = next(o for o in game.options() if o.id == "legacy:open")
    assert not option.enabled and "開季滿一天" in option.label and "15 級以上" in option.label
    assert game.choose("legacy:open") == ["（此刻無法這麼做。）"]
    _unsealable(game)
    assert next(o for o in game.options() if o.id == "legacy:open").enabled
    msgs = game.choose("legacy:open")
    assert any("寒江獨照" in m for m in msgs) and any("屬" in m and "武學" in m for m in msgs)
    assert p.stats["xinde"] == 500 - game.content.config.legacy.shihai_xinde
    own = next(iter(p.own_insights.values()))
    assert own.name == "寒江獨照" and own.creator == p.name
    season = game.world.get_season()
    assert season.god_names["寒江獨照"] == p.name
    assert own.id not in {v.split("|")[0] for v in season.god_firsts.values()} and "寒江獨照" not in str(season.god_firsts)


def test_a_name_taken_this_season_asks_for_another():
    game, iid = god_game()
    game.choose(f"legacy:keep:{iid}")
    next_season(game)
    game.world.mutate_season(lambda w: w.god_names.update({"寒江獨照": "別人"}))
    _unsealable(game)
    msgs = game.choose("legacy:open")
    assert "先取的人優先" in msgs[0]
    names = game.state.player.legacy.sealed.names
    assert len(names) == 3 and "寒江獨照" not in names
    assert [o.id for o in game.options() if o.id.startswith("legacy:")] == ["legacy:name:0", "legacy:name:1", "legacy:name:2"]
    game.choose("legacy:name:1")
    assert next(iter(game.state.player.own_insights.values())).name == names[1]
    assert game.world.get_season().god_names[names[1]] == game.state.player.name


def test_one_god_insight_at_a_time():
    game, iid = god_game()
    game.choose(f"legacy:keep:{iid}")
    next_season(game)
    give_god(game, "斷水流雲")  # 這一季又悟了一份
    _unsealable(game)
    option = next(o for o in game.options() if o.id == "legacy:open")
    assert not option.enabled and actions.WHY_HELD in option.label
    assert actions._open(game, None) == [actions.HOLDING]  # 選單之外直接叫也擋


def test_bots_keep_and_unseal_like_people():
    game, iid = god_game()
    keep = next(o for o in game.options() if o.id == f"legacy:keep:{iid}")
    assert features_core.bot_pick(game, keep) == (True, 30.0) and bots.score(keep) == 30.0
    game.choose(keep.id)
    drop = next(o for o in game.options() if o.id == "legacy:drop")
    assert bots.score(drop) is None and any(drop.id.startswith(p) for p in features_core.bot_always())
    next_season(game)
    _unsealable(game)
    assert bots.score(next(o for o in game.options() if o.id == "legacy:open")) == 40.0


def test_a_real_season_change_through_sync():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.legacy.enabled = True
    world = open_world()
    player = Game.new(c, "沈浪", rng=random.Random(0), world=world)
    player.skip_tutorial()
    player.sync(100.0)
    iid = give_god(player, "寒江獨照")
    player.state.player.stats["good"] = 25
    player.choose(f"legacy:keep:{iid}")
    from conftest import next_season as roll

    roll(c, world, player)
    p = player.state.player
    assert p.legacy.zheng == 5.0 and p.legacy.sealed.insight.name == "寒江獨照" and "legacy_zheng_1" in p.flags
    assert player.feature_status()["legacy"]["values"]["zheng"] == 5


class _Rng:
    """照順序吐出給的亂數。"""

    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


def test_luck_rolls_the_epiphany_once_more():
    """機緣的門路（Config.legacy.luck_reroll_flag）：頓悟沒中再擲一次；沒有那道門路、或開關關著，照舊只擲一次。"""
    from tianxia import epiphany

    game, _ = god_game()
    s, c = game.state, game.content
    c.config.epiphany.enabled = True
    s.player.own_insights.clear()
    s.player.insight_fx.clear()
    if not epiphany.on(c, s):
        pytest.skip("這一份內容沒開一條線的底座")
    odds = epiphany.chance(s, c)
    miss, hit = 0.99, odds / 2
    assert not epiphany.roll(s, c, _Rng(miss, hit)) and s.player.epiphany_dry == 1
    s.player.flags.add(c.config.legacy.luck_reroll_flag)
    assert epiphany.roll(s, c, _Rng(miss, hit))
    c.config.legacy.enabled = False
    rng = _Rng(miss, hit)
    assert not epiphany.roll(s, c, rng) and rng.values == [hit]  # 關著不多擲、不動 rng


def test_the_web_shows_the_three_values_and_the_sealed_one():
    import webharness
    from test_prologue_web import run

    import server

    if webharness.NODE is None:
        pytest.skip("沒有 node")
    game, iid = god_game()
    game.state.player.stats["good"] = 100
    game.choose(f"legacy:keep:{iid}")
    next_season(game)
    top = run(server.main_view(game), "return H.topHtml();", S={"showMore": True})
    assert "傳承　正氣 10（+10）　邪氣 0　機緣 0" in top and "識海封著：寒江獨照" in top and "正派的門路開了第 2 道" in top
    assert "傳承" not in run(server.main_view(god_game()[0]), "return H.topHtml();", S={"showMore": True})  # 還沒結算過：不畫
