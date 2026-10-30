"""商城的 API（功能包 tianxia/features/mall/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES
在原本那一段的位置掛（路由的先後不變），/api/do/{op} 的管理者工具也照清單接（admin_tools）。

開關 Config.mall.enabled 關著時這裡的 API 全部 404（4.10）。購買在行動鎖裡（act）：扣元寶、寫購買紀錄、發貨同一筆交易。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
商城的動作直接叫這一包的 actions（Game.mall_* 那幾個一行的委派是給還沒改的呼叫端過渡用的，手冊 3.10；包自己不繞回 Game）。
"""
import re
import secrets
import unicodedata

from fastapi import APIRouter, Body, HTTPException, Request

from tianxia.core.features import AdminTool

from . import actions
from . import rules as mall

MALL_REF = re.compile(r"[A-Za-z0-9_-]{8,64}")


def _mall_ref(raw) -> str:
    """這一筆的編號：網頁送的是 8～64 個英數字、底線、減號就照用（網頁按下確認那一刻產，重送同一個不會算兩次），
    其餘（沒送、送了怪東西）由伺服器產一個。"""
    text = raw if isinstance(raw, str) else ""
    return text if MALL_REF.fullmatch(text) else secrets.token_urlsafe(12)


def _gate(shell):
    def gate() -> None:
        if not mall.on(shell.CONTENT):
            raise HTTPException(404)
    return gate


def admin_tools(shell) -> dict[str, AdminTool]:
    """管理者的商城工具（4.7）：補發、扣回、退一筆；原因 note 必填、每一筆寫進帳（誰、何時、為什麼）。查帳是 /api/admin/mall。
    商城關著：沒有這個東西（404，先於登入的檢查，跟 /api/mall 一樣）；帳跟季無關：暫停中也做得了。"""
    gate = _gate(shell)
    return {
        "mall_reissue": AdminTool(gate, lambda g, b: actions.admin_reissue(
            g, str(b.get("name", ""))[:40], shell._int(b.get("amount"), 0), str(b.get("note", ""))[:100], _mall_ref(b.get("ref")))),
        "mall_revoke": AdminTool(gate, lambda g, b: actions.admin_revoke(
            g, str(b.get("name", ""))[:40], shell._int(b.get("amount"), 0), str(b.get("note", ""))[:100], _mall_ref(b.get("ref")))),
        "mall_refund": AdminTool(gate, lambda g, b: actions.admin_refund(
            g, str(b.get("name", ""))[:40], shell._int(b.get("id"), 0), str(b.get("note", ""))[:100])),
    }


def router(shell) -> APIRouter:
    r = APIRouter()
    _mall_on = _gate(shell)

    @r.get("/api/mall")
    def api_mall(request: Request):
        """商城那一頁（actions.view）：同步之後的餘額、月卡、上架的商品。"""
        _mall_on()
        return shell.act_look(shell._game(request), lambda g: None, lambda g: actions.view(g))[1]

    @r.get("/api/mall/records")
    def api_mall_records(request: Request):
        """自己的購買紀錄與帳（actions.records）。"""
        _mall_on()
        return shell.act_look(shell._game(request), lambda g: None, lambda g: actions.records(g))[1]

    @r.post("/api/mall/buy")
    def api_mall_buy(request: Request, body: dict = Body(...)):
        """買東西（actions.buy）：{item, ref, qty}（qty 一次買幾件，不給是 1；Joy 2026-10-22）；回 {message, bought, already, mall, main}。bought 是買成的商品 id（不成是 None：網頁照它換
        掌櫃那一句）、already 是這個編號早就買好的那一件（逾時重送，網頁照成了的樣子講，FB-491；其餘是 None）、main 是江湖畫面
        （狀態列的錠子鈕與丹鈕當場換，商城第二批）。賽季時鐘暫停中照其他動作擋。"""
        _mall_on()
        game = shell._game(request)
        item, ref = str(body.get("item", ""))[:40], _mall_ref(body.get("ref"))
        got: dict = {}

        def buy(g):
            out = actions.buy(g, item, ref, max(1, min(mall.MAX_QTY, shell._int(body.get("qty"), 1))))
            got["bought"], got["already"] = g.mall_bought, g.mall_already  # 在鎖裡讀：出了鎖別的請求可能又動了這一份 Game
            return out

        msgs = shell.act(game, buy)
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "bought": got.get("bought"), "already": got.get("already"),
                "mall": shell.look(game, lambda g: actions.view(g)), "main": shell.look(game, shell.main_view)}

    @r.post("/api/mall/claim")
    def api_mall_claim(request: Request):
        """領月卡今天的份（actions.claim；定案甲・每日領）：回 {message, mall, main}（錠子鈕、丹鈕與江湖頁那張小卡當場換）。"""
        _mall_on()
        game = shell._game(request)
        msgs = shell.act(game, lambda g: actions.claim(g))
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "mall": shell.look(game, lambda g: actions.view(g)), "main": shell.look(game, shell.main_view)}

    @r.post("/api/mall/rename")
    def api_mall_rename(request: Request, body: dict = Body(...)):
        """易名帖（actions.rename_self；Joy 2026-10-21 當場生效）：{name}；回 {message, renamed, main}。名號的寫法照建角色（NFKC、長度、
        看不見的字元），撞名照 name_taken 同一句。改成了：GAMES 換到新名號底下（帳號已經指向新名號，下一個請求照新名號找）。"""
        _mall_on()
        name = unicodedata.normalize("NFKC", str(body.get("name", ""))).strip()
        if not name:
            raise shell.GameError("請先輸入新的名號。")
        if len(name) > shell.NAME_MAX or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in name):
            raise shell.GameError(shell.BAD_NAME)
        game = shell._game(request)
        old = game.state.player.name
        msgs = shell.act(game, lambda g: actions.rename_self(g, name, shell.name_taken))
        new = game.state.player.name
        if new != old:
            with shell._GAMES_LOCK:
                shell.GAMES.pop(old.casefold(), None)
                shell.GAMES[new.casefold()] = game
        shell._tell_tabs(game)
        return {"message": shell.joined(msgs), "renamed": new != old, "name": new, "main": shell.look(game, shell.main_view)}

    @r.post("/api/admin/mall")
    def api_admin_mall(request: Request, body: dict = Body(...)):
        """管理者查一個名號（或帳號）的帳（actions.admin_ledger）。名號放在 POST 的內容裡、不放在網址上；查不到回 {refusal}。"""
        _mall_on()
        game = shell._game(request)
        if not game.is_admin():
            raise HTTPException(403)
        name = str(body.get("name", ""))[:40]
        return shell.act_look(game, lambda g: None, lambda g: actions.admin_ledger(g, name))[1]

    return r
