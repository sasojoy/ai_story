"""第一季濃縮版 T10：管理者的時刻表與救場（計畫 2026-10-05-T10-管理者工具）。

用真實內容（content/）、週末設定（季長 2.5 天，一個曆時約 107 世界秒）。每個測試自己載一份，開關在測試裡才打開；
auto_open_first_season 開出來的季照當下的 Config 蓋章。現實時間由測試給（game.now），time_scale 是 1。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import calendar, rules, timetable
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.state import Lock, TimelineResult

CONTENT_DIR = Path(__file__).parent.parent / "content"
NOW = 1000.0


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）；「管」是管理者。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.geju_chaos_per_day = 0.0  # 跳過好幾週時割據不會先衝到 85、提早收季（決定性勝利，T9）
    c.config.admins = ["管"]
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="管"):
    game = Game.new(content, name, rng=random.Random(0))
    game.now = NOW
    return game


def _event(content, event_id):
    return next(e for e in content.timetable if e.id == event_id)


def _settle(game, *event_ids):
    """把這幾件記成跳過（不公告），讓後面那一件變成下一件。"""
    def _apply(season):
        for event_id in event_ids:
            season.timeline.setdefault(event_id, TimelineResult(key="skip", time=season.time))
    game.world.mutate_season(_apply)
    game.state.world = game.world.get_season()


BEFORE_CHANGSHE = ("uprising", "court_mobilizes", "zhangmancheng_wan", "bocai_routs_zhujun")


def _battle(game):
    battle = game.world.get_battle()
    return None if battle is None or battle.phase == "ended" else battle


# ── 權限與開關 ─────────────────────────────────────────────


def test_admin_ops_refused_for_non_admin(on):
    game = _game(on, "甲")
    calls = [
        lambda: game.admin_schedule("changshe_fire", NOW + 3600, NOW),
        lambda: game.admin_jump_next(NOW),
        lambda: game.admin_set_trend("yingru", 70),
        lambda: game.admin_resolve_event("bocai_routs_zhujun", "成"),
        lambda: game.admin_clear_lock("luzhi_siege"),
        lambda: game.admin_cancel_battle(),
    ]
    for call in calls:
        [msg] = call()
        assert msg.startswith("（只有管理者能"), msg
    assert game.world.get_season().timeline == {} and "changshe_fire" in game.world.get_season().schedule


def test_switch_off_timetable_admin_refused(real):
    """RF4：beta 那一季沒有時刻表：排時間、跳到下一件、定結果、清鎖定一律拒絕，賽季一點都不變；定戰況照常
    （beta 的黃巾聲勢推得動），沒有決戰時取消決戰說沒有。"""
    game = _game(real)
    before = game.world.get_season().model_dump()
    for msgs in (
        game.admin_schedule("changshe_fire", NOW + 3600, NOW), game.admin_jump_next(NOW),
        game.admin_resolve_event("bocai_routs_zhujun", "成"), game.admin_clear_lock("luzhi_siege"),
    ):
        assert msgs == ["（這一季沒有時刻表。）"]
    assert game.world.get_season().model_dump() == before
    game.admin_set_trend("huangjin", 40)
    assert rules.trend_value(game.state, real, "huangjin") == 40
    assert game.admin_cancel_battle() == ["（沒有進行中的決戰。）"]


# ── 排時間 ─────────────────────────────────────────────


def test_schedule_converts_real_time_and_validates_order(on):
    """現實 +3600 秒 → 世界秒 world.time + 3600（time_scale 1），寫進共用賽季；排在過去、排在宛城之後、季末排在廣宗之前
    都拒絕；已經結算的、不是三場決戰與季末的都拒絕。"""
    game = _game(on)
    w = game.state.world
    at = w.time + 3600 * on.config.time_scale
    assert game.admin_schedule("changshe_fire", NOW + 3600, NOW) == [
        f"已把長社火攻排在{calendar.stamp_text(at, on, w)}（季曆）。"]
    assert game.world.get_season().schedule["changshe_fire"] == pytest.approx(at)
    assert game.admin_schedule("changshe_fire", NOW - 10, NOW) == ["（不能排在已經過去的時間。）"]
    late = NOW + (w.schedule["wancheng"] - w.time) + 60
    assert game.admin_schedule("changshe_fire", late, NOW) == ["（三場決戰與季末要照順序：要排在宛城之戰之前。）"]
    early = NOW + (w.schedule["guangzong"] - w.time) - 60
    assert game.admin_schedule("xiaquyang", early, NOW) == ["（三場決戰與季末要照順序：要排在廣宗決戰之後。）"]
    assert game.admin_schedule("luzhi_siege", NOW + 3600, NOW) == ["（只有三場決戰與季末能排時間。）"]
    week3 = NOW + (calendar.week_start(3, on, w) - w.time)
    assert game.admin_schedule("wancheng", week3 - 60, NOW) == [  # 看第 3 週的結果決定版本：不能排在它之前（PM 2026-10-05）
        "（宛城之戰要看張曼成攻殺南陽太守的結果決定版本：要排在它之後。）"]
    _settle(game, "changshe_fire")
    assert game.admin_schedule("changshe_fire", NOW + 7200, NOW) == ["（長社火攻已經結算或開打了，不能再排。）"]
    end = NOW + (w.schedule["finale"] - w.time) - 600
    game.admin_schedule("xiaquyang", end, NOW)
    assert game.world.get_season().schedule["finale"] == pytest.approx(w.schedule["finale"] - 600)


def test_schedule_off_the_hour_still_opens(on):
    """RF2：排在不是曆時交界的時刻（交界後 37 秒）：跳到下一件時跳過那個交界，集結照樣開。"""
    game = _game(on)
    _settle(game, *BEFORE_CHANGSHE)
    cal_hour = calendar.cal_hour_seconds(on, game.state.world)
    at = 5 * cal_hour + 37
    game.admin_schedule("changshe_fire", NOW + at - game.state.world.time, NOW)
    game.admin_jump_next(NOW)
    assert _battle(game).battle_id == "changshe_fire"
    assert game.state.world.time == pytest.approx(6 * cal_hour)


# ── 跳到下一件 ─────────────────────────────────────────────


def test_jump_next_resolves_one_event_and_opens_showdown_muster(on):
    """RF1：一次只跳到最早那一件、只結算那一件；一路跳到第 6 週，長社停在集結開始、直接開集結、只開一場；
    集結中再跳拒絕。"""
    game = _game(on)
    game.admin_jump_next(NOW)
    assert list(game.world.get_season().timeline) == ["uprising"]
    game.admin_jump_next(NOW)
    assert list(game.world.get_season().timeline) == ["uprising", "court_mobilizes"]
    for _ in range(2):
        game.admin_jump_next(NOW)
    assert set(game.world.get_season().timeline) == set(BEFORE_CHANGSHE) and _battle(game) is None
    game.admin_jump_next(NOW)
    battle = _battle(game)
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    assert "changshe_fire" not in game.world.get_season().timeline
    assert game.state.world.time == pytest.approx(game.state.world.schedule["changshe_fire"], abs=1e-6)
    assert game.admin_jump_next(NOW) == ["（決戰還沒收場，先等它打完或取消。）"]
    assert _battle(game).record_id == battle.record_id


def test_jump_over_finale_ends_season_once(on):
    """其他大事都結算過了：下一件就是季末，一跳收季，季末那一行江湖史只有一行；再跳就是休季。"""
    game = _game(on)
    _settle(game, *(e.id for e in on.timetable if e.kind != "finale"))
    game.admin_jump_next(NOW)
    season = game.world.get_season()
    assert season.ended and season.ending_id
    assert sum(1 for r in season.chronicle if r.text.startswith("甲子年冬")) == 1
    assert game.admin_jump_next(NOW) == ["（賽季沒有在進行，無法觸發。）"]


# ── 救場 ─────────────────────────────────────────────


def test_admin_set_trend_sets_value_and_refuses_derived(on):
    game = _game(on)
    game.admin_set_trend("yingru", 70)
    assert rules.trend_value(game.state, on, "yingru") == 70
    game.admin_set_trend("yingru", 150)
    assert rules.trend_value(game.state, on, "yingru") == 100
    assert game.admin_set_trend("huangjin", 40) == ["（黃巾聲勢由三條戰線合成，不能直接推；請推其中一條戰線。）"]
    assert game.world.get_season().trends["yingru"] == 100


def test_admin_resolve_event_writes_timeline_and_announces(on):
    """管理者把第 4 週定成「成」：時間軸記成、人人的江湖紀錄收到公告、時間到了也不再擲；鍵不對、已經結算、季末、
    沒有這件都拒絕。"""
    game = _game(on)
    other = _game(on, "乙")
    msgs = game.admin_resolve_event("bocai_routs_zhujun", "成")
    assert any(m.startswith("【江湖大事】") for m in msgs)
    assert game.world.get_season().timeline["bocai_routs_zhujun"].key == "成"
    other.sync(NOW + 1)
    text = game.world.get_season().timeline["bocai_routs_zhujun"].text
    assert any(text in line for e in other.state.journal for line in (e.tag, *e.lines))  # 一件時寫在標籤、多件時一件一行
    assert game.admin_resolve_event("bocai_routs_zhujun", "不成") == ["（波才大敗朱儁已經結算了。）"]
    assert game.admin_resolve_event("luzhi_siege", "guan:大勝") == ["（盧植圍廣宗沒有「guan:大勝」這個結果。）"]
    assert game.admin_resolve_event("xiaquyang", "fixed") == ["（季末請用「立刻收季」。）"]
    assert game.admin_resolve_event("nope", "成") == ["（沒有這件大事。）"]
    assert timetable.result_keys(game.state, on, _event(on, "wancheng")) == []  # 第 3 週還沒結算：宛城不知道是哪一版
    game.admin_resolve_event("zhangmancheng_wan", "成")
    assert timetable.result_keys(game.state, on, _event(on, "wancheng")) == [
        "guan:大勝", "guan:險勝", "huang:大勝", "huang:險勝"]


def test_cancel_then_resolve_showdown(on):
    """RF3：長社正在集結：定它的結果拒絕；取消 → 戰鬥收掉、天下大事一則、記號留著（之後不會自己再開）；再定結果收尾。"""
    game = _game(on)
    _settle(game, *BEFORE_CHANGSHE)
    game.admin_jump_next(NOW)
    assert _battle(game).battle_id == "changshe_fire"
    assert game.admin_resolve_event("changshe_fire", "guan:大勝") == ["（長社火攻正在打，先取消決戰。）"]
    game.admin_cancel_battle()
    assert _battle(game) is None
    season = game.world.get_season()
    assert "長社火攻臨時取消，這一仗沒有打成。" in [r.text for r in season.rumors]
    assert "changshe_fire" in season.showdowns_opened
    game.advance(calendar.cal_hour_seconds(on, game.state.world) * 2)
    assert _battle(game) is None
    assert game.admin_cancel_battle() == ["（沒有進行中的決戰。）"]
    game.admin_resolve_event("changshe_fire", "guan:大勝")
    assert game.world.get_season().timeline["changshe_fire"].key == "guan:大勝"


def test_admin_clear_lock(on):
    game = _game(on)

    def _lock(season):
        season.locks["luzhi_siege"] = Lock(side="guan", name="甲", time=0.0)
        season.lock_losers["luzhi_siege"] = [Lock(side="huang", name="乙", time=1.0)]
    game.world.mutate_season(_lock)
    game.state.world = game.world.get_season()
    assert game.admin_clear_lock("luzhi_siege") == ["已清掉盧植圍廣宗的鎖定。"]
    season = game.world.get_season()
    assert "luzhi_siege" not in season.locks and "luzhi_siege" not in season.lock_losers
    assert game.admin_clear_lock("luzhi_siege") == ["（盧植圍廣宗沒有人鎖定。）"]


def test_wancheng_not_in_battle_menu_before_week_three(on, real):
    """PM 2026-10-05：宛城看第 3 週的結果決定版本，第 3 週結算前不列；結算後列這一季那一版。開關關著照舊沒有時刻表決戰。"""
    game = _game(on)
    assert [b.id for b in game.admin_battles() if b.timetable_event] == ["changshe_fire", "guangzong"]
    game.admin_resolve_event("zhangmancheng_wan", "不成")
    assert [b.id for b in game.admin_battles() if b.timetable_event] == ["changshe_fire", "wancheng_yi", "guangzong"]
    real.config.season_one = False
    assert not any(b.timetable_event for b in _game(real, "乙").admin_battles())
