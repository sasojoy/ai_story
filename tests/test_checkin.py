"""正式季整合第 7 批：每日簽到與回體丹（設計 6.2～6.4、8.1；12.3 第 27、43 條）。只在 21 天季（season21 設定），週末與 14 天
一個字都不變。第 N 天照開季那一天（台灣日）起算，那天沒上線就錯過。"""
from __future__ import annotations

import random

from conftest import real_content
from jianfa_kit import no_jianfa

from tianxia import checkin, opening
from tianxia.content import _material_sources
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED = MON + 2 * DAY


def _game(profile="season21", open_at=MON + 10 * HOUR, *, prologue=False, setup=None):
    c = real_content(profile)
    c.config.admins = ["沈浪"]
    c.config.train_event_chance = 0.0
    if setup is not None:
        setup(c)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, open_at)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store, prologue=prologue)
    game.client = None
    if not prologue:
        game.state.player.tutorial_step = len(c.tutorial.steps)
    _at(game, open_at)
    return game


def _at(game, now):
    """照伺服器：每一下先補算賽季（暫停中不推），再同步這個角色。"""
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


def _day(game, n, open_day=MON):
    """移到開季那一天起算的第 n 天 10:00。"""
    _at(game, open_day + (n - 1) * DAY + 10 * HOUR)


def test_reward_table():
    c = real_content("season21")
    assert checkin.gifts(c, 3) == ("pills",)
    assert checkin.gifts(c, 6) == ("pills", "tier4")
    assert checkin.gifts(c, 13) == ("tier4",) and checkin.gifts(c, 20) == ("tier4",)
    assert checkin.gifts(c, 21) == ("pills",)  # 12.3 第 27 條：丹的日子只給丹
    for day in (1, 4, 7, 10, 14, 17):
        assert checkin.gifts(c, day) == ("silver",), day
    for day in (2, 5, 8, 11, 16, 19):
        assert checkin.gifts(c, day) == ("material",), day


def test_claim_pills_day():
    """每天第一次同步自動領（Joy 2026-10-24 挑江湖頁乙案：簽到不放鈕，Game._auto_checkin）：第 3 天的丹不必按，同步到就進袋、
    寫一則「簽到」江湖紀錄；再按「簽到」只回領過了。開季那一天建角色的第一次同步就領了第 1 天的份。"""
    game = _game()
    p = game.state.player
    before = p.stamina_pills
    _day(game, 3)
    assert p.stamina_pills == before + 2
    assert p.checkin_days == [1, 3]
    entry = next(e for e in game.state.journal if e.title == "簽到")
    assert any("回體丹 +2" in c for c in entry.changes)
    assert game.check_in() == [checkin.TODAY_DONE]


def test_claim_silver_and_material_days():
    game = _game()  # 開季那一天建角色、第一次同步：第 1 天的 30 兩自動領了
    p = game.state.player
    assert p.checkin_days == [1]
    assert any("銀兩 +30" in c for e in game.state.journal if e.title == "簽到" for c in e.changes)
    bag = dict(p.materials)
    _day(game, 2)  # 第 2 天：一階素材，同步到就領
    gained = {k: v - bag.get(k, 0) for k, v in p.materials.items() if v != bag.get(k, 0)}
    assert len(gained) == 1 and list(gained.values()) == [1]
    assert game.content.materials[next(iter(gained))].tier == 1
    assert p.checkin_days == [1, 2]


def test_tier4_day_needs_a_known_attribute():
    game = _game()
    p = game.state.player
    _day(game, 6)
    pills = p.stamina_pills
    for bad in ("", "陰", "胡說"):
        msgs = game.check_in(bad)
        assert msgs and p.stamina_pills == pills and "gang_4" not in p.materials and p.checkin_days == [1]  # 要挑的日子不自動領
    game.check_in("剛")
    assert p.stamina_pills == pills + 2 and p.materials.get("gang_4") == 1 and p.checkin_days == [1, 6]


def test_tier4_only_days():
    game = _game()
    p = game.state.player
    _day(game, 13)
    pills, silver = p.stamina_pills, p.stats["silver"]
    game.check_in("快")
    assert p.materials.get("kuai_4") == 1 and p.stamina_pills == pills and p.stats["silver"] == silver


def test_second_claim_same_day_is_refused():
    game = _game()
    p = game.state.player
    _day(game, 3)  # 同步時自動領了
    pills = p.stamina_pills
    msgs = game.check_in()
    assert msgs == [checkin.TODAY_DONE]
    _day(game, 3)  # 同一天再同步一次：不會再領
    assert p.stamina_pills == pills and p.checkin_days == [1, 3]


def test_missed_day_is_lost():
    game = _game()
    _day(game, 3)  # 第 2 天沒上線：那一份沒了
    week = game.status_data()["checkin"]["week"]
    assert [d["day"] for d in week] == [1, 2, 3, 4, 5, 6, 7]
    assert week[0]["state"] == "got" and week[1]["state"] == "miss" and week[2]["state"] == "today" and week[3]["state"] == "future"
    _day(game, 4)
    week = game.status_data()["checkin"]["week"]
    assert week[1]["state"] == "miss" and week[2]["state"] == "got" and week[3]["state"] == "today"


def test_day_counts_from_the_opening_day():
    game = _game(open_at=WED + 10 * HOUR)  # 週三開季（12.3 第 43 條）
    c = game.content
    assert checkin.day_of(c, game.state.world) == 1
    _at(game, MON + 7 * DAY + 10 * HOUR)  # 隔週一（同步之後 state.world 換成新讀的那一份）
    assert checkin.day_of(c, game.state.world) == 6
    assert checkin.last_day(c, game.state.world) == 19  # 季末照舊是第 4 週週一 00:00：只有 19 天


def test_day_counts_from_the_opening_day_after_a_pause():
    game = _game(open_at=WED + 10 * HOUR)
    pause = WED + 11 * HOUR
    _at(game, pause)
    game.admin_pause_clock(pause)
    resume = pause + 2 * DAY  # 週五 11:00 繼續
    _at(game, resume)
    game.admin_resume_clock(resume)
    _at(game, resume + HOUR)
    assert checkin.day_of(game.content, game.state.world) == 3


def test_view_last_day_has_no_next():
    game = _game()
    _day(game, 6)
    view = game.status_data()["checkin"]
    assert view["day"] == 6 and not view["done"]
    assert view["next"] == "明日 30 兩"
    assert "四階" in view["step"]
    assert [x["attribute"] for x in view["pick"]] == ["剛", "柔", "快", "慢"]
    assert view["week"][5]["four"]
    _day(game, 21)
    view = game.status_data()["checkin"]
    assert view["next"] is None and view["pick"] is None
    assert [d["day"] for d in view["week"]] == [15, 16, 17, 18, 19, 20, 21]


def test_done_line_names_what_was_picked():
    """FB-438：領過之後攤開那一句照實際拿到的寫（挑到的四階、那一天的一階素材），不寫「自己挑的四階料一個」。"""
    game = _game()
    _day(game, 6)
    game.check_in("快")
    assert game.status_data()["checkin"]["step"] == "今天的份領過了：回體丹 2 顆＋奔雷角一個。"
    p = game.state.player
    assert type(p).model_validate_json(p.model_dump_json()).checkin_picks == {6: "kuai_4"}  # 存檔讀回來第幾天還是整數
    _day(game, 8)
    game.check_in()
    p = game.state.player
    name = game.content.materials[checkin.material_for(game.content, p.name, p.season_number, 8)].name
    assert game.status_data()["checkin"]["step"] == f"今天的份領過了：{name}一個。"
    _day(game, 13)
    game.check_in("慢")
    assert game.status_data()["checkin"]["step"] == "今天的份領過了：歸墟壤一個。"


def test_short_last_week_after_a_wednesday_opening():
    game = _game(open_at=WED + 10 * HOUR)
    _day(game, 19, open_day=WED)
    view = game.status_data()["checkin"]
    assert [d["day"] for d in view["week"]] == [15, 16, 17, 18, 19]
    assert view["next"] is None


def test_off_after_the_season_ends():
    game = _game()
    game.admin_end_season(MON + 11 * HOUR)
    _at(game, MON + 12 * HOUR)
    assert "checkin" not in game.status_data()
    assert game.check_in() == [checkin.OFF]


def test_no_card_past_the_last_day():
    """管理者把季末往後排、季還在跑：第 21 天之後沒有表上的份，不畫小標、按了也只回一句。"""
    game = _game()
    _day(game, 21)
    game.state.world.time += DAY  # 第 22 天（季沒收）
    assert not game.state.world.ended
    assert "checkin" not in game.status_data()
    assert game.check_in() == [checkin.OFF]


def test_prologue_cannot_check_in():
    game = _game(prologue=True, setup=lambda c: setattr(c.config.jianfa, "enabled", False))  # 減法季關著：草廬序章
    pills = game.state.player.stamina_pills
    assert "checkin" not in game.status_data()
    assert game.check_in() == [checkin.HUT]
    assert game.state.player.stamina_pills == pills and game.state.player.checkin_days == []


def test_the_opening_gate_holds_the_check_in_until_the_choice_is_made():
    """開局第一分鐘（批 7 前半）：站在城門口三選一還沒選，簽到不畫、按了只回一句；選完下一次同步自動領、寫進紀錄（不當第一張卡）。"""
    game = _game(prologue=True)
    p = game.state.player
    assert opening.pending(game.state, game.content)
    pills, silver = p.stamina_pills, p.stats["silver"]
    assert "checkin" not in game.status_data()
    assert game.check_in() == [opening.GATE]
    assert p.stamina_pills == pills and p.stats["silver"] == silver and p.checkin_days == []
    game.choose("choice:0")
    game.sync(game.now + 60)
    assert p.checkin_days == [1] and p.stats["silver"] > silver  # 第 1 天的 30 兩不必挑：選完同步到就領了、寫進紀錄
    assert game.status_data()["checkin"] is not None


def test_four_tiers_off():
    game = _game(setup=lambda c: setattr(c.config.four_tiers, "enabled", False))
    p = game.state.player
    pills, silver = p.stamina_pills, p.stats["silver"]
    _day(game, 6)  # 四階關著：第 6 天只有丹、不必挑，同步到就領
    assert p.stamina_pills == pills + 2 and p.stats["silver"] == silver
    _day(game, 13)
    assert p.stats["silver"] == silver + 30 and not any(k.endswith("_4") for k in p.materials)


def _explore(game, mode):
    """按探索的那一種（explore:gather|seek|practice），體力先補滿。"""
    game.state.player.stamina = game.content.config.stamina_max
    ids = {o.id for o in game.options() if o.enabled}
    assert f"explore:{mode}" in ids, sorted(ids)
    return game.choose(f"explore:{mode}")


def _sure_drop(c):
    """一定掉丹；測的是探索三選一的找素材、練功、找事件（減法季探索一顆開著時選單上沒有這幾顆），減法季關掉（jianfa_kit.no_jianfa）。"""
    c.config.checkin.pill_drop = 1.0
    no_jianfa(c)


def test_gather_and_practice_drop_a_pill():
    game = _game(setup=_sure_drop)
    p = game.state.player
    pills = p.stamina_pills
    msgs = _explore(game, "gather")
    assert p.stamina_pills == pills + 1 and "回體丹 +1" in msgs
    p.location = "changshe"  # 練功要有對手：城鎮沒有
    msgs = _explore(game, "practice")
    assert p.stamina_pills == pills + 2 and "回體丹 +1" in msgs


def test_seek_does_not_drop():
    game = _game(setup=_sure_drop)
    pills = game.state.player.stamina_pills
    _explore(game, "seek")
    assert game.state.player.stamina_pills == pills


def test_no_pill_drop_outside_season21():
    game = _game(None, setup=_sure_drop)  # 14 天的季：沒有簽到
    pills = game.state.player.stamina_pills
    _explore(game, "gather")
    assert game.state.player.stamina_pills == pills


def test_pill_drop_uses_its_own_dice():
    found = []
    for chance in (0.0, 1.0):
        game = _game(setup=lambda c, chance=chance: (setattr(c.config.checkin, "pill_drop", chance), no_jianfa(c)))  # 找素材：同 _sure_drop
        bag = dict(game.state.player.materials)
        _explore(game, "gather")
        found.append({k: v - bag.get(k, 0) for k, v in game.state.player.materials.items() if v != bag.get(k, 0)})
    assert found[0] == found[1] and found[0]


def test_bot_checks_in_and_picks_by_seed():
    from tianxia import bot

    game = _game()
    p = game.state.player
    p.bot = True
    _day(game, 6)
    bot.check_in(game)
    attribute = checkin.bot_attribute(game.content, p.name, p.season_number)
    mid = next(m.id for m in game.content.materials.values() if m.tier == 4 and m.attribute == attribute)
    assert p.checkin_days == [1, 6] and p.materials.get(mid) == 1
    pills = p.stamina_pills
    bot.check_in(game)  # 同一天再叫一次：什麼都不動
    assert p.checkin_days == [1, 6] and p.stamina_pills == pills


def test_look_after_checks_in():
    from tianxia import bot_policy

    game = _game()
    game.state.player.bot = True
    _day(game, 3)
    bot_policy.look_after(game, random.Random(0))
    assert game.state.player.checkin_days == [1, 3]


def test_tier4_reachable_through_checkin():
    c = real_content("season21")
    c.config.economy.upgrade = False
    assert {"gang_4", "rou_4", "kuai_4", "man_4"} <= _material_sources(c)
    c.config.checkin.enabled = False
    assert not {"gang_4", "rou_4", "kuai_4", "man_4"} & _material_sources(c)
