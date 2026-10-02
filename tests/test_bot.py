import random

from tianxia.bot import pick, play_season, spend_xinde, wants_heal
from tianxia.world_state import WorldStateStore


def test_wants_heal_only_with_internal_injury(game):
    """療傷照內傷計價：氣血低但沒有內傷時會自己回，不用去療傷（不然只會一直寫「氣血無恙」）。"""
    member = game.state.player.member
    assert not wants_heal(game)
    member.neili = 1.0
    assert not wants_heal(game)
    member.injury = 10.0
    assert wants_heal(game)


def test_spend_xinde_first_creates_then_practices_each_slot(game):
    rng = random.Random(0)
    member = game.state.player.member
    spend_xinde(game, rng)
    assert member.neigong_id is not None and member.wugong_id is not None
    assert (member.neigong_level, member.wugong_level) == (1, 1)
    spend_xinde(game, rng)
    assert (member.neigong_level, member.wugong_level) == (2, 2)


def test_spend_xinde_heals_first_when_neili_is_low(game):
    game.state.player.member.neili = 10.0
    game.state.player.member.injury = 40.0  # 有內傷才有東西可以療（療傷按內傷計價）
    game.state.player.stats["silver"] = 999
    spend_xinde(game, random.Random(0))
    assert game.state.player.member.injury == 0.0 and game.state.player.member.neili is None


def test_pick_accepts_whoever_the_event_wants_to_recruit(game):
    game.state.player.flags.add("heard_music")
    game.state.pending_event = "meet"
    options = game.options()
    assert pick(game, options, random.Random(0)) == "choice:0"  # 「請他入門」


def test_pick_is_random_when_nothing_wants_to_be_recruited(game):
    options = [o for o in game.options(odds=False) if o.enabled]
    seeds = {pick(game, options, random.Random(seed)) for seed in range(20)}
    assert seeds <= {o.id for o in options} and len(seeds) > 1


def test_pick_returns_none_with_nothing_to_choose(game):
    assert pick(game, [], random.Random(0)) is None


def test_play_season_completes_a_full_season(content):
    game = play_season(content, 0, max_steps=500)
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert game.state.world.time > 0


def test_play_season_is_deterministic_for_a_given_seed(tmp_path, content):
    """同一顆種子要重現一模一樣的結果——各自給獨立的共用世界狀態，不然招募/取名的
    競態結果會因為兩次呼叫共用同一份檔案而互相汙染，讓比較失去意義。"""
    a = play_season(content, 1, max_steps=200, world=WorldStateStore(tmp_path / "a.json"))
    b = play_season(content, 1, max_steps=200, world=WorldStateStore(tmp_path / "b.json"))
    assert a.state.player.member.level == b.state.player.member.level
    assert a.state.world.time == b.state.world.time


def test_play_season_grows_the_players_arts_with_xinde(content):
    game = play_season(content, 1, max_steps=500)
    member = game.state.player.member
    assert member.neigong_level > 1 or member.wugong_level > 1


def test_play_season_observe_is_called_before_and_after_every_step(content):
    seen = []
    play_season(content, 0, max_steps=5, observe=lambda g: seen.append(g.state.world.time))
    assert len(seen) == 6  # 開季一次 + 每步一次
    assert seen[0] == 0.0


def test_the_bot_opens_the_season_itself_when_the_server_is_still_preparing(content):
    content.config.auto_open_first_season = False
    game = play_season(content, 1)
    assert game.state.world.ended


def test_a_bot_does_not_try_to_heal_what_it_cannot_afford(game):
    """付不起療傷費就先不療傷，不然每一輪都會在江湖紀錄裡寫一筆「銀兩不足」。"""
    member = game.state.player.member
    member.injury = 40.0
    game.state.player.stats["silver"] = 0
    assert not wants_heal(game)
    game.state.player.stats["silver"] = 999
    assert wants_heal(game)
