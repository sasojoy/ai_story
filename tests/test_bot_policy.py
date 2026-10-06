import random

import pytest

from conftest import walk_to
from test_bot import armed
from tianxia import battle_instance, bot, bot_policy, fusion, library, naming, team
from tianxia.engine import Option
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome, Effect,
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


def test_look_after_practices_the_worn_arts_and_never_creates_one(content, game):
    member = game.state.player.member
    bot_policy.look_after(game, random.Random(0))  # 空著的欄位不會被補上（自創已經作廢）
    assert member.neigong_id is None and member.wugong_id is None
    member.neigong_id, member.wugong_id = "breath", "fist"
    member.neigong_level = member.wugong_level = 1
    game.state.player.stats["xinde"] = 1000  # 練成要花心得，這裡驗的是「練不練」不是價錢
    content.config.practice_injury_chance = 0.0
    for seed in range(40):  # 每次有 PRACTICE_CHANCE 的機率練一成：幾輪下來身上的兩門都練到過
        bot_policy.look_after(game, random.Random(seed))
    assert member.neigong_level > 1 and member.wugong_level > 1
    assert (member.neigong_id, member.wugong_id) == ("breath", "fist")


def test_look_after_does_not_practise_what_it_cannot_afford(content, game):
    """練成花心得：付不起下一成就不練，也不會留下一堆「心得不足」的紀錄。"""
    member = game.state.player.member
    member.neigong_id, member.wugong_id = "breath", "fist"
    member.neigong_level = member.wugong_level = 6  # 下一成要 6 點
    game.state.player.stats["xinde"] = 5
    entries = len(game.state.journal)
    for seed in range(40):
        bot_policy.look_after(game, random.Random(seed))
    assert (member.neigong_level, member.wugong_level) == (6, 6)
    assert game.state.player.stats["xinde"] == 5 and len(game.state.journal) == entries


def test_look_after_spends_the_stat_points_through_the_public_action(content, game):
    """假人升級得到的屬性點，每一輪照顧動作先配掉（跟真人一樣只走 Game.allocate_stat，不叫模型）。"""
    p = game.state.player
    p.stat_points = 3
    bot_policy.look_after(game, random.Random(0))
    assert p.stat_points == 0 and sum(p.stats[k] for k in ("str", "agi", "con", "wis")) == 23
    assert [e.title for e in game.state.journal if e.title == "配點"] == ["配點"]  # 連配三點只留一則


def test_a_bot_trains_where_training_helps_its_faction(content, game):
    _install_factions(content)  # 官軍 goals kou -1、黃巾 goals kou +1
    game.state.player.faction = "huang"
    walk_to(game, "lake")  # 湖邊 train_trend kou -1：黃巾的人在這裡遊歷會往 +1 推
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
    """名望不夠的假人在只有大勢人物、沒有交友事件的地方，交友只會白扣體力；福緣到期時交友會先送福緣，就另當別論。"""
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 10
    ch.kind, ch.recruit_at, ch.talk_at = "locked", None, "cave"
    game.state.player.location = "cave"
    profile = _profile("guan")
    socialize = Option(id="act:socialize", label="")
    assert game.socialize_is_futile() and not game.socialize_starts_dialogue()
    assert bot_policy.score(game, socialize, profile) is None
    game.state.world.time = 86400  # 第二天：福緣到期，交友會先送福緣
    assert not game.socialize_is_futile()
    assert bot_policy.score(game, socialize, profile) == bot_policy.ACT_SCORES["socialize"]
    game.state.player.fortune = True  # 福緣給過了：又是白跑一趟
    assert game.socialize_is_futile()
    game.state.player.stats["fame"] = 10  # 名望到了：見得到他，不白跑，但交友會開口對話，照舊不去
    assert not game.socialize_is_futile() and game.socialize_starts_dialogue()
    assert bot_policy.score(game, socialize, profile) is None


def test_a_bot_still_socializes_where_the_location_has_events(content, game):
    content.characters["mate"].deep_interaction = True
    content.characters["mate"].audience_fame = 10  # 小鎮有交友事件（拜師），見不到韓鐵也不白跑
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


def test_a_bot_on_the_road_skips_its_turn(content, game, monkeypatch):
    monkeypatch.setattr(bot_policy, "PRACTICE_CHANCE", 1.0)  # 要是照顧動作沒被跳過，這一輪一定會鍛鍊一成
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 1
    game.choose("move:lake")
    before = (len(game.state.journal), game.state.player.member.wugong_level)
    assert bot_policy.take_turn(game, _profile("guan"), random.Random(0)) == []
    assert (len(game.state.journal), game.state.player.member.wugong_level) == before  # 連鍛鍊這種照顧動作都不做


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


def test_a_bot_at_a_muster_joins_first_even_when_it_picks_at_random(content, game):
    """集結時選單照常有探索、移動（FB-009）；假人不靠強度旋鈕，一看到加入就加入，跟以前選單只剩加入時一樣。"""
    _install_factions(content)
    definition = _install_battle(content)
    content.config.bot_strength = 0.0  # 完全隨機挑
    game.state.player.faction = "guan"
    name = game.state.player.name
    game.world.start_battle(definition, now=game.now)
    assert len([o for o in game.options(odds=False) if o.enabled]) > 1
    for seed in range(5):
        game.world.mutate_battle(lambda b: b.participants.pop(name, None))
        bot_policy.take_turn(game, _profile("guan"), random.Random(seed))
        assert name in game.world.get_battle().participants


def test_a_bot_that_joined_stays_in_the_battle_region_during_the_muster(content, game):
    """集結時選單照常有前往（FB-009）；參戰的假人在區內照常走動，但不走出決戰的大區，開打時人在現場。"""
    _install_factions(content)
    definition = _install_battle(content)
    definition.region = "north"
    content.locations["cave"].y = 170  # 寶洞在南區，從湖邊走得到
    game.state.world.flags.add("cave_open")
    content.config.bot_strength = 0.0  # 完全隨機挑
    game.state.player.faction = "guan"
    walk_to(game, "lake")
    game.world.start_battle(definition, now=game.now)
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.state.player.name in game.world.get_battle().participants
    assert "move:cave" in [o.id for o in game.options(odds=False) if o.enabled]
    for seed in range(30):
        bot_policy.take_turn(game, _profile("guan"), random.Random(seed))
        journey = game.state.player.journey
        assert journey is None or "cave" not in journey.path
        game.state.player.journey = None  # 區內走動就當作已經到了，下一輪接著挑


def test_a_bot_that_joined_never_switches_sides_during_the_muster(content, game):
    """不分陣營的劇本集結時還看得到另一邊的加入；參戰的假人不換邊（加入分數最高，不擋的話每一輪都會換）。"""
    definition = _install_battle(content)
    content.config.bot_strength = 1.0  # 一定挑最高分
    name = game.state.player.name
    game.world.start_battle(definition, now=game.now)
    bot_policy.take_turn(game, _profile(None), random.Random(0))
    side = game.world.get_battle().participants[name].faction
    for seed in range(5):
        bot_policy.take_turn(game, _profile(None), random.Random(seed))
        assert game.world.get_battle().participants[name].faction == side


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
    human_only = [
        Option(id="act:halt", label="喊停", enabled=True), Option(id="act:rest", label="打坐", enabled=True),
        Option(id="road:back", label="折返", enabled=True),  # 路上設計 3.5：假人不折返、不改道
    ]
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


def test_a_bot_never_knocks_on_the_single_audience_button_even_though_it_always_works(content, game):
    """名望不夠的求見按得下去（會被打發，武學與成長設計 9.1）：假人不求見任何人物，單人地點直接列的那顆也不給分。"""
    _install_factions(content)
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 99
    profile = _profile("guan")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "call:mate" in [o.id for o in options]
    assert bot_policy.score(game, next(o for o in options if o.id == "call:mate"), profile) is None
    for seed in range(30):
        assert bot_policy.pick(game, options, profile, random.Random(seed)) != "call:mate"


# ── 假人的武學（tend_arts）：學藝、合成、修練、改練、熔煉、定名 ─────────────────────


@pytest.fixture
def arts_only(monkeypatch):
    """這幾個測試只看合成：每輪必合（有東西可合時），不修練。"""
    monkeypatch.setattr(bot_policy, "FORGE_CHANCE", 1.0)
    monkeypatch.setattr(bot_policy, "CULTIVATE_CHANCE", 0.0)


def test_a_first_time_fusion_waits_for_the_naming_slot(content, world, arts_only):
    """首創的爐要請模型取名：鎖內只開單交給假人程式，什麼都還沒收、還沒合。"""
    game = armed(content, world)
    game.client = None
    slot = bot_policy.NamingSlot(open=True)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert slot.job is not None and slot.job.request.kind == "fuse"
    assert (slot.job.art_id, slot.job.insight_ids) == ("basic_fist", ("feng",))
    assert library.owned_arts(game.state) == ["basic_fist"] and game.state.player.stats["xinde"] == 100


def test_no_slot_no_first_time_fusion(content, world, arts_only):
    """Review Focus 4：輪不到取名就不開這一爐，不用字表名字搶首創。"""
    game = armed(content, world)
    game.client = None
    slot = bot_policy.NamingSlot(open=False)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert slot.job is None and slot.skipped == 1
    assert library.owned_arts(game.state) == ["basic_fist"]


def test_a_known_recipe_is_forged_right_away_without_the_model(content, world, arts_only):
    first = armed(content, world, name="先到")
    first.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))  # 先有人合過、登記了名字
    game = armed(content, world, name="後到")
    game.client = None
    slot = bot_policy.NamingSlot(open=False)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert slot.job is None and slot.skipped == 0
    names = [team.player_art(game.state, content, world, a).name for a in library.owned_arts(game.state)]
    assert "凌風拳" in names


def _waiting_to_name(content, world):
    """合出一門「凌風拳」、練成絕學、輪到自己定名的假人（會等著定名的都是合成出來的：內容武學的名字過不了命名過濾）。"""
    game = armed(content, world)
    game.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))
    game.client = None
    game.state.player.naming = next(a for a in library.owned_arts(game.state) if a != "basic_fist")
    return game


def _named(game, name):
    return any(f"為之定名【{name}】" in r.text for r in game.state.world.chronicle)


def test_a_mastered_art_waits_for_the_naming_slot(content, world, arts_only):
    """練成絕學、輪到自己定名：不沿用原名（企劃者 2026-10-06），開單請模型另取；這一輪什麼都還沒定。"""
    game = _waiting_to_name(content, world)
    slot = bot_policy.NamingSlot(open=True)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert isinstance(slot.job, bot_policy.MasterJob) and slot.job.art_id == game.state.player.naming
    assert slot.job.request.kind == "master"


def test_no_slot_no_mastery_naming(content, world, arts_only):
    """輪不到取名就先不定名（絕學一直等著，跟真人遲遲不填一樣），也不沿用原名。"""
    game = _waiting_to_name(content, world)
    slot = bot_policy.NamingSlot(open=False)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert game.state.player.naming is not None and slot.skipped >= 1 and not _named(game, "凌風拳")


def test_apply_job_names_a_mastered_art_with_the_models_name(content, world):
    game = _waiting_to_name(content, world)
    job = bot_policy.MasterJob(game.state.player.naming, game.mastery_request())
    bot_policy.apply_job(game, job, ("破雲拳", "一句話。"))
    assert game.state.player.naming is None and _named(game, "破雲拳")


@pytest.mark.parametrize("proposed", [("凌風拳", ""), (None, "")], ids=["取回原名", "取不到"])
def test_a_model_name_equal_to_the_old_one_falls_back_to_the_word_list(content, world, proposed):
    """Review Focus 6：模型取回原名、或取壞了叫不動：改用字表另組一個，一定跟原名不同。"""
    game = _waiting_to_name(content, world)
    job = bot_policy.MasterJob(game.state.player.naming, game.mastery_request())
    bot_policy.apply_job(game, job, proposed)
    assert game.state.player.naming is None and not _named(game, "凌風拳")
    assert any("練成絕學，為之定名【" in r.text for r in game.state.world.chronicle)


def test_bots_learn_a_lesson_with_an_attribute_they_lack(content, game):
    walk_to(game, "lake")  # 湖邊教「湖邊腿法」（武學・快，學費 10）
    game.state.player.stats["silver"] = 100
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert "lake_kick" in library.owned_arts(game.state)


def test_bots_keep_silver_for_healing_and_room_for_forging(content, game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = bot_policy.LEARN_SILVER_RESERVE + 9  # 付了 10 兩就不夠療傷
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert "lake_kick" not in library.owned_arts(game.state)
    game.state.player.stats["silver"] = 100
    content.config.holding_cap_base = library.held_count(game.state) + bot_policy.LEARN_ROOM - 1
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert "lake_kick" not in library.owned_arts(game.state)


def test_a_turn_holding_a_naming_job_does_nothing_else(content, world, arts_only):
    """手上有一爐在等名字：這一輪只在爐前等，不做別的（不然體力可能花掉，C 段開不成）。"""
    game = armed(content, world)
    game.client = None
    stamina = game.state.player.stamina
    slot = bot_policy.NamingSlot(open=True)
    bot_policy.take_turn(game, _profile("guan"), random.Random(0), slot)
    assert slot.job is not None and game.state.player.stamina == stamina


@pytest.mark.parametrize("worn,learns", [("sky", False), ("fist", True)], ids=["同屬性不學", "沒有這個屬性才學"])
def test_bots_do_not_learn_what_they_already_have_the_attribute_of(content, game, worn, learns):
    """學藝的價值是多一個屬性可以合成：同一種（武學）已經有這個屬性的，不學、不佔位置。
    身上是天外劍（武學・快）時不學湖邊腿法（武學・快）；身上是長拳（武學・剛）就學（對照組：沒有別的原因擋著）。"""
    walk_to(game, "lake")
    p = game.state.player
    p.stats["silver"] = 100
    p.member.wugong_id, p.member.wugong_level = worn, 1
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert ("lake_kick" in library.owned_arts(game.state)) is learns
    assert p.stats["silver"] == (90 if learns else 100)


def test_a_bot_with_no_arts_and_nothing_to_do_rolls_no_random_numbers(content, game):
    """什麼武學都沒有、也沒有東西可學的假人：tend_arts 一次亂數都不擲（假人程式共用的亂數順序跟以前一樣）。"""
    rng = random.Random(7)
    state = rng.getstate()
    assert bot_policy.tend_arts(game, rng, bot_policy.NamingSlot(open=True)) == []
    assert rng.getstate() == state


def test_take_turn_carries_the_art_messages_in_front_of_the_main_action(content, game):
    _install_factions(content)
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 100
    msgs = bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert any("湖邊腿法" in m for m in msgs) and "lake_kick" in library.owned_arts(game.state)


def test_a_full_library_melts_the_weakest_before_anything_else(content, world, arts_only):
    game = armed(content, world)
    game.client = None
    p = game.state.player
    game.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))
    p.insights = []
    held = library.held_count(game.state)
    content.config.holding_cap_base = held  # 正好滿了
    assert library.full(game.state, content) and p.arts
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot(open=True))
    assert library.held_count(game.state) == held - 1  # 熔了庫裡的一門，沒有意境可合了


def test_a_bot_switches_to_a_stronger_art_in_the_library(content, world, arts_only):
    from test_bot import _two_arts

    game = armed(content, world)
    plain, rich = _two_arts(world, plain_top=29.0, rich_top=60.0, rich_traits=("剛",))
    p = game.state.player
    p.member.wugong_id, p.arts, p.insights = plain.id, [rich.id], []
    for art_id in (plain.id, rich.id):
        p.art_quality[art_id] = "下品"
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert p.member.wugong_id == rich.id


def test_a_bot_cultivates_a_fused_art_when_it_has_the_stamina(content, world, monkeypatch):
    monkeypatch.setattr(bot_policy, "FORGE_CHANCE", 0.0)
    monkeypatch.setattr(bot_policy, "CULTIVATE_CHANCE", 1.0)
    game = armed(content, world)
    game.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))
    p = game.state.player
    p.stats["xinde"], p.stamina = 0, 150
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert p.stamina < 150  # 修練花體力（有融意境的武學才修得了）
    p.stamina = bot.CULTIVATE_RESERVE - 1
    bot_policy.tend_arts(game, random.Random(0), bot_policy.NamingSlot())
    assert p.stamina == bot.CULTIVATE_RESERVE - 1  # 低於保留量：體力留給探索與遊歷


def test_a_second_naming_job_in_the_same_turn_is_skipped(content, world, arts_only):
    """一輪只交一件：名額已經有一件在等，第二件這一輪不開、也不蓋掉前一件。"""
    game = _waiting_to_name(content, world)
    other = bot_policy.MasterJob("別的武學", game.mastery_request())
    slot = bot_policy.NamingSlot(open=True, job=other)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert slot.job is other and slot.skipped >= 1


def test_apply_job_registers_a_first_time_recipe_with_the_models_name(content, world, arts_only):
    game = armed(content, world)
    game.client = None
    slot = bot_policy.NamingSlot(open=True)
    bot_policy.tend_arts(game, random.Random(0), slot)
    msgs = bot_policy.apply_job(game, slot.job, ("凌風拳", "一句話。"))
    names = [team.player_art(game.state, content, world, a).name for a in library.owned_arts(game.state)]
    assert "凌風拳" in names and msgs
    assert game.state.player.stats["xinde"] == 100 - content.config.fuse_xinde


@pytest.mark.parametrize("proposed", [(None, ""), ("拳", "一句話。"), ("凌風拳！？", "")], ids=["沒取到", "太短", "過不了字元"])
def test_apply_job_never_claims_a_first_time_recipe_with_a_name_the_filter_rejects(content, world, arts_only, proposed):
    """F3：取名那一爐沒有拿到過得了過濾的名字（沒取到、或 C 段重驗過不了）：不開、不收費，不用字表名字搶下首創
    （假人搶首創的名字是字表風格，看得出是假人）。"""
    game = armed(content, world)
    game.client = None
    slot = bot_policy.NamingSlot(open=True)
    bot_policy.tend_arts(game, random.Random(0), slot)
    assert bot_policy.apply_job(game, slot.job, proposed) == []
    assert world.lookup_recipe(slot.job.request.key) is None
    assert library.owned_arts(game.state) == ["basic_fist"] and game.state.player.stats["xinde"] == 100


def test_apply_job_still_forges_a_pick_when_the_model_picked_nothing(content, world, arts_only):
    """挑一個的單（合到舊的、候選兩個以上）沒挑到：不產生新名字，C 段照常開爐，由規則挑。"""
    first = armed(content, world, name="先到")
    first.forge("basic_fist", ["feng"], proposed=("凌風拳", "一句話。"))
    game = armed(content, world, name="後到")
    game.client = None
    request = naming.NamingRequest("fuse", fusion.fuse_key("basic_fist", "feng"), "武學", [], choices=("凌風拳", "別名拳"))
    job = bot_policy.ForgeJob("basic_fist", ("feng",), None, request)
    bot_policy.apply_job(game, job, (None, ""))
    assert len(library.owned_arts(game.state)) == 2


def test_apply_job_for_a_mastery_that_is_no_longer_pending_does_nothing(content, world):
    """取名的時候那個等著定名的已經變了（定過了、或換了一門）：不定、不收，下次再來。"""
    game = _waiting_to_name(content, world)
    job = bot_policy.MasterJob(game.state.player.naming, game.mastery_request())
    game.state.player.naming = None
    assert bot_policy.apply_job(game, job, ("破雲拳", "一句話。")) == []
    assert not _named(game, "破雲拳")
