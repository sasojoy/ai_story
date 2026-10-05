"""還原資料庫（線上架構設計 8.5、9.3 第 3 條）：先停掉伺服器與假人程式，再執行這支。

1. 驗過備份（同 backup_db.verify：完整性、結構版本）。
2. 先把備份複製成 <檔名>.restoring 再驗一次：磁碟滿了、複製壞了，都在動到現在的資料庫之前就停下來。
3. 把現在的資料庫連同 -wal／-shm／-journal 一起改名成 <檔名>.pre-restore-<時間>（後面接 -wal 等）：舊檔一定留著，
   還原錯了把它們一起改名回去就好。殘留的 -wal 屬於舊檔，跟著移走，不然 SQLite 會把它套進還原回來的檔；
   資料庫檔已經不在、只剩殘留的 -wal 等時也一樣搬走（搬走比拒絕安全）。
4. 把 .restoring 改名成資料庫。下次伺服器打開時自己換回 WAL 模式。

只有 Windows 擋得住「伺服器還開著」：Windows 上檔案還被打開（伺服器或假人程式還開著）時改名會失敗，
這時停下來、什麼都不動。Linux 與 macOS 的改名不管檔案有沒有被打開都會成功，在那裡這支腳本不會攔你，
會把還開著的資料庫搬走——務必自己先停掉伺服器與假人程式。

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


def aside_sidecars(aside: Path) -> list[Path]:
    """舊的資料庫搬走時一起搬走的 -wal／-shm／-journal（有幾個列幾個）。"""
    return [p for p in (aside.with_name(aside.name + suffix) for suffix in SIDECARS) if p.exists()]


def _move(source: Path, dest: Path) -> None:
    try:
        os.replace(source, dest)
    except PermissionError as e:
        raise BackupError(f"資料庫還開著，請先停掉伺服器與假人程式再還原：{source}") from e


def restore(backup_file: Path, target: Path, *, now: dt.datetime) -> Path | None:
    """把 backup_file 還原成 target；回傳舊檔改名後的路徑，原本沒有檔、也沒有殘留檔是 None。
    資料庫檔不在、只剩殘留的 -wal／-shm／-journal 時也會把它們搬走，回傳的路徑本身就不存在，要看 aside_sidecars。"""
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
    candidate = target.with_name(f"{target.name}.pre-restore-{now.strftime(STAMP)}")
    aside = None  # 有東西真的搬走之後才設，出錯時才不會指著一個不存在的檔
    try:
        if target.exists():
            _move(target, candidate)
            aside = candidate
        # 殘留的 -wal／-shm／-journal 不管資料庫檔還在不在都要搬：資料庫檔不見了、只剩 -wal 時，
        # 它照樣會被 SQLite 套進還原回來的檔（實測：空的江湖史還原後多出 500 筆）
        for suffix in SIDECARS:
            side = target.with_name(target.name + suffix)
            if side.exists():
                _move(side, candidate.with_name(candidate.name + suffix))
                aside = candidate
        os.replace(staged, target)
    except BaseException as e:
        staged.unlink(missing_ok=True)
        if aside is not None and isinstance(e, OSError):
            raise BackupError(
                f"還原到一半失敗：原本的資料庫搬到了 {aside}（旁邊如果有接 -wal／-shm／-journal 的檔也是）。"
                f"要退回就把它們一起改名回去，名字去掉 .pre-restore-… 那一段（{e}）"
            ) from e
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
        if aside.exists():
            print(f"還原前的資料庫留在：{aside}")
        else:
            print(f"資料庫檔本來就不在，只搬走了殘留的檔（下面）：名字是 {aside.name} 後面接 -wal 等")
        moved = aside_sidecars(aside)
        if moved:
            print("跟著搬走的 -wal／-shm／-journal（還原錯了要退回時，要跟資料庫檔一起改名回去）：")
            for path in moved:
                print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
