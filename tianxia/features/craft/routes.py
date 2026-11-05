"""煉製頁的 API（功能包 tianxia/features/craft/；原本寫在 server.py，全部拆包第 44 批照有所感的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/forge_line 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
forge_args 留在殼（MENXIA_ACTIONS 的 forge 與 api_menxia_do 也叫它）；開爐與立意的鎖外三段式（B 段叫模型）照舊在殼的 server.py，這裡只接路由。"""
from fastapi import APIRouter, Body, Request


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/forge_line")
    def api_forge_line(request: Request, body: dict = Body(default={})):
        """煉製頁選了東西就更新說明（不算行動、不存檔）。爐裡只放了一樣時多給 picks：另一格放得進來的每一樣合不合得了，
        判斷是開爐時那一套（skillview.forge_picks）；其他時候是 None。"""
        game = shell._game(request)
        _art, picked = shell.forge_args(body)
        return shell.look(game, lambda g: {
            "line": shell.md(g.forge_line(picked)), "picks": g.forge_picks(picked),
            "preview": g.forge_preview(picked),  # 兩格都放好：預覽卡，其餘 None、網頁畫 line
        })

    return r
