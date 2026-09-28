from collections import deque
from pathlib import Path

from tianxia.content import load_content

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
