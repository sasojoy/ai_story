"""慢慢長出來（tianxia/features/unfold/）：新角色站在城門口開本、只看得到江湖與俠客的武學；選了路輿圖長出來，
升級長出屬性、拿到東西長出裝備；長出來的亮紅點、點開才滅、不收回；舊角色與開關關著一個鍵都不多。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from fastapi.testclient import TestClient

import server
from tianxia.engine import Game
from tianxia.features.unfold import rules


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    c.config.unfold.enabled = True
    return c


def _new(content, name="沈浪"):
    g = Game.new(content, name, rng=random.Random(0), prologue=True)
    g.sync(g.now + 1)
    return g


def test_a_new_player_at_the_gate_starts_with_everything_folded(on):
    g = _new(on)
    u = g.feature_status()["unfold"]
    assert set(u["hide"]) == set(rules.KEYS) and u["fresh"] == []


def test_choosing_a_road_grows_the_map_with_a_dot(on):
    g = _new(on)
    g.choose("choice:0")
    u = g.feature_status()["unfold"]
    assert "tab:map" not in u["hide"] and "tab:map" in u["fresh"]
    rules.seen(g.state.player.unfold, ["tab:map"])
    assert "tab:map" not in g.feature_status()["unfold"]["fresh"]


def test_grown_blocks_never_fold_back(on):
    g = _new(on)
    g.choose("choice:0")
    g.state.player.stat_points = 1
    g.sync(g.now + 1)
    assert "hero:attrs" in g.state.player.unfold.grown
    g.state.player.stat_points = 0
    g.sync(g.now + 1)
    assert "hero:attrs" not in g.feature_status()["unfold"]["hide"]


def test_old_characters_and_the_switch_off_keep_no_key(on):
    g = _new(on)
    g.choose("choice:0")
    g.state.player.unfold = None  # 舊角色：走過城門口才打開開關
    g.sync(g.now + 1)
    assert g.state.player.unfold is None and "unfold" not in g.feature_status()
    on.config.unfold.enabled = False
    assert "unfold" not in _new(on, "林三").feature_status()
    assert "unfold" not in g.state.player.model_dump()


@pytest.mark.smoke
def test_seen_route_clears_the_dot_and_is_404_when_off(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "t.db"))
    client = TestClient(server.app)
    monkeypatch.setattr(server.CONTENT.config.unfold, "enabled", False)
    assert client.post("/api/unfold/seen", json={"keys": []}).status_code in (401, 404)


# ── 小事卡（features/unfold/cards.py）：門派、書信、結義、稱號、江湖錄、合成第一次碰到時攤一張（帶著對象），一次一張、每種一次
def _card(name="王越"):
    from tianxia.state import Mingtie, MingtieCopy

    return MingtieCopy(name=name, card=Mingtie(), when="", place="", season=1, gave=1)


def _card_now(g):
    g.sync(g.now + 1)
    return (g.feature_status()["unfold"] or {}).get("card")


def test_standing_at_a_sect_gate_lays_the_sect_card_with_its_join_button(on):
    on.config.zongmen.enabled = True
    g = _new(on)
    g.choose("choice:0")
    sect = next(s for s in on.sects.values() if s.switch == "zongmen" and on.sect_open(s.id))
    g.state.player.location = sect.location
    k = _card_now(g)
    assert k["kind"] == "sect" and k["arg"] == sect.id and k["go"] and k["later"]
    rules_book = g.state.player.unfold
    from tianxia.features.unfold import cards

    cards.close(g, rules_book)
    assert _card_now(g) is None  # 收了就不再出同一種


def test_one_card_at_a_time_mail_then_jieyi_after_a_fight_together(on):
    from tianxia.features.unfold import cards
    from tianxia.state import BattleRecord, Fighter

    on.config.mail.enabled = on.config.jieyi.enabled = True
    g = _new(on)
    g.choose("choice:0")
    g.state.player.mingtie_box.append(_card())
    assert _card_now(g)["kind"] == "mail"
    g.state.battles.append(BattleRecord(id=99, time=0, location="", kind="spar", opponent="王越", ours=[Fighter(name="沈浪", level=1)],
                                        tier="險勝", our_power=1, difficulty=1))
    assert _card_now(g)["kind"] == "mail"  # 前一張還攤著：排著等
    cards.close(g, g.state.player.unfold)
    k = _card_now(g)
    assert k["kind"] == "jieyi" and k["arg"] == "王越"


def test_an_old_player_never_gets_a_card(on):
    on.config.mail.enabled = True
    g = _new(on)
    g.choose("choice:0")
    g.state.player.unfold = None
    g.state.player.mingtie_box.append(_card())
    g.sync(g.now + 1)
    assert "unfold" not in g.feature_status()


def test_a_new_player_no_longer_hears_the_three_replaced_hints(on):
    g = _new(on)
    assert {"h_merge", "h_points", "h_create"} <= g.state.player.hints_seen


def test_a_new_player_hears_the_short_line(on):
    from tianxia.features.guide import hints, short

    g = _new(on)
    assert hints.note_for(g.state, on, "h_tavern").text == short.SHORT["h_tavern"]
    g.state.player.unfold = None
    assert hints.note_for(g.state, on, "h_tavern").text != short.SHORT["h_tavern"]


def test_the_mall_comes_up_once_the_road_is_chosen_and_the_pills_when_legs_give_out(on):
    from tianxia.features.guide import actions

    on.config.mall.enabled = True
    g = _new(on)
    assert "h_mall" not in actions.hint_triggers(g)
    g.choose("choice:0")
    assert "h_mall" in actions.hint_triggers(g)
    p = g.state.player
    p.stamina, p.stamina_pills = 3, 0
    assert "h_pills" in actions.hint_triggers(g)
    p.stamina_pills = 1
    assert "h_pills" not in actions.hint_triggers(g)


# ── 見面禮與買了之後（Joy 2026-11-25：100 元寶；「很多商城裡面的東西也要教學」）
def _errand_done(g):
    from tianxia.state import ErrandState

    fid = next(iter(g.content.figures))
    g.state.player.errands.append(ErrandState(id="e1", figure=fid, errand="x", kind="letter", target=g.state.player.location, week=1,
                                              at=0, expires=1e12, letter=1, status="done"))
    return g.content.figures[fid].name


def test_the_first_errand_done_brings_the_gift_card_and_pressing_it_pays_once(on):
    from tianxia.features.unfold import cards
    from tianxia.wallet import Wallet

    g = _new(on)
    g.choose("choice:0")
    assert _card_now(g) is None
    who = _errand_done(g)
    k = _card_now(g)
    assert k["kind"] == "gift" and who in k["say"] and "100" in k["say"]
    wallet = Wallet(g.world.db)
    before = wallet.balance(g._mall_owner())
    cards.close(g, g.state.player.unfold)
    assert wallet.balance(g._mall_owner()) == before + 100
    assert cards.give_gift(g) == 0 and wallet.balance(g._mall_owner()) == before + 100  # 一輩子一次
    assert _card_now(g) is None


def test_after_the_first_buy_of_a_kind_a_card_teaches_its_first_use(on):
    from tianxia.features.mall import actions as mall_actions
    from tianxia.features.unfold import cards
    from tianxia.wallet import Wallet

    g = _new(on)
    g.choose("choice:0")
    Wallet(g.world.db).post(g._mall_owner(), 1000, "grant", "test:seed", time=g.now)
    mall_actions.buy(g, "pills_5", "ref-unfold-0001")
    k = _card_now(g)
    assert (k["kind"], k["arg"], k["who"]) == ("buy", "pills", "回體丹五顆") and k["go"] == "服一顆"
    cards.close(g, g.state.player.unfold)
    mall_actions.buy(g, "pills_5", "ref-unfold-0002")
    assert _card_now(g) is None  # 同一種只教一次


def test_the_jianghu_page_blocks_grow_by_the_table(on):
    """江湖頁重排第六批的表（PM 2026-11-25 同意）：俠客、出陣軍務、五塊招牌各自什麼時候長出來。"""
    g = _new(on)
    jh = [k for k in rules.KEYS if k.startswith("jh:")]
    assert set(jh) <= set(g.feature_status()["unfold"]["hide"])  # 城門口全收著
    g.choose("choice:0")
    p = g.state.player
    p.faction = next(iter(on.scenario.factions)).id if isinstance(on.scenario.factions, list) else next(iter(on.scenario.factions))
    _errand_done(g)
    p.stats["silver"] = on.config.unfold.sign_silver_dadian
    p.mingtie_box.append(_card())
    g.sync(g.now + 1)
    grown = set(p.unfold.grown)
    assert {"jh:peers", "jh:sortie", "jh:duty", "jh:sign:bounties", "jh:sign:dadian"} <= grown and "jh:sign:market" not in grown
    p.stats["silver"] = on.config.unfold.sign_silver_market
    g.sync(g.now + 1)
    assert "jh:sign:market" in p.unfold.grown
    assert "jh:sign:arena" not in grown and ("jh:sign:smith" in grown) == ("hero:gear" in grown)


def test_shop_goods_bought_with_the_gift_cannot_change_hands():
    """見面禮是白送的元寶，帳號綁定還沒開、一個人能開很多號（PM 2026-11-25）：小號買的東西不能轉給大號。
    贈物只送素材、商城沒有一樣效果是素材；市集形象一件最低價比見面禮高（小號買大號掛的形象，大號拿分成，就是轉手）。"""
    from tianxia.features.looks import market
    from tianxia.features.mall import rules as mall_rules
    from tianxia.features.peers import social

    c = real_content()
    assert social.GIFT_KINDS == ("material",)
    assert not any(k in ("material", "materials", "silver") for k in mall_rules.EFFECTS)
    assert all("material" not in k for item in c.mall.values() for k in item.effects)
    assert c.config.unfold.gift < market.PRICE_MIN
