"""客服的 API（帳號與客服第 211 批；設計 6.1、6.2、6.6）：殼照 FEATURES 掛（路徑 /api/support/* 不跟別的路由重疊，先後不影響）。
每一條第一行 _gate：先要登入（沒登入 401，開著關著一樣），再看開關（Config.support.enabled 關著 404）。客服那四條再過 _staff：不是名單上的帳號一律 404
（跟沒有這條路同一句，不透露有客服頁）。不走 AdminTool、不放寬 /api/admin、is_admin 不動。

殼的東西照 shell.<名字> 當下讀（測試換掉的也看得到）；現在時間照 shell.time.time()（路由是殼，規則層 rules.py 不讀時鐘）。
玩家寫的字原樣存、原樣回（畫面只過 esc，不經 markdown）；單上的帳號、名號、時間、版本由伺服器填，不收客戶端的。
這個檔只在殼掛路由時才 import（要 fastapi）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from tianxia.database import default_path, open_database

from . import accounts_view, rules, staff, store
from .store import Refused

# 推播的內文（標題照殼的 NOTICE_TITLE）；notify 包的「客服」種類關掉就不送
PUSH_TEXT = "客服回覆了你的單。"  # 待 joy 潤


def sidecar_path():
    return store.store_path(default_path())


def _gate(shell, request: Request) -> str:
    key = shell._account(request)  # 沒登入 401（先於開關：不用登入的路由清單不加這一包）
    if not shell.CONTENT.config.support.enabled:
        raise HTTPException(404)
    return key


def _me(shell, key: str) -> accounts_view.Who:
    who = accounts_view.by_key(open_database(), key)
    if who is None:
        raise HTTPException(401, "請先登入。")
    return who


def _staff(shell, request: Request) -> accounts_view.Who:
    who = _me(shell, _gate(shell, request))
    if not staff.is_staff(shell.CONTENT.config, who):
        raise HTTPException(404)  # 跟沒有這條路同一句
    return who


def _refused(shell, e: Refused):
    return shell.GameError(str(e))


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _version(shell) -> str:
    notes = shell.patch_notes()
    return notes[0]["date"] if notes else ""


def _player_ticket(t: dict, replies: list[dict]) -> dict:
    """玩家看的一張單：不含內部註記、不含誰回的帳號；客服那一側只寫「客服」。"""
    return {
        "id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]), "body": t["body"],
        "status": t["status"], "created": t["created"], "updated": t["updated"],
        "replies": [{"staff": bool(r["staff"]), "body": r["body"], "created": r["created"]} for r in replies if rules.visible_to_player(r)],
    }


def _mine(shell, who: accounts_view.Who, sidecar: store.SupportStore | None) -> dict:
    if sidecar is None:
        return {"tickets": [], "categories": rules.CATEGORIES, "body_max": shell.CONTENT.config.support.body_max}
    tickets = [_player_ticket(t, sidecar.replies(t["id"], internal=False)) for t in sidecar.mine(who.id, who.created)]
    return {"tickets": tickets, "categories": rules.CATEGORIES, "body_max": shell.CONTENT.config.support.body_max}


def _staff_ticket(t: dict, replies: list[dict]) -> dict:
    """客服看的一張單：全部回覆（含內部註記）＋帳號卡（這批只畫單上已有的：帳號、名號、建帳號日；查帳號是客服二）。"""
    return {
        "id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]), "body": t["body"],
        "status": t["status"], "admin_flag": bool(t["admin_flag"]), "created": t["created"], "updated": t["updated"], "version": t["version"],
        "account": {"id": t["account_id"], "login": t["login"], "character": t["character"], "created": t["account_created"]},
        "replies": [{"staff": bool(r["staff"]), "internal": bool(r["internal"]), "body": r["body"], "created": r["created"]} for r in replies],
    }


def _push(shell, ticket: dict, now: float) -> None:
    """客服回覆了（不是內部註記）：經殼的 WEB_PUSH 推一則給單的主人。沒開推播、帳號不在、關掉了「客服」這一種都不送。"""
    push = shell.WEB_PUSH
    if push is None:
        return
    owner = accounts_view.by_id(open_database(), ticket["account_id"])
    if owner is None or owner.created != ticket["account_created"]:
        return
    if "support" in push.store.kinds_off(owner.key):
        return
    push.send(owner.key, shell.NOTICE_TITLE, PUSH_TEXT, tag="support", now=now)


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/support/ticket")
    def api_support_ticket(request: Request, body: dict = Body(default={})):
        """玩家送一張單：{category, body}。帳號、名號、時間、版本伺服器填（客戶端塞的其他欄位不看）。回 {id, mine}。"""
        who = _me(shell, _gate(shell, request))
        cfg = shell.CONTENT.config.support
        category, text = str(body.get("category", "")), str(body.get("body", ""))
        why = rules.ticket_problem(category, text, cfg.body_max)
        if why is not None:
            raise shell.GameError(why)
        sidecar = store.open_store(sidecar_path(), create=True)
        try:
            tid = sidecar.add_ticket(account_id=who.id, account_created=who.created, login=who.login, character=who.character or "",
                                     version=_version(shell), category=category, body=text.strip(), now=shell.time.time(),
                                     open_max=cfg.open_max, daily_max=cfg.daily_max)
        except Refused as e:
            raise _refused(shell, e) from None
        return {"id": tid, "mine": _mine(shell, who, sidecar)}

    @r.get("/api/support/mine")
    def api_support_mine(request: Request):
        """自己的單與看得到的回覆（不含內部註記）；看了就把客服的回覆記成看過。"""
        who = _me(shell, _gate(shell, request))
        sidecar = store.open_store(sidecar_path(), create=False)
        out = _mine(shell, who, sidecar)
        if sidecar is not None:
            sidecar.mark_seen(who.id, who.created)
        return out

    @r.post("/api/support/reply")
    def api_support_reply(request: Request, body: dict = Body(default={})):
        """玩家再回一句：{id, body}。單號、帳號、建帳號的時間都對才行，否則 404 同一句（別人的、不存在的、帳號換過的都一樣）。"""
        who = _me(shell, _gate(shell, request))
        cfg = shell.CONTENT.config.support
        sidecar = store.open_store(sidecar_path(), create=False)
        if sidecar is None:
            raise HTTPException(404, rules.NOT_FOUND)
        tid = _int(body.get("id"))
        t = sidecar.ticket(tid)
        if t is None or not rules.owns(t, who.id, who.created):
            raise HTTPException(404, rules.NOT_FOUND)
        text = str(body.get("body", ""))
        why = rules.body_problem(text, cfg.body_max)
        if why is not None:
            raise shell.GameError(why)
        try:
            sidecar.player_reply(tid, who.id, who.created, text.strip(), shell.time.time())
        except Refused as e:
            if str(e) == rules.NOT_FOUND:
                raise HTTPException(404, rules.NOT_FOUND) from None
            raise _refused(shell, e) from None
        return {"mine": _mine(shell, who, sidecar)}

    @r.get("/api/support/queue")
    def api_support_queue(request: Request):
        """客服頁：沒回的、等玩家、今天新單三個數與沒結的單。"""
        _staff(shell, request)
        sidecar = store.open_store(sidecar_path(), create=False)
        if sidecar is None:
            return {"open": 0, "waiting": 0, "fresh": 0, "tickets": [], "categories": rules.CATEGORIES}
        q = sidecar.queue(shell.time.time())
        q["tickets"] = [{"id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]),
                         "body": t["body"], "status": t["status"], "admin_flag": bool(t["admin_flag"]), "character": t["character"],
                         "login": t["login"], "created": t["created"], "updated": t["updated"]} for t in q["tickets"]]
        q["categories"] = rules.CATEGORIES
        return q

    @r.get("/api/support/ticket/{tid}")
    def api_support_ticket_view(tid: int, request: Request):
        """客服看一張單：全部回覆（含內部註記）＋帳號卡（單上已有的）。"""
        _staff(shell, request)
        sidecar = store.open_store(sidecar_path(), create=False)
        t = sidecar.ticket(tid) if sidecar is not None else None
        if t is None:
            raise HTTPException(404, rules.NOT_FOUND)
        return _staff_ticket(t, sidecar.replies(tid, internal=True))

    @r.post("/api/support/answer")
    def api_support_answer(request: Request, body: dict = Body(default={})):
        """客服回一則：{id, body, then: wait|close|admin}。回覆並等玩家／回覆並結單／請管理者處理（內部註記，玩家看不到，不推播）。"""
        who = _staff(shell, request)
        then = str(body.get("then", ""))
        if then not in rules.THEN:
            raise shell.GameError(rules.BAD_THEN)
        text = str(body.get("body", ""))
        why = rules.body_problem(text, shell.CONTENT.config.support.body_max)
        if why is not None:
            raise shell.GameError(why)
        sidecar = store.open_store(sidecar_path(), create=False)
        if sidecar is None:
            raise HTTPException(404, rules.NOT_FOUND)
        now = shell.time.time()
        tid = _int(body.get("id"))
        try:
            t = sidecar.staff_reply(tid, who.id, text.strip(), then, now)
        except Refused as e:
            if str(e) == rules.NOT_FOUND:
                raise HTTPException(404, rules.NOT_FOUND) from None
            raise _refused(shell, e) from None
        if then != "admin":
            _push(shell, t, now)
        return _staff_ticket(t, sidecar.replies(tid, internal=True))

    @r.post("/api/support/close")
    def api_support_close(request: Request, body: dict = Body(default={})):
        """客服結單：{id}。"""
        _staff(shell, request)
        sidecar = store.open_store(sidecar_path(), create=False)
        if sidecar is None:
            raise HTTPException(404, rules.NOT_FOUND)
        tid = _int(body.get("id"))
        try:
            sidecar.close(tid, shell.time.time())
        except Refused:
            raise HTTPException(404, rules.NOT_FOUND) from None
        return _staff_ticket(sidecar.ticket(tid), sidecar.replies(tid, internal=True))

    return r
