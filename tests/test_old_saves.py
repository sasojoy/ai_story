"""舊存檔一定要讀得回來（悟意境開工前補的回歸測試）。

fixtures/old_saves/v2_main_b8a388c.json 是 main 在 b8a388c（悟意境動存檔欄位之前、資料庫第 2 版）用真實內容讓整季機器人
玩了三千步存下來的樣子：一個角色的存檔、全服登記的三門合成武學、兩個合併出來的意境。之後的版本加欄位時，這份檔不能改——
改了它就不是在測「真的舊檔」。"""
import json
import sqlite3
from pathlib import Path

from tianxia import database, insights
from tianxia.characters import open_characters
from tianxia.content import load_content
from tianxia.database import SCHEMA_VERSION, open_database
from tianxia.engine import Game
from tianxia.martial_arts import Insight, MartialArt
from tianxia.sqlite_world import open_world
from tianxia.state import GameState

ROOT = Path(__file__).resolve().parent.parent
OLD = json.loads((Path(__file__).parent / "fixtures" / "old_saves" / "v2_main_b8a388c.json").read_text(encoding="utf-8"))


def test_an_old_character_save_loads_with_the_new_fields_empty():
    state = GameState.model_validate(OLD["state"])
    assert state.player.sensing is None
    assert state.player.own_insights == {} and state.player.sense_misses == {}
    assert all(entry.glyph == [] for entry in state.journal)
    assert state.player.insights == OLD["state"]["player"]["insights"]  # 舊的意境一個都沒掉


def test_old_registered_arts_and_insights_load():
    arts = [MartialArt.model_validate(a) for a in OLD["skills"]]
    assert arts and all(a.insight_attr is None for a in arts)
    merged = [Insight.model_validate(i) for i in OLD["insights"]]
    assert merged and all(i.glyph == [] and not i.place for i in merged)


def _version_two_file(path):
    conn = sqlite3.connect(path)
    for statement in database.SCHEMA_V1 + database.SCHEMA_V2_TABLES:
        conn.execute(statement)
    conn.execute("PRAGMA user_version = 2")
    return conn


def test_a_version_two_file_with_an_old_save_upgrades_and_plays(tmp_path):
    """第 2 版的檔（悟意境之前）：打開時就地升到第 3 版、多一張空的首悟表，舊角色讀得回來、照樣能玩，
    舊的合併意境照樣查得到。"""
    path = tmp_path / "v2.db"
    state = GameState.model_validate(OLD["state"])
    name = state.player.name
    conn = _version_two_file(path)
    conn.execute("INSERT INTO world (id, data) VALUES (1, '{\"season_number\": 1, \"tianji\": 0}')")
    conn.execute(
        "INSERT INTO characters (key, name, is_bot, faction, data) VALUES (?, ?, 0, NULL, ?)",
        (name, name, json.dumps(OLD["state"], ensure_ascii=False)),
    )
    for art in OLD["skills"]:
        conn.execute("INSERT INTO skills (season, name, creator, data) VALUES (1, ?, ?, ?)",
                     (art["id"], art.get("creator"), json.dumps(art, ensure_ascii=False)))
    for ins in OLD["insights"]:
        conn.execute("INSERT INTO insights (season, name, creator, data) VALUES (1, ?, ?, ?)",
                     (ins["id"], ins.get("creator"), json.dumps(ins, ensure_ascii=False)))
    conn.commit()
    conn.close()

    db = open_database(path)
    with db.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 3
        assert c.execute("SELECT COUNT(*) FROM insight_firsts").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == len(OLD["skills"])
    loaded = open_characters(path).load(name)
    assert loaded is not None and loaded.player.insights == state.player.insights
    world = open_world(path)
    for ins in OLD["insights"]:
        assert world.get_insight(ins["id"]).name == ins["name"]
        assert insights.resolve(ins["id"], load_content(ROOT / "content"), world, loaded) is not None
    game = Game(load_content(ROOT / "content"), loaded, world=world)
    assert game.options()  # 讀回來的角色照樣有事可做
