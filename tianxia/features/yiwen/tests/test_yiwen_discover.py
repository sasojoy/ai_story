"""異聞的撞見（BUS_ORDER 的 outing 那一格）：開關與章、種子、地點類型、名額、時間窗、假人、別的事接管、走一趟停下、序章與季、搶同一句。
經過探索的用正式內容 season21（測試內容走舊探索，撞不到異聞：總計畫「對不上的」第 13 條）；只測規則的直接叫 actions.on_explore。"""
import json

import pytest

from tianxia.features.yiwen import actions, checks, rules
from tianxia.features.yiwen.store import store_of
from tianxia.state import GuardBook, YiwenClaim, YiwenWalk

from yiwen_kit import season21_game


def _meet(game):
    return actions.on_explore(game, game.state.player.location)


OFFICIAL = rules.FILES["openings"]


def _only(monkeypatch, tmp_path, *openings):
    """開場只剩這幾句（從正式檔抄出來寫一份暫存檔）。"""
    known = {o["id"]: o for o in checks.load(OFFICIAL)}
    path = tmp_path / f"only-{len(openings)}.json"
    path.write_text(json.dumps({"openings": [known[o] for o in openings]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(rules.FILES, "openings", path)


def test_needs_switch_and_stamp():
    game = season21_game(discover_chance=1.0)
    game.state.world.yiwen_on = False  # 開關開著、季沒章
    assert _meet(game) == [] and game.state.player.yiwen is None
    game.state.world.yiwen_on = True
    game.content.config.yiwen.enabled = False  # 有章、開關關著
    assert _meet(game) == [] and game.state.player.yiwen is None
    game.content.config.yiwen.enabled = True
    assert _meet(game) and game.state.player.yiwen.opening


def test_roll_seeded_and_leaves_game_rng():
    a, b = season21_game(discover_chance=1.0), season21_game(discover_chance=1.0)
    before = a.rng.getstate()
    assert _meet(a) == _meet(b)
    assert a.state.player.yiwen.opening == b.state.player.yiwen.opening
    assert a.rng.getstate() == before
    seq = a.state.player.explore_seq
    assert rules.roll("yiwen", 1, "甲", seq).random() == rules.roll("yiwen", 1, "甲", seq).random()


def test_kind_mismatch_never_discovers(monkeypatch, tmp_path):
    game = season21_game(discover_chance=1.0, kind="wild")
    _only(monkeypatch, tmp_path, "river_skiff", "eaves_man")  # 渡、城
    for _ in range(20):
        assert _meet(game) == []
        game.state.player.explore_seq += 1
    assert game.state.player.yiwen is None


def test_daily_player_and_season_caps():
    game = season21_game(discover_chance=1.0)
    assert _meet(game)
    actions.drop(game)  # 一幕都還沒寫：開場放回，free_found 不退
    assert game.state.player.yiwen.free_found == 1
    game.state.player.explore_seq += 1
    assert _meet(game) == []  # 一個人一季不用道具一則
    other = season21_game("沈浪", world=game.world, content=game.content)
    other.sync(other.now)
    assert _meet(other) == []  # 全服每天一則（台灣日）
    cfg = game.content.config.yiwen
    cfg.free_daily_cap = 5
    yw = other.state.world.yiwen
    yw.taken["filler"] = YiwenClaim(by="某", at=0.0)
    cfg.season_cap = len(yw.taken)
    assert _meet(other) == []  # 一季的名額滿了
    cfg.season_cap = 30
    assert _meet(other)  # 名額還有就撞得到


def test_until_day_stops_discovery_not_rewalk():
    game = season21_game(discover_chance=1.0, rewalk_chance=1.0)
    other = season21_game("沈浪", world=game.world, content=game.content)
    assert _meet(game)
    from yiwen_kit import walk_all
    walk_all(game)
    actions.drop(game)
    day = game.content.config.yiwen.discover_until_day
    other.sync(other.now)
    other.state.world.time = (day + 1) * rules.DAY * game.content.config.time_scale
    other.state.world.yiwen.taken.clear()
    other.state.world.yiwen.free_day = 0
    assert _meet(other) and other.state.player.yiwen.role == rules.TRAIL  # 重走開到季末
    actions.drop(other)
    other.state.player.yiwen.done.append(other.state.player.yiwen.tale or game.state.player.yiwen.done[0])
    other.state.player.explore_seq += 1
    assert _meet(other) == []  # 走完的那一則不再撞、過了第十八天也不再發掘


def test_bot_never_meets():
    game = season21_game(discover_chance=1.0, rewalk_chance=1.0)
    game.state.player.bot = "test"
    for i in range(1000):
        game.state.player.explore_seq = i
        assert _meet(game) == []
    assert game.state.player.yiwen is None
    assert store_of(game).tales(int(game.state.player.season_number)) == []


def test_side_file_absent_until_first_encounter():
    """第 251 批：開關開著、季有章，沒人撞見過旁檔不存在、存檔也沒有 yiwen 鍵；撞見那一下只寫存檔，
    發掘者說了第一步（開則）旁檔才出現（照現行程式：撞見不寫旁檔，見計畫第 251 批①「先後」）。"""
    from tianxia.features.yiwen.store import TABLES, side_path

    game = season21_game(discover_chance=0.0, rewalk_chance=0.0)
    side = side_path(game.world.db.path)
    for _ in range(5):
        assert _meet(game) == []
        actions.status(game)
        game.state.player.explore_seq += 1
    assert not side.exists()
    assert "yiwen" not in json.loads(game.state.player.model_dump_json())
    assert "yiwen" not in json.loads(game.state.world.model_dump_json())
    game.content.config.yiwen.discover_chance = 1.0
    assert _meet(game) and actions.card(game) is not None  # 撞見
    assert not side.exists()
    from yiwen_kit import walk_all
    walk_all(game, picks=(0,))
    assert side.is_file()
    import contextlib
    import sqlite3
    with contextlib.closing(sqlite3.connect(side)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(TABLES) <= names


def test_takeover_blocks_meeting():
    game = season21_game(discover_chance=1.0)
    game.content.config.guard.enabled = True
    game.state.player.guard = GuardBook(stage="met", opening="", place=game.state.player.location)  # 親衛隊長撞見那一刻接管選單
    assert _meet(game) == [] and game.state.player.yiwen is None


def test_trip_stops_at_the_encounter(monkeypatch):
    """走一趟五段、第二段撞見：停在那一段（最後一拍 stop），選單換成異聞那兩顆。"""
    game = season21_game(discover_chance=1.0)
    calls = {"n": 0}
    real = actions._can_meet

    def second_beat(ctx):
        calls["n"] += 1
        return calls["n"] >= 2 and real(ctx)

    monkeypatch.setattr(actions, "_can_meet", second_beat)
    game.state.pending_event = None
    game.outing_go(5)
    trip = game.state.player.outing
    assert game.state.player.yiwen is not None and game.state.player.yiwen.opening
    assert trip.done == 2 and trip.beats[-1].stop
    assert [o.id for o in game.options(odds=False)] == ["yiwen:open", "yiwen:drop"]


def test_prologue_preparing_closed_never_meet(monkeypatch):
    game = season21_game(discover_chance=1.0)
    monkeypatch.setattr(actions.prologue, "active", lambda s, c: True)
    assert _meet(game) == []
    monkeypatch.undo()
    for phase in ("preparing", "resting"):
        monkeypatch.setattr(type(game.world), "season_phase", lambda self, p=phase: p)
        assert _meet(game) == []
        monkeypatch.undo()
    assert game.state.player.yiwen is None


def test_two_finders_cannot_take_one_opening(monkeypatch, tmp_path):
    _only(monkeypatch, tmp_path, "fog_figure")
    a = season21_game(discover_chance=1.0, free_daily_cap=5, kind="hill")
    b = season21_game("沈浪", world=a.world, content=a.content, kind="hill")
    assert _meet(a)
    b.sync(b.now)
    assert _meet(b) == [] and b.state.player.yiwen is None  # 唯一那一句被佔了：不撞
    _only(monkeypatch, tmp_path, "fog_figure", "clay_faces")
    assert _meet(b) and b.state.player.yiwen.opening == "clay_faces"  # 挑別句
    assert isinstance(a.state.player.yiwen, YiwenWalk)
