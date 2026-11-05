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
    "tianxia.features.explore.explore_base",  # explore（全部拆包第 18 批）：舊探索的底 6 個一行委派
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
    # 決戰「打」那一半之二（全部拆包第 7 批）：集結、投效、挑同伴 13 個一行委派；原本那一行 `from . import (..., escorts, ...)` 現在是別名
    # （engine 照舊叫 escorts.due、after_battle，見 GAME_DIRECT 的 _apply_battle_outcome）
    "tianxia.features.battle.muster", "tianxia.escorts",
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
    "sortie_cards", "sortie_card", "sortie_duel_tick",  # _duty_credit：只有 _duty 叫它，第 17 批 _duty 進了包，拿掉
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
    # 決戰「打」那一半之二（全部拆包第 7 批；11 個私有）：核心原位與別的功能在叫的——options 的戰鬥選單（_battle_menu）、choose 的 battle 那一支
    # （_battle_choose）、sync 與招募的同伴回江湖（_settle_partings）、戰力快照帶同伴（_escort_carry）、選邊與改幫（_ally_follows_battle，測試換掉）、
    # 移動記在不在場（_sync_battle_presence）、引導與「打」c 問到了戰場沒（_at_battle）、「打」c 的我在哪一場（_joinable、_in_region，地盤畫面也問
    # _joinable）、只能臨時投效（_free_agent）、假人趕路（rally_region）；測試直接叫的 _battle_options、_battle_choose_in。其餘 16 個只有包裡叫
    "_battle_menu", "_battle_options", "_battle_choose", "_battle_choose_in", "_escort_carry", "_settle_partings", "_ally_follows_battle",
    "_free_agent", "_at_battle", "_sync_battle_presence", "rally_region", "_joinable", "_in_region",
}
# 第 11 批（全部拆包「核心收接縫」，計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.2）之後留下的直連：核心的接縫（選單、補算時間、
# 行動列與 act 子動詞、choose 前後段、本人這一輪、場景卡、戰報頁、店面）都換成了接縫掛鉤（tianxia/core/features.py），留下的都不是核心
# 自己的接縫——還沒搬的別的功能（或同一包還沒搬的那一半）叫包。每一條寫「為什麼留、哪一批收」；「打完之後」那一種（一包發生了、別包跟著動）
# PM 定這一批不開掛鉤，原位行尾標「# 過渡：第 26 批」（事件機制）。
_MAP_LINE = "輿圖的線（feature/map-view）還在飛，這一輪不碰；輿圖成包（總表第 46～50 批）時改叫出陣、探索的查詢服務"
GAME_DIRECT = {  # 核心自己的邏輯直接叫包（沒有對應的掛鉤；過渡）
    # explore（主動搬六包第 3＋4 批）：用到 outing 這個名字（現在是探索包 outing_rules 的別名）的只剩有所感
    # （_sense：有所感擲特殊頓悟的 boost＝outing_rules.rare_boost——全部拆包第 24 批探索包開了查詢服務 _rare_boost〔# sense 那一段〕，改叫它，拿掉）
    # （_own_scene_text：坐在宴席上的場景卡第 11 批換成 scene 掛鉤，拿掉）
    # 出陣（主動搬六包第 1 批）：下面這些方法用到 sortie 這個名字（現在是出陣包 rules 的別名）——開關（sortie.on＝territory.on）、
    # 鈕上的字（NAME、USED_UP、LEFT_NOTE、OUT_NOTE……）、次數（spend）
    # （_act：探索一顆、進酒肆、約戰開著時那張卡第 11 批換成 act 子動詞的掛鉤〔Verb.run〕；act:train 打的那一場與 act:duty 第 17 批也換成
    # Verb.run，拿掉。_everyday_options、action_notes：行動列那一格與底下那一行第 11 批換成 act 子動詞的掛鉤〔Verb.cell、Verb.note〕、
    # 酒肆那幾行換成店面登記〔Shop〕；舊遊歷那一格與那一行第 17 批也收進 Verb.cell、Verb.note，拿掉）
    "_squad_encounter": "戰鬥（as_sortie 那一支）打贏之後出陣包給獎勵、約戰開著的季不推進度（那兩對記在 GAME_DELEGATE_CALLERS，原位行尾標"
                        "「# 過渡：第 26 批」）：「一包發生了、別包跟著動」是總表第 26 批的事件（打贏一場），PM 定第 11 批不開。序章那一場的"
                        "戰報標題寫雪恥（sortie.on、PROLOGUE_FIGHT）留在這裡（第 17 批）：戰報在這個單打服務裡建、裡面就存檔，序章裡誰打都照寫"
                        "（不只 act:train），出陣包從外面改不到；要拿掉得在單打服務開一個「這一場戰報叫什麼」的位置，交 PM 定",
    # （_train_squad_ids、_duty_option、_duty：舊遊歷與出陣共用的對手池、守勢行動第 17 批搬進出陣包〔train_actions〕，拿掉）
    "map_state": "輿圖（今天去哪裡出陣：sortie.on、叫 _sortie_foes、sorties_left）：" + _MAP_LINE,
    "_map_foes": "輿圖的地點卡（出陣打誰：sortie.on、叫 _sortie_foes）：" + _MAP_LINE,
    # （choose：用到 sortie_duel 這個名字的 PREFIX、PICK 第 11 批換成 choose_unlisted 與 Verb.picks，拿掉）
    # battle（全部拆包第 7 批：tianxia/escorts.py 整個搬進決戰包，舊名是別名）
    "_apply_battle_outcome": "收場那一刻全服放回隨你出陣的同伴（escorts.due、after_battle，排在龍頭上陣的 generals.after_battle 之後，先後算行為）："
                             "決戰「打」那一半還在 Game（總表第 8 批搬 _apply_battle_outcome 時變成包裡直接叫）",
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
    # 擂台形象（looks；PR #121 Joy 11/1 合進 develop，第 11 批合 develop 時接上）：核心的擂台叫形象委派的 4 對（_arena_join、_arena_start
    # 叫 arena_look、arena_move）全部拆包第 12 批拿掉——擂台搬進單挑包，包裡經 ctx 叫形象包的查詢服務（服務清單二、查詢服務 # bout）
    ("_advance_battle_round", "_round_mvp"): "決戰的回合 MVP：回合結算包一層、結算完挑一位（同上，第 8 批）",
    # 出陣（主動搬六包第 1 批）：核心叫出陣委派 13 對（第 1 批時一共 21 對、掃描只看得到 6 對；約戰自己叫的 8 對第 2 批跟著進了包）
    # （第 11 批：_action_title、_everyday_options、action_notes 叫 _train_title、_sortie_option、_sortie_line 那 3 對換成 act 子動詞的掛鉤，拿掉）
    # （第 17 批：(_act, _sortie)、(_train_squad_ids, _sortie_mode|_sortie_foes)、(_duty_option, sorties_left)、(_duty, _sortie_host) 那 5 對
    # 跟著舊遊歷、守勢搬進出陣包，變成包裡互相叫，拿掉）
    ("_squad_encounter", "_sortie_rewards"): "戰鬥（as_sortie）打贏之後給出陣的獎勵：總表第 26 批的事件（打贏一場；原位標「# 過渡：第 26 批」）",
    ("map_state", "_sortie_foes"): "輿圖（今天去哪裡出陣）：出陣那一格是哪一種；" + _MAP_LINE,
    ("map_state", "sorties_left"): "輿圖：今天還能出陣幾次；同上",
    ("_map_foes", "_sortie_foes"): "輿圖的地點卡：約戰關著時出陣打的那一批；同上",
    # 出陣約戰（主動搬六包第 2 批）：核心叫約戰委派 17 對（搬之前約戰自己叫出陣委派的 8 對跟著進了包）。第 11 批（核心收接縫）：三處結算
    # （world_tick、sync、advance → _sortie_duel_tick）換成 on_due 掛鉤，拿掉；choose 那兩對（sortie:* 在查選單之前接走）換成 choose_unlisted，拿掉；
    # _act、action_notes 那 4 對（約戰開著時那張卡、約戰那一句）換成 act 子動詞的掛鉤，拿掉。第 17 批：(_fight_squad, duel_on) 換成
    # act 子動詞的掛鉤（Verb.squad）、(_duty_option|_duty, duel_on)、(_duty, _duty_credit) 跟著守勢搬進出陣包，拿掉
    ("_squad_encounter", "duel_on"): "戰鬥（as_sortie）打贏之後：約戰開著時只剩截糧、不推進度（進度只在約戰結算動）：總表第 26 批的事件"
                                     "（原位標「# 過渡：第 26 批」）",
    ("map_state", "duel_on"): "輿圖：約戰開著時不畫零風險的守、攻不了的不推薦、運糧隊經過的帶 convoy；" + _MAP_LINE,
    ("_map_foes", "duel_on"): "輿圖的地點卡：約戰開著時列貼約戰會迎戰的守軍那一路；同上",
    ("_map_foes", "_duel_squad"): "同上：守軍那一路（經驗最高的那一路）",
    # battle
    # 全服決戰「看」那一半（主動搬六包第 5 批）：叫它的都是「打」那一半（第 7、8 批搬進同一包之後變成包裡互相叫）。第 11 批：場景卡
    # (scene_text, _battle_scene_text) 換成 scene_over 掛鉤、戰報頁 (battle_detail, _round_blocks) 換成 record_detail 掛鉤，拿掉
    # （(_battle_options, _round_wait)：第 7 批 _battle_options 搬進包、包裡直接叫 view.round_wait，拿掉）
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
    # （_joinable、_in_region、_battle_menu、_rally_any、rally_region 叫 _sieges、_definition_of 那 7 對：第 7 批那幾個搬進包、包裡直接叫
    # sieges.sieges、sieges.definition_of，拿掉）
    ("battles_now", "_sieges"): "全服此刻的每一場（假人程式、bot_policy 讀）：決戰「打」那一半，第 8 批",
    ("_siege_live", "_sieges"): "地盤畫面（conquest_view）的集結・交戰中那一場加不加得進去（FB-690）；地盤搬成包（第 46 批）時改叫決戰包的查詢服務",
    ("_apply_battle_outcome", "_settle_siege"): "收場分進攻城那一支（易手、作罷、時程表另外收）：決戰「打」那一半，第 8 批",
    ("admin_end_season", "_sieges"): "管理者立刻收季：沒打完的攻城照決戰收兵（收季的順序算行為：先決戰、再攻城、再補大事）；管理者外殼是核心，"
                                     "可是前一行的決戰收兵（_shelve_unfinished_battle）還在 Game：第 8 批兩段一起搬進決戰包時一起換成「收季」的掛鉤",
    ("admin_end_season", "_shelve_siege"): "同上",
    ("admin_next_season", "_sieges"): "開下一季：季自然結束、沒人同步過的攻城換季前收起來（參戰者補得到交代）；同上",
    ("admin_next_season", "_shelve_siege"): "同上",
    ("admin_conquest_cancel", "_cancel_siege"): "地盤的救場工具「取消一場攻城」：已經開了集結的那一場照收兵收起來；地盤搬成包（第 46 批）時改叫決戰包",
    # 決戰「打」那一半之二（全部拆包第 7 批）：核心與別的功能叫集結、投效、挑同伴的委派 17 對——這幾個位置都沒有第 11 批的掛鉤
    # （計畫 docs/superpowers/plans/2026-11-01-決戰包-第3批.md 1.4）
    ("options", "_battle_menu"): "選單的戰鬥那一段：集結時接在平常的選單前面、開打了整個取代（再接別人前綴的 defect:cancel）；menu 掛鉤在 "
                                 "_everyday_options 裡、位置太後，前後的 _battle_for_me、_watching_battle、_fighting 是第 8 批",
    ("choose", "_battle_choose"): "choose 查完選單、清掉「剛剛」與引導之後、建紀錄之前的 battle 那一支（出招不寫紀錄）：choose_unlisted 在查選單之前、"
                                  "choose 掛鉤會建紀錄，都不是這個位置；同一個位置還有 seal:、duel:、arena:（第 12、28 批），「選單上、不建紀錄」那一格"
                                  "留給核心批（總表第 57 批）",
    ("sync", "_settle_partings"): "同步的同伴回江湖（簽到之後、退押金之前）：on_sync 在寄放之前、還問 enabled，江湖紀錄的先後算行為；同伴還沒成包",
    ("_recruit_one", "_settle_partings"): "按招募之前先把回江湖的那一位情誼減半：同伴還沒成包",
    ("_battle_marks", "_escort_carry"): "戰力快照（核心的單打服務）帶這一次加入的同伴：沒有掛鉤，總表第 15 批登記戰力快照時再看",
    ("_faction_step", "_ally_follows_battle"): "投靠豪強、選邊之後集結名單跟著換邊（FB-273）：陣營還沒成包（總表第 35 批）",
    ("_join_lean", "_ally_follows_battle"): "三陣營四勝利：拜入門派照所在地給傾向之後同上；同上",
    ("_lean_step", "_ally_follows_battle"): "三陣營四勝利：改幫另一軍之後同上；同上",
    ("_arrivals", "_sync_battle_presence"): "抵達時記人還在不在決戰的大區：移動還沒成包（總表第 47 批）",
    ("_depart", "_sync_battle_presence"): "出發時同上；同上",
    ("_halt", "_sync_battle_presence"): "喊停時同上（這一趟縮短了）；同上",
    # （(_hint_triggers, _at_battle)：碰到才說的 h_spectator，全部拆包第 22 批 _hint_triggers 搬進新手引導包、經 ctx._at_battle 叫〔決戰的
    # 查詢服務〕，拿掉）
    ("_watching_battle", "_at_battle"): "此刻只能在一旁看（還沒參戰的人不在那個大區）：決戰「打」那一半，第 8 批",
    ("_fighting", "_free_agent"): "開打了還沒投效的散人與豪強不整個取代畫面：決戰「打」那一半，第 8 批",
    ("_battle_now", "_joinable"): "這個人看的那一場：自己站得進去的那一場先（FB-566）；決戰「打」那一半，第 8 批",
    ("_battle_now", "_in_region"): "同上：自己大區裡的那一場；同上",
    ("_siege_live", "_joinable"): "地盤畫面（conquest_view）的集結・交戰中那一場加不加得進去（FB-690）：地盤搬成包（第 46 批）時改叫決戰包的查詢服務",
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
    # （_hint_triggers、_newbie_go：碰到才說的 h_tavern、新手目標「去酒肆」讀 tavern_rules——全部拆包第 22 批跟著方法搬進新手引導包，
    # 改叫酒肆的查詢服務 _tavern_on、_tavern_here、_tavern_at〔Game 上一行的委派，# guide 那一段〕，拿掉）
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
# sortie（全部拆包第 17 批「出陣三」：舊遊歷、序章雪恥、跟自家隊伍操練、守勢、遊歷推大勢搬進出陣包的 train_actions；計畫
# docs/superpowers/plans/2026-11-01-出陣包-第3批.md 1.6）：四張名單這一批加的集中在這一段（並行的拆包線不跟別人的行穿插；拿掉的在原處）
GAME_IMPORTS |= {"tianxia.features.sortie.train_actions"}  # 8 個一行委派（必敗先問的那兩句也搬進包，從 features.sortie.rules 拿回來）
GAME_DELEGATES |= {
    # 核心原位叫的 3 個（_squad_encounter 的 _drill、train_trend_push，軍情 _order_options 的 _duty_option）；假人、測試、腳本在叫或換掉的
    # 5 個（_train_pick：test_engine；_train：test_parley_two 換掉實例上的；_train_squad_ids：test_ranks、test_explain；drill_scale：
    # test_drill_push；_train_push：sim_trend_sources 換掉 Game._train_push；train_trend_push 另有 bot_policy、test_explain 換掉）
    "_train_pick", "_train", "_train_squad_ids", "_duty_option", "drill_scale", "_drill", "_train_push", "train_trend_push",
}
GAME_DELEGATE_CALLERS.update({
    ("_squad_encounter", "_drill"): "戰鬥（核心的單打服務，遊歷、探索的野怪、劇情以外的仗都經它）遇上自家陣營的隊伍改成操練：操練是出陣包的（第 17 批）、"
                                    "打不打在單打服務裡定；單打服務的「遇上自己人」沒有對應的掛鉤。68 批裡沒有排：總表 3.4 可選的"
                                    "「戰鬥單打服務收進核心」（戰鬥調查 C1）那一次在 core/combat.py 開這一格、改叫掛鉤；不做 C1 就一直留著",
    ("_squad_encounter", "train_trend_push"): "戰鬥（不是出陣的那一支）打贏之後遊歷推大勢：總表第 26 批的事件（打贏一場；原位行尾標「# 過渡：第 26 批」）",
    # （("_order_options", "_duty_option")：軍情第 33 批成包，_order_options 搬進軍情包，經 ctx._duty_option 叫出陣包的委派〔服務清單二、查詢服務 # military〕，拿掉）
})
# guide（全部拆包第 22 批「引導一」：新手引導包；計畫 docs/superpowers/plans/2026-11-01-新手引導包-第1批.md 1.4、1.5）：四張名單的引導那幾筆
# 集中在這一段。核心原位碰引導的那幾處都沒有第 11 批的掛鉤，改叫 Game 上一行的服務委派（不新增 GAME_DIRECT）
GAME_IMPORTS |= {
    # 24 個方法的一行委派、12 個服務的本體（actions）；Game._note_action 叫 engine 模組層的 note_action（`from .guide import note_action`：
    # 別名，tests/core/test_engine.py 換的就是 tianxia.engine.note_action）。原本的 `from . import (..., enlist, newbie, ...)`、opening、
    # hints 那兩行與 guide 其餘的名字，搬完 engine 不再用，拿掉
    "tianxia.features.guide.actions", "tianxia.guide",
}
GAME_DELEGATES |= {
    # 搬進包的 31 個方法留 24 個（10 個私有）：server 叫的 14 個（main_view 的引導框、序章與初入江湖的畫面、任務卡、MAIN_ACTIONS 的 7 個 op、
    # /api/prologue），核心原位與別的功能叫的 _check_hints、_hint、_begin_enlistment、_greet_rejoin、newbie_view、_rest，Game.new 叫的
    # _graduate、_note_gift（`game.` 叫，掃描看不到）、舊模組 step 叫的 _nearest_to、測試直接叫的 _newbie_go、測試換掉的 _hint_triggers。
    # 其餘 7 個（_graduate_pass、_hint_box、_hint_up、_surface_hint、_drop_stale_hints、_queue_triggered_hints、_check_newbie）只有包裡叫
    "_note_gift", "_graduate", "_begin_enlistment", "_greet_rejoin", "enlist_glow", "guide_box", "_hint", "_hint_triggers", "_check_hints",
    "_nearest_to", "_newbie_go", "newbie_view", "newbie_drifter", "set_hints_off", "guide_ack", "_rest", "skip_tutorial", "view_orders",
    "view_map", "view_tab", "prologue_view", "onboard_view", "prologue_recap", "quest_text",
    # 核心原位與出陣包叫的服務 12 個（Task 2 開的；本體在 actions，_note_action 見上）
    "_note_action", "_opening_on", "_opening_begin", "_opening_pending", "_opening_deliver", "_opening_gate", "_tutorial_intro",
    "_base_step_count", "_guide_speakers", "_enlist_done", "_mark_veteran", "_enlist_expire",
    # 酒肆的查詢服務 3 個（主人酒肆；引導包問：碰到才說的 h_tavern、新手目標「去酒肆」）——叫 tavern_rules（酒肆包 rules 的別名）
    "_tavern_on", "_tavern_here", "_tavern_at",
}
_NOTE_HOOK = ("「做完一件事、引導跟著走」歸總表第 57 批（分派與標題收接縫，那一批量了再決定要不要開事件；第 26 批 PM 認定第 6 條。"
              "PM 第 11 批定不開）；這幾處在動作中間、回話照位置接")
_OPENING = "開局第一分鐘（城門口三選一還沒選）"
GAME_DELEGATE_CALLERS.update({
    # 做完一件事看一遍碰到才說（_check_hints）、碰到某個玩法排一條（_hint）：位置都在記進江湖紀錄之前，說的話記在這一則；after_action 在
    # choose 最後、sync 沒有對應的位置，修練頁與移動也不走 choose
    ("choose", "_check_hints"): "choose 最後、記進江湖紀錄之前：這一下碰到的新玩法排一條、排著的上框；after_action 之後才存回季、紀錄已經寫了",
    ("sync", "_check_hints"): "sync 的最後幾行（引薦人的結語之後、結伴逾時之前）：抵達、大事揭曉這些不靠行動的改變；on_sync 在更前面",
    ("travel", "_check_hints"): "出發那一下（移動還沒成包，總表第 47 批）",
    # （(allocate_stat, _check_hints)：配點之後——全部拆包第 23 批 allocate_stat 搬進修練包、包裡經 ctx 叫，拿掉）
    # （(sense_draw, _check_hints)：有所感畫完那一筆——全部拆包第 24 批 sense_draw 搬進有所感包、包裡經 ctx 叫，拿掉）
    ("_menxia_entry", "_check_hints"): "修練頁、煉製頁的動作寫進紀錄（核心的修練頁紀錄服務）：說的話接在這一則",
    ("_act", "_hint"): "act 子動詞裡碰到的事件型提示（操練練完 h_drill_done…）：其餘子動詞還沒分給各包（總表第 57 批）",
    # （原本這裡有 ("_brush_off", "_hint")：第 21 批 _brush_off 搬進交友求見包，包裡經 ctx._hint 問，核心原位不再叫它）
    # （原本這裡有 ("_open_dialogue", "_hint")：第 20 批 _open_dialogue 搬進人物情誼包，包裡經 ctx._hint 問，核心原位不再叫它）
    ("choose", "_begin_enlistment"): "這一下才投靠（或拜入陣營名下的門派）的人開始入伍段：陣營還沒成包（總表第 35 批）、要知道動作之前的陣營",
    ("choose", "_greet_rejoin"): "第二季起再投靠：引薦人打個招呼（同上）",
    ("_act", "_rest"): "act:rest（序章教體力那一步的調息）：核心 act: 的子動詞（總表第 57 批分）",
    ("status_data", "newbie_view"): "狀態列的任務卡那一塊（status 的鍵順序算行為；狀態列掛鉤是總表第 66 批）",
    # 核心原位與別的功能叫引導的服務（Task 2 把 note_action、opening、enlist、guide 的幾個名字換成這幾個一行的委派）
    ("choose", "_note_action"): "選項做完、出門、交友、進出店面……七處：" + _NOTE_HOOK,
    # （(_sense_apply, _note_action)：有所感悟到意境——全部拆包第 24 批 _sense_apply 搬進有所感包、包裡經 ctx 叫，拿掉）
    # （(_order_credit, _note_action)：軍情第 33 批成包，_order_credit 搬進軍情包，經 ctx._note_action 叫引導，拿掉）
    # 守勢（原 Game._duty，act:duty）：這一批開發時第 17 批正在把它搬進出陣包，開發時不改它（計畫第六節「跟第 17 批」）；第 17 批先合進
    # develop、搬成 train_actions.duty，這一批合進 develop 時那兩處改叫 ctx._note_action（包裡叫，不在這張名單；計畫第七節）
    ("_faction_step", "_note_action"): "投靠那一下（序章、引導的 join）：陣營還沒成包（總表第 35 批）；" + _NOTE_HOOK,
    ("_arrive", "_note_action"): "抵達（出師去潁川、離開城鎮）：移動還沒成包（總表第 47 批）；" + _NOTE_HOOK,
    ("take_stamina_pill", "_note_action"): "服回體丹（序章那一步）：回體丹是核心；" + _NOTE_HOOK,
    # （(allocate_stat, _note_action)：配點（序章那一步）——全部拆包第 23 批同上，拿掉）
    ("_menxia_entry", "_note_action"): "修練頁、煉製頁的動作（序章的練功、熔煉）：核心的修練頁紀錄服務；" + _NOTE_HOOK,
    ("choose", "_opening_pending"): _OPENING + "：選完那一下人物的信接在這一下的回話裡（位置算行為）",
    ("choose", "_opening_deliver"): "同上：那位人物的信與護送委託",
    ("check_in", "_opening_pending"): _OPENING + "就簽到，回那一句：簽到還沒成包",
    ("check_in", "_opening_gate"): "同上：那一句",
    ("_auto_checkin", "_opening_pending"): _OPENING + "不自動簽到：簽到還沒成包",
    ("checkin_view", "_opening_pending"): _OPENING + "不畫簽到小卡：簽到還沒成包",
    ("now_entry_html", "_opening_pending"): _OPENING + "不放「剛剛」那張卡：江湖頁的「剛剛」是核心",
    ("sync", "_enlist_expire"): "第一道軍令一週還沒做完：引薦人照樣說結語（sync 的 _check_hints 前一行；on_sync 在更前面，紀錄先後算行為）",
    ("_drop_stale_references", "_mark_veteran"): "入伍段上線之前就投靠了的老手蓋成走完：要在換季之前（_drop_stale_references 一開頭；on_drop_stale 在最後）",
    ("_reset_player_for_new_season", "_enlist_done"): "換季照帶：入伍段走完的帶到下一季（手冊第十五節：照帶不放 on_season_start）",
    ("_reset_player_for_new_season", "_base_step_count"): "換季照帶：做到不分季的那幾步就照帶（同上）",
    ("_reset_player_for_new_season", "_tutorial_intro"): "換季的開場那一則江湖紀錄的引導那幾行（同上）",
    ("_note_guide", "_guide_speakers"): "核心的引導框服務照說話的人分開「下一步的話」與「✔ 與獎勵」",
    # Game.new（classmethod，`game.` 叫）的 _opening_on、_opening_begin、_tutorial_intro、_graduate、_note_gift：掃描只認 self.，記在這裡備查
})
CORE_DELEGATE_CALLERS_GUIDE = {  # 事件檢定（核心本體）經 ctx 叫的新手引導委派：隨口應對的結果也可能拜入門派、碰到新玩法（answer_event、answer_branch
    # 照抄選項做完那一下的三行；位置在事件檢定裡，第 11 批沒有掛鉤；陣營第 35 批、「做完一件事」第 57 批再看〔第 26 批 PM 認定第 6 條〕）
    ("event_check.answer_event", "_begin_enlistment"): "隨口應對的結果拜入陣營名下的門派：開始入伍段",
    ("event_check.answer_event", "_greet_rejoin"): "同上：入伍段早就走完的人，引薦人打個招呼",
    ("event_check.answer_event", "_check_hints"): "隨口應對了結了事件：同選項一樣，碰到的新玩法排一條、排著的上框",
    ("event_check.answer_branch", "_begin_enlistment"): "分岔的隨口應對：同 answer_event",
    ("event_check.answer_branch", "_greet_rejoin"): "同上",
    ("event_check.answer_branch", "_check_hints"): "同上",
}
# battle（全部拆包第 8 批：推進與結算、generals 進包、收季的收兵；計畫 docs/superpowers/plans/2026-11-01-決戰包-第4批.md 1.5）：四張名單的
# 決戰第 8 批那幾筆集中在這一段（四條拆包線並行，PM 合的時候不跟別人的行穿插），改前面的名單用 del、|=、update，不改那幾行的原文
for _pair in (("admin_end_season", "_sieges"), ("admin_end_season", "_shelve_siege"),
              ("admin_next_season", "_sieges"), ("admin_next_season", "_shelve_siege")):
    del GAME_DELEGATE_CALLERS[_pair]  # 收季的收兵換成 on_season_close 接縫掛鉤（決戰包照原本那兩段做，第 11 批 PM 認定第 7 條）
# 推進與結算 20 個方法搬進 features/battle/progress.py（14 個一行委派）；engine 不再 import 舊名 escorts（收場放回同伴進了 progress.apply_battle_outcome）
GAME_IMPORTS -= {"tianxia.escorts"}
GAME_IMPORTS |= {"tianxia.features.battle.progress"}
GAME_DELEGATES -= {"_shelve_siege", "_in_region"}  # 叫它們的 _battle_status、收季、_battle_now 進了包：沒人叫，拿掉
# （_settle_siege 留著：叫它的 _apply_battle_outcome 進了包，可是 features/battle/tests/test_siege_settle.py 直接叫 game._settle_siege）
GAME_DELEGATES |= {
    # 核心原位與別的功能在叫的：options 的戰鬥選單（_battle_for_me、_watching_battle、_fighting）、world_tick 與引導（_battle_status：測試換掉、
    # 數次數；_watching_battle）、叛投（_battle_now）、玉璽（_showdown_status）、場景圖（_battle_for_me）、事件分級（_battle_for_me，CORE_DELEGATE_CALLERS）；
    # 假人程式與 bot_policy、決戰包的 bots.py（battle_now）；測試直接叫或換掉的 battles_now、_shelve_unfinished_battle、_advance_battle_round、
    # _run_battle_tick、_apply_battle_outcome（tests/server/test_server.py 換掉）、_apply_outcome_trends_and_flags、_merit_line。
    # 其餘 6 個（_backfill_battle_scores、_mutate_battle_of、_mutate_battle_now、_highlight_line、_settle_showdown、_open_waiting_showdown）只有包裡叫
    "_battle_status", "_showdown_status", "_battle_for_me", "_battle_now", "battle_now", "battles_now", "_shelve_unfinished_battle",
    "_advance_battle_round", "_run_battle_tick", "_apply_battle_outcome", "_apply_outcome_trends_and_flags", "_watching_battle", "_fighting",
    "_merit_line",
}
del GAME_DIRECT["_apply_battle_outcome"]  # escorts.due、after_battle 進了包裡直接叫（第 7 批 PM 認定第 3 條：第 8 批收）
for _pair in (
    ("_advance_battle_round", "_round_mvp"),  # 回合首功那一層跟著推一回合進了包（經 ctx._round_mvp：服務清單二、查詢服務）
    ("_apply_battle_outcome", "_deliver_battle_results"), ("_settle_showdown", "_deliver_battle_results"),
    ("_shelve_unfinished_battle", "_deliver_battle_results"),  # 收場、時刻表決戰收場、收兵：補送進了包（經 ctx：測試換掉）
    ("_battle_status", "_sieges"), ("_battle_status", "_tick_siege"), ("_battle_status", "_shelve_siege"), ("_battle_status", "_definition_of"),
    ("_battle_now", "_sieges"), ("_battle_now", "_joinable"), ("_battle_now", "_in_region"), ("battles_now", "_sieges"),
    ("_apply_battle_outcome", "_settle_siege"), ("_watching_battle", "_at_battle"), ("_fighting", "_free_agent"),  # 呼叫端進了包、包裡直接叫
):
    del GAME_DELEGATE_CALLERS[_pair]
_LATER_PROGRESS = "；位置固定、沒有對應的掛鉤（全部拆包第 8 批計畫 1.4）"
GAME_DELEGATE_CALLERS.update({
    ("options", "_battle_for_me"): "選單推一次決戰（誰輪詢誰推，一次請求只推一次；奪璽單挑之後、暫停那一顆之前）：選單的先後算行為，"
                                   "總表第 55～57 批「選單」" + _LATER_PROGRESS,
    ("options", "_watching_battle"): "選單的戰鬥那一段：只能觀戰的人照常給平常的選單；同上",
    ("options", "_fighting"): "選單的戰鬥那一段：開打了在場上的人戰鬥選單整個取代、其餘接在平常的選單前面；同上",
    ("world_tick", "_battle_status"): "排程的那一下推一次決戰：領地爭奪換天之後、奪璽單挑之前，on_due 在換天之前（先後算行為）" + _LATER_PROGRESS,
    # （開發時這裡還有 (_hint_triggers, _battle_status)、(_hint_triggers, _watching_battle) 兩對：第 22 批先合進 develop、把 _hint_triggers
    # 搬進引導包、改經 ctx 問〔服務清單〕，Game._hint_triggers 成了一行委派，合進 develop 時拿掉）
    ("_defect_step", "_battle_now"): "叛投：決戰裡的人不能叛投（defection.refusal 讀此刻的那一場）：陣營還沒成包（總表第 35 批）",
    ("_defect_targets", "_battle_now"): "叛投：投得過去的那幾個（defection.slots_here 讀此刻的那一場）：同上",
    ("seal_view", "_showdown_status"): "玉璽碎片卡：這一片被璽動的那一場時刻表決戰（攻城戰不璽動）：玉璽還沒成包（總表第 27、28 批）",
    ("seal_watch", "_showdown_status"): "玉璽碎片：背景也要輪詢（持有者或參戰者）：同上",
    ("scene_art", "_battle_for_me"): "場景卡的圖：全服戰鬥蓋著場景時沒有圖（序章裡不算）：殼的場景卡（總表第 64～67 批）" + _LATER_PROGRESS,
})
# bout（全部拆包第 12 批：單挑——單人頭目戰、擂台；計畫 docs/superpowers/plans/2026-11-03-單挑包-第1批.md 1.4、1.5）：四張名單的單挑那幾筆
# 集中在這一段（四條拆包線並行，PM 合的時候不跟別人的行穿插）。原位有第 11 批掛鉤的接上了（店面登記、act 子動詞、choose、menu、check_content）：
# _everyday_options 坐在擂台邊與此地還能做的入口、_shop_open／_depart／sync／_drop_stale_references 的收店、_act 的 act:arena、_action_title
# 的 arena 兩支、choose 的 arena:join／fight／back、擂台打到一半的三招與認輸。下面是沒有對應掛鉤、留在原位叫委派的。GAME_DIRECT 不加
GAME_IMPORTS |= {
    # 28 個一行委派（頭目戰 duel_actions 16 個〔含審查修正補的 _duel_menu〕、擂台 arena_actions 12 個）；duel_rules 給委派的型別註記（DuelTextRequest）與 Game 的類別屬性
    # DUEL_GAMBLE_NOTE（類別本體不是方法，game_links 掃不到那一行，記在這裡）。原本那幾行 `from . import (..., arena, arena_crowd, ...)`、
    # `from . import duel as duel_rules` 拿掉了：剩下的改叫核心的 tianxia/core/duel_base、arena_ranks（單挑底層、擂台的名次與稱號）或委派
    "tianxia.features.bout.duel_actions", "tianxia.features.bout.arena_actions", "tianxia.features.bout.duel_rules",
}
GAME_DELEGATES |= {  # 20 個私有
    # 頭目戰：server 的輸入框與鎖外三段式（duel_free_text_prompt、duel_free_text_note、duel_text_request、duel_gamble）、腳本換掉的 _duel_finish、
    # 核心原位與別的功能叫的 _duel_start（舊探索、三選一，探索包經 ctx）、_duel_scene（場景卡）、_duel_act（choose）、_duel_side（奪璽單挑）、
    # _duel_cut（戰力快照、奪璽單挑的參戰者）、_duel_menu（打到一半的三招與抽身：審查修正，原本那一段留在 _everyday_options）
    "_duel_start", "_duel_scene", "duel_free_text_prompt", "duel_free_text_note", "duel_text_request", "_duel_side", "duel_gamble",
    "_duel_act", "_duel_finish", "_duel_cut", "_duel_menu",
    # 頭目的查詢：_boss_face 是附錄甲歸單挑、搬進包的那一個；其餘四個是這一批新開的一行查詢（原位叫 duel_rules 的 here、available、
    # used_up 那幾處：舊探索在叫，探索包經 ctx 問 _boss_ready）
    "_boss_face", "_boss_ready",
    # 擂台：測試換掉的 _arena_bare；假人與測試叫的 arena_power、arena_left、_arena_options、_arena_join；server 的看台三段式
    # （arena_crowd_request、apply_arena_crowd）；核心原位叫的 _arena_entry（閉關中、路上）、_arena_fight_problem（新開：灰掉的挑擂鈕）、
    # _arena_scene（場景卡）、_arena_act（choose）、_deliver_arena（sync，測試也直接叫）、arena_left（店面那一頁）
    "_arena_bare", "arena_power", "arena_left", "_arena_fight_problem", "_arena_entry", "_arena_options", "_arena_join", "_arena_scene",
    "arena_crowd_request", "apply_arena_crowd", "_arena_act", "_deliver_arena",
}
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_duel_menu"): "頭目戰打到一半的三招與抽身（審查修正：本體原本留在 _everyday_options）：排在 features_core.menu 前面一行，"
                                         "menu 掛鉤照 FEATURES 問、單挑包排在宴客後面，接上去會排到宴客的席位後面",
    ("_everyday_options", "_arena_entry"): "閉關中、在路上的擂台入口（PM 轉述 Joy 2026-10-14「不一定要鎖死在城鎮」）：那兩支不是「此地還能做」，"
                                           "店面登記沒有這兩格（Shop.entry 只在 shop_entries）",
    ("choose", "_arena_fight_problem"): "按到灰掉的挑擂鈕（兩個分頁、畫面還沒重抓）回為什麼不成、還要等多久：在查完選單之後、「此刻無法」之前，"
                                        "choose_unlisted 在查選單之前，不是這個位置",
    ("choose", "_duel_act"): "choose 查完選單、清掉「剛剛」與引導之後、建紀錄之前的 duel 那一支（出招不寫紀錄）：同 (choose, _battle_choose)，"
                             "「選單上、不建紀錄」那一格總表第 57 批 seal:、duel:、arena:、battle: 四包一起接",
    ("choose", "_arena_act"): "同上：擂台的三招與認輸",
    ("_own_scene_text", "_duel_scene"): "自己眼前的場景卡（頭目戰、擂台排在宴客的席位之前）：scene 掛鉤在擂台之後，接上去會排到宴客後面",
    ("_own_scene_text", "_arena_scene"): "同上",
    ("sync", "_deliver_arena"): "同步的擂台補送（領地爭奪補送之後、痕跡之前：被挑的戰報、領俸、季末前三名）：那一行沒有掛鉤，江湖紀錄的先後算行為",
    ("shop_view", "arena_left"): "店面那一頁的擂台（今天還能挑幾次）：同 (shop_view, tavern_view)，店面那一頁接店面登記是總表第 41 批",
    ("_battle_gear", "_duel_cut"): "戰力快照（核心的單打服務）抄奪璽單挑吃的防具減損（鐵匠鋪與合成流程 3.9）：_duel_cut 照總表第六節第 12 條歸單挑，"
                                   "_battle_gear 在核心",
    # 另外兩處叫 _duel_cut 的在別人的 Game 上（_seal_spectators 的 kin._duel_cut()、_seal_side_of 的 game._duel_cut()：奪璽單挑的參戰者與
    # 沒參戰的持有者），game_links 只掃 self.<名>，這裡記不到。第 28 批把那兩個方法搬進玉璽包時，先把 _duel_cut 登記成服務清單的查詢服務
    # （主人：單挑包），不然玉璽包叫它就是過渡外的 Game 方法（審查修正記下）
    ("seal_text_request", "_duel_side"): "奪璽單挑的放手一搏寫這個人是哪一邊（陣營名）：玉璽還沒成包（總表第 28 批）",
})
# 只讀擂台名次與稱號的舊模組（名帖 mingtie、玩家卡 social、榜單 leaderboard：on、title_of、ladder、title_for、record_text 都在核心
# arena_ranks）讀核心那一份，不經舊名 arena 連帶載入單挑包（手冊 3.11「能走服務就走服務」；第 12 批審查修正）。tiers 照舊經別名：
# tests/core/test_event_tiers.py 換掉 tianxia.arena.entry_of，改讀核心之後那一條打不到（SHARED_LATER 的 tiers）
ARENA_RANK_READERS = ("features/peers/mingtie", "leaderboard")  # 名帖第 37 批搬進玩家互動包（舊名 tianxia/mingtie.py 是別名）； 玩家卡的稱號（social.affiliation）第 37 批搬進核心的 core/presence.py，下面另驗那一份


def test_the_old_modules_that_only_read_the_arena_ranks_read_the_core_not_the_bout_package():
    for name in ARENA_RANK_READERS:
        assert "bout" not in {feature_target(mod) for _, mod in _feature_imports(TIANXIA / f"{name}.py")}, name
        assert "arena_ranks" in (TIANXIA / f"{name}.py").read_text(encoding="utf-8"), name
    assert "arena_ranks" in (TIANXIA / "core" / "presence.py").read_text(encoding="utf-8")  # 身分字的擂台稱號（第 37 批）


# companions（全部拆包第 19 批「人物情誼一」：招募與名下、心意、託付與勸降、來信；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md 1.5、1.6）：
# 四張名單這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。核心原位碰這一包的都沒有第 11 批的掛鉤，改叫 Game 上一行的委派，沒有新增 GAME_DIRECT
GAME_IMPORTS |= {"tianxia.features.companions.actions"}
GAME_DELEGATES |= {
    # 搬進包的 29 個方法留 26 個（9 個私有）：server、假人、測試在叫的 17 個（roster_lines、owned_companions、add_to_team、remove_from_team、release_companion、
    # release_view、voice_stance、figure_view、errands_view、persuade_request、persuade、letter_view、read_letter、decline_letter、morning_mail、letter_request、
    # apply_letter），核心原位叫的 _recruit、_recruit_one、_stance_annals、_errand_options，引導包（ctx）與測試問的 _recruit_target、
    # _recruitable_here，測試直接叫的 _recruit_targets。_errand_act、_errand_reward、_errand_persuade 只有包裡叫（choose 改走掛鉤）
    "_recruit_target", "_recruit_targets", "_recruitable_here", "_recruit", "_recruit_one", "roster_lines", "owned_companions", "add_to_team",
    "remove_from_team", "release_companion", "release_view", "voice_stance", "figure_view", "errands_view",
    "_errand_options", "persuade_request", "persuade", "_stance_annals", "letter_view", "read_letter", "decline_letter", "morning_mail",
    "letter_request", "apply_letter",
    # 原位那幾行的本體一起搬進包（選單招募那一段、同步書信那一格、勸降只叫出輸入框）
    "_recruit_options", "_deliver_mail", "_errand_ask",
}
del GAME_DELEGATE_CALLERS[("_recruit_one", "_settle_partings")]  # _recruit_one 進了包，經 ctx._settle_partings 問（服務清單二、查詢服務）
GAME_DELEGATE_CALLERS[("sync", "_settle_partings")] = ("同步的同伴回江湖（簽到之後、退押金之前）：on_sync 在寄放之前、還問 enabled，江湖紀錄的先後算行為；"
                                                       "本體在決戰包 muster，核心原位叫查詢服務（總表第 19 列「先做」）")
_MENU_ORDER = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）；options 掛鉤在體力玩法之後、位置不對。選單照包排是總表第 55～57 批"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_recruit_options"): "招募那一段（求見之後、前往之前）：" + _MENU_ORDER,
    ("_everyday_options", "_errand_options"): "託付那一顆（伏筆之後、邀請之前）：" + _MENU_ORDER,
    ("sync", "_stance_annals"): "同步記心意的行狀（痕跡 _marks_tick 之後、列傳 _zhuan_tick 之前，三樣都寫行狀，先後算行為）；on_sync 在更後面、還問 enabled",
    ("sync", "_deliver_mail"): "同步書信那一格（欠人物的事過了期限〔parley.lapse，第 20 批搬進同一包、併進 deliver_mail〕、人物來信、過期的委託作罷，一則「書信」併著寫，先後算行為）：deliver_notices 在領地爭奪換天之前、位置不對",
    ("_act", "_recruit"): "act:recruit：核心 act: 的子動詞，總表第 57 批接進 Verb（同第 22 批 PM 認定第 4 條的 act:rest）",
    ("_act", "_recruit_one"): "act:recruit:<id>：同上；Verb 照 verb == 比，這一格第 57 批要照前綴認",
    ("choose", "_errand_ask"): "勸降按下去只叫出輸入框：查完選單、建紀錄之前，同 battle: 那一支的位置（第 7 批 PM 認定第 1 條）；第 57 批「選單上、不建紀錄」那一格一起接",
})
# companions（全部拆包第 20 批「人物情誼二」：人物對話、NPC 智能 2.0；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md 1.5、1.6）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。_stance_before、_stance_credit 兩個委派只有搬走的 talk、road_say 在叫，包裡互相叫之後拿掉了（上面）
GAME_IMPORTS |= {"tianxia.features.companions.talk_actions", "tianxia.features.companions.parley_actions"}
GAME_DELEGATES |= {
    # 搬進包的 29 個方法（第 20 批審查把 _talk、_road_say 換成 choose 掛鉤）留 11 個（9 個私有）：server 與測試在叫的 dialogue_request、say_max、_checked_prepared、_parley_lists、_parley_prompt、_parley_options、
    # _annal_talk（tests/core/test_annals.py 直接叫）；
    # 核心原位叫的 _open_dialogue（交友與求見開口，第 21 批）、_last_talk_line（場景文字）、_parley_road_option（路上的選單）；
    # 出陣包經 ctx 問的 _parley_backing_here。其餘 16 個（_dialogue_unavailable、_prepared_turn、_parley_finish……）只有包裡叫，沒有委派
    "dialogue_request", "say_max", "_checked_prepared", "_parley_lists", "_parley_prompt", "_parley_options", "_annal_talk", "_open_dialogue",
    "_last_talk_line", "_parley_road_option", "_parley_backing_here",
    # 原位那幾行的本體一起搬進包（選單上談著的那一整段、叛投之後欠著的都算食言）
    "_talk_options", "_parley_forsake",
    # 審查補搬：總表附錄甲點名第 20 批的 affinity_text（談話畫面名字底下的「情誼 N」；server 的人物頁、場景卡、測試在叫）
    "affinity_text",
}
_TALK_MENU = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）；談著的時候整個選單是對話的，`menu` 掛鉤要照包排，是總表第 55～57 批"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_talk_options"): "跟人物談著：" + _TALK_MENU,
    ("_everyday_options", "_parley_road_option"): "路上跟他說一句那一顆（折返之後、喊停之前）：" + _TALK_MENU,
    ("choose", "_checked_prepared"): "進鎖後重驗鎖外生成的一輪對話（查完選單、建紀錄之前）：choose 前段，第 57 批「選單上、不建紀錄」那一格再看",
    # （talk:、parley:road 按下去〔talk、road_say〕第 20 批審查接上 choose 掛鉤：prepared 與 said 經 ctx._talk_turn、_talk_said 寄放，同勸降的 _persuade_said）
    ("choose", "say_max"): "「自己說」最多幾個字：choose 前段驗那句話",
    ("_own_scene_text", "_last_talk_line"): "談話畫面名字底下的「上回」那一行：場景文字（_own_scene_text）的一部分。不接 scene 掛鉤的理由（第 20 批審查）：掛鉤坐在一條線的答題"
                                            "（storyline.question_text）之前，談話這一段在答題之後；包的登記順序又是人物情誼排在有所感前面，接成掛鉤得替它補「答題開著就讓路」"
                                            "與「有所感開著就讓路」兩道守衛，位置算行為，這一批的軌證明不了兩者永不並存，所以維持委派",
    ("_own_scene_text", "affinity_text"): "談話畫面名字旁的「情誼 N」：同上一筆（場景文字的一部分，不接 scene 掛鉤）",
    ("scene_art", "affinity_text"): "談話那張人物卡（scene_art）的副標也寫「情誼 N」：與 _own_scene_text 同一個詞，兩處不能各拼一份",
    # （原本這裡有 ("_socialize", "_open_dialogue")、("_precise_socialize", ...)、("_call", ...) 三筆：第 21 批交友求見搬進 socialize 包，包裡經 ctx._open_dialogue 問，拿掉）
    ("_defect_step", "_parley_forsake"): "叛投之後欠著的都算食言（NPC 智能 2.1）：接在 defection.defect 與 _leave_behind 之後，回話的先後算行為；叛投第 36 批再看",
})
# sense（全部拆包第 24 批「有所感與頓悟」：新包 tianxia/features/sense/；計畫 docs/superpowers/plans/2026-11-01-有所感包-第1批.md 1.4、1.5）：
# 四張名單的有所感那幾筆集中在這一段（並行的拆包線不跟別人的行穿插；拿掉的在原處）。核心原位碰有所感的那幾處，能接第 11 批掛鉤的接上
# （choose 掛鉤接 sense:、scene 掛鉤接場景卡），接不了的改叫 Game 上一行的服務委派、記進 GAME_DELEGATE_CALLERS 寫理由（不新增 GAME_DIRECT）
GAME_IMPORTS |= {
    # 8 個方法的一行委派、7 個服務的本體（actions）；原本那一行 `from . import (..., sensing, ...)` 與 `from . import epiphany`（登記一條線的
    # 鉤子）現在是別名：委派的型別註記用，探索包的 test_explore_one_2f 換的是 tianxia.engine.sensing.missed_today（engine 要有這個名字）
    "tianxia.features.sense.actions", "tianxia.sensing", "tianxia.epiphany",
}
GAME_DELEGATES |= {
    # 探索包回答有所感包的查詢服務（主人 explore）：擲特殊頓悟的 boost（原本 Game._sense 直接讀 outing_rules 那一筆 GAME_DIRECT 換成它）
    "_rare_boost",
    # 搬進包的 10 個方法留 8 個（3 個私有）：server 與假人叫的 epiphany_request、epiphany_names、sense_request、sense_draw、method_help，
    # 測試直接叫的 _epiphany_begin，choose 原位叫的 _epiphany_name（dunwu:），探索包與 explore_base.explore_outcome 叫的 _sense_here。
    # _sense（sense: 由 choose 掛鉤接走）、_sense_apply 只有包裡叫
    "_epiphany_begin", "_epiphany_name", "epiphany_request", "epiphany_names", "sense_request", "sense_draw", "_sense_here", "method_help",
    # 核心原位與探索、引導兩包叫的服務 7 個（Task 2 開的；本體在 actions）
    "_sense_missed", "_sense_drop_stale", "_sense_menu", "_sense_start", "_sense_canvas", "_epiphany_title", "_sense_prologue_choice",
}
_LATER_18 = "舊探索（留給序章與測試內容；總表第七節第 1 題選甲，沒有下一批要收）"
GAME_DELEGATE_CALLERS.update({
    ("_drop_stale_references", "_sense_drop_stale"): "清失效參照中段（收店之前）：後面的收店（features_core.drop_shops → 酒肆 Shop.here → _idle）讀 "
                                                     "player.sensing，on_drop_stale 在最後、還只問開著的包",
    ("_everyday_options", "_sense_menu"): "選單：有所感的卡與取名在擂台那一支之後、一條線的答題之前；接 menu 掛鉤留給總表第 57 批"
                                          "（第 24 批 PM 認定第 2 條）",
    ("_insight_blocked", "_sense_missed"): "舊探索那一行（action_notes）句尾補什麼時候才悟得出：" + _LATER_18,
    ("choose", "_sense_canvas"): "「畫下來」只叫出畫布：查完選單、清掉「剛剛」與引導之後、建紀錄之前（同 battle:），「選單上、不建紀錄」那一格"
                                 "留給核心批（總表第 57 批）",
    ("choose", "_epiphany_name"): "dunwu:（特殊頓悟取名）：要帶自己寫的名字（choose 的 text），choose 掛鉤不帶 text，留在原位的 elif",
    ("_action_title", "_epiphany_title"): "dunwu: 那一下江湖紀錄的標題（同上，dunwu: 留在原位）",
})
CORE_DELEGATE_CALLERS_SENSE = {  # 核心本體經 ctx 叫包的委派
    ("services.outing_watch", "_outing_watched"): "走一趟停在要選的事上時這一下選完的得失（探索包的委派）：裝飾器原本是 engine.py 模組層的 "
                                                  "_outing_watch，掛在 Game.choose、answer_event 與有所感包的 sense_draw、epiphany_names 上；"
                                                  "包不能 import engine，第 24 批搬進核心的共用小函式。「做完一件事」歸總表第 57 批（第 26 批 PM 認定第 6 條）",
}
# explore（全部拆包第 18 批「探索三」：舊探索的底 8 個方法搬進 tianxia/features/explore/explore_base.py，Game 留 6 個一行委派；計畫
# docs/superpowers/plans/2026-11-04-探索包-第3批.md 1.1、1.4）：這一批加的集中在這一段。_explore_outcome、_here_squads 只有包裡自己叫，Game 上不留。
GAME_DELEGATES |= {"_practice_tier", "_explore", "_legend_find", "_explore_weights", "_explore_can", "_wild_foes"}
GAME_DELEGATE_CALLERS.update({
    ("_act", "_explore"): "關著探索一顆時的舊探索（扣體力、晉升奇遇、序章的舊探索都在它前面；第 11 批 README 認定留原位，不改成 Verb）",
    ("action_notes", "_explore_weights"): "行動列底下那一行的舊探索句（掛鉤 act_note 回 None 時）：" + _LATER_18,
    ("_fierce_line", "_practice_tier"): "輿圖的地點卡與詳情（place_detail）：這一處練功第幾級；輿圖不是這一包（feature/map-view）",
})
# cultivation（全部拆包第 23 批「修練」：改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡、傳功、配點搬進修練包 tianxia/features/cultivation/；計畫
# docs/superpowers/plans/2026-11-01-修練包-第1批.md 1.6）：這一批加的集中在這一段（並行的拆包線不跟別人的行穿插；拿掉的在原處）
# 22 個動作（actions）、11 個修練頁的唯讀資料（view）的一行委派；原本那兩行 `from . import ascend`、`from . import (..., chuangong, ...,
# cultivation, ...)` 現在是別名，engine 不再用，拿掉。MELT_MANY_PROLOGUE（序章裡批量熔煉那一句）搬進包，tests/core/test_prologue.py 照舊從 engine 拿
GAME_IMPORTS |= {"tianxia.features.cultivation.actions", "tianxia.features.cultivation.view"}
GAME_DELEGATES |= {
    # server（MENXIA_ACTIONS、menxia_view、main_view 的境界卡、/api/do/allocate、破境卡那一句的三段式）、假人（bot、bot_policy）、測試在叫的：
    # 改練、練成、意境裝卸、熔煉、服丹衝關、舊存檔的定名（A 段與 C 段）、破境卡、傳功、配點與境界卡（20 個）、修練頁的唯讀資料（11 個）
    "switch_art", "practice", "practice_refusal", "slot_insight", "unslot_insight", "melt_art", "melt_many", "melt_insight", "cultivate",
    "mastery_request", "name_mastered", "ascend_request", "ascend_line", "ascend_dismiss", "chuangong", "chuangong_lessons", "allocate_stat",
    "milestone_card",
    "skill_detail", "art_detail", "member_card", "roster_cards", "menxia_rules", "attribute_note", "bag_text", "holdings", "art_rows",
    "insight_rows", "naming_row",
    # 核心原位叫的 2 個私有（_drop_stale_references、sync；_drop_old_zhuifeng 測試也直接叫）與兩個新的查詢（絕學的契機：核心的單打服務 _seize、
    # 決戰包的收場補送經 ctx 叫；破境卡：status_data）。_allocate_line 只有 allocate_stat 叫，包裡直接叫 actions.allocate_line，不留
    "_drop_old_zhuifeng", "_deliver_renames", "_seize_chance", "ascend_view",
}
GAME_DELEGATE_CALLERS.update({
    ("_drop_stale_references", "_drop_old_zhuifeng"): "讀檔清失效參照：追風步的舊品質要在 arts.migrate（槽數照品質算）之前拿掉；on_drop_stale 在最後、"
                                                      "位置不對（先後算行為）",
    ("sync", "_deliver_renames"): "同步時補別人定名的那一則：玉璽補送之後、首創名望回饋之前（江湖紀錄的先後算行為）；deliver_notices 在名望回饋與"
                                  "護衛補帳之後、on_sync 還問 enabled 且在寄放之前，都不是這個位置",
    ("_seize", "_seize_chance"): "核心的單打服務打贏一場之後擲絕學的契機：總表第 26 批的事件（打贏一場；原位行尾標「# 過渡：第 26 批」）",
    ("status_data", "ascend_view"): "狀態列的破境卡（status 的 ascension 那一格）：status 掛鉤合進 main_view 的頂層、不是這一格，鍵的順序算行為"
                                    "（狀態列順序，總表第 66 批）",
    # （_graduate_pass 叫 slot_insight、switch_art、practice、allocate_stat、melt_art 那 5 對：第 22 批把 _graduate_pass 搬進引導包、經 ctx 叫，合併時拿掉）
})

# socialize（全部拆包第 21 批「交友求見」：新包 tianxia/features/socialize/；計畫 docs/superpowers/plans/2026-11-04-交友求見包-第1批.md 1.1、1.4）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。31 個方法搬進包，留 21 個一行委派（10 個只有包裡叫，沒有委派）；
# `call:` 的 choose 與 _action_title 的那一格接了掛鉤（Outcome），`bot_policy.score` 的 call 那一段搬進包的 bots.py
GAME_IMPORTS |= {"tianxia.features.socialize.actions", "tianxia.features.socialize.menus", "tianxia.features.socialize.view"}
GAME_DELEGATES |= {
    # 核心原位叫的：選單（_precise_social_option、_socialize_option、_audience_options）、行動列說明（_socialize_figure、_audience_hall、_fame_gap、_can_meet、
    # _talked_out_note）、_act 的 act:socialize（_socialize）、sync（_audience_hall）、補算時間（_deliver_fortune）、場景文字（_audience_intro）
    "_precise_social_option", "_socialize_option", "_audience_options", "_socialize_figure", "_audience_hall", "_fame_gap", "_can_meet",
    "_talked_out_note", "_socialize", "_deliver_fortune", "_audience_intro", "_talks_left",
    # 別的包經 ctx 問的（服務清單二、查詢）：_can_meet、_socialize_figure、_count_talk（人物對話的 A 段與每一輪收尾）、_social_plan、_brush_off（開口與開單）
    "_social_plan", "_count_talk", "_brush_off",
    # server、假人、腳本、測試在叫的：can_meet_figure（bot.py）、socialize_starts_dialogue、socialize_is_futile（bot_policy）、_talk_cap（玉璽測試）、
    # _talks_used（tests/core/test_engine.py、tests/server/test_server.py）、_deep_interaction_target（tests/season/test_real_content.py）
    "can_meet_figure", "socialize_starts_dialogue", "socialize_is_futile", "_talk_cap", "_talks_used", "_deep_interaction_target",
}
_ACT_VERB = "act:socialize、act:call 是 act 子動詞（總表第 57 批才接 Verb.cell、Verb.note、Verb.run）：行動列那一格、底下那一行、按下去，留在核心原位叫這一包的委派"
_AUDIENCE_ONE = "單人地點的「求見某某」（call:<人物>）那一顆：選單上直接列的求見，是 act 子動詞那一格旁邊的選項建構（總表第 57 批），四個分支問閉門不見、見不見得到、差多少、談滿了沒"
GAME_DELEGATE_CALLERS.update({
    ("_act", "_socialize"): _ACT_VERB + "（act:socialize 的動作；最後一行）",
    ("_everyday_options", "_precise_social_option"): _ACT_VERB + "（一類一顆的交友那一顆）",
    ("_everyday_options", "_socialize_option"): _ACT_VERB + "（交友那一顆）",
    ("_everyday_options", "socialize_is_futile"): _ACT_VERB + "（交友撲空時灰掉的判斷）",
    ("_everyday_options", "_can_meet"): _AUDIENCE_ONE,
    ("_everyday_options", "_fame_gap"): _AUDIENCE_ONE,
    ("_everyday_options", "_talks_left"): _AUDIENCE_ONE,
    ("_everyday_options", "_talked_out_note"): _AUDIENCE_ONE,
    # 求見名單的選單：`menu` 掛鉤坐在 sense_menu、一條線答題、談著、選邊、投靠確認、叛投確認這幾個 picking_* 之前（選單的順序算行為，同 _TALK_MENU），
    # 名單這一行夾在叛投確認與懸賞榜中間，接成掛鉤就改了它們並存時誰先；所以留委派
    ("_everyday_options", "_audience_options"): "求見名單（picking_audience）：" + _MENU_ORDER,
    # 場景文字同理：`scene` 掛鉤坐在談話、選邊、投靠、叛投那幾段之前，求見畫面夾在叛投之後、伏筆答題之前，位置算行為，留委派
    ("_own_scene_text", "_audience_intro"): "求見畫面的說明（picking_audience）：場景文字夾在叛投確認與伏筆答題之間，`scene` 掛鉤坐在更前面，位置算行為",
    ("_advance_player_local", "_deliver_fortune"): "福緣到期自己送上門：夾在閉關收尾與別的補算中間，on_sync 沒有對應的位置",
    ("action_notes", "_socialize_figure"): _ACT_VERB + "（交友那一行說明）",
    ("action_notes", "_audience_hall"): _ACT_VERB + "（求見那一行說明）",
    ("action_notes", "_can_meet"): _ACT_VERB + "（單人求見那一行說明）",
    ("action_notes", "_fame_gap"): _ACT_VERB + "（同上）",
    ("action_notes", "_talks_left"): _ACT_VERB + "（同上）",
    ("action_notes", "_talked_out_note"): _ACT_VERB + "（同上）",
})

# story（全部拆包第 30 批「一條線」：新包 tianxia/features/story/；計畫 docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md 1.5、1.6）：這一批加的集中在這一段
# （並行的拆包線不跟別人的行穿插）。核心原位碰一條線的幾處，能接第 11 批掛鉤的接上（choose 掛鉤接 story:，標題一起帶），接不了的改叫 Game 上一行的委派、
# 記進 GAME_DELEGATE_CALLERS 寫理由（不新增 GAME_DIRECT）。原本那行 `from . import storyline`、`chapters` 拿掉：JOURNAL、場景圖、題目文字、線的定義
# 改讀共用規則層 story_base（不算過渡）；章回主線 chapters 的模組層 import 搬到包的 actions.py（載入時登記 storyline.TASKS）
GAME_IMPORTS |= {"tianxia.features.story.actions"}
GAME_DELEGATES |= {
    # 搬進包的 10 個方法留 10 個一行委派：server（MAIN_ACTIONS 的 story_seen、main_view 的 story_cards）、假人與腳本（story_start）、測試（story_cards、
    # _story_begin、_story_tick、_mirror_squad）、探索包（ctx._story_begin）、核心原位（_story_tick）在叫的；_story_act、_story_fight、_story_bout 只有包裡叫
    "story_start", "story_cards", "story_seen", "story_card_view", "_story_begin", "_story_tick", "_mirror_squad",
    # 核心原位叫的 3 個（本體在 actions）：答題的選單、「未了之事」那一顆、換季收線
    "_story_menu", "_story_options", "_story_close_season",
}
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_story_menu"): "選單：一條線的答題在有所感的選單之後、此地有人要談的選單之前；接 menu 掛鉤的位置不對（menu 掛鉤在有所感的 _sense_menu 之前，"
                                          "同時成立時先後會變），/api/main 的選項順序算行為",
    ("_everyday_options", "_story_options"): "選單：「未了之事」那一顆在應召之後、此地的人之前；options 掛鉤在體力玩法之後（最後面），順序算行為",
    ("_reset_player_for_new_season", "_story_close_season"): "換季：還沒收的線要在 world.save_annals 存上一季的行狀之前寫「此事未了」進傳；on_season_end 在 save_annals 之後，來不及",
    ("sync", "_story_tick"): "同步：不在線時過了的期限、休季時還沒收的線在召見之後、席次之前走一步；紀錄先後算行為，on_sync 在召見之前",
    ("choose", "_story_tick"): "每個動作結束那一格（事件了結之後、召見之前）：不是任何掛鉤的位置",
    ("_event_progress", "_story_tick"): "事件了結的推進：段落事件了結了，照記下的那一步往下走；同上",
})

# checkin（全部拆包第 30 批「簽到」：新包 tianxia/features/checkin/；計畫 1.5、1.6）：核心原位碰簽到的兩處沒有第 11 批掛鉤可接，改叫 Game 上一行的委派。
# 原本那行 import 的 checkin 拿掉：回體丹那一套（Game._pill_find）改叫核心 core/services.py 的 checkin_on、PILL_FOUND。
# 引導那一段（# guide）原本記的 (check_in／_auto_checkin／checkin_view, _opening_pending／_opening_gate) 四對，呼叫端搬進簽到包、經 ctx 叫，在 CORE_DELEGATE_CALLERS_CHECKIN
GAME_IMPORTS |= {"tianxia.features.checkin.actions"}
GAME_DELEGATES |= {
    # server（MAIN_ACTIONS["checkin"]）、假人（bot.check_in 叫 checkin_view、check_in）、測試在叫的 check_in、checkin_view，與核心原位 sync 叫的 _auto_checkin
    "check_in", "_auto_checkin", "checkin_view",
}
GAME_DELEGATE_CALLERS.update({
    ("sync", "_auto_checkin"): "同步的每日簽到自動領：在補送裝備（_deliver_held_gear）之後；on_sync 掛鉤在它前面，不能接，紀錄先後算行為",
    ("status_data", "checkin_view"): "狀態列的簽到小標（status 的 checkin 那一格）：在 howto_entry 之後、fronts 之前，鍵的順序算行為；feature_status 是 main 的頂層、位置不對",
})
# 簽到的三個方法搬進簽到包，不再是 Game 上的呼叫端：它們問引導的 _opening_pending／_opening_gate 改成包裡經 ctx 叫（服務清單二、查詢服務 # checkin）
for _pair in (("check_in", "_opening_pending"), ("check_in", "_opening_gate"), ("_auto_checkin", "_opening_pending"), ("checkin_view", "_opening_pending")):
    del GAME_DELEGATE_CALLERS[_pair]

# zhuan（全部拆包第 29 批「列傳」：新包 tianxia/features/zhuan/；計畫 docs/superpowers/plans/2026-11-04-列傳包-第1批.md 1.1、1.5）：Game 上 20 個方法搬進包，
# 留 9 個一行委派；休季用票的 choose 換成 choose_unlisted 掛鉤（兩行拿掉）。三處核心原位叫的委派沒有掛鉤可接（紀錄先後算行為）。
GAME_IMPORTS |= {"tianxia.features.zhuan.actions"}
GAME_DELEGATES |= {
    # server（行狀頁、main_view 的讀傳入口、寫傳的 A、C 段、讀傳、分享）、測試在叫的；_zhuan_past、_zhuan_tick、_zhuan_options 是核心原位叫的（下）
    "annals_view", "biography_entry", "biography_request", "write_biography", "biography_view", "share_biography",
    "_zhuan_past", "_zhuan_tick", "_zhuan_options",
}
GAME_DELEGATE_CALLERS.update({
    ("_reset_player_for_new_season", "_zhuan_past"): "換季那一刻補上一季的季末論功與〈天下形勢〉：在 _story_close_season 之前、最前面，紀錄先後算行為",
    ("sync", "_zhuan_tick"): "同步記行狀（_stance_annals 之後、_deliver_mail 之前）：on_sync 在更後面、還問 enabled，紀錄先後算行為",
    ("_everyday_options", "_zhuan_options"): "休季的行動列：用列傳的票排在休季那一支選單裡，不是店面也不是 menu 掛鉤的位置",
})
# zhuan 第 29 批之二（annals 拆兩半）：換季存行狀時的身家 profile 在包裡（standing.py），核心不能 import 包，經一行委派 _zhuan_profile；
# 記一筆的那一半收進核心 core/annal_base.py，包與核心原本的 annals 過渡 import 都改它。
GAME_DELEGATES |= {"_zhuan_profile"}
GAME_DELEGATE_CALLERS.update({
    ("_reset_player_for_new_season", "_zhuan_profile"): "換季存行狀（save_annals 的第四個引數）時的身家：位置不動，紀錄先後算行為",
})


# strip（全部拆包第 13 批「拿掉一」：探索三選一、找素材「自己說」、城裡操練；計畫 docs/superpowers/plans/2026-11-04-拿掉一-第13批.md）：
# 這一批多半是刪（刪的在原處），加的集中在這一段
GAME_DELEGATES |= {
    "_home_gather",  # 本體搬進探索包（explore_actions.home_gather）；探索包經 ctx 叫這一行，測試換它、same_behavior 叫它（經 ctx 的規矩，手冊第十五節）
}


# figure_acts（全部拆包第 31 批「大勢人物」：新包 tianxia/features/figure_acts/；計畫 docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md 1.1、1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。24 個方法搬進包，留 14 個一行委派（10 個只有包裡或測試在叫，沒有委派，測試改叫包函式）；
# `aid:`、`plan:` 的 choose 與 _action_title 的兩格接了掛鉤（Outcome），`bot_policy.score` 的 aid 那一段搬進包的 bots.py，bot.py 的 aid: 改 bot_always
GAME_IMPORTS |= {
    "tianxia.features.figure_acts.admin_actions", "tianxia.features.figure_acts.aid_actions", "tianxia.features.figure_acts.challenge",
    "tianxia.features.figure_acts.plan_actions", "tianxia.features.figure_acts.yuedan_actions",
}
GAME_DELEGATES |= {
    # 核心原位叫的：選單（_challenge_options、_aid_options、_plan_options）、閉門不見（_snubbed_character）、挑戰的對手隊伍（_figure_squad）、
    # 按下去（_challenge）、同步補名望（_deliver_guard_credits）
    "_challenge_options", "_aid_options", "_plan_options", "_snubbed_character", "_figure_squad", "_challenge", "_deliver_guard_credits",
    # 被測試換掉的：_rout（challenge 經 ctx._rout 叫，批次表第二節）；只有測試直接叫的：_challenge_reward、_figure_tier3、_figure_tier4（留委派，測試不改）
    "_rout", "_challenge_reward", "_figure_tier3", "_figure_tier4",
    # server、假人、腳本、測試在叫的：challenge_odds（bot.py、bot_policy、測試換掉它）、plan_view、place_deeds_view（main_view）、yuedan_request、apply_yuedan（月旦評三段式）、
    # admin_fallen、admin_revive_figure（管理頁）
    "challenge_odds", "plan_view", "place_deeds_view", "yuedan_request", "apply_yuedan", "admin_fallen", "admin_revive_figure",
}
_ACT_CHALLENGE = ("act:challenge:<人物> 是 act 子動詞，帶後綴接不了 Verb（總表第 57 批才擴）：選單那一格、按下去、標題都留在核心原位叫這一包的委派")
_AID_PLAN_MENU = ("選單的順序算行為（/api/main 的選項一顆一顆逐位元組）：末段 `opts + 護衛 + features_core.options + 盤算`，護衛那串在包選項之前、盤算在之後，"
                  "夾著 `options` 掛鉤，接成掛鉤登記在後面的包會排在盤算之後")
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_challenge_options"): _ACT_CHALLENGE + "（選單：在 act:train 那格與晉升奇遇之間）",
    ("_everyday_options", "_snubbed_character"): _ACT_CHALLENGE + "（單人求見那顆灰掉的判斷）",
    ("action_notes", "_snubbed_character"): _ACT_CHALLENGE + "（行動列底下那一行說明：閉門不見的人不算此地可求見）",
    ("_stamina_play_options", "_aid_options"): _AID_PLAN_MENU,
    ("_stamina_play_options", "_plan_options"): _AID_PLAN_MENU,
    ("_fight_squad", "_figure_squad"): "act:challenge: 的對手隊伍（大場面判讀的鎖外 A 段與鎖內 C 段重驗）：" + _ACT_CHALLENGE,
    ("_act", "_challenge"): _ACT_CHALLENGE + "（按下去）",
    ("sync", "_deliver_guard_credits"): "同步補名望與心得：夾在 _deliver_echoes 與 deliver_notices 之間，FEATURES 新包排在最後，酒肆的 deliver_notices 會跑在它前面，行狀順序會變",
})
# military（全部拆包第 33 批「軍情一」：新包 tianxia/features/military/；計畫 docs/superpowers/plans/2026-11-05-軍情包-第1批.md 1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。17 個方法搬進包，留 15 個一行委派（`_check_cost_note`、`_rank_action_line` 只有包裡自己叫，沒有委派）。
# 沒有選項前綴、沒有掛鉤可接：`act:rank2`、`act:convoy`、`act:summons`、`act:rank:<行動>` 是核心 `_act` 的 act 子動詞（行動列，總表第 57 批才接 Verb），
# 選單三段夾在 `_everyday_options` 的 act 那些之間（順序算行為）。`bot_policy.score` 的 act 分支原位不動。
GAME_IMPORTS |= {
    "tianxia.features.military.order_actions", "tianxia.features.military.convoy_actions", "tianxia.features.military.step_actions",
    "tianxia.features.military.seat_actions", "tianxia.features.military.admin_actions",
}
GAME_DELEGATES |= {
    # 核心原位叫的：選單三段、按下去三個（_rank2、_rank_action、_take_convoy）、走到終點交糧車（_convoy_arrives）、軍令記功（_order_credit：出陣、決戰、大勢人物也經它）、
    # 席次抄帳（_report_seat）、管理者召見的規劃（_summons_plan）
    "_order_options", "_rank2_options", "_rank_action_options", "_rank2", "_rank_action", "_take_convoy", "_convoy_arrives", "_order_credit",
    "_report_seat", "_summons_plan",
    # server 與測試在叫的：江湖頁的軍令卡與押糧那一行（/api/main）、管理者三顆鈕（/api/admin）
    "orders_view", "convoy_line", "admin_issue_orders", "admin_rotate_seats", "admin_summon",
}
_ACT_RANK = "act:rank2／act:convoy／act:rank:<行動> 是核心 act 子動詞（行動列），總表第 57 批才擴 Verb：選單那一段、按下去都留在核心原位叫這一包的委派"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_order_options"): _ACT_RANK + "（選單：軍令的守勢與糧車，排在第 2 階之前；順序算行為）",
    ("_everyday_options", "_rank2_options"): _ACT_RANK + "（選單：第 2 階行動）",
    ("_everyday_options", "_rank_action_options"): _ACT_RANK + "（選單：第 3、4 階行動）",
    ("_act", "_rank2"): _ACT_RANK + "（按下去：第 2 階行動）",
    ("_act", "_rank_action"): _ACT_RANK + "（按下去：第 3、4 階行動）",
    ("_act", "_take_convoy"): _ACT_RANK + "（按下去：接下糧車）",
    ("_arrive", "_convoy_arrives"): "走到地點那一刻交糧車（路過也算）：先交糧車、再接懸賞榜的護送交差，位置固定、沒有對應的掛鉤（移動成包時，總表第 56 批再看）",
    ("_squad_encounter", "_order_credit"): "戰鬥（核心的單打服務）打贏之後替軍令記功：位置固定在推線與地盤進度之間（出陣攻打的記功排在推進度之前），沒有對應的掛鉤",
    ("sync", "_report_seat"): "同步的第四階席次抄帳與補缺（回話的最後一段，在 summons 之後）：on_sync 在更後面，回話的先後算行為",
    ("choose", "_report_seat"): "做完一個動作之後抄帳、補缺（這個動作結束時 _save_season 一起存）：位置在 after_action 之前，先後算行為",
    ("travel", "_report_seat"): "走完一趟之後抄帳（同 choose：正式版丁）；賽季時鐘暫停時什麼都不做這一句在委派的本體裡",
    ("admin_player_choices", "_summons_plan"): "管理者的玩家選單（發召見那一顆灰不灰、為什麼）與 admin_summon 共用同一個規劃（_summons_plan）",
})
# military（全部拆包第 34 批「軍情二」：機緣 opp: 與伏筆 fs: 搬進同一包；計畫 docs/superpowers/plans/2026-11-06-軍情包-第2批.md 1.1、1.4、1.5）：
# 這一批加的集中在這一段。5 個方法搬進包（_settle_plots、_hear_after_stamina、admin_give_opportunity、admin_give_fragment 留一行委派；_foreshadow 接 choose 掛鉤之後
# 沒人叫了，不留）。選項前綴 opp:、fs: 接 choose 掛鉤（Outcome.title 隨掛鉤搬走）；效果三格（grain、fs_fragments、foreshadow）與叛投兩格
# （clear 的 opportunities、leave 的 plots）改由包登記；rules 讀伏筆的換算、content 驗內容的天機表、ranks 與叛投確認畫面讀機緣，改讀核心的查詢服務
# core/omen_base.py。接不了掛鉤、留成委派的在下面每一條寫理由。events、narration、rumor_view、step、weekcard、server 讀伏筆機緣的規則走舊名別名
# （都是舊模組、不是核心也不在共用層；它們收進共用層〔第 36、40 批〕時再改成查詢服務）。
GAME_IMPORTS |= {"tianxia.features.military.opp_actions", "tianxia.features.military.fs_actions"}
GAME_DELEGATES |= {
    # 核心原位叫的：集體密謀結算（_settle_plots）、花體力之後抽片段與線索（_hear_after_stamina）、答題中的選單（_fs_asking_options）與場景文字（_fs_asking_text）、
    # 閒著的選單（_omen_options）、第 2 階行動的名字（_rank2_action）、遊歷打贏之後（_fs_after_win、_opp_on_win）、管理者的玩家選單（_admin_omen_choices）；
    # 事件檢定經 ctx 叫的 _hear_from_event；人物情誼包與出陣包經 ctx 問的查詢服務（_omen_talk_options、_fs_hear_talk、_opp_hear_topic、_opp_after_success）
    "_settle_plots", "_hear_after_stamina", "_fs_asking_options", "_fs_asking_text", "_omen_options", "_rank2_action", "_fs_after_win", "_opp_on_win",
    "_admin_omen_choices", "_hear_from_event", "_omen_talk_options", "_fs_hear_talk", "_opp_hear_topic", "_opp_after_success",
    # server 的管理者兩顆鈕（/api/admin：give_opportunity、give_fragment）
    "admin_give_opportunity", "admin_give_fragment",
}
_OMEN_MENU = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）；"
GAME_DELEGATE_CALLERS.update({
    ("sync", "_settle_plots"): "同步的集體密謀結算：位置固定在 sync 的中段，沒有對應的掛鉤（world 的 sync 順序算行為）",
    ("choose", "_settle_plots"): "做完一個動作之後的集體密謀結算：位置在回話的最後一段，沒有對應的掛鉤",
    ("choose", "_hear_after_stamina"): "花體力的動作之後抽伏筆片段與機緣線索：位置在 choose 結尾、after_action 之前，伏筆先機緣後、共用 self.rng，擲骰順序算行為，沒有對應的掛鉤",
    ("travel", "_hear_after_stamina"): "輿圖安排前往走完一趟之後同樣抽一次（同 choose）：位置固定，沒有對應的掛鉤",
    ("_everyday_options", "_fs_asking_options"): _OMEN_MENU + "答題中的選單排在店面 shop_menu 之後、閉關之前，menu 掛鉤在更前面（宴客、有所感之前），位置不同不能接",
    ("_everyday_options", "_omen_options"): _OMEN_MENU + "機緣與伏筆最後一步夾在 _rank_action_options 與 _errand_options 中間，options 掛鉤是另一個選單（體力玩法之後），位置不同不能接",
    ("_action_title", "_rank2_action"): "act:rank2 的江湖紀錄標題寫第 2 階行動自己的名字（招降黃巾散兵、施符水收人心）；act 子動詞的標題在表上，第 2 階行動接 Verb 是總表第 57 批",
    ("_squad_encounter", "_fs_after_win"): "遊歷打贏之後擲官銀：夾在軍令記功前後，「一包發生了、別包跟著動」是總表第 26 批的事件（打贏一場）",
    ("_squad_encounter", "_opp_on_win"): "遊歷打贏之後記密謀一處（三路並進）：夾在軍令記功與懸賞討伐之間，同上（總表第 26 批）",
    ("_own_scene_text", "_fs_asking_text"): "答題中的場景文字排在拜入、投靠、叛投、求見的畫面之後、趕路的畫面之前，scene 掛鉤在更前面（有所感、宴席之後、談話之前），位置不同不能接",
    ("admin_player_choices", "_admin_omen_choices"): "管理者的玩家選單（/api/admin/player）最後兩鍵：可以給的機緣與伏筆片段，鍵的順序算行為，沒有對應的掛鉤",
})

# craft（全部拆包第 44 批「煉製與自創」：新包 tianxia/features/craft/；計畫 docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md 1.4、1.5）：
# 16 個一行委派（煉製頁開爐 5 個、自創 11 個）；原本那一行 `from . import create` 現在是別名（委派的型別註記 create.IntentRequest、IntentReading 用）。
# 沒有選項前綴、沒有 GAME_DIRECT。
GAME_IMPORTS |= {"tianxia.features.craft.actions", "tianxia.create"}
GAME_DELEGATES |= {
    # server（MENXIA_ACTIONS、開爐與立意的鎖外三段式、/api/forge_line）、假人（bot_policy.tend_arts、bot.create_art、forge_and_cultivate）、測試、
    # 引導包的假人走序章（ctx.forge）在叫的；create_view 是核心原位 status_data 叫的（下）
    "forge_request", "forge", "forge_line", "forge_preview", "forge_picks", "create_begin", "create_pose", "create_request", "create_intent",
    "create_reread_request", "create_reread", "create_reroll", "create_back", "create_name", "create_cancel", "create_view",
    # 引導包經 ctx 問的三個查詢服務（services.py 二、查詢服務 # craft）
    "_create_on", "_create_allowed", "_create_price",
}
GAME_DELEGATE_CALLERS.update({
    ("status_data", "create_view"): "狀態列的自創那一塊（status 的 create 鍵）：鍵的順序算行為，狀態列掛鉤是總表第 66 批",
})


# outlets（全部拆包第 43 批「銀兩出口與捐軍備」：新包 tianxia/features/outlets/；計畫 docs/superpowers/plans/2026-11-05-銀兩出口包-第1批.md 1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。17 個方法搬進包，Game 留 8 個一行委派（_close_dadian、_donate_choice 等只有包裡叫的沒有委派）。核心原位碰這一包的，能接第 11 批掛鉤的都接上了
# （兩間店的店面登記 shops：坐在店裡的選單、_shop_open、sync 與 _drop_stale_references 與 _depart 的收店；act:donate、dadian 與銀兩出口四樣的 Verb；
# choose 的 donate:、dadian: 與 _action_title 的兩格），拿掉的在原處。接不了的：「此地還能做」裡捐軍備與打點兩顆入口排在療傷之後（順序算行為，
# Shop.entry 回 None）；bribe:<人物> 帶後綴接不了 Verb（總表第 57 批才擴）；店面那一頁、狀態列、機器人與 server 叫的查詢。
GAME_IMPORTS |= {"tianxia.features.outlets.donate_actions", "tianxia.features.outlets.silver_actions"}
GAME_DELEGATES |= {
    # 核心原位叫的：_everyday_options 的兩顆入口（_donate_option、_silver_options）、_act 的 bribe:（_silver_act）、shop_view 的 dadian_view（_bribe_targets）、
    # status_data 的軍備存量（armament_view）；server 與假人叫的捐軍備（donate、donate_items、can_donate_here）
    "can_donate_here", "_donate_option", "donate", "donate_items", "_silver_options", "_bribe_targets", "_silver_act", "armament_view",
}
_OUTLETS_ENTRY = "「此地還能做」裡捐軍備與打點兩顆入口排在療傷之後（選單的順序算行為，/api/main 的選項一顆一顆逐位元組）：Shop.entry 回 None、入口留在原位叫委派"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_donate_option"): _OUTLETS_ENTRY,
    ("_everyday_options", "_silver_options"): _OUTLETS_ENTRY,
    ("_act", "_silver_act"): "act:bribe:<人物> 帶後綴接不了 Verb（總表第 57 批才擴），按下去留在核心 _act 叫委派",
    ("shop_view", "_bribe_targets"): "店面那一頁（打點的帳簿）要此地打點得了的人物，shop_view 是核心的店面殼",
    ("status_data", "armament_view"): "江湖頁的陣營軍備存量（status_data[\"armament\"]）：狀態列的資料，位置固定、沒有對應的掛鉤",
})

# territory_acts（全部拆包第 46 批「地盤」：新包 tianxia/features/territory_acts/；計畫 docs/superpowers/plans/2026-11-06-地盤包-第1批.md 1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。27 個方法搬進包，Game 留 20 個一行委派（_letter_key、_siege_you 等只有包裡叫的沒有委派）。
# 22:00 換天沒有掛鉤可接（世界層的 day 格是 21 天季的曆日，不是現實 22:00 的換天；engine 的 world_tick、sync、advance 把 _conquest_tick、_deliver_conquest
# 排在別的結算之間，順序就是行為），這五處改叫委派，不新增 GAME_DIRECT。原本 `import conquest_day`、`import xingshi` 兩行拿掉（舊名是指到包裡同一個模組的別名）。
GAME_IMPORTS |= {
    "tianxia.features.territory_acts.admin_actions", "tianxia.features.territory_acts.day_actions", "tianxia.features.territory_acts.letter_actions",
    "tianxia.features.territory_acts.view", "tianxia.features.territory_acts.xingshi_actions",
}
GAME_DELEGATES |= {
    # server（MAIN_ACTIONS 的下戰書、〈天下形勢〉A／C 兩段與背景執行緒、main_view 的 conquest／xingshi_mark、admin_choices 的 conquest）、
    # 測試與腳本（scripts/try_xingshi.py）叫的；letter_problem 只有測試叫（包裡的 view 直接叫 letter_actions.letter_problem）、conquest_view 是 server main_view 與測試叫的，
    # 兩個都沒有核心原位叫的；_conquest_tick、_deliver_conquest 是 engine 五處換天／補送叫的（下）
    "letter_problem", "conquest_letter", "_conquest_tick", "_deliver_conquest", "_xingshi_start", "_xingshi_open", "_xingshi_finish", "xingshi_waiting",
    "release_xingshi", "xingshi_request", "settle_xingshi", "xingshi_view", "xingshi_mark", "admin_xingshi_now", "conquest_view",
    "admin_conquest_set", "admin_conquest_progress", "admin_conquest_letter", "admin_conquest_cancel", "admin_conquest_choices",
}
_TERRITORY_TURN = ("22:00 換天（_conquest_tick）與分紅補送（_deliver_conquest）沒有掛鉤：世界層的 day 格是 21 天季的曆日，不是現實 22:00 的換天；"
                   "這個呼叫排在別的結算之間，順序就是行為（計畫 Review Focus 2）")
GAME_DELEGATE_CALLERS.update({
    ("world_tick", "_conquest_tick"): _TERRITORY_TURN + "：伺服器排程的 world_tick（沒人在線也收得掉）",
    ("sync", "_conquest_tick"): _TERRITORY_TURN + "：第一個看到新的一天的人（sync）",
    ("sync", "_deliver_conquest"): _TERRITORY_TURN + "：登入時補自己的分紅與守城功",
    ("advance", "_conquest_tick"): _TERRITORY_TURN + "：管理者快轉（advance，save=False）",
    ("advance", "_deliver_conquest"): _TERRITORY_TURN + "：同上",
})


# stamina_plays、seclusion（全部拆包第 39 批「體力玩法＋閉關」：新包 tianxia/features/stamina_plays/、tianxia/features/seclusion/；計畫
# docs/superpowers/plans/2026-11-06-體力玩法閉關-第39批.md 1.4）：這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。10 個方法搬進包，Game 留 7 個一行委派
# （_ambush_act、_ambush_fight、_works_act 只有包裡叫，沒有委派），另多一個 _stamina_play_head（_stamina_play_options 的前半），一共 8 個。核心原位碰這一包的：choose 的 ambush:、works:（choose 掛鉤）與 _action_title 的兩格、
# _act 的 act:break（Verb）拿掉；_stamina_play_options 的前半叫包（選單順序算行為，不能改成 Feature.options 登記）；世界層 muster 的 works 那一格換成包登記。
GAME_IMPORTS |= {"tianxia.features.stamina_plays.actions", "tianxia.features.stamina_plays.ambush_actions", "tianxia.features.seclusion.actions"}
GAME_DELEGATES |= {
    # server 與測試叫的閉關（seclusion_refusal、seclude）、_advance_player_local 叫的出關（_finish_seclusion）、sync 叫的收伏、_arrivals 叫的查伏兵，
    # 與測試直接叫的搶奪（_ambush_spoils）、戰報（_ambush_record）
    "seclusion_refusal", "seclude", "_finish_seclusion", "_stamina_play_head", "_ambush_expire", "_ambush_check", "_ambush_spoils", "_ambush_record",
}
GAME_DELEGATE_CALLERS.update({
    ("_advance_player_local", "_finish_seclusion"): "體力回復之後、財運之前：自己滿時的出關（位置就是行為，留在原位叫委派）",
    ("sync", "_ambush_expire"): "drop_shops 之後、_arrivals 之前：守著的埋伏到時刻了收起來（位置就是行為，留在原位叫委派）",
    ("_arrivals", "_ambush_check"): "每換一段才查一次這一段路上有沒有敵對的伏兵（迴圈中途，位置就是行為，留在原位叫委派）",
    ("_stamina_play_options", "_stamina_play_head"): "選單順序「設伏／收伏 → 屯糧 → 護衛 → 功能包的選項 → 盤算」：前半在體力玩法包，接縫留在 Game",
})


# peers（全部拆包第 37 批「玩家互動一」：新包 tianxia/features/peers/；計畫 docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md 1.4）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。31 個方法搬進包，Game 留 21 個一行委派（另加月旦評那一句 _yuedan_line，主人大勢人物包）。
# 核心原位碰這一包的：choose 的 invite: 與 _action_title 的 invite 兩處換成包的 choose 掛鉤；換季的頭銜簿換成 on_season_start 掛鉤；
# 選單的 _invite_options 位置固定（選單的順序算行為），留原位叫委派。engine 還用 invites、social（切磋、論武、結伴同行還在原位，第 38 批與移動包）。
GAME_IMPORTS |= {
    "tianxia.features.peers.actions", "tianxia.features.peers.invite_actions", "tianxia.features.peers.mingtie_actions",
    "tianxia.features.peers.pair_actions", "tianxia.features.peers.invites", "tianxia.features.peers.social",
}
GAME_DELEGATES |= {
    # 玩家卡與此地還有（server 的 /api/main 與 bot_policy 與測試叫）、邀請框（選單 _invite_options、main_view 的 _invite_status、切磋論武叫的 answer_invite 與 _tell_sender、
    # 測試叫的 _invite）、同一對人的帳（切磋、論武在原位算次數）、名帖（server 的管理者工具與測試叫）；_yuedan_line 是玩家卡問大勢人物包的月旦評那一句（包經 ctx 叫）
    "peers_here", "_peer", "peer_card", "peer_request", "peer_act", "calls_here", "_invite_options", "_invite", "answer_invite", "_tell_sender", "_invite_status",
    "gift_day_left", "_spar_pair", "_pair_left", "_pair_tick", "mingtie_view", "make_mingtie", "report_mingtie",
    "admin_mingtie_reports", "admin_mingtie_remove", "admin_mingtie_restore", "_yuedan_line",
}
_PEERS_ORDER = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）：邀請框那幾顆夾在託付與懸賞榜之間，位置固定、沒有對應的掛鉤"
_PEERS_38 = "切磋、論武（總表第 38 批）還在 Game，叫玩家互動包的{what}（經 Game 的一行委派）；搬走之後各自經 ctx 叫"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_invite_options"): _PEERS_ORDER,
    ("status_data", "_invite_status"): "江湖頁的邀請（status_data[\"invites\"]）：狀態列的資料，位置固定、鍵的順序算行為，總表第 66 批才接 status 掛鉤",
    ("_spar", "_tell_sender"): _PEERS_38.format(what="邀請沒成局的通知"),
    ("_discuss", "_tell_sender"): _PEERS_38.format(what="邀請沒成局的通知"),
    ("_join", "_tell_sender"): "結伴同行（移動包）還在 Game，叫玩家互動包的邀請沒成局的通知（經 Game 的一行委派）",
    ("_spar", "_pair_tick"): _PEERS_38.format(what="同一對人的帳"),
    ("_discuss", "_pair_tick"): _PEERS_38.format(what="同一對人的帳"),
    ("_spars_left", "_pair_left"): _PEERS_38.format(what="同一對人的帳"),
    ("discusses_left", "_pair_left"): _PEERS_38.format(what="同一對人的帳"),
    ("join_refusal", "_peer"): "結伴同行（移動包）還在 Game，問玩家互動包此地還有沒有那個人（經 Game 的一行委派）",
})
_PEERS_PENDING = "切磋、論武（總表第 38 批）還在 Game，直接用玩家互動包的 {what}；搬走之後這一條跟著拿掉"
GAME_DIRECT.update({
    "_spar_answer_problem": _PEERS_PENDING.format(what="invites、social（同一對人的上限那一句 social.pair_full、對方不在這裡 presence.GONE）"),
    "spar_invite": _PEERS_PENDING.format(what="invites（發邀請）"),
    "spar_refusal": _PEERS_PENDING.format(what="invites、social（不能發邀請的原因）"),
    "_discuss": _PEERS_PENDING.format(what="invites、social（論武的提示泡泡 social.DISCUSS_BRIEF、thing_label）"),
    "discuss_invite": _PEERS_PENDING.format(what="invites（發邀請）"),
    "discuss_invite_problem": _PEERS_PENDING.format(what="invites、social（答應時重驗）"),
    "discuss_refusal": _PEERS_PENDING.format(what="invites、social（不能發邀請的原因）"),
})


# travel（全部拆包第 47 批「移動一」；計畫 docs/superpowers/plans/2026-11-06-移動包-第1批.md 1.4）：選單的順序算行為
# （/api/main 的選項一顆一顆逐位元組：站著的時候「前往」夾在求見、招募之後、拜師之前；路上那串是折返、帶路一句、喊停、路上小事、擂台），
# 不能改成 Feature.options 登記（會排進 FEATURES 的順序），所以 Game 原位那幾行叫委派、位置不動。
_TRAVEL_MENU = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）；移動的選單不能改成 Feature.options 登記（會排進 FEATURES 的順序），原位叫委派、位置不動"
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_move_option"): _TRAVEL_MENU + "：站著的時候「前往」夾在求見、招募之後、拜師之前",
    ("_everyday_options", "_back_option"): _TRAVEL_MENU
    + "：路上那串的折返，在 act:on_road（結伴時是 act:part）之後、帶路的路上一句與喊停之前",
    ("_everyday_options", "_road_task_options"): _TRAVEL_MENU + "：路上小事在喊停之後、擂台之前（結伴同行時緊接在 act:part 後面）",
    ("_arrivals", "_road_sight"): "抵達一站的迴圈中途（_ambush_check → _arrive → 騎乘飽足 → 路上見聞）：位置固定、沒有對應的掛鉤；第 48 批 _arrivals 搬進移動包時改經 ctx",
})
GAME_IMPORTS |= {
    # travel（全部拆包第 47 批）：移動選單、路上小事、喊停、折返、安排前往的 9 個一行委派
    "tianxia.features.travel.menu", "tianxia.features.travel.road_actions", "tianxia.features.travel.go_actions",
}
GAME_DELEGATES |= {
    # travel（全部拆包第 47 批）：移動一的 9 個一行委派。_move_option、_back_option、_road_task_options 給選單（順序算行為，不能改成 Feature.options）；
    # _road_sight、_road_reward_due、_count_road_reward 給 _arrivals 與第 48 批的 _share_road；set_move_mode 給 server、腳本與測試；
    # travel、travel_refusal 給 /api/travel、假人（bot_policy._rally）、腳本與 21 個測試檔（測試也換掉 game.travel_refusal 繞過檢查）
    "_move_option", "_back_option", "_road_task_options", "set_move_mode", "_road_reward_due", "_count_road_reward", "_road_sight",
    "travel", "travel_refusal",
}
# 拿掉別人段裡的格：在自己的段 del（halt、check_hints、report_seat、hear_after_stamina 現在由包經 ctx 叫，不再是 Game 內部互叫）
del GAME_DELEGATE_CALLERS[("_halt", "_sync_battle_presence")]
del GAME_DELEGATE_CALLERS[("travel", "_check_hints")]
del GAME_DELEGATE_CALLERS[("travel", "_report_seat")]
del GAME_DELEGATE_CALLERS[("travel", "_hear_after_stamina")]


# map（全部拆包第 49 批「輿圖一」：新包 tianxia/features/map/；計畫 docs/superpowers/plans/2026-11-06-輿圖包-第1批.md 1.1、1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。11 個方法搬進包，Game 留 11 個一行委派（_map_foes、_fierce_line 也留：測試換掉 Game._map_foes、
# 包裡經 ctx 叫），另多兩個：探索包原本直接 import mapview、mapdata（open_places、mostly_here），成包之後包不能 import 包，改經 Game 的 _map_open_places、
# _map_mostly_here 問輿圖包。沒有選項前綴、沒有掛鉤可接（輿圖是只讀的畫面）、沒有 GAME_DIRECT：原本 map_state、_map_foes 兩筆（sortie.on）拿掉，
# 現在經 ctx 問出陣包的 _sortie_mode；原本 (map_base|map_state, map_mostly)、(map_state|_map_foes, _sortie_foes|duel_on|_duel_squad|sorties_left)、
# (_fierce_line, _practice_tier) 十幾對是 Game 叫委派，現在是包裡經 ctx 叫（服務清單二、查詢服務 # map），拿掉。
GAME_IMPORTS |= {"tianxia.features.map.actions"}
GAME_DELEGATES |= {
    # server 的 map_base_view（底圖）、/api/map/state（疊層）、map_view（舊輿圖的圖層、標頭、地點、詳情、移動鈕）、/api/travel 走不成時帶的 map，bot_policy
    # 的 travel_options（假人的移動選項），測試與腳本叫的；_map_foes、_fierce_line 包裡也經 ctx 叫（測試換掉 Game._map_foes）；_map_open_places、
    # _map_mostly_here 是探索包的查詢
    "map_base", "map_state", "_map_foes", "_fierce_line", "world_map_svg", "minimap_svg", "map_legend", "map_header", "map_places", "place_detail",
    "travel_options", "_map_open_places", "_map_mostly_here",
}
# 輿圖搬進包之後這些不用了（第 25 批定的寫法：用 del 集中在自己的段，不在別人的段裡刪行）：_MAP_LINE 留著不動
del GAME_DIRECT["map_state"], GAME_DIRECT["_map_foes"]  # 兩支都搬進包，經 ctx 叫
for _pair in (("map_base", "map_mostly"), ("map_state", "map_mostly"), ("map_state", "_sortie_foes"), ("map_state", "sorties_left"),
              ("_map_foes", "_sortie_foes"), ("map_state", "duel_on"), ("_map_foes", "duel_on"), ("_map_foes", "_duel_squad"),
              ("_fierce_line", "_practice_tier")):
    del GAME_DELEGATE_CALLERS[_pair]  # 包裡經 ctx 叫（Game 的委派只剩一行）


# smithy（全部拆包第 41 批「鐵匠鋪」：新包 tianxia/features/smithy/；計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.4、1.9）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。23 個方法搬進包，Game 留 12 個一行委派（其餘 11 個只有包裡叫的，沒有委派）。
# 核心原位碰這一包的：choose 的 smith: 與 _action_title 的兩處（kind == "smith" 的標題、act:smith 的表格）換成包的 choose 掛鉤與 act 子動詞（Verb）；
# 「打造那幾步併成一則」（quiet、merge、fold）留 choose 後半原位讀 smithing 的三個名字（經舊名別名）。
# 店面登記（Shop）這一批不登記（計畫 1.9 量出四條）：鐵匠鋪留在 Game 原位，只有 _smith_options 變成一行委派；第 42 批（馬市）與第 45 批（懸賞榜）比較晚合的那一批
# 把懸賞榜、鐵匠鋪、馬市三間一起排進 Shop，入口先後維持 懸賞榜 → 鐵匠鋪 → 馬市（第 41 批 PM 認定第 1 條）。
GAME_IMPORTS |= {
    "tianxia.features.smithy.shelf_actions", "tianxia.features.smithy.forge_actions", "tianxia.features.smithy.trade_actions",
    "tianxia.features.smithy.gear_actions", "tianxia.features.smithy.divine_actions", "tianxia.features.smithy.clue",
    "tianxia.smithing",  # 舊名：現在是指到包裡 smithing 的別名（核心原位讀 draft_here、draft_stale、GO_VERB 等）
}
GAME_DELEGATES |= {
    # server（MAIN_ACTIONS 的 smith_forge、smith_sell、smith_upgrade、smith_furnace，MENXIA_ACTIONS 的 repair_item、temper_item、name_divine、bind_art，
    # 包的 /api/smith_line 路由）、假人（bot.trade_at_smith、bot.keep_book_names）、測試在叫的；_smith_options 是核心原位選單叫的；
    # _smith_clue 是測試換掉的（包裡經 ctx 叫，services.py 二、查詢服務 # smithy）；_smith 是 tests/gear/test_shop2.py 直接叫的（計畫 1.1 寫沒有呼叫端，量錯了一個）
    "_smith_options", "_smith", "_smith_clue", "smith_line", "smith_forge", "smith_furnace", "smith_sell", "smith_upgrade",
    "repair_item", "temper_item", "name_divine", "bind_art",
}
_SMITHY_SHOP = ("鐵匠鋪不登記店面（計畫 1.9）：「此地還能做」的入口順序是 懸賞榜 → 鐵匠鋪 → 馬市 → 搬成包的店，搬進 Shop 就排到馬市後面（/api/main 的選項順序變）；"
                "同一排的懸賞榜（第 45 批）、馬市（第 42 批）還沒成包；`here` 有兩個意思（_shop_open 要單子沒開著，收店要 smith_open）；PM 一次排")
GAME_DELEGATE_CALLERS.update({
    ("_everyday_options", "_smith_options"): _SMITHY_SHOP,
})
_SMITHY_STALE = "鐵匠鋪的單子：{what}；核心原位讀 smithing（經舊名別名，現在是鐵匠鋪包的 smithing.py）的 {names}，{why}"
GAME_DIRECT.update({
    "choose": _SMITHY_STALE.format(what="打造那幾步併成一則、切頁不寫紀錄", names="GO_VERB、is_forge_step、is_step_line",
                                   why="位置在 choose 後半寫紀錄那一段（quiet、merge、fold 要看單子收起來了沒），沒有對應的掛鉤"),  # 過渡：第 40 批收（第 41 批 PM 認定第 4 條）
    "_drop_stale_references": _SMITHY_STALE.format(what="鐵匠鋪關了、人不在城鎮就收起，單子那一欄關了、內容改版拿掉了種類或素材就清", names="draft_here、draft_stale",
                                                   why="順序夾在懸賞榜與馬市中間（計畫 1.9），on_drop_stale 掛鉤在最後面，位置不同不能接"),  # 過渡：第 40 批收（第 41 批 PM 認定第 4 條）
    "sync": _SMITHY_STALE.format(what="同步時單子那一欄關了就清", names="draft_here",
                                 why="位置固定在 sync 的中段，沒有對應的掛鉤（world 的 sync 順序算行為）"),  # 過渡：第 40 批收（第 41 批 PM 認定第 4 條）
})


# faction（全部拆包第 35 批「陣營」：新包 tianxia/features/faction/；計畫 docs/superpowers/plans/2026-11-06-陣營包-第1批.md 1.1、1.4、1.5）：
# 這一批加的集中在這一段（並行的拆包線不跟別人的行穿插）。20 個方法搬進包，Game 留 13 個一行委派（_season_grant、_sect_options、_lean_options、_lean_anytime、
# _join_lean、_faction_prompt、_four_wins、ending_card、tier_hint、sides_card，加三個新的：_faction_pending_options〔選單接管整個選單的待確認三段〕、
# _defect_options〔選單的叛投迴圈〕、_defect_scene〔叛投確認畫面的場景〕；_ally_options、_left_names 沒有原位的呼叫端、不留）。
# 核心原位碰這一包的：choose 的 faction／defect／sect 與 _action_title 的 faction／defect 換成包的 choose 掛鉤；叛投的 clear progress 與 after leave_behind
# 兩格換成包登記的叛投格（DEFECT_ORDER 不動）；選單的位置固定（選單的順序算行為），留原位叫委派。
GAME_IMPORTS |= {
    "tianxia.features.faction.join_actions", "tianxia.features.faction.lean_actions", "tianxia.features.faction.defect_actions",
    "tianxia.features.faction.ending_actions",
}
GAME_DELEGATES |= {
    "_season_grant", "_sect_options", "_lean_options", "_lean_anytime", "_join_lean", "_faction_prompt", "_faction_pending_options", "_defect_options",
    "_defect_scene", "_four_wins", "ending_card", "tier_hint", "sides_card",
}
_FACTION_ORDER = "選單的順序算行為（/api/main 的選項一顆一顆逐位元組）：{what}，位置固定、沒有對應的掛鉤（選單照包排是總表第 55～57 批）"
GAME_DELEGATE_CALLERS.update({
    ("_reset_player_for_new_season", "_season_grant"): "換季開場、_write 之後發上一季論功的起手資源與稱號：位置固定、沒有掛鉤（on_season_start 在 _write 之前）",
    ("_everyday_options", "_faction_pending_options"): _FACTION_ORDER.format(what="待確認的三段接管整個選單，夾在談著與求見之間；`menu` 掛鉤坐的位置更前面（sense_menu、一條線答題之前）"),
    ("_everyday_options", "_sect_options"): _FACTION_ORDER.format(what="拜入門派那一顆夾在交友與求見的那一顆之間"),
    ("_everyday_options", "_defect_options"): _FACTION_ORDER.format(what="叛投夾在投靠與改幫之間"),
    ("_everyday_options", "_lean_options"): _FACTION_ORDER.format(what="改幫接在叛投之後、軍令之前"),
    ("choose", "_lean_anytime"): "「改幫…」不在選單上時照樣收（在路上、決戰的大區，設計 3.2）：要先查選單、查不到才問它，choose 掛鉤在查選單之後，位置不對",
    ("choose", "_join_lean"): "投靠或拜入陣營名下的門派那一下，動作之後、入伍段之前給傾向：位置固定、動作之後的收尾沒有對應的掛鉤",
    ("_own_scene_text", "_faction_prompt"): "場景那一段的順序算行為（談著、選邊、投靠、叛投確認、求見…）：位置固定，場景的掛鉤是第 55～57 批",
    ("_own_scene_text", "_defect_scene"): "同上（叛投確認畫面的場景）",
    ("season_result", "ending_card"): "收季之後的結局卡接在 season_result 的 out 後面（欄位表 main.ending）：資料的鍵序算行為，沒有對應的掛鉤",
})
# 理由字換了（別人那一段的原文不改）：陣營成包之後，這一筆留的理由是「choose 掛鉤要的是動作之前的陣營」，不再是「陣營還沒成包」
GAME_DELEGATE_CALLERS[("choose", "_begin_enlistment")] = (
    "這一下才投靠（或拜入陣營名下的門派）的人開始入伍段：陣營成包（第 35 批）之後，投靠那一步在包裡，入伍段屬引導包；要知道動作之前的陣營，"
    "位置固定在 choose 掛鉤之後")
for _pair in (("_faction_step", "_ally_follows_battle"), ("_join_lean", "_ally_follows_battle"), ("_lean_step", "_ally_follows_battle"),
              ("_faction_step", "_note_action"), ("_defect_step", "_battle_now"), ("_defect_targets", "_battle_now")):
    del GAME_DELEGATE_CALLERS[_pair]  # 陣營成包：呼叫端搬進包，包裡經 ctx 叫（services.py 的 # faction 一段）；原文不改，同第 8、25、32 批 del 的寫法


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


# shared（全部拆包第 15 批「共用規則層登記」，計畫 docs/superpowers/plans/2026-11-01-共用規則層登記.md 1.3、2.2）
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


SHARED_PENDING = {
    ("timetable", "figures"): "排定：大勢人物（figures.apply、commander、holds、is_out、name_of、state_of）——總表第 40 批收進共用規則層",
    ("timetable", "chapters"): "排定：章回的擲骰修正（chapters.roll_mod，函式裡）——第 40 批收進共用規則層",
    ("seats", "ranks"): "排定：階級的稱號（ranks.TITLES，函式裡）——第 40 批收進共用規則層",
    ("conquest", "seal_acts"): "排定：璽效查詢（seal_acts.held、ends、held_during、hold_lapse）——第 51 批 16 個璽效查詢進共用規則層",
    ("siege", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層。atlas 最外層 import 出陣包"
                        "（舊名 sortie；函式裡還有 sortie_duel），也經 world 帶進宴客包 feast、單挑包 bout（第 12 批）：切開之前 import siege 會連帶載入"
                        " sortie、feast、bout 三包",
    ("clinic", "atlas"): "排定：最近的醫館（atlas.routes、shortest_routes、Route）——同上，第 50 批；切開之前 import clinic 同樣經 atlas"
                         "連帶載入出陣包 sortie、宴客包 feast、單挑包 bout",
    ("siege", "conquest_day"): "排定：作罷（conquest_day.void、note_void）——第 46 批 Task 1 先搬進 conquest",
    ("siege", "world"): "排定：開集結那一季（world._season_vehicle，函式裡）——第 25 批 world 收進核心本體。world 最外層 import 宴客包 feast"
                        "與單挑包 bout（舊名 arena：收季記擂台前三名的 close_season，全部拆包第 12 批成包）："
                        "叫到那個函式就連帶載入 feast、bout（現在 import siege 已經經 atlas 載進來了），收進核心本體之前那一行要先處理（核心不 import 包）",
    ("siege", "generals"): "之後成包：攻城的留守挑龍頭（generals.on、pick）——決戰第 8 批 generals 進包之前，先改成查詢服務或把挑法留在共用規則層"
                           "（siege 第 11 批就登記了）",
}
# battle（全部拆包第 8 批）：generals 進了決戰包（舊名 tianxia/generals.py 是別名），siege 讀的挑法（on、pick）留在共用規則層的 chiefs
# （registry.SHARED）——siege → generals 那一條收掉；chiefs 照原本 generals 那樣 import 大區與大勢人物，多兩條排定的（同 siege → atlas、
# timetable → figures）；world 函式裡 import 舊名 generals（開集結那一下派龍頭上陣），叫到它就連帶載入決戰包
del SHARED_PENDING[("siege", "generals")]
SHARED_PENDING.update({
    ("chiefs", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層。atlas 最外層 import 出陣包"
                         "（舊名 sortie；函式裡還有 sortie_duel），也經 world 帶進宴客包 feast、單挑包 bout（第 12 批；world 函式裡另有舊名 generals，"
                         "叫到才載入決戰包 battle）：切開之前 import chiefs 會連帶載入 sortie、feast、bout 三包（第 12 批合進 develop 時量的）",
    ("chiefs", "figures"): "排定：大勢人物（figures.state_of、line_of）——總表第 40 批收進共用規則層",
})
# story（全部拆包第 30 批：storyline 拆兩半，底座與換字進共用規則層的 story_base；計畫 docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md 1.2）：
# 照原本 storyline 那樣讀大區（here）與章回的大事結果（vary，函式裡），多兩條排定的
SHARED_PENDING.update({
    ("story_base", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層（同 chiefs → atlas：atlas 最外層 import "
                             "出陣包 sortie，也經 world 帶進宴客包 feast、單挑包 bout）：切開之前 import story_base 會連帶載入 sortie（原本 import storyline 就是這樣）",
    ("story_base", "chapters"): "排定：章回的大事結果（chapters.outcome_mark，vary 函式裡延後 import）——第 40 批收進共用規則層"
                                "；章回自己 import 舊名 storyline（一條線包 story 的別名），叫到才連帶載入 story",
})
# chapters 載入時 import 舊名 storyline（章回登記 TASKS，storyline.active、start 這些）：第 30 批 storyline 成了一條線包 story 的別名，
# 所以另外兩條指到 chapters 的排定項（timetable 的擲骰修正）叫到它也連帶載入 story
SHARED_PENDING[("timetable", "chapters")] += "；章回自己 import 舊名 storyline（一條線包 story 的別名），叫到才連帶載入 story（第 30 批）"
SHARED_PENDING[("siege", "world")] += "；world 函式裡也 import 舊名 generals（決戰包 battle 的別名：開集結那一下派龍頭上陣），叫到它就連帶載入 battle"

# 總表第 15 列寫了、這一批先不收的（派工：import 了包的「先改成查詢服務，或者先不收」；讀的都是還沒成包的舊模組，還沒有包可以回答查詢）：
# 模組 → 卡在哪、哪一批之後收。包 import 它們的那幾行照舊註「過渡：待搬」。
SHARED_LATER = {
    "fusion": "讀有所感的自創（sensing.add_own、own_name：有所感第 24 批成包）（第 24 批 PM 認定第 3 條；行狀 annals.note 那一半第 29 批之二收進核心 core/annal_base.py，fusion 改 import 它，不算了）",
    "skillview": "門下頁的說明（彙整）：讀自創 create（第 44 批）、修練 cultivation（第 23 批）、玉璽 seal（第 27 批）、鐵匠鋪 smithing（第 41 批已成包，經舊名別名）、"
                 "輿圖 atlas；那幾包成包、改成查詢服務之後再收",
    "shopview": "店面的畫面資料（彙整）：讀擂台 arena（第 12 批）、懸賞 bounties（第 45 批）、鐵匠鋪 smithing（第 41 批已成包，經舊名別名）、單挑 duel 的底層；"
                "那幾包成包之後再收",
    "events": "事件抽選：讀伏筆 foreshadow（軍情第 34 批成包）與心意 stances（第 19 批）；伏筆改成查詢服務、事件檢定搬進核心（第 16 批）之後再看",
    "tiers": "事件分級：讀擂台的名次 arena.entry_of，經舊名 arena（單挑包的別名）：名次已經是核心的查詢服務 arena_ranks（第 12 批），"
             "可是 tests/core/test_event_tiers.py 換掉 tianxia.arena.entry_of，改讀核心之後那一條打不到；那一條改成換掉核心那一份"
             "（改核心測試，PM 定）之後再收",
    "narration": "事件旁白每週改寫：讀伏筆 foreshadow.event_ids（軍情第 34 批）；那時改成查詢服務再收",
    "leaderboard": "賽季榜單：讀本命兵器 signature_arms（裝備第 42 批）與門下頁的說明 skillview（函式裡）；擂台榜第 12 批審查修正改讀核心的"
                   "查詢服務 arena_ranks；裝備成包、skillview 收進來之後再收",
    "rumor_view": "傳聞分層的畫面：讀伏筆 foreshadow、機緣 opportunities（軍情第 34 批）與軍令 orders（第 40 批）；軍情成包時改成查詢服務再收",
}


# companions（全部拆包第 19 批；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md 1.2、1.6）：stances 的世界那一半進了共用規則層 stance_world。
# 事件抽選 events 讀的也是世界那一半（不再碰包）：理由改成只剩伏筆
SHARED_PENDING[("stance_world", "figures")] = "排定：大勢人物（figures.state_of，函式裡，持重拉進度找他在哪條線）——總表第 40 批收進共用規則層"
SHARED_LATER["events"] = "事件抽選：讀伏筆 foreshadow（軍情第 34 批成包）；伏筆改成查詢服務之後再看（心意第 19 批換成共用規則層 stance_world）"
# figure_acts（全部拆包第 31 批）
# 月旦評 A、C 兩段與盤算、管理者救回人物的 Game 方法只被 server 叫，不是 Game 裡的呼叫端；figures.py 函式裡 import 舊名 figure_aid（犒軍與自然回復共用一天的上限）：
# 叫到才連帶載入 figure_acts，兩條指到 figures 的排定項補一句
for _key in SHARED_PENDING:
    if _key[1] == "figures":
        SHARED_PENDING[_key] += "；figures 函式裡也 import 舊名 figure_aid（大勢人物的行動包 figure_acts 的別名：犒軍與自然回復共用一天的上限），叫到它就連帶載入 figure_acts（第 31 批）"
    elif _key[1] == "world":
        SHARED_PENDING[_key] += "；world 最外層 import 舊名 yuedan（figure_acts 的別名：每一步叫 yuedan.tick），import 它就連帶載入 figure_acts（第 31 批）"
# core_world（全部拆包第 25 批「世界層掛鉤」；計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md 1.6）：world 改成世界層掛鉤、收進核心本體
# （MODULES），不再 import 宴客包、單挑包與舊名 yuedan、generals——siege → world 那一條（含第 30 批補的龍頭上陣、第 31 批補的月旦評兩句）拿掉，
# atlas 的四條（siege、clinic、chiefs、story_base）「也經 world 帶進宴客包、單挑包」那半句改寫。都寫在這一段、上面別批的行照原樣
# （同第 8 批 del、第 19 批覆寫的寫法）。world 自己 import 的舊模組（bounties、figure_life……，行尾標批號）跟 journal 一樣是
# 核心 → 舊模組，這一版不掃。
del SHARED_PENDING[("siege", "world")]
SHARED_PENDING.update({
    ("siege", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層。atlas 最外層 import 出陣包"
                        "（舊名 sortie；函式裡還有 sortie_duel）：切開之前 import siege 會連帶載入 sortie（以前也經 world 帶進宴客包、單挑包，"
                        "第 25 批 world 收進核心本體之後不再 import 包）",
    ("clinic", "atlas"): "排定：最近的醫館（atlas.routes、shortest_routes、Route）——同上，第 50 批；切開之前 import clinic 同樣經 atlas"
                         "連帶載入出陣包 sortie",
    ("chiefs", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層。atlas 最外層 import 出陣包"
                         "（舊名 sortie；函式裡還有 sortie_duel）：切開之前 import chiefs 會連帶載入 sortie（第 25 批 world 收進核心本體之後量的；"
                         "以前也經 world 帶進宴客包 feast、單挑包 bout）",
    ("story_base", "atlas"): "排定：大區（atlas.region_of）——第 50 批 atlas 的地點、大區、路線那一半留在共用規則層（同 chiefs → atlas：atlas 最外層 import "
                             "出陣包 sortie）：切開之前 import story_base 會連帶載入 sortie（原本 import storyline 就是這樣）",
})

# territory_acts（第 46 批）：地盤搬成包之後這四筆不用了（第 25 批定的寫法：用 del 集中在自己的段，不在別人的段裡刪行）
for _pair in (("_siege_live", "_sieges"), ("admin_conquest_cancel", "_cancel_siege"), ("_siege_live", "_joinable")):
    del GAME_DELEGATE_CALLERS[_pair]  # 地盤畫面、救場工具改叫決戰包的查詢服務（ctx._joinable、ctx._cancel_siege、ctx._sieges）
del SHARED_PENDING[("siege", "conquest_day")]  # 作罷（void、note_void）第 46 批 Task 1 已搬進 conquest


def test_the_shared_rules_layer_only_imports_the_core_and_itself():
    """共用規則層只 import 核心本體與同一層（總表第六節第 5 條）：碰到別的舊模組的就是 SHARED_PENDING 那幾條，多一條、少一條都紅
    （新碰到的要寫理由、收掉的要拿掉）；對象沒有一個是核心本體、同一層或別名，理由開頭寫是哪一種。"""
    assert shared_reach() == set(SHARED_PENDING)
    for (name, old), why in SHARED_PENDING.items():
        assert name in SHARED and old not in SHARED and old not in CORE and old not in aliases(), (name, old)
        assert why.startswith(("排定：", "之後成包：")), (name, old)


def test_a_pending_target_that_imports_a_package_says_it_drags_the_package_in():
    """SHARED_PENDING 的對象自己 import 了包的（atlas 經舊名 sortie import 出陣包）：import 那個共用規則層的模組，
    包就跟著載進來（import clinic、siege、chiefs〔第 8 批〕、story_base〔第 30 批〕實際載入出陣包；以前還經 world 載入宴客、單挑兩包，
    第 25 批 world 收進核心本體、不再 import 包之後只剩出陣包；其餘一包都不載）。上面那幾條只看共用規則層自己的 import，
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
    assert outside_imports("from . import figures, territory\n", m) == {"figures"}
    assert outside_imports("def f():\n    from .seal import mandate_event\n", m) == {"seal"}  # 第 25 批：原本的例子 world 收進了核心本體
    assert outside_imports("def f():\n    from .world import _season_vehicle\n", m) == set()
    assert outside_imports("import tianxia.engine\n", m) == {"engine"}
    assert outside_imports("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .engine import Game\n", m) == set()
    assert outside_imports("from .core import features\nfrom .models import Content\nfrom tianxia import calendar, siege\n", m) == set()
    assert outside_imports("from tianxia import TYPE_NAME_NOT_A_MODULE\nimport json\nfrom pydantic import BaseModel\n", m) == set()
    assert outside_imports("from .features.battle import rules\nfrom . import feasts\n", m) == set()


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


# core-events（全部拆包第 16 批「事件檢定進核心」，計畫 docs/superpowers/plans/2026-11-01-事件檢定進核心.md）：事件檢定的本體從 Game 搬進
# 核心本體 tianxia/core/event_check.py。以前那幾個方法在 Game 上，叫包的委派會被 game_links 記成 GAME_DELEGATE_CALLERS；搬進 tianxia/core/
# 之後 game_links（只掃 engine.py）看不到，所以這裡補兩條：核心模組經 ctx 叫的不准是包的委派；Game 上叫 event_check 的只有那幾個一行的委派。
CORE_EVENT_DELEGATES = {  # Game 上本體只有一行 `return event_check.<名>(self, …)` 的方法：server、假人、測試、探索包與 Game 原位在叫的 15 個
    # （只有 event_check 自己叫的 _answer_branch、_deed_credit 不留委派）
    "_present", "_event_text", "event_tier", "event_option_view", "_choice_label",  # 事件卡
    "_choose", "_tale_clue", "_event_battle", "_apply",  # 固定選項
    "_free_text_of", "_branches", "event_free_text_prompt", "free_text_request", "answer_event", "add_gamble_narration",  # 隨口應對
}


# 核心模組經 ctx 叫包的委派（過渡；同 GAME_DELEGATE_CALLERS 的格式與規矩：(模組.函式, 委派) → 為什麼留、哪一批收）。dev/core-events-1 審查補的：
# 搬進 tianxia/core/ 之前，這些呼叫在 Game 上，主人搬成包、留下委派的那一批照批次表第二節記進 GAME_DELEGATE_CALLERS；搬進核心之後記這裡。
# 現在是空的：event_check 經 ctx 叫的 Game 方法都還不是包的委派。總表（final_owner.json）把其中 8 個歸給包，那一包搬的批把它換成委派時
# 這條守門會紅——照下面取消註解、附上理由（或照第 11 批開掛鉤、拿掉那一處），不要拿掉守門：
#   ("event_check.event_tier", "_battle_for_me")：features/battle（決戰「打」，第 8 批）：全服戰鬥蓋著場景時不寫分級那一行（第 8 批接上了，見下面）
#   ("event_check.answer_event", "_begin_enlistment")、("event_check.answer_event", "_greet_rejoin")、
#   ("event_check.answer_event", "_check_hints")：features/guide（新手引導）：隨口應對的結果也可能拜入門派、碰到新玩法
#   ("event_check.answer_event", "_general_gifts")、("event_check.answer_event", "_signature_arms")、
#   ("event_check.answer_event", "_gift_entry")：features/gear：效果加了情誼，另起一則贈禮
#   ("event_check.answer_event", "_report_seat")：features/orders：效果推了大勢、記了貢獻，第四階席次的帳也抄
#   answer_branch 叫同樣那 7 個（一共 15 對）。
# import 那一向沒有名單：event_check 第 37 行 import 的 bounties（總表歸 features/bounties）、foreshadow（歸 features/orders）成包、
# 舊名留成別名時，test_the_core_never_imports_a_feature_package_except_the_registry 會抓到（核心只准 engine.py 的 GAME_IMPORTS）；
# 那一批交 PM 定：開一張核心的 import 名單，或那一包開查詢服務、event_check 改經 ctx 叫。
CORE_DELEGATE_CALLERS: dict[tuple[str, str], str] = {}
# guide（全部拆包第 22 批）：上面註解裡寫好的 features/guide 那 6 對（answer_event、answer_branch × _begin_enlistment、_greet_rejoin、_check_hints）
# 新手引導搬成包、它們成了委派，照註解記進來（理由在 # guide 那一段的 CORE_DELEGATE_CALLERS_GUIDE）
CORE_DELEGATE_CALLERS.update(CORE_DELEGATE_CALLERS_GUIDE)
# sense（全部拆包第 24 批）：核心的裝飾器 outing_watch 經 ctx 叫探索包的委派（理由在 # sense 那一段的 CORE_DELEGATE_CALLERS_SENSE）
CORE_DELEGATE_CALLERS.update(CORE_DELEGATE_CALLERS_SENSE)
# battle（全部拆包第 8 批）：_battle_for_me 換成決戰包的委派，上面預留的第一條接上（寫理由）
CORE_DELEGATE_CALLERS.update({
    ("event_check.event_tier", "_battle_for_me"): "事件分級那一行：全服戰鬥蓋著場景時不寫（tick=False）；事件檢定是核心本體、決戰包回答「此刻蓋著的那一場」，"
                                                  "位置固定、沒有對應的掛鉤（總表第 55～57 批再看要不要改成查詢服務的掛鉤）",
})
# military（全部拆包第 33 批）：上面預留的 features/orders 那一對（answer_event、answer_branch × _report_seat）接上
CORE_DELEGATE_CALLERS.update({
    ("event_check.answer_event", "_report_seat"): "隨口應對的結果也可能推大勢、記貢獻：第四階席次的帳在這裡也抄（正式版丁）；事件檢定是核心本體、席次抄帳在軍情包，位置固定、沒有對應的掛鉤",
    ("event_check.answer_branch", "_report_seat"): "同上（隨口應對的分岔那一支）",
})
# military（全部拆包第 34 批）：事件檢定（核心）經 ctx 叫軍情包的委派——事件卡寫完、接在後面的伏筆片段（核心不 import 包）
CORE_DELEGATE_CALLERS.update({
    ("event_check.present", "_hear_from_event"): "事件觸發時聽到的伏筆片段（計畫 T7）：接在事件卡的後面，事件檢定是核心本體、伏筆在軍情包，位置固定、沒有對應的掛鉤",
})


def ctx_delegate_callers(source: str, name: str, delegates: set[str] | None = None) -> set[tuple[str, str]]:
    """核心模組（source 是原文、name 是模組名，例 event_check）經 ctx.<名> 叫的、而且是包的委派（預設 GAME_DELEGATES）的
    (模組.函式, 委派)；函式以外的記成 (模組, 委派)。巢狀的函式算在最外層那一個。"""
    delegates = GAME_DELEGATES if delegates is None else delegates
    out: set[tuple[str, str]] = set()
    for top in ast.parse(source).body:
        where = f"{name}.{top.name}" if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else name
        out |= {(where, node.attr) for node in ast.walk(top)
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ctx" and node.attr in delegates}
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


# 被測試換掉的 Game 方法（手冊第十五節「換掉的才打得到」）：event_check 裡叫它們一律經 ctx，不直接叫模組裡的本體。
# 模組裡的函式 → Game 上的委派、誰換掉它
EVENT_CHECK_VIA_CTX = {
    "present": ("_present", "tests/bots/test_event_rotation.py 換掉 Game._present：只有端出事件那一下記輪替"),
    "apply": ("_apply", "tests/figures/test_seats.py 換掉 Game._apply：效果裡記的貢獻要排在抄帳之前"),
    "free_text_request": ("free_text_request", "tests/server/test_server.py 換掉 Game.free_text_request：暫停中不問引擎"),
}


def test_the_event_check_calls_the_patched_game_methods_through_ctx():
    tree = ast.parse((TIANXIA / "core" / "event_check.py").read_text(encoding="utf-8"))
    direct = sorted(f"{node.lineno} {node.func.id}" for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in EVENT_CHECK_VIA_CTX)
    assert direct == []
    via = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ctx"}
    assert {name for name, _ in EVENT_CHECK_VIA_CTX.values()} <= via
    assert {name for name, _ in EVENT_CHECK_VIA_CTX.values()} <= CORE_EVENT_DELEGATES


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
    ("from tianxia import bounties\n", "舊模組"),  # shared：原本的例子 library 第 15 批登記進共用規則層，換一個還是舊模組的
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
                         # battle（全部拆包第 7 批：tianxia/escorts.py；第 8 批：tianxia/generals.py）
                         "escorts": "battle", "generals": "battle",
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
                         # map（全部拆包第 49 批：tianxia/mapview.py、mapart.py、mapdata.py、worldgeo.py）
                         "mapview": "map", "mapart": "map", "mapdata": "map", "worldgeo": "map",
                         # smithy（全部拆包第 41 批：tianxia/smithing.py）
                         "smithing": "smithy",
                         # faction（全部拆包第 35 批：tianxia/defection.py）
                         "defection": "faction"}
    assert not [e for e in transitional_imports() if e.rsplit(" ", 1)[1].split(".")[1] in aliases()]


def test_a_mark_with_no_old_module_left_is_caught():
    """註了過渡、import 的卻都是核心本體或共用規則層（搬完了、登記了）：那一行的註要拿掉；同一行還有一個舊模組的照註（第 11 批）。"""
    assert stale_marks("from tianxia import siege  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    assert stale_marks("from tianxia import journal, team  # 過渡：待搬\n", "tianxia.features.battle.view") == [1]
    # shared：原本的例子 conquest 第 15 批登記進共用規則層，換一個還是舊模組的
    assert stale_marks("from tianxia import bounties, siege  # 過渡：待搬\n", "tianxia.features.battle.view") == []
    assert stale_marks("from tianxia import siege\n", "tianxia.features.battle.view") == []


@pytest.mark.parametrize("source", [
    "from tianxia import bounties  # 過渡：待搬\n",  # shared：原本的例子 library 第 15 批登記進共用規則層
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


# core_world（全部拆包第 25 批「世界層掛鉤」；計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md 1.6、Task 4）
def test_the_world_layer_core_files_import_no_package_not_even_inside_a_function():
    """world.py 收進核心本體（MODULES）之後跟 sqlite_world.py 一樣：最外層與函式裡都不 import 包與舊名的別名（宴客 feasts、單挑 arena、
    大勢人物 yuedan、決戰 generals 換成了世界層的格）。掃描照 ast.walk 看得到函式裡的 import（下面那一段證明），所以核心那一條
    （test_the_core_never_imports_a_feature_package_except_the_registry）照 CORE 掃到它們；這裡寫明兩個檔，免得 MODULES 改了沒人發現。"""
    assert {"world", "sqlite_world"} <= CORE
    for name in ("world", "sqlite_world"):
        assert _feature_imports(TIANXIA / f"{name}.py") == [], name
    source = "def f():\n    from . import generals\n    from .features.feast import rules as feasts\n    from . import arena, yuedan\n"
    assert {feature_target(mod) for _, mod, _ in imports_of(source, "tianxia.world")} - {None} == {"battle", "feast", "bout", "figure_acts"}


# core_effects（全部拆包第 32 批「效果與叛投掛鉤」；計畫 docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md 1.7）：叛投之後的食言
# 改由人物情誼包登記叛投 after 位置的 parley 那一格（DEFECT_ORDER），Game._defect_step 不再叫委派 _parley_forsake、委派沒人叫了拿掉。
# 第 20 批那兩行原文不改（同第 8 批 del、第 25 批的寫法）
GAME_DELEGATES -= {"_parley_forsake"}
del GAME_DELEGATE_CALLERS[("_defect_step", "_parley_forsake")]

# 效果那幾格與叛投清進度不碰包認領的欄位（計畫 1.7）：rules.apply_effect 與它的格（_fx_*、核心代叫表 _EFFECT_CORE）、defection 的清進度
# （clear_progress、_clear_own、defect 與代叫表）——屬性名不准是任何一包 player_fields 裡的名字。包的欄位由那一包登記的格寫（一條線的 storylines、
# keepsakes；軍情的 convoy；新手引導的 hint_queue），核心照表叫。defection.prompt（確認畫面讀 convoy）是讀不是清，不在這一條（計畫 1.10）。
EFFECT_DEFECT_SCAN = {
    "rules": ("apply_effect", "_fx_", "_EFFECT_CORE"),
    "defection": ("clear_progress", "_clear_own", "defect", "_CLEAR_CORE", "_LEAVE_CORE", "_STRANDED_CORE"),
}


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


# core_eventbus（全部拆包第 26 批「事件機制」；計畫 docs/superpowers/plans/2026-11-06-事件機制-第26批.md 1.4、1.7）：抵達那一刻的交糧車
# 改由軍情包登記事件 arrive 的 convoy 那一格（BUS_ORDER），Game._arrive 不再叫委派 _convoy_arrives、委派沒人叫了拿掉。第 33 批那兩行原文不改
# （同第 8、25、32 批 del、-= 的寫法）。原位標「過渡：第 26 批」的四處與同一段寫「總表第 26 批的事件」的軍情兩格量過都留原位（計畫 1.4），理由字覆寫在這裡。
GAME_DELEGATES -= {"_convoy_arrives"}
del GAME_DELEGATE_CALLERS[("_arrive", "_convoy_arrives")]
GAME_DIRECT.update({
    "_squad_encounter": "戰鬥（as_sortie 那一支）打贏之後出陣包給獎勵、約戰開著的季不推進度（那兩對記在 GAME_DELEGATE_CALLERS）：留原位"
                        "（第 26 批量過：獎勵是出陣包與核心二選一、接在 msgs 最前面不進 extra；約戰開著與否是查詢；都不在懸賞那一個發布點上，"
                        "原位行尾標「# 留原位：第 26 批」）。序章那一場的戰報標題寫雪恥（sortie.on、PROLOGUE_FIGHT）留在這裡（第 17 批）：戰報在"
                        "這個單打服務裡建、裡面就存檔，序章裡誰打都照寫（不只 act:train），出陣包從外面改不到；要拿掉得在單打服務開一個「這一場"
                        "戰報叫什麼」的位置，交 PM 定",
})
GAME_DELEGATE_CALLERS.update({
    ("_squad_encounter", "_sortie_rewards"): "戰鬥（as_sortie）打贏之後給出陣的獎勵：留原位（第 26 批量過：出陣包與核心二選一、接在 msgs 最前面"
                                             "不進 extra，不在懸賞那一個發布點上；原位行尾標「# 留原位：第 26 批」）",
    ("_squad_encounter", "duel_on"): "戰鬥（as_sortie）打贏之後：約戰開著時只剩截糧、不推進度（進度只在約戰結算動）：留原位（第 26 批量過："
                                     "約戰開著與否是查詢，決定記功與推進度走哪一支，不是事件；原位行尾標「# 留原位：第 26 批」）",
    ("_squad_encounter", "train_trend_push"): "戰鬥（不是出陣的那一支）打贏之後遊歷推大勢：留原位（第 26 批量過：推大勢夾在記功、地盤進度之前，"
                                              "結果交給 push_trend，不在發布點上；原位行尾標「# 留原位：第 26 批」）",
    ("_seize", "_seize_chance"): "核心的單打服務收尾擲絕學的契機：留原位（第 26 批量過：在單打服務收尾、三處叫、野怪與僵持也算，不是懸賞那一下，"
                                 "回傳還要寫進戰報；原位行尾標「# 留原位：第 26 批」）",
    ("_squad_encounter", "_fs_after_win"): "遊歷打贏之後擲官銀：留原位（第 26 批量過：夾在軍令記功前後、懸賞那一個發布點之前，只在單打服務這一處有，"
                                           "收進事件 win 兩個發布點的訂閱者就不一樣）",
    ("_squad_encounter", "_opp_on_win"): "遊歷打贏之後記密謀一處（三路並進）：夾在軍令記功與懸賞討伐之間，留原位（第 26 批量過：同上）",
})

# 發布點之外不直接叫事件的訂閱者（計畫 1.7、Task 4）：懸賞的四種交差（bounties.on_win／on_explore／on_arrive／on_raid_win）、玉璽的撿碎片與收場
# （_seal_find、_seal_settle）、交糧車（_convoy_arrives，已拿掉），在 engine.py 與每一包的 .py（測試除外）只准出現在核心代叫表 engine._BUS_CORE 裡；
# 別處要聽，登記事件的格（Feature.bus()），先後照核心的 BUS_ORDER。bounties.on_aid（人物託付交差）不在總表的四種裡，不管（交 PM）。
BUS_SUBSCRIBERS = {("bounties", "on_win"), ("bounties", "on_explore"), ("bounties", "on_arrive"), ("bounties", "on_raid_win")}
BUS_METHODS = {"_seal_find", "_seal_settle", "_convoy_arrives"}


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
    files = [TIANXIA / "engine.py"] + [path for name in _packages() for path in _package_files(name)]
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
    assert bus_bypasses(old) == [2, 4, 4, 6, 8, 8, 10]


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
