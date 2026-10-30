"""療傷只在醫館（企劃者 2026-10-12「療傷我認為不能隨地療傷，應該去城鎮有醫館的地方」；tianxia/clinic.py）。
測試內容把 Config.heal_at_clinic 關著，這裡用正式內容。"""

import random
from pathlib import Path

import pytest

from tianxia import atlas, bot, clinic, skillview, team
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game

CONTENT_DIR = Path(__file__).parents[2] / "content"


@pytest.fixture(scope="module")
def real():
    content = load_content(CONTENT_DIR)
    content.config.auto_open_first_season = True
    return content


def _game(real, where="yingchuan", injury=40.0, silver=100):
    game = Game.new(real, "甲", rng=random.Random(0), graduated=True)
    p = game.state.player
    p.location, p.journey = where, None
    p.member.injury, p.member.neili = injury, 50.0
    p.stats["silver"] = silver
    return game


def test_every_region_has_a_clinic_and_the_first_stop_out_of_the_prologue_is_one(real):
    places = clinic.clinics(real)
    assert {atlas.region_of(real, loc).id for loc in places} == {region.id for region in real.map.regions}
    assert real.scenario.start_location in places


def test_away_from_a_clinic_healing_is_refused_and_names_the_nearest(real):
    game = _game(real, where="yingshui")  # 潁水河畔：隔壁就是潁川郡
    p = game.state.player
    assert game.heal() == ["這裡沒有醫館，最近的在潁川郡（陽翟）。"]
    assert (p.member.injury, p.stats["silver"]) == (40.0, 100)
    assert skillview.heal_button(game.state, real) == {
        "ok": False, "why": "這裡沒有醫館，最近的在潁川郡（陽翟）。", "clinic": "這裡沒有醫館，最近的在潁川郡（陽翟）。", "note": None,
    }
    assert "act:heal" not in [o.id for o in game.options(odds=False)]


def test_no_injury_says_so_before_the_clinic(real):
    game = _game(real, where="yingshui", injury=0.0)
    assert game.heal() == ["氣血無恙，不用療傷。"]


@pytest.mark.smoke
def test_on_the_road_there_is_no_clinic(real):
    game = _game(real)
    game.choose("move:yingshui")
    assert game.state.player.journey is not None
    assert not clinic.here(game.state, real) and game.heal()[0].startswith("這裡沒有醫館")


def test_at_a_clinic_the_place_offers_healing_at_the_same_price(real):
    game = _game(real)
    p = game.state.player
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert option.enabled and option.label == f"{clinic.HEAL}（內傷 40・{team.heal_cost(real, p.member)} 兩）"
    assert skillview.heal_button(game.state, real) == {"ok": True, "why": None, "clinic": None, "note": "內傷 40・20 兩"}
    stamina = p.stamina
    msgs = game.choose("act:heal")
    assert "療傷完畢，內傷 -40、氣血回滿（銀兩 -20）。" in msgs
    assert (p.member.injury, p.member.neili, p.stats["silver"], p.stamina) == (0.0, None, 80, stamina)
    assert game.state.journal[0].title == "療傷・潁川郡（陽翟）"
    assert "act:heal" not in [o.id for o in game.options(odds=False)]  # 沒有內傷就不畫


def test_penniless_greys_the_option(real):
    game = _game(real, silver=0)
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert not option.enabled and "銀兩不足" in option.label


def test_short_of_silver_heals_what_it_can(real):
    """PM 2026-10-12：銀兩不夠全治時能治多少治多少（每一兩治 2 點），鈕上寫治幾點、還剩幾點。"""
    game = _game(real, injury=40.0, silver=12)
    p = game.state.player
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert option.enabled and option.label == f"{clinic.HEAL}（治 24 點・12 兩（還剩 16 點））"
    assert skillview.heal_button(game.state, real)["note"] == "治 24 點・12 兩（還剩 16 點）"
    assert game.choose("act:heal")[0] == "銀兩只夠治一部分：內傷 -24，還剩 16 點（銀兩 -12）。"
    assert (p.member.injury, p.stats["silver"]) == (16.0, 0)
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert not option.enabled


def test_poor_bots_still_go_when_they_can_heal_a_useful_part(real):
    game = _game(real, where="yingshui", injury=1000.0, silver=bot.CLINIC_MIN_SILVER)
    assert bot.clinic_hop(game) == "yingchuan"
    game.state.player.stats["silver"] = bot.CLINIC_MIN_SILVER - 1
    assert bot.clinic_hop(game) is None


def test_time_and_meditation_never_cure_the_injury(real):
    game = _game(real, where="yingshui")
    game.advance(12 * 3600)
    member = game.state.player.member
    assert member.injury == 40.0
    _, cap = team.member_neili(real, member, team.con_of(game.state, real, game.world, "player"))
    assert team.member_neili(real, member, team.con_of(game.state, real, game.world, "player"))[0] == cap - 40.0


def test_with_the_switch_off_healing_works_anywhere(real):
    off = real.model_copy(update={"config": real.config.model_copy(update={"heal_at_clinic": False})})
    game = _game(off, where="yingshui")
    assert game.heal()[0].startswith("療傷完畢")


def test_a_clinic_is_required_when_the_switch_is_on(real):
    bare = real.model_copy(deep=True)
    for loc in bare.locations.values():
        loc.tags = [tag for tag in loc.tags if tag != clinic.CLINIC_TAG]
    with pytest.raises(ContentError, match="醫館"):
        validate(bare)


def test_bots_detour_to_the_nearest_clinic_when_the_injury_is_heavy(real):
    game = _game(real, where="yingshui", injury=10.0)
    assert bot.clinic_hop(game) is None  # 輕傷：不繞路
    game.state.player.member.injury = 100.0
    assert bot.clinic_hop(game) == "yingchuan"
    game.state.player.stats["silver"] = 0
    assert bot.clinic_hop(game) is None  # 一兩都沒有：去了也白去
    game = _game(real, injury=100.0)
    assert bot.clinic_hop(game) is None and bot.wants_heal(game)  # 已經在醫館：就地療傷


def test_heavy_injury_puts_the_clinic_ahead_of_orders(real):
    from tianxia import bot_policy  # noqa: PLC0415

    game = _game(real, where="yingshui", injury=0.0)
    _, cap = team.member_neili(real, game.state.player.member, team.con_of(game.state, real, game.world, "player"))
    game.state.player.member.injury = 0.2 * cap
    assert bot_policy._clinic_score(game) == bot_policy.CLINIC_MOVE_SCORE < bot_policy.ORDER_SCORE
    game.state.player.member.injury = 0.3 * cap
    assert bot_policy._clinic_score(game) == bot_policy.CLINIC_URGENT_SCORE > bot_policy.SUMMONS_SCORE
    assert bot.injury_share(game) == pytest.approx(0.3)


def test_a_crippled_bot_that_cannot_pay_stops_fighting(real):
    from tianxia import bot_policy  # noqa: PLC0415

    game = _game(real, where="yingshui", injury=0.0, silver=0)
    _, cap = team.member_neili(real, game.state.player.member, team.con_of(game.state, real, game.world, "player"))
    game.state.player.member.injury = 0.3 * cap
    assert bot_policy._crippled(game)
    game.state.player.stats["silver"] = bot.CLINIC_MIN_SILVER
    assert not bot_policy._crippled(game)  # 湊得出錢：先去醫館
    game.state.player.member.injury, game.state.player.stats["silver"] = 0.2 * cap, 0
    assert not bot_policy._crippled(game)  # 傷還不重：照打


def test_zhongjing_owes_takes_thirty_percent_off_and_the_doctor_mentions_it_once(real):
    """《符水與湯藥》湯藥那條路的「仲景欠你一次」（旗標 zhongjing_owes）：這一季療傷照 Config.zhongjing_clinic_share 收，
    第一次用到時大夫多一句，之後不再說。"""
    game = _game(real, injury=40.0, silver=100)
    s = game.state
    member = s.player.member
    base = team._price_here(s, real)
    full = team.heal_cost(real, member, s)
    s.player.flags.add(clinic.ZHONGJING)
    assert team._price_here(s, real) == pytest.approx(base * real.config.zhongjing_clinic_share)
    owed = team.heal_cost(real, member, s)
    assert owed < full
    msgs = game.heal()
    assert s.player.stats["silver"] == 100 - owed
    assert any("南陽張家二郎的信" in m for m in msgs)
    member.injury = 40.0
    assert not any("南陽張家二郎的信" in m for m in game.heal())
