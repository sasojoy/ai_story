import json
import random

from tianxia.events import (
    choice_label, event_matches_location, has_events_here, note_round, pick_event, rotation_pool, visible_choices,
)
from tianxia.models import Choice, Event
from tianxia.rules import check_chance, check_gap
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


def test_check_label_is_one_bracketed_line_with_your_stat_and_a_voice_line(state, content, world):
    """企劃者 2026-10-05 定案：「{選項}（{屬性名} {數值}：{心裡話}）」，一行、括號裡，句子出自 content/check_voice.json
    （依屬性減難度分四檔，{who} 換成「你」）。不寫成算、百分比，也不寫誰出手。"""
    drunk = content.events["drunk"]  # 臂力檢定，難度 5
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（臂力 5：你掂了掂分量：使上全力，應該辦得到。）"
    assert choice_label(drunk.choices[1], state, content, world) == "摸走鐵牌"  # 沒有檢定：照原文
    state.player.stats["str"] = 2  # 差 −3：最低一檔
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（臂力 2：以你現在的臂力，恐怕力有未逮。）"
    state.player.stats["str"] = 4  # 差 −1：心裡沒底那一檔
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（臂力 4：你心裡沒底：這得拚上吃奶的力氣。）"
    state.player.stats["str"] = 9  # 差 +4：最高一檔
    assert choice_label(drunk.choices[0], state, content, world) == "逼問（臂力 9：這點力氣，你使得出來。）"
    insight = content.events["insight"]  # 根骨檢定
    assert choice_label(insight.choices[0], state, content, world) == "運氣衝關（根骨 5：咬咬牙，你應該撐得住。）"


def test_check_label_never_names_a_companion_or_shows_the_odds(state, content, world):
    """「探索應該沒有本人跟夥伴之分了」：隊伍裡有臂力更高的韓鐵，標籤照舊是本人的 5，不寫「本人」也不寫他的名字。"""
    drunk = content.events["drunk"]
    alone = choice_label(drunk.choices[0], state, content, world)
    state.player.team.append("mate")
    label = choice_label(drunk.choices[0], state, content, world)
    assert label == alone
    for word in ("本人", "韓鐵", "出手", "成算", "%", "％"):
        assert word not in label


def test_check_label_shows_the_stat_the_roll_reads_points_not_level(state, content, world):
    """計畫二 Task 1 起本人不再每級自動長屬性：等級高了括號裡的數字不變，配了點才變。"""
    state.player.member.level = 3
    assert choice_label(content.events["drunk"].choices[0], state, content, world).startswith("逼問（臂力 5：")
    state.player.stats["str"] = 6
    assert choice_label(content.events["drunk"].choices[0], state, content, world).startswith("逼問（臂力 6：")


def test_practice_folds_into_the_bracket_with_the_bonus_it_adds(state, content, world):
    """惡名的熟練加成（joy #15）：數值寫成「臂力 5＋2」，熟練的那句併進同一個括號，檔位照加了之後的差值挑。"""
    choice = content.events["drunk"].choices[0].model_copy(deep=True)  # 臂力檢定，難度 5
    choice.check.practice = "evil"
    assert choice_label(choice, state, content, world) == "逼問（臂力 5：你掂了掂分量：使上全力，應該辦得到。）"  # 還沒有惡名
    state.player.stats["evil"] = 20  # 熟練 +2：差 2，換成高一檔的心聲
    assert choice_label(choice, state, content, world) == "逼問（臂力 5＋2：這種事你幹得多了，這點力氣，你使得出來。）"


def test_the_label_band_is_the_band_of_the_gap_the_roll_uses(state, content, world):
    """標籤挑的那一檔，跟擲骰算成功率用的是同一個差值（rules.check_gap）：每一種屬性值、熟練都對得上。"""
    choice = content.events["drunk"].choices[0].model_copy(deep=True)
    choice.check.practice = "evil"
    bands = content.check_voice.bands
    state.player.member.level = 2  # 帶小數：x.3
    for stat_value in range(0, 12):
        for evil in (0, 10, 30):
            state.player.stats["str"], state.player.stats["evil"] = stat_value, evil
            gap = check_gap(choice.check, state, content, world)
            band = next(b for b in bands if gap >= b.min_gap)
            line = band.lines.get("str", band.lines["default"]).replace("{who}", "你")
            assert choice_label(choice, state, content, world).endswith(f"{line}）"), (stat_value, evil)
            assert check_chance(choice.check, state, content, world) == min(0.95, max(0.05, 0.5 + gap * 0.1))


def _add(content, event_id, locations=(), **extra):
    content.events[event_id] = Event(
        id=event_id, title=event_id, text="……", locations=list(locations), choices=[Choice(text="走")], **extra,
    )


def shown(state, content, action, rng, pool=None):
    """抽一則、當作端給玩家了：Game._present 才把它記進輪替（events.note_round），pick_event 本身不改狀態
    （見 tests/test_event_rotation.py）。"""
    event = pick_event(state, content, action, rng, pool)
    if event is not None:
        note_round(state, content, event, action)
    return event


def test_pick_event_goes_through_the_whole_pool_before_repeating(state, content):
    """防重複（交友與人物別傳設計稿第八節）：同一個池子沒看過的優先，整池輪完才重來。"""
    _add(content, "brawl", ["town"])
    _add(content, "rain", ["town"])
    rng = random.Random(0)
    first = [shown(state, content, "explore", rng).id for _ in range(3)]
    assert sorted(first) == ["brawl", "drunk", "rain"]
    assert state.player.event_rounds == {"town:explore": first}
    fourth = shown(state, content, "explore", rng).id
    assert fourth != first[-1]  # 換輪時不會連著兩次一樣
    assert state.player.event_rounds == {"town:explore": [fourth]}  # 池子清空、重開一輪


def test_rotation_keeps_weights_within_what_is_left(state, content):
    _add(content, "brawl", ["town"], weight=1000.0)
    for seed in range(20):
        state.player.event_rounds = {}
        rng = random.Random(seed)
        assert [shown(state, content, "explore", rng).id for _ in range(2)] == ["brawl", "drunk"]


def test_generic_events_share_one_pool_per_action(state, content):
    """不掛地點的通用事件：每種行動一個共用的池子，在哪裡看過都算。"""
    _add(content, "rumor", [])
    assert rotation_pool(content.events["rumor"], "town", "explore") == "*:explore"
    assert rotation_pool(content.events["drunk"], "town", "explore") == "town:explore"
    assert rotation_pool(content.events["scroll"], "lake", "explore") is None  # 一次性、奇遇不輪替
    rng = random.Random(1)
    assert sorted(shown(state, content, "explore", rng).id for _ in range(2)) == ["drunk", "rumor"]
    assert state.player.event_rounds == {"town:explore": ["drunk"], "*:explore": ["rumor"]}
    state.player.location = "lake"  # 湖畔沒有自己的可重複探索事件，通用池這一輪已經看過了：重開一輪
    assert shown(state, content, "explore", rng, "common").id == "rumor"
    assert state.player.event_rounds["*:explore"] == ["rumor"]


def test_each_location_has_its_own_pool(state, content):
    _add(content, "ferry", ["town", "lake"])
    rng = random.Random(2)
    while "ferry" not in state.player.event_rounds.get("town:explore", []):
        shown(state, content, "explore", rng)
    state.player.location = "lake"
    assert shown(state, content, "explore", rng, "common").id == "ferry"  # 在城裡看過，湖畔這一池還沒有


def test_rare_events_are_not_recorded_in_rounds(state, content):
    state.player.location = "lake"
    assert shown(state, content, "explore", random.Random(0), "rare").id in {"scroll", "hermit"}
    assert state.player.event_rounds == {}


def test_an_old_save_without_rounds_still_loads_and_rotates(state, content):
    """舊格式存檔（還沒有 event_rounds 這一欄）載入：當作每個池子都還沒看過。"""
    data = json.loads(state.model_dump_json())
    del data["player"]["event_rounds"]
    old = GameState.model_validate_json(json.dumps(data))
    assert old.player.event_rounds == {}
    assert shown(old, content, "explore", random.Random(0)).id == "drunk"
    assert old.player.event_rounds == {"town:explore": ["drunk"]}
    again = GameState.model_validate_json(old.model_dump_json())  # 新欄位存得下、讀得回
    assert again.player.event_rounds == {"town:explore": ["drunk"]}
