"""本命武學（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；數字在 Config.signature_arts）：
玩家自己那一份威力 × power_scale、學到時直接第 start_level 成。每門本命武學帶一個本命戰法（SkillDef.tactic，tianxia/tactics.py：
在一般的仗的回合裡發動）；以前的本命特效（打贏多拿幾成、少扣幾成氣血這類數字）Joy 2026-10-15 退回（「說是武學卻更像寶物的功能」），拿掉了。
讀的是內容（content.skills），不碰全服：本命武學一定是內容寫的。只 import models、state、tactics。
"""
from __future__ import annotations

import string

from . import tactics
from .models import Content, TacticDef
from .state import GameState
from .tactics import figure_arts


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
    """這個角色情誼到了、學過的本命武學（旗標「學會本命:人物 id」），照人物的本命武學與內功列出（tactics.figure_arts：
    歷史武將同行起始帶的學來的武學不算，FB-640）。"""
    out: list[str] = []
    for flag in state.player.flags:
        if flag.startswith("學會本命:"):
            character = content.characters.get(flag.split(":", 1)[1])
            if character is not None:
                out += tactics.figure_arts(content, character)
    return out


# ── 內容驗證（第二輪第 96 批）──
def check_signature_arts(c: Content, need) -> None:
    """本命武學（tianxia/signature.py、tactics.py，企劃者 2026-10-15）：寫了本命戰法（SkillDef.tactic）的只能是人物的本命武學或本命內功
    （CharacterDef.starting_*，玩家只在情誼到了才學得到）、品質要是絕學；小戰法（TacticDef.minor）只寫在下品、不是本命的武學上；戰法的名字不重複、不撞一般與特別功效的名字；說明裡的 {鍵}
    都要在 params 裡（卡上換成數字）；allies 是人物、foe_faction 是劇本的陣營；寫了一般功效（SkillDef.traits）的第一個要是自己的屬性、不重複。
    本命是人物起始武學裡的絕學（tactics.figure_arts，FB-640）：歷史武將同行起始帶的學來的下品武學（FB-364）照樣帶小戰法、不是本命。"""
    starts = {s for ch in c.characters.values() for s in (ch.starting_wugong, ch.starting_neigong) if s}
    own_arts = {s for ch in c.characters.values() for s in figure_arts(c, ch)}  # 人物的本命武學與本命內功
    trait_names = {t.name for t in c.traits.general} | {t.name for t in c.traits.special}
    factions = {f.id for f in c.scenario.factions}
    seen: dict[str, str] = {}
    for skill in c.skills.values():
        if skill.traits:
            need(skill.traits[0] == skill.attribute, f"武學 {skill.id}：一般功效的第一個要是自己的屬性 {skill.attribute}")
            need(len(set(skill.traits)) == len(skill.traits), f"武學 {skill.id}：一般功效不能重複")
        tactic = skill.tactic
        if tactic is None:
            continue
        if tactic.minor:  # 小戰法（學來的武學，Joy 2026-10-21）：下品的內容武學、不是人物的本命；沒有本命底蘊與連動
            need(skill.id not in own_arts, f"武學 {skill.id}：人物的本命武學寫的是本命戰法，不是小戰法")
            need(skill.quality in ("下品", "上品"), f"武學 {skill.id}：小戰法只寫在下品、上品的武學上")  # 上品內功（企劃者 2026-11-04）
            need(not tactic.might and not tactic.allies and tactic.foe_faction is None,
                 f"武學 {skill.id}：小戰法不寫 might、allies、foe_faction")
        else:
            need(skill.id in starts, f"武學 {skill.id}：本命戰法只能寫在人物的本命武學或本命內功上")
            need(skill.quality == "絕學", f"武學 {skill.id}：本命武學的品質要是絕學")
        first = seen.setdefault(tactic.name, skill.id)
        need(first == skill.id, f"本命戰法的名字「{tactic.name}」重複（{first}、{skill.id}）")
        need(tactic.name not in trait_names, f"武學 {skill.id}：本命戰法的名字「{tactic.name}」跟一般或特別功效同名")
        fields = {name for _, name, _, _ in string.Formatter().parse(tactic.desc) if name}
        need(fields <= set(tactic.params), f"武學 {skill.id}：本命戰法的說明用了 params 沒有的 {sorted(fields - set(tactic.params))}")
        need(all(a in c.characters for a in tactic.allies), f"武學 {skill.id}：本命戰法的 allies 不是人物")
        need(tactic.foe_faction is None or tactic.foe_faction in factions, f"武學 {skill.id}：本命戰法的 foe_faction 不是劇本的陣營")
    # 本命戰法第三批：特別功效、神器、名將本命兵器的戰法（一般功效的換成 traits.tactic_defs 時才有名字，名字就是功效名）
    own = [(f"特別功效 {t.id}", t.tactic) for t in c.traits.special if t.tactic is not None]
    own += [(f"神器配方 {r.id}", r.tactic) for r in c.forge_secrets.values() if r.tactic is not None]
    own += [(f"名將本命兵器 {a.character}", a.tactic) for a in c.gear.signature_arms if a.tactic is not None]
    own += [(f"高階技能 {h.id}", h.tactic) for h in c.traits.high]  # 武學技能分檔
    own += [(f"神品意境 {g.id}", g.tactic) for g in c.traits.god]  # 特殊頓悟
    for where, tactic in own:
        first = seen.setdefault(tactic.name, where)
        need(first == where or (where.startswith("特別功效") and tactic.name in trait_names and first.startswith("特別功效")),
             f"{where}：戰法的名字「{tactic.name}」重複（{first}）")
        if not where.startswith("特別功效"):
            need(tactic.name not in trait_names, f"{where}：戰法的名字「{tactic.name}」跟一般或特別功效同名")
        fields = {name for _, name, _, _ in string.Formatter().parse(tactic.desc) if name}
        need(fields <= set(tactic.params), f"{where}：戰法的說明用了 params 沒有的 {sorted(fields - set(tactic.params))}")
    for arm in c.gear.signature_arms:
        need(arm.bond is None or bool(arm.bond.desc), f"名將本命兵器 {arm.character}：人器合一要寫說明")
        if arm.bond is not None:  # 加強的是那位名將的哪一門（PM 2026-10-16：只加卡上寫的那一門）
            ch = c.characters.get(arm.character)
            own = [c.skills[s].tactic.name for s in (figure_arts(c, ch) if ch else ()) if c.skills[s].tactic is not None]
            need(arm.bond.tactic in own, f"名將本命兵器 {arm.character}：人器合一的 tactic 要是他本命的一門戰法 {own}，寫的是「{arm.bond.tactic}」")
            need(not arm.bond.tactic or arm.bond.tactic in arm.bond.desc, f"名將本命兵器 {arm.character}：人器合一的說明要寫到加強的那一門「{arm.bond.tactic}」")
    for trait in c.traits.general:  # 絕學立招：絕招的名字到時候換成那門絕學的名字，這裡只驗說明的 {鍵} 與以器配招的說明
        if trait.ultimate is not None:
            fields = {name for _, name, _, _ in string.Formatter().parse(trait.ultimate.desc) if name}
            need(fields <= set(trait.ultimate.params), f"一般功效 {trait.name}：絕招的說明用了 params 沒有的 {sorted(fields - set(trait.ultimate.params))}")
            need(trait.ultimate_bond is None or bool(trait.ultimate_bond.desc), f"一般功效 {trait.name}：以器配招要寫說明")
        if trait.tactic is None:
            continue
        need("{extra}" not in trait.desc or trait.extra_per_layer > 0, f"一般功效 {trait.name}：說明寫了 {{extra}} 卻沒有 extra_per_layer")
        used = [v for v in [trait.tactic.rate, *trait.tactic.params.values()] if isinstance(v, str)]
        need(all(v in ("value", "extra") for v in used), f"一般功效 {trait.name}：戰法的數字只能寫數字、value 或 extra")
