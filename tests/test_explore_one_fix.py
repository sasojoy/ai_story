"""減法季批 2 修正輪（PM 2026-10-26；試玩回饋 FB-815～819 與自家營寨比劃的經驗）：
1. 自家營寨跟同袍比劃只給對手那一路的 camp_spar_share（三成），不是全額；
2. 只有頭目的地點（官軍在長社）遇敵拍不再一定撞上頭目：一趟照 5% × 名聲倍數擲一次，沒擲中就當這裡沒有對手（遭遇那一格分給其餘三類）；
   頭目吃掉要選的那一拍時，紀錄標記不寫那一拍；
3. 新手目標 field2 在探索一顆開著時，在二級以上的地方遇敵拍打贏也記上，字改成出門探索的說法；
4. 討伐懸賞與散人出陣的說明在探索一顆開著時不再寫「尋敵」；
5. 45 級的打探懸賞出門一趟交差、經驗換成心得時，段落結尾也寫「境界已到」；
6. 城裡打地痞打成平手寫平手的句子（town_draw），不是吃了虧。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from conftest import real_content
from jianfa_kit import jianfa_game, jianfa_rules, ready

from tianxia import bounties, explore_one, renown, sortie, team
from tianxia.encounter import EncounterResult
from tianxia.engine import drill_share
from tianxia.state import Bounty

pytestmark = pytest.mark.slow


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beats(*beats: str):
    return mock.patch.object(explore_one, "draw", return_value=list(beats))


def _reset(game) -> None:
    """下一趟：體力補滿、沒有待選的事件與感悟。"""
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


# ── 1. 自家營寨比劃只給三成 ──


def test_camp_sparring_pays_the_share_of_the_comrade_squad_not_all_of_it():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)  # 對手 40 級以下的檔：不吃對手那一道、今天第一場不吃疲勞
    p, cfg = game.state.player, game.content.config.jianfa
    host = game.outing_plan().foe
    assert cfg.camp_spar_share == 0.3 and (host.exp, host.reward_xinde) == (40, 35)
    exp0, xinde0 = p.member.exp, p.stats.get("xinde", 0)
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == drill_share(host.exp, 0.3) == 12  # 以前全額 40
    assert p.stats.get("xinde", 0) - xinde0 == drill_share(host.reward_xinde, 0.3) == 11  # 心得照同一個比例（以前 35）


def test_the_camp_share_is_one_number_in_the_config():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    game.content.config.jianfa.camp_spar_share = 0.5
    p = game.state.player
    exp0 = p.member.exp
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == 20


def test_camp_sparring_share_stacks_with_the_fatigue_gate():
    """疲勞那一道照舊乘在上面：第 16 場是 0.8 倍的三成。"""
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    p = game.state.player
    p.fight_day, p.fights_today = game._pill_day(), 15
    exp0 = p.member.exp
    with _beats("encounter", "material", "material"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == drill_share(40, 0.3 * 0.8)


# ── 2. 只有頭目的地點：頭目照 5% × 名聲倍數 ──


def _trips(game, n: int):
    """在所在地連出 n 趟（頭目戰換成只記一筆，不真的開打），回（撞上頭目的趟數, 沒撞上的那幾趟的江湖紀錄標記）。"""
    met: list[str] = []
    tags: list[str] = []
    game._duel_start = lambda boss: met.append(boss.id) or []
    for _ in range(n):
        _reset(game)
        before = len(met)
        game.choose("act:explore")
        if len(met) == before:
            tags.append(game.state.journal[0].tag)
    return len(met), tags


def test_an_official_newbie_at_changshe_meets_the_boss_about_five_percent_of_trips():
    game = ready(jianfa_game(), side="guan", loc="changshe")  # 長社對官軍沒有別的隊伍，只有段鐵頭
    plan = game.outing_plan()
    assert plan.foe is None and plan.boss is not None
    assert plan.weights[explore_one.ENCOUNTER] == 0  # 沒擲中頭目就當這裡沒有對手：遭遇那一格分給其餘三類
    battles = len(game.state.battles)
    hits, tags = _trips(game, 400)
    assert 8 <= hits <= 36, hits  # 5% 是 20，以前一趟三拍至少一拍遇敵的機會約九成
    assert len(game.state.battles) == battles  # 沒撞上頭目的趟：沒有仗
    assert tags and not any("遇敵" in tag for tag in tags)  # 沒撞上時不出現遇敵拍


def test_the_boss_chance_follows_the_renown_multiplier():
    plain = ready(jianfa_game(), side="guan", loc="changshe")
    famous = ready(jianfa_game(), side="guan", loc="changshe")
    with mock.patch.object(renown, "duel_chance", return_value=3.0):
        more, _ = _trips(famous, 400)
    less, _ = _trips(plain, 400)
    assert more > less * 2 and 25 <= more <= 100, (more, less)  # 15% 約 60


def test_a_hit_on_the_boss_roll_always_puts_the_boss_in_the_trip():
    """擲中的那一趟遭遇拍一定有（第一拍就是頭目擋路），不是看三拍抽不抽得到遭遇——一趟的機會才是 5% × 倍數。"""
    game = ready(jianfa_game(), side="guan", loc="changshe")
    with mock.patch.object(renown, "duel_chance", return_value=20.0):  # 5% × 20 = 一定擲中
        hits, tags = _trips(game, 150)
    assert hits == 150 and not tags


def test_a_place_with_foes_still_rolls_the_boss_on_the_encounter_beat():
    """有一般對手的地點照舊：遭遇拍擲 5% × 倍數，沒中就打那一路（只有頭目的地點才改成一趟擲一次）。"""
    game = ready(jianfa_game(), side="huang", loc="changshe")  # 黃巾在長社有官軍巡哨
    plan = game.outing_plan()
    assert plan.foe is not None and plan.boss is not None and plan.weights[explore_one.ENCOUNTER] > 0


def test_the_tag_does_not_name_the_beat_the_boss_ate():
    """頭目擋路時要選的那一拍不出，江湖紀錄的結果標記也不寫它（以前寫「有悟」）。"""
    game = ready(jianfa_game(), side="guan", loc="changshe")
    game._duel_start = lambda boss: []
    with _beats("material", "encounter", "insight"):
        game.choose("act:explore")
    assert game.state.journal[0].tag == "得料・遇敵"


# ── 3. 新手目標 field2 ──


def test_a_won_encounter_at_a_tier_one_place_ticks_the_field_goal():
    game = ready(jianfa_game(), side="guan", loc="songshan_foot")  # 嵩山腳：匪寇橫行（二級）
    assert game._practice_tier(game.content.locations["songshan_foot"]) == 1
    with _beats("encounter", "material", "material"), _fight("大勝"):
        game.choose("act:explore")
    assert "field2" in game.state.player.newbie_marks


def test_a_lost_draw_or_low_tier_encounter_does_not_tick_the_field_goal():
    game = ready(jianfa_game(), side="guan", loc="songshan_foot")
    with _beats("encounter", "material", "material"), _fight("落敗"):
        game.choose("act:explore")
    assert "field2" not in game.state.player.newbie_marks
    _reset(game)
    with _beats("encounter", "material", "material"), _fight("僵持"):
        game.choose("act:explore")
    assert "field2" not in game.state.player.newbie_marks
    low = ready(jianfa_game(), side="guan", loc="yingshui")  # 宵小出沒（一級）
    assert low._practice_tier(low.content.locations["yingshui"]) == 0
    with _beats("encounter", "material", "material"), _fight("大勝"):
        low.choose("act:explore")
    assert "field2" not in low.state.player.newbie_marks
    town = ready(jianfa_game(), side="guan", loc="yingchuan")  # 城裡的地痞不算
    with _beats("encounter", "material", "material"), _fight("大勝"):
        town.choose("act:explore")
    assert "field2" not in town.state.player.newbie_marks


def test_the_field_goal_card_talks_about_the_outing_and_the_old_season_keeps_its_words():
    on = ready(jianfa_game(), side="guan", loc="songshan_foot")
    row = next(r for r in on.newbie_view()["rows"] if r["key"] == "field2")
    assert row["text"] == "到匪寇橫行的地方出門探索，打贏一場" and "尋敵" not in row["text"]
    with _beats("encounter", "material", "material"), _fight("大勝"):
        on.choose("act:explore")
    assert any("到匪寇橫行的地方出門探索，打贏一場" in g for entry in on.state.journal for g in entry.guide)  # 發獎勵那一句
    off = ready(jianfa_game(explore_one=False), side="guan", loc="songshan_foot")
    assert next(r for r in off.newbie_view()["rows"] if r["key"] == "field2")["text"] == "到匪寇橫行的地方尋敵，打贏一場"


