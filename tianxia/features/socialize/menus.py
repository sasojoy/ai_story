"""交友求見的選單與求見畫面（功能包 socialize；全部拆包第 21 批）：交友那一顆、一類一顆的交友那一顆、求見的第二層選單（名單）、求見畫面的說明。
原本 Game 上的 4 個方法，名字去掉前導底線、第一個參數是 ctx。選單上「單人求見」那一顆（call:<人物>，行動列放在交友後面）與 act:call 那一格是 act 子動詞
（總表第 57 批），留在核心原位叫這裡的服務。
"""
from __future__ import annotations

from tianxia import precise, roster
from tianxia.core.option import Option
from tianxia.core.services import SNUB_NOTE
from tianxia.events import has_events_here  # 過渡：待搬（事件：這個地點有沒有）

from . import rules
from .rules import AUDIENCE_MEET, SOCIAL_LIST_INTRO, SOCIAL_TALK


def precise_social_option(ctx, cost: int) -> Option:
    """一類一顆的交友（正式季整合 2.8）：照 social_plan。兩位以上見得到的人物時是「交友」打開名單（act:call，不花體力）；
    一位就直接開口（act:socialize，鈕上寫跟誰說話）；福緣、留在交友的事件也走 act:socialize；沒有人可以說話時灰掉、寫原因、不扣體力。"""
    kind, arg = rules.social_plan(ctx)
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
    per_day = rules.talk_cap(ctx)
    opts = []
    for companion_id in ctx._figures_here():
        ch = c.characters[companion_id]
        option_id = f"call:{companion_id}"
        left = rules.talks_left(ctx, companion_id)
        if ctx._snubbed_character(companion_id):
            opts.append(Option(id=option_id, label=f"{ch.name}（{SNUB_NOTE}）", enabled=False))
        elif not rules.figure_can_meet(ctx, companion_id) and precise.on(c, ctx.state.world):  # 一類一顆（2.8）：不再打發
            if rules.meet_event(ctx, companion_id) is not None:
                opts.append(ctx._cost_option(option_id, ch.name, cost, note=AUDIENCE_MEET))
            else:
                opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {rules.fame_gap(ctx, companion_id)}）", enabled=False))
        elif not rules.figure_can_meet(ctx, companion_id):
            opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {rules.fame_gap(ctx, companion_id)}）"))  # 按下去走打發，見 brush_off
        elif left == 0:
            opts.append(Option(id=option_id, label=f"{ch.name}（{rules.talked_out_note(ctx)}）", enabled=False))
        else:
            opts.append(ctx._cost_option(option_id, ch.name, cost, note=f"還能談 {left}/{per_day} 輪"))
    opts.append(Option(id="call:back", label="返回"))
    return opts


def audience_intro(ctx) -> str:
    """求見畫面的說明（場景上的那一段）：挑一位拜會；每位人物各算各的，一個遊戲日最多談幾輪、什麼時候重新算起。"""
    here = ctx.content.locations[ctx.state.player.location].name
    per_day = rules.talk_cap(ctx)
    # 你跟這幾位的情誼（explain-1）：挑人之前看得到，跟談話時名字旁寫的是同一個數
    bonds = "、".join(f"{ctx.content.characters[cid].name} {ctx.state.player.affinities.get(cid, 0)}" for cid in ctx._figures_here())
    kind, moment = rules.talks_reopen(ctx)
    again = f"到 {moment} 重新算起" if moment else "過一陣子重新算起" if kind == "later" else "這一季之內不再重算"  # FB-102
    if precise.on(ctx.content, ctx.state.world):  # 一類一顆：求見併進交友，名望不夠的灰著寫還差多少，不打發（FB-421）
        head = SOCIAL_LIST_INTRO.format(here=here, per_day=per_day, again=again)
    else:
        head = f"{here}有好幾位人物，挑一位求見。每位人物各算各的，最多談 {per_day} 輪，{again}；名望不夠的會被打發。"
    return head + (f"\n\n你跟他們的情誼：{bonds}。" if bonds else "")
