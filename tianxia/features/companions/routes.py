"""人物情誼的 API（功能包 tianxia/features/companions/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
名冊、書信小卡、勸降的動作照舊走 server 的 /api/menxia/{op}、/api/do/{op}（動作表總表第 68 批才照包分），這裡只有這一包整條自己的路由（第 3 階之前先做的那一件）。"""
from fastapi import APIRouter, Request

from . import actions


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/figure")
    def api_figure(request: Request, id: str = ""):
        """人物頁（減法季批 6，主機側計畫 1.3 的 figure.stances、figure.errands）：這位人物（對話人物 id）的心意條、你今天記的那一筆、
        他託你的事（actions.figure_view）。關著、他什麼都沒有是 None。只讀。"""
        game = shell._game(request)
        return {"figure": shell.look(game, lambda g: actions.figure_view(g, str(id)[:40]))}

    return r
