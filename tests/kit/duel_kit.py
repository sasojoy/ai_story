"""減法季批 3b 接線（出陣約戰，tianxia/sortie_duel.py 接進引擎、伺服器、假人）測試共用的建法（不改 tests/conftest.py）。

正式內容的 season21（減法季、領地爭奪、豪強分屬兩軍都開著）開季就蓋章；off=True 只把 sortie_duel 這個子開關關掉（總開關照開），
拿來證明「子開關關著舊出陣一個字都不變」。一局一個資料庫（conquest_kit._new 每次開新的暫存資料庫檔）；兩個人以上照伺服器的做法
每一個動作都從資料庫重讀自己（do，同 tests/test_conquest_clash._do）。"""
from __future__ import annotations

import random

from conquest_kit import _new
from conftest import real_content
from tianxia import encounter
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import Content
from tianxia.state import BotProfile

NOW = 1_792_000_000.0
LOC = "runan_wilds"  # 汝南荒野：潁川汝南的中立地，兩軍開季都碰得到
FAR = "nanyang_road"  # 南陽官道：南陽的中立地（跟汝南荒野不同區）
WINDOW = 600.0  # Config.sortie.window_minutes 10 分
MOVES = "強攻,固守,奇襲"


def duel_content(profile: str = "season21", *, off: bool = False) -> Content:
    c = real_content(profile)
    c.config.auto_open_first_season = True
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0  # 不等新手期
    c.config.xingshi.enabled = False  # 〈天下形勢〉不開單（不多一則天下大事）
    c.config.train_event_chance = 0.0
    if off:
        c.config.jianfa.sortie_duel = False
    return c


def duel_world(c: Content):
    """開好季的世界（第一個角色「甲」先建好、存起來）。"""
    first = _new(c, "甲")
    first.state.last_real = NOW
    CharacterStore(first.world.db).save(first.state)
    first.world.mutate(lambda shared: setattr(shared, "season_last_real", NOW))
    return first.world


def seat(c: Content, world, name: str, side: str | None, loc: str = LOC, *, bot: bool = False, ally: str | None = None,
         faction: str | None = None) -> None:
    """把這個人擺好：陣營（豪強給 faction="haoqiang"、ally）、所在、引導走完、體力補滿；bot=True 標成這一季的假人。"""
    store = CharacterStore(world.db)
    state = store.load(name)
    if state is None:
        state = _new(c, name, world).state
    p = state.player
    p.faction, p.ally = faction or side, ally
    p.location, p.journey = loc, None
    p.visited.add(loc)
    p.tutorial_step = len(c.tutorial.steps)
    p.stamina = float(c.config.stamina_max)
    state.last_real = NOW
    if bot:
        p.bot = BotProfile(personality="積極", seed=7, faction=p.faction, season_number=world.get_season_number())
    store.save(state)


def load(world, name: str):
    return CharacterStore(world.db).load(name)


def game_of(c: Content, world, name: str, now: float = NOW, *, sync: bool = False) -> Game:
    state = load(world, name)
    game = Game(c, state, random.Random(0), world)
    game.client = None
    if sync:
        game.sync(now)
    else:
        game.now = now
        game.state.world = world.get_season()
    return game


def do(c: Content, world, name: str, act, now: float = NOW, *, sync: bool = False):
    """照伺服器的做法：從資料庫重讀這個人、（要的話先同步）、做一件事、存季與角色。回（訊息, 那一份 Game）。"""
    game = game_of(c, world, name, now, sync=sync)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def tick(c: Content, world, now: float) -> list[str]:
    """伺服器排程的一下（server.world_step 那一份沒有玩家的 Game）。"""
    game = Game.for_world(c, world, random.Random(0))
    game.client = None
    return game.world_tick(now)


def rounds_go(monkeypatch, *tiers: str) -> None:
    """三回合的單次判定照給的結果（攻方的角度：大勝、險勝是攻方贏那一回合，落敗是守方贏，僵持是平）；給一個就三回合都一樣。"""
    seq = list(tiers) * (3 if len(tiers) == 1 else 1)
    calls = {"n": 0}

    def fake(ours, theirs, rng, *a, **k):
        tier = seq[calls["n"] % len(seq)]
        calls["n"] += 1
        rng.random()  # 照樣用掉一次這一場的亂數
        return encounter.EncounterResult(tier=tier, margin=10.0, our_power=ours, difficulty=theirs)

    monkeypatch.setattr(encounter, "resolve_encounter", fake)


def text_of(state) -> str:
    """這個人看得到的字：江湖紀錄每一則（標題、標記、敘事、數值）與每一份戰報（標題、過程、結果）。"""
    parts: list[str] = []
    for e in state.journal:
        parts += [e.title, e.tag, *e.lines, *e.changes]
    for r in state.battles:
        parts += [r.opponent, r.label, *r.rounds, *r.notes, *r.changes]
    return "\n".join(parts)
