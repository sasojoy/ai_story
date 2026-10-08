"""FB-112（QA 93e7037，2026-10-08）：第二批新手說明（tianxia/howto.py：主線小標、戰況圖卡、玩法說明的投靠與軍令、三方有什麼不同）
講得比規則寬。現在照程式與內容寫：

- 伏筆：只有官軍、黃巾做完能改寫一件大事（foreshadow.LOCK_SIDES）；散人拿不到片段、做不了最後一步（foreshadow.capable 要陣營對得上）；
  豪強做完只在揭曉時留名（公告與江湖史）、推一把割據，結果不變（timetable 的 third_party）。
- 推線：不是每一處都推（Location.train_trend 空著的不推，潁水河畔就是），寫「有些地方…（行動列底下那一行寫著）」。
- 軍令湊滿額度推一把：只對有推線軍令的陣營（orders.json 的 effect.trend）；豪強只有打擊（挫大勢人物的聲威）。
- 豪強操練：它能操練的地方（有它自己隊伍的地點）都沒有 train_trend，就照實說操練推不動。
- 散人可以臨時投效：到決戰的大區，挑交戰兩軍之一，只算那一場（試玩回饋 2026-10-08 的決戰規則）。
- 決戰的職位這一版不寫（控制者裁示：戰鬥那條線還在改）。

用真實內容（週末設定）；事實照內容與程式算，句子待 joy 潤：比的是有沒有說到那件事，盡量不鎖死字句。"""
from __future__ import annotations

import random
import re

from tianxia import foreshadow, howto, timetable
from tianxia.engine import Game
from tianxia.rules import STANCE_NAMES


def _quest(on):
    return "".join(howto.quest_help(on))


def _fronts(on):
    game = Game.new(on, "甲", rng=random.Random(0))
    return howto.fronts_help(game.state, on)[1]


def _sides_that_lock():
    return [timetable.SIDE_NAMES[s] for s in foreshadow.LOCK_SIDES]


def test_only_the_two_armies_can_rewrite_a_big_event(on):
    quest = _quest(on)
    before = quest[:quest.index("改寫")]
    assert all(name in before for name in _sides_that_lock())  # 「官軍、黃巾……能暗中改寫」
    hao = STANCE_NAMES["haoqiang"]
    assert hao in quest and "不改結果" in quest and "割據" in quest  # 豪強做完：留名、推割據，結果不變
    assert "散人" in quest and "伏筆" in quest[quest.index("散人"):]  # 散人拿不到伏筆


def test_pushing_a_front_is_only_some_places_and_the_note_row_says_which(on):
    quiet = [loc for loc in on.locations.values() if loc.enemies and not loc.train_trend]
    assert any(loc.id == "yingshui" for loc in quiet)  # 潁水河畔有對手、不推線：所以不能說「在戰線上遊歷打贏就推」
    for line in (_quest(on), _fronts(on), howto.join_lines(on, Game.new(on, "乙").state.world)[0]):
        assert "有些地方" in line and "行動列底下" in line, line
        assert "在戰線上遊歷打贏、操練，會把" not in line


def test_the_order_push_is_claimed_only_for_sides_whose_orders_push(on):
    pushers = {t.side for t in on.orders.templates if t.effect.trend > 0}
    assert pushers == {"guan", "huang"}
    line = _fronts(on)
    clause = line[:line.index("軍令湊滿額度")]
    assert all(STANCE_NAMES[s] in clause for s in pushers) and STANCE_NAMES["haoqiang"] not in clause
    on.orders.templates = [t for t in on.orders.templates if t.side != "huang" or t.kind == "strike"]  # 黃巾只剩打擊
    line = _fronts(on)
    assert STANCE_NAMES["huang"] not in line[:line.index("軍令湊滿額度")]


def _hao_row(on):
    rows = howto.faction_lines(on, Game.new(on, "丙").state.world)
    return next(r for r in rows if r.startswith("**地方豪強**"))


def test_the_warlords_drill_pushes_nothing_and_their_one_order_pushes_no_front(on):
    drill_places = [loc for loc in on.locations.values() if any(on.squads[s].faction == "haoqiang" for s in loc.enemies)]
    assert drill_places and not any(loc.train_trend for loc in drill_places)
    row = _hao_row(on)
    assert "操練" in row and "推不動" in row and "遊歷、操練推割據" not in row
    assert "軍令只有打擊" in row and "不推戰線" in row[row.index("軍令只有打擊"):]
    fronts = _fronts(on)
    assert "操練推不動" in fronts[fronts.index(STANCE_NAMES["haoqiang"]):]
    on.locations["haozu_fort"].train_trend = {"jizhou": 1}  # 哪天豪族塢堡會推線了：照實說操練也推
    assert "推不動" not in _hao_row(on) and "操練" in _hao_row(on)


def test_drifters_hear_they_can_enlist_for_one_battle(on):
    world = Game.new(on, "丁").state.world
    join = howto.join_lines(on, world)[0]
    tail = join[join.index("散人"):]
    assert "臨時投效" in tail and "只算那一場" in tail and "決戰" in tail and "大區" in tail


def _page(on):
    return howto.page(on, Game.new(on, "己").state.world, recruitable=False)


def test_the_how_to_page_says_only_some_places_push_too(on):
    """審查 M4：玩法說明「遊歷」那一項以前寫「打贏或操練多半還會推動戰局」——豪強的操練從來不推、潁水河畔什麼都不推。"""
    text = _page(on)
    assert "多半還會" not in text
    train = next(line for line in text.splitlines() if line.startswith("- **遊歷**"))
    assert "有些地方" in train and "行動列底下" in train


def test_the_how_to_page_does_not_promise_fragments_to_drifters(on):
    """審查 M4：「情誼夠深，他會跟你聊起…伏筆的片段」散人也看得到，可是散人拿不到片段（foreshadow.capable 要陣營對得上）。"""
    line = next(line for line in _page(on).splitlines() if "伏筆的片段" in line)
    assert "散人" in line[line.index("伏筆的片段"):] or "散人" in line[:line.index("伏筆的片段")], line


def test_the_number_of_rewritable_events_follows_the_lock_sides(on, monkeypatch):
    """審查 M4：「其中 N 件可以被關鍵伏筆改寫」數的是會鎖定大事的那兩方的鏈（timetable.SIDE_NAMES，跟 foreshadow.LOCK_SIDES 同一份），不另寫一份。"""
    events = lambda sides: len({c.event for c in on.foreshadows.chains if c.side in sides})  # noqa: E731
    assert howto._lockable(on) == events(set(foreshadow.LOCK_SIDES))  # noqa: SLF001
    monkeypatch.setattr(timetable, "SIDE_NAMES", {"haoqiang": "豪強"})  # 換一份：數字跟著換，不是寫死的兩方
    assert howto._lockable(on) == events({"haoqiang"}) != events(set(foreshadow.LOCK_SIDES))  # noqa: SLF001


def test_battle_roles_are_not_explained_yet(on):
    world = Game.new(on, "戊").state.world
    text = "".join(howto.join_lines(on, world) + howto.faction_lines(on, world) + howto.quest_help(on) + [_fronts(on)])
    assert "職位" not in text and not re.search(r"先鋒|主將|軍師", text)
