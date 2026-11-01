"""玉璽碎片改版第 2 批：五片的獨門行動——引將（玄紐）、頒詔（雲篆）、承露（承露）、傳檄（赤璋）、收心（歸心）
（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第三、四、五、五之一章；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-2.md）。
純規則用測試內容（test_seal_revamp.revamp 打開改版、再裝上五片的行動）；起用與各行動的掛點用正式內容（標 slow）。
不具名的守門（兩個只差「誰起用」的世界）在 test_seal_acts_hidden.py。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path
import json

import pytest

import server
from conftest import no_plans, real_content
from test_seal import put_shards, seal_problems, sealed  # noqa: F401  sealed 是夾具
from test_seal_revamp import revamp
from tianxia import annals, biography, calendar, conquest, renown, seal, seal_acts, tavern
from tianxia.calendar import DAY
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import SealAct, WorldState
from tianxia.world_state import SealShard
from conquest_kit import conquest_rules

ACTS = {"xuanniu": "yinjiang", "yunzhuan": "banzhao", "chenglu": "chenglu", "chizhang": "chuanxi", "guixin": "shouxin"}
NUMBERS = {"uses": 2, "gap_days": 3, "days": 1, "sense_points": 10, "cultivate": 1.2, "stamina": 1.5, "push": 1.25, "affinity": 2.0,
           "hold_hours": 12, "mend_days": 1}  # 後兩個是第 3 批（鎮地、補缺；tests/test_seal_acts3.py）


def acts_on(content):
    """測試內容：七片、改版打開、五片裝上獨門行動（第 2 批）。"""
    revamp(content)
    for sid, kind in ACTS.items():
        content.seal[sid].act = kind
    return content


# ── Task 1：內容、設定、資料欄位 ──

@pytest.mark.slow
def test_the_real_content_gives_seven_shards_their_acts():
    """設計第三章：玄紐引將、雲篆頒詔、承露承露、赤璋傳檄、歸心收心；螭首鎮地、金角補缺（第 3 批接上：這一條原本鎖「這兩片沒有行動」，
    照設計第七章第 3 條翻過來，第 3 批的測試在 tests/test_seal_acts3.py）。數字是【預設】。"""
    c = real_content()
    assert {sid: s.act for sid, s in c.seal.items() if s.act} == {**ACTS, "chishou": "zhendi", "jinjiao": "bujue"}
    assert c.config.seal.revamp.acts.model_dump() == pytest.approx(NUMBERS)


@pytest.mark.smoke
def test_one_act_goes_to_one_shard_only(sealed):
    acts_on(sealed)
    assert seal_problems(sealed) == []
    sealed.seal["chishou"].act = "banzhao"  # 雲篆已經是頒詔
    assert any("同一種獨門行動只能給一片" in p for p in seal_problems(sealed)), seal_problems(sealed)


def test_an_unknown_act_is_refused_by_the_model():
    from pydantic import ValidationError

    from tianxia.models import ShardDef

    with pytest.raises(ValidationError):
        ShardDef(id="x", name="甲", part="印", effect="hp_cap", act="zhendi_typo")


def test_scatter_clears_the_act_counts(sealed):
    from test_seal import _registry

    acts_on(sealed)
    reg = _registry(sealed, yunzhuan="懷璽")
    seal_acts.note_use(reg.shards["yunzhuan"], 3, 100.0)
    seal.scatter(reg, 3)
    shard = reg.shards["yunzhuan"]
    assert (shard.act_season, shard.act_uses, shard.act_last) == (None, 0, None)


def test_switched_off_there_is_no_act(sealed):
    acts_on(sealed)
    assert seal_acts.act_of(sealed, "yunzhuan") == "banzhao"
    assert seal_acts.act_of(sealed, "chishou") is None  # 測試內容只裝這五片的行動（acts_on）
    sealed.config.seal.revamp.enabled = False
    assert seal_acts.act_of(sealed, "yunzhuan") is None


# ── Task 2：純規則 ──

def test_a_day_is_a_world_day_without_the_calendar(sealed):
    """14 天的季（沒有第一季的章）畫面寫世界天：一日是 24 個世界小時（開發定，計畫第二節第 1 條）。"""
    acts_on(sealed)
    w = WorldState()
    assert not calendar.season_one_on(w, sealed)
    assert seal_acts.day_seconds(sealed, w) == DAY
    assert seal_acts.span(sealed, w) == DAY and seal_acts.gap(sealed, w) == 3 * DAY


@pytest.mark.slow
@pytest.mark.parametrize(("profile", "day"), [("week7", DAY), ("season21", DAY), (None, DAY)])
def test_a_day_follows_the_season_calendar(profile, day):
    """有季曆的季照季曆天（7 天、21 天季一個季曆天 24 小時）；14 天的季照世界天。"""
    c = real_content(profile)
    c.config.auto_open_first_season = True
    w = open_world(Path(tempfile.mkdtemp(prefix="seal2d-")) / "t.db")
    w.seed_first_season(c)
    season = w.get_season()
    assert seal_acts.day_seconds(c, season) == pytest.approx(day)
    assert seal_acts.gap(c, season) == pytest.approx(3 * day)


def test_two_uses_a_season_three_days_apart(sealed):
    acts_on(sealed)
    w = WorldState()
    shard = SealShard(id="yunzhuan", state="held", holder="懷璽")
    assert seal_acts.left(shard, 2, sealed) == 2 and seal_acts.ready_at(shard, 2, sealed, w) is None
    seal_acts.note_use(shard, 2, 1000.0)
    assert seal_acts.left(shard, 2, sealed) == 1
    assert seal_acts.ready_at(shard, 2, sealed, w) == pytest.approx(1000.0 + 3 * DAY)
    seal_acts.note_use(shard, 2, 1000.0 + 3 * DAY)
    assert seal_acts.left(shard, 2, sealed) == 0
    # 換季歸零（記的是上一季）
    assert seal_acts.left(shard, 3, sealed) == 2 and seal_acts.ready_at(shard, 3, sealed, w) is None
    seal_acts.note_use(shard, 3, 5.0)
    assert (shard.act_season, shard.act_uses) == (3, 1)


def test_the_count_follows_the_shard_not_the_holder(sealed):
    """次數記在碎片上：同一季被搶走，新主人只剩還沒用掉的次數（設計第三章）。"""
    acts_on(sealed)
    shard = SealShard(id="yunzhuan", state="held", holder="甲")
    seal_acts.note_use(shard, 1, 10.0)
    shard.holder = "乙"
    assert seal_acts.left(shard, 1, sealed) == 1


def _act(kind, start=0.0, until=DAY, **fields):
    return SealAct(kind=kind, shard={v: k for k, v in ACTS.items()}[kind], start=start, until=until, **fields)


def test_an_act_lives_from_its_start_until_it_ends(sealed):
    act = _act("banzhao", start=100.0, until=200.0)
    assert not seal_acts.active(act, 99.0)
    assert seal_acts.active(act, 100.0) and seal_acts.active(act, 199.0)
    assert not seal_acts.active(act, 200.0)
    act.ended = 150.0  # 提前結束
    assert seal_acts.active(act, 149.0) and not seal_acts.active(act, 150.0)


def test_the_hooks_read_neutral_values_when_nothing_is_live(sealed):
    acts_on(sealed)
    w = WorldState(time=50.0)
    assert seal_acts.edict_sense(w, sealed) == 0 and seal_acts.edict_cultivate(w, sealed) == 1.0
    assert seal_acts.heart_scale(w, sealed, "mate") == 1.0 and not seal_acts.heart_open(w, sealed, "mate")
    assert seal_acts.warmer(w, sealed, "mate", 3) == 3
    assert seal_acts.pinned(w, "bocai") is None and seal_acts.next_end(w) is None


def test_the_hooks_read_live_acts_and_multiply_when_they_stack(sealed):
    """同一個目標被好幾個行動疊到，效果相乘（PM 五之一 7）；期滿照舊。"""
    acts_on(sealed)
    w = WorldState(time=50.0, seal_acts=[_act("banzhao"), _act("banzhao"), _act("shouxin", target="mate"), _act("shouxin", target="mate")])
    assert seal_acts.edict_sense(w, sealed) == 20
    assert seal_acts.edict_cultivate(w, sealed) == pytest.approx(1.44)
    assert seal_acts.heart_open(w, sealed, "mate") and not seal_acts.heart_open(w, sealed, "thug")
    assert seal_acts.heart_scale(w, sealed, "mate") == pytest.approx(4.0)
    assert seal_acts.warmer(w, sealed, "mate", 3) == 12 and seal_acts.warmer(w, sealed, "mate", -3) == -3  # 扣的照舊
    w.time = DAY
    assert seal_acts.edict_sense(w, sealed) == 0 and seal_acts.heart_scale(w, sealed, "mate") == 1.0


def test_switched_off_the_hooks_stay_neutral_even_with_acts_on_the_books(sealed):
    acts_on(sealed)
    w = WorldState(time=50.0, seal_acts=[_act("banzhao"), _act("shouxin", target="mate"), _act("chenglu", target="north")])
    sealed.config.seal.revamp.enabled = False
    assert seal_acts.edict_sense(w, sealed) == 0 and seal_acts.edict_cultivate(w, sealed) == 1.0
    assert seal_acts.heart_scale(w, sealed, "mate") == 1.0 and not seal_acts.heart_open(w, sealed, "mate")
    assert seal_acts.writ_factor(w, sealed, "kou", "guan", 1) == 1.0


def test_the_public_line_names_nobody(sealed):
    acts_on(sealed)
    line = seal_acts.public_text(sealed, _act("banzhao"))
    assert line.startswith("有人起用了『雲篆』") and "{" not in line


# ── Task 3～6：正式內容 ──

def _world(profile="season21", *, on=True, conquest_on=True, plans=True):
    c = real_content(profile) if conquest_on else real_content(profile)  # 正式內容 PM 2026-10-22 起打開
    if not plans:
        no_plans(c)  # 引將測的是「人物原本站在原處」：行程（世界活起來）會先把有行程的人（波才）帶走，要寫死他在哪的測試關掉
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = on
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0  # 新手期的體力回復加快不混進承露的帳
    w = open_world(Path(tempfile.mkdtemp(prefix="seal2-")) / "t.db")
    return c, w


def _give(c, w, shard, name):
    def _apply(st):
        s = seal.filled(st.seal, c).shards[shard]
        s.state, s.holder, s.since_season = "held", name, 0

    w.mutate(_apply)


def _person(c, w, name, *, side=None, at="yingchuan_wilds", now=0.0):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, at, len(c.tutorial.steps)
    p.visited.add(at)
    g.sync(now)
    g._save_season()
    CharacterStore(w.db).save(g.state)
    return g


def _do(c, w, name, fn, now=10.0):
    """照伺服器：重讀這個人、補算到此刻、做一個動作、存回去。"""
    game = Game(c, CharacterStore(w.db).load(name), random.Random(0), w)
    game.client = None
    game.sync(now)
    out = fn(game)
    game._save_season()
    CharacterStore(w.db).save(game.state)
    return out


def _holder(shard, *, profile="season21", side="huang", at="yingchuan_wilds", on=True, name="懷璽", conquest_on=True, plans=True):
    c, w = _world(profile, on=on, conquest_on=conquest_on, plans=plans)
    _give(c, w, shard, name)
    return c, w, _person(c, w, name, side=side, at=at)


def _use(c, w, name="懷璽", target="", side="", now=10.0):
    return _do(c, w, name, lambda g: g.seal_use(target, side), now=now)


def _uses(w):
    return w.seal_state().registry.uses  # FB-695：起用另記一欄，不在 history（tests/seal/test_seal.py 的 FB-695 那一段）


@pytest.mark.slow
def test_using_an_act_books_it_on_the_shard_and_the_season():
    """起用：登記記次數與上一次的世界秒、記一筆 use（只給管理者看：有名號）；季上記一筆生效中的（不記是誰）；天下大事與江湖史各一句
    （不寫是誰）；自己一則江湖紀錄（寫還剩幾次）、一則行狀。"""
    c, w, g = _holder("yunzhuan")
    msgs = _use(c, w)
    shard = w.seal_state().registry.shards["yunzhuan"]
    season = w.get_season()
    assert (shard.act_season, shard.act_uses) == (w.get_season_number(), 1) and shard.act_last == pytest.approx(season.time)
    [use] = _uses(w)
    assert (use.holder, use.shard, use.act) == ("懷璽", "yunzhuan", "banzhao")
    [act] = season.seal_acts
    assert (act.kind, act.shard) == ("banzhao", "yunzhuan") and act.until == pytest.approx(act.start + DAY)
    assert "懷璽" not in act.model_dump_json()
    public = [r.text for r in season.rumors if "雲篆" in r.text]
    assert public == [seal_acts.public_text(c, act)] and "懷璽" not in public[0]
    assert [r.text for r in season.chronicle if "雲篆" in r.text] == public
    me = CharacterStore(w.db).load("懷璽")
    entry = next(e for e in me.journal if e.title == seal.SEAL_TITLE)
    assert "還能再起用 1 次" in " ".join([entry.tag, *entry.lines]) and msgs
    assert any("起用了『雲篆』" in a.text for a in me.player.annals)


@pytest.mark.slow
def test_a_second_use_waits_three_days_and_a_third_is_refused():
    c, w, g = _holder("yunzhuan")
    _use(c, w, now=10.0)
    later = _use(c, w, now=10.0 + DAY)
    assert later and "之後才能再起用" in later[0]
    assert len(_uses(w)) == 1
    _use(c, w, now=10.0 + 3 * DAY + 1)
    assert len(_uses(w)) == 2
    third = _use(c, w, now=10.0 + 7 * DAY)
    assert "都用過了" in third[0] and len(_uses(w)) == 2


@pytest.mark.slow
def test_the_refusals_change_nothing():
    """按不下去：季沒在跑、沒有碎片、碎片沒有行動、在路上（引將、承露）、目標不對、要挑邊沒挑——什麼都不動。"""
    c, w, g = _holder("chishou")
    c.seal["chishou"].act = None  # 第 3 批起七片都有行動：沒有行動的那一條路（測試內容、改版關著還走它）拿掉這一片的行動來測
    assert "沒有能起用的碎片" in _use(c, w)[0]
    c, w, g = _holder("xuanniu")
    assert seal_acts.NO_TARGET in _use(c, w)[0]
    assert seal_acts.BAD_TARGET in _use(c, w, target="nobody")[0]

    def on_road(game):
        game.state.player.journey = game.state.player.journey or _journey(game)
        return game.seal_use("bocai")

    assert seal_acts.ON_ROAD in _do(c, w, "懷璽", on_road)[0]
    c, w, g = _holder("chizhang", side=None)  # 散人傳檄：要挑邊
    assert seal_acts.PICK_SIDE in _use(c, w, target="yingru")[0]
    assert seal_acts.BAD_SIDE in _use(c, w, target="yingru", side="haoqiang")[0]
    for world in (w,):
        assert _uses(world) == [] and world.get_season().seal_acts == []


def _journey(game):
    from tianxia.state import Journey

    return Journey(mode="walk", path=["yingchuan"], arrive_at=[game.state.world.time + 3600])


@pytest.mark.slow
def test_the_season_must_be_running():
    c, w = _world()
    c.config.auto_open_first_season = False
    w2 = open_world(Path(tempfile.mkdtemp(prefix="seal2p-")) / "t.db")
    _give(c, w2, "yunzhuan", "懷璽")
    g = Game.new(c, "懷璽", rng=random.Random(0), world=w2)
    g.sync(0.0)
    assert w2.season_phase() == "preparing"
    assert seal_acts.NOT_RUNNING in g.seal_use()[0]
    assert g.seal_view()["act"]["ok"] is False


@pytest.mark.slow
def test_the_card_carries_the_act_for_the_holder_only():
    """碎片卡（status.seal，只給持有者自己）多一份 act：哪一種、說明、還剩幾次、按不按得下去、能指定的目標、確認的問句。"""
    c, w, g = _holder("xuanniu", at="changshe")
    act = server.main_view(g)["status"]["seal"]["act"]
    assert (act["kind"], act["name"], act["left"], act["ok"], act["why"]) == ("yinjiang", "引將", 2, True, "")
    ids = {t["id"]: t for t in act["targets"]}
    assert ids["huangfusong"]["why"] == seal_acts.HERE  # 皇甫嵩就在長社
    assert ids["qinjie"]["why"] == "" and "秦頡" in ids["qinjie"]["name"]  # 沒有行程的人照舊按得下去
    assert ids["bocai"]["why"] == seal_acts.CLASH_PLAN  # 波才的盤算公告（長社那一件）就在第一天之內：FB-9038，行程要動他
    assert "pengtuo" not in ids  # 還沒出場
    assert "{target}" in act["confirm"] and "長社" in act["confirm"]
    other = _person(c, w, "旁人", side="huang")
    assert server.main_view(other)["status"]["seal"] is None


@pytest.mark.slow
def test_a_shard_without_an_act_shows_none():
    c, w, g = _holder("chishou")
    c.seal["chishou"].act = None  # 第 3 批起七片都有行動（同上）
    assert server.main_view(g)["status"]["seal"]["act"] is None


@pytest.mark.slow
def test_switched_off_the_card_has_no_act_and_the_action_says_no():
    c, w, g = _holder("yunzhuan", on=False)
    assert "act" not in server.main_view(g)["status"]["seal"]
    assert _use(c, w) == ["（此刻無法這麼做。）"]
    assert _uses(w) == [] and w.get_season().seal_acts == []
    assert "uses" not in g.admin_seal_choices()


def test_bots_never_use_an_act():
    """假人不用獨門行動（設計第四章【PM】：不具名，看不出誰沒用；假人亂用會把天下攪亂）：起用不是選單上的一顆（bot.pick 碰不到），
    假人程式與整季機器人也不叫 seal_use。"""
    import inspect

    import run_bots
    from tianxia import bot, bot_policy, bot_runner, server_bots

    for module in (bot, bot_policy, bot_runner, server_bots, run_bots):
        assert "seal_use" not in inspect.getsource(module), module.__name__


def test_the_player_action_is_seal_use_not_an_admin_one():
    """玩家動作跟管理者動作不同名（FB-609）。"""
    assert "seal_use" in server.MAIN_ACTIONS and "seal_use" not in server.ADMIN_ACTIONS
    assert not set(server.MAIN_ACTIONS) & set(server.ADMIN_ACTIONS)


@pytest.mark.slow
def test_the_admin_sees_who_used_what():
    c, w, g = _holder("yunzhuan")
    c.config.admins = ["管理"]
    _use(c, w)
    admin = _person(c, w, "管理")
    [row] = admin.admin_seal_choices()["uses"]
    assert row["who"] == "懷璽" and row["act"] == "頒詔" and row["shard"] == "雲篆"


# ── Task 4：引將 ──

@pytest.mark.slow
def test_yinjiang_pulls_a_figure_to_you_and_sends_him_back_on_time():
    from tianxia import figures, plans

    # 盤算開著（FB-9039：主流程要在行程開著時有人守）：挑一位沒有行程的人（秦頡），行程不會把他帶走；
    # 行程開著時波才一開季就先被帶到長社（盤算公告），沒東西可引，所以不挑他
    c, w, g = _holder("xuanniu", at="changshe")
    assert plans.on(c) and not plans.holds(c, "qinjie")
    origin = figures.state_of(_vehicle(c, w.get_season()), c, "qinjie").location
    assert origin != "changshe"
    _use(c, w, target="qinjie")
    season = w.get_season()
    assert season.figures["qinjie"].location == "changshe"
    [act] = season.seal_acts
    assert (act.target, act.place, act.origin) == ("qinjie", "changshe", origin)
    assert any("秦頡應召移駐長社" in r.text for r in season.rumors)
    assert seal_acts.next_end(season) == pytest.approx(act.until)
    late = _do(c, w, "懷璽", lambda game: game.state.world, now=10.0 + DAY + 5)
    assert figures.state_of(_vehicle(c, late), c, "qinjie").location == origin
    back = w.get_season()
    assert back.seal_acts[0].ended == pytest.approx(act.until)
    assert any(seal_acts.BACK.format(figure="秦頡", place=c.locations[origin].name) == r.text for r in back.rumors)


def _vehicle(c, season):
    from tianxia.world import _season_vehicle

    return _season_vehicle(c, season)


@pytest.mark.slow
def test_yinjiang_releases_early_when_the_timetable_moves_him():
    """時刻表要動他（重挫、到任、退場）時引將提早結束、先回原處（時刻表優先，PM 五之一 1）；被挑戰打到退場也一樣。"""
    from tianxia import figures
    from tianxia.models import FigureChange

    c, w, g = _holder("xuanniu", at="changshe", plans=False)
    _use(c, w, target="bocai")
    season = w.get_season()
    v = _vehicle(c, season)
    figures.apply(v, c, "bocai", FigureChange(fate="重挫", location="yingchuan_wilds"))
    assert season.figures["bocai"].location == "yingchuan_wilds"
    assert season.seal_acts[0].ended == pytest.approx(season.time)
    assert seal_acts.pinned(season, "bocai") is None

    c, w, g = _holder("xuanniu", at="changshe", plans=False)
    _use(c, w, target="bocai")
    season = w.get_season()
    v = _vehicle(c, season)
    figures.defeat(v, c, "bocai", 999)
    assert season.figures["bocai"].status in figures.OUT
    assert season.figures["bocai"].location == "huangjin_camp"  # 先回原處（回來時照原處）
    assert season.seal_acts[0].ended is not None


@pytest.mark.slow
def test_a_figure_staying_put_ends_nothing():
    """聲威大減沒扣到 0（留在原地）：引將照舊。"""
    from tianxia import figures
    from tianxia.models import FigureChange

    c, w, g = _holder("xuanniu", at="changshe", plans=False)
    _use(c, w, target="bocai")
    season = w.get_season()
    figures.apply(_vehicle(c, season), c, "bocai", FigureChange(fate="受挫"))
    assert season.figures["bocai"].location == "changshe" and season.seal_acts[0].ended is None


@pytest.mark.slow
def test_a_pinned_figure_does_not_wander():
    """14 天的季人物會自己走動：被引將釘著的不走、不跟、不趕（亂數照擲，別人的序列不位移）。"""
    from tianxia import figure_life, figures, plans

    # 盤算開著（FB-9039）：有行程的人本來就不亂晃（plans.holds），挑到他就測不到引將，所以只挑沒有行程的人
    c, w, g = _holder("xuanniu", profile=None, at="yingchuan_wilds")
    assert plans.on(c)
    fid = next(f for f, d in c.figures.items() if d.character and not plans.holds(c, d.character) and len(c.characters[d.character].haunts) > 1
               and figures.state_of(_vehicle(c, w.get_season()), c, f).location in c.characters[d.character].haunts
               and figures.state_of(_vehicle(c, w.get_season()), c, f).location != "yingchuan_wilds")
    cid = c.figures[fid].character

    class Zero(random.Random):
        def random(self):
            return 0.0

    def moved(pinned: bool) -> bool:
        season = w.get_season()
        v = _vehicle(c, season)
        before = figures.state_of(v, c, fid).location
        if pinned:
            season.seal_acts.append(SealAct(kind="yinjiang", shard="xuanniu", start=season.time, until=season.time + DAY,
                                            target=fid, place=before, origin=before))
        figure_life._act(v, c, cid, Zero())
        return figures.state_of(v, c, fid).location != before

    assert moved(False) and not moved(True)


@pytest.mark.slow
def test_yinjiang_greys_out_a_figure_the_timetable_will_move_within_the_day():
    """窗口內有還沒結算、會動他的時刻表大事：灰掉寫原因（PM 五之一 1）。"""
    from tianxia import figures, timetable

    c, w, g = _holder("xuanniu", at="changshe")
    season = w.get_season()
    v = _vehicle(c, season)
    pairs = sorted(
        (timetable.when(v, c, e), fid)
        for e in timetable.events(season, c) if e.id not in season.timeline
        for o in e.outcomes.values() for key, change in o.figures.items()
        if (fid := timetable._target(v, c, e, key)) in c.figures and figures.state_of(v, c, fid).status == "active"
        and figures.moves(figures.state_of(v, c, fid), change, c)
    )
    at, fid = pairs[0]
    first = min(t for t, f in pairs if f == fid)
    assert seal_acts.clash(v, c, fid, first + 1)
    assert not seal_acts.clash(v, c, fid, first - 1)
    rows = {t["id"]: t["why"] for t in seal_acts.figure_targets(v, c, first + 1)}
    assert rows[fid] == seal_acts.CLASH


@pytest.mark.slow
@pytest.mark.parametrize(("day", "place", "plans_on", "usable"), [
    (1.2, "nanyang_road", True, False),  # 一日之內行程要把他帶去南陽道上：灰掉，按下去被拒
    (1.9, "nanyang_road", True, True),  # 那一站在窗口外：照舊按得下去
    (1.2, "wan_city", True, True),  # 要去的地方就是他此刻站的地方：不灰
    (1.2, "nanyang_road", False, True),  # 盤算關著：行程不算，跟以前一樣
])
def test_yinjiang_refuses_a_figure_whose_itinerary_moves_him_within_the_day(day, place, plans_on, usable):
    """FB-9038：行程比照時刻表，窗口（一日）內會把人搬離他此刻所在的地方，目標灰掉、起用按下去被拒、不記次數、人不動；
    起用那一下的檢查跟目標清單是同一條（seal_acts.figure_targets）。7 天季第 1.7 天孫堅動身那種情形（QA develop-red7）。"""
    from tianxia import figures
    from tianxia.models import Itinerary, ItineraryStop

    c, w, g = _holder("xuanniu", at="changshe", plans=plans_on)
    c.itineraries = [Itinerary(who="qinjie", stops=[ItineraryStop(id="t_march", day=day, place=place, text="{name}拔營了。")])]
    origin = figures.state_of(_vehicle(c, w.get_season()), c, "qinjie").location
    assert origin == "wan_city"
    shard_id = "xuanniu"
    msgs = _use(c, w, target="qinjie")
    season = w.get_season()
    shard = w.seal_state().registry.shards[shard_id]
    number = w.get_season_number()
    if usable:
        [act] = season.seal_acts
        assert (act.target, act.origin) == ("qinjie", origin) and seal_acts.used(shard, number) == 1
        assert figures.state_of(_vehicle(c, season), c, "qinjie").location == "changshe"
    else:
        assert msgs == [f"（秦頡{seal_acts.CLASH_PLAN}。）"]  # 灰掉的原因就是按下去被拒的那一句
        assert season.seal_acts == [] and _uses(w) == [] and seal_acts.used(shard, number) == 0  # 不扣次數
        assert figures.state_of(_vehicle(c, season), c, "qinjie").location == origin  # 人不動
        view = _do(c, w, "懷璽", lambda game: game.seal_view()["act"])  # 碎片卡的目標清單也灰著
        assert {t["id"]: t["why"] for t in view["targets"]}["qinjie"] == seal_acts.CLASH_PLAN


# ── Task 5：頒詔、承露、收心 ──

@pytest.mark.slow
def test_banzhao_lifts_sensing_and_the_peak_try_for_everyone_for_a_day():
    """頒詔一日：人人靜心感悟 +10 個百分點（夾上限）、衝絕學的機會 ×1.2（企劃者 2026-10-21：武學重構之後修練不再擲升品，後半句改成
    衝絕學；掛在 cultivation.peak_scale，契機與服丹共用）。旁人看的是服丹衝關那一個數（force_odds，修練頁寫的就是擲的）。"""
    from tianxia import cultivation, sensing, team, treasures

    c, w, g = _holder("yunzhuan")
    other = _person(c, w, "旁人", side="guan")
    loc = c.locations[other.state.player.location]

    def look(game):
        return sensing.rate(game.state, c, loc), cultivation.force_odds(game.state, c, game.world, "basic_fist"), cultivation.peak_scale(game.state, c)

    before = look(other)
    assert before[2] == 1.0 and treasures.amount(other.state, c, "cultivate") == 1.0
    _use(c, w)
    now = _do(c, w, "旁人", look)
    low, high = c.config.sense_rate_range
    assert now[0] - before[0] == min(10, high - (before[0] - _marks(other, c, loc)))
    cfg = c.config
    raw = cfg.legend_item_bonus * team.stat_factor(c, other.state.player.stats.get("wis", team.BASE_STAT))
    assert now[2] == pytest.approx(cfg.seal.revamp.acts.cultivate) == pytest.approx(1.2)
    assert now[1] == round(max(1.0, min(cfg.breakthrough.max_chance, raw * 1.2))) and now[1] > before[1]
    after = _do(c, w, "旁人", look, now=10.0 + DAY + 1)
    assert after == before


def test_banzhao_multiplies_the_peak_try_on_both_roads(sealed, state, world):
    """衝絕學的兩條路乘同一個倍數（cultivation.peak_scale，寶物「cultivate」那個位置、在上限之內）：契機（seize，難度比 0.5 是 25%，
    頒詔之下 30%）與服丹（force_odds，15% → 18%）。期滿、改版關著（生效中的那一筆還在季上）都回到 1。"""
    from test_cultivation import Fixed, _worn, kicker_art

    from tianxia import cultivation

    acts_on(sealed)
    world.claim_skill_name(kicker_art())

    def seize(value):
        _worn(state)
        state.player.naming = None
        return cultivation.seize(state, sealed, world, 0.5, Fixed(value))[0]

    state.world.time = 50.0
    _worn(state)
    assert cultivation.force_odds(state, sealed, world, "旋風腿") == 15 and seize(0.2899).startswith("打到緊處")
    state.world.seal_acts = [_act("banzhao")]
    assert cultivation.peak_scale(state, sealed) == pytest.approx(1.2)
    assert cultivation.force_odds(state, sealed, world, "旋風腿") == 18
    assert seize(0.2899).startswith("這一戰") and seize(0.3001).startswith("打到緊處")
    state.world.time = DAY  # 期滿
    assert cultivation.peak_scale(state, sealed) == 1.0 and seize(0.2899).startswith("打到緊處")
    state.world.time = 50.0
    sealed.config.seal.revamp.enabled = False
    assert cultivation.peak_scale(state, sealed) == 1.0 and cultivation.force_odds(state, sealed, world, "旋風腿") == 15


def test_the_peak_scale_is_the_only_caller_of_the_edict():
    """頒詔的後半句只有一個掛點：cultivation.peak_scale（seize、force_odds 都經過它）。"""
    import inspect

    from tianxia import cultivation

    root = Path(__file__).resolve().parents[2] / "tianxia"
    callers = [f.name for f in root.glob("*.py") if f.name != "seal_acts.py" and "edict_cultivate(" in f.read_text(encoding="utf-8")]
    assert callers == ["cultivation.py"]
    assert inspect.getsource(cultivation).count("edict_cultivate(") == 1
    assert "peak_scale(state, content)" in inspect.getsource(cultivation.seize)
    assert "peak_scale(state, content)" in inspect.getsource(cultivation.force_odds)


def _marks(game, c, loc):
    from tianxia import sensing

    return min(c.config.sense_marks_cap, sensing._tier(game.state.world.marks.get(sensing.mark_key(loc.id), 0)) * c.config.sense_marks_bonus)


@pytest.mark.slow
def test_banzhao_respects_the_sensing_cap():
    from tianxia import sensing

    c, w, g = _holder("yunzhuan")
    other = _person(c, w, "旁人", side="guan")
    other.state.player.stats["wis"] = 15
    CharacterStore(w.db).save(other.state)
    loc = c.locations[other.state.player.location]
    _use(c, w)
    rate = _do(c, w, "旁人", lambda game: sensing.rate(game.state, c, loc))
    assert rate == c.config.sense_rate_range[1] + _marks(other, c, loc)


def _elsewhere(c):
    """潁川汝南以外、有醫館的一處（承露降在潁川汝南）。"""
    return next(loc for loc, d in c.locations.items() if seal_acts.region_of(c, loc) not in (None, "yingru") and "醫館" in d.tags)


@pytest.mark.slow
def test_chenglu_speeds_stamina_in_its_region_only():
    """承露：那一區的人（不論是誰）體力回復 ×1.5（照跟時效重疊的秒數）；別區照舊。"""
    c, w, g = _holder("chenglu", at="yingchuan_wilds")
    near = _person(c, w, "近人", side="guan", at="yingchuan")  # 同一區（潁川汝南）
    far = _person(c, w, "遠人", side="guan", at=_elsewhere(c))
    _use(c, w, now=0.0)
    for name in ("近人", "遠人"):
        _do(c, w, name, lambda game: setattr(game.state.player, "stamina", 0.0), now=0.0)
    hour = 3600.0
    got = {name: _do(c, w, name, lambda game: game.state.player.stamina, now=hour) for name in ("近人", "遠人")}
    assert got["近人"] == pytest.approx(got["遠人"] * 1.5)
    # 重疊一半：期滿前半小時起算到期滿後半小時
    act = w.get_season().seal_acts[0]
    start = act.until - hour / 2
    for name in ("近人", "遠人"):
        _do(c, w, name, lambda game: setattr(game.state.player, "stamina", 0.0), now=start)
    got = {name: _do(c, w, name, lambda game: game.state.player.stamina, now=start + hour) for name in ("近人", "遠人")}
    assert got["近人"] == pytest.approx(got["遠人"] * 1.25)


@pytest.mark.slow
def test_chenglu_makes_the_clinic_free_in_its_region():
    from tianxia import skillview, team

    c, w, g = _holder("chenglu", at="yingchuan_wilds")
    patient = _person(c, w, "病人", side="guan", at="yingchuan")  # 潁川郡有醫館
    patient.state.player.member.injury = 20.0
    patient.state.player.stats["silver"] = 100
    CharacterStore(w.db).save(patient.state)
    _use(c, w)

    def heal(game):
        plan = team.heal_plan(game.state, c, game.state.player.member)
        note = skillview.heal_note(game.state, c)
        return plan, note, game.heal(), game.state.player.stats["silver"], game.state.player.member.injury

    plan, note, msgs, silver, injury = _do(c, w, "病人", heal)
    assert plan == (20, 0, 0) and silver == 100 and injury == 0
    assert team.HEAL_FREE_NOTE in note and any(team.HEAL_FREE in m for m in msgs)


@pytest.mark.slow
def test_chenglu_heals_someone_without_a_coin():
    """不收錢就不看銀兩：一兩都沒有也治得了（平常是「銀兩不足」）。"""
    from tianxia import team

    c, w, g = _holder("chenglu", at="yingchuan_wilds")
    patient = _person(c, w, "窮人", side="guan", at="yingchuan")
    patient.state.player.member.injury = 12.0
    patient.state.player.stats["silver"] = 0
    CharacterStore(w.db).save(patient.state)
    assert team.heal_problem(patient.state, c, patient.state.player.member) is not None
    _use(c, w)
    injury = _do(c, w, "窮人", lambda game: (game.heal(), game.state.player.member.injury)[1])
    assert injury == 0


@pytest.mark.slow
def test_chenglu_does_not_free_the_clinic_elsewhere():
    from tianxia import team

    c, w, g = _holder("chenglu", at="yingchuan_wilds")
    patient = _person(c, w, "病人", side="guan", at=_elsewhere(c))
    patient.state.player.member.injury = 20.0
    patient.state.player.stats["silver"] = 100
    CharacterStore(w.db).save(patient.state)
    _use(c, w)
    plan = _do(c, w, "病人", lambda game: team.heal_plan(game.state, c, game.state.player.member))
    assert plan[1] > 0


@pytest.mark.slow
def test_shouxin_doubles_talk_and_toast_warmth_and_opens_the_door():
    from tianxia import companion_agent, feasts, rules
    from tianxia.companion_agent import CompanionTurn
    from tianxia.state import Feast

    c, w, g = _holder("guixin")
    fan = _person(c, w, "仰慕者", side="guan")
    cid = "caocao"
    fan.state.player.stats["fame"] = 0
    assert not rules.can_meet(fan.state, c, cid)
    tag = next(t for t, d in companion_agent.AFFINITY_TAG_DELTAS.items() if d >= 2)
    plain = _warmth(fan, c, cid, tag)
    _use(c, w, target=cid)

    def check(game):
        game.state.player.stats["fame"] = 0
        return rules.can_meet(game.state, c, cid), _warmth(game, c, cid, tag), _toast(game, c, cid)

    opened, warm, toast = _do(c, w, "仰慕者", check)
    assert opened and warm == plain * 2
    base_toast = feasts.affinity_of(c, 60)
    assert toast == min(100, base_toast * 2)
    later = _do(c, w, "仰慕者", lambda game: (rules.can_meet(game.state, c, cid), _warmth(game, c, cid, tag)), now=10.0 + DAY + 1)
    assert later == (False, plain)


def _warmth(game, c, cid, tag):
    from tianxia import companion_agent
    from tianxia.companion_agent import CompanionTurn

    state = game.state.model_copy(deep=True)
    state.player.affinities[cid] = 0
    companion_agent._apply_turn(state, c.characters[cid], cid, "說話", CompanionTurn(narrative="嗯。"), tag, content=c)
    return state.player.affinities[cid]


def _toast(game, c, cid):
    from tianxia import feasts
    from tianxia.state import Feast

    state = game.state.model_copy(deep=True)
    state.player.affinities[cid] = 0
    f = Feast(id=1, host=cid, place=state.player.location, start=state.world.time, end=state.world.time + 3600)
    feasts.toast(state, c, f, "敬一杯", 60, True)
    return state.player.affinities[cid]


@pytest.mark.slow
def test_shouxin_targets_greys_out_a_figure_off_the_board():
    c, w, g = _holder("guixin")
    act = server.main_view(g)["status"]["seal"]["act"]
    rows = {t["id"]: t for t in act["targets"]}
    assert rows["caocao"]["why"] == "" and "pengtuo" not in rows
    assert all(c.characters[t].deep_interaction for t in rows)


# ── Task 6：傳檄 ──

@pytest.mark.slow
def test_chuanxi_lifts_its_army_on_its_line_only():
    """傳檄：那一軍的人在那條線上往自家目標推的量 ×1.25（每人每日上限照舊）；別的線、別的軍、反方向不加；期滿照舊。"""
    c, w, g = _holder("chizhang", side="huang")
    _use(c, w, target="yingru")
    season = w.get_season()
    [act] = season.seal_acts
    assert (act.target, act.side) == ("yingru", "huang")
    assert seal_acts.writ_factor(season, c, "yingru", "huang", 1) == pytest.approx(1.25)
    assert seal_acts.writ_factor(season, c, "yingru", "huang", -1) == 1.0  # 反方向
    assert seal_acts.writ_factor(season, c, "nanyang", "huang", 1) == 1.0  # 別的線
    assert seal_acts.writ_factor(season, c, "yingru", "guan", -1) == 1.0  # 別的軍
    assert seal_acts.writ_factor(season, c, "yingru", None, 1) == 1.0  # 散人推不吃
    season.time = act.until
    assert seal_acts.writ_factor(season, c, "yingru", "huang", 1) == 1.0


def _pushed(line: str, amount: float, *, on: bool, profile="season21", cap: float | None = None, monkeypatch=None):
    """黃巾的一個人往 line 推 amount（source="event_once"：不打季長的折）；on 時先有一位黃巾的懷璽者對 line 傳檄。
    回（線上動了多少〔含零頭〕, 這個人今天在這條線上記了多少）。cap 給了就把每人每日上限換成它。"""
    c, w, g = _holder("chizhang", side="huang", profile=profile)
    if on:
        _use(c, w, target=line)
    _person(c, w, "黃巾兵", side="huang", at="yingchuan_wilds")
    if cap is not None:
        monkeypatch.setattr(Game, "daily_push_cap", lambda self: cap)

    def push(game):
        w0 = game.state.world
        before = w0.trend_accum.get(line, 0.0) + w0.trends.get(line, 0)
        game.push_trend(line, amount, source="event_once")
        used = sum(v for k, v in game.state.player.pushed.items() if k.endswith(f":{line}"))
        return w0.trend_accum.get(line, 0.0) + w0.trends.get(line, 0) - before, used

    return _do(c, w, "黃巾兵", push)


@pytest.mark.slow
def test_chuanxi_scales_what_push_trend_moves_before_the_daily_cap():
    plain, writ = _pushed("yingru", 2, on=False), _pushed("yingru", 2, on=True)
    assert writ[0] == pytest.approx(plain[0] * 1.25) and writ[1] == pytest.approx(plain[1] * 1.25)


@pytest.mark.slow
def test_chuanxi_does_not_lift_the_daily_cap(monkeypatch):
    """每人每日上限照舊擋（設計：照盡頭阻力與每日上限照舊）：推到頂的那一下，有沒有傳檄記的都一樣。"""
    plain = _pushed("yingru", 6, on=False, cap=1.0, monkeypatch=monkeypatch)
    writ = _pushed("yingru", 6, on=True, cap=1.0, monkeypatch=monkeypatch)
    assert writ[1] == pytest.approx(1.0) == pytest.approx(plain[1])


@pytest.mark.slow
def test_chuanxi_in_a_season_without_the_first_season_rules():
    """規則關著的季（14 天）三條戰線合成黃巾聲勢：能指定的只有那一條，推的量照樣 ×1.25（零頭記在 trend_accum）。"""
    c, w, g = _holder("chizhang", side="huang", profile=None)
    act = server.main_view(g)["status"]["seal"]["act"]
    assert [t["id"] for t in act["targets"]] == ["huangjin"]
    plain, writ = _pushed("huangjin", 2, on=False, profile=None), _pushed("huangjin", 2, on=True, profile=None)
    assert plain[0] == pytest.approx(2) and writ[0] == pytest.approx(2.5)


@pytest.mark.slow
def test_a_ranger_picks_a_side_for_chuanxi():
    """散人起用要看陣營的那幾片：每次挑一軍當這一次的自家（企劃者）；挑的那一軍才加。"""
    c, w, g = _holder("chizhang", side=None)
    act = server.main_view(g)["status"]["seal"]["act"]
    assert [s["id"] for s in act["sides"]] == ["guan", "huang"]
    _use(c, w, target="yingru", side="guan")
    season = w.get_season()
    assert season.seal_acts[0].side == "guan"
    assert seal_acts.writ_factor(season, c, "yingru", "guan", -1) == pytest.approx(1.25)
    assert seal_acts.writ_factor(season, c, "yingru", "huang", 1) == 1.0


@pytest.mark.slow
def test_a_faction_member_does_not_pick():
    c, w, g = _holder("chizhang", side="guan")
    act = server.main_view(g)["status"]["seal"]["act"]
    assert act["sides"] == [] and "官軍" in act["confirm"]
    _use(c, w, target="yingru", side="huang")  # 送來的 side 不理：照自家
    assert w.get_season().seal_acts[0].side == "guan"


@pytest.mark.slow
def test_chuanxi_lifts_block_progress_in_a_conquest_season():
    """合進 feature/territory-conquest 時改了前提（斷言不動）：翻地與爭搶（dev/flip-1）拿掉了公告攻城（announce 排進時程表＝那一塊被戰書
    凍結、推不動）與拔河的 progress_of；換成新機制——黃巾在開季中立的南陽官道直接出陣攻，讀黃巾那一條翻地進度（conquest.bar）。
    傳檄的掛點 Game._push_progress 照舊在（推的換成翻地的進度）。"""
    from conquest_kit import conquest_game, go, join, win_sortie
    from tianxia import conquest

    def progress(on: bool) -> float:
        game = go(join(conquest_game("season21", name="黃巾兵"), "huang"), "nanyang_road")
        assert conquest.push_problem(game.state.world, game.content, "huang", "nanyang_road", "attack") is None
        if on:
            line = conquest.line_of(game.state.world, game.content, "nanyang_road")
            game.state.world.seal_acts.append(SealAct(kind="chuanxi", shard="chizhang", start=game.state.world.time,
                                                      until=game.state.world.time + DAY, target=line, side="huang"))
        game.content.config.seal.revamp.enabled = True
        win_sortie(game)
        return conquest.bar(game.state.world, "nanyang_road", "huang")

    off = progress(False)
    assert off > 0
    assert progress(True) == pytest.approx(off * 1.25)


# ── FB-643（2026-10-31 從 tests/seal/test_seal_fb643_tavern.py 併進來）────────
# FB-643：起用碎片的那一筆行狀（份量 4）被酒肆讀到——打聽交情列出「近來的事：起用了『X』…」、近況（tavern.fresh）讓查人在哪與
# 買兇找人變準、行狀份量 4 的三件以上算名氣（person_fame），起用的人被認出來；七片同一條路（第 2 批就有）。PM 定：碎片起用的行狀不給酒肆與
# 買兇找人讀（annals.SEAL 這一類，tavern.ties_player_lines、fresh、person_fame、hit_reach 一律跳過），行狀本身留著（傳、本人的行狀頁照舊）。
#
# 守門照「兩個只差誰起用的世界」：甲客或乙客懷著那一片（同一陣營、同一處、同樣的目標），旁觀客跟他們同陣營、站在同一間酒肆（地頭熟），
# 兩人名望都到第一段（打聽度 4 以上才列近來的事）、份量 4 的舊事各兩件而且都在兩天前（再一件就多一點名氣、近況只看這一件）。
# 旁觀客在酒肆打聽交情、查人在哪，加上名氣、近況、打聽度、買兇找人的打聽度與酒肆那一頁，兩個世界要一字不差。正式內容（21 天季＋領地爭奪打開）。


AT = "runan"  # 汝南：黃巾的、有酒肆
VIEWER = "旁觀客"
TARGETS = {  # 片 → 指定的目標（甲客、乙客是黃巾、站在汝南）
    "xuanniu": "bocai",  # 引將
    "yunzhuan": "",  # 頒詔
    "chenglu": "",  # 承露：潁川汝南
    "chizhang": "yingru",  # 傳檄
    "guixin": "caocao",  # 收心
    "chishou": "runan",  # 鎮地
    "jinjiao": "runan_academy",  # 補缺：官軍先翻走汝南書院
}
OLD = -2 * DAY  # 舊事的時刻：兩天前，近況（24 小時）不算它


def _person_fb643(c, w, name, side, *, known=False):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, AT, len(c.tutorial.steps)
    p.visited.add(AT)
    p.stats["silver"] = 5000
    if known:
        p.stats["fame"] = renown.fame_bars(c, g.state.world)[0]  # 名望第一段：打聽度 4 以上，打聽交情列得出近來的事
    g.sync(0.0)
    if known:
        for a in p.annals:  # 開局記下的（投靠）挪到兩天前
            a.time = OLD
        while sum(1 for a in p.annals if a.weight >= 4) < 2:
            annals.note(g.state, c, annals.DEED, f"舊事{len(p.annals)}。", 4, time=OLD)
        assert renown.fame_tier(g.state, c) == 1
    g._save_season()
    CharacterStore(w.db).save(g.state)
    return g


def _do_fb643(c, w, name, fn, now):
    game = Game(c, CharacterStore(w.db).load(name), random.Random(0), w)
    game.client = None
    game.sync(now)
    out = fn(game)
    game._save_season()
    CharacterStore(w.db).save(game.state)
    return out


def _world_fb643(shard: str, user: str, side: str | None):
    """甲客、乙客（side；None 是散人）與旁觀客（黃巾）都在汝南；user 懷著 shard、在 10 秒起用（散人替黃巾）。回旁觀客在酒肆問到的一切。"""
    c = conquest_rules(real_content("season21"))
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = True
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0
    w = open_world(Path(tempfile.mkdtemp(prefix="seal643-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards[shard]
        s.state, s.holder, s.since_season = "held", user, 0

    w.mutate(_give)
    for name in ("甲客", "乙客"):
        _person_fb643(c, w, name, side, known=True)
    _person_fb643(c, w, VIEWER, "huang")
    if shard == "jinjiao":
        _do_fb643(c, w, VIEWER, lambda g: conquest.push(g.state.world, c, "runan_academy", "guan", "官甲", 100, "attack"), now=5.0)
    for name in ("甲客", "乙客"):
        _do_fb643(c, w, name, (lambda g: g.seal_use(TARGETS[shard], "huang")) if name == user else (lambda g: None), now=10.0)
    assert [e.holder for e in w.seal_state().registry.uses] == [user]  # 真的起用了
    store = CharacterStore(w.db)

    def look(viewer: Game) -> dict:
        assert viewer._tavern_enter() and viewer._tavern_open()
        now = viewer.state.world.time
        out = {}
        for name in ("甲客", "乙客"):
            other = store.load(name)
            other.world = viewer.state.world
            out[f"ties:{name}"] = viewer.tavern_do("ties", name)
            out[f"seek:{name}"] = viewer.tavern_do("seek", name)
            out[f"fame:{name}"] = tavern.person_fame(other, c)
            out[f"fresh:{name}"] = tavern.fresh(other, now)
            out[f"reach:{name}"] = tavern.person_reach(viewer.state, c, other, set())
            out[f"hit:{name}"] = tavern.hit_reach(c, AT, other)
        out["page"] = json.dumps(viewer.tavern_view(), ensure_ascii=False, sort_keys=True, default=str)
        return out

    return _do_fb643(c, w, VIEWER, look, now=20.0)


CASES = [(shard, "huang") for shard in TARGETS] + [("chizhang", None), ("chishou", None)]


@pytest.mark.slow  # 原本整個檔標 slow（建 Game、載正式內容）
@pytest.mark.parametrize(("shard", "side"), CASES, ids=[f"{s}-{side or 'ranger'}" for s, side in CASES])
def test_the_tavern_cannot_tell_who_used_a_shard(shard, side):
    a, b = _world_fb643(shard, "甲客", side), _world_fb643(shard, "乙客", side)
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == b[key], key
    if side is not None:  # 打聽度到 4：近來的事真的列得出來（列得出舊事，就列得出起用那一筆）
        assert any("近來的事" in line for line in a["ties:甲客"])


@pytest.mark.slow  # 原本整個檔標 slow（建 Game、載正式內容）
def test_the_seal_annal_stays_for_its_owner():
    """行狀本身留著：本人的行狀頁照舊寫「行事」、季末的傳照舊歸在出身與行事那一段（跟改之前一樣）。"""
    c = conquest_rules(real_content("season21"))
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = True
    w = open_world(Path(tempfile.mkdtemp(prefix="seal643o-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards["yunzhuan"]
        s.state, s.holder, s.since_season = "held", "懷璽", 0

    w.mutate(_give)
    _person_fb643(c, w, "懷璽", "huang")
    _do_fb643(c, w, "懷璽", lambda g: g.seal_use(""), now=10.0)
    me = CharacterStore(w.db).load("懷璽")
    [entry] = [a for a in me.player.annals if a.text.startswith("起用了『雲篆』")]
    assert (entry.kind, entry.weight) == (annals.SEAL, 4) and not annals.heard(entry)
    [row] = [r for r in annals.rows(me, c) if r["text"] == entry.text]
    assert row["kind"] == annals.KINDS[annals.DEED]
    req = biography.BiographyRequest(season=1, name="懷璽", scenario="黃巾之亂", era_note="", annals=(entry.model_dump(),))
    assert entry.text in biography.outline(req).split("【出身與行事】")[1].split("【大戰】")[0]
    assert biography._strip(entry.text, "懷璽") in biography.rule_text(req)
