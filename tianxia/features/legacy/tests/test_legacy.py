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
    r.weights = dict.fromkeys(r.weights, 1.0)
    raw = {"tasks": 4, "merit": 30, "fame": 10, "relations": 20, "good": 49, "evil": 0}
    got = R.gains(raw, r)
    assert got == {"zheng": 7.0, "xie": 0.0, "luck": round(math.sqrt(64), 2)}
    r.curve = "log"
    assert R.gains(raw, r)["zheng"] == round(math.log1p(49), 2)


def test_weights_line_up_the_live_ninetieth_percentile():
    """Joy 11/4「照建議」：正式站 60 個真人的九成位（tasks 4、merit 2075、fame 173、relations 210）乘上權重差不多一樣重。"""
    w = real_content("season21").config.legacy.weights
    assert w == {"tasks": 40.0, "merit": 0.1, "fame": 1.0, "relations": 1.0, "good": 1.0, "evil": 1.0}
    shares = [4 * w["tasks"], 2075 * w["merit"], 173 * w["fame"], 210 * w["relations"]]
    assert max(shares) / min(shares) < 1.4


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


def test_the_season_start_offers_every_god_of_last_season():
    game, _ = god_game()
    next_season(game)
    book = game.state.player.legacy
    assert book.sealed is None and [o.insight.name for o in book.offers] == ["寒江獨照"]
    assert [o.id for o in game.options() if o.id.startswith("legacy:")] == ["legacy:seal:0", "legacy:skip"]
    entry = next(e for e in game.state.journal if e.title == "傳承")
    assert any("「寒江獨照」" in line and "第一件事之前" in line for line in entry.lines)
    game, _ = god_game()
    give_god(game, "斷水流雲")
    next_season(game)
    assert [o.insight.name for o in game.state.player.legacy.offers] == ["寒江獨照", "斷水流雲"]
    game, _ = god_game()  # 上一季傳承還關著（第 8 季）：身上沒有 LegacyBook，開季照樣抄
    assert game.state.player.legacy is None
    next_season(game)
    assert [o.insight.name for o in game.state.player.legacy.offers] == ["寒江獨照"]
    game, _ = god_game()
    game.state.player.own_insights.clear()  # 季末之前熔掉了：沒有可帶的
    next_season(game)
    assert game.state.player.legacy.offers == []


def test_seal_or_skip_before_the_first_move():
    game, _ = god_game()
    give_god(game, "斷水流雲")
    next_season(game)
    msgs = game.choose("legacy:seal:1")
    book = game.state.player.legacy
    assert any("斷水流雲" in m and "封進識海" in m for m in msgs)
    assert book.sealed.insight.name == "斷水流雲" and book.offers == []
    assert not any(o.id.startswith("legacy:seal") for o in game.options())
    game, _ = god_game()
    next_season(game)
    assert game.choose("legacy:skip") == [actions.SKIPPED] and game.state.player.legacy.sealed is None


def test_the_first_other_move_closes_the_offer():
    game, _ = god_game()
    next_season(game)
    other = next(o for o in game.options() if o.enabled and not o.id.startswith("legacy:"))
    msgs = game.choose(other.id)
    assert actions.LAPSED in msgs
    book = game.state.player.legacy
    assert book.offers == [] and book.sealed is None
    assert actions.LAPSED not in game.choose(next(o for o in game.options() if o.enabled).id)  # 只說一次


def test_unsealing_waits_a_day_level_fifteen_and_xinde():
    game, iid = god_game()
    next_season(game)
    game.choose("legacy:seal:0")
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
    next_season(game)
    game.choose("legacy:seal:0")
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
    next_season(game)
    game.choose("legacy:seal:0")
    give_god(game, "斷水流雲")  # 這一季又悟了一份
    _unsealable(game)
    option = next(o for o in game.options() if o.id == "legacy:open")
    assert not option.enabled and actions.WHY_HELD in option.label
    assert actions._open(game, None) == [actions.HOLDING]  # 選單之外直接叫也擋


def test_bots_seal_first_and_unseal_like_people():
    game, _ = god_game()
    next_season(game)
    seal = next(o for o in game.options() if o.id == "legacy:seal:0")
    assert features_core.bot_pick(game, seal) == (True, 60.0) and bots.score(seal) == 60.0
    skip = next(o for o in game.options() if o.id == "legacy:skip")
    assert bots.score(skip) is None and any(skip.id.startswith(p) for p in features_core.bot_always())
    game.choose(seal.id)
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
    give_god(player, "寒江獨照")
    player.state.player.stats["good"] = 25
    from conftest import next_season as roll

    roll(c, world, player)
    player.choose("legacy:seal:0")
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
    """機緣的第一道門路（Config.legacy.doors["epiphany"]）：頓悟沒中再擲一次；沒有那道門路、或開關關著，照舊只擲一次。"""
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
    s.player.flags.add("legacy_luck_1")
    assert epiphany.roll(s, c, _Rng(miss, hit))
    c.config.legacy.enabled = False
    rng = _Rng(miss, hit)
    assert not epiphany.roll(s, c, rng) and rng.values == [hit]  # 關著不多擲、不動 rng


def test_the_web_shows_the_three_values_and_the_sealed_one():
    import webharness
    from test_legacy_web import run as run_page
    from test_prologue_web import run

    import server

    if webharness.NODE is None:
        pytest.skip("沒有 node")
    game, iid = god_game()
    game.state.player.stats["good"] = 100
    next_season(game)
    game.choose("legacy:seal:0")
    view = server.main_view(game)
    top = run(view, "return H.topHtml();", S={"showMore": True})
    assert 'data-act="legacy-open"' in top and "正氣 10" in top and "識海封著：寒江獨照" in top
    page = run_page(view["legacy"], "main")
    assert page.count('class="lg-slip open"') == 2 and "俠義的事多一種做法" in page  # 正氣 5、10 兩道（長句在竹簡的 aria-label）
    sea = run_page(view["legacy"], "shihai")
    assert "寒江獨照" in sea and 'data-id="legacy:open" disabled' in sea  # 開季還不滿一天、等級心得也不夠
    fresh = god_game()[0]
    assert "legacy-open" not in run(server.main_view(fresh), "return H.topHtml();", S={"showMore": True})  # 還沒結算過：不畫
    next_season(fresh)
    fresh.content.config.legacy.enabled = False
    assert "legacy-open" not in run(server.main_view(fresh), "return H.topHtml();", S={"showMore": True})  # 開關關著：不畫


def test_status_lists_tracks_seals_and_offers():
    game, _ = god_game()
    assert "legacy" not in game.feature_status()  # 還沒結算過
    next_season(game)
    st = game.feature_status()["legacy"]
    assert [t["short"] for t in st["tracks"]["zheng"]] == ["書院不問惡名", "俠義多一法", "俠士相敬"]
    assert st["shihai"]["sealed"] is None and [o["name"] for o in st["shihai"]["offers"]] == ["寒江獨照"]
    assert [n["key"] for n in st["shihai"]["need"]] == ["time", "level", "xinde"] and not st["shihai"]["held"]
    game.choose("legacy:seal:0")
    st = game.feature_status()["legacy"]["shihai"]
    assert st["sealed"]["name"] == "寒江獨照" and st["offers"] == []
    _unsealable(game)
    assert all(n["ok"] for n in game.feature_status()["legacy"]["shihai"]["need"])


def test_doors_open_only_with_the_switch_on():
    from tianxia import renown

    game, _ = god_game()
    s, c = game.state, game.content
    s.player.flags |= {"legacy_zheng_1", "legacy_zheng_2", "legacy_xie_1"}
    s.player.stats.update(good=0, evil=0)
    assert renown.open_to(s, c, "choices", "俠", 1) and not renown.open_to(s, c, "choices", "俠", 2)  # 只開到第一段
    assert renown.open_to(s, c, "lessons", "俠", 1) and renown.open_to(s, c, "lessons", "寇", 1)
    assert not renown.open_to(s, c, "choices", "寇", 1)
    assert not renown.meets(s, c, "俠", 1)  # 通緝、黑市、醫館照舊只看名聲
    c.config.legacy.enabled = False
    assert not renown.open_to(s, c, "choices", "俠", 1)


def test_the_third_doors_warm_up_the_figures_who_care():
    game, _ = god_game()
    c = game.content
    keen = next(cid for cid, ch in c.characters.items() if ch.regard == "敬俠")
    hard = next(cid for cid, ch in c.characters.items() if ch.regard == "喜狠")
    game.state.player.legacy = LegacyBook(zheng=30.0, settled=1)
    next_season(game)
    p = game.state.player
    assert "legacy_zheng_3" in p.flags and p.affinities.get(keen, 0) >= c.config.legacy.regard_bonus
    assert p.affinities.get(hard, 0) < c.config.legacy.regard_bonus


def test_luck_weighs_the_qiyu_and_rolls_long_tales_again():
    from tianxia import events, storyline

    game, _ = god_game()
    s, c = game.state, game.content
    base = events.qiyu_multiplier(s, c)
    s.player.flags.add("legacy_luck_2")
    assert events.qiyu_multiplier(s, c) == pytest.approx(base * (1 + c.config.legacy.qiyu_boost))
    assert not storyline._luck_again(s, c)
    s.player.flags.add("legacy_luck_3")
    assert storyline._luck_again(s, c)


def test_the_academy_takes_a_righteous_heir_with_some_infamy():
    from tianxia.rules import check_condition

    game, _ = god_game()
    s, c = game.state, game.content
    cond = c.events["yingchuan_join"].condition
    s.player.sect, s.player.stats["evil"] = None, 20
    assert not check_condition(cond, s, c)
    s.player.flags.add("legacy_zheng_1")
    assert check_condition(cond, s, c)
