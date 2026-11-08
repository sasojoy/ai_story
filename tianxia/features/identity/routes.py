"""帳號綁定的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。

- GET /api/identity/gate（第 201 批）：登入頁問哪幾條路開著。
- POST /api/identity/start、GET /auth/{provider}/callback、POST /api/identity/character（第 202 批，設計 4.2）：LINE、Google 登入；
  驗過、查無對應的身分不開帳號，只留 pending（旁檔，綁 tx_pending cookie），建角色成功那一筆交易才開帳號、寫 logins。
都不拿行動鎖、不叫模型。殼的東西照 shell.<名字> 當下讀（測試換掉的也看得到）；現在時間照 shell.time.time()（路由是殼，oauth.py 不讀時鐘）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets as _rand

from fastapi import APIRouter, Body, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from tianxia.core import identity_base

from . import oauth, store

TICKET_COOKIE = "tx_oauth"  # start 發、回呼比對（票上存它的雜湊）：擋登入 CSRF
TICKET_PATH = "/auth/"
PENDING_COOKIE = "tx_pending"  # 回呼發、建角色那一步讀
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
    def api_start(request: Request, response: Response, body: dict = Body(...)):
        """開一張一次性單、回對方的授權網址（不用 302：fetch 跟不了外站轉址）。不用登入（NO_LOGIN_ROUTES 寫了理由）。
        已經登入的瀏覽器擋下（設計「先問要不要換」的保守版：快速登入只在登入頁有）。同一個來源 IP 一小時 start_per_hour 次。"""
        gate()
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
    def api_character(request: Request, response: Response, body: dict = Body(...)):
        """建角色那一步（第三方驗過、還沒有帳號）：開帳號、寫 logins、建角色同一筆交易，名號不合格整筆退、帳號不留。
        先看 cookie（tx_pending、tx_session 都沒帶 401，同第 211 批「先 401 再 gate」），再過 gate；pending 拿不到 401 同一句。
        開帳號那一步共用殼的註冊限制（shell._register_allowed、_registered：密碼註冊與這裡一起算）。"""
        token = request.cookies.get(PENDING_COOKIE) or ""
        if not token and shell.SESSIONS.get(request.cookies.get(shell.COOKIE, "")) is None:
            raise HTTPException(401, PLEASE_LOGIN)
        gate()
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
                    key = accounts.create_without_password(provider, sub, oauth.DISPLAY[provider])
                    shell.create_character(key, body.get("name", ""), body.get("gender"))
                    made = True
            if made:
                shell._registered(ip, now)
                secret = identity_base.read_key()
                if secret is not None:
                    side.record_verified(accounts.account_id(key), provider, identity_base.subject_hmac(secret, provider, sub), now)
        side.drop_pending(_digest(token))
        response.delete_cookie(PENDING_COOKIE, path=PENDING_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        shell._start_session(request, response, key)
        return shell._entry(key)

    return r
