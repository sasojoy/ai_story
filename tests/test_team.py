"""門下與隊伍：武學與成長 Task 3 加進來的部分——基礎武學照品質解析、每個人自己那一份的品質。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import encounter, team, traits
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name
from tianxia.sqlite_world import open_world
from tianxia.state import PLAYER, Member

LOW_ONLY = {"下品": 100, "中品": 0, "上品": 0, "絕學": 0}
CONTENT_DIR = Path(__file__).parent.parent / "content"


def _claim_whirlwind(world):
    art = generate_from_name("旋風腿", "武學", "旋風腿", weights=LOW_ONLY)
    world.claim_skill_name(art)
    return art


def test_a_companion_without_lore_reads_as_the_base(state, content, world):
    """同伴的內容（characters.json 的 stats）沒寫博聞：member_stats 照五項列出來，博聞當基準 5，不能 KeyError。"""
    companion = next(iter(content.characters))
    assert team.member_stats(state, content, world, companion)["lore"] == team.BASE_STAT
    assert set(team.member_stats(state, content, world, PLAYER)) == set(team.COMBAT_STATS)  # PLAYER 已從 tianxia.state import


def test_content_basic_art_resolves_as_low_grade(content, world):
    assert team.resolve_art("basic_fist", content, world).quality == "下品"


def test_a_peerless_content_art_still_resolves_as_peerless(content, world):
    art = team.resolve_art("fist", content, world)
    assert (art.quality, art.origin) == ("絕學", "historical")


def test_resolve_art_gives_the_shared_registered_copy(state, content, world):
    """resolve_art 回的是全服共享那一份，不看玩家自己的品質；玩家自己的品質另走 player_art。"""
    _claim_whirlwind(world)
    state.player.art_quality["旋風腿"] = "上品"
    assert team.resolve_art("旋風腿", content, world).quality == "下品"
    assert team.resolve_art(None, content, world) is None


def test_art_quality_defaults_to_the_registered_quality(state, content, world):
    art = _claim_whirlwind(world)
    assert team.art_quality(state, art) == "下品"
    state.player.art_quality["旋風腿"] = "中品"
    assert team.art_quality(state, art) == "中品"


def test_player_art_uses_the_players_own_quality(state, content, world):
    _claim_whirlwind(world)
    assert team.player_art(state, content, world, "旋風腿").quality == "下品"
    state.player.art_quality["旋風腿"] = "上品"
    assert team.player_art(state, content, world, "旋風腿").quality == "上品"
    assert world.get_skill("旋風腿").quality == "下品"  # 全服那一筆不動


def test_player_art_of_nothing_is_nothing(state, content, world):
    assert team.player_art(state, content, world, None) is None
    assert team.player_art(state, content, world, "ghost") is None


def test_player_art_works_for_a_content_art_too(state, content, world):
    state.player.art_quality["basic_fist"] = "中品"
    art = team.player_art(state, content, world, "basic_fist")
    assert (art.quality, art.base_power, art.top_power) == ("中品", 16, 44)
    assert team.resolve_art("basic_fist", content, world).quality == "下品"


def test_team_arts_hand_the_encounter_the_players_quality(state, content, world):
    _claim_whirlwind(world)
    state.player.member.wugong_id = "旋風腿"
    state.player.art_quality["旋風腿"] = "中品"
    assert team.team_arts(state, content, world)["旋風腿"].quality == "中品"


def test_team_arts_keep_the_companions_content_arts(state, content, world):
    """同伴的武學照舊從內容解析（沒有「自己的品質」這回事）。"""
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    state.player.team = ["mate"]
    state.player.member.wugong_id = "basic_fist"
    arts = team.team_arts(state, content, world)
    assert arts["fist"].quality == "絕學"
    assert arts["basic_fist"].quality == "下品"


def test_team_arts_keep_the_followers_arts():
    """審查裁示 F6：部下的武學要留在 team_arts 裡，不然部下的威力悄悄變成 0（encounter 查不到那門武學）。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    game.state.player.followers = ["follower_guan_spear", "follower_guan_crossbow"]
    wanted = {real.followers[f].wugong for f in game.state.player.followers}
    assert len(wanted) == 2
    arts = team.team_arts(game.state, real, game.world)
    assert wanted <= set(arts)
    assert all(arts[skill_id].quality == "上品" for skill_id in wanted)


def test_switch_art_message_shows_the_players_own_quality(state, content, world):
    """審查裁示 F11：改練的訊息寫玩家自己那一份的品質，不是全服登記的。"""
    _claim_whirlwind(world)
    state.player.arts = ["旋風腿"]
    state.player.art_quality["旋風腿"] = "上品"
    msgs = team.switch_art(state, content, world, "旋風腿")
    assert any("旋風腿" in m and "上品" in m for m in msgs)
    assert not any("下品" in m for m in msgs)


# ── 改練（功法庫 → 身上）：合成出來的武學只能靠它上身（開局送的兩門把兩個欄位都占了）──────────────


def _claim(world, name, kind="武學"):
    art = generate_from_name(name, kind, name, weights=LOW_ONLY)
    assert world.claim_skill_name(art)
    return art


def _wearing_one_and_holding_another(state, world):
    """身上穿著第一門武學（第一成），第二門在功法庫裡。"""
    worn, held = _claim(world, "旋風腿"), _claim(world, "沉山勢")
    state.player.member.wugong_id, state.player.member.wugong_level = worn.id, 1
    state.player.arts = [held.id]
    return worn, held


def test_switching_swaps_the_equipped_art_with_the_library_one(state, content, world):
    worn, held = _wearing_one_and_holding_another(state, world)
    msgs = team.switch_art(state, content, world, held.id)
    assert state.player.member.wugong_id == held.id
    assert state.player.arts == [worn.id]
    assert f"改練【{held.name}】" in "\n".join(msgs)


def test_switching_keeps_each_arts_level(state, content, world):
    """熟練度各自保留：換回來不用重練（設計文件六.4）。"""
    worn, held = _wearing_one_and_holding_another(state, world)
    state.player.member.wugong_level = 7  # 把身上這門練到第七成
    team.switch_art(state, content, world, held.id)
    assert state.player.member.wugong_level == 1  # 庫裡的那門沒練過，從第一成開始
    team.switch_art(state, content, world, worn.id)
    assert state.player.member.wugong_level == 7  # 換回來還是第七成
    assert state.player.art_levels[held.id] == 1


def test_switching_into_an_empty_slot_needs_no_swap(state, content, world):
    art = _claim(world, "玄淵經", "內功")
    assert state.player.member.neigong_id is None
    state.player.arts.append(art.id)  # 內功欄是空的，這門內功只在庫裡
    msgs = team.switch_art(state, content, world, art.id)
    assert state.player.member.neigong_id == art.id and state.player.arts == []
    assert len(msgs) == 1  # 沒有「你收起了…」那一句


def test_switching_something_not_in_the_library_is_refused(state, content, world):
    assert team.switch_art(state, content, world, "ghost") == ["你的功法庫裡沒有這一門。"]
    worn, _held = _wearing_one_and_holding_another(state, world)
    assert team.switch_art(state, content, world, worn.id) == ["你的功法庫裡沒有這一門。"]  # 身上正練的也不在庫裡
    assert state.player.member.wugong_id == worn.id and len(state.player.arts) == 1


def test_a_neigong_in_the_library_does_not_displace_a_wugong(state, content, world):
    worn, _held = _wearing_one_and_holding_another(state, world)
    neigong = _claim(world, "玄淵經", "內功")
    state.player.arts.append(neigong.id)
    team.switch_art(state, content, world, neigong.id)
    assert state.player.member.wugong_id == worn.id  # 武學沒被動到
    assert state.player.member.neigong_id == neigong.id


def test_old_saves_without_the_new_player_fields_still_load(state):
    from tianxia.state import PlayerState

    old = state.player.model_dump()
    for key in ("insights", "art_quality", "art_mastery", "naming"):
        old.pop(key)
    loaded = PlayerState.model_validate(old)
    assert (loaded.insights, loaded.art_quality, loaded.art_mastery, loaded.naming) == ([], {}, {}, None)


# ── 練成花心得（武學與成長 Task 5）────────────────────────────


def test_practice_costs_xinde_by_the_level_reached(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.member.wugong_level = 3
    state.player.stats["xinde"] = 10
    content.config.practice_injury_chance = 0.0
    msgs = team.practice(state, content, world, "武學", random.Random(0))
    assert state.player.member.wugong_level == 4
    assert state.player.stats["xinde"] == 7  # 第 3 成升第 4 成花 3
    assert "心得 -3" in msgs


def test_practice_without_enough_xinde_says_how_much_is_needed(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    state.player.member.wugong_level = 5
    state.player.stats["xinde"] = 2
    msgs = team.practice(state, content, world, "武學", random.Random(0))
    assert state.player.member.wugong_level == 5 and state.player.stats["xinde"] == 2
    assert "要 5 點心得，你只有 2 點" in msgs[0]
    assert "還差 3 點" in msgs[0]  # 不夠時直接說缺多少，新手才知道要去賺多少


def test_practice_price_is_the_level_reached_times_the_configured_rate(content):
    assert team.practice_price(content, 1) == 1
    assert team.practice_price(content, 9) == 9
    content.config.practice_xinde_per_level = 3
    assert team.practice_price(content, 4) == 12


def test_a_maxed_art_costs_nothing_and_says_so(state, content, world):
    state.player.member.neigong_id = "basic_breath"
    state.player.member.neigong_level = team.MAX_LEVEL
    state.player.stats["xinde"] = 0
    msgs = team.practice(state, content, world, "內功", random.Random(0))
    assert "練無可練" in msgs[0] and state.player.stats["xinde"] == 0


def test_practice_price_ignores_the_players_own_quality(state, content, world):
    """價錢只看第幾成：升品時成不變，品質越高越貴的話，玩家會先趁下品把成練滿再修練。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.member.wugong_level = 2
    state.player.art_quality["basic_fist"] = "上品"
    state.player.stats["xinde"] = 2
    content.config.practice_injury_chance = 0.0
    team.practice(state, content, world, "武學", random.Random(0))
    assert state.player.stats["xinde"] == 0 and state.player.member.wugong_level == 3


# ── 練得動嗎（武學與成長計畫 T11：機器人與主畫面提示共用同一個條件）──────────────


def test_can_practise_needs_a_worn_art_below_level_ten_and_enough_xinde(state, content):
    member = state.player.member
    state.player.stats["xinde"] = 100
    assert not team.can_practise(state, content, "武學")  # 欄位空著
    member.wugong_id, member.wugong_level = "basic_fist", 3
    assert team.can_practise(state, content, "武學")
    assert not team.can_practise(state, content, "內功")  # 另一欄還空著
    member.wugong_level = team.MAX_LEVEL
    assert not team.can_practise(state, content, "武學")  # 第十成練無可練
    member.wugong_level = 3
    state.player.stats["xinde"] = team.practice_price(content, 3) - 1
    assert not team.can_practise(state, content, "武學")
    state.player.stats["xinde"] = team.practice_price(content, 3)
    assert team.can_practise(state, content, "武學")


# ── 屬性點（武學與成長設計 6.2）：升級給點、自己分配，不再每級自動長 ───────────────


def test_the_players_stats_no_longer_grow_by_themselves(state, content, world):
    state.player.member.level = 10
    assert team.member_stats(state, content, world, "player")["str"] == state.player.stats["str"]


def test_each_level_gained_gives_a_stat_point(state, content, world):
    content.config.level_exp = 10  # 第 1 級升第 2 級要 10，第 2 級升第 3 級要 20
    msgs = team.add_team_exp(state, content, world, 30)
    assert state.player.member.level == 3 and state.player.stat_points == 2
    assert any("2 點屬性可以分配" in m for m in msgs)


def test_no_level_gained_gives_no_point_and_no_hint(state, content, world):
    content.config.level_exp = 100
    msgs = team.add_team_exp(state, content, world, 30)
    assert state.player.member.level == 1 and state.player.stat_points == 0
    assert not any("屬性" in m for m in msgs)


def test_points_per_level_come_from_the_config(state, content, world):
    content.config.level_exp = 10
    content.config.stat_points_per_level = 2
    team.add_team_exp(state, content, world, 10)
    assert state.player.member.level == 2 and state.player.stat_points == 2


def test_a_companions_level_ups_give_the_player_no_points(state, content, world):
    """屬性點只給玩家本人；同伴照舊是第 1 級的屬性加上每級成長。"""
    content.config.level_exp = 10
    state.player.member.level = content.config.max_level  # 本人滿級：只有同伴會升
    state.player.team = ["mate"]
    team.add_team_exp(state, content, world, 10)
    assert world.get_companion("mate").level == 2 and state.player.stat_points == 0
    mate = content.characters["mate"]
    assert team.member_stats(state, content, world, "mate")["str"] == pytest.approx(
        mate.stats["str"] + mate.growth["str"]
    )


# ── 四屬性的加成（武學與成長設計 6.1；計畫二 Task 2）──────────────────────────────


def test_strength_and_root_feed_everyones_boost(state, content, world):
    """人物資質設計 14.3：本人照舊；同伴吃他自己的臂力（武學）、根骨（內功），不吃你的共鳴。"""
    state.player.stats["str"], state.player.stats["con"], state.player.stats["good"] = 15, 10, 40
    boost = team.player_boost(state, content, world)
    assert boost.outer == pytest.approx(0.3) and boost.inner == pytest.approx(0.15)
    world.update_companion("mate", lambda p: setattr(p, "level", 11))  # 韓鐵：臂力 6＋0.3×10＝9、根骨 9
    state.player.team = ["mate"]
    mate = team.team_boosts(state, content, world)[1]
    assert (mate.outer, mate.inner, mate.factor) == (pytest.approx(0.12), pytest.approx(0.12), 1.0)  # 只有一門：不算搭配


def test_a_companions_own_pair_of_arts_is_matched_too(state, content, world):
    """同伴的天分就是他那一路武學（14.1）：他自己的內功與武學相剋也打折。掌法屬剛、粗淺吐納屬柔。"""
    def arm(progress):
        progress.wugong_id, progress.neigong_id = "palm", "basic_breath"

    world.update_companion("mate", arm)
    state.player.team = ["mate"]
    assert team.team_boosts(state, content, world)[1].factor == pytest.approx(1 - content.config.pairing_penalty)


def test_root_raises_the_hp_cap_without_refilling(state, content, world):
    member = state.player.member
    member.neili = 100.0
    base_cap = team.neili_cap(content, member.level)
    state.player.stats["con"] = 15
    now, cap = team.member_neili(content, member, team.con_of(state, content, world, PLAYER))
    assert cap == pytest.approx(base_cap * 1.3) and now == 100.0


def test_a_companions_hp_follows_his_own_root(state, content, world):
    """Review Focus 2：同伴的氣血上限照他自己的根骨（韓鐵第 1 級根骨 6，+3%）；本人的根骨不影響他；目前氣血不被補滿。"""
    state.player.stats["con"] = 15
    world.update_companion("mate", lambda p: setattr(p, "neili", 100.0))
    mate = world.get_companion("mate")
    assert team.con_of(state, content, world, "mate") == 6
    now, cap = team.member_neili(content, mate, team.con_of(state, content, world, "mate"))
    assert cap == round(team.neili_cap(content, mate.level) * 1.03) == 330 and now == 100.0  # 上限四捨五入成整數


def test_body_lightness_and_root_soften_a_fights_toll(state, content, world):
    content.config.encounter_neili_loss = {"落敗": 0.3}
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    state.player.stats["agi"], state.player.stats["con"] = 15, 15
    team.take_encounter_toll(state, content, world, "落敗")
    cap_plain = team.neili_cap(content, 1)
    lost_plain = cap_plain - team.member_neili(content, plain.player.member)[0]
    cap = team.neili_cap(content, 1, 15)
    lost = cap - team.member_neili(content, state.player.member, 15)[0]
    assert lost / cap == pytest.approx(lost_plain / cap_plain * 0.7, rel=0.05)
    assert state.player.member.injury < plain.player.member.injury


def _power_seen(call) -> float:
    """call() 裡第一次單次判定收到的我方威力（遊歷與勝算估計都經過 encounter.resolve_encounter）。"""
    seen: list[float] = []
    resolve = encounter.resolve_encounter

    def spy(power, difficulty, rng, shift=0.0, mods=None):
        seen.append(power)
        return resolve(power, difficulty, rng, shift=shift, mods=mods)

    with mock.patch.object(encounter, "resolve_encounter", side_effect=spy):
        call()
    return seen[0]


def test_a_fight_gives_each_of_them_their_own_boost(state, content, world):
    """計畫二 G12、人物資質設計 14.3：帶著同伴打一場，總威力＝吃本人加成的本人＋吃他自己臂力、根骨的同伴
    （韓鐵第 1 級臂力 6、根骨 6：各 +3%）；打一場與勝算估計一樣。"""
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "palm"))
    state.player.team = ["mate"]
    state.player.stats["str"], state.player.stats["con"] = 15, 10
    squad = content.squads["thug"]
    arts = team.team_arts(state, content, world)
    expected = (
        encounter.member_power(state.player.member, arts, squad.attribute, boost=encounter.Boost(outer=0.3, inner=0.15))
        + encounter.member_power(
            world.get_companion("mate"), arts, squad.attribute, boost=encounter.Boost(outer=0.03, inner=0.03),
        )
    )
    assert _power_seen(lambda: team.fight(state, content, world, "thug", random.Random(0))) == pytest.approx(expected)
    assert _power_seen(lambda: team.estimate(state, content, world, "thug")) == pytest.approx(expected)


def test_followers_fight_beside_the_player_with_their_own_strength():
    """計畫二 G1／F17：加成的清單跟陣容一樣長，部下照樣上陣、照樣算進勝算，吃自己模板的臂力（14.3）。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    s = game.state
    s.player.followers = ["follower_guan_spear", "follower_guan_crossbow"]
    s.player.stats["str"] = 15
    squad_id = next(iter(real.squads))
    attribute = real.squads[squad_id].attribute
    arts = team.team_arts(s, real, game.world)
    player = encounter.member_power(s.player.member, arts, attribute, boost=encounter.Boost(outer=0.3))
    rows = team.follower_rows(s, real)
    followers = [
        encounter.member_power(unit, arts, attribute, boost=team.follower_boost(real, follower))
        for unit, (_, follower) in zip(team.follower_units(s, real), rows, strict=True)
    ]
    assert player > 0 and len(followers) == 2 and all(power > 0 for power in followers)
    assert len(team.team_boosts(s, real, game.world)) == 3
    seen = _power_seen(lambda: team.estimate(s, real, game.world, squad_id))
    assert seen == pytest.approx(player + sum(followers))


def test_a_weak_follower_hits_a_little_softer_but_never_below_the_floor():
    """Review Focus 1：屬性比 5 低是負加成（弩手鄉勇臂力 4：−3%），再低也不會讓威力變成負的或 0。"""
    real = load_content(CONTENT_DIR)
    assert team.follower_boost(real, real.followers["follower_guan_crossbow"]).outer == pytest.approx(-0.03)
    weak = real.followers["follower_guan_crossbow"].model_copy(update={"stats": {"str": -100}})
    boost = team.follower_boost(real, weak)
    unit = Member(wugong_id=weak.wugong, wugong_level=weak.wugong_level)
    arts = {weak.wugong: team.resolve_art(weak.wugong, real, open_world())}
    assert encounter.member_power(unit, arts, boost=boost) > 0


def test_boosts_line_up_with_companions_and_followers():
    """Review Focus 5：帶同伴又帶部下，加成一人一份、順序同陣容：本人、同伴、部下。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    s = game.state
    first, second = "guanyu", "zhangfei"  # 真實內容的人物都是 locked；算加成只要他們在隊伍名單上
    s.player.team = [first, second]
    s.player.followers = ["follower_huang_strongman"]  # 太平力士：臂力 7（+6%）
    boosts = team.team_boosts(s, real, game.world)
    assert len(boosts) == 4 == len(team.team_participants(s, game.world)) + len(team.follower_units(s, real))
    assert team.mate_boost(s, real, game.world, first) != team.mate_boost(s, real, game.world, second)  # 兩人不同，對調才看得出來
    assert boosts[1] == team.mate_boost(s, real, game.world, first)
    assert boosts[2] == team.mate_boost(s, real, game.world, second)
    assert boosts[3].outer == pytest.approx(0.06) and boosts[3].inner == 0.0 and boosts[3].factor == 1.0


def test_a_companions_root_is_read_through_con_of(state, content, world, monkeypatch):
    """根骨只從 con_of 讀（Task 1 審查）：同伴的內功加成與一場的內傷、上限也跟著它走，不另外去翻 member_stats。"""
    monkeypatch.setattr(team, "con_of", lambda *_: 15.0)
    content.config.encounter_neili_loss = {"落敗": 0.3}
    state.player.team = ["mate"]
    assert team.mate_boost(state, content, world, "mate").inner == pytest.approx(0.3)
    team.take_encounter_toll(state, content, world, "落敗")
    loss = team.neili_cap(content, 1, 15) * 0.3  # 韓鐵第 1 級身法 5：不減；上限照根骨 15
    assert world.get_companion("mate").injury == pytest.approx(loss * content.config.injury_share * (1 - 0.3))


def test_dodge_chance_follows_the_players_body(state, content):
    for agi, chance in ((15, 0.2), (8, 0.06), (5, 0.0), (2, 0.0)):
        state.player.stats["agi"] = agi
        assert team.dodge_chance(state, content) == pytest.approx(chance)


def test_a_dodged_fight_is_settled_as_a_draw(state, content, world):
    """Review Focus 4：打翻江龍（難度 200）必敗；身法讓閃避必中時，結果就是僵持，之後的扣氣血、獎懲、回合都照僵持。"""
    content.config.dodge_per_point = 0.1
    state.player.stats["agi"] = 15
    result = team.fight(state, content, world, "boss", random.Random(0))
    assert (result.tier, result.dodged) == ("僵持", True)


def test_a_fight_without_a_dodge_chance_draws_the_same_randomness(state, content, world):
    """Review Focus 3：身法 5（機會 0）的人打一場，用掉的亂數跟直接單次判定一樣，落敗也不多擲。"""
    ours, theirs = random.Random(7), random.Random(7)
    result = team.fight(state, content, world, "boss", ours)  # 難度 200，必敗
    assert result.tier == "落敗" and not result.dodged
    assert result == encounter.resolve_encounter(result.our_power, result.difficulty, theirs)
    assert ours.getstate() == theirs.getstate()


def test_a_fight_with_the_dodge_turned_off_never_rolls_it(state, content, world):
    """最終審查 I1：dodge=False（劇情戰）就是閃避必中的人也不閃、也不多擲那一次亂數。"""
    content.config.dodge_per_point = 0.1
    state.player.stats["agi"] = 15  # 閃避機會 100%
    ours, theirs = random.Random(7), random.Random(7)
    result = team.fight(state, content, world, "boss", ours, dodge=False)  # 難度 200，必敗
    assert result.tier == "落敗" and not result.dodged
    assert result == encounter.resolve_encounter(result.our_power, result.difficulty, theirs)
    assert ours.getstate() == theirs.getstate()


def test_the_odds_label_ignores_the_dodge(state, content, world):
    """勝算是贏的機會；閃避只把落敗變僵持、不增加贏，所以按鈕上的勝算不含閃避（14.4）。"""
    before = team.estimate(state, content, world, "boss")
    content.config.dodge_per_point = 0.1
    state.player.stats["agi"] = 15
    assert team.estimate(state, content, world, "boss") == before


def test_a_companions_toll_uses_his_own_body_and_root(state, content, world):
    """同伴扣的那一份照他自己的身法、根骨（14.3）：韓鐵第 11 級身法 7（−6%）、根骨 9（內傷 −12%、上限 +12%）。"""
    content.config.encounter_neili_loss = {"落敗": 0.3}
    state.player.team = ["mate"]
    world.update_companion("mate", lambda p: setattr(p, "level", 11))
    team.take_encounter_toll(state, content, world, "落敗")
    loss = team.neili_cap(content, 11, 9) * 0.3 * (1 - 0.06)
    assert world.get_companion("mate").injury == pytest.approx(loss * content.config.injury_share * (1 - 0.12))


def test_a_practice_injury_starts_from_the_rooted_hp(state, content, world):
    """練功受傷從（吃了根骨的）目前氣血扣起：滿血 416 的人受傷 N 點剩 416 − N，不是先掉回 320。"""
    content.config.practice_injury_chance = 1.0
    state.player.stats["con"], state.player.stats["xinde"] = 15, 1000
    state.player.member.wugong_id = "basic_fist"
    team.practice(state, content, world, "武學", random.Random(0))
    member, hurt = state.player.member, content.config.practice_injury_amount
    assert team.member_neili(content, member, 15) == pytest.approx((416 - hurt, 416))


# ── 計畫二 Task 2 修正第一輪：根骨只從一處讀、加成的乘數只有一種寫法 ──────────────────────


def test_the_players_root_follows_the_key_not_the_member_object(state, content, world):
    """con_of 認的是名冊的 key，不是物件本身：拿玩家 Member 的複本照樣吃本人的根骨，同伴照他自己的根骨。"""
    state.player.stats["con"] = 15
    copy = state.player.member.model_copy(deep=True)
    assert team.con_of(state, content, world, PLAYER) == 15
    assert team.member_neili(content, copy, team.con_of(state, content, world, PLAYER))[1] == 416
    assert team.con_of(state, content, world, "mate") == 6


def test_the_players_root_is_read_in_one_place(state, content, world, monkeypatch):
    """本人的根骨只從 con_of 讀：內功的加成、一場的內傷都跟著它走（不再各自翻 stats）。"""
    content.config.encounter_neili_loss = {"落敗": 0.3}
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    monkeypatch.setattr(team, "con_of", lambda *_: 15.0)
    assert team.player_boost(state, content, world).inner == pytest.approx(0.3)
    team.take_encounter_toll(state, content, world, "落敗")
    assert state.player.member.injury < plain.player.member.injury


def test_the_stat_factor_is_one_plus_the_bonus_and_never_below_the_floor(content):
    """「1＋加成、至少 0.1」只有一種寫法：氣血上限、修練機率、探索比重都用它。"""
    assert team.stat_factor(content, 15) == pytest.approx(1.3)
    assert team.stat_factor(content, team.BASE_STAT) == 1.0
    assert team.stat_factor(content, -100) == encounter.BOOST_FLOOR


def test_the_hp_cap_is_a_whole_number_at_any_root(content):
    """根骨 6：320 × 1.03 ＝ 329.6，上限一律四捨五入成 330，每個呼叫端拿到、畫面寫出來的都是同一個數。"""
    assert team.neili_cap(content, 1, 6) == 330
    assert team.neili_cap(content, 1) == 320


# ── 計畫二 Task 3：內外搭配與正邪共鳴 ──────────────────────────────────────────────


def _art(name, kind, attribute, lean="無"):
    return generate_from_name(name, kind, name, attribute=attribute).model_copy(update={"lean": lean})


def test_pairing_rewards_the_same_attribute_and_punishes_a_countering_pair(content):
    assert team.pairing(content, _art("甲拳", "武學", "剛"), _art("甲功", "內功", "剛")) == pytest.approx(1.2)
    assert team.pairing(content, _art("乙拳", "武學", "剛"), _art("乙功", "內功", "柔")) == pytest.approx(0.8)
    assert team.pairing(content, _art("丙拳", "武學", "剛"), _art("丙功", "內功", "快")) == 1.0
    assert team.pairing(content, _art("丁拳", "武學", "剛"), None) == 1.0
    assert team.pairing(content, None, _art("戊功", "內功", "剛")) == 1.0


def test_a_negative_pairing_bonus_is_held_at_the_floor_like_the_penalty(content):
    """相同屬性那一支也夾在下限：設定寫錯（加成是負的）也不會讓整個人的乘數變成負的。"""
    content.config.pairing_bonus = -5.0
    same = team.pairing(content, _art("甲拳", "武學", "剛"), _art("甲功", "內功", "剛"))
    assert same == encounter.BOOST_FLOOR


def test_resonance_follows_the_matching_name_and_caps(state, content):
    good = _art("正拳", "武學", "陽", "正")
    state.player.stats["good"], state.player.stats["evil"] = 30, 100
    assert team.resonance(state, content, good) == pytest.approx(1.15)
    state.player.stats["good"] = 100
    assert team.resonance(state, content, good) == pytest.approx(1.2)
    assert team.resonance(state, content, _art("平拳", "武學", "陽")) == 1.0
    assert team.resonance(state, content, _art("邪拳", "武學", "陰", "邪")) == pytest.approx(1.2)
    assert team.resonance(state, content, None) == 1.0


def test_the_wrong_name_gives_no_resonance_and_never_a_penalty(state, content):
    """用了反的不會反噬（設計 7.4）：滿身惡名的人使正派武學只是沒有共鳴；名聲是負的也不會變成打折。"""
    state.player.stats["good"], state.player.stats["evil"] = 0, 100
    assert team.resonance(state, content, _art("正拳", "武學", "陽", "正")) == 1.0
    state.player.stats["good"] = -50
    assert team.resonance(state, content, _art("正拳", "武學", "陽", "正")) == 1.0


def _register(world, name, kind, attribute, lean="無"):
    art = _art(name, kind, attribute, lean)
    assert world.claim_skill_name(art)
    return art


def test_pairing_and_resonance_can_never_push_the_factor_under_the_floor(state, content, world):
    """設定把相剋的打折調到比 100% 還大，搭配也只到下限（encounter.BOOST_FLOOR），整個人的乘數不會變成負的；
    共鳴只往上加，名聲是負的也不會把乘數往下拉。"""
    content.config.pairing_penalty = 5.0
    wugong = _register(world, "鐵拳", "武學", "剛", "正")
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, "basic_breath"  # 剛克柔
    state.player.stats["good"] = -500
    assert team.pairing(content, wugong, team.resolve_art("basic_breath", content, world)) == encounter.BOOST_FLOOR
    assert team.player_boost(state, content, world).factor == pytest.approx(encounter.BOOST_FLOOR)
    state.player.stats["good"] = 100  # 共鳴封頂 1.2：搭配的下限 × 1.2，仍是正的
    assert team.player_boost(state, content, world).factor == pytest.approx(encounter.BOOST_FLOOR * 1.2)


def test_the_players_factor_is_pairing_times_both_resonances(state, content, world):
    """計畫二 G12：正派的合成武學＋同屬性的內功＋善名 40 → 整個人乘 1.2（搭配）× 1.2（共鳴）。"""
    wugong = _register(world, "清風拳", "武學", "柔", "正")
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, "basic_breath"  # 內功也是柔
    state.player.stats["good"] = 40
    boost = team.player_boost(state, content, world)
    assert boost.factor == pytest.approx(1.2 * 1.2)
    state.player.stats["good"] = 0  # 名聲掉了，共鳴跟著掉；搭配還在
    assert team.player_boost(state, content, world).factor == pytest.approx(1.2)


def test_both_arts_resonate_each_on_its_own_name(state, content, world):
    """內功與武學都是正派：兩份共鳴各算各的；一正一邪各吃各的名聲。"""
    wugong = _register(world, "清風拳", "武學", "剛", "正")
    neigong = _register(world, "烈焰功", "內功", "快", "邪")  # 剛與快互不相剋、也不同屬性：搭配 1.0
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, neigong.id
    state.player.stats["good"], state.player.stats["evil"] = 20, 40
    assert team.player_boost(state, content, world).factor == pytest.approx(1.1 * 1.2)


def test_a_fight_gives_the_resonance_to_the_player_only(state, content, world):
    """計畫二 G12、人物資質設計 14.3：帶著同伴打一場，總威力＝乘了 1.44（搭配×共鳴）的本人＋只吃自己屬性、
    沒有共鳴的同伴（打一場與勝算估計一樣）。"""
    wugong = _register(world, "清風拳", "武學", "柔", "正")
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, "basic_breath"
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "palm"))
    state.player.team = ["mate"]
    state.player.stats["good"] = 40
    squad = content.squads["thug"]
    arts = team.team_arts(state, content, world)
    plain = encounter.member_power(state.player.member, arts, squad.attribute, boost=encounter.Boost())
    mate = encounter.member_power(
        world.get_companion("mate"), arts, squad.attribute, boost=encounter.Boost(outer=0.03, inner=0.03),
    )
    expected = plain * 1.2 * 1.2 + mate
    assert plain > 0 and mate > 0 and expected > plain + mate
    assert _power_seen(lambda: team.fight(state, content, world, "thug", random.Random(0))) == pytest.approx(expected)
    assert _power_seen(lambda: team.estimate(state, content, world, "thug")) == pytest.approx(expected)


def test_followers_fight_beside_a_resonating_player_without_the_factor():
    """計畫二 G12／F17：部下照樣上陣，只是不吃本人的搭配與共鳴。真實內容、兩個部下。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    s = game.state
    wugong, neigong = _art("清風拳", "武學", "柔", "正"), _art("清風功", "內功", "柔")
    assert game.world.claim_skill_name(wugong) and game.world.claim_skill_name(neigong)
    s.player.member.wugong_id, s.player.member.neigong_id = wugong.id, neigong.id
    s.player.followers = ["follower_guan_spear", "follower_guan_crossbow"]
    s.player.stats["good"] = 40
    squad_id = next(iter(real.squads))
    attribute = real.squads[squad_id].attribute
    arts = team.team_arts(s, real, game.world)
    plain = encounter.member_power(s.player.member, arts, attribute, boost=encounter.Boost())
    rows = team.follower_rows(s, real)
    followers = [  # 部下吃自己的臂力（矛手 +3%、弩手 −3%），但不吃搭配與共鳴
        encounter.member_power(unit, arts, attribute, boost=team.follower_boost(real, follower))
        for unit, (_, follower) in zip(team.follower_units(s, real), rows, strict=True)
    ]
    assert plain > 0 and len(followers) == 2 and all(power > 0 for power in followers)
    boosts = team.team_boosts(s, real, game.world)
    assert [b.factor for b in boosts] == [pytest.approx(1.2 * 1.2), 1.0, 1.0]
    seen = _power_seen(lambda: team.estimate(s, real, game.world, squad_id))
    assert seen == pytest.approx(plain * 1.2 * 1.2 + sum(followers))


# ── 回合演出的我方陣容（計畫三 Task 1、G7）──────────────────────


def test_the_narrated_lineup_is_the_player_then_the_companions_with_their_arts(state, content, world):
    """回合演出的陣容：本人在前、再來是帶著出戰的同伴，各報身上那門武學（名字與屬性）；沒學武學的是 None。"""
    state.player.member.wugong_id = "basic_fist"
    state.player.team = ["mate", "pupil"]
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    lineup = team.fighters(state, content, world)
    assert [(f.name, f.art, f.attribute) for f in lineup] == [
        ("沈浪", "粗淺拳腳", "實"), ("韓鐵", "長拳", "剛"), ("小六", None, None),
    ]


def test_the_narrated_lineup_includes_the_followers():
    """部下也上陣（F17）：照模板的稱呼與武學排在同伴後面，跟算威力的 _fighters 是同一份名冊。真實內容、兩個部下。"""
    real = load_content(CONTENT_DIR)
    real.config.auto_open_first_season = True
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    game = Game.new(real, "甲", rng=random.Random(0))
    s = game.state
    s.player.followers = ["follower_guan_spear", "follower_guan_crossbow"]
    lineup = team.fighters(s, real, game.world)
    members, _, _ = team._fighters(s, real, game.world)
    assert len(lineup) == len(members) == 3
    assert lineup[0].name == "甲"
    for fighter, fid in zip(lineup[1:], s.player.followers, strict=True):
        follower = real.followers[fid]
        art = real.skills[follower.wugong]
        assert (fighter.name, fighter.art, fighter.attribute) == (follower.name, art.name, art.attribute)


def test_a_full_team_says_so_in_chinese_only(state):
    """隊伍滿了的那句話是給玩家看的：不能夾英文字（原本寫成「先讓someone離隊」）。"""
    state.player.team = [f"mate{i}" for i in range(team.MAX_TEAM_COMPANIONS)]
    msgs = team.add_to_team(state, "one_more")
    assert msgs and "一位夥伴" in msgs[0]
    assert not any(ch.isascii() and ch.isalpha() for ch in msgs[0])


# ── 武學的功效（武學與成長設計 13.2、13.4；計畫六 Task 3）：換算成遭遇戰的數字 ──────────────


def _trait_art(world, name, attribute, trait_list, special=None, kind="武學"):
    art = generate_from_name(name, kind, name, attribute=attribute).model_copy(
        update={"origin": "fused", "traits": trait_list, "special": special},
    )
    world.claim_skill_name(art)
    return art


def _wear(state, world, *arts, quality="下品"):
    for art in arts:
        slot = "neigong_id" if art.kind == "內功" else "wugong_id"
        setattr(state.player.member, slot, art.id)
        state.player.art_quality[art.id] = quality


class _CountingRandom(random.Random):
    """數 random() 被叫了幾次：uniform（運氣）與閃避都是一次 random()。"""

    def __init__(self, seed):
        super().__init__(seed)
        self.draws = 0

    def random(self):
        self.draws += 1
        return super().random()


def test_stacked_traits_stop_at_their_caps(state, content, world):
    """Review Focus 2：兩門絕學、三格都是同一個功效＝18 層，數字停在上限。"""
    outer = _trait_art(world, "全快拳", "快", ["快", "快", "快"])
    inner = _trait_art(world, "全快功", "快", ["快", "快", "快"], kind="內功")
    _wear(state, world, outer, inner, quality="絕學")
    mods = team.trait_mods(content, traits.loadout(state, content, world))
    assert mods.big_win_cut == pytest.approx(0.2)


def test_every_general_trait_stops_at_its_cap_and_nothing_goes_negative(state, content, world):
    """八個一般功效各疊 18 層：每個數字停在上限，運氣的倍數、門檻、扣氣血的比例都不會變成負的。"""
    for attribute in ("快", "慢", "剛", "柔", "陽", "陰", "虛", "實"):
        outer = _trait_art(world, f"{attribute}拳", attribute, [attribute] * 3)
        inner = _trait_art(world, f"{attribute}功", attribute, [attribute] * 3, kind="內功")
        _wear(state, world, outer, inner, quality="絕學")
        lo = traits.loadout(state, content, world)
        for trait in content.traits.general:
            if trait.attribute == attribute:
                assert traits.amount(content, lo, trait.hook) == pytest.approx(trait.cap)
        mods = team.trait_mods(content, lo)
        assert mods.luck_scale >= 0 and 0 <= mods.big_win_cut <= 0.2 and 0 <= mods.difficulty_cut <= 0.2


def test_steady_and_risky_cancel_out(state, content, world):
    """Review Focus 3：穩與險都疊到上限，運氣的起伏回到原樣，不會變成負的。"""
    outer = _trait_art(world, "穩拳", "慢", ["慢", "慢", "慢"])
    inner = _trait_art(world, "險功", "虛", ["虛", "虛", "虛"], kind="內功")
    _wear(state, world, outer, inner, quality="絕學")
    assert team.trait_mods(content, traits.loadout(state, content, world)).luck_scale == pytest.approx(1.0)


def test_steady_alone_narrows_the_luck_and_risky_alone_widens_it(state, content, world):
    steady = _trait_art(world, "穩拳", "慢", ["慢", "慢", "慢"])
    _wear(state, world, steady)  # 下品三層：穩 45%
    assert team.trait_mods(content, traits.loadout(state, content, world)).luck_scale == pytest.approx(0.55)
    risky = _trait_art(world, "險拳", "虛", ["虛", "虛"])
    _wear(state, world, risky)  # 下品兩層：險 30%
    assert team.trait_mods(content, traits.loadout(state, content, world)).luck_scale == pytest.approx(1.3)


def test_the_special_mods_come_from_the_specials(state, content, world):
    art = _trait_art(world, "借力拳", "剛", ["剛"], special="jieli")
    _wear(state, world, art)
    mods = team.trait_mods(content, traits.loadout(state, content, world))
    assert mods.power_add == pytest.approx(0.05) and not mods.double_luck
    art = _trait_art(world, "連環拳", "剛", ["剛"], special="lianhuan")
    _wear(state, world, art)
    mods = team.trait_mods(content, traits.loadout(state, content, world))
    assert mods.double_luck and mods.power_add == 0.0


def test_no_traits_means_the_same_roll_as_before(state, content, world):
    """Review Focus 1：沒有武學的人換算出來是空的 Mods——encounter 那一條測試證明空的 Mods 跟以前一模一樣；
    帶了武學、但沒有連環的人，一場仗也只擲一次運氣。"""
    state.player.member.wugong_id = state.player.member.neigong_id = None
    assert team.trait_mods(content, traits.loadout(state, content, world)) == encounter.Mods()
    state.player.member.wugong_id = "basic_fist"  # 屬實：只有【厚】，不碰運氣
    assert not team.trait_mods(content, traits.loadout(state, content, world)).double_luck


def test_a_starter_who_never_double_rolls_draws_exactly_what_a_plain_fight_draws(state, content, world):
    """F12：開局的基礎武學帶【厚】【化勁】，但這兩個都不碰運氣、也不碰閃避——沒有連環的人，一場仗用掉的亂數
    （次數與整個亂數狀態）跟沒有功效時一模一樣：打得贏的一場擲一次運氣；必敗的一場擲一次運氣，加上閃避那一次。"""
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    assert traits.loadout(state, content, world).layers  # 確實帶著功效
    for seed in range(12):
        for squad_id, agi in (("thug", 5), ("boss", 5), ("boss", 15)):
            state.player.stats["agi"] = agi
            ours, theirs = _CountingRandom(seed), _CountingRandom(seed)
            result = team.fight(state, content, world, squad_id, ours)
            plain = encounter.resolve_encounter(result.our_power, result.difficulty, theirs)
            plain = encounter.dodge(plain, team.dodge_chance(state, content), theirs)
            assert result == plain, (seed, squad_id, agi)
            assert ours.draws == theirs.draws and ours.getstate() == theirs.getstate()
    # 數字本身釘住：沒有閃避機會的人一場一次；必敗而有閃避機會的一場兩次（運氣＋閃避）
    state.player.stats["agi"] = 5
    for squad_id in ("thug", "boss"):
        rng = _CountingRandom(3)
        team.fight(state, content, world, squad_id, rng)
        assert rng.draws == 1, squad_id
    state.player.stats["agi"] = 15
    rng = _CountingRandom(3)
    assert team.fight(state, content, world, "boss", rng).tier in ("落敗", "僵持") and rng.draws == 2


def test_double_luck_is_the_only_trait_that_rolls_the_luck_twice(state, content, world):
    state.player.stats["agi"] = 5  # 沒有閃避
    art = _trait_art(world, "連環拳", "剛", ["剛"], special="lianhuan")
    _wear(state, world, art)
    rng = _CountingRandom(1)
    team.fight(state, content, world, "thug", rng)
    assert rng.draws == 2


def test_guard_turns_a_loss_into_a_draw_before_any_dodge(state, content, world):
    """護命（13.4）：落敗一律改判僵持，蓋過身法閃避，也就不擲閃避的亂數。"""
    art = _trait_art(world, "護身拳", "實", ["實"], special="huming")
    _wear(state, world, art)
    state.player.stats["agi"] = 15
    rng = random.Random(0)
    result = team.fight(state, content, world, "boss", rng)
    assert (result.tier, result.guarded, result.dodged) == ("僵持", True, False)


def test_guard_is_checked_before_the_dodge_and_leaves_the_dodge_roll_unspent(state, content, world):
    """閃避必中（身法 15、每點 10%）也是護命先收：guarded 而不是 dodged；亂數只用掉運氣那一次，沒有擲閃避。"""
    content.config.dodge_per_point = 0.1
    state.player.stats["agi"] = 15
    art = _trait_art(world, "護身拳", "實", ["實"], special="huming")
    _wear(state, world, art)
    rng = _CountingRandom(7)
    result = team.fight(state, content, world, "boss", rng)  # 難度 200，必敗
    assert (result.tier, result.guarded, result.dodged) == ("僵持", True, False) and rng.draws == 1


def test_guard_does_nothing_in_a_story_battle_that_turns_the_dodge_off(state, content, world):
    """F1：劇情戰（dodge=False）僵持也算敗，護命改判成僵持只會自相矛盾；跟閃避一樣不動，也不多擲亂數。"""
    art = _trait_art(world, "護身拳", "實", ["實"], special="huming")
    _wear(state, world, art)
    ours, theirs = _CountingRandom(7), _CountingRandom(7)
    result = team.fight(state, content, world, "boss", ours, dodge=False)
    assert result.tier == "落敗" and not result.guarded and not result.dodged
    assert result == encounter.resolve_encounter(result.our_power, result.difficulty, theirs)
    assert ours.draws == theirs.draws == 1


def test_guard_leaves_a_win_alone(state, content, world):
    art = _trait_art(world, "護身拳", "實", ["實"], special="huming")
    _wear(state, world, art)
    result = team.fight(state, content, world, "thug", random.Random(0), difficulty=1)  # 難度 1，一定贏
    assert result.tier in team.WIN_TIERS and not result.guarded


def test_a_fight_passes_the_traits_to_the_judgement(state, content, world):
    """打一場把功效換算成的 Mods 交給單次判定：破甲（下品一層 4%）。"""
    art = _trait_art(world, "破甲拳", "剛", ["剛"])
    _wear(state, world, art)
    seen = []
    resolve = encounter.resolve_encounter

    def spy(power, difficulty, rng, shift=0.0, mods=None):
        seen.append(mods)
        return resolve(power, difficulty, rng, shift=shift, mods=mods)

    with mock.patch.object(encounter, "resolve_encounter", side_effect=spy):
        team.fight(state, content, world, "thug", random.Random(0))
    assert seen[0].difficulty_cut == pytest.approx(0.04)


def test_soft_and_still_cut_the_toll_and_the_injury(state, content, world):
    content.config.encounter_neili_loss = {"落敗": 0.3}
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    art = _trait_art(world, "化勁掌", "柔", ["柔", "柔", "柔"], special="budong")
    _wear(state, world, art)  # 下品三層：化勁 30%
    team.take_encounter_toll(state, content, world, "落敗")
    cap = team.member_neili(content, state.player.member, team.con_of(state, content, world, PLAYER))[1]
    lost = cap - state.player.member.neili
    plain_lost = cap - plain.player.member.neili
    assert lost == pytest.approx(plain_lost * 0.7) and state.player.member.injury == 0


def test_soft_alone_cuts_the_injury_with_the_toll(state, content, world):
    """化勁少扣的氣血，變成內傷的那一部分也跟著少（內傷是損失的固定幾成）。"""
    content.config.encounter_neili_loss = {"落敗": 0.3}
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    art = _trait_art(world, "化勁掌", "柔", ["柔", "柔", "柔"])
    _wear(state, world, art)
    team.take_encounter_toll(state, content, world, "落敗")
    assert state.player.member.injury == pytest.approx(plain.player.member.injury * 0.7)


def test_still_cuts_only_the_injury_not_the_hp(state, content, world):
    content.config.encounter_neili_loss = {"落敗": 0.3}
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    art = _trait_art(world, "不動拳", "剛", ["剛"], special="budong")
    _wear(state, world, art)
    msgs = team.take_encounter_toll(state, content, world, "落敗")
    assert state.player.member.injury == 0 and not any(m.startswith("內傷") for m in msgs)
    assert state.player.member.neili == pytest.approx(plain.player.member.neili)


def test_the_toll_cut_only_touches_the_player_not_the_companions(state, content, world):
    content.config.encounter_neili_loss = {"落敗": 0.3}
    state.player.team = ["mate"]
    plain = state.model_copy(deep=True)
    team.take_encounter_toll(plain, content, world, "落敗")
    mate_plain = world.get_companion("mate").injury
    world.update_companion("mate", lambda p: setattr(p, "injury", 0.0))
    art = _trait_art(world, "化勁掌", "柔", ["柔", "柔", "柔"])
    _wear(state, world, art)
    team.take_encounter_toll(state, content, world, "落敗")
    assert world.get_companion("mate").injury == pytest.approx(mate_plain)


def test_thick_raises_the_players_wounded_floor(state, content, world):
    art = _trait_art(world, "厚土拳", "實", ["實", "實", "實"])
    _wear(state, world, art)
    state.player.member.neili = 0.0
    assert team.team_conditions(state, content, world)[0] == pytest.approx(encounter.CONDITION_FLOOR + 0.15)


def test_thick_does_not_change_a_healthy_or_a_companions_condition(state, content, world):
    art = _trait_art(world, "厚土拳", "實", ["實", "實", "實"])
    _wear(state, world, art)
    state.player.team = ["mate"]
    world.update_companion("mate", lambda p: setattr(p, "neili", 0.0))
    state.player.member.neili = None  # 滿血
    own, mate = team.team_conditions(state, content, world)
    assert own == 1.0 and mate == pytest.approx(encounter.CONDITION_FLOOR)


def test_the_odds_include_roll_traits_but_not_the_guard(state, content, world):
    """勝算含會改到贏的機會的功效（破甲），不含護命（只把落敗變僵持）。"""
    art = _trait_art(world, "破甲拳", "剛", ["剛"])
    _wear(state, world, art)
    seen = []
    resolve = encounter.resolve_encounter

    def spy(power, difficulty, rng, shift=0.0, mods=None):
        seen.append(mods)
        return resolve(power, difficulty, rng, shift=shift, mods=mods)

    with mock.patch.object(encounter, "resolve_encounter", side_effect=spy):
        team.estimate(state, content, world, "thug")
    assert seen and all(m is not None and m.difficulty_cut == pytest.approx(0.04) for m in seen)

    # 同一門武學換上護命（登記成另一個名字，威力與功效都不變）：每一個難度的勝算都不變，必敗的不會變成「難分勝負」
    guarded = art.model_copy(update={"id": "護身破甲拳", "name": "護身破甲拳", "special": "huming"})
    world.claim_skill_name(guarded)
    words = {d: team.estimate(state, content, world, "thug", difficulty=d) for d in range(0, 60, 3)}
    _wear(state, world, guarded)
    assert {d: team.estimate(state, content, world, "thug", difficulty=d) for d in words} == words
    assert team.estimate(state, content, world, "boss") == "必敗"  # 護命若算進勝算，這裡會變成「難分勝負」
    assert len(set(words.values())) > 2  # 掃過的難度橫跨幾種說法，上面的比較才不是同一個字比到底


def test_heal_fraction_heals_up_to_the_ceiling_and_says_how_much(state, content, world):
    content.config.encounter_neili_loss = {"落敗": 0.3}
    team.take_encounter_toll(state, content, world, "落敗")  # 掉氣血、累積內傷
    member = state.player.member
    con = team.con_of(state, content, world, PLAYER)
    now, cap = team.member_neili(content, member, con)
    msgs = team.heal_fraction(state, content, world, 0.02)
    after, _ = team.member_neili(content, member, con)
    assert after == pytest.approx(now + cap * 0.02) and msgs == [f"氣血 +{cap * 0.02:.0f}"]


def test_heal_fraction_stops_at_the_ceiling_and_leaves_full_as_none(state, content, world):
    """回到天花板（上限 − 內傷）就是「滿」：記成 None（member_neili 的約定），升級、根骨變高時才跟著滿；補不到 1 點不寫。"""
    member = state.player.member
    member.injury = 50.0
    con = team.con_of(state, content, world, PLAYER)
    ceiling = team.neili_ceiling(content, member, con)
    member.neili = ceiling - 3.0
    msgs = team.heal_fraction(state, content, world, 0.5)
    assert member.neili is None and msgs == ["氣血 +3"]
    assert team.heal_fraction(state, content, world, 0.5) == []  # 已經滿了：什麼都不寫
    assert member.neili is None
    member.neili = ceiling - 5.0
    assert team.heal_fraction(state, content, world, 0.4 / 320) == []  # 回了 0.4 點：回不到 1 點不寫
    assert member.neili == pytest.approx(ceiling - 4.6)  # 但氣血照樣回了
