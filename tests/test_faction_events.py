"""事件的選項跟著陣營分邊（企劃者 2026-10-08：「玩家都加入黃巾軍了，探索還一堆打黃巾跟增加官軍聲勢的任務」）。

有立場的選項寫 Condition.factions_none（黃巾的人看不到「打黃巾、替官軍長聲勢」那一顆），黃巾那一邊另補一顆
寫 factions: ["huang"] 的選項；散人兩邊都看得到。不掛在第一季開關後面，現在跑的這一季就生效。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tianxia import rules
from tianxia.content import load_content
from tianxia.models import FRONT_KEY, Condition
from tianxia.state import GameState, PlayerState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _state(faction):
    player = PlayerState(name="甲", location="yingchuan", stats={}, stamina=100)
    player.faction = faction
    return GameState(player=player)


def test_factions_none_hides_only_that_faction():
    cond = Condition(factions_none=["huang"])
    assert not rules.check_condition(cond, _state("huang"))
    assert rules.check_condition(cond, _state("guan"))
    assert rules.check_condition(cond, _state(None))  # 散人一律看得到


def _shown_to(cond: Condition, faction: str | None) -> bool:
    if cond.factions and faction not in cond.factions:
        return False
    return faction is None or faction not in cond.factions_none


def test_huang_never_offered_a_choice_that_pushes_against_huang(content):
    """黃巾的人碰得到的事件裡，沒有一顆選項（成功那一邊）會把戰線往官軍推。晉升奇遇只發給自己陣營的人，不算。"""
    bad = []
    for event in content.events.values():
        if event.id.startswith("promo_") or not _shown_to(event.condition, "huang"):
            continue
        for choice in event.choices:
            if not _shown_to(choice.condition, "huang"):
                continue
            pushes = {k: v for k, v in choice.effect.trend.items() if k == FRONT_KEY or k in ("huangjin", "yingru", "nanyang", "jizhou")}
            if any(v < 0 for v in pushes.values()):
                bad.append(f"{event.id}：{choice.text}")
        if event.free_text is not None and _shown_to(event.condition, "huang"):
            if any(v < 0 for k, v in event.free_text.effect.trend.items() if k != "yuxi"):
                bad.append(f"{event.id}：隨口應對")
    assert not bad, "\n".join(bad)


def test_huang_gets_its_own_side_in_events_that_used_to_fight_it(content):
    """補給黃巾的選項真的往黃巾那邊推，而且只給黃巾的人。"""
    added = [
        (event.id, choice) for event in content.events.values() for choice in event.choices
        if choice.condition.factions == ["huang"]
    ]
    assert len(added) >= 25
    for event_id, choice in added:
        assert all(v > 0 for v in choice.effect.trend.values()), event_id
