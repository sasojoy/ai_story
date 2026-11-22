"""異聞走一趟（第 247 批：每一幕寫替身、不叫模型）：三幕走完、重放、獎勵、放下、不見了、換季、江湖史、存檔不多鍵。
測試內容的 game 加十八句（yiwen_kit.use_test_lines），撞見直接擺（claim）或直接叫 actions.on_explore。"""
import contextlib
import json
import random
import sqlite3

import pytest

from tianxia.core.option import IDLE_MARK
from tianxia.engine import Game
from tianxia.features.yiwen import actions, rules
from tianxia.features.yiwen.store import store_of
from tianxia.state import PlayerState

from yiwen_kit import claim, turn_on, use_test_lines, walk_all

OPENING = "fog_figure"


@pytest.fixture
def on(game, monkeypatch):
    use_test_lines(monkeypatch)
    turn_on(game)
    game.content.config.yiwen.discover_chance = 0.0
    return game


def _second(game, name="乙"):
    other = Game.new(game.content, name, rng=random.Random(1), world=game.world)
    other.state.player.location = game.state.player.location
    other.state.player.journey = None
    return other


def _trail(finder, name="乙"):
    """另一個人在同一處重走那一則（rewalk_chance 調成 1）。"""
    other = _second(finder, name)
    finder.content.config.yiwen.rewalk_chance = 1.0
    assert actions.on_explore(other, other.state.player.location)
    finder.content.config.yiwen.rewalk_chance = 0.0
    assert other.state.player.yiwen.role == rules.TRAIL
    return other


def _silver(game):
    return game.state.player.stats.get("silver", 0)


def _amount(game, table, kind="silver"):
    return rules.reward(table, game.content)[kind]


def _finished(game):
    claim(game, OPENING)
    walk_all(game)
    return store_of(game).tale(game.state.player.yiwen.tale)


def test_fallback_discovery_walks_three_scenes(on):
    claim(on, OPENING)
    assert [o.id for o in on.options(odds=False)] == ["yiwen:open", "yiwen:drop"]
    got = walk_all(on)
    w = on.state.player.yiwen
    tale = store_of(on).tale(w.tale)
    assert tale["status"] == rules.OPEN and tale["discoverer_shown"] == on.state.player.name
    nodes = store_of(on).nodes(w.tale)
    assert [n["depth"] for n in nodes] == [1, 2, 3] and all(n["fallback"] for n in nodes)
    assert nodes[0]["pick"] == rules.openings()[OPENING]["guesses"][0]
    assert all(len(n["options"]) == 3 for n in nodes[:2]) and nodes[2]["options"] == []
    assert any(line in rules.lines()["close"] for line in got[-1])
    card = actions.card(on)
    assert card["done"] and card["close"] in rules.lines()["close"] and card["choices"] == []
    assert [o.id for o in on.options(odds=False)] == ["yiwen:drop"]
    on.choose("yiwen:drop")
    assert on.state.player.yiwen.opening == "" and IDLE_MARK in {o.id for o in on.options(odds=False)}


def test_rewalk_replays_scene_with_zhupi(on):
    _finished(on)
    first = store_of(on).nodes(on.state.player.yiwen.tale)[0]
    actions.drop(on)
    other = _trail(on)
    card = actions.card(other)
    assert card["mark"] == "trail" and card["choices"][0]["state"] == "walked" and card["choices"][0]["by"] == on.state.player.name
    got = actions.step(other, {"tale": card["tale"], "opening": OPENING, "node": 0, "pick": 0})
    assert rules.fill(rules.pick_line(rules.lines(), "echo", season=1, tale=card["tale"], node=first["id"]), pick=first["pick"]) in got
    scene = actions.card(other)["scenes"][0]
    assert scene["zhupi"] and on.state.player.name in scene["zhupi_text"] and first["pick"] in scene["zhupi_text"]
    assert scene["luck"] == rules.LUCK_SEAL[first["luck"]] and scene["replay"] and scene["text"] == first["text"]
    assert len(store_of(on).nodes(card["tale"])) == 3  # 重放不寫新的


def test_rewards_scene_replay_finish(on):
    on.content.config.yiwen.luck_good = 0.0  # 不擲出素材，只看銀兩
    claim(on, OPENING)
    before = _silver(on)
    walk_all(on)
    t = on.content.config.yiwen
    assert _silver(on) - before == 3 * _amount(on, t.per_scene) + _amount(on, t.finish_first)
    actions.drop(on)
    other = _trail(on)
    before = _silver(other)
    walk_all(other)
    assert _silver(other) - before == 3 * _amount(on, t.per_replay) + _amount(on, t.finish)


def test_drop_and_rewalk_pays_each_scene_once(on):
    _finished(on)
    actions.drop(on)
    other = _trail(on)
    t = on.content.config.yiwen
    before = _silver(other)
    walk_all(other, picks=(0,))
    actions.drop(other)
    on.content.config.yiwen.rewalk_chance = 1.0
    other.state.player.explore_seq += 1
    assert actions.on_explore(other, other.state.player.location)
    walk_all(other, picks=(0,))
    assert _silver(other) - before == _amount(on, t.per_replay)


def test_finished_tale_never_met_again(on):
    _finished(on)
    actions.drop(on)
    other = _trail(on)
    walk_all(other)
    actions.drop(other)  # 收起
    on.content.config.yiwen.rewalk_chance = 1.0
    for i in range(20):
        other.state.player.explore_seq = 100 + i
        assert actions.on_explore(other, other.state.player.location) == []


def test_luck_material_only_for_writer():
    """正式內容 season21（測試內容的地點沒有素材）：寫成的那一幕是順，多一個此地素材；重放的人不加。"""
    from yiwen_kit import season21_game

    finder = season21_game(discover_chance=1.0, luck_good=1.0)
    c = finder.content
    assert any(m in c.materials for m in c.locations[finder.state.player.location].materials)
    assert actions.on_explore(finder, finder.state.player.location)
    bag = sum(finder.state.player.materials.values())
    walk_all(finder)
    assert sum(finder.state.player.materials.values()) - bag == 3
    actions.drop(finder)
    other = season21_game("沈浪", world=finder.world, content=c)
    c.config.yiwen.rewalk_chance, c.config.yiwen.discover_chance = 1.0, 0.0
    assert actions.on_explore(other, other.state.player.location)
    bag = sum(other.state.player.materials.values())
    walk_all(other)
    assert sum(other.state.player.materials.values()) == bag


def test_season_start_clears_walk(on):
    from tianxia.core.registry import FEATURES

    claim(on, OPENING)
    feature = next(f for f in FEATURES if f.name == "yiwen")
    assert "yiwen" not in feature.carried
    feature.on_season_start(on, on.state)
    assert on.state.player.yiwen is None


def test_switch_off_midwalk_releases_menu(on):
    claim(on, OPENING)
    walk_all(on, picks=(0,))
    on.content.config.yiwen.enabled = False
    assert actions.menu(on) is None
    assert IDLE_MARK in {o.id for o in on.options(odds=False)}
    assert on.state.player.yiwen.opening == OPENING  # 留著
    assert actions.step(on, {"tale": on.state.player.yiwen.tale, "opening": OPENING, "node": on.state.player.yiwen.node, "pick": 0}) == []


def test_others_unwalked_choice_locked(on):
    _finished(on)
    actions.drop(on)
    other = _trail(on)
    card = actions.card(other)
    assert [c["state"] for c in card["choices"]] == ["walked", "locked", "locked"]
    got = actions.step(other, {"tale": card["tale"], "opening": OPENING, "node": 0, "pick": 1})
    assert got == rules.lines()["locked"]
    assert len(store_of(on).nodes(card["tale"])) == 3 and other.state.player.yiwen.node == 0


def test_drop_three_roles(on):
    # ① 發掘者、一幕都還沒寫：開場放回，free_found 不退
    w = claim(on, OPENING)
    w.free_found = 1
    assert actions.drop(on) == rules.lines()["drop"]
    assert OPENING not in on.state.world.yiwen.taken and on.state.player.yiwen.free_found == 1
    # ② 發掘者、已有幾幕：提早公開，名額照留
    claim(on, OPENING)
    walk_all(on, picks=(0,))
    tid = on.state.player.yiwen.tale
    actions.drop(on)
    assert store_of(on).tale(tid)["status"] == rules.OPEN and OPENING in on.state.world.yiwen.taken
    # ③ 後來的人：只清眼前，那一列留著沒走完；接著寫沒寫完的那一步不算岔路
    other = _trail(on)
    assert actions.card(other)["choices"][0]["state"] == "walked"
    walk_all(other, picks=(0,))
    assert [c["state"] for c in actions.card(other)["choices"]] == ["free", "free", "free"]
    actions.drop(other)
    walk = store_of(on).walk(tid, other._mall_owner())
    assert walk is not None and walk["finished_at"] is None
    assert other.state.player.yiwen.opening == ""


def _gone_check(game):
    assert actions.menu(game) is None
    assert IDLE_MARK in {o.id for o in game.options(odds=False)}
    assert actions.on_sync(game, 0) == rules.lines()["gone"]
    assert game.state.player.yiwen.opening == ""


def test_missing_row_or_opening_releases_menu(on, monkeypatch, tmp_path):
    # 旁檔少了那一列（還原到比主檔舊）
    claim(on, OPENING)
    walk_all(on, picks=(0,))
    with contextlib.closing(sqlite3.connect(store_of(on).path)) as conn, conn:
        conn.execute("DELETE FROM tales")
    _gone_check(on)
    # 開場改版後不在內容檔
    on.state.world.yiwen.taken.clear()
    claim(on, "clay_faces")
    path = tmp_path / "less.json"
    data = json.loads(rules.FILES["openings"].read_text(encoding="utf-8"))
    data["openings"] = [o for o in data["openings"] if o["id"] != "clay_faces"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(rules.FILES, "openings", path)
    _gone_check(on)
    use_test_lines(monkeypatch)
    # 旁檔不在（store_of 是 None）
    claim(on, "bell_night")
    monkeypatch.setattr(actions, "store_of", lambda ctx: None)
    _gone_check(on)


def test_finder_chronicle_line(on):
    before = len(on.state.world.chronicle)
    _finished(on)
    lines = [r.text for r in on.state.world.chronicle[before:]]
    title = rules.openings()[OPENING]["title"]
    assert lines == [actions.CHRONICLE.format(who=on.state.player.name, title=title)]
    assert any("首見異聞" in a.text for a in on.state.player.annals) or not on.state.player.annals


def test_world_and_player_none_write_no_key(on):
    """開著、沒人撞見：全服存檔、角色存檔都沒有 yiwen 鍵；撞見一次後才有。舊存檔沒有這個鍵照讀。"""
    player = json.loads(on.state.player.model_dump_json())
    world = json.loads(on.state.world.model_dump_json())
    assert "yiwen" not in player and "yiwen" not in world and world.get("yiwen_on") is True
    assert PlayerState.model_validate(player).yiwen is None
    claim(on, OPENING)
    assert "yiwen" in json.loads(on.state.player.model_dump_json())
    assert "yiwen" in json.loads(on.state.world.model_dump_json())
