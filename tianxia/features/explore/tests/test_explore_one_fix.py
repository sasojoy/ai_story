"""減法季批 2 修正輪（PM 2026-10-26；試玩回饋 FB-815～819 與自家營寨比劃的經驗）：
1. 自家營寨跟同袍比劃只給對手那一路的 camp_spar_share（三成），不是全額；
2. 只有頭目的地點（官軍在長社）遇敵拍不再一定撞上頭目：一趟照 5% × 名聲倍數擲一次，沒擲中就當這裡沒有對手（遭遇那一格分給其餘三類）；
   頭目擋路的那一趟，紀錄標記寫遇敵（2d 以前頭目吃掉要選的那一拍時標記不寫那一拍，現在一趟只有一件事）；
3. 新手目標 field2 在探索一顆開著時，在二級以上的地方遇敵拍打贏也記上，字改成出門探索的說法；
4. 討伐懸賞與散人出陣的說明在探索一顆開著時不再寫「尋敵」；
5. 45 級的打探懸賞出門一趟交差、經驗換成心得時，段落結尾也寫「境界已到」；
6. 城裡打地痞打成平手寫平手的句子（town_draw），不是吃了虧。
用正式內容（season21）（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

from unittest import mock

import pytest
from conftest import real_content
from jianfa_kit import jianfa_game, jianfa_rules, ready

from tianxia import bounties, explore_one, renown, sortie, team
from tianxia.encounter import EncounterResult
from tianxia.engine import drill_share
from tianxia.state import Bounty


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beat(beat: str):
    """這一趟抽到的那一件事照給的（2d：一趟只抽一件事）。"""
    return mock.patch.object(explore_one, "draw", return_value=beat)


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
    with _beat("encounter"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == drill_share(host.exp, 0.3) == 12  # 以前全額 40
    assert p.stats.get("xinde", 0) - xinde0 == drill_share(host.reward_xinde, 0.3) == 11  # 心得照同一個比例（以前 35）


def test_the_camp_share_is_one_number_in_the_config():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    game.content.config.jianfa.camp_spar_share = 0.5
    p = game.state.player
    exp0 = p.member.exp
    with _beat("encounter"):
        game.choose("act:explore")
    assert p.member.exp - exp0 == 20


def test_camp_sparring_share_stacks_with_the_fatigue_gate():
    """疲勞那一道照舊乘在上面：第 16 場是 0.8 倍的三成。"""
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    p = game.state.player
    p.fight_day, p.fights_today = game._pill_day(), 15
    exp0 = p.member.exp
    with _beat("encounter"):
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


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
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


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_the_boss_chance_follows_the_renown_multiplier():
    plain = ready(jianfa_game(), side="guan", loc="changshe")
    famous = ready(jianfa_game(), side="guan", loc="changshe")
    with mock.patch.object(renown, "duel_chance", return_value=3.0):
        more, _ = _trips(famous, 400)
    less, _ = _trips(plain, 400)
    assert more > less * 2 and 25 <= more <= 100, (more, less)  # 15% 約 60


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_a_hit_on_the_boss_roll_always_puts_the_boss_in_the_trip():
    """擲中的那一趟一定是遭遇（頭目擋路），不是看抽不抽得到遭遇——一趟的機會就是 5% × 倍數。"""
    game = ready(jianfa_game(), side="guan", loc="changshe")
    with mock.patch.object(renown, "duel_chance", return_value=20.0):  # 5% × 20 = 一定擲中
        hits, tags = _trips(game, 150)
    assert hits == 150 and not tags


def test_a_place_with_foes_still_rolls_the_boss_on_the_encounter_beat():
    """有一般對手的地點照舊：遭遇拍擲 5% × 倍數，沒中就打那一路（只有頭目的地點才改成一趟擲一次）。"""
    game = ready(jianfa_game(), side="huang", loc="changshe")  # 黃巾在長社有官軍巡哨
    plan = game.outing_plan()
    assert plan.foe is not None and plan.boss is not None and plan.weights[explore_one.ENCOUNTER] > 0


def test_a_boss_trip_is_tagged_as_the_encounter_it_is():
    """頭目擋路的那一趟，江湖紀錄的結果標記寫遇敵（2d 以前三拍裡頭目吃掉要選的那一拍，標記還要拿掉那一拍，FB-815）。"""
    game = ready(jianfa_game(), side="guan", loc="changshe")
    game._duel_start = lambda boss: []
    with _beat("encounter"):
        game.choose("act:explore")
    assert game.state.journal[0].tag == "遇敵"


# ── 3. 新手目標 field2 ──


def test_a_won_encounter_at_a_tier_one_place_ticks_the_field_goal():
    game = ready(jianfa_game(), side="guan", loc="songshan_foot")  # 嵩山腳：匪寇橫行（二級）
    assert game._practice_tier(game.content.locations["songshan_foot"]) == 1
    with _beat("encounter"), _fight("大勝"):
        game.choose("act:explore")
    assert "field2" in game.state.player.newbie_marks


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_a_lost_draw_or_low_tier_encounter_does_not_tick_the_field_goal():
    game = ready(jianfa_game(), side="guan", loc="songshan_foot")
    with _beat("encounter"), _fight("落敗"):
        game.choose("act:explore")
    assert "field2" not in game.state.player.newbie_marks
    _reset(game)
    with _beat("encounter"), _fight("僵持"):
        game.choose("act:explore")
    assert "field2" not in game.state.player.newbie_marks
    low = ready(jianfa_game(), side="guan", loc="yingshui")  # 宵小出沒（一級）
    assert low._practice_tier(low.content.locations["yingshui"]) == 0
    with _beat("encounter"), _fight("大勝"):
        low.choose("act:explore")
    assert "field2" not in low.state.player.newbie_marks
    town = ready(jianfa_game(), side="guan", loc="yingchuan")  # 城裡的地痞不算
    with _beat("encounter"), _fight("大勝"):
        town.choose("act:explore")
    assert "field2" not in town.state.player.newbie_marks


def test_the_field_goal_card_talks_about_the_outing_and_the_old_season_keeps_its_words():
    on = ready(jianfa_game(), side="guan", loc="songshan_foot")
    row = next(r for r in on.newbie_view()["rows"] if r["key"] == "field2")
    assert row["text"] == "到匪寇橫行的地方出門探索，打贏一場" and "尋敵" not in row["text"]
    with _beat("encounter"), _fight("大勝"):
        on.choose("act:explore")
    assert any("到匪寇橫行的地方出門探索，打贏一場" in g for entry in on.state.journal for g in entry.guide)  # 發獎勵那一句
    off = ready(jianfa_game(explore_one=False), side="guan", loc="songshan_foot")
    assert next(r for r in off.newbie_view()["rows"] if r["key"] == "field2")["text"] == "到匪寇橫行的地方尋敵，打贏一場"


# ── 4. 不再寫「尋敵」的兩處 ──


def _strike() -> Bounty:
    return Bounty(id="b1", kind="strike", faction="guan", week=1, expires=1e12, silver=20, deeds=1, location="yanshan_foot", squad="louluo")


def test_the_strike_bounty_names_the_outing_when_explore_one_is_on():
    on = ready(jianfa_game(), side="guan", loc="yingshui")
    line = bounties.how(on.content, _strike(), on.state)
    assert line == "到燕山腳出門探索或出陣攻打贏一場黃巾軍的隊伍" and "尋敵" not in line
    on.state.player.faction = None  # 散人不出陣
    assert bounties.how(on.content, _strike(), on.state) == "到燕山腳出門探索打贏一場黃巾軍的隊伍"
    assert bounties.how(on.content, _strike(), world=on.state.world) == "到燕山腳出門探索或出陣攻打贏一場黃巾軍的隊伍"  # 陣營傳聞沒有看的人
    off = ready(jianfa_game(explore_one=False), side="guan", loc="yingshui")
    assert bounties.how(off.content, _strike(), off.state) == "到燕山腳尋敵或出陣攻打贏一場黃巾軍的隊伍"
    off.state.player.faction = None
    assert bounties.how(off.content, _strike(), off.state) == "到燕山腳尋敵打贏一場黃巾軍的隊伍"


def test_the_ranger_line_names_the_outing_when_explore_one_is_on():
    on = ready(jianfa_game(), loc="runan_wilds")  # 散人站在戰線地點
    notes = on.action_notes([o.id for o in on.options(odds=False)])
    assert notes["act:train"] == sortie.RANGER_LINE_OUTING and "尋敵" not in sortie.RANGER_LINE_OUTING
    assert "出門探索" in sortie.RANGER_LINE_OUTING
    off = ready(jianfa_game(explore_one=False), loc="runan_wilds")
    assert off.action_notes([o.id for o in off.options(odds=False)])["act:train"] == sortie.RANGER_LINE_PRECISE


# ── 5. 45 級打探懸賞交差：段落結尾也寫境界已到 ──


def test_the_capped_close_is_written_when_the_scout_bounty_pays_the_xinde():
    game = ready(jianfa_game(), side="guan", loc="yingshui", level=45)
    capped = team.CAPPED_XINDE.format(n=9)
    with _beat("material"), mock.patch.object(bounties, "on_explore", return_value=[capped]):
        msgs = game.choose("act:explore")
    assert "境界已到，再往上只能打出來。" in msgs[0] and capped in msgs  # 段落結尾有那一句，訊息那一行也在
    low = ready(jianfa_game(), side="guan", loc="yingshui", level=10)
    with _beat("material"):
        assert "境界已到" not in low.choose("act:explore")[0]


def test_the_capped_close_for_a_real_scout_bounty():
    game = ready(jianfa_game(), side="guan", loc="yingshui", level=45)
    p = game.state.player
    game.state.world.bounties.append(Bounty(id="s1", kind="scout", faction="guan", week=1, expires=1e12, silver=10, deeds=1,
                                            location="yingshui", takers=[p.name]))
    exp0, xinde0 = p.member.exp, p.stats.get("xinde", 0)
    with _beat("material"):
        msgs = game.choose("act:explore")
    assert p.member.exp == exp0 and p.stats.get("xinde", 0) > xinde0 and any(m.startswith("境界已到") for m in msgs)  # 經驗換成心得
    assert msgs[0].count("境界已到，再往上只能打出來。") == 1  # 段落結尾也寫了


# ── 6. 城裡平手 ──


def test_a_town_brawl_ending_in_a_draw_reads_as_a_draw_not_a_loss():
    game = ready(jianfa_game(), side="guan", loc="yingchuan")
    assert "town_draw" in explore_one.LINE_KEYS["encounter"] and game.content.outing_lines["encounter"]["town_draw"]
    foe = game.content.squads["dipi"].name
    draws = {line.format(foe=foe, place="", item="") for line in game.content.outing_lines["encounter"]["town_draw"]}
    loses = {line.format(foe=foe, place="", item="") for line in game.content.outing_lines["encounter"]["town_lose"]}
    with _beat("encounter"), _fight("僵持"):
        story = game.choose("act:explore")[0]
    assert any(line in story for line in draws) and not any(line in story for line in loses)
    _reset(game)
    with _beat("encounter"), _fight("落敗"):
        story = game.choose("act:explore")[0]
    assert any(line in story for line in loses) and not any(line in story for line in draws)


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_the_town_draw_lines_are_checked_when_loaded():
    from tianxia.content import ContentError, validate

    c = jianfa_rules(real_content("season21"))
    del c.outing_lines["encounter"]["town_draw"]
    with pytest.raises(ContentError, match="town_draw"):
        validate(c)
    c.outing_lines["encounter"]["town_draw"] = ["街角的{foe}纏了你3回合。"]  # 不准寫數字
    with pytest.raises(ContentError, match="outing_lines.encounter.town_draw"):
        validate(c)
