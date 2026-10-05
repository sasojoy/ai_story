"""探索的多人與 LLM 玩法 §8：事件的隨口應對（A）與地方痕跡（B）。"""
import random
from unittest import mock

import pytest

from conftest import FixedRandom
from test_content import copy_fixture, edit_json
from tianxia import bot, event_llm, team
from tianxia.battle_instance import DEFAULT_FREE_TEXT_SUCCESS_RATE
from tianxia.content import ContentError, load_content
from tianxia.engine import FREE_TEXT_OPTION, FreeTextRequest, Game
from tianxia.models import Condition, Effect, FreeTextChoice
from tianxia.ollama_client import OllamaClient
from tianxia.rules import (
    FREE_TEXT_MAX_RATE, FREE_TEXT_MIN_RATE, add_marks, apply_effect, check_condition, fill_marks, free_text_rate,
    fuzzy_count, rate_words,
)
from tianxia.team import PLAYER

DAY = 86400
GAMBLE = FreeTextChoice(
    prompt="自己想辦法……", stat="str", by="self",
    effect=Effect(text="醉漢被你唬住了。", stats={"good": 1}), fail_effect=Effect(text="醉漢一拳揮來。"),
)


@pytest.fixture
def gamble_game(game):
    """測試內容的「醉漢」事件多一個隨口應對，玩家正停在這則事件上。"""
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    return game


def strength(game) -> float:
    return team.check_value(game.state, game.content, game.world, PLAYER, "str")


# ── A 隨口應對：成功率 ─────────────────────────────────────


def test_rate_is_the_llm_rate_plus_four_per_point_of_the_stat_above_five(gamble_game):
    g = gamble_game
    expected = round(50 + (strength(g) - 5) * 4)
    assert free_text_rate(50, GAMBLE, g.state, g.content, g.world) == max(5, min(85, expected))


def test_rate_is_clamped_between_five_and_eighty_five(gamble_game):
    g = gamble_game
    assert free_text_rate(100, GAMBLE, g.state, g.content, g.world) == FREE_TEXT_MAX_RATE == 85
    assert free_text_rate(0, GAMBLE, g.state, g.content, g.world) == FREE_TEXT_MIN_RATE == 5
    g.state.player.stats["str"] = 0
    assert free_text_rate(20, GAMBLE, g.state, g.content, g.world) == 5


def test_rate_words_round_to_tenths():
    assert rate_words(5) == "成算一成不到"
    assert rate_words(58) == "成算六成"
    assert rate_words(85) == "成算九成"


def test_the_llm_falling_over_counts_as_forty(gamble_game):
    """conftest 讓 chat_structured 一律丟例外（連不上）；沒有 client 也一樣。"""
    event = gamble_game.content.events["drunk"]
    assert event_llm.assess_event_success_rate(OllamaClient(), event, "大喊官兵來了") == DEFAULT_FREE_TEXT_SUCCESS_RATE == 40
    assert event_llm.assess_event_success_rate(None, event, "大喊官兵來了") == 40


def test_the_llm_rate_is_clamped_to_zero_to_a_hundred(gamble_game):
    event = gamble_game.content.events["drunk"]
    judged = event_llm.SuccessRateJudgment(success_rate=140, reasoning="")
    with mock.patch.object(OllamaClient, "chat_structured", return_value=judged) as chat:
        assert event_llm.assess_event_success_rate(OllamaClient(), event, "大喊官兵來了") == 100
    prompt = chat.call_args.args[0][1]["content"]
    assert "醉漢" in prompt and "大喊官兵來了" in prompt


# ── A 隨口應對：選項與套用 ──────────────────────────────────


def test_an_event_with_free_text_offers_one_more_option(gamble_game):
    options = gamble_game.options()
    assert options[-1].id == FREE_TEXT_OPTION and options[-1].label == "自己想辦法……"
    assert gamble_game.event_free_text_prompt() == "自己想辦法……"
    gamble_game.state.pending_event = None
    assert gamble_game.event_free_text_prompt() is None


def test_pressing_the_option_only_asks_for_words(gamble_game):
    gamble_game.choose(FREE_TEXT_OPTION)
    assert gamble_game.state.pending_event == "drunk"


@pytest.mark.parametrize("text", ["", "   ", "字" * 21])
def test_empty_or_too_long_words_are_not_sent(gamble_game, text):
    assert gamble_game.free_text_request(text) is None


def test_a_success_applies_the_effect_and_writes_the_line_with_the_odds(gamble_game):
    g = gamble_game
    g.rng = FixedRandom(0.0)
    good = g.state.player.stats.get("good", 0)
    request = g.free_text_request(" 把酒罈砸在地上大喊官兵來了 ")
    assert request == FreeTextRequest(event_id="drunk", text="把酒罈砸在地上大喊官兵來了")
    g.answer_event(request, 60)
    rate = free_text_rate(60, GAMBLE, g.state, g.content, g.world)
    assert g.state.pending_event is None
    assert g.state.player.stats["good"] == good + 1
    entry = g.state.journal[0]
    assert entry.title == "醉漢・隨口應對" and entry.tag == "成功"
    assert f"你：「把酒罈砸在地上大喊官兵來了」（{rate_words(rate)}）" in entry.lines
    assert "醉漢被你唬住了。" in entry.lines


def test_a_failure_applies_the_fail_effect(gamble_game):
    g = gamble_game
    g.rng = FixedRandom(0.99)
    good = g.state.player.stats.get("good", 0)
    g.answer_event(g.free_text_request("求他放過我"), 85)
    assert g.state.player.stats.get("good", 0) == good
    assert g.state.journal[0].tag == "失敗"
    assert "醉漢一拳揮來。" in g.state.journal[0].lines


def test_nothing_applies_when_the_event_moved_on_during_the_assessment(gamble_game):
    g = gamble_game
    request = g.free_text_request("大喊官兵來了")
    g.state.pending_event = None  # 鎖外評估的時候，這則事件已經在別的分頁處理掉了
    good = g.state.player.stats.get("good", 0)
    msgs = g.answer_event(request, 85)
    assert "事情已經過去了" in "\n".join(msgs)
    assert g.state.player.stats.get("good", 0) == good


def test_without_a_judged_rate_the_engine_assesses_and_falls_back_to_forty(gamble_game):
    g = gamble_game
    g.answer_event(g.free_text_request("大喊官兵來了"))
    rate = free_text_rate(40, GAMBLE, g.state, g.content, g.world)
    assert f"（{rate_words(rate)}）" in g.state.journal[0].lines[0]


def test_the_narration_goes_between_the_words_and_the_result(gamble_game):
    g = gamble_game
    g.rng = FixedRandom(0.0)
    g.answer_event(g.free_text_request("大喊官兵來了"), 60)
    outcome = g.last_gamble
    assert (outcome.success, outcome.effect_text) == (True, "醉漢被你唬住了。")
    g.add_gamble_narration(outcome, "你扯開嗓子一喊。")
    lines = g.state.journal[0].lines
    assert lines.index("你扯開嗓子一喊。") == lines.index("醉漢被你唬住了。") - 1
    assert lines[lines.index("你扯開嗓子一喊。") - 1].startswith("你：「大喊官兵來了」")


def test_the_narration_is_dropped_when_another_entry_came_first(gamble_game):
    g = gamble_game
    g.answer_event(g.free_text_request("大喊官兵來了"), 60)
    outcome = g.last_gamble
    g.choose("act:explore")
    before = [list(e.lines) for e in g.state.journal]
    g.add_gamble_narration(outcome, "你扯開嗓子一喊。")
    assert [list(e.lines) for e in g.state.journal] == before


def test_bots_never_pick_the_free_text_option(gamble_game):
    free_only = [o for o in gamble_game.options() if o.id == FREE_TEXT_OPTION]
    assert bot.pick(gamble_game, free_only, random.Random(0)) is None
    for seed in range(20):
        assert bot.pick(gamble_game, gamble_game.options(), random.Random(seed)) != FREE_TEXT_OPTION


def test_server_bots_never_pick_the_free_text_option(gamble_game):
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    profile = BotProfile(personality="普通", seed=1)
    with mock.patch.object(Game, "choose", wraps=gamble_game.choose) as choose:
        for seed in range(10):
            gamble_game.state.pending_event = "drunk"
            bot_policy.take_turn(gamble_game, profile, random.Random(seed))
    assert FREE_TEXT_OPTION not in [c.args[0] for c in choose.call_args_list]


# ── B 地方痕跡 ───────────────────────────────────────────


def test_marks_count_once_per_person_per_day(state):
    add_marks({"town:棚屋": 2}, state)
    add_marks({"town:棚屋": 2}, state)
    assert state.world.marks == {"town:棚屋": 2}
    state.world.time += DAY
    add_marks({"town:棚屋": 1}, state)
    assert state.world.marks == {"town:棚屋": 3}


def test_effects_leave_marks_and_conditions_read_them(state, content, world):
    cond = Condition(marks_min={"town:棚屋": 2})
    assert not check_condition(cond, state)
    apply_effect(Effect(marks={"town:棚屋": 2}), state, content, world)
    assert check_condition(cond, state)
    assert not check_condition(Condition(marks_max={"town:棚屋": 1}), state)


@pytest.mark.parametrize("n, words", [
    (0, "還沒有人"), (1, "一兩個人"), (2, "一兩個人"), (3, "幾個人"), (9, "幾個人"), (10, "十來個人"),
    (19, "十來個人"), (20, "幾十個人"), (49, "幾十個人"), (50, "上百人"),
])
def test_fuzzy_counts(n, words):
    assert fuzzy_count(n) == words


def test_text_shows_a_fuzzy_count_and_never_names(state):
    state.world.marks["town:棚屋"] = 12
    assert fill_marks("已經有{marks:town:棚屋}來搭過手。", state) == "已經有十來個人來搭過手。"


def test_marks_live_in_the_season_and_are_cleared_with_it(content, world):
    world.seed_first_season(content)
    world.mutate_season(lambda season: season.marks.update({"town:棚屋": 5}))
    assert world.get_season().marks == {"town:棚屋": 5}
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=1.0)
    assert world.get_season().marks == {}


def _with_marks(root, write: dict | None = None, read: dict | None = None, text: str | None = None):
    def edit(events):
        drunk = events[0]
        if write is not None:
            drunk["choices"][1]["effect"]["marks"] = write
        if read is not None:
            drunk["choices"][2]["condition"]["marks_min"] = read
        if text is not None:
            drunk["text"] = text
    edit_json(root / "events" / "test.json", edit)


def test_thresholds_scale_up_with_the_server(tmp_path):
    root = copy_fixture(tmp_path)
    _with_marks(root, write={"town:棚屋": 1}, read={"town:棚屋": 3})
    edit_json(root / "config.json", lambda d: d.update(mark_threshold_scale=2.5))
    content = load_content(root)
    assert content.events["drunk"].choices[2].condition.marks_min == {"town:棚屋": 8}  # 3 × 2.5 無條件進位


def test_a_mark_written_and_read_loads(tmp_path):
    root = copy_fixture(tmp_path)
    _with_marks(root, write={"town:棚屋": 1}, text="棚屋前已有{marks:town:棚屋}。")
    assert load_content(root).events["drunk"].choices[1].effect.marks == {"town:棚屋": 1}


def test_a_mark_nobody_reads_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    _with_marks(root, write={"town:棚屋": 1})
    with pytest.raises(ContentError, match="沒有任何條件或文字讀它"):
        load_content(root)


def test_a_mark_nobody_writes_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    _with_marks(root, read={"town:棚屋": 3})
    with pytest.raises(ContentError, match="條件永遠不會成立"):
        load_content(root)


@pytest.mark.parametrize("write, match", [
    ({"nowhere:棚屋": 1}, "地點 nowhere 不存在"),
    ({"town": 1}, "地點 id:痕跡名"),
    ({"town:棚屋": 4}, "1～3"),
    ({"town:棚屋": -1}, "1～3"),
])
def test_bad_marks_are_rejected(tmp_path, write, match):
    root = copy_fixture(tmp_path)
    _with_marks(root, write=write, read={key: 1 for key in write})
    with pytest.raises(ContentError, match=match):
        load_content(root)


# ── A 隨口應對：內容檢查 ─────────────────────────────────────


def _with_free_text(root, **changes):
    free = {"prompt": "自己想辦法……", "stat": "str", "effect": {"text": "成了。", "stats": {"good": 1}}, "fail_effect": {}}
    free.update(changes)
    edit_json(root / "events" / "test.json", lambda d: d[0].update(free_text=free))


def test_a_free_text_within_the_best_check_loads(tmp_path):
    root = copy_fixture(tmp_path)
    _with_free_text(root)
    assert load_content(root).events["drunk"].free_text.stat == "str"


def test_free_text_cannot_pay_more_than_the_best_check(tmp_path):
    root = copy_fixture(tmp_path)
    _with_free_text(root, effect={"stats": {"good": 3}})  # 逼問成功給善名 +2
    with pytest.raises(ContentError, match="good \\+3"):
        load_content(root)


def test_free_text_cannot_give_more_insights_than_the_best_check(tmp_path):
    root = copy_fixture(tmp_path)
    _with_free_text(root, effect={"insights": ["feng"]})  # 醉漢事件的檢定選項沒有給意境
    with pytest.raises(ContentError, match="意境 1 個比檢定選項最多的 0 個還多"):
        load_content(root)


@pytest.mark.parametrize("field, value", [
    ("next_event", "chain_b"), ("recruit", "liu"), ("join_sect", "cloud"), ("flags_add", ["x"]), ("world_flags_add", ["x"]),
])
def test_free_text_cannot_chain_recruit_or_set_flags(tmp_path, field, value):
    root = copy_fixture(tmp_path)
    _with_free_text(root, fail_effect={field: value})
    with pytest.raises(ContentError, match=f"不能有 {field}"):
        load_content(root)


def test_free_text_stat_must_be_a_check_stat(tmp_path):
    root = copy_fixture(tmp_path)
    _with_free_text(root, stat="silver")
    with pytest.raises((ContentError, Exception)):
        load_content(root)
