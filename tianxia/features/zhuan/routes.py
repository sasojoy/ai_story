"""列傳的 API（功能包 tianxia/features/zhuan/；原本寫在 server.py，全部拆包第 29 批照有所感的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；路徑與別的路由不重疊，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
寫傳的鎖外三段式（A、B、C，B 段叫模型）、評曰的鎖外一條、傳的畫面 zhuan_view、公開頁的 extras 照舊在殼的
server.write_zhuan／verdict_text／zhuan_view／zhuan_extras（tests/server/test_server.py 掃鎖外叫模型的函式認這幾個名字；鎖外工作的掛鉤是總表第 69 批），
這裡只接路由。"""
import secrets

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from . import actions, biography, zhuan_end, zhuan_html


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


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def write_zhuan(shell, game, season: int, rewrite: bool) -> bool:
    """開一個背景執行緒寫那一季的傳：A 鎖內開單 → B 鎖外請模型寫（model_call，佇列開著要排隊；預算 Config.biography.budget_seconds）
    → C 鎖內重驗再存（Game.write_biography；模型寫不出來就照規則拼）。同一篇已經在寫就不再開；開了回 True。"""
    key = shell._zhuan_key(game, season)
    with shell.ZHUAN_LOCK:
        if key in shell.ZHUAN_JOBS:
            return False
        shell.ZHUAN_JOBS[key] = shell.time.monotonic()

    def zhuan_job() -> None:
        try:
            with shell._locked(game):
                request = game.biography_request(season, rewrite)
            if request is None:
                return
            budget = game.content.config.biography.budget_seconds
            started = shell.time.monotonic()

            def ask() -> str | None:
                return biography.write(game.client, request, budget - (shell.time.monotonic() - started))

            text = shell.model_call(game, ask, fallback=None, left=budget)
            if not request.verdicts:  # 關著的季、沒有人替你寫評曰：跟以前一模一樣
                with shell._locked(game):
                    game.write_biography(request, text, shell.time.time())
                return
            verdicts = {job.fid: verdict_text(shell, game, job) for job in request.verdicts}  # 寫完正文再逐條寫評曰（減法季批 7b-2）
            with shell._locked(game):
                game.write_biography(request, text, shell.time.time(), verdicts=verdicts)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，網頁問的時候照「還沒寫」
            shell.traceback.print_exc()
        finally:
            with shell.ZHUAN_LOCK:
                shell.ZHUAN_JOBS.pop(key, None)

    shell.threading.Thread(target=zhuan_job, name=f"zhuan-{season}", daemon=True).start()
    return True


VERDICT_OWNER = "#評曰"  # 人物評曰在佇列裡的名號尾巴：跟這個人自己的請求分開排，當假人排在真人後面


def verdict_text(shell, game, job) -> str:
    """一條人物評曰（減法季批 7b-2；zhuan_job 在鎖外叫）：請模型照他的口氣寫一句（zhuan_end.write_verdict），預算
    Config.jianfa.verdict_budget_seconds（含排隊）；佇列開著時當假人排、排在真人後面（同書信 letter_once）。寫不出來是空字串（照固定句）。"""
    jf = game.content.config.jianfa
    started = shell._monotonic()

    def ask() -> str:
        return zhuan_end.write_verdict(shell.within_budget(game.client, jf.verdict_budget_seconds - (shell._monotonic() - started)), job, jf.verdict_chars)

    if shell.QUEUE is None:
        return ask()
    try:
        return shell.QUEUE.run(game.state.player.name.casefold() + VERDICT_OWNER, ask, fallback="", bot=True, wait=jf.verdict_budget_seconds)
    except (shell.Busy, shell.QueueTimeout):
        return ""
