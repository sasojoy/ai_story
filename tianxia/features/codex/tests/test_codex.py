"""江湖錄（features/codex）：走一條奇事，每一幕記下選了哪一句、重讀得回全文；收了記結局、寫她留在哪；見過的人、拿過的東西、悟出的神品點亮；
紅點看過就滅；換季整本照帶；第一次打開開關照存檔補、不亮紅點。用正式內容（season21）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia.features.codex import rules, view
from tianxia.features.explore import explore_rules as explore_one
from tianxia.models import Condition
from tianxia.rules import day_seconds
from tianxia.state import Equipment, StoryProgress

L = "yesanniang"
FORD, HILL = "mengjin_ford", "beimang_hill"


def _game(loc=FORD):
    game = ready(jianfa_game(), side="guan", loc=loc)
    game.content.config.codex.enabled = True
    game.sync(game.now)
    return game


def _go(game, loc: str, wait: float, event: str):
    s = game.state
    s.world.time += int(wait * day_seconds(game.content, s.world)) + 1
    s.player.location, s.player.journey = loc, None
    game.choose(f"story:{L}")
    assert s.pending_event == event


def _start(game):
    start = game.content.storylines[L].start
    start.chance, start.condition = 1.0, Condition()
    with mock.patch.object(explore_one, "draw", return_value=explore_one.MATERIAL):
        game.choose("act:explore")
    assert game.state.pending_event == "yesanniang_1"


def test_each_scene_keeps_the_pick_and_reads_back_in_full():
    game = _game()
    _start(game)
    game.choose("choice:0")
    b = game.state.player.codex
    assert [(sc.line, sc.event, sc.choice) for sc in b.scenes] == [(L, "yesanniang_1", 0)]
    ev = game.content.events["yesanniang_1"]
    text = view.scene(game, 0)
    assert text["pick"] == ev.choices[0].text and text["before"] and text["after"]
    assert text["after"][0] in rules.fill(ev.choices[0].effect.text, game.state, L, {})
    assert len(text["others"]) == len(ev.choices) - 1
    q = view.quests(game)
    row = next(x for x in q["on"] if x["line"] == L)
    assert row["state"] == "on" and row["next"]["what"] and [x["pick"] for x in row["scenes"]] == [ev.choices[0].text]
    assert all(g["line"] != L for g in q["ghosts"])


@pytest.mark.slow
def test_a_story_walked_to_the_end_shows_the_ending_and_where_she_stays():
    game = _game()
    s, p = game.state, game.state.player
    _start(game)
    game.choose("choice:0")
    _go(game, HILL, 0, "yesanniang_2")
    game.choose("choice:0")
    _go(game, HILL, 0.25, "yesanniang_3")
    game.choose("choice:2")
    _go(game, FORD, 0.25, "yesanniang_4")
    game.choose("choice:1")
    game.sync(game.now)
    assert p.storylines[L].ending == "chuan"
    assert [sc.event for sc in p.codex.scenes] == ["yesanniang_1", "yesanniang_2", "yesanniang_3", "yesanniang_4"]
    row = next(x for x in view.quests(game)["done"] if x["line"] == L)
    assert row["ending"]["title"] == game.content.storylines[L].ending("chuan").title
    assert row["stay"]["loc"] == FORD and row["stay"]["place"]
    assert view.ending_text(game, L, "chuan")["after"]
    assert "yesanniang" in p.codex.people and f"q:{L}" in p.codex.fresh and f"e:{L}:chuan" in p.codex.fresh
    view.seen(game, ["q:*", "e:*"])
    assert not view.status(game)["q"] and not view.status(game)["e"]


def _off_game():
    """開關關著的局（season21 2026-11-13 起打開：這裡自己關）。"""
    content = jianfa_game()
    game = ready(content, side="guan", loc=FORD)
    game.content.config.codex.enabled = False
    game.content.config.codex.tracker = False
    game.state.player.codex = None
    game.sync(game.now)
    return game


def test_the_first_look_fills_from_the_save_without_red_dots():
    game = _off_game()
    p = game.state.player
    p.storylines[L] = StoryProgress(line=L, ending="chuan", ended_at=game.state.world.time)
    p.affinities["caocao"] = 10
    p.materials["gang_1"] = 2
    game.content.config.codex.enabled = True
    game.sync(game.now)
    b = p.codex
    assert b is not None and b.fresh == []
    assert any(e.line == L and e.ending == "chuan" for e in b.ended)
    assert "caocao" in b.people and "材:gang_1" in b.things
    p.treasure = Equipment(slot="treasure", id="寶:1", name="觀山石", template="guanshan_shi")
    game.sync(game.now + 1)
    assert "寶:guanshan_shi" in b.things and "t:寶:guanshan_shi" in b.fresh
    cells = {c["key"]: c for g in view.things(game)["groups"] for c in g["cells"]}
    assert cells["寶:guanshan_shi"]["got"] and cells["寶:guanshan_shi"]["dot"] and not cells["寶:ningshen_xiangnang"]["got"]


def test_unseen_people_and_stories_stay_silhouettes():
    game = _game()
    page = view.page(game)
    ghost = next(g for g in page["quests"]["ghosts"] if g["line"] == "duruo")
    assert ghost["title"] == view.UNSEEN and ghost["where"]
    duruo = next(r for r in page["people"]["rows"] if r["id"] == "duruo")
    assert duruo["name"] == view.UNSEEN and duruo["face"] is None and duruo["place"]
    assert page["gods"]["all"] == 40 and page["gods"]["got"] == 0
    assert set(page["gods"]["forms"]) == {"攻", "守", "變", "心"} and len(page["gods"]["paths"]) == 10


def test_the_book_follows_the_player_into_the_next_season():
    from tianxia.state import GameState

    game = _game()
    _start(game)
    game.choose("choice:0")
    old = game.state.model_copy(deep=True)
    new = GameState(player=game.state.player.model_copy(update={"codex": None}), world=game.state.world)
    rules.carry(old, new, game.content)
    assert [sc.event for sc in new.player.codex.scenes] == ["yesanniang_1"]
    assert new.player.codex.upto == -1


def test_the_switch_off_keeps_the_save_quiet():
    game = _off_game()
    assert game.state.player.codex is None
    assert "codex" not in game.state.player.model_dump()


def test_the_tracker_lists_open_lines_only_with_its_switch():
    game = _game()
    game.content.config.codex.tracker = False
    _start(game)
    game.choose("choice:0")
    assert "track" not in view.status(game)
    game.content.config.codex.tracker = True
    rows = view.status(game)["track"]
    row = next(x for x in rows if x["line"] == L)
    assert row["kind"] == "奇事" and row["title"] == game.content.storylines[L].title and row["what"]
    assert row["key"] == f"{game.state.player.season_number}:{L}"


def _lit_cells(game) -> set[str]:
    """畫面上亮著紅點的每一格（奇遇的一件、人物、器物、意境、結局）換回 fresh 的鍵。"""
    page = view.page(game)
    q = page["quests"]
    out = {f"q:{r['line']}" for r in q["on"] + q["done"] if r["dot"]}
    out |= {f"p:{r['id']}" for r in page["people"]["rows"] if r["dot"]}
    out |= {f"t:{c['key']}" for g in page["things"]["groups"] for c in g["cells"] if c["dot"]}
    out |= {f"g:{c['id']}" for c in page["gods"]["cells"].values() if c["dot"]}
    for r in page["endings"]["rows"]:
        out |= {f"e:{r['line']}:{e['id']}" for e in r["ends"] if e["got"] and f"e:{r['line']}:{e['id']}" in game.state.player.codex.fresh}
    return out


def _every_kind(game):
    """每一種紅點都亮一個：走一幕（q:、p:）、拿寶物（t:）、悟出神品（g:）、另一條奇事收了（e:）。"""
    from tianxia.martial_arts import Insight
    from tianxia.state import InsightFx

    s, p, c = game.state, game.state.player, game.content
    _start(game)
    game.choose("choice:0")
    p.treasure = Equipment(slot="treasure", id="寶:1", name="觀山石", template="guanshan_shi")
    god = c.traits.god[0]
    p.own_insights["悟:9"] = Insight(id="悟:9", name="歸雁", attribute=god.attribute, place="潁川書院")
    p.insight_fx["悟:9"] = InsightFx(quality="神品", grand=god.id)
    other = next(lid for lid, line in c.storylines.items() if line.kind == "奇事" and line.start is not None and lid != L and line.endings)
    p.storylines[other] = StoryProgress(line=other, ending=c.storylines[other].endings[0].id, ended_at=s.world.time)
    game.sync(game.now + 1)


def test_every_red_dot_has_a_cell_and_goes_out_when_seen():
    game = _game()
    _every_kind(game)
    fresh = set(game.state.player.codex.fresh)
    assert {k[0] for k in fresh} >= {"q", "p", "t", "g", "e"}
    assert fresh == _lit_cells(game)  # 亮著的每一個都畫得出一格；畫不出來的不准亮
    for key in sorted(fresh):  # 一格一格點過去：那一格滅，別格不動
        view.seen(game, [key])
        assert key not in game.state.player.codex.fresh and key not in _lit_cells(game)
    st = view.status(game)
    assert not any(st[k] for k in ("q", "p", "t", "g", "e"))


def test_dots_seen_do_not_grow_back_over_ten_syncs():
    from tianxia.state import JournalEntry

    game = _game()
    _every_kind(game)
    view.seen(game, list(game.state.player.codex.fresh))
    for i in range(10):  # 每一下都多一則跟線無關的紀錄（以前讀到哪裡一換，「這條線新開過」的記號就跟著清掉，主線又亮一次）
        game.state.journal.insert(0, JournalEntry(time=game.state.world.time + i + 1, title=f"遊歷・第{i}趟"))
        game.sync(game.now + 600 * (i + 1))
        assert game.state.player.codex.fresh == [], i


def test_dots_from_a_line_that_cannot_be_drawn_are_dropped():
    game = _game()
    _start(game)
    game.choose("choice:0")
    b = game.state.player.codex
    b.fresh += ["q:no_such_line", "p:no_such_person", "e:ch_guan_1:x"]
    game.sync(game.now + 1)
    assert not {"q:no_such_line", "p:no_such_person", "e:ch_guan_1:x"} & set(b.fresh)
