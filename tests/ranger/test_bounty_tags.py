"""21 天季懸賞的賞拆成小籤（企劃者挑第 5 批畫面第三組丙）：江湖頁懸賞卡、懸賞榜放大的紙一樣一格，告示右上角一個寫銀兩的小朱印。
字與數字照伺服器給的（bounties.reward_tags）；週末與 14 天的季照舊那一行，一個字都不變。"""
from __future__ import annotations

import pytest
from test_season21_daily import _first, _game

import server
import webharness
from tianxia import bounties, shopview

TOWN = "wan_city"


def _ranger(profile="season21"):
    game = _game(profile)
    p = game.state.player
    p.faction, p.location = None, TOWN
    p.member.level = 20
    return game


def test_season21_tags_split_the_same_reward_as_the_line():
    game = _ranger()
    s, c = game.state, game.content
    b = _first(s, "strike")
    tags = bounties.reward_tags(s, c, b)
    text = bounties.reward_text(s, c, b)
    assert tags[0] == {"k": "銀", "v": "120"} and tags[1]["k"] == "經驗"
    assert text.startswith(f"賞銀 120・經驗 {tags[1]['v']}")
    gift = next(t for t in tags if t.get("kind") == "gift")
    assert gift["v"] == bounties.ATTACH_NOTES["strike"].removeprefix("・") and gift["v"] in text
    assert bounties.level_note(s, c, b) == "賞照你第 20 級"


def test_a_prize_gets_its_own_red_tag():
    game = _ranger()
    s, c = game.state, game.content
    b = _first(s, "strike")
    b.prize = "treasure"
    assert bounties.reward_tags(s, c, b)[-1] == {"v": "重賞：寶物一件", "kind": "prize"}


@pytest.mark.smoke
def test_the_board_notes_carry_the_corner_and_tags():
    game = _ranger()
    game.choose("act:bounties")
    view = shopview.board_view(game.state, game.content, game.world)
    note = next(n for n in view["notes"] if n["kind"] == "strike")
    assert note["corner"] == "120" and note["tags"][0]["v"] == "120" and note["level"] == "賞照你第 20 級"


# ── 網頁 ──

web = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@web
def test_the_card_draws_one_tag_per_reward():
    from test_prologue_web import run, with_reveal

    game = _ranger()
    b = _first(game.state, "strike")
    game.choose("act:bounties")
    game.choose(f"bounty:take:{b.id}")
    game.choose("bounty:back")
    m = with_reveal(server.main_view(game), ["all"])
    html = run(m, "return H.pageJianghu();")
    assert 'class="rtags"' in html and '<span class="rtag"><em>銀</em>120</span>' in html
    assert 'class="rtag gift"' in html and "賞照你第 20 級" in html


@web
def test_the_board_note_has_a_seal_and_the_paper_has_tags():
    from test_shop2_web import _click
    from test_shop2_web import run as shop_run

    game = _ranger()
    game.choose("act:bounties")
    m = server.main_view(game)
    note = next(n for n in m["shop"]["notes"] if n["kind"] == "strike")
    out = shop_run(m, "return (async () => { H.render(); " + _click('{ act: "board-zoom", id: "' + note["id"] + '" }')
                   + " return T.els.app.innerHTML; })();")
    assert '<i class="corner">120</i>' in out and 'class="rtags"' in out and "賞照你第 20 級・" in out
    assert '<p class="reward">' not in out


# ── FB-390、FB-391（QA 5b）──


def test_the_notice_face_carries_a_short_gift_and_the_prize():
    """FB-391：草圖丙的告示正面在朱印之外還有一格附贈（金框，紙上那一格的短寫）；有重賞時再一格。只在 21 天季。"""
    game = _ranger()
    s = game.state
    b = _first(s, "strike")
    b.prize = "treasure"
    game.choose("act:bounties")
    view = shopview.board_view(s, game.content, game.world)
    note = next(n for n in view["notes"] if n["id"] == b.id)
    assert note["gift"] == "＋二階" and note["prize_chip"] == "重賞"
    scout = next(n for n in view["notes"] if n["kind"] == "scout")
    assert scout["gift"] == f"＋{game.content.config.stamina_pill_name}" and scout["prize_chip"] == ""


@web
def test_the_notice_face_draws_the_gift_cell():
    from test_shop2_web import run as shop_run

    game = _ranger()
    game.choose("act:bounties")
    m = server.main_view(game)
    html = shop_run(m, "H.render(); return T.els.app.innerHTML;")
    assert '<span class="extra"><span class="gift">＋二階</span>' in html


def test_the_held_seal_moves_further_left_on_wide_screens():
    """FB-390：寬過 641px 時「已揭」換成 13px，揭著的朱印照新的字寬往左讓（手機也從 34px 挪到 38px：量到壓了 3px）。"""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[2] / "web" / "style.css").read_text(encoding="utf-8")
    phone, wide = css.split("@media (min-width: 641px)", 1)[0], css.split("@media (min-width: 641px)", 1)[1]
    assert ".shop-board .note.held .corner { right: 38px; }" in phone
    assert ".shop-board .note.held .corner { right: 46px; }" in wide
