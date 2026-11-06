"""戰記（功能包；開發規範手冊 3.2）：決戰收場之後，說書人把那一場寫成一篇話本，全服一份（Joy 2026-10-29）；戰報頁的「戰記 ›」、江湖史的目錄、公開的分享頁都讀它。
全部拆包第 52 批搬進來（計畫 docs/superpowers/plans/2026-11-06-戰記包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、還留在原位的接縫。

- tale.py：備料、寫字、組篇、存放（原 tianxia/tale.py）；tale_html.py：戰記頁的標記（原根目錄 tale_html.py）。舊名都留成別名
- routes.py：/api/tale/{battle_id}、/zhanji/{code} 與 server.py 原本的戰記那一段（寫戰記的背景執行緒、封面、畫面）、決戰放手一搏補劇情的 narrate_*；殼照 FEATURES 掛

沒有選項前綴、沒有狀態鍵、沒有 PlayerState 欄位、沒有內容檔（戰記存在資料庫旁邊的小檔 <db>-tale.sqlite）；假人只會進名錄。接的掛鉤只有 routes、threads。
這個檔不在最上層 import tale：核心載入 FEATURES 時用不到它（tale.py 讀決戰的資料型別），routes、threads 都等殼叫才碰。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class TaleFeature(Feature):
    name = "tale"
    prefix = None  # 沒有選項：戰記是只讀的畫面，寫的是背景執行緒
    web: tuple[str, ...] = ()  # tale.css 不在 index.html（只有戰記頁自己連）；app.js 的戰記歸總表第 66 批
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True  # 同輿圖包：這一包沒有遊戲當下的掛鉤，沒有誰問這個（戰記沒有開關：start_tales 一定開；江湖史的目錄看殼的 TALES_IN_CHRONICLE）

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    def threads(self, shell) -> None:
        """殼開、測試停：只有 server.main 經 start_threads 叫到這裡；TALES_STOP、TALES_THREAD 留殼（tests/conftest.py 收尾認這兩個名字）。"""
        shell.start_tales(shell.CONTENT.config)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


FEATURE = TaleFeature()
