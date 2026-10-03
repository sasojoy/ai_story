"""地圖畫法（純字串，不依賴介面框架）：大地圖「江湖輿圖」的四個圖層，以及場景旁以你為中心的小地圖。
要標什麼由 atlas 決定（視野、大區、路線、各圖層的資料），這裡只負責畫成 SVG。

大地圖上摸清的地點與畫出名字的未知地點包在 <g data-loc="地點 id"> 裡，介面層靠它知道點了哪個地點。
"""
from __future__ import annotations

import math
from html import escape

from . import atlas
from .atlas import KNOWN, Odds
from .models import Content, Location, MapLabel, MapLayout, MapRegion
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
REGION_SIZE = 20  # 大區名稱
TREND_SIZE = 14  # 大區名稱上方的大勢
LINE_GAP = 16  # 名字與底下小字的基線距離
ASCENT = 0.85  # 估文字範圍時，基線以上佔字級的幾成（其餘在基線以下）
LABEL_GAP = 5  # 名字離地點記號（含外圈）多遠
LABEL_PAD = 0.5  # 擺名字時，和別的文字、記號至少隔多遠
EDGE = 4  # 文字離畫布邊緣至少多遠
OUTSIDE_WEIGHT = 10  # 找不到空位時，出界比壓到別的東西更糟
SLIDE_STEP = 10  # 名字擺在地點上方或下方時，往左滑開一次滑多遠
SEARCH_LIMIT = 400  # 擺名字時最多試幾個位置，再多就改成一個一個擺
Box = tuple[float, float, float, float]  # 左、上、右、下
Spot = tuple[float, float, str]  # 文字的 x、第一行的基線 y、對齊（start／middle／end）
Label = tuple[list[tuple[str, int]], list[Spot]]  # 要擺的幾行字（文字, 字級）與依偏好排好的位置
Taken = tuple[Box, float]  # 已經佔用的範圍，與壓到它有多糟：文字比地點記號糟，記號又比外面的細圓圈糟
TEXT_WEIGHT = 4
RING_WEIGHT = 0.2
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
    "situation": "⚑ 龍頭人物（會自己行動的江湖人物）常出沒　大區越紅，大勢越凶",
    "enemies": "底色同外圈　最險：最難對付的對手與勝算",
    "story": f"★ 這一幕主線的目標　✦ 最近 {atlas.NEWS_DAYS} 天的大事與傳聞",
    "routes": "數字：步行要幾分鐘（走路程最短的路）　粗線：到選定地點的路",
}
RIVER_STROKE = "#7FA9D6"
RIVER_TEXT = "#6F93BA"
RIVER_SIZE = 13  # 河名
MINI_HEIGHT = 200  # 小地圖在畫面上固定的高度（px）；寬度隨欄寬，圖置中
MINI_HOPS = 2  # 視窗外、幾站路以內的摸清地點，在視窗邊緣標出方向
MINI_ARROWS = 4  # 視窗邊緣最多標幾個方向
ARROW_SIZE = 13  # 視窗邊緣方向的字級
ARROW_SLIDE = 6  # 方向擠不下時，沿著邊緣滑開一次滑多遠
ARROW_SLIDES = 20  # 往每一邊最多滑幾次（40 個地點的地圖，兩站外同方向的地點常常擠在同一邊）


def node_shape(loc: Location) -> str:
    if "城鎮" in loc.tags:
        return "town"
    if "門派" in loc.tags:
        return "sect"
    return "wild"


def text_width(text: str, size: int) -> float:
    """粗估文字寬度：全形字約一個字級寬，半形字約六成。地圖記號（⚑ ★ ✦ ⚔）、箭頭與全形標點在中文字型裡
    也約一個字寬，所以 U+2000 以後都算一個字級。"""
    return sum(size if ord(ch) >= 0x2000 else size * 0.6 for ch in text)


def text_box(x: float, y: float, text: str, size: int, anchor: str = "start") -> Box:
    """文字大約佔的範圍（x、y 是 <text> 的錨點與基線）：寬用 text_width 估，高就是字級。"""
    width = text_width(text, size)
    left = x - {"start": 0, "middle": width / 2, "end": width}[anchor]
    return left, y - size * ASCENT, left + width, y + size * (1 - ASCENT)


def _overlap(a: Box, b: Box) -> float:
    """兩個範圍重疊的面積。"""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _outside(box: Box, bounds: Box) -> float:
    """範圍超出 bounds 的面積。"""
    return (box[2] - box[0]) * (box[3] - box[1]) - _overlap(box, bounds)


def _lines_at(spot: Spot, lines: list[tuple[str, int]]) -> list[Box]:
    x, y, anchor = spot
    return [text_box(x, y + i * LINE_GAP, text, size, anchor) for i, (text, size) in enumerate(lines)]


def _cost(boxes: list[Box], taken: list[Taken], bounds: Box) -> float:
    """壓到 taken 的面積（依各自的權重），加上加重計算的出界面積；0 表示擺得下。"""
    cost = sum(weight * _overlap(_grow(box, LABEL_PAD), other) for box in boxes for other, weight in taken)
    return cost + OUTSIDE_WEIGHT * sum(_outside(box, bounds) for box in boxes)


def _hits(boxes: list[Box], others: list[Box]) -> bool:
    """boxes 裡有沒有哪一行壓到 others（隔不到 LABEL_PAD 也算）。"""
    return any(_overlap(_grow(box, LABEL_PAD), other) for box in boxes for other in others)


def _least(options: list[list[Box]], taken: list[Taken], bounds: Box) -> int:
    """壓得最少的位置（一樣少時取偏好前面的）。"""
    return min(range(len(options)), key=lambda k: _cost(options[k], taken, bounds))


def _place_labels(labels: list[Label], taken: list[Taken], bounds: Box) -> list[Spot]:
    """擺一組名字，回傳每個名字選中的位置。每個名字是（幾行字, 依偏好排好的位置），行與行一行一行往下排。

    要找的是每個名字都不壓到 taken、彼此不壓到、也不出界的擺法：
    1. 本來就沒有空位的名字（例如被別的地點團團圍住）先擺在壓得最少的地方，其他名字再避開它。
    2. 其餘的名字一起找：第一個（所在地）最先擺，之後每次挑剩下空位最少的先擺（一樣少時照原順序），
       免得空位被別人先佔走；每個名字都先試偏好最前的空位，後面有名字沒地方擺時才回頭改前面的選擇。
    3. 試了 SEARCH_LIMIT 個位置還找不到時，改成照同樣的順序一個一個擺，沒有空位的取壓得最少的。
    擺好的名字都會加進 taken（當成文字）。"""
    options = [[_lines_at(spot, lines) for spot in spots] for lines, spots in labels]
    areas = [_grow(_union([box for option in boxes for box in option]), LABEL_PAD) for boxes in options]
    neighbours = [[j for j, other in enumerate(areas) if j != i and _overlap(area, other)] for i, area in enumerate(areas)]
    free = []  # 每個名字還能擺的位置（依偏好）
    for area, boxes in zip(areas, options):
        near = [item for item in taken if _overlap(area, item[0])]  # 只和附近的東西比，省時間
        free.append([k for k, option in enumerate(boxes) if not _cost(option, near, bounds)])
    chosen: dict[int, int] = {}

    def take(i: int, k: int) -> None:
        chosen[i] = k
        taken.extend((box, TEXT_WEIGHT) for box in options[i][k])
        for j in neighbours[i]:
            free[j] = [n for n in free[j] if not _hits(options[j][n], options[i][k])]

    while stuck := [i for i in range(len(labels)) if i not in chosen and not free[i]]:
        take(stuck[0], _least(options[stuck[0]], taken, bounds))
    budget = [SEARCH_LIMIT]

    def search(todo: list[int], room: list[list[int]], first: bool) -> dict[int, int] | None:
        """替 todo 裡的名字各挑一個空位（名字 → 第幾個位置）；room 是每個名字還剩的空位。
        找不到或試太多次時回傳 None。"""
        if not todo:
            return {}
        i = todo[0] if first else min(todo, key=lambda j: (len(room[j]), j))
        rest = [j for j in todo if j != i]
        for k in room[i]:
            budget[0] -= 1
            if budget[0] < 0:
                return None
            after = room.copy()
            for j in neighbours[i]:
                after[j] = [n for n in room[j] if not _hits(options[j][n], options[i][k])]
            if all(after[j] for j in rest):
                found = search(rest, after, False)
                if found is not None:
                    return {i: k, **found}
        return None

    todo = [i for i in range(len(labels)) if i not in chosen]
    found = search(todo, free, True)
    if found is not None:
        for i, k in found.items():
            take(i, k)
    while todo := [i for i in todo if i not in chosen]:  # 找不到全都擺得下的擺法：一個一個擺
        i = 0 if 0 in todo else min(todo, key=lambda j: (not free[j], len(free[j]), j))
        take(i, free[i][0] if free[i] else _least(options[i], taken, bounds))
    return [labels[i][1][chosen[i]] for i in range(len(labels))]


def _union(boxes: list[Box]) -> Box:
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def _grow(box: Box, pad: float) -> Box:
    return box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad


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


def _label(loc: Location, view: str, fights: bool = True) -> str:
    """地點的名字：摸清的寫名字（fights 時有敵人的加 ⚔，所在地加「（你）」），畫出輪廓的寫「名字？」，淡點不寫。"""
    if view in KNOWN:
        return loc.name + (" ⚔" if fights and loc.enemies else "") + ("（你）" if view == "current" else "")
    return f"{loc.name}？" if view == "outline" else ""


def _tint(color: str, value: int) -> str:
    """大勢越高，大區顏色越往紅色靠。"""
    ratio = TREND_TINT * max(0, min(100, value)) / 100
    mixed = (
        round(int(color[i:i + 2], 16) * (1 - ratio) + int(TREND_RED[i:i + 2], 16) * ratio) for i in (1, 3, 5)
    )
    return "#" + "".join(f"{v:02X}" for v in mixed)


def _legend_line(layer: str) -> str:
    return f"{LEGEND_RING}　{LEGEND_LAYERS[layer]}"


def _legend_width(width: int, layer: str) -> float:
    return min(width - 16, max(400, text_width(_legend_line(layer), 12) + 24))


def _legend(bg: str, top: int, width: int, layer: str) -> str:
    line = _legend_line(layer)
    box = _legend_width(width, layer)
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
            worst = atlas.worst_foe(content, loc, odds, state.player.faction) if odds is not None else None
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
            notes[loc_id] = f"{atlas.whole_minutes(route.minutes)} 分鐘" if route.path else "所在地"
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


def _reach(loc: Location, view: str, selected: bool) -> tuple[float, float]:
    """地點記號從中心往外畫到多遠：（記號本身與危險外圈, 連同所在地、選定地點的圓圈）。"""
    size = NODE_SIZE[view]
    mark = size + (2 if view != "dot" and node_shape(loc) == "sect" else 0) + (1.5 if view in KNOWN else 0)
    ring = mark
    if view == "current":
        ring = max(ring, size + 8)  # 所在地的圓圈：半徑 size + 7，線寬 2
    if selected:
        ring = max(ring, size + 11.5)  # 選定的圓圈：半徑 size + 10，線寬 3
    return mark, ring


def _label_spots(x: int, y: int, reach: float, lines: list[tuple[str, int]], edge: float = EDGE) -> list[Spot]:
    """地點名字（連同底下的小字）可以擺的位置，依偏好排好：右、左、左下、右下；都擠不下時再試
    右邊與左邊高一行（小字在記號旁、名字在它上面）、右上、左上，最後把下方與上方的字往左滑開，
    最遠滑到 edge（文字能擺到的最左邊）。"""
    gap = reach + LABEL_GAP
    clear = reach + LABEL_PAD + 1  # 上下擺時，文字離記號中心至少多遠
    below = y + clear + lines[0][1] * ASCENT
    above = y - clear - lines[-1][1] * (1 - ASCENT) - (len(lines) - 1) * LINE_GAP
    spots = [(x + gap, y + 5, "start"), (x - gap, y + 5, "end"), (x + reach, below, "end"), (x - reach, below, "start")]
    if len(lines) > 1:
        spots += [(x + gap, y + 5 - LINE_GAP, "start"), (x - gap, y + 5 - LINE_GAP, "end")]
    spots += [(x - reach, above, "start"), (x + reach, above, "end")]
    width = max(text_width(text, size) for text, size in lines)
    lefts = [x - reach - d for d in range(SLIDE_STEP, math.ceil(width - 2 * reach), SLIDE_STEP)]
    lefts = [left for left in lefts if left >= edge]
    if x + reach - width < edge < x - reach:
        lefts.append(edge)  # 貼著畫布左邊
    return spots + [(left, base, "start") for base in (below, above) for left in lefts]


def _region_labels(
    state: GameState, content: Content, region: MapRegion, layer: str, taken: list[Taken]
) -> tuple[str, list[tuple[str, int]]]:
    """大區名稱與局勢層的大勢（名稱上方一行）；回傳 SVG 與大勢，並把兩者佔的範圍加進 taken。"""
    m = content.map
    bg = m.background
    trends = atlas.region_trends(state, content, region) if layer == "situation" else []
    out = [_text(region.label_x, region.label_y, region.name, REGION_SIZE, region.text_fill, bg)]
    taken.append((text_box(region.label_x, region.label_y, region.name, REGION_SIZE), TEXT_WEIGHT))
    if trends:
        line = "、".join(f"{name} {value}" for name, value in trends)
        x, y, anchor = region.label_x, region.label_y - 22, "start"
        if x + text_width(line, TREND_SIZE) > m.width - EDGE:
            x, anchor = m.width - EDGE, "end"
        out.append(_text(x, y, line, TREND_SIZE, TREND_TEXT, bg, anchor, bold=True))
        taken.append((text_box(x, y, line, TREND_SIZE, anchor), TEXT_WEIGHT))
    return "".join(out), trends


def _polygons(m: MapLayout, tints: dict[str, str]) -> list[str]:
    """大區的底色；tints 是換過的顏色（大區 id → 顏色），其餘照原色。"""
    return [
        f'<polygon points="{" ".join(f"{x},{y}" for x, y in region.points)}" fill="{tints.get(region.id, region.fill)}"/>'
        for region in m.regions
    ]


def _rivers(m: MapLayout) -> list[str]:
    return [
        f'<polyline points="{" ".join(f"{x},{y}" for x, y in river)}" fill="none" stroke="{RIVER_STROKE}" '
        'stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
        for river in m.rivers
    ]


def _river_label(label: MapLabel) -> tuple[str, Box]:
    """河名的 SVG 與它佔的範圍。"""
    svg = f'<text x="{label.x}" y="{label.y}" font-size="{RIVER_SIZE}" fill="{RIVER_TEXT}">{escape(label.text)}</text>'
    return svg, text_box(label.x, label.y, label.text, RIVER_SIZE)


def _roads(content: Content, views: dict[str, str]) -> list[str]:
    """地點之間的路：兩頭都畫得出來（不是未開放）才畫；有一頭摸清時是實線，不然是淡虛線。"""
    out = []
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
    return out


def _node(loc: Location, view: str, fill: str, selected: bool, taken: list[Taken]) -> tuple[list[str], float]:
    """地點記號：所在地的圓圈、依視野畫的形狀（摸清的加危險外圈）、選定的圓圈。
    把記號佔的範圍加進 taken，回傳（SVG 片段, 記號往外畫到多遠）。"""
    size = NODE_SIZE[view]
    mark, reach = _reach(loc, view, selected)
    taken.append(((loc.x - mark, loc.y - mark, loc.x + mark, loc.y + mark), 1))
    if reach > mark:  # 所在地、選定的圓圈：壓到細圓圈沒有壓到實心記號那麼糟
        taken.append(((loc.x - reach, loc.y - reach, loc.x + reach, loc.y + reach), RING_WEIGHT))
    parts = []
    if view == "current":
        parts.append(
            f'<circle cx="{loc.x}" cy="{loc.y}" r="{size + 7}" fill="none" stroke="{NODE_FILL["current"]}" stroke-width="2"/>'
        )
    shape = "wild" if view == "dot" else node_shape(loc)
    ring = DANGER_RING.get(loc.danger) if view in KNOWN else None
    parts.append(_shape(shape, loc.x, loc.y, size, fill, ring))
    if selected:
        parts.append(
            f'<circle cx="{loc.x}" cy="{loc.y}" r="{size + 10}" fill="none" stroke="{SELECT_STROKE}" stroke-width="3"/>'
        )
    return parts, reach


def render_map(
    state: GameState, content: Content, layer: str = "situation", selected: str | None = None,
    odds: Odds | None = None,
) -> str:
    """大地圖：layer 是 atlas.LAYERS 其中之一，selected 是被選的地點（加粗標示）。
    大地圖照原尺寸畫在可捲動的框裡（地圖上的遠近就是真正的路程，縮到欄寬字會太小；見地圖擴充與移動設計）。
    敵情層要傳 odds（Game.odds）才會寫出「最險」；其餘圖層不用、也不會算勝算。

    地點名字（連同底下的小字）擺在不壓到大區名稱、大勢、河名、地點記號（含所在地與選定的圓圈）、圖例與
    其他名字，也不出界的地方：所在地先擺，每個名字依序試右、左、左下、右下，擠不下再試其他位置
    （見 _label_spots、_place_labels）。選定地點的名字擺在選定圓圈外面。"""
    m = content.map
    bg = m.background
    views = atlas.views(state, content)
    prefixes, notes, fills = _layer_marks(state, content, layer, views, odds)
    legend_top = m.height - 50
    out = [
        # max-width:100% 是必要的：少了它，這個 div 會被裡面整張地圖寬的 SVG 撐開、整塊溢出版面，
        # 於是 overflow:auto 永遠不會啟動——畫面上就是「地圖超出邊界、卡住看不了」（手機實測）。
        '<div class="tx-world-map" style="overflow:auto;max-width:100%;max-height:75vh">'
        f'<svg viewBox="0 0 {m.width} {m.height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:{m.width}px;height:{m.height}px;max-width:none;font-family:sans-serif">',
        f'<rect x="0" y="0" width="{m.width}" height="{m.height}" rx="12" fill="{bg}"/>',
    ]
    taken: list[Taken] = []  # 已經佔用的範圍：擺地點名字時要避開
    region_texts = []
    tints = {}
    for region in m.regions:
        text, trends = _region_labels(state, content, region, layer, taken)
        if trends:
            tints[region.id] = _tint(region.fill, max(value for _, value in trends))
        region_texts.append(text)
    out += _polygons(m, tints)
    out += region_texts  # 大區名稱畫在所有大區上面，不會被相鄰的大區蓋住
    out += _rivers(m)
    for label in m.labels:
        text, box = _river_label(label)
        out.append(text)
        taken.append((box, TEXT_WEIGHT))
    out += _roads(content, views)
    if layer == "routes":
        out.append(_route_line(state, content, selected))
    reach: dict[str, float] = {}
    for loc in content.locations.values():
        view = views[loc.id]
        if view == "hidden":
            continue
        parts, reach[loc.id] = _node(loc, view, fills.get(loc.id, NODE_FILL[view]), loc.id == selected, taken)
        if view in SELECTABLE:
            hit = f'<circle cx="{loc.x}" cy="{loc.y}" r="{HIT_RADIUS}" fill="#000000" fill-opacity="0"/>'
            out.append(f'<g data-loc="{loc.id}" style="cursor:pointer">{hit}{"".join(parts)}</g>')
        else:
            out.extend(parts)
    taken.append(((8, legend_top, 8 + _legend_width(m.width, layer), legend_top + 46), TEXT_WEIGHT))
    here = state.player.location
    placed = []  # （地點, 狀態, 幾行字）：所在地排第一個
    for loc in sorted(content.locations.values(), key=lambda loc: loc.id != here):
        view = views[loc.id]
        text = _label(loc, view)
        if view == "hidden" or not text:
            continue
        note = notes.get(loc.id, "")
        lines = [(prefixes.get(loc.id, "") + text, LABEL_SIZE if view in KNOWN else LABEL_SIZE - 1)]
        placed.append((loc, view, lines + ([(note, NOTE_SIZE)] if note else [])))
    labels = [(lines, _label_spots(loc.x, loc.y, reach[loc.id], lines)) for loc, _, lines in placed]
    spots = _place_labels(labels, taken, (EDGE, EDGE, m.width - EDGE, m.height - EDGE))
    for (loc, view, lines), (x, y, anchor) in zip(placed, spots):
        attrs = f' data-loc="{loc.id}"' if view in SELECTABLE else ""
        (text, font), *note = lines
        bold = view == "current" or loc.id == selected
        out.append(_text(x, y, text, font, TEXT_DARK if view in KNOWN else TEXT_MUTED, bg, anchor, bold, attrs))
        for note_text, size in note:
            out.append(_text(x, y + LINE_GAP, note_text, size, NOTE_FILL, bg, anchor, attrs=attrs))
    out.append(_legend(bg, legend_top, m.width, layer))
    out.append("</svg></div>")
    return "".join(out)


# ── 場景小地圖 ─────────────────────────────────────────


def _contains(box: Box, x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _edge_targets(
    state: GameState, content: Content, views: dict[str, str], here: Location, window: Box
) -> list[Location]:
    """視窗外、MINI_HOPS 站以內（只走已開放的地點）的摸清地點：站數少的先，一樣時近的先，最多 MINI_ARROWS 個。"""
    hops = atlas.road_hops(state, content, MINI_HOPS)
    far = [
        loc for loc in content.locations.values()
        if loc.id in hops and views[loc.id] in KNOWN and not _contains(window, loc.x, loc.y)
    ]
    far.sort(key=lambda loc: (hops[loc.id], math.hypot(loc.x - here.x, loc.y - here.y)))
    return far[:MINI_ARROWS]


def _edge_spots(start: Location, end: Location, text: str, size: int, bounds: Box) -> list[Spot]:
    """視窗邊緣方向文字（置中對齊）可以擺的位置：從 start 往 end 的方向看過去、文字剛好貼著 bounds 邊緣的
    位置最優先；擠不下時沿著那條邊往兩旁滑開，近的先試。"""
    half_w, half_h = text_width(text, size) / 2, size / 2
    lo_x, hi_x = bounds[0] + half_w, bounds[2] - half_w  # 文字中心能到的範圍
    lo_y, hi_y = bounds[1] + half_h, bounds[3] - half_h
    dx, dy = end.x - start.x, end.y - start.y
    to_x = ((hi_x if dx > 0 else lo_x) - start.x) / dx if dx else math.inf  # 走多遠碰到左右邊
    to_y = ((hi_y if dy > 0 else lo_y) - start.y) / dy if dy else math.inf  # 走多遠碰到上下邊
    t = min(to_x, to_y)
    cx = min(max(start.x + t * dx, lo_x), hi_x)
    cy = min(max(start.y + t * dy, lo_y), hi_y)
    centres: list[tuple[float, float]] = []
    for shift in [0] + [sign * k * ARROW_SLIDE for k in range(1, ARROW_SLIDES + 1) for sign in (1, -1)]:
        if to_x <= to_y:  # 貼著左右邊：上下滑
            centre = (cx, min(max(cy + shift, lo_y), hi_y))
        else:  # 貼著上下邊：左右滑
            centre = (min(max(cx + shift, lo_x), hi_x), cy)
        if centre not in centres:
            centres.append(centre)
    return [(x, y + size * (ASCENT - 0.5), "middle") for x, y in centres]


def render_minimap(state: GameState, content: Content) -> str:
    """場景旁的小地圖：以所在地為中心，從大地圖截一塊 content.map.mini_window 大的視窗（超出地圖的地方填底色），
    畫法同大地圖：大區底色（照原色，不依大勢變紅）、河、路，以及整個落在視窗裡的大區名稱與河名。
    中心落在視窗裡的地點依視野畫記號：摸清的寫名字（所在地寫「名字（你）」並加粗），畫出輪廓的未知地點寫
    「名字？」，淡點不寫名字；未開放的地點與通往它的路不畫。視窗外的地點不畫記號，只有路通出去；
    其中 MINI_HOPS 站以內的摸清地點，在視窗邊緣朝它的方向寫「箭頭 名字」（見 _edge_targets）。
    不畫圖層的記號、勝算、體力、傳聞，也沒有圖例。
    名字與方向用大地圖同一套擺法（_label_spots、_place_labels），彼此不疊、也不出視窗。
    畫面上固定 MINI_HEIGHT 高、置中；平常每次重畫都會呼叫，不算勝算。"""
    m = content.map
    bg = m.background
    views = atlas.views(state, content)
    here = content.locations[state.player.location]
    width, height = m.mini_window
    left, top = here.x - width / 2, here.y - height / 2
    window = (left, top, left + width, top + height)
    bounds = _grow(window, -EDGE)
    rect = f'x="{left:g}" y="{top:g}" width="{width}" height="{height}"'
    clip = f"minimap-{here.x}-{here.y}"  # 裁切範圍的 id：同一頁有兩張同一處的小地圖時，範圍也一樣
    out = [
        f'<svg viewBox="{left:g} {top:g} {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="display:block;width:100%;height:{MINI_HEIGHT}px;font-family:sans-serif;cursor:pointer">',
        f'<defs><clipPath id="{clip}"><rect {rect} rx="10"/></clipPath></defs>',
        f'<g clip-path="url(#{clip})">',  # 圖比視窗寬時，視窗外的東西不露出來
        f'<rect {rect} fill="{bg}"/>',
        *_polygons(m, {}),
    ]
    taken: list[Taken] = []  # 已經佔用的範圍：擺名字與方向時要避開
    for region in m.regions:
        box = text_box(region.label_x, region.label_y, region.name, REGION_SIZE)
        if not _outside(box, bounds):
            out.append(_text(region.label_x, region.label_y, region.name, REGION_SIZE, region.text_fill, bg))
            taken.append((box, TEXT_WEIGHT))
    out += _rivers(m)
    for label in m.labels:
        text, box = _river_label(label)
        if not _outside(box, bounds):
            out.append(text)
            taken.append((box, TEXT_WEIGHT))
    out += _roads(content, views)
    shown = [  # 中心落在視窗裡的地點：記號就算壓到邊緣只露出一部分，也照樣寫名字
        loc for loc in content.locations.values() if views[loc.id] != "hidden" and _contains(window, loc.x, loc.y)
    ]
    reach: dict[str, float] = {}
    for loc in shown:
        view = views[loc.id]
        parts, reach[loc.id] = _node(loc, view, NODE_FILL[view], False, taken)
        out += parts
    labels: list[Label] = []
    looks = []  # 每段字的（顏色, 加粗）
    for loc in sorted(shown, key=lambda loc: loc.id != here.id):  # 所在地排第一個
        view = views[loc.id]
        text = _label(loc, view, fights=False)
        if not text:
            continue
        lines = [(text, LABEL_SIZE if view in KNOWN else LABEL_SIZE - 1)]
        labels.append((lines, _label_spots(loc.x, loc.y, reach[loc.id], lines, bounds[0])))
        looks.append((TEXT_DARK if view in KNOWN else TEXT_MUTED, view == "current"))
    for loc in _edge_targets(state, content, views, here, window):
        text = f"{atlas.direction((here.x, here.y), (loc.x, loc.y))} {loc.name}"
        labels.append(([(text, ARROW_SIZE)], _edge_spots(here, loc, text, ARROW_SIZE, bounds)))
        looks.append((TEXT_MUTED, False))
    spots = _place_labels(labels, taken, bounds)
    for ([(text, size)], _), (fill, bold), (x, y, anchor) in zip(labels, looks, spots):
        out.append(_text(x, y, text, size, fill, bg, anchor, bold))
    out.append("</g></svg>")
    return "".join(out)
