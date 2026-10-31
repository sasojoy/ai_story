"""主機端：把商城的帳全部匯出成 CSV，對帳用（商城架構設計 4.7）。只讀不改。

每一列一筆帳（照編號）：時間（台灣）、名號、錢包、增減、原因、單號、購買、經手的管理者、說明、那一筆之後這個錢包的餘額。
檔案是 utf-8-sig（Excel 直接開不會亂碼）。結尾在 stderr 印筆數、錢包數、發出（正的）與花掉（負的）的合計、有沒有負的餘額
（餘額＝帳的加總，程式保證不會是負的；這裡再查一次）。
執行：.venv/Scripts/python.exe scripts/mall_ledger.py --out ledger.csv（沒給 --db 就照 TIANXIA_DB 或 saves/tianxia.db）

真的只讀（FB-481）：用 sqlite 的唯讀模式（mode=ro）直接開檔，不走 open_database——那一條會照版本跑遷移（第 5 版的舊檔就地升到
第 6 版），版本一樣時也先拿一下寫入權，檔不存在還會建一個新的。還沒升級的舊檔（第 6 版以前沒有商城的表）印一句就結束、不寫 CSV；
打不開（路徑打錯、不是資料庫）印一句、結束碼 1。
"""
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.database import default_path  # noqa: E402
from tianxia.features.mall.rules import reason_text  # noqa: E402  商城的規則（功能包 tianxia/features/mall/）
from tianxia.wallet import Wallet  # noqa: E402

HEADER = ["編號", "時間（台灣）", "名號", "錢包", "增減", "原因", "單號", "購買", "經手", "說明", "之後的餘額"]
MALL_SCHEMA = 6  # 商城的三張表是第 6 版加的（database.SCHEMA_V6_TABLES）；之後結構再升版，第 6 版以後的檔照樣讀


class ReadOnly:
    """唯讀地開一個資料庫檔，只給 Wallet.export 要的 snapshot()。開不了丟 sqlite3.Error。"""

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.version = self.conn.execute("PRAGMA user_version").fetchone()[0]  # 不是資料庫的檔在這裡就丟

    @contextmanager
    def snapshot(self) -> Iterator[sqlite3.Connection]:
        yield self.conn


def rows(wallet: Wallet, offset_hours: float) -> tuple[list[list[str]], dict[str, int]]:
    """CSV 的每一列與每個錢包最後的餘額。"""
    tz = timezone(timedelta(hours=offset_hours))
    balances: dict[str, int] = {}
    out: list[list[str]] = []
    for row, shown in wallet.export():
        balances[row.owner] = balances.get(row.owner, 0) + row.delta
        out.append([
            str(row.id), datetime.fromtimestamp(row.time, tz=tz).strftime("%Y-%m-%d %H:%M:%S"), shown or "", row.owner,
            str(row.delta), reason_text(row.reason, row.ref), row.ref, "" if row.purchase_id is None else str(row.purchase_id),
            row.admin or "", row.note, str(balances[row.owner]),
        ])
    return out, balances


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把商城的帳全部匯出成 CSV（對帳用，只讀）")
    parser.add_argument("--db", default=None, help="資料庫檔（預設：環境變數 TIANXIA_DB，沒設就是 saves/tianxia.db）")
    parser.add_argument("--out", default=None, help="寫到這個檔（預設印在畫面上）")
    parser.add_argument("--utc-offset", type=float, default=8, help="時間寫哪個時區（預設台灣 +8）")
    args = parser.parse_args(argv)
    path = Path(args.db) if args.db else default_path()
    try:
        db = ReadOnly(path)
    except sqlite3.Error as error:
        print(f"打不開資料庫檔：{path}（{error}）", file=sys.stderr)
        return 1
    try:
        if db.version < MALL_SCHEMA:
            print(f"這份資料庫還是第 {db.version} 版（還沒升級），沒有商城的帳", file=sys.stderr)
            return 0
        lines, balances = rows(Wallet(db), args.utc_offset)  # type: ignore[arg-type]  # Wallet 只讀的那幾個方法只用 snapshot()
    finally:
        db.conn.close()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    writer.writerows(lines)
    if args.out:
        Path(args.out).write_text(buffer.getvalue(), encoding="utf-8-sig", newline="")
    else:
        sys.stdout.write(buffer.getvalue())
    issued = sum(int(row[4]) for row in lines if int(row[4]) > 0)
    spent = -sum(int(row[4]) for row in lines if int(row[4]) < 0)
    negative = sorted(owner for owner, balance in balances.items() if balance < 0)
    print(f"帳 {len(lines)} 筆、錢包 {len(balances)} 個；發出 {issued}、花掉 {spent}、餘額合計 {issued - spent}", file=sys.stderr)
    print(f"負的餘額：{'、'.join(negative) if negative else '沒有'}", file=sys.stderr)
    return 1 if negative else 0


if __name__ == "__main__":
    raise SystemExit(main())
