"""親衛隊長（features/guard）第二批：求學、出師、投效。測試內容、開關打開；模型用假的 client。"""
from __future__ import annotations

import pytest

from tianxia.features.guard import actions, bots, rules, texts
from tianxia.core.option import Option


@pytest.fixture
def grown(game):
    """收養了、到了求學的等級、手上有錢，沒有模型。"""
    t = game.content.config.guard
    t.enabled = True
    game.state.player.member.level = t.meet_level
    game.client = None
    game.sync(game.now)
    actions.meet_on_explore(game, game.state.player.location)
    game.choose("guard:save")
    game.choose("guard:adopt:女")
    game.state.player.member.level = t.study_level
    game.state.player.stats["silver"] = 500
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def chat_structured(self, messages, model, **kw):
        return model.model_validate(self.reply)


def _to_school(game, key="shuyuan"):
    game.choose("guard:study")
    return game.choose(f"guard:school:{key}")


def test_study_shows_up_at_the_study_level_and_not_before(grown):
    b = grown.state.player.guard
    assert actions.status(grown)["guard"]["can_study"]
    grown.state.player.member.level = grown.content.config.guard.study_level - 1
    assert not actions.status(grown)["guard"]["can_study"]
    assert b.stage == "grow"


def test_picking_a_school_costs_silver_and_pushes_the_tags(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    grown.choose("guard:study")
    menu = {o["id"]: o for o in actions.status(grown)["guard"]["schools"]}
    assert set(menu) == {f"guard:school:{k}" for k in texts.SCHOOLS}
    grown.state.player.stats["silver"] = 120
    menu = {o["id"]: o for o in actions.status(grown)["guard"]["schools"]}
    assert not menu["guard:school:shuyuan"]["enabled"] and menu["guard:school:junying"]["enabled"] and menu["guard:school:gensui"]["enabled"]
    grown.state.player.stats["silver"] = 500
    before = b.tags.get("謀", 0)
    msgs = grown.choose("guard:school:shuyuan")
    assert any("書院" in m for m in msgs) and grown.state.player.stats["silver"] == 500 - t.schools["shuyuan"]["silver"]
    assert b.stage == "study" and b.school == "shuyuan" and b.tags["謀"] == before + 3
    assert b.study_until > b.study_from and "書院" in b.log[-1].text


def test_stay_backs_out_of_the_menu(grown):
    b = grown.state.player.guard
    grown.choose("guard:study")
    grown.choose("guard:stay")
    assert not b.picking and b.stage == "grow" and actions.status(grown)["guard"]["can_study"]


def test_letters_come_while_studying_then_the_trial_settle_and_oath(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    _to_school(grown, "wuguan")
    span = b.study_until - b.study_from
    assert b.event is None  # 剛送去，還沒有信
    grown.sync(b.study_from + span * 0.4)
    assert b.event is not None and b.event.kind == "letter" and "武館" in b.event.text
    grown.choose("guard:open")
    grown.choose("guard:pick:0")
    assert b.letters == 1 and b.stage == "study"
    grown.sync(b.study_from + span * 0.7)
    assert b.event is not None and b.event.kind == "letter"
    grown.choose("guard:open")
    grown.choose("guard:pick:1")
    assert b.letters == t.letters
    grown.sync(b.study_until + 1)  # 看時間不看等級
    assert b.stage == "trial" and b.event is not None and b.event.kind == "trial"
    assert actions.status(grown)["guard"]["event"]["shown"] is False
    grown.choose("guard:open")
    grown.choose("guard:pick:0")
    # 沒有模型：當場固定結算，接著跪誓
    assert b.stage == "oath" and b.path in {p for p, _ in t.paths} and b.title and b.bio and b.oath
    assert b.event is not None and b.event.kind == "oath" and b.event.text == b.oath
    grown.choose("guard:open")
    msgs = grown.choose("guard:pick:0")
    assert b.stage == "sworn" and any("親衛隊長" in m for m in msgs)
    view = actions.status(grown)["guard"]
    assert view["stage"] == "sworn" and view["path"] == b.path and view["bio"] == b.bio


def test_the_top_paths_follow_the_tags(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    b.tags = {"準": 9, "暗": 6, "市": 3}
    top = rules.top_paths(t, b)
    assert top[0] == "弓箭手" and "殺手" in top and len(top) == t.path_options


def test_the_model_settles_but_the_engine_clamps(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    b.tags = {"勇": 8, "謀": 6}
    b.stage = "settle"
    grown.client = FakeClient({"path": "皇帝", "title": "這個稱號太長了吧", "bio": "她長大了。" * 100, "oath": "我發誓。"})
    actions._ask(grown, b, "settle")
    assert b.want == "settle"
    req = actions.event_request(grown)
    assert req.kind == "settle" and req.paths[0] == "將軍"
    got = rules.settle(grown.client, req, t)
    assert actions.apply_event(grown, req, got)
    assert b.path == "將軍"  # 清單外的出路換成第一條
    assert b.title in texts.TITLES["將軍"]  # 稱號太長換固定的
    assert len(b.bio) <= t.bio_max and b.oath == "我發誓。" and b.stage == "oath"
    assert not actions.apply_event(grown, req, got)


def test_a_good_title_from_the_model_is_kept(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    b.stage, b.tags = "settle", {"仁": 5}
    grown.client = FakeClient({"path": "醫者", "title": "杏林客", "bio": "她在醫館學了三年。", "oath": "這雙手，以後只替你縫傷。"})
    actions._ask(grown, b, "settle")
    req = actions.event_request(grown)
    actions.apply_event(grown, req, rules.settle(grown.client, req, t))
    assert (b.path, b.title) == ("醫者", "杏林客")


def test_settling_too_long_falls_back_to_the_fixed_settle(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    b.stage = "settle"
    grown.client = FakeClient({})
    grown.sync(grown.now)
    assert b.want == "settle"
    grown.sync(grown.now + t.wait_seconds * 2)
    assert b.stage == "oath" and b.title in texts.TITLES[b.path]


def test_hate_still_swears_with_the_hate_oath(grown):
    b, t = grown.state.player.guard, grown.content.config.guard
    b.stage, b.qing = "settle", -18
    grown.sync(grown.now)
    assert b.stage == "oath" and "倒下" in b.oath


def test_study_time_left_carries_into_the_next_season(grown):
    b = grown.state.player.guard
    _to_school(grown)
    left = b.study_until - grown.state.world.time
    old = grown.state.model_copy(deep=True)
    grown.state.world.time = 5.0
    actions.on_season_start(grown, old)
    assert b.stage == "study" and abs((b.study_until - 5.0) - left) < 1e-6


def test_bots_go_to_school(grown):
    assert bots.score(grown, Option(id="guard:study", label="")) == 55.0
    scores = [bots.score(grown, Option(id=f"guard:school:{k}", label="")) for k in texts.SCHOOLS]
    assert sorted(scores)[-1] == 50.0 and scores.count(50.0) == 1
    assert bots.score(grown, Option(id="guard:stay", label="")) == 1.0


def test_the_fixed_texts_for_batch_two_are_complete(grown):
    t = grown.content.config.guard
    assert set(texts.SCHOOLS) == set(t.schools)
    assert {p for p, _ in t.paths} == set(texts.TRIALS) == set(texts.TITLES)
    assert set(texts.OATHS) == set(texts.BIO_END) == {n for _, n in t.bands} | {t.hate_band}
    for e in texts.LETTERS:
        assert len(e["choices"]) == 3
