"""親衛隊長第四批（Joy 2026-11-10「全部做完一起上」）：別人看得見他。下一季起酒肆不招（hire 包的測試守）、你在決戰裡倒下他說一句、
截殺時他在一旁、名帖上那一行、寫進列傳。測試內容、開關打開、沒有模型。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from tianxia.core import guard_base
from tianxia.features.guard import actions, texts


@pytest.fixture
def sworn(game):
    t = game.content.config.guard
    t.enabled = True
    game.content.config.biography.enabled = True
    game.state.player.member.level = t.meet_level
    game.client = None
    game.sync(game.now)
    actions.meet_on_explore(game, game.state.player.location)
    for oid in ("guard:save", "guard:adopt:男"):
        game.choose(oid)
    game.state.player.guard.phase = 3
    game.state.player.stats["silver"] = 500
    game.choose("guard:study")
    game.choose("guard:school:gensui")
    b = game.state.player.guard
    b.letters = t.letters
    game.sync(b.study_until + 1)
    for _ in range(2):
        game.choose("guard:open")
        game.choose("guard:pick:0")
    assert b.stage == "sworn"
    return game


def test_adopting_and_swearing_go_into_the_annals(sworn):
    b = sworn.state.player.guard
    texts_ = [a.text for a in sworn.state.player.annals]
    assert any("收養" in x and b.name in x for x in texts_)
    assert any("親衛隊長" in x and b.title in x for x in texts_)


def test_the_card_shows_him(sworn):
    b = sworn.state.player.guard
    assert guard_base.card_line(sworn.state, sworn.content) == f"親衛隊長{b.name}（{b.path}）"
    sworn.content.config.guard.enabled = False
    assert guard_base.card_line(sworn.state, sworn.content) == ""


def test_raid_lines_follow_the_band_and_show_the_rivals_guard(sworn):
    b = sworn.state.player.guard
    b.qing = 15
    s, c = sworn.state, sworn.content
    lost = guard_base.raid_lines(s, c, None, "lost")
    assert lost == [guard_base.RAID_OWN["lost"]["恩深"].replace("{name}", b.name).replace("{pron}", "他")]
    b.along = False
    assert guard_base.raid_lines(s, c, None, "won") == []
    # 對手帶著他的時候，截殺的人也看得到
    rival = s.model_copy(deep=True)
    rival.player.guard.along = True
    rival.player.name = "乙"
    seen = guard_base.raid_lines(s, c, rival, "even")
    assert seen == [f"乙身邊跟著親衛隊長{b.name}（{b.path}），一路盯著你。"]


def test_he_speaks_once_when_you_fall_in_the_battle(sworn, monkeypatch):
    b = sworn.state.player.guard
    me = SimpleNamespace(eliminated=False)
    battle = SimpleNamespace(battle_id="huangjin", record_id=7, participants={sworn.state.player.name: me})
    monkeypatch.setattr(type(sworn), "_battle_now", lambda self: battle)
    assert actions._fell(sworn, b) == []
    me.eliminated = True
    said = actions._fell(sworn, b)
    assert len(said) == 1 and b.name in said[0]
    assert any(said[0] == line.replace("{name}", b.name) for pool in texts.FELL_LINES.values() for line in pool)
    assert actions._fell(sworn, b) == []  # 同一場只說一次
    battle.record_id = 8
    assert len(actions._fell(sworn, b)) == 1


def test_the_player_card_carries_the_line(sworn):
    from tianxia.features.peers import mingtie, social

    b = sworn.state.player.guard
    line = f"親衛隊長{b.name}（{b.path}）"
    assert social.card(sworn, sworn)["guard"] == line
    assert line in mingtie.earned(sworn.state, sworn.content)
    sworn.state.player.guard.stage = "grow"
    assert "guard" not in social.card(sworn, sworn)
