"""地圖與視野：計算玩家看得見哪些地點，並產生 SVG 地圖（純字串，不依賴介面框架）。"""
from __future__ import annotations

from html import escape

from .models import Content, Location
from .state import GameState

KNOWN = ("current", "visible", "remembered")
NODE_FILL = {
    "current": "#D85A30",
    "visible": "#1D9E75",
    "remembered": "#7F77DD",
    "outline": "#B4B2A9",
    "dot": "#C9C3B2",
}
NODE_SIZE = {"current": 11, "visible": 8, "remembered": 8, "outline": 7, "dot": 4}
DANGER_RING = {1: "#639922", 2: "#BA7517", 3: "#A32D2D"}
TEXT_DARK = "#2C2C2A"
TEXT_MUTED = "#8A8577"
LABEL_SIZE = 15
LEGEND_STATES = [("current", "所在地"), ("visible", "看得見"), ("remembered", "去過"), ("outline", "未知")]
LEGEND_SYMBOLS = "■ 城鎮　◆ 門派　● 野外　外圈：綠安全／橙危險／紅兇險　⚔ 可歷練"


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


def node_shape(loc: Location) -> str:
    if "城鎮" in loc.tags:
        return "town"
    if "門派" in loc.tags:
        return "sect"
    return "wild"


def text_width(text: str, size: int) -> float:
    """粗估文字寬度：全形字約一個字級寬，半形字約六成。"""
    return sum(size if ord(ch) > 0x2E7F else size * 0.6 for ch in text)


def _shape(shape: str, x: int, y: int, size: int, fill: str, ring: str | None) -> str:
    stroke = f' stroke="{ring}" stroke-width="3"' if ring else ""
    if shape == "town":
        return f'<rect x="{x - size}" y="{y - size}" width="{size * 2}" height="{size * 2}" rx="3" fill="{fill}"{stroke}/>'
    if shape == "sect":
        s = size + 2
        return f'<path d="M{x} {y - s} L{x + s} {y} L{x} {y + s} L{x - s} {y} Z" fill="{fill}"{stroke}/>'
    return f'<circle cx="{x}" cy="{y}" r="{size}" fill="{fill}"{stroke}/>'


def _text(x: float, y: float, text: str, size: int, fill: str, halo: str, anchor: str = "start", bold: bool = False) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (
        f'<text x="{x:g}" y="{y:g}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{weight} '
        f'stroke="{halo}" stroke-width="5" stroke-linejoin="round" style="paint-order:stroke">{escape(text)}</text>'
    )


def _label(loc: Location, view: str) -> str:
    if view in KNOWN:
        return loc.name + (" ⚔" if loc.enemies else "") + ("（你）" if view == "current" else "")
    return f"{loc.name}？" if view == "outline" else ""


def _legend(bg: str, top: int) -> str:
    parts = [f'<rect x="8" y="{top}" width="400" height="46" rx="6" fill="{bg}" fill-opacity="0.9"/>']
    for i, (view, text) in enumerate(LEGEND_STATES):
        x = 18 + i * 72
        parts.append(f'<circle cx="{x}" cy="{top + 13}" r="5" fill="{NODE_FILL[view]}"/>')
        parts.append(f'<text x="{x + 9}" y="{top + 17}" font-size="12" fill="#5F5E5A">{text}</text>')
    parts.append(f'<text x="14" y="{top + 38}" font-size="12" fill="#5F5E5A">{LEGEND_SYMBOLS}</text>')
    return "".join(parts)


def render_map(state: GameState, content: Content) -> str:
    m = content.map
    bg = m.background
    visible = visible_locations(state, content)
    views = {loc_id: location_view(loc_id, state, content, visible) for loc_id in content.locations}
    out = [
        f'<svg viewBox="0 0 {m.width} {m.height}" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;height:auto;font-family:sans-serif">',
        f'<rect x="0" y="0" width="{m.width}" height="{m.height}" rx="12" fill="{bg}"/>',
    ]
    for region in m.regions:
        points = " ".join(f"{x},{y}" for x, y in region.points)
        out.append(f'<polygon points="{points}" fill="{region.fill}"/>')
        out.append(
            f'<text x="{region.label_x}" y="{region.label_y}" font-size="20" fill="{region.text_fill}">'
            f"{escape(region.name)}</text>"
        )
    for river in m.rivers:
        points = " ".join(f"{x},{y}" for x, y in river)
        out.append(
            f'<polyline points="{points}" fill="none" stroke="#7FA9D6" stroke-width="8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for label in m.labels:
        out.append(f'<text x="{label.x}" y="{label.y}" font-size="13" fill="#6F93BA">{escape(label.text)}</text>')
    for a_id, a in content.locations.items():
        for b_id in a.connections:
            if a_id > b_id or "hidden" in (views[a_id], views[b_id]):
                continue
            b = content.locations[b_id]
            if views[a_id] in KNOWN or views[b_id] in KNOWN:
                style = 'stroke="#8A8577" stroke-width="2"'
            else:
                style = 'stroke="#C9C3B2" stroke-width="1.5" stroke-dasharray="4 4"'
            out.append(f'<line x1="{a.x}" y1="{a.y}" x2="{b.x}" y2="{b.y}" {style}/>')
    for loc in content.locations.values():
        view = views[loc.id]
        if view == "hidden":
            continue
        size = NODE_SIZE[view]
        if view == "current":
            out.append(f'<circle cx="{loc.x}" cy="{loc.y}" r="{size + 7}" fill="none" stroke="{NODE_FILL["current"]}" stroke-width="2"/>')
        shape = "wild" if view == "dot" else node_shape(loc)
        ring = DANGER_RING.get(loc.danger) if view in KNOWN else None
        out.append(_shape(shape, loc.x, loc.y, size, NODE_FILL[view], ring))
    for loc in content.locations.values():
        view = views[loc.id]
        text = _label(loc, view)
        if view == "hidden" or not text:
            continue
        font = LABEL_SIZE if view in KNOWN else LABEL_SIZE - 1
        offset = NODE_SIZE[view] + (13 if view == "current" else 6)
        x, anchor = loc.x + offset, "start"
        if x + text_width(text, font) > m.width - 4:
            x, anchor = loc.x - offset, "end"
        fill = TEXT_DARK if view in KNOWN else TEXT_MUTED
        out.append(_text(x, loc.y + 5, text, font, fill, bg, anchor, bold=view == "current"))
    out.append(_legend(bg, m.height - 50))
    out.append("</svg>")
    return "".join(out)
