"""減法季批 6（人物心意、託付與來信；主機側計畫第七節）的測試建法。批 2 接線在建的 tests/jianfa_kit.py 還不在 feature/jianfa 上，
同名的檔不在這一批建。用正式內容的 season21（三位人物的心意與託付就是正式內容寫的那幾筆）照伺服器開一季；模型一律是假的。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import companion_agent, stances
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣），同 tests/test_week_unlock.py
LUZHI, BOCAI, HUANGFU = "luzhi", "bocai", "huangfusong"
CAMP = "luzhi_camp"  # 盧植開季在這裡（talk_at）


def real_game(profile="season21", *, name="沈浪", open_at=MON + 10 * HOUR, setup=None, location=CAMP, faction="guan") -> Game:
    """照伺服器開一季（store.open_season 蓋章）、建一個走完引導的角色（站在 location、投靠 faction）、同步到開季那一刻。
    setup(content) 在開季之前改內容（例：關掉子開關）。一個測試只開一季（conftest 每個測試一個資料庫）。"""
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    if setup is not None:
        setup(c)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, open_at)
    g = Game.new(c, name, rng=random.Random(0), world=store)
    g.client = None
    p = g.state.player
    p.tutorial_step = len(c.tutorial.steps)
    p.location = location
    p.faction = faction
    at(g, open_at)
    return g


def at(game: Game, now: float) -> None:
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


def week_start_real(game: Game, week: int, after: float = HOUR) -> float:
    """第 week 週（7 天的季是段）開始之後 after 現實秒的現實時間（照 game.now 換算）。"""
    from tianxia import calendar

    w = game.state.world
    return game.now + (calendar.week_start(week, game.content, w) - w.time) / game.content.config.time_scale + after


def stance_turn(game: Game, cid: str, stance: str | None, narrative: str = "他沉吟了一會。") -> companion_agent.CompanionTurn:
    """鎖外生成好的一輪（帶 stance 那一欄的型別，同 companion_agent.generate_turn 開著時用的那一個）。"""
    ids = stances.ids_for(game.state, game.content, cid)
    model = companion_agent.turn_model(ids) if ids else companion_agent.CompanionTurn
    extra = {"stance": stance} if ids and stance is not None else {}
    return model(narrative=narrative, options=["勸他速攻", "勸他持重", "告辭"], option_tags=["真誠請教", "坦誠相待", "尋常寒暄"], **extra)


def talking(game: Game, cid: str, options=("勸他趁黃巾未穩速攻廣宗", "告辭")) -> None:
    """已經在跟 cid 談（上一輪給了這幾個選項）：直接擺好對話的狀態，不叫模型。"""
    p = game.state.player
    p.pending_companion = cid
    p.last_offered_dialogue[cid] = [list(options), ["真誠請教", "尋常寒暄"][: len(options)]]
    p.affinities.setdefault(cid, 20)
