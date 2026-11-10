"""開局前導的路由（殼照 FEATURES 掛；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。

- GET /api/intro：畫本（七幕的圖、字、人物）。沒登入 401（先認登入，殼不多一條不用登入的路由），登入了關著 404。
- POST /api/intro/seen：這個角色看過了（跳過、看完、按進城都算），之後不再自動播；回 {message, main}。同上。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import rules


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/intro")
    def api_intro(request: Request):
        shell._account(request)  # 先認登入（沒登入 401），殼的「不用登入的路由」名單不多一筆
        if not shell.CONTENT.config.intro.enabled:
            raise HTTPException(404)
        return rules.book(shell.CONTENT)

    @r.post("/api/intro/seen")
    def api_intro_seen(request: Request):
        game = shell._game(request)  # 同上：先認登入
        if not shell.CONTENT.config.intro.enabled:
            raise HTTPException(404)
        msgs = shell.act(game, rules.mark_seen, paused_ok=True)
        return {"message": shell.joined(msgs), "main": shell.look(game, shell.main_view)}

    return r
