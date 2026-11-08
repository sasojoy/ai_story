"""拿掉地方豪強（企劃者 2026-11-07 決策卡「下一季起整個拿掉」；Config.gentry、WorldState.no_gentry、allied.gentry_on）。

新開的季（正式內容 content/config.json 寫 gentry false）只剩官軍、黃巾、散人：投靠、拜入、叛投、三方卡、名冊、輿圖、補假人、
玩法說明、新手引導都不再有豪強。章之前開的季（第 9 季）照它自己的章，已經投了豪強的人季中不變（最後一條）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import allied, leaderboard
from tianxia.engine import Game
from tianxia.features.faction import sides as faction_sides
from tianxia.features.guide import howto as guide_howto
from tianxia.features.guide import rules as guide_rules
from tianxia.state import WorldState

GENTRY_BASES = ("zhuo_militia_hall", "cao_manor", "haozu_fort")


@pytest.fixture
def wk():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _game(content, name="甲", at=None, faction=None):
    game = Game.new(content, name, rng=random.Random(0))
    if at is not None:
        game.state.player.location = at
    game.state.player.faction = faction
    return game


def _ids(game):
    return [o.id for o in game.options() if o.enabled]


def test_the_real_config_stamps_new_seasons_without_the_gentry(wk):
    assert wk.config.gentry is False
    game = _game(wk)
    w = game.state.world
    assert w.no_gentry and not allied.gentry_on(wk, w) and not allied.gentry_split(wk, w)
    assert [f.id for f in allied.factions_of(wk, w)] == ["guan", "huang"]
    # 章之前開的季（存檔裡沒有這個鍵）照舊有豪強；False 不寫進存檔
    assert allied.gentry_on(wk, WorldState.model_validate({}))
    assert "no_gentry" not in WorldState().model_dump()


def test_no_join_no_sect_owner_no_defect_at_the_gentry_bases(wk):
    game = _game(wk, at="cao_manor")
    assert not any(i.startswith("faction:") for i in _ids(game))
    msgs = game.choose("faction:haoqiang")  # 舊畫面送來的也不收
    assert game.state.player.pending_faction is None and msgs
    from tianxia.models import Effect
    from tianxia.rules import apply_effect

    apply_effect(Effect(join_sect="cao_manor"), game.state, wk, game.world)  # 拜入曹氏莊院只是入門派
    assert (game.state.player.sect, game.state.player.faction) == ("cao_manor", None)
    army = _game(wk, name="乙", at="cao_manor", faction="guan")
    assert not any(i.startswith("defect:") for i in _ids(army))
    assert "faction:guan" in _ids(_game(wk, name="丙", at="changshe"))


def test_cards_roster_board_and_map_show_two_sides(wk):
    game = _game(wk, at="yingchuan")
    card = faction_sides.sides_card(game)
    assert card is not None and [col["id"] for col in card["cols"]] == ["guan", "huang"]
    assert "豪強" not in game.faction_counts_text()
    assert set(leaderboard.contribution_rankings(wk, game.world)) == {"guan", "huang"}
    st = game.map_state()
    assert "haoqiang" not in st["sides"]
    assert all(st["places"][loc]["kind"] != "base" for loc in GENTRY_BASES if loc in st["places"])


def test_howto_and_the_newbie_lines_leave_the_gentry_out(wk):
    game = _game(wk, at="yingchuan")
    w = game.state.world
    text = game.howto_text()
    assert "豪強" not in text, [line for line in text.splitlines() if "豪強" in line]
    assert "豪強" not in "".join(sum(guide_howto.war_help(game.state, wk).values(), []))
    farewell = next(s for s in wk.tutorial.steps if s.id == "p11_farewell")
    assert "豪強" in farewell.text and "豪強" not in guide_rules.step_words(game.state, wk, farewell)[0]
    assert "豪強" not in wk.tutorial.enlist.drifter_line_two_sides
    assert not allied.gentry_on(wk, w)


def test_a_season_opened_before_the_stamp_keeps_its_gentry(wk):
    """第 9 季（開季時還沒有這個章）：設定改了也照舊有豪強，投靠豪強、依附一軍照走。"""
    game = _game(wk, at="cao_manor")
    game.world.mutate(lambda st: setattr(st.season, "no_gentry", False))
    game.sync(1.0)
    assert allied.gentry_on(wk, game.state.world)
    assert "faction:haoqiang" in _ids(game)
    game.choose("faction:haoqiang")
    assert game.state.player.pending_faction == "haoqiang"


def test_cao_manor_is_no_sect_and_xuchu_stands_with_the_army(wk):
    """企劃者 2026-11-07：曹氏莊院下一季起不當門派（「曹氏莊院 不適合當門派」，拜入的試煉不出、酒肆問路不提）；許褚歸官軍（「按照建議改」）。"""
    from tianxia import figure_life, roster
    from tianxia.features.tavern import ask as tavern_ask
    from tianxia.rules import check_condition

    trial = wk.events["cao_manor_join"]
    game = _game(wk, at="cao_manor")
    st = game.state
    assert not check_condition(trial.condition, st, wk)
    assert not allied.sect_open(wk, st.world, "cao_manor") and allied.sect_open(wk, st.world, "yingchuan_academy")
    assert not any("曹氏莊院" in line and "門派" in line for line in tavern_ask.place_lines(st, wk, "cao_manor"))
    xuchu = wk.characters["xuchu"]
    assert xuchu.side == "haoqiang" and figure_life.side_of(wk, "xuchu", st.world) == "guan"
    st.player.faction = "guan"
    assert roster.recruit_problem(st, wk, game.world, "xuchu") != roster.SIDE_ONLY.format(side="地方豪強")
    st.player.faction = "huang"
    assert roster.recruit_problem(st, wk, game.world, "xuchu") == roster.SIDE_ONLY.format(side="官軍")
    # 章之前開的季（第 9 季）：試煉照出、許褚照舊站豪強
    st.world.no_gentry = False
    st.player.faction = None
    assert check_condition(trial.condition, st, wk)
    assert figure_life.side_of(wk, "xuchu", st.world) == "haoqiang"
