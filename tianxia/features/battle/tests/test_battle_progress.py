"""推進與結算（progress.py，全部拆包第 8 批）——dev/battle-4 審查補的（should、nit）：改這一包時 test_for 挑到的只有包的 tests/ 與核心契約，
搬進來的這幾樣原本只有雜燴檔（tests/core/test_engine.py、test_prologue.py、test_mounts.py……）守，改包的檔挑不到它們。正式內容 week7：
- 份量快照補上（backfill_battle_scores，經 deliver_results 那一格、排在補送前面）：上線前就在場上、沒有份量的人自己同步時補上；看那一場經
  ctx._battle_status（測試換掉 Game._battle_status 的那幾條才打得到；換成「沒有決戰」就不補）。
- 序章裡沒有戰場（battle_for_me，FB-113）：站在草廬、序章還沒走完的人看不到那一場，出了草廬就看得到。
- 收場（apply_battle_outcome）：天下大事多一則「<決戰>論功：」（merit_line），時間到了在等前一場打完的那一場一收場就開（open_waiting_showdown）；
  不在時刻表上的決戰（黃巾決戰）結果的世界旗標記立旗的那一刻（apply_outcome_trends_and_flags）。
"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia.engine import Game
from tianxia.features.battle import progress
from tianxia.sqlite_world import open_world
from tianxia.world import open_showdown

BATTLE = "changshe_fire"
WAITING = "guangzong"  # 時刻表的下一場（冀州）：擺進排隊，長社一收場就開


def _game(name="甲客", world=None):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, name, rng=random.Random(0), world=world or open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "changshe"
    p.tutorial_step = len(c.tutorial.steps)
    game.sync(game.now)
    return game


def _joined(game):
    """長社火攻開集結、加入（有挑同伴那一步就不派）、集結截止開打。"""
    open_showdown(game.world, game.content, BATTLE, game.now)
    game.choose("battle:join:guan")
    if any(o.id == "battle:escort:none" for o in game.options()):
        game.choose("battle:escort:none")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    battle = game.world.get_battle()
    assert battle.phase == "active" and game.state.player.name in battle.participants
    return battle


def _wipe_scores(game):
    name = game.state.player.name
    game.world.mutate_battle(lambda b: setattr(b.participants[name], "scores", {}))
    assert game.world.get_battle().participants[name].scores == {}


def test_a_fighter_with_no_snapshot_gets_it_back_on_his_own_sync(monkeypatch):
    game = _game()
    _joined(game)
    name = game.state.player.name
    taken = dict(game.world.get_battle().participants[name].scores)
    assert taken  # 加入那一刻快照了份量

    _wipe_scores(game)
    game.sync(game.now + 1)  # 同步的 deliver_results 那一格：先補份量快照、再補送
    assert game.world.get_battle().participants[name].scores == taken

    _wipe_scores(game)  # 看那一場經 Game._battle_status（審查 nit：換掉它的測試才打得到）：換成「沒有決戰」就不補，直接叫包裡的 battle_status 會繞過去
    monkeypatch.setattr(Game, "_battle_status", lambda self, tick=True: None)
    progress.backfill_battle_scores(game)
    assert game.world.get_battle().participants[name].scores == {}


def test_nobody_in_the_prologue_sees_the_battle():
    game = _game()
    open_showdown(game.world, game.content, BATTLE, game.now)
    assert progress.battle_for_me(game, tick=False) is not None  # 出了草廬：看得到

    hut = _game("草廬客", world=game.world)
    t = hut.content.tutorial
    hut.state.player.location, hut.state.player.tutorial_step = t.location, 0
    assert hut._battle_status(tick=False) is not None  # 全服那一場就在
    assert progress.battle_for_me(hut, tick=False) is None  # 序章裡一律當作沒有
    assert not any(o.id.startswith("battle:") for o in hut.options())


def _fight_out(game, battle, definition):
    """場上只有他：一直出第一招到收場（同煙霧；倒下了就等回合逾時）。回 battles 表裡收場的那一列。"""
    for _ in range(3 * len(definition.acts) * definition.rounds_per_act):
        b = game.world.get_battle()
        if b.record_id != battle.record_id or b.phase == "ended":
            break
        move = next((o.id for o in game.options() if o.enabled and o.id.startswith("battle:act:")), None)
        if move is not None:
            game.choose(move)
        else:
            game.now = b.round.opened_real + definition.round_seconds + 1
            game.options()
    return game.world.ended_battle(battle.record_id)


def test_the_close_names_the_first_merit_and_opens_the_showdown_waiting_for_it():
    game = _game()
    battle = _joined(game)
    definition = game.content.battles[BATTLE]
    game.world.mutate_season(lambda s: s.showdowns_waiting.append(WAITING))  # 時間到了、前一場還在打：排隊

    ended = _fight_out(game, battle, definition)
    assert ended is not None and ended.phase == "ended" and not ended.unfinished
    season = game.world.get_season()
    merits = [r.text for r in season.rumors if r.layer == "world" and r.text.startswith(f"{definition.name}論功：")]
    assert len(merits) == 1 and game.state.player.name in merits[0]  # 兩軍各自的首功：場上只有他
    nxt = game.world.get_battle()
    assert nxt is not None and nxt.battle_id == WAITING and nxt.phase == "muster"  # 一收場就開排隊的那一場
    assert WAITING not in season.showdowns_waiting


def test_a_plain_showdown_sets_its_world_flags_with_the_time():
    """不在時刻表上的決戰（黃巾決戰）收場：結果的世界旗標寫進季、各記立旗的那一刻（apply_outcome_trends_and_flags）。"""
    game = _game()
    definition = game.content.battles["huangjin_showdown"]
    game.world.start_battle(definition, now=game.now)
    game.choose("battle:join:guan")
    if any(o.id == "battle:escort:none" for o in game.options()):
        game.choose("battle:escort:none")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    battle = game.world.get_battle()
    assert battle.phase == "active"

    ended = _fight_out(game, battle, definition)

    assert ended is not None and not ended.unfinished and ended.outcome_world_flags
    season = game.world.get_season()
    for flag in ended.outcome_world_flags:
        assert flag in season.flags and season.flag_times.get(flag) is not None, flag
