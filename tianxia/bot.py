"""亂數機器人：隨機選擇可用選項玩完一整季，並把心得花在武學上。用於整季測試與平衡模擬。"""
from __future__ import annotations

import random

from . import team
from .engine import Game
from .models import Content

HALF_HOUR = 1800


def spend_xinde(game: Game) -> None:
    """貪心花心得：只要付得起，就把目前最便宜的一門升一成（同價時取排在前面的）。"""
    state, content = game.state, game.content
    while True:
        costs = []
        for _, target in game.upgrade_options():
            level = team.target_level(state, content, target)
            if level is not None and level < team.MAX_SKILL_LEVEL:
                costs.append((team.upgrade_cost(content, level), target))
        if not costs:
            return
        cost, target = min(costs, key=lambda c: c[0])
        if state.player.stats.get("xinde", 0) < cost:
            return
        game.upgrade(target)


def play_season(content: Content, seed: int, max_steps: int = 20000) -> Game:
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed))
    rng = random.Random(seed)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options() if o.enabled]
        if options:
            game.choose(rng.choice(options).id)
            spend_xinde(game)
        if not options or step % 4 == 0:
            game.advance(HALF_HOUR)
    return game
