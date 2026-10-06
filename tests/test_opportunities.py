"""第一季正式版・乙一：機緣的框架、第 2 階行動與九種機緣（計畫 2026-10-06-第一季正式版-乙一）。

用真實內容（content/）；開關在測試裡才打開。週末設定（人數上限 2）：需求量照伏筆 2.8 換算（10 次→2、情誼 40→8）。

content/opportunities.json 與 content/orders.json 的 rank2 裡新寫的句子是初稿，待 joy 潤（JSON 沒有註解、模型不收多的欄位，
所以標記記在這裡與 models.py；跟叛投的 defect_text 同一個做法）。照機緣文件原文的句子不在此列。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import bot, bot_policy, calendar, figures, opportunities, push, rules, timetable
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game
from tianxia.models import OppDef
from tianxia.state import BotProfile, PlayerState, TimelineResult

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, rank=0):
    game = Game.new(content, name, rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def test_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried, p.rank2_days) == (
        [], {}, {}, {}, [], {}, {})


def test_new_fields_survive_a_save_and_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, opp_done=["a"], opp_counts={"b": 1}, opp_items={"c": "信"},
                    opp_fronts={"c": "yingru"}, opp_clues=["d"], opp_tried={"e": 3}, rank2_days={12: 2})
    again = PlayerState.model_validate_json(p.model_dump_json())  # JSON 的鍵都是字串：曆日要換回整數
    assert again.rank2_days == {12: 2} and again == p


def test_real_opportunities_valid(real):
    by_id = {o.id: o for o in real.opportunities if o.rank == 3}  # 第 4 階的六種是乙二加的（test_opportunities_two）
    assert set(by_id) == {
        "guan_zhujun", "guan_courier", "guan_deserter", "huang_zhangliang", "huang_dawn", "huang_talisman",
        "hao_taoqian", "hao_aftermath", "hao_refugees",
    }
    assert all(o.kind in ("bond", "timing", "accumulate") for o in by_id.values())
    assert set(real.orders.rank2) == {"guan", "huang"}
    assert real.orders.rank2["guan"].name == "招降黃巾散兵"


def test_kind_must_match_its_block(real):
    real.opportunities[0] = OppDef(id="bad", name="壞", faction="guan", rank=3, kind="bond")  # bond 卻沒寫 bond
    with pytest.raises(ContentError, match="bad"):
        validate(real)


def _opp(real, opp_id):
    return next(o for o in real.opportunities if o.id == opp_id)


def test_timing_must_name_its_place_and_front(real):
    courier = _opp(real, "guan_courier").timing
    courier.deliver_front = "nowhere"  # 不是戰線
    with pytest.raises(ContentError, match="deliver_front nowhere"):
        validate(real)
    courier.deliver_front = None  # 有 item 卻沒有要送去的戰線
    with pytest.raises(ContentError, match="item 與 deliver_front"):
        validate(real)
    courier.deliver_front, courier.at = "yingru", []  # 夜裡沒寫地點
    with pytest.raises(ContentError, match="夜裡要寫地點"):
        validate(real)


def test_a_timing_item_needs_its_delivery_lines(real):
    courier = _opp(real, "guan_courier").timing
    courier.deliver_label = ""
    with pytest.raises(ContentError, match="guan_courier：有 item 就要寫 deliver_label"):
        validate(real)
    courier.deliver_label, courier.done = "把密信交給{主將}", ""
    with pytest.raises(ContentError, match="guan_courier：有 item 就要寫 done"):
        validate(real)


def test_accumulate_source_must_exist_for_the_faction(real):
    del real.orders.rank2["huang"]
    with pytest.raises(ContentError, match="huang_talisman：來源是第 2 階行動"):
        validate(real)


def test_opportunity_text_must_be_traditional(real):
    _opp(real, "guan_zhujun").bond.text = "朱儁说起自己寒门出身"
    with pytest.raises(ContentError, match="guan_zhujun：文字只能用繁體中文"):
        validate(real)
    real.orders.rank2["guan"].ok = "你放出话去"
    with pytest.raises(ContentError, match="rank2.guan：文字只能用繁體中文"):
        validate(real)


# ── Task 2：機緣的核心與情誼型 ─────────────────────────────────


def test_rank_three_open_to_any_member_rank_four_needs_rank_three(on):
    game = _game(on, faction="guan")
    assert {o.id for o in opportunities.open_ones(game.state, on)} == {"guan_zhujun", "guan_courier", "guan_deserter"}
    assert opportunities.open_ones(_game(on, "乙").state, on) == []  # 散人沒有


def test_rank_four_waits_for_rank_three(on):
    fourth = OppDef(id="guan_four", name="四階", faction="guan", rank=4, kind="bond", bond=on.opportunities[0].bond)
    on.opportunities.append(fourth)
    assert "guan_four" not in {o.id for o in opportunities.open_ones(_game(on, faction="guan", rank=2).state, on)}
    assert "guan_four" in {o.id for o in opportunities.open_ones(_game(on, faction="guan", rank=3).state, on)}


def test_bond_topic_appears_at_the_scaled_affinity(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 7}
    assert "talk:opp:guan_zhujun" not in _ids(game)  # 40 換算成 8，還差 1
    p.affinities["zhujun"] = 8
    option = next(o for o in game.options(odds=False) if o.id == "talk:opp:guan_zhujun")
    assert option.label == "出身"
    msgs = game.choose("talk:opp:guan_zhujun")
    assert msgs[0].startswith("朱儁說起自己寒門出身") and msgs[-1] == "（機緣「朱儁的出身」完成。）"
    assert p.opp_done == ["guan_zhujun"] and opportunities.done_for_rank(game.state, on, 3)
    assert "talk:opp:guan_zhujun" not in _ids(game)  # 每種只完成一次


def test_bond_threshold_is_the_baseline_amount_for_a_big_server(on):
    on.config.server_max_players = 1000  # 1000 人以上那一檔：不換算，情誼要 40
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 39}
    assert "talk:opp:guan_zhujun" not in _ids(game)
    p.affinities["zhujun"] = 40
    assert "talk:opp:guan_zhujun" in _ids(game)


def test_bond_needs_own_faction(on):
    game = _game(on, faction="huang", at="changshe")
    game.state.player.pending_companion, game.state.player.affinities = "zhujun", {"zhujun": 99}
    assert "talk:opp:guan_zhujun" not in _ids(game)


def test_bond_topic_costs_no_stamina_and_no_model(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 8}
    assert game.dialogue_request("talk:opp:guan_zhujun") is None  # 不叫模型（server.prepare_dialogue 靠它判斷）
    before = p.stamina
    game.choose("talk:opp:guan_zhujun")
    assert p.opp_done == ["guan_zhujun"] and p.stamina == before and p.pending_companion == "zhujun"  # 不扣體力、對話還開著


def test_completion_publishes_nothing(on):
    game = _game(on, faction="huang", at="guangzong")
    game.state.player.pending_companion, game.state.player.affinities = "zhangliang", {"zhangliang": 8}
    before = len(game.state.world.rumors)
    game.choose("talk:opp:huang_zhangliang")
    assert len(game.state.world.rumors) == before  # 機緣不發任何傳聞


def test_clear_drops_all_progress():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, opp_done=["a"], opp_counts={"b": 1},
                    opp_items={"c": "信"}, opp_fronts={"c": "yingru"}, opp_clues=["d"], opp_tried={"e": 3})
    opportunities.clear(p)
    assert (p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried) == ([], {}, {}, {}, [], {})


def test_switch_off_no_opportunities(real):
    game = _game(real, faction="guan")
    assert not opportunities.active(game.state, real) and opportunities.open_ones(game.state, real) == []


def test_switch_off_dialogue_menu_unchanged(real):
    game = _game(real, faction="guan", at="changshe")
    game.state.player.pending_companion, game.state.player.affinities = "zhujun", {"zhujun": 99}
    assert not any(i.startswith("talk:opp:") for i in _ids(game))


def test_defection_clears_opportunities(on):
    from tianxia import defection

    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.opp_done = ["guan_zhujun"]
    defection.defect(game.state, on, next(f for f in on.scenario.factions if f.id == "huang"))
    assert game.state.player.opp_done == []


def test_new_season_clears_the_opportunity_fields(on):
    """角色每季重來（同 test_defection 的換季寫法）：七個機緣欄位都回到空的。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    game = _game(on, "甲", faction="guan")
    p = game.state.player
    p.opp_done, p.opp_counts, p.opp_items = ["guan_zhujun"], {"guan_deserter": 1}, {"guan_courier": "南陽渠帥的密信"}
    p.opp_fronts, p.opp_clues, p.opp_tried, p.rank2_days = {"guan_courier": "yingru"}, ["guan_courier"], {"guan_courier": 3}, {5: 2}
    game.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    game.sync(400.0)
    p = game.state.player
    assert p.season_number == 2
    assert (p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried, p.rank2_days) == (
        [], {}, {}, {}, [], {}, {})


# ── Task 3：第 2 階行動與三種累積型 ─────────────────────────────────


def _always(ok=True):
    """檢定一定過（或一定不過）：換掉 rules.check_chance，引擎與 opportunities 呼叫的 roll_check 都讀它。"""
    return mock.patch.object(rules, "check_chance", return_value=1.0 if ok else 0.0)


class _Roll(random.Random):
    """random() 永遠回傳固定值，讓流民的機率可以預測。"""

    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


def test_rank2_action_needs_rank_two_and_a_front(on):
    game = _game(on, faction="guan", at="changshe", rank=1)
    assert "act:rank2" not in _ids(game)
    game.state.player.rank = 2
    option = next(o for o in game.options(odds=False) if o.id == "act:rank2")
    assert option.label == "招降黃巾散兵（體力 15）"
    game.state.player.location = "luoyang_palace"  # 洛陽沒有戰線
    assert "act:rank2" not in _ids(game)


def test_rank2_action_is_each_factions_own(on):
    huang = _game(on, faction="huang", at="julu_altar", rank=2)
    assert next(o for o in huang.options(odds=False) if o.id == "act:rank2").label == "施符水收人心（體力 15）"
    assert "act:rank2" not in _ids(_game(on, faction="haoqiang", at="cao_manor", rank=2))  # 豪強這一版沒有第 2 階行動
    assert "act:rank2" not in _ids(_game(on, at="changshe", rank=2))  # 散人沒有


def test_rank2_costs_stamina_and_is_greyed_without_it(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.stamina = 20
    with _always(True):
        game.choose("act:rank2")
    assert p.stamina == 5
    option = next(o for o in game.options(odds=False) if o.id == "act:rank2")
    assert not option.enabled


def test_rank2_success_pushes_and_counts_toward_deserters(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    game.state.player.stamina = 100
    with _always(True):
        first = game.choose("act:rank2")
        assert first[0].startswith("你在長社放出話去")
        second = game.choose("act:rank2")
    p = game.state.player
    assert p.opp_items == {"guan_deserter": "知道運糧小道的降卒"} and p.opp_fronts == {"guan_deserter": "yingru"}
    assert any(m.startswith("第 2 個降卒是") and "的舊部" in m for m in second)  # 10 換算成 2


def test_rank2_success_pushes_the_local_front_towards_its_own_side(on):
    guan = _game(on, faction="guan", at="changshe", rank=2)
    before = rules.trend_value(guan.state, on, "yingru")
    with _always(True):
        guan.choose("act:rank2")
    assert rules.trend_value(guan.state, on, "yingru") == before - 3  # rank2_push 3，往官軍偏
    # 走 Game.push_trend（不是直接 change_trend）：替自己陣營推，貢獻照 contrib_per_push 記
    assert guan.state.player.contrib == on.config.contrib_per_push * on.config.rank2_push
    huang = _game(on, faction="huang", at="julu_altar", rank=2)
    before = rules.trend_value(huang.state, on, "jizhou")
    with _always(True):
        huang.choose("act:rank2")
    assert rules.trend_value(huang.state, on, "jizhou") == before + 3  # 往黃巾偏
    assert huang.state.player.contrib == on.config.contrib_per_push * on.config.rank2_push


def test_rank2_push_goes_through_the_daily_cap(on):
    on.config.daily_push_cap = 4  # 每人每曆日每條線推得動 4 點
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.stamina = 100
    before = rules.trend_value(game.state, on, "yingru")
    with _always(True):
        game.choose("act:rank2")
        game.choose("act:rank2")
    assert rules.trend_value(game.state, on, "yingru") == before - 4  # 3 加 1，不是 6：超過上限的不推
    cfg = on.config  # 超過上限的那一份貢獻只記 over_cap_contrib_ratio
    assert p.contrib == cfg.contrib_per_push * 3 + push.contribution(3, 3, 1, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)


def test_rank2_failure_counts_a_try_but_not_a_deserter(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    before = rules.trend_value(game.state, on, "yingru")
    with _always(False):
        msgs = game.choose("act:rank2")
    assert msgs[0].startswith("你在長社喊了半天") and game.state.player.opp_counts == {}
    assert sum(game.state.player.rank2_days.values()) == 1
    assert rules.trend_value(game.state, on, "yingru") == before  # 失敗不推戰線
    assert game.state.player.contrib == 0  # 也不記貢獻


def test_rank2_daily_limit_resets_next_day(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    game.state.player.stamina = 100
    with _always(False):
        for _ in range(3):
            game.choose("act:rank2")
    option = next(o for o in game.options(odds=False) if o.id == "act:rank2")
    assert not option.enabled and "今天已經做滿 3 次" in option.label
    w = game.state.world
    w.time += calendar.DAY / calendar.cal_scale(on, w)  # 隔一個曆日
    assert next(o for o in game.options(odds=False) if o.id == "act:rank2").enabled


def test_rank2_daily_limit_resets_at_calendar_midnight(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    game.state.player.stamina = 100
    _at_hour(game, 23)  # 第 1 曆日 23:00
    with _always(False):
        for _ in range(3):
            game.choose("act:rank2")
    for hour in (23, 23.9):
        _at_hour(game, hour)
        option = next(o for o in game.options(odds=False) if o.id == "act:rank2")
        assert not option.enabled and "今天已經做滿 3 次" in option.label
    _at_hour(game, 0.5, day=1)  # 第 2 曆日 00:30：只隔 1.5 個曆時，但曆日換了；滾動 24 小時的算法在這裡還是灰的
    assert next(o for o in game.options(odds=False) if o.id == "act:rank2").enabled


def test_rank2_not_offered_when_the_switch_is_off(real):
    game = _game(real, faction="guan", at="changshe", rank=2)
    assert not any(i.startswith(("act:rank2", "opp:")) for i in _ids(game))


def test_deserter_count_is_the_baseline_amount_for_a_big_server(on):
    on.config.server_max_players = 1000  # 不換算：要 10 個降卒
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    with _always(True):
        for _ in range(9):
            p.stamina, p.rank2_days = 100, {}  # 每天只能做 3 次：這個測試不測限次，每回清掉
            game.choose("act:rank2")
        assert p.opp_items == {} and p.opp_counts == {"guan_deserter": 9}
        p.stamina, p.rank2_days = 100, {}
        msgs = game.choose("act:rank2")
    assert any(m.startswith("第 10 個降卒是") for m in msgs) and p.opp_items


def test_no_more_counting_while_holding_the_item(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.opp_counts, p.opp_items, p.opp_fronts = {"guan_deserter": 2}, {"guan_deserter": "降卒"}, {"guan_deserter": "yingru"}
    p.stamina = 100
    with _always(True):
        game.choose("act:rank2")
    assert p.opp_counts == {"guan_deserter": 2}


def test_deliver_goes_to_whoever_commands_now(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.opp_items, p.opp_fronts = {"guan_deserter": "知道運糧小道的降卒"}, {"guan_deserter": "yingru"}
    option = next(o for o in game.options(odds=False) if o.id == "opp:deliver:guan_deserter")
    assert option.label == "把降卒帶給皇甫嵩"  # 潁川此刻的官軍主將
    game.state.world.figures["huangfusong"] = figures.state_of(game.state, on, "huangfusong").model_copy(update={"status": "retired"})
    option = next(o for o in game.options(odds=False) if o.id == "opp:deliver:guan_deserter")
    assert option.label == "把降卒帶給朱儁"  # 主將換人：交給接手的人
    for fid in ("huangfusong", "zhujun"):  # 潁川一個官軍人物都沒有：交給那條戰線上的官軍投靠點
        game.state.world.figures[fid] = figures.state_of(game.state, on, fid).model_copy(update={"status": "retired"})
    option = next(o for o in game.options(odds=False) if o.id == "opp:deliver:guan_deserter")
    assert option.label == "把降卒帶給官軍的主將"
    before = rules.trend_value(game.state, on, "yingru")
    msgs = game.choose("opp:deliver:guan_deserter")
    assert msgs[-1] == "（機緣「降卒的消息」完成。）" and p.opp_items == {}
    assert rules.trend_value(game.state, on, "yingru") == before - 1  # 往官軍偏 1


def test_deliver_needs_the_commander_to_be_there(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.opp_items, p.opp_fronts = {"guan_deserter": "降卒"}, {"guan_deserter": "yingru"}
    here = figures.state_of(game.state, on, "huangfusong")
    game.state.world.figures["huangfusong"] = here.model_copy(update={"location": "luoyang_road"})  # 主將還在，卻不在這裡
    assert "opp:deliver:guan_deserter" not in _ids(game)
    p.location = "luoyang_road"
    assert "opp:deliver:guan_deserter" in _ids(game)


def test_deliver_only_for_the_front_the_deserter_came_from(on):
    game = _game(on, faction="guan", at="wan_city", rank=2)  # 南陽的官軍大營
    p = game.state.player
    p.opp_items, p.opp_fronts = {"guan_deserter": "降卒"}, {"guan_deserter": "yingru"}
    assert "opp:deliver:guan_deserter" not in _ids(game)  # 降卒是潁川的，要帶去潁川的主將那裡


def test_talisman_delivered_at_any_huang_base(on):
    game = _game(on, faction="huang", at="julu_altar", rank=2)
    p = game.state.player
    p.opp_items, p.opp_fronts = {"huang_talisman": "信眾名冊"}, {"huang_talisman": "nanyang"}
    before = rules.trend_value(game.state, on, "jizhou")
    msgs = game.choose("opp:deliver:huang_talisman")
    assert msgs[-1] == "（機緣「符水救人」完成。）"
    assert rules.trend_value(game.state, on, "jizhou") == before + 1  # 交到哪個據點，就推那裡的戰線


def test_talisman_not_deliverable_off_base(on):
    game = _game(on, faction="huang", at="guangzong", rank=2)
    game.state.player.opp_items = {"huang_talisman": "信眾名冊"}
    assert "opp:deliver:huang_talisman" not in _ids(game)


def test_refugees_roll_after_duty(on):
    game = _game(on, faction="haoqiang", at="cao_manor")
    game.state.player.stamina = 100
    _opp(on, "hao_refugees").accumulate.chance = 1.0  # 每次都遇到流民
    game.choose("act:duty")
    msgs = game.choose("act:duty")
    assert any(m.startswith("第 2 批流民裡有個老人說") for m in msgs)
    assert game.state.player.opp_items == {"hao_refugees": "佃戶名冊"}
    before = rules.trend_value(game.state, on, "geju")
    game.choose("opp:deliver:hao_refugees")
    assert rules.trend_value(game.state, on, "geju") == before + 1


def test_geju_push_on_delivery_follows_the_goals_sign(on):
    haoqiang = next(f for f in on.scenario.factions if f.id == "haoqiang")
    haoqiang.goals[rules.GEJU] = -1  # 假設有個陣營要把割據往下壓：跟戰線那一支一樣是 目標 × 次數
    game = _game(on, faction="haoqiang", at="cao_manor")
    game.state.player.opp_items = {"hao_refugees": "佃戶名冊"}
    before = rules.trend_value(game.state, on, rules.GEJU)
    game.choose("opp:deliver:hao_refugees")
    assert rules.trend_value(game.state, on, rules.GEJU) == before - 1


def test_refugees_come_with_their_chance(on):
    game = _game(on, faction="haoqiang", at="cao_manor")
    p = game.state.player
    p.stamina = 100
    game.rng = _Roll(0.9)  # 機緣文件的 30%：0.9 遇不到
    assert not any("流民" in m for m in game.choose("act:duty"))
    assert p.opp_counts == {}
    game.rng = _Roll(0.1)
    assert any(m.startswith("一群逃難的流民跟在你身後") and "曹氏莊院" in m for m in game.choose("act:duty"))
    assert p.opp_counts == {"hao_refugees": 1}


def test_other_factions_dont_meet_refugees(on):
    game = _game(on, faction="guan", at="changshe")
    game.state.player.stamina = 100
    _opp(on, "hao_refugees").accumulate.chance = 1.0
    game.choose("act:duty")
    assert game.state.player.opp_counts == {}


def test_opportunity_entries_are_titled(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    game.state.player.stamina = 100
    with _always(False):
        game.choose("act:rank2")
    assert game.state.journal[0].title == "招降黃巾散兵・長社"
    game.state.player.opp_items, game.state.player.opp_fronts = {"guan_deserter": "降卒"}, {"guan_deserter": "yingru"}
    game.choose("opp:deliver:guan_deserter")
    assert game.state.journal[0].title == "機緣・降卒的消息"


# ── Task 4：三種天時地利型與線索 ─────────────────────────────────


def _at_hour(game, hour, day=0):
    w = game.state.world
    w.time = (day * 24 + hour) * calendar.HOUR / calendar.cal_scale(game.content, w)


def _try(game, opp_id):
    return next((o for o in game.options(odds=False) if o.id == f"opp:try:{opp_id}"), None)


def test_courier_only_at_night_on_the_hilltop(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    _at_hour(game, 12)
    assert "opp:try:guan_courier" not in _ids(game)
    _at_hour(game, 23)
    option = next(o for o in game.options(odds=False) if o.id == "opp:try:guan_courier")
    assert option.label == "埋伏在荒丘攔信使（體力 10）"
    with _always(True):
        msgs = game.choose("opp:try:guan_courier")
    assert msgs[0].startswith("三更時分") and game.state.player.opp_items == {"guan_courier": "南陽渠帥的密信"}
    assert game.state.player.opp_fronts == {"guan_courier": "yingru"}


def test_courier_hours_are_the_calendar_night(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    for hour, open_ in ((22, False), (23, True), (0, True), (4, True), (5, False)):  # 子時到寅時 23:00～04:59
        _at_hour(game, hour)
        assert (_try(game, "guan_courier") is not None) == open_, hour
    _at_hour(game, 23)
    game.state.player.location = "changshe"  # 不在荒丘
    assert _try(game, "guan_courier") is None


def test_night_retry_waits_for_the_next_night(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    _at_hour(game, 23)
    with _always(False):
        assert game.choose("opp:try:guan_courier")[0].startswith("黑影一閃")
    _at_hour(game, 2, day=1)  # 同一夜的 02:00
    option = next(o for o in game.options(odds=False) if o.id == "opp:try:guan_courier")
    assert not option.enabled and "這一回已經試過" in option.label
    _at_hour(game, 23, day=1)  # 下一夜
    assert next(o for o in game.options(odds=False) if o.id == "opp:try:guan_courier").enabled


def test_a_failed_night_costs_stamina_and_cannot_be_forced_again(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    p = game.state.player
    p.stamina = 30
    _at_hour(game, 23)
    with _always(False):
        game.choose("opp:try:guan_courier")
        assert p.stamina == 20
        assert game.choose("opp:try:guan_courier") == ["（此刻無法這麼做。）"]  # 灰的選項按不下去
    assert p.stamina == 20


def test_courier_without_stamina_is_greyed(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    game.state.player.stamina = 9
    _at_hour(game, 23)
    assert not _try(game, "guan_courier").enabled


def test_courier_letter_goes_to_the_yingchuan_commander(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    _at_hour(game, 23)
    with _always(True):
        game.choose("opp:try:guan_courier")
    assert _try(game, "guan_courier") is None  # 密信在手上，不再出攔截的選項
    assert "opp:deliver:guan_courier" not in _ids(game)  # 荒丘不是主將所在
    game.state.player.location = "changshe"
    option = next(o for o in game.options(odds=False) if o.id == "opp:deliver:guan_courier")
    assert option.label == "把密信交給皇甫嵩"
    msgs = game.choose("opp:deliver:guan_courier")
    assert msgs[0].startswith("皇甫嵩把信看了兩遍") and msgs[-1] == "（機緣「荒丘的信使」完成。）"
    assert game.state.player.opp_items == {} and "guan_courier" in game.state.player.opp_done


def test_dawn_rite_completes_on_a_pass(on):
    game = _game(on, faction="huang", at="xiaquyang")
    _at_hour(game, 5)
    option = next(o for o in game.options(odds=False) if o.id == "opp:try:huang_dawn")
    assert option.label == "替張寶捧旗祭天（體力 10）"
    with _always(True):
        msgs = game.choose("opp:try:huang_dawn")
    assert "張寶在祭壇上看了你一眼" in msgs[0] and msgs[-1] == "（機緣「黎明祭天」完成。）"


def test_dawn_rite_only_at_the_hour_of_mao(on):
    game = _game(on, faction="huang", at="xiaquyang")
    for hour, open_ in ((4, False), (5, True), (6, True), (7, False)):  # 卯時 05:00～06:59
        _at_hour(game, hour)
        assert (_try(game, "huang_dawn") is not None) == open_, hour


def test_dawn_failure_waits_for_tomorrows_dawn(on):
    game = _game(on, faction="huang", at="xiaquyang")
    _at_hour(game, 5)
    with _always(False):
        assert game.choose("opp:try:huang_dawn")[0].startswith("一陣狂風，黃旗歪了一下。張寶沒說什麼")
    _at_hour(game, 6)
    assert not _try(game, "huang_dawn").enabled  # 同一個黎明不能再試
    _at_hour(game, 5, day=1)
    assert _try(game, "huang_dawn").enabled


def test_dawn_host_falls_back_to_zhangliang(on):
    game = _game(on, faction="huang", at="xiaquyang")
    _at_hour(game, 5)
    w = game.state.world
    w.figures["zhangbao"] = figures.state_of(game.state, on, "zhangbao").model_copy(update={"status": "retired"})
    assert "opp:try:huang_dawn" not in _ids(game)  # 下曲陽沒人主持
    game.state.player.location = "guangzong"
    assert next(o for o in game.options(odds=False) if o.id == "opp:try:huang_dawn").label.startswith("替張梁捧旗")
    w.figures["zhangliang"] = figures.state_of(game.state, on, "zhangliang").model_copy(update={"status": "retired"})
    assert "opp:try:huang_dawn" not in _ids(game)


def test_dawn_at_guangzong_waits_while_zhangbao_presides(on):
    game = _game(on, faction="huang", at="guangzong")
    _at_hour(game, 5)
    assert "opp:try:huang_dawn" not in _ids(game)  # 張寶還在下曲陽主持，廣宗不必


def test_dawn_host_who_has_left_xiaquyang_hands_over(on):
    game = _game(on, faction="huang", at="guangzong")
    _at_hour(game, 5)
    w = game.state.world
    w.figures["zhangbao"] = figures.state_of(game.state, on, "zhangbao").model_copy(update={"location": "julu_altar"})
    assert next(o for o in game.options(odds=False) if o.id == "opp:try:huang_dawn").label.startswith("替張梁捧旗")


def test_aftermath_within_a_day_of_a_showdown_on_its_front(on):
    game = _game(on, faction="haoqiang", at="yingchuan_wilds")
    w = game.state.world
    assert "opp:try:hao_aftermath" not in _ids(game)  # 還沒打過決戰
    w.timeline["changshe_fire"] = TimelineResult(key="guan:大勝", time=w.time)
    assert "opp:try:hao_aftermath" in _ids(game)  # 長社在潁川汝南，潁川郊野是野外
    game.state.player.location = "yingchuan"  # 城鎮不算
    assert "opp:try:hao_aftermath" not in _ids(game)
    game.state.player.location = "yingchuan_wilds"
    w.time += 2 * calendar.DAY / calendar.cal_scale(on, w)  # 過了一個曆日
    assert "opp:try:hao_aftermath" not in _ids(game)


def test_aftermath_only_on_the_front_of_that_showdown(on):
    game = _game(on, faction="haoqiang", at="nanyang_wilds")
    w = game.state.world
    w.timeline["changshe_fire"] = TimelineResult(key="guan:大勝", time=w.time)  # 潁川汝南的決戰，南陽郊野不算
    assert "opp:try:hao_aftermath" not in _ids(game)
    w.timeline["wancheng"] = TimelineResult(key="甲:huang:大勝", time=w.time)
    assert "opp:try:hao_aftermath" in _ids(game)


def test_a_skipped_showdown_leaves_no_aftermath(on):
    game = _game(on, faction="haoqiang", at="yingchuan_wilds")
    w = game.state.world
    w.timeline["changshe_fire"] = TimelineResult(key=timetable.SKIPPED, time=w.time)  # 沒有打過
    assert "opp:try:hao_aftermath" not in _ids(game)


def test_aftermath_completes_on_a_pass(on):
    game = _game(on, faction="haoqiang", at="yingchuan_wilds")
    w = game.state.world
    w.timeline["changshe_fire"] = TimelineResult(key="guan:大勝", time=w.time)
    with _always(True):
        msgs = game.choose("opp:try:hao_aftermath")
    assert msgs[0].startswith("你在戰場邊上收攏了一群逃散的佃農") and msgs[-1] == "（機緣「戰後的地」完成。）"


def test_aftermath_failure_can_retry_in_the_window(on):
    game = _game(on, faction="haoqiang", at="yingchuan_wilds")
    w = game.state.world
    w.timeline["changshe_fire"] = TimelineResult(key="guan:大勝", time=w.time)
    with _always(False):
        game.choose("opp:try:hao_aftermath")
    assert next(o for o in game.options(odds=False) if o.id == "opp:try:hao_aftermath").enabled


def test_timing_options_need_the_switch(real):
    off = _game(real, faction="guan", at="hilltop_wilds")
    _at_hour(off, 23)
    assert not any(i.startswith("opp:") for i in _ids(off))  # 開關關著


def test_timing_options_are_only_for_the_own_faction(on):
    other = _game(on, faction="huang", at="hilltop_wilds")
    _at_hour(other, 23)
    assert "opp:try:guan_courier" not in _ids(other)  # 別的陣營的機緣


def test_clue_heard_once_in_its_region(on):
    game = _game(on, faction="guan")
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[0])
    assert opportunities.hear_clues(game.state, on, "jizhou", rng) == []  # 荒丘的線索只在潁川汝南
    first = opportunities.hear_clues(game.state, on, "yingru", rng)
    assert first and "荒丘那條官道" in first[0]
    assert opportunities.hear_clues(game.state, on, "yingru", rng) == []  # 只聽一次


def test_clue_without_a_region_restriction_is_heard_anywhere(on):
    game = _game(on, faction="haoqiang")
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[0])
    heard = opportunities.hear_clues(game.state, on, "luoyang", rng)
    assert heard and "地最便宜" in heard[0]
    assert opportunities.hear_clues(game.state, on, None, rng) == []  # 沒有大區（路上）不抽


def test_clue_only_at_the_fragment_chance(on):
    game = _game(on, faction="guan")
    rng = mock.Mock(random=mock.Mock(return_value=0.99), choice=lambda xs: xs[0])  # 骰不中
    assert opportunities.hear_clues(game.state, on, "yingru", rng) == []
    assert game.state.player.opp_clues == []


def test_clue_goes_to_the_journal_line_and_no_rumour(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    before_rumors, before = len(game.state.world.rumors), p.stamina
    game.rng = _Roll(0.0)  # 一定聽到
    p.stamina -= 5  # 剛花了體力的行動
    heard = game._hear_after_stamina(before)
    assert any(m.startswith("你聽到一件事：南陽和潁川的黃巾") for m in heard)
    assert p.opp_clues == ["guan_courier"] and len(game.state.world.rumors) == before_rumors
    assert game._hear_after_stamina(p.stamina) == []  # 沒花體力的行動不抽


def test_clues_stay_quiet_when_the_switch_is_off(real):
    game = _game(real, faction="guan", at="changshe")
    game.rng = _Roll(0.0)
    before = game.state.player.stamina
    game.state.player.stamina -= 5
    assert game._hear_after_stamina(before) == [] and game.state.player.opp_clues == []


# ── Task 5：假人與整季機器人 ─────────────────────────────────


def _profile(faction="guan"):
    return BotProfile(personality="普通", seed=1, faction=faction, season_number=1)


def test_bots_skip_opportunities_but_do_rank2(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.opp_items, p.opp_fronts = {"guan_deserter": "知道運糧小道的降卒"}, {"guan_deserter": "yingru"}
    options = game.options(odds=False)
    opp = [o for o in options if o.id.startswith("opp:")]
    assert opp and bot.pick(game, opp, random.Random(0)) is None
    profile = _profile()
    assert all(bot_policy.score(game, o, profile) is None for o in opp)
    rank2 = next(o for o in options if o.id == "act:rank2")
    assert bot_policy.score(game, rank2, profile) is not None


def test_bots_skip_the_bond_topics_too(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 8}
    topic = next(o for o in game.options(odds=False) if o.id == "talk:opp:guan_zhujun")
    assert bot.pick(game, [topic], random.Random(0)) is None
    assert bot_policy.score(game, topic, _profile()) is None


def test_bots_skip_the_timing_attempts_too(on):
    game = _game(on, faction="guan", at="hilltop_wilds")
    _at_hour(game, 23)
    attempt = _try(game, "guan_courier")
    assert attempt is not None and attempt.enabled
    assert bot.pick(game, [attempt], random.Random(0)) is None
    assert bot_policy.score(game, attempt, _profile()) is None


def test_rank2_scores_like_the_duty_action_for_bots(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    options = {o.id: o for o in game.options(odds=False)}
    assert bot_policy.score(game, options["act:rank2"], _profile()) == bot_policy.DUTY_SCORE
    assert bot_policy.score(game, options["act:rank2"], _profile()) == bot_policy.score(game, options["act:duty"], _profile())


def test_server_bots_never_choose_an_opportunity(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    p = game.state.player
    p.opp_items, p.opp_fronts = {"guan_deserter": "知道運糧小道的降卒"}, {"guan_deserter": "yingru"}
    chosen = []
    real_choose = game.choose
    with mock.patch.object(game, "choose", side_effect=lambda option_id, *a, **k: chosen.append(option_id) or real_choose(option_id, *a, **k)):
        for seed in range(40):
            p.stamina = 100
            p.location, p.pending_companion = "changshe", None
            bot_policy.take_turn(game, _profile(), random.Random(seed))
    assert chosen and not any(i.startswith(("opp:", "talk:opp:")) for i in chosen)
