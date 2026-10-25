"""俠寇選項（名聲設計 5.3、十一之二 5B）與俠寇的條件（virtue_path／virtue_min）。"""
import random

from conftest import real_content, renown_unscaled

from tianxia import renown, rules
from tianxia.engine import Game
from tianxia.models import Choice, Condition, Effect, VirtueNeed
from tianxia.state import new_game_state


def _game():
    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    return g


def _with_needs(g, event_id, need=("俠", 2)):
    ev = g.content.events[event_id]
    ev.choices.append(Choice(text="仗義出手", needs=VirtueNeed(path=need[0], tier=need[1]), effect=Effect(stats={"good": 3})))
    g.state.pending_event = event_id
    return [o for o in g.options() if o.id == f"choice:{len(ev.choices) - 1}"]


def test_greyed_with_the_reason_then_open_with_the_mark():
    g = _game()
    (opt,) = _with_needs(g, "rn_mkt_rice")
    assert (opt.enabled, opt.tag, opt.note) == (False, "俠", "要一方豪俠才做得來")
    g.state.player.stats["good"] = 15
    (opt,) = [o for o in g.options() if o.label == "仗義出手"]
    assert (opt.enabled, opt.tag, opt.note) == (True, "俠", "")


def test_a_greyed_one_cannot_be_chosen():
    g = _game()
    (opt,) = _with_needs(g, "rn_mkt_rice")
    good = g.state.player.stats.get("good", 0)
    g.choose(opt.id)
    assert g.state.player.stats.get("good", 0) == good and g.state.pending_event == "rn_mkt_rice"


def test_switch_off_hides_it():
    g = _game()
    g.content.config.renown.virtue_choices = False
    assert _with_needs(g, "rn_mkt_rice") == []


def test_virtue_conditions():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats["good"] = 15
    assert rules.check_condition(Condition(virtue_path="俠", virtue_min=2), s, c)
    assert not rules.check_condition(Condition(virtue_path="寇"), s, c)
    assert not rules.check_condition(Condition(virtue_min=3), s, c)
    assert not rules.check_condition(Condition(virtue_path="俠"), s, None)
    c.config.renown.titles = False
    assert not rules.check_condition(Condition(virtue_path="俠"), s, c)


def test_the_virtue_perks_name_the_choices_only_when_content_has_them():
    c = renown_unscaled(real_content("week7"))
    for ev in c.events.values():
        ev.choices = [ch for ch in ev.choices if ch.needs is None]
    assert "事件裡多出俠的做法" not in renown.virtue_perks(c, "俠", 1)
    c.events["rn_mkt_rice"].choices.append(Choice(text="仗義出手", needs=VirtueNeed(path="俠", tier=1)))
    assert "事件裡多出俠的做法" in renown.virtue_perks(c, "俠", 1) and "事件裡多出寇的做法" not in renown.virtue_perks(c, "寇", 1)
