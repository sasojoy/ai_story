"""門下與隊伍：武學與成長 Task 3 加進來的部分——基礎武學照品質解析、每個人自己那一份的品質。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import encounter, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name
from tianxia.state import PLAYER

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


def test_strength_and_root_feed_the_players_boost_only(state, content, world):
    state.player.stats["str"], state.player.stats["con"] = 15, 10
    boost = team.player_boost(state, content, world)
    assert boost.outer == pytest.approx(0.3) and boost.inner == pytest.approx(0.15)
    state.player.team = [next(cid for cid, ch in content.characters.items() if ch.kind == "recruitable")]
    boosts = team.team_boosts(state, content, world)
    assert len(boosts) == 2 and boosts[0].outer > 0
    assert (boosts[1].outer, boosts[1].inner, boosts[1].factor) == (0.0, 0.0, 1.0)  # 同伴不吃玩家的加成


def test_root_raises_the_hp_cap_without_refilling(state, content, world):
    member = state.player.member
    member.neili = 100.0
    base_cap = team.neili_cap(content, member.level)
    state.player.stats["con"] = 15
    now, cap = team.member_neili(content, member, team.con_of(state, PLAYER))
    assert cap == pytest.approx(base_cap * 1.3) and now == 100.0


def test_a_companions_hp_ignores_the_players_root(state, content, world):
    state.player.stats["con"] = 15
    mate = world.get_companion("mate")
    assert team.con_of(state, "mate") == team.BASE_STAT
    assert team.member_neili(content, mate, team.con_of(state, "mate"))[1] == team.neili_cap(content, mate.level)


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

    def spy(power, difficulty, rng):
        seen.append(power)
        return resolve(power, difficulty, rng)

    with mock.patch.object(encounter, "resolve_encounter", side_effect=spy):
        call()
    return seen[0]


def test_a_fight_gives_the_boost_to_the_player_and_not_to_the_companion(state, content, world):
    """計畫二 G12：帶著同伴打一場，總威力＝吃加成的本人＋不吃加成的同伴（打一場與勝算估計一樣）。"""
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "palm"))
    state.player.team = ["mate"]
    state.player.stats["str"], state.player.stats["con"] = 15, 10
    squad = content.squads["thug"]
    arts = team.team_arts(state, content, world)
    expected = (
        encounter.member_power(state.player.member, arts, squad.attribute, boost=encounter.Boost(outer=0.3, inner=0.15))
        + encounter.member_power(world.get_companion("mate"), arts, squad.attribute)
    )
    assert _power_seen(lambda: team.fight(state, content, world, "thug", random.Random(0))) == pytest.approx(expected)
    assert _power_seen(lambda: team.estimate(state, content, world, "thug")) == pytest.approx(expected)


def test_followers_still_fight_beside_a_boosted_player_without_the_boost():
    """計畫二 G1／F17：加成的清單跟陣容一樣長，部下照樣上陣、照樣算進勝算，只是不吃本人的加成。"""
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
    followers = [encounter.member_power(f, arts, attribute) for f in team.follower_units(s, real)]
    assert player > 0 and len(followers) == 2 and all(power > 0 for power in followers)
    assert len(team.team_boosts(s, real, game.world)) == 3
    seen = _power_seen(lambda: team.estimate(s, real, game.world, squad_id))
    assert seen == pytest.approx(player + sum(followers))


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
    """con_of 認的是名冊的 key，不是物件本身：拿玩家 Member 的複本照樣吃本人的根骨，同伴照基準。"""
    state.player.stats["con"] = 15
    copy = state.player.member.model_copy(deep=True)
    assert team.con_of(state, PLAYER) == 15
    assert team.member_neili(content, copy, team.con_of(state, PLAYER))[1] == 416
    assert team.con_of(state, "mate") == team.BASE_STAT


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


def test_a_fight_gives_the_pairing_and_resonance_to_the_player_only(state, content, world):
    """計畫二 G12：帶著同伴打一場，總威力＝乘了 1.44 的本人＋沒乘的同伴（打一場與勝算估計一樣）。"""
    wugong = _register(world, "清風拳", "武學", "柔", "正")
    state.player.member.wugong_id, state.player.member.neigong_id = wugong.id, "basic_breath"
    world.update_companion("mate", lambda p: setattr(p, "wugong_id", "palm"))
    state.player.team = ["mate"]
    state.player.stats["good"] = 40
    squad = content.squads["thug"]
    arts = team.team_arts(state, content, world)
    plain = encounter.member_power(state.player.member, arts, squad.attribute, boost=encounter.Boost())
    mate = encounter.member_power(world.get_companion("mate"), arts, squad.attribute)
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
    followers = [encounter.member_power(f, arts, attribute) for f in team.follower_units(s, real)]
    assert plain > 0 and len(followers) == 2 and all(power > 0 for power in followers)
    boosts = team.team_boosts(s, real, game.world)
    assert [b.factor for b in boosts] == [pytest.approx(1.2 * 1.2), 1.0, 1.0]
    seen = _power_seen(lambda: team.estimate(s, real, game.world, squad_id))
    assert seen == pytest.approx(plain * 1.2 * 1.2 + sum(followers))
