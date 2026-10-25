"""本週卡第一行與三方卡（減法季整合設計 3.4、6.1、6.8；計畫 Task 3c-3，欄位表 main.sides、main.sides_card）。

main.sides：兩軍此刻的態勢、自己是哪一方；豪強另有此刻幫誰與兩本帳；投靠了的人有 tier_hint（此刻就收季拿第幾階・離上一階還差多少，
名次讀全服的帳）。main.sides_card：三方各自的要做到、贏了給（稱號與比例照 Config.jianfa.tiers）、投靠在哪（現實幾分鐘）、現在
（最後一週接「離贏還差多少」）。四勝利關著、休季沒有這些鍵。正式內容、建 Game，整個檔標 slow。"""
from __future__ import annotations

import pytest

import server
from wins_kit import save, wins_content, wins_game
from tianxia import calendar, wins

pytestmark = pytest.mark.slow

KEYS = {"step", "sides", "sides_card", "ending"}


def test_off_sends_none_of_the_keys():
    """four_wins 關著：本週卡「你這一步」、第一行、三方卡、結局卡都沒有；總開關關著也一樣。"""
    game = wins_game(wins_content(off=True), faction="guan", at="changshe")
    assert game.sides() is None and game.sides_card() is None and game.ending_card() is None and game.step_view() is None
    assert not KEYS & set(server.main_view(game))
    content = wins_content()
    content.config.jianfa.enabled = False
    plain = wins_game(content, name="乙客", faction="guan", at="changshe")
    assert not KEYS & set(server.main_view(plain))


def test_on_sends_the_keys():
    game = wins_game(faction="guan", at="changshe")
    view = server.main_view(game)
    assert {"sides", "sides_card"} <= set(view) and "ending" not in view
    assert view["sides"] == game.sides() and view["sides_card"] == game.sides_card()


def test_sides_for_an_army_a_gentry_and_a_drifter():
    army = wins_game(faction="guan", at="changshe")
    sides = army.sides()
    assert set(sides) == {"guan", "huang", "mine", "tier_hint"}
    assert sides["guan"] + sides["huang"] == 100 and sides["mine"] == "guan"
    gentry = wins_game(name="乙客", faction="haoqiang", ally="huang", at="haozu_fort")
    gentry.state.player.ledgers = {"guan": 12}
    sides = gentry.sides()
    assert (sides["mine"], sides["lean"], sides["ledger"]) == ("haoqiang", "huang", {"guan": 12, "huang": 0})
    drifter = wins_game(name="丙客", at="changshe")
    assert set(drifter.sides()) == {"guan", "huang", "mine"} and drifter.sides()["mine"] is None


def test_tier_hint_ranks_against_everyone_saved():
    """官軍此刻領先（結局照此刻：官軍贏）：甲 100 第一階；丙 80 第三階、追平甲就進第一階（還差 20）；乙 50 還差 10 到門檻。"""
    first = save(wins_game(name="甲客", faction="guan", at="changshe"))
    first.state.player.contrib = 100
    save(first)
    third = wins_game(name="丙客", faction="guan", at="changshe", world=first.world)
    third.state.player.contrib = 80
    save(third)
    low = wins_game(name="乙客", faction="guan", at="changshe", world=first.world)
    low.state.player.contrib = 50
    assert first.sides()["tier_hint"] == "第一階"
    assert third.sides()["tier_hint"] == "第三階・還差 20"
    assert low.sides()["tier_hint"] == "未入階・還差 10"
    low.state.player.contrib = 85  # 還沒存：照記憶體裡的這一份算
    assert low.sides()["tier_hint"] == "第三階・還差 15"
    loser = wins_game(name="丁客", faction="huang", at="julu_altar", world=first.world)
    loser.state.player.contrib = 70
    assert loser.sides()["tier_hint"] == "第三階"  # 輸的那一軍最高第三階
    gentry = wins_game(name="戊客", faction="haoqiang", ally="guan", at="zhuo_militia_hall", world=first.world)
    gentry.state.player.ledgers = {"guan": 70}
    assert gentry.sides()["tier_hint"] == "第二階"


def test_outlook_is_the_same_rule_for_many():
    """二分搜尋的「還差多少」跟一個一個試出來的一樣（2,000 人也只重排幾次）。"""
    from tianxia.state import PlayerState

    content = wins_content()
    players = [PlayerState(name=f"g{i:04d}", location="", stats={}, stamina=0, faction="guan", contrib=1000 + i) for i in range(2000)]
    result, gap = wins.outlook(content, players, "g1000", "guan")
    assert (result.tier, result.rank) == (4, 1000)
    assert gap == 2200 - 2000  # 前 40%（800 人）最後一名是 g1200，分數 2200；追平就同名次、進第三階
    assert wins.outlook(content, players, "g1999", "guan")[1] is None


def test_sides_card_three_columns():
    game = wins_game(at="changshe")
    card = game.sides_card()
    assert set(card) == {"guan", "huang", "haoqiang"}
    guan = card["guan"]
    assert guan["goal"] == wins.GOAL_ARMY.format(side="官軍", other="黃巾軍", bar=85, ending="黃巾平定")
    assert card["huang"]["goal"] == wins.GOAL_ARMY.format(side="黃巾軍", other="官軍", bar=85, ending="黃天當立")
    assert "漢室忠良" in guan["reward"] and "黃天功臣" in card["huang"]["reward"] and "一方之雄" in card["haoqiang"]["reward"]
    assert [p["location"] for p in guan["join_at"]] == ["changshe", "wan_city", "luzhi_camp"]
    assert guan["join_at"][0]["minutes"] == 0 and all(p["minutes"] > 0 for p in guan["join_at"][1:])
    assert guan["now"] == f"態勢 {game.sides()['guan']}"
    assert card["haoqiang"]["now"] == "依附官軍 0 人、依附黃巾軍 0 人"
    game.content.config.jianfa.tiers.titles["1:guan"] = "某某忠良"  # 稱號照設定寫
    assert "某某忠良" in game.sides_card()["guan"]["reward"]


def test_sides_card_gentry_now_shows_own_books():
    game = wins_game(faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    game.state.player.ledgers = {"guan": 120, "huang": 40}
    assert game.sides_card()["haoqiang"]["now"] == "你此刻幫官軍・替官軍 120、替黃巾軍 40"


def test_last_week_says_how_far_from_winning():
    game = wins_game(faction="guan", at="changshe")
    assert "還差" not in game.sides_card()["guan"]["now"]
    w = game.state.world
    w.time = calendar.week_start(calendar.weeks(game.content, w), game.content, w) + 3600
    value = game.sides()["guan"]
    assert game.sides_card()["guan"]["now"] == f"態勢 {value}・" + wins.NOW_GAP.format(ending="黃巾平定", gap=85 - value)
    assert game.sides_card()["huang"]["now"].endswith(wins.NOW_GAP.format(ending="黃天當立", gap=85 - (100 - value)))


def test_rest_season_has_no_sides():
    game = wins_game(faction="guan", at="changshe")
    game.state.world.ended = True
    assert game.sides() is None and game.sides_card() is None
