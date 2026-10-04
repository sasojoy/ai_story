"""第一季濃縮版 T5：頭銜、召見、第 2 階晉升奇遇、部下（計畫 2026-10-05-T5-晉升）。

用真實內容（content/）：要驗的就是真實的晉升定義、奇遇、部下與大勢人物。每個測試自己載一份，開關在測試裡才打開。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import ranks, team
from tianxia.content import load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Config, Effect
from tianxia.state import PlayerState, Summons, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def _win():
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_new_fields_have_defaults_so_old_saves_load():
    assert Config().rank2_contrib == 300
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.rank, p.summons, p.followers) == (0, None, [])
    assert WorldState().promoted_today == {}
    assert (Effect().promote, Effect().followers, Effect().affinity) == (None, [], {})


def test_real_promotions_valid(real):
    by_side = {p.faction: p for p in real.promotions}
    assert set(by_side) == {"guan", "huang", "haoqiang"} and all(p.rank == 2 for p in real.promotions)
    guan, huang, gentry = by_side["guan"], by_side["huang"], by_side["haoqiang"]
    assert (guan.figure, guan.successor, guan.location) == ("huangfusong", "zhujun", "changshe")
    assert (huang.figure, huang.successor, huang.location) == ("bocai", "pengtuo", "huangjin_camp")
    assert (gentry.figure, gentry.successor, gentry.location, gentry.event_handoff) == (None, None, "nearest_base", None)
    assert guan.summons_text == "皇甫嵩召你到長社營中。" and guan.summons_handoff == "朱儁召你到長社營中。"
    assert gentry.summons_text == "中山的馬商張世平、蘇雙到了{據點}，指名要見你。"
    for p in real.promotions:
        for event_id in filter(None, (p.event_main, p.event_handoff)):
            event = real.events[event_id]
            assert event.actions == [] and len(event.choices) == 3
            assert all(ch.effect.promote == 2 and len(ch.effect.followers) == 2 for ch in event.choices)
    first = real.events["promo_guan_2"].choices[1]
    assert first.effect.affinity == {"huangfusong": 10} and first.effect.text == "皇甫嵩微微一笑。"
    assert real.events["promo_haoqiang_2"].choices[1].effect.materials == {"kuai_1": 2}


def test_real_followers_valid(real):
    assert set(real.followers) == {
        "follower_guan_spear", "follower_guan_crossbow", "follower_huang_believer",
        "follower_huang_strongman", "follower_haoqiang_retainer", "follower_haoqiang_buqu",
    }
    spear = real.followers["follower_guan_spear"]
    assert (spear.name, spear.faction, spear.wugong, spear.wugong_level) == ("持矛鄉勇", "guan", "xingwu_qiang", 3)
    assert all(f.wugong in real.skills for f in real.followers.values())
    assert real.skills["qiangnu"].name == "強弩射法"


# ── Task 2：頭銜 ─────────────────────────────────


def test_join_shows_rank_one_title(on):
    """投靠之後狀態列寫「陣營・頭銜」（第一季設計 5.2，第 1 階）；有門派時「門派・陣營・頭銜」；散人照舊；第 2 階換頭銜。"""
    assert ranks.TITLES == {
        "guan": ["", "鄉勇", "屯長", "軍司馬", "校尉"],
        "huang": ["", "信眾", "小帥", "小方渠帥", "大方渠帥"],
        "haoqiang": ["", "鄉里子弟", "宗族頭人", "地方豪強", "一方之主"],
    }
    game = _game(on, at="changshe")
    assert (ranks.rank_of(game.state), ranks.title(on, game.state), game.status_data()["affiliation"]) == (0, None, "散人")
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert (ranks.rank_of(game.state), game.status_data()["affiliation"]) == (1, "官軍・鄉勇")
    for name, faction, shown in (("乙", "huang", "黃巾軍・信眾"), ("丙", "haoqiang", "地方豪強・鄉里子弟")):
        assert _game(on, name=name, faction=faction).status_data()["affiliation"] == shown
    game.state.player.sect = "yingchuan_academy"
    assert game.status_data()["affiliation"] == "潁川書院・官軍・鄉勇"
    game.state.player.rank = 2
    assert game.status_data()["affiliation"] == "潁川書院・官軍・屯長"
    assert "潁川書院・官軍・屯長" in game.status_text().splitlines()[0]


def test_switch_off_affiliation_unchanged(real):
    """開關關著（beta 那一季）：沒有頭銜，狀態列照舊「陣營」「門派・陣營」。"""
    game = _game(real, faction="guan")
    assert ranks.title(real, game.state) is None and game.status_data()["affiliation"] == "官軍"
    game.state.player.sect = "yingchuan_academy"
    game.state.player.rank = 2  # 就算存檔裡有階，beta 也不顯示
    assert game.status_data()["affiliation"] == "潁川書院・官軍"


def test_new_season_resets_rank_summons_and_followers(on):
    """RF5：換季是新角色——頭銜、召見、部下都重來（散人、第 0 階、沒有召見、沒有部下）；做完的引導照 T6 的規則不重來。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    player = _game(on, "甲", faction="guan")
    p = player.state.player
    p.rank, p.followers = 2, ["follower_guan_spear", "follower_guan_crossbow"]
    p.summons = Summons(rank=3, figure="huangfusong", location="changshe")
    done = p.tutorial_step = len(on.tutorial.steps)
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    p = player.state.player
    assert (p.faction, p.rank, p.summons, p.followers, p.tutorial_step) == (None, 0, None, [], done)
    assert player.status_data()["affiliation"] == "散人"
