"""口訣與秘方（PM 2026-10-10 派工，企劃者選「甲乙都做」）。
武學重構（Joy 2026-10-20）之後秘方的規則還沒改，這裡照引擎現在實際的行為測：
- kind fuse 的秘方改成「屬性＋指定意境裝滿」：武學合得上那一格、槽全部裝滿、其中一格是指定的意境，就暗合口訣（給特別功效）；
- 武學＋武學的秘方跟著武學合成一起拿掉了（Joy 2026-10-21）；
- 意境＋意境的秘方照舊，合出來的意境帶特別功效（裝進槽就是那一招）。
天時地利（fusion.setting_points）、品質擲骰、合到舊的候選（landing）都拿掉了，那幾條測試刪除。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import arts as arts_mod
from tianxia import fusion, secret_recipes
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import ArtPattern, InsightPattern, SecretRecipe
from tianxia.state import new_game_state
from test_fusion import must_not_ask, named

FUSE = SecretRecipe(
    id="t_fuse", kind="fuse", art=ArtPattern(attribute="慢"), insight=InsightPattern(id="shan"),
    name="鎮岳指", note="一指按下去，像一座山壓著。", clues=["說書一句。", "人物一句。", "殘譜一句。"],
)
MERGE = SecretRecipe(
    id="t_merge", kind="merge", left=InsightPattern(id="shan"), right=InsightPattern(id="shui"),
    name="山環水抱", clues=["先立其山。", "山得坐穩。", "山左水右。"],
)
@pytest.fixture
def secret_content(content):
    content.secret_recipes = [FUSE, MERGE]
    s = content.config.secrets
    s.quality_points, s.insight_points = 20, 10
    return content


@pytest.fixture
def ready(state, secret_content):
    state.player.member.wugong_id = "basic_fist"  # 武學、屬實
    state.player.insights = ["feng", "huo", "shan", "shui"]
    state.player.stats["xinde"] = 100
    return state


def test_each_season_picks_its_own_batch(secret_content):
    pool = [FUSE.model_copy(update={"id": f"f{i}", "name": f"名{i}"}) for i in range(10)]
    secret_content.secret_recipes = pool
    first = secret_recipes.active(secret_content, 0)
    assert len(first) == 2 and first == secret_recipes.active(secret_content, 0)  # 同一季全服同一批
    assert any(secret_recipes.active(secret_content, t) != first for t in range(1, 6))  # 換季換一批


def test_filling_the_slots_with_the_named_insight_hits_the_set_secret(ready, secret_content, world):
    """「屬性＋指定意境裝滿」：基礎拳腳兼容並蓄，屬性照強度最高那一格（山在第一格＝慢）；裝第一格什麼都沒有，裝滿那一下暗合口訣：
    一句話、武學譜記上、這一季第一個暗合的江湖上傳一句；身上的樣子多那一條特別功效。不叫模型、不登記武學。"""
    from tianxia import team
    sp = secret_content.traits.special[0]  # 測試內容現成的一條特別功效
    secret_content.secret_recipes[0] = FUSE.model_copy(update={"special": sp.id})
    assert fusion.forge_request(ready, secret_content, world, "basic_fist", ["shan"]) is None
    first = arts_mod.slot(ready, secret_content, world, "basic_fist", "shan")
    assert len(first) == 1 and ready.player.manual.solved == []
    msgs = arts_mod.slot(ready, secret_content, world, "basic_fist", "feng")
    assert any("暗合口訣" in m and "【鎮岳指】" in m and sp.name in m for m in msgs)
    assert ready.player.manual.solved == ["t_fuse"] and ready.world.secret_sets == {"t_fuse": ready.player.name}
    assert any("鎮岳指" in m for m in msgs[1:])  # 第一個暗合的：傳聞那一句
    mine = team.player_art(ready, secret_content, world, "basic_fist")
    assert mine.special == sp.id
    arts_mod.unslot(ready, secret_content, world, "basic_fist", "feng")  # 拆一格就不合了
    assert team.player_art(ready, secret_content, world, "basic_fist").special is None
    again = arts_mod.slot(ready, secret_content, world, "basic_fist", "feng")
    assert any("暗合口訣" in m for m in again) and not any("江湖上傳開了" in m for m in again)  # 傳聞只有第一次
    assert world.lookup_recipe("秘|t_fuse") is None


def test_the_set_secret_needs_the_named_insight_and_the_attribute(ready, secret_content, world):
    """槽滿了但沒有指定的意境、或屬性對不上（風在第一格＝快），都不合。"""
    from tianxia import team
    arts_mod.slot(ready, secret_content, world, "basic_fist", "feng")
    assert not any("暗合" in m for m in arts_mod.slot(ready, secret_content, world, "basic_fist", "shan"))
    ready.player.art_slots["basic_fist"] = ["huo", "shui"]
    slots = ready.player.art_slots["basic_fist"]
    art = team.resolve_art("basic_fist", secret_content, world)
    assert secret_recipes.match_slots(ready, secret_content, world, "basic_fist", art, slots) is None


@pytest.mark.smoke
def test_hitting_a_merge_secret_registers_the_named_insight_with_a_special_and_tells_the_world(ready, secret_content, world):
    """合中意境＋意境的秘方：名字照內容、不叫模型，帶一條特別功效（裝進槽就是那一招），傳一句、寫進江湖史、記進武學譜；
    照著合的別人不再傳。"""
    assert fusion.forge_request(ready, secret_content, world, None, ["shan", "shui"]) is None  # 名字內容寫好了：不叫模型
    made, msgs = fusion.merge(ready, secret_content, world, must_not_ask(), "shan", "shui")
    assert (made.name, made.secret) == ("山環水抱", "t_merge") and made.secret_special is not None
    assert arts_mod.skill_name(secret_content, made) == arts_mod.special_of(secret_content, made.secret_special).name
    assert world.lookup_insight_recipe("秘|t_merge").id == made.id
    assert secret_content.config.secrets.hit_line in msgs
    assert any("參透了一句口訣" in m for m in msgs)
    assert any("參透口訣" in r.text for r in ready.world.chronicle)
    assert ready.player.manual.solved == ["t_merge"]
    again, msgs = fusion.merge(ready, secret_content, world, must_not_ask(), "shan", "shui")
    assert again.id == f"{made.id}~2" and again.secret_special == made.secret_special  # 意境效果池：再合是另一份
    assert not any("參透了一句口訣" in m for m in msgs) and ready.player.manual.solved == ["t_merge"]
    other = new_game_state(secret_content, "乙")
    other.player.insights = ["shan", "shui"]
    other.player.stats["xinde"] = 100
    copy, msgs = fusion.merge(other, secret_content, world, must_not_ask(), "shan", "shui")
    assert copy.id == made.id and not any("參透了一句口訣" in m for m in msgs)
    assert other.player.manual.solved == ["t_merge"]


def test_merge_secret_cares_about_left_and_right(ready, secret_content, world):
    wrong, _ = fusion.merge(ready, secret_content, world, named("水山相依"), "shui", "shan")
    assert wrong.secret is None
    right, msgs = fusion.merge(ready, secret_content, world, must_not_ask(), "shan", "shui")
    assert (right.name, right.secret) == ("山環水抱", "t_merge") and ready.player.manual.solved == ["t_merge"]


def test_a_character_name_clash_falls_back_to_the_word_table(ready, secret_content, world):
    world.is_character_name = lambda name: name == "山環水抱"
    made, _ = fusion.merge(ready, secret_content, world, must_not_ask(), "shan", "shui")
    assert made.secret == "t_merge" and made.name != "山環水抱" and made.note == ""


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


def test_secrets_in_the_real_content_load_and_cover_every_kind():
    c = real_content()
    assert {r.kind for r in c.secret_recipes} == {"fuse", "merge"}
    assert all(len(r.clues) == 3 for r in c.secret_recipes)
    assert c.config.secrets.quality_points > 0  # 天時地利（fuse_quality.terrain）合成不用了，不再查


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
    merged, _ = fusion.merge(ready, secret_content, world, must_not_ask(), own.id, "shui")
    assert merged.secret == "t_merge" and merged.id in ready.player.insights
