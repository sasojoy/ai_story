"""same_behavior 的快取（第二輪第 71 批）：同一波修正之後重跑閘門時，base 那一邊不必再跑一次。預設關，--cache 才開（鍵漏掉相依會假綠，預設關才不會忘）。

只存 base：整段（all_）、前半連資料庫快照（first_）、假人（bots_）；第 107 批起 --crossover 的 base 整段同時出前半與快照，存成 allx_（output.gz、half.gz、snap/）。head 永遠跑，所以改 head 一個字照樣抓得到。
鍵是指紋加格名（軌、設定在格名上）。指紋寧可多算，多算只是多跑：
- 根的內容雜湊：每個檔的相對路徑加內容，只排除 .git、__pycache__（saves、.local 不排除：根被動過就該沒命中）。
- scripts/sb/**/*.py 加 same_behavior.py，不是繼承鏈：每個子行程都載入全部的軌，facade.py 改寫 MapScenario.web，smithy、shelf 改寫表，繼承鏈看不到。
- Python、SQLite、依賴的版本；環境變數 SB_*（會改輸出）、TIANXIA_*（TIANXIA_DB 除外，每次都不同）、GEMINI_API_KEY 有沒有設（只算有無）。

版面：<快取>/<指紋前 16 碼>/manifest.json（各項雜湊），每格一個資料夾：output.gz，first_ 多一個 snap/（資料庫與旁邊每個檔，主檔名換成固定字）。
先寫 <格>.tmp<pid> 再改名，資料夾在就代表完整。開的時候刪掉別的指紋，磁碟上只留一份。

這個檔只用標準庫、不 import sb.harness（harness 載入時 import 這個檔）。
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path

SKIP = {".git", "__pycache__"}
HALF = "half"  # 快照裡主檔名換成的固定字：每次 compare 的主檔名不同（--tmp、label）
hits = 0  # 這一次 open_folder 之後命中幾格、沒命中幾格（selftest --cache 讀）
misses = 0


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def _file_sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _root_hash(root: Path) -> str:
    lines = []
    for top, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(n for n in names if n not in SKIP):
            path = Path(top, name)
            lines.append(f"{path.relative_to(root).as_posix()}\0{_file_sha(path)}")
    return _sha("\n".join(lines))


def _scripts_hash(scripts: Path) -> str:
    files = [scripts / "same_behavior.py", *sorted((scripts / "sb").rglob("*.py"))]
    return _sha("\n".join(f"{p.relative_to(scripts).as_posix()}\0{_file_sha(p)}" for p in files))


def _deps() -> list[str]:
    return sorted(f"{d.metadata['Name']}={d.version}" for d in importlib.metadata.distributions())


def _env() -> dict[str, str]:
    keep = {k: v for k, v in os.environ.items() if k.startswith("SB_") or (k.startswith("TIANXIA_") and k != "TIANXIA_DB")}
    keep["GEMINI_API_KEY"] = "有" if os.environ.get("GEMINI_API_KEY") else ""  # 只算有無，鑰匙本身不進雜湊也不進 manifest
    return keep


def parts(root: Path, scripts: Path) -> dict[str, str]:
    """指紋的各項（scripts：跑這一次的 scripts/ 資料夾；base 是 head 的腳本跑的）。環境變數只留雜湊，manifest 不寫值。"""
    return {"root": _root_hash(root), "scripts": _scripts_hash(scripts), "python": sys.version, "sqlite": sqlite3.sqlite_version,
            "deps": _sha(json.dumps(_deps(), ensure_ascii=False)), "env": _sha(json.dumps(_env(), ensure_ascii=False, sort_keys=True))}


def fingerprint(info: dict[str, str]) -> str:
    return _sha(json.dumps(info, ensure_ascii=False, sort_keys=True))


def open_folder(cache: Path, root: Path, scripts: Path) -> Path:
    """這一次的資料夾：算指紋、命中數歸零、刪掉別的指紋與上次沒寫完的格。只認得指紋樣子的資料夾，--cache 指錯地方也不會刪到別的東西。"""
    global hits, misses
    hits = misses = 0
    info = parts(root, scripts)
    folder = cache / fingerprint(info)[:16]
    if cache.is_dir():
        for old in cache.iterdir():
            if old != folder and old.is_dir() and re.fullmatch(r"[0-9a-f]{16}", old.name) and (old / "manifest.json").exists():
                shutil.rmtree(old)
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob("*.tmp*"):
        shutil.rmtree(stale)
    (folder / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


def hit(folder: Path, cell: str) -> bool:
    """這一格有沒有，順便記數。compare 組串的時候在主執行緒叫，一格問一次。"""
    global hits, misses
    found = (folder / cell).is_dir()
    hits, misses = hits + found, misses + (not found)
    return found


def _pack(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fin, gzip.open(dest, "wb", compresslevel=1) as fout:  # 第 1 級：快照 4.6 倍、輸出 3.2 倍，32 MB 約 0.1 秒
        shutil.copyfileobj(fin, fout)


def _unpack(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rb") as fin, dest.open("wb") as fout:
        shutil.copyfileobj(fin, fout)


def save(folder: Path, cell: str, output: Path, db_files: Iterable[Path] = (), stem: str = "", half_out: Path | None = None) -> None:
    """存一格。db_files：這一格的資料庫與旁邊每個檔（可以是資料夾），名字都以 stem 開頭，存的時候 stem 換成 HALF。
    half_out（第 107 批 allx_ 格：base 整段同時出前半與快照）：前半輸出多存一份 half.gz。"""
    tmp = folder / f"{cell}.tmp{os.getpid()}"
    tmp.mkdir()
    _pack(output, tmp / "output.gz")
    if half_out is not None:
        _pack(half_out, tmp / "half.gz")
    for path in db_files:
        for f in path.rglob("*") if path.is_dir() else [path]:
            if f.is_file():
                _pack(f, tmp / "snap" / f"{HALF}{f.relative_to(path.parent).as_posix()[len(stem):]}.gz")
    os.replace(tmp, folder / cell)


def restore(folder: Path, cell: str, output: Path, db: Path | None = None, half_out: Path | None = None) -> None:
    """還原一格：輸出解到 output；db 給了就把快照解到它旁邊，HALF 換回這一次的主檔名（舊檔由叫的人先清）；half_out 給了把前半輸出解到那裡。"""
    _unpack(folder / cell / "output.gz", output)
    if half_out is not None:
        _unpack(folder / cell / "half.gz", half_out)
    if db is None:
        return
    snap = folder / cell / "snap"
    for gz in snap.rglob("*.gz"):
        _unpack(gz, db.parent / f"{db.stem}{gz.relative_to(snap).as_posix()[len(HALF):-len('.gz')]}")


def megabytes(folder: Path) -> float:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1e6
