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


def test_one_track_file_runs_only_its_tracks(gate):
    """第 109 批：只改一軌的 scripts/sb/tracks/<軌>.py 只跑那一軌＋import 它的軌檔登記的軌（facade 被 drape import）；sb 其他檔照舊全軌（上面 harness 那一參數）。"""
    d = gate.decide(["scripts/sb/tracks/wicket.py"], _diff("scripts/sb/tracks/wicket.py", "+        self.step()"), ROOT)
    assert (d["mode"], d["track_files_tracks"], d["profiles"], d["crossover"], d["full_reasons"]) == ("tracks", ["wicket"], ["season21", "week7", "test"], True, [])
    assert gate.decide(["scripts/sb/tracks/facade.py"], "", ROOT)["track_files_tracks"] == ["drape", "facade"]
    mixed = gate.decide(["scripts/sb/tracks/wicket.py", "tianxia/features/seal/acts.py"], "", ROOT)
    assert (mixed["mode"], mixed["packages"], mixed["track_files_tracks"], mixed["profiles"]) == ("packages", ["seal"], ["wicket"], ["season21", "week7", "test"])
    assert gate.decide(["scripts/sb/tracks/__init__.py"], "", ROOT)["mode"] == "full"
    assert gate.decide(["scripts/sb/tracks/gone_away.py"], "", ROOT)["mode"] == "full", "head 上沒有的軌檔（刪掉的）量不出，退回全軌"


@pytest.mark.parametrize("path", ["tianxia/core/services_list.md", ".gitattributes"])
def test_core_notes_and_gitattributes_compare_nothing(gate, path):
    d = gate.decide([path], "", ROOT)
    assert (d["mode"], d["full_reasons"], d["web"]) == ("none", [], False)
    assert gate.decide(["tianxia/core/tuning/notes.md"], "", ROOT)["mode"] == "full", "只有 tianxia/core/ 直下的 .md 不比"


def test_core_fallback_does_not_widen_web_rounds(gate):
    """第 109 批第 11 項：核心退回全軌只管比對的軌，網頁回合照改到的 web/ 檔挑（M 波 web/identity.js＋identity_base 跑了 70 分全回合）。"""
    d = gate.decide(["web/identity.js", "tianxia/core/identity_base.py"], "", ROOT)
    assert (d["mode"], d["web"], d["web_all_rounds"], d["web_files"]) == ("full", True, False, ["web/identity.js"])
    page = gate.decide(["web/identity.js", "server.py"], _diff("server.py", "+    return HTMLResponse(page)"), ROOT)
    assert page["mode"] == "full" and page["web_all_rounds"], "server.py 回頁面的行照舊全回合"
    shell = gate.decide(["web/style.css"], "", ROOT)  # web/ 底下的殼檔照舊原樣交 --changed-files，全不全走由第 110 批的 gate.py 定
    assert (shell["web_all_rounds"], shell["web_files"]) == (False, ["web/style.css"])


def test_new_reaches_compare_either_way(gate):
    """PM 11/08 的 --new：--changed 挑軌與全軌都要傳給 compare。"""
    changed = {"tracks": ["facade", "seal"], "profiles": ["season21"], "crossover": False}
    full = {"tracks": None, "profiles": ["season21", "week7", "base"], "crossover": True}
    for d in (changed, full):
        extra = gate.compare_extra(d, "", "identity,support")
        assert extra[-2:] == ["--new", "identity,support"]
        assert "--new" not in gate.compare_extra(d, "", "")
    assert gate.compare_extra(changed, "2", "x")[:4] == ["--tracks", "facade,seal", "--jobs", "2"]
