"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。"""
from __future__ import annotations

from . import view

def _codex_full(ctx) -> list[str]:  # 小 def：測試換掉 view.full_pages 要晚綁定
    return view.full_pages(ctx)


TABLE = {
    "_codex_full": _codex_full,  # 查詢服務（主人 codex）：圖鑑收滿了哪幾頁；稱號包問「收滿給頭銜」
}
