"""開局第一分鐘（減法季整合設計 6.7，批 7 前半；tianxia/opening.py、content/opening.json）：減法季的新角色不進草廬，
站在潁川城門口看旁白、三選一定起手屬性，選完那位人物的信到了（附把信送到長社的委託），信收起來本週卡才出現、第一件就是這封信；
走到長社就算辦成。開關關著（週末、舊的季）照舊走草廬。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import letters, opening, prologue, weekcard
from tianxia.engine import Game


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    return c


def _new(content, name="沈浪", **kw):
    return Game.new(content, name, rng=random.Random(0), **kw)


def test_a_new_player_starts_at_the_gate_with_the_three_way_choice_and_no_hut(on):
    g = _new(on, prologue=True)
    s = g.state
    assert opening.on(on, s.world)
    assert s.player.location == on.scenario.start_location and s.pending_event == on.opening.event
    assert not prologue.active(s, on) and prologue.onboard_step(s, on) is None  # 草廬與老周那幾步都略過
    assert s.player.stamina == on.config.stamina_max
    assert [o.id for o in g.options()] == ["choice:0", "choice:1", "choice:2"]
    assert weekcard.week_card(g, g.status_data(), g.orders_view()) is None and weekcard.sides_card(g) is None  # 選完才畫
    assert not s.player.letters


def test_each_choice_gives_two_points_and_brings_that_persons_letter_with_the_errand(on):
    for i, sender in enumerate(on.opening.senders):
        g = _new(on, name=f"甲{i}", prologue=True)
        s = g.state
        before = dict(s.player.stats)
        msgs = g.choose(f"choice:{i}")
        gained = {k: s.player.stats[k] - before[k] for k in ("str", "agi", "con", "wis") if s.player.stats[k] != before[k]}
        assert sum(gained.values()) == 2 and all(v == 1 for v in gained.values())
        assert sender.flag in s.player.flags and s.pending_event is None
        letter = opening.letter_of(s, on)
        assert letter is not None and letter.sender == sender.figure and letter.kind == opening.KIND and not letter.read
        assert letter.task is not None and letter.task.kind == "escort" and letter.task.end == on.opening.end
        assert letter.task.figure == sender.figure and letter.task.motive == "委託"
        assert on.locations[on.opening.end].name in letter.text and "{" not in letter.text
        who = on.characters[sender.figure].name
        assert any(who in m and "託你把一封信送到" in m for m in msgs)
        assert any(who in line for line in s.journal[0].lines)  # 寫在選了那一顆的那一則紀錄裡
        assert opening.errand_live(s, on)
        view = letters.view(s, on)
        assert view["open"] is True and view["task"]["live"] and view["sender"] == who


def test_the_week_card_appears_after_the_choice_with_the_errand_first(on):
    g = _new(on, prologue=True)
    g.choose("choice:0")
    status = g.status_data()
    card = weekcard.week_card(g, status, g.orders_view())
    assert card is not None and weekcard.sides_card(g) is not None
    assert card["steps"][0]["kind"] == "errand" and "長社" in card["steps"][0]["text"] and card["steps"][0]["who"] == "傅燮"
    assert any(s["kind"] == "newbie" for s in card["steps"])  # 新手八步退到本週卡與「為什麼」


def test_walking_to_changshe_completes_the_errand_with_silver_and_affinity(on):
    g = _new(on, prologue=True)
    s = g.state
    g.choose("choice:0")
    silver, aff = s.player.stats.get("silver", 0), s.player.affinities.get("fuxie", 0)
    assert s.player.journey is None
    g.travel(on.opening.end)
    for _ in range(8):
        g.sync(g.now + 3600)
        if s.player.location == on.opening.end:
            break
    assert s.player.location == on.opening.end and not opening.errand_live(s, on)
    assert s.player.stats["silver"] - silver == on.config.figure_life.commission_silver
    assert s.player.affinities["fuxie"] - aff == on.config.figure_life.commission_affinity


def test_the_errand_has_the_openings_own_deadline(on):
    g = _new(on, prologue=True)
    g.choose("choice:1")
    task = opening.letter_of(g.state, on).task
    assert task.expires == pytest.approx(g.state.world.time + on.opening.days * 86400)


def test_the_letter_is_rewritten_by_the_model_in_the_senders_voice_or_kept_as_written(on):
    g = _new(on, prologue=True)
    g.choose("choice:2")
    note = g.letter_request()
    assert note is not None and note.kind == opening.KIND and note.sender == "zhujun" and "長社" in note.task
    assert g.apply_letter(note, "") is False and opening.letter_of(g.state, on).written  # 寫不出來：照固定句、不再叫
    g2 = _new(on, name="乙", prologue=True)
    g2.choose("choice:2")
    note2 = g2.letter_request()
    assert g2.apply_letter(note2, "少俠，替我跑一趟長社。") and opening.letter_of(g2.state, on).text == "少俠，替我跑一趟長社。"


def test_bots_take_the_same_road_and_scripts_do_not(on):
    bot = _new(on, name="假的", graduated=True)
    assert bot.state.pending_event == on.opening.event and bot.state.player.location == on.scenario.start_location
    plain = _new(on, name="腳本")
    assert plain.state.pending_event is None and not plain.state.player.letters


def test_with_the_rule_off_a_new_player_still_goes_to_the_hut():
    c = real_content()
    c.config.auto_open_first_season = True
    assert not c.config.jianfa.enabled
    g = _new(c, prologue=True)
    assert not opening.on(c, g.state.world) and prologue.active(g.state, c)
    assert g.state.pending_event == c.tutorial.start_event


def test_the_sub_switch_turns_the_opening_off_on_its_own(on):
    on.config.jianfa.opening = False
    g = _new(on, prologue=True)
    assert prologue.active(g.state, on) and g.state.pending_event == on.tutorial.start_event
