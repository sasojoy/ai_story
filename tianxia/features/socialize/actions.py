"""交友求見的動作（功能包 socialize；全部拆包第 21 批）：交友、指名求見、被打發、記一輪對話、福緣（結識奇遇）。原本 Game 上的 9 個方法
（含一類一顆與舊寫法兩套），名字去掉前導底線、第一個參數是 ctx。會改狀態。

對話（open_dialogue）、事件呈現（present）、引導提示（hint）、閉門不見（snubbed_character）都經 ctx，不 import 人物情誼包。
被測試換掉的 brush_off（tests/core/test_engine.py 換掉 Game._brush_off）一律經 ctx 叫才打得到。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tianxia import journal, precise, renown, roster
from tianxia.core.services import SNUB_NOTE
from tianxia import ranks  # 共用規則層（階級 ranks，第 40 批收進）
from tianxia.events import pick_event  # 過渡：待搬（事件：抽一則）
from tianxia.journal import Draft
from tianxia.rules import audience_hint, game_day, season_one

from . import view


def call_title(ctx, arg: str) -> str:
    """指名求見這一下江湖紀錄的標題（核心在動作之前先拿）。"""
    return "收回名帖" if arg == "back" else f"求見・{ctx.content.characters[arg].name}"


def open_audience(ctx) -> list[str]:
    """act:call：打開求見選單（見 menus.audience_options），不花體力（原本 Game._act 那一支，全部拆包第 57 批接進 Verb）。"""
    ctx.state.player.picking_audience = True
    return [f"你遞上名帖，準備求見{ctx.content.locations[ctx.state.player.location].name}的人物。"]


def press(ctx, prepared: Any) -> list[str]:
    """act:socialize 按下去（原本 Game._act 最後那一段，全部拆包第 57 批照原位的先後搬來；先後算行為）：先問召見、再扣體力；在召見的地點交友端出晉升奇遇（計畫 T5；
    一類一顆開著時不再換掉，正式季整合 2.10，應召照舊在「此地還能做」），這一支不排提示；其餘交友、第一次交友排一條「情誼有什麼用」（explain-1，碰到才說；說過就不再說，眼前有事件、對話時排著等）。
    ctx._socialize 經 Game 叫：tianxia/features/guide/tests/test_explain.py 換掉的是 Game 上的名字。"""
    promotion = ranks.summons_event(ctx.state, ctx.content)
    ctx.state.player.stamina -= ctx._action_costs()["socialize"]
    if promotion is not None and not precise.on(ctx.content, ctx.state.world):
        return ctx._present(ctx.content.events[promotion])
    msgs = ctx._socialize(prepared)
    ctx._hint("h_bond")
    return msgs


def socialize(ctx, prepared: Any = None) -> list[str]:
    """交友（act:socialize，體力呼叫端已經扣了）：福緣到了先發福緣；這裡至多一位人物、見得到就開口對話；不然抽一則
    這裡的交友事件，沒有就是打發話。一類一顆開著時照 social_plan（precise_socialize）。"""
    if precise.on(ctx.content, ctx.state.world):
        return precise_socialize(ctx, prepared)
    if roster.fortune_due(ctx.state, ctx.content):
        candidates = [cid for cid, ch in ctx.content.characters.items() if ch.kind == "recruitable"]
        if candidates and roster.owned_by(ctx.world, candidates[0]) is None:
            ctx.state.player.fortune = True
            cid = candidates[0]
            msgs = [f"你新立門戶不久，【{ctx.content.characters[cid].name}】主動前來結識。"]
            msgs += roster.recruit(ctx.state, ctx.content, ctx.world, cid)
            return msgs
        if ctx._draft is not None:
            ctx._draft.title, ctx._draft.tag = "福緣", "賀禮"
        return fortune_gift(ctx)
    companion_id = ctx._socialize_figure()
    if companion_id is not None:
        return ctx._open_dialogue(companion_id, prepared)
    return encounter(ctx, "socialize", lambda: no_audience_line(ctx))  # 惰性：抽到事件就不挑打發話、不白花亂數


def precise_socialize(ctx, prepared: Any) -> list[str]:
    """一類一顆的交友（正式季整合 2.8）：照 social_plan 做那一件事；沒有人可以說話（鈕是灰的，舊分頁按到）退回體力。"""
    s, c = ctx.state, ctx.content
    kind, arg = ctx._social_plan()
    if kind == "fortune":
        s.player.fortune = True
        cid = view.fortune_free(ctx)
        return [f"你新立門戶不久，【{c.characters[cid].name}】主動前來結識。"] + roster.recruit(s, c, ctx.world, cid)
    if kind == "once":
        return ctx._present(pick_event(s, c, "socialize", ctx.rng, "rare"), "socialize")
    if kind == "talk":
        return ctx._open_dialogue(arg, prepared)
    if kind == "meet":
        return ctx._present(view.meet_event(ctx), "socialize")
    s.player.stamina += c.config.action_cost["socialize"]
    if kind == "list":
        s.player.picking_audience = True
        return [f"你遞上名帖，準備求見{c.locations[s.player.location].name}的人物。"]
    return [f"{arg}。"]


def call(ctx, arg: str, prepared: Any = None) -> list[str]:
    """求見選單上的選擇：「返回」收起選單；選了一位人物就跟他開口對話，跟交友碰上人物時一模一樣——
    花交友的體力、生成不出對話就退回（見 Game._open_dialogue）。福緣不在這裡發：指名求見就是要見這個人
    （福緣照舊由交友先發，或到期自己送上門，見 deliver_fortune）。
    門檻不夠（名望與階級都不到、也沒結識過）就被打發：不花體力、不叫模型，見 brush_off。"""
    ctx.state.player.picking_audience = False
    if arg == "back":
        return ["你收回名帖，暫且不求見了。"]
    if not view.figure_can_meet(ctx, arg):
        if precise.on(ctx.content, ctx.state.world):  # 一類一顆（2.8）：不再打發；結識得到的走結識事件，見不到的在名單上是灰的
            event = view.meet_event(ctx, arg)
            if event is None:
                return [f"{view.why_not_talk(ctx, arg)}。"]
            ctx.state.player.stamina -= ctx.content.config.action_cost["socialize"]
            return ctx._present(event, "socialize")
        return ctx._brush_off(arg)
    ctx.state.player.stamina -= ctx.content.config.action_cost["socialize"]
    return ctx._open_dialogue(arg, prepared)


def brush_off(ctx, companion_id: str) -> list[str]:
    """門檻不夠時被打發（武學與成長設計 9.1）：他自己口吻的一句（內容沒寫就用通用的），附上還差多少。
    後面只在「第一季的規則開著（才有晉升）、真的有下一階可升（會升階的：第 4 階只是資格，不算）、而且升一階抵掉的點數補得上差距」時才提在他那個陣營再升一階。
    企劃者裁決 E4：門檻照 rank_of，在任的第 4 階才多抵一階；候缺的人下一步是席次（每週照貢獻輪替，不是被召去的晉升），
    照規則不許諾——next_rank_up 在第 3 階以上本來就是 None，這裡不用另外判斷。
    不叫模型、不花體力、不加情誼。"""
    s, c = ctx.state, ctx.content
    ctx._hint("h_snubbed")  # 第一次被名將打發（新手引導計畫三）：不看狀態，打發的當下排；在行動裡，說的話記在這一則
    ch = c.characters[companion_id]
    line = ctx.rng.choice(ch.brush_off) if ch.brush_off else f"{ch.name}連見都不見你，門口的人把你請了出去。"
    short = view.fame_gap(ctx, companion_id)
    figure = next((f for f in c.figures.values() if f.character == companion_id), None)
    hint = audience_hint(s, c, companion_id)  # 名聲 explain 開著時另寫門檻與每一項折抵（設計 6.3）
    p = s.player
    step = int(c.config.audience_rank_discount * renown.scale(s.world) + 0.5)  # 名聲 2.4：升一階抵的點數也乘季長倍數
    if (
        season_one(c, s.world)  # 規則沒開（beta 那一季）沒有人晉升
        and figure is not None and p.faction == figure.faction
        and short <= step  # 再升一階抵掉的點數補得上這個差距
        and ranks.next_rank_up(s, c) is not None  # 而且下一次晉升真的會升階：第 4 階只是資格（rank 停在 3、在任才降門檻），不許諾
    ):
        faction = c.scenario.faction_name(figure.faction, figure.faction)
        hint += f"，或在{faction}再升一階"
    return [f"{line}（{hint}）"]


def count_talk(ctx, companion_id: str) -> list[str]:
    """記一輪；這個遊戲日聊滿了就自動告辭，寫明什麼時候再來（待 joy 潤）。"""
    ctx.state.player.talks_today[companion_id] = [game_day(ctx.content, ctx.state.world), view.talks_used(ctx, companion_id) + 1]
    if view.talks_left(ctx, companion_id) > 0:
        return []
    ctx.state.player.pending_companion = None
    name, (kind, moment) = ctx.content.characters[companion_id].name, view.talks_reopen(ctx)
    if kind == "later":
        return [f"{name}起身送客，改日再敘：過一陣子再來拜會吧。"]  # FB-102，待 joy 潤
    if moment is None:
        return [f"{name}起身送客：這一季之內不能再來拜會了。"]
    return [f"{name}起身送客，改日再敘：要到 {moment} 之後才能再來拜會。"]


def fortune_gift(ctx) -> list[str]:
    p = ctx.state.player
    amount = ctx.content.config.recruit_consolation_xinde
    p.fortune = True
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    return ["江湖朋友聽說你新立門戶，送來一份賀禮。", f"心得 +{amount}"]


def deliver_fortune(ctx) -> list[str]:
    s, c = ctx.state, ctx.content
    s.player.fortune = True
    candidates = [cid for cid, ch in c.characters.items() if ch.kind == "recruitable"]
    free = [cid for cid in candidates if roster.owned_by(ctx.world, cid) is None]
    if not free and precise.on(c, s.world):  # 一類一顆（2.8【PM】）：沒有同伴可給時不再送 30 心得
        return []
    if not free:
        msgs = fortune_gift(ctx)
        ctx._write("福緣", msgs, tag="賀禮")
        return msgs
    cid = free[0]
    msgs = roster.recruit(s, c, ctx.world, cid)
    journal.add_entry(s, Draft(f"結識【{c.characters[cid].name}】", "福緣").entry(s.world.time, msgs))
    return msgs


def encounter(ctx, action: str, nothing: str | Callable[[], str]) -> list[str]:
    """交友沒碰上人物時：抽一則事件，沒有就是 nothing（探索另有三選一，見 Game._explore）。
    nothing 可以是函式：真的用到才呼叫（打發話要挑一句，不該在抽到事件時白花一次亂數）。"""
    event = pick_event(ctx.state, ctx.content, action, ctx.rng)
    if event:
        return ctx._present(event, action)
    return [nothing() if callable(nothing) else nothing]


def no_audience_line(ctx) -> str:
    """交友時見不到這裡的大勢人物時的說明；這裡沒有大勢人物就是原本的「此地無人可訪」；
    兩位以上大勢人物的地點交友不找人，提醒要按「求見」。"""
    if view.audience_hall(ctx):
        return "你四處結交了一番，沒遇上什麼事；想拜會此地的人物，請按「求見」指名。"
    for companion_id in ctx._figures_here():
        ch = ctx.content.characters[companion_id]
        if ctx._snubbed_character(companion_id):
            return f"{ch.name}{SNUB_NOTE}。"
        if not view.figure_can_meet(ctx, companion_id):
            return ctx._brush_off(companion_id)[0]  # 交友時遇上見不到的人物，用求見同一套打發的話
        if view.talks_left(ctx, companion_id) == 0:  # 這個遊戲日談滿了：寫換日的那一刻（待 joy 潤）
            kind, moment = view.talks_reopen(ctx)
            if kind == "later":
                return f"{ch.name}事忙，過一陣子才得空。"  # FB-102，待 joy 潤
            return f"{ch.name}事忙，要到 {moment} 之後才得空。" if moment else f"{ch.name}事忙，這一季之內都不得空。"
    return "此地無人可訪，你只好悻悻離去。"


def fortune_due(ctx) -> list[str] | None:
    """local 的 fortune 那一格（core_seams，全部拆包第 55 批；原位的判斷搬過來）：福緣到期自己送上門（回的那幾句接進補算的回話）。"""
    if roster.fortune_overdue(ctx.state, ctx.content):
        return deliver_fortune(ctx)
    return None
