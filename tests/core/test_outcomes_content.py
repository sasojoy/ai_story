"""減法季批 4（主機側計畫 Task 4-1）：正式內容的隨口應對分岔——草稿（content/events_outcomes.json，PM 2026-10-24 初版、待 joy 潤）
併進 content/events/*.json 之後，四種設定都載得起來、每則最後一種是 fallback、作惡的那一種只在原事件有作惡選項的那八則。
yc_wilds_plow（人拉犁）本來沒有隨口應對：接線那一批跟開關一起補（PM 2026-10-25 第 7 件），寫成 outcomes_only——只在分岔開著的季
才畫那一顆，關著的季不多一顆鈕（tests/test_outcomes_answer.py 測選單）。"""
from collections import Counter
from pathlib import Path

import pytest

from conftest import real_content
from tianxia.atlas import region_of

ROOT = Path(__file__).resolve().parents[2]
MERGED = {
    "yz_zhuo_wild_horse", "yz_hall_yard_test", "yz_juma_toll", "yz_yan_loose_horses", "yz_market_salt",
    "jz_altar_talisman", "jz_lz_siegework", "jz_xqy_cellar", "jz_bm_pirates", "jz_hz_rentdebt",
    "ly_road_checkpoint", "ly_baima_beam", "ly_beimang_collapse", "ly_mengjin_grain",
    "yc_city_petition", "yc_river_overboard", "yc_wilds_toll", "yc_cs_grain_cart", "yc_sf_herbwife",
    "rn_mkt_rice", "rn_qiao_guoshui", "rn_wild_cellar", "rn_camp_palisade", "rn_hill_deserter",
    "ny_wan_gatecheck", "ny_road_brokencart", "ny_yu_ropetoll", "ny_xinye_wallgap", "ny_wilds_runaways",
    "yc_wilds_plow",  # 人拉犁：接線那一批併進來（outcomes_only）
}
EVIL = {  # 企劃者 2026-10-24 第 8 件 a：原事件有作惡固定選項的八則，各一種作惡後果（掘壕圍城的「動手」就是原本那一支）
    "yz_juma_toll": "collude", "yz_market_salt": "inform", "jz_lz_siegework": "fight", "ly_mengjin_grain": "loot",
    "rn_hill_deserter": "rob", "ny_road_brokencart": "plunder", "ny_yu_ropetoll": "extort", "ny_wilds_runaways": "betray",
}
REGIONS = {"youzhou", "jizhou", "luoyang", "yingru", "nanyang"}


@pytest.mark.parametrize("profile", [None, "season21", "week7"])
def test_the_branching_outcomes_load_under_every_profile(profile):
    content = real_content(profile)
    assert {e.id for e in content.events.values() if e.free_text is not None and e.free_text.outcomes} == MERGED


def test_each_ends_in_a_fallback_and_sits_in_one_of_the_five_regions():
    content = real_content()
    regions = Counter()
    for event_id in MERGED:
        event = content.events[event_id]
        assert event.free_text.outcomes[-1].kind == "fallback", event_id
        assert all(o.kind != "fallback" for o in event.free_text.outcomes[:-1]), event_id
        regions[region_of(content, event.locations[0]).id] += 1
    assert set(regions) == REGIONS and min(regions.values()) >= 4, regions


def test_the_evil_outcome_sits_right_before_the_fallback_in_exactly_the_eight():
    content = real_content()
    found = {}
    for event_id in MERGED:
        outcomes = content.events[event_id].free_text.outcomes
        for o in outcomes:
            if o.evil:
                found[event_id] = o.id
                assert outcomes[-2] is o and o.effect.contribution == 0, event_id
    assert found == EVIL


def test_the_rest_carry_a_mark_and_a_contribution():
    content = real_content()
    plain = [o for event_id in MERGED for o in content.events[event_id].free_text.outcomes[:-1] if not o.evil]
    assert len(plain) == 89 - 1  # 草稿 89 種有痕跡的後果（人拉犁的三種在接線那一批併進來），掘壕圍城的「動手」改成作惡
    assert all(o.effect.marks and 1 <= o.effect.contribution <= 6 for o in plain)
    assert sorted(o.id for event_id in MERGED for o in content.events[event_id].free_text.outcomes
                  if o.check is not None and o.check.stat == "best_of") == ["dig", "labor", "show"]


def test_only_the_plow_waits_for_the_switch():
    """人拉犁的那一顆只在分岔開著時才有（outcomes_only，沒有關著時套的 effect）；其餘 29 則關著照舊用 stat、effect、fail_effect。"""
    content = real_content()
    only = {e.id for e in content.events.values() if e.free_text is not None and e.free_text.outcomes_only}
    assert only == {"yc_wilds_plow"}
    plow = content.events["yc_wilds_plow"].free_text
    assert plow.stat == "str" and [o.id for o in plow.outcomes] == ["labor", "chase", "give", "leave"]


def test_the_draft_and_its_checker_are_gone():
    """規則都搬進 content.validate 了；草稿留著會被 test_explain2 掃到（名望只准 events/ 底下給）。"""
    assert not (ROOT / "content" / "events_outcomes.json").exists()
    assert not (ROOT / "scripts" / "check_outcomes.py").exists()
