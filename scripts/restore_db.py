"""還原資料庫（線上架構設計 8.5、9.3 第 3 條）：先停掉伺服器與假人程式，再執行這支。

1. 驗過備份（同 backup_db.verify：完整性、結構版本）。
2. 先把備份複製成 <檔名>.restoring 再驗一次：磁碟滿了、複製壞了，都在動到現在的資料庫之前就停下來。
3. 把現在的資料庫連同 -wal／-shm 一起改名成 <檔名>.pre-restore-<時間>：舊檔一定留著，還原錯了改名回去就好；
   殘留的 -wal 屬於舊檔，跟著移走，不然 SQLite 會把它套進還原回來的檔。
   在 Windows 上，檔案還被打開（伺服器或假人程式還開著）時改名會失敗：這時停下來，什麼都不動。
4. 把 .restoring 改名成資料庫。下次伺服器打開時自己換回 WAL 模式。

執行：.venv/Scripts/python.exe scripts/restore_db.py <備份檔> [--db <資料庫檔>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backup_db import BackupError, STAMP, describe, verify  # noqa: E402
from tianxia.database import default_path  # noqa: E402

SIDECARS = ("-wal", "-shm", "-journal")


def restore(backup_file: Path, target: Path, *, now: dt.datetime) -> Path | None:
    """把 backup_file 還原成 target；回傳舊檔改名後的路徑（原本沒有檔是 None）。"""
    backup_file = Path(backup_file)
    verify(backup_file)
    target = Path(target)
    staged = target.with_name(target.name + ".restoring")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup_file, staged)
        verify(staged)
    except OSError as e:
        staged.unlink(missing_ok=True)
        raise BackupError(f"備份複製不過去，現在的資料庫沒有動（磁碟空間夠嗎？）：{target.parent}（{e}）") from e
    except BackupError:
        staged.unlink(missing_ok=True)
        raise
    aside = None  # 舊檔真的搬走之後才設，出錯時才不會指著一個不存在的檔
    try:
        if target.exists():
            candidate = target.with_name(f"{target.name}.pre-restore-{now.strftime(STAMP)}")
            try:
                os.replace(target, candidate)
            except PermissionError as e:
                raise BackupError(f"資料庫還開著，請先停掉伺服器與假人程式再還原：{target}") from e
            aside = candidate
            for suffix in SIDECARS:
                side = target.with_name(target.name + suffix)
                if side.exists():
                    os.replace(side, aside.with_name(aside.name + suffix))
        os.replace(staged, target)
    except BaseException as e:
        staged.unlink(missing_ok=True)
        if aside is not None and isinstance(e, OSError):
            raise BackupError(f"還原到一半失敗：原本的資料庫在 {aside}，把它改名回 {target.name} 就好（{e}）") from e
        raise
    return aside


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="從備份還原遊戲資料庫（先停掉伺服器與假人程式）")
    parser.add_argument("backup", help="備份檔（tianxia-daily-…db 或 tianxia-manual-…db）")
    parser.add_argument("--db", default=None, help="要還原成哪個資料庫（預設：環境變數 TIANXIA_DB，沒設是 saves/tianxia.db）")
    args = parser.parse_args(argv)
    target = Path(args.db) if args.db else default_path()
    try:
        aside = restore(Path(args.backup), target, now=dt.datetime.now())
    except BackupError as e:
        print(f"還原失敗：{e}", file=sys.stderr)
        return 1
    print(f"已還原：{target}（{describe(verify(target))}）")
    if aside is not None:
        print(f"還原前的資料庫留在：{aside}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
