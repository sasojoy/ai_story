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
