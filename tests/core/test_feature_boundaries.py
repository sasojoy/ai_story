"""功能包的邊界（開發規範手冊 3.4 第 1 條、3.11）：用 ast 掃 import，幾毫秒。

- 功能包（tianxia/features/<包>/，tests/ 不算）只能 import 核心（tianxia/core/ 與 CORE 那幾個模組）、自己這一包、標準庫與第三方；
  不能 import 別的包。還沒搬的舊模組過渡期可以 import，那一行要註「# 過渡：待搬」（第一版只禁「包 import 包」與沒註的舊模組）。
- 核心不 import 功能包：tianxia/core/ 只有 registry.py（FEATURES 登記）可以，CORE 那幾個模組都不行。
- if TYPE_CHECKING: 底下的 import 只給型別看，不算。
- 網頁框架（fastapi）只有功能包的 routes.py 可以 import，而且只在殼掛路由時延後 import；引擎、run_bots、假人不碰（PM 10/31）。
"""
from __future__ import annotations

import ast
import functools
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
        if name == "tianxia" or parts[1] == "core" or parts[1] in CORE:
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


# 瘦下來的 Game（engine.py）也是核心（手冊 3.1）。3.10 准它留一行的委派，所以它是核心裡唯一另外 import 包的地方：只准下面這幾樣，
# 多一處就紅（要接一包先想掛鉤；真的要過渡就加進這裡、回報寫明）。第 2 階呼叫端改叫包、委派拿掉時從這裡刪。
GAME_IMPORTS = {
    "tianxia.features.mall.actions", "tianxia.features.feast.actions",
    # 出陣（主動搬六包第 1 批）：13 個一行委派；原本那一行 `from . import (..., sortie, ...)` 現在是別名（engine 照舊叫 sortie.on、
    # sortie.NAME 這些字，見 GAME_DIRECT）；混戰的字搬進包，tests/ranger/test_raid.py 照舊從 engine 拿那三個
    "tianxia.features.sortie.actions", "tianxia.sortie", "tianxia.features.sortie.rules",
    # 出陣約戰（主動搬六包第 2 批）：16 個一行委派；原本那一行 `from . import sortie_duel` 現在是別名（choose 照舊讀 PREFIX、PICK）
    "tianxia.features.sortie.duel_actions", "tianxia.sortie_duel",
    "tianxia.features.looks.actions",  # 擂台形象：Game.arena_look 一行委派（擂台報名、開打記穿哪一套）
}
GAME_DELEGATES = {  # 一行的委派（server 與測試照舊叫 Game）
    "arena_look",  # 擂台形象（looks）
    "mall_buy", "mall_entry", "mall_rename_left", "mall_rename", "mall_claim", "mall_view", "mall_records",
    "admin_mall_reissue", "admin_mall_revoke", "admin_mall_refund", "admin_mall_ledger", "_mall_grant",
    "feast_free_text_prompt", "feast_text_request", "feast_toast",
    # 出陣（主動搬六包第 1 批；10 個私有，第 1 批記成 9 個是少算了一個）：server、假人、腳本、測試在叫的 9 個，與核心原位在叫的 4 個
    # （_train_title、_sortie_mode、_sortie_option、_sortie）。這一輪私有的也留（批次表第二節「偏離手冊第三節的」）
    "sorties_left", "_sortie_foes", "sortie_mode", "sortie_progress", "_sortie_host", "_sortie_hold", "_sortie_line", "_melee_record",
    "_sortie_rewards", "_train_title", "_sortie_mode", "_sortie_option", "_sortie",
    # 出陣約戰（主動搬六包第 2 批；7 個私有）：server、假人、腳本、測試在叫的 11 個（duel_on、_duel_power、duel_convoy_here、_duel_squad、
    # sortie_go_problem、sortie_go、sortie_answer、sortie_join、sortie_cards、sortie_card、sortie_duel_tick），與只有核心原位在叫的 5 個
    # （_duel_line、_duel_entry、_duel_choice、_sortie_duel_tick、_duty_credit；duel_on、_duel_squad 核心原位也叫）
    "duel_on", "_duel_power", "duel_convoy_here", "_duel_squad", "sortie_go_problem", "sortie_go", "sortie_answer", "sortie_join",
    "sortie_cards", "sortie_card", "sortie_duel_tick", "_duel_line", "_duel_entry", "_duel_choice", "_sortie_duel_tick", "_duty_credit",
}
_SORTIE_SEAM = "接縫留在原位（批次表第二節：會影響先後的接縫這一輪不開掛鉤，第 11 批一次收）"
GAME_DIRECT = {  # 核心自己的邏輯直接叫包（沒有對應的掛鉤；過渡）
    "_own_scene_text": "坐在宴席上的場景卡（feast_actions.scene）：場景卡還沒有掛鉤；搬包之前也不看宴客開關",
    # 出陣（主動搬六包第 1 批）：下面這些方法用到 sortie 這個名字（現在是出陣包 rules 的別名）——開關（sortie.on＝territory.on）、
    # 鈕上的字（NAME、USED_UP、LEFT_NOTE、OUT_NOTE……）、次數（spend）
    "_act": f"act:train 的分派（約戰開著走 _duel_entry、出陣開著走 _sortie、序章與關著走 _train；並肩出陣包在外面）：act 是核心的前綴；"
            f"{_SORTIE_SEAM}",
    "_everyday_options": f"行動列那一格（雪恥／遊歷／出陣、散人與不在爭奪之列的灰格，叫 _sortie_option）：選項的位置算行為；{_SORTIE_SEAM}",
    "action_notes": f"行動列底下那一行（約戰開著叫 _duel_line、出陣開著叫 _sortie_line，關著是遊歷那一行）；{_SORTIE_SEAM}",
    "_squad_encounter": "戰鬥（as_sortie 那一支）：序章的戰報標題寫雪恥（sortie.PROLOGUE_FIGHT）、打贏回頭叫 _sortie_rewards（那一對記在 "
                        "GAME_DELEGATE_CALLERS）；等戰鬥搬成包時變成核心的事件",
    "_train_squad_ids": "舊遊歷與出陣共用的對手池（出陣開著時只有攻才打，叫 _sortie_mode、_sortie_foes）",
    "_duty_option": "守勢行動（巡哨、傳道、保境安民）共用出陣的次數與鈕上的字（sortie.duty_problem、USED_UP、LEFT_NOTE；叫 sorties_left）",
    "_duty": "守勢行動算一次出陣（sortie.spend；叫 _sortie_host 拿自家那一路的數字）",
    "map_state": "輿圖（今天去哪裡出陣：sortie.on、叫 _sortie_foes、sorties_left）；輿圖的線還在飛，這一輪不碰",
    "_map_foes": "輿圖的地點卡（出陣打誰：sortie.on、叫 _sortie_foes）；同上",
    # 出陣約戰（主動搬六包第 2 批）：用到 sortie_duel 這個名字（現在是出陣包 duel_rules 的別名）的只剩 choose
    "choose": "選單外的前綴（sortie_duel.PREFIX：sortie:go／answer／join 在查選單、建 Draft 之前接走，叫 _duel_choice）與按出陣那一格只回 "
              f"sortie_duel.PICK 時不寫紀錄（picked_only、quiet 兩處）：choose 的掛鉤在驗過選單之後才問包，順序不一樣；{_SORTIE_SEAM}",
}
GAME_DELEGATE_CALLERS = {  # 核心自己的邏輯叫委派（同上）。GAME_DIRECT 的方法裡叫的也列（PM 10/31 答覆出陣第 1 批，第 2 批起）
    ("own_turn_checks", "_mall_grant"): "封測元寶每一輪發（本人這一輪沒有掛鉤；on_sync 不夠：假人程式的那一輪不 sync）",
    ("_arena_join", "arena_look"): "擂台形象：報名、更新分身時記穿哪一套（擂台還在核心；擂台搬成包時改成形象包的查詢服務）",
    ("_arena_start", "arena_look"): "擂台形象：挑人開打時記挑的人穿哪一套（同上）",
    # 出陣（主動搬六包第 1 批）：核心叫出陣委派 13 對（第 1 批時一共 21 對、掃描只看得到 6 對；約戰自己叫的 8 對第 2 批跟著進了包）
    ("_action_title", "_train_title"): "這一下的紀錄標題先算（act:train 是核心的前綴，標題照出陣開著沒、序章寫出陣／雪恥／遊歷）",
    ("_outing_foe", "_sortie_host"): "走一趟（探索）在自家營寨遇上的是自家那一路（出陣的守拿的同一路）；探索搬成包時改成查詢服務",
    ("_act", "_sortie"): f"act:train 的分派：出陣開著走出陣（並肩出陣、扣體力包在外面）；{_SORTIE_SEAM}",
    ("_everyday_options", "_sortie_option"): f"行動列那一格（雪恥／遊歷／出陣）：選項的位置算行為；{_SORTIE_SEAM}",
    ("action_notes", "_sortie_line"): f"行動列底下出陣那一行；{_SORTIE_SEAM}",
    ("_squad_encounter", "_sortie_rewards"): "戰鬥（as_sortie）打贏給出陣的獎勵；等戰鬥搬成包時變成核心的事件",
    ("_train_squad_ids", "_sortie_mode"): "舊遊歷與出陣共用的對手池：出陣開著時只有攻才打",
    ("_train_squad_ids", "_sortie_foes"): "同上：攻打的對手",
    ("_duty_option", "sorties_left"): "守勢行動共用出陣的次數（鈕上寫今天還能幾次）",
    ("_duty", "_sortie_host"): "守勢行動拿自家那一路的經驗心得（一類一顆）",
    ("map_state", "_sortie_foes"): "輿圖（今天去哪裡出陣）：出陣那一格是哪一種；輿圖的線還在飛，這一輪不碰",
    ("map_state", "sorties_left"): "輿圖：今天還能出陣幾次",
    ("_map_foes", "_sortie_foes"): "輿圖的地點卡：約戰關著時出陣打的那一批",
    # 出陣約戰（主動搬六包第 2 批）：核心叫約戰委派 17 對（搬之前約戰自己叫出陣委派的 8 對跟著進了包）
    ("world_tick", "_sortie_duel_tick"): "伺服器排程那一下結算到時的約戰：追完共用賽季之後、領地爭奪換天之前（三處結算的位置算行為：作廢退體力"
                                         f"與回體力誰先誰後夾上限的結果不同；這一輪不開「世界推進」的掛鉤）；{_SORTIE_SEAM}",
    ("sync", "_sortie_duel_tick"): f"排程關著時下一個同步的人替窗滿了的約戰結算：追完共用賽季之後、_stamp_join 之前；同上；{_SORTIE_SEAM}",
    ("advance", "_sortie_duel_tick"): f"快轉（管理者、整季機器人只 advance）：_deliver_conquest 之後、_save_season 之前；同上；{_SORTIE_SEAM}",
    ("choose", "duel_on"): "sortie:* 在查選單之前接走：約戰關著的季照舊當成不在選單上（見 GAME_DIRECT 的 choose）",
    ("choose", "_duel_choice"): "同上：貼、應戰、同去三個動詞",
    ("_act", "duel_on"): f"act:train 的分派：約戰開著（序章以外）出陣那一格只打開出陣前那張卡；{_SORTIE_SEAM}",
    ("_act", "_duel_entry"): "同上：截糧的運糧隊經過時照舊攻打（體力在裡面扣）",
    ("action_notes", "duel_on"): f"行動列底下出陣那一行：約戰開著換約戰那一句；{_SORTIE_SEAM}",
    ("action_notes", "_duel_line"): "同上",
    ("_fight_squad", "duel_on"): "大場面判讀：約戰開著時出陣那一格不判（不會打仗）",
    ("_duty_option", "duel_on"): "守勢行動的鈕：約戰開著時收進此地、不佔出陣的次數",
    ("_duty", "duel_on"): "守勢行動：約戰開著時不佔出陣、不推線、不算守城",
    ("_duty", "_duty_credit"): "同上：一天記一點貢獻（企劃者 2026-10-24 第 2 件）",
    ("_squad_encounter", "duel_on"): "戰鬥（as_sortie）：約戰開著時只剩截糧，打贏不推進度（進度只在約戰結算動）",
    ("map_state", "duel_on"): "輿圖：約戰開著時不畫零風險的守、攻不了的不推薦、運糧隊經過的帶 convoy；輿圖的線還在飛，這一輪不碰",
    ("_map_foes", "duel_on"): "輿圖的地點卡：約戰開著時列貼約戰會迎戰的守軍那一路",
    ("_map_foes", "_duel_squad"): "同上：守軍那一路（經驗最高的那一路）",
}


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
    return frozenset(names)


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
               and n.attr in direct and n.attr != f.name}
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


def test_the_game_reaches_the_packages_only_through_the_listed_methods():
    """Game 碰包的地方只有：一行的委派（3.10）、寫明了的過渡直連（GAME_DIRECT、GAME_DELEGATE_CALLERS）。其餘一律走 FEATURES 的掛鉤。"""
    imports, direct, callers = game_links()
    assert imports == GAME_IMPORTS
    assert direct == GAME_DELEGATES | set(GAME_DIRECT)
    assert {(caller, callee) for caller, callee in callers if callee in GAME_DELEGATES} == set(GAME_DELEGATE_CALLERS)


def reverse_imports() -> list[str]:
    """另一個方向的過渡（3.11）：還沒搬的舊模組、伺服器、腳本 import 功能包（含經過舊名的別名、Game 的委派那兩行）。
    PM 每搬一包在交接記還剩幾處，跟 transitional_imports()（包 import 舊模組）兩個方向都記；核心的 registry.py 不算。"""
    files = [p for p in sorted(TIANXIA.glob("*.py"))] + [ROOT / "server.py", ROOT / "run_bots.py"] + sorted((ROOT / "scripts").rglob("*.py"))
    out = []
    for path in files:
        if path.exists():
            out += [f"{path.relative_to(ROOT).as_posix()}:{line} {mod}" for line, mod in _feature_imports(path)]
    return out


def test_the_reverse_transitional_imports_come_from_old_modules():
    """舊模組 → 包那一向：都在還沒搬的舊模組、殼與腳本裡（核心的只有 engine.py 准的那兩行），而且數得到（不然交接記的數是空的）。"""
    found = reverse_imports()
    assert any(e.startswith("tianxia/engine.py:") for e in found) and any(e.startswith("server.py:") for e in found)
    for entry in found:
        stem = entry.split(":", 1)[0].removeprefix("tianxia/").removesuffix(".py")
        assert stem not in CORE or entry.rsplit(" ", 1)[1] in GAME_IMPORTS, entry


def transitional_imports() -> list[str]:
    """過渡期的 import（包 import 還沒搬的舊模組）：PM 每搬一包在交接記還剩幾處（手冊 3.11）。"""
    out = []
    for name in _packages():
        for path in _package_files(name):
            seen = {(line, ".".join(mod.split(".")[:2])) for line, mod, marked in imports_of(path.read_text(encoding="utf-8"), _modname(path))
                    if marked and mod != "tianxia" and _module_exists(".".join(mod.split(".")[:2])) and mod.split(".")[1] not in aliases()}
            out += [f"{_modname(path)}:{line} {mod}" for line, mod in sorted(seen)]
    return out


def test_every_transitional_import_points_at_an_old_module_not_the_core_or_a_package():
    """註了「過渡：待搬」的那一行真的是舊模組：搬完了（變成核心或包）就把註拿掉。"""
    for entry in transitional_imports():
        mod = entry.rsplit(" ", 1)[1].split(".")
        assert mod[1] not in CORE and mod[1] not in ("core", "features") and mod[1] not in aliases(), entry


SERVICES = TIANXIA / "core" / "services.py"
CTX_NAMES = ("ctx", "g", "game")  # 功能包裡拿 Game 的變數名（掛鉤的 ctx、路由 lambda 的 g、路由裡的 game）
# 約戰結算（出陣包 duel_actions.duel_result，主動搬六包第 2 批）另外兩份 Game 叫 attacker、defender（軍令 _order_credit 叫在它們上面）。
# 包裡同名的也有約戰的一方（duel_rules 的 attacker、defender 是 SortieSide：attacker.model_copy），所以這兩個名字只算 Game 上真的有的名字
GAME_ALIASES = ("attacker", "defender")


def service_list() -> set[str]:
    """tianxia/core/services.py docstring 那張服務清單上的名字（寫成 `ctx.<名字>` 的）。"""
    return set(re.findall(r"`ctx\.(\w+)", ast.get_docstring(ast.parse(SERVICES.read_text(encoding="utf-8"))) or ""))


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


def test_feature_packages_only_touch_the_service_list_on_the_game():
    """功能包經過 Game 只碰服務清單上的（手冊 3.3）：Game.mall_* 這一類委派是給還沒改的呼叫端過渡用的（3.10），包自己直接叫自己的 actions。"""
    allowed = service_list()
    assert {"state", "content", "_log", "_wallet", "wallet"} <= allowed  # 清單讀得到
    found = []
    for name in _packages():
        for path in _package_files(name):
            found += off_list_calls(path.read_text(encoding="utf-8"), _modname(path), allowed)
    assert found == []


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


@pytest.mark.parametrize("source, expected", [
    ("from tianxia.features import feast\n", "別的包"),
    ("from tianxia.features.feast import rules\n", "別的包"),
    ("from ..feast import rules\n", "別的包"),
    ("from tianxia import library\n", "舊模組"),
    ("from tianxia import engine\n", "舊模組"),
    ("import tianxia.zhuan_end\n", "舊模組"),
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
    """tianxia/mall.py、tianxia/feasts.py、tianxia/sortie.py、tianxia/sortie_duel.py 是指到包裡同一個模組的別名（給還沒改的測試與舊模組）：
    掃描照它們指到的那一包算，不算舊模組。"""
    assert aliases() == {"feasts": "feast", "mall": "mall", "sortie": "sortie", "sortie_duel": "sortie"}
    assert not [e for e in transitional_imports() if e.rsplit(" ", 1)[1].split(".")[1] in aliases()]


@pytest.mark.parametrize("source", [
    "from tianxia import library  # 過渡：待搬\n",
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


if __name__ == "__main__":  # PM 記「還剩幾處過渡」（3.11）：python tests/core/test_feature_boundaries.py
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for title, rows in (("包 → 舊模組（transitional_imports）", transitional_imports()), ("舊模組 → 包（reverse_imports）", reverse_imports())):
        print(f"{title}：{len(rows)} 處")
        print("\n".join(f"  {r}" for r in rows))
    print(f"Game 碰包：委派 {len(GAME_DELEGATES)} 個、直連 {len(GAME_DIRECT) + len(GAME_DELEGATE_CALLERS)} 處")
