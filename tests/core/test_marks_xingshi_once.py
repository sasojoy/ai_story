"""減法季批 4 修正輪（PM 2026-10-25 第 1 件）：痕跡過門檻那一刻不再寫世界層一句，〈天下形勢〉的「痕跡」那一類是痕跡唯一進形勢的路——
所以每一條過門檻的痕跡都要恰好進一篇：不重複、不漏。

以前那一類的起點是「上一篇收下的世界秒」，上一篇開單到收下之間過門檻的那一條，靠世界層那一句從「天下大事」補進下一篇；世界層那一句拿掉之後
這一條兩邊都不寫。現在起點是 XingshiMark.fired（上一篇開單那一刻 WorldState.marks_fired 已經有幾條），按過門檻的先後切，不看世界秒
（同一個世界秒過門檻的兩條也分得開）。用正式內容 season21（減法季開、領地爭奪開、〈天下形勢〉開）的一局。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, join
from tianxia import xingshi
from tianxia.state import XingshiMark


def _game():
    game = join(conquest_game("season21", xingshi=True), "huang")
    game._xingshi_start()
    game._save_season()
    return game


def _rule_text(rule):
    return rule.xingshi or rule.rumor


def _fire(game, rule):
    """這條痕跡到門檻（存季那一下 marks.fire_due 發）。"""
    game.state.world.marks[rule.mark] = rule.threshold
    game._save_season()
    assert rule.mark in game.state.world.marks_fired


def _open(game, key):
    game._xingshi_open(key)
    game._save_season()
    return list(game.state.world.xingshi_ticket.facts)


def _accept(game):
    game._xingshi_finish(None)
    game._save_season()


@pytest.mark.parametrize("step", [0.0, 600.0], ids=["same-world-second", "time-passes"])
def test_a_mark_fired_between_open_and_accept_goes_into_the_next_essay(step):
    """開單到收下之間過門檻的那一條會進下一篇（以前靠世界層那一句補，拿掉之後兩邊都不寫）；每一條恰好進一篇。
    step 是 0：每一步都在同一個世界秒上（以前拿世界秒比，邊界上不是重複就是漏）。"""
    game = _game()
    a, b, c, d = game.content.mark_rules[:4]
    tick = lambda: setattr(game.state.world, "time", game.state.world.time + step)  # noqa: E731

    _fire(game, a)  # 開第一單之前
    tick()
    first = _open(game, 1)
    assert _rule_text(a) in first
    tick()
    _fire(game, b)  # 第一單開著、還沒收下
    assert game.state.world.xingshi_ticket is not None
    tick()
    _accept(game)
    tick()
    _fire(game, c)  # 收下之後
    tick()
    second = _open(game, 2)
    assert [_rule_text(r) in second for r in (a, b, c)] == [False, True, True]  # 開單到收下之間的 b 在這一篇
    _accept(game)
    third = _open(game, 3)
    assert not [r for r in (a, b, c) if _rule_text(r) in third]  # 都寫過了：沒有新的就一條也不寫
    _fire(game, d)
    _accept(game)
    fourth = _open(game, 4)
    assert _rule_text(d) in fourth and not [r for r in (a, b, c) if _rule_text(r) in fourth]

    for rule in (a, b, c, d):  # 四條各恰好進一篇
        assert sum(_rule_text(rule) in facts for facts in (first, second, third, fourth)) == 1
        assert sum(facts.count(_rule_text(rule)) for facts in (first, second, third, fourth)) == 1


def test_two_marks_fired_in_the_same_second_split_between_two_essays():
    """同一個世界秒過門檻的兩條，一條在開單之前、一條在開單之後（同一個世界秒）：各進一篇，不重複不漏。"""
    game = _game()
    a, b = game.content.mark_rules[:2]
    _fire(game, a)
    first = _open(game, 1)
    _fire(game, b)  # 世界秒沒動
    assert game.state.world.marks_fired[a.mark] == game.state.world.marks_fired[b.mark]
    _accept(game)
    second = _open(game, 2)
    assert (_rule_text(a) in first, _rule_text(b) in first) == (True, False)
    assert (_rule_text(a) in second, _rule_text(b) in second) == (False, True)


def test_the_world_layer_rumor_is_gone_so_the_rumor_category_does_not_carry_marks():
    """過門檻那一刻只有地方傳聞；〈天下形勢〉的「天下大事」那一類讀的是世界層的傳聞，痕跡不在裡面。"""
    game = _game()
    rule = game.content.mark_rules[0]
    skipped = len(game.state.world.rumors)
    _fire(game, rule)
    rumors = game.state.world.rumors[skipped:]
    assert [(r.layer, r.text) for r in rumors if r.text == rule.rumor] == [("local", rule.rumor)]
    assert not [r for r in rumors if r.layer == "world"]
    assert _rule_text(rule) in _open(game, 1)  # 痕跡那一類照舊把它寫進這一篇


def test_the_start_is_recorded_when_the_essay_opens_and_only_when_something_fired():
    game = _game()
    assert game.state.world.xingshi_mark.fired == 0
    assert "fired" not in game.state.world.xingshi_mark.model_dump()  # 沒有痕跡過門檻（或關著）：存檔一個鍵都不多
    a, b = game.content.mark_rules[:2]
    _fire(game, a)
    _open(game, 1)
    reloaded = game.world.get_season()
    assert reloaded.xingshi_mark.fired == 1 and reloaded.xingshi_mark.model_dump()["fired"] == 1  # 存得進去、讀得回來
    _accept(game)
    _fire(game, b)
    _open(game, 2)
    assert game.world.get_season().xingshi_mark.fired == 2


def test_the_mark_model_adds_no_key_until_used():
    assert XingshiMark().model_dump() == {"log": 0, "rumors": 0, "lines": {}}
    assert XingshiMark().model_dump_json() == '{"log":0,"rumors":0,"lines":{}}'
    mark = XingshiMark(log=1, rumors=2, lines={"nanyang": 30}, fired=3)
    assert XingshiMark.model_validate_json(mark.model_dump_json()) == mark


def test_facts_without_a_start_or_with_marks_off_do_not_read_marks():
    game = _game()
    rule = game.content.mark_rules[0]
    _fire(game, rule)
    w = game.state.world
    assert _rule_text(rule) not in xingshi.facts(w, game.content, [], {}, len(w.rumors))  # 沒給起點：一個字不變
    assert _rule_text(rule) in xingshi.facts(w, game.content, [], {}, len(w.rumors), marks_from=0)
    game.content.config.jianfa.marks_visible = False
    assert _rule_text(rule) not in xingshi.facts(w, game.content, [], {}, len(w.rumors), marks_from=0)
