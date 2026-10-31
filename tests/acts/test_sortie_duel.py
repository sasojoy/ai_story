"""減法季批 3b-2：出陣約戰接進引擎（整合設計 4.3；計畫第四節 Task 3b-2、4.0 之三）。

兩個真人照伺服器的做法各自從資料庫重讀（duel_kit.do，同 tests/test_conquest_clash._do）。貼約戰扣一次出陣、卡在 main.sorties；
對面同區的人應戰（先按的那一位是守方，第二位回「已有人應戰」、什麼都不扣）；窗滿了伺服器排程（world_tick）或下一個同步的人結算，
兩邊各一份戰報與一則紀錄、進度照倍率動、輸的一方內傷 +10、冷卻多 30 分；沒人應戰由對面的假人應戰（戰報寫「某某應戰」、不寫假人），
連假人都沒有由守軍迎戰；季終作廢退次數退體力；子開關關著舊出陣一個字都不變。"""
from __future__ import annotations

import pytest

from duel_kit import FAR, LOC, MOVES, NOW, WINDOW, do, duel_content, duel_world, game_of, load, rounds_go, seat, text_of, tick
from tianxia import conquest, sortie_duel
from tianxia.characters import CharacterStore


def _go(c, world, name="甲", moves=MOVES, now=NOW):
    return do(c, world, name, lambda g: g.choose(f"sortie:go:{moves}"), now)


def _answer(c, world, name, duel_id, moves="固守,固守,固守", now=NOW + 60):
    return do(c, world, name, lambda g: g.choose(f"sortie:answer:{duel_id}:{moves}"), now)


def _only(world):
    duels = world.sortie_duels()
    assert len(duels) == 1, duels
    return next(iter(duels.values()))


def _pair(**kw):
    c = duel_content(**kw)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    return c, world


# ── 貼約戰 ──


def test_posting_spends_a_sortie_and_stamina_and_shows_the_cards():
    c, world = _pair()
    before = load(world, "甲").player.stamina
    msgs, game = _go(c, world)
    p = load(world, "甲").player
    cfg = c.config.sortie
    assert p.sorties_today == 1 and p.stamina == before - cfg.jianfa_stamina
    assert p.sortie_cooldown_until == NOW + cfg.cooldown_minutes * 60
    duel = _only(world)
    assert (duel.block, duel.attacker.name, duel.attacker.side, duel.attacker.moves) == (LOC, "甲", "guan", ["強攻", "固守", "奇襲"])
    assert duel.expires_at == NOW + WINDOW and duel.garrison is not None and duel.report["squad"] in c.squads
    assert load(world, "甲").journal[0].title == "約戰・汝南荒野"
    mine = game.sortie_cards()
    assert [(d["id"], d["role"], d["status"]) for d in mine] == [(duel.id, "mine", "open")]
    theirs = game_of(c, world, "乙").sortie_cards()
    assert theirs[0]["role"] == "answer" and theirs[0]["can_answer"] and theirs[0]["same_region"]
    assert theirs[0]["answers_left"] == cfg.answer_per_day


def test_the_action_row_cell_stays_act_train_and_opens_the_card_for_free():
    c, world = _pair()
    game = game_of(c, world, "甲")
    cell = next(o for o in game.options() if o.id == "act:train")
    assert cell.enabled and "出陣" in cell.label and f"體力 {c.config.sortie.jianfa_stamina}" in cell.label
    card = game.sortie_card()
    assert card["block"] == LOC and card["moves"] == ["強攻", "固守", "奇襲", "撤退"] and card["left_today"] == 2
    assert card["why_not"] == "" and set(card["gain"]) >= {"push", "contribution", "loot", "dividend", "order_match", "letter_gap"}
    stamina = game.state.player.stamina
    msgs = game.choose("act:train")
    assert msgs == [sortie_duel.PICK] and game.state.player.stamina == stamina and game.state.player.sorties_today == 0
    assert world.sortie_duels() == {}


def test_own_block_waits_for_the_other_side():
    c, world = _pair()
    season = world.get_season()
    own = next(b for b in conquest.blocks(c) if conquest.capturable(c, b) and conquest.holder(season, c, b) == "guan")
    seat(c, world, "甲", "guan", own)  # 官軍此刻佔著、搶得下來的一塊
    game = game_of(c, world, "甲")
    cell = next(o for o in game.options() if o.id == "act:train")
    assert not cell.enabled and cell.label == f"出陣（{sortie_duel.CELL_WAIT}）"  # 格子只放得下四個字（FB-670）
    assert game.sortie_card()["why_not"] == sortie_duel.WHY_WAIT
    assert "對面來約戰時在約戰卡上應戰" in game.action_notes(["act:train"])["act:train"]
    msgs, _ = _go(c, world)
    assert world.sortie_duels() == {} and load(world, "甲").player.sorties_today == 0


# 出陣約戰網頁（企劃者 2026-10-28 選丙）要的幾樣：這一塊歸誰、對面那一條是哪一軍、兩軍的名字、窗幾分鐘、應戰的體力——網頁不寫死


def test_the_card_names_the_holder_both_armies_the_window_and_the_answer_stamina():
    c, world = _pair()
    cfg = c.config.sortie
    card = game_of(c, world, "甲").sortie_card()
    assert card["holder"] is None  # 汝南荒野開季是中立地、還沒人佔
    assert card["sides"] == {"guan": c.scenario.faction_name("guan"), "huang": c.scenario.faction_name("huang")}
    assert card["sides"]["guan"] == "官軍" and card["sides"]["huang"] == "黃巾軍"  # 照劇本的陣營名
    assert card["bars"]["theirs_side"] == "huang" and game_of(c, world, "乙").sortie_card()["bars"]["theirs_side"] == "guan"
    assert card["window_minutes"] == cfg.window_minutes and card["answer_stamina"] == cfg.answer_stamina
    assert card["to_flip"] == 100 - card["bars"]["mine"] and card["gain"] is not None  # 不是自家的地方：照舊算自己那一條


def test_on_its_own_block_the_card_counts_the_other_sides_bar_and_offers_no_gain():
    c, world = _pair()
    season = world.get_season()
    own = next(b for b in conquest.blocks(c) if conquest.capturable(c, b) and conquest.holder(season, c, b) == "guan")
    seat(c, world, "甲", "guan", own)
    game = game_of(c, world, "甲")
    conquest._fight(game.state.world, c, own).bars.setdefault("huang", conquest.Bar()).value = 30.0  # 黃巾軍在官軍的地方推到 30
    card = game.sortie_card()
    assert card["holder"] == "guan" and card["why_not"] == sortie_duel.WHY_WAIT
    assert card["bars"] == {"mine": 0, "theirs": 30, "theirs_side": "huang"}
    assert card["to_flip"] == 70 and card["gain"] is None  # 對面離翻走這裡還差 70（以前寫自己那一條「還差 100」）；守就是應戰，沒有「贏了」
    game.state.player.sortie_cooldown_until = NOW + 600  # 冷卻中：按出陣寫「還要 N 分」，可是這裡照樣是自家的地方
    card = game.sortie_card()
    assert card["why_not"].startswith("還要") and card["gain"] is None and card["to_flip"] == 70


def test_the_cooldown_and_the_daily_cap_block_the_next_post():
    c, world = _pair()
    _go(c, world)
    msgs, _ = _go(c, world, now=NOW + 120)
    assert len(world.sortie_duels()) == 1 and "還要" in msgs[0]
    state = load(world, "甲")
    state.player.sorties_today = c.config.sortie.jianfa_per_day
    CharacterStore(world.db).save(state)
    msgs, _ = _go(c, world, now=NOW + 7200)
    assert len(world.sortie_duels()) == 1 and "明日 00:00" in msgs[0]


def test_a_ranger_cannot_post():
    c, world = _pair()
    seat(c, world, "丙", None)
    msgs, game = _go(c, world, "丙")
    assert world.sortie_duels() == {} and game.sortie_card() is None


# ── 應戰 ──


def test_two_humans_answer_at_once_only_the_first_one_gets_in():
    c, world = _pair()
    seat(c, world, "丙", "huang")
    _go(c, world)
    duel = _only(world)
    stamina = load(world, "丙").player.stamina
    first, _ = _answer(c, world, "乙", duel.id)
    second, _ = _answer(c, world, "丙", duel.id)
    duel = _only(world)
    assert duel.status == "answered" and duel.defender.name == "乙" and duel.defender.moves == ["固守"] * 3
    assert sortie_duel.WHY_TAKEN in second[0]
    p = load(world, "丙").player
    assert p.answers_today == 0 and p.stamina == stamina
    q = load(world, "乙").player
    assert q.answers_today == 1 and q.stamina == c.config.stamina_max - c.config.sortie.answer_stamina


def test_far_away_the_answer_button_is_grey_with_the_walk():
    c, world = _pair()
    seat(c, world, "乙", "huang", FAR)
    _go(c, world)
    card = game_of(c, world, "乙").sortie_cards()[0]
    assert not card["can_answer"] and not card["same_region"] and "才應得了戰" in card["why_not"]
    assert isinstance(card["travel_minutes"], int) and card["travel_minutes"] > 0
    msgs, _ = _answer(c, world, "乙", card["id"])
    assert _only(world).status == "open" and "才應得了戰" in msgs[0]


def test_every_duel_card_carries_both_army_names_and_the_answer_stamina_even_off_a_block():
    """FB-9003：站在不是區塊的地方（南華觀）沒有出陣前那張卡，網頁的陣營名與應戰的體力只能從約戰卡自己拿。"""
    c, world = _pair()
    cfg = c.config.sortie
    seat(c, world, "乙", "huang", "jade_cave")  # 潁川汝南的南華觀：不是區塊，跟約戰的汝南荒野同一個大區
    _go(c, world)
    game = game_of(c, world, "乙")
    assert game.sortie_card() is None
    card = game.sortie_cards()[0]
    assert card["can_answer"] and card["same_region"]
    assert card["sides"] == {"guan": "官軍", "huang": "黃巾軍"} and card["answer_stamina"] == cfg.answer_stamina
    mine = game_of(c, world, "甲").sortie_cards()[0]  # 自己貼的那一張、對面看的那一張一樣帶
    assert mine["sides"] == card["sides"] and mine["answer_stamina"] == cfg.answer_stamina


def test_a_live_duel_card_says_where_the_block_stands_for_the_side_that_posted(monkeypatch):
    """FB-9004：應戰卡寫的是這一場牽動的那一塊——約戰那一軍推到幾、離翻走還差多少、幾人在推；站在哪裡都一樣，打完的那一張不帶。"""
    c, world = _pair()
    seat(c, world, "乙", "huang", "jade_cave")  # 站的地方不是區塊
    _go(c, world)

    def push(g):  # 官軍在汝南荒野推到 30（約戰之外的人先推過）
        conquest._fight(g.state.world, c, LOC).bars.setdefault("guan", conquest.Bar()).value = 30.0

    do(c, world, "甲", push)
    card = game_of(c, world, "乙").sortie_cards()[0]
    assert card["holder"] is None and card["bars"] == {"mine": 0, "theirs": 30} and card["to_flip"] == 70 and card["foe_pushing"] == 0
    assert game_of(c, world, "甲").sortie_cards()[0]["bars"] == {"mine": 30, "theirs": 30}  # 自己貼的那一張：兩條都是官軍的
    seat(c, world, "乙", "huang", LOC)  # 站在那一塊上：數字一樣（以前借出陣卡寫自己這一邊）
    assert game_of(c, world, "乙").sortie_cards()[0]["bars"] == {"mine": 0, "theirs": 30}
    duel = _only(world)
    _answer(c, world, "乙", duel.id)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    settled = game_of(c, world, "乙", NOW + WINDOW + 2).sortie_cards()[0]
    assert settled["status"] == "settled" and {"bars", "to_flip", "holder", "foe_pushing"}.isdisjoint(settled)  # 打完了：只剩結果


def test_the_same_side_can_only_join():
    c, world = _pair()
    seat(c, world, "丙", "guan")
    _go(c, world)
    duel = _only(world)
    card = game_of(c, world, "丙").sortie_cards()[0]
    assert card["role"] == "join" and card["can_join"] and not card["can_answer"]
    msgs, _ = _answer(c, world, "丙", duel.id)
    assert _only(world).status == "open"
    msgs, _ = do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel.id}"), NOW + 30)
    duel = _only(world)
    assert duel.attacker.allies == ["丙"]
    p = load(world, "丙").player
    assert p.sorties_today == 1 and p.stamina == c.config.stamina_max - c.config.sortie.jianfa_stamina


# ── 結算 ──


def test_attacker_wins_the_tick_settles_pushes_and_both_get_a_report(monkeypatch):
    c, world = _pair()
    _go(c, world)
    duel = _only(world)
    _answer(c, world, "乙", duel.id)
    injury = load(world, "乙").player.member.injury
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW - 1)
    assert _only(world).status == "answered"  # 窗還沒滿
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.status == "settled" and duel.result.tier == "big" and duel.result.wins == 3
    season = world.get_season()
    expect = conquest.sortie_nominal(c, LOC, "attack") * 1.5 * sortie_duel.progress_scale(c)
    assert conquest.bar(season, LOC, "guan") == pytest.approx(expect)
    a, b = load(world, "甲"), load(world, "乙")
    assert a.battles[0].label == "約戰" and a.battles[0].kind == "sortie" and a.battles[0].tier == "大勝"
    assert len(a.battles[0].rounds) == 3 and b.battles[0].tier == "落敗"
    assert a.journal[0].title == "約戰・汝南荒野" and b.journal[0].title == "約戰・汝南荒野"
    assert a.player.contrib > 0 and b.player.contrib == 0
    cfg = c.config.sortie
    assert b.player.member.injury >= injury + cfg.lose_injury
    assert b.player.sortie_cooldown_until == pytest.approx(NOW + WINDOW + 1 + cfg.lose_cooldown_minutes * 60)
    assert b.player.answer_cooldown_until == pytest.approx(NOW + WINDOW + 1 + cfg.lose_cooldown_minutes * 60)
    assert "乙應戰" in text_of(a) and "甲" in text_of(b)


def test_the_loser_gets_ten_more_injury_on_top_of_the_rounds(monkeypatch):
    c, world = _pair()
    c.config.sortie.round_toll = {"win": 0.0, "draw": 0.0, "lose": 0.0}  # 回合不扣：內傷只剩輸的那一筆
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    a0, b0 = load(world, "甲").player.member.injury, load(world, "乙").player.member.injury
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    assert load(world, "乙").player.member.injury == pytest.approx(b0 + c.config.sortie.lose_injury)
    assert load(world, "甲").player.member.injury == pytest.approx(a0)
    assert "內傷 +10" in load(world, "乙").battles[0].changes


def test_defender_wins_pulls_the_attackers_bar(monkeypatch):
    c, world = _pair()
    season = world.get_season()
    conquest.push(season, c, LOC, "guan", "甲", 30.0, "attack")
    world.save_season(season)
    _go(c, world)
    duel = _only(world)
    _answer(c, world, "乙", duel.id)
    rounds_go(monkeypatch, "落敗")
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.result.tier == "lose" and duel.result.defender_tier == "big"
    pulled = conquest.sortie_nominal(c, LOC, "attack") * 1.5 * sortie_duel.progress_scale(c)
    assert conquest.bar(world.get_season(), LOC, "guan") == pytest.approx(30.0 - pulled)
    a, b = load(world, "甲"), load(world, "乙")
    assert b.player.contrib > 0 and a.battles[0].tier == "落敗" and b.battles[0].tier == "大勝"
    assert a.player.sortie_cooldown_until == pytest.approx(NOW + 3600 + c.config.sortie.lose_cooldown_minutes * 60)
    assert b.player.sortie_cooldown_until is None


def test_holding_by_answering_counts_for_the_defend_order_and_the_card_says_so(monkeypatch):
    """約戰開著時守城是應戰守住（巡哨、傳道不再算）：守方贏了照拉之前的清單記守城，軍令卡寫「去應戰、守住」。"""
    from tianxia import atlas, orders
    from tianxia.state import Order

    c, world = _pair()
    seat(c, world, "甲", "guan", "zhuo_county")  # 涿郡：官軍的，黃巾開季就碰得到
    seat(c, world, "乙", "huang", "zhuo_county")
    g = game_of(c, world, "甲")
    w = g.state.world
    order = Order(id="t:guan:defend", template="defend", faction="guan", week=orders.period_of(g.state, c),
                  front=conquest.line_of(w, c, "zhuo_county"), quota=99, text="（測試）")
    w.orders = [order]
    conquest.push(w, c, "zhuo_county", "huang", "黃巾兵", 20.0, "attack")
    g._save_season()
    assert orders.defend_places(c, w, order) == ["zhuo_county"]
    assert "去應戰、守住" in atlas.order_how(g.state, c, order)
    _go(c, world, "乙")
    _answer(c, world, "甲", _only(world).id)
    rounds_go(monkeypatch, "落敗")
    tick(c, world, NOW + WINDOW + 1)
    done = next(o for o in world.get_season().orders if o.id == order.id)
    assert done.progress.get("甲") == 1


@pytest.mark.parametrize(("tier", "winner"), [("大勝", "甲"), ("落敗", "乙")])
def test_duel_exp_is_battle_exp_past_level_45(monkeypatch, tier, winner):
    """約戰（攻方 sortie）與應戰（answer）的經驗都是仗（growth.exp_source → battle，批 2 的第三道閘）：45 級以後照樣算經驗、不換心得。"""
    from tianxia import growth
    from tianxia.rules import jianfa

    c, world = _pair()
    cap = c.config.jianfa.drill_level_cap
    for name in ("甲", "乙"):
        state = load(world, name)
        state.player.member.level, state.player.member.exp = cap, 0
        CharacterStore(world.db).save(state)
    assert jianfa(c, world.get_season(), "drill_gates")
    assert growth.exp_source("sortie") == growth.exp_source("answer") == growth.BATTLE
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, tier)
    tick(c, world, NOW + WINDOW + 1)
    won = load(world, winner)
    assert won.battles[0].exp > 0 and won.player.member.exp == won.battles[0].exp


def test_the_duel_scale_replaces_progress_scale_only_for_duels(monkeypatch):
    """約戰自己的倍數（Config.sortie.duel_progress_scale）：設了照它、沒設照 progress_scale；舊出陣讀的 progress_scale 不動。"""
    c, world = _pair()
    c.config.sortie.duel_progress_scale = 7.0
    assert sortie_duel.progress_scale(c) == 7.0
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    assert conquest.bar(world.get_season(), LOC, "guan") == pytest.approx(conquest.sortie_nominal(c, LOC, "attack") * 1.5 * 7.0)
    c.config.sortie.duel_progress_scale = None
    assert sortie_duel.progress_scale(c) == c.config.conquest.progress_scale


def test_a_draw_pushes_a_little(monkeypatch):
    c, world = _pair()
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, "僵持")
    tick(c, world, NOW + WINDOW + 1)
    expect = conquest.sortie_nominal(c, LOC, "attack") * 0.4 * sortie_duel.progress_scale(c)
    assert conquest.bar(world.get_season(), LOC, "guan") == pytest.approx(expect)


def test_nobody_answers_a_bot_on_the_other_side_answers(monkeypatch):
    c, world = _pair()
    seat(c, world, "乙", "huang", FAR)  # 真人在別區，不補位
    seat(c, world, "丁", "huang", LOC, bot=True)
    _go(c, world)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.defender.name == "丁" and not duel.defender.garrison
    assert duel.opened_at <= duel.defender.sealed_at <= duel.expires_at
    a, d = load(world, "甲"), load(world, "丁")
    assert "丁應戰" in text_of(a)
    assert d.player.answers_today == 1 and d.battles[0].label == "約戰"
    for word in ("假人", "機器人", "沒有人防守", "bot"):
        assert word not in text_of(a) and word not in text_of(d)
    assert load(world, "乙").battles == []  # 真人不補位


def test_a_gentry_bot_leaning_on_the_other_army_fills_in(monkeypatch):
    """豪強的假人照依附的那一軍補位（存檔不帶季：判依附哪一軍要接上手上這一份季，不然豪強一個都補不上）。"""
    c, world = _pair()
    seat(c, world, "乙", "huang", FAR)
    seat(c, world, "丁", None, LOC, bot=True, faction="haoqiang", ally="huang")
    _go(c, world)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.defender.name == "丁" and duel.defender.side == "huang"
    assert "丁應戰" in text_of(load(world, "甲"))


def test_no_one_at_all_the_garrison_answers(monkeypatch):
    c, world = _pair()
    seat(c, world, "乙", "huang", FAR)
    _go(c, world)
    rounds_go(monkeypatch, "落敗")
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.status == "settled" and duel.defender.garrison
    a = load(world, "甲")
    assert "守軍迎戰" in text_of(a) and "沒有人防守" not in text_of(a)
    card = game_of(c, world, "甲", NOW + WINDOW + 2).sortie_cards()[0]
    assert card["defender"] == sortie_duel.GARRISON and card["status"] == "settled"


def test_an_ally_who_joined_adds_focus_and_gets_the_credit(monkeypatch):
    c, world = _pair()
    seat(c, world, "丙", "guan")
    _go(c, world)
    duel = _only(world)
    do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel.id}"), NOW + 30)
    _answer(c, world, "乙", duel.id)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    cfg = c.config.conquest
    base = conquest.sortie_nominal(c, LOC, "attack") * 1.5 * sortie_duel.progress_scale(c)
    assert conquest.bar(world.get_season(), LOC, "guan") == pytest.approx(base * (1 + cfg.focus_step))
    ally = load(world, "丙")
    assert ally.player.contrib > 0 and ally.battles[0].label == "約戰"


def test_with_the_scheduler_off_the_next_sync_settles_it(monkeypatch):
    c, world = _pair()
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, "大勝")
    do(c, world, "甲", lambda g: [], NOW + WINDOW + 5, sync=True)
    assert _only(world).status == "settled"
    assert load(world, "甲").battles[0].label == "約戰" and load(world, "乙").battles[0].label == "約戰"


def test_two_programs_taking_turns_settle_it_once(monkeypatch):
    c, world = _pair()
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    bar = conquest.bar(world.get_season(), LOC, "guan")
    tick(c, world, NOW + WINDOW + 2)
    do(c, world, "乙", lambda g: [], NOW + WINDOW + 3, sync=True)
    do(c, world, "甲", lambda g: [], NOW + WINDOW + 4, sync=True)
    assert conquest.bar(world.get_season(), LOC, "guan") == pytest.approx(bar)
    assert [r.label for r in load(world, "甲").battles] == ["約戰"]
    assert [r.label for r in load(world, "乙").battles] == ["約戰"]


def test_the_season_ending_voids_it_and_refunds(monkeypatch):
    c, world = _pair()
    _go(c, world)
    _answer(c, world, "乙", _only(world).id)
    season = world.get_season()
    season.ended = True
    world.save_season(season)
    tick(c, world, NOW + 30)
    duel = _only(world)
    assert duel.status == "void"
    a, b = load(world, "甲").player, load(world, "乙").player
    assert a.sorties_today == 0 and a.stamina == c.config.stamina_max
    assert b.answers_today == 0 and b.stamina == c.config.stamina_max


# ── 開關關著 ──


def test_switched_off_the_old_sortie_stays_and_sortie_moves_are_not_on_the_menu():
    c = duel_content(off=True)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    game = game_of(c, world, "甲")
    cell = next(o for o in game.options() if o.id == "act:train")
    assert cell.label.startswith("出陣・攻") and game.sortie_card() is None and game.sortie_cards() is None
    msgs = game.choose(f"sortie:go:{MOVES}")
    assert msgs == ["（此刻無法這麼做。）"] and world.sortie_duels() == {}
