"""一門打不遍（企劃者 2026-10-07 選甲）與首創名望回饋：大場面對手的路數、決戰的隊伍多樣性、給模型的提示、照著合的名望。"""
import random

import pytest

from conftest import real_content
from tianxia import battle_instance, companion_agent, encounter, fusion, journal, styles, team
from tianxia.battle_instance import BattleInstance, BattleParticipant
from tianxia.encounter import Boost, EncounterResult
from tianxia.martial_arts import Insight, MartialArt
from tianxia.models import BattleTuning
from tianxia.state import Echo, new_game_state
from tianxia.sqlite_world import open_world


def season_on(content, state):
    content.config.season_one = True
    state.world.season_one = True


@pytest.fixture
def on(content, state):
    season_on(content, state)
    return content


def _power(state, content, world, squad):
    arts = team.team_arts(state, content, world)
    return encounter.team_power(*team._with_attribute(team._styled_fighters(state, content, world, arts, squad), arts, squad.attribute))


# ── 路數怎麼挑 ──────────────────────────────


def test_each_big_opponent_fears_one_road_and_handles_another_and_it_changes_by_season():
    attrs = ["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"]
    first = styles.pick(0, "boss", attrs)
    assert first == styles.pick(0, "boss", attrs)  # 同一季同一個對手固定
    assert first.soft != first.hard and {first.soft, first.hard} <= set(attrs)
    assert len({styles.pick(t, "boss", attrs) for t in range(20)}) > 3  # 換季（天機 +1）就換，抄不了去年的答案
    assert len({styles.pick(0, f"figure_{i}", attrs) for i in range(20)}) > 3  # 每個人不一樣


def test_only_big_opponents_have_a_road_and_only_with_season_one_on(content, state, world):
    boss, thug = content.squads["boss"], content.squads["thug"]
    assert styles.style_of(state, content, world, boss) is None  # 開關關著：beta 一個字都不變
    season_on(content, state)
    assert styles.style_of(state, content, world, boss) == styles.pick(world.read().tianji, "boss", content.config.styles.attributes)
    assert styles.style_of(state, content, world, thug) is None  # 散兵沒有路數


def test_the_soft_road_lifts_and_the_hard_road_drags_each_fighter(on):
    rule = on.config.styles
    style = styles.Style("柔", "剛")
    assert styles.factor(on, style, "柔") == 1 + rule.soft_bonus
    assert styles.factor(on, style, "剛") == 1 - rule.hard_penalty
    assert styles.factor(on, style, "快") == 1.0 and styles.factor(on, None, "柔") == 1.0
    boosts = styles.styled([Boost(factor=1.2), Boost()], ["柔", "快"], on, style)
    assert boosts[0].factor == pytest.approx(1.2 * 1.25) and boosts[1].factor == 1.0


@pytest.mark.parametrize("road", ["soft", "hard"])
def test_the_fight_and_the_odds_both_feel_the_road(content, state, world, road):
    boss = content.squads["boss"]
    state.player.member.wugong_id = "fist"
    worn = team.worn_attribute(state, content, world)
    plain = _power(state, content, world, boss)
    assert plain > 0
    season_on(content, state)
    other = next(a for a in content.config.styles.attributes if a != worn)
    # 只留兩路：本人那一門不是對手怕的、就是對手拿手對付的，看天機落在哪一邊
    content.config.styles.attributes = [worn, other]
    style = styles.style_of(state, content, world, boss)
    if getattr(style, road) != worn:
        content.config.styles.attributes = [other, worn]
        style = styles.style_of(state, content, world, boss)
    assert getattr(style, road) == worn
    expected = 1.25 if road == "soft" else 0.75
    assert _power(state, content, world, boss) == pytest.approx(plain * expected)
    assert team.estimate(state, content, world, "boss")  # 勝算走同一條路（_styled_fighters）


def test_the_report_says_one_soft_line_only_when_the_road_mattered(on):
    style, lines = styles.Style("柔", "剛"), on.config.styles.lines
    assert styles.note(on, style, "柔", "險勝") == [lines["soft"]]
    assert styles.note(on, style, "柔", "落敗") == []
    assert styles.note(on, style, "剛", "落敗") == [lines["hard"]]
    assert styles.note(on, style, "剛", "大勝") == []
    assert styles.note(on, style, "快", "落敗") == []
    for line in lines.values():  # 含蓄：不寫屬性、不寫倍數
        assert not any(ch.isdigit() for ch in line) and not any(a in line for a in on.config.styles.attributes)


def test_a_big_fight_in_the_game_files_the_line_in_the_battle_report(game):
    season_on(game.content, game.state)
    game.state.player.member.wugong_id = "fist"
    worn = team.worn_attribute(game.state, game.content, game.world)
    game.content.config.styles.attributes = [worn, "實" if worn != "實" else "虛"]
    boss = game.content.squads["boss"]
    style = styles.style_of(game.state, game.content, game.world, boss)
    tier = "險勝" if style.soft == worn else "落敗"
    result = EncounterResult(tier=tier, our_power=100.0, difficulty=200.0, margin=0.0)
    line = game.content.config.styles.lines["soft" if style.soft == worn else "hard"]
    assert game._style_note(boss, result) == [line]
    assert game._style_note(game.content.squads["thug"], result) == []  # 散兵沒有路數


# ── 決戰：隊伍的路數越雜越難招架 ──────────────────────────────


def _instance(*people):
    instance = BattleInstance(battle_id="b", phase="active")
    for name, faction, attribute in people:
        instance.participants[name] = BattleParticipant(name=name, faction=faction, neili=100, neili_cap=100, attribute=attribute)
    return instance


def test_more_roads_on_one_side_push_harder_up_to_a_cap():
    tuning = BattleTuning()
    instance = _instance(("甲", "guan", "剛"), ("乙", "guan", "柔"), ("丙", "guan", "剛"), ("丁", "huang", "快"))
    moves = {"甲": "強攻", "乙": "強攻", "丙": "固守", "丁": "強攻"}
    assert battle_instance.diversity(instance, moves, "guan", tuning) == pytest.approx(1 + tuning.diversity_per)
    assert battle_instance.diversity(instance, moves, "huang", tuning) == 1.0
    many = _instance(*((str(i), "guan", a) for i, a in enumerate("陰陽剛柔快慢")))
    assert battle_instance.diversity(many, {str(i): "強攻" for i in range(6)}, "guan", tuning) == pytest.approx(1 + tuning.diversity_cap)


def test_no_roads_are_counted_when_the_snapshot_is_empty():
    instance = _instance(("甲", "guan", ""), ("乙", "guan", ""))
    assert battle_instance.diversity(instance, {"甲": "強攻", "乙": "奇襲"}, "guan", BattleTuning()) == 1.0


def test_the_join_snapshot_carries_the_road_only_with_season_one_on(game):
    game.state.player.member.wugong_id = "fist"
    assert game._battle_road() == ""
    season_on(game.content, game.state)
    assert game._battle_road() == "剛"
    game.state.player.member.wugong_id = None
    assert game._battle_road() == ""  # 赤手空拳不算一路
    instance = BattleInstance(battle_id="b", phase="muster")
    battle_instance.join_faction(instance, "沈浪", "guan", 100, attribute="剛")
    assert instance.participants["沈浪"].attribute == "剛"


def test_a_mixed_side_beats_a_same_road_side_of_equal_strength(definition_for_round):
    """兩邊各四個人、份量一樣、出同一招：路數雜的那一邊把戰局推過去。"""
    from tianxia.battle_instance import MOVES  # noqa: PLC0415

    definition = definition_for_round
    battle = battle_instance.start_muster(definition, now=0)
    people = [(f"官{i}", "guan", road) for i, road in enumerate("剛柔快慢")] + [(f"黃{i}", "huang", "剛") for i in range(4)]
    for name, side, road in people:
        battle_instance.join_faction(battle, name, side, neili_cap=1000, scores={m: 50.0 for m in MOVES}, attribute=road)
    battle_instance.close_muster(battle, definition, random.Random(0), now=0)
    for name, side, _ in people:
        battle_instance.submit_action(battle, name, f"{side}_strong")
    battle_instance.resolve_round(battle, definition, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 51  # 官軍（正向）四路封頂 ×1.15、黃巾一路：10 × 0.15 ÷ 2.15 ≈ 0.7，進成 1


@pytest.fixture
def definition_for_round():
    from test_battle_instance import _three_moves_for  # noqa: PLC0415
    from tianxia.models import BattleAct, BattleDef, BattleFaction, BattleOutcome  # noqa: PLC0415

    return BattleDef(
        id="three", name="三招之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=_three_moves_for("guan", "huang"))],
        rounds_per_act=9, decisive_margin=40,
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
    )


# ── 給模型的提示 ──────────────────────────────


def test_the_big_fight_judge_hears_the_road_in_plain_words(on):
    line = styles.fight_line(on, styles.Style("柔", "剛"))
    words = on.config.styles.words
    assert words["柔"] in line and words["剛"] in line
    assert styles.fight_line(on, None) == ""


def test_a_figure_lets_slip_a_habit_only_to_a_friend():
    c = real_content("weekend")
    state, world = new_game_state(c, "沈浪"), open_world()
    state.world.season_one = True
    character = c.characters["bocai"]
    habit = c.config.styles.words
    style = styles.style_of(state, c, world, c.squads[c.figures["bocai"].squad])
    state.player.affinities["bocai"] = c.config.styles.talk_affinity - 1
    assert habit[style.soft] not in companion_agent.build_system_prompt(character, state, c, world, "bocai")
    state.player.affinities["bocai"] = c.config.styles.talk_affinity
    prompt = companion_agent.build_system_prompt(character, state, c, world, "bocai")
    assert habit[style.soft] in prompt and habit[style.hard] in prompt


# ── 首創名望回饋 ──────────────────────────────


def _art(creator="王五"):
    return MartialArt(id="寒江掌", name="寒江掌", kind="武學", attribute="柔", quality="下品", base_power=10, top_power=40, creator=creator, creator_shown=creator)


def test_following_someone_elses_recipe_is_counted_once_per_person(on, state):
    art = _art()
    fusion.echo(state, on, art, first=False)
    fusion.echo(state, on, art, first=False)  # 同一個人只算一次
    assert state.world.echoes["寒江掌"] == Echo(creator="王五", name="【寒江掌】", followers=["沈浪"])
    fusion.echo(state, on, _art("沈浪").model_copy(update={"id": "自己的"}), first=False)  # 自己首創的不算
    fusion.echo(state, on, art.model_copy(update={"id": "首創"}), first=True)
    fusion.echo(state, on, Insight(id="霜意", name="霜意", attribute="陰"), first=False)  # 沒有首創者的不算
    assert list(state.world.echoes) == ["寒江掌"]


def test_nothing_is_counted_with_season_one_off(content, state):
    fusion.echo(state, content, _art(), first=False)
    assert state.world.echoes == {}


def test_the_cap_stops_the_count_and_spreads_a_rumor(on, state):
    cap = on.config.first_echo.cap
    state.world.echoes["寒江掌"] = Echo(creator="王五", name="【寒江掌】", followers=[f"人{i}" for i in range(cap - 1)])
    fusion.echo(state, on, _art(), first=False)
    assert len(state.world.echoes["寒江掌"].followers) == cap
    assert state.world.rumors[-1].text == fusion.ECHO_RUMOR.format(who="王五", thing="【寒江掌】")
    state.player.name = "後來的人"
    fusion.echo(state, on, _art(), first=False)
    assert len(state.world.echoes["寒江掌"].followers) == cap


def test_the_creator_gets_the_fame_on_the_next_sync_once(game):
    season_on(game.content, game.state)
    game.state.world.echoes["寒江掌"] = Echo(creator="沈浪", name="【寒江掌】", followers=["甲", "乙"])
    game.state.world.echoes["別人的"] = Echo(creator="王五", name="【別人的】", followers=["沈浪"])
    fame = game.state.player.stats.get("fame", 0)
    game._deliver_echoes()
    assert game.state.player.stats["fame"] == fame + 2 * game.content.config.first_echo.fame_per
    entry = game.state.journal[0]
    assert entry.title == journal.ECHO and "江湖上又有 2 人照著你首創的【寒江掌】練了出來。" in entry.lines
    game._deliver_echoes()  # 補過了就不再補
    assert game.state.player.stats["fame"] == fame + 2
    game.state.world.echoes["寒江掌"].followers.append("丙")
    game._deliver_echoes()
    assert game.state.player.stats["fame"] == fame + 3


def test_a_real_follow_through_the_forge_is_recorded(on, state, world):
    """真的走兩次 fusion.fuse：甲首創、乙照著合，季裡記乙一筆（甲的 Game 同步時補名望）。"""
    from test_fusion import named, other_player  # noqa: PLC0415

    state.player.member.wugong_id = "basic_fist"
    state.player.insights, state.player.stats["xinde"] = ["feng"], 100
    first, _ = fusion.fuse(state, on, world, named("旋風腿"), "basic_fist", "feng")
    follower = other_player(on)
    follower.world = state.world  # 同一季
    art, msgs = fusion.fuse(follower, on, world, None, "basic_fist", "feng")
    assert art.id == first.id and "照著合出了同一門" in msgs[0]
    assert state.world.echoes[art.id] == Echo(creator="沈浪", name=f"【{art.name}】", followers=["乙"])
