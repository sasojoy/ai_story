"""探索一顆（減法季整合設計 4.1；主機側實作計畫 Task 2-1 的六張表、Task 2-2 的抽一件事）的純規則。

批 0 的 `Config.jianfa` 還沒到：數字吃 `tianxia/jianfa_numbers.py` 的 `JianfaNumbers`（批 0 到了之後併進 `JianfaRules`），
這裡直接建它。開關、接線（選單只剩一顆探索、結算）在批 0 之後的 Task 2-3。

2d（企劃者 2026-10-26「只抽一件事情，然後體力先維持不動」，同天體力改 15）：以前一趟連抽三拍（同一類最多兩拍、要選的拍放最後、
接了討伐懸賞至少一拍是遭遇）；現在一趟只抽一件事，那些規則作廢，斷言三拍的舊測試照新規則改。"""
import ast
import random
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import explore_one
from tianxia.explore_one import ENCOUNTER, EVENT, INSIGHT, KINDS, MATERIAL
from tianxia.jianfa_numbers import ExploreOneTable, JianfaNumbers

CFG = JianfaNumbers()
TABLES = {t.name: t for t in CFG.explore_tables}


def _place(*tags: str, danger: int = 1) -> SimpleNamespace:
    """kind_of／weights 只讀 tags 與 danger。"""
    return SimpleNamespace(tags=list(tags), danger=danger)


def _row(t: ExploreOneTable) -> dict[str, int]:
    return {EVENT: t.event, ENCOUNTER: t.encounter, MATERIAL: t.material, INSIGHT: t.insight}


# ── 十八張表（Task 2-1 的六張；企劃者 2026-10-30 細分）──────────────────────────


def test_eighteen_tables_as_joy_approved_them():
    """企劃者 2026-10-30「城內多事件、少材料、少敵人，地點要做出差異化」：六種地點細分成十八張表（事件／遭遇／素材／感悟），
    每張掛在六種地點之一。"""
    assert {k: (t.kind, *_row(t).values()) for k, t in TABLES.items()} == {
        "營寨": ("camp", 15, 60, 15, 10),
        "官署": ("town", 80, 5, 5, 10), "市集": ("town", 65, 5, 25, 5), "塢堡": ("town", 45, 35, 10, 10),
        "里巷": ("town", 70, 5, 15, 10), "城鎮": ("town", 75, 5, 10, 10),
        "寺觀": ("temple", 40, 0, 10, 50), "書院": ("temple", 55, 0, 5, 40), "莊院": ("temple", 65, 10, 15, 10),
        "結社": ("temple", 50, 25, 5, 20),
        "渡口": ("ford", 45, 30, 15, 10), "河畔": ("ford", 20, 25, 45, 10),
        "山寨": ("hill", 10, 60, 20, 10), "洞窟": ("hill", 10, 10, 40, 40), "山林": ("hill", 10, 30, 45, 15),
        "官道": ("wild", 25, 50, 15, 10), "古戰場": ("wild", 10, 55, 20, 15), "野外": ("wild", 10, 50, 30, 10),
    }
    assert len(CFG.explore_tables) == len(TABLES) == 18
    assert {t.kind for t in CFG.explore_tables} == set(explore_one.PLACE_WORDS)


def test_town_tables_give_more_events_fewer_materials_and_fewer_foes_than_the_wilds():
    """城裡（官署、里巷、城鎮）比城外每一張表事件多、遭遇少；城鎮的素材比任何城外的表少。"""
    towns = [TABLES[n] for n in ("官署", "里巷", "城鎮")]
    outside = [t for t in CFG.explore_tables if t.kind in ("wild", "hill", "ford", "camp")]
    assert min(t.event for t in towns) > max(t.event for t in outside)
    assert max(t.encounter for t in towns) < min(t.encounter for t in outside if t.name != "洞窟")
    assert TABLES["城鎮"].material < min(t.material for t in outside)


def test_a_table_that_does_not_add_up_to_100_is_rejected():
    with pytest.raises(ValidationError, match="100"):
        ExploreOneTable(kind="town", tags=["城鎮"], event=60, encounter=15, material=15, insight=15)


def test_each_tag_falls_in_one_table_only():
    seen = Counter(tag for t in CFG.explore_tables for tag in t.tags)
    assert seen and max(seen.values()) == 1
    clash = [t.model_copy(update={"tags": t.tags + ["城鎮"]}) if t.kind == "temple" else t for t in CFG.explore_tables]
    with pytest.raises(ValidationError, match="城鎮"):
        JianfaNumbers(explore_tables=clash)


def test_a_kind_may_have_several_tables_but_names_are_unique():
    more = [*CFG.explore_tables, ExploreOneTable(kind="town", tags=["新標籤"], event=25, encounter=25, material=25, insight=25)]
    assert len(JianfaNumbers(explore_tables=more).explore_tables) == 19
    twice = [*CFG.explore_tables, ExploreOneTable(name="官署", kind="town", tags=["新標籤"], event=25, encounter=25, material=25, insight=25)]
    with pytest.raises(ValidationError, match="官署"):
        JianfaNumbers(explore_tables=twice)


def test_every_real_location_falls_in_a_table_by_its_own_tags():
    """正式內容每一處都靠自己的標籤歸得到一張（不是掉到「其餘」）；兩張都對得上的照順序，營排第一。"""
    locs = real_content().locations
    assert locs
    unmatched = [loc.id for loc in locs.values() if explore_one.match(CFG, loc.tags) is None]
    assert unmatched == []
    kinds = {loc_id: explore_one.kind_of(CFG, loc).kind for loc_id, loc in locs.items()}
    assert {k: kinds[k] for k in (
        "yingchuan", "haozu_fort", "guangzong", "julu_altar", "baima_temple", "mentor_hut", "yingshui",
        "mengjin_ford", "yingchuan_wilds", "changshe", "nanyang_road", "songshan_foot", "lulin_zhai", "guan_camp",
    )} == {
        "yingchuan": "town", "haozu_fort": "town",  # 塢堡算城（設計 4.1；現行 explore_mix 是營）
        "guangzong": "camp", "julu_altar": "camp",  # 「城池、營寨」「祭壇、營寨」：營排第一（設計「營（營寨、道壇）」）
        "baima_temple": "temple", "mentor_hut": "temple", "yingshui": "ford", "mengjin_ford": "ford",
        "yingchuan_wilds": "wild", "changshe": "wild", "nanyang_road": "wild",
        "songshan_foot": "hill", "lulin_zhai": "hill", "guan_camp": "camp",
    }


def test_tags_no_table_names_fall_to_the_last_table():
    assert explore_one.match(CFG, ["酒肆", "醫館"]) is None
    assert explore_one.kind_of(CFG, _place("酒肆")) is CFG.explore_tables[-1]
    assert CFG.explore_tables[-1].kind == "wild"


# ── 這一處這一趟的比重 ──────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(TABLES))
def test_one_star_places_draw_by_the_table_as_written(kind):
    t = TABLES[kind]
    assert explore_one.weights(CFG, _place(t.tags[0]), has_foes=True) == _row(t)


def test_each_star_past_the_first_moves_ten_from_event_to_encounter_within_5_to_80():
    w = explore_one.weights
    assert w(CFG, _place("城鎮", danger=2), has_foes=True) == {EVENT: 65, ENCOUNTER: 15, MATERIAL: 10, INSIGHT: 10}
    assert w(CFG, _place("野外", danger=2), has_foes=True) == {EVENT: 5, ENCOUNTER: 60, MATERIAL: 30, INSIGHT: 10}  # 事件夾在 5
    assert w(CFG, _place("野外", danger=3), has_foes=True) == {EVENT: 5, ENCOUNTER: 70, MATERIAL: 30, INSIGHT: 10}
    assert w(CFG, _place("營寨", danger=3), has_foes=True) == {EVENT: 5, ENCOUNTER: 80, MATERIAL: 15, INSIGHT: 10}  # 遭遇夾在 80


def test_no_foe_here_gives_the_encounter_share_to_the_other_three():
    got = explore_one.weights(CFG, _place("城鎮"), has_foes=False)
    assert got == {EVENT: 75, ENCOUNTER: 0, MATERIAL: 10, INSIGHT: 10}


def test_a_bounty_here_makes_the_whole_trip_that_bounty_encounter():
    """2d：一趟只有一件事，接了這裡的討伐懸賞這一趟就是遭遇（以前遭遇那一欄 +30、至少一拍是遭遇）；任何地點、任何危險度、
    有沒有對手（懸賞那一路易手了也找得到）都一樣。"""
    w = explore_one.weights
    only = {EVENT: 0, ENCOUNTER: 100, MATERIAL: 0, INSIGHT: 0}
    assert explore_one.encounter_only() == only
    for tag, danger, foes in (("寺院", 1, True), ("野外", 1, True), ("營寨", 3, True), ("城鎮", 1, False), ("山林", 2, False)):
        assert w(CFG, _place(tag, danger=danger), has_foes=foes, bounty_here=True) == only, tag
    assert w(CFG, _place("野外"), has_foes=True, bounty_here=False) != only  # 交了差回原表
    assert not hasattr(CFG, "bounty_encounter_bonus") and not hasattr(CFG, "beats")


def test_the_outing_costs_six_stamina_by_default():
    """企劃者 2026-10-26：一趟一件事；體力企劃者 2026-10-27 改回 6（曾是 18、15）。"""
    assert CFG.explore_stamina == 6


# ── 抽一件事、出門一趟 ──────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(TABLES))
def test_single_beats_follow_each_table_within_5_points(kind):
    row = _row(TABLES[kind])
    rng = random.Random(f"單拍|{kind}")
    got = Counter(explore_one.roll(rng, row) for _ in range(1000))
    for k, share in row.items():
        assert abs(got[k] / 10 - share) <= 5, (kind, k, got)


def _outings(row, n=600, **kw):
    return [explore_one.draw(random.Random(f"出門|{i}"), row, **kw) for i in range(n)]


@pytest.mark.parametrize("kind", sorted(TABLES))
def test_an_outing_is_one_thing_that_follows_the_table_within_5_points(kind):
    """2d：一趟就是一件事（以前三拍、要選的拍最多一個，城裡約八成的出門帶一則事件），所以每一類的機會就是表上的數字。"""
    row = _row(TABLES[kind])
    got = Counter(_outings(row, n=1000))
    assert set(got) <= set(KINDS) and all(isinstance(k, str) for k in got)
    for k, share in row.items():
        assert abs(got[k] / 10 - share) <= 5, (kind, k, got)


def test_town_outings_bring_an_event_about_three_quarters_of_the_time():
    outings = _outings(_row(TABLES["城鎮"]), n=1000)
    share = sum(kind == EVENT for kind in outings) / len(outings)
    assert 0.70 <= share <= 0.80


def test_a_bounty_here_makes_every_outing_an_encounter():
    for kind in ("寺觀", "城鎮", "野外"):
        row = explore_one.weights(CFG, _place(TABLES[kind].tags[0]), has_foes=kind != "城鎮", bounty_here=True)
        assert set(_outings(row)) == {ENCOUNTER}, kind


def test_a_place_with_no_foe_never_draws_an_encounter():
    row = explore_one.weights(CFG, _place("營寨", danger=3), has_foes=False)
    assert ENCOUNTER not in set(_outings(row))


def test_sensing_here_twice_in_a_row_is_not_drawn_but_events_are_left_to_the_rotation():
    """同一處連兩趟要選的那件事不同一則：上一趟在這裡是感悟，這一趟不抽感悟；事件的不重照舊交給 events.rotation_pool。"""
    row = _row(TABLES["寺觀"])
    assert INSIGHT not in set(_outings(row, last_choice=INSIGHT))
    assert EVENT in set(_outings(row, last_choice=EVENT))
    assert INSIGHT in set(_outings(row, last_choice=EVENT))


def test_when_nothing_can_be_drawn_the_outing_is_a_material():
    empty = {EVENT: 0, ENCOUNTER: 0, MATERIAL: 0, INSIGHT: 0}
    assert explore_one.draw(random.Random(1), empty) == MATERIAL
    only_insight = {EVENT: 0, ENCOUNTER: 0, MATERIAL: 0, INSIGHT: 100}
    assert explore_one.draw(random.Random(1), only_insight) == INSIGHT
    assert explore_one.draw(random.Random(1), only_insight, last_choice=INSIGHT) == MATERIAL  # 抽不了感悟、其餘都是 0：補素材


# ── 亂數 ─────────────────────────────────────────────────────


def test_the_same_seed_draws_the_same_outing():
    row = _row(TABLES["渡口"])
    one = [explore_one.draw(explore_one.rng_for(1, "沈浪", n, "抽拍"), row) for n in range(50)]
    two = [explore_one.draw(explore_one.rng_for(1, "沈浪", n, "抽拍"), row) for n in range(50)]
    assert one == two
    assert len(set(one)) > 1  # 第幾趟不同，抽出來的不一樣


def test_drawing_never_touches_the_shared_random():
    row = _row(TABLES["山林"])
    random.seed(7)
    expected = random.random()
    random.seed(7)
    explore_one.draw(explore_one.rng_for(1, "沈浪", 3, "抽拍"), explore_one.weights(CFG, _place("山林"), has_foes=True))
    explore_one.roll(random.Random(2), row)
    assert random.random() == expected


def test_explore_one_does_not_import_the_engine():
    tree = ast.parse(Path(explore_one.__file__).read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom | ast.Import) for a in n.names}
    names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any("engine" in name for name in names)
