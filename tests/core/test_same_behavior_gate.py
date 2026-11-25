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


def test_tuning_file_counts_as_its_package(gate):  # 第 112 批：tuning/<包>.py 照包挑軌（intro 只有自己讀 Config.intro；jieyi 第二批起核心 combat 也讀、mail 新角色漸進的小事卡也讀，換成 intro）
    d = gate.decide(["tianxia/core/tuning/intro.py"], _diff("tianxia/core/tuning/intro.py", "-    enabled: bool = False", "+    enabled: bool = True"), ROOT)
    assert (d["mode"], d["packages"], d["profiles"], d["crossover"]) == ("packages", ["intro"], ["season21", "test"], False)
    assert any("tuning，照包 intro" in r for r in d["reasons"])
    field = gate.decide(["tianxia/core/tuning/intro.py"], _diff("tianxia/core/tuning/intro.py", "+    x: int = Field(0, json_schema_extra=QUIET)"), ROOT)
    assert field["mode"] == "packages" and field["crossover"], "Field( 那一行照舊開半舊半新"


def test_tuning_read_by_another_package_picks_both(gate):  # mail 的開關新角色漸進也讀：兩包一起挑
    d = gate.decide(["tianxia/core/tuning/mail.py"], _diff("tianxia/core/tuning/mail.py", "-    per_day: int = 10", "+    per_day: int = 11"), ROOT)
    assert d["mode"] == "packages" and d["packages"] == ["mail", "unfold"]


def test_tuning_read_by_core_still_falls_back(gate):  # Config.identity 核心 identity_base.py 也讀：照舊全軌
    d = gate.decide(["tianxia/core/tuning/identity.py"], "", ROOT)
    assert d["mode"] == "full" and len(d["full_reasons"]) == 1
    assert "identity_base.py" in d["full_reasons"][0] and "核心也讀 Config.identity" in d["full_reasons"][0]


def test_tuning_init_and_unknown_fall_back(gate):
    assert gate.decide(["tianxia/core/tuning/__init__.py"], "", ROOT)["full_reasons"] == ["tianxia/core/tuning/__init__.py"]
    assert gate.decide(["tianxia/core/tuning/nope.py"], "", ROOT)["full_reasons"] == ["tianxia/core/tuning/nope.py"], "包不存在退回全軌"


def test_tuning_readers_in_other_packages_join(gate, tmp_path):  # 別包讀 Config.<包> 就一起挑；核心或殼讀就退全軌
    (tmp_path / "tianxia" / "features" / "aa").mkdir(parents=True)
    (tmp_path / "tianxia" / "features" / "bb").mkdir(parents=True)
    (tmp_path / "tianxia" / "features" / "aa" / "x.py").write_text("v = ctx.content.config.aa.on\n", encoding="utf-8")
    (tmp_path / "tianxia" / "features" / "bb" / "y.py").write_text("v = content.config.aa.cap\nw = content.config.aab\n", encoding="utf-8")
    (tmp_path / "tianxia" / "features" / "bb" / "tests").mkdir()
    (tmp_path / "tianxia" / "features" / "bb" / "tests" / "t.py").write_text("v = content.config.aa\n", encoding="utf-8")
    assert gate._tuning_readers(tmp_path, "aa") == ({"bb"}, [])
    (tmp_path / "server.py").write_text("if CONTENT.config.aa.on: pass\n", encoding="utf-8")
    assert gate._tuning_readers(tmp_path, "aa") == ({"bb"}, ["server.py"])


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


def test_new_reaches_the_web_gate(gate):
    """N 波合併時補（第 110 批留下的）：wave_gate --web 把 --new <包> 轉給 scripts/webqa/gate.py --new；--also-existing 不轉（webqa 沒有）。"""
    changed = {"web_files": ["web/identity.js"], "web_all_rounds": False}
    assert gate.web_args(changed, True, "identity,support") == ["--changed-files", "web/identity.js", "--new", "identity,support"]
    assert "--new" not in gate.web_args(changed, True, "")
    full = {"web_files": [], "web_all_rounds": False}
    assert gate.web_args(full, False, "identity,support") == ["--new", "identity,support"]
    assert gate.web_args(full, False, "") == []
    assert gate.web_args({"web_files": ["web/app.js"], "web_all_rounds": True}, True, "") == [], "全回合不交 --changed-files"


def test_bot_covers_reach_compare_only_in_packages_mode(gate, tmp_path):
    """第 112 批：packages 模式把包交給 compare --bot-covers（座位照 covers 挑）；全軌、--tracks 蓋過、舊 head 的 compare 認不得都照舊不帶。"""
    script = ROOT / "scripts" / "same_behavior.py"
    packages = {"mode": "packages", "packages": ["seal"], "tracks": ["facade", "seal"], "profiles": ["season21"], "crossover": False}
    assert gate.bot_covers(script, packages, False) == ["seal"]
    assert gate.bot_covers(script, packages, True) is None, "--tracks 蓋過的照舊"
    assert gate.bot_covers(script, {**packages, "mode": "full", "packages": None}, False) is None
    old = tmp_path / "same_behavior.py"
    old.write_text("x.add_argument('--covers')\n", encoding="utf-8")
    assert gate.bot_covers(old, packages, False) is None, "舊 head 的 compare 沒有 --bot-covers"
    assert gate.compare_extra({**packages, "bot_covers": ["seal"]})[-2:] == ["--bot-covers", "seal"]
    assert gate.compare_extra({**packages, "bot_covers": []})[-2:] == ["--bot-covers", ","]
    assert "--bot-covers" not in gate.compare_extra(packages)


# ── 第 262 批：紅的只有把 js 算進輸出的軌、js 只有內容變 → base 換進 head 的 js 再比一次 ──

def _row(track: str, profile: str, hb: str, hh: str, crossover: str = "") -> str:
    tail = f"｜base 前半＋head 後半 {crossover} {'一樣' if crossover == hb else '不一樣'}" if crossover else "｜半舊半新 沒跑"
    return f"{track:6} {profile:9} 整段 base 120 行 4096 位元組 {hb}｜head {hh} {'一樣' if hb == hh else '不一樣'}{tail}"


A, B, C = "a" * 16, "b" * 16, "c" * 16
JS_RED = "\n".join(["跑完 30 秒", _row("facade", "season21", A, B), "  第 12 行起不一樣：…", _row("facade", "test", C, B),
                    _row("seal", "season21", A, A), "假人 ALWAYS season21  10 行 99 位元組 base " + A + "｜head " + A + " 一樣", "有不一樣的"])


def test_only_js_content_changed_reruns_the_js_tracks(gate):
    plan = gate.js_rerun_plan(JS_RED, "M\tweb/terms.js\nM\ttianxia/features/terms/routes.py\nA\tdocs/x.md")
    assert plan["rerun"], plan["why"]
    assert (plan["tracks"], plan["profiles"], plan["files"]) == (["facade"], ["season21", "test"], ["web/terms.js"])
    assert plan["first"] == {("facade", "season21"): [A, B], ("facade", "test"): [C, B]}
    assert set(gate.JS_TRACKS) == {"facade", "map", "beacon"}


def test_a_js_file_added_or_gone_is_not_rerun(gate):
    for status in ("A\tweb/x.js", "D\tweb/terms.js", "R100\tweb/a.js\tweb/b.js"):
        plan = gate.js_rerun_plan(JS_RED, "M\tweb/terms.js\n" + status)
        assert not plan["rerun"] and "script 清單會變" in plan["why"], status
    assert not gate.js_rerun_plan(JS_RED, "M\tweb/terms.css")["rerun"], "沒有改了的 js：不再跑"


def test_another_track_red_or_a_bot_red_is_not_rerun(gate):
    other = JS_RED.replace(_row("seal", "season21", A, A), _row("seal", "season21", A, C))
    plan = gate.js_rerun_plan(other, "M\tweb/terms.js")
    assert not plan["rerun"] and "seal" in plan["why"]
    bot = JS_RED.replace(f"base {A}｜head {A} 一樣", f"base {A}｜head {C} 不一樣")
    assert not gate.js_rerun_plan(bot, "M\tweb/terms.js")["rerun"]
    assert not gate.js_rerun_plan(JS_RED + "\nTraceback (most recent call last):", "M\tweb/terms.js")["rerun"]
    half = "\n".join([_row("sortie", "season21", A, A, crossover=C), "有不一樣的"])
    assert not gate.js_rerun_plan(half, "M\tweb/terms.js")["rerun"], "半舊半新不一樣也算紅"
    assert not gate.js_rerun_plan("全部一樣", "M\tweb/terms.js")["rerun"]


def test_the_rerun_verdict(gate):
    plan = gate.js_rerun_plan(JS_RED, "M\tweb/terms.js")
    same = "\n".join([_row("facade", "season21", B, B), _row("facade", "test", B, B), "全部一樣"])
    v = gate.js_rerun_verdict(plan, same)
    assert v["ok"] and v["rerun"] == {"facade season21": [B, B], "facade test": [B, B]}
    assert "整段一樣，比對這一項算過" in gate.js_rerun_note(plan, v)
    still = same.replace(_row("facade", "test", B, B), _row("facade", "test", C, B))
    v = gate.js_rerun_verdict(plan, still)
    assert not v["ok"] and "facade test 再跑還是不一樣" in v["bad"][0] and "照舊紅" in gate.js_rerun_note(plan, v)
    moved = "\n".join([_row("facade", "season21", C, C), _row("facade", "test", B, B), "全部一樣"])
    v = gate.js_rerun_verdict(plan, moved)
    assert not v["ok"] and "不等於第一次的" in v["bad"][0], "再跑一樣、head 雜湊卻跟第一次不同：不算"
    assert not gate.js_rerun_verdict(plan, _row("facade", "season21", B, B))["ok"], "少一列：不算"
    assert "沒再跑" in gate.js_rerun_note({"rerun": False, "why": "x"}, None)


def test_the_rerun_swaps_the_heads_js_into_a_copy_of_the_base(gate, tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    for root, text in ((base, "old"), (head, "new")):
        (root / "web").mkdir(parents=True)
        (root / "web" / "terms.js").write_text(text, encoding="utf-8")
        (root / "web" / "app.js").write_text(text, encoding="utf-8")
    fake = tmp_path / "fake_sb.py"
    fake.write_text("import sys, pathlib\nb = pathlib.Path(sys.argv[sys.argv.index('--base') + 1])\n"
                    "print(' '.join(sys.argv[2:]).replace(str(b), 'B'))\nprint((b / 'web' / 'terms.js').read_text(), (b / 'web' / 'app.js').read_text())\n", encoding="utf-8")
    import sys

    plan = {"tracks": ["facade"], "profiles": ["season21", "test"], "files": ["web/terms.js"]}
    extra = ["--tracks", "facade,seal", "--jobs", "2", "--profiles", "season21,test", "--crossover", "--bot-covers", "seal", "--new", "terms", "--also-existing"]
    text = gate.js_rerun(sys.executable, str(fake), base, head, tmp_path / "tmp", plan, extra, tmp_path / "out.txt", None)
    first, second = text.splitlines()[:2]
    assert first.endswith("--tracks facade --profiles season21,test --no-bots --crossover --new terms --also-existing")
    assert "--bot-covers" not in first and "--jobs" not in first
    assert second == "new old", "只換進 plan 的檔，別的留 base 的"
    assert not (tmp_path / "tmp" / "base_js").exists() and (base / "web" / "terms.js").read_text(encoding="utf-8") == "old"
