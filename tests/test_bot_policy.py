import random
import time

from tianxia import battle_instance, bot_policy
from tianxia.engine import Option
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome, Effect,
    FactionDef,
)
from tianxia.state import BotProfile


def _install_factions(content):
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
    ]


def _install_battle(content):
    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[BattleOption(text="穩紮穩打", tag="safe"), BattleOption(text="全力進攻", tag="aggressive")],
                advance_when=BattleAdvanceWhen(trend_min=90),
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "aggressive": BattleActionEffect(trend_delta=5, neili_damage=20),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
    )
    content.battles[definition.id] = definition
    return definition


def _profile(faction, personality="普通"):
    return BotProfile(personality=personality, seed=1, faction=faction, season_number=1)


def test_effect_score_follows_the_faction_goal_and_likes_rewards():
    effect = Effect(trend={"kou": 2}, stats={"xinde": 10})
    assert bot_policy.effect_score(effect, {"kou": 1}) == 21.0
    assert bot_policy.effect_score(effect, {"kou": -1}) == -19.0


def test_full_strength_always_picks_the_best_option(content, game):
    _install_factions(content)
    content.config.bot_strength = 1.0
    game.state.player.faction = "guan"
    options = [o for o in game.options(odds=False) if o.enabled and o.id != "act:rest"]
    picks = {bot_policy.pick(game, options, _profile("guan"), random.Random(seed)) for seed in range(20)}
    assert picks == {"act:explore"}


def test_low_strength_mostly_picks_at_random(content, game):
    _install_factions(content)
    content.config.bot_strength = 0.2  # 普通個性 +0：強度 0.2
    game.state.player.faction = "guan"
    options = [o for o in game.options(odds=False) if o.enabled and o.id != "act:rest"]
    rng = random.Random(0)
    picks = {bot_policy.pick(game, options, _profile("guan"), rng) for _ in range(100)}
    assert len(picks) > 1


def test_a_bot_never_picks_another_factions_join_or_a_figure_dialogue(content, game):
    _install_factions(content)
    content.characters["mate"].deep_interaction = True
    profile = _profile("huang")
    assert bot_policy.score(game, Option(id="faction:guan", label=""), profile) is None
    assert game.socialize_starts_dialogue()
    assert bot_policy.score(game, Option(id="act:socialize", label=""), profile) is None


def test_a_bot_walks_to_its_factions_join_point_and_joins(content, game):
    _install_factions(content)
    profile = _profile("huang")
    rng = random.Random(0)
    bot_policy.take_turn(game, profile, rng)
    assert game.state.player.location == "lake"
    bot_policy.take_turn(game, profile, rng)
    assert game.state.player.pending_faction == "huang"
    bot_policy.take_turn(game, profile, rng)
    assert game.state.player.faction == "huang"
    assert game.world.faction_counts() == {"huang": 1}


def test_next_hop_follows_the_map_and_skips_locked_places(content, game):
    assert bot_policy.next_hop(game, ["lake"]) == "lake"
    assert bot_policy.next_hop(game, ["town"]) is None  # 已經在這裡
    assert bot_policy.next_hop(game, ["cave"]) is None  # 寶洞還沒開放


def test_a_bot_leaves_a_dialogue_it_somehow_got_into(content, game):
    game.state.player.pending_companion = "mate"
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.state.player.pending_companion is None


def test_a_bot_joins_its_own_side_of_a_battle_as_an_ordinary_fighter(content, game):
    _install_factions(content)
    definition = _install_battle(content)
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=time.time())
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    fighter = game.world.get_battle().participants[game.state.player.name]
    assert fighter.faction == "guan" and not fighter.is_bot


def _active_battle_with(game, definition, faction):
    game.state.player.faction = faction
    game.world.start_battle(definition, now=0.0)  # 集結早就截止：下一次刷新就開打
    name = game.state.player.name
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, name, faction, neili_cap=100.0))
    other = "huang" if faction == "guan" else "guan"
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "對手", other, neili_cap=100.0))


def test_at_full_strength_a_bot_picks_the_tactic_that_pushes_its_side(content, game):
    _install_factions(content)
    definition = _install_battle(content)
    content.config.bot_strength = 1.0
    _active_battle_with(game, definition, "guan")  # 官軍是第一方：戰局往上推對官軍有利
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.world.get_battle().round.pending_actions[game.state.player.name] == "aggressive"


def test_at_full_strength_the_other_side_holds_the_line(content, game):
    _install_factions(content)
    definition = _install_battle(content)
    content.config.bot_strength = 1.0
    _active_battle_with(game, definition, "huang")
    bot_policy.take_turn(game, _profile("huang"), random.Random(0))
    assert game.world.get_battle().round.pending_actions[game.state.player.name] == "safe"


def test_look_after_creates_arts_with_ordinary_looking_names(content, game):
    bot_policy.look_after(game, random.Random(0))
    member = game.state.player.member
    assert member.neigong_id and member.wugong_id
    assert not any(ch.isdigit() for ch in member.neigong_id + member.wugong_id)
