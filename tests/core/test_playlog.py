"""真人量表（減法季批 0，設計稿第十章；tianxia/playlog.py、資料庫第 7 版）：每個帳號每天按了哪幾顆、第幾天不再上線、
第一次寫隨口應對與第一次跟人物說話是第幾天。只有伺服器記真人的請求，不露給玩家。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tianxia import database
from tianxia.database import Database, open_database
from tianxia.playlog import FIGURE_TALK, FREE_TEXT, PlayLog, button_of, last_days, retention


@pytest.fixture
def log(tmp_path):
    return PlayLog(open_database(tmp_path / "t.db"))


def test_buttons_are_grouped_without_places_people_or_numbers():
    assert button_of("act:train") == "act:train"
    assert button_of("act:challenge:luzhi") == "act:challenge"
    assert button_of("explore:gather:say") == "explore:gather"
    assert button_of("explore") == "explore"
    assert button_of("choice:2") == "choice"
    assert button_of("talk:leave") == "talk"
    assert button_of("call:luzhi") == "call"
    assert button_of("battle:act:3") == "battle"
    assert button_of("") == ""


def test_a_day_counts_each_button_and_seen_alone_is_an_empty_day(log):
    log.seen("沈浪", 3, 100)
    log.press("沈浪", 3, 100, "act:train")
    log.press("沈浪", 3, 100, "act:train")
    log.press("沈浪", 3, 100, "explore:gather")
    log.press("沈浪", 3, 100, "")  # 空的不記
    log.seen("沈浪", 3, 102)  # 只上線、沒按
    log.seen("白飛", 4, 100)  # 別一季
    (a,) = log.accounts(3)
    assert a.days == {1, 3}
    assert a.buttons == {"act:train": 2, "explore:gather": 1}
    with log.db.snapshot() as conn:
        rows = conn.execute("SELECT day, buttons FROM action_counts WHERE owner = '沈浪' ORDER BY day").fetchall()
    assert [(r["day"], r["buttons"]) for r in rows] == [(100, '{"act:train": 2, "explore:gather": 1}'), (102, "{}")]


def test_only_the_first_time_is_kept(log):
    assert log.first("沈浪", 3, FREE_TEXT, 101, 5.0) is True
    assert log.first("沈浪", 3, FREE_TEXT, 104, 9.0) is False
    assert log.first("沈浪", 3, FIGURE_TALK, 103, 7.0) is True
    assert log.first("沈浪", 4, FREE_TEXT, 200, 1.0) is True  # 新的一季重記
    with pytest.raises(ValueError):
        log.first("沈浪", 3, "fight", 101, 1.0)
    (a,) = log.accounts(3, start_day=100)
    assert a.firsts == {FREE_TEXT: 2, FIGURE_TALK: 4}


def test_retention_and_the_last_day(log):
    for owner, days in {"甲": (100, 101, 102), "乙": (100, 106), "丙": (100,), "丁": (101, 102)}.items():
        for d in days:
            log.seen(owner, 1, d)
    accounts = log.accounts(1)
    assert retention(accounts, 3) == pytest.approx(2 / 3)  # 頭一天來的甲乙丙，第 3 天（含）以後還來的是甲、乙
    assert retention(accounts, 7) == pytest.approx(1 / 3)
    assert last_days(accounts) == {3: 2, 7: 1, 1: 1}
    assert retention([], 3) is None


def test_a_version_6_file_upgrades_to_7_with_the_two_empty_tables(tmp_path):
    path = tmp_path / "v6.db"
    conn = sqlite3.connect(path)
    for sql in database.SCHEMA[: len(database.SCHEMA) - len(database.SCHEMA_V7_TABLES) - len(database.SCHEMA_V8_CHANGES) - len(database.SCHEMA_V9_TABLES)]:
        conn.execute(sql)
    conn.execute("INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('沈浪', '沈浪', 0, NULL, '{}')")
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()
    db = Database(path)
    with db.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION == 9
        assert c.execute("SELECT COUNT(*) FROM action_counts").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM action_firsts").fetchone()[0] == 0
        assert c.execute("SELECT name FROM characters").fetchone()[0] == "沈浪"
    db.close()


def test_the_host_report_prints_totals_without_names(tmp_path, capsys):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import play_metrics

    path = tmp_path / "t.db"
    log = PlayLog(open_database(path))
    for owner, days in {"沈浪": (20000, 20002, 20006), "白飛": (20000,)}.items():
        for d in days:
            log.press(owner, 2, d, "act:train")
    log.first("沈浪", 2, FREE_TEXT, 20002, 1.0)
    assert play_metrics.day_number("1970-01-02") == 1
    assert play_metrics.main(["--db", str(path)]) == 0
    out = capsys.readouterr().out
    assert "第 2 季：2 個帳號上線過" in out
    assert "第 3 天留存：50%（判準 50%，過）" in out and "第 7 天留存：50%（判準 40%，過）" in out
    assert "第一次寫隨口應對：1 人，中位數第 3 天；還沒做過 1 人" in out
    assert "第一次看全區：0 人，沒有人；還沒做過 2 人" in out and "第 2 天以前寫過隨口應對：0%（判準 50%，未過）" in out
    assert "沈浪" not in out and "白飛" not in out  # 不印名號
    old = tmp_path / "v6.db"
    conn = sqlite3.connect(old)
    conn.execute("PRAGMA user_version = 6")
    conn.close()
    assert play_metrics.main(["--db", str(old)]) == 0
    assert "還沒有真人量表" in capsys.readouterr().out
