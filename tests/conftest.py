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


@pytest.fixture
def content():
    return load_content(FIXTURE)


@pytest.fixture
def state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "沈浪")


@pytest.fixture
def game(content):
    from tianxia.engine import Game

    content.config.train_event_chance = 0.0
    content.config.train_stat_chance = 0.0
    return Game.new(content, "沈浪", rng=random.Random(0))
