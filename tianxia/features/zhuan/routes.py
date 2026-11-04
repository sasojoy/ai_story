"""列傳的 API（功能包 tianxia/features/zhuan/；原本寫在 server.py，全部拆包第 29 批照有所感的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；路徑與別的路由不重疊，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
寫傳的鎖外三段式（A、B、C，B 段叫模型）、評曰的鎖外一條、傳的畫面 zhuan_view、公開頁的 extras 照舊在殼的
server.write_zhuan／verdict_text／zhuan_view／zhuan_extras（tests/server/test_server.py 掃鎖外叫模型的函式認這幾個名字；鎖外工作的掛鉤是總表第 69 批），
這裡只接路由。"""
import secrets

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from . import actions, zhuan_html


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/annals")
    def api_annals(request: Request):
        """見聞的「行狀」：這一季至今記下的事（玩家傳第一批；不叫模型）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: actions.annals_view(g))

    @r.get("/api/zhuan")
    def api_zhuan(request: Request, season: int):
        """那一季的傳（還沒寫成時 written 是 False、can_write 說寫不寫得了；正在寫時 writing 是 True）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: shell.zhuan_view(g, season, request))

    @r.post("/api/zhuan/write")
    def api_zhuan_write(request: Request, body: dict = Body(default={})):
        """請史官寫（或重寫一次）那一季的傳：在背景寫，馬上回目前的樣子（writing 是 True）。寫不了丟 GameError。"""
        game = shell._game(request)
        season, rewrite = shell._season_arg(body.get("season")), body.get("rewrite") is True
        if shell.look(game, lambda g: actions.request(g, season, rewrite)) is None:
            raise shell.GameError("這一篇現在不能再寫了。" if rewrite else "這一季還不能寫傳。")
        shell.write_zhuan(game, season, rewrite)
        return shell.look(game, lambda g: shell.zhuan_view(g, season, request))

    @r.post("/api/zhuan/share")
    def api_zhuan_share(request: Request, body: dict = Body(default={})):
        """公開或收回那一季的傳：公開時回分享網址（不用登入的唯讀頁 /zhuan/<代碼>）。"""
        game = shell._game(request)
        season, public = shell._season_arg(body.get("season")), body.get("public") is True
        code = shell.look(game, lambda g: actions.share(g, season, public, secrets.token_urlsafe(6)))
        if code is None:
            raise shell.GameError("傳還沒寫成，不能分享。")
        return shell.look(game, lambda g: shell.zhuan_view(g, season, request))

    @r.get("/zhuan/{code}")
    def zhuan_page(code: str, request: Request):
        """公開的傳（不用登入、唯讀）：只認公開中的分享代碼，其餘一律 404（不說是沒有、還是收回了）。
        帶 Open Graph，LINE、FB 貼上去有預覽（題簽圖是 web/zhuan-og.png，所有的傳共用一張）。"""
        store = shell.open_world()
        row = store.biography_by_code(code)
        if row is None:
            return HTMLResponse(zhuan_html.missing(), status_code=404)
        base = shell.public_base(request)
        return HTMLResponse(zhuan_html.page(row, shell.CONTENT.scenario.name, f"{base}/zhuan/{code}", f"{base}/static/zhuan-og.png",
                                            extras=shell.zhuan_extras(store, row)))

    return r
