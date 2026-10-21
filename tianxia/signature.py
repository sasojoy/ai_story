"""本命武學（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；數字在 Config.signature_arts）：
玩家自己那一份威力 × power_scale、學到時直接第 start_level 成。每門本命武學帶一個本命戰法（SkillDef.tactic，tianxia/tactics.py：
在一般的仗的回合裡發動）；以前的本命特效（打贏多拿幾成、少扣幾成氣血這類數字）Joy 2026-10-15 退回（「說是武學卻更像寶物的功能」），拿掉了。
讀的是內容（content.skills），不碰全服：本命武學一定是內容寫的。只 import models、state、tactics。
"""
from __future__ import annotations

from . import tactics
from .models import Content, TacticDef
from .state import GameState


def of(content: Content, skill_id: str | None) -> TacticDef | None:
    """這門武學的本命戰法；不是本命武學是 None（學來的武學的小戰法 TacticDef.minor 不算）。"""
    tactic = tactics.of(content, skill_id)
    return tactic if tactic is not None and not tactic.minor else None


def is_signature(content: Content, skill_id: str | None) -> bool:
    return of(content, skill_id) is not None


def worn(state: GameState, content: Content) -> list[tuple[str, TacticDef]]:
    """本人身上練著的那兩門裡的本命戰法（武學在前）：（武學 id, 戰法）。"""
    member = state.player.member
    out = []
    for skill_id in (member.wugong_id, member.neigong_id):
        tactic = of(content, skill_id)
        if tactic is not None:
            out.append((skill_id, tactic))
    return out


def scale(content: Content, skill_id: str | None) -> float:
    """玩家自己那一份本命武學的威力倍數（Config.signature_arts.power_scale）；其他武學是 1。"""
    return content.config.signature_arts.power_scale if is_signature(content, skill_id) else 1.0


def card_text(tactic: TacticDef) -> str:
    """功法卡、修練頁、角色卡那一段（tactics.card_text；小戰法寫「小戰法」）。"""
    return tactics.card_text(tactic)


def lift_levels(state: GameState, content: Content, skill_ids) -> None:
    """本命武學學到時直接第 Config.signature_arts.start_level 成：身上那一欄照欄位、功法庫裡的照 art_levels；
    已經練得更高的不動、還沒學到的不管。學到那一刻（companion_agent）與舊角色讀檔（Game._lift_signature_levels）都叫它。"""
    start = content.config.signature_arts.start_level
    p = state.player
    for skill_id in skill_ids:
        if not is_signature(content, skill_id):
            continue
        for slot in ("wugong", "neigong"):
            if getattr(p.member, f"{slot}_id") == skill_id:
                setattr(p.member, f"{slot}_level", max(getattr(p.member, f"{slot}_level"), start))
                break
        else:
            if skill_id in p.arts:
                p.art_levels[skill_id] = max(p.art_levels.get(skill_id, 1), start)


def learned(state: GameState, content: Content) -> list[str]:
    """這個角色情誼到了、學過的本命武學（旗標「學會本命:人物 id」），照人物的本命武學與內功列出。"""
    out: list[str] = []
    for flag in state.player.flags:
        if flag.startswith("學會本命:"):
            character = content.characters.get(flag.split(":", 1)[1])
            if character is not None:
                out += [s for s in (character.starting_wugong, character.starting_neigong) if s]
    return out
