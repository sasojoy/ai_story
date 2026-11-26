"""地方大事的動作（設計：玩家一起玩設計稿第一節；Joy 2026-11-26「做」）。

一個大區一週一件，三幕：
- 第一幕：在這個大區探索一顆（事件 outing）、打贏一場（事件 win）都算一份力，不另外按鈕。
- 第二幕：人在這個大區，挑一個做法（difang:way:<i>），照那一項屬性擲；成了兩份、沒成一份；一人一次。
- 第三幕：人在這個大區，一天上去一次（difang:strike），一下的份量照戰力；最後一下的名號記下來。
三幕湊滿＝湊滿了；這一週過完沒湊滿＝沒湊滿（此地鬧饑荒）。兩種都寫一行江湖史；出過力的人下一次同步領收場那一份。
換週、收場都是「誰先同步誰做」（全服那一份在 WorldState.difang，照 _save_season 寫回）。
包只 import 核心、共用層與自己。"""
from __future__ import annotations

from tianxia import atlas  # 共用層（大區）
from tianxia import calendar  # 核心（季曆第幾週）
from tianxia import materials  # 共用層（收場給的此地素材）
from tianxia import place_state  # 共用層（沒湊滿：此地鬧饑荒）
from tianxia import prologue  # 共用層（序章裡不算）
from tianxia import renown  # 共用層（收場的名望）
from tianxia import rules as core_rules  # 核心（add_rumor）
from tianxia.core import annal_base as annals  # 核心（行狀）
from tianxia.core.option import Option
from tianxia.state import DifangAffair, DifangWorld, Rumor

from . import rules

# 給玩家看的字（待 joy 潤）
TITLE = "地方大事・{title}"  # 待 joy 潤（江湖紀錄的標題）
CREDIT = "{title}：{what}也算一份力。"  # 待 joy 潤（第一幕：探索、打贏之後那一行）
CREDIT_WHAT = {"outing": "你這一趟帶回來的", "win": "你這一仗"}  # 待 joy 潤
ACT_UP = "{title}：{name}湊齊了，接著是「{next}」。"  # 待 joy 潤（換幕那一刻的地方傳聞）
WAY_LABEL = "{title}・{label}"  # 待 joy 潤（第二幕的選項）
WAY_HIT = "成了。這一手算兩份力。"  # 待 joy 潤
WAY_MISS = "沒有全成，不過也幫上了一點。"  # 待 joy 潤
WAY_DONE = "這一幕你已經出過手了。"  # 待 joy 潤
STRIKE_LABEL = "{title}・上前對付{foe}"  # 待 joy 潤（第三幕的選項）
STRIKE_LINE = "你和{foe}的人交了手，替大家壓下一截。"  # 待 joy 潤
STRIKE_LAST = "你補上了最後一下，{foe}撐不住了。"  # 待 joy 潤
STRIKE_DONE = "今天你已經上去過了，明天再來。"  # 待 joy 潤
GONE = "這件事已經過去了。"  # 待 joy 潤（按下去那一刻已經換幕或收場）
PAID_DONE = "{title}湊滿了。出過力的人都記了一筆。"  # 待 joy 潤（收場那一份的第一行）
PAID_FAILED = "{title}沒能湊滿。你出過的力，此地的人記得。"  # 待 joy 潤
ANNAL_DONE = "與眾人合力，{title}"  # 待 joy 潤（行狀；接 done.chronicle 不帶名字的那一段）
NAMES_SEP = "、"


def _t(ctx):
    return ctx.content.config.difang


def _key(ctx) -> str:
    return ctx._mall_owner()


def _season(ctx) -> int:
    return int(ctx.state.player.season_number or 0)


def _week(ctx) -> int:
    w = ctx.state.world
    return int(calendar.point(w.time, ctx.content, w).week)


def _running(ctx) -> bool:
    if not rules.on(ctx.content) or not ctx.content.map.regions:
        return False
    if prologue.active(ctx.state, ctx.content):
        return False
    return ctx.world.season_phase() == "running"


def _region_here(ctx) -> str | None:
    p = ctx.state.player
    if p.journey is not None or p.location not in ctx.content.locations:
        return None
    region = atlas.region_of(ctx.content, p.location)
    return region.id if region is not None else None


def _region_name(ctx, region_id: str) -> str:
    return next((r.name for r in ctx.content.map.regions if r.id == region_id), region_id)


def _place_name(ctx, loc_id: str) -> str:
    loc = ctx.content.locations.get(loc_id)
    return loc.name if loc is not None else loc_id


def _def(a: DifangAffair) -> dict | None:
    return rules.affairs().get(a.affair)


# ── 換週：這一週還沒開的大區開一件；上一週還開著的收成沒湊滿 ──


def roll_week(ctx) -> bool:
    """回 True＝全服那一份動了（呼叫的人負責 _save_season）。"""
    if not _running(ctx):
        return False
    s, week = ctx.state, _week(ctx)
    dw = s.world.difang
    if dw is not None and dw.week == week:
        return False
    dw = s.world.difang = dw or DifangWorld()
    for a in dw.affairs:
        if a.status == rules.OPEN and a.week != week:
            _fail(ctx, a)
    for region in ctx.content.map.regions:
        if any(a.region == region.id and a.week == week for a in dw.affairs):
            continue
        d = rules.pick(region.id, _season(ctx), week)
        if d is None or d.get("place") not in ctx.content.locations:
            continue
        prev = [a for a in dw.affairs if a.region == region.id]
        heads = len(prev[-1].shares) if prev else 0
        dw.affairs.append(DifangAffair(region=region.id, affair=d["id"], week=week, need=rules.needs(_t(ctx), heads)))
        core_rules.add_rumor(s, f"{_region_name(ctx, region.id)}出了一件大事：{d['hook']}", d["place"], content=ctx.content, layer="local", named=False)  # 待 joy 潤
    dw.week = week
    return True


def _chronicle(ctx, text: str) -> None:
    s = ctx.state
    s.world.chronicle.append(Rumor(time=s.world.time, text=text))


def _top_names(a: DifangAffair, n: int) -> list[str]:
    ranked = sorted(a.shares.items(), key=lambda kv: (-kv[1], kv[0]))
    return [a.names.get(k, k) for k, _ in ranked[:n]]


def _fail(ctx, a: DifangAffair) -> None:
    d = _def(a)
    a.status = rules.FAILED
    if d is None:
        return
    place_state.famine(ctx.state.world, ctx.content, d["place"])
    _chronicle(ctx, d["failed"]["chronicle"])


def _finish(ctx, a: DifangAffair) -> None:
    d = _def(a)
    a.status = rules.DONE
    if d is None:
        return
    names = NAMES_SEP.join(_top_names(a, _t(ctx).top_names))
    _chronicle(ctx, rules.fill(d["done"]["chronicle"], n=len(a.shares), names=names))
    ctx.state.world.flags.add(f"difang:{a.affair}")  # 之後的事件可以照它開（Condition 的世界旗標）


# ── 此地這一件 ──


def here(ctx) -> DifangAffair | None:
    region = _region_here(ctx)
    dw = ctx.state.world.difang
    if region is None or dw is None:
        return None
    week = _week(ctx)
    return next((a for a in dw.affairs if a.region == region and a.week == week), None)


def _credit(ctx, a: DifangAffair, n: int) -> list[str]:
    """出 n 份力：記到自己頭上、這一幕往前推；推滿了換幕（第三幕推滿就收場）。回換幕那一行（沒換是空的）。"""
    key = _key(ctx)
    a.shares[key] = a.shares.get(key, 0) + n
    a.names[key] = ctx.state.player.name
    a.got += n
    while len(a.by_act) < a.act:
        a.by_act.append([])
    if key not in a.by_act[a.act - 1]:
        a.by_act[a.act - 1].append(key)
    if a.got < a.need[a.act - 1]:
        return []
    d = _def(a) or {}
    acts = d.get("acts", [])
    if a.act >= rules.ACTS:
        a.last = ctx.state.player.name
        _finish(ctx, a)
        return []
    a.act += 1
    a.got = 0
    line = ACT_UP.format(title=d.get("title", ""), name=acts[a.act - 2]["name"], next=acts[a.act - 1]["name"]) if len(acts) >= a.act else ""
    if line:
        core_rules.add_rumor(ctx.state, line, d.get("place"), content=ctx.content, layer="local", named=False)
    return []


def _act_one(ctx, what: str) -> list[str]:
    """事件 outing、win：第一幕的一份力（假人一樣算：照公開行動出力）。包的 bus 格核心不看 enabled：第一行自己問。"""
    if not _running(ctx):
        return []
    changed = roll_week(ctx)
    a = here(ctx)
    if a is None or a.status != rules.OPEN or a.act != 1:
        if changed:
            ctx._save_season()
        return []
    d = _def(a) or {}
    _credit(ctx, a, 1)
    ctx._save_season()
    return [CREDIT.format(title=d.get("title", ""), what=CREDIT_WHAT[what])]


def on_outing(ctx, loc_id: str) -> list[str]:
    return _act_one(ctx, "outing")


def on_win(ctx, loc_id: str, squad_id: str) -> list[str]:
    return _act_one(ctx, "win")


# ── 選項：第二幕的做法、第三幕上前 ──


def options(ctx) -> list[Option]:
    if not _running(ctx):
        return []
    a = here(ctx)
    if a is None or a.status != rules.OPEN or a.act == 1:
        return []
    d = _def(a)
    if d is None:
        return []
    key, title = _key(ctx), d["title"]
    if a.act == 2:
        done = key in a.act2
        return [Option(id=f"difang:way:{i}", label=WAY_LABEL.format(title=title, label=w["label"]), enabled=not done)
                for i, w in enumerate(d["acts"][1].get("ways", []))]
    foe = d["acts"][2].get("foe", "")
    return [Option(id="difang:strike", label=STRIKE_LABEL.format(title=title, foe=foe), enabled=a.struck.get(key) != ctx._pill_day())]


def title(ctx) -> str:
    a = here(ctx)
    d = _def(a) if a is not None else None
    return TITLE.format(title=d["title"] if d else "")


def act(ctx, arg: str) -> list[str]:
    roll_week(ctx)
    a = here(ctx)
    d = _def(a) if a is not None else None
    if a is None or d is None or a.status != rules.OPEN:
        return [GONE]
    key = _key(ctx)
    verb, _, rest = arg.partition(":")
    if verb == "way":
        if a.act != 2:
            return [GONE]
        if key in a.act2:
            return [WAY_DONE]
        ways = d["acts"][1].get("ways", [])
        try:
            way = ways[int(rest)]
        except (ValueError, IndexError):
            return [GONE]
        t = _t(ctx)
        chance = rules.way_chance(t, ctx.state.player.stats.get(way.get("stat", ""), 0))
        hit = rules.roll("地方大事", _season(ctx), a.week, a.region, key, "way").random() < chance
        a.act2.append(key)
        out = [WAY_HIT if hit else WAY_MISS]
        _credit(ctx, a, t.way_hit if hit else t.way_miss)
        ctx._save_season()
        return out
    if verb == "strike":
        if a.act != 3:
            return [GONE]
        today = ctx._pill_day()
        if a.struck.get(key) == today:
            return [STRIKE_DONE]
        a.struck[key] = today
        foe = d["acts"][2].get("foe", "")
        _credit(ctx, a, rules.blow(_t(ctx), ctx._battle_power(seal=False)))
        ctx._save_season()
        return [(STRIKE_LAST if a.status == rules.DONE else STRIKE_LINE).format(foe=foe)]
    return [GONE]


# ── 同步：換週、領收場那一份 ──


def on_sync(ctx) -> None:
    if not _running(ctx):
        return
    changed = roll_week(ctx)
    key = _key(ctx)
    dw = ctx.state.world.difang
    for a in (dw.affairs if dw is not None else []):
        if a.status == rules.OPEN or key not in a.shares or key in a.paid:
            continue
        a.paid.append(key)
        changed = True
        _pay(ctx, a)
    if changed:
        ctx._save_season()


def _material(ctx, a: DifangAffair, d: dict) -> list[str]:
    """此地（沒有就這個大區第一個有素材的地點）的素材，第 material_tier 階。"""
    c = ctx.content
    spots = [d["place"], *atlas.region_locations(c, a.region)]
    mats = next(([m for m in c.locations[x].materials if m in c.materials] for x in spots if x in c.locations
                 and any(m in c.materials for m in c.locations[x].materials)), [])
    if not mats:
        return []
    mid = materials.tier_pick(c, c.materials[mats[0]].attribute, f"地方大事｜{_season(ctx)}｜{a.week}｜{a.region}｜{_key(ctx)}", _t(ctx).material_tier)
    got = materials.grant(ctx.state, c, mid) if mid is not None else None
    return [got] if got else []


def _pay(ctx, a: DifangAffair) -> None:
    d = _def(a)
    if d is None:
        return
    s, t = ctx.state, _t(ctx)
    if a.status == rules.DONE:
        lines = [d["done"]["line"], PAID_DONE.format(title=d["title"])]
        lines += _material(ctx, a, d)
        lines += renown.gain(s, ctx.content, "fame", t.fame_done)
        annals.note(s, ctx.content, annals.DEED, ANNAL_DONE.format(title=d["title"]), 2, place=d["place"])
    else:
        lines = [d["failed"]["line"], PAID_FAILED.format(title=d["title"])]
        lines += renown.gain(s, ctx.content, "fame", t.fame_failed)
    ctx._write(TITLE.format(title=d["title"]), lines)


# ── 畫面那一份（main.difang）──


def status(ctx) -> dict:
    if not _running(ctx):
        return {}
    a = here(ctx)
    return {"difang": {"card": card(ctx, a)}} if a is not None else {}


WHO_MAX = 6  # 一幕最多畫幾枚名號印（390 寬一排），其餘寫「等 N 位」


def _who(a: DifangAffair, act: int, me: str) -> dict:
    """這一幕出過力的人：自己排第一，其餘新來的在前；不給份數、不排名次。"""
    keys = a.by_act[act - 1] if len(a.by_act) >= act else []
    order = ([me] if me in keys else []) + [k for k in reversed(keys) if k != me]
    return {"who": [a.names.get(k, k) for k in order[:WHO_MAX]], "more": max(0, len(order) - WHO_MAX)}


def card(ctx, a: DifangAffair) -> dict | None:
    d = _def(a)
    if d is None:
        return None
    key = _key(ctx)
    acts = []
    for i, x in enumerate(d["acts"][: rules.ACTS], 1):
        state = "done" if a.status == rules.DONE or i < a.act else ("now" if i == a.act and a.status == rules.OPEN else "later")
        acts.append({"name": x["name"], "line": x["line"], "state": state, **_who(a, i, key)})
    need = a.need[a.act - 1] if a.need else 1
    opts = [o.model_dump() for o in options(ctx)]
    return {
        "affair": a.affair,
        "title": d["title"],
        "hook": d["hook"],
        "region": _region_name(ctx, a.region),
        "place": _place_name(ctx, d["place"]),
        "art": d.get("art", ""),
        "status": a.status,
        "act": a.act,
        "acts": acts,
        "fill": 1.0 if a.status == rules.DONE else round(min(1.0, a.got / max(1, need)), 3),
        "foe": d["acts"][2].get("foe", ""),
        "heads": len(a.shares),
        "mine": a.shares.get(key, 0) > 0,
        "options": opts,
        "result": d["done"]["line"] if a.status == rules.DONE else d["failed"]["line"] if a.status == rules.FAILED else "",
        "last": a.last,
    }
