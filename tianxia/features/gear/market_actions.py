"""馬市（全部拆包第 42 批；裝備四欄設計 5.5）：第二層選單與選單上的選擇、進門。原本 Game 上的 2 個方法（_market_options、_market）加 _act 裡 act:market 的三行，
Game 留 _market 一行委派（測試叫；market_options 第 56 批起是 take/gear 那一格，委派拿掉）。choose 的 market: 由包的 choose 掛鉤接走（Outcome.run 叫 market）；
act:market 由包的 act 子動詞接走（enter）。選單開著與否（picking_market）、入口、收店不登記 Shop，留在 Game 原位（計畫 1.9）。
計畫 docs/superpowers/plans/2026-11-07-裝備包-第1批.md 1.1。第一個參數 ctx 是 Game（手冊 3.3）。
規則照模組屬性叫（mounts.buy、mounts.feed……：量表腳本換掉模組上的，這裡照樣打得到）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import equipment  # 共用規則層
from tianxia import mounts  # 共用規則層
from tianxia import territory  # 共用規則層
from tianxia.core.option import Option, Refused  # 核心
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）

if TYPE_CHECKING:
    from tianxia.engine import Game


def stale_cell(ctx: Game, option: Option | None, option_id: str) -> Refused | None:
    """stale/market 那一格（第二輪第 92 批；原本在 Game.choose 查完選單之後）。FB-195：馬市的選項已經不在選單上或灰掉了（兩個分頁搶，慢的那一頁的鈕還亮著）：
    同懸賞榜 FB-162，回為什麼不成的那一句（Refused，伺服器傳去網頁跳提示），馬販那一句換成那個原因；不寫江湖紀錄。"""
    if (option is None or not option.enabled) and option_id.startswith("market:"):
        problem = mounts.stale_problem(ctx.state, ctx.content, option_id.partition(":")[2])
        if ctx._shop_open() == "market":  # 已經出了馬市、進了別的店（另一個分頁）：不改那一間店掌櫃的話（終審 M1）
            ctx._shop_after(problem, "refused")
        return Refused(ctx._log([problem if problem == mounts.STALE else f"（{problem}。）"]))
    return None


def market_options(ctx: Game) -> list[Option]:
    """馬市的第二層選單（裝備四欄設計 5.5）：一顆「買」（駑馬下品，寫省幾成體力與價錢；買不了的灰掉寫為什麼），
    身上有馬時一顆「餵」（寫用哪一種素材；不餓、沒素材灰掉寫為什麼），裝備庫裡每一匹一顆「換上」，最後「離開」。都不花體力。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    item = mounts.shop_item(s, c)
    problem = mounts.buy_problem(s, c)
    note = problem or f"{mounts.price(s, c)} 兩{territory.price_note(s, c)}"  # 名聲 4.1：馬價後面寫原因
    # 三種鈕的寫法都待 joy 潤；飽足度這個叫法讀 mounts.WEAR_WORD，不寫死。網頁照 FB-132 把 market: 的鈕切成不折行的小段
    opts = [Option(id=mounts.BUY, enabled=problem is None,
                   label=f"買【{mounts.name_of(item)}】（{mounts.grade(item)}・疾行省 {mounts.pct(mounts.fresh_power(c, item))} 體力・{note}）")]
    if p.mount is not None:
        opts.append(Option(id=mounts.FEED, enabled=mounts.feed_problem(s, c) is None,
                           label=f"餵【{mounts.name_of(p.mount)}】（{mounts.WEAR_WORD} {p.mount.edge}・{mounts.feed_note(s, c)}）"))
    for m in equipment.in_slot(p, "mount"):
        opts.append(Option(id=f"{mounts.WIELD}{m.id}",
                           label=f"換上【{mounts.name_of(m)}】（{mounts.grade(m)}・{mounts.WEAR_WORD} {m.edge}）"))
    opts.append(Option(id=mounts.BACK, label=mounts.LEAVE))
    return opts


def market(ctx: Game, arg: str) -> list[str]:
    """馬市上的選擇：買、餵、換上，或離開（收起選單）。做完選單還開著，可以接著挑。店面上馬販那一句照這一下的擋法記（1.4）。"""
    s, c = ctx.state, ctx.content
    verb, _, rest = arg.partition(":")
    if verb == "back":
        mounts.close_market(s.player)
        return [mounts.LEFT]
    if verb == "buy":
        ctx._shop_after(mounts.buy_problem(s, c), "buy")
        return mounts.buy(s, c)
    if verb == "feed":
        ctx._shop_after(mounts.feed_problem(s, c), "feed")
        return mounts.feed(s, c)
    if verb == "wield":
        msgs = mounts.wield(s, c, rest)
        ctx._shop_say("wield" if msgs[0].startswith(equipment.WIELDED.partition("{")[0]) else "refused")
        return msgs
    return ["（此刻無法這麼做。）"]


def enter(ctx: Game) -> list[str]:
    """act:market（裝備包的 act 子動詞接走，原本是 Game._act 中段那幾行）：走進馬市。"""
    p = ctx.state.player
    p.picking_market, p.shop_clue = True, ""  # 打開馬市（見 market_options），不花體力
    ctx._shop_say("enter")  # 店面上馬販那一句（1.4）
    return [mounts.ENTERED]


def close_gone(ctx: Game) -> None:
    """sync.close、stale.mid 的 gear 那一格（core_seams，全部拆包第 55 批；原位兩處寫的是同一句）：坐騎關了、人不在馬市了（內容改版、管理者挪人）：
    收起馬市（裝備四欄 5.5），馬販那一句一併清掉。"""
    if ctx.state.player.picking_market and not mounts.market_here(ctx.state, ctx.content):
        mounts.close_market(ctx.state.player)


def here_cell(ctx: Game, loc, cost, odds) -> list[Option]:
    """here/gear 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：馬市（裝備四欄 5.5，帶「馬市」標籤的城鎮）：只是打開第二層選單，不花體力。"""
    return [Option(id="act:market", label=mounts.MARKET)] if mounts.market_here(ctx.state, ctx.content) else []


def open_cell(ctx: Game) -> str | None:
    """open/gear 那一格（core_seams，全部拆包第 56 批；原本在 Game._shop_open）：沒坐著是 None；坐著、這裡還開著是 market，不開門了是 ""（核心 or None）。"""
    s, c = ctx.state, ctx.content
    if not s.player.picking_market:
        return None
    return "market" if mounts.market_here(s, c) else ""


def travel_block(state, content) -> TravelBlock | None:
    """block/gear 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block；待 joy 潤的字在 mounts）。"""
    return TravelBlock(mounts.TRAVEL_BLOCKED, to_jianghu=True) if state.player.picking_market else None
