"""假人看到移動的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 move: 那一段，全部拆包第 47 批）。
road:（折返、路上小事）假人不按：score 沒有這一支，落到最後回 None，這裡一樣。

move: 那一段要 profile（BotProfile）與 bot_policy 的七個私有函式、七個分數常數，都還在舊模組裡（待搬；假人的線），所以經 `from tianxia import bot_policy`
延後 import（舊模組 import engine，包不能在模組載入時 import 它）；分數常數照模組屬性讀，測試換掉也生效。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core.option import Option
from tianxia.state import BotProfile

if TYPE_CHECKING:
    from tianxia.engine import Game


def score(game: Game, option: Option, profile: BotProfile) -> float | None:
    """選項的分數；None＝假人不會按（road:）。move: 是往哪裡走：往自己陣營的地盤、軍令、召見、懸賞、醫館、領地爭奪要去的地方加分。"""
    from tianxia import bot, bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    kind, _, arg = option.id.partition(":")
    if kind != "move":
        return None
    base = bp.HOME_MOVE_SCORE if arg == bp._front_hop(game, profile) or arg in bp._home(game, profile) else bp.AWAY_MOVE_SCORE
    order_hop = bp.ORDER_MOVE_SCORE if arg.partition(":")[0] == bp._order_hop(game) else 0.0  # 往軍令要去的地方（計畫 T6）
    summons_hop = bp.SUMMONS_MOVE_SCORE if arg.partition(":")[0] == bp._summons_hop(game) else 0.0  # 往召見的地點（計畫 T5）
    bounty_hop = bp.BOUNTY_MOVE_SCORE if arg.partition(":")[0] == bp._bounty_hop(game) else 0.0  # 往懸賞要去的地方
    clinic_hop = bp._clinic_score(game) if arg.partition(":")[0] == bot.clinic_hop(game) else 0.0  # 內傷重了往醫館
    focus_hop = bp.FOCUS_MOVE_SCORE if arg.partition(":")[0] == bp._focus_hop(game) else 0.0  # 領地爭奪：往這一邊最該推的那一塊
    return base + order_hop + summons_hop + bounty_hop + clinic_hop + focus_hop \
        + (bp.TRAIN_MOVE_SCORE if bp._train_value(game, profile, arg) > 0 else 0.0)
