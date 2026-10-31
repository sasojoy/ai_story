"""假人挑心意（減法季批 6 Task 6-3；企劃者 2026-10-24 第 5 件）：伺服器假人每天照名號雜湊擲 bot_stance_chance（0.3【預設】），
中了就直接記一筆心意（不說話、不寫字，讓人少的服心意也會動）；人物挑自己這一邊的，心意照名號＋人物的雜湊挑。一人一天一筆、
到門檻、貢獻都跟真人說話那一輪同一條（Game.voice_stance）。關著的季一筆都不記。正式內容的 season21。"""
from __future__ import annotations

import random


from stances_kit import BOCAI, DAY, HUANGFU, LUZHI, at, real_game
from tianxia import bot_policy, stances
from tianxia.state import BotProfile


def _bot(g, faction="guan"):
    g.state.player.bot = BotProfile(personality="普通", seed=1, faction=faction, season_number=1)
    g.state.player.faction = faction


def _chance(value):
    return lambda c: setattr(c.config.jianfa, "bot_stance_chance", value)


def test_a_bot_voices_one_stance_a_day_without_a_word():
    g = real_game(setup=_chance(1.0))
    _bot(g)
    s, c = g.state, g.content
    journal, contrib = len(s.journal), s.player.contrib
    assert bot_policy.voice_stance(g)
    [(fid, book)] = g.world.get_season().stance_counts.items()  # 存進共用的季
    assert fid in (LUZHI, HUANGFU) and sum(book.values()) == 1  # 官軍的假人只勸官軍的人物
    assert len(s.journal) == journal and s.player.contrib == contrib + c.config.jianfa.stance_contribution  # 不寫紀錄
    bot_policy.look_after(g, random.Random(1))  # 同一天的照顧動作那一輪：同一個結果、已經記過
    assert not bot_policy.voice_stance(g)
    assert sum(g.world.get_season().stance_counts[fid].values()) == 1
    picked = stances.bot_pick(s, c)
    assert picked is not None and picked[0] == fid and stances.heard_today(s, c, fid) == picked[1]


def test_the_care_round_is_where_bots_voice_it():
    """伺服器假人每一輪的照顧動作（bot_policy.look_after）會叫它：一筆就記在那裡。"""
    g = real_game(setup=_chance(1.0))
    _bot(g)
    bot_policy.look_after(g, random.Random(0))
    assert sum(sum(b.values()) for b in g.world.get_season().stance_counts.values()) == 1


def test_the_same_bot_keeps_advising_the_same_stance():
    g = real_game(setup=_chance(1.0))
    _bot(g, "huang")
    s, c = g.state, g.content
    first = stances.bot_pick(s, c)
    assert first is not None and first[0] == BOCAI  # 黃巾的假人只勸波才
    g._save_season()
    at(g, g.now + DAY)
    assert stances.bot_pick(g.state, c) == first  # 照名號＋人物的雜湊：像有個性


def test_the_daily_roll_misses_about_seventy_percent_of_days():
    g = real_game()
    _bot(g)
    s, c = g.state, g.content
    hits = 0
    for name in (f"假{i}" for i in range(200)):
        s.player.name = name
        hits += stances.bot_pick(s, c) is not None
    assert 40 <= hits <= 80  # 0.3【預設】


def test_closed_seasons_and_zero_chance_record_nothing():
    g = real_game(setup=_chance(0.0))
    _bot(g)
    bot_policy.look_after(g, random.Random(0))
    assert g.world.get_season().stance_counts == {}
    h = real_game(setup=lambda c: (setattr(c.config.jianfa, "bot_stance_chance", 1.0), setattr(c.config.jianfa, "stances", False)))
    _bot(h)
    bot_policy.look_after(h, random.Random(0))
    assert h.world.get_season().stance_counts == {} and stances.bot_pick(h.state, h.content) is None
