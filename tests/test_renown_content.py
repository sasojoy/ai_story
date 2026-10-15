"""附錄 A、B 的內容（名聲設計 5.3）：20 則各一顆、俠 8 寇 12；新事件；綠林山寨的寨門盤問。"""
from collections import Counter

from conftest import real_content

APPENDIX_A = {
    "rn_mkt_rice": ("俠", 2), "jz_bm_pirates": ("俠", 2), "jz_hz_rentdebt": ("俠", 2), "yc_dm_stockade": ("俠", 2),
    "yc_wilds_toll": ("俠", 1), "ly_mengjin_capsize": ("俠", 1), "beggar": ("俠", 1), "sc_rnmk_thief": ("俠", 1),
    "yc_river_shacks": ("寇", 1), "ny_road_brokencart": ("寇", 1), "yz_juma_toll": ("寇", 1), "ny_yu_ropetoll": ("寇", 1),
    "yc_wilds_horse": ("寇", 1), "rn_hill_diggers": ("寇", 1), "sc_xy_pickpocket": ("寇", 1), "tavern_brawl": ("寇", 1),
    "ly_road_courier": ("寇", 2), "ly_mengjin_grain": ("寇", 2), "jizhou_baima_crossing": ("寇", 2), "sc_mt_salt": ("寇", 2),
}


def test_each_listed_event_has_one_needs_choice():
    c = real_content("weekend")
    for event_id, (way, tier) in APPENDIX_A.items():
        needs = [ch.needs for ch in c.events[event_id].choices if ch.needs is not None]
        assert [(n.path, n.tier) for n in needs] == [(way, tier)], event_id
    ways = Counter(way for way, _ in APPENDIX_A.values())
    assert ways == {"俠": 8, "寇": 12}


def test_the_rogue_ways_pay_more_and_half_use_evil_practice():
    c = real_content("weekend")
    practiced = 0
    for event_id, (way, _) in APPENDIX_A.items():
        ev = c.events[event_id]
        (mine,) = [ch for ch in ev.choices if ch.needs is not None]
        others = [ch for ch in ev.choices if ch.needs is None]
        if way == "寇":
            assert mine.effect.stats.get("evil", 0) >= 2, event_id
            loot = mine.effect.stats.get("silver", 0) + 10 * sum(mine.effect.materials.values())
            assert loot > max(ch.effect.stats.get("silver", 0) for ch in others), event_id
            practiced += mine.check is not None and mine.check.practice == "evil"
        else:
            assert mine.effect.stats.get("good", 0) >= 2, event_id
    assert practiced >= 6


def test_new_events_exist_with_their_conditions():
    c = real_content("weekend")
    assert {"xia_grain", "xia_tipoff", "lulin_gate", "lulin_spoils", "lulin_drill", "lulin_snare"} <= set(c.events)
    for event_id in ("xia_grain", "xia_tipoff"):
        ev = c.events[event_id]
        assert (ev.condition.virtue_path, ev.condition.virtue_min, ev.weight) == ("俠", 2, 0.3)
    assert c.events["lulin_spoils"].condition.virtue_path == "寇"


def test_the_fort_gate_has_both_ways():
    c = real_content("weekend")
    needs = [(ch.needs.path, ch.needs.tier) for ch in c.events["lulin_gate"].choices if ch.needs is not None]
    assert needs == [("俠", 2), ("寇", 1)]
