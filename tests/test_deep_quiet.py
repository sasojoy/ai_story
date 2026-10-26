"""減法季批 7d：深交那兩句不給玩家看（企劃者 2026-10-26：「『不傳看家本領』和『情誼停在 69』這兩句，不給玩家看」；FB-869）。

玩家看得到的地方——回給玩家的訊息、GameState.log、江湖紀錄（含見聞→紀錄的「深交」那一則）、行狀、戰報、江湖畫面——
都不再出現「你已深交三位人物，某某的情誼停在 69。」與「某某把你當作知己，卻不打算把看家本領交出來。」；規則照舊在背後運作
（沒買名額的第四位照樣夾在 69、靠名額深交的照樣不教本命武學、不送本命兵器）。對話畫面名字旁的「情誼 69・已深交三位」
（Game.affinity_text）企劃者沒說拿掉，先留著。玩法說明補一句「最多深交幾位」（數字讀 Config，zhuan_end 關著的季沒有）。
"""
from __future__ import annotations

import json

import pytest
from test_deep_cap import _game, _set, _talk

import server
from jianfa_kit import jianfa_game, plain_game, ready
from tianxia import zhuan_end
from tianxia.characters import name_key
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow

LIST3 = {"zhujun": 80, "huangfusong": 72, "luzhi": 70}
ARM3 = {"liubei": 82, "guanyu": 81, "zhangfei": 80}
# 兩句的字（任何一句出現在玩家看得到的地方都算漏）
BANNED = ("看家本領", "把你當作知己", "你已深交", "情誼停在", "停在 69", "停在 六十九")


def _hits(texts) -> list[str]:
    return [t[:60] for t in texts if any(word in t for word in BANNED)]


def _buy_slot(game, tag: str) -> None:
    wallet = Wallet(game.world.db)
    wallet.post(name_key(game.state.player.name), 1000, "grant", f"test:{tag}", time=game.now)
    assert game.mall_buy("deep_slot", tag)[0].startswith("買下")


def _everything(game, said: list[str]) -> list[str]:
    """玩家看得到的一切：這一路回給他的訊息、log、江湖紀錄每一則、行狀、戰報、整份存檔、江湖畫面、紀錄頁、行狀頁。"""
    s = game.state
    seen = list(said) + list(s.log)
    seen += [e.model_dump_json() for e in s.journal]
    seen += [e.model_dump_json() for e in s.player.annals]
    seen += [b.model_dump_json() for b in s.battles]
    seen.append(s.model_dump_json())
    seen.append(game.journal_html(1, 500))
    seen.append(json.dumps(game.annals_view(), ensure_ascii=False, default=str))
    seen.append(json.dumps(server.main_view(game), ensure_ascii=False, default=str))
    return seen


# ── 掃描：兩句不出現在玩家看得到的任何地方，規則照舊 ──


def test_the_capped_fourth_says_nothing_anywhere_and_still_stops_short():
    """沒買名額：第四位在同步、一輪對話、一個動作裡都被夾在 69（規則不變），可是哪裡都沒有那一句，也沒有「深交」那一則紀錄。"""
    game = _game()
    p = game.state.player
    said: list[str] = []
    _set(game, LIST3)
    said += game.sync(game.now)
    _set(game, {"caocao": 74})
    said += game.sync(game.now)
    assert p.affinities["caocao"] == 69  # 規則照舊
    p.affinities["liubei"] = 69
    said += _talk(game, "liubei")
    assert p.affinities["liubei"] == 69 and "學會本命:liubei" not in p.flags
    p.affinities["caocao"] = 90
    said += game.choose("act:explore")
    assert p.affinities["caocao"] == 69 and "caocao" not in game.state.world.signature_arms
    assert p.deep_order == list(LIST3)
    assert game.affinity_text("caocao") == "情誼 69・已深交三位"  # 對話畫面名字旁的標記先留著（企劃者沒說拿掉）
    assert not any(e.title == "深交" for e in game.state.journal)
    assert _hits(_everything(game, said)) == []


def test_a_bought_slot_figure_is_let_in_quietly_and_still_gives_nothing():
    """買了名額：第四位進名單、情誼照長，不教本命武學、不送本命兵器（規則不變），可是不再說「不打算把看家本領交出來」；第五位照樣夾在 69。"""
    game = _game()
    p = game.state.player
    said: list[str] = []
    _set(game, ARM3)
    said += game.sync(game.now)
    _buy_slot(game, "deep-7d")
    p.affinities["caocao"] = 69
    arts = set(p.arts)
    said += _talk(game, "caocao")
    assert p.deep_order == [*ARM3, "caocao"] and p.affinities["caocao"] >= 70
    assert "學會本命:caocao" not in p.flags and set(p.arts) == arts
    said += _talk(game, "caocao")
    p.affinities["caocao"] = 85
    said += game.choose("act:explore")
    assert "caocao" not in game.state.world.signature_arms and p.affinities["caocao"] == 85
    p.affinities["zhujun"] = 75  # 第五位：名額只有一張，照樣夾在 69
    said += game.sync(game.now)
    assert p.affinities["zhujun"] == 69 and "zhujun" not in p.deep_order
    assert not any(e.title == "深交" for e in game.state.journal)
    assert _hits(_everything(game, said)) == []


def test_a_slot_figure_with_nothing_to_give_is_let_in_quietly_too():
    game = _game()
    s, c = game.state, game.content
    arm_owners = {arm.character for arm in c.gear.signature_arms}
    from tianxia.tactics import figure_arts

    bare = next(cid for cid, ch in c.characters.items() if cid not in arm_owners and not figure_arts(c, ch))
    _set(game, LIST3)
    game.sync(game.now)
    _buy_slot(game, "deep-7d-bare")
    _set(game, {bare: 75})
    said = game.sync(game.now)
    assert s.player.deep_order[-1] == bare and s.player.affinities[bare] == 75
    assert _hits(_everything(game, said)) == []


def test_the_scan_has_teeth():
    """掃描抓得到：兩句原文放進哪個字串都會被點名。"""
    assert _hits(["你已深交三位人物，曹操的情誼停在 69。"]) and _hits(["曹操把你當作知己，卻不打算把看家本領交出來。"])
    assert not _hits(["情誼 69・已深交三位", "曹操把本命武學傳給了你。"])


def test_the_pure_rule_names_who_was_stopped_and_says_nothing():
    """enforce_deep_cap 只回被夾住的人物 id（不是句子）；沒有給玩家看的句子常數了。"""
    game = _game()
    s, c = game.state, game.content
    _set(game, LIST3)
    assert zhuan_end.enforce_deep_cap(s, c) == []
    _set(game, {"caocao": 75})
    assert zhuan_end.enforce_deep_cap(s, c) == ["caocao"] and s.player.affinities["caocao"] == 69
    _set(game, {"caocao": 75})
    assert zhuan_end.enforce_deep_cap(s, c, slots=1) == [] and s.player.affinities["caocao"] == 75
    for name in ("DEEP_FULL", "DEEP_KEEP", "DEEP_TITLE"):
        assert not hasattr(zhuan_end, name), name


def test_off_nothing_changes_for_the_slot_and_the_cap():
    """子開關關著：沒有上限、沒有紀錄（跟以前一樣）。"""
    game = _game(zhuan_end=False)
    _set(game, {**LIST3, "caocao": 75})
    said = game.sync(game.now)
    assert game.state.player.affinities["caocao"] == 75
    assert _hits(_everything(game, said)) == []


# ── 玩法說明：最多深交幾位 ──


def _deep_line(text: str) -> list[str]:
    return [line for line in text.splitlines() if "深交" in line]


def test_the_howto_says_the_most_deep_friends_when_the_season_has_it():
    for profile in ("season21", "week7"):
        game = jianfa_game(profile)
        n = game.content.config.jianfa.deep_figures
        lines = _deep_line(game.howto_text())
        assert len(lines) == 1, (profile, lines)
        assert f"最多同時深交 {n} 位" in lines[0] and f"第 {n + 1} 位起情誼不再往上加" in lines[0] and "深交名額" in lines[0]
        assert not any(word in lines[0] for word in BANNED)  # 只講規則本身，不帶出那兩句
        assert "停在" not in lines[0] and "69" not in lines[0]
        assert game.howto_text().index(lines[0]) > game.howto_text().index("#### 情誼")  # 在「情誼」那一節


def test_the_howto_reads_the_number_from_config():
    game = jianfa_game("season21")
    game.content.config.jianfa.deep_figures = 5
    assert "最多同時深交 5 位" in game.howto_text() and "第 6 位起" in game.howto_text()
    game.content.config.signature_affinity = 60
    assert "情誼到 60" in _deep_line(game.howto_text())[0]


def test_the_howto_is_silent_when_the_season_does_not_have_it():
    assert _deep_line(jianfa_game("season21", zhuan_end=False).howto_text()) == []
    assert _deep_line(plain_game("season21").howto_text()) == []
    assert _deep_line(plain_game("week7").howto_text()) == []
    weekend = ready(plain_game("weekend"))
    assert _deep_line(weekend.howto_text()) == []
