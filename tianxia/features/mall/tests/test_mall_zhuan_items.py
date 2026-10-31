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
from conftest import next_season
from zhuan_fix_kit import close_season, make_game, option_ids, row, to_week
from tianxia import zhuan_end
from tianxia.wallet import Purchase, Wallet
from zhuan_fix_kit import add_story, close_season, figures, make_game, verdict_paras
from tianxia.wallet import Purchase
from zhuan_fix_kit import add_story, admin_of, close_season, figures, make_game, verdict_paras
from jianfa_kit import jianfa_game
from tianxia.characters import name_key
from zhuan_fix_kit import add_story, close_season, make_game, verdict_paras
from zhuan_fix_kit import close_season, make_game, row, to_week
from tianxia import calendar, mall

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


def test_the_items_follow_their_windows():
    game = _game()
    first = _shelf(game)
    assert not first & FOUR  # 第 1 週：一件都沒有（深交名額企劃者 2026-10-28 下架了）
    _to_week(game, 3)
    assert "zhuan_art" in _shelf(game) and not _shelf(game) & {"zhuan_seal", "zhuan_quote", "deep_slot"}  # 插畫第 3 週起
    _close(game)
    rest = _shelf(game)
    assert {"zhuan_art", "zhuan_seal", "zhuan_quote"} <= rest and "deep_slot" not in rest  # 休季：插畫、紀念印、親筆評曰
    prices = {item["id"]: item["price"] for item in game.mall_view()["items"]}
    assert (prices["zhuan_art"], prices["zhuan_seal"], prices["zhuan_quote"]) == (300, 150, 200)
    assert "deep_slot" not in game.content.mall


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
    assert game.mall_buy("deep_slot", "d1") == [mall.NO_ITEM]  # 深交名額下架了（企劃者 2026-10-28）


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


def test_the_server_gives_the_art_url_only_when_the_file_is_there(monkeypatch, tmp_path):
    """伺服器（server.zhuan_art_src）：江湖頁的 main.zhuan、讀傳那一層（/api/zhuan 的 zhuan_view）、公開頁（zhuan_extras）都是
    web/img/zhuan/<鍵>.webp 真的在才給網址；雲端批 8 還沒放圖時是 None，公開頁不多插畫那一段。紀念印照票。"""
    import server

    game = _game()
    _to_week(game, 3)
    game.mall_buy("zhuan_art", "art")
    _close(game)
    game.mall_buy("zhuan_seal", "seal")
    game.choose(zhuan_end.PICK_ART)
    game.choose(zhuan_end.SEAL)
    key = game.biography_entry()["illustration"]
    monkeypatch.setattr(server, "CONTENT", game.content)
    monkeypatch.setattr(server, "WEB", tmp_path)
    assert server.main_view(game)["zhuan"]["illustration_src"] is None  # 圖還沒放
    assert server.zhuan_view(game, 1, None)["illustration_src"] is None
    (tmp_path / "img" / "zhuan").mkdir(parents=True)
    (tmp_path / "img" / "zhuan" / f"{key}.webp").write_bytes(b"RIFF")
    src = f"/static/img/zhuan/{key}.webp"
    assert server.main_view(game)["zhuan"]["illustration_src"] == src
    assert server.zhuan_view(game, 1, None)["illustration_src"] == src
    req = game.biography_request(1)
    assert game.write_biography(req, None, game.now + 40)
    code = game.share_biography(1, True, "artcode")
    row = game.world.biography_by_code(code)
    extras = server.zhuan_extras(game.world, row)
    assert extras["art"] == src and extras["seal"].startswith("黃巾之亂・第 1 季")


def test_off_the_server_adds_no_art_keys(monkeypatch, tmp_path):
    """關著的季：main.zhuan 與 zhuan_view 一個鍵都不多（沒有 illustration 就不寫 illustration_src），公開頁的 extras 是空的。"""
    import server
    from tianxia import annals

    game = _game(zhuan_end=False)
    game.state.player.contrib = 120  # 開著的話是第一階、插畫白送
    annals.note(game.state, game.content, annals.DEED, "在長社城下守了一夜。", 3)
    CharacterStore(game.world.db).save(game.state)
    _close(game)
    monkeypatch.setattr(server, "CONTENT", game.content)
    monkeypatch.setattr(server, "WEB", tmp_path)
    entry = server.main_view(game)["zhuan"]
    assert set(entry) == {"season", "title"}
    game.write_biography(game.biography_request(1), None, game.now + 40)
    assert not {"illustration", "illustration_src", "seal", "tier", "verdicts"} & set(server.zhuan_view(game, 1, None))
    code = game.share_biography(1, True, "offcode")
    assert server.zhuan_extras(game.world, game.world.biography_by_code(code)) == {}


def test_the_schema_does_not_move_and_bad_windows_are_caught():
    assert database.SCHEMA_VERSION == 7
    game = jianfa_game()
    c = game.content
    bad = MallItem(id="x", name="測試貨", price=10, kind="consumable", effects={"zhuan_seal": 1},
                   on_sale=MallWindow(rule="no_such_switch", from_week=2))
    assert any("no_such_switch" in line for line in mall.item_problems(bad, c))
    assert set(mall.EFFECTS) >= FOUR
    assert all(c.mall[i].on_sale.rule == "zhuan_end" for i in FOUR - {"deep_slot"})  # 深交名額只留在 EFFECTS（舊的購買讀得出來），架上沒有


# ── 原 test_fb845_art_ticket.py（整檔搬進來） ──
# FB-845：這一季用不到的列傳插畫票不賣，票綁買的那一季。
# - 沒投靠一方的人（散人）：列傳配不了插畫，商城那一列灰掉寫原因、買也買不了；休季時已經得第一階的人：插畫白送，同樣灰掉寫原因
#   （季中看不出會是第幾階，照舊賣）。已經買了一張的人說的是限購。
# - 列傳的三種票（插畫、紀念印、親筆評曰）綁買的那一季：之後的季不再冒出用票的鈕，用票用的是這一季買的那一張。

def test_a_wanderer_cannot_buy_the_art_ticket_in_season_or_in_the_rest():
    game = make_game(side=None)
    to_week(game, 3)
    art = row(game, "zhuan_art")
    assert art is not None and art["can"] is False and art["why"] == zhuan_end.ART_NO_SIDE and art["max"] == 0
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    before = wallet.balance(owner)
    assert game.mall_buy("zhuan_art", "w1") == [zhuan_end.ART_NO_SIDE]
    assert wallet.balance(owner) == before and not [b for b in wallet.purchases(owner) if b.item == "zhuan_art"]
    close_season(game)
    assert row(game, "zhuan_art")["why"] == zhuan_end.ART_NO_SIDE
    assert game.mall_buy("zhuan_art", "w2") == [zhuan_end.ART_NO_SIDE]
    assert row(game, "zhuan_seal")["can"] is True  # 紀念印、親筆評曰散人也用得上，照舊賣


def test_a_wanderer_who_joins_a_side_can_buy_it():
    game = make_game(side=None)
    to_week(game, 3)
    assert row(game, "zhuan_art")["can"] is False
    game.state.player.faction = "guan"
    assert row(game, "zhuan_art")["can"] is True and row(game, "zhuan_art")["why"] is None
    assert game.mall_buy("zhuan_art", "j1")[0].startswith("買下")


def test_the_first_tier_cannot_buy_the_art_ticket_once_the_season_is_over():
    game = make_game()
    game.state.player.contrib = 120  # 這一局官軍只有他：過了門檻就是第一階
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert row(game, "zhuan_art")["can"] is True  # 季中看不出會是第幾階：照舊賣
    close_season(game)
    assert game.biography_entry()["tier"]["tier"] == 1
    art = row(game, "zhuan_art")
    assert art["can"] is False and art["why"] == zhuan_end.ART_FREE and art["max"] == 0
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    assert game.mall_buy("zhuan_art", "t1") == [zhuan_end.ART_FREE]
    assert not [b for b in wallet.purchases(owner) if b.item == "zhuan_art"]


def test_a_lower_tier_keeps_buying_the_art_ticket_in_the_rest():
    game = make_game()
    to_week(game, 3)
    close_season(game)
    assert game.biography_entry()["tier"] is None
    assert row(game, "zhuan_art")["can"] is True
    assert game.mall_buy("zhuan_art", "l1")[0].startswith("買下")
    assert zhuan_end.PICK_ART in option_ids(game)


def test_the_limit_is_told_before_the_unfit_reason():
    """季中買了一張、休季才知道是第一階：再按說的是限購，不是「第一階白送」。"""
    game = make_game()
    game.state.player.contrib = 120
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert game.mall_buy("zhuan_art", "b1")[0].startswith("買下")
    close_season(game)
    assert "這一季已經買了" in row(game, "zhuan_art")["why"]


def test_the_other_shelf_rows_are_not_blocked():
    game = make_game(side=None)
    to_week(game, 3)
    others = [r for r in game.mall_view()["items"] if r["id"] != "zhuan_art"]
    assert others and all(r["can"] and r["why"] is None for r in others)


def test_a_ticket_belongs_to_the_season_it_was_bought_in():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert game.mall_buy("zhuan_art", "a1")[0].startswith("買下")
    close_season(game)
    for item, ref in (("zhuan_seal", "s1"), ("zhuan_quote", "q1")):
        assert game.mall_buy(item, ref)[0].startswith("買下")
    assert {zhuan_end.PICK_ART, zhuan_end.SEAL, "zhuan:quote:luzhi"} <= option_ids(game)  # 這一季的票這一季用得上
    next_season(game.content, game.world, game)  # 第 2 季開了：第 1 季沒用掉的三張不再算
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    close_season(game)
    assert game.state.player.season_number == 2 and game.state.world.ended
    assert not {zhuan_end.PICK_ART, zhuan_end.SEAL, "zhuan:quote:luzhi"} & option_ids(game)
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    assert game.mall_buy("zhuan_seal", "s2")[0].startswith("買下")  # 第 2 季的限購另算
    assert zhuan_end.SEAL in option_ids(game)
    game.choose(zhuan_end.SEAL)
    used = [(b.item, b.season, b.data.get("season")) for b in wallet.purchases(owner) if b.data.get("used")]
    assert used == [("zhuan_seal", 2, 2)]  # 用掉的是第 2 季買的那一張，第 1 季的還躺著（沒作廢也用不到）
    assert sum(1 for b in wallet.purchases(owner) if b.item == "zhuan_seal" and not b.data.get("used")) == 1


def test_the_button_spends_the_ticket_of_this_season_not_an_older_one():
    """手上同時有舊季的票和這一季的票：用掉的是這一季買的那一張（舊的留著）。"""
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    close_season(game)
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    wallet.add_purchase(owner, "old-art", "zhuan_art", 300, time=game.now, day=0, season=0, data={"zhuan_art": 1})
    game.mall_buy("zhuan_art", "new-art")
    assert zhuan_end.PICK_ART in option_ids(game)
    game.choose(zhuan_end.PICK_ART)
    used = {b.ref.split(":")[-1]: b.data.get("used") is not None for b in wallet.purchases(owner) if b.item == "zhuan_art"}
    assert used == {"old-art": False, "new-art": True}


def test_only_this_seasons_tickets_are_counted_when_the_buttons_are_drawn():
    """純規則：zhuan_end.unused 帶了季就只數那一季買的。"""
    rows = [
        Purchase(id=3, owner="x", ref="r3", item="zhuan_seal", price=1, time=0, day=0, season=2, data={"zhuan_seal": 1}, refunded=None),
        Purchase(id=2, owner="x", ref="r2", item="zhuan_seal", price=1, time=0, day=0, season=1, data={"zhuan_seal": 1}, refunded=None),
    ]
    assert [b.id for b in zhuan_end.unused(rows, "zhuan_seal", 2)] == [3]
    assert [b.id for b in zhuan_end.unused(rows, "zhuan_seal", 1)] == [2]


def test_art_problem_is_a_pure_rule():
    game = make_game(side=None)
    s, c = game.state, game.content
    assert zhuan_end.art_problem(s, c, s.world) == zhuan_end.ART_NO_SIDE
    s.player.faction = "guan"
    assert zhuan_end.art_problem(s, c, s.world) is None


# ── 原 test_fb846_quote_order.py（整檔搬進來） ──
# FB-846：兩張親筆評曰照「請的先後」排，不是買的先後倒過來（QA 減法季批 7b：先請曹操、再請波才，名單與寫成的傳都是波才在前）。
# 原因：zhuan_end.season_tickets 照 Wallet.purchases（新的在前）收 quotes，而每一次請都用最舊的一張票，先請的人記在舊的那一筆、排到後面。

def test_quotes_follow_the_order_they_were_asked():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55, "zhujun": 45, "caocao": 50})
    add_story(game)
    close_season(game)
    for ref in ("q1", "q2"):
        assert game.mall_buy("zhuan_quote", ref)[0].startswith("買下")
    game.choose("zhuan:quote:caocao")
    game.choose("zhuan:quote:luzhi")
    assert figures(game.biography_entry()) == ["caocao", "luzhi"]
    assert [j.fid for j in game.biography_request(1).verdicts] == ["caocao", "luzhi"]
    assert game.write_biography(game.biography_request(1), None, game.now + 40)
    assert [p[3:5] for p in verdict_paras(game.biography_view(1)["paragraphs"])] == ["曹操", "盧植"]
    assert figures(game.biography_view(1)) == ["caocao", "luzhi"]


def test_the_order_does_not_depend_on_when_the_tickets_were_bought():
    """買一張、請一位，再買一張、請一位：照請的先後。"""
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55, "caocao": 50})
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    game.mall_buy("zhuan_quote", "q2")
    game.choose("zhuan:quote:caocao")
    assert figures(game.biography_entry()) == ["luzhi", "caocao"]


def test_season_tickets_collects_the_quotes_oldest_purchase_first():
    def ticket(pid, fid):
        return Purchase(id=pid, owner="x", ref=f"r{pid}", item="zhuan_quote", price=1, time=0, day=0, season=1,
                        data={"zhuan_quote": 1, "used": float(pid), "season": 1, "fid": fid}, refunded=None)

    newest_first = [ticket(5, "c"), ticket(4, "b"), ticket(3, "a")]  # Wallet.purchases 的次序
    assert zhuan_end.season_tickets(newest_first, 1)["quotes"] == ["a", "b", "c"]


# ── 原 test_fb847_verdict_list.py（整檔搬進來） ──
# FB-847：評曰名單（main.zhuan／/api/zhuan 的 verdicts）照寫成的那一篇傳列。
# （一）傳寫成之後才請的人不列，等重修寫進去才列；（二）管理者退了已經用過的那一張，寫成的正文照留，名單也照正文列（不因退款拿掉）。
# 還沒寫成時列的是「要寫的人」（預告）。名單從正文的段首「評曰：某某云：「」認，不另存一份。

def _written():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    return game


def test_a_quote_asked_after_the_biography_is_written_is_listed_only_after_the_rewrite():
    game = _written()
    assert game.biography_entry()["verdicts"] == []
    game.mall_buy("zhuan_quote", "q1")
    out = game.choose("zhuan:quote:luzhi")
    assert zhuan_end.QUOTE_LATER in out
    assert game.biography_entry()["verdicts"] == [] and game.biography_view(1)["verdicts"] == []
    assert verdict_paras(game.biography_view(1)["paragraphs"]) == []
    request = game.biography_request(1, rewrite=True)
    assert request is not None and [j.fid for j in request.verdicts] == ["luzhi"]
    assert game.write_biography(request, None, game.now + 60)
    got = game.biography_entry()["verdicts"]
    assert got == [{"figure": "luzhi", "name": "盧植", "reason": zhuan_end.BOUGHT}]
    assert game.biography_view(1)["verdicts"] == got
    assert game.biography_view(1)["paragraphs"][-1].startswith("評曰：盧植云：「")


def test_before_the_biography_is_written_the_list_says_who_will_write():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    assert figures(game.biography_entry()) == ["luzhi"]  # 還沒寫：預告要寫的人
    assert figures(game.biography_view(1)) == ["luzhi"]
    assert game.biography_view(1)["written"] is False


def test_a_refunded_used_quote_stays_listed_because_the_text_still_has_it():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    assert figures(game.biography_entry()) == ["luzhi"]
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    pid = next(b.id for b in wallet.purchases(owner) if b.item == "zhuan_quote")
    msg = admin_of(game).admin_mall_refund(game.state.player.name, pid, "測試退款")[0]
    assert "人物親筆評曰作廢" in msg
    game.sync(game.now + 40)
    assert figures(game.biography_entry()) == ["luzhi"]  # 正文還有他，名單就還有他
    assert figures(game.biography_view(1)) == ["luzhi"]
    assert verdict_paras(game.biography_view(1)["paragraphs"])[0].startswith("評曰：盧植云：「")


def test_a_refund_before_the_biography_is_written_takes_him_off_the_list_and_the_text():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    pid = next(b.id for b in wallet.purchases(owner) if b.item == "zhuan_quote")
    admin_of(game).admin_mall_refund(game.state.player.name, pid, "測試退款")
    game.sync(game.now + 40)
    assert game.biography_entry()["verdicts"] == []
    assert game.write_biography(game.biography_request(1), None, game.now + 50)
    assert verdict_paras(game.biography_view(1)["paragraphs"]) == [] and game.biography_view(1)["verdicts"] == []


def test_the_list_is_what_the_text_has_free_writers_first_then_the_asked_ones():
    game = make_game()
    game.state.player.affinities.update({"zhujun": 75, "luzhi": 55, "caocao": 50})
    add_story(game)
    close_season(game)
    for ref in ("q1", "q2"):
        game.mall_buy("zhuan_quote", ref)
    game.choose("zhuan:quote:luzhi")
    game.choose("zhuan:quote:caocao")
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    got = game.biography_entry()["verdicts"]
    assert [(v["figure"], v["reason"]) for v in got] == [
        ("zhujun", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT), ("caocao", zhuan_end.BOUGHT)]
    assert [p[3:5] for p in verdict_paras(game.biography_view(1)["paragraphs"])] == ["朱儁", "盧植", "曹操"]


def test_written_writers_reads_only_the_verdict_paragraphs():
    content = jianfa_game().content
    text = "\n\n".join([
        "沈浪者，不知何許人也。",
        "評曰：此人敢作敢當，頗有可取。",  # 史官自己的評曰
        "評曰：盧植云：「沈浪此季之功，吾親書以表之。」",
        "評曰：不知名者云：「這一段不認得。」",
        "評曰：盧植云：「同一位不重複列。」",
        "評曰：曹操云：「可託大事。」",
        "評曰：皇甫嵩云：「三個字的名字也認得。」",
    ])
    got = zhuan_end.written_writers(text, content, {"caocao": zhuan_end.TIER})
    assert got == [zhuan_end.Writer("luzhi", zhuan_end.BOUGHT), zhuan_end.Writer("caocao", zhuan_end.TIER),
                   zhuan_end.Writer("huangfusong", zhuan_end.BOUGHT)]
    assert zhuan_end.written_writers("", content, {}) == []


def test_the_public_page_extras_do_not_move(monkeypatch):
    """公開頁只用插畫與紀念印；名單改照正文列不動它們。"""
    import server

    game = make_game()
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_seal", "s1")
    game.choose(zhuan_end.SEAL)
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    code = game.share_biography(1, True, "fb847")
    monkeypatch.setattr(server, "CONTENT", game.content)
    got = server.zhuan_extras(game.world, game.world.biography_by_code(code))
    assert set(got) == {"seal"} and got["seal"].startswith("黃巾之亂・第 1 季")


# ── 原 test_fb848_fixed_lines.py（整檔搬進來） ──
# FB-848：模型叫不動時，同一篇傳裡每位寫手的固定句不重複（QA：波才與曹操同一個理由，固定句一字不差）。
# 固定句改成整篇一起挑（zhuan_end.fixed_verdicts）：同一個理由的寫手照順序輪著挑、整篇不撞句；自己那一組不夠了往別組借，句子全用過了才重複。

def _writers(*pairs) -> list[zhuan_end.Writer]:
    return [zhuan_end.Writer(fid, reason) for fid, reason in pairs]


def test_fixed_lines_never_repeat_inside_one_piece():
    content = jianfa_game().content
    ws = _writers(("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY),
                  ("liubei", zhuan_end.AFFINITY), ("guanyu", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT),
                  ("xunyu", zhuan_end.BOUGHT))
    for name in ("甲客", "乙客", "沈浪", "丙", "丁客", "無名氏", "蘭陵王", "青衫"):
        for season in (1, 2, 3):
            lines = zhuan_end.fixed_verdicts(content, ws, name, season)
            assert list(lines) == [w.fid for w in ws]
            assert len(set(lines.values())) == len(ws), (name, season)
            assert all(name in line and "{name}" not in line for line in lines.values())


def test_each_writer_gets_a_line_from_his_own_reason_while_the_pool_lasts():
    content = jianfa_game().content
    ws = _writers(("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT))
    lines = zhuan_end.fixed_verdicts(content, ws, "甲客", 1)
    for w in ws:
        assert lines[w.fid] in [x.replace("{name}", "甲客") for x in content.verdicts[w.reason]]


def test_the_same_inputs_give_the_same_lines():
    content = jianfa_game().content
    ws = _writers(("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY))
    assert zhuan_end.fixed_verdicts(content, ws, "甲客", 1) == zhuan_end.fixed_verdicts(content, ws, "甲客", 1)


def test_a_content_with_one_fixed_line_per_reason_still_never_repeats():
    content = jianfa_game().content
    content.verdicts = {}  # 測試內容沒有 verdicts.json：照 DEFAULT_VERDICTS 每種一句，同理由的第二位往別組借
    ws = _writers(("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY), ("luzhi", zhuan_end.AFFINITY))
    assert len(set(zhuan_end.fixed_verdicts(content, ws, "甲客", 1).values())) == 3


def test_more_writers_than_lines_repeats_instead_of_failing():
    content = jianfa_game().content
    content.verdicts = {"affinity": ["{name}一。", "{name}二。"], "tier": ["{name}三。"], "bought": ["{name}四。"]}
    ws = _writers(*[(f"p{i}", zhuan_end.AFFINITY) for i in range(6)])
    lines = zhuan_end.fixed_verdicts(content, ws, "甲客", 1)
    assert len(lines) == 6 and len(set(lines.values())) == 4  # 四句都用過了才重複


def test_the_content_pools_are_big_enough_for_the_most_writers_a_piece_can_have():
    content = jianfa_game().content
    most = content.config.jianfa.verdict_affinity_max + 1  # 情誼寫手最多三位，再加一位買來的
    assert len(content.verdicts[zhuan_end.AFFINITY]) >= most
    assert len(content.verdicts[zhuan_end.BOUGHT]) >= content.mall["zhuan_quote"].limit.season
    lines = [line for pool in content.verdicts.values() for line in pool]
    assert len(lines) == len(set(lines))  # 各組之間、組裡面都不重複（往別組借時才不會借到同一句）


def test_the_content_check_catches_a_repeated_line():
    content = jianfa_game().content
    assert zhuan_end.check_verdicts(content) == []
    content.verdicts = {"affinity": ["{name}可交。", "{name}可交。"], "tier": ["{name}可交。"]}
    problems = zhuan_end.check_verdicts(content)
    assert any("重複" in p for p in problems)


def test_four_deep_friends_and_a_tier_writer_get_the_top_three_and_four_different_lines():
    """深交不限人數（企劃者 2026-10-28），評曰只取情誼最高的前三位（PM 2026-10-28，Config.jianfa.verdict_affinity_max）：第四位關羽不寫。"""
    game = make_game()
    p = game.state.player
    p.contrib = 120  # 第一階：官軍的主將（皇甫嵩，情誼 0）替他寫
    p.affinities.update({"zhujun": 80, "caocao": 75, "liubei": 72, "guanyu": 71})
    game.sync(game.now)
    assert all(p.affinities[cid] >= 70 for cid in ("zhujun", "caocao", "liubei", "guanyu"))  # 不限人數（企劃者 2026-10-28）
    add_story(game)
    close_season(game)
    request = game.biography_request(1)
    assert [(j.fid, j.reason) for j in request.verdicts] == [
        ("huangfusong", zhuan_end.TIER), ("zhujun", zhuan_end.AFFINITY), ("caocao", zhuan_end.AFFINITY),
        ("liubei", zhuan_end.AFFINITY)]
    assert len({j.fixed for j in request.verdicts}) == 4
    assert game.write_biography(request, None, game.now + 30)  # 模型叫不動：整篇都是固定句
    said = [para.split("：「", 1)[1] for para in verdict_paras(game.biography_view(1)["paragraphs"])]
    assert len(said) == 4 and len(set(said)) == 4


def test_a_single_writer_keeps_the_old_entry_point():
    content = jianfa_game().content
    writer = zhuan_end.Writer("luzhi", zhuan_end.TIER)
    assert zhuan_end.fixed_verdict(content, writer, "甲客", 1) in [line.replace("{name}", "甲客") for line in content.verdicts["tier"]]


# ── 原 test_fb849_art_note.py（整檔搬進來） ──
# FB-849：列傳插畫票的說明照這一季的季曆寫上架時機：7 天季的「週」是段，畫面上沒有「第三週」，寫「第 5 天起買得到」（讀 MallWindow.from_week
# 和 calendar 的段，不另寫一份判斷）；其他季照舊「第三週起買得到」。說明（content/mall.json 的 note）用插槽 {上架}，載入時驗插槽。

@pytest.mark.parametrize("profile, said, other", [("season21", "第三週起買得到", "第 5 天"), ("week7", "第 5 天起買得到", "第三週")])
def test_the_art_note_says_when_it_goes_on_sale_in_the_calendars_own_words(profile, said, other):
    game = make_game(profile)
    to_week(game, 3)
    note = row(game, "zhuan_art")["note"]
    assert said in note and other not in note and "{" not in note


def test_the_week7_note_names_the_day_the_item_really_goes_on_sale():
    game = make_game("week7")
    c, w = game.content, game.state.world
    first = calendar.segment_days(3, c)[0]
    assert first == 5
    start = calendar.week_start(3, c, w)
    w.time = start - 600
    game._save_season()
    assert row(game, "zhuan_art") is None  # 第 4 天 23:50：還沒上架
    w.time = start + 600
    game._save_season()
    assert f"第 {first} 天起買得到" in row(game, "zhuan_art")["note"]  # 第 5 天 00:10：上架了，說明寫的就是這一天


def test_the_rest_keeps_the_same_words_and_the_other_items_are_untouched():
    game = make_game("week7")
    to_week(game, 3)
    shelf = {r["id"]: r["note"] for r in game.mall_view()["items"]}
    for item_id, note in shelf.items():
        if item_id != "zhuan_art":
            assert note == game.content.mall[item_id].note  # 沒有插槽的說明一個字不變
    close_season(game)
    assert "第 5 天起買得到" in row(game, "zhuan_art")["note"]


def test_a_note_slot_has_to_be_known_and_needs_a_week_to_fill():
    content = jianfa_game().content
    bad = MallItem(id="x", name="測試貨", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="買不到{別的}。")
    assert any("{別的}" in line for line in mall.item_problems(bad, content))
    no_week = MallItem(id="y", name="測試二", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="{上架}起買得到。")
    assert any("{上架}" in line for line in mall.item_problems(no_week, content))
    ok = MallItem(id="z", name="測試三", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="{上架}起買得到。",
                  on_sale=MallWindow(rule="zhuan_end", from_week=3))
    assert not any("{" in line for line in mall.item_problems(ok, content))


def test_the_real_content_note_uses_the_slot():
    content = jianfa_game().content
    assert "{上架}" in content.mall["zhuan_art"].note and "第三週" not in content.mall["zhuan_art"].note
    assert not any("zhuan_art" in line for item in content.mall.values() for line in mall.item_problems(item, content))
