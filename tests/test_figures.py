"""第一季濃縮版 T4：大勢人物、聲威、敗走與接手（計畫 2026-10-04-T4）。

規則與引擎的測試大多用真實內容（content/）：要驗的就是濃縮版內容表第一節的 14 位人物、他們的戰線與接位鏈。
每個測試自己載一份，開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tianxia import figures, timetable
from tianxia.content import ContentError, load_content, validate
from tianxia.models import Config, FigureChange
from tianxia.server_bots import reserved_names
from tianxia.state import FigureState, GameState, PlayerState
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
    c.config.train_stat_chance = 0.0
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
