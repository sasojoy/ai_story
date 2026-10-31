"""第一季正式版・戊一：第 3、4 階的行動（計畫 2026-10-06-第一季正式版-戊一）。

用真實內容（content/）：fixture real、on 在 tests/conftest.py（每個測試拿 real_content 的一份複本；on 是週末設定打開）。
釘住的內容：content/orders.json 的 rank_actions（scripts/test_for.py 改到這個檔時靠檔名挑到這裡）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from pydantic import ValidationError

from tianxia import calendar, events, models, opportunities, rank_actions, rules, seats
from tianxia.content import ContentError, validate
from tianxia.engine import RANK_ACTION_PREFIX, Game
from tianxia.models import Check, OrdersContent, RankAction
from tianxia.state import PlayerState


def _game(content, faction, at, rank=3):
    game = Game.new(content, "甲", rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank, p.location, p.stamina = faction, rank, at, 100
    p.ally = "guan" if faction == "haoqiang" else None  # 豪強分屬兩軍（第一季規則的季一律如此）：依附官軍
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def _always(ok=True):
    return mock.patch.object(rules, "check_chance", return_value=1.0 if ok else 0.0)


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_defaults_so_old_saves_load():
    assert PlayerState(name="甲", location="x", stats={}, stamina=0).rank_action_weeks == {}
    assert OrdersContent().rank_actions == []


def test_real_rank_actions(real):
    by_id = {a.id: a for a in real.orders.rank_actions}
    assert set(by_id) == {"incite", "fortify"}  # 豪強第四階的趁亂占據郡縣 2026-10-31 拿掉（豪強最多第三階）


def test_the_real_rows_follow_the_plan_table(real):
    """內容表（計畫 Task 1）：每一格都照寫；機制數字是【預設】，改了要改這裡與計畫。"""
    rows = {
        a.id: (a.faction, a.rank, a.name, a.stamina, a.weekly, a.tags, a.chaos_only,
               None if a.check is None else (a.check.stat, a.check.difficulty), a.push)
        for a in real.orders.rank_actions
    }
    assert rows == {
        "incite": ("huang", 3, "在一地煽動起事", 20, 3, ["城鎮"], False, ("wis", 7), 5),
        "fortify": ("haoqiang", 3, "修築塢堡", 20, 3, [], True, None, 5),
    }


def test_the_real_texts_name_the_place(real):
    """成功與失敗的敘事都是照{地點}填的；沒有檢定的行動不會失敗，沒有 fail。"""
    by_id = {a.id: a for a in real.orders.rank_actions}
    assert all("{地點}" in a.ok for a in by_id.values())
    assert "{地點}" in by_id["incite"].fail and by_id["fortify"].fail == ""


def test_rank_action_faction_must_exist(real):
    real.orders.rank_actions[0].faction = "nobody"
    with pytest.raises(ContentError, match="rank_actions"):
        validate(real)


def test_rank_action_ids_must_not_repeat(real):
    real.orders.rank_actions.append(real.orders.rank_actions[0].model_copy())
    with pytest.raises(ContentError, match="rank_actions.*id 重複"):
        validate(real)


@pytest.mark.parametrize("field", ["name", "ok", "fail"])
def test_rank_action_text_must_be_traditional(real, field):
    incite = next(a for a in real.orders.rank_actions if a.id == "incite")
    setattr(incite, field, "这里的话是简体")
    with pytest.raises(ContentError, match="rank_actions.incite.*繁體"):
        validate(real)


def test_a_check_needs_a_fail_text(real):
    """有檢定就會有失敗：fail 空著，每次失敗第一句是空的。"""
    next(a for a in real.orders.rank_actions if a.id == "incite").fail = ""
    with pytest.raises(ContentError, match="fail"):
        validate(real)


def test_a_blank_fail_text_does_not_count(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").fail = "  "
    with pytest.raises(ContentError, match="fail"):
        validate(real)


@pytest.mark.parametrize("tags", [["城池村"], ["城鎮", "城池村"]])
def test_tags_must_be_tags_some_location_carries(real, tags):
    """拼錯的標籤：那個行動在哪裡都不會出現，載入時就擋；好幾個標籤裡有一個拼錯也擋（不是有一個對就放行）。"""
    next(a for a in real.orders.rank_actions if a.id == "incite").tags = tags
    with pytest.raises(ContentError, match="tags.*城池村"):
        validate(real)


def test_tags_may_mix_known_tags(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").tags = ["城鎮", "營寨"]
    validate(real)


def test_the_check_stat_must_be_a_known_stat(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").check.stat = "luck"
    with pytest.raises(ContentError, match="未知的屬性 luck"):
        validate(real)


@pytest.mark.parametrize(
    "change", [{"rank": 2}, {"rank": 5}, {"stamina": -1}, {"stamina": 0}, {"weekly": 0}, {"push": 0}, {"surprise": 1}],
)
def test_the_model_refuses_nonsense_numbers_and_unknown_fields(change):
    fields = {"id": "x", "faction": "huang", "rank": 3, "name": "甲", "stamina": 1, "weekly": 1, "push": 1, "ok": "好"}
    with pytest.raises(ValidationError):
        RankAction(**{**fields, **change})


def test_the_menu_family_is_registered_for_tutorial_allow_lists():
    """教學與入伍的 allow 要能寫 act:rank:…（models.ALLOW_FAMILIES；沒列的話那一步會把選單清空）。"""
    assert models.allow_known("act:rank:incite") and models.allow_known("act:rank:")
    assert not models.allow_known("act:rankings")  # 前綴是整個「act:rank:」，不是 act:rank 開頭的任何字串


# ── Task 2：規則與引擎 ───────────────────────────────────


def _week(game, n, offset=3600.0):
    """把共用賽季的時間放到季曆第 n 週週一 00:00 再加 offset 世界秒（預設 +1 小時，週末設定落在那一週的週二，不會跨週）。"""
    w = game.state.world
    w.time = calendar.week_start(n, game.content, w) + offset


def _next_day(game, days=1):
    """往後推 days 個季曆日（同一週裡）：每人每曆日每條線的推動上限（daily_push_cap）換一天重算。"""
    w = game.state.world
    w.time += days * calendar.DAY / calendar.cal_scale(game.content, w)


def _chaos(game, front, value=50):
    game.state.world.trends[front] = value
    rules.recompute_trends(game.state.world, game.content)


def _option(game, option_id):
    return next((o for o in game.options(odds=False) if o.id == option_id), None)


def _action(content, action_id):
    return next(a for a in content.orders.rank_actions if a.id == action_id)


def _said(content, action_id, field, loc_id):
    """行動成功（ok）或失敗（fail）時玩家讀到的那一句：照內容檔的字、填上地點名。句子是 joy 在潤的，內容檔改了字，測試不該跟著變紅。"""
    return getattr(_action(content, action_id), field).replace("{地點}", content.locations[loc_id].name)


def _check_note(game, action_id):
    """有檢定的行動在括號裡寫的那一段（跟事件選項同一個寫法，events.check_note；企劃者裁決 E5.3）。心裡話是 joy 的字，不在這裡寫死。"""
    return events.check_note(_action(game.content, action_id).check, game.state, game.content, game.world)


def test_incite_needs_rank_three_and_a_town(on):
    game = _game(on, "huang", "runan", rank=2)
    assert "act:rank:incite" not in _ids(game)
    game.state.player.rank = 3
    option = _option(game, "act:rank:incite")
    assert option.label == f"在一地煽動起事（體力 20・{_check_note(game, 'incite')}）"
    game.state.player.location = "runan_wilds"  # 野外不是城鎮
    assert "act:rank:incite" not in _ids(game)


def test_the_option_id_is_the_registered_prefix_plus_the_action_id(on):
    game = _game(on, "huang", "runan")
    assert f"{RANK_ACTION_PREFIX}incite" in _ids(game) and RANK_ACTION_PREFIX == "act:rank:"


def test_incite_pushes_the_front_and_credits_orders(on):
    game = _game(on, "huang", "runan")
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True), mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        msgs = game.choose("act:rank:incite")
    assert msgs[0] == _said(on, "incite", "ok", "runan")
    credit.assert_called_once_with(kind="incite", location="runan", front="yingru", weight=5)
    assert rules.trend_value(game.state, on, "yingru") == before + 5  # 黃巾往己方（往 100）推 5 點


def test_failed_incite_counts_but_does_not_push(on):
    game = _game(on, "huang", "runan")
    before = rules.trend_value(game.state, on, "yingru")
    with _always(False), mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        msgs = game.choose("act:rank:incite")
    assert msgs[0] == _said(on, "incite", "fail", "runan") and rules.trend_value(game.state, on, "yingru") == before
    assert sum(game.state.player.rank_action_weeks.values()) == 1
    credit.assert_not_called()  # 沒過檢定：不替軍令記功
    assert game.state.player.stamina == 80  # 體力照扣


def test_a_failed_incite_adds_no_contribution_and_a_won_one_does(on):
    game = _game(on, "huang", "runan")
    with _always(False):
        game.choose("act:rank:incite")
    assert game.state.player.contrib == 0
    with _always(True):
        game.choose("act:rank:incite")
    assert game.state.player.contrib > 0  # 推動走 push_trend：貢獻帳照第七節記


def test_fortify_only_where_the_front_is_in_chaos(on):
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 20)  # 官軍穩控，不在亂局
    assert "act:rank:fortify" not in _ids(game)
    _chaos(game, "yingru", 50)
    assert "act:rank:fortify" in _ids(game)


@pytest.mark.parametrize("value, shown", [(34, False), (35, True), (65, True), (66, False)])
def test_the_chaos_band_includes_both_ends(on, value, shown):
    """亂局是 chaos_low～chaos_high 含兩端（rules.in_chaos）：選項照它出現，不是按了才說不行。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", value)
    assert ("act:rank:fortify" in _ids(game)) is shown


def test_fortify_pushes_the_front_toward_the_army_the_gentry_back(on):
    """豪強分屬兩軍：修築塢堡照依附那一軍的目標推所在的戰線（依附官軍：潁川往 0 推 5 點；推割據 2026-10-31 拿掉）。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    front = rules.trend_value(game.state, on, "yingru")
    game.choose("act:rank:fortify")
    assert rules.trend_value(game.state, on, "yingru") == front - 5


def test_fortify_credits_orders_with_weight_five(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    with mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        game.choose("act:rank:fortify")
    assert credit.call_args_list == [mock.call(kind="fortify", location="runan", front="yingru", weight=5)]


def test_each_faction_gets_only_its_own_actions(on):
    for faction, mine in (("huang", {"act:rank:incite"}), ("haoqiang", {"act:rank:fortify"}), ("guan", set())):
        game = _game(on, faction, "runan", rank=3)
        _chaos(game, "yingru", 50)
        assert {i for i in _ids(game) if i.startswith("act:rank:")} == mine


def test_a_drifter_has_no_rank_actions(on):
    game = _game(on, None, "runan", rank=3)
    assert not any(i.startswith("act:rank:") for i in _ids(game))


def test_nothing_where_there_is_no_front(on):
    game = _game(on, "haoqiang", "luoyang_road")  # 洛陽官道：沒有戰線
    assert not any(i.startswith("act:rank:") for i in _ids(game))


def test_the_option_is_grey_when_the_stamina_is_short(on):
    """體力不夠：灰掉、只寫體力，不帶檢定那一段（審查 I1 改裁決：這些行動在「此地還能做」裡，網頁照原文印灰掉的標籤，
    帶著心裡話會讀成是悟性不夠才灰的）。體力夠了才寫檢定（裁決 E5.3）。"""
    game = _game(on, "huang", "runan")
    game.state.player.stamina = 19
    option = _option(game, "act:rank:incite")
    assert option is not None and not option.enabled and option.label == "在一地煽動起事（體力 20）"
    game.state.player.stamina = 20
    assert _option(game, "act:rank:incite").enabled
    assert _option(game, "act:rank:incite").label == f"在一地煽動起事（體力 20・{_check_note(game, 'incite')}）"


def test_a_rank_two_check_action_short_of_stamina_reads_only_its_cost(on):
    """第 2 階行動也一樣（審查 I1）：施符水收人心體力不夠時灰掉，標籤是「施符水收人心（體力 15）」；夠了才帶檢定那一段。"""
    game = _game(on, "huang", "julu_altar", rank=2)
    cost = on.config.rank2_stamina
    game.state.player.stamina = cost - 1
    option = _option(game, "act:rank2")
    assert option is not None and not option.enabled and option.label == f"施符水收人心（體力 {cost}）"
    game.state.player.stamina = cost
    note = events.check_note(opportunities.rank2_action(game.state, on).check, game.state, on, game.world)
    option = _option(game, "act:rank2")
    assert option.enabled and option.label == f"施符水收人心（體力 {cost}・{note}）"


def test_an_option_that_is_not_on_the_menu_is_refused(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    stamina = game.state.player.stamina
    assert game.choose("act:rank:incite") == ["（此刻無法這麼做。）"]  # 不是黃巾：沒有這個選項，按了什麼都沒發生
    assert game.state.player.stamina == stamina and game.state.player.rank_action_weeks == {}


def test_weekly_limit_resets_on_monday(on):
    """一週 3 次分在三個曆日做（同一個曆日推兩次就碰到每人每曆日的上限，企劃者裁決 E1：那一下灰掉，見下面）。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    for day in range(3):
        if day:
            _next_day(game)
        game.choose("act:rank:fortify")
    option = _option(game, "act:rank:fortify")
    assert not option.enabled and "這週已經做滿 3 次" in option.label
    _week(game, 3, offset=-60)  # 第 2 週週日 23:59：還是這一週
    assert not _option(game, "act:rank:fortify").enabled
    _week(game, 3, offset=0)  # 週一 00:00
    assert _option(game, "act:rank:fortify").enabled


def test_the_weekly_count_keeps_only_this_week(on):
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    game.choose("act:rank:fortify")
    assert game.state.player.rank_action_weeks == {"2:fortify": 1}
    _week(game, 3)
    game.choose("act:rank:fortify")
    assert game.state.player.rank_action_weeks == {"3:fortify": 1}  # 上一週的丟掉


def test_a_won_and_a_failed_try_both_count(on):
    game = _game(on, "huang", "runan")
    _week(game, 2)
    with _always(True):
        game.choose("act:rank:incite")
    with _always(False):
        game.choose("act:rank:incite")
    assert game.state.player.rank_action_weeks == {"2:incite": 2}


def test_the_journal_title_names_the_action_and_the_place(on):
    game = _game(on, "huang", "runan")
    game.choose("act:rank:incite")
    assert game.state.journal[0].title == "在一地煽動起事・汝南"  # 江湖紀錄最新的在最前面


def test_switch_off_no_rank_actions(real):
    game = _game(real, "huang", "runan")
    assert not any(i.startswith("act:rank:") for i in _ids(game))


def test_the_actions_leave_a_bot_loop_no_endless_option(on):
    """整季機器人只在「沒有任何可按的選項」時推進時間（bot.pick、play_season）：這幾個行動花體力、做滿就灰掉，
    不是永遠按得下去的選項（像 act:rest）；play_season 只收 enabled 的。一直按到不能按為止，一定停得下來。
    同一個曆日裡先碰到的是每人每曆日的推動上限（兩次 5 點推滿 10 點，企劃者裁決 E1），換一天再按到這一週做滿。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    pressed = 0
    while (option := _option(game, "act:rank:fortify")) is not None and option.enabled:
        game.choose("act:rank:fortify")
        pressed += 1
        assert pressed <= 2
    assert pressed == 2
    game.state.player.stamina = 100
    assert not _option(game, "act:rank:fortify").enabled  # 體力夠、還是灰的：今天這條線推滿了
    _next_day(game)
    while (option := _option(game, "act:rank:fortify")) is not None and option.enabled:
        game.choose("act:rank:fortify")
        pressed += 1
        assert pressed <= 3
    assert pressed == 3
    game.state.player.stamina = 100
    assert not _option(game, "act:rank:fortify").enabled  # 體力夠、還是灰的：這一週做滿了
    _week(game, 3)
    game.state.player.stamina = 10
    assert not _option(game, "act:rank:fortify").enabled  # 新的一週：體力不夠一樣灰


def test_mine_is_empty_for_a_drifter_and_when_the_switch_is_off(on):
    assert rank_actions.mine(_game(on, None, "runan").state, on) == []
    game = _game(on, "haoqiang", "runan")
    assert [a.id for a in rank_actions.mine(game.state, on)] == ["fortify"]
    on.config.season_one = False  # 管理者把設定關掉，資料庫裡的那一季還蓋著章：規則兩個都要看
    assert rank_actions.mine(game.state, on) == []


def test_where_ok_checks_front_tags_and_chaos(on):
    game = _game(on, "haoqiang", "runan")
    fortify, incite = _action(on, "fortify"), _action(on, "incite")
    _chaos(game, "yingru", 50)
    assert rank_actions.where_ok(game.state, on, fortify, "runan_wilds") and not rank_actions.where_ok(game.state, on, incite, "runan_wilds")
    assert rank_actions.where_ok(game.state, on, incite, "runan")  # 城鎮
    assert not rank_actions.where_ok(game.state, on, fortify, "luoyang_road")  # 沒有戰線
    _chaos(game, "yingru", 10)
    assert not rank_actions.where_ok(game.state, on, fortify, "runan")  # 不在亂局


def test_where_ok_for_a_tagless_action_that_is_not_chaos_only(on):
    """tags 空＝有戰線的地方都行；chaos_only 是 False＝不看戰況（內容現在沒有這種行動，規則照寫的做）。"""
    game = _game(on, "huang", "runan_wilds")
    incite = _action(on, "incite").model_copy(update={"tags": []})
    assert rank_actions.where_ok(game.state, on, incite, "runan_wilds")
    assert not rank_actions.where_ok(game.state, on, incite, "luoyang_road")
    _chaos(game, "yingru", 10)
    assert rank_actions.where_ok(game.state, on, incite, "runan_wilds")


def test_weight_is_five_for_rank_three(on):
    assert [rank_actions.weight(_action(on, i)) for i in ("incite", "fortify")] == [5, 5]


def test_left_counts_down_and_count_rewrites_the_week(on):
    game = _game(on, "haoqiang", "runan")
    fortify = _action(on, "fortify")
    _week(game, 4)
    assert rank_actions.left(game.state, on, fortify) == 3
    rank_actions.count(game.state, on, fortify)
    rank_actions.count(game.state, on, fortify)
    assert rank_actions.left(game.state, on, fortify) == 1
    game.state.player.rank_action_weeks["1:seize"] = 1  # 舊的一週留下的
    rank_actions.count(game.state, on, fortify)
    assert game.state.player.rank_action_weeks == {"4:fortify": 3}
    assert rank_actions.left(game.state, on, fortify) == 0


def test_the_front_push_follows_the_factions_goal(on):
    """戰線那一支也乘自己陣營對這條戰線的目標：目標是 2 就推 2 × 5 點（每人每曆日上限 10 點以內）。"""
    game = _game(on, "huang", "runan")
    on.scenario.faction("huang").goals["yingru"] = 2
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True):
        game.choose("act:rank:incite")
    assert rules.trend_value(game.state, on, "yingru") == before + 10


def test_two_tags_mean_either_one(on):
    """寫了好幾個 tags：帶其中一個就行（不是每個都要帶）。"""
    game = _game(on, "huang", "runan")
    incite = _action(on, "incite").model_copy(update={"tags": ["城鎮", "營寨"]})
    assert rank_actions.where_ok(game.state, on, incite, "runan")  # 汝南是城鎮、不是營寨
    assert not rank_actions.where_ok(game.state, on, incite.model_copy(update={"tags": ["營寨", "祭壇"]}), "runan")


def test_rank_action_weeks_is_keyed_by_the_week_and_the_action_id():
    """「季曆週:行動 id」→ 這一週做了幾次：鍵是字串、值是整數（不是 int 的鍵）。Task 2 的測試只讀它的值，型別在這裡釘。"""
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, rank_action_weeks={"3:incite": 1})
    assert p.rank_action_weeks == {"3:incite": 1}
    with pytest.raises(ValidationError):
        PlayerState(name="甲", location="x", stats={}, stamina=0, rank_action_weeks={"3:incite": "很多"})


def test_rank_action_weeks_survive_a_save_and_load(on):
    """存檔再讀回來還是同一份（角色存成一列 JSON，鍵是「週:行動 id」的字串）：換了週還記得這一週做了幾次。"""
    from tianxia.characters import open_characters

    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    game.choose("act:rank:fortify")
    game.choose("act:rank:fortify")
    open_characters().save(game.state)
    loaded = open_characters().load("甲")
    assert loaded.player.rank_action_weeks == game.state.player.rank_action_weeks == {"2:fortify": 2}


@pytest.mark.parametrize("bad_id", ["", "a:b", ":x", "x:"])
def test_a_rank_action_id_is_not_empty_and_has_no_colon(real, bad_id):
    """id 是選項 act:rank:<id> 的尾巴（_rank_action_id 照前綴切）、也是軍令記功的 kind：空的或帶冒號都會切錯。"""
    next(a for a in real.orders.rank_actions if a.id == "fortify").id = bad_id
    with pytest.raises(ContentError, match="id 不能"):
        validate(real)


def test_the_success_text_must_name_the_place(real):
    """成功的那一句要有 {地點}：玩家看到的是「你在汝南…」，沒寫就不知道在哪裡做的。"""
    next(a for a in real.orders.rank_actions if a.id == "incite").ok = "你振臂一呼，幾十個鄉民扯下了頭巾。"
    with pytest.raises(ContentError, match="rank_actions.incite.*ok.*地點"):
        validate(real)


def test_a_good_id_with_an_underscore_or_digits_loads(real):
    next(a for a in real.orders.rank_actions if a.id == "fortify").id = "fort_2"
    validate(real)


def test_the_tags_error_says_which_tags_no_location_carries(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").tags = ["城鎮", "城池村"]
    with pytest.raises(ContentError, match=r"tags 裡有的標籤，沒有任何地點帶：\['城池村'\]"):
        validate(real)


@pytest.mark.parametrize("state", ["resting", "preparing", "paused"])
def test_no_rank_actions_while_the_season_is_closed(on, state):
    """休季、籌備中、賽季時鐘暫停：選單上沒有第 3、4 階的行動，直接按也什麼都不發生（體力、這週的次數都不動）。
    這三個都在 options()／_everyday_options 的早退裡；行動的選項不能跑到它們前面。"""
    if state == "preparing":
        on.config.auto_open_first_season = False
    game = _game(on, "huang", "runan")
    if state == "preparing":
        game.state.world.season_one = True  # 籌備中的季還沒蓋章；蓋著章才看得出擋住的是籌備中的早退，不是章
    elif state == "resting":
        game.world.mutate_season(lambda s: setattr(s, "ended", True))
        game.state.world = game.world.get_season()
    else:
        assert game.world.pause_clock(1000.0)
    assert game.world.season_phase() == ("running" if state == "paused" else state)
    stamina = game.state.player.stamina
    assert not any(i.startswith("act:rank:") for i in _ids(game))
    msgs = game.choose("act:rank:incite")
    assert len(msgs) == 1 and msgs[0].startswith("（") and not msgs[0].startswith("（你")  # 一句拒絕的話
    assert game.state.player.stamina == stamina and game.state.player.rank_action_weeks == {}


def test_a_menu_built_while_the_front_was_in_chaos_is_refused_once_it_left(on):
    """審查焦點 2，走 choose：選單上有修築塢堡，戰線離開亂局（黃巾壓過去了）；按下去是被拒絕的，什麼都沒扣。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    assert "act:rank:fortify" in _ids(game)
    _chaos(game, "yingru", 80)
    stamina = game.state.player.stamina
    assert game.choose("act:rank:fortify") == ["（此刻無法這麼做。）"]
    assert game.state.player.stamina == stamina and game.state.player.rank_action_weeks == {}


def test_a_failed_check_on_a_gentry_action_pushes_nothing_credits_nothing_and_still_counts(on):
    """真實內容的豪強行動都沒有檢定，失敗那一支走不到：給修築塢堡一個檢定（內容的複本），逼它失敗。"""
    fortify = _action(on, "fortify")
    fortify.check = Check(stat="str", difficulty=7)
    fortify.fail = "你的部曲在{地點}挖了半天，牆還是塌了。"
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    front = rules.trend_value(game.state, on, "yingru")
    with _always(False), mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        msgs = game.choose("act:rank:fortify")
    assert msgs[0] == "你的部曲在汝南荒野挖了半天，牆還是塌了。"
    assert rules.trend_value(game.state, on, "yingru") == front
    credit.assert_not_called()
    assert game.state.player.rank_action_weeks == {"1:fortify": 1}
    assert game.state.player.stamina == 80


def test_defecting_keeps_the_counter_but_the_old_actions_do_not_follow(on):
    """叛投不清 rank_action_weeks（行動 id 跟陣營綁，同 rank2_days）：黃巾第 3 階這週用過煽動起事，叛去豪強——
    身份歸零（第 1 階）沒有任何第 3、4 階行動；之後長到第 3 階，修築塢堡是自己的一份次數，不吃煽動起事的。"""
    game = _game(on, "huang", "runan")
    with _always(True):
        game.choose("act:rank:incite")
    assert game.state.player.rank_action_weeks == {"1:incite": 1}
    game.state.player.location = "cao_manor"
    game.choose("defect:haoqiang:guan")  # 豪強分屬兩軍：投靠點每一軍一顆，依附官軍
    game.choose("defect:confirm")
    p = game.state.player
    assert (p.faction, p.rank, p.qualified) == ("haoqiang", 0, False)
    _chaos(game, "yingru", 50)
    assert not any(i.startswith("act:rank:") for i in _ids(game))  # 第 1 階：什麼都沒有
    assert p.rank_action_weeks == {"1:incite": 1}  # 舊的那筆還在（沒清）
    p.rank = 3  # 之後在豪強這邊晉升到第 3 階
    fortify = _option(game, "act:rank:fortify")
    assert fortify is not None and fortify.enabled
    assert rank_actions.left(game.state, on, _action(on, "fortify")) == 3  # 煽動起事的那一次不算進修築塢堡
    game.choose("act:rank:fortify")
    assert p.rank_action_weeks == {"1:incite": 1, "1:fortify": 1}  # 兩個行動各記各的


# ── 企劃者裁決 E1（2026-10-07）：這條線今天推滿了，行動灰掉 ─────────────────
# 每人每曆日每條線的推動上限（daily_push_cap，緩衝之後的量）不改；推滿了的那條線，第 3、4 階行動按下去只會推 +0，
# 所以灰掉、寫「今天這條線已經推滿」，按了被拒絕（不扣體力、不記次數）。還推得動一點的照常按、照常付。
# 「推滿了沒」跟 Game.push_trend 走 push.py 的同一個地方（push.room_left），不另算一份。


def _fill(game, line, amount=None):
    """把自己今天在這條線上的推動帳記到 amount（預設正好推滿上限）。"""
    w = game.state.world
    day = calendar.point(w.time, game.content, w).cal_day
    game.state.player.pushed[f"{day}:{line}"] = game.content.config.daily_push_cap if amount is None else amount


FULL = "今天這條線已經推滿"


def test_a_full_line_greys_the_action_and_says_why(on):
    game = _game(on, "huang", "runan")
    _fill(game, "yingru")
    option = _option(game, "act:rank:incite")
    assert option is not None and not option.enabled
    assert option.label == f"在一地煽動起事（{FULL}）"  # 新寫，待 joy 潤
    assert game.state.player.stamina >= _action(on, "incite").stamina  # 體力夠：灰掉是因為推滿了


def test_pressing_an_action_on_a_full_line_is_refused_and_costs_nothing(on):
    game = _game(on, "huang", "runan")
    _fill(game, "yingru")
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True):
        assert game.choose("act:rank:incite") == ["（此刻無法這麼做。）"]
    p = game.state.player
    assert (p.stamina, p.rank_action_weeks, p.contrib) == (100, {}, 0)
    assert rules.trend_value(game.state, on, "yingru") == before


def test_partial_room_is_pushed_and_paid_in_full(on):
    """還推得動 3 點（推 5 點的行動）：照常按、照常付全部體力、記一次，只推得動的那 3 點。"""
    game = _game(on, "huang", "runan")
    cap = on.config.daily_push_cap
    _fill(game, "yingru", cap - 3)
    option = _option(game, "act:rank:incite")
    assert option.enabled and FULL not in option.label
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True):
        msgs = game.choose("act:rank:incite")
    assert msgs[0] == _said(on, "incite", "ok", "runan")
    assert rules.trend_value(game.state, on, "yingru") == before + 3
    assert game.state.player.stamina == 100 - _action(on, "incite").stamina
    assert sum(game.state.player.rank_action_weeks.values()) == 1
    assert FULL in _option(game, "act:rank:incite").label  # 推滿了：下一次灰掉


def test_two_incites_fill_the_day_and_the_third_is_grey(on):
    """戊一最終審查量到的：一個人煽動起事 47→52→57→57，第三次推 +0 卻照扣體力、照寫成功。現在第三次灰掉、按了被拒絕。"""
    game = _game(on, "huang", "runan")
    _week(game, 2)
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True):
        game.choose("act:rank:incite")
        game.choose("act:rank:incite")
        assert rules.trend_value(game.state, on, "yingru") == before + 10
        option = _option(game, "act:rank:incite")
        assert not option.enabled and option.label == f"在一地煽動起事（{FULL}）"
        stamina = game.state.player.stamina
        assert game.choose("act:rank:incite") == ["（此刻無法這麼做。）"]
    assert game.state.player.stamina == stamina and game.state.player.rank_action_weeks == {"2:incite": 2}


def test_the_next_calendar_day_reopens_the_line(on):
    game = _game(on, "huang", "runan")
    _week(game, 2)
    _fill(game, "yingru")
    assert not _option(game, "act:rank:incite").enabled
    _next_day(game)
    assert _option(game, "act:rank:incite").enabled


def test_a_menu_built_before_the_line_filled_is_refused(on):
    """選單是推滿之前拿到的（例如在別的分頁推滿了）：choose 重建選單、按下去被拒絕，什麼都不扣。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    assert _option(game, "act:rank:fortify").enabled  # 玩家看到的選單
    _fill(game, "yingru")
    assert game.choose("act:rank:fortify") == ["（此刻無法這麼做。）"]
    assert game.state.player.stamina == 100 and game.state.player.rank_action_weeks == {}


def test_the_weekly_limit_label_comes_before_the_full_line(on):
    """這週做滿而且今天這條線也推滿：只寫一個原因，先寫這週做滿。"""
    game = _game(on, "huang", "runan")
    _week(game, 2)
    game.state.player.rank_action_weeks = {"2:incite": _action(on, "incite").weekly}
    _fill(game, "yingru")
    option = _option(game, "act:rank:incite")
    assert not option.enabled and option.label == "在一地煽動起事（這週已經做滿 3 次）"


def test_hao_and_huang_actions_check_the_front_they_push(on):
    """看哪一條線跟推哪一條線同一個判斷：豪強（修築塢堡，照依附那一軍）與黃巾（煽動起事）都看所在的戰線（割據 2026-10-31 拿掉）。"""
    hao = _game(on, "haoqiang", "runan")
    _chaos(hao, "yingru", 50)
    assert _option(hao, "act:rank:fortify").enabled
    _fill(hao, "nanyang")  # 別的戰線推滿了：不相干
    assert _option(hao, "act:rank:fortify").enabled
    _fill(hao, "yingru")
    assert FULL in _option(hao, "act:rank:fortify").label
    huang = _game(on, "huang", "runan")
    assert _option(huang, "act:rank:incite").enabled
    _fill(huang, "yingru")
    assert FULL in _option(huang, "act:rank:incite").label


def test_the_menu_and_push_trend_read_the_same_room(on):
    """「推滿了沒」只有一個地方算（push.room_left，push_trend 與選單都走它）：把它換成永遠沒有空間，
    選單灰掉、push_trend 也一點都推不動；換成還有空間，帳上推滿了選單也照樣亮著。"""
    from tianxia import push

    game = _game(on, "huang", "runan")
    before = rules.trend_value(game.state, on, "yingru")
    with mock.patch.object(push, "room_left", return_value=0.0):
        assert FULL in _option(game, "act:rank:incite").label
        game.push_trend("yingru", 5, source="test")
    assert rules.trend_value(game.state, on, "yingru") == before
    _fill(game, "yingru")
    with mock.patch.object(push, "room_left", return_value=5.0):
        assert _option(game, "act:rank:incite").enabled


# ── 企劃者裁決 E5.3（2026-10-07）：有檢定的行動照事件選項的寫法寫檢定 ─────────────────
# 「{行動}（體力 N・{屬性名} {數值}：{心裡話}）」：括號裡體力後面接的，就是事件選項括號裡的那一段（events.check_note，choice_label
# 也用它），沒有第二份寫法；吃到惡名熟練加成的照寫「＋N」與熟練那一句。不寫失手多耗體力（這些行動失敗不另扣）。灰掉的標籤照舊。


def test_the_check_reads_like_an_event_option(on):
    """悟性 5 煽動起事（難度 7）：「在一地煽動起事（體力 20・悟性 5：{差 -2 那一檔的心裡話}）」。"""
    game = _game(on, "huang", "runan")
    incite = _action(on, "incite")
    outlook = rules.check_outlook(incite.check, game.state, on, game.world)
    voice = events.voice_line("wis", outlook.gap, on)
    assert _option(game, "act:rank:incite").label == f"在一地煽動起事（體力 20・悟性 5：{voice}）"


def test_rank_actions_and_event_options_share_one_check_writer(on):
    """把 events.check_note 換掉：事件選項與第 3 階、第 2 階的行動都跟著換（不是各寫一份）。"""
    game = _game(on, "huang", "runan")
    choice = next(ch for e in on.events.values() for ch in e.choices if ch.check is not None and not ch.combat)
    with mock.patch.object(events, "check_note", return_value="記號"):
        assert "（記號）" in events.choice_label(choice, game.state, on, game.world)
        assert _option(game, "act:rank:incite").label == "在一地煽動起事（體力 20・記號）"
        game.state.player.rank = 2
        game.state.player.location = "julu_altar"
        assert _option(game, "act:rank2").label == f"施符水收人心（體力 {on.config.rank2_stamina}・記號）"


def test_evil_practice_shows_in_the_label(on):
    """內容的複本：煽動起事的檢定吃惡名的熟練加成。惡名 10 → 「悟性 5＋1：」接熟練那一句、逗號、心裡話。"""
    incite = _action(on, "incite")
    incite.check = incite.check.model_copy(update={"practice": "evil"})
    game = _game(on, "huang", "runan")
    game.state.player.stats["evil"] = 10
    label = _option(game, "act:rank:incite").label
    practiced = rules.practice_line(incite.check, game.state, on, game.world).rstrip("。")
    assert label.startswith(f"在一地煽動起事（體力 20・悟性 5＋1：{practiced}，")


def test_actions_without_a_check_keep_their_label(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    assert _option(game, "act:rank:fortify").label == "修築塢堡（體力 20）"


def test_grey_labels_do_not_carry_the_check(on):
    """灰掉的原因照舊只寫原因（這週做滿、今天推滿、第 2 階今天做滿）。"""
    game = _game(on, "huang", "runan", rank=2)
    game.state.player.rank2_days = {calendar.point(game.state.world.time, on, game.state.world).cal_day: on.config.rank2_daily}
    assert _option(game, "act:rank2").label == f"施符水收人心（今天已經做滿 {on.config.rank2_daily} 次）"
    game.state.player.rank = 3
    _fill(game, "yingru")
    assert _option(game, "act:rank:incite").label == f"在一地煽動起事（{FULL}）"


def test_rank_two_and_duty_are_not_greyed_by_a_full_line(on):
    """裁決只管第 3、4 階的行動：第 2 階行動與守勢行動照舊按得下去（推力被上限吃掉的那一份照舊）。"""
    game = _game(on, "huang", "runan", rank=2)
    _fill(game, "yingru")
    assert _option(game, "act:rank2").enabled and FULL not in _option(game, "act:rank2").label
    assert _option(game, "act:duty").enabled
