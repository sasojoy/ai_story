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
from .world import current_act, sim_active

DAY = 86400
KNOWN = ("current", "visible", "remembered")  # 摸清的地點
LAYERS = {"situation": "局勢", "enemies": "敵情", "story": "劇情", "routes": "路線"}
NEWS_DAYS = 3  # 劇情層的 ✦：最近幾天的大事與傳聞
LEADER_NEWS = 2  # 詳情欄每位龍頭人物最多列幾則最近提到他的傳聞
LEADER_WHO = "江湖上的龍頭人物，會自己行動，左右江湖大勢"
LEADER_QUIET = "眼下沒有動靜"
ODDS_ORDER = ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗")  # 由易到難；「最險」取排在最後的
ARROWS = ("→", "↘", "↓", "↙", "←", "↖", "↑", "↗")  # 從正東起順時針，每 45 度一個（畫面座標 y 向下）
UNKNOWN = "尚未摸清"
Odds = Callable[[str], str]  # 敵方隊伍 id → 勝算（Game.odds）
HOP_STAMINA = 5  # 每走一站扣的體力：拿掉各地點的 move_cost 之後、計時移動上線之前，先統一用原本的預設值


# ── 視野 ──────────────────────────────────────────────


def vision_range(state: GameState, content: Content) -> int:
    cfg, p = content.config, state.player
    bonus = p.stats.get("fame", 0) >= cfg.vision_fame
    return cfg.vision_base + (1 if bonus else 0)


def is_unlocked(loc: Location, state: GameState) -> bool:
    return not loc.unlock_flag or loc.unlock_flag in state.world.flags


def road_hops(state: GameState, content: Content, limit: int) -> dict[str, int]:
    """從所在地出發、只走已開放的地點，limit 站以內到得了的地點：地點 id → 最少幾站（所在地是 0）。"""
    hops = {state.player.location: 0}
    frontier = [state.player.location]
    for step in range(1, limit + 1):
        nxt = []
        for loc_id in frontier:
            for dest in content.locations[loc_id].connections:
                if dest not in hops and is_unlocked(content.locations[dest], state):
                    hops[dest] = step
                    nxt.append(dest)
        frontier = nxt
    return hops


def visible_locations(state: GameState, content: Content) -> set[str]:
    return set(road_hops(state, content, vision_range(state, content)))


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


def is_known(state: GameState, content: Content, loc_id: str) -> bool:
    """這個地點摸清了嗎（看得見或去過，而且已開放）。沒摸清的地點不能洩漏敵人、勝算、路線或名字：
    下面局勢、劇情、敵情的資料函式本身不檢查，呼叫端（圖層、詳情欄）要先用這個把關。"""
    return location_view(loc_id, state, content, visible_locations(state, content)) in KNOWN


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


def direction(start: tuple[float, float], end: tuple[float, float]) -> str:
    """從 start 看 end 的八方位箭頭。"""
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    return ARROWS[round(angle / 45) % len(ARROWS)]


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
    """常出沒在這個地點、而且已經該露面的龍頭人物名字（同名只列一次）。不檢查視野：呼叫端要先用 is_known 把關。"""
    names = [sim.name for sim in content.scenario.sim_players if loc_id in sim.haunts and sim_shown(sim, state)]
    return list(dict.fromkeys(names))


def leader_activity(state: GameState, content: Content, name: str) -> str:
    """龍頭人物現在在做什麼：他名下此刻會行動的設定（和世界模擬同一條規則，見 world.sim_active），
    寫成「每天約出手 N 次，讓某某大勢上升／下降」。只寫已浮現的大勢，隱藏大勢不提；沒有一條會行動時寫「眼下沒有動靜」。"""
    trend_names = {t.id: t.name for t in content.scenario.trends}
    revealed = state.world.revealed
    doing = []
    for sim in content.scenario.sim_players:
        if sim.name != name or not sim_active(sim, state):
            continue
        ups = [trend_names[t] for t, delta in sim.trend.items() if delta > 0 and t in revealed]
        downs = [trend_names[t] for t, delta in sim.trend.items() if delta < 0 and t in revealed]
        pushes = ([f"讓{'、'.join(ups)}上升"] if ups else []) + ([f"讓{'、'.join(downs)}下降"] if downs else [])
        doing.append("，".join([f"每天約出手 {sim.actions_per_day:g} 次", *pushes]))
    return "；".join(doing) or LEADER_QUIET


def leader_news(state: GameState, name: str) -> list[Rumor]:
    """最近提到這位龍頭人物的傳聞（不分地點、不限天數），最新的在前，最多 LEADER_NEWS 則。"""
    return [r for r in reversed(state.world.rumors) if name in r.text][:LEADER_NEWS]


def leader_text(state: GameState, content: Content, name: str) -> str:
    """詳情欄裡一位常出沒在此的龍頭人物：他是誰、現在在做什麼、最近的傳聞（沒有就不寫）。
    和 haunters 一樣不檢查視野與是否該露面：呼叫端要先把關。"""
    lines = [f"**龍頭人物**　{name}（常出沒在此）", f"- {LEADER_WHO}。", f"- 現在：{leader_activity(state, content, name)}。"]
    news = leader_news(state, name)
    if news:
        lines += ["- 最近：", *(f"  - {clock_text(r.time)}　{r.text}" for r in news)]
    return "\n".join(lines)


# ── 劇情 ──────────────────────────────────────────────


def goal_places(state: GameState, content: Content) -> list[str]:
    """目前這一幕主線的目標地點。隱藏主線要等大勢浮現、取代主線後，才會是「目前這一幕」。
    不檢查視野：呼叫端要用 is_known 把關，沒摸清的目標不能標出來。"""
    return list(current_act(state, content).places)


def recent_news(state: GameState, loc_id: str) -> list[Rumor]:
    """這個地點最近 NEWS_DAYS 天的江湖大事與傳聞，最新的在前。不檢查視野：呼叫端要先用 is_known 把關。"""
    now = state.world.time
    return [r for r in reversed(state.world.rumors) if r.location == loc_id and now - r.time <= NEWS_DAYS * DAY]


# ── 敵情 ──────────────────────────────────────────────


def foes(content: Content, loc: Location, odds: Odds) -> list[tuple[str, str]]:
    """可能遇到的敵方隊伍與勝算：（隊伍名稱, 勝算），同一隊只列一次。
    不檢查視野：呼叫端要先用 is_known 把關，沒摸清的地點不能露出敵人，也不該去算勝算。"""
    return [(content.squads[squad_id].name, odds(squad_id)) for squad_id in dict.fromkeys(loc.enemies)]


def worst_foe(content: Content, loc: Location, odds: Odds) -> tuple[str, str] | None:
    """最難對付的對手與勝算（勝算最差的；一樣差取排在前面的）；沒有敵人時為 None。
    不檢查視野：呼叫端要先用 is_known 把關（同 foes）。"""
    listed = foes(content, loc, odds)
    return max(listed, key=lambda foe: ODDS_ORDER.index(foe[1])) if listed else None


# ── 路線與安排前往 ────────────────────────────────────


def leg_minutes(content: Content, a: str, b: str) -> float:
    """相鄰兩地 a、b 之間的路程（步行幾分鐘）：地圖上的距離 × 路的種類係數 × 換算比例（地圖擴充設計 3.1）。"""
    cfg = content.config
    start, end = content.locations[a], content.locations[b]
    distance = math.hypot(start.x - end.x, start.y - end.y)
    return distance * cfg.road_factor[start.road_to(b)] * cfg.travel_minutes_per_unit


@dataclass(frozen=True)
class Route:
    path: tuple[str, ...]  # 依序要走的地點，最後一個是目的地（不含所在地）；所在地本身是空的
    cost: int  # 每一站 HOP_STAMINA 的加總

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
                heapq.heappush(heap, (cost + HOP_STAMINA, hops + 1, path + (dest,), dest))
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
    if state.player.stamina < HOP_STAMINA:
        return f"體力不足，第一站要 {HOP_STAMINA} 體力", False
    return f"安排前往（約 {route.cost} 體力）", True


# ── 畫面文字 ──────────────────────────────────────────


def header_text(state: GameState, content: Content) -> str:
    """大地圖頁面上方：目前時間與體力。"""
    return f"⏳ {clock_text(state.world.time)}　**體力** {int(state.player.stamina)} / {content.config.stamina_max}"


def _names(content: Content, loc_ids) -> str:
    return "、".join(content.locations[loc_id].name for loc_id in loc_ids)


def detail_text(state: GameState, content: Content, loc_id: str, odds: Odds) -> str:
    """詳情欄（Markdown）：局勢（含常出沒在此的龍頭人物是誰、現在在做什麼、最近的傳聞）、敵情、劇情、路線。
    沒摸清的地點只寫「尚未摸清」，也不算勝算。"""
    loc = content.locations[loc_id]
    if not is_known(state, content, loc_id):
        # 只有畫出輪廓的未知重要地點才有名字；淡點與未開放的地點連名字都不能露
        outlined = views(state, content)[loc_id] == "outline"
        return f"### {loc.name if outlined else ''}？\n\n{UNKNOWN}"
    here = loc_id == state.player.location
    parts = [f"### {loc.name}" + ("（所在地）" if here else "") + f"　危險 {'★' * loc.danger}"]

    region = region_of(content, loc_id)
    situation = []
    if region is not None:
        trends = "、".join(f"{name} {value}" for name, value in region_trends(state, content, region))
        situation.append(region.name + (f"（{trends}）" if trends else ""))
    people = haunters(state, content, loc_id)
    if not people:
        situation.append("沒有龍頭人物在此出沒")
    if situation:
        parts.append("**局勢**　" + "　｜　".join(situation))
    parts += [leader_text(state, content, name) for name in people]  # 常出沒的人物併在這裡說明，不另外列名字

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
