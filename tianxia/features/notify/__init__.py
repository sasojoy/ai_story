"""手機通知包（全部拆包第 53 批）：玩家在設定頁自己打開的手機通知——分頁關著、手機鎖著也跳得出來的來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到
（減法季整合設計第十章「回來的理由」，批 9）。包名不叫 push：tianxia/push.py 是推力規則（共用規則層）。
本包的細節與還留在殼的接縫看 README.md；計畫 docs/superpowers/plans/2026-11-06-手機通知包-第1批.md。

- notices.py：五種事（舊名 tianxia/notices.py 留成 sys.modules 別名）；純函式，只讀存檔與決戰。
- webpush.py：Web Push 的加密、VAPID 簽名、訂閱小檔 PushStore、WebPush 送出（server_push.py 的下半段搬來，舊名檔尾再匯出）。
- routes.py：看守一輪（notice_round）、開看守（start_web_push）、/api/push 五條與 /sw.js（server.py 搬來）。

沒有選項前綴、沒有 PlayerState 欄位（訂閱記在 <db>-push.sqlite 小檔，不進資料庫第 9 版）、沒有內容檔。只接 routes、threads 兩個掛鉤。
不在最上層 import webpush 與 routes：FEATURES 登記不拖進 fastapi 與 cryptography。
"""
from __future__ import annotations

from tianxia.core.features import Feature, StatusHook


class NotifyFeature(Feature):
    name = "notify"
    prefix = None  # 沒有選項：通知是設定頁與看守的事
    web = ("notify.js",)  # 設定頁的手機通知、怎麼收到那一頁、信底下問一次與訂閱（全部拆包第 66 批從 app.js 切出來）；web/sw.js 留原位不宣告（web_scripts 會把 .js 排成 script，/sw.js 由這一包的路由讀）
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True  # 沒有遊戲當下的掛鉤；開關看 Config.web_push.enabled，由 start_web_push 判斷

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def threads(self, shell) -> None:
        """看守的執行緒：殼開（server.main 經 start_threads 叫到這裡），測試不叫、自己叫 start_web_push；NOTICE_STOP、NOTICE_THREAD 留殼（tests/conftest.py 收尾認這兩個名字）。"""
        shell.start_web_push(shell.CONTENT.config)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            self._status_slots = (
                # 手機通知（減法季批 9）：設定頁畫不畫那一顆、第一次來信問不問（WEB_PUSH 是殼的 state）
                StatusHook("main", "web_push", lambda ctx, frame: {"web_push": frame.shell.WEB_PUSH is not None}),
            )
        return self._status_slots


FEATURE = NotifyFeature()
