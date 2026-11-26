"""俠客頁重排（web/xiake.js）：開關開著時俠客頁換成人像、眼下一張卡、六面牌；點一面拉起那一塊（內容照舊是原本那一頁）；
同伴那一塊排成立繪方格、點一位拉起他的卡。正式內容；沒有 node 的略過。"""
from __future__ import annotations

import re

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import run

import server
import webharness
from tianxia import roster

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _game(real, world, mates=("liubei", "caocao")):  # noqa: F811
    real.config.xiake.enabled = True
    g = _player(real, world, "沈浪", "guan", "zhuo_county", warm=True)
    for cid in mates:
        assert world.try_recruit(cid, "沈浪", cap=3)
        roster._seed_starting_skills(world, cid, real.characters[cid])
    g.state.player.team = list(mates[:1])
    return g


def test_status_carries_the_switch_and_the_faces(real, world):  # noqa: F811
    g = _game(real, world)
    xk = server.main_view(g)["xiake"]
    assert xk["on"] is True and xk["faces"]["liubei"].endswith("/liubei.webp")
    g.state.player.bot = True
    assert "xiake" not in server.main_view(g)


def test_main_view_draws_hero_eye_and_one_plaque_per_tab(real, world):  # noqa: F811
    g = _game(real, world)
    g.state.player.stat_points = 3
    m, x = server.main_view(g), server.menxia_view(g)
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.startswith('<div class="xk-page">')
    assert 'class="hero-tabs"' not in page  # 那一排小分頁不畫
    assert "<h1>沈浪</h1>" in page and 'class="xk-fig"' in page
    eye = page.split('aria-label="眼下"')[1].split("</section>")[0]
    assert "還有 3 點可配" in eye and 'data-sec="attrs"' in eye  # 鈕在卡上：拉起屬性那一塊
    plaques = re.findall(r'data-act="xk-open" data-sec="(\w+)"><i', page)
    assert plaques[:3] == ["arts", "gear", "mates"] and "attrs" in plaques
    assert "出戰 1・共 2" in page  # 同伴那面牌上的一行


def test_a_plaque_pulls_up_its_page(real, world):  # noqa: F811
    g = _game(real, world)
    m, x = server.main_view(g), server.menxia_view(g)
    page = run(m, "return H.pagePractice();", menxia=x, S={"xkSec": "gear", "heroTab": "gear", "xkSeen": "gear"})
    assert '<div class="xk-page open">' in page and 'class="xk-sheet sec-gear"' in page
    assert "gear-sec" in page and "<h3>裝備</h3>" not in page  # 原本那一頁的內容；小標題不寫第二次
    assert 'data-act="xk-close"' in page


def test_a_jump_from_elsewhere_opens_that_sheet(real, world):  # noqa: F811
    """狀態列的名號、江湖錄的連結照舊只設 S.heroTab：這裡看到它變了就拉起那一塊。"""
    g = _game(real, world)
    page = run(server.main_view(g), "return H.pagePractice();", menxia=server.menxia_view(g), S={"heroTab": "attrs"})
    assert 'class="xk-sheet sec-attrs"' in page


def test_mates_are_portrait_tiles_and_a_tap_pulls_up_the_card(real, world):  # noqa: F811
    g = _game(real, world)
    m = server.main_view(g)
    S = {"xkSec": "mates", "heroTab": "mates", "xkSeen": "mates"}
    page = run(m, "return H.pagePractice();", menxia=server.menxia_view(g), S=S)
    tiles = page.split('class="xk-mates"')[1]
    assert len(re.findall(r'class="xk-mt[ "]', tiles)) == 2 and "/liubei.webp" in tiles and 'class="xk-mt fight"' in tiles
    opened = run(m, "return H.pagePractice();", menxia=server.menxia_view(g, "liubei"), S={**S, "person": "liubei"})
    card = opened.split('class="sheet xk-card"')[1]
    assert "劉備" in card and 'data-op="leave"' in card and 'data-act="person" data-key="liubei"' in card


def test_a_lone_hero_gets_a_line_not_tiles(real, world):  # noqa: F811
    g = _game(real, world, mates=())
    S = {"xkSec": "mates", "heroTab": "mates", "xkSeen": "mates"}
    page = run(server.main_view(g), "return H.pagePractice();", menxia=server.menxia_view(g), S=S)
    if 'class="xk-sheet' in page:  # 同伴那一塊還沒長出來的角色：收起來
        assert "還沒有同伴" in page and 'class="xk-mates"' not in page


def test_off_keeps_the_old_tabs(real, world):  # noqa: F811
    g = _game(real, world)
    real.config.xiake.enabled = False
    page = run(server.main_view(g), "return H.pagePractice();", menxia=server.menxia_view(g))
    assert "xk-page" not in page and 'class="hero-tabs"' in page
