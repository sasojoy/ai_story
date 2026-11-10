"""scripts/test_for.py：改了哪些檔就挑哪幾條測試（開發規範手冊 4.3 的挑法）。"""
from __future__ import annotations

import importlib.util
import re
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


APP_JS_NO_DIFF = {"web/app.js": ([], "", "")}  # 第二輪第 95 批：釘住 app.js 的原挑法（分支上 app.js 有改，沒釘就翻成照名字挑）


@pytest.fixture
def leaderboard_reads_server_bots(monkeypatch):
    """第二輪第 88 批量過，舊模組（bot、bot_policy、bot_runner、server_bots）的 dependents 全是空的，「經 import 它的模組再挑」與「太多就不併」都沒有真例子了。
    這幾條守的是 pick 的做法、不是哪個模組，所以用真圖加一條假的邊。第二輪第 103 批 shopview 那個殼收掉，假的邊從 shopview 換成共用層的 leaderboard（9 個測試檔讀它、dependents 是空的，牽連最少）。
    量到的：pick(["tianxia/server_bots.py"]) 15 個檔、why「經 leaderboard（依賴它的 1 個模組）再挑到 7 個檔」、含只 import leaderboard 的 test_leaderboard、core 與 smoke 都假；
    IMPORT_CAP 壓到 5：8 個檔、core 與 smoke 都真、往上找到的 7 個一個都沒併（test_server 也讀 leaderboard，可是它是檔名第一個字挑到的，算直接）、why 寫「太多」。scripts/test_for.py 的 IMPORT_CAP 不動。"""
    real = test_for.module_graph()
    graph = {**real, "leaderboard": real["leaderboard"] | {"server_bots"}}
    monkeypatch.setattr(test_for, "module_graph", lambda: graph)
    test_for.dependents.cache_clear()
    yield
    test_for.dependents.cache_clear()


def test_a_module_picks_the_tests_that_import_it(leaderboard_reads_server_bots):
    # sense（全部拆包第 24 批）：原本的例子 glyph ← sensing 搬進了有所感包（tianxia/glyph.py 成了別名），換一對還是舊模組的 chapters ← weekcard
    # core_step（全部拆包第 36 批）：weekcard 收進核心本體（MODULES），核心不往上走——chapters 往上找的舊模組變成 0 個（量的：dependents("chapters")
    # 是空的、改 chapters 挑 1 個檔 test_chapters）。直接 import 的那一半照舊用 chapters；「經 import 它的模組再挑」那一行換成還是舊模組的
    # skillview ← shopview（改 skillview 挑 52 個檔，why 一行「經 shopview（依賴它的 1 個模組）再挑到 11 個檔」；兩個當時都不在共用層，收的那一批再換）
    # core_world2（全部拆包第 40 批）：chapters 收進共用規則層，改它照「自己檔名的＋煙霧＋邊界」挑，test_chapters 靠檔名挑到、不是靠 import。
    # 直接 import 的那一半換成還是舊模組的伺服器假人 server_bots ← test_bot_runner（量的：改 server_bots 挑 8 個檔、dependents 是空的〔import 它的
    # bot_policy、bot_runner 是 DRIVERS〕，test_bot_runner 檔名對不上、只靠直接 import 挑到；server_bots 不在總表任何一批，第 66 批以前不會動）
    picked = test_for.pick(["tianxia/server_bots.py"])
    assert "test_bot_runner.py" in {p.name for p in picked.files} and not picked.core
    assert "server_bots" in test_for.imported(next(p for p in picked.files if p.name == "test_bot_runner.py"))
    # 第二輪第 88 批：切開 skillview 之後沒有真例子了，「經 import 它的模組再挑」那一行用假的邊（leaderboard_reads_server_bots 的說明）
    assert any("leaderboard" in w for w in picked.why)  # 經 import 它的 leaderboard 再挑（T-02）


def test_a_module_also_picks_the_tests_of_the_modules_that_import_it(leaderboard_reads_server_bots):
    """10/31 測試自檢 T-02：might.py 沒有測試檔直接 import，以前挑 0 個；把 might.now 改成回 0，透過 ascend、create 用到它的
    test_ascend、test_create_ritual 會紅。現在照 tianxia/ 模組之間的 import 往上找。
    （shared：might 第 15 批進了共用規則層，改共用規則層照下面那一條挑；這一條換成還是舊模組的 ascend——經 cultivation 挑到
    只 import cultivation 的 test_cultivation。cultivation：ascend、cultivation 第 23 批搬進修練包、舊名成了別名，換成還是舊模組的輿圖畫法
    mapview——經 mapdata 挑到只 import mapdata 的 test_mapdata_layers。mapview：mapview、mapdata 第 49 批搬進輿圖包、舊名成了別名，
    換成還是舊模組的本週卡 step——經 weekcard 挑到只 import weekcard 的 test_weekcard。core_step：step、weekcard 第 36 批收進核心本體（MODULES），
    改 step 跑核心測試、不往上找，換成還是舊模組的事件抽選 events——經 narration 挑到只 import narration 的 test_narration
    〔量的：改 events 挑 22 個檔、dependents("events") 只有 narration；兩個當時都不在共用層，第 40 批照留、理由改寫成 events 只剩讀事件分級 tiers、narration 只剩讀 events，收的那一批再換〕。
    第二輪第 87 批 events、narration 收進共用規則層（共用層只挑自己檔名＋煙霧），換成還是舊模組的門下頁 skillview——經 shopview 挑到只 import shopview 的 test_bounty_tags
    〔量的：改 skillview 挑 54 個檔、core 與 smoke 都假、dependents("skillview") 只有 shopview；第 88 批切 skillview 時再換〕。
    第二輪第 88 批：舊模組沒有真例子了，換假的邊 shopview → server_bots；第 103 批殼收掉，假的邊換 leaderboard → server_bots、例子換 test_leaderboard（fixture 的說明）。）"""
    picked = test_for.pick(["tianxia/server_bots.py"])
    assert "test_leaderboard.py" in {p.name for p in picked.files}
    assert "server_bots" not in test_for.imported(next(p for p in picked.files if p.name == "test_leaderboard.py"))
    assert not picked.core and not picked.smoke
    ups = test_for.dependents("server_bots")
    assert {"leaderboard"} <= ups
    assert not ups & test_for.DRIVERS and not ups & test_for.CORE_MODULES  # engine、假人、核心不往上走


# shared（全部拆包第 15 批「共用規則層登記」）
@pytest.mark.parametrize("module, own", [
    ("might", {"test_might.py"}),
    ("tactics", {"test_tactics.py", "test_tactics_bouts.py"}),
    ("timetable", {"test_timetable.py"}),
    ("allied", set()),
])
def test_a_shared_rules_module_picks_its_own_tests_smoke_and_the_boundary_test(module, own):
    """總表第六節第 5 條：共用規則層（registry.SHARED）的模組改了，只挑自己檔名的測試＋煙霧＋邊界測試——不跑核心測試、不照「誰 import 它」
    挑也不往上找。以前 might 經 ascend、create 等 4 個模組往上挑到 46 個檔（T-02）、timetable 經 19 個模組往上挑到 109 個檔（連直接
    import 它的一共 133）、tactics 走「太多」那一條帶核心測試；
    allied 沒有自己檔名的測試，只剩煙霧＋邊界。"""
    assert module in test_for.SHARED_MODULES
    picked = test_for.pick([f"tianxia/{module}.py"])
    names = {p.name for p in picked.files}
    assert own <= names and "test_feature_boundaries.py" in names
    allowed = {"test_feature_boundaries.py"} | ({"test_content.py"} if module == "timetable" else set())  # timetable 有內容驗證 check_timetable（第 95 批）：這條沒給 hunks_of，帶不帶照它跟 base 的差；might、tactics、allied 沒有，不准多
    assert all(n in allowed or n.startswith(f"test_{module}") for n in names), names
    assert picked.smoke and not picked.core
    assert any("共用規則層" in w for w in picked.why)
    assert "test_ascend.py" not in _names(["tianxia/might.py"])


# 第二輪第 95 批：行號 模組說明 1；LIMIT 3；_limit 5～6；check_x 8～9；other 11～12；check_summons 14～15；validate_y 17～18
FAKE_SHARED_CHECKS = (
    '"""模組說明。"""\n'
    "from x import y\n"
    "LIMIT = 3\n"
    "\n"
    "def _limit(v):\n"
    "    return v < LIMIT\n"
    "\n"
    "def check_x(c, need):\n"
    "    need(_limit(c), 'x')\n"
    "\n"
    "def other(c):\n"
    "    return c\n"
    "\n"
    "def check_summons(state, content):\n"
    "    return []\n"
    "\n"
    "def validate_y(c, need, known):\n"
    "    return known\n"
)


@pytest.mark.parametrize("line, expected", [
    (9, True),  # 內容驗證本身
    (18, True),  # validate_*
    (6, True),  # 它用到的小函式
    (3, True),  # 小函式用到的常數
    (12, False),  # 別的函式
    (15, False),  # 名字像、參數沒有 need：不是內容驗證
    (1, False),  # 說明（這一批拿掉那一句就是這種）
    (2, False),  # import
])
def test_a_shared_rules_change_brings_test_content_only_when_it_reaches_a_content_check(line, expected):
    """第 96 批留的：共用層的 check_*、validate_* 由 content.validate 在函式內叫，改了以前挑不到 test_content.py。"""
    rel = "tianxia/relations.py"
    picked = test_for.pick([rel], base="HEAD", hunks_of=_added(rel, FAKE_SHARED_CHECKS, line))
    assert ("test_content.py" in {p.name for p in picked.files}) is expected
    assert any("test_content.py" in w for w in picked.why) is expected
    assert picked.smoke and not picked.core


def test_a_shared_rules_module_named_without_a_diff_counts_as_the_whole_file():
    rel = "tianxia/relations.py"
    plain = "def other(c):\n    return c\n"
    assert "test_content.py" in _names([rel], base="HEAD", hunks_of={rel: ([], FAKE_SHARED_CHECKS, FAKE_SHARED_CHECKS)})
    assert "test_content.py" not in _names([rel], base="HEAD", hunks_of={rel: ([], plain, plain)})


def test_the_content_checks_are_read_off_the_real_shared_modules():
    """真實的 15 個模組（第 95 批量的）認得到；舊名字像的不算。失效了是挑少，這條讓人知道。"""
    def checks(module):
        return test_for.content_checks((test_for.ROOT / "tianxia" / f"{module}.py").read_text(encoding="utf-8"))
    assert {"validate_forge_secrets", "validate_tier4_named", "validate_named_clash"} <= checks("forge_secrets")
    for module, name in (("relations", "check_relations"), ("timetable", "check_timetable"), ("figures", "check_figures")):
        assert name in checks(module) and module in test_for.SHARED_MODULES
    assert not checks("might") and not checks("ranks")  # ranks.check_summons 不是內容驗證


def test_the_shared_rules_layer_is_one_list_for_the_picker_and_the_boundary_test():
    """共用規則層只有一份：tianxia/core/registry.py 的 SHARED。test_for 照語法樹讀它（不 import：registry 會 import 每一包）、
    邊界測試 import 它；兩邊一樣，也都不跟核心本體重疊。"""
    from tianxia.core import MODULES, registry
    import test_feature_boundaries
    assert {"tactics", "timetable", "renown", "siege", "zh"} <= set(registry.SHARED)
    assert test_for.SHARED_MODULES == set(registry.SHARED) == set(test_feature_boundaries.SHARED)
    assert not test_for.SHARED_MODULES & MODULES


def test_the_shared_rules_layer_is_read_from_the_syntax_tree_and_a_broken_file_says_so(tmp_path, capsys):
    """照語法樹讀（SHARED: dict[str, str] = {...}，相鄰的字串照接）；讀不出來在 stderr 說一聲、當成沒有，那些模組照一般的舊模組挑。"""
    good = tmp_path / "good.py"
    good.write_text('from .features import Feature\nFEATURES = []\nSHARED: dict[str, str] = {\n    "a": "甲"\n         "乙",\n'
                    '    "b": "丙",  # 註解\n}\n', encoding="utf-8")
    assert test_for.shared_modules(good) == {"a", "b"}
    plain = tmp_path / "plain.py"
    plain.write_text('SHARED = {"c": "丁"}\n', encoding="utf-8")
    assert test_for.shared_modules(plain) == {"c"}
    broken = tmp_path / "broken.py"
    broken.write_text("SHARED = {\n", encoding="utf-8")
    assert test_for.shared_modules(broken) == frozenset()
    computed = tmp_path / "computed.py"
    computed.write_text('WHY = "x"\nSHARED = {"d": WHY}\n', encoding="utf-8")
    assert test_for.shared_modules(computed) == frozenset()
    missing = tmp_path / "none.py"
    missing.write_text("OTHER = 1\n", encoding="utf-8")
    assert test_for.shared_modules(missing) == frozenset()
    err = capsys.readouterr().err
    assert err.count("讀不出共用規則層的模組") == 3 and "沒有 SHARED" in err


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
    """彙整的模組（import 很多模組的那種）：依賴它算，可是不再往上走；DRIVERS 與核心連算都不算。"""
    many = frozenset(f"m{i}" for i in range(test_for.AGGREGATOR_FANOUT))
    graph = {"low": frozenset(), "mid": frozenset({"low"}), "agg": frozenset({"mid"}) | many,
             "top": frozenset({"agg"}), "bot": frozenset({"mid"}), "rules": frozenset({"low"})}
    monkeypatch.setattr(test_for, "module_graph", lambda: graph)
    test_for.dependents.cache_clear()
    try:
        assert test_for.dependents("low") == {"mid", "agg"}
    finally:
        test_for.dependents.cache_clear()


def test_a_low_module_with_too_many_dependents_runs_core_and_smoke_instead(monkeypatch, leaderboard_reads_server_bots):
    """tactics、zh 這種底層模組往上找會挑到兩、三百個檔：超過 IMPORT_CAP 只挑直接 import 的，加核心測試＋煙霧。
    （shared：tactics、zh 第 15 批進了共用規則層，照上面那一條挑；這一條換成還是舊模組的 seal_acts——經 conquest、figures 往上一百多個檔。
    map2：第 50 批 atlas 收進共用規則層之後量的，依賴它的模組 17 個、import 它們的測試檔 141 個，還是超過壓低的上限 100，例子不用換。）"""
    # 陣營第 35 批：defection 搬進包（舊名是沒有 import 的別名），seal_acts 往上找到的檔從超過上限掉到剛好 120 個（IMPORT_CAP 是「超過」才算），
    # 守的是「超過就只挑直接 import 的」這個做法，不是 120 這個數：把上限壓到 100，讓它不再貼著邊界
    # 玉璽第 51 批：seal_acts 收進共用規則層（照上面那一條挑），例子換成還是真正的舊模組 fusion（依賴它的模組 1 個、import 它的測試檔量到 33 個；
    # 其餘沒搬的檔 sensing、seal、smithing 是只有幾行的別名，不算）：沒有一個舊模組超過 100，所以上限壓到 30（直接 import 它的測試檔 27 個，在上限之內）；scripts/test_for.py 的 IMPORT_CAP 不動
    # 第二輪第 75 批：test_for 看穿 tests/kit 之後，fusion 直接的 42 個檔（server_kit 帶進來 15 個）、往上找到的 34 個：上限 30 仍是「太多」（core、smoke 照舊真），
    # 「直接的比上限少」不成立了。這一條守的是「太多就不併往上找到的」，所以換成那一群一個都沒併；scripts/test_for.py 的 IMPORT_CAP 不動
    # 第二輪第 87 批：fusion 收進共用規則層（照上面那一條挑），例子換成還是舊模組的 skillview；它往上找到的只有 11 個檔，30 不算太多，上限壓到 5
    # （量的：挑 43 個檔、core 與 smoke 都真、往上找到的 11 個一個都沒併、why 寫「太多」）；scripts/test_for.py 的 IMPORT_CAP 不動
    # 第二輪第 88 批：切開 skillview 之後舊模組沒有真例子了，換假的邊（第 103 批換成 leaderboard → server_bots，fixture 的說明），上限照舊壓到 5
    monkeypatch.setattr(test_for, "IMPORT_CAP", 5)
    picked = test_for.pick(["tianxia/server_bots.py"])
    assert picked.core and picked.smoke
    direct = {t for t in test_for.all_tests() if "server_bots" in test_for.reached(t) or t.stem == "test_server" or t.stem.startswith("test_server_")}  # 第一個字 server：test_server 也讀 leaderboard，是檔名挑到的
    via = {t for t in test_for.all_tests() if test_for.reached(t) & test_for.dependents("server_bots")} - direct
    assert via and not picked.files & via
    assert any("太多" in w for w in picked.why)


@pytest.mark.parametrize("module, kind, expected", [
    # 第二輪第 103 批：這兩個舊名的別名檔收掉了，路徑留假檔名：pick 不看檔在不在，registered_actions 照模組名找到包裡的登記
    ("wanted", "wanted", {"test_bounties.py", "test_sanren_web.py"}),
    ("mingtie_card", "mingtie", {"test_mingtie.py"}),
])
def test_a_module_engine_imports_to_register_picks_the_tests_that_name_its_action(module, kind, expected):
    """T-02：wanted.py、mingtie_card.py 只靠 engine 的 `as _x  # noqa: F401` 登記進 social.ACTIONS，測試經 peer_card／peer_act
    用到、沒有人 import：照登記的動作名挑寫到它的測試檔。讓 wanted.buttons 回 []，test_bounties 與 test_sanren_web 會紅。"""
    assert kind in test_for.registered_actions(module)
    assert expected <= _names([f"tianxia/{module}.py"])
    if module == "wanted":
        # 第 45 批：wanted 搬進懸賞榜包（登記改在包的 __init__.py，registered_actions 照樣認）。真正的檔在包裡：改它照包的規矩挑那一包的 tests/＋核心契約，
        # 挑得到搬進包的 test_renown_wanted；test_bounties、test_sanren_web 第 61 批也搬進包了
        assert {"test_renown_wanted.py", "test_bounties.py", "test_sanren_web.py"} <= _names(["tianxia/features/bounties/wanted.py"])
    assert test_for.registered_actions("might") == ()


def test_a_module_picks_the_tests_named_after_its_first_word():
    # 第二輪第 103 批：原本的例子 mingtie_card 是別名、檔收掉了，換還在的 server_bots（第一個字 server）
    assert "test_server.py" in _names(["tianxia/server_bots.py"])


def test_content_picks_its_tests_and_the_fast_part_of_real_content():
    """內容改了挑 test_content.py、寫到那個檔名的，加 test_real_content.py 不是 slow 的那些（147 條只有整季那 11 條是 slow；
    其他的含事件難度帶 DIFFICULTY_BANDS 的鎖、地點走得到，-n 4 約 25 秒）。整季那幾條照舊要 --slow（手冊 4.3 的本意）。"""
    picked = test_for.pick(["content/events/jizhou.json"])  # 留在 content/ 的事件池（explore_* 全部拆包第 63 批搬進探索包）
    assert {"test_content.py", "test_real_content.py"} <= {p.name for p in picked.files}
    (cmd,) = test_for.pytest_commands(picked, slow=False, extra=[])
    assert _marker(cmd) == "not slow"
    real = next(p for p in picked.files if p.name == "test_real_content.py")
    assert not test_for.whole_slow(real), "test_real_content.py 整個標 slow 的話，內容改了就一條難度帶都不驗"
    (both,) = test_for.pytest_commands(picked, slow=True, extra=[])
    assert _marker(both) == "slow or not slow" and "tests/season/test_real_content.py" in both


def test_a_pack_content_file_takes_the_content_route_and_the_pack_route():
    """全部拆包第 62 批：內容檔搬進包之後照舊走內容那一條（不補的話改 mall.json 挑不到 test_content.py），再加那一包的 tests/。"""
    names = _names(["tianxia/features/mall/content/mall.json"])
    assert {"test_content.py", "test_real_content.py", "test_mall_content.py", "test_contract_features.py"} <= names


def test_a_pack_test_content_file_takes_the_fixture_route_and_the_pack_route():
    """全部拆包第 63 批：包裡的測試內容同 tests/fixtures/（寫到那個檔名的）再加那一包的 tests/；不補的話落進測試檔那一支，什麼都挑不到。"""
    names = _names(["tianxia/features/travel/tests/content/road_sights.json"])
    assert {"test_content.py", "test_travel_smoke.py"} <= names
    assert "test_real_content.py" not in names  # 測試內容不走真實內容那一條


def test_a_new_undeclared_pack_file_picks_the_test_that_catches_it():
    """包裡新檔忘了寫進 Feature.content 時載入不報錯（_locate 只查宣告了的），事件靜靜少掉；
    新檔名不會寫在 test_content_packs.py 裡，所以內容改了要固定挑到它（第 B 波審查）。"""
    for path in ("tianxia/features/socialize/content/events/social_wan.json",  # 還沒有這個檔：情境就是剛新增
                 "tianxia/features/socialize/tests/content/social_wan.json",
                 "content/events/jizhou.json"):
        assert "test_content_packs.py" in _names([path]), path


def test_the_promotion_and_rank_action_content_picks_the_tests_that_pin_it():
    """第一季正式版丙一、丙二、戊一的測試檔用真實內容釘住晉升奇遇與第 3、4 階行動：改那幾個內容檔時要挑到它們（整合審查 M2）。"""
    promotions = {"test_promotions_high.py", "test_promotions_huang.py"}
    assert promotions <= _names(["tianxia/features/military/content/promotions.json"])
    assert promotions <= _names(["tianxia/features/military/content/events/promotion.json"])
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
    assert _names(["tianxia/features/craft/tests/test_fusion.py", "pyproject.toml"]) == {"test_fusion.py"}


def test_docs_pick_nothing_and_a_test_file_picks_itself():
    assert test_for.pick(["docs/superpowers/specs/x.md", "CLAUDE.md"]).empty
    assert _names(["tianxia/features/craft/tests/test_fusion.py"]) == {"test_fusion.py"}


# 全部拆包第 61 批拿掉過渡挑法（照方法名、hunk 裡的字、欄位名、路由前綴分功能群；手冊 4.3 終態）：
# test_a_group_also_takes_the_tests_that_mostly_call_it、test_a_verb_first_method_name_goes_to_the_feature_after_the_verb、
# test_every_shared_service_is_a_real_game_method 測的規則不在了，一起拿掉；下面這幾條照新的規則改寫。
def test_an_engine_method_picks_the_core_and_the_tests_that_write_its_name():
    """改 Game 上不是委派的方法 → 核心測試＋煙霧＋內文寫到那個方法名的測試檔（同 core_module_callers）：不照方法名的第一個字分群，
    也不因為 import 了 engine 就挑七成（第 61 批量到：寫到 _tavern_price 的只有 test_tavern.py）。"""
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 6))
    names = {p.name for p in picked.files}
    assert picked.core and picked.smoke
    assert names == _writes("_tavern_price") and "test_tavern.py" in names
    assert any("_tavern_price：不是委派" in w for w in picked.why)


def test_the_pickers_own_test_does_not_count_as_writing_a_name():
    """這個檔的內文是假的 engine、server、models（_tavern_price、_pill_day……寫在字串裡）：不算「寫到那個名字」（TEXT_BLIND）。
    它只在改 scripts/test_for.py（與它自己）時跑。"""
    me = ROOT / "tests" / "core" / "test_test_for.py"
    assert not any(me in files for files in test_for._index().values())
    tavern = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 6))
    assert me not in tavern.files and "test_tavern.py" in {p.name for p in tavern.files}
    assert me in test_for.pick(["scripts/test_for.py"]).files


def test_the_contract_and_boundary_tests_follow_the_core_not_the_names_they_write():
    """核心契約與邊界測試（全部拆包第 11 批）：內文寫滿各包的委派名，算「寫到」的話改哪個方法都挑到它們。它們不算寫到；
    改核心照核心測試挑到、改包照核心契約挑到。"""
    names = {"test_feature_boundaries.py", "test_contract_core.py", "test_contract_features.py"}
    assert not names & {p.name for files in test_for._index().values() for p in files}
    assert names <= {p.name for p in test_for.core_tests()} and names <= {p.name for p in test_for.contract_tests()}


DELEGATE_ENGINE = (
    "from .features.tavern import actions as tavern_actions\n"
    "from .features.battle import sieges as battle_sieges\n"
    "class Game:\n"
    "    def _tavern_price(self, base):\n"
    "        return tavern_actions.tavern_price(self, base)\n"
    "\n"
    "    def _settle_siege(self, battle):\n"
    "        \"\"\"說明字不算本體。\"\"\"\n"
    "        return battle_sieges.settle_siege(self, battle)\n"
    "\n"
    "    def _tavern_close(self):\n"
    "        x = 1\n"
    "        return tavern_actions.close(self, x)\n"
)


def test_an_engine_delegate_picks_its_package_and_the_contract():
    """改 engine 上一行委派（本體只有 return <包的模組>.<函式>(self, …)，第 11 批）：照那一包挑（那一包的 tests/＋核心契約），不照方法名的
    第一個字——_settle_siege 以前算 siege 群（第 6 批量到 105 條），現在是決戰包；本體不只一句的不算委派。"""
    assert test_for.engine_delegates(DELEGATE_ENGINE) == {"_tavern_price": "tavern", "_settle_siege": "battle"}
    siege = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", DELEGATE_ENGINE, 9))
    names = {p.name for p in siege.files}
    battle_pkg = {p.name for p in (test_for.FEATURES / "battle" / "tests").rglob("test_*.py")}
    assert battle_pkg <= names and {p.name for p in test_for.contract_tests()} <= names
    assert not siege.core
    assert any("battle 這一包的一行委派" in w for w in siege.why)
    tavern = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", DELEGATE_ENGINE, 5))
    assert {p.name for p in (test_for.FEATURES / "tavern" / "tests").rglob("test_*.py")} <= {p.name for p in tavern.files}
    plain = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", DELEGATE_ENGINE, 13))
    assert not any("一行委派" in w for w in plain.why)


GAME_API = 'TABLE = {\n    "_tavern_price": actions.tavern_price,\n    "check_in": actions.check_in,\n}\n'


def test_a_game_api_hunk_picks_its_package_and_the_tests_that_write_that_name():
    """第二輪第 72 批：一行委派搬進 features/<包>/game_api.py，改表上一格挑那一包的 tests/＋核心契約＋內文寫到那個名字的；另一格的不併。"""
    rel = "tianxia/features/tavern/game_api.py"
    picked = test_for.pick([rel], hunks_of=_added(rel, GAME_API, 2))
    names = {p.name for p in picked.files}
    assert {p.name for p in (test_for.FEATURES / "tavern" / "tests").rglob("test_*.py")} <= names
    assert {p.name for p in test_for.contract_tests()} <= names
    assert _writes("_tavern_price") <= names and any("寫到它們的" in w for w in picked.why)
    others = _writes("check_in") - _writes("_tavern_price") - {p.name for p in (test_for.FEATURES / "tavern" / "tests").rglob("test_*.py")} - {p.name for p in test_for.contract_tests()}
    assert others and not others & names


def _writes(name: str) -> set[str]:
    """內文寫到這個識別字的測試檔（不照內文歸群的 TEXT_BLIND 不算）。"""
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    return {t.name for t in test_for.all_tests() if t.name not in test_for.TEXT_BLIND and word.search(test_for._text(t))}


SCENE_ENGINE = (
    "from .features.battle import view as battle_view\n"
    "class Game:\n"
    "    def _battle_scene_text(self, battle, definition):\n"
    "        return battle_view.battle_scene_text(self, battle, definition)\n"
)


def test_an_engine_delegate_also_picks_the_tests_that_call_it_by_name():
    """一行委派也挑內文寫到那個方法名的測試檔（第 11 批審查）：包外直接叫它的混合檔（_battle_scene_text 有 test_jianghu_page_web、test_seal、
    test_conquest_siege 直接叫）不在那一包的 tests/ 裡，只照包挑會掉。挑到的就是那一包的 tests/＋核心契約＋寫到那個名字的，不多不少。
    第 61 批量到 7 個檔：原本例子裡 test_engine 叫它的那幾條搬進決戰包的 test_battle_facade，換成還在包外的 test_jianghu_page_web。"""
    scene = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", SCENE_ENGINE, 4))
    battle_pkg = {p.name for p in (test_for.FEATURES / "battle" / "tests").rglob("test_*.py")}
    callers = _writes("_battle_scene_text")
    assert {"test_jianghu_page_web.py", "test_seal.py", "test_conquest_siege.py", "test_battle_facade.py"} <= callers
    assert {p.name for p in scene.files} == battle_pkg | {p.name for p in test_for.contract_tests()} | callers
    assert any("寫到 _battle_scene_text 的" in w for w in scene.why) and not scene.core


MOVED_OLD = (
    "from .features.sortie import actions as sortie_actions\n"
    "class Game:\n"
    "    def _train_squad_ids(self, loc):\n"
    "        ids = [s for s in loc.squads]\n"
    "        return ids\n"
)
MOVED_NEW = (
    "from .features.sortie import actions as sortie_actions\n"
    "class Game:\n"
    "    def _train_squad_ids(self, loc):\n"
    "        return sortie_actions.train_squad_ids(self, loc)\n"
)


def test_a_method_that_becomes_a_delegate_is_still_picked_by_its_name():
    """往後的搬包批把胖方法換成一行委派（第 11 批審查）：那一筆照「舊檔裡是不是委派」認——舊檔是胖方法，不算委派：核心測試＋煙霧＋內文寫到
    那個方法名的（第 61 批以前照名字分群；量到寫到 _train_squad_ids 的是 test_explain、test_ranks），守那段舊本體的測試才挑得到；
    那一包的 tests/ 由同改包裡的檔挑到。舊檔沒有、新加的委派照新檔認。"""
    old_lines, new_lines = MOVED_OLD.splitlines(), MOVED_NEW.splitlines()
    moved = {"tianxia/engine.py": ([([(4, old_lines[3]), (5, old_lines[4])], [(4, new_lines[3])])], MOVED_OLD, MOVED_NEW)}
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=moved)
    assert not any("一行委派" in w for w in picked.why), picked.why
    assert picked.core and picked.smoke
    assert {p.name for p in picked.files} == _writes("_train_squad_ids") and "test_ranks.py" in {p.name for p in picked.files}
    fresh = {"tianxia/engine.py": ([([], [(3, new_lines[2]), (4, new_lines[3])])], MOVED_NEW.replace("_train_squad_ids", "_x"),
                                   MOVED_NEW)}
    assert any("sortie 這一包的一行委派" in w for w in test_for.pick(["tianxia/engine.py"], hunks_of=fresh).why)


def test_any_engine_hunk_picks_the_contract_and_boundary_tests():
    """改 engine 一律帶核心契約與邊界（第 11 批審查）：邊界測試的 GAME_* 名單只有它守（Game 新叫了一個包的名字就該紅）。
    只改到委派的另外加（不跑核心測試）；不是委派的方法跑核心測試，核心測試本來就含它們（CORE_GLOBS）。"""
    contract = {p.name for p in test_for.contract_tests()}
    delegate = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", DELEGATE_ENGINE, 5))
    assert contract <= {p.name for p in delegate.files}
    assert not delegate.core and not delegate.smoke
    assert any("核心契約與邊界測試" in w for w in delegate.why)
    plain = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 6))
    assert plain.core and plain.smoke and contract <= {p.name for p in test_for.core_tests()}


def test_a_method_too_many_tests_write_stays_core_and_smoke():
    """choose、sync 這種到處都寫得到的方法名（第 61 批量到：choose 237 個檔、sync 146 個，IMPORT_CAP 120）：不併寫到它的，只有核心測試＋煙霧。
    hunk 裡提到什麼不再算（第 61 批拿掉）。"""
    src = FAKE_ENGINE.replace("        pass\n", "        if kind == 'arena': return self._arena_enter(arg)\n", 1)
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", src, 3))
    assert picked.core and picked.smoke and not picked.files
    assert len(test_for._index()["choose"]) > test_for.IMPORT_CAP
    assert any("太多不併" in w for w in picked.why)


def test_a_shared_helper_without_a_feature_is_core():
    """_side 這種共用的小方法（服務）：不是委派 → 核心測試＋煙霧。"""
    picked = test_for.pick(["tianxia/engine.py"], hunks_of=_added("tianxia/engine.py", FAKE_ENGINE, 12))
    assert picked.core and picked.smoke


def test_the_shared_services_of_the_handbook_are_core_even_when_named_like_a_feature():
    """手冊 3.3 列為 ctx 的共用服務（_side、_save_season、_pill_day……）被叫幾十上百次：改到就是核心（核心測試＋煙霧），名字裡的字
    （season、pill）不分群；寫到方法名的照併（第 61 批量到：_save_season 56 個檔、_pill_day 12 個、_side 3 個，都在 IMPORT_CAP 以內）。"""
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
        assert {p.name for p in picked.files} == _writes(name), name


def test_a_removed_line_is_found_in_the_old_file():
    """整個方法拿掉：拿掉的行照舊檔的行號找方法。"""
    old = FAKE_ENGINE
    new = FAKE_ENGINE.replace("    def _tavern_price(self, base):\n        return base\n\n", "")
    hunk = {"tianxia/engine.py": ([([(5, "    def _tavern_price(self, base):"), (6, "        return base")], [])], old, new)}
    assert "test_tavern.py" in _names(["tianxia/engine.py"], hunks_of=hunk)


def test_models_and_state_are_core_plus_their_own_tests():
    """models.py、state.py 改了 → 核心測試＋煙霧＋自己檔名的（第 61 批拿掉欄位名帶功能前綴那一段，手冊 4.3 終態：mall_tokens 不再加商城那一群；
    量到沒有 test_state… 這個檔）。"""
    picked = test_for.pick(["tianxia/state.py"], hunks_of=_added("tianxia/state.py", FAKE_MODELS, 3))
    assert picked.core and picked.smoke and not picked.files
    bare = test_for.pick(["tianxia/models.py"], hunks_of=_added("tianxia/models.py", FAKE_MODELS, 2))
    assert bare.core and bare.smoke and {p.name for p in bare.files} == {"test_models.py"}


def test_server_py_picks_the_core_its_test_and_every_shell_test():
    """server.py 只剩殼（路由都在包裡）：不管 hunk 落在哪 → 核心測試＋煙霧＋test_server.py＋全部 test_*_shell.py（第 61 批從 test_server
    拆進各包的，守住「改 server.py 一定跑它的測試」）。路由前綴不再分群（第 61 批拿掉）。"""
    for line in (3, 6):
        picked = test_for.pick(["server.py"], hunks_of=_added("server.py", FAKE_SERVER, line))
        names = {p.name for p in picked.files}
        assert picked.core and picked.smoke
        assert {"test_server.py", "test_battle_shell.py", "test_craft_shell.py"} <= names
        assert all(n == "test_server.py" or n.endswith("_shell.py") for n in names), names


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


# shared（第 15 批審查修正）：test_for 的 lru_cache（_all_tests、_candidates、smoke_ids、feature_web……）照當時的 FEATURES 記，
# monkeypatch 還原了 FEATURES、快取還是暫存資料夾那一份：同一個行程後面跑的 test_the_smoke_set_covers_every_block 就少了 mall
# （-p no:xdist 照這個先後跑兩條，base a242343b 也紅；-n 4 分到同一個行程時才踩到）。換掉 FEATURES 的測試前後都清。
def _clear_test_for_caches() -> None:
    for obj in vars(test_for).values():
        clear = getattr(obj, "cache_clear", None)
        if callable(clear):
            clear()


@pytest.fixture
def fresh_test_for_caches():
    _clear_test_for_caches()
    yield
    _clear_test_for_caches()


def test_a_feature_package_picks_its_own_tests_and_the_contract(tmp_path, monkeypatch, fresh_test_for_caches):
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
    guards = {"test_action_tables.py", "test_outlock.py"} if changed.endswith("/routes.py") else set()  # 第 106 批：包的路由帶這兩個
    assert own and own | contract | guards == {p.name for p in picked.files} and not picked.core and not picked.smoke


def test_slow_is_opt_in_and_three_files_run_on_four_workers():
    three = test_for.Pick(files={ROOT / "tianxia/features/craft/tests/test_fusion.py", ROOT / "tests/arts/test_naming.py",
                                 ROOT / "tests/arts/test_library.py"})
    (cmd,) = test_for.pytest_commands(three, slow=False, extra=[])
    assert _marker(cmd) == "not slow"
    if importlib.util.find_spec("xdist") is not None:
        assert cmd[cmd.index("-n") + 1] == "4"
    (both,) = test_for.pytest_commands(three, slow=True, extra=[])
    assert _marker(both) == "slow or not slow"
    (mine,) = test_for.pytest_commands(three, slow=False, extra=["-n", "2"])
    assert mine.count("-n") == 1 and mine[mine.index("-n") + 1] == "2"
    (one,) = test_for.pytest_commands(test_for.Pick(files={ROOT / "tianxia/features/craft/tests/test_fusion.py"}), slow=False, extra=[])
    assert "-n" not in one


def _marker(cmd):
    """python -m pytest 後面那一個 -m 的式子。"""
    return cmd[cmd.index("-m", cmd.index("pytest")) + 1]


def test_a_changed_test_file_runs_with_its_slow_tests():
    """手冊 4.3「只跑改到的那幾個測試檔」：改了一個整個檔標 slow 的測試檔，就是要跑它，連 slow 一起
    （以前 -m "not slow" 把它整個濾掉，39 deselected、結束碼 5）。"""
    own = test_for.pick(["tests/core/test_event_tiers.py", "tests/core/test_gentry_ledgers.py"])
    (cmd,) = test_for.pytest_commands(own, slow=False, extra=[])
    assert _marker(cmd) == "slow or not slow"
    assert {"tests/core/test_event_tiers.py", "tests/core/test_gentry_ledgers.py"} <= set(cmd)


def test_changed_slow_test_files_run_apart_from_the_rest_of_the_pick():
    """改到的測試檔連 slow 一起跑，其他挑到的照舊不含 slow：分兩次，改到的那幾個不在第一次裡重複跑。"""
    mixed = test_for.pick(["tests/core/test_event_tiers.py"])
    mixed.files.add(ROOT / "tianxia/features/craft/tests/test_fusion.py")
    mixed.core = True
    first, second = test_for.pytest_commands(mixed, slow=False, extra=[])
    assert _marker(first) == "not slow" and "tianxia/features/craft/tests/test_fusion.py" in first
    assert "tests/core/test_event_tiers.py" not in first and "tests/core/test_engine.py" in first
    assert _marker(second) == "slow or not slow" and second[-1] == "tests/core/test_event_tiers.py"
    plain = test_for.pick(["tianxia/features/craft/tests/test_fusion.py"])  # 沒有 slow 的測試檔：一次就好
    assert len(test_for.pytest_commands(plain, slow=False, extra=[])) == 1
    # 這個檔的字串裡寫了 "@pytest.mark.slow"（_slow_smoke 的例子），不是標記：也是一次就好
    assert not test_for.has_slow(ROOT / "tests/core/test_test_for.py")
    assert test_for.has_slow(ROOT / "tests/core/test_event_tiers.py")


def test_a_pick_that_is_all_slow_says_so_and_does_not_fail(capsys):
    """挑到的全在整個檔標 slow 的檔裡：先列出來；一條都沒跑（pytest 結束碼 5）時說要 --slow，結束碼 0。"""
    picked = test_for.Pick(files={ROOT / "tests/core/test_event_tiers.py"})
    assert any("--slow" in line and "test_event_tiers.py" in line for line in test_for.describe(picked))
    assert test_for.finish([5], picked, slow=False) == 0
    assert "--slow" in capsys.readouterr().out
    assert test_for.finish([0, 5], picked, slow=False) == 0
    assert test_for.finish([1, 0], picked, slow=False) == 1
    plain = test_for.Pick(files={ROOT / "tianxia/features/craft/tests/test_fusion.py"})  # 不是 slow 濾掉的（例如 -- -k 濾光了）照 pytest 的
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
    assert 100 <= len(ids) <= 180 and len(set(ids)) == len(ids)  # 每一包至少一條，新包一包加一條（門派包 2026-11-09 從 170 放到 180）
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
    # 寫到 web/mall.js 檔名的別包測試照檔名跟；絕招例句（#166）第 94 批切到 web/looks.js，test_looks_scenes.py 不再跟來
    assert {p.name for p in js.files} == mall_tests | contract | {"test_server_bots.py"}  # 第 106 批：web/ 一律帶 FB-673 的掃描
    assert not js.core and not js.smoke
    assert "test_server.py" not in {p.name for p in js.files}
    assert not {p.name for p in js.files} & (_names(["web/app.js"], hunks_of=APP_JS_NO_DIFF) - mall_tests - contract - {"test_server_bots.py"})
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
    """「核心測試」（PM 10/31）＝手冊 3.1 核心模組自己檔名的測試（test_<模組>…，在哪個資料夾都算）＋
    tests/core/test_engine*.py＋tests/core/ 的核心契約、邊界、錢包服務測試；不是整個 tests/core/（那裡是雜燴：
    test_factions 這些屬於功能的）；test_social 第 61 批搬進玩家互動包，一樣不算。"""
    names = {p.name for p in test_for.core_tests()}
    assert CORE_OWN | {"test_engine.py"} <= names
    assert not names & {"test_social.py", "test_factions.py", "test_nightly.py", "test_test_for.py", "test_errands.py"}
    allowed = {f"test_{m}" for m in test_for.CORE_MODULES - test_for.NOT_CORE_TESTS} | {
        "test_engine", "test_contract", "test_feature_boundaries", "test_wallet", "test_shell_stays_thin"}  # 第 106 批：殼的名單進 CORE_GLOBS
    assert all(any(p.stem == a or p.stem.startswith(a + "_") or (a in ("test_engine", "test_contract")
                                                                 and p.stem.startswith(a)) for a in allowed)
               for p in test_for.core_tests()), sorted(names)
    goal = test_for.targets(test_for.Pick(core=True))
    assert {"tests/core/test_engine.py", "tests/arts/test_naming.py", "tests/battle/test_team.py"} <= set(goal)
    assert "tianxia/features/peers/tests/test_social.py" not in goal
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


# core_world（全部拆包第 25 批「世界層掛鉤」）
def test_the_core_tests_stay_what_the_pm_defined_when_the_world_joins_the_core():
    """world 收進核心本體（第 25 批）同 journal 只改「改了它挑什麼」：它自己的 test_world、test_world_map 不收進核心測試
    （NOT_CORE_TESTS；要不要收交 PM），world_state 的 test_world_state 照舊在。改 world.py 是核心那一條：核心測試＋煙霧＋自己檔名的
    （test_world…，連 test_world_state），不再照「誰 import 它」往上找。"""
    names = {p.name for p in test_for.core_tests()}
    assert "world" in test_for.CORE_MODULES and "world" in test_for.NOT_CORE_TESTS
    assert "test_world_state.py" in names and not names & {"test_world.py", "test_world_map.py"}
    picked = test_for.pick(["tianxia/world.py"])
    assert picked.core and picked.smoke
    assert {p.name for p in picked.files} == {"test_world.py", "test_world_map.py", "test_world_state.py"}


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
    first = _first_line(capsys, ["tianxia/features/craft/tests/test_fusion.py", "--list"])
    assert "origin/develop" in first and "預設" in first
    assert "origin/develop" in _first_line(capsys, ["CLAUDE.md", "--list"])  # 挑不到東西的也先寫 base
    monkeypatch.setenv("TIANXIA_TEST_BASE", "origin/main")
    assert test_for.default_base() == "origin/main"
    first = _first_line(capsys, ["tianxia/features/craft/tests/test_fusion.py", "--list"])
    assert "origin/main" in first and "TIANXIA_TEST_BASE" in first
    first = _first_line(capsys, ["tianxia/features/craft/tests/test_fusion.py", "--list", "--base", "origin/develop"])
    assert "origin/develop" in first and "--base" in first


def test_a_base_that_was_never_fetched_stops_before_picking(monkeypatch, capsys):
    """這份 clone 的 git fetch origin 不更新 feature/*、dev/*：沒明確 fetch 的 base 找不到分岔點，挑法就不準——不給檔名
    只剩還沒提交的改動，給了檔名整個檔當新檔（10/31 審查：models.py 挑到 347 個檔、結束碼 0）。第一行說找不到、
    怎麼 fetch，然後停下、結束碼 2，一個檔都不挑、不跑。"""
    monkeypatch.delenv("TIANXIA_TEST_BASE", raising=False)
    fetch = "git fetch origin +refs/heads/feature/no-such-branch-1031:refs/remotes/origin/feature/no-such-branch-1031"
    for argv in (["--list"], ["tianxia/models.py", "--list"], ["tianxia/models.py", "--count"], ["tianxia/features/craft/tests/test_fusion.py"]):
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
    assert conftest.long_first_rank("tianxia/features/craft/tests/test_fusion.py::test_x") == len(conftest.LONG_FIRST)


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


# ── core-events（全部拆包第 16 批修正，PM 2026-11-03）：改核心裡掛鉤、清單以外的模組（tianxia/core/event_check.py……）──
# 以前一律只挑核心測試＋煙霧：事件檢定從 Game 搬進核心之後，搬之前照方法名挑得到的隨口應對、端出事件的回歸挑不到了（審查 M1、M4、M8、M9）。
# 照第 11 批修正輪的做法再並上寫到改到的函式名或 Game 委派名的測試檔。

def _core_hunk(module: str, name: str) -> dict:
    """假裝改了 tianxia/core/<module>.py 裡最外層 name（函式、類別、常數）的最後一行；位置照這一份真的原始碼找。"""
    rel = f"tianxia/core/{module}.py"
    src = (ROOT / rel).read_text(encoding="utf-8")
    end = next(e for n, _, e, _ in test_for._core_spans(src) if n == name)
    return _added(rel, src, end)


def _core_pick(name: str):
    return test_for.pick(["tianxia/core/event_check.py"], hunks_of=_core_hunk("event_check", name))


def test_the_game_delegates_to_the_core_are_read_from_the_engine():
    """Game 上委派給核心本體的一行委派（`return event_check.<函式>(self, …)`）照 engine.py 的語法樹認，跟邊界測試的
    CORE_EVENT_DELEGATES 是同一批方法（那一份另外守張數與「只有一行」）。"""
    import test_feature_boundaries
    found = test_for.core_delegates((ROOT / "tianxia" / "engine.py").read_text(encoding="utf-8"))
    assert {"_present": ("event_check", "present"), "_choose": ("event_check", "resolve_choice"),
            "answer_event": ("event_check", "answer_event"), "_tale_clue": ("event_check", "tale_clue")}.items() <= found.items()
    assert {m for m, (mod, _) in found.items() if mod == "event_check"} == set(test_feature_boundaries.CORE_EVENT_DELEGATES)
    assert not set(found) & set(test_for.engine_delegates((ROOT / "tianxia" / "engine.py").read_text(encoding="utf-8")))


@pytest.mark.parametrize("name, delegate, expected", [
    ("tale_clue", "_tale_clue", {"test_secret_recipes.py", "test_forge_secrets.py"}),  # 審查 M9：以前 test_for 挑的 1,599 條 0 紅
    ("present", "_present", {"test_stances_fix6.py", "test_seats.py", "test_event_rotation.py"}),  # 人物心意那一則（審查第一條）
    ("event_battle", "_event_battle", {"test_terrain_arts.py"}),
    ("resolve_choice", "_choose", {"test_drill_push.py"}),
    ("add_gamble_narration", "add_gamble_narration", {"test_free_text_and_marks.py"}),  # 審查 M4
])
def test_a_core_function_also_picks_the_tests_that_name_its_game_delegate(name, delegate, expected):
    picked = _core_pick(name)
    names = {p.name for p in picked.files}
    assert picked.core and picked.smoke
    assert expected <= names and _writes(delegate) <= names
    assert not names & {"test_tavern.py", "test_mall.py"}
    assert any(delegate in w for w in picked.why), picked.why


def test_a_core_function_name_alone_counts_only_with_the_module_name():
    """函式名照字面算太寬（present、apply 是一般的字：test_admin_triggers、test_fusion 寫到它們、跟事件檢定無關）：
    函式名要跟模組名（event_check）寫在同一個檔裡才算；委派名、類別、常數照識別字算。present 模組裡沒有人直接叫
    （都經 ctx._present），挑到的就是寫到 _present 的＋同時寫到 event_check 與 present 的，不多不少。"""
    names = {p.name for p in _core_pick("present").files}
    assert names == _writes("_present") | (_writes("event_check") & _writes("present"))
    assert "test_admin_triggers.py" in _writes("present") and "test_admin_triggers.py" not in names
    assert "test_fusion.py" not in {p.name for p in _core_pick("apply").files}


def test_a_core_helper_without_a_delegate_picks_through_the_functions_that_call_it():
    """answer_branch、deed_credit 只有模組裡的 answer_event 在叫（沒留委派）：一路往上找模組裡直接叫它的函式，照那幾個的
    名字與委派名挑。審查 M8：answer_branch 拿掉 cost_problem，test_outcomes_answer 紅、test_for 以前挑的 0 紅。"""
    for name in ("answer_branch", "deed_credit"):
        picked = _core_pick(name)
        names = {p.name for p in picked.files}
        assert {"test_outcomes_answer.py", "test_free_text_and_marks.py", "test_outcomes_server.py"} <= names, name
        assert any("answer_event" in w for w in picked.why), (name, picked.why)
    # 模組裡經 ctx 叫的（apply 經 ctx._present 串下一則）不算「叫它的」：照的是函式之間直接的呼叫
    assert "test_seal_mandate.py" not in {p.name for p in _core_pick("present").files}


def test_a_core_constant_picks_the_tests_that_name_it_and_the_functions_that_use_it():
    """模組層的常數與類別（EVIL_ANNAL、FreeTextRequest）照識別字挑（engine 照名字 import 回來，測試寫 from tianxia.engine import …），
    再加模組裡用到它的函式（往上找）的委派名。"""
    names = {p.name for p in _core_pick("EVIL_ANNAL").files}
    assert _writes("EVIL_ANNAL") <= names and _writes("answer_event") <= names
    request = {p.name for p in _core_pick("FreeTextRequest").files}
    assert _writes("FreeTextRequest") <= request and _writes("free_text_request") <= request


def test_a_core_module_named_without_a_change_counts_the_whole_file():
    """指名了、可是跟 base 沒有差（`test_for.py tianxia/core/event_check.py --base HEAD`）：照整個檔算，每一個函式、類別、常數都算。"""
    rel = "tianxia/core/event_check.py"
    src = (ROOT / rel).read_text(encoding="utf-8")
    picked = test_for.pick([rel], hunks_of={rel: ([], src, src)})
    names = {p.name for p in picked.files}
    assert picked.core and picked.smoke
    for name in ("tale_clue", "present", "answer_branch", "EVIL_ANNAL"):
        assert {p.name for p in _core_pick(name).files} <= names, name
    assert any("整個檔" in w for w in picked.why)


# bout（全部拆包第 12 批審查修正）：單挑底層 duel_base、擂台的名次 arena_ranks 被單挑包的 duel_rules、arena_rules 照抄出去
# （re-export 同一批函式物件），測試照舊經舊名寫（`from tianxia import duel`、`duel.blow_taken`、`arena.title_for`、
# `from tianxia import duel as duel_rules`）。以前「模組名與函式名寫在同一個檔」只認 duel_base、arena_ranks 這兩個字，一個都並不上
# （審查 C1、C2、C5：改了核心那一份，test_for 挑的全綠、包與奪璽單挑的測試紅）。

def _core_pick_in(module: str, name: str):
    return test_for.pick([f"tianxia/core/{module}.py"], hunks_of=_core_hunk(module, name))


def test_the_core_names_a_package_reexports_are_read_with_the_package_module_and_its_old_name():
    """照語法樹讀出：名字 → 照抄它的模組名（duel_rules、arena_rules）與測試給那一份取的本地名（duel、arena；第二輪第 103 批之前是舊名的別名）。只看 from … import 名字
    （整個模組 import 進來的 `from tianxia.core import duel_base as duel_rules` 不算照抄：那一份寫得到 duel_base 這個字）。"""
    duel_words = test_for.core_reexports("duel_base")
    assert {"duel_rules", "duel"} <= duel_words["push_of"] and {"duel_rules", "duel"} <= duel_words["blow_taken"]
    assert {"arena_rules", "arena"} <= test_for.core_reexports("arena_ranks")["title_for"]
    assert "shop_view" not in set().union(*duel_words.values()) and "seal_duel" not in set().union(*duel_words.values())
    assert "present" not in test_for.core_reexports("event_check")  # 沒有人照抄的函式：照舊只認模組名與委派名
    local = test_for.local_names_in_tests()
    assert {"duel"} <= local["tianxia.features.bout.duel_rules"] and {"arena"} <= local["tianxia.features.bout.arena_rules"]
    assert {"sortie_duel"} <= local["tianxia.features.sortie.duel_rules"]  # 同名的模組照全名分開


@pytest.mark.parametrize("module, name, expected", [
    ("duel_base", "push_of", {"test_seal_duel.py"}),  # 審查 C1（參謀減半拿掉）：寫 duel_rules.push_of
    ("duel_base", "blow_taken", {"test_duel.py"}),  # 審查 C2（不算防具）：寫 duel.blow_taken
    ("arena_ranks", "title_for", {"test_arena.py"}),  # 審查 C5（<= 改成 <）：寫 arena.title_for
])
def test_a_core_function_also_picks_the_tests_that_name_it_through_a_package_reexport(module, name, expected):
    picked = _core_pick_in(module, name)
    names = {p.name for p in picked.files}
    assert picked.core and picked.smoke
    assert expected <= names, picked.why
    assert any("照抄" in w for w in picked.why), picked.why


def test_a_reexported_name_counts_only_when_written_after_the_module_word():
    """經照抄的模組寫的要寫成 `<模組名>.<名字>`（或從那個模組 import 那個名字）才算：duel、arena 是到處都有的字（p.duel、config.arena），
    只看兩個字寫在同一個檔裡會把一大半的測試都挑進來。"""
    assert test_for.names_through(["duel", "duel_rules"], "push_of", "from tianxia import duel as duel_rules\nduel_rules.push_of(1)\n")
    assert test_for.names_through(["duel"], "blow_taken", "from tianxia.duel import blow_taken, counter\n")
    assert not test_for.names_through(["duel"], "counter", "p.duel = None\ncounter = 3\n")
    assert not test_for.names_through(["arena"], "title_for", "c.config.arena.enabled = True\nleaderboard.title_for\n")


STAGE_PACKAGES = ["bout", "battle", "checkin", "companions", "feast", "figure_acts", "guide", "looks", "outlets", "sense", "socialize", "story", "territory_acts", "zhuan"]  # 有 <包>_stage.py 的包（銀兩出口是第 43 批加的；引導是第 22 批合進 develop 的，第 12 批合併時補上；人物情誼是第 19 批、有所感是第 24 批、交友求見是第 21 批、大勢人物是第 31 批合進 split/trunk 時補上；列傳是第 29 批加的；地盤是第 46 批加的）
STAGE_PACKAGES += ["seal"]  # seal（全部拆包第 27 批）：玉璽包的 seal_stage.py（擺「懷璽」：有登記、有抄本）；接在這裡、不改上一行（並行的拆包線各寫各的一行）
STAGE_PACKAGES += ["legacy", "hire"]  # 合回 develop（2026-11-06）：傳承、招募的 <包>_stage.py
STAGE_PACKAGES += ["persona"]  # 人物性子（develop cf927227，合回第 4 段）：persona_stage.py
STAGE_PACKAGES += ["heroines"]  # 女子與隱線（PR #179）：heroines_stage.py
STAGE_PACKAGES += ["identity"]  # 帳號綁定（scripts/new_feature.py 生的 identity_stage.py）
STAGE_PACKAGES += ["support"]  # 客服（scripts/new_feature.py 生的 support_stage.py）
STAGE_PACKAGES += ["news"]  # 見聞（scripts/new_feature.py 生的 news_stage.py）
STAGE_PACKAGES += ["titles"]  # 稱號與官職（scripts/new_feature.py 生的 titles_stage.py）
STAGE_PACKAGES += ["terms"]  # 條款（scripts/new_feature.py 生的 terms_stage.py）
STAGE_PACKAGES += ["jieyi"]  # 結義（scripts/new_feature.py 生的 jieyi_stage.py）
STAGE_PACKAGES += ["mail"]  # 帖友書信（scripts/new_feature.py 生的 mail_stage.py）
STAGE_PACKAGES += ["zongmen"]  # 門派（scripts/new_feature.py 生的 zongmen_stage.py）
STAGE_PACKAGES += ["guard"]  # 親衛隊長（scripts/new_feature.py 生的 guard_stage.py）


def test_the_stage_packages_are_every_package_with_a_stage_file():
    """下面兩條照這張表參數化：新的一包放了 <包>_stage.py 就要加進來（不然那一包的擺局面檔沒有人驗挑不挑得到）。"""
    found = sorted(p.parent.parent.name for p in (ROOT / "tianxia" / "features").glob("*/tests/*_stage.py")
                   if p.name == f"{p.parent.parent.name}_stage.py")
    assert found == sorted(STAGE_PACKAGES)


@pytest.mark.parametrize("package", STAGE_PACKAGES)
def test_a_package_stage_file_picks_the_contract_test_that_loads_it(package):
    """tianxia/features/<包>/tests/<包>_stage.py 只有契約測試載入（test_contract_features 的 _stages 用 importlib 照路徑讀），沒有測試檔
    import 它：改了挑核心契約（同改包的檔），不是「import 它的測試檔」那一條（第 12 批審查：以前四包的 *_stage.py 一條都不挑）。"""
    rel = f"tianxia/features/{package}/tests/{package}_stage.py"
    assert (ROOT / rel).is_file(), rel
    picked = test_for.pick([rel])
    assert {p.name for p in picked.files} >= {"test_contract_features.py", "test_feature_boundaries.py"}
    assert any("契約" in w for w in picked.why), picked.why


@pytest.mark.parametrize("package", STAGE_PACKAGES)
def test_a_package_stage_file_also_picks_its_own_package_tests(package):
    """擺局面檔算成那一包（第 22 批 PM 認定第 1 條、第 12 批合併時補）：挑那一包的 tests/ 加核心契約，同改包裡的任一檔——擺錯局面時
    契約測試會紅，那一包自己的測試也要跟著跑（修正輪只挑了核心契約）。"""
    rel = f"tianxia/features/{package}/tests/{package}_stage.py"
    own = set((ROOT / "tianxia" / "features" / package / "tests").rglob("test_*.py"))
    assert own, package
    picked = test_for.pick([rel])
    assert own <= set(picked.files), sorted(p.name for p in own - set(picked.files))
    assert picked.files == test_for.pick([f"tianxia/features/{package}/__init__.py"]).files


def test_a_core_pick_that_names_too_many_files_falls_back_to_core_and_smoke(monkeypatch):
    """寫到那幾個名字的檔超過 IMPORT_CAP 個（同 tianxia/<模組>.py 往上找的那一條）：不一個一個挑，只剩核心測試＋煙霧。"""
    monkeypatch.setattr(test_for, "IMPORT_CAP", 1)
    picked = _core_pick("answer_branch")
    assert picked.core and picked.smoke and not picked.files
    assert any("太多" in w for w in picked.why)


@pytest.mark.parametrize("module", sorted(test_for.CORE_LISTS))
def test_the_core_hooks_and_lists_still_pick_only_the_core_tests_and_smoke(module):
    """掛鉤（features.py）、服務與共用的字（services.py；清單在 services_list.md，下一條）與清單（registry.py 的 FEATURES、__init__.py 的 MODULES）改了照舊只跑核心測試＋煙霧：
    名字（options、choose、FEATURES）到處都寫得到，照名字挑等於整套。"""
    assert (ROOT / "tianxia" / "core" / f"{module}.py").is_file(), module
    rel = f"tianxia/core/{module}.py"
    src = (ROOT / rel).read_text(encoding="utf-8")
    picked = test_for.pick([rel], hunks_of=_added(rel, src, *range(1, len(src.splitlines()) + 1)))
    assert picked.core and picked.smoke and not picked.files


# core_api（第二輪第 74 批）
def test_the_service_list_file_picks_only_the_boundary_test():
    """服務清單搬成 tianxia/core/services_list.md：只有邊界測試讀它，改它不走核心測試＋煙霧（條件放在 tianxia/core/ 那一條前面）。"""
    picked = test_for.pick(["tianxia/core/services_list.md"])
    assert {p.name for p in picked.files} == {"test_feature_boundaries.py"}
    assert not picked.core and not picked.smoke


@pytest.mark.parametrize("path", ["scripts/sb/harness.py", "scripts/sb/base.py", "scripts/sb/tracks/relay.py", "scripts/sb/tracks/world.py", "scripts/sb/tracks/map.py"])
def test_the_scenarios_pick_only_the_boundary_test_and_point_at_the_selftest(path):
    """scripts/sb/**：第 70 批量到照檔名字根挑 198 個檔（軌名撞 world、map 這種模組名），它們都不讀這些檔。"""
    picked = test_for.pick([path])
    assert {p.name for p in picked.files} == {"test_feature_boundaries.py"}
    assert not picked.core and not picked.smoke
    assert any("same_behavior selftest" in why for why in picked.why)


@pytest.mark.parametrize("path", ["scripts/webqa/gate.py", "scripts/webqa/driver.mjs", "scripts/webqa/flows/extra.mjs", "scripts/webqa/must_reach.txt"])
def test_the_web_compare_tool_picks_its_own_test(path):
    picked = test_for.pick([path])
    assert {p.name for p in picked.files} == {"test_webqa.py"}
    assert not picked.core and not picked.smoke


@pytest.mark.parametrize("path", ["scripts/support_bridge.py", "scripts/support_cli.py", "scripts/support_session_init.py", "scripts/support_knowledge.py"])
def test_the_support_host_scripts_pick_their_own_tests(path):
    """客服的主機端四支（T 波，PM）：測試在 support 包裡，照檔名字根挑不到。"""
    picked = test_for.pick([path])
    assert {p.name for p in picked.files} == {"test_support_bridge.py", "test_support_cli.py", "test_support_session.py", "test_feature_boundaries.py"}
    assert not picked.core and not picked.smoke


def test_a_package_tuning_file_picks_only_that_package():
    """tianxia/core/tuning/<包>.py 是那一包的 Config 子模型，不走核心測試＋煙霧（第 74 批留的）。"""
    picked = test_for.pick(["tianxia/core/tuning/tavern.py"])
    assert picked.files == set((test_for.FEATURES / "tavern" / "tests").rglob("test_*.py"))
    assert picked.files and not picked.core and not picked.smoke
    for not_a_package in ("tianxia/core/tuning/__init__.py", "tianxia/core/tuning/no_such_package.py"):
        assert test_for.pick([not_a_package]).core, not_a_package


def test_a_package_checks_file_also_picks_the_content_test():
    """包的 checks.py（內容驗證）的測試寫在 test_content.py（第 95 批問的，PM 定）：改它併上那一檔；包裡別的檔不跟。"""
    picked = test_for.pick(["tianxia/features/bounties/checks.py"])
    assert test_for.CONTENT_TEST in {p.name for p in picked.files}
    assert any("checks.py" in why and test_for.CONTENT_TEST in why for why in picked.why)
    assert test_for.CONTENT_TEST not in {p.name for p in test_for.pick(["tianxia/features/bounties/actions.py"]).files}


# core_step（全部拆包第 36 批「你這一步」）
def test_the_core_tests_stay_what_the_pm_defined_when_step_and_weekcard_join_the_core():
    """step、weekcard 收進核心本體（第 36 批，計畫 1.5 甲案）同 world 只改「改了它挑什麼」：它們自己的 test_step（9 條）、test_weekcard（8 條）
    不收進核心測試（NOT_CORE_TESTS），改這兩個是核心那一條：核心測試＋煙霧＋自己檔名的，不再照「誰 import 它」往上找
    （以前改 step 經 weekcard 挑 7 個檔 54 條）。"""
    names = {p.name for p in test_for.core_tests()}
    assert {"step", "weekcard"} <= test_for.CORE_MODULES and {"step", "weekcard"} <= test_for.NOT_CORE_TESTS
    assert not names & {"test_step.py", "test_weekcard.py"}
    for module, own in (("step", {"test_step.py"}), ("weekcard", {"test_weekcard.py"})):
        picked = test_for.pick([f"tianxia/{module}.py"])
        assert picked.core and picked.smoke
        assert {p.name for p in picked.files} == own, module


# 第二輪第 75 批：契約變快（逐包的核心契約只跑 [<包>]）、看穿 tests/kit、核心服務檔的新規則、第 72 批蓋掉 named 的修正
def _package_names() -> list[str]:
    return sorted(p.name for p in test_for.FEATURES.iterdir() if (p / "__init__.py").is_file())


def _deselected(picked, tmp=None) -> list[str]:
    return [a for cmd in test_for.pytest_commands(picked, False, [], tmp) for a in cmd if a.startswith("--deselect=")]


@pytest.mark.parametrize("changed, hunks_of, package", [
    ("tianxia/features/tavern/rules.py", None, "tavern"),
    ("web/tavern.js", None, "tavern"),
    ("tianxia/features/bout/tests/bout_stage.py", None, "bout"),
    ("tianxia/features/tavern/game_api.py", _added("tianxia/features/tavern/game_api.py", GAME_API, 2), "tavern"),
    ("tianxia/engine.py", _added("tianxia/engine.py", DELEGATE_ENGINE, 5), "tavern"),
])
def test_a_package_change_runs_only_its_own_cells_of_the_core_contract(changed, hunks_of, package):
    """改一包：test_contract_features 逐包參數化的那幾條只留 [<包>]，別的包那幾格 --deselect（6 條 ×〔包數 − 1〕）；核心契約的檔照舊挑到。"""
    picked = test_for.pick([changed], base="HEAD", hunks_of=hunks_of)
    assert picked.contract_only == {package} and not picked.core
    assert {p.name for p in test_for.contract_tests()} <= {p.name for p in picked.files}
    args = _deselected(picked)
    assert any(a.endswith("[hire]") for a in args) and not any(a.endswith(f"[{package}]") for a in args)
    assert len(args) == len(test_for.per_package_contract_tests(test_for.CORE_TESTS / test_for.PER_PACKAGE_CONTRACT)) * (len(_package_names()) - 1)
    assert all(a.startswith("--deselect=tests/core/test_contract_features.py::") for a in args)
    assert any("核心契約逐包那幾條只跑" in line and f"[{package}]" in line for line in test_for.describe(picked))


@pytest.mark.parametrize("files, hunks_of", [
    (["tianxia/features/tavern/rules.py", "tianxia/core/features.py"], None),  # 動到核心：全跑
    (["tianxia/features/tavern/rules.py", "tests/core/test_contract_features.py"], None),  # 改到契約檔本身：全跑
    (["tianxia/engine.py"], _added("tianxia/engine.py", DELEGATE_ENGINE, 13)),  # engine 上不是委派的方法：不知道算哪一包，全跑
])
def test_the_core_contract_runs_every_package_when_the_change_is_not_just_a_package(files, hunks_of):
    picked = test_for.pick(files, base="HEAD", hunks_of=hunks_of)
    assert {"test_contract_features.py"} <= {p.name for p in picked.files} or picked.core
    assert _deselected(picked) == []
    assert not any("核心契約逐包那幾條只跑" in line for line in test_for.describe(picked))


def test_the_core_contract_is_not_narrowed_for_everything_or_a_goal_without_it():
    assert test_for._contract_deselect(test_for.Pick(everything=True, contract_only={"tavern"}), ["tests/core/test_contract_features.py"]) == []
    assert test_for._contract_deselect(test_for.Pick(contract_only={"tavern"}), ["tests/core/test_contract_core.py"]) == []
    assert test_for._contract_deselect(test_for.Pick(), ["tests/core/test_contract_features.py"]) == []


def test_the_per_package_contract_tests_are_read_from_the_syntax_tree():
    """照語法樹讀 @pytest.mark.parametrize("feature", …)：新加一條逐包的，不用改 test_for。"""
    assert set(test_for.per_package_contract_tests(test_for.CORE_TESTS / test_for.PER_PACKAGE_CONTRACT)) == {
        "test_declared_seams_look_up_the_package_functions_when_called",
        "test_choose_takes_only_its_own_ids", "test_a_closed_package_gives_nothing",
        "test_a_closed_package_gives_nothing_on_the_prep_card", "test_a_new_season_keeps_only_what_the_package_carries"}


def test_a_long_deselect_list_goes_into_the_args_file_with_the_goal(tmp_path):
    """一包 6 格 × 別的包，約兩萬字：跟 goal 一起算長度，太長寫進 @檔（Windows 一行有上限）。"""
    picked = test_for.pick(["tianxia/features/tavern/rules.py"], base="HEAD")
    [cmd] = test_for.pytest_commands(picked, False, [], tmp_path)
    assert not any(a.startswith("--deselect=") for a in cmd)
    listed = next(a for a in cmd if a.startswith("@"))[1:]
    text = Path(listed).read_text(encoding="utf-8")
    assert "tests/core/test_contract_features.py\n" in text and "::test_choose_takes_only_its_own_ids[hire]" in text
    assert "::test_choose_takes_only_its_own_ids[tavern]" not in text


def test_a_change_to_a_kit_or_a_module_reaches_the_tests_that_use_it_through_a_kit():
    """test_battle_page_web → jianghu_kit → webharness；*_shell → server_kit → server_push（C 波審查量到的三種）。"""
    harness = _names(["tests/kit/webharness.py"])
    assert {"test_battle_page_web.py", "test_guide_page_web.py"} <= harness
    assert "test_travel_shell.py" in _names(["server_push.py"])


def test_a_js_file_reaches_the_tests_through_the_kit_text_but_not_through_the_kit_that_lists_every_js():
    """web/app.js 掉過 cultivation、guide、socialize 的 *_page_web（jianghu_kit 寫到它的檔名）；webharness 的 APP_FILES 寫滿每一支 js、
    server_kit 只在說明字寫到 app.js：這兩個不算（KIT_TEXT_BLIND），不然改哪一支都多 90 幾個檔、app.js 多 15 個 *_shell。"""
    app = _names(["web/app.js"], hunks_of=APP_JS_NO_DIFF)
    assert {"test_cultivation_page_web.py", "test_guide_page_web.py", "test_socialize_page_web.py"} <= app
    assert "test_travel_shell.py" not in app
    assert "test_battle_page_web.py" not in _names(["web/hire.js"], base="HEAD")


def test_seeing_through_a_kit_goes_down_one_layer_only():
    """test_sortie_duel → duel_kit → conquest_kit 算得到；conquest_kit 才 import 的 territory 算不到（第二輪第 103 批：原本的例子 conquest_day 是別名、檔收掉了，kit 改寫包的全名，換 territory）。"""
    test = test_for.FEATURES / "sortie" / "tests" / "test_sortie_duel.py"
    assert "conquest_kit" in test_for.reached(test) and "conquest_kit" not in test_for.imported(test)
    assert "territory" in test_for.imported(test_for.TESTS / "kit" / "conquest_kit.py")
    assert "territory" not in test_for.reached(test)


# 假的核心服務檔（hunks_of 給假原文、不讀真檔，驗規則本身；pushing 的真檔第 80 批開了，用真檔的那一條在 test_the_push_and_pill_service_files_pick_their_base_not_core_and_smoke）：行號 _shaped 1～2、push_trend 5～6、LIMIT 9
FAKE_PUSHING = "def _shaped(a):\n    return a\n\n\ndef push_trend(self, x):\n    return _shaped(x)\n\n\nLIMIT = 3\n"
PUSHING = "tianxia/core/pushing.py"


def test_the_core_service_files_are_the_six_the_plan_named():
    assert set(test_for.CORE_SERVICES) == {"combat", "pushing", "pills", "status_view", "page_view", "scene_view"}


@pytest.mark.parametrize("line", [6, 2, 9], ids=["the_function", "a_helper_only_it_calls", "a_constant"])
def test_a_core_service_hunk_picks_its_group_not_core_and_smoke(line):
    """服務檔裝的是單一功能本體：hunk 落在函式、類別、常數上 → 名字的功能群＋這個檔的底＋邊界測試，不跑核心測試、煙霧、契約兩檔。"""
    picked = test_for.pick([PUSHING], hunks_of=_added(PUSHING, FAKE_PUSHING, line))
    names = {p.name for p in picked.files}
    assert {"test_push.py", "test_feature_boundaries.py"} <= names
    assert not picked.core and not picked.smoke
    assert not names & {"test_contract_core.py", "test_contract_features.py"}
    assert len(names) <= test_for.IMPORT_CAP


def test_a_core_service_helper_counts_the_function_that_calls_it():
    """_shaped 自己的名字認不出功能（沒有測試檔叫 shaped）：連模組裡用到它的 push_trend，跟改 push_trend 同一群。"""
    assert test_for.service_word("_shaped") == ""
    helper = test_for.pick([PUSHING], hunks_of=_added(PUSHING, FAKE_PUSHING, 2))
    caller = test_for.pick([PUSHING], hunks_of=_added(PUSHING, FAKE_PUSHING, 6))
    assert helper.files == caller.files


def test_a_core_service_hunk_names_its_group_by_the_first_word_a_test_file_has():
    assert test_for.service_word("push_trend") == "push"
    assert test_for.service_word("take_stamina_pill") == "stamina"  # take 在 SERVICE_STOP
    assert test_for.service_word("pills_left_today") == "pill"  # 複數試單數
    assert test_for.word_tests("push") and all("push" in t.stem.split("_")[1:] for t in test_for.word_tests("push"))


def test_a_core_service_leaves_the_tests_that_only_write_the_name_to_the_gate_and_says_so():
    """test_opportunities 442 條只拿 push_trend 當準備動作：不併，why 寫幾個檔，要當場驗直接給檔名。"""
    picked = test_for.pick([PUSHING], hunks_of=_added(PUSHING, FAKE_PUSHING, 6))
    assert "test_opportunities.py" in _writes("push_trend") and "test_opportunities.py" not in {p.name for p in picked.files}
    assert any("不挑" in w and "push_trend" in w for w in picked.why)


@pytest.mark.parametrize("hunks_of", [
    _added(PUSHING, "import x\n" + FAKE_PUSHING, 1),  # 函式以外（import、說明、模組層）
    {PUSHING: ([], FAKE_PUSHING, FAKE_PUSHING)},  # 指名了卻沒有差
], ids=["outside_any_function", "no_difference"])
def test_a_core_service_change_outside_a_function_falls_back_to_core_and_smoke(hunks_of):
    picked = test_for.pick([PUSHING], hunks_of=hunks_of)
    assert picked.core and picked.smoke


def test_a_core_service_pick_with_too_many_files_falls_back_to_core_and_smoke(monkeypatch):
    monkeypatch.setattr(test_for, "IMPORT_CAP", 2)
    picked = test_for.pick([PUSHING], hunks_of=_added(PUSHING, FAKE_PUSHING, 6))
    assert picked.core and picked.smoke and any("太多" in w for w in picked.why)


def test_the_combat_service_file_picks_its_base_not_core_and_smoke():
    """第 79 批開的真檔（FAKE_PUSHING 那幾條照留、驗規則本身，第 80 批另補用真檔的）：take_toll 的名字認不出功能（take 在 SERVICE_STOP、沒有測試檔叫 toll），靠這個檔的底，
    不跑核心測試與煙霧。battle_scores 經 ctx._battle_power 叫它（test_rise 換掉 Game._battle_power，要打得到）：_core_refs 只看 ast.Name，不往上算；
    battle_scores 也在 battle 那一群，而 battle 就在底裡，所以沒漏。"""
    assert test_for.service_word("take_toll") == ""
    picked = test_for.pick(["tianxia/core/combat.py"], hunks_of=_core_hunk("combat", "take_toll"))
    names = {p.name for p in picked.files}
    assert {"test_battle_facade.py", "test_tactics.py", "test_engine.py", "test_feature_boundaries.py"} <= names
    assert not picked.core and not picked.smoke
    assert len(names) <= test_for.IMPORT_CAP
    src = (ROOT / "tianxia" / "core" / "combat.py").read_text(encoding="utf-8")
    assert "battle_scores" not in test_for._callers_up("battle_power", test_for._core_refs(src, src)[2])
    assert test_for.service_word("battle_scores") == "battle" and test_for.word_tests("battle") <= picked.files


# core_imports（第二輪第 98 批）
def test_the_combat_service_file_names_the_squad_encounter_it_took_over():
    """第 98 批把 _squad_encounter 收進真檔：底不動（service_word 是 encounter，本來就在底裡），hunk 落在 squad_encounter 時 why 寫到它，不跑核心測試與煙霧。
    寫到 _squad_encounter、可是檔名不在底裡的 7 個檔（test_fronts、test_characters……）只拿它當準備動作，留給閘門。"""
    assert test_for.service_word("squad_encounter") == "encounter"
    picked = test_for.pick(["tianxia/core/combat.py"], hunks_of=_core_hunk("combat", "squad_encounter"))
    assert not picked.core and not picked.smoke
    assert {"test_encounter.py", "test_tactics.py", "test_engine.py", "test_feature_boundaries.py"} <= {p.name for p in picked.files}
    assert any("squad_encounter" in w for w in picked.why)


def test_the_push_and_pill_service_files_pick_their_base_not_core_and_smoke():
    """第 80 批開的真檔：goals、deed_points 的名字認不出功能（service_word 空字串），靠這個檔的底，不跑核心測試與煙霧；refill_stamina 的底是 pill、stamina。
    push_trend、push_room 經 ctx.daily_push_cap 叫它（test_seal_acts 換掉 Game.daily_push_cap，要打得到）：_core_refs 只看 ast.Name，不往上算；
    daily_push_cap 自己認得 push，而 push 就在底裡，所以沒漏。"""
    assert test_for.service_word("goals") == "" and test_for.service_word("deed_points") == ""
    cases = [
        ("pushing", "goals", {"test_fronts.py", "test_gentry_allied.py", "test_push.py"}),
        ("pushing", "deed_points", {"test_gentry_ledgers.py", "test_outcomes_answer.py", "test_outcomes_classify.py", "test_push.py"}),
        ("pills", "refill_stamina", {"test_stamina_refill.py", "test_stamina_pill.py", "test_pill_per_day.py"}),
    ]
    for module, name, want in cases:
        picked = test_for.pick([f"tianxia/core/{module}.py"], hunks_of=_core_hunk(module, name))
        names = {p.name for p in picked.files}
        assert want | {"test_feature_boundaries.py"} <= names, name
        assert not picked.core and not picked.smoke, name
        assert len(names) <= test_for.IMPORT_CAP, name
    src = (ROOT / "tianxia" / "core" / "pushing.py").read_text(encoding="utf-8")
    callers = test_for._callers_up("daily_push_cap", test_for._core_refs(src, src)[2])
    assert not callers & {"push_trend", "push_room"}
    goals = test_for.pick(["tianxia/core/pushing.py"], hunks_of=_core_hunk("pushing", "goals"))
    assert test_for.service_word("daily_push_cap") == "push" and test_for.word_tests("push") <= goals.files


def _real_service(module: str, function: str):
    """第 81 批開的真檔：改 module 這個函式（真檔的原文、hunk 落在那個 def 那一行）挑到什麼。"""
    rel = f"tianxia/core/{module}.py"
    src = (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")
    line = next(i for i, text in enumerate(src.splitlines(), 1) if text.startswith(f"def {function}("))
    return test_for.pick([rel], hunks_of=_added(rel, src, line))


@pytest.mark.parametrize("module, function, wants", [
    ("status_view", "status_data", {"test_renown_status.py", "test_jianghu_page_web.py", "test_explain2.py", "test_fronts.py"}),
    ("page_view", "shop_view", {"test_jianghu_page_web.py", "test_shop.py", "test_shop2.py", "test_journal.py", "test_rumor_layers.py", "test_front_lines.py"}),
    ("scene_view", "scene_art", {"test_scene_art.py", "test_place_state.py", "test_marks_wired.py", "test_engine.py"}),  # 第 91 批量的：scene 1、place 1、marks 5、engine 5，併起來 12 個
])
def test_the_real_view_files_pick_their_ground_not_core_and_smoke(module, function, wants):
    """真的 core/status_view.py、core/page_view.py 照 CORE_SERVICES 的底挑（第 81 批量的：status、jianghu 各只有 1 個檔，真的在測 status_data 的 test_explain2 24 處、
    test_fronts 10 處要另外寫進底；page_view 的 test_shop2 24 處、test_journal 45 處也是）。"""
    picked = _real_service(module, function)
    names = {p.name for p in picked.files}
    assert wants | {"test_feature_boundaries.py"} <= names
    assert not picked.core and not picked.smoke
    assert len(names) <= test_for.IMPORT_CAP


def test_the_scene_view_goes_by_its_ground_even_when_the_name_says_nothing():
    """真的 core/scene_view.py（第 91 批開檔）：location_text、_own_ended 的名字認不出功能（service_word 空字串），改它們一樣挑到底的四群；
    第 91 批量的：底裡 scene 1 個檔、place 1、marks 5、engine 5。"""
    assert test_for.service_word("location_text") == test_for.service_word("_own_ended") == ""
    for function in ("location_text", "_own_scene_text", "_own_ended", "_art_place"):
        names = {p.name for p in _real_service("scene_view", function).files}
        assert {"test_scene_art.py", "test_place_state.py", "test_marks_wired.py", "test_engine.py", "test_feature_boundaries.py"} <= names, function


def test_a_real_view_helper_without_a_word_goes_with_the_functions_that_call_it():
    """_core_refs 只看 ast.Name：模組裡直接叫才算得到呼叫端（服務檔經 ctx._x 互叫的不往上算，所以這兩份模組裡互叫都直接叫）。
    _chip 自己的名字認不出功能（沒有測試檔叫 chip），連用到它的 battle_extra_html，比它自己的底多挑到 battle 那一群。"""
    assert test_for.service_word("_chip") == ""
    chip = _real_service("page_view", "_chip").files
    assert _real_service("page_view", "battle_extra_html").files == chip
    assert len(chip) > len(_real_service("page_view", "_timeline").files)


def test_the_view_delegates_are_read_from_the_engine():
    """Game 上委派給 status_view、page_view、scene_view 的（test_for.core_delegates 照語法樹認）跟邊界測試的 CORE_VIEW_DELEGATES 是同一批；模組裡的函式名與方法名相同。"""
    import test_feature_boundaries
    found = test_for.core_delegates((ROOT / "tianxia" / "engine.py").read_text(encoding="utf-8"))
    views = {m: f for m, (mod, f) in found.items() if mod in ("status_view", "page_view", "scene_view")}
    assert set(views) == set(test_feature_boundaries.CORE_VIEW_DELEGATES)
    assert all(m == f for m, f in views.items())


def test_a_game_api_change_listed_first_keeps_the_content_and_web_routes():
    """第 72 批留的：pick 裡 named（檔名 → 路徑）被 game_api 那一條蓋掉，game_api.py 排在內容檔、web/ 前面時 test_content、test_real_content、
    test_content_packs、test_server 都掉（排後面才挑得到）。"""
    rel = "tianxia/features/tavern/game_api.py"
    hunks_of = _added(rel, GAME_API, 2)
    names = {p.name for p in test_for.pick([rel, "content/events.json"], base="HEAD", hunks_of=hunks_of).files}
    assert {"test_content.py", "test_real_content.py", "test_content_packs.py"} <= names
    # web/icon.svg：test_server.py 沒寫到這個檔名，只有 web/ 那一條的 SERVER_TEST 挑得到（web/app.js 它有寫到，壞了也挑得到，驗不出來）
    assert "test_server.py" in {p.name for p in test_for.pick([rel, "web/icon.svg"], base="HEAD", hunks_of=hunks_of).files}


# 第二輪第 95 批：殼的 js 照 hunk 挑。行號在下面每一條測試寫到的地方都是這一份的。
FAKE_SHELL_JS = (
    "/* 說明 */\n"  # 1
    "(function () {\n"
    '  "use strict";\n'
    "  const LIMIT = 3; // 行尾有註解\n"  # 4
    "  const CHOSEN = cond\n"  # 5
    "    ? 1\n"
    "    : 2;\n"  # 7
    "  function topHtml(a) {\n"  # 8
    "    return a;\n"
    "  }\n"  # 10
    "\n"  # 11
    "  // 落在外面的註解\n"  # 12
    "  setInterval(tick, 1000);\n"  # 13
    "\n"
    '  document.addEventListener("click", async (ev) => {\n'  # 15
    "    const el = ev.target;\n"  # 16
    "    try {\n"
    "      switch (el.act) {\n"
    '        case "gate": renderGate(); break;\n'  # 19
    '        case "report-list":\n'  # 20
    "          closeReport();\n"  # 21
    "          break;\n"  # 22
    '        case "one": case "two": both(); break;\n'  # 23
    "      }\n"
    "    } catch (e) {}\n"
    "  });\n"  # 26
    "\n"
    "  async function wkTap() {\n"  # 28
    "    return 1;\n"
    "  }\n"  # 30
    "})();\n"
)
SHELL_LOAD = {"test_shell_web.py", "test_server_bots.py", "test_shell_stays_thin.py"}  # 第 106 批：web/ 一律帶殼的名單（test_shell_stays_thin）


def _shell_pick(monkeypatch, line, writers, js="web/app.js", src=FAKE_SHELL_JS):
    """假裝改了 src 的第 line 行；writers 是 {名字: [測試檔名…]}，換掉「寫到名字」，不靠真實測試的字。"""
    by_name = {t.name: t for t in test_for.all_tests()}
    table = {name: frozenset(by_name[n] for n in files) for name, files in writers.items()}
    monkeypatch.setattr(test_for, "_name_writers", lambda name: table.get(name, frozenset()))
    return test_for.pick([js], base="HEAD", hunks_of=_added(js, src, line))


@pytest.mark.parametrize("js", ["web/app.js", "web/main.js"])
def test_a_shell_js_hunk_in_a_function_picks_who_writes_its_name(monkeypatch, js):
    """寫到它的檔＋載入檢查與 FB-673（固定兩個）＋煙霧，不再帶 test_server.py（它的煙霧那幾條 -m smoke 會跑）。"""
    picked = _shell_pick(monkeypatch, 9, {"topHtml": ["test_might.py"]}, js=js)
    assert {p.name for p in picked.files} == {"test_might.py"} | SHELL_LOAD
    assert picked.smoke and not picked.core and not picked.runs_js
    assert any("topHtml" in w and js in w for w in picked.why)


def test_a_removed_line_is_found_in_the_old_file_so_a_deleted_function_still_picks_its_writers(monkeypatch):
    monkeypatch.setattr(test_for, "_name_writers", lambda name: frozenset(
        t for t in test_for.all_tests() if name == "topHtml" and t.name == "test_might.py"))
    hunks_of = {"web/app.js": ([([(9, "    return a;")], [])], FAKE_SHELL_JS, "(function () {\n})();\n")}
    assert "test_might.py" in _names(["web/app.js"], base="HEAD", hunks_of=hunks_of)


@pytest.mark.parametrize("line, label", [(19, "gate"), (21, "report-list"), (22, "report-list")])
def test_a_shell_js_hunk_in_a_click_case_goes_by_the_case_label(monkeypatch, line, label):
    picked = _shell_pick(monkeypatch, line, {label: ["test_might.py"], "report": ["test_tactics.py"]})
    assert {p.name for p in picked.files} == {"test_might.py"} | SHELL_LOAD
    assert any(f"case:{label}" in w for w in picked.why)


def test_every_label_on_a_case_line_counts(monkeypatch):
    picked = _shell_pick(monkeypatch, 23, {"one": ["test_might.py"], "two": ["test_tactics.py"]})
    assert {p.name for p in picked.files} == {"test_might.py", "test_tactics.py"} | SHELL_LOAD


def test_a_name_with_a_hyphen_or_a_prefix_is_not_the_shorter_name(monkeypatch):
    """report-list 不算寫到 report；_name_writers 有 lru_cache，假的測試檔走 __wrapped__ 不留進快取。"""
    fake = {Path("a.py"): 'click("report-list")', Path("b.py"): 'act: "report"', Path("c.py"): "my_report $report xreport",
            Path("test_test_for.py"): 'act: "report"'}
    monkeypatch.setattr(test_for, "all_tests", lambda: list(fake))
    monkeypatch.setattr(test_for, "web_text", fake.__getitem__)
    writers = test_for._name_writers.__wrapped__
    assert writers("report") == {Path("b.py")}  # 假原始碼的 test_test_for 不算（TEXT_BLIND）
    assert writers("report-list") == {Path("a.py")}


def test_a_name_too_many_tests_write_falls_back_to_the_whole_file_picks(monkeypatch):
    many = [t.name for t in test_for.all_tests()[:test_for.SHELL_NAME_CAP + 1]]
    whole = test_for.pick(["web/app.js"], base="HEAD", hunks_of=APP_JS_NO_DIFF)
    picked = _shell_pick(monkeypatch, 9, {"topHtml": many})
    assert picked.files == whole.files and not picked.smoke and "test_server.py" in {p.name for p in picked.files}
    assert any("topHtml" in w and f"{len(many)} 個檔" in w for w in picked.why)
    at_cap = _shell_pick(monkeypatch, 9, {"topHtml": many[:-1]})  # 剛好 20 個不退回
    assert at_cap.smoke and {p.name for p in at_cap.files} == set(many[:-1]) | SHELL_LOAD


def test_a_case_with_a_label_too_many_tests_write_falls_back_too(monkeypatch):
    many = [t.name for t in test_for.all_tests()[:test_for.SHELL_NAME_CAP + 1]]
    whole = test_for.pick(["web/app.js"], base="HEAD", hunks_of=APP_JS_NO_DIFF)
    assert _shell_pick(monkeypatch, 23, {"one": ["test_might.py"], "two": many}).files == whole.files


@pytest.mark.parametrize("line", [13, 16, 15, 3])  # 頂層的句子、handler 前段、addEventListener 那一行、"use strict"
def test_a_hunk_outside_every_name_falls_back_to_the_whole_file_picks(monkeypatch, line):
    whole = test_for.pick(["web/app.js"], base="HEAD", hunks_of=APP_JS_NO_DIFF)
    picked = _shell_pick(monkeypatch, line, {"topHtml": ["test_might.py"]})
    assert picked.files == whole.files and not picked.smoke
    assert any(f"第 {line} 行" in w and "原挑法" in w for w in picked.why)


@pytest.mark.parametrize("line", [11, 12])
def test_a_comment_or_blank_line_outside_every_name_only_runs_the_fixed_ones(monkeypatch, line):
    picked = _shell_pick(monkeypatch, line, {})
    assert {p.name for p in picked.files} == SHELL_LOAD and picked.smoke
    assert any("註解" in w for w in picked.why)


def test_a_name_nobody_writes_only_runs_the_fixed_ones_and_says_the_nightly_covers_it(monkeypatch):
    """總表認的坑：沒人寫到的函式執行期才炸，這裡全綠，靠 03:30 的整套。"""
    picked = _shell_pick(monkeypatch, 29, {})
    assert {p.name for p in picked.files} == SHELL_LOAD and picked.smoke
    assert any("wkTap" in w and "03:30" in w for w in picked.why)


def test_a_shell_js_named_without_a_diff_keeps_the_whole_file_picks():
    picked = test_for.pick(["web/app.js"], base="HEAD", hunks_of=APP_JS_NO_DIFF)
    names = {p.name for p in picked.files}
    assert "test_server.py" in names and len(names) > test_for.SHELL_NAME_CAP and not picked.smoke
    assert any("原挑法" in w for w in picked.why)


def test_the_other_shell_scripts_stay_on_the_whole_file_picks(monkeypatch):
    """第一條只管 app.js、main.js：shell.js 有 hunk 也照舊，WEB_SCRIPTS 不動。"""
    assert test_for.SHELL_HUNK_JS == {"web/app.js", "web/main.js"}
    plain = test_for.pick(["web/shell.js"], base="HEAD", hunks_of={"web/shell.js": ([], "", "")})
    picked = _shell_pick(monkeypatch, 9, {"topHtml": ["test_might.py"]}, js="web/shell.js")
    assert picked.files == plain.files and not picked.smoke and "test_server.py" in {p.name for p in picked.files}


def test_a_wholly_slow_web_test_that_writes_the_name_runs_with_its_slow_tests(monkeypatch):
    """test_errands_web 整檔 slow、用假瀏覽器跑頁面：不連 slow 一起跑，挑到了也一條不跑（同包的 js，10/31 審查）。
    部分 slow 的（test_cultivation_page_web）、整檔 slow 可是不跑 js 的（test_event_tiers）不放。"""
    files = ["test_errands_web.py", "test_cultivation_page_web.py", "test_event_tiers.py"]
    picked = _shell_pick(monkeypatch, 9, {"topHtml": files})
    assert set(files) <= {p.name for p in picked.files}
    assert {p.name for p in picked.runs_js} == {"test_errands_web.py"}
    assert {p.name for p in picked.with_slow} == {"test_errands_web.py"}


def test_shell_spans_do_not_let_one_name_swallow_the_next():
    """行尾有註解的 const、沒有收尾行的三元運算：只找收尾那一行的話會一路吞到下一個收尾，歸屬往挑少的方向錯（第 95 批第一版量到吞掉約一百個名字）。"""
    spans = {name: (start, end) for name, start, end in test_for.shell_spans(FAKE_SHELL_JS)}
    assert spans == {"LIMIT": (4, 4), "CHOSEN": (5, 7), "topHtml": (8, 10), "case:gate": (19, 19),
                     "case:report-list": (20, 22), "case:one|two": (23, 23), "wkTap": (28, 30)}
    assert test_for.shell_spans(FAKE_SHELL_JS.replace("\n", "\r\n")) == test_for.shell_spans(FAKE_SHELL_JS)


def test_shell_spans_edges_stay_on_the_side_that_picks_more():
    src = (
        '  document.addEventListener("input", onInput);\n'  # 1：一行的 handler，下一行的名字不能漏
        "  function named() {\n"  # 2
        "  }\n"  # 3
        '  document.addEventListener("click", (ev) => {\n'  # 4
        "      switch (act) {\n"
        '        case "a":\n'  # 6：連續只有標籤的行併成一個
        '        case "b":\n'  # 7
        "          both();\n"  # 8
        "          break;\n"  # 9
        '        case SOME: other(); break;\n'  # 10：認不得的標籤
        "        default: quiet();\n"  # 11
        "      }\n"
        "  });\n"
    )
    spans = {name: (start, end) for name, start, end in test_for.shell_spans(src)}
    assert spans == {"named": (2, 3), "case:a|b": (6, 9)}  # 第 10、11 行落在 span 外 → 原挑法


@pytest.mark.parametrize("name", ["choose", "render", "pageJianghu", "case:gate"])
def test_shell_spans_read_the_real_shell_files(name):
    """真實的兩支認得這幾個。失效了是全部退回原挑法（方向對、只是又變慢），這條是讓人知道。"""
    found = {span[0] for js in ("app.js", "main.js")
             for span in test_for.shell_spans((test_for.ROOT / "web" / js).read_text(encoding="utf-8"))}
    assert name in found


# ── 第 106 批：守門跟著帶 ──
IMPORT_SCAN = "tests/core/test_feature_boundaries.py::test_every_tianxia_import_resolves"


@pytest.mark.parametrize("changed", [
    "tianxia/features/mall/actions.py", "tianxia/server_bots.py", "scripts/set_password.py", "scripts/sb/base.py", "scripts/webqa/flows/z.mjs", "server.py", "run_bots.py", "tale_html.py",
])
def test_code_files_bring_the_old_name_scan_and_only_that_one_node(changed):
    """舊名掃描整條是 slow，不跟著跑就抓不到新寫的舊名；只跑那一條（約 6 秒），不是整個 slow。"""
    picked = test_for.pick([changed], base="HEAD")
    assert picked.nodes == {IMPORT_SCAN}
    assert not picked.empty


@pytest.mark.parametrize("changed", [
    "docs/superpowers/plans/x.md", "content/events/jizhou.json", "tests/core/test_engine.py", "tianxia/features/mall/tests/test_mall_routes.py", "web/mall.css",
])
def test_other_files_do_not_bring_the_old_name_scan(changed):
    assert not test_for.pick([changed], base="HEAD").nodes


def test_the_node_runs_apart_with_slow_and_the_exit_code_counts(monkeypatch, capsys):
    picked = test_for.pick(["tianxia/features/mall/actions.py"], base="HEAD")
    (node,) = test_for.node_commands(picked, ["-x"])
    assert _marker(node) == "slow or not slow" and IMPORT_SCAN in node and node[-1] == "-x" and "-n" not in node
    assert all(IMPORT_SCAN not in cmd for cmd in test_for.pytest_commands(picked, slow=False, extra=[]))  # 不併進去：其他挑到的照舊不含 slow
    assert any(IMPORT_SCAN in line for line in test_for.describe(picked))
    assert test_for.node_commands(test_for.Pick(everything=True), []) == []  # 整套本來就含
    assert test_for.node_commands(test_for.Pick(files={ROOT / "tests/core/test_engine.py"}), []) == []
    # main：跑完 pytest_commands 接著跑它，它紅了整個紅
    ran = []
    monkeypatch.setattr(test_for, "base_line", lambda base, source: ("base", True))
    monkeypatch.setattr(test_for.subprocess, "call", lambda cmd, cwd=None: ran.append(cmd) or (1 if IMPORT_SCAN in cmd else 0))
    assert test_for.main(["tianxia/features/mall/actions.py", "--base", "HEAD"]) == 1
    assert IMPORT_SCAN in ran[-1] and len(ran) == 2
    capsys.readouterr()


def test_a_file_with_only_the_node_runs_only_the_node(monkeypatch):
    """挑到的只有這一條時不准多一次不帶目標的 pytest（那會變成整套）。"""
    only = test_for.Pick(nodes={IMPORT_SCAN})
    assert not only.empty
    assert test_for.pytest_commands(only, slow=False, extra=[]) == []
    ran = []
    monkeypatch.setattr(test_for, "base_line", lambda base, source: ("base", True))
    monkeypatch.setattr(test_for, "pick", lambda files, base=None: only)
    monkeypatch.setattr(test_for.subprocess, "call", lambda cmd, cwd=None: ran.append(cmd) or 0)
    assert test_for.main(["tianxia/zz.py", "--base", "HEAD"]) == 0
    assert len(ran) == 1 and IMPORT_SCAN in ran[0]


def test_a_package_routes_file_brings_the_route_guards():
    """包的 routes.py：動作表的鎖與鎖外三段式只有這兩個檔守（稽核注入綠）；只有包那一支 routes.py，子資料夾的不算。"""
    guards = {"test_action_tables.py", "test_outlock.py"}
    assert guards <= _names(["tianxia/features/feast/routes.py"], base="HEAD")
    assert not guards & _names(["tianxia/features/feast/actions.py"], base="HEAD")
    assert not guards & _names(["tianxia/features/feast/tests/routes.py"], base="HEAD")


@pytest.mark.parametrize("changed, hunks_of", [
    ("web/mall.js", None), ("web/mall.css", None), ("web/style.css", None), ("web/index.html", None), ("web/app.js", APP_JS_NO_DIFF),
])
def test_web_files_bring_the_bot_word_scan_and_the_shell_lists(changed, hunks_of):
    """web/ 送到每個玩家的瀏覽器：FB-673 的掃描（test_server_bots）與殼的名單（test_shell_stays_thin）一律帶，包的網頁檔那一支也是。"""
    assert {"test_server_bots.py", "test_shell_stays_thin.py"} <= _names([changed], base="HEAD", hunks_of=hunks_of)


def test_a_shell_js_picked_by_hunk_still_brings_the_shell_lists(monkeypatch):
    picked = _shell_pick(monkeypatch, 9, {"topHtml": ["test_might.py"]})
    assert {"test_server_bots.py", "test_shell_stays_thin.py"} <= {p.name for p in picked.files}


def test_a_script_brings_the_boundary_test():
    """腳本 import 包有反方向的名單（test_only_the_shells_the_scripts_and_the_aliases_import_a_package）與舊名掃描，改腳本要帶。"""
    assert "test_feature_boundaries.py" in _names(["scripts/set_password.py"], base="HEAD")


def test_content_brings_the_shell_lists():
    assert "test_shell_stays_thin.py" in _names(["content/events/jizhou.json"], base="HEAD")


def test_core_and_contract_bring_the_shell_lists():
    assert "test_shell_stays_thin.py" in {p.name for p in test_for.core_tests()}
    assert "test_shell_stays_thin.py" in {p.name for p in test_for.contract_tests()}
