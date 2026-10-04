"""第一季濃縮版 T9：結局、季末公告、決定性勝利、結算畫面（計畫 2026-10-05-T9-結局與結算畫面）。

用真實內容（content/）：要驗的就是那六種結局、三條戰線與季末大事。每個測試自己載一份，開關在測試裡才打開；
auto_open_first_season 開出來的季照當下的 Config 蓋章，所以開關開著的季是「蓋了章」的。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import guide, rules
from tianxia import world as world_mod
from tianxia.content import load_content
from tianxia.engine import Game

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2。"""
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", world=None):
    return Game.new(content, name, rng=random.Random(0), world=world)


def _stances(game, *, huangjin_fronts, geju):
    """三條戰線都設成 huangjin_fronts（黃巾聲勢就是它），割據設成 geju。"""
    w = game.state.world
    for front in ("yingru", "nanyang", "jizhou"):
        w.trends[front] = huangjin_fronts
    w.trends["geju"] = geju
    rules.recompute_trends(w, game.content)


# ── Task 1：六種結局、態勢比較、「可能的結局」──────────────────


@pytest.mark.parametrize("fronts, geju, expected", [
    (55, 20, "s1_turbans_hold"),     # 黃巾 55、官軍 45、豪強 20
    (40, 20, "s1_turbans_retreat"),  # 官軍 60 最高
    (50, 70, "s1_gentry"),           # 豪強 70 最高
    (50, 20, "s1_turbans_hold"),     # 官黃平手 50：清單裡黃巾坐地排前面（RF4）
    (90, 20, "s1_huangtian"),        # 黃巾聲勢 90：門檻那一種優先
    (10, 20, "s1_pacified"),
    (50, 90, "s1_warlords"),
])
def test_finale_compares_stances(on, fronts, geju, expected):
    game = _game(on)
    _stances(game, huangjin_fronts=fronts, geju=geju)
    assert world_mod.evaluate_ending(game.state, on).id == expected


def test_decisive_only_for_threshold_endings(on):
    game = _game(on)
    _stances(game, huangjin_fronts=60, geju=40)
    assert world_mod.decisive_ending(game.state, on) is None  # 比態勢的那三種不是決定性勝利
    _stances(game, huangjin_fronts=86, geju=40)
    assert world_mod.decisive_ending(game.state, on).id == "s1_huangtian"


def test_switch_off_endings_are_the_beta_ones(real):
    game = _game(real)
    assert world_mod.evaluate_ending(game.state, real).id == "hold"  # beta 主線 huangjin_line 撐到季末的那一個（跟以前一樣）
    assert world_mod.decisive_ending(game.state, real) is None
    assert "黃天當立" not in guide.quest_text(game.state, real)


def test_possible_endings_in_season_one_are_the_six(on):
    game = _game(on)
    text = guide.quest_text(game.state, on)
    assert "**可能的結局**" in text
    for title in ("黃天當立（無璽）", "黃巾平定", "群雄並起", "黃巾坐地", "黃巾敗退", "豪強坐大"):
        assert f"- {title}：" in text
    assert "黃巾稱霸" not in text and "潁川平定" not in text  # beta 的結局（T8 審查 M-4）


# ── Task 2：季中決定性勝利、季末公告、收季寫下結算資料 ──────────────

PREFACE = "史書上，皇甫嵩攻下曲陽，斬張寶，黃巾之亂至此平定。這一次……"


def _quiet_until_finale(game):
    """季末之前的大事都當成已經結算（跳過、沒有公告），週初掛鉤也跑過：推到季末時只剩季末那一件，戰況不會被別的大事改掉。"""
    from tianxia.state import TimelineResult

    w = game.state.world
    for event in game.content.timetable:
        if event.kind != "finale":
            w.timeline.setdefault(event.id, TimelineResult(key="skip", time=0.0))
    w.hooked_week = game.content.config.season_weeks


def _to_finale(game, seconds_before):
    _quiet_until_finale(game)
    game.state.world.time = game.state.world.schedule["finale"] - seconds_before


def test_finale_announcement_and_chronicle(on):
    from tianxia import journal

    game = _game(on)
    _stances(game, huangjin_fronts=40, geju=20)  # 官軍最高：黃巾敗退
    _to_finale(game, 30)
    game.advance(120)
    w = game.state.world
    assert w.ended and w.ending_id == "s1_turbans_retreat" and w.ending_title == "黃巾敗退"
    text = PREFACE + "下曲陽破了，可冀州的山裡仍有黃旗。"
    assert w.timeline["xiaquyang"].text == text and w.timeline["xiaquyang"].key == "s1_turbans_retreat"
    assert w.ending_text == text
    assert w.chronicle[-1].text == "甲子年冬，第一季黃巾之亂落幕：黃巾敗退。"
    assert not any(r.text.startswith("賽季落幕") for r in w.chronicle)  # beta 那一行不寫
    news = [e for e in game.state.journal if e.title == journal.WORLD_NEWS]
    assert news and text in news[0].tag + "".join(news[0].lines)  # FB-038：公告補進自己的江湖紀錄
    assert (w.final_trends["yingru"], w.final_trends["geju"], w.final_trends["huangjin"]) == (40, 20, 40)
    assert game.world.season_phase() == "resting"


def test_finale_adds_dong_zhuo_when_crippled(on):
    from tianxia.state import FigureState

    game = _game(on)
    _stances(game, huangjin_fronts=40, geju=20)
    game.state.world.figures["dongzhuo"] = FigureState(status="crippled", prestige=0)
    _to_finale(game, 30)
    game.advance(120)
    assert game.state.world.timeline["xiaquyang"].text.endswith("下曲陽破了，可冀州的山裡仍有黃旗。董卓兵敗，涼州軍元氣大傷。")


def test_decisive_victory_ends_immediately(on):
    from tianxia import calendar

    game = _game(on)
    game.advance(60)  # 開季後的第一個曆時：第 1 週的事
    _stances(game, huangjin_fronts=86, geju=20)
    game.advance(calendar.cal_hour_seconds(on, game.state.world) + 1)  # 跨過下一個曆時交界
    w = game.state.world
    assert w.ended and w.ending_id == "s1_huangtian"
    assert w.timeline["xiaquyang"].text == "戰事提前收束。下曲陽沒有破，黃巾的聲勢席捲了半個天下。"
    assert w.chronicle[-1].text == "甲子年冬，第一季黃巾之亂落幕：黃天當立（無璽）。"
    assert game.world.season_phase() == "resting"


def test_decisive_at_the_finale_hour_is_not_early(on):
    """RF2：到門檻的那一刻也剛好是排定的季末：只收一次，開頭照季末，結局照門檻那一種。"""
    game = _game(on)
    _stances(game, huangjin_fronts=90, geju=20)
    _to_finale(game, 0.5)
    game.advance(120)
    w = game.state.world
    assert w.ending_id == "s1_huangtian" and w.timeline["xiaquyang"].text.startswith(PREFACE)
    assert sum(1 for r in w.chronicle if r.text.startswith("甲子年冬")) == 1


def test_admin_end_season_in_season_one_is_early(on):
    """RF3：管理者提早收季，第一季照樣有結局與公告，開頭是提前收束。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    admin.advance(60)
    admin.admin_end_season(now=admin.now)
    w = admin.world.get_season()
    assert w.ended and w.ending_id and w.timeline["xiaquyang"].text.startswith("戰事提前收束。")


def test_switch_off_season_end_is_unchanged(real):
    game = _game(real)
    game.advance(14 * 86400 + 60)
    w = game.state.world
    beta = {e.id: e.title for e in real.scenario.endings if not e.season_one}
    assert w.ended and w.ending_id in beta and w.ending_title == beta[w.ending_id]  # beta 自己的結局（門檻或季末）
    assert f"賽季落幕：{w.ending_title}" in [r.text for r in w.chronicle] and "xiaquyang" not in w.timeline
    assert w.final_trends == {} and w.final_rankings == {}


def test_contribution_rankings_top_five_per_side_this_season(on, world):
    from tianxia import leaderboard
    from tianxia.characters import open_characters

    store = open_characters()
    people = [("guan", 50), ("guan", 120), ("huang", 30), (None, 999), ("guan", 1), ("guan", 2), ("guan", 3), ("guan", 4)]
    for i, (faction, contrib) in enumerate(people):
        g = _game(on, f"人{i}", world=world)
        g.state.player.faction, g.state.player.contrib = faction, contrib
        store.save(g.state)
    hidden = _game(on, "影", world=world)
    hidden.state.player.faction, hidden.state.player.contrib, hidden.state.player.anonymous = "huang", 10, True
    store.save(hidden.state)
    ranks = leaderboard.contribution_rankings(on, world, store)
    assert ranks["guan"] == [("人1", 120), ("人0", 50), ("人7", 4), ("人6", 3), ("人5", 2)]
    assert ranks["huang"] == [("人2", 30), ("某位少俠", 10)]
    assert ranks["haoqiang"] == []  # RF5：沒人出力也有那一格
    assert all(name != "人3" for rows in ranks.values() for name, _ in rows)  # 散人不列
