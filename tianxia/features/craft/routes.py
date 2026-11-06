"""煉製頁的 API（功能包 tianxia/features/craft/；原本寫在 server.py，全部拆包第 44 批照有所感的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/forge_line 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
forge_args 留在殼（MENXIA_ACTIONS 的 forge 與 api_menxia_do 也叫它）；開爐與立意的鎖外三段式（B 段叫模型）照舊在殼的 server.py，這裡只接路由。
自創的動作表（原本寫在 server.py 的 MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（menxia_actions 掛鉤）。"""
from fastapi import APIRouter, Body, Request

from tianxia.core.features import Outlock

from . import actions, create


def menxia_actions(shell) -> dict:
    return {
        # 自創武學（tianxia/create.py）：執器、擺式、回頭、立名、擱下；立意走 /api/do/create_intent（三段式，模型讀這一句意）
        "create_begin": lambda g, b: actions.begin(g, str(b.get("kind") or ""), str(b.get("form") or "")),
        "create_pose": lambda g, b: actions.pose(g, b.get("pose") if isinstance(b.get("pose"), dict) else {}),
        "create_back": lambda g, b: actions.back(g, str(b.get("to") or "")),
        "create_name": lambda g, b: actions.name(g, str(b.get("name") or ""), str(b.get("move") or "")[:create.MOVE_MAX * 2]),
        "create_cancel": lambda g, b: actions.cancel(g),
        "create_reroll": lambda g, b: actions.reroll(g),  # 重悟帖：成了形直接重骰（萬寶閣，Joy 2026-10-21）
    }


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


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "create_intent": lambda g, b: create_intent(shell, g, b),  # 自創武學的形意：意分在行動鎖外評（見 create_intent）
        "create_reread": lambda g, b: shell.create_reread(g, b),  # 重悟帖：重讀這句意，意分在行動鎖外評（見 create_reread）
    })


def create_intent(shell, game, body: dict) -> list[str]:
    """自創武學的立意（tianxia/create.py），三段同 duel_text：A Game.create_request（只讀）→ B 鎖外 create.read 讀這一句意
    （分數、最多兩路屬性、正邪；預算同隨口應對）→ C Game.create_intent(reading=) 整個重驗再成形。叫不動照關鍵字表讀。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = shell._open_request(game, lambda: game.create_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read(shell.within_budget(game.client, total - (shell._monotonic() - started)), request, game.content)

    value = shell.model_call(
        game, reading, fallback=create.fallback_read(game.content, request.text),
        left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT,
    )
    return shell.act(game, lambda g: g.create_intent(request.text, reading=value))


def create_reread(shell, game, body: dict) -> list[str]:
    """重悟帖的第二個用法：重讀這句意（可以改寫），三段同 create_intent：A Game.create_reread_request → B 鎖外 create.read_or_none
    → C Game.create_reread(reading=)。叫不動（None）就什麼都不改、不扣帖（不照關鍵字表讀）。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = shell._open_request(game, lambda: game.create_reread_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read_or_none(shell.within_budget(game.client, total - (shell._monotonic() - started)), request)

    value = shell.model_call(game, reading, fallback=None, left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.create_reread(request.text, value))
