"""體力平衡（docs/superpowers/specs/2026-10-07-體力平衡-提案.md 第〇節，企劃者 2026-10-07 定案 A＋B＋C）：
上限 250、回體丹 150、探索遊歷 6／交友 3；事件失敗另扣的體力減半並寫在選項上；新手期體力回復 ×3、跟氣血一樣 18 季曆天。"""
import random

import pytest

from conftest import install_season_one, real_content
from tianxia import calendar, rules
from tianxia.engine import Game
from tianxia.events import choice_label, free_text_note, stamina_note
from tianxia.models import Check, Choice, Effect, FreeTextChoice

DAY = 86400


def test_the_decided_numbers_are_in_the_real_config():
    cfg = real_content().config
    assert cfg.stamina_max == 250 and cfg.stamina_pill_restore == 150
    assert cfg.action_cost == {"explore": 6, "train": 6, "socialize": 3}
    assert cfg.event_fail_stamina_scale == 0.5 and cfg.newbie_stamina_multiplier == 3
    assert cfg.newbie_days == cfg.newbie_stamina_days == 18


@pytest.mark.parametrize(("cost", "halved"), [(-15, -8), (-10, -5), (-5, -3), (-8, -4), (-1, -1), (0, 0), (10, 10)])
def test_failure_stamina_is_halved_rounding_half_up(content, cost, halved):
    content.config.event_fail_stamina_scale = 0.5
    assert rules.fail_stamina(cost, content) == halved


def test_a_failed_check_takes_the_halved_stamina(game):
    game.content.config.event_fail_stamina_scale = 0.5
    p = game.state.player
    p.stamina = 100.0
    effect = rules.failed(Effect(stamina=-15, text="摔了一跤。"), game.content)
    assert effect.stamina == -8 and effect.text == "摔了一跤。"
    assert "體力 -8" in game._apply(effect) and p.stamina == 92


def _check_choice(effect: int = 0, fail: int = 0) -> Choice:
    return Choice(text="翻牆進去", check=Check(stat="agi", difficulty=5),
                  effect=Effect(stamina=effect), fail_effect=Effect(stamina=fail))


def test_the_option_says_what_it_costs(content):
    content.config.event_fail_stamina_scale = 0.5
    assert stamina_note(_check_choice(fail=-15), content) == "（失手多耗體力 8）"
    assert stamina_note(_check_choice(effect=-5, fail=-15), content) == "（體力 -5，失手多耗體力 3）"
    assert stamina_note(_check_choice(effect=-10, fail=-10), content) == "（體力 -10）"  # 減半之後失手不比成功多扣
    assert stamina_note(Choice(text="連夜趕路追上去", effect=Effect(stamina=-10)), content) == "（體力 -10）"  # 選了就扣：照扣、不減半
    assert stamina_note(_check_choice(), content) == ""


def test_the_cost_rides_at_the_end_of_the_check_line(game):
    game.content.config.event_fail_stamina_scale = 0.5
    label = choice_label(_check_choice(fail=-10), game.state, game.content, game.world)
    assert label.startswith("翻牆進去（身法 5：") and label.endswith("）（失手多耗體力 5）")
    plain = Choice(text="連夜趕路追上去", effect=Effect(stamina=-10))
    assert choice_label(plain, game.state, game.content, game.world) == "連夜趕路追上去（體力 -10）"


def test_the_free_text_button_says_what_failing_costs(content):
    content.config.event_fail_stamina_scale = 0.5
    choice = FreeTextChoice(prompt="隨口應對", stat="wis", fail_effect=Effect(stamina=-15))
    assert free_text_note(choice, content) == "（失手多耗體力 8）"


def test_newbie_stamina_regen_triples_for_newbie_stamina_days(content, world):
    """新手期（從自己加入起 newbie_stamina_days 個季曆天）體力回復 ×3，跟打坐疊乘；過了恢復一倍。"""
    install_season_one(content)
    content.config.newbie_stamina_multiplier = 3
    game = Game.new(content, "新來", rng=random.Random(0), world=world)
    game.sync(1000.0)
    p = game.state.player
    day = DAY / calendar.cal_scale(content, game.state.world)
    gained = []
    for after in (content.config.newbie_stamina_days * day - 1, content.config.newbie_stamina_days * day + 1):
        game.state.world.time = p.joined_at + after
        p.stamina = 0.0
        game._advance_player_local(1800)
        gained.append(p.stamina)
    assert gained == [pytest.approx(30.0), pytest.approx(10.0)]  # 半小時：平常 10 點，新手期 30 點
    game.state.world.time = p.joined_at
    p.stamina, p.resting_since = 0.0, p.joined_at
    game._advance_player_local(1800)
    assert p.stamina == pytest.approx(60.0)  # 打坐 ×2 再乘新手 ×3


def test_the_newbie_period_is_about_thirteen_hours_on_a_weekend_season(content):
    """18 季曆天照季長縮：週末 2.5 天的季約 12.9 個現實小時，14 天的季 3 天。"""
    install_season_one(content)
    for days, hours in ((2.5, 12.857), (14, 72.0)):
        content.config.season_days = days
        assert 18 * DAY / calendar.cal_scale(content) / 3600 == pytest.approx(hours, abs=0.01)


def test_leaving_the_hut_fills_the_bigger_bar():
    """序章出師的獎勵要補滿體力（content.validate 檢查）：上限 250 時獎勵也是 250。"""
    c = real_content()
    last = c.tutorial.steps[c.tutorial.prologue_steps - 1]
    assert last.reward.stamina >= c.config.stamina_max == 250
