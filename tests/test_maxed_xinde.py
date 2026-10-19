"""正式季整合第 8 批：滿級之後的經驗 5 換 1 換成心得（設計 3.5），每一種給經驗的地方都一樣；同伴照拿經驗。"""
from __future__ import annotations

import random
from unittest import mock

from conftest import real_content

from tianxia import battle_instance, team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _game(faction="guan", at="huangjin_camp", level=50):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    p.member.level = level
    return game


def _attack(game):
    with mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40)):
        msgs = game.choose("act:train")
    record = game.state.battles[-1]
    return record, next(q for q in game.content.squads.values() if q.name == record.opponent), msgs


def test_the_conversion_is_five_to_one_and_only_at_the_top():
    game = _game()
    c, s = game.content, game.state
    assert c.config.maxed_exp_per_xinde == 5 and team.as_xinde(c, 24) == 4
    have = s.player.stats.get("xinde", 0)
    assert team.maxed_xinde(s, c, 50) == 10 and s.player.stats["xinde"] - have == 10
    s.player.member.level = 49
    assert team.maxed_xinde(s, c, 50) == 0 and s.player.stats["xinde"] - have == 10


def test_a_maxed_sortie_win_writes_xinde_not_exp():
    game = _game()
    xinde = game.state.player.stats.get("xinde", 0)
    record, squad, msgs = _attack(game)
    exp = squad.exp * 2  # 一類一顆：對手的兩倍（第 4 批）
    assert record.exp == 0 and record.xinde == squad.reward_xinde * 2 + exp // 5
    assert team.MAXED_XINDE.format(n=exp // 5) in " ".join(msgs)
    assert game.state.player.stats["xinde"] - xinde == record.xinde


def test_reaching_the_top_in_this_win_does_not_convert_the_rest():
    game = _game(level=49)
    p = game.state.player
    p.member.exp = team.level_cost(game.content.config, 49) - 1
    record, squad, _ = _attack(game)
    assert p.member.level == 50 and record.exp == squad.exp * 2 and record.xinde == squad.reward_xinde * 2


def test_a_maxed_hold_converts_the_host_exp():
    game = _game(faction="huang")
    host = game._sortie_host(game.content.locations["huangjin_camp"], "hold")
    xinde = game.state.player.stats.get("xinde", 0)
    msgs = game.choose("act:train")
    assert game.state.player.stats["xinde"] - xinde == host.reward_xinde + host.exp // 5
    assert team.MAXED_XINDE.format(n=host.exp // 5) in " ".join(msgs)


def test_maxed_showdown_pay_writes_xinde():
    game = _game()
    c = game.content
    c.config.showdown_pay.exp = 60
    definition = next(b for b in c.battles.values() if b.timetable_event)
    battle = battle_instance.BattleInstance(battle_id=definition.id, record_id=7, phase="ended", round_number=6)
    me = battle_instance.BattleParticipant(name="沈浪", faction="guan", neili=100, neili_cap=100, acted_rounds=6)
    battle.participants["沈浪"] = me
    changes = game._showdown_pay(battle, me, [])
    assert not any(x.startswith("經驗") for x in changes) and any(x.startswith("心得 +") for x in changes)


def test_maxed_bounty_reward_converts_in_every_season():
    """第 5 批只在 21 天季的懸賞換；第 8 批起每一種季都換（週末這裡）。"""
    from tianxia import bounties
    from tianxia.state import Bounty

    game = _game(faction=None)
    s, c = game.state, game.content
    b = Bounty(id="b1", kind="scout", faction="huang", week=1, expires=1e12, silver=20, deeds=1, location="changshe", takers=["沈浪"])
    s.world.bounties.append(b)
    bits = bounties.reward_bits(s, c, b)
    exp = bounties._exp(s, c, b)
    assert exp > 0 and bits.exp == 0 and bits.xinde >= exp // 5
    msgs = bounties._complete(s, c, game.world, b)
    assert not any(m.startswith("經驗") for m in msgs) and f"心得 +{exp // 5}" in msgs


def test_a_maxed_boss_duel_report_keeps_the_converted_xinde():
    """FB-450：滿級頭目戰的戰報得失，心得含換來的那一份（以前被頭目給的心得蓋掉：實際 +27、得失只寫 +15）。"""
    game = _game()
    s, c = game.state, game.content
    boss = next(b for b in c.duels.values() if b.exp >= 5 and b.xinde > 0)
    s.player.location = boss.locations[0]
    game._duel_start(boss)
    have = s.player.stats.get("xinde", 0)
    game._duel_finish("大勝", "（測試）")
    record = s.battles[-1]
    gained = s.player.stats["xinde"] - have
    assert gained > round(boss.xinde * c.config.duel.reward_share["大勝"]) and record.xinde == gained and record.exp == 0


def test_the_now_card_has_no_red_xinde_after_a_maxed_win():
    """FB-451：滿級打完仗，「剛剛」卡片底下不多一顆「心得 -N」：紀錄那一則的心得跟卡片得失的心得對得上。"""
    game = _game()
    record, _, msgs = _attack(game)
    assert record.xinde > 0
    assert "心得 -" not in game.battle_extra_html() and "心得 -" not in game.battle_extra_html(for_card=True)
