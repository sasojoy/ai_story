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


def test_legend_strip_does_not_cover_locations():
    c = load_content(CONTENT_DIR)
    assert max(loc.y for loc in c.locations.values()) + 12 < c.map.height - 50
