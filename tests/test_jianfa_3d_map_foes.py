"""減法季 3d（FB-858）：輿圖地點卡的對手與勝算，照「出陣真的會打的那一路」算。

修之前（QA 複驗 3b 修正輪）：黃巾新角色站汝南學宮，輿圖推薦第一是涿郡、沒有勝算字，地點卡寫「此地的對手 沒有對手」，
實際在那裡出陣打的是官軍的守軍（官軍的城沒有官軍的隊伍站著時，conquest.sortie_foes 退回 Scenario.territory.side_garrison：
官軍巡騎、郡國兵），必敗。輿圖走 atlas.foes → territory.squads_at，算不到這個退回；約戰關著（只關 sortie_duel）同一個缺口早就在
（標攻卻沒有勝算字的有 14 處），有的地方甚至寫了勝算字、卻是別的隊伍的（潁水河畔寫「有把握」，出陣鈕寫「必敗」）。

不變量（開季、季中；week7、season21；兩軍；約戰開、只關 sortie_duel）：地點卡標「攻」的每一處
- 列得出對手、有勝算字，勝算字是列出來那幾路裡最險的；
- 勝算跟站過去按出陣的結果一致：約戰關著對鈕上寫的（_train_note），約戰開著對貼約戰時抄進去的守軍（Game._duel_squad）；
- 不在爭奪之列的地方（自家的、大本營、不是區塊）照舊。"""
from __future__ import annotations

import re

import pytest

from duel_kit import MOVES, NOW, duel_content, duel_world, game_of, seat
from tianxia import atlas, conquest, mapdata, orders
from tianxia.characters import CharacterStore
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

START = {"guan": "yingchuan_wilds", "huang": "runan_academy"}  # 潁川郊野（官軍）、汝南學宮（黃巾）：開季就站得到的出陣起點
# 季中：兩邊各拿下幾塊（含官軍的城被黃巾拿下、中立地被官軍拿下），冷卻都過了
MID = [("runan_wilds", "guan"), ("nanyang_road", "huang"), ("yingchuan", "huang"), ("hilltop_wilds", "guan")]
WORDS = atlas.ODDS_ORDER
ODDS_AT_END = re.compile(r"・([^・（）]+)）$")


def _setup(profile: str, off: bool, mid: bool):
    c = duel_content(profile, off=off)
    world = duel_world(c)
    if mid:
        def play(season) -> None:
            for loc, side in MID:
                assert loc in conquest.blocks(c) and conquest.capturable(c, loc), loc
                conquest.flip(season, c, loc, side, note=False)
                season.conquest.fights[loc].flipped_at = season.time - 10**8  # 冷卻過了
        world.mutate_season(play)
    return c, world


def _attacks(state) -> list[str]:
    return [loc for loc, info in state["places"].items() if info["sortie"] == "attack"]


def _worst(squads: list[dict]) -> str:
    return max((q["odds"] for q in squads if q["odds"] != atlas.DRILL), key=WORDS.index)


def _stand(c, world, side: str, loc: str, now: float = NOW):
    """人站到這一處、體力補滿、出陣次數與冷卻清掉（同一條測試站過去好幾處），回那一份 Game。"""
    seat(c, world, "甲", side, loc)
    store = CharacterStore(world.db)
    state = store.load("甲")
    state.player.sorties_today, state.player.sortie_cooldown_until = 0, None
    store.save(state)
    return game_of(c, world, "甲", now)


CASES = [
    pytest.param(profile, side, off, mid, id=f"{profile}-{side}-{'只關約戰' if off else '約戰開'}-{'季中' if mid else '開季'}")
    for profile in ("week7", "season21") for side in ("guan", "huang") for off in (False, True) for mid in (False, True)
]


@pytest.mark.parametrize(("profile", "side", "off", "mid"), CASES)
def test_every_attack_place_lists_its_foes_with_an_odds_word(profile, side, off, mid):
    """修之前：標攻沒有勝算字開季就有（約戰開：涿郡；只關約戰：官軍 5 處、黃巾 9 處）。"""
    c, world = _setup(profile, off, mid)
    seat(c, world, "甲", side, START[side])
    state = game_of(c, world, "甲").map_state()
    attacks = _attacks(state)
    assert attacks, "這一局一處都沒標攻，測試沒有東西可驗"
    for loc in attacks:
        info = state["places"][loc]
        name = c.locations[loc].name
        assert info["squads"], f"{name}：標了攻、卡上卻沒有對手"
        assert info["odds"] is not None, f"{name}：標了攻、卻沒有勝算字"
        assert all(q["odds"] in WORDS for q in info["squads"]), f"{name}：有一路對手沒有勝算字 {info['squads']}"
        assert info["odds"]["word"] == _worst(info["squads"]), name
        assert not any(q["odds"] == atlas.DRILL for q in info["squads"]), f"{name}：攻打的對手不會是自己人 {info['squads']}"


@pytest.mark.parametrize(("profile", "side", "mid"), [(p, s, m) for p in ("week7", "season21") for s in ("guan", "huang") for m in (False, True)])
def test_odds_on_the_card_match_the_button_when_duels_are_off(profile, side, mid):
    """約戰關著（舊出陣）：站過去，出陣鈕上寫的對手與勝算（_train_note）跟地點卡一致。修之前潁水河畔卡上寫「有把握」、鈕上寫「必敗」。"""
    c, world = _setup(profile, True, mid)
    seat(c, world, "甲", side, START[side])
    state = game_of(c, world, "甲").map_state()
    for loc in _attacks(state):
        info, name = state["places"][loc], c.locations[loc].name
        option = next(o for o in _stand(c, world, side, loc).options() if o.id == "act:train")
        word = ODDS_AT_END.search(option.label)
        assert word is not None, f"{name}：出陣鈕上沒有勝算 {option.label}"
        assert word.group(1) == info["odds"]["word"], f"{name}：鈕上 {option.label}、卡上 {info['squads']}"
        if len(info["squads"]) == 1:
            assert f"・{info['squads'][0]['name']}・" in option.label, f"{name}：鈕上 {option.label}、卡上 {info['squads']}"
        else:
            assert f"{len(info['squads'])} 路對手" in option.label, f"{name}：鈕上 {option.label}、卡上 {info['squads']}"


@pytest.mark.parametrize(("profile", "side", "mid"), [(p, s, m) for p in ("week7", "season21") for s in ("guan", "huang") for m in (False, True)])
def test_odds_on_the_card_match_the_garrison_that_answers_when_duels_are_on(profile, side, mid):
    """約戰開著：站過去貼約戰，抄進去的守軍（SortieDuel.report["squad"]，Game._duel_squad 挑的那一路）就是卡上寫的那一路、勝算字一樣。"""
    c, world = _setup(profile, False, mid)
    seat(c, world, "甲", side, START[side])
    state = game_of(c, world, "甲").map_state()
    for i, loc in enumerate(_attacks(state)):
        info, name = state["places"][loc], c.locations[loc].name
        now = NOW + 7 * i  # 約戰 id 照貼的那一刻，一處一個
        game = _stand(c, world, side, loc, now)
        assert game.sortie_go_problem() is None, f"{name}：標了攻卻貼不了"
        game.sortie_go(MOVES)
        game._save_season()
        duel = next(d for d in world.sortie_duels().values() if d.block == loc)
        squad = c.squads[duel.report["squad"]]
        assert [q["name"] for q in info["squads"]] == [squad.name], f"{name}：守軍是 {squad.name}、卡上 {info['squads']}"
        assert info["odds"]["word"] == game.odds(squad.id, at=loc), name


# ── 涿郡那一例（FB-858 原文）──

def test_fb858_zhuo_county_names_the_garrison_and_is_marked_a_sure_loss_while_duels_are_on():
    c, world = _setup("week7", False, False)
    seat(c, world, "甲", "huang", START["huang"])
    state = game_of(c, world, "甲").map_state()
    zhuo = state["places"]["zhuo_county"]
    assert zhuo["sortie"] == "attack"
    assert zhuo["squads"] == [{"name": "郡國兵", "odds": "必敗"}]  # 修前 []：「此地的對手 沒有對手」
    assert zhuo["odds"] == {"word": "必敗", "tone": "risk"}
    rows = state["suggest"]
    assert all(r["lose"] for r in rows)  # 新手開季，推薦的三處都是必敗（企劃者 10/26 說先不用動）
    assert "zhuo_county" not in [r["id"] for r in rows]  # 修前：沒有勝算字的涿郡不算必敗，排第一（步行 38 分也蓋不掉）；現在照必敗排，路遠掉出前三


def test_fb858_zhuo_county_lists_both_garrison_squads_while_duels_are_off():
    c, world = _setup("week7", True, False)
    seat(c, world, "甲", "huang", START["huang"])
    zhuo = game_of(c, world, "甲").map_state()["places"]["zhuo_county"]
    assert {q["name"] for q in zhuo["squads"]} == {"官軍巡騎", "郡國兵"} and zhuo["odds"]["word"] == "必敗"


# ── 照舊的地方 ──

@pytest.mark.parametrize("off", [False, True], ids=["約戰開", "只關約戰"])
def test_places_that_are_not_attacks_keep_the_old_listing(off):
    """不是攻的地方（自家的守、不在爭奪之列、搶不下來）一個字不變：對手照 atlas.foes（站的隊伍，自己人寫操練）。"""
    c, world = _setup("week7", off, True)
    seat(c, world, "甲", "guan", START["guan"])
    game = game_of(c, world, "甲")
    state = game.map_state()
    kept = 0
    season = game.state.world
    for loc, info in state["places"].items():
        if info["sortie"] == "attack":
            continue
        # FB-878（PM 2026-10-26）：約戰開著、此刻攻不了的敵方與中立區塊（不相連、冷卻、戰書凍結）改列守軍那一路，新規則在
        # tests/test_fb878_map_foes_shut.py；這裡只守其餘照舊（自家的、不在爭奪之列、搶不下來的）
        if not off and loc in conquest.blocks(c) and conquest.holder(season, c, loc) != "guan" and game._duel_squad(loc) is not None \
                and conquest.push_problem(season, c, "guan", loc, "attack") is not None:
            continue
        expected = atlas.foes(c, c.locations[loc], lambda sid, at=loc: game.odds(sid, at=at), "guan", game.state.world)
        assert [(q["name"], q["odds"]) for q in info["squads"]] == expected, loc
        kept += 1
    assert kept > 20


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_with_conquest_off_the_map_listing_is_the_old_one(profile):
    """領地爭奪關著的季：地點卡的對手一處都不改——掛鉤處處回 None，每一處的 squads 就是 atlas.foes（站的隊伍）加上截糧的運糧隊。"""
    from conftest import no_conquest, real_content
    from conquest_kit import _new, go, join

    game = go(join(_new(no_conquest(real_content(profile)), "沈浪"), "guan"), "yingchuan_wilds")
    c = game.content
    assert not conquest.on(c, game.state.world)
    assert all(game._map_foes(loc) is None for loc in c.locations)
    state = game.map_state()
    assert any(info["sortie"] == "attack" for info in state["places"].values())
    for loc, info in state["places"].items():
        expected = atlas.foes(c, c.locations[loc], lambda sid, at=loc: game.odds(sid, at=at), "guan", game.state.world)
        assert [(q["name"], q["odds"]) for q in info["squads"]] == expected, loc


def test_a_scattered_player_keeps_the_old_listing():
    """散人不出陣：沒有「攻」，掛鉤回 None，卡上照舊。"""
    c, world = _setup("week7", False, False)
    seat(c, world, "甲", None, "runan_wilds")
    game = game_of(c, world, "甲")
    assert all(game._map_foes(loc) is None for loc in c.locations)


# ── 截糧的運糧隊 ──

def _with_convoy(c, world, side: str, loc: str):
    """黃巾（或官軍）這週在 loc 掛一道截糧，運糧隊就是 loc 的對手之一。"""
    game = game_of(c, world, "甲")
    game.state.world.orders.append(Order(id=f"t:{side}:intercept", template="intercept", faction=side, week=orders.period_of(game.state, c),
                                         location=loc, quota=4, text="（測試）"))
    return game


@pytest.mark.parametrize("capturable", [False, True], ids=["搶不下來的大本營", "搶得下來的區塊"])
def test_a_convoy_is_the_only_foe_the_duel_button_attacks(capturable):
    """約戰開著：運糧隊正打那裡經過的，出陣那一格照舊攻打運糧隊（_duel_entry），卡上寫運糧隊、勝算字是運糧隊的（修前連駐軍一起列）。"""
    c, world = _setup("week7", False, False)
    seat(c, world, "甲", "huang", START["huang"])
    season = world.get_season()
    cannot = next(loc for loc in conquest.blocks(c) if conquest.holder(season, c, loc) == "guan"
                  and conquest.capturable(c, loc) == capturable and conquest.push_problem(season, c, "huang", loc, "attack") is not None)
    game = _with_convoy(c, world, "huang", cannot)
    convoy = c.squads[c.orders.convoy_squads["guan"]]
    info = game.map_state()["places"][cannot]
    assert info["sortie"] == "attack"
    assert info["squads"] == [{"name": convoy.name, "odds": game.odds(convoy.id, at=cannot)}]


def test_a_convoy_joins_the_garrison_when_duels_are_off():
    """約戰關著：出陣照舊從駐軍與運糧隊裡擲一路（Game._sortie_foes），卡上兩邊都列。"""
    c, world = _setup("week7", True, False)
    seat(c, world, "甲", "huang", START["huang"])
    season = world.get_season()
    spot = next(loc for loc in conquest.blocks(c) if conquest.holder(season, c, loc) == "guan" and conquest.capturable(c, loc))
    game = _with_convoy(c, world, "huang", spot)
    convoy = c.squads[c.orders.convoy_squads["guan"]]
    names = [q["name"] for q in game.map_state()["places"][spot]["squads"]]
    expected = [c.squads[sid].name for sid in game._sortie_foes(c.locations[spot])]
    assert convoy.name in names and names == expected


# ── 推薦排序照舊的規則 ──

def test_suggestion_order_follows_the_existing_rule_once_the_odds_are_there():
    """有勝算字之後涿郡自然照必敗排（排在有把握的後面、跟別的必敗並列時照分數），排序的規則本身沒動。"""
    c, world = _setup("week7", False, False)
    seat(c, world, "甲", "huang", START["huang"])
    game = game_of(c, world, "甲")
    state = game.map_state()
    rows = state["suggest"]
    for a, b in zip(rows, rows[1:]):  # 既有的規則：打得過的在前、必敗的在後，同一類照分數高的在前
        assert (a["lose"], -a["score"]) <= (b["lose"], -b["score"])
    assert mapdata.rank_suggestions(rows) == rows  # 排好的再排一次不動
    zhuo = state["places"]["zhuo_county"]
    assert zhuo["odds"]["word"] == "必敗" and zhuo["minutes"] > max(r["minutes"] for r in rows)  # 比被推薦的三處都遠，又是必敗：掉出前三
