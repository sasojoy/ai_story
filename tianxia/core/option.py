"""選單上的一顆（原本寫在 engine.py；功能包要做選項、又不能 import engine，搬進核心。`from tianxia.engine import Option` 照舊拿得到）。"""
from __future__ import annotations

from pydantic import BaseModel, model_serializer

# 閒著的選單（在地點上、沒有事件、對話、路上、閉關、開打的決戰）一定有這一顆，拿它認「此刻閒著」（切磋、論武、假人答論武、走一趟）。
# 以前認「打坐」（永遠按得下去），打坐 2026-10-12 拿掉之後改認探索：_everyday_options 第一顆，體力不夠也在（灰的）。
# 原本寫在 engine.py；走一趟搬進探索包（主動搬六包第 3＋4 批）要認它、又不能 import engine，搬進核心（`engine.IDLE_MARK` 照舊叫得到）
IDLE_MARK = "act:explore"


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True
    wait: str = ""  # 按下去要等模型時，按鈕上換上的字（大場面「兩人對峙……」，武學與成長設計 8.3）；不必等是空的
    confirm: str = ""  # 按下去之前先問一次的話（FB-095：必敗的遊歷）；網頁照它跳確認層，空的直接送
    confirm_yes: str = ""  # 確認層上「做」那一顆寫什麼；空的照舊寫「照打」（FB-125：拆解寫「拆掉」）
    tag: str = ""  # 名聲 5B：俠寇選項的「俠」「寇」（網頁畫在編號那一格）；空的照舊寫編號
    note: str = ""  # 名聲 5B：標籤底下第二行小字（俠寇選項寫為什麼合你的路數）；空的不畫
    # 減法季批 4（主機側計畫 1.3 欄位表 options[].outcomes）：分岔開著時「隨口應對」那一顆的可能走向 [{id, tag}]（outcomes.tags，不給數字）；
    # 其餘是 None，不寫進 model_dump（關著的季選單一個鍵都不多）
    outcomes: list[dict[str, str]] | None = None

    @model_serializer(mode="wrap")
    def _drop_no_outcomes(self, handler):
        data = handler(self)
        if isinstance(data, dict) and data.get("outcomes") is None:
            data.pop("outcomes", None)
        return data
