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


def test_others_hear_of_him_only_the_path_and_the_deed(sworn):
    """收尾（Joy 2026-11-25）：酒肆打聽交情聽得到他的傳聞（出路與撿到他的那一件事，不講心性）；留在家、還沒投效、開關關著都聽不到。"""
    from tianxia.features.tavern import rules as tavern_rules

    s, c, b = sworn.state, sworn.content, sworn.state.player.guard
    line = guard_base.rumor_line(s, c)
    assert line.startswith(f"聽說{s.player.name}身邊那個{guard_base.PATH_WORD[b.path]}{b.name}，是")
    assert all(word not in line for word in ("恩深", "敬重", "淡然", "怨懟", "恨極"))
    b.opening = "spy"
    b.sex = "女"
    assert "要打死她的村人" in guard_base.rumor_line(s, c)
    b.opening = "nope"
    assert "撿回來的孩子" in guard_base.rumor_line(s, c)
    # 接在酒肆打聽交情（打聽度 3 以上）
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(tavern_rules, "person_reach", lambda *a, **k: 3)
        lines, found = tavern_rules.ties_player_lines(s, c, s, [])
        assert found and guard_base.rumor_line(s, c) in lines
        monkey.setattr(tavern_rules, "person_reach", lambda *a, **k: 2)
        assert guard_base.rumor_line(s, c) not in tavern_rules.ties_player_lines(s, c, s, [])[0]
    finally:
        monkey.undo()
    b.along = False
    assert guard_base.rumor_line(s, c) == ""
    b.along, b.stage = True, "grow"
    assert guard_base.rumor_line(s, c) == ""
    b.stage = "sworn"
    c.config.guard.enabled = False
    assert guard_base.rumor_line(s, c) == ""


def test_at_a_spar_or_a_discussion_the_rivals_guard_says_a_line_by_his_band(sworn):
    s, c, b = sworn.state, sworn.content, sworn.state.player.guard
    owner = s.player.name
    for qing, mood in ((15, "warm"), (0, "plain"), (-15, "cold")):
        b.qing = qing
        assert guard_base._mood(c, b) == mood
        for outcome in ("won", "lost", "even"):
            assert guard_base.spar_line(s, c, outcome) == guard_base.SPAR_RIVAL[outcome][mood].format(owner=owner, gname=b.name)
        assert guard_base.discuss_line(s, c) == guard_base.DISCUSS_RIVAL[mood].format(owner=owner, gname=b.name)
    b.along = False
    assert guard_base.spar_line(s, c, "won") == "" == guard_base.discuss_line(s, c)
