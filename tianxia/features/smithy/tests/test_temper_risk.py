"""淬煉衝階（Joy 2026-11-10「像天堂衝階才有那個稀有度」，失敗選「退一級」）：安全線以內必成，過了照 temper_odds 擲，
失敗料錢照收、淬煉次數退一；淬到 temper_rumor_from 以上天下大事寫一筆；衝階關著（temper_risk_max 0）照舊。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import equipment
from tianxia.features.smithy import smithing
from tianxia.state import Equipment


def _risk(content, safe=None, odds=None, top=10, rumor=9):
    rule = content.config.weapons
    rule.enabled = True
    rule.temper_risk_max, rule.temper_rumor_from = top, rumor
    rule.temper_safe_by_quality = safe if safe is not None else {"下品": 3, "中品": 4, "上品": 5}
    rule.temper_odds = odds if odds is not None else [0.75, 0.6, 0.45, 0.35, 0.25, 0.18, 0.12]
    return content


def _blade(quality="下品", tempers=0, tier=1):
    return Equipment(id="刀:1", slot="weapon", name="試刀", kind="刀", attribute="剛", tier=tier, quality=quality, tempers=tempers)


def _smith(content, world, blade, silver=500, mats=20):
    from tianxia.engine import Game
    game = Game.new(content, "試刀客", rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.location, p.stats["silver"], p.weapon, p.materials = "town", silver, blade, {"gang_1": mats}
    game.sync(0.0)
    return game


def test_safe_line_and_odds_follow_quality(content):
    _risk(content)
    assert equipment.temper_cap(_blade(), content) == 10  # 衝階開著：上限一律 10，不照品質
    assert [equipment.temper_safe(_blade(q), content) for q in ("下品", "中品", "上品")] == [3, 4, 5]
    chances = [equipment.temper_chance(_blade("下品", n), content) for n in range(11)]
    assert chances[:3] == [1.0, 1.0, 1.0]  # +1～+3 必成
    assert chances[3:10] == [0.75, 0.6, 0.45, 0.35, 0.25, 0.18, 0.12] and chances[10] == 0.0  # 淬滿了是 0
    assert equipment.temper_chance(_blade("上品", 5), content) == 0.75  # 上品的安全線多兩層


def test_risk_off_keeps_the_old_cap_and_always_succeeds(content):
    content.config.weapons.temper_max_by_quality = {"下品": 5}
    assert content.config.weapons.temper_risk_max == 0
    assert equipment.temper_cap(_blade(), content) == 5 and equipment.temper_chance(_blade(tempers=4), content) == 1.0


def test_failure_drops_one_level_and_still_charges(content, world):
    _risk(content, odds=[0.0])  # 過了安全線一定失敗
    game = _smith(content, world, _blade(tempers=3))
    p = game.state.player
    msgs = smithing.temper(game.state, content)
    assert p.weapon.tempers == 2 and p.materials == {"gang_1": 19} and p.temper_seq == 1
    assert msgs[0] == smithing.TEMPER_DOWN.format(name="試刀", n=2)


def test_success_beyond_safe_and_rumor_at_nine(content, world):
    _risk(content, odds=[0.9999])  # 幾乎一定成（1.0 會被當成安全線以內、不擲）
    game = _smith(content, world, _blade(tempers=8))
    p = game.state.player
    assert smithing.temper(game.state, content)[0] == smithing.TEMPER_UP.format(name="試刀", n=9)
    assert p.weapon.tempers == 9 and p.temper_seq == 1
    texts = [r.text for r in game.state.world.rumors]
    assert smithing.TEMPER_RUMOR.format(who="試刀客", name="試刀", n=9) in texts
    smithing.temper(game.state, content)
    assert p.weapon.tempers == 10 and smithing.temper_problem(game.state, content) == smithing.FULL


def test_safe_tempers_do_not_roll_or_rumor(content, world):
    _risk(content, odds=[0.0])
    game = _smith(content, world, _blade())
    for _ in range(3):
        smithing.temper(game.state, content)
    assert game.state.player.weapon.tempers == 3 and game.state.player.temper_seq == 0


def test_rolls_are_deterministic_by_name_and_count(content, world):
    _risk(content, odds=[0.5])
    runs = []
    for _ in range(2):
        game = _smith(content, world, _blade(tempers=3), silver=5000, mats=60)
        for _ in range(40):
            smithing.temper(game.state, content)
        runs.append(game.state.player.weapon.tempers)
    assert runs[0] == runs[1]


def test_option_label_shows_the_odds_beyond_the_safe_line(content, world):
    _risk(content)
    game = _smith(content, world, _blade(tempers=3))
    assert smithing.temper_option(game.state, content).label.endswith("・成功 75%）")


def test_real_content_turns_the_risk_on_with_a_lower_step():
    content = real_content()
    for rule in (content.config.weapons, content.config.armor):
        assert rule.temper_risk_max == 10 and rule.temper_rumor_from == 9
        assert rule.temper_safe_by_quality == {"下品": 3, "中品": 4, "上品": 5}
        assert abs(rule.temper_step * 10 - 0.07) < 1e-9  # +10 等於舊的上品淬滿（7 次 × 1%）
