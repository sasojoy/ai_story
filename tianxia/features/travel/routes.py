"""移動的 API（功能包 tianxia/features/travel/；原本寫在 server.py，全部拆包第 47 批）：殼（server 模組，參數 shell）照 FEATURES 掛
（server 的 features_core.routers 那一行；/api/travel 跟別的路徑不重疊，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from fastapi import APIRouter, Body, Request


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/travel")
    def api_travel(request: Request, body: dict = Body(...)):
        """「安排前往」（步行、疾行）：出發了就回 {main, arrived: true}，畫面回江湖、場景寫路上或抵達的地點；
        按鈕是舊的而走不成時（例如打開輿圖之後才冒出事件）回 {arrived: false, map, reason}，留在輿圖、寫出原因。"""
        game = shell._game(request)
        target = str(body.get("place", ""))
        mode = str(body.get("mode") or "walk")
        refused: list[str] = []

        def go(g):
            reason = g.travel_refusal(target, mode)
            if reason is not None:
                refused.append(reason)
            return g.travel(target, mode)

        shell.act(game, go)
        if not refused:  # 走不成的什麼都沒變（同步而已），其他分頁不必刷新
            shell._play_did(game, "travel")
            shell._tell_tabs(game)
        out = {"main": shell.look(game, shell.main_view), "arrived": not refused}
        if refused:
            out["reason"] = refused[0]
            out["map"] = shell.look(game, lambda g: shell.map_view(g, str(body.get("layer") or shell.DEFAULT_LAYER), target))
        return out

    return r
