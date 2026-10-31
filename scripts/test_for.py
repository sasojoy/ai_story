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
- 「核心測試」（過渡期，PM 2026-10-31）＝ 核心模組自己檔名的測試（test_<模組>…；江湖紀錄的 test_journal 不收，
  NOT_CORE_TESTS）＋ tests/core/test_engine*.py
  ＋ tests/core/ 的核心契約、邊界、錢包服務測試（CORE_GLOBS），不含 slow；「煙霧」＝ 標了 @pytest.mark.smoke 的
  （每個區塊約 10 條）。
- tianxia/features/<包>/**：那一包的 tests/ ＋ 核心契約（tests/core/test_contract*.py 與邊界 test_feature_boundaries.py，
  CONTRACT_GLOBS：手冊 4.1 第三級的核心契約含邊界測試，改包最容易踩的就是 import 了別的包）。
- 核心（tianxia/core/**，與 tianxia/core/__init__.py 的 MODULES：手冊 3.1 的 state、models、content、rules、calendar、
  sqlite_world、world_state、characters、accounts、database、team、gender、naming，3.10 的 wallet，PM 10/31 的 journal；
  邊界測試照同一份）：核心測試＋煙霧＋檔名是 test_<模組>… 的。
  state.py、models.py 另外看 hunk 落在哪個類別、哪個欄位：類別名或欄位名帶功能前綴的（mall_tokens → mall）再加那一群。
- tianxia/engine.py：hunk 落在 Game 的哪個方法 → 方法名第一個認得的字當功能群（tavern_seek → tavern；_deliver_seal_results
  → seal）→ 那一群的測試檔。落在 choose、_everyday_options、sync、status_data、__init__、換季重設、清失效參照這幾個共用方法
  （SHARED_METHODS）、方法以外、或方法名認不出功能 → 看 hunk 裡提到哪些功能前綴；都沒有 → 核心測試＋煙霧。
  落在手冊 3.3 列為 ctx 的共用服務（CORE_METHODS：_log、_write、_save_season、_side、_pill_day……）→ 核心測試＋煙霧
  （名字像功能也一樣），hunk 裡提到的功能前綴另外加。
- server.py：hunk 落在哪條路由 → 路由前綴（/api/mall → mall）那一群＋tests/server/test_server.py；
  /api/do、/api/choose 這種不帶功能的路由看 hunk 裡提到什麼；殼（登入、鎖、路由以外）→ 核心測試＋煙霧＋test_server.py。
- 「功能群的測試檔」＝ 檔名（test_ 後面照底線拆）有那個字的（test_tavern.py、test_tavern_web.py），
  加上內文叫最多的是那一群的（至少 DOMINANT_MIN 次；走一趟 outing_* 的引擎測試叫 test_explore_one*）；
  兩樣都沒有的群（feast、road、ambush……）改用內文叫到那一群方法（.feast_open(）或寫到那一群選項 id（"feast:）的。
  內文是假原始碼的（test_test_for，TEXT_BLIND）不照內文歸群。
- 其他 tianxia/<模組>.py、run_bots.py、scripts/<腳本>.py：直接 import 它的測試檔，加上檔名是 test_<模組>… 的、檔名是模組名
  第一個字的（mingtie_card → test_mingtie.py）（「import 了 engine」不再算相關：engine.py 照上面那一條）。
  tianxia/<模組>.py 另外照模組之間最外層的 import 往上找（dependents；10/31 測試自檢 T-02：改 might.py 以前挑 0 個檔）：
  import 任何依賴它的模組的測試檔也挑；engine 與假人三支（DRIVERS）、核心模組不往上走，彙整的模組（自己 import 至少
  AGGREGATOR_FANOUT 個的：skillview、world……）算、不往上走；往上找到的超過 IMPORT_CAP 個檔（tactics、zh 這種底層的）改加
  核心測試＋煙霧。engine 只為了登記才 import 的（from . import wanted as _wanted_card  # noqa: F401）照它登記的動作名
  （social.register(CardAction(id=KIND))：wanted、mingtie）挑寫到 "wanted" 的測試檔＋那一群（registered_actions）。
- content/：test_content.py ＋ test_real_content.py ＋ 寫到那個檔名的測試檔，照舊不含 slow：test_real_content.py 用真實內容
  跑整季的那幾條是 slow（--slow 才跑、每日整套會跑），其他的（事件難度帶 DIFFICULTY_BANDS 的鎖、地點走得到……）每次都跑。
- web/：寫到那個檔名的測試檔（main.js、map.js、outing.js 照 app.js 挑），加上 test_server.py。功能包登記的網頁檔
  （各包 __init__.py 的 web，例 web/mall.js、web/mall.css；feature_web）→ 那一包的 tests/＋核心契約（CONTRACT_GLOBS）
  ＋寫到那個檔名的（店面的 CSS 守門），不照 app.js 挑、不加 test_server.py（PM 2026-10-31）。包的 js 另外：包裡用假瀏覽器
  （webharness）跑整支頁面、真的執行它的網頁測試（test_mall_web）連 slow 一起跑，跟改到的測試檔一樣（runs_js）。
- tests/ 裡的測試檔：跑它自己，連 slow 一起（改了就是要跑它；挑到的其他檔照舊不含 slow，所以分兩次跑）；
  tests/kit/ 這類共用工具：import 它的測試檔；tests/fixtures/：寫到那個檔名的測試檔。
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
# 功能包的 js（mall.js）也在 APP_FILES 裡，可是照那一包挑（feature_web）；test_test_for 守 WEB_SCRIPTS ∪ 各包的 js == APP_FILES
WEB_SCRIPTS = {"main.js", "map.js", "outing.js", "app.js"}
SETUP_FILES = {"pyproject.toml", "requirements.txt", "requirements-dev.txt"}  # conftest.py 另外照 hunk 挑（conftest_picks）
CONFTEST_CAP = 50  # conftest 改到的名字有超過這麼多個測試檔在用（content、game、real_content）：不一個一個挑，跑煙霧
# 跟哪一條分支比：PM 2026-10-31 起預設 origin/develop（大家從 develop 開）；環境變數 TIANXIA_TEST_BASE 蓋過預設、
# --base 再蓋過它（功能分支的工作樹照舊給 --base origin/feature/<名字>）。default_base() 每次現讀環境變數。
DEFAULT_BASE = "origin/develop"
BASE_ENV = "TIANXIA_TEST_BASE"
REAL_CONTENT_TEST = "test_real_content.py"  # 內容改了就跟（不含 slow）；用真實內容跑整季的那幾條是 slow，--slow 才跑
SERVER_TEST = "test_server.py"

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
# 核心模組裡、自己檔名的測試不收進「核心測試」的：江湖紀錄的 test_journal（76 條）。PM 10/31 定的核心測試是手冊 3.1 那十三個
# 自己的測試＋test_engine＋契約、邊界、錢包（CORE_GLOBS），journal 算核心是同一天邊界測試那一條定的；收進來改 models.py 一個
# 欄位的底數從 1,517 再漲到約 1,593，要不要收等 PM 跟 < 1,500 一起定。改 journal.py 照舊跑它（自己檔名的測試）。
NOT_CORE_TESTS = frozenset({"journal"})
# 「核心測試」除了核心模組自己檔名的，再收 tests/core/ 底下這幾種（core_tests）：Game 門面、核心契約、邊界、錢包服務
CORE_GLOBS = ("test_engine*.py", "test_contract*.py", "test_feature_boundaries.py", "test_wallet.py")
# 功能包改了跟著那一包跑的「核心契約」（tests/core/ 底下；手冊 4.1 第三級：選項帶前綴、choose 不吃別包的、關著不給、換季、邊界）
CONTRACT_GLOBS = ("test_contract*.py", "test_feature_boundaries.py")
HUNK_FILES = {"tianxia/engine.py", "tianxia/models.py", "tianxia/state.py", "server.py"}  # 看 hunk 落在哪裡的四個大檔
# 大家都插一段的 Game 方法（手冊第一節量到的）：落在這裡不看方法名，看 hunk 裡提到哪些功能前綴
SHARED_METHODS = {
    "choose", "_everyday_options", "sync", "status_data", "__init__",
    "_reset_player_for_new_season", "_drop_stale_references", "options", "new",
}
# 共用服務（手冊 3.1「共用服務（記錄、花費、錢包、時刻）」、3.3 的 ctx 清單）：每一個都被叫幾十上百次，改到就是改核心
# → 核心測試＋煙霧（hunk 裡提到的功能前綴另外加）。名字像功能（_save_season、_pill_day、_guide、_wallet）也不照名字分群。
# tests/core/test_test_for.py 守這裡的每一個都還是 Game 的方法。
CORE_METHODS = {
    "_log", "_write", "_save_season", "_side", "_pill_day", "_cost_option", "stamp", "_guide", "_quick_client",
    "_wallet",
}
# 不是功能前綴的字：方法名第一個字是它的（_deliver_seal_results、apply_tavern_chatter、_can_x）往後找下一個認得的字，
# hunk 裡出現它也不算。寫在這裡的字有自己的測試檔名也不算（test_for、test_in_lock_model_timeout、test_real_content……）。
# 挑多一點沒關係，挑漏了每日整套會抓到（手冊二之 3「偶爾晚一點才知道別處壞了，可以接受」）；看 --list 的「為什麼」調這兩張表。
GENERIC = {
    # 核心的模組與物件：到處都會寫到
    "self", "game", "state", "world", "content", "config", "rules", "models", "team", "calendar", "gender", "naming",
    "characters", "accounts", "database", "engine", "server", "core", "sqlite", "api", "now", "options", "option",
    "choose", "sync", "status", "player", "players", "kind", "arg", "args", "id", "ids", "text", "line", "lines",
    "power", "step", "week", "tier", "tiers", "order", "card", "day", "daily", "mark", "four",
    # 一般的動詞（方法名的第一個字是動詞時，功能在後面：_deliver_seal_results → seal、_settle_siege → siege）
    "can", "is", "at", "own", "owned", "set", "check", "checked", "drop", "take", "record", "file", "view", "add",
    "write", "open", "count", "read", "act", "call", "calls", "say", "run", "restore", "present", "carry", "hold",
    "lose", "play", "depart", "finish", "make", "load", "use", "shows", "log", "reset", "share", "shared", "switch",
    "tick", "fold", "highlight", "watch", "begin", "surface", "hear", "backfill", "join", "seek", "deliver", "apply",
    "settle", "advance", "move", "mutate", "submit", "skip", "remove", "auto", "decline", "cancel", "cancelled",
    "rewrite", "tell", "hide", "mirror", "place", "leave", "meet",
    # 一般的名詞、形容詞、介系詞
    "note", "notes", "action", "actions", "save", "free", "in", "name", "init", "quick", "new", "top", "for", "copy",
    "everyday", "close", "cost", "why", "choice", "odds", "prepared", "judged", "here", "home", "mostly", "last",
    "no", "side", "sides", "left", "my", "without", "people", "shaped", "held", "thin", "part", "lead", "when",
    "real", "big", "back", "stamp", "latest", "report", "general", "news", "region", "watching", "absent",
    "fighting", "wild", "standing", "definition", "joinable", "round", "exp", "hp", "solved", "deep", "branches",
    "member", "location", "town", "paused", "method", "phase", "credit", "talked", "famed", "resisted", "nearest",
    "quest", "do", "main", "me", "static", "test", "tests", "web", "app", "index", "stale", "references",
}
# 是功能前綴，可是共用的程式裡到處都寫得到（team.resolve_art、self.world.season、map() 內建函式）：
# 方法名、欄位名是它的照它分群，hunk 裡提到它不算
SCAN_SKIP = {"art", "arts", "season", "map", "xinde"}
# 一個測試檔叫某一群的方法（或寫那一群的選項 id）至少這麼多次、而且是它叫最多的那一群，就算那一群的測試檔（_dominant）。
# 2026-10-31 重放 develop 最近 250 筆改 engine.py 的提交（176 筆同時改了測試檔）：只看檔名時 engine.py 那一份挑法蓋到
# 65 筆的全部被改測試檔，加這一條 81 筆，不含 slow 的條數中位數 152 → 227；把「內文叫到就算」全加進來是 118 筆、
# 中位數 1,204 條（太多：拿 admin_*、practice_* 當準備動作的測試到處都是）。
DOMINANT_MIN = 3
# 內文是假的原始碼、不是在叫那一群的測試檔：不照內文歸群（_dominant 與 group_files 的備案都不算它）。test_test_for 的
# 假 engine 寫了 _tavern_price、_pill_day……，照「內文叫最多」會算進酒肆、pill、season（10/31 審查：每一列多它 31 條）。
# 改 scripts/test_for.py 照舊挑到它（檔名 test_<模組>）。
TEXT_BLIND = frozenset({"test_test_for.py"})


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


# ── tianxia/ 模組之間的 import 圖（10/31 測試自檢 T-02）────────────────
# 只看直接 import 的話，改 might.py 挑不到 test_ascend、test_create_ritual（它們透過 ascend、create 用到 might）。所以照
# tianxia/ 模組之間最外層的 import 往上找：改了 X，import 任何「依賴 X 的模組」的測試檔也算。三種模組不往上走：
# - engine 與假人的三支（DRIVERS：bot、bot_policy、bot_runner，經 Game 什麼都碰）：engine 照它自己那一條（hunk 落在哪個
#   方法）另外挑，「import 了 engine」不算相關；拿 bot 當驅動的測試檔有三十幾個，算進來改 outing.py 也挑到七十幾個檔。
# - 核心模組（CORE_MODULES）：改核心照核心那一條；X 被核心 import，也不把 import 核心的幾百個測試檔算進來。
# - 彙整的模組（自己 import 至少 AGGREGATOR_FANOUT 個 tianxia 模組的：bot、skillview、shopview、world、mapdata……）：
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
        if mod not in _ENGINE_SIDE_IMPORT.findall(engine.read_text(encoding="utf-8")):
            return ()
        tree = _ast((TIANXIA / f"{mod}.py").read_text(encoding="utf-8"))
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
    """寫到動作名字串（"wanted"、'wanted'）的測試檔，加上那個字的功能群（group_files）。"""
    quoted = (f'"{kind}"', f"'{kind}'")
    return {t for t in all_tests() if t.name not in TEXT_BLIND and any(q in _text(t) for q in quoted)} | group_files(kind)


def _parts(ident: str) -> list[str]:
    """一個識別字照底線與大小寫拆開、轉小寫（_tavern_seek → tavern、seek；TavernNote → tavern、note）。"""
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", ident)]


def words(text: str) -> set[str]:
    """一段程式裡的字（self._tavern_seek、TavernNote、"tavern:seek" 都拆出 tavern）。"""
    return {p for ident in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text) for p in _parts(ident)}


def _forms(word: str) -> set[str]:
    """一個字的單複數（bounty／bounties、annal／annals、sortie／sorties）。"""
    forms = {word, word + "s", word + "es"}
    if word.endswith("ies"):
        forms.add(word[:-3] + "y")
    if word.endswith("y"):
        forms.add(word[:-1] + "ies")
    if word.endswith("es"):
        forms.add(word[:-2])
    if word.endswith("s"):
        forms.add(word[:-1])
    return forms


@functools.lru_cache(maxsize=None)
def _index() -> tuple[dict[str, frozenset[Path]], dict[str, frozenset[Path]]]:
    """（檔名的字 → 測試檔, 內文的識別字與選項 id 前綴（"tavern: 記成 tavern:）→ 測試檔）。"""
    by_name: dict[str, set[Path]] = collections.defaultdict(set)
    by_text: dict[str, set[Path]] = collections.defaultdict(set)
    for t in all_tests():
        for tok in t.stem.split("_")[1:]:
            by_name[tok].add(t)
        if t.name in TEXT_BLIND:
            continue
        text = _text(t)
        for ident in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)):
            by_text[ident].add(t)
        for prefix in set(re.findall(r"[\"']([a-z][a-z0-9]*):", text)):
            by_text[prefix + ":"].add(t)
    return ({k: frozenset(v) for k, v in by_name.items()}, {k: frozenset(v) for k, v in by_text.items()})


@functools.lru_cache(maxsize=None)
def _engine_groups() -> dict[str, frozenset[str]]:
    """Game 的方法照第一個字分群：{tavern: {_tavern_open, tavern_do, …}}（用正規式讀方法名，不建語法樹）。"""
    engine = ROOT / "tianxia" / "engine.py"
    groups: dict[str, set[str]] = collections.defaultdict(set)
    text = engine.read_text(encoding="utf-8") if engine.exists() else ""
    start = re.search(r"^class Game\b", text, re.M)
    body = text[start.end():] if start else ""
    end = re.search(r"^(?:class |def |async def |@)", body, re.M)  # Game 後面下一個最外層的 def／class
    for name in re.findall(r"^    (?:async[ \t]+)?def[ \t]+(\w+)", body[: end.start()] if end else body, re.M):
        groups[_first_word(name)].add(name)
    return {k: frozenset(v) for k, v in groups.items()}


def group_files(word: str) -> set[Path]:
    """功能群 word 的測試檔：檔名有那個字的，加上內文叫最多的是這一群的（_dominant：走一趟的方法叫 outing_*，
    引擎測試叫 test_explore_one*）；兩樣都沒有的群，改用內文寫到那一群的 Game 方法名（_feast_menu）
    或那一群的選項 id（"feast:）的。"""
    by_name, by_text = _index()
    hit: set[Path] = set()
    for f in _forms(word):
        hit |= by_name.get(f, frozenset())
    hit |= _dominant().get(word, frozenset())
    if not hit:
        for ident in (*_engine_groups().get(word, ()), word + ":"):
            hit |= by_text.get(ident, frozenset())
    return hit


@functools.lru_cache(maxsize=None)
def _candidates() -> frozenset[str]:
    """可能是功能前綴的字：Game 方法名、tianxia/ 底下模組名的第一個字與功能包的名字，扣掉 GENERIC
    （vocabulary 再扣掉沒有測試檔的）。"""
    found: set[str] = set(_engine_groups())
    found.update(_first_word(p.stem) for p in (ROOT / "tianxia").glob("*.py"))
    if FEATURES.is_dir():
        found.update(p.name for p in FEATURES.iterdir() if p.is_dir() and not p.name.startswith("_"))
    return frozenset(w for w in found - GENERIC if w)


@functools.lru_cache(maxsize=None)
def _dominant() -> dict[str, frozenset[Path]]:
    """測試檔照「內文叫最多的是哪一群」分：數每一群的 Game 方法名（方法名第一個認得的字當群，同 _feature_words）
    與選項 id（"outing:）各出現幾次，最多的那一群（一樣多就都算）至少 DOMINANT_MIN 次才算。
    檔名對不上功能的測試檔靠這一條歸群；只拿別群的方法當準備動作（admin_open_season）的不會被算進那一群。"""
    words_ok = _candidates()
    owner: dict[str, str] = {}
    for methods in _engine_groups().values():
        for m in methods:
            w = next((p for p in _parts(m) if p in words_ok), None)
            if w:
                owner[m] = w
    found: dict[str, set[Path]] = collections.defaultdict(set)
    for t in all_tests():
        if t.name in TEXT_BLIND:
            continue
        text = _text(t)
        tally: collections.Counter[str] = collections.Counter()
        for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
            if ident in owner:
                tally[owner[ident]] += 1
        for prefix in re.findall(r"[\"']([a-z][a-z0-9]*):", text):
            if prefix in words_ok:
                tally[prefix] += 1
        top = max(tally.values(), default=0)
        if top >= DOMINANT_MIN:
            for w, n in tally.items():
                if n == top:
                    found[w].add(t)
    return {k: frozenset(v) for k, v in found.items()}


@functools.lru_cache(maxsize=None)
def vocabulary() -> frozenset[str]:
    """功能前綴：_candidates 裡有測試檔的。"""
    return frozenset(w for w in _candidates() if group_files(w))


def _first_word(name: str) -> str:
    parts = _parts(name)
    return parts[0] if parts else ""


def _feature_words(name: str) -> list[str]:
    """名字裡第一個認得的功能前綴（tavern_seek → tavern；_can_enter_battle → battle；TavernNote → tavern）。"""
    vocab = vocabulary()
    for w in _parts(name):
        if w in vocab:
            return [w]
    return []


def scan(lines: Lines) -> set[str]:
    """hunk 裡提到的功能前綴（共用方法、殼、方法以外用）。"""
    return (words("\n".join(text for _, text in lines)) & vocabulary()) - SCAN_SKIP


def scan_changed(removed: Lines, added: Lines) -> set[str]:
    """方法以外（import 那一串）：只算拿掉或加上的字，不算同一行原本就有的（改一行 import 不會帶出整串模組）。"""
    before = words("\n".join(t for _, t in removed))
    after = words("\n".join(t for _, t in added))
    changed = (before ^ after) or (before | after)
    return (changed & vocabulary()) - SCAN_SKIP


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
    """過渡期的「核心測試」（PM 2026-10-31；跑的時候 -m "not slow"）：核心模組（CORE_MODULES，扣掉 NOT_CORE_TESTS）自己檔名的
    測試（test_<模組>.py、test_<模組>_….py，在哪個資料夾都算：test_naming 在 arts/、test_team 在 battle/）＋
    tests/core/test_engine*.py（Game 門面；第 2 階搬包時屬於包的搬走，條數往下掉）＋ tests/core/ 的核心契約、
    邊界、錢包服務測試（CORE_GLOBS，第 1 階才有）。不再是整個 tests/core/（雜燴：test_social、test_factions……）。"""
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


def engine_groups(hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[set[str], bool, list[str]]:
    """engine.py 的 hunk → （功能群, 要不要核心測試＋煙霧, 為什麼）。"""
    def spans_of(src: str):
        methods = _game_methods(src)
        tops = [(name, start, end) for name, start, end, node in _top_level(src)
                if not (isinstance(node, ast.ClassDef) and name == "Game")]
        return methods + tops

    found: set[str] = set()
    core = False
    why: list[str] = []
    for name, (removed, added) in _split(hunk_list, old_src, new_src, spans_of).items():
        label = name or "方法以外"
        if name in CORE_METHODS:
            hits = scan(removed + added)
            core = True
            found |= hits
            why.append(f"{label}：共用服務（手冊 3.3）→ 核心測試＋煙霧"
                       + (f"，另外提到 {'、'.join(sorted(hits))}" if hits else ""))
            continue
        if name is not None and name not in SHARED_METHODS:
            hit = _feature_words(name)
            if hit:
                found.update(hit)
                why.append(f"{label} → {hit[0]}")
                continue
        hits = scan(removed + added) if name else scan_changed(removed, added)
        if hits:
            found |= hits
            why.append(f"{label} 提到 {'、'.join(sorted(hits))}")
        else:
            core = True
            why.append(f"{label} 沒提到功能前綴 → 核心測試＋煙霧")
    return found, core, why


def fields_groups(hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[set[str], list[str]]:
    """models.py、state.py 的 hunk → （類別名或欄位名帶的功能前綴, 為什麼）；核心測試＋煙霧另外一定加。"""
    def spans_of(src: str):
        return [(name, start, end) for name, start, end, _ in _top_level(src)]

    found: set[str] = set()
    why: list[str] = []
    for name, (removed, added) in _split(hunk_list, old_src, new_src, spans_of).items():
        hits = set(_feature_words(name)) if name else set()
        for _, text in removed + added:  # 欄位名（行首的識別字）帶功能前綴的：mall_tokens: dict → mall
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]", text)
            if m:
                hits.update(_feature_words(m.group(1)))
        hits -= SCAN_SKIP
        if hits:
            found |= hits
            why.append(f"{name or '類別以外'} → {'、'.join(sorted(hits))}")
    return found, why


def _route_paths(node) -> list[str]:
    paths = []
    for d in getattr(node, "decorator_list", []):
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr in {"get", "post", "put", "delete", "patch", "api_route"}
                and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
            paths.append(d.args[0].value)
    return paths


def server_groups(hunk_list: list[Hunk], old_src: str, new_src: str) -> tuple[set[str], bool, list[str]]:
    """server.py 的 hunk → （功能群, 要不要核心測試＋煙霧, 為什麼）；test_server.py 另外一定加。"""
    routes: dict[str, set[str]] = collections.defaultdict(set)

    def spans_of(src: str):
        spans = []
        for name, start, end, node in _top_level(src):
            routes[name].update(_route_paths(node))
            spans.append((name, start, end))
        return spans

    found: set[str] = set()
    core = False
    why: list[str] = []
    for name, (removed, added) in _split(hunk_list, old_src, new_src, spans_of).items():
        paths = sorted(routes.get(name, ())) if name else []
        hits: set[str] = set()
        for p in paths:  # /api/mall/buy → mall；/api/sense_read → sense；/api/do/{op} 認不出 → 看 hunk
            for seg in p.split("/"):
                if seg and not seg.startswith("{"):
                    hits.update(w for w in _parts(seg) if w in vocabulary())
        if name and not paths:
            hits.update(_feature_words(name))
        hits -= SCAN_SKIP
        if not hits:
            hits = scan(removed + added) if name else scan_changed(removed, added)
        label = (f"{name}（{'、'.join(paths)}）" if paths else name) if name else "函式以外"
        if hits:
            found |= hits
            why.append(f"{label} → {'、'.join(sorted(hits))}")
        else:
            core = True
            why.append(f"{label}：殼 → 核心測試＋煙霧")
    return found, core, why


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

    def add_group(found: set[str], source: str) -> None:
        for w in sorted(found):
            hit = group_files(w)
            result.files |= hit
            if not hit:
                result.why.append(f"{source}：{w} 這一群沒有測試檔")

    def own_named(mod: str) -> set[Path]:
        return {t for t in tests if t.stem == f"test_{mod}" or t.stem.startswith(f"test_{mod}_")}

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
        if f.startswith("tests/") or (f.startswith("tianxia/features/") and "/tests/" in f):
            if path.name.startswith("test_") and path.suffix == ".py":
                if (ROOT / f).exists():
                    result.files.add(ROOT / f)
                    result.own.add(ROOT / f)
            elif path.suffix == ".py":  # 測試共用的小工具：import 它的測試檔
                result.files |= {t for t in tests if path.stem in imported(t)}
            continue
        if f.startswith("tianxia/features/"):
            parts = f.split("/")
            pkg_tests = FEATURES / parts[2] / "tests" if len(parts) > 3 else None
            if pkg_tests is not None:
                result.files |= set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
                result.files |= contract_tests()
                result.why.append(f"{f}：{parts[2]} 這一包的 tests/＋核心契約")
            else:
                core_and_smoke()
                result.why.append(f"{f}：功能包的登記 → 核心測試＋煙霧")
            continue
        if f.startswith("tianxia/core/"):
            core_and_smoke()
            result.why.append(f"{f}：核心 → 核心測試＋煙霧")
            continue
        if f in HUNK_FILES:
            given = (hunks_of or {}).get(f)
            hunk_list, old_src, new_src = given if given is not None else hunks(f, base)
            mod = path.stem
            if mod == "server" and SERVER_TEST in named:
                result.files.add(named[SERVER_TEST])
            if mod in ("models", "state"):
                result.files |= own_named(mod)
            if not hunk_list:  # 指名了、可是跟 base 沒有差：照整個檔算
                core_and_smoke()
                result.why.append(f"{f}：跟 base 沒有差異，照整個檔算 → 核心測試＋煙霧")
                continue
            if mod == "engine":
                found, core, why = engine_groups(hunk_list, old_src, new_src)
            elif mod == "server":
                found, core, why = server_groups(hunk_list, old_src, new_src)
            else:
                found, why = fields_groups(hunk_list, old_src, new_src)
                core, why = True, ["核心 → 核心測試＋煙霧", *why]
            if core:
                core_and_smoke()
            add_group(found, f)
            result.why.extend(f"{f}：{w}" for w in why)
            continue
        if path.suffix == ".py" and f.startswith("tianxia/") and path.stem in CORE_MODULES:
            core_and_smoke()
            result.files |= own_named(path.stem)
            result.why.append(f"{f}：核心 → 核心測試＋煙霧＋test_{path.stem}…")
            continue
        if path.suffix == ".py" and (f.startswith("tianxia/") or f.startswith("scripts/") or "/" not in f):
            mod = path.stem
            first = _first_word(mod)  # mingtie_card 也挑 test_mingtie.py（檔名是模組名的第一個字）
            result.files |= {t for t in tests if mod in imported(t) or t.stem == f"test_{mod}"
                             or t.stem.startswith(f"test_{mod}_") or (first != mod and t.stem == f"test_{first}")
                             or (f.startswith("scripts/") and f"{mod}.py" in _text(t))}
            if f == f"tianxia/{path.name}":
                ups = dependents(mod)
                if ups:
                    via = {t for t in tests if imported(t) & ups} - result.files
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
            # test_real_content.py 147 條只有整季那 11 條是 slow：其他的（事件難度帶 DIFFICULTY_BANDS、地點走得到……）照
            # 「不含 slow」跟著跑，約 25 秒；整季那幾條 --slow 才跑（手冊 4.3 不要的是用真實內容跑整季）
            for name in ("test_content.py", REAL_CONTENT_TEST):
                if name in named:
                    result.files.add(named[name])
            result.files |= {t for t in tests if path.name in _text(t)}
            continue
        owner = feature_web().get(path.name) if f.startswith("web/") and f.count("/") == 1 else None
        if owner is not None:  # 功能包的網頁檔（web/mall.js）：那一包的 tests/＋核心契約，不照 app.js 挑（PM 10/31）
            pkg_tests = FEATURES / owner / "tests"
            pkg_files = set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
            result.files |= pkg_files
            result.files |= contract_tests()
            # 寫到那個檔名的（店面的 CSS 守門讀包的樣式）：整個檔名，「mall.js」不算「mall.json」裡的那一段
            exact = re.compile(rf"(?<![\w.]){re.escape(path.name)}(?!\w)")
            named_it = {t for t in tests if t.name not in TEXT_BLIND and exact.search(_text(t))}
            result.files |= named_it
            others = sorted(t.name for t in named_it if not t.is_relative_to(pkg_tests))
            # 包的 js 只有包裡用假瀏覽器（webharness 載入 APP_FILES）跑整支頁面的測試會真的執行它，而那種測試常整個檔標 slow
            # （test_mall_web）：照「不含 slow」挑等於沒有一條在跑它（10/31 審查：插一行 function ((( 照預設 134 passed）。
            # 那幾個連 slow 一起跑，跟改到的測試檔一樣；樣式表不是 webharness 跑的，照舊。
            runs_js = {t for t in pkg_files if "webharness" in imported(t)} if path.suffix == ".js" else set()
            result.runs_js |= runs_js
            result.why.append(f"{f}：{owner} 這一包的網頁檔 → 那一包的 tests/＋核心契約"
                              + (f"＋寫到 {path.name} 的 {'、'.join(others)}" if others else "")
                              + (f"；跑它的網頁測試 {'、'.join(sorted(t.name for t in runs_js))} 連 slow 一起跑"
                                 if runs_js else ""))
            continue
        if f.startswith("web/"):
            if SERVER_TEST in named:
                result.files.add(named[SERVER_TEST])
            # 江湖頁（main.js）、輿圖（map.js）、走一趟（outing.js）是從 app.js 切出來的：測試照舊寫「app.js」，也算寫到它們
            names = {path.name, "app.js"} if path.name in WEB_SCRIPTS else {path.name}
            result.files |= {t for t in tests if any(n in _text(t) for n in names)}
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


def _command(goal: list[str], marker: str, extra: list[str], everything: bool, args_file: Path | None) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", marker]
    if args_file is not None and sum(len(g) + 1 for g in goal) > 8000:
        args_file.write_text("\n".join(goal) + "\n", encoding="utf-8")
        cmd.append(f"@{args_file}")
    else:
        cmd += goal
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
    return [_command(goal, marker, extra, chosen.everything, None if tmp is None else tmp / f"targets-{i}.txt")
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
