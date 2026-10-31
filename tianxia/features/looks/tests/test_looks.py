"""擂台形象（功能包 looks；Joy 2026-10-31）：萬寶閣買一套、換上、擂台記穿哪一套；買到的是帳號的、換季也帶著走；退了款換回斗笠小子；
假人不買，照名號挑（多數穿預設的）。測試內容的商城關著，這裡自己打開、自己放商品與形象。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season

from tianxia.characters import CharacterStore
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.features.looks import actions as looks_actions
from tianxia.features.looks import rules
from tianxia.models import Look, MallItem
from tianxia.wallet import Wallet

T0 = 20000 * 86400 + 3600


@pytest.fixture
def on(content):
    content.config.mall.enabled, content.config.mall.beta_grant = True, 5000
    content.looks = {
        "moying": Look(id="moying", name="墨影", bots=True),
        "jinshen": Look(id="jinshen", name="金身"),
    }
    content.mall = {i.id: i for i in (
        MallItem(id="look_moying", name="墨影形象", price=600, kind="look", look="moying", effects={"look": 1}),
        MallItem(id="look_jinshen", name="金身形象", price=600, kind="look", look="jinshen", effects={"look": 1}),
    )}
    content.config.admins = ["管理者"]
    return content


def _game(content, name="沈浪", world=None) -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.sync(T0)
    game.mark_seen(T0)  # 封測發放
    CharacterStore(game.world.db).save(game.state)  # 伺服器存過的樣子：管理者照名號找得到他
    return game


@pytest.mark.smoke
def test_buy_wear_and_the_arena_records_the_look(on):
    game = _game(on)
    assert game.arena_look() == ""
    game.mall_buy("look_moying", "ref-look-0001")
    assert Wallet(game.world.db).balance("沈浪") == 4400
    view = looks_actions.view(game)
    assert view["worn"] == "" and [(lk["id"], lk["owned"]) for lk in view["looks"]] == [("", True), ("moying", True), ("jinshen", False)]
    assert view["looks"][2]["item"] == "look_jinshen"
    msgs = looks_actions.wear(game, "moying")
    assert "墨影" in msgs[-1] and game.arena_look() == "moying"
    assert "形象" in [e.title for e in game.state.journal]


def test_cannot_wear_what_you_did_not_buy_and_cannot_buy_twice(on):
    game = _game(on)
    assert looks_actions.wear(game, "jinshen")[-1] == rules.NOT_OWNED
    game.mall_buy("look_jinshen", "ref-look-0002")
    assert game.mall_buy("look_jinshen", "ref-look-0003")[-1] == "你已經有「金身形象」這一套形象了。"
    assert Wallet(game.world.db).balance("沈浪") == 4400
    item = next(i for i in game.mall_view()["items"] if i["id"] == "look_jinshen")
    assert item["can"] is False and item["look"] == "jinshen"


def test_the_look_survives_a_new_season(on, world):
    game = _game(on, world=world)
    game.mall_buy("look_moying", "ref-look-0004")
    looks_actions.wear(game, "moying")
    next_season(on, world, game)
    assert game.arena_look() == "moying"


def test_a_refund_takes_the_look_back_to_the_default(on):
    game = _game(on)
    game.mall_buy("look_moying", "ref-look-0005")
    looks_actions.wear(game, "moying")
    pid = Wallet(game.world.db).purchases("沈浪")[0].id
    admin = Game.new(on, "管理者", rng=random.Random(1), world=game.world)
    admin.sync(T0)
    out = admin.admin_mall_refund("沈浪", pid, "測試退款")
    assert "形象「墨影」收回" in out[-1]
    assert game.arena_look() == ""


def test_bots_pick_by_name_and_mostly_wear_the_default(on):
    picks = [rules.bot_look(on, f"假{i}") for i in range(200)]
    assert set(picks) == {"", "moying"}  # 只挑 bots 開著的
    assert picks.count("") > picks.count("moying")
    assert rules.bot_look(on, "假7") == rules.bot_look(on, "假7")
    bot = Game.new(on, "假人甲", rng=random.Random(0))
    bot.state.player.bot = True
    assert bot.arena_look() == rules.bot_look(on, "假人甲")


def test_closed_means_default_and_no_view(content):
    game = Game.new(content, "沈浪", rng=random.Random(0))
    feature = next(f for f in FEATURES if f.name == "looks")
    assert feature.enabled(game) is False
    assert game.arena_look() == "" and looks_actions.view(game) is None


def test_every_look_in_the_real_content_has_all_nine_sheets():
    from pathlib import Path

    from tianxia.content import load_content

    root = Path(__file__).resolve().parents[4]
    content = load_content(root / "content")
    sheets = sorted(p.name for p in (root / "web/img/arena").glob("hero_*.webp"))
    assert len(sheets) == 9
    for look in content.looks:
        assert sorted(p.name for p in (root / "web/img/looks" / look).glob("hero_*.webp")) == sheets
    sold = {item.look for item in content.mall.values() if item.look}
    assert sold == set(content.looks)
