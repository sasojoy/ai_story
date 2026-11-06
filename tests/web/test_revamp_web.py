"""介面重整（2026-11-05，Joy「操作簡單 回饋直覺 畫面有質感」，挑「四塊一次做」）的網頁那一半：江湖頁閒著時是場景卡、要事一張卡、
四顆行動、此地可為一排圓章、此地人物一排；點大勢人物打開「點人物之後」（交談、護衛、往來紀錄）；跟人物說話整頁換成浮在最上層的對話框；
俠客頁四分頁、身上那一門的抽屜能當場換；管理頁四格狀態、分頁籤、危險區長按。真的引擎（正式內容 week7）給的 /api/main。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_prologue_web import run as run_classic

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def run(m, script, *, S=None, menxia=None):
    return run_classic(m, script, S=S, menxia=menxia)


@pytest.fixture
def wan(world):
    """正式內容 week7、開了季、站在大將軍府（何進在）、投靠官軍、名望夠求見。"""
    content = real_content("week7")
    world.seed_first_season(content)
    world.open_season(content, now=0.0)
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world, graduated=True)
    game.state.player.location = "dajiangjun_fu"
    game.state.player.faction = "guan"
    game.state.player.stats["fame"] = 200
    game.state.pending_event = None  # 開局那一則（opening_gate）先放下
    for _ in range(4):  # 開季準備（挑成長配比……）做完，回到閒著的選單
        ids = [o.id for o in game.options(odds=False) if o.enabled]
        if "act:explore" in ids:
            break
        game.choose(next(i for i in ids if i != "growth:custom"))
    return game


def test_the_idle_page_has_the_duty_card_the_seal_row_and_the_people_row(wan):
    m = server.main_view(wan)
    figs = {f["id"]: f for f in m["figures_here"]}
    assert figs["hejin"]["talk"]["via"] == ["act:call", "call:hejin"] and figs["hejin"]["side"] == "官軍"  # 兩位人物：先打開名單再指名
    page = run(m, "return H.pageJianghu();")
    assert 'class="card scene rv' in page and 'class="act-bar"' in page
    assert "此地還能做" not in page  # 摺疊換成了此地可為那一排
    assert 'class="here-row"' in page and 'class="people-row"' in page
    assert 'data-act="fig-open" data-id="hejin"' in page
    assert "hire:" not in page.split('class="here-row"')[1]  # 招募不在此地可為（搬去酒肆）
    assert "aid:guard:" not in page.split('class="here-row"')[1]  # 護衛在點了人物之後
    assert "/static/img/acts/explore.webp" in page


def test_tapping_a_figure_offers_talk_guard_and_the_log(wan):
    m = server.main_view(wan)
    page = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();')
    pick = page.split('class="vn-layer pick"')[1]
    assert 'data-act="fig-talk" data-id="hejin"' in pick and 'data-act="fig-log" data-id="hejin"' in pick
    assert "護衛" in pick
    assert "/static/img/figures/full/hejin.webp" in pick


def test_talking_to_a_figure_draws_the_overlay_with_the_same_options(wan):
    m = server.main_view(wan)
    m["talk"] = {"id": "zhujun", "name": "朱儁", "side": "官軍", "affinity": 7, "face": "/static/img/figures/full/zhujun.webp"}
    m["options"] = [{"id": "talk:0", "label": "「請將軍指點。」", "enabled": True}, {"id": "talk:say", "label": "自己說…", "enabled": True},
                    {"id": "talk:leave", "label": "告辭", "enabled": True}]
    m["scene"] = "<p><strong>朱儁</strong>（情誼 7）</p>\n<p>「你來了。」</p>"
    m["art"] = None
    page = run(m, "return H.pageJianghu();")
    assert 'class="vn-layer talk"' in page
    assert 'data-id="talk:0"' in page and 'data-id="talk:leave"' in page
    assert "「你來了。」" in page and "（情誼 7）" not in page  # 名字在名牌上、情誼在框底，不寫第二次
    assert "情誼 7" in page


def test_the_log_groups_by_day_and_shows_affinity_gains(wan):
    m = server.main_view(wan)
    log = {"id": "zhujun", "name": "朱儁", "face": None, "affinity": 9, "meets": 1, "more": False, "season": "now", "lines": [
        {"id": 2, "stamp": "第 3 天 08:10", "place": "宛城", "role": "assistant", "text": "「坐。」", "gain": 5},
        {"id": 1, "stamp": "第 3 天 08:10", "place": "宛城", "role": "user", "text": "「將軍。」", "gain": 0},
    ]}
    page = run(m, f"H.S.figLog = {__import__('json').dumps(log, ensure_ascii=False)}; return H.pageJianghu();")
    body = page.split('class="vn-layer log"')[1]
    assert "第 3 天・宛城" in body and "情誼 +5" in body
    assert body.index("「將軍。」") < body.index("「坐。」")  # 同一天照說話的先後


def test_the_hero_page_has_four_tabs_and_the_worn_drawer_lists_swaps(wan):
    m, x = server.main_view(wan), server.menxia_view(wan)
    page = run(m, "return H.pagePractice();", menxia=x)
    for key in ("arts", "gear", "mates", "attrs"):
        assert f'data-act="hero-tab" data-tab="{key}"' in page
    worn = next(a for a in x["owned_arts"] if a["worn"])
    drawer = run(m, f'H.S.pdrawer = {{ t: "worn", key: "{worn["kind"]}" }}; return H.pagePractice();', menxia=x)
    assert "換一門" in drawer or "功法庫裡沒有別的" in drawer
    attrs = run(m, 'H.S.heroTab = "attrs"; return H.pagePractice();', menxia=x)
    assert "經驗與成長" in attrs


def test_the_admin_page_has_tiles_tabs_and_a_hold_to_confirm_danger_zone(wan):
    wan.state.player.name = "Rayal"
    m = server.main_view(wan)
    page = run(m, "return H.adminHtml();", S={"admin": server.admin_choices(wan)})
    assert len(__import__("re").findall(r'class="ad-tile( hot)?"', page)) == 4 and 'data-act="ad-tab"' in page
    assert 'data-act="ad-hold" data-op="end_season"' in page and 'data-act="ad-hold" data-op="next_season"' in page
    assert 'data-act="admin" data-op="end_season"' not in page  # 收季只在危險區、要長按
