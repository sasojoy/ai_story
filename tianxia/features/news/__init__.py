"""見聞（功能包；開發規範手冊 3.2）：底部分頁「見聞」那一頁的畫法（見聞改版，Joy 2026-11-08 對設計稿說「好」）。
README.md 寫這一包做什麼、導覽與設計稿。

只有畫面：沒有選項前綴、沒有狀態鍵、沒有 PlayerState 欄位、沒有內容檔、沒有開關（同戰記包：見聞頁本來就一直在）。
資料照舊是殼給的（/api/main 的 chronicle、rumor_layers、journal……，/api/reports、/api/xingshi、/api/boards）；
點擊照舊走殼 app.js 的 case "news"。這一包的 web/news.js 只放畫法的小工具（分日收合、戰報分段、三路戰況那一張），web/news.css 是它的樣子。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class NewsFeature(Feature):
    name = "news"
    prefix = None  # 沒有選項：見聞是只讀的畫面
    web = ("news.js", "news.css")  # 見聞頁的畫法小工具與樣子（手冊 G9）；css 的 link 手寫在 index.html 最後，js 手寫進 tests/kit/webharness.APP_FILES
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True  # 沒有開關：見聞頁一直都在（同戰記包）


FEATURE = NewsFeature()
