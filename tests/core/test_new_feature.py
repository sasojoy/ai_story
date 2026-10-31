"""scripts/new_feature.py（開發規範手冊 3.4 第 2 條）：在一份暫存的小 repo 裡生骨架，看生了什麼、登記了沒、撞名擋不擋。"""
from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import new_feature  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tianxia" / "core").mkdir(parents=True)
    (tmp_path / "tianxia" / "features").mkdir()
    (tmp_path / "docs" / "guide").mkdir(parents=True)
    shutil.copy(ROOT / "tianxia" / "core" / "registry.py", tmp_path / "tianxia" / "core" / "registry.py")
    (tmp_path / "tianxia" / "mall.py").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "guide" / "大勢人物與賽季.md").write_bytes("# 大勢人物與賽季\r\n\r\n- 舊的一條\r\n".encode("utf-8"))
    return tmp_path


def test_it_makes_the_package_registers_it_and_adds_the_guide_heading(repo):
    made = new_feature.make(repo, "tavern2", "酒肆", "大勢人物與賽季")
    pkg = repo / "tianxia" / "features" / "tavern2"
    for rel in ("__init__.py", "README.md", "tests/test_tavern2_smoke.py", "tests/tavern2_stage.py"):
        assert (pkg / rel).exists(), rel
    for path in (pkg / "__init__.py", pkg / "tests" / "test_tavern2_smoke.py", pkg / "tests" / "tavern2_stage.py"):
        ast.parse(path.read_text(encoding="utf-8"))  # 生出來的程式讀得懂
    init = (pkg / "__init__.py").read_text(encoding="utf-8")
    assert 'name = "tavern2"' in init and 'prefix = "tavern2"' in init and "FEATURE = Tavern2Feature()" in init
    assert b"\r\n" in (pkg / "__init__.py").read_bytes()  # 工作樹是 CRLF
    smoke = (pkg / "tests" / "test_tavern2_smoke.py").read_text(encoding="utf-8")  # 每一包至少一條煙霧（手冊 4.3）
    assert "@pytest.mark.smoke\ndef test_tavern2_" in smoke.replace("\r\n", "\n")
    registry = (repo / "tianxia" / "core" / "registry.py").read_text(encoding="utf-8")
    assert "from ..features import tavern2  # 酒肆" in registry and "    tavern2.FEATURE," in registry
    assert registry.index("tavern2.FEATURE,") < registry.index(new_feature.LIST_MARK.strip())
    guide = (repo / "docs" / "guide" / "大勢人物與賽季.md").read_text(encoding="utf-8")
    assert guide.startswith("# 大勢人物與賽季") and "## 酒肆（功能包 `tianxia/features/tavern2/`）" in guide
    assert len(made) == 6


def test_a_second_package_lines_up_after_the_first(repo):
    new_feature.make(repo, "first", "甲", "大勢人物與賽季")
    new_feature.make(repo, "second", "乙", "大勢人物與賽季")
    registry = (repo / "tianxia" / "core" / "registry.py").read_text(encoding="utf-8")
    assert registry.index("first.FEATURE,") < registry.index("second.FEATURE,")
    assert registry.index("import first") < registry.index("import second")


@pytest.mark.parametrize("name, guide, why", [
    ("Tavern", "大勢人物與賽季", "小寫"),
    ("9lives", "大勢人物與賽季", "小寫"),
    ("mall", "大勢人物與賽季", "模組"),
    ("tavern", "沒有這一塊", "docs/guide"),
])
def test_it_refuses_bad_names_and_missing_guides(repo, name, guide, why):
    with pytest.raises(SystemExit) as caught:
        new_feature.make(repo, name, "名", guide)
    assert why in str(caught.value)
    assert not (repo / "tianxia" / "features" / name).exists()


def test_it_refuses_a_package_that_is_already_there(repo):
    new_feature.make(repo, "tavern2", "酒肆", "大勢人物與賽季")
    with pytest.raises(SystemExit):
        new_feature.make(repo, "tavern2", "酒肆", "大勢人物與賽季")
