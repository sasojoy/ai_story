"""帳號綁定的數字（Config.identity；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。

設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md（第 2 版）。72 小時、30 天、180 天那三個數字第 204 批才加。客服信箱第 202 批拿掉（登入頁那一行歸客服包畫）。
開著還要 .local/identity.json 的金鑰讀得到（core/identity_base.on）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PHONE_REQUIRED = ["raid", "wanted", "bounty_post", "gift", "spar", "discuss", "mall_buy", "looks_market", "mall_grant"]


class IdentityTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ways: list[Literal["line", "google", "email", "phone"]] = Field(default_factory=list)  # 登入頁畫哪幾條路
    redirect_base: str = ""  # LINE、Google 回呼網址的前半（例 https://tianxiadashi.com；第 202 批）：寫死設定值，不照請求的網域拼；空的兩家都不開
    ticket_seconds: int = 600  # 第三方登入的一次性單（state、nonce、PKCE）多久過期
    pending_seconds: int = 1800  # 第三方驗過、還沒建角色的身分留多久（建角色前不開帳號，設計 4.2）
    start_per_hour: int = 30  # 同一個來源 IP 一小時最多按幾次第三方登入
    turnstile_site_key: str = ""  # Cloudflare Turnstile 的網站金鑰（公開的那一把；第 203 批才用）
    phone_gate: bool = False  # 綁手機才能用的功能（設計 4.5；第 205 批才有入口）
    phone_required: list[str] = Field(default_factory=lambda: list(PHONE_REQUIRED))  # 這一批沒人讀
