"""第二輪第 103 批的改名工具：把別名與三個測試殼的 import 換成真位置（計畫 2026-11-07-第二輪-第103批.md 第三、四節）。

表凍在這個檔裡（別名與殼刪掉之後就讀不到了），可以重跑：改過的不再改。**同波別條線合進來之後新加的舊名 import，PM 在工作樹根目錄再跑一次就好**：

    python docs/superpowers/plans/2026-11-07-第二輪-第103批-改名工具.py run          # 別名與殼一起改
    python docs/superpowers/plans/2026-11-07-第二輪-第103批-改名工具.py alias        # 只改別名
    python docs/superpowers/plans/2026-11-07-第二輪-第103批-改名工具.py shell        # 只改殼
    python docs/superpowers/plans/2026-11-07-第二輪-第103批-改名工具.py check <基準>  # 跟基準那一筆比語法樹與 import 序列（只讀）
    python docs/superpowers/plans/2026-11-07-第二輪-第103批-改名工具.py targets      # 新 import 指到的模組與名字都在（只讀）

規則：本地名不動（`patch.object`、`monkeypatch.setattr(seal, …)` 打的是同一個模組物件）；順序不動（一句裡混著別的名字就照原順序切段）；尾註抄到每一段；
字串裡的 import 樣本不碰。範圍 tests/、tianxia/、scripts/、根目錄的 *.py（第 106 批）；docs/ 底下的舊工具是當時的紀錄，不改。

殼不能保留本地名（一個殼拆成好幾個模組），所以 `<殼>.x` 逐名換成真位置，這個檔用到哪個才 import 哪個，接在原本那一行的位置。同檔註解、說明字裡的 `<殼>.x` 一起換。
"""
from __future__ import annotations

import ast
import collections
import importlib
import io
import pathlib
import re
import subprocess
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 舊名 → 真正的模組全名（第 102 批量到的 67 個）
ALIASES = {
    "ambush": "tianxia.features.stamina_plays.ambush_rules",
    "annals": "tianxia.features.zhuan.standing",
    "arena": "tianxia.features.bout.arena_rules",
    "arena_crowd": "tianxia.features.bout.arena_crowd",
    "ascend": "tianxia.features.cultivation.ascend",
    "battle_instance": "tianxia.features.battle.instance",
    "biography": "tianxia.features.zhuan.biography",
    "bounties": "tianxia.features.bounties.rules",
    "checkin": "tianxia.features.checkin.checkin",
    "chuangong": "tianxia.features.cultivation.chuangong",
    "companion_agent": "tianxia.features.companions.companion_agent",
    "conquest_day": "tianxia.features.territory_acts.conquest_day",
    "create": "tianxia.features.craft.create",
    "cultivation": "tianxia.features.cultivation.cultivation",
    "defection": "tianxia.features.faction.defection",
    "discuss": "tianxia.features.peers.discuss",
    "duel": "tianxia.features.bout.duel_rules",
    "enlist": "tianxia.features.guide.enlist",
    "epiphany": "tianxia.features.sense.epiphany",
    "errands": "tianxia.features.companions.errands",
    "escorts": "tianxia.features.battle.escorts",
    "explore_one": "tianxia.features.explore.explore_rules",
    "feasts": "tianxia.features.feast.rules",
    "figure_aid": "tianxia.features.figure_acts.figure_aid",
    "foreshadow": "tianxia.features.military.fs_rules",
    "generals": "tianxia.features.battle.generals",
    "glyph": "tianxia.features.sense.glyph",
    "guide": "tianxia.features.guide.rules",
    "hints": "tianxia.features.guide.hints",
    "insight_llm": "tianxia.features.sense.insight_llm",
    "invites": "tianxia.features.peers.invites",
    "letters": "tianxia.features.companions.letters",
    "mall": "tianxia.features.mall.rules",
    "mapart": "tianxia.features.map.mapart",
    "mapdata": "tianxia.features.map.mapdata",
    "mapview": "tianxia.features.map.mapview",
    "mingtie": "tianxia.features.peers.mingtie",
    "mingtie_card": "tianxia.features.peers.mingtie_card",
    "newbie": "tianxia.features.guide.newbie",
    "notices": "tianxia.features.notify.notices",
    "opening": "tianxia.features.guide.opening",
    "opportunities": "tianxia.features.military.opp_rules",
    "outing": "tianxia.features.explore.outing_rules",
    "parley": "tianxia.features.companions.parley",
    "raid": "tianxia.features.peers.raid",
    "rank_actions": "tianxia.features.military.rank_rules",
    "seal": "tianxia.features.seal.seal",
    "seal_duel": "tianxia.features.seal.duel_rules",
    "sensing": "tianxia.features.sense.sensing",
    "signature_arms": "tianxia.features.gear.signature_arms",
    "smithing": "tianxia.features.smithy.smithing",
    "social": "tianxia.features.peers.social",
    "sortie": "tianxia.features.sortie.rules",
    "sortie_duel": "tianxia.features.sortie.duel_rules",
    "spar": "tianxia.features.peers.spar",
    "stances": "tianxia.features.companions.stances",
    "storyline": "tianxia.features.story.storyline",
    "tale": "tianxia.features.tale.tale",
    "talk_log": "tianxia.features.companions.talk_log",
    "tavern": "tianxia.features.tavern.rules",
    "tavern_ask": "tianxia.features.tavern.ask",
    "wanted": "tianxia.features.bounties.wanted",
    "works": "tianxia.features.stamina_plays.works_rules",
    "worldgeo": "tianxia.features.map.worldgeo",
    "xingshi": "tianxia.features.territory_acts.xingshi",
    "yuedan": "tianxia.features.figure_acts.yuedan",
    "zhuan_end": "tianxia.features.zhuan.zhuan_end",
}

# 本地名 → (from 什麼, import 什麼)
SHELL_IMPORTS = {
    "art_cards": ("tianxia", "art_cards"),
    "art_view": ("tianxia.features.cultivation", "art_view"),
    "forge_view": ("tianxia.features.craft", "forge_view"),
    "shop_base": ("tianxia.core", "shop_base"),
    "howto_base": ("tianxia.core", "howto_base"),
    "smithy_shop": ("tianxia.features.smithy", "shop_view"),
    "bout_shop": ("tianxia.features.bout", "shop_view"),
    "outlets_shop": ("tianxia.features.outlets", "shop_view"),
    "bounties_shop": ("tianxia.features.bounties", "shop_view"),
    "gear_shop": ("tianxia.features.gear", "shop_view"),
    "guide_howto": ("tianxia.features.guide", "howto"),
    "explore_howto": ("tianxia.features.explore", "howto"),
    "sortie_howto": ("tianxia.features.sortie", "howto"),
    "socialize_howto": ("tianxia.features.socialize", "howto"),
    "stamina_plays_howto": ("tianxia.features.stamina_plays", "howto"),
    "faction_howto": ("tianxia.features.faction", "howto"),
    "territory_acts_howto": ("tianxia.features.territory_acts", "howto"),
    "figure_acts_howto": ("tianxia.features.figure_acts", "howto"),
    "cultivation_howto": ("tianxia.features.cultivation", "howto"),
    "smithy_howto": ("tianxia.features.smithy", "howto"),
    "sense_howto": ("tianxia.features.sense", "howto"),
    "outlets_howto": ("tianxia.features.outlets", "howto"),
    "mall_howto": ("tianxia.features.mall", "howto"),
}

# 殼 → 本地名 → 這個本地名底下有哪些名字（殼檔的語法樹抄來；同名的照殼檔後蓋前）
SHELLS = {
    "skillview": {
        "art_cards": "STAT_USES STAT_CHECK_NOTE tactic_line RIPE_MOVE RIPE_NOTE fifth_ring stat_uses _milestones _signed_pct STAT_NOW _stat_numbers stat_lines practice_hint fx_traits heal_note heal_button shown_art shown_gear HIGH_MORE HIGH_LONGER _stack_scope _stack_cells _high_word slot_stack_marks slot_rows _look SCORE_NOTE score_note level_bar gear_rows gen_word parent_names power_line POWER_NEXT POWER_NEXT_IS_TOP POWER_MAXED art_card",
        "forge_view": "_known_insight_recipe AGAIN_PIECE _strip_note FORGE_ONE_INSIGHT FORGE_EMPTY forge_line forge_preview FIRES FIRE_CUTS fire_of DEEPEN_KEEP _deepen_preview _compound_grand _no forge_picks",
        "art_view": "STAT_STEP stat_step rules_line ARTS_ATTRIBUTES ATTRIBUTE_ORDER attribute_line _nearest_town relearn_note art_rows melt_judge STACK_RULE TOPPED stack_hint stack_parts _force_choice _fits insight_effects insight_rows insight_note _idle_why _slotted_name bag_text _art_label member_card _art_cell roster_cards _pct boost_line _echo_part detail",
    },
    "shopview": {
        "shop_base": "SMITH_SITUATIONS MARKET_SITUATIONS BOARD_SITUATIONS DONATE_SITUATIONS DADIAN_SITUATIONS TAVERN_SITUATIONS SITUATIONS BACKS RACK_FULL problem_key REFUSALS _mark hold_for still_holds line_text ATTRIBUTE_ROWS attribute_rank TIER_NAMES",
        "smithy_shop": "FORGED_KEYS forged_key next_rule rule_line SMITH_SIGN PAGE_NAMES ARMOR_FORGE_NOTE _pct _arts _weapon_shelf _armor_shelf _worn _repair_use _temper_use _rack _held_rows _forge SHORT_CELL ONLY_ONE GO_TEXT smith_line FURNACE_OP furnace_view DIVINE_YOU divine_view smith_view trade_view UP_SHORT_HAVE UP_SHORT_DAY UP_SHORT_SEASON NOT_SOLD_NOTE SELL_EMPTY UPGRADE_HINT UPGRADE_HINT_FOUR UP_LEFT_DAY UP_LEFT_SEASON TRADE_HINT SELL_ONLY_HINT _upgrade_short _trade_hint _trade_captions BLACK_MARKET BLACK_MARKET_CAP GLOWS FITS UNFITS glow_of forged_card",
        "bout_shop": "ARENA_SIGN ARENA_LINES YIELD_ASK NO_ENTRY JOIN_NOTE NOBODY_YET WAGES_NOTE _fight_view _ring_short arena_view",
        "outlets_shop": "DONATE_SIGN DONATE_CAP DONATE_EMPTY DONATE_TIER4_ONLY DONATE_HINT DONATE_HINT_S1 dadian_view donate_view",
        "bounties_shop": "_HELD_HEAD board_key HELD_HEAD SLOT_LEFT HAVE_NOTE NO_FIT PRIZE_CHIP PRIZE_SHORT DROP_ASK _headline board_view",
        "gear_shop": "NO_HORSE STALL_WHO ABILITY_NAMES FASTER SLOWER SAME HUNGRY_NOTE BUY_TEXT FEED_TEXT WIELD_TEXT _coat _bars _speed_shown _stall market_view",
    },
    "howto": {
        "howto_base": "SOME_PLACES",
        "guide_howto": "_clock _span regen_line newbie_line pill_line stamina_lines gift_line top_up_line _count _band _tenths season_line front_rule ALLIED_RULE allied_rule stance_help SORTIE_RANGER CONQUEST_PLACES CONQUEST_FRONTS _sortie_places _pct jianfa_growth_lines fronts_help _lockable board_help quest_help war_help FameRange _effects fame_ranges _plus fame_lines _fame_sources _fame_uses RENOWN_INTRO RENOWN_FAME RENOWN_VIRTUE RENOWN_DEEDS RENOWN_TOP RENOWN_VIRTUE_FROM RENOWN_RESONANCE RENOWN_PRACTICE renown_lines season_page_lines page",
        "explore_howto": "BRANCH_WORDS explore_line OUTING_WORDS OUTING_HEAD OUTING_FOE OUTING_BOUNTY outing_line outing_lines _kind_name mix_sentence",
        "sortie_howto": "PUSH_WORD train_line SORTIE_NOTES SORTIE_LOOT SORTIE_LOOT_SILVER SORTIE_PROGRESS SORTIE_HOLD_PROGRESS SORTIE_BLOCKED SORTIE_BLOCKED_HOLD SORTIE_LEFT sortie_line sortie_loot DUEL_NOTES DUEL_LEFT duel_line duel_lines sortie_lines",
        "socialize_howto": "SEEK_NAME social_line CALL_LINE call_line day_every",
        "stamina_plays_howto": "ambush_lines",
        "faction_howto": "CONQUEST_JOIN CONQUEST_JOIN_DUEL _place_names join_lines faction_lines",
        "territory_acts_howto": "conquest_lines territory_lines",
        "figure_acts_howto": "CHALLENGE_UNTIMED CHALLENGE_SEASON21_REGEN CHALLENGE_TITLE CHALLENGE_WHO CHALLENGE_BOTH CHALLENGE_SNUB CHALLENGE_RISE CHALLENGE_DRAW _challenge_lines",
        "cultivation_howto": "pages_lines",
        "smithy_howto": "forge_lines",
        "sense_howto": "STRONG_HOWTO TERRAIN_HOWTO",
        "outlets_howto": "ECONOMY_TITLE economy_lines",
        "mall_howto": "MALL_TITLE MALL_WHERE MALL_COIN MALL_BETA MALL_CARD mall_lines",
    },
}

SHELL_NAME_TO_LOCAL = {shell: {name: local for local, names in table.items() for name in names.split()} for shell, table in SHELLS.items()}

WIDE = 160


def git_files() -> list[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "--", "tests", "tianxia", "scripts", ":(glob)*.py"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line.endswith(".py")]


def is_alias_file(rel: str) -> bool:
    return bool(re.fullmatch(r"tianxia/[^/]+\.py", rel)) and pathlib.PurePosixPath(rel).stem in (*ALIASES, *SHELLS)


def read(path: pathlib.Path) -> tuple[str, bool]:
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def write(path: pathlib.Path, text: str, crlf: bool) -> None:
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def base_module(node: ast.ImportFrom, rel: str) -> str:
    """這一句 from 的絕對模組名。"""
    if not node.level:
        return node.module or ""
    parts = rel[:-3].split("/")
    base = parts[: -node.level]
    return ".".join(base + ([node.module] if node.module else []))


def render_prefix(prefix: str, node: ast.ImportFrom, rel: str) -> str:
    """絕對模組名寫回這一句原本的寫法（相對的留相對）。"""
    if not node.level:
        return prefix
    parts = rel[:-3].split("/")
    root = ".".join(parts[: -node.level])
    assert prefix == root or prefix.startswith(root + "."), (prefix, root)
    return "." * node.level + prefix[len(root) + 1 :]


def split_target(full: str) -> tuple[str, str]:
    package, _, module = full.rpartition(".")
    return package, module


def statement_tail(lines: list[str], node: ast.stmt, rel: str, problems: list[str]) -> tuple[str, str] | None:
    """(縮排, 尾註)。這一句前面有別的東西、或多行的中間有註解，就報出來不動。"""
    first = lines[node.lineno - 1].encode("utf-8")
    last = lines[node.end_lineno - 1].encode("utf-8")
    head = first[: node.col_offset].decode("utf-8")
    if head.strip():
        problems.append(f"{rel}:{node.lineno} 這一句前面還有東西：{head.strip()}")
        return None
    tail = last[node.end_col_offset :].decode("utf-8").rstrip()
    if tail.strip() and not tail.strip().startswith("#"):
        problems.append(f"{rel}:{node.lineno} 這一句後面還有東西：{tail.strip()}")
        return None
    if node.end_lineno > node.lineno:
        opener = first.decode("utf-8")
        if "#" in opener:
            comment = opener[opener.index("#") :].rstrip()
            tail = f"  {comment}" + (tail if tail.strip() else "")
        for number in range(node.lineno, node.end_lineno - 1):
            if "#" in lines[number]:
                problems.append(f"{rel}:{number + 1} 多行 import 中間有註解，手改")
                return None
    return head, tail


def render(head: str, prefix: str, items: list[str], tail: str) -> list[str]:
    line = f"{head}from {prefix} import {', '.join(items)}"
    if len(line) <= WIDE:
        return [line + tail]
    out = [f"{head}from {prefix} import ({tail}"]
    row = f"{head}    "
    for item in items:
        piece = f"{item}, "
        if len(row) + len(piece) > WIDE:
            out.append(row.rstrip())
            row = f"{head}    "
        row += piece
    out.append(row.rstrip())
    out.append(f"{head})")
    return out


def scope_of(tree: ast.Module) -> dict[int, ast.AST]:
    """每個節點 id → 它在哪個函式（最內層），不在函式裡就是模組。"""
    scopes: dict[int, ast.AST] = {}

    def walk(node: ast.AST, scope: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            scopes[id(child)] = scope
            walk(child, child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else scope)

    walk(tree, tree)
    return scopes


def shell_uses(tree: ast.Module, shell: str, stmt_scope: ast.AST, own_scopes: set[int]) -> list[str]:
    """這個殼在這個範圍裡讀了哪些名字（有自己那一句 import 的內層函式不算）。"""
    found: list[str] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if id(child) in own_scopes and child is not stmt_scope:
                continue
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == shell:
                found.append(child.attr)
            walk(child)

    walk(stmt_scope)
    return found


def bindings(tree: ast.Module, rel: str, scopes: dict[int, ast.AST]) -> tuple[dict[tuple[int, str], str], set[str]]:
    """(範圍, 本地名) → 真模組，和這個檔裡當變數、參數用的名字。"""
    bound: dict[tuple[int, str], str] = {}
    stored: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = base_module(node, rel)
            for alias in node.names:
                bound[(id(scopes[id(node)]), alias.asname or alias.name)] = f"{base}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bound[(id(scopes[id(node)]), alias.asname)] = alias.name
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            stored.add(node.id)
        elif isinstance(node, ast.arg):
            stored.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stored.add(node.name)
    return bound, stored


SHELL_TEXT = re.compile(r"(?<![\w./\\])(" + "|".join(SHELLS) + r")\.([A-Za-z_]\w*)")


def rewrite(rel: str, text: str, do_alias: bool, do_shell: bool, problems: list[str]) -> str:
    tree = ast.parse(text)
    lines = text.split("\n")
    scopes = scope_of(tree)
    bound, stored = bindings(tree, rel, scopes)
    # 這個檔裡哪些函式有自己那一句殼的 import
    own: dict[str, set[int]] = collections.defaultdict(set)
    shells_here: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and base_module(node, rel) == "tianxia":
            for alias in node.names:
                if alias.name in SHELLS:
                    shells_here.add(alias.name)
                    if alias.asname:
                        problems.append(f"{rel}:{node.lineno} 殼有 as，手改")
                    own[alias.name].add(id(scopes[id(node)]))
    jobs: list[tuple[int, int, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) == 2 and parts[0] == "tianxia" and (parts[1] in ALIASES or parts[1] in SHELLS):
                    if not do_alias:
                        continue
                    if not alias.asname or len(node.names) > 1:
                        problems.append(f"{rel}:{node.lineno} import {alias.name} 沒有 as，手改")
                        continue
                    where = statement_tail(lines, node, rel, problems)
                    if where is None:
                        continue
                    package, module = split_target(ALIASES[parts[1]])
                    item = module if module == alias.asname else f"{module} as {alias.asname}"
                    jobs.append((node.lineno, node.end_lineno, [f"{where[0]}from {package} import {item}{where[1]}"]))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        base = base_module(node, rel)
        parts = base.split(".")
        if len(parts) == 2 and parts[0] == "tianxia" and parts[1] in SHELLS:
            problems.append(f"{rel}:{node.lineno} from 殼 import，手改")
            continue
        if len(parts) == 2 and parts[0] == "tianxia" and parts[1] in ALIASES:
            if not do_alias:
                continue
            first = lines[node.lineno - 1]
            written = ("." * node.level + (node.module or "")) if node.level else base
            target = render_prefix(ALIASES[parts[1]], node, rel)
            swapped = re.sub(rf"(\bfrom\s+){re.escape(written)}(\s+import\b)", lambda m: m.group(1) + target + m.group(2), first, count=1)
            if swapped == first:
                problems.append(f"{rel}:{node.lineno} 換不到模組名：{first.strip()}")
                continue
            jobs.append((node.lineno, node.lineno, [swapped]))
            continue
        if base != "tianxia":
            continue
        touched = any((do_alias and a.name in ALIASES) or (do_shell and a.name in SHELLS) for a in node.names)
        if not touched:
            continue
        where = statement_tail(lines, node, rel, problems)
        if where is None:
            continue
        head, tail = where
        segments: list[tuple[str, list[str]]] = []

        def add(prefix: str, item: str) -> None:
            if segments and segments[-1][0] == prefix:
                segments[-1][1].append(item)
            else:
                segments.append((prefix, [item]))

        scope = scopes[id(node)]
        for alias in node.names:
            local = alias.asname or alias.name
            if do_alias and alias.name in ALIASES:
                package, module = split_target(ALIASES[alias.name])
                add(package, module if module == local else f"{module} as {local}")
            elif do_shell and alias.name in SHELLS:
                shell = alias.name
                used = shell_uses(tree, shell, scope, own[shell])
                table = SHELL_NAME_TO_LOCAL[shell]
                wanted: list[str] = []
                for name in used:
                    if name not in table:
                        problems.append(f"{rel}: {shell}.{name} 不在表上，手改")
                        continue
                    if table[name] not in wanted:
                        wanted.append(table[name])
                order = list(SHELLS[shell])
                wanted.sort(key=order.index)
                if not wanted:
                    problems.append(f"{rel}:{node.lineno} {shell} import 了但沒讀任何名字，手改")
                for new_local in wanted:
                    package, module = SHELL_IMPORTS[new_local]
                    real = f"{package}.{module}"
                    if new_local in stored:
                        problems.append(f"{rel}:{node.lineno} {new_local} 在這個檔裡是別的東西，手改")
                    seen = bound.get((id(scope), new_local)) or bound.get((id(tree), new_local))
                    if seen == real:
                        continue
                    if seen is not None:
                        problems.append(f"{rel}:{node.lineno} {new_local} 已經綁到 {seen}，手改")
                    add(package, module if module == new_local else f"{module} as {new_local}")
            else:
                add(base, alias.name if not alias.asname else f"{alias.name} as {alias.asname}")
        new_lines: list[str] = []
        for prefix, items in segments:
            new_lines += render(head, render_prefix(prefix, node, rel), items, tail)
        jobs.append((node.lineno, node.end_lineno, new_lines))
    for start, end, new_lines in sorted(jobs, key=lambda job: job[0], reverse=True):
        lines[start - 1 : end] = new_lines
    out = "\n".join(lines)
    if do_shell and shells_here:

        def swap(match: re.Match[str]) -> str:
            shell, name = match.group(1), match.group(2)
            if shell not in shells_here:
                return match.group(0)
            local = SHELL_NAME_TO_LOCAL[shell].get(name)
            return f"{local}.{name}" if local else match.group(0)

        out = SHELL_TEXT.sub(swap, out)
    return out


def run(do_alias: bool, do_shell: bool) -> int:
    problems: list[str] = []
    changed = 0
    for rel in git_files():
        if is_alias_file(rel):
            continue
        path = pathlib.Path(rel)
        if not path.exists():
            continue
        text, crlf = read(path)
        if "tianxia" not in text and "from ." not in text:
            continue
        new = rewrite(rel, text, do_alias, do_shell, problems)
        if new != text:
            ast.parse(new)
            write(path, new, crlf)
            changed += 1
    print("changed files", changed)
    for line in problems:
        print("PROBLEM", line)
    return 1 if problems else 0


# ---------- 驗 ----------


class Blank(ast.NodeTransformer):
    """拿掉 import、字串換成佔位，把殼的 `<殼>.x` 換成真位置。"""

    def __init__(self, shells: set[str]) -> None:
        self.shells = shells

    def visit_Import(self, node):  # noqa: N802
        return None

    def visit_ImportFrom(self, node):  # noqa: N802
        return None

    def visit_Constant(self, node):  # noqa: N802
        if isinstance(node.value, str):
            return ast.Constant("S")
        return node

    def visit_Attribute(self, node):  # noqa: N802
        if isinstance(node.value, ast.Name) and node.value.id in self.shells:
            local = SHELL_NAME_TO_LOCAL[node.value.id].get(node.attr)
            if local:
                return ast.Attribute(ast.Name(local, ast.Load()), node.attr, ast.Load())
        return self.generic_visit(node)

    def visit_arg(self, node):  # noqa: N802
        return self.generic_visit(node)


def real_of(full: str) -> str:
    """基準那份的全名照表翻譯。"""
    parts = full.split(".")
    if len(parts) >= 2 and parts[0] == "tianxia" and parts[1] in ALIASES:
        return ".".join([ALIASES[parts[1]], *parts[2:]])
    return full


def import_seq(tree: ast.Module, rel: str) -> list[tuple[str, str]]:
    seq: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = base_module(node, rel)
            for index, alias in enumerate(node.names):
                seq.append((node.lineno, index, alias.asname or alias.name, real_of(f"{base}.{alias.name}")))
        elif isinstance(node, ast.Import):
            for index, alias in enumerate(node.names):
                seq.append((node.lineno, index, alias.asname or alias.name.split(".")[0], real_of(alias.name) if alias.asname else alias.name))
    seq.sort(key=lambda row: (row[0], row[1]))
    return [(local, real) for _, _, local, real in seq]


def check(base: str) -> int:
    names = subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--name-status", base, "--", "tests", "tianxia", "scripts", ":(glob)*.py"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    bad = 0
    same = 0
    shell_real = {f"{package}.{module}": local for local, (package, module) in SHELL_IMPORTS.items()}
    for row in names:
        status, _, rel = row.partition("\t")
        if not rel.endswith(".py") or status != "M":
            continue
        old = subprocess.run(["git", "-c", "core.quotepath=off", "show", f"{base}:{rel}"], capture_output=True, check=True).stdout.decode("utf-8").replace("\r\n", "\n")
        new = read(pathlib.Path(rel))[0]
        old_tree, new_tree = ast.parse(old), ast.parse(new)
        shells = {a.name for n in ast.walk(old_tree) if isinstance(n, ast.ImportFrom) and base_module(n, rel) == "tianxia" for a in n.names if a.name in SHELLS}
        old_seq = [row for row in import_seq(old_tree, rel) if not (row[0] in SHELLS and row[1] == f"tianxia.{row[0]}")]
        new_seq = import_seq(new_tree, rel)
        if shells:
            # 基準那份要是新序列的子序列，多出來的只能是殼換成的本地名
            allowed = {local for shell in shells for local in SHELLS[shell]}
            filtered = []
            at = 0
            for row in new_seq:
                if at < len(old_seq) and row == old_seq[at]:
                    at += 1
                    filtered.append(row)
                elif not (row[0] in allowed and shell_real.get(row[1]) == row[0]):
                    filtered.append(row)
            new_seq = filtered
        old_dump = ast.dump(Blank(shells).visit(old_tree))
        new_dump = ast.dump(Blank(set()).visit(new_tree))
        if old_dump != new_dump or old_seq != new_seq:
            bad += 1
            why = []
            if old_dump != new_dump:
                why.append("語法樹")
            if old_seq != new_seq:
                only_old = [r for r in old_seq if r not in new_seq][:3]
                only_new = [r for r in new_seq if r not in old_seq][:3]
                why.append(f"import 序列 少{only_old} 多{only_new}" if (only_old or only_new) else "import 順序")
            print("DIFF", rel, "；".join(why))
        else:
            same += 1
    print("same", same, "different", bad)
    return 1 if bad else 0


def targets() -> int:
    bad = 0
    count = 0
    for rel in git_files():
        path = pathlib.Path(rel)
        if not path.exists() or is_alias_file(rel):
            continue
        text = read(path)[0]
        if "tianxia" not in text and "from ." not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            base = base_module(node, rel)
            if not base.startswith("tianxia.features.") and base != "tianxia.core" and base != "tianxia":
                continue
            for alias in node.names:
                count += 1
                try:
                    module = importlib.import_module(base)
                    if not hasattr(module, alias.name):
                        importlib.import_module(f"{base}.{alias.name}")
                except ImportError as err:
                    bad += 1
                    print("MISSING", f"{rel}:{node.lineno}", base, alias.name, err)
        # 模組.名字：新位置的本地名讀的名字都在
        for local, (package, module) in SHELL_IMPORTS.items():
            uses = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == local}
            if not uses or not any(isinstance(n, ast.ImportFrom) and any((a.asname or a.name) == local for a in n.names) for n in ast.walk(tree)):
                continue
            real = importlib.import_module(f"{package}.{module}")
            for name in uses:
                count += 1
                if not hasattr(real, name):
                    bad += 1
                    print("MISSING", rel, f"{local}.{name}")
    print("checked", count, "missing", bad)
    return 1 if bad else 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        return run(True, True)
    if command == "alias":
        return run(True, False)
    if command == "shell":
        return run(False, True)
    if command == "check":
        return check(sys.argv[2])
    if command == "targets":
        sys.path.insert(0, ".")
        return targets()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
