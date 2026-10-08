"""玩法說明二（explain-2，FB-100：QA 用完全不懂的新玩家角度玩 20 分鐘，說明告訴了「這一下會怎樣」，還沒告訴「為什麼要這樣做、目標是什麼」）。

一、點戰況圖卡、態勢、大事、主線看的說明（status.war_help，句子在 tianxia/howto.py）：這一季在打什麼、亂局與割據、大事怎麼定、
    你能怎麼出力。門檻讀設定、此刻在亂局的讀 rules.chaos_fronts、大事的件數讀時刻表、擲骰的上下限讀 timetable 的常數。
句子待 joy 潤；這裡驗的是「說的跟規則一樣」：設定改了、時刻表改了，字跟著變。"""
from __future__ import annotations

import random

import pytest

from tianxia import howto, rules, timetable
from tianxia.engine import Game


def _war(content, name="甲"):
    return Game.new(content, name, rng=random.Random(0))


# ── 一、點戰況、態勢、大事、主線 ─────────────────────────────────────


def test_each_war_element_has_its_explanation_in_season_one(on):
    help_ = _war(on).status_data()["war_help"]
    assert set(help_) == {"stance", "fronts", "board", "quest"}
    assert all(help_[k] and all(isinstance(line, str) and line for line in help_[k]) for k in help_)
    stance = "".join(help_["stance"])
    assert f"這一季是{on.scenario.name}" in stance and "潁川汝南、南陽、冀州" in stance and "割據" in stance  # 在打什麼、割據
    assert "亂局" in "".join(help_["fronts"]) and "0 是官軍穩控、100 是黃巾控制" in help_["fronts"][0]  # 三條戰線與亂局帶
    board = "".join(help_["board"])
    assert "看戰況擲骰" in board and "史書寫定" in board and "決戰" in board and "關鍵伏筆" in board  # 大事怎麼定：戰況、伏筆、寫定的
    quest = "".join(help_["quest"])
    assert "遊歷" in quest and "軍令" in quest and "伏筆" in quest  # 你能怎麼出力


def test_no_war_explanations_outside_season_one(real):
    """開關關著（beta 那一季）：沒有戰況、態勢，也沒有它們的說明，畫面照舊。"""
    data = _war(real).status_data()
    assert "war_help" not in data and "fronts" not in data


def test_the_chaos_band_in_the_explanations_follows_the_config(on):
    game = _war(on)
    assert "戰況 35～65" in game.status_data()["war_help"]["stance"][1]
    on.config.chaos_low, on.config.chaos_high = 30, 70
    help_ = game.status_data()["war_help"]
    assert "戰況 30～70" in help_["stance"][1] and "落在 30～70 是亂局" in help_["fronts"][0]
    assert "35" not in "".join(help_["stance"] + help_["fronts"])


def test_the_fronts_explanation_names_the_fronts_in_chaos_from_the_rule(on):
    """此刻哪幾條在亂局讀 rules.chaos_fronts（圖卡上的「亂局」標、割據的漲落讀的也是它）；門檻一改，名單跟著變。"""
    game = _war(on)
    s = game.state
    names = [rules.trend_name(on, f) for f in rules.chaos_fronts(s, on)]
    line = game.status_data()["war_help"]["fronts"][0]
    assert names and f"現在{'、'.join(names)}在亂局。" in line  # 開季的起始值 40／35／55：三條都在 35～65
    on.config.chaos_low, on.config.chaos_high = 36, 54  # 起始值 40 在、35 與 55 都不在
    assert rules.chaos_fronts(s, on) == ["yingru"]
    assert "現在潁川汝南在亂局。" in game.status_data()["war_help"]["fronts"][0]
    on.config.chaos_low, on.config.chaos_high = 90, 95
    assert rules.chaos_fronts(s, on) == [] and "現在沒有戰線在亂局。" in game.status_data()["war_help"]["fronts"][0]


def test_the_big_event_counts_follow_the_timetable(on):
    kinds = [e.kind for e in on.timetable]
    line = howto.board_help(on)[0]
    assert f"這一季有 {len(kinds)} 件大事" in line
    assert f"{kinds.count('fixed')} 件史書寫定" in line and f"{kinds.count('roll')} 件看戰況擲骰" in line
    assert f"{kinds.count('showdown')} 場決戰" in line and "季末收場" in line
    first_roll = next(e for e in on.timetable if e.kind == "roll")
    first_roll.kind = "fixed"  # 時刻表改了：件數跟著變
    line = howto.board_help(on)[0]
    assert f"{kinds.count('fixed') + 1} 件史書寫定" in line and f"{kinds.count('roll') - 1} 件看戰況擲骰" in line


def test_the_roll_limits_come_from_the_timetable_rule(on, monkeypatch):
    assert "最多給到九成、最少也有一成" in howto.board_help(on)[0]  # timetable.CHANCE_CEIL／CHANCE_FLOOR
    monkeypatch.setattr(timetable, "CHANCE_CEIL", 0.8)
    monkeypatch.setattr(timetable, "CHANCE_FLOOR", 0.2)
    assert "最多給到八成、最少也有二成" in howto.board_help(on)[0]


def test_the_rewritable_events_are_the_ones_guan_and_huang_chains_point_at(on):
    """關鍵伏筆改寫得了的大事：官軍、黃巾的鏈指著的那幾件（豪強的鏈是第三方，不改寫結果）；伏筆拿掉就不提。"""
    events = {c.event for c in on.foreshadows.chains if c.side in ("guan", "huang")}
    assert f"其中 {len(events)} 件可以被關鍵伏筆改寫" in howto.board_help(on)[1]
    on.foreshadows.chains = [c for c in on.foreshadows.chains if c.side == "haoqiang"]
    assert len(howto.board_help(on)) == 1 and "伏筆改寫" not in "".join(howto.board_help(on))
