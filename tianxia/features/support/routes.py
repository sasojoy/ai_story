"""客服的 API（帳號與客服第 211 批；設計 6.1、6.2、6.6）：殼照 FEATURES 掛（路徑 /api/support/* 不跟別的路由重疊，先後不影響）。
每一條都是 async def，第一行 _gate_off（第 212 批，計畫「J 波落地時 PM 加的」第 1 條）：Config.support.enabled 關著一律 404
{"detail":"Not Found"}，先於登入、先於參數解析（沒登入、壞 JSON、單號不是數字都一樣，跟沒有這條路同一個回應）。之後才自己解 JSON
（壞的或不是物件 422）、單號在 gate 之後轉數字（不是數字 404「找不到這張單。」），再把同步的本體丟進執行緒池（sqlite 與 shell._account
都在那裡，不卡事件迴圈；server.api_events 的前例）。本體第一步 _gate 認登入（沒登入 401）。客服那幾條再過 _staff：不是名單上的帳號一律 404
（跟沒有這條路同一句，不透露有客服頁）。例外是 GET /api/support/mailbox（第 214 批）：gate 之後直接回設定裡的信箱與那一行字，不認登入、不開旁檔。不走 AdminTool、不放寬 /api/admin、is_admin 不動。

殼的東西照 shell.<名字> 當下讀（測試換掉的也看得到）；現在時間照 shell.time.time()（路由是殼，規則層 rules.py 不讀時鐘）。
玩家寫的字原樣存、原樣回（畫面只過 esc，不經 markdown）；單上的帳號、名號、時間、版本由伺服器填，不收客戶端的。
這個檔只在殼掛路由時才 import（要 fastapi）。"""
from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from tianxia.core import identity_base
from tianxia.database import default_path, open_database

from . import FEATURE, accounts_view, lookup, rules, staff, store
from .store import Refused

# 推播的內文（標題照殼的 NOTICE_TITLE）；notify 包的「客服」種類關掉就不送
PUSH_TEXT = "客服回覆了你的單。"  # 待 joy 潤


def sidecar_path():
    return store.store_path(default_path())


def files_path():
    """截圖的資料夾（第 215 批）：跟旁檔並排，跟著 TIANXIA_DB。只有上傳那一支建它。"""
    return store.files_dir(default_path())


def _gate_off(shell) -> None:
    """每一條路由的第一行：關著 404（HTTPException 的預設字 Not Found，跟沒有這條路一樣）。"""
    if not shell.CONTENT.config.support.enabled:
        raise HTTPException(404)


async def _json(request: Request) -> dict:
    """gate 之後才讀內文：空的當 {}（同舊的 Body(default={})），壞的或不是物件 422。"""
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(422) from None
    if not isinstance(data, dict):
        raise HTTPException(422)
    return data


def _gate(shell, request: Request) -> str:
    return shell._account(request)  # 沒登入 401（開關在 _gate_off 已經看過；不用登入的只有 /api/support/mailbox，它不叫這一支）


def _me(shell, key: str) -> accounts_view.Who:
    who = accounts_view.by_key(open_database(), key)
    if who is None:
        raise HTTPException(401, "請先登入。")
    return who


def _staff(shell, request: Request) -> accounts_view.Who:
    who = _me(shell, _gate(shell, request))
    if not staff.is_staff(shell.CONTENT.config, who):
        raise HTTPException(404)  # 跟沒有這條路同一句
    # 帳號與客服第 204 批（設計 4.4、6.2）：客服權限要這次是密碼登入、而且 6 小時內登入或重驗過（identity 關著看 session 建立的時間）；
    # 不夠的跟不是客服同一句
    if not identity_base.staff_session_ok(open_database(), shell.CONTENT, request.cookies.get(shell.COOKIE), shell.time.time()):
        raise HTTPException(404)
    return who


def _refused(shell, e: Refused):
    return shell.GameError(str(e))


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _tid(text: str) -> int:
    """路徑上的單號（gate 之後才轉）：不是數字 404「找不到這張單。」。"""
    if not (text.isascii() and text.isdigit()):
        raise HTTPException(404, rules.NOT_FOUND)
    return int(text)


def _version(shell) -> str:
    notes = shell.patch_notes()
    return notes[0]["date"] if notes else ""


def _files(files: list[dict]) -> list[dict]:
    """單上的截圖（第 215 批）：只給序號、種類、大小（看圖走 GET /api/support/file/<單號>/<seq>）。"""
    return [{"seq": f["seq"], "kind": f["kind"], "bytes": f["bytes"]} for f in files]


def _player_ticket(t: dict, replies: list[dict], files: list[dict]) -> dict:
    """玩家看的一張單：不含內部註記、不含誰回的帳號；客服那一側只寫「客服」。"""
    return {
        "id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]), "body": t["body"],
        "status": t["status"], "created": t["created"], "updated": t["updated"],
        "replies": [{"staff": bool(r["staff"]), "body": r["body"], "created": r["created"]} for r in replies if rules.visible_to_player(r)],
        "files": _files(files),
    }


def _mine(shell, who: accounts_view.Who, sidecar: store.SupportStore | None) -> dict:
    if sidecar is None:
        return {"tickets": [], "categories": rules.CATEGORIES, "body_max": shell.CONTENT.config.support.body_max}
    tickets = [_player_ticket(t, sidecar.replies(t["id"], internal=False), sidecar.files(t["id"])) for t in sidecar.mine(who.id, who.created)]
    return {"tickets": tickets, "categories": rules.CATEGORIES, "body_max": shell.CONTENT.config.support.body_max}


def _staff_ticket(t: dict, replies: list[dict], files: list[dict]) -> dict:
    """客服看的一張單：全部回覆（含內部註記）＋單上已有的帳號（帳號、名號、建帳號日）＋截圖（第 215 批）。"""
    return {
        "id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]), "body": t["body"],
        "status": t["status"], "admin_flag": bool(t["admin_flag"]), "created": t["created"], "updated": t["updated"], "version": t["version"],
        "account": {"id": t["account_id"], "login": t["login"], "character": t["character"], "created": t["account_created"]},
        "replies": [{"staff": bool(r["staff"]), "internal": bool(r["internal"]), "body": r["body"], "created": r["created"]} for r in replies],
        "files": _files(files),
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


# ── 同步的本體（執行緒池裡跑）──

def _file_ticket(shell, request: Request, body: dict) -> dict:
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


def _my_tickets(shell, request: Request) -> dict:
    """自己的單與看得到的回覆（不含內部註記）；看了就把客服的回覆記成看過。"""
    who = _me(shell, _gate(shell, request))
    sidecar = store.open_store(sidecar_path(), create=False)
    out = _mine(shell, who, sidecar)
    if sidecar is not None:
        sidecar.mark_seen(who.id, who.created)
    return out


def _player_reply(shell, request: Request, body: dict) -> dict:
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


def _queue(shell, request: Request) -> dict:
    """客服頁：沒回的、等玩家、今天新單三個數與沒結的單；lookups_left 是這位客服這一小時還能查幾次帳號（第 212 批）。"""
    who = _staff(shell, request)
    hourly = shell.CONTENT.config.support.lookup_hourly
    sidecar = store.open_store(sidecar_path(), create=False)
    if sidecar is None:
        return {"open": 0, "waiting": 0, "fresh": 0, "tickets": [], "categories": rules.CATEGORIES, "lookups_left": hourly}
    now = shell.time.time()
    q = sidecar.queue(now)
    q["tickets"] = [{"id": t["id"], "category": t["category"], "category_name": rules.CATEGORIES.get(t["category"], t["category"]),
                     "body": t["body"], "status": t["status"], "admin_flag": bool(t["admin_flag"]), "character": t["character"],
                     "login": t["login"], "created": t["created"], "updated": t["updated"]} for t in q["tickets"]]
    extras = sidecar.queue_extras([t["id"] for t in q["tickets"]])  # 第 215 批：每一列多張數 file_count
    for t in q["tickets"]:
        t.update(extras[t["id"]])
    q["categories"] = rules.CATEGORIES
    q["lookups_left"] = sidecar.lookups_left(who.id, now, hourly)
    return q


def _view_ticket(shell, request: Request, text: str) -> dict:
    """客服看一張單：全部回覆（含內部註記）＋單上的帳號帶出的帳號卡 card（第 212 批；帳號 id 與建帳號的時間都對才給，不對給
    {"gone": true}）。帶卡不算查帳次數、照樣記一筆。單號在認過客服之後才轉（不是客服的人看不出這條路在）。"""
    who = _staff(shell, request)
    tid = _tid(text)
    sidecar = store.open_store(sidecar_path(), create=False)
    t = sidecar.ticket(tid) if sidecar is not None else None
    if t is None:
        raise HTTPException(404, rules.NOT_FOUND)
    out = _staff_ticket(t, sidecar.replies(tid, internal=True), sidecar.files(tid))
    out["card"] = lookup.card(open_database(), t["account_id"], ledger_rows=shell.CONTENT.config.support.ledger_rows,
                              created_must=t["account_created"])
    found = None if out["card"].get("gone") else t["account_id"]
    sidecar.log_card(staff_account_id=who.id, ticket_id=tid, shown=t["login"] or f"id:{t['account_id']}", found=found, now=shell.time.time())
    return out


def _lookup(shell, request: Request, body: dict) -> dict:
    """查別的帳號：{id（單號）, kind（login|email|phone）, text}。單不存在 404（不算、不留：沒帶單就不是一次查詢）；寫法不對回那一句
    （不算、不留）；這一小時滿了記一筆 limit、回那一句；否則查、記一筆（查無也算一次）。回 {found, card, left, message}。"""
    who = _staff(shell, request)
    cfg = shell.CONTENT.config.support
    sidecar = store.open_store(sidecar_path(), create=False)
    tid = _int(body.get("id"))
    if sidecar is None or sidecar.ticket(tid) is None:
        raise HTTPException(404, rules.NOT_FOUND)
    kind, text = str(body.get("kind", "")), str(body.get("text", ""))
    why = rules.lookup_problem(kind, text)
    if why is not None:
        raise shell.GameError(why)
    value = rules.lookup_value(kind, text)
    db = open_database()
    outcome, found, left = sidecar.lookup(staff_account_id=who.id, ticket_id=tid, kind=kind, shown=rules.lookup_shown(kind, value),
                                          now=shell.time.time(), hourly=cfg.lookup_hourly,
                                          find=lambda: lookup.find(db, shell.CONTENT, kind, value))
    if outcome == "limit":
        raise shell.GameError(rules.LOOKUP_LIMIT.format(n=cfg.lookup_hourly))
    card = None if found is None else lookup.card(db, found, ledger_rows=cfg.ledger_rows)
    return {"found": found is not None, "card": card, "left": left, "message": "" if found is not None else rules.LOOKUP_NONE}


def _answer(shell, request: Request, body: dict) -> dict:
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
    return _staff_ticket(t, sidecar.replies(tid, internal=True), sidecar.files(tid))


def _close(shell, request: Request, body: dict) -> dict:
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
    return _staff_ticket(sidecar.ticket(tid), sidecar.replies(tid, internal=True), sidecar.files(tid))


# ── 截圖（客服自動受理第 215 批；設計 5.1、5.5）──

def _mb(n: int) -> str:
    """位元組 → 拒絕那一句的 MB（3,000,000 → 「3」）。"""
    return f"{n / 1_000_000:g}"


def _upload(shell, request: Request, text_id: str, raw: bytes) -> dict:
    """讀完內文之後的同步本體：單號 → 檔頭 → 登入 → 單在、是自己的、沒結 → 寫 .part → add_file（交易裡算 seq、記一列、換名）。
    別人的單、不存在的單 404 同一句（同 _player_reply）；不是圖、結了、滿了回那一句。失敗一律刪 .part。"""
    tid = _tid(text_id)
    kind = rules.image_kind(raw[:12])
    if kind is None:
        raise shell.GameError(rules.FILE_NOT_IMAGE)
    who = _me(shell, _gate(shell, request))
    cfg = shell.CONTENT.config.support
    sidecar = store.open_store(sidecar_path(), create=False)
    t = sidecar.ticket(tid) if sidecar is not None else None
    if t is None or not rules.owns(t, who.id, who.created):
        raise HTTPException(404, rules.NOT_FOUND)
    if t["status"] == rules.CLOSED:
        raise shell.GameError(rules.CLOSED_ALREADY)
    folder = files_path() / str(tid)
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f".upload-{uuid.uuid4().hex}.part"
    try:
        part.write_bytes(raw)
        row = sidecar.add_file(tid, who.id, who.created, kind, len(raw), hashlib.sha256(raw).hexdigest(), shell.time.time(), cfg.files_max,
                               part=part)
    except Refused as e:
        if str(e) == rules.NOT_FOUND:
            raise HTTPException(404, rules.NOT_FOUND) from None
        raise _refused(shell, e) from None
    finally:
        part.unlink(missing_ok=True)
    return {"id": tid, "seq": row["seq"], "kind": row["kind"], "bytes": row["bytes"], "files": _files(sidecar.files(tid))}


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/support/ticket")
    async def api_support_ticket(request: Request):
        _gate_off(shell)
        body = await _json(request)
        return await run_in_threadpool(_file_ticket, shell, request, body)

    @r.get("/api/support/mine")
    async def api_support_mine(request: Request):
        _gate_off(shell)
        return await run_in_threadpool(_my_tickets, shell, request)

    @r.post("/api/support/reply")
    async def api_support_reply(request: Request):
        _gate_off(shell)
        body = await _json(request)
        return await run_in_threadpool(_player_reply, shell, request, body)

    @r.get("/api/support/queue")
    async def api_support_queue(request: Request):
        _gate_off(shell)
        return await run_in_threadpool(_queue, shell, request)

    @r.get("/api/support/ticket/{tid}")
    async def api_support_ticket_view(tid: str, request: Request):
        _gate_off(shell)
        return await run_in_threadpool(_view_ticket, shell, request, tid)

    @r.post("/api/support/answer")
    async def api_support_answer(request: Request):
        _gate_off(shell)
        body = await _json(request)
        return await run_in_threadpool(_answer, shell, request, body)

    @r.post("/api/support/close")
    async def api_support_close(request: Request):
        _gate_off(shell)
        body = await _json(request)
        return await run_in_threadpool(_close, shell, request, body)

    @r.post("/api/support/lookup")
    async def api_support_lookup(request: Request):
        _gate_off(shell)
        body = await _json(request)
        return await run_in_threadpool(_lookup, shell, request, body)

    @r.post("/api/support/file")
    async def api_support_file(request: Request):
        """截圖（第 215 批）：內文就是圖的位元組（不解 JSON）。gate → 認登入（只查記憶體的 SESSIONS，在讀內文之前）→ Content-Length 說超過的
        提早拒（說不超過的不信）→ 串流累計、超過 file_bytes_max 立刻停止讀、拒絕 → 同步的本體丟執行緒池。"""
        _gate_off(shell)
        shell._account(request)
        cap = shell.CONTENT.config.support.file_bytes_max
        told = request.headers.get("content-length", "")
        if told.isascii() and told.isdigit() and int(told) > cap:
            raise shell.GameError(rules.FILE_TOO_BIG.format(mb=_mb(cap)))
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > cap:
                raise shell.GameError(rules.FILE_TOO_BIG.format(mb=_mb(cap)))
        return await run_in_threadpool(_upload, shell, request, request.query_params.get("id", ""), bytes(raw))

    @r.get("/api/support/mailbox")
    async def api_support_mailbox():
        """登入頁的客服信箱那一行（第 214 批；web/support.js 畫）：不用登入、不看 cookie、不開旁檔，回應不因人而異（只回設定裡公開的信箱）。"""
        _gate_off(shell)
        config = shell.CONTENT.config
        return {"mailbox": config.support.mailbox, "line": FEATURE.gate_slot(config)}

    return r
