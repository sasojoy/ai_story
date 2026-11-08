"""假人看到體力玩法的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 ambush／works 那一段）。
設伏、屯糧由 take_turn 的 _stamina_play 做（護衛、犒軍、探望 aid: 同理），不交給打分數：這一包的選項假人在 score 裡一律不按。
_stamina_play、PLAY_CHANCE、PLAY_STAMINA 第二輪第 101 批從 bot_policy 搬來，舊名 re-export 同一批物件（要換機會換這裡，換 bot_policy 打不到）；take_turn 叫它的先後留在殼。**模組層不准碰 engine 與假人殼**（bot_policy 模組層 import 這個檔）。"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from tianxia import bot_base
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

# 後期體力玩法（設伏劫道、修築工事、屯糧練兵）：體力在上限的 PLAY_STAMINA 以上時，每一輪 PLAY_CHANCE 的機會挑一樣做（選單上按得下去的，
# 照名號＋這一輪的雜湊挑，不動 rng 的序列以外的東西）。內傷重的不設伏（伏兵也要打）。
PLAY_CHANCE = 0.05
PLAY_STAMINA = 0.8


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按（ambush:、works:）。"""
    return None


def _stamina_play(game: Game, rng: random.Random) -> list[str] | None:
    """體力花不完時（PLAY_STAMINA 以上）PLAY_CHANCE 的機會設伏、修工事、屯糧、護衛、犒軍或探望（選單上按得下去的那幾顆挑一顆）；這一輪不做是 None。
    體力不夠、選單上沒有這幾顆時不擲骰。"""
    p = game.state.player
    if p.stamina < game.content.config.stamina_max * PLAY_STAMINA:
        return None
    plays = [o.id for o in game.options(odds=False, tick=False) if o.enabled and o.id.startswith(("ambush:set:", "works:", "aid:"))]
    if bot_base._crippled(game):
        plays = [i for i in plays if not i.startswith("ambush:")]
    if not plays or rng.random() >= PLAY_CHANCE:
        return None
    return game.choose(rng.choice(plays))
