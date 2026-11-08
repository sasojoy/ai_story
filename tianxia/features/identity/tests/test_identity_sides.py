"""帳號綁定的旁檔跟著情境的暫存資料庫清掉（scripts/sb/harness.py 的 _wipe_db；帳號與客服第 201 批）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_wipe_db_removes_identity_and_support_sides(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from sb import harness  # 只走 sb.harness 這條路徑（同 same_behavior.py 開頭）

    db = tmp_path / "game.db"
    made = [db, *(tmp_path / f"game-{side}.sqlite{suffix}" for side in ("identity", "support", "push") for suffix in ("", "-wal", "-shm"))]
    for p in made:
        p.write_bytes(b"x")
    keep = tmp_path / "other-identity.sqlite"
    keep.write_bytes(b"x")
    harness._wipe_db(db)
    assert not any(p.exists() for p in made)
    assert keep.exists()
