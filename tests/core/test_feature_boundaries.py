"""功能包的邊界（開發規範手冊 3.4 第 1 條、3.11）：用 ast 掃 import，幾毫秒。

- 功能包（tianxia/features/<包>/，tests/ 不算）只能 import 核心（tianxia/core/ 與 CORE 那幾個模組）、共用規則層（registry.SHARED，第 11 批）、
  自己這一包、標準庫與第三方；不能 import 別的包。還沒搬的舊模組過渡期可以 import，那一行要註「# 過渡：待搬」（第一版只禁「包 import 包」
  與沒註的舊模組）；註了的那一行要真的有一個還沒搬的舊模組（全是核心、共用規則層的就把註拿掉）。
- 核心不 import 功能包：tianxia/core/ 只有 registry.py（FEATURES 登記）可以，CORE 那幾個模組都不行；共用規則層的模組也不行
  （它們 import 的別的舊模組總表第 15 批登記進同一層之後再守「只 import 核心本體與同一層」）。
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
from tianxia.core.registry import SHARED  # noqa: E402  共用規則層（第 11 批）：模組名 → 為什麼在共用層
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


# 瘦下來的 Game（engine.py）也是核心（手冊 3.1）。3.10 准它留一行的委派，所以它是核心裡唯一另外 import 包的地方：只准下面這幾樣，
# 多一處就紅（要接一包先想掛鉤；真的要過渡就加進這裡、回報寫明）。第 2 階呼叫端改叫包、委派拿掉時從這裡刪。
GAME_IMPORTS = {
    # explore（主動搬六包第 3＋4 批）：走一趟 9 個、探索一顆 9 個一行委派；原本那一行 `from . import outing as outing_rules` 現在是別名
    # （有所感照舊讀 rare_boost，見 GAME_DIRECT 的 _sense）；原本的 `from . import explore_one` 拿掉了（engine 不再用它）
    "tianxia.features.explore.outing_actions", "tianxia.features.explore.explore_actions", "tianxia.outing",
    "tianxia.features.mall.actions", "tianxia.features.feast.actions",
    # 出陣（主動搬六包第 1 批）：13 個一行委派；原本那一行 `from . import (..., sortie, ...)` 現在是別名（engine 照舊叫 sortie.on、
    # sortie.NAME 這些字，見 GAME_DIRECT）；混戰的字搬進包，tests/ranger/test_raid.py 照舊從 engine 拿那三個
    "tianxia.features.sortie.actions", "tianxia.sortie", "tianxia.features.sortie.rules",
    # 出陣約戰（主動搬六包第 2 批）：16 個一行委派；原本那一行 `from . import sortie_duel`（別名，choose 讀 PREFIX、PICK）第 11 批
    # 換成 choose_unlisted 與 Verb.picks 之後沒人用，拿掉
    "tianxia.features.sortie.duel_actions",
    # battle
    # 全服決戰「看」那一半（主動搬六包第 5 批）：22 個一行委派（view）；rules 給測試從 engine 拿的 6 個字、委派的型別註記，與 Game 的類別屬性
    # BATTLE_GAMBLE_NOTE／LAST（類別本體不是方法，game_links 掃不到那兩行，記在這裡）
    "tianxia.features.battle.view", "tianxia.features.battle.rules",
    # 決戰「打」那一半之一（全部拆包第 6 批）：管理者的決戰工具 6 個、攻城 6 個一行委派
    "tianxia.features.battle.admin", "tianxia.features.battle.sieges",
    "tianxia.features.looks.actions",  # 擂台形象：Game.arena_look、arena_move 一行委派（擂台報名、開打記穿哪一套、疊哪一張光效）
}
GAME_DELEGATES = {  # 一行的委派（server 與測試照舊叫 Game）
    "arena_look",  # 擂台形象（looks）
    "arena_move",  # 招式動畫（looks）
    "_battle_ult", "_round_mvp",  # 決戰的回合 MVP（looks；Joy 11/3「決戰現在做，改動壓到最少」）：放手一搏送出記絕招、回合結算包一層挑人
    # explore（主動搬六包第 3＋4 批）：走一趟 9 個（1 個私有）——server、bot、bot_policy、測試在叫的 8 個，與 engine 模組層的 _outing_watch
    # （套在 choose、answer_event、epiphany_names、sense_draw 上；不是 Game 的方法，掃描看不到）叫的 _outing_watched
    "outing_go", "outing_view", "outing_can_go", "_outing_watched", "outing_say", "outing_tale_request", "outing_set_tale",
    "outing_ink_left", "admin_erase_inscription",
    # 探索一顆 9 個（5 個私有）：核心原位在叫的 5 個（_outing_on：_act、_action_title、_everyday_options、action_notes；_outing_plan：
    # action_notes；_outing_option：_everyday_options；_explore_one：_act；map_mostly：map_base、map_state），server、bot_policy、腳本、
    # 測試在叫的 mostly_here、outing_plan、fatigue_next、_outing_fight（出陣包經 ctx 叫 _outing_on、包裡經 ctx 叫 _outing_plan、outing_plan）。
    # 第 11 批（核心收接縫）：_act、_action_title、_everyday_options、action_notes 那幾行換成 act 子動詞的掛鉤（Verb），_outing_option、
    # _explore_one 沒人叫了，拿掉（_outing_on、_outing_plan 是服務清單上的，出陣包與測試在用，留著）
    "_outing_on", "_outing_plan", "mostly_here", "outing_plan", "map_mostly", "_outing_fight",
    "fatigue_next",
    "mall_buy", "mall_entry", "mall_rename_left", "mall_rename", "mall_claim", "mall_view", "mall_records",
    "admin_mall_reissue", "admin_mall_revoke", "admin_mall_refund", "admin_mall_ledger",  # _mall_grant：第 11 批換成 on_own_turn，拿掉
    "feast_free_text_prompt", "feast_text_request", "feast_toast",
    # 出陣（主動搬六包第 1 批；10 個私有，第 1 批記成 9 個是少算了一個）：server、假人、腳本、測試在叫的 9 個，與核心原位在叫的 4 個
    # （_train_title、_sortie_mode、_sortie_option、_sortie）。這一輪私有的也留（批次表第二節「偏離手冊第三節的」）。第 11 批：行動列那一格、
    # 紀錄標題換成 act 子動詞的掛鉤，_train_title、_sortie_option 沒人叫了，拿掉
    "sorties_left", "_sortie_foes", "sortie_mode", "sortie_progress", "_sortie_host", "_sortie_hold", "_sortie_line", "_melee_record",
    "_sortie_rewards", "_sortie_mode", "_sortie",
    # 出陣約戰（主動搬六包第 2 批；7 個私有）：server、假人、腳本、測試在叫的 11 個（duel_on、_duel_power、duel_convoy_here、_duel_squad、
    # sortie_go_problem、sortie_go、sortie_answer、sortie_join、sortie_cards、sortie_card、sortie_duel_tick），與只有核心原位在叫的 5 個
    # （_duel_line、_duel_entry、_duel_choice、_sortie_duel_tick、_duty_credit；duel_on、_duel_squad 核心原位也叫）。
    # 第 11 批（核心收接縫）：三處結算換成 on_due 掛鉤，_sortie_duel_tick 沒人叫了，拿掉；choose 前段換成 choose_unlisted，_duel_choice 拿掉；
    # 行動列底下那一行與按出陣那一格換成 act 子動詞的掛鉤，_duel_line、_duel_entry 拿掉
    "duel_on", "_duel_power", "duel_convoy_here", "_duel_squad", "sortie_go_problem", "sortie_go", "sortie_answer", "sortie_join",
    "sortie_cards", "sortie_card", "sortie_duel_tick", "_duty_credit",
    # battle
    # 全服決戰「看」那一半（主動搬六包第 5 批；11 個私有）：server 叫的 12 個（main_view 的戰局條、攻城條、輸入框，reports_view，放手一搏與
    # 補劇情的三段式，_tales_waiting）、核心原位叫的 4 個（_battle_scene_text、_round_blocks、_round_wait、_deliver_battle_results），
    # 只有測試直接叫的 6 個（_file_showdown、_annal_showdown、_showdown_pay、_showdown_credits、_showdown_tier4、_battle_spotlight）。
    # 第 11 批：戰報頁換成 record_detail 掛鉤，_round_blocks 沒人叫了，拿掉（_battle_scene_text 測試直接叫，留著）
    "_battle_scene_text", "_round_wait", "_battle_spotlight", "battle_gauge", "siege_banner", "record_gauge", "card_gauge",
    "battle_on_screen", "_deliver_battle_results", "_file_showdown", "_annal_showdown", "_showdown_pay", "_showdown_credits", "_showdown_tier4",
    "battle_free_text_prompt", "battle_free_text_note", "battle_text_request", "submit_battle_custom_action", "battle_tale_request",
    "apply_battle_tales", "_tale_battles",
    # 決戰「打」那一半之一（全部拆包第 6 批；6 個私有）：server 與測試叫的管理者工具 6 個（ADMIN_ACTIONS 的 start_battle、cancel_battle、
    # start_showdown，admin_choices 的立刻開戰選單與三場大戲，timetable_choices 的開打後取消），核心原位叫的攻城 6 個（_definition_of、
    # _tick_siege 測試也直接叫）。_showdown_refusal、_siege_guards 只有包裡叫，沒有委派
    "admin_battles", "admin_start_battle", "admin_cancel_battle", "admin_showdowns", "cancelled_showdowns", "admin_start_showdown",
    "_sieges", "_definition_of", "_tick_siege", "_shelve_siege", "_cancel_siege", "_settle_siege",
}
# 第 11 批（全部拆包「核心收接縫」，計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.2）之後留下的直連：核心的接縫（選單、補算時間、
# 行動列與 act 子動詞、choose 前後段、本人這一輪、場景卡、戰報頁、店面）都換成了接縫掛鉤（tianxia/core/features.py），留下的都不是核心
# 自己的接縫——還沒搬的別的功能（或同一包還沒搬的那一半）叫包。每一條寫「為什麼留、哪一批收」；「打完之後」那一種（一包發生了、別包跟著動）
# PM 定這一批不開掛鉤，原位行尾標「# 過渡：第 26 批」（事件機制）。
_LATER_17 = "出陣自己還沒搬的那一半（舊遊歷、序章雪恥、守勢；act:train 整格）：總表第 17 批（出陣三）收進出陣包"
_MAP_LINE = "輿圖的線（feature/map-view）還在飛，這一輪不碰；輿圖成包（總表第 46～50 批）時改叫出陣、探索的查詢服務"
GAME_DIRECT = {  # 核心自己的邏輯直接叫包（沒有對應的掛鉤；過渡）
    # explore（主動搬六包第 3＋4 批）：用到 outing 這個名字（現在是探索包 outing_rules 的別名）的只剩有所感
    "_sense": "有所感畫完那一筆擲特殊頓悟（epiphany.roll 的 boost＝outing_rules.rare_boost：走一趟段數越多越容易來）：有所感還沒成包"
              "（總表第 24 批）；成包時探索包開「此刻稀有的乘多少」的查詢服務，改叫它",
    # （_own_scene_text：坐在宴席上的場景卡第 11 批換成 scene 掛鉤，拿掉）
    # 出陣（主動搬六包第 1 批）：下面這些方法用到 sortie 這個名字（現在是出陣包 rules 的別名）——開關（sortie.on＝territory.on）、
    # 鈕上的字（NAME、USED_UP、LEFT_NOTE、OUT_NOTE……）、次數（spend）
    "_act": "act:train 打的那一場（出陣開著走 _sortie、序章與關著走 _train）：扣體力、並肩出陣的加成、晉升奇遇包在外面，" + _LATER_17
            + "。第 11 批：探索一顆、進酒肆、約戰開著時那張卡換成 act 子動詞的掛鉤（Verb.run）",
    # （_everyday_options、action_notes：行動列那一格與底下那一行第 11 批換成 act 子動詞的掛鉤〔Verb.cell、Verb.note〕、酒肆那幾行換成
    # 店面登記〔Shop〕，拿掉）
    "_squad_encounter": "戰鬥（as_sortie 那一支）打贏之後出陣包給獎勵、約戰開著的季不推進度（那兩對記在 GAME_DELEGATE_CALLERS，原位行尾標"
                        "「# 過渡：第 26 批」）：「一包發生了、別包跟著動」是總表第 26 批的事件（打贏一場），PM 定第 11 批不開；序章那一場的"
                        "戰報標題寫雪恥（sortie.on、PROLOGUE_FIGHT）：" + _LATER_17,
    "_train_squad_ids": "舊遊歷與出陣共用的對手池（出陣開著時只有攻才打，叫 _sortie_mode、_sortie_foes）：" + _LATER_17,
    "_duty_option": "守勢行動（巡哨、傳道、保境安民）共用出陣的次數與鈕上的字（sortie.duty_problem、USED_UP、LEFT_NOTE；叫 sorties_left）："
                    + _LATER_17,
    "_duty": "守勢行動算一次出陣（sortie.spend；叫 _sortie_host 拿自家那一路的數字）：" + _LATER_17,
    "map_state": "輿圖（今天去哪裡出陣：sortie.on、叫 _sortie_foes、sorties_left）：" + _MAP_LINE,
    "_map_foes": "輿圖的地點卡（出陣打誰：sortie.on、叫 _sortie_foes）：" + _MAP_LINE,
    # （choose：用到 sortie_duel 這個名字的 PREFIX、PICK 第 11 批換成 choose_unlisted 與 Verb.picks，拿掉）
}
GAME_DELEGATE_CALLERS = {  # 核心自己的邏輯叫委派（同上）。GAME_DIRECT 的方法裡叫的也列（PM 10/31 答覆出陣第 1 批，第 2 批起）
    # explore（主動搬六包第 3＋4 批；審查修正：獨立一段放最前面，不夾在出陣那幾行中間）：核心叫探索委派一共 9 對。開發時掃描只看得到
    # 頭兩對；合了 develop（出陣第 2 批把掃描改成連 GAME_DIRECT 的方法裡叫的也記）之後，呼叫端本身在 GAME_DIRECT 裡的另外 7 對補進來。
    # 出陣第 1 批記的 (_outing_foe, _sortie_host) 拿掉了（下面出陣那一段少了那一行）：_outing_foe 進了探索包，經 ctx._sortie_host 叫
    # （服務清單二、查詢服務）。第 11 批（核心收接縫）：_act、_action_title、_everyday_options、action_notes 那 7 對換成 act 子動詞的掛鉤
    # （Verb：探索一顆開著時的出門一趟、標題、那一顆、那一行），拿掉
    ("map_base", "map_mostly"): "輿圖的底圖：名字旁的兩個字照看的人站過去之後的比重（探索一顆開著時）：" + _MAP_LINE,
    ("map_state", "map_mostly"): "輿圖：地點旁的兩個字照看的人站過去之後的比重（探索一顆開著時）：" + _MAP_LINE,
    # （(own_turn_checks, _mall_grant)：封測元寶每一輪發，第 11 批換成 on_own_turn 掛鉤，拿掉）
    # 擂台形象（looks；PR #121 Joy 11/1 合進 develop，第 11 批合 develop 時接上）：核心的擂台叫形象委派 4 對
    ("_arena_join", "arena_look"): "擂台形象：報名、更新分身時記穿哪一套（擂台還在核心；擂台搬成包時改成形象包的查詢服務）",
    ("_arena_start", "arena_look"): "擂台形象：挑人開打時記挑的人穿哪一套（同上）",
    ("_arena_join", "arena_move"): "招式動畫：報名、更新分身時記出招疊哪一張（同上）",
    ("_arena_start", "arena_move"): "招式動畫：挑人開打時記挑的人出招疊哪一張（同上）",
    ("_submit_battle_action", "_battle_ult"): "決戰的回合 MVP：放手一搏送出那一刻記身上的絕招（決戰「打」那一半第 8 批搬進決戰包時改成形象包的查詢服務）",
    ("_advance_battle_round", "_round_mvp"): "決戰的回合 MVP：回合結算包一層、結算完挑一位（同上，第 8 批）",
    # 出陣（主動搬六包第 1 批）：核心叫出陣委派 13 對（第 1 批時一共 21 對、掃描只看得到 6 對；約戰自己叫的 8 對第 2 批跟著進了包）
    # （第 11 批：_action_title、_everyday_options、action_notes 叫 _train_title、_sortie_option、_sortie_line 那 3 對換成 act 子動詞的掛鉤，拿掉）
    ("_act", "_sortie"): "act:train 打的那一場：出陣開著走出陣（扣體力、並肩出陣的加成包在外面）：" + _LATER_17,
    ("_squad_encounter", "_sortie_rewards"): "戰鬥（as_sortie）打贏之後給出陣的獎勵：總表第 26 批的事件（打贏一場；原位標「# 過渡：第 26 批」）",
    ("_train_squad_ids", "_sortie_mode"): "舊遊歷與出陣共用的對手池：出陣開著時只有攻才打；" + _LATER_17,
    ("_train_squad_ids", "_sortie_foes"): "同上：攻打的對手",
    ("_duty_option", "sorties_left"): "守勢行動共用出陣的次數（鈕上寫今天還能幾次）；" + _LATER_17,
    ("_duty", "_sortie_host"): "守勢行動拿自家那一路的經驗心得（一類一顆）；同上",
    ("map_state", "_sortie_foes"): "輿圖（今天去哪裡出陣）：出陣那一格是哪一種；" + _MAP_LINE,
    ("map_state", "sorties_left"): "輿圖：今天還能出陣幾次；同上",
    ("_map_foes", "_sortie_foes"): "輿圖的地點卡：約戰關著時出陣打的那一批；同上",
    # 出陣約戰（主動搬六包第 2 批）：核心叫約戰委派 17 對（搬之前約戰自己叫出陣委派的 8 對跟著進了包）。第 11 批（核心收接縫）：三處結算
    # （world_tick、sync、advance → _sortie_duel_tick）換成 on_due 掛鉤，拿掉；choose 那兩對（sortie:* 在查選單之前接走）換成 choose_unlisted，拿掉；
    # _act、action_notes 那 4 對（約戰開著時那張卡、約戰那一句）換成 act 子動詞的掛鉤，拿掉
    ("_fight_squad", "duel_on"): "大場面判讀（核心的單打服務）問出陣那一格這一下打不打仗：約戰開著時不判（不會打仗）；" + _LATER_17,
    ("_duty_option", "duel_on"): "守勢行動的鈕：約戰開著時收進此地、不佔出陣的次數；" + _LATER_17,
    ("_duty", "duel_on"): "守勢行動：約戰開著時不佔出陣、不推線、不算守城；同上",
    ("_duty", "_duty_credit"): "同上：一天記一點貢獻（企劃者 2026-10-24 第 2 件）",
    ("_squad_encounter", "duel_on"): "戰鬥（as_sortie）打贏之後：約戰開著時只剩截糧、不推進度（進度只在約戰結算動）：總表第 26 批的事件"
                                     "（原位標「# 過渡：第 26 批」）",
    ("map_state", "duel_on"): "輿圖：約戰開著時不畫零風險的守、攻不了的不推薦、運糧隊經過的帶 convoy；" + _MAP_LINE,
    ("_map_foes", "duel_on"): "輿圖的地點卡：約戰開著時列貼約戰會迎戰的守軍那一路；同上",
    ("_map_foes", "_duel_squad"): "同上：守軍那一路（經驗最高的那一路）",
    # battle
    # 全服決戰「看」那一半（主動搬六包第 5 批）：叫它的都是「打」那一半（第 7、8 批搬進同一包之後變成包裡互相叫）。第 11 批：場景卡
    # (scene_text, _battle_scene_text) 換成 scene_over 掛鉤、戰報頁 (battle_detail, _round_blocks) 換成 record_detail 掛鉤，拿掉
    ("_battle_options", "_round_wait"): "決戰「打」那一半（第 7 批搬）：已選了、等其他人那一顆灰鈕上寫已送出／在場",
    # （第 11 批：sync 的收場補送換成 deliver_results 掛鉤，拿掉 (sync, _deliver_battle_results)）
    ("_apply_battle_outcome", "_deliver_battle_results"): "決戰「打」那一半（第 8 批搬）：自己這一下把決戰推到收場，馬上補到自己手上",
    ("_settle_showdown", "_deliver_battle_results"): "決戰「打」那一半（第 8 批搬）：時刻表決戰收場，同上",
    ("_shelve_unfinished_battle", "_deliver_battle_results"): "決戰「打」那一半（第 8 批搬）：決戰季終收兵，同上",
    # 決戰「打」那一半之一（全部拆包第 6 批）：核心叫攻城委派 20 對（第 5 批記的 (_settle_siege|_shelve_siege, _deliver_battle_results) 兩對
    # 拿掉了：那兩個成了委派，補送在包裡經 ctx 叫）。「我在哪一場」與每一場推一次還是「打」那一半（第 7、8 批），叫的位置算行為
    ("_battle_status", "_sieges"): "每一場推一次（先決戰、再每一場攻城；沒有攻城戰時照舊走 _showdown_status）：決戰「打」那一半，第 8 批",
    ("_battle_status", "_tick_siege"): "同上：tick 時每一場攻城各推一次，一次請求只推一次",
    ("_battle_status", "_shelve_siege"): "同上：季收了，每一場攻城收兵",
    ("_battle_status", "_definition_of"): "同上：回這個人看的那一場與它的定義",
    ("_battle_now", "_sieges"): "這個人看的那一場（按鈕指定、自己參戰、站得進去、自己大區裡的）：決戰「打」那一半，第 8 批",
    ("_joinable", "_sieges"): "自己大區裡加得進去的那幾場（決戰在前）：集結，第 7 批",
    ("_joinable", "_definition_of"): "同上：那一場在哪個大區、看不看得進去",
    ("_in_region", "_definition_of"): "這幾場裡在自己大區的：集結，第 7 批",
    ("_battle_menu", "_definition_of"): "同一個大區兩場以上時每一場一組加入鈕（字前面寫是哪一場）：集結，第 7 批",
    ("_rally_any", "_sieges"): "假人趕路：有攻城戰時每一場都看（rally_region 那一支）：集結，第 7 批",
    ("_rally_any", "_definition_of"): "同上：那一場的大區",
    ("rally_region", "_sieges"): "假人趕路：有攻城戰時走 _rally_any（bot_runner 在叫）：集結，第 7 批",
    ("battles_now", "_sieges"): "全服此刻的每一場（假人程式、bot_policy 讀）：決戰「打」那一半，第 8 批",
    ("_siege_live", "_sieges"): "地盤畫面（conquest_view）的集結・交戰中那一場加不加得進去（FB-690）；地盤搬成包（第 46 批）時改叫決戰包的查詢服務",
    ("_apply_battle_outcome", "_settle_siege"): "收場分進攻城那一支（易手、作罷、時程表另外收）：決戰「打」那一半，第 8 批",
    ("admin_end_season", "_sieges"): "管理者立刻收季：沒打完的攻城照決戰收兵（收季的順序算行為：先決戰、再攻城、再補大事）；管理者外殼是核心，"
                                     "可是前一行的決戰收兵（_shelve_unfinished_battle）還在 Game：第 8 批兩段一起搬進決戰包時一起換成「收季」的掛鉤",
    ("admin_end_season", "_shelve_siege"): "同上",
    ("admin_next_season", "_sieges"): "開下一季：季自然結束、沒人同步過的攻城換季前收起來（參戰者補得到交代）；同上",
    ("admin_next_season", "_shelve_siege"): "同上",
    ("admin_conquest_cancel", "_cancel_siege"): "地盤的救場工具「取消一場攻城」：已經開了集結的那一場照收兵收起來；地盤搬成包（第 46 批）時改叫決戰包",
}
# tavern（主動搬六包第 10 批：酒肆的引擎那一半）：四張名單的酒肆那幾筆集中在這一段（三條拆包線並行，PM 合的時候不跟別人的行穿插）
GAME_IMPORTS |= {
    # 19 個一行委派；原本那一行 `from . import tavern as tavern_rules` 現在是別名（engine 照舊叫 tavern_rules.on、here、close、sign……，
    # 見下面 GAME_DIRECT；BANNED_WORDS 合 develop 時搬進核心 naming）。`from . import tavern_ask` 搬完沒人用，拿掉了
    "tianxia.features.tavern.actions", "tianxia.tavern",
}
GAME_DELEGATES |= {  # 13 個私有：server、假人、腳本、測試在叫的，與核心原位在叫的（_tavern_options、_tavern_enter、_tavern_hit_check、三個 deliver、_tavern_sign）
    # 第 11 批（核心收接縫）：sync 的三個 deliver 換成 deliver_notices 掛鉤，_deliver_whispers 沒人叫了，拿掉（_deliver_hits、_deliver_watches、
    # _tavern_hit_check 測試直接叫，留著）；選單接管那一格換成店面登記（Shop.menu），_tavern_options 沒人叫了，拿掉；紀錄標題換成
    # act 子動詞的掛鉤（Verb.title），_tavern_sign 拿掉（_tavern_enter 測試直接叫，留著）
    "tavern_do", "tavern_view", "tavern_ask_request", "tavern_ask", "tavern_chatter_request", "apply_tavern_chatter",
    "_tavern_open", "_tavern_enter", "_tavern_price", "_tavern_run", "_tavern_hit_problem",
    "_tavern_hit_check", "_tavern_hit_fight", "_tavern_ask_facts", "_deliver_watches", "_deliver_hits",
}
# 第 11 批（核心收接縫）：sync、_drop_stale_references 的收店，_shop_open、_depart、_everyday_options 的選單接管與入口換成店面登記（Shop），
# _act 的 act:tavern 換成 act 子動詞的掛鉤（Verb.run），拿掉
GAME_DIRECT.update({  # 用到 tavern_rules 這個名字（現在是酒肆包 rules 的別名）的
    "_hint_triggers": "碰到才說：有酒肆的城（tavern_rules.on、here）排 h_tavern 那一條：引導還沒成包（總表第 22 批）；成包時改叫酒肆的查詢服務",
    "_newbie_go": "新手目標「去酒肆」指哪幾個地點（tavern_rules.tavern_at）：同上",
})
GAME_DELEGATE_CALLERS.update({
    # （(choose, _tavern_hit_check)：每個動作之後的殺手檢查，第 11 批換成 after_action 掛鉤，拿掉）
    ("shop_view", "tavern_view"): "店面那一頁：鐵匠鋪那條線（feature/smithing-flow）緊貼著這一行改，這一輪不動；鐵匠鋪落地、成包時（總表第 41 批）"
                                  "店面那一頁接上店面登記（Shop）",
    # 呼叫端本身在 GAME_DIRECT 裡的另外 6 對：開發時那一版的掃描不記；合 develop（出陣第 2 批的掃描：GAME_DIRECT 的方法裡叫的也記，
    # PM 10/31）之後掃得到，取消註解（核心叫酒肆委派一共 9 對）。第 11 批：sync 那四對（下線的殺手、三個 deliver）換成 on_away、
    # deliver_notices 掛鉤，拿掉；(_everyday_options, _tavern_options) 換成店面登記，拿掉；(_act, _tavern_enter)、
    # (_action_title, _tavern_sign) 換成 act 子動詞的掛鉤，拿掉
})


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


def test_the_shared_rules_layer_is_real_old_modules_with_a_reason_and_never_imports_a_package():
    """共用規則層（registry.SHARED，第 11 批 PM 定的格式）：每一個是 tianxia/ 底下真的有的模組、不是核心本體、不是包、不是舊名的別名，
    寫了為什麼在共用層；跟核心一樣不 import 包（總表第六節第 5 條「兩層都不准 import 包」）。"""
    assert SHARED and all(isinstance(why, str) and why.strip() for why in SHARED.values())
    for name in SHARED:
        assert (TIANXIA / f"{name}.py").exists(), name
        assert name not in CORE and name not in aliases() and name not in _packages(), name
    assert [f"{name}.py:{line} {mod}" for name in sorted(SHARED) for line, mod in _feature_imports(TIANXIA / f"{name}.py")] == []


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
    """tianxia/mall.py、tianxia/feasts.py、tianxia/sortie.py、tianxia/sortie_duel.py、tianxia/outing.py、tianxia/explore_one.py、
    tianxia/tavern.py、tianxia/tavern_ask.py 是指到包裡同一個模組的別名（給還沒改的測試與舊模組）：掃描照它們指到的那一包算，不算舊模組。"""
    assert aliases() == {"feasts": "feast", "mall": "mall", "sortie": "sortie", "sortie_duel": "sortie",
                         # explore
                         "outing": "explore", "explore_one": "explore",
                         # tavern
                         "tavern": "tavern", "tavern_ask": "tavern"}
    assert not [e for e in transitional_imports() if e.rsplit(" ", 1)[1].split(".")[1] in aliases()]


def test_a_mark_with_no_old_module_left_is_caught():
    """註了過渡、import 的卻都是核心本體或共用規則層（搬完了、登記了）：那一行的註要拿掉；同一行還有一個舊模組的照註（第 11 批）。"""
    assert stale_marks("from tianxia import siege  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    assert stale_marks("from tianxia import journal, team  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    assert stale_marks("from tianxia import conquest, siege  # 過渡：待搬\n", "tianxia.features.battle.view") == []
    assert stale_marks("from tianxia import siege\n", "tianxia.features.battle.view") == []


@pytest.mark.parametrize("source", [
    "from tianxia import library  # 過渡：待搬\n",
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
