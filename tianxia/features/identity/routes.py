"""帳號綁定的路由（殼掛的；只在殼掛的時候才 import，engine 與假人不載入 fastapi）。帳號與客服第 201 批只有 /api/identity/gate。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tianxia.core import identity_base


def gate_info(content) -> dict:
    """登入頁要知道的：哪幾條路開著、客服信箱、Turnstile 的網站金鑰（公開的那一把）。只讀設定，跟誰來問無關。"""
    cfg = content.config.identity
    return {"ways": list(cfg.ways), "support_mail": cfg.support_mail, "turnstile": cfg.turnstile_site_key}


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/identity/gate")
    def api_gate():
        """不用登入、不拿行動鎖、不看 cookie（tests/core/shell_tables.NO_LOGIN_ROUTES 寫了理由）；關著或金鑰讀不到 404。"""
        if not identity_base.on(shell.CONTENT):
            raise HTTPException(404)
        return gate_info(shell.CONTENT)

    return r
