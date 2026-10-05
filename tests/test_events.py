import json
import random

from tianxia.events import (
    choice_hint, choice_label, event_matches_location, has_events_here, pick_event, rotation_pool, visible_choices,
)
from tianxia.models import CheckVoice, CheckVoiceBand, Choice, Event
from tianxia.state import GameState


def test_location_matching(content):
    town, lake = content.locations["town"], content.locations["lake"]
    assert event_matches_location(content.events["drunk"], town)
    assert not event_matches_location(content.events["drunk"], lake)


def test_pick_event_filters_by_action_and_location(state, content):
    rng = random.Random(0)
    assert {pick_event(state, content, "explore", rng).id for _ in range(20)} == {"drunk"}
    assert pick_event(state, content, "socialize", rng).id == "join"
    assert pick_event(state, content, "train", rng) is None


def test_pick_event_skips_seen_once_events(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    assert pick_event(state, content, "explore", rng).id == "scroll"
    state.player.seen_events.add("scroll")
    assert pick_event(state, content, "explore", rng) is None


def test_the_common_pool_never_holds_once_or_qiyu_events(state, content):
    """探索三選一：事件那一支只從可重複的事件抽，一次性與奇遇只走奇遇那一步（探索三選一設計 4.3）。"""
    state.player.location = "lake"  # 湖邊的探索事件只有殘卷（一次性＋奇遇）
    rng = random.Random(0)
    assert pick_event(state, content, "explore", rng, pool="common") is None
    assert pick_event(state, content, "explore", rng, pool="rare").id == "scroll"
    assert pick_event(state, content, "explore", rng).id == "scroll"  # 不指定池子＝照舊（遊歷、交友用）
    content.events["scroll"].once = False  # 只是奇遇、不是一次性：一樣不進可重複的池子
    assert pick_event(state, content, "explore", rng, pool="common") is None
    content.events["scroll"].once, content.events["scroll"].qiyu = True, False  # 只是一次性
    assert pick_event(state, content, "explore", rng, pool="common") is None
    state.player.location = "town"
    assert {pick_event(state, content, "explore", rng, pool="common").id for _ in range(20)} == {"drunk"}
    assert pick_event(state, content, "explore", rng, pool="rare") is None


def test_a_seen_qiyu_stays_in_the_rare_pool_but_a_seen_once_event_does_not(state, content):
    """企劃者 2026-10-03 改：奇遇看過之後還能再遇到；標了 once 的照舊只有一次。"""
    state.player.location = "lake"
    rng = random.Random(0)
    content.events["scroll"].once = False
    state.player.seen_events.add("scroll")
    assert pick_event(state, content, "explore", rng, pool="rare").id == "scroll"
    content.events["scroll"].once = True
    assert pick_event(state, content, "explore", rng, pool="rare") is None


def test_pick_event_respects_condition(state, content):
    state.player.sect = "cloud"
    assert pick_event(state, content, "socialize", random.Random(0)) is None


def test_chain_only_events_never_picked(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    picks = {pick_event(state, content, "train", rng).id for _ in range(20)}
    assert picks == {"chain_a"}


def test_visible_choices_hide_conditional(state, content):
    ev = content.events["drunk"]
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1]
    state.player.stats["evil"] = 5
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1, 2]


def test_has_events_here(content):
    assert has_events_here(content, content.locations["town"], "socialize")
    assert not has_events_here(content, content.locations["cave"], "socialize")


def test_choice_label_shows_the_stat_and_the_odds(state, content, world):
    """企劃者 2026-10-05：玩家要知道為什麼有時拉得開、有時拉不開，所以寫出看哪一項屬性與成算。"""
    drunk = content.events["drunk"]
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（臂力・成算五成）"  # 空隊伍時是本人：不寫誰
    state.player.team.append("mate")  # 韓鐵臂力 6，比本人高
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（韓鐵出手・臂力・成算六成）"
    assert choice_label(drunk.choices[1], state, content, world) == "摸走鐵牌"
    insight = content.events["insight"]
    assert choice_label(insight.choices[0], state, content, world) == "運氣衝關（本人・根骨・成算五成）"  # 本人檢定


VOICE = CheckVoice(bands=[
    CheckVoiceBand(min_gap=2, lines={"str": "這點力氣，{who}使得出來。", "default": "難不倒{who}。"}),
    CheckVoiceBand(min_gap=0, lines={"default": "{who}有幾分把握。"}),
    CheckVoiceBand(min_gap=-99, lines={"str": "以{who}現在的臂力，恐怕力有未逮。", "default": "恐怕不成。"}),
])


def test_choice_hint_picks_the_band_by_stat_minus_difficulty(state, content, world):
    drunk = content.events["drunk"]  # 臂力檢定，難度 5
    assert choice_hint(drunk.choices[0], state, content, world) == ""  # 沒寫心聲就不顯示
    content.check_voice = VOICE
    assert choice_hint(drunk.choices[0], state, content, world) == "你有幾分把握。"  # 臂力 5：差 0
    assert choice_hint(drunk.choices[1], state, content, world) == ""  # 沒有檢定
    state.player.stats["str"] = 2
    assert choice_hint(drunk.choices[0], state, content, world) == "以你現在的臂力，恐怕力有未逮。"
    state.player.stats["str"] = 9
    assert choice_hint(drunk.choices[0], state, content, world) == "這點力氣，你使得出來。"
    state.player.stats["str"] = 5
    state.player.team.append("mate")  # 韓鐵出手：心聲講的是他
    assert choice_hint(drunk.choices[0], state, content, world) == "韓鐵有幾分把握。"


def test_choice_hint_mentions_practice_when_infamy_helps(state, content, world):
    content.check_voice = VOICE
    choice = content.events["drunk"].choices[0].model_copy(deep=True)  # 臂力檢定，難度 5
    choice.check.practice = "evil"
    assert choice_hint(choice, state, content, world) == "你有幾分把握。"  # 還沒有惡名：照舊
    state.player.stats["evil"] = 20  # 熟練 +2：差 2，換成高一檔的心聲，前面補一句熟練
    assert choice_hint(choice, state, content, world) == "這種事你幹得多了。這點力氣，你使得出來。"


def _add(content, event_id, locations=(), **extra):
    content.events[event_id] = Event(
        id=event_id, title=event_id, text="……", locations=list(locations), choices=[Choice(text="走")], **extra,
    )


def test_pick_event_goes_through_the_whole_pool_before_repeating(state, content):
    """防重複（交友與人物別傳設計稿第八節）：同一個池子沒看過的優先，整池輪完才重來。"""
    _add(content, "brawl", ["town"])
    _add(content, "rain", ["town"])
    rng = random.Random(0)
    first = [pick_event(state, content, "explore", rng).id for _ in range(3)]
    assert sorted(first) == ["brawl", "drunk", "rain"]
    assert state.player.event_rounds == {"town:explore": first}
    fourth = pick_event(state, content, "explore", rng).id
    assert fourth != first[-1]  # 換輪時不會連著兩次一樣
    assert state.player.event_rounds == {"town:explore": [fourth]}  # 池子清空、重開一輪


def test_rotation_keeps_weights_within_what_is_left(state, content):
    _add(content, "brawl", ["town"], weight=1000.0)
    for seed in range(20):
        state.player.event_rounds = {}
        rng = random.Random(seed)
        assert [pick_event(state, content, "explore", rng).id for _ in range(2)] == ["brawl", "drunk"]


def test_generic_events_share_one_pool_per_action(state, content):
    """不掛地點的通用事件：每種行動一個共用的池子，在哪裡看過都算。"""
    _add(content, "rumor", [])
    assert rotation_pool(content.events["rumor"], "town", "explore") == "*:explore"
    assert rotation_pool(content.events["drunk"], "town", "explore") == "town:explore"
    assert rotation_pool(content.events["scroll"], "lake", "explore") is None  # 一次性、奇遇不輪替
    rng = random.Random(1)
    assert sorted(pick_event(state, content, "explore", rng).id for _ in range(2)) == ["drunk", "rumor"]
    assert state.player.event_rounds == {"town:explore": ["drunk"], "*:explore": ["rumor"]}
    state.player.location = "lake"  # 湖畔沒有自己的可重複探索事件，通用池這一輪已經看過了：重開一輪
    assert pick_event(state, content, "explore", rng, "common").id == "rumor"
    assert state.player.event_rounds["*:explore"] == ["rumor"]


def test_each_location_has_its_own_pool(state, content):
    _add(content, "ferry", ["town", "lake"])
    rng = random.Random(2)
    while "ferry" not in state.player.event_rounds.get("town:explore", []):
        pick_event(state, content, "explore", rng)
    state.player.location = "lake"
    assert pick_event(state, content, "explore", rng, "common").id == "ferry"  # 在城裡看過，湖畔這一池還沒有


def test_rare_events_are_not_recorded_in_rounds(state, content):
    state.player.location = "lake"
    assert pick_event(state, content, "explore", random.Random(0), "rare").id in {"scroll", "hermit"}
    assert state.player.event_rounds == {}


def test_an_old_save_without_rounds_still_loads_and_rotates(state, content):
    """舊格式存檔（還沒有 event_rounds 這一欄）載入：當作每個池子都還沒看過。"""
    data = json.loads(state.model_dump_json())
    del data["player"]["event_rounds"]
    old = GameState.model_validate_json(json.dumps(data))
    assert old.player.event_rounds == {}
    assert pick_event(old, content, "explore", random.Random(0)).id == "drunk"
    assert old.player.event_rounds == {"town:explore": ["drunk"]}
    again = GameState.model_validate_json(old.model_dump_json())  # 新欄位存得下、讀得回
    assert again.player.event_rounds == {"town:explore": ["drunk"]}
