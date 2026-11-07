"""只留給測試的殼（第二輪第 93 批）：shopview 切成六處，這裡一個名字都不少地重新匯出，靠舊名的測試不用動。
- 核心 tianxia/core/shop_base.py：每一間店都要的（掌櫃的話、離開鈕、情況鍵、被拒那一句、素材格的排序）。
- 鐵匠鋪包 tianxia/features/smithy/shop_view.py、擂台包 tianxia/features/bout/shop_view.py、銀兩出口包 tianxia/features/outlets/shop_view.py、
  懸賞包 tianxia/features/bounties/shop_view.py、裝備包 tianxia/features/gear/shop_view.py：各間店的畫面資料。酒肆的 tavern_view 本來就在酒肆包。

沒有人換掉 shopview.* 的屬性（已掃；要 patch 打真正的位置），重新匯出打得到。產品程式不准 import 這一檔（tests/core/test_feature_boundaries.py 的 TEST_ONLY_SHELLS 守）。
"""
from __future__ import annotations

from tianxia.core.shop_base import (  # noqa: F401
    SMITH_SITUATIONS, MARKET_SITUATIONS, BOARD_SITUATIONS, DONATE_SITUATIONS, DADIAN_SITUATIONS, TAVERN_SITUATIONS, SITUATIONS, BACKS, RACK_FULL,
    problem_key, REFUSALS, _mark, hold_for, still_holds, line_text, ATTRIBUTE_ROWS, attribute_rank, TIER_NAMES,
)
from tianxia.features.smithy.shop_view import (  # noqa: F401
    FORGED_KEYS, forged_key, next_rule, rule_line, SMITH_SIGN, PAGE_NAMES, ARMOR_FORGE_NOTE, _pct, _arts, _weapon_shelf, _armor_shelf, _worn,
    _repair_use, _temper_use, _rack, _held_rows, _forge, SHORT_CELL, ONLY_ONE, GO_TEXT, smith_line, FURNACE_OP, furnace_view, DIVINE_YOU, divine_view,
    smith_view, trade_view, UP_SHORT_HAVE, UP_SHORT_DAY, UP_SHORT_SEASON, NOT_SOLD_NOTE, SELL_EMPTY, UPGRADE_HINT, UPGRADE_HINT_FOUR, UP_LEFT_DAY,
    UP_LEFT_SEASON, TRADE_HINT, SELL_ONLY_HINT, _upgrade_short, _trade_hint, _trade_captions, BLACK_MARKET, BLACK_MARKET_CAP, GLOWS, FITS, UNFITS,
    glow_of, forged_card,
)
from tianxia.features.bout.shop_view import (  # noqa: F401
    ARENA_SIGN, ARENA_LINES, YIELD_ASK, NO_ENTRY, JOIN_NOTE, NOBODY_YET, WAGES_NOTE, _fight_view, _ring_short, arena_view,
)
from tianxia.features.outlets.shop_view import (  # noqa: F401
    DONATE_SIGN, DONATE_CAP, DONATE_EMPTY, DONATE_TIER4_ONLY, DONATE_HINT, DONATE_HINT_S1, dadian_view, donate_view,
)
from tianxia.features.bounties.shop_view import (  # noqa: F401
    _HELD_HEAD, board_key, HELD_HEAD, SLOT_LEFT, HAVE_NOTE, NO_FIT, PRIZE_CHIP, PRIZE_SHORT, DROP_ASK, _headline, board_view,
)
from tianxia.features.gear.shop_view import (  # noqa: F401
    NO_HORSE, STALL_WHO, ABILITY_NAMES, FASTER, SLOWER, SAME, HUNGRY_NOTE, BUY_TEXT, FEED_TEXT, WIELD_TEXT, _coat, _bars, _speed_shown, _stall,
    market_view,
)
