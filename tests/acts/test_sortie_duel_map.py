"""減法季批 3b 收尾：約戰開著時輿圖不畫「出陣・守」（整合設計 4.3「零風險的守拿掉」；計畫 4.0 之四）。

約戰開著的季，自家的地方出陣那一格灰著寫「等對面來約」（守就是應戰），輿圖的疊層（Game.map_state → mapdata.state）也不再給那一處
"sortie": "hold"、不在「今天去哪裡出陣」推薦它（不然推薦卡寫「出陣・守」、還寫「軍令・守城」，按下去卻貼不了）。中立地、敵方的地方照舊
是攻。子開關關著（舊出陣）自家的地方照舊是守。"""
from __future__ import annotations

import pytest

from duel_kit import LOC, duel_content, duel_world, game_of, seat
from tianxia import conquest, mapdata, orders
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _own_block(c, world, side: str) -> str:
    season = world.get_season()
    return next(loc for loc in conquest.blocks(c)
                if conquest.capturable(c, loc) and conquest.holder(season, c, loc) == side)


def _map(off: bool):
    c = duel_content(off=off)
    world = duel_world(c)
    own = _own_block(c, world, "guan")
    seat(c, world, "甲", "guan", own)
    return game_of(c, world, "甲").map_state(), own


def test_duels_on_the_map_does_not_offer_holding_at_home():
    state, own = _map(off=False)
    assert state["places"][own]["sortie"] is None
    assert own not in {row["id"] for row in state["suggest"]}
    assert state["places"][LOC]["sortie"] == "attack"  # 中立地照舊是攻（貼約戰）
    assert all(row["sortie"] != "hold" for row in state["suggest"])


def test_duels_off_the_map_still_offers_holding_at_home():
    state, own = _map(off=True)
    assert state["places"][own]["sortie"] == "hold"
    assert state["places"][LOC]["sortie"] == "attack"


# ── FB-855：約戰開著時，貼不了約戰的敵方地方（跟自家領地不相連、推不動）不標「攻」、不推薦 ──
# 輿圖的 mode() 跟貼約戰（Game.sortie_go_problem）問同一個 conquest.push_problem；有截糧的運糧隊經過的那一格照舊是攻

START = {"guan": "yingchuan_wilds", "huang": "runan_academy"}  # 潁川郊野（官軍）、汝南學宮（黃巾）：開季就站得到的出陣起點


def _attack_places(state) -> list[str]:
    return [loc for loc, info in state["places"].items() if info["sortie"] == "attack"]


def _can_post(c, world, side: str, loc: str) -> str | None:
    """把人擺到這一處，貼不了約戰的原因（貼得了是 None）；體力補滿、沒有冷卻，所以剩下的只可能是這一塊本身的原因。"""
    seat(c, world, "甲", side, loc)
    return game_of(c, world, "甲").sortie_go_problem()


@pytest.mark.parametrize("profile", ["week7", "season21"])
@pytest.mark.parametrize("side", ["guan", "huang"])
def test_every_place_the_map_calls_an_attack_can_really_post(profile, side):
    c = duel_content(profile)
    world = duel_world(c)
    seat(c, world, "甲", side, START[side])
    state = game_of(c, world, "甲").map_state()
    assert _attack_places(state), "開季總有幾處貼得了的地方"
    for loc in _attack_places(state):
        assert _can_post(c, world, side, loc) is None, f"{profile} {side}：{loc} 標了攻卻貼不了"


@pytest.mark.parametrize("profile", ["week7", "season21"])
@pytest.mark.parametrize("side", ["guan", "huang"])
def test_every_recommended_place_can_really_post_and_the_cell_is_not_grey(profile, side):
    c = duel_content(profile)
    world = duel_world(c)
    seat(c, world, "甲", side, START[side])
    rows = game_of(c, world, "甲").map_state()["suggest"]
    assert rows, "開季一個推薦都沒有"
    for row in rows:
        loc = row["id"]
        assert _can_post(c, world, side, loc) is None, f"{profile} {side}：推薦 {loc} 卻貼不了"
        option = next(o for o in game_of(c, world, "甲").options() if o.id == "act:train")
        assert option.enabled, f"{profile} {side}：推薦 {loc} 出陣那一格是灰的：{option.label}"


def test_unconnected_enemy_places_are_not_called_an_attack_while_duels_are_on():
    """修之前重現：官軍站潁川郊野，汝南學宮、汝南集市這幾處跟官軍的領地不相連，標了攻、排進推薦，站過去貼不了。"""
    c = duel_content("week7")
    world = duel_world(c)
    seat(c, world, "甲", "huang", START["huang"])
    state = game_of(c, world, "甲").map_state()
    cannot = [loc for loc in conquest.blocks(c)
              if conquest.holder(world.get_season(), c, loc) != "huang"
              and conquest.push_problem(world.get_season(), c, "huang", loc, "attack") is not None]
    assert cannot, "這一局找不到貼不了的敵方地方，測試沒有東西可驗"
    for loc in cannot:
        assert state["places"][loc]["sortie"] is None, loc
    assert not {row["id"] for row in state["suggest"]} & set(cannot)


def test_a_convoy_passing_an_unconnected_place_keeps_it_an_attack():
    """截糧的運糧隊經過的那一格，出陣照舊攻打運糧隊（_duel_option 先看運糧隊），輿圖也照舊標攻。"""
    c = duel_content("week7")
    world = duel_world(c)
    seat(c, world, "甲", "huang", START["huang"])
    season = world.get_season()
    cannot = next(loc for loc in conquest.blocks(c) if conquest.holder(season, c, loc) == "guan"
                  and conquest.push_problem(season, c, "huang", loc, "attack") is not None)
    before = game_of(c, world, "甲").map_state()
    assert before["places"][cannot]["sortie"] is None
    game = game_of(c, world, "甲")
    game.state.world.orders.append(Order(id="t:huang:intercept", template="intercept", faction="huang", week=orders.period_of(game.state, c),
                                         location=cannot, quota=4, text="（測試）"))
    state = game.map_state()
    assert state["places"][cannot]["sortie"] == "attack"
    assert cannot in {row["id"] for row in state["suggest"]}


@pytest.mark.parametrize("off", [False, True], ids=["約戰開著", "約戰關著"])
def test_a_passing_convoy_marks_only_its_place_and_only_with_duels_on(off):
    """FB-9005：輿圖那一處的 convoy 旗（網頁卡的鈕寫「出陣・截糧」、不掛攻的勝算）只在約戰開著、出陣標攻、運糧隊正打那裡經過時有；
    沒有運糧隊、約戰關著（舊出陣照舊攻打駐軍與運糧隊擲一路）整份疊層一個鍵都不多。"""
    c = duel_content("week7", off=off)
    world = duel_world(c)
    seat(c, world, "甲", "guan", LOC)
    game = game_of(c, world, "甲")
    assert all("convoy" not in info for info in game.map_state()["places"].values())
    game.state.world.orders.append(Order(id="t:guan:intercept", template="intercept", faction="guan", week=orders.period_of(game.state, c),
                                         location=LOC, quota=4, text="（測試）"))
    state = game.map_state()
    flagged = [loc for loc, info in state["places"].items() if "convoy" in info]
    assert flagged == ([] if off else [LOC])
    assert state["places"][LOC]["sortie"] == "attack"  # 輿圖照舊標攻（只換了鈕上的字）
    own = _own_block(c, world, "guan")  # 自家的地方運糧隊經過：有運糧隊可打就照舊標攻（出陣那一格也是「出陣・截糧」），旗跟著在
    game.state.world.orders.append(Order(id="t:guan:intercept2", template="intercept", faction="guan", week=orders.period_of(game.state, c),
                                         location=own, quota=4, text="（測試）"))
    state = game.map_state()
    assert state["places"][own]["sortie"] == "attack" and state["places"][own].get("convoy") is (None if off else True)


def test_only_the_places_marked_attack_get_the_convoy_flag():
    """mapdata.state 的契約：convoy 是「運糧隊正打那裡經過」的判斷，旗只給出陣標攻的地方（不標攻的地方沒有那顆鈕，旗沒有用處、也不多一個鍵）。"""
    c = duel_content("week7")
    world = duel_world(c)
    seat(c, world, "甲", "guan", LOC)
    game = game_of(c, world, "甲")
    quiet = {loc for i, loc in enumerate(c.locations) if i % 2}
    state = mapdata.state(game.state, c, odds=game.odds, sortie_mode=lambda loc: None if loc in quiet else "attack", sorties_left=2,
                          real_minutes=game._real_minutes, convoy=lambda loc: True)
    flagged = {loc for loc, info in state["places"].items() if "convoy" in info}
    assert flagged == {loc for loc, info in state["places"].items() if info["sortie"] == "attack"} and flagged and flagged.isdisjoint(quiet)


@pytest.mark.parametrize("side", ["guan", "huang"])
def test_duels_off_keeps_the_old_attack_marks_on_unconnected_places(side):
    """子開關關著（舊出陣）：不相連的敵方地方照舊標攻（打贏拿戰利、不推進度），輿圖一個字不變。"""
    c = duel_content("week7", off=True)
    world = duel_world(c)
    seat(c, world, "甲", side, START[side])
    state = game_of(c, world, "甲").map_state()
    season = world.get_season()
    unconnected = [loc for loc in conquest.blocks(c) if conquest.holder(season, c, loc) not in (side, None)
                   and conquest.push_problem(season, c, side, loc, "attack") is not None
                   and state["places"][loc]["sortie"] == "attack"]
    assert unconnected, "舊出陣下，不相連的敵方地方應該還是攻"
