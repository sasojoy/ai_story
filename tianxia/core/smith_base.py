"""打造單子「讀」的那一小半（全部拆包第 40 批，第 41 批 PM 認定第 4 條：鐵匠鋪包 features/smithy/smithing.py 的 GO_VERB、
is_forge_step、is_step_line、draft_here、draft_stale 與它們讀的常數、here 原樣搬來，包 re-export 同一批）：核心的 choose（打造那幾步
併成一則）、_drop_stale_references 與 sync（單子那一欄關了、失效了就清）讀它，不經舊名 smithing。只讀，不寫。核心本體
（tianxia/core/ 底下的檔），不進 MODULES。單子一步一步回的那幾句（問下一步、挑了什麼、退回、不打了）是原句搬家。
"""
from __future__ import annotations

from .. import armor, weapons
from ..models import WEAPON_KINDS, Content
from ..state import GameState, SmithDraft

ARMOR_KIND = "防具"  # 單子（SmithDraft.kind）與開爐鈕 id 上代表防具的那一格（防具沒有種類，四欄設計 4.7）
GO_VERB = "forge-go"
ASK_KIND = "要打哪一種兵器？"  # 待 joy 潤
ASK_MAIN = "挑主料：主料定這把兵器的階，也定工錢。"  # 待 joy 潤
UNDONE = "退回一步。"  # 待 joy 潤（FB-133）：按「上一步」先回這一句，再問那一步
ASK_AUX = "挑輔料：主料與輔料合起來定這把兵器的屬性。"  # 待 joy 潤
READY = "料都齊了，看一眼機率再開爐。"  # 待 joy 潤
PICKED_KIND = "兵器：{what}。"  # 待 joy 潤：每挑一樣，這一步的回話先回報挑了什麼（進同一則「打造」紀錄），再問下一步
PICKED_MAIN = "主料：{what}。"  # 待 joy 潤
PICKED_AUX = "輔料：{what}。"  # 待 joy 潤
CANCELLED = "你把素材收了回去，這回先不打。"  # 待 joy 潤
ARMOR_ASK_MAIN = "挑主料：主料定這件防具的階，也定工錢。"  # 待 joy 潤（防具沒有挑種類那一步，打開就從主料挑起）
ARMOR_ASK_AUX = "挑輔料：主料與輔料合起來定這件防具的屬性。"  # 待 joy 潤


def here(state: GameState, content: Content, kind: str | None) -> bool:
    """這一爐在這裡打得了：防具看防具的開關、其餘看武器的開關，人都要在城鎮（armor.smith_here、weapons.smith_here）。"""
    return (armor.smith_here if kind == ARMOR_KIND else weapons.smith_here)(state, content)


def is_forge_step(arg: str) -> bool:
    """smith: 後面這一段是打造的一步（含打開與開爐）：江湖紀錄的標題是「打造」；打開以外的每一步併進同一則
    （Game.choose 照它 merge，打開那一步 "forge" 另起一則）。"""
    return arg.partition(":")[0].startswith("forge")


# 打造單子自己的回話（step 回的那幾句）：問下一步的、退回去的、不打了的整句照常數認；挑了什麼（PICKED_*）的中間是素材或種類的名字，
# 拆成前後兩段認。Game.choose 開爐成了併進「打造」那一則時用 is_step_line 收掉這些（FB-141），別的話（大勢門檻的消息之類）留著
_STEP_LINES = frozenset({ASK_KIND, ASK_MAIN, ASK_AUX, ARMOR_ASK_MAIN, ARMOR_ASK_AUX, READY, CANCELLED, UNDONE})
_PICKED_FRAMES = tuple(tuple(template.split("{what}")) for template in (PICKED_KIND, PICKED_MAIN, PICKED_AUX))


def is_step_line(line: str) -> bool:
    """這一行是不是打造單子一步一步走時自己回的話（step 的回話：問下一步、挑了什麼、上一步、不打了）。開爐的結果、拒絕句、
    別的消息都不是。照上面的常數認，句子改了這裡跟著改，不另寫一份。"""
    if line in _STEP_LINES:
        return True
    return any(len(line) > len(head) + len(tail) and line.startswith(head) and line.endswith(tail) for head, tail in _PICKED_FRAMES)


def draft_stale(content: Content, draft: SmithDraft) -> bool:
    """存檔裡的單子指著內容已經沒有的種類或素材（內容改版）：選單畫不出來（go_option 查素材會丟 KeyError），要從頭來。
    防具的單子 kind 是 ARMOR_KIND。"""
    return (draft.kind is not None and draft.kind not in WEAPON_KINDS and draft.kind != ARMOR_KIND) or any(
        mid is not None and mid not in content.materials for mid in (draft.main, draft.aux))


def draft_here(state: GameState, content: Content, draft: SmithDraft) -> bool:
    """這張單子在這裡還打得了（存檔修補、同步時看）：防具的單子看防具的開關、兵器的看武器的開關（人都要在城鎮）。"""
    return here(state, content, draft.kind)
