"""擂台形象的 API（功能包 tianxia/features/looks/）：殼照 FEATURES 掛。形象關著（商城關著或 content/looks.json 沒有東西）全部 404。"""
import base64
import binascii
import re
import secrets

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from tianxia.core.features import AdminTool
from tianxia.database import default_path

from . import actions, orders, rules

REF = re.compile(r"[A-Za-z0-9_-]{8,64}")


def _gate(shell):
    def gate() -> None:
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)
    return gate


def admin_tools(shell) -> dict[str, AdminTool]:
    """自建形象的管理者工具（/api/do/looks_*）：上傳一張（{id, sheet, data：base64}）、上架（{id}）、退回（{id, note}）。"""
    gate = _gate(shell)

    def upload(g, b):
        try:
            data = base64.b64decode(str(b.get("data", "")), validate=True)
        except (binascii.Error, ValueError):
            return ["（圖讀不出來。）"]
        return actions.admin_upload(g, shell._int(b.get("id"), 0), str(b.get("sheet", ""))[:40], data)

    return {
        "looks_upload": AdminTool(gate, upload),
        "looks_release": AdminTool(gate, lambda g, b: actions.admin_release(g, shell._int(b.get("id"), 0))),
        "looks_reject": AdminTool(gate, lambda g, b: actions.admin_reject(g, shell._int(b.get("id"), 0), str(b.get("note", ""))[:100])),
    }


def router(shell) -> APIRouter:
    r = APIRouter()
    gate = _gate(shell)

    @r.get("/api/looks")
    def api_looks(request: Request):
        """萬寶閣「形象」那一頁（actions.view）：穿著哪一套、每一套買了沒、自建形象的訂單。"""
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

    @r.post("/api/looks/order")
    def api_looks_order(request: Request, body: dict = Body(...)):
        """自建形象下單：{name, prompt, ref}（ref 是網頁按下確認那一刻產的編號，重送不會扣兩次）；回 {message, looks, main}。"""
        gate()
        game = shell._game(request)
        raw = body.get("ref")
        ref = raw if isinstance(raw, str) and REF.fullmatch(raw) else secrets.token_urlsafe(12)
        name, prompt = str(body.get("name", ""))[:20], str(body.get("prompt", ""))[:300]
        msgs = shell.act(game, lambda g: actions.order(g, name, prompt, ref))
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g)),
                "main": shell.look(game, shell.main_view)}

    @r.get("/api/admin/looks")
    def api_admin_looks(request: Request):
        """管理者看自建形象的訂單（actions.admin_view）。"""
        gate()
        game = shell._game(request)
        if not game.is_admin():
            raise HTTPException(403)
        return shell.act_look(game, lambda g: None, lambda g: actions.admin_view(g))[1]

    @r.get("/api/looks/img/{look}/{sheet}")
    def api_looks_img(look: str, sheet: str):
        """自建形象的圖（資料庫旁邊的 looks/<id>/）：擂台上別人也看得到，所以不看登入；只認 u<數字> 與九張的檔名。"""
        gate()
        if not orders.is_custom(look) or sheet not in orders.SHEETS:
            raise HTTPException(404)
        path = orders.sheet_file(actions.images_beside(default_path()), look, sheet)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type=f"image/{path.suffix[1:]}", headers={"Cache-Control": "public, max-age=86400"})

    return r
