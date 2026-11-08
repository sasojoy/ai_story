"""same_behavior 的 covers、--covers、--crossover 與前半快照（測試流程優化第 107 批）。整條比對在波末閘門跑，這裡只驗不開伺服器就看得到的。"""
from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sb(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from sb import harness  # 只走 sb.harness 這條路徑，不要 scripts.sb（同 same_behavior.py 開頭）

    if not harness.TRACK_NAMES:
        harness.load_tracks()
    return harness


def _packages() -> set[str]:
    return {p.name for p in (ROOT / "tianxia" / "features").iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def test_every_track_declares_covers_of_real_packages(sb):
    packages = _packages()
    assert sb.TRACK_NAMES, "一軌都沒載到"
    for t in sb.TRACK_NAMES:
        assert sb.COVERS.get(t), f"軌 {t} 沒寫 covers（register_track 的 covers=，量法見 harness.COVERS 的說明）"
        unknown = set(sb.COVERS[t]) - packages
        assert not unknown, f"軌 {t} 的 covers 有不存在的包 {sorted(unknown)}"
    assert set(sb.ALWAYS_TRACKS) <= set(sb.TRACK_NAMES), f"ALWAYS_TRACKS 有不是軌的 {sorted(set(sb.ALWAYS_TRACKS) - set(sb.TRACK_NAMES))}"
    lonely = sorted(packages - {p for t in sb.TRACK_NAMES for p in sb.COVERS[t]})
    if lonely:  # 不紅、不自己補軌：寫進回報
        warnings.warn(f"沒有一軌走到的包：{lonely}", stacklevel=1)


def test_the_mutated_package_is_in_that_tracks_covers(sb):
    """selftest 改一個字的那一句（_mutant 的找法：列的檔裡剛好一處的那一個）落在哪一包，那一包要在那一軌的 covers：不然 --covers 挑不到自己證明抓得到的那一包。"""
    for t in sb.TRACK_NAMES:
        files, (old, _) = sb.MUTATIONS[t]
        hit = next((rel for rel in files if (ROOT / rel).exists() and (ROOT / rel).read_text(encoding="utf-8").count(old) == 1), None)
        assert hit, f"軌 {t} 改一個字的那一句在列的檔裡找不到剛好一處"
        parts = Path(hit).parts
        package = parts[2] if parts[:2] == ("tianxia", "features") else Path(hit).stem if parts[0] == "web" else None
        if package in _packages():
            assert package in sb.COVERS[t], f"軌 {t} 改的是 {hit}，covers 沒有 {package}"


def test_pick_takes_the_tracks_that_cover_the_package_plus_always(sb, monkeypatch):
    monkeypatch.setattr(sb, "TRACK_NAMES", ("a", "b", "c", "battle"))
    monkeypatch.setattr(sb, "COVERS", {"a": ("x",), "b": ("y",), "c": ("x", "y"), "battle": ("z",)})
    monkeypatch.setattr(sb, "ALWAYS_TRACKS", ("battle",))
    assert sb.pick_tracks(["x"]) == ["a", "c", "battle"]
    assert sb.pick_tracks(["nothing"]) == ["battle"]
    assert sb.pick_tracks(["x", "y"], ["b", "battle"]) == ["b", "battle"]  # --tracks 同時給取交集


def _chains(sb, monkeypatch, tmp_path, crossover: bool, tracks: list[str]) -> list[list]:
    seen = []

    def grab(chains, workers):
        seen.extend(chains)
        raise KeyboardInterrupt  # 只看組出來的串，不真的跑

    monkeypatch.setattr(sb, "_run_set", grab)
    with pytest.raises(KeyboardInterrupt):
        sb.compare(ROOT, ROOT, tmp_path, ["test"], 1, False, tracks=tracks, crossover=crossover)
    return [[step[0] for step in chain] for chain in seen]


def test_compare_without_crossover_has_no_half_runs(sb, monkeypatch, tmp_path):
    runs = [args for chain in _chains(sb, monkeypatch, tmp_path, False, ["sortie"]) for args in chain]
    assert len(runs) == 2 and not any("--part" in a or "--snapshot" in a for a in runs)


def test_compare_crossover_takes_the_half_from_the_base_full_run(sb, monkeypatch, tmp_path):
    chains = _chains(sb, monkeypatch, tmp_path, True, ["sortie"])
    full = next(c for c in chains if "--snapshot" in c[0])
    assert len(full) == 2 and full[1][full[1].index("--part") + 1] == "second", "head 後半要排在 base 整段（出快照）之後同一串"
    assert full[1][full[1].index("--db") + 1] == full[0][full[0].index("--snapshot") + 1], "後半接的就是快照"
    assert not any("first" in a for c in chains for a in c), "base 前半不再另開"


def test_compare_crossover_keeps_the_old_half_for_a_twin(sb, monkeypatch, tmp_path):
    twin = next(iter(sb.FULL_SAME_AS))
    chains = _chains(sb, monkeypatch, tmp_path, True, [twin, sb.FULL_SAME_AS[twin]])
    firsts = [c for c in chains if c[0][c[0].index("--track") + 1] == twin]
    assert len(firsts) == 1 and "first" in firsts[0][0] and "second" in firsts[0][1], "整段同一軌的照舊另開 base 前半（切點不同）"


def test_snapshot_copies_every_file_under_the_half_name(sb, tmp_path):
    db = tmp_path / "cmp_base_x_test.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (v)")
    con.execute("INSERT INTO t VALUES (7)")
    con.commit()  # 留在 -wal 裡，連線不關：backup 要拿到這一列
    side = tmp_path / "cmp_base_x_test-tale.sqlite"
    sqlite3.connect(side).close()
    (tmp_path / "cmp_base_x_test.db.x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "cmp_base_x_test-vapid.pem").write_text("k", encoding="utf-8")
    (tmp_path / "cmp_base_x_test-covers").mkdir()
    (tmp_path / "cmp_base_x_test-covers" / "a.txt").write_text("a", encoding="utf-8")
    half = tmp_path / "cmp_half_x_test.db"
    (tmp_path / "cmp_half_x_test-stale.txt").write_text("old", encoding="utf-8")
    sb.snapshot_db(db, half)
    con.close()
    names = {p.name for p in tmp_path.iterdir() if p.name.startswith("cmp_half_")}
    assert names == {"cmp_half_x_test.db", "cmp_half_x_test-tale.sqlite", "cmp_half_x_test.db.x.json", "cmp_half_x_test-vapid.pem", "cmp_half_x_test-covers"}
    copy = sqlite3.connect(half)
    assert copy.execute("SELECT v FROM t").fetchall() == [(7,)]
    copy.close()
    assert (tmp_path / "cmp_half_x_test-covers" / "a.txt").read_text(encoding="utf-8") == "a"
