"""參透秘方看得出來（玩家回報 2026-10-25「刷很多事件，但是武學譜很空」）：參透當下多一句這一季的進度、另寫一則「武學譜」
江湖紀錄、伺服器回一個視窗（Game.secret_solved）；武學譜入口的分母是這一季全服共有的；照著合第二次不再算。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from test_secret_recipes import FUSE, MERGE
from tianxia import journal, secret_recipes
from tianxia.engine import Game


@pytest.fixture
def game(content, world):
    content.secret_recipes = [FUSE, MERGE]
    content.config.auto_open_first_season = True
    g = Game.new(content, "甲", rng=random.Random(0), world=world)
    g.client = None
    g.sync(1000.0)
    p = g.state.player
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng", "huo", "shan", "shui"]
    p.stats["xinde"] = 1000
    p.stamina = 100
    return g


def test_solving_a_merge_secret_tells_the_progress_writes_a_manual_entry_and_pops_up(game, content):
    assert game.status_data()["manual_total"] == 2  # 分母：這一季全服共有的，還沒聽過也算
    msgs = game.forge(None, ["shan", "shui"], proposed=(None, ""))
    note = content.config.secrets.solved_note.format(n=1, total=2)
    assert content.config.secrets.hit_line in msgs and note in msgs
    card = game.secret_solved
    assert card["name"] == "山環水抱" and (card["solved"], card["total"]) == (1, 2)
    assert card["title"] == content.config.secrets.solved_title.format(n=1, total=2) and card["note"] == note
    entry = next(e for e in reversed(game.state.journal) if e.title == journal.MANUAL)
    assert "山環水抱" in entry.tag and note in entry.lines
    # 照著合第二次：不是新參透，不跳視窗、不再寫進度、不再記一則
    count = sum(e.title == journal.MANUAL for e in game.state.journal)
    game.state.player.insights += ["shan", "shui"]
    again = game.forge(None, ["shan", "shui"], proposed=(None, ""))
    assert game.secret_solved is None and not any("參透" in m and "／" in m for m in again)
    assert sum(e.title == journal.MANUAL for e in game.state.journal) == count


def test_filling_slots_into_a_set_secret_pops_up_too(game, content):
    game.slot_insight("basic_fist", "shan")
    assert game.secret_solved is None
    msgs = game.slot_insight("basic_fist", "feng")
    assert game.secret_solved["name"] == "鎮岳指" and game.secret_solved["solved"] == 1
    assert content.config.secrets.solved_note.format(n=1, total=2) in msgs
    assert any(e.title == journal.MANUAL for e in game.state.journal)


def test_progress_only_counts_this_seasons_batch(game, content):
    game.state.player.manual.solved = ["t_merge", "gone_last_season"]
    assert secret_recipes.progress(game.state, content, game.world) == (1, 2)
    game.state.player.manual.tianji += 1  # 別一季的譜：這一季一條都還沒參透
    assert secret_recipes.progress(game.state, content, game.world)[0] == 0


def test_raising_per_season_keeps_the_ones_already_picked():
    """正式內容一季各 4 條（Joy 2026-10-25）：加大之後原本那一批還在裡面（同一個天機照同一個順序挑），已經參透的不會被換掉。"""
    content = real_content()
    assert content.config.secrets.per_season == {"fuse": 4, "merge": 4}
    for tianji in range(8):
        now = {r.id for r in secret_recipes.active(content, tianji)}
        content.config.secrets.per_season = {"fuse": 2, "merge": 2}
        before = {r.id for r in secret_recipes.active(content, tianji)}
        content.config.secrets.per_season = {"fuse": 4, "merge": 4}
        assert len(now) == 8 and before <= now
