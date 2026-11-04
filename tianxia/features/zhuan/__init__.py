"""列傳（功能包；開發規範手冊 3.2）：一季的終點是一篇列傳——寫傳（鎖內開單、鎖外叫模型、鎖內重驗再存的三段式）、休季三顆（用列傳插畫、
蓋紀念印、請人物親筆評曰）、行狀頁與分享。全部拆包第 29 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 zhuan:（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物 id>）。沒有假人分數（假人在休季整個不動，碰不到 zhuan:）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class ZhuanFeature(Feature):
    name = "zhuan"
    prefix = "zhuan"
    content = ("verdicts.json",)  # content.py 照舊讀（核心沒有 import 這一包）；驗證在下面的 check_content
    # 沒有認領的 PlayerState 欄位：annals、annals_mark、xingshi_seen 是行狀，核心 annals.py 管；列傳存在資料庫的 biographies 表、票在錢包裡
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def check_content(self, content, need) -> None:
        """人物評曰的固定句（content/verdicts.json：理由、長度、沒有數字；原本是 content.validate 裡的 check_verdicts）。
        錯誤的字串前綴「verdicts.json：」照舊。"""
        from tianxia.zhuan_end import check_verdicts  # noqa: PLC0415  過渡：待搬（第 3 個 Task 搬進包）

        for line in check_verdicts(content):
            need(False, f"verdicts.json：{line}")


FEATURE = ZhuanFeature()
