"""三方卡與本週卡第一行（減法季整合設計 3.4、6.1、6.8；計畫 Task 3c-3，欄位表 main.sides_card、main.week_card）。

畫面只有一份：批 1 的 weekcard（main.week_card 的 sides 是兩軍態勢、main.sides_card 是三方卡 `cols`）。批 3c 的資料補在它裡面
（PM 2026-10-25：不要兩套並存）：四勝利開著時每一欄的「贏了給」照 Config.jianfa.tiers 寫、多投靠點的分鐘（join_at），豪強那一欄的
「現在」寫兩本帳，`lean` 是豪強此刻幫的那一軍，投靠了的人多 `tier_hint`（此刻就收季拿第幾階・離上一階還差多少，名次讀全服的帳），
豪強多 `ledger`；最後一週「離贏還差多少」在 week_unlock.win_gap（本週卡的 gap、輿圖天下層）。沒有另外的 main.sides、main.step。
四勝利關著、休季沒有這些補上的東西。正式內容、建 Game，整個檔標 slow。"""
from __future__ import annotations

import pytest

import server
from wins_kit import save, wins_content, wins_game
from tianxia import calendar, rules, week_unlock, weekcard, wins

pytestmark = pytest.mark.slow

KEYS = {"step", "sides", "ending"}  # 只有 ending 是批 3c 自己的鍵（休季才有）；step、sides 合進 weekcard 之後不送


def _guan(game) -> int:
    return rules.stances(game.state, game.content)["guan"]


def test_off_adds_nothing_to_the_batch_one_card():
    """四勝利關著（減法季的總開關關著）：批 1 的三方卡照舊（兩軍、贏了給是舊的那一句、沒有 lean、tier_hint、ledger、join_at）。"""
    content = wins_content()
    content.config.jianfa.enabled = False
    game = wins_game(content, faction="guan", at="changshe")
    assert game.sides_card() is None and game.ending_card() is None and game.tier_hint() is None
    view = server.main_view(game)
    assert not KEYS & set(view)
    card = view["sides_card"]
    assert set(card) == {"cols", "joined", "lean"} and card["lean"] is None
    assert [col["id"] for col in card["cols"]] == ["guan", "huang"]
    assert {col["gives"] for col in card["cols"]} == {weekcard.WIN_GIVES_OLD} and not any("join_at" in col for col in card["cols"])


def test_on_fills_the_batch_one_card():
    game = wins_game(faction="guan", at="changshe")
    view = server.main_view(game)
    assert not KEYS & set(view)  # 只有一份本週卡、一份三方卡
    assert view["week_card"]["sides"] == {"guan": _guan(game), "huang": 100 - _guan(game)}
    mine = game.sides_card()
    card = view["sides_card"]
    cols = {col["id"]: col for col in card["cols"]}
    assert set(cols) == {"guan", "huang", "haoqiang"} and card["lean"] is None  # 兩軍的人沒有「此刻幫誰」
    assert card["tier_hint"] == game.tier_hint() == "未入階・還差 40" and "ledger" not in card
    for side, col in cols.items():  # 贏了給照四階、投靠點帶分鐘（批 3c 補進批 1 的卡）
        assert col["gives"] == mine[side]["reward"] and col["join_at"] == mine[side]["join_at"]
    assert cols["haoqiang"]["now"] == mine["haoqiang"]["now"] != weekcard.HAOQIANG_NOW_PENDING
    assert cols["guan"]["now"] == f"態勢 {_guan(game)}"  # 兩軍的「現在」照批 1


def test_lean_ledger_and_hint_for_an_army_a_gentry_and_a_drifter():
    army = weekcard.sides_card(wins_game(faction="guan", at="changshe"))
    assert army["lean"] is None and "ledger" not in army and army["tier_hint"]
    gentry = wins_game(name="乙客", faction="haoqiang", ally="huang", at="haozu_fort")
    gentry.state.player.ledgers = {"guan": 12}
    card = weekcard.sides_card(gentry)
    assert (card["lean"], card["ledger"], card["tier_hint"]) == ("huang", {"guan": 12, "huang": 0}, gentry.tier_hint())
    drifter = weekcard.sides_card(wins_game(name="丙客", at="changshe"))
    assert drifter["lean"] is None and "tier_hint" not in drifter and "ledger" not in drifter


def test_tier_hint_ranks_against_everyone_saved():
    """官軍此刻領先（結局照此刻：官軍贏）：甲 100 第一階；丙 80 第三階、追平甲就進第一階（還差 20）；乙 30 還差 10 到門檻。"""
    first = save(wins_game(name="甲客", faction="guan", at="changshe"))
    first.state.player.contrib = 100
    save(first)
    third = wins_game(name="丙客", faction="guan", at="changshe", world=first.world)
    third.state.player.contrib = 80
    save(third)
    low = wins_game(name="乙客", faction="guan", at="changshe", world=first.world)
    low.state.player.contrib = 30
    assert first.tier_hint() == "第一階"
    assert third.tier_hint() == "第三階・還差 20"
    assert low.tier_hint() == "未入階・還差 10"
    low.state.player.contrib = 85  # 還沒存：照記憶體裡的這一份算
    assert low.tier_hint() == "第三階・還差 15"
    loser = wins_game(name="丁客", faction="huang", at="julu_altar", world=first.world)
    loser.state.player.contrib = 70
    assert loser.tier_hint() == "第三階"  # 輸的那一軍最高第三階
    gentry = wins_game(name="戊客", faction="haoqiang", ally="guan", at="zhuo_militia_hall", world=first.world)
    gentry.state.player.ledgers = {"guan": 70}
    assert gentry.tier_hint() == "第二階"


def test_outlook_is_the_same_rule_for_many():
    """二分搜尋的「還差多少」跟一個一個試出來的一樣（2,000 人也只重排幾次）。"""
    from tianxia.state import PlayerState

    content = wins_content()
    players = [PlayerState(name=f"g{i:04d}", location="", stats={}, stamina=0, faction="guan", contrib=1000 + i) for i in range(2000)]
    result, gap = wins.outlook(content, players, "g1000", "guan")
    assert (result.tier, result.rank) == (4, 1000)
    assert gap == 2200 - 2000  # 前 40%（800 人）最後一名是 g1200，分數 2200；追平就同名次、進第三階
    assert wins.outlook(content, players, "g1999", "guan")[1] is None


def test_sides_card_data_three_columns():
    game = wins_game(at="changshe")
    card = game.sides_card()
    assert set(card) == {"guan", "huang", "haoqiang"}
    guan = card["guan"]
    assert guan["goal"] == wins.GOAL_ARMY.format(side="官軍", other="黃巾軍", bar=85, ending="黃巾平定")
    assert card["huang"]["goal"] == wins.GOAL_ARMY.format(side="黃巾軍", other="官軍", bar=85, ending="黃天當立")
    assert "漢室忠良" in guan["reward"] and "黃天功臣" in card["huang"]["reward"] and "一方之雄" in card["haoqiang"]["reward"]
    assert [p["location"] for p in guan["join_at"]] == ["changshe", "wan_city", "luzhi_camp"]
    assert guan["join_at"][0]["minutes"] == 0 and all(p["minutes"] > 0 for p in guan["join_at"][1:])
    assert guan["now"] == f"態勢 {_guan(game)}"
    assert card["haoqiang"]["now"] == "依附官軍 0 人、依附黃巾軍 0 人"
    game.content.config.jianfa.tiers.titles["1:guan"] = "某某忠良"  # 稱號照設定寫
    assert "某某忠良" in game.sides_card()["guan"]["reward"]
    assert "某某忠良" in next(col for col in weekcard.sides_card(game)["cols"] if col["id"] == "guan")["gives"]


def test_gentry_column_shows_own_books():
    game = wins_game(faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    game.state.player.ledgers = {"guan": 120, "huang": 40}
    card = weekcard.sides_card(game)
    assert card["lean"] == "guan"
    assert next(col for col in card["cols"] if col["id"] == "haoqiang")["now"] == "你此刻幫官軍・替官軍 120、替黃巾軍 40"


def test_last_week_says_how_far_from_winning():
    """最後一週（7 天的季最後一段）：批 5 留的位子 week_unlock.win_gap 換成兩軍各自離勝利條件還差多少（本週卡的 gap、輿圖天下層同一句）；
    前面幾週沒有。"""
    game = wins_game(faction="guan", at="changshe")
    assert week_unlock.win_gap(game.state, game.content) is None
    w = game.state.world
    w.time = calendar.week_start(calendar.weeks(game.content, w), game.content, w) + 3600
    value = _guan(game)
    expected = (wins.GAP_PART.format(side="官軍", ending="黃巾平定", gap=85 - value) + "，"
                + wins.GAP_PART.format(side="黃巾", ending="黃天當立", gap=85 - (100 - value)))
    assert week_unlock.win_gap(game.state, game.content) == expected
    assert game.map_state()["gap"] == expected
    assert server.main_view(game)["week_card"]["gap"] == expected


def test_rest_season_has_none_of_it():
    game = wins_game(faction="guan", at="changshe")
    game.state.world.ended = True
    assert game.tier_hint() is None and game.sides_card() is None
