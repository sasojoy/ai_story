"""fix-1009（PM 2026-10-08/09）：玩家自己選了就要付錢的選項，錢不夠就不出現。

apply_effect 把銀兩夾在 0：沒錢的人照樣按得下「買下」「塞錢了事」「乖乖交錢」，少付了照樣拿到全部的效果。做法照裁決 E5.1
（「給他。」50）與 fix-1008 項目一（「塞錢給黃門」20）：選項加 "condition": {"min_stats": {"silver": 價錢}}，價錢就是那個選項
effect.stats.silver 扣的數，錢不夠時選項不出現。只加條件，選項與結果的字是 joy 的、不動。

這個檔守住以後：真實內容裡每一個「選了、效果就扣銀兩」的選項（沒有檢定、也沒有戰鬥：選了就一定付），都要帶不低於價錢的
min_stats.silver（慣例是剛好等於價錢）。懲罰從結構上認：檢定失敗、打輸（fail_effect）、隨口應對失敗都不算，照舊夾在 0。
其餘不擋的（檢定成功或打贏也要付錢的）列在 NOT_GATED，一則一句理由；joy 新寫的付錢選項忘了擋，這裡就紅。

釘住的內容：content/events/ 底下有付錢選項的檔（scripts/test_for.py 靠檔名挑到這裡）：explore_luoyang.json、
explore_nanyang.json、explore_runan.json、explore_yingchuan.json、explore_youzhou.json、general.json、luoyang.json、marks.json、
social_nanyang_yingchuan.json、social_north.json、social_runan.json、tales.json、train_aftermath.json、treasure.json、trend.json、
以及原本就擋好的 foreshadow_prep.json、jizhou.json、nanyang.json、promotion.json、ranger.json、youzhou.json。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import bot
from tianxia.engine import FREE_TEXT_OPTION, Game
from tianxia.models import Check, Choice, Condition, Content, Effect, Event, FreeTextChoice

# 效果（檢定成功、打贏）也扣銀兩、但照規矩不擋的選項：（事件 id, 選項序號）→（價錢, 理由）。這幾則照舊夾在 0。
# 「選了就一定付」的選項不該出現在這裡：要嘛擋，要嘛由企劃者裁決之後寫上理由。
NOT_GATED: dict[tuple[str, int], tuple[int, str]] = {
    ("jz_hz_rentdebt", 1): (20, "檢定選項，成功、失敗都付 20：PM（fix-1009 brief 規則 2）明定不擋"),
    ("ny_yu_ropetoll", 2): (5, "講價的檢定，成功付 5、失敗付 20：PM（fix-1009 brief 規則 2）明定不擋"),
    ("yz_yan_cold_night", 1): (5, "檢定選項，成功才分出 5 兩的乾糧、失敗不花錢：比照上面兩則不擋（fix-1009 裁決）"),
}

# 這份計畫要擋、還沒擋的（逐檔擋完就從這裡拿掉；全部擋完這個清單就刪掉）
TO_GATE: set[tuple[str, int]] = {
    ("ly_road_checkpoint", 2), ("ny_wan_gatecheck", 2), ("ny_yu_net", 2), ("ny_yu_ropetoll", 3), ("rn_mkt_rice", 2),
    ("yc_city_petition", 2), ("yc_wilds_toll", 3), ("yz_market_wrist", 2), ("yz_market_fushui", 2), ("yz_lou_sandals", 2),
    ("yz_juma_toll", 3), ("yz_juma_ironsand", 2),
    ("luoyang_beimang_search", 0),
    ("mk_yingshui_bareshore", 2), ("mk_mengjin_ferrymen", 2), ("mk_yu_fishmarket", 2), ("mk_yu_tollhut", 3),
    ("mk_nyroad_ambush", 3),
    ("sc_xy_wedding", 2), ("sc_xy_register", 2), ("sc_zhuo_wedding", 2), ("sc_rn_mourning", 2), ("sc_rnac_recommend", 2),
    ("sc_rnmk_measure", 2), ("sc_rnmk_wedding", 2), ("sc_qiao_liubo", 2),
    ("tale_yc_riverbank", 0), ("tale_wan_road", 0), ("tale_rnmk_ford", 0),
    ("train_campfire", 1), ("yuxi_antique", 0), ("trend_baima_ford_panic", 2),
}


def price_of(effect: Effect) -> int:
    """這個效果扣幾兩（沒扣、或是給錢都是 0）。"""
    return max(0, -effect.stats.get("silver", 0))


def paying_choices(content: Content) -> list[tuple[str, int | str, int, Choice | None]]:
    """每一個「選了，效果就可能扣銀兩」的地方：（事件 id, 選項序號或 "free", 價錢, 選項）。
    只看 effect（沒有擲骰時、檢定成功、打贏）：fail_effect 是檢定失敗或打輸的懲罰，結構上就不算；
    沒有檢定也沒有戰鬥的選項本來就走不到 fail_effect。隨口應對成功也扣錢的話一樣列出來（它沒有條件可加，只能進白名單）。"""
    out: list[tuple[str, int | str, int, Choice | None]] = []
    for event in content.events.values():
        for i, choice in enumerate(event.choices):
            price = price_of(choice.effect)
            if price:
                out.append((event.id, i, price, choice))
        if event.free_text is not None and price_of(event.free_text.effect):
            out.append((event.id, "free", price_of(event.free_text.effect), None))
    return out


def ungated(content: Content, allowed: dict | None = None) -> list[tuple[str, int | str, int, int | None]]:
    """付錢的選項裡，沒有擋（或擋得比價錢低）、也不在白名單上的：（事件 id, 選項, 價錢, 現在的門檻）。"""
    allowed = NOT_GATED if allowed is None else allowed
    out = []
    for eid, i, price, choice in paying_choices(content):
        if (eid, i) in allowed:
            continue
        gate = choice.condition.min_stats.get("silver") if choice is not None else None
        if gate is None or gate < price:
            out.append((eid, i, price, gate))
    return out


def gated(content: Content) -> list[tuple[str, int, int]]:
    """擋好的付錢選項：（事件 id, 選項序號, 價錢）。"""
    return [
        (eid, i, price) for eid, i, price, choice in paying_choices(content)
        if choice is not None and choice.condition.min_stats.get("silver", -1) >= price
    ]


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _game(content: Content) -> Game:
    game = Game.new(content, "甲", rng=random.Random(0))
    game.client = None  # 沒有任何地方會叫模型
    return game


def _scene(game: Game, event_id: str, silver: int) -> list[str]:
    """把這則事件端到玩家眼前、身上剛好 silver 兩；回傳選單上的選項 id。"""
    game.state.pending_event = event_id
    game.state.player.stats["silver"] = silver
    return [o.id for o in game.options(odds=False)]


# ── 守門：真實內容 ─────────────────────────────


def test_every_paying_choice_is_gated_or_whitelisted(real):
    """選了就付錢的選項都要擋（min_stats.silver ≥ 價錢）；不擋的要在 NOT_GATED 寫理由。新寫的付錢選項忘了擋，這裡就紅。"""
    assert {(eid, i) for eid, i, _, _ in ungated(real)} == TO_GATE


def test_the_whitelist_is_not_stale(real):
    """白名單上的每一則都還在、價錢對得上、真的沒擋（擋了就從白名單拿掉）。"""
    found = {(eid, i): (price, choice) for eid, i, price, choice in paying_choices(real)}
    for key, (price, reason) in NOT_GATED.items():
        assert key in found, f"{key} 已經不扣錢或不在了：從 NOT_GATED 拿掉"
        assert found[key][0] == price, f"{key} 的價錢變了：{found[key][0]}（白名單寫 {price}）"
        assert "silver" not in found[key][1].condition.min_stats, f"{key} 已經擋了：從 NOT_GATED 拿掉"
        assert reason.strip()


def test_a_gated_scene_never_loses_all_its_options(real):
    """沒錢的人照樣有路可走：每一則有付錢選項的事件，都至少留一個沒有任何條件的選項（content.validate 對全部事件也要求這條）。"""
    events = {eid for eid, _, _ in gated(real)}
    assert events
    for eid in sorted(events):
        assert any(ch.condition == Condition() for ch in real.events[eid].choices), eid


def test_a_player_short_of_the_price_does_not_see_it(real):
    """每一個擋好的選項：差一兩就不出現、從舊的選單硬按也被拒絕（什麼都沒扣）；錢剛好夠就出現，付完剛好歸零。"""
    game = _game(real)
    problems = []
    for eid, i, price in gated(real):
        option = f"choice:{i}"
        if option in _scene(game, eid, price - 1):
            problems.append(f"{eid} {option}：差一兩還看得到")
        if game.choose(option) != ["（此刻無法這麼做。）"] or game.state.player.stats["silver"] != price - 1:
            problems.append(f"{eid} {option}：差一兩硬按沒被拒絕")
        if game.state.pending_event != eid:
            problems.append(f"{eid} {option}：被拒絕之後事件不見了")
        if option not in _scene(game, eid, price):
            problems.append(f"{eid} {option}：錢剛好夠卻看不到")
        game.choose(option)
        if game.state.player.stats["silver"] != 0:
            problems.append(f"{eid} {option}：付了 {price} 兩之後剩 {game.state.player.stats['silver']}")
    assert not problems, "\n".join(problems)


def test_a_broke_bot_always_has_something_to_press(real):
    """機器人只看選單上給的選項（bot.pick）；「沒有任何可按的選項」是整季模擬推進時間的訊號。身上一兩都沒有時，
    每一則有付錢選項的事件都還有選項可按、按的是事件的選項，而且不是付錢的那一個。"""
    game = _game(real)
    rng = random.Random(0)
    priced = {(eid, i) for eid, i, _ in gated(real)}
    for eid in sorted({eid for eid, _ in priced}):
        ids = _scene(game, eid, 0)
        assert not any((eid, int(o.partition(":")[2])) in priced for o in ids if o.startswith("choice:") and o != FREE_TEXT_OPTION), eid
        picked = bot.pick(game, game.options(odds=False), rng)
        assert picked is not None and picked.startswith("choice:") and picked != FREE_TEXT_OPTION, (eid, picked)


# ── 守門本身會不會紅（突變）：拿掉一個條件、新寫一個忘了擋的付錢選項 ─────────────────────────────


def test_the_guard_catches_a_removed_gate(real):
    eid, i, price = next((e, i, p) for e, i, p in gated(real) if (e, i) not in TO_GATE)
    real.events[eid].choices[i].condition = Condition()
    assert (eid, i, price, None) in ungated(real)


def test_the_guard_catches_a_gate_below_the_price(real):
    eid, i, price = next((e, i, p) for e, i, p in gated(real) if (e, i) not in TO_GATE)
    real.events[eid].choices[i].condition = Condition(min_stats={"silver": price - 1})
    assert (eid, i, price, price - 1) in ungated(real)


def test_the_guard_catches_a_new_ungated_paying_choice(real):
    """joy 新寫一則事件、付錢的選項忘了擋：紅。失敗才扣錢（懲罰）的選項不算；擋好的不算。"""
    real.events["fx_new"] = Event(
        id="fx_new", title="新事件", text="……",
        choices=[
            Choice(text="付錢", effect=Effect(text="付了。", stats={"silver": -12})),
            Choice(text="擋好的付錢", condition=Condition(min_stats={"silver": 7}), effect=Effect(stats={"silver": -7})),
            Choice(text="試試看", check=Check(stat="wis", difficulty=5), fail_effect=Effect(stats={"silver": -9})),
            Choice(text="走開"),
        ],
        free_text=FreeTextChoice(prompt="另想法子", stat="wis", effect=Effect(stats={"silver": -3}),
                                 fail_effect=Effect(stats={"silver": -8})),
    )
    found = [row for row in ungated(real) if row[0] == "fx_new"]
    assert found == [("fx_new", 0, 12, None), ("fx_new", "free", 3, None)]


def test_the_guard_catches_a_paying_check_or_fight_that_is_not_whitelisted(real):
    """檢定成功、打贏也扣錢的選項：沒擋又不在白名單上，紅（白名單是一則一則寫理由的，不是整類放行）。"""
    real.events["fx_new"] = Event(
        id="fx_new", title="新事件", text="……",
        choices=[
            Choice(text="講價", check=Check(stat="wis", difficulty=5), effect=Effect(stats={"silver": -4})),
            Choice(text="打過去", combat=next(iter(real.squads)), effect=Effect(stats={"silver": -6})),
            Choice(text="走開"),
        ],
    )
    assert [row for row in ungated(real) if row[0] == "fx_new"] == [("fx_new", 0, 4, None), ("fx_new", 1, 6, None)]
    assert [row for row in ungated(real, allowed={}) if row[0] in {k[0] for k in NOT_GATED}]  # 拿掉白名單，那幾則就紅
