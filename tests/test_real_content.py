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


@pytest.fixture(autouse=True)
def no_real_ollama():
    with mock.patch.object(OllamaClient, "chat_structured", _fake_chat_structured):
        yield


@pytest.fixture(scope="module")
def content():
    return load_content(CONTENT_DIR)


# ── 內容結構完整性 ────────────────────────────────────────


def test_real_content_loads():
    c = load_content(CONTENT_DIR)
    assert 20 <= len(c.locations) <= 30
    assert {t.id for t in c.scenario.trends} == {"huangjin", "yuxi"}


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


def test_fifteen_historical_figures_split_locked_and_recruitable(content):
    locked = [ch for ch in content.characters.values() if ch.kind == "locked"]
    recruitable = [ch for ch in content.characters.values() if ch.kind == "recruitable"]
    assert len(content.characters) == 15
    assert len(locked) == 8 and len(recruitable) == 7


def test_only_recruitable_figures_have_a_recruit_location(content):
    for ch in content.characters.values():
        if ch.kind == "recruitable":
            assert ch.recruit_at in content.locations, ch.id
        else:
            assert ch.recruit_at is None, ch.id


def test_recruitable_figures_have_their_own_signature_skills(content):
    for ch in content.characters.values():
        if ch.kind != "recruitable":
            continue
        assert ch.starting_wugong in content.skills, ch.id
        assert ch.starting_neigong in content.skills, ch.id


def test_every_figure_opts_into_deep_dialogue(content):
    """設計文件四.3：這一期黃巾之亂人物全部開放深度 LLM 對話（鎖定的龍頭人物也一樣，
    只是還沒有 recruit_at 讓玩家在地圖上找到他們，見 engine.py::_deep_interaction_target）。"""
    assert all(ch.deep_interaction for ch in content.characters.values())


def test_lu_bei_faction_all_gather_at_zhuo_county(content):
    zhuo_faction = {cid for cid, ch in content.characters.items() if ch.recruit_at == "zhuo_county"}
    assert zhuo_faction == {"liubei", "guanyu", "zhangfei"}


# ── 招募（roster.py）跑在真正的內容上 ──────────────────────


def test_recruitable_here_matches_each_figures_own_location(content):
    from tianxia.world_state import WorldStateStore

    world = WorldStateStore(None)  # 讀取用不到磁碟：.read() 找不到檔案時回傳空狀態
    assert roster.recruitable_here(content, world, "zhuo_county") == ["liubei", "guanyu", "zhangfei"]
    assert roster.recruitable_here(content, world, "qiao_county") == ["caocao"]
    assert roster.recruitable_here(content, world, "yingchuan") == []  # 開局地點沒有人可招


def test_attempt_recruit_seeds_the_real_signature_skills(content, world):
    from tianxia.state import new_game_state

    state = new_game_state(content, "測試俠客")
    msgs = roster.attempt_recruit(state, content, world, "caocao", random.Random(0))
    assert msgs
    progress = world.get_companion("caocao")
    if progress.owner == "測試俠客":
        assert progress.wugong_id == "caocao_wugong" and progress.neigong_id == "caocao_neigong"


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
