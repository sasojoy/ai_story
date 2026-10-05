"""看過的事件下次更少出現（週末試玩項目 B）：抽事件的權重 × event_repeat_decay ^ 這個玩家這一季看過幾次。

計次在 Game._present：每一次事件真的成為玩家眼前的待處理事件才記一次（探索、交友、遊歷、召見、next_event 串接
全都走那裡），只是「進了候選清單」或被 pick_event 抽到但沒端出來不算。"""
import random

import pytest
from conftest import walk_to
from pydantic import ValidationError

from tianxia.engine import Game
from tianxia.events import event_weight, pick_event
from tianxia.models import Config, ExploreMix
from tianxia.state import GameState, new_game_state


class RecordingRandom(random.Random):
    """照常抽，但記下 choices 收到的權重。"""

    def __init__(self, seed: int = 0):
        super().__init__(seed)
        self.weights: list[list[float]] = []

    def choices(self, population, weights=None, **kwargs):
        self.weights.append(list(weights))
        return super().choices(population, weights=weights, **kwargs)


def _town_pool(content):
    """小鎮的探索事件原本只有醉漢；再加兩則可重複的，湊成三個候選。"""
    drunk = content.events["drunk"]
    for event_id, weight in (("peddler", 2.0), ("storyteller", 3.0)):
        content.events[event_id] = drunk.model_copy(update={"id": event_id, "title": event_id, "weight": weight})
    return ["drunk", "peddler", "storyteller"]


def test_a_new_player_has_not_seen_anything(state):
    assert state.player.event_seen == {}


def test_event_weight_halves_with_every_sighting(state, content):
    drunk = content.events["drunk"]
    assert content.config.event_repeat_decay == 0.5
    assert event_weight(drunk, state, content) == drunk.weight
    state.player.event_seen["drunk"] = 1
    assert event_weight(drunk, state, content) == drunk.weight * 0.5
    state.player.event_seen["drunk"] = 3
    assert event_weight(drunk, state, content) == drunk.weight * 0.125


def test_one_events_sightings_do_not_weigh_down_another(state, content):
    state.player.event_seen["drunk"] = 4
    others = _town_pool(content)[1:]
    assert [event_weight(content.events[i], state, content) for i in others] == [2.0, 3.0]


def test_the_qiyu_multiplier_stays_and_stacks_with_the_decay(state, content):
    scroll = content.events["scroll"]
    mult = content.config.qiyu_weight_multiplier
    assert event_weight(scroll, state, content) == scroll.weight * mult
    state.player.event_seen["scroll"] = 2
    assert event_weight(scroll, state, content) == scroll.weight * mult * 0.25


def test_pick_event_hands_the_decayed_weights_to_the_rng(state, content):
    _town_pool(content)
    state.player.event_seen = {"drunk": 1, "storyteller": 2}
    rng = RecordingRandom()
    pick_event(state, content, "explore", rng, pool="common")
    assert rng.weights == [[0.5, 2.0, 0.75]]


def test_a_seen_event_comes_up_less_often(state, content):
    """看過三次的醉漢（權重 1→0.125）：沒有遞減時佔 1/6，加權後只剩 0.125/5.125 ≈ 0.024。"""
    _town_pool(content)
    state.player.event_seen = {"drunk": 3}
    rng = random.Random(7)
    picks = [pick_event(state, content, "explore", rng, pool="common").id for _ in range(2000)]
    assert picks.count("drunk") / len(picks) < 0.06


def test_pick_event_never_counts_a_sighting_by_itself(state, content):
    """計次是事件真的端到玩家眼前時才記（Game._present），挑出來看看不算。"""
    _town_pool(content)
    rng = random.Random(0)
    for _ in range(10):
        pick_event(state, content, "explore", rng, pool="common")
    assert state.player.event_seen == {}


def test_a_very_often_seen_event_can_still_be_picked(state, content):
    """看過上千次（機器人整季亂逛才會）：0.5 ^ 1100 在浮點數裡是 0.0，總權重為 0 會讓 random.choices 丟 ValueError。
    權重壓低有下限，永遠留一點機會。"""
    state.player.event_seen = {"drunk": 1100}
    weight = event_weight(content.events["drunk"], state, content)
    assert 0 < weight < 1e-6
    assert pick_event(state, content, "explore", random.Random(0), pool="common").id == "drunk"


def test_the_floor_does_not_give_a_zero_weight_event_a_chance(state, content):
    """權重本來就是 0 的事件（內容用來關掉隨機抽到）不因為下限變成抽得到。"""
    content.events["drunk"] = content.events["drunk"].model_copy(update={"weight": 0.0})
    state.player.event_seen = {"drunk": 1100}
    assert event_weight(content.events["drunk"], state, content) == 0.0


def test_with_the_decay_at_one_the_pick_is_the_old_weighted_pick(state, content):
    """decay＝1.0 時完全等於舊的純權重抽法：同一個亂數序列抽出同一串。"""
    ids = _town_pool(content)
    content.config.event_repeat_decay = 1.0
    state.player.event_seen = {"drunk": 5, "peddler": 2, "storyteller": 9}  # 次數再多也不影響
    for seed in range(60):
        got = [pick_event(state, content, "explore", random.Random(seed), pool="common").id]
        old = random.Random(seed).choices(ids, weights=[content.events[i].weight for i in ids])
        assert got == old


def test_the_decay_must_be_above_zero_and_at_most_one():
    assert Config().event_repeat_decay == 0.5
    assert Config(event_repeat_decay=1.0).event_repeat_decay == 1.0
    for bad in (0, -0.5, 1.5):
        with pytest.raises(ValidationError):
            Config(event_repeat_decay=bad)


# ── 計次：每一次真的觸發才記一次 ──────────────────────────


def test_presenting_an_event_counts_one_sighting_each_time(game):
    event = game.content.events["drunk"]
    game._present(event)
    assert game.state.player.event_seen == {"drunk": 1}
    game._present(event)
    game._present(event)
    assert game.state.player.event_seen == {"drunk": 3}


def test_exploring_into_an_event_counts_it_once(game):
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert game.state.player.event_seen == {"drunk": 1}
    game.choose("choice:1")  # 選一個選項不再多記一次
    assert game.state.player.event_seen == {"drunk": 1}


def test_socializing_into_an_event_counts_it_once(game):
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    assert game.state.player.event_seen == {"join": 1}


def test_training_into_an_event_counts_it_once(game):
    """遊歷打完接戰後事件走 _train 的事件那一段、一樣經過 _present。夾具湖邊的遊歷事件只有 chain_a。"""
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"
    assert game.state.player.event_seen == {"chain_a": 1}


def test_a_next_event_chain_counts_each_event_it_shows(game):
    """next_event 串接出來的事件玩家也真的讀了、seen_events 也記，所以一樣計次。"""
    game._present(game.content.events["chain_a"])
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"
    assert game.state.player.event_seen == {"chain_a": 1, "chain_b": 1}


# ── 存檔與換季 ────────────────────────────────────────────


def test_old_saves_without_the_counter_load_with_an_empty_one(game):
    raw = game.state.model_dump(mode="json")
    del raw["player"]["event_seen"]
    assert GameState.model_validate(raw).player.event_seen == {}


def test_the_counter_survives_a_save_round_trip(game):
    game._present(game.content.events["drunk"])
    loaded = GameState.model_validate(game.state.model_dump(mode="json"))
    assert loaded.player.event_seen == {"drunk": 1}


def test_a_new_season_starts_the_counter_over(content, world):
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    player.state.player.event_seen = {"drunk": 6, "join": 1}
    player.state.player.seen_events = {"drunk", "join"}
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    assert player.state.player.season_number == 2
    assert player.state.player.event_seen == {}
    assert player.state.player.seen_events == set()
    assert new_game_state(content, "玩家").player.event_seen == {}
