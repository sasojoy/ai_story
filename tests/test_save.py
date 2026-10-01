import json

from tianxia.engine import Game
from tianxia.save import load_game, save_game


def test_roundtrip(tmp_path, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.world.flags.add("blocked")
    game.state.player.member.neili = 12.5
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    assert load_game(path) == game.state


def test_roundtrip_keeps_battle_records(tmp_path, game):
    game.choose("move:lake")
    game._squad_encounter("thug")  # 直接觸發遭遇，不依賴 explore 的隨機事件/遭遇機率
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
    old._squad_encounter("thug")
    assert [r.id for r in old.state.battles] == [1]


def test_pre_fix_battle_record_without_changes_field_still_loads(tmp_path, game):
    """在「結果／獲得與損失」拆分上線前存的戰報，BattleRecord 還沒有 changes 欄位；讀檔不能炸。"""
    game.choose("move:lake")
    game._squad_encounter("thug")
    dump = game.state.model_dump(mode="json")
    del dump["battles"][0]["changes"]  # 模擬舊版存檔
    path = tmp_path / "old_battle.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    state = load_game(path)
    assert state.battles[0].changes == []


def test_stale_battle_card_is_dropped(content, game):
    game.state.battle_card = 7  # 卡片指向一場不在紀錄裡的戰鬥
    assert Game(content, game.state).battle_card_id() is None
    assert game.state.battle_card is None


def test_stale_references_are_dropped(content, game):
    s = game.state
    s.pending_event = "removed_event"
    s.player.location = "removed_place"
    s.player.member.wugong_id = "removed_skill"
    s.player.team.append("ghost")
    fresh = Game(content, s)
    assert fresh.state.pending_event is None
    assert fresh.state.player.location == "town"
    assert fresh.state.player.member.wugong_id is None
    assert "ghost" not in fresh.state.player.team


def test_old_rumors_without_a_location_still_load(tmp_path, game):
    from tianxia.state import Rumor

    game.state.world.rumors.append(Rumor(time=0, text="舊傳聞", location="lake"))
    dump = game.state.model_dump(mode="json")
    del dump["world"]["rumors"][0]["location"]  # 模擬大地圖上線前的存檔
    path = tmp_path / "old_rumor.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    state = load_game(path)
    assert (state.world.rumors[0].text, state.world.rumors[0].location) == ("舊傳聞", None)


def test_rumor_at_a_removed_place_loses_its_location(tmp_path, content, game):
    """傳聞現在跟著共用賽季走（見 Game._reconcile_season），不是存在玩家自己的存檔裡——
    要模擬「內容已不存在的地點」要改共用儲存裡那一份，不是玩家存檔裡的 world 欄位
    （那個欄位讀檔時會被共用賽季整個覆蓋掉）。"""
    from tianxia.state import Rumor

    season = game.world.get_season()
    season.rumors.append(Rumor(time=0, text="舊地方的傳聞", location="removed_place"))
    season.rumors.append(Rumor(time=0, text="湖邊的傳聞", location="lake"))
    game.world.save_season(season)
    path = tmp_path / "stale_rumor.json"
    save_game(game.state, path)
    fresh = Game(content, load_game(path), world=game.world)
    assert [(r.text, r.location) for r in fresh.state.world.rumors] == [("舊地方的傳聞", None), ("湖邊的傳聞", "lake")]
    assert "湖邊的傳聞" in fresh.place_detail("lake")  # 查詢不會當機
