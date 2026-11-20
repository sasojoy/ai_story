"""主機端：列出資料庫裡名號像官方的角色（含客服、官方、管理員、GM 這類字，core/name_base.staff_like；第 240 批）。只讀不改。

給企劃者在主機上對線上資料庫跑，決定要不要請那些人改名：已經叫這類名號的人登入、玩照舊，只是不能再用易名帖改成另一個這類名字。
只印名號（一行一個，照名號排），最後一行印共幾個；不印陣營、帳號，也不分是誰。
執行：.venv/Scripts/python.exe scripts/list_staff_like_names.py <資料庫檔>

真的只讀：用 sqlite 的唯讀模式（mode=ro）直接開檔（照 scripts/mall_ledger.py），不走 open_database（那一條會跑遷移、檔不存在會建新的）。
打不開（路徑打錯、不是資料庫）印一句、結束碼 1。
"""
from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.core.name_base import staff_like  # noqa: E402


def staff_like_names(path: Path) -> list[str]:
    """這個資料庫裡名號像官方的角色名號（照名號排）。開不了丟 sqlite3.Error。"""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        names = [row[0] for row in conn.execute("SELECT name FROM characters ORDER BY name")]
    finally:
        conn.close()
    return [name for name in names if staff_like(name)]


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper) and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="列出名號像官方的角色（只讀）")
    parser.add_argument("db", help="資料庫檔")
    args = parser.parse_args(argv)
    try:
        found = staff_like_names(Path(args.db))
    except sqlite3.Error as error:
        print(f"打不開這個資料庫：{args.db}（{error}）")
        return 1
    for name in found:
        print(name)
    print(f"共 {len(found)} 個")
    return 0


if __name__ == "__main__":
    sys.exit(main())
