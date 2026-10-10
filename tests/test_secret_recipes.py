"""口訣與秘方、天時地利（PM 2026-10-10 派工，企劃者選「甲乙都做」）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import fusion, landing, secret_recipes, skillview
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import ArtPattern, InsightPattern, SecretRecipe
from tianxia.state import new_game_state
from test_fusion import Fixed, must_not_ask, named

FUSE = SecretRecipe(
    id="t_fuse", kind="fuse", art=ArtPattern(attribute="實"), insight=InsightPattern(id="shan"),
    name="鎮岳指", note="一指按下去，像一座山壓著。", clues=["說書一句。", "人物一句。", "殘譜一句。"],
)
MERGE = SecretRecipe(
    id="t_merge", kind="merge", left=InsightPattern(id="shan"), right=InsightPattern(id="shui"),
    name="山環水抱", clues=["先立其山。", "山得坐穩。", "山左水右。"],
)
BLEND = SecretRecipe(
    id="t_blend", kind="blend", arts=[ArtPattern(attribute="實"), ArtPattern(attribute="快", kind="武學")],
    name="疾實勁", clues=["一實一疾。", "又實又快。", "實者為裡。"],
)


@pytest.fixture
def secret_content(content):
    content.secret_recipes = [FUSE, MERGE, BLEND]
    s = content.config.secrets
    s.quality_points, s.insight_points = 20, 10
    return content


@pytest.fixture
def ready(state, secret_content):
    state.player.member.wugong_id = "basic_fist"  # 武學、屬實
    state.player.arts = ["step"]  # 武學、屬快
    state.player.insights = ["feng", "huo", "shan", "shui"]
    state.player.stats["xinde"] = 100
    return state


def test_each_season_picks_its_own_batch(secret_content):
    pool = [FUSE.model_copy(update={"id": f"f{i}", "name": f"名{i}"}) for i in range(10)]
    secret_content.secret_recipes = pool
    first = secret_recipes.active(secret_content, 0)
    assert len(first) == 2 and first == secret_recipes.active(secret_content, 0)  # 同一季全服同一批
    assert any(secret_recipes.active(secret_content, t) != first for t in range(1, 6))  # 換季換一批


def test_hitting_a_secret_registers_the_named_art_with_a_special_and_tells_the_world(ready, secret_content, world):
    rng = Fixed("中品")
    art, msgs = fusion.fuse(ready, secret_content, world, must_not_ask(), "basic_fist", "shan", rng=rng)
    assert (art.name, art.secret, art.note) == ("鎮岳指", "t_fuse", FUSE.note)
    assert art.special is not None and art.attribute == "慢"
    assert world.lookup_recipe("秘|t_fuse").id == art.id
    assert secret_content.config.secrets.hit_line in msgs
    assert any("參透了一句口訣" in m for m in msgs)
    assert any("參透口訣" in r.text for r in ready.world.chronicle)
    assert ready.player.manual.solved == ["t_fuse"]
    shan = fusion.insights.resolve("shan", secret_content, world)
    plain = fusion.fuse_odds(ready, secret_content, "basic_fist", secret_content.skills["basic_fist"], shan)
    assert rng.weights["上品"] > plain.odds["上品"]  # 秘方那一爐擲的機率比同一組一般的好
    # 同一個人再合一次：已經有了；照著合的人不再傳
    again, why = fusion.fuse(ready, secret_content, world, must_not_ask(), "basic_fist", "shan")
    assert again is None and "已經有了" in why[0]
    other = new_game_state(secret_content, "乙")
    other.player.member.wugong_id = "basic_fist"
    other.player.insights = ["shan"]
    other.player.stats["xinde"] = 100
    copy, msgs = fusion.fuse(other, secret_content, world, must_not_ask(), "basic_fist", "shan")
    assert copy.id == art.id and not any("參透了一句口訣" in m for m in msgs)
    assert other.player.manual.solved == ["t_fuse"]


def test_a_secret_needs_no_model_and_is_never_a_landing_candidate(ready, secret_content, world):
    assert fusion.forge_request(ready, secret_content, world, "basic_fist", ["shan"]) is None
    art, _ = fusion.fuse(ready, secret_content, world, must_not_ask(), "basic_fist", "shan")
    assert art not in landing.art_candidates(world, art.kind, art.attribute, art.lean)


def test_merge_secret_cares_about_left_and_right(ready, secret_content, world):
    wrong, _ = fusion.merge(ready, secret_content, world, named("水山相依"), "shui", "shan")
    assert wrong.secret is None
    right, msgs = fusion.merge(ready, secret_content, world, must_not_ask(), "shan", "shui")
    assert (right.name, right.secret) == ("山環水抱", "t_merge") and ready.player.manual.solved == ["t_merge"]
    # 秘方合出來的意境拿去融，意境的來歷多加分
    assert fusion.insight_points(ready, secret_content, right) >= secret_content.config.secrets.insight_points


def test_blend_secret_ignores_the_order(ready, secret_content, world):
    art, _ = fusion.blend(ready, secret_content, world, must_not_ask(), "step", "basic_fist")
    assert (art.name, art.secret) == ("疾實勁", "t_blend")
    assert sorted(art.parents) == ["basic_fist", "step"]


def test_a_character_name_clash_falls_back_to_the_word_table(ready, secret_content, world):
    world.is_character_name = lambda name: name == "鎮岳指"
    art, _ = fusion.fuse(ready, secret_content, world, must_not_ask(), "basic_fist", "shan")
    assert art.secret == "t_fuse" and art.name != "鎮岳指" and art.note == ""


@pytest.fixture
def game(secret_content, world):
    secret_content.config.auto_open_first_season = True
    g = Game.new(secret_content, "甲", rng=random.Random(0), world=world)
    g.client = None
    g.sync(1000.0)
    return g


def test_tales_and_scraps_write_clues_into_the_manual_without_touching_the_game_rng(game, secret_content):
    cfg = secret_content.config.secrets
    event = secret_content.events["drunk"]
    assert game._tale_clue(event) == [] and game._scrap_find() == []  # 全關
    cfg.tale_events, cfg.tale_chance, cfg.scrap_chance = ["drunk"], 1.0, 1.0
    before = game.rng.getstate()
    tale = game._tale_clue(event)
    scrap = game._scrap_find()
    assert game.rng.getstate() == before
    assert "「" in tale[0] and "殘譜" in scrap[0]
    book = game.state.player.manual
    heard = sorted((rid, i) for rid, idx in book.heard.items() for i in idx)
    assert len(heard) == 2 and {i for _, i in heard} == {secret_recipes.TALE, secret_recipes.SCRAP}
    assert len(book.heard) == 2  # 先挑還沒聽過的那一條
    rows = game.status_data()["manual"]
    assert sorted(len(r["clues"]) for r in rows) == [1, 1] and all(r["solved"] is None for r in rows)


def test_a_character_only_lets_a_clue_slip_once_close_enough(game, secret_content):
    s, w = game.state, game.world
    cid = next(iter(secret_content.characters))
    assert secret_recipes.talk_line(s, secret_content, w, cid, "某") == ""
    recipe = secret_recipes.talk_clue(secret_content, secret_recipes.tianji_of(w), cid)
    said = f"他嘆道：「{recipe.clues[secret_recipes.TALK]}」"
    assert game._overhear(cid, [said]) == []  # 情誼不夠：提示裡沒有，說了也不算
    s.player.affinities[cid] = secret_content.config.secrets.talk_affinity
    assert recipe.clues[secret_recipes.TALK] in secret_recipes.talk_line(s, secret_content, w, cid, "某")
    assert game._overhear(cid, ["他只是笑了笑。"]) == []
    assert game._overhear(cid, [said]) == [secret_content.config.secrets.overheard]
    assert game._overhear(cid, [said]) == []  # 第二次不再提醒


def test_the_manual_belongs_to_one_season(state, secret_content):
    secret_recipes.solve(state, 3, FUSE)
    assert secret_recipes.manual(state, 3).solved == ["t_fuse"]
    assert secret_recipes.manual(state, 4).solved == []


# ── 天時地利 ─────────────────────────────────────────────


@pytest.fixture
def setting(content):
    rule = content.config.fuse_quality
    rule.terrain, rule.night_match, rule.night_clash, rule.battlefield, rule.calm = 6, 6, -4, 6, 5
    rule.setting_good, rule.setting_bad = "天時地利。", "時辰不對。"
    return content


def test_setting_is_off_by_default(state, content):
    shui = fusion.insights.resolve("shui", content, None, state)
    assert fusion.setting_points(state, content, "柔", "無", shui) == []


def test_terrain_night_battlefield_and_calm(state, setting):
    c, s = setting, state
    resolve = lambda i: fusion.insights.resolve(i, c, None, s)  # noqa: E731
    s.world.time = 3600  # 白天
    s.player.location = "lake"  # 探索悟得到水、風
    assert fusion.setting_points(s, c, "柔", "無", resolve("shui")) == [("terrain", 6)]
    assert fusion.setting_points(s, c, "山", "無", resolve("shan")) == []
    assert fusion.setting_points(s, c, "陰", "邪", resolve("xuesha")) == [("night", -4)]
    assert fusion.setting_points(s, c, "陽", "正", resolve("haoran")) == [("night", 6)]
    s.world.time = 0  # 夜裡
    assert fusion.setting_points(s, c, "陰", "邪", resolve("xuesha")) == [("night", 6)]
    c.locations["cave"].tags = ["營寨"]
    s.player.location = "cave"
    assert fusion.setting_points(s, c, "剛", "無", resolve("huo")) == [("battlefield", 6)]
    s.player.seclusion_done = 0
    s.world.time = 3600
    got = fusion.setting_points(s, c, "剛", "邪", resolve("huo"))
    assert len(got) == 2 and got[0] == ("battlefield", 6)  # 最多兩條，照絕對值挑
    assert fusion.setting_line(c, got) == ["天時地利。"]
    assert fusion.setting_line(c, [("night", -4)]) == ["時辰不對。"]


def test_setting_moves_the_odds_and_the_forge_line_says_why(state, setting, world):
    s = state
    s.player.member.wugong_id = "basic_fist"
    s.player.insights = ["shui"]
    s.player.stats["xinde"] = 100
    s.player.location = "town"
    away = fusion.fuse_odds(s, setting, "basic_fist", setting.skills["basic_fist"], fusion.insights.resolve("shui", setting, world, s))
    s.player.location = "lake"
    here = fusion.fuse_odds(s, setting, "basic_fist", setting.skills["basic_fist"], fusion.insights.resolve("shui", setting, world, s))
    assert here.odds["上品"] > away.odds["上品"]
    assert "此地氣象與這股意相合" in skillview.forge_line(s, setting, world, "basic_fist", ["shui"])


def test_secrets_in_the_real_content_load_and_cover_every_kind():
    c = real_content()
    assert {r.kind for r in c.secret_recipes} == {"fuse", "merge", "blend"}
    assert all(len(r.clues) == 3 for r in c.secret_recipes)
    assert c.config.secrets.quality_points > 0 and c.config.fuse_quality.terrain > 0


def test_a_broken_secret_fails_validation(content):
    content.secret_recipes = [SecretRecipe(id="x", kind="fuse", art=ArtPattern(), insight=InsightPattern(id="nope"),
                                           name="壞方子", clues=["一。", "二。", "三3。"])]
    with pytest.raises(ContentError) as caught:
        validate(content)
    text = str(caught.value)
    assert "誰都合得上" in text and "nope" in text and "數字" in text


def test_a_self_found_insight_counts_by_its_attribute(ready, secret_content, world):
    """大多數人手上是自己悟的私有意境：寫了基本意境 id 的格子照那個意境的屬性認（同配方鍵認私有意境的做法）。"""
    from tianxia import sensing
    from tianxia.martial_arts import Insight

    own = sensing.add_own(ready, Insight(id="", name="峰影", attribute="慢", creator="沈浪", creator_shown="沈浪"))
    ready.player.insights.remove("shan")
    art, _ = fusion.fuse(ready, secret_content, world, must_not_ask(), "basic_fist", own.id)
    assert art.secret == "t_fuse" and art.insight is None and art.insight_attr == "慢"
    merged, _ = fusion.merge(ready, secret_content, world, must_not_ask(), own.id, "shui")
    assert merged.secret == "t_merge" and merged.id in ready.player.insights
