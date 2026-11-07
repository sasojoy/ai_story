"""輿圖（功能包；開發規範手冊 3.2）：天下圖、區圖、小地圖、地點詳情、疊層。README.md 寫這一包做什麼、導覽與設計稿。

全部拆包第 49 批搬進來（計畫 docs/superpowers/plans/2026-11-06-輿圖包-第1批.md）。

- mapview.py、mapart.py、mapdata.py、worldgeo.py：原本的 tianxia/mapview.py 等四個（舊名留成指到同一個模組的別名）：畫法、設色山水、底圖資料與疊層、天下圖的純幾何
- actions.py：原本 Game 上輿圖的 11 個方法（Game 留一行委派）；views.py：/api/map 的資料與底圖快取；routes.py：/api/map 三條路由（殼照 FEATURES 掛）

沒有選項前綴、沒有狀態鍵（輿圖的畫面全從存檔現算，自己沒有寫到一半的東西）；假人不看地圖，只有 bot_policy 叫 Game.travel_options。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class MapFeature(Feature):
    name = "map"
    prefix = None  # 輿圖是只讀的畫面，選單上沒有 map: 的選項（view_map 是新手引導包的、tab:map 是揭曉鍵）
    web = ("map.js", "map.css")  # 輿圖的畫面；app.js 的 loadMap 是殼呼叫的入口，留在 app.js
    # content/map.json 是核心 models.Content.map 的，不歸這一包；沒有 PlayerState 欄位
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = MapFeature()
