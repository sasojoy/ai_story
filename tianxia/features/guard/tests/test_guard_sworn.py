"""親衛隊長（features/guard）第三批：投效之後。測試內容、開關打開、沒有模型。"""
from __future__ import annotations

import pytest

from tianxia.features.guard import actions, rules, texts


@pytest.fixture
def sworn(game):
    """走完求學、出師、跪誓的那一位（沒有模型：固定事件與固定結算）。"""
    t = game.content.config.guard
    t.enabled = True
    game.state.player.member.level = t.meet_level
    game.client = None
    game.sync(game.now)
    actions.meet_on_explore(game, game.state.player.location)
    for oid in ("guard:save", "guard:adopt:男"):
        game.choose(oid)
    game.state.player.member.level = t.study_level
    game.state.player.stats["silver"] = 500
    game.choose("guard:study")
    game.choose("guard:school:gensui")
    b = game.state.player.guard
    b.letters = t.letters
    game.sync(b.study_until + 1)
    for _ in range(2):  # 出師考驗、跪誓
        game.choose("guard:open")
        game.choose("guard:pick:0")
    assert b.stage == "sworn"
    return game


def test_after_swearing_he_still_has_daily_things(sworn):
    b = sworn.state.player.guard
    b.home_day = 0
    sworn.sync(sworn.now)
    assert b.event is not None and b.event.kind == "home"
    assert actions.status(sworn)["guard"]["event"]["shown"] is False


def test_the_band_moves_at_most_one_step_a_season(sworn):
    b, t = sworn.state.player.guard, sworn.content.config.guard
    b.qing = b.season_qing = 15  # 恩深
    for _ in range(12):
        b.event = rules.fixed_event(t, b, "home", 1, "x")
        b.event.shown = True
        sworn.choose("guard:pick:2")  # 一直狠心
    assert rules.band(t, b.qing) == "敬重"  # 一季只掉一檔
    old = sworn.state.model_copy(deep=True)
    actions.on_season_start(sworn, old)
    assert b.season_qing == b.qing  # 新的一季重新起算


def test_clamp_bounds_cover_both_ends(game):
    t = game.content.config.guard
    assert rules.season_clamp(t, -20, 20) == -4  # 恨極這一季最多焐到怨懟的頂，再上一檔要下一季
    assert rules.season_clamp(t, 20, -20) == 4  # 恩深最多寒到敬重
    assert rules.season_clamp(t, 0, 7) == 7


def test_the_new_season_opens_with_his_letter(sworn):
    b = sworn.state.player.guard
    old = sworn.state.model_copy(deep=True)
    actions.on_season_start(sworn, old)
    assert b.event is not None and b.event.kind == "season" and b.event.text in {rules.fill(v, b) for v in texts.SEASON_LETTERS.values()}


def test_badly_hurt_he_says_a_line_by_his_heart(sworn):
    b, t = sworn.state.player.guard, sworn.content.config.guard
    b.qing = -18
    sworn.sync(sworn.now)
    assert b.hp_seen is not None and b.hp_seen > t.hurt_ratio
    sworn.state.player.member.neili = 1.0
    lines = actions._hurt(sworn, b)
    assert len(lines) == 1 and lines[0] in {rules.fill(x, b) for x in texts.HURT_LINES["恨極"]}
    b.hp_seen = 0.9
    assert actions._hurt(sworn, b) == []  # 一天一次


def test_left_at_home_he_says_nothing(sworn):
    b = sworn.state.player.guard
    b.along = False
    b.hp_seen = 0.9
    sworn.state.player.member.neili = 1.0
    assert actions._hurt(sworn, b) == []


def test_every_band_has_lines():
    assert set(texts.HURT_LINES) == set(texts.SEASON_LETTERS) == set(texts.OATHS)


def test_his_picture_follows_stage_path_and_heart(sworn):
    """頁首的圖（web/img/guard/）：投效了是長大的立繪，出路與心性挑那一張；檔案都在。"""
    import pathlib
    t = sworn.content.config.guard
    b = sworn.state.player.guard
    root = pathlib.Path(__file__).resolve().parents[4] / "web"
    b.qing = t.qing_cap
    a = rules.art(t, b)
    assert a["hero"].endswith("story/yard.webp")
    assert a["face"] == f"/static/img/guard/grown/m-{rules.PATH_ART[b.path]}-wen.webp"
    assert actions.status(sworn)["guard"]["art"] == a
    b.qing = -t.qing_cap
    assert rules.art(t, b)["face"].endswith("-leng.webp")
    b.stage = "oath"
    assert rules.art(t, b)["hero"].endswith("story/oath-leng.webp")
    b.stage, b.sex = "grow", "女"
    assert rules.art(t, b)["face"].endswith("child/f-grown.webp")
    b.stage, b.opening = "met", "river"
    assert rules.art(t, b) == {"hero": "/static/img/guard/story/meet-river.webp", "face": ""}
    for sx in "mf":  # 每一種組合的檔都在
        for code in rules.PATH_ART.values():
            for look in set(rules.LOOKS):
                assert (root / f"img/guard/grown/{sx}-{code}-{look}.webp").exists()
        for school in t.schools:
            assert (root / f"img/guard/study/{sx}-{school}.webp").exists()
    for key in rules.MEET_ART:
        assert (root / f"img/guard/story/meet-{key}.webp").exists()
