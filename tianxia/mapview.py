"""地圖畫法（純字串，不依賴介面框架）：大地圖「江湖輿圖」的四個圖層，以及場景旁的大區小地圖。
要標什麼由 atlas 決定（視野、大區、路線、各圖層的資料），這裡只負責畫成 SVG。

大地圖上摸清的地點與畫出名字的未知地點包在 <g data-loc="地點 id"> 裡，介面層靠它知道點了哪個地點。
"""
from __future__ import annotations

from html import escape

from . import atlas
from .atlas import KNOWN, Odds
from .models import Content, Location, MapRegion
from .state import GameState

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
NOTE_FILL = "#8C3B2A"  # 名字底下那行小字（常出沒、最險、體力）
LABEL_SIZE = 15
NOTE_SIZE = 12
SELECTABLE = (*KNOWN, "outline")  # 點得到、選得到的地點
HIT_RADIUS = 16  # 地點可點的範圍（透明圓）
SELECT_STROKE = "#2C2C2A"
ROUTE_STROKE = "#D85A30"
TREND_RED = "#C0392B"
TREND_TINT = 0.6  # 大勢 100 時，大區顏色往紅色靠六成
TREND_TEXT = "#A32D2D"
LEGEND_STATES = [("current", "所在地"), ("visible", "看得見"), ("remembered", "去過"), ("outline", "未知")]
LEGEND_SHAPES = "■ 城鎮　◆ 門派　● 野外"
LEGEND_RING = "外圈：綠安全／橙危險／紅兇險　⚔ 可歷練"
LEGEND_LAYERS = {
    "situation": "⚑ 龍頭人物常出沒　大區越紅，大勢越凶",
    "enemies": "底色同外圈　最險：最難對付的對手與勝算",
    "story": f"★ 這一幕主線的目標　✦ 最近 {atlas.NEWS_DAYS} 天的大事與傳聞",
    "routes": "數字：走過去最省的體力　粗線：到選定地點的路",
}
MINI_SPAN = 220  # 小地圖裡，大區較長的一邊畫成多寬
MINI_PAD = 26
HINT_SPOTS = {  # 往相鄰大區的方向標在小地圖邊緣的哪裡：箭頭 → (橫向比例, 直向比例, 對齊)
    "→": (1, 0.5, "end"), "↘": (1, 1, "end"), "↓": (0.5, 1, "middle"), "↙": (0, 1, "start"),
    "←": (0, 0.5, "start"), "↖": (0, 0, "start"), "↑": (0.5, 0, "middle"), "↗": (1, 0, "end"),
}


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


def _text(
    x: float, y: float, text: str, size: int, fill: str, halo: str, anchor: str = "start", bold: bool = False,
    attrs: str = "",
) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (
        f'<text x="{x:g}" y="{y:g}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{weight}{attrs} '
        f'stroke="{halo}" stroke-width="5" stroke-linejoin="round" style="paint-order:stroke">{escape(text)}</text>'
    )


def _label(loc: Location, view: str) -> str:
    if view in KNOWN:
        return loc.name + (" ⚔" if loc.enemies else "") + ("（你）" if view == "current" else "")
    return f"{loc.name}？" if view == "outline" else ""


def _tint(color: str, value: int) -> str:
    """大勢越高，大區顏色越往紅色靠。"""
    ratio = TREND_TINT * max(0, min(100, value)) / 100
    mixed = (
        round(int(color[i:i + 2], 16) * (1 - ratio) + int(TREND_RED[i:i + 2], 16) * ratio) for i in (1, 3, 5)
    )
    return "#" + "".join(f"{v:02X}" for v in mixed)


def _legend(bg: str, top: int, width: int, layer: str) -> str:
    line = f"{LEGEND_RING}　{LEGEND_LAYERS[layer]}"
    box = min(width - 16, max(400, text_width(line, 12) + 24))
    parts = [f'<rect x="8" y="{top}" width="{box:g}" height="46" rx="6" fill="{bg}" fill-opacity="0.9"/>']
    for i, (view, text) in enumerate(LEGEND_STATES):
        x = 18 + i * 72
        parts.append(f'<circle cx="{x}" cy="{top + 13}" r="5" fill="{NODE_FILL[view]}"/>')
        parts.append(f'<text x="{x + 9}" y="{top + 17}" font-size="12" fill="#5F5E5A">{text}</text>')
    parts.append(f'<text x="{18 + len(LEGEND_STATES) * 72}" y="{top + 17}" font-size="12" fill="#5F5E5A">{LEGEND_SHAPES}</text>')
    parts.append(f'<text x="14" y="{top + 38}" font-size="12" fill="#5F5E5A">{escape(line)}</text>')
    return "".join(parts)


def _layer_marks(
    state: GameState, content: Content, layer: str, views: dict[str, str], odds: Odds | None
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """這一層要加的東西，只給摸清的地點：（名字前的記號, 名字底下的小字, 節點底色）。"""
    prefixes: dict[str, str] = {}
    notes: dict[str, str] = {}
    fills: dict[str, str] = {}
    known = [loc_id for loc_id, view in views.items() if view in KNOWN]
    if layer == "situation":
        for loc_id in known:
            people = atlas.haunters(state, content, loc_id)
            if people:
                notes[loc_id] = f"⚑ {'、'.join(people)} 常出沒"
    elif layer == "enemies":
        for loc_id in known:
            loc = content.locations[loc_id]
            fills[loc_id] = DANGER_RING[loc.danger]
            worst = atlas.worst_foe(content, loc, odds) if odds is not None else None
            if worst:
                notes[loc_id] = f"最險：{worst[0]} {worst[1]}"
    elif layer == "story":
        goals = atlas.goal_places(state, content)
        for loc_id in known:
            marks = ("★" if loc_id in goals else "") + ("✦" if atlas.recent_news(state, loc_id) else "")
            if marks:
                prefixes[loc_id] = f"{marks} "
    elif layer == "routes":
        for loc_id, route in atlas.routes(state, content).items():
            notes[loc_id] = f"{route.cost} 體力" if route.path else "所在地"
    return prefixes, notes, fills


def _route_line(state: GameState, content: Content, selected: str | None) -> str:
    """路線層：從所在地到選定地點的那條路（粗線）；選的是所在地或走不到時是空字串。"""
    route = atlas.routes(state, content).get(selected) if selected else None
    if route is None or not route.path:
        return ""
    stops = [content.locations[loc_id] for loc_id in (state.player.location, *route.path)]
    points = " ".join(f"{loc.x},{loc.y}" for loc in stops)
    return (
        f'<polyline points="{points}" fill="none" stroke="{ROUTE_STROKE}" stroke-width="5" stroke-opacity="0.7" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def render_map(
    state: GameState, content: Content, layer: str = "situation", selected: str | None = None,
    odds: Odds | None = None,
) -> str:
    """大地圖：layer 是 atlas.LAYERS 其中之一，selected 是被選的地點（加粗標示）。
    敵情層要傳 odds（Game.odds）才會寫出「最險」；其餘圖層不用、也不會算勝算。"""
    m = content.map
    bg = m.background
    views = atlas.views(state, content)
    prefixes, notes, fills = _layer_marks(state, content, layer, views, odds)
    out = [
        f'<svg viewBox="0 0 {m.width} {m.height}" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;height:auto;font-family:sans-serif">',
        f'<rect x="0" y="0" width="{m.width}" height="{m.height}" rx="12" fill="{bg}"/>',
    ]
    for region in m.regions:
        trends = atlas.region_trends(state, content, region) if layer == "situation" else []
        fill = _tint(region.fill, max(value for _, value in trends)) if trends else region.fill
        points = " ".join(f"{x},{y}" for x, y in region.points)
        out.append(f'<polygon points="{points}" fill="{fill}"/>')
        out.append(
            f'<text x="{region.label_x}" y="{region.label_y}" font-size="20" fill="{region.text_fill}">'
            f"{escape(region.name)}</text>"
        )
        if trends:
            line = "、".join(f"{name} {value}" for name, value in trends)
            x, anchor = region.label_x, "start"
            if x + text_width(line, 14) > m.width - 4:
                x, anchor = m.width - 4, "end"
            out.append(_text(x, region.label_y - 22, line, 14, TREND_TEXT, bg, anchor, bold=True))
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
    if layer == "routes":
        out.append(_route_line(state, content, selected))
    for loc in content.locations.values():
        view = views[loc.id]
        if view == "hidden":
            continue
        size = NODE_SIZE[view]
        parts = []
        if view == "current":
            parts.append(
                f'<circle cx="{loc.x}" cy="{loc.y}" r="{size + 7}" fill="none" stroke="{NODE_FILL["current"]}" stroke-width="2"/>'
            )
        shape = "wild" if view == "dot" else node_shape(loc)
        ring = DANGER_RING.get(loc.danger) if view in KNOWN else None
        parts.append(_shape(shape, loc.x, loc.y, size, fills.get(loc.id, NODE_FILL[view]), ring))
        if loc.id == selected:
            parts.append(
                f'<circle cx="{loc.x}" cy="{loc.y}" r="{size + 10}" fill="none" stroke="{SELECT_STROKE}" stroke-width="3"/>'
            )
        if view in SELECTABLE:
            hit = f'<circle cx="{loc.x}" cy="{loc.y}" r="{HIT_RADIUS}" fill="#000000" fill-opacity="0"/>'
            out.append(f'<g data-loc="{loc.id}" style="cursor:pointer">{hit}{"".join(parts)}</g>')
        else:
            out.extend(parts)
    for loc in content.locations.values():
        view = views[loc.id]
        text = _label(loc, view)
        if view == "hidden" or not text:
            continue
        text = prefixes.get(loc.id, "") + text
        note = notes.get(loc.id, "")
        font = LABEL_SIZE if view in KNOWN else LABEL_SIZE - 1
        offset = NODE_SIZE[view] + (13 if view == "current" else 6)
        x, anchor = loc.x + offset, "start"
        if x + max(text_width(text, font), text_width(note, NOTE_SIZE)) > m.width - 4:
            x, anchor = loc.x - offset, "end"
        fill = TEXT_DARK if view in KNOWN else TEXT_MUTED
        attrs = f' data-loc="{loc.id}"' if view in SELECTABLE else ""
        bold = view == "current" or loc.id == selected
        out.append(_text(x, loc.y + 5, text, font, fill, bg, anchor, bold, attrs))
        if note:
            out.append(_text(x, loc.y + 21, note, NOTE_SIZE, NOTE_FILL, bg, anchor, attrs=attrs))
    out.append(_legend(bg, m.height - 50, m.width, layer))
    out.append("</svg>")
    return "".join(out)


# ── 場景小地圖 ─────────────────────────────────────────


def _hints(state: GameState, content: Content, region: MapRegion, width: float, height: float, bg: str) -> list[str]:
    """小地圖邊緣往相鄰大區的方向，例如「↘ 太湖一帶」；同一個方向有兩區時往內疊一行。"""
    out = []
    used: dict[str, int] = {}
    for arrow, other in atlas.neighbours(state, content, region):
        fx, fy, anchor = HINT_SPOTS[arrow]
        stack = used.get(arrow, 0)
        used[arrow] = stack + 1
        x = 4 + fx * (width - 8)
        y = 16 + fy * (height - 22) + (-14 if fy == 1 else 14) * stack
        out.append(_text(x, y, f"{arrow} {other.name}", 12, TEXT_MUTED, bg, anchor))
    return out


def render_minimap(state: GameState, content: Content) -> str:
    """場景旁的小地圖：只畫所在大區的輪廓、區內摸清的地點（小點；只有重要地點與所在地寫名字）、
    沒摸清的淡點、所在地的醒目記號，以及往相鄰大區的方向。不畫路，也不寫危險、敵人、體力等數字。
    地圖沒有大區時回傳空字串。"""
    region = atlas.region_of(content, state.player.location)
    if region is None:
        return ""
    bg = content.map.background
    views = atlas.views(state, content)
    xs = [x for x, _ in region.points]
    ys = [y for _, y in region.points]
    left, top = min(xs), min(ys)
    scale = MINI_SPAN / max(max(xs) - left, max(ys) - top, 1)
    width = (max(xs) - left) * scale + 2 * MINI_PAD
    height = (max(ys) - top) * scale + 2 * MINI_PAD

    def at(x: float, y: float) -> tuple[float, float]:
        return round(MINI_PAD + (x - left) * scale, 1), round(MINI_PAD + (y - top) * scale, 1)

    outline = " ".join(f"{px:g},{py:g}" for px, py in (at(x, y) for x, y in region.points))
    out = [
        f'<svg viewBox="0 0 {width:.1f} {height:.1f}" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;height:auto;font-family:sans-serif;cursor:pointer">',
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" rx="10" fill="{bg}"/>',
        f'<polygon points="{outline}" fill="{region.fill}" stroke="{region.text_fill}" stroke-width="2"/>',
    ]
    here = content.locations[state.player.location]
    here_x = at(here.x, here.y)[0]
    labels = []
    for loc in content.locations.values():
        view = views[loc.id]
        if view == "hidden" or atlas.region_of(content, loc.id).id != region.id:
            continue
        x, y = at(loc.x, loc.y)
        if view == "current":
            out.append(f'<circle cx="{x:g}" cy="{y:g}" r="10" fill="none" stroke="{NODE_FILL["current"]}" stroke-width="2"/>')
            out.append(f'<circle cx="{x:g}" cy="{y:g}" r="5" fill="{NODE_FILL["current"]}"/>')
        elif view in KNOWN:
            out.append(f'<circle cx="{x:g}" cy="{y:g}" r="3.5" fill="{NODE_FILL[view]}"/>')
        else:
            out.append(f'<circle cx="{x:g}" cy="{y:g}" r="2.5" fill="{NODE_FILL["dot"]}" fill-opacity="0.7"/>')
        if view == "current":  # 所在地的名字寫在記號上方，不和旁邊地點的名字疊在一起
            labels.append(_text(x, y - 14, loc.name, 12, TEXT_DARK, bg, "middle", bold=True))
        elif view in KNOWN and loc.important:
            lx, anchor = x + 7, "start"
            name_w = text_width(loc.name, 12)
            if lx + name_w > width - 2 or (x < here_x and x - 7 - name_w >= 2):  # 在所在地左邊的，名字寫在左邊
                lx, anchor = x - 7, "end"
            labels.append(_text(lx, y + 4, loc.name, 12, TEXT_DARK, bg, anchor))
    out += labels
    out += _hints(state, content, region, width, height, bg)
    out.append("</svg>")
    return "".join(out)
