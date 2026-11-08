"""假人的每日簽到（第二輪第 101 批從 bot.py 搬來，bot 留 re-export 同一個函式）。沒有掛鉤：整季機器人（bot.play_season）與伺服器假人（bot_policy.look_after）經舊名叫。
**模組層不准碰 engine 與假人殼**（bot 模組層 import 這個檔）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import checkin

if TYPE_CHECKING:
    from tianxia.engine import Game


def check_in(game: Game) -> None:
    """每日簽到（21 天季，正式季整合 8.1）：今天還沒簽就簽，四階的日子照名號＋季數的種子挑屬性（checkin.bot_attribute）。只走
    Game.check_in（真人按「簽到」小標的同一條路）；畫面沒有簽到（關著、序章裡、休季）或今天簽過了都不叫。整季機器人與伺服器假人共用。"""
    view = game.checkin_view()
    if view is None or view["done"]:
        return
    p = game.state.player
    game.check_in(checkin.bot_attribute(game.content, p.name, p.season_number) if view["pick"] else "")
