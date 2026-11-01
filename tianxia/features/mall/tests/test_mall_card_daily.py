"""萬寶閣販賣清單定案（Joy 2026-10-21）：月卡甲・每日領（買下當場回 300、每天上線領 60 元寶＋1 顆回體丹、沒上線不補）與重修列傳。
帳本結構不動：月卡的元寶記成 grant，照編號開頭認（mall.CARD_REFS）。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season
from test_mall import DAY, DAY0, T0, _admin, _game, _ready, _rows, _wallet

from tianxia import annals, biography, mall
from tianxia.engine import Game
from tianxia.models import MallItem


@pytest.fixture
def on(content):
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    m.card_daily_ingots, m.card_daily_pills = 60, 1
    content.mall = {i.id: i for i in (
        MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30, "card_rebate": 300}, limit={"account": 3}),
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}),
        MallItem(id="rewrite_zhuan", name="重修列傳", price=200, kind="consumable", effects={"zhuan_rewrite": 1}, limit={"season": 2}),
    )}
    content.config.admins = ["管理者"]
    return content


def test_card_pays_back_300_at_once(on):
    game = _ready(on)
    game.mall_buy("card_30", "r1")
    assert _wallet(game).balance("沈浪") == 5000 - 600 + 300
    rebate = _rows(game)[0]
    assert (rebate.reason, rebate.delta, rebate.ref) == ("grant", 300, f"card:rebate:{rebate.purchase_id}")
    assert "元寶 +300（月卡回饋）" in game.state.journal[0].changes
    reasons = [r["reason"] for r in game.mall_records()["ledger"]]
    assert reasons[:2] == ["月卡回饋", "購買"]


def test_claim_once_a_day_and_no_make_up(on):
    game = _ready(on)
    assert "沒有月卡" in game.mall_claim()[0]
    assert "daily" not in game.mall_entry()
    game.mall_buy("card_30", "d1")
    pills = game.state.player.stamina_pills
    assert game.mall_entry()["daily"] == {"ingots": 60, "pills": 1, "claimed": False}
    msg = game.mall_claim()
    assert "元寶 +60" in msg[0] and game.state.player.stamina_pills == pills + 1
    assert _wallet(game).balance("沈浪") == 4700 + 60
    assert game.mall_entry()["daily"]["claimed"] is True
    assert "領過了" in game.mall_claim()[0] and _wallet(game).balance("沈浪") == 4760
    game.now = T0 + 3 * DAY  # 中間兩天沒上線：不補
    game.mall_claim()
    assert _wallet(game).balance("沈浪") == 4820
    daily = [r.ref for r in _rows(game) if r.ref.startswith("card:daily:")]
    assert daily == [f"card:daily:沈浪:{DAY0 + 3}", f"card:daily:沈浪:{DAY0}"]
    game.now = T0 + 30 * DAY  # 卡到期了
    assert "沒有月卡" in game.mall_claim()[0] and "daily" not in game.mall_entry()


def test_no_daily_share_when_config_is_zero(on):
    on.config.mall.card_daily_ingots = on.config.mall.card_daily_pills = 0
    game = _ready(on)
    game.mall_buy("card_30", "z1")
    assert game.mall_view()["card"]["daily"] is None and "daily" not in game.mall_entry()
    assert game.mall_claim()[0] == mall.NO_DAILY


def test_view_lists_the_perks_on_the_card(on):
    game = _ready(on)
    card = {row["id"]: row for row in game.mall_view()["items"]}["card_30"]
    assert "每天領 60 元寶與 1 顆回體丹" in card["effects"] and "當場回 300 元寶" in card["effects"]
    assert card["perks"][0] == "買下當場拿回 300 元寶" and "沒上線那天不補" in card["perks"][1]
    assert {row["id"]: row for row in game.mall_view()["items"]}["pills_5"]["perks"] == []


def test_refunding_a_card_takes_the_rebate_back(on):
    player = _ready(on)
    player.mall_buy("card_30", "f1")
    pid = _wallet(player).purchases("沈浪")[0].id
    msg = _admin(on).admin_mall_refund("沈浪", pid, "測試退卡")
    assert "300 元寶扣回" in msg[0]
    assert _wallet(player).balance("沈浪") == 5000
    assert [r["reason"] for r in mall.records(on, _wallet(player), "沈浪")["ledger"]][0] == "扣回月卡回饋"


@pytest.mark.smoke
def test_rebate_must_be_below_the_price(on):
    bad = MallItem(id="x", name="怪卡", price=100, kind="card", effects={"card_days": 3, "card_rebate": 100})
    assert any("要比價錢" in p for p in mall.item_problems(bad, on))
    alone = MallItem(id="y", name="怪帖", price=100, kind="card", effects={"card_rebate": 10})
    assert any("card_days" in p for p in mall.item_problems(alone, on))


# ── 重修列傳 ──


def _closed(on) -> Game:
    on.config.biography.enabled = True
    game = _ready(on)
    game.client = None
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    Game.new(on, "管理者", rng=random.Random(1), world=game.world).admin_end_season(now=T0 + 10)
    game.sync(T0 + 20)
    game.write_biography(game.biography_request(1), None, 5.0)
    return game


def test_rewrite_tokens_add_rewrites(on):
    on.config.biography.rewrites = 1
    game = _closed(on)
    text = "沈浪者，" + "起於潁川，" * 50
    assert game.write_biography(game.biography_request(1, rewrite=True), text, 6.0)
    assert game.biography_view(1)["can_rewrite"] is False and game.biography_request(1, rewrite=True) is None
    game.mall_buy("rewrite_zhuan", "z1")
    assert "列傳重寫 +1" in game.state.journal[0].changes
    assert game.biography_view(1)["can_rewrite"] is True
    assert game.write_biography(game.biography_request(1, rewrite=True), text + "又", 7.0)
    assert mall.rewrite_tokens(_wallet(game), "沈浪") == []  # 用掉了
    assert game.biography_view(1)["can_rewrite"] is False


def test_free_rewrite_does_not_use_a_token(on):
    on.config.biography.rewrites = 1
    game = _closed(on)
    game.mall_buy("rewrite_zhuan", "z2")
    assert game.write_biography(game.biography_request(1, rewrite=True), None, 6.0)
    assert len(mall.rewrite_tokens(_wallet(game), "沈浪")) == 1
    assert game.biography_view(1)["can_rewrite"] is True


def test_rewrite_is_limited_twice_a_season(on):
    game = _ready(on)
    assert game.mall_buy("rewrite_zhuan", "a")[0].startswith("買下")
    assert game.mall_buy("rewrite_zhuan", "b")[0].startswith("買下")
    assert not game.mall_buy("rewrite_zhuan", "c")[0].startswith("買下")
    next_season(on, game.world, game)
    game.sync(T0 + DAY)
    assert game.mall_buy("rewrite_zhuan", "d")[0].startswith("買下")


# ── 易名帖（當場生效）──


def _rename_on(on):
    on.mall["rename"] = MallItem(id="rename", name="易名帖", price=300, kind="consumable", effects={"rename": 1}, limit={"season": 1})
    return on


def test_rename_needs_a_token(on):
    game = _ready(_rename_on(on))
    assert game.mall_rename("沈青") == [mall.NO_RENAME]
    assert "rename" not in game.mall_entry()


def test_rename_moves_everything_to_the_new_name(on):
    from tianxia.characters import open_characters
    game = _ready(_rename_on(on))
    other = _game(on, "葉開")
    other.state.player.tagalong = None
    game.mall_buy("card_30", "c")
    game.mall_buy("rename", "n")
    assert game.mall_entry()["rename"] == 1
    # 別人存檔與這一季的全服狀態裡提到他的地方
    other.state.player.hearsay_keys.append("沈浪")
    open_characters().save(other.state)
    msg = game.mall_rename("沈青")
    assert "沈青" in msg[0] and game.state.player.name == "沈青"
    store = open_characters()
    assert store.load("沈浪") is None and store.load("沈青").player.name == "沈青"
    assert "沈浪" not in store.load("葉開").player.hearsay_keys and "沈青" in store.load("葉開").player.hearsay_keys
    w = _wallet(game)
    assert w.balance("沈浪") == 0 and w.balance("沈青") == 5000 - 600 + 300 - 300
    assert w.card("沈青", mall.CARD_KEY) is not None
    assert not w.has_ref("grant:beta:沈浪") and w.has_ref("grant:beta:沈青")  # 封測發放不會再發一次
    game.mark_seen(T0 + 60)
    assert w.balance("沈青") == 4400
    assert mall.rename_tokens(w, "沈青") == [] and "rename" not in game.mall_entry()
    chron = [r.text for r in game.world.get_season().chronicle]
    assert "沈浪改名沈青。" in chron


def test_rename_refuses_taken_and_reserved_names(on):
    game = _ready(_rename_on(on))
    _game(on, "葉開")
    game.mall_buy("rename", "n")
    assert "有人使用" in game.mall_rename("葉開")[0]
    assert "有人使用" in game.mall_rename("管理者")[0]
    assert game.mall_rename("沈浪") == [mall.RENAME_SAME]
    assert len(mall.rename_tokens(_wallet(game), "沈浪")) == 1  # 沒改成不用掉


def test_rename_is_once_a_season(on):
    game = _ready(_rename_on(on))
    assert game.mall_buy("rename", "a")[0].startswith("買下")
    assert not game.mall_buy("rename", "b")[0].startswith("買下")


def test_admin_cannot_rename(on):
    admin = _admin(_rename_on(on))
    admin.mall_buy("rename", "a")
    assert admin.mall_rename("新管理") == [mall.RENAME_ADMIN]


# ── 藏經匣：功法庫上限擴充（Joy 2026-10-21「一張多放15格，沒有上限」）──


def _holding_on(on):
    on.mall["holding_15"] = MallItem(id="holding_15", name="藏經匣", price=300, kind="consumable", effects={"holding": 15})
    return on


def test_holding_box_adds_fifteen_each_without_a_limit(on):
    from tianxia import library
    game = _ready(_holding_on(on))
    base = library.cap_of(game.state, on)
    for i in range(4):
        assert game.mall_buy("holding_15", f"h{i}")[0].startswith("買下")
    assert library.cap_of(game.state, on) == base + 60 and game.state.player.holding_bonus == 60
    assert f"功法庫上限 +15（現在 {base + 60} 格，這一季）" in game.state.journal[0].changes
    card = {row["id"]: row for row in game.mall_view()["items"]}["holding_15"]
    assert "功法庫多放 15 格（這一季）" in card["effects"]


def test_holding_box_lasts_only_this_season(on):
    from tianxia import library
    game = _ready(_holding_on(on))
    base = library.cap_of(game.state, on)
    game.mall_buy("holding_15", "s1")
    next_season(on, game.world, game)
    game.sync(T0 + DAY)
    assert game.state.player.holding_bonus == 0 and library.cap_of(game.state, on) <= base


def test_refunding_a_holding_box_takes_the_slots_back(on):
    player = _ready(_holding_on(on))
    from tianxia.characters import open_characters
    player.mall_buy("holding_15", "r1")
    open_characters().save(player.state)  # 伺服器每個動作之後都存檔；管理者退款照資料庫裡那一份改
    pid = _wallet(player).purchases("沈浪")[0].id
    msg = _admin(on).admin_mall_refund("沈浪", pid, "測試退匣")
    assert "功法庫上限收回 15 格" in msg[0]
    assert open_characters().load("沈浪").player.holding_bonus == 0
