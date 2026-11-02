"""戰局條的倒數（view.battle_gauge 的 due：這一回合還剩幾秒逾時，網頁每秒自己倒數「最遲 M 分 S 秒後結算」，Joy 2026-10-13）。

搬包時開發回報「誰都抓不到」的兩處之一（dev/battle-1；另一處是補劇情單子的 act_index，由 scripts/same_behavior.py 把送給模型的提示
寫進輸出蓋住）：期限過了、還沒有人輪詢把回合推進的那一刻（battle_gauge 只讀、不推進），倒數停在 0、不是負的；集結中不倒數。"""
from __future__ import annotations

import random

from tianxia.engine import Game

BATTLE = "wancheng_jia"


def _active(on):
    """宛城之戰：官軍的甲、黃巾的乙都在宛城，加入、推到開打。回（甲, 這一回合的期限）。"""
    games = []
    for name, side in (("甲", "guan"), ("乙", "huang")):
        g = Game.new(on, name, rng=random.Random(0))
        g.client = None
        g.set_hints_off(True)
        g.state.player.faction, g.state.player.location = side, "wan_city"
        games.append(g)
    a, b = games
    a.world.start_battle(on.battles[BATTLE], now=a.now)
    a.choose("battle:join:guan")
    b.choose("battle:join:huang")
    assert "due" not in a.battle_gauge()  # 集結中不倒數
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()  # 集結截止：推到開打
    battle = a.world.get_battle()
    assert battle.phase == "active"
    return a, battle.round.opened_real + on.battles[BATTLE].round_seconds


def test_the_round_countdown_runs_down_and_stops_at_zero(on):
    a, due = _active(on)
    round_number = a.world.get_battle().round_number
    a.now = due - 30.5
    assert a.battle_gauge()["due"] == 30
    a.now = due + 45  # 期限過了，還沒有人輪詢（battle_gauge 只讀）：停在 0
    assert a.battle_gauge()["due"] == 0
    assert a.world.get_battle().round_number == round_number  # 真的沒推進：看的那一下不結算
