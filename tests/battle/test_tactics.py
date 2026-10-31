"""本命戰法與一般的仗的回合（tianxia/tactics.py，Joy 2026-10-15 選「全部改回合制」）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import encounter, tactics, team
from tianxia.engine import Game
from tianxia.state import PLAYER


def _holders(content, *rows):
    return tactics.holders_of(content, [(who, key, w, n) for who, key, w, n in rows])


def _ctx(**kw):
    base = {"foe": "山賊", "our_agility": 5.0, "foe_agility": 6.0, "team": [PLAYER]}
    return tactics.Ctx(**(base | kw))


def _only(content, skill_id, **params):
    """拿一門本命戰法、改它的發動率或數字（測一種狀態時讓它一定發）。"""
    tactic = content.skills[skill_id].tactic.model_copy(update=params)
    return tactics.Holder(who="你", key=PLAYER, skill=skill_id, figure=tactics.figure_of(content, skill_id), tactic=tactic)


@pytest.mark.parametrize("margin", [-60.0, -10.0, 0.0, 12.0, 45.0, 200.0])
def test_without_tactics_the_rounds_add_up_to_the_rolled_margin(margin):
    t = real_content().config.tactics
    for seed in range(30):
        clash = tactics.play(margin, 100.0, 4, [], _ctx(), t, random.Random(seed))
        assert clash.margin == margin and not clash.stopped and not clash.fired
        assert len(clash.turns) == 4
        assert sum(turn.push for turn in clash.turns) == pytest.approx(t.span * margin / 100.0)
        for turn in clash.turns[:-1]:  # 中途不會提前收場
            assert abs(turn.edge - 50) < t.stop


def test_every_kind_runs():
    content = real_content()
    t = content.config.tactics
    sids = [sid for sid, s in content.skills.items() if s.tactic is not None]
    minor = [sid for sid in sids if content.skills[sid].tactic.minor]  # 學來的武學帶的小戰法（TacticDef.minor）也要跑得動
    assert (len(sids) - len(minor), len(minor)) == (36, 23) and {content.skills[s].tactic.kind for s in sids} <= set(tactics.KINDS)
    for sid in sids:
        holder = _only(content, sid, rate=1.0)
        for seed in range(20):
            clash = tactics.play(5.0, 100.0, 5, [holder], _ctx(night=True, mount_tier=2, good=40, evil=40, followers=2,
                                                             foe_faction="huangjin", own_turf=True), t, random.Random(seed))
            assert 1 <= len(clash.turns) <= 5
            assert all(line.startswith(tactics.LEAD) for turn in clash.turns for line in turn.lines)


def test_roar_stuns_and_the_foe_cannot_hit():
    content = real_content()
    t = content.config.tactics
    holder = _only(content, "zhangfei_wugong", rate=1.0, params={"stun_pct": 1.0, "turns": 1.0})
    clash = tactics.play(0.0, 100.0, 4, [holder], _ctx(), t, random.Random(1))
    assert all(turn.theirs is None and not turn.landed for turn in clash.turns[: len(clash.turns)])
    assert "長坂一喝" in clash.fired and clash.margin > 0
    assert clash.turns[0].lines[0].startswith("〔長坂一喝〕你一聲大喝")
    assert clash.blocked_share() == 1.0


def test_tactics_turn_a_close_fight_upward_on_average():
    content = real_content()
    t = content.config.tactics
    holders = _holders(content, ("你", PLAYER, "guanyu_wugong", "zhangfei_wugong"))
    gained = [tactics.play(0.0, 100.0, 4, holders, _ctx(), t, random.Random(seed)).margin for seed in range(300)]
    assert sum(gained) / len(gained) > 0


def test_rally_raises_the_brothers_rates():
    content = real_content()
    rally = _holders(content, ("劉備", PLAYER, None, "liubei_neigong"))
    guan = _holders(content, ("關羽", "guanyu", "guanyu_wugong", None))
    f = tactics._Fight(rally + guan, _ctx(), content.config.tactics, random.Random(0))
    assert f.rate(guan[0]) == pytest.approx(guan[0].tactic.rate + rally[0].tactic.params["boost_pct"])
    alone = tactics._Fight(guan, _ctx(), content.config.tactics, random.Random(0))
    assert alone.rate(guan[0]) == pytest.approx(guan[0].tactic.rate)


@pytest.mark.smoke
def test_ward_keeps_your_own_side_from_losing_its_head():
    content = real_content()
    f = tactics._Fight([], _ctx(), content.config.tactics, random.Random(0))
    f.us.states["守一"] = 2
    assert not f.put(f.us, "失神", 1, now=True)
    assert not f.us.has("失神") and f.lines == ["〔守一〕你這一方心神守住，失神沒能沾身"]
    assert f.put(f.foe, "失神", 1, now=True) and f.foe.has("失神")


def test_fog_and_thunder_combo_fires_both():
    content = real_content()
    holders = [_only(content, "zhangbao_neigong"), _only(content, "zhangjiao_wugong", rate=1.0)]
    clash = tactics.play(0.0, 100.0, 5, holders, _ctx(our_agility=9.0), content.config.tactics, random.Random(3))
    assert "霧鎖山川" in clash.fired and "天雷符" in clash.fired


def test_the_same_tactic_on_two_people_counts_once_player_first():
    content = real_content()
    hs = _holders(content, ("你", PLAYER, "zhangfei_wugong", None), ("張飛", "zhangfei", "zhangfei_wugong", "zhangfei_neigong"))
    assert [(h.who, h.tactic.name) for h in hs] == [("你", "長坂一喝"), ("張飛", "丈八狂瀾")]


def test_cards_say_kind_rate_and_effect():
    content = real_content()
    text = tactics.card_text(content.skills["zhangfei_wugong"].tactic)
    assert text.startswith("本命〔長坂一喝〕出招・每回合 40%：") and "{" not in text  # 招名前面蓋「本命」印（招式與絕學稿案第一節）


def _fighter(content):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    m = game.state.player.member
    m.wugong_id, m.wugong_level, m.neigong_id, m.neigong_level = "zhangfei_wugong", 10, "liubei_neigong", 10
    return game


def test_estimate_counts_the_tactics_and_stays_put_without_them():
    content = real_content()
    game = _fighter(content)
    squad = next(s for s in content.squads.values() if 60 <= s.difficulty <= 140)
    s, w = game.state, game.world
    power = team.power_vs(s, content, w, squad, fresh=True)
    plain = team.odds_word(power, squad)
    plan = (team.tactic_holders(s, content, w), team.tactic_ctx(s, content, w, squad, squad.difficulty), content)
    assert plan[0]
    assert team.odds_word(power, squad, plan=([], plan[1], content)) == plain


def test_an_engine_fight_writes_tactic_lines_into_the_report():
    content = real_content()
    game = _fighter(content)
    s = game.state
    found = False
    for _ in range(40):
        game._squad_encounter("shoumu", wild=True)
        record = s.battles[-1]
        if any(line.startswith("〔") and "〕" in line for line in record.rounds):
            found = True
            assert any(line.startswith("〔仁義聚眾〕") for line in record.rounds)
            break
    assert found


def test_tactic_heals_and_self_costs_change_hp_after_the_toll():
    content = real_content()
    game = _fighter(content)
    m = game.state.player.member
    _, cap = team.member_neili(content, m, team.con_of(game.state, content, game.world, PLAYER))
    m.neili = cap * 0.5
    turn = tactics.Turn(number=1, ours="強攻", theirs=None, beat=0, push=0.0, edge=50.0, landed=False)
    healed = tactics.Clash(turns=[turn], margin=0.0, hp={PLAYER: 0.1})
    toll, _, _ = game._take_toll("大勝", clash=healed)
    assert any("氣血 +" in line for line in toll)
    assert m.neili == pytest.approx(cap * 0.6)  # 這一回合對手沒打到你：不扣，只回
    hurt = tactics.Clash(turns=[turn], margin=0.0, hp={PLAYER: -0.1})
    game._take_toll("大勝", clash=hurt)
    assert m.neili == pytest.approx(cap * 0.5)


def _own_tactics(content):
    """本命以外的戰法（第三批）：八個一般功效疊到上限、七個特別功效、九件神器的特技、七把名將本命兵器的特技，再加八個絕招。"""
    from tianxia import traits
    lo = traits.Loadout(layers={t.hook: 99.0 for t in content.traits.general},
                        specials={sp.hook: sp for sp in content.traits.special})
    out = traits.tactic_defs(content, lo)
    out += [r.tactic for r in content.forge_secrets.values() if r.tactic is not None]
    out += [a.tactic for a in content.gear.signature_arms if a.tactic is not None]
    out += [t.ultimate for t in content.traits.general if t.ultimate is not None]  # 絕學立招（玩家武學追上本命）
    out += [h.tactic for h in content.traits.high]  # 武學技能分檔的高階技能
    return out


def test_every_trait_and_gear_tactic_runs_and_together_they_cover_every_kind():
    content = real_content()
    t = content.config.tactics
    own = _own_tactics(content)
    assert len(own) == 7 + 8 + 7 + (9 + 12) + 7 + 8 + 8  # 厚沒有回合裡的戰法；意境效果池每一路的第二個一般功效八個；神器原本九件加第 10 批十二件；絕招八個；高階技能八個
    kinds = {content.skills[s].tactic.kind for s, sk in content.skills.items() if sk.tactic is not None}
    assert kinds | {x.kind for x in own} == set(tactics.KINDS)
    for tactic in own:
        holder = tactics.Holder(who="你", key=PLAYER, skill="test", tactic=tactic.model_copy(update={"rate": 1.0}))
        for seed in range(20):
            clash = tactics.play(5.0, 100.0, 5, [holder], _ctx(night=True, mount_tier=2, good=40, evil=40, followers=2,
                                                             foe_faction="huangjin", own_turf=True), t, random.Random(seed))
            assert 1 <= len(clash.turns) <= 5
            assert all(line.startswith(tactics.LEAD) for turn in clash.turns for line in turn.lines), tactic.name


def test_every_own_tactic_has_a_unique_name_and_a_filled_in_card():
    content = real_content()
    names = [x.name for x in _own_tactics(content)]
    names += [sk.tactic.name for sk in content.skills.values() if sk.tactic is not None]
    assert len(names) == len(set(names))
    for tactic in _own_tactics(content):
        text = tactics.card_text(tactic, tactics.GEAR_TITLE)
        assert "{" not in text and tactic.name in text, text
