"""scripts/test_for.py：改了哪些檔就挑哪幾個測試檔。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("test_for", ROOT / "scripts" / "test_for.py")
test_for = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(test_for)


def _names(files):
    picked = test_for.pick(files)
    return None if picked is None else {p.name for p in picked}


def test_a_module_picks_the_tests_that_import_it():
    names = _names(["tianxia/glyph.py"])
    assert "test_sensing.py" in names and "test_real_content.py" not in names


def test_content_picks_the_real_content_season():
    assert {"test_content.py", "test_real_content.py"} <= _names(["content/skills.json"])


@pytest.mark.slow  # 挑三次（每次讀過所有測試檔），超過一秒
def test_the_promotion_and_rank_action_content_picks_the_tests_that_pin_it():
    """第一季正式版丙一、丙二、戊一的測試檔用真實內容釘住晉升奇遇與第 3、4 階行動：改那幾個內容檔時要挑到它們（整合審查 M2）。"""
    promotions = {"test_promotions_high.py", "test_promotions_huang.py"}
    assert promotions <= _names(["content/promotions.json"])
    assert promotions <= _names(["content/events/promotion.json"])
    assert "test_rank_actions.py" in _names(["content/orders.json"])


def test_shared_test_setup_runs_everything():
    assert _names(["tests/conftest.py"]) is None and _names(["pyproject.toml"]) is None


def test_docs_pick_nothing_and_a_test_file_picks_itself():
    assert _names(["docs/superpowers/specs/x.md", "CLAUDE.md"]) == set()
    assert _names(["tests/test_fusion.py"]) == {"test_fusion.py"}
