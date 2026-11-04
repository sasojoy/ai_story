"""管理者的軍令與召見（功能包 military；全部拆包第 33 批）：立刻發本週軍令、立刻輪替第 4 階席次、立刻替人發召見（與管理者玩家選單共用的召見規劃）。
原本 Game 上的 4 個方法（admin_issue_orders、admin_rotate_seats、_summons_plan、admin_summon）與回話用的五個常數；名字去掉前導的 admin_ 與底線。
第一個參數是 ctx。會改狀態。路由（/api/admin 的 issue_orders、rotate_seats、summon 三顆鈕）照舊在 server.py 叫 Game 的委派。
"""
from __future__ import annotations

from tianxia import allied, calendar, gender, seats
from tianxia import orders, ranks  # 過渡：待搬（軍令 orders、階級 ranks，總表第 40 批收共用規則層）
from tianxia.core.services import NO_SUCH_PLAYER
from tianxia.models import PromotionDef
from tianxia.rules import season_one

# 管理者「立刻發軍令」的回話照軍令多久一道（orders.daily：照週一發、每天 00:00 發；FB-502，待 joy 潤）
ADMIN_REISSUE_HOW = {False: "週一", True: " 00:00 "}  # 「已照週一的做法重發」「已照 00:00 的做法重發」
ADMIN_REISSUE_NONE = {False: "這一週沒有要重挑的軍令", True: "今天沒有要重挑的軍令"}
# 管理者「立刻輪替第 4 階席次」的回話：7 天濃縮季照段（calendar.week7_on；FB-503，待 joy 潤）
ADMIN_ROTATE_FIRST = {
    False: "（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）",
    True: "（第 1 段沒有上一段的貢獻可排；空缺照常由有資格的人補上。）",
}
ADMIN_ROTATE_AGAIN = {False: "下週一照常再排", True: "下一段第一天 00:00 照常再排"}
ADMIN_ROTATE_LAST = "這是最後一段，季末之前不再排"  # 7 天濃縮季的最後一段沒有下一段


def issue_orders(ctx) -> list[str]:
    """立刻發本週軍令：這一週還沒達成的軍令換成照週一的做法（orders.issue，週一掛鉤用的同一個函式，redraw）此刻重新挑的一批，
    各陣營照常發「本週軍令：…」的陣營軍情。換掉的那幾道進度不算了；已經達成的原封不動、不會再達成一次（審查 I-1：重挑的 id
    是決定性的，不留著的話同一道會達成兩次、效果套兩次）。不動 hooked_week：下週一照常發令。"""
    refusal = ctx._admin_refusal(f"發{calendar.week_word('order_this', ctx.content, ctx.state.world)}軍令")
    if refusal:
        return ctx._log(refusal)
    s, c = ctx.state, ctx.content
    if not orders.active(s, c):
        return ctx._log(["（這一季沒有軍令。）"])
    week = orders.period_of(s, c)  # 21 天季是季曆第幾天（每天一期）
    daily = orders.daily(s, c)
    replaced = sum(1 for o in s.world.orders if o.week == week and not o.done)
    kept = {o.id for o in s.world.orders if o.week == week and o.done}
    if daily:
        orders.issue_day(s, c, week, ctx.rng, redraw=True)
    else:
        orders.issue(s, c, week, ctx.rng, redraw=True)
    ctx._save_season()
    issued = [o for o in s.world.orders if o.week == week and o.id not in kept]
    listing = "；".join(
        f"{f.name}：{'、'.join(orders.title(c, o) for o in issued if o.faction == f.id)}"
        for f in c.scenario.factions if any(o.faction == f.id for o in issued)
    ) or ADMIN_REISSUE_NONE[daily]
    label = f"第 {week} 天" if daily else f"第 {week} 週"
    msg = (f"已照{ADMIN_REISSUE_HOW[daily]}的做法重發{label}的軍令，換掉沒達成的 {replaced} 道（進度不算了；已達成的 {len(kept)} 道照舊）"
           f"——{listing}。")
    ctx._write("重發軍令", [msg], tag="管理者")
    return ctx._log([msg])


def rotate_seats(ctx) -> list[str]:
    """立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情（seats.rotate，週一掛鉤用的同一個函式）。
    不動 hooked_week：下週一照常再排。賽季時鐘暫停中不排（_admin_refusal；自然的路暫停時也不補缺、不輪替）；
    第 1 週沒有上一週可排（seats.rotate 自己也什麼都不做），說一聲。"""
    refusal = ctx._admin_refusal("輪替第 4 階席次")
    if refusal:
        return ctx._log(refusal)
    s, c = ctx.state, ctx.content
    if not season_one(c, s.world):
        return ctx._log(["（這一季沒有第 4 階席次。）"])
    week = calendar.point(s.world.time, c, s.world).week
    segments = calendar.week7_on(s.world, c)  # 7 天濃縮季照段寫（FB-503，待 joy 潤）
    if week < 2:
        return ctx._log([ADMIN_ROTATE_FIRST[segments]])
    seats.rotate(s, c, week)
    ctx._save_season()
    held = s.world.seats
    listing = "；".join(
        f"{f.name}{ranks.TITLES[f.id][seats.SEAT_RANK]}：{'、'.join(held.get(f.id, [])) or '沒有人'}"
        for f in c.scenario.factions if f.id in s.world.seat_ledger and f.id in ranks.TITLES
    ) or "帳上還沒有人有第 4 階的資格"
    last = segments and week >= len(c.config.season_segments)
    again = ADMIN_ROTATE_LAST if last else ADMIN_ROTATE_AGAIN[segments]
    msg = f"已照{calendar.week_label(week - 1, c, s.world)}的貢獻輪替第 4 階席次（{again}）——{listing}。"
    ctx._write("輪替席次", [msg], tag="管理者")
    return ctx._log([msg])


def summons_plan(ctx, target) -> tuple[str | None, PromotionDef | None]:
    """「立刻替他發召見」：（拒絕的原因, 要發的那一階）。發的是下一階（rank_of + 1）；不看貢獻門檻、也不看那一階的機緣做了沒
    （控制者裁決：測試要跳過的就是這兩樣）。散人、手上已經有召見、已經取得第 4 階資格、到頂、第 3、4 階第一段此刻沒有人能出面
    （企劃者裁決 E3 那一句的情況），都不發。"""
    s, c, p = target.state, ctx.content, target.state.player
    if p.faction is None:
        return f"（{p.name}是散人，沒有陣營可以召見{gender.pronoun(p)}。）", None
    if p.summons is not None:
        return f"（{p.name}手上已經有一張第 {p.summons.rank} 階的召見了。）", None
    if p.qualified:
        return f"（{p.name}已經取得第 {ranks.SEAT_RANK} 階的資格了。）", None
    promo = ranks.promotion_for(c, p.faction, ranks.rank_of(s) + 1)
    cap = allied.rank_cap(s, c)  # 豪強分屬兩軍：豪強第 3 階就到頂
    if promo is None or (cap is not None and promo.rank > cap):
        return f"（{p.name}已經升到頂了。）", None
    if promo.legs and ranks.current_cast(s, c, promo, 0, None) is None:
        line = ranks.NO_PRESENTER.get(p.faction, ranks.NO_PRESENTER["guan"])
        return f"（第 {promo.rank} 階此刻沒有人能出面召見{p.name}：{line}）", None
    return None, promo


def summon(ctx, name: str) -> list[str]:
    """立刻替他發召見：下一階的召見照 ranks.issue_summons（check_summons 過了門檻之後的同一條：召見地點、出面的人、摸清路、那一句），
    第 3、4 階從第一段起。他的江湖紀錄記一則「召見」（同步時發的召見也是這個標題）。"""
    refusal = ctx._admin_refusal("發召見")
    if refusal:
        return ctx._log(refusal)
    if not season_one(ctx.content, ctx.state.world):
        return ctx._log(["（這一季沒有陣營的階級，發不了召見。）"])
    target = ctx._admin_target(name)
    if target is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=name.strip())])
    why, promo = summons_plan(ctx, target)
    lines = [] if promo is None else ranks.issue_summons(target.state, ctx.content, promo)
    if lines:
        target._write("召見", lines)  # 同步時自然發的召見也是這個標題；不標管理者（審查 M-1）
    ctx._save_target(target)
    if why is not None:
        return ctx._log([why])
    msg = f"已替{target.state.player.name}發第 {promo.rank} 階的召見：{lines[0]}"
    ctx._write("發召見", [msg], tag="管理者")
    return ctx._log([msg])
