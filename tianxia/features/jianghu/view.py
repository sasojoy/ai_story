"""江湖頁重排送給頁面的那一格（main.jianghu）。

第一批（骨架）只要一個「開著」的記號：頁面照它換排法，資料都是 /api/main 原本就有的（status、art、scene、options）。
之後的批真的缺欄位（例：一顆選項屬於去處、差事還是對人）才加在這裡，先回報 PM。
"""
from __future__ import annotations


def status(ctx) -> dict:
    return {"on": True}
