"""只留給測試的殼（第二輪第 88 批）：skillview 切成三處，這裡一個名字都不少地重新匯出，靠舊名的測試不用動。
- 共用層 tianxia/art_cards.py：別的地方也讀的卡片。
- 煉製包 tianxia/features/craft/forge_view.py：煉製頁的預覽與提示。
- 修練包 tianxia/features/cultivation/art_view.py：修練頁的說明與功法列。

沒有人換掉 skillview.* 的屬性（已掃；要 patch 打真正的位置），重新匯出打得到。產品程式不准 import 這一檔（tests/core/test_feature_boundaries.py 的 TEST_ONLY_SHELLS 守）。
"""
from __future__ import annotations

from tianxia.art_cards import (  # noqa: F401
    STAT_USES, STAT_CHECK_NOTE, tactic_line, RIPE_MOVE, RIPE_NOTE, fifth_ring, stat_uses, _milestones, _signed_pct, STAT_NOW, _stat_numbers,
    stat_lines, practice_hint, fx_traits, heal_note, heal_button, shown_art, shown_gear, HIGH_MORE, HIGH_LONGER, _stack_scope, _stack_cells,
    _high_word, slot_stack_marks, slot_rows, _look, SCORE_NOTE, score_note, level_bar, gear_rows, gen_word, parent_names, power_line, POWER_NEXT,
    POWER_NEXT_IS_TOP, POWER_MAXED, art_card,
)
from tianxia.features.craft.forge_view import (  # noqa: F401
    _known_insight_recipe, AGAIN_PIECE, _strip_note, FORGE_ONE_INSIGHT, FORGE_EMPTY, forge_line, forge_preview, FIRES, FIRE_CUTS, fire_of,
    DEEPEN_KEEP, _deepen_preview, _compound_grand, _no, forge_picks,
)
from tianxia.features.cultivation.art_view import (  # noqa: F401
    STAT_STEP, stat_step, rules_line, ARTS_ATTRIBUTES, ATTRIBUTE_ORDER, attribute_line, _nearest_town, relearn_note, art_rows, melt_judge, STACK_RULE,
    TOPPED, stack_hint, stack_parts, _force_choice, _fits, insight_effects, insight_rows, insight_note, _idle_why, _slotted_name, bag_text,
    _art_label, member_card, _art_cell, roster_cards, _pct, boost_line, _echo_part, detail,
)
