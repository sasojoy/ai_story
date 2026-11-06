"""有所感的 API（功能包 tianxia/features/sense/；原本寫在 server.py，全部拆包第 24 批照商城的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/sense* 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
畫完那一筆的鎖外三段式（A、B、C，B 段叫模型）照舊在殼的 server.sense_draw（鎖外工作的掛鉤是總表第 69 批），這裡只接路由。"""
from fastapi import APIRouter, Body, Request

from . import epiphany, glyph, insight_llm


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/sense")
    def api_sense(request: Request, body: dict = Body(default={})):
        """有所感畫完那一筆：points 是 [[x, y, 毫秒], …]，png 是畫布的小圖（base64，不含 data: 開頭）。"""
        game = shell._game(request)
        msgs = sense_draw(shell, game, body.get("points"), body.get("png") or "")
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


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def epiphany_think(shell, game) -> list[str] | None:
    """特殊頓悟的「靜心思名」，跟開爐取名一樣分三段：
      A（鎖內、很快）同步時間，Game.epiphany_request 開單（只讀）；不在等著取名、已經想過了是 None，照一般的按鈕走（引擎回那一句）；
      B（鎖外、很慢）epiphany.propose_names 請模型一次取三個（model_call 排隊），預算是 Config.naming_budget_seconds 扣掉 A 段；
        取不到是空的；
      C（鎖內、很快）Game.epiphany_names 重驗還是同一個神品、名字再過一次過濾，不夠三個用字表補。"""
    started, request = shell._open_request(game, game.epiphany_request)
    if request is None:
        return shell.act(game, lambda g: g.choose(shell.EPIPHANY_THINK))
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (shell._monotonic() - started))
        return epiphany.propose_names(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    names = shell.model_call(game, name_it, fallback=[], left=total - (shell._monotonic() - started), busy=shell.BUSY_EPIPHANY)
    return shell.act(game, lambda g: g.epiphany_names(request, names))


SENSE_PNG_MAX = 300_000  # 畫布存的小 PNG（base64 字數）最多收這麼多；再大就不給模型看圖，只給文字特徵（畫布 256×256，實際約一兩萬字）


def sense_draw(shell, game, points, png: str = "") -> list[str] | None:
    """有所感畫完那一筆（悟意境設計 0.2、0.2a），跟開爐取名一樣分三段：
      A（鎖內、很快）同步時間，Game.sense_request 讀那一筆、開單（只讀）；讀不出來（只點了一下、格式不對）回那一句話；
      B（鎖外、很慢）要悟一個自己的新意境才叫模型：看圖取名，取不到再只給文字特徵（insight_llm.name，model_call 排隊）；
        預算是 Config.sense_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間；落回基本意境的不叫；
      C（鎖內、很快）Game.sense_draw 重驗還是同一次感悟、同一筆讀出同一個屬性才套用，名字再過一次過濾，取不到走退路字表。
    PNG 只轉交給模型，不存（存的是規則取樣過的點位，畫縮圖用）。"""
    image = png if isinstance(png, str) and len(png) <= SENSE_PNG_MAX else ""
    started, request = shell._open_request(game, lambda: game.sense_request(points, image))
    if isinstance(request, str):
        raise shell.GameError(request)
    proposed = shell.NO_NAME
    if request.needs_name:
        total = game.content.config.sense_budget_seconds

        def name_it():
            budget = max(0.0, total - (shell._monotonic() - started))
            got = insight_llm.name(
                game.client, game.content, request.facts, image=request.png, budget=budget,
                person=game.world.is_character_name,
            )
            return got[0], got[1]

        proposed = shell.model_call(game, name_it, fallback=shell.NO_NAME, left=total - (shell._monotonic() - started), busy=shell.BUSY_SENSE)
    return shell.act(game, lambda g: g.sense_draw(request, proposed))
