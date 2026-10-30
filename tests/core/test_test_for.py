"""scripts/test_for.py：改了哪些檔就挑哪幾條測試（開發規範手冊 4.3 的挑法）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("test_for", ROOT / "scripts" / "test_for.py")
test_for = importlib.util.module_from_spec(_spec)
sys.modules["test_for"] = test_for  # dataclass 要從 sys.modules 找得到它的模組
_spec.loader.exec_module(test_for)

# 假的 engine.py：hunk 落在哪個方法照這一份找（行號：choose 2～3、_tavern_price 5～6、_deliver_seal_results 8～9、_side 11～12）
FAKE_ENGINE = (
    "class Game:\n"
    "    def choose(self, kind, arg):\n"
    "        pass\n"
    "\n"
    "    def _tavern_price(self, base):\n"
    "        return base\n"
    "\n"
    "    def _deliver_seal_results(self):\n"
    "        pass\n"
    "\n"
    "    def _side(self):\n"
    "        return None\n"
)
FAKE_SERVER = (
    "@app.post(\"/api/mall/buy\")\n"
    "def api_mall_buy(request):\n"
    "    return 1\n"
    "\n"
    "def _locked(game):\n"
    "    return game\n"
)
FAKE_MODELS = (
    "class PlayerState(BaseModel):\n"
    "    hp: int = 0\n"
    "    mall_tokens: dict = {}\n"
)


def _names(files, **kw):
    return {p.name for p in test_for.pick(files, **kw).files}


def _added(path, src, *lines):
    """假裝在 src 的這幾行（行號）改了東西：只有加上的行。"""
    text = src.splitlines()
    return {path: ([([], [(n, text[n - 1]) for n in lines])], src, src)}


def test_a_module_picks_the_tests_that_import_it():
    names = _names(["tianxia/glyph.py"])
    assert "test_sensing.py" in names and "test_real_content.py" not in names


def test_content_picks_its_tests_and_the_fast_part_of_real_content():
    """內容改了挑 test_content.py、寫到那個檔名的，加 test_real_content.py 不是 slow 的那些（147 條只有整季那 11 條是 slow；
    其他的含事件難度帶 DIFFICULTY_BANDS 的鎖、地點走得到，-n 4 約 25 秒）。整季那幾條照舊要 --slow（手冊 4.3 的本意）。"""
    picked = test_for.pick(["content/events/explore_jizhou.json"])
    assert {"test_content.py", "test_real_content.py"} <= {p.name for p in picked.files}
    (cmd,) = test_for.pytest_commands(picked, slow=False, extra=[])
    assert _marker(cmd) == "not slow"
    real = next(p for p in picked.files if p.name == "test_real_content.py")
    assert not test_for.whole_slow(real), "test_real_content.py 整個標 slow 的話，內容改了就一條難度帶都不驗"
    (both,) = test_for.pytest_commands(picked, slow=True, extra=[])
    assert _marker(both) == "slow or not slow" and "tests/season/test_real_content.py" in both


def test_the_promotion_and_rank_action_content_picks_the_tests_that_pin_it():
    """第一季正式版丙一、丙二、戊一的測試檔用真實內容釘住晉升奇遇與第 3、4 階行動：改那幾個內容檔時要挑到它們（整合審查 M2）。"""
    promotions = {"test_promotions_high.py", "test_promotions_huang.py"}
    assert promotions <= _names(["content/promotions.json"])
    assert promotions <= _names(["content/events/promotion.json"])
    assert "test_rank_actions.py" in _names(["content/orders.json"])


def test_shared_test_setup_adds_nothing():
    """手冊 4.3：conftest、fixtures、pyproject 改了只跑改到的那幾個測試檔，整套留給每日整套。"""
    for f in ("tests/conftest.py", "pyproject.toml"):
        picked = test_for.pick([f])
        assert picked.empty and not picked.everything, f
    assert _names(["tests/conftest.py", "tests/arts/test_fusion.py"]) == {"test_fusion.py"}


def test_docs_pick_nothing_and_a_test_file_picks_itself():
    assert test_for.pick(["docs/superpowers/specs/x.md", "CLAUDE.md"]).empty
    assert _names(["tests/arts/test_fusion.py"]) == {"test_fusion.py"}


def test_an_engine_method_picks_its_group_and_not_everyone_who_imports_engine():
    """改 Game 的 _tavern_price → 酒肆那一群（test_tavern*、檔名有 tavern 的），不再因為 import 了 engine 就挑七成。"""
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 6))
    names = {p.name for p in picked.files}
    assert {"test_tavern.py", "test_tavern_seek_presence.py"} <= names
    assert "test_engine.py" not in names and "test_server.py" not in names
    assert not picked.core and not picked.smoke


def test_a_group_also_takes_the_tests_that_mostly_call_it():
    """走一趟的方法叫 outing_*，引擎測試的檔名卻是 test_explore_one*（FB-880 只改 _outing_foe，壞的是
    test_explore_one_single）：內文叫最多的是那一群（至少 DOMINANT_MIN 次）的測試檔也算那一群的。
    拿別群的方法當準備動作的不算（不然改一個管理者工具、一個酒肆方法就挑一大片）。"""
    src = "class Game:\n    def _outing_foe(self, loc, kind):\n        return None, None\n"
    names = _names(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", src, 3))
    assert {"test_outing.py", "test_explore_one_single.py", "test_drill_gates_engine.py"} <= names
    assert len(test_for.group_files("tavern")) <= 10 and len(test_for.group_files("admin")) <= 30


def test_a_verb_first_method_name_goes_to_the_feature_after_the_verb():
    """_deliver_seal_results 的 deliver 是動詞：照後面的 seal 分群。"""
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 9))
    assert "test_seal.py" in {p.name for p in picked.files} and not picked.core


def test_a_shared_method_goes_by_the_features_the_hunk_mentions():
    """choose 這種大家都插一段的方法：看 hunk 提到哪些功能前綴；什麼都沒提到 → 核心測試＋煙霧。"""
    src = FAKE_ENGINE.replace("        pass\n", "        if kind == 'arena': return self._arena_enter(arg)\n", 1)
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", src, 3))
    assert "test_arena.py" in {p.name for p in picked.files} and not picked.core
    plain = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 3))
    assert plain.core and plain.smoke and not plain.files


def test_a_shared_helper_without_a_feature_is_core():
    """_side 這種共用的小方法（服務）：認不出功能 → 核心測試＋煙霧。"""
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 12))
    assert picked.core and picked.smoke


def test_the_shared_services_of_the_handbook_are_core_even_when_named_like_a_feature():
    """手冊 3.3 列為 ctx 的共用服務（_side、_save_season、_pill_day、_write、_guide、_wallet……）被叫幾十上百次：
    改到就是核心（核心測試＋煙霧），不是名字裡那個字的小功能群（_save_season 不是 season、_pill_day 不是 pill），
    hunk 裡提到的功能前綴另外加（_side 改成問 allied → 也加 allied 那一群）。"""
    src = (
        "class Game:\n"
        "    def _side(self):\n"
        "        return allied.side_of(self.state, self.content) or None\n"
        "\n"
        "    def _save_season(self):\n"
        "        self._write()  # 註解\n"
        "\n"
        "    def _pill_day(self):\n"
        "        return 1\n"
    )
    for line, name in ((3, "_side"), (6, "_save_season"), (9, "_pill_day")):
        picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", src, line))
        assert picked.core and picked.smoke, name
        assert not {p.name for p in picked.files} & {"test_pill_per_day.py", "test_season_pause.py"}, name
    side = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", src, 3))
    assert any("allied" in p.name for p in side.files)


def test_every_shared_service_is_a_real_game_method():
    """CORE_METHODS 跟著 engine.py 走：改了名字、拿掉了，這裡紅（不然那個服務改到時悄悄落回小功能群）。"""
    methods = {name for name, *_ in test_for._game_methods((ROOT / "tianxia" / "engine.py").read_text(encoding="utf-8"))}
    assert test_for.CORE_METHODS <= methods, sorted(test_for.CORE_METHODS - methods)
    assert {"_log", "_write", "_save_season", "_side", "_pill_day", "_cost_option", "stamp", "_guide",
            "_quick_client", "_wallet"} <= test_for.CORE_METHODS


def test_a_removed_line_is_found_in_the_old_file():
    """整個方法拿掉：拿掉的行照舊檔的行號找方法。"""
    old = FAKE_ENGINE
    new = FAKE_ENGINE.replace("    def _tavern_price(self, base):\n        return base\n\n", "")
    hunk = {"tianxia/engine.py": ([([(5, "    def _tavern_price(self, base):"), (6, "        return base")], [])], old, new)}
    assert "test_tavern.py" in _names(["tianxia/engine.py"], hunks_of=hunk)


def test_models_and_state_are_core_plus_the_field_prefix():
    """models.py、state.py 改了 → 核心測試＋煙霧＋自己的測試檔；欄位名帶功能前綴（mall_tokens）的再加那一群。"""
    picked = test_for.pick(["tianxia/state.py"], hunks_of=_added("tianxia/state.py", FAKE_MODELS, 3))
    names = {p.name for p in picked.files}
    assert picked.core and picked.smoke
    assert {"test_mall.py", "test_wallet.py"} & names and "test_tavern.py" not in names
    bare = test_for.pick(["tianxia/models.py"], hunks_of=_added("tianxia/models.py", FAKE_MODELS, 2))
    assert bare.core and bare.smoke and {p.name for p in bare.files} == {"test_models.py"}


def test_a_server_route_picks_its_prefix_and_the_shell_is_core():
    route = test_for.pick(["server.py"], hunks_of=_added("server.py", FAKE_SERVER, 3))
    names = {p.name for p in route.files}
    assert {"test_server.py", "test_mall.py"} <= names and not route.core
    shell = test_for.pick(["server.py"], hunks_of=_added("server.py", FAKE_SERVER, 6))
    assert shell.core and shell.smoke and {p.name for p in shell.files} == {"test_server.py"}


def test_core_modules_are_core_tests_and_smoke_not_their_importers():
    picked = test_for.pick(["tianxia/rules.py"])
    assert picked.core and picked.smoke
    assert {p.name for p in picked.files} <= {"test_rules.py"}


def test_a_feature_package_picks_its_own_tests_and_the_contract(tmp_path, monkeypatch):
    pkg = tmp_path / "mall" / "tests"
    pkg.mkdir(parents=True)
    (pkg / "test_mall_pkg.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(test_for, "FEATURES", tmp_path)
    picked = test_for.pick(["tianxia/features/mall/actions.py"])
    assert {p.name for p in picked.files} >= {"test_mall_pkg.py"} and not picked.core


def test_slow_is_opt_in_and_three_files_run_on_four_workers():
    three = test_for.Pick(files={ROOT / "tests/arts/test_fusion.py", ROOT / "tests/arts/test_naming.py",
                                 ROOT / "tests/arts/test_library.py"})
    (cmd,) = test_for.pytest_commands(three, slow=False, extra=[])
    assert _marker(cmd) == "not slow"
    if importlib.util.find_spec("xdist") is not None:
        assert cmd[cmd.index("-n") + 1] == "4"
    (both,) = test_for.pytest_commands(three, slow=True, extra=[])
    assert _marker(both) == "slow or not slow"
    (mine,) = test_for.pytest_commands(three, slow=False, extra=["-n", "2"])
    assert mine.count("-n") == 1 and mine[mine.index("-n") + 1] == "2"
    (one,) = test_for.pytest_commands(test_for.Pick(files={ROOT / "tests/arts/test_fusion.py"}), slow=False, extra=[])
    assert "-n" not in one


def _marker(cmd):
    """python -m pytest 後面那一個 -m 的式子。"""
    return cmd[cmd.index("-m", cmd.index("pytest")) + 1]


def test_a_changed_test_file_runs_with_its_slow_tests():
    """手冊 4.3「只跑改到的那幾個測試檔」：改了一個整個檔標 slow 的測試檔，就是要跑它，連 slow 一起
    （以前 -m "not slow" 把它整個濾掉，39 deselected、結束碼 5）。"""
    own = test_for.pick(["tests/arts/test_epiphany.py", "tests/core/test_errands.py"])
    (cmd,) = test_for.pytest_commands(own, slow=False, extra=[])
    assert _marker(cmd) == "slow or not slow"
    assert {"tests/arts/test_epiphany.py", "tests/core/test_errands.py"} <= set(cmd)


def test_changed_slow_test_files_run_apart_from_the_rest_of_the_pick():
    """改到的測試檔連 slow 一起跑，其他挑到的照舊不含 slow：分兩次，改到的那幾個不在第一次裡重複跑。"""
    mixed = test_for.pick(["tests/arts/test_epiphany.py"])
    mixed.files.add(ROOT / "tests/arts/test_fusion.py")
    mixed.core = True
    first, second = test_for.pytest_commands(mixed, slow=False, extra=[])
    assert _marker(first) == "not slow" and "tests/arts/test_fusion.py" in first
    assert "tests/arts/test_epiphany.py" not in first and "tests/core/test_errands.py" in first
    assert _marker(second) == "slow or not slow" and second[-1] == "tests/arts/test_epiphany.py"
    plain = test_for.pick(["tests/arts/test_fusion.py"])  # 沒有 slow 的測試檔：一次就好
    assert len(test_for.pytest_commands(plain, slow=False, extra=[])) == 1


def test_a_pick_that_is_all_slow_says_so_and_does_not_fail(capsys):
    """挑到的全在整個檔標 slow 的檔裡：先列出來；一條都沒跑（pytest 結束碼 5）時說要 --slow，結束碼 0。"""
    picked = test_for.Pick(files={ROOT / "tests/arts/test_epiphany.py"})
    assert any("--slow" in line and "test_epiphany.py" in line for line in test_for.describe(picked))
    assert test_for.finish([5], picked, slow=False) == 0
    assert "--slow" in capsys.readouterr().out
    assert test_for.finish([0, 5], picked, slow=False) == 0
    assert test_for.finish([1, 0], picked, slow=False) == 1
    plain = test_for.Pick(files={ROOT / "tests/arts/test_fusion.py"})  # 不是 slow 濾掉的（例如 -- -k 濾光了）照 pytest 的
    assert test_for.finish([5], plain, slow=False) == 5


def test_the_smoke_set_covers_every_block():
    """手冊 4.3：過渡期每個區塊（CLAUDE.md 區塊表十二塊）在現有測試裡挑約 10 條標 smoke；測試資料夾大致照區塊分。"""
    ids = test_for.smoke_ids()
    assert 100 <= len(ids) <= 150 and len(set(ids)) == len(ids)
    folders = {i.split("/")[1] for i in ids}
    assert {"core", "acts", "battle", "arts", "gear", "figures", "ranger", "seal", "mall", "map", "bots", "season"} <= folders
    goal = test_for.targets(test_for.Pick(files={ROOT / "tests/core/test_engine.py"}, smoke=True))
    assert "tests/core/test_engine.py" in goal and not any(g.startswith("tests/core/test_engine.py::") for g in goal)


def test_the_web_scripts_are_the_ones_every_web_test_loads():
    """網頁測試每一條都載入 webharness.APP_FILES 那幾個檔：改其中哪一個都照 app.js 挑（outing.js 10/30 加進去時漏了）。"""
    import re
    harness = (ROOT / "tests" / "kit" / "webharness.py").read_text(encoding="utf-8")
    app_files = set(re.findall(r'"([\w.]+\.js)"', re.search(r"^APP_FILES = \(([^)]*)\)", harness, re.M).group(1)))
    assert test_for.WEB_SCRIPTS == app_files
    outing = _names(["web/outing.js"])
    assert {"test_server.py", "test_outing_web.py"} < outing and _names(["web/app.js"]) <= outing


def test_core_targets_are_the_core_folder():
    goal = test_for.targets(test_for.Pick(core=True))
    assert "tests/core/test_engine.py" in goal and all(g.startswith("tests/core/") for g in goal)
