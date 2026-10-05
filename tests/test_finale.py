"""第一季濃縮版 T9：結局、季末公告、決定性勝利、結算畫面（計畫 2026-10-05-T9-結局與結算畫面）。

用真實內容（content/）：要驗的就是那六種結局、三條戰線與季末大事。每個測試自己載一份，開關在測試裡才打開；
auto_open_first_season 開出來的季照當下的 Config 蓋章，所以開關開著的季是「蓋了章」的。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import calendar, guide, rules
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
    from tianxia import calendar

    game = _game(on)
    game.state.world.time = calendar.week_start(10, on, game.state.world)  # 決定性勝利第 10 週起才算
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


def test_decisive_victory_waits_for_week_ten(on):
    """企劃者 2026-10-05：決定性勝利三方都一樣，第 decisive_from_week 週（預設 10）以後才提前收季；之前到了門檻也不收。"""
    from tianxia import calendar

    assert on.config.decisive_from_week == 10
    game = _game(on)
    game.advance(60)
    _stances(game, huangjin_fronts=50, geju=95)  # 群雄並起的門檻早就過了
    assert world_mod.decisive_ending(game.state, on) is None
    _quiet_until_finale(game)
    game.state.world.time = calendar.week_start(10, on, game.state.world) - 200
    game.advance(150)  # 第 9 週的最後一刻：還不收
    assert not game.state.world.ended
    game.advance(120)  # 跨進第 10 週：已經在門檻上，照規則收
    assert game.state.world.ended and game.state.world.ending_id == "s1_warlords"
    assert game.state.world.timeline["xiaquyang"].text.startswith("戰事提前收束。")


def test_decisive_victory_ends_immediately(on):
    from tianxia import calendar

    game = _game(on)
    _quiet_until_finale(game)
    game.state.world.time = calendar.week_start(10, on, game.state.world) + 60  # 第 10 週起才算
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


def test_an_idle_season_lasts_to_week_ten(on):
    """沒人玩的一季（企劃者 2026-10-05 的裁定之後）：割據早早頂到門檻，但第 10 週以前不收季；T11「第 6 週以前沒有決定性勝利」。"""
    from tianxia import calendar

    game = _game(on)
    while not game.state.world.ended:
        game.advance(3600)
    w = game.state.world
    assert calendar.point(w.time, on, w).week >= on.config.decisive_from_week


# ── Task 3：休季的結算卡 ─────────────────────────────────────


def test_season_result_view(on):
    game = _game(on)
    game.state.player.faction = "guan"
    _stances(game, huangjin_fronts=40, geju=20)
    _to_finale(game, 30)
    game.advance(120)
    result = game.season_result()
    assert result["title"] == "黃巾敗退" and result["text"].startswith(PREFACE)
    assert [(s["side"], s["name"], s["value"]) for s in result["stances"]] == [
        ("guan", "官軍", 60), ("huang", "黃巾軍", 40), ("haoqiang", "地方豪強", 20),
    ]
    assert [(f["name"], f["value"]) for f in result["fronts"]] == [("潁川汝南", 40), ("南陽", 40), ("冀州", 40)]
    rows = result["timeline"]
    assert len(rows) == 12 and (rows[-1]["week"], rows[-1]["title"]) == (12, "下曲陽・季末")
    assert rows[-1]["text"].startswith(PREFACE) and rows[-1]["locked_by"] is None
    assert rows[0]["text"] == "（這一季沒有發生。）"  # 這個測試把季末以前的大事都記成跳過了
    assert [r["faction"] for r in result["rankings"]] == ["guan", "huang", "haoqiang"]  # RF5：沒人出力也有那一格
    assert all(r["rows"] == [] for r in result["rankings"])


def test_season_result_names_the_locker_as_shown(on):
    """時刻表那一列寫公告上的名字：匿名鎖定的人寫「某位少俠」，不是真名。"""
    from tianxia.state import Lock

    game = _game(on)
    _stances(game, huangjin_fronts=40, geju=20)
    _quiet_until_finale(game)
    w = game.state.world
    w.timeline["changshe_fire"].locked_by = "趙甲"
    w.timeline["changshe_fire"].text = "長社的公告。"
    w.locks["changshe_fire"] = Lock(side="guan", name="趙甲", time=0.0, shown="某位少俠")
    w.time = w.schedule["finale"] - 30
    game.advance(120)
    row = next(r for r in game.season_result()["timeline"] if r["title"] == "長社火攻")
    assert row["locked_by"] == "某位少俠" and row["text"] == "長社的公告。"


def test_season_result_after_an_early_end_marks_what_never_came(on):
    on.config.admins = ["管"]
    admin = _game(on, "管")
    admin.advance(200)  # 跨過第一個曆時交界（約 107 秒）：第 1 週的大事結算了
    admin.admin_end_season(now=admin.now)
    rows = admin.season_result()["timeline"]
    assert rows[0]["text"] and rows[0]["text"] != "（季已落幕，沒有發生。）"  # 第 1 週起義在收季之前發生了
    assert rows[5]["text"] == "（季已落幕，沒有發生。）"  # 第 7 週的事沒輪到


def test_season_result_only_when_resting_in_season_one(on):
    assert _game(on).season_result() is None  # 還在進行


def test_switch_off_season_end_has_no_result_card(real):
    off = _game(real, "乙")
    off.advance(14 * 86400 + 60)
    assert off.state.world.ended and off.season_result() is None  # beta 季收季：沒有結算卡


def test_no_next_event_countdown_once_the_season_rests(on):
    """休季時狀態列不再倒數下一件大事（收季之後沒有下一件了）。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    assert admin.status_data()["next_event"] is not None
    admin.admin_end_season(now=admin.now)
    assert admin.status_data()["next_event"] is None


def test_a_decisive_end_keeps_the_ending_that_triggered_it(on):
    """T9 審查 M1：決定性勝利那一刻剛好有決戰該開（還沒開成、在等）：收季時照起點結算那場決戰會把戰況拉回門檻下，
    但季是因為門檻收的，結局要是觸發收季的那一種，公告不能變成「戰事提前收束。……黃巾坐地」這種自相矛盾的組合。"""
    from tianxia.state import Lock, TimelineResult

    game = _game(on)
    w = game.state.world
    for event in on.timetable:
        if event.id not in ("guangzong", "xiaquyang"):
            w.timeline.setdefault(event.id, TimelineResult(key="skip", time=0.0))
    w.hooked_week = on.config.season_weeks
    w.trends.update(yingru=100, nanyang=100, jizhou=62, geju=10)  # 黃巾聲勢 85：到門檻
    rules.recompute_trends(w, on)
    w.locks["guangzong"] = Lock(side="guan", name="趙甲", time=0.0)  # 廣宗照鎖定判官軍：冀州往官軍 10
    w.time = w.schedule["guangzong"] - 0.5
    game.advance(10)
    w = game.state.world
    assert w.ended and w.ending_id == "s1_huangtian"
    assert w.timeline["xiaquyang"].text == "戰事提前收束。下曲陽沒有破，黃巾的聲勢席捲了半個天下。"
    assert "guangzong" in w.timeline  # 廣宗照樣結算了（收季前把等著的決戰判掉）


# ── 正式版辛：態勢卡的收季規則 ─────────────────────────────


def test_stance_rule_before_the_decisive_week(on):
    game = _game(on)
    assert rules.stance_rule_note(game.state, on) == "第 10 週起，哪一方的態勢一到 85，這一季當場收場；否則到季末比高低。"
    assert game.status_data()["stance_rule"] == rules.stance_rule_note(game.state, on)


def test_stance_rule_after_the_decisive_week(on):
    game = _game(on)
    w = game.state.world
    w.time = calendar.week_start(10, on, w)
    assert rules.stance_rule_note(game.state, on) == "哪一方的態勢一到 85，這一季當場收場；否則到季末比高低。"


def test_stance_rule_reads_the_endings_not_a_fixed_number(on):
    game = _game(on)
    for ending in on.scenario.endings:
        if ending.stance_min:
            ending.stance_min = {side: 80 for side in ending.stance_min}
        if ending.stance_max:
            ending.stance_max = {side: 20 for side in ending.stance_max}  # 黃巾 ≤ 20 ＝ 官軍 ≥ 80
    on.config.decisive_from_week = 9
    assert rules.stance_rule_note(game.state, on) == "第 9 週起，哪一方的態勢一到 80，這一季當場收場；否則到季末比高低。"
    assert game.status_data()["stance_rule"] == rules.stance_rule_note(game.state, on)  # 態勢卡那一句跟著內容走


def _decisive(content):
    """第一季的決定性結局（有 stance_min／stance_max 的），照 id 取出來，方便在記憶體裡改。"""
    return {e.id: e for e in content.scenario.endings if e.season_one and (e.stance_min or e.stance_max)}


def test_stance_rule_names_each_side_when_the_bars_differ(on):
    """三方的門檻不一樣時，不能說「哪一方一到 85」：照每一方寫自己的數字（豪強改 90，其他兩方 85）。"""
    game = _game(on)
    _decisive(on)["s1_warlords"].stance_min = {"haoqiang": 90}
    on.config.decisive_from_week = 1  # 第 1 週起就算：不帶「第 N 週起」，只剩規則那一句
    note = rules.stance_rule_note(game.state, on)
    assert note == "官軍一到 85、黃巾一到 85、豪強一到 90，這一季當場收場；否則到季末比高低。"


def test_stance_rule_lists_only_the_sides_that_can_end_the_season(on):
    """只有黃巾與豪強有決定性的結局（官軍那一種被拿掉）：不能說「哪一方」，官軍沒有門檻就不列。"""
    game = _game(on)
    _decisive(on)["s1_pacified"].stance_max = {}
    on.config.decisive_from_week = 1
    assert rules.stance_rule_note(game.state, on) == "黃巾一到 85、豪強一到 85，這一季當場收場；否則到季末比高低。"


def test_stance_rule_states_no_number_it_cannot_back(on):
    """豪強的 stance_max 沒有「另一方到幾分」可換（豪強 ≤ 10 不等於誰到了幾分），兩個條件合成一種的結局也不是「哪一方到幾分」：
    這兩種都不報數字，寫一句中性的話。"""
    game = _game(on)
    on.config.decisive_from_week = 1
    endings = _decisive(on)
    endings["s1_warlords"].stance_min, endings["s1_warlords"].stance_max = {}, {"haoqiang": 10}
    note = rules.stance_rule_note(game.state, on)
    assert note == "哪一方的態勢到了決勝的門檻，這一季當場收場；否則到季末比高低。"
    endings["s1_warlords"].stance_max = {}
    endings["s1_warlords"].stance_min = {"haoqiang": 85}
    endings["s1_huangtian"].stance_min = {"huang": 60}
    endings["s1_huangtian"].stance_max = {"haoqiang": 30}  # 兩個條件合在一起
    assert rules.stance_rule_note(game.state, on) == note
    assert not any(ch.isdigit() for ch in note)


def test_stance_rule_is_empty_without_a_decisive_ending(on):
    game = _game(on)
    for ending in _decisive(on).values():
        ending.stance_min, ending.stance_max = {}, {}
    assert rules.stance_rule_note(game.state, on) == ""


def test_no_stance_rule_with_switch_off(real):
    assert "stance_rule" not in _game(real).status_data()
