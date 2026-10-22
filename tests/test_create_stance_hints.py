"""自創擺式那一步讓人知道勢與稀有路數（Joy 2026-10-22「要加」）：四個勢怎麼擺、對應哪個時機，擺的當下就讀出現在是哪一個；
稀有路數在哪八格（只給格子、不給招名），現在的主屬性＋時機落在有稀有的那一格時多寫一句。規則不改：網頁照 create.stance_of、
create.top_of 的同一套即時算，這裡用 node 對一遍。"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import webharness
from tianxia import create, moves
from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def real():
    c = load_content(ROOT / "content")
    c.config.auto_open_first_season = True
    return c


def _game(c):
    game = Game.new(c, "立派人", rng=random.Random(3))
    game.world.open_season(c, now=0.0)
    game.state.player.stats["xinde"] = 5000
    return game


def test_the_view_lists_the_stances_in_the_order_they_are_read(real):
    v = create.view(_game(real).state, real, _game(real).world)
    assert [r["stance"] for r in v["stances"]["武學"]] == ["變勢", "守勢", "攻勢", "起勢"]
    assert [r["timing"] for r in v["stances"]["武學"]] == ["乘勢", "應招", "出招", "起手"]
    assert [r["timing"] for r in v["stances"]["內功"]] == ["心法", "心法", "心法", "起手"]
    assert all(r["how"] for r in v["stances"]["武學"])


def test_the_rare_cells_are_listed_without_their_names(real):
    v = create.view(_game(real).state, real, _game(real).world)
    rare = [(m.attribute, m.timing) for m in real.create_forms.moves if m.rare]
    assert [(r["attribute"], r["timing"]) for r in v["rare_paths"]] == rare and len(rare) == 8
    text = json.dumps(v["rare_paths"], ensure_ascii=False) + v["rare_line"]
    assert not any(m.name in text for m in real.create_forms.moves if m.rare)  # 招名留驚喜
    assert v["rare_line"] == create.RARE_LINE.format(odds="一成")


def test_the_draft_carries_the_main_attribute_and_whether_its_cell_is_rare(real):
    game = _game(real)
    assert game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(real, "奇變"))
    d = create.view(game.state, real, game.world)["draft"]
    draft = game.state.player.creating
    assert d["main"] == create.top_of(real, draft)
    assert d["rare_cell"] == moves.has_rare(real, d["main"], d["timing"])
    w = dict(d["base_weights"])
    for a, n in zip(create.pose_read(draft.pose), real.config.arts.create_pose_weights):
        w[a] += n
    assert w == create.weights(real, draft)


# ── 網頁：即時讀勢與主屬性跟伺服器同一套 ──

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _poses(n=60):
    rng = random.Random(7)
    keys = ("t", "lS", "lE", "rS", "rE", "lH", "lK", "rH", "rK")
    out = [{k: round(rng.uniform(-170, 170) if k != "t" else rng.uniform(-35, 35), 1) for k in keys} for _ in range(n)]
    return out


@needs_node
def test_the_page_reads_the_same_stance_as_the_server(real):
    from test_arts_pages_two import run

    poses = _poses() + [p.angles for p in real.create_forms.presets]
    got = run(f"return JSON.stringify({json.dumps(poses)}.map((P) => H.poseRead(P).stance));", fns=["poseRead"])
    assert json.loads(got) == [create.stance_of(p) for p in poses]


@needs_node
def test_the_page_picks_the_same_main_attribute_as_the_server(real):
    from test_arts_pages_two import run

    game = _game(real)
    assert game.create_begin("武學", "刀")
    c = create.view(game.state, real, game.world)
    poses = _poses(40)
    got = json.loads(run(f"const c = {json.dumps(c, ensure_ascii=False)}; return JSON.stringify({json.dumps(poses)}.map((P) => H.createMain(c, c.draft, H.poseRead(P).attrs)));",
                         fns=["poseRead", "createMain"]))
    want = []
    for pose in poses:
        draft = game.state.player.creating.model_copy(update={"pose": pose})
        want.append(create.top_of(real, draft))
    assert got == want


@needs_node
def test_the_box_lights_the_stance_and_the_rare_cell(real):
    from test_arts_pages_two import run

    c = create.view(_game(real).state, real, _game(real).world)
    html = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '武學', '變勢', '快');", fns=["stanceBoxHtml"])
    assert '<li class="on"><span><b>變勢</b>・乘勢</span><small>提起一條腿</small></li>' in html
    assert "此式是<b>變勢</b>・乘勢" in html and create.RARE_HERE in html
    assert html.count('class="cr-rp on"') == 1
    plain = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '武學', '起勢', '快');", fns=["stanceBoxHtml"])
    assert create.RARE_HERE not in plain and 'class="cr-rp on"' not in plain
    inner = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '內功', '守勢', '柔');", fns=["stanceBoxHtml"])
    assert "此式是<b>守勢</b>・心法" in inner and create.RARE_HERE not in inner
