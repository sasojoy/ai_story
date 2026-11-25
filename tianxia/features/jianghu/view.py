"""江湖頁重排送給頁面的那一格（main.jianghu）。

第一批（骨架）只要一個「開著」的記號：頁面照它換排法，資料都是 /api/main 原本就有的（status、art、scene、options）。
之後的批真的缺欄位才加在這裡，先回報 PM：
- 第五批「趕路中」的墨條（road）：/api/main 只有狀態列那一句字，沒有走到幾成，這裡照 Journey 算；疾行那一顆照輿圖詳情欄同一個算法（atlas.travel_options）。
- 第五批事件頁的小印（event）：章回寫「主線」、奇事寫「奇事」、其餘「遭遇」（PM 11/25）；/api/main 看不出眼前這一則是不是哪條線的一段。
- 第五批「行路」清單的遠路（ways）：有事要辦的地方不一定在鄰近，選項裡沒有它的「前往」；這裡給每個走得到的地方步行要多久（輿圖出發同一條路）。
- 第六批接管選單的那一刻（take）：/api/main 只有選項，看不出是哪一格接管了選單（撞見、感悟、同伴、投靠……），頁面要照它寫那一枚小印；
  照 MENU_ORDER["take"] 同一個先後問一次（店面那幾格不算：店有自己的整頁）。
"""
from __future__ import annotations

from tianxia import atlas, mounts, story_base  # 共用規則層（輿圖：路程、走法、抵達時刻；坐騎的步調；一條線走到哪）
from tianxia.core import features as features_core  # 核心：選單接管的先後表與各格


def status(ctx) -> dict:
    out: dict = {"on": True}
    kind = event_kind(ctx)
    if kind:
        out["event"] = kind
    took = take(ctx)
    if took:
        out["take"] = took
    road = road_bar(ctx)
    if road:
        out["road"] = road
    elif ctx.state.player.journey is None:
        out["ways"] = ways(ctx)
    return out


EVENT_KINDS = {"章回": "主線", "奇事": "奇事"}  # 待 joy 潤：一條線的種類 → 事件頁那一枚小印
EVENT_PLAIN = "遭遇"  # 待 joy 潤


def event_kind(ctx) -> str | None:
    """眼前端出來的事件是哪一種：某條線開著的事件段（同 story_base.stage_art 的認法）照那條線的種類，其餘是遭遇；沒有事件是 None。"""
    s, c = ctx.state, ctx.content
    if not s.pending_event:
        return None
    for progress in story_base.active(s):
        pair = story_base.current(c, progress)
        if pair is not None and progress.opened and pair[1].kind == "event":
            return EVENT_KINDS.get(pair[0].kind, EVENT_PLAIN)
    return EVENT_PLAIN


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


# 第六批：接管整個選單的那一格 → 頁上那一枚小印（待 joy 潤）。店面那幾格（懸賞榜、鐵匠鋪、馬市、搬成包的店）不在這裡：店有自己的整頁
TAKE_SEALS = {"duel": "單挑", "sense": "感悟", "talk": "同伴", "faction": "投靠", "audience": "求見", "omen": "伏筆"}  # 待 joy 潤
MENU_SEALS = {"guard": "撞見", "heroines": "奇遇", "yiwen": "異聞", "feast": "宴席", "bout": "擂台"}  # 待 joy 潤：Feature.menu 接管的那一包
STORY_SEALS = {**EVENT_KINDS, "頓悟": "頓悟"}  # 待 joy 潤
SHOP_SLOTS = ("bounties", "smithy", "gear", "shops")
# 撞見孩子那兩步（親衛隊長包，PlayerState.guard 是核心存檔欄位）：標題與圖照開場（web/img/guard/story/meet-<開場>.webp）
GUARD_TITLES = {"soldiers": "被追的孩子", "slaves": "車上的孩子", "river": "河裡的孩子", "spy": "被圍的孩子",
                "fever": "破廟裡的孩子", "thief": "偷錢袋的孩子"}  # 待 joy 潤


def take(ctx) -> dict | None:
    """此刻接管整個選單的是哪一格（同 Game._everyday_options：籌備、休季、開季準備、事件都不是；先後照 MENU_ORDER["take"]）。
    回 {"slot", "seal", "title"?, "art"?}；店面那幾格與沒人接管是 None。每一格照原本的條件問一次（只讀，同 /api/main 已經叫過的那一次）。"""
    s, c = ctx.state, ctx.content
    if s.world.ended or s.pending_event or ctx._preparing():  # 開季準備卡（main.prep）接管時頁面先看它
        return None
    own = features_core.menu_hooks("take")
    for slot in features_core.MENU_ORDER["take"]:
        if slot == "menu":
            for f in features_core.active(ctx):
                if f.menu(ctx) is not None:
                    return _menu_take(ctx, f.name)
            continue
        if slot in SHOP_SLOTS:
            if slot == "shops" and features_core.shop_menu(ctx) is not None:
                return None
            run = own.get(slot)
            if run is not None and run(ctx) is not None:
                return None
            continue
        run = own.get(slot)
        if run is None or run(ctx) is None:
            continue
        if slot == "story":
            return _story_take(ctx)
        return {"slot": slot, "seal": TAKE_SEALS.get(slot, EVENT_PLAIN), "place": _place_art(c, s.player.location)}
    return None


def _menu_take(ctx, name: str) -> dict:
    out = {"slot": "menu", "seal": MENU_SEALS.get(name, EVENT_PLAIN), "pack": name, "place": _place_art(ctx.content, ctx.state.player.location)}
    b = ctx.state.player.guard
    if name == "guard" and b is not None and b.stage in ("met", "saved") and b.opening in GUARD_TITLES:
        out["title"] = GUARD_TITLES[b.opening]
        out["art"] = f"/static/img/guard/story/meet-{b.opening}.webp"
    return out


def _story_take(ctx) -> dict:
    s, c = ctx.state, ctx.content
    progress = s.player.storylines.get(s.player.story_open or "")
    line = story_base.definition(c, progress) if progress is not None else None
    out = {"slot": "story", "seal": STORY_SEALS.get(line.kind, "奇事") if line is not None else "奇事", "place": _place_art(c, s.player.location)}
    if line is not None and line.title:
        out["title"] = line.title
    return out
