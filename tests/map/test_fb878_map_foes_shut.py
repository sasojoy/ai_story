"""FB-878（PM 從減法季 3d 驗收接過來）：約戰開著，現在攻不了的敵方、中立區塊（跟自家領地不相連、剛易手冷卻中、被戰書凍結），輿圖地點卡
以前照舊列站在那裡的隊伍（atlas.foes）——黃巾開季站汝南學宮看潁水河畔寫「河灘潑皮 穩勝、偷網賊 有把握」，真的打進去（連上了、貼約戰）
迎戰的是守軍郡國兵，必敗。改成跟 3d 標攻的地方同一份規則：對手與勝算照貼約戰時會迎戰的守軍那一路（Game._duel_squad）；攻不了的原因、
「出陣」那一格（不標攻、不推薦）照舊。搶不下來的（大本營、廣宗）沒有守軍迎戰，照舊列站的隊伍；約戰關著的季照 3d 的規則不動。

寫法沿用 tests/test_jianfa_3d_map_foes.py：兩軍、week7／season21、開季與季中（季中另外擺一塊冷卻中、一塊被戰書凍結）。"""
from __future__ import annotations

import pytest
from duel_kit import seat
from test_jianfa_3d_map_foes import START, _setup, game_of

from tianxia import atlas, conquest, conquest_day, orders
from tianxia.engine import Game
from tianxia.state import SiegeSlot

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

# 季中多擺的兩塊（對方的、本來連得上）：一塊剛易手還在冷卻、一塊被戰書凍結。照看的那一邊挑：{看的人: (冷卻那一塊, 凍結那一塊)}
TWISTS = {"huang": ("runan_wilds", "hilltop_wilds"), "guan": ("yingchuan", "nanyang_road")}


def _world(profile: str, side: str, mid: bool):
    c, world = _setup(profile, False, mid)
    if mid:
        cool, frozen = TWISTS[side]

        def twist(season) -> None:
            season.conquest.fights[cool].flipped_at = season.time  # 剛易手：冷卻中
            other = next(s for s in conquest.SIDES if s != conquest.holder(season, c, frozen))
            season.conquest.schedule.append(SiegeSlot(
                id=f"t-{frozen}", key=season.conquest.settled_key, loc=frozen, minute=21 * 60, at=season.time + 3600,
                muster_at=season.time + 1800, attackers=[other], by={other: conquest_day.LETTER}, reasons={other: ""}))
        world.mutate_season(twist)
    seat(c, world, "甲", side, START[side])
    return c, world


def _shut(game: Game, side: str) -> dict[str, str]:
    """看的人此刻攻不了的敵方、中立區塊（不是自家的、push_problem 有原因、沒有截糧的運糧隊經過）→ 原因。"""
    c, w = game.content, game.state.world
    return {loc: why for loc in conquest.blocks(c)
            if conquest.holder(w, c, loc) != side and not orders.extra_enemies(game.state, c, loc, side)
            and (why := conquest.push_problem(w, c, side, loc, "attack")) is not None}


CASES = [pytest.param(p, s, m, id=f"{p}-{s}-{'季中' if m else '開季'}") for p in ("week7", "season21") for s in ("guan", "huang") for m in (False, True)]


@pytest.mark.parametrize(("profile", "side", "mid"), CASES)
def test_a_place_you_cannot_attack_yet_names_the_garrison_that_would_answer(profile, side, mid):
    """每一處此刻攻不了的敵方、中立區塊：卡上的對手就是守軍那一路、勝算字一樣；搶不下來的照舊列站的隊伍。出陣那一格照舊不標攻、不推薦。"""
    c, world = _world(profile, side, mid)
    game = game_of(c, world, "甲")
    state = game.map_state()
    shut = _shut(game, side)
    suggested = {r["id"] for r in state["suggest"]}
    named, kinds = 0, set()
    for loc, why in shut.items():
        info, name = state["places"].get(loc), c.locations[loc].name
        if info is None:
            continue
        assert info["sortie"] is None and loc not in suggested, f"{name}：攻不了卻標了 {info['sortie']}"
        squad = game._duel_squad(loc)
        if squad is None:  # 搶不下來（大本營、廣宗）：沒有守軍迎戰，照舊列站的隊伍
            assert why == conquest.WHY_OUT, f"{name}：{why}"
            expected = atlas.foes(c, c.locations[loc], lambda sid, at=loc: game.odds(sid, at=at), side, game.state.world)
            assert [(q["name"], q["odds"]) for q in info["squads"]] == expected, name
            continue
        word = game.odds(squad.id, at=loc)
        assert info["squads"] == [{"name": squad.name, "odds": word}], f"{name}（{why}）：守軍是 {squad.name}、卡上 {info['squads']}"
        assert info["odds"]["word"] == word, name
        named += 1
        kinds.add("cut" if why == conquest.WHY_CUT else "cool" if why.startswith("剛易手") else "frozen" if why in conquest.FROZEN_WHY.values() else why)
    assert named, "這一局一處攻不了的敵方區塊都沒有，測試沒有東西可驗"
    assert kinds >= ({"cut", "cool", "frozen"} if mid else {"cut"}), kinds


def test_fb878_yingshui_for_a_new_yellow_turban():
    """回報那一例：黃巾開季站汝南學宮，潁水河畔（官軍的、不相連）卡上寫守軍郡國兵、必敗（修前「河灘潑皮 穩勝、偷網賊 有把握」）。"""
    c, world = _world("week7", "huang", False)
    game = game_of(c, world, "甲")
    yingshui = game.map_state()["places"]["yingshui"]
    assert conquest.push_problem(game.state.world, c, "huang", "yingshui", "attack") == conquest.WHY_CUT
    assert yingshui["sortie"] is None
    assert yingshui["squads"] == [{"name": "郡國兵", "odds": "必敗"}] and yingshui["odds"] == {"word": "必敗", "tone": "risk"}


@pytest.mark.parametrize(("profile", "side"), [(p, s) for p in ("week7", "season21") for s in ("guan", "huang")])
def test_only_squads_and_odds_change_on_those_cards(profile, side, monkeypatch):
    """攻不了的那幾處只換了「此地的對手」與勝算字：拿掉這一條（那幾處 _map_foes 回 None＝修前），疊層其餘一個字不差；其他地方整份一樣。"""
    c, world = _world(profile, side, True)
    game = game_of(c, world, "甲")
    after = game.map_state()
    shut = _shut(game, side)
    real = Game._map_foes
    monkeypatch.setattr(Game, "_map_foes", lambda self, loc: None if loc in shut else real(self, loc))
    before = game_of(c, world, "甲").map_state()
    changed = set()
    for loc, info in after["places"].items():
        old = before["places"][loc]
        diff = {k for k in info if info[k] != old[k]}
        assert diff <= {"squads", "odds"}, f"{loc}：{diff}"
        if diff:
            assert loc in shut, loc
            changed.add(loc)
    assert changed, "一處都沒變：測試沒有牙"
    assert {k: v for k, v in after.items() if k != "places"} == {k: v for k, v in before.items() if k != "places"}


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_with_duels_off_the_cards_follow_3d(profile):
    """約戰關著（只關 sortie_duel）：沒有「攻不了就不標攻」那一條，卡上照 3d——標攻的照出陣擲的那一批、其餘照站的隊伍。"""
    c, world = _setup(profile, True, True)
    seat(c, world, "甲", "huang", START["huang"])
    game = game_of(c, world, "甲")
    assert not game.duel_on()
    state = game.map_state()
    for loc, info in state["places"].items():
        if info["sortie"] == "attack":
            expected = [c.squads[sid].name for sid in game._sortie_foes(c.locations[loc])]
            assert [q["name"] for q in info["squads"]] == expected, loc
        else:
            expected = atlas.foes(c, c.locations[loc], lambda sid, at=loc: game.odds(sid, at=at), "huang", game.state.world)
            assert [(q["name"], q["odds"]) for q in info["squads"]] == expected, loc
