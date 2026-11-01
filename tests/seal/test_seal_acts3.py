"""玉璽碎片改版第 3 批：鎮地（螭首）、補缺（金角），建在翻地與爭搶上（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第三章、
第四章、五之一第 5、7 條；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-3.md）。順手的 FB-626、FB-627、FB-642 也在這裡。
都是正式內容（21 天季＋領地爭奪打開，除非另寫），標 slow。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path

import pytest

import server
from conftest import real_content
from conquest_kit import conquest_rules
from test_seal_acts import _do, _give, _person, _uses
from tianxia import calendar, conquest, seal, seal_acts
from tianxia.calendar import DAY
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import SealAct

HUANG_BLOCKS = ["runan", "runan_academy", "runan_market", "qiao_county", "xinye"]  # 開季黃巾的、搶得下來的（大本營與廣宗不算）


def _world(profile="season21", *, conquest_on=True, on=True):
    c = real_content(profile)
    if conquest_on:
        conquest_rules(c)
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = on
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0
    w = open_world(Path(tempfile.mkdtemp(prefix="seal3-")) / "t.db")
    return c, w


def _holder(shard, *, side="huang", at="runan", conquest_on=True, profile="season21", name="懷璽"):
    c, w = _world(profile, conquest_on=conquest_on)
    _give(c, w, shard, name)
    return c, w, _person(c, w, name, side=side, at=at)


def _use(c, w, target="", side="", now=10.0, name="懷璽"):
    return _do(c, w, name, lambda g: g.seal_use(target, side), now=now)


def _act(c, w, name="懷璽", now=10.0):
    return _do(c, w, name, lambda g: server.main_view(g)["status"]["seal"]["act"], now=now)


def _season(c, w, fn, now=10.0, name="懷璽"):
    """照伺服器在季上做一件事（翻一塊、推一下）：讀、改、存回去。"""
    return _do(c, w, name, lambda g: fn(g.state.world), now=now)


def _hold(start: float, until: float, loc="runan", side="huang") -> SealAct:
    return SealAct(kind="zhendi", shard="chishou", start=start, until=until, target=loc, side=side)


# ── Task 1：內容、設定、資料欄位 ──

def test_the_two_shards_get_their_acts_and_numbers():
    """設計第三章：螭首鎮地、金角補缺；鎮地 12 個季曆小時、補缺的窗口 1 個季曆天（PM 五之一 5）是【預設】。"""
    c = real_content()
    assert (c.seal["chishou"].act, c.seal["jinjiao"].act) == ("zhendi", "bujue")
    acts = c.config.seal.revamp.acts
    assert (acts.hold_hours, acts.mend_days) == (12, 1)
    assert seal_acts.act_of(c, "chishou") == "zhendi"
    c.config.seal.revamp.enabled = False
    assert seal_acts.act_of(c, "chishou") is None and seal_acts.act_of(c, "jinjiao") is None


def test_a_flip_remembers_who_held_the_block():
    """設計五之一 5：翻地記下每塊最近一次易手的時刻與原主（day_log 只記新主人）。推滿、攻城戰打贏都寫；中立地沒人佔是 None。"""
    c, w = _world()
    from conquest_kit import _new

    g = _new(c, "記帳", world=w)
    wd = g.state.world
    conquest.push(wd, c, "yingchuan_wilds", "huang", "甲", 100, "attack")
    fight = conquest.fight_of(wd, "yingchuan_wilds")
    assert (fight.flipped_at, fight.flipped_from) == (wd.time, "guan")
    conquest.push(wd, c, "hilltop_wilds", "guan", "乙", 100, "attack")
    assert conquest.fight_of(wd, "hilltop_wilds").flipped_from is None
    conquest.flip(wd, c, "runan", "guan", note=False)  # 攻城戰打贏走同一條
    assert conquest.fight_of(wd, "runan").flipped_from == "huang"


# ── 鎮地 ──

def test_zhendi_lists_your_own_blocks_and_greys_a_cooling_one():
    c, w, g = _holder("chishou")
    act = _act(c, w)
    assert (act["kind"], act["name"], act["ok"], act["idle"], act["sides"]) == ("zhendi", "鎮地", True, False, [])
    assert [(t["id"], t["side"], t["why"]) for t in act["targets"]] == [(loc, "huang", "") for loc in HUANG_BLOCKS]
    assert "替黃巾軍鎮住{target}半日" in act["confirm"]
    _season(c, w, lambda wd: conquest.push(wd, c, "yingchuan_wilds", "huang", "甲", 100, "attack"), now=20.0)
    rows = {t["id"]: t for t in _act(c, w, now=30.0)["targets"]}
    assert rows["yingchuan_wilds"]["why"] == seal_acts.LAND_COOLING  # 剛翻下來、還在冷卻：鎮不了（設計）
    refused = _use(c, w, target="yingchuan_wilds", now=40.0)
    assert seal_acts.LAND_COOLING in refused[0] and _uses(w) == [] and w.get_season().seal_acts == []


def test_zhendi_books_a_half_day_hold_and_names_nobody():
    c, w, g = _holder("chishou")
    _use(c, w, target="runan")
    season = w.get_season()
    [act] = season.seal_acts
    assert (act.kind, act.target, act.side) == ("zhendi", "runan", "huang")
    assert act.until - act.start == pytest.approx(DAY / 2)  # 21 天季一個季曆天 24 小時：半日
    public = [r.text for r in season.rumors if "螭首" in r.text]
    assert public == ["有人起用了『螭首』：汝南被鎮住了，半日之內誰都推不動那裡的進度。"] and "懷璽" not in public[0]
    [use] = _uses(w)
    assert (use.holder, use.act) == ("懷璽", "zhendi")
    card = _act(c, w, now=20.0)
    assert card["left"] == 1 and card["live"].startswith("生效中：汝南被鎮住了")


def test_zhendi_stops_every_push_on_that_block_until_it_ends():
    """鎮住的那一塊誰都推不動：對面攻、自家守、事件、戰書都擋（WHY_HELD）；別的塊照舊；期滿照舊。
    開季黃巾碰得到官軍的涿郡（兩邊直通的那一塊），官軍的懷璽者鎮住它。"""
    c, w, g = _holder("chishou", side="guan", at="zhuo_county")
    _season(c, w, lambda wd: conquest.push(wd, c, "zhuo_county", "huang", "巾甲", 30, "attack"))
    assert conquest.push_problem(w.get_season(), c, "huang", "zhuo_county", "attack") is None
    _use(c, w, target="zhuo_county", now=20.0)
    game = Game(c, CharacterStore(w.db).load("懷璽"), random.Random(0), w)
    game.sync(30.0)
    wd = game.state.world
    why = conquest.push_problem(wd, c, "huang", "zhuo_county", "attack")
    assert why is not None and why.startswith("這一塊被鎮住了，") and "之前誰都推不動" in why
    assert conquest.push_problem(wd, c, "guan", "zhuo_county", "hold") == why
    assert conquest.letter_problem(wd, c, "huang", "zhuo_county", 0) == why
    assert conquest.push_problem(wd, c, "guan", "market_town", "hold") == conquest.WHY_IDLE  # 別的塊照舊
    assert "zhuo_county" not in conquest.focus_blocks(wd, c, "huang", "attack")  # 軍令與假人都問同一個判斷
    assert "zhuo_county" not in conquest.focus_blocks(wd, c, "guan", "defend")
    before = conquest.bar(wd, "zhuo_county", "huang")
    assert game._push_progress("zhuo_county", 1, "event") == [] and conquest.bar(wd, "zhuo_county", "huang") == before
    wd.time = wd.seal_acts[0].until
    assert conquest.push_problem(wd, c, "huang", "zhuo_county", "attack") is None


def test_zhendi_keeps_the_bars_from_falling_back_that_day():
    """對面的進度不漲、也不回：那一天鎮過，每日回跳過那一塊；沒鎮的照回。"""
    def after_a_quiet_day(hold: bool) -> float:
        c, w = _world()
        from conquest_kit import _new

        wd = _new(c, "推").state.world
        conquest.decay(wd, c)  # 這一季第一次只記下今天
        conquest.push(wd, c, "runan", "guan", "官甲", 30, "attack")
        day1 = calendar.day_start(2, c, wd)  # 第 2 天 00:00（從 1 算）
        if hold:
            wd.seal_acts.append(_hold(day1 + 100, day1 + 100 + DAY / 2))
        wd.time = calendar.day_start(3, c, wd) + 1
        conquest.decay(wd, c)
        return conquest.bar(wd, "runan", "guan")

    assert after_a_quiet_day(False) == pytest.approx(30 - real_content().config.conquest.decay_per_day)
    assert after_a_quiet_day(True) == pytest.approx(30)


def test_zhendi_ends_when_the_block_changes_hands():
    """鎮著的那一塊換了主人（攻城戰、時刻表、管理者、補缺）：替原主鎮的那一筆當場結束，新主人不吃。"""
    c, w = _world()
    from conquest_kit import _new

    wd = _new(c, "推").state.world
    wd.time = 50.0
    wd.seal_acts.append(_hold(0.0, DAY / 2, side="guan"))  # 替別人鎮的（主人換過、沒經過 _announce 的那種）不算：第二層
    assert seal_acts.held(wd, c, "runan", "huang") is None
    wd.seal_acts = [_hold(0.0, DAY / 2)]
    assert seal_acts.held(wd, c, "runan", "huang") is not None
    conquest.flip(wd, c, "runan", "guan", note=False)
    assert wd.seal_acts[0].ended == 50.0 and seal_acts.held(wd, c, "runan", "guan") is None
    wd.seal_acts.append(_hold(0.0, DAY / 2, loc="runan_academy"))
    conquest.set_control(wd, c, "runan_academy", None)  # 管理者放回中立
    assert wd.seal_acts[1].ended == 50.0


def test_switched_off_a_hold_on_the_books_blocks_nothing():
    c, w = _world()
    from conquest_kit import _new

    wd = _new(c, "推").state.world
    wd.seal_acts.append(_hold(0.0, DAY / 2, loc="zhuo_county", side="guan"))
    assert conquest.push_problem(wd, c, "huang", "zhuo_county", "attack") is not None
    c.config.seal.revamp.enabled = False
    assert conquest.push_problem(wd, c, "huang", "zhuo_county", "attack") is None
    assert not seal_acts.held_during(wd, c, "zhuo_county", 0.0, DAY)


# ── 補缺 ──

def test_bujue_lists_what_was_flipped_away_within_a_day():
    c, w, g = _holder("jinjiao")
    act = _act(c, w)
    assert not act["ok"] and act["why"] == seal_acts.NOTHING["bujue"] and act["targets"] == []  # 還沒丟過地：灰著
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)
    _season(c, w, lambda wd: conquest.push(wd, c, "hilltop_wilds", "guan", "官甲", 100, "attack"), now=110.0)  # 中立地：沒有原主
    act = _act(c, w, now=200.0)
    assert act["ok"] and [(t["id"], t["side"], t["why"]) for t in act["targets"]] == [("runan", "huang", "")]
    assert act["targets"][0]["info"].startswith("被官軍翻走・")
    assert "把{target}退回黃巾軍手中" in act["confirm"]
    late = _act(c, w, now=100.0 + DAY + 60)  # 一日過了
    assert late["why"] == seal_acts.NOTHING["bujue"]


def test_bujue_hands_the_block_back_like_a_flip():
    """補缺：當場退回原主——「收復」天下大事與江湖史、冷卻重新起算、所有條清掉、不分紅；同一塊一季只能補一次。"""
    c, w, g = _holder("jinjiao")
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官乙", 5, "attack"), now=100.0 + 3700)  # 冷卻過了，官軍又推一截
    payouts = len(w.get_season().conquest.payouts)
    msgs = _use(c, w, target="runan", now=100.0 + 3800)
    assert msgs and "汝南當場退回黃巾軍手中" in msgs[0]
    season = w.get_season()
    assert conquest.holder(season, c, "runan") == "huang"
    fight = conquest.fight_of(season, "runan")
    assert fight.bars == {} and fight.flipped_at == pytest.approx(season.time) and fight.flipped_from == "guan"
    assert conquest.cooling(season, c, "runan") and len(season.conquest.payouts) == payouts
    texts = [r.text for r in season.rumors]
    public = "有人起用了『金角』：汝南當場退回黃巾軍手中。"
    assert public in texts and "黃巾軍收復汝南。" in texts and texts.index(public) < texts.index("黃巾軍收復汝南。")
    assert "懷璽" not in public
    [act] = season.seal_acts
    assert (act.kind, act.target, act.side, act.until) == ("bujue", "runan", "huang", act.start)
    # 再被翻走：這一季補過了，灰掉（碎片卡在間隔裡、不列目標，直接問目標那一份）
    again = 100.0 + 3800 + 3700
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=again)
    game = Game(c, CharacterStore(w.db).load("懷璽"), random.Random(0), w)
    game.sync(again + 60)
    assert [(t["id"], t["why"]) for t in seal_acts.land_rows(game.state, c, "bujue")] == [("runan", seal_acts.MENDED)]


def test_bujue_greys_a_block_whose_siege_is_mustering():
    from conquest_kit import announce

    c, w, g = _holder("jinjiao")
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)

    def muster(wd):
        game = Game(c, CharacterStore(w.db).load("懷璽"), random.Random(0), w)
        game.state.world = wd
        slot = announce(game, "runan", "huang")
        slot.status = "open"

    _season(c, w, muster, now=200.0)
    game = Game(c, CharacterStore(w.db).load("懷璽"), random.Random(0), w)
    game.sync(210.0)
    assert [(t["id"], t["why"]) for t in seal_acts.land_rows(game.state, c, "bujue")] == [("runan", seal_acts.SIEGING)]
    act = _act(c, w, now=210.0)
    # 唯一的一塊灰著：整顆按不下去，那一塊照樣列出來、寫原因（FB-645 起；以前是 NOTHING、不列）
    assert act["why"] == seal_acts.ALL_GREY["bujue"] and [(t["id"], t["why"]) for t in act["targets"]] == [("runan", seal_acts.SIEGING)]
    assert seal_acts.ALL_GREY["bujue"] in _use(c, w, target="runan", now=220.0)[0]
    assert _uses(w) == []


def test_fb645_when_every_flipped_block_is_greyed_they_are_still_listed():
    """FB-645：剛被翻走的地全都補不了（這一季補過、正在攻城）時，以前只寫「此刻沒有剛被翻走、補得回來的地」、那一塊與原因都不列（字跟
    天下大事剛寫的易手對不上）。改成照樣列出那幾塊、灰掉、各寫原因（mend_rows 同一個判斷），整顆的原因換一句 ALL_GREY（待 joy 潤）；
    按下去照舊什麼都不動。一塊都沒有的時候照舊 NOTHING。"""
    c, w, g = _holder("jinjiao")
    _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=100.0)
    _season(c, w, lambda wd: wd.seal_acts.append(SealAct(kind="bujue", shard="jinjiao", start=50.0, until=50.0, target="runan",
                                                         side="huang")), now=110.0)  # 這一季補過汝南（之後又被翻走）
    act = _act(c, w, now=200.0)
    assert (act["ok"], act["why"], act["idle"]) == (False, seal_acts.ALL_GREY["bujue"], False)
    assert [(t["id"], t["side"], t["why"]) for t in act["targets"]] == [("runan", "huang", seal_acts.MENDED)]
    assert act["targets"][0]["info"].startswith("被官軍翻走・")
    assert _use(c, w, target="runan", now=210.0) == [f"（{seal_acts.ALL_GREY['bujue']}）"] and _uses(w) == []
    assert conquest.holder(w.get_season(), c, "runan") == "guan"


def test_fb645_zhendi_with_every_block_cooling_lists_them_greyed(monkeypatch):
    c, w, g = _holder("chishou")
    monkeypatch.setattr(conquest, "cooling", lambda world, content, loc_id: True)
    act = _act(c, w)
    assert (act["ok"], act["why"]) == (False, seal_acts.ALL_GREY["zhendi"])
    assert [(t["id"], t["why"]) for t in act["targets"]] == [(loc, seal_acts.LAND_COOLING) for loc in HUANG_BLOCKS]
    assert _use(c, w, target="runan") == [f"（{seal_acts.ALL_GREY['zhendi']}）"] and _uses(w) == []


def test_mend_rows_only_count_flips():
    """時刻表與管理者指定的易手不起冷卻、不算「翻走」；翻走之後又被這樣拿回來的，也不列（此刻已經是自家的）。"""
    c, w, g = _holder("jinjiao")
    _season(c, w, lambda wd: conquest.set_control(wd, c, "runan", "guan"), now=100.0)
    assert _act(c, w, now=200.0)["why"] == seal_acts.NOTHING["bujue"]
    _season(c, w, lambda wd: conquest.push(wd, c, "runan_academy", "guan", "官甲", 100, "attack"), now=300.0)
    assert [t["id"] for t in _act(c, w, now=400.0)["targets"]] == ["runan_academy"]
    _season(c, w, lambda wd: conquest.assign(wd, c, {"runan_academy": "huang"}), now=500.0)  # 時刻表指定回黃巾
    assert _act(c, w, now=600.0)["why"] == seal_acts.NOTHING["bujue"]


def test_fb644_with_conquest_a_pause_is_still_a_pause():
    """領地爭奪打開的季，暫停照舊寫暫停（不是整季用不上）。"""
    c, w, g = _holder("chishou")
    assert w.pause_clock(15.0)
    act = _act(c, w, now=20.0)
    assert (act["ok"], act["why"], act["idle"]) == (False, seal_acts.PAUSED, False)


def test_other_acts_are_never_idle():
    from test_seal_acts import _holder as plain_holder

    c, w, g = plain_holder("yunzhuan")
    assert server.main_view(g)["status"]["seal"]["act"]["idle"] is False


def test_a_ranger_picks_a_side_and_only_that_armys_blocks_count():
    """散人起用要看陣營的三片：每次挑一軍（企劃者）。鎮地的目標兩軍都列（每一列寫是哪一軍的），挑了哪一軍只認那一軍的。"""
    c, w, g = _holder("chishou", side=None, at="yingchuan")
    act = _act(c, w)
    assert [s["id"] for s in act["sides"]] == ["guan", "huang"] and act["side_note"] == seal_acts.PICK_SIDE
    sides = {t["id"]: t["side"] for t in act["targets"]}
    assert sides["runan"] == "huang" and sides["yingchuan_wilds"] == "guan"
    assert "{side}" in act["confirm"]
    assert seal_acts.PICK_SIDE in _use(c, w, target="runan")[0]
    assert seal_acts.BAD_SIDE in _use(c, w, target="runan", side="haoqiang")[0]
    assert seal_acts.BAD_TARGET in _use(c, w, target="runan", side="guan")[0]  # 汝南是黃巾的
    assert _uses(w) == []
    _use(c, w, target="runan", side="huang")
    assert w.get_season().seal_acts[0].side == "huang"


def test_a_faction_member_cannot_pick_the_other_army():
    c, w, g = _holder("chishou", side="huang")
    assert seal_acts.BAD_TARGET in _use(c, w, target="yingchuan_wilds", side="guan")[0]
    _use(c, w, target="runan", side="guan")  # 送來的 side 不理：照自家
    assert w.get_season().seal_acts[0].side == "huang"


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_two_worlds_that_differ_only_in_who_used_it_look_the_same():
    """不具名（企劃者）：甲客或乙客懷著那一片（同一陣營、同一處、同樣的目標），旁觀客看到的江湖頁、江湖史、天下大事與傳聞、輿圖、
    兩人的玩家卡一個字不差。補缺那一場先讓官軍翻走汝南。"""
    import json

    from tianxia import social, tavern

    def world(shard: str, user: str) -> dict:
        c, w = _world()
        _give(c, w, shard, user)
        for name in ("甲客", "乙客"):
            _person(c, w, name, side="huang", at="runan_wilds")
        _person(c, w, "旁觀客", side="huang", at="runan")
        if shard == "jinjiao":
            _season(c, w, lambda wd: conquest.push(wd, c, "runan", "guan", "官甲", 100, "attack"), now=5.0, name="旁觀客")
        for name in ("甲客", "乙客"):
            _do(c, w, name, (lambda g: g.seal_use("runan")) if name == user else (lambda g: None), now=10.0)
        assert [e.holder for e in w.seal_state().registry.uses] == [user]
        store = CharacterStore(w.db)

        def look(viewer):
            season = w.get_season()
            out = {"main": json.dumps(server.main_view(viewer), ensure_ascii=False, sort_keys=True, default=str),
                   "chronicle": viewer.chronicle_text(), "rumors": [(r.layer, r.text, r.location) for r in season.rumors],
                   "history": [r.text for r in season.chronicle],
                   "map": json.dumps(server.map_view(viewer, server.DEFAULT_LAYER, "runan"), ensure_ascii=False, sort_keys=True, default=str)}
            for name in ("甲客", "乙客"):
                out[f"card:{name}"] = json.dumps(social.card(viewer, viewer._kin(store.load(name))), ensure_ascii=False, sort_keys=True,
                                                 default=str)
                other = store.load(name)
                other.world = viewer.state.world
                # FB-643：酒肆打聽交情、查人在哪、名氣、近況、買兇找人（打聽度夠高的那一種在 test_seal_acts.py 的 FB-643 那一段）
                out[f"tavern:{name}"] = (tavern.ties_player_lines(viewer.state, c, other, [], set()),
                                         tavern.seek_lines(viewer.state, c, other, 100.0, set()), tavern.person_fame(other, c),
                                         tavern.fresh(other, viewer.state.world.time), tavern.hit_reach(c, "runan", other))
            return out

        return _do(c, w, "旁觀客", look, now=20.0)

    for shard in ("chishou", "jinjiao"):
        a, b = world(shard, "甲客"), world(shard, "乙客")
        for key in a:
            assert a[key] == b[key], (shard, key)
        assert any("有人起用了" in text for _, text, _ in a["rumors"])


# ── FB-626、FB-627、FB-642 ──

def test_fb626_the_card_says_the_stir_not_the_act():
    """FB-626：碎片卡「新得之季，此季不動」緊挨獨門行動那一行，讀起來像用不了——改版開著寫明是璽動；關著照舊。"""
    from test_seal_acts import _holder as plain_holder

    def fresh(st):
        st.seal.shards["xuanniu"].since_season = st.season_number  # 這一季剛拿到的

    for on, new, calm in ((True, "新得之季：這一季不會被璽動牽動", "這一季可能被璽動牽動"), (False, "新得之季，此季不動", "此季可能被牽動")):
        c, w, g = plain_holder("xuanniu", on=on)
        assert g.seal_view()["state"] == calm
        w.mutate(fresh)
        assert g.seal_view()["state"] == new


def test_fb627_a_merged_line_is_not_written_as_a_place():
    """FB-627：14 天的季三條戰線合成黃巾聲勢，傳檄那一句不把線名當地名寫；有戰線的季一個字不變。"""
    from test_seal_acts import _holder as plain_holder
    from test_seal_acts import _use as plain_use

    c, w, g = plain_holder("chizhang", side="huang", profile=None)
    act = server.main_view(g)["status"]["seal"]["act"]
    assert act["confirm"].startswith("起用『赤璋』，替黃巾軍傳檄天下一日？")
    plain_use(c, w, target="huangjin")
    [line] = [r.text for r in w.get_season().rumors if "赤璋" in r.text]
    assert line == "有人起用了『赤璋』：檄文傳遍天下，一日之內黃巾軍聲勢更盛。"
    c, w, g = plain_holder("chizhang", side="huang")
    assert "替黃巾軍傳檄{target}一日？" in server.main_view(g)["status"]["seal"]["act"]["confirm"]
    plain_use(c, w, target="yingru")
    assert any(r.text == "有人起用了『赤璋』：檄文傳遍潁川汝南，一日之內黃巾軍在那裡推得更猛。" for r in w.get_season().rumors)


def test_fb642_the_shard_is_not_hidden_somewhere_not_yet_open():
    """FB-642：藏碎片的地方跳過劇情還沒開放的區塊（沒立「綠林開寨」的綠林山寨去不了）。"""
    from conquest_kit import _new

    c, w = _world()
    wd = _new(c, "藏", world=w).state.world
    spots = [loc for loc, _ in seal.hide_spots(c, wd)]
    assert "lulin_zhai" in spots  # 正式內容開季就立了
    wd.flags.discard(c.locations["lulin_zhai"].unlock_flag)
    assert "lulin_zhai" not in [loc for loc, _ in seal.hide_spots(c, wd)]
    assert len(seal.hide_spots(c, wd)) == len(spots) - 1
