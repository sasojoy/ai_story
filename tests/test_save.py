import json

from tianxia.engine import Game
from tianxia.save import load_game, save_game


def test_roundtrip(tmp_path, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.world.flags.add("blocked")
    game.state.player.members["mate"].neili = 12.5
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    assert load_game(path) == game.state


def test_roundtrip_keeps_battle_records(tmp_path, game):
    game.choose("move:lake")
    game.choose("act:train")
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    loaded = load_game(path)
    assert loaded == game.state
    assert loaded.battles[0].opponent == "水寇小隊" and loaded.battle_card == 1


def test_1a_save_without_battle_records_still_loads(tmp_path, content, game):
    dump = game.state.model_dump(mode="json")
    for key in ("battles", "battle_seq", "battle_card"):
        del dump[key]
    dump["last_report"] = ["⚔ 對陣：翻江龍", "── 第1回合 ──"]  # 1a 的存檔只留最近一場的戰報文字
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    state = load_game(path)
    assert (state.battles, state.battle_seq, state.battle_card) == ([], 0, None)
    assert "last_report" not in state.model_dump()
    old = Game(content, state)
    old.choose("move:lake")
    old.choose("act:train")
    assert [r.id for r in old.state.battles] == [1]


def test_stale_battle_card_is_dropped(content, game):
    game.state.battle_card = 7  # 卡片指向一場不在紀錄裡的戰鬥
    assert Game(content, game.state).battle_card_id() is None
    assert game.state.battle_card is None


def test_stale_references_are_dropped(content, game):
    s = game.state
    s.pending_event = "removed_event"
    s.player.location = "removed_place"
    s.player.skills["removed_skill"] = 3
    s.player.loadouts["player"][1] = "removed_skill"
    s.player.team.append("ghost")
    fresh = Game(content, s)
    assert fresh.state.pending_event is None
    assert fresh.state.player.location == "town"
    assert fresh.state.player.loadouts["player"][1] is None
    assert "removed_skill" not in fresh.state.player.skills
    assert fresh.state.player.team == ["player", "mate"]
