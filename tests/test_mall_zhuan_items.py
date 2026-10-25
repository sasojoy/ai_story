"""減法季批 7b-3：只對準列傳的四件商品（整合設計第九章的表；企劃者 2026-10-24 定價：列傳插畫 300、紀念印 150、人物親筆評曰 200、
深交名額 250 元寶）。上架照 MallWindow 的 rule（子開關 zhuan_end）、from_week、phases；購買那一列就是票（不改資料庫結構，第 7 版），
休季用掉（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物>）；退得掉；關著的季貨架一件不多、休季的選單一顆不多。"""
from __future__ import annotations

import random

import pytest

import zhuan_html
from jianfa_kit import jianfa_game, ready
from tianxia import calendar, database, mall, zhuan_end
from tianxia.characters import CharacterStore, name_key
from tianxia.engine import Game
from tianxia.models import MallItem, MallWindow
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow

ADMIN = "史館管理者"
FOUR = {"zhuan_art", "zhuan_seal", "zhuan_quote", "deep_slot"}


def _game(**flags) -> Game:
    game = jianfa_game(**flags)
    game.content.config.admins = [ADMIN]
    ready(game, side="guan", loc="changshe")
    game.sync(game.now)
    Wallet(game.world.db).post(name_key(game.state.player.name), 5000, "grant", "test:zhuan", time=game.now)
    CharacterStore(game.world.db).save(game.state)
    return game


def _shelf(game: Game) -> set[str]:
    return {item["id"] for item in game.mall_view()["items"]}


def _to_week(game: Game, week: int) -> None:
    w = game.state.world
    w.time = calendar.week_start(week, game.content, w) + 60
    game._save_season()


def _close(game: Game) -> Game:
    admin = Game.new(game.content, ADMIN, rng=random.Random(1), world=game.world)
    admin.client = None
    admin.admin_end_season(game.now + 10)
    CharacterStore(game.world.db).save(game.state)
    game.sync(game.now + 20)
    return game


def test_the_four_items_follow_their_windows():
    game = _game()
    first = _shelf(game)
    assert "deep_slot" in first and not first & {"zhuan_art", "zhuan_seal", "zhuan_quote"}  # 第 1 週：只有深交名額
    _to_week(game, 3)
    assert {"deep_slot", "zhuan_art"} <= _shelf(game) and not _shelf(game) & {"zhuan_seal", "zhuan_quote"}  # 插畫第 3 週起
    _close(game)
    rest = _shelf(game)
    assert {"zhuan_art", "zhuan_seal", "zhuan_quote"} <= rest and "deep_slot" not in rest  # 休季：插畫、紀念印、親筆評曰
    prices = {item["id"]: item["price"] for item in game.mall_view()["items"]}
    assert (prices["zhuan_art"], prices["zhuan_seal"], prices["zhuan_quote"]) == (300, 150, 200)
    assert game.content.mall["deep_slot"].price == 250


def test_off_the_shelf_has_none_of_them_and_the_rest_menu_is_one_grey_button():
    game = _game(zhuan_end=False)
    assert not _shelf(game) & FOUR
    _to_week(game, 3)
    assert not _shelf(game) & FOUR
    _close(game)
    assert not _shelf(game) & FOUR
    assert [(o.id, o.enabled) for o in game.options()] == [("season:resting", False)]
    assert game.mall_buy("zhuan_seal", "off-1") == [mall.NO_ITEM]


def test_limits_per_season():
    game = _game()
    _to_week(game, 3)
    assert game.mall_buy("zhuan_art", "a1")[0].startswith("買下")
    assert "這一季" in game.mall_buy("zhuan_art", "a2")[0]
    _close(game)
    assert game.mall_buy("zhuan_quote", "q1")[0].startswith("買下") and game.mall_buy("zhuan_quote", "q2")[0].startswith("買下")
    assert "這一季" in game.mall_buy("zhuan_quote", "q3")[0]
    assert game.mall_buy("zhuan_seal", "s1")[0].startswith("買下")
    assert "這一季" in game.mall_buy("zhuan_seal", "s2")[0]
    assert game.mall_buy("deep_slot", "d1") == [mall.NO_ITEM]  # 深交名額只在季中賣


def test_rest_buttons_use_the_tickets_and_the_biography_shows_them():
    game = _game()
    _to_week(game, 3)
    game.mall_buy("zhuan_art", "art")
    p = game.state.player
    p.affinities.update({"luzhi": 55, "zhujun": 75, "caocao": 30})
    CharacterStore(game.world.db).save(game.state)
    _close(game)
    game.mall_buy("zhuan_seal", "seal")
    game.mall_buy("zhuan_quote", "quote")
    ids = {o.id: o for o in game.options()}
    assert ids["season:resting"].enabled is False
    assert {zhuan_end.PICK_ART, zhuan_end.SEAL, "zhuan:quote:luzhi"} <= set(ids)
    assert "zhuan:quote:zhujun" not in ids and "zhuan:quote:caocao" not in ids  # 70 以上白送、40 以下挑不到
    entry = game.biography_entry()
    assert entry is not None and entry["illustration"] is None and entry["seal"] is None
    assert entry["tier"] is None  # 散不散人都看論功：這一局只有一個人、貢獻 0
    out = game.choose(zhuan_end.PICK_ART)
    assert out[0] == zhuan_end.ART_DONE and game.state.journal[0].title == zhuan_end.TITLE
    assert zhuan_end.PICK_ART not in {o.id for o in game.options()}  # 用過了：這一季不再出現
    assert game.biography_entry()["illustration"] == "guan_" + ("win" if game.ending_card()["winner"] == "guan" else "lose")
    sealed = game.choose(zhuan_end.SEAL)[0]
    assert sealed.startswith("列傳末尾蓋上一方朱印：黃巾之亂・第 1 季")
    assert game.biography_entry()["seal"].startswith("黃巾之亂・第 1 季")
    assert game.choose("zhuan:quote:luzhi")[0] == "你請盧植替你的列傳寫一句評曰。"
    assert "zhuan:quote:luzhi" not in {o.id for o in game.options()}
    wallet, owner = Wallet(game.world.db), name_key(p.name)
    used = [b for b in wallet.purchases(owner) if b.data.get("used")]
    assert sorted((b.item, b.data.get("season"), b.data.get("fid")) for b in used) == [
        ("zhuan_art", 1, None), ("zhuan_quote", 1, "luzhi"), ("zhuan_seal", 1, None)]
    assert game.choose(zhuan_end.SEAL) == ["（此刻無法這麼做。）"]  # 沒有票了


def test_one_use_per_season_even_with_a_spare_ticket():
    """手上還有上一季沒用的票（這裡直接塞一列購買）：這一季用過一張插畫、一方紀念印，就不再出那兩顆鈕（票留到下一季）。"""
    game = _game()
    _to_week(game, 3)
    game.mall_buy("zhuan_art", "art")
    _close(game)
    game.mall_buy("zhuan_seal", "seal")
    game.choose(zhuan_end.PICK_ART)
    game.choose(zhuan_end.SEAL)
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    for item, effect in (("zhuan_art", "zhuan_art"), ("zhuan_seal", "zhuan_seal")):
        wallet.add_purchase(owner, f"spare-{item}", item, 1, time=game.now, day=0, season=1, data={effect: 1})
    ids = {o.id for o in game.options()}
    assert zhuan_end.PICK_ART not in ids and zhuan_end.SEAL not in ids
    assert len(mall.tokens(wallet, owner, "zhuan_art")) == 1 and len(mall.tokens(wallet, owner, "zhuan_seal")) == 1


def test_the_first_tier_gets_the_art_free_and_no_button():
    game = _game()
    game.state.player.contrib = 120  # 這一局官軍只有他：過了門檻就是第一階
    CharacterStore(game.world.db).save(game.state)
    _to_week(game, 3)
    game.mall_buy("zhuan_art", "art")
    _close(game)
    entry = game.biography_entry()
    assert entry["tier"]["tier"] == 1 and entry["illustration"] and entry["illustration"].startswith("guan_")
    assert zhuan_end.PICK_ART not in {o.id for o in game.options()}  # 白送了：票留著


def test_refund_voids_the_ticket_and_takes_the_art_off():
    game = _game()
    _to_week(game, 3)
    game.mall_buy("zhuan_art", "art")
    _close(game)
    game.choose(zhuan_end.PICK_ART)
    assert game.biography_entry()["illustration"]
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    pid = next(b.id for b in wallet.purchases(owner) if b.item == "zhuan_art")
    admin = Game.new(game.content, ADMIN, rng=random.Random(2), world=game.world)
    admin.client = None
    msg = admin.admin_mall_refund(game.state.player.name, pid, "測試退款")[0]
    assert "列傳插畫作廢" in msg
    game.sync(game.now + 30)
    assert game.biography_entry()["illustration"] is None


def test_the_public_page_prints_the_seal_and_the_art_only_when_given():
    row = {"name": "沈浪", "season": 1, "text": "沈浪者，不知何許人也。\n\n評曰：善。"}
    plain = zhuan_html.page(row, "黃巾之亂", "https://x/zhuan/a", "https://x/og.png")
    assert plain == zhuan_html.page(row, "黃巾之亂", "https://x/zhuan/a", "https://x/og.png", extras={})
    assert "zh-art" not in plain and "zh-mark" not in plain
    full = zhuan_html.page(row, "黃巾之亂", "https://x/zhuan/a", "https://x/og.png",
                           extras={"seal": "黃巾之亂・第 1 季・官軍第 3 名", "art": "/static/img/zhuan/guan_win.webp"})
    assert 'class="zh-art"' in full and "/static/img/zhuan/guan_win.webp" in full
    assert "黃巾之亂・第 1 季・官軍第 3 名" in full and 'class="zh-mark"' in full


def test_the_schema_does_not_move_and_bad_windows_are_caught():
    assert database.SCHEMA_VERSION == 7
    game = jianfa_game()
    c = game.content
    bad = MallItem(id="x", name="測試貨", price=10, kind="consumable", effects={"zhuan_seal": 1},
                   on_sale=MallWindow(rule="no_such_switch", from_week=2))
    assert any("no_such_switch" in line for line in mall.item_problems(bad, c))
    assert set(mall.EFFECTS) >= FOUR
    assert all(c.mall[i].on_sale.rule == "zhuan_end" for i in FOUR)
