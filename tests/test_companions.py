"""歷史武將同行（docs/superpowers/specs/2026-10-18-歷史武將同行-design.md）：十五位不是大勢人物的歷史武將照陣營招進名下、
全服唯一、一人三位、情誼放慢、放走、叛投帶不走。決戰裡的同伴在 tests/test_companions_battle.py。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import roster
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import MAX_TEAM_COMPANIONS

FIFTEEN = {
    "caocao", "liubei", "guanyu", "zhangfei", "yuanshao", "taoqian", "wangyun", "gongsunzan",
    "xuchu", "tangzhou", "zhangyan", "xushao", "xunyu", "huatuo", "zhangrang",
}


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _player(content, store, name, faction, at) -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    p.joined_at = -1e9
    p.stamina = 250
    p.stats["silver"] = 100
    game.now = 1000.0
    game._save_season()
    CharacterStore(store.db).save(game.state)
    return game


def _opts(game):
    return {o.id: o for o in game.options()}


# ── Task 1：開關、可招的人、照陣營招、名下三位 ──


def test_fifteen_are_recruitable_and_no_figure_is():
    c = real_content()
    assert c.config.companions.enabled
    recruitable = {cid for cid, ch in c.characters.items() if ch.recruitable}
    assert recruitable == FIFTEEN
    assert not recruitable & {f.character for f in c.figures.values() if f.character}
    assert c.characters["zhangyan"].side == "huang"  # 9.2：黑山軍出自黃巾


def test_the_recruit_button_follows_the_side(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    button = _opts(guan)["act:recruit:liubei"]
    assert button.enabled and "成功率約" in button.label
    huang = _player(real, world, "黃甲", "huang", "zhuo_county")
    button = _opts(huang)["act:recruit:liubei"]
    assert not button.enabled and roster.SIDE_ONLY.format(side="官軍") in button.label
    drifter = _player(real, world, "散甲", None, "yingchuan_academy")
    assert _opts(drifter)["act:recruit:xunyu"].enabled  # 沒寫 side 的誰都招得到（含散人）


def test_a_recruit_lands_him_in_your_name_and_team(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    guan.rng = mock.Mock(random=mock.Mock(return_value=0.0))
    guan.choose("act:recruit:guanyu")
    assert world.get_companion("guanyu").owner == "官甲"
    assert "guanyu" in guan.state.player.team
    assert "act:recruit:guanyu" not in _opts(guan)  # 有主了：鈕不再出現


def test_a_fourth_companion_is_refused(real, world):
    guan = _player(real, world, "Ray", "guan", "zhuo_county")
    for cid in ("caocao", "yuanshao", "taoqian"):
        assert world.try_recruit(cid, "Ray", cap=3)
    button = _opts(guan)["act:recruit:liubei"]
    assert not button.enabled and roster.FULL.format(n=3) in button.label
    assert not world.try_recruit("liubei", "Ray", cap=3)
    assert not world.try_recruit("liubei", "RAY", cap=3)  # 名號比對不分大小寫
    assert world.get_companion("liubei").owner is None


def test_switch_off_changes_nothing(content):
    assert not content.config.companions.enabled
    assert roster.cap(content) == MAX_TEAM_COMPANIONS
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.state.player.tutorial_step = len(content.tutorial.steps)
    ids = {o.id for o in game.options()}
    assert not any(i.startswith("act:recruit:") for i in ids)


# ── Task 2：情誼放慢 ──


def test_affinity_gains_are_scaled_and_rounded():
    from tianxia import renown

    c = real_content()
    assert c.config.affinity_gain_scale == 0.7 and real_content("weekend").config.affinity_gain_scale == 0.85
    assert [renown.warmed(c, d) for d in (1, 2, 5, 8, -5, 0)] == [1, 1, 4, 6, -5, 0]  # 9.4：四捨五入、至少 1、扣的不乘
    c.config.affinity_gain_scale = 1.0
    assert renown.warmed(c, 7) == 7


def test_each_gain_source_goes_through_warmed(real, world):
    from tianxia import atlas, companion_agent, figure_life, renown, rules
    from tianxia.companion_agent import CompanionTurn
    from tianxia.models import Effect

    game = _player(real, world, "官甲", "guan", "zhuo_county")
    s, p = game.state, game.state.player
    rules.apply_effect(Effect(affinity={"liubei": 5}), s, real, world)  # 事件
    assert p.affinities["liubei"] == 4
    companion_agent._apply_turn(s, real.characters["guanyu"], "guanyu", "請教", CompanionTurn(narrative="嗯。"), "坦誠相待", real)  # 對話
    assert p.affinities["guanyu"] == 7  # 關羽的坦誠相待 +10（affinity_tag_deltas）× 0.7
    p.stats["fame"] = 100_000
    renown.first_meet(s, real, "zhangfei")  # 名望起步
    assert p.affinities["zhangfei"] == renown.warmed(real, real.config.renown.fame_affinity)
    region = atlas.region_of(real, "zhuo_county").id
    figure_life.spread(s, real, "merit", "長社", at=None, side="guan", text="立了戰功", region=region)  # 風聞
    assert p.affinities["gongsunzan"] == renown.warmed(real, real.config.figure_life.side_merit)


# ── Task 3：放走與名冊 ──


def test_release_frees_him_for_anyone(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官甲", cap=3)
    guan.state.player.team.append("guanyu")
    msgs = guan.release_companion("guanyu")
    assert world.get_companion("guanyu").owner is None and "guanyu" not in guan.state.player.team
    assert msgs == [roster.RELEASE_DONE.format(name="關羽")]
    other = _player(real, world, "官乙", "guan", "zhuo_county")
    assert _opts(other)["act:recruit:guanyu"].enabled


def test_release_refuses_someone_not_yours(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官乙", cap=3)
    assert guan.release_companion("guanyu") == [roster.RELEASE_NOT_YOURS]
    assert world.get_companion("guanyu").owner == "官乙"


def test_unowned_team_members_are_dropped_on_load(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("liubei", "官甲", cap=3)
    guan.state.player.team = ["liubei", "guanyu"]  # 關羽不在他名下（例：打完決戰回江湖了）
    CharacterStore(world.db).save(guan.state)
    again = Game(real, CharacterStore(world.db).load("官甲"), random.Random(0), world)
    assert again.state.player.team == ["liubei"]


def test_the_roster_card_offers_release_through_the_server(real, world):
    import server

    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官甲", cap=3)
    view = server.menxia_view(guan, "guanyu")
    assert view["release"] == {"confirm": roster.RELEASE_CONFIRM.format(name="關羽")}
    assert server.menxia_view(guan, "player")["release"] is None
    server.MENXIA_ACTIONS["release"](guan, {"person": "guanyu"})
    assert world.get_companion("guanyu").owner is None


# ── Task 7：叛投帶不走 ──


def test_defecting_drops_companions_of_the_old_side(real, world):
    """9.5：官軍叛投黃巾，劉備（寫了官軍）當場回江湖、情誼減半，確認畫面列出他；荀彧（沒寫陣營）照舊跟著。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    p = game.state.player
    for cid in ("liubei", "xunyu"):
        assert world.try_recruit(cid, "官甲", cap=3)
        p.team.append(cid)
    p.affinities["liubei"] = 61
    target = next(f for f in real.scenario.factions if f.id == "huang")
    assert p.location in target.join_at
    prompt = game.choose(f"defect:{target.id}")
    assert roster.DEFECT_LOST.format(names="劉備") in "".join(prompt)
    msgs = game.choose("defect:confirm")
    assert roster.DEFECT_LEFT.format(name="劉備", before=61, after=30) in msgs
    assert world.get_companion("liubei").owner is None and "liubei" not in p.team and p.affinities["liubei"] == 30
    assert world.get_companion("xunyu").owner == "官甲" and "xunyu" in p.team
