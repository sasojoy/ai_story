"""第一季正式版・甲：叛投（計畫 2026-10-06-第一季正式版-甲-叛投）。

用真實內容（content/）：投靠點、門派歸屬、頭銜都照真的；開關在測試裡才打開。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.state import PlayerState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None):
    game = Game.new(content, name, rng=random.Random(0))
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def test_new_fields_have_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.defected, p.pending_defect) == (False, None)
    assert FactionDef(id="x", name="X").defect_text == ""


def test_real_factions_have_defect_text(real):
    # 三句是新寫的初稿，待 joy 潤（content/scenario.json 是 JSON、FactionDef 不收多的欄位，所以標記記在這裡與 models.py）
    texts = {f.id: f.defect_text for f in real.scenario.factions}
    assert set(texts) == {"guan", "huang", "haoqiang"} and all(texts.values())


def test_defect_text_must_be_traditional(real):
    real.scenario.factions[0].defect_text = "过去的事不问"
    with pytest.raises(ContentError, match="defect_text"):
        validate(real)
