"""帳號綁定（功能包；開發規範手冊 3.2；帳號與客服第 201 批起）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- store.py：旁檔 <db>-identity.sqlite（驗證紀錄、解綁留的雜湊、驗證碼、限制計數、這次登入的方式；第 202 批加一次性單與還沒開帳號的身分；
  第 203 批加信任的瀏覽器，驗證碼查無帳號也寫同一張 pending）。
- oauth.py：LINE、Google 的設定表、PKCE、換 token、驗 id_token 的欄位（第 202 批；HTTP 可換、不讀時鐘）。
- routes.py：/api/identity/gate（登入頁問哪幾條路開著）、/api/identity/start、/auth/{provider}/callback（不用登入）、/api/identity/character（先看 cookie）；
  第 203 批 /api/identity/code/send、/api/identity/code/verify（驗證碼登入，不用登入）；關著都 404。
- codes.py（第 203 批）：驗證碼的純規則（分格、分池、產碼與 HMAC、寄與驗、玩家看的字）；senders.py：寄送與 Turnstile 的介面與假的實作。
- 純規則與 phone_ok 在核心 tianxia/core/identity_base.py；沒有密碼的帳號在核心 tianxia/accounts.py。
沒有選項前綴、沒有 PlayerState 欄位、沒有內容檔。開關 Config.identity.enabled（預設關），開著還要讀得到 .local/identity.json 的金鑰。
不在最上層 import routes：FEATURES 登記不拖進 fastapi。新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core import identity_base
from tianxia.core.features import Feature, StatusHook

# 主機看的字（不是玩家看的）：fake_services 是開發與測試用的假寄送與假 Turnstile
FAKE_WARNING = "警告：identity.fake_services 開著（假的簡訊、Email 與 Turnstile），正式機必須關。"
FAKE_REFUSED = "identity.fake_services 只給開發與測試用：正式設定（season_one 開著）不准開"


class IdentityFeature(Feature):
    name = "identity"
    prefix = None  # 沒有選項：登入頁的格與 /api/identity/*
    web = ("identity.js", "identity.css")  # 登入頁的格（registerGateSlot）；css 的 link 手寫在 index.html 最後一行 link 之後
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return identity_base.on(ctx.content)  # Config.identity.enabled 加上金鑰讀得到

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def on_own_turn(self, ctx) -> None:
        """本人這一輪（第 204 批）：「帳號」紀錄寫進存檔（兩段式）與 180 天提醒。假人第一行就跳過（假人沒有帳號、不開旁檔），再看開關。"""
        if ctx.state.player.bot is not None:
            return
        if not identity_base.on(ctx.content):
            return
        from . import notes  # noqa: PLC0415

        notes.journal_notes(ctx)

    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """main 表的表外格（第 204 批）：關著、沒有帳號回 {}；開著回本人的 identity 格（設定抽屜的「帳號綁定」與紅點）。"""
        if self._status_slots is None:
            from . import notes  # noqa: PLC0415

            self._status_slots = (StatusHook("main", "identity", lambda ctx, frame: notes.main_slot(ctx)),)
        return self._status_slots

    def admin_tools(self, shell) -> dict:
        """管理者工具（第 204 批；設計 6.5）：identity_unbind、identity_delete、identity_view。關著 gate 404。"""
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.admin_tools(shell)

    def threads(self, shell) -> None:
        """不開執行緒：伺服器啟動時（start_threads 只在 server.main 叫）fake_services 開著印一行警告給主機看（第 204 批，K 波審查）。"""
        if shell.CONTENT.config.identity.fake_services:
            print(FAKE_WARNING, flush=True)

    def check_content(self, content, need) -> None:
        """正式設定（season21、week7 都開 season_one）不准開 fake_services：載入就擋（第 204 批，K 波審查）。"""
        cfg = content.config
        need(not (cfg.identity.fake_services and cfg.season_one), FAKE_REFUSED)


FEATURE = IdentityFeature()
