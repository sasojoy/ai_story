"""減法季批 3b-2：約戰的結算掛在哪裡（計畫 Review Focus 第 1 條）。

伺服器排程（server.world_step → Game.world_tick）、任何人的同步（Game.sync）、假人程式的一輪（BotRunner.tick）都會收到時的約戰；
先只讀 world 那一列（sqlite_world.sortie_duels）看有沒有到時的，沒有就不開 world.mutate（每 10 秒的排程與輪詢不寫）。
伺服器的動作（MAIN_ACTIONS 的 sortie_go、sortie_answer、sortie_join）與 main_view 的 sortie_card、sorties。"""
from __future__ import annotations

import random


import server
from duel_kit import LOC, MOVES, NOW, WINDOW, do, duel_content, duel_world, game_of, load, rounds_go, seat, tick
from tianxia import sortie_duel
from tianxia.bot_runner import BotRunner
from tianxia.characters import CharacterStore


def _posted():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    return c, world


def test_nothing_due_means_no_write(monkeypatch):
    c, world = _posted()
    calls = []
    real = sortie_duel.advance
    monkeypatch.setattr(sortie_duel, "advance", lambda *a, **k: calls.append(1) or real(*a, **k))
    before = world.sortie_duels()
    tick(c, world, NOW + 30)
    game_of(c, world, "乙", NOW + 40, sync=True)
    assert calls == [] and world.sortie_duels() == before  # 窗還沒滿：沒開 mutate 結算、world 那一列的約戰一個字不變
    tick(c, world, NOW + WINDOW + 1)
    assert calls == [1]


def test_the_bot_program_tick_settles_a_due_duel(monkeypatch):
    c, world = _posted()
    c.config.bots_min_per_faction = 0  # 不補人：只剩假人程式自己那一下收約戰（沒有假人同步替它收）
    rounds_go(monkeypatch, "大勝")
    runner = BotRunner(c, world=world, characters=CharacterStore(world.db), rng=random.Random(0), clock=lambda: NOW + WINDOW + 1)
    runner.tick()
    duel = next(iter(world.sortie_duels().values()))
    assert duel.status == "settled" and load(world, "甲").battles[0].label == "約戰"


def test_server_world_step_settles(monkeypatch):
    c, world = _posted()
    rounds_go(monkeypatch, "大勝")
    monkeypatch.setattr(server, "CONTENT", c)
    monkeypatch.setattr(server, "WORLD_GAME", None)
    monkeypatch.setattr(server, "open_world", lambda: world)
    server.world_step(lambda: NOW + WINDOW + 1)
    assert next(iter(world.sortie_duels().values())).status == "settled"


def test_main_actions_and_main_view_carry_the_duel(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    assert {"sortie_go", "sortie_answer", "sortie_join"} <= set(server.MAIN_ACTIONS)
    game = game_of(c, world, "甲")
    view = server.main_view(game)
    assert view["sortie"] is True  # 出陣開著的布林照舊（web/main.js 讀它）
    assert view["sortie_card"]["block"] == LOC and view["sorties"] == []
    msgs = server.MAIN_ACTIONS["sortie_go"](game, {"moves": ["奇襲", "奇襲", "撤退"]})
    assert world.sortie_duels() and next(iter(world.sortie_duels().values())).attacker.moves == ["奇襲", "奇襲", "撤退"]
    other = game_of(c, world, "乙")
    duel_id = next(iter(world.sortie_duels()))
    server.MAIN_ACTIONS["sortie_answer"](other, {"id": duel_id, "moves": "強攻,強攻,強攻"})
    assert world.sortie_duels()[duel_id].defender.name == "乙"
    view = server.main_view(game_of(c, world, "乙"))
    assert view["sorties"][0]["id"] == duel_id and view["sorties"][0]["defender"] == "乙"


def test_switched_off_main_view_has_no_duel_keys():
    c = duel_content(off=True)
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    view = server.main_view(game_of(c, world, "甲"))
    assert "sortie_card" not in view and "sorties" not in view


def test_pick_is_quiet():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    game = game_of(c, world, "甲")
    count = len(game.state.journal)
    assert game.choose("act:train") == [sortie_duel.PICK] and len(game.state.journal) == count
