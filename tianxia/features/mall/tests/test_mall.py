"""商城的引擎那一側（商城架構設計第四節）：封測發放、月卡加回體丹上限、購買與發貨、限購與上架、月卡的日子、管理者工具。
測試內容的商城關著（Config.mall），這裡自己打開、自己放商品。時間：現實秒，台灣 00:00 換日（同回體丹，Game._pill_day）。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season

from tianxia import mall, roster, skillview
from tianxia.characters import name_key, open_characters
from tianxia.engine import Game
from tianxia.models import MallItem
from tianxia.state import BotProfile
from tianxia.wallet import Wallet

HOUR = 3600
DAY = 24 * HOUR
MIDNIGHT_TW = DAY - 8 * HOUR  # 1970-01-02 00:00（台灣）
T0 = MIDNIGHT_TW + 20000 * DAY + 9 * HOUR  # 某一天台灣早上九點
DAY0 = int((T0 + 8 * HOUR) // DAY)


def _items() -> dict[str, MallItem]:
    return {i.id: i for i in (
        MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5}, limit={"day": 2}),
        MallItem(id="pills_30", name="回體丹三十顆", price=500, kind="consumable", effects={"pills": 30}, limit={"season": 1}),
        MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30}, limit={"account": 2}),
        MallItem(id="card_1", name="一日卡", price=10, kind="card", effects={"card_days": 1}),
    )}


@pytest.fixture
def on(content):
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    content.mall = _items()
    content.config.stamina_pills_per_day = 2
    content.config.newbie_pills_per_day = 5
    content.config.admins = ["管理者"]
    return content


def _game(content, name="沈浪", now=T0) -> Game:
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(now)
    open_characters().save(game.state)  # 伺服器存過的樣子：管理者照名號找得到他
    return game


def _wallet(game) -> Wallet:
    return Wallet(game.world.db)


def _rows(game) -> list:
    return _wallet(game).ledger(name_key(game.state.player.name))


def _titles(game) -> list[str]:
    return [e.title for e in game.state.journal]


# ── 封測發放 ─────────────────────────────────────


@pytest.mark.smoke
def test_off_means_no_grant_and_no_rows(content):
    content.config.mall.beta_grant = 5000  # 開關關著，數字寫了也不發
    game = _game(content)
    game.mark_seen(T0)
    with game.world.db.snapshot() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mall_ledger").fetchone()[0] == 0
    assert "商城" not in _titles(game)


def test_first_own_turn_grants_once(on):
    game = _game(on)
    game.mark_seen(T0)
    game.mark_seen(T0 + 60)
    rows = _rows(game)
    assert [(r.reason, r.delta, r.ref) for r in rows] == [("grant", 5000, "grant:beta:沈浪")]
    assert _titles(game).count("商城") == 1
    assert _wallet(game).balance("沈浪") == 5000


def test_zero_grant_writes_nothing(on):
    on.config.mall.beta_grant = 0
    game = _game(on)
    game.mark_seen(T0)
    assert _rows(game) == [] and "商城" not in _titles(game)


def test_grant_is_not_repeated_next_season(on):
    game = _game(on)
    game.mark_seen(T0)
    next_season(on, game.world, game)
    game.mark_seen(T0 + DAY)
    assert len(_rows(game)) == 1


def test_bots_get_the_same_grant(on):
    """假人沒有帳號也有錢包（錢包照角色名號），假人程式自己那一輪（own_turn_checks）照樣發：看不出誰是假人。"""
    game = _game(on, "某假人")
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    game.own_turn_checks()
    assert [(r.reason, r.delta) for r in _rows(game)] == [("grant", 5000)]


# ── 月卡加上限 ───────────────────────────────────


def _card(game, start, end):
    _wallet(game).set_card(name_key(game.state.player.name), mall.CARD_KEY, start, end)


def test_card_adds_one_to_the_daily_cap(on, monkeypatch):
    game = _game(on)
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: False)
    assert game.pill_cap() == 2
    _card(game, DAY0, DAY0 + 30)
    assert game.pill_cap() == 3 and game.pills_left_today() == 3
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: True)
    assert game.pill_cap() == 6  # 新手期 5 → 6


def test_no_cap_stays_no_cap(on):
    on.config.stamina_pills_per_day = 0  # 不限就是不限
    game = _game(on)
    _card(game, DAY0, DAY0 + 30)
    assert game.pill_cap() == 0 and game.pills_left_today() is None


def test_card_bonus_is_ignored_when_the_mall_is_off(on):
    game = _game(on)
    _card(game, DAY0, DAY0 + 30)
    on.config.mall.enabled = False
    assert game.pill_cap() in (2, 5)  # 照原本的（新手期與否），不加


def test_stamina_help_names_the_card_cap(on, monkeypatch):
    """FB-480：月卡有效時，點體力條看的說明照這個人此刻的上限寫（跟 pill_cap、「今天還能服幾顆」對得上）；沒有卡一個字都不變。"""
    game = _game(on)
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: False)
    plain = game.status_data()["stamina_help"][-1]
    assert "一天最多服 2 顆（新手期 5 顆），每天 00:00（台灣時間）重新計算（今天還能服 2 顆）。" in plain
    _card(game, DAY0, DAY0 + 30)
    line = game.status_data()["stamina_help"][-1]
    assert "一天最多服 3 顆（新手期 6 顆；月卡多 1 顆），每天 00:00（台灣時間）重新計算（今天還能服 3 顆）。" in line
    on.config.mall.enabled = False  # 商城關著：卡不算，說明照舊
    assert game.status_data()["stamina_help"][-1] == plain


def test_newbie_line_names_the_card_cap(on, monkeypatch):
    """FB-480：新手期那一行「回體丹一天能服 N 顆」有月卡時照 pill_cap 寫（5 → 6）。"""
    on.config.newbie_real_hours = 48
    game = _game(on)
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: True)
    assert any("回體丹一天能服 5 顆，" in line for line in game.status_data()["stamina_help"])
    _card(game, DAY0, DAY0 + 30)
    help_lines = game.status_data()["stamina_help"]
    assert game.pill_cap() == 6
    assert any("回體丹一天能服 6 顆（月卡多 1 顆），" in line for line in help_lines)


# ── 購買與發貨 ───────────────────────────────────


def _date(day: int) -> str:
    from datetime import date, timedelta

    return (date(1970, 1, 1) + timedelta(days=day)).isoformat()


def _ready(on, name="沈浪", now=T0) -> Game:
    game = _game(on, name, now)
    game.mark_seen(now)  # 封測發放 5000
    return game


def test_buying_pills_moves_yuanbao_and_pills(on):
    game = _ready(on)
    pills = game.state.player.stamina_pills
    msgs = game.mall_buy("pills_5", "ref-0001")
    assert game.state.player.stamina_pills == pills + 5
    wallet = _wallet(game)
    assert wallet.balance("沈浪") == 4900
    buy = _rows(game)[0]
    assert (buy.reason, buy.delta, buy.ref) == ("buy", -100, "buy:沈浪:ref-0001") and buy.purchase_id
    bought = wallet.purchase(buy.purchase_id)
    assert (bought.item, bought.price, bought.day, bought.data) == ("pills_5", 100, DAY0, {"pills": 5})
    assert bought.season == game.world.get_season_number() and bought.time == T0
    entry = game.state.journal[0]
    assert entry.title == "商城" and "元寶 -100" in entry.changes and "回體丹 +5" in entry.changes
    assert any("回體丹五顆" in m for m in msgs)


def test_not_enough_yuanbao_writes_nothing(on):
    on.config.mall.beta_grant = 50
    game = _ready(on)
    pills, entries = game.state.player.stamina_pills, len(game.state.journal)
    msgs = game.mall_buy("pills_5", "ref-0002")
    assert "元寶不夠" in msgs[0]
    assert _wallet(game).balance("沈浪") == 50 and len(_rows(game)) == 1
    assert _wallet(game).purchases("沈浪") == []
    assert game.state.player.stamina_pills == pills and len(game.state.journal) == entries


def test_unknown_item_is_refused(on):
    game = _ready(on)
    assert game.mall_buy("nope", "ref-0003") == [mall.NO_ITEM]
    assert len(_rows(game)) == 1


def test_same_ref_twice_charges_once(on):
    game = _ready(on)
    pills = game.state.player.stamina_pills
    game.mall_buy("pills_5", "same-ref-1")
    again = game.mall_buy("pills_5", "same-ref-1")
    assert "已經買好" in again[0]
    assert _wallet(game).balance("沈浪") == 4900 and len(_wallet(game).purchases("沈浪")) == 1
    assert game.state.player.stamina_pills == pills + 5


def test_limits_per_day(on):
    game = _ready(on)
    assert game.mall_buy("pills_5", "d1")[0].startswith("買下")
    assert game.mall_buy("pills_5", "d2")[0].startswith("買下")
    refused = game.mall_buy("pills_5", "d3")
    assert "今天" in refused[0] and _wallet(game).balance("沈浪") == 4800
    game.now = T0 + 15 * HOUR  # 台灣隔天 00:00
    assert game.mall_buy("pills_5", "d4")[0].startswith("買下")


def test_limits_per_season(on):
    game = _ready(on)
    assert game.mall_buy("pills_30", "s1")[0].startswith("買下")
    assert "這一季" in game.mall_buy("pills_30", "s2")[0]
    next_season(on, game.world, game)
    game.now = T0 + DAY
    assert game.mall_buy("pills_30", "s3")[0].startswith("買下")


def test_limits_per_account(on):
    game = _ready(on)
    assert game.mall_buy("card_30", "a1")[0].startswith("買下")
    assert game.mall_buy("card_30", "a2")[0].startswith("買下")
    assert "每個帳號" in game.mall_buy("card_30", "a3")[0]
    next_season(on, game.world, game)
    game.now = T0 + DAY
    assert "每個帳號" in game.mall_buy("card_30", "a4")[0]


def test_items_out_of_window_are_not_for_sale(on):
    game = _ready(on)
    window = on.mall["pills_5"].on_sale
    window.seasons = [9]
    assert game.mall_buy("pills_5", "w1") == [mall.NO_ITEM]
    window.seasons = []
    window.start = _date(DAY0 + 1)
    assert game.mall_buy("pills_5", "w2") == [mall.NO_ITEM]
    window.start, window.end = None, _date(DAY0 - 1)
    assert game.mall_buy("pills_5", "w3") == [mall.NO_ITEM]
    window.start = window.end = _date(DAY0)  # 頭尾都含
    assert game.mall_buy("pills_5", "w4")[0].startswith("買下")


def test_a_failed_delivery_rolls_everything_back(on, monkeypatch):
    """發貨中途出錯（這裡是月卡寫不進去）：伺服器的行動鎖是一筆交易，整筆撤回——帳、購買紀錄、月卡都跟沒買一樣，手上的東西也沒動。"""
    game = _ready(on)
    pills = game.state.player.stamina_pills

    def boom(*args, **kwargs):
        raise RuntimeError("發貨壞了")

    monkeypatch.setattr(Wallet, "set_card", boom)
    with pytest.raises(RuntimeError), game.world.db.transaction():
        game.mall_buy("card_30", "ref-boom")
    wallet = _wallet(game)
    assert wallet.balance("沈浪") == 5000 and len(_rows(game)) == 1
    assert wallet.purchases("沈浪") == [] and wallet.card("沈浪", mall.CARD_KEY) is None
    assert game.state.player.stamina_pills == pills


def test_balance_always_equals_the_ledger(on):
    game = _ready(on)
    for i, item in enumerate(("pills_5", "pills_30", "card_30", "card_1", "pills_5")):
        game.mall_buy(item, f"sum-{i}")
    rows = _rows(game)
    assert _wallet(game).balance("沈浪") == sum(r.delta for r in rows) == 5000 - 100 - 500 - 600 - 10 - 100


# ── 月卡的日子 ───────────────────────────────────


def test_card_bought_at_2359_counts_that_day(on, monkeypatch):
    monkeypatch.setattr(roster, "newbie", lambda state, content, days=None: False)
    late = MIDNIGHT_TW + 20000 * DAY + DAY - 60  # DAY0 的台灣 23:59
    game = _ready(on, now=late)
    game.mall_buy("card_1", "c1")
    assert _wallet(game).card("沈浪", mall.CARD_KEY) == (DAY0, DAY0 + 1)
    assert game.pill_cap() == 3
    game.now = late + 60  # 00:00 一到就失效
    assert game.pill_cap() == 2


def test_card_rebuy_extends_from_the_end(on):
    game = _ready(on)
    game.mall_buy("card_30", "e1")
    game.now = T0 + 20 * DAY  # 還剩 10 天
    game.mall_buy("card_30", "e2")
    assert _wallet(game).card("沈浪", mall.CARD_KEY) == (DAY0, DAY0 + 60)


def test_card_rebuy_after_expiry_starts_today(on):
    game = _ready(on)
    game.mall_buy("card_1", "x1")
    game.now = T0 + 5 * DAY
    game.mall_buy("card_1", "x2")
    assert _wallet(game).card("沈浪", mall.CARD_KEY) == (DAY0 + 5, DAY0 + 6)


# ── 畫面資料 ─────────────────────────────────────


def test_view_is_none_when_off(content):
    game = _game(content)
    assert game.mall_view() is None and game.mall_records() is None


def test_view_lists_items_with_why(on):
    game = _ready(on)
    on.mall["pills_30"].on_sale.seasons = [9]  # 沒上架的不列
    game.mall_buy("pills_5", "v1")
    game.mall_buy("pills_5", "v2")
    view = game.mall_view()
    assert view["balance"] == 4800 and view["card"] is None
    rows = {row["id"]: row for row in view["items"]}
    assert set(rows) == {"pills_5", "card_30", "card_1"}
    pills = rows["pills_5"]
    assert pills["can"] is False and "今天" in pills["why"] and pills["price"] == 100
    assert pills["effects"] == "回體丹 5 顆" and pills["kind_name"] == "消耗品" and "每天限 2 次" in pills["limit"]
    card = rows["card_30"]
    assert card["can"] is True and card["why"] is None and card["after"] == 4200
    game.mall_buy("card_30", "v3")
    assert game.mall_view()["card"] == {"until": mall.day_text(DAY0 + 29), "bonus": 1, "left": 30, "daily": None}


def test_records_show_the_ledger_with_running_balance(on):
    game = _ready(on)
    game.mall_buy("pills_5", "r1")
    records = game.mall_records()
    assert records["balance"] == 4900
    assert [(row["reason"], row["delta"], row["balance"]) for row in records["ledger"]] == [("購買", -100, 4900), ("封測發放", 5000, 5000)]
    assert [(p["item"], p["price"], p["refunded"]) for p in records["purchases"]] == [("回體丹五顆", 100, False)]
    assert "admin" not in records["ledger"][0]  # 玩家看自己的帳不寫經手的管理者


def test_records_also_say_the_season_time(on):
    """全面自檢 U-12（Joy 2026-10-31 照建議）：元寶是真錢，帳照舊寫現實時間，旁邊多寫季曆（跟江湖紀錄同一個寫法）。"""
    game = _ready(on)
    game.mall_buy("pills_5", "r1")
    row = game.mall_records()["ledger"][0]
    assert row["season_time"] == game.stamp(game.state.world.time)
    game.state.world.ended = True
    assert game.mall_records()["ledger"][0]["season_time"] is None  # 休季不寫


# ── 管理者工具 ───────────────────────────────────


def _admin(on, now=T0) -> Game:
    admin = _game(on, "管理者", now)
    admin.mark_seen(now)
    return admin


def test_reissue_and_revoke_are_logged_with_admin_and_note(on):
    player = _ready(on)
    admin = _admin(on)
    assert "只有管理者" in player.admin_mall_reissue("管理者", 100, "自己加", "ref-x")[0]
    assert "原因" in admin.admin_mall_reissue("沈浪", 100, "  ", "ref-a")[0]
    assert "江湖上沒有" in admin.admin_mall_reissue("查無此人", 100, "補償", "ref-b")[0]
    msgs = admin.admin_mall_reissue("沈浪", 300, "伺服器維修補償", "ref-c")
    assert "沈浪" in msgs[0] and _wallet(player).balance("沈浪") == 5300
    row = _rows(player)[0]
    assert (row.reason, row.delta, row.admin, row.note) == ("reissue", 300, "管理者", "伺服器維修補償")
    assert admin.admin_mall_reissue("沈浪", 300, "伺服器維修補償", "ref-c")  # 同一個編號重送不算兩次
    assert _wallet(player).balance("沈浪") == 5300
    assert "不能是負的" in admin.admin_mall_revoke("沈浪", 9999, "扣錯了", "ref-d")[0]
    admin.admin_mall_revoke("沈浪", 300, "發錯了", "ref-e")
    assert _wallet(player).balance("沈浪") == 5000 and _rows(player)[0].reason == "revoke"


def test_admin_finds_the_wallet_by_login_too(on):
    from tianxia.accounts import AccountStore

    player = _ready(on)
    store = AccountStore(player.world.db)
    store.register("shen_01", "secret-pw")
    store.bind_character("shen_01", "沈浪")
    admin = _admin(on)
    admin.admin_mall_reissue("shen_01", 10, "測試", "ref-login")
    assert _wallet(player).balance("沈浪") == 5010


def test_refund_returns_yuanbao_and_takes_back_pills_in_hand(on):
    player = _ready(on)
    player.mall_buy("pills_30", "f1")
    player.state.player.stamina_pills = 12  # 用掉了一大半
    open_characters().save(player.state)
    pid = _wallet(player).purchases("沈浪")[0].id
    admin = _admin(on)
    msgs = admin.admin_mall_refund("沈浪", pid, "買錯了")
    assert "500" in msgs[0]
    assert _wallet(player).balance("沈浪") == 5000
    assert open_characters().load("沈浪").player.stamina_pills == 0  # 手上的 12 顆收回，用掉的不追
    row = _rows(player)[0]
    assert (row.reason, row.delta, row.purchase_id, row.admin) == ("refund", 500, pid, "管理者")
    assert "退過" in admin.admin_mall_refund("沈浪", pid, "再退一次")[0]
    assert _wallet(player).balance("沈浪") == 5000


def test_refunded_purchase_frees_the_limit(on):
    player = _ready(on)
    player.mall_buy("pills_30", "l1")
    pid = _wallet(player).purchases("沈浪")[0].id
    _admin(on).admin_mall_refund("沈浪", pid, "買錯了")
    player.state = open_characters().load("沈浪")
    player.sync(T0)
    assert player.mall_buy("pills_30", "l2")[0].startswith("買下")


def test_refunding_a_card_takes_its_days_back(on):
    player = _ready(on)
    player.mall_buy("card_30", "k1")
    player.mall_buy("card_30", "k2")
    first = _wallet(player).purchases("沈浪")[-1].id
    _admin(on).admin_mall_refund("沈浪", first, "測試退卡")
    assert _wallet(player).card("沈浪", mall.CARD_KEY) == (DAY0, DAY0 + 30)


def test_admin_ledger_looks_the_same_for_bots(on):
    """管理者查帳：真人與假人回一樣的鍵、都沒有帳號字樣（看不出誰是假人）；不是管理者、查不到的回 refusal。"""
    real = _ready(on, "沈浪")
    bot = _game(on, "某假人")
    bot.state.player.bot = BotProfile(personality="普通", seed=1)
    bot.own_turn_checks()
    open_characters().save(real.state)
    open_characters().save(bot.state)
    admin = _admin(on)
    a, b = admin.admin_mall_ledger("沈浪"), admin.admin_mall_ledger("某假人")
    assert set(a) == set(b) == {"name", "balance", "card", "ledger", "purchases"}
    assert a["balance"] == b["balance"] == 5000
    assert a["ledger"][0]["reason"] == b["ledger"][0]["reason"] == "封測發放"
    assert "refusal" in real.admin_mall_ledger("某假人")
    assert "refusal" in admin.admin_mall_ledger("查無此人")


def test_buying_a_breakthrough_pill_puts_it_in_the_bag_and_a_refund_takes_back_the_unused(on):
    """萬寶閣的破境丹（Joy 2026-10-21「把破境丹也加入商城」）：legend_items 加上去；退款收回還在行囊裡的，服掉的不追。"""
    on.mall["legend_1"] = MallItem(id="legend_1", name="破境丹", price=150, kind="consumable", effects={"legend": 2})
    player = _ready(on)
    msgs = player.mall_buy("legend_1", "pj1")
    assert player.state.player.legend_items == 2 and _wallet(player).balance("沈浪") == 4850
    assert "破境丹 +2" in player.state.journal[0].changes and any("破境丹" in m for m in msgs)
    assert mall.effects_text(on.mall["legend_1"], on) == "破境丹 2 顆"
    player.state.player.legend_items = 1  # 服掉一顆
    open_characters().save(player.state)
    pid = _wallet(player).purchases("沈浪")[0].id
    _admin(on).admin_mall_refund("沈浪", pid, "買錯了")
    assert open_characters().load("沈浪").player.legend_items == 0 and _wallet(player).balance("沈浪") == 5000



def test_buying_reroll_slips_and_refunding_the_unused(on):
    """重悟帖（Joy 2026-10-21）：PlayerState.create_rerolls 加上去；退款收回還沒用的。"""
    on.mall["reroll_1"] = MallItem(id="reroll_1", name="重悟帖", price=50, kind="consumable", effects={"create_reroll": 2})
    player = _ready(on)
    player.mall_buy("reroll_1", "rr1")
    assert player.state.player.create_rerolls == 2 and "重悟帖 +2" in player.state.journal[0].changes
    assert mall.effects_text(on.mall["reroll_1"], on) == "自創重骰 2 次"
    player.state.player.create_rerolls = 1  # 用掉一張
    open_characters().save(player.state)
    pid = _wallet(player).purchases("沈浪")[0].id
    msgs = _admin(on).admin_mall_refund("沈浪", pid, "買錯了")
    assert "重悟帖收回 1 張" in msgs[0]
    assert open_characters().load("沈浪").player.create_rerolls == 0


def test_pills_and_reroll_slips_bought_with_ingots_survive_the_season_change(on):
    """花元寶買的破境丹、重悟帖換季不能就不見（Joy 2026-10-21「再研究一下有沒有什麼瑕疵」）：同回體丹，剩下的帶著走。"""
    player = _ready(on)
    p = player.state.player
    p.legend_items, p.create_rerolls, p.created_count = 2, 3, 4
    player._reset_player_for_new_season(p.season_number + 1)
    p = player.state.player
    assert (p.legend_items, p.create_rerolls, p.created_count) == (2, 3, 0)


def test_the_practice_row_sends_a_player_without_a_pill_to_the_mall(on):
    """到了極處、手上沒丹：修練頁那一格帶上萬寶閣賣破境丹那一件（Joy 2026-10-21「破境丹沒有可以引導他去商城」）。"""
    from test_cultivation import equip, kicker_art, ripen

    on.mall["legend_1"] = MallItem(id="legend_1", name="破境丹", price=150, kind="consumable", effects={"legend": 1})
    game = _ready(on)
    game.world.claim_skill_name(kicker_art())
    ripen(equip(game.state))
    row = lambda: next(r for r in skillview.art_rows(game.state, on, game.world) if r["id"] == "旋風腿")  # noqa: E731
    game.state.player.legend_items = 0
    assert row()["cultivate"]["shop"] == "legend_1"
    game.state.player.legend_items = 1
    assert row()["cultivate"]["shop"] is None  # 有丹就直接服
    game.state.player.legend_items = 0
    game.state.player.art_levels["旋風腿"] = 9
    assert row()["cultivate"]["shop"] is None  # 還沒到極處，買了也用不上
    game.state.player.art_levels["旋風腿"] = 10
    on.config.mall.enabled = False
    assert row()["cultivate"]["shop"] is None  # 商城關著


# ── 一次買好幾件（Joy 2026-10-22「商城買東西現在一次只能買一個很不人性化，應該可以一次買多個」）──


def test_buying_several_at_once_writes_one_purchase_each(on):
    on.mall["pills_9"] = MallItem(id="pills_9", name="回體丹一顆", price=10, kind="consumable", effects={"pills": 1})
    game = _ready(on)
    pills = game.state.player.stamina_pills
    msgs = game.mall_buy("pills_9", "many-0001", qty=4)
    assert game.state.player.stamina_pills == pills + 4 and _wallet(game).balance("沈浪") == 4960
    refs = sorted(p.ref for p in _wallet(game).purchases("沈浪"))
    assert refs == ["buy:沈浪:many-0001", "buy:沈浪:many-0001#2", "buy:沈浪:many-0001#3", "buy:沈浪:many-0001#4"]
    assert "×4" in msgs[0] and "元寶 -40" in msgs[0]
    entry = game.state.journal[0]
    assert entry.changes == ["元寶 -40", "回體丹 +4"]
    assert "已經買好" in game.mall_buy("pills_9", "many-0001", qty=4)[0]  # 重送同一個編號不再買
    assert game.state.player.stamina_pills == pills + 4


def test_quantity_is_clamped_to_what_the_limit_leaves(on):
    game = _ready(on)
    game.mall_buy("pills_5", "c1")
    msgs = game.mall_buy("pills_5", "c2", qty=5)  # 一天限 2 次，已經買了 1 次
    assert "限購只剩 1 件" in msgs[0] and _wallet(game).balance("沈浪") == 4800
    assert _wallet(game).count("沈浪", "pills_5", day=DAY0) == 2


def test_not_enough_for_all_buys_none(on):
    on.config.mall.beta_grant = 150
    game = _ready(on)
    msgs = game.mall_buy("pills_5", "short-1", qty=2)
    assert "元寶不夠" in msgs[0] and "×2 要 200" in msgs[0]
    assert _wallet(game).purchases("沈浪") == [] and _wallet(game).balance("沈浪") == 150


def test_view_says_how_many_can_be_bought(on):
    on.config.mall.beta_grant = 1000
    game = _ready(on)
    rows = {row["id"]: row for row in game.mall_view()["items"]}
    assert rows["pills_5"]["max"] == 2  # 限購一天 2 次
    assert rows["pills_30"]["max"] == 1  # 限購一季 1 次
    assert rows["card_1"]["max"] == 1  # 月卡一次一張
    on.mall["pills_9"] = MallItem(id="pills_9", name="回體丹一顆", price=300, kind="consumable", effects={"pills": 1})
    assert {row["id"]: row for row in game.mall_view()["items"]}["pills_9"]["max"] == 3  # 元寶只夠三件
