"""換戴的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import actions, rules


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/titles/wear")
    def api_wear(request: Request, body: dict = Body(...)):
        """{id}：換戴手上有的那一個；空字串是自動（戴最高檔的）。回 {message, main}。"""
        shell._account(request)  # 沒登入 401（先於開關，同客服包）
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)
        game = shell._game(request)
        tid = str(body.get("id", ""))[:32]
        msgs = shell.act(game, lambda g: actions.set_pin(g, tid))
        return {"message": shell.joined(msgs), "main": shell.look(game, shell.main_view)}

    return r
