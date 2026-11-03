"""新手引導（功能包；開發規範手冊 3.2）：草廬之後的引導框、碰到才說的提示、新手目標、開局第一分鐘、入伍段。全部拆包第 22 批（引導一）
搬進來；玩法說明（howto）是第 59 批（引導二）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- checks.py：內容檢查（碰到才說那一塊，原本在 content.validate）

這一包沒有選項前綴：它的動作走 server 的 MAIN_ACTIONS（hints_off、skip_tutorial、view_map、view_orders、view_tab、guide_ack、
newbie_drifter）與 /api/prologue，選單上的那幾顆是別人的（act:rest 是核心 act: 的子動詞、開局三選一是事件的 choice:、投靠是 faction:）。
所以 options、menu、choose、bot_pick 都是預設的；enabled 一直是 True（引導、提示、新手目標、開局各有自己的開關，包本身沒有總開關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class GuideFeature(Feature):
    name = "guide"
    prefix = None  # 沒有自己的選項（見模組說明）
    content = ("tutorial.json", "hints.json", "opening.json")  # content.py 照舊讀（第 62 批起照它載）；檔名照舊

    def enabled(self, ctx) -> bool:
        return True

    def check_content(self, content, need) -> None:
        """碰到才說（hints.json）的檢查：原本在 content.validate 裡、句子照抄（核心的 content.py 不能 import 包）。"""
        from . import checks  # noqa: PLC0415

        checks.check_hints(content, need)


FEATURE = GuideFeature()
