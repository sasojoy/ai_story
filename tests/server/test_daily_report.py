"""每天一份玩家數字（scripts/daily_report.py，2026-11-25）：只算真人、不列名號、只讀、短報先三行重點、備份失敗寫第一行。"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_report  # noqa: E402

from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.database import close_all, open_database  # noqa: E402
from tianxia.state import new_game_state  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "content"
TODAY = dt.date(2026, 11, 25)
NOW = dt.datetime(2026, 11, 25, 8, 0)


def _at(d: dt.date, hour: int = 12) -> float:
    return dt.datetime.combine(d, dt.time(hour), tzinfo=daily_report.TAIWAN).timestamp()


def make_db(tmp_path: Path) -> Path:
    """真人五個（甲乙丙丁戊）、假人兩個；第 4 季。"""
    path = tmp_path / "tianxia.db"
    db = open_database(path)
    content = load_content(FIXTURE)
    store = CharacterStore(db)
    for name in ("甲", "乙", "丙", "丁", "戊", "假一", "假二"):
        store.save(new_game_state(content, name))
    close_all()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE characters SET is_bot = 1 WHERE name LIKE '假%'")
    conn.execute("INSERT INTO seasons (number, data) VALUES (4, '{}')")
    y = TODAY - dt.timedelta(days=1)
    created = {"甲": y - dt.timedelta(days=20), "乙": y - dt.timedelta(days=1), "丙": y, "丁": y - dt.timedelta(days=4), "戊": y - dt.timedelta(days=3)}
    for i, (name, d) in enumerate(created.items(), 1):
        conn.execute("INSERT INTO accounts (id, character, character_key, created) VALUES (?, ?, ?, ?)", (i, name, name, _at(d)))
    # 丙還在城門口
    data = json.loads(conn.execute("SELECT data FROM characters WHERE key = '丙'").fetchone()[0])
    data["pending_event"] = "opening_gate"
    conn.execute("UPDATE characters SET data = ? WHERE key = '丙'", (json.dumps(data),))
    yd = daily_report.taiwan_day(y)
    visits = [("甲", yd - 10, {"act:explore": 3}), ("甲", yd, {"act:explore": 30, "talk": 5}), ("乙", yd - 1, {"choice": 2}),
              ("乙", yd, {"act:explore": 2}), ("丙", yd, {}), ("丁", yd - 4, {"choice": 1, "act:explore": 1}), ("假一", yd, {"act:explore": 99})]
    for owner, d, buttons in visits:
        conn.execute("INSERT INTO action_counts (owner, season, day, buttons) VALUES (?, 4, ?, ?)", (owner, d, json.dumps(buttons)))
    conn.execute("INSERT INTO mall_ledger (owner, time, delta, reason, ref) VALUES ('甲', ?, -120, 'buy', 'r1')", (_at(y),))
    conn.execute("INSERT INTO mall_ledger (owner, time, delta, reason, ref) VALUES ('乙', ?, 100, 'grant', 'r2')", (_at(y),))
    conn.commit()
    conn.close()
    return path


def _status(tmp_path: Path, **kw) -> Path:
    data = {"time": "2026-11-25T05:00:00", "ok": True, "file": "x", "bytes": 42_000_000, "characters": 7, "error": ""} | kw
    path = tmp_path / "backup_status.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_numbers_count_real_players_only(tmp_path):
    db = make_db(tmp_path)
    n = daily_report.collect(db, TODAY, status=_status(tmp_path), now=NOW)
    assert (n.season, n.bots, n.online, n.online_week, n.online_season) == (4, 2, 3, 4, 4)
    assert (n.registered, n.reg_before, n.reg_before_back) == (1, 1, 1)
    assert n.idle == 1 and n.few == 1  # 丙一顆沒按、乙按了 2 次
    assert n.presses["act:explore"] == 32  # 假人的 99 次不算
    assert n.stages == {"還在城門口沒選路": 1, "選了路未滿 5 級": 3}  # 乙丙丁戊；甲是 20 天前的
    assert n.gone == 2 and n.gone_last == {"choice": 1, "act:explore": 1}  # 丁（4 天前最後一次）、戊（從沒來過）
    assert (n.buyers, n.spent) == (1, 120)


def test_short_report_leads_with_three_lines_and_no_names(tmp_path):
    db = make_db(tmp_path)
    short, full = daily_report.render(daily_report.collect(db, TODAY, status=_status(tmp_path), now=NOW), TODAY)
    lines = short.splitlines()
    assert lines[1].startswith("・昨天上線 3 人") and "最多停在：選了路未滿 5 級 3 人" in lines[2] and lines[3].startswith("・備份：成功")
    assert len(short) < 600
    for name in ("甲", "乙", "丙", "丁", "戊", "假一"):
        assert name not in full


def test_backup_failure_goes_first(tmp_path):
    db = make_db(tmp_path)
    short, _ = daily_report.render(daily_report.collect(db, TODAY, status=_status(tmp_path, ok=False, error="磁碟滿了"), now=NOW), TODAY)
    assert short.splitlines()[1].startswith("⚠ 備份失敗") and "磁碟滿了" in short
    stale = _status(tmp_path, time="2026-11-23T05:00:00")
    short, _ = daily_report.render(daily_report.collect(db, TODAY, status=stale, now=NOW), TODAY)
    assert short.splitlines()[1].startswith("⚠ 備份失敗") and "超過 36 小時" in short
    short, _ = daily_report.render(daily_report.collect(db, TODAY, status=tmp_path / "nope.json", now=NOW), TODAY)
    assert "排程還沒裝" in short.splitlines()[1]


def test_main_only_reads_and_saves_without_a_webhook(tmp_path, capsys):
    db = make_db(tmp_path)
    before = db.read_bytes()
    out = tmp_path / "report"
    args = ["--db", str(db), "--date", "2026-11-25", "--status", str(_status(tmp_path)), "--config", str(tmp_path / "none.json"), "--out", str(out)]
    assert daily_report.main(args) == 0
    assert "沒設 relay 或 discord_webhook" in capsys.readouterr().out
    assert (out / "2026-11-25.txt").read_text(encoding="utf-8") == (out / "latest.txt").read_text(encoding="utf-8")
    assert db.read_bytes() == before  # 唯讀：一個位元都沒動


FAKE_RELAY = '''import sys
args = sys.argv[1:]
text = sys.stdin.buffer.read().decode("utf-8")
log, fail = sys.argv[0] + ".log", sys.argv[0] + ".fail"
import os
if os.path.exists(fail):
    n = int(open(fail).read() or "0")
    if n > 0:
        open(fail, "w").write(str(n - 1))
        sys.exit(1)
open(log, "a", encoding="utf-8").write(repr((args, text)) + "\\n")
sys.stdout.buffer.write("已送出".encode("utf-8"))
'''


def _relay_setup(tmp_path: Path, fails: int = 0):
    import ast
    script = tmp_path / "relay.py"
    script.write_text(FAKE_RELAY, encoding="utf-8")
    if fails:
        (tmp_path / "relay.py.fail").write_text(str(fails))
    cfg = tmp_path / "daily_report.json"
    cfg.write_text(json.dumps({"relay": {"script": str(script), "channel": "123"}, "discord_webhook": "http://127.0.0.1:9/never"}), encoding="utf-8")
    sent = lambda: [ast.literal_eval(line) for line in (tmp_path / "relay.py.log").read_text(encoding="utf-8").splitlines()] if (tmp_path / "relay.py.log").exists() else []  # noqa: E731
    return cfg, sent


def test_relay_sends_the_short_report_as_utf8(tmp_path, capsys):
    db = make_db(tmp_path)
    cfg, sent = _relay_setup(tmp_path)
    args = ["--db", str(db), "--date", "2026-11-25", "--status", str(_status(tmp_path)), "--config", str(cfg), "--out", str(tmp_path / "o")]
    assert daily_report.main(args) == 0  # relay 跟 webhook 都有時走 relay（webhook 那個網址連不上，走到就會失敗）
    [(argv, text)] = sent()
    assert argv == ["send", "123", "-"] and text.startswith("【天下大勢　每日數字 11/25】") and "【細項】" not in text


def test_relay_retries_once_then_fails_but_keeps_the_file(tmp_path, capsys):
    db = make_db(tmp_path)
    cfg, sent = _relay_setup(tmp_path, fails=1)
    args = ["--db", str(db), "--date", "2026-11-25", "--status", str(_status(tmp_path)), "--config", str(cfg), "--out", str(tmp_path / "o")]
    assert daily_report.main(args) == 0 and len(sent()) == 1  # 第一次失敗、第二次成功
    (tmp_path / "relay.py.fail").write_text("5")
    assert daily_report.main(args) == 1 and len(sent()) == 1  # 兩次都失敗：不再試第三次
    assert "貼不到 Discord" in capsys.readouterr().err and (tmp_path / "o" / "latest.txt").is_file()


def test_long_report_is_cut_to_one_message():
    text = daily_report.fit("字" * 5000)
    assert len(text) == 2000 and text.endswith("（全文在主機）")
    assert daily_report.fit("短") == "短"


def test_short_report_never_shows_code_names(tmp_path):
    import re
    db = make_db(tmp_path)
    n = daily_report.collect(db, TODAY, status=_status(tmp_path), now=NOW)
    n.presses.update({"story": 9, "road": 7, "act:duty": 5, "zzz_unknown": 4, "act:whatever": 3})
    n.gone_last.update({"weird:thing": 2})
    short, full = daily_report.render(n, TODAY)
    assert "奇事 9" in short and "趕路 7" in short and "軍務 5" in full and "其他 7" in full
    assert not re.search(r"[A-Za-z]", full.replace("MB", ""))  # 英文代號一個都不印（MB 是單位）
