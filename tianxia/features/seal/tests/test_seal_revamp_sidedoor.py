"""玉璽碎片改版第 1 批 QA 之後的修正（FB-625、FB-615；企劃者 2026-10-21「給別人看的截殺勝算、擂台身手照不含碎片的算，
真的打起來照吃碎片的戰力」；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-1.md 〈QA 之後的修正〉）。

碎片的戰力 ×1.10 是真的：截殺、設伏、切磋、擂台打起來照含碎片的威力擲，勝負、份量、損耗都不變。但給**別人**看的三種字——
截殺鈕上的勝算、擂台挑人的「身手」、四種戰報（切磋、截殺、設伏、擂台）上的「對手威力 N」——照持有者**不含碎片**的那一份算，
不然對同一個人拿到碎片前後看一次，字就變了（持有者平時藏起來被側門看穿）。持有者自己看自己的也照不含碎片的算，
免得他的畫面跟別人看到的對不上。兩個只差誰持有的世界、旁人看到的一個字不差，在 test_seal_revamp_hidden.py。

測試內容裡甲（官軍）懷著螭首、乙（官軍）跟他一模一樣但沒有碎片：甲的威力 55、不含碎片 50，乙 50。丙、丁（黃巾，臂力 12）威力 60.5，
戊（黃巾，臂力 5）威力 50——強度挑在含碎片算會讓勝算字、身手字變的位置，沒有這個前提下面的「一樣」證明不了什麼。"""
from __future__ import annotations

import random
import re

import pytest

from conftest import real_content
from test_seal import sealed  # noqa: F401  sealed 是夾具
from test_seal_revamp import revamp
from tianxia import arena, battlelog, encounter, rules, team
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import MOVES, Squad
from tianxia.state import ArenaEntry, ArenaReport, ArenaSide

NOW = 1000.0
CAST = (("甲", "guan", 5), ("乙", "guan", 5), ("丙", "huang", 12), ("丁", "huang", 12), ("戊", "huang", 5))  # 名號、陣營、臂力（5 是基準）


@pytest.fixture
def trio(sealed, world):
    """測試內容＋七片＋改版；五個人都在湖畔（不是城鎮）、學了拳腳、過了新手期；甲懷著螭首。回（內容, 資料庫）。"""
    c = revamp(sealed)
    c.config.auto_open_first_season = True
    c.config.newbie_days = -1
    c.config.newbie_real_hours = 0
    c.config.arena.enabled = True

    def _give(st):
        from tianxia import seal

        shard = seal.filled(st.seal, c).shards["chishou"]
        shard.state, shard.holder, shard.since_season = "held", "甲", 0

    world.mutate(_give)
    for name, side, strength in CAST:
        game = Game.new(c, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, c, "fist")
        p = game.state.player
        p.faction, p.location, p.stamina = side, "lake", 200.0
        p.stats["str"] = strength
        game.sync(NOW)
        game.sync(NOW + 1)  # 甲的傳承那一格照登記抄好
        CharacterStore(world.db).save(game.state)
    return c, world


def _do(content, world, name, act, now=NOW + 2):
    """照伺服器：重讀這個人、補算到此刻、做一個動作、存回去（連同共用賽季）。回（訊息, 做完的 Game）。"""
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(now)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _g(content, world, name):
    return _do(content, world, name, lambda g: None)[1]


def _word(mine: float, theirs: float) -> str:
    return team.odds_word(mine, Squad(id="x", name="x", difficulty=theirs))


def _shown(record) -> int:
    """戰報頁上寫的「對手威力 N」。"""
    return int(re.search(r"對手威力 (\d+)", battlelog.detail_text(record)).group(1))


def _fmt(power: float) -> int:
    return int(f"{power:.0f}")


def _own(record) -> int:
    return int(re.search(r"我方威力 (\d+)", battlelog.detail_text(record)).group(1))


def _last(world, name):
    return CharacterStore(world.db).load(name).battles[0]


# ── 前提：碎片是真的，而且在這個強度上會讓字變 ──

def test_the_cast_stands_where_the_shard_would_change_the_words(trio):
    c, w = trio
    holder, twin = _g(c, w, "甲"), _g(c, w, "乙")
    assert holder._battle_power() == pytest.approx(55.0) and holder._battle_power(seal=False) == pytest.approx(50.0)
    assert twin._battle_power() == pytest.approx(50.0)
    viewer = _g(c, w, "丙")
    mine = Game._spar_power(viewer, holder)
    assert _word(mine, Game._spar_power(holder, viewer)) != _word(mine, Game._spar_power(holder, viewer, seal=False))
    assert arena.strength_words(c, viewer._battle_power(), 55.0) != arena.strength_words(c, viewer._battle_power(), 50.0)


# ── FB-625：截殺鈕上的勝算 ──

def test_the_raid_button_odds_leave_the_shard_out(trio):
    """旁人看持有者與沒有碎片的雙胞胎，勝算字一樣，照不含碎片的算（以前持有者那一顆多一階）。"""
    c, w = trio
    holder, twin, viewer = _g(c, w, "甲"), _g(c, w, "乙"), _g(c, w, "丙")
    mine = Game._spar_power(viewer, holder)
    real, bare = Game._spar_power(holder, viewer), Game._spar_power(holder, viewer, seal=False)
    assert real == pytest.approx(bare * 1.1) and _word(mine, real) != _word(mine, bare)  # 前提
    assert viewer.raid_odds(holder) == viewer.raid_odds(twin) == _word(mine, bare)

    def note(name):
        return next(b["note"] for b in _g(c, w, "丙").peer_card(name)["actions"] if b["action"] == "raid")

    assert note("甲").split("勝算")[1] == note("乙").split("勝算")[1] == f" {_word(mine, bare)}"


def test_the_holder_reads_his_own_raid_odds_without_the_shard_too(trio):
    """持有者自己看別人也照不含碎片的算：他的畫面跟旁人看到的他對得上（跟沒有碎片的雙胞胎看同一個人一樣）。"""
    c, w = trio
    holder, twin, target = _g(c, w, "甲"), _g(c, w, "乙"), _g(c, w, "戊")
    theirs = Game._spar_power(target, holder)
    real, bare = Game._spar_power(holder, target), Game._spar_power(holder, target, seal=False)
    assert _word(real, theirs) != _word(bare, theirs)  # 前提
    assert holder.raid_odds(target) == twin.raid_odds(target) == _word(bare, theirs)
    assert dict(holder.raid_targets())["戊"] == dict(twin.raid_targets())["戊"] == _word(bare, theirs)


def test_a_raid_is_still_fought_with_the_real_power(trio, monkeypatch):
    """打起來照吃碎片的戰力（勝負不變）：判定收到的是含碎片的威力，只有鈕上的字與戰報上的「對手威力」不含。"""
    c, w = trio
    holder, viewer = _g(c, w, "甲"), _g(c, w, "丙")
    real_theirs, real_ours = Game._spar_power(holder, viewer), Game._spar_power(viewer, holder)
    seen = []
    resolve = encounter.resolve_encounter
    monkeypatch.setattr(encounter, "resolve_encounter", lambda ours, theirs, rng, *a, **k: (seen.append((ours, theirs)),
                                                                                         resolve(ours, theirs, rng, *a, **k))[1])
    _do(c, w, "丙", lambda g: g.peer_act("甲", "raid"))
    assert seen and seen[-1] == (pytest.approx(real_ours), pytest.approx(real_theirs))
    assert real_theirs == pytest.approx(Game._spar_power(holder, viewer, seal=False) * 1.1)


# ── FB-615：切磋、截殺、設伏、擂台的戰報寫「對手威力 N」──

@pytest.mark.smoke
def test_a_spar_report_names_the_rivals_bare_power(trio):
    """丙跟甲切磋（甲答應）：丙的戰報寫甲不含碎片的 50（不是 55），甲自己的「我方威力」照實寫 55；甲發邀請、丙答應也一樣；
    對沒有碎片的乙寫 50，跟對甲一樣。"""
    c, w = trio
    viewer_power = _fmt(Game._spar_power(_g(c, w, "丙"), _g(c, w, "甲")))
    for inviter, answerer in (("丙", "甲"), ("甲", "丙"), ("丙", "乙")):
        _do(c, w, inviter, lambda g, other=answerer: g.peer_act(other, "spar", {"arg": "invite"}))
        iid = w.get_season().invites[0].id
        _do(c, w, answerer, lambda g: g.choose(f"invite:yes:{iid}"))
    rows = {name: [r for r in CharacterStore(w.db).load(name).battles if r.kind == "spar"] for name in ("甲", "乙", "丙")}
    assert [_shown(r) for r in rows["丙"]] == [50, 50, 50]  # 對乙、對甲（甲發邀請）、對甲（丙發邀請）：都是 50
    assert [_own(r) for r in rows["甲"]] == [55, 55]  # 持有者自己的「我方威力」照實寫
    assert [_shown(r) for r in rows["甲"]] == [viewer_power, viewer_power]  # 丙沒有碎片：寫他的威力
    assert [_shown(r) for r in rows["乙"]] == [viewer_power]


def test_a_raid_on_the_holder_reports_his_bare_power(trio):
    """丙截殺甲：丙的戰報寫甲不含碎片的 50；甲（被截殺）自己的戰報我方 55、對手寫丙的威力。"""
    c, w = trio
    viewer_power = _fmt(Game._spar_power(_g(c, w, "丙"), _g(c, w, "甲")))
    _do(c, w, "丙", lambda g: g.peer_act("甲", "raid"))
    assert _last(w, "丙").kind == "raid" and _shown(_last(w, "丙")) == 50
    assert _own(_last(w, "甲")) == 55 and _shown(_last(w, "甲")) == viewer_power


def test_a_raid_by_the_holder_reports_his_bare_power_to_the_victim(trio):
    """甲截殺丁：丁（被截殺的人）的戰報寫甲不含碎片的 50（以前是 55）；甲自己的戰報我方 55、對手寫丁的威力。"""
    c, w = trio
    ding = _fmt(Game._spar_power(_g(c, w, "丁"), _g(c, w, "甲")))
    _do(c, w, "甲", lambda g: g.peer_act("丁", "raid"))
    assert _last(w, "丁").kind == "raid" and _shown(_last(w, "丁")) == 50
    assert _own(_last(w, "甲")) == 55 and _shown(_last(w, "甲")) == ding


def test_a_lost_raid_reads_the_same_as_always(trio, monkeypatch):
    """勝負與損耗不動：判定結果釘死成「大勝」，甲照常贏、丙照常丟銀兩，戰報的「對手威力」只改字。"""
    c, w = trio
    resolve = encounter.resolve_encounter
    monkeypatch.setattr(encounter, "resolve_encounter", lambda ours, theirs, rng, *a, **k: resolve(ours, theirs, rng, *a, **k).model_copy(
        update={"tier": "落敗", "margin": -80}))
    before = CharacterStore(w.db).load("丙").player.stats.get("silver", 0)
    _do(c, w, "丙", lambda g: g.peer_act("甲", "raid"))
    after = CharacterStore(w.db).load("丙").player.stats.get("silver", 0)
    assert after < before and _last(w, "丙").tier == "落敗" and _shown(_last(w, "丙")) == 50


# ── FB-625：擂台挑人的「身手」；FB-615：擂台戰報 ──

def _ring(c, w):
    """榜：丁 1、甲 2、乙 3、丙 4（丙看得到前三名；甲看得到丁）。"""
    for name in ("丁", "甲", "乙", "丙"):
        _do(c, w, name, lambda g: g.choose("act:arena") + g.choose("arena:join") + g.choose("arena:back"))


def _strength_of(options, name: str) -> str:
    label = next(o.label for o in options if o.id == f"arena:fight:{name}")
    return re.search(r"身手(.+?)・", label).group(1)


def test_the_arena_strength_words_read_the_bare_power(trio):
    c, w = trio
    _ring(c, w)
    _, viewer = _do(c, w, "丙", lambda g: g.choose("act:arena"))
    mine = viewer._battle_power()
    bare = arena.strength_words(c, mine, 50.0)
    assert arena.strength_words(c, mine, 55.0) != bare  # 前提：含碎片算會變
    assert _strength_of(viewer._arena_options(), "甲") == _strength_of(viewer._arena_options(), "乙") == bare
    words = {f["name"]: f["strength"] for f in viewer.shop_view()["foes"]}  # 擂台那一頁的挑戰卡
    assert words["甲"] == words["乙"] == "身手" + bare


def test_the_holder_reads_the_arena_without_his_own_shard(trio):
    """持有者看別人的身手，連他自己這一邊也不含碎片：跟沒有碎片的雙胞胎乙看同一個人一樣。"""
    c, w = trio
    _ring(c, w)
    holder, twin = _g(c, w, "甲"), _g(c, w, "乙")
    foe = _g(c, w, "丁")
    assert arena.strength_words(c, 55.0, foe._battle_power()) != arena.strength_words(c, 50.0, foe._battle_power())  # 前提
    assert _strength_of(holder._arena_options(), "丁") == arena.strength_words(c, 50.0, foe._battle_power())
    assert _strength_of(holder._arena_options(), "丁") == _strength_of(twin._arena_options(), "丁")
    for name in ("甲", "乙"):  # 擂台那一頁的挑戰卡也一樣
        _, page = _do(c, w, name, lambda g: g.choose("act:arena"))
        assert {f["name"]: f["strength"] for f in page.shop_view()["foes"]}["丁"] == "身手" + arena.strength_words(c, 50.0, foe._battle_power())


def test_the_arena_keeps_a_bare_copy_only_for_the_holder(trio):
    c, w = trio
    _ring(c, w)
    entries = w.get_season().arena
    assert entries["甲"].power == pytest.approx(55.0) and entries["甲"].bare == pytest.approx(50.0)
    assert entries["乙"].bare is None and entries["丙"].bare is None  # 沒有碎片：威力本身就是給別人看的那一份
    assert entries["甲"].shown == pytest.approx(50.0) and entries["乙"].shown == pytest.approx(50.0)
    # 碎片易主（奪璽單挑輸了）：甲再更新分身，不含碎片的複本跟著清掉；乙拿到之後更新，換成乙有
    def _hand_over(st):
        st.seal.shards["chishou"].holder = "乙"

    w.mutate(_hand_over)
    join = lambda g: g.choose("act:arena") + g.choose("arena:join") + g.choose("arena:back")  # noqa: E731
    _do(c, w, "甲", join)
    _do(c, w, "乙", join)
    entries = w.get_season().arena
    assert entries["甲"].bare is None and entries["甲"].power == pytest.approx(50.0)
    assert entries["乙"].bare == pytest.approx(50.0) and entries["乙"].power == pytest.approx(55.0)


def test_an_arena_bout_is_fought_real_and_reported_bare(trio):
    """丙挑甲的分身：打的是含碎片的 55（ArenaFight.foe.power），戰報的「對手威力」寫不含碎片的 50；
    甲挑丁：丁（守擂的人）下次同步補的守擂戰報寫甲不含碎片的 50，甲自己的戰報我方 55、對手寫丁的威力。"""
    c, w = trio
    _ring(c, w)
    ding = _g(c, w, "丁")._battle_power()
    bing = _g(c, w, "丙")._battle_power()
    started = {}

    def go(name, foe):
        def act(g):
            g.choose("act:arena")
            g.choose(f"arena:fight:{foe}")
            started[name] = g.state.player.arena.model_copy(deep=True)
            i = 0
            while g.state.player.arena is not None:
                g.choose(f"arena:{MOVES[i % len(MOVES)]}")
                i += 1
        return act

    _do(c, w, "丙", go("丙", "甲"), now=NOW + 10)
    assert started["丙"].foe.power == pytest.approx(55.0) and started["丙"].foe.bare == pytest.approx(50.0)  # 打的是含碎片的
    assert started["丙"].me.power == pytest.approx(bing) and started["丙"].me.bare is None
    mine = _last(w, "丙")
    assert mine.kind == "arena" and _shown(mine) == 50
    _do(c, w, "甲", go("甲", "丁"), now=NOW + 20)
    assert started["甲"].me.power == pytest.approx(55.0) and started["甲"].me.bare == pytest.approx(50.0)
    report = w.get_season().arena["丁"].inbox[-1]
    assert report.power == pytest.approx(55.0) and report.bare == pytest.approx(50.0) and report.shown == pytest.approx(50.0)
    holder_card = _last(w, "甲")
    assert _own(holder_card) == 55 and _shown(holder_card) == _fmt(ding)
    _do(c, w, "丁", lambda g: None, now=NOW + 30)  # 守擂的人同步，補戰報
    defended = [r for r in CharacterStore(w.db).load("丁").battles if r.kind == "arena"][0]
    assert _shown(defended) == 50 and _own(defended) == _fmt(ding)
    _do(c, w, "甲", lambda g: None, now=NOW + 40)  # 甲被丙挑過：守擂的戰報寫丙的威力，我方是甲分身的 55
    guarded = [r for r in CharacterStore(w.db).load("甲").battles if r.event.startswith("守擂")]
    assert [_shown(r) for r in guarded] == [_fmt(bing)] and [_own(r) for r in guarded] == [55]


def test_an_old_arena_entry_without_the_bare_field_still_loads():
    entry = ArenaEntry.model_validate({"name": "舊人", "power": 12.0, "hp_cap": 100.0})
    assert entry.bare is None and entry.shown == 12.0
    side = ArenaSide.model_validate({"name": "舊人", "power": 12.0, "hp": 100.0, "hp_cap": 100.0})
    assert side.bare is None and side.shown == 12.0
    report = ArenaReport.model_validate({"challenger": "舊人", "tier": "大勝", "time": 0.0, "rank": 1, "before": 2, "power": 9.0})
    assert report.bare is None and report.shown == 9.0


# ── 子開關關著：什麼都不變 ──

def test_with_the_revamp_off_nothing_is_bare_or_hidden(trio):
    c, w = trio
    c.config.seal.revamp.enabled = False
    holder = _g(c, w, "甲")
    assert holder._battle_power() == holder._battle_power(seal=False)
    _ring(c, w)
    assert all(e.bare is None for e in w.get_season().arena.values())
    viewer = _g(c, w, "丙")
    assert viewer.raid_odds(holder) == _word(Game._spar_power(viewer, holder), Game._spar_power(holder, viewer))


# ── 設伏（正式內容）──

@pytest.mark.slow
@pytest.mark.parametrize("holder_is_owner", [True, False])
def test_an_ambush_report_names_the_rivals_bare_power(world, holder_is_owner):
    """設伏的伏兵與中伏的人，戰報寫對方不含碎片的威力（正式內容：無碎片 8.64，含碎片 9.504），打起來照含的。"""
    from test_stamina_plays import _player, _plays_on, _reload, _set
    from tianxia import seal

    c = _plays_on(real_content())
    c.config.auto_open_first_season = True
    c.config.train_event_chance = c.config.road_sight_chance = 0.0
    holder_name = "黃甲" if holder_is_owner else "官乙"

    def _give(st):
        shard = seal.filled(st.seal, c).shards["chishou"]
        shard.state, shard.holder, shard.since_season = "held", holder_name, 0

    world.mutate(_give)
    for name, side, at in (("黃甲", "huang", "huangjin_camp"), ("官乙", "guan", "changshe")):
        game = _player(c, world, name, side, at)
        game.sync(1000.0)  # 傳承那一格照登記抄好
        CharacterStore(world.db).save(game.state)
    owner, passer = _reload(world, c, "黃甲"), _reload(world, c, "官乙")
    held = owner if holder_is_owner else passer
    assert held._battle_power() == pytest.approx(held._battle_power(seal=False) * 1.1)
    assert _fmt(Game._spar_power(held, passer if holder_is_owner else owner)) != \
        _fmt(Game._spar_power(held, passer if holder_is_owner else owner, seal=False))  # 前提：四捨五入之後字也會變
    owner_bare, passer_bare = Game._spar_power(owner, passer, seal=False), Game._spar_power(passer, owner, seal=False)
    _set(owner)
    passer = _reload(world, c, "官乙")
    passer.travel("huangjin_camp", "dash")
    back = _reload(world, c, "黃甲")
    assert back.state.battles[0].kind == passer.state.battles[0].kind == "ambush"
    assert _shown(passer.state.battles[0]) == _fmt(owner_bare)  # 中伏的人看到的伏兵
    assert _shown(back.state.battles[0]) == _fmt(passer_bare)  # 伏兵看到的路過的人
