"""同效果好幾份（Joy 2026-10-22 選「第二份算半」）：同一個一般功效第二份起每份算一半，可以超過上限，最多一倍半；
同一個真意第二份發動率多一半（鎮岳、金身改成多撐一回合），第三份起不再加。打仗、戰力、評分、修練頁同一條（traits.stack_value）。"""
import json

import pytest
from conftest import real_content

from tianxia import arts as arts_mod, howto, skillview, team, traits
from tianxia.martial_arts import Insight, generate_from_name
from tianxia.state import InsightFx


def _art(name, attribute="快", kind="武學"):
    return generate_from_name(name, kind, name, attribute=attribute).model_copy(update={"origin": "fused"})


def _ins(state, n, attribute, general=None, grand=None):
    """一份自己悟的意境，效果照 general／grand 寫死（不擲）。"""
    ins = Insight(id=f"悟:{n}", name=f"悟{n}", attribute=attribute)
    state.player.own_insights[ins.id] = ins
    state.player.insights.append(ins.id)
    state.player.insight_fx[ins.id] = InsightFx(general=general if general is not None else {attribute: 3}, grand=grand)
    return ins.id


def _wear(state, world, art, quality, slots):
    world.claim_skill_name(art)
    if art.kind == "內功":
        state.player.member.neigong_id = art.id
    else:
        state.player.member.wugong_id = art.id
    state.player.art_quality[art.id] = quality
    state.player.art_slots[art.id] = list(slots)
    return art


# ── 規則本身 ──

def test_one_copy_or_copies_under_the_cap_add_up_as_before():
    assert traits.stack_value([0.6], 0.5, 0.5, 1.5) == pytest.approx(0.5)
    assert traits.stack_value([0.1, 0.2], 0.5, 0.5, 1.5) == pytest.approx(0.3)
    assert traits.stack_value([0.3, 0.2], 0.5, 0.5, 1.5) == pytest.approx(0.5)


def test_past_the_cap_the_second_copy_counts_half_up_to_one_and_a_half():
    assert traits.stack_value([0.5, 0.5], 0.5, 0.5, 1.5) == pytest.approx(0.75)
    assert traits.stack_value([0.6, 0.6], 0.5, 0.5, 1.5) == pytest.approx(0.75)  # 每一份先夾在上限
    assert traits.stack_value([0.5, 0.5, 0.5], 0.5, 0.5, 1.5) == pytest.approx(0.75)  # 到頂
    assert traits.stack_value([0.4, 0.3], 0.5, 0.5, 1.5) == pytest.approx(0.55)  # 0.4＋0.3 的一半


def test_shares_say_how_much_each_copy_counted():
    assert traits.stack_shares([0.6, 0.6, 0.6], 0.5, 0.5, 1.5) == pytest.approx([1.0, 0.5, 0.0])
    assert [traits.share_word(x) for x in (0.5, 0.42, 0.0)] == ["算五成", "算四成", "不加"]


def test_stack_note_on_the_card():
    assert traits.stack_note([0.5], 0.5, 0.5, 1.5) == ""
    assert traits.stack_note([0.5, 0.5], 0.5, 0.5, 1.5) == "（兩份：第二份算五成・到頂）"
    assert traits.stack_note([0.5, 0.5, 0.5], 0.5, 0.5, 1.5) == "（三份：第二份算五成、第三份不加・到頂）"
    assert traits.stack_note([0.1, 0.1], 0.5, 0.5, 1.5) == "（兩份）"


# ── 打仗 ──

def test_two_copies_on_two_worn_arts_pass_the_old_cap(state, content, world):
    """上品三重的破甲一份就到上限（0.6 夾成 0.5）；兩門各一份：0.5＋0.5 的一半＝0.75，以前停在 0.5。"""
    _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛")])
    lo = traits.loadout(state, content, world)
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.5)
    _wear(state, world, _art("柔息功", "柔", kind="內功"), "上品", [_ins(state, 2, "剛")])
    lo = traits.loadout(state, content, world)
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.75)


def test_three_copies_stop_at_one_and_a_half(state, content, world):
    _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛"), _ins(state, 2, "剛"), _ins(state, 3, "剛")])
    lo = traits.loadout(state, content, world)
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.75)


def test_copies_under_the_cap_add_up_as_before(state, content, world):
    _wear(state, world, _art("裂石拳", "剛"), "下品", [_ins(state, 1, "剛", {"剛": 1}), _ins(state, 2, "剛", {"剛": 2})])
    lo = traits.loadout(state, content, world)
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.3)


def test_the_tactic_of_a_stacked_effect_uses_the_stacked_number():
    """先手上限五成；疊到一倍半，戰法的發動率是 75%（以前夾回 50%）。"""
    real = real_content()
    lo = traits.Loadout()
    lo.layers["big_win"] = 7.5
    (tac,) = traits.tactic_defs(real, lo)
    assert tac.name == "先手" and tac.rate == pytest.approx(0.75)
    lo.layers["big_win"] = 20
    assert traits.tactic_defs(real, lo)[0].rate == pytest.approx(0.75)


# ── 真意 ──

@pytest.fixture
def real():
    return real_content()


def _high(c, high_id):
    return next(h for h in c.traits.high if h.id == high_id)


def test_a_second_copy_of_a_chance_true_intent_fires_half_again_as_often(real):
    tac = _high(real, "liuguang").tactic
    assert traits.high_tactic(real, tac, 1) is tac
    assert traits.high_tactic(real, tac, 2).rate == pytest.approx(tac.rate * 1.5)
    assert traits.high_tactic(real, tac, 3).rate == pytest.approx(tac.rate * 1.5)  # 第三份起不加


def test_always_firing_true_intents_hold_one_more_round(real):
    zhenyue, jinshen = _high(real, "zhenyue").tactic, _high(real, "jinshen").tactic
    assert traits.high_tactic(real, zhenyue, 2).rounds == zhenyue.rounds + 1
    assert traits.high_tactic(real, zhenyue, 2).rate == zhenyue.rate
    assert traits.high_tactic(real, jinshen, 2).params["turns"] == jinshen.params["turns"] + 1
    assert traits.high_tactic(real, jinshen, 3).params["turns"] == jinshen.params["turns"] + 1


def test_the_same_true_intent_on_both_arts_counts_once_with_the_bonus(real, world):
    from tianxia.state import new_game_state

    state = new_game_state(real, "沈浪")
    _wear(state, world, _art("飛燕腿", "快"), "上品", [_ins(state, 1, "快", {}, "liuguang")])
    _wear(state, world, _art("疾風訣", "快", kind="內功"), "上品", [_ins(state, 2, "快", {}, "liuguang")])
    lo = traits.loadout(state, real, world)
    flows = [t for t in lo.highs if t.name == "流光"]
    assert len(flows) == 1 and flows[0].rate == pytest.approx(_high(real, "liuguang").tactic.rate * 1.5)


def test_the_card_names_the_second_true_intent(real):
    assert traits.high_note(_high(real, "liuguang").tactic, 1) == ""
    assert traits.high_note(_high(real, "liuguang").tactic, 2) == "（兩份：第二份多一半發動的機會）"
    assert traits.high_note(_high(real, "zhenyue").tactic, 2) == "（兩份：第二份多撐一回合）"
    assert traits.high_note(_high(real, "liuguang").tactic, 3) == "（三份：第二份多一半發動的機會，第三份起不加）"


# ── 戰力、評分（跟打仗同一條）──

def test_rating_bonus_counts_the_second_copy_half(state, content, world):
    cfg = content.config.arts
    art = _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛"), _ins(state, 2, "剛")])
    view = arts_mod.apply(state, content, world, team.player_art(state, content, world, art.id))
    assert view.copies == {"剛": [3, 3]}
    state.player.art_slots[art.id] = [state.player.art_slots[art.id][0]]
    alone = arts_mod.effect_bonus(content, arts_mod.apply(state, content, world, team.player_art(state, content, world, art.id)))
    state.player.art_slots[art.id] = ["悟:1", "悟:2"]
    both = arts_mod.effect_bonus(content, arts_mod.apply(state, content, world, team.player_art(state, content, world, art.id)))
    assert both - alone == pytest.approx(cfg.general_weight * 3 * cfg.stack_share)


def test_score_counts_the_second_copy_half(state, content, world):
    cfg = content.config.arts
    art = _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛")])
    alone = arts_mod.score(state, content, world, team.player_art(state, content, world, art.id))
    _ins(state, 2, "剛")
    state.player.art_slots[art.id] = ["悟:1", "悟:2"]
    both = arts_mod.score(state, content, world, team.player_art(state, content, world, art.id))
    colors = arts_mod.slot_colors(state, content, team.player_art(state, content, world, art.id))
    single = cfg.score_single_color if len(colors) > 1 and len(colors[1]) == 1 else 1.0
    assert both - alone == pytest.approx(cfg.score_per_layer * 3 * cfg.stack_share * single, abs=1)


def test_the_art_card_marks_the_second_copy(state, content, world):
    art = _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛"), _ins(state, 2, "剛")])
    view = arts_mod.apply(state, content, world, team.player_art(state, content, world, art.id))
    line = traits.card_line(content, view)
    assert "〔破甲〕" in line and "（兩份：第二份算五成・到頂）" in line


# ── 修練頁 ──

def test_the_slot_marks_the_second_copy_and_the_picker_warns(state, content, world):
    art = _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛"), _ins(state, 2, "剛")])
    mine = team.player_art(state, content, world, art.id)
    assert skillview.slot_stack_marks(state, content, world, mine) == {1: "破甲算五成"}
    third = _ins(state, 3, "剛")
    assert skillview.stack_hint(state, content, world, mine, third) == f"{skillview.STACK_RULE}：破甲已到頂，再裝不加"
    small = _ins(state, 4, "剛", {"剛": 1})
    state.player.art_slots[art.id] = ["悟:1"]
    mine = team.player_art(state, content, world, art.id)
    assert skillview.stack_hint(state, content, world, mine, small) == f"{skillview.STACK_RULE}：破甲算五成"
    other = _ins(state, 5, "柔")
    assert skillview.stack_hint(state, content, world, mine, other) == ""


def test_a_worn_art_looks_at_both_worn_arts(state, content, world):
    _wear(state, world, _art("裂石拳", "剛"), "上品", [_ins(state, 1, "剛")])
    inner = _wear(state, world, _art("柔息功", "柔", kind="內功"), "上品", [])
    mine = team.player_art(state, content, world, inner.id)
    assert skillview.stack_hint(state, content, world, mine, _ins(state, 2, "剛")) == f"{skillview.STACK_RULE}：破甲算五成，裝了就到頂"


def test_the_howto_says_the_rule(real):
    from tianxia.world_state import fresh_season

    text = howto.page(real, fresh_season(real), recruitable=False)
    line = next(l for l in text.splitlines() if "第二份起" in l)
    assert "算一半" in line and "一倍半" in line and "鎮岳、金身" in line and "多撐一回合" in line


# ── 網頁：伺服器寫好的字照畫 ──

def _web():
    import webharness

    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    from test_arts_pages_two import run

    return run


def test_the_slot_cell_the_picker_and_the_fit_button_show_the_server_words():
    run = _web()
    slot = {"id": "悟:2", "name": "悟二", "attribute": "剛", "skill": "破甲", "strength": 3, "fx": [], "look": "凡", "stack": "破甲算五成"}
    art = {"id": "a1", "slots": [None, slot], "colors": [[], []], "stack": {"悟:3": "破甲已到頂，再裝不加"}, "stack_rule": "同效果第二份起算一半，最多一倍半"}
    free = {"id": "悟:3", "name": "悟三", "attribute": "剛", "fx": [], "look": "凡"}
    html = run("S.slotPick = {art: 'a1', i: 0}; return H.slotsHtml(" + json.dumps(art, ensure_ascii=False) + ", {insights: ["
               + json.dumps(free, ensure_ascii=False) + "]});", fns=["slotsHtml"])
    assert '<small class="stk">破甲算五成</small>' in html
    assert '<p class="stk-rule">同效果第二份起算一半，最多一倍半</p>' in html and '<em class="stk">破甲已到頂，再裝不加</em>' in html
    card = {"id": "悟:3", "name": "悟三", "attribute": "剛", "look": "凡", "effects": [],
            "fits": [{"art": "a1", "name": "裂石拳", "i": 0, "stack": "同效果第二份起算一半，最多一倍半：破甲算五成"}]}
    html = run("return H.insightCardHtml(" + json.dumps(card, ensure_ascii=False) + ", {fits: true});", fns=["insightCardHtml"])
    assert '裝進【裂石拳】第 1 格</button><small class="stk">同效果第二份起算一半，最多一倍半：破甲算五成</small>' in html
