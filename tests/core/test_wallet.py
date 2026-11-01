"""元寶錢包（商城架構設計 4.1）：餘額＝帳的加總、同一個編號只算一次、餘額不能是負的；購買紀錄與月卡的讀寫。"""
from __future__ import annotations

import pytest

from tianxia.database import open_database
from tianxia.wallet import Wallet


@pytest.fixture
def wallet():
    return Wallet(open_database())


def test_balance_is_the_sum_of_the_ledger(wallet):
    assert wallet.balance("沈青衫") == 0
    assert wallet.post("沈青衫", 5000, "grant", "grant:beta:沈青衫", time=10.0)
    assert wallet.post("沈青衫", -100, "buy", "buy:沈青衫:a", time=11.0)
    assert wallet.post("別人", 300, "reissue", "admin:1", time=12.0, admin="管理者", note="補償")
    assert wallet.balance("沈青衫") == 4900
    rows = wallet.ledger("沈青衫")
    assert [r.delta for r in rows] == [-100, 5000]  # 新的在前
    assert rows[1].reason == "grant" and rows[1].ref == "grant:beta:沈青衫"
    other = wallet.ledger("別人")[0]
    assert other.admin == "管理者" and other.note == "補償"


@pytest.mark.smoke
def test_same_ref_counts_once(wallet):
    assert wallet.post("沈青衫", 5000, "grant", "grant:beta:沈青衫", time=10.0) is True
    assert wallet.post("沈青衫", 5000, "grant", "grant:beta:沈青衫", time=20.0) is False
    assert wallet.balance("沈青衫") == 5000 and len(wallet.ledger("沈青衫")) == 1


def test_balance_never_goes_negative(wallet):
    wallet.post("沈青衫", 50, "grant", "g", time=1.0)
    with pytest.raises(ValueError):
        wallet.post("沈青衫", -51, "buy", "b", time=2.0)
    assert wallet.balance("沈青衫") == 50 and len(wallet.ledger("沈青衫")) == 1


@pytest.mark.smoke
def test_unknown_reason_is_refused_by_the_table(wallet):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        wallet.post("沈青衫", 1, "gift", "x", time=1.0)


def test_purchases_and_counts(wallet):
    first = wallet.add_purchase("沈青衫", "buy:沈青衫:a", "pills_5", 100, time=1.0, day=20000, season=1, data={"pills": 5})
    wallet.add_purchase("沈青衫", "buy:沈青衫:b", "pills_5", 100, time=2.0, day=20001, season=1, data={"pills": 5})
    wallet.add_purchase("沈青衫", "buy:沈青衫:c", "pills_5", 100, time=3.0, day=20001, season=2, data={"pills": 5})
    assert wallet.count("沈青衫", "pills_5") == 3
    assert wallet.count("沈青衫", "pills_5", day=20001) == 2
    assert wallet.count("沈青衫", "pills_5", season=1) == 2
    wallet.mark_refunded(first, 9.0)
    assert wallet.count("沈青衫", "pills_5") == 2  # 退了的不算
    bought = wallet.purchase(first)
    assert bought.refunded == 9.0 and bought.data == {"pills": 5} and bought.item == "pills_5"
    assert wallet.purchase_by_ref("buy:沈青衫:b").day == 20001
    assert wallet.purchase_by_ref("buy:沈青衫:zzz") is None
    assert [p.ref for p in wallet.purchases("沈青衫")] == ["buy:沈青衫:c", "buy:沈青衫:b", "buy:沈青衫:a"]


def test_card_round_trip(wallet):
    assert wallet.card("沈青衫", "pill_cap") is None
    wallet.set_card("沈青衫", "pill_cap", 20000, 20030)
    assert wallet.card("沈青衫", "pill_cap") == (20000, 20030)
    wallet.set_card("沈青衫", "pill_cap", 20000, 20060)
    assert wallet.card("沈青衫", "pill_cap") == (20000, 20060)


def test_export_pairs_rows_with_names(wallet):
    """匯出全部的帳（對帳用）：照 id，名號從 characters 表配上（沒有這個角色是 None）。"""
    with open_database().transaction() as conn:
        conn.execute("INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('rayal', 'Rayal', 0, NULL, '{}')")
    wallet.post("rayal", 5000, "grant", "g1", time=1.0)
    wallet.post("nobody", 10, "reissue", "g2", time=2.0, admin="Rayal", note="測試")
    rows = wallet.export()
    assert [(r.ref, name) for r, name in rows] == [("g1", "Rayal"), ("g2", None)]
