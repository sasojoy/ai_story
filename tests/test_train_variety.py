"""遊歷打完接的戰後事件不能只有兩則（2026-10-05：通用遊歷池只有拆招頓悟、錦衣少年，防重複輪替救不了，一季各出現十五次以上）。

補寫的事件放在 content/events/train_aftermath.json。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tianxia.content import load_content
from tianxia.models import Condition

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


def _general_train_events(content):
    """不掛地點、沒有條件、不是一次性的遊歷事件：在任何地方遊歷打完都可能接到。"""
    return [
        e for e in content.events.values()
        if "train" in e.actions and not e.locations and not e.tags
        and e.condition == Condition() and not e.once
    ]


def test_the_general_train_pool_has_at_least_eight_events(content):
    assert len(_general_train_events(content)) >= 8


def test_at_least_one_general_train_event_takes_a_free_text_answer(content):
    assert any(e.free_text for e in _general_train_events(content))


def test_added_train_checks_suit_a_new_character():
    """遊歷到處都可能接到，所以難度照最安全的地方算：新角色（屬性 5）至少五成。"""
    for e in json.loads((CONTENT_DIR / "events" / "train_aftermath.json").read_text(encoding="utf-8")):
        for c in e["choices"]:
            if "check" in c:
                assert 3 <= c["check"]["difficulty"] <= 5, e["id"]
