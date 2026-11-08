"""帳號綁定的數字（Config.identity；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。

設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md（第 2 版）。72 小時、30 天、180 天那三個數字第 204 批加（連同近期驗證、忘記密碼、客服權限的時間窗）。客服信箱第 202 批拿掉（登入頁那一行歸客服包畫）。
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
    redirect_base: str = ""  # LINE、Google 回呼網址的前半（例 https://tianxiadashi.com；第 202 批）：寫死設定值，不照請求的網域拼；空的兩家都不開
    ticket_seconds: int = 600  # 第三方登入的一次性單（state、nonce、PKCE）多久過期
    pending_seconds: int = 1800  # 第三方驗過、還沒建角色的身分留多久（建角色前不開帳號，設計 4.2）
    start_per_hour: int = 30  # 同一個來源 IP 一小時最多按幾次第三方登入
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
    # ── 綁定、解綁、補設與忘記密碼、門號回收（第 204 批；設計 4.3、4.4）──
    new_binding_hours: int = 72  # 新綁的方式這麼久內不能拿來設密碼、解綁別的方式、走忘記密碼（花元寶、贈物、上架市集的擋是第 205 批的入口）
    rebind_days: int = 30  # 解綁之後這支手機（Email、第三方帳號）這麼久內不能綁別的帳號、也不能開新帳號；原帳號重綁不受限
    fresh_days: int = 180  # Email、手機這麼久內驗過碼才算還是本人的（門號回收）；也是密碼與第三方玩家被提醒一次的間隔
    stale_hold_days: int = 7  # 只剩過期那一種登入的帳號：進得了遊戲，這麼久內不能設密碼、解綁（花元寶等是第 205 批的入口）
    recent_seconds: int = 600  # 近期驗證：登入或重驗之後這麼久內才能綁、解綁、補設密碼（設計沒寫時間窗，PM 計畫先定 10 分鐘）
    reset_seconds: int = 600  # 忘記密碼：用綁定方式登入之後這麼久內能設新密碼（tx_reset cookie 同長）
    staff_hours: int = 6  # 客服權限要這次是密碼登入，而且這麼久內登入或重驗過（設計 4.4）
    reset_hold_hours: int = 72  # 第 208 批：管理者重設密碼之後這麼久內不能花元寶、贈物、上架市集、綁定新的登入方式（設計 6.4）
