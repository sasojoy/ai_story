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


def test_content_picks_its_tests_but_the_real_content_season_only_with_slow():
    """手冊 4.3：內容改了挑 test_content.py 與寫到那個檔名的；test_real_content.py（整季）每日整套會跑，--slow 才加。"""
    assert "test_content.py" in _names(["content/skills.json"])
    assert "test_real_content.py" not in _names(["content/skills.json"])
    assert "test_real_content.py" in _names(["content/skills.json"], slow=True)


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
    def marker(cmd):  # python -m pytest 後面那一個 -m
        return cmd[cmd.index("-m", cmd.index("pytest")) + 1]

    cmd = test_for.pytest_command(three, slow=False, extra=[])
    assert marker(cmd) == "not slow"
    if importlib.util.find_spec("xdist") is not None:
        assert cmd[cmd.index("-n") + 1] == "4"
    assert marker(test_for.pytest_command(three, slow=True, extra=[])) == "slow or not slow"
    mine = test_for.pytest_command(three, slow=False, extra=["-n", "2"])
    assert mine.count("-n") == 1 and mine[mine.index("-n") + 1] == "2"
    one = test_for.pytest_command(test_for.Pick(files={ROOT / "tests/arts/test_fusion.py"}), slow=False, extra=[])
    assert "-n" not in one


def test_core_targets_are_the_core_folder():
    goal = test_for.targets(test_for.Pick(core=True))
    assert "tests/core/test_engine.py" in goal and all(g.startswith("tests/core/") for g in goal)
