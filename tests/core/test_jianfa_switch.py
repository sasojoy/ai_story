"""減法季的開關（減法季批 0，設計稿第十章；Config.jianfa 加開季時蓋的章，讀的時候走 rules.jianfa）：
season21、week7 新開的季蓋章，週末設定不蓋；正在跑的季照它自己的章；主機把開關關掉時一律照關著。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tianxia import rules
from tianxia.content import load_content
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 載三份正式內容

CONTENT = Path(__file__).resolve().parents[2] / "content"


@pytest.mark.parametrize(("profile", "on"), [("season21", True), ("week7", True), (None, False)])
def test_which_settings_stamp_the_season(profile, on):
    content = load_content(CONTENT, profile=profile)
    season = fresh_season(content, now=1_800_000_000.0)
    assert content.config.jianfa.enabled is on
    assert season.jianfa_on is on and rules.jianfa(content, season) is on


def test_a_running_season_keeps_its_stamp_and_the_host_switch_wins(content):
    assert content.config.jianfa.enabled is False  # 測試內容關著
    season = fresh_season(content)
    assert season.jianfa_on is False and rules.jianfa(content, season) is False
    content.config.jianfa.enabled = True
    assert rules.jianfa(content, season) is False  # 打開時正在跑的季沒有章，照舊
    stamp_season(season, content)
    assert season.jianfa_on is True and rules.jianfa(content, season) is True
    content.config.jianfa.enabled = False
    assert season.jianfa_on is True and rules.jianfa(content, season) is False  # 主機的緊急開關
    assert rules.jianfa(content, None) is False


def test_each_batch_has_its_own_sub_switch(content):
    """子開關（整合設計第十二章）：總開關開著、有章時各批再看自己的；總開關關著時一律不算。寫錯名字直接丟 AttributeError。"""
    content.config.jianfa.enabled = True
    season = fresh_season(content)
    parts = ["explore_one", "drill_gates", "sortie_duel", "free_text_outcomes", "marks_visible", "stances", "errands",
             "week_unlock", "rewrite_narration", "stat_milestones", "zhuan_end"]
    assert all(rules.jianfa(content, season, part) for part in parts)
    content.config.jianfa.sortie_duel = False
    assert not rules.jianfa(content, season, "sortie_duel") and rules.jianfa(content, season, "explore_one")
    assert rules.jianfa(content, season)
    with pytest.raises(AttributeError):
        rules.jianfa(content, season, "no_such_part")
    content.config.jianfa.enabled = False
    assert not any(rules.jianfa(content, season, part) for part in parts)


# ── 批 2（探索一顆、三道閘、屬性五段）的數字、表與存檔的鍵（主機側計畫 Task 2-1）──


def test_batch2_numbers_ride_on_config_jianfa():
    """批 2 的數字繼承自 jianfa_numbers.JianfaNumbers（純規則吃同一份）；子開關 stat_milestones 是批 2 加的。"""
    from tianxia.jianfa_numbers import JianfaNumbers

    cfg = load_content(CONTENT, profile="season21").config.jianfa
    assert isinstance(cfg, JianfaNumbers)
    # 2d（企劃者 2026-10-26）：一趟只抽一件事（沒有「一趟幾拍」了）；體力 2026-10-27 改回 6（曾是 18、15）
    assert (cfg.explore_stamina, cfg.drill_full_per_day, cfg.drill_floor, cfg.drill_level_cap) == (6, 15, 0.3, 45)
    assert not hasattr(cfg, "beats")
    assert cfg.milestone_levels == [10, 20, 30, 40, 50] and cfg.stat_points_per_milestone == 5
    assert cfg.stat_rates.bonus_per_point == 0.06 and cfg.town_foes == ["dipi"] and cfg.town_loot_scale == 0.5
    assert cfg.camp_spar_share == 0.3  # 修正輪（PM 2026-10-26）：自家營寨比劃給對手那一路的三成
    # 子開關 2026-10-28 關掉（85ed8748，FB-899：1～9 級沒點可配）：數字留在 Config.jianfa，開關照現行設定；五段本身在 test_stat_milestones_engine 自己打開
    assert cfg.stat_milestones is False


def test_every_real_place_has_an_explore_table_and_travelers_are_wild():
    """正式內容每個地點都靠自己的標籤歸得到一張表；標了「旅人」的事件至少三則、都只在野類的地點（PM 2026-10-25 第 2、7 件）。"""
    from tianxia import explore_one
    from tianxia.content import TRAVELER_MIN, TRAVELER_TAG
    from tianxia.events import event_matches_location

    c = load_content(CONTENT, profile="season21")
    cfg = c.config.jianfa
    assert all(explore_one.match(cfg, loc.tags) is not None for loc in c.locations.values())
    kinds = {loc.id: explore_one.kind_of(cfg, loc).kind for loc in c.locations.values()}
    assert kinds["guangzong"] == kinds["julu_altar"] == explore_one.CAMP  # 兩張表都對得上的：營優先（第 2 件）
    assert kinds["haozu_fort"] == explore_one.TOWN  # 塢堡算城
    travelers = [e for e in c.events.values() if TRAVELER_TAG in e.tags]
    assert len(travelers) >= TRAVELER_MIN
    for event in travelers:
        places = {loc.id for loc in c.locations.values() if event_matches_location(event, loc)}
        assert places and all(kinds[p] == explore_one.WILD for p in places), event.id


def test_validate_catches_a_place_without_a_table_only_when_jianfa_is_on():
    from tianxia.content import ContentError, validate

    c = load_content(CONTENT, profile="season21")
    c.locations["yingshui"].tags = ["酒肆"]  # 店面標籤不歸表
    with pytest.raises(ContentError, match="yingshui"):
        validate(c)
    c.config.jianfa.enabled = False
    validate(c)  # 關著的設定不驗（週末、測試內容）


def test_validate_wants_three_traveler_events(monkeypatch):
    from tianxia import content as content_mod
    from tianxia.content import ContentError, validate

    c = load_content(CONTENT, profile="season21")
    monkeypatch.setattr(content_mod, "TRAVELER_MIN", 99)
    with pytest.raises(ContentError, match="旅人"):
        validate(c)


def test_a_place_can_override_its_four_columns():
    """locations.json 可以寫 explore_mix 覆寫四欄（設計 4.1）；算哪一種地點照舊看標籤；沒寫的不寫進序列化。"""
    from tianxia import explore_one
    from tianxia.jianfa_numbers import ExploreMix

    c = load_content(CONTENT, profile="season21")
    loc = c.locations["yingshui"]
    assert "explore_mix" not in loc.model_dump()
    loc.explore_mix = ExploreMix(event=70, encounter=10, material=10, insight=10)
    got = explore_one.weights(c.config.jianfa, loc, has_foes=True)
    assert got == {"event": 70, "encounter": 10, "material": 10, "insight": 10}
    assert explore_one.kind_of(c.config.jianfa, loc).kind == explore_one.FORD
    with pytest.raises(ValueError):
        ExploreMix(event=70, encounter=10, material=10, insight=11)


def test_batch2_player_fields_add_no_keys_until_used(content):
    """PlayerState 的批 2 欄位（疲勞、境界卡、上一趟要選的那一拍）預設時不寫進存檔；有值寫得出來、讀得回去；舊存檔讀得進來。"""
    import json

    from tianxia.state import GameState, new_game_state

    fields = ("fights_today", "fight_day", "milestone_due", "outing_last")
    state = new_game_state(content, "甲客")
    assert not set(fields) & set(json.loads(state.model_dump_json())["player"])
    p = state.player
    p.fights_today, p.fight_day, p.milestone_due, p.outing_last = 3, 20380, 20, "yingshui:insight"
    data = json.loads(state.model_dump_json())["player"]
    assert [data[k] for k in fields] == [3, 20380, 20, "yingshui:insight"]
    back = GameState.model_validate_json(state.model_dump_json())
    assert (back.player.fights_today, back.player.outing_last) == (3, "yingshui:insight")
    loaded = GameState.model_validate(json.loads(new_game_state(content, "乙客").model_dump_json()))
    assert (loaded.player.fights_today, loaded.player.fight_day, loaded.player.milestone_due, loaded.player.outing_last) == (0, 0, 0, "")
