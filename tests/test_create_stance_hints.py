"""自創擺式那一步讓人知道勢與稀有路數（Joy 2026-10-22「要加」）：四個勢怎麼擺、對應哪個時機，擺的當下就讀出現在是哪一個；
稀有路數只寫一行「每一格都有機會撞到」（表上每一格都有稀有的才寫，Joy「那個10%應該是怎麼擺都要有機會吧」）。規則不改：網頁照 create.stance_of、
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


def test_the_rare_line_shows_only_when_every_cell_has_a_rare_move(real):
    v = create.view(_game(real).state, real, _game(real).world)
    every = all(moves.has_rare(real, m.attribute, m.timing) for m in real.create_forms.moves)
    assert v["rare_line"] == (create.RARE_LINE.format(odds="一成") if every else "")
    assert "rare_paths" not in v  # 不列哪幾格、不給招名
    gaps = real.model_copy(deep=True)
    gaps.create_forms.moves = [m for m in gaps.create_forms.moves if not m.rare]
    assert create.view(_game(gaps).state, gaps, _game(gaps).world)["rare_line"] == ""
    full = real.model_copy(deep=True)
    full.create_forms.moves = [*full.create_forms.moves, *(m.model_copy(update={"rare": True}) for m in full.create_forms.moves if not m.rare)]
    assert create.view(_game(full).state, full, _game(full).world)["rare_line"] == create.RARE_LINE.format(odds="一成")


def test_the_draft_carries_the_main_attribute(real):
    game = _game(real)
    assert game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(real, "奇變"))
    d = create.view(game.state, real, game.world)["draft"]
    draft = game.state.player.creating
    assert d["main"] == create.top_of(real, draft)
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
def test_the_box_lights_the_stance_and_writes_the_rare_line(real):
    from test_arts_pages_two import run

    c = create.view(_game(real).state, real, _game(real).world)
    c["rare_line"] = create.RARE_LINE.format(odds="一成")
    html = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '武學', '變勢', '快');", fns=["stanceBoxHtml"])
    assert '<li class="on"><span><b>變勢</b>・乘勢</span><small>提起一條腿</small></li>' in html
    assert "此式是<b>變勢</b>・乘勢" in html and c["rare_line"] in html
    inner = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '內功', '守勢', '柔');", fns=["stanceBoxHtml"])
    assert "此式是<b>守勢</b>・心法" in inner
    c["rare_line"] = ""
    plain = run(f"return H.stanceBoxHtml({json.dumps(c, ensure_ascii=False)}, '武學', '起勢', '快');", fns=["stanceBoxHtml"])
    assert "稀有" not in plain


def test_every_cell_of_the_real_table_has_its_own_rare_move(real):
    """Joy「那個10%應該是怎麼擺都要有機會吧」：四十格每一格都有稀有路數，跟那一格常見的招名字不同、打法（kind）或數字不同；
    破境後發動率升到必定，所以出招、心法不放每回合都連環無隙、無隙、打空的那幾種（量過：破境後對常見九成以上）。"""
    for a in create.ATTRIBUTES:
        for timing in ("起手", "出招", "乘勢", "應招", "心法"):
            common, rare = moves.cell(real, a, timing), moves.cell(real, a, timing, rare=True)
            assert rare is not None and rare.rare and not common.rare, (a, timing)
            assert rare.name != common.name and (rare.kind, rare.params, rare.rate) != (common.kind, common.params, common.rate)
            assert not (timing in ("出招", "心法") and rare.rounds == 0 and rare.kind in ("flash", "flawless", "elude")), (a, timing)
    names = [m.name for m in real.create_forms.moves]
    assert len(names) == len(set(names))


# ── 撞到稀有路數看得出來（Joy 2026-10-23「我還是不懂稀有招式是什麼，玩家要怎樣才知道自己的是」）──


def _formed(real, rare):
    game = _game(real)
    game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(real, "奇變"))
    game.create_intent("一拳既出，山河皆震", create.IntentReading(score=80, attributes=["剛"]))
    game.state.player.creating.rare = rare
    return game


def test_forming_a_rare_move_says_so_and_names_the_common_one(real):
    game = _formed(real, True)
    d = create.view(game.state, real, game.world)["draft"]
    common = moves.cell(real, d["main"], d["timing"])
    assert d["rare_hit"] == create.RARE_HIT.format(common=common.name)
    assert d["tactic"].endswith(f"（{moves.RARE_WORD}）")
    assert d["move"] == moves.cell(real, d["main"], d["timing"], True).name != common.name
    plain = create.view(_formed(real, False).state, real, game.world)["draft"]
    assert plain["rare_hit"] == "" and moves.RARE_WORD not in plain["tactic"]


def test_the_art_card_marks_a_rare_move(real):
    from tianxia import skillview
    game = _formed(real, True)
    game.create_name("震山拳")
    from tianxia import team
    art = team.player_art(game.state, real, game.world, game.forged_thing[1])
    assert art.move_rare
    assert skillview.tactic_line(real, art, 5).count(f"（{moves.RARE_WORD}）") == 1
    assert moves.RARE_WORD not in skillview.tactic_line(real, art.model_copy(update={"move_rare": False}), 5)


@needs_node
def test_the_page_draws_the_rare_mark_as_a_tag():
    from test_arts_pages_two import run

    html = run('return H.tacticHtml("立〔以靜制動〕起手・80%：前 3 回合無隙。（稀有路數）");', fns=["tacticHtml"])
    assert '<span class="rare-tag">稀有路數</span>' in html and "（稀有路數）" not in html


def test_the_forming_message_says_a_rare_move_was_hit(real):
    game = _game(real)
    game.create_begin("武學", "拳腳")
    game.create_pose(create.preset(real, "奇變"))
    game.state.player.creating.intent = "一拳既出，山河皆震"
    game.state.player.creating.rare = True
    game.state.player.creating.colors = [["剛"], ["剛"], ["剛"]]
    lines = create.move_lines(game.state, real, game.state.player.creating)
    d = create.view(game.state, real, game.world)["draft"]
    assert lines[0].endswith(f"（{moves.RARE_WORD}）") and lines[1] == d["rare_hit"]
    game.state.player.creating.rare = False
    assert len(create.move_lines(game.state, real, game.state.player.creating)) == 1
