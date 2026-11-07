"""下戰書（功能包 territory_acts；全部拆包第 46 批）：今天是第幾天、下不了戰書的那一句、下戰書。原本 Game 上的 _letter_key、letter_problem、conquest_letter，
名字去掉前導底線、第一個參數是 ctx。會改狀態的只有 conquest_letter（MAIN_ACTIONS["conquest_letter"] 在這一包的 routes.py，全部拆包第 68 批）。
"""
from __future__ import annotations

from tianxia import conquest
from tianxia import ranks  # 共用規則層（階級 ranks，第 40 批收進）

from . import conquest_day

# 領地爭奪：戰書（翻地與爭搶，輿圖簡化設計 4.4；投票與 22:00 公告結算拿掉了，PM 2026-10-20）。待 joy 潤
LETTER_TITLE = "下戰書"
LETTER_DONE = "你替{side}下了戰書：{time} 攻{place}。這一塊的進度凍結到那一場打完。"
LETTER_JOINED = "你替{side}下了戰書，併進{time} 那一場：跟{others}同時攻{place}。"
LETTER_RANK = "只有這一週在任的第 4 階才能下戰書"
LETTER_NO_SLOT = "今明兩天都排不出攻城的時段"
CONQUEST_OFF = "這一季沒有攻城戰。"
CONQUEST_ENDED = "這一季已經收了。"


def letter_key(ctx) -> int:
    """今天是第幾天（conquest_day.day_key：當地 22:00 換天；一邊一天一張戰書照它算）。"""
    return conquest_day.day_key(ctx.pill_now(), ctx.content.config)

def letter_problem(ctx, loc: str) -> str | None:
    """下不了戰書的那一句（不含括號）；下得了是 None（設計 4.4、第九章第 13 條）：這一週在任的第 4 階（ranks.rank_of）、自己那一邊在這一塊的
    進度到 letter_at、這一塊推得動、這一邊今天還沒下過（conquest.letter_problem），排得出時段。假人不下（bot_policy 不按），規則本身不看。"""
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.conquest is None:
        return CONQUEST_OFF
    if w.ended:
        return CONQUEST_ENDED
    side = ctx._conquest_side()
    if side is None or ranks.rank_of(ctx.state) != ranks.SEAT_RANK:
        return LETTER_RANK
    if loc not in c.locations:
        return conquest.WHY_OUT
    problem = conquest.letter_problem(w, c, side, loc, letter_key(ctx))
    if problem is not None:
        return problem
    slot = conquest.frozen(w, loc)
    if slot is None and conquest_day.next_slot(w, c, ctx.pill_now()) is None:
        return LETTER_NO_SLOT
    return None

def conquest_letter(ctx, loc: str) -> list[str]:
    """下戰書（MAIN_ACTIONS["conquest_letter"]；輿圖的卡上那一顆，第 4 批畫）：照 conquest_day.place_letter 排一場攻城（最近的時段；同一塊
    別一邊下了、還沒開集結就併進那一場），那一塊凍結到打完。天下大事一句（具名）、江湖紀錄一則、存季。"""
    problem = letter_problem(ctx, loc)
    if problem is not None:
        return ctx._log([f"（{problem}。）"])
    c, w = ctx.content, ctx.state.world
    side = ctx._conquest_side()
    before = list(conquest.frozen(w, loc).attackers) if conquest.frozen(w, loc) is not None else []
    placed = conquest_day.place_letter(w, c, side, loc, ctx.state.player.name, ctx.pill_now())
    if placed is None:
        return ctx._log([f"（{LETTER_NO_SLOT}。）"])
    slot, _ = placed
    names = {f.id: f.name for f in c.scenario.factions}
    when, place = ctx.stamp(slot.at), c.locations[loc].name
    if before:
        line = LETTER_JOINED.format(side=names.get(side, side), time=when, others="、".join(names.get(a, a) for a in before), place=place)
    else:
        line = LETTER_DONE.format(side=names.get(side, side), time=when, place=place)
    ctx._write(LETTER_TITLE, [line])
    ctx._save_season()
    return ctx._log([line])
