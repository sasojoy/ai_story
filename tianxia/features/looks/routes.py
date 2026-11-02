"""擂台形象的 API（功能包 tianxia/features/looks/）：殼照 FEATURES 掛。形象關著（商城關著或 content/looks.json 沒有東西）全部 404。"""
import base64
import binascii
import re
import secrets
import time

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, Response

from tianxia.core.features import AdminTool
from tianxia.database import default_path

from . import actions, moves, orders, rules, scenes

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

    def move_upload(g, b):
        try:
            data = base64.b64decode(str(b.get("data", "")), validate=True)
        except (binascii.Error, ValueError):
            return ["（圖讀不出來。）"]
        return actions.admin_move_upload(g, shell._int(b.get("id"), 0), data, str(b.get("sheet", moves.SHEET))[:10] or moves.SHEET)

    return {
        "moves_upload": AdminTool(gate, move_upload),
        "moves_release": AdminTool(gate, lambda g, b: actions.admin_move_release(g, shell._int(b.get("id"), 0))),
        "moves_reject": AdminTool(gate, lambda g, b: actions.admin_move_reject(g, shell._int(b.get("id"), 0), str(b.get("note", ""))[:100])),
        "looks_upload": AdminTool(gate, upload),
        "looks_release": AdminTool(gate, lambda g, b: actions.admin_release(g, shell._int(b.get("id"), 0))),
        "looks_studio_retry": AdminTool(gate, lambda g, b: actions.admin_studio_retry(g, shell._int(b.get("id"), 0))),
        "looks_reject": AdminTool(gate, lambda g, b: actions.admin_reject(g, shell._int(b.get("id"), 0), str(b.get("note", ""))[:100])),
    }


def _draft(shell, game, text: str) -> dict | None:
    """請模型把玩家那一句拆成一張表（三段式的 B 段，**在行動鎖外**：慢的模型呼叫不進鎖）。
    叫不動、逾時、排隊被擋都回 None，導演落回關鍵字——下單不會因為模型而失敗。"""
    budget = float(getattr(game.content.config, "free_text_budget_seconds", 20) or 20)
    started = time.monotonic()

    def ask():
        return scenes.model_draft(shell.within_budget(game.client, budget - (time.monotonic() - started)), text)

    try:
        return shell.model_call(game, ask, fallback=None, left=budget)
    except Exception:  # noqa: BLE001  排隊被擋、模型那邊出事：照樣走關鍵字
        return None


def router(shell) -> APIRouter:
    r = APIRouter()
    gate = _gate(shell)

    @r.get("/api/looks")
    def api_looks(request: Request):
        """萬寶閣「形象」那一頁（actions.view）：穿著哪一套、每一套買了沒、自建形象的訂單。"""
        gate()
        return shell.act_look(shell._game(request), lambda g: actions.settle(g), lambda g: actions.view(g))[1]  # 順手結市集分成

    @r.post("/api/looks/wear")
    def api_looks_wear(request: Request, body: dict = Body(...)):
        """換上一套：{look}（空字串是預設的斗笠小子）；回 {message, looks}。"""
        gate()
        game = shell._game(request)
        look = str(body.get("look", ""))[:40]
        msgs = shell.act(game, lambda g: actions.wear(g, look))
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g))}

    @r.post("/api/looks/gear")
    def api_looks_gear(request: Request, body: dict = Body(...)):
        """戴上或拿下一件飾品：{id}；回 {message, looks}。"""
        gate()
        game = shell._game(request)
        gid = str(body.get("id", ""))[:40]
        msgs = shell.act(game, lambda g: actions.wear_gear(g, gid))
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

    @r.post("/api/looks/withdraw")
    def api_looks_withdraw(request: Request, body: dict = Body(...)):
        """撤回自己還沒上架的單：{id, kind}（kind "look" 自建形象、"move" 招式動畫），元寶全退；回 {message, looks, main}。"""
        gate()
        game = shell._game(request)
        pid, kind = shell._int(body.get("id"), 0), "move" if body.get("kind") == "move" else "look"
        msgs = shell.act(game, lambda g: actions.withdraw(g, pid, kind))
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g)),
                "main": shell.look(game, shell.main_view)}

    @r.post("/api/looks/move")
    def api_looks_move(request: Request, body: dict = Body(...)):
        """絕招下單：{prompt, ref, basic}（替現在練的那一門；打法照手上的兵器。basic＝通用 60、不畫圖、當場學成；不帶就是獨門 300、一定畫圖、送出等審核）；回 {message, looks, main}。"""
        gate()
        game = shell._game(request)
        raw = body.get("ref")
        ref = raw if isinstance(raw, str) and REF.fullmatch(raw) else secrets.token_urlsafe(12)
        prompt = str(body.get("prompt", ""))[:300]
        problem = shell.look(game, lambda g: actions.scene_problem(g, prompt))  # A：先驗，壞句子不必叫模型
        draft = None if problem else _draft(shell, game, prompt)  # B：鎖外問模型
        basic = bool(body.get("basic"))  # 通用絕招（60，不畫圖、當場學成）；不然是獨門（300，畫圖、送出等審核）
        msgs = shell.act(game, lambda g: actions.order_move(g, prompt, ref, draft, basic))  # C：扣元寶、存稿
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g)),
                "main": shell.look(game, shell.main_view)}

    @r.post("/api/looks/scene")
    def api_looks_scene_preview(request: Request, body: dict = Body(...)):
        """一句話自創的預覽：{text}；回 {scene}（導演稿）或 {problem}。不扣元寶、不存。"""
        gate()
        game = shell._game(request)
        text = str(body.get("text", ""))[:120]
        problem = shell.look(game, lambda g: actions.scene_problem(g, text))  # A：鎖內只讀，先驗那一句
        if problem:
            return {"problem": problem}
        draft = _draft(shell, game, text)  # B：鎖外問模型
        return shell.look(game, lambda g: actions.preview_scene(g, text, draft))  # C：鎖內組稿（純規則）

    @r.get("/api/looks/scene/{mid}")
    def api_looks_scene(request: Request, mid: str):
        """擂台上要演的那一招的導演稿（m<數字>，上架了的才有）：擂台上別人的招也要演，所以看得到的是登入的人。"""
        gate()
        game = shell._game(request)
        scene = shell.look(game, lambda g: actions.scene_of(g, mid))
        if scene is None:
            raise HTTPException(404)
        return {"scene": scene}

    @r.post("/api/looks/bind")
    def api_looks_bind(request: Request, body: dict = Body(...)):
        """把招式庫的一招綁到現在練的那一門上：{id}；回 {message, looks}。"""
        gate()
        game = shell._game(request)
        pid = shell._int(body.get("id"), 0)
        msgs = shell.act(game, lambda g: actions.bind_move(g, pid))
        return {"message": shell.joined(msgs), "looks": shell.look(game, lambda g: actions.view(g))}

    @r.post("/api/looks/market")
    def api_looks_market(request: Request, body: dict = Body(...)):
        """形象市集：{op: list（帶 look、price）| unlist（帶 look）| buy（帶 look、ref）}；回 {message, looks, main}。"""
        gate()
        game = shell._game(request)
        op, look = str(body.get("op", "")), str(body.get("look", ""))[:40]
        if op == "list":
            price = shell._int(body.get("price"), 0)
            msgs = shell.act(game, lambda g: actions.market_list(g, look, price))
        elif op == "unlist":
            msgs = shell.act(game, lambda g: actions.market_unlist(g, look))
        elif op == "buy":
            raw = body.get("ref")
            ref = raw if isinstance(raw, str) and REF.fullmatch(raw) else secrets.token_urlsafe(12)
            msgs = shell.act(game, lambda g: actions.market_buy(g, look, ref))
            shell._tell_tabs(game)
        else:
            raise HTTPException(400)
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
    def api_looks_img(request: Request, look: str, sheet: str):
        """自建形象與招式動畫的圖（資料庫旁邊的 looks/<id>/）：擂台上別人也看得到，所以不看登入；只認 u<數字> 配十張的檔名、m<數字> 配 fx。"""
        gate()
        if not ((orders.is_custom(look) and (sheet in orders.SHEETS or sheet == orders.HANDS))
                or (moves.is_move(look) and sheet in (moves.SHEET, *scenes.ART_SLOTS))):
            raise HTTPException(404)
        root = actions.images_beside(default_path())
        if sheet == orders.HANDS:  # 這一套自己的手位表（兵器掛在哪）：沒有就回 404，網頁照斗笠小子那張表
            path = orders.hands_file(root, look)
            path = path if path.is_file() else None
        else:
            path = orders.sheet_file(root, look, sheet)
        if path is None:
            raise HTTPException(404)
        # 每次都向伺服器確認，沒換就回 304（Starlette 1.7 的 FileResponse 不處理條件請求，這幾行自己做）。
        # 原本寫 public, max-age=86400：圖換了網址沒換，瀏覽器整天拿舊的那張——2026-11-02 把「魔教聖女」
        # 十張 refit 回標準身高之後，畫面上還是舊的大號身體，看起來像沒生效（Joy「沒辦法透過管理工具重複上架」；
        # 上架狀態不必動，圖是從磁碟送的）。上架之後圖還會被 refit、重畫、退回重來，所以不能釘死快取；
        # 照 server.NO_CACHE 那條家規（「開發時改了檔沒重開，會被瀏覽器釘死」）。
        stat = path.stat()
        tag = f'"{int(stat.st_mtime)}-{stat.st_size}"'  # 檔案換了（mtime 或大小變了）這個就變
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "no-cache"})
        media = "application/json" if path.suffix == ".json" else f"image/{path.suffix[1:]}"
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache", "ETag": tag})

    return r
