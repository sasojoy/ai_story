"""重悟帖的第二個用法「重讀這句意」（Joy 2026-10-22「立意那邊好像也要可以重骰」，PM 定的做法）：成了形之後，同一句意（或改寫過的）
請模型再讀一次，換掉意分、火候、屬性與正邪，照新的讀法重擲成形；跟重骰形共用 create_reroll_cap、各用掉一張帖，不另收心得；
模型叫不動（None）什麼都不改、不扣帖。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import create
from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def content():
    c = load_content(ROOT / "tests" / "fixtures" / "content")
    c.config.auto_open_first_season = True
    return c


def _formed(content, score=40, attrs=("快",)):
    game = Game.new(content, "重讀人", rng=random.Random(3))
    game.world.open_season(content, now=0.0)
    game.state.player.stats["xinde"] = 5000
    assert game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(content, "起手"))
    game.create_intent("風過林梢，影不留痕", reading=create.IntentReading(score=score, attributes=list(attrs)))
    return game


def test_rereading_takes_a_slip_and_changes_the_reading_and_the_form(content):
    game = _formed(content)
    p = game.state.player
    p.create_rerolls = 2
    xinde, redo, rolls = p.stats["xinde"], p.creating.redo, p.creating.rolls
    req = game.create_reread_request("風過林梢，影不留痕")
    assert isinstance(req, create.IntentRequest) and req.text == "風過林梢，影不留痕"
    msgs = game.create_reread("山嶽不動，一拳開碑", create.IntentReading(score=80, attributes=["剛", "實"], lean="正"))
    assert "重新體會" in msgs[0] and msgs[-1].startswith("重悟帖 -1")
    d = p.creating
    assert d.intent == "山嶽不動，一拳開碑" and d.score == 80 and d.read == ["剛", "實"] and d.lean == "正"
    assert d.step == "name" and d.colors and d.rolls == rolls + 1 and d.rerolled == 1
    assert p.create_rerolls == 1 and p.stats["xinde"] == xinde and d.redo == redo  # 不收心得、不用掉免費的重來
    assert create.view(game.state, content, game.world)["draft"]["fire"] == create.fire_of_draft(game.state, content, d)


def test_no_reading_changes_nothing_and_keeps_the_slip(content):
    game = _formed(content)
    p = game.state.player
    p.create_rerolls = 1
    before = p.creating.model_copy(deep=True)
    assert game.create_reread("風過林梢，影不留痕", None) == [create.REREAD_FAILED]
    assert p.create_rerolls == 1 and p.creating == before


def test_rereading_shares_the_cap_with_rerolling(content):
    game = _formed(content)
    p = game.state.player
    cap = content.config.arts.create_reroll_cap
    p.create_rerolls = cap + 2
    for i in range(cap):
        if i % 2:
            game.create_reroll()
        else:
            game.create_reread("風過林梢，影不留痕", create.IntentReading(score=50 + i, attributes=["快"]))
    capped = [create.REROLL_CAPPED.format(cap=cap)]
    assert game.create_reread("風過林梢，影不留痕", create.IntentReading(score=99)) == capped
    assert game.create_reread_request("風過林梢，影不留痕") == capped
    assert game.create_reroll() == capped and p.create_rerolls == 2


def test_rereading_needs_a_formed_draft_a_slip_and_a_proper_line(content):
    game = Game.new(content, "未立人", rng=random.Random(3))
    game.world.open_season(content, now=0.0)
    assert game.create_reread_request("風過林梢") == [create.NO_DRAFT]
    game.state.player.stats["xinde"] = 5000
    assert game.create_begin("武學", "拳腳")
    assert game.create_reread_request("風過林梢") == [create.REROLL_STEP]
    game = _formed(content)
    assert game.create_reread_request("風過林梢") == [create.NO_REROLL]
    game.state.player.create_rerolls = 1
    assert game.create_reread_request("風") == [create.INTENT_LINE]
    assert game.create_reread("風", create.IntentReading(score=90)) == [create.INTENT_LINE] and game.state.player.create_rerolls == 1


def test_the_server_without_a_model_keeps_the_slip(content, monkeypatch):
    import server

    game = _formed(content)
    game.client = None
    game.state.player.create_rerolls = 1
    monkeypatch.setattr(server, "act", lambda g, fn, **kw: fn(g))
    monkeypatch.setattr(server, "_open_request", lambda g, open_it: (0.0, open_it()))
    assert server.create_reread(game, {"text": "風過林梢，影不留痕"}) == [create.REREAD_FAILED]
    assert game.state.player.create_rerolls == 1


def test_a_reading_is_none_when_the_model_cannot_be_called(content):
    req = create.IntentRequest("武學", "拳腳", "此式平正", "風過林梢", "某")
    assert create.read_or_none(None, req) is None

    class Broken:
        def chat_structured(self, *a, **k):
            raise RuntimeError("down")

    assert create.read_or_none(Broken(), req) is None
