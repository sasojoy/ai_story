"""輿圖的 API 資料（全部拆包第 49 批：原本寫在 server.py 的 MAP_BASE、MAP_BASE_KEEP、map_base_view、map_view）。

不 import 網頁框架（引擎與假人程式不碰它；只有 routes.py 用 fastapi）。server.py 留同一個物件的別名：`server.MAP_BASE is views.MAP_BASE`、
`server.map_base_view is views.map_base_view`；`server.map_view` 是一層薄薄的包裝（把殼的 md 帶進來，/api/travel 走不成時也叫它）。
呼叫端拿著行動鎖（look）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from . import mapdata

if TYPE_CHECKING:
    from tianxia.engine import Game

DEFAULT_LAYER = "situation"  # 同 server.DEFAULT_LAYER（/api/travel 與測試讀 server 的那一份；package 的測試守兩邊一樣）

MAP_BASE: dict[str, dict] = {}  # 輿圖升級的底圖：照開放的地點（mapdata.base_key）快取；一季差不多只有一兩把鍵
MAP_BASE_KEEP = 8  # 超過就整個清掉重來（劇情開放的地點只有幾處，不會真的到）


def map_base_view(game: Game) -> dict:
    """輿圖升級的底圖與清單（/api/map/base）：同一把鍵（開放的地點一樣）回同一份，不重畫。呼叫端拿著行動鎖（look）。
    減法季探索一顆開著的季，名字旁的兩個字是看的人的（Game.map_mostly，2f，FB-886；網頁讀這裡 places[].mostly）：快取的是跟人無關的那一份
    （山河的圖、路、大區、天下圖），每個人再換上自己的名字旁與鍵（mapdata.with_mostly，新的 dict、重的部分同一份物件）；鍵跟疊層
    （Game.map_state）的 key 是同一串，字變了網頁就會重抓。"""
    key = mapdata.base_key(game.state, game.content)
    if key not in MAP_BASE:
        if len(MAP_BASE) >= MAP_BASE_KEEP:
            MAP_BASE.clear()
        MAP_BASE[key] = game.map_base(viewer=False)
    mostly = game.map_mostly()
    if mostly is None:
        return MAP_BASE[key]
    return mapdata.with_mostly(MAP_BASE[key], mapdata.base_key(game.state, game.content, mostly), mostly)


def map_view(game: Game, layer: str, selected: str | None, md: Callable[[str | None], str]) -> dict:
    """舊的輿圖（四個圖層的整張 SVG 與詳情欄）；md 是殼的 markdown 轉換（server.md）。"""
    places = game.map_places()
    if selected not in {loc_id for _, loc_id in places}:
        selected = game.state.player.location
    if layer not in game.MAP_LAYERS:
        layer = DEFAULT_LAYER
    return {
        "header": md(game.map_header()),
        "layers": [{"id": key, "name": name} for key, name in game.MAP_LAYERS.items()],
        "layer": layer,
        "svg": game.world_map_svg(layer, selected),
        # 圖例不畫進 svg（圖裡的會跟著平移、縮放，放大時就看不見）：跟 svg 並排給網頁，疊在地圖框角落（web/app.js 的 legendHtml）
        "legend": game.map_legend(layer),
        "places": [{"label": label, "id": loc_id} for label, loc_id in places],
        "selected": selected,
        "here": game.state.player.location,
        "detail": md(game.place_detail(selected)),
        # 步行、疾行兩個按鈕（照 atlas.MODES 的順序）；就在這裡時是 None。被待處理的事件擋著時只有一顆灰的、
        # label 寫是哪一則，to_jianghu 為真：頁面在旁邊多給一顆「回江湖」（FB-063）
        "travel": [
            {"mode": o.mode, "label": o.label, "enabled": o.enabled, "to_jianghu": o.to_jianghu}
            for o in game.travel_options(selected) or []
        ] or None,
    }
