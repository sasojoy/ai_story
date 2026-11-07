"""功能包的邊界（開發規範手冊 3.4 第 1 條、3.11）：用 ast 掃 import，幾毫秒。

- 功能包（tianxia/features/<包>/，tests/ 不算）只能 import 核心（tianxia/core/ 與 CORE 那幾個模組）、共用規則層（registry.SHARED，第 11 批）、
  自己這一包、標準庫與第三方；不能 import 別的包。還沒搬的舊模組過渡期可以 import，那一行要註「# 過渡：待搬」（第一版只禁「包 import 包」
  與沒註的舊模組）；註了的那一行要真的有一個還沒搬的舊模組（全是核心、共用規則層的就把註拿掉）。
- 核心不 import 功能包：tianxia/core/ 只有 registry.py（FEATURES 登記）可以，CORE 那幾個模組都不行；共用規則層的模組也不行，
  而且只 import 核心本體與同一層（總表第 15 批：還碰到別的舊模組的那幾條逐條記在 SHARED_PENDING，總表寫了、先不收的在 SHARED_LATER）。
- if TYPE_CHECKING: 底下的 import 只給型別看，不算。
- 網頁框架（fastapi）只有功能包的 routes.py 可以 import，而且只在殼掛路由時延後 import；引擎、run_bots、假人不碰（PM 10/31）。
"""
from __future__ import annotations

import ast
import functools
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # 直接當腳本跑（PM 記過渡處數，見檔尾）時 repo 不在路徑上
    sys.path.insert(0, str(ROOT))
from tianxia.core import MODULES as CORE_MODULES  # noqa: E402
from tianxia.core.registry import SHARED  # noqa: E402  共用規則層（第 11 批）：模組名 → 為什麼在共用層
from boundary_tables import (  # noqa: E402  名單（最後的值）在同一個資料夾的 boundary_tables.py，這個檔只有規則
    ARENA_RANK_READERS, ATLAS_PACKAGE_FIELDS, BUS_METHODS,
    BUS_SUBSCRIBERS, CORE_DELEGATE_CALLERS, CORE_EVENT_DELEGATES,
    COMBAT_CALLED_THROUGH_CTX, COMBAT_VIA_CTX, CORE_COMBAT_DELEGATES, CORE_COMBAT_STATIC_DELEGATES,
    CORE_PILLS_DELEGATES, CORE_PUSHING_DELEGATES, PILLS_VIA_CTX, PUSHING_CALLED_THROUGH_CTX, PUSHING_VIA_CTX,  # core_pushing（第二輪第 80 批）
    CORE_VIEW_DELEGATES,  # core_views
    CORE_TOP_DELEGATE_CALLERS, EFFECT_DEFECT_SCAN, EVENT_CHECK_VIA_CTX,
    GAME_DELEGATE_CALLERS, GAME_DIRECT, GAME_IMPORTS,
    PREPARING_GUARDED, RELAY_OWNERS, RENAMED_PARAMS,
    SHARED_CORE_WORLD2, SHARED_LATER, SHARED_PENDING,
    STEP_PACKAGE_READS,
    # core_api（第二輪第 74 批）
    CROSS_PACKAGE_CALLS,
    # core_bots（第二輪第 89 批）
    BOT_SHELL, BOT_SHELL_PENDING,
)
TIANXIA = ROOT / "tianxia"
FEATURES = TIANXIA / "features"
MARK = "過渡：待搬"

# 核心的模組：tianxia/core/__init__.py 的 MODULES（手冊 3.1 的十三個、3.10 的錢包、PM 10/31 定算核心的江湖紀錄），
# 只有那一份——scripts/test_for.py 也照它挑（10/31 審查：以前這裡跟 test_for 各寫一份，對不上）。
# journal 自己 import front_lines、battlelog（核心 → 舊模組，這一版不掃）
CORE = set(CORE_MODULES)


def _packages() -> list[str]:
    return sorted(p.name for p in FEATURES.iterdir() if (p / "__init__.py").exists())


def _package_files(name: str) -> list[Path]:
    folder = FEATURES / name
    return sorted(p for p in folder.rglob("*.py") if "tests" not in p.relative_to(folder).parts)


def _type_checking_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test) in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            for inner in node.body:
                lines.update(range(inner.lineno, (inner.end_lineno or inner.lineno) + 1))
    return lines


def imports_of(source: str, module: str) -> list[tuple[int, str, bool]]:
    """source（模組 module 的原文）import 了哪些 tianxia 的模組：[(行, 絕對模組名, 那一行有沒有「過渡：待搬」)]。
    from tianxia import a 記成 tianxia.a；相對 import 照 module 算成絕對的。"""
    tree = ast.parse(source)
    lines = source.splitlines()
    skip = _type_checking_lines(tree)
    package = module.rsplit(".", 1)[0]
    out: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)) or node.lineno in skip:
            continue
        text = "\n".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
        marked = MARK in text
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                head = ".".join(base + ([node.module] if node.module else []))
            else:
                head = node.module or ""
            # from x import y：y 可能是模組（from tianxia import mall）也可能是名字；x 本身與 x.y 都記
            names = [head] + [f"{head}.{a.name}" for a in node.names if a.name != "*"]
        out += [(node.lineno, n, marked) for n in names if n == "tianxia" or n.startswith("tianxia.")]
    return out


def _module_exists(name: str) -> bool:
    parts = name.split(".")
    path = ROOT.joinpath(*parts)
    return path.with_suffix(".py").exists() or (path / "__init__.py").exists()


def _is_alias(tree: ast.AST) -> bool:
    """這個模組把自己換成別的模組（sys.modules[__name__] = …）。"""
    return any(isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Subscript) and ast.unparse(t.value) == "sys.modules" and ast.unparse(t.slice) == "__name__"
        for t in node.targets) for node in ast.walk(tree))


def _find_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(TIANXIA.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "sys.modules" not in source or not _is_alias(ast.parse(source)):
            continue
        packages = {mod.split(".")[2] for _, mod, _ in imports_of(source, _modname(path))
                    if mod.startswith("tianxia.features.") and len(mod.split(".")) > 2}
        if len(packages) == 1:
            out[path.stem] = packages.pop()
    return out


def aliases() -> dict[str, str]:
    """舊名留成的別名（3.11 過渡：tianxia/mall.py、tianxia/feasts.py 把 sys.modules 換成包裡的 rules，給還沒改的測試）：舊名 → 包名。
    import 它就是 import 那一包，掃描照那一包算（不然「包 import 包」換個名字就溜過去、還被算成一處過渡）。"""
    global _ALIASES
    if _ALIASES is None:
        _ALIASES = _find_aliases()
    return _ALIASES


_ALIASES: dict[str, str] | None = None


def problems_of(source: str, module: str) -> list[str]:
    """一個功能包的模組違反的地方（空的是乾淨）。"""
    own = module.split(".")[2]
    out: dict[tuple[int, str], str] = {}
    for line, name, marked in imports_of(source, module):
        parts = name.split(".")
        if name == "tianxia" or parts[1] == "core" or parts[1] in CORE or parts[1] in SHARED:
            continue
        if parts[1] in aliases():  # 舊名的別名就是那一包
            target = aliases()[parts[1]]
            if target != own:
                out.setdefault((line, target), f"{module}:{line} 經過別名 tianxia.{parts[1]} import 了別的包 {target}"
                                               f"（要用別包的東西走核心的服務，手冊 3.4）")
            else:
                out.setdefault((line, target), f"{module}:{line} import 了自己這一包的別名 tianxia.{parts[1]}（別名只給還沒改的測試；"
                                               f"包裡用相對 import）")
            continue
        if parts[1] == "features":
            if len(parts) > 2 and parts[2] != own:  # 別的包（還沒建的也算）
                out.setdefault((line, parts[2]), f"{module}:{line} import 了別的包 {parts[2]}（要用別包的東西走核心的服務，手冊 3.4）")
            continue
        if not _module_exists(".".join(parts[:2])):
            continue  # from tianxia import 名字（不是模組）
        if not marked:
            out.setdefault((line, parts[1]), f"{module}:{line} import 了還沒搬的舊模組 {parts[1]}，行尾要註「# {MARK}」（手冊 3.11）")
    return list(out.values())


def _modname(path: Path) -> str:
    """tianxia/features/mall/actions.py → tianxia.features.mall.actions；__init__.py 留著「.__init__」，相對 import 才照那一包算。"""
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def test_feature_packages_only_import_the_core_their_own_package_or_marked_old_modules():
    found = []
    for name in _packages():
        for path in _package_files(name):
            found += problems_of(path.read_text(encoding="utf-8"), _modname(path))
    assert found == []


def feature_target(mod: str) -> str | None:
    """import 的這個模組是哪一包（tianxia.features.<包>…，或舊名的別名）；不是包是 None。"""
    parts = mod.split(".")
    if len(parts) > 2 and parts[:2] == ["tianxia", "features"]:
        return parts[2]
    return aliases().get(parts[1]) if len(parts) > 1 and parts[0] == "tianxia" else None


def _feature_imports(path: Path) -> list[tuple[int, str]]:
    """這個檔 import 了哪幾個功能包的模組：[(行, 模組)]，同一行同一包只記一次（記最長的那個模組名：from .features.mall import actions
    記 tianxia.features.mall.actions；from tianxia.features.mall.rules import reason_text 記 tianxia.features.mall.rules）。"""
    return list(_feature_imports_cached(path))


@functools.lru_cache(maxsize=None)
def _feature_imports_cached(path: Path) -> tuple[tuple[int, str], ...]:
    text = path.read_text(encoding="utf-8")
    if "features" not in text and not any(re.search(rf"\b{re.escape(a)}\b", text) for a in aliases()):
        return ()  # 寫不到 features 也寫不到別名的檔不可能 import 包：不必 parse（engine.py 一萬七千行，parse 一次一秒多）
    seen: dict[tuple[int, str], str] = {}
    for line, mod, _ in imports_of(text, _modname(path)):
        target = feature_target(mod)
        if target is not None:
            best = seen.get((line, target))
            if best is None or (_module_exists(mod), len(mod)) > (_module_exists(best), len(best)):
                seen[(line, target)] = mod
    return tuple(sorted((line, mod) for (line, _), mod in seen.items()))


def test_the_old_modules_that_only_read_the_arena_ranks_read_the_core_not_the_bout_package():
    for name in ARENA_RANK_READERS:
        assert "bout" not in {feature_target(mod) for _, mod in _feature_imports(TIANXIA / f"{name}.py")}, name
        assert "arena_ranks" in (TIANXIA / f"{name}.py").read_text(encoding="utf-8"), name
    assert "arena_ranks" in (TIANXIA / "core" / "presence.py").read_text(encoding="utf-8")  # 身分字的擂台稱號（第 37 批）


@functools.lru_cache(maxsize=None)
def _engine_tree() -> ast.Module:
    return ast.parse((TIANXIA / "engine.py").read_text(encoding="utf-8"))  # 一萬七千行，parse 一次一秒多：大家共用這一份


@functools.lru_cache(maxsize=None)
def game_members() -> frozenset[str]:
    """engine.Game 上的名字：類別裡定義的方法與類別屬性、方法裡寫 self.x = 的屬性（off_list_calls 認 attacker、defender 用）。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    names = {f.name for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    names |= {t.id for n in game.body if isinstance(n, (ast.Assign, ast.AnnAssign))
              for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    names |= {n.attr for n in ast.walk(game) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
              and isinstance(n.ctx, ast.Store)}
    return frozenset(names | set(game_api_names()))  # 掛上去的名字（第 72 批）也是 Game 上的


@functools.lru_cache(maxsize=None)
def game_links() -> tuple[set[str], set[str], set[tuple[str, str]]]:
    """engine.py：(模組頂層 import 的包的模組, Game 裡直接叫到包的方法, Game 裡叫委派的 (方法, 委派))。Game 以外碰到包也算直接叫。
    叫委派的那一組連 GAME_DIRECT 的方法裡叫的也記（PM 10/31 答覆出陣第 1 批：以前只記呼叫端本身不碰包的，出陣的 21 對只看得到 6 對）。"""
    tree = _engine_tree()
    local: dict[str, str] = {}  # 模組頂層 import 進來的包的模組：本地名字 → 模組
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            head = ".".join((["tianxia"] if node.level else []) + ([node.module] if node.module else []))
            # from <包的模組> import <名字>（名字不是模組，例：混戰的字 CLASH_OPEN）記成那個模組，跟 _feature_imports 同一個算法
            # （出陣第 1 批加的；以前只有 from <包> import <模組>，兩邊記的一樣）
            local.update({a.asname or a.name: f"{head}.{a.name}" if _module_exists(f"{head}.{a.name}") else head
                          for a in node.names if feature_target(f"{head}.{a.name}") is not None})
        elif isinstance(node, ast.Import):
            local.update({a.asname or a.name.split(".")[0]: a.name for a in node.names if feature_target(a.name) is not None})
    imports = set(local.values())
    game = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
    methods = [f for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    direct = {f.name for f in methods if any(isinstance(n, ast.Name) and n.id in local for n in ast.walk(f))}
    outside = [n for top in tree.body if top is not game and not isinstance(top, (ast.Import, ast.ImportFrom))
               for n in ast.walk(top) if isinstance(n, ast.Name) and n.id in local]
    direct |= {f"<engine 模組層:{n.lineno}>" for n in outside}
    callers = {(f.name, n.attr) for f in methods for n in ast.walk(f)
               if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
               and n.attr in direct | GAME_DELEGATES and n.attr != f.name}
    return imports, direct, callers


def test_the_core_never_imports_a_feature_package_except_the_registry():
    found = []
    for path in sorted((TIANXIA / "core").glob("*.py")):
        if path.name == "registry.py":
            continue
        found += [f"{path.name}:{line} {mod}" for line, mod in _feature_imports(path)]
    for name in sorted(CORE):
        found += [f"{name}.py:{line} {mod}" for line, mod in _feature_imports(TIANXIA / f"{name}.py")]
    found += [f"engine.py:{line} {mod}" for line, mod in _feature_imports(TIANXIA / "engine.py") if mod not in GAME_IMPORTS]
    assert found == []


def test_the_shared_rules_layer_is_real_old_modules_with_a_reason_and_never_imports_a_package():
    """共用規則層（registry.SHARED，第 11 批 PM 定的格式）：每一個是 tianxia/ 底下真的有的模組、不是核心本體、不是包、不是舊名的別名，
    寫了為什麼在共用層；跟核心一樣不 import 包（總表第六節第 5 條「兩層都不准 import 包」）。"""
    assert SHARED and all(isinstance(why, str) and why.strip() for why in SHARED.values())
    for name in SHARED:
        assert (TIANXIA / f"{name}.py").exists(), name
        assert name not in CORE and name not in aliases() and name not in _packages(), name
    assert [f"{name}.py:{line} {mod}" for name in sorted(SHARED) for line, mod in _feature_imports(TIANXIA / f"{name}.py")] == []


# 總表第六節第 5 條「共用規則層可以 import 核心本體與同層」：共用規則層的模組 import 的別的 tianxia 模組只能是核心本體（MODULES、tianxia/core/）
# 與同一層；包與舊名的別名是上面那一條，一律不准。現行程式裡碰到別的舊模組的逐條記在 SHARED_PENDING，兩種寫在理由開頭：
# 「排定：」收進核心本體或共用規則層的（那一批收完拿掉這一行）；「之後成包：」主人成包之前要先改成查詢服務、或把用到的那一段留在共用規則層
# （不然那一下就是「共用規則層 import 包」，上面那一條紅）。多一條、少一條都紅。


def outside_imports(source: str, module: str) -> set[str]:
    """共用規則層的模組（module 的原文 source）import 了哪些不是核心本體、不是同一層的 tianxia 舊模組：最外層與函式裡都算，
    TYPE_CHECKING 底下不算；包、舊名的別名、from tianxia import 名字（不是模組）不在這裡（包與別名是另一條，一律不准）。"""
    out: set[str] = set()
    for _, name, _ in imports_of(source, module):
        parts = name.split(".")
        if name == "tianxia" or parts[1] in ("core", "features") or parts[1] in CORE or parts[1] in SHARED or parts[1] in aliases():
            continue
        if _module_exists(".".join(parts[:2])):
            out.add(parts[1])
    return out


def shared_reach() -> set[tuple[str, str]]:
    """共用規則層碰到的別的舊模組：{(共用規則層的模組, 舊模組)}。"""
    return {(name, old) for name in SHARED
            for old in outside_imports((TIANXIA / f"{name}.py").read_text(encoding="utf-8"), f"tianxia.{name}")}


def test_the_shared_rules_layer_only_imports_the_core_and_itself():
    """共用規則層只 import 核心本體與同一層（總表第六節第 5 條）：碰到別的舊模組的就是 SHARED_PENDING 那幾條，多一條、少一條都紅
    （新碰到的要寫理由、收掉的要拿掉）；對象沒有一個是核心本體、同一層或別名，理由開頭寫是哪一種。"""
    assert shared_reach() == set(SHARED_PENDING)
    for (name, old), why in SHARED_PENDING.items():
        assert name in SHARED and old not in SHARED and old not in CORE and old not in aliases(), (name, old)
        assert why.startswith(("排定：", "之後成包：")), (name, old)


def test_a_pending_target_that_imports_a_package_says_it_drags_the_package_in():
    """SHARED_PENDING 的對象自己 import 了包的（以前有 bounties 經舊名 letters、parley、sortie import 人物情誼包與出陣包，第 45 批成包、figure_life 改讀核心 bounty_base，那一條收掉；
    atlas 經舊名 sortie import 出陣包，第 50 批 atlas 收進共用規則層、不再 import 包，指到它的六條收掉）：import 那個共用規則層的模組，包就跟著載進來
    （seal_acts 函式裡 import seal〔第 27 批成了玉璽包的別名〕，叫到它就連帶載入玉璽包）。上面那幾條只看共用規則層自己的 import，
    看不到這一層，所以理由要寫明「連帶載入」與那幾包的名字；對象不再 import 包了，「連帶載入」那句也拿掉（第 15 批審查修正）。
    只驗對象直接的 import；經對象再往下一層的（chapters 經舊名 storyline 載一條線包）寫在理由裡，這裡不驗。"""
    for (name, old), why in SHARED_PENDING.items():
        packages = sorted({feature_target(mod) for _, mod in _feature_imports(TIANXIA / f"{old}.py")})
        if packages:
            assert "連帶載入" in why and all(p in why for p in packages), (name, old, packages)
        else:
            assert "連帶載入" not in why, (name, old)


def test_the_modules_left_out_of_the_shared_layer_still_reach_past_it():
    """總表寫了、先不收的（SHARED_LATER）：不在 SHARED，而且真的還 import 了核心本體與共用規則層以外的模組（或包）——卡住的那一條不見了，
    這裡紅，登記進 registry.SHARED。"""
    for name, why in SHARED_LATER.items():
        path = TIANXIA / f"{name}.py"
        assert path.exists() and name not in SHARED and why.strip(), name
        assert outside_imports(path.read_text(encoding="utf-8"), _modname(path)) or _feature_imports(path), \
            f"{name} 只 import 核心本體與共用規則層了：登記進 registry.SHARED"


def test_the_shared_scanner_catches_an_old_module():
    """outside_imports 本身抓得到（不然上面那一條永遠綠）：最外層、函式裡、import tianxia.x 都算；TYPE_CHECKING、tianxia/core/、核心本體、
    同一層、from tianxia import 名字、標準庫不算；包與別名不在這裡算（是上面那一條）。"""
    m = "tianxia.timetable"
    assert outside_imports("from . import server_bots, territory\n", m) == {"server_bots"}  # 第 40 批：原本的例子 figures 收進了共用規則層；第 50 批：atlas 也收進了共用規則層，換成 seal_acts；第 51 批 seal_acts 也收進了共用規則層，換成 fusion；第二輪第 87 批 fusion 也收進了共用規則層，換成 shopview（SHARED_LATER，還是舊模組，第 93 批才動它）；第二輪第 93 批 shopview 切成測試用的殼（TEST_ONLY_SHELLS），換 server_bots（還是舊模組）
    # 第 25 批：原本的例子 world 收進了核心本體；第 27 批：seal 成了玉璽包的別名（包與別名不在這裡算）；第 52 批：tale 也成了戰記包的別名，換 bot（舊模組、之後不成包、這一波不動）
    assert outside_imports("def f():\n    from .bot import pick\n", m) == {"bot"}
    assert outside_imports("def f():\n    from .world import _season_vehicle\n", m) == set()
    assert outside_imports("import tianxia.engine\n", m) == {"engine"}
    assert outside_imports("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .engine import Game\n", m) == set()
    assert outside_imports("from .core import features\nfrom .models import Content\nfrom tianxia import calendar, siege\n", m) == set()
    assert outside_imports("from tianxia import TYPE_NAME_NOT_A_MODULE\nimport json\nfrom pydantic import BaseModel\n", m) == set()
    assert outside_imports("from .features.battle import rules\nfrom . import feasts\n", m) == set()


def test_the_game_reaches_the_packages_only_through_the_listed_methods():
    """Game 碰包的地方只有：各包 game_api.py 掛上去的（第二輪第 72 批，不在 engine.py）、寫明了的過渡直連（GAME_DIRECT、GAME_DELEGATE_CALLERS）。其餘一律走 FEATURES 的掛鉤。"""
    imports, direct, callers = game_links()
    assert imports == GAME_IMPORTS
    assert direct == set(GAME_DIRECT)
    assert not GAME_IMPORTS and not GAME_DIRECT  # 第 98 批鎖成空：核心不 import 包是真的（要加先過 PM）
    assert {(caller, callee) for caller, callee in callers if callee in GAME_DELEGATES} == set(GAME_DELEGATE_CALLERS)


def reverse_imports() -> list[str]:
    """另一個方向的過渡（3.11）：還沒搬的舊模組、伺服器、腳本 import 功能包（含經過舊名的別名）。
    PM 每搬一包在交接記還剩幾處，跟 transitional_imports()（包 import 舊模組）兩個方向都記；核心的 registry.py 不算。"""
    files = [p for p in sorted(TIANXIA.glob("*.py"))] + [ROOT / "server.py", ROOT / "run_bots.py"] + sorted((ROOT / "scripts").rglob("*.py"))
    out = []
    for path in files:
        if path.exists():
            out += [f"{path.relative_to(ROOT).as_posix()}:{line} {mod}" for line, mod in _feature_imports(path)]
    return out


def test_the_reverse_transitional_imports_come_from_old_modules():
    """舊模組 → 包那一向：都在還沒搬的舊模組、殼與腳本裡（核心的一筆都不准：第 98 批起 GAME_IMPORTS 是空的），而且數得到（不然交接記的數是空的）。"""
    found = reverse_imports()
    assert any(e.startswith("server.py:") for e in found)
    for entry in found:
        stem = entry.split(":", 1)[0].removeprefix("tianxia/").removesuffix(".py")
        assert stem not in CORE or entry.rsplit(" ", 1)[1] in GAME_IMPORTS, entry


def transitional_imports() -> list[str]:
    """過渡期的 import（包 import 還沒搬的舊模組）：PM 每搬一包在交接記還剩幾處（手冊 3.11）。共用規則層（SHARED）的不算：它們不搬。"""
    out = []
    for name in _packages():
        for path in _package_files(name):
            seen = {(line, ".".join(mod.split(".")[:2])) for line, mod, marked in imports_of(path.read_text(encoding="utf-8"), _modname(path))
                    if marked and mod != "tianxia" and _module_exists(".".join(mod.split(".")[:2])) and mod.split(".")[1] not in aliases()
                    and mod.split(".")[1] not in SHARED}
            out += [f"{_modname(path)}:{line} {mod}" for line, mod in sorted(seen)]
    return out


def stale_marks(source: str, module: str) -> list[int]:
    """註了「過渡：待搬」、可是 import 的 tianxia 模組裡沒有一個是還沒搬的舊模組（全是核心本體、共用規則層、包或 from tianxia import 名字）的那幾行。"""
    lines: dict[int, bool] = {}
    for line, name, marked in imports_of(source, module):
        if not marked:
            continue
        parts = name.split(".")
        old = (len(parts) > 1 and parts[1] not in CORE and parts[1] not in SHARED and parts[1] not in ("core", "features")
               and parts[1] not in aliases() and _module_exists(".".join(parts[:2])))
        lines[line] = lines.get(line, False) or old
    return sorted(line for line, has_old in lines.items() if not has_old)


def test_every_transitional_import_points_at_an_old_module_not_the_core_or_a_package():
    """註了「過渡：待搬」的那一行真的是舊模組：搬完了（變成核心或包）、登記進共用規則層，就把註拿掉。"""
    for entry in transitional_imports():
        mod = entry.rsplit(" ", 1)[1].split(".")
        assert mod[1] not in CORE and mod[1] not in ("core", "features") and mod[1] not in aliases() and mod[1] not in SHARED, entry
    stale = [f"{_modname(path)}:{line}" for name in _packages() for path in _package_files(name)
             for line in stale_marks(path.read_text(encoding="utf-8"), _modname(path))]
    assert stale == []


SERVICES = TIANXIA / "core" / "services_list.md"
CTX_NAMES = ("ctx", "g", "game")  # 功能包裡拿 Game 的變數名（掛鉤的 ctx、路由 lambda 的 g、路由裡的 game）
# 約戰結算（出陣包 duel_actions.duel_result，主動搬六包第 2 批）另外兩份 Game 叫 attacker、defender（軍令 _order_credit 叫在它們上面）。
# 包裡同名的也有約戰的一方（duel_rules 的 attacker、defender 是 SortieSide：attacker.model_copy），所以這兩個名字只算 Game 上真的有的名字
GAME_ALIASES = ("attacker", "defender")


def service_list() -> set[str]:
    """tianxia/core/services_list.md 那張服務清單上的名字（寫成 `ctx.<名字>` 的）。"""
    return set(re.findall(r"`ctx\.(\w+)", SERVICES.read_text(encoding="utf-8")))


def off_list_calls(source: str, module: str, allowed: set[str]) -> list[str]:
    """功能包的模組碰了 Game 上不在服務清單的東西（ctx.x、g.x、game.x；手冊 3.3「只准叫服務清單上的方法」）。
    只認那三個變數名，加上 GAME_ALIASES（attacker、defender：只算 Game 上有的名字）：拿別的名字接 Game 的看不到，第一版先這樣。"""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)) or node.attr in allowed:
            continue
        if node.value.id in CTX_NAMES or (node.value.id in GAME_ALIASES and node.attr in game_members()):
            out.append(f"{module}:{node.lineno} {node.value.id}.{node.attr}")
    return out


def allowed_for(package: str, allowed: set[str]) -> set[str]:
    """這一包經 Game 放行的名字：清單上的，加上自己這一包的委派（第二輪第 74 批：包叫自己的不算離清單，主人從第 72 批的表讀）。"""
    return allowed | {name for name, pack in game_api_names().items() if pack == package}


def test_feature_packages_only_touch_the_service_list_on_the_game():
    """功能包經過 Game 只碰服務清單上的，和自己這一包的委派（手冊 3.3、第二輪第 74 批）。"""
    allowed = service_list()
    assert {"state", "content", "_log", "_wallet", "wallet"} <= allowed  # 清單讀得到
    found = []
    for name in _packages():
        for path in _package_files(name):
            found += off_list_calls(path.read_text(encoding="utf-8"), _modname(path), allowed_for(name, allowed))
    assert found == []


def foreign_relay_calls(source: str, module: str, package: str) -> list[str]:
    """這一包經 Game 叫了別包三段式的名字。"""
    owner = {name: pack for pack, names in RELAY_OWNERS.items() for name in names}
    return [f"{module}:{node.lineno} {node.value.id}.{node.attr}（{owner[node.attr]} 的）" for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in CTX_NAMES
            and owner.get(node.attr, package) != package]


def test_the_three_stage_relay_names_are_only_called_by_their_owner():
    owner = game_api_names()
    assert {name for pack, names in RELAY_OWNERS.items() for name in names if owner.get(name) != pack} == set()  # 主人跟第 72 批的表對得上（第二輪第 74 批，以前對清單上那一段）
    assert foreign_relay_calls("def f(ctx):\n    ctx.apply_letter(1, 2)\n", "x", "tavern")  # 真的看得到別包叫
    assert not foreign_relay_calls("def f(ctx):\n    ctx.apply_letter(1, 2)\n", "x", "companions")
    found = []
    for name in _packages():
        for path in _package_files(name):
            found += foreign_relay_calls(path.read_text(encoding="utf-8"), _modname(path), name)
    assert found == []


def ctx_delegate_callers(source: str, name: str, delegates: set[str] | None = None,
                         names: tuple[str, ...] = ("ctx",)) -> set[tuple[str, str]]:
    """核心模組（source 是原文、name 是模組名，例 event_check）經 ctx.<名> 叫的、而且是包的委派（預設 GAME_DELEGATES）的
    (模組.函式, 委派)；函式以外的記成 (模組, 委派)。巢狀的函式算在最外層那一個。names 是哪幾個變數名算 Game（預設只認 ctx；
    core_world2：頂層的核心模組也認 game，全部拆包第 40 批）。"""
    delegates = GAME_DELEGATES if delegates is None else delegates
    out: set[tuple[str, str]] = set()
    for top in ast.parse(source).body:
        where = f"{name}.{top.name}" if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else name
        out |= {(where, node.attr) for node in ast.walk(top)
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in names and node.attr in delegates}
    return out


def test_the_core_modules_reach_no_package_delegate_through_ctx():
    """tianxia/core/ 底下（registry.py 以外）經 ctx 叫回 Game 的，是包的委派的只有 CORE_DELEGATE_CALLERS 列的過渡（附理由）；
    新的要用包的東西照第 11 批開掛鉤（接縫掛鉤、Shop、Verb）。"""
    found: set[tuple[str, str]] = set()
    for path in sorted((TIANXIA / "core").glob("*.py")):
        if path.name != "registry.py":
            found |= ctx_delegate_callers(path.read_text(encoding="utf-8"), path.stem)
    assert found == set(CORE_DELEGATE_CALLERS)
    assert all(isinstance(why, str) and why.strip() for why in CORE_DELEGATE_CALLERS.values())
    assert ctx_delegate_callers("def f(ctx):\n    return ctx._tavern_price(1)\n", "m") == {("m.f", "_tavern_price")}  # 掃描抓得到
    assert ctx_delegate_callers("def f(ctx):\n    return ctx._present(e)\n", "m") == set()
    # 主人搬成包的那一批：委派多一個，掃描報出 (模組.函式, 委派) 這一對（記進名單就過，見上面的註解）
    assert ctx_delegate_callers("def f(ctx):\n    def g():\n        return ctx._x()\n    return g\n", "m", {"_x"}) == {("m.f", "_x")}


def event_check_delegates() -> set[str]:
    """engine.Game 上本體（說明字以外）只有一行 `return event_check.<名>(self, …)` 的方法。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    out = set()
    for f in game.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [n for n in f.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        call = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "event_check" and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "self"):
            out.add(f.name)
    return out


def test_the_game_reaches_the_event_check_only_through_its_one_line_delegates():
    """Game 上叫 event_check 的只有 CORE_EVENT_DELEGATES 那幾個一行的委派（多一處就是把事件檢定的邏輯寫回 Game、或委派加了邏輯）。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    users = {f.name for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
             and any(isinstance(n, ast.Name) and n.id == "event_check" for n in ast.walk(f))}
    assert event_check_delegates() == CORE_EVENT_DELEGATES
    assert users == CORE_EVENT_DELEGATES


def test_the_event_check_calls_the_patched_game_methods_through_ctx():
    tree = ast.parse((TIANXIA / "core" / "event_check.py").read_text(encoding="utf-8"))
    direct = sorted(f"{node.lineno} {node.func.id}" for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in EVENT_CHECK_VIA_CTX)
    assert direct == []
    via = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ctx"}
    assert {name for name, _ in EVENT_CHECK_VIA_CTX.values()} <= via
    assert {name for name, _ in EVENT_CHECK_VIA_CTX.values()} <= CORE_EVENT_DELEGATES


def combat_delegates() -> set[str]:
    """engine.Game 上本體（說明字以外）只有一行 `return combat.<名>(self, …)` 的方法；CORE_COMBAT_STATIC_DELEGATES 那三個照舊是 staticmethod，沒有 self。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    out = set()
    for f in game.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [n for n in f.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        call = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "combat"):
            continue
        static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in f.decorator_list)
        if static or (call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "self"):
            out.add(f.name)
            assert static == (f.name in CORE_COMBAT_STATIC_DELEGATES), f.name
    return out


def test_the_game_reaches_the_combat_service_only_through_its_one_line_delegates():
    """Game 上碰 combat 的只有 CORE_COMBAT_DELEGATES 那幾個一行的委派（多一處就是把單打服務的邏輯寫回 Game、或委派加了邏輯）。
    型別註記寫到的 combat.TollFacts 不算碰（_hp_facts、_take_toll、_play_rounds 本來就是委派）。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    users = {f.name for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
             and any(isinstance(n, ast.Name) and n.id == "combat" for n in ast.walk(f))}
    assert combat_delegates() == CORE_COMBAT_DELEGATES
    assert users == CORE_COMBAT_DELEGATES


def test_the_combat_service_calls_the_patched_game_methods_through_ctx():
    """被換掉的 8 個，combat 裡一處都不直接叫本體；真的有人互叫的 6 個（COMBAT_CALLED_THROUGH_CTX）寫成 ctx.<委派>。
    另外 2 個模組裡沒有人互叫，所以這裡不要求 ctx.<委派> 寫到（照抄 event_check 那條的 `<= via` 會紅）。"""
    tree = ast.parse((TIANXIA / "core" / "combat.py").read_text(encoding="utf-8"))
    direct = sorted(f"{node.lineno} {node.func.id}" for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in COMBAT_VIA_CTX)
    assert direct == []
    via = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ctx"}
    assert via & {name for name, _ in COMBAT_VIA_CTX.values()} == COMBAT_CALLED_THROUGH_CTX
    assert {name for name, _ in COMBAT_VIA_CTX.values()} <= CORE_COMBAT_DELEGATES


# core_pushing（第二輪第 80 批）
def _service_delegates(module: str) -> set[str]:
    """engine.Game 上本體（說明字以外）只有一行 `return <module>.<名>(self, …)` 的方法（take_stamina_pill 帶裝飾器，語法樹一樣認得）。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    out = set()
    for f in game.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [n for n in f.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        call = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                and call.func.value.id == module and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "self"):
            out.add(f.name)
    return out


@pytest.mark.parametrize("module, delegates", [("pushing", CORE_PUSHING_DELEGATES), ("pills", CORE_PILLS_DELEGATES)], ids=["pushing", "pills"])
def test_the_game_reaches_the_push_and_pill_services_only_through_their_one_line_delegates(module, delegates):
    """Game 上碰 pushing、pills 的只有 CORE_PUSHING_DELEGATES、CORE_PILLS_DELEGATES 那幾個一行的委派（多一處就是把邏輯寫回 Game、或委派加了邏輯）。
    engine 模組層那幾行 import 不算碰。"""
    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    users = {f.name for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
             and any(isinstance(n, ast.Name) and n.id == module for n in ast.walk(f))}
    assert _service_delegates(module) == delegates
    assert users == delegates


@pytest.mark.parametrize("module, via_ctx, delegates", [("pushing", PUSHING_VIA_CTX, CORE_PUSHING_DELEGATES), ("pills", PILLS_VIA_CTX, CORE_PILLS_DELEGATES)], ids=["pushing", "pills"])
def test_the_push_and_pill_services_call_the_patched_game_methods_through_ctx(module, via_ctx, delegates):
    """被換掉的那幾個，模組裡一處都不直接叫本體。pushing 真的有人互叫的只有 daily_push_cap（PUSHING_CALLED_THROUGH_CTX，寫成 ctx.daily_push_cap）；
    其餘的模組裡沒有人互叫，所以這裡不要求 ctx.<委派> 寫到（照抄 event_check 那條的 `<= via` 會紅）。"""
    tree = ast.parse((TIANXIA / "core" / f"{module}.py").read_text(encoding="utf-8"))
    direct = sorted(f"{node.lineno} {node.func.id}" for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in via_ctx)
    assert direct == []
    via = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ctx"}
    assert via & {name for name, _ in via_ctx.values()} == (PUSHING_CALLED_THROUGH_CTX if module == "pushing" else set())
    assert {name for name, _ in via_ctx.values()} <= delegates


# core_views（第二輪第 81 批）
VIEW_MODULES = {"status_view", "page_view", "scene_view"}  # scene_view：core_scene（第二輪第 91 批）


def test_the_game_reaches_the_views_only_through_its_one_line_delegates():
    """Game 上叫 status_view、page_view、scene_view 的只有 CORE_VIEW_DELEGATES 那幾個一行的委派（多一處就是把畫面的邏輯寫回 Game、或委派加了邏輯）；
    engine._MENU_CORE 的 "open" 那一格指到 page_view.OPEN_CORE（_shop_open 讀的是同一份，核心不 import engine）。"""
    from tianxia import engine
    from tianxia.core import page_view

    game = next(n for n in _engine_tree().body if isinstance(n, ast.ClassDef) and n.name == "Game")
    methods = [f for f in game.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    users = {f.name for f in methods if any(isinstance(n, ast.Name) and n.id in VIEW_MODULES for n in ast.walk(f))}
    one_liners = set()
    for f in methods:
        body = [n for n in f.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        call = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                and call.func.value.id in VIEW_MODULES and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "self"):
            one_liners.add(f.name)
    assert one_liners == CORE_VIEW_DELEGATES
    assert users == CORE_VIEW_DELEGATES
    assert engine._MENU_CORE["open"] is page_view.OPEN_CORE


# ── 網頁框架（docs/guide/核心與存檔.md「tianxia/ 不得 import 任何網頁框架」的例外，PM 10/31）──
# 只有 tianxia/features/<包>/routes.py 可以 import fastapi，而且只在殼掛路由時延後 import（包的 __init__ 在 routes()、
# admin_tools() 裡面才 from . import routes）；引擎、run_bots、假人不碰。

WEB_FRAMEWORKS = {"fastapi", "starlette", "uvicorn"}
_ROUTES_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+\S*[ \t]+import[ \t]+[^\n]*\broutes\b|from[ \t]+\S*\broutes[ \t]+import|import[ \t]+\S*\broutes\b)",
                            re.M)


def _engine_files() -> list[Path]:
    """tianxia/ 底下的程式（功能包的 tests/ 不算：測試本來就可以用 fastapi 的 TestClient）。"""
    return sorted(p for p in TIANXIA.rglob("*.py") if "tests" not in p.relative_to(TIANXIA).parts)


def _load_time_nodes(tree: ast.AST):
    """import 這個模組的那一刻就會跑到的節點：不進函式（def、async def、lambda）的本體；類別的本體會跑，要進。"""
    todo = list(ast.iter_child_nodes(tree))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            todo.extend(ast.iter_child_nodes(node))


def web_framework_problems() -> list[str]:
    found = []
    for path in _engine_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        is_routes = path.name == "routes.py" and path.parent.parent == FEATURES
        if any(w in text for w in WEB_FRAMEWORKS) and not is_routes:
            for node in ast.walk(ast.parse(text)):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else [])
                found += [f"{rel}:{node.lineno} import {n}（只有功能包的 routes.py 可以）" for n in names
                          if n.split(".")[0] in WEB_FRAMEWORKS]
        if _ROUTES_IMPORT.search(text):
            module = _modname(path)
            tree = ast.parse(text)
            skip = _type_checking_lines(tree)
            for node in _load_time_nodes(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)) or node.lineno in skip:
                    continue
                for _, mod, _ in imports_of(ast.unparse(node) + "\n", module):
                    parts = mod.split(".")
                    if len(parts) == 4 and parts[:2] == ["tianxia", "features"] and parts[3] == "routes":
                        found.append(f"{rel}:{node.lineno} 載入時就 import {mod}（要延後到殼掛路由的那一刻）")
    return found


def test_only_package_routes_import_a_web_framework_and_only_when_the_shell_mounts_them():
    """幾毫秒的那一半：照原始碼看。另一半（真的 import 之後 sys.modules 裡沒有 fastapi）是下面那一條 slow 的。"""
    assert web_framework_problems() == []
    assert (FEATURES / "mall" / "routes.py").exists()  # 有一包真的用到（不然這一條永遠綠）


def test_the_web_framework_scan_catches_a_load_time_import(tmp_path, monkeypatch):
    pkg = tmp_path / "tianxia" / "features" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from . import routes\n\ndef later():\n    from . import routes\n", encoding="utf-8")
    (pkg / "routes.py").write_text("from fastapi import APIRouter\n", encoding="utf-8")
    (tmp_path / "tianxia" / "glyph2.py").write_text("import fastapi\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "TIANXIA", tmp_path / "tianxia")
    monkeypatch.setattr(sys.modules[__name__], "FEATURES", tmp_path / "tianxia" / "features")
    found = web_framework_problems()
    assert len(found) == 2, found
    assert any("features/demo/__init__.py:1" in f and "tianxia.features.demo.routes" in f for f in found)
    assert any("glyph2.py:1 import fastapi" in f for f in found)


@pytest.mark.slow  # 開一個乾淨的子行程 import 引擎與假人程式，約 3 秒
def test_the_engine_the_bot_program_and_the_bots_load_no_web_framework(tmp_path):
    code = (
        "import json, sys\n"
        "import tianxia.engine, tianxia.bot, tianxia.bot_policy, tianxia.bot_runner, run_bots\n"
        "from tianxia.core import features\n"
        "features.bot_always()\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in %r)))\n" % (sorted(WEB_FRAMEWORKS),)
    )
    env = {**os.environ, "TIANXIA_DB": str(tmp_path / "t.db"), "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                         env=env, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


# ── 掃描本身抓得到（不然上面幾條永遠綠）──


def test_the_service_scanner_catches_a_game_method_off_the_list():
    allowed = service_list()
    assert off_list_calls("def f(ctx):\n    return ctx._tavern_price(1)\n", "m", allowed) == ["m:2 ctx._tavern_price"]
    assert off_list_calls("route = lambda g: g.mall_view()\n", "m", allowed) == ["m:1 g.mall_view"]
    assert off_list_calls("def f(ctx):\n    ctx._log(['x'])\n    return ctx.state.player\n", "m", allowed) == []
    # 約戰結算的另外兩份 Game（主動搬六包第 2 批）：Game 上有、清單上沒有的抓得到；清單上的、Game 上沒有的（約戰的一方 SortieSide）不算
    assert off_list_calls("def f(attacker, defender):\n    attacker._tavern_price(1)\n    return defender._tavern_price(2)\n", "m",
                          allowed) == ["m:2 attacker._tavern_price", "m:3 defender._tavern_price"]
    assert off_list_calls("def f(attacker):\n    attacker._order_credit(kind='win')\n    return attacker.model_copy(deep=True)\n", "m",
                          allowed) == []
    # 自己這一包的委派放行、別包照抓（第二輪第 74 批）
    assert off_list_calls("def f(ctx):\n    return ctx._tavern_price(1)\n", "m", allowed_for("tavern", allowed)) == []
    assert off_list_calls("def f(ctx):\n    return ctx._tavern_price(1)\n", "m", allowed_for("mall", allowed)) == ["m:2 ctx._tavern_price"]


@pytest.mark.parametrize("source, expected", [
    ("from tianxia.features import feast\n", "別的包"),
    ("from tianxia.features.feast import rules\n", "別的包"),
    ("from ..feast import rules\n", "別的包"),
    ("from tianxia import server_bots\n", "舊模組"),  # shared：原本的例子 library 第 15 批登記進共用規則層，換一個還是舊模組的；bounties 第 45 批成包，再換 shopview；第二輪第 93 批 shopview 切成測試用的殼（TEST_ONLY_SHELLS），換 server_bots（還是舊模組）
    ("from tianxia import engine\n", "舊模組"),
    ("import tianxia.server_bots\n", "舊模組"),
    # 舊名留成的別名（tianxia/feasts.py 把 sys.modules 換成宴客包的 rules）就是那一包：註了過渡也擋
    ("from tianxia import feasts  # 過渡：待搬\n", "別的包 feast"),
    ("from tianxia.feasts import ToastRequest\n", "別的包 feast"),
    ("import tianxia.feasts\n", "別的包 feast"),
    ("from tianxia import mall  # 過渡：待搬\n", "自己這一包的別名"),
])
def test_the_scanner_catches_a_crossing(source, expected):
    found = problems_of(source, "tianxia.features.mall.actions")
    assert len(found) == 1 and expected in found[0]


def test_the_old_names_left_as_aliases_are_known():
    """tianxia/mall.py、tianxia/feasts.py、tianxia/sortie.py、tianxia/sortie_duel.py、tianxia/outing.py、tianxia/explore_one.py、
    tianxia/tavern.py、tianxia/tavern_ask.py、tianxia/escorts.py、tianxia/generals.py、tianxia/duel.py、tianxia/arena.py、tianxia/arena_crowd.py 是指到包裡同一個模組的別名（給還沒改的測試與舊模組）：掃描照它們指到的那一包算，不算舊模組。"""
    assert aliases() == {"feasts": "feast", "mall": "mall", "sortie": "sortie", "sortie_duel": "sortie",
                         # explore
                         "outing": "explore", "explore_one": "explore",
                         # tavern
                         "tavern": "tavern", "tavern_ask": "tavern",
                         # battle（全部拆包第 7 批：tianxia/escorts.py；第 8 批：tianxia/generals.py；第 54 批：tianxia/battle_instance.py）
                         "escorts": "battle", "generals": "battle", "battle_instance": "battle",
                         # guide（全部拆包第 22 批：tianxia/guide.py、hints.py、newbie.py、opening.py、enlist.py）
                         "guide": "guide", "hints": "guide", "newbie": "guide", "opening": "guide", "enlist": "guide",
                         # stamina_plays（全部拆包第 39 批：tianxia/ambush.py、works.py）
                         "ambush": "stamina_plays", "works": "stamina_plays",
                         # bout（全部拆包第 12 批：tianxia/duel.py、arena.py、arena_crowd.py）
                         "duel": "bout", "arena": "bout", "arena_crowd": "bout",
                         # companions（全部拆包第 19 批：tianxia/stances.py、errands.py、letters.py）
                         "stances": "companions", "errands": "companions", "letters": "companions",
                         # companions（全部拆包第 20 批：tianxia/companion_agent.py、parley.py）
                         "companion_agent": "companions", "parley": "companions",
                         # companions（主幹合回 D 段：tianxia/talk_log.py）
                         "talk_log": "companions",
                         # sense（全部拆包第 24 批：tianxia/sensing.py、epiphany.py、glyph.py、insight_llm.py）
                         "sensing": "sense", "epiphany": "sense", "glyph": "sense", "insight_llm": "sense",
                         # cultivation（全部拆包第 23 批：tianxia/cultivation.py、chuangong.py、ascend.py）
                         "cultivation": "cultivation", "chuangong": "cultivation", "ascend": "cultivation",
                         # story（全部拆包第 30 批：tianxia/storyline.py）
                         "storyline": "story",
                         # checkin（全部拆包第 30 批：tianxia/checkin.py）
                         "checkin": "checkin",
                         # figure_acts（全部拆包第 31 批：tianxia/figure_aid.py、yuedan.py）
                         "figure_aid": "figure_acts", "yuedan": "figure_acts",
                         # zhuan（全部拆包第 29 批：tianxia/biography.py、zhuan_end.py）
                         "biography": "zhuan", "zhuan_end": "zhuan",
                         # zhuan（第 29 批之二：tianxia/annals.py 指到 zhuan/standing.py，那一份 re-export 核心 annal_base）
                         "annals": "zhuan",
                         # military（全部拆包第 33 批：tianxia/rank_actions.py）
                         "rank_actions": "military",
                         # military（全部拆包第 34 批：tianxia/foreshadow.py、opportunities.py）
                         "foreshadow": "military", "opportunities": "military",
                         # craft（全部拆包第 44 批：tianxia/create.py）
                         "create": "craft",
                         # territory_acts（全部拆包第 46 批：tianxia/conquest_day.py、xingshi.py）
                         "conquest_day": "territory_acts", "xingshi": "territory_acts",
                         # peers（全部拆包第 37 批：tianxia/social.py、invites.py、mingtie.py、mingtie_card.py）
                         "social": "peers", "invites": "peers", "mingtie": "peers", "mingtie_card": "peers",
                         # peers2（全部拆包第 38 批：tianxia/spar.py、discuss.py、raid.py）
                         "spar": "peers", "discuss": "peers", "raid": "peers",
                         # map（全部拆包第 49 批：tianxia/mapview.py、mapart.py、mapdata.py、worldgeo.py）
                         "mapview": "map", "mapart": "map", "mapdata": "map", "worldgeo": "map",
                         # smithy（全部拆包第 41 批：tianxia/smithing.py）
                         "smithing": "smithy",
                         # faction（全部拆包第 35 批：tianxia/defection.py）
                         "defection": "faction",
                         # gear（全部拆包第 42 批：tianxia/signature_arms.py）
                         "signature_arms": "gear",
                         # seal（全部拆包第 27 批：tianxia/seal.py；包名跟別名同字，同 cultivation、guide）
                         "seal": "seal",
                         # bounties（全部拆包第 45 批：tianxia/bounties.py、wanted.py；包名跟別名同字，同 cultivation、guide、seal）
                         "bounties": "bounties", "wanted": "bounties",
                         # seal（全部拆包第 28 批：tianxia/seal_duel.py 指到 seal/duel_rules.py）
                         "seal_duel": "seal",
                         # tale（全部拆包第 52 批：tianxia/tale.py；包名跟別名同字，同 cultivation、guide）
                         "tale": "tale",
                         # notify（全部拆包第 53 批：tianxia/notices.py；包名不叫 push，tianxia/push.py 是推力規則）
                         "notices": "notify"}
    assert not [e for e in transitional_imports() if e.rsplit(" ", 1)[1].split(".")[1] in aliases()]


def test_a_mark_with_no_old_module_left_is_caught():
    """註了過渡、import 的卻都是核心本體或共用規則層（搬完了、登記了）：那一行的註要拿掉；同一行還有一個舊模組的照註（第 11 批）。"""
    assert stale_marks("from tianxia import siege  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    assert stale_marks("from tianxia import journal, team  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    # shared：原本的例子 conquest 第 15 批登記進共用規則層，換一個還是舊模組的
    assert stale_marks("from tianxia import server_bots, siege  # 過渡：待搬\n", "tianxia.features.battle.view") == []  # 第 45 批：原本的例子 bounties 成包，換還是舊模組的 shopview；第二輪第 93 批 shopview 切成測試用的殼（TEST_ONLY_SHELLS），換 server_bots（還是舊模組）
    assert stale_marks("from tianxia import siege\n", "tianxia.features.battle.view") == []


@pytest.mark.parametrize("source", [
    "from tianxia import server_bots  # 過渡：待搬\n",  # shared：原本的例子 library 第 15 批登記進共用規則層；bounties 第 45 批成包，再換 shopview；第二輪第 93 批 shopview 切成測試用的殼（TEST_ONLY_SHELLS），換 server_bots（還是舊模組）
    "from tianxia import library\n",  # shared：共用規則層（第 15 批）不必註
    "from tianxia import siege\n",  # 共用規則層（registry.SHARED，第 11 批）：不必註
    "from tianxia.siege import title\n",
    "from tianxia.core.services import WalletService\n",
    "from tianxia import calendar, naming\n",
    "from tianxia.models import Content\n",
    "from . import rules\n",
    "from .rules import buy\n",
    "from tianxia.features.mall import rules\n",
    "import json\nfrom pydantic import BaseModel\n",
    "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from tianxia.engine import Game\n",
])
def test_the_scanner_lets_the_allowed_ones_through(source):
    assert problems_of(source, "tianxia.features.mall.actions") == []


def test_the_world_layer_core_files_import_no_package_not_even_inside_a_function():
    """world.py 收進核心本體（MODULES）之後跟 sqlite_world.py 一樣：最外層與函式裡都不 import 包與舊名的別名（宴客 feasts、單挑 arena、
    大勢人物 yuedan、決戰 generals 換成了世界層的格）。掃描照 ast.walk 看得到函式裡的 import（下面那一段證明），所以核心那一條
    （test_the_core_never_imports_a_feature_package_except_the_registry）照 CORE 掃到它們；這裡寫明兩個檔，免得 MODULES 改了沒人發現。"""
    assert {"world", "sqlite_world"} <= CORE
    for name in ("world", "sqlite_world"):
        assert _feature_imports(TIANXIA / f"{name}.py") == [], name
    source = "def f():\n    from . import generals\n    from .features.feast import rules as feasts\n    from . import arena, yuedan\n"
    assert {feature_target(mod) for _, mod, _ in imports_of(source, "tianxia.world")} - {None} == {"battle", "feast", "bout", "figure_acts"}


def claimed_fields() -> dict[str, str]:
    """包認領的 PlayerState 欄位 → 哪一包（registry.FEATURES 的 player_fields）。"""
    from tianxia.core.registry import FEATURES as registered  # noqa: PLC0415  這個檔的 FEATURES 是 features 資料夾

    return {field: f.name for f in registered for field in f.player_fields}


def package_fields_touched(source: str, names: tuple[str, ...]) -> list[str]:
    """source 最外層名字是 names 之一（結尾是底線的照開頭比：_fx_ 就是每一格）的函式與賦值裡，碰到的包認領的欄位：["函式:行 欄位（包）"]。"""
    claimed = claimed_fields()

    def picked(name: str) -> bool:
        return any(name.startswith(n) if n.endswith("_") else name == n for n in names)

    out = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            name = node.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            name = next((t.id for t in targets if isinstance(t, ast.Name)), "")
        else:
            continue
        if not picked(name):
            continue
        out += [f"{name}:{sub.lineno} {sub.attr}（{claimed[sub.attr]}）" for sub in ast.walk(node)
                if isinstance(sub, ast.Attribute) and sub.attr in claimed]
    return out


def test_the_effect_slots_and_the_defection_clearing_touch_no_package_field():
    """核心本體 rules 的效果格與舊模組 defection 的清進度都不寫包認領的欄位（換成核心的掛鉤之後是空的）。先證明掃描看得到：
    原本寫在 apply_effect 最後一段的一條線那一步、clear_progress 裡的押糧與提示，照這一條都抓得到。"""
    for module, names in EFFECT_DEFECT_SCAN.items():
        where = FEATURES / "faction" / f"{module}.py" if module == "defection" else TIANXIA / f"{module}.py"  # defection 第 35 批搬進陣營包（舊名是別名）
        assert package_fields_touched(where.read_text(encoding="utf-8"), names) == [], module
    old = ("def apply_effect(effect, state):\n    p = state.player\n    progress = p.storylines.get(effect.story.line)\n"
           "    p.keepsakes.append(effect.story.keepsake)\n"
           "def clear_progress(p):\n    p.convoy = None\n    p.hint_queue = []\n    p.rank = 0\n"
           "def prompt(p):\n    return p.convoy\n")
    assert sorted(package_fields_touched(old, EFFECT_DEFECT_SCAN["rules"] + EFFECT_DEFECT_SCAN["defection"])) == [
        "apply_effect:3 storylines（story）", "apply_effect:4 keepsakes（story）", "clear_progress:6 convoy（military）",
        "clear_progress:7 hint_queue（guide）"]


def bus_bypasses(source: str) -> list[int]:
    """source 裡直接叫事件訂閱者的行號（模組層 _BUS_CORE 那一個賦值裡的不算）：bounties.<交差>(...)、<誰>._seal_find(...) 這一類呼叫。"""
    tree = ast.parse(source)
    allowed: set[int] = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "_BUS_CORE" for t in targets):
            allowed |= {id(sub) for sub in ast.walk(node)}
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or id(node) in allowed:
            continue
        func = node.func
        if func.attr in BUS_METHODS or (isinstance(func.value, ast.Name) and (func.value.id, func.attr) in BUS_SUBSCRIBERS):
            out.append(node.lineno)
    return sorted(out)


def test_nobody_calls_an_event_subscriber_outside_the_publish_points():
    """engine.py 與每一包都經 ctx.publish 發事件，不直接叫懸賞的交差、玉璽、交糧車（只有 engine._BUS_CORE 代叫）。先證明掃描看得到：
    原本那幾行（engine 的打贏、抵達、截殺打贏，探索包的出門一趟、遭遇打贏，決戰包的收場）照這一條都抓得到，_BUS_CORE 裡的不算。"""
    files = [TIANXIA / "engine.py", TIANXIA / "core" / "combat.py"] + [path for name in _packages() for path in _package_files(name)]  # combat：win 的發布點第 98 批搬過去
    found = {str(path.relative_to(ROOT)): bus_bypasses(path.read_text(encoding="utf-8")) for path in files}
    assert {path: lines for path, lines in found.items() if lines} == {}
    old = ("def _squad_encounter(self, s, c, loc, squad):\n    extra = bounties.on_win(s, c, self.world, loc.id, squad.id)\n"
           "def _arrive(self, s, c, loc_id):\n    convoy = self._convoy_arrives(loc_id) + bounties.on_arrive(s, c, self.world, loc_id)\n"
           "def _raid_bounty(self, target):\n    msgs = bounties.on_raid_win(self.state, self.content, self.world, target)\n"
           "def explore_one(ctx, s, c, loc):\n    extras = bounties.on_explore(s, c, ctx.world, loc.id) + ctx._seal_find(loc.id)\n"
           "def settle_showdown(ctx, battle, definition, result):\n    ctx._seal_settle(battle, definition, result)\n"
           "_BUS_CORE = {'win': {'bounties': lambda ctx, loc_id, squad_id: bounties.on_win(ctx.state, ctx.content, ctx.world, loc_id, squad_id)},\n"
           "             'outing': {'seal': lambda ctx, loc_id: ctx._seal_find(loc_id)}}\n"
           "def aid(s, c, who):\n    return bounties.on_aid(s, c, who) + bounties.mine(s, c)\n")
    assert bus_bypasses(old) == [2, 4, 4, 6, 8, 8, 10, 14]  # 14：人物託付第 45 批開成事件 aid，on_aid 也算訂閱者（mine 不算）


def _package_imports_of(source: str, module: str) -> list[tuple[int, str]]:
    """source（模組 module 的原文）裡 import 包（含舊名的別名）的 (行, 那一包)：同 _feature_imports，不讀檔（拿換之前的原文證明掃得到）。"""
    return sorted({(line, feature_target(mod)) for line, mod, _ in imports_of(source, module) if feature_target(mod) is not None})


def test_step_and_weekcard_joined_the_core_and_reach_no_package():
    """step、weekcard 在核心本體裡、一處都不 import 包、不讀換之前直接讀的那幾樣（糧車、最近的地點、伏筆的下一步）。先證明掃描看得到：
    換之前那幾行 import（split/trunk 8f86777e 的原文：weekcard 第 18、20 行、step 第 15 行）照這一條抓得到 5 處。"""
    assert {"step", "weekcard"} <= CORE
    for name in ("step", "weekcard"):
        assert _feature_imports(TIANXIA / f"{name}.py") == [], name
        tree = ast.parse((TIANXIA / f"{name}.py").read_text(encoding="utf-8"))
        assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & STEP_PACKAGE_READS, name
    old_weekcard = ("from . import calendar, chapters, errands, foreshadow, rules, storyline, week_unlock, wins\n"
                    "from . import step as step_rules\n"
                    "from . import opening as opening_rules\n"
                    "from . import prologue as prologue_rules\n")
    old_step = "from . import atlas, foreshadow, orders\nfrom .rules import jianfa\n"  # 第 45 批：bounties 成包之後多回一筆，拿掉（照第 40 批認定第 15 條），這個例子只驗 foreshadow 那一包
    assert _package_imports_of(old_weekcard, "tianxia.weekcard") == [(1, "companions"), (1, "military"), (1, "story"), (3, "guide")]
    assert _package_imports_of(old_step, "tianxia.step") == [(1, "military")]
    assert not [e for e in transitional_imports() if e.endswith(" tianxia.step") or e.endswith(" tianxia.weekcard")]
    assert not [e for e in reverse_imports() if e.startswith(("tianxia/step.py:", "tianxia/weekcard.py:"))]


def test_the_seven_joined_the_shared_layer_and_import_no_package_not_even_inside_a_function():
    """這一批收進共用規則層的七個：最外層與函式裡都不 import 包與舊名的別名（大勢人物的 figure_aid、宴客 feasts、出陣 sortie、一條線 storyline、
    軍情 foreshadow、opportunities 換成了核心的查詢服務 omen_base、feast_base、底座 story_base 與世界層的 life 那一格）。上面
    test_the_shared_rules_layer_is_real_old_modules_with_a_reason_and_never_imports_a_package 照 SHARED 掃到它們；這裡寫明七個，免得名單改了沒人發現。
    先證明掃描看得到函式裡的：換之前那幾行（figures.recover、figure_life.tick、orders.intercept_spots 的延後 import，chapters、rumor_view 的最外層）。"""
    assert set(SHARED_CORE_WORLD2) <= set(SHARED)
    for name in SHARED_CORE_WORLD2:
        assert _feature_imports(TIANXIA / f"{name}.py") == [], name
    old = ("from . import calendar, foreshadow, opportunities, orders\n"
           "from . import calendar, deeds, storyline, wins\n"
           "def recover():\n    from . import figure_aid\n"
           "def tick():\n    from .features.feast import rules as feasts\n"
           "def intercept_spots():\n    from . import sortie\n")
    assert _package_imports_of(old, "tianxia.figures") == [(1, "military"), (2, "story"), (4, "figure_acts"), (6, "feast"), (8, "sortie")]


def test_the_top_level_core_modules_reach_no_package_delegate_through_the_game():
    """「核心叫委派」那一條（test_the_core_modules_reach_no_package_delegate_through_ctx）只掃 tianxia/core/ 底下的 ctx.：擴到 MODULES 裡放在
    tianxia/ 頂層的模組（world、weekcard、step……），game.<委派> 照 ctx. 一樣算。掃到的只有 CORE_TOP_DELEGATE_CALLERS 那幾對（寫明哪一批收）。
    先證明掃描看得到 game 那個名字（預設只認 ctx 的照舊看不到）。"""
    found: set[tuple[str, str]] = set()
    for name in sorted(CORE):
        path = TIANXIA / f"{name}.py"
        if path.exists():
            found |= ctx_delegate_callers(path.read_text(encoding="utf-8"), name, names=("ctx", "game"))
    assert found == set(CORE_TOP_DELEGATE_CALLERS)
    assert all(isinstance(why, str) and why.strip() for why in CORE_TOP_DELEGATE_CALLERS.values())
    src = "def f(game):\n    return game._tavern_price(1)\n"
    assert ctx_delegate_callers(src, "m", names=("ctx", "game")) == {("m.f", "_tavern_price")}
    assert ctx_delegate_callers(src, "m") == set()


def condition_fields_touched(source: str) -> list[str]:
    """source 的 check_condition 裡碰到的包認領的欄位：["行 欄位（包）"]。條件本身的欄位（cond.<名>：Condition 的 clue_items 跟 PlayerState 的同名）不算。"""
    claimed = claimed_fields()
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "check_condition")
    return [f"{sub.lineno} {sub.attr}（{claimed[sub.attr]}）" for sub in ast.walk(fn)
            if isinstance(sub, ast.Attribute) and sub.attr in claimed and not (isinstance(sub.value, ast.Name) and sub.value.id == "cond")]


def test_check_condition_touches_no_package_field():
    """核心本體的 rules.check_condition 不直接讀包認領的欄位：一條線的記號（storylines）問共用規則層的 story_base.mark_of、伏筆物品
    （clue_items）問核心的查詢服務 omen_base.clue_count。先證明掃描看得到：換之前的寫法（split/trunk d4b36bf6 第 218～227、298 行）抓得到兩樣。"""
    assert condition_fields_touched((TIANXIA / "rules.py").read_text(encoding="utf-8")) == []
    old = ("def check_condition(cond, state, content=None):\n    p = state.player\n"
           "    for key, need in cond.story_marks.items():\n        progress = p.storylines.get(key)\n"
           "    if any(p.clue_items.get(k, 0) < v for k, v in cond.clue_items.items()):\n        return False\n")
    assert condition_fields_touched(old) == ["4 storylines（story）", "5 clue_items（military）"]


def test_atlas_joined_the_shared_layer_and_imports_no_package_not_even_inside_a_function():
    """atlas 在共用規則層裡、最外層與函式裡都不 import 包（出陣包 sortie、sortie_duel 換成共用層的 territory.on、conquest.duel_on），
    不直接讀換之前讀的 fs_asking、tagalong（改問核心的 omen_base.fs_answering、travel_base.following）；兩邊留的是同一個函式物件。
    先證明掃描看得到：換之前那三行（split/trunk febd38d8 的原文：atlas 第 17 行、siege_how 與 order_how 裡的延後 import）抓得到 3 處。"""
    from tianxia import conquest, sortie_duel
    from tianxia.core import omen_base, travel_base
    from tianxia.features.military import fs_rules
    from tianxia.features.sortie import duel_rules
    from tianxia.features.travel import party

    assert "atlas" in SHARED
    assert _feature_imports(TIANXIA / "atlas.py") == []
    tree = ast.parse((TIANXIA / "atlas.py").read_text(encoding="utf-8"))
    assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & ATLAS_PACKAGE_FIELDS
    assert duel_rules.on is conquest.duel_on and sortie_duel.on is conquest.duel_on
    assert fs_rules.fs_answering is omen_base.fs_answering and party.following is travel_base.following
    old = ("from . import allied, conquest, figures, insights, mounts, orders, prologue, sortie, terrain, territory\n"
           "def siege_how():\n    from . import sortie_duel\n"
           "def order_how():\n    from . import sortie_duel\n")
    assert _package_imports_of(old, "tianxia.atlas") == [(1, "sortie"), (3, "sortie"), (5, "sortie")]
    assert not [e for e in reverse_imports() if e.startswith("tianxia/atlas.py:")]


def private_touches(source: str) -> list[str]:
    """碰了別的物件私有成員的地方（x._y；self 的、雙底線的不算）。"""
    return [f"{node.lineno} {node.attr}" for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute) and node.attr.startswith("_")
            and not node.attr.startswith("__") and not (isinstance(node.value, ast.Name) and node.value.id == "self")]


def test_the_bot_shell_touches_nothing_private_on_the_game():
    """假人的殼（bot_policy、bot、bot_runner、server_bots）只走 Game 的公開行動與服務（總表第 60 列）：不准碰別的物件的私有成員。"""
    assert private_touches("def f(game):\n    return game._side()\n") == ["2 _side"]  # 掃描本身抓得到
    assert private_touches("class A:\n    def f(self):\n        return self._x, self.__class__\n") == []
    for name in ("bot_policy.py", "bot.py", "bot_runner.py", "server_bots.py"):
        assert private_touches((TIANXIA / name).read_text(encoding="utf-8")) == [], name


# core_bots（第二輪第 89 批）
def shell_imports(source: str, module: str) -> set[str]:
    """這個檔 import 了哪幾支假人殼：函式裡也算、標了「過渡：待搬」也算，if TYPE_CHECKING: 底下的不算（imports_of 已經略過）。"""
    return {name.split(".")[1] for _, name, _ in imports_of(source, module) if name.count(".") >= 1 and name.split(".")[1] in BOT_SHELL}


def test_no_package_imports_the_bot_shell():
    """假人殼（bot、bot_policy、bot_runner、server_bots）接在包的上面（第二輪第 89 批把包要讀的搬走了）：包再 import 就是跳回舊模組，延後 import 或標過渡都不放行。
    兩包以上讀的進共用層 bot_base，一包讀的進那一包的 bots.py。只准比 BOT_SHELL_PENDING 少，不准多。"""
    module = "tianxia.features.x.bots"
    assert shell_imports("def f():\n    from tianxia import bot_policy as bp\n", module) == {"bot_policy"}  # 掃描本身抓得到：函式裡的
    assert shell_imports("from tianxia import bot  # 過渡：待搬\n", module) == {"bot"}  # 標了過渡的
    assert shell_imports("def f():\n    from ...bot_runner import BotRunner\n", module) == {"bot_runner"}  # 相對的
    assert shell_imports("from tianxia.server_bots import active\n", module) == {"server_bots"}
    assert shell_imports("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from tianxia import bot\n", module) == set()  # 只給型別看的
    assert shell_imports("from tianxia import bot_base, botany\n", module) == set()  # 共用層 bot_base 不算
    found = {(_modname(path).removeprefix("tianxia.features."), shell) for name in _packages() for path in _package_files(name)
             for shell in shell_imports(path.read_text(encoding="utf-8"), _modname(path))}
    assert found <= BOT_SHELL_PENDING, f"包不准 import 假人殼：{sorted(found - BOT_SHELL_PENDING)}"


def test_bot_pick_asks_the_packages_for_what_it_skips():
    """bot.pick 的「永遠按得下去」只問各包的宣告（features_core.bot_idle）：act: 字面只剩沒有主人的 act:heal（第 57 批第四節）與挑戰本人照勝算挑那兩行（不是「永遠按得下去」，計畫第四節）。"""
    tree = ast.parse((TIANXIA / "bot.py").read_text(encoding="utf-8"))
    pick = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "pick")
    words = {node.value for stmt in pick.body[1:] for node in ast.walk(stmt) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert {w for w in words if w.startswith("act:")} == {"act:heal", "act:challenge:"}
    assert not {w for w in words if ":" in w} - {"act:heal", "act:challenge:", ":", "battle:join", "choice:"}  # 別的前綴也問宣告（加入決戰、結識一定接受不是「永遠按得下去」）


# 包的一行委派不在 engine.py 了，GAME_DELEGATES 改從各包 game_api.py 的 TABLE 讀（語法樹，不 import）。
@functools.lru_cache(maxsize=None)
def game_api_names() -> dict[str, str]:
    """各包 game_api.py 的 TABLE 上的名字 → 包。"""
    out: dict[str, str] = {}
    for path in sorted((TIANXIA / "features").glob("*/game_api.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        table = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TABLE")
        out.update({key.value: path.parent.name for key in table.keys})
    return out


GAME_DELEGATES = set(game_api_names())

# core_imports（第二輪第 98 批）：表上不是函式的那幾格
from boundary_tables import GAME_TABLE_TEXTS  # noqa: E402  自己這一段另 import：上面那一串別條線也在加


def test_the_prologue_fight_label_is_one_object_in_the_core():
    """序章那一場的字搬進核心（第 98 批）：單打服務、出陣包是同一個物件（engine 留的名字沒人讀，第 99 批拿掉）。"""
    from tianxia.core import combat, services
    from tianxia.features.sortie import rules

    assert services.PROLOGUE_FIGHT is rules.PROLOGUE_FIGHT is combat.PROLOGUE_FIGHT



def test_every_name_on_the_game_api_tables_hangs_a_function_of_that_package():
    """表上每一格掛在 Game 上的就是那個函式本身（不包）、住在那一包裡、第一個參數接 Game。GAME_TABLE_TEXTS 那幾格是字（第 98 批）：只驗掛上去的是它、是那一包的。"""
    from tianxia.core import features as features_core
    from tianxia.engine import Game

    assert set(game_api_names()) == {name for table in features_core.game_api_tables().values() for name in table}
    tables = features_core.game_api_tables()
    assert GAME_TABLE_TEXTS == {name: package for package, table in tables.items() for name, value in table.items() if isinstance(value, str)}
    for package, table in tables.items():
        for name, func in table.items():
            assert vars(Game)[name] is func, name
            if name in GAME_TABLE_TEXTS:
                continue
            assert func.__module__.startswith(f"tianxia.features.{package}"), name
            assert next(iter(inspect.signature(func).parameters)) in ("ctx", "game"), name


def test_attach_refuses_a_name_already_taken_and_hangs_nothing():
    from tianxia.core.features import attach_game_api

    class Host:
        def taken(self):
            return None

    with pytest.raises(ValueError, match="taken"):
        attach_game_api(Host, {"a": {"fresh": len, "taken": len}})
    with pytest.raises(ValueError, match="twice"):
        attach_game_api(Host, {"a": {"twice": len}, "b": {"twice": len}})
    assert not hasattr(Host, "fresh") and not hasattr(Host, "twice")
    attach_game_api(Host, {"a": {"fresh": len}})
    assert Host.fresh is len


def test_the_guarded_delegates_keep_the_preparing_refusal():
    from tianxia.core.services import not_while_preparing
    from tianxia.engine import Game

    guard = not_while_preparing(len).__code__
    assert all(vars(Game)[name].__code__ is guard for name in PREPARING_GUARDED)


def test_the_delegates_whose_parameter_names_differ_are_never_called_by_keyword():
    """write_biography(request…) 對 zhuan.actions.write(ctx, req…)、_ambush_record(…spoils…) 對 ambush_actions.record(…got…)：
    兩邊的名字都不准當關鍵字用；名單對得上本體，本體改名這裡會紅。"""
    from tianxia.engine import Game

    for name, (delegate_side, body_side) in RENAMED_PARAMS.items():
        params = inspect.signature(vars(Game)[name]).parameters
        assert body_side in params and delegate_side not in params, name
    roots = [p for base in ("tianxia", "tests", "scripts") for p in (TIANXIA.parent / base).rglob("*.py")]
    found = []
    for path in [*roots, TIANXIA.parent / "server.py", TIANXIA.parent / "run_bots.py"]:
        source = path.read_text(encoding="utf-8")
        if not any(name in source for name in RENAMED_PARAMS):
            continue
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in RENAMED_PARAMS
                    and {k.arg for k in node.keywords} & set(RENAMED_PARAMS[node.func.attr])):
                found.append(f"{path.name}:{node.lineno}")
    assert found == []


# ── core_api（第二輪第 74 批）：包與包之間的兩個鎖 ──


def _game_attrs(source: str):
    """原始碼裡每一個經 Game 碰的名字（node）：認法同 off_list_calls。"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and (
                node.value.id in CTX_NAMES or (node.value.id in GAME_ALIASES and node.attr in game_members())):
            yield node


def cross_package_calls(source: str, package: str) -> dict[tuple[str, str], set[str]]:
    """這一包經 Game 叫了別包的委派：{(這一包, 主人): {名字}}。只看第 72 批的表：Game 本體上的方法（例 _note_action）不算。"""
    owner = game_api_names()
    out: dict[tuple[str, str], set[str]] = {}
    for node in _game_attrs(source):
        if owner.get(node.attr, package) != package:
            out.setdefault((package, owner[node.attr]), set()).add(node.attr)
    return out


def _every_cross_package_call() -> dict[tuple[str, str], set[str]]:
    found: dict[tuple[str, str], set[str]] = {}
    for name in _packages():
        for path in _package_files(name):
            for pair, names in cross_package_calls(path.read_text(encoding="utf-8"), name).items():
                found.setdefault(pair, set()).update(names)
    return found


def test_the_calls_between_packages_are_exactly_the_written_list():
    """包經 Game 叫別包的委派，哪一對、哪幾個名字都在 CROSS_PACKAGE_CALLS（多了少了都紅）：跨包依賴看得到、擋得住。"""
    assert cross_package_calls("def f(ctx):\n    ctx.apply_letter(1, 2)\n", "tavern") == {("tavern", "companions"): {"apply_letter"}}
    assert cross_package_calls("def f(ctx):\n    ctx.apply_letter(1, 2)\n", "companions") == {}
    assert cross_package_calls("def f(ctx):\n    ctx._guide(['x'])\n", "tavern") == {}  # Game 本體的不算，只看表
    found = _every_cross_package_call()
    more = {pair: sorted(names - CROSS_PACKAGE_CALLS.get(pair, set())) for pair, names in found.items() if names - CROSS_PACKAGE_CALLS.get(pair, set())}
    less = {pair: sorted(names - found.get(pair, set())) for pair, names in CROSS_PACKAGE_CALLS.items() if names - found.get(pair, set())}
    assert not more, f"新的跨包呼叫：boundary_tables.py 的 CROSS_PACKAGE_CALLS 加這幾對，名字也要列在 services_list.md：{more}"
    assert not less, f"這幾對不再叫了：從 CROSS_PACKAGE_CALLS 拿掉：{less}"


@functools.lru_cache(maxsize=None)
def server_package_modules() -> tuple[tuple[str, str], ...]:
    """server.py 最外層 import 進來、指到功能包的名字：((名字, 包), ...)（feature_target 認別名）。"""
    out: dict[str, str] = {}
    for node in ast.parse((ROOT / "server.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            pairs = [(a.asname or a.name.split(".")[0], a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            pairs = [(a.asname or a.name, f"{node.module}.{a.name}") for a in node.names]
        else:
            continue
        out.update({name: target for name, mod in pairs if (target := feature_target(mod))})
    return tuple(out.items())


def foreign_shell_refs(source: str, package: str) -> set[tuple[str, str]]:
    """這一包的 shell.<名字> 指到別包（名字是 server.py 最外層 import 的模組）：{(這一包, 名字)}。server 頂上賦值出來的（map_base_view = map_views.map_base_view）不算。"""
    points = dict(server_package_modules())
    return {(package, node.attr) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "shell"
            and points.get(node.attr, package) != package}


def test_no_package_reaches_another_package_through_the_shell():
    """shell.<名字> 指到別包是繞過 ctx 的跨包，一處都不准（第二輪第 102 批收掉最後 4 列）。"""
    source = "def f(shell):\n    return shell.battle_instance.x\n"
    assert foreign_shell_refs(source, "tale") == {("tale", "battle_instance")}
    assert foreign_shell_refs(source, "battle") == set()
    assert foreign_shell_refs("def f(shell):\n    return shell.GAMES\n", "tale") == set()  # 殼自己的不算
    found: set[tuple[str, str]] = set()
    for name in _packages():
        for path in _package_files(name):
            found |= foreign_shell_refs(path.read_text(encoding="utf-8"), name)
    assert found == set(), f"經殼碰別包的模組，改走核心或 ctx 服務：{sorted(found)}"


def service_list_leftovers() -> list[str]:
    """清單上沒有包叫、或只有主人自己叫的名字：merge=union 會留該刪的舊行，PM 每波清一次（多的名字只讓放行變寬、不會紅，所以不做成紅燈）。"""
    callers: dict[str, set[str]] = {}
    for name in _packages():
        for path in _package_files(name):
            for node in _game_attrs(path.read_text(encoding="utf-8")):
                callers.setdefault(node.attr, set()).add(name)
    owner = game_api_names()
    return sorted(name for name in service_list() if not callers.get(name, set()) - {owner.get(name)})


# core_shared（第二輪第 88 批：skillview 切成三處，留下來的殼只給測試；殼不能藏跨包）
from boundary_tables import TEST_ONLY_SHELLS  # noqa: E402  自己這一段另 import：上面那一串別條線也在加


def _shell_imports(source: str, module: str) -> set[str]:
    """source（模組 module 的原文）import 了哪幾個只留給測試的殼；最外層與函式裡都算，TYPE_CHECKING 底下不算（imports_of）。"""
    shells = {f"tianxia.{name}" for name in TEST_ONLY_SHELLS}
    return {name for _, name, _ in imports_of(source, module)} & shells


def test_product_code_does_not_import_a_test_only_shell():
    """產品程式（tianxia/ 底下除了測試，加 server.py、run_bots.py）一律讀真正的位置：共用層 art_cards、修練包 art_view、煉製包 forge_view。"""
    paths = [p for p in TIANXIA.rglob("*.py") if "tests" not in p.relative_to(TIANXIA).parts] + [ROOT / "server.py", ROOT / "run_bots.py"]
    found = {path.relative_to(ROOT).as_posix(): sorted(hit) for path in paths if (hit := _shell_imports(path.read_text(encoding="utf-8"), _modname(path)))}
    assert not found, f"這幾個檔 import 了只留給測試的殼，改讀真正的位置：{found}"


def test_the_shell_scanner_catches_a_fake_import():
    """上面那一條的掃描抓得到（不然永遠綠）：相對、絕對、函式裡都算；別的模組與 TYPE_CHECKING 底下不算。"""
    module = "tianxia.features.craft.actions"
    assert _shell_imports("from tianxia import skillview\n", module) == {"tianxia.skillview"}
    assert _shell_imports("def f():\n    from tianxia.skillview import art_card\n", module) == {"tianxia.skillview"}
    assert _shell_imports("def f():\n    from ... import skillview\n", module) == {"tianxia.skillview"}
    assert not _shell_imports("from tianxia import art_cards\n", module)
    assert not _shell_imports("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from tianxia import skillview\n", module)


if __name__ == "__main__":  # PM 記「還剩幾處過渡」（3.11）：python tests/core/test_feature_boundaries.py
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for title, rows in (("包 → 舊模組（transitional_imports）", transitional_imports()), ("舊模組 → 包（reverse_imports）", reverse_imports())):
        print(f"{title}：{len(rows)} 處")
        print("\n".join(f"  {r}" for r in rows))
    print(f"Game 碰包：委派 {len(GAME_DELEGATES)} 個、直連 {len(GAME_DIRECT) + len(GAME_DELEGATE_CALLERS)} 處"
          f"（GAME_DIRECT {len(GAME_DIRECT)}、GAME_DELEGATE_CALLERS {len(GAME_DELEGATE_CALLERS)}）；GAME_IMPORTS {len(GAME_IMPORTS)}")
    print(f"共用規則層（registry.SHARED）：{len(SHARED)} 個模組（{'、'.join(sorted(SHARED))}）")
    # shared（第 15 批）
    print(f"共用規則層碰到的別的舊模組（SHARED_PENDING）：{len(SHARED_PENDING)} 條"
          f"（排定 {sum(w.startswith('排定：') for w in SHARED_PENDING.values())}、"
          f"之後成包 {sum(w.startswith('之後成包：') for w in SHARED_PENDING.values())}）")
    print("\n".join(f"  {a} → {b}" for a, b in sorted(SHARED_PENDING)))
    print(f"總表寫了、先不收的（SHARED_LATER）：{len(SHARED_LATER)} 個（{'、'.join(sorted(SHARED_LATER))}）")
    # core_api（第二輪第 74 批）
    print(f"跨包經 Game（CROSS_PACKAGE_CALLS）：{len(CROSS_PACKAGE_CALLS)} 對、{len(set().union(*CROSS_PACKAGE_CALLS.values()))} 個名字")
    print(f"服務清單上沒有包叫或只有主人叫（PM 每波清一次）：{len(service_list_leftovers())} 個（{'、'.join(service_list_leftovers())}）")
