"""FB-670（企劃者 2026-10-22 選練功入口「丙」，PM 給號）：練功藏在探索卡最下面、城裡灰著看不到。行動列多一格「練功」，五格：
探索、練功、出陣、交友、移動。野外亮著寫「不限次數」、第二行照勝算上色；城裡灰著寫「城外才有」（城外沒有對手的地方寫「這裡沒有」，
PM 2026-10-22；照伺服器給的 note），整句（最近的在哪、
步行多久）在行動列底下那一行，照伺服器的 action_notes（Game._practice_line，見 tests/test_fb670_practice_cell.py），網頁不另寫判斷；
不帶路（按不下去）。探索卡回到真的三選一。五格每格約 62 px（320 寬約 51 px）：灰格小字最多四個字，長的原因格子寫短的、整句在底下那一行
（同 FB-664）；出陣的名字（「出陣・攪局」）只在「・」後面換行。序章與初入江湖照 reveal 的鍵（act:practice）亮，教學沒寫的步驟不畫。
node 排不了版：這裡看畫了什麼；375／320 寬切不切字在瀏覽器裡量，數字寫在試玩回饋 FB-670 那一列。沒有 node 就略過。"""
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


def _game(at, faction=None, profile="week7", classic=False):
    c = real_content(profile)
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


def _rows(bar):
    block = re.search(r'<div class="act-notes">(.*?)</div>', bar, re.S)
    return re.findall(r"<p><b>(.*?)</b>(.*?)</p>", block.group(1)) if block else []


def _width(text):
    """格子小字的寬（以一個漢字為 1）：英數與空白算半個。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.5 for ch in text)


# ── 五格 ─────────────────────────────────


def test_the_wild_shows_five_cells_with_practice_lit_beside_explore():
    game = _game("yingshui")
    m = server.main_view(game)
    bar = _bar(m)
    assert _keys(bar) == ["explore", "practice", "train", "social", "move"]
    assert 'class="act-bar" role="group" aria-label="行動" style="--cells:5"' in bar
    cell = _cell(bar, "practice")
    assert 'data-act="choose" data-id="explore:practice"' in cell and " off" not in cell
    assert '<b>練功</b><small>不限次數</small><small class="ink-note good">穩勝</small>' in cell
    rows = _rows(bar)
    assert ("練功", m["action_notes"][PRACTICE]) in rows  # 底下那一行是伺服器那一句
    assert [name for name, _ in rows][:2] == ["探索", "練功"]  # 照格子的順序


def test_the_explore_card_is_back_to_three():
    bar = _bar(server.main_view(_game("yingshui")), wheelSel="explore")
    card = re.search(r'<div class="card act-explore">.*?</div></div>', bar, re.S).group(0)
    assert all(f'data-id="explore:{mode}"' in card for mode in ("gather", "seek", "sense"))
    assert PRACTICE not in card and "練功" not in card
    assert bar.count(f'data-id="{PRACTICE}"') == 1  # 只有行動列那一格
    assert "此地還能做" not in bar or PRACTICE not in bar[bar.index("此地還能做"):]


def test_in_town_the_cell_is_grey_and_the_row_below_says_where_and_how_far():
    game = _game("yingchuan")
    m = server.main_view(game)
    note = m["action_notes"][PRACTICE]
    assert note.startswith("城外才有對手，最近的在潁水河畔（步行約 ")  # 伺服器那一句（tests/test_fb670_practice_cell.py）
    bar = _bar(m)
    assert _keys(bar) == ["explore", "practice", "train", "social", "move"]  # 出陣那一格在城裡照舊灰著寫「不在戰線」
    cell = _cell(bar, "practice")
    assert '<button class="act-ink off" data-key="practice"' in cell and " disabled>" in cell and "data-id" not in cell  # 不帶路
    assert "<b>練功</b><small>城外才有</small>" in cell and "ink-note" not in cell
    assert ("練功", note) in _rows(bar)


@pytest.mark.parametrize("faction, at, word", [
    (None, "yingchuan", "城外才有"),  # 城鎮
    ("guan", "guan_camp", "這裡沒有"),  # 自家大營：不是城鎮、沒有對手
    ("huang", "huangjin_camp", "這裡沒有"),
    (None, "jade_cave", "這裡沒有"),
])
def test_a_grey_cell_says_outside_the_walls_only_in_town(faction, at, word):
    """PM 2026-10-22（FB-670 回覆第 1 條）：城鎮寫「城外才有」；城外、沒有對手的地方（自家大營、黃巾營寨、玉洞、草廬）人已經在城外，
    寫「這裡沒有」。是不是城鎮照伺服器的判斷（練功鈕的 note，explore_modes.is_town），網頁不另寫。"""
    m = server.main_view(_game(at, faction))
    option = next(o for o in m["options"] if o["id"] == PRACTICE)
    assert not option["enabled"] and option["note"] == word
    assert f"<b>練功</b><small>{word}</small>" in _cell(_bar(m), "practice")


def test_the_grey_cells_word_is_the_servers():
    """格子的字照伺服器給的那一個（練功鈕的 note）：伺服器換了就照換；舊版伺服器沒給（note 是空的）寫「城外才有」。"""
    m = server.main_view(_game("guan_camp", "guan"))
    option = next(o for o in m["options"] if o["id"] == PRACTICE)
    option["note"] = "伺服器"
    assert "<b>練功</b><small>伺服器</small>" in _cell(_bar(m), "practice")
    option["note"] = ""
    assert "<b>練功</b><small>城外才有</small>" in _cell(_bar(m), "practice")


def test_the_row_below_is_only_ever_the_servers_sentence():
    """網頁不另寫判斷：伺服器那一句換了，底下就照換；伺服器沒給（舊版）就不畫那一行，格子照畫。"""
    m = server.main_view(_game("yingchuan"))
    m["action_notes"][PRACTICE] = "伺服器換了一句"
    assert ("練功", "伺服器換了一句") in _rows(_bar(m))
    m["action_notes"].pop(PRACTICE)
    bar = _bar(m)
    assert "練功" not in [name for name, _ in _rows(bar)] and "<b>練功</b><small>城外才有</small>" in _cell(bar, "practice")


def test_a_boss_only_place_lights_the_cell_for_the_boss_and_greys_it_while_he_is_away():
    game = _game("julu_altar", faction="huang")
    s, c = game.state, game.content
    bar = _bar(server.main_view(game))
    cell = _cell(bar, "practice")
    assert "<b>練功</b><small>對上頭目</small>" in cell and "ink-note" not in cell and " off" not in cell
    s.player.duel_last = [float(s.player.season_number), s.world.time]  # 冷卻中
    m = server.main_view(game)
    bar = _bar(m)
    assert "<b>練功</b><small>頭目不在</small>" in _cell(bar, "practice")
    assert ("練功", m["action_notes"][PRACTICE]) in _rows(bar) and "後才會再現身" in m["action_notes"][PRACTICE]
    s.player.duel_last = []
    boss = duel_rules.here(s, c)[0]
    s.player.duel_tally[duel_rules.week_key(s, c, boss.id)] = c.config.duel.per_boss_week
    m = server.main_view(game)
    bar = _bar(m)
    assert "<b>練功</b><small>頭目不在</small>" in _cell(bar, "practice") and "不再現身" in m["action_notes"][PRACTICE]


def test_a_tired_player_sees_practice_greyed_for_stamina():
    game = _game("yingshui")
    game.state.player.stamina = 0.0
    assert "<b>練功</b><small>體力不夠</small>" in _cell(_bar(server.main_view(game)), "practice")


# ── 五格時每一格的小字都放得下 ─────────────────────────────


PLACES = [  # (陣營, 地點)：城裡、野外、戰線、自家大營、頭目、名望不夠、散人站在戰線上
    (None, "yingchuan"), (None, "yingshui"), (None, "changshe"), (None, "luoyang_road"), (None, "wan_city"),
    (None, "dajiangjun_fu"), (None, "mengjin_ford"), (None, "jade_cave"), ("guan", "changshe"), ("guan", "guan_camp"),
    ("huang", "huangjin_camp"), ("huang", "julu_altar"), ("huang", "changshe"), ("guan", "yingchuan_wilds"),
]


@pytest.mark.parametrize("profile", ["week7", "season21", "weekend"])
def test_every_grey_cell_says_at_most_four_characters(profile):
    seen = set()
    for faction, at in PLACES:
        bar = _bar(server.main_view(_game(at, faction, profile)))
        assert "practice" in _keys(bar), (at, faction)
        for off in re.findall(r'<button class="act-ink[^"]* off".*?</button>', bar, re.S):
            assert _width(_sub(off)) <= 4, (profile, at, faction, off)
            seen.add(_sub(off))
    assert {"城外才有", "這裡沒有", "未投靠", "名望不夠", "不在戰線", "沒有人"} <= seen  # 真的量到了這幾種灰格


def test_the_long_reasons_go_to_the_row_below():
    """散人站在戰線上：格子「未投靠」，「散人不能出陣」整句是伺服器寫的出陣那一行；名望不夠：格子「名望不夠」，還差多少寫在底下（同 FB-664）。"""
    game = _game("changshe")
    m = server.main_view(game)
    social = next(o for o in m["options"] if o["id"] == "act:socialize")
    gap = social["label"].split("（", 1)[1].removesuffix("）")
    assert not social["enabled"] and gap.startswith("名望還差 ")  # 前提
    bar = _bar(m)
    assert "<b>出陣</b><small>未投靠</small>" in _cell(bar, "train") and "<b>交友</b><small>名望不夠</small>" in _cell(bar, "social")
    rows = dict(_rows(bar))
    assert rows["出陣"] == m["action_notes"]["act:train"] and rows["出陣"].startswith(sortie.RANGER_NOTE)
    assert rows["交友"] == f"{gap}。"


def test_a_sortie_name_breaks_only_after_the_dot():
    """「出陣・守」「出陣・攪局」：五格時一行放不下，換行只換在「・」後面，不斷在「攪／局」中間。"""
    bar = _bar(server.main_view(_game("huangjin_camp", "huang")))
    assert '<b><span class="nb">出陣・</span><span class="nb">守</span></b>' in _cell(bar, "train")
    assert "<b>練功</b>" in _cell(bar, "practice") and "<b>探索</b>" in _cell(bar, "explore")  # 沒有「・」的照舊


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
    c = real_content("week7")
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
    assert m["onboard"] is None and "practice" in _keys(_bar(m))


def test_the_hut_never_has_a_practice_option():
    """草廬裡（序章）探索不展開、也沒有練功（_explore_mode_options 在序章是空的）：格子不會在序章冒出來。"""
    c = real_content("week7")
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world(), prologue=True)
    game.client = None
    m = server.main_view(game)
    assert m["prologue"] is not None and PRACTICE not in [o["id"] for o in m["options"]]
    assert explore_modes.option_id(explore_modes.PRACTICE) == PRACTICE
