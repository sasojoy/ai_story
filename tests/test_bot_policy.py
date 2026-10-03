import random

from conftest import walk_to
from tianxia import battle_instance, bot, bot_policy
from tianxia.engine import Option
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome, Effect,
    FactionDef, Location,
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
    journey = game.state.player.journey
    assert journey is not None and journey.path == ["lake"]  # 步行出發，路上要花時間
    game.advance(journey.arrive_at[-1] - game.state.world.time)
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
    game.world.start_battle(definition, now=game.now)
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    fighter = game.world.get_battle().participants[game.state.player.name]
    assert fighter.faction == "guan" and not fighter.is_bot


def _active_battle_with(game, definition, faction):
    game.state.player.faction = faction
    game.world.start_battle(definition, now=game.now - definition.muster_seconds - 1)  # 集結早就截止：下一次刷新就開打
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

def test_a_bot_trains_where_training_helps_its_faction(content, game):
    _install_factions(content)  # 官軍 goals kou -1、黃巾 goals kou +1
    game.state.player.faction = "huang"
    walk_to(game, "lake")  # 湖邊 train_trend kou -1：黃巾的人在這裡歷練會往 +1 推
    train = bot_policy.score(game, Option(id="act:train", label=""), _profile("huang"))
    explore = bot_policy.score(game, Option(id="act:explore", label=""), _profile("huang"))
    assert train > explore


def test_training_with_no_push_scores_below_exploring(content, game):
    content.locations["town"].enemies = ["thug"]  # 小鎮有敵人但沒有大勢推動
    game.state.player.faction = "guan"
    _install_factions(content)
    assert bot_policy.score(game, Option(id="act:train", label=""), _profile("guan")) == bot_policy.TRAIN_SCORE
    assert bot_policy.TRAIN_SCORE < bot_policy.score(game, Option(id="act:explore", label=""), _profile("guan"))


def test_a_bot_heads_for_a_place_where_training_helps(content, game):
    _install_factions(content)
    game.state.player.faction = "huang"
    to_lake = bot_policy.score(game, Option(id="move:lake", label=""), _profile("huang"))
    assert to_lake >= bot_policy.HOME_MOVE_SCORE + bot_policy.TRAIN_MOVE_SCORE


def test_a_bot_does_not_socialize_where_it_would_only_be_turned_away(content, game):
    """名望不夠的假人在只有大勢人物、沒有交遊事件的地方，交遊只會白扣體力；福緣到期時交遊會先送福緣，就另當別論。"""
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 10
    ch.kind, ch.recruit_at, ch.talk_at = "locked", None, "cave"
    game.state.player.location = "cave"
    profile = _profile("guan")
    socialize = Option(id="act:socialize", label="")
    assert game.socialize_is_futile() and not game.socialize_starts_dialogue()
    assert bot_policy.score(game, socialize, profile) is None
    game.state.world.time = 86400  # 第二天：福緣到期，交遊會先送福緣
    assert not game.socialize_is_futile()
    assert bot_policy.score(game, socialize, profile) == bot_policy.ACT_SCORES["socialize"]
    game.state.player.fortune = True  # 福緣給過了：又是白跑一趟
    assert game.socialize_is_futile()
    game.state.player.stats["fame"] = 10  # 名望到了：見得到他，不白跑，但交遊會開口對話，照舊不去
    assert not game.socialize_is_futile() and game.socialize_starts_dialogue()
    assert bot_policy.score(game, socialize, profile) is None


def test_a_bot_still_socializes_where_the_location_has_events(content, game):
    content.characters["mate"].deep_interaction = True
    content.characters["mate"].audience_fame = 10  # 小鎮有交遊事件（拜師），見不到韓鐵也不白跑
    assert not game.socialize_is_futile()
    assert bot_policy.score(game, Option(id="act:socialize", label=""), _profile("guan")) == bot_policy.ACT_SCORES["socialize"]


def _battle_in_the_south(content, game):
    """寶洞搬進南區、打開；官軍的假人在北區的小鎮，自己這一方的決戰在南區集結。"""
    _install_factions(content)
    definition = _install_battle(content)
    definition.region = "south"
    content.locations["cave"].y = 170
    game.state.world.flags.add("cave_open")
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=game.now)
    return definition


def test_a_bot_on_the_road_skips_its_turn(content, game):
    game.choose("move:lake")
    before = (len(game.state.journal), game.state.player.member.wugong_id)
    assert bot_policy.take_turn(game, _profile("guan"), random.Random(0)) == []
    assert (len(game.state.journal), game.state.player.member.wugong_id) == before  # 連自創功法這種照顧動作都不做


def test_a_bot_on_the_road_still_ticks_the_shared_battle(content, game):
    """在路上的假人也替全服戰鬥追趕時間：不然全是假人的戰鬥，集結截止會一直等到有人刷新畫面。"""
    _install_factions(content)
    definition = _install_battle(content)
    game.state.player.faction = "guan"
    game.choose("move:lake")
    game.world.start_battle(definition, now=game.now - definition.muster_seconds - 1)  # 集結早就該截止了
    assert game.world.get_battle().phase == "muster"
    assert bot_policy.take_turn(game, _profile("guan"), random.Random(0)) == []
    assert game.world.get_battle().phase != "muster"


def test_a_bot_hurries_toward_its_sides_battle_in_another_region(content, game):
    _battle_in_the_south(content, game)
    game.state.player.stamina = 100
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    journey = game.state.player.journey
    assert journey is not None and journey.path == ["lake"] and journey.mode == "hurry"


def test_a_bot_walks_to_the_battle_when_it_cannot_afford_to_hurry(content, game, monkeypatch):
    """體力 0 時平常的挑選也會走路（那是唯一能點的選項），所以光看「有走」分不出是不是趕往戰場：
    小鎮多一條通往死路山丘的出口，並把平常的挑選釘死在山丘；只有 _toward_battle 會走向戰場那一站。"""
    _battle_in_the_south(content, game)
    content.locations["hill"] = Location(
        id="hill", name="山丘", description="死路上的小山丘。", connections=["town"], x=200, y=50
    )
    content.locations["town"].connections.append("hill")
    game.state.player.stamina = 0
    monkeypatch.setattr(bot_policy, "pick", lambda game, options, profile, rng: "move:hill")
    enabled = {o.id for o in game.options(odds=False) if o.enabled}
    assert {"move:lake", "move:hill"} <= enabled  # 平常的挑選兩條路都走得了
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    journey = game.state.player.journey
    assert journey is not None and journey.path == ["lake"] and journey.mode == "walk"


def test_a_bot_already_in_the_battle_region_joins_instead_of_travelling(content, game):
    _install_factions(content)
    definition = _install_battle(content)
    definition.region = "north"
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=game.now)
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.state.player.journey is None
    assert game.state.player.name in game.world.get_battle().participants


def test_a_bot_with_an_event_to_settle_does_not_rush_off(content, game):
    _battle_in_the_south(content, game)
    game.state.pending_event = "drunk"
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.state.player.journey is None and game.state.pending_event is None  # 先把事件選完


def test_next_hop_takes_the_quickest_road(content, game):
    game.state.world.flags.add("cave_open")
    assert bot_policy.next_hop(game, ["cave"]) == "lake"
    content.locations["hill"] = Location(
        id="hill", name="山丘", description="小山丘。", connections=["town", "cave"], x=200, y=50
    )
    content.locations["town"].connections.append("hill")
    content.locations["cave"].connections.append("hill")
    assert bot_policy.next_hop(game, ["cave"]) == "hill"  # 一樣兩站，山丘那條不用走湖邊—寶洞的山路


def test_bots_never_pick_the_halt_or_rest_options_meant_for_humans(content, game, monkeypatch):
    """喊停、打坐是修給真人的：假人只走單站、喊停不會出現，萬一出現了也不選，不然整季模擬「沒有能做的事就推進時間」的訊號會失效。"""
    human_only = [Option(id="act:halt", label="喊停", enabled=True), Option(id="act:rest", label="打坐", enabled=True)]
    assert bot.pick(game, human_only, random.Random(0)) is None
    monkeypatch.setattr(game, "options", lambda **kwargs: human_only)
    assert bot_policy.take_turn(game, _profile("guan"), random.Random(0)) == []
    assert game.state.player.journey is None and game.state.player.resting_since is None


def test_a_bot_never_calls_on_a_figure_but_can_always_back_out(content, game):
    """假人不求見大勢人物（不呼叫模型）；萬一停在求見選單上，只會按「返回」。"""
    for cid in ("mate", "scholar"):
        content.characters[cid].deep_interaction = True
    profile = _profile("guan")
    assert bot_policy.score(game, Option(id="act:call", label=""), profile) is None
    game.choose("act:call")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert [o.id for o in options] == ["call:mate", "call:scholar", "call:back"]
    assert [bot_policy.score(game, o, profile) for o in options] == [None, None, 0.0]
    assert bot_policy.pick(game, options, profile, random.Random(0)) == "call:back"
