"""江湖頁重排送給頁面的那一格（main.jianghu）。

第一批（骨架）只要一個「開著」的記號：頁面照它換排法，資料都是 /api/main 原本就有的（status、art、scene、options）。
之後的批真的缺欄位才加在這裡，先回報 PM：
- 第五批「趕路中」的墨條（road）：/api/main 只有狀態列那一句字，沒有走到幾成，這裡照 Journey 算；疾行那一顆照輿圖詳情欄同一個算法（atlas.travel_options）。
- 第五批「行路」清單的遠路（ways）：有事要辦的地方不一定在鄰近，選項裡沒有它的「前往」；這裡給每個走得到的地方步行要多久（輿圖出發同一條路）。
"""
from __future__ import annotations

from tianxia import atlas, mounts  # 共用規則層（輿圖：路程、走法、抵達時刻；坐騎的步調）


def status(ctx) -> dict:
    out: dict = {"on": True}
    road = road_bar(ctx)
    if road:
        out["road"] = road
    elif ctx.state.player.journey is None:
        out["ways"] = ways(ctx)
    return out


def ways(ctx) -> dict[str, str]:
    """每個走得到的地方，步行要多久（「約 14 分鐘」）：行路清單裡不在鄰近、但有事要去的那幾列用。"""
    s, c = ctx.state, ctx.content
    pace = mounts.pace(s, c)  # 騎著馬步行比較快（同輿圖詳情欄）
    return {loc: atlas.mode_when(r.minutes, "walk", pace=pace) for loc, r in atlas.routes(s, c).items() if r.path}


def road_bar(ctx) -> dict | None:
    """趕路中那一條墨條：從剛經過的那一站（出發時是出發地）到終點，走掉幾成、中間各站落在哪、現實還要幾分鐘。
    第一段照 atlas.road_spot 的算法（改道出發只走剩下的那一截），之後各段照排好的抵達時刻。"""
    s, c = ctx.state, ctx.content
    j = s.player.journey
    spot = atlas.road_spot(s, c)
    if j is None or spot is None:
        return None
    first = j.reached == 0 and j.origin is not None
    share = j.share if first else 0.0
    span = atlas.travel_seconds(spot.minutes * (1 - share), j.mode, pace=j.pace)
    now = s.world.time
    left_leg = j.arrive_at[j.reached] - now
    walked = max(0.0, min(span, span - left_leg))
    last = j.last
    total = span + max(0.0, j.arrive_at[last] - j.arrive_at[j.reached])
    frac = lambda x: 0.0 if total <= 0 else round(min(1.0, max(0.0, x / total)), 3)  # noqa: E731
    stops = [{"name": c.locations[j.path[k]].name, "at": frac(span + j.arrive_at[k] - j.arrive_at[j.reached])}
             for k in range(j.reached, last)]
    end = j.path[last]
    dash = next((o for o in atlas.travel_options(s, c, end) or [] if o.mode == "dash"), None)
    return {
        "from": c.locations[spot.behind].name if spot.behind in c.locations else "",
        "to": c.locations[end].name, "dest": end, "mode": atlas.MODE_NAMES[j.mode],
        "done": frac(walked), "stops": stops, "left": ctx._real_minutes(j.arrive_at[last] - now),
        "dash": None if dash is None else {"label": dash.label, "enabled": dash.enabled},
        "art": _place_art(c, spot.behind),
    }


def _place_art(c, loc_id: str) -> str:
    """路上那一頁的底圖：剛經過那一站的畫（沒有就照大區），跟地點場景卡同一條（core/scene_view._art_place）。"""
    loc = c.locations.get(loc_id)
    if loc is None:
        return ""
    if loc.image:
        path = loc.image
    else:
        region = atlas.region_of(c, loc.id)
        path = f"places/{region.id}" if region is not None else "places/world"
    return f"/static/img/{path}.webp"
