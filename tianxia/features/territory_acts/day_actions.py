"""22:00 換天與分紅補送（功能包 territory_acts；全部拆包第 46 批）：換天的掛鉤（前一天沒開成的攻城作罷、〈天下形勢〉開單）、翻地分紅與守城功送到。原本 Game 上的
_conquest_tick、_deliver_conquest，名字去掉前導底線、第一個參數是 ctx。**沒有接世界層的掛鉤**：Game.sync、world_tick、advance 三個地方把它排在別的結算之間，
順序就是行為（計畫 Review Focus 2），所以 engine 三處（五個呼叫）照舊叫 Game 上的委派。
"""
from __future__ import annotations

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import conquest, renown
from tianxia import team
from tianxia.characters import name_key

from . import conquest_day, xingshi_actions

CONQUEST_PAY_TITLE = "攻下{place}"  # 分紅送到的那一則江湖紀錄（Game._deliver_conquest）
CONQUEST_GUARD_TITLE = "守住{place}"
CONQUEST_PAY_LINE = "{place}易手，你這一輪替{side}出了 {pct}% 的力，分得："
CONQUEST_GUARD_LINE = "{place}守住了，你這一輪替{side}拉回 {pct}% 的進度，分得守城功："
CONQUEST_TOP_ANNAL = "率先攻入{place}"  # 行狀（annals.CONQUER）
CONQUEST_TOP_GUARD_ANNAL = "力保{place}不失"


def conquest_tick(ctx, save: bool = True) -> list[str]:
    """領地爭奪：換天（當地 22:00，conquest_day.day_key 照 pill_now）的掛鉤——前幾天排的、到現在還沒開集結的攻城作罷（conquest_day.day_turn），
    收場的攻城戰從共用狀態拿掉。第一個看到新的一天的人觸發（sync、伺服器的排程 world_tick、快轉 advance 都叫）；**日子只准往前走**
    （ConquestState.settled_key，同 arena.roll_day 的教訓：快轉過的 Game 與照現實時間的 Game 輪流同步不重排、不倒退）。這一季第一次只記下今天。
    開關關著、季收了、暫停中什麼都不做（不碰 WorldState）。save 是假時不存季（advance 自己存）。
    第三批 A〈天下形勢〉（開著時，xingshi.on）：一開頭先看還在等模型的那一張單過了 grace_seconds 沒有（照固定段收，季收了也收）；
    第一次只記下起點（_xingshi_start），之後每一次換天（day_turn）之後開一張新的（_xingshi_open）。"""
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.conquest is None:
        return []
    late = xingshi_actions.grace(ctx)  # 沒人上線也收得掉：伺服器排程的 world_tick 也走這裡
    key = conquest_day.day_key(ctx.pill_now(), c.config)
    if w.ended or key <= w.conquest.settled_key or ctx.world.paused_at() is not None:
        if late and save:
            ctx._save_season()
        return []
    if w.conquest.settled_key < 0:
        w.conquest.settled_key, msgs = key, []
        xingshi_actions.start(ctx)
    else:
        msgs = conquest_day.day_turn(w, c, key)
        for done in [b for b in ctx.world.get_sieges() if b.phase == "ended"]:  # 收場的攻城戰留到這時才從共用狀態拿掉
            ctx.world.drop_siege(done.record_id)
        xingshi_actions.open_ticket(ctx, key)
    if save:
        ctx._save_season()
    return msgs

def deliver_conquest(ctx) -> None:
    """翻地的分紅送到（輿圖簡化設計 4.5；conquest._payout 記在 ConquestState.payouts）：自己同步（與快轉）時拿走自己的那幾筆——銀兩、經驗
    （只給本人；滿級照 5 換 1 換成心得，同決戰軍餉）、名望（renown.gain）；推（拉）最多的那一個記一筆行狀（annals.CONQUER）。一筆一則江湖紀錄。
    下線的人回來照樣拿得到。沒有自己的什麼都不做（不碰共用賽季）。"""
    s, c = ctx.state, ctx.content
    state = s.world.conquest
    if state is None or not state.payouts:
        return
    me = name_key(s.player.name)
    mine = [pay for pay in state.payouts if name_key(pay.name) == me]
    if not mine:
        return
    state.payouts = [pay for pay in state.payouts if name_key(pay.name) != me]
    p = s.player
    names = {f.id: f.name for f in c.scenario.factions}
    # 出陣回報：最新一則就是推滿（拉回歸零）那一下出陣的話，分紅那一則接著畫同一塊——不然一同步「剛剛」就換成分紅、看不到易手那一條
    last = s.journal[0].front if s.journal else None
    for pay in mine:
        place = c.locations[pay.loc].name if pay.loc in c.locations else pay.loc
        side = names.get(pay.side, pay.side)
        head = (CONQUEST_PAY_LINE if pay.kind == "take" else CONQUEST_GUARD_LINE).format(place=place, side=side, pct=round(pay.share * 100))
        lines: list[str] = [head]
        if pay.silver:
            p.stats["silver"] = p.stats.get("silver", 0) + pay.silver
            lines.append(f"銀兩 +{pay.silver}")
        if pay.exp and team.maxed(c, p.member):
            gained = team.maxed_xinde(s, c, pay.exp, "dividend")
            if gained:
                lines += [team.MAXED_XINDE.format(n=gained), f"心得 +{gained}"]
        elif pay.exp:  # 翻地分紅算仗（地是打下來的，growth.BATTLE_KINDS）
            before = p.member.level
            lines.append(f"經驗 +{pay.exp}")
            lines += team.add_exp(c, p.member, pay.exp, p.name, "dividend")
            if p.member.level > before:
                points = team.level_points(ctx.state, c, before, p.member.level)
                p.stat_points += points
                if points:
                    lines.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
        if pay.fame:
            lines += renown.gain(s, c, "fame", pay.fame)
        if pay.top:
            text = (CONQUEST_TOP_ANNAL if pay.kind == "take" else CONQUEST_TOP_GUARD_ANNAL).format(place=place)
            annals.note(s, c, annals.CONQUER, text, 4, place=place, time=pay.time)
        ctx._write((CONQUEST_PAY_TITLE if pay.kind == "take" else CONQUEST_GUARD_TITLE).format(place=place), lines)
        if last is not None and last.loc == pay.loc:
            s.journal[0].front = last
    ctx._save_season()
