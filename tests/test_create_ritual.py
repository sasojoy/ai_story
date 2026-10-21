"""自創武學的五步（Joy 2026-10-20：執器、擺式〔拖火柴人〕、立意〔模型讀一句意〕、成形〔每格分顏色〕、立名）與槽分顏色。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import arts as arts_mod, create, fusion, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import ATTRIBUTES, MartialArt as _MA


def MartialArt(**kw):
    return _MA(**{"base_power": 10, "top_power": 100, **kw})

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def content():
    c = load_content(ROOT / "tests" / "fixtures" / "content")
    c.config.auto_open_first_season = True
    return c


def _game(content, name="立派人", xinde=5000):
    game = Game.new(content, name, rng=random.Random(3))
    game.world.open_season(content, now=0.0)
    game.state.player.stats["xinde"] = xinde
    return game


def _walk(game, kind="武學", form="拳腳", pose=None, text="風過林梢，影不留痕", reading=None):
    assert game.create_begin(kind, form)
    game.create_pose(pose or create.preset(game.content, "起手"))
    game.create_intent(text, reading=reading)
    return game.state.player.creating


def test_five_steps_make_an_art_with_coloured_slots_and_the_pose(content):
    game = _game(content)
    draft = _walk(game, reading=create.IntentReading(score=60, attributes=["快", "虛"], lean="正"))
    assert draft.step == "name" and len(draft.colors) == content.config.arts.create_slots
    assert draft.colors[0] == [max(ATTRIBUTES, key=lambda a: (create.weights(content, draft)[a], -ATTRIBUTES.index(a)))]
    assert draft.colors[0] == ["快"]  # 拳腳偏快＋意讀出快：權重最高的那一路當第一格單色
    xinde = game.state.player.stats["xinde"]
    need = create.price(game.state, content)
    game.create_name("飄風手")
    p = game.state.player
    assert p.creating is None and p.stats["xinde"] == xinde - need
    art = team.resolve_art("飄風手", content, game.world)
    assert art.origin == "created" and art.weapon == "拳腳" and art.lean == "正"
    assert art.slot_colors == draft.colors and art.pose == draft.pose
    n = len(arts_mod.slots_of(game.state, content, art))
    assert n == arts_mod.slot_count(content, p.art_quality.get("飄風手", "下品"))
    assert art.affinity == create.affinity_of(draft.colors[:n]) and art.attribute == "快"


def test_begin_checks_the_form_and_the_price_but_charges_nothing(content):
    game = _game(content, xinde=10)
    assert "心得不足" in game.create_begin("武學", "拳腳")[0]
    game.state.player.stats["xinde"] = 5000
    assert "要挑一種" in game.create_begin("武學", "吐納")[0]  # 吐納是內功的行功之法
    game.create_begin("內功", "吐納")
    assert game.state.player.creating.step == "pose" and game.state.player.stats["xinde"] == 5000
    assert create.BUSY_LINE in game.create_begin("武學", "劍")


def test_pose_is_read_from_geometry_and_cleaned(content):
    assert create.pose_read(create.preset(content, "起手")) == []
    assert create.pose_read(create.preset(content, "進擊"))[0] == "剛"
    assert create.pose_read(create.preset(content, "守禦"))[0] == "柔"
    assert create.pose_read(create.preset(content, "奇變"))[0] == "虛"
    pose = create.clean_pose({"t": 99, "lS": 400, "rE": "x", "lK": float("nan")}, create.preset(content))
    assert pose["t"] == create.TORSO_LIMIT and pose["lS"] == 40.0 and set(pose) == set(create.POSE_KEYS)


def test_the_model_reading_is_rechecked(content):
    r = create.clean_reading(create.IntentReading(score=999, attributes=["快", "雷", "快", "陰", "陽"], lean="魔"))
    assert (r.score, r.attributes, r.lean) == (create.SCORE_CAP, ["快", "陰"], "無")
    fb = create.fallback_read(content, "風過林梢，影不留痕")
    assert fb.score == create.DEFAULT_SCORE and fb.attributes and fb.attributes[0] == "快"


def test_one_free_redo_after_the_shape_is_rolled(content):
    game = _game(content)
    draft = _walk(game)
    first = [list(c) for c in draft.colors]
    assert game.create_back("pose") == [create.BACK_LINE]
    assert draft.step == "pose" and draft.colors == [] and draft.redo == 0
    game.create_pose(create.preset(content, "起手"))
    assert game.create_back("pose") == [create.BACK_LINE]  # 立意回擺式不算重來
    game.create_pose(create.preset(content, "起手"))
    game.create_intent("風過林梢，影不留痕")
    assert draft.rolls == 2 and draft.step == "name"
    assert game.create_back("intent") == [create.NO_REDO]
    assert isinstance(first, list)


def test_neutral_intent_rolls_more_any_colour_slots(content):
    draft = create.CreateDraft(kind="武學", form="劍", pose=create.preset(content), step="name")
    keen = draft.model_copy(update={"read": ["快"]})
    any_neutral = sum(c == [] for i in range(400) for c in create.roll_colors(content, draft, random.Random(i)))
    any_keen = sum(c == [] for i in range(400) for c in create.roll_colors(content, keen, random.Random(i)))
    assert any_neutral > any_keen * 1.5


def test_slots_only_take_their_colours_and_pick_a_matching_slot(content):
    game = _game(content)
    art = MartialArt(id="試色掌", name="試色掌", kind="武學", quality="上品", attribute="剛", affinity=["剛", "柔"],
                     slot_colors=[["剛"], ["柔", "快"], [], ["剛"]], origin="created")
    assert game.world.claim_skill_name(art)
    p = game.state.player
    p.arts.append(art.id)
    p.art_quality[art.id] = "上品"
    from tianxia import insights

    shui = next((i for i in content.insights if content.insights[i].attribute == "柔"), None)
    if shui is None:
        pytest.skip("測試內容沒有柔的意境")
    insights.learn(game.state, content, game.world, shui)
    assert arts_mod.slot_problem(game.state, content, game.world, art.id, shui, 0).short == "顏色不合"
    game.slot_insight(art.id, shui)
    assert p.art_slots[art.id][1] == shui  # 柔快那一格（任色的那格留給別的）


def test_blend_inherits_slot_colours_from_both_parents(content):
    a = MartialArt(id="甲", name="甲", kind="武學", quality="下品", attribute="剛", affinity=["剛"], slot_colors=[["剛"], ["剛", "快"]])
    b = MartialArt(id="乙", name="乙", kind="武學", quality="下品", attribute="柔", affinity=["柔"])
    colors = fusion.blend_colors(a, b, "兼|甲+乙", 1, content)
    n = max(content.config.arts.slots.values())
    pool = arts_mod.colors_of(a, n) + arts_mod.colors_of(b, n)
    assert len(colors) == n and all(c in pool for c in colors)
    assert colors == fusion.blend_colors(a, b, "兼|甲+乙", 1, content)
    base = MartialArt(id="丙", name="丙", kind="武學", quality="下品", attribute="")
    assert fusion.blend_colors(base, base, "兼|丙+丙", 1, content) == []


def test_old_three_step_drafts_are_dropped_on_load(content):
    game = _game(content)
    game.state.player.creating = create.CreateDraft(kind="武學", step="form", affinity=["快"], weapon="劍")
    create.prune(game.state, content)
    assert game.state.player.creating is None


def test_bots_walk_all_five_steps(content):
    game = _game(content)
    from tianxia import bot

    assert bot.create_art(game, random.Random(5))
    from tianxia import library

    made = [a for a in library.owned_arts(game.state) if (team.resolve_art(a, content, game.world) or MartialArt(id="x", name="x", kind="武學")).origin == "created"]
    assert made and game.state.player.creating is None


def test_view_lists_forms_presets_and_the_draft(content):
    game = _game(content)
    v = game.create_view()
    assert v["step"] == "form" and {f["key"] for f in v["forms"]["武學"]} >= {"拳腳", "劍", "弓弩"}
    assert {p["name"] for p in v["presets"]} == {"起手", "進擊", "守禦", "奇變"}
    _walk(game)
    d = game.create_view()["draft"]
    assert d["form"] == "拳腳" and len(d["colors"]) == 4 and d["colors_text"][0] in ATTRIBUTES
    assert set(d["odds"]) == {"下品", "中品", "上品"}


def test_the_intent_score_sets_the_base_power(content):
    """基本威力（Joy 2026-10-21）：意分＋加分夾 0～100，從 power_scale_range 下限推到上限；名字不影響。"""
    from tianxia.martial_arts import power_scale
    low, high = content.config.arts.power_scale_range
    assert create.power_scale_of(content, 0) == pytest.approx(low)
    assert create.power_scale_of(content, 100) == pytest.approx(high)
    assert create.power_scale_of(content, 150) == pytest.approx(high)
    game = _game(content)
    _walk(game, reading=create.IntentReading(score=80, attributes=["快"], lean="無"))
    assert game.create_view()["draft"]["power"].startswith("底子：")
    game.create_name("厚底拳")
    art = team.resolve_art("厚底拳", content, game.world)
    assert power_scale(art) == pytest.approx(create.power_scale_of(content, 80), abs=0.01)
