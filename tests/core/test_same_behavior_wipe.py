"""same_behavior 的 _wipe_db（第 239 批）：同一個 --tmp 跑第二次之前，遊戲在資料庫旁邊建的檔與資料夾要全清掉，不然第二次會讀到第一次留下的信、截圖。
掃 tianxia/（不含測試）與 server.py 裡 `stem}-<名字>` 的寫法，在暫存資料夾全建出來，跑 _wipe_db 後要全不在；刻意不清的（-vapid.pem、.db.<軌>.json）要還在。
包新建一個旁檔沒補進 _wipe_db 的清單，這條會紅。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SIDE = re.compile(r'stem\}-(\{[A-Za-z_]+\}|[a-z][a-z-]*)(\.sqlite)?"')
ARCHIVE = '.replace(".sqlite", "-archive.sqlite")'
# 封存檔是「主旁檔名換 .sqlite → -archive.sqlite」，掃不到 stem}- 的寫法：現在兩處（companions/talk_log.py、mail/store.py），多一處就紅、要人來補下面這張
ARCHIVES = ("talk-archive", "mail-archive")


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from sb import harness  # 走 sb.harness 這條路（不是 scripts.sb），跟 same_behavior.py 一樣

    return harness


def _sources() -> list[Path]:
    files = [p for p in (ROOT / "tianxia").rglob("*.py") if "tests" not in p.relative_to(ROOT).parts]
    return files + [ROOT / "server.py"]


def _placeholder(name: str) -> str:
    from tianxia.core import identity_base
    from tianxia.features.identity import store as identity_store

    known = {"SIDE_SUFFIX": identity_base.SIDE_SUFFIX, "SUFFIX": identity_store.SUFFIX}
    assert name in known, f"旁檔名用了沒見過的變數 {{{name}}}：在這張表補上它的值"
    return known[name]


def _scanned() -> tuple[set[str], set[str]]:
    """（旁檔 <名字>.sqlite 的名字, 資料夾的名字）。"""
    files: set[str] = set(ARCHIVES)
    folders: set[str] = set()
    archives = 0
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        archives += text.count(ARCHIVE)
        for name, sqlite in SIDE.findall(text):
            name = _placeholder(name[1:-1]) if name.startswith("{") else name
            (files if sqlite else folders).add(name)
    assert archives == len(ARCHIVES), f"封存的寫法 {ARCHIVE} 現在 {archives} 處：補 ARCHIVES 與 _wipe_db 的清單"
    return files, folders


def test_scan_finds_the_known_sides():
    files, folders = _scanned()
    assert {"talk", "narration", "archive", "tale", "push", "identity", "support", "terms", "mail"} <= files
    assert folders == {"support-files"}


def test_wipe_db_clears_every_side_the_game_writes(harness, tmp_path):
    files, folders = _scanned()
    db = tmp_path / "x.db"
    made = [db, tmp_path / "x.db.state.json"]
    for name in sorted(files):
        made += [tmp_path / f"x-{name}.sqlite{suffix}" for suffix in ("", "-wal", "-shm")]
    for p in made:
        p.write_bytes(b"old")
    for name in sorted(folders):
        (tmp_path / f"x-{name}" / "1").mkdir(parents=True)
        (tmp_path / f"x-{name}" / "1" / "1.png").write_bytes(b"old")
    kept = [tmp_path / "x.db.omen.json", tmp_path / "x-vapid.pem"]  # 刻意不清（_wipe_db 的說明）
    for p in kept:
        p.write_bytes(b"keep")

    harness._wipe_db(db)

    left = [p.name for p in made if p.exists()] + [n for n in folders if (tmp_path / f"x-{n}").exists()]
    assert left == [], f"_wipe_db 沒清：{left}"
    assert all(p.exists() for p in kept)
