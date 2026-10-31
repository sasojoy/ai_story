"""探索三選一（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第三節）。正式內容、週末設定。
潁水河畔：危險度 1、野外、素材屬柔與慢、站河灘潑皮與偷網賊（都無陣營）、悟得到水。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import classic_rules, real_content
from jianfa_kit import classic_explore
from tianxia import engine as engine_mod
from tianxia import explore_modes, rules, sensing, team, treasures
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Bounty


def _game(faction=None, at="yingshui", **cfg):
    c = real_content("week7")  # 領地加成（自家領地找素材多一份）另測（tests/test_conquest_rules.py）
    classic_explore(c)  # 探索三選一本身（減法季探索一顆開著時選單上沒有這幾顆，tests/test_explore_one.py）
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.duel.explore_chance = 0.0  # 頭目戰另外測（tests/test_duel.py）：這裡的地點有頭目也不擲中
    c.config.precise_actions = False  # 一類一顆之前的三選一（新規則在 tests/test_precise_actions.py，設計 8.4）
    for key, value in cfg.items():
        setattr(c.config.explore_modes, key, value)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def _fight(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=10))


def _bag(game):
    return dict(game.state.player.materials)


def _new(before, after):
    return [mid for mid, n in after.items() for _ in range(n - before.get(mid, 0))]


def test_explore_opens_three_ways():
    opts = _ids(_game())
    assert "act:explore" in opts
    assert [opts[explore_modes.option_id(m)].label for m in explore_modes.MODES] == [
        "找素材（體力 6）", "找事件（體力 6）", "靜心感悟（體力 6）"]


def test_the_entry_does_not_say_stamina():
    """PM 2026-10-14：三選一開著時「探索」入口按了不花體力，所以鈕上不寫體力、三顆各自寫；體力不夠三顆都灰時入口也灰。
    開關關著照舊「探索（體力 6）」。"""
    game = _game()
    entry = _ids(game)["act:explore"]
    assert entry.label == "探索" and entry.enabled
    game.state.player.stamina = 0
    assert not _ids(game)["act:explore"].enabled
    game.state.player.stamina = 100
    game.content.config.explore_modes.enabled = False
    assert _ids(game)["act:explore"].label == "探索（體力 6）"


def test_sense_is_grey_where_nothing_can_be_learned():
    """悟不出＝insights.explore_gives 是空的：這類地點的 explore_mix 悟意境比例是 0（地點沒寫 insights 會退回全部基本意境，
    所以正式內容現在每一處都悟得到；這裡把野外那一類的比例設成 0 造一處悟不出的）。"""
    game = _game()
    c = game.content
    c.config.explore_mix_of(c.locations["yingshui"].tags).weights["insight"] = 0
    sense = _ids(game)["explore:sense"]
    assert not sense.enabled and sense.label == f"靜心感悟（{explore_modes.NO_SENSE}）"


def test_explore_itself_only_points_at_the_three():
    game = _game()
    stamina, journal = game.state.player.stamina, len(game.state.journal)
    assert game.choose("act:explore") == [explore_modes.PICK]
    assert game.state.player.stamina == stamina and len(game.state.journal) == journal


@pytest.mark.smoke
def test_gathering_in_the_wild_gives_a_first_tier_of_the_places_kind():
    game = _game(encounter_chance=0.0)
    before = _bag(game)
    game.choose("explore:gather")
    got = _new(before, _bag(game))
    c = game.content
    assert len(got) == 1 and c.materials[got[0]].tier == 1 and c.materials[got[0]].attribute in {"柔", "慢"}
    assert game.state.player.stamina == c.config.stamina_max - 6 and game.state.battles == []


def test_dangerous_places_add_a_second_tier():
    game = _game(faction="huang", at="huangjin_camp", encounter_chance=0.0, second_tier={3: 1.0})
    before = _bag(game)
    game.choose("explore:gather")
    got = sorted(game.content.materials[m].tier for m in _new(before, _bag(game)))
    assert got.count(2) == 1 and 1 in got  # 自家的領地多一份一階（領地加成，tests/acts/test_conquest_rules.py）


def test_towns_never_fight_and_find_half_the_time():
    game = _game(at="yingchuan", encounter_chance=1.0, town_chance=1.0)
    before = _bag(game)
    game.choose("explore:gather")
    assert len(_new(before, _bag(game))) == 1 and game.state.battles == []
    game.content.config.explore_modes.town_chance = 0.0
    assert explore_modes.GATHER_NONE in game.choose("explore:gather")


def test_a_gathering_fight_is_the_weakest_foe_and_pays_in_full():
    game = _game(at="yingchuan_wilds", encounter_chance=1.0)  # 流寇散兵（8）、黃巾散兵（15）
    with _fight():
        game.choose("explore:gather")
    record = game.state.battles[-1]
    assert record.kind == "wild" and record.opponent == "流寇散兵" and record.silver == 5


def test_a_gathering_fight_chains_an_after_battle_event():
    game = _game(at="yingchuan_wilds", encounter_chance=1.0)
    game.content.config.train_event_chance = 1.0
    with _fight(), mock.patch.object(engine_mod, "pick_event", wraps=engine_mod.pick_event) as picked:
        game.choose("explore:gather")
    assert any(call.args[2] == "train" for call in picked.call_args_list)


def test_a_ranger_finishes_a_strike_bounty_after_the_spot_changed_hands():
    """Review Focus 5：揭了「汝南荒野打黃巾嘍囉」，汝南荒野被官軍拿回去（站的換成官軍）；找素材撞上的照樣是黃巾嘍囉，打贏交差。"""
    game = _game(at="runan_wilds", encounter_chance=1.0)
    w = game.state.world
    w.bounties.append(Bounty(id="b1", kind="strike", faction="guan", week=1, expires=1e12, silver=20, deeds=1,
                             location="runan_wilds", squad="louluo", takers=["沈浪"]))
    rules.change_trend(game.state, game.content, "yingru", -10)  # 30：汝南荒野歸官軍
    assert "louluo" not in game._here_squads("runan_wilds")
    with _fight():
        game.choose("explore:gather")
    assert game.state.battles[-1].opponent == "黃巾嘍囉" and w.bounties[-1].done_by == ["沈浪"]


def test_seeking_draws_an_explore_event():
    game = _game()
    game.content.config.rare_explore_chance = 0.0
    game.choose("explore:seek")
    explore_events = {e.id for e in game.content.events.values() if "explore" in e.actions}
    assert game.state.pending_event in explore_events


def test_sensing_starts_a_scene_where_the_place_gives_insight():
    game = _game()
    game.choose("explore:sense")
    assert game.state.player.sensing is not None


def test_a_treasure_raises_the_sensing_odds_instead_of_the_weight():
    game = _game()
    s, c = game.state, game.content
    loc = c.locations["yingshui"]
    insight = mock.patch.object(treasures, "amount", side_effect=lambda st, ct, key: 1.5 if key == "insight" else 1.0)
    with insight:
        assert sensing.rate(s, c, loc) == 85
        s.player.stats["wis"] = 15
        assert sensing.rate(s, c, loc) == 95  # 夾在 sense_rate_range 的上限
        s.player.stats["wis"] = 5
        c.config.explore_modes.enabled = False
        assert sensing.rate(s, c, loc) == 70


def test_every_way_rolls_the_pill_and_counts_the_scout():
    game = _game(encounter_chance=0.0)
    game.content.config.explore_legend_chance = 1.0
    game.content.config.rare_explore_chance = 0.0
    for mode in explore_modes.MODES:
        game.state.pending_event, game.state.player.sensing = None, None
        game.choose(explore_modes.option_id(mode))
    assert game.state.player.legend_items == 3
    game.state.pending_event, game.state.player.sensing = None, None
    game.state.world.bounties.append(Bounty(id="b2", kind="scout", faction="guan", week=1, expires=1e12, silver=20, deeds=1,
                                            location="yingshui", takers=["沈浪"]))
    game.choose("explore:seek")
    assert game.state.world.bounties[-1].done_by == ["沈浪"]


def test_gathering_rolls_its_own_dice():
    """找素材與破境丹的骰子不碰 Game.rng（choose 前後花了體力之後的偷聽片段照舊用它，那是每個花體力的動作都有的，不是這一批的事）。"""
    game = _game(encounter_chance=0.0)
    before = game.rng.getstate()
    game._gather(game.content.locations["yingshui"], explore_modes.rng_for(1, "沈浪", 1, "找素材"))
    game._legend_find(explore_modes.rng_for(1, "沈浪", 1, "破境丹"))
    assert game.rng.getstate() == before


def test_the_old_explore_with_the_switch_off():
    game = _game()
    classic_rules(game.content)
    opts = _ids(game)
    assert "act:explore" in opts and not any(i.startswith(explore_modes.PREFIX) for i in opts)
    stamina = game.state.player.stamina
    game.choose("act:explore")
    assert game.state.player.stamina == stamina - 6
