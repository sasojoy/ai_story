"""主機端（條款第 249 批）：列出「現在會被伺服器擋下會改東西的請求」的帳號——必須同意條款而還沒同意的。只讀不改。

執行：.venv/Scripts/python.exe scripts/list_terms_must.py <主資料庫檔>（設定照伺服器同一份：TIANXIA_PROFILE，沒帶是 season21）
主資料庫與 <stem>-terms.sqlite 旁檔都用 sqlite 的唯讀模式（mode=ro）開：不跑遷移、不建表、旁檔不在不建（當作沒有人同意過）。
判斷用條款包同一支（tianxia/features/terms/rules.need，經 audit.must_rows）。一行一個：登入名（或帳號鍵）、最後同意的版號（沒有寫「沒有」）；
名號在管理者名單上的多寫「管理者，不擋」（伺服器 _game 放行管理者）。最後一行印幾個。不印是不是假人：假人沒有帳號，本來就不在表裡。
打不開（路徑打錯、不是資料庫）印一句、結束碼 1。
"""
from __future__ import annotations

import argparse
import io
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.content import load_content, serving_profile  # noqa: E402
from tianxia.features.terms import audit  # noqa: E402  條款的唯讀查帳（功能包 tianxia/features/terms/）


def lines(db: Path, content, now: float) -> list[str]:
    cfg = content.config.terms
    if not cfg.enabled:
        return ["條款關著：伺服器什麼都不擋。", "共 0 個"]
    out = []
    for row in audit.must_rows(db, cfg, set(content.config.admins), now):
        tail = "　管理者，不擋" if row["admin"] else ""
        out.append(f"{row['login']}　最後同意：{row['agreed'] or '沒有'}{tail}")
    out.append(f"共 {len(out)} 個")
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="列出現在會被條款擋下的帳號（唯讀）")
    ap.add_argument("db", type=Path, help="主資料庫檔")
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"找不到資料庫：{args.db}")
        return 1
    content = load_content(ROOT / "content", profile=serving_profile())
    try:
        for line in lines(args.db, content, time.time()):
            print(line)
    except sqlite3.Error as exc:
        print(f"讀不了：{args.db}（{exc}）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
