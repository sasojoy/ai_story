"""交友求見的選單與求見畫面（功能包 socialize；全部拆包第 21 批）：交友那一顆、一類一顆的交友那一顆、求見的第二層選單（名單）、求見畫面的說明，
還有江湖頁「此地人物」那一排（figures_here_view；主幹合回第 2 段 D，它要問求見名單，所以放這裡不放 view.py：view 不 import menus）。
原本 Game 上的 4 個方法，名字去掉前導底線、第一個參數是 ctx。選單上「單人求見」那一顆（call:<人物>，行動列放在交友後面）與 act:call 那一格是 here_cell（MENU_ORDER["here"] 的 social 那一格，第 56 批）；按下去與標題接 Verb（第 57 批）。
"""
from __future__ import annotations

from tianxia import figures, precise, prologue as prologue_rules, ranks, roster
from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）
from tianxia.core.services import AUDIENCE_HALL_FIGURES, SNUB_NOTE
from tianxia.events import has_events_here  # 共用規則層（事件：這個地點有沒有）

from . import howto, view
from .view import AUDIENCE_MEET, SOCIAL_LIST_INTRO, SOCIAL_TALK


def precise_social_option(ctx, cost: int) -> Option:
    """一類一顆的交友（正式季整合 2.8）：照 social_plan。兩位以上見得到的人物時是「交友」打開名單（act:call，不花體力）；
    一位就直接開口（act:socialize，鈕上寫跟誰說話）；福緣、留在交友的事件也走 act:socialize；沒有人可以說話時灰掉、寫原因、不扣體力。"""
    kind, arg = view.social_plan(ctx)
    if kind == "list":
        return Option(id="act:call", label="交友")
    if kind == "talk":
        return ctx._cost_option("act:socialize", "交友", cost, note=SOCIAL_TALK.format(name=ctx.content.characters[arg].name))
    if kind is not None:
        return ctx._cost_option("act:socialize", "交友", cost)
    return Option(id="act:socialize", label=f"交友（{arg}）", enabled=False)


def socialize_option(ctx, people: list[str], cost: int) -> Option:
    """交友的按鈕。這裡只有一位大勢人物、沒有交友事件、福緣也還沒到，而他剛被你打敗、閉門不見（T4）時，交友只會
    撲空——按不下去、寫明原因。其他時候照舊。"""
    s, c = ctx.state, ctx.content
    if (
        len(people) == 1 and ctx._snubbed_character(people[0])
        and not has_events_here(c, c.locations[s.player.location], "socialize") and not roster.fortune_due(s, c)
    ):
        return Option(id="act:socialize", label=f"交友（{SNUB_NOTE}）", enabled=False)
    return ctx._cost_option("act:socialize", "交友", cost)


def audience_options(ctx) -> list[Option]:
    """求見的第二層選單：這裡每一位大勢人物一個選項，最後是永遠按得下去的「返回」。名望不夠（也沒結識過）的人
    也按得下去，只是會被打發（見 brush_off）；這個遊戲日已經跟他談滿、或剛吃了敗仗閉門不見的人按不下去並寫明原因
    （談滿的寫換日的那一刻）；每個遊戲日的輪數上限是每位人物各算各的（talk_turns_per_day）。"""
    c = ctx.content
    cost = c.config.action_cost["socialize"]
    per_day = view.talk_full_cap(ctx)
    opts = []
    for companion_id in ctx._figures_here():
        ch = c.characters[companion_id]
        option_id = f"call:{companion_id}"
        left = view.talks_left(ctx, companion_id)
        if ctx._snubbed_character(companion_id):
            opts.append(Option(id=option_id, label=f"{ch.name}（{SNUB_NOTE}）", enabled=False))
        elif not view.figure_can_meet(ctx, companion_id) and precise.on(c, ctx.state.world):  # 一類一顆（2.8）：不再打發
            if view.meet_event(ctx, companion_id) is not None:
                opts.append(ctx._cost_option(option_id, ch.name, cost, note=AUDIENCE_MEET))
            else:
                opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {view.fame_gap(ctx, companion_id)}）", enabled=False))
        elif not view.figure_can_meet(ctx, companion_id):
            opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {view.fame_gap(ctx, companion_id)}）"))  # 按下去走打發，見 brush_off
        elif left == 0:
            opts.append(Option(id=option_id, label=f"{ch.name}（{view.talked_out_note(ctx)}）", enabled=False))
        else:
            opts.append(ctx._cost_option(option_id, ch.name, cost, note=f"還能談 {left}/{per_day} 輪"))
    opts.append(Option(id="call:back", label="返回"))
    return opts


def audience_intro(ctx) -> str:
    """求見畫面的說明（場景上的那一段）：挑一位拜會；每位人物各算各的，一個遊戲日最多談幾輪、什麼時候重新算起。"""
    here = ctx.content.locations[ctx.state.player.location].name
    per_day = view.talk_full_cap(ctx)
    # 你跟這幾位的情誼（explain-1）：挑人之前看得到，跟談話時名字旁寫的是同一個數
    bonds = "、".join(f"{ctx.content.characters[cid].name} {ctx.state.player.affinities.get(cid, 0)}" for cid in ctx._figures_here())
    kind, moment = view.talks_reopen(ctx)
    again = f"到 {moment} 重新算起" if moment else "過一陣子重新算起" if kind == "later" else "這一季之內不再重算"  # FB-102
    if precise.on(ctx.content, ctx.state.world):  # 一類一顆：求見併進交友，名望不夠的灰著寫還差多少，不打發（FB-421）
        head = SOCIAL_LIST_INTRO.format(here=here, per_day=per_day, again=again)
    else:
        head = f"{here}有好幾位人物，挑一位求見。每位人物各算各的，最多談 {per_day} 輪，{again}；名望不夠的會被打發。"
    return head + (f"\n\n你跟他們的情誼：{bonds}。" if bonds else "")


def figures_here_view(ctx) -> list[dict]:
    """江湖頁「此地人物」那一排（介面重整 2026-11-05）：這裡此刻的大勢人物，一位一筆
    {id, name, side, affinity, talk: {via, why}, aid: [選項 id]}。talk.via 是「交談」要依序按的選項（一類一顆的交友直接開口是
    ["act:socialize"]、名單是 ["act:call", "call:<id>"]）；說不上話是 None、why 寫原因。aid 是選單上跟他有關的那幾顆
    （護衛、犒軍、挑戰本人），網頁點了人物才畫。只讀，不扣體力；路上、序章、事件與對話中、季收了是空的（決戰蓋著場景時選單是戰鬥的，網頁不畫這一排）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if p.journey is not None or s.pending_event or p.pending_companion or prologue_rules.active(s, c) or s.world.ended:
        return []
    people = ctx._figures_here()
    kind, arg = view.social_plan(ctx) if precise.on(c, s.world) else (None, None)
    listed = {o.id: o for o in audience_options(ctx)} if len(people) >= AUDIENCE_HALL_FIGURES or kind == "list" else {}
    out = []
    for cid in people:
        ch = c.characters[cid]
        fid = figures.of_character(c, cid)
        side = figures.side_name(c, fid)
        via = None
        if kind == "talk" and arg == cid:
            via = ["act:socialize"]
        elif f"call:{cid}" in listed and listed[f"call:{cid}"].enabled:
            via = ["act:call", f"call:{cid}"]
        elif not precise.on(c, s.world) and len(people) == 1 and view.talkable(ctx, cid):
            via = [f"call:{cid}"]
        why = None if via else (view.why_not_talk(ctx, cid) if not view.talkable(ctx, cid) else "先按「交友」")
        aid = [f"aid:guard:{fid}", f"aid:rally:{fid}", f"act:challenge:{fid}"] if fid else []
        out.append({"id": cid, "name": ch.name, "side": side, "affinity": p.affinities.get(cid, 0),
                    "talk": {"via": via, "why": why}, "aid": aid})
    return out


def here_cell(ctx, loc, cost: dict[str, int], odds: bool) -> list[Option]:
    """here/social 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options，本體與先後一字不動）：一類一顆開著時是交友那一顆（交友只談話、求見併進交友，正式季整合 2.8；
    拜入門派是前一格 here/sect），關著是舊的交友與求見。"""
    s, c = ctx.state, ctx.content
    if precise.on(c, s.world):
        return [precise_social_option(ctx, cost["socialize"])]
    people = ctx._figures_here()
    opts: list[Option] = []
    # 只有一位大勢人物、沒有交友事件、他又見不到（名望不夠、閉門不見、這個遊戲日談滿）、福緣也沒到、也不在召見的地點：
    # 交友只會花 5 點體力換同一句打發，所以不給，這條路只剩不花體力的求見（下面）
    only_the_door = len(people) == 1 and ranks.summons_event(s, c) is None and view.is_futile(ctx)
    if (has_events_here(c, loc, "socialize") or 0 < len(people) < AUDIENCE_HALL_FIGURES) and not only_the_door:
        # 兩位以上大勢人物的地點，交友只走福緣與地點事件、從不開口對話（見 socialize_figure），
        # 所以只在有交友事件時才給；人物改由下面的「求見」指名
        opts.append(socialize_option(ctx, people, cost["socialize"]))
    if len(people) == 1:  # 只有一位：直接求見他，一直按得下去（武學與成長設計 9.1）
        cid = people[0]
        ch = c.characters[cid]
        if ctx._snubbed_character(cid):
            opts.append(Option(id=f"call:{cid}", label=f"求見{ch.name}（{SNUB_NOTE}）", enabled=False))
        elif not ctx._can_meet(cid):
            opts.append(Option(id=f"call:{cid}", label=f"求見{ch.name}（名望還差 {view.fame_gap(ctx, cid)}）"))  # 按下去走打發，見 brush_off
        elif view.talks_left(ctx, cid) == 0:  # 求見一直都在：談滿了也留著、灰掉，說法跟求見名單一樣
            opts.append(Option(id=f"call:{cid}", enabled=False, label=f"求見{ch.name}（{view.talked_out_note(ctx)}）"))
        else:
            opts.append(ctx._cost_option(f"call:{cid}", f"求見{ch.name}", cost["socialize"]))
    if len(people) >= AUDIENCE_HALL_FIGURES:
        opts.append(Option(id="act:call", label="求見"))  # 只是打開第二層選單，不花體力（見 audience_options）
    return opts


def action_notes(ctx, ids: set[str], loc) -> dict[str, str]:
    """notes/socialize 那一格（core_seams，全部拆包第 56 批；原本在 Game.action_notes，鍵的順序算行為：交友、求見、單人求見）：行動列底下交友、求見那幾行。只給 ids 裡有的。"""
    s, c = ctx.state, ctx.content
    notes: dict[str, str] = {}
    if "act:socialize" in ids:
        figure = ctx._socialize_figure()
        notes["act:socialize"] = howto.social_line(
            None if figure is None else c.characters[figure].name, has_events_here(c, loc, "socialize"), view.audience_hall(ctx),
        )
    if "act:call" in ids:
        notes["act:call"] = howto.CALL_LINE
    if not s.player.picking_audience:  # 只有一位人物時選單上直接列的「求見某某」（行動列交友那一格放它）
        for option_id in ids:
            cid = option_id.removeprefix("call:")
            if option_id.startswith("call:") and cid in c.characters:
                # 跟選單上那一顆的判斷同一個次序、同一句話（FB-103：格子寫什麼，這一行就說什麼）：閉門不見寫整句（格子只放得下
                # 「閉門不見」）；見不到寫還差幾點名望、會被打發；談滿了寫整句連同換日的那一刻（格子只放得下「已談滿」，day-scale 審查 I1）
                name = c.characters[cid].name
                if ctx._snubbed_character(cid):
                    notes[option_id] = SNUB_NOTE
                elif not ctx._can_meet(cid):
                    notes[option_id] = howto.call_line(name, False, view.fame_gap(ctx, cid))
                elif view.talks_left(ctx, cid) == 0:
                    notes[option_id] = view.talked_out_note(ctx)
                else:
                    notes[option_id] = howto.call_line(name, True)
    return notes


def travel_block(state, content) -> TravelBlock | None:
    """block/audience 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字一字不動）：求見名單開著。"""
    return TravelBlock("求見中，先返回才能安排前往", to_jianghu=True) if state.player.picking_audience else None
