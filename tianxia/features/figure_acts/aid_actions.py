"""護衛、犒軍、探望的動作（功能包 figure_acts；全部拆包第 31 批）：選單那幾顆（護著同陣營的大勢人物）、按下去（aid:guard／rally／visit:<人物>）、
同步時補護衛擋下挑戰的名望與心得。原本 Game 上的 3 個方法，名字去掉前導底線、第一個參數是 ctx。會改狀態。規則在同包的 figure_aid.py。

`aid:` 的 choose 接掛鉤（標題一起給，在動作之前拿）；`options` 與 `deliver_guard_credits` 的位置算行為（選單末段護衛這一串在包選項之前、同步時夾在
_deliver_echoes 與 deliver_notices 之間），所以 Game 留一行委派原位叫。
"""
from __future__ import annotations

from tianxia import bounties  # 過渡：待搬（懸賞 bounties）
from tianxia import calendar, renown, wins
from tianxia import figures  # 共用規則層（大勢人物 figures，第 40 批收進）
from tianxia.core.option import Option
from tianxia.rules import season_one

from . import figure_aid


def options(ctx) -> list[Option]:
    """護著同陣營的大勢人物（figure_aid）：這裡在場的同陣營人物各一顆護衛、一顆犒軍；在自己陣營的大本營，被挑戰打退、
    還在等回來的人物各一顆探望。按不下去的灰掉寫原因。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not figure_aid.on(c) or p.faction is None or p.journey is not None:
        return []
    cfg = c.config.figure_aid
    side = ctx._side()
    opts: list[Option] = []
    for fid in figures.present_at(s, c, p.location):
        fig = c.figures[fid]
        if fig.faction != side:
            continue
        post = figure_aid.guarding(s, c, p.name, fid)
        if post is not None:
            opts.append(Option(id=f"aid:guard:{fid}", enabled=False,
                               label=figure_aid.GUARD_ON_LABEL.format(name=fig.name, until=ctx.stamp(post.until))))
        else:
            label = figure_aid.GUARD_LABEL.format(name=fig.name)
            problem = figure_aid.guard_problem(s, c, fid)
            opts.append(Option(id=f"aid:guard:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                        else ctx._cost_option(f"aid:guard:{fid}", label, cfg.guard_stamina))
        now = figures.state_of(s, c, fid)
        label = figure_aid.RALLY_LABEL.format(name=fig.name, now=now.prestige, cap=fig.start_prestige, silver=cfg.rally_silver)
        problem = figure_aid.rally_problem(s, c, fid)
        opts.append(Option(id=f"aid:rally:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                    else ctx._cost_option(f"aid:rally:{fid}", label, cfg.rally_stamina))
    for fid in figure_aid.visiting(s, c):
        name = c.figures[fid].name
        label = figure_aid.VISIT_LABEL.format(name=name, left=figure_aid.left_text(s, c, fid))
        problem = figure_aid.visit_problem(s, c, fid)
        opts.append(Option(id=f"aid:visit:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                    else ctx._cost_option(f"aid:visit:{fid}", label, cfg.visit_stamina))
    return opts


def act(ctx, arg: str) -> list[str]:
    """護衛（aid:guard:<id>）、犒軍（aid:rally:<id>）、探望（aid:visit:<id>）：重驗、扣體力（犒軍另扣銀兩）、記進這一季；
    第一季規則開著時記 contrib_push 點推力的貢獻。"""
    s, c = ctx.state, ctx.content
    p = s.player
    cfg = c.config.figure_aid
    verb, _, fid = arg.partition(":")
    refuse = ["（此刻無法這麼做。）"]
    if not figure_aid.on(c) or p.faction is None or fid not in c.figures or p.journey is not None:
        return refuse
    fig = c.figures[fid]
    if verb in ("guard", "rally"):
        if fig.faction != ctx._side() or fid not in figures.present_at(s, c, p.location):
            return refuse
        if verb == "guard":
            cost, problem = cfg.guard_stamina, figure_aid.guard_problem(s, c, fid)
        else:
            cost, problem = cfg.rally_stamina, figure_aid.rally_problem(s, c, fid)
    elif verb == "visit":
        if fid not in figure_aid.visiting(s, c):
            return refuse
        cost, problem = cfg.visit_stamina, figure_aid.visit_problem(s, c, fid)
    else:
        return refuse
    if problem is None and p.stamina < cost:
        problem = f"體力不夠（要 {cost} 點）"
    if problem is not None:
        return [problem if problem.startswith("（") else f"（{problem}。）"]
    p.stamina -= cost
    changes = [f"體力 -{cost}"]
    if verb == "guard":
        post = figure_aid.guard(s, c, fid, ctx._battle_power())
        msgs = [figure_aid.GUARD_DONE.format(name=fig.name, until=ctx.stamp(post.until))]
    elif verb == "rally":
        p.stats["silver"] = p.stats.get("silver", 0) - cfg.rally_silver
        changes.append(f"銀兩 -{cfg.rally_silver}")
        n = figure_aid.rally(s, c, fid)
        now = figures.state_of(s, c, fid)
        msgs = [figure_aid.RALLY_DONE.format(silver=cfg.rally_silver, name=fig.name, n=n, now=now.prestige, cap=fig.start_prestige)]
    else:
        hours = figure_aid.visit(s, c, fid)
        msgs = [figure_aid.VISIT_DONE.format(name=fig.name, hours=figure_aid.hours_text(hours))]
    if verb in ("guard", "rally") and fig.character:  # 求援委託（第三批）：護衛、犒軍他也算辦成
        msgs += bounties.on_aid(s, c, fig.character)
    if ctx._draft is not None:
        ctx._draft.changes += changes
    if season_one(c, s.world) and cfg.contrib_push:
        contrib = c.config.contrib_per_push * cfg.contrib_push
        wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib)
        msgs.append(f"貢獻 +{contrib}")
    return msgs


def deliver_guard_credits(ctx) -> None:
    """護衛替人物擋下的挑戰（figure_aid.contest 記在 WorldState.guard_credits）：自己同步時補名望 guard_fame、心得 guard_xinde
    （每擋一次），一則紀錄。做法同 _deliver_echoes：擋下的那一下不動護衛的角色。"""
    s, c = ctx.state, ctx.content
    lines = s.world.guard_credits.pop(s.player.name, None)
    if not lines:
        return
    cfg = c.config.figure_aid
    n = len(lines)
    out = list(lines)
    if cfg.guard_xinde:
        s.player.stats["xinde"] = s.player.stats.get("xinde", 0) + cfg.guard_xinde * n
        out.append(f"心得 +{cfg.guard_xinde * n}")
    if cfg.guard_fame:
        out += renown.gain(s, c, "fame", cfg.guard_fame * n)
    ctx._write(figure_aid.CREDIT_TITLE, out)
    ctx._save_season()


def title(ctx, arg: str) -> str:
    """護衛、犒軍、探望這一下江湖紀錄的標題（核心在動作之前先拿；原本 Game._action_title 的 aid 那一格）。"""
    verb, _, fid = arg.partition(":")
    name = {"guard": figure_aid.GUARD_TITLE, "rally": figure_aid.RALLY_TITLE, "visit": figure_aid.VISIT_TITLE}.get(verb, figure_aid.GUARD_TITLE)
    return f"{name}・{ctx.content.figures[fid].name}" if fid in ctx.content.figures else name
