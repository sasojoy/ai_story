"""江湖錄的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import rules, view


def router(shell) -> APIRouter:
    r = APIRouter()

    def gate(request: Request):
        shell._account(request)  # 沒登入 401（先於開關，同稱號包）
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)
        return shell._game(request)

    @r.get("/api/codex")
    def api_codex(request: Request):
        """整本：奇遇（正在走、已了、往季、還沒遇上）與圖鑑（人物、器物、意境、結局）。"""
        game = gate(request)
        return shell.look(game, view.page)

    @r.get("/api/codex/scene")
    def api_scene(request: Request, i: int = -1, line: str = "", end: str = ""):
        """重讀一幕（i 是第幾幕）或一個結局（line、end）。看不到的 404。"""
        game = gate(request)
        got = shell.look(game, lambda g: view.ending_text(g, line[:40], end[:40]) if end else view.scene(g, i))
        if got is None:
            raise HTTPException(404)
        return got

    @r.post("/api/codex/seen")
    def api_seen(request: Request, body: dict = Body(...)):
        """{keys}：看過了，紅點滅（一整類寫「p:*」）。回 {main}。"""
        game = gate(request)
        keys = [str(k)[:80] for k in (body.get("keys") or [])][:200]
        shell.act(game, lambda g: view.seen(g, keys), paused_ok=True)
        return {"main": shell.look(game, shell.main_view)}

    return r
