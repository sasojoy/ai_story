"""帳號綁定的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。

- GET /api/identity/gate（第 201 批）：登入頁問哪幾條路開著。
- POST /api/identity/start、GET /auth/{provider}/callback、POST /api/identity/character（第 202 批，設計 4.2）：LINE、Google 登入；
  驗過、查無對應的身分不開帳號，只留 pending（旁檔，綁 tx_pending cookie），建角色成功那一筆交易才開帳號、寫 logins。
- POST /api/identity/code/send、/api/identity/code/verify（第 203 批）：驗證碼登入；查無帳號一樣只留 pending，建角色走上面的 character。
  寄送與 Turnstile 是網路呼叫。
- 第 204 批：start、code/send、code/verify 多 bind、reauth 兩種用途（要登入）；已登入再走 login 先回 {ask}（帶 switch: true 才換）；
  第三方與驗證碼登入成功由殼的 _start_session(…, method) 記這次用哪一種登入；帳號有密碼時發 tx_reset（忘記密碼）；門號過期的三種處理。
  新路由 /api/identity/me、reauth、unbind、password/set、password/reset、code/release、admin/accounts（都先 401 再 gate）；管理者工具 admin_tools。
都不拿行動鎖、不叫模型；第 201～203 批那五條不用登入（tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由），第 204 批的都要登入或 cookie。
殼的東西照 shell.<名字> 當下讀（測試換掉的也看得到）；第三方登入的現在時間照 shell.time.time()（路由是殼，oauth.py 不讀時鐘），
驗證碼兩條也照 shell.time.time()（第 204 批，K 波審查：原本自己 import time）、傳進 codes。新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets as _rand
import weakref

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from tianxia import accounts as shell_accounts
from tianxia.core import identity_base
from tianxia.core import terms_base  # 第 206 批：建角色那一步開帳號要兩個勾選、記同意版本（不 import terms 包）
from tianxia.database import open_database

from . import alerts, binding, codes, contacts, notes, oauth, senders, store

CODE_COOKIE = "tx_code"  # 這張驗證碼的單（challenge id）；max_age＝code_ttl
RESET_COOKIE = "tx_reset"  # 第 204 批：用綁定的方式登入、帳號有密碼時發（忘記密碼的證明）；path PENDING_PATH，max_age＝reset_seconds
RECHECK_COOKIE = "tx_recheck"  # 第 204 批：門號過期、帳號還有別種時發（「這不是我的帳號」）；path PENDING_PATH，max_age＝code_ttl
DEV_COOKIE = "tx_dev"  # 曾用這個身分成功登入的瀏覽器（只存 sha256）；成功登入才發
DEV_SECONDS = 365 * 86400
TICKET_COOKIE = "tx_oauth"  # start 發、回呼比對（票上存它的雜湊）：擋登入 CSRF
TICKET_PATH = "/auth/"
PENDING_COOKIE = "tx_pending"  # 第三方回呼與驗證碼查無帳號時發、建角色那一步讀
PENDING_PATH = "/api/identity/"
TOO_OFTEN = "太頻繁了，請稍後再試"  # 待 joy 潤
PLEASE_LOGIN = "請先登入。"  # 殼 _account 的同一句（不是新字）
START_WINDOW = 3600.0


def gate_info(content) -> dict:
    """登入頁要知道的：哪幾條路開著、Turnstile 的網站金鑰（公開的那一把）。只讀設定與金鑰檔，跟誰來問無關。
    line、google 要 oauth.ready（金鑰兩欄、redirect_base）才列；email、phone 照設定列（第 203 批才接）。客服信箱第 202 批拿掉（客服包畫）。"""
    cfg = content.config.identity
    ways = [w for w in cfg.ways if w not in oauth.PROVIDERS or oauth.ready(content, w)]
    # pw_min（第 209 批）：identity 開著時全體密碼的下限，註冊格那一行提示照它寫（這條路關著 404，關著拿不到）
    return {"ways": ways, "turnstile": cfg.turnstile_site_key, "pw_min": shell_accounts.STRICT_PASSWORD_MIN, **notice_info(content)}


def notice_info(content) -> dict:
    """第 210 批（設計第五節、個資法第 8 條）：驗證碼寄碼前那一張的個資告知短文與隱私權頁網址（同 codes.send 寄出後回的那兩鍵）。"""
    return {"notice": codes.NOTICE, "privacy": content.config.identity.privacy_url}


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


def admin_tools(shell) -> dict:
    """管理者工具（第 204 批；設計 6.5）：本體在 admin.py（不 import fastapi、不讀時鐘），這裡給 gate 與現實時間（殼的 shell.time）。"""
    from tianxia.core.features import AdminTool  # noqa: PLC0415

    from . import admin  # noqa: PLC0415

    def gate() -> None:  # 寫法刻意跟 router 的 gate 不同：sb 的 selftest（wicket 軌）要那一句全檔只有一處
        if identity_base.on(shell.CONTENT):
            return
        raise HTTPException(404)

    return {
        "identity_view": AdminTool(gate, lambda g, b: admin.view(shell, g, b)),
        # 第 210 批：通知不在行動鎖裡寄（真的簡訊、Email 是 HTTP 呼叫，卡在鎖裡全服都等）：鎖內只記下，放鎖之後 identity_notify 寄
        "identity_unbind": AdminTool(gate, lambda g, b: admin.unbind(shell, g, b, shell.time.time(), later=_LATER.setdefault(g, []))),
        "identity_delete": AdminTool(gate, lambda g, b: admin.delete(shell, g, b, shell.time.time())),
    }


# 第 210 批（企劃者 2026-11-09「2. ok」）：管理者解綁在行動鎖內記下要寄的通知（account_id、帳號鍵、拿掉的那一種、那一句），
# 鍵是那一份 Game（server.act 問 waiting、開 start 都拿同一份）；記憶體、不進存檔、不是 Game 的屬性
_LATER: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_log = logging.getLogger(__name__)


def outlock(shell):
    """放鎖之後的背景格 identity_notify（OUTLOCK_ORDER 外，接在表尾）：waiting 只讀這一份 Game 有沒有記下的；start 拿走、
    每一則再查一次那一種已經不在帳號上（動作丟例外、交易撤回的那一則不寄），才寄給剩下綁著的 Email、手機。寄失敗只記 log。"""
    from tianxia.core.features import Outlock, OutlockJob  # noqa: PLC0415

    def waiting(game):
        return _LATER.get(game) or None

    def start(game, got) -> None:
        pending = _LATER.pop(game, None) or []
        for account_id, key, provider, text in pending:
            try:
                if any(r["provider"] == provider for r in shell.account_store().logins_of(key)):
                    continue
                contacts.send_all(shell, store.IdentityStore(), account_id, text)
            except Exception:  # noqa: BLE001  寄不出去不影響回給管理者的話
                _log.exception("identity_notify")

    return Outlock(jobs=(OutlockJob("identity_notify", waiting, start),))


def router(shell) -> APIRouter:
    r = APIRouter()
    # 第 209 批：admin 包重設密碼之後經核心 identity_base.notify 寄通知（admin 包不能 import 這一包）；關著不會有人叫
    identity_base.set_notifier(lambda account_id, text: contacts.send_all(shell, store.IdentityStore(), account_id, text))

    def gate() -> None:
        if not identity_base.on(shell.CONTENT):
            raise HTTPException(404)

    def back(request: Request, code: str, via: str | None = None) -> RedirectResponse:
        """回首頁 /?auth=<代碼>（web/identity.js 讀完 replaceState）；一律刪 tx_oauth。"""
        resp = RedirectResponse(f"/?auth={code}" + (f"&via={via}" if via else ""), status_code=302)
        resp.delete_cookie(TICKET_COOKIE, path=TICKET_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        return resp

    # ── 第 204 批：登入的人、近期驗證、綁定的列 ─────────────

    def session_of(request: Request) -> tuple[str, str | None]:
        token = request.cookies.get(shell.COOKIE, "")
        return token, shell.SESSIONS.get(token)

    def logged_in(request: Request):
        """(token, Account)；沒登入或帳號不在 401（同殼的 _account 那一句）。"""
        token, key = session_of(request)
        account = shell.account_store().get(key) if key is not None else None
        if account is None or account.id is None:
            raise HTTPException(401, PLEASE_LOGIN)
        return token, account

    def need_recent(token: str, now: float) -> None:
        if not binding.recent(identity_base.session_auth(token), now, shell.CONTENT.config.identity):
            raise shell.GameError(binding.NEED_RECENT)

    def have_of(account) -> dict[str, dict]:
        """這個帳號的每一種（記號列不算）：provider → {subject, display}。"""
        rows = shell.account_store().logins_of(account.key)
        return {r["provider"]: r for r in rows if r["provider"] != binding.MARKER}

    def not_held(side, account, now: float) -> None:
        if binding.held(side.hold_until(account.id), now):
            raise shell.GameError(binding.ON_HOLD.format(days=shell.CONTENT.config.identity.stale_hold_days))

    def not_by_new(side, account, token: str, now: float) -> None:
        """這次拿來驗的那一種是新綁的（不滿 new_binding_hours）：不能拿來設密碼、解綁別的方式（設計 4.3）。"""
        by = binding.checked_by(identity_base.session_auth(token))
        cfg = shell.CONTENT.config.identity
        if by is not None and binding.is_new(side.meta(account.id).get(by), now, cfg):
            raise shell.GameError(binding.NEW_BINDING.format(hours=cfg.new_binding_hours))

    def switch_from(request: Request) -> None:
        """換帳號：登入成功那一下把這個瀏覽器原本的登入狀態登出（先問過一次，見 SWITCH_ASK）。"""
        token = request.cookies.get(shell.COOKIE, "")
        if token:
            shell.SESSIONS.pop(token, None)

    def after_binding_login(request: Request, response: Response, account_key: str, provider: str, now: float, side) -> None:
        """用綁定的方式登入、帳號有密碼：發忘記密碼的證明（tx_reset，reset_seconds 內有效；設計 4.4）。"""
        account = shell.account_store().get(account_key)
        if account is None or account.id is None or account.hash is None:
            return
        proof = _rand.token_urlsafe(32)
        side.put_reset(_hash(proof), account.id, provider, now)
        _cookie(shell, request, response, RESET_COOKIE, proof, shell.CONTENT.config.identity.reset_seconds, path=PENDING_PATH)

    def note(side, account_id: int, text: str, now: float) -> None:
        notes.add(side, account_id, text, now)

    def not_reset_held(account, now: float) -> None:
        """管理者重設密碼之後 reset_hold_hours 內不能綁新的方式（第 208 批；設計 6.4）：寄碼、開單之前擋（省一則簡訊）。"""
        if identity_base.reset_held(account.id, now):
            raise shell.GameError(binding.RESET_NO_BIND.format(hours=shell.CONTENT.config.identity.reset_hold_hours))

    def bound_back(request: Request, ticket: dict, provider: str, sub: str, hashed: str, now: float, side) -> RedirectResponse:
        """第三方回呼的綁定與重驗（第 204 批）：瀏覽器現在登入的帳號要是開單的那一個；回 auth=bound／taken／wait／reauth／fail。"""
        accounts = shell.account_store()
        token, key = session_of(request)
        account = accounts.get(key) if key is not None else None
        if account is None or account.id != ticket["account_id"]:
            return back(request, "fail")
        found = accounts.login_key(provider, sub)
        owner = accounts.account_id(found) if found is not None else None
        if ticket["purpose"] == "reauth":
            if owner != account.id or not identity_base.record_reauth(token, provider, now):
                return back(request, "fail")
            return back(request, "reauth")
        if identity_base.reset_held(account.id, now):  # 第 209 批：開單之後才被管理者重設的，回呼這一步也擋（網頁照 RESET_NO_BIND 那一句）
            return back(request, "held")
        if owner is not None:
            return back(request, "bound" if owner == account.id else "taken")
        if binding.rebind_wait(side.unbound_elsewhere(hashed, provider, account.id), now, shell.CONTENT.config.identity):
            return back(request, "wait")
        try:
            accounts.add_login(account.key, provider, sub, oauth.DISPLAY.get(provider, provider))
        except ValueError:
            return back(request, "taken")
        side.mark_bound(account.id, provider, hashed, now)
        note(side, account.id, binding.NOTE_BOUND.format(kind=binding.kind_name(provider)), now)
        contacts.send_all(shell, side, account.id, binding.NOTE_BOUND.format(kind=binding.kind_name(provider)))  # 第 208 批：第三方沒有號碼可存
        return back(request, "bound")

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
        purpose = body.get("purpose")
        if purpose not in codes.PURPOSES or not isinstance(provider, str) or not oauth.ready(content, provider):
            raise HTTPException(404)
        now = shell.time.time()
        token, key = session_of(request)
        account = None
        if purpose == "login":
            if key is not None and body.get("switch") is not True:
                return {"ask": binding.SWITCH_ASK}  # 第 204 批：已登入先問一次要不要換帳號（帶 switch: true 再來一次）
        else:  # bind、reauth（第 204 批）：要登入；綁要近期驗證，單綁這個帳號
            token, account = logged_in(request)
            if purpose == "bind":
                need_recent(token, now)
                if provider in have_of(account):
                    raise shell.GameError(binding.ALREADY_KIND)
                not_reset_held(account, now)
            elif provider not in have_of(account):
                raise shell.GameError(binding.NO_SUCH_WAY)
        side = store.IdentityStore()
        if not side.count_and_record(f"oauth:{shell.client_ip(request)}", START_WINDOW, cfg.start_per_hour, now):
            raise shell.GameError(TOO_OFTEN)
        keys = oauth.secrets(provider)
        ticket = oauth.new_ticket()
        browser = _rand.token_urlsafe(32)
        side.put_ticket(_digest(ticket["state"]), provider, purpose, _digest(browser), ticket["nonce"], ticket["verifier"],
                        expires=now + cfg.ticket_seconds, now=now, account_id=account.id if account is not None else None)
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
        if ticket is None or ticket["provider"] != provider or ticket["purpose"] not in codes.PURPOSES or not browser \
                or not hmac.compare_digest(ticket["browser_hash"], _digest(browser)) or not oauth.ready(content, provider):
            return back(request, "fail")
        keys = oauth.secrets(provider)
        token = oauth.exchange(provider, q.get("code") or "", ticket["verifier"], oauth.redirect_uri(content, provider),
                               keys["client_id"], keys["client_secret"])
        sub = oauth.check(oauth.claims(token), provider, keys["client_id"], ticket["nonce"], now)
        if sub is None:
            return back(request, "fail")
        accounts = shell.account_store()
        hashed = binding.subject_hash(identity_base.read_key() or b"", provider, sub)
        if ticket["purpose"] != "login":
            return bound_back(request, ticket, provider, sub, hashed, now, side)
        key = accounts.login_key(provider, sub)
        if key is not None:
            resp = back(request, "ok")
            switch_from(request)
            shell._start_session(request, resp, key, provider)
            after_binding_login(request, resp, key, provider, now, side)
            return resp
        if binding.rebind_wait(side.unbound_elsewhere(hashed, provider, None), now, cfg):
            return back(request, "wait")  # 第 204 批：剛從別的帳號解綁的身分 30 天內不能開新帳號
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
            if why := terms_base.register_problem(shell.CONTENT, body):  # 第 206 批：terms 開著才查；拒了 pending 不丟、可以再送
                raise shell.GameError(why)
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
                terms_base.record(shell.CONTENT, key, body.get("terms_version"))  # 第 206 批：記勾過的那一版；關著不記
                secret = identity_base.read_key()
                if secret is not None:
                    hashed = identity_base.subject_hmac(secret, provider, sub) if provider in oauth.PROVIDERS else sub
                    side.record_verified(accounts.account_id(key), provider, hashed, now)
                if provider not in oauth.PROVIDERS:  # 第 209 批：驗證碼開的帳號存通知用的號碼（第三方沒有號碼；沒有金鑰不存）
                    contacts.keep(side, accounts.account_id(key), provider, side.pending_contact(_digest(token)),
                                  side.pending_display(_digest(token)))
        side.drop_pending(_digest(token))
        response.delete_cookie(PENDING_COOKIE, path=PENDING_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        shell._start_session(request, response, key, provider)  # 第 204 批：這次是用那一種登入的（session_auth）
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
        purpose = str(body.get("purpose") or codes.PURPOSE)
        if purpose not in codes.PURPOSES:
            raise HTTPException(404)
        account, subject_ok = None, None
        if purpose == "login":
            if session_of(request)[1] is not None and body.get("switch") is not True:
                return {"ask": binding.SWITCH_ASK}  # 第 204 批：已登入先問一次要不要換帳號
        else:  # bind、reauth（第 204 批）：要登入；綁要近期驗證、走 bind 池，重驗要是這個帳號綁的那一個
            token, account = logged_in(request)
            have = have_of(account)
            if purpose == "bind":
                need_recent(token, now)
                if channel in have:
                    raise shell.GameError(binding.ALREADY_KIND)
                not_reset_held(account, now)
            elif channel not in have:
                raise shell.GameError(binding.NO_SUCH_WAY)
            else:
                subject_ok = lambda subject: subject == have[channel]["subject"]  # noqa: E731
        db = open_database()
        dev = request.cookies.get(DEV_COOKIE)
        status, reply, cid = codes.send(
            cfg=shell.CONTENT.config.identity, key=key, store=store.IdentityStore(), senders=senders.pick(shell.CONTENT),
            channel=channel, to=body.get("to"), token=body.get("turnstile"), ip=shell.client_ip(request),
            hostname=request.url.hostname, dev_hash=_hash(dev) if dev else None,
            is_bound=lambda subject: identity_base.account_key_for(db, channel, subject) is not None, now=now,
            purpose=purpose, account_id=account.id if account is not None else None, subject_ok=subject_ok,
            # 第 208 批：綁定的單封號碼，綁成功才存（通知用）；第 209 批：登入用途也封，開了 session 或建了角色才存
            seal=contacts.sealer(channel) if purpose in ("bind", "login") else None,
            on_full=lambda bucket: alerts.pool_full(shell, bucket, now),  # 第 208 批：全服池滿了通知管理者（同一格一小時一次）
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
        if row["purpose"] != "login":
            response.delete_cookie(CODE_COOKIE)
            return code_bound(request, row, now, side)
        account_key = identity_base.account_key_for(open_database(), channel, subject)
        if account_key is None:
            if binding.rebind_wait(side.unbound_elsewhere(subject, channel, None), now, cfg):  # 第 204 批：30 天內不能開新帳號
                raise shell.GameError(binding.REBIND_WAIT.format(days=cfg.rebind_days))
            token = _rand.token_urlsafe(32)
            side.put_pending(_hash(token), channel, subject, expires=now + cfg.pending_seconds, now=now, display=row["display"],
                             contact=row.get("contact"))  # 第 209 批：封的號碼帶到建角色那一步才存
            _cookie(shell, request, response, PENDING_COOKIE, token, cfg.pending_seconds, path=PENDING_PATH)
            response.delete_cookie(CODE_COOKIE)
            return {"stage": "create", "pending": True}
        account = shell.account_store().get(account_key)
        response.delete_cookie(CODE_COOKIE)
        if account is not None and account.id is not None and binding.stale(side.meta(account.id).get(channel), now, cfg):
            # 門號回收（第 204 批；設計 4.4）：太久沒驗的號碼。帳號還有別種：不開 session，要那一種，給「這不是我的帳號」；
            # 只有這一種：照開，扣押 stale_hold_days。verified_at 只在開了 session 才更新（拒絕的這一下更新的話，再驗一次就過了）
            others = [k for k in have_of(account) if k != channel]
            if others:
                proof = _rand.token_urlsafe(32)
                side.put_recheck(_hash(proof), account.id, channel, subject, row["display"], now,
                                 contact=row.get("contact"))  # 第 209 批：沒開 session 不存，帶到「這不是我的帳號」
                _cookie(shell, request, response, RECHECK_COOKIE, proof, cfg.code_ttl, path=PENDING_PATH)
                return {"stale": True, "message": binding.STALE_USE_OTHER, "ways": binding.kinds_of(others)}
            side.set_hold(account.id, now + cfg.stale_hold_days * binding.DAY)
        dev = request.cookies.get(DEV_COOKIE) or ""
        if not 20 <= len(dev) <= 100:
            dev = _rand.token_urlsafe(32)
        side.trust_device(_hash(dev), subject, now)
        _cookie(shell, request, response, DEV_COOKIE, dev, DEV_SECONDS)
        switch_from(request)
        shell._start_session(request, response, account_key, channel)  # 第 204 批：這次用哪一種登入由殼記（session_auth）
        if account is not None and account.id is not None:
            side.record_verified(account.id, channel, subject, now)
            contacts.keep(side, account.id, channel, row.get("contact"), row["display"])  # 第 209 批：通知用的號碼（沒有金鑰不存）
        after_binding_login(request, response, account_key, channel, now, side)
        return shell._entry(account_key)

    def code_bound(request: Request, row: dict, now: float, side) -> dict:
        """驗證碼的綁定與重驗（第 204 批）：瀏覽器現在登入的帳號要是寄碼的那一個（不是同一句 BAD_CODE）。
        綁：已綁其他帳號、這一種綁過、30 天，驗過碼才說；成功寫 logins、bound_at、verified_at、一則紀錄。重驗：只改 session 的 verified。"""
        cfg = shell.CONTENT.config.identity
        accounts = shell.account_store()
        token, key = session_of(request)
        account = accounts.get(key) if key is not None else None
        if account is None or account.id is None or account.id != row["account_id"]:
            raise shell.GameError(codes.BAD_CODE)
        channel, subject = row["channel"], row["subject_hmac"]
        if row["purpose"] == "reauth":
            if have_of(account).get(channel, {}).get("subject") != subject or not identity_base.record_reauth(token, channel, now):
                raise shell.GameError(codes.BAD_CODE)
            side.record_verified(account.id, channel, subject, now)
            return {"message": binding.REAUTH_OK.format(minutes=max(1, cfg.recent_seconds // 60))}
        not_reset_held(account, now)  # 第 209 批：寄碼之後才被管理者重設的，驗碼這一步也擋（同寄碼那一句）
        found = accounts.login_key(channel, subject)
        if found is not None:
            raise shell.GameError(binding.ALREADY_KIND if accounts.account_id(found) == account.id else binding.BOUND_ELSEWHERE)
        if binding.rebind_wait(side.unbound_elsewhere(subject, channel, account.id), now, cfg):
            raise shell.GameError(binding.REBIND_WAIT.format(days=cfg.rebind_days))
        try:
            accounts.add_login(account.key, channel, subject, row["display"] or channel)
        except ValueError:
            raise shell.GameError(binding.ALREADY_KIND) from None
        side.mark_bound(account.id, channel, subject, now)
        contacts.keep(side, account.id, channel, row.get("contact"), row["display"])  # 第 208 批：通知用的加密號碼（沒有金鑰不存）
        note(side, account.id, binding.NOTE_BOUND.format(kind=binding.kind_name(channel)), now)
        contacts.send_all(shell, side, account.id, binding.NOTE_BOUND.format(kind=binding.kind_name(channel)))
        return {"message": binding.BOUND}

    # ── 第 204 批：設定抽屜的「帳號綁定」（全部要登入：先 401 再 gate，關著登入了也 404；不拿行動鎖）──

    def me_info(request: Request, token: str, account, now: float) -> dict:
        cfg = shell.CONTENT.config.identity
        side = store.IdentityStore()
        have = have_of(account)
        meta = side.meta(account.id)
        auth = identity_base.session_auth(token)
        last = identity_base.last_checked(auth)
        proof = request.cookies.get(RESET_COOKIE)
        reset = side.get_reset(_hash(proof)) if proof else None
        reset_left = 0
        if reset is not None and reset["account_id"] == account.id:
            reset_left = max(0, int(cfg.reset_seconds - (now - reset["at"])))
        kinds = []
        for provider in binding.kinds_of(have):
            row = meta.get(provider) or {}
            shown = have[provider]["display"] if provider != "password" else account.login
            kinds.append({"provider": provider, "name": binding.kind_name(provider), "shown": shown,
                          "bound_at": row.get("bound_at"), "verified_at": row.get("verified_at"),
                          "new": binding.is_new(row or None, now, cfg),
                          "can_unbind": provider != "password" and binding.can_remove(have, provider)})
        ways = [w for w in gate_info(shell.CONTENT)["ways"] if w not in have]
        return {"kinds": kinds, "ways": ways, "has_password": "password" in have,
                "recent": 0 if last is None else max(0, int(cfg.recent_seconds - (now - last))),
                "reset": reset_left, "hold": binding.held(side.hold_until(account.id), now),
                "turnstile": cfg.turnstile_site_key,
                # 第 208 批：⚙ 的紅點與摺疊列照它即時更新（web/identity.js identitySyncDot；同 notes.main_slot 的判斷）
                "phone_missing": bool(cfg.phone_gate) and "phone" not in have,
                **notice_info(shell.CONTENT)}  # 第 210 批：抽屜綁定那一張寄碼前的個資告知

    @r.get("/api/identity/me")
    def api_me(request: Request):
        """本人的綁定（四種＋密碼、遮好的顯示字、綁的時間、能不能解綁、近期驗證剩幾秒、忘記密碼剩幾秒）。"""
        token, account = logged_in(request)
        gate()
        return me_info(request, token, account, shell.time.time())

    @r.get("/api/identity/session")
    def api_session(request: Request):
        """第 209 批「請用密碼重新登入」：先 401 再 gate（同 /api/identity/me）。relogin 只有這個帳號在名單上（管理者、客服）而且
        這次 session 不夠格（admin_session_ok 假：驗證碼、第三方、密碼登入超過 staff_hours）才真；名單外永遠假、同一個形狀。
        只讀自己的帳號（試不出別人）；不拿行動鎖、不寫東西。"""
        token, account = logged_in(request)
        gate()
        listed = identity_base.listed(shell.CONTENT, login=account.login, character=account.character, account_id=account.id)
        return {"relogin": bool(listed and not identity_base.admin_session_ok(shell.CONTENT, token, shell.time.time))}

    @r.post("/api/identity/reauth")
    async def api_reauth(request: Request):
        logged_in(request)
        gate()
        body = await _json(request, required=False)
        return await run_in_threadpool(reauth, request, body)

    def reauth(request: Request, body: dict):
        """有密碼打密碼（authenticate：同一套擋猜，錯了算一次）；沒密碼回該用哪幾種重驗（前端走 start、code 的 purpose=reauth）。"""
        token, account = logged_in(request)
        now = shell.time.time()
        if account.hash is None:
            return {"message": binding.REAUTH_WAYS, "ways": [k for k in binding.kinds_of(have_of(account)) if k != "password"]}
        try:
            shell.account_store().authenticate(account.login, str(body.get("password") or ""))
        except shell.AccountError as exc:
            raise shell.GameError(str(exc)) from None
        identity_base.record_reauth(token, "password", now)
        return {"message": binding.REAUTH_OK.format(minutes=max(1, shell.CONTENT.config.identity.recent_seconds // 60))}

    @r.post("/api/identity/unbind")
    async def api_unbind(request: Request):
        logged_in(request)
        gate()
        body = await _json(request, required=True)
        return await run_in_threadpool(unbind, request, body)

    def unbind(request: Request, body: dict):
        """{provider}：近期驗證、不是密碼、這個帳號有、留至少一種、不在扣押、這次不是拿新綁的那一種驗的。解綁的雜湊永久留著（30 天）。"""
        token, account = logged_in(request)
        now = shell.time.time()
        provider = str(body.get("provider") or "")
        side = store.IdentityStore()
        need_recent(token, now)
        have = have_of(account)
        if provider == "password":
            raise shell.GameError(binding.KEEP_PASSWORD)
        if provider not in have:
            raise shell.GameError(binding.NO_SUCH_WAY)
        not_held(side, account, now)
        not_by_new(side, account, token, now)
        if not binding.can_remove(have, provider):
            raise shell.GameError(binding.KEEP_ONE)
        try:
            shell.account_store().remove_login(account.key, provider)
        except (ValueError, KeyError):
            raise shell.GameError(binding.KEEP_ONE) from None
        side.record_unbound(binding.subject_hash(identity_base.read_key() or b"", provider, have[provider]["subject"]),
                            provider, account.id, now)
        side.drop_meta(account.id, provider)
        gone = [c for c in side.contacts(account.id) if c["provider"] == provider]  # 第 208 批：被拿掉的那一支也寄一則，寄完不留
        side.drop_contacts(account.id, provider)
        note(side, account.id, binding.NOTE_UNBOUND.format(kind=binding.kind_name(provider)), now)
        contacts.send_all(shell, side, account.id, binding.NOTE_UNBOUND.format(kind=binding.kind_name(provider)), extra=gone)
        return {"message": binding.UNBOUND}

    @r.post("/api/identity/password/set")
    async def api_password_set(request: Request):
        logged_in(request)
        gate()
        body = await _json(request, required=True)
        return await run_in_threadpool(password_set, request, body)

    def password_set(request: Request, body: dict):
        """補設密碼 {login, new, again}（設計 4.4）：沒密碼的帳號才行；近期驗證、不在扣押、這次不是拿新綁的驗的；鍵不變（id:<n>）。"""
        token, account = logged_in(request)
        now = shell.time.time()
        side = store.IdentityStore()
        if account.hash is not None:
            raise shell.GameError(binding.HAS_PASSWORD)
        need_recent(token, now)
        not_held(side, account, now)
        not_by_new(side, account, token, now)
        new = str(body.get("new") or "")
        if new != str(body.get("again") or ""):
            raise shell.GameError(shell.PASSWORDS_DIFFER)
        try:
            strict = identity_base.on(shell.CONTENT)  # identity 開著全體 12 字（第 209 批；這條路關著 404，所以一定真）
            shell.account_store().add_password(account.key, body.get("login"), new, strict=strict)
        except shell.AccountError as exc:
            raise shell.GameError(str(exc)) from None
        except ValueError:
            raise shell.GameError(binding.HAS_PASSWORD) from None
        note(side, account.id, binding.NOTE_PASSWORD_SET.format(login=str(body.get("login") or "").strip()), now)
        contacts.send_all(shell, side, account.id, binding.NOTE_PASSWORD_SET.format(login=str(body.get("login") or "").strip()))  # 第 208 批
        return {"message": binding.PASSWORD_SET}

    @r.post("/api/identity/password/reset")
    async def api_password_reset(request: Request, response: Response):
        logged_in(request)
        gate()
        body = await _json(request, required=True)
        return await run_in_threadpool(password_reset, request, response, body)

    def password_reset(request: Request, response: Response, body: dict):
        """忘記密碼 {new, again}（設計 4.4）：tx_reset 要對得上這個帳號、reset_seconds 內；那一種綁超過 new_binding_hours；
        其他裝置登出（留這個 cookie）、寫一則紀錄。/api/password 不動。"""
        token, account = logged_in(request)
        now = shell.time.time()
        cfg = shell.CONTENT.config.identity
        side = store.IdentityStore()
        proof = request.cookies.get(RESET_COOKIE) or ""
        row = side.get_reset(_hash(proof)) if proof else None
        if row is None or row["account_id"] != account.id or now - row["at"] > cfg.reset_seconds:
            raise shell.GameError(binding.RESET_EXPIRED.format(minutes=max(1, cfg.reset_seconds // 60)))
        if binding.is_new(side.meta(account.id).get(row["provider"]), now, cfg):
            raise shell.GameError(binding.NEW_BINDING.format(hours=cfg.new_binding_hours))
        not_held(side, account, now)
        new = str(body.get("new") or "")
        if new != str(body.get("again") or ""):
            raise shell.GameError(shell.PASSWORDS_DIFFER)
        try:
            strict = identity_base.on(shell.CONTENT)  # 同補設密碼（第 209 批）
            shell.account_store().reset_password(account.key, new, keep=token, strict=strict)
        except shell.AccountError as exc:
            raise shell.GameError(str(exc)) from None
        side.drop_reset(_hash(proof))
        response.delete_cookie(RESET_COOKIE, path=PENDING_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        note(side, account.id, binding.NOTE_PASSWORD_RESET.format(kind=binding.kind_name(row["provider"])), now)
        contacts.send_all(shell, side, account.id, binding.NOTE_PASSWORD_RESET.format(kind=binding.kind_name(row["provider"])),
                          skip=(row["provider"],))  # 第 208 批：通知其他綁定（設計 4.4），登入用的那一種不寄
        return {"message": binding.PASSWORD_RESET}

    @r.post("/api/identity/code/release")
    async def api_code_release(request: Request, response: Response):
        """「這不是我的帳號」：先看 cookie（tx_recheck、tx_session 都沒帶 401，同 /api/identity/character），再 gate。"""
        if not request.cookies.get(RECHECK_COOKIE) and session_of(request)[1] is None:
            raise HTTPException(401, PLEASE_LOGIN)
        gate()
        return await run_in_threadpool(code_release, request, response)

    def code_release(request: Request, response: Response):
        """門號過期、帳號還有別種的那一下發的單：從舊帳號拿掉這支手機（或 Email）、記解綁的雜湊、舊帳號寫一則紀錄，接著寫 pending 走建角色。"""
        cfg = shell.CONTENT.config.identity
        now = shell.time.time()
        side = store.IdentityStore()
        proof = request.cookies.get(RECHECK_COOKIE) or ""
        row = side.take_recheck(_hash(proof), now, cfg.code_ttl)
        response.delete_cookie(RECHECK_COOKIE, path=PENDING_PATH, httponly=True, samesite="lax", secure=shell.cookie_secure(request))
        if row is None:
            raise shell.GameError(codes.BAD_CODE)
        accounts = shell.account_store()
        old_key = accounts.login_key(row["provider"], row["subject_hmac"])
        if old_key is not None and accounts.account_id(old_key) == row["account_id"]:
            try:
                accounts.remove_login(old_key, row["provider"])
            except (ValueError, KeyError):
                raise shell.GameError(codes.BAD_CODE) from None
            side.record_unbound(row["subject_hmac"], row["provider"], row["account_id"], now)
            side.drop_meta(row["account_id"], row["provider"])
            side.drop_contacts(row["account_id"], row["provider"])  # 第 208 批：號碼已經不是舊帳號的了，不寄
            note(side, row["account_id"], binding.NOTE_RELEASED.format(kind=binding.kind_name(row["provider"])), now)
            # 第 209 批（PM 11/09）：寄給舊帳號剩下綁著的（被拿掉那一支上面已刪，不寄）
            contacts.send_all(shell, side, row["account_id"], binding.MAIL_RELEASED.format(kind=binding.kind_name(row["provider"])))
        elif old_key is not None:
            raise shell.GameError(codes.BAD_CODE)
        token = _rand.token_urlsafe(32)
        side.put_pending(_hash(token), row["provider"], row["subject_hmac"], expires=now + cfg.pending_seconds, now=now,
                         display=row["display"], contact=row["contact"])  # 第 209 批：號碼帶到新帳號
        _cookie(shell, request, response, PENDING_COOKIE, token, cfg.pending_seconds, path=PENDING_PATH)
        return {"stage": "create", "pending": True, "message": binding.NOT_MINE_DONE}

    @r.post("/api/identity/admin/accounts")
    async def api_admin_accounts(request: Request):
        """管理頁重設密碼的搜尋（identity 開著時 web/admin.js 改打這裡）：每列多帶帳號鍵與綁定、時間。不是管理者 403。"""
        logged_in(request)
        gate()
        body = await _json(request, required=False)
        return await run_in_threadpool(admin_accounts, request, body)

    def admin_accounts(request: Request, body: dict):
        from . import admin  # noqa: PLC0415

        game = shell._game(request)
        # 第 207 批：identity 開著時名單上的人還要這次是密碼登入、staff_hours 內驗過（同殼的 /api/do 與 admin 包）
        if not game.is_admin() or not identity_base.admin_session_ok(shell.CONTENT, request.cookies.get(shell.COOKIE), shell.time.time):
            raise HTTPException(403)
        return {"rows": admin.search_rows(shell, str(body.get("q", "")))}

    return r
