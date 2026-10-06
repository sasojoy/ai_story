"""換上另一門功法會不會改變內外搭配（FB-088）：功法庫那一門跟身上同一種那門的比較（team.compare_with_worn，W6）與改練的回話
（team.switch_art）都要講。搭配的數字一律來自 team.pairing（設定的 pairing_bonus、pairing_penalty），這裡不寫死 20%：
測試把設定改掉，句子跟著變。夾具的身上是粗淺吐納（內功・柔）與粗淺拳腳（武學・實）——實跟柔不相剋、不同屬，搭配是 1。"""
from __future__ import annotations

import pytest

from tianxia import team
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name, power_at

LOW_ONLY = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}


def _art(world, name, attribute, kind="武學"):
    art = generate_from_name(name, kind, name, weights=LOW_ONLY, attribute=attribute).model_copy(update={"origin": "fused"})
    assert world.claim_skill_name(art)
    return art


@pytest.fixture
def worn(state):
    """身上：粗淺吐納（內功・柔）與粗淺拳腳（武學・實）。"""
    state.player.member.neigong_id, state.player.member.wugong_id = "basic_breath", "basic_fist"
    return state


def _clause(content, state, world, art) -> str:
    line = team.compare_with_worn(state, content, world, art)
    return line.partition("；")[2]


# ── 比較那一句 ────────────────────────────────────────────


def test_a_same_attribute_switch_says_the_pair_turns_into_a_bonus(worn, content, world):
    art = _art(world, "柔拳", "柔")  # 跟身上的內功（柔）同屬
    worn.player.arts = [art.id]
    line = team.compare_with_worn(worn, content, world, art)
    assert line.endswith("；換上後跟內功同屬，整體 +20%") and line.count("；") == 1
    assert line.startswith("比身上的【粗淺拳腳】：威力 ")  # 原本的比較照舊在前面


def test_a_counter_switch_says_the_pair_turns_into_a_penalty(worn, content, world):
    art = _art(world, "剛拳", "剛")  # 剛剋柔：跟身上的內功相剋
    worn.player.arts = [art.id]
    assert team.compare_with_worn(worn, content, world, art).endswith("；換上後跟內功相剋，整體 −20%")


def test_a_neutral_switch_says_nothing_extra(worn, content, world):
    art = _art(world, "快拳", "快")  # 快跟柔：不同屬也不相剋
    worn.player.arts = [art.id]
    line = team.compare_with_worn(worn, content, world, art)
    assert "換上後" not in line and "整體" not in line and "；" not in line


def test_the_pair_clause_follows_the_worn_art_of_the_other_kind(worn, content, world):
    """換的是內功時，看的是身上的武學：跟武學同屬寫「跟武學」。"""
    inner = _art(world, "實功", "實", kind="內功")  # 跟身上的武學（實）同屬
    worn.player.arts = [inner.id]
    assert team.compare_with_worn(worn, content, world, inner).endswith("；換上後跟武學同屬，整體 +20%")
    clash = _art(world, "虛功", "虛", kind="內功")  # 虛剋實
    worn.player.arts.append(clash.id)
    assert team.compare_with_worn(worn, content, world, clash).endswith("；換上後跟武學相剋，整體 −20%")


def test_going_from_a_penalty_or_a_bonus_back_to_nothing_says_the_pair_goes_away(worn, content, world):
    worn.player.member.wugong_id = _art(world, "剛拳", "剛").id  # 現在跟柔內功相剋（−20%）
    neutral = _art(world, "快拳", "快")
    worn.player.arts = [neutral.id]
    assert team.compare_with_worn(worn, content, world, neutral).endswith("；換上後跟內功不再相剋，整體不再 −20%")
    worn.player.member.wugong_id = _art(world, "柔拳", "柔").id  # 現在跟柔內功同屬（+20%）
    assert team.compare_with_worn(worn, content, world, neutral).endswith("；換上後跟內功不再同屬，整體不再 +20%")


def test_going_from_a_penalty_to_a_bonus_reports_the_new_state(worn, content, world):
    """QA 說的反過來：−20% 換成 +20%——寫換上之後的樣子（跟門下卡的「內外搭配」同一個數）。"""
    worn.player.member.wugong_id = _art(world, "剛拳", "剛").id
    same = _art(world, "柔拳", "柔")
    worn.player.arts = [same.id]
    assert team.compare_with_worn(worn, content, world, same).endswith("；換上後跟內功同屬，整體 +20%")


def test_no_pair_clause_when_the_other_slot_is_empty_or_the_pair_does_not_change(worn, content, world):
    art = _art(world, "柔拳", "柔")
    worn.player.arts = [art.id]
    worn.player.member.neigong_id = None  # 內功欄空著：武學之間沒有搭配可言
    assert "換上後" not in team.compare_with_worn(worn, content, world, art)
    worn.player.member.neigong_id = "basic_breath"
    same_again = _art(world, "柔拳二式", "柔")
    worn.player.member.wugong_id = _art(world, "柔拳三式", "柔").id  # 已經同屬了：換成另一門同屬的，搭配不變
    worn.player.arts = [same_again.id]
    assert "換上後" not in team.compare_with_worn(worn, content, world, same_again)


def test_the_percentages_come_from_the_engines_pairing(worn, content, world):
    content.config.pairing_bonus, content.config.pairing_penalty = 0.35, 0.1
    same, clash = _art(world, "柔拳", "柔"), _art(world, "剛拳", "剛")
    worn.player.arts = [same.id, clash.id]
    assert team.compare_with_worn(worn, content, world, same).endswith("；換上後跟內功同屬，整體 +35%")
    assert team.compare_with_worn(worn, content, world, clash).endswith("；換上後跟內功相剋，整體 −10%")


def test_the_pair_clause_is_the_same_pairing_the_card_shows_after_switching(worn, content, world):
    from tianxia import skillview

    art = _art(world, "剛拳", "剛")
    worn.player.arts = [art.id]
    assert team.compare_with_worn(worn, content, world, art).endswith("整體 −20%")
    team.switch_art(worn, content, world, art.id)
    assert "內外搭配 -20%" in skillview.boost_line(worn, content, world)  # 門下卡上換上後真的是這個數（卡上的減號是半形，句子照 W6 用 −）


# ── 改練的回話 ────────────────────────────────────────────


def test_the_switch_reply_adds_one_sentence_when_the_pair_changes(worn, content, world):
    same = _art(world, "柔拳", "柔")
    worn.player.arts = [same.id]
    msgs = team.switch_art(worn, content, world, same.id)
    assert msgs[-1] == "你的內功與武學現在同屬，整體威力 +20%。" and msgs[-2].startswith("你改練【柔拳】")
    assert sum("整體威力" in m for m in msgs) == 1
    clash = _art(world, "剛拳", "剛")
    worn.player.arts.append(clash.id)
    assert team.switch_art(worn, content, world, clash.id)[-1] == "你的內功與武學現在相剋，整體威力 −20%。"


def test_the_switch_reply_stays_as_before_for_a_neutral_switch(worn, content, world):
    art = _art(world, "快拳", "快")
    worn.player.arts = [art.id]
    msgs = team.switch_art(worn, content, world, art.id)
    assert not any("整體威力" in m for m in msgs) and msgs[-1].startswith("你改練【快拳】")


def test_the_switch_reply_when_the_pair_goes_away_or_flips(worn, content, world):
    worn.player.member.wugong_id = _art(world, "剛拳", "剛").id  # 相剋 −20%
    neutral, same = _art(world, "快拳", "快"), _art(world, "柔拳", "柔")
    worn.player.arts = [neutral.id, same.id]
    assert team.switch_art(worn, content, world, same.id)[-1] == "你的內功與武學現在同屬，整體威力 +20%。"  # −20% → +20%
    assert team.switch_art(worn, content, world, neutral.id)[-1] == "你的內功與武學不再同屬，整體威力不再 +20%。"  # +20% → 沒有


def test_the_switch_reply_percentages_come_from_the_engine(worn, content, world):
    content.config.pairing_bonus = 0.35
    same = _art(world, "柔拳", "柔")
    worn.player.arts = [same.id]
    assert team.switch_art(worn, content, world, same.id)[-1] == "你的內功與武學現在同屬，整體威力 +35%。"


def test_switching_into_an_empty_slot_or_with_nothing_to_pair_adds_nothing(worn, content, world):
    worn.player.member.neigong_id = None
    art = _art(world, "柔拳", "柔")
    worn.player.arts = [art.id]
    assert not any("整體威力" in m for m in team.switch_art(worn, content, world, art.id))  # 內功欄空著：沒有搭配


def test_the_engines_switch_keeps_the_journal_tag_on_the_switch_line_and_shows_the_sentence(content):
    import random

    game = Game.new(content, "沈浪", rng=random.Random(0))
    art = _art(game.world, "柔拳", "柔")
    game.state.player.member.neigong_id = "basic_breath"
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.arts = [art.id]
    msgs = game.switch_art(art.id)
    assert msgs[-1] == "你的內功與武學現在同屬，整體威力 +20%。"
    entry = game.state.journal[0]
    assert entry.tag.startswith("你改練【柔拳】") and "整體威力" not in entry.tag  # 江湖紀錄的標記還是那一句改練
    assert power_at(art, 1) > 0
