"""減法季三道閘的引擎接線（減法季整合設計 4.2；主機側計畫 Task 2-4）：遭遇拍那一場的經驗、心得、銀兩乘疲勞（今天第幾場）與對手的檔；
45 級以後只有打出來的經驗算（不是仗的換心得，跨過 45 的那一截也是）。純規則在 tests/test_drill_gates.py。用正式內容（season21）（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

from unittest import mock

from jianfa_kit import jianfa_game, plain_game, ready

from tianxia import explore_one, team
from tianxia.encounter import EncounterResult


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _outing_fight(game, nth: int | None = None):
    """在所在地出門一趟、遇上一場（打贏；2d 起一趟只有一件事）；nth 給了先把今天記成已經打了 nth − 1 場。回那一場的戰報。"""
    p = game.state.player
    if nth is not None:
        p.fight_day, p.fights_today = game._pill_day(), nth - 1
    p.stamina = 250.0
    game.state.pending_event = None
    with mock.patch.object(explore_one, "draw", return_value="encounter"), _fight():
        game.choose("act:explore")
    return next(r for r in game.state.battles if r.id == game.state.battle_card)


def _camp(side="huang", level=1):
    """黃巾的人站在官軍大營：遭遇是北軍五校（難度 55、經驗 35），一級打它不吃對手那一道。"""
    return ready(jianfa_game(), side=side, loc="guan_camp", level=level)


def test_the_sixteenth_fight_pays_eight_tenths_and_the_thirtieth_three_tenths():
    full = _outing_fight(_camp(), nth=15)
    tired = _outing_fight(_camp(), nth=16)
    floor = _outing_fight(_camp(), nth=30)
    assert full.exp == 35 and tired.exp == round(35 * 0.8) and floor.exp == round(35 * 0.3)
    assert tired.xinde == round(30 * 0.8)


def test_fights_are_counted_and_reset_on_a_new_day():
    game = _camp()
    p = game.state.player
    _outing_fight(game)
    _outing_fight(game)
    assert p.fights_today == 2 and p.fight_day == game._pill_day()
    p.fight_day, p.fights_today = game._pill_day() - 1, 40  # 昨天打滿了：今天從頭算
    assert _outing_fight(game).exp == 35 and p.fights_today == 1


def test_the_tired_paragraph_says_so():
    game = _camp()
    _outing_fight(game, nth=20)
    assert "今天練得多了，收穫漸少。" in game.state.journal[0].lines[0]


def test_a_foe_two_bands_below_you_pays_one_tenth():
    game = ready(jianfa_game(), side="guan", loc="yingchuan", level=30)  # 城裡的地痞：難度 8（第 0 檔），三十級是第 3 檔
    record = _outing_fight(game)
    assert record.opponent == game.content.squads["dipi"].name
    assert record.exp == round(10 * 0.1)
    assert "對手已經配不上你" in game.state.journal[0].lines[0]


def test_closed_season_counts_nothing():
    game = ready(plain_game(), side="huang", loc="guan_camp")
    p = game.state.player
    p.stamina = 250.0
    with _fight():
        game.choose("explore:practice")
    assert (p.fights_today, p.fight_day) == (0, 0)


def _to(game, level: int, short: int):
    """本人站在 level 級、離下一級還差 short 點經驗。"""
    p = game.state.player
    p.member.level = level
    p.member.exp = team.level_cost(game.content.config, level) - short
    return p


def test_other_exp_climbs_to_45_and_the_rest_becomes_xinde():
    """44 → 45 用不是仗的經驗（操練、守）升得上，跨過 45 的那一截整截換心得；45 級以後不是仗的經驗全換心得、寫那一句（PM 2026-10-25 第 4 件）。"""
    game = _camp(side="guan")
    c = game.content
    host = c.squads["liangzhou_cavalry"]  # 經驗 40
    p = _to(game, 44, 10)
    xinde = p.stats.get("xinde", 0)
    msgs = game._drill_gains(host, 1.0, "hold")
    assert p.member.level == 45 and p.member.exp == 0
    over = 40 - 10
    gained = team.as_xinde(c, over)
    assert p.stats["xinde"] == xinde + 35 + gained  # 對手心得 35 照給，多的經驗換的心得另加
    assert team.CAPPED_XINDE.format(n=gained) in msgs
    msgs = game._drill_gains(host, 1.0, "hold")
    assert p.member.level == 45 and p.member.exp == 0 and team.CAPPED_XINDE.format(n=team.as_xinde(c, 40)) in msgs


def test_battle_exp_still_climbs_past_45():
    game = _camp()
    p = _to(game, 45, 20)
    record = _outing_fight(game)
    assert record.exp == 35 and p.member.level == 46


def test_camp_sparring_is_a_fight_past_45():
    """自家營寨跟同袍比劃算仗（PM 2026-10-25 第 5 件）：45 級以後照樣升級；也吃疲勞那一道。"""
    game = _camp(side="guan")
    p = _to(game, 45, 10)
    p.fight_day, p.fights_today = game._pill_day(), 0
    with mock.patch.object(explore_one, "draw", return_value="encounter"):
        game.choose("act:explore")
    assert p.member.level == 46 and p.fights_today == 1


def test_a_bounty_past_45_pays_xinde_not_exp():
    from tianxia import bounties

    game = _camp()
    p = _to(game, 45, 30)
    b = mock.Mock(kind="scout", deeds=0, id="x")
    with mock.patch.object(bounties, "_exp", return_value=40), mock.patch.object(bounties, "_silver", return_value=0), \
            mock.patch.object(bounties, "_attached", return_value=[]), mock.patch.object(bounties, "title", return_value="t"), \
            mock.patch.object(bounties, "issuer", return_value="i"), mock.patch.object(bounties, "_figure_thanks", return_value=[]):
        b.takers, b.done_by, b.prize = [p.name], [], ""
        msgs = bounties._complete(game.state, game.content, game.world, b)
    assert p.member.level == 45 and any(m.startswith("境界已到") for m in msgs) and "經驗 +40" not in msgs
