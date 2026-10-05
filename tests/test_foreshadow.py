"""關鍵伏筆的引擎（計畫 T7a、伏筆文件第二節、濃縮版內容表第四節）：片段、對話的片段選項、最後一步、暗中鎖定、
豪強第三方、天機、官銀、開關。

用 tests/fixtures/content 加上 conftest.install_foreshadows（第一季開關、三個陣營、fixture 的六條鏈）。
真實的 11 條鏈是 T7b 的事，這裡不碰。fixture 的人數上限是預設的 30，係數 0.3：葦束 3 → 1、膏油 2 → 1、
皇甫嵩的情誼 20 → 6、波才 30 → 9、官銀 5 → 2、糧草 4 → 2；片段的機率是 0.05 ÷ 0.3。"""
import random

import pytest

import server
from conftest import CHANGSHE_LOCKED, CHANGSHE_LOSER, FixedRandom, install_foreshadows
from tianxia import bot, bot_policy, calendar, companion_agent, foreshadow, rules, skillview, team, timetable
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game, Option
from tianxia.models import Condition, Effect, Foreshadows
from tianxia.state import BotProfile, FigureState, GameState, Lock, TimelineResult

DAY = 86400


@pytest.fixture
def fs(content):
    return install_foreshadows(content)


def cal(content, week: int, weekday: int = 0, hour: int = 0, minute: int = 0) -> float:
    """季曆第 week 週、週 weekday（0＝週一）的 hour:minute 是第幾個世界秒。"""
    return calendar.week_start(week, content) + ((weekday * 24 + hour) * 60 + minute) * 60 / calendar.cal_scale(content)


def night_in_window(content) -> float:
    """長社火攻排在第 6 週週四 20:00：前 7 曆日內、夜裡的一刻（第 5 週週五 00:30）。"""
    return cal(content, 5, 4, 0, 30)


def player(content, world, name: str, faction: str | None, at: str, *, rng=None, time: float | None = None) -> Game:
    game = Game.new(content, name, rng=rng or random.Random(0), world=world)
    p = game.state.player
    p.faction, p.location = faction, at
    p.visited.add(at)
    if time is not None:
        game.state.world.time = time
    return game


def refresh(game: Game) -> None:
    """換成資料庫裡最新的共用賽季（伺服器每次進鎖都這樣做，見 server._locked）。"""
    game.state.world = game.world.get_season()


def ids(game: Game) -> list[str]:
    return [o.id for o in game.options()]


def option(game: Game, option_id: str) -> Option | None:
    return next((o for o in game.options() if o.id == option_id), None)


def wind(world) -> str:
    return foreshadow.tianji_answer(world.read().tianji, "wind")


def finish_fire_guan(game: Game, answer: str) -> list[str]:
    """官軍的長社鏈：按「束苣乘城」看題，再答。回傳答完那一下的訊息。"""
    assert game.choose("fs:fs_fire_guan") == ["軍司馬問：「火從哪一面放？」"]
    return game.choose(f"fs:fs_fire_guan:{answer}")


# ── 換算 ─────────────────────────────────────────────────


def test_scale_and_need(fs):
    fs.config.server_max_players = 2
    assert foreshadow.scale(fs) == pytest.approx(0.2)
    assert [foreshadow.need(fs, n) for n in (24, 30, 3, 20, 1, 0)] == [5, 6, 1, 4, 1, 0]  # 無條件進位、最少 1；0 是不要
    assert foreshadow.fragment_chance(fs) == pytest.approx(0.25)
    for players, factor in ((9, 0.2), (10, 0.3), (99, 0.3), (100, 0.6), (999, 0.6), (1000, 1.0), (5000, 1.0)):
        fs.config.server_max_players = players
        assert foreshadow.scale(fs) == pytest.approx(factor)
    assert foreshadow.need(fs, 24) == 24
    assert foreshadow.fragment_chance(fs) == pytest.approx(0.05)


# ── 片段 ─────────────────────────────────────────────────


def test_fragments_only_for_capable_faction(fs, world):
    """官軍聽得到長社官軍鏈；黃巾只聽得到自己那條、散人什麼都聽不到；只抽所在的大區。"""
    rng = FixedRandom(0.0)
    guan = player(fs, world, "甲", "guan", "lake")
    assert foreshadow.hear_after_action(guan.state, fs, "north", rng, world) == [
        "你聽到一件事：黃巾的營帳全搭在荒草坡上，風一吹，草浪一直漫到營門口。"
    ]
    assert guan.state.player.fragments == {"fs_fire_guan": [0]}
    huang = player(fs, world, "乙", "huang", "lake")
    assert foreshadow.hear_after_action(huang.state, fs, "north", rng, world) == [
        "你聽到一件事：汝南的油坊這幾天被官軍包了，膏油一車一車往長社送。"
    ]
    assert foreshadow.hear_after_action(huang.state, fs, "north", rng, world) == []  # 黃巾在北區只有這一則
    assert huang.state.player.fragments == {"fs_fire_huang": [0]}
    loner = player(fs, world, "丙", None, "lake")
    assert foreshadow.hear_after_action(loner.state, fs, "north", rng, world) == []
    assert loner.state.player.fragments == {}
    haoqiang = player(fs, world, "丁", "haoqiang", "lake")
    assert foreshadow.hear_after_action(haoqiang.state, fs, "north", rng, world) == ["你聽到一件事：長社城裡的官軍已經在殺馬吃了。"]
    other_region = player(fs, world, "戊", "guan", "port")
    heard = foreshadow.hear_after_action(other_region.state, fs, "south", rng, world)
    assert len(heard) == 1 and "營帳" not in heard[0]  # 南區只有南區的片段
    assert set(other_region.state.player.fragments) <= {"fs_fire_guan", "fs_jail_guan"}


def test_fragment_chance_is_rolled_and_can_miss(fs, world):
    guan = player(fs, world, "甲", "guan", "lake")
    chance = foreshadow.fragment_chance(fs)
    assert foreshadow.hear_after_action(guan.state, fs, "north", FixedRandom(chance + 0.001), world) == []
    assert guan.state.player.fragments == {}
    assert foreshadow.hear_after_action(guan.state, fs, "north", FixedRandom(chance - 0.001), world) != []


def test_fragment_never_repeats_and_writes_journal_not_rumor(fs, world):
    """渡口（南區）探索：官軍在南區有兩則行動片段，兩次各聽一則、不重複，第三次什麼都沒有；寫進江湖紀錄、不發傳聞。"""
    game = player(fs, world, "甲", "guan", "port", rng=FixedRandom(0.0))
    rumors = list(world.get_season().rumors)
    heard: list[str] = []
    for _ in range(3):
        game.choose("act:explore")
        heard += [line for line in game.state.journal[0].lines if line.startswith("你聽到一件事：")]
    assert len(heard) == 2 and len(set(heard)) == 2
    assert f"你聽到一件事：靈台的太史說，今年夜裡的風從{wind(world)}來。" in heard
    assert game.state.player.fragments == {"fs_fire_guan": [3], "fs_jail_guan": [0]}
    assert world.get_season().rumors == rumors
    assert all("聽到一件事" not in r.text for r in world.get_season().rumors)


def test_fragment_rolls_exactly_once_after_every_stamina_spending_action(fs, world, monkeypatch):
    """每一個花體力的行動之後抽「剛好一次」：探索、遊歷、交友、求見、對話、招募、選單的趕路、折返、輿圖的安排前往；
    不花體力的（打坐、起身、步行、遞名帖、收回名帖、對話的片段選項）一次都不抽。用 spy 數呼叫次數，不靠抽中與否。"""
    monkeypatch.setattr(team, "fight", lambda *a, **k: EncounterResult(tier="大勝", margin=50, our_power=60, difficulty=1))
    monkeypatch.setattr(companion_agent, "start_dialogue", lambda *a, **k: ["你們寒暄了幾句。"])
    monkeypatch.setattr(companion_agent, "continue_dialogue", lambda *a, **k: ["他點點頭。"])
    real = foreshadow.hear_after_action
    calls: list[str | None] = []

    def spy(state, content, region, rng, world=None):
        calls.append(region)
        return real(state, content, region, rng, world)

    monkeypatch.setattr(foreshadow, "hear_after_action", spy)
    fs.characters["zhujun"].talk_at = "lake"  # 湖邊有兩位人物：交友不直接找人、改按求見
    game = player(fs, world, "甲", "guan", "lake", rng=FixedRandom(0.99))
    p = game.state.player

    def calls_after(action) -> int:
        p.stamina = 150.0
        calls.clear()
        action()
        return len(calls)

    assert calls_after(lambda: game.choose("act:explore")) == 1
    game.state.pending_event = None
    assert calls_after(lambda: game.choose("act:train")) == 1
    assert calls_after(lambda: game.choose("act:call")) == 0  # 遞名帖不花體力
    assert calls_after(lambda: game.choose("call:back")) == 0
    game.choose("act:call")
    assert calls_after(lambda: game.choose("call:huangfusong")) == 1  # 求見
    _talking(game, "huangfusong", 6)
    assert calls_after(lambda: game.choose("talk:clue:fs_fire_guan:2")) == 0  # 片段選項不花體力
    assert calls_after(lambda: game.choose("talk:0")) == 1  # 對話一輪
    game.choose("talk:leave")
    assert calls_after(lambda: game.choose("act:rest")) == 0
    assert calls_after(lambda: game.choose("act:stand")) == 0
    game.set_move_mode("walk")
    assert calls_after(lambda: walk_to_town(game)) == 0  # 步行不花體力
    assert calls_after(lambda: game.choose("act:socialize")) == 1  # 小鎮只有波才一位：交友直接找他
    assert calls_after(lambda: game.choose("act:recruit")) == 1
    game.set_move_mode("hurry")
    assert calls_after(lambda: game.choose("move:lake:hurry")) == 1  # 選單的趕路
    game.advance(60)  # 走了一段（趕路 3 分鐘的路要 90 秒）
    assert calls_after(lambda: game.choose("road:back:hurry")) == 1  # 折返也是趕路
    game.advance(600)
    assert p.journey is None and p.location == "town"
    assert calls_after(lambda: game.travel("lake", "hurry")) == 1  # 輿圖的安排前往
    assert calls == ["north"]  # 抽的是出發那一站的大區


def walk_to_town(game: Game) -> None:
    game.choose("move:town")
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)


def test_event_fragment_goes_to_each_faction_its_own(fs, world):
    """同一則老船夫的事件：官軍聽到官軍鏈那一則、黃巾聽到黃巾那一則、散人什麼都沒有；只說一次。"""
    direction = wind(world)
    guan = player(fs, world, "甲", "guan", "lake")
    huang = player(fs, world, "乙", "huang", "lake")
    loner = player(fs, world, "丙", None, "lake")
    assert foreshadow.hear_from_event(guan.state, fs, "fs_ev_boatman", world) == [
        f"你聽到一件事：「這時節的大風，都是半夜從{direction}邊刮過來的。」"
    ]
    assert foreshadow.hear_from_event(huang.state, fs, "fs_ev_boatman", world) == [
        f"你聽到一件事：「前兩天官軍把我叫去，問的全是颳風的事。夜裡的風都從{direction}邊來。」"
    ]
    assert foreshadow.hear_from_event(loner.state, fs, "fs_ev_boatman", world) == []
    assert foreshadow.hear_from_event(guan.state, fs, "fs_ev_boatman", world) == []  # 聽過了
    assert guan.state.player.fragments == {"fs_fire_guan": [1]} and huang.state.player.fragments == {"fs_fire_huang": [1]}
    assert foreshadow.hear_from_event(guan.state, fs, "drunk", world) == []


def test_event_fragment_is_appended_when_the_event_is_presented(fs, world):
    fs.events = {eid: e for eid, e in fs.events.items() if eid in ("fs_ev_boatman",)}  # 湖邊探索只剩老船夫
    fs.config.rare_explore_chance = 0.0
    fs.config.explore_mix[-1].weights = {"event": 1}
    game = player(fs, world, "甲", "guan", "lake", rng=FixedRandom(0.99))  # 0.99：行動後的片段抽不中
    game.choose("act:explore")
    assert game.state.pending_event == "fs_ev_boatman"
    assert f"你聽到一件事：「這時節的大風，都是半夜從{wind(world)}邊刮過來的。」" in game.state.journal[0].lines


def test_fragment_versions_follow_the_event_version(fs, world):
    """宛城有甲、乙兩版：第 3 週那件還沒定時用史書那一版（第一個，甲），定成乙之後用乙的文字。"""
    game = player(fs, world, "甲", "haoqiang", "port", rng=FixedRandom(0.0))
    assert "你聽到一件事：新野的縣令早就跑了。" in foreshadow.hear_after_action(game.state, fs, "south", FixedRandom(0.0), world)
    game.state.player.fragments = {}
    game.state.world.timeline["zhangmancheng"] = TimelineResult(key="不成", time=0.0)
    assert foreshadow.hear_after_action(game.state, fs, "south", FixedRandom(0.0), world) == [
        "你聽到一件事：新野的縣令早就跑了，縣衙裡只剩幾個老吏。"
    ]


# ── 對話的片段選項 ───────────────────────────────────────


def _talking(game: Game, companion_id: str, affinity: int) -> None:
    p = game.state.player
    p.pending_companion = companion_id
    p.last_offered_dialogue[companion_id] = [["問好", "說說近況"], ["warm", "neutral"]]
    p.affinities[companion_id] = affinity


def test_talk_clue_option_fixed_text_once(fs, world):
    """情誼夠（20 → 6）就在 talk:N 後面多一個固定選項；按了回固定文字，不經模型、不扣體力、不算對話輪數，只說一次。"""
    game = player(fs, world, "甲", "guan", "lake")
    p = game.state.player
    _talking(game, "huangfusong", 5)
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]
    p.affinities["huangfusong"] = 6
    opts = game.options()
    assert [o.id for o in opts] == ["talk:0", "talk:1", "talk:clue:fs_fire_guan:2", "talk:leave"]
    assert opts[2].label == "問起破敵之策" and opts[2].enabled
    assert game.dialogue_request("talk:clue:fs_fire_guan:2") is None  # 不送模型
    stamina = p.stamina
    msgs = game.choose("talk:clue:fs_fire_guan:2")
    assert msgs == ["皇甫嵩說：「賊依草結營，若有引火之物，一夜可破。」"]
    assert p.stamina == stamina and p.talks_today == {} and p.pending_companion == "huangfusong"
    assert p.fragments == {"fs_fire_guan": [2]}
    assert game.state.journal[0].lines == msgs
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]  # 只說一次
    assert game.choose("talk:clue:fs_fire_guan:2") == ["（此刻無法這麼做。）"]


def test_talk_clue_goes_to_the_stand_in_when_the_figure_is_out(fs, world):
    """皇甫嵩退場（或重創、下獄）後，這一則改由朱儁說；皇甫嵩本人不再給。黃巾、散人跟誰聊都沒有。"""
    game = player(fs, world, "甲", "guan", "port")
    _talking(game, "zhujun", 6)
    assert "talk:clue:fs_fire_guan:2" not in ids(game)  # 皇甫嵩還在：朱儁不說這個
    for status in ("retired", "crippled", "jailed"):
        game.state.world.figures["huangfusong"] = FigureState(status=status)
        assert "talk:clue:fs_fire_guan:2" in ids(game)
    assert game.choose("talk:clue:fs_fire_guan:2") == ["朱儁說：「賊依草結營，若有引火之物，一夜可破。」"]
    other = player(fs, world, "乙", "guan", "lake")
    other.state.world.figures["huangfusong"] = FigureState(status="retired")
    _talking(other, "huangfusong", 50)
    assert "talk:clue:fs_fire_guan:2" not in ids(other)
    huang = player(fs, world, "丙", "huang", "lake")
    _talking(huang, "huangfusong", 50)
    assert ids(huang) == ["talk:0", "talk:1", "talk:leave"]


def only_unheard(fs, game: Game, *keep: tuple[str, int]) -> None:
    """所有鏈的所有片段都記成聽過，只留 keep 的那幾片：行動抽片段時只剩這幾片可抽。"""
    game.state.player.fragments = {
        ch.id: [i for i in range(len(ch.fragments)) if (ch.id, i) not in keep] for ch in fs.foreshadows.chains
    }


OVERHEARD_TALK = "你聽到一件事：聽說皇甫嵩說過：「賊依草結營，若有引火之物，一夜可破。」"


def test_can_meet_is_one_predicate_for_the_engine_and_the_overhearing(fs, world):
    """見得到一位大勢人物只有一個判斷（rules.can_meet：名望到他的 audience_fame，或有他的「結識」旗標）：引擎的交友對話
    與伏筆的偷聽都看它——見得到的人行動不偷聽、見不到的才偷聽；名望的邊界與結識旗標，兩邊一起動。"""
    fs.characters["huangfusong"].audience_fame = 30
    game = player(fs, world, "甲", "guan", "lake")
    p = game.state.player
    for fame, flags, meet in (
        (0, [], False), (29, [], False), (30, [], True), (99, [], True),
        (0, ["結識:huangfusong"], True), (0, ["結識:zhujun"], False),
    ):
        p.stats["fame"], p.flags = fame, set(flags)
        only_unheard(fs, game, ("fs_fire_guan", 2))
        assert rules.can_meet(game.state, fs, "huangfusong") is meet
        assert game.socialize_starts_dialogue() is meet  # 引擎：見得到才會開口對話
        heard = foreshadow.hear_after_action(game.state, fs, "north", FixedRandom(0.0), world)
        assert heard == ([] if meet else [OVERHEARD_TALK]), (fame, flags)
        assert (2 in p.fragments["fs_fire_guan"]) is (not meet)  # 偷聽到才記成聽過


def test_overhearing_rides_on_the_same_gates_as_every_other_fragment(fs, world):
    """偷聽只是把對話片段多放進行動的來源：還是只有做得了這條鏈的人聽得到（散人、別的陣營沒有）、情誼不設限（見不到的人本來就
    沒有情誼）、文字照填天機的插槽、機率照舊、沒人出面（退場又沒有接手的）就沒有得聽、開關關著什麼都不做。"""
    chain = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_guan")
    fs.characters["huangfusong"].audience_fame = 30
    chain.fragments[2].text = "「風從{風向}邊來，賊依草結營。」"
    said = f"你聽到一件事：聽說皇甫嵩說過：「風從{wind(world)}邊來，賊依草結營。」"
    for faction in ("huang", "haoqiang", None):
        other = player(fs, world, f"外{faction}", faction, "lake")
        other.state.player.fragments = {c.id: list(range(len(c.fragments))) for c in fs.foreshadows.chains if c is not chain}
        assert foreshadow.hear_after_action(other.state, fs, "north", FixedRandom(0.0), world) == [], faction
    game = player(fs, world, "甲", "guan", "lake")
    only_unheard(fs, game, ("fs_fire_guan", 2))
    assert game.state.player.affinities.get("huangfusong", 0) == 0  # 情誼門檻（6）不擋偷聽
    assert foreshadow.hear_after_action(game.state, fs, "north", FixedRandom(foreshadow.fragment_chance(fs) + 0.001), world) == []
    assert foreshadow.hear_after_action(game.state, fs, "north", FixedRandom(0.0), world) == [said]
    nobody = player(fs, world, "乙", "guan", "lake")
    chain.fragments[2].stand_in = None
    nobody.state.world.figures["huangfusong"] = FigureState(status="retired")
    only_unheard(fs, nobody, ("fs_fire_guan", 2))
    assert foreshadow.hear_after_action(nobody.state, fs, "north", FixedRandom(0.0), world) == []  # 沒人出面
    fs.config.season_one = False
    off = player(fs, world, "丙", "guan", "lake")
    only_unheard(fs, off, ("fs_fire_guan", 2))
    assert foreshadow.hear_after_action(off.state, fs, "north", FixedRandom(0.0), world) == []
    assert off.state.player.fragments["fs_fire_guan"] == [0, 1, 3]


# ── 最後一步 ─────────────────────────────────────────────


def test_final_step_window_night_and_front(fs, world):
    """前一週以前、白天、戰況 70（官軍）都按不下去；三者都對才按得下去。只說做不了，不說為什麼。"""
    game = player(fs, world, "甲", "guan", "lake", time=night_in_window(fs))
    p, w = game.state.player, game.state.world
    assert option(game, "fs:fs_fire_guan").label == "束苣乘城（東西還沒備齊）"
    p.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    assert option(game, "fs:fs_fire_guan") == Option(id="fs:fs_fire_guan", label="束苣乘城", enabled=True)
    w.time = cal(fs, 4, 4, 0, 30)  # 早一週，也是夜裡
    assert option(game, "fs:fs_fire_guan") == Option(id="fs:fs_fire_guan", label="束苣乘城（時候未到）", enabled=False)
    w.time = cal(fs, 5, 4, 12)  # 時間窗內、白天
    assert option(game, "fs:fs_fire_guan").label == "束苣乘城（時候未到）"
    w.time = night_in_window(fs)
    w.trends["yingru"] = 70
    assert option(game, "fs:fs_fire_guan") == Option(id="fs:fs_fire_guan", label="束苣乘城（戰況不利）", enabled=False)
    w.trends["yingru"] = 60
    assert option(game, "fs:fs_fire_guan").enabled
    w.schedule["changshe_fire"] = cal(fs, 7, 0, 2)  # 管理者把決戰挪到第 7 週週一 02:00：時間窗跟著挪
    assert option(game, "fs:fs_fire_guan").label == "束苣乘城（時候未到）"
    w.time = cal(fs, 6, 2, 1)
    assert option(game, "fs:fs_fire_guan").enabled
    assert game.choose("fs:fs_fire_guan:東") == ["（此刻無法這麼做。）"]  # 沒先看題不能直接答
    p.location = "town"
    assert option(game, "fs:fs_fire_guan") is None  # 不在那個地點
    p.location = "lake"
    w.timeline["changshe_fire"] = TimelineResult(key="guan:大勝", time=w.time)
    assert option(game, "fs:fs_fire_guan") is None  # 大事已經發生：選項不出現
    huang = player(fs, world, "乙", "huang", "lake", time=night_in_window(fs))
    assert not any(i.startswith("fs:") for i in ids(huang))


def test_requires_any_of_and_unready_text(fs, world):
    """黃巾的勸營：乾葦證物或波才情誼（30 → 9）擇一；兩樣都沒有時按不下去，寫的是波才那句話。"""
    game = player(fs, world, "乙", "huang", "town", time=night_in_window(fs))
    p = game.state.player
    assert option(game, "fs:fs_fire_huang") == Option(
        id="fs:fs_fire_huang", label="勸營（官軍縮在城裡，我還怕他放火？）", enabled=False,
    )
    p.affinities["bocai"] = 9
    assert option(game, "fs:fs_fire_huang").enabled
    p.affinities["bocai"] = 8
    p.clue_items = {"fs_dry_reeds": 1}
    assert option(game, "fs:fs_fire_huang").enabled
    w = game.state.world
    w.time = cal(fs, 5, 4, 12)  # 黃巾這一條不用夜裡
    assert option(game, "fs:fs_fire_huang").enabled
    w.trends["yingru"] = 39
    assert option(game, "fs:fs_fire_huang").label == "勸營（戰況不利）"


def test_first_finisher_locks_later_ones_are_losers(fs, world):
    """官軍甲先完成、黃巾乙後完成、官軍丙更晚：locks 是甲，lock_losers 依序有乙、丙；甲與丙看到的成功敘事一字不差，
    乙看到的就是自己那條鏈的敘事；三個人都記貢獻、都不發任何傳聞。"""
    t = night_in_window(fs)
    direction = wind(world)
    rumors = list(world.get_season().rumors)
    jia = player(fs, world, "甲", "guan", "lake", time=t)
    jia.state.player.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    first = finish_fire_guan(jia, direction)
    assert first == [
        f"▸ {direction}",
        "你把葦束膏油交進營中，又在沙盤上畫了風向。皇甫嵩看了很久，只說：「就等那一夜。」",
        "葦束 -1", "膏油 -1",
    ]
    assert jia.state.player.clue_items == {} and "fs_fire_guan" in jia.state.player.fs_done
    assert jia.state.player.fs_asking is None
    assert world.get_season().locks["changshe_fire"] == Lock(side="guan", name="甲", time=t)

    yi = player(fs, world, "乙", "huang", "town", time=t)
    yi.state.player.clue_items = {"fs_dry_reeds": 1}
    assert yi.choose("fs:fs_fire_huang") == ["波才問：「那你說，營往哪邊挪？」"]
    assert yi.choose(f"fs:fs_fire_huang:{direction}") == [
        f"▸ {direction}", "波才盯著那束乾葦看了半晌，啐了一口：「拔營。」", "長社的乾葦 -1",
    ]
    bing = player(fs, world, "丙", "guan", "lake", time=t)
    bing.state.player.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    assert finish_fire_guan(bing, direction) == first

    season = world.get_season()
    assert season.locks["changshe_fire"] == Lock(side="guan", name="甲", time=t)
    assert season.lock_losers["changshe_fire"] == [Lock(side="huang", name="乙", time=t), Lock(side="guan", name="丙", time=t)]
    assert season.rumors == rumors
    week = calendar.point(t, fs).week
    for game in (jia, yi, bing):
        assert game.state.player.contrib == 50 and game.state.player.contrib_weeks == {week: 50}
    assert jia.state.journal[0].lines == bing.state.journal[0].lines
    assert jia.state.journal[0].changes == bing.state.journal[0].changes
    assert option(jia, "fs:fs_fire_guan") is None  # 每人每條鏈只成功一次


def test_lock_is_invisible(fs, world):
    """Review Focus 3：甲鎖定前後，第三人（同陣營、同一個地點、什麼都還沒準備）的 main_view 一字不差
    （場景、傳聞、江湖史、大勢、公告、江湖紀錄、選單）。決戰的起點與選項不讀 locks（只有 timetable.resolve 讀），
    所以這裡改驗揭曉：鎖定真的寫下了，而且要到大事當天的公告與江湖史才看得到甲的名號。"""
    t = night_in_window(fs)
    jia = player(fs, world, "甲", "guan", "lake", time=t)
    jia.state.player.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    jia._save_season()
    ding = player(fs, world, "丁", "guan", "lake", time=t)
    world.record_faction("丁", "guan")  # 真人投靠就在名冊上（這裡直接設陣營沒走投靠）；名冊空著時畫面的割據說明會隨甲的第一次行動變（FB-065 M1）
    refresh(ding)
    before = server.main_view(ding)
    finish_fire_guan(jia, wind(world))
    refresh(ding)
    assert server.main_view(ding) == before
    assert "甲" not in str(before) and option(ding, "fs:fs_fire_guan").label == "束苣乘城（東西還沒備齊）"  # 丁照樣做得了

    season = world.get_season()
    reveal = GameState(player=ding.state.player, world=season)
    msgs = timetable.resolve(reveal, fs, next(e for e in fs.timetable if e.id == "changshe_fire"), FixedRandom(0.5),
                             key="guan:大勝")
    assert msgs == ["【江湖大事】" + CHANGSHE_LOCKED.replace("{name}", "甲")]
    assert season.timeline["changshe_fire"].locked_by == "甲"
    assert [r.text for r in season.chronicle][-1] == "皇甫嵩火攻長社。（甲改寫）"


def test_anonymous_lockers_stay_anonymous_in_the_announcement(fs, world):
    """匿名的人鎖定、搶輸、做完豪強那一條：公告、江湖史都寫「某位少俠」；時間軸的 locked_by、losers 與 third_party 留真名
    （T9 的稱號要用）。不匿名的照舊寫名號。"""
    t = night_in_window(fs)
    direction = wind(world)
    changshe = next(e for e in fs.timetable if e.id == "changshe_fire")
    changshe.locked_chronicle = {"guan": "火具是{name}備下的。"}
    changshe.third_party_chronicle = "{name} 收了兩邊的糧錢。"
    jia = player(fs, world, "甲", "guan", "lake", time=t)
    jia.state.player.anonymous = True
    jia.state.player.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    finish_fire_guan(jia, direction)
    yi = player(fs, world, "乙", "huang", "town", time=t)
    yi.state.player.anonymous = True
    yi.state.player.clue_items = {"fs_dry_reeds": 1}
    yi.choose("fs:fs_fire_huang")
    yi.choose(f"fs:fs_fire_huang:{direction}")
    bing = player(fs, world, "丙", "haoqiang", "town", rng=FixedRandom(0.0), time=t)
    bing.state.player.anonymous = True
    bing.state.player.fs_counters = {"two_buyers": 1}
    bing.state.player.materials = {"man_1": 4}
    bing.choose("fs:fs_fire_haoqiang")
    bing.state.player.location = "lake"
    bing.choose("fs:fs_fire_haoqiang")
    ding = player(fs, world, "丁", "haoqiang", "town", rng=FixedRandom(0.0), time=t)  # 不匿名的豪強
    ding.state.player.fs_counters = {"two_buyers": 1}
    ding.state.player.materials = {"man_1": 4}
    ding.choose("fs:fs_fire_haoqiang")
    ding.state.player.location = "lake"
    ding.choose("fs:fs_fire_haoqiang")

    season = world.get_season()
    assert season.locks["changshe_fire"] == Lock(side="guan", name="甲", time=t, shown="某位少俠")
    assert season.lock_losers["changshe_fire"] == [Lock(side="huang", name="乙", time=t, shown="某位少俠")]
    assert season.third_party["changshe_fire"] == ["丙", "丁"]
    reveal = GameState(player=ding.state.player, world=season)
    msgs = timetable.resolve(reveal, fs, changshe, FixedRandom(0.5), key="guan:大勝")
    assert msgs == ["【江湖大事】" + CHANGSHE_LOCKED.replace("{name}", "某位少俠") + CHANGSHE_LOSER.replace("{loser}", "某位少俠")
                    + changshe.third_party_text.replace("{name}", "某位少俠、丁")]
    assert [r.text for r in season.chronicle][-2:] == ["火具是某位少俠備下的。", "某位少俠、丁 收了兩邊的糧錢。"]
    result = season.timeline["changshe_fire"]
    assert (result.locked_by, result.losers) == ("甲", ["乙"])
    assert not any(name in msgs[0] for name in "甲乙丙")


def test_wrong_answer_penalties(fs, world):
    """長社官軍收走物品；黃巾情誼 −5；送金帛亮出黃巾要等一個曆日、塞包袱沒有損失；進大將軍府說錯三樣全部作廢。"""
    t = night_in_window(fs)
    wrong = next(d for d in "東南西北" if d != wind(world))
    guan = player(fs, world, "甲", "guan", "lake", time=t)
    guan.state.player.clue_items = {"fs_reeds": 2, "fs_oil": 1}
    assert finish_fire_guan(guan, wrong) == [f"▸ {wrong}", "軍司馬搖頭：「這一面放火，燒的是我們自己。」", "葦束 -2", "膏油 -1"]
    assert guan.state.player.clue_items == {} and guan.state.player.fs_done == [] and guan.state.player.fs_asking is None
    assert option(guan, "fs:fs_fire_guan").label == "束苣乘城（東西還沒備齊）"  # 備料後可以再來

    huang = player(fs, world, "乙", "huang", "town", time=t)
    huang.state.player.affinities["bocai"] = 12
    huang.choose("fs:fs_fire_huang")
    assert huang.choose(f"fs:fs_fire_huang:{wrong}") == [f"▸ {wrong}", "「挪到那邊？官軍做夢都要笑醒。」", "波才情誼 -5"]
    assert huang.state.player.affinities["bocai"] == 7
    assert option(huang, "fs:fs_fire_huang").label == "勸營（官軍縮在城裡，我還怕他放火？）"

    luzhi_t = cal(fs, 7, 2)  # 盧植下獄在第 8 週週一：前 7 曆日內
    bribe = player(fs, world, "丙", "huang", "port", time=luzhi_t)
    bribe.state.player.fs_counters = {"guanyin": 2}
    bribe.choose("fs:fs_jail_huang")
    assert bribe.choose("fs:fs_jail_huang:2") == ["▸ 直接把包袱塞給他", "他裝作不認識你。"]
    assert option(bribe, "fs:fs_jail_huang").enabled and bribe.state.player.fs_counters == {"guanyin": 2}
    bribe.choose("fs:fs_jail_huang")
    assert bribe.choose("fs:fs_jail_huang:3") == ["▸ 亮出黃巾", "他嚇得跑了。"]
    assert option(bribe, "fs:fs_jail_huang").label == "送金帛（時候未到）"
    bribe.state.world.time = luzhi_t + DAY / calendar.cal_scale(fs) - 1
    assert not option(bribe, "fs:fs_jail_huang").enabled
    bribe.state.world.time = luzhi_t + DAY / calendar.cal_scale(fs)
    assert option(bribe, "fs:fs_jail_huang").enabled
    bribe.choose("fs:fs_jail_huang")
    assert bribe.choose("fs:fs_jail_huang:1")[1] == "老宦官接過包袱掂了掂，沒有多看你一眼：「話會帶到。」"
    assert bribe.state.player.fs_counters == {"guanyin": 2}  # 計數不扣

    court = player(fs, world, "丁", "guan", "port", time=luzhi_t)
    court.state.player.clue_items = {"fs_letter": 1, "fs_ledger": 1, "fs_witness": 1}
    court.choose("fs:fs_jail_guan")
    assert court.choose("fs:fs_jail_guan:1") == ["▸ 盧中郎冤枉", "何進聳聳肩，證物退還給你。"]
    assert court.state.player.clue_items == {"fs_letter": 1, "fs_ledger": 1, "fs_witness": 1}
    court.choose("fs:fs_jail_guan")
    assert court.choose("fs:fs_jail_guan:3") == [
        "▸ 不辦的話，證據就送到別人手上", "何進大怒，三樣東西全被收走了。", "郡守的血書 -1", "渡口的貨帳 -1", "宮中的證人 -1",
    ]
    assert court.state.player.clue_items == {}


def test_leaving_the_question_and_follow_up_questions(fs, world):
    """看題之後選單只剩答案與「作罷」；作罷什麼都不損失。追問（then）要全對才算；選項自己的懲罰蓋過那一步的。"""
    game = player(fs, world, "甲", "haoqiang", "port", rng=FixedRandom(0.0))
    w, p = game.state.world, game.state.player
    materials_bag = {"man_1": 2}
    p.materials = dict(materials_bag)
    w.time = timetable_when(game, "wancheng") - 1
    assert option(game, "fs:fs_wan_haoqiang").label == "討冊子（時候未到）"  # 集結開始前
    w.time = timetable_when(game, "wancheng") + 1  # 決戰排定的時間到了（集結中）、還沒收場
    assert option(game, "fs:fs_wan_haoqiang").enabled
    assert game.choose("fs:fs_wan_haoqiang") == ["老縣吏抱著冊子不放。"]
    assert ids(game) == ["fs:fs_wan_haoqiang:1", "fs:fs_wan_haoqiang:2", "fs:leave"]
    assert "老縣吏抱著冊子不放。" in game.scene_text()
    assert game.travel_refusal("town") == "正在答話，先作罷才能安排前往"
    assert game.choose("fs:leave") == ["你想了想，暫且作罷。"] and p.fs_asking is None
    game.choose("fs:fs_wan_haoqiang")
    assert game.choose("fs:fs_wan_haoqiang:2") == ["▸ 帶人進縣衙直接拿冊子", "老吏把冊子扔進火盆，這次不算。"]
    assert p.materials == materials_bag
    game.choose("fs:fs_wan_haoqiang")
    assert game.choose("fs:fs_wan_haoqiang:1") == ["▸ 開倉放糧，讓縣裡的人自己推你", "老縣吏又問：「糧從哪裡來？」"]
    assert ids(game) == ["fs:fs_wan_haoqiang:倉", "fs:fs_wan_haoqiang:搶", "fs:leave"]
    assert game.choose("fs:fs_wan_haoqiang:搶") == ["▸ 從黃巾手上搶", "老縣吏搖頭。"]
    game.choose("fs:fs_wan_haoqiang")
    game.choose("fs:fs_wan_haoqiang:1")
    w.timeline["zhangmancheng"] = TimelineResult(key="不成", time=0.0)  # 宛城是乙版
    assert game.choose("fs:fs_wan_haoqiang:倉") == ["▸ 從自家倉裡出", "老縣吏把冊子捧出來，城外的官軍還沒走遠。", "粗糧 -2"]
    assert w.third_party["wancheng"] == ["甲"] and "wancheng" not in w.locks
    w.timeline["wancheng"] = TimelineResult(key="乙:guan:大勝", time=w.time)
    assert option(game, "fs:fs_wan_haoqiang") is None


def timetable_when(game: Game, event_id: str) -> float:
    event = next(e for e in game.content.timetable if e.id == event_id)
    return timetable.when(game.state, game.content, event)


def test_requirements_in_final_and_a_step_add_up(fs, world):
    """審查 M1：整條另要 4 份糧草（final.requires）、每一趟也要 4 份（係數 0.3：2＋2＋2＝6）。條件照「這一趟加整條」一起算，
    整條的那份等完成才交，交不夠就不能完成；檢定失敗只沒收這一趟的 2 份。"""
    chain = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_haoqiang")
    chain.final.requires.grain = 4
    validate(fs)
    t = night_in_window(fs)
    game = player(fs, world, "甲", "haoqiang", "town", rng=FixedRandom(0.0), time=t)
    p = game.state.player
    p.fs_counters = {"two_buyers": 1}
    p.materials = {"man_1": 4}
    assert option(game, "fs:fs_fire_haoqiang").enabled  # 這一趟 2 ＋ 整條 2
    assert game.choose("fs:fs_fire_haoqiang") == ["（本人——成功）", "長社的帳房在你的契上按了手印。", "粗糧 -2"]
    p.location = "lake"
    assert option(game, "fs:fs_fire_haoqiang").label == "交糧（東西還沒備齊）"  # 只剩 2 份：不夠這一趟加整條
    assert game.choose("fs:fs_fire_haoqiang") == ["（此刻無法這麼做。）"]
    assert "fs_fire_haoqiang" not in p.fs_done and p.materials == {"man_1": 2}
    p.materials = {"man_1": 4}
    game.rng = FixedRandom(0.99)
    assert game.choose("fs:fs_fire_haoqiang") == ["（本人——失敗）", "半路撞上官軍斥候，糧車被扣下。", "粗糧 -2"]
    p.materials = {"man_1": 4}
    game.rng = FixedRandom(0.0)
    assert game.choose("fs:fs_fire_haoqiang") == [
        "（本人——成功）", "黃巾的帳房在你的契上按了手印。",
        "兩邊的帳房都在你的契上按了手印。不論那一夜誰勝誰敗，他們都欠你一份人情。", "粗糧 -4",
    ]
    assert p.materials == {} and "fs_fire_haoqiang" in p.fs_done


def test_any_of_branch_counts_items_on_top_of_the_rest(fs, world):
    """any_of 的那一組跟上一層要同一樣東西時，要夠兩份才算（上一層 1 ＋ 乾葦那一組 1）；用情誼那一組就只要 1。"""
    chain = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_huang")
    chain.final.requires.clue_items = {"fs_dry_reeds": 1}
    game = player(fs, world, "乙", "huang", "town", time=night_in_window(fs))
    p = game.state.player
    p.clue_items = {"fs_dry_reeds": 1}
    assert option(game, "fs:fs_fire_huang").label == "勸營（官軍縮在城裡，我還怕他放火？）"
    p.affinities["bocai"] = 9
    assert option(game, "fs:fs_fire_huang").enabled
    p.affinities["bocai"] = 0
    p.clue_items = {"fs_dry_reeds": 2}
    game.choose("fs:fs_fire_huang")
    assert game.choose(f"fs:fs_fire_huang:{wind(world)}")[-1] == "長社的乾葦 -2"
    assert p.clue_items == {}


def test_cannot_seclude_while_answering(fs, world):
    """審查 M6：看題之後不能去閉關（跟事件待處理一樣）；作罷之後才行。"""
    game = player(fs, world, "丙", "huang", "port", time=cal(fs, 7, 2))
    game.state.player.fs_counters = {"guanyin": 2}
    game.choose("fs:fs_jail_huang")
    assert game.seclude(2) == ["你現在無法閉關。"] and game.state.player.busy_until is None
    game.choose("fs:leave")
    game.seclude(2)
    assert game.state.player.busy_until is not None


def test_haoqiang_chain_is_third_party(fs, world):
    """兩頭賣糧：兩趟（長社、黃巾營寨各一趟）都做完才算；寫進 third_party，不碰 locks，也不會讓官軍、黃巾的鎖定失效。
    檢定失敗沒收那一趟的糧草，可以再來。"""
    t = night_in_window(fs)
    game = player(fs, world, "甲", "haoqiang", "town", rng=FixedRandom(0.99), time=t)
    p, w = game.state.player, game.state.world
    p.materials = {"man_1": 6}
    assert option(game, "fs:fs_fire_haoqiang").label == "交糧（東西還沒備齊）"  # 還沒有「兩邊都賣」的起點
    p.fs_counters = {"two_buyers": 1}
    w.locks["changshe_fire"] = Lock(side="guan", name="官軍某甲", time=0.0)
    assert option(game, "fs:fs_fire_haoqiang").enabled
    assert game.choose("fs:fs_fire_haoqiang") == ["（本人——失敗）", "帳房翻了兩頁就看穿了假帳，糧車被扣下。", "粗糧 -2"]
    assert p.materials == {"man_1": 4} and p.fs_done == []
    game.rng = FixedRandom(0.0)
    assert game.choose("fs:fs_fire_haoqiang") == ["（本人——成功）", "長社的帳房在你的契上按了手印。", "粗糧 -2"]
    assert p.fs_done == ["fs_fire_haoqiang:0"] and option(game, "fs:fs_fire_haoqiang") is None  # 長社這一趟做完了
    p.location = "lake"
    assert game.choose("fs:fs_fire_haoqiang") == [
        "（本人——成功）", "黃巾的帳房在你的契上按了手印。",
        "兩邊的帳房都在你的契上按了手印。不論那一夜誰勝誰敗，他們都欠你一份人情。", "粗糧 -2",
    ]
    assert p.fs_done == ["fs_fire_haoqiang:0", "fs_fire_haoqiang:1", "fs_fire_haoqiang"]
    assert w.third_party["changshe_fire"] == ["甲"]
    assert w.locks["changshe_fire"].name == "官軍某甲" and "changshe_fire" not in w.lock_losers
    assert p.contrib == 50


def test_chain_invalid_when_figure_retired(fs, world):
    """波才退場後，黃巾識破火攻的最後一步不出現，片段也不再發。"""
    game = player(fs, world, "乙", "huang", "town", time=night_in_window(fs))
    game.state.player.clue_items = {"fs_dry_reeds": 1}
    assert option(game, "fs:fs_fire_huang").enabled
    game.state.world.figures["bocai"] = FigureState(status="retired")
    assert option(game, "fs:fs_fire_huang") is None
    assert foreshadow.hear_after_action(game.state, fs, "north", FixedRandom(0.0), world) == []
    assert foreshadow.hear_from_event(game.state, fs, "fs_ev_boatman", world) == []
    game.state.world.figures["bocai"] = FigureState(status="jailed")  # 下獄不算退場
    assert option(game, "fs:fs_fire_huang").enabled


def test_tianji_answers_stable_within_season(fs, world):
    for key, candidates in (("wind", "東南西北"), ("disguise", ("鹽車", "棺木", "香客", "商隊"))):
        answers = [foreshadow.tianji_answer(tianji, key) for tianji in range(40)]
        assert all(a in candidates for a in answers)
        assert len(set(answers)) > 1  # 換季（天機 +1）會換
        assert answers == [foreshadow.tianji_answer(tianji, key) for tianji in range(40)]
    # 用穩定的雜湊（不是 Python 內建的 hash）：每次執行都一樣，釘死兩個值
    assert foreshadow.tianji_answer(0, "wind") == PINNED_WIND_0
    assert foreshadow.tianji_answer(3, "disguise") == PINNED_DISGUISE_3
    with pytest.raises(KeyError):
        foreshadow.tianji_answer(0, "mole")
    game = player(fs, world, "甲", "guan", "port")
    game.state.player.fragments = {"fs_jail_guan": [0]}  # 南區另一則先聽過：只剩靈台那一則
    heard = foreshadow.hear_after_action(game.state, fs, "south", FixedRandom(0.0), world)
    assert heard == [f"你聽到一件事：靈台的太史說，今年夜裡的風從{foreshadow.tianji_answer(world.read().tianji, 'wind')}來。"]


PINNED_WIND_0 = "南"  # sha256("0|tianji|wind")
PINNED_DISGUISE_3 = "商隊"  # sha256("3|tianji|disguise")


# ── 官銀 ─────────────────────────────────────────────────


def _won(monkeypatch, tier: str = "大勝") -> None:
    monkeypatch.setattr(team, "fight", lambda *a, **k: EncounterResult(tier=tier, margin=50, our_power=60, difficulty=1))


def test_guanyin_on_win_against_guan_squad(fs, world, monkeypatch):
    """只有黃巾、只有那兩個大區（fixture 是北區）、只有遊歷打贏官軍的隊伍才擲；中了 fs_counters["guanyin"] +1、寫一句。"""
    _won(monkeypatch)
    text = fs.foreshadows.guanyin.text
    fs.locations["lake"].enemies = ["guan_patrol"]
    fs.locations["port"].enemies = ["guan_patrol"]
    huang = player(fs, world, "乙", "huang", "lake", rng=FixedRandom(0.0))
    huang.choose("act:train")
    assert huang.state.player.fs_counters == {"guanyin": 1}
    assert text in huang.state.journal[0].lines and text in huang.state.battles[0].notes
    huang.rng = FixedRandom(fs.config.guanyin_chance + 0.01)
    huang.choose("act:train")
    assert huang.state.player.fs_counters == {"guanyin": 1}  # 沒擲中
    guan_squad_elsewhere = player(fs, world, "丙", "huang", "port", rng=FixedRandom(0.0))
    guan_squad_elsewhere.choose("act:train")
    assert guan_squad_elsewhere.state.player.fs_counters == {}  # 南區不算
    haoqiang = player(fs, world, "丁", "haoqiang", "lake", rng=FixedRandom(0.0))
    haoqiang.choose("act:train")
    assert haoqiang.state.player.fs_counters == {}  # 不是黃巾
    fs.locations["lake"].enemies = ["thug"]
    other_squad = player(fs, world, "戊", "huang", "lake", rng=FixedRandom(0.0))
    other_squad.choose("act:train")
    assert other_squad.state.player.fs_counters == {}  # 不是官軍的隊伍
    fs.locations["lake"].enemies = ["guan_patrol"]
    _won(monkeypatch, "落敗")
    lost = player(fs, world, "己", "huang", "lake", rng=FixedRandom(0.0))
    lost.choose("act:train")
    assert lost.state.player.fs_counters == {}  # 沒打贏


def test_guanyin_stops_once_no_open_chain_reads_it(fs, world, monkeypatch):
    """審查 M3：讀官銀的那條鏈做完了、失效了、或那件大事已經發生，官銀就不再掉（也不擲那一下）。"""
    _won(monkeypatch)
    fs.locations["lake"].enemies = ["guan_patrol"]
    text = fs.foreshadows.guanyin.text
    done = player(fs, world, "乙", "huang", "lake", rng=FixedRandom(0.0))
    done.state.player.fs_done = ["fs_jail_huang"]
    done.choose("act:train")
    assert done.state.player.fs_counters == {} and text not in done.state.journal[0].lines
    out = player(fs, world, "丙", "huang", "lake", rng=FixedRandom(0.0))
    out.state.world.figures["luzhi"] = FigureState(status="retired")
    out.choose("act:train")
    assert out.state.player.fs_counters == {}
    resolved = player(fs, world, "丁", "huang", "lake", rng=FixedRandom(0.0))
    resolved.state.world.timeline["luzhi_jailed"] = TimelineResult(key="成", time=0.0)
    resolved.choose("act:train")
    assert resolved.state.player.fs_counters == {}


def test_no_guanyin_or_foreshadow_items_leak_when_no_chain_reads_them(fs, world, monkeypatch):
    """QA：開關開著、季也蓋了章，黃巾在北區打贏官軍的隊伍，但沒有任何鏈讀官銀：江湖紀錄、增減、戰報、背包都看不到
    官銀，也不擲那一下骰；有一條鏈讀官銀時，同樣的勝仗才擲得到。物品那一半（審查 M4）：一條鏈都沒有時，準備事件與
    片段事件不出現，就算眼前已經是那則準備事件，選了也不給葦束、不寫字。"""
    _won(monkeypatch)
    fs.locations["lake"].enemies = ["guan_patrol"]
    leaks = ("官銀", "guanyin", "葦束", "膏油", "乾葦", "血書", "貨帳", "證人")

    def shown(game: Game) -> list[str]:
        entry = game.state.journal[0]
        texts = entry.lines + entry.changes + [entry.tag, skillview.bag_text(game.state, fs)]
        if game.state.battles:
            record = game.state.battles[0]
            texts += record.notes + record.changes + record.materials
        return texts

    reading = [c for c in fs.foreshadows.chains if c.id == "fs_jail_huang"]
    fs.foreshadows.chains = [c for c in fs.foreshadows.chains if c.id != "fs_jail_huang"]
    game = player(fs, world, "乙", "huang", "lake", rng=FixedRandom(0.0))
    game.state.player.fragments = {"fs_fire_huang": [0, 1]}  # 片段都聽過了：這裡只看官銀
    assert calendar.season_one_on(game.state.world, fs)
    game.choose("act:train")
    assert not any(word in text for text in shown(game) for word in leaks)
    assert game.state.player.fs_counters == {}
    fs.foreshadows.chains += reading
    game.choose("act:train")
    assert game.state.player.fs_counters == {"guanyin": 1}
    assert fs.foreshadows.guanyin.text in game.state.journal[0].lines

    chains, fs.foreshadows.chains = fs.foreshadows.chains, []  # 物品與事件都在、一條鏈都沒有
    guan = player(fs, world, "甲", "guan", "lake", rng=FixedRandom(0.0))
    assert calendar.season_one_on(guan.state.world, fs) and not foreshadow.active(guan.state, fs)
    from tianxia.events import event_candidates

    candidates = [e.id for e in event_candidates(guan.state, fs, "explore")]
    assert "fs_prep_reeds" not in candidates  # 會給伏筆物品的事件不出現
    # 老船夫只是因為有鏈引用它才算伏筆事件；一條鏈都沒有時它就是一則不帶線索的一般事件，出現也不會給任何東西
    guan.state.pending_event = "fs_prep_reeds"  # 眼前已經是那則準備事件（例如鏈在中途被拿掉）
    guan.choose("choice:0")
    assert guan.state.player.clue_items == {}
    assert not any(word in text for text in shown(guan) for word in leaks)
    fs.foreshadows.chains = chains  # 有鏈時同一個選項才給
    guan.state.pending_event = "fs_prep_reeds"
    guan.choose("choice:0")
    assert guan.state.player.clue_items == {"fs_reeds": 1} and "獲得 葦束 ×1" in guan.state.journal[0].lines


# ── 條件、效果、開關 ─────────────────────────────────────


def test_condition_factions_night_weeks(fs, world):
    game = player(fs, world, "甲", "haoqiang", "town")
    s, w = game.state, game.state.world
    check = rules.check_condition
    assert check(Condition(factions=["haoqiang", "guan"]), s, fs)
    assert not check(Condition(factions=["guan"]), s, fs)
    s.player.faction = None
    assert not check(Condition(factions=["haoqiang"]), s, fs) and check(Condition(), s, fs)
    w.time = cal(fs, 5, 2, 23, 30)
    assert check(Condition(night=True), s, fs) and not check(Condition(night=False), s, fs)
    w.time = cal(fs, 5, 2, 12)
    assert check(Condition(night=False), s, fs) and not check(Condition(night=True), s, fs)
    assert check(Condition(week_min=4, week_max=6), s, fs) and check(Condition(week_min=5, week_max=5), s, fs)
    assert not check(Condition(week_min=6), s, fs) and not check(Condition(week_max=4), s, fs)
    assert not check(Condition(night=False), s)  # 沒給內容就看不到季曆：不成立
    s.player.clue_items = {"fs_reeds": 2}
    assert check(Condition(clue_items={"fs_reeds": 2}), s, fs) and not check(Condition(clue_items={"fs_reeds": 3}), s, fs)
    assert check(Condition(any_of=[Condition(week_min=9), Condition(night=False)]), s, fs)
    fs.config.season_one = False  # 開關關著：季曆的條件一律不成立，陣營與物品照常
    assert not check(Condition(night=False), s, fs) and not check(Condition(week_min=1), s, fs)
    assert check(Condition(clue_items={"fs_reeds": 2}), s, fs)


def test_prep_events_and_their_items(fs, world):
    """準備事件：只對那個陣營出現；週次的條件照季曆；給的物品寫成「獲得 葦束 ×1」，計數不寫字。"""
    guan = player(fs, world, "甲", "guan", "lake")
    huang = player(fs, world, "乙", "huang", "lake")
    from tianxia.events import event_candidates

    assert "fs_prep_reeds" in [e.id for e in event_candidates(guan.state, fs, "explore")]
    assert "fs_prep_reeds" not in [e.id for e in event_candidates(huang.state, fs, "explore")]
    msgs = rules.apply_effect(Effect(clue_items={"fs_reeds": 1}), guan.state, fs, world)
    assert msgs == ["獲得 葦束 ×1"] and guan.state.player.clue_items == {"fs_reeds": 1}
    assert rules.apply_effect(Effect(clue_items={"fs_reeds": -3}), guan.state, fs, world) == ["葦束 -1"]
    assert guan.state.player.clue_items == {}
    assert rules.apply_effect(Effect(fs_counters={"two_buyers": 1}), guan.state, fs, world) == []
    assert guan.state.player.fs_counters == {"two_buyers": 1}
    seller = player(fs, world, "丙", "haoqiang", "town")
    seller.state.world.time = cal(fs, 3, 6, 12)
    assert "fs_ev_two_buyers" not in [e.id for e in event_candidates(seller.state, fs, "explore")]
    seller.state.world.time = cal(fs, 4, 0, 1)
    assert "fs_ev_two_buyers" in [e.id for e in event_candidates(seller.state, fs, "explore")]


def test_foreshadow_off_switch_changes_nothing(fs, world, monkeypatch):
    """開關關著（這一季開季時沒開）：同樣的行動不抽片段、沒有 fs: 選項、沒有 talk:clue: 選項；準備事件與片段事件不出現、
    物品與計數不給；官銀不擲。"""
    fs.config.season_one = False
    _won(monkeypatch)
    fs.locations["lake"].enemies = ["guan_patrol"]
    guan = player(fs, world, "甲", "guan", "port", rng=FixedRandom(0.0))
    assert not calendar.season_one_on(guan.state.world, fs)
    guan.state.world.time = night_in_window(fs)
    guan.state.player.clue_items = {"fs_letter": 1, "fs_ledger": 1, "fs_witness": 1}
    for _ in range(3):
        guan.choose("act:explore")
        assert not any("你聽到一件事" in line for line in guan.state.journal[0].lines)
    assert guan.state.player.fragments == {}
    assert not any(i.startswith("fs:") for i in ids(guan))
    _talking(guan, "zhujun", 100)
    guan.state.world.figures["huangfusong"] = FigureState(status="retired")
    assert ids(guan) == ["talk:0", "talk:1", "talk:leave"]
    assert foreshadow.hear_from_event(guan.state, fs, "fs_ev_boatman", world) == []
    lake = player(fs, world, "乙", "guan", "lake")
    from tianxia.events import event_candidates

    candidates = [e.id for e in event_candidates(lake.state, fs, "explore")]
    assert "fs_prep_reeds" not in candidates and "fs_ev_boatman" not in candidates
    assert "scroll" in candidates  # 一般的事件照舊
    assert rules.apply_effect(Effect(clue_items={"fs_reeds": 1}, fs_counters={"two_buyers": 1}), lake.state, fs, world) == []
    assert lake.state.player.clue_items == {} and lake.state.player.fs_counters == {}
    huang = player(fs, world, "丙", "huang", "lake", rng=FixedRandom(0.0))
    huang.choose("act:train")
    assert huang.state.player.fs_counters == {}
    assert foreshadow.final_options(huang.state, fs, "lake") == []


def test_new_season_clears_the_foreshadow_fields(fs, world):
    """QA：換季（管理者開下一季，玩家下次同步時 _reconcile_season → _reset_player_for_new_season）之後，
    片段、物品、計數、做完的、冷卻、正在答的題都是空的。"""
    fs.config.admins = ["管理者"]
    admin = player(fs, world, "管理者", None, "town")
    game = player(fs, world, "甲", "guan", "lake")
    p = game.state.player
    p.fragments, p.clue_items, p.fs_counters = {"fs_fire_guan": [0, 2]}, {"fs_reeds": 3}, {"guanyin": 4}
    p.fs_done, p.fs_cooldown_until, p.fs_asking, p.fs_asked = ["fs_fire_guan"], {"fs_jail_huang": 99.0}, "fs_jail_huang", 1
    p.donations = {"port:糧草": 5}
    admin.admin_end_season(now=10.0)
    admin.admin_next_season(now=20.0)
    game.sync(30.0)
    p = game.state.player
    assert game.state.player.season_number == 2
    assert (p.fragments, p.clue_items, p.fs_counters, p.fs_done, p.fs_cooldown_until) == ({}, {}, {}, [], {})
    assert (p.fs_asking, p.fs_asked, p.donations) == (None, 0, {})


# ── 假人、載入與檢查 ─────────────────────────────────────


def test_bots_never_pick_foreshadow_options(fs, world):
    game = player(fs, world, "甲", "guan", "lake")
    fs_options = [Option(id="fs:fs_fire_guan", label="束苣乘城"), Option(id="talk:clue:fs_fire_guan:2", label="問起破敵之策")]
    assert bot.pick(game, fs_options, random.Random(0)) is None
    profile = BotProfile(personality="普通", seed=1)
    assert [bot_policy.score(game, o, profile) for o in fs_options] == [None, None]


def test_missing_or_empty_foreshadows_file_is_empty(tmp_path):
    from conftest import FIXTURE

    assert load_content(FIXTURE).foreshadows == Foreshadows()
    import shutil

    root = tmp_path / "content"
    shutil.copytree(FIXTURE, root)
    (root / "foreshadows.json").write_text("", encoding="utf-8")
    assert load_content(root).foreshadows == Foreshadows()
    (root / "foreshadows.json").write_text('{"items": [], "chains": []}', encoding="utf-8")
    assert load_content(root).foreshadows == Foreshadows()


@pytest.mark.parametrize("break_it, message", [
    (lambda c: setattr(c, "event", "nowhere"), "時刻表大事 nowhere"),
    (lambda c: setattr(c, "side", "pirates"), "陣營 pirates"),
    (lambda c: setattr(c.final, "location", "atlantis"), "地點 atlantis"),
    (lambda c: setattr(c.fragments[0], "region", "moon"), "大區 moon"),
    (lambda c: setattr(c.fragments[1], "event", "ghost_event"), "事件 ghost_event"),
    (lambda c: setattr(c.fragments[2], "character", "nobody"), "人物 nobody"),
    (lambda c: setattr(c.fragments[2], "stand_in", "nobody2"), "人物 nobody2"),
    (lambda c: c.final.requires.clue_items.update({"fs_magic": 1}), "伏筆物品 fs_magic"),
    (lambda c: setattr(c.final, "answer", "中"), "答案 中"),
    (lambda c: setattr(c.final, "answer", "tianji:mole"), "天機 mole"),
    (lambda c: c.final.options.pop(), "天機 wind 的選項"),
    (lambda c: setattr(c.final.wrong, "lose_items", ["fs_magic"]), "伏筆物品 fs_magic"),
    (lambda c: setattr(c.invalid_if, "figure_out", "nobody3"), "人物 nobody3"),
    (lambda c: setattr(c.final, "label", ""), "label"),
    (lambda c: setattr(c.final, "success_text", "火从哪一面放"), "繁體"),
])
def test_validate_catches_broken_chains(fs, break_it, message):
    chain = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_guan")
    break_it(chain)
    with pytest.raises(ContentError, match=message):
        validate(fs)


def test_validate_catches_the_review_gaps(fs):
    """審查 M5：題目沒有選項、對話片段的人物沒有對話的地方、鏈沒有戰況可看、官軍／黃巾的鏈鎖不到那件大事、
    物品沒有任何一條鏈讀它，都要在載入當下報 ContentError。"""
    guan = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_guan")
    jail = next(c for c in fs.foreshadows.chains if c.id == "fs_jail_huang")
    options = list(guan.final.options)
    cases = [
        (lambda: setattr(guan.final, "options", []), lambda: setattr(guan.final, "options", options), "題目要有選項"),
        (lambda: setattr(guan.fragments[2], "character", "luzhi"), lambda: setattr(guan.fragments[2], "character", "huangfusong"),
         "talk_at"),
        (lambda: setattr(guan.fragments[2], "stand_in", "dongzhuo"), lambda: setattr(guan.fragments[2], "stand_in", "zhujun"),
         "talk_at"),
        (lambda: setattr(jail, "front", None), lambda: setattr(jail, "front", "jizhou"), "戰況"),
    ]
    for break_it, fix_it, message in cases:
        break_it()
        with pytest.raises(ContentError, match=message):
            validate(fs)
        fix_it()
        validate(fs)
    luzhi = next(e for e in fs.timetable if e.id == "luzhi_jailed")
    luzhi.lock_result = {"guan": "不成"}
    with pytest.raises(ContentError, match="lock_result"):
        validate(fs)
    luzhi.lock_result = {"huang": "成", "guan": "不成"}
    fs.foreshadows.items.append(fs.foreshadows.items[0].model_copy(update={"id": "fs_spare", "name": "多出來的東西"}))
    with pytest.raises(ContentError, match="fs_spare"):
        validate(fs)


def test_validate_checks_steps_windows_and_counters(fs):
    chain = next(c for c in fs.foreshadows.chains if c.id == "fs_fire_haoqiang")
    chain.final.steps[1].location = "atlantis"
    with pytest.raises(ContentError, match="地點 atlantis"):
        validate(fs)
    chain.final.steps[1].location = "town"
    with pytest.raises(ContentError, match="同一個地點"):
        validate(fs)
    chain.final.steps[1].location = "lake"
    chain.final.location = "lake"
    with pytest.raises(ContentError, match="steps"):
        validate(fs)
    chain.final.location = None
    wan = next(c for c in fs.foreshadows.chains if c.id == "fs_wan_haoqiang")
    wan.event = "luzhi_jailed"
    with pytest.raises(ContentError, match="during_muster"):
        validate(fs)
    wan.event = "wancheng"
    fs.events["fs_ev_two_buyers"].choices[3].effect.fs_counters = {"three_buyers": 1}
    with pytest.raises(ContentError, match="three_buyers"):
        validate(fs)
    fs.events["fs_ev_two_buyers"].choices[3].effect.fs_counters = {"two_buyers": 1}
    fs.events["fs_prep_reeds"].condition.factions = ["pirates"]
    with pytest.raises(ContentError, match="陣營 pirates"):
        validate(fs)
    fs.events["fs_prep_reeds"].condition.factions = ["guan"]
    fs.foreshadows.guanyin.regions = ["moon"]
    with pytest.raises(ContentError, match="大區 moon"):
        validate(fs)
