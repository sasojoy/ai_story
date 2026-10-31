"""三陣營四勝利（減法季批 3c）測試共用的建法（不改 tests/conftest.py；批 2 的 tests/jianfa_kit.py 是另一份，這裡不建同名檔）。

正式內容的 season21（豪強分屬兩軍、減法季開著、領地爭奪開著）開季就蓋章（子開關 four_wins 2026-10-31 拿掉：四勝利跟著減法季的
總開關）。每一局各載一份內容的複本，世界照 conftest 給這一個測試的 TIANXIA_DB（open_world 預設），
角色存檔與季末論功讀的是同一個資料庫。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import wins
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import Content


def wins_content(profile: str = "season21") -> Content:
    content = real_content(profile)
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    return content


def wins_game(
    content: Content | None = None, name: str = "甲客", faction: str | None = None, ally: str | None = None,
    at: str | None = None, world=None,
) -> Game:
    """開好季的一局；faction／ally 直接寫進存檔（不走投靠的確認），引導走完、體力補滿。world 給了就跟那一局同一個世界。"""
    content = content or wins_content()
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.ally = faction, ally
    p.tutorial_step = len(content.tutorial.steps)
    p.stamina = float(content.config.stamina_max)
    if at is not None:
        p.location, p.journey = at, None
        p.visited.add(at)
    return game


def save(game: Game) -> Game:
    """存進資料庫（別人的 Game、季末論功才讀得到）。"""
    CharacterStore(game.world.db).save(game.state)
    return game


def on(game: Game) -> bool:
    return wins.on(game.content, game.state.world)


def ids(game: Game) -> list[str]:
    return [o.id for o in game.options() if o.enabled]
