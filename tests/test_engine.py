import pytest

from conftest import FixedRandom

HOUR = 3600


def ids(game):
    return [o.id for o in game.options()]


def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.equipped[1] == "fist"
    assert "測試開始。" in game.state.log


def test_town_options(game):
    assert ids(game) == ["act:explore", "act:socialize", "move:lake"]  # 城鎮沒有敵人，不能歷練


def test_locked_location_hidden_until_flag(game):
    game.choose("move:lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_move_costs_stamina(game):
    game.choose("move:lake")
    assert game.state.player.location == "lake"
    assert game.state.player.stamina == 145


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    assert all(not o.enabled for o in game.options())
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_explore_presents_event_and_resolves_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert ids(game) == ["choice:0", "choice:1"]
    game.choose("choice:0")
    assert game.state.pending_event is None
    assert game.state.player.stats["good"] == 2
    assert game.state.world.trends["kou"] == 25
    assert "（檢定成功）" in game.state.log


def test_join_sect_via_socialize(game):
    game.choose("act:socialize")
    game.choose("choice:0")
    assert game.state.player.sect == "cloud"
    assert game.state.player.equipped[1:3] == ["fist", "sword"]


def test_key_battle_flow_lose(game):
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")
    assert ids(game) == ["tactic:強攻", "tactic:巧取", "tactic:固守", "tactic:絕招", "tactic:撤退"]
    for _ in range(10):
        if game.state.battle is None:
            break
        game.choose("tactic:強攻")
    assert game.state.battle is None
    assert game.state.player.stats["silver"] == 40
    assert "你敗了。" in game.state.log


def test_train_wins_and_pushes_trend(game):
    game.choose("move:lake")
    game.choose("act:train")
    p = game.state.player
    assert p.stamina == 135
    assert p.stats["silver"] == 55
    assert p.skills["fist"].exp == 10
    assert game.state.world.trends["kou"] == 29


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"


def test_stamina_regenerates_with_time(game):
    game.state.player.stamina = 0
    game.advance(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)  # 第一次只記下現實時間
    game.sync(1010.0)  # 10 秒 × 60 倍 = 600 秒
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_seclusion_completes_and_grants_exp(game):
    game.seclude(4, "fist")
    assert ids(game) == ["act:break"]
    game.advance(4 * HOUR)
    assert game.state.player.busy_until is None
    assert game.state.player.skills["fist"].level == 2  # 4 小時 × 20 × (1 + 5/20) = 100


def test_break_seclusion_early(game):
    game.seclude(4, "fist")
    game.advance(HOUR)
    game.choose("act:break")
    assert game.state.player.busy_until is None
    assert game.state.player.skills["fist"].exp == 25


def test_season_ends_by_time(game):
    game.advance(2 * 24 * HOUR)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags  # 翻江龍 48 小時把寇亂推到 78
    assert ids(game) == ["season:new"]


def test_new_season_resets(game):
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"


def test_equip_rules(game):
    game.choose("act:socialize")
    game.choose("choice:0")  # 學到 sword，放進第二個外功欄
    game.equip(1, "sword")
    assert game.state.player.equipped[1:3] == ["sword", None]
    game.equip(0, "sword")  # 欄位不符，不變
    assert game.state.player.equipped[0] is None
    game.equip(1, None)
    assert game.state.player.equipped[1] is None


def test_texts_render(game):
    assert "沈浪" in game.status_text()
    assert "小鎮" in game.scene_text()
    assert "寇亂" in game.trends_text() and "寶藏" not in game.trends_text()
    assert game.rumors_text() == "（尚無傳聞。）"
    game.choose("act:explore")
    assert "醉漢" in game.scene_text()
