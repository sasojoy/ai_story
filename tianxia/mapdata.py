"""輿圖升級的資料（docs/superpowers/specs/2026-10-15-輿圖升級-design.md 第九節）：
- 底圖（base）：一張只有紙、大區、山河、路的 SVG（mapview.render_base），加上地點、路、大區的清單；伺服器照開放的地點（base_key）快取。
- 疊層（state）：一份 JSON：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞……；戰線、割據、本週大事、今天去哪裡出陣、每一週的地盤。
網頁照這兩份自己畫記號、抽屜與年表。純資料：不 import 網頁框架、不讀時鐘、不擲骰；要引擎才算得出來的（勝算、出陣、分鐘換算）由 Game 傳進來。"""
from __future__ import annotations

import hashlib
from collections.abc import Callable

from . import atlas, bounties, calendar, equipment, figures, mapart, mapview, mounts, orders, rules, territory, timetable
from .models import Content, Location
from .state import GameState, TerritoryWeek, WorldState

ODDS_TONE = {"穩勝": "safe", "有把握": "safe", "五五波": "ok", "難分勝負": "ok", "凶險": "risk", "必敗": "risk", "操練": "safe"}
ODDS_SCORE = {"穩勝": 30, "有把握": 20, "五五波": 10}  # 今天去哪裡出陣的排法（設計第五節）：軍令 100、懸賞 50、勝算、減路上分鐘
ORDER_SCORE, BOUNTY_SCORE = 100, 50
ORDER_WORDS = {"siege": "攻城", "defend": "守城", "intercept": "截糧", "escort": "護糧", "strike": "打擊"}  # 待 joy 潤
BOUNTY_WORDS = {"strike": "討伐", "scout": "打探", "escort": "護送"}  # 待 joy 潤
PRICE_OWN = "自家地盤：療傷、打造、買馬便宜 {pct}%"  # 待 joy 潤
PRICE_ENEMY = "別人的地盤：療傷、打造、買馬貴 {pct}%"  # 待 joy 潤
FIXED_ROW = "只照大事易手"  # 年表最後一組（廣宗）的名字，待 joy 潤
SUGGEST_MAX = 3
LOSE_WORD = "必敗"  # 這種勝算的出陣建議照樣列，但排到最後、網頁畫淡（企劃者 10/15 從對比圖選乙）


def rank_suggestions(rows: list[dict]) -> list[dict]:
    """今天去哪裡出陣列哪幾處：打得過的照分數高的在前、最多 SUGGEST_MAX 處；必敗的照樣列（軍令要你去，你自己決定要不要
    硬打），排在後面、補滿 SUGGEST_MAX，打得過的已經有那麼多處時也留分數最高的一處（多一列），不會整個不見。"""
    ordered = sorted(rows, key=lambda g: (g["lose"], -g["score"]))
    win = [g for g in ordered if not g["lose"]][:SUGGEST_MAX]
    lose = [g for g in ordered if g["lose"]]
    return win + lose[: max(1, SUGGEST_MAX - len(win))]


def base_key(state: GameState, content: Content) -> str:
    """底圖的快取鍵：開放的地點（劇情開放了新地點才換）。"""
    return hashlib.sha1(",".join(mapview.open_places(state, content)).encode()).hexdigest()[:12]


def base(state: GameState, content: Content) -> dict:
    """底圖與清單（這裡不快取：伺服器 server.map_base_view 照 base_key 快取）。"""
    shown = mapview.open_places(state, content)
    keep = set(shown)
    places = []
    for loc_id in shown:
        loc = content.locations[loc_id]
        region = atlas.region_of(content, loc_id)
        places.append({
            "id": loc_id, "name": loc.name, "x": loc.x, "y": loc.y, "glyph": mapview.GLYPHS[mapart.icon_kind(loc)],
            "big": loc.important, "region": region.id if region is not None else None,
        })
    edges = [[a, z] for a in shown for z in content.locations[a].connections if a < z and z in keep]
    regions = [{
        "id": r.id, "name": r.name,
        "cx": round(sum(p[0] for p in r.points) / len(r.points)), "cy": round(sum(p[1] for p in r.points) / len(r.points)),
    } for r in content.map.regions]
    return {
        "key": base_key(state, content), "w": content.map.width, "h": content.map.height,
        "svg": mapview.render_base(state, content), "places": places, "edges": edges, "regions": regions,
    }


def _order_marks(state: GameState, content: Content, faction: str | None) -> dict[str, str]:
    """你這一週還沒達成的軍令在哪裡記功（地點 → 軍令名）；守城只標自家地盤上的戰線地點（不然整條戰線都掛牌）。"""
    if faction is None or not orders.active(state, content):
        return {}
    w, marks = state.world, {}
    for o in orders.current(state, content, faction):
        if o.done:
            continue
        spots: list[str] = []
        if o.template == "siege" and o.front is not None:
            spots = list(orders.siege_places(content, o.faction, o.front, w))
        elif o.template == "defend" and o.front is not None:
            spots = [loc for loc in content.locations if rules.front_of(content, loc) == o.front
                     and territory.line_of(content, loc) and territory.controller(w, content, loc) == faction]
        elif o.template == "intercept" and o.location is not None:
            spots = sorted(orders.intercept_spots(content, o.location))  # 出陣開著時只有那一處（FB-248、FB-258）
        elif o.template == "escort":
            spots = [x for x in (o.start, o.end) if x]
        elif o.template == "strike" and o.figure is not None:
            fs = figures.state_of(state, content, o.figure)
            spots = [fs.location] if fs.status == "active" and fs.location else []
        for loc in spots:
            marks.setdefault(loc, ORDER_WORDS.get(o.template, o.template))
    return marks


def _foes(state: GameState, content: Content, loc: Location, odds: atlas.Odds, faction: str | None) -> list[tuple[str, str]]:
    """這裡遇得上的隊伍與勝算（atlas.foes：自己陣營的寫「操練」），加上這週截糧帶來的敵方運糧隊（orders.extra_enemies，
    出陣攻的對手就有它）：截糧的地點歸自己時，那一處的對手就是糧隊（FB-258）。"""
    listed = atlas.foes(content, loc, odds, faction, state.world)
    names = {name for name, _ in listed}
    for sid in orders.extra_enemies(state, content, loc.id, faction):
        squad = content.squads[sid]
        if squad.name not in names:
            listed.append((squad.name, odds(sid)))
    return listed


def _worst(listed: list[tuple[str, str]]) -> tuple[str, str] | None:
    """最險的那一隊（同 atlas.worst_foe：操練不算）。"""
    fights = [foe for foe in listed if foe[1] != atlas.DRILL]
    return max(fights, key=lambda foe: atlas.ODDS_ORDER.index(foe[1])) if fights else None


def _sortie_order(state: GameState, content: Content, faction: str | None, loc_id: str, how: str | None) -> str | None:
    """在這裡出陣真的記得到的軍令（跟記功同一套判斷）：攻打贏記攻城或截糧（orders.win_counts；這裡有運糧隊就是截糧），
    守記守城（orders.duty_counts），攪局什麼都不記（FB-258、FB-259）。"""
    if how == "attack" and orders.win_counts(state, content, faction, loc_id):
        return ORDER_WORDS["intercept"] if orders.extra_enemies(state, content, loc_id, faction) else ORDER_WORDS["siege"]
    if how == "hold" and orders.duty_counts(state, content, faction, loc_id):
        return ORDER_WORDS["defend"]
    return None


def _bounty_marks(state: GameState, content: Content) -> dict[str, str]:
    """你揭著的懸賞在哪裡交差（地點 → 種類）；護送起點終點都標。"""
    marks: dict[str, str] = {}
    for b in bounties.mine(state, content):
        word = BOUNTY_WORDS.get(b.kind)
        for loc in (b.location, b.end if b.kind == "escort" else None):
            if word and loc:
                marks.setdefault(loc, word)
    return marks


def _people(state: GameState, content: Content) -> dict[str, list[str]]:
    """常出沒的龍頭人物（atlas.haunters）與此刻站在那裡的大勢人物（figures.placed_characters），同名只列一次。"""
    out = {loc_id: list(atlas.haunters(state, content, loc_id)) for loc_id in content.locations}
    for cid, loc in figures.placed_characters(state, content).items():
        if loc and cid in content.characters and content.characters[cid].name not in out.get(loc, []):
            out.setdefault(loc, []).append(content.characters[cid].name)
    return out


def _services(content: Content, loc: Location) -> list[str]:
    tags = set(loc.tags)
    smith = "城鎮" in tags and (equipment.on(content, "weapon") or equipment.on(content, "armor"))
    return [name for name, ok in (("醫館", "醫館" in tags), ("鐵匠鋪", smith), ("馬市", "馬市" in tags)) if ok]


def _price(world: WorldState, content: Content, faction: str | None, loc_id: str) -> str:
    factor = territory.price_factor(world, content, faction, loc_id)
    if factor < 1:
        return PRICE_OWN.format(pct=round((1 - factor) * 100))
    if factor > 1:
        return PRICE_ENEMY.format(pct=round((factor - 1) * 100))
    return ""


def _titles(state: GameState, content: Content, week: int, now_week: int) -> list[str]:
    """第 week 週時刻表的大事（第一季才有）：以前的週全列，這一週只列已經到了的。"""
    w = state.world
    if not rules.season_one(content, w):
        return []
    return [e.title for e in timetable.events(w, content)
            if e.week == week and (week < now_week or calendar.event_time(e, content, w) <= w.time)]


def _ropes(state: GameState, content: Content, now_week: int) -> list[dict]:
    """三條戰線（第一季）或一根黃巾聲勢（規則關著的季）：值、比上一週推了多少、繩上的可易手地點（地盤開著才有）。"""
    w = state.world
    fronts = rules.front_ids(content)
    if not fronts:
        return []
    lines = content.scenario.territory.lines if territory.on(content) else {}
    names = {t.id: t.name for t in content.scenario.trends}
    prev = territory.week_at(w, now_week - 1) if now_week > 1 else None

    def bead(loc_id: str, spots: list[str]) -> dict:
        return {"id": loc_id, "threshold": territory.threshold(spots.index(loc_id) + 1, len(spots)),
                "control": territory.controller(w, content, loc_id)}

    if rules.season_one(content, w):
        out = []
        for line in fronts:
            value = rules.world_trend_value(w, content, line)
            before = prev.fronts.get(line, value) if prev is not None else value
            spots = lines.get(line, [])
            out.append({"id": line, "name": names.get(line, line), "value": value, "delta": value - before,
                        "beads": [bead(x, spots) for x in spots]})
        return out
    trend = rules.resolve_trend(content, w, fronts[0]) or fronts[0]
    value = rules.world_trend_value(w, content, trend)
    before = next(iter(prev.fronts.values()), value) if prev is not None and prev.fronts else value
    beads = [bead(x, spots) for spots in lines.values() for x in spots]
    return [{"id": trend, "name": names.get(trend, trend), "value": value, "delta": value - before, "beads": beads}]


def _rope_values(snap: TerritoryWeek, ropes: list[dict]) -> dict[str, int | None]:
    """某一週快照裡每根繩的值：第一季照戰線；一根繩（黃巾聲勢）時三條戰線的值一樣，取第一個。"""
    first = next(iter(snap.fronts.values()), None)
    return {r["id"]: snap.fronts.get(r["id"], first) for r in ropes}


def _weeks(state: GameState, content: Content, now_week: int, ropes: list[dict]) -> list[dict]:
    """每一週週末的地盤（版圖變化）：控制方、每根繩的值、割據、大事、這一週易手的地點。地盤關著或這一季還沒算過是空的；
    第一筆快照以前的週 control 是 None（中途上線、舊存檔）。"""
    w = state.world
    if not territory.on(content) or w.territory is None:
        return []
    start = w.territory.weeks.get(territory.START_WEEK)
    out, before = [], (start.control if start is not None else None)  # 第 1 週跟開季那一刻比（FB-264）
    for week in range(1, now_week + 1):
        snap = territory.week_at(w, week)
        events = _titles(state, content, week, now_week)
        if snap is None:
            out.append({"week": week, "control": None, "ropes": {}, "geju": None, "events": events, "changed": []})
            continue
        changed = [] if before is None else [
            {"id": loc, "from": before.get(loc), "to": side} for loc, side in snap.control.items() if before.get(loc) not in (None, side)
        ]
        out.append({"week": week, "control": dict(snap.control), "ropes": _rope_values(snap, ropes), "geju": snap.geju,
                    "events": events, "changed": changed})
        before = snap.control
    return out


def _start_control(world: WorldState) -> dict[str, str] | None:
    """開季那一刻的控制方（territory.START_WEEK）；中途上線、還沒算過是 None。"""
    start = world.territory.weeks.get(territory.START_WEEK) if world.territory is not None else None
    return dict(start.control) if start is not None else None


def _flips(world: WorldState, loc_id: str, now_week: int) -> list[dict]:
    """這個地點這一季每一次易手（第幾週、從誰到誰），照每週的快照比；有開季那一刻的就從它比起（第 1 週的易手也算，FB-264）。"""
    start = world.territory.weeks.get(territory.START_WEEK) if world.territory is not None else None
    out, last = [], (start.control.get(loc_id) if start is not None else None)
    for week in range(1, now_week + 1):
        snap = territory.week_at(world, week)
        side = snap.control.get(loc_id) if snap is not None else None
        if last is not None and side is not None and side != last:
            out.append({"week": week, "from": last, "to": side})
        if side is not None:
            last = side
    return out


def state(
    state: GameState, content: Content, *, odds: atlas.Odds, sortie_mode: Callable[[str], str | None],
    sorties_left: int | None, real_minutes: Callable[[float], int],
) -> dict:
    """疊層（設計第九節）。odds 是 Game.odds（這裡記住、同一支隊伍只算一次）；sortie_mode(地點) 是 sortie.mode 的結果；
    sorties_left 是今天還能出陣幾次（散人、出陣關著是 None）；real_minutes 把世界秒換成現實分鐘（Game._real_minutes）。

    {"key", "now_week", "weeks_total", "season_one", "territory", "faction", "here", "stamina", "sorties_left",
     "journey": None | {"to","to_name","minutes","next_name","x","y"}, "travel_block": None | {"reason","to_jianghu"},
     "places": {地點: {"control","kind","odds","sortie","armed","minutes","stamina","order","bounty","goal","news","people","services",
                       "price","squads","danger","flips"}},
     "ropes": [{"id","name","value","delta","beads": [{"id","threshold","control"}]}], "geju", "events",
     "suggest": [{"id","sortie","why": [[字, 種類]],"minutes","score","lose"}], "chart": [{"name","spots"}],
     "weeks": [{"week","control","ropes","geju","events","changed"}], "start": None | {地點: 開季那一刻的控制方}}"""
    s, c, w, p = state, content, state.world, state.player
    memo: dict[str, str] = {}

    def odds_once(squad_id: str) -> str:
        if squad_id not in memo:
            memo[squad_id] = odds(squad_id)
        return memo[squad_id]

    faction, on = p.faction, territory.on(c)
    weeks_total = c.config.season_weeks
    now_week = min(calendar.point(w.time, c, w).week, weeks_total)
    shown = mapview.open_places(s, c)
    routes = atlas.routes(s, c) if p.journey is None else {}
    pace = mounts.pace(s, c)
    order_at, bounty_at = _order_marks(s, c, faction), _bounty_marks(s, c)
    goals, news, people = set(atlas.goal_places(s, c)), atlas.news_places(s, c), _people(s, c)
    armed = mapview.armed_places(s, c)  # ⚔ 標在哪裡：跟舊輿圖同一個判斷（FB-251）；出陣關著是 None，照內容的 enemies
    base_ids = territory.bases(c) if on else {}
    fixed = c.scenario.territory.fixed if on else {}
    places = {}
    for loc_id in shown:
        loc = c.locations[loc_id]
        here = loc_id == p.location and p.journey is None
        route = None if here else (routes.get(loc_id) if p.journey is None else atlas.way_to(s, c, loc_id))
        if route is not None and not route.path:
            route = None
        listed = _foes(s, c, loc, odds_once, faction)
        worst = _worst(listed)
        places[loc_id] = {
            "control": territory.controller(w, c, loc_id),
            "kind": "base" if loc_id in base_ids else "fixed" if loc_id in fixed
            else "line" if on and territory.line_of(c, loc_id) else None,
            "odds": None if worst is None else {"word": worst[1], "tone": ODDS_TONE.get(worst[1], "ok")},
            "sortie": sortie_mode(loc_id),
            "armed": (loc_id in armed) if armed is not None else bool(loc.enemies),
            "minutes": None if route is None else atlas.whole_minutes(route.minutes * atlas.TIME_SHARE["walk"] * pace),
            "stamina": None if route is None else atlas.route_stamina(s, c, route, "dash"),
            "order": order_at.get(loc_id), "bounty": bounty_at.get(loc_id),
            "goal": loc_id in goals, "news": loc_id in news, "people": people.get(loc_id, []),
            "services": _services(c, loc), "price": _price(w, c, faction, loc_id),
            "squads": [{"name": name, "odds": word} for name, word in listed],
            "danger": loc.danger, "flips": _flips(w, loc_id, now_week) if on else [],
        }
    suggest = []
    for loc_id, info in places.items():
        if info["sortie"] is None:
            continue
        # 理由只寫這一種出陣真的記得到的（FB-258、FB-259）：軍令照記功的判斷；懸賞只有討伐、只有攻打贏了才交得了；
        # 勝算只有攻才看（守、攪局不打）
        how, attack = info["sortie"], info["sortie"] == "attack"
        why, score = [], -(info["minutes"] or 0)
        counted = _sortie_order(s, c, faction, loc_id, how)
        if counted:
            why.append([f"軍令・{counted}", "order"])
            score += ORDER_SCORE
        if attack and info["bounty"] and BOUNTY_WORDS["strike"] in info["bounty"]:
            why.append([f"懸賞・{BOUNTY_WORDS['strike']}", "bounty"])
            score += BOUNTY_SCORE
        if attack and info["odds"]:
            why.append([info["odds"]["word"], info["odds"]["tone"]])
            score += ODDS_SCORE.get(info["odds"]["word"], 0)
        lose = attack and info["odds"] is not None and info["odds"]["word"] == LOSE_WORD
        suggest.append({"id": loc_id, "sortie": info["sortie"], "why": why, "minutes": info["minutes"], "score": score, "lose": lose})
    suggest = rank_suggestions(suggest)
    journey = None
    if p.journey is not None:
        j = p.journey
        spot = atlas.road_spot(s, c)
        x, y = mapview.you_point(c, spot)[:2] if spot is not None else (c.locations[p.location].x, c.locations[p.location].y)
        journey = {
            "to": j.path[j.last], "to_name": c.locations[j.path[j.last]].name, "minutes": real_minutes(j.arrive_at[j.last] - w.time),
            "next_name": c.locations[j.path[j.reached]].name if j.reached < j.last else None, "x": x, "y": y,
        }
    block = atlas.travel_block(s, c)
    ropes = _ropes(s, c, now_week)
    chart = []
    if on:
        names = {t.id: t.name for t in c.scenario.trends}
        chart = [{"name": names.get(line, line), "spots": list(spots)} for line, spots in c.scenario.territory.lines.items()]
        if fixed:
            chart.append({"name": FIXED_ROW, "spots": list(fixed)})
    return {
        "key": base_key(s, c), "now_week": now_week, "weeks_total": weeks_total, "season_one": rules.season_one(c, w),
        "territory": on, "faction": faction, "here": p.location, "stamina": int(p.stamina), "sorties_left": sorties_left,
        "journey": journey, "travel_block": None if block is None else {"reason": block.reason, "to_jianghu": block.to_jianghu},
        "places": places, "ropes": ropes,
        "geju": rules.world_trend_value(w, c, rules.GEJU) if rules.trend_shown(c, w, rules.GEJU) else None,
        "events": _titles(s, c, now_week, now_week), "suggest": suggest, "chart": chart,
        "start": _start_control(w) if on else None,
        "weeks": _weeks(s, c, now_week, ropes),
    }
