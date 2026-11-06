"""女子與隱線（features/heroines）：葉三娘走完〈渡口帳〉才出現在孟津渡；成人內容預設關，開了、結局對、情誼到了才有隱線兩段；
給模型的提示與寫回來的過濾照段落的尺度（甲）；假人不走；換季帶開關、隱線重來。用正式內容（season21）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import explore_one
from tianxia.features.heroines import actions, rules
from tianxia.models import Condition
from tianxia.rules import day_seconds
from tianxia.state import StoryProgress

L, YE = "yesanniang", "yesanniang"
FORD, HILL = "mengjin_ford", "beimang_hill"


def _game(loc=FORD):
    game = ready(jianfa_game(), side="guan", loc=loc)
    game.sync(game.now)
    return game


def _ended(game, ending: str, affinity: int = 0):
    game.state.player.storylines[L] = StoryProgress(line=L, ending=ending, ended_at=game.state.world.time)
    game.state.player.affinities[YE] = affinity


def _go(game, loc: str, wait: float, event: str):
    s = game.state
    s.world.time += int(wait * day_seconds(game.content, s.world)) + 1
    s.player.location, s.player.journey = loc, None
    game.choose(f"story:{L}")
    assert s.pending_event == event


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def test_she_is_not_at_the_ford_until_her_story_ends_in_one_that_keeps_her():
    game = _game()
    assert YE not in game._figures_here()
    _ended(game, "late")  # 帳沒送到：她不留
    assert YE not in game._figures_here()
    _ended(game, "chuan")
    assert YE in game._figures_here()
    game.state.player.location = HILL
    assert YE not in game._figures_here()


@pytest.mark.slow
def test_the_ledger_walked_to_the_end_where_the_boat_comes_back():
    game = _game()
    s, p = game.state, game.state.player
    start = game.content.storylines[L].start
    start.chance, start.condition = 1.0, Condition()
    with mock.patch.object(explore_one, "draw", return_value=explore_one.MATERIAL):
        game.choose("act:explore")
    assert s.pending_event == "yesanniang_1"
    game.choose("choice:0")  # 我替妳送
    _go(game, HILL, 0, "yesanniang_2")
    game.choose("choice:0")  # 打開來看
    _go(game, HILL, 0.25, "yesanniang_3")
    game.choose("choice:2")  # 不收
    _go(game, FORD, 0.25, "yesanniang_4")
    labels = [o.label for o in game.options(odds=False)]
    assert "把炭寫的那張遞給軍候" not in labels and "照你記得的真日子，說給軍候聽" in labels
    game.choose("choice:1")
    game.sync(game.now)
    assert p.storylines[L].ending == "chuan" and p.affinities[YE] > 0
    assert YE in game._figures_here()


def test_the_hidden_line_needs_the_switch_the_ending_and_the_affinity():
    game = _game()
    _ended(game, "chuan", 70)
    assert not any(i.startswith("heroines:") for i in _ids(game))  # 預設關：什麼都沒有
    actions.set_adult(game, True)
    assert "heroines:open:yesanniang" in _ids(game)
    _ended(game, "cuo", 90)  # 她心裡還有葉樁：不開
    assert not any(i.startswith("heroines:") for i in _ids(game))
    _ended(game, "shao", 69)
    assert not any(i.startswith("heroines:") for i in _ids(game))


def test_two_scenes_in_order_and_a_decline_waits_a_day():
    game = _game()
    p = game.state.player
    actions.set_adult(game, True)
    _ended(game, "shao", 90)
    game.choose("heroines:open:yesanniang")
    assert _ids(game) == ["heroines:yes", "heroines:no"]
    game.choose("heroines:no")
    assert p.heroines.steps == {} and "heroines:open:yesanniang" not in _ids(game)  # 婉拒：今天不再問
    game.state.world.time += int(day_seconds(game.content, game.state.world)) + 1
    game.choose("heroines:open:yesanniang")
    game.choose("heroines:yes")
    assert p.heroines.steps == {YE: 3}
    game.choose("heroines:open:yesanniang")  # 情誼 90：第四段接著端得出來
    assert game.state.player.heroines.scene == "yesanniang:4"
    game.choose("heroines:yes")
    assert p.heroines.steps == {YE: 4} and rules.next_scene(game.state, game.content, YE) is None


def test_turning_the_switch_off_hides_the_scene_in_front_of_you():
    game = _game()
    actions.set_adult(game, True)
    _ended(game, "chuan", 80)
    game.choose("heroines:open:yesanniang")
    actions.set_adult(game, False)
    assert game.state.player.heroines.scene is None and not any(i.startswith("heroines:") for i in _ids(game))


def test_bots_never_open_it():
    game = _game()
    game.state.player.bot = True
    assert actions.set_adult(game, True) == [rules.NO_BOT] and not game.state.player.heroines_adult
    assert actions.status(game) == {}


def test_the_prompt_says_who_she_is_and_how_far_it_may_go():
    game = _game()
    s, c = game.state, game.content
    assert rules.prompt_lines(s, c, "luzhi") == "" and rules.role(c, "luzhi") == rules.ROLE_REAL
    _ended(game, "chuan", 90)
    text = rules.prompt_lines(s, c, YE)
    assert "官倉把阿稻還給了她" in text and "不寫調情" in text and rules.role(c, YE) == rules.ROLE_OWN
    actions.set_adult(game, True)
    assert "不寫調情" in rules.prompt_lines(s, c, YE)  # 開了、還沒應下第三段：照舊只寫交情
    s.player.heroines.steps[YE] = 4
    text = rules.prompt_lines(s, c, YE)
    assert "已經是相好" in text and "寫到熄燈為止" in text and "成年人" in text


def test_what_comes_back_is_filtered_by_the_step():
    game = _game()
    s, c = game.state, game.content
    _ended(game, "chuan", 90)
    nar, opts, said, blocked = rules.clean(s, c, YE, "她靠過來吻了你。", ["說酒", "問船", "看河"], "")
    assert blocked and nar == rules.FALLBACK.format(name="葉三娘")
    actions.set_adult(game, True)
    s.player.heroines.steps[YE] = 3
    nar, opts, said, blocked = rules.clean(s, c, YE, "她靠過來吻了你。", ["說酒", "問船", "看河"], "")
    assert not blocked  # 第三段：到親吻為止
    nar, opts, said, blocked = rules.clean(s, c, YE, "燈下。", ["替她寬衣", "問船", "看河"], "妳還是少女")
    assert blocked and opts == [rules.FALLBACK_OPTION, "問船", "看河"] and said == "……"
    assert rules.clean(s, c, "luzhi", "強迫", [], "") == ("強迫", [], "", False)  # 不是女子：原樣


def test_the_switch_carries_into_the_next_season_and_the_line_starts_over():
    game = _game()
    old = game.state.model_copy(deep=True)
    old.player.heroines_adult, old.player.heroines.steps = True, {YE: 4}
    game.state.player.heroines.steps = {}
    actions.on_season_start(game, old)
    assert game.state.player.heroines_adult and game.state.player.heroines.steps == {}


def test_the_settings_row_shows_the_switch():
    game = _game()
    assert actions.status(game) == {"heroines": {"adult": False}}
    actions.set_adult(game, True)
    assert actions.status(game) == {"heroines": {"adult": True}}
