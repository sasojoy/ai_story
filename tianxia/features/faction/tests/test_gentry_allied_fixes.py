"""第一季豪強分屬兩軍的補修（FB-273～275，QA 2026-10-16）。"""
from __future__ import annotations

import random

from conftest import real_content
from test_gentry_allied import _game, _showdown

from tianxia import allied, battle_instance


def _wk():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _fourteen_day():
    """沒有第一季規則的季（不帶設定、14 天）：豪強照舊是第三方（2026-10-31 第一季規則的季的豪強第三方拿掉）。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _ids(game):
    return [o.id for o in game.options() if o.enabled]


# ── FB-273：還沒選邊的豪強遇上集結 ─────────────────────────────


def test_an_unsided_gentry_only_picks_a_side_during_the_muster():
    game = _game(_wk(), faction="haoqiang")  # 拜入曹氏莊院那一下：陣營有了、還沒挑一邊
    definition = _showdown(game)
    assert not game._free_agent(definition)
    ids = [o.id for o in game.options()]
    assert [i for i in ids if i.startswith("battle:")] == []
    assert ids == ["faction:ally:guan", "faction:ally:huang"]
    assert game.choose("battle:enlist:huang") == ["（此刻無法這麼做。）"]
    assert "甲" not in game.world.get_battle().participants


def test_picking_a_side_moves_the_muster_entry_over():
    game = _game(_wk())  # 散人：先臨時投效黃巾
    definition = _showdown(game)
    game.choose("battle:enlist:huang")
    assert game.world.get_battle().participants["甲"].faction == "huang"
    game.state.player.faction = "haoqiang"  # 接著拜入曹氏莊院（還沒挑一邊）
    msgs = game.choose("faction:ally:guan")
    battle = game.world.get_battle()
    assert battle.participants["甲"].faction == "guan"
    assert allied.ALLY_REJOINED.format(ally="官軍", battle=definition.name) in msgs
    assert game.state.journal[0].lines[-1] == allied.ALLY_REJOINED.format(ally="官軍", battle=definition.name)


def test_picking_the_same_side_says_nothing_more():
    game = _game(_wk())
    _showdown(game)
    game.choose("battle:enlist:guan")
    game.state.player.faction = "haoqiang"
    msgs = game.choose("faction:ally:guan")
    assert game.world.get_battle().participants["甲"].faction == "guan"
    assert msgs == [allied.ALLY_DONE.format(ally="官軍")]


def test_after_the_fight_starts_the_side_stays_for_this_battle():
    game = _game(_wk())
    definition = _showdown(game)
    game.choose("battle:enlist:huang")
    game.world.mutate_battle(lambda b: battle_instance.close_muster(b, definition, random.Random(0), 1000.0))
    game.state.player.faction = "haoqiang"
    assert "faction:ally:guan" not in _ids(game)  # 在場上打著：選單是戰場，打完（或走開）再挑
    game.world.mutate_battle(lambda b: setattr(b.participants["甲"], "away", True))  # 走出決戰的大區：照常遊玩
    msgs = game.choose("faction:ally:guan")
    assert game.state.player.ally == "guan"
    assert game.world.get_battle().participants["甲"].faction == "huang"  # 開打之後不能改投（同臨時投效）
    assert allied.ALLY_STAYS.format(ally="官軍", old="黃巾軍", battle=definition.name) in msgs


def test_an_unsided_gentry_is_not_pulled_into_a_running_fight():
    game = _game(_wk(), faction="haoqiang")
    definition = _showdown(game)
    game.world.mutate_battle(lambda b: battle_instance.close_muster(b, definition, random.Random(0), 1000.0))
    battle = game.world.get_battle()
    assert not game._fighting(battle, definition)
    ids = [o.id for o in game.options()]
    assert "battle:join_late" not in ids and ids[:2] == ["faction:ally:guan", "faction:ally:huang"]
    game.choose("faction:ally:guan")
    assert "battle:join_late" in [o.id for o in game.options()]  # 選了邊就照那一軍晚到


# ── FB-274：豪強的投靠點不算哪一方的地盤 ─────────────────────────────

GENTRY_BASES = ("zhuo_militia_hall", "cao_manor", "haozu_fort")


def test_gentry_bases_have_no_controller():
    from tianxia import territory

    wk = _wk()
    game = _game(wk, faction="guan")
    game.advance(60)  # 推一步：地盤照規則算一次
    w = game.state.world
    assert all(territory.controller(w, wk, loc) is None for loc in GENTRY_BASES)
    assert "haoqiang" not in set(w.territory.control.values())
    assert territory.controller(w, wk, "changshe") == "guan"  # 兩軍的大本營照舊


def test_map_counts_only_the_two_sides():
    game = _game(_wk(), faction="guan")
    game.advance(60)
    st = game.map_state()
    controls = {info["control"] for info in st["places"].values()}
    assert "haoqiang" not in controls
    assert all(st["places"][loc]["control"] is None and st["places"][loc]["kind"] == "base" for loc in GENTRY_BASES)
    assert "haoqiang" not in set((st["start"] or {}).values())
    assert all("haoqiang" not in set((week["control"] or {}).values()) for week in st["weeks"])


def test_snapshots_from_before_the_fix_drop_the_gentry_bases():
    """上線那一刻正在跑的季：開季與每週的快照裡記著豪強佔著自己的投靠點（修好之前算的），畫面上照樣只算兩方。"""
    game = _game(_wk(), faction="guan")
    game.advance(60)
    t = game.state.world.territory
    for snap in t.weeks.values():
        snap.control.update({loc: "haoqiang" for loc in GENTRY_BASES})
    st = game.map_state()
    assert "haoqiang" not in set((st["start"] or {}).values())
    assert all("haoqiang" not in set((week["control"] or {}).values()) for week in st["weeks"])


def test_stale_season_control_reads_no_gentry_base():
    from tianxia import territory

    game = _game(_wk(), faction="guan")
    game.advance(60)
    w = game.state.world
    w.territory.control["cao_manor"] = "haoqiang"  # 修好之前存下來的那一份
    assert territory.controller(w, game.content, "cao_manor") is None


# ── FB-275：此地還有寫出依附哪一邊 ─────────────────────────────


def test_presence_names_the_side_of_an_allied_gentry():
    from tianxia import social

    wk = _wk()
    game = _game(wk, faction="haoqiang", ally="huang")
    assert social.side(game.state, wk) == "地方豪強・依附黃巾軍"
    game.state.player.faction, game.state.player.ally = "guan", None
    assert social.side(game.state, wk) == "官軍"
    game.state.player.faction = None
    assert social.side(game.state, wk) == "散人"


def test_presence_old_rules_say_the_faction_only():
    from tianxia import social

    off = _fourteen_day()
    game = _game(off, name="乙", faction="haoqiang")
    assert social.side(game.state, off) == "地方豪強"


def _seen_here(content, ally):
    """「此地還有」照真的那條路走（FB-275 複驗，QA 40b89826）：另一個人的存檔存進資料庫，再由 Game.peers_here 經
    CharacterStore.present 讀回來——角色存檔不含賽季，讀回來的那一份沒有這一季的章。"""
    from tianxia.characters import CharacterStore

    now = 1_000_000.0
    me = _game(content, at="yingchuan")
    other = _game(content, name="豪客子", faction="haoqiang", ally=ally, at="yingchuan")
    for g in (me, other):
        g.sync(now)
    CharacterStore(other.world.db).save(other.state)
    return me.peers_here()


def test_presence_read_back_from_the_database_names_the_allied_side():
    """依附黃巾軍的豪強，從資料庫讀回來照樣寫「地方豪強・依附黃巾軍」（以前讀回來的存檔沒有章，寫回「地方豪強」）。"""
    assert _seen_here(_wk(), "huang") == [{"name": "豪客子", "side": "地方豪強・依附黃巾軍"}]


def test_presence_read_back_under_the_old_rules_says_the_faction_only():
    """豪強不分屬兩軍的季（14 天那一種）照舊只寫陣營名。"""
    assert _seen_here(_fourteen_day(), None) == [{"name": "豪客子", "side": "地方豪強"}]
