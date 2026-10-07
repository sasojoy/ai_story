"""scripts/test_for.py：改了哪些檔就挑哪幾個測試檔。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

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


def test_shared_test_setup_runs_everything():
    assert _names(["tests/conftest.py"]) is None and _names(["pyproject.toml"]) is None


def test_docs_pick_nothing_and_a_test_file_picks_itself():
    assert _names(["docs/superpowers/specs/x.md", "CLAUDE.md"]) == set()
    assert _names(["tests/test_fusion.py"]) == {"test_fusion.py"}
