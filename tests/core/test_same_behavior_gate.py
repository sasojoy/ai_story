"""wave_gate.decide：改到哪些、要跑什麼（測試流程優化第 107 批）。純函式，不碰 git、不開伺服器；head_root 用這一份程式。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("_wave_gate_under_test", ROOT / "docs" / "superpowers" / "pm-workflows" / "wave_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _diff(path: str, *lines: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n" + "".join(f"{x}\n" for x in lines)


def test_a_package_file_compares_only_that_package(gate):
    d = gate.decide(["tianxia/features/seal/acts.py"], _diff("tianxia/features/seal/acts.py", "-    x = 1", "+    x = 2"), ROOT)
    assert (d["mode"], d["packages"], d["profiles"], d["crossover"], d["web"]) == ("packages", ["seal"], ["season21", "test"], False, False)


@pytest.mark.parametrize("path, why", [
    ("tianxia/core/registry.py", "tianxia/core/registry.py"),
    ("tianxia/engine.py", "tianxia/engine.py（舊模組或殼）"),
    ("tianxia/timetable.py", "tianxia/timetable.py（共用層）"),
    ("server.py", "server.py"),
    ("content/config.json", "content/config.json"),
    ("scripts/sb/harness.py", "scripts/sb/harness.py"),
    ("tests/fixtures/content/config.json", "tests/fixtures/content/config.json"),
    ("requirements-dev.txt", "requirements-dev.txt"),
    ("run_bots.py", "run_bots.py（歸不到包）"),
])
def test_what_cannot_be_placed_falls_back_to_every_track(gate, path, why):
    d = gate.decide(["tianxia/features/seal/acts.py", path], "", ROOT)
    assert d["mode"] == "full" and d["packages"] is None and d["profiles"] == ["season21", "week7", "test"] and d["crossover"]
    assert d["full_reasons"] == [why], "退回全軌的理由要寫對那一條規則"


def test_season_words_add_week7(gate):
    d = gate.decide(["tianxia/features/seal/acts.py"], _diff("tianxia/features/seal/acts.py", "+    if rules.season_one:"), ROOT)
    assert d["profiles"] == ["season21", "week7", "test"] and d["mode"] == "packages"


def test_save_fields_turn_on_the_crossover(gate):
    d = gate.decide(["tianxia/features/seal/acts.py"], _diff("tianxia/features/seal/acts.py", "+    shards: int = Field(0, json_schema_extra=QUIET)"), ROOT)
    assert d["crossover"] and d["mode"] == "packages"


def test_web_files(gate):
    d = gate.decide(["web/seal.js"], "", ROOT)
    assert (d["mode"], d["packages"], d["web"], d["web_files"]) == ("packages", ["seal"], True, ["web/seal.js"])
    shell = gate.decide(["web/app.js"], "", ROOT)
    assert (shell["mode"], shell["packages"], shell["web"]) == ("packages", [], True), "殼的網頁檔：只跑 ALWAYS_TRACKS（facade、drape）＋網頁"
    page = gate.decide(["tianxia/features/seal/routes.py"], _diff("tianxia/features/seal/routes.py", "+    return HTMLResponse(html)"), ROOT)
    assert page["web"] and page["packages"] == ["seal"]
    tool = gate.decide(["scripts/webqa/gate.py"], "", ROOT)
    assert (tool["mode"], tool["web"]) == ("none", True)


@pytest.mark.parametrize("files", [
    ["docs/superpowers/plans/x.md"],
    ["docs/superpowers/architecture/三國篇架構.html"],
    ["tests/core/test_engine.py", "tianxia/features/seal/tests/test_seal.py"],
    ["CLAUDE.md", ".claude/skills/tianxia-flow/SKILL.md", "scripts/test_for.py"],
])
def test_docs_and_tests_compare_nothing(gate, files):
    d = gate.decide(files, "", ROOT)
    assert (d["mode"], d["packages"], d["profiles"], d["crossover"], d["web"]) == ("none", [], [], False, False)
