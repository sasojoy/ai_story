"""假人的有所感與頓悟取名（第二輪第 101 批：SENSE_RIGHT、SENSE_DRAW、sense_pick、sense_stroke、sense_draw 從 bot 搬來，_sense、_god_name 從 bot_policy 搬來；舊名 re-export 同一批物件）。
沒有掛鉤：bot.play_season、bot_policy.take_turn 經舊名叫，先後留在殼。要換 SENSE_DRAW、sense_stroke 換這裡，換 bot 打不到（_sense 讀這個檔的模組全域）。
取名的單子（SenseJob、EpiphanyJob、NamingSlot、NO_NAME）四包開單，在共用層 bot_base，一律寫 `bot_base.X`。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from tianxia import bot_base, insights

from . import epiphany, glyph, sensing

if TYPE_CHECKING:
    from tianxia.engine import Game

SENSE_RIGHT = 0.6  # 有所感時挑到選得對的做法的機會（其餘從全部做法裡隨便挑，可能也挑對）：看得懂場景的玩家大多挑得對
SENSE_DRAW = 0.8  # 進了感悟狀態之後真的畫一筆（其餘順其自然，落回做法那個基本意境）


def sense_pick(game: Game, rng: random.Random) -> str | None:
    """有所感的時候挑什麼（整季機器人與伺服器假人共用，悟意境設計 0.4）：還沒選做法就挑一個（SENSE_RIGHT 的機會挑選得對的），
    進了感悟狀態就畫（sensing.DRAW，呼叫端要接著 sense_draw）或順其自然。不在有所感是 None。"""
    got = sensing.current(game.state, game.content)
    if got is None:
        return None
    s, scene, loc = got
    if s.stage == "draw":
        return sensing.DRAW if rng.random() < SENSE_DRAW else sensing.LET_GO
    pool = insights.pool_attributes(loc, game.content)
    right = [i for i, j in enumerate(s.order) if scene.prologue or scene.methods[j].attribute in pool]
    if right and rng.random() < SENSE_RIGHT:
        return f"{sensing.PREFIX}{rng.choice(right)}"
    return f"{sensing.PREFIX}{rng.randrange(len(s.order))}"


def sense_stroke(game: Game, rng: random.Random, same: bool = False) -> list[list[float]]:
    """機器人不會畫：照它想要的屬性挑一筆現成的（glyph.SAMPLES）。same＝畫跟做法一樣的屬性（一定落回基本意境、不用取名）。"""
    s = game.state.player.sensing
    attribute = s.method if same and s is not None and s.method in glyph.SAMPLES else rng.choice(sorted(glyph.SAMPLES))
    return glyph.SAMPLES[attribute]


def sense_draw(game: Game, rng: random.Random) -> list[str]:
    """整季機器人畫一筆：A 段開單、C 段直接交回（沒給名字：Game.sense_draw 在鎖內用短逾時問一次，取不到走退路字表）。"""
    req = game.sense_request(sense_stroke(game, rng))
    if isinstance(req, str):
        return game.choose(sensing.LET_GO)
    return game.sense_draw(req)


def _sense(game: Game, rng: random.Random, slot: bot_base.NamingSlot | None) -> list[str]:
    """有所感：挑做法照整季機器人（bot.sense_pick）。要畫的時候，輪得到取名名額就隨手畫一筆——要取名的開成單交給假人程式；
    輪不到就畫一筆跟做法同屬性的（一定落回這裡的基本意境、不用取名），不拿字表名字悟出私有意境。"""
    choice = sense_pick(game, rng)
    if choice is None:
        return []
    if choice != sensing.DRAW:
        return game.choose(choice)
    can_name = slot is not None and slot.open and slot.job is None
    req = game.sense_request(sense_stroke(game, rng, same=not can_name))
    if isinstance(req, str):
        return game.choose(sensing.LET_GO)
    if req.needs_name:
        if can_name:
            slot.job = bot_base.SenseJob(req)
            return []
        if slot is not None:
            slot.skipped += 1
        return game.choose(sensing.LET_GO)
    return game.sense_draw(req, bot_base.NO_NAME)


def _god_name(game: Game, rng: random.Random, slot: bot_base.NamingSlot | None) -> list[str]:
    """特殊頓悟取名：還沒想過名字的，輪得到就開單交給假人程式請模型取（B、C 段在 bot_runner）；輪不到先等，下一輪再來；
    假人程式叫不到模型（slot.model 是 False）、或不是從假人程式來的（slot 是 None）直接按靜心思名（字表）。候選排好了挑一個（不自己寫）。"""
    naming_ = game.state.player.god_naming
    if not naming_.asked:
        request = game.epiphany_request()
        if request is None:
            return []
        if slot is None or not slot.model:
            return game.choose(f"{epiphany.OPTION}:{epiphany.THINK}")
        if slot.open and slot.job is None:
            slot.job = bot_base.EpiphanyJob(request)
        else:
            slot.skipped += 1
        return []
    if not naming_.candidates:
        return []
    return game.choose(f"{epiphany.OPTION}:{rng.randrange(len(naming_.candidates))}")
