import random

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


def test_real_content_places_are_filled_in():
    c = load_content(CONTENT_DIR)
    s = c.scenario
    assert all(sim.haunts for sim in s.sim_players)
    assert all(act.places for line in s.storylines for act in line.acts)
    assert all(th.location for th in s.thresholds) and all(e.location for e in s.world_events)


def test_legend_strip_does_not_cover_locations():
    c = load_content(CONTENT_DIR)
    assert max(loc.y for loc in c.locations.values()) + 12 < c.map.height - 50


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
