"""全服決戰的煙霧測試（開發規範手冊 4.1 第三級：一包一條，真實內容，走一次最常見的路）：這一包搬的是「看」那一半，所以走一次「看」——
正式內容 week7 開長社火攻（時刻表決戰，管理者開戰同一條 world.open_showdown），官軍的人在長社加入、集結截止開打：場景、戰局條、
放手一搏的輸入框；一個人打到收場（倒下了就等回合逾時），收場那一下把自己的戰報、江湖紀錄與「剛剛」那張卡片的戰局條補上來、下一次同步
不再補一次。不借別的測試檔的輔助函式
（審查 nit：以前用測試內容、從 tests/core/test_engine.py 拿兩個私有的輔助函式）。"""
import random

import pytest
from conftest import real_content

from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world import open_showdown

BATTLE = "changshe_fire"


@pytest.mark.smoke
def test_a_fight_is_drawn_and_its_closing_report_is_filed():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲客", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "changshe"
    p.tutorial_step = len(c.tutorial.steps)
    game.sync(game.now)  # 伺服器每個請求先同步（今天的簽到在這一下記掉，不擠到收場那一則前面）
    feature = next(f for f in FEATURES if f.name == "battle")
    assert feature.enabled(game) is True  # 正式內容有決戰（battles.json）
    assert game.battle_gauge() is None and not game.battle_on_screen()
    definition = c.battles[BATTLE]

    open_showdown(game.world, c, BATTLE, game.now)  # 集結
    assert game.battle_gauge()["phase"] == "muster" and "due" not in game.battle_gauge()
    game.choose("battle:join:guan")
    if any(o.id == "battle:escort:none" for o in game.options()):
        game.choose("battle:escort:none")  # 有挑同伴那一步就不派
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()  # 集結截止：推到開打
    assert game.world.get_battle().phase == "active"
    assert definition.name in game.scene_text() and game.battle_on_screen()
    assert game.battle_gauge()["phase"] == "active" and game.siege_banner() is None
    gamble = next(o.text for o in definition.acts[0].options if o.free_text and o.faction == "guan")
    assert game.battle_free_text_prompt() == gamble and game.battle_free_text_note() is not None

    for _ in range(3 * len(definition.acts) * definition.rounds_per_act):  # 場上只有他：一直出第一招到收場
        battle = game.world.get_battle()
        if battle.phase == "ended":
            break
        move = next((o.id for o in game.options() if o.enabled and o.id.startswith("battle:act:")), None)
        if move is not None:
            game.choose(move)
        else:  # 倒下了、轉為觀戰：回合等到逾時才結算（輪詢的人推進）
            game.now = battle.round.opened_real + definition.round_seconds + 1
            game.options()
    assert game.world.get_battle().phase == "ended"
    game.sync(game.now)  # 收場那一下補到自己手上（_deliver_battle_results）；下一次同步不再補一次

    (record,) = [r for r in game.state.battles if r.kind == "showdown"]
    assert record.event == definition.name and record.battle_ref == game.world.get_battle().record_id and record.log
    assert any(e.title.startswith(definition.name) and e.battle_id == record.id for e in game.state.journal)
    assert game.card_gauge() == record.gauge is not None and record.gauge["phase"] == "ended"
    assert not game.battle_on_screen() and game.battle_free_text_prompt() is None and game.battle_gauge() is None
