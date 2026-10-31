"""攻城收場（sieges.settle_siege）裡前後對照與別的測試都沒走到的那一支（dev/battle-2 審查，should）：龍頭上陣的留守敗走。

守方是陣營時，攻城的留守是那一區守方的大勢人物（siege.commanders 照 generals.pick）；打倒了照決戰扣聲威、天下大事一句，句子寫這一場的
名字（攻城・地點），「每一位只扣一次」記在攻城那一列（generals.after_battle 的 where、mutate 兩個參數）。搬包之前也沒有一條測試守：
tests/acts/test_conquest_siege.py 倒下的守將都是隊伍（squad:…，不在人物表、after_battle 略過），tests/battle/test_generals.py 拿決戰直接叫
after_battle、不經攻城收場；scripts/same_behavior.py 決戰一軌的六場攻城，是人物的留守一位都沒倒。

另一條（同一輪審查的單點突變裡沒人抓到的 M6）：收場只做一次——傳進來的那一份也標上 settled，同一份再叫一次什麼都不做。
"""
from __future__ import annotations

from conquest_kit import announce, conquest_game, go, join

from tianxia import figures, generals, siege

NOW = 1_792_000_000.0
LOC = "xinye"  # 新野：開季時是黃巾的（守方是陣營），留守是那一區黃巾的大勢人物


def _game():
    game = go(join(conquest_game("week7"), "guan"), LOC)
    game.now = NOW
    return game


def _siege(game):
    """官軍攻黃巾的新野，排到此刻開集結（同 tests/acts/test_conquest_siege.py 的 _open，照 world 的路開：siege.open_waiting）。"""
    slot = announce(game, LOC, "guan")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    found = next(s for s in game.state.world.conquest.schedule if s.id == slot.id)
    return next(b for b in game.world.get_sieges() if b.record_id == found.record_id)


def _felled(game, battle, who="甲"):
    """收場：戰局停在 90（官軍拿下），第一位留守倒在第一回合、who 最後一擊；照收場那一下的路套結果（_apply_battle_outcome → _settle_siege）。"""
    def _close(b):
        b.phase, b.trend, b.end_time = "ended", 90, game.state.world.time
        b.commanders[0].fallen_round, b.commanders[0].felled_by = 1, who

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    return after


def test_a_figure_felled_on_a_siege_loses_prestige_once_under_the_siege_name():
    game = _game()
    c = game.content
    battle = _siege(game)
    chief = battle.commanders[0]
    assert chief.fid in c.figures and chief.faction == "huang"  # 守方是陣營：留守是人物（不是隊伍）
    start = figures.state_of(game.state, c, chief.fid).prestige
    fall = c.config.battle.generals.fall_prestige
    assert fall > 0 and start > fall

    after = _felled(game, battle)
    season = game.world.get_season()
    assert season.figures[chief.fid].prestige == start - fall  # 照決戰扣聲威
    line = generals.SLAY_RUMOR.format(battle=siege.title(c, after.siege), who="甲", name=chief.name)  # 「攻城・新野上，甲陣前擊退……」
    assert [r.text for r in season.rumors if r.layer == "world"].count(line) == 1
    ended = game.world.ended_battle(after.record_id)
    assert ended.commanders[0].settled  # 只扣一次的記號寫在攻城那一列（mutate_siege），不是時刻表決戰那一列
    assert not any(x.settled for x in ended.commanders[1:])  # 沒倒的不記

    generals.after_battle(game.world, c, ended, where=siege.title(c, ended.siege),
                          mutate=lambda fn: game.world.mutate_siege(ended.record_id, fn))  # 讀回來那一列再收一次：不再扣、不再發
    again = game.world.get_season()
    assert again.figures[chief.fid].prestige == start - fall
    assert [r.text for r in again.rumors if r.layer == "world"].count(line) == 1


def test_settling_the_same_object_again_does_nothing():
    """收場只做一次（SiegeInfo.settled）：攻城那一列標上之外，傳進來的那一份也標上（收場那一下的呼叫端手上那一份）；同一份再叫一次
    _settle_siege 什麼都不做——不重發天下大事、季與那一列都不動。"""
    game = _game()
    after = _felled(game, _siege(game))
    assert after.siege.settled
    season, row = game.world.get_season(), game.world.ended_battle(after.record_id)
    game._settle_siege(after)
    assert game.world.get_season().model_dump() == season.model_dump()
    assert game.world.ended_battle(after.record_id).model_dump() == row.model_dump()
