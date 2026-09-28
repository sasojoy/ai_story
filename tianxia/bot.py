"""亂數機器人：隨機選擇可用選項玩完一整季。用於整季測試與平衡模擬。"""
from __future__ import annotations

import random

from .engine import Game
from .models import Content

HALF_HOUR = 1800


def play_season(content: Content, seed: int, max_steps: int = 20000) -> Game:
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed))
    rng = random.Random(seed)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options() if o.enabled]
        if options:
            game.choose(rng.choice(options).id)
        if not options or step % 4 == 0:
            game.advance(HALF_HOUR)
    return game
