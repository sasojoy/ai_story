"""素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md）第六節：自家陣營的大本營捐軍備。
正式內容、週末設定（Config.economy 預設開）。長社是官軍的大本營、在潁川汝南戰線上（開季 40）；宛城是官軍的投靠點、不在戰線上（南陽）；
曹氏莊院是豪強的大本營。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import bot, economy
from tianxia.engine import Game
from tianxia.equipment import NOT_NOW
from tianxia.sqlite_world import open_world

TW_MIDNIGHT = 16 * 3600  # UTC 16:00＝台灣 00:00（1970-01-02）


def _game(faction="guan", at="changshe", bag=None, profile="weekend", **econ):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    for key, value in econ.items():
        setattr(c.config.economy, key, value)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(c.tutorial.steps)
    p.materials = dict(bag or {})
    game.now = TW_MIDNIGHT + 3600
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def test_only_your_own_base_takes_donations():
    assert "act:donate" in _ids(_game())
    assert "act:donate" in _ids(_game(at="wan_city"))  # 不在戰線上的投靠點也是大本營
    assert "act:donate" not in _ids(_game(at="huangjin_camp"))  # 別人的大本營
    assert "act:donate" not in _ids(_game(at="yingchuan"))  # 不是大本營
    assert "act:donate" not in _ids(_game(faction=None))  # 散人


def test_donating_from_the_menu_records_points_stores_and_pushes_the_front():
    game = _game(bag={"rou_1": 40, "rou_3": 1})
    p, w = game.state.player, game.state.world
    contrib = p.contrib
    game.choose("act:donate")
    ids = _ids(game)
    assert "donate:back" in ids and "donate:rou_1:40" in ids  # 一次收得下的全部（今天還有 100 點）
    assert "donate:rou_3:1" in ids
    msgs = game.choose("donate:rou_1:40")
    assert p.materials == {"rou_3": 1}
    assert w.armaments == {"guan": {"柔": 40}}
    assert p.contrib - contrib == 40  # 照份量記貢獻；推大勢不另記
    assert w.trends["yingru"] == 39  # 40 × 0.05 × 五折＝1：往官軍那頭
    assert "貢獻 +40" in msgs and "戰馬 +40" in msgs
    assert game.state.journal[0].title == f"{economy.DONATE_TITLE}・長社"


def test_the_daily_cap_takes_only_what_fits_and_keeps_the_rest():
    game = _game(bag={"rou_1": 50, "rou_3": 1})
    p = game.state.player
    p.donate_day, p.donated_today = game._pill_day(), 95
    game.choose("act:donate")
    ids = _ids(game)
    assert "donate:rou_1:5" in ids
    three = next(o for o in game.options() if o.id.startswith("donate:rou_3"))
    assert not three.enabled  # 一個三階 9 點，今天只剩 5 點
    msgs = game.donate("rou_1", 50)
    assert p.materials["rou_1"] == 45 and economy.DONATE_KEPT.format(n=45) in msgs
    assert game.donate("rou_1", 1) == [economy.DONATE_FULL.format(cap=100)]
    game.now = TW_MIDNIGHT + 24 * 3600  # 隔天台灣 00:00
    game.donate("rou_1", 10)
    assert p.materials["rou_1"] == 35


def test_the_gentry_push_their_hold():
    game = _game(faction="haoqiang", at="cao_manor", bag={"man_2": 20})
    w = game.state.world
    before = w.trends.get("geju", 0) + w.trend_accum.get("geju", 0)
    game.donate("man_2", 20)  # 60 點
    assert w.armaments == {"haoqiang": {"慢": 60}}
    assert w.trends.get("geju", 0) + w.trend_accum.get("geju", 0) > before


def test_a_season_without_the_season_one_rules_only_stores():
    game = _game(bag={"rou_1": 20}, profile=None)
    p = game.state.player
    contrib = p.contrib
    game.donate("rou_1", 20)
    assert game.state.world.armaments == {"guan": {"柔": 20}} and p.contrib == contrib


def test_rangers_and_other_bases_are_refused_and_nothing_moves():
    for game in (_game(faction=None, bag={"rou_1": 5}), _game(at="huangjin_camp", bag={"rou_1": 5})):
        assert game.donate("rou_1", 5) == [NOT_NOW]
        assert game.state.player.materials == {"rou_1": 5} and game.state.world.armaments == {}


def test_switched_off_nothing_changes():
    game = _game(bag={"rou_1": 5}, donate=False)
    assert "act:donate" not in _ids(game)
    assert game.donate("rou_1", 5) == [NOT_NOW]
    assert game.status_data()["armament"] is None


def test_the_jianghu_page_shows_the_factions_stores():
    game = _game(bag={"man_1": 3, "kuai_2": 1})
    game.donate("man_1", 3)
    game.donate("kuai_2", 1)
    stock = game.status_data()["armament"]
    assert stock["faction"] == "官軍"
    assert [(row["name"], row["points"]) for row in stock["stock"]] == [("糧秣", 3), ("箭矢", 3), ("甲冑", 0), ("戰馬", 0)]
    assert _game(faction=None).status_data()["armament"] is None


def test_leaving_closes_the_menu_and_bots_never_press_it():
    game = _game(bag={"rou_1": 5})
    game.choose("act:donate")
    game.choose("donate:back")
    assert not game.state.player.picking_donate and "act:donate" in _ids(game)
    options = [o for o in game.options() if o.id == "act:donate"]
    assert bot.pick(game, options, random.Random(0)) is None
