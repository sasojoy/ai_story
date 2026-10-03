"""跑真正的 content/ 內容（黃巾之亂・三國重皮），不是 tests/fixtures/content 的測試夾具。

跟本機 Ollama 有關的路徑（companion_agent.py 的深度對話、定期記憶梳理）一律 monkeypatch
掉：這裡要驗證的是內容本身的結構完整性與遊戲規則，不是要連真正的模型（會慢、會不穩定，
也會讓 CI 環境在沒裝 Ollama 時整個掛掉）。
"""
from __future__ import annotations

import html
import random
import re
from collections import deque
from pathlib import Path
from unittest import mock

import pytest

from tianxia import companion_agent, roster
from tianxia.atlas import region_of
from tianxia.bot import play_season
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.mapview import render_map, render_minimap, text_width
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
    assert 20 <= len(c.locations) <= 30
    assert {t.id for t in c.scenario.trends} == {"huangjin", "yuxi"}


def test_real_content_waits_for_the_admin_to_open_the_season():
    assert load_content(CONTENT_DIR).config.auto_open_first_season is False


def test_travel_settings_follow_the_map_design(content):
    cfg = content.config
    assert cfg.stamina_regen_seconds == 180 and cfg.rest_regen_multiplier == 2
    assert cfg.road_factor == {"官道": 0.8, "路": 1.0, "山路": 1.5}
    assert (cfg.hurry_stamina_per_minute, cfg.dash_stamina_per_minute) == (1, 2)
    assert cfg.travel_minutes_per_unit > 0  # 跟著地圖座標走（第二步重畫地圖時 PM 會改），這裡不寫死


def test_the_tutorial_explains_travel_and_sitting_down(content):
    texts = {step.id: step.text for step in content.tutorial.steps}
    assert all(word in texts["t2_map"] for word in ("步行", "趕路", "疾行", "體力"))
    assert "打坐" in texts["t3_outskirts"]


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


# ── 人物誌：15 位黃巾之亂人物 ─────────────────────────────


FORMER_RECRUITABLE = ["caocao", "liubei", "guanyu", "zhangfei", "sunjian", "yuanshao", "taoqian"]


def test_all_fifteen_historical_figures_are_locked(content):
    """第一季設計第一節：大勢人物這一季都不開放招募。"""
    assert len(content.characters) == 15
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


def test_lu_bei_faction_all_gather_at_zhuo_county(content):
    zhuo_faction = {cid for cid, ch in content.characters.items() if ch.talk_at == "zhuo_county"}
    assert zhuo_faction == {"liubei", "guanyu", "zhangfei"}


# ── 招募（roster.py）跑在真正的內容上 ──────────────────────


def test_nobody_is_recruitable_anywhere(content):
    from tianxia.world_state import WorldStateStore

    world = WorldStateStore(None)  # 讀取用不到磁碟：.read() 找不到檔案時回傳空狀態
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
    from tianxia.world_state import WorldStateStore

    game = Game.new(content, "測試俠客", rng=random.Random(0), world=WorldStateStore(tmp_path / "world.json"))
    msgs = game._deliver_fortune()
    assert any("賀禮" in m for m in msgs)
    assert game.state.player.team == []


# ── 完整跑一季（機器人）──────────────────────────────────


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_bot_plays_a_full_season(content, seed, tmp_path):
    from tianxia.world_state import WorldStateStore

    game = play_season(content, seed, world=WorldStateStore(tmp_path / f"world-{seed}.json"))
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert len(game.state.player.seen_events) >= 3


def test_bot_grows_its_arts_with_xinde(content, tmp_path):
    from tianxia.world_state import WorldStateStore

    game = play_season(content, 1, world=WorldStateStore(tmp_path / "world.json"))
    member = game.state.player.member
    assert member.neigong_level > 1 or member.wugong_level > 1


# ── 戰鬥難度曲線 ──────────────────────────────────────────


def _win_rate(content, squad_id: str, wugong_id: str | None = None, runs: int = 40) -> float:
    wins = 0
    for seed in range(runs):
        game = Game.new(content, "測試俠客", rng=random.Random(seed))
        if wugong_id:
            game.state.player.member.wugong_id = wugong_id
        wins += fight(game.state, content, game.world, squad_id, random.Random(seed)).tier in ("大勝", "險勝")
    return wins / runs


def test_a_freshly_started_hero_with_no_martial_art_cannot_win_any_fight(content):
    """設計文件六.3：威力全靠武學，新手一開局手無寸鐵（沒有任何預設武學）——這跟舊版
    「開局自動配一門長拳」不同，是刻意的設計，練功／招募同伴才是變強的路。"""
    assert _win_rate(content, "dipi") == 0.0


def test_a_hero_with_a_signature_skill_beats_stray_bandits(content):
    wugong_id = next(s.id for s in content.skills.values() if s.kind == "武學")
    assert _win_rate(content, "dipi", wugong_id) >= 0.9


def test_a_hero_with_a_signature_skill_still_cannot_beat_bocai(content):
    wugong_id = next(s.id for s in content.skills.values() if s.kind == "武學")
    assert _win_rate(content, "fanjianglong", wugong_id) <= 0.05


def test_bocai_is_the_hardest_squad_by_difficulty(content):
    assert max(content.squads.values(), key=lambda s: s.difficulty).id == "fanjianglong"


# ── 大地圖 ────────────────────────────────────────────────


TEXT_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"([^>]*)>([^<]*)</text>')
Box = tuple[float, float, float, float]


def _text_boxes(svg: str) -> list[tuple[str, Box]]:
    out = []
    for m in TEXT_RE.finditer(svg):
        x, y, size, text = float(m[1]), float(m[2]), int(m[3]), html.unescape(m[5])
        anchor = re.search(r'text-anchor="(\w+)"', m[4])
        width = text_width(text, size)
        left = x - {"start": 0, "middle": width / 2, "end": width}[anchor[1] if anchor else "start"]
        out.append((text, (left, y - size * 0.85, left + width, y + size * 0.15)))
    return out


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


def test_minimap_never_collides_from_any_location(content):
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    for loc_id in content.locations:
        game.state.player.location = loc_id
        svg = render_minimap(game.state, content)
        assert _collisions(svg, _minimap_window(svg)) == [], loc_id


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


def test_nobody_can_join_a_faction_at_the_start_location(content):
    """伺服器假人設計第八節第 3 項：開局地點不設投靠點，不然所有人一開場就全投了官軍。"""
    start = content.scenario.start_location
    assert all(start not in f.join_at for f in content.scenario.factions)


def test_each_side_of_the_war_wants_the_yellow_turbans_to_go_its_way(content):
    goals = {f.id: f.goals for f in content.scenario.factions}
    assert goals == {"guan": {"huangjin": -1}, "huang": {"huangjin": 1}, "haoqiang": {}}


def test_the_playtest_admin_is_rayal():
    assert load_content(CONTENT_DIR).config.admins == ["Rayal"]

def test_enemy_squads_are_marked_with_the_designers_factions(content):
    factions = {sid: s.faction for sid, s in content.squads.items()}
    assert {sid for sid, f in factions.items() if f == "huang"} == {"louluo", "shuikou", "toumu", "shanzei", "fanjianglong"}
    assert {sid for sid, f in factions.items() if f == "guan"} == {"guishou"}
    assert {sid for sid, f in factions.items() if f == "haoqiang"} == {"xuantie_dizi"}


def test_season_one_tells_the_dialogue_model_when_it_is(content):
    note = content.scenario.era_note
    assert "184" in note and "諸葛亮" in note and "赤壁" in note


def test_every_figure_has_an_audience_threshold(content):
    figures = {cid: ch.audience_fame for cid, ch in content.characters.items() if ch.deep_interaction}
    assert len(figures) == 15 and all(fame > 0 for fame in figures.values())
    assert figures["liubei"] < figures["caocao"] < figures["yuanshao"] < figures["luzhi"] < figures["huangfusong"] < figures["zhangjiao"]


def test_figure_dialogue_runs_on_gemma4_without_thinking_or_repetition_penalties(content):
    """2026-10-03 實測：gemma4:26b 內容最好；重複懲罰會讓它夾英文、關掉思考才不會每輪多等。"""
    cfg = content.config
    assert cfg.ollama_model == "gemma4:26b"
    assert cfg.ollama_think is False
    assert cfg.ollama_repeat_penalty == 1.0 and cfg.ollama_presence_penalty == 0.0 and cfg.ollama_frequency_penalty == 0.0
