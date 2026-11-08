"""帳號綁定的數字（Config.identity；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。

設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md（第 2 版）。72 小時、30 天、180 天那三個數字第 204 批才加。
開著還要 .local/identity.json 的金鑰讀得到（core/identity_base.on）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

POOL_CAPS = {"login": [400, 100], "bind": [300, 75], "anon": [200, 50]}  # 設計 4.6 PM 暫定（天、時＝四分之一）
PHONE_REQUIRED = ["raid", "wanted", "bounty_post", "gift", "spar", "discuss", "mall_buy", "looks_market", "mall_grant"]


class IdentityTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ways: list[Literal["line", "google", "email", "phone"]] = Field(default_factory=list)  # 登入頁畫哪幾條路
    support_mail: str = ""  # 登入頁「登不進去？」那一行的客服信箱；空的不畫那一行
    turnstile_site_key: str = ""  # Cloudflare Turnstile 的網站金鑰（公開的那一把；第 203 批才用）
    phone_gate: bool = False  # 綁手機才能用的功能（設計 4.5；第 205 批才有入口）
    phone_required: list[str] = Field(default_factory=lambda: list(PHONE_REQUIRED))  # 這一批沒人讀
    # ── 驗證碼（第 203 批；設計 4.2、4.6）──
    code_ttl: int = 300  # 一張驗證碼的單幾秒過期（tx_code cookie 同長）
    code_tries: int = 5  # 一張單錯幾次就作廢（算在單上，別人猜錯不廢你的單）
    resend_seconds: int = 60  # 同一個號碼（Email）多久才能再寄一次
    daily_shared: int = 5  # 每日：沒用這個身分登入過的瀏覽器共用幾次
    daily_trusted: int = 5  # 每日：曾用這個身分成功登入的瀏覽器（tx_dev）自己另有幾次
    source_hour: int = 10  # 同一個來源（IPv4；IPv6 的 /64 與 /48 各一格）一小時幾次
    sms_caps: dict[str, list[int]] = Field(default_factory=lambda: {k: list(v) for k, v in POOL_CAPS.items()})  # 全服分池上限：池 → [每天, 每小時]
    mail_caps: dict[str, list[int]] = Field(default_factory=lambda: {k: list(v) for k, v in POOL_CAPS.items()})  # Email 同樣分池（照服務商額度調）
    fake_services: bool = False  # 開發與測試用假的寄送與假的 Turnstile；正式機必須關
    turnstile_action: str = "identity_code"  # siteverify 回的 action 要等於它
    privacy_url: str = "/privacy"  # 個資告知短文連去的隱私權頁（條款包的）
