"""翻地與爭搶的純規則（輿圖簡化設計第四章；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md Task 1）：每一塊對每個攻方一條進度、推滿當場翻、
冷卻鎖住兩邊與加成暫停、每日回、集火、守把每一條都拉下、守城功、分紅、戰書門檻、軍令改讀、三方也成立。

合進區塊表 v3（輿圖第三版第 2 批，feature/territory-conquest b9ee3c9c）之後：汝南荒野改成中立、嵩山深處與官軍大營改成官軍的、黃巾開季
碰不到荒丘。要兩邊都推得動的中立地改用汝南荒野，黃巾開季的陣營區塊改用汝南；斷言不動。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game
from tianxia import calendar, conquest, territory
from conquest_kit import announce, conquest_game, go, join, plain_game, win_sortie
from tianxia import annals, calendar, conquest, materials
import re
from conquest_kit import announce, conquest_game, go, join
from tianxia import bot_policy, conquest, conquest_day, orders
from tianxia.engine import Option
from tianxia.state import BotProfile, Order
import random
from conquest_kit import _new, conquest_rules, fight
from conftest import real_content
from tianxia import conquest, encounter, team
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from conquest_kit import announce, contribution, conquest_game, go, join, plain_game, win_sortie
from tianxia import bot_policy, conquest, howto, orders, rules, sortie, territory, works
from tianxia.state import BotProfile
from conquest_kit import conquest_game, go, join, plain_game, press
from tianxia import bot_policy, conquest, howto, orders, sortie
from conquest_kit import conquest_game, go, join, plain_game
from tianxia import conquest, howto
from conquest_kit import conquest_game, go, join, win_sortie
from tianxia import conquest, orders
from tianxia.state import Order
from tianxia import atlas, conquest, orders
from conquest_kit import conquest_game, go, join, plain_game, win_sortie
from conquest_kit import conquest_game, join, plain_game, press
from tianxia import atlas, conquest, mapdata, orders


def _game():
    game = conquest_game("season21")
    return game, game.state.world, game.content


def _attack(w, c, loc, side, name, amount):
    return conquest.push(w, c, loc, side, name, amount, "attack")


def test_push_fills_the_bar_and_flips_at_full_with_payouts():
    game, w, c = _game()
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") is None
    first = _attack(w, c, "hilltop_wilds", "guan", "甲", 60)
    assert first.moved == 60 and not first.flipped and conquest.bar(w, "hilltop_wilds", "guan") == 60
    assert conquest.holder(w, c, "hilltop_wilds") is None
    done = _attack(w, c, "hilltop_wilds", "guan", "乙", 55)  # 只推得動 40：滿了就翻
    assert done.moved == 40 and done.flipped
    assert conquest.holder(w, c, "hilltop_wilds") == "guan"
    assert conquest.bars(w, "hilltop_wilds") == {}
    assert any("荒丘落入" in r.text for r in w.rumors)  # territory 的「落入」天下大事
    assert any(r.text == "甲率先攻入荒丘。" for r in w.chronicle)
    pay = {p.name: p for p in w.conquest.payouts}
    assert (pay["甲"].silver, pay["甲"].exp, pay["甲"].fame, pay["甲"].top) == (120, 180, 12, True)  # 中立地全額 200／300／20，佔六成
    assert (pay["乙"].silver, pay["乙"].exp, pay["乙"].fame, pay["乙"].top) == (80, 120, 8, False)
    note = w.conquest.day_log[-1]
    assert (note.by, note.side, note.loc, note.reason) == ("flip", "guan", "hilltop_wilds", "甲")


def test_faction_block_pool_is_halved():
    game, w, c = _game()
    conquest.push(w, c, "runan", "guan", "甲", 100, "attack")  # 黃巾開季的領地
    assert conquest.holder(w, c, "runan") == "guan"
    (pay,) = w.conquest.payouts
    assert (pay.silver, pay.exp, pay.fame) == (100, 150, 10)


def test_cooling_locks_both_sides_and_pauses_the_perks():
    game, w, c = _game()
    loc = "runan_wilds"  # 兩邊開季都碰得到的中立地（區塊表 v3 之前用荒丘）
    _attack(w, c, loc, "guan", "甲", 100)
    for side, how in (("huang", "attack"), ("guan", "hold")):
        assert conquest.push_problem(w, c, side, loc, how) == "剛易手，60 分後才能再推"
    assert conquest.cooling(w, c, loc)
    assert territory.price_factor(w, c, "guan", loc) == 1.0  # 自家的便宜暫停
    assert territory.price_factor(w, c, "huang", loc) == 1.0  # 敵方的加價也停
    assert not conquest.is_home(w, c, "guan", loc) and not conquest.is_home(w, c, None, loc)
    assert conquest.drop_cap(w, c, loc) == 1  # 中立駐軍只掉一階
    w.time += 59 * 60
    assert conquest.cooling_minutes(w, c, loc) == 1
    w.time += 61
    assert not conquest.cooling(w, c, loc)
    assert conquest.push_problem(w, c, "huang", loc, "attack") is None
    assert conquest.push_problem(w, c, "guan", loc, "hold") == conquest.WHY_IDLE  # 沒人推，守了也拉不動
    assert territory.price_factor(w, c, "guan", loc) == c.config.territory.own_price
    assert conquest.is_home(w, c, "guan", loc) and conquest.drop_cap(w, c, loc) is None


def test_hold_pulls_every_bar_down():
    game, w, c = _game()
    conquest.set_control(w, c, "hilltop_wilds", "guan")  # 管理者改的：沒有冷卻
    _attack(w, c, "hilltop_wilds", "huang", "丁", 30)
    _attack(w, c, "hilltop_wilds", "haoqiang", "戊", 20)  # 第三方也各推各的一條（翻地對 N 方成立）
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "hold") is None
    pulled = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 25, "hold")
    assert pulled.moved == 45 and conquest.bars(w, "hilltop_wilds") == {"huang": 5}
    assert not pulled.guarded  # 沒有哪一條到過五成：沒有守城功
    assert conquest.push_problem(w, c, "huang", "hilltop_wilds", "hold") == conquest.WHY_OUT  # 守只有佔著的那一方


def test_guard_merit_needs_the_alarm():
    game, w, c = _game()
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    _attack(w, c, "hilltop_wilds", "huang", "丁", 55)  # 過了五成
    conquest.push(w, c, "hilltop_wilds", "guan", "甲", 30, "hold")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "乙", 30, "hold")
    assert done.guarded and conquest.bars(w, "hilltop_wilds") == {}
    pay = {p.name: p for p in w.conquest.payouts if p.kind == "guard"}
    assert (pay["甲"].silver, pay["乙"].silver) == (55, 45)  # 總額 200 × 0.5，照拉回的 30：25 分
    assert any(r.text == "甲力保荒丘不失。" for r in w.chronicle)
    _attack(w, c, "hilltop_wilds", "huang", "丁", 30)  # 這一輪沒到五成
    again = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 30, "hold")
    assert not again.guarded and len([p for p in w.conquest.payouts if p.kind == "guard"]) == 2


def test_decay_only_blocks_nobody_pushed_for_a_whole_day():
    game, w, c = _game()
    conquest.decay(w, c)  # 第一次只記下今天
    today = calendar.day_index(w.time, c, w)
    _attack(w, c, "hilltop_wilds", "guan", "甲", 30)
    _attack(w, c, "runan_wilds", "guan", "甲", 30)  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    announce(game, "runan_wilds", "guan")  # 下了戰書：凍結，不回
    w.time = calendar.day_start(today + 2, c, w) + 60  # 跨進第二天：推過的那一天不回
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 30
    w.time = calendar.day_start(today + 3, c, w) + 60  # 再跨一天：前一整天沒人推，回 10
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 20
    assert conquest.bar(w, "runan_wilds", "guan") == 30
    w.time = calendar.day_start(today + 5, c, w) + 60  # 一次跨兩天：回兩次，歸零拿掉、這一輪的帳一起清
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 0 and "guan" not in w.conquest.fights["hilltop_wilds"].bars


def test_focus_counts_other_pushers_of_the_same_side_within_the_hour():
    game, w, c = _game()
    for name in ("甲", "乙"):
        conquest.mark(w, c, "hilltop_wilds", name, "guan", "attack", 5)
    conquest.mark(w, c, "hilltop_wilds", "丁", "huang", "attack", 5)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == pytest.approx(0.2)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "甲") == pytest.approx(0.1)  # 自己不算
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "huang", "戊") == pytest.approx(0.1)  # 別一邊不算
    for name in "子丑寅卯辰巳":
        conquest.mark(w, c, "hilltop_wilds", name, "guan", "attack", 5)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == pytest.approx(0.5)  # 最多五成
    w.time += 61 * 60
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == 0


def test_clash_names_are_the_other_side_within_ten_minutes():
    game, w, c = _game()
    conquest.mark(w, c, "hilltop_wilds", "戊", "huang", "attack", 5)
    w.time += 11 * 60
    conquest.mark(w, c, "hilltop_wilds", "丁", "huang", "attack", 5)
    conquest.mark(w, c, "hilltop_wilds", "甲", "guan", "attack", 5)
    assert conquest.clash_names(w, c, "hilltop_wilds", "guan", "甲") == ["丁"]  # 戊推的是 11 分鐘前
    assert conquest.clash_names(w, c, "hilltop_wilds", "huang", "丁") == ["甲"]
    assert conquest.clashing(w, c, "hilltop_wilds")
    w.time += 11 * 60
    assert not conquest.clashing(w, c, "hilltop_wilds") and conquest.clash_names(w, c, "hilltop_wilds", "guan", "甲") == []
    names = [row["name"] for row in conquest.pushers(w, c, "hilltop_wilds")]
    assert sorted(names) == ["丁", "戊", "甲"]  # 「正在推這裡的人」照 presence_seconds（一天）


def test_a_third_side_can_fill_and_flip_too():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 90)
    done = _attack(w, c, "hilltop_wilds", "haoqiang", "戊", 100)
    assert done.flipped and conquest.holder(w, c, "hilltop_wilds") == "haoqiang"
    assert conquest.bars(w, "hilltop_wilds") == {}  # 每一條都清掉


def test_letter_problem():
    game, w, c = _game()
    key = 7
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key) == "進度要到 60 才能下戰書（此刻 0）"
    _attack(w, c, "hilltop_wilds", "guan", "甲", 60)
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key) is None
    w.conquest.letter_days["guan"] = key
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key).startswith("官軍今天已經下過戰書了")
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) is None
    _attack(w, c, "hilltop_wilds", "huang", "丁", 70)
    slot = announce(game, "hilltop_wilds", "huang")
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) is None  # 黃巾下的、還沒開集結：可以併進同一場
    assert conquest.letter_problem(w, c, "huang", "hilltop_wilds", key + 1) == "黃巾軍已經對這一塊下了戰書"
    slot.status = "open"
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) == conquest.LETTER_OPEN
    assert conquest.letter_problem(w, c, "huang", "runan", key + 1) == conquest.WHY_OWN


def test_targets_skip_blocks_without_foes():
    game, w, c = _game()
    assert "hilltop_wilds" in conquest.targets(w, c, "guan")
    c.scenario.territory.neutral_garrison["hilltop_wilds"] = []
    c.locations["hilltop_wilds"].enemies = []
    assert "hilltop_wilds" not in conquest.targets(w, c, "guan")
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") == conquest.WHY_NO_FOE


def test_orders_read_the_highest_block_per_line():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 30)
    _attack(w, c, "runan_wilds", "guan", "甲", 10)  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    spots = conquest.focus_blocks(w, c, "guan", "attack")
    assert "hilltop_wilds" in spots and "runan_wilds" not in spots and "guan_camp" not in spots
    assert {"nanyang_road", "nanyang_wilds"} <= set(spots)  # 南陽那條線全是 0：每一塊推得動的都算
    assert conquest.focus_blocks(w, c, "guan", "defend") == []  # 沒人在推自家的地方
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    _attack(w, c, "hilltop_wilds", "huang", "丁", 20)
    _attack(w, c, "runan", "guan", "甲", 40)  # 黃巾的地方被推：黃巾要守
    assert conquest.focus_blocks(w, c, "guan", "defend") == ["hilltop_wilds"]
    assert conquest.focus_blocks(w, c, "huang", "defend") == ["runan"]


def test_halve_and_siege_start_shift():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 80)
    assert conquest.progress_shift(w, c, "hilltop_wilds", ["guan"]) == -6  # 往官軍偏（戰局以官軍為正向：起點 56）
    assert conquest.progress_shift(w, c, "hilltop_wilds", ["guan", "huang"]) == 0
    conquest.halve(w, c, "hilltop_wilds", ["guan"])
    assert conquest.bar(w, "hilltop_wilds", "guan") == 40


# ── 原 test_conquest_flip_game.py（整檔搬進來） ──
# 翻地與爭搶接到出陣上（輿圖簡化設計 4.1、4.2、4.5；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）：出陣攻推自己那一條、推滿那一下
# 當場易手、分紅在自己同步時送到（下線的人回來也拿得到）、冷卻期行動列寫原因、掉落只給一階、每日回在世界推進時跑、集火寫在那一句裡。

DAY = 86400


def _game_flipgame(side="guan", loc="hilltop_wilds", name="沈浪", world=None):
    return go(join(conquest_game("season21", name=name, world=world), side), loc)


def _nominal(game, loc="hilltop_wilds", how="attack"):
    return conquest.sortie_nominal(game.content, loc, how) * game.content.config.conquest.progress_scale


def test_sortie_attack_pushes_my_own_bar():
    game = _game_flipgame()
    msgs = win_sortie(game)
    w = game.state.world
    assert conquest.bar(w, "hilltop_wilds", "guan") == pytest.approx(_nominal(game))
    assert conquest.bar(w, "hilltop_wilds", "huang") == 0
    assert any("你在荒丘替官軍推進了" in m and "／100" in m for m in msgs)
    assert [row["name"] for row in conquest.pushers(w, game.content, "hilltop_wilds")] == ["沈浪"]


def test_the_push_that_fills_the_bar_flips_on_the_spot_and_pays_on_sync():
    game = _game_flipgame()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 99, "attack")
    silver = game.state.player.stats.get("silver", 0)
    msgs = win_sortie(game)
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and conquest.cooling(w, c, "hilltop_wilds")
    assert any("進度推滿了，當場易手" in m for m in msgs)
    assert any("荒丘落入" in r.text for r in w.rumors)
    assert {p.name for p in w.conquest.payouts} == {"沈浪", "別人"}
    mine = next(m for m in conquest.fight_of(w, "hilltop_wilds").marks if m.name == "沈浪")
    assert mine.moved == pytest.approx(1)  # 只推得動到滿的那一截
    game._deliver_conquest()
    entry = next(e for e in game.state.journal if e.title == "攻下荒丘")
    assert game.state.player.stats["silver"] > silver and any(line.startswith("銀兩 +") for line in entry.changes)
    assert [p.name for p in w.conquest.payouts] == ["別人"]  # 別人的留著，等他自己同步時拿
    assert not any(a.kind == annals.CONQUER for a in game.state.player.annals)  # 推最多的是「別人」


def test_the_top_pusher_gets_an_annal_and_the_payout_leaves_the_season():
    game = _game_flipgame()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "沈浪", 100, "attack")
    game._save_season()
    game.state.world = game.world.get_season()
    game._deliver_conquest()
    assert any(e.title == "攻下荒丘" for e in game.state.journal)
    assert any(a.kind == annals.CONQUER and "率先攻入荒丘" in a.text for a in game.state.player.annals)
    assert game.world.get_season().conquest.payouts == []


def test_the_action_note_says_why_it_cannot_push():
    game = _game_flipgame()
    w, c = game.state.world, game.content
    loc = c.locations["hilltop_wilds"]
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 100, "attack")  # 官軍剛拿下：冷卻
    assert "剛易手，60 分後才能再推" in game._sortie_line(loc)
    w.time += 3601
    assert "沒有人在推這裡" in game._sortie_line(loc)  # 自家的、沒人推：守了也拉不動
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 10, "attack")
    assert "把對面在這裡的進度拉回來" in game._sortie_line(loc)
    other = _game_flipgame(side="huang", world=game.world)
    other.state.world = w
    announce(game, "hilltop_wilds", "huang")
    assert "已下戰書" in other._sortie_line(loc)
    go(game, "xiaquyang")  # 冀州的中立地：官軍此刻碰不到
    assert "跟自家的領地不相連" in game._sortie_line(c.locations["xiaquyang"])


def test_a_cooling_neutral_block_drops_only_first_tier(monkeypatch):
    game = _game_flipgame()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 100, "attack")  # 黃巾剛拿下：官軍照樣能攻駐軍，但推不動、只掉一階
    seen: list = []
    real = materials.roll_squad_drops
    monkeypatch.setattr(materials, "roll_squad_drops", lambda *a, **k: seen.append(k.get("max_tier")) or real(*a, **k))
    win_sortie(game)
    assert seen == [1]
    assert conquest.bar(w, "hilltop_wilds", "guan") == 0


def test_decay_runs_when_the_world_moves():
    game = _game_flipgame()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 50, "attack")
    game._save_season()
    game.advance(3 * DAY / calendar.cal_scale(c, w))  # 三個季曆天：推過的那一天不回，後面兩天各回 10
    assert conquest.bar(game.state.world, "hilltop_wilds", "guan") == pytest.approx(50 - 2 * c.config.conquest.decay_per_day)


def test_focus_shows_in_the_line():
    game = _game_flipgame()
    w, c = game.state.world, game.content
    conquest.mark(w, c, "hilltop_wilds", "同袍", "guan", "attack", 3)
    msgs = win_sortie(game)
    assert any("集火 +10%" in m for m in msgs)
    assert conquest.bar(w, "hilltop_wilds", "guan") == pytest.approx(_nominal(game) * 1.1)


# ── 原 test_conquest_flip_qa_small.py（整檔搬進來） ──
# 輿圖第三版第 1 批（翻地與爭搶）QA 的順帶幾樣（試玩回饋檔尾那一節的「順帶」；PM 2026-10-21 派一起修）：
#
# 1. 守的那一句四捨五入成「拉回了 0」接著「全數歸零」：量不到 1 時不寫 0，寫「一點」（推也一樣；待 joy 潤）。
# 2. 戰書的時刻後面直接接字（「週三 12:00攻汝南荒野」「併進第 1 週・週六 12:00那一場」）：時刻與後面的字中間補一個空格，同別處接在時刻後面的寫法。
# 3. 管理者白天開單時〈天下形勢〉寫「一仗打到入夜」：在 test_xingshi.py 的 FB-610 那一段（同一個函式）。
# 4. 假人照開季的截糧軍令跑去推不動的地方出陣：假人挑出陣地點時先問 conquest.push_problem，推不動的不去、不出陣。

NOW = 1_792_000_000.0


STUCK = re.compile(r"\d:\d\d[^\s\d]")  # 時刻後面直接接字


def test_a_pull_under_one_does_not_say_zero():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 0.4, "attack")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 5, "hold")
    assert done.moved == pytest.approx(0.4)
    assert not any("拉回了 0" in line for line in done.lines), done.lines  # 修前「把對面的進度拉回了 0。」接「全數歸零」
    assert any("拉回了一點" in line for line in done.lines)
    big = conquest.push(w, c, "hilltop_wilds", "huang", "丁", 3, "attack")
    pulled = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 3, "hold")
    assert big.moved == 3 and any("拉回了 3" in line for line in pulled.lines)  # 一以上照舊寫數字


def test_a_push_under_one_does_not_say_zero():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "甲", 99.7, "attack")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "乙", 2, "attack")
    assert done.flipped and done.moved == pytest.approx(0.3)
    assert not any("推進了 0" in line for line in done.lines), done.lines
    assert any("推進了一點" in line for line in done.lines)


def _seated(side="guan", loc="hilltop_wilds", name="沈浪", world=None):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    game.state.player.qualified = True
    game.state.world.seats[side] = [name]
    return game


def test_letter_times_have_a_space_before_the_words():
    game = _seated(loc="runan_wilds")
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "先鋒", 60, "attack")
    conquest.push(w, c, "runan_wilds", "huang", "先鋒", 60, "attack")
    mine = game.conquest_letter("runan_wilds")
    game._save_season()
    rival = _seated(side="huang", loc="runan_wilds", name="張角徒", world=game.world)
    joined = rival.conquest_letter("runan_wilds")
    news = [r.text for r in rival.state.world.rumors if "戰書" in r.text]
    texts = mine + joined + news
    assert len(news) == 2 and any("下了戰書" in t for t in mine) and any("併進" in t for t in joined)
    for text in texts:
        assert not STUCK.search(text), text  # 修前「定於第 1 週・週三 12:00攻汝南荒野」「併進第 1 週・週六 12:00那一場」


def test_admin_letter_time_has_a_space_before_the_words():
    game = _seated()
    text = conquest_day.place_now(game.state.world, game.content, "huang", "runan_wilds", NOW)
    assert "攻汝南荒野" in text and not STUCK.search(text), text  # 修前「黃巾軍定於第 1 週・週四 15:30攻荒丘。」


def _bot(game, side):
    game.state.player.bot = BotProfile(personality="普通", seed=7, faction=side, season_number=game.world.get_season_number())
    return game


def _intercept(game, side, loc, front):
    s, c = game.state, game.content
    s.world.orders.clear()
    order = Order(id=f"t:{side}:intercept", template="intercept", faction=side, week=orders.period_of(s, c), front=front,
                  location=loc, quota=99, text="（測試）")
    s.world.orders.append(order)
    return order


def test_bots_do_not_sortie_where_they_cannot_push(monkeypatch):
    """QA：開季的截糧軍令把官軍的假人拉到下曲陽（官軍開季碰不到、推不動），在那裡一直出陣、連輸中立駐軍。
    2026-10-22（7 天季領地爭奪調整）之後假人出陣也看勝算（bot_policy._outmatched，測試在 test_bot_policy_conquest.py）：剛建的假人在荒丘
    攻打的贏面不到門檻；這一條只鎖「推不推得動」，勝算一律當成穩勝。"""
    monkeypatch.setattr(bot_policy, "_sortie_win", lambda game, loc_id: 1.0)
    game = _bot(go(join(conquest_game("season21", name="假官"), "guan"), "xiaquyang"), "guan")
    w, c = game.state.world, game.content
    _intercept(game, "guan", "xiaquyang", "jizhou")
    assert conquest.push_problem(w, c, "guan", "xiaquyang", "attack") is not None  # 推不動
    assert orders.win_counts(game.state, c, "guan", "xiaquyang")  # 截糧照舊記得到（修前就是這個加分把假人留在這裡出陣）
    train = Option(id="act:train", label="出陣・攻")
    assert bot_policy.score(game, train, game.state.player.bot) is None  # 修前照樣打分數（還多一份軍令的加分）
    go(game, "hilltop_wilds")  # 推得動的地方照舊會出陣
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") is None
    assert bot_policy.score(game, train, game.state.player.bot) is not None


def test_bots_are_not_led_to_an_intercept_spot_they_cannot_push():
    game = _bot(go(join(conquest_game("season21", name="假官"), "guan"), "luzhi_camp"), "guan")
    _intercept(game, "guan", "xiaquyang", "jizhou")
    assert "xiaquyang" in orders.targets(game.state, game.content, "guan")  # 軍令本身照舊列它（卡上照寫）
    assert bot_policy._order_hop(game) is None  # 修前往下曲陽走


def test_bots_still_go_to_a_frozen_block_of_their_own_to_defend():
    """FB-605 之後守城會列自家被戰書凍結的那一塊（推不動，等著攻城戰）：假人照樣往那裡走（加入攻城站守方才記得到），不被上面那一條擋掉。"""
    game = _bot(go(join(conquest_game("season21", name="假黃"), "huang"), "huangjin_camp"), "huang")
    s, c = game.state, game.content
    s.world.orders.clear()
    s.world.orders.append(Order(id="t:huang:defend", template="defend", faction="huang", week=orders.period_of(s, c), front="yingru",
                                quota=99, text="（測試）"))
    conquest.push(s.world, c, "runan", "guan", "敵將", 60, "attack")
    announce(game, "runan", "guan")
    assert orders.targets(s, c, "huang") == ["runan"]
    assert bot_policy._order_hop(game) is not None


# ── 原 test_conquest_clash.py（整檔搬進來） ──
# 翻地與爭搶：混戰（輿圖簡化設計 4.3【企劃者選 b】、第九章第 14 條；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）。
# 出陣時對面 10 分鐘內在這一塊推過、人還在這裡，照截殺的規則打一場：贏的那一下推得多、輸的白跑、平手照推；保護照截殺（新手期、同一對的冷卻、
# 被截過的護身、截殺開關），帳跟截殺共用；城鎮也打；沒有戰利品；兩邊各一份戰報。
#
# 兩個角色開在同一個資料庫：每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去。
#
# 合進區塊表 v3（輿圖第三版第 2 批，feature/territory-conquest b9ee3c9c）之後黃巾開季碰不到荒丘：兩邊撞上的地方從荒丘換成汝南荒野（v3 起是兩邊都碰得到的中立地），斷言不動。

LOC = "runan_wilds"  # 兩邊開季都碰得到的中立地（區塊表 v3 之前用荒丘）


def _world():
    c = conquest_rules(real_content("season21"))
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0  # 不等新手期（新手期另外測）
    first = _new(c, "甲")
    CharacterStore(first.world.db).save(first.state)
    return c, first.world


def _seat(c, world, name, side, loc):
    state = CharacterStore(world.db).load(name)
    if state is None:
        state = _new(c, name, world).state
    p = state.player
    p.faction, p.location, p.journey = side, loc, None
    p.tutorial_step = len(c.tutorial.steps)
    p.stamina = float(c.config.stamina_max)
    p.visited.add(loc)
    CharacterStore(world.db).save(state)


def _do(c, world, name, act):
    state = CharacterStore(world.db).load(name)
    game = Game(c, state, random.Random(0), world)
    game.client = None
    game.now = NOW
    game.state.world = world.get_season()
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _sortie(c, world, name, tier="大勝"):
    with fight(tier):
        return _do(c, world, name, lambda g: g.choose("act:train"))


def _melee(monkeypatch, tier):
    real = encounter.resolve_encounter
    monkeypatch.setattr(encounter, "resolve_encounter",
                        lambda ours, theirs, rng, *a, **k: real(ours, theirs, rng).model_copy(update={"tier": tier}))


def _pair(loc=LOC):
    c, world = _world()
    _seat(c, world, "甲", "guan", loc)
    _seat(c, world, "乙", "huang", loc)
    return c, world


def _base(c, loc):
    """一個人推、沒有集火：名目量 × progress_scale。"""
    return conquest.sortie_nominal(c, loc, "attack") * c.config.conquest.progress_scale


def test_a_win_pushes_more_and_both_sides_get_a_report(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")  # 黃巾先在這裡推了一下
    _melee(monkeypatch, "大勝")
    purse = CharacterStore(world.db).load("乙").player.stats.get("silver", 0)
    msgs, game = _sortie(c, world, "甲")
    w = game.state.world
    assert conquest.bar(w, LOC, "guan") == pytest.approx(_base(c, LOC) * c.config.conquest.clash_scale)
    assert any("乙正在汝南荒野替黃巾軍出力" in m for m in msgs) and any("混戰得勝" in m for m in msgs)
    mine = [r for r in game.state.battles if r.kind == "melee"]
    assert len(mine) == 1 and mine[0].silver in (None, 0)  # 沒有戰利品
    theirs = CharacterStore(world.db).load("乙")
    assert any(r.kind == "melee" for r in theirs.battles)
    assert any(e.title == "遭甲撞上" for e in theirs.journal)
    assert w.raids["甲>乙"] == w.raids["乙>甲"] == w.time and w.raided["乙"] == w.time  # 跟截殺共用一本帳
    assert theirs.player.stats.get("silver", 0) == purse  # 輸的不失銀兩


def test_a_loss_wastes_the_push_but_spends_the_sortie(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "落敗")
    before = CharacterStore(world.db).load("甲").player
    msgs, game = _sortie(c, world, "甲")
    w = game.state.world
    assert conquest.bar(w, LOC, "guan") == 0
    assert any("這一趟白跑了" in m for m in msgs)
    p = game.state.player
    assert p.sorties_today == before.sorties_today + 1 and p.stamina < before.stamina
    assert [r.kind for r in game.state.battles] == ["melee"]  # 沒有打守軍
    assert any(row["name"] == "甲" and row["moved"] == 0 for row in conquest.pushers(w, c, LOC))


def test_a_draw_pushes_as_usual(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "僵持")
    _, game = _sortie(c, world, "甲")
    assert conquest.bar(game.state.world, LOC, "guan") == pytest.approx(_base(c, LOC))


@pytest.mark.parametrize("guard", ["stale", "moved", "cooldown", "shield", "switch", "newbie"])
def test_protections_keep_a_clash_from_happening(monkeypatch, guard):
    c, world = _pair()
    _sortie(c, world, "乙")
    if guard == "stale":  # 11 分鐘前推的：不是「正在推」
        world.mutate_season(lambda s: setattr(s, "time", s.time + 11 * 60))
    elif guard == "moved":
        _seat(c, world, "乙", "huang", "nanyang_road")
    elif guard == "cooldown":
        world.mutate_season(lambda s: s.raids.__setitem__("乙>甲", s.time))  # 他剛截殺過你：這一對三小時內不撞
    elif guard == "shield":
        world.mutate_season(lambda s: s.raided.__setitem__("乙", s.time))
    elif guard == "switch":
        c.config.raid.enabled = False
    elif guard == "newbie":
        c.config.newbie_days = 3
    _melee(monkeypatch, "落敗")
    msgs, game = _sortie(c, world, "甲")
    assert not any(r.kind == "melee" for r in game.state.battles)
    assert conquest.bar(game.state.world, LOC, "guan") > 0  # 照常推


def test_a_clash_happens_in_a_town_on_a_hold(monkeypatch):
    c, world = _world()
    world.mutate_season(lambda s: conquest.set_control(s, c, "runan_wilds", "guan"))  # 汝南荒野歸官軍：汝南（黃巾的城）碰得到
    _seat(c, world, "甲", "huang", "runan")
    _seat(c, world, "乙", "guan", "runan")
    _sortie(c, world, "乙")  # 官軍攻汝南
    _, game = _do(c, world, "甲", lambda g: None)
    pushed = conquest.bar(game.state.world, "runan", "guan")
    assert pushed > 0
    _melee(monkeypatch, "大勝")
    msgs, game = _sortie(c, world, "甲")  # 黃巾在自家的城守：撞上就打（城鎮也打）
    w = game.state.world
    assert any(r.kind == "melee" for r in game.state.battles)
    pull = conquest.sortie_nominal(c, "runan", "hold") * c.config.conquest.progress_scale * c.config.conquest.clash_scale
    assert conquest.bar(w, "runan", "guan") == pytest.approx(max(0.0, pushed - pull))


def test_no_clash_where_the_sortie_cannot_push(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    world.mutate_season(lambda s: s.conquest.fights[LOC].__setattr__("flipped_at", s.time))  # 剛易手：兩邊都推不動
    _melee(monkeypatch, "落敗")
    _, game = _sortie(c, world, "甲")
    assert not any(r.kind == "melee" for r in game.state.battles)


@pytest.mark.parametrize(("tier", "hit_won"), [("大勝", False), ("落敗", True), ("險勝", False)])
def test_the_hit_side_story_follows_its_own_result(monkeypatch, tier, hit_won):
    """FB-606（QA 驗輿圖第三版第 1 批）：被撞的那一方，那一則紀錄「遭某某撞上」與行狀照**自己的**勝負寫，跟他那一份戰報對得上
    （修前照出陣那一方的結果挑句子：出陣的大勝，被撞的戰報「落敗」，紀錄卻寫「你逼退了他」）。"""
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, tier)
    _sortie(c, world, "甲")
    theirs = CharacterStore(world.db).load("乙")
    (record,) = [r for r in theirs.battles if r.kind == "melee"]
    assert (record.tier in team.WIN_TIERS) is hit_won
    entry = next(e for e in theirs.journal if e.title == "遭甲撞上")
    story = next(line for line in entry.lines if "撞上了你" in line)
    annal = next(a.text for a in theirs.player.annals if "撞上了你" in a.text)
    for text in (story, annal):
        if hit_won:
            assert "你逼退了" in text and "你不敵" not in text, text
        else:
            assert "你不敵" in text and "逼退" not in text, text


def test_a_draw_story_is_a_draw_on_the_hit_side(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "僵持")
    _sortie(c, world, "甲")
    theirs = CharacterStore(world.db).load("乙")
    assert any("撞上了你" in a.text and "不分高下" in a.text for a in theirs.player.annals)


def test_after_a_clash_the_raid_refusal_says_clash_not_raid(monkeypatch):
    """FB-607（QA 驗輿圖第三版第 1 批）：混戰跟截殺共用冷卻與護身那一本，可是撞過一場之後兩個人互看截殺的拒絕話寫「你不久前才截殺過某某」
    （被撞的那一個從頭到尾沒截殺過誰）、第三個人去截殺被撞的那一個寫「剛被人截殺過」。照實寫：混戰過的寫混戰（待 joy 潤）。"""
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "僵持")
    _sortie(c, world, "甲")
    _seat(c, world, "丙", "guan", LOC)
    _, hit = _do(c, world, "乙", lambda g: None)
    _, hitter = _do(c, world, "甲", lambda g: None)
    _, third = _do(c, world, "丙", lambda g: None)
    to_hitter = hit.raid_refusal(hit._load_kin("甲"))
    to_hit = hitter.raid_refusal(hitter._load_kin("乙"))
    to_shielded = third.raid_refusal(third._load_kin("乙"))
    for text in (to_hitter, to_hit, to_shielded):
        assert text is not None and "截殺過" not in text, text
        assert "混戰" in text, text
    assert "甲" in to_hitter and "乙" in to_hit and "乙" in to_shielded


def test_a_real_raid_still_says_raid():
    """FB-607 的另一面：真的截殺過，拒絕話照舊寫截殺（同一對的冷卻、剛被截過的護身）。"""
    c, world = _pair()
    _do(c, world, "甲", lambda g: g.raid(g._load_kin("乙")))
    _seat(c, world, "丙", "guan", LOC)
    _, again = _do(c, world, "甲", lambda g: None)
    _, third = _do(c, world, "丙", lambda g: None)
    assert again.raid_refusal(again._load_kin("乙")) == "你不久前才截殺過乙，過一陣子再說。"
    assert third.raid_refusal(third._load_kin("乙")) == "乙剛被人截殺過，元氣未復，這時下手太不講江湖道義。"


# ── 原 test_conquest_progress.py（整檔搬進來） ──
# 領地爭奪第一批 Task 6：出陣改推進度（計畫三、Task 6；設計 3.7：平常出陣推那一塊的進度、不推線；貢獻照記）。翻地與爭搶（輿圖簡化設計第四章）之後
# 進度是每個攻方各一條、推得動的是碰得到的每一塊（不再只推今天公告的目標），這幾條照新形狀改寫；推滿易手、混戰、戰書另在 test_conquest_flip*.py、
# test_conquest_flip.py、test_conquest_siege.py。

def _sortie_progress(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def test_sortie_attack_win_pushes_progress_not_the_line():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    before = _value(game, "nanyang")
    option = _sortie_progress(game)
    assert option is not None and option.enabled and "攻" in option.label
    msgs = win_sortie(game)
    assert conquest.bar(game.state.world, "nanyang_road", "huang") > 0
    assert _value(game, "nanyang") == before  # 不推線
    assert contribution(game) > 0  # 貢獻照記（不然沒人升得到第 4 階）
    assert any("你在南陽官道替黃巾軍推進了" in m for m in msgs)  # 輿圖簡化設計第五章起進度看得到數字
    assert not any("大勢@" in m for m in msgs)


def test_hold_at_own_block_pushes_back():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 30, "attack")  # 黃巾在推官軍的潁川郊野
    option = _sortie_progress(game)
    assert option is not None and "守" in option.label
    game.choose("act:train")
    assert conquest.bar(game.state.world, "yingchuan_wilds", "huang") < 30  # 把黃巾那一條拉回來
    assert contribution(game) > 0


def test_sortie_exists_at_non_line_block_but_not_off_the_blocks():
    game = go(join(conquest_game("season21"), "huang"), "deep_mountain")  # 嵩山深處不是戰線地點（區塊表 v3：官軍的）
    option = _sortie_progress(game)
    assert option is not None and "攻" in option.label
    go(game, "haozu_fort")  # 豪強的投靠點不是區塊
    assert _sortie_progress(game) is None


def test_bases_hold_but_push_no_progress():
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "守" in _sortie_progress(game).label
    game.choose("act:train")
    assert conquest.bars(game.state.world, "changshe") == {}  # 大本營搶不下來：沒有進度


def test_neutral_block_foes_are_the_neutral_garrison():
    game = go(join(conquest_game("season21"), "guan"), "yu_river")  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    loc = game.content.locations["yu_river"]
    assert set(game._sortie_foes(loc)) == set(territory.squads_at(game.state.world, game.content, "yu_river"))
    assert "nz_shuifei" in game._sortie_foes(loc)


def test_enemy_block_without_garrison_has_the_holders_patrol():
    game = go(join(conquest_game("season21"), "huang"), "yingchuan")  # 官軍的城鎮沒寫 garrison
    loc = game.content.locations["yingchuan"]
    assert set(game._sortie_foes(loc)) == set(game.content.scenario.territory.side_garrison["guan"])


def test_event_at_block_pushes_progress_once():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")  # 還沒人佔的中立地：事件了結推自己那一條
    s, c = game.state, game.content
    for event in c.events.values():
        for i, choice in enumerate(event.choices):
            if choice.combat or choice.check or choice.effect.next_event or choice.needs or event.once or event.qiyu:
                continue
            s.pending_event = event.id
            option = next((o for o in game.options() if o.id == f"choice:{i}" and o.enabled), None)
            if option is None:
                s.pending_event = None
                continue
            game.choose(option.id)
            assert s.pending_event is None
            # 只推一次 event_progress（一個人推：人數緩衝 ÷√1），推官軍那一條；不是出陣，不記「正在推的人」
            assert conquest.bar(s.world, "hilltop_wilds", "guan") == pytest.approx(c.config.conquest.event_progress)
            assert conquest.pushers(s.world, c, "hilltop_wilds") == []
            return
    pytest.skip("找不到單純的事件選項")


def test_bot_train_value_follows_progress(monkeypatch):
    # 2026-10-22（7 天季領地爭奪調整）之後假人出陣也看勝算（bot_policy._outmatched，測試在 test_bot_policy_conquest.py）：剛建的人打不贏
    # 南陽官道的駐軍；這一條只鎖「推不推得動」，勝算一律當成穩勝
    monkeypatch.setattr(bot_policy, "_sortie_win", lambda game, loc_id: 1.0)
    game = go(join(conquest_game("season21"), "huang"), "nanyang_huangjin_camp")
    profile = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    assert bot_policy._train_value(game, profile, "nanyang_road") > 0  # 碰得到的中立地：推得動
    announce(game, "nanyang_road", "huang")  # 下了戰書：凍結，推不動
    assert bot_policy._train_value(game, profile, "nanyang_road") == 0
    assert bot_policy._train_value(game, profile, "nanyang_huangjin_camp") == 0  # 大本營：沒有進度可推


def test_siege_places_are_the_highest_block_on_that_line():
    """翻地與爭搶（PM 2026-10-20 第 1 條）：攻城軍令的地點是這一邊此刻進度最高、推得動的那一塊（第二批是今天公告的目標）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert "runan_wilds" in orders.siege_places(c, "guan", "yingru", w)  # 全是 0：推得動的每一塊都算
    conquest.push(w, c, "runan_wilds", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
    assert orders.siege_places(c, "huang", "yingru", w) == ["runan_wilds"]  # 區塊表 v3：黃巾開季碰不到荒丘


def test_howto_has_the_conquest_version():
    game = conquest_game("season21")
    lines = howto.territory_lines(game.content, True, game.state.world)
    assert any("中立地" in line for line in lines)


def test_help_texts_say_progress_and_holdings():
    """戰況圖卡、主線小標、投靠那一段的說明：出陣推進度、戰線照佔領算（不再寫「在戰線上的地點出陣會推動戰況」）。"""
    game = conquest_game("season21")
    s, c = game.state, game.content
    helps = howto.war_help(s, c)
    assert howto.CONQUEST_FRONTS in " ".join(helps["fronts"])
    assert howto.CONQUEST_PLACES in " ".join(helps["quest"])
    assert howto.CONQUEST_PLACES in " ".join(howto.season_page_lines(c, s.world))
    assert howto.CONQUEST_JOIN in " ".join(howto.join_lines(c, s.world))


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])  # 行動列底下出陣那一行（action_notes 的 act:train）


def test_action_note_says_progress_not_the_line():
    """行動列底下那一行：出陣推的是這一塊的進度，不寫「這條線推滿了」（sortie_push 開著時是空的，舊寫法會判成推不動）。"""
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road")
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 10, "attack")
    go(join(game, "guan"), "yingchuan_wilds")  # 守自家的區塊：有人在推，拉得回來
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")
    go(game, "changshe")  # 大本營搶不下來：沒有進度（FB-532：自家的大本營另一句，見 test_conquest_sortie_notes）
    assert "沒有進度可推" in _note(game, "changshe") and howto.SORTIE_PROGRESS not in _note(game, "changshe")


def test_ranger_sees_why_at_every_block():
    """散人站在不是戰線地點的區塊（嵩山深處）：投靠了陣營的人在這裡有出陣，散人那一格灰著寫原因（FB-250 的同一條，照區塊判）。"""
    game = go(join(conquest_game("season21"), None), "deep_mountain")
    option = _sortie_progress(game)
    assert option is not None and not option.enabled and sortie.RANGER_NOTE in option.label
    go(game, "haozu_fort")  # 不是區塊：沒有出陣那一格
    assert _sortie_progress(game) is None


# ── 原 test_conquest_duty.py（整檔搬進來） ──
# 計畫第八章裁決 24（PM 2026-10-20，照企劃者 10/17 行動精準化「鈕寫什麼就要給什麼」，同裁決 18 的道理）：領地爭奪開著時，
# 守勢行動（巡哨、傳道、保境安民）只給自家的地方——站在別人的地方（敵方的大本營與區塊、廣宗）或還沒佔下的中立地，那一顆灰著寫原因
# （跟出陣用完、「此地不在爭奪之列」同一種寫法），按下去什麼都不給：不扣體力與出陣次數、不推線、不記守城。自家的地方照舊。
# 守城軍令記得了次數的地點只有「自家今天被公告的那一塊」（裁決 11），敵方大本營從來不在裡面；這一支把它鎖住。
# 關著的季（週末、14 天、21 天）一個字都不變。

# （陣營, 地點, 這裡是誰的）：敵方大本營、敵方區塊、廣宗（fixed，黃巾的）、還沒佔下的中立地（區塊表 v3：汝南荒野改成中立、
# 嵩山深處改成官軍的，敵方區塊換汝南、中立地換淯水河畔）
OTHERS = (
    ("guan", "huangjin_camp", "other"),
    ("guan", "runan", "other"),
    ("guan", "guangzong", "other"),
    ("guan", "yu_river", "open"),
    ("guan", "hilltop_wilds", "open"),
    ("huang", "changshe", "other"),
    ("huang", "yingchuan_wilds", "other"),
    ("huang", "nanyang_road", "open"),
)


OWN = (("guan", "changshe"), ("guan", "yingchuan_wilds"), ("huang", "huangjin_camp"), ("huang", "runan"))


def _duty(game):
    return next((o for o in game.options() if o.id == "act:duty"), None)


def _snapshot(game):
    s, w = game.state, game.state.world
    return {
        "stamina": s.player.stamina, "sorties": (s.player.sortie_day, s.player.sorties_today), "contrib": s.player.contrib,
        "trends": dict(w.trends), "offset": dict(w.conquest.offset), "journal": len(s.journal),
        "orders": [(o.id, dict(o.progress)) for o in w.orders],
    }


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.parametrize(("side", "loc", "kind"), OTHERS)
def test_duty_is_grey_with_a_reason_off_own_ground(side, loc, kind):
    game = go(join(conquest_game("season21"), side), loc)
    option = _duty(game)
    assert option is not None and not option.enabled  # 修前按得下去
    name = game.content.orders.duties[side].name
    reason = sortie.DUTY_OUT_OPEN if kind == "open" else sortie.DUTY_OUT_OTHER
    assert option.label == f"{name}（{reason}）"
    assert conquest.holder(game.state.world, game.content, loc) in (None, "huang" if side == "guan" else "guan")


@pytest.mark.parametrize(("side", "loc", "kind"), OTHERS)
def test_pressing_it_gives_nothing(side, loc, kind):
    game = go(join(conquest_game("season21"), side), loc)
    w, c = game.state.world, game.content
    w.orders.append(Order(id="t:defend", template="defend", faction=side, week=orders.period_of(game.state, c),
                          front=conquest.line_of(w, c, loc) or "yingru", quota=5, text="（測試）"))
    before = _snapshot(game)
    msgs = game.choose("act:duty")
    assert msgs == ["（此刻無法這麼做。）"]
    assert _snapshot(game) == before  # 不扣體力與出陣次數、不推線、不記貢獻與守城、不寫江湖紀錄


@pytest.mark.parametrize(("side", "loc"), OWN)
def test_own_ground_still_gives_it(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    option = _duty(game)
    assert option is not None and option.enabled
    before = _snapshot(game)
    game.choose("act:duty")
    after = _snapshot(game)
    assert after["stamina"] < before["stamina"] and after["sorties"][1] == before["sorties"][1] + 1
    assert after["offset"] != before["offset"]  # 自家的地方照舊推線（裁決 11）


def test_taking_a_neutral_block_turns_the_button_on_and_losing_it_turns_it_off():
    game = go(join(conquest_game("season21"), "guan"), "yu_river")  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    w, c = game.state.world, game.content
    assert not _duty(game).enabled
    conquest.set_control(w, c, "yu_river", "guan")
    assert _duty(game).enabled
    conquest.set_control(w, c, "yu_river", "huang")
    option = _duty(game)
    assert not option.enabled and option.label.endswith(f"（{sortie.DUTY_OUT_OTHER}）")


def test_a_gentry_follows_the_side_it_leans_on():
    game = go(join(conquest_game("season21"), "haoqiang"), "changshe")
    game.state.player.ally = "guan"
    assert _duty(game).enabled  # 依附官軍：長社是自家的
    go(game, "huangjin_camp")
    assert not _duty(game).enabled
    game.state.player.ally = "huang"
    assert _duty(game).enabled and not _duty(go(game, "changshe")).enabled


def test_places_that_are_not_blocks_are_untouched():
    """不是區塊的地點（南華觀、豪強三處投靠點）誰也不佔：先不動（裁決只點名別人的區塊與沒佔下的中立地），要不要擋交 PM。"""
    game = go(join(conquest_game("season21"), "guan"), "jade_cave")
    assert "jade_cave" not in conquest.blocks(game.content)
    assert _duty(game) is not None and _duty(game).enabled


def test_the_defend_order_never_counts_or_lists_an_enemy_base():
    """守城軍令（裁決 11）：自家今天被公告的那一塊；敵方的大本營、區塊、自家沒被公告的區塊，記不到、假人也不往那裡走。
    翻地與爭搶（PM 2026-10-20 第 1 條）之後「被公告的那一塊」換成「自家被推得最高的那一塊」：前提改成黃巾在那裡推了一截（conquest_kit.press），
    斷言不動。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    guan_block = next(loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
                      and conquest.line_of(w, c, loc) == "yingru")
    press(game, guan_block, "huang")
    w.orders.append(Order(id="t:defend", template="defend", faction="guan", week=orders.period_of(game.state, c), front="yingru",
                          quota=5, text="守"))
    state = join(game, "guan").state
    assert orders.duty_counts(state, c, "guan", guan_block)
    for loc in ("huangjin_camp", "runan", "runan_academy", "runan_wilds", "hilltop_wilds", "changshe", "yingchuan_wilds", "deep_mountain"):
        assert not orders.duty_counts(state, c, "guan", loc), loc  # 敵方大本營、敵方區塊、中立地、自家大本營與沒被公告的自家區塊
    assert orders.targets(state, c, "guan") == [guan_block]
    for loc in ("huangjin_camp", "runan"):  # 真的站在敵方那裡也記不到（修前就是如此，只是鈕按得下去、線照推）
        assert not orders._counts(c, w.orders[-1], "duty", loc, None, None, None, None, None, w)


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_bots_never_press_it_off_own_ground():
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    game = go(join(conquest_game("season21"), "guan"), "huangjin_camp")
    options = [o for o in game.options(odds=False, tick=False) if o.enabled]
    assert "act:duty" not in {o.id for o in options}
    rng = random.Random(3)
    assert all(bot_policy.pick(game, options, profile, rng) != "act:duty" for _ in range(200))


def test_howto_says_duty_stays_on_own_ground():
    game = conquest_game("season21")
    lines = " ".join(howto.territory_lines(game.content, True, game.state.world))
    assert "守勢行動也只在自家的領地做" in lines
    off = plain_game("season21")
    assert "守勢行動" not in " ".join(howto.territory_lines(off.content, True, off.state.world))  # 關著：拔河那一版，一個字不變


# ── 原 test_conquest_sortie_notes.py（整檔搬進來） ──
# 領地爭奪第一批 QA 之後：行動列底下出陣那一行照實寫（FB-532、FB-533），敵方大本營與廣宗不給攻（計畫第八章裁決 18）。字待 joy 潤。
#
# 翻地與爭搶（輿圖簡化設計第四章）之後碰得到的每一塊都推得動（不再只推今天公告的目標），推不動照 conquest.push_problem 寫原因：
# 「今天沒有公告」那幾句換成原因（沒人在推、不相連）；裁決 21 的一個括號照留。

@pytest.mark.parametrize(("side", "base"), [("guan", "changshe"), ("huang", "huangjin_camp")])
def test_own_base_hold_line_reads_right(side, base):
    """FB-532：站在自家大本營守，那一行不再寫「推不動進度（這裡搶不下來）（量是攻的一半）」。"""
    game = go(join(conquest_game("season21"), side), base)
    note = _note(game, base)
    assert note == "這裡是自家地盤，不在爭奪之列：不用打，也沒有進度可推；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"


def test_own_fixed_block_hold_line_reads_right():
    """廣宗（fixed）在黃巾手上：同自家大本營。"""
    game = go(join(conquest_game("season21"), "huang"), "guangzong")
    assert _note(game, "guangzong").startswith("這裡是自家地盤，不在爭奪之列：")


def test_own_capturable_block_hold_line_is_unchanged():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 20, "attack")  # 黃巾在推：官軍守拉得回來
    assert _note(game, "yingchuan_wilds") == (
        "這裡是自家地盤：不用打，把對面在這裡的進度拉回來、記貢獻（量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


@pytest.mark.parametrize("loc", ["hilltop_wilds", "runan"])
def test_own_idle_block_hold_line_has_one_parenthesis(loc):
    """計畫第八節裁決 21：自家推不動的區塊守（翻地與爭搶之後是「沒人在推」），推不動的原因與「量是攻的一半」合成一個括號。
    荒丘是被管理者定給黃巾的中立地，汝南是黃巾開季的陣營區塊（區塊表 v3 之前用汝南荒野）。"""
    game = go(join(conquest_game("season21"), "huang"), loc)
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    note = _note(game, loc)
    assert "）（" not in note and note.count("（") == 1  # 修前兩個括號
    assert note == (
        "這裡是自家地盤：不用打，推不動進度（沒有人在推這裡，守了也拉不動；有人來攻時守拉的量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


def test_others_block_out_of_reach_line_says_why():
    """別人的區塊、跟自家的領地不相連：一個括號寫原因。"""
    game = go(join(conquest_game("season21"), "guan"), "runan")
    assert _note(game, "runan").startswith("這裡歸別人：打一場，打贏推不動進度（這裡跟自家的領地不相連）；只拿對手 3 成的心得與經驗，")


def test_unheld_neutral_block_does_not_say_someone_else_holds_it():
    """FB-533（1）：還沒人佔的中立地，出陣那一行不寫「這裡歸別人」。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")  # 區塊表 v3 之前用官軍大營（現在是官軍的）
    note = _note(game, "runan_wilds")
    assert note.startswith("這裡還沒有人佔：打一場，打贏推這一塊的進度、記貢獻；只拿對手 3 成的心得與經驗，")
    assert "這裡歸別人" not in note


def test_neutral_block_held_by_the_enemy_still_says_so():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    assert _note(game, "hilltop_wilds").startswith("這裡歸別人：打一場，打贏推這一塊的進度、記貢獻；")


def test_howto_sortie_line_drops_the_resistance_half_sentence():
    """FB-533（2）：領地爭奪版的出陣說明不寫「越往對方老巢推越難推」（推進度沒有盡頭阻力），還沒人佔的中立地也是打。"""
    game = conquest_game("season21")
    text = " ".join(howto.sortie_lines(game.content, True, game.state.world))
    assert "越往對方老巢推越難推" not in text and "還沒人佔" in text


# ── 原 test_conquest_merge_c1.py（整檔搬進來） ──
# 領地爭奪：第一批的修正（FB-531、裁決 18）合進第二批之後疊起來的規則（計畫 6.2「合併 conquest-1 修正」，PM 2026-10-20），翻地與爭搶之後的樣子。
#
# - 攻城軍令記得到功、軍令卡列得出來的地方＝這一邊此刻進度最高、推得動的那幾塊（PM 2026-10-20 第 1 條；第二批是今天公告的目標），而且
#   `orders.siege_win` 也成立：打贏那裡的守軍就記功，中立駐軍也算（裁決 20）。
# - 敵方大本營與廣宗（搶不下來）不是目標：推不動、不列成攻城地點、下不了戰書；就算硬塞一條進度也不列。

def _siege(game, faction="guan", front="yingru"):
    s, c = game.state, game.content
    order = Order(id=f"t:{faction}:siege:{front}", template="siege", faction=faction, week=orders.period_of(s, c), front=front,
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    return order


def _out_of_contest(game) -> list[str]:
    c = game.content
    return [loc for loc in conquest.blocks(c) if not conquest.capturable(c, loc)]


def test_a_neutral_target_and_an_enemy_block_tied_at_the_top_are_both_listed():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "hilltop_wilds") is None and conquest.line_of(w, c, "hilltop_wilds") == "yingru"
    for loc in ("hilltop_wilds", "runan_wilds"):
        conquest.push(w, c, loc, "guan", "某", 15, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds", "runan_wilds"]


def test_a_win_at_the_top_neutral_target_credits_the_siege():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    conquest.push(game.state.world, game.content, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1  # 裁決 20：中立駐軍也算
    assert orders.win_counts(game.state, game.content, "guan", "hilltop_wilds")


def test_a_win_at_the_top_enemy_block_credits_the_siege():
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "runan_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.win_counts(game.state, game.content, "guan", "runan_wilds")
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_a_lower_block_does_not_count():
    """列與記同一個判斷：進度不是最高的那一塊不列、不記。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "hilltop_wilds", "guan", "某", 20, "attack")
    order = _siege(game)
    assert orders.siege_places(game.content, "guan", "yingru", game.state.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert game.state.player.name not in order.progress


@pytest.mark.parametrize("side", ["guan", "huang"])
def test_enemy_bases_and_guangzong_are_never_targets(side):
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    out = _out_of_contest(game)
    mine = {loc for loc in conquest.blocks(c) if conquest.holder(w, c, loc) == side}
    near = [loc for loc in out if conquest.holder(w, c, loc) != side and any(x in mine for x in conquest.adjacent(c, loc))]
    assert near  # 有搶不下來、又跟自家領地直通的敵方區塊（例：官軍的長社挨著黃巾別部營寨），這條才量得到東西
    assert not set(conquest.targets(w, c, side)) & set(out)
    assert not set(conquest.focus_blocks(w, c, side, "attack")) & set(out)
    for loc in near:
        assert conquest.push_problem(w, c, side, loc, "attack") == conquest.WHY_OUT
        assert conquest.letter_problem(w, c, side, loc, 1) == conquest.WHY_OUT


def test_a_forced_bar_at_an_enemy_base_is_still_not_a_siege_place():
    """硬塞一條進度（不經出陣）：黃巾別部營寨搶不下來，照樣不列。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "huangjin_camp", "guan", "某", 50, "attack")
    conquest.push(w, c, "runan_wilds", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]


# ── 原 test_conquest_siege_garrison.py（整檔搬進來） ──
# 領地爭奪：攻城軍令打贏那裡的守軍就記功，中立駐軍也算（計畫第八節裁決 20，PM 2026-10-21）。軍令卡列的、記功的、假人往哪裡走、發不發攻城
# 照舊問同一個判斷（`orders.siege_win`），不會列了卻記不到、或記得到卻沒列。翻地與爭搶（PM 2026-10-20 第 1 條）之後地點改讀成「這一邊此刻
# 進度最高、推得動的那一塊」（第二批是今天公告的目標）；開關關著一個字都不變（test_conquest_fb531_siege 的最後一條）。

def test_the_top_neutral_target_is_listed_and_credited():
    """官軍在荒丘（還沒人佔的中立地）的進度最高：在那裡打贏中立駐軍記攻城一次，軍令卡寫得出荒丘。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.holder(s.world, c, "hilltop_wilds") is None
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    assert orders.win_counts(s, c, "guan", "hilltop_wilds") and "hilltop_wilds" in orders.targets(s, c, "guan")
    how = atlas.siege_how(s, c, order)
    assert "荒丘" in how and "黃巾" not in how
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_a_captured_neutral_block_held_by_the_enemy_counts_too():
    """被敵方佔下的中立地站的照舊是中立駐軍：進度最高，打贏也算。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    s, c = game.state, game.content
    assert conquest.set_control(s.world, c, "hilltop_wilds", "huang")
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_a_line_with_only_neutral_targets_still_issues_a_siege():
    """一條線上碰得到的只有中立地（官軍在南陽）：照樣發得出攻城（_issuable 先看的就是 siege_places）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert "nanyang_road" in orders.siege_places(c, "guan", "nanyang", w)


def test_lower_blocks_do_not_count_until_they_are_the_top():
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    s, c = game.state, game.content
    conquest.push(s.world, c, "hilltop_wilds", "guan", "某", 20, "attack")
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    win_sortie(game)
    assert s.player.name not in order.progress
    conquest.push(s.world, c, "runan_wilds", "guan", "某", 30, "attack")
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["runan_wilds"]
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_card_without_a_pushable_place_does_not_point_anywhere():
    """這條線此刻沒有推得動的地方（全都剛易手）：卡上不指「到某一帶敵方的地盤出陣」——那裡打贏記不到。"""
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    for loc in conquest.targets(s.world, c, "guan"):
        conquest._fight(s.world, c, loc).flipped_at = s.world.time
    order = _siege(game)
    assert orders.siege_places(c, "guan", "yingru", s.world) == []
    how = atlas.siege_how(s, c, order)
    assert "地盤出陣" not in how and "推得動" in how


def test_own_and_unknown_factions_never_count():
    """判斷本身：中立（沒有陣營）的隊伍只在領地爭奪開著時算；自家、豪強的隊伍兩邊都不算。"""
    assert orders.siege_win("guan", None, True) and not orders.siege_win("guan", None)
    assert orders.siege_win("guan", "huang", True) and orders.siege_win("guan", "huang")
    assert not orders.siege_win("guan", "guan", True)
    assert not orders.siege_win("guan", "cao", True)


# ── 原 test_conquest_fb531_siege.py（整檔搬進來） ──
# FB-531：攻城軍令的地點只列打贏真的記得到的區塊（軍令卡、記功、假人同一個判斷）。
#
# 第二批起攻城地點是今天公告的目標（裁決 11），裁決 20（PM 2026-10-21）讓中立駐軍也算。翻地與爭搶（PM 2026-10-20 第 1 條）之後改讀成
# 「這一邊此刻進度最高、推得動的那一塊」：這幾條先把要比的區塊推到最高再比；列與記功照舊同一個判斷（FB-531 的教訓不變）。

def _hilltop_to_huang(game):
    w, c = game.state.world, game.content
    assert conquest.set_control(w, c, "hilltop_wilds", "huang")  # QA：管理者把荒丘定給黃巾
    for loc in ("hilltop_wilds", "runan_wilds"):  # 兩塊並列官軍此刻進度最高
        conquest.push(w, c, loc, "guan", "某", 20, "attack")
    return w, c


def test_a_captured_neutral_block_is_a_siege_place_since_ruling_20():
    game = conquest_game("season21")
    w, c = _hilltop_to_huang(game)
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds", "runan_wilds"]  # 裁決 20：中立駐軍也算


def test_the_card_names_only_where_a_win_counts():
    game = join(conquest_game("season21"), "guan")
    _hilltop_to_huang(game)
    order = _siege(game)
    how = atlas.siege_how(game.state, game.content, order)
    assert "汝南荒野" in how and "荒丘" in how and "嵩山深處" not in how


def test_bots_go_where_a_win_counts():
    game = join(conquest_game("season21"), "guan")
    s, c = game.state, game.content
    _hilltop_to_huang(game)
    _siege(game)
    assert orders.win_counts(s, c, "guan", "hilltop_wilds") and orders.win_counts(s, c, "guan", "runan_wilds")
    assert not orders.win_counts(s, c, "guan", "deep_mountain")  # 進度不是最高：記不到
    assert "hilltop_wilds" in orders.targets(s, c, "guan")


def test_every_listed_place_credits_a_sortie_win():
    """列出來的地方打贏一定記得到：在汝南荒野出陣攻打贏，那一道攻城記一次。"""
    game = go(join(conquest_game("season21"), "guan"), "runan_wilds")
    conquest.push(game.state.world, game.content, "runan_wilds", "guan", "某", 10, "attack")
    order = _siege(game)
    assert "runan_wilds" in orders.siege_places(game.content, "guan", "yingru", game.state.world)
    win_sortie(game)
    assert order.progress.get(game.state.player.name) == 1


def test_a_siege_is_issued_where_only_captured_neutral_blocks_are_enemy_held():
    """一條線上敵方只佔了中立地（黃巾在南陽拿下南陽官道）：照樣發攻城（中立駐軍也算）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_road", "huang")
    conquest.push(w, c, "nanyang_road", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "nanyang", w) == ["nanyang_road"]


# ── 原 test_conquest_fb565_defend.py（整檔搬進來） ──
# FB-565（PM 2026-10-20，dev/conquest-fix2 開發回報）：領地爭奪開著時，守城軍令卡的做法（atlas.order_how）與輿圖的守城標記
# （mapdata._order_marks）要跟實際記得到的一致——只寫、只標「自家今天被公告要攻的那一塊」（裁決 11、24）；今天沒有公告自家的區塊時，
# 卡上照實說今天沒有可守的，輿圖不標。同 FB-531 的教訓：列與記同一個判斷（orders.defend_places，記功、假人往哪走、卡、輿圖都讀它）。
# 關著的季（週末、14 天、21 天）一個字都不變。
# 翻地與爭搶（PM 2026-10-20 第 1 條）之後「被公告要攻的那一塊」換成「自家被推得最高、守得動的那一塊」（conquest.focus_blocks）：
# 前提從 announce（排進時程表，翻地之後等於那一塊被戰書凍結、守不動）改成對面在那裡推了一截（conquest_kit.press），斷言不動；
# 「打完、作罷就不算」換成「對面的進度被拉回零就不算」。卡上的字照翻地改（dev/flip-1 收尾）：「今天沒有…被公告要攻」換成「此刻沒有對面在推…」，
# 「被公告要攻的自家地方」換成「對面推得最高的幾處自家地方」（test_the_card_never_talks_about_announcements）。

GUAN_BLOCKS = ("yingchuan", "yingshui", "yingchuan_wilds", "songshan_foot", "yingchuan_academy", "guan_camp",
               "deep_mountain")  # 潁川汝南線上官軍的區塊（不含大本營長社；官軍大營、嵩山深處是區塊表 v3 給官軍的）


def _game_fb565defend(profile: str = "season21"):
    """領地爭奪開著、官軍的人；開季發的軍令清掉，只剩測試自己掛的（不然別的戰線的守城也算進 duty_counts）。"""
    game = join(conquest_game(profile), "guan")
    game.state.world.orders.clear()
    return game


def _defend(game, side="guan", front="yingru") -> Order:
    order = Order(id=f"t:{side}:defend", template="defend", faction=side, week=orders.period_of(game.state, game.content),
                  front=front, quota=5, text="守")
    game.state.world.orders.append(order)
    return order


def _marks(game, side="guan") -> set[str]:
    marks = mapdata._order_marks(game.state, game.content, side)
    return {loc for loc, word in marks.items() if word == mapdata.ORDER_WORDS["defend"]}


def _counts_at(game, order) -> set[str]:
    c, w = game.content, game.state.world
    return {loc for loc in c.locations if orders._counts(c, order, "duty", loc, None, None, None, None, None, w)}


def _agree(game, order, side="guan") -> set[str]:
    """卡上列的（defend_places）、輿圖標的、記得到的、假人往哪走的、duty_counts 的，是同一批地點；回那一批。"""
    c, w = game.content, game.state.world
    listed = set(orders.defend_places(c, w, order))
    assert _marks(game, side) == listed
    assert _counts_at(game, order) == listed
    assert set(orders.targets(game.state, c, side)) == listed
    assert {loc for loc in c.locations if orders.duty_counts(game.state, c, side, loc)} == listed
    return listed


def test_no_block_announced_the_card_says_so_and_the_map_marks_nothing():
    game = _game_fb565defend()
    order = _defend(game)
    assert _agree(game, order) == set()  # 修前輿圖標長社（自家大本營，記不到）
    text = atlas.order_how(game.state, game.content, order)
    assert text == atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(game.content, "yingru"))
    assert "此刻沒有" in text and "自家的地盤出陣" not in text  # 修前寫「在潁川汝南一帶自家的地盤出陣守一回…做一次記一次」


def test_one_announced_block_is_named_and_marked():
    game = _game_fb565defend()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    assert _agree(game, order) == {"yingchuan_wilds"}
    text = atlas.order_how(game.state, game.content, order)
    assert "潁川郊野" in text and "做一次記一次" in text and "此刻沒有" not in text
    assert "巡哨" in text and "出陣" in text
    assert mapdata._order_marks(game.state, game.content, "guan")["yingchuan_wilds"] == "守城"


def test_two_announced_blocks_are_both_named():
    game = _game_fb565defend()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    press(game, "yingshui", "huang")
    assert _agree(game, order) == {"yingchuan_wilds", "yingshui"}
    text = atlas.order_how(game.state, game.content, order)
    assert "潁川郊野" in text and "潁水河畔" in text


def test_many_announced_blocks_say_the_area():
    game = _game_fb565defend()
    order = _defend(game)
    for i, loc in enumerate(GUAN_BLOCKS[:3]):
        press(game, loc, "huang")
    assert _agree(game, order) == set(GUAN_BLOCKS[:3])
    text = atlas.order_how(game.state, game.content, order)
    assert text == atlas.DEFEND_AREA_CONQUEST.format(
        front=atlas.trend_name(game.content, "yingru"), act=atlas.DEFEND_ACT_SORTIE.format(duty="巡哨"))
    assert "對面推得最高" in text


def test_a_siege_that_is_over_or_called_off_no_longer_counts():
    game = _game_fb565defend()
    order = _defend(game)
    press(game, "yingchuan_wilds", "huang")
    assert _agree(game, order) == {"yingchuan_wilds"}
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "guan", "守將", 100, "hold")  # 拉回零
    assert _agree(game, order) == set()
    assert "此刻沒有" in atlas.order_how(game.state, game.content, order)


def test_a_block_my_own_side_is_attacking_is_not_one_to_defend():
    """官軍攻黃巾的區塊：那一塊是官軍要攻的，不是官軍要守的；黃巾那邊才是要守的。"""
    game = _game_fb565defend()
    order = _defend(game)
    huang_order = _defend(game, side="huang")
    press(game, "runan", "guan")  # 區塊表 v3 之前用汝南荒野（現在是中立地）
    assert _agree(game, order) == set()
    assert _agree(game, huang_order, side="huang") == {"runan"}


def test_other_fronts_are_not_listed():
    game = _game_fb565defend()
    order = _defend(game, front="nanyang")
    press(game, "yingchuan_wilds", "huang")  # 潁川汝南線上的，不是南陽線
    assert _agree(game, order) == set()


def test_every_location_agrees_between_card_map_credit_and_bots():
    """列與記同一個判斷：不管公告了哪幾塊，每一個地點上四個說法都一致（沒有列了卻記不到、記得到卻沒列）。"""
    game = _game_fb565defend()
    order = _defend(game)
    for loc in GUAN_BLOCKS:
        press(game, loc, "huang")
        _agree(game, order)
    assert conquest.holder(game.state.world, game.content, "changshe") == "guan"
    assert "changshe" not in _agree(game, order)  # 自家大本營搶不下來，從來不會被公告，也從來不在守城的地點裡


def test_the_card_never_talks_about_announcements():
    """翻地與爭搶（dev/flip-1 收尾）：投票與每天 22:00 的公告拿掉了，守城卡上不能再寫「被公告要攻」「每天 22:00 公告下一天的」——
    照翻地寫：對面此刻在推的自家地方，沒有就說此刻沒有對面在推的自家地方。"""
    game = _game_fb565defend()
    order = _defend(game)
    texts = [atlas.order_how(game.state, game.content, order)]  # 沒人在推
    for loc in GUAN_BLOCKS[:3]:
        press(game, loc, "huang")
        texts.append(atlas.order_how(game.state, game.content, order))  # 一處、兩處（寫地名）、三處（寫一帶）
    for text in texts:
        assert "公告" not in text and "今天" not in text, text  # 修前「今天沒有自家的地方被公告要攻…每天 22:00 公告下一天的」
    assert texts[0] == atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(game.content, "yingru"))
    assert texts[-1] == atlas.DEFEND_AREA_CONQUEST.format(
        front=atlas.trend_name(game.content, "yingru"), act=atlas.DEFEND_ACT_SORTIE.format(duty="巡哨"))


# ── 原 test_conquest_fb608_edge_credit.py（整檔搬進來） ──
# FB-608（QA 驗輿圖第三版第 1 批）：推滿易手的那一下、守到歸零的那一下，軍令記不到。
#
# `Game._squad_encounter` 與 `_sortie_hold` 都是先推進度、後記軍令，`orders._counts` 讀的是推完之後的清單（`conquest.focus_blocks`）：
# 易手的那一塊已經是自家的、在冷卻，不在攻的清單；拉到零的那一塊沒有條，不在守的清單——卡上列的地方，最關鍵的那一下反而不算。
# 修法（PM 2026-10-21）：記不記照出陣**之前**的清單判（列與記同一個判斷，同 FB-531、FB-565）。

def _order(game, template: str, side: str) -> Order:
    s, c = game.state, game.content
    s.world.orders.clear()  # 開季發的軍令清掉，只剩這一道
    order = Order(id=f"t:{side}:{template}", template=template, faction=side, week=orders.period_of(s, c), front="yingru",
                  quota=99, text="（測試）")
    s.world.orders.append(order)
    return order


def test_the_win_that_fills_the_bar_and_flips_counts_for_the_siege_order():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    w, c = game.state.world, game.content
    order = _order(game, "siege", "guan")
    conquest.push(w, c, "hilltop_wilds", "guan", "先鋒", 99.5, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["hilltop_wilds"]  # 卡上寫的就是這裡
    win_sortie(game)
    assert conquest.holder(game.state.world, c, "hilltop_wilds") == "guan"  # 這一下推滿、當場易手
    assert order.progress.get(game.state.player.name) == 1  # 修前 0：推完那一塊已經是自家的、在冷卻，不在攻的清單


def test_a_plain_win_still_counts_once():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    order = _order(game, "siege", "guan")
    win_sortie(game)
    assert conquest.holder(game.state.world, game.content, "hilltop_wilds") is None
    assert order.progress.get(game.state.player.name) == 1


def test_the_hold_that_pulls_the_last_bit_to_zero_counts_for_the_defend_order():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    w, c = game.state.world, game.content
    order = _order(game, "defend", "huang")
    conquest.push(w, c, "runan", "guan", "敵將", 0.4, "attack")
    assert orders.defend_places(c, w, order) == ["runan"]  # 卡上寫的就是這裡
    msgs = game.choose("act:train")  # 自家的區塊：出陣・守
    assert conquest.bars(game.state.world, "runan") == {}  # 這一下拉到零
    assert any("全數歸零" in m for m in msgs)
    assert order.progress.get(game.state.player.name) == 1  # 修前 0：拉到零的那一塊沒有條，不在守的清單


def test_a_hold_where_nobody_pushes_still_counts_nothing():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    order = _order(game, "defend", "huang")
    game.choose("act:train")
    assert order.progress == {}  # 沒人在推：出陣前就不在清單上，照舊記不到
