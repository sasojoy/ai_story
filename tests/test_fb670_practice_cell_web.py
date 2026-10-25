"""FB-670（企劃者 2026-10-22 選練功入口「丙」，PM 給號）：練功藏在探索卡最下面、城裡灰著看不到。行動列多一格「練功」，五格：
探索、練功、出陣、交友、移動。野外亮著寫「不限次數」、第二行照勝算上色；城裡灰著寫「城外才有」（城外沒有對手的地方寫「這裡沒有」，
PM 2026-10-22；照伺服器給的 note），整句（最近的在哪、
步行多久）在行動列底下那一行，照伺服器的 action_notes（Game._practice_line，見 tests/test_fb670_practice_cell.py），網頁不另寫判斷；
不帶路（按不下去）。探索卡回到真的三選一。五格每格約 62 px（320 寬約 51 px）：灰格小字最多四個字，長的原因格子寫短的、整句在底下那一行
（同 FB-664）；出陣的名字（「出陣・攪局」）只在「・」後面換行。序章與初入江湖照 reveal 的鍵（act:practice）亮，教學沒寫的步驟不畫。
node 排不了版：這裡看畫了什麼；375／320 寬切不切字在瀏覽器裡量，數字寫在試玩回饋 FB-670 那一列。沒有 node 就略過。
減法季批 1（整合設計 6.3【定】）起行動列回到四格（探索、出陣、交友、移動）：練功那一格只在序章與初入江湖（引導）時畫，平常收進「此地還能做」，
等批 2 把練功併進探索；行動列底下那幾行說明拿掉了，灰格點了浮出那一句（data-why）。這一份留下還成立的幾條。"""
from __future__ import annotations

import random
import re

import pytest
from conftest import classic_rules, real_content
from test_prologue_web import run, with_reveal

import server
import webharness
from tianxia import explore_modes, sortie
from tianxia import duel as duel_rules
from tianxia.engine import Game
from tianxia.models import REVEAL_KEYS
from tianxia.sqlite_world import open_world

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR
PRACTICE = "explore:practice"


# 城裡操練（新手引導重做，Config.training）開著時城裡那一格是操練、城外練功寫級數（tests/test_training.py）；
# 這一份測的是練功一格本身（操練關著），內容一律把它關掉

def _content(profile):
    c = real_content(profile)
    c.config.training.enabled = False
    return c


def _game(at, faction=None, profile="week7", classic=False):
    c = _content(profile)
    if classic:
        classic_rules(c)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _bar(m, **S):
    return run(m, "return H.actionBar(H.S.main);", S=S)


def _keys(bar):
    return re.findall(r'class="act-ink[^"]*" data-key="(\w+)"', bar)


def _cell(bar, key):
    return re.search(rf'<button class="act-ink[^"]*" data-key="{key}".*?</button>', bar, re.S).group(0)


def _sub(cell):
    return re.search(r"</b><small>(.*?)</small>", cell).group(1)


def _why(cell):
    return re.search(r'data-why="([^"]*)"', cell).group(1)


def _width(text):
    """格子小字的寬（以一個漢字為 1）：英數與空白算半個。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.5 for ch in text)


# ── 四格（減法季批 1） ─────────────────────────────────


def test_outside_the_guide_practice_waits_in_the_here_fold():
    bar = _bar(server.main_view(_game("yingshui")))
    assert _keys(bar) == ["explore", "train", "social", "move"] and "--cells:4" in bar
    fold = bar[bar.index("此地還能做"):]
    assert f'data-id="{PRACTICE}"' in fold


PLACES = [  # (陣營, 地點)：城裡、野外、戰線、自家大營、頭目、名望不夠、散人站在戰線上
    (None, "yingchuan"), (None, "yingshui"), (None, "changshe"), (None, "luoyang_road"), (None, "wan_city"),
    (None, "dajiangjun_fu"), (None, "mengjin_ford"), (None, "jade_cave"), ("guan", "changshe"), ("guan", "guan_camp"),
    ("huang", "huangjin_camp"), ("huang", "julu_altar"), ("huang", "changshe"), ("guan", "yingchuan_wilds"),
]


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_every_grey_cell_says_at_most_four_characters(profile):
    seen = set()
    for faction, at in PLACES:
        bar = _bar(server.main_view(_game(at, faction, profile)))
        assert "practice" not in _keys(bar), (at, faction)
        for off in re.findall(r'<button class="act-ink[^"]* off".*?</button>', bar, re.S):
            assert _width(_sub(off)) <= 4, (profile, at, faction, off)
            seen.add(_sub(off))
    assert {"未投靠", "名望不夠", "不在戰線", "沒有人"} <= seen  # 真的量到了這幾種灰格


def test_the_long_reasons_go_to_the_tap():
    """散人站在戰線上：格子「未投靠」，「散人不能出陣」整句是伺服器寫的出陣那一句；名望不夠：格子「名望不夠」，還差多少在點了浮出的那一句。"""
    game = _game("changshe")
    m = server.main_view(game)
    social = next(o for o in m["options"] if o["id"] == "act:socialize")
    gap = social["label"].split("（", 1)[1].removesuffix("）")
    assert not social["enabled"] and gap.startswith("名望還差 ")  # 前提
    bar = _bar(m)
    assert "<b>出陣</b><small>未投靠</small>" in _cell(bar, "train") and "<b>交友</b><small>名望不夠</small>" in _cell(bar, "social")
    assert _why(_cell(bar, "train")) == m["action_notes"]["act:train"] and _why(_cell(bar, "train")).startswith(sortie.RANGER_NOTE)
    assert _why(_cell(bar, "social")) == f"{gap}。"


# ── 舊季、序章與初入江湖 ─────────────────────────────


def test_an_old_season_without_practice_keeps_four_cells():
    game = _game("yingshui")
    game.state.world.precise_actions = False  # 一類一顆沒蓋章：沒有練功
    bar = _bar(server.main_view(game))
    assert "practice" not in _keys(bar) and "--cells:4" in bar


def test_practice_is_a_reveal_key_of_its_own():
    assert "act:practice" in REVEAL_KEYS
    m = server.main_view(_game("yingshui"))
    others = ["act:explore", "act:train", "act:social", "act:move"]
    assert "practice" not in _keys(_bar(with_reveal(m, others)))
    assert _keys(_bar(with_reveal(m, [*others, "act:practice"]))) == ["explore", "practice", "train", "social", "move"]
    assert "practice" in _keys(_bar(with_reveal(m, ["all"])))


def test_the_tutorial_only_draws_the_cell_from_a_step_that_reveals_it():
    """序章（草廬）與初入江湖（出了草廬那四步）照教學內容的 reveal：寫了 act:practice 的那一步起才畫，沒寫就不畫，
    也不掉進「此地還能做」。初入江湖走完（onboard 是 None）才全亮。照正式內容的每一步算，教學改了也抓得到。"""
    c = _content("week7")
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.stamina = "yingchuan", 250.0
    t = c.tutorial
    lit = False
    for step in range(t.prologue_steps, len(t.steps)):
        p.tutorial_step = step
        lit = lit or "act:practice" in t.steps[step].reveal or "all" in t.steps[step].reveal
        m = server.main_view(game)
        assert m["onboard"] and any(o["id"] == PRACTICE for o in m["options"]), t.steps[step].id
        bar = _bar(m)
        assert ("practice" in _keys(bar)) is lit, t.steps[step].id
        assert PRACTICE not in bar.replace(_cell(bar, "practice"), "") if lit else PRACTICE not in bar, t.steps[step].id
    p.tutorial_step = len(t.steps)
    m = server.main_view(game)
    bar = _bar(m)
    assert m["onboard"] is None and "practice" not in _keys(bar) and PRACTICE in bar  # 走完：收進「此地還能做」


def test_the_hut_never_has_a_practice_option():
    """草廬裡（序章）探索不展開、也沒有練功（_explore_mode_options 在序章是空的）：格子不會在序章冒出來。"""
    c = _content("week7")
    c.config.jianfa.enabled = False  # 減法季的新角色不進草廬（開局第一分鐘）：這一條測的是草廬本身
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world(), prologue=True)
    game.client = None
    m = server.main_view(game)
    assert m["prologue"] is not None and PRACTICE not in [o["id"] for o in m["options"]]
    assert explore_modes.option_id(explore_modes.PRACTICE) == PRACTICE
