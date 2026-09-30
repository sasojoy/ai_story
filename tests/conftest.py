import random
from pathlib import Path

import pytest

from tianxia.content import load_content

FIXTURE = Path(__file__).parent / "fixtures" / "content"


class FixedRandom(random.Random):
    """random() 永遠回傳固定值，讓檢定與機率判定可以預測。"""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.fixture(autouse=True)
def isolated_world_state(tmp_path, monkeypatch):
    """每個測試都用自己的暫存共用世界狀態檔，不會讀寫到真正的 saves/world/state.json，
    測試之間也不會互相汙染（例如武學命名去重、同伴招募狀態）。"""
    from tianxia import world_state

    monkeypatch.setattr(world_state, "DEFAULT_PATH", tmp_path / "world" / "state.json")


@pytest.fixture
def content():
    return load_content(FIXTURE)


@pytest.fixture
def state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "沈浪")


@pytest.fixture
def world():
    from tianxia.world_state import WorldStateStore

    return WorldStateStore()


@pytest.fixture
def game(content):
    from tianxia.engine import Game

    content.config.train_event_chance = 0.0
    content.config.train_stat_chance = 0.0
    return Game.new(content, "沈浪", rng=random.Random(0))
