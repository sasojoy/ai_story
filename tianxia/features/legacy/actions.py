"""傳承的動作（架構方向 v2 第六、七節）：換季那一刻結算正氣、邪氣、機緣；識海——這一季選一份神品意境帶到下一季，下一季解封才用得到。

識海的三個選項（「此地還能做」裡；序章、休季核心本來就不問）：
- legacy:keep:<意境 id>：把身上這一份神品意境放進識海（換季那一刻照它抄；不選就沒有，不自動帶）。
- legacy:drop：不留了（一直按得下去，bot_always）。
- legacy:open：解封上一季帶來的那一份：開季後 shihai_after 世界秒、shihai_level 級以上、花 shihai_xinde 心得；名字照這一季登記
  （WorldState.god_names；不寫 god_firsts、不上江湖史的首創：帶過來的是傳承、不是首創）。這一季已經有人先取了同名，先取的人優先，
  改從三個候選挑一個（legacy:name:<i>）。身上已經有一份神品（或正在等著取名）的解不開：神品一人最多一份，識海那一份也算。
"""
from __future__ import annotations

from tianxia import insight_fx, insights, naming
from tianxia.core.features import Outcome
from tianxia.core.option import Option
from tianxia.state import GameState, LegacyBook, ShihaiSeal

from . import rules as R

TITLE = "識海"
NAMES_OFFERED = 3
NAME_TRIES = 12

# 寫給玩家看的字（待 joy 潤）
KEEP_LABEL = "放進識海：{name}"
DROP_LABEL = "識海不留了（{name}）"
OPEN_LABEL = "解封識海：{name}"
OPEN_WAIT = "解封識海：{name}（{why}）"
NAME_LABEL = "識海裡的那一份改名為「{name}」"
KEPT = "你把「{name}」沉進識海。這一季收季、下一季開季時，它會跟著你，只是封著，要解封才用得上。"
DROPPED = "你不再把「{name}」留進識海。"
TAKEN = "這一季江湖上已經有一個神品意境叫「{name}」了，先取的人優先。替識海裡的那一份換個名字。"
OPENED = "識海解封：神品意境「{name}」（屬{attribute}）回到你身上。"
FITS = "這一份要裝在合得上屬{attribute}的武學上才生效；裝不上的話，先換一門武學。"
HOLDING = "你身上已經有一份神品意境了：神品一人最多一份，先放掉那一份才解得開識海。"
NOT_YET = "（此刻無法這麼做。）"
WHY_TIME = "開季滿一天"
WHY_LEVEL = "{level} 級以上"
WHY_XINDE = "心得 {xinde}"
WHY_HELD = "先放掉身上那一份神品"


def book_of(state: GameState) -> LegacyBook:
    p = state.player
    if p.legacy is None:
        p.legacy = LegacyBook()
    return p.legacy


def _gods(state: GameState) -> list[str]:
    """自己身上的神品意境 id（照拿到的先後）。"""
    p = state.player
    return [iid for iid in p.own_insights if insight_fx.is_god(state, iid)]


def _held(state: GameState) -> bool:
    return bool(_gods(state)) or state.player.god_naming is not None


def _blockers(ctx) -> list[str]:
    """解封還差什麼（空的是解得開）。"""
    r = R.rules(ctx.content)
    p = ctx.state.player
    out = []
    if ctx.state.world.time < r.shihai_after:
        out.append(WHY_TIME)
    if p.member.level < r.shihai_level:
        out.append(WHY_LEVEL.format(level=r.shihai_level))
    if p.stats.get("xinde", 0) < r.shihai_xinde:
        out.append(WHY_XINDE.format(xinde=r.shihai_xinde))
    return out


def options(ctx) -> list[Option]:
    p = ctx.state.player
    book = p.legacy
    out: list[Option] = []
    pick = book.pick if book is not None else None
    for iid in _gods(ctx.state):
        if iid != pick:
            out.append(Option(id=f"legacy:keep:{iid}", label=KEEP_LABEL.format(name=p.own_insights[iid].name)))
    if pick is not None and pick in p.own_insights:
        out.append(Option(id="legacy:drop", label=DROP_LABEL.format(name=p.own_insights[pick].name)))
    sealed = book.sealed if book is not None else None
    if sealed is not None:
        if sealed.names:
            out += [Option(id=f"legacy:name:{i}", label=NAME_LABEL.format(name=n)) for i, n in enumerate(sealed.names)]
        else:
            why = _blockers(ctx) + ([WHY_HELD] if _held(ctx.state) else [])
            label = OPEN_WAIT.format(name=sealed.insight.name, why="、".join(why)) if why else OPEN_LABEL.format(name=sealed.insight.name)
            out.append(Option(id="legacy:open", label=label, enabled=not why))
    return out


def title(ctx, arg: str) -> str:
    return TITLE


def act(ctx, arg: str) -> list[str]:
    verb, _, rest = arg.partition(":")
    p = ctx.state.player
    if verb == "keep":
        if rest not in _gods(ctx.state):
            return [NOT_YET]
        book_of(ctx.state).pick = rest
        return [KEPT.format(name=p.own_insights[rest].name)]
    if verb == "drop":
        book = p.legacy
        if book is None or book.pick is None:
            return [NOT_YET]
        name = p.own_insights[book.pick].name if book.pick in p.own_insights else ""
        book.pick = None
        return [DROPPED.format(name=name)]
    if verb == "open":
        return _open(ctx, None)
    if verb == "name" and rest.isdigit():
        return _open(ctx, int(rest))
    return [NOT_YET]


def _taken(ctx, name: str) -> bool:
    return (name in ctx.world.get_season().god_names or ctx.world.is_character_name(name)
            or name in {i.name for i in ctx.state.player.own_insights.values()})


def _candidates(ctx, sealed: ShihaiSeal) -> list[str]:
    """撞名時換的三個候選（字表；同一個人同一份同一季永遠一樣）。"""
    out: list[str] = []
    key = f"識海|{ctx.state.player.name}|{sealed.fx.grand}|{sealed.season}"
    for salt in range(NAME_TRIES):
        name = naming.fallback_name(ctx.content, key, "意境", salt=salt, tianji=ctx.state.world.tianji)
        if name not in out and not _taken(ctx, name) and naming.name_problem(name, ctx.content) is None:
            out.append(name)
        if len(out) == NAMES_OFFERED:
            break
    return out


def _open(ctx, choice: int | None) -> list[str]:
    p = ctx.state.player
    book = p.legacy
    sealed = book.sealed if book is not None else None
    if sealed is None or _blockers(ctx):
        return [NOT_YET]
    if _held(ctx.state):
        return [HOLDING]
    if choice is None:
        if sealed.names:
            return [NOT_YET]
        name = sealed.insight.name
    else:
        if choice >= len(sealed.names):
            return [NOT_YET]
        name = sealed.names[choice]
    claimed: dict[str, bool] = {}

    def claim(season) -> None:  # 鎖內原子：同一季全服不重複（同 epiphany.grant；不碰 god_firsts：傳承不算首創）
        claimed["ok"] = name not in season.god_names and not ctx.world.is_character_name(name)
        if claimed["ok"]:
            season.god_names[name] = p.name

    if name in {i.name for i in p.own_insights.values()}:
        claimed["ok"] = False
    else:
        season = ctx.world.mutate_season(claim)
    if not claimed["ok"]:
        sealed.names = _candidates(ctx, sealed)
        return [TAKEN.format(name=name)]
    ctx.state.world.god_names = dict(season.god_names)
    p.stats["xinde"] = p.stats.get("xinde", 0) - R.rules(ctx.content).shihai_xinde
    p.own_serial += 1
    own = sealed.insight.model_copy(update={"id": f"{insights.OWN_PREFIX}{p.own_serial}", "name": name})
    p.own_insights[own.id] = own
    p.insights.append(own.id)
    p.insight_fx[own.id] = sealed.fx.model_copy(deep=True)
    book.sealed = None
    attribute = own.attribute
    return [OPENED.format(name=name, attribute=attribute), FITS.format(attribute=attribute)]


def on_season_start(ctx, old: GameState) -> None:
    """換季那一刻（新的存檔接上了、開場那一則之前；old 是上一季的）：結算三項、識海抄下上一季選的那一份、立門路的旗標、寫一則江湖紀錄。
    同一季只結算一次（settled）。"""
    r = R.rules(ctx.content)
    p = ctx.state.player
    season = p.season_number
    book = p.legacy if p.legacy is not None else LegacyBook()
    if book.settled == season:
        return
    book = R.settle(book, R.gains(R.inputs(old, ctx.content), r), r, season)
    # 識海：上一季選的那一份還在身上、還是神品才帶；不選就沒有（上一季帶來還沒解封的那一份也一樣，不自動再帶）
    pick = book.pick
    if pick is not None and pick in old.player.own_insights and insight_fx.is_god(old, pick):
        book.sealed = ShihaiSeal(
            insight=old.player.own_insights[pick].model_copy(deep=True), fx=old.player.insight_fx[pick].model_copy(deep=True),
            season=old.player.season_number,
        )
    else:
        book.sealed = None
    book.pick = None
    p.legacy = book
    p.flags -= R.all_flags(r)
    p.flags |= {tier.flag for _, tier in R.reached(book, r)}
    lines = R.summary(book, r)
    if book.sealed is not None:
        why = "、".join([WHY_TIME, WHY_LEVEL.format(level=r.shihai_level), WHY_XINDE.format(xinde=r.shihai_xinde)])
        lines.append(f"識海裡封著上一季的神品意境「{book.sealed.insight.name}」：{why}，才解得開。")
    ctx._write("傳承", lines, tag="傳承")


def status(ctx) -> dict:
    """江湖畫面的頂層 main.legacy：三項的值、這一季加了多少、到了的門路、識海封著的那一份（網頁之後照它畫）。"""
    book = ctx.state.player.legacy
    if book is None:
        return {}
    r = R.rules(ctx.content)
    return {"legacy": {
        "values": {axis: R.shown(getattr(book, axis)) for axis in R.AXES},
        "gains": {axis: R.shown(book.gains.get(axis, 0.0)) for axis in R.AXES},
        "opened": [tier.text for _, tier in R.reached(book, r)],
        "sealed": book.sealed.insight.name if book.sealed is not None else None,
        "pick": book.pick,
    }}
