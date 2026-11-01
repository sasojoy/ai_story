"""擂台的場邊事件（Joy 2026-10-17；tianxia/arena_crowd.py、Config.arena.crowd）：一場最多一件、同一種一天一次、條件是真資料、
效果小、守擂的分身那一邊也算；模型判放手一搏的觀眾反應、重寫場邊那一句（鎖外），寫不出來照固定句。"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from tianxia import arena_crowd
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import MOVES
from tianxia.state import CrowdNote

from test_arena import NOW, _do, _join, ring  # noqa: F401 — ring 是 fixture

LINES = json.loads((Path(__file__).resolve().parents[2] / "content" / "arena_crowd.json").read_text(encoding="utf-8"))


class _Fake:
    timeout = 5.0
    def __init__(self, **values):
        self.values = values

    def chat_structured(self, messages, model, **kw):
        if isinstance(self.values.get("error"), Exception):
            raise self.values["error"]
        return model(**self.values)


@pytest.fixture
def crowd(ring):
    content, world = ring
    content.arena_crowd = LINES
    content.config.arena.crowd.chance = 1.0
    return content, world


def _befriend(content, world, name, who="friend", n=80):
    state = CharacterStore(world.db).load(name)
    state.player.affinities[who] = n
    CharacterStore(world.db).save(state)


def _open(content, world, name="甲", foe="乙"):
    return _do(content, world, name, lambda g: g.choose("act:arena") + g.choose(f"arena:fight:{foe}"))


@pytest.mark.smoke
def test_a_friendly_figure_helps_once_and_says_who(crowd):
    content, world = crowd
    _befriend(content, world, "甲")
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _open(content, world)
    msgs = game.choose(f"arena:{MOVES[0]}")
    helper = content.characters["friend"].name
    fight = game.state.player.arena
    crowd_lines = [line for line in (fight.lines if fight else msgs) if line.startswith(arena_crowd.PREFIX)]
    assert len(crowd_lines) == 1 and helper in crowd_lines[0] and "氣勢 +" in crowd_lines[0]
    assert any(line == crowd_lines[0] for line in msgs)
    assert game.state.player.arena_crowd_seen == {"patron": game._pill_day()}
    while game.state.player.arena is not None:  # 一場最多一件
        msgs = game.choose(f"arena:{MOVES[0]}")
    assert sum(line.startswith(arena_crowd.PREFIX) for line in game.state.player.arena_last.lines) == 1
    assert sum(line.startswith(arena_crowd.PREFIX) for line in game.state.battles[-1].rounds) == 1


def test_the_same_kind_only_once_a_day(crowd):
    content, world = crowd
    content.config.arena.pair_cooldown_seconds = 0
    _befriend(content, world, "甲")
    _join(content, world, "乙")
    _join(content, world, "甲")

    def bout(g):
        g.choose("act:arena")
        g.choose("arena:fight:乙")
        while g.state.player.arena is not None:
            g.choose("arena:yield") if g.state.player.arena.round else g.choose(f"arena:{MOVES[0]}")
        return list(g.state.player.arena_last.lines)

    first, _ = _do(content, world, "甲", bout)
    second, _ = _do(content, world, "甲", bout)
    helper = content.characters["friend"].name
    assert any(line.startswith(arena_crowd.PREFIX) and helper in line for line in first)
    assert not any(line.startswith(arena_crowd.PREFIX) and helper in line for line in second)  # 別種的（乙成了天下第一）照樣可能


def test_nothing_happens_without_anything_true_to_go_on(crowd):
    content, world = crowd
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _open(content, world)
    while game.state.player.arena is not None:
        game.choose(f"arena:{MOVES[1]}")
    assert not any(line.startswith(arena_crowd.PREFIX) for line in game.state.player.arena_last.lines)


def test_the_defenders_proxy_can_be_helped_from_what_he_left_at_signup(crowd):
    content, world = crowd
    _befriend(content, world, "乙")
    _join(content, world, "乙")  # 報名那一刻抄底細
    _join(content, world, "甲")
    assert world.get_season().arena["乙"].crowd.patron == "friend"
    _, game = _open(content, world)
    game.choose(f"arena:{MOVES[0]}")
    lines = game.state.player.arena.lines if game.state.player.arena else game.state.player.arena_last.lines
    line = next(line for line in lines if line.startswith(arena_crowd.PREFIX))
    assert "氣勢 -" in line and content.characters["friend"].name in line
    assert world.get_season().arena["乙"].crowd_seen.get("patron") == game._pill_day()


def test_an_outrageous_gamble_angers_the_crowd(crowd):
    content, world = crowd
    content.config.arena.crowd.outrage_chance = 1.0
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _open(content, world)
    hp = game.state.player.arena.me.hp
    msgs = game.duel_gamble("脫褲子放屁嚇他", 30, ("", ""), crowd="離譜")
    line = next(line for line in msgs if line.startswith(arena_crowd.PREFIX))
    assert "你氣血 -" in line
    fight = game.state.player.arena
    if fight is not None:
        assert fight.me.hp < hp and fight.crowd_done


def test_a_plain_gamble_does_not_trigger_the_outrage(crowd):
    content, world = crowd
    content.config.arena.crowd.outrage_chance = 1.0
    _join(content, world, "乙")
    _join(content, world, "甲")
    _, game = _open(content, world)
    msgs = game.duel_gamble("一拳直取中路", 50, ("", ""), crowd="平常")
    assert not any(line.startswith(arena_crowd.PREFIX) for line in msgs)


def test_effects_stay_small():
    from tianxia.models import ArenaCrowdTuning

    cfg = ArenaCrowdTuning()
    assert max(cfg.edge.values()) <= 5 and max(abs(v) for v in cfg.pool.values()) <= 0.06
    assert 0.15 <= 1 - (1 - cfg.chance) ** 5 <= 0.21  # 預設 chance：五回合打滿約兩成；常提前收場，量到的在 15～20% 之間


def test_the_model_rewrites_the_line_only_for_the_same_note(crowd):
    content, world = crowd
    _befriend(content, world, "甲")
    _join(content, world, "乙")
    _join(content, world, "甲")
    state = CharacterStore(world.db).load("甲")
    game = Game(content, state, random.Random(0), world)
    game.client = _Fake()  # 伺服器：模型叫得到才記單子
    game.sync(NOW)
    game.choose("act:arena")
    game.choose("arena:fight:乙")
    game.choose(f"arena:{MOVES[0]}")
    note = game.arena_crowd_request()
    assert note is not None and note.kind == "patron"
    stale = note.model_copy(update={"round": note.round + 1})
    assert not game.apply_arena_crowd(stale, "亂寫")
    helper = content.characters["friend"].name
    assert game.apply_arena_crowd(note, f"{helper}在台下打了個噴嚏，乙嚇了一跳。")
    lines = game.state.player.arena.lines if game.state.player.arena else game.state.player.arena_last.lines
    assert any(line.startswith(arena_crowd.PREFIX + helper + "在台下打了個噴嚏") and "氣勢 +" in line for line in lines)
    assert game.arena_crowd_request() is None


def test_judge_gamble_only_takes_listed_labels():
    assert arena_crowd.judge_gamble(_Fake(crowd="離譜"), "x", "擂台", "甲") == "離譜"
    assert arena_crowd.judge_gamble(_Fake(crowd="很爛"), "x", "擂台", "甲") == "平常"
    assert arena_crowd.judge_gamble(_Fake(error=RuntimeError()), "x", "擂台", "甲") == "平常"
    assert arena_crowd.judge_gamble(None, "x", "擂台", "甲") == "平常"


def test_write_line_rejects_numbers_and_missing_names():
    note = CrowdNote(fight_id=1, round=0, kind="patron", side="me", name="甲", rival="乙", helper="張飛", fixed="〔場邊〕x", text="x")
    assert arena_crowd.write_line(_Fake(line="張飛彈出一粒花生米，正中乙的鼻樑"), note).startswith("張飛")
    assert arena_crowd.write_line(_Fake(line="張飛彈出三粒花生米加2"), note) == ""
    assert arena_crowd.write_line(_Fake(line="有人彈出花生米"), note) == ""
    assert arena_crowd.write_line(_Fake(line="張飛對你眨眼"), note) == ""
    assert arena_crowd.write_line(_Fake(error=RuntimeError()), note) == ""


def test_content_lines_are_checked(content):
    content.arena_crowd = {"patron": ["{helper}丟了 3 顆花生"]}
    with pytest.raises(ContentError):
        validate(content)
    content.arena_crowd = {"nope": ["x"]}
    with pytest.raises(ContentError):
        validate(content)
    content.arena_crowd = {"patron": ["{who}出手"]}
    with pytest.raises(ContentError):
        validate(content)


def test_real_content_has_every_kind():
    assert set(LINES) == set(arena_crowd.KINDS)
    for kind, lines in LINES.items():
        for text in lines:
            assert text.format(**arena_crowd.SAMPLE)


# ── 伺服器：評分之後另問觀眾反應、場邊那一句在鎖外重寫 ──


def _server_ring(monkeypatch):
    import server
    from tianxia.state import ArenaEntry, CrowdSide

    content = server.CONTENT
    monkeypatch.setattr(content.config.arena.crowd, "chance", 1.0)
    monkeypatch.setattr(content.config.arena.crowd, "outrage_chance", 1.0)
    game = Game.new(content, "測試")
    game.world.open_season(content, 0.0)
    game.client = _Fake()
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.now = 0.0
    w = game.world.get_season()
    w.arena["守者"] = ArenaEntry(name="守者", power=50, hp_cap=300, rank=1, arts=["基礎拳腳"], crowd=CrowdSide())
    game.world.save_season(w)
    game.sync(0.0)
    game.choose("act:arena")
    game.choose("arena:join")
    game.choose("arena:fight:守者")
    assert game.state.player.arena is not None
    open_characters_save(game)
    return server, game


def open_characters_save(game):
    from tianxia.characters import open_characters

    open_characters().save(game.state)


def test_the_server_asks_the_crowd_outside_the_lock_and_rewrites_the_line(monkeypatch):
    from unittest import mock

    from tianxia import battle_instance
    from tianxia.sqlite_world import open_world

    server, game = _server_ring(monkeypatch)
    seen = []

    def judge(client, text, title, name):
        seen.append(("judge", open_world().db.writing(), text))
        return "離譜"

    monkeypatch.setattr(battle_instance, "assess_gamble", lambda *a, **k: battle_instance.GambleVerdict(30, "", ""))
    monkeypatch.setattr(arena_crowd, "judge_gamble", judge)
    with mock.patch("server.time.time", return_value=0.0):
        msgs = server.duel_text(game, "脫鞋丟他")
    assert seen == [("judge", False, "脫鞋丟他")]
    assert any(line.startswith(arena_crowd.PREFIX) and "你氣血 -" in line for line in msgs)
    assert game.arena_crowd_request() is not None and game.arena_crowd_request().kind == "outrage"

    def write(client, note):
        seen.append(("write", open_world().db.writing(), note.kind))
        return "台下一隻破草鞋飛上來，正砸中測試的後腦。"

    monkeypatch.setattr(arena_crowd, "write_line", write)
    assert server.crowd_once(game)
    assert seen[-1] == ("write", False, "outrage")
    fight = game.state.player.arena
    lines = fight.lines if fight is not None else game.state.player.arena_last.lines
    assert any(line.startswith(arena_crowd.PREFIX + "台下一隻破草鞋") and "你氣血 -" in line for line in lines)
    assert not server.crowd_once(game)  # 單子收掉了
