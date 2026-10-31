"""自創武學的五步（Joy 2026-10-20：執器、擺式〔拖火柴人〕、立意〔模型讀一句意〕、成形〔每格分顏色〕、立名）與槽分顏色。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import arts as arts_mod, create, moves, tactics, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import ATTRIBUTES, MartialArt as _MA
from tianxia import create
from tianxia.state import CreateDraft


def MartialArt(**kw):
    return _MA(**{"base_power": 10, "top_power": 100, **kw})

ROOT = Path(__file__).parents[2]


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
    xinde = game.state.player.stats["xinde"]
    need = create.price(game.state, content)
    draft = _walk(game, reading=create.IntentReading(score=60, attributes=["快", "虛"], lean="正"))
    assert draft.step == "name" and len(draft.colors) == content.config.arts.create_slots
    assert draft.colors[0] == [max(ATTRIBUTES, key=lambda a: (create.weights(content, draft)[a], -ATTRIBUTES.index(a)))]
    assert draft.colors[0] == ["快"]  # 拳腳偏快＋意讀出快：權重最高的那一路當第一格單色
    assert game.state.player.stats["xinde"] == xinde - need and draft.paid == need  # 立意那一刻就收（Joy 2026-10-21）
    game.create_name("飄風手")
    p = game.state.player
    assert p.creating is None and p.stats["xinde"] == xinde - need  # 立名不再收
    art = team.resolve_art("飄風手", content, game.world)
    assert art.origin == "created" and art.weapon == "拳腳" and art.lean == "正"
    assert art.slot_colors == draft.colors and art.pose == draft.pose
    n = len(arts_mod.slots_of(game.state, content, art))
    assert p.art_quality["飄風手"] == "上品"  # Joy 2026-10-21：自創保底上品
    assert n == arts_mod.slot_count(content, "上品")
    assert art.attribute == "快" and art.affinity[0] == "快"
    assert set(art.affinity) == {"快", *create.affinity_of(draft.colors[:n])}


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


@pytest.mark.smoke
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
    assert d["form"] == "拳腳" and len(d["colors"]) == content.config.arts.create_slots
    assert "odds" not in d and v["grade"] == "上品"  # 不擲品級了


def test_the_intent_score_sets_the_base_power(content):
    """基本威力（Joy 2026-10-21）：意分夾 0～100，從 power_scale_range 下限推到上限；名字不影響。"""
    from tianxia.martial_arts import power_scale
    low, high = content.config.arts.power_scale_range
    assert create.power_scale_of(content, 0) == pytest.approx(low)
    assert create.power_scale_of(content, 100) == pytest.approx(high)
    assert create.power_scale_of(content, 150) == pytest.approx(high)
    game = _game(content)
    _walk(game, reading=create.IntentReading(score=80, attributes=["快"], lean="無"))
    d = game.create_view()["draft"]
    m = d["might"]
    assert d["power"] == create.MIGHT_LINE.format(now=m["now"], first=m["first"], full=m["full"])
    assert m["full"] > m["first"] > 0  # 練滿比第一成強
    game.create_name("厚底拳")
    art = team.resolve_art("厚底拳", content, game.world)
    assert power_scale(art) == pytest.approx(create.power_scale_of(content, 80), abs=0.01)


# ── 以意成招（招式與絕學稿案第二節）──────────────────


def test_stance_is_read_from_the_pose(content):
    assert create.stance_of(create.preset(content, "進擊")) == "攻勢"
    assert create.stance_of(create.preset(content, "守禦")) == "守勢"
    assert create.stance_of(create.preset(content, "奇變")) == "變勢"
    assert create.stance_of(create.preset(content, "起手")) == "起勢"
    assert moves.timing_of("武學", "攻勢") == "出招" and moves.timing_of("內功", "攻勢") == "心法"
    assert moves.timing_of("內功", "起勢") == "起手"


def test_the_table_covers_every_attribute_and_stance(content):
    for a in ATTRIBUTES:
        for timing in ("起手", "出招", "乘勢", "應招", "心法"):
            assert moves.cell(content, a, timing) is not None, (a, timing)
    assert sum(m.rare for m in content.create_forms.moves) == len(ATTRIBUTES)
    for m in content.create_forms.moves:  # 每一種招在那個時機都接得上戰鬥的程式；那一句只用得到 {foe}、params 與 {state}
        assert m.kind in tactics.KINDS and set(m.grow) <= {"rate", *m.params}
        m.say.format(foe="某", state="定身", **{k: tactics.value_text(k, v) for k, v in m.params.items()})


def test_fire_follows_the_score_and_scales_the_growing_numbers(content):
    low, high = content.config.arts.move_fire_cuts
    assert [moves.fire_of(content, s) for s in (low, low + 1, high, high + 1)] == ["生", "熟", "熟", "透"]
    clear = moves.build(content, "武學", "快", "攻勢", "透")
    raw = moves.build(content, "武學", "快", "攻勢", "生")
    row = moves.cell(content, "快", "出招")
    assert clear.rate == pytest.approx(row.rate) and raw.rate == pytest.approx(row.rate * content.config.arts.move_fire["生"])
    young = moves.build(content, "武學", "快", "攻勢", "透", level=1)
    grown = moves.build(content, "武學", "快", "攻勢", "透", level=content.config.arts.move_raw_levels + 1)
    assert young.rate == pytest.approx(row.rate * content.config.arts.move_raw_scale) and grown.rate == pytest.approx(row.rate)


def test_a_created_art_grows_its_own_move(content):
    from tianxia import skillview

    game = _game(content)
    reading = create.IntentReading(score=80, attributes=["快"], lean="無", move="追風影", say="腳下一錯追了上去")
    _walk(game, pose=create.preset(content, "進擊"), reading=reading)
    d = game.create_view()["draft"]
    seal = game.state.player.name[:1]  # 自創的招蓋創的人名號的第一個字（私印）
    assert d["stance"] == "攻勢" and d["timing"] == "出招" and d["fire"] == "透" and d["move"] == "追風影"
    assert d["tactic"].startswith(seal + "〔追風影〕出招")
    assert "影不留" not in d["tactic"]
    assert "招還生" not in d["tactic"]
    game.create_name("追影拳", move="疾影")
    art = team.resolve_art("追影拳", content, game.world)
    assert (art.move_name, art.move_fire, art.move_stance, art.move_say) == ("疾影", "透", "攻勢", "腳下一錯追了上去")
    move = tactics.of_art(content, art)
    assert move.name == "疾影" and move.timing == "出招" and move.say == "腳下一錯追了上去"
    assert tactics.title_of(move, art) == seal
    p = game.state.player
    p.member.wugong_id, p.member.wugong_level = "追影拳", 1
    held = next(h for h in team.tactic_holders(game.state, content, game.world) if h.skill == "追影拳")
    assert held.tactic.rate < move.rate  # 第一成招還生
    row = next(r for r in skillview.art_rows(game.state, content, game.world) if r["id"] == "追影拳")
    assert row["tactic"].startswith(seal + "〔疾影〕") and row["tactic"].endswith("（招還生）")
    p.member.wugong_level = content.config.arts.move_raw_levels + 1
    held = next(h for h in team.tactic_holders(game.state, content, game.world) if h.skill == "追影拳")
    assert held.tactic.rate == pytest.approx(move.rate)


def test_a_bad_move_name_is_refused_and_nothing_is_charged(content):
    game = _game(content)
    _walk(game)
    xinde = game.state.player.stats["xinde"]
    assert game.create_name("飄風手", move="一二三四五六") == [create.MOVE_LINE]
    assert game.state.player.creating is not None and game.state.player.stats["xinde"] == xinde
    game.create_name("飄風手")  # 沒給招名：照模型起的，再沒有照表的預設名
    art = team.resolve_art("飄風手", content, game.world)
    assert art.move_name == moves.cell(content, art.attribute, moves.timing_of("武學", "起勢")).name


def test_pure_slots_add_to_the_trait_layers(content):
    game = _game(content)
    art = MartialArt(id="純色掌", name="純色掌", kind="武學", quality="上品", attribute="剛", affinity=["剛"],
                     slot_colors=[["剛"], ["剛"], ["柔"]], origin="created", creator=game.state.player.name)
    assert moves.look_bonus(content, art) == pytest.approx(content.config.arts.pure_bonus)
    mixed = art.model_copy(update={"slot_colors": [["剛"], [], ["柔"]]})
    assert moves.look_bonus(content, mixed) == 0.0
    whole = art.model_copy(update={"slot_colors": [[], [], []]})
    assert moves.look_bonus(content, whole) == pytest.approx(content.config.arts.whole_bonus)
    assert create.look_text(create.marks_of([["剛"], ["剛"], ["柔"]], "透", False)).startswith("珍・")


def test_the_first_art_of_the_season_is_cheaper(content):
    """Joy 2026-10-21「第一次自創武學，降低到只需要100心得，之後一樣500」：這一季第一門 create_first_xinde，之後照 create_xinde。"""
    content.config.arts.create_first_xinde = 100
    game = _game(content)
    p = game.state.player
    assert create.price(game.state, content) == 100
    xinde = p.stats["xinde"]
    _walk(game, reading=create.IntentReading(score=60, attributes=["快", "虛"], lean="正"))
    game.create_name("飄風手")
    assert p.stats["xinde"] == xinde - 100 and p.created_count == 1
    assert create.price(game.state, content) == content.config.arts.create_xinde == 500
    content.config.arts.create_first_xinde = 0  # 測試內容關著：第一門也照 create_xinde
    p.created_count = 0
    assert create.price(game.state, content) == 500


def test_going_back_after_paying_does_not_charge_again_and_cancel_keeps_the_xinde(content):
    game = _game(content)
    p = game.state.player
    xinde = p.stats["xinde"]
    need = create.price(game.state, content)
    _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
    assert p.stats["xinde"] == xinde - need and p.created_count == 1
    game.create_back("intent")  # 免費重來一次：回去重立意不再收
    game.create_intent("風過林梢，影不留痕", reading=create.IntentReading(score=70, attributes=["快"]))
    assert p.stats["xinde"] == xinde - need and p.created_count == 1 and p.creating.step == "name"
    msgs = game.create_cancel()
    assert "不退" in msgs[0] and p.stats["xinde"] == xinde - need and p.creating is None


def test_paying_the_last_xinde_at_intent_still_lets_you_name_it(content):
    """立意收光了心得，立名那一步不能再拿「心得不足」擋下來（整季機器人抓到的）。"""
    game = _game(content)
    game.state.player.stats["xinde"] = create.price(game.state, content)
    _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
    assert game.state.player.stats["xinde"] == 0
    art, msgs = create.finish(game.state, content, game.world, "流雲步")
    assert art is not None and game.state.player.creating is None, msgs


def test_a_reroll_slip_rolls_the_form_again(content):
    """重悟帖（Joy 2026-10-21「弄個商城道具可以直接重骰，有上限」）：成了形直接重擲顏色與變招，不收心得、不用掉免費的重來。"""
    game = _game(content)
    p = game.state.player
    assert create.reroll(game.state, content, game.world) == [create.NO_DRAFT]
    _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
    assert game.create_reroll() == [create.NO_REROLL]
    p.create_rerolls = 3
    xinde, redo, rolls = p.stats["xinde"], p.creating.redo, p.creating.rolls
    seen = {tuple(map(tuple, p.creating.colors))}
    for _ in range(3):
        msgs = game.create_reroll()
        assert "換了個形" in msgs[0]
        seen.add(tuple(map(tuple, p.creating.colors)))
    assert p.create_rerolls == 0 and p.creating.rolls == rolls + 3 and p.creating.redo == redo and p.stats["xinde"] == xinde
    assert len(seen) > 1  # 三次裡總會擲出不一樣的形
    assert create.view(game.state, content, game.world)["rerolls"] == 0


def test_rerolls_are_capped_per_art_not_per_purchase(content):
    """Joy 2026-10-21「一次創造武學的時候可能最多重骰3或是5，總共要買幾張都可以」：帖子不限，一門最多 create_reroll_cap 次；下一門重新算。"""
    game = _game(content)
    p = game.state.player
    cap = content.config.arts.create_reroll_cap
    assert cap == 5
    _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
    p.create_rerolls = cap + 3
    for i in range(cap):
        assert "換了個形" in game.create_reroll()[0]
        assert create.view(game.state, content, game.world)["draft"]["reroll_left"] == cap - i - 1
    assert game.create_reroll() == [create.REROLL_CAPPED.format(cap=cap)]
    assert p.create_rerolls == 3 and p.creating.rerolled == cap  # 骰不了的那一下不扣帖子



def test_a_paid_draft_can_still_be_named_when_the_season_cap_is_reached(content):
    """立意就數進這一季的門數：有每季上限時，付過的那一門照樣立得了名（不能卡在那裡、心得白付）。"""
    content.config.arts.create_per_season = 1
    try:
        game = _game(content)
        _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
        assert game.state.player.created_count == 1
        art, msgs = create.finish(game.state, content, game.world, "流雲步")
        assert art is not None, msgs
        assert create.allowed(game.state, content) == create.CAP_LINE.format(n=1)  # 下一門才擋
    finally:
        content.config.arts.create_per_season = 0


def test_a_bot_keeps_a_paid_draft_and_names_it_next_time(content):
    """假人取名都撞名時不丟掉付過心得的單子，下一次接著取。"""
    from tianxia import bot

    game = _game(content)
    _walk(game, reading=create.IntentReading(score=60, attributes=["快"]))
    xinde = game.state.player.stats["xinde"]
    assert bot.create_art(game, random.Random(1))
    assert game.state.player.creating is None and game.state.player.stats["xinde"] == xinde


def test_no_slip_points_to_the_mall(content):
    """Joy 2026-10-22「沒有重悟丹不會自動提示玩家去商城購買」：手上沒帖、萬寶閣賣重悟帖時 view 給那一件的 id（網頁畫「去萬寶閣」）；
    商城關著、沒賣、手上還有帖都是 None。"""
    from tianxia.models import MallItem

    game = _game(content)
    assert create.view(game.state, content, game.world)["shop"] is None  # 商城關著
    content.config.mall.enabled = True
    content.mall = {"reroll_1": MallItem(id="reroll_1", name="重悟帖", price=50, kind="consumable", effects={"create_reroll": 1})}
    assert create.view(game.state, content, game.world)["shop"] == "reroll_1"
    game.state.player.create_rerolls = 1
    assert create.view(game.state, content, game.world)["shop"] is None


# ── 原 test_fb653_create_draft_doc.py（整檔搬進來） ──
# FB-653：`state.CreateDraft` 的說明不再寫「擲品級」。
#
# 自創武學的品級不擲（武學重構之後；`create.finish` 的 `grade = content.config.arts.create_grade`），說明還寫「立名（付心得、擲品級、登記）」
# 會讓讀的人以為立名這一步有一擲。說明寫現在的規則；只是文字，不影響執行。

def test_the_draft_doc_says_the_grade_is_not_rolled():
    doc = CreateDraft.__doc__
    assert "擲品級" not in doc
    assert "付心得、登記" in doc and "create_grade" in doc


def test_the_create_module_agrees():
    assert "擲品級" not in create.__doc__
    assert "Config.arts.create_grade" in create.__doc__


def test_the_model_move_name_and_line_are_screened(content):
    """2026-10-31 自檢：模型起的招名不過名字過濾（禁用名單、人物同名進得了草稿，網頁還預填），招式那一句留著簡體與英文。"""
    game = _game(content)
    draft = _walk(game, reading=create.IntentReading(score=60, attributes=["快"], move="小龍女", say="腳下一错追了上去刺出一剑"))
    assert draft.move == "" and draft.say == "腳下一錯追了上去刺出一劍"
    game2 = _game(content, name="立派人二")
    draft2 = _walk(game2, reading=create.IntentReading(score=60, attributes=["快"], move="追風影", say="He moves like the wind"))
    assert draft2.move == "追風影" and draft2.say == ""
