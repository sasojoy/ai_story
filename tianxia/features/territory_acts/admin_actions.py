"""管理者救場工具（功能包 territory_acts；全部拆包第 46 批）：定一塊歸誰、定一塊的進度、立刻下戰書、取消一場攻城。原本 Game 上的 admin_conquest_set／progress／letter／cancel，
去掉 admin_conquest_、第一個參數是 ctx。會改狀態。路由是這一包的 admin_tools（op 名字照舊：conquest_set、conquest_progress、admin_conquest_letter、conquest_cancel；
立刻下戰書的 op 不准叫 conquest_letter，FB-609）。
"""
from __future__ import annotations

from tianxia import conquest, territory
from tianxia.world import check_thresholds

from . import conquest_day
from .letter_actions import CONQUEST_OFF


def conquest_set(ctx, loc_id: str, side: str | None) -> list[str]:
    """領地爭奪（第 38 項改版）：管理者把一塊改成某一軍的（side None 或空字串＝放回中立）。第一批沒有攻城戰，地圖只能靠這裡與時刻表
    指定易手動；易手的天下大事、江湖史、三條線的重算跟自然易手一樣（conquest.set_control）。只收搶得下來的區塊、官軍或黃巾。"""
    refusal = ctx._admin_refusal("定一塊歸誰")
    if refusal:
        return ctx._log(refusal)
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w):
        return ctx._log(["（這一季沒有開領地爭奪。）"])
    side = side or None
    if not conquest.capturable(c, loc_id):
        return ctx._log(["（這裡不是搶得下來的區塊：大本營、廣宗、不是區塊的地點都不收。）"])
    if side is not None and side not in conquest.SIDES:
        return ctx._log(["（只能定給官軍或黃巾。）"])
    before = territory.controller(w, c, loc_id)
    if before == side:
        return ctx._log(["（這一塊本來就是這樣。）"])
    conquest.set_control(w, c, loc_id, side)
    msgs = check_thresholds(ctx.state, c, ctx.world, ctx._flavor_sink(), now=ctx.now)
    name = c.locations[loc_id].name
    line = f"{name}改歸{c.scenario.faction_name(side, side)}。" if side else f"{name}放回中立。"  # 管理者看的，不是天下大事
    ctx._write("定一塊歸誰", [line] + msgs, tag="管理者")
    ctx._save_season()
    return ctx._log([line] + msgs)

def conquest_progress(ctx, loc_id: str, side: str, value: float) -> list[str]:
    """領地爭奪（救場，QA 用；翻地與爭搶）：直接把 side 在這一塊的那一條定成 value（0～100）；到 100 照推滿當場易手（分紅給這一輪推過的人、
    冷卻起算）。不看推不推得動、不記誰推的。只收搶得下來的區塊、劇本的陣營、而且不是此刻佔著的那一方。"""
    refusal = ctx._admin_refusal("定一塊的進度")
    if refusal:
        return ctx._log(refusal)
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.conquest is None or w.ended:
        return ctx._log([f"（{CONQUEST_OFF}）"])
    if not conquest.capturable(c, loc_id):
        return ctx._log(["（這裡不是搶得下來的區塊：大本營、廣宗、不是區塊的地點都不收。）"])
    if c.scenario.find_faction(side) is None or conquest.holder(w, c, loc_id) == side:
        return ctx._log(["（只能替不是此刻佔著的那一方定進度。）"])
    value = max(0.0, min(conquest.FULL, float(value)))
    fight = conquest._fight(w, c, loc_id)
    line = fight.bars.setdefault(side, conquest.Bar())
    line.value = value
    fight.last_push = w.time
    name = c.locations[loc_id].name
    msgs = [f"{name}：{c.scenario.faction_name(side, side)}的進度定成 {round(value)}。"]  # 管理者看的
    if value >= conquest.FULL:
        msgs += conquest.flip(w, c, loc_id, side)
        msgs += check_thresholds(ctx.state, c, ctx.world, ctx._flavor_sink(), now=ctx.now)
    elif value <= 0:
        fight.bars.pop(side, None)
    ctx._write("定一塊的進度", msgs, tag="管理者")
    ctx._save_season()
    return ctx._log(msgs)

def conquest_letter(ctx, loc_id: str, side: str) -> list[str]:
    """領地爭奪（救場，QA 用）：替 side 立刻對這一塊下一張戰書——不看階、門檻、一天一張，開打在「此刻＋集結」、集結馬上開（QA 不必等到下午）。
    同一塊別一邊下了、還沒開集結就併進那一場。天下大事照戰書寫、不寫管理者；不算進那一邊今天的那一張。"""
    refusal = ctx._admin_refusal("立刻下戰書")
    if refusal:
        return ctx._log(refusal)
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.conquest is None or w.ended:
        return ctx._log([f"（{CONQUEST_OFF}）"])
    if side not in conquest.SIDES or not conquest.capturable(c, loc_id) or conquest.holder(w, c, loc_id) == side:
        return ctx._log(["（只能替官軍或黃巾、對不是自己的、搶得下來的區塊下。）"])
    found = conquest.frozen(w, loc_id)
    if found is not None and (found.status == "open" or side in found.attackers):
        return ctx._log(["（這一塊已經有一場攻城了。）"])
    text = conquest_day.place_now(w, c, side, loc_id, ctx.pill_now())
    ctx._write("立刻下戰書", [text], tag="管理者")
    ctx._save_season()
    return ctx._log([text])

def conquest_cancel(ctx, slot_id: str) -> list[str]:
    """領地爭奪（救場）：取消一場攻城（照作罷處理：那一塊解凍、進度照留、天下大事一句，公告不寫管理者）；已經開了集結的那一場照決戰的
    取消收兵（不算勝負、不發軍餉、不易手）。"""
    refusal = ctx._admin_refusal("取消一場攻城")
    if refusal:
        return ctx._log(refusal)
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.conquest is None:
        return ctx._log([f"（{CONQUEST_OFF}）"])
    slot = next((s for s in w.conquest.schedule if s.id == slot_id), None)
    if slot is None or slot.status in ("done", "void"):
        return ctx._log(["（找不到這一場，或已經打完、作罷了。）"])
    text = conquest_day.VOID_CANCEL.format(who=conquest_day._names(c, slot.attackers), place=c.locations[slot.loc].name)
    if slot.status == "open" and slot.record_id is not None:
        ctx._cancel_siege(slot.record_id, text)
        w = ctx.state.world
        slot = next(s for s in w.conquest.schedule if s.id == slot_id)
    conquest_day.void(w, c, slot, text)
    ctx._write("取消一場攻城", [text], tag="管理者")
    ctx._save_season()
    return ctx._log([text])
