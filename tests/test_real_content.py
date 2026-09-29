import html
import random
import re

import pytest
from collections import deque
from pathlib import Path

from tianxia.content import load_content
from tianxia.bot import play_season

CONTENT_DIR = Path(__file__).parent.parent / "content"


def test_real_content_loads():
    c = load_content(CONTENT_DIR)
    assert 20 <= len(c.locations) <= 30
    assert sum(loc.important for loc in c.locations.values()) >= 5
    assert {t.id for t in c.scenario.trends} == {"kou", "bao"}


def test_all_locations_reachable_from_start():
    c = load_content(CONTENT_DIR)
    start = c.scenario.start_location
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in c.locations[queue.popleft()].connections:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(c.locations)


SELF_CHECKS = {
    ("herb", "當場服下"), ("temple_zen", "坐下靜聽"), ("teahouse", "上台和說書先生對幾句"),
    ("train_insight", "靜下心來細想"), ("monk_jinshan", "請教調息之法"), ("waterfall", "躲在石後偷學"),
    ("bao_scholar", "自己拿著殘卷琢磨"),
}


def test_exactly_the_seven_self_checks_are_marked():
    c = load_content(CONTENT_DIR)
    checks = [(e.id, ch.text, ch.check.by) for e in c.events.values() for ch in e.choices if ch.check]
    assert len(checks) == 16
    assert {(eid, text) for eid, text, by in checks if by == "self"} == SELF_CHECKS


def test_real_content_has_enough_events():
    c = load_content(CONTENT_DIR)
    assert len(c.events) >= 30
    assert sum(e.qiyu for e in c.events.values()) >= 3


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_bot_plays_full_season(seed):
    game = play_season(load_content(CONTENT_DIR), seed)
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert len(game.state.player.seen_events) >= 5


def test_bot_grows_its_arts_with_xinde():
    game = play_season(load_content(CONTENT_DIR), 1)
    p = game.state.player
    levels = list(p.skills.values()) + [m.innate_level for key, m in p.members.items() if key != "player"]
    assert max(levels) > 1


def test_fresh_team_facing_heixiong_shows_hard_to_tell():
    """新手隊初期打不動黑熊（防禦高），模擬大多是平手：該顯示「難分勝負」而非「必敗」。"""
    from tianxia.engine import Game

    game = Game.new(load_content(CONTENT_DIR), "測試俠客", rng=random.Random(0))
    assert game.odds("heixiong") == "難分勝負"


def test_treasure_storyline_can_be_lost_to_fanjianglong():
    from tianxia.engine import Game
    from tianxia.world import check_thresholds

    game = Game.new(load_content(CONTENT_DIR), "測試俠客", rng=random.Random(0))
    w = game.state.world
    w.revealed.add("bao")
    w.trends["bao"] = 100
    check_thresholds(game.state, game.content)
    assert w.storyline == "bao_line" and "cave_open" in w.flags
    game.advance(49 * 3600)
    assert "treasure_lost" in w.flags


def test_bao_line_advances_to_aftermath_act_after_treasure_taken():
    from tianxia.engine import Game
    from tianxia.world import check_thresholds, current_act

    content = load_content(CONTENT_DIR)
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    w = game.state.world
    w.storyline = "bao_line"
    w.act = 2  # bao_3「藏龍洞」
    w.flags.add("treasure_taken")
    check_thresholds(game.state, content)
    assert current_act(game.state, content).id == "bao_4"


def test_peace_treasure_ending_reachable_on_bao_line():
    from tianxia.engine import Game
    from tianxia.world import evaluate_ending

    content = load_content(CONTENT_DIR)
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    w = game.state.world
    w.storyline = "bao_line"
    w.flags.update({"kou_crushed", "treasure_taken"})
    assert evaluate_ending(game.state, content).id == "peace_treasure"


def test_peace_ending_on_kou_line_with_only_kou_crushed():
    from tianxia.engine import Game
    from tianxia.world import evaluate_ending

    content = load_content(CONTENT_DIR)
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    w = game.state.world
    w.storyline = "kou_line"
    w.flags.add("kou_crushed")
    assert evaluate_ending(game.state, content).id == "peace"


def test_starting_team_odds_on_real_content():
    from tianxia.engine import Game

    game = Game.new(load_content(CONTENT_DIR), "測試俠客", rng=random.Random(0))
    assert game.odds("dipi") == "穩勝"
    assert game.odds("fanjianglong") == "必敗"
    game.state.player.location = "yangzhou_jiao"
    assert game.options()[0].label == "歷練（體力 10・可能遇到：地痞無賴 穩勝、劫道山賊 穩勝）"


REGIONS = {
    "jiangbei": {"yangzhou", "shouxihu", "yangzhou_jiao", "gaoyou", "guazhou"},
    "jinling_area": {"jinshan", "jiangning_road", "jinling", "qinhuai", "yuhuatai", "qixia_sect", "qixia_foot", "qixia_back", "canglong"},
    "taihu_area": {"zhenjiang", "changzhou", "wuxi", "xuantie", "taihu_north", "taihu_isle", "suzhou", "hanshan"},
}


def test_real_regions_trends_and_membership():
    from tianxia.atlas import region_of

    c = load_content(CONTENT_DIR)
    assert {r.id: r.trends for r in c.map.regions} == {
        "jiangbei": ["kou"], "jinling_area": ["bao"], "taihu_area": ["kou"],
    }
    members: dict[str, set[str]] = {}
    for loc_id in c.locations:
        members.setdefault(region_of(c, loc_id).id, set()).add(loc_id)
    assert members == REGIONS  # 棲霞劍派移到 (55, 188)，和棲霞山腳同屬金陵一帶


def test_real_region_neighbours_point_the_right_way():
    from tianxia.atlas import neighbours
    from tianxia.state import new_game_state

    c = load_content(CONTENT_DIR)
    state = new_game_state(c, "測試俠客")
    regions = {r.id: r for r in c.map.regions}
    found = {rid: [(arrow, other.name) for arrow, other in neighbours(state, c, r)] for rid, r in regions.items()}
    assert found == {
        "jiangbei": [("↘", "太湖一帶")],  # 棲霞劍派移到江南後，江北只經瓜洲渡—鎮江渡口連到太湖一帶
        "jinling_area": [("→", "太湖一帶")],
        "taihu_area": [("↖", "江北"), ("←", "金陵一帶")],
    }


def test_travel_on_real_content_matches_the_design_examples():
    from tianxia.engine import Game

    game = Game.new(load_content(CONTENT_DIR), "測試俠客", rng=random.Random(0))
    p = game.state.player
    p.tutorial_step = 2  # 下一步是「出城往揚州城郊走走」
    game.travel("gaoyou")
    assert game.state.journal[0].title == "前往 高郵湖（途經 揚州城郊）"
    assert p.location == "gaoyou" and p.stamina == 140 and p.tutorial_step == 3

    p.location = "yangzhou"
    p.visited |= {"guazhou", "zhenjiang", "changzhou", "wuxi", "taihu_north", "taihu_isle"}
    p.stamina = 10
    game.travel("taihu_isle")
    assert game.state.journal[0].title == "前往 太湖水寨（體力不足，停在 鎮江渡口）"
    assert p.location == "zhenjiang" and p.stamina == 0


def test_enemies_layer_on_real_content_simulates_once_per_foe(monkeypatch):
    from tianxia import team
    from tianxia.engine import Game

    game = Game.new(load_content(CONTENT_DIR), "測試俠客", rng=random.Random(0))
    calls = []
    real = team.run_battle
    monkeypatch.setattr(team, "run_battle", lambda *args: calls.append(1) or real(*args))
    for layer in ("situation", "story", "routes"):
        game.world_map_svg(layer, "gaoyou")
    game.minimap_svg()
    assert calls == []  # 平常重畫不模擬
    svg = game.world_map_svg("enemies")
    assert len(calls) == 4 * 40  # 開局摸清的地點有 4 種對手：地痞、山賊、嘍囉、水寇
    assert "最險：水寇嘍囉 穩勝" in svg
    game.world_map_svg("enemies", "gaoyou")
    assert len(calls) == 160  # 已快取


def test_map_guide_step_points_to_the_world_map():
    c = load_content(CONTENT_DIR)
    step = c.tutorial.steps[1]
    assert step.id == "t2_map" and "「大地圖」" in step.text and "分頁" not in step.text
    assert step.done_when.condition.flags_all == ["看過地圖"]  # Game.view_map()：打開大地圖就算完成


def test_real_content_places_are_filled_in():
    c = load_content(CONTENT_DIR)
    s = c.scenario
    assert all(sim.haunts for sim in s.sim_players)
    assert all(act.places for line in s.storylines for act in line.acts)
    assert all(th.location for th in s.thresholds) and all(e.location for e in s.world_events)


def test_legend_strip_does_not_cover_locations():
    c = load_content(CONTENT_DIR)
    assert max(loc.y for loc in c.locations.values()) + 12 < c.map.height - 50


# ── 大地圖與小地圖不疊字 ─────────────────────────────

TEXT_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="(\d+)"([^>]*)>([^<]*)</text>')
Box = tuple[float, float, float, float]  # 左、上、右、下


def _text_boxes(svg: str) -> list[tuple[str, Box]]:
    """SVG 裡每段文字大約佔的範圍：寬用 text_width 估，高就是字級（基線以上 0.85、以下 0.15）。"""
    from tianxia.mapview import text_width

    out = []
    for m in TEXT_RE.finditer(svg):
        x, y, size, text = float(m[1]), float(m[2]), int(m[3]), html.unescape(m[5])
        anchor = re.search(r'text-anchor="(\w+)"', m[4])
        width = text_width(text, size)
        left = x - {"start": 0, "middle": width / 2, "end": width}[anchor[1] if anchor else "start"]
        out.append((text, (left, y - size * 0.85, left + width, y + size * 0.15)))
    return out


def _mark_boxes(svg: str, bottom: float) -> list[tuple[str, Box]]:
    """大地圖上地點記號的範圍（方塊、菱形、圓點，含外圈與所在地、選定的圓圈）；bottom 以下的圖例不算。"""
    out = []
    for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="3"([^>]*)>', svg):
        x, y, w, h = map(float, m.groups()[:4])
        pad = 1.5 if "stroke=" in m[5] else 0
        out.append((f"記號({x + w / 2:g},{y + h / 2:g})", (x - pad, y - pad, x + w + pad, y + h + pad)))
    for m in re.finditer(r'<path d="M([-\d.]+) ([-\d.]+) L([-\d.]+) [-\d.]+ L[^"]*"([^>]*)>', svg):
        x, top, right = float(m[1]), float(m[2]), float(m[3])
        s = right - x + (1.5 if "stroke=" in m[4] else 0)
        out.append((f"記號({x:g},{top + right - x:g})", (x - s, top + right - x - s, x + s, top + right - x + s)))
    for m in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([\d.]+)" fill="([^"]+)"([^>]*)>', svg):
        cx, cy, r = float(m[1]), float(m[2]), float(m[3])
        if m[4] == "#000000" or cy > bottom:  # 透明的可點範圍、圖例
            continue
        stroke = re.search(r'stroke-width="([\d.]+)"', m[5])
        r += float(stroke[1]) / 2 if stroke else 0
        out.append((f"記號({cx:g},{cy:g})", (cx - r, cy - r, cx + r, cy + r)))
    return out


def _overlaps(a: Box, b: Box, allow: float = 1.0) -> bool:
    return a[0] < b[2] - allow and b[0] < a[2] - allow and a[1] < b[3] - allow and b[1] < a[3] - allow


def _collisions(svg: str, width: float, height: float, marks: list[tuple[str, Box]] = ()) -> list[str]:
    """疊在一起的文字、壓到地點記號的文字、超出畫布的文字（容許 1 px）。"""
    texts = _text_boxes(svg)
    found = [f"{a}×{b}" for i, (a, box_a) in enumerate(texts) for b, box_b in texts[i + 1:] if _overlaps(box_a, box_b)]
    found += [f"{a}×{b}" for a, box_a in texts for b, box_b in marks if _overlaps(box_a, box_b)]
    found += [f"{a} 出界" for a, (left, top, right, bottom) in texts if left < -1 or top < -1 or right > width + 1 or bottom > height + 1]
    return found


def _map_game(everything: bool, bao: bool = False, cave: bool = True):
    """everything：每個地點都去過、每個地點都有最近的傳聞；bao：寶藏線浮現、進入寶藏主線；cave：藏龍洞開放。"""
    from tianxia.engine import Game
    from tianxia.state import Rumor

    c = load_content(CONTENT_DIR)
    game = Game.new(c, "測試俠客", rng=random.Random(0))
    s = game.state
    if cave:
        s.world.flags.add("cave_open")
    if bao:
        s.world.revealed.add("bao")
        s.world.trends["bao"] = 60
        s.world.storyline, s.world.act = "bao_line", 1
    if everything:
        s.player.visited = set(c.locations)
        s.world.rumors += [Rumor(time=s.world.time, text="傳聞", location=loc_id) for loc_id in c.locations]
    return game


def _widest_odds(squad_id: str) -> str:
    return "難分勝負"  # 最長的勝算詞


def _map_collisions(game, layer: str, selected: str | None = None, marks: bool = True) -> list[str]:
    """大地圖上疊在一起、出界的文字；marks 時連壓到地點記號的文字也算。"""
    from tianxia.mapview import render_map

    m = game.content.map
    svg = render_map(game.state, game.content, layer, selected, _widest_odds if layer == "enemies" else None)
    return _collisions(svg, m.width, m.height, _mark_boxes(svg, m.height - 50) if marks else [])


@pytest.mark.parametrize("layer", ["situation", "enemies", "story", "routes"])
def test_world_map_labels_never_collide_at_the_start(layer):
    game = _map_game(everything=False, cave=False)
    for selected in [None, *(loc_id for _, loc_id in game.map_places())]:
        assert _map_collisions(game, layer, selected) == [], selected


# 棲霞山腳、棲霞後山、棲霞劍派、藏龍洞、金陵城擠在一起：其中棲霞山腳或棲霞後山畫上大圓圈（所在地或選定）時，
# 棲霞後山的名字連同底下的小字找不到完全空著的地方，只能壓到旁邊的地點記號（文字仍然不疊）。
CROWDED = {"qixia_foot", "qixia_back"}


@pytest.mark.parametrize("layer", ["situation", "enemies", "story", "routes"])
@pytest.mark.parametrize("bao", [False, True])
def test_world_map_labels_never_collide_with_everything_known(layer, bao):
    game = _map_game(everything=True, bao=bao)
    for loc_id in game.content.locations:
        assert _map_collisions(game, layer, loc_id, marks=loc_id not in CROWDED) == [], f"選 {loc_id}"
    for loc_id in game.content.locations:
        game.state.player.location = loc_id
        assert _map_collisions(game, layer, marks=loc_id not in CROWDED) == [], f"在 {loc_id}"


def _win_rate(squad_id: str, runs: int = 40) -> float:
    from tianxia.engine import Game
    from tianxia.team import fight

    content = load_content(CONTENT_DIR)
    wins = 0
    for seed in range(runs):
        game = Game.new(content, "測試俠客", rng=random.Random(seed))
        wins += fight(game.state, content, squad_id, random.Random(seed)).outcome == "win"
    return wins / runs


def test_starting_team_beats_street_thugs():
    assert _win_rate("dipi") >= 0.8


def test_starting_team_cannot_beat_fanjianglong():
    assert _win_rate("fanjianglong") <= 0.1


def _trained_win_rate(squad_id: str, level: int, skill_level: int, runs: int = 40) -> float:
    """新開一局，全隊練到 level 級、所有武學（本人武學、本人本命、同伴本命）練到第 skill_level 成；
    每場開打前回滿內力，讓每一場互不影響。"""
    from tianxia.engine import Game
    from tianxia.team import fight

    content = load_content(CONTENT_DIR)
    game = Game.new(content, "測試俠客", rng=random.Random(0))
    p = game.state.player
    for member in p.members.values():
        member.level = level
        member.innate_level = skill_level
    for skill_id in p.skills:
        p.skills[skill_id] = skill_level
    wins = 0
    for seed in range(runs):
        for member in p.members.values():
            member.neili = None
        wins += fight(game.state, content, squad_id, random.Random(seed)).outcome == "win"
    return wins / runs


def test_tomb_guardian_gates_the_treasure_within_a_season():
    """藏龍洞守墓人：剛出道的隊伍打不過，練到 10 級、武學第五成就有一戰之力（寶藏主線才走得完）。"""
    assert _trained_win_rate("shoumu", level=1, skill_level=1) <= 0.1
    assert _trained_win_rate("shoumu", level=10, skill_level=5) >= 0.5
