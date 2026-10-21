"""輿圖升級的資料（docs/superpowers/specs/2026-10-15-輿圖升級-design.md 第九節）：
- 底圖（base）：一張只有紙、大區、山河、路的 SVG（mapview.render_base），加上地點、路、大區的清單；伺服器照開放的地點（base_key）快取。
- 疊層（state）：一份 JSON：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞……；戰線、割據、本週大事、今天去哪裡出陣、每一週的地盤。
網頁照這兩份自己畫記號、抽屜與年表。純資料：不 import 網頁框架、不讀時鐘、不擲骰；要引擎才算得出來的（勝算、出陣、分鐘換算）由 Game 傳進來。"""
from __future__ import annotations

import hashlib
from collections.abc import Callable

from . import (
    atlas, bounties, calendar, conquest, equipment, figures, insights, mapart, mapview, mounts, orders, rules, sensing, terrain,
    territory, timetable, worldgeo,
)
from .models import Content, FactionDef, Location
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
# ── 天下圖（輿圖簡化設計 5.1、3.3；環形版 dev/map-2 的畫法，輿圖第三版第 3 批搬回真實地形）──
WORLD_MARGIN = 70  # 取景框：開放的地點外框往外加多少（地圖單位）
FALLBACK_INKS = ["#7A4E8C", "#2E7D7A", "#A0522D", "#5C6B2E", "#8C3B5A", "#3B5C8C"]  # 劇本沒寫 ink 的陣營照順序挑（待 joy 對色）
WORLD_CACHE_KEEP = 8  # 幾何照內容快取最多幾份
_WORLD_CACHE: dict[str, dict] = {}


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


def insight_pool(loc: Location, content: Content) -> list[str]:
    """這一處悟得到的意境（意境提示設計第六節）：照 insights.explore_gives，最濃的排第一；序章草廬走寫死的四景、不抽池子，不列
    （同 atlas.insight_names）。開關不看：抽屜的「此地能悟」是補漏。"""
    if loc.prologue_only:
        return []
    gives = insights.explore_gives(loc, content)
    strong = insights.strong_of(loc, content)
    return sorted(gives, key=lambda i: i != strong)


def base(state: GameState, content: Content) -> dict:
    """底圖與清單（這裡不快取：伺服器 server.map_base_view 照 base_key 快取）。每個地點帶悟得到什麼、最濃、地形（意境提示設計第六節：
    內容的事實，不是這一刻的狀態，所以放底圖不放疊層），與地利那一行（terrain.place_line，同一個道理）。"""
    shown = mapview.open_places(state, content)
    keep = set(shown)
    places = []
    for loc_id in shown:
        loc = content.locations[loc_id]
        region = atlas.region_of(content, loc_id)
        places.append({
            "id": loc_id, "name": loc.name, "x": loc.x, "y": loc.y, "glyph": mapview.GLYPHS[mapart.icon_kind(loc)],
            "big": loc.important, "region": region.id if region is not None else None,
            "insights": insight_pool(loc, content), "strong": None if loc.prologue_only else insights.strong_of(loc, content),
            "terrain": next(iter(sensing.terrain_tags(loc)), ""),
            "terrain_arts": terrain.place_line(content, loc_id),  # 地利那一行（武學隨地理環境）；沒有地利是空字串
        })
    edges = [[a, z] for a in shown for z in content.locations[a].connections if a < z and z in keep]
    regions = [{
        "id": r.id, "name": r.name,
        "cx": round(sum(p[0] for p in r.points) / len(r.points)), "cy": round(sum(p[1] for p in r.points) / len(r.points)),
    } for r in content.map.regions]
    return {
        "key": base_key(state, content), "w": content.map.width, "h": content.map.height,
        "svg": mapview.render_base(state, content), "places": places, "edges": edges, "regions": regions,
        "insight_kinds": {d.id: {"name": d.name, "attribute": d.attribute} for d in content.insights.values() if d.grant is None},
        "insight_layer": content.config.insight_strong.enabled and any(p["strong"] for p in places),
        "world": world(state, content),
    }


def ground_places(state: GameState, content: Content) -> list[str]:
    """天下圖上分地面的地點：劇本寫了區塊表就只拿區塊（鄉里結社、曹氏莊院、草廬這類不是區塊的不分地面，不然大區裡挖出一個灰洞）；
    沒寫照全部開放的地點（序章專屬的不算）。只看內容與開放的地點，跟底圖一起快取。"""
    shown = mapview.open_places(state, content)
    table = conquest.blocks(content)
    if table:
        return [x for x in shown if x in table]
    return [x for x in shown if not content.locations[x].prologue_only]


def side_inks(content: Content) -> list[dict]:
    """劇本的每一方在輿圖上的樣子（設計 3.3：顏色與幾方從劇本讀）：FactionDef.ink；沒寫的照 FALLBACK_INKS 的順序挑、
    名字照 FactionDef.name、一個字照名字的第一個字。soft、tint 沒寫照 color 往紙色淡。"""
    paper = content.map.background
    spare = iter(FALLBACK_INKS)

    def one(f: FactionDef) -> dict:
        ink = f.ink
        color = ink.color if ink is not None else next(spare, FALLBACK_INKS[-1])
        return {
            "id": f.id, "name": (ink.label if ink is not None and ink.label else f.name),
            "short": (ink.short if ink is not None and ink.short else f.name[:1]), "color": color,
            "soft": (ink.soft if ink is not None and ink.soft else mapart.mix(color, paper, 0.45)),
            "tint": (ink.tint if ink is not None and ink.tint else mapart.mix(color, paper, 0.8)),
        }

    return [one(f) for f in content.scenario.factions]


def _world_geometry(state: GameState, content: Content) -> dict:
    """取景框、大區（輪廓、面積、大區名可以擺的幾處）、地面格、相鄰的邊：只看內容與開放的地點，照內容雜湊快取（同一份內容另一局不再算）。"""
    m = content.map
    shown = mapview.open_places(state, content)
    seeds = ground_places(state, content)
    regions = [(r.id, [(float(x), float(y)) for x, y in r.points]) for r in m.regions]
    key = hashlib.sha1(repr((
        m.width, m.height, regions, [(r.id, r.name) for r in m.regions],
        [(x, content.locations[x].x, content.locations[x].y) for x in shown], seeds,
    )).encode()).hexdigest()
    if key in _WORLD_CACHE:
        return _WORLD_CACHE[key]
    box = (0.0, 0.0, float(m.width), float(m.height))
    spots = [(float(content.locations[x].x), float(content.locations[x].y)) for x in shown] or [(m.width / 2, m.height / 2)]
    x0, y0, x1, y1 = worldgeo.frame(spots, m.width, m.height, WORLD_MARGIN)
    by_region: dict[str, list[tuple[str, tuple[float, float]]]] = {r.id: [] for r in m.regions}
    for loc_id in seeds:
        region = atlas.region_of(content, loc_id)
        if region is not None:
            loc = content.locations[loc_id]
            by_region[region.id].append((loc_id, (float(loc.x), float(loc.y))))
    cells, edges = [], []
    for rid, _ in regions:
        group = by_region[rid]
        polys = worldgeo.cells([pt for _, pt in group], box)
        cells += [{"id": loc_id, "region": rid, "d": worldgeo.path([p for p, _ in poly])}
                  for (loc_id, _), poly in zip(group, polys) if poly]
        edges += [{"a": group[i][0], "b": group[j][0], "d": worldgeo.path([p, q], closed=False), "clip": rid}
                  for i, j, p, q in worldgeo.inner_edges(polys)]
    # 兩個大區相接的那一段（真實地形的五個大區互不相接，這裡是空的；劇本的大區相接時才有）
    edges += [{"a": a, "b": b, "d": worldgeo.path([p, q], closed=False), "clip": None}
              for a, b, p, q in worldgeo.cross_edges(regions, by_region, box)]
    out = {
        "frame": [round(x0), round(y0), round(x1 - x0), round(y1 - y0)],
        "regions": [{
            "id": r.id, "name": r.name, "d": worldgeo.path(pts), "area": round(worldgeo.area(pts)),
            "spots": [list(p) for p in worldgeo.label_spots(pts, (x0, y0, x1, y1), spots)],  # 大區名可以擺的幾處，好的在前（網頁照字級挑不壓字的）
        } for r, (_, pts) in zip(m.regions, regions)],
        "cells": cells, "edges": edges,
    }
    if len(_WORLD_CACHE) >= WORLD_CACHE_KEEP:
        _WORLD_CACHE.clear()
    _WORLD_CACHE[key] = out
    return out


def world(state: GameState, content: Content) -> dict:
    """天下圖要的資料（輿圖簡化設計 5.1）：幾何（_world_geometry）加劇本的每一方（side_inks）與沒人佔的顏色。誰佔著在疊層
    （state 的 places[*].control、rich），網頁照它上色。"""
    return {**_world_geometry(state, content), "sides": side_inks(content), "unheld": content.map.unheld}


def _order_marks(state: GameState, content: Content, faction: str | None) -> dict[str, str]:
    """你這一週還沒達成的軍令在哪裡記功（地點 → 軍令名）；守城只標自家地盤上的戰線地點（不然整條戰線都掛牌）。領地爭奪開著時守城只標
    自家被對面推得最高、守得動的那幾塊（orders.defend_places，跟記功、卡上寫的同一個判斷；裁決 24、FB-565，翻地與爭搶），沒有就不標。"""
    if faction is None or not orders.active(state, content):
        return {}
    w, marks = state.world, {}
    for o in orders.current(state, content, faction):
        if o.done:
            continue
        spots: list[str] = []
        if o.template == "siege" and o.front is not None:
            spots = list(orders.siege_places(content, o.faction, o.front, w))
        elif o.template == "defend" and o.front is not None and conquest.on(content, w):
            spots = orders.defend_places(content, w, o)  # 領地爭奪：自家被推得最高的那一塊（裁決 24、FB-565：列與記同一個判斷）
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
    """三條戰線（第一季）或一根黃巾聲勢（規則關著的季）：值、比上一週推了多少、繩上的可易手地點（地盤開著才有）。
    領地爭奪開著的季沒有拔河：地點不照戰線的門檻易手，繩上不掛地點（不然小方印擺在已經不作用的門檻上）。"""
    w = state.world
    fronts = rules.front_ids(content)
    if not fronts:
        return []
    lines = content.scenario.territory.lines if territory.on(content) and not conquest.on(content, w) else {}
    names = {t.id: t.name for t in content.scenario.trends}
    prev = territory.week_at(w, now_week - 1) if now_week > 1 else None

    def bead(loc_id: str, spots: list[str]) -> dict:
        return {"id": loc_id, "threshold": territory.threshold(spots.index(loc_id) + 1, len(spots)),
                "control": territory.controller(w, content, loc_id)}

    def ends(line: str) -> dict:  # 繩的兩頭是誰（往 0 推的、往 100 推的；territory.sides 照劇本的 goals）：網頁不寫死官軍、黃巾
        low, high = territory.sides(content, line)
        return {"low": low, "high": high}

    if rules.season_one(content, w):
        out = []
        for line in fronts:
            value = rules.world_trend_value(w, content, line)
            before = prev.fronts.get(line, value) if prev is not None else value
            spots = lines.get(line, [])
            out.append({"id": line, "name": names.get(line, line), "value": value, "delta": value - before,
                        "beads": [bead(x, spots) for x in spots], **ends(line)})
        return out
    trend = rules.resolve_trend(content, w, fronts[0]) or fronts[0]
    value = rules.world_trend_value(w, content, trend)
    before = next(iter(prev.fronts.values()), value) if prev is not None and prev.fronts else value
    beads = [bead(x, spots) for spots in lines.values() for x in spots]
    return [{"id": trend, "name": names.get(trend, trend), "value": value, "delta": value - before, "beads": beads, **ends(fronts[0])}]


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
    out, before = [], (_held(w, content, start.control) if start is not None else None)  # 第 1 週跟開季那一刻比（FB-264）
    for week in range(1, now_week + 1):
        snap = territory.week_at(w, week)
        events = _titles(state, content, week, now_week)
        if snap is None:
            out.append({"week": week, "control": None, "ropes": {}, "geju": None, "events": events, "changed": []})
            continue
        control = _held(w, content, snap.control)
        changed = [] if before is None else [
            {"id": loc, "from": before.get(loc), "to": side} for loc, side in control.items() if before.get(loc) not in (None, side)
        ]
        out.append({"week": week, "control": control, "ropes": _rope_values(snap, ropes), "geju": snap.geju,
                    "events": events, "changed": changed})
        before = control
    return out


def _conquest_kind(world: WorldState, content: Content, loc_id: str) -> str | None:
    """領地爭奪開著的季，地點那一格的 kind（大本營、fixed 在呼叫端先判）：開季中立的區塊 neutral（被佔下了也是，網頁的抽屜寫「開季是中立地」），
    搶得下來的陣營區塊 line（同拔河的可易手），不是區塊 None。"""
    if conquest.start_kind(world, content, loc_id) == conquest.NEUTRAL:
        return "neutral"
    return "line" if conquest.capturable(content, loc_id) else None


def _held(world: WorldState, content: Content, control: dict[str, str]) -> dict[str, str]:
    """快照裡的控制方拿掉不算誰的地盤的大本營（territory.unheld；FB-274：修好之前的快照記著豪強佔著自己的投靠點）。"""
    return {loc: side for loc, side in control.items() if not territory.unheld(world, content, loc)}


def _start_control(world: WorldState, content: Content) -> dict[str, str] | None:
    """開季那一刻的控制方（territory.START_WEEK）；中途上線、還沒算過是 None。"""
    start = world.territory.weeks.get(territory.START_WEEK) if world.territory is not None else None
    return _held(world, content, start.control) if start is not None else None


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
    state: GameState, content: Content, *, odds: Callable[..., str], sortie_mode: Callable[[str], str | None],
    sorties_left: int | None, real_minutes: Callable[[float], int],
) -> dict:
    """疊層（設計第九節）。odds 是 Game.odds，照 odds(隊伍, at=地點) 問：每一處的勝算照那一處的地利算（terrain.strong_at，
    武學隨地理環境計畫第六節）；這裡記住，同一支隊伍、同一種地利只算一次；sortie_mode(地點) 是 sortie.mode 的結果；
    sorties_left 是今天還能出陣幾次（散人、出陣關著是 None）；real_minutes 把世界秒換成現實分鐘（Game._real_minutes）。

    {"key", "now_week", "weeks_total", "season_one", "territory", "faction", "sides", "here", "stamina", "sorties_left",
     "journey": None | {"to","to_name","minutes","next_name","x","y"}, "travel_block": None | {"reason","to_jianghu"},
     "places": {地點: {"control","kind","odds","sortie","armed","minutes","stamina","order","bounty","goal","news","people","services",
                       "price","squads","danger","flips","rich"}},
     "ropes": [{"id","name","value","delta","beads": [{"id","threshold","control"}],"low","high"}], "geju", "geju_side", "events",
     "suggest": [{"id","sortie","why": [[字, 種類]],"minutes","score","lose"}], "chart": [{"name","spots"}],
     "weeks": [{"week","control","ropes","geju","events","changed"}], "start": None | {地點: 開季那一刻的控制方}}"""
    s, c, w, p = state, content, state.world, state.player
    memo: dict[tuple[str, str | None], str] = {}

    def odds_at(loc_id: str) -> atlas.Odds:
        strong = terrain.strong_at(c, loc_id)
        lie = strong.id if strong is not None else None

        def ask(squad_id: str) -> str:
            if (squad_id, lie) not in memo:
                memo[squad_id, lie] = odds(squad_id, at=loc_id)
            return memo[squad_id, lie]
        return ask

    faction, on = rules.side_of(s, c), territory.on(c)  # 豪強分屬兩軍：照依附那一軍算自家、敵方
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
    conquest_on = conquest.on(c, w)
    places = {}
    for loc_id in shown:
        loc = c.locations[loc_id]
        here = loc_id == p.location and p.journey is None
        route = None if here else (routes.get(loc_id) if p.journey is None else atlas.way_to(s, c, loc_id))
        if route is not None and not route.path:
            route = None
        listed = _foes(s, c, loc, odds_at(loc_id), faction)
        worst = _worst(listed)
        places[loc_id] = {
            "control": territory.controller(w, c, loc_id),
            "kind": "base" if loc_id in base_ids else "fixed" if loc_id in fixed
            else _conquest_kind(w, c, loc_id) if conquest_on  # 領地爭奪：中立地 neutral、搶得下來的陣營區塊 line（網頁照它畫灰、寫「可易手」）
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
            # 高級資源地（天下圖的金點，輿圖簡化設計 5.1）：開季中立的區塊，不管此刻誰佔著；領地爭奪關著的季照內容的區塊表
            "rich": conquest.start_kind(w, c, loc_id) == conquest.NEUTRAL,
            # 「正在翻」「激戰」（設計 4.1、4.3）由翻地規則那一批（dev/flip-1）在這裡補 tug（{攻方: 進度 0～100}）、melee（bool）、
            # cool（剛易手還要幾分鐘）；網頁（worldParts）沒有這幾個鍵就不畫。計畫 docs/superpowers/plans/2026-10-20-輿圖v3-天下圖.md 1.3
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
        # 會佔地的幾方（網頁的各佔幾處、圖例照它畫）：劇本的陣營，豪強分屬兩軍的季拿掉要依附的那一個（豪強不佔地）
        "sides": [f.id for f in c.scenario.factions if not (f.allies and rules.haoqiang_allied(c, w))],
        "journey": journey, "travel_block": None if block is None else {"reason": block.reason, "to_jianghu": block.to_jianghu},
        "places": places, "ropes": ropes,
        "geju": rules.world_trend_value(w, c, rules.GEJU) if rules.trend_shown(c, w, rules.GEJU) else None,
        "geju_side": territory.geju_side(c),  # 割據那一條曲線照誰的顏色（劇本裡推割據的那一方）
        "events": _titles(s, c, now_week, now_week), "suggest": suggest, "chart": chart,
        "start": _start_control(w, c) if on else None,
        "weeks": _weeks(s, c, now_week, ropes),
    }
