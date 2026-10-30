"""改了哪些檔就跑哪幾條測試（開發中用；整套交給每日整套 scripts/nightly.ps1 與上 main 之前）。

用法：
  python scripts/test_for.py                 # 跟 origin/main 比，加上還沒提交的改動
  python scripts/test_for.py --base origin/feature/formal-season   # 在功能分支上跟功能分支比
  python scripts/test_for.py tianxia/fusion.py content/skills.json
  python scripts/test_for.py --list ...      # 只列出會跑哪些、為什麼，不跑
  python scripts/test_for.py --count ...     # 再用 pytest --collect-only 數一共幾條（不跑）
  python scripts/test_for.py --slow          # 挑到的連 slow 一起跑（內容批要當場跑真實內容的整季時用）
  python scripts/test_for.py --all           # 整套（含 slow），上 main 之前用
  python scripts/test_for.py -- -x -k fuse   # -- 之後的參數原樣交給 pytest（-- -n 2 會換掉預設的 -n 4）

怎麼挑（開發規範手冊 4.3，docs/superpowers/specs/2026-10-30-開發模式-design.md）：
- 「核心測試」（過渡期）＝ tests/core/ 不含 slow 的；「煙霧」＝ 標了 @pytest.mark.smoke 的（每個區塊約 10 條）。
- tianxia/features/<包>/**：那一包的 tests/ ＋ tests/core/test_contract*.py。
- 核心（tianxia/core/**、state.py、models.py、content.py、rules.py、calendar.py，與手冊 3.1 列的
  sqlite_world、world_state、characters、accounts、database、team、gender、naming）：核心測試＋煙霧＋檔名是 test_<模組>… 的。
  state.py、models.py 另外看 hunk 落在哪個類別、哪個欄位：類別名或欄位名帶功能前綴的（mall_tokens → mall）再加那一群。
- tianxia/engine.py：hunk 落在 Game 的哪個方法 → 方法名第一個認得的字當功能群（tavern_seek → tavern；_deliver_seal_results
  → seal）→ 那一群的測試檔。落在 choose、_everyday_options、sync、status_data、__init__、換季重設、清失效參照這幾個共用方法
  （SHARED_METHODS）、方法以外、或方法名認不出功能 → 看 hunk 裡提到哪些功能前綴；都沒有 → 核心測試＋煙霧。
- server.py：hunk 落在哪條路由 → 路由前綴（/api/mall → mall）那一群＋tests/server/test_server.py；
  /api/do、/api/choose 這種不帶功能的路由看 hunk 裡提到什麼；殼（登入、鎖、路由以外）→ 核心測試＋煙霧＋test_server.py。
- 「功能群的測試檔」＝ 檔名（test_ 後面照底線拆）有那個字的（test_tavern.py、test_seal_fb643_tavern.py）；
  檔名都沒有的群（feast、road、ambush……）改用內文叫到那一群方法（.feast_open(）或寫到那一群選項 id（"feast:）的。
- 其他 tianxia/<模組>.py、run_bots.py、scripts/<腳本>.py：直接 import 它的測試檔，加上檔名是 test_<模組>… 的
  （「import 了 engine」不再算相關：engine.py 照上面那一條）。
- content/：test_content.py ＋ 寫到那個檔名的測試檔；test_real_content.py 不自動跟（每日整套會跑），--slow 才加。
- web/：寫到那個檔名的測試檔（main.js、map.js 照 app.js 挑），加上 test_server.py。
- tests/ 裡的測試檔：跑它自己；tests/kit/ 這類共用工具：import 它的測試檔；tests/fixtures/：寫到那個檔名的測試檔。
- tests/conftest.py、pyproject.toml、requirements*.txt：不加任何東西（整套留給每日整套）。
- docs/、CLAUDE.md 這類文件：不跑。
slow 不自動跟（--slow 才加，連核心測試的 slow 一起）。挑到三個檔以上預設 -n 4（不寫 auto：同一台常有別的代理在跑），
-- 之後給了 -n 就照給的。"""
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
WEB_SCRIPTS = {"app.js", "main.js", "map.js"}  # 網頁的三個檔（tests/webharness.APP_FILES），index.html 照 main、map、app 的順序載入
SETUP_FILES = {"tests/conftest.py", "pyproject.toml", "requirements.txt", "requirements-dev.txt"}
# 跟哪一條分支比（企劃者 2026-10-18 起功能在功能分支上做：批的工作樹要跟功能分支比，不然越做越多）
DEFAULT_BASE = os.environ.get("TIANXIA_TEST_BASE", "origin/main")
REAL_CONTENT_TEST = "test_real_content.py"  # 用真實內容跑整季（slow）：內容改了不自動跟，--slow 才加
SERVER_TEST = "test_server.py"

# 核心（手冊 3.1、4.3）：改了跑核心測試＋煙霧＋自己檔名的測試，不照「誰 import 它」挑（team、models、state 被一兩百個測試檔 import）
CORE_MODULES = {
    "state", "models", "content", "rules", "calendar",
    "sqlite_world", "world_state", "characters", "accounts", "database", "team", "gender", "naming",
}
HUNK_FILES = {"tianxia/engine.py", "tianxia/models.py", "tianxia/state.py", "server.py"}  # 看 hunk 落在哪裡的四個大檔
# 大家都插一段的 Game 方法（手冊第一節量到的）：落在這裡不看方法名，看 hunk 裡提到哪些功能前綴
SHARED_METHODS = {
    "choose", "_everyday_options", "sync", "status_data", "__init__",
    "_reset_player_for_new_season", "_drop_stale_references", "options", "new",
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


@dataclass
class Pick:
    """挑到的東西。files 整個檔跑（不含 slow，--slow 才含）；core 加核心測試；smoke 加煙霧；everything 是整套。"""
    files: set[Path] = field(default_factory=set)
    core: bool = False
    smoke: bool = False
    everything: bool = False
    why: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.files or self.core or self.smoke or self.everything)


# ── git ──────────────────────────────────────────────────────────────

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def changed_files(base: str = DEFAULT_BASE) -> list[str]:
    """跟 base（預設 origin/main）分岔之後改過的、還沒提交的、還沒加進版控的檔。"""
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
    """功能群 word 的測試檔：檔名有那個字的；檔名都沒有的群，改用內文寫到那一群的 Game 方法名（_feast_menu）
    或那一群的選項 id（"feast:）的。"""
    by_name, by_text = _index()
    hit: set[Path] = set()
    for f in _forms(word):
        hit |= by_name.get(f, frozenset())
    if not hit:
        for ident in (*_engine_groups().get(word, ()), word + ":"):
            hit |= by_text.get(ident, frozenset())
    return hit


@functools.lru_cache(maxsize=None)
def vocabulary() -> frozenset[str]:
    """功能前綴：Game 方法名、tianxia/ 底下模組名的第一個字與功能包的名字，扣掉 GENERIC，而且有測試檔的。"""
    found: set[str] = set(_engine_groups())
    found.update(_first_word(p.stem) for p in (ROOT / "tianxia").glob("*.py"))
    if FEATURES.is_dir():
        found.update(p.name for p in FEATURES.iterdir() if p.is_dir() and not p.name.startswith("_"))
    return frozenset(w for w in found - GENERIC if w and group_files(w))


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
    """過渡期的「核心測試」：tests/core/ 底下的測試檔（跑的時候 -m "not slow"）。"""
    return sorted(CORE_TESTS.glob("test_*.py"))


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


# ── 挑 ───────────────────────────────────────────────────────────────

def pick(files: list[str], base: str = DEFAULT_BASE, slow: bool = False,
         hunks_of: dict[str, tuple[list[Hunk], str, str]] | None = None) -> Pick:
    """要跑的測試。hunks_of 給測試用：{"tianxia/engine.py": ([(拿掉的行, 加上的行)…], 舊原始碼, 新原始碼)}，
    沒給就問 git。"""
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
        if f in SETUP_FILES:
            result.why.append(f"{f}：不加（整套留給每日整套）")
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
            elif path.suffix == ".py":  # 測試共用的小工具：import 它的測試檔
                result.files |= {t for t in tests if path.stem in imported(t)}
            continue
        if f.startswith("tianxia/features/"):
            parts = f.split("/")
            pkg_tests = FEATURES / parts[2] / "tests" if len(parts) > 3 else None
            if pkg_tests is not None:
                result.files |= set(pkg_tests.rglob("test_*.py")) if pkg_tests.is_dir() else set()
                result.files |= set(CORE_TESTS.glob("test_contract*.py"))
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
            result.files |= {t for t in tests if mod in imported(t) or t.stem == f"test_{mod}"
                             or t.stem.startswith(f"test_{mod}_")
                             or (f.startswith("scripts/") and f"{mod}.py" in _text(t))}
            continue
        if f.startswith("content/"):
            if "test_content.py" in named:
                result.files.add(named["test_content.py"])
            result.files |= {t for t in tests if path.name in _text(t) and (slow or t.name != REAL_CONTENT_TEST)}
            if slow and REAL_CONTENT_TEST in named:
                result.files.add(named[REAL_CONTENT_TEST])
            continue
        if f.startswith("web/"):
            if SERVER_TEST in named:
                result.files.add(named[SERVER_TEST])
            # 江湖頁（main.js）、輿圖（map.js）是從 app.js 切出來的（減法季批 0）：測試照舊寫「app.js」，也算寫到它們
            names = {path.name, "app.js"} if path.name in WEB_SCRIPTS else {path.name}
            result.files |= {t for t in tests if any(n in _text(t) for n in names)}
    return result


def targets(chosen: Pick) -> list[str]:
    """交給 pytest 的路徑與測試 id（相對 ROOT），重複的拿掉。"""
    if chosen.everything:
        return ["tests", *(["tianxia/features"] if FEATURES.is_dir() else [])]
    files = set(chosen.files) | (set(core_tests()) if chosen.core else set())
    out = sorted(p.relative_to(ROOT).as_posix() for p in files)
    if chosen.smoke:
        have = set(out)
        out += [i for i in smoke_ids() if i.split("::")[0] not in have]
    return out


def pytest_command(chosen: Pick, slow: bool, extra: list[str], args_file: Path | None = None) -> list[str]:
    """跑 pytest 的指令。目標太多（Windows 一行最多三萬多字）時寫進 args_file，用 pytest 的 @檔名。"""
    goal = targets(chosen)
    marker = "slow or not slow" if (slow or chosen.everything) else "not slow"
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", marker]
    if args_file is not None and sum(len(g) + 1 for g in goal) > 8000:
        args_file.write_text("\n".join(goal) + "\n", encoding="utf-8")
        cmd.append(f"@{args_file}")
    else:
        cmd += goal
    cmd += extra
    many = chosen.everything or len({g.split("::")[0] for g in goal}) >= PARALLEL_FROM
    asked = any(a in ("-n", "--numprocesses", "no:xdist") or a.startswith(("--numprocesses=", "-pno:xdist"))
                or (a.startswith("-n") and not a.startswith("--") and a[2:].isalnum()) for a in extra)
    if many and not asked and importlib.util.find_spec("xdist") is not None:
        cmd += ["-n", WORKERS]
    return cmd


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


def describe(chosen: Pick) -> list[str]:
    if chosen.everything:
        return ["整套（含 slow）"]
    lines = []
    files = sorted(p.relative_to(ROOT).as_posix() for p in chosen.files)
    if files:
        lines.append(f"要跑（{len(files)} 個檔）：" + " ".join(f.removeprefix("tests/") for f in files))
    if chosen.core:
        lines.append(f"核心測試：tests/core/ 不含 slow 的（{len(core_tests())} 個檔）")
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
    parser.add_argument("--slow", action="store_true", help="挑到的連 slow 一起跑（內容改了也加 test_real_content.py）")
    parser.add_argument("--all", action="store_true", help="整套，含 slow（上 main 之前用）")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help="跟哪一條分支比（預設 origin/main，或環境變數 TIANXIA_TEST_BASE）")
    argv = sys.argv[1:] if argv is None else argv
    extra = argv[argv.index("--") + 1:] if "--" in argv else []  # -- 之後的原樣交給 pytest（例：-- -x -k fusion）
    args = parser.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if args.all:
        chosen = Pick(everything=True)
    else:
        chosen = pick(args.files or changed_files(args.base), base=args.base, slow=args.slow)
    if chosen.empty:
        print("這些改動沒有對應的測試（文件之類）。要跑整套用 --all。")
        for w in chosen.why:
            print(f"  {w}")
        return 0
    print("\n".join(describe(chosen)), flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = pytest_command(chosen, args.slow, extra, Path(tmp) / "targets.txt")
        if args.count:
            print("一共：" + count(cmd), flush=True)
        if args.list or args.count:
            return 0
        return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
