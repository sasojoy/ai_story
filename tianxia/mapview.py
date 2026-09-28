"""地圖與視野：計算玩家看得見哪些地點，並產生 SVG 地圖（純字串，不依賴介面框架）。"""
from __future__ import annotations

from html import escape

from .models import Content, Location
from .state import GameState

KNOWN = ("current", "visible", "remembered")
NODE_STYLE = {  # 顏色、半徑
    "current": ("#D85A30", 11),
    "visible": ("#1D9E75", 7),
    "remembered": ("#5DCAA5", 7),
    "outline": ("#B4B2A9", 6),
    "dot": ("#D3D1C7", 4),
}
LEGEND = [("current", "所在地"), ("visible", "看得見"), ("remembered", "去過"), ("outline", "未知")]


def vision_range(state: GameState, content: Content) -> int:
    cfg, p = content.config, state.player
    trained_qinggong = any(
        skill_id
        and content.skills[skill_id].slot == "輕功"
        and p.skills[skill_id].level >= cfg.vision_qinggong_level
        for skill_id in p.equipped
    )
    bonus = p.stats.get("fame", 0) >= cfg.vision_fame or trained_qinggong
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


def _label(loc: Location, view: str) -> str:
    if view in KNOWN:
        text = f"{loc.name} {'★' * loc.danger}" + (" ⚔" if loc.enemies else "")
        return text + ("（你）" if view == "current" else "")
    return f"{loc.name}？" if view == "outline" else ""


def render_map(state: GameState, content: Content) -> str:
    m = content.map
    visible = visible_locations(state, content)
    views = {loc_id: location_view(loc_id, state, content, visible) for loc_id in content.locations}
    out = [
        f'<svg viewBox="0 0 {m.width} {m.height}" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;height:auto;font-family:sans-serif">'
    ]
    for river in m.rivers:
        points = " ".join(f"{x},{y}" for x, y in river)
        out.append(f'<polyline points="{points}" fill="none" stroke="#85B7EB" stroke-width="6"/>')
    for label in m.labels:
        out.append(f'<text x="{label.x}" y="{label.y}" font-size="12" fill="#888780">{escape(label.text)}</text>')
    for a_id, a in content.locations.items():
        for b_id in a.connections:
            if a_id > b_id or "hidden" in (views[a_id], views[b_id]):
                continue
            b = content.locations[b_id]
            if views[a_id] in KNOWN or views[b_id] in KNOWN:
                style = 'stroke="#888780" stroke-width="1.5"'
            else:
                style = 'stroke="#D3D1C7" stroke-width="1" stroke-dasharray="3 3"'
            out.append(f'<line x1="{a.x}" y1="{a.y}" x2="{b.x}" y2="{b.y}" {style}/>')
    for loc_id, loc in content.locations.items():
        view = views[loc_id]
        if view == "hidden":
            continue
        color, radius = NODE_STYLE[view]
        out.append(f'<circle cx="{loc.x}" cy="{loc.y}" r="{radius}" fill="{color}"/>')
        text = _label(loc, view)
        if text:
            fill = "#2C2C2A" if view in KNOWN else "#888780"
            weight = ' font-weight="bold"' if view == "current" else ""
            out.append(
                f'<text x="{loc.x + radius + 4}" y="{loc.y + 4}" font-size="12" fill="{fill}"{weight}>'
                f"{escape(text)}</text>"
            )
    for i, (view, text) in enumerate(LEGEND):
        x = 10 + i * 70
        out.append(f'<circle cx="{x}" cy="12" r="5" fill="{NODE_STYLE[view][0]}"/>')
        out.append(f'<text x="{x + 9}" y="16" font-size="11" fill="#888780">{text}</text>')
    out.append("</svg>")
    return "".join(out)
