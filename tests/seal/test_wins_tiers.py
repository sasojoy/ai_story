"""季末四階的純規則（減法季整合設計 3.3；計畫第五節 Task 3c-2、5.0 第 11、13 條；企劃者 2026-10-24 第 3、4 件）。

贏的那一軍：一 → 三 → 四；豪強：替贏的那一軍那一本過門檻的二 → 三 → 四，那一本不到才看輸的那一本（三 → 四）；輸的那一軍：三 → 四。
和局（結局的 winner 是 None）：兩軍都照輸的切、豪強照兩本合計。名次只在過了門檻的人裡排；20 人與 2,000 人同一條規則。
用正式內容（season21）的劇本與結局（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。開季收季的那一支（test_season_end_tiers.py）留給接線。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import wins
from tianxia.models import JianfaRules, TierRules
from tianxia.state import PlayerState, WorldState

GUAN_WINS, HUANG_WINS, DRAW = "s1_pacified", "s1_turbans_hold", "s1_gentry"


@pytest.fixture(scope="module")
def content():
    return real_content("season21")


def _p(name: str, faction: str | None, contrib: int = 0, ledgers: dict[str, int] | None = None, ally: str | None = None):
    p = PlayerState(name=name, location="changshe", stats={}, stamina=0, faction=faction, ally=ally)
    p.ledgers = dict(ledgers or {})
    p.contrib = contrib if ledgers is None else sum(p.ledgers.values())
    return p


def _army(faction: str, n: int, base: int = 1000) -> list[PlayerState]:
    """n 個過門檻、貢獻都不一樣的人（第 1 名最多）。"""
    return [_p(f"{faction}{i:04d}", faction, base + n - i) for i in range(n)]


def _settle(content, ending: str, players: list[PlayerState], rules: JianfaRules | None = None):
    return wins.settle(WorldState(ending_id=ending), content, players, rules)


def _count(result, names, tier) -> int:
    return sum(1 for name in names if result[name].tier == tier)


def test_eight_season_one_endings_name_the_winner(content):
    """企劃者 2026-10-24：三種官軍贏、三種黃巾贏、兩種豪強的結局（和局）是 None。"""
    endings = {e.id: e.winner for e in content.scenario.endings if e.season_one}
    assert endings == {
        "s1_tianming_guan": "guan", "s1_tianming_huang": "huang",
        "s1_huangtian": "huang", "s1_pacified": "guan",
        "s1_warlords": None, "s1_turbans_hold": "huang", "s1_turbans_retreat": "guan", "s1_gentry": None,
    }
    assert all(e.winner is None for e in content.scenario.endings if not e.season_one)
    assert wins.winner_of(WorldState(ending_id=GUAN_WINS), content) == "guan"
    assert wins.winner_of(WorldState(ending_id=HUANG_WINS), content) == "huang"
    assert wins.winner_of(WorldState(ending_id=DRAW), content) is None
    assert wins.winner_of(WorldState(), content) is None  # 還沒收季


def test_mandate_endings_agree_with_their_winner(content):
    """天命之爭得天命的那一軍 → 結局（時刻表的 mandate_endings）跟結局自己寫的 winner 是同一軍。"""
    from tianxia.seal import mandate_event

    event = mandate_event(content)
    assert event is not None and event.mandate_endings
    endings = {e.id: e for e in content.scenario.endings}
    assert {side: endings[ending].winner for side, ending in event.mandate_endings.items()} == {"guan": "guan", "huang": "huang"}


@pytest.mark.parametrize("n", [20, 2000])
def test_same_shares_for_twenty_and_two_thousand(content, n):
    guan, huang = _army("guan", n), _army("huang", n)
    result = _settle(content, GUAN_WINS, guan + huang)
    won, lost = [p.name for p in guan], [p.name for p in huang]
    assert [_count(result, won, t) for t in (1, 2, 3, 4)] == [n // 10, 0, n * 4 // 10 - n // 10, n - n * 4 // 10]
    assert [_count(result, lost, t) for t in (1, 2, 3, 4)] == [0, 0, n * 4 // 10, n - n * 4 // 10]
    top = result[guan[0].name]
    assert (top.tier, top.title, top.ledger_used, top.points, top.rank, top.of) == (1, "漢室忠良", "guan", guan[0].contrib, 1, n)
    last = result[huang[-1].name]
    assert (last.tier, last.title, last.ledger_used, last.rank, last.of) == (4, "隨軍", "huang", n, n)


def test_huang_winning_gets_its_own_first_tier_title(content):
    result = _settle(content, HUANG_WINS, _army("guan", 10) + _army("huang", 10))
    assert result["huang0000"].tier == 1 and result["huang0000"].title == "黃天功臣"
    assert result["guan0000"].tier == 3 and result["guan0000"].title == "有功之臣"


def test_threshold_comes_first_and_only_the_qualified_are_ranked(content):
    players = _army("guan", 5) + [_p("guan_low", "guan", 39), _p("guan_zero", "guan", 0)]
    result = _settle(content, GUAN_WINS, players)
    for name in ("guan_low", "guan_zero"):
        assert (result[name].tier, result[name].title, result[name].ledger_used, result[name].rank, result[name].of) == (0, "", None, 0, 0)
    assert result["guan_low"].points == 39
    assert {result[p.name].of for p in players[:5]} == {5}  # 過門檻的 5 人一池
    assert result[_army("guan", 5)[-1].name].rank == 5
    assert _p("x", "guan", 40).contrib == 40 and _settle(content, GUAN_WINS, [_p("x", "guan", 40)])["x"].tier == 1  # 剛好到門檻也算（40：企劃者 2026-10-26 定）


def test_at_least_one_on_top_and_small_pools(content):
    """第一階前 10% 至少 1 人；扣掉第一、二階那一池還有人時第三階也至少 1 人（PM 2026-10-25 第 1 件）：
    贏的 3 人是一、三、四；輸的 3 人是三、四、四；輸的那一軍只有 1 人是第三階。"""
    result = _settle(content, GUAN_WINS, _army("guan", 3) + _army("huang", 3))
    assert [result[f"guan{i:04d}"].tier for i in range(3)] == [1, 3, 4]
    assert [result[f"huang{i:04d}"].tier for i in range(3)] == [3, 4, 4]
    alone = _settle(content, GUAN_WINS, [_p("solo", "guan", 100), _p("enemy", "huang", 100)])
    assert (alone["solo"].tier, alone["enemy"].tier) == (1, 3)  # 40% 捨去是 0，第三階至少 1 人
    two = _settle(content, GUAN_WINS, _army("guan", 2))
    assert [two[f"guan{i:04d}"].tier for i in range(2)] == [1, 3]


def test_third_tier_minimum_skips_a_tie_on_top(content):
    """第一階同分多拿了人：第三階的那一個名次接在他們後面（扣掉最上面那一段還有人才給）。"""
    players = _army("guan", 3)
    players[1].contrib = players[0].contrib  # 前兩名同分：都是第一階
    result = _settle(content, GUAN_WINS, players)
    assert [result[p.name].tier for p in players] == [1, 1, 3]
    tied = _army("guan", 2)
    tied[1].contrib = tied[0].contrib  # 兩人同分都在第一階：池子裡沒有別人，第三階沒有人
    assert [_settle(content, GUAN_WINS, tied)[p.name].tier for p in tied] == [1, 1]


def test_ties_share_a_rank_and_a_tier(content):
    players = _army("guan", 20)
    players[2].contrib = players[1].contrib  # 第 2、3 名同分：都算第 2 名、都在前 10%（2 人）裡
    result = _settle(content, GUAN_WINS, players)
    assert [result[p.name].rank for p in players[:4]] == [1, 2, 2, 4]
    assert [result[p.name].tier for p in players[:4]] == [1, 1, 1, 3]


def test_gentry_ranked_by_the_winning_side_book_first(content):
    """官軍贏：豪強照「替官軍」那一本排（前 10% 第二階、前 40% 其餘第三階、其餘第四階）；那一本到了門檻就照它，
    另一本再多也不換；那一本不到門檻才看「替黃巾」那一本（前 40% 第三階、其餘第四階）；兩本都不到沒有。"""
    win_book = [_p(f"g{i}", "haoqiang", ledgers={"guan": 500 - i * 10}, ally="guan") for i in range(10)]
    stays = _p("g_stays", "haoqiang", ledgers={"guan": 40, "huang": 900}, ally="huang")  # 替官軍剛好到門檻：照官軍那一本，排最後
    fallback = [_p(f"f{i}", "haoqiang", ledgers={"guan": 39, "huang": 300 - i * 10}, ally="huang") for i in range(5)]
    nothing = _p("g_none", "haoqiang", ledgers={"guan": 39, "huang": 39}, ally="guan")
    result = _settle(content, GUAN_WINS, win_book + [stays] + fallback + [nothing])
    pool = win_book + [stays]  # 11 人：前 10% 捨去 1 人第二階、前 40% 捨去 4 人
    assert [result[p.name].tier for p in pool] == [2, 3, 3, 3] + [4] * 7
    assert {result[p.name].ledger_used for p in pool} == {"guan"}
    assert {result[p.name].of for p in pool} == {11}
    assert (result["g_stays"].tier, result["g_stays"].rank, result["g_stays"].points) == (4, 11, 40)
    assert result["g0"].title == "一方之雄" and result["g1"].title == "鄉里之望" and result["g9"].title == "附從"
    assert [result[p.name].tier for p in fallback] == [3, 3, 4, 4, 4]  # 5 人的 40% 捨去是 2
    assert {(result[p.name].ledger_used, result[p.name].of) for p in fallback} == {("huang", 5)}
    assert result["f0"].points == 300
    assert (result["g_none"].tier, result["g_none"].ledger_used, result["g_none"].points) == (0, None, 39)


def test_gentry_book_follows_whichever_side_won(content):
    gentry = [_p("for_guan", "haoqiang", ledgers={"guan": 400}, ally="guan"),
              _p("for_huang", "haoqiang", ledgers={"huang": 400}, ally="huang")]
    by_guan = _settle(content, GUAN_WINS, gentry)
    by_huang = _settle(content, HUANG_WINS, gentry)
    assert (by_guan["for_guan"].tier, by_guan["for_huang"].tier) == (2, 3)  # 替黃巾那一本的池只有 1 人：第三階至少 1 人
    assert (by_huang["for_guan"].tier, by_huang["for_huang"].tier) == (3, 2)
    assert (by_guan["for_huang"].ledger_used, by_huang["for_guan"].ledger_used) == ("huang", "guan")


def test_first_tier_only_for_the_winning_army_and_second_only_for_gentry(content):
    players = _army("guan", 30) + _army("huang", 30) + [
        _p(f"g{i}", "haoqiang", ledgers={"guan": 900 - i, "huang": 900 - i}, ally="guan") for i in range(30)
    ]
    result = _settle(content, GUAN_WINS, players)
    by_faction: dict[str, set[int]] = {}
    for p in players:
        by_faction.setdefault(p.faction, set()).add(result[p.name].tier)
    assert by_faction == {"guan": {1, 3, 4}, "huang": {3, 4}, "haoqiang": {2, 3, 4}}


def test_draw_cuts_both_armies_as_losers_and_gentry_by_both_books(content):
    """企劃者 2026-10-24 第 3 件：和局沒有第一、二階；兩軍各自照輸的切，豪強照兩本合計排。"""
    gentry = [_p(f"g{i}", "haoqiang", ledgers={"guan": 40, "huang": 100 - i * 5}, ally="guan") for i in range(5)]
    gentry.append(_p("g_split", "haoqiang", ledgers={"guan": 20, "huang": 20}, ally="huang"))  # 兩本各 20、合計 40：剛好到門檻
    gentry.append(_p("g_short", "haoqiang", ledgers={"guan": 20, "huang": 19}, ally="huang"))
    players = _army("guan", 10) + _army("huang", 10) + gentry
    result = _settle(content, DRAW, players)
    for faction in ("guan", "huang"):
        names = [p.name for p in players if p.faction == faction]
        assert [_count(result, names, t) for t in (1, 2, 3, 4)] == [0, 0, 4, 6]
    assert [result[p.name].tier for p in gentry] == [3, 3, 4, 4, 4, 4, 0]  # 6 人過門檻：40% 捨去 2 人
    assert {result[p.name].ledger_used for p in gentry[:6]} == {wins.BOTH}
    assert (result["g0"].points, result["g_split"].points, result["g_short"].points) == (140, 40, 39)
    assert result["g0"].title == "鄉里之望"
    assert wins.winner_of(WorldState(ending_id="s1_warlords"), content) is None


def test_drifters_and_unknown_factions_have_no_tier(content):
    result = _settle(content, GUAN_WINS, [_p("drifter", None, 0), _p("ghost", "nobody", 500), _p("guan1", "guan", 100)])
    assert set(result) == {"guan1"}


def test_rules_are_read_from_the_argument(content):
    rules = JianfaRules(tiers=TierRules(min_contribution=200, tier1_share=0.2, tier3_share=0.5))
    players = _army("guan", 10, base=195)  # 貢獻 205～196：只有前 6 人過 200
    result = _settle(content, GUAN_WINS, players, rules)
    assert [result[p.name].tier for p in players] == [1, 3, 3, 4, 4, 4, 0, 0, 0, 0]  # 6 人：20% 捨去 1、50% 是 3


def test_start_grant_and_titles(content):
    rules = wins.rules_of(content)
    assert [wins.start_grant(rules, t) for t in (0, 1, 2, 3, 4)] == [(0, 0), (300, 200), (240, 160), (150, 100), (90, 60)]
    assert wins.title_of(rules, 2, "haoqiang") == "一方之雄"
    assert wins.title_of(rules, 4, "guan") == "隨軍"
    assert wins.title_of(rules, 0, "guan") == ""
    assert wins.title_of(rules, 1, "nobody") == ""


def test_tier_rules_reject_shares_out_of_order():
    with pytest.raises(ValueError):
        TierRules(tier1_share=0.5, tier3_share=0.4)
    with pytest.raises(ValueError):
        TierRules(start_shares={5: 0.1})
