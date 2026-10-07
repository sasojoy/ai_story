"""體力平衡（docs/superpowers/specs/2026-10-07-體力平衡-提案.md 第〇節，企劃者 2026-10-07 定案 A＋B＋C）：
上限 250、回體丹 150、探索遊歷 6／交友 3；事件失敗另扣的體力減半並寫在選項上；新手期體力回復 ×3、跟氣血一樣 18 季曆天。"""
import random

import pytest

from conftest import FixedRandom, install_season_one, real_content, walk_to
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


# ── 企劃者裁決 E6（2026-10-07）：劇情戰打輸另扣的體力減半、寫在開打的選項上 ─────────────────
# 「劇情戰打輸另外扣的體力，要減半，或者是改其他的懲罰。」減半走檢定失敗同一個函式（rules.failed → fail_stamina，
# event_fail_stamina_scale、四捨五入）；選項上照 stamina_note 的寫法寫「（輸了多耗體力 N）」（新寫，待 joy 潤），
# N 是縮過、比打贏那一邊多扣的部分（同「失手多耗體力」）。「改成別的懲罰」是內容的事，列在 joy 的清單上。


def _story_fight(game, win=0, lose=-15, squad="boss"):
    """測試內容的「挑戰」（湖邊交友遇上翻江龍，應戰是劇情戰）：打贏、打輸各扣多少體力照參數；squad 換成 thug 就打得贏。"""
    game.content.config.event_fail_stamina_scale = 0.5
    choice = game.content.events["duel"].choices[0]
    choice.combat = squad
    choice.effect = choice.effect.model_copy(update={"stamina": win})
    choice.fail_effect = choice.fail_effect.model_copy(update={"stamina": lose})
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.state.player.stamina = 100.0
    return choice


def _fight_label(game, odds):
    return next(o.label for o in game.options(odds=odds) if o.id == "choice:0")


def test_a_lost_story_fight_takes_half(game):
    _story_fight(game, lose=-15)
    game.choose("choice:0")  # 應戰翻江龍：必敗
    record = game.state.battles[0]
    assert record.tier == "落敗"
    assert game.state.player.stamina == 100 - 8  # 15 減半、四捨五入是 8
    assert "體力 -8" in record.changes


def test_the_number_on_the_option_is_what_a_loss_takes(game):
    _story_fight(game, lose=-15)
    assert _fight_label(game, odds=True).endswith("）（輸了多耗體力 8）")  # 對手與勝算那一個括號之後
    assert _fight_label(game, odds=False) == "應戰（輸了多耗體力 8）"
    game.choose("choice:0")
    assert 100 - game.state.player.stamina == 8


def test_a_won_story_fight_is_unaffected(game):
    """打贏照打贏那一邊扣（選了就扣的不減半）；選項上兩樣都寫：贏了也扣的寫「體力 -N」，輸了多扣的只寫多出來的那一份。"""
    rules.learn_skill(game.state, game.content, "fist")
    _story_fight(game, win=-5, lose=-15, squad="thug")
    assert _fight_label(game, odds=False) == "應戰（體力 -5，輸了多耗體力 3）"
    game.rng = FixedRandom(1.0)  # 最佳運氣：穩穩打贏
    game.choose("choice:0")
    assert game.state.battles[0].tier in ("大勝", "險勝")
    assert game.state.player.stamina == 100 - 5


def test_a_story_fight_that_costs_no_stamina_shows_no_note(game):
    _story_fight(game, lose=0)
    assert _fight_label(game, odds=False) == "應戰"
    assert "多耗" not in _fight_label(game, odds=True) and not _fight_label(game, odds=True).endswith("）（")
    game.choose("choice:0")
    assert game.state.player.stamina == 100


def test_the_story_fight_note_reads_like_the_check_note(content):
    content.config.event_fail_stamina_scale = 0.5
    fight = Choice(text="拔刀", combat="boss", fail_effect=Effect(stamina=-15))
    assert stamina_note(fight, content) == "（輸了多耗體力 8）"
    assert stamina_note(fight.model_copy(update={"fail_effect": Effect(stamina=-10)}), content) == "（輸了多耗體力 5）"


def test_real_story_fights_show_the_halved_loss(on):
    """真實內容（減半 0.5）：狼群那一戰打輸另扣 15，選項上寫 8。"""
    game = Game.new(on, "甲", rng=random.Random(0))
    game.state.pending_event = "wolves"
    choice = on.events["wolves"].choices[0]
    assert choice.combat and choice.fail_effect.stamina == -15
    assert next(o.label for o in game.options(odds=True) if o.id == "choice:0").endswith("（輸了多耗體力 8）")
