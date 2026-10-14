"""回饋單甲批（PM 2026-10-14；企劃者「先不用等～都先做～之後再回頭潤字」）：裝備、店面、紀錄、版面的幾張小單。新寫的字都待 joy 潤。"""
from __future__ import annotations

import random

import pytest
from test_weapons import _blade, _game, _new_state, _on, _town

from tianxia import team, weapons

ATTRS = "剛柔快慢陰陽虛實"


# ── FB-127：兵器的字 ──


def test_fb127_only_a_blade_is_said_to_have_a_blade_edge(content, world):
    """拳套、弩、棍沒有刀口：鈍了的提醒照種類換字；只有刀寫「刀口」。"""
    _on(content)
    state = _new_state(content, world, "鈍拳")
    lines = {}
    for kind in ("劍", "刀", "槍", "棍", "弓弩", "拳腳"):
        state.player.weapon, state.player.edge_warned = _blade(kind=kind, edge=30), False
        [lines[kind]] = weapons.wear(state, content, "落敗")
    assert all(("刀口" in line) == (kind == "刀") for kind, line in lines.items()), lines
    assert "拳套" in lines["拳腳"] and "弩" in lines["弓弩"]


def test_fb127_a_full_edge_does_not_say_blade_edge_for_a_fist(content, world):
    game = _town(content, world)
    game.state.player.weapon = _blade(kind="拳腳", edge=100)
    problem = weapons.repair_problem(game.state, content)
    assert problem is not None and "刀口" not in problem


def test_fb127_the_mismatch_names_the_piece_not_the_kind(content, world):
    """「這把拳腳用不上你的劍法」：拳腳是種類名，東西是一副拳套。"""
    _on(content)
    game = _game(content, world)
    art = team.resolve_art("sword", content, world)
    game.state.player.weapon = _blade(kind="拳腳")
    line = weapons.card_line(game.state, content, world, art)
    assert "這副拳套用不上你的劍法" in line and "這把拳腳" not in line
    game.state.player.weapon = _blade(kind="弓弩")
    assert "這把弩用不上你的劍法" in weapons.card_line(game.state, content, world, art)


def test_fb127_a_clashing_blade_says_so_instead_of_a_bare_plus_zero(content, world):
    """配得上、屬性卻跟武學相剋：一階下品的加成正好抵掉，寫「威力 +0%」像沒配上。補一句相剋（角色卡與修練頁那一列）。"""
    _on(content)
    game = _game(content, world)
    art = team.player_art(game.state, content, world, game.state.player.member.wugong_id)
    clash = next(a for a in ATTRS if weapons.counters(a, art.attribute) or weapons.counters(art.attribute, a))
    game.state.player.weapon = _blade(kind=weapons.art_weapon(art.id, content, world), attribute=clash)
    line = weapons.card_line(game.state, content, world, art)
    assert "威力 +0%" in line and weapons.CLASH_NOTE in line
    row = weapons.rows(game.state, content, world, art)["worn"]
    assert row["bonus"] == "+0%" + weapons.CLASH_NOTE
    game.state.player.weapon = _blade(kind=weapons.art_weapon(art.id, content, world), attribute=art.attribute)
    assert weapons.CLASH_NOTE not in weapons.card_line(game.state, content, world, art)


def test_fb127_the_practice_rows_carry_the_piece_noun(content, world):
    """修練頁、人物面板、店面裝備庫那幾處寫的種類：伺服器給 noun（拳套、弩），網頁照它寫，不寫種類名（拳腳、弓弩）。"""
    _on(content)
    game = _game(content, world)
    art = team.player_art(game.state, content, world, game.state.player.member.wugong_id)
    game.state.player.weapon = _blade(kind="拳腳")
    assert weapons.rows(game.state, content, world, art)["worn"]["noun"] == "拳套"


def test_fb127_the_practice_page_writes_the_noun(hints_content, world):
    import webharness
    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    from test_prologue_web import run
    from test_weapons_web import _gear, _row, _weapons_block

    import server
    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m, x = server.main_view(game), server.menxia_view(game)
    x["gear"] = _gear(weapon={"worn": _row(kind="拳腳", noun="拳套", grade="一階下品", confirm=""),
                              "rack": [_row(id="兵:2", kind="弓弩", noun="弩", grade="一階下品", confirm="")]})
    block = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert "拳套・屬柔" in block and "弩・屬柔" in block and "拳腳" not in block and "弓弩" not in block


# ── FB-133、FB-160：種類字與量詞一致（拳套／拳腳、弩／弓弩；拳套論「副」） ──


def _piece(kind="拳腳", **over):
    from tianxia.state import Weapon
    return Weapon(**{"id": "兵:9", "name": "綿羽護手", "kind": kind, "attribute": "剛", "tier": 1, "quality": "中品", **over})


def test_fb133_the_forge_result_writes_the_noun_and_its_measure_word():
    """打出來的結果句寫「拳腳」「弓弩」，挑種類與開爐鈕寫「拳套」「弩」：結果句也寫拳套、弩；拳套論副。"""
    from tianxia import smithing

    fist = smithing.forged_head(_piece("拳腳"), "兩份精鐵砂")
    assert "一副" in fist and "拳套" in fist and "拳腳" not in fist and "一把" not in fist
    bow = smithing.forged_head(_piece("弓弩", name="驚弦弩"), "兩份精鐵砂")
    assert "一把" in bow and "弩・" in bow and "弓弩" not in bow


def test_fb133_buying_and_picking_up_a_fist_says_a_pair(content, world):
    game = _town(content, world)
    game.choose("act:smith")
    assert "買下一副【厚背拳套】" in game.choose("smith:buy:拳腳")[0]
    assert weapons.DROP_LINE.format(unit=weapons.unit("拳腳"), name="厚背拳套") == "撿到一副【厚背拳套】"


def test_fb133_the_old_smithy_menu_writes_nouns(content, world):
    """店面開關關著的舊選單：買鈕的括號寫「弩」「拳套」，不寫「弓弩」「拳腳」。"""
    content.config.shop_screens = False
    game = _town(content, world)
    game.choose("act:smith")
    labels = {o.id: o.label for o in game.options(odds=False)}
    assert "（弩・一階" in labels["smith:buy:弓弩"] and "（拳套・一階" in labels["smith:buy:拳腳"]
    assert not any("弓弩" in label or "拳腳" in label for label in labels.values())


def test_fb133_the_dismantle_question_says_the_tempering_goes_too(content):
    """鈕上寫「（一階中品・淬煉 5）」，確認框只寫「（一階中品）」：淬過的次數會一起沒了，確認框該提醒。"""
    from tianxia import equipment

    ask = equipment.dismantle_confirm(content, _piece(tempers=5))
    assert "淬煉 5 次" in ask
    assert "淬煉" not in equipment.dismantle_confirm(content, _piece())


def test_fb133_stepping_back_says_so_before_asking_again(content, world):
    """「上一步」只回下一步的問句，讀起來像同一個問題問了兩次：先回一句退回了。這一句也算單子自己的回話（開爐成了收掉）。"""
    from tianxia import smithing
    from tianxia.state import SmithDraft

    _on(content)
    state = _new_state(content, world, "退步")
    state.player.smith_draft = SmithDraft(kind="劍", main="gang_1")
    assert smithing.step(state, content, "forge-undo", "") == [smithing.UNDONE, smithing.ASK_MAIN]
    assert smithing.is_step_line(smithing.UNDONE)


def test_fb160_a_fist_bounty_asks_for_a_pair():
    from tianxia import bounties
    from tianxia.state import Bounty

    fist = Bounty(id="b1", kind="arms", faction="guan", week=1, silver=0, deeds=2, attribute="剛", weapon_kind="拳腳", expires=0.0)
    assert "交出一副屬剛的拳套" in bounties.how(None, fist) and bounties.unit_of(fist) == "副"
    bow = fist.model_copy(update={"weapon_kind": "弓弩"})
    assert "交出一把屬剛的弩" in bounties.how(None, bow) and bounties.unit_of(bow) == "把"
    art = fist.model_copy(update={"kind": "art", "weapon_kind": None})
    assert bounties.unit_of(art) == "門"
