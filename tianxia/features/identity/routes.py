"""帳號綁定的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。
第 201 批 /api/identity/gate；第 203 批驗證碼登入兩條：POST /api/identity/code/send、/api/identity/code/verify（不用登入，
tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由）。現在時間在這裡讀（time.time()）、傳進 codes；寄送與 Turnstile 是網路呼叫，不拿行動鎖。
殼的東西照 shell.<名字> 當下讀：_start_session、_entry、client_ip、COOKIE、cookie_secure、GameError、CONTENT（不改 server.py）。"""
from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import APIRouter, Body, HTTPException, Request, Response

from tianxia.accounts import _token_hash
from tianxia.core import identity_base
from tianxia.database import open_database

from . import codes, senders, store

CODE_COOKIE = "tx_code"  # 這張驗證碼的單（challenge id）；max_age＝code_ttl
DEV_COOKIE = "tx_dev"  # 曾用這個身分成功登入的瀏覽器（只存 sha256）；成功登入才發
PENDING_COOKIE = "tx_pending"  # 驗過、查無帳號的身分（第 202 批的建角色流程讀）
DEV_SECONDS = 365 * 86400
PENDING_SECONDS = 600


def gate_info(content) -> dict:
    """登入頁要知道的：哪幾條路開著、客服信箱、Turnstile 的網站金鑰（公開的那一把）。只讀設定，跟誰來問無關。"""
    cfg = content.config.identity
    return {"ways": list(cfg.ways), "support_mail": cfg.support_mail, "turnstile": cfg.turnstile_site_key}


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


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def _cookie(shell, request: Request, response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(name, value, httponly=True, samesite="lax", max_age=max_age, secure=shell.cookie_secure(request))


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

    @r.get("/api/identity/gate")
    def api_gate():
        """不用登入、不拿行動鎖、不看 cookie（tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由）；關著或金鑰讀不到 404。"""
        if not identity_base.on(shell.CONTENT):
            raise HTTPException(404)
        return gate_info(shell.CONTENT)

    @r.post("/api/identity/code/send")
    def api_code_send(request: Request, response: Response, body: dict = Body(default={})):
        """{channel: "phone"/"email", to, turnstile}。寄出與額度滿了回同一份 {message, notice, privacy}（不透露有沒有帳號）；
        寄出才設 tx_code。打錯的、沒過 Turnstile、寄送服務壞了回各自那一句（400）。"""
        channel = str(body.get("channel") or "")
        key = _code_gate(shell, channel)
        now = time.time()
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
    def api_code_verify(request: Request, response: Response, body: dict = Body(default={})):
        """{code}；單從 tx_code 取。沒單、過期、錯碼回 BAD_CODE（錯碼算在單上）。對了：有帳號就開 session、記這次用哪一種登入、
        回 _entry；查無帳號只寫待處理（建角色之前不開帳號，設計 4.2）、設 tx_pending、回 {stage: create, pending: true}。"""
        key = _code_gate(shell)
        cfg = shell.CONTENT.config.identity
        side = store.IdentityStore()
        cid = request.cookies.get(CODE_COOKIE)
        peek = side.challenge(cid) if cid else None
        if peek is not None and peek.get("channel") and peek["channel"] not in cfg.ways:
            raise HTTPException(404)  # 這條路被拿掉了：同關著
        now = time.time()
        row = codes.verify(cfg=cfg, key=key, store=side, cid=cid, code=body.get("code"), now=now)
        if row is None:
            raise shell.GameError(codes.BAD_CODE)
        channel, subject = row["channel"], row["subject_hmac"]
        account_key = identity_base.account_key_for(open_database(), channel, subject)
        if account_key is None:
            token = secrets.token_urlsafe(32)
            side.put_pending(_hash(token), channel, subject, row["display"], now + PENDING_SECONDS)
            _cookie(shell, request, response, PENDING_COOKIE, token, PENDING_SECONDS)
            response.delete_cookie(CODE_COOKIE)
            return {"stage": "create", "pending": True}
        dev = request.cookies.get(DEV_COOKIE) or ""
        if not 20 <= len(dev) <= 100:
            dev = secrets.token_urlsafe(32)
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
