"""第一季濃縮版 T4：大勢人物、聲威、敗走與接手（計畫 2026-10-04-T4）。

規則與引擎的測試大多用真實內容（content/）：要驗的就是濃縮版內容表第一節的 14 位人物、他們的戰線與接位鏈。
每個測試自己載一份，開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tianxia.content import ContentError, load_content, validate
from tianxia.models import Config, FigureChange
from tianxia.server_bots import reserved_names

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
