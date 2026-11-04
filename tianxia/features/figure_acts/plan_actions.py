"""盤算（助他一臂、壞他的事）的動作與畫面（功能包 figure_acts；全部拆包第 31 批）：人在盤算的地點的選單那兩顆、按下去（plan:help／block:<站>）、
江湖頁的盤算卡、此地舊事。原本 Game 上的 4 個方法，名字去掉前導底線、第一個參數是 ctx。會改狀態（只有 act）。

`plan:` 的 choose 接掛鉤（標題一起給）；選單末段盤算那一串在包選項之後（夾著 features_core.options），所以 options 留委派；畫面兩個是 server 在叫。
"""
from __future__ import annotations

from tianxia import deeds
from tianxia import plans  # 過渡：待搬（人物活起來 plans，總表第 40 批）
from tianxia.core.option import Option


def options(ctx) -> list[Option]:
    """人在盤算的地點：助他一臂、壞他的事（花 Config.plans.stamina）；插過手的留一顆灰的。"""
    cost = ctx.content.config.plans.stamina
    return [ctx._cost_option(oid, label, cost) if ok else Option(id=oid, label=label, enabled=False)
            for oid, label, ok in plans.options(ctx.state, ctx.content)]


def act(ctx, arg: str) -> list[str]:
    """助一臂（plan:help:<站>）、壞他的事（plan:block:<站>）：重驗還開著、人在那裡、站的邊對、還沒插過手、體力夠。"""
    s, c = ctx.state, ctx.content
    verb, _, stop = arg.partition(":")
    problem = plans.problem(s, c, verb, stop)
    if problem is not None:
        return [problem]
    cost = c.config.plans.stamina
    if s.player.stamina < cost:
        return [f"體力不足（需要 {cost}）。"]
    s.player.stamina -= cost
    return plans.join(s, c, verb, stop, ctx.stamp(plans.find(s, stop).due))


def plan_view(ctx) -> dict | None:
    """江湖頁的盤算卡（main.plan）：全服開著的盤算裡最切身的一件；沒有開著的、開關關著是 None。"""
    s, c = ctx.state, ctx.content
    plan = plans.pick(s, c)
    if plan is None:
        return None
    view = plans.card(s, c, plan, when=ctx.stamp(plan.due), minutes=ctx.place_minutes(plan.place))
    for act in view["acts"]:  # 卡上的鈕跟「此地還能做」那一顆同一個字（帶體力）
        act["label"] = f"{act['label']}（體力 {c.config.plans.stamina}）"
    return view


def place_deeds_view(ctx) -> list[dict] | None:
    """此地舊事（main.place_deeds）：這裡最近的幾筆世界記事；在路上、沒有、開關關著是 None。"""
    s, c = ctx.state, ctx.content
    if s.player.journey is not None:
        return None
    found = deeds.at_place(s, c, s.player.location)
    return [{"when": ctx.stamp(d.time), "text": d.text} for d in found] or None


def title(ctx, arg: str) -> str:
    """盤算這一下江湖紀錄的標題（核心在動作之前先拿；原本 Game._action_title 的 plan 那一格）：「盤算・劉備」。"""
    plan = plans.find(ctx.state, arg.partition(":")[2])
    return f"{plans.TITLE}・{plans._name(ctx.content, plan.who)}" if plan is not None else plans.TITLE
