"""帳號綁定的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。

- GET /api/identity/gate（第 201 批）：登入頁問哪幾條路開著。
- POST /api/identity/start、GET /auth/{provider}/callback、POST /api/identity/character（第 202 批，設計 4.2）：LINE、Google 登入；
  驗過、查無對應的身分不開帳號，只留 pending（旁檔，綁 tx_pending cookie），建角色成功那一筆交易才開帳號、寫 logins。
- POST /api/identity/code/send、/api/identity/code/verify（第 203 批）：驗證碼登入；查無帳號一樣只留 pending，建角色走上面的 character。
  寄送與 Turnstile 是網路呼叫。
都不拿行動鎖、不叫模型；全部不用登入（tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由）。
殼的東西照 shell.<名字> 當下讀（測試換掉的也看得到）；第三方登入的現在時間照 shell.time.time()（路由是殼，oauth.py 不讀時鐘），
驗證碼兩條也照 shell.time.time()（第 204 批，K 波審查：原本自己 import time）、傳進 codes。新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets as _rand

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from tianxia.accounts import _token_hash
from tianxia.core import identity_base
from tianxia.database import open_database

from . import codes, oauth, senders, store

CODE_COOKIE = "tx_code"  # 這張驗證碼的單（challenge id）；max_age＝code_ttl
DEV_COOKIE = "tx_dev"  # 曾用這個身分成功登入的瀏覽器（只存 sha256）；成功登入才發
DEV_SECONDS = 365 * 86400
TICKET_COOKIE = "tx_oauth"  # start 發、回呼比對（票上存它的雜湊）：擋登入 CSRF
TICKET_PATH = "/auth/"
PENDING_COOKIE = "tx_pending"  # 第三方回呼與驗證碼查無帳號時發、建角色那一步讀
PENDING_PATH = "/api/identity/"
ALREADY_IN = "你已經登入了，要換帳號請先登出"  # 待 joy 潤
TOO_OFTEN = "太頻繁了，請稍後再試"  # 待 joy 潤
PLEASE_LOGIN = "請先登入。"  # 殼 _account 的同一句（不是新字）
START_WINDOW = 3600.0


def gate_info(content) -> dict:
    """登入頁要知道的：哪幾條路開著、Turnstile 的網站金鑰（公開的那一把）。只讀設定與金鑰檔，跟誰來問無關。
    line、google 要 oauth.ready（金鑰兩欄、redirect_base）才列；email、phone 照設定列（第 203 批才接）。客服信箱第 202 批拿掉（客服包畫）。"""
    cfg = content.config.identity
    ways = [w for w in cfg.ways if w not in oauth.PROVIDERS or oauth.ready(content, w)]
    return {"ways": ways, "turnstile": cfg.turnstile_site_key}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _code_gate(shell, channel: str | None = None) -> bytes:
    """驗證碼兩條的 gate：關著、金鑰讀不到、這條路不在 ways（verify 是 email、phone 都不在）一律 404。回金鑰。"""
    key = identity_base.read_key() if identity_base.on(shell.CONTENT) else None
    if key is None:
        raise HTTPException(404)
    ways = shell.CONTENT.config.identity.ways
    if channel is None:
        if not any(ch in ways for ch in codes.CHANNELS):
            raise HTTPException(404)
    elif channel not in codes.CHANNELS or channel not in ways:
        raise HTTPException(404)
    return key


async def _json(request: Request, required: bool) -> dict:
    """gate 之後才讀內文（K 波修：Body(...) 在進函式前就解析，關著打壞的內文回 422、不是 404）。
    空的：required 照舊的 Body(...) 回 422，否則當 {}（同舊的 Body(default={})）；壞的或不是物件 422。"""
    raw = await request.body()
    if not raw:
        if required:
            raise HTTPException(422)
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(422) from None
    if not isinstance(data, dict):
        raise HTTPException(422)
    return data


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def _cookie(shell, request: Request, response: Response, name: str, value: str, max_age: int, path: str = "/") -> None:
    response.set_cookie(name, value, httponly=True, samesite="lax", max_age=max_age, path=path, secure=shell.cookie_secure(request))


def _session_token(shell, response: Response) -> str | None:
    """shell._start_session 不回 token：從回應的 set-cookie 找 <COOKIE>= 那一條。"""
    prefix = f"{shell.COOKIE}="
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            text = value.decode("latin-1")
            if text.startswith(prefix):
                return text[len(prefix):].split(";", 1)[0]
    return None


def router(shell) -> APIRouter:
    r = APIRouter()

    def gate() -> None:
        if not identity_base.on(shell.CONTENT):
            raise HTTPException(404)

    def back(request: Request, code: str, via: str | None = None) -> RedirectResponse:
        """回首頁 /?auth=<代碼>（web/identity.js 讀完 replaceState）；一律刪 tx_oauth。"""
        resp = RedirectResponse(f"/?auth={code}" + (f"&via={via}" if via else ""), status_code=302)
        resp.delete_cookie(TICKET_COOKIE, path=TICKET_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        return resp

    @r.get("/api/identity/gate")
    def api_gate():
        """不用登入、不拿行動鎖、不看 cookie（tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由）；關著或金鑰讀不到 404。"""
        gate()
        return gate_info(shell.CONTENT)

    @r.post("/api/identity/start")
    async def api_start(request: Request, response: Response):
        """第一行 gate（關著 404，先於讀內文）；同步的本體丟進執行緒池。"""
        gate()
        body = await _json(request, required=True)
        return await run_in_threadpool(start, request, response, body)

    def start(request: Request, response: Response, body: dict):
        """開一張一次性單、回對方的授權網址（不用 302：fetch 跟不了外站轉址）。不用登入（NO_LOGIN_ROUTES 寫了理由）。
        已經登入的瀏覽器擋下（設計「先問要不要換」的保守版：快速登入只在登入頁有）。同一個來源 IP 一小時 start_per_hour 次。"""
        content = shell.CONTENT
        cfg = content.config.identity
        provider = body.get("provider")
        if body.get("purpose") != "login" or not isinstance(provider, str) or not oauth.ready(content, provider):
            raise HTTPException(404)
        if shell.SESSIONS.get(request.cookies.get(shell.COOKIE, "")) is not None:
            raise shell.GameError(ALREADY_IN)
        now = shell.time.time()
        side = store.IdentityStore()
        if not side.count_and_record(f"oauth:{shell.client_ip(request)}", START_WINDOW, cfg.start_per_hour, now):
            raise shell.GameError(TOO_OFTEN)
        keys = oauth.secrets(provider)
        ticket = oauth.new_ticket()
        browser = _rand.token_urlsafe(32)
        side.put_ticket(_digest(ticket["state"]), provider, "login", _digest(browser), ticket["nonce"], ticket["verifier"],
                        expires=now + cfg.ticket_seconds, now=now)
        response.set_cookie(TICKET_COOKIE, browser, httponly=True, samesite="lax", max_age=cfg.ticket_seconds, path=TICKET_PATH,
                            secure=shell.cookie_secure(request))
        url = oauth.authorize_url(provider, keys["client_id"], oauth.redirect_uri(content, provider), ticket["state"], ticket["nonce"],
                                  ticket["verifier"])
        return {"url": url}

    @r.get("/auth/{provider}/callback")
    def api_callback(provider: str, request: Request):
        """對方轉回來：票一律作廢（拿走就刪）；取消回 auth=cancel，票、cookie、id_token 有一樣不對回 auth=fail；
        認得的身分開 session 回 auth=ok，不認得的留 pending 回 auth=new（不開帳號）。不用登入（NO_LOGIN_ROUTES 寫了理由）。"""
        gate()
        if provider not in oauth.PROVIDERS:
            raise HTTPException(404)
        content = shell.CONTENT
        cfg = content.config.identity
        q = request.query_params
        now = shell.time.time()
        side = store.IdentityStore()
        state = q.get("state") or ""
        ticket = side.take_ticket(_digest(state), now) if state else None
        if q.get("error"):
            return back(request, "cancel")
        browser = request.cookies.get(TICKET_COOKIE) or ""
        if ticket is None or ticket["provider"] != provider or ticket["purpose"] != "login" or not browser \
                or not hmac.compare_digest(ticket["browser_hash"], _digest(browser)) or not oauth.ready(content, provider):
            return back(request, "fail")
        keys = oauth.secrets(provider)
        token = oauth.exchange(provider, q.get("code") or "", ticket["verifier"], oauth.redirect_uri(content, provider),
                               keys["client_id"], keys["client_secret"])
        sub = oauth.check(oauth.claims(token), provider, keys["client_id"], ticket["nonce"], now)
        if sub is None:
            return back(request, "fail")
        key = shell.account_store().login_key(provider, sub)
        if key is not None:
            resp = back(request, "ok")
            shell._start_session(request, resp, key)
            return resp
        pending = _rand.token_urlsafe(32)
        side.put_pending(_digest(pending), provider, sub, expires=now + cfg.pending_seconds, now=now)
        resp = back(request, "new", provider)
        resp.set_cookie(PENDING_COOKIE, pending, httponly=True, samesite="lax", max_age=cfg.pending_seconds, path=PENDING_PATH,
                        secure=shell.cookie_secure(request))
        return resp

    @r.post("/api/identity/character")
    async def api_character(request: Request, response: Response):
        """先看 cookie（401）、再 gate（404），都在讀內文之前；同步的本體丟進執行緒池。"""
        token = request.cookies.get(PENDING_COOKIE) or ""
        if not token and shell.SESSIONS.get(request.cookies.get(shell.COOKIE, "")) is None:
            raise HTTPException(401, PLEASE_LOGIN)
        gate()
        body = await _json(request, required=True)
        return await run_in_threadpool(character, request, response, body, token)

    def character(request: Request, response: Response, body: dict, token: str):
        """建角色那一步（第三方驗過、還沒有帳號）：開帳號、寫 logins、建角色同一筆交易，名號不合格整筆退、帳號不留。
        先看 cookie（tx_pending、tx_session 都沒帶 401，同第 211 批「先 401 再 gate」），再過 gate；pending 拿不到 401 同一句。
        開帳號那一步共用殼的註冊限制（shell._register_allowed、_registered：密碼註冊與這裡一起算）。"""
        now = shell.time.time()
        side = store.IdentityStore()
        got = side.get_pending(_digest(token), now) if token else None
        if got is None:
            raise HTTPException(401, PLEASE_LOGIN)
        provider, sub = got
        accounts = shell.account_store()
        key = accounts.login_key(provider, sub)
        made = False
        if key is None:
            ip = shell.client_ip(request)
            if not shell._register_allowed(ip, now):
                raise shell.GameError(shell.TOO_MANY_REGISTERS)
            with shell.open_database().transaction():  # create_without_password 與 create_character 的交易併進這一筆
                key = accounts.login_key(provider, sub)  # 連按兩次：前一下在這筆交易開始前已經開好
                if key is None:
                    # 驗證碼那條（第 203 批）的 pending：provider 是 email／phone、subject 已是加金鑰的雜湊、display 是遮罩過的號碼
                    display = oauth.DISPLAY.get(provider) or side.pending_display(_digest(token)) or provider
                    key = accounts.create_without_password(provider, sub, display)
                    shell.create_character(key, body.get("name", ""), body.get("gender"))
                    made = True
            if made:
                shell._registered(ip, now)
                secret = identity_base.read_key()
                if secret is not None:
                    hashed = identity_base.subject_hmac(secret, provider, sub) if provider in oauth.PROVIDERS else sub
                    side.record_verified(accounts.account_id(key), provider, hashed, now)
        side.drop_pending(_digest(token))
        response.delete_cookie(PENDING_COOKIE, path=PENDING_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        shell._start_session(request, response, key)
        return shell._entry(key)

    @r.post("/api/identity/code/send")
    async def api_code_send(request: Request, response: Response):
        """第一行 _code_gate（關著、沒金鑰、沒有驗證碼的路 404，先於讀內文）；同步的本體丟進執行緒池（本體照舊拿 channel 再過一次）。"""
        _code_gate(shell)
        body = await _json(request, required=False)
        return await run_in_threadpool(code_send, request, response, body)

    def code_send(request: Request, response: Response, body: dict):
        """{channel: "phone"/"email", to, turnstile}。寄出與額度滿了回同一份 {message, notice, privacy}（不透露有沒有帳號）；
        寄出才設 tx_code。打錯的、沒過 Turnstile、寄送服務壞了回各自那一句（400）。"""
        channel = str(body.get("channel") or "")
        key = _code_gate(shell, channel)
        now = shell.time.time()
        db = open_database()
        dev = request.cookies.get(DEV_COOKIE)
        status, reply, cid = codes.send(
            cfg=shell.CONTENT.config.identity, key=key, store=store.IdentityStore(), senders=senders.pick(shell.CONTENT),
            channel=channel, to=body.get("to"), token=body.get("turnstile"), ip=shell.client_ip(request),
            hostname=request.url.hostname, dev_hash=_hash(dev) if dev else None,
            is_bound=lambda subject: identity_base.account_key_for(db, channel, subject) is not None, now=now,
        )
        if status != 200:
            raise shell.GameError(reply["error"])
        if cid is not None:
            _cookie(shell, request, response, CODE_COOKIE, cid, shell.CONTENT.config.identity.code_ttl)
        return reply

    @r.post("/api/identity/code/verify")
    async def api_code_verify(request: Request, response: Response):
        """第一行 _code_gate（關著、沒金鑰、沒有驗證碼的路 404，先於讀內文）；同步的本體丟進執行緒池。"""
        _code_gate(shell)
        body = await _json(request, required=False)
        return await run_in_threadpool(code_verify, request, response, body)

    def code_verify(request: Request, response: Response, body: dict):
        """{code}；單從 tx_code 取。沒單、過期、錯碼回 BAD_CODE（錯碼算在單上）。對了：有帳號就開 session、記這次用哪一種登入、
        回 _entry；查無帳號只寫待處理（建角色之前不開帳號，設計 4.2）、設 tx_pending、回 {stage: create, pending: true}。"""
        key = _code_gate(shell)
        cfg = shell.CONTENT.config.identity
        side = store.IdentityStore()
        cid = request.cookies.get(CODE_COOKIE)
        peek = side.challenge(cid) if cid else None
        if peek is not None and peek.get("channel") and peek["channel"] not in cfg.ways:
            raise HTTPException(404)  # 這條路被拿掉了：同關著
        now = shell.time.time()
        row = codes.verify(cfg=cfg, key=key, store=side, cid=cid, code=body.get("code"), now=now)
        if row is None:
            raise shell.GameError(codes.BAD_CODE)
        channel, subject = row["channel"], row["subject_hmac"]
        account_key = identity_base.account_key_for(open_database(), channel, subject)
        if account_key is None:
            token = _rand.token_urlsafe(32)
            side.put_pending(_hash(token), channel, subject, expires=now + cfg.pending_seconds, now=now, display=row["display"])
            _cookie(shell, request, response, PENDING_COOKIE, token, cfg.pending_seconds, path=PENDING_PATH)
            response.delete_cookie(CODE_COOKIE)
            return {"stage": "create", "pending": True}
        dev = request.cookies.get(DEV_COOKIE) or ""
        if not 20 <= len(dev) <= 100:
            dev = _rand.token_urlsafe(32)
        side.trust_device(_hash(dev), subject, now)
        _cookie(shell, request, response, DEV_COOKIE, dev, DEV_SECONDS)
        response.delete_cookie(CODE_COOKIE)
        shell._start_session(request, response, account_key)
        token = _session_token(shell, response)
        if token is not None:
            side.set_session_auth(_token_hash(token), channel, now)
        account = shell.account_store().get(account_key)
        if account is not None and account.id is not None:
            side.record_verified(account.id, channel, subject, now)
        return shell._entry(account_key)

    return r
