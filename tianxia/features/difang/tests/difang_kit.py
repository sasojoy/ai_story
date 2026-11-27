"""地方大事的測試局面：正式內容 season21、開關打開、季自己開、出了序章、站在潁水河畔（潁川汝南那一區）。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path


def season21_game(name: str = "陸三刀", world=None, content=None, loc: str = "yingshui", **tuning):
    from conftest import real_content
    from jianfa_kit import ready
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = content
    if c is None:
        c = real_content("season21")
        c.config.auto_open_first_season = True
        c.config.train_event_chance = 0.0
        c.config.difang.enabled = True
        c.config.guard.enabled = False  # 親衛隊長撞見會接管選單
        c.config.yiwen.enabled = False
        for k, v in tuning.items():
            setattr(c.config.difang, k, v)
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="difang-")) / "tianxia.db")
    game = Game.new(c, name, rng=random.Random(0), world=world)
    game.client = None
    return ready(game, loc=loc, level=20)


def affair_here(game):
    from tianxia.features.difang import actions

    return actions.here(game)


def open_here(game, affair_id: str = "yingshui_dike"):
    """開這一週全服那一件，換成指定的那一件（測試照潁水決堤寫；輪到哪一區照季與週的種子，這裡不管）。"""
    from tianxia.features.difang import actions, rules

    actions.on_sync(game)
    a = actions.current(game)
    d = rules.affairs()[affair_id]
    a.affair, a.region = affair_id, d["regions"][0]
    game._save_season()
    return actions.here(game)
