"""第一季濃縮版 T10：管理者的時刻表與救場（計畫 2026-10-05-T10-管理者工具）。

用真實內容（content/）、週末設定（季長 2.5 天，一個曆時約 107 世界秒）。每個測試拿自己的一份（conftest.real_content 的複本），開關在測試裡才打開；
auto_open_first_season 開出來的季照當下的 Config 蓋章。現實時間由測試給（game.now），time_scale 是 1。"""
from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from conftest import real_content
from tianxia import calendar, rules, timetable
from tianxia.characters import open_characters
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.state import Lock, TimelineResult
from tianxia.sqlite_world import open_world
from tianxia.world_state import season_length_days
import re
from test_prologue_web import run
import server
import webharness
from tianxia import timetable
from unittest import mock
from conftest import FixedRandom, walk_to
from test_day_scale import SHORT, WEEKEND, _lake, _miss, _season, _talk_out, SCENE
from tianxia import rules, sensing
from tianxia.models import TimetableEvent

CONTENT_DIR = Path(__file__).parents[2] / "content"
NOW = 1000.0


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）；「管」是管理者。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
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
    cal_hour = calendar.cal_hour_seconds(on, w)
    at = math.ceil((w.time + 3600 * on.config.time_scale) / cal_hour) * cal_hour  # 決戰對齊到下一個曆時交界（T10 審查 I1）
    assert game.admin_schedule("changshe_fire", NOW + 3600, NOW) == [
        f"已把長社火攻排在{calendar.stamp_text(at, on, w)}（季曆，對齊整點）。"]
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


def test_schedule_snaps_to_the_hour_and_off_a_regular_event(on):
    """T10 審查 I1：排在第 7 週週初（盧植圍廣宗）前 30 秒：先進到下一個曆時交界，那一刻又剛好是第 7 週的大事，
    再往後挪一個曆時——集結照樣開，不會被第 7 週的大事先照起點判掉；跳一次只到長社。"""
    game = _game(on)
    _settle(game, *BEFORE_CHANGSHE)
    w = game.state.world
    cal_hour = calendar.cal_hour_seconds(on, w)
    week7 = calendar.week_start(7, on, w)
    msgs = game.admin_schedule("changshe_fire", NOW + (week7 - 30) - w.time, NOW)
    assert game.world.get_season().schedule["changshe_fire"] == pytest.approx(week7 + cal_hour)
    assert msgs == [f"已把長社火攻排在{calendar.stamp_text(week7 + cal_hour, on, w)}（季曆，對齊整點、避開同一刻的盧植圍廣宗）。"]
    game.admin_jump_next(NOW)
    assert "changshe_fire" not in game.world.get_season().timeline
    game.admin_jump_next(NOW)
    assert _battle(game).battle_id == "changshe_fire"
    assert "changshe_fire" not in game.world.get_season().timeline


def test_rescheduling_a_waiting_showdown_takes_it_off_the_queue(on):
    """T10 審查 I2：宛城時間到了、在排隊等長社打完（showdowns_waiting）；改排到之後：拿出隊伍，到了新的時間才開。"""
    game = _game(on)
    game.admin_resolve_event("zhangmancheng_wan", "成")
    game.world.mutate_season(lambda s: s.showdowns_waiting.append("wancheng"))
    game.state.world = game.world.get_season()
    w = game.state.world
    later = w.schedule["guangzong"] - 600
    game.admin_schedule("wancheng", NOW + later - w.time, NOW)
    assert game.world.get_season().showdowns_waiting == []
    game.advance(calendar.cal_hour_seconds(on, w) * 2)
    assert _battle(game) is None


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
    [(_, shelved)] = game.world.ended_battles()  # T10 審查 I3：參戰者那一則寫「臨時取消」，不是「季終了」
    assert shelved.unfinished and shelved.unfinished_text == "長社火攻臨時取消，這一仗沒有打成，不算勝負。"
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


# ── 換版當天的順序（總計畫 T10 的表）──────────────────────────


def _restart(content, *names):
    """「重開伺服器」：角色照資料庫裡存的那一份、換上這一份內容（開關照它）重建 Game。"""
    chars = open_characters()
    return [Game(content, chars.load(name), rng=random.Random(0), world=open_world()) for name in names]


def test_cutover_sequence(real):
    """RF5：照總計畫 T10 的表 1～5 步走一次（假時鐘、兩個角色）：
    1. 開關關著，beta 那一季照舊進行；2. 管理者立刻收季；3. 開關打開、重開：休季中的 beta 季什麼都不補算；
    4. 開啟下一季：照週末設定蓋章，第 1 週的大事結算一次、公告一則；5. 排長社，時間到了開集結。
    兩個角色同步後都是新角色、在第 1 週，江湖史留著上一季。"""
    chars = open_characters()
    admin, player = _game(real), _game(real, "乙")
    player.state.player.faction = "guan"
    for game in (admin, player):
        game.sync(NOW)
        chars.save(game.state)
    assert not admin.world.get_season().season_one  # 1. beta：沒蓋章
    admin.admin_end_season(NOW + 60)  # 2.
    chars.save(admin.state)
    assert admin.world.season_phase() == "resting"

    on = load_content(CONTENT_DIR)  # 3. 設 TIANXIA_PROFILE=week7、重開
    on.config.auto_open_first_season, on.config.admins = True, ["管"]
    on.config.season_one, on.config.season_days, on.config.server_max_players = True, 2.5, 2
    admin, player = _restart(on, "管", "乙")
    for game in (admin, player):
        game.sync(NOW + 120)
    old = admin.world.get_season()
    assert old.ended and not old.season_one and old.timeline == {} and old.schedule == {}

    admin.admin_next_season(NOW + 180)  # 4.
    admin.sync(NOW + 181)
    season = admin.world.get_season()
    assert season.season_one and season_length_days(season, on) == 2.5 and list(season.timeline) == ["uprising"]
    uprising = season.timeline["uprising"].text
    assert sum(uprising in (e.tag + "".join(e.lines)) for e in admin.state.journal) == 1

    t = NOW + 200  # 5. 排長社在現實 10 分鐘後；時間一到（下一個曆時交界）開集結
    admin.admin_schedule("changshe_fire", t + 600, t)
    assert admin.world.get_battle() is None
    cal_hour = calendar.cal_hour_seconds(on, season)
    admin.sync(t + 600 + cal_hour)
    battle = admin.world.get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")

    player.sync(t + 600 + cal_hour + 1)
    for game in (admin, player):
        p = game.state.player
        assert (p.season_number, p.faction, p.rank) == (2, None, 0)
        assert game.status_data()["calendar"]["week"] == 1
    assert any(uprising in (e.tag + "".join(e.lines)) for e in player.state.journal)
    assert "賽季落幕" in player.chronicle_text()  # 江湖史留著上一季


def test_admin_revives_a_fallen_figure_at_half_on_his_old_front(on):
    """叫回人物（PM 2026-10-16）：時刻表或挑戰打退的人物，管理者叫他以一半開季聲威回到原本的戰線；接位的人交還戰線。"""
    from tianxia import figures
    from tianxia.models import FigureChange
    game = _game(on)
    s = game.state
    figures.apply(s, on, "bocai", FigureChange(fate="退場"))
    game._save_season()
    assert game.admin_fallen() == ["bocai"]
    assert game.admin_revive_figure("bocai") == [figures.BACK_LINE.format(name="波才", where="，回到潁川汝南")]
    stored = game.world.get_season().figures
    assert stored["bocai"].status == "active" and stored["bocai"].prestige == 30 and stored["bocai"].front == "yingru"
    assert stored["pengtuo"].front is None and game.admin_fallen() == []
    assert game.admin_revive_figure("bocai") == ["（這位人物此刻沒有退場。）"]
    assert _game(on, "路人").admin_revive_figure("bocai") == ["（只有管理者能叫回人物。）"]


# ── 原 test_fb099_cancelled_showdown.py（整檔搬進來） ──
# FB-099（QA 驗管理者觸發鈕時發現）：管理者按了一場大戲的「立刻開這一場」再按「⚠ 取消決戰」，管理者工具的三場大戲那一列一直寫
# 「（長社火攻已經開打過了。）」、時刻表那一列寫「開打了」——可是這一仗沒打成、時間軸上也沒有結果，只能用「定結果」收尾，畫面上卻沒說。
#
# 裁決照舊：開過的記號（WorldState.showdowns_opened）留著，提早開的決戰不會再開。只改字（只有管理者看得到）：開打後被取消、
# 時間軸上還沒有結果的那一場，三場大戲那一列與時刻表那一列都說「開打後被取消，還沒有結果；要收尾請用「定結果」」；定了結果之後照平常的
# 「已經結算了」；真的打完的照舊。真實內容、週末設定的開關；管理者是「管」。

CANCELLED = "（長社火攻開打後被取消，還沒有結果；要收尾請用「定結果」。）"


@pytest.fixture
def on_fb099(monkeypatch):
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.admins = ["管"]
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 250
    monkeypatch.setattr(server, "CONTENT", c)  # 伺服器整理管理者資料讀的是 server.CONTENT
    return c


def _admin(content):
    game = Game.new(content, "管", rng=random.Random(0))
    game.client = None
    game.sync(NOW)
    return game


def _notes(game):
    return {event.id: why for event, why in game.admin_showdowns()}


def _row(game, event_id="changshe_fire"):
    return next(r for r in server.timetable_choices(game)["timetable"] if r["id"] == event_id)


def test_open_then_cancel_says_cancelled_in_both_places(on_fb099):
    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    season = admin.world.get_season()
    assert "changshe_fire" in season.showdowns_opened and "changshe_fire" not in season.timeline  # 記號照舊、沒有結果
    assert _notes(admin)["changshe_fire"] == CANCELLED
    assert admin.admin_start_showdown("changshe_fire", NOW) == [CANCELLED]  # 照舊開不了（不會再開），按下去也是這一句
    row = _row(admin)
    assert row["state"] == "cancelled" and row["state_text"] == "開打後取消・待定結果" and row["result"] is None
    assert not row["schedulable"]  # 開過了：照舊不能再排時間


def test_open_cancel_then_set_a_result_says_settled(on_fb099):
    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    admin.admin_resolve_event("changshe_fire", "guan:大勝")
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經結算了。）"
    row = _row(admin)
    assert (row["state"], row["state_text"], row["result"]) == ("done", "已結算", "官軍大勝")


def test_a_running_battle_keeps_its_wording(on_fb099):
    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經開打過了。）"
    row = _row(admin)
    assert (row["state"], row["state_text"]) == ("running", "開打了")


def test_a_battle_that_was_fought_to_the_end_keeps_its_wording(on_fb099):
    """真的打完的（沒人上陣，回合逾時、照保底收場，時刻表照戰局判結果）：照舊「已經結算了」「已結算」。"""
    from conftest import at

    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    deadline = admin.world.get_battle().muster_deadline_real
    for now in (deadline, deadline + on_fb099.battles["changshe_fire"].round_seconds):  # 集結截止開打，再過一回合逾時照保底收場
        with at(admin, now):
            admin.options()
    assert admin.world.get_battle().phase == "ended" and "changshe_fire" in admin.world.get_season().timeline
    assert _notes(admin)["changshe_fire"] == "（長社火攻已經結算了。）"
    assert (_row(admin)["state"], _row(admin)["state_text"]) == ("done", "已結算")


def test_a_cancelled_battle_beside_another_live_one_still_says_cancelled(on_fb099):
    """取消了長社、之後開了廣宗（另一場在打）：長社那一列照樣說取消了；廣宗是開打中。"""
    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    admin.admin_start_showdown("guangzong", NOW)
    assert admin.world.get_battle() is not None and admin.world.get_battle().phase != "ended"
    rows = {r["id"]: r["state"] for r in timetable.status_rows(admin.state, on_fb099, cancelled=admin.cancelled_showdowns())}
    assert rows["changshe_fire"] == "cancelled" and rows["guangzong"] == "running"
    assert _notes(admin)["changshe_fire"] == CANCELLED


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_drawer_shows_the_cancelled_wording(on_fb099):
    """設定抽屜的管理者工具（node 假瀏覽器，伺服器給的真資料）：三場大戲那一列與時刻表那一列都寫取消了、待定結果。"""
    admin = _admin(on_fb099)
    admin.admin_start_showdown("changshe_fire", NOW)
    admin.admin_cancel_battle()
    m = server.main_view(admin)
    assert m["admin"] is True
    drawer = run(m, "return H.sheetHtml();", S={"sheet": True, "admin": server.admin_choices(admin)})
    assert CANCELLED in drawer
    assert re.search(r'<span class="tt-name">第\d+週　長社火攻</span><span class="tt-state">開打後取消・待定結果</span>', drawer)


# ── 原 test_fb102_postponed_finale.py（整檔搬進來） ──
# FB-102（QA 7cc1fd7，2026-10-08）：管理者把季末往後排時，最後一天的「這一季之內…」說錯了。
#
# 換日在名義季長之後寫不出時刻（季曆只寫到第 12 週・週日 23:59），以前一律改寫「這一季之內不能再來…」；可是季末延後時，名義季長
# 之後照樣換日（每 4 小時 17 分重算），照字面走的人會白白放棄。換日的時刻怎麼算不改（PM：不改什麼時候換日）。
#
# 現在（rules.day_turn）分三種：
# - 換日在真的季末（排定的 schedule["finale"]）之前、寫得出來：照舊寫那一刻；
# - 換日在真的季末之前、但在名義季長之後（寫不出來）：寫一句不承諾時刻的話（「過一陣子」，待 joy 潤）；
# - 換日在真的季末那一刻或之後：「這一季之內…」（那時才是真的）。
# 測試內容（tests/fixtures），第一季縮小的時刻表（conftest.install_season_one）；句子照字比（每一句都是待 joy 潤的初稿，改字時改這裡）。

LATER_TEXTS = {
    "warning": "> 選錯了做法，這裡要過一陣子才悟得出。",
    "miss": "心浮氣躁，什麼也沒抓住。要過一陣子，這裡才悟得出東西。",
    "explore": "；這裡要過一陣子才悟得出",
    "talk": "韓鐵起身送客，改日再敘：過一陣子再來拜會吧。",
    "talked_out": "已經談滿 3 輪，過一陣子再來",
    "busy": "韓鐵事忙，過一陣子才得空。",
    "intro": "最多談 3 輪，過一陣子重新算起；",
    "gather": "你留心路邊，這陣子已經撿夠了，沒再去翻（過一陣子再說）。",
    "think": "你邊走邊想，這陣子想得夠多了，沒有新的心得（過一陣子才會再有）。",
}


def _postponed(content, game, finale=16 * SHORT):
    """管理者把季末排到 finale（世界秒）：時刻表要有季末那一件，排定的時間記在 schedule["finale"]。"""
    if not any(e.kind == "finale" for e in content.timetable):
        content.timetable.append(TimetableEvent(id="finale", week=12, title="季末", kind="finale"))
    game.state.world.schedule["finale"] = finale


def test_the_three_kinds_of_day_turn(content):
    content.config.season_one = True
    content.timetable.append(TimetableEvent(id="finale", week=12, title="季末", kind="finale"))
    season = _season(content, WEEKEND, one=True)
    season.schedule["finale"] = 16 * SHORT  # 延後兩個多遊戲日
    season.time = 12.5 * SHORT
    assert rules.day_turn(content, season) == ("at", "第 12 週・週二 00:00")  # 名義季長以內：照舊
    for t in (13.5, 14.5):  # 換日落在名義季長之後、真的季末之前：寫不出時刻，但還會換日
        season.time = t * SHORT
        assert rules.day_turn(content, season) == ("later", None) and rules.day_ends_text(content, season) is None
    season.time = 15.5 * SHORT  # 真的最後一個遊戲日：換日在季末那一刻之後
    assert rules.day_turn(content, season) == ("season", None)
    plain = _season(content, WEEKEND, one=True)  # 沒延後：最後一天照舊是「這一季之內」
    plain.time = 13.5 * SHORT
    assert rules.day_turn(content, plain) == ("season", None)


def test_days_still_turn_after_the_nominal_end(content):
    """換日的時刻不改：名義季長之後照樣每一個遊戲日換一次（以前就是這樣，句子跟著說實話）。"""
    season = _season(content, WEEKEND, one=True)
    days = [rules.game_day(content, season, t * SHORT) for t in (13.5, 14.5, 15.5)]
    assert days == [14, 15, 16]


def _texts(game, content):
    """所有寫「什麼時候再來」的句子，照 LATER_TEXTS 的鍵。"""
    out = {}
    sensing.start(game.state, content, SCENE, random.Random(0))
    out["warning"] = sensing.scene_text(game.state, content)
    game.state.player.sensing = None
    out["miss"] = _miss(game)[-1]
    out["explore"] = game.action_notes(["act:explore"])["act:explore"]
    game.state.player.location = "town"
    out["talk"] = _talk_out(game)[-1]
    out["talked_out"] = game._talked_out_note()  # noqa: SLF001
    with mock.patch("tianxia.engine.pick_event", return_value=None):
        out["busy"] = game.choose("act:socialize")[0]
    content.characters["scholar"].deep_interaction = True
    content.characters["scholar"].audience_fame = 0
    out["intro"] = game._audience_intro()  # noqa: SLF001
    content.config.road_reward_daily_cap = 1
    game.choose("move:lake")
    game.choose("road:think")
    game.rng = FixedRandom(0.1)
    out["gather"] = game.choose("road:gather")[0]
    walk_to(game, "lake")
    game.choose("move:town")
    out["think"] = game.choose("road:think")[0]
    return out


def test_after_the_nominal_end_of_a_postponed_season_nothing_promises_the_whole_season(content):
    game = _lake(content, WEEKEND, one=True)
    _postponed(content, game)
    game.state.world.time = 13.5 * SHORT
    texts = _texts(game, content)
    for key, line in LATER_TEXTS.items():
        assert line in texts[key], key
    assert not any("這一季之內" in t or "23:59" in t or "第 12 週・週日" in t for t in texts.values())


def test_the_real_last_day_still_says_this_season(content):
    game = _lake(content, WEEKEND, one=True)
    _postponed(content, game)
    game.state.world.time = 15.5 * SHORT
    texts = _texts(game, content)
    assert "這一季之內" in texts["talk"] and "這一季之內" in texts["warning"] and "過一陣子" not in texts["talked_out"]
    assert texts["talked_out"] == "已經談滿 3 輪，這一季之內不能再來"


@pytest.mark.parametrize("finale", [None, 10 * SHORT])
def test_a_season_that_was_not_postponed_is_unchanged(content, finale):
    """沒延後（最後一天照舊「這一季之內」）、提前收季（換日在季末之後：也是「這一季之內」）。"""
    game = _lake(content, WEEKEND, one=True)
    if finale is not None:
        _postponed(content, game, finale)
    game.state.world.time = (9.5 if finale else 13.5) * SHORT
    assert rules.day_turn(content, game.state.world) == ("season", None)
    assert game._talked_out_note() == "已經談滿 3 輪，這一季之內不能再來"  # noqa: SLF001
