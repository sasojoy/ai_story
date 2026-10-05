"""資料庫備份（線上架構設計 8.5）：伺服器開著也能做的線上備份。

用 SQLite 內建的線上備份（sqlite3.Connection.backup）：拿到的一定是同一個時間點的一致內容。
一定要一步複製完（不給 pages）：資料庫是 WAL 模式，一步讀完是一個讀取快照，不擋寫入的人，也不會被寫入打斷；
分很多步複製的話，步與步之間只要有人寫入，備份就從頭來，資料庫一大、寫入一頻繁就永遠做不完（實測 41MB、每秒三百多筆，十二秒沒完）。
做出來的檔改成 DELETE 日誌模式，是一個自足的 .db，不帶 -wal／-shm，雲端硬碟同步不會只同步到一半。
先寫成 .partial、驗過（integrity_check、結構版本、幾張表的列數）才換上正式檔名；驗不過改名成 .bad 留著查。

刻意不用 tianxia.database.open_database 打開來源：它會照 MIGRATIONS 升級結構，不能替線上那個檔升級。

手動：.venv/Scripts/python.exe scripts/backup_db.py --dest <資料夾>          （資料庫照 TIANXIA_DB，沒設是 saves/tianxia.db）
每天：.venv/Scripts/python.exe scripts/backup_db.py --dest <雲端資料夾> --tag daily --prune
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.database import SCHEMA_VERSION, default_path  # noqa: E402

PREFIX = "tianxia"
TAGS = ("daily", "manual")  # 只有 daily 會被保留規則刪掉；manual（換版前、出事前手動做的）永遠留著
STAMP = "%Y%m%d-%H%M%S"
COUNTED = ("accounts", "characters", "seasons", "chronicle")  # 驗證時數這幾張表，印出來讓人一眼看出是不是空的


class BackupError(Exception):
    """要直接告訴企劃者的錯（找不到資料庫、資料夾寫不進去、備份壞了）。"""


def backup_name(tag: str, now: dt.datetime) -> str:
    return f"{PREFIX}-{tag}-{now.strftime(STAMP)}.db"


def backup(src: Path, dest_dir: Path, *, tag: str, now: dt.datetime) -> Path:
    """把 src 線上備份成 dest_dir/tianxia-<tag>-<時間>.db，驗過才換上正式檔名；回傳正式檔的路徑。"""
    if tag not in TAGS:
        raise ValueError(f"tag 只能是 {TAGS}：{tag!r}")
    src = Path(src)
    if not src.is_file():
        raise BackupError(f"找不到資料庫：{src}")
    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupError(f"備份資料夾建不起來：{dest_dir}（{e}）") from e
    final = dest_dir / backup_name(tag, now)
    partial = final.with_name(final.name + ".partial")
    try:
        source = sqlite3.connect(src, timeout=30)
        try:
            target = sqlite3.connect(partial)
            try:
                source.backup(target)  # 一步複製完：遊戲的資料庫是 WAL，讀的人不擋寫的人（見檔案開頭）
                target.execute("PRAGMA journal_mode = DELETE")
            finally:
                target.close()
        finally:
            source.close()
    except (sqlite3.Error, OSError) as e:
        partial.unlink(missing_ok=True)
        raise BackupError(f"備份資料夾寫不進去，或資料庫讀不到：{dest_dir}（{e}）") from e
    try:
        verify(partial)
    except BackupError:
        os.replace(partial, final.with_name(final.name + ".bad"))
        raise
    os.replace(partial, final)
    return final


def verify(path: Path) -> dict[str, int]:
    """備份檔驗得過：integrity_check 是 ok、結構版本是這版程式認得的、數得出幾張表的列數。回傳版本與列數。"""
    path = Path(path)
    try:
        conn = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)  # as_uri 會跳脫 # 與 %：資料夾名字帶這些字不會驗到別的檔
    except sqlite3.Error as e:
        raise BackupError(f"打不開備份：{path}（{e}）") from e
    try:
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNTED if t in tables}
    except sqlite3.Error as e:
        raise BackupError(f"備份壞了，不是可用的資料庫：{path}（{e}）") from e
    finally:
        conn.close()
    if check != "ok":
        raise BackupError(f"備份沒通過完整性檢查：{path}（{check}）")
    if not 1 <= version <= SCHEMA_VERSION:
        raise BackupError(f"備份的結構版本是 {version}，這版程式只認得 1～{SCHEMA_VERSION}：{path}")
    return {"version": version, **counts}


KEEP_DAILY = 14  # 最近幾個日曆日每天留最新的一份（設計 8.5【預設】）
KEEP_WEEKLY = 8  # 再加最近幾個 ISO 週每週留最新的一份


def _daily_backups(dest_dir: Path) -> list[tuple[dt.datetime, Path]]:
    """資料夾裡認得出來的每日備份（照檔名的時間）；認不出時間的、.partial、.bad、手動的都不算。"""
    found = []
    for path in Path(dest_dir).glob(f"{PREFIX}-daily-*.db"):
        stamp = path.name.removeprefix(f"{PREFIX}-daily-").removesuffix(".db")
        try:
            found.append((dt.datetime.strptime(stamp, STAMP), path))
        except ValueError:
            continue
    return sorted(found)


def prune(dest_dir: Path, now: dt.datetime, *, keep_daily: int = KEEP_DAILY, keep_weekly: int = KEEP_WEEKLY) -> list[Path]:
    """照保留規則刪掉舊的每日備份，回傳刪掉的檔。留下：最近 keep_daily 個日曆日每天最新的一份，
    加上最近 keep_weekly 個 ISO 週每週最新的一份；時間在 now 之後的（時鐘被調過）一律留著。"""
    backups = _daily_backups(dest_dir)
    days = {(now - dt.timedelta(days=i)).date() for i in range(keep_daily)}
    monday = now.date() - dt.timedelta(days=now.weekday())
    weeks = {(monday - dt.timedelta(weeks=i)).isocalendar()[:2] for i in range(keep_weekly)}  # （年, 週）：跨年週數會重複
    newest_of_day: dict[dt.date, Path] = {}
    newest_of_week: dict[tuple[int, int], Path] = {}
    for when, path in backups:  # 已照時間排序：後面的蓋掉前面的，留下的就是最新的
        newest_of_day[when.date()] = path
        newest_of_week[when.isocalendar()[:2]] = path
    keep = {p for d, p in newest_of_day.items() if d in days} | {p for w, p in newest_of_week.items() if w in weeks}
    keep |= {p for when, p in backups if when > now}
    removed = []
    for _, path in backups:
        if path not in keep:
            path.unlink()
            removed.append(path)
    return removed


def describe(report: dict[str, int]) -> str:
    names = {"accounts": "帳號", "characters": "角色", "seasons": "季", "chronicle": "江湖史"}
    parts = [f"結構第 {report['version']} 版"] + [f"{names[t]} {report[t]}" for t in COUNTED if t in report]
    return "、".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="備份遊戲資料庫（伺服器開著也可以）")
    parser.add_argument("--db", default=None, help="要備份的資料庫（預設：環境變數 TIANXIA_DB，沒設是 saves/tianxia.db）")
    parser.add_argument("--dest", required=True, help="備份放哪個資料夾（每天的備份放雲端硬碟的同步資料夾）")
    parser.add_argument("--tag", choices=TAGS, default="manual", help="manual（預設，永遠留著）或 daily（照保留規則刪舊）")
    parser.add_argument("--prune", action="store_true", help="做完之後照保留規則刪掉舊的每日備份（只能搭 --tag daily）")
    args = parser.parse_args(argv)
    if args.prune and args.tag != "daily":
        parser.error("--prune 只能搭 --tag daily：手動備份永遠留著")
    src = Path(args.db) if args.db else default_path()
    try:
        out = backup(src, Path(args.dest), tag=args.tag, now=dt.datetime.now())
    except BackupError as e:
        print(f"備份失敗：{e}", file=sys.stderr)
        return 1
    print(f"已備份：{out}（{describe(verify(out))}）")
    if args.prune:
        try:
            removed = prune(Path(args.dest), dt.datetime.now())
        except OSError as e:  # 雲端硬碟正在同步時舊檔可能刪不掉：新的備份已經做好，明天再刪，但要讓排程看得出這次不完全成功
            print(f"刪舊備份失敗（今天這份備份已經做好）：{e}", file=sys.stderr)
            return 1
        print(f"刪掉 {len(removed)} 份舊的每日備份")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
