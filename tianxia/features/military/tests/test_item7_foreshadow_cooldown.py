"""fix-1008 項目七（joy：「冷卻先改一天」，PM 讀成：冷卻改成一個遊戲日，joy 的字「一個遊戲日內不會再出現」不動）。

伏筆最後一步答錯（FsWrong.cooldown_days）以前是季曆天（DAY ÷ cal_scale：一個遊戲日的六分之一——14 天的季是 4 小時、週末約 43 分鐘），
跟 joy 寫的「一個遊戲日內不會再出現」對不上。現在照遊戲日（rules.day_seconds，跟著這一季蓋的季長縮）：從答錯那一刻起整整 cooldown_days
個遊戲日（控制者裁示：整段時間，不是「到下一次換日」）——14 天的季是 24 小時（以前 4 小時）、週末 2.5 天的季約 4 小時 17 分（以前
約 43 分鐘）：兩種季長都長了六倍。用真實內容的兩處（亮出黃巾、什麼都沒搜到）。"""
from __future__ import annotations

import random

import pytest

from tianxia import foreshadow, rules
from tianxia.engine import Game
from tianxia.models import FsWrong

DAY = 86400


def _wrongs(content):
    """真實內容裡每一個有冷卻的答錯：(鏈, 答錯)。"""
    out = []
    for chain in content.foreshadows.chains:
        steps = [chain.final, *chain.final.steps] if chain.final.steps else [chain.final]
        for step in steps:
            for option in getattr(step, "options", []) or []:
                if option.wrong is not None and option.wrong.cooldown_days:
                    out.append((chain, option.wrong))
            wrong = getattr(step, "wrong", None)
            if wrong is not None and wrong.cooldown_days:
                out.append((chain, wrong))
    return out


def _game(content, days):
    content.config.season_days = days
    game = Game.new(content, "甲", rng=random.Random(0))
    game.client = None
    assert game.state.world.length_days == days
    return game


@pytest.mark.parametrize("days, hours", [(2.5, 24 * 2.5 / 14), (14, 24)])
def test_a_wrong_answer_waits_one_game_day(on, days, hours):
    game = _game(on, days)
    chain = on.foreshadows.chains[0]
    now = 5000.0
    foreshadow._punish(game.state, on, chain, chain.final, FsWrong(cooldown_days=1), now)  # noqa: SLF001
    waited = game.state.player.fs_cooldown_until[chain.id] - now
    assert waited == pytest.approx(rules.day_seconds(on, game.state.world)) == pytest.approx(hours * 3600)


def test_the_wait_is_a_full_span_from_the_wrong_answer_not_until_the_next_day_turn(on):
    game = _game(on, 2.5)
    chain = on.foreshadows.chains[0]
    span = rules.day_seconds(on, game.state.world)
    for now in (100.0, span * 0.9):  # 一天的開頭、快換日的時候答錯：都是整整一個遊戲日
        foreshadow._punish(game.state, on, chain, chain.final, FsWrong(cooldown_days=1), now)  # noqa: SLF001
        assert game.state.player.fs_cooldown_until[chain.id] - now == pytest.approx(span)
    foreshadow._punish(game.state, on, chain, chain.final, FsWrong(cooldown_days=2), 0.0)  # noqa: SLF001
    assert game.state.player.fs_cooldown_until[chain.id] == pytest.approx(2 * span)


def test_the_wait_follows_the_season_length_stamped_at_its_opening(on):
    """季長照開季時蓋的章（CLAUDE.md「設定中途換了也不影響正在跑的這一季」）：設定改成 14 天，這一季（2.5 天開的）照舊約 4 小時 17 分。"""
    game = _game(on, 2.5)
    on.config.season_days = 14
    chain = on.foreshadows.chains[0]
    foreshadow._punish(game.state, on, chain, chain.final, FsWrong(cooldown_days=1), 0.0)  # noqa: SLF001
    assert game.state.player.fs_cooldown_until[chain.id] == pytest.approx(24 * 2.5 / 14 * 3600)


def test_both_real_cooldowns_follow_the_game_day_and_keep_joys_words(on):
    wrongs = _wrongs(on)
    texts = sorted(w.text for _, w in wrongs)
    assert texts == sorted(["他嚇得跑了，一個遊戲日內不會再出現。", "什麼都沒搜到。"]) and all(w.cooldown_days == 1 for _, w in wrongs)
    game = _game(on, 2.5)
    for chain, wrong in wrongs:
        foreshadow._punish(game.state, on, chain, chain.final, wrong, 1000.0)  # noqa: SLF001
        assert game.state.player.fs_cooldown_until[chain.id] - 1000.0 == pytest.approx(rules.day_seconds(on, game.state.world))
