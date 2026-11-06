"""玩法說明（explain-1，試玩回饋：Gary「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）：

- 江湖頁行動列底下那幾行：探索、遊歷、交友這一下會怎樣（explore_line、train_line、social_line）；
- 狀態列體力條點開的說明（stamina_lines）與建角色時送回體丹的那一行（gift_line）；
- 江湖頁的戰況圖卡、態勢、大事、主線點開的說明（war_help，explain-2：這一季在打什麼、亂局、大事怎麼定、你能怎麼出力）；
- 設定抽屜的「玩法說明」（page，Markdown）。

這裡只把事實寫成字：比重、獎勵、推不推戰局由呼叫端照引擎真正的規則算好傳進來（Game._explore_weights、遊歷的對手、
Game.train_trend_push），數字一律讀 Config（或內容、規則模組的常數），句子裡不寫死任何數。不改狀態、不擲骰、不讀時鐘。
所有句子待 joy 潤。

過渡（全部拆包第 59 批「引導二」；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md 第四節）：本體拆進 17 包各自的 howto.py，順序在核心的 HOWTO_ORDER。
這裡留成重新匯出的殼，舊的頂層名字一個都不少（二十幾個測試檔照舊 `howto.X`）：內容在好幾包，sys.modules 別名只能指一包，包又不准 import 包。
沒有產品程式 import 這個檔；測試改完就拿掉（第 61 批之後）。沒有人換掉 howto.* 的屬性（已掃），重新匯出打得到。"""
from __future__ import annotations

from tianxia.core.howto_base import SOME_PLACES  # noqa: F401
from tianxia.core.howto_base import order_pushers as _order_pushers  # noqa: F401
from tianxia.core.howto_base import section as _section  # noqa: F401
from tianxia.core.howto_base import tenth as _tenth  # noqa: F401
from tianxia.features.guide.howto import (  # noqa: F401
    _clock, _span, regen_line, newbie_line, pill_line, stamina_lines, gift_line, top_up_line, _count, _band, _tenths, season_line, front_rule,
    ALLIED_RULE, allied_rule, stance_help, SORTIE_RANGER, CONQUEST_PLACES, CONQUEST_FRONTS, _sortie_places, _pct, jianfa_growth_lines, fronts_help,
    _lockable, board_help, quest_help, war_help, FameRange, _effects, fame_ranges, _plus, fame_lines, _fame_sources, _fame_uses, RENOWN_INTRO,
    RENOWN_FAME, RENOWN_VIRTUE, RENOWN_DEEDS, RENOWN_TOP, RENOWN_VIRTUE_FROM, RENOWN_RESONANCE, RENOWN_PRACTICE, renown_lines, season_page_lines,
    page,
)
from tianxia.features.explore.howto import (  # noqa: F401
    BRANCH_WORDS, explore_line, OUTING_WORDS, OUTING_HEAD, OUTING_FOE, OUTING_BOUNTY, outing_line, outing_lines, _kind_name, mix_sentence,
)
from tianxia.features.sortie.howto import (  # noqa: F401
    PUSH_WORD, train_line, SORTIE_NOTES, SORTIE_LOOT, SORTIE_LOOT_SILVER, SORTIE_PROGRESS, SORTIE_HOLD_PROGRESS, SORTIE_BLOCKED, SORTIE_BLOCKED_HOLD,
    SORTIE_LEFT, sortie_line, sortie_loot, DUEL_NOTES, DUEL_LEFT, duel_line, duel_lines, sortie_lines,
)
from tianxia.features.socialize.howto import (  # noqa: F401
    SEEK_NAME, social_line, CALL_LINE, call_line, day_every,
)
from tianxia.features.stamina_plays.howto import (  # noqa: F401
    ambush_lines,
)
from tianxia.features.faction.howto import (  # noqa: F401
    CONQUEST_JOIN, CONQUEST_JOIN_DUEL, _place_names, join_lines, faction_lines,
)
from tianxia.features.territory_acts.howto import (  # noqa: F401
    conquest_lines, territory_lines,
)
from tianxia.features.figure_acts.howto import (  # noqa: F401
    CHALLENGE_UNTIMED, CHALLENGE_SEASON21_REGEN, CHALLENGE_TITLE, CHALLENGE_WHO, CHALLENGE_BOTH, CHALLENGE_SNUB, CHALLENGE_RISE, CHALLENGE_DRAW,
    _challenge_lines,
)
from tianxia.features.cultivation.howto import (  # noqa: F401
    pages_lines,
)
from tianxia.features.smithy.howto import (  # noqa: F401
    forge_lines,
)
from tianxia.features.sense.howto import (  # noqa: F401
    STRONG_HOWTO, TERRAIN_HOWTO,
)
from tianxia.features.outlets.howto import (  # noqa: F401
    ECONOMY_TITLE, economy_lines,
)
from tianxia.features.mall.howto import (  # noqa: F401
    MALL_TITLE, MALL_WHERE, MALL_COIN, MALL_BETA, MALL_CARD, mall_lines,
)
