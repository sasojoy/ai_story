"""設定頁的成人內容開關（殼掛的路由；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import actions, rules


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/heroines/adult")
    def api_adult(request: Request, body: dict = Body(...)):
        """{value}：開或關成人內容。打開之前網頁先跳確認卡（我已年滿十八歲）；回 {message, main}。沒有女子的內容 404。"""
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)
        game = shell._game(request)
        msgs = shell.act(game, lambda g: actions.set_adult(g, bool(body.get("value"))))
        return {"message": shell.joined(msgs), "main": shell.look(game, shell.main_view)}

    return r
