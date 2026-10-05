"""第一季濃縮版 T4：大勢人物、聲威、敗走與接手（計畫 2026-10-04-T4）。

規則與引擎的測試大多用真實內容（content/）：要驗的就是濃縮版內容表第一節的 14 位人物、他們的戰線與接位鏈。
每個測試自己載一份，開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

import random
import re
from unittest import mock

from conftest import FixedRandom
from tianxia import atlas, battle_instance, bot_policy, calendar, figures, rules, team, timetable, world
from tianxia.encounter import EncounterResult
from tianxia.engine import Game, Option
from tianxia.events import event_candidates
from tianxia.state import BotProfile, FigureState, GameState, PlayerState
from tianxia.content import ContentError, load_content, validate
from tianxia.models import Config, FigureChange
from tianxia.server_bots import reserved_names
from tianxia.world_state import fresh_season

CONTENT_DIR = Path(__file__).parent.parent / "content"

# 濃縮版內容表 1.1（企劃者已審）：id → (character, name, faction, front, location, destiny, start_prestige,
# actions_per_day, push, successor, active_from_week, start_status)；squad 一律是 figure_<id>
FIGURE_TABLE = {
    "bocai": ("bocai", "波才", "huang", "yingru", "huangjin_camp", False, 60, 1, 1, "pengtuo", 1, "active"),
    "pengtuo": (None, "彭脫", "huang", None, "huangjin_camp", False, 40, 1, 1, None, 1, "away"),
    "zhangmancheng": ("zhangmancheng", "張曼成", "huang", "nanyang", "nanyang_huangjin_camp", False, 50, 1, 1, "zhaohong", 1, "active"),
    "zhaohong": ("zhaohong", "趙弘", "huang", None, "nanyang_huangjin_camp", False, 50, 1, 1, "hanzhong", 1, "active"),
    "hanzhong": (None, "韓忠", "huang", None, "nanyang_huangjin_camp", False, 40, 1, 1, None, 1, "away"),
    "zhangjiao": ("zhangjiao", "張角", "huang", "jizhou", "guangzong", False, 80, 0.5, 1, None, 1, "active"),
    "zhangbao": ("zhangbao", "張寶", "huang", "jizhou", "xiaquyang", False, 60, 0.5, 1, None, 1, "active"),
    "zhangliang": ("zhangliang", "張梁", "huang", "jizhou", "guangzong", False, 60, 0.5, 1, None, 1, "active"),
    "huangfusong": ("huangfusong", "皇甫嵩", "guan", "yingru", "changshe", False, 70, 1, 1, "zhujun", 2, "active"),
    "zhujun": ("zhujun", "朱儁", "guan", "yingru", "changshe", False, 60, 0.5, 1, None, 2, "active"),
    "luzhi": ("luzhi", "盧植", "guan", "jizhou", "luzhi_camp", False, 70, 1, 1, "dongzhuo", 2, "active"),
    "sunjian": ("sunjian", "孫堅", "guan", "nanyang", "wan_city", True, 60, 1, 1, None, 2, "active"),
    "hejin": ("hejin", "何進", "guan", None, "dajiangjun_fu", True, 70, 0, 0, None, 1, "active"),
    "dongzhuo": ("dongzhuo", "董卓", "guan", None, "mengjin_ford", True, 60, 1, 1, None, 1, "active"),
}
# 濃縮版內容表 1.4：figure_<id> → (name, difficulty, attribute, faction)；難度是聲威 100 時的值
SQUAD_TABLE = {
    "bocai": ("波才", 150, "剛", "huang"), "pengtuo": ("彭脫", 110, "剛", "huang"),
    "zhangmancheng": ("張曼成", 130, "柔", "huang"), "zhaohong": ("趙弘", 130, "實", "huang"),
    "hanzhong": ("韓忠", 110, "實", "huang"), "zhangjiao": ("張角", 160, "柔", "huang"),
    "zhangbao": ("張寶", 140, "快", "huang"), "zhangliang": ("張梁", 150, "剛", "huang"),
    "huangfusong": ("皇甫嵩", 150, "實", "guan"), "zhujun": ("朱儁", 140, "實", "guan"),
    "luzhi": ("盧植", 140, "柔", "guan"), "sunjian": ("孫堅", 150, "快", "guan"),
    "hejin": ("何進", 100, "虛", "guan"), "dongzhuo": ("董卓", 160, "剛", "guan"),
}


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0  # 遊歷打完不接戰後事件，結果才寫得死
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，開關打開（第一季濃縮版）。"""
    real.config.season_one = True
    return real


# ── Task 1：人物表與檢查 ─────────────────────────────────


def test_real_figures_valid(real):
    """14 位照內容表 1.1；人物、隊伍、地點都存在，開季時站在對話人物的 talk_at，接位鏈沒有環；代表本人的隊伍照 1.4。"""
    assert list(real.figures) == list(FIGURE_TABLE)
    for fid, row in FIGURE_TABLE.items():
        fig = real.figures[fid]
        got = (fig.character, fig.name, fig.faction, fig.front, fig.location, fig.destiny, fig.start_prestige,
               fig.actions_per_day, fig.push, fig.successor, fig.active_from_week, fig.start_status)
        assert got == row, fid
        assert fig.squad == f"figure_{fid}"
        squad = real.squads[fig.squad]
        assert (squad.name, squad.difficulty, squad.attribute, squad.faction) == SQUAD_TABLE[fid], fid
        assert (squad.reward_xinde, squad.exp, squad.drops) == (80, 80, [])  # 照舊的波才隊伍；素材走依難度的預設表
        if fig.character is not None:
            assert real.characters[fig.character].talk_at == fig.location, fid
        chain, nxt = {fid}, fig.successor
        while nxt is not None:
            assert nxt not in chain, fid
            chain.add(nxt)
            nxt = real.figures[nxt].successor
    assert real.squads["fanjianglong"].name == "波才"  # beta 的波才（kou_boss）照留


def test_content_without_figures_loads(content):
    """測試夾具沒有 figures.json：照舊載得進來，人物表是空的。"""
    assert content.figures == {}


def test_figure_settings_defaults():
    cfg = Config()
    assert (cfg.figure_reaction_lean, cfg.figure_reaction_mult, cfg.figure_defeat_prestige, cfg.figure_defeat_affinity,
            cfg.snub_hours, cfg.figure_difficulty_floor) == (15, 2.0, 5, 5, 2.0, 0.5)


@pytest.mark.parametrize(("edit", "message"), [
    (lambda c: setattr(c.figures["bocai"], "character", "ghost"), "ghost"),
    (lambda c: setattr(c.figures["zhujun"], "character", "huangfusong"), "huangfusong"),  # 一個對話人物只能是一位
    (lambda c: setattr(c.figures["bocai"], "character", "caocao"), "bocai：對話人物要跟人物 id 一樣"),  # 伏筆用人物 id 找他的狀態
    (lambda c: setattr(c.figures["bocai"], "faction", "nobody"), "nobody"),
    (lambda c: setattr(c.figures["bocai"], "front", "youzhou"), "youzhou"),  # 戰線 id，不是大區
    (lambda c: setattr(c.figures["bocai"], "location", "nowhere"), "nowhere"),
    (lambda c: setattr(c.figures["bocai"], "squad", "ghost_squad"), "ghost_squad"),
    (lambda c: setattr(c.figures["bocai"], "squad", "figure_luzhi"), "陣營"),  # 隊伍跟人物同一個陣營
    (lambda c: setattr(c.figures["bocai"], "successor", "ghost"), "ghost"),
    (lambda c: setattr(c.figures["bocai"], "successor", "zhujun"), "同一個陣營"),
    (lambda c: setattr(c.figures["pengtuo"], "successor", "bocai"), "接位鏈"),  # 繞回來
    (lambda c: setattr(c.figures["bocai"], "active_from_week", 13), "13"),
    (lambda c: setattr(c.figures["bocai"], "name", "张曼成"), "繁體"),
])
def test_validate_checks_the_figures(real, edit, message):
    edit(real)
    with pytest.raises(ContentError, match=message):
        validate(real)


def test_timetable_figures_are_checked_against_the_figure_table(real):
    """有人物表時，時刻表的人物效果認的是人物表的 id：彭脫不在 characters.json 也認得，曹操是人物、不是大勢人物。"""
    outcome = next(e for e in real.timetable if e.id == "changshe_fire").outcomes["guan:大勝"]
    outcome.figures["pengtuo"] = FigureChange(fate="受挫")
    validate(real)
    outcome.figures["caocao"] = FigureChange(fate="受挫")
    with pytest.raises(ContentError, match="caocao"):
        validate(real)


def test_figure_names_are_reserved(real):
    """彭脫、韓忠沒有對話人物，名字照樣不能拿來當名號（公告寫的就是他們）。"""
    assert {"彭脫", "韓忠", "波才"} <= reserved_names(real)


# ── Task 2：種人物、讀人物 ───────────────────────────────


def _season(content) -> GameState:
    """真實內容的一季（照當下的設定蓋章、種人物）＋季的事用的那種空殼玩家。"""
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def test_figures_are_seeded_when_the_season_opens_with_the_switch_on(on):
    season = fresh_season(on)
    assert list(season.figures) == list(FIGURE_TABLE)
    assert season.figures["bocai"] == FigureState(prestige=60, status="active", front="yingru", location="huangjin_camp")
    assert season.figures["pengtuo"].status == "away"
    assert season.figures["zhaohong"] == FigureState(prestige=50, front=None, location="nanyang_huangjin_camp")  # 在地圖上、不推


def test_no_figures_are_seeded_with_the_switch_off(real):
    assert fresh_season(real).figures == {}  # beta 那一季的存檔跟以前一樣


def test_opening_a_season_seeded_with_the_switch_off_seeds_the_figures(real, world):
    """第一次啟動忘了設 weekend：籌備中的季蓋的是「關」、沒有人物；設好重開、管理者開季時照新的章種好。"""
    real.config.auto_open_first_season = False
    world.seed_first_season(real)
    assert world.get_season().figures == {}
    real.config.season_one = True
    assert world.open_season(real, now=0.0)
    assert list(world.get_season().figures) == list(FIGURE_TABLE)


def test_state_of_reads_the_table_for_a_figure_the_season_never_seeded(on):
    """Review Focus 2：T4 之前就蓋了「開」的章的季（或季中才加進人物表的人）存檔裡沒有他——照人物表的起始值讀，
    主將、難度都算得出來，讀了也不寫回存檔。"""
    s = _season(on)
    s.world.figures = {}
    assert figures.state_of(s, on, "huangfusong") == FigureState(
        prestige=70, status="active", front="yingru", location="changshe",
    )
    assert figures.commander(s, on, "yingru", "guan") == "huangfusong"
    assert figures.difficulty(s, on, "huangfusong") == 128  # 150 × (0.5 + 0.5 × 0.70) = 127.5 → 128
    assert figures.present_at(s, on, "huangjin_camp") == ["bocai"]
    assert s.world.figures == {}


def test_t2_minimal_entry_without_a_location_is_read_from_the_table(on):
    """T4 之前蓋「開」的章的季，人物表上被時刻表碰過的人存的是 T2 最小版的預設值（沒有所在、戰線是空的）：
    讀的時候用人物表補上所在與戰線（聲威、狀態照存檔），讀了不寫回存檔；要改的時候（_ensure）才把補好的寫進存檔。
    不補的話張曼成不在任何地點、挑戰不了、不推南陽、退場也沒人接。"""
    s = _season(on)
    minimal = FigureState(prestige=45, status="active", front=None, location="")
    s.world.figures["zhangmancheng"] = minimal.model_copy()
    repaired = FigureState(prestige=45, status="active", front="nanyang", location="nanyang_huangjin_camp")
    assert figures.state_of(s, on, "zhangmancheng") == repaired
    assert s.world.figures["zhangmancheng"] == minimal  # 讀不改存檔
    assert "zhangmancheng" in figures.present_at(s, on, "nanyang_huangjin_camp")
    assert figures.commander(s, on, "nanyang", "huang") == "zhangmancheng"
    assert figures.push_goal(s, on, "zhangmancheng") == 1
    assert figures._ensure(s, on, "zhangmancheng") == repaired
    assert s.world.figures["zhangmancheng"] == repaired  # 要改之前才寫回


def test_t2_minimal_entry_that_is_not_active_only_gets_its_location(on):
    """補戰線只補在場的人：T2 最小版裡下獄的人所在補上、戰線照存檔（沒有）；表上本來就沒有戰線的人（趙弘）補完還是沒有。"""
    s = _season(on)
    s.world.figures["luzhi"] = FigureState(prestige=70, status="jailed", front=None, location="")
    s.world.figures["zhaohong"] = FigureState(prestige=50, status="active", front=None, location="")
    assert figures.state_of(s, on, "luzhi") == FigureState(prestige=70, status="jailed", front=None, location="luzhi_camp")
    assert figures.state_of(s, on, "zhaohong") == FigureState(
        prestige=50, status="active", front=None, location="nanyang_huangjin_camp",
    )


def test_entry_with_a_location_is_read_as_stored(on):
    """已經有所在的存檔照存檔：重挫退出戰線的皇甫嵩（所在盧植營、戰線是空的）不會被人物表拉回潁川；不在人物表的 id（夾具）
    也照存檔，哪怕所在是空的。"""
    s = _season(on)
    left = FigureState(prestige=40, status="active", front=None, location="luzhi_camp")
    s.world.figures["huangfusong"] = left.model_copy()
    s.world.figures["fixture"] = FigureState(prestige=33, status="active", front=None, location="")
    assert figures.state_of(s, on, "huangfusong") == left
    assert figures._ensure(s, on, "huangfusong") == left and s.world.figures["huangfusong"] == left
    assert figures.state_of(s, on, "fixture") == FigureState(prestige=33, status="active", front=None, location="")
    assert figures.commander(s, on, "yingru", "guan") == "zhujun"  # 皇甫嵩已經不在潁川


def test_only_if_reads_the_table_for_an_unseeded_figure(on):
    """朱儁到任南陽的條件（皇甫嵩還在潁川）：沒種過的皇甫嵩照人物表算他在潁川（T2 審查的提醒）；轉往冀州之後就不成立。"""
    s = _season(on)
    s.world.figures = {}
    change = FigureChange(fate="到任", front="nanyang", location="wan_city", only_if={"huangfusong": "yingru"})
    assert figures.holds(s, on, change)
    s.world.figures["huangfusong"] = FigureState(prestige=40, front="jizhou", location="luzhi_camp")
    assert not figures.holds(s, on, change)


def test_commander_is_the_senior_figure_on_that_front(on):
    s = _season(on)
    w = s.world
    assert figures.commander(s, on, "yingru", "guan") == "huangfusong"  # 皇甫嵩在朱儁前
    assert figures.commander(s, on, "jizhou", "huang") == "zhangjiao"
    assert figures.commander(s, on, "nanyang", "guan") == "sunjian"
    w.figures["zhujun"].front, w.figures["zhujun"].location = "nanyang", "wan_city"  # 第 7 週朱儁到任南陽
    assert figures.commander(s, on, "nanyang", "guan") == "zhujun"  # 宛城的 {官軍主將}「通常就是朱儁」
    w.figures["huangfusong"].status = "retired"
    assert figures.commander(s, on, "yingru", "guan") is None  # 潁川沒有官軍的人物了
    assert figures.commander(s, on, None, "guan") is None


def test_commander_slot_names_the_figure_from_the_table(on):
    s = _season(on)
    wancheng = next(e for e in on.timetable if e.id == "wancheng")
    changshe = next(e for e in on.timetable if e.id == "changshe_fire")
    assert timetable.fill_slots(s, on, wancheng, "{官軍主將}也在。") == "孫堅也在。"
    s.world.figures["bocai"].status = "retired"
    s.world.figures["pengtuo"].status, s.world.figures["pengtuo"].front = "active", "yingru"
    assert timetable.fill_slots(s, on, changshe, "{黃巾主將}收攏殘部。") == "彭脫收攏殘部。"  # 沒有對話人物也寫名字


def test_difficulty_follows_prestige(on):
    s = _season(on)
    assert figures.difficulty(s, on, "bocai") == 120  # 150 × (0.5 + 0.5 × 0.60)
    s.world.figures["bocai"].prestige = 100
    assert figures.difficulty(s, on, "bocai") == 150
    s.world.figures["bocai"].prestige = 0
    assert figures.difficulty(s, on, "bocai") == 75
    squad = figures.squad_of(s, on, "bocai")
    assert (squad.id, squad.name, squad.difficulty) == ("figure_bocai", "波才", 75)
    assert on.squads["figure_bocai"].difficulty == 150  # 內容本身不動


def test_who_stands_where(on):
    s = _season(on)
    assert figures.present_at(s, on, "changshe") == ["huangfusong", "zhujun"]
    assert figures.present_at(s, on, "huangjin_camp") == ["bocai"]  # 彭脫還沒出場
    s.world.figures["luzhi"].status = "jailed"
    placed = figures.placed_characters(s, on)
    assert placed["luzhi"] is None and placed["dongzhuo"] == "mengjin_ford" and "pengtuo" not in placed
    assert figures.of_character(on, "luzhi") == "luzhi" and figures.of_character(on, "caocao") is None
    on.config.season_one = False  # 規則沒開（開關關了，這一季的章也不算數）：大家照 talk_at
    assert figures.placed_characters(s, on) == {}


# ── Task 3：每曆時的推動 ─────────────────────────────────


def _only(content, fid: str, **changes) -> None:
    """人物表只留這一位（其他人不推，數字才寫得死）；changes 改他的設定。"""
    content.figures = {fid: content.figures[fid].model_copy(update=changes)}


def _ticks(state, content, n: int) -> None:
    for _ in range(n):
        figures.tick(state, content, 1)


def test_figure_pushes_its_front_each_calendar_day(on):
    _only(on, "bocai", actions_per_day=2)
    s = _season(on)
    s.world.trends["yingru"] = 50
    _ticks(s, on, 24)  # 一曆日
    assert s.world.trends["yingru"] == 52
    _ticks(s, on, 12)  # 半曆日
    assert s.world.trends["yingru"] == 53
    _ticks(s, on, 11)  # 不足一次：先累積
    assert s.world.trends["yingru"] == 53 and s.world.trend_accum["fig:bocai"] == pytest.approx(11 / 12)


def test_figure_reacts_when_losing(on):
    """戰線偏向對方 20（潁川 30，黃巾輸）：推得加倍勤，一曆日 4 點。"""
    _only(on, "bocai", actions_per_day=2)
    s = _season(on)
    s.world.trends["yingru"] = 30
    _ticks(s, on, 24)
    assert s.world.trends["yingru"] == 34


def test_a_losing_guan_general_reacts_too(on):
    """官軍那邊同理：潁川 70（偏黃巾 20），皇甫嵩一曆日推回 4 點。"""
    _only(on, "huangfusong", actions_per_day=2, active_from_week=1)
    s = _season(on)
    s.world.trends["yingru"] = 70
    _ticks(s, on, 24)
    assert s.world.trends["yingru"] == 66


def test_figures_that_do_not_push(on):
    """何進（push 0）、趙弘與董卓（開季時沒有戰線）、彭脫（還沒出場）、下獄的盧植都不推。"""
    s = _season(on)
    for fid in ("hejin", "zhaohong", "dongzhuo", "pengtuo"):
        assert figures.push_goal(s, on, fid) == 0, fid
    assert (figures.push_goal(s, on, "bocai"), figures.push_goal(s, on, "luzhi")) == (1, -1)
    s.world.figures["luzhi"].status = "jailed"
    assert figures.push_goal(s, on, "luzhi") == 0


def test_guan_generals_start_week_two(on):
    """第 1 週只有黃巾在推；第 2 週「朝廷出兵」之後皇甫嵩、朱儁、盧植、孫堅才開始推（濃縮版內容表 1.2）。"""
    on.timetable = []  # 只看人物的推動
    s = _season(on)
    s.world.trends.update(yingru=50, nanyang=50, jizhou=45)
    week = calendar.week_start(2, on, s.world)
    world.advance_world_state(s.world, on, week, random.Random(0))
    assert [s.world.trends[f] for f in ("yingru", "nanyang", "jizhou")] == [57, 57, 54]  # 7 曆日：+7、+7、三兄弟各 3.5→3
    world.advance_world_state(s.world, on, week, random.Random(0))
    # 潁川：波才 +7、皇甫嵩 −7、朱儁 3.5→−3；南陽：張曼成 +7、孫堅 −7；冀州：三兄弟各 (0.5＋3.5)→+4、盧植 −7
    assert [s.world.trends[f] for f in ("yingru", "nanyang", "jizhou")] == [54, 57, 59]


def test_figures_tick_once_per_calendar_hour_on_the_season_clock(on):
    """figures.tick 掛在 season_hour（每曆時一次）：季長 14 天時一個真實小時是 6 個曆時。每小時那一步若也掛了會多一次。
    開季那一刻只跑 season_events，不推。"""
    on.timetable = []
    _only(on, "bocai", actions_per_day=24)  # 每曆時一次
    s = _season(on)
    s.world.trends["yingru"] = 50
    world.settle_season_start(s.world, on, random.Random(0))
    assert s.world.trends["yingru"] == 50 and not any(key.startswith("fig:") for key in s.world.trend_accum)
    world.advance_world_state(s.world, on, 3600, random.Random(0))
    assert s.world.trends["yingru"] == 56


def test_figures_do_not_push_with_the_switch_off(real):
    s = _season(real)
    before = dict(s.world.trends)
    _ticks(s, real, 48)
    assert s.world.trends == before and s.world.trend_accum == {}


def test_sim_players_stand_down_in_season_one(on):
    """第一季：大勢人物取代虛擬玩家，虛擬玩家不推大勢、不發傳聞；門檻照舊每小時檢查（玉璽線索到 50 照樣觸發；黃巾聲勢的舊門檻第一季由 T8 關掉）。"""
    on.figures = {}
    s = _season(on)
    before = dict(s.world.trends)
    world.sim_tick(s, on, 24, FixedRandom(0.0))  # 0.0：沒停下來的話每一小時都出手
    assert s.world.trends == before and s.world.rumors == []
    s.world.trends["yuxi"] = 50
    world.sim_tick(s, on, 1, FixedRandom(0.0))
    assert "yuxi_50" in s.world.fired_thresholds


def test_the_map_shows_the_figures_where_they_stand(on):
    s = _season(on)
    assert atlas.haunters(s, on, "changshe") == ["皇甫嵩", "朱儁"]
    assert atlas.haunters(s, on, "mengjin_ford") == ["董卓"]  # 不推戰線也在地圖上（內容表 1.1）
    assert atlas.haunters(s, on, "deep_mountain") == []  # beta 的虛擬玩家董卓不再標在嵩山深處
    assert atlas.leader_activity(s, on, "波才") == "每天約出手 1 次，讓潁川汝南上升"
    assert atlas.leader_activity(s, on, "皇甫嵩") == "每天約出手 1 次，讓潁川汝南下降（第 2 週起）"
    assert atlas.leader_activity(s, on, "董卓") == atlas.LEADER_QUIET
    assert "- 聲威 60（越高越難打）。" in atlas.leader_text(s, on, "波才")
    s.world.figures["luzhi"].status = "jailed"
    assert atlas.haunters(s, on, "luzhi_camp") == []


def test_the_map_keeps_the_sim_players_with_the_switch_off(real):
    s = _season(real)
    assert atlas.haunters(s, real, "huangjin_camp") == ["波才"]
    assert atlas.haunters(s, real, "mengjin_ford") == []
    assert "聲威" not in atlas.leader_text(s, real, "波才")


# ── Task 4：人物結局、接手、打贏扣聲威 ───────────────────


def test_prestige_zero_retires_and_successor_takes_the_front(on):
    """波才被打到聲威歸零：退場，彭脫上場、接下潁川（在黃巾別部營寨）、開始推；退場與接手合成一則天下大事。"""
    s = _season(on)
    s.world.figures["bocai"].prestige = 5
    lines = figures.defeat(s, on, "bocai", 5)
    assert lines == ["波才聲威 -5", "波才連吃敗仗，聲威掃地，再也號令不動手下的兵。", "彭脫接手潁川汝南的戰事。"]
    assert s.world.figures["bocai"].status == "retired" and figures.is_out(s, "bocai")
    assert s.world.figures["pengtuo"] == FigureState(prestige=40, status="active", front="yingru", location="huangjin_camp")
    assert figures.commander(s, on, "yingru", "huang") == "pengtuo" and figures.push_goal(s, on, "pengtuo") == 1
    assert [(r.layer, r.text) for r in s.world.rumors] == [
        ("world", "波才連吃敗仗，聲威掃地，再也號令不動手下的兵。彭脫接手潁川汝南的戰事。"),
    ]
    assert figures.defeat(s, on, "bocai", 5) == []  # 退場的人不再扣、不再發公告


def test_successor_takes_over_the_post_of_the_one_he_replaces(on):
    """盧植被打到聲威歸零：董卓接手冀州，而且站到盧植原本的所在（盧植營），不是他自己開季時的孟津渡；
    天下大事傳聞寫「董卓接手冀州的戰事。」。盧植退場、聲威歸零。"""
    s = _season(on)
    assert s.world.figures["dongzhuo"] == FigureState(prestige=60, status="active", front=None, location="mengjin_ford")
    s.world.figures["luzhi"].prestige = 3
    lines = figures.defeat(s, on, "luzhi", 5)
    assert lines[-1] == "董卓接手冀州的戰事。"
    assert s.world.figures["luzhi"].status == "retired" and s.world.figures["luzhi"].prestige == 0
    assert s.world.figures["dongzhuo"] == FigureState(prestige=60, status="active", front="jizhou", location="luzhi_camp")
    assert "董卓接手冀州的戰事。" in [r.text for r in s.world.rumors][-1]
    assert figures.present_at(s, on, "luzhi_camp") == ["dongzhuo"] and figures.present_at(s, on, "mengjin_ford") == []


def test_destiny_figure_is_crippled_not_retired(on):
    """孫堅是天命人物：歸零是重創，退出本季；他沒有接位的人，南陽官軍沒有人物了。"""
    s = _season(on)
    s.world.figures["sunjian"].prestige = 3
    assert figures.defeat(s, on, "sunjian", 5) == ["孫堅聲威 -3", "孫堅連吃敗仗，元氣大傷，今年是露不了面了。"]
    assert s.world.figures["sunjian"].status == "crippled" and figures.is_out(s, "sunjian")
    assert figures.commander(s, on, "nanyang", "guan") is None


def test_successor_chain_ends_without_error(on):
    """總計畫 Review Focus 4：波才退場、接手的彭脫也退場——潁川沒有黃巾的人物了：commander 回 None、{黃巾主將}
    填「黃巾」、tick 照跑不丟例外，潁川只剩官軍在推。"""
    s = _season(on)
    figures.apply(s, on, "bocai", FigureChange(fate="退場"))
    figures.apply(s, on, "pengtuo", FigureChange(fate="退場"))
    assert s.world.figures["pengtuo"].status == "retired"
    assert figures.commander(s, on, "yingru", "huang") is None
    changshe = next(e for e in on.timetable if e.id == "changshe_fire")
    assert timetable.fill_slots(s, on, changshe, "{黃巾主將}") == "黃巾"
    s.world.time = calendar.week_start(2, on, s.world) + calendar.cal_hour_seconds(on, s.world)  # 第 2 週：官軍出兵了
    s.world.trends["yingru"] = 50
    _ticks(s, on, 24)
    assert s.world.trends["yingru"] == 49  # 皇甫嵩 −1；朱儁的 0.5 還沒滿一次


def test_defeat_keeps_the_fraction_of_a_point(on):
    """兩個人都在推時人數緩衝打折：扣 2.5 先扣 2、留 0.5，再扣 2.5 湊滿 3。"""
    s = _season(on)
    assert figures.defeat(s, on, "bocai", 2.5) == ["波才聲威 -2"]
    assert figures.defeat(s, on, "bocai", 2.5) == ["波才聲威 -3"]
    assert s.world.figures["bocai"].prestige == 55 and "prestige:bocai" not in s.world.trend_accum


def test_timetable_outcome_retires_bocai(on):
    """長社「guan:大勝」：波才退場、彭脫接手潁川；公告照時刻表的原文（不多接接手那一句），接手另發一則天下大事。"""
    s = _season(on)
    changshe = next(e for e in on.timetable if e.id == "changshe_fire")
    outcome = changshe.outcomes["guan:大勝"]
    msgs = timetable.resolve(s, on, changshe, random.Random(0), key="guan:大勝")
    text = outcome.text.replace("{人物:bocai}", "波才")  # 8.11：「這一次」那半句寫出人名，結算前的波才
    assert msgs == [f"【江湖大事】{changshe.preface}{text}{outcome.note}"]
    assert s.world.figures["bocai"].status == "retired"
    assert (s.world.figures["pengtuo"].status, s.world.figures["pengtuo"].front) == ("active", "yingru")
    assert [r.text for r in s.world.rumors] == ["彭脫接手潁川汝南的戰事。", msgs[0].removeprefix("【江湖大事】")]


def test_displaced_figure_leaves_front_successor_takes_it(on):
    """長社「huang:險勝」：皇甫嵩重挫——聲威 −30、離開潁川轉往冀州盧植營；朱儁本來就在潁川，接下潁川不必交接、
    也不另發公告。冀州官軍的主將變成皇甫嵩（人物表上他排在盧植前面）。"""
    s = _season(on)
    changshe = next(e for e in on.timetable if e.id == "changshe_fire")
    timetable.resolve(s, on, changshe, random.Random(0), key="huang:險勝")
    assert s.world.figures["huangfusong"] == FigureState(prestige=40, front="jizhou", location="luzhi_camp")
    assert figures.commander(s, on, "yingru", "guan") == "zhujun"
    assert figures.commander(s, on, "jizhou", "guan") == "huangfusong"
    assert figures.push_goal(s, on, "huangfusong") == -1  # 之後推冀州
    assert not any("接手" in r.text for r in s.world.rumors)


def test_displaced_with_nobody_left_on_the_front_hands_it_down_the_chain(on):
    """皇甫嵩重挫時朱儁已經南下宛城（守著南陽）：他不回頭，接位鏈到底，潁川沒有官軍的人物了，也不發接手公告。"""
    s = _season(on)
    s.world.figures["zhujun"].front, s.world.figures["zhujun"].location = "nanyang", "wan_city"
    figures.apply(s, on, "huangfusong", FigureChange(fate="重挫", front="jizhou", location="luzhi_camp"))
    assert figures.commander(s, on, "yingru", "guan") is None
    assert (s.world.figures["zhujun"].front, s.world.rumors) == ("nanyang", [])


def test_jailed_figure_hidden_dongzhuo_arrives(on):
    """盧植下獄「成」：盧植 jailed（不在地圖上、不推、不算退場、聲威不變）；董卓到任冀州、在盧植營，開始推冀州。
    下獄不走接位鏈（董卓是「到任」），不發接手公告。求見、交友那一半見 Task 5。"""
    s = _season(on)
    jailed = next(e for e in on.timetable if e.id == "luzhi_jailed")
    timetable.resolve(s, on, jailed, random.Random(0), key="成")
    assert s.world.figures["luzhi"] == FigureState(prestige=70, status="jailed", front="jizhou", location="luzhi_camp")
    assert not figures.is_out(s, "luzhi") and figures.present_at(s, on, "luzhi_camp") == ["dongzhuo"]
    assert (s.world.figures["dongzhuo"].front, figures.push_goal(s, on, "dongzhuo")) == ("jizhou", -1)
    assert figures.commander(s, on, "jizhou", "guan") == "dongzhuo"
    assert not any("接手" in r.text for r in s.world.rumors)


def test_a_figure_who_is_out_stays_out(on):
    """已經退場或重創的人不再被時刻表改：張角病逝之後廣宗的「張角退場」什麼都不做；重創的董卓不會因為「到任」回來。"""
    s = _season(on)
    figures.apply(s, on, "zhangjiao", FigureChange(fate="退場"))
    figures.apply(s, on, "zhangjiao", FigureChange(fate="退場"))
    assert s.world.rumors == []  # 張角沒有接位的人，兩次都不發公告
    figures.apply(s, on, "dongzhuo", FigureChange(fate="重創"))
    figures.apply(s, on, "dongzhuo", FigureChange(fate="到任", front="jizhou", location="luzhi_camp"))
    assert s.world.figures["dongzhuo"].status == "crippled"


def test_fates_that_zero_the_prestige_retire_through_the_chain(on):
    """受挫扣到 0 也照退場處理（結算文件第一節）：張曼成聲威 10 時「受挫」→ 退場，趙弘接下南陽、開始推。"""
    s = _season(on)
    s.world.figures["zhangmancheng"].prestige = 10
    figures.apply(s, on, "zhangmancheng", FigureChange(fate="受挫"))
    assert s.world.figures["zhangmancheng"].status == "retired"
    assert (s.world.figures["zhaohong"].front, figures.push_goal(s, on, "zhaohong")) == ("nanyang", 1)
    assert [r.text for r in s.world.rumors] == ["趙弘接手南陽的戰事。"]


# ── Task 5：挑戰本人、閉門不見 ───────────────────────────


def _player(content, store, name: str, faction: str | None, at: str, *, now: float = 1000.0) -> Game:
    """真實內容的一個角色：站在 at、投靠 faction（None＝散人），現實時間是 now。store 是測試的資料庫（conftest 的 world）。"""
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.visited.add(at)
    game.now = now
    return game


def _option(game: Game, option_id: str):
    return next((o for o in game.options() if o.id == option_id), None)


def _fight(tier: str = "大勝"):
    """挑戰的結果寫死（team.fight），只看打完之後的事。"""
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=120))


def test_challenge_only_for_enemy_faction_at_location(on, world):
    """挑戰本人只給敵方陣營、站在人物所在地點的人：官軍在黃巾別部營寨看得到「挑戰波才」（勝算照聲威算的難度）；
    黃巾（同陣營）、散人看不到；官軍在長社（皇甫嵩、朱儁是自己人）看不到；豪強兩邊都打。還沒出場的彭脫不在。"""
    ids = lambda game: [o.id for o in game.options()]  # noqa: E731
    guan = _player(on, world, "官甲", "guan", "huangjin_camp")
    challenge = _option(guan, "act:challenge:bocai")
    assert challenge.enabled and challenge.label.startswith("挑戰波才（體力 10・")
    assert "act:challenge:pengtuo" not in ids(guan)
    for name, faction, at in (("黃乙", "huang", "huangjin_camp"), ("散丙", None, "huangjin_camp"), ("官丁", "guan", "changshe")):
        assert not any(i.startswith("act:challenge:") for i in ids(_player(on, world, name, faction, at))), name
    assert {"act:challenge:huangfusong", "act:challenge:zhujun"} <= set(ids(_player(on, world, "豪戊", "haoqiang", "changshe")))


def test_figures_off_the_front_refuse_challenges_but_still_meet(on, world, real):
    """戰線空著的人物不接受挑戰（PM 2026-10-05 定 (A)）：黃巾在孟津渡看得到「挑戰董卓」但按不下去、寫明原因，求見照常；
    官軍在南陽黃巾營，趙弘（沒戰線）同樣按不下去，張曼成照打；何進（人物表標了 challenge_off_front）沒有戰線也照打；
    重挫退出戰線的波才也不受挑戰。開關關著照舊沒有挑戰。"""
    off_front = "沒在戰線上領兵，不受挑戰"
    huang = _player(on, world, "黃甲", "huang", "mengjin_ford")
    assert (_option(huang, "act:challenge:dongzhuo").enabled, _option(huang, "act:challenge:dongzhuo").label) == (
        False, f"挑戰董卓（{off_front}）")
    # 求見照常（孟津渡沒有交友事件、董卓又見不到：交友只會撲空所以不給，求見不花體力、按得下去）
    assert _option(huang, "act:socialize") is None and _option(huang, "call:dongzhuo").enabled
    guan = _player(on, world, "官乙", "guan", "nanyang_huangjin_camp")
    assert (_option(guan, "act:challenge:zhaohong").enabled, _option(guan, "act:challenge:zhaohong").label) == (
        False, f"挑戰趙弘（{off_front}）")
    assert _option(guan, "act:challenge:zhangmancheng").enabled
    assert real.figures["hejin"].challenge_off_front and not real.figures["dongzhuo"].challenge_off_front
    assert _option(_player(on, world, "黃丙", "huang", "dajiangjun_fu"), "act:challenge:hejin").enabled
    guan.state.player.location = "huangjin_camp"
    assert _option(guan, "act:challenge:bocai").enabled
    figures.apply(guan.state, on, "bocai", FigureChange(fate="重挫", location="huangjin_camp"))
    assert not _option(guan, "act:challenge:bocai").enabled
    on.config.season_one = False
    assert _option(_player(on, world, "黃戊", "huang", "mengjin_ford"), "act:challenge:dongzhuo") is None


@pytest.mark.parametrize("faction, spot, figure", [
    ("guan", "luzhi_camp", "luzhi"), ("huang", "huangjin_camp", "bocai"), ("huang", "mengjin_ford", "dongzhuo"),
])
def test_a_lone_general_behind_a_closed_door_leaves_only_the_free_audience_button(on, world, faction, spot, figure):
    """陣營投靠點的營寨、孟津渡都只站著一位將領、沒有交友事件：名望不夠時交友只會花 5 點體力換同一句打發，
    所以不給交友，只留不花體力的求見（審查：盧植營交友 150→145 還吃了閉門羹）。"""
    game = _player(on, world, "新人", faction, spot)
    assert [o.id for o in game.options() if o.id in ("act:socialize", f"call:{figure}")] == [f"call:{figure}"]
    option = _option(game, f"call:{figure}")
    assert option.enabled and option.label.startswith("求見") and "名望還差" in option.label
    stamina = game.state.player.stamina
    msgs = game.choose(f"call:{figure}")
    assert game.state.player.stamina == stamina and len(msgs) == 1 and "（名望還差 " in msgs[0]
    game.state.player.stats["fame"] = 100  # 見得到了：交友照給
    assert _option(game, "act:socialize") is not None


def test_win_routs_the_figure_and_snubs_the_winner(on, world):
    """打贏波才：他敗走，聲威 −5（陣營只有一人在推）、跟他的情誼 −5、記 50 貢獻、戰報記一筆「挑戰波才」；兩個現實小時內
    他的交友、挑戰對打贏的人都按不下去、寫「剛吃了敗仗，閉門不見」，別人照常；時間一過又見得到。"""
    winner = _player(on, world, "官甲", "guan", "huangjin_camp")
    winner.state.player.affinities["bocai"] = 20
    winner.state.player.stats["fame"] = 50  # 名望夠，平常見得到波才
    stamina = winner.state.player.stamina
    with _fight():
        msgs = winner.choose("act:challenge:bocai")
    assert {"波才敗走。", "波才聲威 -5", "波才情誼 -5"} <= set(msgs)
    assert world.get_season().figures["bocai"].prestige == 55
    p = winner.state.player
    assert (p.affinities["bocai"], p.contrib, p.snubbed_until["bocai"], p.stamina) == (15, 50, 1000.0 + 2 * 3600, stamina - 10)
    assert winner.state.battles[0].event == "挑戰波才" and "波才聲威 -5" in winner.state.battles[0].changes
    option = _option(winner, "act:challenge:bocai")
    assert (option.enabled, option.label) == (False, "挑戰波才（剛吃了敗仗，閉門不見）")
    # 營寨沒有交友事件、他又閉門不見：交友只會撲空，所以不給交友，求見那顆灰掉、寫同一個原因
    assert _option(winner, "act:socialize") is None
    option = _option(winner, "call:bocai")
    assert (option.enabled, option.label) == (False, "求見波才（剛吃了敗仗，閉門不見）")
    assert not winner.socialize_starts_dialogue()
    other = _player(on, world, "官乙", "guan", "huangjin_camp")
    other.state.player.stats["fame"] = 50
    assert _option(other, "act:challenge:bocai").enabled and other.socialize_starts_dialogue()
    winner.now += 2 * 3600
    assert _option(winner, "act:challenge:bocai").enabled and winner.socialize_starts_dialogue()


def test_a_challenge_plays_out_rounds_that_add_up_to_the_toll(on, world):
    """挑戰本人也演回合（計畫三 Task 1）：對手是照聲威的那一份（難度 120，身法 5＋120÷20＝11，比你快、先出手），
    回合裡的「你氣血 -N」加起來等於戰報那一筆（根骨 10，上限吃根骨）。"""
    game = _player(on, world, "官甲", "guan", "huangjin_camp")
    game.state.player.stats["con"] = 10
    with _fight("落敗"):
        game.choose("act:challenge:bocai")
    record = game.state.battles[0]
    assert record.event == "挑戰波才" and len(record.rounds) in (3, 4)
    assert all(line.startswith(f"第{i}回合　波才") for i, line in enumerate(record.rounds, 1))
    told = int(re.search(r"氣血 -(\d+)", " ".join(record.changes)).group(1))
    assert told > 0 and sum(int(n) for line in record.rounds for n in re.findall(r"你氣血 -(\d+)", line)) == told


def test_the_fight_receives_the_difficulty_from_the_prestige(on, world):
    """挑戰本人時交給 team.fight 的難度是照聲威算的（聲威 60：150 × (0.5 + 0.5 × 0.60) = 120），不是代表本人的隊伍
    寫死的 150；不寫死結果，只看呼叫收到什麼（真的打一場）。"""
    game = _player(on, world, "官甲", "guan", "huangjin_camp")
    assert on.squads["figure_bocai"].difficulty == 150 and world.get_season().figures["bocai"].prestige == 60
    expected = figures.difficulty(game.state, on, "bocai")  # 打之前算（打贏會扣聲威）
    assert expected == 120
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game.choose("act:challenge:bocai")
    assert fight.call_count == 1
    assert fight.call_args.args[3] == "figure_bocai"
    assert fight.call_args.kwargs["difficulty"] == expected


def test_snub_in_the_audience_list(on, world):
    """兩位人物以上的地點（長社）：被你打敗的朱儁在求見名單上按不下去、寫原因；皇甫嵩照常。"""
    game = _player(on, world, "黃甲", "huang", "changshe")
    game.state.player.stats["fame"] = 50
    with _fight():
        game.choose("act:challenge:zhujun")
    game.choose("act:call")
    names = {o.id: (o.label, o.enabled) for o in game.options()}
    assert names["call:zhujun"] == ("朱儁（剛吃了敗仗，閉門不見）", False)
    assert names["call:huangfusong"][1]


def test_snub_follows_the_real_clock_not_the_season_clock(on, world):
    """Review Focus 3：不見你看的是現實時間（Game.now）。管理者快轉賽季三天他照樣不見；現實時間過兩小時才見。
    內容改版拿掉的人物，紀錄跟著清掉。"""
    winner = _player(on, world, "官甲", "guan", "huangjin_camp", now=5000.0)
    with _fight():
        winner.choose("act:challenge:bocai")
    winner.advance(3 * 86400)  # 賽季時鐘、季曆往前三天，現實時間沒動
    assert not _option(winner, "act:challenge:bocai").enabled
    winner.sync(5000.0 + 2 * 3600 - 1)
    assert not _option(winner, "act:challenge:bocai").enabled
    winner.sync(5000.0 + 2 * 3600)
    assert _option(winner, "act:challenge:bocai").enabled
    winner.state.player.snubbed_until["ghost"] = 1e12
    winner._drop_stale_references()
    assert "ghost" not in winner.state.player.snubbed_until


def test_losing_a_challenge_costs_silver_and_blood_but_no_prestige(on, world):
    game = _player(on, world, "官甲", "guan", "huangjin_camp")
    game.state.player.stats["silver"] = 50
    with _fight("落敗"):
        msgs = game.choose("act:challenge:bocai")
    assert "銀兩 -5" in msgs and any(m.startswith("氣血 -") for m in msgs)
    assert world.get_season().figures["bocai"].prestige == 60 and game.state.player.snubbed_until == {}
    assert game.state.player.contrib == 0


def test_the_rout_is_buffered_by_the_sides_active_members(on, world):
    """陣營人數緩衝（T3）：官軍這一曆日裡連自己有 4 個人推過大勢，打贏一次只扣 5 ÷ √4 = 2.5 點——先扣 2、留 0.5；貢獻照記 50。"""
    game = _player(on, world, "官甲", "guan", "huangjin_camp")
    w = game.state.world
    w.active_pushers["guan"] = {name: w.time for name in ("官乙", "官丙", "官丁")}
    with _fight():
        msgs = game.choose("act:challenge:bocai")
    assert "波才聲威 -2" in msgs and game.state.player.contrib == 50
    assert world.get_season().trend_accum["prestige:bocai"] == pytest.approx(0.5)


def test_challenge_while_a_showdown_is_on(on, world):
    """Review Focus 4：決戰打起來的時候——上場的人只看得到決戰的選單（不能分身去挑戰）；在一旁觀戰的豪強照常挑戰，
    打贏扣的是人物的聲威，決戰的戰局一點都不動。"""
    definition = on.battles["huangjin_showdown"]
    fighter = _player(on, world, "官甲", "guan", "huangjin_camp", now=0.0)
    world.start_battle(definition, now=0.0)
    for name, side in (("官甲", "guan"), ("黃乙", "huang")):
        world.mutate_battle(lambda b, n=name, f=side: battle_instance.join_faction(b, n, f, neili_cap=100.0))
    fighter.now = definition.muster_seconds + 1
    assert fighter._battle_status()[0].phase == "active"
    assert not any(o.id.startswith("act:") for o in fighter.options())
    watcher = _player(on, world, "豪丙", "haoqiang", "huangjin_camp", now=definition.muster_seconds + 2)
    trend = world.get_battle().trend
    with _fight():
        watcher.choose("act:challenge:bocai")
    assert world.get_battle().trend == trend and world.get_season().figures["bocai"].prestige == 55


def test_jailed_figure_is_gone_from_audience_and_dongzhuo_receives_at_the_camp(on, world):
    """盧植下獄、董卓到任之後：盧植營交友直接找董卓（盧植不在），孟津渡沒有董卓了；人物照他此刻的所在出現。"""
    game = _player(on, world, "官甲", "guan", "luzhi_camp")
    game.state.player.stats["fame"] = 50
    assert game._figures_here() == ["luzhi"]
    jailed = next(e for e in on.timetable if e.id == "luzhi_jailed")
    timetable.resolve(game.state, on, jailed, random.Random(0), key="成")
    assert game._figures_here() == ["dongzhuo"] and game.socialize_starts_dialogue()
    game.state.player.location = "mengjin_ford"
    assert game._figures_here() == []


def test_nothing_changes_with_the_switch_off(real, world):
    """Review Focus 5：開關關著（beta 那一季）：沒有挑戰的選項、人物照 characters.json 的 talk_at 站（下獄也看不到）、
    存檔沒有人物，交友照舊找波才。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    game.state.player.stats["fame"] = 50
    assert not any(o.id.startswith("act:challenge:") for o in game.options())
    assert game._figures_here() == ["bocai"] and game.socialize_starts_dialogue()
    assert world.get_season().figures == {}
    game.state.player.location = "mengjin_ford"
    assert game._figures_here() == ["dongzhuo"]


# ── Task 6：假人偶爾挑戰 ─────────────────────────────────


def test_bot_challenges_target_figure(on, world):
    """假人只挑打得贏的大勢人物（勝算穩勝或有把握），分數比探索、交友高、比推大勢的遊歷低——前線上照舊遊歷，前線以外
    遇上了才挑戰（洛陽沒有戰況，遊歷不推大勢）。打不贏的不碰：輸了要賠銀兩、扣氣血。"""
    bot = _player(on, world, "黃假", "huang", "dajiangjun_fu")
    profile = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    challenge = Option(id="act:challenge:hejin", label="挑戰何進")
    with mock.patch.object(Game, "challenge_odds", return_value="凶險"):
        assert bot_policy.score(bot, challenge, profile) is None
    with mock.patch.object(Game, "challenge_odds", return_value="有把握"):
        assert bot_policy.score(bot, challenge, profile) == bot_policy.CHALLENGE_SCORE
        assert bot_policy.score(bot, Option(id="act:explore", label="探索"), profile) < bot_policy.CHALLENGE_SCORE
    on.config.bot_strength = 1.0  # 一定挑最高分
    with mock.patch.object(Game, "challenge_odds", return_value="穩勝"), _fight():
        bot_policy.take_turn(bot, profile, random.Random(0))
    assert "hejin" in bot.state.player.snubbed_until and world.get_season().figures["hejin"].prestige == 65

# ── Task 7：第一季不發生的 beta 事件 ─────────────────────


def test_kou_boss_does_not_fire_in_season_one(on, world):
    """beta 的「波才」事件（kou_boss，一季一次的挑戰波才）在第一季的規則開著時抽不到——挑戰本人取代它；開關關著時照舊
    抽得到（PM 2026-10-04）。清單在 scenario.json 的 season_one_off.events（格式是 T8 定的）。"""
    assert on.scenario.season_one_off.events == ["kou_boss"]
    assert "beat_bocai" in on.scenario.season_one_off.milestones  # 挑戰本人不寫 bocai_defeated，擊敗波才照樣做不到
    game = _player(on, world, "官甲", "guan", "huangjin_camp")
    game.state.player.stats["fame"] = 10
    assert "kou_boss" not in [e.id for e in event_candidates(game.state, on, "explore")]
    on.config.season_one = False
    assert "kou_boss" in [e.id for e in event_candidates(game.state, on, "explore")]


def test_guangzong_names_the_jizhou_commander(on):
    """QA 驗 T4 時記的：廣宗公告的 {官軍主將} 以前退回「官軍」；有了人物表，寫得出當時冀州的官軍主將（PM 2026-10-05）。"""
    import random as _random

    from tianxia import timetable

    game = Game.new(on, "甲", rng=_random.Random(0))
    event = next(e for e in on.timetable if e.id == "guangzong")
    text = timetable.resolve(game.state, on, event, _random.Random(0), key="guan:大勝")[0]
    assert "盧植破了廣宗" in text and "官軍破了廣宗" not in text
