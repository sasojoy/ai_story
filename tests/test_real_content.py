"""跑真正的 content/ 內容（黃巾之亂・三國重皮），不是 tests/fixtures/content 的測試夾具。

跟本機 Ollama 有關的路徑（companion_agent.py 的深度對話、定期記憶梳理）一律 monkeypatch
掉：這裡要驗證的是內容本身的結構完整性與遊戲規則，不是要連真正的模型（會慢、會不穩定，
也會讓 CI 環境在沒裝 Ollama 時整個掛掉）。
"""
from __future__ import annotations

import html
import math
import random
import re
from collections import deque
from pathlib import Path
from unittest import mock

import pytest

from tianxia import companion_agent, fusion, roster, team
from tianxia.atlas import region_of
from tianxia.bot import play_season
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.mapart import BANNER_BOX, FRAME_INSIDE
from tianxia.mapview import CURRENT_RING, NODE_SIZE, render_map, render_minimap, text_width
from tianxia.ollama_client import OllamaClient
from tianxia.team import fight

CONTENT_DIR = Path(__file__).parent.parent / "content"

FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他微微頷首，若有所思。", options=["繼續交談", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)
FAKE_CONSOLIDATION = companion_agent.MemoryConsolidation(
    relationship_summary="彼此的關係穩定發展。", new_milestones=["閒聊了幾句家常"],
)


def _fake_chat_structured(self, messages, response_model, **kwargs):
    """companion_agent 兩條會連 Ollama 的路徑（單輪對話生成、定期記憶梳理）共用的假回應，
    依 response_model 分流回傳合理的樣板值，讓 play_season 快速、確定地跑完。"""
    if response_model is companion_agent.CompanionTurn:
        return FAKE_TURN
    if response_model is companion_agent.MemoryConsolidation:
        return FAKE_CONSOLIDATION
    return response_model()


def _fake_chat_text(self, messages, **kwargs):
    """flavor.py 的裝飾句潤色（重遊地點/重複事件/江湖大事）也會連真正的 Ollama，同樣要假掉，
    不然整季模擬每次重遊/重複觸發都會多一次真的網路呼叫，把測試拖到以分鐘計。"""
    return "（測試用潤色句）"


@pytest.fixture(autouse=True)
def no_real_ollama():
    with mock.patch.object(OllamaClient, "chat_structured", _fake_chat_structured), \
         mock.patch.object(OllamaClient, "chat_text", _fake_chat_text):
        yield


@pytest.fixture(scope="module")
def content():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True  # 這個檔案測的是開打後的內容；正式設定另有一個測試檢查
    return c


# ── 內容結構完整性 ────────────────────────────────────────


def test_real_content_loads():
    c = load_content(CONTENT_DIR)
    assert 30 <= len([loc for loc in c.locations.values() if not loc.prologue_only]) <= 40  # 草廬（序章專用）另外算
    assert {t.id for t in c.scenario.trends} == {"huangjin", "yuxi", "yingru", "nanyang", "jizhou", "geju"}


def test_the_season_one_switch_stays_off_until_the_condensed_build_ships():
    """濃縮版做到一半時 main 也會換上試玩伺服器：開關關著、季長照舊，正在跑的那一季才不會被提早收掉或套上半套規則。"""
    config = load_content(CONTENT_DIR).config
    assert config.season_one is False
    assert config.season_days == 14


def test_real_content_waits_for_the_admin_to_open_the_season():
    assert load_content(CONTENT_DIR).config.auto_open_first_season is False


def test_travel_settings_follow_the_map_design(content):
    cfg = content.config
    assert cfg.stamina_regen_seconds == 180 and cfg.rest_regen_multiplier == 2
    assert cfg.road_factor == {"官道": 0.8, "路": 1.0, "山路": 1.5}
    assert (cfg.hurry_stamina_per_minute, cfg.dash_stamina_per_minute) == (1, 2)
    assert cfg.travel_minutes_per_unit > 0  # 跟著地圖座標走（第二步重畫地圖時 PM 會改），這裡不寫死


def test_the_road_sights_are_the_thirty_written_for_season_one(content):
    """路上見聞的內容稿（2026-10-03-第一季陣營內容-路上見聞.md 第二節）：30 則，心得 23、銀兩 4、素材 3。"""
    sights = content.road_sights
    assert len(sights) == 30 and all(sight_id.startswith("sight_") for sight_id in sights)
    effects = [sight.effect for sight in sights.values()]
    assert sum("xinde" in e.stats for e in effects) == 23
    assert sum("silver" in e.stats for e in effects) == 4
    assert sum(bool(e.materials) for e in effects) == 3
    assert content.config.road_sight_chance == 0.3  # 三成：正式內容用預設值


def test_the_mentor_explains_travel_and_sitting_down(content):
    """步行、趕路、疾行與打坐現在由師父講：出師那一步（第 11 步）講走法與體力，打坐那一步（第 7 步）講打坐。"""
    texts = {step.id: step.text for step in content.tutorial.steps}
    assert all(word in texts["p11_farewell"] for word in ("步行", "趕路", "疾行", "體力"))
    assert "打坐" in texts["p7_rest"]


def _walk_the_hut(content, world, ambush="choice:0", sight="choice:0"):
    """真人照著序章走：遇險、拜師、看修練頁、探索悟意境、合成、換上並練到第三成、修練、打坐、雪恥、配點、熔雜學（剛走完前十步、
    還站在草廬）。回傳（遊戲，合成出來的那一門）。"""
    from tianxia import prologue
    from tianxia.engine import Game

    game = Game.new(content, "新人", rng=random.Random(0), world=world, prologue=True)
    game.world.open_season(game.content, now=0.0)
    for option in (ambush, "choice:0"):  # 遇險（三選一）、拜師
        game.choose(option)
    game.view_tab("practice")
    game.choose("act:explore")
    game.choose(sight)  # 四景四選一
    insight = game.state.player.insights[0]
    game.forge("jichu_quanjiao", [insight], proposed=(None, ""))
    art = prologue.fused_arts(game.state, content, game.world)[0]
    game.switch_art(art.id)
    game.practice("武學")
    game.practice("武學")
    game.cultivate(art.id)
    game.choose("act:rest")
    game.choose("act:train")
    game.allocate_stat("str")
    game.melt_art("manniu_quan")
    return game, art


@pytest.mark.parametrize("ambush, first_words", [
    ("choice:0", "拿身子去擋柴刀"), ("choice:1", "抄根扁擔就敢往上衝"), ("choice:2", "喊一嗓子『官兵來了』"),
])
@pytest.mark.parametrize("sight, art_name", [
    ("choice:0", "穿林腿"), ("choice:1", "坐山拳"), ("choice:2", "回瀾手"), ("choice:3", "烈爐拳"),
])
def test_every_way_through_the_real_hut_reaches_yingchuan_with_a_preset_art(content, world, ambush, first_words, sight, art_name):
    """遇險的三個選項各接到自己的拜師那一則（師父醒來的第一句照選項換）、四景各悟一個意境、各合出自己的師門功夫；十二條路都走得到潁川。"""
    from tianxia.engine import Game

    peek = Game.new(content, "偷看", rng=random.Random(0), world=world, prologue=True)
    peek.world.open_season(content, now=0.0)
    peek.choose(ambush)
    assert first_words in peek.scene_text()  # 拜師那一則開頭的評語照剛才選的那一個
    game, art = _walk_the_hut(content, world, ambush, sight)
    assert (art.name, art.preset, art.creator) == (art_name, True, None)
    game.choose("move:yingchuan")
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert game.state.player.location == "yingchuan" and game.state.player.tutorial_step == content.tutorial.prologue_steps


@pytest.mark.parametrize("old_step, new_step", [(0, 11), (3, 11), (6, 11), (7, 12)])
def test_a_save_from_before_the_prologue_is_never_sent_to_the_real_hut(content, world, old_step, new_step):
    """換版當下已經有的角色（舊引導八步：t1～t6、第一季的 t7、t8）：讀檔後不管走到哪一步都站在原地、不進草廬；步數換算成新的
    （不分季的舊六步當作走過序章，t7、t8 接在序章後面）。"""
    from tianxia.state import ONBOARDING_VERSION

    game = Game.new(content, "老手", rng=random.Random(0), world=world)
    p = game.state.player
    p.onboarding, p.tutorial_step = 0, old_step  # 換版之前存的樣子：沒有版本章、步數是舊的編號
    here = p.location
    again = Game(content, game.state, world=world)
    q = again.state.player
    assert (q.tutorial_step, q.onboarding, q.location) == (new_step, ONBOARDING_VERSION, here)
    assert again.state.pending_event is None and not q.guide_skipped


def test_the_real_prologue_text_has_no_placeholder_left_over(content):
    """{武學} 只許出現在「收起」那一行（Game.guide_box 換成合成出來的那一門）與步驟的話裡；事件與四景沒有要換的字。"""
    for event_id in ("prologue_ambush", "prologue_apprentice_dang", "prologue_apprentice_bian", "prologue_apprentice_han", "prologue_insight"):
        event = content.events[event_id]
        texts = [event.title, event.text] + [x for ch in event.choices for x in (ch.text, ch.effect.text)]
        assert not any("{" in text for text in texts), event_id
    steps = {step.id: step for step in content.tutorial.steps}
    assert "{武學}" in steps["p5_level"].line and "{武學}" in steps["p6_refine"].line
    assert not any("{" in step.text for step in content.tutorial.steps)
    assert content.tutorial.outro == ""  # 第一季兩步走完不再有說書人的結語


def test_the_real_prologue_walks_to_yingchuan(content, world):
    from tianxia import atlas

    game, art = _walk_the_hut(content, world)
    assert art.name == "穿林腿" and art.preset
    assert game.state.player.stats["xinde"] == content.config.start_stats["xinde"]  # 心得的帳：20 → −5 → −3 → +8 → 20
    silver = game.state.player.stats["silver"]
    game.choose("move:yingchuan")
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    p = game.state.player
    assert p.location == "yingchuan" and p.tutorial_step == content.tutorial.prologue_steps == 11
    assert p.stats["silver"] == silver + 30 and p.stamina == content.config.stamina_max
    assert "mentor_hut" not in atlas.visible_locations(game.state, content)


def test_every_battle_is_fought_in_the_region_where_it_starts(content):
    for th in content.scenario.thresholds:
        if th.starts_battle and th.location:
            assert content.battles[th.starts_battle].region == region_of(content, th.location).id, th.id


def test_all_locations_reachable_from_start(content):
    start = content.scenario.start_location
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in content.locations[queue.popleft()].connections:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(content.locations)


def test_real_content_has_enough_events(content):
    total_choices = sum(len(e.choices) for e in content.events.values())
    assert len(content.events) >= 30 and total_choices >= 30
    assert sum(e.qiyu for e in content.events.values()) >= 1


def test_start_location_has_no_enemies(content):
    """開局地點不該一站出門就撞見敵人，符合「先探索一下」的新手引導語氣。"""
    assert content.locations[content.scenario.start_location].enemies == []


# ── 人物誌：18 位黃巾之亂人物 ─────────────────────────────


FORMER_RECRUITABLE = ["caocao", "liubei", "guanyu", "zhangfei", "sunjian", "yuanshao", "taoqian"]


def test_all_eighteen_historical_figures_are_locked(content):
    """第一季設計第一節：大勢人物這一季都不開放招募（人物誌補遺加了波才、張曼成、趙弘，共 18 位）。"""
    assert len(content.characters) == 18
    assert all(ch.kind == "locked" for ch in content.characters.values())


def test_every_figure_has_a_place_to_talk_and_nobody_has_a_recruit_location(content):
    for ch in content.characters.values():
        assert ch.talk_at in content.locations, ch.id
        assert ch.recruit_at is None, ch.id


def test_the_former_recruitable_seven_keep_their_signature_skills(content):
    for cid in FORMER_RECRUITABLE:
        ch = content.characters[cid]
        assert ch.starting_wugong in content.skills and ch.starting_neigong in content.skills, cid


def test_every_figure_opts_into_deep_dialogue(content):
    """設計文件四.3：這一期黃巾之亂人物全部開放深度 LLM 對話（鎖定的龍頭人物也一樣，
    只是還沒有 recruit_at 讓玩家在地圖上找到他們，見 engine.py::_deep_interaction_target）。"""
    assert all(ch.deep_interaction for ch in content.characters.values())


def test_every_figure_has_three_brush_off_lines(content):
    """設計 9.1、內容表《打發話與回合句型》第一節：每位名將三句他自己口吻的打發話，不寫數字（名望與階級的落差由程式接在後面）。"""
    for cid, ch in content.characters.items():
        assert len(ch.brush_off) == 3 and len(set(ch.brush_off)) == 3, cid
        for line in ch.brush_off:
            assert line.strip() and len(line) <= 40 and not re.search(r"\d", line), (cid, line)


def test_a_newcomer_calling_on_a_figure_hears_one_of_his_own_lines_and_the_fame_gap(content):
    game = Game.new(content, "試玩者", rng=random.Random(1))
    game.world.open_season(game.content, now=0.0)
    game.state.player.location = content.characters["luzhi"].talk_at
    stamina = game.state.player.stamina
    (line,) = game.choose("call:luzhi")
    spoken, _, hint = line.rpartition("（")
    assert spoken in content.characters["luzhi"].brush_off
    assert hint == f"名望還差 {content.characters['luzhi'].audience_fame - game.state.player.stats.get('fame', 0)}）"
    assert game.state.player.stamina == stamina and game.state.player.pending_companion is None


def test_lu_bei_faction_all_gather_at_zhuo_county(content):
    zhuo_faction = {cid for cid, ch in content.characters.items() if ch.talk_at == "zhuo_county"}
    assert zhuo_faction == {"liubei", "guanyu", "zhangfei"}


# ── 招募（roster.py）跑在真正的內容上 ──────────────────────


def test_nobody_is_recruitable_anywhere(content):
    from tianxia.sqlite_world import open_world

    world = open_world()  # 預設的資料庫是測試用的暫存檔，裡面什麼都還沒有：.read() 回傳空狀態
    for loc_id in content.locations:
        assert roster.recruitable_here(content, world, loc_id) == [], loc_id


def test_meeting_events_mark_the_acquaintance_instead_of_handing_out_companions(content):
    for ev in content.events.values():
        for choice in ev.choices:
            assert choice.effect.recruit is None and choice.fail_effect.recruit is None, ev.id
    meet = content.events["meet_caocao"]
    assert "結識:caocao" in meet.choices[0].effect.flags_add
    assert "結識:caocao" in meet.condition.flags_none


def test_the_fortune_turns_into_a_gift_when_nobody_can_be_recruited(content, tmp_path):
    from tianxia.sqlite_world import open_world

    game = Game.new(content, "測試俠客", rng=random.Random(0), world=open_world(tmp_path / "world.db"))
    msgs = game._deliver_fortune()
    assert any("賀禮" in m for m in msgs)
    assert game.state.player.team == []


# ── 完整跑一季（機器人）──────────────────────────────────


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_bot_plays_a_full_season(content, seed, tmp_path):
    from tianxia.sqlite_world import open_world

    game = play_season(content, seed, world=open_world(tmp_path / f"world-{seed}.db"))
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert len(game.state.player.seen_events) >= 3


def test_the_bot_learns_insights_fuses_and_cultivates(content, tmp_path):
    from tianxia.sqlite_world import open_world

    game = play_season(content, 1, world=open_world(tmp_path / "arts.db"))
    p = game.state.player
    assert p.insights, "整季都沒悟到意境：探索的悟意境那一支沒接上"
    assert game.world.recipe_keys(), "整季都沒合成過"
    assert any(key.startswith(fusion.BLEND_PREFIX) for key in game.world.recipe_keys()), "整季都沒把兩門武學合在一起過"
    assert p.art_quality or p.art_mastery, "整季都沒修練過"
    assert p.member.wugong_level > 1 or p.member.neigong_level > 1, "整季都沒練成過"


def test_a_new_character_starts_with_the_two_starter_arts_at_level_one(content):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    member = game.state.player.member
    assert (member.neigong_id, member.neigong_level) == ("jichu_tuna", 1)
    assert (member.wugong_id, member.wugong_level) == ("jichu_quanjiao", 1)
    assert game.state.player.stats["xinde"] == content.config.start_stats["xinde"]


def test_the_level_step_waits_for_a_real_practice_not_for_having_the_art(content, world):
    """審查裁示 F1（現在是師父的第 5 步）：合成出來的那一門一到手就有了，這一步若只看「有沒有」一開始就成立、教不到練成；
    要它真的練到第三成：先換上、練一次還不算，練到第三成才算。"""
    from tianxia import prologue

    game = Game.new(content, "新人", rng=random.Random(0), world=world, prologue=True)
    game.world.open_season(content, now=0.0)
    for option in ("choice:0", "choice:0"):
        game.choose(option)
    game.view_tab("practice")
    game.choose("act:explore")
    game.choose("choice:0")
    game.forge("jichu_quanjiao", ["feng"], proposed=(None, ""))
    index = [step.id for step in content.tutorial.steps].index("p5_level")
    assert game.state.player.tutorial_step == index and content.tutorial.steps[index].done_when.fused_level == 3
    art = prologue.fused_arts(game.state, content, world)[0]
    game.switch_art(art.id)
    game.practice("武學")
    assert game.state.player.tutorial_step == index  # 帶著、換上、練到第二成，還不算
    game.practice("武學")
    assert game.state.player.tutorial_step == index + 1 and "✔ 引導完成" in game.state.player.guide_done


def test_a_new_character_can_afford_the_first_practices_the_tutorial_asks_for(content):
    """練成花心得（武學與成長 4.2）：開局 20 點心得，第 1 成升第 2 成只花 1 點，照引導去練一次練得起；
    心得見底時，訊息直接說差多少，新手才知道要去賺。"""
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    member = game.state.player.member
    start = game.state.player.stats["xinde"]
    assert start >= team.practice_price(content, 1)
    msgs = game.practice("武學")
    assert member.wugong_level == 2 and "心得 -1" in msgs
    assert game.state.player.stats["xinde"] == start - 1
    game.state.player.stats["xinde"] = 0
    msgs = game.practice("武學")
    assert member.wugong_level == 2
    assert "要 2 點心得，你只有 0 點" in msgs[0] and "還差 2 點" in msgs[0]


def test_event_taught_arts_still_reach_a_character_whose_slots_are_full(content):
    """審查裁示 F2：開局兩個欄位都被基礎武學佔了，事件教的追風步、混元一氣不能因此學不到——進功法庫，附錄 B.1 說它們照舊拿得到。"""
    from tianxia import library
    from tianxia.models import Effect
    from tianxia.rules import apply_effect

    game = Game.new(content, "測試俠客", rng=random.Random(0))
    worn = (game.state.player.member.neigong_id, game.state.player.member.wugong_id)
    assert None not in worn
    for skill_id in ("zhuifeng", "hunyuan"):
        assert any(skill_id in (e.model_dump_json()) for e in content.events.values())  # 內容裡真的有事件教它
        msgs = apply_effect(Effect(learn_skills=[skill_id]), game.state, content, game.world)
        assert any("功法庫" in m for m in msgs), msgs
    assert {"zhuifeng", "hunyuan"} <= set(game.state.player.arts)
    assert (game.state.player.member.neigong_id, game.state.player.member.wugong_id) == worn
    assert {"zhuifeng", "hunyuan"} <= set(library.owned_arts(game.state))


def test_the_escort_lesson_stops_coming_back_once_the_art_is_in_the_library(content):
    """最終審查 Important 1：潁川「汝南鏢局」（交友、可重複）只在還不會追風步時出現，付 40 兩學。開局兩個欄位都是基礎武學，
    學到的追風步進功法庫；條件只看身上兩欄的話，這則會一直回來、第二次付錢什麼都學不到（100 → 60 → 20 兩）。"""
    from tianxia.rules import apply_effect, check_condition

    game = Game.new(content, "測試俠客", rng=random.Random(0))
    event = content.events["escort_teacher"]
    assert not event.once and "yingchuan" in event.locations and "socialize" in event.actions
    assert check_condition(event.condition, game.state, content)
    lesson = next(c for c in event.choices if "zhuifeng" in c.effect.learn_skills)
    apply_effect(lesson.effect, game.state, content, game.world)
    assert "zhuifeng" in game.state.player.arts  # 欄位滿了，收進功法庫
    assert not check_condition(event.condition, game.state, content)
    waterfall = next(c for c in content.events["waterfall"].choices if c.condition.skills_none == ["zhuifeng"])
    assert not check_condition(waterfall.condition, game.state, content)  # 瀑布怪客的偷學也不再出現


# ── 戰鬥難度曲線 ──────────────────────────────────────────


def _win_rate(content, squad_id: str, wugong_id: str | None = None, runs: int = 40, bare: bool = False) -> float:
    """新角色（開局就帶著 starter_skills 的兩門基礎武學）對 squad_id 的勝率；bare 先把兩門都清掉，wugong_id 換掉武學那一門。"""
    wins = 0
    for seed in range(runs):
        game = Game.new(content, "測試俠客", rng=random.Random(seed))
        if bare:
            game.state.player.member.neigong_id = game.state.player.member.wugong_id = None
        if wugong_id:
            game.state.player.member.wugong_id = wugong_id
        wins += fight(game.state, content, game.world, squad_id, random.Random(seed)).tier in ("大勝", "險勝")
    return wins / runs


def test_a_hero_with_no_martial_art_at_all_cannot_win_any_fight(content):
    """設計文件六.3：威力全靠武學，沒有武學的人誰都打不贏（開局送的兩門基礎武學清掉才是這個情況）。"""
    assert _win_rate(content, "dipi", bare=True) == 0.0


def test_a_freshly_started_hero_with_only_the_starter_arts_wins_sometimes_but_not_reliably(content):
    """審查裁示 F3：開局就有兩門基礎武學，對地痞流氓有得打但不穩（量過約四成）；練上去、換更強的功夫才是變強的路。"""
    rate = _win_rate(content, "dipi")
    assert 0 < rate < 0.9


def test_a_hero_with_a_signature_skill_beats_stray_bandits(content):
    wugong_id = next(s.id for s in content.skills.values() if s.kind == "武學")
    assert _win_rate(content, "dipi", wugong_id) >= 0.9


def test_a_hero_with_a_signature_skill_still_cannot_beat_bocai(content):
    wugong_id = next(s.id for s in content.skills.values() if s.kind == "武學")
    assert _win_rate(content, "fanjianglong", wugong_id) <= 0.05


# ── 戰後事件的文字假設打贏了：「倒地的對手」只在遊歷打贏之後接（跟 FB-001 同一類）──────────


def _after_a_fight(content, tier):
    """剛打完一場遊歷（結果是 tier）的新角色：站在有敵人的地方，戰鬥卡片指著那一場。"""
    from tianxia.state import BattleRecord, Fighter

    game = Game.new(content, "遊歷人")
    game.state.player.location = next(loc.id for loc in content.locations.values() if loc.enemies)
    game.state.battles.insert(0, BattleRecord(
        id=1, time=0.0, location="某地", kind="train", opponent="流寇散兵", ours=[Fighter(name="遊歷人", level=1)],
        tier=tier, our_power=40.0, difficulty=8.0,
    ))
    game.state.battle_card = 1
    return game


def _after_fight_events(content, tier):
    from tianxia.events import event_candidates

    game = _after_a_fight(content, tier)
    return {e.id for e in event_candidates(game.state, content, "train")}


@pytest.mark.parametrize("tier", ["大勝", "險勝"])
def test_the_fallen_foe_can_follow_a_win(content, tier):
    assert "train_fallen_foe" in _after_fight_events(content, tier)


@pytest.mark.parametrize("tier", ["僵持", "落敗"])
def test_the_fallen_foe_never_follows_a_draw_or_a_loss(content, tier):
    after = _after_fight_events(content, tier)
    assert "train_fallen_foe" not in after
    assert "train_campfire" in after  # 結果不挑的戰後事件照舊接得到


def test_the_fallen_foe_needs_a_fight_in_this_very_action(content):
    """上一次行動打贏了、這一次沒打（戰鬥卡片已經清掉）：紀錄還在，也抽不到它。"""
    from tianxia.events import event_candidates

    game = _after_a_fight(content, "大勝")
    game.state.battle_card = None
    assert "train_fallen_foe" not in {e.id for e in event_candidates(game.state, content, "train")}


def test_playing_the_real_fight_the_fallen_foe_only_ever_comes_after_a_win(content, monkeypatch):
    """真實內容、固定種子、戰後事件一定接：新角色在只有流寇散兵的地方遊歷，打贏與沒打贏都有，倒地的對手只跟著打贏。"""
    monkeypatch.setattr(content.config, "train_event_chance", 1.0)
    place = next(loc.id for loc in content.locations.values() if loc.enemies == ["dipi"])
    tiers: dict[str, int] = {}
    fired_after: set[str] = set()
    for seed in range(120):
        game = Game.new(content, f"遊歷{seed}", rng=random.Random(seed))
        game.state.player.location = place
        game.choose("act:train")
        tier = game.state.battles[0].tier
        tiers[tier] = tiers.get(tier, 0) + 1
        if game.state.pending_event == "train_fallen_foe":
            fired_after.add(tier)
    assert set(tiers) & {"僵持", "落敗"} and set(tiers) & {"大勝", "險勝"}  # 輸贏都打出來過，下面才不是空轉
    assert fired_after and fired_after <= {"大勝", "險勝"}, (fired_after, tiers)


# ── 事件檢定的難度帶（企劃者 2026-10-05「成功率毫無道理可言」）────────
# 開局五項屬性都是 5，`rules.check_chance` 是 50% ＋ 每點差 10%（不動，按鈕上顯示的成算就是它）。
# 所以難度帶跟著地點的危險度走：危險度 1 的地方（城鎮、官道、河畔）新角色有五到七成，
# 2 的地方要練過，3 的地方（營寨、祭壇、洞窟）明確是難的。事件出現在好幾個地方時取最危險的那個。
DIFFICULTY_BANDS = {1: (3, 6), 2: (4, 7), 3: (6, 8)}


def _event_danger(content, event):
    locs = list(event.locations) or [
        lid for lid, loc in content.locations.items() if set(event.tags) & set(loc.tags)
    ]
    return max((content.locations[lid].danger for lid in locs), default=1)


def _checks(content):
    for event in content.events.values():
        for choice in event.choices:
            if choice.check is not None:
                yield event, choice.check


def test_event_checks_stay_inside_the_band_for_their_danger(content):
    for event, check in _checks(content):
        low, high = DIFFICULTY_BANDS[_event_danger(content, event)]
        assert low <= check.difficulty <= high, (event.id, check.difficulty)


def test_a_new_character_has_even_odds_or_better_on_most_checks_in_safe_places(content):
    """危險度 1 的地方，九成以上的檢定新角色（屬性 5）有五成以上；難度 6（四成）留給刻意難的那幾個。"""
    safe = [check.difficulty for event, check in _checks(content) if _event_danger(content, event) <= 1]
    assert sum(d <= 5 for d in safe) / len(safe) >= 0.9


def test_most_checks_in_the_starting_region_give_a_new_character_five_to_seven_in_ten(content):
    start = region_of(content, content.scenario.start_location).id
    here = [
        check.difficulty for event, check in _checks(content)
        if any(
            region_of(content, lid).id == start
            for lid in (list(event.locations) or [
                lid for lid, loc in content.locations.items() if set(event.tags) & set(loc.tags)
            ])
        )
    ]
    # 屬性 5 對難度 3～5 ＝ 七成～五成；其餘是長社、嵩山深處、南華觀這類危險度 2、3 的地方
    assert sum(3 <= d <= 5 for d in here) / len(here) >= 0.75


def test_bocai_is_the_hardest_squad_by_difficulty(content):
    """代表大勢人物本人的隊伍（figure_<id>，T4）不算：難度跟著聲威走，見 tests/test_figures.py。"""
    squads = [s for s in content.squads.values() if not s.id.startswith("figure_")]
    assert max(squads, key=lambda s: s.difficulty).id == "fanjianglong"


# ── 大地圖 ────────────────────────────────────────────────


TEXT_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"([^>]*)>([^<]*)</text>')
Box = tuple[float, float, float, float]


def _text_box(m: re.Match) -> Box:
    x, y, size, text = float(m[1]), float(m[2]), int(m[3]), html.unescape(m[5])
    anchor = re.search(r'text-anchor="(\w+)"', m[4])
    width = text_width(text, size)
    left = x - {"start": 0, "middle": width / 2, "end": width}[anchor[1] if anchor else "start"]
    return left, y - size * 0.85, left + width, y + size * 0.15


def _text_boxes(svg: str) -> list[tuple[str, Box]]:
    return [(html.unescape(m[5]), _text_box(m)) for m in TEXT_RE.finditer(svg)]


def _placed_texts(svg: str) -> list[tuple[str, Box, str | None]]:
    """地點的名字與小字（帶 data-loc，第三項是它屬於哪個地點）和山名（帶字距，第三項是 None）：
    大區名稱、大勢、河名的位置是內容寫死的，不是擺出來的，所以不在這裡。"""
    return [
        (html.unescape(m[5]), _text_box(m), owner[1] if owner else None)
        for m in TEXT_RE.finditer(svg)
        if (owner := re.search(r'data-loc="(\w+)"', m[4])) or "letter-spacing" in m[4]
    ]


def _touches_circle(box: Box, cx: float, cy: float, radius: float, allow: float = 1.0) -> bool:
    """文字範圍有沒有壓進圓裡（圓心到範圍最近的一點比半徑近超過 allow）。"""
    nearest_x, nearest_y = min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])
    return math.hypot(cx - nearest_x, cy - nearest_y) < radius - allow


def _overlaps(a: Box, b: Box, allow: float = 1.0) -> bool:
    return a[0] < b[2] - allow and b[0] < a[2] - allow and a[1] < b[3] - allow and b[1] < a[3] - allow


def _collisions(svg: str, canvas: Box) -> list[str]:
    texts = _text_boxes(svg)
    found = [f"{a}×{b}" for i, (a, box_a) in enumerate(texts) for b, box_b in texts[i + 1:] if _overlaps(box_a, box_b)]
    x0, y0, x1, y1 = canvas
    found += [f"{a} 出界" for a, (left, top, right, bottom) in texts if left < x0 - 1 or top < y0 - 1 or right > x1 + 1 or bottom > y1 + 1]
    return found


def _minimap_window(svg: str) -> Box:
    left, top, width, height = map(float, re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', svg).groups())
    return left, top, left + width, top + height


@pytest.mark.parametrize("layer", ["situation", "enemies", "story", "routes"])
def test_world_map_labels_never_collide_or_leave_the_canvas_at_the_start(content, layer):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    canvas = (0, 0, content.map.width, content.map.height)
    for selected in [None, *(loc_id for _, loc_id in game.map_places())]:
        svg = render_map(game.state, content, layer, selected, game.odds if layer == "enemies" else None)
        assert _collisions(svg, canvas) == [], selected


# 每個地點都當所在地、而且選定（玩家一打開地圖看到的就是這個）時，名字壓到「別的地點的圓盤」的次數上限。
# 圓盤半徑 14（13 加外圈的一半）。名字多了左右錯開、正上下、斜角幾種位置之後，只剩擠得沒有任何空位的地方
# 只好壓到邊緣（例如淯水河畔：貼著地圖左緣、新野就在右下，名字又長）。這個數字只准變少。
# 輿圖圖例浮層（圖例搬出 SVG、左下角不再留位置）之後重新量過：四層的數字跟搬走前一樣（0、1、0、1）；真實地圖上最低的地點在 y=1235，原本圖例佔的 y 1280～1326（局勢層有打擊記號那一行時從 1262 起）那一條從來沒有擠開過名字，連同打擊記號開著的局勢層一起逐張比對過、一張不差。剩下的一處是淯水河畔貼著左緣、新野在右下。
DISC_OVERLAPS = {"situation": 0, "enemies": 1, "story": 0, "routes": 1}


@pytest.mark.parametrize("layer", list(DISC_OVERLAPS))
def test_current_place_marks_stay_clear_of_names_from_any_location(content, layer):
    """所在地的紅旗、紅圈與選定的圓圈上面不會有字（名字、小字、山名）；別的地點的圓盤也盡量不被名字壓到。"""
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    game.state.player.visited.update(content.locations)  # 每個地點都去過：全都畫成圓盤
    game.state.world.flags.update(loc.unlock_flag for loc in content.locations.values() if loc.unlock_flag)
    left, top, right, bottom = BANNER_BOX
    red_ring, select_ring, disc = CURRENT_RING + 1, NODE_SIZE["current"] + 11.5, NODE_SIZE["visible"] + 1
    disc_overlaps = 0
    # 敵情層「最險」那行字的長短跟著誰最難對付走：這個測試量的是版面，所以勝算固定成全部必敗（開局送武學之前，
    # 新角色看到的就是這樣）；開局帶著基礎武學時最險的換成官軍巡騎、字更長，北邙山那行會壓到白馬寺的紅旗（版面的老毛病）
    odds = (lambda squad_id: "必敗") if layer == "enemies" else None
    for loc in content.locations.values():
        game.state.player.location = loc.id
        svg = render_map(game.state, content, layer, loc.id, odds)
        for text, box, owner in _placed_texts(svg):
            assert not _overlaps(box, (loc.x + left, loc.y + top, loc.x + right, loc.y + bottom)), (loc.id, text, "紅旗")
            assert not _touches_circle(box, loc.x, loc.y, red_ring), (loc.id, text, "紅圈")
            assert not _touches_circle(box, loc.x, loc.y, select_ring), (loc.id, text, "選定的圓圈")
            if owner is None:  # 山名的位置是內容定的：要整個在外框裡面（燕山貼著上緣，往下挪）
                assert _inside_frame(box, content), (loc.id, text, "壓到外框")
            if owner is not None:
                disc_overlaps += sum(
                    _touches_circle(box, other.x, other.y, disc)
                    for other in content.locations.values()
                    if other.id not in (loc.id, owner) and not other.prologue_only  # 草廬的圓盤只有站在那裡的人看得到，別處不畫
                )
    assert disc_overlaps <= DISC_OVERLAPS[layer]


def _inside_frame(box: Box, content) -> bool:
    """字整個在外框裡面那條線之內（左右上下各 FRAME_INSIDE），不壓到外框。地點名字不檢查這個：
    貼著地圖邊的地點（大將軍府、淯水河畔）名字要是不准碰外框，就只能壓到隔壁的圓盤，那個比較糟。"""
    inside = FRAME_INSIDE - 1
    return box[0] >= inside and box[1] >= inside and box[2] <= content.map.width - inside and box[3] <= content.map.height - inside


def _disc_overlaps(game, content, svg: str, texts: list[tuple[str, Box, str | None]]) -> list[tuple[str, str]]:
    """字壓到「別的地點」的圓盤（摸清的地點才有圓盤）：回傳（字, 被壓到的地點）。"""
    from tianxia.atlas import KNOWN, views

    seen = views(game.state, content)
    disc = NODE_SIZE["visible"] + 1
    here = game.state.player.location
    return [
        (text, other.id) for text, box, owner in texts for other in content.locations.values()
        if other.id not in (here, owner) and seen[other.id] in KNOWN and _touches_circle(box, other.x, other.y, disc)
    ]


def test_a_new_player_at_the_first_fight_sees_the_camp_next_door(content):
    """新手引導叫玩家去潁川郊野歷練：打開敵情時「最險」那行不能蓋住隔壁黃巾別部營寨的圓盤（蓋住的那一半點下去會選錯地點）。"""
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    game.state.player.visited.update(["yingchuan", "yingchuan_wilds", "yingshui", "changshe", "songshan_foot", "yingchuan_academy", "huangjin_camp"])
    game.state.player.location = "yingchuan_wilds"
    for selected in ("yingchuan_wilds", "huangjin_camp"):  # 打開地圖時選的是所在地；點了營寨之後選的是營寨
        svg = render_map(game.state, content, "enemies", selected, game.odds)
        assert "最險" in svg
        assert _disc_overlaps(game, content, svg, _placed_texts(svg)) == [], selected


def _owner_by_name(content, text: str) -> str | None:
    """小地圖的字沒有 data-loc（點不到）：照字裡的地名認是哪個地點的（視窗邊緣的「↘ 荒丘」是指向荒丘的）。"""
    names = [loc for loc in content.locations.values() if loc.name in text]
    return max(names, key=lambda loc: len(loc.name)).id if names else None


def test_minimap_never_collides_from_any_location(content):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    for loc_id in content.locations:
        game.state.player.location = loc_id
        svg = render_minimap(game.state, content)
        assert _collisions(svg, _minimap_window(svg)) == [], loc_id
        texts = [(text, box, _owner_by_name(content, text)) for text, box in _text_boxes(svg)]
        assert _disc_overlaps(game, content, svg, texts) == [], loc_id


def test_regions_reference_real_trends(content):
    trend_ids = {t.id for t in content.scenario.trends}
    for region in content.map.regions:
        assert set(region.trends) <= trend_ids, region.id


def test_every_location_belongs_to_a_region(content):
    from tianxia.atlas import region_of

    for loc_id in content.locations:
        assert region_of(content, loc_id) is not None, loc_id


def test_real_content_defines_the_three_factions_and_the_battle_uses_them(content):
    assert [f.id for f in content.scenario.factions] == ["guan", "huang", "haoqiang"]
    sides = {f.id for f in content.battles["huangjin_showdown"].factions}
    assert sides <= {f.id for f in content.scenario.factions}


def test_the_showdown_gives_scattered_players_time_to_gather(content):
    """企劃者定案：集結 30 分鐘、每回合 5 分鐘，人少、上線時間不一的伺服器也來得及到場。"""
    showdown = content.battles["huangjin_showdown"]
    assert showdown.muster_seconds == 30 * 60
    assert showdown.round_seconds == 5 * 60


def test_the_showdown_is_three_acts_of_three_rounds_and_ends_early_at_90_or_10(content):
    """戰鬥系統設計 3.2（FB-016）：三幕各 3 回合、共 9 回合（每回合最多 5 分鐘，約 45 分鐘）；
    戰局到 90 以上或 10 以下就提前收場。"""
    showdown = content.battles["huangjin_showdown"]
    assert (len(showdown.acts), showdown.rounds_per_act) == (3, 3)
    from tianxia.battle_instance import CENTER

    assert (CENTER + showdown.decisive_margin, CENTER - showdown.decisive_margin) == (90, 10)  # 提前收場看中線 50（戰鬥系統 5.3）


def test_nobody_can_join_a_faction_at_the_start_location(content):
    """伺服器假人設計第八節第 3 項：開局地點不設投靠點，不然所有人一開場就全投了官軍。"""
    start = content.scenario.start_location
    assert all(start not in f.join_at for f in content.scenario.factions)


def test_each_side_of_the_war_wants_the_yellow_turbans_to_go_its_way(content):
    """官軍把三條戰線往 0 壓、黃巾往 100 推，豪強只推割據（第一季設計 4.4、總計畫 T1）。"""
    goals = {f.id: f.goals for f in content.scenario.factions}
    fronts = ("yingru", "nanyang", "jizhou")
    assert goals == {"guan": dict.fromkeys(fronts, -1), "huang": dict.fromkeys(fronts, 1), "haoqiang": {"geju": 1}}


# 遊歷推大勢：數字跟遷移前一模一樣，鍵換成所在大區的戰線；洛陽沒有戰況，寫 front
EXPECTED_TRAINING = {
    "changshe": {"yingru": -1}, "luoyang_road": {"front": -1}, "mengjin_ford": {"front": 1},
    "nanyang_huangjin_camp": {"nanyang": -2}, "yu_river": {"nanyang": -1}, "nanyang_wilds": {"nanyang": -1},
    "runan_wilds": {"yingru": -1}, "huangjin_camp": {"yingru": -2}, "juma_river": {"jizhou": -1},
    "yanshan_foot": {"jizhou": -1}, "julu_altar": {"jizhou": -2}, "guangzong": {"jizhou": -2},
    "luzhi_camp": {"jizhou": 1}, "xiaquyang": {"jizhou": -1}, "baima_ford": {"jizhou": 1},
}


def test_real_content_fronts(content):
    """三條戰線的起始值與權重照第一季設計 4.1，割據從 10 起；大區對戰線；遊歷指向所在戰線；
    虛擬玩家與決戰結果改推潁川汝南（數字不變）。"""
    trends = {t.id: t for t in content.scenario.trends}
    starts = {key: trends[key].start for key in ("yingru", "nanyang", "jizhou", "geju")}
    assert starts == {"yingru": 40, "nanyang": 35, "jizhou": 55, "geju": 10}
    assert trends["huangjin"].derived == {"yingru": 0.35, "nanyang": 0.25, "jizhou": 0.40}
    assert trends["huangjin"].start == 25 and not trends["huangjin"].season_one
    assert all(trends[key].season_one for key in ("yingru", "nanyang", "jizhou", "geju"))
    assert {r.id: r.front for r in content.map.regions} == {
        "youzhou": "jizhou", "jizhou": "jizhou", "luoyang": None, "yingru": "yingru", "nanyang": "nanyang",
    }
    assert {r.id: r.trends for r in content.map.regions} == {
        "youzhou": ["jizhou"], "jizhou": ["jizhou"], "luoyang": [], "yingru": ["yingru", "yuxi"], "nanyang": ["nanyang"],
    }
    assert {lid: loc.train_trend for lid, loc in content.locations.items() if loc.train_trend} == EXPECTED_TRAINING
    for lid, pushes in EXPECTED_TRAINING.items():
        assert set(pushes) == {region_of(content, lid).front or "front"}, lid
    assert [s.trend for s in content.scenario.sim_players] == [{"yingru": 1}, {"yingru": -1}, {"yuxi": 2}]
    outcomes = [o.trend_delta for o in content.battles["huangjin_showdown"].outcomes]
    assert outcomes == [{"yingru": -35}, {"yingru": 25}, {"yingru": -5}]


def test_the_playtest_admin_is_rayal(tmp_path, monkeypatch):
    """驗的是版控內容只帶 Rayal，所以要先隔開這台機器自己的 `.local/admins.txt` 與 `TIANXIA_ADMINS`
    （那兩個是附加在名單上的，不隔開的話凡是設過本機管理者的機器都會失敗）。"""
    from tianxia import content as content_mod

    monkeypatch.setattr(content_mod, "ADMINS_FILE", tmp_path / "nope.txt")
    monkeypatch.delenv("TIANXIA_ADMINS", raising=False)
    assert load_content(CONTENT_DIR).config.admins == ["Rayal"]

def test_enemy_squads_are_marked_with_the_designers_factions(content):
    factions = {  # 本人的隊伍見 test_figures；運糧隊（截糧、護糧，T6）見 test_orders
        sid: s.faction for sid, s in content.squads.items()
        if not sid.startswith("figure_") and not sid.endswith("_grain_convoy")
    }
    assert {sid for sid, f in factions.items() if f == "huang"} == {
        "louluo", "shuikou", "toumu", "shanzei", "fanjianglong", "taiping_lishi", "huangjin_sishi",
    }
    assert {sid for sid, f in factions.items() if f == "guan"} == {"guishou", "guan_patrol", "jun_bing", "beijun_wuzu", "liangzhou_cavalry"}
    assert {sid for sid, f in factions.items() if f == "haoqiang"} == {"xuantie_dizi", "wubao_buqu", "yiyong"}


def test_season_one_tells_the_dialogue_model_when_it_is(content):
    note = content.scenario.era_note
    assert "184" in note and "諸葛亮" in note and "赤壁" in note


def test_every_figure_has_an_audience_threshold(content):
    figures = {cid: ch.audience_fame for cid, ch in content.characters.items() if ch.deep_interaction}
    assert len(figures) == 18 and all(fame > 0 for fame in figures.values())
    assert figures["liubei"] < figures["caocao"] < figures["yuanshao"] < figures["luzhi"] < figures["huangfusong"] < figures["zhangjiao"]


def test_figure_dialogue_runs_on_gemma4_without_thinking_or_repetition_penalties(content):
    """2026-10-03 實測：gemma4:26b 內容最好；重複懲罰會讓它夾英文、關掉思考才不會每輪多等。"""
    cfg = content.config
    assert cfg.ollama_model == "gemma4:26b"
    assert cfg.ollama_think is False
    assert cfg.ollama_repeat_penalty == 1.0 and cfg.ollama_presence_penalty == 0.0 and cfg.ollama_frequency_penalty == 0.0


# ── 時刻表（計畫 T2；時刻表結算文件第五節）────────────────────────────


def test_real_timetable_matches_settlement_doc():
    """12 件大事照結算文件第五節的週次；固定 3 件、決戰 3 件、最後是季末。用週末設定載入（開關與季長都開著）。"""
    c = load_content(CONTENT_DIR, profile="weekend")
    events = {e.id: e for e in c.timetable}
    assert len(c.timetable) == 12
    assert [(e.week, e.kind) for e in c.timetable] == [
        (1, "fixed"), (2, "fixed"), (3, "roll"), (4, "roll"), (6, "showdown"), (7, "roll"), (7, "fixed"),
        (8, "roll"), (9, "showdown"), (10, "roll"), (11, "showdown"), (12, "finale"),
    ]
    assert [e.id for e in c.timetable if e.kind == "fixed"] == ["uprising", "court_mobilizes", "qinjie_slays_zhangmancheng"]
    assert [e.id for e in c.timetable if e.kind == "showdown"] == ["changshe_fire", "wancheng", "guangzong"]
    assert c.timetable[-1].id == "xiaquyang"

    zhang = events["zhangmancheng_wan"].outcomes  # 張曼成「成」南陽 +8，「不成」−5 且張曼成（不在時是接手的人）受挫
    assert zhang["成"].trends == {"nanyang": 8} and not zhang["成"].figures
    assert zhang["不成"].trends == {"nanyang": -5} and zhang["不成"].figures["@人物:zhangmancheng"].fate == "受挫"
    guangzong = events["guangzong"].outcomes["guan:大勝"]  # 廣宗官軍大勝：冀州 −20、張梁（不在時是接手的人）退場
    assert guangzong.trends == {"jizhou": -20} and guangzong.figures["@人物:zhangliang"].fate == "退場"
    changshe = events["changshe_fire"].outcomes  # 長社四格：15／8
    assert {k: o.trends["yingru"] for k, o in changshe.items()} == {
        "guan:大勝": -15, "guan:險勝": -8, "huang:大勝": 15, "huang:險勝": 8,
    }
    assert changshe["huang:大勝"].chance_mods == {"luzhi_siege": -0.10} and changshe["huang:大勝"].trends["jizhou"] == 5
    assert set(events["wancheng"].outcomes) == {  # 宛城甲、乙兩版共 8 格
        f"{v}:{side}:{tier}" for v in ("甲", "乙") for side in ("guan", "huang") for tier in ("大勝", "險勝")
    }
    qinjie = events["qinjie_slays_zhangmancheng"]  # 朱儁到任南陽，條件是皇甫嵩還在潁川（濃縮版內容表 1.3）
    assert qinjie.skip_if_out == "zhangmancheng" and set(qinjie.outcomes) == {"甲:fixed", "乙:fixed"}
    zhujun = qinjie.outcomes["甲:fixed"].figures["zhujun"]
    assert (zhujun.fate, zhujun.front, zhujun.location, zhujun.only_if) == ("到任", "nanyang", "wan_city", {"huangfusong": "yingru", "zhujun": "yingru"})  # 8.11：朱儁也要在潁川
    assert zhujun.note == "右中郎將朱儁也領兵南下，往宛城去了。"
    assert events["luzhi_jailed"].base_chance == 0.5 and events["luzhi_jailed"].front is None
    assert events["luzhi_jailed"].lock_result == {"huang": "成", "guan": "不成"}
    assert events["zhangjiao_dies"].lock_result == {"guan": "成", "huang": "不成"}


def test_real_endings_valid(content):
    """第一季的六種結局（第一季設計 13.1，不含玉璽）照順序；beta 的保底照舊；季末大事的三種句子（時刻表結算第 12 週）。"""
    s1 = [e for e in content.scenario.endings if e.season_one]
    assert [e.title for e in s1] == ["黃天當立（無璽）", "黃巾平定", "群雄並起", "黃巾坐地", "黃巾敗退", "豪強坐大"]
    assert [e.stance_min or e.stance_max for e in s1[:3]] == [{"huang": 85}, {"huang": 15}, {"haoqiang": 85}]
    assert [e.stance_top for e in s1[3:]] == ["huang", "guan", "haoqiang"]
    assert s1[4].text == "下曲陽破了，可冀州的山裡仍有黃旗。"
    for ending in s1[:3]:  # 決定性勝利第 10 週起才收（企劃者 2026-10-05）：提示不能說「當場收場」卻讓人空等五週（T9 審查 I1）
        assert f"第 {content.config.decisive_from_week} 週起" in ending.hint, ending.hint
    assert [e.hint for e in s1] == [  # 濃縮版內容表第七節（2026-10-05 審過）：一律照狀態列的「態勢」講、三方對稱
        "第 10 週起，黃巾的態勢一到 85，這一季當場收場。",
        "第 10 週起，官軍的態勢一到 85，這一季當場收場。",
        "第 10 週起，豪強的態勢一到 85，這一季當場收場。",
        "到了季末，黃巾的態勢最高。",
        "到了季末，官軍的態勢最高。",
        "到了季末，豪強的態勢最高。",
    ]
    beta = [e for e in content.scenario.endings if not e.season_one]
    assert beta[-1].id == "default"
    finale = next(e for e in content.timetable if e.kind == "finale")
    assert finale.preface == "史書上，皇甫嵩攻下曲陽，斬張寶，黃巾之亂至此平定。這一次……"
    assert finale.early_preface == "戰事提前收束。"
    assert finale.out_lines == {"dongzhuo": "董卓兵敗，涼州軍元氣大傷。"}
    assert finale.ending_chronicle == "甲子年冬，第一季黃巾之亂落幕：{結局}。"


def test_wancheng_after_a_government_win_reads_that_the_turbans_withdrew(content):
    """濃縮版內容表 4.7：宛城之戰官軍打贏（甲版破城、乙版解圍，大勝險勝都算）寫 wancheng_guan_holds，
    宛城的描寫換成「黃巾退了」那一段，排在第 3 週的版本描寫前面；黃巾打贏的四格不寫。"""
    outcomes = next(e for e in content.timetable if e.id == "wancheng").outcomes
    for key, outcome in outcomes.items():
        holds = "wancheng_guan_holds" in outcome.world_flags_add
        assert holds == (":guan:" in key), key
    wan = content.locations["wan_city"]
    text = "南陽郡治，黃巾退了。城牆上到處是刀砍火燒的痕跡，郡兵正忙著修補；城中人人都在說，那位江東來的將領是怎麼帶頭打贏這一仗的。"
    assert wan.desc_when[0].world_flag == "wancheng_guan_holds" and wan.desc_when[0].text == text
    for version in ("wan_version_jia", "wan_version_yi"):
        assert wan.describe({version, "wancheng_guan_holds"}) == text
        assert wan.describe({version}) != text


def test_real_timetable_runs_a_whole_condensed_season():
    """週末設定下把真實內容的一季從頭推到尾：除了季末（T9），每件大事都結算一次、照週次。這裡沒有 store，三場決戰開不了
    集結：長社、宛城在之後那件大事結算之前照起點結算（T8 fix round 1），廣宗之後沒有大事、等到收季前才結算（fix round 0）。"""
    import random as _random

    from tianxia.state import GameState, PlayerState
    from tianxia.world import advance_world_state
    from tianxia.world_state import fresh_season

    c = load_content(CONTENT_DIR, profile="weekend")
    c.scenario.sim_players, c.scenario.thresholds, c.scenario.world_events = [], [], []  # 只看時刻表：舊聲勢門檻收季另外測
    c.config.geju_chaos_per_day = 0.0  # 割據不漲：沒人玩時三條戰線一直在亂局，割據第 5 週就過 85，第 10 週（decisive_from_week）起會以「群雄並起」提前收季，廣宗與季末就輪不到；這裡測的不是它
    state = GameState(player=PlayerState(name="", location=c.scenario.start_location, stats={}, stamina=0),
                      world=fresh_season(c))
    msgs = advance_world_state(state.world, c, 2.5 * 86400, _random.Random(0))
    expected = [e.id for e in c.timetable]  # timetable.json 照週次排；季末那件（下曲陽）收季時由 T9 寫在最後
    assert list(state.world.timeline) == expected and state.world.showdowns_waiting == []
    assert state.world.timeline["xiaquyang"].key == state.world.ending_id
    assert state.world.timeline["guangzong"].time == state.world.time  # 廣宗之後沒有大事：收季前才結算
    announced = len(expected) - (state.world.timeline["qinjie_slays_zhangmancheng"].key == "skip")
    assert sum(m.startswith("【江湖大事】") for m in msgs) == announced
    assert state.world.ended  # 季末照舊收季（T9 換成下曲陽）


# ── 時刻表：有人鎖定時的公告（伏筆文件 3.4、5.4；2026-10-04 S1 的四欄表）──────────────────
#
# 組法：具名的一段＋這一檔（大勝或險勝）的結果句＋搶輸的一筆＋豪強的一筆；「波才北上」由 note 接、只出現一次。
# 下面三張表是照伏筆文件逐字抄的（具名的一段、大勝接、險勝接、搶輸的一筆），不是從 content 反推；「這一次」那半句
# 寫到的人照濃縮版內容表第八節（FB-042）改成人物欄位，長社黃巾勝的「潁川交給了朱儁」移到朱儁那筆人物效果的 note。

SHOWDOWN_NAMED = {
    ("changshe_fire", "", "guan"): "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。",
    ("changshe_fire", "", "huang"): "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 看破了火攻，先一步勸{人物:bocai}移營，那一夜燒的是一座空營。",
    ("wancheng", "甲", "guan"): "史書上，孫堅身當一面，登城先入，大破宛城。這一次，{name} 帶著一隊人跟在{人物:sunjian}身後，從東北角新補的城牆攀了上去。",
    ("wancheng", "甲", "huang"): "史書上，孫堅先登，宛城被破。這一次，城裡的糧倉是滿的，{name} 一袋一袋囤下的糧讓宛城撐過了最難的一個月。",
    ("wancheng", "乙", "guan"): "這一次，宛城在官軍手裡。黃巾圍城數十日，{name} 跟著{人物:sunjian}在一個雨夜縋城而出，直撲黃巾連營。",
    ("wancheng", "乙", "huang"): "圍城的黃巾糧足，城裡的官軍先斷了糧。{name} 替{人物:zhaohong}囤下的糧，比攻城梯還管用，宛城開了門。",
}
SHOWDOWN_TIER = {  # 大勝接、險勝接。長社黃巾大勝的「波才分兵北上」不在這裡：那一句在 note 上，不論有沒有鎖定都接
    ("changshe_fire", "", "guan"): ("騎都尉曹操的援兵恰好趕到，{人物:bocai}的草營燒成一片火海。", "只是風向不定，火只燒了半座營，{人物:bocai}敗走陽翟。"),
    ("changshe_fire", "", "huang"): ("黃巾反從上風殺出，{人物:huangfusong}重挫退走。", "黃巾趁亂反撲，官軍折損甚重，{人物:huangfusong}重挫退走。"),
    ("wancheng", "甲", "guan"): ("城門從裡面打開，{人物:zhaohong}死在亂軍之中。", "宛城是破了，可{人物:zhaohong}帶著殘部從南門突圍。"),
    ("wancheng", "甲", "huang"): ("官軍的雲梯一架架被推倒，{官軍主將}的兵先散了。", "宛城守住了，只是城裡的糧也快見底了。"),
    ("wancheng", "乙", "guan"): ("{人物:zhaohong}死在亂軍之中，圍城不攻自解。", "黃巾的連營被衝亂，{人物:zhaohong}退兵三十里。"),
    ("wancheng", "乙", "huang"): ("{官軍主將}的援軍晚到了一步。", "但黃巾也死傷慘重。"),
}
SHOWDOWN_LOSER = {  # 搶輸的一筆；乙版沒有
    ("changshe_fire", "", "guan"): "黃巾的 {loser} 曾看破火攻、勸{人物:bocai}移營，可惜晚了一步。",
    ("changshe_fire", "", "huang"): "官軍的 {loser} 費盡心思備下的火具，燒掉的只是幾頂空帳。",
    ("wancheng", "甲", "guan"): "黃巾的 {loser} 送進城的糧，最後沒能派上用場。",
    ("wancheng", "甲", "huang"): "{人物:sunjian}帶著 {loser} 攀上東北角，城頭的守兵卻吃得飽、站得穩。",
}
SHOWDOWN_CELLS = [(eid, ver, side, tier) for (eid, ver, side) in SHOWDOWN_NAMED for tier in ("大勝", "險勝")]


def _cell_key(ver: str, side: str, tier: str) -> str:
    return f"{ver}:{side}:{tier}" if ver else f"{side}:{tier}"


def _announce(event_id, key, *, version="", lock=None, losers=(), third=(), commander=None):
    """用真實內容（週末設定）結算一件決戰，回傳公告那一段。lock 是 (陣營, 名號)；losers 是 [(陣營, 名號)]。
    commander 換掉的是 figures.commander（{官軍主將}，以及人物欄位寫到的人不在時找的接手者）。"""
    from tianxia import figures, timetable
    from tianxia.models import FigureChange
    from tianxia.state import GameState, Lock, PlayerState
    from tianxia.world_state import fresh_season

    c = load_content(CONTENT_DIR, profile="weekend")
    state = GameState(player=PlayerState(name="", location=c.scenario.start_location, stats={}, stamina=0),
                      world=fresh_season(c))
    if version:  # 宛城的版本看「張曼成攻殺南陽太守」那件的結果
        state.world.timeline["zhangmancheng_wan"] = timetable.TimelineResult(key={"甲": "成", "乙": "不成"}[version], time=0.0)
        figures.apply(state, c, "zhangmancheng", FigureChange(fate="退場"))  # 第 7 週秦頡斬張曼成，趙弘接下南陽
    if lock is not None:
        state.world.locks[event_id] = Lock(side=lock[0], name=lock[1], time=0.0)
        state.world.lock_losers[event_id] = [Lock(side=s, name=n, time=1.0) for s, n in losers]
    if third:
        state.world.third_party[event_id] = list(third)
    event = next(e for e in c.timetable if e.id == event_id)
    with mock.patch.object(figures, "commander", lambda *a: commander):
        msgs = timetable.resolve(state, c, event, random.Random(0), key=key)
    assert len(msgs) == 1 and msgs[0].startswith("【江湖大事】")
    return msgs[0].removeprefix("【江湖大事】"), c


def test_every_locked_showdown_cell_is_the_named_part_plus_that_tiers_result_sentence():
    """長社四格、宛城八格：locked_text ＝ 具名的一段＋這一檔的結果句，只有贏家那一方有；搶輸的一筆照表，乙版沒有。"""
    c = load_content(CONTENT_DIR, profile="weekend")
    events = {e.id: e for e in c.timetable}
    assert len(SHOWDOWN_CELLS) == 12
    for eid, ver, side, tier in SHOWDOWN_CELLS:
        outcome = events[eid].outcomes[_cell_key(ver, side, tier)]
        named, (big, narrow), loser = SHOWDOWN_NAMED[eid, ver, side], SHOWDOWN_TIER[eid, ver, side], SHOWDOWN_LOSER.get((eid, ver, side))
        assert outcome.locked_text == {side: named + (big if tier == "大勝" else narrow)}, (eid, ver, side, tier)
        assert outcome.loser_text == ({side: loser} if loser else {}), (eid, ver, side, tier)


def test_no_locked_announcement_is_left_with_an_ellipsis():
    """S1 節錄時的「……」不是定稿；真實內容所有具名公告與搶輸的一筆都寫完整。"""
    c = load_content(CONTENT_DIR, profile="weekend")
    for e in c.timetable:
        for key, o in e.outcomes.items():
            for text in [*o.locked_text.values(), *o.loser_text.values(), o.text, o.note]:
                assert "……" not in text, (e.id, key, text)


def test_changshe_guan_lock_narrow_win_reads_named_part_then_the_narrow_sentence_then_the_loser_line():
    text, _ = _announce("changshe_fire", "guan:險勝", lock=("guan", "甲"), losers=[("huang", "乙")])
    assert text == (
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，甲 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。"
        "只是風向不定，火只燒了半座營，波才敗走陽翟。"
        "黃巾的 乙 曾看破火攻、勸波才移營，可惜晚了一步。"
    )


def test_changshe_guan_lock_big_win_with_the_baron_adds_his_line_last():
    text, _ = _announce("changshe_fire", "guan:大勝", lock=("guan", "甲"), losers=[("huang", "乙"), ("huang", "丙")], third=["豪甲"])
    assert text == (
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，甲 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。"
        "騎都尉曹操的援兵恰好趕到，波才的草營燒成一片火海。"  # 8.11：人名寫進「這一次」那半句
        "黃巾的 乙、丙 曾看破火攻、勸波才移營，可惜晚了一步。"
        "事後才有人發現，兩軍那幾天吃的糧竟出自同一家：豪甲 的糧車。"
    )


def test_changshe_huang_lock_big_win_says_the_northward_march_exactly_once():
    text, _ = _announce("changshe_fire", "huang:大勝", lock=("huang", "甲"), losers=[("guan", "乙")], third=["豪甲"])
    assert text.count("波才分兵北上") == 1
    assert text == (
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，甲 看破了火攻，先一步勸波才移營，那一夜燒的是一座空營。"
        "黃巾反從上風殺出，皇甫嵩重挫退走。"
        "潁川得手之後，波才分兵北上，往廣宗去了。"  # 北上是這一檔結果句的一部分（S1 表），排在搶輸的一筆前面
        "留在潁川的官軍，由朱儁收拾殘局。"  # 朱儁那筆人物效果的 note（FB-042；8.11 改字），接在這一格的 note 之後
        "官軍的 乙 費盡心思備下的火具，燒掉的只是幾頂空帳。"
        "事後才有人發現，兩軍那幾天吃的糧竟出自同一家：豪甲 的糧車。"
    )
    unlocked, _ = _announce("changshe_fire", "huang:大勝")  # 沒人鎖定的黃巾大勝：note 照樣接、也只有一次
    assert unlocked.count("波才分兵北上") == 1 and unlocked.endswith("潁川得手之後，波才分兵北上，往廣宗去了。留在潁川的官軍，由朱儁收拾殘局。")


def test_changshe_huang_lock_narrow_win_has_no_northward_march():
    text, _ = _announce("changshe_fire", "huang:險勝", lock=("huang", "甲"))
    assert text == (
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，甲 看破了火攻，先一步勸波才移營，那一夜燒的是一座空營。"
        "黃巾趁亂反撲，官軍折損甚重，皇甫嵩重挫退走。"
        "留在潁川的官軍，由朱儁收拾殘局。"  # 黃巾險勝原本沒有這一句，FB-042 一起補上（8.11 改字）
    )


def test_wancheng_yi_huang_lock_big_win_fills_the_commander_and_has_no_loser_line():
    text, _ = _announce("wancheng", "huang:大勝", version="乙", lock=("huang", "甲"), losers=[("guan", "乙")], commander="zhujun")
    assert text == (
        "圍城的黃巾糧足，城裡的官軍先斷了糧。甲 替趙弘囤下的糧，比攻城梯還管用，宛城開了門。"
        "朱儁的援軍晚到了一步。"  # {官軍主將} 填朱儁；乙版沒有搶輸的一筆，所以官軍的乙不出現
    )
    assert "{" not in text and "乙" not in text


def test_wancheng_jia_lock_cells_fill_the_commander_slot_and_keep_the_loser_line():
    text, _ = _announce("wancheng", "huang:險勝", version="甲", lock=("huang", "甲"), losers=[("guan", "乙")], commander="zhujun")
    assert text == (
        "史書上，孫堅先登，宛城被破。這一次，城裡的糧倉是滿的，甲 一袋一袋囤下的糧讓宛城撐過了最難的一個月。"
        "宛城守住了，只是城裡的糧也快見底了。"
        "孫堅帶著 乙 攀上東北角，城頭的守兵卻吃得飽、站得穩。"
    )
    text, _ = _announce("wancheng", "huang:大勝", version="甲", lock=("huang", "甲"))  # 沒有主將時 {官軍主將} 填「官軍」
    assert text.endswith("官軍的雲梯一架架被推倒，官軍的兵先散了。")


def test_wancheng_guan_lock_cells_read_named_part_then_tier_sentence():
    text, _ = _announce("wancheng", "guan:險勝", version="乙", lock=("guan", "甲"), losers=[("huang", "乙")], third=["豪甲"])
    assert text == (
        "這一次，宛城在官軍手裡。黃巾圍城數十日，甲 跟著孫堅在一個雨夜縋城而出，直撲黃巾連營。"
        "黃巾的連營被衝亂，趙弘退兵三十里。"
        "宛城殺聲震天的時候，新野縣衙的冊子換了主人：豪甲 開倉放糧，縣裡的人自己把冊子捧了出來。"
    )
    text, _ = _announce("wancheng", "guan:大勝", version="甲", lock=("guan", "甲"), losers=[("huang", "乙")])
    assert text == (
        "史書上，孫堅身當一面，登城先入，大破宛城。這一次，甲 帶著一隊人跟在孫堅身後，從東北角新補的城牆攀了上去。"
        "城門從裡面打開，趙弘死在亂軍之中。"
        "黃巾的 乙 送進城的糧，最後沒能派上用場。"
    )


# ── 時刻表的人物欄位（FB-042，濃縮版內容表第八節，2026-10-05 企劃者定）──────────────────────────────
#
# 「史書上」那半句照寫真名；「這一次」那半句與江湖史寫到的人改成 {人物:<id>}，人物效果的鍵跟著改成 @人物:<id>。
# 下面這張表是照第八節逐格抄的（沒列的欄位照舊），不是從 content 反推。鍵是 (大事, 結果鍵, 欄位)；
# 欄位 "locked_text.guan" 是那一方的具名公告，"figures" 是人物效果的鍵（照順序）。

SECTION_EIGHT_ELEVEN = {  # 8.11（2026-10-05 企劃者同意）：「這一次也一樣」那半句寫出人名
    ("changshe_fire", "guan:大勝", "text"):
        "這一次也一樣：大風夜起，城上舉火，{人物:bocai}的草營燒成一片火海，騎都尉曹操的援兵恰好趕到。",
    ("changshe_fire", "guan:大勝", "locked_text.guan"):
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。"
        "騎都尉曹操的援兵恰好趕到，{人物:bocai}的草營燒成一片火海。",
    ("guangzong", "guan:大勝", "text"):
        "史書上，皇甫嵩夜勒兵，雞鳴馳赴廣宗，斬張梁，黃巾赴河死者五萬。這一次也一樣：{官軍主將}破了廣宗，斬了{人物:zhangliang}。",
}


def test_section_eight_eleven_cells():
    """濃縮版內容表 8.11：三格「這一次」寫出人名；秦頡兩版的朱儁南下要朱儁也在潁川；長社黃巾勝朱儁那一句改字（順序不變）。"""
    c, _ = _real_s1()
    events = {e.id: e for e in c.timetable}
    for (event_id, key, field), expected in SECTION_EIGHT_ELEVEN.items():
        outcome = events[event_id].outcomes[key]
        got = outcome.locked_text["guan"] if field == "locked_text.guan" else getattr(outcome, field)
        assert got == expected, (event_id, key, field)
    for key in ("甲:fixed", "乙:fixed"):
        assert events["qinjie_slays_zhangmancheng"].outcomes[key].figures["zhujun"].only_if == {
            "huangfusong": "yingru", "zhujun": "yingru"}
    for key in ("huang:大勝", "huang:險勝"):
        assert events["changshe_fire"].outcomes[key].figures["zhujun"].note == "留在潁川的官軍，由朱儁收拾殘局。"


def test_bocai_gone_changshe_guan_win_names_his_successor():
    """8.11 的例子：波才先退場、彭脫接手，長社官軍大勝讀到「……彭脫的草營燒成一片火海……」，江湖史也是彭脫。"""
    from tianxia import figures, timetable
    from tianxia.models import FigureChange

    c, here = _real_s1()
    figures.apply(here, c, "bocai", FigureChange(fate="退場"))
    changshe = next(e for e in c.timetable if e.id == "changshe_fire")
    [msg] = timetable.resolve(here, c, changshe, random.Random(0), key="guan:大勝")
    assert "城上舉火，彭脫的草營燒成一片火海" in msg and "這一次也一樣" in msg
    assert here.world.chronicle[-1].text == "皇甫嵩火攻長社，大破彭脫。"


def test_qinjie_skips_zhujuns_march_when_he_is_gone():
    """8.11 二：朱儁已經退場，秦頡那件不再接「右中郎將朱儁也領兵南下」。"""
    from tianxia import figures, timetable
    from tianxia.models import FigureChange
    from tianxia.state import TimelineResult

    c, here = _real_s1()
    figures.apply(here, c, "zhujun", FigureChange(fate="退場"))
    here.world.timeline["zhangmancheng_wan"] = TimelineResult(key="成", time=0.0)
    qinjie = next(e for e in c.timetable if e.id == "qinjie_slays_zhangmancheng")
    [msg] = timetable.resolve(here, c, qinjie, random.Random(0))
    assert "朱儁也領兵南下" not in msg


SECTION_EIGHT = {
    # 8.2 第 3 週・張曼成攻宛城
    ("zhangmancheng_wan", "成", "text"):
        "史書上，張曼成攻殺南陽太守褚貢，屯據宛城。這一次也一樣：{人物:zhangmancheng}的黃旗插上了宛城城頭，郡府的官吏逃散一空。",
    ("zhangmancheng_wan", "成", "chronicle"): "{人物:zhangmancheng}攻殺南陽太守褚貢，據宛城。",
    ("zhangmancheng_wan", "不成", "chronicle"): "{人物:zhangmancheng}攻宛城不下。",
    ("zhangmancheng_wan", "不成", "figures"): ["@人物:zhangmancheng"],
    # 8.3 第 4 週・波才敗朱儁
    ("bocai_routs_zhujun", "成", "text"): "史書上，波才大敗右中郎將朱儁。這一次也一樣：{人物:zhujun}的前軍在潁川郊外被黃巾衝散，退保長社。",
    ("bocai_routs_zhujun", "成", "chronicle"): "{人物:bocai}大敗{人物:zhujun}於潁川。",
    ("bocai_routs_zhujun", "成", "figures"): ["@人物:zhujun"],
    ("bocai_routs_zhujun", "不成", "text"):
        "史書上，波才大敗右中郎將朱儁。這一次，{人物:zhujun}穩住了陣腳，黃巾幾次衝陣都沒衝動，{人物:bocai}只得收兵。",
    ("bocai_routs_zhujun", "不成", "chronicle"): "{人物:zhujun}擋住了{人物:bocai}的攻勢。",
    ("bocai_routs_zhujun", "不成", "figures"): ["@人物:bocai"],
    # 8.4 第 6 週・長社火攻（preface 照舊）
    ("changshe_fire", "guan:大勝", "loser_text.guan"): "黃巾的 {loser} 曾看破火攻、勸{人物:bocai}移營，可惜晚了一步。",
    ("changshe_fire", "guan:險勝", "loser_text.guan"): "黃巾的 {loser} 曾看破火攻、勸{人物:bocai}移營，可惜晚了一步。",
    ("changshe_fire", "guan:大勝", "chronicle"): "{人物:huangfusong}火攻長社，大破{人物:bocai}。",
    ("changshe_fire", "guan:大勝", "figures"): ["@人物:bocai"],
    ("changshe_fire", "guan:險勝", "text"): "這一次，火是放起來了，可風向不定，只燒了半座營。黃巾且戰且退，{人物:bocai}敗走陽翟。",
    ("changshe_fire", "guan:險勝", "locked_text.guan"):
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。"
        "只是風向不定，火只燒了半座營，{人物:bocai}敗走陽翟。",
    ("changshe_fire", "guan:險勝", "chronicle"): "長社一戰，{人物:bocai}敗走陽翟。",
    ("changshe_fire", "guan:險勝", "figures"): ["@人物:bocai"],
    ("changshe_fire", "huang:大勝", "text"): "這一次，火攻沒有成。黃巾趁官軍出城時反撲，{人物:huangfusong}重挫退走。",
    ("changshe_fire", "huang:大勝", "locked_text.huang"):
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 看破了火攻，先一步勸{人物:bocai}移營，那一夜燒的是一座空營。"
        "黃巾反從上風殺出，{人物:huangfusong}重挫退走。",
    ("changshe_fire", "huang:大勝", "note"): "潁川得手之後，{人物:bocai}分兵北上，往廣宗去了。",
    ("changshe_fire", "huang:險勝", "text"): "這一次，火攻沒有成。黃巾死戰不退，官軍折損甚重，{人物:huangfusong}重挫退走。",
    ("changshe_fire", "huang:險勝", "locked_text.huang"):
        "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，{name} 看破了火攻，先一步勸{人物:bocai}移營，那一夜燒的是一座空營。"
        "黃巾趁亂反撲，官軍折損甚重，{人物:huangfusong}重挫退走。",
    ("changshe_fire", "huang:大勝", "chronicle"): "長社火攻失利，{人物:huangfusong}重挫。",
    ("changshe_fire", "huang:險勝", "chronicle"): "長社火攻失利，{人物:huangfusong}重挫。",
    ("changshe_fire", "huang:大勝", "figures"): ["zhujun", "@人物:huangfusong"],  # 朱儁那筆排在前面（見下面的測試）
    ("changshe_fire", "huang:險勝", "figures"): ["zhujun", "@人物:huangfusong"],
    # 8.5 第 7 週・盧植圍廣宗
    ("luzhi_siege", "成", "text"):
        "史書上，盧植連戰破賊，把張角圍在廣宗，築圍鑿塹、造雲梯，眼看就要破城。這一次也一樣：{人物:luzhi}把{人物:zhangjiao}圍在了廣宗。",
    ("luzhi_siege", "成", "chronicle"): "{人物:luzhi}圍{人物:zhangjiao}於廣宗。",
    ("luzhi_siege", "成", "figures"): ["@人物:zhangjiao"],
    ("luzhi_siege", "不成", "text"):
        "史書上，盧植把張角圍在廣宗。這一次，黃巾在廣宗城外連營數十里，{人物:luzhi}的圍塹還沒挖成就被衝開，只能退守大營。",
    ("luzhi_siege", "不成", "chronicle"): "{人物:luzhi}圍廣宗不成，退守大營。",
    ("luzhi_siege", "不成", "figures"): ["@人物:luzhi"],
    # 8.6 第 7 週・秦頡（只拿掉寫死的接手者）
    ("qinjie_slays_zhangmancheng", "甲:fixed", "text"):
        "新任南陽太守秦頡引兵來攻，張曼成在宛城下被斬。神上使一死，黃巾收攏餘眾，又把宛城守了起來。",
    ("qinjie_slays_zhangmancheng", "乙:fixed", "text"): "援兵統帥秦頡趕到南陽，張曼成在宛城外被斬。黃巾在城外重整連營，圍城不退。",
    ("qinjie_slays_zhangmancheng", "甲:fixed", "chronicle"): "秦頡斬張曼成。",
    ("qinjie_slays_zhangmancheng", "乙:fixed", "chronicle"): "秦頡斬張曼成。",
    # 8.7 第 8 週・盧植下獄（skip_if_out 見下面的測試）
    ("luzhi_jailed", "成", "loser_text.huang"): "官軍的 {loser} 蒐齊的證據送進了大將軍府，卻遲遲沒有下文。",
    # 8.8 第 9 週・宛城之戰
    ("wancheng", "甲:guan:大勝", "text"):
        "史書上，孫堅身當一面，登城先入，大破宛城。這一次也一樣：{人物:sunjian}的兵攀上東北角的城牆，城門從裡面打開了。",
    ("wancheng", "甲:guan:大勝", "locked_text.guan"):
        "史書上，孫堅身當一面，登城先入，大破宛城。這一次，{name} 帶著一隊人跟在{人物:sunjian}身後，從東北角新補的城牆攀了上去。"
        "城門從裡面打開，{人物:zhaohong}死在亂軍之中。",
    ("wancheng", "甲:guan:大勝", "figures"): ["@人物:zhaohong"],
    ("wancheng", "甲:guan:險勝", "text"): "史書上，孫堅先登，大破宛城。這一次，宛城是破了，可{人物:zhaohong}帶著殘部從南門突圍。",
    ("wancheng", "甲:guan:險勝", "locked_text.guan"):
        "史書上，孫堅身當一面，登城先入，大破宛城。這一次，{name} 帶著一隊人跟在{人物:sunjian}身後，從東北角新補的城牆攀了上去。"
        "宛城是破了，可{人物:zhaohong}帶著殘部從南門突圍。",
    ("wancheng", "甲:guan:險勝", "figures"): ["@人物:zhaohong"],
    ("wancheng", "甲:guan:大勝", "chronicle"): "{人物:sunjian}先登，宛城破。",
    ("wancheng", "甲:guan:險勝", "chronicle"): "{人物:sunjian}先登，宛城破。",
    ("wancheng", "甲:huang:大勝", "loser_text.huang"): "{人物:sunjian}帶著 {loser} 攀上東北角，城頭的守兵卻吃得飽、站得穩。",
    ("wancheng", "甲:huang:險勝", "loser_text.huang"): "{人物:sunjian}帶著 {loser} 攀上東北角，城頭的守兵卻吃得飽、站得穩。",
    ("wancheng", "乙:guan:大勝", "text"): "這一次，宛城在官軍手裡。{人物:sunjian}在雨夜縋城而出，直撲黃巾連營，{人物:zhaohong}死在亂軍之中。",
    ("wancheng", "乙:guan:大勝", "locked_text.guan"):
        "這一次，宛城在官軍手裡。黃巾圍城數十日，{name} 跟著{人物:sunjian}在一個雨夜縋城而出，直撲黃巾連營。"
        "{人物:zhaohong}死在亂軍之中，圍城不攻自解。",
    ("wancheng", "乙:guan:大勝", "figures"): ["@人物:zhaohong"],
    ("wancheng", "乙:guan:險勝", "text"): "這一次，宛城在官軍手裡。黃巾的連營被{人物:sunjian}衝亂，{人物:zhaohong}退兵三十里。",
    ("wancheng", "乙:guan:險勝", "locked_text.guan"):
        "這一次，宛城在官軍手裡。黃巾圍城數十日，{name} 跟著{人物:sunjian}在一個雨夜縋城而出，直撲黃巾連營。"
        "黃巾的連營被衝亂，{人物:zhaohong}退兵三十里。",
    ("wancheng", "乙:guan:險勝", "figures"): ["@人物:zhaohong"],
    ("wancheng", "乙:guan:大勝", "chronicle"): "{人物:sunjian}夜襲，解宛城之圍。",
    ("wancheng", "乙:guan:險勝", "chronicle"): "{人物:sunjian}夜襲，解宛城之圍。",
    ("wancheng", "乙:huang:大勝", "locked_text.huang"):
        "圍城的黃巾糧足，城裡的官軍先斷了糧。{name} 替{人物:zhaohong}囤下的糧，比攻城梯還管用，宛城開了門。{官軍主將}的援軍晚到了一步。",
    ("wancheng", "乙:huang:險勝", "locked_text.huang"):
        "圍城的黃巾糧足，城裡的官軍先斷了糧。{name} 替{人物:zhaohong}囤下的糧，比攻城梯還管用，宛城開了門。但黃巾也死傷慘重。",
    # 8.9 第 11 週・廣宗
    ("guangzong", "guan:大勝", "chronicle"): "{官軍主將}破廣宗，斬{人物:zhangliang}。",
    ("guangzong", "guan:大勝", "figures"): ["@人物:zhangliang", "zhangjiao"],
    ("guangzong", "guan:險勝", "text"): "史書上，皇甫嵩破廣宗，斬張梁。這一次，廣宗的外城破了，{人物:zhangliang}退守內城。",
    ("guangzong", "guan:險勝", "figures"): ["@人物:zhangliang"],
    ("guangzong", "huang:大勝", "text"):
        "史書上，皇甫嵩破廣宗，斬張梁。這一次，{人物:zhangliang}領著死士夜出，官軍大營起火，{官軍主將}退走。",
}


def _real_s1():
    """真實內容（週末設定，第一季開關打開）的一季＋季的事用的那種空殼玩家（人物照人物表種好）。"""
    from tianxia.state import GameState, PlayerState
    from tianxia.world_state import fresh_season

    c = load_content(CONTENT_DIR, profile="weekend")
    state = GameState(player=PlayerState(name="", location=c.scenario.start_location, stats={}, stamina=0),
                      world=fresh_season(c))
    return c, state


def test_section_eight_cells_are_in_the_timetable_word_for_word():
    c = load_content(CONTENT_DIR)
    events = {e.id: e for e in c.timetable}
    for (event_id, key, field), expected in SECTION_EIGHT.items():
        outcome = events[event_id].outcomes[key]
        if field == "figures":
            actual = list(outcome.figures)
        elif "." in field:
            name, side = field.split(".")
            actual = getattr(outcome, name).get(side)
        else:
            actual = getattr(outcome, field)
        assert actual == expected, (event_id, key, field)


# 8.10 不改的大事，與第八節刻意照寫真名的幾件（秦頡要張曼成還在才發生、盧植下獄寫的是朝廷的任命）
NAMES_KEPT = {"uprising", "court_mobilizes", "qinjie_slays_zhangmancheng", "luzhi_jailed", "zhangjiao_dies", "xiaquyang"}
# 「這一次」那半句不能寫死的稱呼：人物表上的名字，加上只對那一位成立的稱號與官銜（第八節逐條拿掉的）
FIGURE_TITLES = ("神上使", "江東子弟", "孫文臺", "人公將軍", "右中郎將")
PLAIN_KEYS_KEPT = {("changshe_fire", "huang:大勝", "zhujun"), ("changshe_fire", "huang:險勝", "zhujun"),
                   ("guangzong", "guan:大勝", "zhangjiao")}


def test_the_this_time_half_names_nobody_directly():
    """FB-042：「這一次」那半句、江湖史、note、搶輸的一句都不寫死人名（人物被挑戰打到退場之後就會寫錯人）——一律是
    {人物:<id>} 或 {官軍主將}。人物效果的鍵也一樣是 @人物 或 @commander；照寫人物 id 的只剩第八節列明的三筆。"""
    c = load_content(CONTENT_DIR)
    banned = [fig.name for fig in c.figures.values()] + list(FIGURE_TITLES)
    for e in c.timetable:
        if e.id in NAMES_KEPT:
            continue
        for key, o in e.outcomes.items():
            halves = [t.split("這一次", 1)[-1] for t in (o.text, *o.locked_text.values())]
            notes = [ch.note for k, ch in o.figures.items() if (e.id, key, k) not in PLAIN_KEYS_KEPT]  # 「潁川交給了朱儁」只在朱儁在時才接
            for line in [*halves, o.note, o.chronicle, *o.loser_text.values(), *notes]:
                assert not [w for w in banned if w in line], (e.id, key, line)
            plain = [k for k in o.figures if not k.startswith("@") and (e.id, key, k) not in PLAIN_KEYS_KEPT]
            assert plain == [], (e.id, key)


def test_changshe_huang_win_hands_yingru_to_zhujun_only_when_huangfusong_held_it():
    """S1 第 1 項：長社黃巾勝，「潁川交給了朱儁」移到朱儁那筆人物效果的 note（不改數字、皇甫嵩與朱儁都在潁川才套），
    排在皇甫嵩那筆前面（檢查條件時皇甫嵩還沒轉走）。皇甫嵩先被打到退場、潁川由朱儁接手時，重挫的就是朱儁本人，
    不再寫「交給了朱儁」。"""
    from tianxia import figures, timetable
    from tianxia.models import FigureChange

    c, here = _real_s1()
    changshe = next(e for e in c.timetable if e.id == "changshe_fire")
    for key in ("huang:大勝", "huang:險勝"):
        assert changshe.outcomes[key].figures["zhujun"] == FigureChange(
            only_if={"huangfusong": "yingru", "zhujun": "yingru"}, note="留在潁川的官軍，由朱儁收拾殘局。",
        )
    msgs = timetable.resolve(here, c, changshe, random.Random(0), key="huang:險勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，火攻沒有成。黃巾死戰不退，官軍折損甚重，皇甫嵩重挫退走。留在潁川的官軍，由朱儁收拾殘局。"]
    assert (here.world.figures["huangfusong"].front, here.world.figures["zhujun"].front) == ("jizhou", "yingru")
    assert here.world.figures["zhujun"].prestige == 60  # 朱儁那筆不動數字
    assert here.world.chronicle[-1].text == "長社火攻失利，皇甫嵩重挫。"

    _, gone = _real_s1()
    figures.apply(gone, c, "huangfusong", FigureChange(fate="退場"))  # 朱儁本來就在潁川：接下潁川
    msgs = timetable.resolve(gone, c, changshe, random.Random(0), key="huang:險勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，火攻沒有成。黃巾死戰不退，官軍折損甚重，朱儁重挫退走。"]
    zhujun = gone.world.figures["zhujun"]
    assert (zhujun.front, zhujun.location, zhujun.prestige) == ("jizhou", "luzhi_camp", 30)  # 重挫照舊轉往冀州盧植營
    assert gone.world.chronicle[-1].text == "長社火攻失利，朱儁重挫。"


def test_luzhi_jailed_is_skipped_once_luzhi_is_out():
    """S1 第 2 項：盧植已經退場（冀州照接位鏈交給了董卓）就整件跳過，同張角病逝——不公告、不套效果、鎖定也不算；
    搶輸的一句不寫何進（天命人物，可能先被打到重創）。"""
    from tianxia import figures, timetable
    from tianxia.models import FigureChange
    from tianxia.state import Lock

    c, s = _real_s1()
    jailed = next(e for e in c.timetable if e.id == "luzhi_jailed")
    assert jailed.skip_if_out == "luzhi" and "何進" not in jailed.outcomes["成"].loser_text["huang"]
    figures.apply(s, c, "luzhi", FigureChange(fate="退場"))
    assert (s.world.figures["dongzhuo"].status, s.world.figures["dongzhuo"].front) == ("active", "jizhou")
    s.world.locks["luzhi_jailed"] = Lock(side="huang", name="甲", time=0.0)
    trends, chronicle = dict(s.world.trends), list(s.world.chronicle)
    assert timetable.resolve(s, c, jailed, random.Random(0)) == []
    assert s.world.timeline["luzhi_jailed"].key == timetable.SKIPPED
    assert (s.world.trends, s.world.chronicle) == (trends, chronicle)

    _, there = _real_s1()  # 盧植還在：照舊結算（鎖定的黃巾定成「成」，董卓到任）
    there.world.locks["luzhi_jailed"] = Lock(side="huang", name="甲", time=0.0)
    assert timetable.resolve(there, c, jailed, random.Random(0))
    assert (there.world.figures["luzhi"].status, there.world.timeline["luzhi_jailed"].key) == ("jailed", "成")


def test_qinjie_no_longer_names_the_heir():
    """S1 第 3 項：秦頡斬張曼成不寫「推趙弘為帥」——趙弘可能早就被挑戰打到退場，接手的是韓忠；誰接手由接手那則
    天下大事講。"""
    c = load_content(CONTENT_DIR)
    qinjie = next(e for e in c.timetable if e.id == "qinjie_slays_zhangmancheng")
    for o in qinjie.outcomes.values():
        assert "趙弘" not in o.text + o.chronicle and "推趙弘為帥" not in o.text


def test_every_person_slot_resolves_whoever_is_left():
    """真實時刻表每一格（季末除外）都結算得了：人物都在時寫名字；人物全都不在時寫泛稱、@人物 的效果略過、不丟例外。
    兩種情形都沒有沒填的欄位留在公告、傳聞與江湖史裡。"""
    from tianxia import timetable

    c, _ = _real_s1()
    for e in c.timetable:
        for key in e.outcomes:
            for everyone_out in (False, True):
                _, s = _real_s1()
                if everyone_out:
                    for figure in s.world.figures.values():
                        figure.status = "retired"
                msgs = timetable.resolve(s, c, e, random.Random(0), key=key)
                written = msgs + [r.text for r in s.world.rumors] + [r.text for r in s.world.chronicle]
                assert not [t for t in written if "{" in t], (e.id, key, everyone_out, written)
    _, s = _real_s1()
    for figure in s.world.figures.values():
        figure.status = "retired"
    wancheng = next(e for e in c.timetable if e.id == "wancheng")
    msgs = timetable.resolve(s, c, wancheng, random.Random(0), key="乙:guan:險勝")
    assert msgs == ["【江湖大事】這一次，宛城在官軍手裡。黃巾的連營被官軍主將衝亂，黃巾渠帥退兵三十里。"]


def test_the_timetable_never_runs_with_the_switch_off():
    """開關關著（beta 那一季）時時刻表整個不跑：一整季推到收季，時刻表一件也不結算、句子一句也不填，沒有人物欄位寫進
    傳聞或江湖史。FB-042 改的是時刻表的句子與結算，所以 beta 的行為一個字都不變。"""
    from tianxia import timetable
    from tianxia.world import advance_world_state
    from tianxia.world_state import fresh_season, season_length_days

    c = load_content(CONTENT_DIR)
    assert not c.config.season_one
    w = fresh_season(c)
    untouched = AssertionError("開關關著時不該碰時刻表")
    with mock.patch.object(timetable, "resolve", side_effect=untouched), \
            mock.patch.object(timetable, "fill_slots", side_effect=untouched):
        msgs = advance_world_state(w, c, season_length_days(w, c) * 86400 + 3600, random.Random(0))
    assert w.ended and w.timeline == {} and w.figures == {}
    written = msgs + [r.text for r in w.rumors] + [r.text for r in w.chronicle]
    assert written and not [t for t in written if "{人物" in t]


# ── 第一季不觸發的 beta 內容（計畫 T8；控制者 2026-10-04）──────────────────────────────


def _beta_season(c, tmp_path, name: str):
    """一季剛開（照 c 的開關蓋章）、一位管理者 Rayal 的 Game 與它的資料庫；季的事與虛擬玩家先拿掉，只看門檻。"""
    from tianxia.sqlite_world import open_world

    c.scenario.sim_players = []
    c.config.auto_open_first_season = True
    game = Game.new(c, "Rayal", rng=random.Random(0), world=open_world(tmp_path / f"{name}.db"))
    game.now = 0.0
    return game


def _push_huangjin_to(game, value: int) -> None:
    """黃巾聲勢推到 value：開關開著時它由三條戰線合成，三條都設成 value；關著時直接設。"""
    from tianxia.rules import recompute_trends

    w = game.state.world
    for key in ("yingru", "nanyang", "jizhou") if w.season_one else ("huangjin",):
        w.trends[key] = value
    recompute_trends(w, game.content)


def test_season_one_off_blocks_thresholds_storyline_and_beta_battle(tmp_path):
    """開關打開、季蓋了章：黃巾聲勢推到 50／60／80／10 都不觸發（沒有 road_blocked、不開戰、不收季、沒有
    huangjin_crushed）；「主線與目標」沒有黃巾之亂；管理者的開戰選單沒有 beta 那場、也開不了。開關關著時四個門檻與主線照舊。"""
    from tianxia.guide import quest_text
    from tianxia.world import check_thresholds

    c = load_content(CONTENT_DIR, profile="weekend")
    off = c.scenario.season_one_off
    assert (off.thresholds, off.storylines, off.battles) == (
        ["huangjin_50", "huangjin_60", "huangjin_80", "huangjin_10"], ["huangjin_line"], ["huangjin_showdown"],
    )
    # 個人目標裡那四個也做不到了（波才的舊事件、平定門檻、beta 那場決戰都關了）：不列（PM：主線與目標不顯示做不到的目標）
    assert off.milestones == ["beat_bocai", "crush_huangjin", "showdown_win", "showdown_loss"]
    game = _beta_season(c, tmp_path, "on")
    w = game.state.world
    assert w.season_one
    for value in (50, 60, 80, 10):
        _push_huangjin_to(game, value)
        check_thresholds(game.state, c, game.world, now=0.0)
    assert not ({"huangjin_50", "huangjin_60", "huangjin_80", "huangjin_10"} & w.fired_thresholds)
    assert not ({"road_blocked", "huangjin_win", "huangjin_crushed"} & w.flags) and not w.ended
    assert game.world.get_battle() is None
    assert (w.storyline, w.act) == ("huangjin_line", 0)
    assert "黃巾之亂" not in quest_text(game.state, c) and "黃巾橫行" not in quest_text(game.state, c)
    goals = quest_text(game.state, c)
    assert "投身潁川書院或曹氏莊院" in goals and "名望達到 10" in goals  # 做得到的照列
    assert not any(t in goals for t in ("擊敗波才", "平定黃巾", "打贏黃巾決戰", "黃巾決戰落敗"))
    assert "huangjin_showdown" not in [b.id for b in game.admin_battles()]
    assert "huangjin_60" not in [x.id for x in game.admin_fires()]
    assert game.admin_start_battle("huangjin_showdown", now=0.0) == ["（沒有這場戰鬥。）"]
    assert game.world.get_battle() is None

    beta = load_content(CONTENT_DIR)  # 開關關著：beta 那一季照舊
    game = _beta_season(beta, tmp_path, "off")
    w = game.state.world
    assert not w.season_one and "黃巾之亂" in quest_text(game.state, beta)
    assert all(t in quest_text(game.state, beta) for t in ("擊敗波才", "平定黃巾", "打贏黃巾決戰", "黃巾決戰落敗"))
    _push_huangjin_to(game, 60)
    check_thresholds(game.state, beta, game.world, now=0.0)
    assert {"huangjin_50", "huangjin_60"} <= w.fired_thresholds and "road_blocked" in w.flags
    assert game.world.get_battle().battle_id == "huangjin_showdown"
    assert "huangjin_showdown" in [b.id for b in game.admin_battles()]
    _push_huangjin_to(game, 10)
    check_thresholds(game.state, beta, game.world, now=0.0)
    assert "huangjin_crushed" in w.flags
    _push_huangjin_to(game, 80)
    check_thresholds(game.state, beta, game.world, now=0.0)
    assert w.ended and "huangjin_win" in w.flags


# ── 三場大戲（計畫 T8；戰鬥系統附錄 A）──────────────────────────────────

SHOWDOWN_TABLE = {  # 計畫 T8 的表：大區、守方、時刻表大事、版本、戰線
    "changshe_fire": ("yingru", "guan", "changshe_fire", None, "yingru"),
    "wancheng_jia": ("nanyang", "huang", "wancheng", "甲", "nanyang"),
    "wancheng_yi": ("nanyang", "guan", "wancheng", "乙", "nanyang"),
    "guangzong": ("jizhou", "huang", "guangzong", None, "jizhou"),
}
SHOWDOWN_ACTS = {  # 決戰改版一的三招表：每幕標題，與官軍、黃巾各自的強攻／固守／奇襲（設計 session 的草稿，待 joy 潤）
    "changshe_fire": [
        ("長社被圍", "開門突擊黃巾前營", "固守城頭", "縋城而下，夜探敵營虛實", "架起雲梯，強攻城牆", "圍住四門，斷絕城中糧道", "挖掘地道，潛向城根"),
        ("夜風將起", "點齊兵馬，出城衝營", "按兵不動，靜待時機", "縋城而下，襲擾敵營", "趁夜猛攻城門", "收攏營寨，嚴加戒備", "趁夜摸上城頭"),
        ("決勝長社", "全軍出城，衝擊敵陣", "守住城門，穩住陣腳", "分兵出側門，抄敵後路", "全軍壓上，奪下城門", "穩住營盤，步步進逼", "繞到城北，偷開小門"),
    ],
    "wancheng_jia": [
        ("兵臨宛城", "推上雲梯，強攻城牆", "深溝高壘，困住宛城", "趁夜挖掘地道", "開門出擊，衝散攻城兵", "閉門死守，輪番上城", "縋城夜出，燒毀土山"),
        ("四面攻城", "集中一面，蟻附登城", "輪番佯攻，耗盡守軍", "聲東擊西，暗襲另一面城牆", "開城反衝，殺退攻城兵", "添兵守垛，滾木擂石", "夜縋出城，焚燒雲梯"),
        ("城破與否", "全軍登城，畢其功於一役", "圍死四門，不放一人", "挑選精兵，夜攀城角", "傾城而出，殺散圍軍", "死守最後一道城門", "分兵出城，偷襲官軍後營"),
    ],
    "wancheng_yi": [
        ("連營圍城", "開門突擊，衝亂連營", "閉城固守，清點糧草", "派小隊出城，燒敵營柵", "趁城中未穩，架梯強攻", "圍住四門，斷絕糧道", "扮作逃難百姓，混近城門"),
        ("圍城日久", "整頓兵馬，出城衝營", "節省糧草，輪番守城", "派死士夜出，燒敵糧車", "四面同時攻城", "加固連營，圍而不攻", "夜派輕兵，繞到城後放火"),
        ("城門開不開", "傾城出戰，解圍在此一舉", "死守城門，寸步不讓", "分兵出側門，抄敵後營", "全軍蟻附，奪下城頭", "穩住連營，步步進逼", "趁夜攀城，打開城門"),
    ],
    "guangzong": [
        ("廣宗城下", "架起雲梯，強攻城牆", "築圍挖塹，步步緊逼", "夜遣輕兵，探城中虛實", "開門出擊，衝散圍塹", "閉門堅守，以逸待勞", "縋城夜出，燒毀官軍器械"),
        ("堅城難下", "晝夜不停，輪番攻城", "閉營休兵，佯示退意", "佯退設伏，誘敵出城", "開門追擊，掩殺官軍", "輪班上城，保存氣力", "趁官軍疲憊，夜襲大營"),
        ("雞鳴", "雞鳴而發，全軍撲城", "穩住陣線，堵死各門", "挑選死士，夜攀城角", "傾城而出，決一死戰", "死守內城，寸土不讓", "死士出城，直撲中軍"),
    ],
}


def test_real_battles_three_showdowns(content):
    """真實內容有四筆時刻表決戰（宛城分甲乙兩筆）：大區、守方、時刻表大事、版本、戰線照計畫 T8 的表；三幕照戰鬥系統附錄 A；
    推力、放手一搏、時間、提前收場跟 beta 那場一模一樣；結果只留一筆保底（實際效果走時刻表）。"""
    beta = content.battles["huangjin_showdown"]
    showdowns = {bid: b for bid, b in content.battles.items() if b.timetable_event is not None}
    assert set(showdowns) == set(SHOWDOWN_TABLE)
    for bid, (region, defender, event_id, version, front) in SHOWDOWN_TABLE.items():
        b = showdowns[bid]
        assert (b.region, b.defender, b.timetable_event, b.version, b.front) == (region, defender, event_id, version, front), bid
        assert [(f.id, f.name) for f in b.factions] == [("guan", "官軍"), ("huang", "黃巾軍")]
        assert (b.trend_start, b.rounds_per_act, b.decisive_margin) == (50, 3, 40)
        assert (b.muster_seconds, b.round_seconds) == (beta.muster_seconds, beta.round_seconds)
        assert not b.action_tags and b.free_text_gamble == beta.free_text_gamble  # 固定招走三招，沒有查表
        assert len(b.outcomes) == 1 and b.outcomes[0].trend_min is None and b.outcomes[0].trend_max is None
        assert not b.outcomes[0].trend_delta and not b.outcomes[0].world_flags_add  # 效果走時刻表，不重複套
        acts = []
        for act in b.acts:
            fixed = {(o.faction, o.tag): o.text for o in act.options if not o.free_text}
            acts.append((act.title, *(fixed[side, f"{side}_{code}"]
                                      for side in ("guan", "huang") for code in ("strong", "hold", "raid"))))
            assert sorted(o.tag for o in act.options if o.free_text) == ["guan_reckless", "huang_reckless"]
            assert set(act.text_by_lead) == {"guan", "huang"}  # 每幕兩個佔上風的版本（句子是草稿，待 joy 潤，不釘死）
        assert acts == SHOWDOWN_ACTS[bid]
    events = {e.id: e for e in content.timetable}
    for bid, b in showdowns.items():  # 每一件時刻表決戰、每一個版本都正好有一筆
        event = events[b.timetable_event]
        assert event.kind == "showdown" and (b.version in event.versions.values() if event.versions else b.version is None)
    assert sorted((b.timetable_event, b.version or "") for b in showdowns.values()) == sorted([
        ("changshe_fire", ""), ("guangzong", ""), ("wancheng", "甲"), ("wancheng", "乙"),
    ])


ALL_BATTLES = ["huangjin_showdown", "changshe_fire", "wancheng_jia", "wancheng_yi", "guangzong"]
CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}


def test_every_real_battle_is_three_moves_per_side_in_every_act(content):
    """決戰改版一：五場（黃巾決戰保留，預設的季打的是它）每一幕每一邊都是強攻、固守、奇襲各一個，加一個放手一搏；
    沒有舊的查表、每幕有兩個佔上風的版本。選項名的字數也守住（網頁按鈕 375px 上一行放得下：十三字內）。"""
    assert set(ALL_BATTLES) <= set(content.battles)
    for bid in ALL_BATTLES:
        battle = content.battles[bid]
        assert not battle.action_tags and battle.free_text_gamble is not None, bid
        for act in battle.acts:
            where = f"{bid} {act.id}"
            for side in ("guan", "huang"):
                mine = [o for o in act.options if o.faction == side]
                fixed = [o for o in mine if not o.free_text]
                assert [(o.move, o.tag) for o in fixed] == [(m, f"{side}_{c}") for m, c in CODES.items()], where
                assert [o.tag for o in mine if o.free_text] == [f"{side}_reckless"] and mine[-1].free_text, where
                assert all(0 < len(o.text) <= 13 for o in fixed), (where, [o.text for o in fixed])
            assert set(act.text_by_lead) == {"guan", "huang"}, where
            assert len({act.text, *act.text_by_lead.values()}) == 3 and all(act.text_by_lead.values()), where


def test_server_bots_play_the_real_showdowns_by_move_not_at_random(tmp_path):
    """決戰改版一 Task 5 之前，真實內容的選項沒有 move，假人對每個選項都是 0 分、等於亂出；換成三招之後照自己每招的份量挑。"""
    from tianxia import battle_instance as bi
    from tianxia import bot_policy
    from tianxia.engine import Option
    from tianxia.models import MOVES
    from tianxia.state import BotProfile

    c = load_content(CONTENT_DIR)
    c.config.bot_strength = 1.0
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert set(MOVES) == set(CODES)
    for bid in ALL_BATTLES:
        game = _beta_season(c, tmp_path, f"bots_{bid}")  # 每一場一個自己的世界：同時只能有一場決戰
        game.world.start_battle(c.battles[bid], now=0.0)
        name = game.state.player.name
        game.world.mutate_battle(lambda b: bi.join_faction(b, name, "guan", 400.0, scores={"強攻": 30.0, "固守": 30.0, "奇襲": 90.0}))
        scores = {m: bot_policy._battle_score(game, f"act:guan_{code}") for m, code in CODES.items()}
        assert max(scores, key=scores.get) == "奇襲" and len(set(scores.values())) == 3, (bid, scores)
        options = [Option(id=f"battle:act:guan_{code}", label=m) for m, code in CODES.items()]
        picks = {bot_policy.pick(game, options, profile, random.Random(seed)) for seed in range(20)}
        assert picks == {"battle:act:guan_raid"}, bid  # 強度全開：每次都出份量最高的那一招


@pytest.mark.parametrize(("battle_id", "winner"), [
    ("changshe_fire", "guan"), ("guangzong", "huang"), ("wancheng_jia", "huang"), ("wancheng_yi", "guan"),
])
def test_real_showdowns_tie_goes_to_defender(content, battle_id, winner):
    """計畫 T8：長社 50→官軍險勝；廣宗 50→黃巾險勝；宛城甲 50→黃巾、乙 50→官軍（戰鬥系統 4.2、附錄 A.5）。"""
    from tianxia import battle_instance as bi

    definition = content.battles[battle_id]
    instance = bi.start_muster(definition, now=0.0)
    assert bi.decide_result(instance, definition, None, definition.defender) == (winner, "險勝")


def test_wan_city_reads_like_its_version_from_week_three(content):
    """宛城的描寫第 3 週起依版本換（伏筆文件 5.0）：甲版黃巾據城、官軍大營在城外；乙版太守守住、黃巾在城外連營；
    乙版宛城陷落之後換成甲版的描寫（結算文件 5.2）。版本的旗標由第 3 週「張曼成攻殺南陽太守」的結果寫入。"""
    wan = content.locations["wan_city"]
    zhang = next(e for e in content.timetable if e.id == "zhangmancheng_wan").outcomes
    jia_flag, = zhang["成"].world_flags_add
    yi_flag, = zhang["不成"].world_flags_add
    assert wan.describe(set()) == wan.description
    jia, yi = wan.describe({jia_flag}), wan.describe({yi_flag})
    assert "黃" in jia and "城外" in jia and "連營" in yi and len({jia, yi, wan.description}) == 3
    assert wan.describe({yi_flag, "wancheng_fallen"}) == jia


def test_a_real_weekend_season_opens_and_settles_the_three_showdowns(tmp_path):
    """週末設定的真實內容：長社、宛城、廣宗照排定的時間在各自的大區開集結（起點照當時的戰況），沒人參戰也照起點判、
    交給時刻表結算（宛城帶版本前綴）；beta 那場一次也沒開。"""
    from tianxia import battle_instance as bi
    from tianxia.rules import trend_value
    from tianxia.sqlite_world import open_world

    c = load_content(CONTENT_DIR, profile="weekend")
    c.config.auto_open_first_season = True
    c.config.geju_chaos_per_day = 0.0  # 割據不漲：沒人玩時三條戰線一直在亂局，割據第 5 週就過 85，第 10 週（decisive_from_week）起會以「群雄並起」提前收季，廣宗與季末就輪不到；這裡測的不是它
    world = open_world(tmp_path / "weekend.db")
    game = Game.new(c, "Rayal", rng=random.Random(0), world=world)
    game.now = 0.0
    for event_id, region in (("changshe_fire", "yingru"), ("wancheng", "nanyang"), ("guangzong", "jizhou")):
        game.advance(game.state.world.schedule[event_id] + 1.0 - game.state.world.time)
        battle = world.get_battle()
        definition = c.battles[battle.battle_id]
        assert (definition.timetable_event, definition.region, battle.phase) == (event_id, region, "muster")
        assert battle.trend == bi.start_from_front(trend_value(game.state, c, definition.front))
        deadline = battle.muster_deadline_real
        for now in (deadline, deadline + definition.round_seconds):
            game.now = now
            game.options()
        key = world.get_season().timeline[event_id].key
        version = f"{definition.version}:" if definition.version else ""
        assert key == f"{version}{':'.join(bi.decide_result(battle, definition, None, definition.defender))}"
    assert [b.battle_id for _, b in world.ended_battles()] == [
        "changshe_fire", world.get_season().showdowns_opened["wancheng"], "guangzong",
    ]


def test_real_showdowns_start_from_the_opening_fronts():
    """計畫 T8：開季那一刻照前線算的起點是長社 55（潁川 40）、宛城 58（南陽 35）、廣宗 48（冀州 55）。"""
    from tianxia.state import GameState, PlayerState
    from tianxia.world import showdown_battle, showdown_start
    from tianxia.world_state import fresh_season

    c = load_content(CONTENT_DIR, profile="weekend")
    state = GameState(player=PlayerState(name="", location=c.scenario.start_location, stats={}, stamina=0), world=fresh_season(c))
    starts = {
        e.id: showdown_start(state, c, showdown_battle(state, c, e)) for e in c.timetable if e.kind == "showdown"
    }
    assert starts == {"changshe_fire": 55, "wancheng": 58, "guangzong": 48}


@pytest.mark.parametrize("season_one", [False, True])
def test_every_idle_menu_id_is_one_the_prologue_allow_list_knows(content, tmp_path, season_one):
    """序章每一步的 allow 只准寫閒著的選單真的做得出來的 id（models.allow_known）。整季隨機玩，每一個閒著的選單（有「打坐」；
    決戰集結時前面多的 battle: 不算）裡的 id 都要被認得：引擎多了新的行動、沒有列進 ALLOW_FIXED／ALLOW_FAMILIES，這裡就會叫。"""
    from tianxia.models import allow_known
    from tianxia.sqlite_world import open_world

    real = content.model_copy(deep=True)
    real.config.season_one = season_one
    seen: set[str] = set()

    def observe(game):
        ids = [o.id for o in game.options(odds=False, tick=False)]
        if "act:rest" in ids:
            seen.update(oid for oid in ids if not oid.startswith("battle:"))

    play_season(real, 2, max_steps=700, observe=observe, world=open_world(tmp_path / f"idle-{season_one}.db"))
    assert {"act:explore", "act:rest"} <= seen and any(oid.startswith("move:") for oid in seen)
    stray = {oid for oid in seen if not allow_known(oid)}
    assert not stray, f"閒著的選單上有、models.ALLOW_FIXED／ALLOW_FAMILIES 沒列的 id：{sorted(stray)}（引擎新加的行動要補進去）"
