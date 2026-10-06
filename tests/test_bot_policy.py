import random

from conftest import walk_to
from test_engine import _open_three_move_battle, _warlord_in_battle
from tianxia import battle_instance, bot, bot_policy
from tianxia.engine import Option
from tianxia.models import (
    MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, Effect, FactionDef, Location,
)
from tianxia.state import BotProfile

CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}


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
                options=[
                    BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
                    for side in ("guan", "huang") for move in MOVES
                ],
            ),
        ],
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


def _active_battle_with(game, definition, faction, scores=None):
    """假人站 faction 這一邊、已經開打；scores 是它加入時快照的每招份量（沒給＝舊資料，每招 0）。"""
    game.state.player.faction = faction
    game.world.start_battle(definition, now=game.now - definition.muster_seconds - 1)  # 集結早就截止：下一次刷新就開打
    name = game.state.player.name
    game.world.mutate_battle(
        lambda b: battle_instance.join_faction(b, name, faction, neili_cap=300.0, scores=scores)
    )
    other = "huang" if faction == "guan" else "guan"
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "對手", other, neili_cap=300.0))


def test_at_full_strength_a_bot_picks_the_move_it_is_best_at(content, game):
    """三招之後假人照自己每招的份量挑（決戰改版 1）：強攻 90、固守 60、奇襲 40，扣血又不大 → 強攻。"""
    _install_factions(content)
    definition = _install_battle(content)
    content.config.bot_strength = 1.0
    _active_battle_with(game, definition, "guan", scores={"強攻": 90.0, "固守": 60.0, "奇襲": 40.0})
    bot_policy.take_turn(game, _profile("guan"), random.Random(0))
    assert game.world.get_battle().round.pending_actions[game.state.player.name] == "guan_strong"


def test_at_full_strength_a_bot_without_a_snapshot_holds_the_line(content, game):
    """沒有快照的假人（舊資料）份量全 0，只剩扣血的差別：損耗最低的固守。"""
    _install_factions(content)
    definition = _install_battle(content)
    content.config.bot_strength = 1.0
    _active_battle_with(game, definition, "huang")
    name = game.state.player.name
    for seed in range(12):  # 不是碰巧：換十二顆亂數種子都是固守
        game.world.mutate_battle(lambda b: b.round.pending_actions.clear())
        bot_policy.take_turn(game, _profile("huang"), random.Random(seed))
        assert game.world.get_battle().round.pending_actions[name] == "huang_hold"


def test_a_bot_scores_its_best_move_highest(game):
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.update({"強攻": 30.0, "固守": 30.0, "奇襲": 90.0}))
    faction = game.world.get_battle().participants[name].faction
    scores = {m: bot_policy._battle_score(game, f"act:{faction}_{c}") for m, c in CODES.items()}
    assert max(scores, key=scores.get) == "奇襲"


def test_a_warlord_bot_grabs_when_healthy_and_keeps_when_hurt(game):
    """決戰改版 5：豪強的兩招也照份量與扣血打分數——血多就搶地盤，血少就保存實力。"""
    _warlord_in_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.update({m: 100.0 for m in MOVES}))  # 不看開局武學的屬性
    assert bot_policy._battle_score(game, "act:third_grab") > bot_policy._battle_score(game, "act:third_keep")
    game.world.mutate_battle(lambda b: setattr(b.participants[name], "neili", 40.0))
    assert bot_policy._battle_score(game, "act:third_keep") > bot_policy._battle_score(game, "act:third_grab")


def test_a_warlord_bots_scores_follow_the_tuning_numbers(game):
    """份量在扣血之前算、保存實力只算一半：搶地盤 100×1.0÷100 − 35÷氣血，保存實力 100×0.5÷100 − 10÷氣血。"""
    _warlord_in_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: (
        b.participants[name].scores.update({m: 100.0 for m in MOVES}),
        setattr(b.participants[name], "neili_cap", 100.0), setattr(b.participants[name], "neili", 100.0),
    ))
    assert abs(bot_policy._battle_score(game, "act:third_grab") - (1.0 - 0.35)) < 1e-9
    assert abs(bot_policy._battle_score(game, "act:third_keep") - (0.5 - 0.1)) < 1e-9


def test_a_warlord_bot_scores_each_move_with_its_own_share_and_its_hurt_condition(game):
    """搶地盤用奇襲的份量、保存實力用固守的份量（一半），都乘氣血狀態：奇襲 90、固守 30、氣血剩一半（狀態 0.75）。
    份量全一樣、滿血的測試分不出份量拿錯招或沒乘狀態。"""
    _warlord_in_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: (
        b.participants[name].scores.update({"強攻": 10.0, "固守": 30.0, "奇襲": 90.0}),
        setattr(b.participants[name], "neili_cap", 100.0), setattr(b.participants[name], "neili", 50.0),
    ))
    assert abs(bot_policy._battle_score(game, "act:third_grab") - (90 * 0.75 / 100 - 35 / 50)) < 1e-9  # 0.675 − 0.7
    assert abs(bot_policy._battle_score(game, "act:third_keep") - (30 * 0.75 * 0.5 / 100 - 10 / 50)) < 1e-9  # 0.1125 − 0.2


def test_a_warlord_bots_grab_cost_is_its_own_tuning_number_not_the_raids(game):
    """搶地盤的扣血是 third_grab_damage、保存實力是 third_keep_damage，不是奇襲與固守的損耗（預設值剛好相同，所以改成不一樣來測）。"""
    _warlord_in_battle(game)
    tuning = game.content.config.battle
    tuning.third_grab_damage, tuning.third_keep_damage = 50.0, 20.0
    assert tuning.damage["奇襲"] == 35.0 and tuning.damage["固守"] == 15.0
    name = game.state.player.name
    game.world.mutate_battle(lambda b: (
        b.participants[name].scores.update({"奇襲": 100.0, "固守": 100.0}),
        setattr(b.participants[name], "neili_cap", 100.0), setattr(b.participants[name], "neili", 100.0),
    ))
    assert abs(bot_policy._battle_score(game, "act:third_grab") - (1.0 - 50 / 100)) < 1e-9
    assert abs(bot_policy._battle_score(game, "act:third_keep") - (0.5 - 20 / 100)) < 1e-9


def test_a_warlord_bot_takes_a_turn_in_the_battle_and_picks_one_of_its_two_moves(content, game):
    content.config.bot_strength = 1.0
    _warlord_in_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.update({m: 100.0 for m in MOVES}))
    bot_policy.take_turn(game, _profile("haoqiang"), random.Random(0))
    after = game.world.get_battle()  # 場上只有它一個人：出完招這一回合就結算了
    assert after.round_number == 1 and after.participants[name].last_result == "趁亂搶地盤"  # 滿血：搶地盤


def test_an_army_bot_never_scores_the_warlords_moves(game):
    """兩招只在豪強自己的選單上；官軍的人拿到那個 tag（不會發生）也不打分數。"""
    battle, definition = _open_three_move_battle(game)
    assert bot_policy._battle_score(game, f"act:{battle_instance.THIRD_GRAB}") == 0.0


def test_a_bot_that_is_nearly_down_prefers_the_cheaper_move(game):
    """扣血相對剩下的氣血越重、扣分越多：同樣的份量，血少的時候不再挑最傷的強攻。"""
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.update({"強攻": 90.0, "固守": 60.0, "奇襲": 40.0}))
    faction = game.world.get_battle().participants[name].faction

    def best():
        scores = {m: bot_policy._battle_score(game, f"act:{faction}_{c}") for m, c in CODES.items()}
        return max(scores, key=scores.get)

    game.world.mutate_battle(lambda b: setattr(b.participants[name], "neili", 300.0))
    assert best() == "強攻"
    game.world.mutate_battle(lambda b: setattr(b.participants[name], "neili", 40.0))
    assert best() == "固守"


def test_the_bots_scores_count_how_worn_down_it_is(game):
    """份量乘氣血狀態（0.5＋0.5×剩的÷上限）：剩一半氣血時，強攻的 100 分只剩 75。少了這個係數，這裡會挑強攻。"""
    battle, definition = _open_three_move_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: (
        b.participants[name].scores.update({"強攻": 100.0, "固守": 0.0, "奇襲": 0.0}),
        setattr(b.participants[name], "neili_cap", 100.0), setattr(b.participants[name], "neili", 50.0),
    ))
    faction = game.world.get_battle().participants[name].faction
    scores = {m: bot_policy._battle_score(game, f"act:{faction}_{c}") for m, c in CODES.items()}
    # 乘氣血狀態 0.75：強攻 1.0 × 0.75 − 60/50 ＝ −0.45，固守 0 − 15/50 ＝ −0.3 → 固守；少了這個係數，強攻是 1.0 − 1.2 ＝ −0.2 → 強攻
    assert abs(scores["強攻"] + 0.45) < 1e-9 and abs(scores["固守"] + 0.3) < 1e-9
    assert max(scores, key=scores.get) == "固守"


def test_a_bot_scores_nothing_for_a_choice_that_is_not_a_move(game):
    """沒有招的選項（放手一搏、查無此選項）一律 0，不當機；加入戰局還是照舊的高分。"""
    battle, definition = _open_three_move_battle(game)
    assert bot_policy._battle_score(game, "act:no_such_tag") == 0.0
    assert bot_policy._battle_score(game, "join:guan") == bot_policy.JOIN_BATTLE_SCORE
    assert bot_policy._battle_score(game, "spectate") is None


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
