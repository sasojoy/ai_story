"""玩家武學追上本命（/mnt/project-files/plan/玩家武學追上本命定案.md）：一、絕學立招；四、鑄器配招。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import library, skillview, smithing, tactics, team, traits
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name
from tianxia.state import PLAYER, Equipment

ALL_ODDS = {"下品": 0.0, "中品": 0.0, "上品": 0.0, "絕學": 100.0}


def _ctx(**kw):
    base = {"foe": "山賊", "our_agility": 5.0, "foe_agility": 6.0, "team": [PLAYER]}
    return tactics.Ctx(**(base | kw))


def _game(content):
    content.config.weapons.enabled = True
    content.config.armor.enabled = True
    game = Game.new(content, "試招俠客", rng=random.Random(0))
    game.world.open_season(content, now=0.0)
    return game


INSIGHT_OF = {"快": "feng", "剛": "huo", "柔": "shui", "慢": "shan", "陽": "haoran", "陰": "xuesha"}  # 正式內容的基本意境


def _mastered(game, name, cells, kind="武學", quality="絕學"):
    """一門自己合成、練到 quality 的武學，功效照 cells（第一格是自己的屬性），配在身上。
    武學重構：功效不寫在武學上、由槽裡裝的意境決定（arts.apply 會蓋掉 traits）——cells 換成同屬性的基本意境裝進槽，
    同一個屬性出現幾次就是那個意境的強度（層數）；相容屬性照 cells 的順序，第一個就是武學自己的屬性。"""
    affinity = list(dict.fromkeys(cells))
    art = generate_from_name(name, kind, name, weights=ALL_ODDS).model_copy(
        update={"origin": "fused", "creator": game.state.player.name, "attribute": cells[0], "affinity": affinity})
    assert game.world.claim_skill_name(art)
    p = game.state.player
    p.art_quality[art.id] = quality
    p.art_slots[art.id] = [INSIGHT_OF[a] for a in affinity]
    for a in affinity:
        if INSIGHT_OF[a] not in p.insights:
            p.insights.append(INSIGHT_OF[a])
        p.insight_strength[INSIGHT_OF[a]] = cells.count(a)
    if kind == "武學":
        p.member.wugong_id, p.member.wugong_level = art.id, 10
    else:
        p.member.neigong_id, p.member.neigong_level = art.id, 10
    return art


def _original(recipe="wd_dark_crystal", attribute="剛", **kw):
    return Equipment(id="兵:9", name="試劍", kind="劍", attribute=attribute, tier=3, quality="上品", original=True,
                     secret=recipe, **kw)


def _named(attribute="剛"):
    return Equipment(id="兵:8", name="名劍", kind="劍", attribute=attribute, tier=2, quality="中品", secret="w2_falcon_chase")


def test_every_general_trait_has_an_ultimate_with_a_bond():
    content = real_content()
    for trait in (t for t in content.traits.general if not t.id):  # 每一路第一個功效有絕招；意境效果池的第二個沒有
        assert trait.ultimate is not None and trait.ultimate.kind in tactics.KINDS, trait.name
        assert trait.ultimate_bond is not None and trait.ultimate_bond.desc.startswith("以器配招"), trait.name
        assert "{" not in tactics.card_text(trait.ultimate, traits.ULTIMATE_TITLE)


@pytest.mark.smoke
def test_only_a_self_made_mastered_art_gets_an_ultimate_named_after_it():
    content = real_content()
    game = _game(content)
    art = _mastered(game, "裂岳狂風拳", ["剛", "快", "快"])
    mine = team.player_art(game.state, content, game.world, art.id)
    ult = traits.ultimate_of(content, mine)
    assert ult is not None and ult.name == "裂岳狂風拳" and ult.kind == "swift"  # 層數最多的是快：先手的絕招
    assert traits.card_line(content, mine) is None or "絕〔裂岳狂風拳〕" in traits.card_line(content, mine)
    game.state.player.art_quality[art.id] = "上品"
    assert traits.ultimate_of(content, team.player_art(game.state, content, game.world, art.id)) is None
    assert traits.ultimate_of(content, team.player_art(game.state, content, game.world, "guanyu_wugong")) is None


def test_the_ultimate_joins_the_fight_holders_under_the_art_name():
    content = real_content()
    game = _game(content)
    _mastered(game, "斷金掌", ["剛", "剛", "柔"])
    names = {h.tactic.name: h for h in team.tactic_holders(game.state, content, game.world)}
    assert "斷金掌" in names and names["斷金掌"].tactic.kind == "shatter"


@pytest.mark.parametrize("attribute, needle", [
    ("快", "定身"), ("剛", "卸勁"), ("陰", "血創"), ("虛", "失神"), ("陽", "無隙"), ("實", "退無可退"),
])
def test_each_new_ultimate_shows_up_in_the_round_lines(attribute, needle):
    content = real_content()
    t = content.config.tactics
    trait = traits.general(content, attribute)
    params = dict(trait.ultimate.params)
    for key in ("stun_pct", "daze_pct"):
        if key in params:
            params[key] = 1.0
    tactic = trait.ultimate.model_copy(update={"name": "試招", "rate": 1.0, "params": params})
    holder = tactics.Holder(who="你", key=PLAYER, skill="test", tactic=tactic)
    seen = ""
    for seed in range(60):
        margin = -20.0 if attribute == "實" else 20.0
        clash = tactics.play(margin, 100.0, 5, [holder], _ctx(hp_ratio=0.2), t, random.Random(seed))
        seen += "".join(line for turn in clash.turns for line in turn.lines)
    assert needle in seen, attribute


def test_borrow_ultimate_can_daze_and_ward_ultimate_reflects():
    content = real_content()
    t = content.config.tactics
    for attribute, needle in (("柔", "失神"), ("慢", "守一")):
        trait = traits.general(content, attribute)
        params = dict(trait.ultimate.params) | {"chance_pct": 1.0, "daze_pct": 1.0}
        holder = tactics.Holder(who="你", key=PLAYER, skill="test",
                                tactic=trait.ultimate.model_copy(update={"name": "試招", "rate": 1.0, "params": params}))
        seen = "".join(line for seed in range(40) for turn in tactics.play(
            -10.0, 100.0, 5, [holder], _ctx(), t, random.Random(seed)).turns for line in turn.lines)
        assert needle in seen, attribute


def test_a_bound_original_strengthens_the_ultimate_and_a_named_piece_a_little():
    content = real_content()
    game = _game(content)
    art = _mastered(game, "疾雷手", ["快", "快", "剛"])
    p = game.state.player
    base = traits.ultimate_of(content, team.player_art(game.state, content, game.world, art.id))
    p.weapon = _named("快")
    got = dict(team.ultimate_tactics(game.state, content, game.world))[art.id]
    assert got.rate == pytest.approx(base.rate + content.config.tactics.named_bond_rate)
    p.weapon = _named("剛")  # 屬性不同：沒有名器同氣
    assert dict(team.ultimate_tactics(game.state, content, game.world))[art.id].rate == pytest.approx(base.rate)
    p.weapon = _original(attribute="剛", bound_art=art.id)
    got = dict(team.ultimate_tactics(game.state, content, game.world))[art.id]
    assert got.rate == pytest.approx(base.rate + 0.15)


def test_binding_rules_and_the_gear_row():
    content = real_content()
    game = _game(content)
    art = _mastered(game, "迴風劍", ["柔", "柔", "快"])
    p = game.state.player
    p.rack.append(_original())
    p.rack.append(_named("柔"))
    assert smithing.bind_problem(game.state, content, game.world, "兵:8", art.id) == smithing.BIND_NOT_ORIGINAL
    assert smithing.bind_problem(game.state, content, game.world, "兵:9", "basic_fist") == smithing.BIND_BAD_ART
    rows = {r["id"]: r for b in skillview.gear_rows(game.state, content, game.world)["slots"] for r in b["rack"]}
    assert rows["兵:9"]["bind"]["options"][0]["id"] == art.id and rows["兵:8"]["bind"] is None
    msgs = game.bind_art("兵:9", art.id)
    assert msgs[0].startswith("【試劍】與【迴風劍】人器合一")
    assert smithing.bind_problem(game.state, content, game.world, "兵:9", art.id).startswith("（【試劍】已經配了")
    rows = {r["id"]: r for b in skillview.gear_rows(game.state, content, game.world)["slots"] for r in b["rack"]}
    assert rows["兵:9"]["bind"] is None and any(t.startswith("以器配招〔迴風劍〕") for t in rows["兵:9"]["tactic"])
    p.member.wugong_id = None  # 那一門不在手上了：可以再配別門
    assert library.owned_arts(game.state) == [a for a in (p.member.neigong_id,) if a] + list(p.arts)
    assert not smithing.bound_alive(game.state, p.rack[0])


def test_a_signature_arm_cannot_be_bound():
    content = real_content()
    game = _game(content)
    art = _mastered(game, "鎮山拳", ["剛", "剛", "剛"])
    game.state.player.rack.append(Equipment(id="兵:7", name="刀", kind="刀", attribute="剛", tier=3, quality="上品",
                                            original=True, signature="guanyu"))
    assert smithing.bind_problem(game.state, content, game.world, "兵:7", art.id) == smithing.BIND_NOT_ORIGINAL


def test_signature_might_only_counts_in_player_versus_player_bouts():
    content = real_content()
    t = content.config.tactics
    hs = tactics.holders_of(content, [("你", PLAYER, "liubei_wugong", "liubei_neigong")])
    might = sum(h.tactic.might for h in hs)
    assert might > 0
    side = tactics.side_for(hs, _ctx())
    for pvp, want in ((True, might), (False, 0.0)):
        bout = tactics.open_bout(side, None, "你", "對手", pvp=pvp)
        f, _g = tactics._fights(bout, t, random.Random(1), 1.0, 1.0)
        f.begin(1, 50.0, [])
        assert f.push_mod == pytest.approx(want)
    assert tactics.MIGHT_NOTE.format(pct=round(hs[0].tactic.might * 100)) in tactics.card_text(hs[0].tactic)
    # 武學重構第三批滿配變強，張梁的底蘊也重調過（2026-10-20；同效果第二份算半之後 +0.15，2026-10-22；破境修法甲 +0.65，2026-10-23），卡上照實寫
    assert "推力 +161%" in tactics.card_text(content.skills["zhangliang_wugong"].tactic)
