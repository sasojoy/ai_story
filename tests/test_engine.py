import random
import re
import time
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom, at, install_season_one, walk_to
from tianxia import (
    atlas, battle_instance, calendar, companion_agent, fight_llm, flavor, front_lines, guide, library, rules, skillview,
)
from tianxia.characters import open_characters
from tianxia.content import load_content
from tianxia.engine import Game, Option
from tianxia.martial_arts import Insight, MartialArt, generate_from_name
from tianxia.models import Effect, FigureDef, Location, PromotionDef
from tianxia.models import ExploreMix
from tianxia.state import BotProfile, FigureState, GameState, Journey, Rumor, new_game_state
from tianxia.sqlite_world import open_world
from tianxia.world_state import season_length_days

HOUR = 3600
DAY = 86400
ROOT = Path(__file__).resolve().parent.parent


def ids(game):
    return [o.id for o in game.options()]


# ── 新遊戲與選項 ─────────────────────────────────────────


def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.team == [] and p.member.level == 1
    assert "測試開始。" in game.state.log


def test_a_new_character_starts_with_the_starter_arts(content, world):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0), world=world)
    member = game.state.player.member
    assert (member.neigong_id, member.neigong_level) == ("basic_breath", 1)
    assert (member.wugong_id, member.wugong_level) == ("basic_fist", 1)


def test_a_new_season_character_starts_with_the_starter_arts_again(content, world):
    """每季重來的角色也從那兩門第一成開始（_reset_player_for_new_season 走同一個 new_game_state）。"""
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0), world=world)
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 7
    game._reset_player_for_new_season(game.state.player.season_number + 1)
    member = game.state.player.member
    assert (member.neigong_id, member.neigong_level) == ("basic_breath", 1)
    assert (member.wugong_id, member.wugong_level) == ("basic_fist", 1)


def test_there_is_no_self_created_art_any_more(game):
    """行為上也沒有（審查 F18）：就算兩個欄位都空著、手上心得銀兩都有，選單也不給自創，硬送自創的選項 id 只會被擋回；
    伺服器那一側的拒絕在 tests/test_server.py。"""
    member = game.state.player.member
    member.neigong_id = member.wugong_id = None
    game.state.player.stats.update(xinde=500, silver=500)
    listed = game.options()
    assert not any("create" in o.id or "自創" in o.label for o in listed)
    arts_before = library.owned_arts(game.state)
    for option_id in ("act:create", "act:create_skill", "create", "act:craft"):
        assert game.choose(option_id) == ["（此刻無法這麼做。）"]
    assert library.owned_arts(game.state) == arts_before == []
    assert (member.neigong_id, member.wugong_id) == (None, None)


def test_the_menxia_pages_get_their_rows_from_the_game_facade(game):
    """修練與煉製兩頁的資料都從 Game 這個門面拿（伺服器不直接碰 skillview）。"""
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.arts = ["lake_kick"]
    game.state.player.insights = ["feng"]
    assert game.holdings() == {"count": 3, "cap": library.cap_of(game.state, game.content)}
    assert [r["id"] for r in game.art_rows()] == ["basic_fist", "lake_kick"]
    assert [r["id"] for r in game.insight_rows()] == ["feng"]
    assert game.naming_row() is None
    game.state.player.naming = "lake_kick"
    assert game.naming_row() == {"id": "lake_kick", "name": "湖邊腿法"}
    game.state.player.naming = "ghost"
    assert game.naming_row() is None  # 找不到那門武學：沒有東西可以取名


def test_real_content_starts_with_enough_xinde_for_the_first_level():
    """Review Focus 第 5 條：新角色照新手引導按「練成」，第一成一定練得起。"""
    real = load_content(ROOT / "content")
    first = [real.skills[s] for s in real.config.starter_skills]
    assert len(first) == 2
    assert real.config.start_stats["xinde"] >= 2 * real.config.practice_xinde_per_level  # 兩門各練一成


# ── 讀檔清理（武學與成長計畫 T10）──────────────────────────


def _reload(game, content, world):
    return Game(content, game.state, rng=random.Random(0), world=world).state.player


def _a_fused_art(world, name="旋風腿"):
    """全服登記一門合成的武學（修練、定名都要它存在於全服）。"""
    art = generate_from_name(name, "武學", name).model_copy(update={"origin": "fused", "insight": "feng", "creator": "舊檔"})
    assert world.claim_skill_name(art)
    return art


def test_loading_drops_insights_and_records_that_no_longer_point_anywhere(content, world):
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.neigong_id = "basic_breath"
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng", "feng", "不存在的意境"]
    p.art_quality = {"basic_fist": "中品", "早就熔掉的": "上品", "basic_breath": "怪品"}  # 怪品：不是四個品質之一
    p.art_mastery = {"basic_fist": 2, "早就熔掉的": 3, "basic_breath": 0}
    p.naming = "basic_fist"  # 不是全服第一個練成的人
    q = _reload(game, content, world)
    assert q.insights == ["feng"]
    assert q.art_quality == {"basic_fist": "中品"}
    assert q.art_mastery == {"basic_fist": 2}
    assert q.naming is None


def test_loading_keeps_world_made_insights_that_still_exist(content, world):
    """全服合併出來的意境（world.get_insight）找得到就留著，換季或內容改版後找不到才丟。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    assert world.claim_insight_recipe("合|feng+huo", Insight(id="燎原", name="燎原", attribute="陽", creator="乙"))[1]
    game.state.player.insights = ["燎原", "huo", "已經散掉的意境"]
    assert _reload(game, content, world).insights == ["燎原", "huo"]


def test_loading_keeps_a_naming_right_the_player_really_holds(content, world):
    """等著取名的那一門是自己第一個練成的、又還擁有它：讀檔後取名權還在（清理不能一律清掉）。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    art = _a_fused_art(world)
    assert world.claim_master(art.id, "舊檔")
    p = game.state.player
    p.arts, p.naming = [art.id], art.id
    assert _reload(game, content, world).naming == art.id


def test_loading_drops_a_naming_right_someone_else_holds_or_the_art_is_gone(content, world):
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    art = _a_fused_art(world)
    p = game.state.player
    assert world.claim_master(art.id, "別人")  # 第一個練成的是別人：換季、讀到舊檔都可能對不上
    p.arts, p.naming = [art.id], art.id
    assert _reload(game, content, world).naming is None
    other = _a_fused_art(world, "回風掌")
    assert world.claim_master(other.id, "舊檔")
    p.arts, p.naming = [], other.id  # 取名權是自己的，可是那門武學已經不在手上
    assert _reload(game, content, world).naming is None


def test_a_worn_id_that_is_only_an_insight_name_or_an_alias_is_not_an_art(content, world):
    """is_skill_name_taken 連改過的名字與意境名都算，不能拿來判斷「這門武學存在」：身上的 id 對不到真的武學就丟掉。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    art = _a_fused_art(world)
    assert world.rename_skill(art.id, "風神腿")
    assert world.claim_insight_recipe("合|feng+huo", Insight(id="燎原", name="燎原", attribute="陽", creator="乙"))[1]
    member = game.state.player.member
    member.neigong_id, member.wugong_id = "燎原", "風神腿"  # 一個是意境名、一個是別名，都沒有這個 id 的武學
    after = _reload(game, content, world).member
    assert after.neigong_id is None and after.wugong_id is None
    member.wugong_id = art.id  # 真的存在的合成武學：留著
    assert _reload(game, content, world).member.wugong_id == art.id


def test_loading_fills_an_empty_slot_with_the_matching_starter_art(content, world):
    """新規則下欄位不會空（開局送兩門、身上的熔不掉）；改版前存的角色欄位空著、又不能再自創，讀檔時補回開局那門。"""
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    member = game.state.player.member
    member.neigong_id = member.wugong_id = None
    member.neigong_level = member.wugong_level = 7  # 舊的熟練度不帶：新的一門從第一成起
    after = _reload(game, content, world).member
    assert (after.neigong_id, after.neigong_level) == ("basic_breath", 1)
    assert (after.wugong_id, after.wugong_level) == ("basic_fist", 1)


def test_loading_moves_a_starter_from_the_library_into_the_empty_slot_keeping_its_level(content, world):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.wugong_id = None
    p.arts, p.art_levels = ["basic_fist"], {"basic_fist": 6}
    after = _reload(game, content, world)
    assert (after.member.wugong_id, after.member.wugong_level) == ("basic_fist", 6)
    assert "basic_fist" not in after.arts
    assert library.owned_arts(game.state).count("basic_fist") == 1


def test_loading_leaves_a_filled_slot_alone(content, world):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.wugong_id, p.member.wugong_level = "fist", 4
    p.arts, p.art_levels = ["basic_fist"], {"basic_fist": 6}  # 開局那門收在庫裡也不動它
    after = _reload(game, content, world)
    assert (after.member.wugong_id, after.member.wugong_level) == ("fist", 4)
    assert after.arts == ["basic_fist"] and after.art_levels == {"basic_fist": 6}
    assert (after.member.neigong_id, after.member.neigong_level) == ("basic_breath", 1)


def test_loading_leaves_an_empty_slot_empty_when_the_content_has_no_starter_arts(content, world):
    assert content.config.starter_skills == []
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.member.neigong_id = game.state.player.member.wugong_id = None
    after = _reload(game, content, world).member
    assert after.neigong_id is None and after.wugong_id is None


def test_town_options(game):
    # 小鎮有事件可交友（拜師）、有可招募的人（韓鐵），沒有敵人所以不能遊歷
    assert ids(game) == ["act:explore", "act:socialize", "act:recruit", "move:lake", "act:rest"]


def test_locked_location_hidden_until_flag(game):
    walk_to(game, "lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_socialize_hidden_when_no_events_here(game):
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)


def test_recruit_option_follows_who_is_free_at_this_location(game):
    assert "招募【韓鐵】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    walk_to(game, "lake")
    assert "招募【琴師】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    game.world.try_recruit("friend", "李四")
    game.world.try_recruit("hero", "李四")
    assert "act:recruit" not in ids(game)  # 湖邊兩人都被搶走了


def test_recruit_option_shows_the_real_odds_and_tracks_affinity(game):
    """實機 playtest 發現招募失敗時玩家完全看不出原因、也不知道好感度才是真正的槓桿
    （roster.py::recruit_chance）。選單上的成功率要跟著好感度即時變化，不是寫死的。"""
    def label():
        return next(o.label for o in game.options() if o.id == "act:recruit")

    assert "成功率約 35%" in label()  # 好感度 0：基礎成功率
    game.state.player.affinities["mate"] = 100
    assert "成功率約 85%" in label()  # 基礎 35% + 好感度 100 的加成 50%


def test_walking_to_a_neighbour_costs_no_stamina(game):
    game.state.player.stamina = 0
    move = next(o for o in game.options() if o.id == "move:lake")
    assert move.enabled and move.label == "前往 湖邊（步行約 3 分鐘）"
    game.choose("move:lake")
    assert game.state.player.stamina == 0


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    opts = game.options()
    assert all(not o.enabled for o in opts if o.id != "act:rest" and not o.id.startswith("move:"))
    assert all(o.enabled for o in opts if o.id.startswith("move:"))  # 步行不花體力
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_rest_is_always_available_and_never_locks_the_player_out(game):
    """實機 playtest 發現的卡死情境：體力見底時過去完全沒有選項可點，新玩家只能乾等。
    act:rest（打坐）必須永遠是 enabled，坐下來之後時間過去就真的會回體力。"""
    game.state.player.stamina = 0
    rest = next(o for o in game.options() if o.id == "act:rest")
    assert rest.enabled
    game.choose("act:rest")
    game.advance(HOUR)
    assert game.state.player.stamina > 0


# ── 打坐 ──────────────────────────────────────────────


def test_sitting_down_is_a_state_you_stand_up_from(game):
    game.choose("act:rest")
    assert game.state.player.resting_since == game.state.world.time
    assert ids(game) == ["act:stand"]
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert "打坐中" in game.status_text()
    game.choose("act:stand")
    assert game.state.player.resting_since is None
    assert "act:explore" in ids(game)
    assert game.state.journal[0].title == "起身"


def test_standing_up_right_away_does_not_count_zero_minutes(game):
    """FB-049：剛坐下就起身，不寫「打坐了約 0 分鐘」；坐滿一分鐘以上照舊寫幾分鐘。"""
    game.choose("act:rest")
    assert game.choose("act:stand") == ["你收功起身。"]
    game.state.player.stamina = 0  # 不然體力早就滿了，一推進時間就自己起身
    game.choose("act:rest")
    game.advance(600)
    assert game.choose("act:stand") == ["你收功起身（打坐了約 10 分鐘）。"]


def test_sitting_doubles_the_natural_regen(game):
    cfg = game.content.config
    game.state.player.stamina = 0
    game.choose("act:rest")
    game.advance(1800)
    sitting = 1800 / cfg.stamina_regen_seconds * cfg.rest_regen_multiplier
    assert game.state.player.stamina == pytest.approx(sitting)
    game.choose("act:stand")
    game.advance(1800)
    assert game.state.player.stamina == pytest.approx(sitting + 1800 / cfg.stamina_regen_seconds)


def test_sitting_counts_real_time_between_syncs(game):
    cfg = game.content.config
    game.sync(1000.0)
    game.state.player.stamina = 0
    game.choose("act:rest")
    game.sync(1000.0 + 1800)
    assert game.state.player.stamina == pytest.approx(1800 / cfg.stamina_regen_seconds * cfg.rest_regen_multiplier)


def test_sitting_ends_by_itself_once_stamina_is_full(game):
    game.state.player.stamina = game.content.config.stamina_max - 1
    game.choose("act:rest")
    game.advance(HOUR)
    assert game.state.player.resting_since is None
    assert game.state.player.stamina == game.content.config.stamina_max
    entry = game.state.journal[0]
    assert entry.title == "起身" and "回滿" in entry.lines[0]


# ── 事件與檢定 ────────────────────────────────────────────


def _explore_finds_events(game):
    """探索三選一：讓探索一定走「事件」那一支（這些測試看的是事件本身，不是探索抽到哪一支）。"""
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]


def test_explore_presents_event_and_resolves_check(game):
    _explore_finds_events(game)
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert ids(game) == ["choice:0", "choice:1"]
    game.choose("choice:0")
    assert game.state.pending_event is None
    assert game.state.player.stats["good"] == 2
    assert game.state.world.trends["kou"] == 25
    assert "（成功）" in game.state.log


def test_an_event_choice_that_lifts_the_name_to_the_threshold_grants_the_insight(game):
    """走真的事件選項（Game.choose → apply_effect）：善名 14 +2 到門檻，悟得浩然，寫進江湖紀錄。"""
    game.state.pending_event = "drunk"
    game.state.player.stats["good"] = 14
    game.rng = FixedRandom(0.0)  # 檢定必定成功：逼問，善名 +2
    game.choose("choice:0")
    assert game.state.player.insights == ["haoran"]
    assert any("浩然" in m for m in game.state.log)


def test_self_check_shows_one_bracketed_line_and_takes_the_fail_branch(game):
    game.state.pending_event = "insight"
    assert [o.label for o in game.options()] == ["運氣衝關（根骨 5：咬咬牙，你應該撐得住。）"]
    # 選項底下沒有另一行（wait 是按下去等模型時換上的字，不是另一行；不是大場面就是空的）
    assert all(o.model_dump().keys() == {"id", "label", "enabled", "wait"} and o.wait == "" for o in game.options())
    game.rng = FixedRandom(0.99)  # 成功率 50%：必定失敗
    game.choose("choice:0")
    log = game.state.log
    assert log.index("（失敗）") < log.index("氣息一亂，只得作罷。")
    assert game.state.player.stats["xinde"] == 0


def test_join_sect_via_socialize(game):
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    game.choose("choice:0")
    assert game.state.player.sect == "cloud"


def test_declining_the_sect_leaves_the_player_unaffiliated(game):
    game.choose("act:socialize")
    game.choose("choice:1")
    assert game.state.player.sect is None


# ── 遭遇/劇情戰：單次判定 ───────────────────────────────────


def test_event_battle_is_fully_automatic_and_a_loss_applies_the_fail_effect(game):
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")  # 應戰翻江龍：必敗，全自動打完
    assert game.state.pending_event is None
    assert not any(i.startswith("tactic:") for i in ids(game))
    assert game.state.player.stats["silver"] == 40
    assert "你敗了。" in game.state.log
    record = game.state.battles[0]
    assert (record.kind, record.event, record.opponent, record.tier) == ("event", "挑戰", "翻江龍", "落敗")
    assert record.notes == ["你敗了。"]
    assert record.changes == ["銀兩 -10"]
    assert "⚔ 湖邊：落敗翻江龍" in game.state.log


def test_event_battle_win_pays_squad_rewards_once_and_applies_choice_effect(game):
    game.content.events["duel"].choices[0].combat = "thug"  # 換成打得贏的水寇小隊
    rules.learn_skill(game.state, game.content, "fist")  # 沒武學＝威力 0，門檻改成比例後真的打不贏
    walk_to(game, "lake")
    game.choose("act:socialize")
    game.rng = FixedRandom(1.0)  # 最佳運氣：穩穩打贏
    game.choose("choice:0")
    p = game.state.player
    assert game.state.pending_event is None
    assert "你擊敗了翻江龍！" in game.state.log
    assert game.state.world.trends["kou"] == 10  # 30 − 20
    assert p.stats["silver"] == 55 and p.stats["xinde"] == 10
    assert p.member.exp == 20


def test_event_battle_win_splits_story_from_numeric_changes(game):
    game.content.events["duel"].choices[0].combat = "thug"
    rules.learn_skill(game.state, game.content, "fist")
    game.content.events["duel"].choices[0].effect.stats = {"fame": 3}
    game.content.events["duel"].choices[0].effect.rumor = "{name}擊敗了翻江龍！"
    walk_to(game, "lake")
    game.choose("act:socialize")
    game.rng = FixedRandom(1.0)
    game.choose("choice:0")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.notes == ["你擊敗了翻江龍！", "（寇亂 -20）", "【江湖傳聞】沈浪擊敗了翻江龍！"]
    assert record.changes == ["名望 +3"]


def test_train_win_is_recorded_with_rewards(game):
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)
    game.choose("act:train")
    record = game.state.battles[0]
    assert (record.kind, record.location, record.opponent) == ("train", "湖邊", "水寇小隊")
    assert record.tier in ("大勝", "險勝")
    assert [(f.name, f.level) for f in record.ours] == [("沈浪", 1)]
    assert (record.exp, record.xinde, record.silver) == (20, 10, 5)
    assert game.state.world.trends["kou"] == 29  # 湖邊 train_trend kou:-1
    assert "⚔ 湖邊：" in "\n".join(game.state.log)


def test_train_loss_costs_a_tenth_of_the_silver(game):
    game.content.locations["lake"].enemies = ["boss"]  # 換成打不贏的翻江龍
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier == "落敗" and record.silver == -5
    assert game.state.player.stats["silver"] == 45


def test_train_win_records_the_trend_as_a_note(game):
    rules.learn_skill(game.state, game.content, "fist")
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.notes == ["（寇亂 -1）"]  # 湖邊 train_trend kou:-1


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"  # 打完接上戰後的事件
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"  # 再串到下一則


# ── 招募與隊伍 ────────────────────────────────────────────


def test_recruit_action_succeeds_and_joins_the_team(game):
    game.rng = FixedRandom(0.1)  # < 0.35：成功
    msgs = game.choose("act:recruit")
    assert msgs == ["【韓鐵】被你的誠意打動，願意追隨於你！"]
    assert game.state.player.team == ["mate"]
    assert game.state.player.stamina == 135  # 只扣一次 15 體力，不是兩次


def test_recruit_action_can_fail(game):
    game.rng = FixedRandom(0.99)  # 遠高於成功率與決鬥率
    msgs = game.choose("act:recruit")
    assert "婉拒" in msgs[0]
    assert game.state.player.team == []


def test_no_recruit_option_when_nobody_is_free_here(game):
    game.world.try_recruit("mate", "李四")
    game.world.try_recruit("pupil", "李四")
    game.world.try_recruit("scholar", "李四")
    assert "act:recruit" not in ids(game)
    assert game.choose("act:recruit") == ["（此刻無法這麼做。）"]


def test_add_and_remove_from_team(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]
    game.remove_from_team("mate")
    assert game.team_members() == [("沈浪", "player")]
    game.add_to_team("mate")
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]


def test_you_yourself_are_never_added_to_or_removed_from_the_team(game):
    """名冊第一列是本人（key "player"）：加入、移出都只回一句話，隊伍裡不會多出一個 "player"。"""
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    for act in (game.add_to_team, game.remove_from_team):
        msgs = act("player")
        assert msgs == ["本人一直都在隊伍裡，不用加入，也不能移出。"]
        assert game.state.player.team == ["mate"]
        assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]


def test_owned_companions_and_roster_lines(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert game.owned_companions() == ["mate"]
    assert game.roster_lines() == [
        ("本人　沈浪　第 1 級", "player"),
        ("韓鐵　第 1 級　出戰", "mate"),
    ]


# ── 深度對話（companion_agent.py 的引擎接線）────────────────


FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


def test_socializing_with_a_deep_interaction_companion_starts_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]
    assert game.scene_text() == "**韓鐵**\n\n他點了點頭。"


def test_continuing_and_leaving_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        msgs = game.choose("talk:0")
        assert msgs == ["他點了點頭。", "（好感度 +1）"]
        assert game.state.player.affinities["mate"] == 1
        msgs = game.choose("talk:leave")
    assert msgs == ["你結束了這段交談，先行告辭。"]
    assert game.state.player.pending_companion is None
    # 小鎮只有他一位大勢人物：交友之外，直接多一顆求見他（名望門檻 0，見得到）
    assert ids(game) == ["act:explore", "act:socialize", "call:mate", "act:recruit", "move:lake", "act:rest"]


def test_socializing_without_a_deep_interaction_companion_falls_through_to_events(game):
    """小鎮的韓鐵沒有標 deep_interaction：交友照舊走一般事件（例如拜師），不會誤觸發對話。"""
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    assert game.state.player.pending_companion is None


def test_locked_figures_use_talk_at_instead_of_recruit_at_for_dialogue(content, game):
    """龍頭人物（kind=locked）不可招募，深度對話走 talk_at，不是 recruit_at。"""
    ch = content.characters["mate"]
    ch.kind, ch.recruit_at, ch.talk_at, ch.deep_interaction = "locked", None, "town", True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert "act:recruit" not in ids(game)  # 鎖定人物不會因為 talk_at 而冒出招募選項


# ── 重複內容的潤色（還要改進第 3 點）─────────────────────────


def test_first_visit_to_a_location_does_not_call_flavor(game):
    with mock.patch.object(flavor, "polish_revisit") as polish:
        walk_to(game, "lake")  # 第一次去湖邊，不是重遊
    polish.assert_not_called()


def test_revisiting_a_location_appends_the_flavor_sentence(game):
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit", return_value="風又吹起了。"):
        msgs = game.travel("town", "dash")  # 疾行：在這次行動裡抵達終點；小鎮開局就去過，是重遊，補一句
    assert f"{game.location_text()}\n\n風又吹起了。" in msgs


def test_a_timed_arrival_never_calls_the_model(game):
    """計時器的 sync 拿著全服行動鎖：路上抵達不叫模型（重遊點綴句、江湖大事潤色都不叫）。"""
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit") as revisit, \
            mock.patch.object(flavor, "polish_world_event") as news:
        game.choose("move:town")  # 小鎮開局就去過：重遊
        game.state.world.trends["kou"] = 50  # 抵達時才跨過「水寇封江」
        game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert "blocked" in game.state.world.flags  # 門檻照樣觸發，只是沒潤色
    revisit.assert_not_called()
    news.assert_not_called()


def test_revisiting_an_important_location_skips_flavor(content, game):
    content.locations["town"].important = True
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit") as polish:
        game.travel("town", "dash")
    polish.assert_not_called()


def test_revisiting_skips_the_sentence_when_flavor_comes_back_empty(game):
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit", return_value=""):
        msgs = game.travel("town", "dash")
    assert game.location_text() in msgs  # 失敗就整句省略，不多附加任何東西


def test_only_the_last_stop_of_a_trip_gets_the_flavor_sentence(game):
    game.state.world.flags.add("cave_open")
    game.state.player.visited |= {"lake", "cave"}
    with mock.patch.object(flavor, "polish_revisit", return_value="風又吹起了。") as polish:
        game.travel("cave", "dash")
    polish.assert_called_once()
    assert polish.call_args.args[1] == "寶洞"


def test_presenting_an_event_for_the_first_time_does_not_call_flavor(game):
    event = next(iter(game.content.events.values()))
    with mock.patch.object(flavor, "polish_event_repeat") as polish:
        game._present(event)
    polish.assert_not_called()


def test_presenting_a_repeated_event_appends_the_flavor_sentence(game):
    event = next(iter(game.content.events.values()))
    game._present(event)
    with mock.patch.object(flavor, "polish_event_repeat", return_value="巷口又傳來同樣的吆喝聲。"):
        head, text = game._present(event)
    assert text.endswith("\n\n巷口又傳來同樣的吆喝聲。")


# ── 練功、療傷 ───────────────────────────────────────────


def _wear(game, wugong: str | None = None, neigong: str | None = None):
    """直接把內容裡的武學配到身上（第一成）：自創已經作廢，測試要「先有一門功夫」就這樣借。"""
    member = game.state.player.member
    if wugong:
        member.wugong_id, member.wugong_level = wugong, 1
    if neigong:
        member.neigong_id, member.neigong_level = neigong, 1


def test_practice_writes_one_merged_journal_entry(game):
    _wear(game, wugong="fist")
    game.state.player.stats["xinde"] = 10
    msgs = game.practice("武學")
    assert msgs == ["【長拳】精進至第2成。", "心得 -1"]  # 第 1 成升第 2 成花 1 點心得
    assert game.state.player.member.wugong_level == 2
    entry = game.state.journal[0]
    assert entry.title == "修練" and entry.tag == msgs[0]
    game.practice("武學")
    assert game.state.player.member.wugong_level == 3
    assert game.state.player.stats["xinde"] == 7  # 再花 2 點
    assert game.state.journal[0].title == "修練"  # 併進同一則


def test_a_failed_practice_does_not_finish_the_tutorial_step(game):
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.stats["xinde"] = 0
    with mock.patch("tianxia.engine.note_action", return_value=[]) as noted:
        game.practice("武學")
    noted.assert_not_called()


def test_a_real_practice_still_reaches_the_tutorial_hook(game):
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.stats["xinde"] = 5
    with mock.patch("tianxia.engine.note_action", return_value=[]) as noted:
        game.practice("武學")
    noted.assert_called_once()
    assert noted.call_args.args[-1] == "practice"


def test_practicing_without_enough_xinde_says_how_much_is_missing(game):
    _wear(game, wugong="fist")
    game.state.player.member.wugong_level = 4
    game.state.player.stats["xinde"] = 1
    msgs = game.practice("武學")
    assert game.state.player.member.wugong_level == 4 and game.state.player.stats["xinde"] == 1
    assert "要 4 點心得，你只有 1 點" in msgs[0] and "還差 3 點" in msgs[0]


def test_a_refused_practice_writes_no_journal_entry(game):
    """練不成（還沒學、心得不足）只回一句話，不留一則「修練」紀錄（武學與成長計畫 F12）。"""
    game.state.player.stats["xinde"] = 0
    before = list(game.state.journal)
    game.state.player.member.wugong_id = None
    game.practice("武學")  # 還沒學
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 4
    msgs = game.practice("武學")  # 心得不足
    assert "心得不足" in msgs[0]
    assert game.state.journal == before


def test_learning_shows_up_on_the_menu_and_costs_no_stamina(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 30
    stamina = game.state.player.stamina
    option = next(o for o in game.options() if o.id == "learn:lake_kick")
    assert option.enabled and "銀兩 10" in option.label
    game.choose("learn:lake_kick")
    assert "lake_kick" in library.owned_arts(game.state)
    assert game.state.player.stamina == stamina


def test_a_lesson_you_cannot_afford_is_listed_but_greyed_out(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 3
    option = next(o for o in game.options() if o.id == "learn:lake_kick")
    assert not option.enabled and "學費 10 兩" in option.label
    assert "（此刻無法這麼做。）" in game.choose("learn:lake_kick")


def test_learning_is_written_to_the_journal_and_the_lesson_leaves_the_menu(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 30
    game.choose("learn:lake_kick")
    entry = game.state.journal[0]
    assert entry.title == "學藝・湖邊腿法" and "銀兩 -10" in entry.changes
    assert "learn:lake_kick" not in ids(game)


def test_melting_a_library_art_writes_one_journal_entry(game):
    player = game.state.player
    player.arts, player.art_levels["lake_kick"], player.stats["xinde"] = ["lake_kick"], 5, 0
    msgs = game.melt_art("lake_kick")
    assert "熔成了心得" in msgs[0] and player.arts == [] and player.stats["xinde"] == 8
    entry = game.state.journal[0]
    assert entry.title == "修練" and entry.tag == msgs[0] and "心得 +8" in entry.changes


def test_melting_an_art_worth_no_xinde_still_counts_as_something_that_happened(game):
    game.state.player.arts = ["lake_kick"]  # 第一成、下品：退 0 心得，但這門武學確實沒了
    game.melt_art("lake_kick")
    assert game.state.player.arts == [] and game.state.journal[0].tag.startswith("你把【湖邊腿法】")


def test_a_refused_melt_writes_no_journal_entry(game):
    game.state.player.member.wugong_id = "basic_fist"
    before = list(game.state.journal)
    assert "先改練" in game.melt_art("basic_fist")[0]  # 身上正在練的
    assert "沒有" in game.melt_art("lake_kick")[0]  # 功法庫裡沒有
    assert "沒有" in game.melt_insight("feng")[0]  # 沒有這個意境
    assert game.state.journal == before


def test_melting_an_insight_writes_one_journal_entry(game):
    game.state.player.insights, game.state.player.stats["xinde"] = ["feng"], 0
    msgs = game.melt_insight("feng")
    assert "化成了心得" in msgs[0] and game.state.player.insights == []
    entry = game.state.journal[0]
    assert entry.title == "修練" and "心得 +10" in entry.changes


def _practice_step_game(game, worn: dict[str, int]):
    """把引導換成「第 1 步＝鍛鍊」（fixture 的引導沒有這一步，照 _install_* 的慣例直接裝進內容），
    身上先配好 worn（種類 → 熟練度），並給足心得（練成要花心得，這裡驗的是引導不是價錢）。回傳（引導步驟的獎勵銀兩）。"""
    from tianxia.models import Effect, TutorialGoal, TutorialStep

    for kind, level in worn.items():
        _wear(game, **{"neigong" if kind == "內功" else "wugong": "breath" if kind == "內功" else "fist"})
        slot = "neigong" if kind == "內功" else "wugong"
        setattr(game.state.player.member, f"{slot}_level", level)
    game.state.player.stats["xinde"] = 100
    reward = 10
    game.content.tutorial.steps = [
        TutorialStep(
            id="t4_practice", text="先修練。", done_when=TutorialGoal(action="practice"),
            reward=Effect(stats={"silver": reward}),
        ),
        TutorialStep(id="t5_next", text="出城。", done_when=TutorialGoal(action="move")),
    ]
    game.state.player.tutorial_step = 0
    return reward


@pytest.mark.parametrize(
    "worn, kind, counts",
    [
        ({}, "武學", False),  # FB-007：沒學過就練不到，不能算完成這一步
        ({}, "內功", False),
        ({"內功": 3}, "武學", False),  # 只有內功時，練「武學」那一欄還是空的
        ({"武學": 3}, "內功", False),
        ({"武學": 1}, "武學", True),  # 有功法、練了一成
        ({"內功": 1}, "內功", True),
        ({"武學": 10}, "武學", True),  # 第十成「練無可練」也算：這一步要的是「你有一門功夫了」
    ],
)
def test_the_practice_tutorial_step_counts_only_when_that_slot_has_an_art(game, worn, kind, counts):
    reward = _practice_step_game(game, worn)
    silver = game.state.player.stats["silver"]
    msgs = game.practice(kind)
    assert "✔ 引導完成" not in msgs  # 引導的訊息走對話框，不進修練頁的訊息（引導重做設計 8.1.3）
    if counts:
        assert game.state.player.tutorial_step == 1
        assert "✔ 引導完成" in game.state.player.guide_done
        assert game.state.player.stats["silver"] == silver + reward
    else:
        assert game.state.player.tutorial_step == 0
        assert game.state.player.guide_done == []
        assert game.state.player.stats["silver"] == silver


def test_the_practice_tutorial_step_counts_a_maxed_art_and_says_so(game):
    _practice_step_game(game, {"武學": 10})
    msgs = game.practice("武學")
    assert "練無可練" in msgs[0]
    assert "✔ 引導完成" in game.state.player.guide_done
    assert game.state.player.tutorial_step == 1


def test_a_practice_that_cannot_be_afforded_does_not_finish_the_step(game):
    """練成花心得：心得不夠就沒練成，引導那一步不能算完成（也不發獎勵）。"""
    reward = _practice_step_game(game, {"武學": 1})
    game.state.player.stats["xinde"] = 0
    silver = game.state.player.stats["silver"]
    msgs = game.practice("武學")
    assert "心得不足" in msgs[0] and game.state.player.member.wugong_level == 1
    assert game.state.player.tutorial_step == 0 and game.state.player.guide_done == []
    assert game.state.player.stats["silver"] == silver
    game.state.player.stats["xinde"] = 1  # 湊到第 1 成升第 2 成的價錢，再練就算了
    game.practice("武學")
    assert game.state.player.tutorial_step == 1
    assert game.state.player.stats["silver"] == silver + reward


def test_practicing_with_nothing_learned_says_so_without_finishing_the_step(game):
    """FB-007 原本的現場：畫面寫「你還沒學武學」，緊接著卻是「✔ 引導完成」。"""
    _practice_step_game(game, {})
    assert game.practice("武學") == ["你還沒學武學，沒東西可以練。"]


def _wugong_step_game(game, worn: dict[str, int]):
    """把引導換成「看地圖 → 身上要有一門武學（has_wugong）→ 出城」；身上先配好 worn（種類 → 熟練度），引導停在
    看地圖那一步。回傳 has_wugong 那一步的獎勵銀兩。正式內容的 t4_practice 已經改成看「練功」這個動作
    （開局就送了武學，has_wugong 一開始就成立，教不到練成），這裡留著測 has_wugong 這種條件本身。"""
    from tianxia.models import Effect, TutorialGoal, TutorialStep

    for kind, level in worn.items():
        _wear(game, **{"neigong" if kind == "內功" else "wugong": "breath" if kind == "內功" else "fist"})
        setattr(game.state.player.member, f"{'neigong' if kind == '內功' else 'wugong'}_level", level)
    reward = 10
    game.content.tutorial.steps = [
        TutorialStep(id="t2_map", text="看地圖。", done_when=TutorialGoal(action="view_map")),
        TutorialStep(
            id="t4_practice", text="先修練。", done_when=TutorialGoal(has_wugong=True),
            reward=Effect(stats={"silver": reward}),
        ),
        TutorialStep(id="t5_next", text="出城。", done_when=TutorialGoal(action="move")),
    ]
    game.state.player.tutorial_step = 0
    return reward


def test_a_maxed_wugong_finishes_the_practice_step_as_soon_as_it_comes_up(game):
    """W6 Important 1：修練頁的鍛鍊鈕在第十成是灰的，所以走到這一步之前就練滿的人按不了「鍛鍊」。
    這一步改成「身上有一門武學」：前一步一完成，同一次 note_action 就接著完成它。"""
    reward = _wugong_step_game(game, {"武學": 10})
    silver = game.state.player.stats["silver"]
    game.view_map()
    assert game.state.player.guide_done.count("✔ 引導完成") == 2  # 對話框列出兩步（RF2）
    assert game.state.player.tutorial_step == 2
    assert game.state.player.stats["silver"] == silver + reward
    assert game.guide_box()["text"] == "出城。"


def test_only_a_neigong_never_finishes_the_wugong_step_until_a_wugong_is_worn(game):
    """只有內功時：鍛鍊內功、看地圖、練空著的武學都不算；身上有了一門武學再練才算（W5 的規則在這裡有洞：練內功也算）。"""
    _wugong_step_game(game, {"內功": 10})
    game.view_map()
    assert game.state.player.tutorial_step == 1
    for act in (lambda: game.practice("內功"), lambda: game.practice("武學"), game.view_map):
        act()
        assert game.state.player.tutorial_step == 1 and game.state.player.guide_done == []
    _wear(game, wugong="fist")
    game.state.player.stats["xinde"] = 5  # 練成要花心得
    game.practice("武學")
    assert "✔ 引導完成" in game.state.player.guide_done
    assert game.state.player.tutorial_step == 2


def test_art_detail_of_a_worn_art_uses_the_slots_level(game):
    """FB-006：功法卡。配在身上的那一門，熟練度看身上那一欄（內功、武學各一欄）。"""
    _wear(game, wugong="fist", neigong="breath")
    game.state.player.member.wugong_level = 5
    game.state.player.member.neigong_level = 7
    wugong = game.art_detail("fist")
    assert wugong.startswith("【長拳】") and "\n第5成 " in wugong
    assert "\n第7成 " in game.art_detail("breath")


def test_art_detail_of_a_library_art_uses_its_own_kept_level(game):
    """功法庫裡的那一門用換下來時存的熟練度（art_levels）；沒存過的從第一成算（見 team.switch_art）。"""
    stored = MartialArt(
        id="沉柳纏勁", name="沉柳纏勁", kind="武學", quality="上品", attribute="柔",
        base_power=28.0, top_power=72.0, creator="沈浪", note="以柔勁纏住兵刃，借力卸力。",
    )
    assert game.world.claim_skill_name(stored)
    game.state.player.arts.append(stored.id)
    assert game.art_detail(stored.id) == skillview.art_card(stored, 1)
    game.state.player.art_levels[stored.id] = 4
    card = game.art_detail(stored.id)
    assert card == skillview.art_card(stored, 4)
    assert card.endswith("以柔勁纏住兵刃，借力卸力。")


def test_art_detail_shows_the_players_own_quality(game):
    """武學與成長 Task 3：功法卡寫玩家自己那一份的品質與威力，全服登記的那一筆不動。"""
    registered = MartialArt(
        id="沉柳纏勁", name="沉柳纏勁", kind="武學", quality="中品", attribute="柔",
        base_power=16.0, top_power=44.0, creator="沈浪",
    )
    assert game.world.claim_skill_name(registered)
    game.state.player.member.wugong_id = registered.id
    game.state.player.art_quality[registered.id] = "絕學"
    card = game.art_detail(registered.id)
    assert card.startswith("【沉柳纏勁】絕學・屬柔")
    assert game.world.get_skill(registered.id).quality == "中品"


def test_art_detail_shows_the_players_own_quality_of_a_basic_art(game):
    """開局送的基礎武學也一樣：功法卡寫玩家自己那一份的品質，內容裡那一筆不動。"""
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.art_quality["basic_fist"] = "上品"
    assert game.art_detail("basic_fist").startswith("【粗淺拳腳】上品・屬實")
    assert game.content.skills["basic_fist"].quality == "下品"


def test_art_detail_of_an_art_that_is_not_yours_is_not_found(game):
    other = MartialArt(
        id="鐵柳纏勁", name="鐵柳纏勁", kind="武學", quality="中品", attribute="剛",
        base_power=16.0, top_power=44.0, creator="別人",
    )
    assert game.world.claim_skill_name(other)
    assert game.art_detail("鐵柳纏勁") == "（找不到這門功法。）"  # 世界裡有，但不是你的
    assert game.art_detail("ghost") == "（找不到這門功法。）"
    game.state.player.arts.append("ghost")  # 庫裡記著、內容與世界裡都沒有
    assert game.art_detail("ghost") == "（找不到這門功法。）"


def test_heal(game):
    assert game.heal() == ["氣血無恙，不用療傷。"]
    member = game.state.player.member
    member.neili = 10.0  # 只有輕傷：會自己回，不該收錢（療傷按內傷計價，見 team.heal_cost）
    assert game.heal() == ["氣血無恙，不用療傷。"]
    member.injury = 40.0
    game.state.player.stats["silver"] = 999
    msgs = game.heal()
    assert msgs[0].startswith("療傷完畢")
    assert member.injury == 0.0 and member.neili is None


# ── 閉關 ──────────────────────────────────────────────


def test_seclusion_grants_xinde(game):
    game.seclude(4)
    assert ids(game) == ["act:break"]
    game.advance(4 * HOUR)
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 75  # 4 小時 × 15 × (1 + 5/20)


def test_seclusion_countdown_says_real_hours(content, game):
    """FB-062：出關的倒數標「現實」，而且照現實小時算（世界時鐘 ÷ time_scale）：time_scale 2 時，世界 4 小時＝現實 2 小時。"""
    content.config.time_scale = 2.0
    assert game.seclude(4) == ["你閉關靜修，預計現實 2 小時後出關；閉關期間氣血回復加倍。"]
    assert game.status_data()["busy_hours"] == 2.0
    assert "🧘 閉關中，現實約 2.0 小時後出關" in game.status_text()


def test_break_seclusion_early(game):
    game.seclude(4)
    game.advance(HOUR)
    game.choose("act:break")
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 19  # round(1 × 15 × 1.25)


def test_cannot_seclude_while_busy_with_something_else(game):
    game.state.pending_event = "drunk"
    assert game.seclude(4) == ["你現在無法閉關。"]


# ── 時間、賽季 ────────────────────────────────────────────


def test_stamina_regenerates_with_time(game):
    game.state.player.stamina = 0
    game.advance(600)
    assert game.state.player.stamina == pytest.approx(600 / game.content.config.stamina_regen_seconds)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)
    game.sync(1010.0)
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(600 / game.content.config.stamina_regen_seconds)


def test_season_ends_by_time(game):
    game.advance(2 * DAY)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags
    assert ids(game) == ["season:resting"]


def test_admin_next_season_resets_and_keeps_the_name_and_last_real(game):
    game.content.config.admins = ["沈浪"]
    game.sync(1000.0)
    game.advance(2 * DAY)
    game.admin_next_season(now=2000.0)
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"
    assert game.state.player.season_number == 2
    assert game.state.last_real == 1000.0


# ── 共享賽季：跨玩家傳播（真正共享賽季，取代每個玩家各自獨立的大勢/門檻）──────────


def test_two_players_start_in_the_same_shared_season(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    assert a.state.world.trends == b.state.world.trends
    assert a.state.world.storyline == b.state.world.storyline


def test_one_players_trend_push_is_invisible_to_another_until_they_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    a.state.world.trends["kou"] = 55
    a._save_season()
    assert b.state.world.trends["kou"] == 30  # 乙還沒同步，看不到甲剛才的改動
    b.sync(1000.0)
    assert b.state.world.trends["kou"] == 55  # 同步後就看到了


def test_one_players_action_ending_the_season_propagates_to_another_on_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    a.state.world.trends["kou"] = 80
    from tianxia.world import check_thresholds
    check_thresholds(a.state, content, a.world, a.client)
    a._save_season()
    assert a.state.world.ended
    assert not b.state.world.ended  # 乙還沒同步
    b.sync(1000.0)
    assert b.state.world.ended and b.state.world.ending_title == a.state.world.ending_title


def test_new_season_propagates_to_another_player_on_their_next_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    b.state.player.affinities["mate"] = 42
    b.state.player.member.level = 5
    a.advance(2 * DAY)
    assert a.state.world.ended
    a.content.config.admins = ["甲"]
    a.admin_next_season(now=1.0)
    assert a.state.player.season_number == 2

    b.sync(1000.0)  # 乙完全沒點任何東西，只是連線期間剛好同步到
    assert b.state.player.season_number == 2
    assert not b.state.world.ended
    assert b.state.player.affinities["mate"] == 4  # 好感度只帶一成（Config.affinity_carry_ratio），無條件捨去
    assert b.state.player.member.level == 1  # 角色本身重新開始


def test_a_brand_new_player_joining_mid_season_sees_the_current_shared_state(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    a.state.world.trends["kou"] = 70
    a._save_season()
    b = Game.new(content, "乙", rng=random.Random(2), world=world)  # 乙中途才加入
    assert b.state.world.trends["kou"] == 70
    assert b.state.player.season_number == 1


def test_a_fresh_server_waits_for_the_admin(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert [(o.id, o.enabled) for o in game.options()] == [("season:preparing", False)]
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]


def test_only_an_admin_can_open_the_season(content, world):
    content.config.auto_open_first_season = False
    content.config.admins = ["管理者"]
    player = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert player.admin_open_season(now=0.0) == ["（只有管理者能開季。）"]
    admin = Game.new(content, "管理者", rng=random.Random(2), world=world)
    admin.admin_open_season(now=0.0)
    assert world.season_phase() == "running"
    assert admin.admin_open_season(now=1.0) == ["（現在不是籌備期，無法開季。）"]
    player.sync(10.0)
    assert "act:explore" in ids(player)


def test_the_shared_clock_does_not_run_while_preparing(content, world):
    content.config.auto_open_first_season = False
    content.config.time_scale = 60
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.sync(1000.0)
    game.sync(1010.0)
    assert game.state.world.time == 0


def test_travel_is_refused_while_preparing(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert game.travel("lake") == ["（賽季籌備中，等待管理者開季。）"]
    assert game.state.player.location == "town"


def test_nothing_personal_can_be_done_while_preparing(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    waiting = ["（賽季籌備中，等待管理者開季。）"]
    assert game.practice("武學") == waiting
    assert game.heal() == waiting
    assert game.add_to_team("mate") == waiting
    assert game.remove_from_team("mate") == waiting
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert game.state.player.busy_until is None
    assert game.state.player.member.wugong_id is None
    game.state.player.insights = ["feng"]
    game.state.player.stats["xinde"] = 500
    assert game.forge(None, ["feng", "feng"]) == waiting
    assert game.state.player.insights == ["feng"] and game.state.player.stats["xinde"] == 500
    assert game.switch_art("驚雷掌") == waiting


def test_players_cannot_start_the_next_season_themselves(game):
    game.advance(2 * DAY)
    assert game.choose("season:new") == ["（此刻無法這麼做。）"]
    assert game.admin_next_season(now=0.0) == ["（只有管理者能開啟下一季。）"]
    assert game.state.world.ended


def test_admin_next_season_needs_the_season_to_be_over(game):
    game.content.config.admins = ["沈浪"]
    assert game.admin_next_season(now=0.0) == ["（這一季還沒結束，無法開啟下一季。）"]


# ── 換季重來（企劃者 2026-10-04：試玩伺服器的帳號與江湖史保留，角色照換季規則重來）──


def test_season_roll_resets_the_character(content, world):
    """管理者立刻收季、開下一季，玩家下次同步時角色整份重來：陣營、武學、素材、銀兩、心得回到新角色的樣子；
    只留引導進度、對話紀錄，與一成的好感度（無條件捨去）；上一季的江湖史跨季看得到。"""
    _install_factions(content)
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    fresh = new_game_state(content, "玩家").player
    p = player.state.player
    p.faction = "guan"
    p.member.wugong_id, p.member.wugong_level = "fist", 3
    p.materials = {"gang_1": 2}
    p.stats["silver"], p.stats["xinde"] = 999, 77
    p.affinities = {"mate": 80, "friend": 5}
    p.relationship_notes = {"mate": "並肩作戰過的朋友"}
    p.dialogue_history = {"mate": [{"role": "user", "content": "久仰"}]}
    p.tutorial_step = 2
    player.sync(100.0)  # 投靠名冊記下他的陣營
    assert world.faction_counts() == {"guan": 1}

    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)

    p = player.state.player
    assert p.season_number == world.get_season_number() == 2
    assert p.faction is None and world.faction_counts() == {}  # 新的一季又是散人，名冊也是新的
    assert p.member.wugong_id is None and p.materials == {}
    assert p.stats == fresh.stats  # 銀兩、心得回到新角色的值
    assert p.affinities == {"mate": 8, "friend": 0}  # 80→8、5→0
    assert p.relationship_notes == {"mate": "並肩作戰過的朋友"}
    assert p.dialogue_history == {"mate": [{"role": "user", "content": "久仰"}]}
    assert p.tutorial_step == fresh.tutorial_step  # 2 還沒做完（共 3 步）：換季是新角色，引導從頭來（FB-034）
    assert "賽季落幕" in player.chronicle_text()


def _roll_one_season(content, world, tutorial_step=None, skip=False):
    """建一個玩家、把引導調到指定的一步（或略過），管理者收季再開下一季，玩家同步一次；回傳玩家的 Game。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    if tutorial_step is not None:
        player.state.player.tutorial_step = tutorial_step
    if skip:
        player.skip_tutorial()
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    assert player.state.player.season_number == 2
    return player


@pytest.mark.parametrize("unfinished", [0, 1, 2], ids=["first", "second", "last"])
def test_season_roll_restarts_an_unfinished_tutorial(content, world, unfinished):
    """引導做到一半的人，新一季是新角色、沒有武學：下一步不能再叫他出城遊歷，要回到新角色的起始步（FB-034）。"""
    assert unfinished < len(content.tutorial.steps)
    start = new_game_state(content, "玩家").player.tutorial_step  # 照新角色的起始值，不寫死 0
    player = _roll_one_season(content, world, tutorial_step=unfinished)
    assert player.state.player.tutorial_step == start
    assert guide.tutorial_active(player.state, content)
    assert guide.next_hint(player.state, content) == f"（說書人）{content.tutorial.steps[start].text}"


def test_season_roll_keeps_a_finished_tutorial_finished(content, world):
    steps = len(content.tutorial.steps)
    player = _roll_one_season(content, world, tutorial_step=steps)
    assert player.state.player.tutorial_step == steps
    assert not guide.tutorial_active(player.state, content)  # 引導不再出現


def test_season_roll_keeps_a_skipped_tutorial_skipped(content, world):
    player = _roll_one_season(content, world, skip=True)
    assert player.state.player.tutorial_step == len(content.tutorial.steps)
    assert not guide.tutorial_active(player.state, content)


def test_admin_end_season_only_while_running(content, world):
    content.config.auto_open_first_season = False
    content.config.admins = ["管理者"]
    player = Game.new(content, "甲", rng=random.Random(1), world=world)
    admin = Game.new(content, "管理者", rng=random.Random(2), world=world)
    not_running = ["（賽季不在進行中，沒有可以收的。）"]

    before = world.get_season()
    assert admin.admin_end_season(now=0.0) == not_running  # 籌備中
    assert world.season_phase() == "preparing" and world.get_season() == before

    admin.admin_open_season(now=0.0)
    before = world.get_season()
    assert player.admin_end_season(now=1.0) == ["（只有管理者能收季。）"]  # 非管理者
    assert world.season_phase() == "running" and world.get_season() == before

    msgs = admin.admin_end_season(now=2.0)
    assert world.season_phase() == "resting"
    assert any("賽季落幕" in m for m in msgs) and "【天下武學榜】" in msgs  # 結局與武學榜都在
    season = world.get_season()
    assert season.ended and season.time == before.time  # 季的時間停在收季那一刻
    assert admin.state.world.ended  # 管理者自己的畫面也跟著進休季
    assert admin.state.journal[0].title == "收季" and admin.state.journal[0].tag == "管理者"  # 跟開季一樣留一則（最新的在最前面）

    ended = world.get_season()
    assert admin.admin_end_season(now=3.0) == not_running  # 休季
    assert world.get_season() == ended


@pytest.mark.parametrize("under_way", [False, True], ids=["muster", "active"])
def test_admin_end_season_with_battle_running(content, game, under_way):
    """決戰還在集結或開打時收季：照自然收季的做法（試玩回饋 FB-015）直接清掉、不套用結果，戰況不變。"""
    definition = _install_battle_def(content)
    content.config.admins = ["沈浪"]
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    if under_way:
        with at(game, 1000.0 + 601):
            assert ids(game) == ["battle:act:safe", "battle:act:aggressive"]  # 開打了
    trends = dict(game.world.get_season().trends)

    game.admin_end_season(now=1000.0 + 700)

    assert game.world.get_battle() is None
    assert game.world.season_phase() == "resting"
    assert dict(game.world.get_season().trends) == trends  # 沒有套用決戰的結果
    assert not any("官軍大勝" in entry.text for entry in game.world.get_season().chronicle)
    assert ids(game) == ["season:resting"]


def test_admin_end_season_leaves_a_finished_battle_alone(content, game):
    """已經打完的決戰不是「沒打完」：收季不去動它（跟 _battle_status 一樣只清沒打完的）。"""
    definition = _install_battle_def(content)
    content.config.admins = ["沈浪"]
    game.world.start_battle(definition, now=1000.0)
    game.world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    game.admin_end_season(now=1000.0)
    battle = game.world.get_battle()
    assert battle is not None and battle.phase == "ended"


# ── 新手引導 ──────────────────────────────────────────────


def test_new_game_starts_tutorial_at_step_zero(content):
    fresh = Game.new(content, "新人", world=open_world())
    assert fresh.state.player.tutorial_step == 0


def test_skip_tutorial(game):
    msgs = game.skip_tutorial()
    assert game.state.player.tutorial_step == len(game.content.tutorial.steps)
    assert msgs == ["（已略過新手引導。）"]


def test_tutorial_runs_through_engine(game):
    assert "【說書人】先探索一下。" in game.state.log
    game.choose("act:explore")
    assert game.state.player.tutorial_step == 1
    if game.state.pending_event:
        game.choose(ids(game)[-1])
    walk_to(game, "lake")
    assert game.state.player.tutorial_step == 2
    game.view_map()
    assert game.state.player.tutorial_step == 3
    assert "拜入門派" in game.quest_text()


def test_view_map_always_sets_the_flag_even_when_not_the_current_step(game):
    game.view_map()
    game.view_map()
    assert "看過地圖" in game.state.player.flags
    assert game.state.player.tutorial_step == 0


# ── 舊存檔相容 ────────────────────────────────────────────


def test_stale_storyline_is_reset(content, game):
    game.state.world.storyline = "removed_line"
    game.state.world.act = 5
    fresh = Game(content, game.state, world=game.world)
    assert (fresh.state.world.storyline, fresh.state.world.act) == ("main", 0)


def test_old_save_missing_tutorial_step_finishes_the_tutorial(content, game):
    dump = game.state.model_dump()
    del dump["player"]["tutorial_step"]
    old_state = GameState.model_validate(dump)
    fresh = Game(content, old_state, world=game.world)
    assert fresh.state.player.tutorial_step == len(content.tutorial.steps)


def test_stale_world_flags_get_flag_time_backfilled(content, game):
    """共用賽季本身的存檔格式較舊、缺 flag_times 時也要能補上——世界狀態現在是從共用
    儲存拉回來的（見 _reconcile_season），不是直接改 game.state.world 就能模擬，要改
    的是共用儲存裡實際存著的那一份。"""
    season = game.world.get_season()
    season.time = 12345
    season.flags.add("legacy_flag")
    game.world.save_season(season)
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.world.flag_times["legacy_flag"] == 12345


def test_stale_dialogue_reference_is_dropped(content, game):
    game.state.player.pending_companion = "ghost"
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.player.pending_companion is None


def test_stale_learned_skill_reference_is_dropped(content, game):
    game.state.player.member.wugong_id = "ghost_skill"
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.player.member.wugong_id is None


def test_team_members_beyond_the_cap_or_unknown_are_trimmed(content, game):
    game.state.player.team = ["mate", "ghost", "pupil", "scholar", "friend", "hero"]
    fresh = Game(content, game.state, world=game.world)
    from tianxia import team as team_mod

    assert fresh.state.player.team == ["mate", "pupil", "scholar", "friend"][: team_mod.MAX_TEAM_COMPANIONS]


# ── 畫面文字 ──────────────────────────────────────────────


def test_texts_render(game):
    assert "沈浪" in game.status_text()
    assert "小鎮" in game.scene_text()
    assert "寇亂" in game.trends_text() and "寶藏" not in game.trends_text()
    assert game.rumors_text() == "（尚無傳聞。）"
    _explore_finds_events(game)
    game.choose("act:explore")
    assert "醉漢" in game.scene_text()


def test_status_text_shows_the_practice_hint_only_when_xinde_is_idle(game):
    assert "心得" in game.status_text() and "💡" not in game.status_text()
    game.state.player.stats["xinde"] = game.content.config.xinde_hint_threshold
    assert "💡" not in game.status_text()  # 兩欄都空著：沒有哪一門可以練
    _wear(game, wugong="fist", neigong="breath")
    assert "💡" in game.status_text() and "練成內功、武學" in game.status_text()
    game.state.player.member.wugong_level = game.state.player.member.neigong_level = 10
    assert "💡" not in game.status_text()  # 沒東西可練、手上也沒有意境可合成


def test_visited_and_map(game):
    assert game.state.player.visited == {"town"}
    walk_to(game, "lake")
    assert game.state.player.visited == {"town", "lake"}
    assert "<svg" in game.world_map_svg()
    assert "<svg" in game.minimap_svg()


# ── 安排前往 ──────────────────────────────────────────────


@pytest.mark.parametrize(("mode", "cost"), [("walk", 0), ("hurry", 8), ("dash", 15)])
def test_travel_charges_the_stamina_of_the_chosen_way_up_front(game, mode, cost):
    game.state.world.flags.add("cave_open")  # 小鎮—湖邊 3 分鐘＋湖邊—寶洞山路 4.5 分鐘
    game.state.player.stamina = 100
    game.travel("cave", mode)
    assert game.state.player.stamina == 100 - cost


def test_dash_arrives_at_once_and_writes_one_entry(game):
    game.state.world.flags.add("cave_open")
    before = len(game.state.journal)
    msgs = game.travel("cave", "dash")
    p = game.state.player
    assert p.location == "cave" and {"lake", "cave"} <= p.visited
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("前往 寶洞（途經 湖邊）", "疾行立刻到", [], ["體力 -15"])
    assert msgs[-1] == game.location_text() == game.scene_text()


def test_dash_stops_when_the_season_ends_on_the_way(game):
    game.state.world.flags.add("cave_open")
    game.state.world.trends["kou"] = 80  # 一走到湖邊就觸發「水寇稱霸」，賽季落幕
    game.travel("cave", "dash")
    assert game.state.world.ended and game.state.player.location == "lake"
    assert game.state.journal[0].tag == "賽季落幕，停在 湖邊"


def test_travel_is_refused_with_a_reason(game):
    before = len(game.state.journal)
    game.state.pending_event = "drunk"
    assert game.travel("lake") == ["（先回江湖頁處理「醉漢」。）"]
    game.state.pending_event = None
    game.state.player.busy_until = 3600.0
    assert game.travel("lake") == ["（閉關中，不能安排前往。）"]
    game.state.player.busy_until = None
    game.state.world.ended = True
    assert game.travel("lake") == ["（賽季已結束，不能安排前往。）"]
    game.state.world.ended = False
    assert game.travel("town") == ["（無法安排前往這裡。）"]  # 所在地
    assert game.travel("cave") == ["（無法安排前往這裡。）"]  # 未開放
    assert game.travel("nowhere") == ["（無法安排前往這裡。）"]
    assert game.travel("lake", "fly") == ["（無法安排前往這裡。）"]
    game.state.player.stamina = 5
    assert game.travel("lake", "dash") == ["（體力不足，疾行要 6 體力。）"]
    assert game.travel_refusal("lake", "hurry") is None
    assert game.state.player.location == "town" and game.state.player.stamina == 5
    assert len(game.state.journal) == before


def test_a_chained_event_names_the_step_that_is_pending_now_when_travel_is_refused(game):
    """FB-063：多段事件走到下一段（next_event）之後，不能出發的原因寫的是「現在」待處理的那一段，不是第一段。"""
    game._present(game.content.events["chain_a"])
    assert game.travel_refusal("lake") == "先回江湖頁處理「跟蹤」"
    game.choose("choice:0")  # 繼續：接到「倉庫」
    assert game.state.pending_event == "chain_b"
    assert game.travel_refusal("lake") == "先回江湖頁處理「倉庫」"
    assert game.travel("lake") == ["（先回江湖頁處理「倉庫」。）"]
    game.choose("choice:0")  # 離開：事件了結，路就通了
    assert game.state.pending_event is None and game.travel_refusal("lake") is None


def test_walking_takes_time_and_arrives_on_the_next_sync(game):
    game.sync(1000.0)
    game.choose("move:lake")  # 夾具：小鎮—湖邊 3 分鐘
    p = game.state.player
    assert p.location == "town" and p.journey.path == ["lake"] and p.journey.arrive_at == [180.0]
    game.sync(1000.0 + 60)
    assert p.location == "town" and p.journey is not None  # 還在路上
    game.sync(1000.0 + 200)
    assert p.location == "lake" and p.journey is None and "lake" in p.visited


def test_hurrying_takes_half_the_time(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "hurry")
    assert game.state.player.journey.arrive_at == [pytest.approx(90.0), pytest.approx(225.0)]  # (3＋4.5 分鐘) × 30 秒


def test_on_the_road_you_can_turn_back_but_not_do_what_needs_a_place(game):
    game.choose("move:lake")
    opts = game.options()
    assert [(o.id, o.enabled) for o in opts] == [
        ("act:on_road", False), ("road:back", True),
        ("road:think", True), ("road:ask", True), ("road:survey", True), ("road:gather", True),
    ]
    assert "抵達湖邊" in opts[0].label
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert game.travel_refusal("lake") is None  # 路上設計 3.1：在路上也能安排前往（改道）


def test_the_status_bar_shows_the_arrival_countdown_and_the_scene_does_not_repeat_it(game):
    """FB-046：抵達的倒數只寫在狀態列（每一頁都看得到）；場景只寫「在路上」與路上能做什麼，不再寫一次。
    FB-062：只寫現實的倒數，不寫抵達的時刻——季曆跑得比現實快，兩種時間混在一行會讓人算不出來。"""
    game.choose("move:lake")
    assert "🧭 在路上：往湖邊（步行），現實約 3 分鐘後抵達" in game.status_text()
    assert game.status_data()["journey"] == "往湖邊（步行），現實約 3 分鐘後抵達"
    scene = game.scene_text()
    assert scene.startswith("**在路上**") and "到了會自己抵達" in scene
    assert "現實約" not in scene and "第1天 00:03" not in scene


def test_the_journey_line_counts_real_minutes_even_when_the_world_clock_runs_faster(content, game):
    """FB-062：世界時鐘的一段秒數 ÷ time_scale ＝ 現實秒；狀態列的「現實約 N 分鐘」照現實算，後面的站名照舊。"""
    content.config.time_scale = 3.0  # 世界時鐘每現實秒走 3 秒：湖邊 3 分鐘的路程（世界秒）只要現實 1 分鐘
    game.choose("move:lake")
    assert game.status_data()["journey"] == "往湖邊（步行），現實約 1 分鐘後抵達"


def test_the_journey_line_names_the_next_station_on_a_multi_leg_trip(game):
    """FB-062：多段的路，倒數算到最後一站，後面接「；下一站某某」。"""
    game.state.world.flags.add("cave_open")
    msgs = game.travel("cave", "walk")
    line = game.status_data()["journey"]
    assert line.startswith("往寶洞（步行），現實約 ") and "分鐘後抵達；下一站湖邊" in line
    assert "第" not in line  # 沒有季曆時刻
    depart = next(m for m in msgs if "前往寶洞" in m)  # 出發的那一句也一樣只寫現實的倒數
    assert "現實約 " in depart and "分鐘後抵達" in depart and "第" not in depart


def test_every_station_on_the_way_fires_the_arrival_rules(game):
    game.state.world.flags.add("cave_open")
    game.state.player.tutorial_step = 1  # 下一步是「去湖邊」
    game.travel("cave", "walk")
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 只走到湖邊
    p = game.state.player
    assert p.location == "lake" and "lake" in p.visited and p.journey.reached == 1
    assert p.tutorial_step == 2  # 抵達湖邊就完成這一步，不必等到終點
    game.advance(p.journey.arrive_at[1] - game.state.world.time)
    assert p.location == "cave" and p.journey is None


def test_departing_is_not_arriving_for_the_tutorial(game):
    game.state.player.tutorial_step = 1  # 「去湖邊」
    game.choose("move:lake")
    assert game.state.player.tutorial_step == 1
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert game.state.player.tutorial_step == 2


def test_a_threshold_crossed_on_arrival_reaches_the_shared_season(game):
    game.sync(1000.0)
    game.choose("move:lake")
    # sync 會先換成共用賽季的那一份，所以改共用的；追趕那 200 秒不滿一小時，世界本身不檢查門檻
    game.world.mutate_season(lambda season: season.trends.__setitem__("kou", 80))
    game.sync(1000.0 + 200)  # 抵達時才檢查：水寇稱霸，賽季落幕
    assert game.state.world.ended and game.world.get_season().ended


def test_a_season_that_ends_on_the_road_leaves_you_where_you_got_to(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "walk")
    game.state.world.ended = True
    game.advance(0)  # 時鐘停在落幕那一刻：還沒到的站不會再到
    assert game.state.player.journey is None and game.state.player.location == "town"
    assert game.state.journal[0].tag == "賽季落幕，停在 小鎮"


def test_a_stale_journey_is_dropped_on_load(content, game):
    game.state.player.journey = Journey(mode="walk", path=["nowhere"], arrive_at=[60.0])
    game.state.player.leg_actions = {"think"}
    reloaded = Game(content, game.state, world=game.world)
    assert reloaded.state.player.journey is None
    assert reloaded.state.player.leg_actions == set()  # 那段路不在了：下次出發是新的一段，路上小事都還能做


def test_a_rerouted_journey_whose_road_end_is_gone_is_dropped_on_load(content, game):
    """改道後的半段路，另一頭（origin）在內容改版時被拿掉：路已經不存在，丟掉這趟路程，不然算位置會找不到地點。"""
    game.state.player.journey = Journey(mode="walk", path=["town"], arrive_at=[60.0], origin="nowhere", share=0.5)
    assert Game(content, game.state, world=game.world).state.player.journey is None
    game.state.player.location = "nowhere"  # 所在地被拿掉、改回起點：腳下這段路也不存在了
    game.state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[60.0])
    reloaded = Game(content, game.state, world=game.world)
    assert reloaded.state.player.journey is None and reloaded.state.player.location == content.scenario.start_location


# ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）──────────


def _install_battle_def(content):
    from tianxia.models import (
        BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    )

    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[BattleOption(text="穩紮穩打", tag="safe"), BattleOption(text="全力進攻", tag="aggressive")],
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "aggressive": BattleActionEffect(trend_delta=5, neili_damage=20),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
        rounds_per_act=1,  # 一幕一回合：第一回合結算完就看戰局收場（保底結果沒有門檻，一定是官軍大勝）
    )
    content.battles[definition.id] = definition
    return definition


def _install_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾"),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


def test_a_free_agent_can_join_a_faction_where_it_recruits(content, game):
    _install_factions(content)
    assert "faction:guan" in ids(game)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert "faction:guan" not in ids(game)


def test_the_join_option_only_shows_at_the_factions_own_places(content, game):
    _install_factions(content)
    walk_to(game, "lake")
    assert not any(i.startswith("faction:") for i in ids(game))


def test_with_factions_the_muster_only_offers_your_own_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert [i for i in ids(game) if i.startswith("battle:")] == ["battle:join:huang"]
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]
        assert "選擇陣營" in game.scene_text()


def test_with_factions_joining_the_other_side_directly_is_refused(content, game):
    """選單上本來就不會出現對方陣營的加入選項；直接呼叫 _battle_choose 也一樣擋得住。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    assert game._battle_choose("join:guan") == ["（你只能站在自己陣營這一邊。）"]
    assert game.world.get_battle().participants == {}


def test_with_factions_a_free_agent_or_an_outside_faction_watches_and_keeps_playing(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        for faction in (None, "haoqiang"):
            game.state.player.faction = faction
            assert "act:explore" in ids(game)
            assert not any(i.startswith("battle:") for i in ids(game))
            scene = game.scene_text()
            assert "測試決戰" in scene and "觀戰" in scene and "選擇陣營" not in scene


def test_with_factions_a_free_agent_can_leave_the_sidelines_once_the_battle_is_under_way(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert "act:explore" in ids(game)
        assert not any(i.startswith("battle:") for i in ids(game))
        game.choose("faction:guan")
        game.choose("faction:confirm")
        assert game.state.player.faction == "guan"
        assert ids(game) == ["battle:join_late"]  # 投靠了交戰的一方，就能加入戰局


def test_a_watcher_still_sees_their_own_event_below_the_battle(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    _explore_finds_events(game)
    with at(game, 1000.0):
        game.choose("act:explore")
        event = content.events[game.state.pending_event]
        scene = game.scene_text()
    assert "測試決戰" in scene and event.title in scene


def test_with_factions_a_latecomer_joins_their_own_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=0.0)
    # 黃巾已經有人了，單看人數平衡會把後來的人分去官軍；玩家仍要站在自己的黃巾這一邊。
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:join_late")
    assert game.world.get_battle().participants["沈浪"].faction == "huang"


def test_a_battle_with_no_fighters_ends_with_its_fallback_outcome_once_the_round_times_out(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    closed = definition.muster_seconds + 1
    with at(game, closed):
        assert game._battle_status()[0].phase == "active"
    with at(game, closed + definition.round_seconds - 1):
        assert game._battle_status() is not None  # 回合還沒逾時，不提前收場
    with at(game, closed + definition.round_seconds):
        assert "act:explore" in ids(game)
    assert game.world.get_battle().phase == "ended"
    assert any("官軍大勝" in r.text for r in game.world.get_season().chronicle)


def test_status_text_shows_the_faction_of_a_player_without_a_sect(content, game):
    _install_factions(content)
    assert "散人" in game.status_text()
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert "官軍" in game.status_text() and "散人" not in game.status_text()


def test_status_text_shows_both_sect_and_faction(content, game):
    _install_factions(content)
    game.state.player.sect = "cloud"
    assert "流雲派" in game.status_text() and "官軍" not in game.status_text()
    game.state.player.faction = "guan"
    assert "流雲派・官軍" in game.status_text()


def test_no_active_battle_leaves_normal_gameplay_untouched(content, game):
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


def test_an_active_muster_shows_faction_join_options(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert ids(game)[:2] == ["battle:join:guan", "battle:join:huang"]
        assert "測試決戰" in game.scene_text()


def test_the_muster_keeps_the_everyday_menu_under_the_join_buttons(content, game):
    """集結那段時間（企劃者 2026-10-03 決定，FB-009）：人在戰場的人照常探索、移動、打坐，另外多加入的按鈕；
    場景上戰場底下接著自己所在的地點。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert ids(game) == ["battle:join:guan", "battle:join:huang"] + [
            "act:explore", "act:socialize", "act:recruit", "move:lake", "act:rest"]
        scene = game.scene_text()
        assert "測試決戰" in scene and "選擇陣營" in scene and "小鎮" in scene
        game.choose("act:explore")  # 集結中照常探索，不會被擋
        assert game.state.journal[0].title.startswith("探索")


def test_a_fighter_who_joined_sees_it_on_the_button_and_in_the_scene(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 125):
        opts = {o.id: (o.label, o.enabled) for o in game.options()}
        assert opts["battle:join:guan"] == ("已加入【官軍】", False)
        assert opts["battle:join:huang"] == ("加入【黃巾】", True)  # 不分陣營的劇本：集結時還能換邊
        assert opts["act:explore"][1] and "move:lake" in opts
        scene = game.scene_text()
        assert "你已加入【官軍】，集結還剩現實 7 分 55 秒" in scene and "選擇陣營" not in scene
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]


def test_with_factions_a_fighter_who_joined_only_sees_joined(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:huang")
        battle_ids = [o for o in game.options() if o.id.startswith("battle:")]
        assert [(o.id, o.label, o.enabled) for o in battle_ids] == [("battle:join:huang", "已加入【黃巾】", False)]


def test_a_fighter_who_walks_out_during_the_muster_is_away_until_back(content, game):
    """集結時已經加入的人照常可以走動；走出決戰的大區就不在場（沒有加入的按鈕、場景說明離開了），回來就又是「已加入」。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    walk_to(game, "lake")
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
        game.set_move_mode("dash")
        game.choose("move:cave:dash")
        assert game.state.player.location == "cave"
        assert not any(i.startswith("battle:") for i in ids(game))
        assert "你離開了測試北區" in game.scene_text()
        game.choose("move:lake:dash")
        opts = {o.id: (o.label, o.enabled) for o in game.options()}
        assert opts["battle:join:guan"] == ("已加入【官軍】", False)
        assert "你已加入【官軍】" in game.scene_text()


def test_the_battle_scene_shows_which_round_of_how_many(content, game):
    """FB-016：決戰的場景在幕名後面寫第幾回合、一共幾回合，讓人知道還要打多久。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 一幕三回合：整場 3 回合
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        assert "【初探】（第 1／3 回合）雙方試探。" in game.scene_text()
        game.world.mutate_battle(lambda b: battle_instance.submit_action(b, "乙玩家", "safe"))
        game.choose("battle:act:safe")  # 兩人都出手了：第 1 回合結算
        assert game.world.get_battle().round_number == 1
        assert "【初探】（第 2／3 回合）雙方試探。" in game.scene_text()


def test_the_fighting_menu_still_replaces_everything_once_the_muster_closes(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 601):
        assert ids(game) == ["battle:act:safe", "battle:act:aggressive"]


def test_an_unfinished_battle_is_dropped_without_its_outcome_when_the_season_ends(content, game):
    """季一結束，沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了），參戰者回到休季畫面（試玩回饋 FB-015）。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + 601):
        assert ids(game) == ["battle:act:safe", "battle:act:aggressive"]  # 開打了
    trends = dict(game.world.get_season().trends)
    game.world.mutate_season(lambda season: (setattr(season, "ended", True), setattr(season, "ending_title", "天下太平")))
    game.sync(1000.0 + 700)
    with at(game, 1000.0 + 700):
        assert ids(game) == ["season:resting"]
        assert "測試決戰" not in game.scene_text()
    assert game.world.get_battle() is None
    assert dict(game.world.get_season().trends) == trends  # 沒有套用決戰的結果
    assert not any("官軍大勝" in entry.text for entry in game.world.get_season().chronicle)


def test_joining_a_faction_during_muster(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    assert game.world.get_battle().participants["沈浪"].faction == "guan"


def test_muster_auto_closes_once_the_deadline_passes(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    with at(game, 1000.0 + definition.muster_seconds + 1):
        status = game._battle_status()
    assert status is not None and status[0].phase == "active"


def test_submitting_an_action_and_a_bot_auto_fills_then_the_round_resolves(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()  # 推進一次，確保集結已關閉、進入 active
        game.choose("battle:act:safe")  # 人類送出，機器人在同一次 tick 裡自動補上，回合應該已經結算
    battle = game.world.get_battle()
    assert battle.trend != 50  # 已經結算過，trend 被推動了
    assert battle.round.pending_actions == {}  # 回合已經重置


def test_the_player_whose_action_completes_the_round_sees_the_resolution_text(content, game):
    """送出最後一個行動的那個人，自己這次 choose() 的回傳就該看到這一回合真正發生的事
    （不能是空清單）——不管這回合只是普通推進，還是剛好把戰鬥打完。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:safe")
    assert msgs != []
    assert any("官軍大勝" in m or "官軍獲勝" in m for m in msgs)  # _install_battle_def 的保底結果沒有數值門檻，第一回合就分出勝負


def test_waiting_for_others_returns_a_placeholder_message(content, game):
    """送出行動但還有人沒選完，回合不會結算：至少要有個訊息，不能讓畫面看起來像沒反應。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 讓這回合分不出勝負
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:safe")
    assert msgs == ["你選擇了行動，等待其他人……"]


def test_battle_outcome_applies_trend_delta_and_flags_to_the_shared_season(content, game):
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    before = game.world.get_season().trends["kou"]
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
        game.choose("battle:act:safe")
    season = game.world.get_season()
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags
    assert any("官軍大勝" in r.text for r in season.chronicle)


def test_a_battle_that_ends_inside_a_normal_choice_keeps_its_trend_and_flags(content, game):
    """旁觀者按一般選項時，options() 的決戰 tick 剛好讓決戰收場：結果寫進共用賽季之後，choose() 最後的
    _save_season 不能拿記憶體裡比較舊的賽季把大勢與旗標蓋掉（總審查重現過：kou 停在原值、旗標不見）。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "官軍機器人", "guan", neili_cap=100.0, is_bot=True))
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "黃巾機器人", "huang", neili_cap=100.0, is_bot=True))
    game.sync(0.0)
    before = game.state.world.trends["kou"]
    assert before > 0  # 才看得出被扣掉
    with at(game, definition.muster_seconds + 1):  # 集結關閉、兩個機器人補位、這一回合就分出勝負——全在 options() 的 tick 裡
        game.choose("act:explore")
    assert game.world.get_battle().phase == "ended"
    season = game.world.get_season()
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags and "huangjin_decisive_win" in season.flag_times
    assert sum("官軍大勝" in r.text for r in season.chronicle) == 1  # 江湖史只寫一則
    assert game.state.world.trends["kou"] == season.trends["kou"]  # 記憶體裡的那份也跟上了


def test_a_battle_ended_by_a_tick_survives_a_later_travel_save(content, game):
    """同一個根因的另一條路：先有一次 options() 的 tick 把決戰收了場，之後 travel() 的 _save_season 也不能蓋掉它。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "官軍機器人", "guan", neili_cap=100.0, is_bot=True))
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "黃巾機器人", "huang", neili_cap=100.0, is_bot=True))
    game.sync(0.0)
    before = game.state.world.trends["kou"]
    with at(game, definition.muster_seconds + 1):
        game.options()  # 決戰在這裡的 tick 收場
        game.travel("lake")
        assert game.state.player.journey is not None  # 真的出發了，_save_season 才跑得到
    season = game.world.get_season()
    assert game.world.get_battle().phase == "ended"
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags


def test_an_eliminated_participant_sees_a_spectate_only_option(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()  # 讓集結自動關閉
    game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
    with at(game, after_muster):
        opts = game.options()
    assert opts == [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]


def test_a_latecomer_can_join_an_already_active_battle(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 讓集結自動關閉，模擬戰鬥已經開打
        assert ids(game) == ["battle:join_late"]
        game.choose("battle:join_late")
    assert "沈浪" in game.world.get_battle().participants


def test_a_latecomer_is_told_they_can_act_this_round_and_can(content, game):
    """FB-028：晚到的人當回合就能出招（企劃者決定改說法、不改規則），提示要照實說。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3  # 這一回合不會一結算就收場
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 集結關閉，已經開打
        assert game.choose("battle:join_late") == ["你趕到了戰場，這一回合就能出手。"]
        battle = game.world.get_battle()
        assert battle_instance.options_for(battle, definition, "沈浪")
        assert ids(game) == ["battle:act:safe", "battle:act:aggressive"]
        game.choose("battle:act:safe")
    battle = game.world.get_battle()
    assert battle.round_number == 0 and battle.round.pending_actions == {"沈浪": "safe"}  # 送出了、等乙玩家


# ── 決戰選項的江湖紀錄（FB-030：加入與趕到各寫一則，每回合出招不寫）──────────────


def test_joining_a_side_in_the_muster_writes_one_journal_entry(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    before = len(game.state.journal)
    with at(game, 0.0):
        msgs = game.choose("battle:join:guan")
    assert msgs == ["你加入了這場戰局。"]  # 回話照舊
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "測試決戰・加入官軍" and entry.lines == ["你加入了這場戰局。"]


def test_changing_sides_in_the_muster_writes_its_own_entry(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        before = len(game.state.journal)
        game.choose("battle:join:huang")
    assert len(game.state.journal) == before + 1
    assert game.state.journal[0].title == "測試決戰・改選黃巾"


def test_a_refused_join_writes_nothing(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    before = len(game.state.journal)
    with at(game, 1000.0):
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]
    assert len(game.state.journal) == before


def test_joining_late_writes_one_journal_entry_with_the_line_it_returns(content, game):
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    before = len(game.state.journal)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        msgs = game.choose("battle:join_late")
    assert msgs == ["你趕到了戰場，這一回合就能出手。"]
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "測試決戰・趕到戰場" and entry.lines == msgs


def test_a_rounds_action_is_not_journaled(content, game):
    """每回合一句太吵：戰局的敘事在場景裡，收場後補送的那一則才留下完整的結果。"""
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:join_late")
        before = len(game.state.journal)
        assert game.choose("battle:act:safe") == ["你選擇了行動，等待其他人……"]
    assert len(game.state.journal) == before


def test_the_join_entry_is_what_the_just_now_card_shows(content, game):
    """加入寫的那則不是戰鬥紀錄（沒有 battle_id）：「剛剛」放那一則本身，不放戰鬥卡片。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        assert not game.shows_battle_card()
        assert "加入官軍" in game.latest_entry_html()


def test_battle_ending_falls_back_to_normal_gameplay_on_the_next_render(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


# ── 決戰的結果送到每個參戰者手上（FB-027：下次同步時補）──────────────


def _three_round_showdown(content, trend_delta=None):
    """劇本分陣營、一幕三回合（整場 3 回合；穩紮穩打只推 1，不會提前收場），保底結果官軍大勝。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    definition.outcomes[0] = definition.outcomes[0].model_copy(update={"trend_delta": trend_delta or {"kou": -20}})
    return definition


def _fighter(content, game, name, faction):
    """跟沈浪同一個全服世界的另一位玩家（自己的一份 Game），已經投靠 faction。"""
    other = Game.new(content, name, rng=random.Random(1), world=game.world)
    other.state.player.faction = faction
    return other


def _fight_to_the_end(game, definition, now):
    """沈浪每回合自己出手，其他還在場上的人逾時由系統代選，一路打到收場；回傳收場那一刻的時間。"""
    while True:
        with at(game, now):
            game.options()  # 推進：集結關閉，或上一回合逾時、代選、結算
            battle = game.world.get_battle()
            if battle.phase == "ended":
                return now
            if game.state.player.name not in battle.round.pending_actions:
                game.choose("battle:act:safe")
        now = game.world.get_battle().round.opened_real + definition.round_seconds


def _showdown_entries(game):
    """收場補送的那一則（掛著戰報的 battle_id）；加入、趕到寫的紀錄（FB-030）標題也有決戰的名字，但不是戰報。"""
    return [e for e in game.state.journal if "測試決戰" in e.title and e.battle_id is not None]


def test_every_fighter_gets_the_showdown_in_their_journal_and_battle_reports(content, game):
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    fallen = _fighter(content, game, "乙", "huang")
    watcher = Game.new(content, "丙", rng=random.Random(2), world=game.world)  # 散人：打不了，只能觀戰
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(fallen, 0.0):
        game.choose("battle:join:guan")
        fallen.choose("battle:join:huang")
    game.world.mutate_battle(lambda b: setattr(b.participants["乙"], "neili", 8.0))  # 穩紮穩打扣 5：第 2 回合倒下
    start = definition.muster_seconds + 1
    for i in range(3):
        with at(game, start + i), at(fallen, start + i):
            game.choose("battle:act:safe")
            if i < 2:
                fallen.choose("battle:act:safe")  # 兩人都出手了：這一回合結算
    assert game.world.get_battle().phase == "ended"

    entry = game.state.journal[0]  # 收場那一下出手的人當場就有
    assert (entry.title, entry.tag) == ("測試決戰・官軍大勝", "你站在官軍")
    assert entry.lines == ["官軍獲勝。", "你出手 3 回合"]
    assert entry.changes == ["寇亂 -20"]
    report = game.state.battles[0]
    assert report.kind == "showdown" and entry.battle_id == report.id
    assert (report.opponent, report.side, report.tier) == ("黃巾", "官軍", "官軍大勝")
    assert game.shows_battle_card()  # 「剛剛」放這一場的卡片，連得到完整戰報
    assert "威力" not in game.battle_detail(report.id)

    assert _showdown_entries(fallen) == []  # 倒下的那位：下次同步時才補
    fallen.sync(start + 10)
    mine = fallen.state.journal[0]
    assert (mine.title, mine.tag) == ("測試決戰・官軍大勝", "你站在黃巾")
    assert mine.lines == ["官軍獲勝。", "你出手 2 回合", "你在第 2 回合倒下，轉為觀戰"]
    assert fallen.state.battles[0].kind == "showdown" and fallen.state.battles[0].opponent == "官軍"

    watcher.sync(start + 10)
    assert _showdown_entries(watcher) == [] and watcher.state.battles == []

    for g in (game, fallen):  # 再同步一次不會多寫
        g.sync(start + 20)
        assert len(_showdown_entries(g)) == 1 and len(g.state.battles) == 1


def test_an_offline_fighter_gets_the_showdown_on_the_next_sync_without_the_timed_out_rounds(content, game):
    """乙出了第 1 回合就下線（角色只在資料庫裡）：後兩回合逾時由系統代選，不算他自己出手；回來第一次同步就補到。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    start = definition.muster_seconds + 1
    with at(game, start), at(away, start):
        game.choose("battle:act:safe")
        away.choose("battle:act:safe")
    open_characters().save(away.state)
    end = _fight_to_the_end(game, definition, start + 1)
    assert "你出手 3 回合" in game.state.journal[0].lines

    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    assert _showdown_entries(back) == []  # 讀回來還沒同步：還沒補
    back.sync(end + 10)
    entry = back.state.journal[0]
    assert entry.title == "測試決戰・官軍大勝" and entry.changes == ["寇亂 -20"]
    assert "你出手 1 回合" in entry.lines and not any("倒下" in line for line in entry.lines)
    assert back.state.battles[0].kind == "showdown"


def _showdown_ends_the_season(content, game):
    """寇亂 30 → 80 跨過收季的門檻：決戰收場、季的時鐘再走一個鐘頭，季就收了。乙加入之後就下線。回傳那時的時間。"""
    definition = _three_round_showdown(content, trend_delta={"kou": 50})
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    open_characters().save(away.state)
    end = _fight_to_the_end(game, definition, definition.muster_seconds + 1)
    with at(game, end):
        game.advance(HOUR)
    assert game.world.season_phase() == "resting"
    return end


def test_a_fighter_back_during_the_off_season_gets_the_showdown_that_ended_it(content, game):
    end = _showdown_ends_the_season(content, game)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(end + 10)
    assert ids(back) == ["season:resting"]
    entry = back.state.journal[0]
    assert entry.title == "測試決戰・官軍大勝" and entry.changes == ["寇亂 +50"]  # 還是這一季打的：大勢照常是數值變化
    assert "你出手 0 回合" in entry.lines
    open_characters().save(back.state)

    game.world.next_season(content, now=end + 20)  # 補過的那一場，到了下一季不會再補一次
    again = Game(content, open_characters().load("乙"), rng=random.Random(4), world=game.world)
    again.sync(end + 30)
    assert _showdown_entries(again) == [] and again.state.battles == []


def test_a_fighter_first_back_next_season_gets_last_seasons_showdown_marked_with_its_season(content, game):
    end = _showdown_ends_the_season(content, game)
    game.world.next_season(content, now=end + 20)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(end + 30)
    entry = back.state.journal[0]
    assert (entry.title, entry.tag) == ("第 1 季・測試決戰・官軍大勝", "你站在黃巾")
    assert entry.changes == []  # 上一季的大勢不放進數值變化：那看起來像剛發生在你身上
    assert "（第 1 季）寇亂 +50" in entry.lines
    report = back.state.battles[0]
    assert report.kind == "showdown" and report.location.startswith("第 1 季・") and report.changes == []
    (_, battle), = game.world.ended_battles()
    assert battle.end_time is not None
    assert entry.time == report.time == battle.end_time  # 收場時（第 1 季）的時間，不是補送這一刻
    assert battle.end_time != back.state.world.time  # 這一季的時鐘
    back.sync(end + 40)
    assert len(_showdown_entries(back)) == 1 and len(back.state.battles) == 1


# ── 季終時沒打完的決戰：不算勝負，但參戰者補一則江湖紀錄（FB-035）──────────────

SHELVED_LINE = "季終了，這場決戰沒打完就各自收兵，不算勝負。"


def _showdown_under_way(content, game):
    """一幕三回合的決戰打到第 2 回合還在等人：沈浪（官軍、在線）與乙（黃巾，出完第 1 回合就下線，角色只在資料庫裡）
    各出手 1 回合；散人丙在一旁觀戰。回傳（丙, 現在的時間）。"""
    definition = _three_round_showdown(content)
    game.state.player.faction = "guan"
    away = _fighter(content, game, "乙", "huang")
    watcher = Game.new(content, "丙", rng=random.Random(2), world=game.world)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0), at(away, 0.0):
        game.choose("battle:join:guan")
        away.choose("battle:join:huang")
    start = definition.muster_seconds + 1
    with at(game, start), at(away, start):
        game.choose("battle:act:safe")
        away.choose("battle:act:safe")  # 兩人都出手了：第 1 回合結算
    open_characters().save(away.state)
    battle = game.world.get_battle()
    assert battle.phase == "active" and battle.round_number == 1
    return watcher, start


def _assert_got_the_shelved_note(fighter, side, label=""):
    """補到的是一則只有江湖紀錄的交代：沒有戰報、沒有「剛剛」的戰鬥卡片、沒有數值變化；再同步也不重複。"""
    entry = fighter.state.journal[0]
    assert (entry.title, entry.tag) == (f"{label}測試決戰・未分勝負", f"你站在{side}")
    assert entry.lines == [SHELVED_LINE, "你出手 1 回合"]
    assert entry.changes == [] and entry.battle_id is None
    assert fighter.state.battles == [] and fighter.state.battle_card is None and not fighter.shows_battle_card()
    fighter.sync(entry.time + 1000.0)
    assert [e.title for e in fighter.state.journal].count(entry.title) == 1


def test_admin_ending_the_season_tells_each_fighter_the_battle_was_shelved(content, game):
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    watcher, now = _showdown_under_way(content, game)
    season = game.world.get_season()
    trends, flags, chronicle = dict(season.trends), set(season.flags), len(season.chronicle)

    admin.admin_end_season(now=now)

    assert game.world.get_battle() is None
    after = game.world.get_season()
    assert dict(after.trends) == trends and set(after.flags) == flags  # 不套任何結果
    assert not any("未分勝負" in entry.text or "官軍大勝" in entry.text for entry in after.chronicle[chronicle:])
    (_, shelved), = game.world.ended_battles()  # 標成收場、才補送得到；但記著它沒打完
    assert shelved.unfinished and shelved.outcome_title == "未分勝負" and shelved.outcome_text is None
    assert shelved.end_time == after.time
    assert not any("未分勝負" in e.title for e in admin.state.journal)  # 管理者沒參戰：什麼都沒有

    online = game
    offline = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    assert not any("未分勝負" in e.title for e in offline.state.journal)  # 讀回來還沒同步：還沒補
    online.sync(now + 10)
    offline.sync(now + 10)
    _assert_got_the_shelved_note(online, "官軍")
    _assert_got_the_shelved_note(offline, "黃巾")
    watcher.sync(now + 10)  # 觀戰的人照舊什麼都沒有
    assert not any("未分勝負" in e.title for e in watcher.state.journal) and watcher.state.battles == []


def test_a_season_that_ends_on_its_own_tells_each_fighter_too(content, game):
    watcher, now = _showdown_under_way(content, game)
    with at(game, now):
        game.advance(2 * DAY)  # 快轉到季末，季自己收了
    assert game.state.world.ended and game.world.get_battle() is not None  # 還沒有人刷新畫面：決戰還掛著
    trends = dict(game.world.get_season().trends)

    with at(game, now + 1):
        assert ids(game) == ["season:resting"]  # 畫面刷新那一下把沒打完的收起來
    assert game.world.get_battle() is None
    assert dict(game.world.get_season().trends) == trends  # 官軍大勝的 -20 沒有套
    (_, shelved), = game.world.ended_battles()
    assert shelved.unfinished and shelved.outcome_title == "未分勝負"

    offline = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    game.sync(now + 10)
    offline.sync(now + 10)
    _assert_got_the_shelved_note(game, "官軍")
    _assert_got_the_shelved_note(offline, "黃巾")
    watcher.sync(now + 10)
    assert not any("未分勝負" in e.title for e in watcher.state.journal)


def test_a_fighter_first_back_next_season_gets_the_shelved_note_marked_with_its_season(content, game):
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    _, now = _showdown_under_way(content, game)
    admin.admin_end_season(now=now)
    admin.admin_next_season(now=now + 5)
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(now + 10)
    assert back.state.player.season_number == 2
    _assert_got_the_shelved_note(back, "黃巾", label="第 1 季・")
    (_, shelved), = game.world.ended_battles()
    assert back.state.journal[0].time == shelved.end_time  # 收季那一刻（第 1 季）的時間，不是補送這一刻


def test_opening_the_next_season_shelves_a_battle_nobody_ticked_after_the_natural_end(content, game):
    """季自然結束、到管理者開下一季之前沒有人同步過（沒人走到 _battle_status 收掉它）：開下一季先把它收起來，
    參戰者照樣補得到「不算勝負」那一則，不會被換季靜靜清掉（FB-035）。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(5), world=game.world)
    _, now = _showdown_under_way(content, game)
    game.world.mutate_season(lambda season: (setattr(season, "ended", True), setattr(season, "ending_title", "天下太平")))
    ended_at = game.world.get_season().time

    admin.admin_next_season(now=now + 5)

    assert game.world.get_season_number() == 2
    (_, shelved), = game.world.ended_battles()
    assert shelved.unfinished and shelved.end_time == ended_at
    back = Game(content, open_characters().load("乙"), rng=random.Random(3), world=game.world)
    back.sync(now + 10)
    _assert_got_the_shelved_note(back, "黃巾", label="第 1 季・")


def test_a_shelved_battle_that_is_still_linked_is_not_taken_for_a_normal_finish(content, game):
    """收季時「標成 ended＋unfinished」與「清掉」是兩步（同一筆交易裡）。就算有人在兩步之間看到它還掛著，也不能當成
    剛打完去套結果：_battle_status 看到的是本來就 ended 的，_apply_battle_outcome 認得 unfinished、直接不動。"""
    definition = _three_round_showdown(content, trend_delta={"kou": -20})
    game.state.player.faction = "guan"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.world.mutate_battle(lambda b: (
        setattr(b, "phase", "ended"), setattr(b, "unfinished", True), setattr(b, "outcome_title", "未分勝負"),
    ))
    season = game.world.get_season()
    trends, chronicle = dict(season.trends), len(season.chronicle)
    with at(game, 1.0):
        assert game._battle_status() is None
    game._apply_battle_outcome(game.world.get_battle())
    after = game.world.get_season()
    assert dict(after.trends) == trends and len(after.chronicle) == chronicle
    assert dict(game.state.world.trends) == trends


# ── 決戰要人在那個大區才打得到（地圖擴充設計第六節）──────────────


def _south_cave(content, game):
    """寶洞搬進南區（夾具的三個地點本來都在北區）並打開。"""
    content.locations["cave"].y = 170
    game.state.world.flags.add("cave_open")


def test_you_can_join_a_battle_only_in_its_region(content, game):
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert "act:explore" in ids(game)  # 人在北區：照常遊玩
        assert "這場決戰在測試南區" in game.scene_text()
        assert game._battle_choose("join:guan") == ["（這場決戰在測試南區，人要到了那裡、不在路上才能加入。）"]
        game.state.player.location = "cave"
        assert ids(game)[:2] == ["battle:join:guan", "battle:join:huang"]  # 集結中：加入的按鈕在平常的選單前面


def test_nobody_on_the_road_can_join(content, game):
    definition = _install_battle_def(content)  # 不限地點
    game.choose("move:lake")  # 先出發：在路上的人不算到了戰場
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert not any(i.startswith("battle:") for i in ids(game))
        assert game._battle_choose("join:guan") == ["（你還在路上，到了才能加入戰局。）"]


def test_arriving_mid_battle_lets_you_join_late(content, game):
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert "act:explore" in ids(game)
        game.travel("cave", "dash")
        assert ids(game) == ["battle:join_late"]


def test_a_fighter_who_leaves_the_region_sits_the_rounds_out_until_back(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    definition.rounds_per_act = 3  # 不要一回合就分出勝負
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        game.travel("cave", "dash")  # 離開北區
        battle = game.world.get_battle()
        assert battle.participants["沈浪"].away
        assert "act:explore" in ids(game) and "你離開了測試北區" in game.scene_text()
        assert game.battle_free_text_prompt() is None
        game.world.mutate_battle(lambda b: battle_instance.submit_action(b, "乙玩家", "safe"))
        assert battle_instance.round_is_complete(game.world.get_battle())  # 不等離開的人
        game.travel("lake", "dash")  # 回到北區
        assert not game.world.get_battle().participants["沈浪"].away
        assert any(i.startswith("battle:act:") for i in ids(game))


def test_walking_inside_the_region_keeps_a_fighter_present(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.travel("lake", "walk")  # 小鎮、湖邊都在北區：在路上也還在戰場
    assert game.state.player.journey is not None
    assert not game.world.get_battle().participants["沈浪"].away
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert not game.world.get_battle().participants["沈浪"].away


def test_a_fighter_walking_inside_the_region_can_still_change_sides_during_the_muster(content, game):
    """已經報名的人在區內站與站之間走動，集結期還看得到改選陣營的按鈕；按下去是改選、不是「加入」，
    不能被「人要到了那裡、不在路上才能加入」擋下。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.travel("lake", "walk")
        assert game.state.player.journey is not None
        assert "battle:join:huang" in ids(game)
        assert game.choose("battle:join:huang") == ["你加入了這場戰局。"]
    participant = game.world.get_battle().participants["沈浪"]
    assert participant.faction == "huang" and not participant.away


def test_a_fighter_walking_out_of_the_region_is_away_from_the_start_of_the_trip(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.travel("cave", "walk")  # 小鎮—湖邊在北區，終點寶洞在南區：這一趟還沒走到的站有一個在區外
    assert game.world.get_battle().participants["沈浪"].away


def test_a_battle_with_no_region_cannot_be_left(content, game):
    definition = _install_battle_def(content)  # 不限地點
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    game.travel("cave", "walk")
    assert game.state.player.journey is not None
    assert not game.world.get_battle().participants["沈浪"].away  # 沒有大區就沒有「離開」


def test_joining_a_battle_stands_you_up(content, game):
    definition = _install_battle_def(content)
    game.choose("act:rest")
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    assert game.state.player.resting_since is None
    assert "沈浪" in game.world.get_battle().participants


def test_a_sitter_can_still_stand_up_while_the_muster_menu_is_showing(content, game):
    """打坐中碰上集結：加入的按鈕旁邊一定還有起身（集結時平常的選單接在後面，打坐中就是起身）——
    不然人坐著出不去，只能硬加入戰局。規則是隨時可以起身。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    game.choose("act:rest")
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert "act:stand" in ids(game)
        assert next(o for o in game.options() if o.id == "act:stand").label == "起身"
        game.choose("act:stand")
        assert game.state.player.resting_since is None
        assert ids(game)[:2] == ["battle:join:guan", "battle:join:huang"]  # 起身不等於加入，加入的按鈕還在
        assert "沈浪" not in game.world.get_battle().participants


def test_a_sitter_can_stand_up_while_the_late_join_menu_is_showing(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    game.choose("act:rest")
    game.world.start_battle(definition, now=0.0)
    with at(game, definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert ids(game) == ["battle:join_late", "act:stand"]
        game.choose("act:stand")
        assert game.state.player.resting_since is None
        assert ids(game) == ["battle:join_late"]


def test_a_standing_player_gets_no_stand_option_on_the_battle_menu(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert "act:stand" not in ids(game)


def test_rally_region_names_a_battle_you_should_head_for(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.region = "south"
    _south_cave(content, game)
    game.state.player.faction = "guan"
    assert game.rally_region() is None  # 沒有決戰
    game.world.start_battle(definition, now=time.time())
    assert game.rally_region() == "south"
    game.state.player.faction = "haoqiang"
    assert game.rally_region() is None  # 打不了這場
    game.state.player.faction = "guan"
    game.state.player.location = "cave"
    assert game.rally_region() is None  # 已經在南區
    definition.region = None
    game.state.player.location = "town"
    assert game.rally_region() is None  # 不限地點的決戰不用趕


def test_halting_inside_the_region_brings_an_away_fighter_back(content, game):
    """出發時這一趟有站在區外就記成離開；喊停之後最後一站落在區內，就不該再被當成離開、坐著等整段路。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        game.travel("cave", "walk")  # 小鎮出發：湖邊在北區、終點寶洞在南區
        assert game.world.get_battle().participants["沈浪"].away
        assert "act:halt" in ids(game)
        game.choose("act:halt")  # 下一站湖邊還在北區
        assert game.state.player.journey.stop_at == 0
        assert not game.world.get_battle().participants["沈浪"].away
        assert "你離開了" not in game.scene_text()


def test_a_fallen_fighter_who_left_the_region_is_not_promised_a_return_to_action(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        game.travel("cave", "dash")  # 離開北區
        assert "人回到測試北區就能再出手" in game.scene_text()
        game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
        scene = game.scene_text()
        assert "你已經倒下" in scene and "再出手" not in scene


def test_rally_region_sends_a_fighter_who_left_the_region_back_unless_they_have_fallen(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        assert game.rally_region() is None  # 人在戰場上
        game.travel("cave", "dash")  # 離開北區
        assert game.rally_region() == "north"  # 參戰了卻離開大區：該趕回去
        game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
        assert game.rally_region() is None  # 已經倒下，趕回去也沒得打


# ── 自訂行動輸入框（設計討論：魯莽該是玩家自己想出來的招，不是固定選單）────────


def _install_battle_def_with_free_text(content):
    from tianxia.models import (
        BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    )

    definition = BattleDef(
        id="t2", name="測試決戰（自訂行動）",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[
                    BattleOption(text="穩紮穩打", tag="safe", faction="guan"),
                    BattleOption(text="放手一搏（20字內）", tag="reckless", faction="guan", free_text=True),
                    BattleOption(text="死守營寨", tag="huang_safe", faction="huang"),
                ],
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "reckless": BattleActionEffect(trend_delta=10, neili_damage=50),
            "huang_safe": BattleActionEffect(trend_delta=-1, neili_damage=5),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
        rounds_per_act=1,  # 一幕一回合，同 _install_battle_def
    )
    content.battles[definition.id] = definition
    return definition


def _join_and_open(content, game, definition):
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
    return after_muster


def test_free_text_option_is_excluded_from_the_button_list(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        assert [o.label for o in game.options()] == ["穩紮穩打"]  # 自訂行動不是按鈕


def test_battle_free_text_prompt_shows_when_available(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        assert game.battle_free_text_prompt() == "放手一搏（20字內）"


def test_battle_free_text_prompt_is_none_outside_battle(content, game):
    assert game.battle_free_text_prompt() is None


def test_battle_free_text_prompt_is_none_after_submitting(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        game.submit_battle_custom_action("直取波才首級")
        assert game.battle_free_text_prompt() is None


def test_submit_battle_custom_action_truncates_to_20_characters(content, game):
    """這場測試戰鬥只有一幕、保底結果沒有數值門檻，機器人補位後這回合會立刻結算（round
    也會跟著重置），所以改檢查 narrative_log（結算後仍然保留）而不是 round.custom_texts
    （結算後已經清空）。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    long_text = "一二三四五六七八九十" * 3  # 30 字
    with at(game, after_muster):
        game.submit_battle_custom_action(long_text)
    battle = game.world.get_battle()
    assert any(long_text[:20] in line for line in battle.narrative_log)
    assert not any(long_text in line for line in battle.narrative_log)  # 完整 30 字版本不該出現


def test_submit_battle_custom_action_rejects_empty_input(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        msgs = game.submit_battle_custom_action("   ")
    assert msgs == ["（請先輸入你想做的事。）"]
    assert "沈浪" not in game.world.get_battle().round.pending_actions


def test_submit_battle_custom_action_outside_battle_is_a_no_op(content, game):
    assert game.submit_battle_custom_action("test") == ["（此刻無法這麼做。）"]


def test_submit_battle_custom_action_works_even_as_the_very_first_call_after_muster_overruns(content, game):
    """自訂行動輸入框不是透過 choose() 進來的，沒有 choose() 開頭那次 self.options()
    順便推進過一次的保護——真的抓到過的 bug：如果這是集結逾時後的第一個請求，
    submit_battle_custom_action() 自己沒有先追趕，battle_instance.submit_action()
    內部看到 battle.phase 還是 "muster" 會悄悄把這次送出的行動吃掉，玩家完全不知道
    自己其實白打了一輪字。"""
    definition = _install_battle_def_with_free_text(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        # 注意：這裡故意不先呼叫 game.options()/game._battle_status() 暖身，
        # 直接送出自訂行動，模擬「這是逾時後第一個進來的請求」。
        msgs = game.submit_battle_custom_action("直取波才首級")
    assert msgs != ["（此刻無法這麼做。）"]
    battle = game.world.get_battle()
    assert any("直取波才首級" in line for line in battle.narrative_log)


def test_custom_action_mechanics_match_the_fixed_tag_regardless_of_text(content, game):
    """這個 fixture 沒有設定 free_text_gamble，所以就算玩家打的字會先被送去評成功率，
    resolve_round 還是會退回 action_tags 查表那條路（見 battle_instance.py 的對應測試），
    機制效果不會因為文字內容不同而有不同結果——有設定 free_text_gamble 的戰鬥則相反，
    見 test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()  # 玩家真實的氣血上限（join 時是這樣算的，不是隨便假設的數字）
    assert battle.participants["沈浪"].neili == cap - 50  # reckless 的 50 點損耗


def _install_battle_def_with_gamble(content):
    from tianxia.models import FreeTextGamble

    definition = _install_battle_def_with_free_text(content)
    definition.id = "t3"
    content.battles[definition.id] = definition
    definition.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_damage=10,
        failure_trend_per_risk=0.1, failure_neili_base=20, failure_neili_per_risk=3.0,
    )
    return definition


def test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble(content, game):
    """跟上一個測試同一套劇本，差別只在這個 definition 有設定 free_text_gamble——這次
    送出的自訂行動會先呼叫 LLM（這裡用 mock）評成功率，評出來的結果真的拿去擲骰、
    算出不是固定 50 點的傷害，證明整條鏈路（engine.submit_battle_custom_action →
    battle_instance.assess_action_success_rate → resolve_round 的賭局分支）真的接起來了。"""
    definition = _install_battle_def_with_gamble(content)
    after_muster = _join_and_open(content, game, definition)
    with at(game, after_muster), \
         mock.patch.object(game.client, "chat_structured", return_value=battle_instance.SuccessRateJudgment(success_rate=20)):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()
    # success_rate=20、risk=80：成功時只扣固定的 10（傷害很小，賭贏代價低），失敗時扣
    # 20+80*3=260——用的是 game.rng（真的隨機，不是 FixedRandom），究竟成功還是失敗
    # 不好預測，但傷害一定精確落在這兩個數字其中之一，不會是固定查表的 50，證明真的
    # 走了賭局公式（不是退回 action_tags 查表那條路）。
    damage = cap - battle.participants["沈浪"].neili
    assert damage in (10, 260)


def test_a_battle_threshold_crossed_in_the_background_starts_the_battle(content, game):
    """伺服器假人設計第八節第 1 項：沒人在行動時，大勢人物在背景把大勢推過開戰門檻，也要開戰。"""
    from tianxia.world import advance_season

    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id  # kou50
    game.world.mutate_season(lambda season: season.trends.__setitem__("kou", 60))
    msgs = advance_season(game.world, content, 3600, random.Random(0), now=0.0)
    battle = game.world.get_battle()
    assert battle is not None and battle.battle_id == definition.id and battle.phase == "muster"
    assert any("集結號角" in m for m in msgs)
    assert game.world.get_season().pending_battle is None


def test_fast_forwarding_across_a_battle_threshold_starts_the_battle(content, game):
    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id
    game.state.world.trends["kou"] = 60
    msgs = game.advance(3600)
    assert game.world.get_battle() is not None
    assert any("集結號角" in m for m in msgs)
    assert game.state.world.pending_battle is None
    assert game.world.get_season().pending_battle is None


def test_each_dialogue_turn_costs_stamina(content, game):
    """伺服器假人設計第八節第 4 項：跟大勢人物對話每一輪扣體力，不再是免費的。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        before = game.state.player.stamina
        game.choose("talk:0")
    assert game.state.player.stamina == before - content.config.talk_stamina


def test_dialogue_turns_are_disabled_without_stamina_but_leaving_is_not(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    game.state.player.stamina = content.config.talk_stamina - 1
    options = {o.id: o for o in game.options()}
    assert not options["talk:0"].enabled and not options["talk:1"].enabled
    assert options["talk:leave"].enabled


def test_joining_a_faction_asks_for_confirmation_and_shows_the_headcount(content, game):
    """伺服器假人設計第八節第 3 項：投靠要確認一次，確認畫面寫明不能改投與三方目前各有幾人。"""
    _install_factions(content)
    game.world.record_faction("別人", "huang")
    game.choose("faction:guan")
    assert game.state.player.faction is None
    assert ids(game) == ["faction:confirm", "faction:cancel"]
    scene = game.scene_text()
    assert "這一季不能改投" in scene
    assert "目前官軍 0 人、黃巾 1 人、地方豪強 0 人" in scene
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert game.world.faction_counts() == {"guan": 1, "huang": 1}


def test_the_join_question_is_on_the_scene_only(content, game):
    """FB-046：「投靠後這一季不能改投……確定投靠官軍？」場景上寫著，江湖紀錄那一則（「剛剛」）不再寫一次。"""
    _install_factions(content)
    game.choose("faction:guan")
    entry = game.state.journal[0]
    assert entry.title == "考慮投靠官軍"
    assert "這一季不能改投" in game.scene_text()
    assert "這一季不能改投" not in game.latest_entry_html()
    assert not any("不能改投" in line for line in [entry.tag, *entry.lines])


def test_thinking_again_leaves_you_a_free_agent(content, game):
    _install_factions(content)
    game.choose("faction:guan")
    game.choose("faction:cancel")
    assert game.state.player.faction is None and game.state.player.pending_faction is None
    assert "faction:guan" in ids(game)
    assert game.world.faction_counts() == {}


def test_a_player_who_joined_before_the_roll_existed_is_counted_on_the_next_sync(content, game):
    _install_factions(content)
    game.state.player.faction = "huang"
    game.sync(time.time())
    assert game.world.faction_counts() == {"huang": 1}


def test_a_new_season_keeps_a_server_bots_profile(content, game):
    profile = BotProfile(personality="積極", seed=7, faction="guan", season_number=1)
    game.state.player.bot = profile
    game.world.mutate_season(lambda season: setattr(season, "ended", True))
    assert game.world.next_season(content, now=time.time())
    game.sync(time.time())
    assert game.state.player.season_number == 2
    assert game.state.player.bot == profile


def test_a_server_bot_looks_exactly_like_a_player_on_screen(content, game):
    """伺服器假人設計第五節：「是假人」只記在存檔裡，畫面上任何地方都看不出來。"""
    before = (game.status_text(), game.scene_text(), game.quest_text(), game.journal_html(1, 5))
    game.state.player.bot = BotProfile(personality="積極", seed=7, faction="guan", season_number=1)
    assert (game.status_text(), game.scene_text(), game.quest_text(), game.journal_html(1, 5)) == before


# ── 管理者觸發（伺服器假人計畫 Task 8）────────────────────────


def _admin(content, game):
    content.config.admins = [game.state.player.name]
    return game


def test_only_an_admin_can_trigger_things(content, game):
    definition = _install_battle_def(content)
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（只有管理者能開戰。）"]
    assert game.admin_fire("kou50") == ["（只有管理者能觸發大事。）"]
    assert game.admin_push_trend("kou", 10) == ["（只有管理者能推動大勢。）"]
    assert game.world.get_battle() is None
    assert "kou50" not in game.world.get_season().fired_thresholds
    assert game.world.get_season().trends["kou"] == 30


def test_an_admin_starts_a_battle_right_away(content, game):
    definition = _install_battle_def(content)
    _admin(content, game)
    msgs = game.admin_start_battle(definition.id, now=time.time())
    assert any("集結號角" in m for m in msgs)
    assert game.world.get_battle().phase == "muster"
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（已經有一場戰鬥在進行。）"]
    assert game.admin_start_battle("no_such_battle", now=time.time()) == ["（沒有這場戰鬥。）"]


def test_an_admin_fires_a_great_event_once(content, game):
    _admin(content, game)
    msgs = game.admin_fire("kou50")
    assert any("水寇封江" in m for m in msgs)
    season = game.world.get_season()
    assert "kou50" in season.fired_thresholds and "blocked" in season.flags
    assert game.admin_fire("kou50") == ["（這件大事已經發生過了。）"]
    assert game.admin_fire("no_such_event") == ["（沒有這件大事。）"]


def test_firing_a_battle_threshold_by_hand_starts_its_battle(content, game):
    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id
    _admin(content, game)
    game.admin_fire("kou50")
    assert game.world.get_battle() is not None


def test_an_admin_push_crosses_thresholds_like_any_push(content, game):
    _admin(content, game)
    game.admin_push_trend("kou", 25)  # 30 → 55，跨過 kou50
    season = game.world.get_season()
    assert season.trends["kou"] == 55
    assert "kou50" in season.fired_thresholds
    assert game.admin_push_trend("no_such_trend", 5) == ["（沒有這條大勢線。）"]


def test_the_admin_menus_leave_out_what_season_one_turns_off(content, game):
    """計畫 T8：開關打開、這一季蓋了「開」的章時，第一季不觸發的決戰與門檻不列在管理者的選單上、也觸發不了；
    開關關著照舊。"""
    from tianxia.models import SeasonOneOff

    definition = _install_battle_def(content)
    _admin(content, game)
    content.scenario.season_one_off = SeasonOneOff(thresholds=["kou50"], battles=[definition.id])
    assert [b.id for b in game.admin_battles()] == [definition.id]  # 開關關著：照舊
    assert [x.id for x in game.admin_fires()] == ["kou50", "kou80", "bao100", "grab"]
    content.config.season_one = True
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))
    game.sync(time.time())
    assert game.admin_battles() == [] and [x.id for x in game.admin_fires()] == ["kou80", "bao100", "grab"]
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（沒有這場戰鬥。）"]
    assert game.admin_fire("kou50") == ["（沒有這件大事。）"]
    assert game.world.get_battle() is None and "kou50" not in game.world.get_season().fired_thresholds


def test_triggers_wait_for_the_season_to_run(content, game):
    _admin(content, game)
    game.world.mutate_season(lambda season: setattr(season, "ended", True))
    game.sync(time.time())
    assert game.admin_fire("kou50") == ["（賽季沒有在進行，無法觸發。）"]
    assert game.admin_push_trend("kou", 5) == ["（賽季沒有在進行，無法觸發。）"]
    assert game.admin_start_battle("t1", now=time.time()) == ["（賽季沒有在進行，無法觸發。）"]


# ── 煉製素材的掉落（無限煉製第一刀）──────────────────────────


def test_train_win_drops_a_material_into_the_bag_and_the_report(game):
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)  # 水寇小隊難度 5：預設掉落表 50% 掉一個一階素材
    msgs = game.choose("act:train")
    record = game.state.battles[0]
    assert record.materials == ["精鐵砂 ×1"]
    assert game.state.player.materials == {"gang_1": 1}
    assert "獲得 精鐵砂 ×1" in msgs


def test_a_hard_fought_loss_drops_nothing(game):
    game.content.locations["lake"].enemies = ["boss"]  # 打不贏的翻江龍
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    assert game.state.battles[0].tier == "落敗"
    assert game.state.player.materials == {}


def test_exploring_a_quiet_place_can_still_turn_up_an_insight(game):
    game.state.player.location = "cave"  # fixture 的山洞沒有任何事件也沒有敵人
    game.content.locations["cave"].materials = ["gang_3"]
    game.rng = FixedRandom(0.0)
    msgs = game.choose("act:explore")  # 訊息串後面還會接新手引導的進度
    assert "你在寶洞靜下心來，看了好一陣。" in msgs and "你悟得了「山」的意境（屬慢）！" in msgs
    assert game.state.player.insights == ["shan"] and game.state.player.materials == {}  # 探索不再撿素材


def test_exploring_and_finding_nothing_still_says_so(game):
    """探索三選一：三支都做不了才是一無所獲——山洞沒有敵人、沒有事件，再把悟意境那一支的比例設成 0。"""
    game.state.player.location = "cave"
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 0, "wild": 35, "event": 25})]
    game.rng = FixedRandom(0.99)
    msgs = game.choose("act:explore")
    assert msgs[0] == "你四處走走，一無所獲。"
    assert not any("獲得" in m for m in msgs)
    assert game.state.player.materials == {}


# ── 遊歷（第二層：遭遇戰的唯一管道）──────────────────────────


def test_train_is_offered_only_where_there_are_enemies(game):
    ids = [o.id for o in game.options()]
    assert "act:train" not in ids  # 鎮上沒有敵人
    walk_to(game, "lake")  # 湖邊有水寇小隊
    option = next(o for o in game.options() if o.id == "act:train")
    assert "遊歷" in option.label and "水寇小隊" in option.label


def test_training_always_fights_even_though_an_event_would_have_fired(game):
    """探索永遠會撞到事件（pick_event 只在完全沒有候選時才回 None），所以掛在探索後面的
    遭遇戰分支一次都不會執行——遊歷就是為了這件事存在的。"""
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)  # 高到不會觸發戰後事件
    msgs = game.choose("act:train")
    assert game.state.battles and game.state.battles[0].opponent == "水寇小隊"
    assert game.state.pending_event is None  # 沒有被事件搶走
    assert any("⚔" in m for m in msgs)


def test_training_costs_the_configured_stamina(game):
    walk_to(game, "lake")
    before = game.state.player.stamina
    game.rng = FixedRandom(0.99)
    game.choose("act:train")
    assert before - game.state.player.stamina == game.content.config.action_cost["train"]


def test_a_post_battle_event_can_follow_the_fight(game):
    """「拆招頓悟」「錦衣少年」的文字本來就是戰後餘韻，現在掛回 actions: ["train"]。"""
    game.content.events["chain_a"].actions = ["train"]  # fixture 裡唯一掛在 train 上的事件
    game.content.config.train_event_chance = 1.0
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)
    game.choose("act:train")
    assert game.state.battles  # 先打了一場
    assert game.state.pending_event == "chain_a"  # 再接上戰後的事件


# ── 回合演出（武學與成長設計 8.2、計畫三 Task 1）──────────────────────


def _told_and_shown(record) -> tuple[int, int]:
    """戰報「獲得與損失」寫的那一筆「氣血 -N」（沒有就是 0），以及回合裡每一句「你氣血 -N」加起來的數。"""
    told = re.search(r"氣血 -(\d+)", " ".join(record.changes))
    shown = sum(int(n) for line in record.rounds for n in re.findall(r"你氣血 -(\d+)", line))
    return (int(told.group(1)) if told else 0), shown


def _forced(tier: str):
    """這一場的勝負寫死（team.fight 不擲骰）；回合怎麼演只看結果。"""
    from tianxia import team
    from tianxia.encounter import EncounterResult

    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5))


def _player_hp(game) -> float:
    from tianxia import team
    from tianxia.state import PLAYER

    return team.member_neili(game.content, game.state.player.member, team.con_of(game.state, PLAYER))[0]


def test_a_training_fight_shows_rounds_that_match_the_hp_lost(game):
    walk_to(game, "lake")
    game.state.player.member.wugong_id = "basic_fist"
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.rounds and record.rounds[0].startswith("第1回合")
    told = re.search(r"氣血 -(\d+)", " ".join(record.changes))  # 戰報「獲得與損失」寫的那一筆
    shown = sum(int(n) for line in record.rounds for n in re.findall(r"你氣血 -(\d+)", line))
    assert shown == (int(told.group(1)) if told else 0)
    assert "**過程**" in game.battle_card()


@pytest.mark.parametrize("neili", [None, 360.0])
def test_the_rounds_add_up_to_what_a_sturdy_player_really_lost(game, neili):
    """根骨 10 的人氣血上限是 368（吃根骨），比基準的 320 高：回合裡的「你氣血 -N」加起來要等於戰報那一筆、也等於真的
    扣掉的（G4：con_of 認 key 不認物件，拿 Member 去問會當成基準 5，滿血落敗時只寫出 62、戰報卻是 110）。"""
    walk_to(game, "lake")
    p = game.state.player
    p.stats["con"], p.member.neili = 10, neili
    before = _player_hp(game)
    with _forced("落敗"):
        game.choose("act:train")
    record = game.state.battles[0]
    told, shown = _told_and_shown(record)
    assert record.tier == "落敗" and told == round(before - _player_hp(game)) == 110
    assert shown == told and len(record.rounds) in (3, 4)


def test_the_rounds_add_up_to_the_halved_toll_of_a_wild_fight(game):
    """探索撞上的野怪只扣一半的氣血（wild）：回合照樣加得起來。"""
    game.state.player.stats["con"] = 10
    before = _player_hp(game)
    with _forced("落敗"):
        game._squad_encounter("thug", wild=True)
    record = game.state.battles[0]
    told, shown = _told_and_shown(record)
    assert record.kind == "wild" and told == round(before - _player_hp(game)) == 55 and shown == told


def test_the_rounds_add_up_to_the_toll_after_a_level_up(game):
    """打贏升級、氣血上限跟著變高（滿血的人「滿」也跟著變高）：回合的氣血要緊貼著扣氣血的前後量，
    不是開打前——開打前量的話，升級多出來的上限會把這一場扣的蓋掉，回合裡一滴血都沒掉。"""
    walk_to(game, "lake")
    p = game.state.player
    p.stats["con"], p.member.exp = 10, 90  # 夾具的 level_exp 是 100：水寇小隊給 20 經驗，打贏升到第 2 級
    with _forced("大勝"):
        game.choose("act:train")
    record = game.state.battles[0]
    told, shown = _told_and_shown(record)
    assert p.member.level == 2 and told > 0 and shown == told


def test_an_event_battle_takes_no_blood_so_their_blows_carry_no_numbers(game):
    """劇情戰不扣氣血（G5）：對手的出手不寫「你氣血 -N」，也不寫「被你閃開了」——落敗的仗寫「被你閃開了」，
    讀起來是對方從頭到尾沒碰到你、你卻輸了。沒學武學的人上場，也不會寫出「以【None】」。"""
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")  # 應戰翻江龍：必敗
    record = game.state.battles[0]
    assert record.tier == "落敗" and len(record.rounds) in (3, 4)
    for line in record.rounds:
        assert "你氣血" not in line and "被你閃開了" not in line
        assert "None" not in line and "【" not in line and "翻江龍" in line and "沈浪" in line


def test_an_event_battle_is_played_with_the_fighters_from_before_its_rewards(game):
    """劇情戰的回合照開打時的陣容與身法演（計畫三 Task 1 審查修正）：打贏的效果（真實內容的 wolves 打贏身法 +1）
    不能回頭改寫這一場——身法 5 比水寇小隊的 5.25 慢，是對手先出手；效果加了身法也一樣。學到的武學同理：
    本人空著手上陣、打贏才學會（配上身）的追風步，不會出現在這一場的回合裡，出手的只有帶著長拳的韓鐵。"""
    duel = game.content.events["duel"].choices[0]
    duel.combat = "thug"  # 換成打得贏的水寇小隊（難度 5：身法 5＋5÷20＝5.25）
    duel.effect.stats = {"agi": 3}
    duel.effect.learn_skills = ["step"]
    game.state.player.team = ["mate"]
    game.world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.rng = FixedRandom(1.0)  # 最佳運氣：穩穩打贏
    game.choose("choice:0")
    record = game.state.battles[0]
    p = game.state.player
    assert record.tier in ("大勝", "險勝") and (p.stats["agi"], p.member.wugong_id) == (8, "step")  # 效果真的生效了
    assert record.rounds and all(line.startswith(f"第{i}回合　水寇小隊") for i, line in enumerate(record.rounds, 1))
    assert all("韓鐵以【長拳】" in line and "追風步" not in line and "沈浪" not in line for line in record.rounds)


def test_the_rounds_do_not_touch_the_rules_rng_and_read_the_same_every_time(game):
    """回合與句子用自己的亂數（名號＋戰報流水號當種子，G3），不動 Game.rng：演出是畫面上的事，不能讓同一個行動裡
    接下來的擲骰（戰後事件、掉落、假人）跟著位移；同一筆戰報演幾次都一樣。"""
    walk_to(game, "lake")
    state = game.rng.getstate()
    with _forced("落敗"):
        game._squad_encounter("thug")
    assert game.rng.getstate() == state
    record = game.state.battles[0]
    told, _ = _told_and_shown(record)
    shown = list(record.rounds)
    game._play_rounds(record, game.content.squads["thug"], "落敗", told)
    assert shown and record.rounds == shown


# ── 大場面請模型判讀（武學與成長設計 8.3、計畫三 Task 2）──────────────────────

JUDGMENT = fight_llm.Judgment(advantage=15, winning="佔上風的過程。", losing="落下風的過程。")
ACCOUNTS = (JUDGMENT.winning, JUDGMENT.losing)


def _boss_at_the_lake(game):
    game.content.locations["lake"].enemies = ["boss"]
    walk_to(game, "lake")
    game.state.player.member.wugong_id = "basic_fist"


def _judged(request, judgment=JUDGMENT):
    return fight_llm.PreparedFight(request=request, judgment=judgment)


def test_an_ordinary_fight_needs_no_judgment(game):
    walk_to(game, "lake")
    assert game.fight_request("act:train") is None
    assert next(o for o in game.options() if o.id == "act:train").wait == ""


def test_a_big_fight_is_judged_and_tells_the_page_to_wait(game):
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    assert request.squad_id == "boss" and request.ours and "翻江龍" in request.theirs
    assert request.ours[0].startswith("沈浪：武學【") and request.battle_seq == game.state.battle_seq
    assert next(o for o in game.options() if o.id == "act:train").wait == "兩人對峙……"


def test_the_judgment_writes_the_matching_account(game):
    """僵持也算落下風（計畫三 G15）：只有大勝、險勝播佔上風那一版。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.choose("act:train", fight=_judged(request))
    record = game.state.battles[0]
    expected = "佔上風的過程。" if record.tier in ("大勝", "險勝") else "落下風的過程。"
    assert record.narration == expected and expected in game.battle_card()
    assert record.rounds  # 回合照樣算好：過程換成模型寫的那一版，數字照樣在得失裡


def test_a_stale_judgment_is_dropped(game):
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    stale = _judged(request.model_copy(update={"location": "town"}))
    game.choose("act:train", fight=stale)
    assert game.state.battles[0].narration == ""


def test_a_judgment_survives_the_season_clock_moving_while_the_model_thinks(game):
    """模型要想一分鐘，這段時間誰同步一次，賽季時鐘就往前走（計畫三 G1）：單子不記時間，判讀照樣套得上。"""
    _boss_at_the_lake(game)
    game.sync(1000.0)
    request = game.fight_request("act:train")
    before = game.state.world.time
    game.sync(1060.0)
    assert game.state.world.time > before
    game.choose("act:train", fight=_judged(request))
    assert game.state.battles[0].narration in ACCOUNTS


def test_a_judgment_is_dropped_after_another_fight(game):
    """Review Focus 3：等模型的時候（另一個分頁）又打了一場，戰報流水號變了：回來的判讀作廢、照平常打。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.choose("act:train")
    game.choose("act:train", fight=_judged(request))
    newest = game.state.battles[0]
    assert newest.id == request.battle_seq + 2 and newest.narration == ""
    assert game.state.battles[1].narration == ""


def test_a_judgment_is_dropped_after_switching_arts(game):
    """Review Focus 3：等模型的時候換了武學，陣容跟判讀的那一張對不上：作廢、照平常打。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.state.player.member.wugong_id = "fist"
    game.choose("act:train", fight=_judged(request))
    assert game.state.battles[0].narration == ""


class _FirstChoice(random.Random):
    """rng.choice 一律挑第一個：看得出遊歷的對手是不是照 Game.rng 挑的。"""

    def choice(self, seq):
        return seq[0]


def test_a_judged_trip_fights_the_judged_foe_and_an_unjudged_one_still_draws_from_the_rng(game):
    """判讀過的遊歷打單子上那一路（照名號、地點、戰報流水號雜湊挑的），判定差距平移優勢換算的量；沒有判讀的照舊用
    Game.rng 隨機挑（計畫三 G1：亂數序列、整季模擬都不變）。"""
    from tianxia import encounter, team

    game.content.locations["lake"].enemies = ["thug", "boss"]
    walk_to(game, "lake")
    game.state.player.member.wugong_id = "basic_fist"
    game.state.battle_seq = next(n for n in range(100) if _pick(game, n) == "boss")
    request = game.fight_request("act:train")
    assert request.squad_id == "boss"
    game.rng = _FirstChoice(0)
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game.choose("act:train", fight=_judged(request))
    assert game.state.battles[0].opponent == "翻江龍" and game.state.battles[0].narration in ACCOUNTS
    assert fight.call_args.kwargs["shift"] == pytest.approx(encounter.advantage_shift(200, 15))
    game.choose("act:train")
    assert game.state.battles[0].opponent == "水寇小隊" and game.state.battles[0].narration == ""


def _pick(game, battle_seq: int) -> str:
    game.state.battle_seq = battle_seq
    return game._train_pick(game.content.locations[game.state.player.location]).id


def test_a_judgment_is_used_once_and_never_by_a_foe_met_while_exploring(game):
    """判讀只用在它那一場（計畫三 G8）：同一次行動再打一場同一路不會再吃一次；探索撞上的野外對手是當下擲出來的，不問模型、
    也不吃判讀（設計 8.3 只算遊歷、劇情戰與挑戰本人）。"""
    _boss_at_the_lake(game)
    game._fight = _judged(game.fight_request("act:train"))
    game._squad_encounter("boss", wild=True)
    assert game.state.battles[0].narration == "" and game._fight is not None
    game._squad_encounter("boss")
    game._squad_encounter("boss")
    assert game.state.battles[1].narration in ACCOUNTS and game.state.battles[0].narration == ""
    assert game._fight is None


def test_the_fight_request_and_its_recheck_never_tick_the_battle(game):
    """備料（A 段）與進鎖重驗都只讀：推進全服戰鬥留給 choose() 開頭那一次（理由同 dialogue_request）。"""
    _boss_at_the_lake(game)
    calls, patched = _spy_battle_status(game)
    with patched:
        request = game.fight_request("act:train")
        game._checked_fight("act:train", _judged(request))
    assert calls and True not in calls
    calls, patched = _spy_battle_status(game)
    with patched:
        game.choose("act:train", fight=_judged(request))
    assert calls.count(True) == 1 and game.state.battles[0].narration in ACCOUNTS


def test_no_model_and_drills_are_never_judged(game):
    """沒有模型（伺服器假人的 client 是 None）不問；遊歷遇上自己陣營的隊伍是操練、不打架，不判讀，按鈕也不寫「兩人對峙」。
    操練只是遊歷的事：同一路人馬在劇情戰裡照樣開打，仍是大場面（Task 2 審查修正 1）。"""
    _boss_at_the_lake(game)
    client, game.client = game.client, None
    assert game.fight_request("act:train") is None
    game.client = client
    game.content.squads["boss"].faction = game.state.player.faction = "kou"
    assert game.fight_request("act:train") is None
    assert next(o for o in game.options() if o.id == "act:train").wait == ""
    game.state.pending_event = "duel"  # 應戰翻江龍：劇情戰不操練
    assert next(o for o in game.options() if o.id == "choice:0").wait == "兩人對峙……"
    assert game.fight_request("choice:0").squad_id == "boss"


def test_only_the_big_event_fight_tells_the_page_to_wait_and_free_words_are_no_fight(game):
    """事件的戰鬥選項：打頭目（翻江龍）那一顆寫「兩人對峙」，其他不寫；隨口應對（choice:free）不是仗，也不會在鎖裡出錯。"""
    from tianxia.models import FreeTextChoice

    walk_to(game, "lake")
    game.content.events["duel"].free_text = FreeTextChoice(prompt="自己想辦法……", stat="str")
    game.state.pending_event = "duel"
    assert {o.id: o.wait for o in game.options()} == {"choice:0": "兩人對峙……", "choice:1": "", "choice:free": ""}
    assert game.fight_request("choice:0").squad_id == "boss" and game.fight_request("choice:0").event == "duel"
    assert game.fight_request("choice:1") is None and game.fight_request("choice:free") is None


def test_the_journal_calls_it_a_training_trip(game):
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)
    game.choose("act:train")
    assert any(entry.title == "遊歷・湖邊" for entry in game.state.journal)


def test_an_unavailable_dialogue_turn_costs_nothing_and_ends_the_talk(content, game):
    """模型叫不動：這輪不扣體力、不記好感度與交友 tag，對話直接結束（不再卡在同一句保底反應裡）。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("talk:0")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_an_unavailable_opening_refunds_the_socialize_cost(content, game):
    content.characters["mate"].deep_interaction = True
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("act:socialize")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None

def _training_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


@pytest.mark.parametrize("faction, expected", [("huang", 31), ("guan", 29), ("haoqiang", 29), (None, 29)])
def test_winning_a_training_fight_pushes_the_trend_your_factions_way(content, game, faction, expected):
    """企劃者決定：遊歷推大勢的量照地點，方向照自己陣營的目標；散人和沒有這條線目標的陣營照地點原本的方向。"""
    _training_factions(content)
    game.state.player.faction = faction
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    walk_to(game, "lake")
    game.choose("act:train")  # 湖邊的對手是水寇小隊（不屬於任何陣營），train_trend kou:-1
    assert game.state.battles[0].kind == "train"
    assert game.state.world.trends["kou"] == expected


def test_training_with_your_own_factions_squad_is_a_drill(content, game):
    """遇到自己陣營的人不開打，改成一起操軍擺陣：不會輸、給經驗與心得、不給銀兩不掉素材，大勢往自己這邊推。"""
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"  # 沒學武功也沒關係：操練不會輸
    walk_to(game, "lake")
    silver, xinde = game.state.player.stats["silver"], game.state.player.stats.get("xinde", 0)
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.state.battles == []
    assert game.state.player.stats["silver"] == silver
    assert game.state.player.stats["xinde"] == xinde + content.squads["thug"].reward_xinde
    assert game.state.player.member.exp > 0 or game.state.player.member.level > 1
    assert game.state.player.materials == {}
    assert game.state.world.trends["kou"] == 31


def test_training_among_your_own_side_is_labelled_a_drill_not_a_fight(content, game):
    """自己陣營的地盤（只會操練）不寫勝算「必敗」，寫明是操練（試玩回饋 FB-008）。"""
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"  # 沒學武功：照勝算算是必敗，但操練不會輸
    walk_to(game, "lake")
    option = next(o for o in game.options() if o.id == "act:train")
    assert (option.label, option.enabled) == ("操練（體力 10・零風險）", True)
    game.state.player.faction = "guan"  # 換成對頭：照樣是要打的遊歷，寫對手與勝算
    option = next(o for o in game.options() if o.id == "act:train")
    assert option.label.startswith("遊歷（體力 10・水寇小隊・")


def test_where_some_squads_are_your_own_the_odds_are_for_the_others(content, game):
    """自己人與外人都有的地方：勝算只看真的會打的那幾路，另外說明也可能是操練。"""
    _training_factions(content)
    content.squads["boss"].faction = "huang"  # 翻江龍（難度 200）是自己人：不能拿它算勝算
    content.locations["lake"].enemies = ["thug", "boss"]
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    label = next(o for o in game.options() if o.id == "act:train").label
    assert label == f"遊歷（體力 10・水寇小隊・{game.odds('thug')}・或與自己人操練）"


def test_train_trend_push_previews_the_push_for_your_faction(content, game):
    _training_factions(content)
    game.state.player.faction = "huang"
    assert game.train_trend_push("lake") == {"kou": 1}
    assert game.train_trend_push("town") == {}
    game.state.player.faction = None
    assert game.train_trend_push("lake") == {"kou": -1}

def test_a_drill_is_journaled_as_a_drill_without_a_battle_card(content, game):
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    game.choose("act:train")
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.battle_id) == ("遊歷・湖邊", "操練", None)
    assert entry.changes == ["心得 +10", "經驗 +20（每人）"] and entry.lines == ["（寇亂 +1）"]
    assert game.state.battle_card is None


def test_a_drill_is_not_followed_by_a_post_fight_event(content, game):
    """操練不是打架，不該接「一番苦戰之後」這類戰後事件（試玩回饋 FB-001）。"""
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    content.config.train_event_chance = 1.0
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.state.pending_event is None


def _figure(content, fame=0):
    ch = content.characters["mate"]
    ch.deep_interaction = True
    ch.audience_fame = fame
    return ch


def test_a_newcomer_without_fame_is_turned_away_from_a_figure(content, game):
    _figure(content, fame=10)
    with mock.patch("tianxia.engine.pick_event", return_value=None), \
            mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert msgs == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 10）"]  # 內容沒寫打發話，用通用的那一句


def test_enough_fame_or_a_prior_meeting_opens_the_door(content, game):
    _figure(content, fame=10)
    game.state.player.flags.add("結識:mate")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    game.choose("talk:leave")
    game.state.player.flags.discard("結識:mate")
    game.state.player.stats["fame"] = 10
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


def test_three_turns_a_day_with_the_same_figure(content, game):
    _figure(content)
    game.state.player.fortune = True  # 第二天起交友會先觸發新立門戶福緣，這裡只測輪數上限
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
        assert msgs[-1] == "天色已晚，韓鐵起身送客，改日再敘。"
        assert game.state.player.pending_companion is None
        with mock.patch("tianxia.engine.pick_event", return_value=None):
            msgs = game.choose("act:socialize")
        assert msgs == ["韓鐵今日事忙，改日再來拜會吧。"]
        game.state.world.time += 86400  # 隔天重算
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


def _lone_figure_at_the_cave(content, fame=10):
    """寶洞沒有交友事件：這裡只站著韓鐵一位大勢人物。"""
    ch = _figure(content, fame=fame)
    ch.kind, ch.recruit_at, ch.talk_at = "locked", None, "cave"
    return ch


def test_a_lone_figure_you_cannot_meet_leaves_only_the_free_audience_button(content, game):
    """沒有交友事件、唯一的大勢人物又見不到：交友按下去只是花 5 點體力換同一句打發，所以不給交友，
    這條路只剩不花體力的求見（設計 9.1：求見一直都在）。"""
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)  # 沒有大勢人物也沒有事件
    _lone_figure_at_the_cave(content, fame=10)
    assert game.state.player.stats.get("fame", 0) < 10
    assert "act:socialize" not in ids(game)
    option = next(o for o in game.options() if o.id == "call:mate")
    assert (option.label, option.enabled) == ("求見韓鐵（名望還差 10）", True)
    stamina = game.state.player.stamina
    assert game.choose("call:mate")[0].startswith("韓鐵連見都不見你")
    assert game.state.player.stamina == stamina


def test_socialize_stays_wherever_it_is_not_futile(content, game):
    """交友照給：地點有交友事件、見得到那位人物、福緣到期、或在召見的地點（交友端出晉升奇遇）。"""
    game.state.player.location = "cave"
    _lone_figure_at_the_cave(content, fame=10)
    assert "act:socialize" not in ids(game)
    game.state.player.stats["fame"] = 10  # 見得到他
    assert "act:socialize" in ids(game)
    game.state.player.stats["fame"] = 0
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min  # 福緣到期：交友最先發福緣
    assert "act:socialize" in ids(game)
    game.state.player.fortune = True
    assert "act:socialize" not in ids(game)
    with mock.patch("tianxia.engine.ranks.summons_event", return_value="join"):  # 召見的地點
        assert "act:socialize" in ids(game)
    game.state.player.location = "town"  # 小鎮有交友事件（拜師）
    assert "act:socialize" in ids(game)


def test_a_newcomer_below_the_threshold_gets_the_locations_event_instead_of_a_dialogue(content, game):
    """小鎮有交友事件（拜師）也有一位名望不夠的大勢人物：不 mock pick_event，交友照地點事件走，不算被擋在門外。"""
    _figure(content, fame=10)
    msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert game.state.pending_event is not None
    assert not any("連見都不見你" in m for m in msgs)


# ── 鎖外生成：dialogue_request 與 choose(prepared=...) ────────────────


def _open_dialogue(content, game):
    """停在小鎮、已跟韓鐵開了第一輪對話（選項是「閒聊幾句」「就此告辭」）；福緣設成已領，交友不會先觸發福緣。"""
    _figure(content)
    game.state.player.fortune = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")


def _prepared(game, option_id, turn=FAKE_TURN):
    req = game.dialogue_request(option_id)
    return companion_agent.PreparedTurn(req.option_id, req.companion_id, req.player_action, turn)


NEXT_TURN = companion_agent.CompanionTurn(
    narrative="他笑了笑。", options=["再聊聊", "起身告辭"], option_tags=["雪中送炭", "尋常寒暄"],
)


def _no_model():
    """讓任何一條「在鎖內生成」的路徑直接失敗，證明這輪用的是預先生成好的。"""
    return mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該在鎖內生成"))


def test_dialogue_request_for_a_talk_option_carries_the_offered_text(content, game):
    _open_dialogue(content, game)
    req = game.dialogue_request("talk:0")
    assert (req.option_id, req.companion_id, req.player_action) == ("talk:0", "mate", "閒聊幾句")
    assert req.messages[-1]["content"].startswith("玩家的行動：「閒聊幾句」")
    assert game.dialogue_request("talk:1").player_action == "就此告辭"


def test_dialogue_request_is_none_for_leaving_and_for_options_that_are_not_offered(content, game):
    _open_dialogue(content, game)
    assert game.dialogue_request("talk:leave") is None
    assert game.dialogue_request("talk:2") is None  # 只有兩個選項
    assert game.dialogue_request("talk:x") is None
    assert game.dialogue_request("act:socialize") is None  # 對話中選單上沒有交友


def test_dialogue_request_for_socialize_is_the_generic_opening(content, game):
    _figure(content)
    game.state.player.fortune = True
    req = game.dialogue_request("act:socialize")
    assert (req.option_id, req.companion_id, req.player_action) == (
        "act:socialize", "mate", companion_agent.GENERIC_OPENING,
    )
    assert req.messages == companion_agent._build_messages(
        content.characters["mate"], game.state, content, game.world, "mate", companion_agent.GENERIC_OPENING,
    )


def test_dialogue_request_is_none_when_socialize_would_not_open_a_dialogue(content, game):
    _figure(content, fame=10)
    game.state.player.fortune = True
    assert game.dialogue_request("act:socialize") is None  # 名望不夠，見不到
    game.state.player.stats["fame"] = 10
    assert game.dialogue_request("act:socialize") is not None
    game.state.player.stamina = 0
    assert game.dialogue_request("act:socialize") is None  # 選項停用
    game.state.player.stamina = content.config.stamina_max
    game.state.world.time += 86400 * content.config.fortune_day_min
    game.state.player.fortune = False
    assert game.dialogue_request("act:socialize") is None  # 福緣先到，交友不開對話


def test_dialogue_request_is_none_for_a_non_dialogue_option(content, game):
    _figure(content)
    game.state.player.fortune = True
    assert game.dialogue_request("act:explore") is None
    assert game.dialogue_request("move:lake") is None


def test_dialogue_request_does_not_change_the_game(content, game):
    _open_dialogue(content, game)
    def snapshot():  # 角色存檔不含賽季（GameState.world 不進 model_dump），賽季要另外比：記憶體裡的與全服共用的那一份
        return game.state.model_dump(), game.state.world.model_dump(), game.world.get_season().model_dump()

    before = snapshot()
    game.dialogue_request("talk:0")
    game.dialogue_request("act:socialize")
    assert snapshot() == before


def test_choose_applies_a_prepared_talk_turn_without_calling_the_model(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=NEXT_TURN)
    with _no_model(), mock.patch.object(game.client, "chat_structured", side_effect=AssertionError("不該呼叫模型")):
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["他笑了笑。", "（好感度 +1）"]
    assert game.state.player.stamina == before - content.config.talk_stamina
    assert game._talks_used("mate") == 1  # 這一輪算進今天的輪數
    assert game.state.player.last_offered_dialogue["mate"] == [["再聊聊", "起身告辭"], ["雪中送炭", "尋常寒暄"]]
    assert game.state.player.affinities["mate"] == 1


def test_choose_applies_a_prepared_opening_without_calling_the_model(content, game):
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=NEXT_TURN)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["他笑了笑。"]
    assert game.state.player.pending_companion == "mate"
    assert game.state.player.stamina == before - content.config.action_cost["socialize"]
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]


def test_a_prepared_failure_for_the_opening_refunds_the_socialize_cost(content, game):
    """鎖外生成失敗（turn=None）：跟鎖內 DialogueUnavailable 完全一樣——退回交友體力、不開對話、同一句說明。"""
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=None)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None


def test_a_prepared_failure_for_a_talk_turn_costs_nothing_and_ends_the_talk(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=None)
    with _no_model():
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert game._talks_used("mate") == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_a_mismatched_prepared_turn_is_ignored_and_the_normal_path_generates(content, game):
    """對不上（玩家行動不同，例如選項清單已經換了）：丟掉預先生成的，照一般路徑在鎖內生成。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", FAKE_TURN)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
        msgs = game.choose("talk:0", prepared=stale)
    gen.assert_called_once()
    assert msgs[0] == "他笑了笑。"  # 用的是現生成的，不是 stale 帶的 FAKE_TURN


def test_a_mismatched_failed_prepared_turn_does_not_end_the_talk(content, game):
    """對不上的 prepared 連同它的失敗一起丟掉：不能因為別張單子失敗，就把這輪對話結束掉。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", None)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN):
        msgs = game.choose("talk:0", prepared=stale)
    assert msgs[0] == "他笑了笑。"
    assert game.state.player.pending_companion == "mate"


def test_a_prepared_turn_for_another_companion_or_option_is_ignored(content, game):
    for stale in (
        companion_agent.PreparedTurn("talk:0", "someone_else", "閒聊幾句", FAKE_TURN),
        companion_agent.PreparedTurn("talk:1", "mate", "閒聊幾句", FAKE_TURN),
    ):
        _open_dialogue(content, game)
        with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
            msgs = game.choose("talk:0", prepared=stale)
        gen.assert_called_once()
        assert msgs[0] == "他笑了笑。"
        game.choose("talk:leave")  # 退出這段對話，下一個 stale 重新開


def test_choose_rejects_a_second_opening_once_a_dialogue_is_already_open(content, game):
    """連點兩下：第二張單子進鎖時對話已經開了，交友不在選單上——這是 choose() 自己的「選項可用」檢查擋下的，
    不是 prepared 的重驗（重驗見下一個測試）。"""
    _figure(content)
    game.state.player.fortune = True
    first, second = _prepared(game, "act:socialize"), _prepared(game, "act:socialize")
    with _no_model():
        game.choose("act:socialize", prepared=first)
        stamina = game.state.player.stamina
        assert game.choose("act:socialize", prepared=second) == ["（此刻無法這麼做。）"]
    assert game.state.player.stamina == stamina


def test_a_prepared_turn_is_ignored_by_options_that_do_not_use_it(content, game):
    _figure(content)
    game.state.player.fortune = True
    stray = companion_agent.PreparedTurn("act:explore", "mate", "x", FAKE_TURN)
    before = game.state.player.stamina
    with _no_model():
        game.choose("act:explore", prepared=stray)
    assert game.state.player.stamina == before - content.config.action_cost["explore"]
    assert game.state.player.pending_companion is None


def test_a_prepared_opening_is_dropped_by_the_recheck_when_the_fortune_comes_due_meanwhile(content, game):
    """生成的那段時間福緣到期：交友選項還在、還能按，但這次交友會先發福緣、不開對話——這才是重驗擋下來的情況。"""
    _figure(content)
    game.state.player.fortune = True
    prepared = _prepared(game, "act:socialize")
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min
    assert any(o.id == "act:socialize" and o.enabled for o in game.options())
    assert game._checked_prepared("act:socialize", prepared) is None
    with _no_model():
        game.choose("act:socialize", prepared=prepared)
    assert game.state.player.pending_companion is None
    assert game.state.player.fortune  # 走的是福緣那條路，不是對話


def _spy_battle_status(game):
    """記下每次 _battle_status 是用 tick=True 還是 tick=False 呼叫的。"""
    calls = []
    real = type(game)._battle_status

    def spy(self, tick=True):
        calls.append(tick)
        return real(self, tick=tick)

    return calls, mock.patch.object(type(game), "_battle_status", spy)


def test_options_passes_tick_through_to_the_battle_status(game):
    calls, patched = _spy_battle_status(game)
    with patched:
        game.options(odds=False, tick=False)
        assert calls == [False]
        game.options(odds=False)
        game.options()
    assert calls == [False, True, True]  # 預設還是 tick=True，其他呼叫端的行為不變


def test_dialogue_request_and_the_recheck_never_tick_the_battle(content, game):
    """一次請求只能推進一次戰鬥（推進可能結算一回合、呼叫 LLM 潤色，而且是握著鎖呼叫）：
    備料（階段 A）與進鎖後的重驗都只讀，推進交給 choose() 自己開頭那一次。"""
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched:
        game.dialogue_request("talk:0")
        game.dialogue_request("act:socialize")
        game._checked_prepared("talk:0", prepared)
    assert calls and True not in calls


def test_choosing_a_prepared_dialogue_option_ticks_the_battle_only_once(content, game):
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched, _no_model():
        game.choose("talk:0", prepared=prepared)
    assert calls.count(True) == 1


# ── 喊停（地圖擴充：停在下一站） ─────────────────────────────────────────


def test_you_can_stop_at_the_next_station(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "walk")
    assert "act:halt" in [o.id for o in game.options() if o.enabled]
    assert "喊停（到湖邊就停下）" in [o.label for o in game.options()]
    game.choose("act:halt")
    assert game.state.player.journey.stop_at == 0
    assert not any(o.id == "act:halt" for o in game.options())  # 已經喊停了
    assert "已經喊停" in game.scene_text()
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)
    assert game.state.player.location == "lake" and game.state.player.journey is None
    assert game.state.journal[0].tag == "喊停，停在 湖邊"


def test_stopping_does_not_refund_the_stamina_paid_to_hurry(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 100
    game.travel("cave", "hurry")  # 7.5 分鐘：8 點
    msgs = game.choose("act:halt")
    assert game.state.player.stamina == 92
    assert "（趕路已經花掉的體力不退。）" in msgs


def test_there_is_nothing_to_stop_on_the_last_leg(game):
    game.choose("move:lake")
    assert not any(o.id == "act:halt" for o in game.options())


# ── 路上：改道與折返（路上設計第三節）──────────────────────────


def _add_field(content):
    """夾具只有一條線（小鎮—湖邊—寶洞）；在小鎮西邊加一塊田（一般路，3 分鐘），讓掉頭之後有別處可去。"""
    content.locations["field"] = Location(id="field", name="田野", description="一片田。", connections=["town"], x=0, y=100)
    content.locations["town"].connections.append("field")


def _partway(game, share=1 / 3):
    """從小鎮步行往湖邊（夾具 3 分鐘），把時間推到走了 share 成的那一刻；回傳這一趟。"""
    game.choose("move:lake")
    game.advance(180 * share)
    return game.state.player.journey


def _back(game):
    return next(o for o in game.options() if o.id.startswith("road:back"))


def test_turning_back_walks_back_the_part_already_walked(game):
    _partway(game)  # 走了一成三：回小鎮要 1 分鐘
    back = _back(game)
    assert (back.id, back.label, back.enabled) == ("road:back", "折返 小鎮（步行約 1 分鐘）", True)
    game.choose("road:back")
    j = game.state.player.journey
    assert (j.path, j.origin, j.share) == (["town"], "lake", pytest.approx(2 / 3))
    assert j.arrive_at == [pytest.approx(120.0)]  # 第 60 秒掉頭，再走 60 秒
    assert (game.state.journal[0].title, game.state.journal[0].tag) == ("前往 小鎮", "步行約 1 分鐘")
    game.advance(60)
    assert game.state.player.location == "town" and game.state.player.journey is None


def test_rerouting_takes_the_shorter_of_turning_back_and_going_on(content, game):
    _add_field(content)
    game.state.world.flags.add("cave_open")
    _partway(game)  # 小鎮—湖邊走了一成三：回小鎮 1 分鐘、到湖邊 2 分鐘
    on = atlas.way_to(game.state, content, "cave")  # 繼續：2 ＋ 湖邊—寶洞山路 4.5（掉頭要 1 ＋ 3 ＋ 4.5）
    assert (on.path, on.origin, on.share) == (("lake", "cave"), "town", pytest.approx(1 / 3))
    assert on.minutes == pytest.approx(6.5)
    back = atlas.way_to(game.state, content, "field")  # 掉頭：1 ＋ 小鎮—田野 3（繼續要 2 ＋ 3 ＋ 3）
    assert (back.path, back.origin, back.share) == (("town", "field"), "lake", pytest.approx(2 / 3))
    assert back.legs == (pytest.approx(1.0), pytest.approx(3.0))


def test_rerouting_to_either_end_of_the_road(game):
    _partway(game)
    game.travel("lake")  # 改去前面那一站：照原路走完這一段，抵達時間不變
    j = game.state.player.journey
    assert (j.path, j.arrive_at) == (["lake"], [pytest.approx(180.0)])
    game.travel("town")  # 改去剛離開的那一站：就是折返
    j = game.state.player.journey
    assert (j.path, j.origin, j.arrive_at) == (["town"], "lake", [pytest.approx(120.0)])


def test_a_reroute_charges_the_new_way_and_refunds_nothing(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 100
    game.set_move_mode("hurry")
    game.choose("move:lake:hurry")  # 3 分鐘：3 點
    game.choose("road:back:hurry")  # 剛出發就掉頭：不扣體力、當下回到小鎮（FB-025），原本的 3 點不退
    assert game.state.player.stamina == 97 and game.state.player.journey is None
    game.choose("move:lake:hurry")
    game.advance(30)  # 趕路 90 秒的一成三
    game.travel("cave", "hurry")  # 繼續：2 ＋ 4.5 ＝ 6.5 分鐘，7 點；第一段是半段路
    assert game.state.player.stamina == pytest.approx(97 - 3 - 7 + 30 / 180)  # 走那 30 秒回了一點點
    j = game.state.player.journey
    assert j.arrive_at == [pytest.approx(game.state.world.time + 60), pytest.approx(game.state.world.time + 195)]


def test_dashing_from_the_road_reaches_an_end_of_the_road_first(content, game):
    _add_field(content)
    _partway(game)
    game.travel("field", "dash")  # 掉頭比較近：先到小鎮，再到田野
    p = game.state.player
    assert p.location == "field" and p.journey is None and "field" in p.visited
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.changes) == ("前往 田野（途經 小鎮）", "疾行立刻到", ["體力 -8"])


def test_a_rerouted_trip_can_be_halted_like_any_other(content, game):
    _add_field(content)
    _partway(game)
    game.travel("field")  # 小鎮、田野兩站
    assert "喊停（到小鎮就停下）" in [o.label for o in game.options()]
    game.choose("act:halt")
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)
    assert game.state.player.location == "town" and game.state.player.journey is None
    assert game.state.journal[0].tag == "喊停，停在 小鎮"


def test_rerouting_out_of_the_battle_region_leaves_it_and_turning_back_returns(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        _partway(game)
        game.travel("cave")  # 繼續走：湖邊之後是南區的寶洞
        assert game.world.get_battle().participants["沈浪"].away
        game.choose("road:back")  # 掉頭回小鎮：這一趟的站都在北區
        assert not game.world.get_battle().participants["沈浪"].away


def test_turning_back_follows_the_move_mode(game):
    _partway(game)
    game.set_move_mode("hurry")
    assert (_back(game).id, _back(game).label) == ("road:back:hurry", "折返 小鎮（趕路約 1 分鐘・體力 1）")
    game.set_move_mode("dash")
    game.state.player.stamina = 1
    back = _back(game)
    assert (back.id, back.label, back.enabled) == ("road:back:dash", "折返 小鎮（疾行・體力不足，要 2）", False)
    assert game.choose("road:back:dash") == ["（此刻無法這麼做。）"]
    game.state.player.stamina = 10
    game.choose("road:back:dash")
    assert game.state.player.location == "town" and game.state.player.journey is None
    assert game.state.player.stamina == 8


def test_turning_back_right_after_setting_off_is_free_and_lands_at_once(game):
    """剛出發就折返（FB-025）：回程不到半分鐘路程時，哪種走法都不扣體力、當下就回到原地（路上裁決「給 QA 的」）。"""
    game.set_move_mode("hurry")
    game.choose("move:lake:hurry")
    game.advance(10)  # 趕路 10 秒＝走了 1/3 分鐘路程
    stamina = game.state.player.stamina
    assert [(o.label, o.enabled) for o in game.travel_options("town")] == [
        ("步行（立刻到）", True), ("趕路（立刻到）", True), ("疾行（立刻到）", True),
    ]
    assert (_back(game).id, _back(game).label) == ("road:back:hurry", "折返 小鎮（立刻到）")
    game.choose("road:back:hurry")
    p = game.state.player
    assert (p.location, p.journey, p.stamina) == ("town", None, stamina)
    assert (game.state.journal[0].title, game.state.journal[0].tag, game.state.journal[0].changes) == (
        "前往 小鎮", "立刻折返", [],
    )


def test_turning_back_after_a_real_stretch_still_costs_and_takes_time(game):
    """走了一段才折返照舊算：回程 1.5 分鐘路程，趕路 2 點、約 1 分鐘。"""
    game.set_move_mode("hurry")
    game.choose("move:lake:hurry")
    game.advance(45)  # 趕路 90 秒的一半
    stamina = game.state.player.stamina
    assert _back(game).label == "折返 小鎮（趕路約 1 分鐘・體力 2）"
    game.choose("road:back:hurry")
    p = game.state.player
    assert p.journey is not None and p.journey.path == ["town"] and p.stamina == stamina - 2


def test_turning_back_twice_quickly_is_not_a_free_arrival_at_the_far_end(game):
    """掉頭之後馬上又掉頭：身後那一站是剛才要去的湖邊、不是自己最後待過的小鎮，不算剛出發，照舊要走（不能拿來白白抵達）。"""
    game.choose("move:lake")
    game.advance(160)  # 走了快九成
    game.choose("road:back")
    game.choose("road:back")  # 再掉頭：往湖邊，回程 20 秒路程
    p = game.state.player
    assert p.journey is not None and p.journey.path == ["lake"] and p.location == "town"


def test_the_road_scene_says_what_you_can_do_on_the_road(game):
    game.choose("move:lake")
    scene = game.scene_text()
    assert "路上可以折返" in scene and "修練、煉製" in scene and "到了會自己抵達" in scene
    assert "路上不能做事" not in scene


def test_an_old_journey_without_the_reroute_fields_still_loads():
    j = Journey.model_validate({"mode": "walk", "path": ["lake"], "arrive_at": [180.0]})
    assert (j.origin, j.share) == (None, 0.0)


# ── 路上小事（路上設計第四節）──────────────────────────────


def _task(game, what):
    return next(o for o in game.options() if o.id == f"road:{what}")


def test_road_tasks_are_once_per_leg_and_free(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave")  # 小鎮—湖邊—寶洞兩段
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（心得 +3）", True)
    stamina = game.state.player.stamina
    game.choose("road:think")
    assert game.state.player.stats["xinde"] == 3 and game.state.player.stamina == stamina
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)
    entry = game.state.journal[0]
    assert (entry.title, entry.changes) == ("邊走邊想", ["心得 +3"])
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 到湖邊：換段
    assert game.state.player.journey is not None and _task(game, "think").enabled


def test_turning_back_does_not_hand_out_the_road_tasks_again(game):
    game.choose("move:lake")
    game.choose("road:think")
    game.choose("road:back")  # 剛出發就掉頭，馬上回到小鎮
    game.advance(0)
    assert game.state.player.location == "town" and game.state.player.journey is None
    game.choose("move:lake")  # 再出發：還沒真的到下一站，做過的還是做過了（不然來回折返就能不走路刷完一天的收穫）
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 真的走到湖邊才換段
    assert game.state.player.leg_actions == set()


def test_dashing_has_no_road_tasks(game):
    game.state.player.journey = Journey(mode="dash", path=["lake"], arrive_at=[1e9])
    assert not any(o.id.startswith("road:") and o.id != "road:back" for o in game.options())
    game.state.player.journey = Journey(mode="hurry", path=["lake"], arrive_at=[90.0])
    assert "road:gather" in ids(game)


def test_asking_along_the_road_hears_a_rumor_from_this_part_of_the_land(game):
    game.choose("move:lake")
    w = game.state.world
    w.rumors += [
        Rumor(time=0, text="南邊鬧水患。", location=None, region="south"),
        Rumor(time=0, text="官軍在湖邊集結。", location="lake", region="north", faction="guan"),  # 別的陣營的軍情
        Rumor(time=0, text="湖邊來了個怪客。", location="lake", region="north"),
    ]
    msgs = game.choose("road:ask")
    assert msgs == ["你沿途向人打聽，聽說：湖邊來了個怪客。"]
    assert (_task(game, "ask").label, _task(game, "ask").enabled) == ("沿途打聽（打聽過了，到下一站再說）", False)


def test_asking_with_nothing_to_hear_still_counts(game):
    game.choose("move:lake")
    assert game.choose("road:ask") == ["你沿途問了幾個人，這一帶最近沒什麼新鮮事。"]
    assert not _task(game, "ask").enabled


def test_surveying_marks_the_unknown_places_near_both_ends(content, game):
    content.config.vision_base = 0  # 只看得見自己那一站
    game.state.world.flags.add("cave_open")
    game.choose("move:lake")
    assert atlas.views(game.state, content)["lake"] == "dot"
    msgs = game.choose("road:survey")
    assert msgs == ["你留意沿路的地形，摸清了湖邊、寶洞的位置。"]
    assert game.state.player.surveyed == {"lake", "cave"}
    assert atlas.views(game.state, content)["cave"] == "remembered"


def test_surveying_with_nothing_left_to_find_still_counts(game):
    game.choose("move:lake")
    assert game.choose("road:survey") == ["你留意了一路的地形，附近沒有什麼沒摸清的地方。"]
    assert not _task(game, "survey").enabled


def test_gathering_by_the_road_follows_what_the_two_ends_offer(content, game):
    content.locations["lake"].materials = ["gang_2"]  # 湖邊出剛的素材：路邊撿到的是剛的一階
    game.choose("move:lake")
    game.rng = FixedRandom(0.1)
    assert game.choose("road:gather") == ["你在路邊翻找了一陣。", "獲得 精鐵砂 ×1"]
    assert game.state.player.materials == {"gang_1": 1}


def test_gathering_can_come_up_empty(game):
    game.choose("move:lake")
    game.rng = FixedRandom(0.9)  # 四成機會：沒撿到
    assert game.choose("road:gather") == ["你在路邊翻找了一陣，沒找到什麼能用的。"]
    assert game.state.player.materials == {} and not _task(game, "gather").enabled


def test_gathering_without_any_tier_one_material_finds_nothing(content, game):
    """內容裡沒有一階素材時，採集當成沒找到，不會出錯，也不算今天的收穫。"""
    content.materials = {k: m for k, m in content.materials.items() if m.tier != 1}
    game.choose("move:lake")
    game.rng = FixedRandom(0.1)
    assert game.choose("road:gather") == ["你在路邊翻找了一陣，沒找到什麼能用的。"]
    assert game.state.player.road_rewards_today.get("task") is None


def test_the_road_scene_lists_the_road_tasks(game):
    game.choose("move:lake")
    assert "邊走邊想、沿途打聽、留意地形、路邊採集" in game.scene_text()


def test_old_saves_without_road_fields_load(content, game):
    raw = game.state.model_dump(mode="json")
    del raw["player"]["leg_actions"], raw["player"]["surveyed"], raw["player"]["road_rewards_today"]
    loaded = GameState.model_validate(raw)
    assert loaded.player.leg_actions == set() and loaded.player.surveyed == set()
    assert loaded.player.road_rewards_today == {}


# ── 路上收穫的每天上限（企劃者 2026-10-03 決定）──────────────────


def _leg(game, dest, *tasks):
    """從所在的站步行到相鄰的 dest，路上依序做 tasks，一路走到。"""
    game.choose(f"move:{dest}")
    for what in tasks:
        game.choose(f"road:{what}")
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)


def test_thinking_on_the_road_pays_only_the_first_few_times_a_game_day(content, game):
    content.config.road_reward_daily_cap = 2
    p = game.state.player
    _leg(game, "lake", "think")
    _leg(game, "town", "think")
    assert p.road_rewards_today == {"task": [1, 2]}
    game.choose("move:lake")  # 同一天的第三段路
    think = _task(game, "think")
    assert (think.label, think.enabled) == ("邊走邊想（今天沒有收穫了）", True)
    xinde = p.stats["xinde"]
    assert game.choose("road:think") == ["你邊走邊想，今天想得夠多了，沒有新的心得。"]
    assert p.stats["xinde"] == xinde and p.road_rewards_today == {"task": [1, 2]}
    assert game.state.journal[0].changes == []
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)


def test_the_road_reward_count_starts_over_the_next_game_day(content, game):
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    _leg(game, "lake", "think")
    game.state.world.time += DAY  # 隔天：紀錄是前一天的就當沒拿過（跟每天對話輪數同一個算法）
    game.choose("move:town")
    assert _task(game, "think").label == "邊走邊想（心得 +3）"
    xinde = p.stats["xinde"]
    game.choose("road:think")
    assert p.stats["xinde"] == xinde + 3 and p.road_rewards_today == {"task": [2, 1]}


def test_only_a_material_actually_found_counts_toward_the_day(game):
    p = game.state.player
    game.choose("move:lake")
    game.rng = FixedRandom(0.9)
    game.choose("road:gather")  # 沒撿到：不算一次
    assert p.road_rewards_today == {}
    game.advance(p.journey.arrive_at[-1] - game.state.world.time)
    game.choose("move:town")
    game.rng = FixedRandom(0.1)
    game.choose("road:gather")
    assert sum(p.materials.values()) == 1 and p.road_rewards_today == {"task": [1, 1]}


def test_thinking_and_gathering_share_the_days_road_rewards(content, game):
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    game.choose("move:lake")
    game.choose("road:think")
    gather = _task(game, "gather")
    assert (gather.label, gather.enabled) == ("路邊採集（今天沒有收穫了）", True)
    game.rng = FixedRandom(0.1)  # 沒到上限的話這一擲撿得到
    assert game.choose("road:gather") == ["你留心路邊，今天已經撿夠了，沒再去翻。"]
    assert p.materials == {} and p.road_rewards_today == {"task": [1, 1]}
    assert not _task(game, "gather").enabled  # 照樣算這段路做過了
    # 沿途打聽、留意地形沒有經濟上的收穫，不設上限
    assert [_task(game, what).label for what in ("ask", "survey")] == ["沿途打聽（聽一則這一帶的傳聞）", "留意地形（摸清附近的地點）"]


# ── 路上見聞（路上設計第五節）──────────────────────────────
# 夾具的 road_sight_chance 是 0（其他測試的亂數序列才不會被打亂），這裡的測試自己設機率。


def test_a_road_sight_comes_on_arrival_at_the_set_chance(content, game):
    content.config.road_sight_chance = 0.3
    game.rng = FixedRandom(0.31)  # 沒擲進三成
    walk_to(game, "lake")
    assert game.state.player.recent_sights == []
    game.rng = FixedRandom(0.29)  # 擲進三成：看見一則
    walk_to(game, "town")
    (seen,) = game.state.player.recent_sights
    assert seen in {"sight_crow", "sight_wind", "sight_north_peddler"}  # 一般路、北區能挑的三則
    assert content.road_sights[seen].text in game.state.journal[0].lines


def test_road_sights_follow_the_kind_of_road(content, game):
    content.config.road_sight_chance = 1.0
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    game.state.player.recent_sights = ["sight_crow", "sight_wind"]  # 通用的兩則剛看過
    silver = game.state.player.stats["silver"]
    walk_to(game, "cave")  # 湖邊—寶洞是山路：剩下山路那一則
    assert game.state.player.recent_sights[-1] == "sight_cliff"
    assert game.state.player.stats["silver"] == silver + 5
    assert "銀兩 +5" in game.state.journal[0].changes


def test_road_sights_follow_the_region_of_the_stop_just_reached(content, game):
    content.config.road_sight_chance = 1.0
    content.locations["cave"].y = 170  # 寶洞搬進南區
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    game.state.player.recent_sights = ["sight_crow", "sight_wind", "sight_cliff"]
    walk_to(game, "cave")
    assert game.state.player.recent_sights[-1] == "sight_south_feather"
    assert game.state.player.materials == {"kuai_1": 1}


def test_recent_road_sights_wait_until_the_pool_runs_out(content, game):
    content.config.road_sight_chance = 1.0
    for dest in ("lake", "town", "lake"):
        walk_to(game, dest)
    assert set(game.state.player.recent_sights) == {"sight_crow", "sight_wind", "sight_north_peddler"}
    for dest in ("town", "lake", "town"):
        walk_to(game, dest)  # 池子用完了才重複
    assert len(game.state.player.recent_sights) == 5


def test_a_road_sight_seen_while_offline_is_dated_at_the_arrival(content, game):
    content.config.road_sight_chance = 1.0
    game.sync(1000.0)
    game.choose("move:lake")  # 第 0 秒出發，第 180 秒抵達
    game.sync(1000.0 + 3600)  # 下線一小時才回來
    sight = content.road_sights[game.state.player.recent_sights[-1]]
    entry = next(e for e in game.state.journal if sight.text in e.lines)
    assert entry.time == pytest.approx(180.0)


def test_dashing_still_rolls_a_road_sight_at_every_stop(content, game):
    content.config.road_sight_chance = 1.0
    game.state.world.flags.add("cave_open")
    game.travel("cave", "dash")  # 湖邊、寶洞兩站立刻抵達
    assert len(game.state.player.recent_sights) == 2


def test_old_saves_without_recent_sights_load(game):
    raw = game.state.model_dump(mode="json")
    del raw["player"]["recent_sights"]
    assert GameState.model_validate(raw).player.recent_sights == []


# ── 路上見聞的每天上限與折返（企劃者 2026-10-03 決定）──────────────
# 夾具在小鎮—湖邊（北區的一般路）能挑的是烏鴉（心得 +1）、起風（沒有收穫）、貨郎（心得 +2）三則；
# 把其餘的標成剛看過，下一則就一定是想要的那一則。


def _sight_rewards(entry):
    """一則江湖紀錄裡，路上見聞會給的那幾種收穫行。"""
    return [line for line in entry.lines + entry.changes if line.startswith(("心得 +", "銀兩 +", "獲得"))]


def test_road_sight_rewards_stop_at_the_days_cap_but_the_text_stays(content, game):
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    xinde = p.stats["xinde"]
    p.recent_sights = ["sight_wind", "sight_north_peddler"]  # 只剩烏鴉
    walk_to(game, "lake")
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [1, 1]}
    p.recent_sights = ["sight_crow", "sight_wind"]  # 同一天走回小鎮：只剩貨郎，但今天的收穫拿滿了
    walk_to(game, "town")
    entry = game.state.journal[0]
    assert content.road_sights["sight_north_peddler"].text in entry.lines  # 文字照寫
    assert _sight_rewards(entry) == []  # 沒有收穫、也沒有多一句
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [1, 1]}
    assert p.recent_sights[-1] == "sight_north_peddler"


def test_at_the_days_cap_sights_that_hand_you_something_stay_away(content, game):
    """拿滿了：給銀兩、素材的見聞，文字寫的就是拿到東西，那天不再出現；給心得的照寫文字、不給心得（見上一則）。"""
    content.config.road_sight_chance = 0.0
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    p.road_rewards_today = {"sight": [1, 1]}  # 今天的見聞收穫已經拿滿
    p.recent_sights = ["sight_crow", "sight_wind"]  # 湖邊—寶洞是山路：沒看過的只剩峭壁（給銀兩）
    walk_to(game, "cave")
    assert p.recent_sights[-1] != "sight_cliff"
    assert content.road_sights["sight_cliff"].text not in game.state.journal[0].lines


def test_the_road_sight_cap_counts_the_day_of_the_arrival(content, game):
    """下線補算跨過午夜：第 1 天 23:58 抵達的那一站，收穫算第 1 天（紀錄上寫的也是那一刻）。"""
    content.config.road_sight_chance = 1.0
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]  # 只剩烏鴉（心得 +1）
    game.advance(DAY - 300 - game.state.world.time)  # 第 1 天 23:55
    game.choose("move:lake")  # 走三分鐘，23:58 抵達
    game.advance(600)  # 第 2 天 00:05 才補算
    assert p.road_rewards_today == {"sight": [1, 1]}


def test_road_sight_rewards_start_over_the_next_game_day(content, game):
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    walk_to(game, "lake")
    game.state.world.time += DAY  # 隔天：紀錄是前一天的就當沒拿過
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    xinde = p.stats["xinde"]
    walk_to(game, "town")
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [2, 1]}
    assert _sight_rewards(game.state.journal[0]) == ["心得 +1"]


def test_a_road_sight_without_a_reward_never_counts_toward_the_day(content, game):
    content.config.road_sight_chance = 1.0
    p = game.state.player
    p.recent_sights = ["sight_crow", "sight_north_peddler"]  # 只剩起風
    walk_to(game, "lake")
    assert p.recent_sights[-1] == "sight_wind" and p.road_rewards_today == {}


def test_turning_back_at_once_brings_no_road_sight(content, game):
    """剛出發就掉頭回到剛離開的那一站（不花時間也不花體力）不擲見聞：跟路上小事不換段是同一條規則。"""
    content.config.road_sight_chance = 1.0
    p = game.state.player
    game.choose("move:lake")
    game.choose("road:back")
    game.advance(0)
    assert p.location == "town" and p.journey is None
    assert p.recent_sights == []
    texts = {sight.text for sight in content.road_sights.values()}
    assert not any(line in texts for entry in game.state.journal for line in entry.lines)
    walk_to(game, "lake")  # 真的走到另一站才有
    assert len(p.recent_sights) == 1


# ── 時間由外面傳入（線上架構設計第四節）──────────────────────


def test_the_engine_never_reads_the_wall_clock():
    """引擎不自己讀電腦時鐘：現在時間一律由外面傳進來（sync(now) 或明確的 now 參數）。"""
    import tianxia.bot
    import tianxia.engine
    import tianxia.sqlite_world
    import tianxia.world
    import tianxia.world_state

    for module in (tianxia.engine, tianxia.world, tianxia.bot, tianxia.world_state, tianxia.sqlite_world):
        assert not hasattr(module, "time"), module.__name__


def test_the_muster_closes_by_the_time_passed_to_sync(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.sync(1.0)
    game.choose("battle:join:guan")
    assert game._battle_status()[0].phase == "muster"
    game.sync(definition.muster_seconds + 1)
    assert game._battle_status()[0].phase == "active"


def test_a_loaded_game_starts_its_clock_at_the_last_sync(content, game):
    assert game.now == 0.0  # 新角色還沒同步過
    game.sync(5000.0)
    assert game.now == 5000.0
    assert Game(content, game.state, world=game.world).now == 5000.0


def test_the_training_button_shows_the_odds(game):
    """實機試玩發現的坑：新角色沒有武學時威力是 0、遊歷必敗，而落敗現在真的要付氣血與內傷
    的代價。按鈕上要先講清楚勝算（跟劇情戰的選項同一套慣例）。"""
    walk_to(game, "lake")
    fresh = next(o for o in game.options() if o.id == "act:train")
    assert "必敗" in fresh.label
    rules.learn_skill(game.state, game.content, "fist")
    armed = next(o for o in game.options() if o.id == "act:train")
    assert "穩勝" in armed.label


def test_the_training_button_skips_the_odds_when_asked(game):
    walk_to(game, "lake")
    option = next(o for o in game.options(odds=False) if o.id == "act:train")
    assert "水寇小隊" in option.label and "勝" not in option.label


def test_the_training_odds_quote_the_hardest_opponent(game):
    """寧可低估：多路對手時標籤拿最強的那個算，不要給過度樂觀的承諾。"""
    game.content.locations["lake"].enemies = ["thug", "boss"]  # 水寇小隊 5、翻江龍 200
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    option = next(o for o in game.options() if o.id == "act:train")
    assert "2 路對手" in option.label and "必敗" in option.label  # 翻江龍打不贏


def test_the_chronicle_lists_earlier_seasons_after_this_one(content, game):
    """線上架構設計 3.2：江湖史跨季保留。"""
    season = game.world.get_season()
    season.chronicle.append(Rumor(time=0, text="第一季的大事"))
    season.ended = True
    game.world.save_season(season)
    assert game.world.next_season(content, now=1.0)
    game.sync(2.0)
    text = game.chronicle_text()
    assert text.index("第 2 季（本季）") < text.index("### 第 1 季") < text.index("第一季的大事")


def test_the_round_narration_is_kept_with_the_round(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster), mock.patch.object(battle_instance, "narrate_round", return_value="一場惡戰。"):
        game._battle_status()
        game.choose("battle:act:safe")
    battle = game.world.get_battle()
    assert [r.narration for r in game.world.battle_rounds(battle.record_id)] == ["一場惡戰。"]


# ── 同伴也拿經驗（試玩回饋 FB-002）────────────────────────────


def _companion_on_the_team(game, exp=0):
    """在小鎮招到韓鐵（帶著出戰），再把他的經驗設成 exp；之後換回一般亂數，免得固定亂數影響走路時的世界推進。"""
    game.rng = FixedRandom(0.1)  # < 0.35：招募成功
    game.choose("act:recruit")
    assert game.state.player.team == ["mate"]
    game.world.update_companion("mate", lambda progress: setattr(progress, "exp", exp))
    game.rng = random.Random(0)


def test_a_won_training_fight_gives_every_fighter_the_exp(content, game):
    """戰報寫「經驗 +N（每人）」：帶著的同伴也真的拿到，照同一套規則升級，氣血上限跟著升。"""
    from tianxia import team

    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    _companion_on_the_team(game, exp=90)
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)
    msgs = game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝") and record.exp == 20
    assert game.state.player.member.exp == 20
    mate = game.world.get_companion("mate")  # 同伴進度存在全服共用的世界（資料庫），不是角色存檔
    assert (mate.level, mate.exp) == (2, 10)
    assert "韓鐵升到第 2 級！" in msgs and "韓鐵升到第 2 級！" in record.notes
    assert team.member_neili(content, mate)[1] == content.config.neili_base + 2 * content.config.neili_per_level
    assert "🧍 韓鐵　第2級" in game.status_text()


def test_a_drill_gives_every_fighter_the_exp_too(content, game):
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    _companion_on_the_team(game, exp=90)
    walk_to(game, "lake")
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.world.get_companion("mate").level == 2
    assert "韓鐵升到第 2 級！" in msgs
    assert "韓鐵升到第 2 級！" in game.state.journal[0].lines


# ── 指名求見（兩位以上大勢人物的地點，企劃者 2026-10-03 決定）──────────


def _hall(content, game, mate_fame=0, scholar_fame=0):
    """把小鎮變成兩位大勢人物的地點：韓鐵、書生（recruit_at 本來就是小鎮）都開深度對話。小鎮有交友事件（拜師）；
    福緣設成已領，交友不會先送福緣。"""
    for cid, fame in (("mate", mate_fame), ("scholar", scholar_fame)):
        content.characters[cid].deep_interaction = True
        content.characters[cid].audience_fame = fame
    game.state.player.fortune = True


def _labels(game):
    return {o.id: (o.label, o.enabled) for o in game.options()}


def test_a_place_with_two_figures_offers_one_audience_option(content, game):
    _hall(content, game)
    assert ids(game) == ["act:explore", "act:socialize", "act:call", "act:recruit", "move:lake", "act:rest"]
    assert _labels(game)["act:call"] == ("求見", True)


def test_a_place_with_two_figures_and_no_socialize_events_has_no_socialize_option(content, game):
    for cid in ("mate", "scholar"):
        ch = content.characters[cid]
        ch.kind, ch.recruit_at, ch.talk_at, ch.deep_interaction = "locked", None, "cave", True
    game.state.player.location = "cave"  # 寶洞沒有交友事件
    assert "act:socialize" not in ids(game) and "act:call" in ids(game)


def test_socializing_where_two_figures_stand_never_opens_a_dialogue(content, game):
    _hall(content, game)
    assert not game.socialize_starts_dialogue()
    assert game.dialogue_request("act:socialize") is None
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("交友不該開口對話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "join"  # 小鎮的交友事件（拜師）照常發生
    assert game.state.player.pending_companion is None
    game.state.pending_event = None
    with mock.patch("tianxia.engine.pick_event", return_value=None):
        msgs = game.choose("act:socialize")
    assert msgs == ["你四處結交了一番，沒遇上什麼事；想拜會此地的人物，請按「求見」指名。"]


def test_the_audience_list_names_each_figure_and_why_some_cannot_be_seen(content, game):
    _hall(content, game, mate_fame=10)
    game.choose("act:call")
    assert game.state.player.picking_audience
    assert [(o.id, o.label, o.enabled) for o in game.options()] == [
        ("call:mate", "韓鐵（名望還差 10）", True),  # 求見一直都在（武學與成長設計 9.1）；被打發是一定的，寫真正的差距
        ("call:scholar", "書生（體力 5・今天還能談 3/3 輪）", True),
        ("call:back", "返回", True),
    ]
    scene = game.scene_text()
    assert scene.startswith("**求見**") and "每位人物每天最多談 3 輪，各算各的" in scene
    assert game.state.journal[0].title == "求見・小鎮"
    assert game.state.player.stamina == content.config.stamina_max  # 打開名單不花體力


def test_a_prior_meeting_opens_the_door_in_the_audience_list(content, game):
    _hall(content, game, mate_fame=10)
    game.state.player.flags.add("結識:mate")
    game.choose("act:call")
    assert _labels(game)["call:mate"] == ("韓鐵（體力 5・今天還能談 3/3 輪）", True)


def test_calling_on_a_figure_starts_the_dialogue_with_that_figure(content, game):
    _hall(content, game)
    game.choose("act:call")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN), \
            mock.patch("tianxia.engine.note_action", return_value=[]) as noted:
        msgs = game.choose("call:scholar")
    assert msgs == ["他點了點頭。"]
    p = game.state.player
    assert p.pending_companion == "scholar" and not p.picking_audience
    assert p.stamina == content.config.stamina_max - content.config.action_cost["socialize"]
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]
    assert game.state.journal[0].title == "求見・書生"
    noted.assert_called_once()
    assert noted.call_args.args[3] == "socialize"  # 指名求見算一次交友（新手引導、任務）


def test_the_daily_limit_counts_per_figure(content, game):
    """每位人物每天最多談 3 輪，各算各的：跟書生談滿了，韓鐵照樣見得到。"""
    _hall(content, game)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:call")
        game.choose("call:scholar")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
    assert msgs[-1] == "天色已晚，書生起身送客，改日再敘。"
    game.choose("act:call")
    labels = _labels(game)
    assert labels["call:scholar"] == ("書生（今天已經談滿 3 輪，明天再來）", False)
    assert labels["call:mate"] == ("韓鐵（體力 5・今天還能談 3/3 輪）", True)
    assert game.choose("call:scholar") == ["（此刻無法這麼做。）"]
    game.state.world.time += DAY  # 隔天重算
    assert _labels(game)["call:scholar"][1]


def test_an_unavailable_audience_refunds_the_cost_and_closes_the_list(content, game):
    _hall(content, game)
    game.choose("act:call")
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("call:scholar")
    assert msgs == ["書生似乎無心多談，你只好先行告辭。"]
    p = game.state.player
    assert p.stamina == content.config.stamina_max
    assert p.pending_companion is None and not p.picking_audience


def test_going_back_always_works_and_closes_the_list(content, game):
    _hall(content, game)
    game.choose("act:call")
    game.state.player.stamina = 0
    labels = _labels(game)
    assert labels["call:scholar"] == ("書生（體力 5・今天還能談 3/3 輪）", False)  # 體力不夠
    assert labels["call:back"] == ("返回", True)  # 永遠有路可退，不會卡死
    assert game.choose("call:back") == ["你收回名帖，暫且不求見了。"]
    assert not game.state.player.picking_audience
    assert "act:call" in ids(game)
    assert game.state.journal[0].title == "收回名帖"


def test_you_cannot_travel_or_seclude_while_picking_whom_to_call_on(content, game):
    _hall(content, game)
    game.choose("act:call")
    assert game.travel_refusal("lake") == "求見中，先返回才能安排前往"
    assert game.travel("lake") == ["（求見中，先返回才能安排前往。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]


def test_dialogue_request_for_a_call_is_the_generic_opening(content, game):
    _hall(content, game, mate_fame=10)
    game.choose("act:call")
    req = game.dialogue_request("call:scholar")
    assert (req.option_id, req.companion_id, req.player_action) == (
        "call:scholar", "scholar", companion_agent.GENERIC_OPENING,
    )
    assert game.dialogue_request("call:mate") is None  # 見不到：被打發，不叫模型
    assert game.dialogue_request("call:back") is None


def test_choose_applies_a_prepared_audience_without_calling_the_model(content, game):
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=NEXT_TURN)
    with _no_model():
        msgs = game.choose("call:scholar", prepared=prepared)
    assert msgs == ["他笑了笑。"]
    assert game.state.player.pending_companion == "scholar"


def test_a_prepared_failure_for_an_audience_refunds_the_cost(content, game):
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=None)
    with _no_model():
        msgs = game.choose("call:scholar", prepared=prepared)
    assert msgs == ["書生似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == content.config.stamina_max
    assert not game.state.player.picking_audience


def test_calling_on_a_figure_never_delivers_the_fortune(content, game):
    """福緣到期也一樣：求見是指名拜會，直接開口對話，福緣留給交友或之後自己到。"""
    _hall(content, game)
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min
    game.choose("act:call")
    assert game.dialogue_request("call:scholar") is not None
    with mock.patch.object(companion_agent, "generate_turn", return_value=NEXT_TURN):
        game.choose("call:scholar")
    assert game.state.player.pending_companion == "scholar"
    assert not game.state.player.fortune


def test_a_prepared_audience_is_refused_once_the_list_is_closed(content, game):
    """生成的那段時間另一個分頁按了「返回」：call:<人物> 已經不在選單上，鎖外生成好的這輪不套用、也不扣體力。"""
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=NEXT_TURN)
    game.choose("call:back")
    before = game.state.player.stamina
    with _no_model():
        assert game.choose("call:scholar", prepared=prepared) == ["（此刻無法這麼做。）"]
    assert game.state.player.pending_companion is None
    assert game.state.player.stamina == before


def test_a_stale_audience_list_is_closed_where_two_figures_no_longer_stand(content, game):
    game.state.player.picking_audience = True  # 夾具的小鎮沒有大勢人物：例如內容改版後讀進來的舊存檔
    reloaded = Game(content, game.state, world=game.world)
    assert not reloaded.state.player.picking_audience


# ── 求見一直都在，門檻不夠就打發（武學與成長設計 9.1）──────────


def _stand_by_one_figure(content, game, fame=30):
    """小鎮只剩韓鐵一位大勢人物（夾具裡其他人都沒開深度對話），名望門檻 fame；他有一句打發話。福緣設成已領。"""
    ch = _figure(content, fame=fame)
    ch.brush_off = ["閒雜人等退下。"]
    game.state.player.fortune = True
    return "mate"


def _guan_figure(content, character_id="mate"):
    """把這位人物掛成官軍的大勢人物（階級抵門檻只認人物表上的陣營）。"""
    _training_factions(content)
    content.figures["f_test"] = FigureDef(
        id="f_test", character=character_id, name=content.characters[character_id].name, faction="guan",
        location="town", squad=next(iter(content.squads)),
    )


def _season_one_on(content, game):
    """第一季的規則開著（開關開、這一季開季時也蓋了章）：晉升只有這時候才有，「再升一階」的提示才算數。"""
    content.config.season_one = True
    game.state.world.season_one = True


def _promotion(content, faction="guan", rank=2):
    """這個陣營升到第 rank 階的晉升定義（hint 只在真的有下一階可升時才提「再升一階」）。"""
    content.promotions.append(PromotionDef(
        faction=faction, rank=rank, location="town", event_main="x", summons_text="x", closing="x",
    ))


def test_the_audience_button_is_always_there_and_brushes_off_for_free(content, game):
    cid = _stand_by_one_figure(content, game)
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    assert option.enabled and option.label == "求見韓鐵（名望還差 30）"
    game.state.player.stats["fame"] = 12
    assert next(o for o in game.options() if o.id == f"call:{cid}").label == "求見韓鐵（名望還差 18）"
    game.state.player.stats["fame"] = 0
    stamina, affinity = game.state.player.stamina, game.state.player.affinities.get(cid, 0)
    msgs = game.choose(f"call:{cid}")
    assert any("閒雜人等退下。" in m and "名望還差 30" in m for m in msgs)
    assert game.state.player.stamina == stamina and game.state.player.affinities.get(cid, 0) == affinity
    assert game.state.player.pending_companion is None
    assert game.state.journal[0].title == "求見・韓鐵"  # 吃閉門羹也寫進江湖紀錄


def test_a_brush_off_does_not_ask_the_model(content, game):
    cid = _stand_by_one_figure(content, game)
    assert game.dialogue_request(f"call:{cid}") is None
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("被打發的不該叫模型")):
        game.choose(f"call:{cid}")


def test_a_brush_off_without_written_lines_uses_the_general_one(content, game):
    cid = _stand_by_one_figure(content, game)
    content.characters[cid].brush_off = []
    assert game.choose(f"call:{cid}") == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 30）"]


def test_a_brush_off_picks_one_of_the_written_lines(content, game):
    cid = _stand_by_one_figure(content, game)
    content.characters[cid].brush_off = ["一", "二", "三"]
    seen = set()
    for _ in range(40):
        seen.add(game.choose(f"call:{cid}")[0].partition("（")[0])
    assert seen == {"一", "二", "三"}


def test_the_brush_off_says_how_far_short_you_are(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    game.state.player.stats["fame"] = 12
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18）"]  # 散人只看名望
    game.state.player.faction = "huang"  # 敵對陣營：階級不抵，也不指望在他那邊升階
    game.state.player.rank = 2
    _promotion(content, "huang", 3)
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18）"]


def test_the_hint_names_the_faction_way_up_when_one_more_step_would_close_the_gap(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    _season_one_on(content, game)
    _promotion(content, "guan", 2)  # 官軍有第 2 階可升
    p = game.state.player
    p.faction, p.rank = "guan", 0  # 投靠了、還沒晉升：門檻 30，升一階抵 5
    p.stats["fame"] = 25  # 差 5：剛好一階補得上
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 5，或在官軍再升一階）"]
    p.stats["fame"] = 26
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 4，或在官軍再升一階）"]


def test_the_hint_is_left_out_when_no_next_promotion_is_written(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    _season_one_on(content, game)
    p = game.state.player
    p.faction, p.rank = "guan", 0
    p.stats["fame"] = 26
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 4）"]  # 官軍的晉升表上沒有第 2 階
    _promotion(content, "guan", 2)
    p.rank = 2  # 已經升過第 2 階，下一階（3）沒寫
    p.stats["fame"] = 22  # 門檻 30 - 5 = 25，差 3
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 3）"]


def test_the_hint_is_left_out_when_one_more_step_cannot_close_the_gap(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    _season_one_on(content, game)
    _promotion(content, "guan", 2)
    p = game.state.player
    p.faction, p.rank = "guan", 0
    p.stats["fame"] = 12  # 差 18，一階只抵 5
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18）"]
    content.config.audience_rank_discount = 18  # 抵得夠大的話就補得上
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18，或在官軍再升一階）"]


def test_the_hint_is_left_out_while_the_season_one_rules_are_off(content, game):
    """規則沒開（beta 那一季）沒有晉升這回事，「再升一階」不能寫：其他條件都成立也一樣。"""
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    _promotion(content, "guan", 2)
    p = game.state.player
    p.faction, p.rank = "guan", 0
    p.stats["fame"] = 26
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 4）"]
    _season_one_on(content, game)
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 4，或在官軍再升一階）"]


def test_enough_fame_turns_the_audience_button_into_a_real_audience(content, game):
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    assert (option.label, option.enabled) == ("求見韓鐵（體力 5）", True)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose(f"call:{cid}")
    p = game.state.player
    assert p.pending_companion == cid
    assert p.stamina == content.config.stamina_max - content.config.action_cost["socialize"]


def test_rank_in_the_figures_faction_opens_the_door(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    game.state.player.stats["fame"] = 24
    game.state.player.faction, game.state.player.rank = "guan", 2  # 晉升過一次：30 - 5 = 25
    assert not game.can_meet_figure(cid)
    game.state.player.stats["fame"] = 25  # 剛好到
    assert game.can_meet_figure(cid)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose(f"call:{cid}")
    assert game.state.player.pending_companion == cid
    game.choose("talk:leave")
    game.state.player.stats["fame"], game.state.player.rank = 20, 3  # 兩次：30 - 10 = 20
    assert game.can_meet_figure(cid)
    game.state.player.rank = 0  # 投靠了還沒晉升：一點都不抵
    assert not game.can_meet_figure(cid)


def test_can_meet_figure_follows_fame_or_a_prior_meeting(content, game):
    cid = _stand_by_one_figure(content, game)
    assert not game.can_meet_figure(cid)
    game.state.player.flags.add(f"結識:{cid}")
    assert game.can_meet_figure(cid)
    game.state.player.flags.discard(f"結識:{cid}")
    game.state.player.stats["fame"] = 30
    assert game.can_meet_figure(cid)


def test_a_figure_who_turned_you_away_after_a_defeat_stays_shut(content, game):
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    with mock.patch.object(Game, "_snubbed_character", return_value=True):
        option = next(o for o in game.options() if o.id == f"call:{cid}")
        assert option.label == "求見韓鐵（剛吃了敗仗，閉門不見）" and not option.enabled


def test_the_audience_button_stays_but_greys_out_once_the_day_is_used_up(content, game):
    """每天 3 輪談滿後，單人地點的求見不消失：灰掉、寫跟求見名單同一句（設計 9.1：求見一直都在）。"""
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    game.state.player.talks_today[cid] = [rules.current_day(game.state), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    assert (option.label, option.enabled) == ("求見韓鐵（今天已經談滿 3 輪，明天再來）", False)
    assert game.choose(f"call:{cid}") == ["（此刻無法這麼做。）"]
    game.state.world.time += DAY  # 隔天重算
    assert next(o for o in game.options() if o.id == f"call:{cid}").enabled


def test_two_figures_still_share_one_audience_option_and_a_brush_off_closes_the_list(content, game):
    _hall(content, game, mate_fame=10)
    assert "call:mate" not in ids(game) and "act:call" in ids(game)  # 兩位以上：求見先打開名單，不直接列人
    game.choose("act:call")
    stamina = game.state.player.stamina
    msgs = game.choose("call:mate")
    assert msgs == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 10）"]
    assert game.state.player.stamina == stamina and not game.state.player.picking_audience
    assert game.state.player.pending_companion is None


def test_the_brush_off_line_is_only_picked_when_it_is_used(content, game):
    """交友先抽地點事件，抽到了就不用打發話：不白花一次亂數（打發話是惰性算的）。小鎮有交友事件（拜師），韓鐵見不到。"""
    _stand_by_one_figure(content, game)
    with mock.patch.object(Game, "_brush_off", side_effect=AssertionError("有事件時不該挑打發話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "join"
    game.state.pending_event = None
    with mock.patch("tianxia.engine.pick_event", return_value=None),             mock.patch.object(Game, "_brush_off", return_value=["打發。"]) as brushed:
        assert game.choose("act:socialize") == ["打發。"]
    brushed.assert_called_once()


def test_socializing_with_a_figure_you_cannot_meet_uses_the_same_brush_off(content, game):
    cid = _stand_by_one_figure(content, game)
    with mock.patch("tianxia.engine.pick_event", return_value=None),             mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("被打發的不該叫模型")):
        msgs = game.choose("act:socialize")
    assert msgs == ["閒雜人等退下。（名望還差 30）"]
    assert game.state.player.pending_companion is None


# ── 主畫面的走法切換（步行／趕路／疾行）──────────────────────


def _move_to_lake(game):
    return next(o for o in game.options() if o.id.startswith("move:lake"))


def test_the_menu_walks_by_default(game):
    assert game.move_mode == "walk"
    move = _move_to_lake(game)
    assert (move.id, move.label, move.enabled) == ("move:lake", "前往 湖邊（步行約 3 分鐘）", True)


def test_hurrying_from_the_menu_shows_and_spends_its_stamina(game):
    game.set_move_mode("hurry")
    move = _move_to_lake(game)
    assert (move.id, move.label, move.enabled) == ("move:lake:hurry", "前往 湖邊（趕路約 2 分鐘・體力 3）", True)
    game.choose("move:lake:hurry")
    p = game.state.player
    assert p.journey.mode == "hurry" and p.journey.arrive_at == [pytest.approx(90.0)]
    assert p.stamina == 147
    assert (game.state.journal[0].title, game.state.journal[0].tag) == ("前往 湖邊", "趕路約 2 分鐘")


def test_dashing_from_the_menu_arrives_at_once(game):
    game.set_move_mode("dash")
    assert _move_to_lake(game).label == "前往 湖邊（疾行立刻到・體力 6）"
    game.choose("move:lake:dash")
    p = game.state.player
    assert p.location == "lake" and p.journey is None and p.stamina == 144


def test_a_mode_you_cannot_afford_disables_the_move_and_says_why(game):
    game.set_move_mode("dash")
    game.state.player.stamina = 5
    move = _move_to_lake(game)
    assert (move.label, move.enabled) == ("前往 湖邊（疾行・體力不足，要 6）", False)
    assert game.choose("move:lake:dash") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town" and game.state.player.stamina == 5


def test_the_move_mode_changes_labels_not_the_number_of_options(game):
    walking = ids(game)
    for mode in ("hurry", "dash"):
        game.set_move_mode(mode)
        assert len(ids(game)) == len(walking)
        assert f"move:lake:{mode}" in ids(game) and "move:lake" not in ids(game)
    assert game.choose("move:lake") == ["（此刻無法這麼做。）"]  # 選單上已經不是步行：舊按鈕的 id 不算數


def test_an_unknown_mode_falls_back_to_walking(game):
    game.set_move_mode("fly")
    assert game.move_mode == "walk" and "move:lake" in ids(game)


def test_the_move_mode_is_screen_state_and_never_saved(content, game):
    """走法不存進存檔（企劃者決定），讀存檔開的 Game 一律從步行開始；網頁上每個請求的走法由 server.py 逐次設定。"""
    game.set_move_mode("hurry")
    assert "move_mode" not in game.state.model_dump_json()
    assert Game(content, game.state, world=game.world).move_mode == "walk"


# ── 第一季濃縮版的總開關（計畫 T2「總開關與週末設定」）──────────────────


def test_old_season_not_replayed_when_switch_turns_on(content, world):
    """QA 要的保險：開關關著、季長 14 天時開的季，換成週末設定之後照它自己的章走——不會因為季長變成 2.5 天
    就一口氣收掉；管理者收季、開下一季之後，新的一季才照週末設定。"""
    install_season_one(content)  # 有時刻表、沒有虛擬玩家（推過門檻也會收季，這裡只看時間與開關）
    content.config.admins = ["管理者"]
    content.config.season_one, content.config.season_days = False, 14
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.sync(0.0)
    admin.advance(5 * DAY)

    content.config.season_one, content.config.season_days = True, 2.5  # 換成週末設定再同步
    admin.sync(60.0)
    season = world.get_season()
    assert not season.ended and season.time >= 5 * DAY
    assert (season.season_one, season.length_days) == (False, 14)

    assert season.timeline == {} and season.hooked_week == 0  # 舊季不跑時刻表，也不補算
    assert "calendar" not in admin.status_data()

    admin.admin_end_season(now=120.0)
    admin.admin_next_season(now=180.0)
    season = world.get_season()
    assert (season.season_one, season.length_days) == (True, 2.5)
    admin.sync(180.0 + calendar.cal_hour_seconds(content))
    assert list(world.get_season().timeline) == ["uprising"]  # 新的一季才照季曆跑
    assert admin.status_data()["calendar"]["week"] == 1
    past, current = admin.chronicle_text().split("### 第 1 季")[::-1][:2]  # 本季的時間寫季曆，上一季照舊寫天數
    assert "第 1 週・週一 00:00　張角率三十六方同時起義。" in current and "第6天　賽季落幕" in past


def test_an_unstamped_season_is_not_cut_short_by_the_weekend_profile(content, world):
    """FB-037：沒蓋章的舊季（T2 之前開的，例如試玩伺服器那一季）一套週末設定，不會因為設定的季長是 2.5 天，
    第 4 天就自己收掉，狀態列也還是寫「共 14 天」。蓋了章的季才照章（見 test_world 與 test_status_shows_calendar…）。"""
    install_season_one(content)  # 設定是週末的：開、2.5 天
    game = Game.new(content, "沈浪", rng=random.Random(1), world=world)
    game.sync(0.0)
    world.mutate_season(lambda s: (setattr(s, "season_one", False), setattr(s, "length_days", None), s.schedule.clear()))
    game.sync(1.0)  # 拉回改過章的那一份
    game.advance(4 * DAY)
    season = world.get_season()
    assert not season.ended and season.time >= 4 * DAY
    assert world.season_phase() == "running"
    assert game.status_data()["season_days"] == 14
    assert "共 14 天" in game.status_text()
    assert "calendar" not in game.status_data()  # 時刻表照舊不跑
    game.advance(11 * DAY)  # 開季時就是 14 天
    assert world.get_season().ended


def test_status_shows_calendar_and_next_event(content, world):
    """狀態列的季曆與下一件大事：季曆時刻 at（第N週・週X HH:MM）加上倒數（真實秒，FB-062）；決戰照排定的時間算。
    舊的 day／clock／season_days 照舊在。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    d = game.status_data()
    assert d["calendar"] == {"week": 1, "weekday": 0, "clock": "00:00", "weeks": 12, "text": "第 1 週・週一 00:00"}
    assert d["next_event"] == {"title": "張曼成攻殺南陽太守", "at": "第 3 週・週一 00:00", "in_seconds": 36000}  # 起義就在此刻；下一件在第 3 週
    assert (d["day"], d["clock"], d["season_days"]) == (1, "00:00", 2.5)

    tuesday = calendar.week_start(3, content) + (DAY + 21 * HOUR + 40 * 60) / 33.6
    game.advance(tuesday)
    d = game.status_data()
    assert d["calendar"] == {"week": 3, "weekday": 1, "clock": "21:40", "weeks": 12, "text": "第 3 週・週二 21:40"}
    assert d["next_event"] == {"title": "波才大敗朱儁", "at": "第 4 週・週一 00:00", "in_seconds": round(calendar.week_start(4, content) - tuesday)}
    assert "第 3 週・週二 21:40" in game.status_text()

    game.advance(calendar.week_start(5, content) - tuesday)
    showdown = game.state.world.schedule["changshe_fire"]
    assert game.status_data()["next_event"] == {"title": "長社火攻", "at": calendar.stamp_text(showdown, content, game.state.world), "in_seconds": round(showdown - game.state.world.time)}
    content.config.time_scale = 2  # 1 時等於現實 2 秒：倒數是現實秒
    assert game.status_data()["next_event"]["in_seconds"] == round((showdown - game.state.world.time) / 2)


def test_next_event_time_is_written_like_the_status_bars_second_line(content, world):
    """每一處季曆時刻都是同一種寫法「第 N 週・週X HH:MM」（N 前後有空格，PM 定）：下一件的 at 等到那一刻真的到了，
    就跟狀態列第二行（日期那一行）寫的一字不差；江湖史、江湖紀錄、傳聞也一樣。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    d = game.status_data()
    at = d["next_event"]["at"]
    assert re.fullmatch(r"第 \d+ 週・週[一二三四五六日] \d\d:\d\d", at)
    game.advance(d["next_event"]["in_seconds"] * content.config.time_scale)  # 等到下一件的那一刻
    assert game.status_data()["calendar"]["text"] == at
    assert at in game.status_text()
    assert f"{at}　" in game.chronicle_text()  # 那一件大事寫進江湖史，時刻的寫法跟狀態列一樣


def test_open_season_restamps_with_current_profile(content, world):
    """第一次啟動忘了設 TIANXIA_PROFILE：籌備中的季種下時蓋的是「關」。換成週末設定重開、管理者開季時重新蓋章，
    這一季照週末設定跑（開季前時間是 0、什麼都還沒跑，重蓋是安全的）。"""
    install_season_one(content)
    content.config.admins = ["管理者"]
    content.config.auto_open_first_season = False
    content.config.season_one, content.config.season_days = False, 14  # 沒設 profile 的第一次啟動
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    assert world.season_phase() == "preparing"
    assert (world.get_season().season_one, world.get_season().length_days) == (False, 14)

    content.config.season_one, content.config.season_days = True, 2.5  # 設好 weekend 重開
    admin.admin_open_season(now=100.0)
    season = world.get_season()
    assert (season.season_one, season.length_days, season.time) == (True, 2.5, 0)
    assert season.schedule["finale"] == pytest.approx(2.5 * DAY)  # 決戰與季末的預設時間也一起補上
    admin.sync(100.0 + calendar.cal_hour_seconds(content))
    assert list(world.get_season().timeline) == ["uprising"]
    assert admin.status_data()["calendar"]["week"] == 1



def test_week_one_is_settled_the_moment_a_stamped_season_opens(content, world):
    """FB-040：開季那一刻（世界秒 0）就結算第 1 週週一 00:00 的大事，不必等到第一個曆時交界：時間軸、傳聞、江湖史、
    公告卡都在，狀態列的下一件是第 2 週那件；再推進一個曆時不會重複結算。下一季開出來也一樣。"""
    install_season_one(content)
    content.config.admins = ["管理者"]
    content.config.auto_open_first_season = False
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    assert world.season_phase() == "preparing"
    admin.admin_open_season(now=100.0)  # 沒有推進任何時間

    season = world.get_season()
    assert season.time == 0 and list(season.timeline) == ["uprising"] and season.timeline["uprising"].time == 0
    assert season.hooked_week == 1
    assert "第 1 週・週一 00:00　三十六方同日起事。" in admin.rumors_text()
    assert "第 1 週・週一 00:00　張角率三十六方同時起義。" in admin.chronicle_text()
    assert [b.split("**")[1] for b in admin.bulletin()] == ["三十六方起義"]
    assert admin.status_data()["next_event"]["title"] == "張曼成攻殺南陽太守"  # 第一件已經結算，倒數指向下一件

    admin.sync(100.0 + calendar.cal_hour_seconds(content))  # 跨過第一個曆時：不會再結算一次
    assert list(world.get_season().timeline) == ["uprising"]
    assert admin.chronicle_text().count("張角率三十六方同時起義。") == 1
    assert admin.rumors_text().count("三十六方同日起事。") == 1

    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)  # 新的一季：開季那一刻照樣結算
    season = world.get_season()
    assert season.time == 0 and list(season.timeline) == ["uprising"] and season.hooked_week == 1
    assert "第 1 週・週一 00:00　張角率三十六方同時起義。" in admin.chronicle_text().split("### 第 1 季")[0]


def test_opening_a_season_with_the_switch_off_settles_nothing(content, world):
    install_season_one(content)
    content.config.admins = ["管理者"]
    content.config.auto_open_first_season = False
    content.config.season_one = False
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_open_season(now=100.0)
    season = world.get_season()
    assert season.timeline == {} and season.hooked_week == 0 and "calendar" not in admin.status_data()


def _big_event_entries(game) -> list:
    return [e for e in game.state.journal if e.title == "江湖大事"]


def _announced(content, world, *ids) -> list[str]:
    """這幾件大事照時間先後、每行前面標季曆時間的樣子（江湖紀錄裡一則「江湖大事」該有的三行）。"""
    season = world.get_season()
    return [f"{calendar.stamp_text(season.timeline[i].time, content, season)}　{season.timeline[i].text}" for i in ids]


def test_everyone_gets_the_seasons_big_events_not_just_whoever_advanced_the_clock(content, world):
    """FB-038：管理者快轉推過三件大事，另一個在線、這段時間沒有請求的人同步一次，江湖紀錄裡就有一則「江湖大事」，
    三行、照時間排、每行前面標季曆時間；再同步不重複。推進的那個人自己也只有一則（不是兩則）。"""
    install_season_one(content)
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    zi = Game.new(content, "子", rng=random.Random(2), world=world)
    admin.sync(0.0)
    zi.sync(0.0)
    assert _big_event_entries(zi) == []

    admin.advance(calendar.week_start(4, content) + calendar.cal_hour_seconds(content))  # 起義、張曼成、波才
    ids = ["uprising", "zhangmancheng", "bocai"]
    assert list(world.get_season().timeline) == ids
    expected = _announced(content, world, *ids)
    assert len(_big_event_entries(admin)) == 1 and _big_event_entries(admin)[0].lines == expected

    zi.sync(5.0)
    assert len(_big_event_entries(zi)) == 1 and _big_event_entries(zi)[0].lines == expected
    assert [line.split("　")[0] for line in expected] == ["第 1 週・週一 01:00", "第 3 週・週一 00:00", "第 4 週・週一 00:00"]
    zi.sync(10.0)
    admin.sync(10.0)
    assert len(_big_event_entries(zi)) == 1 and len(_big_event_entries(admin)) == 1  # 再同步不重複


def test_one_new_big_event_is_one_line_in_the_journal_and_never_twice(content, world):
    """每次同步補到的只有還沒看過的：一件就是一則（標籤是公告全文）；推進的人與在線的人都只有一則。"""
    install_season_one(content)
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    zi = Game.new(content, "子", rng=random.Random(2), world=world)
    admin.sync(0.0)
    zi.sync(0.0)
    admin.advance(calendar.cal_hour_seconds(content))
    for game in (admin, zi):
        game.sync(5.0)
        (entry,) = _big_event_entries(game)
        assert entry.tag == "三十六方同日起事。" and entry.lines == []
    assert admin.state.player.events_seen == ["uprising"] == zi.state.player.events_seen
    admin.advance(calendar.week_start(3, content))  # 張曼成：只補新的一件
    zi.sync(10.0)
    assert [e.tag for e in _big_event_entries(zi)] == [world.get_season().timeline["zhangmancheng"].text, "三十六方同日起事。"]
    assert len(_big_event_entries(admin)) == 2


def test_a_character_who_was_away_or_made_mid_season_catches_up_on_this_seasons_events(content, world):
    """離線（角色只在資料庫裡）的人回來第一次同步補到；這一季中途才建立的角色也補到這一季已經發生的。"""
    install_season_one(content)
    away = Game.new(content, "丙", rng=random.Random(3), world=world)
    away.sync(0.0)
    open_characters().save(away.state)
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.sync(0.0)
    admin.advance(calendar.week_start(3, content) + calendar.cal_hour_seconds(content))  # 起義、張曼成
    expected = _announced(content, world, "uprising", "zhangmancheng")

    back = Game(content, open_characters().load("丙"), rng=random.Random(3), world=world)
    assert _big_event_entries(back) == []  # 讀回來還沒同步：還沒補
    back.sync(5.0)
    assert [e.lines for e in _big_event_entries(back)] == [expected]
    late = Game.new(content, "丁", rng=random.Random(4), world=world)  # 這一季中途才建立
    late.sync(6.0)
    assert [e.lines for e in _big_event_entries(late)] == [expected]
    back.sync(7.0)
    assert len(_big_event_entries(back)) == 1


def test_the_big_event_settled_at_the_opening_reaches_everyone_too(content, world):
    """FB-040 與 FB-038 合起來：管理者開季那一下結算的第 1 週大事，開季的人與其他人同步時都補到，時間寫週一 00:00。"""
    install_season_one(content)
    content.config.admins = ["管理者"]
    content.config.auto_open_first_season = False
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    zi = Game.new(content, "子", rng=random.Random(2), world=world)
    admin.admin_open_season(now=100.0)
    zi.sync(101.0)
    for game in (admin, zi):
        (entry,) = _big_event_entries(game)
        assert (entry.tag, entry.time) == ("三十六方同日起事。", 0)
    assert "剛剛　第 1 週・週一 00:00" in zi.latest_entry_html()


def test_skipped_big_events_are_not_delivered(content, world):
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.state.world.figures["zhangmancheng"] = FigureState(status="retired")
    game.advance(calendar.week_start(7, content) + calendar.cal_hour_seconds(content))
    assert game.state.world.timeline["qinjie"].key == "skip"
    lines = [line for e in _big_event_entries(game) for line in e.lines]
    assert not any("秦頡" in line for line in lines) and "qinjie" not in game.state.player.events_seen


def test_no_big_events_are_delivered_with_the_switch_off(content, world):
    install_season_one(content)
    zi = Game.new(content, "子", rng=random.Random(2), world=world)
    zi.sync(0.0)
    zi.advance(calendar.week_start(3, content))
    assert len(_big_event_entries(zi)) == 1
    content.config.season_one = False  # 開關關著：就算這一季蓋過章，什麼也不補
    other = Game.new(content, "乙", rng=random.Random(5), world=world)
    other.sync(5.0)
    assert _big_event_entries(other) == [] and other.state.player.events_seen == []


def test_big_events_start_over_with_the_new_season(content, world):
    """看過的大事 id 每季重來：新的一季開季那一下結算的第 1 週大事，上一季看過的人也照樣收得到。"""
    install_season_one(content)
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    zi = Game.new(content, "子", rng=random.Random(2), world=world)
    admin.sync(0.0)
    zi.sync(0.0)
    admin.advance(calendar.cal_hour_seconds(content))
    zi.sync(5.0)
    assert zi.state.player.events_seen == ["uprising"]
    admin.admin_end_season(now=10.0)
    admin.admin_next_season(now=20.0)
    zi.sync(30.0)
    assert zi.state.player.events_seen == ["uprising"] and len(_big_event_entries(zi)) == 1  # 新角色的紀錄，新的一季
    assert len(_big_event_entries(admin)) == 1 and admin.state.player.events_seen == ["uprising"]


def test_skipped_events_stay_off_the_bulletin(content, world):
    """張曼成已經退場：第 7 週秦頡那件記成跳過，公告卡只有同一週的盧植圍廣宗。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.state.world.figures["zhangmancheng"] = FigureState(status="retired")
    game.advance(calendar.week_start(7, content) + calendar.cal_hour_seconds(content))
    assert game.state.world.timeline["qinjie"].key == "skip"
    assert [b.split("**")[1] for b in game.bulletin()] == ["盧植圍廣宗"]


def test_timestamps_read_like_the_calendar_when_the_season_is_season_one(content, world):
    """第一季（開關開著、這一季也蓋了章）：江湖紀錄（含「剛剛」）、江湖史、傳聞、戰報的時間都寫成季曆。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.sync(0.0)
    game.sync(calendar.cal_hour_seconds(content))  # 第 1 週週一 01:00：三十六方起義
    assert "剛剛　第 1 週・週一 01:00" in game.latest_entry_html()
    assert "第 1 週・週一 01:00　張角率三十六方同時起義。" in game.chronicle_text()
    assert "第 1 週・週一 01:00　三十六方同日起事。" in game.rumors_text()
    assert "第 1 週・週一 00:00" in game.journal_html(1, 5)  # 開季那一則
    assert "第 1 週・週一 01:00" in atlas.header_text(game.state, content)


def test_timestamps_are_unchanged_with_the_switch_off(game):
    game.advance(HOUR + 5 * 60)
    game.state.world.chronicle.append(Rumor(time=game.state.world.time, text="測試大事。"))
    game.notice("測試")
    assert "剛剛　第1天 01:05" in game.latest_entry_html()
    assert "第1天　測試大事。" in game.chronicle_text()
    assert "第1天 01:05" in atlas.header_text(game.state, game.content)


# ── 地點描寫隨世界旗標換版（計畫 T8：宛城的 desc_when）──────────────────────


def test_a_location_description_follows_the_first_matching_world_flag(content, game):
    """Location.desc_when：照順序第一個成立的世界旗標勝出；都不成立時是原本的描寫。"""
    from tianxia.models import LocationText

    town = content.locations["town"]
    base = town.description
    town.desc_when = [LocationText(world_flag="fallen", text="城頭換了旗。"), LocationText(world_flag="held", text="城門緊閉。")]
    assert base in game.location_text()
    game.state.world.flags.add("held")
    assert "城門緊閉。" in game.location_text() and base not in game.location_text()
    game.state.world.flags.add("fallen")  # 排在前面的勝出
    assert "城頭換了旗。" in game.location_text() and "城門緊閉。" not in game.location_text()


# ── 三場大戲（計畫 T8）：照時刻表開集結、收場的結果餵給時刻表 ────────────────────


def _showdown_game(content, world, name="沈浪", faction="guan"):
    """第一季內容＋三筆時刻表決戰（北區打，小鎮就在北區）＋陣營；第 3、4 週的擲骰先記成跳過，戰線停在開季的數字
    （潁川 40、南陽 35），起點才算得準。回傳站在 faction 的 Game（現實時間 0）。"""
    from conftest import install_showdowns
    from tianxia.state import TimelineResult

    if not content.config.season_one:
        install_season_one(content)
        install_showdowns(content)
        _install_factions(content)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    game.now = 0.0
    skipped = {e: TimelineResult(key="skip", time=0.0) for e in ("zhangmancheng", "bocai")}
    game.world.mutate_season(lambda s: s.timeline.update({k: v for k, v in skipped.items() if k not in s.timeline}))
    game.state.world = game.world.get_season()
    return game


def _to_showdown(game, event_id: str, after: float = 1.0) -> list[str]:
    """把季推進到這件決戰排定的時間再過 after 世界秒（遊戲時間；現實時間 game.now 不動）。"""
    return game.advance(game.state.world.schedule[event_id] + after - game.state.world.time)


def _settle_without_fighters(game, definition) -> None:
    """沒人參戰：集結截止那一刻開打，再過一回合逾時就照 end_without_fighters 收場（有人刷新畫面才推進）。"""
    deadline = game.world.get_battle().muster_deadline_real
    for now in (deadline, deadline + definition.round_seconds):
        with at(game, now):
            game.options()


def test_showdown_starts_at_scheduled_time_in_region(content, world):
    """排定的時間（第 6 週週四 20:00）一到就在那個大區開集結：起點照潁川的戰況（40 → 55），季上記下開過了；
    人要在那個大區才能加入。"""
    game = _showdown_game(content, world)
    schedule = game.state.world.schedule["changshe_fire"]
    game.advance(schedule - 1.0 - game.state.world.time)
    assert world.get_battle() is None and "changshe_fire" not in world.get_season().showdowns_opened
    msgs = game.advance(2.0)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase, battle.trend) == ("changshe_fire", "muster", 55)
    assert battle.muster_deadline_real == game.now + content.battles["changshe_fire"].muster_seconds
    assert "🛡️ 【全服戰報】長社火攻的集結號角已經吹響！" in msgs
    assert world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}
    assert game.state.world.showdowns_opened == {"changshe_fire": "changshe_fire"}  # 手上的那一份也跟上了
    assert "battle:join:guan" in ids(game) and "battle:join:huang" not in ids(game)
    content.battles["changshe_fire"].region = "south"  # 人不在決戰的大區：加入不了
    assert "battle:join:guan" not in ids(game)


def _play_showdown(game, tag: str) -> None:
    """自己一個人參戰（集結時加入），集結截止後每回合都出 tag，一路打到收場。"""
    with at(game, game.now):
        game.choose(f"battle:join:{game.state.player.faction}")
    now = game.world.get_battle().muster_deadline_real
    while game.world.get_battle().phase != "ended":
        with at(game, now):
            game.choose(f"battle:act:{tag}")
        now += 1


def test_showdown_result_feeds_timetable(content, world):
    """收場後 timeline["changshe_fire"] 有結果（不再走保底的 BattleOutcome）：戰況照表跳，波才照表退場；公告進每個人的
    江湖紀錄，參戰者的戰報與那一則紀錄寫的是時刻表那一格（官軍大勝）。"""
    from tianxia.models import FigureChange

    game = _showdown_game(content, world)
    content.map.regions[0].front = "yingru"  # 測試夾具的北區沒寫戰線：這裡宣告它算潁川汝南，官軍的目標是把它壓低
    next(f for f in content.scenario.factions if f.id == "guan").goals = {"yingru": -1}
    event = next(e for e in content.timetable if e.id == "changshe_fire")
    event.outcomes["guan:大勝"].figures = {"bocai": FigureChange(fate="退場")}
    event.outcomes["guan:險勝"].figures = {"bocai": FigureChange(fate="聲威大減")}
    _to_showdown(game, "changshe_fire")
    _play_showdown(game, "guan_aggressive")  # 55 → 61 → 67 → 73：打滿三回合，官軍大勝
    season = world.get_season()
    assert season.timeline["changshe_fire"].key == "guan:大勝"
    assert season.trends["yingru"] == 40 - 15 and season.figures["bocai"].status == "retired"
    assert "皇甫嵩火攻長社。" in [r.text for r in season.chronicle]
    assert not any("長社火攻戰罷" in r.text for r in season.chronicle)  # 保底結果不寫江湖史
    assert game.state.world.timeline["changshe_fire"].key == "guan:大勝"  # 手上的那一份也跟上了（之後存檔不會蓋掉）
    report = next(e for e in game.state.journal if e.battle_id is not None)
    assert (report.title, report.tag) == ("長社火攻・官軍大勝", "你站在官軍")
    # 第一季規則開著、潁川汝南是一條戰線：大勢增減不再是帶正負號的數字（FB-064）——江湖紀錄存的是機器可讀的標籤（畫出來是
    # 一句話，官軍看是綠的），戰報不收
    assert season.timeline["changshe_fire"].text in report.lines and report.changes == [front_lines.mark("yingru", -15)]
    assert game.state.battles[0].changes == [] and "潁川汝南 -15" not in game.state.battles[0].notes
    assert any("潁川汝南：官軍" in html and "tx-up" in html for html in (game.battle_extra_html(),))
    assert game.state.battles[0].tier == "官軍大勝"
    assert any(e.title == "江湖大事" and "火光燭天" in e.tag for e in game.state.journal)
    other = Game.new(content, "丙", rng=random.Random(5), world=world)  # 沒參戰的人也收到公告，但沒有戰報
    other.sync(game.now + 10)
    assert any(e.title == "江湖大事" and "火光燭天" in e.tag + "".join(e.lines) for e in other.state.journal)  # 幾件合成一則
    assert not any(e.battle_id is not None for e in other.state.journal)


def test_no_fighters_judged_from_front_start(content, world):
    """沒人參戰：照 end_without_fighters 收場，用照戰況算出的起點判（潁川 30 → 起點 60 → 官軍險勝），不是保底的結果。"""
    game = _showdown_game(content, world)
    world.mutate_season(lambda s: s.trends.update(yingru=30))
    game.state.world = world.get_season()
    _to_showdown(game, "changshe_fire")
    assert world.get_battle().trend == 60
    _settle_without_fighters(game, content.battles["changshe_fire"])
    season = world.get_season()
    assert season.timeline["changshe_fire"].key == "guan:險勝" and season.trends["yingru"] == 30 - 8


def test_no_fighters_still_resolves(content, world):
    """Review Focus 2：那個大區沒人打，時刻表照樣拿到一個結果，季不會卡住：決戰收掉、下一件照常倒數、之後的大事照常結算。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire")
    _settle_without_fighters(game, content.battles["changshe_fire"])
    season = world.get_season()
    assert season.timeline["changshe_fire"].key == "guan:險勝"  # 起點 55，沒人推
    assert game.options() and world.get_battle().phase == "ended"
    assert season.showdowns_waiting == [] and game.status_data()["next_event"]["title"] != "長社火攻"
    game.advance(calendar.week_start(8, content) - game.state.world.time)
    assert {"luzhi_siege", "qinjie", "luzhi_jailed"} <= set(world.get_season().timeline)


def test_scheduled_while_another_battle_runs_waits_then_starts(content, world):
    """Review Focus 1、2：時間到了卻開不成（另一場還在打）：記號留著，那一場收場的那一下立刻開。長社開打後一路推到宛城的時間：
    中間第 7、8 週照常結算（長社已經開過，不算「沒開成」，不會被照起點結算），宛城排在長社後面等，長社收場立刻開。
    每件只開一次、各自結算一次。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    beta = _install_battle_def(content)
    game.admin_start_battle(beta.id, now=0.0)
    _to_showdown(game, "changshe_fire")
    assert world.get_battle().battle_id == beta.id and world.get_season().showdowns_waiting == ["changshe_fire"]
    _settle_without_fighters(game, beta)
    changshe = world.get_battle()
    assert changshe.battle_id == "changshe_fire" and world.get_season().showdowns_waiting == []
    _to_showdown(game, "wancheng")
    season = world.get_season()
    assert world.get_battle().record_id == changshe.record_id and season.showdowns_waiting == ["wancheng"]
    assert {"luzhi_siege", "qinjie", "luzhi_jailed"} <= set(season.timeline) and "changshe_fire" not in season.timeline
    _settle_without_fighters(game, content.battles["changshe_fire"])
    assert world.get_battle().battle_id == "wancheng_jia" and world.get_season().showdowns_waiting == []
    _settle_without_fighters(game, content.battles["wancheng_jia"])
    season = world.get_season()
    assert season.showdowns_opened == {"changshe_fire": "changshe_fire", "wancheng": "wancheng_jia"}
    assert season.timeline["changshe_fire"].key == "guan:險勝" and season.timeline["wancheng"].key == "甲:guan:險勝"
    assert [b.battle_id for _, b in world.ended_battles()] == [beta.id, "changshe_fire", "wancheng_jia"]


def test_showdown_never_opens_twice(content, world):
    """開戰後推進跨過開戰時間好幾次、季終收兵（FB-035）後再推進，都不會再開同一場；收兵的那一場不算結果。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire")
    record = world.get_battle().record_id
    for _ in range(3):
        game.advance(calendar.cal_hour_seconds(content) * 7)
        game.sync(game.now)
        assert world.get_battle().record_id == record
    game.advance(season_length_days(world.get_season(), content) * DAY)  # 季終
    assert world.get_season().ended
    game.options()  # 有人刷新畫面：沒打完的收兵
    for _ in range(2):
        game.advance(DAY)
        game.sync(game.now + 1)
    assert world.get_battle() is None
    ended = world.ended_battles()
    assert [(b.battle_id, b.unfinished) for _, b in ended] == [("changshe_fire", True)]
    assert "changshe_fire" not in world.get_season().timeline  # 沒打完的不算結果（季末交給 T9）


def test_lock_does_not_change_start_or_options(content, tmp_path):
    """Review Focus 3：有人鎖定長社（黃巾）的那一服，跟沒人鎖定的那一服，決戰的起點、集結、選項、戰場文字都一模一樣；
    只有收場判結果時才看鎖定（起點 55 沒人推：沒鎖定是官軍險勝，黃巾鎖定是黃巾險勝）。"""
    from tianxia.state import Lock

    views, games = [], []
    for name in ("plain", "locked"):
        world = open_world(tmp_path / f"{name}.db")
        game = _showdown_game(content, world)
        if name == "locked":
            world.mutate_season(lambda s: s.locks.update(changshe_fire=Lock(side="huang", name="乙", time=0.0, shown="某位少俠")))
            game.state.world = world.get_season()
        _to_showdown(game, "changshe_fire")
        battle = world.get_battle()
        views.append((battle.trend, [o.model_dump() for o in game.options()], game.scene_text()))
        with at(game, battle.muster_deadline_real):
            views.append(([o.model_dump() for o in game.options()], game.scene_text()))
        games.append(game)
    assert views[0] == views[2] and views[1] == views[3]
    for game in games:
        battle = game.world.get_battle()
        with at(game, battle.round.opened_real + content.battles["changshe_fire"].round_seconds):
            game.options()
    assert [g.world.get_season().timeline["changshe_fire"].key for g in games] == ["guan:險勝", "huang:險勝"]


def test_admin_can_open_a_showdown_by_hand_once(content, world):
    """管理者「立刻開戰」：第一季列出還沒開過的時刻表決戰（宛城只列這一季版本的那一筆），開出來的跟排定時間開的一樣
    （起點照戰況、記下開過了）；開過就不再列、時間到了也不再開。開關關著不列時刻表決戰。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    assert [b.id for b in game.admin_battles()] == ["changshe_fire", "wancheng_jia"]
    assert any("長社火攻的集結號角" in m for m in game.admin_start_battle("changshe_fire", now=0.0))
    assert (world.get_battle().battle_id, world.get_battle().trend) == ("changshe_fire", 55)
    assert game.state.world.showdowns_opened == {"changshe_fire": "changshe_fire"}
    assert [b.id for b in game.admin_battles()] == ["wancheng_jia"]
    assert game.admin_start_battle("changshe_fire", now=1.0) == ["（沒有這場戰鬥。）"]
    record = world.get_battle().record_id
    _to_showdown(game, "changshe_fire")
    assert world.get_battle().record_id == record and world.get_season().showdowns_waiting == []
    content.config.season_one = False
    assert game.admin_battles() == []


def test_admin_end_season_settles_a_waiting_showdown_and_shelves_a_running_one(content, world):
    """T8 fix round 0：管理者「立刻收季」——長社正在打（沒打完：收兵、不算結果，FB-035），排在後面等它的宛城從沒開成
    （收季前照起點結算：南陽 35 − 秦頡 3 → 59 → 甲版官軍險勝），記號清掉；結算的公告照樣進江湖紀錄、只有一則。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    _to_showdown(game, "changshe_fire")  # 長社開了
    _to_showdown(game, "wancheng")  # 長社還在打（開過了，第 7、8 週照常結算），宛城排在後面等
    assert world.get_battle().battle_id == "changshe_fire" and world.get_season().showdowns_waiting == ["wancheng"]
    game.admin_end_season(now=game.now)
    season = world.get_season()
    assert season.ended and season.timeline["wancheng"].key == "甲:guan:險勝"
    assert "changshe_fire" not in season.timeline and season.showdowns_waiting == []
    assert [(b.battle_id, b.unfinished) for _, b in world.ended_battles()] == [("changshe_fire", True)]
    announced = season.timeline["wancheng"].text
    assert sum(announced in e.tag + "".join(e.lines) for e in game.state.journal) == 1
    game.sync(game.now + 5)
    assert sum(announced in e.tag + "".join(e.lines) for e in game.state.journal) == 1


def test_admin_end_season_with_only_a_waiting_showdown_settles_it(content, world):
    """沒有決戰在打、長社的時間到了卻還在等（例：開集結之前就收季）：收季前照起點結算（潁川 40 → 55 → 官軍險勝）。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    world.mutate_season(lambda s: s.showdowns_waiting.append("changshe_fire"))  # 記號在、還沒開（開在 mutate 之後）
    game.state.world = world.get_season()
    game.admin_end_season(now=0.0)
    season = world.get_season()
    assert season.ended and season.timeline["changshe_fire"].key == "guan:險勝" and season.showdowns_waiting == []
    assert world.get_battle() is None


def test_a_catch_up_that_crosses_only_the_showdown_time_still_opens_the_muster(content, world):
    """T8 fix round 1：一次追趕只跨過長社的時間、還沒到之後的大事（第 7 週）：照舊晚開集結，不照起點結算。"""
    game = _showdown_game(content, world)
    luzhi = next(e for e in content.timetable if e.id == "luzhi_siege")
    before_week7 = calendar.event_time(luzhi, content, game.state.world) - calendar.cal_hour_seconds(content)
    game.advance(before_week7 - game.state.world.time)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase, battle.trend) == ("changshe_fire", "muster", 55)
    season = world.get_season()
    assert "changshe_fire" not in season.timeline and "luzhi_siege" not in season.timeline
    assert season.showdowns_opened == {"changshe_fire": "changshe_fire"} and season.showdowns_waiting == []


def test_a_showdown_records_the_version_it_actually_fought(content, world):
    """審查 M-1：宛城在第 3 週結算之前就開了（照史書那一版，甲：守方黃巾），開打期間第 3 週結算成「不成」；
    收場時記的仍是實際打的甲版（南陽 35 → 起點 58 → 官軍險勝），不是照當下的版本改成乙版。
    T10 起管理者的開戰選單在第 3 週結算前不列宛城（PM 2026-10-05），所以這裡直接照時間到了的那條路開。"""
    from tianxia.state import TimelineResult
    from tianxia.world import open_showdown

    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    world.mutate_season(lambda s: s.timeline.pop("zhangmancheng"))  # 第 3 週還沒結算
    game.state.world = world.get_season()
    assert [b.id for b in game.admin_battles()] == ["changshe_fire"]
    open_showdown(world, content, "wancheng", 0.0)
    world.mutate_season(lambda s: s.timeline.update(zhangmancheng=TimelineResult(key="不成", time=1.0)))
    game.state.world = world.get_season()
    _settle_without_fighters(game, content.battles["wancheng_jia"])
    assert world.get_season().timeline["wancheng"].key == "甲:guan:險勝"


def test_a_shelved_showdown_opens_again_next_season_once(content, world):
    """審查 M-6：長社打到一半就收季（收兵、不算結果）；開下一季之後，新的一季照自己的排程把長社開一次（起點照新的戰況），
    再推進也不重開。"""
    game = _showdown_game(content, world)
    content.config.admins = ["沈浪"]
    _to_showdown(game, "changshe_fire")
    first = world.get_battle().record_id
    game.admin_end_season(now=game.now)
    assert [(b.battle_id, b.unfinished) for _, b in world.ended_battles()] == [("changshe_fire", True)]
    game.admin_next_season(now=game.now)
    season = world.get_season()
    assert (season.showdowns_waiting, season.showdowns_opened, season.timeline.get("changshe_fire")) == ([], {}, None)
    _to_showdown(game, "changshe_fire")
    battle = world.get_battle()
    assert battle.battle_id == "changshe_fire" and battle.record_id != first and battle.phase == "muster"
    assert battle.trend == battle_instance.start_from_front(rules.trend_value(game.state, content, "yingru"))
    for _ in range(3):
        game.advance(calendar.cal_hour_seconds(content) * 7)
        assert world.get_battle().record_id == battle.record_id
    assert world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}


# ── 季末時決戰還在打（計畫 T9 Review Focus 5）──────────────────────


def test_ending_once_when_battle_running(content, world):
    """第一季排定的季末到了、長社還在打：結局只算一次、季末公告一則、決戰收兵不算結果（戰況不動）、
    參戰者之後同步收到「沒打完、不算勝負」那一則（沒有戰報）、階段是休季。"""
    game = _showdown_game(content, world)
    _to_showdown(game, "changshe_fire", after=2.0)
    with at(game, game.now):
        game.choose("battle:join:guan")
    start = game.world.get_battle().muster_deadline_real + 1
    with at(game, start):
        game.choose("battle:act:guan_safe")  # 打到一半：還在交戰
    assert game.world.get_battle().phase == "active"
    trends = dict(game.world.get_season().trends)

    game.advance(game.state.world.schedule["finale"] + 1 - game.state.world.time)
    season = game.world.get_season()
    assert season.ended and season.ending_id and season.timeline["xiaquyang"].key == season.ending_id
    assert sum(1 for r in season.chronicle if r.text == f"賽季落幕：{season.ending_title}") <= 1
    assert game.world.season_phase() == "resting"

    with at(game, start + 1):
        assert ids(game) == ["season:resting"]  # 畫面刷新那一下把沒打完的收起來
    assert game.world.get_battle() is None
    after = game.world.get_season()
    # 決戰的結果沒有套：潁川（長社的戰線）沒動，時間軸沒有長社（之後別的大事照常動了南陽、冀州）
    assert after.trends["yingru"] == trends["yingru"] and "changshe_fire" not in after.timeline
    (_, shelved), = [b for b in game.world.ended_battles() if b[1].battle_id == "changshe_fire"]
    assert shelved.unfinished
    game.sync(start + 10)
    assert SHELVED_LINE in game.state.journal[0].lines and game.state.journal[0].battle_id is None
    assert game.state.battles == []
    game.advance(60)  # 收季之後再推也不會再收一次
    assert game.world.get_season().ending_id == season.ending_id


def test_a_character_made_mid_season_gets_one_season_start_entry(content, world):
    """FB-052：第二季開季之後才建立的角色，江湖紀錄只有一則「賽季開始」（以前換季的重來與建角色各寫一則）。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=100.0)
    admin.admin_next_season(now=200.0)
    newcomer = Game.new(content, "新來的", rng=random.Random(2), world=world)
    assert [e.tag for e in newcomer.state.journal].count("賽季開始") == 1
    assert newcomer.state.player.season_number == world.get_season_number() == 2


def test_the_season_start_entry_of_a_mid_season_character_has_the_season_time(content, world):
    """FB-052（FB-045～052 審查 m1）：第二季過了一陣子才建的角色，留下的那一則「賽季開始」記的是建角色那一刻的季時間，
    不是 0（「剛剛」的時間才對）。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=100.0)
    admin.admin_next_season(now=200.0)
    admin.advance(3 * 86400)
    newcomer = Game.new(content, "新來的", rng=random.Random(2), world=world)
    [entry] = [e for e in newcomer.state.journal if e.tag == "賽季開始"]
    assert entry.time == world.get_season().time > 0


# ── 配點（武學與成長設計 6.2）──────────────────────────────────────────────


def test_allocating_a_point_raises_the_stat(game):
    game.state.player.stat_points = 2
    game.allocate_stat("agi")
    assert game.state.player.stats["agi"] == 6 and game.state.player.stat_points == 1


def test_allocation_stops_at_the_cap_and_without_points(game):
    p = game.state.player
    p.stat_points = 1
    p.stats["wis"] = 15
    assert "到頂" in game.allocate_stat("wis")[0]
    assert p.stat_points == 1  # 到頂的那一點沒扣
    p.stat_points = 0
    assert "沒有可以分配" in game.allocate_stat("str")[0]
    assert "沒有這項" in game.allocate_stat("silver")[0]
    assert p.stats["str"] == 5 and p.stats["silver"] == 50


def test_a_refused_allocation_writes_no_journal_entry(game):
    """被拒絕（沒有點、到頂、沒這項）只回一句話，不留紀錄（武學與成長計畫 F12）。"""
    p = game.state.player
    before = list(game.state.journal)
    game.allocate_stat("str")  # 沒有點
    p.stat_points, p.stats["wis"] = 1, 15
    game.allocate_stat("wis")  # 到頂
    game.allocate_stat("silver")  # 沒這項
    assert game.state.journal == before


def test_allocating_writes_one_merged_journal_entry(game):
    """連按幾次（玩家、假人都一樣）併成一則「配點」，數值變化加總。"""
    game.state.player.stat_points = 3
    game.allocate_stat("str")
    game.allocate_stat("str")
    game.allocate_stat("agi")
    heads = [e for e in game.state.journal if e.title == "配點"]
    assert len(heads) == 1 and game.state.journal[0] is heads[0]
    assert heads[0].changes == ["臂力 +2", "身法 +1"]


def test_allocation_waits_for_the_season_to_open(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.state.player.stat_points = 1
    assert game.allocate_stat("str") == ["（賽季籌備中，等待管理者開季。）"]
    assert game.state.player.stat_points == 1 and game.state.player.stats["str"] == 5


def test_the_status_carries_the_points_to_allocate(game):
    game.state.player.stat_points = 3
    data = game.status_data()
    assert data["stat_points"] == 3 and data["stat_cap"] == 15
    assert data["attrs"][0] == ("臂力", 5, "str")
    assert [k for _, _, k in data["attrs"]] == ["str", "agi", "con", "wis", "lore"]


def test_the_status_says_what_each_stat_does(game):
    """配點鈕底下那一行（計畫二最終審查 M2）：點數配了收不回來（設計 6.2），按之前要看得到五項各管什麼（照設計 6.1、6.3）。
    名字照 Config.stat_names、順序跟 attrs 一樣，再加一句事件的檢定看哪幾項；文字由引擎給，網頁不寫死。"""
    names = game.content.config.stat_names
    names["agi"] = "輕功"  # 改了名字，那一行跟著改
    data = game.status_data()
    assert [name for name, _ in data["stat_uses"]] == [name for name, _, _ in data["attrs"]] == [
        names[k] for k in ("str", "agi", "con", "wis", "lore")
    ]
    uses = dict(data["stat_uses"])
    assert "武學" in uses[names["str"]]  # 臂力：武學（外功）的威力
    assert "氣血" in uses["輕功"]  # 身法：打完一場少掉一點氣血
    assert all(word in uses[names["con"]] for word in ("內功", "氣血上限", "內傷"))  # 根骨：內功、氣血上限、少受內傷
    assert all(word in uses[names["wis"]] for word in ("修練", "意境", "閉關"))  # 悟性：修練升品、探索悟意境、閉關心得
    assert "持有" in uses[names["lore"]]  # 博聞：武學與意境的持有上限（設計 6.3）
    assert data["stat_uses_note"] == "事件的檢定看前四項。"  # 還沒有事件檢定博聞（PM 2026-10-05），見下一個測試


def test_the_stat_note_says_four_until_an_event_checks_lore():
    """「事件的檢定看前四項」是因為正式內容還沒有任何事件檢定（或隨口應對看）博聞。joy 加了第一個之後這條會失敗：
    把 skillview.STAT_CHECK_NOTE 改回「事件的檢定也看這五項。」、這條跟著改（PM 2026-10-05）。"""
    from tianxia import skillview

    real = load_content(ROOT / "content")
    stats = {ch.check.stat for e in real.events.values() for ch in e.choices if ch.check is not None}
    stats |= {e.free_text.stat for e in real.events.values() if e.free_text is not None}
    assert stats and "lore" not in stats
    assert skillview.STAT_CHECK_NOTE == "事件的檢定看前四項。"


def test_lore_is_the_fifth_stat_and_is_named_in_one_place(game):
    """設計 6.3：第五項屬性「博聞」。顯示名只在 Config.stat_names，改那裡狀態列就跟著改。"""
    assert game.state.player.stats["lore"] == 5
    game.content.config.stat_names["lore"] = "見識"
    game.state.player.stat_points = 1
    assert game.status_data()["attrs"][-1] == ("見識", 5, "lore")
    assert game.allocate_stat("lore") == ["見識 +1"]
    assert game.state.player.stats["lore"] == 6 and game.state.player.stat_points == 0


def test_lore_is_capped_like_the_other_stats(game):
    p = game.state.player
    p.stats["lore"], p.stat_points = game.content.config.stat_cap, 1
    assert "到頂" in game.allocate_stat("lore")[0] and p.stat_points == 1
    msgs = rules.apply_effect(Effect(stats={"lore": 3}), game.state, game.content, game.world)
    assert p.stats["lore"] == game.content.config.stat_cap and any("到頂" in m for m in msgs)


def test_an_old_save_without_lore_gets_the_starting_value(game):
    """舊存檔（博聞加進來之前存的）沒有這一項：讀進來時照開局的數字補上，狀態列、加點、檢定都照常。"""
    state = game.state.model_copy(deep=True)
    del state.player.stats["lore"]
    loaded = Game(game.content, state, random.Random(0), game.world)
    assert loaded.state.player.stats["lore"] == game.content.config.start_stats["lore"] == 5
    assert loaded.status_data()["attrs"][-1][1:] == (5, "lore")


def test_the_status_text_still_reads_the_attrs_with_their_keys(game):
    assert "臂力 5　身法 5　根骨 5　悟性 5" in game.status_text()


def test_a_win_no_longer_gives_a_random_stat_point(game):
    """打贏不再有「隨機 +1 屬性」的機會（武學與成長設計 6.2：屬性只靠升級給的點）。"""
    rules.learn_skill(game.state, game.content, "fist")
    game.content.config.train_event_chance = 0.0
    walk_to(game, "lake")
    game.rng = FixedRandom(0.0)  # 以前這個值一定中那一個 +1
    before = {k: game.state.player.stats[k] for k in ("str", "agi", "con", "wis")}
    game.choose("act:train")
    assert game.state.battles[0].tier in ("大勝", "險勝")
    assert {k: game.state.player.stats[k] for k in before} == before
    assert not any(c.split(" ")[0] in ("臂力", "身法", "根骨", "悟性") for c in game.state.battles[0].changes)


def test_the_last_point_does_not_say_there_are_zero_left(game):
    game.state.player.stat_points = 2
    assert game.allocate_stat("str") == ["臂力 +1（還有 1 點可以分配）"]
    assert game.allocate_stat("agi") == ["身法 +1"]  # 最後一點：不寫「還有 0 點」


# ── 四屬性的加成接進氣血與決戰（武學與成長設計 6.1；計畫二 Task 2）──────────────────────


def test_a_point_of_root_raises_the_hp_cap_but_not_the_hp(game):
    """計畫二 G7：配一點根骨，氣血上限多 3%，目前氣血不變（沒滿血時分子不動、分母變大）。"""
    from tianxia import team
    p = game.state.player
    p.stat_points, p.member.neili = 1, 100.0
    base = team.neili_cap(game.content, p.member.level)
    before = game.status_data()
    game.allocate_stat("con")
    after = game.status_data()
    assert before["hp"] == after["hp"] == 100
    assert (before["hp_max"], after["hp_max"]) == (base, round(base * 1.03))  # 320 → 330（329.6 四捨五入）
    assert game._battle_neili_cap() == round(base * 1.03)  # 決戰帶進去的氣血上限也吃根骨


def test_hp_comes_back_by_the_rooted_cap(content):
    """氣血隨時間回復照（吃了根骨的）上限算：同樣過一段時間，根骨 15 回得多三成。"""
    games = [Game.new(content, name, rng=random.Random(0)) for name in ("甲", "乙")]
    games[1].state.player.stats["con"] = 15
    for game in games:
        game.state.player.member.neili = 0.0
        game._advance_player_local(HOUR / 10)
    plain, rooted = (game.state.player.member.neili for game in games)
    assert plain > 0 and rooted == pytest.approx(plain * 1.3)


def test_the_showdown_power_snapshot_carries_the_players_boost(game):
    """決戰加入時存的威力快照也吃本人的加成（武學與成長設計 8.4）。"""
    p = game.state.player
    p.member.wugong_id = "basic_fist"
    plain = game._battle_power()
    p.stats["str"] = 15
    assert plain > 0 and game._battle_power() == pytest.approx(plain * 1.3)


def test_the_status_bar_and_the_card_show_the_same_hp_at_root_6(game):
    """計畫二 Task 2 修正第一輪：根骨 6 的上限 329.6、目前氣血 100.6，狀態列與名冊的角色卡寫出同一組數字。"""
    p = game.state.player
    p.stats["con"], p.member.neili = 6, 100.6
    data = game.status_data()
    assert (data["hp"], data["hp_max"]) == (101, 330)
    assert f"氣血 {data['hp']}/{data['hp_max']}" in game.member_card("player")
