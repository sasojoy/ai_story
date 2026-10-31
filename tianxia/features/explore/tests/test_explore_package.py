"""探索包（走一趟、探索一顆）登記之後的煙霧與接縫：包的內容驗證（原本的 content.check_explore_one、check_outing_lines）照樣擋得下
壞的內容、核心照 FEATURES 叫得到它；核心寫的那一份「旅人」跟包裡的一樣（核心不 import 包，抄了一份字）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import content as content_mod
from tianxia.core import features as features_core
from tianxia.features.explore import explore_rules


def _problems(c) -> list[str]:
    found: list[str] = []
    features_core.check_content(c, lambda ok, message: None if ok else found.append(message))
    return found


@pytest.mark.smoke
def test_the_package_checks_the_explore_tables_and_the_outing_lines():
    c = real_content("season21")
    assert _problems(c) == []
    c.locations["yingshui"].tags = ["酒肆"]  # 店面標籤不歸表
    c.outing_lines = {**c.outing_lines, "nope": {"x": ["y"]}}
    found = _problems(c)
    assert any("yingshui" in f for f in found) and any("不認得的組 nope" in f for f in found)


def test_the_core_and_the_package_spell_the_traveler_tag_the_same():
    assert content_mod.TRAVELER_TAG == explore_rules.TRAVELER
