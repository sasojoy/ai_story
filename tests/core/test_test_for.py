"""scripts/test_for.py：改了哪些檔就挑哪幾條測試（開發規範手冊 4.3 的挑法）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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
    picked = test_for.pick(["tianxia/glyph.py"])
    assert "test_sensing.py" in {p.name for p in picked.files} and not picked.core
    assert any("sensing" in w for w in picked.why)  # 經 import 它的 sensing 再挑（T-02）


def test_a_module_also_picks_the_tests_of_the_modules_that_import_it():
    """10/31 測試自檢 T-02：might.py 沒有測試檔直接 import，以前挑 0 個；把 might.now 改成回 0，透過 ascend、create 用到它的
    test_ascend、test_create_ritual 會紅。現在照 tianxia/ 模組之間的 import 往上找。"""
    picked = test_for.pick(["tianxia/might.py"])
    assert {"test_ascend.py", "test_create_ritual.py"} <= {p.name for p in picked.files}
    assert not picked.core and not picked.smoke
    ups = test_for.dependents("might")
    assert {"ascend", "create"} <= ups
    assert not ups & test_for.DRIVERS and not ups & test_for.CORE_MODULES  # engine、假人、核心不往上走


def test_the_import_graph_skips_type_checking_and_imports_inside_functions():
    tree = test_for._ast(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "from . import alpha, beta as b\n"
        "from .gamma import thing\n"
        "import tianxia.delta\n"
        "try:\n"
        "    from . import eps\n"
        "except ImportError:\n"
        "    pass\n"
        "if TYPE_CHECKING:\n"
        "    from .engine import Game\n"
        "def late():\n"
        "    from . import zeta\n"
    )
    known = frozenset({"alpha", "beta", "gamma", "delta", "eps", "engine", "zeta"})
    assert test_for._module_deps(tree, known) == {"alpha", "beta", "gamma", "delta", "eps"}


def test_an_aggregator_is_picked_but_not_walked_through(monkeypatch):
    """彙整的模組（import 很多模組的 skillview 這種）：依賴它算，可是不再往上走；DRIVERS 與核心連算都不算。"""
    many = frozenset(f"m{i}" for i in range(test_for.AGGREGATOR_FANOUT))
    graph = {"low": frozenset(), "mid": frozenset({"low"}), "agg": frozenset({"mid"}) | many,
             "top": frozenset({"agg"}), "bot": frozenset({"mid"}), "rules": frozenset({"low"})}
    monkeypatch.setattr(test_for, "module_graph", lambda: graph)
    test_for.dependents.cache_clear()
    try:
        assert test_for.dependents("low") == {"mid", "agg"}
    finally:
        test_for.dependents.cache_clear()


def test_a_low_module_with_too_many_dependents_runs_core_and_smoke_instead():
    """tactics、zh 這種底層模組往上找會挑到兩、三百個檔：超過 IMPORT_CAP 只挑直接 import 的，加核心測試＋煙霧。"""
    picked = test_for.pick(["tianxia/zh.py"])
    assert picked.core and picked.smoke
    assert len(picked.files) < test_for.IMPORT_CAP
    assert any("太多" in w for w in picked.why)


@pytest.mark.parametrize("module, kind, expected", [
    ("wanted", "wanted", {"test_bounties.py", "test_sanren_web.py"}),
    ("mingtie_card", "mingtie", {"test_mingtie.py"}),
])
def test_a_module_engine_imports_to_register_picks_the_tests_that_name_its_action(module, kind, expected):
    """T-02：wanted.py、mingtie_card.py 只靠 engine 的 `as _x  # noqa: F401` 登記進 social.ACTIONS，測試經 peer_card／peer_act
    用到、沒有人 import：照登記的動作名挑寫到它的測試檔。讓 wanted.buttons 回 []，test_bounties 與 test_sanren_web 會紅。"""
    assert kind in test_for.registered_actions(module)
    assert expected <= _names([f"tianxia/{module}.py"])
    assert test_for.registered_actions("might") == ()


def test_a_module_picks_the_tests_named_after_its_first_word():
    assert "test_mingtie.py" in _names(["tianxia/mingtie_card.py"])


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


FAKE_CONFTEST = (
    "import pytest\n"                                   # 1
    "\n"
    "def classic_rules(content):\n"                     # 3
    "    return content\n"                              # 4
    "\n"
    "@pytest.fixture(autouse=True)\n"                   # 6
    "def isolated_database(tmp_path):\n"                # 7
    "    yield\n"                                       # 8
    "\n"
    "@pytest.fixture\n"                                 # 10
    "def content():\n"                                  # 11
    "    return 1\n"                                    # 12
    "\n"
    "@pytest.fixture(scope='session')\n"                # 14
    "def _prologue_master(tmp_path_factory):\n"         # 15
    "    return 1\n"                                    # 16
    "\n"
    "@pytest.fixture\n"                                 # 18
    "def prologue_content(_prologue_master):\n"         # 19
    "    return _prologue_master\n"                     # 20
)


def test_conftest_picks_the_tests_that_use_the_changed_helper():
    """手冊 4.3：conftest 改了跑「直接相關的」——hunk 落在哪個函式或 fixture，用到它的測試檔（from conftest import、
    fixture 參數）；conftest 裡別的 fixture 用到它的，連那一個的使用者一起。"""
    helper = test_for.pick(["tests/conftest.py"], hunks_of=_added("tests/conftest.py", FAKE_CONFTEST, 4))
    users = {p.name for p in helper.files}
    assert len(users) >= 10 and not helper.smoke and not helper.core
    assert all("classic_rules" in test_for._text(p) for p in helper.files)
    chained = test_for.pick(["tests/conftest.py"], hunks_of=_added("tests/conftest.py", FAKE_CONFTEST, 16))
    assert chained.files and all("prologue_content" in test_for._text(p) for p in chained.files)


def test_conftest_changes_that_touch_every_test_run_the_smoke_set():
    """autouse 的 fixture、模組最外層（import、sys.path）、或一個幾百個檔都在用的 fixture（content）：一個一個挑等於整套，
    跑煙霧（每一塊一小撮），整套留給每日整套。"""
    for line in (1, 8, 12):
        picked = test_for.pick(["tests/conftest.py"], hunks_of=_added("tests/conftest.py", FAKE_CONFTEST, line))
        assert picked.smoke and not picked.files and not picked.core, line
        assert picked.why and not any("文件" in w for w in picked.why), line


def test_test_settings_pick_nothing_and_do_not_say_docs(capsys):
    assert test_for.pick(["pyproject.toml"]).empty
    assert test_for.main(["pyproject.toml", "--list"]) == 0
    out = capsys.readouterr().out
    assert "pyproject.toml" in out and "文件之類" not in out
    assert _names(["tests/arts/test_fusion.py", "pyproject.toml"]) == {"test_fusion.py"}


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


def test_the_pickers_own_test_is_in_no_feature_group():
    """這個檔的內文是假的 engine、server、models（_tavern_price、_pill_day……寫在字串裡）：照「內文叫最多」會被算進酒肆、
    pill、season，每一群多它 31 條（10/31 審查：改 _tavern_price 從 43 條變 74 條，test_test_for 不 import engine）。
    它只在改 scripts/test_for.py（與它自己）時跑。"""
    me = ROOT / "tests" / "core" / "test_test_for.py"
    assert not sorted(w for w in test_for.vocabulary() if me in test_for.group_files(w))
    tavern = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 6))
    assert me not in tavern.files and "test_tavern.py" in {p.name for p in tavern.files}
    assert me in test_for.pick(["scripts/test_for.py"]).files


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


def test_the_core_modules_are_one_list_for_the_picker_and_the_boundary_test():
    """「核心」只有一份：tianxia/core/__init__.py 的 MODULES（手冊 3.1 的十三個、3.10 的錢包、PM 10/31 定算核心的江湖紀錄）。
    test_for 照語法樹讀它（不 import）、邊界測試 import 它。10/31 審查：以前兩邊各寫一份，邊界的有 journal、wallet，
    test_for 的沒有——改 journal.py 挑「import 它的」22 個檔、改 wallet.py 挑 8 個檔，都沒有核心測試與煙霧。"""
    from tianxia import core
    import test_feature_boundaries
    assert {"journal", "wallet", "models", "state", "rules", "naming"} <= core.MODULES
    assert test_for.CORE_MODULES == core.MODULES
    assert set(test_feature_boundaries.CORE) == set(core.MODULES)


def test_the_core_modules_are_read_from_the_syntax_tree_and_a_broken_file_says_so(tmp_path, capsys):
    """照語法樹讀（不 import）；讀不出來在 stderr 說一聲、當成沒有，test_for 照樣挑得下去。"""
    good = tmp_path / "good.py"
    good.write_text('"""核心。"""\nMODULES = frozenset({\n    "a", "b",\n})\n', encoding="utf-8")
    assert test_for.core_modules(good) == {"a", "b"}
    broken = tmp_path / "broken.py"
    broken.write_text("MODULES = frozenset({\n", encoding="utf-8")
    assert test_for.core_modules(broken) == frozenset()
    missing = tmp_path / "none.py"
    missing.write_text("OTHER = 1\n", encoding="utf-8")
    assert test_for.core_modules(missing) == frozenset()
    err = capsys.readouterr().err
    assert err.count("讀不出核心的模組") == 2 and "沒有 MODULES" in err


@pytest.mark.parametrize("module", ["journal", "wallet"])
def test_the_journal_and_the_wallet_pick_like_the_rest_of_the_core(module):
    """核心改了跑核心測試＋煙霧＋自己檔名的測試（手冊 4.2、4.3），不照「誰 import 它」挑；錢包、江湖紀錄也是核心。"""
    picked = test_for.pick([f"tianxia/{module}.py"])
    assert picked.core and picked.smoke
    assert {p.name for p in picked.files} == {f"test_{module}.py"}


def test_a_feature_package_picks_its_own_tests_and_the_contract(tmp_path, monkeypatch):
    pkg = tmp_path / "mall" / "tests"
    pkg.mkdir(parents=True)
    (pkg / "test_mall_pkg.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(test_for, "FEATURES", tmp_path)
    picked = test_for.pick(["tianxia/features/mall/actions.py"])
    assert {p.name for p in picked.files} >= {"test_mall_pkg.py"} and not picked.core


@pytest.mark.parametrize("changed, package", [
    ("tianxia/features/mall/rules.py", "mall"),  # 不是 tianxia/rules.py（核心）：不帶核心測試與煙霧
    ("tianxia/features/mall/actions.py", "mall"),
    ("tianxia/features/mall/routes.py", "mall"),
    ("tianxia/features/feast/rules.py", "feast"),
])
def test_a_package_file_on_this_tree_picks_only_that_package_and_the_contract(changed, package):
    own = {p.name for p in (test_for.FEATURES / package / "tests").rglob("test_*.py")}
    contract = {p.name for p in test_for.contract_tests()}  # 核心契約含邊界測試（手冊 4.1 第三級）
    assert {"test_contract_core.py", "test_contract_features.py", "test_feature_boundaries.py"} <= contract
    picked = test_for.pick([changed])
    assert own and own | contract == {p.name for p in picked.files} and not picked.core and not picked.smoke


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
    own = test_for.pick(["tests/core/test_story_wolong.py", "tests/core/test_story_maier.py"])
    (cmd,) = test_for.pytest_commands(own, slow=False, extra=[])
    assert _marker(cmd) == "slow or not slow"
    assert {"tests/core/test_story_wolong.py", "tests/core/test_story_maier.py"} <= set(cmd)


def test_changed_slow_test_files_run_apart_from_the_rest_of_the_pick():
    """改到的測試檔連 slow 一起跑，其他挑到的照舊不含 slow：分兩次，改到的那幾個不在第一次裡重複跑。"""
    mixed = test_for.pick(["tests/core/test_story_wolong.py"])
    mixed.files.add(ROOT / "tests/arts/test_fusion.py")
    mixed.core = True
    first, second = test_for.pytest_commands(mixed, slow=False, extra=[])
    assert _marker(first) == "not slow" and "tests/arts/test_fusion.py" in first
    assert "tests/core/test_story_wolong.py" not in first and "tests/core/test_engine.py" in first
    assert _marker(second) == "slow or not slow" and second[-1] == "tests/core/test_story_wolong.py"
    plain = test_for.pick(["tests/arts/test_fusion.py"])  # 沒有 slow 的測試檔：一次就好
    assert len(test_for.pytest_commands(plain, slow=False, extra=[])) == 1
    # 這個檔的字串裡寫了 "@pytest.mark.slow"（_slow_smoke 的例子），不是標記：也是一次就好
    assert not test_for.has_slow(ROOT / "tests/core/test_test_for.py")
    assert test_for.has_slow(ROOT / "tests/core/test_story_wolong.py")


def test_a_pick_that_is_all_slow_says_so_and_does_not_fail(capsys):
    """挑到的全在整個檔標 slow 的檔裡：先列出來；一條都沒跑（pytest 結束碼 5）時說要 --slow，結束碼 0。"""
    picked = test_for.Pick(files={ROOT / "tests/core/test_story_wolong.py"})
    assert any("--slow" in line and "test_story_wolong.py" in line for line in test_for.describe(picked))
    assert test_for.finish([5], picked, slow=False) == 0
    assert "--slow" in capsys.readouterr().out
    assert test_for.finish([0, 5], picked, slow=False) == 0
    assert test_for.finish([1, 0], picked, slow=False) == 1
    plain = test_for.Pick(files={ROOT / "tests/arts/test_fusion.py"})  # 不是 slow 濾掉的（例如 -- -k 濾光了）照 pytest 的
    assert test_for.finish([5], plain, slow=False) == 5


def _slow_smoke(text: str, names: list[str]) -> bool:
    """這一條煙霧（檔裡的 names：類別、函式）是不是也標了 slow（整個檔、類別或函式本身）。"""
    import ast
    import re
    if re.search(r"^pytestmark[ \t]*=.*\bslow\b", text, re.M) or (not names and "mark.slow" in text):
        return True
    body = ast.parse(text).body
    for name in names:
        node = next(n for n in body if getattr(n, "name", None) == name)
        marks = [ast.unparse(d) for d in node.decorator_list]
        if isinstance(node, ast.ClassDef):
            marks += [ast.unparse(s.value) for s in node.body if isinstance(s, ast.Assign)
                      and any(getattr(t, "id", None) == "pytestmark" for t in s.targets)]
            body = node.body
        if any(re.search(r"\bslow\b", m) for m in marks):
            return True
    return False


def test_a_slow_smoke_test_is_caught():
    assert _slow_smoke("import pytest\n@pytest.mark.smoke\n@pytest.mark.slow\ndef test_x():\n    pass\n", ["test_x"])
    assert _slow_smoke("import pytest\npytestmark = pytest.mark.slow\n@pytest.mark.smoke\ndef test_x():\n    pass\n",
                       ["test_x"])
    assert _slow_smoke("import pytest\n@pytest.mark.slow\nclass TestA:\n    @pytest.mark.smoke\n    def test_x(self):\n"
                       "        pass\n", ["TestA", "test_x"])
    assert not _slow_smoke("import pytest\n@pytest.mark.smoke\ndef test_x():\n    pass\n", ["test_x"])


def test_the_smoke_set_covers_every_block():
    """手冊 4.3：過渡期每個區塊（CLAUDE.md 區塊表十二塊）在現有測試裡挑約 10 條標 smoke；測試資料夾大致照區塊分。
    煙霧不能也是 slow：單獨跑 -m smoke 會蓋掉 addopts 的 not slow（那一條就跑了、兩分鐘的保證破了），test_for 照
    -m "not slow" 跑又會悄悄把它濾掉（那一塊的煙霧少一條）。"""
    ids = test_for.smoke_ids()
    assert 100 <= len(ids) <= 150 and len(set(ids)) == len(ids)
    slow = [i for i in ids if _slow_smoke(test_for._text(ROOT / i.split("::")[0]), i.split("::")[1:])]
    assert not slow, f"煙霧不能標 slow：{slow}"
    # 手冊 4.3「搬成包的區塊，煙霧改成那一包 tests/ 裡的一條」：tianxia/features/<包>/tests/ 的算那一包（商城的在 mall 包裡）
    blocks = {(p[2] if p[:2] == ["tianxia", "features"] else p[1]) for p in (i.split("::")[0].split("/") for i in ids)}
    assert {"core", "acts", "battle", "arts", "gear", "figures", "ranger", "seal", "mall", "map", "bots", "season"} <= blocks
    packages = {p.name for p in test_for.FEATURES.iterdir() if (p / "__init__.py").exists()}
    assert packages and packages <= blocks, f"每一包至少一條煙霧（手冊 4.1 第三級）：{sorted(packages - blocks)}"
    goal = test_for.targets(test_for.Pick(files={ROOT / "tests/core/test_engine.py"}, smoke=True))
    assert "tests/core/test_engine.py" in goal and not any(g.startswith("tests/core/test_engine.py::") for g in goal)


def test_the_web_scripts_are_the_ones_every_web_test_loads():
    """網頁測試每一條都載入 webharness.APP_FILES 那幾個檔：殼的（WEB_SCRIPTS）改哪一個都照 app.js 挑（outing.js 10/30 加進去時
    漏了）；功能包的 js（mall.js，各包登記的 web）也在 APP_FILES 裡，照那一包挑（PM 10/31）。兩樣合起來就是 APP_FILES。"""
    import re
    harness = (ROOT / "tests" / "kit" / "webharness.py").read_text(encoding="utf-8")
    app_files = set(re.findall(r'"([\w.]+\.js)"', re.search(r"^APP_FILES = \(([^)]*)\)", harness, re.M).group(1)))
    package_js = {name for name in test_for.feature_web() if name.endswith(".js")}
    assert package_js and not package_js & test_for.WEB_SCRIPTS
    assert test_for.WEB_SCRIPTS | package_js == app_files
    # 走一趟的 outing.js 主動搬六包第 3＋4 批登記成探索包的網頁檔：照那一包挑（寫到它的 test_outing_web 照樣在），不再照 app.js 一大批
    outing = _names(["web/outing.js"])
    assert "test_outing_web.py" in outing and "test_server.py" not in outing and test_for.feature_web()["outing.js"] == "explore"


def test_feature_web_is_what_the_packages_register():
    """test_for 照語法樹讀各包 __init__.py 的 web（不 import）：跟核心照 FEATURES 彙整的 web_files() 一樣、認得是哪一包的。"""
    from tianxia.core import features as features_core
    from tianxia.core.registry import FEATURES
    assert sorted(test_for.feature_web()) == sorted(features_core.web_files())
    assert test_for.feature_web() == {name: f.name for f in FEATURES for name in f.web}


def test_a_feature_packages_web_file_picks_that_package_not_the_app_js_batch():
    """web/mall.js、web/mall.css 是商城包的（手冊 3.7 第 1 階切出來的）：挑那一包的 tests/＋核心契約（＋寫到那個檔名的店面
    CSS 守門），不照 app.js 挑一大批、不加 test_server.py；PM 10/31。"""
    mall_tests = {p.name for p in (test_for.FEATURES / "mall" / "tests").rglob("test_*.py")}
    contract = {p.name for p in test_for.contract_tests()}
    js = test_for.pick(["web/mall.js"])
    assert {p.name for p in js.files} == mall_tests | contract and not js.core and not js.smoke
    assert "test_server.py" not in {p.name for p in js.files}
    assert not {p.name for p in js.files} & (_names(["web/app.js"]) - mall_tests - contract)
    css = {p.name for p in test_for.pick(["web/mall.css"]).files}
    assert mall_tests | contract | {"test_desktop_type.py", "test_shop_width.py"} <= css and "test_server.py" not in css
    assert "test_test_for.py" not in css  # 內文是假原始碼的（TEXT_BLIND）不照檔名算


def test_a_feature_packages_js_runs_the_package_tests_that_execute_it_with_their_slow_tests():
    """包的 js 只有包裡用假瀏覽器（webharness）跑整支頁面的測試會真的執行它，而商城的 test_mall_web.py 以前整個檔標 slow
    （10/31 起只有超過一秒的那幾條）：照「不含 slow」挑等於沒有一條在跑 mall.js（10/31 審查：插一行 function ((( 照預設 134 passed、exit 0，--slow 才 30 failed）。
    那幾個連 slow 一起跑，跟改到的測試檔一樣分開跑一次；挑到的其他檔照舊不含 slow，也不再列成「這一次不跑」。"""
    web_test = test_for.FEATURES / "mall" / "tests" / "test_mall_web.py"
    assert test_for.has_slow(web_test) and "webharness" in test_for.imported(web_test)
    js = test_for.pick(["web/mall.js"])
    assert web_test in js.files
    rest, slow_too = test_for.pytest_commands(js, slow=False, extra=[])
    assert _marker(rest) == "not slow" and test_for._rel(web_test) not in rest
    assert "tianxia/features/mall/tests/test_mall.py" in rest
    assert _marker(slow_too) == "slow or not slow" and test_for._rel(web_test) in slow_too
    assert not [a for a in slow_too[slow_too.index("slow or not slow") + 1:] if a.endswith(".py")
                and a != test_for._rel(web_test)]
    assert "test_mall_web.py" not in " ".join(test_for._slow_only(js))
    lines = test_for.describe(js)
    assert any("連 slow 一起跑" in line and "test_mall_web.py" in line for line in lines), lines
    # 樣式表不是 webharness 跑的：照舊一次、不含 slow（店面的 CSS 守門不是 slow）
    assert len(test_for.pytest_commands(test_for.pick(["web/mall.css"]), slow=False, extra=[])) == 1


CORE_OWN = {  # 手冊 3.1 的核心模組自己檔名的測試（10/31 有的這 11 個；state、sqlite_world 還沒有自己的測試檔）
    "test_accounts.py", "test_calendar.py", "test_characters.py", "test_content.py", "test_database.py",
    "test_gender.py", "test_models.py", "test_naming.py", "test_rules.py", "test_team.py", "test_world_state.py",
}


def test_core_tests_are_the_core_modules_own_tests_and_test_engine():
    """過渡期的「核心測試」（PM 10/31）＝手冊 3.1 核心模組自己檔名的測試（test_<模組>…，在哪個資料夾都算）＋
    tests/core/test_engine*.py＋tests/core/ 的核心契約、邊界、錢包服務測試；不是整個 tests/core/（那裡是雜燴：
    test_social、test_factions 這些屬於功能的，第 2 階搬包時搬走）。"""
    names = {p.name for p in test_for.core_tests()}
    assert CORE_OWN | {"test_engine.py"} <= names
    assert not names & {"test_social.py", "test_factions.py", "test_nightly.py", "test_test_for.py", "test_errands.py"}
    allowed = {f"test_{m}" for m in test_for.CORE_MODULES - test_for.NOT_CORE_TESTS} | {
        "test_engine", "test_contract", "test_feature_boundaries", "test_wallet"}
    assert all(any(p.stem == a or p.stem.startswith(a + "_") or (a in ("test_engine", "test_contract")
                                                                 and p.stem.startswith(a)) for a in allowed)
               for p in test_for.core_tests()), sorted(names)
    goal = test_for.targets(test_for.Pick(core=True))
    assert {"tests/core/test_engine.py", "tests/arts/test_naming.py", "tests/battle/test_team.py"} <= set(goal)
    assert "tests/core/test_social.py" not in goal
    # 第 1 階有了的核心契約、邊界、錢包服務（第 0 階收尾定的；test_wallet 從 tests/mall/ 搬到 tests/core/）
    assert {"tests/core/test_contract_core.py", "tests/core/test_contract_features.py",
            "tests/core/test_feature_boundaries.py", "tests/core/test_wallet.py"} <= set(goal)


def test_the_core_tests_stay_what_the_pm_defined_when_the_journal_joins_the_core():
    """江湖紀錄算核心（PM 10/31）只改「改了它挑什麼」：它自己的 test_journal 不收進核心測試（NOT_CORE_TESTS）——PM 10/31
    定的核心測試是手冊 3.1 那十三個自己的測試＋test_engine＋契約、邊界、錢包，收了改 models.py 一個欄位的底數
    再多七十幾條；要不要收等 PM 跟 < 1,500 一起定。錢包的 test_wallet 本來就在。"""
    names = {p.name for p in test_for.core_tests()}
    assert "test_wallet.py" in names and "test_journal.py" not in names
    assert test_for.NOT_CORE_TESTS <= test_for.CORE_MODULES


def test_core_tests_take_the_contract_boundary_and_wallet_tests_of_tests_core(tmp_path, monkeypatch):
    """第 1 階會在 tests/core/ 加核心契約（test_contract*）、邊界（test_feature_boundaries）、錢包服務（test_wallet）的
    測試：用 glob 收，現在沒有就是空的；tests/core/ 的其他檔不算。"""
    for name in ("test_contract_options.py", "test_contract.py", "test_feature_boundaries.py", "test_wallet.py",
                 "test_engine_sync.py", "test_social.py", "test_wallet_ledger.py"):
        (tmp_path / name).write_text("def test_x():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(test_for, "CORE_TESTS", tmp_path)
    names = {p.name for p in test_for.core_tests()}
    assert {"test_contract_options.py", "test_contract.py", "test_feature_boundaries.py", "test_wallet.py",
            "test_engine_sync.py"} <= names
    assert not names & {"test_social.py", "test_wallet_ledger.py"}


def _first_line(capsys, argv):
    assert test_for.main(argv) == 0
    return capsys.readouterr().out.splitlines()[0]


def test_the_base_is_develop_unless_the_env_or_the_flag_says_otherwise(monkeypatch, capsys):
    """PM 10/31：大家從 develop 開，不給 --base 跟 origin/develop 比；TIANXIA_TEST_BASE 與 --base 照舊蓋過預設
    （--base 最優先）。--list 第一行寫這一次跟哪個 base 比、是從哪裡來的。"""
    monkeypatch.delenv("TIANXIA_TEST_BASE", raising=False)
    assert test_for.default_base() == "origin/develop"
    first = _first_line(capsys, ["tests/arts/test_fusion.py", "--list"])
    assert "origin/develop" in first and "預設" in first
    assert "origin/develop" in _first_line(capsys, ["CLAUDE.md", "--list"])  # 挑不到東西的也先寫 base
    monkeypatch.setenv("TIANXIA_TEST_BASE", "origin/main")
    assert test_for.default_base() == "origin/main"
    first = _first_line(capsys, ["tests/arts/test_fusion.py", "--list"])
    assert "origin/main" in first and "TIANXIA_TEST_BASE" in first
    first = _first_line(capsys, ["tests/arts/test_fusion.py", "--list", "--base", "origin/develop"])
    assert "origin/develop" in first and "--base" in first


def test_a_base_that_was_never_fetched_stops_before_picking(monkeypatch, capsys):
    """這份 clone 的 git fetch origin 不更新 feature/*、dev/*：沒明確 fetch 的 base 找不到分岔點，挑法就不準——不給檔名
    只剩還沒提交的改動，給了檔名整個檔當新檔（10/31 審查：models.py 挑到 347 個檔、結束碼 0）。第一行說找不到、
    怎麼 fetch，然後停下、結束碼 2，一個檔都不挑、不跑。"""
    monkeypatch.delenv("TIANXIA_TEST_BASE", raising=False)
    fetch = "git fetch origin +refs/heads/feature/no-such-branch-1031:refs/remotes/origin/feature/no-such-branch-1031"
    for argv in (["--list"], ["tianxia/models.py", "--list"], ["tianxia/models.py", "--count"], ["tests/arts/test_fusion.py"]):
        assert test_for.main([*argv, "--base", "origin/feature/no-such-branch-1031"]) == 2, argv
        out = capsys.readouterr().out
        first = out.splitlines()[0]
        assert "找不到" in first and fetch in first and "挑不到" not in first, argv
        assert "要跑（" not in out and "一共" not in out and "結束碼 2" in out, argv


def test_a_base_without_a_fork_point_also_stops(monkeypatch, capsys):
    """base 在、可是跟 HEAD 沒有共同的祖先：一樣沒有分岔點可比，一樣停下。"""
    import subprocess
    real = test_for._git

    def no_fork(*args):
        return subprocess.CompletedProcess(args, 1, "", "") if args[0] == "merge-base" else real(*args)

    monkeypatch.setattr(test_for, "_git", no_fork)
    monkeypatch.delenv("TIANXIA_TEST_BASE", raising=False)
    assert test_for.main(["tianxia/models.py", "--list"]) == 2
    out = capsys.readouterr().out
    assert "沒有共同的祖先" in out.splitlines()[0] and "要跑（" not in out


def test_describe_says_what_the_core_tests_are():
    lines = test_for.describe(test_for.Pick(core=True))
    line = next(x for x in lines if x.startswith("核心測試"))
    assert "test_engine" in line and f"{len(test_for.core_tests())} 個檔" in line and "tests/core/ 不含 slow" not in line


def test_the_long_tests_listed_first_still_exist_and_rank_in_order():
    """tests/conftest.py 的 LONG_FIRST（T-03：已知很長的排在最前面）：每一筆的檔與測試函式都還在（改名了要跟著改，
    不然那一條又排回尾巴），排序照表上的順序，不在表上的排在後面。"""
    import re

    import conftest
    for entry in conftest.LONG_FIRST:
        path, _, name = entry.partition("::")
        assert (ROOT / path).is_file(), entry
        if name:
            assert re.search(rf"^def {re.escape(name)}\(", test_for._text(ROOT / path), re.M), entry
    first = conftest.LONG_FIRST[0]
    assert conftest.long_first_rank(first) == 0
    assert conftest.long_first_rank("tests/season/test_real_content.py::test_bot_plays_a_full_season[2]") > 0
    assert conftest.long_first_rank("tests/season/test_sim_scripts.py::test_anything_else") == len(conftest.LONG_FIRST) - 2
    assert conftest.long_first_rank("tests/arts/test_fusion.py::test_x") == len(conftest.LONG_FIRST)


def test_the_long_tests_are_spread_to_the_head_of_each_workers_first_chunk():
    """xdist load 一開始給每個 worker 連續的一段（條數 ÷ worker 數 ÷ 4）：長的照蛇形分到每一段的最前面，不全擠在第一段。"""
    from types import SimpleNamespace

    import conftest
    longs = [SimpleNamespace(nodeid=e) for e in conftest.LONG_FIRST[:6]]
    rest = [SimpleNamespace(nodeid=f"tests/arts/test_x.py::test_{i}") for i in range(114)]
    items = longs + rest
    assert conftest.spread_long_first(items, 1) == items
    out = conftest.spread_long_first(items, 3)
    assert sorted(id(i) for i in out) == sorted(id(i) for i in items)
    chunk = len(items) // 3 // 4  # 10
    heads = [out[k * chunk:(k + 1) * chunk] for k in range(3)]
    assert [[i for i in h if i in longs] for h in heads] == [[longs[0], longs[5]], [longs[1], longs[4]], [longs[2], longs[3]]]
    assert [i for i in out if i not in longs] == rest  # 其餘照原本的順序
