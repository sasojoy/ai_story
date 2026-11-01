"""FB-810：豪強的假人投靠地方豪強那一下，傾向給「依附豪強人數少的那一軍」，不看投靠點（減法季批 3c 修正輪；PM 2026-10-26 定）。

批 3c 之後真人投靠豪強直接照投靠點給傾向（曹氏莊院 → 官軍），選邊鈕沒了；假人又不按「改幫」。新角色都從潁川出發、最近的豪強
投靠點是曹氏莊院，結果豪強的假人全部幫官軍（QA：官 5、巾 0）。這一檔鎖：假人投靠那一下照人數少的挑（一樣多照名號＋季的雜湊，
不碰亂數），真人照舊照投靠點，假人投靠之後照舊不按改幫。"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from wins_kit import wins_content, wins_game
from tianxia import server_bots, wins
from tianxia.bot_runner import BotRunner
from tianxia.characters import CharacterStore, open_characters
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile

T0 = 1_792_549_800.0  # 週三開季（同 QA 的 T0）


# ── 純規則：wins.bot_lean ─────────────────────────────


def test_bot_lean_goes_to_the_army_with_fewer_gentry():
    content = wins_content()
    assert wins.bot_lean("甲", 1, content, "haoqiang", {"haoqiang@guan": 3, "haoqiang@huang": 1}) == "huang"
    assert wins.bot_lean("甲", 1, content, "haoqiang", {"haoqiang@guan": 1, "haoqiang@huang": 3}) == "guan"
    assert wins.bot_lean("甲", 1, content, "haoqiang", {"haoqiang@huang": 1}) == "guan"  # 一個都沒有的那一軍算 0


def test_bot_lean_counts_only_the_gentry_not_the_armies():
    """數的是「依附豪強的人」（FB-810 的標準），不是那一軍全部的人：官軍本人再多也不影響。"""
    content = wins_content()
    rolls = {"guan": 40, "huang": 2, "haoqiang@guan": 1, "haoqiang@huang": 2}
    assert wins.bot_lean("甲", 1, content, "haoqiang", rolls) == "guan"


def test_bot_lean_tie_is_a_hash_of_the_name_and_the_season():
    """一樣多：照名號＋季的雜湊挑（不碰亂數）；同一個名號同一季永遠一樣，換名號、換季會有兩邊都出現。"""
    content = wins_content()
    even = {"haoqiang@guan": 2, "haoqiang@huang": 2}
    names = [f"客{i}" for i in range(24)]
    first = [wins.bot_lean(n, 1, content, "haoqiang", even) for n in names]
    assert first == [wins.bot_lean(n, 1, content, "haoqiang", even) for n in names]
    assert set(first) == {"guan", "huang"}
    assert [wins.bot_lean(n, 2, content, "haoqiang", even) for n in names] != first


def test_bot_lean_is_none_for_an_army_or_no_faction():
    content = wins_content()
    assert wins.bot_lean("甲", 1, content, "guan", {}) is None
    assert wins.bot_lean("甲", 1, content, None, {}) is None


# ── 引擎：投靠那一下 ─────────────────────────────


def _bot(game: Game) -> Game:
    game.state.player.bot = BotProfile(personality="普通", seed=1, faction="haoqiang", season_number=game.world.get_season_number())
    return game


def _gentry(world, name: str, ally: str) -> Game:
    """已經依附一軍的豪強（寫進名冊，別人投靠時數得到）。"""
    game = wins_game(name=name, faction="haoqiang", ally=ally, at="changshe", world=world)
    game.sync(T0)
    CharacterStore(world.db).save(game.state)
    assert world.roll_of(name) == f"haoqiang@{ally}"
    return game


def _join(game: Game, place: str) -> str | None:
    game.state.player.location = place
    game.choose("faction:haoqiang")
    game.choose("faction:confirm")
    assert game.state.player.faction == "haoqiang"
    return game.state.player.ally


@pytest.mark.slow
@pytest.mark.parametrize(("place", "side"), [("cao_manor", "guan"), ("haozu_fort", "huang"), ("zhuo_militia_hall", "guan")])
def test_a_human_still_takes_the_join_point_lean_even_when_it_is_lopsided(place, side):
    world = open_world()
    for i in range(3):  # 預設的那一邊已經很多人：真人照舊照投靠點，不管人數
        _gentry(world, f"先{i}", side)
    assert _join(wins_game(name="真人", at=place, world=world), place) == side


@pytest.mark.slow
@pytest.mark.parametrize(("place", "crowded", "expected"), [
    ("cao_manor", "guan", "huang"),        # 曹氏莊院預設官軍，官軍那邊豪強較多 → 幫黃巾
    ("haozu_fort", "huang", "guan"),       # 豪族塢堡預設黃巾，黃巾那邊豪強較多 → 幫官軍
    ("zhuo_militia_hall", "guan", "huang"),
])
def test_a_bot_joins_the_army_with_fewer_gentry_wherever_it_stands(place, crowded, expected):
    world = open_world()
    _gentry(world, "先一", crowded)
    _gentry(world, "先二", crowded)
    assert _join(_bot(wins_game(name="假乙", at=place, world=world)), place) == expected


@pytest.mark.slow
@pytest.mark.parametrize(("place", "against"), [("cao_manor", "huang"), ("haozu_fort", "guan")])
def test_a_bot_with_an_even_count_follows_the_hash_not_the_join_point(place, against):
    """兩邊一樣多：照名號＋季的雜湊，不照投靠點。挑一個雜湊結果跟投靠點預設相反的名號，才分得開兩個原因。"""
    world = open_world()
    _gentry(world, "先一", "guan")
    _gentry(world, "先二", "huang")
    content, season = wins_content(), world.get_season_number()
    even = {"haoqiang@guan": 1, "haoqiang@huang": 1}
    name = next(n for n in (f"假{i}" for i in range(64)) if wins.bot_lean(n, season, content, "haoqiang", even) == against)
    assert _join(_bot(wins_game(name=name, at=place, world=world)), place) == against

@pytest.mark.slow
def test_the_bot_count_is_read_at_confirm_not_at_the_first_press():
    """兩個假人先後按了「投靠」、還沒確認：確認那一下才數人（先確認的那一個已經記進名冊了），不會兩個都挑同一邊。"""
    world = open_world()
    one = _bot(wins_game(name="假一", at="cao_manor", world=world))
    two = _bot(wins_game(name="假二", at="cao_manor", world=world))
    one.choose("faction:haoqiang")
    two.choose("faction:haoqiang")
    one.choose("faction:confirm")
    one._record_faction()
    CharacterStore(world.db).save(one.state)
    two.choose("faction:confirm")
    assert {one.state.player.ally, two.state.player.ally} == {"guan", "huang"}


@pytest.mark.slow
def test_the_sect_join_of_a_human_is_unchanged():
    """拜入曹氏莊院（真人）照舊照門派所在地給官軍，不看人數。"""
    world = open_world()
    for i in range(3):
        _gentry(world, f"先{i}", "guan")
    game = wins_game(name="真人", at="cao_manor", world=world)
    game.state.pending_event = "cao_manor_join"
    from unittest import mock

    from tianxia import team
    from tianxia.encounter import EncounterResult

    with mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40)):
        game.choose("choice:0")
    assert game.state.player.ally == "guan"


@pytest.mark.slow
def test_gentry_server_bots_split_between_the_two_armies(monkeypatch):
    """BotRunner 假時鐘跑一段（QA 的重現：season21 正式內容，每輪 40 秒；修之前豪強假人 5 個全是官軍）：豪強假人兩軍都有、差距不超過 1；
    假人投靠之後照舊不按「改幫」或叛投。"""
    monkeypatch.setattr(server_bots, "is_online", lambda profile, now: True)
    content = wins_content()
    content.config.bot_tick_seconds, content.config.bot_fill_seconds = 1000.0, 1.0
    world = open_world()
    human = wins_game(content, name="看客", world=world)
    human.sync(T0)
    CharacterStore(world.db).save(human.state)
    now = [T0]
    pressed: Counter = Counter()
    original = Game.choose

    def spy(self, option_id, *args, **kwargs):
        if self.state.player.bot is not None and option_id.startswith(("faction:lean:", "defect:")):
            pressed[option_id] += 1
        return original(self, option_id, *args, **kwargs)

    monkeypatch.setattr(Game, "choose", spy)
    runner = BotRunner(content, world, open_characters(), random.Random(7), clock=lambda: now[0])

    def gentry_bots():
        return [s.player for s in CharacterStore(world.db).all(bots_only=True) if s.player.faction == "haoqiang"]

    for _ in range(120):  # 最多 120 輪；豪強假人（bots_min_per_faction 個）都投靠了就再跑 10 輪看它們有沒有亂按，然後收工
        now[0] += 40
        runner.tick()
        if len(gentry_bots()) >= content.config.bots_min_per_faction:
            break
    for _ in range(10):
        now[0] += 40
        runner.tick()
    gentry = gentry_bots()
    sides = Counter(p.ally for p in gentry)
    assert len(gentry) >= 4, f"豪強假人太少，測不出分邊：{len(gentry)}"
    assert set(sides) == {"guan", "huang"}, f"豪強假人全幫一邊：{dict(sides)}"
    assert abs(sides["guan"] - sides["huang"]) <= 1, dict(sides)
    assert all(p.lean_changed == 0 for p in gentry)
    assert not pressed, f"假人不該按改幫或叛投：{dict(pressed)}"
