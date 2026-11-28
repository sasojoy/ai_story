"""元寶錢包的讀寫（商城架構設計 4.1、4.4、4.5、4.9；資料庫第 6 版的三張表）。

- 錢包不另存餘額：餘額＝帳本 mall_ledger 的加總，永遠對得起來；扣到負的在同一筆交易裡擋（丟 ValueError、什麼都不寫）。
- 每一筆帶不重複的編號 ref（表上 UNIQUE）：同一個編號第二次 post 回 False、什麼都不寫，連點、逾時重送都不會算兩次。
- owner 是角色名號的 casefold（characters.name_key）：真人的帳號與角色一對一、綁了不換，這個鍵就是 accounts.character_key；
  假人沒有帳號也有錢包（看不出誰是假人，設計 4.8）。換季角色重來，characters 那一列留著，錢包跟著跨季。
- 每個寫的方法自己開 db.transaction()：呼叫端已經開著（伺服器的行動鎖）就併進那一筆，出錯整筆撤回。

- 元寶分兩種（資料庫第 10 版，Joy 2026-11-26）：每一筆帳記 coin，paid＝元寶（只能儲值取得）、gift＝送的那一種。兩種各自不能
  扣到負的。花錢走 spend：先扣送的、不夠再扣元寶（paid_only 時只扣元寶），一筆購買最多寫兩列帳（第二列的編號接 ":paid"），
  回這一筆各扣了幾個（呼叫端記進購買那一列的 data["coins"]，退款照它退回原來的那一種）。

只碰資料庫，不碰遊戲規則（規則在 tianxia/mall.py）、不讀時鐘（時間由呼叫端傳進來）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .database import Database


GIFT, PAID = "gift", "paid"
COINS = (PAID, GIFT)
PAID_SUFFIX = ":paid"  # 一筆兩種都動到時，元寶那一列的編號（接在原編號後面；改名照 ":" 切開換主人，不會切壞）


def coin_of(reason: str) -> str:
    """沒指定時這一種原因記哪一種：儲值是元寶，其餘（發放、補發、退款、扣回……）都是送的那一種。"""
    return PAID if reason == "topup" else GIFT


def coins_of(data: dict, price: int) -> dict[str, int]:
    """一筆購買當初各扣了幾個（購買那一列的 data["coins"]）；拆開以前買的沒有這一格，全算送的。"""
    got = data.get("coins")
    if isinstance(got, dict):
        return {GIFT: int(got.get(GIFT, 0)), PAID: int(got.get(PAID, 0))}
    return {GIFT: int(price), PAID: 0}


@dataclass(frozen=True)
class LedgerRow:
    id: int
    owner: str
    time: float
    delta: int
    reason: str  # grant、buy、refund、reissue、revoke、topup（mall.REASONS）
    ref: str
    purchase_id: int | None
    admin: str | None
    note: str
    coin: str = GIFT  # paid 元寶、gift 送的那一種（第 10 版）


@dataclass(frozen=True)
class Purchase:
    id: int
    owner: str
    ref: str
    item: str
    price: int
    time: float
    day: int  # 回體丹換日的那一天（台灣 00:00）
    season: int
    data: dict  # 發了什麼（例 {"pills": 5}、{"card_days": 30}）：退的時候照它收回
    refunded: float | None  # 退的時刻；沒退是 None


def _row(r) -> LedgerRow:
    return LedgerRow(
        id=r["id"], owner=r["owner"], time=r["time"], delta=r["delta"], reason=r["reason"], ref=r["ref"],
        purchase_id=r["purchase_id"], admin=r["admin"], note=r["note"],
        coin=r["coin"] if "coin" in r.keys() else coin_of(r["reason"]),  # 第 9 版以前的檔（主機端唯讀對帳）沒有這一欄
    )


def _purchase(r) -> Purchase:
    return Purchase(
        id=r["id"], owner=r["owner"], ref=r["ref"], item=r["item"], price=r["price"], time=r["time"], day=r["day"],
        season=r["season"], data=json.loads(r["data"]), refunded=r["refunded"],
    )


class Wallet:
    def __init__(self, db: Database):
        self.db = db

    # ── 帳 ──────────────────────────────────────

    def balance(self, owner: str, coin: str | None = None) -> int:
        """餘額：coin 沒給是兩種加起來，給了只算那一種。"""
        with self.db.snapshot() as conn:
            return self._balance(conn, owner, coin)

    def balances(self, owner: str) -> dict[str, int]:
        """兩種各剩多少（{paid, gift}）。"""
        with self.db.snapshot() as conn:
            return {c: self._balance(conn, owner, c) for c in COINS}

    @staticmethod
    def _balance(conn, owner: str, coin: str | None = None) -> int:
        if coin is None:
            return conn.execute("SELECT COALESCE(SUM(delta), 0) FROM mall_ledger WHERE owner = ?", (owner,)).fetchone()[0]
        return conn.execute(
            "SELECT COALESCE(SUM(delta), 0) FROM mall_ledger WHERE owner = ? AND coin = ?", (owner, coin),
        ).fetchone()[0]

    def payable(self, owner: str, *, paid_only: bool = False) -> int:
        """這一次最多付得出多少：paid_only 只算元寶，否則兩種加起來。"""
        return self.balance(owner, PAID) if paid_only else self.balance(owner)

    def ledger(self, owner: str, limit: int | None = None) -> list[LedgerRow]:
        """這個錢包的帳，新的在前；limit 給了就只取最近幾筆。"""
        sql = "SELECT * FROM mall_ledger WHERE owner = ? ORDER BY id DESC" + (" LIMIT ?" if limit else "")
        with self.db.snapshot() as conn:
            return [_row(r) for r in conn.execute(sql, (owner, limit) if limit else (owner,))]

    def has_ref(self, ref: str) -> bool:
        with self.db.snapshot() as conn:
            return conn.execute("SELECT 1 FROM mall_ledger WHERE ref = ?", (ref,)).fetchone() is not None

    def post(
        self, owner: str, delta: int, reason: str, ref: str, *, time: float, admin: str | None = None, note: str = "",
        purchase_id: int | None = None, coin: str | None = None,
    ) -> bool:
        """記一筆帳（coin 沒給照 coin_of(reason)）。編號已經有了回 False、什麼都不寫；記了之後那一種的餘額會是負的就丟
        ValueError（也什麼都不寫）。"""
        coin = coin or coin_of(reason)
        if coin not in COINS:
            raise ValueError(f"不認得的元寶種類：{coin}")
        with self.db.transaction() as conn:
            if conn.execute("SELECT 1 FROM mall_ledger WHERE ref = ?", (ref,)).fetchone() is not None:
                return False
            if delta < 0 and self._balance(conn, owner, coin) + delta < 0:
                raise ValueError(f"元寶不夠：{owner} 的{coin}扣 {-delta} 會變成負的")
            conn.execute(
                "INSERT INTO mall_ledger (owner, time, delta, reason, ref, purchase_id, admin, note, coin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner, time, int(delta), reason, ref, purchase_id, admin, note, coin),
            )
        return True

    def split(self, owner: str, price: int, *, paid_only: bool = False) -> dict[str, int] | None:
        """付 price 要各扣幾個：先扣送的、不夠再扣元寶（paid_only 只扣元寶）；付不起回 None。不寫任何東西。"""
        with self.db.snapshot() as conn:
            gift_have, paid_have = self._balance(conn, owner, GIFT), self._balance(conn, owner, PAID)
        gift = 0 if paid_only else min(int(price), max(0, gift_have))
        paid = int(price) - gift
        return None if paid > paid_have else {GIFT: gift, PAID: paid}

    def _write(
        self, owner: str, coins: dict[str, int], sign: int, reason: str, ref: str, *, time: float, purchase_id: int | None,
        admin: str | None, note: str,
    ) -> bool:
        """照 coins 寫一列或兩列帳（第一列用 ref、元寶在第二列時接 ":paid"）；兩種都是 0 寫一列 0 的送的那一種。"""
        parts = [(c, int(coins.get(c, 0))) for c in (GIFT, PAID) if int(coins.get(c, 0))] or [(GIFT, 0)]
        with self.db.transaction():
            for k, (coin, n) in enumerate(parts):
                row_ref = ref if k == 0 else ref + PAID_SUFFIX
                if not self.post(owner, sign * n, reason, row_ref, time=time, purchase_id=purchase_id, admin=admin, note=note, coin=coin):
                    if k == 0:
                        return False
                    raise RuntimeError(f"編號 {row_ref} 已經記過帳")
        return True

    def spend(
        self, owner: str, price: int, reason: str, ref: str, *, time: float, purchase_id: int | None = None,
        paid_only: bool = False, admin: str | None = None, note: str = "",
    ) -> dict[str, int] | None:
        """花 price（先扣送的、不夠再扣元寶；paid_only 只扣元寶）：回各扣了幾個；編號已經有了回 None、什麼都不寫；
        付不起丟 ValueError（什麼都不寫）。"""
        coins = self.split(owner, price, paid_only=paid_only)
        if coins is None:
            raise ValueError(f"元寶不夠：{owner} 付不起 {price}")
        return coins if self._write(owner, coins, -1, reason, ref, time=time, purchase_id=purchase_id, admin=admin, note=note) else None

    def credit(
        self, owner: str, coins: dict[str, int], reason: str, ref: str, *, time: float, purchase_id: int | None = None,
        admin: str | None = None, note: str = "",
    ) -> bool:
        """照 coins 入帳（退款退回原來的那一種、市集分成照買家付的那一種）；編號已經有了回 False。"""
        return self._write(owner, coins, 1, reason, ref, time=time, purchase_id=purchase_id, admin=admin, note=note)

    def take(
        self, owner: str, coins: dict[str, int], reason: str, ref: str, *, time: float, purchase_id: int | None = None,
        admin: str | None = None, note: str = "",
    ) -> bool:
        """照 coins 扣（例：退月卡時扣回當場回的那一份）；編號已經有了回 False，哪一種不夠丟 ValueError。"""
        return self._write(owner, coins, -1, reason, ref, time=time, purchase_id=purchase_id, admin=admin, note=note)

    # ── 購買紀錄 ────────────────────────────────

    def add_purchase(
        self, owner: str, ref: str, item: str, price: int, *, time: float, day: int, season: int, data: dict,
    ) -> int:
        with self.db.transaction() as conn:
            return conn.execute(
                "INSERT INTO mall_purchases (owner, ref, item, price, time, day, season, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (owner, ref, item, int(price), time, day, season, json.dumps(data, ensure_ascii=False)),
            ).lastrowid

    def purchase(self, pid: int) -> Purchase | None:
        with self.db.snapshot() as conn:
            r = conn.execute("SELECT * FROM mall_purchases WHERE id = ?", (pid,)).fetchone()
        return None if r is None else _purchase(r)

    def purchase_by_ref(self, ref: str) -> Purchase | None:
        with self.db.snapshot() as conn:
            r = conn.execute("SELECT * FROM mall_purchases WHERE ref = ?", (ref,)).fetchone()
        return None if r is None else _purchase(r)

    def purchases(self, owner: str, limit: int | None = None) -> list[Purchase]:
        """這個錢包的購買紀錄，新的在前。"""
        sql = "SELECT * FROM mall_purchases WHERE owner = ? ORDER BY id DESC" + (" LIMIT ?" if limit else "")
        with self.db.snapshot() as conn:
            return [_purchase(r) for r in conn.execute(sql, (owner, limit) if limit else (owner,))]

    def count(self, owner: str, item: str, *, day: int | None = None, season: int | None = None) -> int:
        """這個錢包買過幾次這件（不算退了的）；day、season 給了就只數那一天、那一季的（限購用）。"""
        sql = "SELECT COUNT(*) FROM mall_purchases WHERE owner = ? AND item = ? AND refunded IS NULL"
        args: list = [owner, item]
        if day is not None:
            sql += " AND day = ?"
            args.append(day)
        if season is not None:
            sql += " AND season = ?"
            args.append(season)
        with self.db.snapshot() as conn:
            return conn.execute(sql, args).fetchone()[0]

    def mark_used(self, pid: int, time: float, **extra) -> None:
        """這一筆購買用掉了（重修列傳、易名帖、列傳的票）：data 多一個 used（時刻），extra 一起記（列傳的票記用在哪一季 season、
        親筆評曰請了哪一位 fid，減法季批 7b）。不改結構版本，記在原本那一列的 data 裡。"""
        with self.db.transaction() as conn:
            r = conn.execute("SELECT data FROM mall_purchases WHERE id = ?", (pid,)).fetchone()
            data = json.loads(r["data"]) if r is not None else {}
            data.update(extra)
            data["used"] = time
            conn.execute("UPDATE mall_purchases SET data = ? WHERE id = ?", (json.dumps(data, ensure_ascii=False), pid))

    def update_data(self, pid: int, **fields) -> None:
        """改一筆購買 data 裡的幾個欄位（自建形象的訂單照它換狀態）；其餘照舊。"""
        with self.db.transaction() as conn:
            r = conn.execute("SELECT data FROM mall_purchases WHERE id = ?", (pid,)).fetchone()
            data = json.loads(r["data"]) if r is not None else {}
            data.update(fields)
            conn.execute("UPDATE mall_purchases SET data = ? WHERE id = ?", (json.dumps(data, ensure_ascii=False), pid))

    def purchases_of(self, item: str) -> list[Purchase]:
        """全部錢包買過這一件的紀錄（舊的在前）：管理者看自建形象的訂單用。"""
        with self.db.snapshot() as conn:
            return [_purchase(r) for r in conn.execute("SELECT * FROM mall_purchases WHERE item = ? ORDER BY id", (item,))]

    def mark_refunded(self, pid: int, time: float) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE mall_purchases SET refunded = ? WHERE id = ?", (time, pid))

    # ── 月卡 ────────────────────────────────────

    def card(self, owner: str, key: str) -> tuple[int, int] | None:
        """月卡（key 是效果，例 pill_cap）的開始日與到期日（不含）；沒買過是 None。"""
        with self.db.snapshot() as conn:
            r = conn.execute(
                "SELECT start_day, end_day FROM mall_entitlements WHERE owner = ? AND kind = 'card' AND key = ?", (owner, key),
            ).fetchone()
        return None if r is None else (r["start_day"], r["end_day"])

    def set_card(self, owner: str, key: str, start: int, end: int) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO mall_entitlements (owner, kind, key, start_day, end_day) VALUES (?, 'card', ?, ?, ?) "
                "ON CONFLICT (owner, kind, key) DO UPDATE SET start_day = excluded.start_day, end_day = excluded.end_day",
                (owner, key, start, end),
            )

    def entitlement(self, owner: str, kind: str, key: str) -> dict | None:
        """mall_entitlements 那一格的 data（例：形象穿哪一套，kind 'look'、key 'wear'）；沒有這一格是 None。"""
        with self.db.snapshot() as conn:
            r = conn.execute(
                "SELECT data FROM mall_entitlements WHERE owner = ? AND kind = ? AND key = ?", (owner, kind, key),
            ).fetchone()
        return None if r is None else json.loads(r["data"])

    def set_entitlement(self, owner: str, kind: str, key: str, data: dict) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO mall_entitlements (owner, kind, key, data) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (owner, kind, key) DO UPDATE SET data = excluded.data",
                (owner, kind, key, json.dumps(data, ensure_ascii=False)),
            )

    # ── 對帳 ────────────────────────────────────

    def entitlements(self, kind: str) -> list[tuple[str, str, dict]]:
        """全服這一種的每一格（主人、key、data），舊的在前（例：形象市集上架的，kind 'market'）。"""
        with self.db.snapshot() as conn:
            rows = conn.execute("SELECT owner, key, data FROM mall_entitlements WHERE kind = ? ORDER BY rowid", (kind,)).fetchall()
        return [(r["owner"], r["key"], json.loads(r["data"] or "{}")) for r in rows]

    def drop_entitlement(self, owner: str, kind: str, key: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM mall_entitlements WHERE owner = ? AND kind = ? AND key = ?", (owner, kind, key))

    def reason_total(self, owner: str, reason: str) -> int:
        """這個錢包某一種帳的加總（例：儲值 topup 一共進來多少）。"""
        with self.db.snapshot() as conn:
            return conn.execute("SELECT COALESCE(SUM(delta), 0) FROM mall_ledger WHERE owner = ? AND reason = ?", (owner, reason)).fetchone()[0]

    def character_name(self, owner: str) -> str | None:
        """這個錢包的角色名號（characters 表的原寫法）；沒有這個角色是 None。管理者查帳找人用（真人假人一樣查）。"""
        with self.db.snapshot() as conn:
            r = conn.execute("SELECT name FROM characters WHERE key = ?", (owner,)).fetchone()
        return None if r is None else r["name"]

    def export(self) -> list[tuple[LedgerRow, str | None]]:
        """全部的帳照 id 排，配上角色的名號（characters 表；沒有這個角色是 None）。主機端對帳用（scripts/mall_ledger.py）。"""
        sql = "SELECT l.*, c.name AS shown FROM mall_ledger l LEFT JOIN characters c ON c.key = l.owner ORDER BY l.id"
        with self.db.snapshot() as conn:
            return [(_row(r), r["shown"]) for r in conn.execute(sql)]
