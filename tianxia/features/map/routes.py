"""輿圖的 API（功能包 tianxia/features/map/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛。

- GET /api/map?layer=&place=：舊的輿圖（四個圖層的整張 SVG 與詳情欄），輿圖升級之後網頁不再呼叫，留一版給還開著舊網頁的分頁（設計第九節）
- GET /api/map/base：輿圖升級的底圖（只有紙、大區、山河、路）與地點、路、大區的清單；網頁一次載入只抓一次，疊層的 key 變了才重抓
- GET /api/map/state：輿圖升級的疊層：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞，戰線、今天去哪裡出陣、每一週的地盤（mapdata.state）

這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的 map_view、map_base_view 也看得到）。
"""
from fastapi import APIRouter, Request


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/map")
    def api_map(request: Request, layer: str = shell.DEFAULT_LAYER, place: str | None = None):
        """舊的輿圖（四個圖層的整張 SVG 與詳情欄）：輿圖升級之後網頁不再呼叫，留一版給還開著舊網頁的分頁（設計第九節）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: shell.map_view(g, layer, place))

    @r.get("/api/map/base")
    def api_map_base(request: Request):
        """輿圖升級的底圖（只有紙、大區、山河、路）與地點、路、大區的清單；網頁一次載入只抓一次，疊層的 key 變了才重抓。"""
        game = shell._game(request)
        return shell.look(game, shell.map_base_view)

    @r.get("/api/map/state")
    def api_map_state(request: Request):
        """輿圖升級的疊層：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞，戰線、今天去哪裡出陣、每一週的地盤（mapdata.state）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: g.map_state())

    return r
