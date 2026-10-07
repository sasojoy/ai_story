"""第一季正式版・戊一：第 3、4 階的行動（計畫 2026-10-06-第一季正式版-戊一）。

用真實內容（content/）：fixture real、on 在 tests/conftest.py（每個測試拿 real_content 的一份複本；on 是週末設定打開）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from pydantic import ValidationError

from tianxia import calendar, models, rank_actions, rules
from tianxia.content import ContentError, validate
from tianxia.engine import RANK_ACTION_PREFIX, Game
from tianxia.models import OrdersContent, RankAction
from tianxia.state import PlayerState


def _game(content, faction, at, rank=3):
    game = Game.new(content, "甲", rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank, p.location, p.stamina = faction, rank, at, 100
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
    assert set(by_id) == {"incite", "fortify", "seize"}
    assert (by_id["seize"].rank, by_id["seize"].weekly, by_id["seize"].push) == (4, 1, 10)


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
        "seize": ("haoqiang", 4, "趁亂占據郡縣", 30, 1, ["城鎮"], True, None, 10),
    }


def test_the_real_texts_name_the_place(real):
    """成功與失敗的敘事都是照{地點}填的；沒有檢定的行動不會失敗，沒有 fail。"""
    by_id = {a.id: a for a in real.orders.rank_actions}
    assert all("{地點}" in a.ok for a in by_id.values())
    assert "{地點}" in by_id["incite"].fail and by_id["fortify"].fail == "" and by_id["seize"].fail == ""


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


def _chaos(game, front, value=50):
    game.state.world.trends[front] = value
    rules.recompute_trends(game.state.world, game.content)


def _option(game, option_id):
    return next((o for o in game.options(odds=False) if o.id == option_id), None)


def _action(content, action_id):
    return next(a for a in content.orders.rank_actions if a.id == action_id)


def _seat(game, faction="haoqiang"):
    """有第 4 階資格、這一週在任（計畫丁）：rank_of 才是 4。"""
    game.state.player.qualified = True
    game.state.world.seats = {faction: [game.state.player.name]}


def test_incite_needs_rank_three_and_a_town(on):
    game = _game(on, "huang", "runan", rank=2)
    assert "act:rank:incite" not in _ids(game)
    game.state.player.rank = 3
    option = _option(game, "act:rank:incite")
    assert option.label == "在一地煽動起事（體力 20）"
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
    assert msgs[0].startswith("你在汝南的市集上振臂一呼")
    credit.assert_called_once_with(kind="incite", location="runan", front="yingru", weight=5)
    assert rules.trend_value(game.state, on, "yingru") == before + 5  # 黃巾往己方（往 100）推 5 點


def test_failed_incite_counts_but_does_not_push(on):
    game = _game(on, "huang", "runan")
    before = rules.trend_value(game.state, on, "yingru")
    with _always(False), mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        msgs = game.choose("act:rank:incite")
    assert msgs[0].startswith("你在汝南喊了半天") and rules.trend_value(game.state, on, "yingru") == before
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


def test_fortify_pushes_geju_not_the_front(on):
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    front, geju = rules.trend_value(game.state, on, "yingru"), rules.trend_value(game.state, on, "geju")
    game.choose("act:rank:fortify")
    assert rules.trend_value(game.state, on, "yingru") == front
    assert rules.trend_value(game.state, on, "geju") == geju + 5


def test_the_geju_push_follows_the_factions_goal(on):
    """割據的推動乘自己陣營對割據的目標（跟戰線那一支一樣乘目標）：目標是 2 就推 2 × 5 點（每人每曆日上限 10 點以內）。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    on.scenario.faction("haoqiang").goals["geju"] = 2
    geju = rules.trend_value(game.state, on, "geju")
    game.choose("act:rank:fortify")
    assert rules.trend_value(game.state, on, "geju") == geju + 10


def test_fortify_credits_orders_with_weight_five_and_seize_with_ten(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    _seat(game)
    with mock.patch.object(Game, "_order_credit", return_value=[]) as credit:
        game.choose("act:rank:fortify")
        game.choose("act:rank:seize")
    assert credit.call_args_list == [
        mock.call(kind="fortify", location="runan", front="yingru", weight=5),
        mock.call(kind="seize", location="runan", front="yingru", weight=10),
    ]


def test_seize_needs_a_seat(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    assert "act:rank:seize" not in _ids(game)  # 第 3 階
    game.state.player.qualified = True
    assert "act:rank:seize" not in _ids(game)  # 有資格、還沒在任（候缺）：rank_of 是 3
    assert "act:rank:fortify" in _ids(game)
    game.state.world.seats = {"haoqiang": ["甲"]}  # 這一週在任（計畫丁）
    assert "act:rank:seize" in _ids(game)
    game.state.world.seats = {"haoqiang": []}  # 週一輪替掉出席次
    assert "act:rank:seize" not in _ids(game)


def test_seize_needs_a_town_and_a_front_in_chaos(on):
    game = _game(on, "haoqiang", "runan")
    _seat(game)
    _chaos(game, "yingru", 50)
    option = _option(game, "act:rank:seize")
    assert option.label == "趁亂占據郡縣（體力 30）"
    game.state.player.location = "runan_wilds"  # 野外不是城鎮
    assert "act:rank:seize" not in _ids(game)
    game.state.player.location = "runan"
    _chaos(game, "yingru", 80)  # 黃巾壓過去了，不在亂局
    assert "act:rank:seize" not in _ids(game)


def test_seize_pushes_geju_by_ten_and_names_the_place(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    _seat(game)
    geju = rules.trend_value(game.state, on, "geju")
    msgs = game.choose("act:rank:seize")
    assert msgs[0] == "趁著官軍與黃巾殺得難分難解，你帶人進了汝南的縣衙，把官印收進了自己的匣子。"
    assert rules.trend_value(game.state, on, "geju") == geju + 10


def test_a_seated_member_may_still_fortify(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    _seat(game)
    assert {"act:rank:fortify", "act:rank:seize"} <= set(_ids(game))


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
    game = _game(on, "huang", "runan")
    game.state.player.stamina = 19
    option = _option(game, "act:rank:incite")
    assert option is not None and not option.enabled and option.label == "在一地煽動起事（體力 20）"
    game.state.player.stamina = 20
    assert _option(game, "act:rank:incite").enabled


def test_an_option_that_is_not_on_the_menu_is_refused(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    stamina = game.state.player.stamina
    assert game.choose("act:rank:seize") == ["（此刻無法這麼做。）"]  # 第 3 階：沒有這個選項，按了什麼都沒發生
    assert game.state.player.stamina == stamina and game.state.player.rank_action_weeks == {}


def test_weekly_limit_resets_on_monday(on):
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    for _ in range(3):
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


def test_the_count_is_per_action_and_seize_is_once_a_week(on):
    game = _game(on, "haoqiang", "runan")
    _chaos(game, "yingru", 50)
    _seat(game)
    _week(game, 2)
    game.choose("act:rank:seize")
    assert not _option(game, "act:rank:seize").enabled and "這週已經做滿 1 次" in _option(game, "act:rank:seize").label
    assert _option(game, "act:rank:fortify").enabled  # 另一個行動各算各的
    assert game.state.player.rank_action_weeks == {"2:seize": 1}


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


def test_no_rank_actions_in_a_resting_season(on):
    game = _game(on, "huang", "runan")
    game.state.world.ended = True
    assert not any(i.startswith("act:rank:") for i in _ids(game))


def test_switch_off_no_rank_actions(real):
    game = _game(real, "huang", "runan")
    assert not any(i.startswith("act:rank:") for i in _ids(game))


def test_the_actions_leave_a_bot_loop_no_endless_option(on):
    """整季機器人只在「沒有任何可按的選項」時推進時間（bot.pick、play_season）：這幾個行動花體力、做滿就灰掉，
    不是永遠按得下去的選項（像 act:rest）；play_season 只收 enabled 的。一直按到不能按為止，一定停得下來。"""
    game = _game(on, "haoqiang", "runan_wilds")
    _chaos(game, "yingru", 50)
    _week(game, 2)
    pressed = 0
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


def test_the_module_reads_the_rank_not_the_stored_rank(on):
    """存檔的階（PlayerState.rank）停在 3；做得了哪些讀 ranks.rank_of：候缺是 3、在任是 4。"""
    game = _game(on, "haoqiang", "runan")
    assert [a.id for a in rank_actions.mine(game.state, on)] == ["fortify"]
    game.state.player.qualified = True
    assert [a.id for a in rank_actions.mine(game.state, on)] == ["fortify"]
    _seat(game)
    assert game.state.player.rank == 3
    assert [a.id for a in rank_actions.mine(game.state, on)] == ["fortify", "seize"]


def test_mine_is_empty_for_a_drifter_and_when_the_switch_is_off(on):
    assert rank_actions.mine(_game(on, None, "runan").state, on) == []
    game = _game(on, "haoqiang", "runan")
    assert [a.id for a in rank_actions.mine(game.state, on)] == ["fortify"]
    on.config.season_one = False  # 管理者把設定關掉，資料庫裡的那一季還蓋著章：規則兩個都要看
    assert rank_actions.mine(game.state, on) == []


def test_where_ok_checks_front_tags_and_chaos(on):
    game = _game(on, "haoqiang", "runan")
    fortify, seize = _action(on, "fortify"), _action(on, "seize")
    _chaos(game, "yingru", 50)
    assert rank_actions.where_ok(game.state, on, fortify, "runan_wilds") and not rank_actions.where_ok(game.state, on, seize, "runan_wilds")
    assert rank_actions.where_ok(game.state, on, seize, "runan")  # 城鎮、亂局
    assert not rank_actions.where_ok(game.state, on, fortify, "luoyang_road")  # 沒有戰線
    _chaos(game, "yingru", 10)
    assert not rank_actions.where_ok(game.state, on, fortify, "runan") and not rank_actions.where_ok(game.state, on, seize, "runan")


def test_where_ok_for_a_tagless_action_that_is_not_chaos_only(on):
    """tags 空＝有戰線的地方都行；chaos_only 是 False＝不看戰況（內容現在沒有這種行動，規則照寫的做）。"""
    game = _game(on, "huang", "runan_wilds")
    incite = _action(on, "incite").model_copy(update={"tags": []})
    assert rank_actions.where_ok(game.state, on, incite, "runan_wilds")
    assert not rank_actions.where_ok(game.state, on, incite, "luoyang_road")
    _chaos(game, "yingru", 10)
    assert rank_actions.where_ok(game.state, on, incite, "runan_wilds")


def test_weight_is_five_for_rank_three_and_ten_for_rank_four(on):
    assert [rank_actions.weight(_action(on, i)) for i in ("incite", "fortify", "seize")] == [5, 5, 10]


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
