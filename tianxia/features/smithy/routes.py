"""鐵匠鋪的 API（功能包 tianxia/features/smithy/；原本寫在 server.py，全部拆包第 41 批照煉製頁的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/smith_line 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from fastapi import APIRouter, Body, Request


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/smith_line")
    def api_smith_line(request: Request, body: dict = Body(default={})):
        """店面打造那一頁：爐裡放了什麼就問這一爐會怎樣（不算行動、不存檔；店面獨立介面設計 6.3）。參數是客戶端寫的，一律轉成字串。"""
        game = shell._game(request)
        kind, main, aux = (str(body.get(key) or "") for key in ("kind", "main", "aux"))
        return shell.look(game, lambda g: g.smith_line(kind, main or None, aux or None))

    return r
