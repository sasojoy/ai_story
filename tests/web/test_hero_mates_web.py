"""俠客頁「門下」一人一張卡（Joy 2026-10-26「裝備跟門下顯示優化」）：伺服器的 roster_cards（skillview.roster_cards）照名冊的順序
給本人、同伴、部下各一張（名字、本人／出戰／在門下、等級、氣血、身上兩門），網頁畫成卡，點一張在底下攤開戰法、加入移出、傳功，
卡頭已經寫了的（名字、等級、內功、武學、裝備）不再寫一次。正式內容；沒有 node 的網頁那幾條略過。"""
from __future__ import annotations

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import run

import server
import webharness
from tianxia import roster


def _game(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county", warm=True)
    for cid in ("liubei", "caocao"):
        assert world.try_recruit(cid, "沈浪", cap=3)
        roster._seed_starting_skills(world, cid, real.characters[cid])  # 同 roster.recruit 招到那一下
    g.state.player.team = ["liubei"]
    return g


def test_roster_cards_list_self_then_companions_with_their_arts(real, world):  # noqa: F811
    g = _game(real, world)
    cards = server.menxia_view(g)["roster_cards"]
    assert [(c["key"], c["role"]) for c in cards] == [("player", "本人"), ("liubei", "出戰"), ("caocao", "在門下")]
    me = cards[0]
    assert me["name"] == "沈浪" and me["level"] == g.state.player.member.level and 0 < me["hp"] <= me["hp_max"]
    assert [a["kind"] for a in me["arts"]] == ["內功", "武學"]
    liubei = cards[1]
    assert liubei["name"] == "劉備" and all(a["name"] and a["quality"] for a in liubei["arts"])


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")
def test_the_cards_draw_and_the_open_one_skips_what_its_head_already_says(real, world):  # noqa: F811
    g = _game(real, world)
    m = server.main_view(g)
    x = server.menxia_view(g)
    page = run(m, "return H.pagePractice();", menxia=x)
    sec = page.split('class="self-sec mates-sec"')[1].split("</section>")[0]
    assert "2 人・出戰 1 人" in sec and sec.count('class="mate ') == 3
    assert 'class="mate role-fight"' in sec and 'class="mate role-home"' in sec and "劉備" in sec and "曹操" in sec
    assert "mate-detail" not in sec  # 沒點誰：都收著
    x = server.menxia_view(g, "liubei")
    opened = run(m, "return H.pagePractice();", menxia=x, S={"person": "liubei"})
    detail = opened.split('class="mate-detail"')[1].split('<div class="mate ')[0]
    assert 'data-op="leave"' in detail and "內功　" not in detail and "第 1 級" not in detail and "<h3>" not in detail
    assert 'aria-expanded="true"' in opened.split('class="mate on role-fight"')[1].split("</button>")[0]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")
def test_a_lone_hero_gets_one_card_and_a_hint(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    page = run(server.main_view(g), "return H.pagePractice();", menxia=server.menxia_view(g))
    sec = page.split('class="self-sec mates-sec"')[1].split("</section>")[0]
    assert "還沒有同伴" in sec and sec.count('class="mate ') == 1 and "mates-none" in sec
