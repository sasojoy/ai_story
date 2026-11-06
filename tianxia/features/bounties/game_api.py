"""Game 上掛的名字 → 這一包的函式（第二輪第 72 批；engine.py 檔尾 features_core.attach_game_api 掛一次）。
`g.xxx` 照舊叫得到；要改就改本體，這裡沒有邏輯。小 def 是不能直接掛的（不傳 self，或測試換掉包的函式要晚綁定）。"""
from __future__ import annotations

from . import actions


TABLE = {
    # ── 懸賞榜：本體在 tianxia/features/bounties/（全部拆包第 45 批），這裡留一行委派 ─────
    "_bounty": actions.bounty,
    "_bounty_stale": actions.stale,
    "_raid_bounty": actions.raid_bounty,
}
