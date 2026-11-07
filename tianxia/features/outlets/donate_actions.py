"""捐軍備（大本營的軍需官那一串）：捐素材、記貢獻與軍備存量、推大本營那一條線，與江湖頁的陣營軍備存量。
原本 Game 上的 9 個方法（_donate_option、_donate_options、_donate_choice、donate、donate_items、_donate、_credit_donation、can_donate_here、
armament_view；全部拆包第 43 批搬進來，行為一個字不變）；Game 留一行委派。第一個參數都是 ctx（Game）。銀兩出口的捐銀兩
（silver_actions.silver_donate）也走這裡的 credit。
"""
from __future__ import annotations

from tianxia import calendar, economy, equipment, journal, materials, wins
from tianxia.core import shop_base
from tianxia.core.option import Option
from tianxia.journal import Draft
from tianxia.rules import season_one


def can_donate_here(ctx) -> bool:
    """這一下捐得了軍備嗎（人在自家大本營、閒著或軍需官那一串開著）：Game.donate 收不收的同一個判斷，機器人照它。"""
    return ctx._at_own_base() and (ctx._idle() or ctx.state.player.picking_donate)


def donate_option(ctx) -> Option | None:
    """大本營「此地還能做」裡的「捐軍備（今天還能捐 N 點）」：只是打開軍需官那一串（不花體力）；今天捐滿了灰掉寫什麼時候再來。"""
    if not ctx._at_own_base():
        return None
    room = economy.donate_room(ctx.state, ctx.content, ctx._pill_day())
    if room <= 0:
        full = economy.DONATE_FULL.format(cap=ctx.content.config.economy.donate_daily_cap)
        return Option(id="act:donate", label=f"{economy.DONATE_TITLE}（{full}）", enabled=False)
    return Option(id="act:donate", label=f"{economy.DONATE_TITLE}（{economy.DONATE_LEFT.format(n=room)}）")


def donate_options(ctx) -> list[Option]:
    """軍需官那一串（店面關著、整季機器人與假人看的選單）：背包裡每一種素材一顆「捐這一種收得下的全部」（donate:<素材>:<個數>，
    寫份量與進哪一樣軍備；一個都收不下的灰掉寫為什麼），最上面一行灰字寫今天還能捐幾點，最後「離開」。都不花體力。"""
    s, c = ctx.state, ctx.content
    day = ctx._pill_day()
    room = economy.donate_room(s, c, day)
    opts = [Option(id="donate:room", label=economy.DONATE_LEFT.format(n=room), enabled=False)]
    # 一階排最前面（最該捐的）、三階排最後（要留著打神器，免得一按就捐掉）；同階照剛柔快慢
    held_by_tier = sorted(materials.bag_contents(s, c), key=lambda pair: (pair[0].tier, shop_base.attribute_rank(pair[0].attribute)))
    for material, held in held_by_tier:
        if economy.donate_points(c, material.id) <= 0:
            continue
        problem = economy.donate_problem(s, c, material.id, day)
        if problem is not None:
            opts.append(Option(id=f"donate:{material.id}:0", enabled=False,
                               label=economy.DONATE_REFUSED.format(name=material.name, problem=problem)))
            continue
        n = economy.donate_take(s, c, material.id, held, day)
        armament = economy.armament_of(c, material.attribute) or economy.DONATE_MISC
        opts.append(Option(id=f"donate:{material.id}:{n}", label=economy.DONATE_BUTTON.format(
            name=material.name, n=n, points=n * economy.donate_points(c, material.id), armament=armament)))
    return opts + [Option(id="donate:back", label=economy.DONATE_BACK)]


def donate_choice(ctx, arg: str) -> list[str]:
    """軍需官那一串上的選擇：donate:back 收起；donate:<素材>:<個數> 捐（_donate）。選單還開著，可以接著捐。"""
    if arg == "back":
        economy.close_donate(ctx.state)
        return [economy.DONATE_CLOSED]
    mid, _, count = arg.rpartition(":")
    return take(ctx, [(mid, int(count) if count.isdecimal() else 0)])


def donate(ctx, mid: str, count: int) -> list[str]:
    """捐一種素材 count 個（MAIN_ACTIONS["donate"]；整季機器人與假人也走它）：見 donate_items。"""
    return donate_items(ctx, [(str(mid), int(count))])


def donate_items(ctx, items: list[tuple[str, int]]) -> list[str]:
    """捐軍備（MAIN_ACTIONS["donate"]，軍需帳那一頁一次送挑好的幾種）：人在自家大本營、閒著（或軍需官那一串開著）才收。
    捐成了寫一則「捐軍備」紀錄（幾種一起捐也是一則）；一樣都沒收下的什麼都不動、不寫紀錄。"""
    s = ctx.state
    if not can_donate_here(ctx):
        return ctx._log([equipment.NOT_NOW])
    p = s.player
    here = ctx.content.locations[p.location].name
    before = (p.donate_day, p.donated_today)
    msgs = take(ctx, [(str(mid), int(count)) for mid, count in items])
    if (p.donate_day, p.donated_today) != before:  # 真的收下了
        journal.add_entry(s, Draft(f"{economy.DONATE_TITLE}・{here}").entry(s.world.time, msgs))
        ctx._save_season()
    return ctx._log(msgs)


def take(ctx, items: list[tuple[str, int]]) -> list[str]:
    """收下（設計第六節）：每一種照 economy.take_donation 扣背包、記今天的點數（上限切一半：收得下的收，其餘留著），照給的先後收；
    軍備存量照份量累積（economy.add_armament）；第一季規則開著時記貢獻（push.add_contribution，照份量）；推大本營那一條線（
    economy.donate_target）往自己陣營，量是 economy.donate_push（每點 0.05、事件五折），走 push_trend(source="donate")：季長倍數、
    盡頭阻力、每人每日上限照出陣，推力不另記貢獻（幾種一起捐也只推一次，照合起來的點數）。一樣都沒收下回第一個原因、什麼都不動。
    軍需帳上掌櫃那一句照這一下（_shop_after）。"""
    s, c = ctx.state, ctx.content
    p, w = s.player, s.world
    day = ctx._pill_day()
    if not ctx._at_own_base():
        return [equipment.NOT_NOW]
    took: list[tuple[str, int, int]] = []  # (素材, 收下幾個, 幾點)
    kept: list[str] = []
    refused: list[str] = []
    for mid, count in items:
        problem = economy.donate_problem(s, c, mid, day)
        if problem is not None:
            refused.append(problem)
            continue
        wanted = max(0, min(count, materials.held(s, mid)))
        points = economy.take_donation(s, c, mid, wanted, day)
        if points <= 0:
            refused.append(economy.DONATE_TOO_BIG.format(points=economy.donate_points(c, mid), room=economy.donate_room(s, c, day)))
            continue
        taken = points // economy.donate_points(c, mid)
        took.append((mid, taken, points))
        if taken < wanted:
            kept.append(economy.DONATE_KEPT.format(n=wanted - taken, name=c.materials[mid].name))
    if not took:
        problem = refused[0] if refused else economy.DONATE_NONE
        ctx._shop_after(problem, "donate")
        return [problem]
    faction = c.scenario.faction(ctx._side())
    items_text = "、".join(materials.item_text(c, mid, taken) for mid, taken, _ in took)
    msgs = [economy.DONATE_DONE.format(items=items_text, faction=faction.name)]
    by_attribute: dict[str, int] = {}
    for mid, _, points in took:
        attribute = c.materials[mid].attribute
        by_attribute[attribute] = by_attribute.get(attribute, 0) + points
    msgs += credit(ctx, by_attribute)
    ctx._shop_after(None, "donate")
    return msgs + kept


def credit(ctx, by_attribute: dict[str, int]) -> list[str]:
    """捐軍備收下之後（捐素材、捐銀兩共用）：軍備存量照份量累積（economy.add_armament）；第一季規則開著時記貢獻（照份量）；
    推大本營那一條線（economy.donate_target），量是 economy.donate_push，走 push_trend(source="donate")。"""
    s, c = ctx.state, ctx.content
    p, w = s.player, s.world
    side = ctx._side()  # 豪強分屬兩軍：軍備進依附那一軍的存量、推依附那一軍的目標（設計第六、十二節）
    msgs: list[str] = []
    for attribute, points in by_attribute.items():
        armament = economy.armament_of(c, attribute)
        if armament is not None:
            economy.add_armament(w, side, attribute, points)
            msgs.append(f"{armament} +{points}")
    total = sum(by_attribute.values())
    if season_one(c, w):  # 晉升只在第一季的規則下有：規則關著的季只記軍備
        wins.credit(p, c, w, calendar.point(w.time, c, w).week, total)  # 豪強另記此刻幫的那一軍那一本（減法季批 3c）
        msgs.append(f"貢獻 +{total}")
    target = economy.donate_target(c, w, side, p.location)
    if target is not None:
        trend_id, direction = target
        msgs += ctx.push_trend(trend_id, economy.donate_push(c, total) * direction, source="donate")
    return msgs


def armament_view(ctx) -> dict | None:
    """江湖頁的陣營軍備存量（設計第六節第 3 點；status_data["armament"]）：投靠了陣營、捐軍備開著才有。
    {"faction": 陣營名, "stock": [{"name": 糧秣, "attribute": 慢, "points": n}, …]}，照 Config.economy.armaments 的順序（沒捐過的是 0）。
    在決戰怎麼起作用還沒定（第 2 塊），這裡只給存量。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not c.config.economy.donate or p.faction is None:
        return None
    side = ctx._side()  # 豪強分屬兩軍：看依附那一軍的存量
    stock = s.world.armaments.get(side, {})
    return {
        "faction": c.scenario.faction_name(side, side),
        "stock": [{"name": name, "attribute": attribute, "points": stock.get(attribute, 0)}
                  for attribute, name in c.config.economy.armaments.items()],
    }


def here_cell(ctx, loc, cost, odds) -> list[Option]:
    """here/donate 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：大本營的捐軍備那一顆，這裡沒有是空的。"""
    donate = donate_option(ctx)
    return [] if donate is None else [donate]
