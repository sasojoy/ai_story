"""減法季（Config.jianfa；減法季整合設計第十二章）測試共用的建法（主機側計畫 Global Constraints：不改 tests/conftest.py，共用的放這裡）。

正式內容的 season21、week7 打開 Config.jianfa（新開的季蓋章），週末設定與不帶設定的內容關著，測試內容（fixture）也關著。
- 新規則的測試：`jianfa_game(...)`（正式內容、開季就蓋章；子開關照 flags 開關，例 `jianfa_game(explore_one=False)`）。
- 用正式內容測舊規則、或拿來跟改版之前比的：`plain_game(...)`（同一份設定，jianfa 關著），或在自己的 helper 裡叫 `no_jianfa(content)`。
"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path

from conftest import real_content
from tianxia.engine import Game
from tianxia.models import Content
from tianxia.sqlite_world import open_world


def jianfa_rules(content: Content, **flags: bool) -> Content:
    """打開減法季（Config.jianfa.enabled），flags 是子開關（JianfaRules 的欄位，例 explore_one=False）；回傳同一份內容。
    寫錯子開關的名字直接丟 AttributeError（不讓測試靜靜照預設跑）。"""
    cfg = content.config.jianfa
    cfg.enabled = True
    for part, on in flags.items():
        if not hasattr(cfg, part):
            raise AttributeError(f"JianfaRules 沒有子開關 {part}")
        setattr(cfg, part, on)
    return content


def no_jianfa(content: Content) -> Content:
    """減法季之前的規則（Config.jianfa 關著）：正式內容的 season21、week7 是開的，測舊規則的測試在 helper 裡叫它；回傳同一份內容。"""
    content.config.jianfa.enabled = False
    return content


def _new(content: Content, name: str, world=None) -> Game:
    """world 沒給：每一局自己一個資料庫檔（同一條測試建兩局時，第二局不會讀到第一局種下、蓋了別的章的季）。"""
    content.config.auto_open_first_season = True
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="jianfa-")) / "tianxia.db")
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    return game


def jianfa_game(profile: str = "season21", name: str = "沈浪", world=None, **flags: bool) -> Game:
    """正式內容、開季時就蓋了減法季的章的一局；flags 是子開關（見 jianfa_rules）。"""
    return _new(jianfa_rules(real_content(profile), **flags), name, world)


def plain_game(profile: str = "season21", name: str = "沈浪", world=None) -> Game:
    """同上，減法季關著（同一份設定的舊規則；「關著一個字都不變」拿它跟改版之前比）。"""
    return _new(no_jianfa(real_content(profile)), name, world)


def ready(game: Game, side: str | None = None, loc: str | None = None, level: int | None = None) -> Game:
    """出了序章、體力補滿；side 給了直接寫進存檔（不走投靠的確認）；loc 給了直接站到那裡；level 給了直接設等級（經驗歸零）。"""
    p, c = game.state.player, game.content
    p.tutorial_step = len(c.tutorial.steps)
    if side is not None:
        p.faction = side
    if loc is not None:
        p.location, p.journey = loc, None
        p.visited.add(loc)
    if level is not None:
        p.member.level, p.member.exp = level, 0
    p.stamina = float(c.config.stamina_max)
    return game
