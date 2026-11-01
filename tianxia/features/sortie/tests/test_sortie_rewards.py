"""正式季整合第 4 批：出陣更誘人與四階來源（設計 2.6、4.5、10.1）。正式內容、週末設定（一類一顆、素材四階都開著）。"""
from __future__ import annotations

import random
from unittest import mock

from conftest import real_content
from conquest_kit import conquest_rules

from tianxia import battle_instance, forge_secrets, four_tiers, team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game, drill_share
from tianxia.sqlite_world import open_world


def _game(faction="guan", at="runan_wilds", profile="week7", precise=True, tiers=True):
    c = conquest_rules(real_content(profile))  # 出陣攻中立地（敵方的大本營不給攻）；出陣約戰關掉，攻一下就打一場
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.precise_actions = precise
    c.config.four_tiers.enabled = tiers
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    return game


def _fight(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _attack(game):
    with _fight():
        game.choose("act:train")
    record = game.state.battles[-1]
    return record, next(q for q in game.content.squads.values() if q.name == record.opponent)


# ── Task 2：出陣攻打贏 ──


def test_an_attack_win_pays_double_with_full_silver_and_a_merit_bonus():
    game = _game()
    p = game.state.player
    p.member.level = 10
    silver = p.stats["silver"]
    record, squad = _attack(game)
    assert record.kind == "sortie" and record.exp == squad.exp * 2 and record.xinde == squad.reward_xinde * 2
    assert record.silver == squad.reward_silver + 30 and p.stats["silver"] - silver >= squad.reward_silver + 30
    assert any("軍功賞銀 30 兩" in n for n in record.notes)


def test_an_attack_win_rolls_the_drop_table_but_never_a_weapon():
    from tianxia import weapons

    game = _game()
    with mock.patch.object(weapons, "drop", side_effect=AssertionError("出陣不擲兵器")):
        record, _ = _attack(game)
    assert record.materials  # 難度 20～69 一階必掉


def test_tier_four_off_drops_nothing():
    game = _game(tiers=False)
    record, _ = _attack(game)
    assert not record.materials


def test_rare_drops_hit_with_their_own_dice_and_respect_the_caps():
    game = _game()
    cfg = game.content.config.sortie
    cfg.rare_legend, cfg.rare_treasure, cfg.rare_horse = 1.0, 1.0, 1.0
    cfg.treasure_cap, cfg.horse_cap = 1, 1
    p = game.state.player
    legend = p.legend_items
    record, _ = _attack(game)
    assert p.legend_items == legend + 1 and p.sortie_treasures == 1 and p.sortie_horses == 1
    # FB-430：寶物、良駒照挑戰本人寫進得失那一格
    assert any(m.startswith("寶物【") for m in record.materials) and any(m.startswith("良駒【") for m in record.materials)
    p.stamina = 250.0
    _attack(game)
    assert p.sortie_treasures == 1 and p.sortie_horses == 1  # 一季的上限


def test_a_full_treasure_pool_pays_silver_into_the_report(monkeypatch):
    """FB-434：掉落池都拿齊了，擲中換成 dup_silver 兩，這筆也算進得失的銀兩（以前得失寫 +103、手上多了 153）。"""
    from tianxia import treasures

    game = _game()
    cfg = game.content.config.sortie
    cfg.rare_legend, cfg.rare_treasure, cfg.rare_horse = 0.0, 1.0, 0.0
    monkeypatch.setattr(treasures, "pick_pool", lambda *a, **k: None)
    p = game.state.player
    silver = p.stats["silver"]
    record, _ = _attack(game)
    assert p.stats["silver"] - silver == record.silver
    assert record.silver >= game.content.config.treasures.dup_silver


def test_season21_allows_three_sortie_treasures():
    assert real_content("season21").config.sortie.treasure_cap == 3


# ── Task 3：守、攪局、守勢行動 ──


def test_holding_pays_the_host_in_full():
    game = _game(faction="huang", at="huangjin_camp")
    p = game.state.player
    xinde = p.stats.get("xinde", 0)
    game.choose("act:train")
    assert p.stats["xinde"] - xinde == 35  # 自家經驗最高的一路：黃巾渠帥（心得 35）全額


def test_holding_with_precise_off_keeps_the_third():
    game = _game(faction="huang", at="huangjin_camp", precise=False)
    p = game.state.player
    xinde = p.stats.get("xinde", 0)
    game.choose("act:train")
    assert p.stats["xinde"] - xinde == drill_share(35, 0.3)


def test_a_duty_pays_like_holding():
    game = _game(faction="huang", at="huangjin_camp")
    p = game.state.player
    xinde = p.stats.get("xinde", 0)
    game.choose("act:duty")
    assert p.stats["xinde"] - xinde == 35


# ── Task 4：四階兩條來源 ──


def _tier4(game):
    return sum(n for mid, n in game.state.player.materials.items() if four_tiers.tier4_id(game.content, mid))


def _beat_figure(game, fid):
    game._figure_tier4(fid, game.content.squads[game.content.figures[fid].squad], game.state.battles[-1] if game.state.battles else
                       type("R", (), {"id": 1, "materials": []})())


def test_a_first_challenge_win_rolls_tier_four_once_per_figure_and_twice_a_season():
    game = _game()
    c, p = game.content, game.state.player
    c.config.four_tiers.challenge_chance = 1.0
    fids = list(c.figures)[:3]
    for fid in fids:
        _beat_figure(game, fid)
    assert _tier4(game) == 2 and p.tier4_challenge_drops == 2  # 一季最多 2 個
    _beat_figure(game, fids[0])
    assert _tier4(game) == 2  # 同一位第二次不擲
    assert p.tier4_wins == fids


def test_tier_four_challenge_roll_ignores_the_tier_three_cap():
    game = _game()
    c, p = game.content, game.state.player
    c.config.four_tiers.challenge_chance = 1.0
    p.figure_rare_drops = c.config.figure_rare_cap
    _beat_figure(game, next(iter(c.figures)))
    assert _tier4(game) == 1


def _battle(game, *, winner="guan", side="guan", acted=3, participants=12, mandate=False, rounds=6):
    c = game.content
    definition = next(b for b in c.battles.values() if b.timetable_event)
    battle = battle_instance.BattleInstance(battle_id=definition.id, record_id=7, phase="ended", round_number=rounds)
    battle.outcome_side = winner
    for i in range(participants):
        battle.participants[f"人{i}"] = battle_instance.BattleParticipant(name=f"人{i}", faction=side, neili=100, neili_cap=100)
    me = battle_instance.BattleParticipant(name="沈浪", faction=side, neili=100, neili_cap=100, acted_rounds=acted)
    battle.participants["沈浪"] = me
    if mandate:
        battle.battle_id = next((b.id for b in c.battles.values() if b.timetable_event and "tianming" in b.id), battle.battle_id)
    return battle, me


def test_a_timetable_showdown_win_gives_tier_four():
    game = _game()
    battle, me = _battle(game)
    lines: list[str] = []
    assert game._showdown_tier4(battle, me, lines) and _tier4(game) == 1 and "四階料" in lines[-1]


def test_no_tier_four_for_the_losers_the_idle_or_a_stalemate():
    game = _game()
    lines: list[str] = []
    battle, me = _battle(game, winner="huang")
    assert game._showdown_tier4(battle, me, lines) == []
    battle, me = _battle(game, acted=2)
    assert game._showdown_tier4(battle, me, lines) == []  # 參戰 13 人：門檻 3 回合
    battle, me = _battle(game, winner=None)
    assert game._showdown_tier4(battle, me, lines) == []  # 保底收場沒有贏家
    battle, me = _battle(game, acted=1, participants=3)
    assert game._showdown_tier4(battle, me, lines)  # 不到 10 人放寬到 1 回合
    assert _tier4(game) == 1


def test_the_mandate_battle_gives_no_tier_four():
    game = _game()
    c = game.content
    mandate = next((b for b in c.battles.values() if b.timetable_event and "tianming" in b.id), None)
    if mandate is None:
        return
    battle, me = _battle(game)
    battle.battle_id = mandate.id
    assert game._showdown_tier4(battle, me, []) == []


# ── Task 5：三階名器配方 ──


def test_a_season_picks_two_weapon_and_one_armor_tier_three_recipes():
    c = real_content("week7")
    picked = forge_secrets.active(c, 1)
    groups = [forge_secrets.group_of(r) for r in picked]
    assert groups.count("weapon:3") == 2 and groups.count("armor:3") == 1
    pool = [r for r in c.forge_secrets.values() if r.main.tier == 3 and not r.divine]
    assert sum(r.slot == "weapon" for r in pool) == 8 and sum(r.slot == "armor" for r in pool) == 3
