"""投靠與拜入門派（全部拆包第 35 批；原本是 Game 上的 _sect_options、_ally_options、_faction_step、_bot_lean、_join_lean、_faction_prompt，
本體一字沒改，self 換成 ctx）。

投靠分兩步（伺服器假人設計第八節第 3 項）：按「投靠某陣營」先出確認畫面，「確定」才真的投靠，「再想想」就作罷；豪強分屬兩軍的季
投靠豪強中間多一步挑依附哪一軍。Game 留一行委派的：_sect_options、_join_lean、_faction_prompt（選單與場景原位在叫）；_ally_options 只有包裡的
pending_options 叫（沒有委派）；_faction_step 只有包的 choose 掛鉤叫（沒有委派）。選單「接管整個選單」的待確認那三段搬成 pending_options
（Game 留 _faction_pending_options）。

「你這一步」的 join 那一格（全部拆包第 36 批；原本 weekcard._steps 最後那一段與 step._target 的去投靠那一支）：join_step_items、
join_step_place，只讀；JOIN_STEP 從 weekcard 搬來，字一個不改。
"""
from __future__ import annotations

from tianxia import allied, wins
from tianxia import step as step_rules  # 核心本體（第 36 批收進 MODULES）：「你這一步」的 REF、place
from tianxia.core import bounty_base
from tianxia.core.option import Option
from tianxia.events import event_candidates  # 過渡：待搬（事件：這裡抽得到的拜門派事件）
from tianxia.rules import STANCE_NAMES, season_one

from . import defection, lean_actions
from .ending_actions import four_wins

SECT_LABEL = "拜入{sect}"  # 待 joy 潤：拜入門派從交友搬到「此地還能做」的一顆（正式季整合 2.7；原本寫在 engine.py）


def sect_options(ctx) -> list[Option]:
    """拜入門派（一類一顆開著時從交友搬出來，正式季整合 2.7）：這裡抽得到的拜門派事件各一顆，不花體力（同投靠）。"""
    s, c = ctx.state, ctx.content
    opts = []
    for event in event_candidates(s, c, "sect"):
        sect = next((e.join_sect for ch in event.choices for e in (ch.effect, ch.fail_effect) if e.join_sect), None)
        if sect in c.sects:
            opts.append(Option(id=f"sect:{event.id}", label=SECT_LABEL.format(sect=c.sects[sect].name)))
    return opts


def sect_choose(ctx, event_id: str) -> list[str]:
    """拜入門派（一類一顆，sect_options）：端出那一則事件，不花體力。"""
    return ctx._present(ctx.content.events[event_id], "sect")


def ally_options(ctx, cancel: bool) -> list[Option]:
    """選邊的兩顆（豪強分屬兩軍；照劇本 allies 的順序，鈕上寫那一軍此刻幾人，人數照 allied.side_totals）；
    投靠的確認畫面上多「再想想」，拜入門派之後那兩顆不能略過。"""
    sides = allied.side_totals(ctx.world.roll_counts())
    faction = ctx.state.player.pending_faction or ctx.state.player.faction
    opts = [
        Option(id=f"faction:ally:{a.id}", label=allied.ALLY_BUTTON.format(ally=a.name, n=sides.get(a.id, 0)))
        for a in allied.allies_of(ctx.content, faction)
    ]
    return opts + ([Option(id="faction:cancel", label="再想想")] if cancel else [])


def faction_step(ctx, arg: str) -> list[str]:
    """投靠分兩步（伺服器假人設計第八節第 3 項）：按「投靠某陣營」先出確認畫面（寫明這一季
    不能改投、各方目前各有幾人），「確定」才真的投靠，「再想想」就作罷。
    豪強分屬兩軍的季（allied.on），投靠豪強中間多一步挑依附哪一軍（ally:<id>）；拜入要依附的門派之後（allied.needs_ally）
    也按 ally:<id> 挑，挑了就算投靠完成。"""
    p = ctx.state.player
    if arg == "cancel":
        p.pending_faction = p.pending_ally = None
        return ["你決定再想想。"]
    kind, _, ally_id = arg.partition(":")
    if kind == "lean":  # 三陣營四勝利：豪強改幫另一軍（本週卡「改幫黃巾」；選單只在 lean_options 給）
        return lean_actions.lean_step(ctx, ally_id)
    if kind == "ally":
        ally = ctx.content.scenario.faction(ally_id)
        if p.pending_faction is None:  # 拜入門派之後挑一邊（選單只在 needs_ally 時給這兩顆）
            p.ally = ally.id
            return [allied.ALLY_DONE.format(ally=ally.name)] + ctx._ally_follows_battle()
        p.pending_ally = ally.id
        prompt = faction_prompt(ctx, ctx.content.scenario.faction(p.pending_faction))
        ctx._hide(prompt)
        return [prompt]
    if arg == "confirm":
        faction = ctx.content.scenario.faction(p.pending_faction)
        ally, p.pending_faction, p.pending_ally = p.pending_ally, None, None
        if p.location not in faction.join_at:
            return ["（你已經不在投靠的地方了。）"]
        p.faction = faction.id
        p.ally = bot_lean(ctx, faction.id, ally) if allied.on(ctx.content, ctx.state.world) else None
        # 投靠這一刻就推一次新手引導：第一季「投靠、看一眼本週軍令」那一步只看陣營（計畫 T6）；beta 照舊等下一個行動
        msgs = [f"你投靠了{allied.label(ctx.content, p.faction, p.ally)}。"]
        if p.ally is not None:
            msgs += ctx._ally_follows_battle()  # 先臨時投效了另一邊的散人（FB-273）
        if season_one(ctx.content, ctx.state.world):
            msgs += ctx._guide(ctx._note_action("join"))  # 走對話框（畫面批次審查 I2）
        return msgs
    faction = ctx.content.scenario.faction(arg)
    # 三陣營四勝利開著的季，投靠豪強照投靠點直接給傾向、不出選邊鈕（企劃者 2026-10-24 第 6 件；之後隨時改幫）
    lean = wins.join_lean(ctx.content, faction.id, p.location) if four_wins(ctx) and allied.on(ctx.content, ctx.state.world) else None
    p.pending_faction, p.pending_ally = faction.id, lean
    prompt = faction_prompt(ctx, faction)
    ctx._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（FB-046）
    return [prompt]


def bot_lean(ctx, faction_id: str, picked: str | None) -> str | None:
    """三陣營四勝利開著的季，伺服器假人投靠豪強那一下的傾向（FB-810）：依附豪強人數少的那一軍（wins.bot_lean，確認這一下才數），
    不看投靠點；真人、兩軍的人、開關關著（還有選邊鈕）都照 picked。假人投靠之後不按「改幫」，所以這一下就是它這一季幫誰。"""
    if ctx.state.player.bot is None or not four_wins(ctx):
        return picked
    season = ctx.world.get_season_number()
    return wins.bot_lean(ctx.state.player.name, season, ctx.content, faction_id, ctx.world.roll_counts()) or picked


def join_lean(ctx) -> list[str]:
    """三陣營四勝利開著的季，拜入要依附一軍的門派而投靠（曹氏莊院）的那一下：照門派所在地直接給傾向（PM 2026-10-25 第 5 件），
    不出選邊鈕；先臨時投效了另一邊的照 _ally_follows_battle 換過去。其他時候什麼都不做（照舊 allied.needs_ally 出選邊鈕）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not four_wins(ctx) or not allied.needs_ally(s, c):
        return []
    sect = c.sects.get(p.sect) if p.sect else None
    p.ally = wins.join_lean(c, p.faction, sect.location if sect is not None else p.location)
    return [allied.ALLY_DONE.format(ally=c.scenario.faction_name(p.ally, p.ally))] + ctx._ally_follows_battle()


def faction_prompt(ctx, faction) -> str:
    p = ctx.state.player
    counts = ctx.faction_counts_text()
    if allied.on(ctx.content, ctx.state.world) and faction.allies and p.pending_ally is None:  # 豪強分屬兩軍：先挑一邊
        return allied.ALLY_PICK.format(counts=counts)
    side = p.pending_ally or faction.id  # 依附的豪強接的是那一軍的懸賞
    held = bounty_base.stranded(ctx.state, ctx.content, side)  # 手上揭著、投靠之後接不了的懸賞（FB-151）；沒有就一個字不多
    lost = bounty_base.STRANDED_JOIN.format(n=len(held)) if held else ""
    return f"投靠後這一季不能改投（叛投另論）。{lost}{counts}。確定投靠{allied.label(ctx.content, faction.id, p.pending_ally)}？"


def pending_options(ctx) -> list[Option] | None:
    """選單「接管整個選單」的待確認三段（原本寫在 Game._everyday_options 夾在談著與求見之間：拜入要依附的門派之後還沒挑一邊、
    投靠的確認畫面、叛投的確認畫面）：都沒有待確認回 None，Game 原位接著往下排。"""
    s, c = ctx.state, ctx.content
    if allied.needs_ally(s, c):  # 拜入要依附的門派之後還沒挑一邊（豪強分屬兩軍）：只剩選邊
        return ally_options(ctx, cancel=False)
    if s.player.pending_faction:
        faction = c.scenario.faction(s.player.pending_faction)
        if allied.on(c, s.world) and faction.allies and s.player.pending_ally is None:  # 投靠豪強：先挑依附哪一軍
            return ally_options(ctx, cancel=True)
        return [
            Option(id="faction:confirm", label=f"確定投靠{allied.label(c, faction.id, s.player.pending_ally)}"),
            Option(id="faction:cancel", label="再想想"),
        ]
    if s.player.pending_defect:
        target = c.scenario.faction(s.player.pending_defect)
        return [  # 「確定叛投X」；豪強分屬兩軍時也可能是「確定改投X」「確定改依附X」（defection.slot_label）
            Option(id="defect:confirm", label=f"確定{defection.slot_label(s, c, target, s.player.pending_ally)}"),
            Option(id="defect:cancel", label="再想想"),
        ]
    return None


# core_step（全部拆包第 36 批「你這一步」）：join 那一格（core/features.py 的 STEP_ORDER：排最後）
JOIN_STEP = "先投一方：{places}。"  # 待 joy 潤：散人「眼下要事」最後的退路


def _join_place_names(ctx, faction) -> list[str]:
    """這一方的投靠點的地名（同 weekcard._places：三方卡照用那一份，這裡抄一份，包不 import weekcard）。"""
    locs = ctx.content.locations
    return [locs[x].name for x in faction.join_at if x in locs]


def join_step_items(ctx) -> list[dict]:
    """「你這一步」的去投靠那一件（原本 weekcard._steps 最後那一段）：散人、劇本有陣營、季沒收才有。"""
    s, c = ctx.state, ctx.content
    if s.player.faction is None and c.scenario.factions and not s.world.ended:
        places = "、".join(f"{STANCE_NAMES.get(f.id, f.name)}在{_join_place_names(ctx, f)[0]}" for f in c.scenario.factions if _join_place_names(ctx, f))
        return [{"kind": "join", "text": JOIN_STEP.format(places=places), step_rules.REF: ("join",)}]
    return []


def join_step_place(ctx, ref: tuple) -> tuple:
    """去投靠那一件的 (id, target, None)（原本 step._target 的去投靠那一支）：最近的投靠點；一樣近照劇本陣營的順序；沒有 (None, None, None)。"""
    c = ctx.content
    joins = {loc: f for f in reversed(c.scenario.factions) for loc in f.join_at if loc in c.locations}  # 一樣近照劇本陣營的順序
    where = ctx._nearest_to(set(joins)) if joins else None  # noqa: SLF001
    return (joins[where].id, step_rules.place(ctx, where), None) if where is not None else (None, None, None)
