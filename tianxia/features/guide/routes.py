"""新手引導包的 API（功能包 tianxia/features/guide/；原本寫在 server.py，全部拆包第 59 批搬進來）：殼（server 模組，參數 shell）照 FEATURES 掛
（server 的 features_core.routers 那一行；路徑沒有帶參數的路由吃得到，先後不影響）。這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；
殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。/api/prologue 這一批不動。"""
from fastapi import APIRouter, Request


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/howto")
    def api_howto(request: Request):
        """設定抽屜的「玩法說明」（explain-1）：五個行動、體力、情誼、心得、意境、背包各一兩句，數字照設定（Markdown 轉成 HTML）。
        不看個人狀態，網頁同一次載入只問一次。"""
        game = shell._game(request)
        return shell.look(game, lambda g: {"text": shell.md(g.howto_text())})

    return r
