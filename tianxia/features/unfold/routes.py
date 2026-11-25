"""慢慢長出來的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import rules


def router(shell) -> APIRouter:
    r = APIRouter()

    def gate(request: Request):
        shell._account(request)  # 沒登入 401（先於開關，同江湖錄包）
        if not shell.CONTENT.config.unfold.enabled:
            raise HTTPException(404)
        return shell._game(request)

    @r.post("/api/unfold/seen")
    def api_seen(request: Request, body: dict = Body(...)):
        """{keys}：點開過了，那幾塊剛長出來的紅點滅。回 {main}。"""
        game = gate(request)
        keys = [str(k)[:40] for k in (body.get("keys") or [])][:20]
        shell.act(game, lambda g: rules.seen(g.state.player.unfold, keys), paused_ok=True)
        return {"main": shell.look(game, shell.main_view)}

    return r
