"""五項屬性（屬性與跨季架構 v2 第三節；第 ② 階段第 1 批，tianxia/attrset.py）：開關加開季章、配比回溯、送點、舊鍵對應、新的檢定換算。"""
from __future__ import annotations

import random

import pytest
import tempfile
from pathlib import Path

from conftest import real_content
from tianxia import attrset, rules, team
from tianxia.engine import Game
from tianxia.models import Check, Effect
from tianxia.sqlite_world import open_world


def _game(on: bool = True, profile: str = "season21") -> Game:
    c = real_content(profile)
    c.config.attributes.v2.enabled = on
    c.config.auto_open_first_season = True
    world = open_world(Path(tempfile.mkdtemp(prefix="attrs-")) / "tianxia.db")
    g = Game.new(c, "沈浪", rng=random.Random(0), world=world)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    return g


def _grow(g: Game, preset: str, split: dict | None = None) -> list[str]:
    """量不同配比：一季只能挑一次（開季準備卡），測試要換一套就先清掉再挑。"""
    g.state.player.growth_preset = None
    return g.pick_growth(preset, split)


def _level(g: Game, level: int) -> None:
    g.state.player.member.level = level


def test_the_season_stamp_turns_it_on_and_the_switch_alone_does_not():
    g = _game(True)
    assert g.state.world.attrs_v2 and attrset.on(g.content, g.state.world)
    off = _game(False)
    assert not attrset.on(off.content, off.state.world)
    off.content.config.attributes.v2.enabled = True  # 季中打開主機開關：正在跑的季沒蓋章，照舊
    assert not attrset.on(off.content, off.state.world)


def test_values_grow_by_the_preset_and_a_later_pick_is_retroactive():
    g = _game()
    c, v2 = g.content, g.content.config.attributes.v2
    _level(g, 11)
    balanced = attrset.values(g.state, c)
    assert balanced == {k: v2.base + 10 * 2 for k in v2.keys}  # 還沒挑：照均衡長
    _grow(g, "warrior")
    assert attrset.value(g.state, c, "str") == v2.base + 10 * 4  # 回溯：照現在的等級整條重算
    assert attrset.value(g.state, c, "int") == v2.base + 10 * 1
    names = [row[0] for row in g.status_data()["attrs"]]
    assert names == ["武力", "統御", "悟性", "身法", "魅力"]


def test_custom_split_must_add_up():
    g = _game()
    bad = _grow(g, "custom", {"str": 9, "lead": 1, "int": 0, "spd": 0, "cha": 0})
    assert "至少" in bad[-1] and g.state.player.growth_preset is None
    bad = _grow(g, "custom", {"str": 6, "lead": 1, "int": 1, "spd": 1, "cha": 1})
    assert "最多" in bad[-1] and g.state.player.growth_preset is None  # 每一項最多 custom_max（4），不能全壓在一項
    _grow(g, "custom", {"str": 4, "lead": 3, "int": 1, "spd": 1, "cha": 1})
    _level(g, 3)
    assert attrset.value(g.state, g.content, "str") == g.content.config.attributes.v2.base + 8


def test_bonus_points_every_ten_levels_have_no_cap():
    g = _game()
    c = g.content
    assert team.level_points(g.state, c, 9, 10) == c.config.attributes.v2.bonus_points
    assert team.level_points(g.state, c, 10, 19) == 0
    g.state.player.stat_points = 30
    for _ in range(30):
        g.allocate_stat("cha")
    assert g.state.player.attr_alloc == {"cha": 30} and g.state.player.stat_points == 0


def test_old_formulas_read_the_new_value_against_the_average_person():
    """舊公式讀新的五項：比同等級的平均人高幾成，經過有上限的曲線（企劃者 2026-11-04「不限於5～15」）。"""
    import math
    g = _game()
    c, v2 = g.content, g.content.config.attributes.v2
    assert team.v1_stat(g.state, c, "agi") == 5  # 跟平均人一樣：舊尺度的起點，效果 0
    _level(g, 11)
    _grow(g, "ranger")  # 身法每級 4
    mean = attrset.expect(c, 11)
    r = (attrset.value(g.state, c, "spd") - mean) / mean
    want = v2.legacy_caps["agi"] * math.tanh(r / v2.legacy_scale)
    assert team.stat_bonus(c, team.v1_stat(g.state, c, "agi")) == pytest.approx(want)
    assert team.v1_stat(g.state, c, "lore") == 5  # 博聞拔掉：當基準
    assert team.con_of(g.state, c, g.world, "player") == team.v1_stat(g.state, c, "con")


def test_the_check_is_relative_to_the_level():
    g = _game()
    c = g.content
    check = Check(stat="wis", grade="normal", tier=2)  # 第二階：減法季的放寬不算進來
    even = rules.check_outlook(check, g.state, c, g.world)
    assert round(even.chance, 6) == c.config.attributes.v2.grade_rates["normal"]  # 第 1 級＝平均人
    _level(g, 21)
    _grow(g, "strategist")  # 悟性每級 4：高過平均
    high = rules.check_outlook(check, g.state, c, g.world).chance
    _grow(g, "warrior")  # 悟性每級 1：低過平均，還是有基本的成功率
    low = rules.check_outlook(check, g.state, c, g.world).chance
    assert high > c.config.attributes.v2.grade_rates["normal"] > low >= c.config.checks.floor
    legacy = Check(stat="agi", difficulty=8)  # 舊寫法照帶子分級：8 是「難」＋1
    assert rules.grade_of(legacy, c) == ("hard", 1)


def test_events_give_xinde_instead_of_attribute_points():
    g = _game()
    p = g.state.player
    before = p.stats.get("xinde", 0)
    rules.apply_effect(Effect(stats={"str": 2, "silver": 5}), g.state, g.content, g.world)
    assert p.stats["xinde"] == before + 2 * g.content.config.attributes.v2.attr_xinde
    assert attrset.value(g.state, g.content, "str") == g.content.config.attributes.v2.base


def test_the_old_season_is_untouched():
    g = _game(False)
    assert "growth" not in g.status_data()
    assert [row[2] for row in g.status_data()["attrs"]] == list(team.COMBAT_STATS)


# ── 第 2 批：同一把尺（對手也有屬性）、對抗式 ──


def test_foes_get_attributes_from_level_and_aptitude():
    g = _game()
    c = g.content
    weak, strong = c.squads[min(c.squads, key=lambda k: c.squads[k].difficulty)], c.squads[max(c.squads, key=lambda k: c.squads[k].difficulty)]
    assert attrset.foe_values(c, weak)["lead"] < attrset.foe_values(c, strong)["lead"]
    picked = weak.model_copy(update={"level": 30, "aptitude": {"lead": 9}})
    assert attrset.foe_values(c, picked)["lead"] > attrset.foe_values(c, picked)["str"]


def test_damage_is_my_force_against_their_command():
    g = _game()
    c = g.content
    _level(g, 21)
    _grow(g, "warrior")
    weak = c.squads[min(c.squads, key=lambda k: c.squads[k].difficulty)]
    tough = weak.model_copy(update={"level": 21, "aptitude": {"lead": 9}})
    with team.facing(g.state, c, weak):
        vs_weak = team.player_boost(g.state, c, g.world).outer
    with team.facing(g.state, c, tough):
        vs_tough = team.player_boost(g.state, c, g.world).outer
    assert vs_weak > vs_tough
    assert abs(vs_weak) <= c.config.attributes.v2.effects[0].cap


def test_the_old_season_ignores_the_foe():
    g = _game(False)
    c = g.content
    squad = next(iter(c.squads.values()))
    plain = team.player_boost(g.state, c, g.world)
    with team.facing(g.state, c, squad):
        assert team.player_boost(g.state, c, g.world) == plain


# ── 第 3、4 批：江湖水漲退掉、獎勵跟著等級、歷史武將不同行 ──


def test_rise_steps_back_in_the_new_season():
    from tianxia import rise

    g, old = _game(), _game(False)
    assert not rise.on(g.content, g.state.world)
    assert rise.on(old.content, old.state.world) == old.content.config.rise.enabled


def test_rewards_follow_the_level():
    g = _game()
    p = g.state.player
    rules.apply_effect(Effect(stats={"silver": 35}), g.state, g.content, g.world)  # 35 最近「大」：40
    low = p.stats["silver"]
    _level(g, 21)
    rules.apply_effect(Effect(stats={"silver": 35}), g.state, g.content, g.world)
    assert p.stats["silver"] - low > 40
    old = _game(False)
    before = old.state.player.stats["silver"]
    rules.apply_effect(Effect(stats={"silver": 35}), old.state, old.content, old.world)
    assert old.state.player.stats["silver"] == before + 35


def test_historical_figures_do_not_join_in_the_new_season():
    from tianxia import roster

    g = _game()
    c = g.content
    assert not roster.on(c, g.state.world)
    cid = next(k for k, ch in c.characters.items() if ch.recruitable)
    lines = roster.recruit(g.state, c, g.world, cid)
    assert "不會跟你走" in lines[0] and roster.owned_by(g.world, cid) is None


def test_figures_grow_with_the_calendar_instead_of_rise():
    from tianxia import calendar

    g = _game()
    c = g.content
    fid = next(iter(c.figures))
    g.state.world.time = 0
    start = g._figure_squad(fid)
    g.state.world.time = calendar.calendar_end(c, g.state.world)
    end = g._figure_squad(fid)
    assert end.level - start.level == pytest.approx(c.config.attributes.v2.figure_growth, abs=0.5)
    assert end.difficulty > start.difficulty
    assert attrset.foe_level(c, attrset.foe_difficulty(c, 25)) == pytest.approx(25)
    old = _game(False)
    assert old._figure_squad(fid).level is None


def test_command_cuts_the_hp_lost_against_their_force():
    g = _game()
    c = g.content
    _level(g, 21)
    weak = c.squads[min(c.squads, key=lambda k: c.squads[k].difficulty)]
    brute = weak.model_copy(update={"level": 21, "aptitude": {"str": 9}})

    def lost(preset, squad):
        _grow(g, preset)
        m = g.state.player.member
        m.neili, m.injury = None, 0.0
        before, cap = g._player_hp_and_cap()
        team.take_encounter_toll(g.state, c, g.world, "落敗", squad=squad)
        return (before - g._player_hp()) / cap  # 照上限的比例（根骨〔統御〕也拉高上限）

    assert lost("warrior", weak) < lost("strategist", weak)  # 統御每級 3 對 2、身法一樣：同一隊少掉的比例小
    assert lost("warrior", weak) < lost("warrior", brute)  # 他的武力越高，擋掉的越少
    old = _game(False)
    assert team._guard(old.state, old.content, old.world, weak) == 0.0


def _pvp_pair(level: int = 30):
    """兩個同武學同等級的人：甲全點武力（上限 4，另一項 3 給身法、送點全給武力），乙全點統御（送點全給統御）。"""
    a, b = _game(), _game()
    for g, split, bonus in ((a, {"str": 4, "lead": 1, "int": 1, "spd": 3, "cha": 1}, "str"),
                            (b, {"str": 3, "lead": 4, "int": 1, "spd": 1, "cha": 1}, "lead")):
        _level(g, level)
        _grow(g, "custom", split)
        g.state.player.attr_alloc = {bonus: 30}
    return a, b


def _alone(g: Game) -> float:
    from tianxia import encounter
    s, c, w = g.state, g.content, g.world
    return encounter.member_power(s.player.member, team.team_arts(s, c, w), boost=team.player_boost(s, c, w))


def test_player_fights_face_the_real_opponents_attributes():
    """企劃者 2026-11-04「全部點武力 會不會沒人打得過他」：玩家對玩家照對手本人的五項（他的統御擋你的武力），不是同等級的平均人。"""
    brute, wall = _pvp_pair()
    assert Game._spar_power(brute, wall) < _alone(brute)  # 對上統御高的人，武力的加成縮了
    assert Game._spar_power(wall, brute) > Game._spar_power(brute, wall)
    # 快照（擂台的分身、奪璽單挑）照卡重算，跟兩邊都活著算的一樣
    ca, cb = (team.pvp_card(g.state, g.content, g.world) for g in (brute, wall))
    with team.facing_player(brute.content, brute.state, wall.state):
        live = _alone(brute)
    faced, _, _ = team.pvp_faced(brute.content, _alone(brute), {}, ca, cb)
    assert faced == pytest.approx(live, rel=1e-6)


def test_arena_rescales_both_snapshots_against_each_other():
    from tianxia.features.bout import arena_actions
    brute, wall = _pvp_pair()
    me, foe = arena_actions.arena_side(brute), arena_actions.arena_side(wall)
    before = (me.power, foe.power, dict(me.scores))
    arena_actions.faced(brute.content, me, foe)
    assert me.power / before[0] < foe.power / before[1] and foe.power > me.power  # 全武力撞上全統御：前者縮得多、後者反而比較強
    assert all(me.scores[m] <= before[2][m] for m in me.scores)
    old = _game(False)
    assert team.pvp_card(old.state, old.content, old.world) is None  # 舊的季沒有卡，擂台、奪璽一個字不變


def test_custom_growth_is_capped_per_attribute():
    g = _game()
    cap = g.content.config.attributes.v2.custom_max
    assert attrset.growth_problem(g.content, "custom", {"str": cap + 1, "lead": 1, "int": 1, "spd": 1, "cha": 10 - cap - 4})
    assert attrset.view(g.state, g.content)["custom_max"] == cap


def test_extreme_builds_stay_inside_the_effect_caps():
    """全點一項到第 60 級：舊公式拿到的效果不超過 legacy_caps（屬性沒有上限、效果有上限；企劃者 2026-11-04）。"""
    a, b = _pvp_pair(level=60)
    caps = a.content.config.attributes.v2.legacy_caps
    for g in (a, b):
        for old, cap in caps.items():
            assert abs(team.stat_bonus(g.content, team.v1_stat(g.state, g.content, old))) <= cap + 1e-9


def test_neigong_weighs_double_only_in_five_attribute_seasons():
    """企劃者 2026-11-04 點頭的武學調整「內功加重」：五項屬性的季內功份量的除數 100 → 50，舊的季照舊。"""
    from tianxia import encounter
    g, old = _game(), _game(False)
    assert team.player_boost(g.state, g.content, g.world).inner_div == g.content.config.attributes.v2.neigong_divisor == 50
    assert team.player_boost(old.state, old.content, old.world).inner_div == encounter.NEIGONG_BONUS_DIVISOR


def test_counter_traits_cut_the_attribute_they_answer(monkeypatch):
    """剋屬性的功效（企劃者 2026-11-04）：破甲讓對手的統御少算兩成——全武力帶破甲撞全統御，比不帶的強；舊的季沒有。"""
    from tianxia import traits
    brute, wall = _pvp_pair()
    plain = Game._spar_power(brute, wall)
    real = traits.loadout
    monkeypatch.setattr(traits, "loadout", lambda s, c, w: traits.Loadout(layers={"difficulty_cut": 1.0})
                        if s is brute.state else real(s, c, w))
    assert team.counter_cuts(brute.state, brute.content, brute.world) == {"lead": 0.2}
    assert Game._spar_power(brute, wall) > plain
    # 快照（擂台、奪璽）帶在卡上，照卡重算跟活的一樣
    ca, cb = (team.pvp_card(x.state, x.content, x.world) for x in (brute, wall))
    assert ca["cuts"] == {"lead": 0.2}
    # 對手帶化勁回瀾：我的武力少算
    monkeypatch.setattr(traits, "loadout", lambda s, c, w: traits.Loadout(layers={"toll_cut": 1.0})
                        if s is wall.state else real(s, c, w))
    assert Game._spar_power(brute, wall) < plain
    old = _game(False)
    assert team.counter_cuts(old.state, old.content, old.world) == {}


def test_arena_counts_dodge_and_drops_roles_in_five_attribute_seasons():
    """企劃者 2026-11-04：擂台以前完全不看身法——補上閃避（身法對他的身法）；玩家對打不給職位加成（職位留在決戰）。"""
    from tianxia.features.bout import arena_actions
    quick, plain = _game(), _game()
    for g, split, bonus in ((quick, {"str": 3, "lead": 1, "int": 1, "spd": 4, "cha": 1}, "spd"), (plain, None, None)):
        _level(g, 30)
        if split:
            _grow(g, "custom", split)
            g.state.player.attr_alloc = {bonus: 30}
    me, foe = arena_actions.arena_side(quick), arena_actions.arena_side(plain)
    assert me.role  # 開打前還帶著職位（身法最高：斥候）
    arena_actions.faced(quick.content, me, foe)
    assert me.dodge > 0 and foe.dodge == 0
    assert me.role == "" and foe.role == ""
    old = _game(False)
    assert arena_actions.arena_side(old).dodge == 0.0


def test_charm_helps_gamble_hire_and_favor_only_in_five_attribute_seasons():
    """魅力的用途（企劃者 2026-11-04）：高於平均人放手一搏多幾個百分點、招募便宜、情誼長得快，都有上限；低於平均反過來、上限小；舊的季是 0。"""
    from tianxia import renown
    from tianxia.features.hire import actions as hire
    g = _game()
    _level(g, 30)
    caps = g.content.config.attributes.v2.charm
    _grow(g, "custom", {"str": 1, "lead": 1, "int": 3, "spd": 1, "cha": 4})
    g.state.player.attr_alloc = {"cha": 30}
    up = {h: attrset.charm(g.state, g.content, h) for h in caps}
    assert all(0 < up[h] <= caps[h][0] for h in caps) and up["gamble"] > 4
    assert hire.price(g) < g.content.config.hire.cost
    assert renown.warmed(g.content, 10, g.state) > renown.warmed(g.content, 10)
    _grow(g, "custom", {"str": 4, "lead": 3, "int": 1, "spd": 1, "cha": 1})
    g.state.player.attr_alloc = {"str": 30}
    assert all(-caps[h][1] <= attrset.charm(g.state, g.content, h) < 0 for h in caps)
    old = _game(False)
    assert all(attrset.charm(old.state, old.content, h) == 0 for h in caps)
    assert hire.price(old) == old.content.config.hire.cost


def test_a_check_can_read_charm_in_five_attribute_seasons():
    """檢定寫了 v2（例 cha）：五項屬性的季改看那一項、選項上寫「魅力」；舊的季照 stat。"""
    g = _game()
    _level(g, 30)
    _grow(g, "custom", {"str": 1, "lead": 1, "int": 1, "spd": 3, "cha": 4})
    plain, charm = Check(stat="wis", difficulty=7), Check(stat="wis", difficulty=7, v2="cha")
    assert rules.check_chance(charm, g.state, g.content, g.world) > rules.check_chance(plain, g.state, g.content, g.world)
    assert rules.check_stat_name(charm, g.content, g.state.world) == "魅力"
    old = _game(False)
    assert rules.check_chance(charm, old.state, old.content, old.world) == rules.check_chance(plain, old.state, old.content, old.world)
    assert "v2" not in plain.model_dump()


def test_hints_talk_about_the_new_rules_in_five_attribute_seasons():
    """PM 2026-11-04 查新手教學：五項屬性的季配點提示講每十級送點、找同伴的提示指向酒肆招募；舊的季照舊。"""
    from tianxia.features.guide import actions as guide_actions, hints as hint_rules
    g, old = _game(), _game(False)
    for hid in ("h_points", "h_recruit"):
        hint = next(h for h in g.content.hints.hints if h.id == hid)
        assert hint_rules.note_for(g.state, g.content, hid).text.endswith(hint.attrs_v2[-6:])
        assert hint_rules.note_for(old.state, old.content, hid).text.endswith(hint.text[-6:])
    town = next(ch.hire_at for ch in g.content.characters.values() if ch.hire_at)
    g.state.player.location = town
    assert guide_actions.hire_here(g) and not guide_actions.hire_here(old)


def test_counter_cuts_need_a_world_and_dodge_still_works_without_one():
    """dodge_chance 不經 world（量表與純函式）：剋屬性的功效要 world 才解得出身上的武學，沒有就不算，不能炸（2026-11-05 量表腳本）。"""
    g = _game()
    assert team.counter_cuts(g.state, g.content, None) == {}
    assert 0 <= team.dodge_chance(g.state, g.content) <= 1


def test_the_season_prep_card_asks_for_the_growth_first_and_locks_it():
    """開季準備卡（企劃者 2026-11-05）：還沒挑配比時選單只剩挑配比的鈕（排在開局三選一前面）；挑了就鎖，這一季不能再換。"""
    g = _game()
    g.state.player.growth_preset = None  # 換季、網頁上建的新角色：還沒挑
    assert g.season_prep_view() == {"step": "growth", "steps": ["growth"]}
    ids = [o.id for o in g.options()]
    assert ids == [f"growth:{p.key}" for p in g.content.config.attributes.v2.presets] + ["growth:custom"]
    assert g.choose("act:train") == ["（此刻無法這麼做。）"]
    assert g.choose("growth:custom") == ["（在卡上自己配五項，配好按「定下來」。）"] and g.state.player.growth_preset is None
    g.choose("growth:ranger")
    assert g.state.player.growth_preset == "ranger" and g.season_prep_view() is None
    assert not any(o.id.startswith("growth:") for o in g.options())
    assert g.pick_growth("warrior") == ["這一季的成長配比已經定了，下一季開季再挑。"] and g.state.player.growth_preset == "ranger"


def test_no_prep_card_in_old_seasons_or_for_script_characters():
    off = _game(False)
    assert off.season_prep_view() is None
    c = real_content("season21")
    c.config.auto_open_first_season = True
    scripted = Game.new(c, "沈浪", rng=random.Random(0), world=open_world(Path(tempfile.mkdtemp(prefix="attrs-")) / "tianxia.db"))
    assert scripted.state.player.growth_preset == c.config.attributes.v2.default_preset  # 序章算走過：照預設那一套
    assert scripted.season_prep_view() is None


def test_bots_pick_their_growth_on_the_prep_card():
    from tianxia import bot, bot_policy

    g = _game()
    g.state.player.growth_preset = None
    options = g.options()
    key = bot.growth_key(g)
    assert bot.pick(g, options, random.Random(0)) == f"growth:{key}"
    scores = {o.id: bot_policy.score(g, o, None) for o in options}  # 挑配比的分數不看個性
    assert scores[f"growth:{key}"] == bot_policy.GROWTH_SCORE and all(v is None for k, v in scores.items() if k != f"growth:{key}")
