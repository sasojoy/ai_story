"""軍令卡與記功（功能包 military；全部拆包第 33 批）：軍令的兩個行動（第 1 階守勢、接糧車）的選單、替自己記一次軍令、江湖頁的「本週軍令」卡、押著的糧車那一行。
原本 Game 上的 4 個方法（_order_options、_order_credit、convoy_line、orders_view）；名字去掉前導底線。第一個參數是 ctx。orders_view、convoy_line 不改狀態；
order_credit 會改（記進軍令的進度、推新手引導）。軍令的規則在 tianxia/orders.py（共用規則層，第 40 批收進）。
「你這一步」的 order 那一格（全部拆包第 36 批；原本 weekcard._steps 的軍令那一段與 step._order_places、_target、_then 的軍令那一支）：
step_items、step_place，只讀；ORDER_GAIN 從 weekcard 搬來，字一個不改。
"""
from __future__ import annotations

from tianxia import materials
from tianxia import atlas, orders  # 共用規則層（打擊點 _strike_place、摸清 is_known，第 50 批收進；軍令 orders）
from tianxia import step as step_rules  # 核心本體（第 36 批收進 MODULES）：「你這一步」的 REF、place
from tianxia.core.option import Option
from tianxia.models import Location
from tianxia.rules import front_of

from . import order_cards  # 軍令卡上怎麼出力那一行（第二輪第 97 批從 atlas 搬進這一包）


def order_options(ctx, loc: Location) -> list[Option]:
    """軍令的兩個行動（計畫 T6）：在有戰線的地方做第 1 階守勢行動；在護糧的起點接糧車。開關關著、散人沒有。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not orders.active(s, c) or p.faction is None:
        return []
    opts: list[Option] = []
    duty = c.orders.duties.get(p.faction)
    if duty is not None and front_of(c, loc.id) is not None:
        opts.append(ctx._duty_option(duty.name))
    escort = orders.escort_at(s, c, ctx._side(), loc.id)  # 豪強分屬兩軍：依附那一軍的護糧
    if escort is not None and p.convoy is not None:  # 一次押一車：寫明手上那一車要送去哪（T6 審查 I3）
        dest = c.locations[p.convoy.to_loc].name
        opts.append(Option(id="act:convoy", enabled=False, label=f"接下糧車（你還押著一車糧，要送到{dest}）"))
    elif escort is not None:
        need, have = c.config.convoy_grain, materials.grain_of(s, c)
        dest = c.locations[escort.end].name
        if have < need:
            opts.append(Option(
                id="act:convoy", enabled=False,
                label=f"接下糧車（送到{dest}・糧草不夠：要 {need} 份，你有 {have} 份；糧草是慢屬性的素材）",
            ))
        else:
            used = "、".join(f"{c.materials[mid].name} ×{n}" for mid, n in materials.grain_plan(s, c, need))
            opts.append(Option(id="act:convoy", label=f"接下糧車（送到{dest}・交出糧草 {need} 份：{used}）"))
    return opts


def order_credit(ctx, *, side: str | None = None, **kw) -> list[str]:
    """替自己記一次軍令（orders.credit）；真的記到了就推新手引導的「完成一次軍令的個人部分」（計畫 T6 Task 8）。
    達成時陣營軍情列的前三名一律寫名號（傳聞分層第七節：陣營軍情一律具名），所以不給 shown。
    side 不給就是此刻的陣營；約戰結算（FB-856）給貼（應）約戰那一刻替哪一軍出力，豪強窗內改幫也不搬帳。"""
    s, c = ctx.state, ctx.content
    msgs = orders.credit(s, c, side or ctx._side(), s.player.name, **kw)  # 豪強分屬兩軍：記在依附那一軍的軍令上
    if msgs:
        msgs += ctx._guide(ctx._note_action("order"))
    return msgs


def convoy_line(ctx) -> str | None:
    """押著的糧車要送去哪（江湖頁軍令卡上的一行；T6 審查 I3）：那一道軍令已經達成或換週清掉了也照樣寫，
    送到了照樣記捐獻與貢獻。沒有押車、或這一季已經收了（休季，FB-045）時是 None。"""
    convoy = ctx.state.player.convoy
    if convoy is None or ctx.state.world.ended:
        return None
    return f"你押著一車糧（{convoy.grain} 份），要送到{ctx.content.locations[convoy.to_loc].name}。"


def orders_view(ctx) -> list[dict]:
    """江湖頁的「本週軍令」卡（計畫 T6）：自己陣營這週的軍令，只給自己陣營看；散人、開關關著是空的。
    截止是下週一 00:00（最後一週寫成季末那一刻，calendar.point 會夾住）。休季時也是空的（FB-045）：
    收季那一週的軍令截止已經過了，休季什麼都不能做，結算畫面底下不該還有一張叫人去做事的卡。
    沒達成的軍令多一個 how：怎麼出力（order_cards.order_how，FB-093；打擊另寫他在哪，FB-072）；打完的沒有這個鍵。"""
    s, c = ctx.state, ctx.content
    if s.world.ended:
        return []
    name = s.player.name
    views = []
    for o in orders.current(s, c, ctx._side()):  # 豪強分屬兩軍：看依附那一軍的軍令
        total = sum(o.progress.values())
        view = {
            "id": o.id, "title": orders.title(c, o), "text": o.text, "mine": o.progress.get(name, 0),
            "progress": min(total, o.quota), "quota": o.quota, "done": o.done,
            "deadline": ctx.stamp(orders.deadline(s, c, o)),  # 下週一 00:00；21 天季是隔天 00:00
        }
        if not o.done and (o.template != "strike" or o.figure is not None):
            view["how"] = order_cards.order_how(s, c, o)  # 怎麼出力（FB-093；打擊另寫他在哪，FB-072）；打完的沒有這個鍵
        views.append(view)
    return views


# core_step（全部拆包第 36 批「你這一步」）：order 那一格（core/features.py 的 STEP_ORDER：委託之後、揭了的懸賞之前）
ORDER_GAIN = "陣營記功 {n}／{quota}"  # 待 joy 潤：軍令那一件做完拿什麼（軍令本人不另給賞：照做一次替陣營記一次，湊滿套效果）


def step_items(ctx, views: list[dict]) -> list[dict]:
    """「你這一步」的軍令那幾件（原本 weekcard._steps 的軍令那一段）：views 是殼算好傳進來的那一份 orders_view（不重算），沒做完的每一道一件。"""
    out: list[dict] = []
    for o in views:
        if not o.get("done"):
            out.append({"kind": "order", "text": f"{o['title']}：{o.get('how') or o['text']}",
                        "reward": ORDER_GAIN.format(n=o.get("progress", 0), quota=o.get("quota", 0)), step_rules.REF: ("order", o.get("id"))})
    return out


def _step_order_places(ctx, o) -> set[str]:
    """這道軍令去哪裡做（只列摸清了的地方：同軍令卡，不洩漏沒摸清的地點；原本 step._order_places）。"""
    s, c = ctx.state, ctx.content
    if o.template == "strike":
        where = atlas._strike_place(s, c, o)  # noqa: SLF001  同軍令卡的「他現在在哪」（讀人物此刻的所在）
        places = [where] if where is not None else []
    elif o.template == "siege":
        places = orders.siege_places(c, o.faction, o.front, s.world) if o.front else []
    elif o.template == "defend":
        places = orders.defend_places(c, s.world, o)
    elif o.template == "escort":
        places = [o.end if s.player.convoy is not None and s.player.convoy.order == o.id else o.start]
    else:
        places = [o.location]
    return {loc for loc in places if loc in c.locations and atlas.is_known(s, c, loc)}


def _step_then(ctx, o) -> dict | None:
    """護糧軍令還沒接糧車：糧車要送到的終點 {"location", "name"}（target 是起點）；其他都是 None（原本 step._then）。"""
    s, c = ctx.state, ctx.content
    if o is None or o.template != "escort" or (s.player.convoy is not None and s.player.convoy.order == o.id):
        return None
    if o.end not in c.locations or not atlas.is_known(s, c, o.end):
        return None
    return {"location": o.end, "name": c.locations[o.end].name}


def step_place(ctx, ref: tuple) -> tuple:
    """軍令那一件的 (id, target, then)（原本 step._target、_then 的軍令那一支）：target 是最近的摸清了的那一處，護糧還沒接糧車多 then（終點）。"""
    s = ctx.state
    o = next((x for x in s.world.orders if x.id == ref[1]), None)
    places = _step_order_places(ctx, o) if o is not None else set()
    target = step_rules.place(ctx, ctx._nearest_to(places) if places else None)  # noqa: SLF001
    return ref[1], target, _step_then(ctx, o)
