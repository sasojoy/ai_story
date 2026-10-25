"""減法季批 3b-3：假人與整季機器人碰約戰（整合設計 4.3、5.7「假人可以應約戰、封招，不可以寫字」；計畫 Task 3b-3）。

伺服器假人（bot_policy.take_turn）在推得動、打得贏的塊貼約戰（act:train 換成 sortie:go:<三招>），封招用 tactics.best_against 混一招隨機；
對面貼的、同一區、還有次數、威力不被壓太多的，窗開過一半才應（留給真人先應）；同袍的約三分之一同去；不應自己陣營的。
整季機器人（bot.pick）挑到出陣那一格也換成 sortie:go。整季跑得完、戰報不露假人。"""
from __future__ import annotations

import random

import pytest

from duel_kit import FAR, LOC, MOVES, NOW, WINDOW, do, duel_content, duel_world, game_of, load, seat
from tianxia import bot, bot_policy, sortie_duel
from tianxia.characters import CharacterStore
from tianxia.models import MOVES as THREE

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _quiet(monkeypatch):
    """take_turn 前面那幾樣隨機的事（截殺、名帖、設伏工事、酒肆、擂台）不做，只看打分數那一步。"""
    for name in ("_raid", "_hand_card", "_stamina_play", "_tavern", "_arena"):
        monkeypatch.setattr(bot_policy, name, lambda *a, **k: None)
    monkeypatch.setattr(bot_policy, "_outmatched", lambda game, loc: False)  # 打得過守軍（不然守軍難度六十幾，新角色不去攻）


def test_duel_moves_are_three_known_moves():
    rng = random.Random(3)
    for _ in range(30):
        moves = bot.duel_moves(rng)
        assert len(moves) == 3 and all(m in THREE for m in moves)


def test_the_whole_season_bot_turns_the_cell_into_a_sealed_post():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    game = game_of(c, world, "甲")
    cell = next(o for o in game.options() if o.id == "act:train")
    choice = bot.pick(game, [cell], random.Random(0))
    assert choice.startswith("sortie:go:")
    assert sortie_duel.moves_problem(c.config.sortie, choice.removeprefix("sortie:go:").split(",")) is None
    game.choose(choice)
    assert world.sortie_duels()


def test_a_server_bot_posts_where_it_can_push(monkeypatch):
    _quiet(monkeypatch)
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan", bot=True)
    game = game_of(c, world, "甲")
    cell = next(o for o in game.options() if o.id == "act:train")
    assert bot_policy.score(game, cell, game.state.player.bot) is not None
    monkeypatch.setattr(bot_policy, "pick", lambda g, options, profile, rng: "act:train")
    bot_policy.take_turn(game, game.state.player.bot, random.Random(1))
    duels = world.sortie_duels()
    assert duels and next(iter(duels.values())).attacker.name == "甲"


def test_a_server_bot_answers_the_other_side_late_in_the_window_but_not_its_own_side():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "丁", "huang", bot=True)
    seat(c, world, "戊", "guan", bot=True)
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    duel_id = next(iter(world.sortie_duels()))
    early = game_of(c, world, "丁", NOW + 30)
    assert bot_policy.duel_play(early, early.state.player.bot, random.Random(0)) is None  # 窗的前一半留給真人
    late = game_of(c, world, "丁", NOW + WINDOW * 0.9)
    assert bot_policy.duel_play(late, late.state.player.bot, random.Random(0)) is not None
    CharacterStore(world.db).save(late.state)
    assert world.sortie_duels()[duel_id].defender.name == "丁"
    assert load(world, "丁").player.answers_today == 1
    ally = game_of(c, world, "戊", NOW + WINDOW * 0.9)
    bot_policy.duel_play(ally, ally.state.player.bot, random.Random(0))
    assert world.sortie_duels()[duel_id].defender.name == "丁"  # 同陣營不應戰（同去看機率，不在這裡驗）


def test_a_server_bot_does_not_answer_when_far_or_outclassed():
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "丁", "huang", FAR, bot=True)
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    far = game_of(c, world, "丁", NOW + WINDOW * 0.9)
    assert bot_policy.duel_play(far, far.state.player.bot, random.Random(0)) is None
    world.mutate(lambda shared: [setattr(d.attacker, "power", 1e6) for d in shared.sorties.values()])  # 對面強得多
    seat(c, world, "丁", "huang", LOC, bot=True)
    weak = game_of(c, world, "丁", NOW + WINDOW * 0.9)
    assert bot_policy.duel_play(weak, weak.state.player.bot, random.Random(0)) is None
    assert next(iter(world.sortie_duels().values())).defender is None


def test_a_bots_only_server_clears_every_duel_within_a_day(monkeypatch):
    """只有假人的服：兩邊的假人貼約戰、窗內應戰或到時補位結算，一天之內收得掉（沒有卡著不結算的），紀錄不露假人。"""
    _quiet(monkeypatch)
    c = duel_content()
    world = duel_world(c)
    names = [f"將{i}" for i in range(4)]
    for name, side in zip(names, ("guan", "huang", "guan", "huang"), strict=True):
        seat(c, world, name, side, bot=True)
    t = NOW
    for step in range(24 * 6):  # 每 10 分鐘一輪、一天
        t = NOW + step * 600
        for i, name in enumerate(names):
            game = game_of(c, world, name, t, sync=True)
            bot_policy.take_turn(game, game.state.player.bot, random.Random(step * 10 + i))
            game._save_season()
            CharacterStore(world.db).save(game.state)
    game_of(c, world, names[0], t + WINDOW + 1, sync=True)
    duels = world.sortie_duels()
    assert duels, "一天下來一張約戰都沒貼"
    assert all(d.status in ("settled", "void") for d in duels.values())
    for name in names:
        words = "\n".join(e.title + "".join(e.lines) for e in load(world, name).journal)
        assert "假人" not in words and "機器人" not in words


def test_the_whole_season_bot_runs_a_short_season21_stretch(tmp_path):
    from tianxia.sqlite_world import open_world

    c = duel_content()
    game = bot.play_season(c, 1, max_steps=300, world=open_world(tmp_path / "w.db"))
    assert game.state.player.name
    for r in game.state.battles:
        assert "假人" not in "".join(r.notes)
