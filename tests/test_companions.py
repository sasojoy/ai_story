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
