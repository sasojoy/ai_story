"""城裡操練與城外練功分級（新手引導重做，Joy 2026-10-22 同意設計稿 https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx；Config.training）。

一類一顆（precise.on）開著、Config.training.enabled 也開著才有：
- 城鎮裡行動列那一格是「操練」（act:drill）：零風險、一天 drill_per_day 次（同回體丹的現實 00:00 換日，Game._pill_day）、
  主要給心得（基數＋等級），經驗很少（基數＋等級÷5）。不打仗、不扣氣血、不掉東西。
- 城外那一格是「尋敵」（explore:practice，Game._practice_option；以前叫練功，Joy 2026-10-22 改名）：照這裡最弱的對手分一、二、三級，
  打贏的心得與銀兩乘級數的倍數，經驗不加成。玩家看不到「幾級」：每一級寫成一句江湖話（TIER_WORDS），寫在那一格與輿圖的地點詳情（PLACE_LINE）。
這裡放不看引擎的純規則（字、數字、次數），engine.Game 接線。"""
from __future__ import annotations

from . import explore_modes, precise
from .models import Content, Location, Training
from .state import PlayerState, WorldState

DRILL_ID = "act:drill"
DRILL = "操練"  # 待 joy 潤
PRACTICE = explore_modes.NAMES[explore_modes.PRACTICE]
# 一、二、三級的江湖話（Joy 2026-10-22：不寫「幾級練功點」，移動清單也不寫）：尋敵那一格的小字（五格時最多四個字）、鈕上、輿圖的地點詳情。待 joy 潤
TIER_WORDS = ("宵小出沒", "匪寇橫行", "兇徒盤據")
PLACE_LINE = "此地{tier}。"  # 輿圖地點詳情最後那一句（Game.place_detail）
DRILL_LEFT = "今日還能 {n} 次"  # 鈕上：同出陣的「今日還能 N 次」（網頁照同一個樣子切成格子的小字）
DRILL_FULL = "今日已練滿"  # 鈕上：用完了（網頁格子寫「今日已滿」）
NEAREST = "，最近能尋敵的地方在{place}（{tier}）"  # 接在 DRILL_FULL 後面
DRILL_LINES = (  # 操練那一句：照今天第幾次輪著說（不擲骰）。待 joy 潤
    "你在校場跟教頭過了幾招，他拿木棍在你肩上點了點：「沉肩，再來。」",
    "校場邊的木樁被你打得砰砰響，一旁看熱鬧的孩子跟著拍手。",
    "教頭讓你跟幾個新募的鄉勇對練，你一招一式慢慢拆，越打越順手。",
    "你蹲了半個時辰的馬步，又把今天練的招從頭走了一遍。",
    "教頭看了你兩趟拳，指出一處破綻：「這裡慢了半拍。」你記下了。",
)
TAG = "校場過招"  # 江湖紀錄標題後面那一格（「操練・潁川郡　校場過招」）。待 joy 潤
DONE_TODAY = "教頭擺擺手：「今天就到這裡。要再練，出城找真對手去。」"  # 用完了還按到（舊分頁）


def on(content: Content, world: WorldState | None) -> bool:
    return content.config.training.enabled and precise.on(content, world)


def tier_of(cfg: Training, difficulty: float) -> int:
    """最弱的對手難度 → 第幾級（0、1、2）。"""
    low, mid = cfg.tier_bounds
    return 0 if difficulty <= low else 1 if difficulty <= mid else 2


def loot_scale(cfg: Training, tier: int) -> float:
    return cfg.tier_loot[tier]


def drills_left(p: PlayerState, cfg: Training, today: int) -> int:
    return max(0, cfg.drill_per_day - (p.drills_today if p.drill_day == today else 0))


def spend(p: PlayerState, today: int) -> None:
    p.drills_today = (p.drills_today if p.drill_day == today else 0) + 1
    p.drill_day = today


def gains(cfg: Training, level: int) -> tuple[int, int]:
    """操練一次給的（心得，經驗）。"""
    return round(cfg.drill_xinde_base + level * cfg.drill_xinde_per_level), cfg.drill_exp_base + level // cfg.drill_exp_level_div


def line(p: PlayerState) -> str:
    return DRILL_LINES[(p.drills_today - 1) % len(DRILL_LINES)]


def is_town(content: Content, loc: Location) -> bool:
    return explore_modes.is_town(content, loc)
