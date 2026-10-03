import json

import pytest
from pydantic import ValidationError

from conftest import walk_to
from tianxia.characters import name_key, open_characters
from tianxia.engine import Game
from tianxia.state import BotProfile, Rumor


@pytest.fixture
def characters():
    return open_characters()


def _put_raw(characters, name: str, data: str) -> None:
    """直接寫一列（模擬舊格式或壞掉的存檔）。"""
    with characters.db.transaction() as conn:
        conn.execute(
            "INSERT INTO characters (key, name, is_bot, faction, data) VALUES (?, ?, 0, NULL, ?) "
            "ON CONFLICT (key) DO UPDATE SET data = excluded.data",
            (name_key(name), name, data),
        )


def test_roundtrip(characters, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.player.member.neili = 12.5
    characters.save(game.state)
    assert characters.load("沈浪").model_dump() == game.state.model_dump()  # 賽季不存檔，比對存得下來的部分


def test_roundtrip_keeps_battle_records(characters, game):
    walk_to(game, "lake")
    game._squad_encounter("thug")  # 直接觸發遭遇，不依賴 explore 的隨機事件/遭遇機率
    characters.save(game.state)
    loaded = characters.load("沈浪")
    assert loaded.model_dump() == game.state.model_dump()
    assert loaded.battles[0].opponent == "水寇小隊" and loaded.battle_card == 1


def test_1a_save_without_battle_records_still_loads(characters, content, game):
    dump = game.state.model_dump(mode="json")
    for key in ("battles", "battle_seq", "battle_card"):
        del dump[key]
    dump["last_report"] = ["⚔ 對陣：翻江龍", "── 第1回合 ──"]  # 1a 的存檔只留最近一場的戰報文字
    _put_raw(characters, "沈浪", json.dumps(dump, ensure_ascii=False))
    state = characters.load("沈浪")
    assert (state.battles, state.battle_seq, state.battle_card) == ([], 0, None)
    assert "last_report" not in state.model_dump()
    old = Game(content, state)
    walk_to(old, "lake")
    old._squad_encounter("thug")
    assert [r.id for r in old.state.battles] == [1]


def test_pre_fix_battle_record_without_changes_field_still_loads(characters, game):
    """在「結果／獲得與損失」拆分上線前存的戰報，BattleRecord 還沒有 changes 欄位；讀檔不能炸。"""
    walk_to(game, "lake")
    game._squad_encounter("thug")
    dump = game.state.model_dump(mode="json")
    del dump["battles"][0]["changes"]  # 模擬舊版存檔
    _put_raw(characters, "沈浪", json.dumps(dump, ensure_ascii=False))
    state = characters.load("沈浪")
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


def test_an_old_save_that_carries_a_season_still_loads(characters, content, game):
    dump = game.state.model_dump(mode="json")
    dump["world"] = {"time": 999.0, "rumors": [{"time": 0, "text": "舊傳聞"}]}  # 第 1 期以前的存檔夾帶一份賽季
    _put_raw(characters, "沈浪", json.dumps(dump, ensure_ascii=False))
    loaded = Game(content, characters.load("沈浪"), world=game.world)
    assert loaded.state.world.time == game.world.get_season().time  # 夾帶的那份被共用賽季取代


def test_rumor_at_a_removed_place_loses_its_location(characters, content, game):
    """傳聞現在跟著共用賽季走（見 Game._reconcile_season），不是存在玩家自己的存檔裡——
    要模擬「內容已不存在的地點」要改共用儲存裡那一份，不是玩家存檔裡的 world 欄位
    （那個欄位讀檔時會被共用賽季整個覆蓋掉）。"""
    season = game.world.get_season()
    season.rumors.append(Rumor(time=0, text="舊地方的傳聞", location="removed_place"))
    season.rumors.append(Rumor(time=0, text="湖邊的傳聞", location="lake"))
    game.world.save_season(season)
    characters.save(game.state)
    fresh = Game(content, characters.load("沈浪"), world=game.world)
    assert [(r.text, r.location) for r in fresh.state.world.rumors] == [("舊地方的傳聞", None), ("湖邊的傳聞", "lake")]
    assert "湖邊的傳聞" in fresh.place_detail("lake")  # 查詢不會當機


def test_the_save_no_longer_carries_the_season(characters, game):
    """線上架構設計 3.1：角色存檔不再夾帶一份全服賽季。"""
    characters.save(game.state)
    with characters.db.snapshot() as conn:
        data = json.loads(conn.execute("SELECT data FROM characters WHERE key = ?", (name_key("沈浪"),)).fetchone()["data"])
    assert "world" not in data and data["player"]["name"] == "沈浪"


def test_names_ignore_case(characters, content):
    """線上架構設計第六節：名號同服不重複，比對不分大小寫。"""
    characters.save(Game.new(content, "Rayal").state)
    assert characters.exists("rayal") and characters.load("RAYAL").player.name == "Rayal"
    assert characters.names() == {"Rayal"}


def test_all_skips_unreadable_saves_and_can_pick_only_bots(characters, content):
    characters.save(Game.new(content, "真人").state)
    bot = Game.new(content, "假人").state
    bot.player.bot = BotProfile(personality="普通", seed=1)
    characters.save(bot)
    _put_raw(characters, "壞掉的", "{not json")
    assert [s.player.name for s in characters.all()] == ["假人", "真人"]
    assert [s.player.name for s in characters.all(bots_only=True)] == ["假人"]
    assert "壞掉的" in characters.names()  # 讀不懂的存檔也占著名號


def test_an_unreadable_save_is_moved_aside_not_deleted(characters):
    _put_raw(characters, "壞掉的", "{not json")
    with pytest.raises(ValidationError):
        characters.load("壞掉的")
    characters.backup("壞掉的")
    assert characters.load("壞掉的") is None
    with characters.db.snapshot() as conn:
        assert conn.execute("SELECT data FROM character_backups").fetchone()["data"] == "{not json"
