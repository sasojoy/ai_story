"""擂台形象的 API（功能包 tianxia/features/looks/）：殼照 FEATURES 掛。形象關著（商城關著或 content/looks.json 沒有東西）全部 404。"""
from fastapi import APIRouter, Body, HTTPException, Request

from . import actions, rules


def router(shell) -> APIRouter:
    r = APIRouter()

    def gate() -> None:
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)

    @r.get("/api/looks")
    def api_looks(request: Request):
        """萬寶閣「形象」那一頁（actions.view）：穿著哪一套、每一套買了沒。"""
        gate()
        return shell.act_look(shell._game(request), lambda g: None, lambda g: actions.view(g))[1]

    @r.post("/api/looks/wear")
    def api_looks_wear(request: Request, body: dict = Body(...)):
        """換上一套：{look}（空字串是預設的斗笠小子）；回 {message, looks}。"""
        gate()
        game = shell._game(request)
        look = str(body.get("look", ""))[:40]
        msgs = shell.act(game, lambda g: actions.wear(g, look))
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g))}

    return r
