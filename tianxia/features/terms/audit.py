"""條款第 249 批：主機用的唯讀查帳（scripts/list_terms_must.py 與 routes.router 啟動時的警告）。

主資料庫與同意旁檔一律 `mode=ro` 開：不建檔、不建表、不跑遷移、不寫任何東西（不用 ConsentStore／AccountStore，它們一建就會 mkdir、
CREATE TABLE、跑遷移）。帳號鍵照 tianxia/accounts.py 的 AccountStore.get：有 password 那一列的是它的 subject，有補設密碼記號列
（provider=accounts.MARKER）的是 id:<n>；沒有 password 列的也是 id:<n>。判斷照 rules.need（跟 routes._Hook.must 同一支）。
不看、也不印是不是假人：假人沒有帳號，本來就不在帳號表裡。"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from tianxia import accounts

from . import rules


def side_path(db: Path) -> Path:
    """同意旁檔的位置（同 routes.store_path）：遊戲資料庫旁邊、同名多「-terms.sqlite」。"""
    db = Path(db)
    return db.with_name(f"{db.stem}-terms.sqlite")


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def account_rows(db: Path) -> list[dict]:
    """每個帳號一列：key（同意紀錄認的鍵）、login（顯示用的登入名，沒有就是鍵）、character（名號，可能是 None）。"""
    sql = (
        "SELECT a.id, a.character, l.subject, l.display, "
        f"EXISTS (SELECT 1 FROM logins m WHERE m.account_id = a.id AND m.provider = '{accounts.MARKER}') AS marked "
        "FROM accounts a LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' ORDER BY a.id")
    with contextlib.closing(_ro(db)) as conn:
        rows = conn.execute(sql).fetchall()
    out = []
    for r in rows:
        key = r["subject"] if r["subject"] is not None and not r["marked"] else f"id:{r['id']}"
        out.append({"key": key, "login": r["display"] or key, "character": r["character"]})
    return out


def latest_by_account(db: Path) -> dict[str, str]:
    """旁檔裡每個帳號最後同意的版號（同 ConsentStore.latest：id 最大的那一筆）；旁檔不在當全空。"""
    side = side_path(db)
    if not side.exists():
        return {}
    with contextlib.closing(_ro(side)) as conn:
        return {r["account"]: r["version"] for r in conn.execute("SELECT account, version FROM consents ORDER BY id")}


def must_rows(db: Path, cfg, admins, now: float, data: dict | None = None) -> list[dict]:
    """現在會被擋的帳號（rules.need 回 MUST）；cfg 是 Config.terms。關著回空表（什麼都不擋）。
    名號在 admins 上的照樣列出、帶 admin=True（伺服器 _game 放行管理者）。"""
    if not cfg.enabled:
        return []
    data = data or rules.load()
    latest = latest_by_account(db)
    out = []
    for row in account_rows(db):
        agreed = latest.get(row["key"])
        if rules.need(agreed, data, now, cfg.grace_days, cfg.update_must) == rules.MUST:
            out.append({**row, "agreed": agreed, "admin": row["character"] in admins})
    return out


def consent_missing(db: Path, version: str) -> bool:
    """啟動時的警告要不要印：主資料庫在、帳號表有人，而同意旁檔不在、或現行版一筆都沒有（旁檔遺失或搬機沒帶，全體會變成要重新同意）。
    主資料庫不在或讀不到回 False（新開的服、還沒建表）。"""
    db = Path(db)
    if not db.exists():
        return False
    with contextlib.closing(_ro(db)) as conn:
        if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is None:
            return False
    side = side_path(db)
    if not side.exists():
        return True
    with contextlib.closing(_ro(side)) as conn:
        return conn.execute("SELECT 1 FROM consents WHERE version = ? LIMIT 1", (version,)).fetchone() is None
