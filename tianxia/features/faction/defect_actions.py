"""叛投的行動（全部拆包第 35 批；原本是 Game 上的 _defect_step、_left_names、_leave_behind、_defect_targets，本體一字沒改，self 換成 ctx；
另加 scene：原本 Game._own_scene_text 叛投確認畫面那一段）。Game 留一行委派的：_left_names（場景原位在叫）、_defect_options（選單原位在叫）；
_defect_step 只有包的 choose 掛鉤叫（沒有委派）；_leave_behind 改由包登記叛投 after 位置的 leave_behind 那一格（DEFECT_ORDER）。
"""
from __future__ import annotations

import math

from tianxia import roster, team
from tianxia.core import features as features_core
from tianxia.core.option import Option
from tianxia.models import FactionDef

from . import defection


def defect_step(ctx, arg: str) -> list[str]:
    """叛投分兩步（同投靠）：按「叛投某陣營」先出確認畫面（寫明代價、一季一次、三方人數），「確定」才真的叛投。
    確定時再驗一次（defection.refusal，跟選單挑對象的 targets_here 同一套規則：還在那個投靠點、還能叛投、不是自己的陣營、
    名字不在沒打完的決戰的參戰名單上）：中間走開了、規則關了、另一個分頁已經叛投過、報了名參戰，都不叛投，
    而且把真正的原因說給玩家聽；那一則江湖紀錄也不寫成「叛投某某」（沒叛成）。
    投靠名冊由 choose() 結尾的 _record_faction 改記，這裡不碰。
    豪強分屬兩軍的季，arg 可以是「陣營:依附的那一軍」（defection.slots_here），挑的那一軍記在 pending_ally。"""
    p = ctx.state.player
    if arg == "cancel":
        p.pending_defect = p.pending_ally = None
        return ["你決定再想想。"]
    if arg == "confirm":
        target = ctx.content.scenario.faction(p.pending_defect)
        ally, p.pending_defect, p.pending_ally = p.pending_ally, None, None
        reason = defection.refusal(ctx.state, ctx.content, target, ctx._battle_now(), ally)
        if reason is not None:
            if ctx._draft is not None:
                ctx._draft.title = "叛投不成"
            return [f"（{reason}）"]
        msgs = defection.defect(ctx.state, ctx.content, target, ally)
        for got in features_core.defect_run("after", {}, ctx, target.id):
            msgs += got  # 同伴回江湖（陣營自己的 leave_behind）→ 人物情誼包：接了又叛投，欠著的都算食言（NPC 智能 2.1）
        return msgs
    fid, _, ally = arg.partition(":")
    target = ctx.content.scenario.faction(fid)
    p.pending_defect, p.pending_ally = target.id, ally or None
    prompt = defection.prompt(ctx.state, ctx.content, target, ctx.faction_counts_text(), p.pending_ally, left_names(ctx, target.id))
    ctx._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（同投靠，FB-046）
    return [prompt]


def left_names(ctx, side: str) -> list[str]:
    """叛投確認畫面「會失去」那一段的同伴（歷史武將同行 9.5）：寫了 side、跟新陣營不合的。按鈕回的那一份與場景那一段（FB-362）共用。"""
    return [ctx.content.characters[cid].name for cid in roster.left_behind(ctx.state, ctx.content, ctx.world, side)]


def leave_behind(ctx, side: str) -> list[str]:
    """叛投之後（歷史武將同行 9.5）：寫了 side、跟新陣營不合的同伴當場回江湖——全服放掉 owner、拿出隊伍、情誼照決戰後回江湖減半。"""
    c, p = ctx.content, ctx.state.player
    keep, out = c.config.companions.parted_keep, []
    for cid in roster.left_behind(ctx.state, c, ctx.world, side):
        ctx.world.release_companion(cid)
        team.remove_from_team(ctx.state, cid)
        before = p.affinities.get(cid, 0)
        p.affinities[cid] = math.floor(before * keep)
        out.append(roster.DEFECT_LEFT.format(name=c.characters[cid].name, before=before, after=p.affinities[cid]))
    return out


def defect_targets(ctx) -> list[tuple[FactionDef, str | None]]:
    """這一刻選單上能叛投去的（陣營, 依附的那一軍）。先用不碰資料庫的條件擋掉大多數人（散人、劇本沒有陣營、叛投過），
    剩下的才讀目前的決戰、看名字在不在參戰名單上（defection.enlisted）。豪強分屬兩軍的季見 defection.slots_here。"""
    if not defection.can_defect(ctx.state, ctx.content):
        return []
    return defection.slots_here(ctx.state, ctx.content, ctx._battle_now())


def defect_options(ctx) -> list[Option]:
    """選單上的叛投（原本 Game._everyday_options 的一段迴圈）：每個能叛投去的槽一顆；豪強分屬兩軍的季，豪強的投靠點每一軍一顆。"""
    opts = []
    for target, ally in defect_targets(ctx):
        option_id = f"defect:{target.id}" + (f":{ally}" if ally else "")  # 豪強分屬兩軍：豪強的投靠點每一軍一顆
        opts.append(Option(id=option_id, label=defection.slot_label(ctx.state, ctx.content, target, ally)))
    return opts


def scene(ctx) -> str:
    """叛投確認畫面的場景（原本 Game._own_scene_text 叛投那一段）：標題「叛投X」，豪強分屬兩軍時也可能是「改投X」「改依附X」，接確認畫面的話。"""
    s, c = ctx.state, ctx.content
    target = c.scenario.faction(s.player.pending_defect)
    ally = s.player.pending_ally
    head = defection.slot_label(s, c, target, ally)  # 「叛投X」；豪強分屬兩軍時也可能是「改投X」「改依附X」
    return f"**{head}**\n\n{defection.prompt(s, c, target, ctx.faction_counts_text(), ally, left_names(ctx, target.id))}"
