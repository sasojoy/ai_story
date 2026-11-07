"""龍頭上陣（Joy 2026-10-17 第 2 條「大決戰雙方龍頭武將應該要參與且有份量」）的決戰包那一半（generals.py）：開集結派那條戰線上的
大勢人物上陣、陣前那一行寫兩邊的陣容與主將令、收場扣聲威。

全部拆包第 8 批合進 develop 時從 tianxia/features/battle/tests/test_generals.py 拆過來（PM 定，手冊第十五節「第 8 批的 PM 認定」第 1 條）；回合規則與挑法
（battle_instance、共用規則層 chiefs.pick）那七條在 tests/battle/test_chiefs.py。斷言一個字沒改。"""
from __future__ import annotations

from conftest import real_content
from tianxia.features.battle import instance as bi
from tianxia import figures
from tianxia.features.battle import generals
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season


def _season(content) -> GameState:
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def test_after_battle_dents_prestige_once(world):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    world.seed_first_season(c)
    if world.season_phase() == "preparing":
        world.open_season(c, 0.0)
    d = c.battles["changshe_fire"]
    battle = world.start_battle(d, 0.0)
    battle.commanders = [bi.Commander(fid="bocai", name="波才", faction="huang", fallen_round=3, felled_by="甲")]
    start = figures.state_of(_season(c), c, "bocai").prestige
    generals.after_battle(world, c, battle)
    season = world.get_season()
    assert season.figures["bocai"].prestige == start - c.config.battle.generals.fall_prestige
    assert any("甲陣前擊退波才" in r.text for r in season.rumors)
    assert battle.commanders[0].settled
    generals.after_battle(world, c, battle)
    assert world.get_season().figures["bocai"].prestige == start - c.config.battle.generals.fall_prestige


def test_the_showdown_scene_shows_the_lineup_and_the_order(world):
    """長社火攻：開集結派皇甫嵩、朱儁、波才上陣；開打之後畫面寫兩邊的陣容與主將令，照令的那一顆按鈕接「・主將令」。"""
    from test_gentry_allied import _game, _showdown

    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = _game(c, faction="guan")
    _showdown(game)
    assert [x.name for x in game.world.get_battle().commanders][:3] == ["皇甫嵩", "朱儁", "波才"]
    game.choose("battle:join:guan")
    game.now = game.world.get_battle().muster_deadline_real + 1
    game.options()  # 被動追趕：集結時間到了就開打
    battle = game.world.get_battle()
    assert battle.phase == "active" and battle.orders
    scene = game.scene_text()
    assert "主將皇甫嵩" in scene and "傳令" in scene
    assert any(bi.ORDER_MARK in o.label for o in game.options())
