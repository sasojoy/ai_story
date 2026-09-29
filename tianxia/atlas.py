"""江湖輿圖的資料（純資料與文字，不依賴介面框架）：視野、大區歸屬、最省體力的路線、
大地圖四個圖層要標的東西、地點詳情與「安排前往」的條件。畫圖在 mapview.py。

沒摸清（看不見也沒去過）的地點在每個圖層都只畫輪廓與「？」，詳情只寫「尚未摸清」；未開放的地點照舊完全不畫。
勝算只在呼叫端傳入 odds 函式時才算（敵情層與詳情欄），平常重畫不模擬。
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass

from .battlelog import clock_text
from .models import Content, Location, MapRegion, SimPlayer
from .state import GameState, Rumor
from .world import current_act

DAY = 86400
KNOWN = ("current", "visible", "remembered")  # 摸清的地點
LAYERS = {"situation": "局勢", "enemies": "敵情", "story": "劇情", "routes": "路線"}
NEWS_DAYS = 3  # 劇情層的 ✦：最近幾天的大事與傳聞
ODDS_ORDER = ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗")  # 由易到難；「最險」取排在最後的
ARROWS = ("→", "↘", "↓", "↙", "←", "↖", "↑", "↗")  # 從正東起順時針，每 45 度一個（畫面座標 y 向下）
UNKNOWN = "尚未摸清"
Odds = Callable[[str], str]  # 敵方隊伍 id → 勝算（Game.odds）


# ── 視野 ──────────────────────────────────────────────


def vision_range(state: GameState, content: Content) -> int:
    cfg, p = content.config, state.player
    trained = any(p.skills.get(skill_id, 0) >= cfg.vision_skill_level for skill_id in cfg.vision_skills)
    bonus = p.stats.get("fame", 0) >= cfg.vision_fame or trained
    return cfg.vision_base + (1 if bonus else 0)


def is_unlocked(loc: Location, state: GameState) -> bool:
    return not loc.unlock_flag or loc.unlock_flag in state.world.flags


def visible_locations(state: GameState, content: Content) -> set[str]:
    seen = {state.player.location}
    frontier = [state.player.location]
    for _ in range(vision_range(state, content)):
        nxt = []
        for loc_id in frontier:
            for dest in content.locations[loc_id].connections:
                if dest not in seen and is_unlocked(content.locations[dest], state):
                    seen.add(dest)
                    nxt.append(dest)
        frontier = nxt
    return seen


def location_view(loc_id: str, state: GameState, content: Content, visible: set[str]) -> str:
    loc = content.locations[loc_id]
    if not is_unlocked(loc, state):
        return "hidden"
    if loc_id == state.player.location:
        return "current"
    if loc_id in visible:
        return "visible"
    if loc_id in state.player.visited:
        return "remembered"
    return "outline" if loc.important else "dot"


def views(state: GameState, content: Content) -> dict[str, str]:
    """每個地點在地圖上的樣子：current／visible／remembered（摸清）、outline（有名字的未知）、dot、hidden。"""
    visible = visible_locations(state, content)
    return {loc_id: location_view(loc_id, state, content, visible) for loc_id in content.locations}


def known_locations(state: GameState, content: Content) -> set[str]:
    """摸清的地點：看得見或去過，而且已開放。"""
    return {loc_id for loc_id, view in views(state, content).items() if view in KNOWN}


def place_choices(state: GameState, content: Content) -> list[tuple[str, str]]:
    """大地圖選得到的地點（顯示文字, 地點 id），依內容順序：摸清的寫名字（所在地另外註明），
    畫出輪廓的未知重要地點寫「名字？」；沒名字的淡點與未開放的地點不列。"""
    out = []
    for loc_id, view in views(state, content).items():
        name = content.locations[loc_id].name
        if view in KNOWN:
            out.append((name + ("（所在地）" if view == "current" else ""), loc_id))
        elif view == "outline":
            out.append((f"{name}？", loc_id))
    return out


# ── 大區 ──────────────────────────────────────────────


def _inside(x: float, y: float, points: list[list[int]]) -> bool:
    """射線法：點是否在多邊形內。"""
    inside = False
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _edge_distance(x: float, y: float, points: list[list[int]]) -> float:
    """點到多邊形邊界的最短距離。"""
    best = math.inf
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def region_of(content: Content, loc_id: str) -> MapRegion | None:
    """地點所屬的大區：座標落在哪個大區的多邊形內（依 map.json 的順序取第一個）；
    落在所有大區外時歸給邊界最近的大區（同樣近取排在前面的）。地圖沒有大區時為 None。"""
    regions = content.map.regions
    if not regions:
        return None
    loc = content.locations[loc_id]
    for region in regions:
        if _inside(loc.x, loc.y, region.points):
            return region
    return min(regions, key=lambda region: _edge_distance(loc.x, loc.y, region.points))


def region_center(region: MapRegion) -> tuple[float, float]:
    """多邊形的形心；面積為 0 時用頂點平均。"""
    points = region.points
    area = cx = cy = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if area == 0:
        return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)
    return cx / (3 * area), cy / (3 * area)


def direction(start: tuple[float, float], end: tuple[float, float]) -> str:
    """從 start 看 end 的八方位箭頭。"""
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    return ARROWS[round(angle / 45) % len(ARROWS)]


def neighbours(state: GameState, content: Content, region: MapRegion) -> list[tuple[str, MapRegion]]:
    """和這一區有已開放的道路相連的其他大區：（從這一區中心看過去的箭頭, 大區），依 map.json 順序。"""
    linked: set[str] = set()
    for loc in content.locations.values():
        if not is_unlocked(loc, state) or region_of(content, loc.id).id != region.id:
            continue
        for dest in loc.connections:
            other = region_of(content, dest)
            if other.id != region.id and is_unlocked(content.locations[dest], state):
                linked.add(other.id)
    center = region_center(region)
    return [(direction(center, region_center(r)), r) for r in content.map.regions if r.id in linked]


# ── 局勢 ──────────────────────────────────────────────


def region_trends(state: GameState, content: Content, region: MapRegion) -> list[tuple[str, int]]:
    """大區對應、而且已經浮現的大勢：（名稱, 數值）；隱藏的大勢浮現前不列。"""
    w = state.world
    names = {t.id: t.name for t in content.scenario.trends}
    return [(names[trend_id], w.trends.get(trend_id, 0)) for trend_id in region.trends if trend_id in w.revealed]


def sim_shown(sim: SimPlayer, state: GameState) -> bool:
    """龍頭人物要等他需要的隱藏大勢浮現（requires_revealed 與條件裡的 revealed_all）才標在地圖上。"""
    needed = ([sim.requires_revealed] if sim.requires_revealed else []) + sim.condition.revealed_all
    return set(needed) <= state.world.revealed


def haunters(state: GameState, content: Content, loc_id: str) -> list[str]:
    """常出沒在這個地點、而且已經該露面的龍頭人物名字（同名只列一次）。"""
    names = [sim.name for sim in content.scenario.sim_players if loc_id in sim.haunts and sim_shown(sim, state)]
    return list(dict.fromkeys(names))


# ── 劇情 ──────────────────────────────────────────────


def goal_places(state: GameState, content: Content) -> list[str]:
    """目前這一幕主線的目標地點。隱藏主線要等大勢浮現、取代主線後，才會是「目前這一幕」。"""
    return list(current_act(state, content).places)


def recent_news(state: GameState, loc_id: str) -> list[Rumor]:
    """這個地點最近 NEWS_DAYS 天的江湖大事與傳聞，最新的在前。"""
    now = state.world.time
    return [r for r in reversed(state.world.rumors) if r.location == loc_id and now - r.time <= NEWS_DAYS * DAY]


# ── 敵情 ──────────────────────────────────────────────


def foes(content: Content, loc: Location, odds: Odds) -> list[tuple[str, str]]:
    """可能遇到的敵方隊伍與勝算：（隊伍名稱, 勝算），同一隊只列一次。"""
    return [(content.squads[squad_id].name, odds(squad_id)) for squad_id in dict.fromkeys(loc.enemies)]


def worst_foe(content: Content, loc: Location, odds: Odds) -> tuple[str, str] | None:
    """最難對付的對手與勝算（勝算最差的；一樣差取排在前面的）；沒有敵人時為 None。"""
    listed = foes(content, loc, odds)
    return max(listed, key=lambda foe: ODDS_ORDER.index(foe[1])) if listed else None


# ── 路線與安排前往 ────────────────────────────────────


@dataclass(frozen=True)
class Route:
    path: tuple[str, ...]  # 依序要走的地點，最後一個是目的地（不含所在地）；所在地本身是空的
    cost: int  # 每一站 move_cost 的加總

    @property
    def via(self) -> tuple[str, ...]:
        """途經的地點（不含目的地）。"""
        return self.path[:-1]


def routes(state: GameState, content: Content) -> dict[str, Route]:
    """從所在地出發、只走摸清且已開放的地點，到每個摸清地點最省體力的走法。
    一樣省時取站數少的，再一樣時比地點 id 的順序，結果固定。"""
    allowed = known_locations(state, content)
    best: dict[str, Route] = {}
    heap: list[tuple[int, int, tuple[str, ...], str]] = [(0, 0, (), state.player.location)]
    while heap:
        cost, hops, path, here = heapq.heappop(heap)
        if here in best:
            continue
        best[here] = Route(path, cost)
        for dest in content.locations[here].connections:
            if dest in allowed and dest not in best:
                step = content.locations[dest].move_cost
                heapq.heappush(heap, (cost + step, hops + 1, path + (dest,), dest))
    return best


def travel_block(state: GameState) -> str | None:
    """現在不能安排前往的原因（賽季已結束、有事件待處理、閉關中）；可以時為 None。"""
    if state.world.ended:
        return "賽季已結束，不能安排前往"
    if state.pending_event:
        return "有事件待處理，不能安排前往"
    if state.player.busy_until is not None:
        return "閉關中，不能安排前往"
    return None


def travel_button(state: GameState, content: Content, loc_id: str) -> tuple[str, bool] | None:
    """詳情欄最下方的按鈕：（文字, 按得下去）。所在地、沒摸清或未開放的地點不顯示按鈕（None）。"""
    route = routes(state, content).get(loc_id)
    if route is None or not route.path:
        return None
    reason = travel_block(state)
    if reason:
        return reason, False
    first = content.locations[route.path[0]].move_cost
    if state.player.stamina < first:
        return f"體力不足，第一站要 {first} 體力", False
    return f"安排前往（約 {route.cost} 體力）", True


# ── 畫面文字 ──────────────────────────────────────────


def header_text(state: GameState, content: Content) -> str:
    """大地圖頁面上方：目前時間與體力。"""
    return f"⏳ {clock_text(state.world.time)}　**體力** {int(state.player.stamina)} / {content.config.stamina_max}"


def _names(content: Content, loc_ids) -> str:
    return "、".join(content.locations[loc_id].name for loc_id in loc_ids)


def detail_text(state: GameState, content: Content, loc_id: str, odds: Odds) -> str:
    """詳情欄（Markdown）：局勢、敵情、劇情、路線四方面。沒摸清的地點只寫「尚未摸清」，也不算勝算。"""
    loc = content.locations[loc_id]
    view = views(state, content)[loc_id]
    if view not in KNOWN:
        return f"### {loc.name}？\n\n{UNKNOWN}"
    here = view == "current"
    parts = [f"### {loc.name}" + ("（所在地）" if here else "") + f"　危險 {'★' * loc.danger}"]

    region = region_of(content, loc_id)
    situation = []
    if region is not None:
        trends = "、".join(f"{name} {value}" for name, value in region_trends(state, content, region))
        situation.append(region.name + (f"（{trends}）" if trends else ""))
    people = haunters(state, content, loc_id)
    situation.append(f"常出沒：{'、'.join(people)}" if people else "沒有龍頭人物在此出沒")
    parts.append("**局勢**　" + "　｜　".join(situation))

    listed = foes(content, loc, odds)
    parts.append("**敵情**　" + ("、".join(f"{name} {word}" for name, word in listed) if listed else "沒有人在這裡滋事"))

    act = current_act(state, content)
    story = [f"★ 這一幕主線的目標：{act.goal}" if loc_id in act.places else "不是這一幕主線的目標"]
    news = recent_news(state, loc_id)
    if news:
        story.append(f"✦ 最近 {NEWS_DAYS} 天的大事與傳聞：\n" + "\n".join(f"- {clock_text(r.time)}　{r.text}" for r in news))
    else:
        story.append(f"最近 {NEWS_DAYS} 天沒有大事或傳聞")
    parts.append("**劇情**　" + "\n\n".join(story))

    route = routes(state, content).get(loc_id)
    if here:
        way = "你就在這裡"
    elif route is None:
        way = "沒有摸清的路可以過去"
    else:
        way = f"約 {route.cost} 體力" + (f"，途經 {_names(content, route.via)}" if route.via else "")
    parts.append("**路線**　" + way)
    return "\n\n".join(parts)
