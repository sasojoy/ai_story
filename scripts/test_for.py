"""改了哪些檔就跑哪幾條測試（開發中用；整套交給每日整套 scripts/nightly.ps1 與上 main 之前）。

用法：
  python scripts/test_for.py                 # 跟 origin/develop 比（或 TIANXIA_TEST_BASE），加上還沒提交的改動
  python scripts/test_for.py --base origin/feature/formal-season   # 功能分支的工作樹：跟功能分支比
  python scripts/test_for.py tianxia/fusion.py content/skills.json
  python scripts/test_for.py --list ...      # 只列出會跑哪些、為什麼，不跑
  python scripts/test_for.py --count ...     # 再用 pytest --collect-only 數一共幾條（不跑）
  python scripts/test_for.py --slow          # 挑到的連 slow 一起跑（內容批要當場跑真實內容的整季時用）
  python scripts/test_for.py --all           # 整套（含 slow），上 main 之前用
  python scripts/test_for.py -- -x -k fuse   # -- 之後的參數原樣交給 pytest（-- -n 2 會換掉預設的 -n 4）

怎麼挑（開發規範手冊 4.3，docs/superpowers/specs/2026-10-30-開發模式-design.md）：
- 「核心測試」＝ 核心模組自己檔名的測試（test_<模組>…；江湖紀錄的 test_journal、全部拆包第 25 批收進來的
  world 的 test_world、test_world_map 不收，第 36 批收進來的 step、weekcard 的 test_step、test_weekcard 也不收，NOT_CORE_TESTS）＋ tests/core/test_engine*.py
  ＋ tests/core/ 的核心契約、邊界、錢包服務測試（CORE_GLOBS），不含 slow；「煙霧」＝ 標了 @pytest.mark.smoke 的
  （每個區塊約 10 條）。
- tianxia/features/<包>/**：那一包的 tests/ ＋ 核心契約（tests/core/test_contract*.py 與邊界 test_feature_boundaries.py，
  CONTRACT_GLOBS：手冊 4.1 第三級的核心契約含邊界測試，改包最容易踩的就是 import 了別的包）。test_contract_features.py 逐包參數化的那幾條
  只跑 [<包>]（別的包那幾格 --deselect，第二輪第 75 批；改核心、改到契約檔本身、--all、整套與閘門全跑）。
  包的 checks.py（內容驗證）再加 test_content.py：那幾包的驗證測試寫在那裡（PM 定，第二輪 F 波）。
- 核心（tianxia/core/**，與 tianxia/core/__init__.py 的 MODULES：手冊 3.1 的 state、models、content、rules、calendar、
  sqlite_world、world_state、characters、accounts、database、team、gender、naming，3.10 的 wallet，PM 10/31 的 journal，全部拆包第 25 批的 world、
  第 32 批的 log_archive（它的 test_log_archive 收進核心測試）、第 36 批的 step、weekcard（NOT_CORE_TESTS）；
  邊界測試照同一份）：核心測試＋煙霧＋檔名是 test_<模組>… 的。tianxia/core/ 底下掛鉤與清單（CORE_LISTS：features、services、
  registry、__init__）以外的（event_check.py：第 16 批從 Game 搬來的事件檢定）再並上寫到改到的函式名（連模組名）、Game 委派名、
  類別與常數的測試檔，模組裡直接叫它的函式一路往上算（core_module_callers；第 16 批修正，PM 11/03 照第 11 批修正輪的做法）。
  tianxia/core/services_list.md（服務清單，第二輪第 74 批）只有邊界測試讀，只挑 test_feature_boundaries.py。
  tianxia/core/tuning/<包>.py（新包的 Config 子模型，第二輪第 74 批）只挑那一包的 tests/；沒有那一包的 tests/ 照核心。
  核心服務檔（CORE_SERVICES：combat、pushing、pills、status_view、page_view、scene_view，第二輪第 75 批）不走這一條：hunk 落在函式、類別、常數上 →
  名字的功能群（檔名有名字第一個認得的字的測試檔，連模組裡用到它的；service_groups）＋這個檔的底＋自己檔名的＋邊界測試；函式以外或指名了卻沒有差 → 核心測試＋煙霧。
- 共用規則層（tianxia/core/registry.py 的 SHARED，全部拆包第 15 批登記；照語法樹讀、跟邊界測試同一份）：自己檔名的測試（同核心）
  ＋煙霧＋邊界測試 test_feature_boundaries.py，不跑核心測試、不照「誰 import 它」挑也不往上找（總表第六節第 5 條；依賴它的測試
  留給合併閘門與每日整套，要當場驗就直接給那幾個測試檔或 --all）。改到內容驗證（最外層、名字 check_*、validate_*、參數有 need 的 def，
  或它用到的小函式與常數；沒有差就照整個檔）再加 test_content.py（shared_content_checks，第二輪第 95 批：content.validate 在函式內叫，import 圖看不到）。
- tianxia/engine.py：hunk 落在一行委派 → 那一包的 tests/＋核心契約＋內文寫到那個方法名的測試檔（engine_delegates，舊檔裡是胖方法、
  這一次才換成委派的不算委派）。落在其餘的方法（Game 的門面與核心）→ 核心測試＋煙霧＋內文寫到那個方法名的測試檔，同 core_module_callers：
  寫到它的超過 IMPORT_CAP 個檔不併（choose、sync 這種）；方法以外 → 核心測試＋煙霧。核心測試本來就含核心契約，只改到委派的另外帶核心契約。
  內文是假原始碼、或名單寫滿委派名的（test_test_for、核心契約，TEXT_BLIND）不算寫到。全部拆包第 61 批拿掉了照方法名、hunk 裡的字分功能群的過渡挑法。
- server.py：核心測試＋煙霧＋tests/server/test_server.py＋全部 test_*_shell.py（第 61 批從 test_server 拆進各包的）。路由都在包裡，改路由是改包。
- 其他 tianxia/<模組>.py、run_bots.py、scripts/<腳本>.py：直接 import 它的測試檔，加上檔名是 test_<模組>… 的、檔名是模組名
  第一個字的（mingtie_card → test_mingtie.py）（「import 了 engine」不再算相關：engine.py 照上面那一條）。
  tianxia/<模組>.py 另外照模組之間最外層的 import 往上找（dependents；10/31 測試自檢 T-02：改 might.py 以前挑 0 個檔）：
  import 任何依賴它的模組的測試檔也挑；engine 與假人三支（DRIVERS）、核心模組不往上走，彙整的模組（自己 import 至少
  AGGREGATOR_FANOUT 個的：shopview……；skillview 第二輪第 88 批切開之後只是給測試的殼）算、不往上走；往上找到的超過 IMPORT_CAP 個檔（tactics、zh 這種底層的）改加
  核心測試＋煙霧。engine 只為了登記才 import 的（from . import wanted as _wanted_card  # noqa: F401）照它登記的動作名
  （social.register(CardAction(id=KIND))：wanted、mingtie）挑寫到 "wanted" 的測試檔（registered_actions；
  搬進功能包的登記〔mingtie_card，第 37 批〕改在包的 __init__.py 寫同樣的 `as _x  # noqa: F401`，照樣認）。
- scripts/sb/**（情境，第二輪第 70 批）：不照檔名字根挑（量到 198 個檔，軌名撞 world、map 這種模組名，它們都不讀這些檔），只跑邊界測試；
  情境改了跑那一軌的 same_behavior selftest。scripts/webqa/**（網頁比對工具，第二輪第 77 批，有 .mjs、.txt）：tests/web/test_webqa.py。
- content/：test_content.py ＋ test_real_content.py ＋ 寫到那個檔名的測試檔，照舊不含 slow：test_real_content.py 用真實內容
  跑整季的那幾條是 slow（--slow 才跑、每日整套會跑），其他的（事件難度帶 DIFFICULTY_BANDS 的鎖、地點走得到……）每次都跑。
  包裡的內容檔（tianxia/features/<包>/content/，全部拆包第 62 批）兩條都走：內容這一條＋那一包的 tests/＋核心契約。
  內容這一條再加 test_content_packs.py（新檔忘了寫進 Feature.content 時載入不報錯，只有它抓得到）。
- web/：寫到那個檔名的測試檔（main.js 照 app.js 挑），加上 test_server.py。web/app.js、web/main.js 另外照 hunk 挑（shell_js_writers，第二輪第 95 批）：
  落在頂層的 function、const、let 或事件處理的 case（shell_spans）→ 寫到那個名字或 case 標籤的測試檔（整檔 slow 的網頁測試連 slow 一起跑）
  ＋test_shell_web.py、test_server_bots.py＋煙霧；只改名字以外的註解或空行只有固定那幾個；沒有測試寫到的名字也只有固定那幾個（執行期才炸的靠每日整套）。
  沒有差、落在名字以外的程式行、任一個名字超過 SHELL_NAME_CAP 個檔寫到（choose、pageJianghu 這種）→ 上面的原挑法。功能包登記的網頁檔
  （各包 __init__.py 的 web，例 web/mall.js、web/mall.css、web/outing.js；feature_web）→ 那一包的 tests/＋核心契約（CONTRACT_GLOBS）
  ＋寫到那個檔名的（店面的 CSS 守門），不照 app.js 挑、不加 test_server.py（PM 2026-10-31）。包的 js 另外：包裡用假瀏覽器
  （webharness）跑整支頁面、真的執行它的網頁測試（test_mall_web）連 slow 一起跑，跟改到的測試檔一樣（runs_js）。
- tests/ 裡的測試檔：跑它自己，連 slow 一起（改了就是要跑它；挑到的其他檔照舊不含 slow，所以分兩次跑）；
  tests/kit/ 這類共用工具：import 它的測試檔；tests/fixtures/：寫到那個檔名的測試檔。
  「import 它」都順著 tests/kit/ 往下找一層（reached，第二輪第 75 批：test_battle_page_web → jianghu_kit → webharness）；web/ 的「寫到檔名」也看 kit 的內文（web_text，KIT_TEXT_BLIND 不算）。
  包裡的測試內容（tianxia/features/<包>/tests/content/，全部拆包第 63 批）：同 tests/fixtures/，再加那一包的 tests/ 與 test_content_packs.py。
- tests/conftest.py：hunk 落在哪個函式、fixture 或常數 → 用到它的測試檔（from conftest import、fixture 參數；conftest 裡
  別的 fixture 用到它的連那一個的使用者）；autouse 的 fixture、最外層的 import 與 sys.path、或用到的檔超過 CONFTEST_CAP 個
  （content、game 這種）→ 煙霧。整套留給每日整套。
- pyproject.toml、requirements*.txt：不挑（整套留給每日整套）。docs/、CLAUDE.md 這類文件：不跑。
slow 不自動跟（--slow 才加，連核心測試的 slow 一起）：挑到的檔整個標 slow 的，開跑前列出來；全被 slow 濾光、一條都沒跑時
說要 --slow、結束碼 0（不是 pytest 的 5）。挑到三個檔以上預設 -n 4（不寫 auto：同一台常有別的代理在跑），
-- 之後給了 -n 就照給的。跟 base 找不到分岔點（沒明確 fetch 的 feature/*、dev/*）：第一行說怎麼 fetch，停下、結束碼 2。"""
from __future__ import annotations

import argparse
import ast
import collections
import functools
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
CORE_TESTS = TESTS / "core"
FEATURES = ROOT / "tianxia" / "features"
PARALLEL_FROM = 3  # 挑到這麼多個檔以上才開 xdist（開工作行程本身要幾秒）
WORKERS = "4"  # 開發規範手冊 4.5：同一台同時最多兩份測試在跑，各自 -n 4
# 殼的網頁檔：網頁測試每一條都載入（tests/kit/webharness.py 的 APP_FILES 扣掉功能包的 js），改哪一個都照 app.js 挑。
# 功能包的 js（mall.js；outing.js 主動搬六包第 3＋4 批登記成探索包的）也在 APP_FILES 裡，可是照那一包挑（feature_web）；
# test_test_for 守 WEB_SCRIPTS ∪ 各包的 js == APP_FILES
WEB_SCRIPTS = {"shell.js", "main.js", "arena_anim.js", "arena_scene.js", "state.js", "fit.js", "app.js"}  # map.js 第 49 批起是輿圖包登記的網頁檔（feature_web）；admin.js 第二輪第 90 批起是管理者包的
SETUP_FILES = {"pyproject.toml", "requirements.txt", "requirements-dev.txt"}  # conftest.py 另外照 hunk 挑（conftest_picks）
CONFTEST_CAP = 50  # conftest 改到的名字有超過這麼多個測試檔在用（content、game、real_content）：不一個一個挑，跑煙霧
# 跟哪一條分支比：PM 2026-10-31 起預設 origin/develop（大家從 develop 開）；環境變數 TIANXIA_TEST_BASE 蓋過預設、
# --base 再蓋過它（功能分支的工作樹照舊給 --base origin/feature/<名字>）。default_base() 每次現讀環境變數。
DEFAULT_BASE = "origin/develop"
BASE_ENV = "TIANXIA_TEST_BASE"
CONTENT_TEST = "test_content.py"  # 內容改了就跟；共用層改到內容驗證也跟（shared_content_checks，第二輪第 95 批）
REAL_CONTENT_TEST = "test_real_content.py"  # 內容改了就跟（不含 slow）；用真實內容跑整季的那幾條是 slow，--slow 才跑
PACK_CONTENT_TEST = "test_content_packs.py"  # 內容改了也跟：包裡新檔忘了宣告（Feature.content）時載入不報錯、事件靜靜少掉，只有這支抓得到，新檔名又不會寫在它裡面
SERVER_TEST = "test_server.py"
WEBQA_TEST = "test_webqa.py"  # scripts/webqa/** 的工具自測
SHELL_TEST = re.compile(r"test_\w+_shell\.py")  # 第 61 批從 test_server 拆進各包的路由與殼的測試

CORE_INIT = ROOT / "tianxia" / "core" / "__init__.py"


def core_modules(init: Path = CORE_INIT) -> frozenset[str]:
    """核心的模組：tianxia/core/__init__.py 的 MODULES（手冊 3.1 的十三個、3.10 的錢包、PM 10/31 定算核心的江湖紀錄），
    跟邊界測試 tests/core/test_feature_boundaries.py 同一份。照語法樹讀、不 import（同 feature_web：核心寫壞了 test_for
    照樣挑得出來）；讀不出來（語法錯、沒有 MODULES）在 stderr 說一聲、當成沒有——改 tianxia/core/ 本來就跑核心測試＋煙霧。"""
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))  # 模組一載入就讀：_ast 還沒定義
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MODULES" for t in node.targets):
                value = node.value
                if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "frozenset" and value.args:
                    value = value.args[0]
                return frozenset(ast.literal_eval(value))
        problem = "沒有 MODULES"
    except (OSError, SyntaxError, ValueError) as e:
        problem = f"{type(e).__name__}: {e}"
    print(f"test_for：{_rel_root(init)} 讀不出核心的模組（{problem}），這一次不認核心模組", file=sys.stderr)
    return frozenset()


def _rel_root(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


# 核心（手冊 3.1、4.2、4.3）：改了跑核心測試＋煙霧＋自己檔名的測試，不照「誰 import 它」挑（team、models、state 被一兩百個
# 測試檔 import）。只有一份，在 tianxia/core/__init__.py（test_test_for 守它跟邊界測試的 CORE 一樣）
CORE_MODULES = core_modules()

# shared（全部拆包第 15 批「共用規則層登記」，計畫 docs/superpowers/plans/2026-11-01-共用規則層登記.md 1.6）
REGISTRY = ROOT / "tianxia" / "core" / "registry.py"


def shared_modules(registry: Path = REGISTRY) -> frozenset[str]:
    """共用規則層的模組：tianxia/core/registry.py 的 SHARED（模組名 → 理由），跟邊界測試同一份。照語法樹讀、不 import（registry 會
    import 每一包：包寫壞了 test_for 照樣挑得出來）；讀不出來（語法錯、沒有 SHARED、值不是字面的）在 stderr 說一聲、當成沒有——
    那些模組就照一般的舊模組挑（挑得多，不會漏）。"""
    try:
        tree = ast.parse(registry.read_text(encoding="utf-8"))
        for node in tree.body:
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) else None
            if isinstance(target, ast.Name) and target.id == "SHARED" and node.value is not None:
                return frozenset(ast.literal_eval(node.value))
        problem = "沒有 SHARED"
    except (OSError, SyntaxError, ValueError) as e:
        problem = f"{type(e).__name__}: {e}"
    print(f"test_for：{_rel_root(registry)} 讀不出共用規則層的模組（{problem}），這一次照一般的舊模組挑", file=sys.stderr)
    return frozenset()


# 共用規則層（總表第六節第 5 條；手冊 4.3 沒有這一種，第 15 批定成「核心那一種拿掉核心測試」）：改了跑自己檔名的測試＋煙霧＋邊界測試，
# 不跑核心測試、不照「誰 import 它」挑也不往上找（timetable 以前挑到 5,195 條、tactics 走「太多」那一條帶核心測試 1,800 條）。
# 邊界測試另外帶：「共用規則層只 import 核心本體與同一層」只有它守（同 engine.py 有 hunk 一律帶邊界）。
SHARED_MODULES = shared_modules()
BOUNDARY_TEST = "test_feature_boundaries.py"
# 核心模組裡、自己檔名的測試不收進「核心測試」的：江湖紀錄的 test_journal（76 條）。PM 10/31 定的核心測試是手冊 3.1 那十三個
# 自己的測試＋test_engine＋契約、邊界、錢包（CORE_GLOBS），journal 算核心是同一天邊界測試那一條定的；收進來改 models.py 一個
# 欄位的底數從 1,517 再漲到約 1,593，要不要收等 PM 跟 < 1,500 一起定。改 journal.py 照舊跑它（自己檔名的測試）。
# core_world（全部拆包第 25 批）：world 收進核心本體，同 journal 先不收它的 test_world、test_world_map（69 條；test_world_state 是 world_state 的、
# 照舊在）——核心測試照 PM 10/31 定的那一份，要不要收交 PM。改 world.py 照舊跑它們（自己檔名的測試）。
NOT_CORE_TESTS = frozenset({"journal", "world"})
# core_step（全部拆包第 36 批）：step、weekcard 收進核心本體，同 world 先不收它們的 test_step（9 條）、test_weekcard（8 條）——改別的核心模組
# 不多跑這 17 條；改 step.py、weekcard.py 照舊跑它們（自己檔名的測試）。
NOT_CORE_TESTS = NOT_CORE_TESTS | {"step", "weekcard"}
# merge_back（主幹合回 develop，2026-11-06，PM 認定第 1 條）：attrset 進核心本體，同 world、step 先不收它的 test_attrset（467 行）；改 attrset.py 照舊跑它（自己檔名的測試）。
NOT_CORE_TESTS = NOT_CORE_TESTS | {"attrset"}
# 「核心測試」除了核心模組自己檔名的，再收 tests/core/ 底下這幾種（core_tests）：Game 門面、核心契約、邊界、錢包服務
CORE_GLOBS = ("test_engine*.py", "test_contract*.py", "test_feature_boundaries.py", "test_wallet.py")
# 功能包改了跟著那一包跑的「核心契約」（tests/core/ 底下；手冊 4.1 第三級：選項帶前綴、choose 不吃別包的、關著不給、換季、邊界）
CONTRACT_GLOBS = ("test_contract*.py", "test_feature_boundaries.py")
HUNK_FILES = {"tianxia/engine.py"}  # 看 hunk 落在哪個方法的（委派 → 那一包；其餘 → 核心測試＋煙霧＋寫到那個方法名的）
# 內文是假的原始碼、或名單寫滿了各包的委派名，不算「寫到那個名字」的測試檔（_index、action_files）：test_test_for 的假 engine 寫了
# _tavern_price、_pill_day……；核心契約與邊界測試固定跟著核心走（改核心照核心測試挑到〔CORE_GLOBS〕、改包與包的委派照核心契約挑到〔contract_tests〕）。
# 改 scripts/test_for.py 照舊挑到 test_test_for（檔名 test_<模組>）。
TEXT_BLIND = frozenset({"test_test_for.py", "test_feature_boundaries.py", "test_contract_core.py", "test_contract_features.py"})
# 第二輪第 75 批：逐包參數化的核心契約。改包時那幾條只跑 [<包>]，別的包那幾格用 --deselect 拿掉（整套與閘門不走 test_for，照舊全跑）；
# 跨包的問題（這一包新給的 id 被別包的 choose 吃掉）這裡抓不到，留給波末閘門（同企劃者 11/04 的取捨）。
PER_PACKAGE_CONTRACT = "test_contract_features.py"


@dataclass
class Pick:
    """挑到的東西。files 整個檔跑（不含 slow，--slow 才含）；own 是改到的測試檔本身（也在 files 裡，連 slow 一起跑）；
    runs_js 是包裡真的執行改到的那個包的 js 的網頁測試（也在 files 裡，跟 own 一樣連 slow 一起跑）；
    core 加核心測試；smoke 加煙霧；everything 是整套。"""
    files: set[Path] = field(default_factory=set)
    own: set[Path] = field(default_factory=set)
    runs_js: set[Path] = field(default_factory=set)
    core: bool = False
    smoke: bool = False
    everything: bool = False
    why: list[str] = field(default_factory=list)
    contract_only: set[str] = field(default_factory=set)  # 逐包的核心契約只跑這幾包（空的＝不限；core、改到契約檔本身也不限，_contract_deselect）

    @property
    def empty(self) -> bool:
        return not (self.files or self.core or self.smoke or self.everything)

    @property
    def with_slow(self) -> set[Path]:
        """連 slow 一起跑的那幾個檔（另外跑一次）：改到的測試檔＋執行改到的包 js 的網頁測試。"""
        return self.own | self.runs_js


# ── git ──────────────────────────────────────────────────────────────

def _git(*args: str) -> subprocess.CompletedProcess:
    # core.quotepath=off：中文檔名照原字印（不然是 "docs/guide/\351\207…" 加引號，對不上任何規則）
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def default_base() -> str:
    """沒給 --base 時跟哪一條比：TIANXIA_TEST_BASE，沒設就是 origin/develop。"""
    return os.environ.get(BASE_ENV, "").strip() or DEFAULT_BASE


def base_line(base: str, source: str) -> tuple[str, bool]:
    """（--list 與每一次的第一行, 有沒有分岔點）。第一行寫這一次跟哪個 base 比、從哪裡來的、分岔點；找不到那條分支就直說
    怎麼 fetch（這份 clone 的 git fetch origin 不更新 feature/*、dev/*）。沒有分岔點的 main 停下不挑（NO_FORK）。"""
    mb = _git("merge-base", base, "HEAD")
    if mb.returncode == 0 and mb.stdout.strip():
        return f"跟 {base} 比（{source}；分岔點 {mb.stdout.strip()[:8]}）", True
    if _git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        how = ""
        if base.startswith("origin/"):
            branch = base.removeprefix("origin/")
            how = f"，先明確 fetch：git fetch origin +refs/heads/{branch}:refs/remotes/origin/{branch}"
        return f"跟 {base} 比（{source}）：找不到這條分支{how}", False
    return f"跟 {base} 比（{source}）：跟 HEAD 沒有共同的祖先", False


# 跟 base 沒有分岔點時挑法不準（10/31 審查）：不給檔名，git diff base...HEAD 失敗、只剩還沒提交的改動；給了檔名，拿不到舊版、
# 整個檔當成新檔（models.py 挑到 347 個檔）。兩種都停下、不挑不跑，結束碼 NO_FORK_EXIT。
NO_FORK = ("沒有分岔點就算不出這條分支改了什麼（不給檔名只剩還沒提交的改動；給了檔名整個檔都當新的，挑到幾百個檔），"
           "所以停下、一條都不跑（結束碼 2）。fetch 好再跑、換 --base，或用 --all 跑整套。")
NO_FORK_EXIT = 2


def changed_files(base: str | None = None) -> list[str]:
    """跟 base（預設 default_base()）分岔之後改過的、還沒提交的、還沒加進版控的檔。"""
    base = base or default_base()

    def names(*args: str) -> list[str]:
        return [line.strip() for line in _git(*args).stdout.splitlines() if line.strip()]

    files = names("diff", "--name-only", f"{base}...HEAD") + names("diff", "--name-only", "HEAD")
    files += names("ls-files", "--others", "--exclude-standard")
    return sorted(set(files))


def merge_base(base: str) -> str:
    out = _git("merge-base", base, "HEAD")
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else base


Lines = list[tuple[int, str]]
Hunk = tuple[Lines, Lines]  # （舊檔拿掉的行, 新檔加上的行）；行是（行號, 內容）


def hunks(path: str, base: str) -> tuple[list[Hunk], str, str]:
    """path 跟 base 的分岔點比（含還沒提交的）的 hunk，加上分岔點那一版與現在的原始碼（沒有的是空字串）。"""
    mb = merge_base(base)
    new_src = (ROOT / path).read_text(encoding="utf-8", errors="replace") if (ROOT / path).exists() else ""
    old = _git("show", f"{mb}:{path}")
    old_src = old.stdout if old.returncode == 0 else ""
    out = _git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", mb, "--", path).stdout
    result: list[Hunk] = []
    old_no = new_no = 0
    for line in out.splitlines():
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(2))
            result.append(([], []))
        elif result and line.startswith("-") and not line.startswith("---"):
            result[-1][0].append((old_no, line[1:]))
            old_no += 1
        elif result and line.startswith("+") and not line.startswith("+++"):
            result[-1][1].append((new_no, line[1:]))
            new_no += 1
    if not result and not old_src and new_src:  # 還沒加進版控的新檔：每一行都是新的
        result = [([], list(enumerate(new_src.splitlines(), 1)))]
    return result, old_src, new_src


# ── 測試檔 ───────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=None)
def _all_tests() -> tuple[Path, ...]:
    found = [t for t in TESTS.rglob("test_*.py") if "fixtures" not in t.relative_to(TESTS).parts]
    if FEATURES.is_dir():
        found += list(FEATURES.glob("*/tests/**/test_*.py"))
    return tuple(sorted(found))


def all_tests() -> list[Path]:
    """tests/ 與 tianxia/features/<包>/tests/ 底下所有的測試檔（fixtures 不算）。"""
    return list(_all_tests())


@functools.lru_cache(maxsize=None)
def _text(test: Path) -> str:
    return test.read_text(encoding="utf-8")


def _ast(text: str) -> ast.Module:
    """照原始碼建語法樹，不印 SyntaxWarning（有的測試檔字串裡寫了 "\\/"，每挑一次就印一次很吵）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(text)


_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)|import[ \t]+([^\n]+))", re.M)


@functools.lru_cache(maxsize=None)
def imported(test: Path) -> frozenset[str]:
    """這個測試檔直接 import 的本專案模組（tianxia.x 記成 x；server、run_bots、scripts 底下的腳本照名字）。
    用正規式讀，不建語法樹（四百多個檔建語法樹要一秒多）。"""
    names: set[str] = set()
    for m in _IMPORT.finditer(_text(test)):
        module, what, plain = m.group(1), m.group(2), m.group(3)
        if module:
            if module == "tianxia":
                names.update(n.split()[0] for n in what.strip("()").replace("\n", " ").split(",") if n.strip())
            elif module.startswith("tianxia."):
                names.add(module.split(".")[1])
            else:
                names.add(module.split(".")[0])
        else:
            for part in plain.split("#")[0].split(","):
                name = part.strip().split(" ")[0]
                if name:
                    names.add(name.split(".")[1] if name.startswith("tianxia.") else name.split(".")[0])
    return frozenset(names)


# 第二輪第 75 批（C 波審查的 nit）：測試經 tests/kit/ 的小工具用到的（test_battle_page_web → jianghu_kit → webharness；
# *_shell → server_kit → server_push），順著 kit 往下找一層也算。只有 tests/kit/ 底下這幾個，測試檔互相 import 的不算。
KIT = TESTS / "kit"
# 找「寫到 js 檔名」不看的 kit：webharness 的 APP_FILES 寫滿每一支 js（算進來改哪一支都挑到它的 99 個使用者）；server_kit 只在小工具 _js_function 的說明字寫到 app.js（算進來多 15 個 *_shell，它們不跑畫面）
KIT_TEXT_BLIND = frozenset({"webharness", "server_kit"})


@functools.lru_cache(maxsize=None)
def _kits(test: Path) -> tuple[Path, ...]:
    return tuple(k for k in (KIT / f"{n}.py" for n in sorted(imported(test))) if k.is_file())


@functools.lru_cache(maxsize=None)
def reached(test: Path) -> frozenset[str]:
    """這個測試檔 import 的本專案模組，加上它 import 的 kit 再 import 的（往下一層）。"""
    return imported(test).union(*(imported(k) for k in _kits(test)))


def web_text(test: Path) -> str:
    """找「寫到某一支 js 的檔名」時看的字：測試檔本身＋它 import 的 kit（webharness 不算）。"""
    return _text(test) + "".join(_text(k) for k in _kits(test) if k.stem not in KIT_TEXT_BLIND)


# ── tianxia/ 模組之間的 import 圖（10/31 測試自檢 T-02）────────────────
# 只看直接 import 的話，改 might.py 挑不到 test_ascend、test_create_ritual（它們透過 ascend、create 用到 might）。所以照
# tianxia/ 模組之間最外層的 import 往上找：改了 X，import 任何「依賴 X 的模組」的測試檔也算。三種模組不往上走：
# - engine 與假人的三支（DRIVERS：bot、bot_policy、bot_runner，經 Game 什麼都碰）：engine 照它自己那一條（hunk 落在哪個
#   方法）另外挑，「import 了 engine」不算相關；拿 bot 當驅動的測試檔有三十幾個，算進來改 outing.py 也挑到七十幾個檔。
# - 核心模組（CORE_MODULES）：改核心照核心那一條；X 被核心 import，也不把 import 核心的幾百個測試檔算進來。
# - 彙整的模組（自己 import 至少 AGGREGATOR_FANOUT 個 tianxia 模組的：bot、shopview、mapdata……；world 第 25 批收進核心）：
#   import 它的測試檔算，可是不再往上走（不然 bot 一路帶出整套）。
# 函式裡的 import（多半是為了繞開互相 import 的圈）與 TYPE_CHECKING 底下的不算邊：算進來一百二十個模組連成一圈。
# 往上找到的（不含直接 import 的）超過 IMPORT_CAP 個測試檔時（tactics、zh、martial_arts 這種底層模組）：不一個一個挑，
# 改加核心測試＋煙霧，其他留給每日整套（同 conftest 的 CONFTEST_CAP）。
DRIVERS = frozenset({"engine", "bot", "bot_policy", "bot_runner"})
AGGREGATOR_FANOUT = 15
IMPORT_CAP = 120
TIANXIA = ROOT / "tianxia"


def _type_checking(node: ast.If) -> bool:
    t = node.test
    return (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING")


def _module_deps(tree: ast.Module, known: frozenset[str]) -> frozenset[str]:
    """一個模組最外層（含最外層的 if、try 裡面；不含函式、類別裡、TYPE_CHECKING 底下）import 的 tianxia 模組。"""
    found: set[str] = set()

    def visit(nodes) -> None:
        for n in nodes:
            if isinstance(n, ast.ImportFrom):
                if n.level == 1 and n.module is None or n.level == 0 and n.module == "tianxia":
                    found.update(a.name for a in n.names)
                elif n.level == 1:
                    found.add(n.module.split(".")[0])
                elif n.level == 0 and n.module and n.module.startswith("tianxia."):
                    found.add(n.module.split(".")[1])
            elif isinstance(n, ast.Import):
                found.update(a.name.split(".")[1] for a in n.names if a.name.startswith("tianxia."))
            elif isinstance(n, ast.If):
                visit(n.orelse if _type_checking(n) else [*n.body, *n.orelse])
            elif isinstance(n, ast.Try):
                visit([*n.body, *n.orelse, *n.finalbody, *(s for h in n.handlers for s in h.body)])

    visit(tree.body)
    return frozenset(found & known)


@functools.lru_cache(maxsize=None)
def module_graph() -> dict[str, frozenset[str]]:
    """tianxia/<模組>.py → 它最外層 import 的 tianxia 模組（照語法樹讀；讀不出來的當成沒有 import）。engine 不讀：
    它從來不往上走，讀它要多半秒。"""
    files = {p.stem: p for p in TIANXIA.glob("*.py") if p.stem != "__init__"}
    known = frozenset(files)
    graph: dict[str, frozenset[str]] = {}
    for mod, path in files.items():
        if mod == "engine":
            continue
        try:
            graph[mod] = _module_deps(_ast(path.read_text(encoding="utf-8")), known)
        except (OSError, SyntaxError):
            graph[mod] = frozenset()
    return graph


@functools.lru_cache(maxsize=None)
def dependents(mod: str) -> frozenset[str]:
    """依賴 mod 的 tianxia 模組（一路往上找，不含 mod 自己；DRIVERS、核心模組不算也不往上走，彙整的模組算、不往上走）。"""
    graph = module_graph()
    users: dict[str, set[str]] = collections.defaultdict(set)
    for m, deps in graph.items():
        for d in deps:
            users[d].add(m)
    seen: set[str] = set()
    todo = [mod]
    while todo:
        for u in users.get(todo.pop(), ()):
            if u in seen or u == mod or u in DRIVERS or u in CORE_MODULES:
                continue
            seen.add(u)
            if len(graph.get(u, ())) < AGGREGATOR_FANOUT:
                todo.append(u)
    return frozenset(seen)


_ENGINE_SIDE_IMPORT = re.compile(r"^from[ \t]+\.[ \t]+import[ \t]+(\w+)[ \t]+as[ \t]+_\w+[ \t]*#[ \t]*noqa:[ \t]*F401", re.M)


@functools.lru_cache(maxsize=None)
def registered_actions(mod: str) -> tuple[str, ...]:
    """engine.py 只為了登記才 import 的模組（`from . import wanted as _wanted_card  # noqa: F401`）登記的動作名：
    模組裡 xxx.register(CardAction(id=…)) 的 id（字面字串，或最外層的常數 KIND = "wanted"）。其他模組回空的。
    這種模組沒有測試檔 import 它（測試是經 Game.peer_card／peer_act 用到），只能照動作名挑。"""
    engine = TIANXIA / "engine.py"
    try:
        path = TIANXIA / f"{mod}.py"
        if mod not in _ENGINE_SIDE_IMPORT.findall(engine.read_text(encoding="utf-8")):
            # 搬進功能包之後，登記改在包的 __init__.py 載入時做（全部拆包第 37 批：mingtie_card 進了玩家互動包，舊名是別名）：
            # 同一個寫法，模組在那一包的資料夾裡
            path = next((init.parent / f"{mod}.py" for init in sorted((TIANXIA / "features").glob("*/__init__.py"))
                         if mod in _ENGINE_SIDE_IMPORT.findall(init.read_text(encoding="utf-8"))), None)
            if path is None:
                return ()
        tree = _ast(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ()
    consts = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
              for t in n.targets if isinstance(t, ast.Name)}
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
                and getattr(node.func, "attr", getattr(node.func, "id", None)) == "register"):
            continue
        for arg in node.args:
            for kw in (arg.keywords if isinstance(arg, ast.Call) else []):
                if kw.arg != "id":
                    continue
                value = kw.value.value if isinstance(kw.value, ast.Constant) else consts.get(getattr(kw.value, "id", ""))
                if isinstance(value, str) and value not in found:
                    found.append(value)
    return tuple(found)


def action_files(kind: str) -> set[Path]:
    """寫到動作名字串（"wanted"、'wanted'）的測試檔。"""
    quoted = (f'"{kind}"', f"'{kind}'")
    return {t for t in all_tests() if t.name not in TEXT_BLIND and any(q in _text(t) for q in quoted)}


def _parts(ident: str) -> list[str]:
    """一個識別字照底線與大小寫拆開、轉小寫（_tavern_seek → tavern、seek；TavernNote → tavern、note）。"""
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", ident)]


@functools.lru_cache(maxsize=None)
def _index() -> dict[str, frozenset[Path]]:
    """內文的識別字 → 寫到它的測試檔（TEXT_BLIND 不算）。"""
    by_text: dict[str, set[Path]] = collections.defaultdict(set)
    for t in all_tests():
        if t.name in TEXT_BLIND:
            continue
        for ident in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _text(t))):
            by_text[ident].add(t)
    return {k: frozenset(v) for k, v in by_text.items()}


def _first_word(name: str) -> str:
    parts = _parts(name)
    return parts[0] if parts else ""


_SMOKE = re.compile(r"^([ \t]*)@pytest\.mark\.smoke\b[^\n]*\n(?:\1@[^\n]*\n)*\1(?:async[ \t]+)?(?:def|class)[ \t]+(\w+)", re.M)


@functools.lru_cache(maxsize=None)
def smoke_ids() -> tuple[str, ...]:
    """標了 @pytest.mark.smoke 的測試（檔::函式、檔::類別、檔::類別::函式）；整個檔都是（pytestmark）就是那個檔。
    smoke 一律寫成 @pytest.mark.smoke 這一行（不要 from pytest import mark）；用正規式找，不建語法樹。"""
    ids: list[str] = []
    for test in all_tests():
        text = _text(test)
        if "smoke" not in text:
            continue
        rel = test.relative_to(ROOT).as_posix()
        if re.search(r"^pytestmark[ \t]*=.*\bsmoke\b", text, re.M):
            ids.append(rel)
            continue
        for m in _SMOKE.finditer(text):
            indent, name = m.group(1), m.group(2)
            if not indent:
                ids.append(f"{rel}::{name}")
                continue
            owner = None  # 縮排的：往回找它所在的類別
            for c in re.finditer(r"^class[ \t]+(\w+)", text[: m.start()], re.M):
                owner = c.group(1)
            if owner:
                ids.append(f"{rel}::{owner}::{name}")
    return tuple(ids)


def core_tests() -> list[Path]:
    """「核心測試」（PM 2026-10-31；跑的時候 -m "not slow"）：核心模組（CORE_MODULES，扣掉 NOT_CORE_TESTS）自己檔名的
    測試（test_<模組>.py、test_<模組>_….py，在哪個資料夾都算：test_naming 在 arts/、test_team 在 battle/）＋
    tests/core/test_engine*.py（Game 門面；屬於包的第 61 批搬走了）＋ tests/core/ 的核心契約、
    邊界、錢包服務測試（CORE_GLOBS，第 1 階才有）。不再是整個 tests/core/（雜燴：test_factions……）。"""
    own = {t for t in all_tests() for mod in CORE_MODULES - NOT_CORE_TESTS
           if t.stem == f"test_{mod}" or t.stem.startswith(f"test_{mod}_")}
    globbed = {t for pattern in CORE_GLOBS for t in CORE_TESTS.glob(pattern)}
    return sorted(own | globbed)


def contract_tests() -> set[Path]:
    """功能包改了跟著跑的核心契約（CONTRACT_GLOBS）。"""
    return {t for pattern in CONTRACT_GLOBS for t in CORE_TESTS.glob(pattern)}


@functools.lru_cache(maxsize=None)
def feature_web() -> dict[str, str]:
    """功能包登記的網頁檔 → 包名（{"mall.js": "mall", "mall.css": "mall"}）：各包 __init__.py 裡類別的 web = (…)，
    照語法樹讀、不 import（包寫壞了 test_for 照樣挑得出來）。test_test_for 守它跟 tianxia.core.features.web_files() 一樣。"""
    found: dict[str, str] = {}
    for init in sorted(FEATURES.glob("*/__init__.py")) if FEATURES.is_dir() else []:
        try:
            tree = _ast(init.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
                value = getattr(stmt, "value", None)
                if any(isinstance(t, ast.Name) and t.id == "web" for t in targets) and isinstance(value, (ast.Tuple, ast.List)):
                    for elt in value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            found[elt.value] = init.parent.name
    return found


_SLOW_MARK = re.compile(r"^[ \t]*(?:@pytest\.mark\.slow\b|pytestmark[ \t]*=[^\n]*\bslow\b)|\bmarks[ \t]*=[^\n]*\bmark\.slow\b",
                        re.M)


def has_slow(test: Path) -> bool:
    """這個測試檔有沒有標 slow 的（整個檔、類別、函式，或 pytest.param 的 marks）；字串裡寫到的不算。"""
    return _SLOW_MARK.search(_text(test)) is not None


def whole_slow(test: Path) -> bool:
    """整個檔都標 slow（pytestmark）：不加 --slow 一條都不跑。"""
    return re.search(r"^pytestmark[ \t]*=.*\bslow\b", _text(test), re.M) is not None


# ── 原始碼裡的位置 ───────────────────────────────────────────────────

def _span(node) -> tuple[int, int]:
    start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
    return start, node.end_lineno or node.lineno


@functools.lru_cache(maxsize=8)
def _parse(src: str):
    try:
        return _ast(src)
    except SyntaxError:
        return None


def _game_methods(src: str) -> list[tuple[str, int, int]]:
    tree = _parse(src)
    for node in (tree.body if tree else []):
        if isinstance(node, ast.ClassDef) and node.name == "Game":
            return [(n.name, *_span(n)) for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return []


def _top_level(src: str) -> list[tuple[str, int, int, object]]:
    """模組最外層的 def 與 class：（名字, 起, 迄, 節點）。"""
    tree = _parse(src)
    return [(n.name, *_span(n), n) for n in (tree.body if tree else [])
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _meaningful(text: str) -> bool:
    s = text.strip()
    return bool(s) and not s.startswith("#")


def _split(hunk_list: list[Hunk], old_src: str, new_src: str, spans_of) -> dict:
    """hunk 的每一行照它落在哪個 span（方法、函式、類別）分組：{名字: (拿掉的行, 加上的行)}；落在外面的記在 None。
    舊檔拿掉的行照舊檔的位置找，新檔加上的照新檔；外面的空行與註解不算。"""
    spans = (spans_of(old_src), spans_of(new_src))
    groups: dict = {}
    for hunk in hunk_list:
        for side in (0, 1):
            for no, text in hunk[side]:
                span = next((s for s in spans[side] if s[1] <= no <= s[2]), None)
                if span is None and not _meaningful(text):
                    continue
                groups.setdefault(span[0] if span else None, ([], []))[side].append((no, text))
    return groups


def _game_one_liners(src: str) -> dict[str, tuple[str, str]]:
    """Game 上本體（說明字之後）只有一句 `return <名字>.<函式>(self, …)`（或不 return 的那一句）的方法 → （<名字>, <函式>）。
    engine_delegates（委派給包）與 core_delegates（委派給核心本體）照它認。"""
    tree = _parse(src)
    out: dict[str, tuple[str, str]] = {}
    for node in (tree.body if tree else []):
        if not (isinstance(node, ast.ClassDef) and node.name == "Game"):
            continue
        for f in node.body:
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [s for s in f.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                              and isinstance(s.value.value, str))]
            call = body[0].value if len(body) == 1 and isinstance(body[0], (ast.Return, ast.Expr)) else None
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                    and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "self"):
                out[f.name] = (call.func.value.id, call.func.attr)
    return out


def engine_delegates(src: str) -> dict[str, str]:
    """engine.py 裡 Game 上的一行委派 → 它委派給哪一包（全部拆包第 11 批）：方法的本體（說明字之後）只有一句
    `return <名字>.<函式>(self, …)`（或不 return 的那一句），<名字> 是最外層 `from .features.<包> import <模組> [as <名字>]` 進來的。
    第二輪第 72 批起 engine.py 上沒有這種方法了（搬進各包 game_api.py，改表照 tianxia/features/<包>/** 那一條加 game_api_callers）；
    留著給 base 還在第 72 批之前的 diff 認舊檔。"""
    tree = _parse(src)
    if tree is None:
        return {}
    local: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and (node.module or "").startswith("features."):
            pkg = node.module.split(".")[1]
            local.update({a.asname or a.name: pkg for a in node.names})
    return {method: local[alias] for method, (alias, _) in _game_one_liners(src).items() if alias in local}


def engine_groups(hunk_list: list[Hunk], old_src: str,
                  new_src: str) -> tuple[bool, list[str], set[str], set[Path]]:
    """engine.py 的 hunk → （要不要核心測試＋煙霧, 為什麼, 委派到的包, 寫到那幾個方法名的測試檔）。hunk 落在一行委派
    （engine_delegates）上照那一包挑（那一包的 tests/＋核心契約，同改那一包的檔），再加內文寫到那個方法名的測試檔（包外直接叫它的）。
    是不是委派照舊檔認：舊檔裡是胖方法、這一次換成委派的不算委派（守那段舊本體的測試才挑得到）；舊檔沒有這個方法的才照新檔認。
    其餘的方法（Game 的門面與核心，第 61 批拿掉照名字分功能群之後）→ 核心測試＋煙霧＋內文寫到那個方法名的測試檔，同 core_module_callers：
    寫到它的超過 IMPORT_CAP 個檔不併（choose、sync 這種）。方法以外 → 核心測試＋煙霧。"""
    def spans_of(src: str):
        methods = _game_methods(src)
        tops = [(name, start, end) for name, start, end, node in _top_level(src)
                if not (isinstance(node, ast.ClassDef) and name == "Game")]
        return methods + tops

    core = False
    why: list[str] = []
    packages: set[str] = set()
    callers: set[Path] = set()
    old_methods = {name for name, _, _ in _game_methods(old_src)}
    delegates = {**{n: p for n, p in engine_delegates(new_src).items() if n not in old_methods}, **engine_delegates(old_src)}
    by_text = _index()
    for name in _split(hunk_list, old_src, new_src, spans_of):
        if name in delegates:
            packages.add(delegates[name])
            named = set(by_text.get(name, frozenset()))
            callers |= named
            why.append(f"{name}：{delegates[name]} 這一包的一行委派 → 那一包的 tests/＋核心契約"
                       + (f"＋寫到 {name} 的 {len(named)} 個檔" if named else ""))
            continue
        core = True
        if name is None:
            why.append("方法以外 → 核心測試＋煙霧")
            continue
        named = set(by_text.get(name, frozenset()))
        if len(named) > IMPORT_CAP:
            why.append(f"{name}：不是委派 → 核心測試＋煙霧；寫到 {name} 的測試檔有 {len(named)} 個，太多不併（其他留給每日整套；要當場驗用 --all）")
        else:
            callers |= named
            why.append(f"{name}：不是委派 → 核心測試＋煙霧" + (f"＋寫到 {name} 的 {len(named)} 個檔" if named else ""))
    return core, why, packages, callers


GAME_API_NAME = re.compile(r'(?:^\s*"|^def )(\w+)')


def game_api_callers(f: str, base: str, hunks_of: dict | None) -> set[Path]:
    """features/<包>/game_api.py 的 hunk 落在哪幾個名字（TABLE 的鍵、小 def）→ 內文寫到它們的測試檔（同 engine_groups 對一行委派的做法）。"""
    given = (hunks_of or {}).get(f)
    hunk_list = (given if given is not None else hunks(f, base))[0]
    names = {name for hunk in hunk_list for side in hunk for _, text in side for name in GAME_API_NAME.findall(text)}
    by_text = _index()
    return {path for name in names for path in by_text.get(name, frozenset())}


# ── core-events（全部拆包第 16 批修正，PM 2026-11-03）：改核心本體裡掛鉤、清單以外的模組 ─────────────
# tianxia/core/ 底下的掛鉤與清單（features.py 掛鉤、services.py 服務與共用的字〔清單在 services_list.md，上面另一條〕、registry.py 的 FEATURES、__init__.py 的 MODULES）改了照舊
# 只跑核心測試＋煙霧：裡面的名字（options、choose、FEATURES）到處都寫得到，照名字挑等於整套。其餘的核心本體（event_check.py 這種
# 從 Game 搬來的）照第 11 批修正輪的做法，再並上寫到改到的函式名或 Game 委派名的測試檔（core_module_callers）：搬之前照方法名
# 挑得到的隨口應對、端出事件的回歸，搬進核心之後 test_for 一條都挑不到（dev/core-events-1 審查 M1、M4、M8、M9）。
CORE_LISTS = frozenset({"__init__", "features", "services", "registry"})


@functools.lru_cache(maxsize=None)
def _engine_src() -> str:
    engine = ROOT / "tianxia" / "engine.py"
    return engine.read_text(encoding="utf-8") if engine.exists() else ""


def core_delegates(src: str) -> dict[str, tuple[str, str]]:
    """engine.py 裡 Game 上委派給核心本體的一行委派 → （核心的模組, 函式）：本體只有一句 `return <名字>.<函式>(self, …)`，
    <名字> 是最外層 `from .core import <模組> [as <名字>]` 進來的（_present → ("event_check", "present")）。"""
    tree = _parse(src)
    local: dict[str, str] = {}
    for node in (tree.body if tree else []):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "core":
            local.update({a.asname or a.name: a.name for a in node.names})
    return {method: (local[alias], func) for method, (alias, func) in _game_one_liners(src).items() if alias in local}


def _import_target(node: ast.ImportFrom, path: Path) -> str:
    """`from … import` 的模組全名（相對的照檔案的位置算：tianxia/features/bout/x.py 的 `from ..core.a import b` → tianxia.core.a）。"""
    if not node.level:
        return node.module or ""
    package = list(path.relative_to(ROOT).with_suffix("").parts[:-1])
    base = package[:len(package) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


@functools.lru_cache(maxsize=None)
def old_aliases() -> dict[str, frozenset[str]]:
    """舊名的別名（開發規範手冊 3.11：tianxia/<舊名>.py 只寫 `from tianxia.features.<包> import <模組> as _x` 與
    `sys.modules[__name__] = _x`）：包裡的模組全名 → 指到它的舊名（{"tianxia.features.bout.duel_rules": {"duel"}, …}；出陣包也有一個
    duel_rules，舊名是 sortie_duel，所以照全名分）。照語法樹讀、不 import。"""
    found: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(TIANXIA.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "sys.modules[__name__]" not in src:
            continue
        tree = _parse(src)
        for node in (tree.body if tree else []):
            if isinstance(node, ast.ImportFrom) and _import_target(node, path).startswith("tianxia.features."):
                for a in node.names:
                    found[f"{_import_target(node, path)}.{a.name}"].add(path.stem)
    return {k: frozenset(v) for k, v in found.items()}


@functools.lru_cache(maxsize=None)
def core_reexports(module: str) -> dict[str, frozenset[str]]:
    """tianxia/core/<module>.py 的名字被別的模組照抄出去（`from tianxia.core.<module> import 名字`：包把留在核心的那一半 re-export
    同一批函式物件，例：單挑包的 duel_rules、arena_rules 照抄 duel_base、arena_ranks）→ {名字: {照抄的模組名, 指到它的舊名別名}}。
    測試經這幾個字寫（duel.push_of、arena.title_for、`from tianxia import duel as duel_rules`）也算寫到核心的那個名字（全部拆包第 12 批
    審查修正）。整個模組 import 進來的（`from .core import duel_base as duel_rules`）不算：那一份寫得到模組名。照語法樹讀、不 import。"""
    found: dict[str, set[str]] = collections.defaultdict(set)
    target = f"tianxia.core.{module}"
    for path in sorted(TIANXIA.rglob("*.py")):
        if "tests" in path.relative_to(TIANXIA).parts or path.parent == TIANXIA / "core":
            continue
        src = path.read_text(encoding="utf-8")
        if module not in src:
            continue
        tree = _parse(src)
        for node in (tree.body if tree else []):
            if isinstance(node, ast.ImportFrom) and _import_target(node, path) == target:
                for a in node.names:
                    if a.name != "*" and (a.asname or a.name) == a.name:
                        dotted = ".".join(path.relative_to(ROOT).with_suffix("").parts)
                        found[a.name] |= {path.stem} | old_aliases().get(dotted, frozenset())
    return {k: frozenset(v) for k, v in found.items()}


def names_through(words, name: str, text: str) -> bool:
    """這一份原始碼經照抄的模組（words：duel_rules、duel……）寫到 name：寫成 `<字>.<name>`，或從那個模組 import 了 name。
    只看兩個字寫在同一個檔裡不算：duel、arena 是到處都有的字（p.duel、config.arena）。"""
    alt = "|".join(re.escape(w) for w in sorted(words))
    if not alt:
        return False
    if re.search(rf"\b(?:{alt})\.{re.escape(name)}\b", text):
        return True
    return any(re.search(rf"\b{re.escape(name)}\b", m.group(1))
               for m in re.finditer(rf"from\s+[\w.]*\b(?:{alt})\s+import\s+(\([^)]*\)|[^\n]*)", text))


def _core_spans(src: str) -> list[tuple[str, int, int, object]]:
    """核心模組最外層的 def、class 與常數（FREE_TEXT_OPTION = …，照第一個名字；同 conftest_picks）：（名字, 起, 迄, 節點）。"""
    tree = _parse(src)
    out = []
    for n in (tree.body if tree else []):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((n.name, *_span(n), n))
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            names = [t.id for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)]
            if names:
                out.append((names[0], n.lineno, n.end_lineno or n.lineno, n))
    return out


def _core_refs(old_src: str, new_src: str) -> tuple[dict[str, set[str]], set[str], dict[str, set[str]]]:
    """（名字 → 它用到的最外層名字, 哪些是函式, 名字 → 模組裡用到它的）：新舊兩份的聯集。"""
    refs: dict[str, set[str]] = collections.defaultdict(set)
    funcs: set[str] = set()
    for src in (old_src, new_src):
        for name, _, _, node in _core_spans(src):
            refs[name] |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} - {name}
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.add(name)
    users: dict[str, set[str]] = collections.defaultdict(set)
    for name, ids in refs.items():
        for i in ids & set(refs):
            users[i].add(name)
    return refs, funcs, users


def _callers_up(seed: str, users: dict[str, set[str]]) -> set[str]:
    """seed 連模組裡直接叫它、用到它的，一路往上。"""
    seen, todo = {seed}, [seed]
    while todo:
        for u in users.get(todo.pop(), ()):
            if u not in seen:
                seen.add(u)
                todo.append(u)
    return seen


def core_module_callers(module: str, hunk_list: list[Hunk], old_src: str,
                        new_src: str) -> tuple[set[Path], list[str]]:
    """tianxia/core/<module>.py 的 hunk → （寫到改到的名字的測試檔, 為什麼）；核心測試＋煙霧另外一定加。
    hunk 落在哪個最外層的函式、類別、常數 → 連模組裡直接叫它、用到它的（一路往上：只有 answer_event 在叫的 answer_branch、
    deed_credit 沒留委派，照 answer_event 挑；經 ctx.<委派> 叫的不算）→ 每一個的：
    - 函式：Game 上委派給它的方法名（_present、_choose、answer_event；照 engine.py 認，core_delegates），加上模組名與函式名寫在
      同一個檔裡的（函式名本身太常見：present、apply），再加經照抄它的模組或那個模組的舊名寫的（`duel.push_of`、`arena.title_for`：
      core_reexports、names_through；全部拆包第 12 批審查修正）；
    - 類別、常數：那個識別字（EVIL_ANNAL、FreeTextRequest：engine 照名字 import 回來，測試從 engine 拿）。
    跟 base 沒有差（指名了這個檔）照整個檔算；挑到的超過 IMPORT_CAP 個檔不一個一個挑（只剩核心測試＋煙霧）。說明、import 這種
    函式以外的行不挑。經 choose、探索走、不寫名字的混合檔（test_explore、test_real_content）照第 11 批認定 4 列在模組的說明。"""
    refs, funcs, users = _core_refs(old_src, new_src)
    delegates: dict[str, set[str]] = collections.defaultdict(set)
    for method, (mod, func) in core_delegates(_engine_src()).items():
        if mod == module:
            delegates[func].add(method)
    whole = not hunk_list
    seeds = sorted(refs) if whole else sorted(n for n in _split(
        hunk_list, old_src, new_src, lambda s: [x[:3] for x in _core_spans(s)]) if n is not None)
    by_text = _index()
    reexported = core_reexports(module)
    files: set[Path] = set()
    why: list[str] = []
    for seed in seeds:
        seen = _callers_up(seed, users)
        terms: set[str] = set()
        hit: set[Path] = set()
        for n in seen:
            if n in funcs:
                for method in delegates.get(n, ()):
                    terms.add(method)
                    hit |= by_text.get(method, frozenset())
                qualified = by_text.get(n, frozenset()) & by_text.get(module, frozenset())
                if qualified:
                    terms.add(f"{module}.{n}")
                    hit |= qualified
                words = reexported.get(n)
                through = {t for t in by_text.get(n, frozenset()) if words and names_through(words, n, _text(t))}
                if through:
                    terms.add(f"{'／'.join(sorted(words))}.{n}（照抄）")
                    hit |= through
            elif by_text.get(n):
                terms.add(n)
                hit |= by_text[n]
        files |= hit
        if not whole:
            via = sorted(seen - {seed})
            shown = sorted(terms)
            why.append(f"{seed}" + (f"（連模組裡叫它、用到它的 {'、'.join(via[:6])}{'……' if len(via) > 6 else ''}）" if via else "")
                       + (f" → 寫到 {'、'.join(shown[:8])}{'……' if len(shown) > 8 else ''} 的 {len(hit)} 個檔" if hit
                          else " → 沒有測試檔寫到它的名字或委派名"))
    if whole:
        why.append(f"跟 base 沒有差異，照整個檔算：寫到這一份的函式（連模組名）、Game 委派名、類別與常數的 {len(files)} 個檔")
    elif not seeds:
        why.append("改的是說明、import 這些（函式以外）→ 只有核心測試＋煙霧")
    if len(files) > IMPORT_CAP:
        return set(), [*why, f"寫到那幾個名字的測試檔有 {len(files)} 個，太多 → 只有核心測試＋煙霧（其他留給每日整套；要當場驗用 --all）"]
    return files, why


# ── 核心服務檔（第二輪第 75 批；E 波第 79～81、91 批才開檔，規則先寫好，測試用假檔名驗）──────────────
# 這幾個檔裝的是從 Game 搬來的單一功能本體（push_trend、take_stamina_pill……），不是掛鉤：照核心那一條（核心測試＋煙霧＋寫到名字的）
# 改一個函式要跑兩千多條（量：engine 上的 push_trend 2,616 條）。所以 hunk 落在函式、類別、常數上 → 名字的功能群＋這個檔的底＋自己檔名的＋
# 邊界測試（push_trend → test_push*，202 條）。函式以外（import、說明、模組層）或指名了卻沒有差 → 照舊核心測試＋煙霧。
# 寫到那個名字、可是檔名不是這一群的（test_opportunities 442 條只拿 push_trend 當準備動作）不挑：留給閘門，why 寫幾個檔，要當場驗就直接給檔名。
CORE_SERVICES: dict[str, tuple[str, ...]] = {  # 模組 → 這個檔的底（改哪個函式都跑）；開檔的那一批照實調
    # 第 79 批開檔照實量：squad 0 個檔；battle 22、tactics 5、engine 5、encounter、fight、rounds、team 各 1，併起來 36 個（IMPORT_CAP 之內）
    "combat": ("battle", "encounter", "fight", "rounds", "tactics", "team", "engine"),
    # 第 80 批開檔照實量：push 7 個檔沒有一條蓋 goals（test_fronts、test_gentry_allied）、deed_points（test_gentry_ledgers、test_outcomes_answer、test_outcomes_classify）、
    # push_progress、event_progress（test_conquest_flip）、shaped、daily_push_cap（test_season21_daily），而 shaped、resisted_line(s)、goals、deed_points 的名字認不出功能（service_word 空字串），靠底。
    # conquest 7、season21 5、fronts 1、gentry 5、outcomes 6，併起來 31 個（IMPORT_CAP 之內）
    "pushing": ("push", "conquest", "season21", "fronts", "gentry", "outcomes"),
    # 第 80 批開檔照實量：pill 2、stamina 6，併起來 7 個（test_pill_per_day、test_stamina_pill、test_stamina_refill 都在；pill_cap 另外寫到的 test_mall、test_wallet 留閘門）
    "pills": ("pill", "stamina"),
    "status_view": ("status", "jianghu", "explain", "explain2", "fronts"),  # 第 81 批照實調：status、jianghu 各只有 1 個檔，真的在測 status_data 的 test_explain2、test_fronts 原本挑不到
    "page_view": ("jianghu", "shop", "shop2", "journal", "rumor", "front"),  # 第 81 批照實調：test_shop2、test_journal 原本挑不到
    # 第 91 批開檔照實量：scene 1 個檔（test_scene_art）、place 1、marks 5、engine 5，併起來 12 個（IMPORT_CAP 之內）；location_text、_own_ended 的名字認不出功能（service_word 空字串），靠底
    "scene_view": ("scene", "place", "marks", "engine"),
}
# 名字裡這些字不是功能：拿來對測試檔名會誤中（test_free_text、test_real_content、test_for_world、_player_hp_and_cap、_reset_player_for_new_season）
SERVICE_STOP = frozenset({"and", "for", "free", "real", "text", "line", "lines", "core", "new", "set", "get", "day", "daily", "base", "local", "load", "take", "data"})


def word_tests(word: str) -> set[Path]:
    """檔名（test_ 後面照底線拆）有這個字的測試檔。"""
    return {t for t in all_tests() if t.name not in TEXT_BLIND and word in t.stem.split("_")[1:]}


def service_word(name: str) -> str:
    """名字裡第一個有測試檔叫這個字的字（push_trend → push；take_stamina_pill → stamina；pills_left_today → pill）；沒有回空字串。"""
    for part in _parts(name):
        for word in (part, part[:-1]) if part.endswith("s") else (part,):
            if word not in SERVICE_STOP and word_tests(word):
                return word
    return ""


def service_groups(module: str, hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[set[Path], bool, list[str]]:
    """tianxia/core/<服務檔>.py 的 hunk → （測試檔, 要不要核心測試＋煙霧, 為什麼）。"""
    if not hunk_list:
        return set(), True, ["跟 base 沒有差異，照整個檔算 → 核心測試＋煙霧"]
    spots = _split(hunk_list, old_src, new_src, lambda s: [x[:3] for x in _core_spans(s)])
    _, _, users = _core_refs(old_src, new_src)
    by_text = _index()
    files = set().union(*(word_tests(w) for w in CORE_SERVICES[module]))
    why = [f"這個檔的底 {'、'.join(CORE_SERVICES[module])} → {len(files)} 個檔"]
    for seed in sorted(n for n in spots if n is not None):
        seen = _callers_up(seed, users)
        words = {w for w in map(service_word, seen) if w}
        hit = set().union(*(word_tests(w) for w in words)) if words else set()
        files |= hit
        left = set(by_text.get(seed, frozenset())) - files
        why.append(f"{seed}" + (f"（連模組裡用到它的 {len(seen) - 1} 個）" if len(seen) > 1 else "") + (f" → {'、'.join(sorted(words))} 那一群 {len(hit)} 個檔" if words else " → 名字認不出功能")
                   + (f"；寫到 {seed} 的另外 {len(left)} 個檔不挑（留給閘門，要當場驗直接給檔名）" if left else ""))
    core = None in spots or len(files) > IMPORT_CAP
    if None in spots:
        why.append("函式以外（import、說明、模組層）→ 核心測試＋煙霧")
    elif core:
        why.append(f"挑到 {len(files)} 個檔，太多 → 核心測試＋煙霧")
    return files, core, why


# 第二輪第 95 批（第 96 批留的）：content.validate 在函式內叫共用層模組的 check_*、validate_*，module_graph 只讀最外層的 import、
# 共用層又不往上找，改它們挑不到 test_content.py。內容驗證＝模組最外層、名字對、參數有 need 的 def：
# need 要留著，ranks.check_summons、events.check_note、jianfa_numbers._check_100 不是內容驗證。
_CONTENT_CHECK = re.compile(r"_?(?:check|validate)_")


def content_checks(src: str) -> set[str]:
    """這份原始碼最外層的內容驗證（函式名）。"""
    found: set[str] = set()
    for name, _, _, node in _top_level(src):
        if isinstance(node, ast.ClassDef) or not _CONTENT_CHECK.match(name):
            continue
        params = node.args
        if any(a.arg == "need" for a in (*params.posonlyargs, *params.args, *params.kwonlyargs)):
            found.add(name)
    return found


def shared_content_checks(hunk_list: list[Hunk], old_src: str, new_src: str) -> list[str]:
    """共用層模組的 hunk 碰到內容驗證了嗎：碰到的寫成給 why 的句子，沒碰到是空的。沒有 hunk（指名了、跟 base 沒有差）照整個檔算；
    有 hunk 照 hunk 落在哪個最外層的名字，連模組裡用到它的一路往上（改驗證用到的小函式、常數也算）；說明、import 這種名字以外的行不算。"""
    checks = content_checks(old_src) | content_checks(new_src)
    if not checks:
        return []
    if not hunk_list:
        return [f"跟 base 沒有差異，照整個檔算：內容驗證 {'、'.join(sorted(checks))}"]
    _, _, users = _core_refs(old_src, new_src)
    why = []
    for seed in sorted(n for n in _split(hunk_list, old_src, new_src, lambda s: [x[:3] for x in _core_spans(s)]) if n is not None):
        hit = _callers_up(seed, users) & checks
        if hit:
            why.append(f"改到 {seed}，經內容驗證 {'、'.join(sorted(hit))}")
    return why


# ── 殼的 js 照 hunk 挑（第二輪第 95 批）──────────────────────────────
# app.js、main.js 每一條網頁測試都載入，照檔名挑一改就是七十幾個檔。hunk 落在哪個頂層名字或 click 的 case 認得出來就只挑寫到它的；
# 認不出來一律退回原挑法（pick 的 web_route），歸屬只准往挑多的方向錯。寫到名字的測試檔常常不經殼的那個名字走（靠 03:30 的整套兜底），
# 所以固定帶載入檢查與「每個按鈕一個主人」（test_shell_web）、FB-673 掃 web/ 不准出現的字（test_server_bots）、煙霧。
SHELL_HUNK_JS = frozenset({"web/app.js", "web/main.js"})
SHELL_NAME_CAP = 20  # 任一個名字有超過這麼多個測試檔寫到（choose、api、pageJianghu、render……）：不算認得出來，退回原挑法
SHELL_LOAD_TESTS = ("test_shell_web.py", "test_server_bots.py")
_JS_TOP = re.compile(r"^  (?:async )?function (\w+)\s*\(|^  (?:const|let) (\w+)\s*=")
_JS_HANDLER = re.compile(r'^  (?:document|window)\.addEventListener\("')
_JS_CLOSE = re.compile(r"^  [}\])]")
_JS_LEFT = re.compile(r"^(?:  )?\S")
_JS_CASE = re.compile(r'^ {8}case "')
_JS_CASE_EDGE = re.compile(r"^ {8}(?:case|default)\b")  # 認不得的標籤也斷在這裡：後面那幾行落在 span 外，退回原挑法
_JS_LABEL = re.compile(r'case "([\w:-]+)":')


def _js_block_end(lines: list[str], start: int) -> int:
    """頂層那一句從 start 開始，結尾在第幾行（都從 0 算）：碰到縮排兩格的收尾符號結束在那一行，碰到別的縮排兩格或頂格的結束在上一行。
    不能只找收尾那一行：行尾有註解的 `const X = 1; // …`、沒有收尾行的 `const A = cond\\n    ? x\\n    : y;` 都會把後面的名字吞掉，歸屬往挑少的方向錯。"""
    for j in range(start + 1, len(lines)):
        if _JS_CLOSE.match(lines[j]):
            return j
        if _JS_LEFT.match(lines[j]):
            return j - 1
    return len(lines) - 1


def _case_spans(lines: list[str], start: int, stop: int) -> list[tuple[str, int, int]]:
    """事件處理裡縮排八格的 `case "x"`：（case:x, 起, 迄）；連續只有標籤的行、同一行好幾個標籤併成一個（case:a|b）。"""
    out = []
    k = start
    while k < stop:
        if not _JS_CASE.match(lines[k]):
            k += 1
            continue
        first, labels = k, []
        while k < stop and _JS_CASE.match(lines[k]):
            labels += _JS_LABEL.findall(lines[k])
            rest = _JS_LABEL.sub("", lines[k]).strip()
            k += 1
            if rest and not rest.startswith("//"):  # 標籤後面就是程式：這一段從這裡開始
                break
        while k < stop and not _JS_CASE_EDGE.match(lines[k]) and not (lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) < 8):
            k += 1
        if labels:
            out.append(("case:" + "|".join(labels), first + 1, k))
    return out


def shell_spans(src: str) -> list[tuple[str, int, int]]:
    """殼的 js 裡認得出來的位置：（名字, 起, 迄），行號從 1 算。兩支檔的頂層都縮排兩格（包在一個立即執行的函式裡），照縮排認，不解析 js。
    頂層的 function、const、let 是它自己；事件處理（addEventListener）那一段本身不算，裡面的 case 才算，名字 case:<標籤>；
    const 與函式裡的 switch 照函式名、不拆。其他都不算 span（handler 前段、沒有 case 的 handler、頂層的句子）：縮排整個變了就是全部退回，不會挑少。"""
    lines = src.replace("\r\n", "\n").split("\n")
    out: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        top = _JS_TOP.match(lines[i])
        if top or _JS_HANDLER.match(lines[i]):
            end = _js_block_end(lines, i)
            out += [(top.group(1) or top.group(2), i + 1, end + 1)] if top else _case_spans(lines, i + 1, end)
            i = end + 1
        else:
            i += 1
    return out


@functools.lru_cache(maxsize=None)
def _name_writers(name: str) -> frozenset[Path]:
    """內文（連 kit，同 web_text）寫到這個 js 名字的測試檔，假原始碼的不算（TEXT_BLIND）。連字號要擋：report-list 不算寫到 report
    （_index 認不得連字號，不用它）。"""
    word = re.compile(rf"(?<![\w$-]){re.escape(name)}(?![\w$-])")
    return frozenset(t for t in all_tests() if t.name not in TEXT_BLIND and word.search(web_text(t)))


def _js_code(text: str) -> bool:
    s = text.strip()
    return bool(s) and not s.startswith(("//", "/*", "*"))


def shell_js_writers(hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[frozenset[Path] | None, list[str]]:
    """殼的 js 的 hunk → （寫到改到的名字的測試檔, 為什麼）；None 是退回原挑法（沒有 hunk、落在 span 外、任一個名字超過 SHELL_NAME_CAP）。
    只改 span 外的註解或空行落不到任何名字，回空的，只跑固定那幾個。"""
    if not hunk_list:
        return None, ["跟 base 沒有差異，照整個檔算 → 原挑法"]
    groups = _split(hunk_list, old_src, new_src, shell_spans)
    loose = sorted(no for side in groups.pop(None, ([], [])) for no, text in side if _js_code(text))  # _split 的 _meaningful 只認 # 開頭
    if loose:
        return None, [f"第 {loose[0]} 行落在函式與 case 以外 → 原挑法"]
    writers = {label: _name_writers(label) for span in groups
               for label in (span.removeprefix("case:").split("|") if span.startswith("case:") else [span])}
    over = sorted((name, len(hit)) for name, hit in writers.items() if len(hit) > SHELL_NAME_CAP)
    if over:
        return None, [f"{'、'.join(f'{name} 有 {n} 個檔寫到' for name, n in over)}（超過 {SHELL_NAME_CAP}）→ 原挑法"]
    found = frozenset().union(*writers.values())
    if not groups:
        return found, ["只改註解或空行，落不到任何名字"]
    why = [f"改到 {'、'.join(sorted(groups))} → 寫到它們的 {len(found)} 個檔"]
    silent = sorted(name for name, hit in writers.items() if not hit)
    if silent:
        why.append(f"沒有測試寫到 {'、'.join(silent)}，只跑固定那幾個，靠 03:30 的整套")
    return found, why


_CONFTEST_IMPORT = re.compile(r"^[ \t]*from[ \t]+conftest[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)", re.M)
_PARAMS = re.compile(r"\bdef[ \t]+\w+[ \t]*\(([^)]*)\)", re.S)


@functools.lru_cache(maxsize=None)
def _conftest_uses(test: Path) -> frozenset[str]:
    """這個測試檔用到的 conftest 名字：from conftest import 的、conftest.<名字>、函式參數（fixture），
    與 request.getfixturevalue／usefixtures 裡寫的字串。"""
    text = _text(test)
    names: set[str] = set()
    for m in _CONFTEST_IMPORT.finditer(text):
        names.update(n.split()[0] for n in m.group(1).split("#")[0].strip("()").replace("\n", " ").split(",") if n.strip())
    names.update(re.findall(r"\bconftest\.(\w+)", text))
    for m in _PARAMS.finditer(text):
        names.update(re.findall(r"(?:^|,)\s*\*{0,2}(\w+)", m.group(1)))
    if "getfixturevalue" in text or "usefixtures" in text:
        names.update(re.findall(r"[\"'](\w+)[\"']", text))
    return frozenset(names)


def _autouse(node) -> bool:
    return any(isinstance(d, ast.Call) and any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value
                                               for k in d.keywords)
               for d in getattr(node, "decorator_list", []))


def conftest_picks(hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[set[Path], bool, list[str]]:
    """conftest.py 的 hunk → （直接相關的測試檔, 要不要跑煙霧, 為什麼）。手冊 4.3「只跑改到的那幾個測試檔與直接相關的」：
    hunk 落在哪個函式、類別或 fixture → 用到它的測試檔（conftest 裡別的 fixture 或函式用到它的，連那一個的使用者一起）。
    每一條測試都會碰到的（autouse 的 fixture、最外層的 import 與 sys.path）、或用到的檔超過 CONFTEST_CAP 個（content、game
    這種）：一個一個挑等於整套，改跑煙霧，整套留給每日整套。"""
    def spans(src: str) -> list[tuple[str, int, int, object]]:
        """最外層的 def、class 與常數（IDLE_LINE = …，照第一個名字）；import、sys.path 這些不算，落在外面。"""
        tree = _parse(src)
        out = []
        for n in (tree.body if tree else []):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append((n.name, *_span(n), n))
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                names = [t.id for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)]
                if names:
                    out.append((names[0], n.lineno, n.end_lineno or n.lineno, n))
        return out

    tops = {name: (node, src) for src in (old_src, new_src) for name, *_, node in spans(src)}
    sources = {name: ast.get_source_segment(src, node) or "" for name, (node, src) in tops.items()}
    files: set[Path] = set()
    smoke = False
    why: list[str] = []
    for name, _lines in _split(hunk_list, old_src, new_src, lambda src: [s[:3] for s in spans(src)]).items():
        if name is None:
            smoke = True
            why.append("最外層（import、sys.path 這些每一條測試都碰得到）→ 煙霧")
            continue
        todo, seen = {name}, set()
        while todo:  # conftest 裡誰用到它：一路找上去（_prologue_master → prologue_content）
            n = todo.pop()
            seen.add(n)
            todo |= {other for other, src in sources.items()
                     if other not in seen and other != n and re.search(rf"\b{re.escape(n)}\b", src)}
        label = name
        if any(_autouse(tops[n][0]) for n in seen if n in tops):
            smoke = True
            why.append(f"{label}：autouse 的 fixture（每一條測試都用）→ 煙霧")
            continue
        users = {t for t in all_tests() if _conftest_uses(t) & seen}
        if len(users) > CONFTEST_CAP:
            smoke = True
            why.append(f"{label}：{len(users)} 個測試檔在用，太多 → 煙霧（其他留給每日整套；要當場驗用 --all）")
            continue
        files |= users
        via = sorted(seen - {name})
        why.append(f"{label}" + (f"（連用到它的 {'、'.join(via)}）" if via else "") + f"：用到的 {len(users)} 個測試檔")
    return files, smoke, why


# ── 挑 ───────────────────────────────────────────────────────────────

def pick(files: list[str], base: str | None = None,
         hunks_of: dict[str, tuple[list[Hunk], str, str]] | None = None) -> Pick:
    """要跑的測試（挑的時候不管 slow：要不要連 slow 一起跑是 pytest_commands 的事）。hunks_of 給測試用：
    {"tianxia/engine.py": ([(拿掉的行, 加上的行)…], 舊原始碼, 新原始碼)}，沒給就問 git（跟 base 比，預設 default_base()）。"""
    base = base or default_base()
    tests = all_tests()
    named = {t.name: t for t in tests}
    result = Pick()

    def own_named(mod: str) -> set[Path]:
        return {t for t in tests if t.stem == f"test_{mod}" or t.stem.startswith(f"test_{mod}_")}

    def content_route(path: Path) -> None:
        # test_real_content.py 147 條只有整季那 11 條是 slow：其他的（事件難度帶 DIFFICULTY_BANDS、地點走得到……）照
        # 「不含 slow」跟著跑，約 25 秒；整季那幾條 --slow 才跑（手冊 4.3 不要的是用真實內容跑整季）
        for name in (CONTENT_TEST, REAL_CONTENT_TEST, PACK_CONTENT_TEST):
            if name in named:
                result.files.add(named[name])
        result.files |= {t for t in tests if path.name in _text(t)}

    def core_and_smoke() -> None:
        result.core = result.smoke = True

    for raw in files:
        f = raw.replace("\\", "/")
        path = Path(f)
        if path.name == "conftest.py" and (f.startswith("tests/") or f.startswith("tianxia/features/")):
            given = (hunks_of or {}).get(f)
            hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
            if not hunk_list:  # 指名了、可是跟 base 沒有差
                result.smoke = True
                result.why.append(f"{f}：跟 base 沒有差異，照整個檔算 → 煙霧")
                continue
            found, smoke, why = conftest_picks(hunk_list, old_src, new_src)
            result.files |= found
            result.smoke |= smoke
            result.why.extend(f"{f}：{w}" for w in why)
            continue
        if f in SETUP_FILES:
            result.why.append(f"{f}：測試設定，不挑（整套留給每日整套；要當場驗用 --all）")
            continue
        if f.startswith("tests/fixtures/"):
            hit = {t for t in tests if path.name in _text(t)}
            result.files |= hit
            result.why.append(f"{f}：寫到 {path.name} 的 {len(hit)} 個檔")
            continue
        if f.startswith("tianxia/features/") and path.parts[3:5] == ("tests", "content"):  # core_content：包裡的測試內容（第 63 批），不補就落進下面那一支、什麼都挑不到
            hit = {t for t in tests if path.name in _text(t)}
            result.files |= hit | set((FEATURES / path.parts[2] / "tests").rglob("test_*.py"))
            if PACK_CONTENT_TEST in named:
                result.files.add(named[PACK_CONTENT_TEST])
            result.why.append(f"{f}：寫到 {path.name} 的 {len(hit)} 個檔＋{path.parts[2]} 這一包的 tests/＋{PACK_CONTENT_TEST}")
            continue
        if f.startswith("tests/") or (f.startswith("tianxia/features/") and "/tests/" in f):
            if path.name.startswith("test_") and path.suffix == ".py":
                if (ROOT / f).exists():
                    result.files.add(ROOT / f)
                    result.own.add(ROOT / f)
            elif (f.startswith("tianxia/features/") and len(path.parts) == 5
                  and path.name == f"{path.parts[2]}_stage.py"):  # 包的擺局面檔：只有契約測試照路徑載入（_stages），沒有人 import 它
                # 算成那一包（第 22 批 PM 認定第 1 條，第 12 批合併時補）：那一包的 tests/＋核心契約，同改包裡的任一檔
                result.files |= set((FEATURES / path.parts[2] / "tests").rglob("test_*.py"))
                result.files |= contract_tests()
                result.contract_only.add(path.parts[2])
                result.why.append(f"{f}：{path.parts[2]} 這一包擺局面的檔（契約測試照路徑載入）→ {path.parts[2]} 這一包的 tests/＋核心契約")
            elif path.suffix == ".py":  # 測試共用的小工具：import 它的測試檔
                result.files |= {t for t in tests if path.stem in reached(t)}
            continue
        if f.startswith("tianxia/features/"):
            parts = f.split("/")
            if parts[3:4] == ["content"]:  # 包裡的內容檔（全部拆包第 62 批）：內容那一條＋下面包那一條
                content_route(path)
            pkg_tests = FEATURES / parts[2] / "tests" if len(parts) > 3 else None
            if pkg_tests is not None:
                result.files |= set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
                result.files |= contract_tests()
                result.contract_only.add(parts[2])
                result.why.append(f"{f}：{parts[2]} 這一包的 tests/＋核心契約")
                if path.name == "checks.py" and len(parts) == 4 and CONTENT_TEST in named:  # PM 定（第二輪 F 波）：包的內容驗證，測試寫在 test_content.py
                    result.files.add(named[CONTENT_TEST])
                    result.why.append(f"{f}：包的內容驗證 → {CONTENT_TEST}")
                if path.name == "game_api.py":  # 第二輪第 72 批：engine 上的一行委派搬進表，照舊併上內文寫到那個名字的測試檔（包外直接叫它的）
                    writers = game_api_callers(f, base, hunks_of)
                    result.files |= writers
                    result.why.append(f"{f}：表上改到的名字 → 寫到它們的 {len(writers)} 個檔")
            else:
                core_and_smoke()
                result.why.append(f"{f}：功能包的登記 → 核心測試＋煙霧")
            continue
        if f.startswith("scripts/sb/"):  # 情境（第二輪第 70 批）：照下面的檔名字根挑會挑到 198 個不相干的檔，它們都不讀這些檔
            result.files |= {t for t in tests if t.name == BOUNDARY_TEST}
            result.why.append(f"{f}：情境 → 邊界測試；情境改了跑那一軌的 same_behavior selftest")
            continue
        if f.startswith("scripts/webqa/"):  # 網頁比對工具（第二輪第 77 批）：有 .mjs、.txt，下面 .py 那一條接不到
            result.files |= {t for t in tests if t.name == WEBQA_TEST}
            result.why.append(f"{f}：網頁比對工具 → {WEBQA_TEST}")
            continue
        if f.startswith("tianxia/core/tuning/") and path.suffix == ".py" and (FEATURES / path.stem / "tests").is_dir():  # 新包的 Config 子模型（第二輪第 74 批）：只有那一包讀，不算改核心
            result.files |= set((FEATURES / path.stem / "tests").rglob("test_*.py"))
            result.why.append(f"{f}：{path.stem} 這一包的 Config 子模型 → 那一包的 tests/")
            continue
        if f == "tianxia/core/services_list.md":  # core_api（第二輪第 74 批）：只有邊界測試讀，不算改核心
            result.files |= {t for t in tests if t.name == BOUNDARY_TEST}
            result.why.append(f"{f}：服務清單 → 邊界測試")
            continue
        if f.startswith("tianxia/core/") and path.suffix == ".py" and f == f"tianxia/core/{path.name}" and path.stem in CORE_SERVICES:
            given = (hunks_of or {}).get(f)
            hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
            found, core, why = service_groups(path.stem, hunk_list, old_src, new_src)
            result.files |= found | own_named(path.stem) | {t for t in tests if t.name == BOUNDARY_TEST}
            if core:
                core_and_smoke()
            result.why.extend(f"{f}：{w}" for w in why)
            continue
        if f.startswith("tianxia/core/"):
            core_and_smoke()
            # core-events（第 16 批修正）：掛鉤與清單以外的核心本體，再並上寫到改到的函式名或 Game 委派名的（core_module_callers）
            if path.suffix == ".py" and f == f"tianxia/core/{path.name}" and path.stem not in CORE_LISTS:
                given = (hunks_of or {}).get(f)
                hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
                found, why = core_module_callers(path.stem, hunk_list, old_src, new_src)
                result.files |= found
                result.why.extend(f"{f}：{w}" for w in ["核心 → 核心測試＋煙霧", *why])
                continue
            result.why.append(f"{f}：核心 → 核心測試＋煙霧")
            continue
        if f == "server.py":  # 第 61 批：路由都在包裡，server.py 只剩殼；拆進各包的路由測試（test_*_shell.py）跟著它
            core_and_smoke()
            result.files |= {t for t in tests if t.name == SERVER_TEST or SHELL_TEST.fullmatch(t.name)}
            result.why.append(f"{f}：殼 → 核心測試＋煙霧＋{SERVER_TEST}＋全部 test_*_shell.py")
            continue
        if f in HUNK_FILES:
            given = (hunks_of or {}).get(f)
            hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
            if not hunk_list:  # 指名了、可是跟 base 沒有差：照整個檔算
                core_and_smoke()
                result.why.append(f"{f}：跟 base 沒有差異，照整個檔算 → 核心測試＋煙霧")
                continue
            core, why, packages, callers = engine_groups(hunk_list, old_src, new_src)
            for pkg in sorted(packages):  # 一行委派（第 11 批）：同改那一包的檔
                pkg_tests = FEATURES / pkg / "tests"
                result.files |= set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
            result.files |= callers
            if core:  # 核心測試本來就含核心契約與邊界（CORE_GLOBS）
                core_and_smoke()
            else:  # 核心契約與邊界測試一律帶（第 11 批審查）：Game 新叫了一個包的名字，只有邊界測試的 GAME_* 名單抓得到
                result.files |= contract_tests()
                result.contract_only |= packages
                why = [*why, "engine.py 有改動 → 核心契約與邊界測試（GAME_* 名單只有邊界測試守）"]
            result.why.extend(f"{f}：{w}" for w in why)
            continue
        if path.suffix == ".py" and f.startswith("tianxia/") and path.stem in CORE_MODULES:
            core_and_smoke()
            result.files |= own_named(path.stem)
            result.why.append(f"{f}：核心 → 核心測試＋煙霧＋test_{path.stem}…")
            continue
        # shared（第 15 批）：共用規則層 → 自己檔名的測試＋煙霧＋邊界測試（不跑核心測試、不往上找）
        if path.suffix == ".py" and f == f"tianxia/{path.name}" and path.stem in SHARED_MODULES:
            result.smoke = True
            result.files |= own_named(path.stem) | {t for t in tests if t.name == BOUNDARY_TEST}
            result.why.append(f"{f}：共用規則層 → 自己檔名的測試＋煙霧＋邊界測試（不跑核心測試、不往上找；總表第六節第 5 條）")
            given = (hunks_of or {}).get(f)
            hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
            touched = shared_content_checks(hunk_list, old_src, new_src)
            if touched and CONTENT_TEST in named:
                result.files.add(named[CONTENT_TEST])
                result.why.extend(f"{f}：{w} → {CONTENT_TEST}" for w in touched)
            continue
        if path.suffix == ".py" and (f.startswith("tianxia/") or f.startswith("scripts/") or "/" not in f):
            mod = path.stem
            first = _first_word(mod)  # mingtie_card 也挑 test_mingtie.py（檔名是模組名的第一個字）
            result.files |= {t for t in tests if mod in reached(t) or t.stem == f"test_{mod}"
                             or t.stem.startswith(f"test_{mod}_") or (first != mod and t.stem == f"test_{first}")
                             or (f.startswith("scripts/") and f"{mod}.py" in _text(t))}
            if f == f"tianxia/{path.name}":
                ups = dependents(mod)
                if ups:
                    via = {t for t in tests if reached(t) & ups} - result.files
                    if len(via) > IMPORT_CAP:
                        core_and_smoke()
                        result.why.append(f"{f}：依賴它的模組有 {len(ups)} 個、import 它們的測試檔 {len(via)} 個，太多"
                                          " → 直接 import 它的＋核心測試＋煙霧（其他留給每日整套；要當場驗用 --all）")
                    elif via:
                        result.files |= via
                        shown = sorted(ups)
                        result.why.append(f"{f}：經 {'、'.join(shown[:8])}{'……' if len(shown) > 8 else ''}"
                                          f"（依賴它的 {len(ups)} 個模組）再挑到 {len(via)} 個檔")
                for kind in registered_actions(mod):
                    hit = action_files(kind)
                    result.files |= hit
                    result.why.append(f"{f}：engine 為了登記才 import 它（動作 {kind}）→ 寫到 \"{kind}\" 的 {len(hit)} 個檔")
            continue
        if f.startswith("content/"):
            content_route(path)
            continue
        owner = feature_web().get(path.name) if f.startswith("web/") and f.count("/") == 1 else None
        if owner is not None:  # 功能包的網頁檔（web/mall.js）：那一包的 tests/＋核心契約，不照 app.js 挑（PM 10/31）
            pkg_tests = FEATURES / owner / "tests"
            pkg_files = set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
            result.files |= pkg_files
            result.files |= contract_tests()
            result.contract_only.add(owner)
            # 寫到那個檔名的（店面的 CSS 守門讀包的樣式）：整個檔名，「mall.js」不算「mall.json」裡的那一段
            exact = re.compile(rf"(?<![\w.]){re.escape(path.name)}(?!\w)")
            named_it = {t for t in tests if t.name not in TEXT_BLIND and exact.search(web_text(t))}
            result.files |= named_it
            others = sorted(t.name for t in named_it if not t.is_relative_to(pkg_tests))
            # 包的 js 只有包裡用假瀏覽器（webharness 載入 APP_FILES）跑整支頁面的測試會真的執行它，而那種測試常整個檔標 slow
            # （test_mall_web）：照「不含 slow」挑等於沒有一條在跑它（10/31 審查：插一行 function ((( 照預設 134 passed）。
            # 那幾個連 slow 一起跑，跟改到的測試檔一樣；樣式表不是 webharness 跑的，照舊。
            runs_js = {t for t in pkg_files if "webharness" in reached(t)} if path.suffix == ".js" else set()
            result.runs_js |= runs_js
            result.why.append(f"{f}：{owner} 這一包的網頁檔 → 那一包的 tests/＋核心契約"
                              + (f"＋寫到 {path.name} 的 {'、'.join(others)}" if others else "")
                              + (f"；跑它的網頁測試 {'、'.join(sorted(t.name for t in runs_js))} 連 slow 一起跑"
                                 if runs_js else ""))
            continue
        if f.startswith("web/"):
            if f in SHELL_HUNK_JS:  # 第二輪第 95 批：殼的 js 認得出 hunk 落在哪個名字就只挑寫到它的，認不出來走下面的原挑法
                given = (hunks_of or {}).get(f)
                hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
                writers, why = shell_js_writers(hunk_list, old_src, new_src)
                result.why.extend(f"{f}：{w}" for w in why)
                if writers is not None:
                    load = {named[n] for n in SHELL_LOAD_TESTS if n in named}
                    result.smoke = True
                    result.files |= writers | load
                    # 寫到名字又整檔 slow 的網頁測試：不連 slow 一起跑，挑到了也一條不跑（同包的 js 那一支，10/31 審查）
                    runs_js = {t for t in writers if whole_slow(t) and "webharness" in reached(t)}
                    result.runs_js |= runs_js
                    result.why.append(f"{f}：固定帶 {'、'.join(sorted(t.name for t in load))}＋煙霧"
                                      + (f"；跑它的網頁測試 {'、'.join(sorted(t.name for t in runs_js))} 連 slow 一起跑" if runs_js else ""))
                    continue
            if SERVER_TEST in named:
                result.files.add(named[SERVER_TEST])
            # 江湖頁（main.js）是從 app.js 切出來的：測試照舊寫「app.js」，也算寫到它們（走一趟的 outing.js 是探索包的、輿圖的 map.js 是輿圖包的〔第 49 批〕，上面那一支）
            names = {path.name, "app.js"} if path.name in WEB_SCRIPTS else {path.name}
            result.files |= {t for t in tests if any(n in web_text(t) for n in names)}
            continue
        result.why.append(f"{f}：不是程式、內容或測試，不跑")
    return result


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def targets(chosen: Pick, leave_out: frozenset[Path] = frozenset()) -> list[str]:
    """交給 pytest 的路徑與測試 id（相對 ROOT），重複的拿掉；leave_out 的檔（另外一次跑）連核心測試、煙霧裡的都拿掉。"""
    if chosen.everything:
        return ["tests", *(["tianxia/features"] if FEATURES.is_dir() else [])]
    files = (set(chosen.files) | (set(core_tests()) if chosen.core else set())) - set(leave_out)
    out = sorted(_rel(p) for p in files)
    if chosen.smoke:
        have = set(out) | {_rel(p) for p in leave_out}
        out += [i for i in smoke_ids() if i.split("::")[0] not in have]
    return out


def _slow_split(chosen: Pick, slow: bool) -> list[tuple[list[str], str]]:
    """（目標, -m 的式子）一次或兩次。改到的測試檔本身（own）連 slow 一起跑——改了就是要跑它（手冊 4.3「只跑改到的
    那幾個測試檔」）；執行改到的包 js 的網頁測試（runs_js）也是；其他挑到的照舊不含 slow（--slow 才含）。
    那幾個檔裡沒有 slow 的就一次跑完。"""
    if chosen.everything or slow:
        return [(targets(chosen), "slow or not slow")]
    mine = chosen.with_slow
    if not any(has_slow(p) for p in mine):
        return [(targets(chosen), "not slow")]
    rest = targets(chosen, leave_out=frozenset(mine))
    runs = [(rest, "not slow")] if rest else []
    return runs + [(sorted(_rel(p) for p in mine), "slow or not slow")]


def per_package_contract_tests(path: Path) -> list[str]:
    """test_contract_features.py 裡逐包參數化的測試（@pytest.mark.parametrize("feature", …)）。照語法樹讀。"""
    found = []
    for node in _ast(_text(path)).body:
        if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "parametrize"
                and d.args and isinstance(d.args[0], ast.Constant) and d.args[0].value == "feature" for d in node.decorator_list):
            found.append(node.name)
    return found


def _contract_deselect(chosen: Pick, goal: list[str]) -> list[str]:
    """逐包的核心契約只留 chosen.contract_only 那幾包的 --deselect。改核心、改到契約檔本身、整套都不限。"""
    path = CORE_TESTS / PER_PACKAGE_CONTRACT
    if (chosen.everything or chosen.core or not chosen.contract_only or path in chosen.own or _rel(path) not in goal):
        return []
    others = sorted(p.name for p in FEATURES.iterdir() if (p / "__init__.py").is_file() and p.name not in chosen.contract_only)
    return [f"--deselect={_rel(path)}::{test}[{name}]" for test in per_package_contract_tests(path) for name in others]


def _command(goal: list[str], marker: str, extra: list[str], everything: bool, args_file: Path | None,
             deselect: list[str] = ()) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", marker]
    listed = [*goal, *deselect]
    if args_file is not None and sum(len(g) + 1 for g in listed) > 8000:
        args_file.write_text("\n".join(listed) + "\n", encoding="utf-8")
        cmd.append(f"@{args_file}")
    else:
        cmd += listed
    cmd += extra
    many = everything or len({g.split("::")[0] for g in goal}) >= PARALLEL_FROM
    asked = any(a in ("-n", "--numprocesses", "no:xdist") or a.startswith(("--numprocesses=", "-pno:xdist"))
                or (a.startswith("-n") and not a.startswith("--") and a[2:].isalnum()) for a in extra)
    if many and not asked and importlib.util.find_spec("xdist") is not None:
        cmd += ["-n", WORKERS]
    return cmd


def pytest_commands(chosen: Pick, slow: bool, extra: list[str], tmp: Path | None = None) -> list[list[str]]:
    """跑 pytest 的指令（一個；改到的測試檔有 slow 時兩個，見 _slow_split）。目標太多（Windows 一行最多三萬多字）時
    寫進 tmp 底下的檔，用 pytest 的 @檔名。"""
    return [_command(goal, marker, extra, chosen.everything, None if tmp is None else tmp / f"targets-{i}.txt",
                     _contract_deselect(chosen, goal))
            for i, (goal, marker) in enumerate(_slow_split(chosen, slow))]


def _slow_only(chosen: Pick) -> list[str]:
    """挑到的（連 slow 一起跑的那幾個以外）整個檔標 slow 的：不加 --slow 一條都不跑。"""
    return sorted(_rel(p).removeprefix("tests/") for p in chosen.files - chosen.with_slow if whole_slow(p))


def finish(codes: list[int], chosen: Pick, slow: bool) -> int:
    """幾次 pytest 的結束碼合成一個。一次都沒跑到（5）而且是 slow 濾掉的：說要 --slow，回 0（沒有東西壞）。"""
    bad = [c for c in codes if c not in (0, 5)]
    if bad:
        return bad[0]
    if codes and all(c == 5 for c in codes):
        if not slow and any(has_slow(p) for p in chosen.files):
            print("挑到的測試全在標了 slow 的地方，這一次一條都沒跑。要跑加 --slow"
                  + (f"（整個檔標 slow 的：{' '.join(_slow_only(chosen))}）" if _slow_only(chosen) else "") + "。")
            return 0
        return 5
    return 0


def count(cmd: list[str]) -> str:
    """用 pytest --collect-only 數一共幾條（照 pytest 印的那一行）。"""
    collect = [a for a in cmd if a != "-q"]
    if "-n" in collect:
        i = collect.index("-n")
        del collect[i:i + 2]
    out = subprocess.run([*collect, "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = [line for line in out.stdout.splitlines() if "collected" in line or "no tests" in line]
    return lines[-1].strip() if lines else (out.stdout.strip().splitlines() or ["（數不出來）"])[-1]


def describe(chosen: Pick, slow: bool = False) -> list[str]:
    if chosen.everything:
        return ["整套（含 slow）"]
    lines = []
    files = sorted(_rel(p) for p in chosen.files)
    if files:
        lines.append(f"要跑（{len(files)} 個檔）：" + " ".join(f.removeprefix("tests/") for f in files))
    mine = sorted(_rel(p).removeprefix("tests/") for p in chosen.own if has_slow(p))
    if mine and not slow:
        lines.append("改到的測試檔連 slow 一起跑：" + " ".join(mine))
    web = sorted(_rel(p).removeprefix("tests/") for p in chosen.runs_js - chosen.own if has_slow(p))
    if web and not slow:
        lines.append("執行改到的包 js 的網頁測試連 slow 一起跑：" + " ".join(web))
    if _slow_only(chosen) and not slow:
        lines.append("整個檔標 slow、這一次不跑（要跑加 --slow）：" + " ".join(_slow_only(chosen)))
    if not chosen.everything and _contract_deselect(chosen, targets(chosen)):
        lines.append(f"核心契約逐包那幾條只跑 {'、'.join(f'[{n}]' for n in sorted(chosen.contract_only))}（別的包那幾格留給整套與閘門）")
    if chosen.core:
        lines.append(f"核心測試：核心模組自己的測試＋test_engine，不含 slow（{len(core_tests())} 個檔）")
    if chosen.smoke:
        lines.append(f"煙霧：標了 smoke 的 {len(smoke_ids())} 條")
    if chosen.why:
        lines.append("為什麼：")
        lines += [f"  {w}" for w in chosen.why]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="改了哪些檔就跑哪幾條測試")
    parser.add_argument("files", nargs="*", help="改過的檔（沒給就問 git）")
    parser.add_argument("--list", action="store_true", help="只列出要跑的、為什麼，不跑")
    parser.add_argument("--count", action="store_true", help="再用 pytest --collect-only 數一共幾條（不跑）")
    parser.add_argument("--slow", action="store_true", help="挑到的連 slow 一起跑（例：內容改了連 test_real_content 的整季）")
    parser.add_argument("--all", action="store_true", help="整套，含 slow（上 main 之前用）")
    parser.add_argument("--base", default=None,
                        help=f"跟哪一條分支比（預設 {DEFAULT_BASE}；環境變數 {BASE_ENV} 蓋過預設，--base 再蓋過它）")
    argv = sys.argv[1:] if argv is None else argv
    extra = argv[argv.index("--") + 1:] if "--" in argv else []  # -- 之後的原樣交給 pytest（例：-- -x -k fusion）
    args = parser.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if args.all:
        chosen = Pick(everything=True)
    else:
        base = args.base or default_base()
        source = "--base" if args.base else (BASE_ENV if os.environ.get(BASE_ENV, "").strip() else "預設")
        line, forked = base_line(base, source)
        print(line, flush=True)
        if not forked:
            print(NO_FORK, flush=True)
            return NO_FORK_EXIT
        chosen = pick(args.files or changed_files(base), base=base)
    if chosen.empty:
        print("這些改動挑不到要跑的測試（為什麼寫在下面）。要跑整套用 --all。")
        for w in chosen.why:
            print(f"  {w}")
        return 0
    print("\n".join(describe(chosen, args.slow)), flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmds = pytest_commands(chosen, args.slow, extra, Path(tmp))
        if args.count:
            for cmd in cmds:
                label = "連 slow 一起跑的那幾個檔" if len(cmds) > 1 and cmd is cmds[-1] else "一共"
                print(f"{label}：" + count(cmd), flush=True)
        if args.list or args.count:
            return 0
        return finish([subprocess.call(cmd, cwd=ROOT) for cmd in cmds], chosen, args.slow)


if __name__ == "__main__":
    sys.exit(main())
