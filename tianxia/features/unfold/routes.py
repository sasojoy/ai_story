"""慢慢長出來的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。開關關著回 404。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import cards, rules


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

    @r.post("/api/unfold/card")
    def api_card(request: Request, body: dict | None = Body(None)):
        """小事卡按了鈕（{go: true}：收起，有帶法的開始帶著做）或「改天」（收起；隔一陣子再碰到還會出一次，第二次就不出；
        見面禮兩顆都入帳）。回 {main}。"""
        game = gate(request)
        go = bool((body or {}).get("go"))

        def _do(g):
            book = g.state.player.unfold
            if book is None:
                return
            if go:
                cards.start(g, book)
            else:
                cards.close(g, book)
        shell.act(game, _do, paused_ok=True)
        return {"main": shell.look(game, shell.main_view)}

    @r.post("/api/unfold/lead")
    def api_lead(request: Request, body: dict = Body(...)):
        """帶著做一次：{kind, step} 網頁回報這一步做完了（寄出了、讀了結局、翻到圖鑑；end 是按了「好」）；{stop: true} 帶到一半不帶了。回 {main}。"""
        game = gate(request)
        kind, stp, halt = str(body.get("kind") or "")[:20], str(body.get("step") or "")[:20], bool(body.get("stop"))

        def _do(g):
            book = g.state.player.unfold
            if halt:
                cards.stop(book)
            else:
                cards.report(g, book, kind, stp)
        shell.act(game, _do, paused_ok=True)
        return {"main": shell.look(game, shell.main_view)}

    return r
