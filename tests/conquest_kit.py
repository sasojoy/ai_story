"""領地爭奪（第 38 項改版）測試共用的建法（計畫的 Global Constraints：不改 tests/conftest.py，共用的放這裡）。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path
from unittest import mock

from conftest import real_content
from tianxia import team, territory
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Content
from tianxia.sqlite_world import open_world


def conquest_rules(content: Content) -> Content:
    """打開領地爭奪（Config.conquest.enabled），回傳同一份內容。"""
    content.config.conquest.enabled = True
    return content


def _new(content: Content, name: str, world=None) -> Game:
    """world 沒給：每一局自己一個資料庫檔（同一條測試建兩局時，第二局不會讀到第一局種下、蓋了別的章的季）。"""
    content.config.auto_open_first_season = True
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="conquest-")) / "tianxia.db")
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    territory.update(game.state.world, content)  # 開季那一下：第一次算，不發天下大事
    return game


def conquest_game(profile: str = "season21", name: str = "沈浪", world=None) -> Game:
    """正式內容、開季時就打開領地爭奪的一局（同 test_territory._game 的建法）。"""
    return _new(conquest_rules(real_content(profile)), name, world)


def plain_game(profile: str = "weekend", name: str = "沈浪", world=None) -> Game:
    """同上，領地爭奪關著（正式內容的預設）。"""
    return _new(real_content(profile), name, world)


def join(game: Game, side: str | None) -> Game:
    """直接把陣營寫進存檔（不走投靠的確認），引導走完、體力補滿：完成步驟的獎勵與序章不混進出陣的帳。"""
    p, c = game.state.player, game.content
    p.faction = side
    p.tutorial_step = len(c.tutorial.steps)
    p.stamina = float(c.config.stamina_max)
    return game


def go(game: Game, loc_id: str) -> Game:
    p = game.state.player
    p.location, p.journey = loc_id, None
    p.visited.add(loc_id)
    return game


def fight(tier: str = "大勝"):
    """單次判定照給的結果（同 test_sortie._fight）。"""
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def win_sortie(game: Game) -> list[str]:
    """在所在地出陣攻、打贏一場（固定結果）。"""
    with fight():
        return game.choose("act:train")


def contribution(game: Game) -> int:
    """本季的貢獻（push.add_contribution 寫進的那一份）。"""
    return game.state.player.contrib
