"""懸賞榜的動作（原本 Game 上的 _bounty_options、_bounty、post_wanted、_raid_bounty 四個方法，與 _act 的 act:bounties、sync 的退押金與作廢、own_turn_checks 的系統通緝、
choose 的 FB-162、status_data 的懸賞卡；全部拆包第 45 批）。第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用 tianxia/core/services_list.md 那張清單上的。
規則照模組屬性叫（rules.take、rules.give……：測試與量表腳本換掉模組上的，這裡照樣打得到）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core.option import Option
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）
from tianxia.core import bounty_base  # 核心（榜的入口與收店：清失效參照那一格讀，core_seams）

from . import rules
from . import shop_view

if TYPE_CHECKING:
    from tianxia.engine import Game


def options(ctx: Game) -> list[Option]:
    """懸賞榜的第二層選單（rules.py）：交得出的求兵每張一顆「交出…」（按了到第三層挑一件；排最前面，當場就能交），
    手上的每一張一顆「放棄」，榜上其他看得到的每一張一顆「揭下」（揭不了的灰掉、寫為什麼），交不出的求兵收成一行灰掉的，
    最後是永遠按得下去的「返回」；上面全空（榜開著時單被別人交光）就多一行灰掉的 bounty:empty（FB-156）。都不花體力。列的是 rules.visible（別的陣營的、自己交過的不列），跟閒著的選單寫的張數一樣
    （灰掉那一行照它包含幾張算）。bounty_pick 指著一張還交得出的求兵時整份換成第三層（rules.hand_in_options）；
    那一張下榜了、交不出了就當它不存在，照第二層畫（懸賞榜設計 4.3、4.4）。"""
    s, c = ctx.state, ctx.content
    shown = rules.visible(s, c)
    picked = next((b for b in shown if b.id == s.player.bounty_pick and b.kind in rules.GIVE_KINDS), None)
    items = rules.fitting(s, c, ctx.world, picked) if picked is not None else []
    if items:
        return rules.hand_in_options(s, c, ctx.world, picked, items)
    mine = {b.id for b in rules.mine(s, c)}
    ready, opts, stuck = [], [], []
    for b in shown:
        if b.kind in rules.GIVE_KINDS:  # 求兵不用揭
            have = rules.fitting(s, c, ctx.world, b)
            if have:
                ready.append(Option(id=f"bounty:pick:{b.id}", label=rules.pick_label(s, c, b, len(have))))
            else:
                stuck.append(b)
            continue
        line = (f"{rules.issuer(c, b)}・{rules.title(c, b)}：{rules.how(c, b, ctx.state)}"
                f"（{rules.reward_text(s, c, b)}；{rules.due_line(s, c, b)}）")  # 期限與名額（FB-121 第 5 件）
        if b.id in mine:
            opts.append(Option(id=f"bounty:drop:{b.id}", label=f"放棄 {line}"))
            continue
        problem = rules.take_problem(s, c, b)
        opts.append(Option(id=f"bounty:take:{b.id}", label=f"揭下 {line}" + (f"（{problem}）" if problem else ""),
                           enabled=problem is None))
    if stuck:
        kept = {b.id: tail for b in stuck if (tail := rules.only_original(s, b))}  # 只有神器原品或本命兵器對得上的那幾張照實寫（FB-145）
        opts.append(Option(id="bounty:none", label=rules.stuck_label(c, stuck, kept), enabled=False))
    if not ready and not opts:  # 榜開著的時候，看得到的單被別人交光了：不能只剩「返回」（FB-156）
        opts.append(Option(id="bounty:empty", label=rules.BOARD_EMPTY, enabled=False))
    return ready + opts + [Option(id="bounty:back", label="返回")]


def bounty(ctx: Game, arg: str) -> list[str]:
    """懸賞榜上的選擇：揭下、放棄、交出…（到第三層挑一件）、回到懸賞榜、交出，或返回（收起懸賞榜）。做完榜還開著，可以接著挑。
    交出的 id 是「give:懸賞 id:東西 id」：兵器 id「兵:3」帶冒號，懸賞 id（b17）沒有，所以只切一次。"""
    s, c = ctx.state, ctx.content
    verb, _, rest = arg.partition(":")
    if verb == "back":
        rules.close_board(s.player)
        return ["你離開了懸賞榜。"]
    if verb == "take":
        b = next((x for x in rules.open_bounties(s, c) if x.id == rest), None)
        ctx._shop_after(rules.take_problem(s, c, b) if b is not None else rules.GONE, "take", shop_view.board_key)  # 1.4
        return rules.take(s, c, rest)
    if verb == "drop":
        msgs = rules.drop(s, c, rest)
        ctx._shop_say("refused" if msgs == [rules.NOT_HELD] else "drop")
        return msgs
    if verb == "pick":
        b = next((x for x in s.world.bounties if x.id == rest), None)
        if b is None:
            ctx._shop_say("refused")
            return [rules.GONE]
        s.player.bounty_pick = rest
        ctx._shop_say("pick")
        return [rules.pick_line(c, b)]
    if verb == "unpick":
        s.player.bounty_pick = None
        return [rules.UNPICKED]
    if verb == "give":
        bounty_id, _, item = rest.partition(":")
        msgs = rules.give(s, c, ctx.world, bounty_id, item)
        if msgs[0].startswith(rules.GIVEN_PREFIX):
            s.player.bounty_pick = None  # 交完回到第二層，可以接著交別張
            ctx._shop_say("give")
        else:
            ctx._shop_say("refused")
        return msgs
    return ["（此刻無法這麼做。）"]


def enter(ctx: Game) -> list[str]:
    """打開懸賞榜（見 options），不花體力；每次打開都從第二層開始（第三層是替一張求兵挑東西）。"""
    p = ctx.state.player
    p.picking_bounty, p.bounty_pick, p.shop_clue = True, None, ""
    ctx._shop_say("enter")  # 店面上榜吏那一句（店面獨立介面設計 1.4）
    return [f"你擠到{rules.BOARD}前，看上面貼了些什麼。"]


def post_wanted(ctx: Game, other: Game, amount: int) -> list[str]:
    """通緝 other（玩家卡的「通緝」）：押金從你身上扣、掛上懸賞榜（rules.post）；成了寫一則江湖紀錄、存季。"""
    msgs = rules.post(ctx.state, ctx.content, other.state, amount)
    if msgs and msgs[0].startswith("你押了"):
        ctx._write(rules.BOARD, msgs)
        ctx._save_season()
    return msgs


def raid_bounty(ctx: Game, target: str) -> list[str]:
    """截殺打贏、揭了通緝他的懸賞：交差（賞銀、散人的俠名），補進這一則江湖紀錄。"""
    msgs = ctx.publish("raid_win", target)  # 事件 raid_win（第 26 批）：通緝交差
    if msgs and ctx._draft is None:
        ctx._write(rules.BOARD, msgs)
    return msgs


def deliver(ctx: Game) -> None:
    """Game.sync 中段的那兩段（位置固定；deliver_* 不問 active，季收了也要退）。"""
    refunds = rules.deliver_refunds(ctx.state, ctx.content)  # 掛的通緝沒人揭成：押金退回
    if refunds:
        ctx._write(rules.BOARD, refunds)
        ctx._save_season()
    lapses = rules.deliver_lapses(ctx.state, ctx.content)  # 揭了的被別人交滿名額、或過了期限：拿掉名字、補一句（FB-121）
    if lapses:
        ctx._write(rules.BOARD, lapses)
        ctx._save_season()


def post_auto(ctx: Game) -> None:
    """Game.own_turn_checks 暫停那一道之後：系統通緝這一週還沒掛就掛（rules.post_auto，名聲 4.6、5.4），被掛的那幾句寫進一則紀錄。"""
    posted = rules.post_auto(ctx.state, ctx.content)
    if posted:
        ctx._write(rules.BOARD, posted)
        ctx._save_season()


def stale(ctx: Game, arg: str) -> list[str]:
    """FB-162：懸賞選項已經不在選單上（兩個分頁搶同一張，慢的那一頁）時回的那一句；Game.choose 原位包成 Refused（只讀，不改狀態、不寫紀錄）。"""
    return [rules.stale_line(ctx.state, ctx.content, ctx.world, arg)]


def status(ctx: Game) -> list[dict]:
    """Game.status_data 的 "bounties"：手上揭了的與身上有合用東西的求兵（rules.status）。"""
    return rules.status(ctx)


def drop_stale(ctx: Game) -> None:
    """stale.mid 的 bounties 那一格（core_seams，全部拆包第 55 批；照原位搬）：懸賞榜關了（Config.bounties.enabled、劇本沒有陣營）、人不在城鎮了：
    收起懸賞榜，挑到哪一張與榜吏那一句一併清掉。"""
    s, c = ctx.state, ctx.content
    if s.player.picking_bounty and not bounty_base.board_here(s, c):
        bounty_base.close_board(s.player)


def here_cell(ctx: Game, loc, cost, odds) -> list[Option]:
    """here/bounties 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：城鎮類的地點、有看得到的單才有（FB-121：張數只算看得到的，0 張不畫）；只是打開第二層選單，不花體力。"""
    s, c = ctx.state, ctx.content
    shown = bounty_base.visible(s, c) if bounty_base.board_here(s, c) else []
    return [Option(id="act:bounties", label=f"{bounty_base.BOARD}（{len(shown)} 張）")] if shown else []


def open_cell(ctx: Game) -> str | None:
    """open/bounties 那一格（core_seams，全部拆包第 56 批；原本在 Game._shop_open）：沒坐著是 None；坐著、這裡還開著是 board，不開門了是 ""（核心 or None）。"""
    s, c = ctx.state, ctx.content
    if not s.player.picking_bounty:
        return None
    return "board" if bounty_base.board_here(s, c) else ""


def travel_block(state, content) -> TravelBlock | None:
    """block/bounties 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字一字不動）。"""
    return TravelBlock("懸賞榜還開著，先離開才能安排前往", to_jianghu=True) if state.player.picking_bounty else None
