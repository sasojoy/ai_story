"""門派論劍的測試局面：正式內容 season21、開關打開、季自己開、出了序章、拜在白馬寺。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path


def season21_game(name: str = "陸三刀", sect: str = "baima", world=None, content=None, **tuning):
    from conftest import real_content
    from jianfa_kit import ready

    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = content
    if c is None:
        c = real_content("season21")
        c.config.auto_open_first_season = True
        c.config.train_event_chance = 0.0
        c.config.lunjian.enabled = True
        c.config.guard.enabled = False  # 親衛隊長撞見會接管選單
        c.config.yiwen.enabled = False
        c.config.difang.enabled = False
        for k, v in tuning.items():
            setattr(c.config.lunjian, k, v)
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="lunjian-")) / "tianxia.db")
    game = Game.new(c, name, rng=random.Random(0), world=world)
    game.client = None
    game = ready(game, level=20)
    game.state.player.sect = sect
    return game


def seat(name: str, sect: str, power: float, key: str | None = None):
    """另一位報了名的人（直接寫進這一週，不另開角色）。"""
    from tianxia.models import MOVES
    from tianxia.state import ArenaEntry, LunjianSeat

    kit = ArenaEntry(name=name, power=power, scores={m: power for m in MOVES}, hp_cap=power * 4)
    return LunjianSeat(key=key or name.casefold(), name=name, sect=sect, kit=kit)


def to(game, when: float):
    """把這一季的世界時間撥到 when（世界秒）。"""
    game.state.world.time = when
