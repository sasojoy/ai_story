"""店面第二批：馬市與懸賞榜（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第三、四節；
計畫 docs/superpowers/plans/2026-10-13-店面-2-馬市與懸賞榜.md）。"""
from __future__ import annotations

import json
import random

import pytest

from conftest import real_content
from tianxia import bounties, equipment, mounts, shopview
from tianxia.content import validate
from tianxia.models import FactionDef
from tianxia.state import Bounty, Equipment

LINES = {shop: {key: [f"{shop}說{key}之一。", f"{shop}說{key}之二。"] for key in keys} for shop, keys in shopview.SITUATIONS.items()}
NOW = 1000.0
WEEK = 10_000_000.0  # 測試裡的懸賞一律掛到很久以後（同 tests/test_bounties.py）
SWORD = dict(id="兵:1", slot="weapon", name="試劍", kind="劍", attribute="剛", tier=1, quality="下品")
SCOUT = dict(kind="scout", faction="guan", silver=10, deeds=2, location="lake")
STRIKE = dict(kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug")
ARMS = dict(kind="arms", faction="guan", silver=0, deeds=2, attribute="剛", weapon_kind="劍", quota=3)


def _horse(hid="騎:1", name="青驄駒", tier=2, quality="中品", edge=100):
    return Equipment(id=hid, slot="mount", name=name, tier=tier, quality=quality, edge=edge)


def _market(content, world, silver=200, horse=None, name="試馬"):
    """坐騎開著、測試內容的小鎮臨時加上「馬市」標籤（同 tests/test_mounts.py::_market_game）、店面的字照 LINES；
    背包：精鐵砂 ×2（一階，餵得了）。走進馬市（act:market）。"""
    from tianxia.engine import Game

    content.config.mounts.enabled = True
    if mounts.MARKET_TAG not in content.locations["town"].tags:
        content.locations["town"].tags.append(mounts.MARKET_TAG)
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.mount = "town", 100.0, silver, horse
    p.materials = {"gang_1": 2}
    game.choose("act:market")
    return game


def _board(content, world, posts=(), name="試榜", faction=None):
    """劇本兩個陣營（官軍 join_at 小鎮、黃巾 join_at 湖邊，同 tests/test_bounties.py 的 setup）、兵器開著（求兵要）、店面的字照 LINES。
    posts 有東西時先把開季自動掛的單拿掉、照順序貼這幾張（同 test_bounties._post，掛到很久以後），直接貼在這一份 Game 的季上再存季；
    沒給就照季上原本的（另一個角色先貼好的）。走進懸賞榜（act:bounties）。"""
    from tianxia import rules
    from tianxia.engine import Game

    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["lake"])]
    content.config.weapons.enabled = True
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "fist")
    p = game.state.player
    p.faction, p.location, p.stamina, p.stats["silver"] = faction, "town", 100.0, 200
    game.sync(NOW)
    if posts:
        w = game.state.world
        w.bounties = []
        for kw in posts:
            w.bounty_seq += 1
            w.bounties.append(Bounty(id=f"b{w.bounty_seq}", week=1, expires=WEEK, **kw))
        game._save_season()
    game.choose("act:bounties")
    return game


def _ids(game):
    return [b.id for b in game.state.world.bounties]


# ── Task 1：馬販與榜吏的話、記情況鍵、收起店 ──


def test_the_market_and_board_lines_load_and_every_situation_is_required():
    c = real_content()
    for shop in ("market", "board"):
        for key in shopview.SITUATIONS[shop]:
            assert c.shop_lines[shop][key], (shop, key)
    validate(c)
    from tianxia.content import ContentError

    for shop, key in (("market", "feed"), ("board", "give")):
        c = real_content()
        del c.shop_lines[shop][key]
        with pytest.raises(ContentError, match=key):
            validate(c)
    c = real_content()
    c.shop_lines["market"]["haggle"] = ["馬販殺價。"]
    with pytest.raises(ContentError, match="不認得的情況"):
        validate(c)


def test_the_board_key_sorts_the_take_refusals():
    assert shopview.board_key(None, "take") == "take"
    assert shopview.board_key(bounties.HELD_FULL.format(count=3), "take") == "held_full"
    assert shopview.board_key(bounties.WANTED_NEWBIE, "take") == "refused"


def test_each_market_action_records_a_keeper_situation(content, world):
    game = _market(content, world, silver=300)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "market") in LINES["market"]["enter"]
    game.choose(mounts.BUY)  # 沒有馬：買下來直接騎上
    assert p.shop_line == "buy"
    game.choose(mounts.BUY)  # 第二匹進裝備庫
    assert p.shop_line == "buy"
    p.mount.edge = 40
    game.choose(mounts.FEED)
    assert p.shop_line == "feed"
    other = equipment.in_slot(p, "mount")[0].id
    game.choose(f"{mounts.WIELD}{other}")
    assert p.shop_line == "wield"
    p.stats["silver"] = 10
    game._market("buy")  # 灰掉的鈕在 choose 的選單那一關就擋下：直接叫，等於兩個分頁搶
    assert p.shop_line == "short_silver"
    game._market("feed")  # 換上的那一匹吃飽了
    assert p.shop_line == "refused"
    game.choose(mounts.BACK)
    assert (p.picking_market, p.shop_line, p.shop_clue) == (False, "", "")


def test_each_board_action_records_a_keeper_situation(content, world):
    game = _board(content, world, [SCOUT, dict(SCOUT, location="cave"), ARMS])
    scout, scout2, arms = _ids(game)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "board") in LINES["board"]["enter"]
    game.choose(f"bounty:take:{scout}")
    assert p.shop_line == "take"
    game.choose(f"bounty:drop:{scout}")
    assert p.shop_line == "drop"
    p.rack = [Equipment(**SWORD)]
    game.choose(f"bounty:pick:{arms}")
    assert p.shop_line == "pick"
    game.choose(f"bounty:give:{arms}:兵:1")
    assert p.shop_line == "give" and p.bounty_pick is None
    game._bounty("take:b999")  # 下榜了
    assert p.shop_line == "refused"
    content.config.bounties.max_taken = 1
    game.choose(f"bounty:take:{scout}")
    game._bounty(f"take:{scout2}")  # 手上揭滿了（選單上灰掉的鈕，直接叫）
    assert p.shop_line == "held_full"
    game._bounty("drop:b999")
    assert p.shop_line == "refused"
    game.choose("bounty:back")
    assert (p.picking_bounty, p.bounty_pick, p.shop_line) == (False, None, "")


def test_walking_off_or_reloading_clears_the_shop_line(content, world):
    from tianxia.engine import Game

    game = _market(content, world)
    p = game.state.player
    p.location = "lake"  # 湖邊沒有馬市：同步時收起
    game.sync(10.0)
    assert (p.picking_market, p.shop_line) == (False, "")
    game = _board(content, world, [SCOUT], name="讀檔")
    game.state.player.location = "lake"  # 湖邊不是城鎮：讀檔修補時收起懸賞榜
    again = Game(content, game.state, random.Random(0), world)
    assert (again.state.player.picking_bounty, again.state.player.shop_line) == (False, "")
