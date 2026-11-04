"""有所感的 API（功能包 tianxia/features/sense/；原本寫在 server.py，全部拆包第 24 批照商城的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/sense* 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
畫完那一筆的鎖外三段式（A、B、C，B 段叫模型）照舊在殼的 server.sense_draw（鎖外工作的掛鉤是總表第 69 批），這裡只接路由。"""
from fastapi import APIRouter, Body, Request

from . import glyph, insight_llm


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/sense")
    def api_sense(request: Request, body: dict = Body(default={})):
        """有所感畫完那一筆：points 是 [[x, y, 毫秒], …]，png 是畫布的小圖（base64，不含 data: 開頭）。"""
        game = shell._game(request)
        msgs = shell.sense_draw(game, body.get("points"), body.get("png") or "")
        shell._tell_tabs(game)
        return {"main": shell.look(game, shell.main_view), "message": shell.joined(msgs)}

    @r.post("/api/sense_read")
    def api_sense_read(request: Request, body: dict = Body(default={})):
        """畫布底下那一行（不算行動、不拿鎖、不碰狀態）：這一筆讀不讀得出來（跟送出時讀的是同一套 glyph.read）。讀得出來只回 ok，
        不寫規則讀到什麼——玩家面前不寫筆畫的幾何（企劃者 2026-10-06），那一筆的感覺留到意境的說明；讀不出來回一句話（只點了一下）。"""
        shell._game(request)
        try:
            glyph.read(body.get("points"))
        except glyph.GlyphError as e:
            return {"ok": False, "problem": str(e)}
        return {"ok": True}

    @r.post("/api/sense_warm")
    def api_sense_warm(request: Request):
        """畫布一出現就送的暖機（悟意境設計 0.2a）：只叫 Ollama 把模型載起來、不取名、不等它載完；不拿鎖、不碰狀態。"""
        game = shell._game(request)
        return {"ok": insight_llm.warm(game.client)}

    return r
