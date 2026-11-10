import random
import re
import time
from unittest import mock

import pytest

from conftest import FixedRandom, at, classic_rules, install_season_one, real_content, walk_to
from tianxia import atlas
from tianxia.features.battle import instance as battle_instance
from tianxia import battlelog, calendar
from tianxia.features.companions import companion_agent
from tianxia import encounter, fight_llm, library, rules, team, traits
from tianxia.features.map import layers
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.martial_arts import Insight, MartialArt, generate_from_name
from tianxia.models import Condition, Effect
from tianxia.models import ExploreMix
from tianxia.state import BotProfile, FigureState, GameState, Journey, Rumor, new_game_state
from tianxia.sqlite_world import open_world
from tianxia.world_state import season_length_days
from engine_kit import (  # noqa: F401
    ACCOUNTS, DAY, FAKE_TURN, HOUR, NEXT_TURN, _a_fused_art, _add_field, _admin, _boss_at_the_lake, _fight_to_the_end,
    _fighter, _figure, _hall, _install_battle_def, _install_battle_def_with_free_text, _install_factions,
    _install_three_move_battle, _join_and_open, _joined_a_battle_in_the_north, _judged, _labels, _legacy_hurry, _no_model,
    _open_three_move_battle, _partway, _play_showdown, _practice_step_game, _prepared, _reload, _showdown_game,
    _south_cave, _spy_battle_status, _stand_by_one_figure, _strip_scores, _three_round_showdown, _to_showdown,
    _training_factions, _warlord_in_battle, _wear, _wugong_step_game, ids,
)


# ── 新遊戲與選項 ─────────────────────────────────────────


@pytest.mark.smoke
def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.team == [] and p.member.level == 1
    assert "測試開始。" in game.state.log


@pytest.mark.parametrize("new_season", [False, True], ids=["new-character", "new-season"])
def test_a_new_character_starts_with_the_starter_arts(content, world, new_season):
    """新角色從那兩門第一成開始；每季重來的角色也一樣（_reset_player_for_new_season 走同一個 new_game_state）。"""
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    game = Game.new(content, "新人", rng=random.Random(0), world=world)
    if new_season:
        game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 7
        game._reset_player_for_new_season(game.state.player.season_number + 1)
    member = game.state.player.member
    assert (member.neigong_id, member.neigong_level) == ("basic_breath", 1)
    assert (member.wugong_id, member.wugong_level) == ("basic_fist", 1)


def test_there_is_no_self_created_art_any_more(game):
    """行為上也沒有（審查 F18）：就算兩個欄位都空著、手上心得銀兩都有，選單也不給自創，硬送自創的選項 id 只會被擋回；
    伺服器那一側的拒絕在 tests/server/test_server.py。"""
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


def test_real_content_starts_with_enough_xinde_for_the_first_level():
    """Review Focus 第 5 條：新角色照新手引導按「練成」，第一成一定練得起。"""
    real = real_content()
    first = [real.skills[s] for s in real.config.starter_skills]
    assert len(first) == 2
    assert real.config.start_stats["xinde"] >= 2 * real.config.practice_xinde_per_level  # 兩門各練一成


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
    assert ids(game) == ["act:explore", "act:socialize", "act:recruit", "move:lake"]


def test_socialize_hidden_when_no_events_here(game):
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)


def test_recruit_option_shows_the_real_odds_and_tracks_affinity(game):
    """實機 playtest 發現招募失敗時玩家完全看不出原因、也不知道好感度才是真正的槓桿
    （roster.py::recruit_chance）。選單上的成功率要跟著好感度即時變化，不是寫死的。"""
    def label():
        return next(o.label for o in game.options() if o.id == "act:recruit")

    assert "成功率約 35%" in label()  # 好感度 0：基礎成功率
    game.state.player.affinities["mate"] = 100
    assert "成功率約 85%" in label()  # 基礎 35% + 好感度 100 的加成 50%


def test_stamina_comes_back_with_time_alone(game):
    """體力見底時沒有按鈕要按：時間過去就回（打坐 2026-10-12 拿掉了，企劃者「打坐也拿掉」）。"""
    cfg = game.content.config
    game.state.player.stamina = 0
    game.advance(1800)
    assert game.state.player.stamina == pytest.approx(1800 / cfg.stamina_regen_seconds)


# ── 打坐拿掉了 ──────────────────────────────────────────────


def test_a_save_made_while_sitting_stands_up_on_load(game):
    """存檔時坐著的人（打坐拿掉之前）讀檔就起身：選單是平常閒著的那一份，體力照平常的速度回。"""
    game.state.player.resting_since = 0.0
    game._drop_stale_references()
    assert game.state.player.resting_since is None
    assert "act:explore" in ids(game)


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
    # 選項底下沒有另一行（wait 是按下去等模型時換上的字，不是另一行；不是大場面就是空的；note 是名聲 5B 俠寇選項的第二行，這裡空著）
    assert all(o.model_dump().keys() == {"id", "label", "enabled", "wait", "confirm", "confirm_yes", "tag", "note"}
               and o.wait == o.confirm == o.confirm_yes == o.tag == o.note == "" for o in game.options())
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


def test_a_story_battle_is_not_dodged_and_a_loss_still_applies_the_fail_effect(game):
    """最終審查 I1：劇情戰的結果是人寫好的勝或敗（僵持也算敗），身法閃避不擲——不然卡片寫「躲過了這一敗」、
    下面卻照樣「你敗了。」「銀兩 -10」。身法 55＝閃避機會 100%。"""
    game.state.player.stats["agi"] = 55
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    with mock.patch.object(encounter, "dodge", wraps=encounter.dodge) as spy:
        game.choose("choice:0")  # 應戰翻江龍：必敗
    spy.assert_not_called()  # 劇情戰一點亂數也不給閃避
    record = game.state.battles[0]
    assert (record.tier, record.event) == ("落敗", "挑戰")
    assert record.notes == ["你敗了。"] and battlelog.DODGE_NOTE not in record.notes
    assert record.changes == ["銀兩 -10"] and game.state.player.stats["silver"] == 40


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


def test_a_dodged_train_loss_is_a_draw_with_a_note_and_costs_no_silver(game):
    """身法閃避（人物資質設計 14.4）：落敗被閃成僵持，戰報註明、不賠銀兩（賠銀兩只在落敗），氣血照僵持扣。"""
    game.content.locations["lake"].enemies = ["boss"]  # 打不贏的翻江龍
    game.content.config.dodge_per_point = 1.0
    game.state.player.stats["agi"] = 6  # 閃避機會 1×1＝100%
    walk_to(game, "lake")
    before = game.state.model_copy(deep=True)
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    record = game.state.battles[0]
    assert (record.tier, record.silver) == ("僵持", 0)
    assert record.notes == [battlelog.DODGE_NOTE]
    assert game.state.player.stats["silver"] == 50
    draw_toll = team.take_encounter_toll(before, game.content, game.world, "僵持")  # 同一個人、同一份氣血，結果是僵持
    assert draw_toll and record.changes == draw_toll  # 戰報上的損耗就是僵持的那一份（不是落敗的）
    assert game.state.player.member.neili == before.player.member.neili


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


def test_continuing_and_leaving_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        msgs = game.choose("talk:0")
        assert msgs == ["他點了點頭。", "（情誼 +1）"]
        assert game.state.player.affinities["mate"] == 1
        msgs = game.choose("talk:leave")
    assert msgs == ["你結束了這段交談，先行告辭。"]
    assert game.state.player.pending_companion is None
    # 小鎮只有他一位大勢人物：交友之外，直接多一顆求見他（名望門檻 0，見得到）
    assert ids(game) == ["act:explore", "act:socialize", "call:mate", "act:recruit", "move:lake"]


def test_socializing_without_a_deep_interaction_companion_falls_through_to_events(game):
    """小鎮的韓鐵沒有標 deep_interaction：交友照舊走一般事件（例如拜師），不會誤觸發對話。"""
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    assert game.state.player.pending_companion is None


# ── 重複內容不在行動鎖裡叫模型（2026-10-12：點綴句看不到、卻讓全服等）─────────


class _CountingClient:
    timeout = 15

    def __init__(self):
        self.calls = 0

    def chat_text(self, *a, **k):
        self.calls += 1
        return "風又吹起了。"

    def chat_structured(self, *a, **k):
        self.calls += 1
        raise RuntimeError("不該叫")


def test_a_repeated_event_does_not_call_the_model(game):
    """探索幾乎每次都撞到看過的事件：以前每次都在行動鎖裡等模型補一句點綴（最多 15 秒，全服跟著等），那句卻只進 GameState.log。"""
    event = next(iter(game.content.events.values()))
    game._present(event)
    game.client = _CountingClient()
    head, text = game._present(event)
    assert game.client.calls == 0
    assert text == rules.fill_marks(event.text, game.state)


def test_revisiting_a_location_does_not_call_the_model(game):
    walk_to(game, "lake")
    game.client = _CountingClient()
    msgs = game.travel("town", "dash")  # 疾行：在這次行動裡抵達；小鎮開局就去過，是重遊
    assert game.client.calls == 0
    assert game.location_text() in msgs


def test_a_failed_practice_does_not_finish_the_tutorial_step(game):
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.stats["xinde"] = 0
    with mock.patch("tianxia.features.guide.rules.note_action", return_value=[]) as noted:
        game.practice("武學")
    noted.assert_not_called()


def test_a_real_practice_still_reaches_the_tutorial_hook(game):
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.stats["xinde"] = 5
    with mock.patch("tianxia.features.guide.rules.note_action", return_value=[]) as noted:
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


def test_melting_an_insight_writes_one_journal_entry(game):
    game.state.player.insights, game.state.player.stats["xinde"] = ["feng"], 0
    msgs = game.melt_insight("feng")
    assert "化成了心得" in msgs[0] and game.state.player.insights == []
    entry = game.state.journal[0]
    assert entry.title == "修練" and "心得 +10" in entry.changes


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


def test_practicing_with_nothing_learned_says_so_without_finishing_the_step(game):
    """FB-007 原本的現場：畫面寫「你還沒學武學」，緊接著卻是「✔ 引導完成」。"""
    _practice_step_game(game, {})
    assert game.practice("武學") == ["你還沒學武學，沒東西可以練。"]


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


def test_art_detail_shows_the_players_own_quality(game):
    """武學與成長 Task 3：功法卡寫玩家自己那一份的品質與威力，全服登記的那一筆不動。"""
    registered = MartialArt(
        id="沉柳纏勁", name="沉柳纏勁", kind="武學", quality="中品", attribute="柔", affinity=["柔"],  # 武學重構：屬性照相容屬性
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
    assert game.art_detail("basic_fist").startswith("【粗淺拳腳】上品")
    assert game.content.skills["basic_fist"].quality == "下品"


def test_a_universal_art_card_has_no_dangling_attribute(game):
    """武學重構：基礎武學兼容並蓄、沒有屬性，功法卡的名下不留一個空的「・屬」（網頁那邊 4d0238d 已經不留「・」）。"""
    game.state.player.member.wugong_id = "basic_fist"
    head = game.art_detail("basic_fist").split("\n")[0]
    assert not head.endswith("・屬") and "・屬・" not in head, head


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


def test_seclusion_countdown_says_real_hours(content, game):
    """FB-062：出關的倒數標「現實」，而且照現實小時算（世界時鐘 ÷ time_scale）：time_scale 2 時，世界 4 小時＝現實 2 小時。"""
    content.config.time_scale = 2.0
    assert game.seclude(4) == ["你閉關靜修，預計現實 2 小時後出關；閉關期間氣血回復加倍。"]
    assert game.status_data()["busy_hours"] == 2.0
    assert "🧘 閉關中，現實約 2.0 小時後出關" in game.status_text()


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
    content.config.decisive_from_week = 1  # 這一支不是在測收季門檻要等到決定性那一週（FB-165，test_world 另測）：關掉那一道
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    a.state.world.trends["kou"] = 80
    from tianxia.world import check_thresholds
    check_thresholds(a.state, content, a.world)
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
    game.state.player.arts = ["basic_fist"]  # 庫裡一門、身上沒在練：開了季就熔得掉（整併最終審查 area 8 M5 要釘住這兩個）
    assert game.melt_art("basic_fist") == waiting
    assert game.melt_insight("feng") == waiting
    assert game.state.player.arts == ["basic_fist"] and game.state.player.insights == ["feng"]
    assert game.state.player.stats["xinde"] == 500


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
    assert p.relationship_notes == {}  # 這一季的關係從頭寫
    assert p.past_notes == {"mate": "並肩作戰過的朋友"}  # 上一季的交情另外留著，交給模型當背景
    assert p.dialogue_history == {"mate": [{"role": "user", "content": "久仰"}]}  # 對話紀錄照舊保留
    assert p.history_start == {"mate": 1}  # 這一季的對話從第 2 則開始
    assert p.tutorial_step == fresh.tutorial_step  # 2 還沒做完（共 3 步）：換季是新角色，引導從頭來（FB-034）
    assert "賽季落幕" in player.chronicle_text()


def test_past_notes_survive_a_quiet_season(content, world):
    """上一季沒聊、上上季聊過的人物：上上季的交情留著，不被清掉。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    player.state.player.relationship_notes = {"mate": "第一季的舊識"}
    for t in (100.0, 400.0):  # 兩次換季，第二季一句都沒聊
        player.sync(t)
        admin.admin_end_season(now=t + 100.0)
        admin.admin_next_season(now=t + 200.0)
    player.sync(800.0)
    assert player.state.player.season_number == 3
    assert player.state.player.past_notes == {"mate": "第一季的舊識"}


def test_the_status_carries_the_season_number(content, world):
    """網頁用它記「這個名號看過哪一季哪一週的大事」：週次每一季都從 1 起，不帶季就分不出上一季的第 1 週與這一季的第 1 週。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    assert player.status_data()["season"] == 1
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    assert player.status_data()["season"] == 2


def test_each_season_marks_where_its_own_dialogue_begins(content, world):
    """對話紀錄跨季保留：每次換季記下當時的長度，模型只看這之後的；第二次換季往後挪到第二季的尾巴。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    said = lambda text: {"role": "user", "content": text}  # noqa: E731
    player.state.player.dialogue_history = {"mate": [said("第一季")]}
    player.state.player.relationship_notes = {"mate": "第一季的關係"}
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    p = player.state.player
    assert p.history_start == {"mate": 1}
    p.dialogue_history["mate"] += [said("第二季一"), said("第二季二")]
    p.relationship_notes = {"mate": "第二季的關係"}
    admin.admin_end_season(now=500.0)
    admin.admin_next_season(now=600.0)
    player.sync(700.0)
    p = player.state.player
    assert p.history_start == {"mate": 3}
    assert p.past_notes == {"mate": "第二季的關係"}  # 最近一次聊過的那一季蓋過更早的
    assert p.relationship_notes == {}


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


def test_a_rumor_at_a_removed_place_is_cleared_only_in_this_copy(content, game):
    """內容拿掉了某個地點：讀進來的那一份傳聞清掉發生地（照舊），但不能就地改到共用的那一份（sqlite_world._logs 記下的
    傳聞物件跟別的讀取共用）：下一次讀、別人讀到的照舊是資料庫裡的樣子。"""
    game.world.mutate_season(lambda s: s.rumors.append(Rumor(time=0, text="舊地方的事", location="removed_place")))
    first = game.world.get_season()
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.world.rumors[-1].location is None and fresh.state.world.rumors[-1].id is not None
    assert first.rumors[-1].location == "removed_place"
    assert game.world.get_season().rumors[-1].location == "removed_place"


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


def test_the_status_shows_a_companions_rooted_hp_cap(game):
    """狀態列的同伴氣血照他自己的根骨（人物資質設計 14.3）：韓鐵第 1 級根骨 6，上限 +3%。"""
    game.state.player.team = ["mate"]
    mate = game.status_data()["team"][0]
    assert mate["hp_max"] == round(team.neili_cap(game.content, 1, 6))


def test_status_text_shows_the_practice_hint_only_when_xinde_is_idle(game):
    assert "心得" in game.status_text() and "💡" not in game.status_text()
    # explain-2：提示只看「付得起、做得了」——心得夠練第一成就算（以前要攢到 xinde_hint_threshold 50）
    game.state.player.stats["xinde"] = team.practice_price(game.content, 1)
    assert "💡" not in game.status_text()  # 兩欄都空著：沒有哪一門可以練
    _wear(game, wugong="fist", neigong="breath")
    assert "💡" in game.status_text() and "練成內功、武學" in game.status_text()
    game.state.player.member.wugong_level = game.state.player.member.neigong_level = 10
    assert "💡" not in game.status_text()  # 沒東西可練、手上也沒有意境可合成


# ── 安排前往 ──────────────────────────────────────────────


@pytest.mark.parametrize(("mode", "cost"), [("walk", 0), ("dash", 15)])
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
    game.content.config.decisive_from_week = 1  # 這一支不是在測收季門檻要等到決定性那一週（FB-165，test_world 另測）：關掉那一道
    game.state.world.flags.add("cave_open")
    game.state.world.trends["kou"] = 80  # 一走到湖邊就觸發「水寇稱霸」，賽季落幕
    game.travel("cave", "dash")
    assert game.state.world.ended and game.state.player.location == "lake"
    assert game.state.journal[0].tag == "賽季落幕，停在 湖邊"


def test_a_trip_set_off_hurrying_before_it_was_removed_still_takes_half_the_time(game):
    game.state.world.flags.add("cave_open")
    _legacy_hurry(game, "cave")
    assert game.state.player.journey.arrive_at == [pytest.approx(90.0), pytest.approx(225.0)]  # (3＋4.5 分鐘) × 30 秒


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


def _ticked_by_the_world_alone(content, game, strip_scores=False):
    """沈浪在集結時站官軍、存檔之後就沒人在線：排程的 Game（沒有玩家）把集結與第一回合的逾時推完，而且不准它算份量。
    strip_scores：先把沈浪的份量快照拿掉。回傳之後的戰局。"""
    definition = _install_three_move_battle(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    if strip_scores:
        _strip_scores(game)
    open_characters().save(game.state)
    ticker = Game.for_world(content, game.world, rng=random.Random(3))
    with mock.patch.object(Game, "_battle_scores", side_effect=AssertionError("排程不該算份量")):
        ticker.world_tick(1000.0 + 601)
        ticker.world_tick(1000.0 + 601 + 121)
    return game.world.get_battle()


def test_the_world_ticker_never_backfills_anyones_scores(content, game):
    """排程的 Game 玩家是空白的，補誰的份量都會補錯：場上有人沒有快照，它照樣推回合、逾時代選，一個份量也不算。"""
    battle = _ticked_by_the_world_alone(content, game, strip_scores=True)
    assert battle.round_number == 1 and battle.participants["沈浪"].scores == {}  # 還是空的：份量 0，照常結算


def test_the_world_ticker_plays_the_three_moves_with_nobody_online(content, game):
    """排程沒有玩家：逾時代出自己那邊的固守，三招照結算（黃巾沒人 → 官軍推滿 10），而且不替誰算份量。"""
    battle = _ticked_by_the_world_alone(content, game)
    assert battle.round_number == 1 and battle.trend == 60
    assert battle.participants["沈浪"].last_result == "固守（剋制 ×1.0）"
    assert battle.round.pending_actions == {} and battle.last_mix["guan"]["固守"] == 1.0


def test_the_world_ticker_never_snapshots_anyones_scores(content, game):
    """排程那個 Game 的玩家是空白的（Game.for_world）：它推回合、逾時代選，但絕不替任何人算份量。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    open_characters().save(game.state)
    ticker = Game.for_world(content, game.world, rng=random.Random(3))
    with mock.patch.object(Game, "_battle_scores", side_effect=AssertionError("排程不該算份量")):
        ticker.world_tick(1000.0 + 601)
        ticker.world_tick(1000.0 + 601 + 121)
    (_, done), = game.world.ended_battles()
    assert not done.unfinished


def test_with_factions_joining_the_other_side_directly_is_refused(content, game):
    """選單上本來就不會出現對方陣營的加入選項；直接呼叫 _battle_choose 也一樣擋得住。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    assert game._battle_choose("join:guan") == ["（你只能站在自己陣營這一邊。）"]
    assert game.world.get_battle().participants == {}


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


def test_status_text_shows_both_sect_and_faction(content, game):
    _install_factions(content)
    game.state.player.sect = "cloud"
    assert "流雲派" in game.status_text() and "官軍" not in game.status_text()
    game.state.player.faction = "guan"
    assert "流雲派・官軍" in game.status_text()


def test_no_active_battle_leaves_normal_gameplay_untouched(content, game):
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


def test_the_muster_keeps_the_everyday_menu_under_the_join_buttons(content, game):
    """集結那段時間（企劃者 2026-10-03 決定，FB-009）：人在戰場的人照常探索、移動，另外多加入的按鈕；
    場景上戰場底下接著自己所在的地點。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert ids(game) == ["battle:join:guan", "battle:join:huang"] + [
            "act:explore", "act:socialize", "act:recruit", "move:lake"]
        scene = game.scene_text()
        assert "測試決戰" in scene and "選擇陣營" in scene and "小鎮" in scene
        game.choose("act:explore")  # 集結中照常探索，不會被擋
        assert game.state.journal[0].title.startswith("探索")


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


def test_battle_ending_falls_back_to_normal_gameplay_on_the_next_render(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


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


def test_a_standing_player_gets_no_stand_option_on_the_battle_menu(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        assert "act:stand" not in ids(game)


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
    definition = _joined_a_battle_in_the_north(content, game)
    with at(game, definition.muster_seconds + 1):
        game._battle_status()  # 開打
        game.travel("cave", "dash")  # 離開北區
        assert "人回到測試北區就能再出手" in game.scene_text()
        game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
        scene = game.scene_text()
        assert "你已經倒下" in scene and "再出手" not in scene


def test_submit_battle_custom_action_outside_battle_is_a_no_op(content, game):
    assert game.submit_battle_custom_action("test") == ["（此刻無法這麼做。）"]


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


def test_only_an_admin_can_trigger_things(content, game):
    definition = _install_battle_def(content)
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（只有管理者能開戰。）"]
    assert game.admin_fire("kou50") == ["（只有管理者能觸發大事。）"]
    assert game.admin_push_trend("kou", 10) == ["（只有管理者能推動大勢。）"]
    assert game.world.get_battle() is None
    assert "kou50" not in game.world.get_season().fired_thresholds
    assert game.world.get_season().trends["kou"] == 30


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


def _after_a_win_only(game):
    """fixture 裡唯一掛在遊歷上的事件（chain_a）改成只在打贏之後接，湖邊遊歷後必接事件。"""
    game.content.events["chain_a"].condition = Condition(fight_tiers=["大勝", "險勝"])
    game.content.config.train_event_chance = 1.0


def test_a_post_fight_event_that_asks_for_a_win_follows_a_win(game):
    _after_a_win_only(game)
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)
    game.choose("act:train")
    assert game.state.battles[0].tier in ("大勝", "險勝")
    assert game.state.pending_event == "chain_a"


@pytest.mark.parametrize("dodged, tier", [(False, "落敗"), (True, "僵持")], ids=["loss", "draw"])
def test_a_post_fight_event_that_asks_for_a_win_never_follows_a_loss_or_a_draw(game, dodged, tier):
    """打不贏的翻江龍：落敗之後不接只給贏家的戰後事件；落敗被身法閃成僵持也不接。"""
    _after_a_win_only(game)
    game.content.locations["lake"].enemies = ["boss"]  # 打不贏的翻江龍
    if dodged:
        game.content.config.dodge_per_point = 1.0
        game.state.player.stats["agi"] = 6  # 落敗被身法閃成僵持
    walk_to(game, "lake")
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    assert game.state.battles[0].tier == tier
    assert game.state.pending_event is None


def test_a_post_fight_event_follows_a_fight_only_when_it_was_won(content):
    """亂數固定、戰後事件一定接（train_event_chance＝1）：不管這一場打成什麼結果，只有打贏才接那則事件。
    對手難度 45 打出險勝與僵持、100 打出僵持與落敗（固定種子，量過），所以贏與沒贏的結果都碰得到。"""
    content.events["chain_a"].condition = Condition(fight_tiers=["大勝", "險勝"])
    content.config.train_event_chance = 1.0
    content.locations["lake"].enemies = ["thug"]
    seen: set[str] = set()
    for difficulty in (45, 100):
        content.squads["thug"].difficulty = difficulty
        for seed in range(20):
            game = Game.new(content, "沈浪", rng=random.Random(seed))
            rules.learn_skill(game.state, content, "fist")
            walk_to(game, "lake")
            game.choose("act:train")
            tier = game.state.battles[0].tier
            seen.add(tier)
            assert (game.state.pending_event == "chain_a") == (tier in ("大勝", "險勝")), (difficulty, seed, tier)
    assert seen >= {"險勝", "僵持", "落敗"}  # 贏、平手、輸都真的打出來過，上面的斷言才不是空轉（結果的分佈跟著戰鬥數字走，多出大勝也行）


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

    return team.member_neili(
        game.content, game.state.player.member, team.con_of(game.state, game.content, game.world, PLAYER),
    )[0]


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


def test_a_dodged_fight_plays_the_draw_it_ended_as(game):
    """身法閃避（人物資質設計 14.4）之後：回合照真的打的那一場演（一回合一回合打，Joy 2026-10-15「全部改回合制」：落敗的 3～4 回合，
    閃避是最後那一下才閃開的），回合裡的「你氣血 -N」加起來等於僵持那一份損耗（62），不是落敗的（93），也等於戰報與真的扣掉的。"""
    game.content.config.dodge_per_point = 1.0
    game.state.player.stats["agi"] = 6  # 閃避機會 100%
    game.content.locations["lake"].enemies = ["boss"]  # 打不贏的翻江龍
    walk_to(game, "lake")
    before = _player_hp(game)
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier == "僵持" and battlelog.DODGE_NOTE in record.notes
    told, shown = _told_and_shown(record)
    assert told == shown == round(before - _player_hp(game)) == 62
    assert len(record.rounds) in (3, 4)


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


@pytest.mark.parametrize("tier", ["落敗", "僵持"])
def test_a_fight_not_won_at_zero_blood_does_not_say_the_blows_were_dodged(game, tier):
    """已經沒氣血的人遊歷落敗，這一場掉的氣血是 0（內傷照樣累積）：對手的出手不能每一下都寫「被你閃開了」——
    讀起來是對方從頭到尾沒碰到你、你卻輸了、損失裡還有內傷（G5 對劇情戰拿掉的同一個矛盾，Final review Minor 2）。
    輸了就不寫打中沒有（跟劇情戰一樣只寫怎麼出手）；回合裡的氣血數字照樣加得起來（0）。"""
    walk_to(game, "lake")
    game.state.player.member.neili = 0.0
    with _forced(tier):
        game.choose("act:train")
    record = game.state.battles[0]
    told, shown = _told_and_shown(record)
    assert record.tier == tier and told == shown == 0 and any(c.startswith("內傷") for c in record.changes)
    assert len(record.rounds) in (3, 4, 5)
    for line in record.rounds:
        assert "被你閃開了" not in line and "你氣血" not in line and "水寇小隊" in line, line
    assert "被你閃開了" not in game.battle_card()


@pytest.mark.parametrize("tier", ["落敗", "僵持"])
def test_a_fight_at_zero_blood_shows_no_zero_blood_change(game, tier):
    """已經沒氣血的人打輸，這一場掉的氣血是 0：戰報的獲得與損失、江湖紀錄的數值變化都不寫「氣血 -0」（零的變化是雜訊，
    手機上還多佔一格）；內傷照樣累積、照樣寫。"""
    from tianxia import battlelog  # 區域 import：不動檔頭那一行（跟別的分支各自往同一行加東西會合併衝突）

    walk_to(game, "lake")
    game.state.player.member.neili = 0.0
    with _forced(tier):
        game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier == tier and any(c.startswith("內傷 +") for c in record.changes)
    assert not any(c.startswith("氣血") for c in record.changes)
    assert "氣血" not in "　".join(battlelog.gains_list(record))
    assert "氣血 -0" not in game.battle_card() and "氣血" not in " ".join(game.state.journal[0].changes)


def test_a_won_fight_that_costs_no_blood_still_says_the_blows_were_dodged(game):
    """反過來：贏了而這一場沒掉氣血（打得漂亮），「被你閃開了」是通的，不動。"""
    walk_to(game, "lake")
    game.state.player.member.neili = 0.0
    with _forced("大勝"):
        game.choose("act:train")
    record = game.state.battles[0]
    assert _told_and_shown(record) == (0, 0) and any("被你閃開了" in line for line in record.rounds)


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


def test_a_big_fight_the_player_set_out_from_on_foot_while_it_was_judged_says_they_left(game):
    """步行、趕路出發之後地點要到抵達才換（Journey 在路上時 location 還是出發地），所以光看地點會誤說「情勢變了」。
    大場面的單子只在不在路上時才開，套用時人在路上就是離開了。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.choose("move:town")  # 另一個分頁：步行出發
    player = game.state.player
    assert player.journey is not None and player.location == request.location  # 地點還沒變
    assert game.choose("act:train", fight=_judged(request)) == ["你離開了，這一仗沒打成。"]
    assert game.state.battles == []


def test_a_big_fight_that_can_no_longer_start_for_another_reason_says_the_situation_changed(game):
    """人沒走、選項卻按不下去了（例如別的分頁把體力花光）：認不出是哪一種變動，就說得中性一點。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.state.player.stamina = 0
    assert game.choose("act:train", fight=_judged(request)) == ["情勢變了，這一仗沒打成。"]
    assert game.state.battles == []


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


def test_a_judgment_is_dropped_after_switching_arts(game):
    """Review Focus 3：等模型的時候換了武學，陣容跟判讀的那一張對不上：作廢、照平常打。"""
    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    game.state.player.member.wugong_id = "fist"
    game.choose("act:train", fight=_judged(request))
    assert game.state.battles[0].narration == ""


class _Recording(random.Random):
    """照常擲骰，順便記下每一次 rng.choice 從哪一串挑、挑到什麼。"""

    def __init__(self, seed):
        super().__init__(seed)
        self.picked: list[tuple[list, object]] = []

    def choice(self, seq):
        got = super().choice(seq)
        self.picked.append((list(seq), got))
        return got


def test_a_real_trip_still_draws_its_foe_from_the_rng():
    """正式內容沒有一個地點的遊歷池子裡有大場面的對手，所以每一處遊歷照舊用 Game.rng 從池子裡挑（亂數序列、整季模擬、
    好玩度量表的對手組成都不變）：潁川郊野打的就是 rng.choice 挑到的那一路。測的是舊遊歷（散人在出陣開著時沒有出陣鈕）。"""
    real = classic_rules(real_content())
    real.config.auto_open_first_season = True
    real.config.train_event_chance = 0.0
    game = Game.new(real, "甲", rng=_Recording(0))
    for loc in real.locations.values():
        assert not any(game.is_big(real.squads[sid]) for sid in loc.enemies), loc.id
    game.state.player.location = "yingchuan_wilds"
    pool = real.locations["yingchuan_wilds"].enemies
    game.rng.picked.clear()
    game.choose("act:train")
    got = next(got for seq, got in game.rng.picked if seq == pool)
    assert game.state.battles[0].opponent == real.squads[got].name
    assert game.rng.picked[0][0] == pool  # 遊歷這一下第一個擲的就是挑對手，跟以前一樣


def test_the_engine_clamps_the_advantage_itself(game):
    """引擎自己也把優勢夾在 ±big_fight_swing：判讀不一定都經過 fight_llm.judge（之後的模型佇列也會交判讀進來），
    優勢 99 只當 15 用（Task 2 審查修正 4）。"""
    from tianxia import encounter, team

    _boss_at_the_lake(game)
    request = game.fight_request("act:train")
    wild = fight_llm.Judgment(advantage=99, winning="贏", losing="輸")
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game.choose("act:train", fight=_judged(request, wild))
    assert fight.call_args.kwargs["shift"] == pytest.approx(encounter.advantage_shift(200, 15))
    game._fight = _judged(game.fight_request("act:train"), wild.model_copy(update={"advantage": -99}))
    with mock.patch.object(team, "fight", wraps=team.fight) as fight:
        game._squad_encounter("boss")
    assert fight.call_args.kwargs["shift"] == pytest.approx(encounter.advantage_shift(200, -15))


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
    assert game.state.player.stats["xinde"] == xinde + int(content.squads["thug"].reward_xinde * 0.3 + 0.5)
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

def test_a_drill_is_journaled_as_a_drill_without_a_battle_card(content, game):
    _training_factions(content)
    content.config.drill_reward_share = 1.0
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


def test_a_newcomer_below_the_threshold_gets_the_locations_event_instead_of_a_dialogue(content, game):
    """小鎮有交友事件（拜師）也有一位名望不夠的大勢人物：不 mock pick_event，交友照地點事件走，不算被擋在門外。"""
    _figure(content, fame=10)
    msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert game.state.pending_event is not None
    assert not any("連見都不見你" in m for m in msgs)


def test_dialogue_request_is_none_for_a_non_dialogue_option(content, game):
    _figure(content)
    game.state.player.fortune = True
    assert game.dialogue_request("act:explore") is None
    assert game.dialogue_request("move:lake") is None


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


def test_options_passes_tick_through_to_the_battle_status(game):
    calls, patched = _spy_battle_status(game)
    with patched:
        game.options(odds=False, tick=False)
        assert calls == [False]
        game.options(odds=False)
        game.options()
    assert calls == [False, True, True]  # 預設還是 tick=True，其他呼叫端的行為不變


def test_stopping_does_not_refund_the_stamina_paid_to_hurry(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 100
    _legacy_hurry(game, "cave")  # 7.5 分鐘：8 點
    msgs = game.choose("act:halt")
    assert game.state.player.stamina == 92
    assert "（趕路已經花掉的體力不退。）" in msgs


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


def test_an_old_journey_without_the_reroute_fields_still_loads():
    j = Journey.model_validate({"mode": "walk", "path": ["lake"], "arrive_at": [180.0]})
    assert (j.origin, j.share) == (None, 0.0)


def test_old_saves_without_road_fields_load(content, game):
    raw = game.state.model_dump(mode="json")
    del raw["player"]["leg_actions"], raw["player"]["surveyed"], raw["player"]["road_rewards_today"]
    loaded = GameState.model_validate(raw)
    assert loaded.player.leg_actions == set() and loaded.player.surveyed == set()
    assert loaded.player.road_rewards_today == {}


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


def test_old_saves_without_recent_sights_load(game):
    raw = game.state.model_dump(mode="json")
    del raw["player"]["recent_sights"]
    assert GameState.model_validate(raw).player.recent_sights == []


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


def test_the_fight_card_puts_every_level_up_on_one_line(content, game):
    """FB-074：升級的句子（本人一句一級、配點提示、每位同伴各一句）在「剛剛」的戰鬥卡片上收成一行，戰報頁與江湖紀錄照舊；
    點數跟狀態列同一個數（配了就少）。"""
    rules.learn_skill(game.state, game.content, "fist")
    _companion_on_the_team(game, exp=90)
    game.state.player.member.exp = 90
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)
    game.choose("act:train")
    record = game.state.battles[0]
    assert (record.levelups.you, record.levelups.points, record.levelups.mates) == (2, 1, [("韓鐵", 2)])
    card = game.battle_card()
    assert "升到第 2 級（可配 1 點）・韓鐵升到第 2 級　**得失**" in card  # 在結果的最後、得失的前面（前面可能有別的敘事，例如大勢的變動）
    assert card.count("升到第") == 2 and "升到第 2 級！" not in card and "屬性可以分配" not in card
    detail = game.battle_detail(record.id)  # 戰報頁：完整的句子
    assert "沈浪升到第 2 級！" in detail and "你有 1 點屬性可以分配（點名號展開）。" in detail and "韓鐵升到第 2 級！" in detail
    assert "沈浪升到第 2 級！" in game.state.journal[0].lines and "韓鐵升到第 2 級！" in game.state.journal[0].lines  # 江湖紀錄也是
    assert game.battle_extra_html() == ""  # 卡片底下的補充不重複句子
    game.allocate_stat("str")
    card = game.battle_card()
    assert "升到第 2 級・韓鐵升到第 2 級　**得失**" in card and "可配" not in card


def test_a_drill_gives_every_fighter_the_exp_too(content, game):
    _training_factions(content)
    content.config.drill_reward_share = 1.0
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    _companion_on_the_team(game, exp=90)
    walk_to(game, "lake")
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.world.get_companion("mate").level == 2
    assert "韓鐵升到第 2 級！" in msgs
    assert "韓鐵升到第 2 級！" in game.state.journal[0].lines


def test_a_drill_pays_three_tenths_of_the_squad(content, game):
    """戰鬥系統第八節：沒風險就拿得少，心得、經驗只給對手的三成（四捨五入）。"""
    _training_factions(content)
    squad = content.squads["thug"]
    squad.faction, squad.reward_xinde, squad.exp = "huang", 35, 40
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    xinde = game.state.player.stats.get("xinde", 0)
    msgs = game.choose("act:train")
    assert game.state.player.stats["xinde"] == xinde + 11  # 35 × 0.3 ＝ 10.5 → 11
    assert "心得 +11" in msgs
    assert any("經驗 +12" in c for c in game.state.journal[0].changes)  # 40 × 0.3


def test_a_place_with_two_figures_offers_one_audience_option(content, game):
    _hall(content, game)
    assert ids(game) == ["act:explore", "act:socialize", "act:call", "act:recruit", "move:lake"]
    assert _labels(game)["act:call"] == ("求見", True)


def test_a_place_with_two_figures_and_no_socialize_events_has_no_socialize_option(content, game):
    for cid in ("mate", "scholar"):
        ch = content.characters[cid]
        ch.kind, ch.recruit_at, ch.talk_at, ch.deep_interaction = "locked", None, "cave", True
    game.state.player.location = "cave"  # 寶洞沒有交友事件
    assert "act:socialize" not in ids(game) and "act:call" in ids(game)


def test_an_unavailable_audience_refunds_the_cost_and_closes_the_list(content, game):
    _hall(content, game)
    game.choose("act:call")
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("call:scholar")
    assert msgs == ["書生似乎無心多談，你只好先行告辭。"]
    p = game.state.player
    assert p.stamina == content.config.stamina_max
    assert p.pending_companion is None and not p.picking_audience


def test_choose_applies_a_prepared_audience_without_calling_the_model(content, game):
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=NEXT_TURN)
    with _no_model():
        msgs = game.choose("call:scholar", prepared=prepared)
    assert msgs == ["他笑了笑。"]
    assert game.state.player.pending_companion == "scholar"


def test_a_stale_audience_list_is_closed_where_two_figures_no_longer_stand(content, game):
    game.state.player.picking_audience = True  # 夾具的小鎮沒有大勢人物：例如內容改版後讀進來的舊存檔
    reloaded = Game(content, game.state, world=game.world)
    assert not reloaded.state.player.picking_audience


def test_the_brush_off_line_is_only_picked_when_it_is_used(content, game):
    """交友先抽地點事件，抽到了就不用打發話：不白花一次亂數（打發話是惰性算的）。小鎮有交友事件（拜師），韓鐵見不到。"""
    _stand_by_one_figure(content, game)
    with mock.patch.object(Game, "_brush_off", side_effect=AssertionError("有事件時不該挑打發話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "join"
    game.state.pending_event = None
    with mock.patch("tianxia.features.socialize.actions.pick_event", return_value=None),             mock.patch.object(Game, "_brush_off", return_value=["打發。"]) as brushed:
        assert game.choose("act:socialize") == ["打發。"]
    brushed.assert_called_once()


def test_socializing_with_a_figure_you_cannot_meet_uses_the_same_brush_off(content, game):
    cid = _stand_by_one_figure(content, game)
    with mock.patch("tianxia.features.socialize.actions.pick_event", return_value=None),             mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("被打發的不該叫模型")):
        msgs = game.choose("act:socialize")
    assert msgs == ["閒雜人等退下。（名望還差 30）"]
    assert game.state.player.pending_companion is None


def test_the_move_mode_is_screen_state_and_never_saved(content, game):
    """走法不存進存檔（企劃者決定），讀存檔開的 Game 一律從步行開始；網頁上每個請求的走法由 server.py 逐次設定。"""
    game.set_move_mode("dash")
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
    assert "#### 第 1 週・週一\n\n00:00　張角率三十六方同時起義。" in current and "第6天　賽季落幕" in past  # 本季照日子分段（見聞改版）


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
    day, _, clock = at.rpartition(" ")
    assert f"#### {day}\n\n{clock}　" in game.chronicle_text()  # 那一件大事寫進江湖史，時刻的寫法跟狀態列一樣（見聞改版：照日子分段）


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
    本週大事都在，狀態列的下一件是第 2 週那件；再推進一個曆時不會重複結算。下一季開出來也一樣。"""
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
    assert "#### 第 1 週・週一\n\n00:00　張角率三十六方同時起義。" in admin.chronicle_text()
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
    assert "#### 第 1 週・週一\n\n00:00　張角率三十六方同時起義。" in admin.chronicle_text().split("### 第 1 季")[0]


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


def _past_a_skipped_qinjie(content, world):
    """第一季、張曼成已經退場，時間推過第 7 週開頭：秦頡那件記成跳過。回傳那個 Game。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.state.world.figures["zhangmancheng"] = FigureState(status="retired")
    game.advance(calendar.week_start(7, content) + calendar.cal_hour_seconds(content))
    assert game.state.world.timeline["qinjie"].key == "skip"
    return game


def test_skipped_big_events_are_not_delivered(content, world):
    game = _past_a_skipped_qinjie(content, world)
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
    """張曼成已經退場：第 7 週秦頡那件記成跳過，本週大事只有同一週的盧植圍廣宗。"""
    game = _past_a_skipped_qinjie(content, world)
    assert [b.split("**")[1] for b in game.bulletin()] == ["盧植圍廣宗"]


def test_timestamps_read_like_the_calendar_when_the_season_is_season_one(content, world):
    """第一季（開關開著、這一季也蓋了章）：江湖紀錄（含「剛剛」）、江湖史、傳聞、戰報的時間都寫成季曆。"""
    install_season_one(content)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.sync(0.0)
    game.sync(calendar.cal_hour_seconds(content))  # 第 1 週週一 01:00：三十六方起義
    assert "剛剛　第 1 週・週一 01:00" in game.latest_entry_html()
    assert "#### 第 1 週・週一\n\n01:00　張角率三十六方同時起義。" in game.chronicle_text()
    assert "第 1 週・週一 01:00　三十六方同日起事。" in game.rumors_text()
    assert "第 1 週・週一 00:00" in game.journal_html(1, 5)  # 開季那一則
    assert "第 1 週・週一 01:00" in layers.header_text(game.state, content)


def test_timestamps_are_unchanged_with_the_switch_off(game):
    game.advance(HOUR + 5 * 60)
    game.state.world.chronicle.append(Rumor(time=game.state.world.time, text="測試大事。"))
    game.notice("測試")
    assert "剛剛　第1天 01:05" in game.latest_entry_html()
    assert "第1天　測試大事。" in game.chronicle_text()
    assert "第1天 01:05" in layers.header_text(game.state, game.content)


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


def _settle_without_fighters(game, definition) -> None:
    """沒人參戰：集結截止那一刻開打，再過一回合逾時就照 end_without_fighters 收場（有人刷新畫面才推進）。"""
    deadline = game.world.get_battle().muster_deadline_real
    for now in (deadline, deadline + definition.round_seconds):
        with at(game, now):
            game.options()


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
    assert all(word in uses["輕功"] for word in ("氣血", "落敗", "平手"))  # 身法：打完一場少掉一點氣血，落敗有機會閃成平手（14.4；點數收不回來）
    assert all(word in uses[names["con"]] for word in ("內功", "氣血上限", "內傷"))  # 根骨：內功、氣血上限、少受內傷
    assert all(word in uses[names["wis"]] for word in ("意境", "衝關")) and "閉關" not in uses[names["wis"]]  # 悟性：探索悟意境、衝絕學（閉關 Joy 2026-10-25 拿掉了）
    assert "持有" in uses[names["lore"]]  # 博聞：武學與意境的持有上限（設計 6.3）
    assert data["stat_uses_note"] == "事件的檢定看前四項。"  # 還沒有事件檢定博聞（PM 2026-10-05），見下一個測試


def test_the_stat_note_says_four_until_an_event_checks_lore():
    """「事件的檢定看前四項」是因為正式內容還沒有任何事件檢定（或隨口應對看）博聞。joy 加了第一個之後這條會失敗：
    把 art_cards.STAT_CHECK_NOTE 改回「事件的檢定也看這五項。」、這條跟著改（PM 2026-10-05）。"""
    from tianxia import art_cards

    real = real_content()
    stats = {ch.check.stat for e in real.events.values() for ch in e.choices if ch.check is not None}
    stats |= {e.free_text.stat for e in real.events.values() if e.free_text is not None}
    assert stats and "lore" not in stats
    assert art_cards.STAT_CHECK_NOTE == "事件的檢定看前四項。"


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


def test_a_companions_hp_comes_back_by_his_own_cap(game):
    """同伴的氣血也回到他自己（吃了根骨的）上限（人物資質設計 14.3）：韓鐵第 1 級根骨 6，上限 330，本人根骨 5 是 320。"""
    game.state.player.team = ["mate"]
    game.state.player.member.neili = 0.0
    game.world.update_companion("mate", lambda p: setattr(p, "neili", 0.0))
    game._advance_player_local(HOUR / 10)
    player, mate = game.state.player.member.neili, game.world.get_companion("mate").neili
    assert player > 0 and mate == pytest.approx(player * 330 / 320)


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


# ── 武學的功效（武學與成長設計 13.2、13.4；計畫六 Task 3）：獎勵、打完回氣血、遊歷的體力 ──────────────


def _wear_trait_art(game, name, attribute, trait_list, special=None, kind="武學", quality="下品"):
    """合成武學直接登記到全服、穿到本人身上（品質照 quality）。
    武學重構：身上那一份的功效由槽裡的意境決定（arts.apply 蓋掉登記的 traits），所以 trait_list 每一種屬性造一個私有意境
    （強度＝那一種的層數，最多 ●●●；陰陽虛實沒有基本意境，只能這樣造）、special 另造一個帶特別功效的意境，全部裝進槽；
    相容屬性寫 attribute（武學的屬性照它），槽不夠就加 slot_adjust。"""
    from tianxia import arts as arts_mod
    from tianxia.martial_arts import Insight

    p = game.state.player
    cells = []
    for i, attr in enumerate(dict.fromkeys(trait_list)):
        iid = f"悟:{name}{i}"
        p.own_insights[iid] = Insight(id=iid, name=f"{name}{attr}", attribute=attr)
        p.insight_strength[iid] = min(arts_mod.MAX_STRENGTH, trait_list.count(attr))
        cells.append(iid)
    if special:
        iid = f"悟:{name}特"
        p.own_insights[iid] = Insight(id=iid, name=f"{name}特", attribute=attribute, secret_special=special)
        cells.append(iid)
    p.insights = [*p.insights, *cells]
    art = generate_from_name(name, kind, name, attribute=attribute).model_copy(
        update={"origin": "fused", "affinity": [attribute],
                "slot_adjust": max(0, len(cells) - arts_mod.slot_count(game.content, quality))},
    )
    game.world.claim_skill_name(art)
    p.art_slots[art.id] = cells
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    setattr(game.state.player.member, slot, art.id)
    game.state.player.art_quality[art.id] = quality
    return art


def _record_of(game, tier):
    squad = game.content.squads["thug"].model_copy(update={"reward_xinde": 10, "exp": 20})
    result = encounter.EncounterResult(tier=tier, margin=10, our_power=50, difficulty=5)
    return squad, battlelog.new_record(game.state, game.content, game.world, squad, result, "train")


def test_rewards_are_untouched_without_momentum_or_insight(game):
    """沒有乘勝、悟招的人（這裡什麼武學都沒有）：心得、經驗、戰報跟以前一模一樣。"""
    game.state.player.member.wugong_id = game.state.player.member.neigong_id = None
    squad, record = _record_of(game, "大勝")
    before = game.state.player.stats.get("xinde", 0)
    msgs = game._battle_rewards(squad, record)
    assert game.state.player.stats["xinde"] - before == 10 and record.xinde == 10 and record.exp == 20
    assert "心得 +10" in msgs


def test_light_body_only_touches_the_journey_cost(game):
    base = dict(game.content.config.action_cost)
    _wear_trait_art(game, "輕身腿", "快", ["快"], special="qingshen")
    costs = game._action_costs()
    assert costs["explore"] == base["explore"] and costs["socialize"] == base["socialize"]
    assert game.content.config.action_cost == base  # 設定本身沒被改


@pytest.mark.slow
@pytest.mark.parametrize("traits_worn", [(), ("慢", "慢", "慢"), ("虛", "虛", "虛"), ("剛", "剛", "剛")])
def test_the_models_push_in_a_big_fight_is_the_same_points_with_or_without_roll_traits(game, traits_worn):
    """Task 3 審查 I1：判讀的優勢（最多 ±15 個百分點，武學與成長設計 8.3）走完整條路（_fight_with → team.fight →
    resolve_encounter）推的勝算，不因為本人帶了穩（慢）、險（虛）、破甲（剛）而變多變少：每一組都剛好 +15 個百分點。
    運氣用均勻切成的格子當亂數，沒有抽樣誤差；難度挑成沒有優勢時剛好五成贏。"""
    from tianxia import fight_llm

    if traits_worn:
        _wear_trait_art(game, "試招拳", traits_worn[0], list(traits_worn), quality="絕學")
    base_power = game._fight_with(game.content.squads["thug"], None).our_power
    cut = team.trait_mods(game.content, traits.loadout(game.state, game.content, game.world)).difficulty_cut
    difficulty = base_power / (1.15 * (1 - cut))  # 險勝線在當作的難度的 15%：威力剛好到線，運氣要到 0 才過，五成
    game.content.squads["thug"] = game.content.squads["thug"].model_copy(update={"difficulty": difficulty})
    squad = game.content.squads["thug"]

    grid = 400  # 均勻格點：勝負對運氣是一道門檻，格點最多差 1/400＝0.25%，比下面容許的 1% 小（測試整併第 3 區，原本 2000）

    def win_rate(judged):
        wins = 0
        for i in range(grid):
            game.rng = FixedRandom((i + 0.5) / grid)
            wins += game._fight_with(squad, judged).tier in team.WIN_TIERS
        return wins / grid

    base = win_rate(None)
    assert base == pytest.approx(0.5, abs=0.01)
    pushed = win_rate(fight_llm.Judgment(advantage=15))
    assert pushed - base == pytest.approx(0.15, abs=0.01)
    assert win_rate(fight_llm.Judgment(advantage=-15)) - base == pytest.approx(-0.15, abs=0.01)


def test_actions_that_cost_nothing_do_not_build_the_cost_table(game):
    """不花體力的行動（序章的調息、分道揚鑣……）不必算各行動的體力（要翻武學的資料）；要花體力的才算、而且只算一次。"""
    spy = mock.Mock(wraps=game._action_costs)
    game._action_costs = spy
    game._act("rest")
    game._act("part")
    assert spy.call_count == 0
    game._act("explore")
    assert spy.call_count == 1


@pytest.mark.parametrize("tier", ["大勝", "僵持", "落敗"])
@pytest.mark.parametrize("trait_list, special", [
    (["柔", "柔", "柔"], None),  # 化勁：少扣
    (["剛"], "budong"),  # 不動：不受內傷
    (["陰", "陰", "陰"], None),  # 吸取：打贏回血
    (["剛"], "huichun"),  # 回春：不論勝負回血
])
def test_the_rounds_still_add_up_to_the_toll_with_hp_traits(game, trait_list, special, tier):
    """計畫六對氣血的四個功效（化勁、不動、吸取、回春）都不動回合：回合裡每一句「你氣血 -N」加起來，等於戰報上扣氣血那一筆
    （回血是回合之後的事，另外一行「氣血 +N」）。"""
    walk_to(game, "lake")
    _wear_trait_art(game, "護體拳", trait_list[0], trait_list, special=special)
    with _forced(tier):
        game.choose("act:train")
    record = game.state.battles[0]
    told, shown = _told_and_shown(record)
    assert told > 0 and shown == told, (told, shown, record.changes, record.rounds)


# ── 功效的演出句（計畫六 Task 4）：只在功效真的改到結果時才演（武學與成長設計 13.6）────────────


def _fought(game, tier, *, guarded=False, wounded=False, empty=False, hp=None, kind="train"):
    """在湖邊打一場、結果寫死（team.fight 不擲骰），回傳那一場的戰報。wounded：開打前氣血低於上限（100）；empty：氣血見底；
    hp：開打前的氣血（本人上限 320）。"""
    if game.state.player.location != "lake":
        walk_to(game, "lake")
    if hp is not None:
        game.state.player.member.neili = hp  # 走路會自然回氣血，所以走完才設
    elif wounded or empty:
        game.state.player.member.neili = 0.0 if empty else 100.0
    result = encounter.EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5, guarded=guarded)
    with mock.patch.object(team, "fight", return_value=result):
        if kind == "wild":
            game._squad_encounter("thug", wild=True)
        else:
            game.choose("act:train")
    return game.state.battles[0]


def _said(record):
    """戰報上這一場所有功效的演出句，開頭的〔功效名〕湊成集合。"""
    return {line[1:line.index("〕")] for line in record.trait_before + record.trait_after}


def test_without_first_strike_a_slow_player_is_hit_first(game):
    """對照：沒有先手時，身法比對手低的人在每一回合都是對手先出手（所以上面那一條是先手改的，不是本來就這樣）。"""
    game.state.player.member.wugong_id = "basic_fist"  # 屬實：【厚】，不帶先手
    game.state.player.stats["agi"] = 1
    squad = game.content.squads["boss"]
    record = battlelog.new_record(game.state, game.content, game.world, squad,
                                  encounter.EncounterResult(tier="落敗", margin=-100, our_power=10, difficulty=200), "train")
    game._play_rounds(record, squad, "落敗", 30)
    assert all(line.split("　", 1)[1].startswith(squad.name) for line in record.rounds)
    assert record.trait_before == []


def test_nothing_is_told_when_no_trait_is_worn(game):
    game.state.player.member.wugong_id = game.state.player.member.neigong_id = None
    record = _fought(game, "大勝")
    assert record.trait_before == [] and record.trait_after == [] and record.guarded is False


def test_thick_is_told_only_when_the_fight_began_wounded(game):
    """F11：厚只在開打前氣血低於上限時才有用（見底的威力下限）：滿血的人打輸一場掉了氣血，也不演〔厚〕。"""
    _wear_trait_art(game, "厚土拳", "實", ["實"])
    assert "厚" not in _said(_fought(game, "落敗"))
    game.state.battles.clear()
    assert "厚" in _said(_fought(game, "落敗", wounded=True))


def test_a_player_with_old_wounds_counts_as_wounded_even_at_full_health(game):
    """內傷讓「滿血」的上蓋低於上限（根骨、內傷設計）：氣血記成 None（回滿了）也算帶傷，厚照樣有用、照樣演。"""
    _wear_trait_art(game, "厚土拳", "實", ["實"])
    walk_to(game, "lake")
    game.state.player.member.injury = 60.0
    game.state.player.member.neili = None
    result = encounter.EncounterResult(tier="落敗", margin=0, our_power=10, difficulty=5)
    with mock.patch.object(team, "fight", return_value=result):
        game.choose("act:train")
    assert "厚" in _said(game.state.battles[0])


def _thick_lines(game, tier, hp, count=40):
    """帶【厚】、開打前氣血是 hp 的人，連打 count 場（流水號不同、演出句的亂數就不同）：每一場的〔厚〕那一句（沒演的不算）。"""
    _wear_trait_art(game, "厚土拳", "實", ["實"])
    squad = game.content.squads["thug"]
    lines = []
    for number in range(1, count + 1):
        member = game.state.player.member
        member.neili, member.injury = hp, 0.0
        result = encounter.EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5)
        record = battlelog.new_record(game.state, game.content, game.world, squad, result, "train")
        record.id = number
        _, hp_lost, facts = game._take_toll(tier)
        game._play_rounds(record, squad, tier, hp_lost, facts)
        lines += [line for line in record.trait_after if line.startswith("〔厚〕")]
    return lines


def test_thick_is_told_at_zero_blood_where_it_helps_most(game):
    """Task 4 審查 M3：氣血見底時厚把威力的下限從五成拉到更高，是它最有用的時候；這一場一滴血都沒得扣（hp_lost 是 0）也要演，
    而且 S1 那句「氣血見底，……硬撐」就是寫這個情形的。"""
    _wear_trait_art(game, "厚土拳", "實", ["實"])
    record = _fought(game, "落敗", empty=True)
    assert not any(c.startswith("氣血 -") for c in record.changes) and "厚" in _said(record)


def test_the_bottom_variant_of_thick_is_for_the_bottom_only(game):
    """氣血見底那一句只在氣血真的低（開打前剩三成以下，engine.LOW_HP_RATIO）時才挑；95% 氣血的人不會被寫成「氣血見底」，
    見底的人三句都可能（正是那一句寫的情形，同時也沒有排除別句）。"""
    from tianxia.engine import LOW_HP_RATIO

    assert LOW_HP_RATIO == 0.3
    cap = 320.0
    healthy = _thick_lines(game, "落敗", 0.95 * cap)
    assert healthy and not any("氣血見底" in line for line in healthy)  # 帶傷、不見底：有演，但沒有那一句
    low = _thick_lines(game, "落敗", 0.0)
    assert any("氣血見底" in line for line in low) and any("氣血見底" not in line for line in low)  # 見底：三句都可能
    assert any("氣血見底" in line for line in _thick_lines(game, "落敗", LOW_HP_RATIO * cap))  # 剛好三成算見底（含）
    assert not any("氣血見底" in line for line in _thick_lines(game, "落敗", LOW_HP_RATIO * cap + 1))


def test_the_bottom_line_of_thick_is_marked_in_the_real_content():
    """「氣血見底」是引擎認的暗號（battlelog.LOW_HP_MARKS）：S1 的三句厚裡剛好一句有它——內容改掉那一句的話這條會失敗，
    不會悄悄讓見底的句子變成誰都能抽。"""
    from tianxia import battlelog

    real = real_content()
    marked = [line for line in real.trait_lines["厚"] if battlelog.LOW_HP_MARKS["厚"] in line]
    assert len(real.trait_lines["厚"]) == 3 and len(marked) == 1


@pytest.mark.parametrize("hp, told", [(100.0, True), (None, False)])
def test_thick_is_told_in_a_wounded_story_battle_too(game, hp, told):
    """劇情戰也吃厚拉高的下限（team_conditions 照舊算）：帶傷打、演；滿血打、不演。劇情戰不扣氣血，所以只有〔厚〕這一個氣血的功效會演。"""
    _wear_trait_art(game, "厚土拳", "實", ["實"])
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.state.player.member.neili = hp  # 走路會自然回氣血，所以走完才設
    result = encounter.EncounterResult(tier="落敗", margin=0, our_power=10, difficulty=200)
    with mock.patch.object(team, "fight", return_value=result):
        game.choose("choice:0")
    record = game.state.battles[0]
    assert record.kind == "event" and ("厚" in _said(record)) is told
    assert not ({"化勁", "不動", "吸取", "回春"} & _said(record))


def test_momentum_is_not_told_for_a_story_battle_that_gives_nothing(game):
    _wear_trait_art(game, "得勝拳", "陽", ["陽"])  # 夾具的翻江龍沒有獎勵：沒有東西可以多給
    walk_to(game, "lake")
    game.choose("act:socialize")
    won = encounter.EncounterResult(tier="大勝", margin=50, our_power=300, difficulty=200)
    with mock.patch.object(team, "fight", return_value=won):
        game.choose("choice:0")
    assert "乘勝" not in _said(game.state.battles[0])


SOFT_AND_STILL = [(None, "柔", ["柔"], "化勁"), ("budong", "剛", ["剛"], "不動")]


@pytest.mark.parametrize("special, attribute, trait_list, said", SOFT_AND_STILL)
def test_soft_and_still_are_not_told_for_a_fight_that_took_no_blood(game, special, attribute, trait_list, said):
    """氣血已經見底的人打輸：這一場一滴氣血都沒得扣，化勁沒有東西可以少扣、不動沒有東西可以不傷，不演。"""
    _wear_trait_art(game, "護體拳", attribute, trait_list, special=special)
    record = _fought(game, "落敗", empty=True)
    assert not any(c.startswith("氣血 -") for c in record.changes) and said not in _said(record)


def test_momentum_is_not_told_when_the_squad_gives_nothing_to_multiply(game):
    _wear_trait_art(game, "得勝拳", "陽", ["陽"])
    game.content.squads["thug"] = game.content.squads["thug"].model_copy(update={"reward_xinde": 0, "exp": 0})
    assert "乘勝" not in _said(_fought(game, "大勝"))


def test_guard_is_silent_when_nothing_was_guarded(game):
    _wear_trait_art(game, "護身拳", "實", ["實"], special="huming")
    record = _fought(game, "僵持")  # 一般的僵持：護命沒有改判
    assert record.guarded is False and not any(note.startswith("〔護命〕") for note in record.notes)


def test_a_dodge_and_a_guard_do_not_both_speak(game):
    """閃避的那一句還是 DODGE_NOTE；沒有被護命改判就不會有護命的那一句。"""
    game.state.player.member.wugong_id = "basic_fist"
    record = _fought(game, "落敗")
    assert not any(note.startswith("〔") for note in record.notes)


def test_a_fight_with_and_without_traits_uses_the_same_game_rng(content, world):
    """演出句用「名號｜戰報流水號」那一份亂數（跟回合一樣），不碰 Game.rng：同一個種子、同樣的一場仗，帶功效的人與沒帶的人，
    打完之後 Game.rng 吐出來的下一個數字一樣。"""
    content.config.train_event_chance = 0.0
    results = []
    for traits_on in (False, True):
        game = Game.new(content, "乙甲"[traits_on], rng=random.Random(5), world=world)
        if traits_on:
            _wear_trait_art(game, "先手拳", "快", ["快", "柔"])
        else:
            game.state.player.member.wugong_id = None
        walk_to(game, "lake")
        result = encounter.EncounterResult(tier="大勝", margin=0, our_power=10, difficulty=5)
        with mock.patch.object(team, "fight", return_value=result):
            game.choose("act:train")
        results.append(game.rng.random())
    assert results[0] == results[1]


def test_a_story_battle_takes_no_blood_so_nothing_is_healed(game):
    """劇情戰不扣氣血（計畫三 G5）：吸取與回春也不動，戰報上沒有「氣血 +N」。"""
    _wear_trait_art(game, "回春拳", "剛", ["剛"], special="huichun")
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.state.player.member.neili = 100.0  # 走路會自然回氣血，所以走完才設
    game.choose("choice:0")
    assert game.state.player.member.neili == 100.0
    assert not any(c.startswith("氣血") for c in game.state.battles[0].changes)


# ── 伺服器自己的排程（線上架構設計第四節）：沒有玩家的 Game 推全服的事 ──────────────


def test_world_tick_advances_the_shared_season_once(content, game):
    """排程推過之後玩家再同步，同一段現實時間不會推兩次（Review Focus 1）。"""
    ticker = Game.for_world(content, game.world, rng=random.Random(0))
    ticker.world_tick(5000.0)  # 第一下只記下時鐘
    before = game.world.get_season().time
    ticker.world_tick(5600.0)
    after = game.world.get_season().time
    assert after == pytest.approx(before + 600 * content.config.time_scale)
    game.sync(5600.0)
    assert game.world.get_season().time == pytest.approx(after)


def test_world_tick_closes_muster_and_times_out_rounds_with_nobody_online(content, game):
    """沒人在線：集結截止自動分配、回合逾時代選、全員到齊就結算、收場套結果（以前都要有人刷新畫面）。"""
    definition = _install_battle_def(content)  # 集結 600 秒、回合 120 秒、一幕一回合
    game.world.start_battle(definition, now=1000.0)
    with at(game, 1000.0):
        game.choose("battle:join:guan")
    open_characters().save(game.state)  # 沈浪下線
    ticker = Game.for_world(content, game.world, rng=random.Random(3))
    ticker.world_tick(1000.0 + 601)
    assert game.world.get_battle().phase == "active"
    ticker.world_tick(1000.0 + 601 + 121)  # 回合逾時：系統代選、結算；一幕一回合就收場
    (_, done), = game.world.ended_battles()
    assert not done.unfinished and done.outcome_title == "官軍大勝"
    back = Game(content, open_characters().load("沈浪"), rng=random.Random(4), world=game.world)
    back.sync(1000.0 + 800)
    assert any("測試決戰" in e.title for e in back.state.journal)  # 參戰者回來補到戰報（W13）


def test_world_tick_opens_and_settles_a_scheduled_showdown_with_nobody_online(content, world):
    """第一季：排定的時間一到，排程那一下就開集結（不用等誰刷新）；沒人參戰，集結截止再一回合逾時，照前線起點判、
    寫進時間軸（Review Focus 4 的排程版）。"""
    _showdown_game(content, world)  # 裝好第一季內容、決戰與陣營，種好季；之後完全不用這個玩家
    ticker = Game.for_world(content, world, rng=random.Random(5))
    ticker.world_tick(0.0)  # 記下時鐘
    season = world.get_season()
    until_open = (season.schedule["changshe_fire"] - season.time) / content.config.time_scale
    ticker.world_tick(until_open + 1.0)
    battle = world.get_battle()
    assert (battle.battle_id, battle.phase) == ("changshe_fire", "muster")
    definition = content.battles["changshe_fire"]
    t = battle.muster_deadline_real + 1.0
    ticker.world_tick(t)
    ticker.world_tick(t + definition.round_seconds + 1.0)
    assert "changshe_fire" in world.get_season().timeline


def test_a_forge_request_while_the_season_is_preparing_stays_none_even_if_naming_outside(game):
    """賽季籌備中什麼都不能做：named_outside 只換掉「沒有 client」那一條，籌備中照舊不開單。"""
    p = game.state.player
    p.insights, p.stats["xinde"], p.stamina = ["feng", "huo"], 100, 150
    game.client = None
    with mock.patch.object(game.world, "season_phase", return_value="preparing"):
        assert game.forge_request(None, ["feng", "huo"], named_outside=True) is None


# ── 一次畫面建構裡，「籌備中嗎」只讀一次共用狀態 ──────────────────────────


def _count_phase_reads(game):
    reads = []
    real = game.world.season_phase
    game.world.season_phase = lambda: reads.append(1) or real()
    return reads


def test_preparing_is_read_once_inside_a_phase_memo_and_every_time_outside(game):
    reads = _count_phase_reads(game)
    for _ in range(3):
        assert game._preparing() is False
    assert len(reads) == 3  # 沒有範圍：每次都讀（動作裡要的是最新的）
    reads.clear()
    with game.phase_memo():
        for _ in range(3):
            game._preparing()
        with game.phase_memo():  # 巢狀：還是外層那一份，不重讀
            game._preparing()
    assert len(reads) == 1
    game._preparing()
    assert len(reads) == 2  # 範圍結束，記住的丟掉


def test_a_phase_memo_ends_when_the_build_breaks(game):
    reads = _count_phase_reads(game)
    with pytest.raises(RuntimeError):
        with game.phase_memo():
            game._preparing()
            raise RuntimeError("畫面建到一半壞了")
    reads.clear()
    game._preparing()
    game._preparing()
    assert len(reads) == 2  # 範圍沒有留到下一個動作


def test_everyday_options_use_the_memoed_preparing(game):
    """選單（_everyday_options）走同一個 _preparing：在範圍裡建一次選單只讀一次。"""
    reads = _count_phase_reads(game)
    with game.phase_memo():
        game.options()
        game.options()
    assert len(reads) == 1
