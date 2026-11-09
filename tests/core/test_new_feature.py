"""scripts/new_feature.py（開發規範手冊 3.4 第 2 條）：在一份暫存的小 repo 裡生骨架，看生了什麼、登記了沒、撞名擋不擋。"""
from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pydantic
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
    shutil.copy(ROOT / "tianxia" / "models.py", tmp_path / "tianxia" / "models.py")
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
    assert "web: tuple[str, ...] = ()" in init and "content: tuple[str, ...] = ()" in init  # 畫面、內容檔怎麼宣告（手冊第十五節 G8、G9）
    assert "tianxia/features/tavern2/content/" in init and "不要手改 index.html 的 script" in init
    # 第 106 批：範本照 test_shell_stays_thin 講：新欄位標 QUIET、路由第一行 gate 丟 404、enabled 讀 Config 預設關
    assert "json_schema_extra=QUIET" in init and "關著丟 404" in init and "Config.tavern2.enabled" in init and "enabled: bool = False" in init
    assert b"\r\n" in (pkg / "__init__.py").read_bytes()  # 工作樹是 CRLF
    smoke = (pkg / "tests" / "test_tavern2_smoke.py").read_text(encoding="utf-8")  # 每一包至少一條煙霧（手冊 4.3）
    assert "@pytest.mark.smoke\ndef test_tavern2_" in smoke.replace("\r\n", "\n")
    registry = (repo / "tianxia" / "core" / "registry.py").read_text(encoding="utf-8")
    assert "from ..features import tavern2  # 酒肆" in registry and "    tavern2.FEATURE," in registry
    assert registry.index("tavern2.FEATURE,") < registry.index(new_feature.LIST_MARK.strip())
    guide = (repo / "docs" / "guide" / "大勢人物與賽季.md").read_text(encoding="utf-8")
    assert guide.startswith("# 大勢人物與賽季") and "## 酒肆（功能包 `tianxia/features/tavern2/`）" in guide
    assert len(made) == 8


def test_the_stage_file_is_registered_after_the_last_stage_line(repo):
    """tests/core/test_test_for.py 的 STAGE_PACKAGES：沒登記的話每一個新包都讓 test_the_stage_packages_are_every_package_with_a_stage_file 紅。"""
    (repo / "tests" / "core").mkdir(parents=True)
    path = repo / "tests" / "core" / "test_test_for.py"
    path.write_bytes('STAGE_PACKAGES = ["a"]\r\nSTAGE_PACKAGES += ["b"]  # 乙\r\n\r\n\r\ndef test_x():\r\n    assert sorted(STAGE_PACKAGES)\r\n'.encode("utf-8"))
    made = new_feature.make(repo, "tavern2", "酒肆", "大勢人物與賽季")
    assert path in made and len(made) == 9
    lines = path.read_bytes().decode("utf-8").split("\r\n")  # 工作樹是 CRLF
    assert lines[1] == 'STAGE_PACKAGES += ["b"]  # 乙'
    assert lines[2].startswith('STAGE_PACKAGES += ["tavern2"]') and lines[3] == ""
    namespace: dict = {}
    exec("\n".join(lines[:3]), namespace)  # 接上去的那一行是讀得懂的程式
    assert namespace["STAGE_PACKAGES"] == ["a", "b", "tavern2"]


def test_a_second_package_lines_up_after_the_first(repo):
    new_feature.make(repo, "first", "甲", "大勢人物與賽季")
    new_feature.make(repo, "second", "乙", "大勢人物與賽季")
    registry = (repo / "tianxia" / "core" / "registry.py").read_text(encoding="utf-8")
    assert registry.index("first.FEATURE,") < registry.index("second.FEATURE,")
    assert registry.index("import first") < registry.index("import second")
    models = (repo / "tianxia" / "models.py").read_text(encoding="utf-8")
    assert models.index("tuning.first import") < models.index("tuning.second import") < models.index(new_feature.TUNING_IMPORT_MARK)
    assert models.index("    first: FirstTuning") < models.index("    second: SecondTuning") < models.index(new_feature.TUNING_FIELD_MARK)


def test_the_config_model_goes_in_a_tuning_file_and_models_only_gets_two_lines(repo):
    """新包的 Config 子模型（手冊第十五節「波次 B、C」第 15 條）：tianxia/core/tuning/<包>.py 不 import models、多寫一個鍵會擋；models.py 兩行都在標記前面；骨架的 enabled 讀它。"""
    before = (repo / "tianxia" / "models.py").read_text(encoding="utf-8")
    made = new_feature.make(repo, "tavern2", "酒肆", "大勢人物與賽季")
    path = repo / "tianxia" / "core" / "tuning" / "tavern2.py"
    assert path in made and b"\r\n" in path.read_bytes()
    source = path.read_text(encoding="utf-8")
    assert "models" not in {node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
    assert "class Tavern2Tuning(BaseModel):" in source and 'extra="forbid"' in source
    space: dict = {"__name__": "tavern2_tuning"}
    exec(source, space)
    assert space["Tavern2Tuning"]().enabled is False
    with pytest.raises(pydantic.ValidationError):
        space["Tavern2Tuning"](nosuch=1)
    models = (repo / "tianxia" / "models.py").read_text(encoding="utf-8")
    added = [line for line in models.split("\n") if line not in before.split("\n")]
    assert added == ["from .core.tuning.tavern2 import Tavern2Tuning  # 酒肆",
                     "    tavern2: Tavern2Tuning = Field(default_factory=Tavern2Tuning)  # 酒肆（tianxia/core/tuning/tavern2.py）"]
    ast.parse(models)
    assert models.index(added[0]) < models.index(new_feature.TUNING_IMPORT_MARK) and models.index(added[1]) < models.index(new_feature.TUNING_FIELD_MARK)
    assert "return ctx.content.config.tavern2.enabled" in (repo / "tianxia" / "features" / "tavern2" / "__init__.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("name, why", [
    ("taken", "tianxia/core/tuning/taken.py"),  # tuning 檔已經有了
    ("clash", "class ClashTuning"),  # models.py 已經有這個子模型
    ("time_scale", "Config 已經有 time_scale"),  # Config 已經有這一格（真的 models.py 上的）
])
def test_it_refuses_a_tuning_file_a_model_or_a_config_slot_that_is_already_there(repo, name, why):
    (repo / "tianxia" / "core" / "tuning").mkdir()
    (repo / "tianxia" / "core" / "tuning" / "taken.py").write_text("", encoding="utf-8")
    models = repo / "tianxia" / "models.py"
    models.write_bytes(models.read_bytes() + b"\r\n\r\nclass ClashTuning:\r\n    pass\r\n")
    with pytest.raises(SystemExit) as caught:
        new_feature.make(repo, name, "名", "大勢人物與賽季")
    assert why in str(caught.value)
    assert not (repo / "tianxia" / "features" / name).exists()  # 沒有生到一半


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
