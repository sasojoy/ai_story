"""輿圖升級的資料（docs/superpowers/specs/2026-10-15-輿圖升級-design.md 第九節）：
- 底圖（base）：一張只有紙、大區、山河、路的 SVG（mapview.render_base），加上地點、路、大區的清單；伺服器照開放的地點（base_key）快取。
- 疊層（state）：一份 JSON：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞……；戰線、割據、本週大事、今天去哪裡出陣、每一週的地盤。
網頁照這兩份自己畫記號、抽屜與年表。純資料：不 import 網頁框架、不讀時鐘、不擲骰；要引擎才算得出來的（勝算、出陣、分鐘換算）由 Game 傳進來。"""
from __future__ import annotations

import hashlib
from collections.abc import Callable

from . import (
    atlas, bounties, calendar, conquest, equipment, figures, insights, mapart, mapview, materials, mounts, orders, rules, sensing,
    terrain, territory, timetable, week_unlock, worldgeo,
)
from . import explore_one  # 減法季探索一顆（批 2）：「多半」照出門一趟的表
from .models import Content, FactionDef, Location
from .state import GameState, Order, TerritoryWeek, WorldState

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
# 輿圖第一層（減法季整合設計第七章）：走得到的地方名字旁的「多半」兩字，照地點的小圖（城、營、寺、渡、山、野）；內容的事實，放底圖。待 joy 潤
MOSTLY = {"城": "多事", "野": "多敵", "山": "多料", "渡": "參半", "營": "多敵", "寺": "多悟"}
# 底圖的旗子（2f 補一筆）：名字旁的兩個字是看的人的（Game.map_mostly，減法季探索一顆開著才有），含接了討伐懸賞的「有賞」——網頁 nearSub 看到它就整個照
# 底圖的 mostly，不再自己因為疊層的 bounty 含「討伐」就寫「有賞」（必敗放開時鈕上照表，名字旁也要照表）。關著的季、序章沒有這個鍵，網頁照舊
VIEWER_MOSTLY = "viewer_mostly"
# 四格探索那一格的小字（減法季整合設計 6.3「這裡多半給什麼」；批 5）：腳下這一處照小圖寫一句，同一張表加地點的字。待 joy 潤
MOSTLY_HERE = {"城": "城裡多事", "野": "野外多敵", "山": "山裡多料", "渡": "渡口參半", "營": "營裡多敵", "寺": "寺裡多悟"}
# 本週要去的那一處那一句為什麼（減法季整合設計第七章第 1 條；來源照本週卡：軍令、懸賞、主線）。待 joy 潤
WEEK_ORDER = "軍令・{title}"
WEEK_BOUNTY = "懸賞・{kind}"
WEEK_GOAL = "主線的目標"
_WORLD_CACHE: dict[str, dict] = {}


def rank_suggestions(rows: list[dict]) -> list[dict]:
    """今天去哪裡出陣列哪幾處：打得過的照分數高的在前、最多 SUGGEST_MAX 處；必敗的照樣列（軍令要你去，你自己決定要不要
    硬打），排在後面、補滿 SUGGEST_MAX，打得過的已經有那麼多處時也留分數最高的一處（多一列），不會整個不見。"""
    ordered = sorted(rows, key=lambda g: (g["lose"], -g["score"]))
    win = [g for g in ordered if not g["lose"]][:SUGGEST_MAX]
    lose = [g for g in ordered if g["lose"]]
    return win + lose[: max(1, SUGGEST_MAX - len(win))]


def mostly_here(state: GameState, content: Content) -> str:
    """腳下這一處「多半給什麼」那一句（MOSTLY_HERE；四格探索的小字，整合設計 6.3）：在路上、地點不在表上是空字串。
    減法季探索一顆開著（批 2）照出門一趟抽的那一張表（explore_one.hint_in，照表算；伺服器另用 Game.mostly_here 補上此刻的比重、「有賞」「同袍比劃」）。"""
    loc = content.locations.get(state.player.location)
    if loc is None or state.player.journey is not None:
        return ""
    if _outing_tables(state.world, content):
        return explore_one.hint_in(explore_one.kind_of(content.config.jianfa, loc))
    return MOSTLY_HERE.get(mapview.GLYPHS[mapart.icon_kind(loc)], "")


def _outing_tables(world: WorldState, content: Content) -> bool:
    """這一季的探索照出門一趟的表抽（減法季 explore_one）：「多半」照表、不照地點的小圖。"""
    return rules.jianfa(content, world, "explore_one")


def place_mostly(world: WorldState, content: Content, loc: Location, glyph: str, mostly: dict[str, str] | None = None) -> str:
    """輿圖第一層名字旁的兩個字（MOSTLY，照小圖）；減法季探索一顆開著照出門一趟（2f，FB-886）：mostly 是 Game.map_mostly 替看的人算好的
    （每一處「站過去之後」鈕上小字的最後兩個字，含危險度、有沒有對手、懸賞、自家營寨）；沒給（序章裡沒有比重可看、直接叫 mapdata 的）照地點種類的
    表（explore_one.mostly_in；幾處跟小圖不一樣：樓桑里、廣宗、草廬，寺是表上事件最大〔2e，FB-882〕）。"""
    if _outing_tables(world, content):
        if mostly is not None and loc.id in mostly:
            return mostly[loc.id]
        return explore_one.mostly_in(explore_one.kind_of(content.config.jianfa, loc))
    return MOSTLY.get(glyph, "")


def base_key(state: GameState, content: Content, mostly: dict[str, str] | None = None) -> str:
    """底圖的快取鍵：開放的地點（劇情開放了新地點才換）。減法季探索一顆開著的季，名字旁的「多半」照出門一趟（place_mostly），鍵多一段
    「|出門」，跟關著的季的底圖分開快取（關著的鍵一個字不變）。mostly 給了（看的人的那一份，Game.map_mostly）鍵再多一段每一處的字：
    網頁拿疊層（/api/map/state）的 key 跟手上的底圖比，不一樣才重抓，所以字變了（換了陣營、接了懸賞、地盤易手）網頁才會換上新的字。"""
    shown = mapview.open_places(state, content)
    places = ",".join(shown) + ("|出門" if _outing_tables(state.world, content) else "")
    if mostly:
        places += "|" + ",".join(f"{loc_id}={mostly[loc_id]}" for loc_id in shown if loc_id in mostly)
    return hashlib.sha1(places.encode()).hexdigest()[:12]


def with_mostly(core: dict, key: str, mostly: dict[str, str]) -> dict:
    """底圖（base，快取起來每個人共用的那一份）換上看的人的名字旁：新的 dict，只有 key 與 places 是新的（山河的圖、路、大區、天下圖還是同一份物件，
    不重畫、不重複存）。沒在 mostly 裡的地點照原樣。同 base(…, mostly)，多一個 VIEWER_MOSTLY 的旗子。"""
    places = [{**p, "mostly": mostly[p["id"]]} if p["id"] in mostly and mostly[p["id"]] != p["mostly"] else p for p in core["places"]]
    return {**core, "key": key, "places": places, VIEWER_MOSTLY: True}


def insight_pool(loc: Location, content: Content) -> list[str]:
    """這一處悟得到的意境（意境提示設計第六節）：照 insights.explore_gives，最濃的排第一；序章草廬走寫死的四景、不抽池子，不列
    （同 atlas.insight_names）。開關不看：抽屜的「此地能悟」是補漏。"""
    if loc.prologue_only:
        return []
    gives = insights.explore_gives(loc, content)
    strong = insights.strong_of(loc, content)
    return sorted(gives, key=lambda i: i != strong)


def base(state: GameState, content: Content, mostly: dict[str, str] | None = None) -> dict:
    """底圖與清單（這裡不快取：伺服器 server.map_base_view 照 base_key 快取）。每個地點帶悟得到什麼、最濃、地形（意境提示設計第六節：
    內容的事實，不是這一刻的狀態，所以放底圖不放疊層），與地利那一行（terrain.place_line，同一個道理）。
    mostly：看的人的名字旁（Game.map_mostly，減法季探索一顆開著才有）；給了 key 也帶著它（base_key），沒給是跟人無關的那一份（伺服器快取這一份、
    每個人再換上自己的名字旁，with_mostly）。
    輿圖表現 S1 多一個鍵：view（Config.map_view 的九個數字）；其餘鍵不變（山河林與名字是 Joy 的 paint，S1 原本另送的 terrain 作廢、已拿掉）。"""
    shown = mapview.open_places(state, content)
    keep = set(shown)
    places = []
    for loc_id in shown:
        loc = content.locations[loc_id]
        region = atlas.region_of(content, loc_id)
        glyph = mapview.GLYPHS[mapart.icon_kind(loc)]
        places.append({
            "id": loc_id, "name": loc.name, "x": loc.x, "y": loc.y, "glyph": glyph, "mostly": place_mostly(state.world, content, loc, glyph, mostly),
            "big": loc.important, "region": region.id if region is not None else None,
            "insights": insight_pool(loc, content), "strong": None if loc.prologue_only else insights.strong_of(loc, content),
            "terrain": next(iter(sensing.terrain_tags(loc)), ""),
            "terrain_arts": terrain.place_line(content, loc_id),  # 地利那一行（武學隨地理環境）；沒有地利是空字串
        })
    edges = [[a, z] for a in shown for z in content.locations[a].connections if a < z and z in keep]
    # 每一條路畫成哪一條二次曲線（mapart.road_control，跟底圖同一條）：第一層描「到它們的路」、本週那一處的金路照它描
    roads = [[a, z, *(round(v, 1) for v in mapart.road_control(content, a, z))] for a, z in edges]
    regions = [{
        "id": r.id, "name": r.name,
        "cx": round(sum(p[0] for p in r.points) / len(r.points)), "cy": round(sum(p[1] for p in r.points) / len(r.points)),
    } for r in content.map.regions]
    out = {
        "key": base_key(state, content, mostly), "w": content.map.width, "h": content.map.height,
        "svg": mapview.render_base(state, content), "places": places, "edges": edges, "roads": roads, "regions": regions,
        "insight_kinds": {d.id: {"name": d.name, "attribute": d.attribute} for d in content.insights.values() if d.grant is None},
        "insight_layer": content.config.insight_strong.enabled and any(p["strong"] for p in places),
        "world": world(state, content),
        "paint": paint(content),
        # 輿圖表現 S1（給 W1 以後的新圖用；svg 照舊送〔一張到底已經不讀，W4 拿掉〕）：取景與密度的數字。只看內容，跟誰在看無關
        "view": content.config.map_view.model_dump(),
    }
    if mostly is not None:
        out[VIEWER_MOSTLY] = True  # 名字旁整個是看的人的（含「有賞」）：網頁不再另判討伐；沒給的季這個鍵不存在，底圖一個字不變
    return out


def paint(content: Content) -> dict:
    """輿圖一張到底（企劃者 2026-10-30「可以 這樣改」）：網頁照這一份自己畫淡彩水墨的底圖（大區、河、山、林、山河名），烤成一張圖。
    只是內容（content/map.json），跟人無關、跟底圖一起快取。"""
    m = content.map
    return {
        "regions": [{"id": r.id, "points": r.points} for r in m.regions],
        "rivers": [{"points": r.points, "width": list(r.width), "color": r.color} for r in m.rivers],
        "terrain": [t.model_dump(exclude_none=True) for t in m.terrain],
        "labels": [{"text": x.text, "x": x.x, "y": x.y} for x in m.labels],
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
    marks: dict[str, str] = {}
    for o, spots in _order_spots(state, content, faction):
        for loc in spots:
            marks.setdefault(loc, ORDER_WORDS.get(o.template, o.template))
    return marks


def _order_spots(state: GameState, content: Content, faction: str | None) -> list[tuple[Order, list[str]]]:
    """你這一週還沒達成的每一道軍令與它在哪裡記功（_order_marks、本週那一處 _week_place 共用）。"""
    if faction is None or not orders.active(state, content):
        return []
    w, out = state.world, []
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
        out.append((o, spots))
    return out


def _week_place(state: GameState, content: Content, faction: str | None, places: dict[str, dict]) -> dict | None:
    """本週要去的那一處（減法季整合設計第七章第 1 條：輿圖第一層的金路、紅旗、「本週」朱印與一句為什麼）。來源照本週卡的先後：
    還沒達成的軍令記功的地點、揭著的懸賞交差的地點、這一幕主線的目標；同一種裡挑走得到、最近的那一處（就在這裡算 0 分）。
    都沒有（或都走不到）是 None。{"id", "why", "minutes"}"""
    def reach(loc_id: str) -> float | None:
        info = places.get(loc_id)
        if info is None:
            return None
        return 0 if info["here"] else info["minutes"]

    w = state.world

    def order_spots(o: Order, spots: list[str]) -> list[str]:
        # 守城這一週還沒有被推的塊（領地爭奪開著時 defend_places 是空的）：那條戰線上自家的地點都算，挑腳下以外最近的去守
        if spots or o.template != "defend" or o.front is None:
            return spots
        return [loc for loc in places if not places[loc]["here"] and rules.front_of(content, loc) == o.front
                and territory.controller(w, content, loc) == faction]

    groups: list[list[tuple[str, str]]] = [
        [(loc, WEEK_ORDER.format(title=orders.title(content, o))) for o, spots in _order_spots(state, content, faction)
         for loc in order_spots(o, spots)],
        [(loc, WEEK_BOUNTY.format(kind=kind)) for loc, kind in _bounty_marks(state, content).items()],
        [(loc, WEEK_GOAL) for loc in atlas.goal_places(state, content)],
    ]
    for group in groups:
        near = [(reach(loc), loc, why) for loc, why in group if reach(loc) is not None]
        if near:
            minutes, loc, why = min(near, key=lambda r: (r[0], r[1]))
            return {"id": loc, "why": why, "minutes": minutes}
    return None


def _foes(
    state: GameState, content: Content, loc: Location, odds: atlas.Odds, faction: str | None, squad_ids: list[str] | None = None,
) -> list[tuple[str, str]]:
    """這裡遇得上的隊伍與勝算（atlas.foes：自己陣營的寫「操練」），加上這週截糧帶來的敵方運糧隊（orders.extra_enemies，
    出陣攻的對手就有它）：截糧的地點歸自己時，那一處的對手就是糧隊（FB-258）。
    squad_ids 給了（FB-858）：領地爭奪開著、這一處是出陣攻（或約戰開著、此刻攻不了，FB-878），列出陣真的會打的那幾路（Game._map_foes），
    不查站的隊伍。"""
    listed = atlas.foes(content, loc, odds, faction, state.world, squad_ids)
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


YIELD_LINE = "今日產出：{items}"  # 輿圖卡的第 6 段（輿圖簡化設計 4.5、5.3）；待 joy 潤
YIELD_TIER = "{tier}素材"  # 照預設掉落表（照對手的屬性挑、不定哪一樣）
YIELD_ITEM = "{name} ×{count}"  # 寫了掉落表的素材
YIELD_MORE = "等"
YIELD_NAMES = 2  # 同一階最多寫幾樣


def yield_line(world: WorldState, content: Content, loc_id: str) -> str:
    """今日產出那一句（輿圖卡第 6 段）：站在這裡的隊伍（territory.squads_at：開季中立的區塊是中立駐軍）打贏有機會掉的素材裡最高的那一階
    （materials.possible_drops，跟真的擲骰讀同一份表）——寫了掉落表的寫素材名（同一階最多 YIELD_NAMES 樣），照預設表的寫「靈品素材」；
    開季中立的區塊剛易手照 conquest.drop_cap 夾（高階回饋暫停，翻地與爭搶）。只讀表、不擲骰、不看誰在看。沒有隊伍或一樣都掉不了是空字串。"""
    cap = conquest.drop_cap(world, content, loc_id)
    found: list[tuple[int, str | None, int]] = []
    for sid in territory.squads_at(world, content, loc_id):
        if sid in content.squads:
            found += materials.possible_drops(content.squads[sid], content, max_tier=cap)
    if not found:
        return ""
    top = max(tier for tier, _, _ in found)
    named = list(dict.fromkeys((mid, count) for tier, mid, count in found if tier == top and mid is not None))
    items = [YIELD_ITEM.format(name=content.materials[mid].name, count=count) for mid, count in named[:YIELD_NAMES]]
    if not items:
        items = [YIELD_TIER.format(tier=materials.TIER_NAMES.get(top, str(top)))]
    elif len(named) > YIELD_NAMES or any(tier == top and mid is None for tier, mid, _ in found):
        items[-1] += YIELD_MORE
    return YIELD_LINE.format(items="、".join(items))


def _titles(state: GameState, content: Content, week: int, now_week: int) -> list[str]:
    """第 week 週時刻表的大事（第一季才有）：只列已經到了的。
    「到了沒」照這一件真正的時刻（timetable.happened_at：決戰照排定的時刻、季末照排定的季末，其餘照季曆；FB-504）：時刻表決戰只寫了
    星期與鐘點，照 calendar.event_time 會被當成那一週（段）第一天就到了（7 天季第 1 天就列出長社火攻、21 天季與週末在決戰那一週
    的週一就列出）。以前的週也照它（管理者往後排到還沒到的不列）。週末 PM 2026-10-20 改修，跟 21 天季、7 天季同一個寫法：
    除了決戰與季末，其他大事的時刻就是 calendar.event_time，週末列的時刻一個字都不變。
    FB-561：管理者提早開的決戰一開就列，不等排定的時刻，FB-563：照開的那一刻（WorldState.showdown_opened_at）歸週，之後收場、
    過了週界也不換週，開打後被管理者取消、沒有結果的不列（showdowns_cancelled）；FB-562：決戰與季末歸在實際排定的時刻落的那一週
    （timetable.happened_week；被「避開半夜」或管理者挪到別週的，不照時刻表原本寫的那一週）。now_week 只留著給呼叫端對齊。
    FB-654：休季時換了程式的上一季（calendar.weekend_style）一般大事只列這一季真的結算過的（season.timeline），歸週走這一季自己的季曆，
    不列新程式時刻表上舊季沒發生過的（timetable.happened_at、happened_week）。"""
    w = state.world
    if not rules.season_one(content, w):
        return []
    return [e.title for e in timetable.events(w, content)
            if timetable.happened_week(w, content, e) == week and timetable.happened_at(w, content, e) <= w.time]


def _ropes(state: GameState, content: Content, now_week: int) -> list[dict]:
    """三條戰線（第一季）或一根黃巾聲勢（規則關著的季）：值、比上一週推了多少。繩上不掛地點（beads 是空的）：領地爭奪沒有拔河，
    地點不照戰線的門檻易手（舊的拔河 2026-10-27 拿掉）。"""
    w = state.world
    fronts = rules.front_ids(content)
    if not fronts:
        return []
    names = {t.id: t.name for t in content.scenario.trends}
    prev = territory.week_at(w, now_week - 1) if now_week > 1 else None

    def ends(line: str) -> dict:  # 繩的兩頭是誰（往 0 推的、往 100 推的；territory.sides 照劇本的 goals）：網頁不寫死官軍、黃巾
        low, high = territory.sides(content, line)
        return {"low": low, "high": high}

    if rules.season_one(content, w):
        out = []
        for line in fronts:
            value = rules.world_trend_value(w, content, line)
            before = prev.fronts.get(line, value) if prev is not None else value
            out.append({"id": line, "name": names.get(line, line), "value": value, "delta": value - before, "beads": [], **ends(line)})
        return out
    trend = rules.resolve_trend(content, w, fronts[0]) or fronts[0]
    value = rules.world_trend_value(w, content, trend)
    before = next(iter(prev.fronts.values()), value) if prev is not None and prev.fronts else value
    return [{"id": trend, "name": names.get(trend, trend), "value": value, "delta": value - before, "beads": [], **ends(fronts[0])}]


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
        # 沒人佔↔有人佔也算易手（FB-632：開季中立的地第一次被佔下，同規則那一邊 conquest._announce 發天下大事；from／to 是 None＝沒人佔）。
        # 舊拔河的季每一處每一週都有控制方，照舊只有換手
        changed = [] if before is None else [
            {"id": loc, "from": before.get(loc), "to": control.get(loc)} for loc in [*control, *(x for x in before if x not in control)]
            if before.get(loc) != control.get(loc)
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


def _flips(world: WorldState, content: Content, loc_id: str, now_week: int) -> list[dict]:
    """這個地點這一季每一次易手（第幾週、從誰到誰），照每週的快照比；有開季那一刻的就從它比起（第 1 週的易手也算，FB-264）。
    沒人佔↔有人佔也算（FB-632，from／to 是 None）；還沒記到的週（快照是 None）不算。不算誰的地盤的大本營（territory.unheld）沒有易手。"""
    if territory.unheld(world, content, loc_id):
        return []
    start = world.territory.weeks.get(territory.START_WEEK) if world.territory is not None else None
    out, known, last = [], start is not None, (start.control.get(loc_id) if start is not None else None)
    for week in range(1, now_week + 1):
        snap = territory.week_at(world, week)
        if snap is None:
            continue
        side = snap.control.get(loc_id)
        if known and side != last:
            out.append({"week": week, "from": last, "to": side})
        known, last = True, side
    return out


def flip_marks(world: WorldState, content: Content, loc_id: str) -> dict:
    """天下圖的「正在翻」「激戰」「冷卻」（輿圖簡化設計 4.1、4.3；計畫 docs/superpowers/plans/2026-10-20-輿圖v3-天下圖.md 1.3、收尾）：
    不另寫判斷，照翻地那一份畫面資料（conquest.block_view，server 的 main_view["conquest"]["blocks"] 同一個函式、同一個四捨五入）
    換成天下圖讀的名字——tug＝bars（{攻方: 進度 0～100}，只列寫出來不是 0 的；沒有是 None）、melee＝clash、cool＝cooling
    （剛易手還要幾分鐘；沒在冷卻是 None）。看的人是誰不影響這三樣（side 給 None，不算攻守推不推得動）。呼叫端只在領地爭奪開著、
    這一處是區塊時叫。
    siege（輿圖第三版第 5 批，企劃者 2026-10-22 挑 A 乙、B 甲）＝frozen 那一場攻城在哪一步：letter（下了戰書、還沒開集結：區圖名字框旁
    「戰」字印、天下圖那一格朱紅虛線框）、fight（集結・交戰中：天下圖那一格借激戰的紅光、區圖名字框一圈紅）、沒有是 None。"""
    row = conquest.block_view(world, content, loc_id, None)
    tug = {line["side"]: line["value"] for line in row["bars"] if line["value"] > 0}
    frozen = row["frozen"]
    siege = None if frozen is None else "fight" if frozen["status"] == "open" else "letter"
    return {"tug": tug or None, "melee": bool(row["clash"]), "cool": row["cooling"] or None, "siege": siege}


def state(
    state: GameState, content: Content, *, odds: Callable[..., str], sortie_mode: Callable[[str], str | None],
    sorties_left: int | None, real_minutes: Callable[[float], int], sortie_foes: Callable[[str], list[str] | None] | None = None,
    mostly: dict[str, str] | None = None, convoy: Callable[[str], bool] | None = None,
) -> dict:
    """疊層（設計第九節）。odds 是 Game.odds，照 odds(隊伍, at=地點) 問：每一處的勝算照那一處的地利算（terrain.strong_at，
    武學隨地理環境計畫第六節）；這裡記住，同一支隊伍、同一種地利只算一次；sortie_mode(地點) 是 sortie.mode 的結果；
    sorties_left 是今天還能出陣幾次（散人、出陣關著是 None）；real_minutes 把世界秒換成現實分鐘（Game._real_minutes）；
    sortie_foes(地點) 由 Game.map_state 給（FB-858，減法季 3d；每一處都問，問誰由它決定：標攻的地方，與約戰開著、此刻攻不了的敵方與中立區塊，
    FB-878）：領地爭奪開著，出陣真的會打的那幾路隊伍 id（Game._map_foes；地點卡的對手、勝算字、推薦排序都跟著它）；領地爭奪關著、沒給、
    回 None 是照舊列站的隊伍（atlas.foes）。
    mostly 是看的人的名字旁（Game.map_mostly，2f）：key 要跟他手上的底圖（同一份 mostly）對得上，字變了網頁才會重抓底圖。
    convoy(地點) 由 Game.map_state 給（FB-9005）：約戰開著、出陣標攻、這週截糧的運糧隊正打那裡經過（行動列那一格寫「出陣・截糧」、按了打運糧隊）；
    真的才在那一處多一個 "convoy": True（沒給、不是的地方一個鍵都不多），網頁的卡寫「出陣・截糧」、不掛攻的勝算。

    {"key", "now_week", "weeks_total", "season_one", "territory", "faction", "sides", "here", "stamina", "sorties_left",
     "journey": None | {"to","to_name","minutes","next_name","x","y"}, "travel_block": None | {"reason","to_jianghu"},
     "places": {地點: {"control","kind","odds","sortie","armed","minutes","stamina","order","bounty","goal","news","people","services",
                       "price","squads","danger","flips","rich","yield"} ＋ 領地爭奪開著時區塊多 "tug","melee","cool","siege"（flip_marks）},
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
    weeks_total = calendar.weeks(c, w)
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
    blocks = conquest.blocks(c) if conquest_on else {}
    places = {}
    for loc_id in shown:
        loc = c.locations[loc_id]
        here = loc_id == p.location and p.journey is None
        route = None if here else (routes.get(loc_id) if p.journey is None else atlas.way_to(s, c, loc_id))
        if route is not None and not route.path:
            route = None
        how = sortie_mode(loc_id)
        listed = _foes(s, c, loc, odds_at(loc_id), faction, sortie_foes(loc_id) if sortie_foes is not None else None)
        worst = _worst(listed)
        places[loc_id] = {
            "control": territory.controller(w, c, loc_id),
            "kind": "base" if loc_id in base_ids else "fixed" if loc_id in fixed
            else _conquest_kind(w, c, loc_id) if conquest_on  # 領地爭奪：中立地 neutral、搶得下來的陣營區塊 line（網頁照它畫灰、寫「可易手」）
            else "line" if on and territory.line_of(c, loc_id) else None,
            "odds": None if worst is None else {"word": worst[1], "tone": ODDS_TONE.get(worst[1], "ok")},
            "sortie": how,
            "armed": (loc_id in armed) if armed is not None else bool(loc.enemies),
            "minutes": None if route is None else atlas.whole_minutes(route.minutes * atlas.TIME_SHARE["walk"] * pace),
            # 走過去依序經過哪幾站（最後一個是這一處；就在這裡、走不到是空的）：第二層點一處、本週那一處的金路照它描（減法季第七章）
            "path": [] if route is None else list(route.path), "here": here,
            "stamina": None if route is None else atlas.route_stamina(s, c, route, "dash"),
            "order": order_at.get(loc_id), "bounty": bounty_at.get(loc_id),
            "goal": loc_id in goals, "news": loc_id in news, "people": people.get(loc_id, []),
            "services": _services(c, loc), "price": _price(w, c, faction, loc_id),
            "squads": [{"name": name, "odds": word} for name, word in listed],
            "danger": loc.danger, "flips": _flips(w, c, loc_id, now_week) if on else [],
            # 高級資源地（天下圖的金點，輿圖簡化設計 5.1）：開季中立的區塊，不管此刻誰佔著；領地爭奪關著的季照內容的區塊表
            "rich": conquest.start_kind(w, c, loc_id) == conquest.NEUTRAL,
            "yield": yield_line(w, c, loc_id),  # 卡上「今日產出」那一句（輿圖第三版第 4 批）；沒有是空字串
        }
        if conquest_on and loc_id in blocks:  # 「正在翻」「激戰」「冷卻」：領地爭奪關著的季沒有這三個鍵（網頁就不畫）
            places[loc_id].update(flip_marks(w, c, loc_id))
        if how == "attack" and convoy is not None and convoy(loc_id):
            places[loc_id]["convoy"] = True
    suggest = []
    for loc_id, info in places.items():
        if info["sortie"] is None:
            continue
        if conquest_on and loc_id in blocks and (conquest.cooling(w, c, loc_id) or conquest.frozen(w, loc_id) is not None):
            # 剛易手、還在冷卻：兩邊都推不動（設計 4.1），不推薦（輿圖第三版第 5 批，QA 第 4 批複驗的順帶）；被戰書凍結到那一場攻城打完
            # 也一樣推不動（設計 4.4），不推薦（FB-692）
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
        "key": base_key(s, c, mostly), "now_week": now_week, "weeks_total": weeks_total, "season_one": rules.season_one(c, w),
        "territory": on, "faction": faction, "here": p.location, "stamina": int(p.stamina), "sorties_left": sorties_left,
        # 會佔地的幾方（網頁的各佔幾處、圖例照它畫）：劇本的陣營，豪強分屬兩軍的季拿掉要依附的那一個（豪強不佔地）
        "sides": [f.id for f in c.scenario.factions if not (f.allies and rules.haoqiang_allied(c, w))],
        "journey": journey, "travel_block": None if block is None else {"reason": block.reason, "to_jianghu": block.to_jianghu},
        "places": places, "ropes": ropes,
        "geju": rules.world_trend_value(w, c, rules.GEJU) if rules.trend_shown(c, w, rules.GEJU) else None,
        "geju_side": territory.geju_side(c),  # 割據那一條曲線照誰的顏色（劇本裡推割據的那一方）
        "events": _titles(s, c, now_week, now_week), "suggest": suggest, "chart": chart,
        "start": _start_control(w, c) if on else None,
        "week": _week_place(s, c, faction, places),  # 本週要去的那一處（輿圖第一層，減法季整合設計第七章）
        "gap": week_unlock.win_gap(s, c),  # 第 3 週「離贏還差多少」，天下層戰線那裡寫（6.8；批 3c 的數字接上之前是結局門檻那一句）
        "weeks": _weeks(s, c, now_week, ropes),
    }
