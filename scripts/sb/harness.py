"""same_behavior 的調度與固定層：compare、selftest、子行程的假時鐘假模型與資料庫文字、軌的登記表（第二輪第 70 批）。
compare --new（第 106 批）：新包帶來的差異（web 宣告的 js、css，帶包名前綴的表，新 op 與管理者動作）只在 head 的子行程扣掉，比完印成清單；base 的子行程走原路。"""
from __future__ import annotations

import concurrent.futures
import hashlib
import importlib
import io
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from sb import cache

PROFILES = ("season21", "week7", "test")  # 拿掉二（甲）：none、weekend 關門，不再是可以選的設定
TRACK_NAMES: tuple[str, ...] = ()  # 全部的軌：load_tracks 載完才算（sortie、duel 在前，再照檔名排，同一檔照登記先後）；別的檔讀 harness.TRACK_NAMES，不要 from … import（拿到舊的空值）
CLOCK0 = 1792900800.0  # 2026-10-25 04:00 UTC（台灣 12:00；1792900800 mod 86400 = 14400）
STEP_SECONDS = 60.0
ADMIN = "掌門"
# selftest 故意改的一個字：每一軌一句（舊名的檔、搬進包的檔兩處找），在 MUTANT_PROFILE 那一種設定跑
MUTATIONS: dict[str, tuple] = {}
MUTANT_PROFILE: dict[str, str] = {}
TRACK_REQUIRES: dict[str, str] = {}  # 只有部分根起得來的軌（軌名 → 根上要有的檔）：沒有那個檔的根，compare、selftest 略過這一軌（_tracks_on）
FULL_SAME_AS: dict[str, str] = {}  # 整段跟另一軌一模一樣的軌（軌名 → 那一軌）：compare 清單上兩軌都在時整段只跑那一軌（register_track 的 full_same_as）
SECONDS: dict[str, float] = {}  # 這一次 compare 每個子行程跑了幾秒（log 的主檔名 → 秒）；沒跑的不在表上
# 每軌走到哪幾包（register_track 的 covers，寫死在各軌檔尾），量法是 scripts/sb/covers_measure.py（第 109 批）：三種設定每軌各跑一次、sys.monitoring 記
# tianxia/ 被叫到的函式；共同組照設定各算（同一設定裡被 ≥ 90% 的軌碰到的函式：每一步的同步、選單、狀態列叫到每一包的掛鉤），扣掉之後碰到的包取聯集，
# 再併上軌讀的 web/<包>.js|css（drape、facade 在 Python 那一側幾乎不碰包）。共同組裡的包函式都要有 ALWAYS_TRACKS 碰到（analyze 守，破了結束碼 1）：
# 改到共同組的東西只靠 ALWAYS 抓。compare --covers 挑 covers 有交集的軌加上 ALWAYS_TRACKS。加軌、加包或換量法：measure → analyze → write 再量一次。
# 第 107 批（9610b568、只 season21、不扣共同組）：76 軌每一軌都走到全部 38 包，--covers 挑不掉任何一軌；第 109 批（41a6f870）扣掉之後小包挑得掉（support 3 軌、persona 4）。
COVERS: dict[str, tuple[str, ...]] = {}
ALWAYS_TRACKS = ("battle", "sortie", "progress", "switchboard", "facade", "drape")
IN_CALL = [0]  # Scenario.call 進出的深度：切點（前半寫完、快照）要在 0（不在請求中間）


# ═══════════════════════════ 調度（compare、selftest） ═══════════════════════════


def _tracks_on(tracks: list[str], root: Path) -> list[str]:
    """這個根起得來的軌；略過的寫一行，不會當成比過了。"""
    keep = []
    for t in tracks:
        need = TRACK_REQUIRES.get(t)
        if need and not (root / need).exists():
            print(f"略過 {t}：這個根沒有 {need}（合回 develop 第 1 段之前的主幹本來就沒有這一軌）")
        else:
            keep.append(t)
    return keep


def pick_tracks(packages: list[str], tracks: list[str] | None = None) -> list[str]:
    """compare --covers、pick：covers 跟這幾包有交集的軌，加上 ALWAYS_TRACKS；照 TRACK_NAMES 的先後。tracks 給了就再取交集（--tracks 同時給）。"""
    want = set(packages)
    picked = [t for t in TRACK_NAMES if t in ALWAYS_TRACKS or want & set(COVERS.get(t, ()))]
    return [t for t in picked if t in tracks] if tracks else picked


def _sqlite_file(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(16) == b"SQLite format 3\x00"


def snapshot_db(db: Path, half: Path) -> None:
    """前半的快照（第 107 批：compare --crossover 不再另開 base 前半）：db 寫出來的每樣東西（_db_files）抄到 half 的名字，只換開頭的主檔名。
    SQLite 檔用 backup()（連 -wal 裡的一起拿到一致的那一份），-wal、-shm 不抄；其他檔與資料夾原樣抄。half 原本的檔先清掉。"""
    for old in _db_files(half):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    for path in _db_files(db):
        if path.name.endswith(("-wal", "-shm")):
            continue
        dest = half.with_name(half.stem + path.name[len(db.stem):])
        if path.is_dir():
            shutil.copytree(path, dest)
        elif _sqlite_file(path):
            src, dst = sqlite3.connect(path), sqlite3.connect(dest)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        else:
            shutil.copyfile(path, dest)


def _child(args: list[str], log: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as fh:
        done = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "same_behavior.py"), *args], env=env, stdout=fh, stderr=subprocess.STDOUT)
    SECONDS[log.stem] = time.monotonic() - started
    if done.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-3000:]
        raise RuntimeError(f"{' '.join(args[:3])} 結束碼 {done.returncode}：\n{tail}")


def _digest(*paths: Path) -> tuple[str, int, int]:
    data = b"".join(p.read_bytes() for p in paths)
    return hashlib.sha256(data).hexdigest(), data.count(b"\n"), len(data)


def _first_diff(a: bytes, b: bytes) -> str:
    la, lb = a.split(b"\n"), b.split(b"\n")
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            k = next((j for j in range(min(len(x), len(y))) if x[j] != y[j]), min(len(x), len(y)))
            return (f"第 {i + 1} 行（共 {len(la)}／{len(lb)} 行）第 {k} 個位元組起：\n  base {x[max(0, k - 120):k + 200]!r}\n"
                    f"  head {y[max(0, k - 120):k + 200]!r}")
    return f"前 {min(len(la), len(lb))} 行一樣，行數 {len(la)}／{len(lb)}"


def _run_set(chains: list[list], workers: int) -> None:
    """chains：每一串是先後要跑的幾步——（引數, log）是子行程，可叫的就叫（快取的還原、跑完存起來）；前半＋後半是同一串；串與串之間平行跑。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for f in [pool.submit(lambda chain=chain: [step() if callable(step) else _child(*step) for step in chain]) for chain in chains]:
            f.result()


def _bot_runs(tracks: list[str]) -> list[tuple[str, str]]:
    """（seats, 設定）：每一軌登記的假人（register_bots）跑它登記的那幾種設定；軌不在清單上的不跑。"""
    return [(seats, p) for seats, (profiles, _) in BOT_SEATS.items() if seats in tracks for p in profiles]


def _db_files(db: Path) -> list[Path]:
    """這個資料庫寫出來的每樣東西：<主檔名>-*（旁邊的小檔、-vapid.pem、資料夾）與 <主檔名>.db*（-wal、-shm、.state.json、各軌的 .db.<軌>.json）。
    前半的快照一定走這裡：_wipe_db 那張清單少 -vapid.pem 與 .db.<軌>.json，少抄的話後半換一把鑰匙或直接炸。"""
    return [p for p in db.parent.iterdir() if p.name.startswith((f"{db.stem}-", db.name))]


def _base_step(step: tuple, folder: Path | None, cell: str, out: Path, db: Path | None = None, half_out: Path | None = None):
    """base 那一步。沒開快取：原樣。命中：換成還原，不開子行程。沒命中：跑完存起來（子行程結束碼非 0 時 _child 丟例外，壞的存不進去）。
    half_out（第 107 批，base 整段同時出前半與快照）：db 是快照的名字，這一格多存前半輸出（half.gz）與快照。"""
    if folder is None:
        return step
    if cache.hit(folder, cell):

        def restore() -> None:
            for path in _db_files(db) if db else ():  # --part second 不會自己清
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            cache.restore(folder, cell, out, db, half_out)

        return restore

    def run_and_save() -> None:
        _child(*step)
        cache.save(folder, cell, out, _db_files(db) if db else (), db.stem if db else "", half_out)

    return run_and_save


def _print_seconds(label: str, outputs: dict, bot_out: dict, twins: dict[str, str], crossover: bool = True) -> None:
    """每格每個子行程幾秒、最慢的十格（照那一格跑過的秒數加總）。這幾行不准出現閘門當紅的字（wave_gate.red_lines）。"""
    totals: dict[str, float] = {}

    def line(name: str, n: str, kinds: tuple[tuple[str, str], ...], twin: str = "") -> None:
        cells = []
        for word, stem in kinds:
            spent = SECONDS.get(f"{label}_{stem}_{n}")
            totals[name] = totals.get(name, 0.0) + (spent or 0.0)
            if spent is not None:
                cells.append(f"{word} {spent:.1f}")
            elif twin and stem in ("base", "head"):
                cells.append(f"{word} 同 {twin}")
            elif stem in ("base1", "head2") and not crossover:
                cells.append(f"{word} 沒跑")
            elif stem == "base1" and not twin:  # 第 107 批：前半併在 base 整段裡（快照）
                cells.append(f"{word} 併在 base")
            else:
                cells.append(f"{word} 快取")
        print(f"秒數 {name} " + " ".join(cells))

    for t, p in outputs:
        line(f"{t} {p}", f"{t}_{p}", (("base", "base"), ("head", "head"), ("前半", "base1"), ("後半", "head2")), twins.get(t, ""))
    for seats, p in bot_out:
        line(f"假人 {seats} {p}", f"{seats}_{p}", (("base", "bots_base"), ("head", "bots_head")))
    for name, spent in sorted(totals.items(), key=lambda kv: -kv[1])[:10]:
        print(f"最慢 {spent:.1f} {name}")


def check_new(base: Path, head: Path, names: tuple[str, ...], also_existing: bool = False) -> None:
    """--new 只給真的新的包：base 已經有的扣掉就藏差異了，head 沒有的是打錯字。
    also_existing（K 波 --also-existing）：同一包的後續批，base 已經有也放行；head 沒有照舊拒絕。"""
    for name in names:
        if not also_existing and (base / "tianxia" / "features" / name).exists():
            raise SystemExit(f"--new {name}：base 已經有這一包，不是新包")
        if not (head / "tianxia" / "features" / name).is_dir():
            raise SystemExit(f"--new {name}：head 沒有這一包")


def _print_new(names: tuple[str, ...], outs: list[Path]) -> None:
    """head 的子行程各自記下扣了什麼（<輸出檔>.new.json，write_new）：合起來印一行。"""
    seen: dict[str, set[str]] = {}
    for out in outs:
        path = Path(f"{out}.new.json")
        if path.exists():
            for kind, items in json.loads(path.read_text(encoding="utf-8")).items():
                seen.setdefault(kind, set()).update(items)
    listed = "、".join(f"{kind} {' '.join(sorted(seen[kind]))}" for kind in NEW_KINDS if seen.get(kind))
    print(f"新包 {'、'.join(names)} 帶來、扣掉的差異：{listed or '沒有'}")


def compare(base: Path, head: Path, tmp: Path, profiles: list[str], workers: int, bots: bool, label: str = "compare",
            tracks: list[str] | None = None, cache_dir: Path | None = None, new: tuple[str, ...] = (), crossover: bool = False,
            also_existing: bool = False) -> bool:
    """crossover（第 107 批 --crossover，PM 定改預設）：才比「base 整段」＝「base 前半＋head 後半」；不帶就不跑那一串，每格印「半舊半新 沒跑」。
    also_existing（K 波）：--new 的包 base 已經有也收（扣法一樣，base 的子行程也扣：兩邊都不比這幾包自己的 js、css、表、op）。"""
    check_new(base, head, new, also_existing)
    head_new = ["--new", ",".join(new)] if new else []  # 只有 head 的子行程帶（整段、後半、假人）
    # --also-existing（K 波）：base 也有這幾包，base 的子行程同樣扣（不然 base 多出包自己的行、head 扣掉，反而紅）；快取的鍵分開
    base_new, tag = (head_new, "_new_" + "_".join(new)) if (new and also_existing) else ([], "")
    tmp.mkdir(parents=True, exist_ok=True)
    tracks = tracks or list(TRACK_NAMES)
    SECONDS.clear()
    twins = {t: FULL_SAME_AS[t] for t in tracks if FULL_SAME_AS.get(t) in tracks}  # 清單上有那一軌才省；只有這一軌就照舊自己跑
    folder = cache.open_folder(cache_dir, base, Path(__file__).resolve().parents[1]) if cache_dir else None  # sb/cache.py；鍵只看 base，head 永遠跑
    chains, outputs = [], {}
    for t in tracks:
        for p in profiles:
            n = f"{t}_{p}"
            o = {k: tmp / f"{label}_{k}_{n}.txt" for k in ("base", "head", "base1", "head2")}
            dbs = {k: tmp / f"{label}_{k}_{n}.db" for k in ("base", "head", "half")}
            outputs[(t, p)] = o
            run = ["--tmp", str(tmp), "--track", t]
            second = (["run", str(head), p, str(o["head2"]), *run, "--db", str(dbs["half"]), "--part", "second", *head_new], tmp / f"{label}_head2_{n}.log")
            if t in twins:  # 整段比那一軌跑出來的（檔名照命名算，清單的先後不影響）；後半照舊接，宣告過時會紅
                o["base"], o["head"] = (tmp / f"{label}_{k}_{twins[t]}_{p}.txt" for k in ("base", "head"))
                if crossover:  # 切點跟那一軌不同，前半照舊另開（保守：整段借那一軌的）
                    chains.append([
                        _base_step((["run", str(base), p, str(o["base1"]), *run, "--db", str(dbs["half"]), "--part", "first", *base_new], tmp / f"{label}_base1_{n}.log"),
                                   folder, f"first_{n}{tag}", o["base1"], dbs["half"]),
                        second,
                    ])
                continue
            full = ["run", str(base), p, str(o["base"]), *run, "--db", str(dbs["base"]), *base_new]
            if crossover:  # 第 107 批：base 整段跑到切點時同時寫前半與快照（--snapshot），head 後半從快照接，不再另開 base 前半
                full += ["--snapshot", str(dbs["half"]), "--snapshot-out", str(o["base1"])]
                chains.append([_base_step((full, tmp / f"{label}_base_{n}.log"), folder, f"allx_{n}{tag}", o["base"], dbs["half"], o["base1"]), second])
            else:
                chains.append([_base_step((full, tmp / f"{label}_base_{n}.log"), folder, f"all_{n}{tag}", o["base"])])
            chains.append([(["run", str(head), p, str(o["head"]), *run, "--db", str(dbs["head"]), *head_new], tmp / f"{label}_head_{n}.log")])
    bot_out = {}
    if bots:
        for seats, p in [r for r in _bot_runs(tracks) if r[1] in profiles]:  # --profiles 給什麼就跑什麼
            n = f"{seats}_{p}"
            bot_out[(seats, p)] = {k: tmp / f"{label}_bots_{k}_{n}.txt" for k in ("base", "head")}
            for k, root in (("base", base), ("head", head)):
                step = (["bots", str(root), p, str(bot_out[(seats, p)][k]), "--tmp", str(tmp / f"{label}_bots_{k}_{n}"),
                         "--seats", seats, *(head_new if k == "head" else base_new)], tmp / f"{label}_bots_{k}_{n}.log")
                chains.append([_base_step(step, folder, f"bots_{n}{tag}", bot_out[(seats, p)][k]) if k == "base" else step])
    started = time.time()
    _run_set(chains, workers)
    ok = True
    print(f"跑完 {time.time() - started:.0f} 秒")
    for (t, p), o in outputs.items():
        hb, nb, bb = _digest(o["base"])
        hh, nh, bh = _digest(o["head"])
        if crossover:
            hx, nx, bx = _digest(o["base1"], o["head2"])
            half = hb == hx
            cross = f"｜base 前半＋head 後半 {hx[:16]} {'一樣' if half else '不一樣'}"
        else:  # 第 107 批：不帶 --crossover 不跑這一串（閘門 --changed 只在改到存檔欄位時才帶）
            half, cross = True, "｜半舊半新 沒跑"
        same = hb == hh
        ok &= same and half
        print(f"{t:6} {p:9} 整段 base {nb} 行 {bb} 位元組 {hb[:16]}｜head {hh[:16]} {'一樣' if same else '不一樣'}"
              + cross + (f"（整段同 {twins[t]}）" if t in twins else ""))
        if not same:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
        if not half:
            print("  半舊半新：" + _first_diff(o["base"].read_bytes(), o["base1"].read_bytes() + o["head2"].read_bytes()))
    for (seats, p), o in bot_out.items():
        hb, nb, bb = _digest(o["base"])
        hh, _, _ = _digest(o["head"])
        ok &= hb == hh
        print(f"假人 {seats:6} {p:9} {nb} 行 {bb} 位元組 base {hb[:16]}｜head {hh[:16]} {'一樣' if hb == hh else '不一樣'}")
        if hb != hh:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
    _print_seconds(label, outputs, bot_out, twins, crossover)
    if folder:
        print(f"快取：命中 {cache.hits} 格、沒命中 {cache.misses} 格、{folder} {cache.megabytes(folder):.0f} MB")
    if new:
        _print_new(new, [o[k] for o in outputs.values() for k in ("head", "head2")] + [o["head"] for o in bot_out.values()])
    return ok


def _mutant(base: Path, tmp: Path, track: str) -> Path:
    """base 抄一份、那一軌的一句改一個字（MUTATIONS[track]：列的幾個檔裡找，哪一處有就改哪一處）。"""
    files, (old, new) = MUTATIONS[track]
    dest = tmp / f"mutant_{track}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=shutil.ignore_patterns(".git", "saves", ".local", "__pycache__", "node_modules", ".venv", "docs"))
    for rel in files:
        path = dest / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if text.count(old) == 1:
            path.write_text(text.replace(old, new), encoding="utf-8")
            return dest
    raise RuntimeError("找不到要改的那一句")


def _selftest_cache(base: Path, tmp: Path, profiles: list[str], workers: int, tracks: list[str], mutants: dict[str, Path], cache_dir: Path) -> bool:
    """selftest --cache：快取本身穩不穩，每一軌在 MUTANT_PROFILE 那一種設定跑四次 compare。這幾次 compare 自己會印「不一樣」，這裡只看回傳值與命中數。
    1. compare(base, base)（快取 A）：先填，要全部一樣。
    2. 同一對再跑：要有命中、全部一樣。前半快照接後半的雜湊等於整段就是這一條。
    3. compare(base, mutant)：base 要有命中、要抓到不一樣。開快取時改一個字照樣抓得到。
    4. compare(mutant, base)（快取 B，先抄一份 A：A 要留給下一軌；空的快取本來就全部沒命中，等於沒驗）：要全部沒命中、要抓到不一樣。base 改一個字不會假綠。"""
    a, b = cache_dir / "selftest_a", cache_dir / "selftest_b"
    shutil.rmtree(a, ignore_errors=True)
    ok = True
    for t in tracks:
        p = MUTANT_PROFILE[t]
        if p not in profiles:
            continue
        fill = compare(base, base, tmp, [p], workers, True, "selfcache1", [t], a, crossover=True)
        filled = cache.misses
        again = compare(base, base, tmp, [p], workers, True, "selfcache2", [t], a, crossover=True)
        hit2, miss2 = cache.hits, cache.misses
        caught_head = not compare(base, mutants[t], tmp, [p], workers, True, "selfcache3", [t], a, crossover=True)
        hit3 = cache.hits
        shutil.rmtree(b, ignore_errors=True)
        shutil.copytree(a, b)
        caught_base = not compare(mutants[t], base, tmp, [p], workers, True, "selfcache4", [t], b, crossover=True)
        hit4, miss4 = cache.hits, cache.misses
        ok &= fill and filled > 0 and again and hit2 > 0 and miss2 == 0 and caught_head and hit3 > 0 and caught_base and hit4 == 0 and miss4 > 0
        print(f"快取 {t} {p} 填 {filled}{'' if fill else ' 不一樣'}｜再跑命中 {hit2} 沒命中 {miss2} {'一樣' if again else '不一樣'}"
              f"｜改 head 命中 {hit3} {'抓得到' if caught_head else '抓不到'}｜改 base 命中 {hit4} 沒命中 {miss4} {'抓得到' if caught_base else '抓不到'}")
    shutil.rmtree(a, ignore_errors=True)
    shutil.rmtree(b, ignore_errors=True)
    return ok


def selftest(base: Path, tmp: Path, profiles: list[str], workers: int, tracks: list[str] | None = None, cache_dir: Path | None = None) -> bool:
    """比對本身穩不穩：同一份跑兩次一樣、前半＋後半（base 接 base）＝整段、改一個字（mutant，每一軌在 MUTANT_PROFILE 那一種設定跑）抓得到差。"""
    tmp.mkdir(parents=True, exist_ok=True)
    tracks = tracks or list(TRACK_NAMES)
    mutants = {t: _mutant(base, tmp, t) for t in tracks}
    chains, outs = [], {}
    for t in tracks:
        for p in profiles:
            n = f"{t}_{p}"
            o = {k: tmp / f"self_{k}_{n}.txt" for k in ("a", "b", "first", "second", "mut")}
            outs[(t, p)] = o
            run = ["--tmp", str(tmp), "--track", t]
            half = tmp / f"self_half_{n}.db"
            second = (["run", str(base), p, str(o["second"]), *run, "--db", str(half), "--part", "second"], tmp / f"self_second_{n}.log")
            # 第 107 批：a 那一趟帶 --snapshot（整段同時出前半與快照），後半從快照接；b 不帶，a＝b 證明快照不擾動。整段同一軌的（muster）照舊 first→second
            snap = [] if FULL_SAME_AS.get(t) else ["--snapshot", str(half), "--snapshot-out", str(o["first"])]
            a_run = (["run", str(base), p, str(o["a"]), *run, "--db", str(tmp / f"self_a_{n}.db"), *snap], tmp / f"self_a_{n}.log")
            chains.append([a_run, second] if snap else [a_run])
            chains.append([(["run", str(base), p, str(o["b"]), *run, "--db", str(tmp / f"self_b_{n}.db")], tmp / f"self_b_{n}.log")])
            if not snap:
                chains.append([(["run", str(base), p, str(o["first"]), *run, "--db", str(half), "--part", "first"], tmp / f"self_first_{n}.log"), second])
            if p == MUTANT_PROFILE[t]:
                chains.append([(["run", str(mutants[t]), p, str(o["mut"]), *run, "--db", str(tmp / f"self_mut_{n}.db")], tmp / f"self_mut_{n}.log")])
    bot_out = {}
    for seats, p in [r for r in _bot_runs(tracks) if r[1] in profiles]:
        n = f"{seats}_{p}"
        bot_out[(seats, p)] = {k: tmp / f"self_bots_{k}_{n}.txt" for k in ("a", "b")}
        for k in ("a", "b"):
            chains.append([(["bots", str(base), p, str(bot_out[(seats, p)][k]), "--tmp", str(tmp / f"self_bots_{k}_{n}"), "--seats", seats],
                            tmp / f"self_bots_{k}_{n}.log")])
    started = time.time()
    _run_set(chains, workers)
    print(f"跑完 {time.time() - started:.0f} 秒")
    ok = True
    for (t, p), o in outs.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        hx, _, _ = _digest(o["first"], o["second"])
        ok &= ha == hb and ha == hx
        line = (f"{t:6} {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}｜前半＋後半 {'一樣' if ha == hx else '不一樣'}"
                f"（{'前半 base 整段' if not FULL_SAME_AS.get(t) else '前半另開'}）｜切點 不在請求中")  # 切點在請求中間的話子行程丟例外，到不了這裡
        if p == MUTANT_PROFILE[t]:
            hm, _, _ = _digest(o["mut"])
            caught = hm != ha
            ok &= caught
            line += f"｜改一個字 {'抓得到' if caught else '抓不到'}"
            if caught:
                line += "（" + _first_diff(o["a"].read_bytes(), o["mut"].read_bytes()).split("：")[0] + "）"
        twin = FULL_SAME_AS.get(t)
        if twin in tracks:  # 宣告整段同一軌：selftest 照舊跑兩次，多比一次宣告還成不成立
            alike = ha == _digest(outs[(twin, p)]["a"])[0]
            ok &= alike
            line += f"｜整段同 {twin} {'一樣' if alike else '不一樣'}"
        print(line)
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
        if ha != hx:
            print("  " + _first_diff(o["a"].read_bytes(), o["first"].read_bytes() + o["second"].read_bytes()))
    for (seats, p), o in bot_out.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        ok &= ha == hb
        print(f"假人 {seats:6} {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}")
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
    if cache_dir:
        ok &= _selftest_cache(base, tmp, profiles, workers, tracks, mutants, cache_dir)
    return ok


# ═══════════════════════════ 子行程共用：固定的那幾層 ═══════════════════════════

CLOCK = [CLOCK0]
STEP = [0]
MODEL = {"judge": False}
BUF = io.StringIO()


def _fake_time() -> float:
    CLOCK[0] += 0.5
    return CLOCK[0]


def _fake_monotonic() -> float:
    """server._monotonic：同一顆鐘，讀的時候不往前推（只有 time.time 推）。"""
    return CLOCK[0]


def _setup_child(root: Path, profile: str, db: Path) -> None:
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("要帶 PYTHONHASHSEED=0 跑（compare／selftest 會自己帶）")
    os.environ["TIANXIA_DB"] = str(db)
    if profile in ("none", "test"):
        os.environ.pop("TIANXIA_PROFILE", None)
    else:
        os.environ["TIANXIA_PROFILE"] = profile
    os.environ["TIANXIA_ADMINS"] = ADMIN
    os.environ.pop("TIANXIA_PUBLIC_URL", None)
    here = str(Path(__file__).resolve().parents[1])  # scripts/（這個檔在 scripts/sb/）
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != Path(here)]  # 不讓這一份 scripts/ 蓋掉被比的那一份
    sys.path.insert(0, str(root))
    os.chdir(root)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    time.time = _fake_time
    original = random.Random.__init__

    def seeded(self, x=None):  # Game 的預設 rng（rng or random.Random()）與各處沒給種子的 Random() 都從這裡固定：照步數換
        original(self, 12345 + 7919 * STEP[0] if x is None else x)  # （每一步同一顆的話，同樣長的清單永遠挑到同一個）

    random.Random.__init__ = seeded
    random.seed(0)

    import requests

    from tianxia import ollama_client

    real_from_config = ollama_client.OllamaClient.from_config.__func__

    class DeadClient(ollama_client.OllamaClient):
        def warm(self, *a, **k):
            return False

        def chat_text(self, *a, **k):
            raise requests.ConnectionError("same_behavior：不連模型")

        def chat_structured(self, *a, **k):
            raise requests.ConnectionError("same_behavior：不連模型")

    class JudgeClient(DeadClient):
        def chat_structured(self, messages, schema, *a, **k):
            if schema.__name__ == "Judgment" and schema.__module__.endswith("fight_llm"):
                return schema(advantage=8, winning="你搶得先機，一路壓著對手打。", losing="對手壓住了你，你只能且戰且退。")
            raise requests.ConnectionError("same_behavior：不連模型")

    class ZhuanClient(DeadClient):
        """列傳那一軌「模型回了」（MODEL["zhuan"]，全部拆包第 29 批）：寫傳（chat_text）回一篇照名號寫的固定長文，人物評曰（VerdictText）回一句固定的話；
        其餘叫法照 DeadClient 丟連線錯誤。"""

        def chat_text(self, messages, *a, **k):
            ask = messages[-1]["content"]
            name = ask.split("「", 1)[1].split("」", 1)[0] if "「" in ask else "某人"
            para = "其後遇事不退，臨陣不亂，同道多敬重之，鄉里亦稱其信義。" * 3
            return f"{name}者，本是江湖中人，少有志氣，不甘平庸。{para}\n\n{para}\n\n{para}\n\n評曰：{name}一路行來，所守者信義而已，足以記之。"

        def chat_structured(self, messages, schema, *a, **k):
            if schema.__name__ == "VerdictText":
                return schema(verdict="一諾千金，臨事不苟，可託大事。")
            raise requests.ConnectionError("same_behavior：不連模型")

    def from_config(cls, cfg):
        client = real_from_config(cls, cfg)
        client.__class__ = ZhuanClient if MODEL.get("zhuan") else (JudgeClient if MODEL["judge"] else DeadClient)
        return client

    ollama_client.OllamaClient.from_config = classmethod(from_config)


def _wipe_db(db: Path) -> None:
    """同一個暫存資料夾跑第二次之前清掉上一次的資料庫與旁邊的小檔（小檔的名字是 <主檔名去掉副檔名>-xxx.sqlite，不接在主檔名後面）：
    留著的話舊的往來紀錄、戰記、封存會被讀到，「同一份跑兩次一樣」就不穩。"""
    sides = ("talk", "talk-archive", "tale", "narration", "archive", "push", "identity", "support")  # identity：帳號綁定（第 201 批）；support：客服單（第 211 批；開關關著不建）
    names = [db.name, f"{db.name}.state.json"] + [f"{db.stem}-{side}.sqlite" for side in sides]
    for name in names:
        for suffix in ("", "-wal", "-shm"):
            p = db.with_name(name + suffix)
            if p.exists():
                p.unlink()


def emit(tag: str, value) -> None:
    BUF.write(f"## {STEP[0]:04d} {tag}\n")
    BUF.write(json.dumps(value, ensure_ascii=False) + "\n")


# 公開頁（/zhuan/<代碼>、/zhanji/<代碼>）頁上的程式：第 213 批（CSP）把 inline 的 <script>…</script> 原樣搬成 web/zhuan_page.js、
# web/tale_page.js，頁裡改寫 <script src>。印整頁的軌（scribe、zhuan、zhuanframe、portrait）兩邊都換成同一個記號，其餘 HTML 照比；
# 搬出去的內容跟原本 inline 的一字不差（L 波合併時核對過），script 本身由那兩包的網頁測試與 tests/web/test_csp_web.py 守。
PAGE_SCRIPT = re.compile(r'<script src="/static/(?:zhuan|tale)_page\.js(?:\?v=[0-9a-f]+)?"></script>|<script>.*?</script>', re.S)


def page_script(html: str) -> str:
    return PAGE_SCRIPT.sub("<script>[page-script]</script>", html)


# compare --new：head 的子行程才有值（same_behavior 的 run、bots 叫 set_new）；base 的子行程這裡全是空的，走原路、輸出一個位元組不變。
NEW: dict = {"packages": (), "seen": {}}
NEW_KINDS = ("js", "css", "表", "op", "管理者動作")


def set_new(names) -> None:
    """記下這幾包是新包。這裡不 import registry：多一次 import 可能動到亂數先後；第一次用到才 import（new_features）。"""
    NEW["packages"], NEW["seen"] = tuple(names), {}


def note_new(kind: str, what: str) -> None:
    NEW["seen"].setdefault(kind, set()).add(what)


def write_new(out: Path) -> None:
    """扣了什麼寫 <輸出檔>.new.json，compare 比完讀回來；沒帶 --new 不寫。"""
    if NEW["packages"]:
        Path(f"{out}.new.json").write_text(json.dumps({kind: sorted(items) for kind, items in NEW["seen"].items()}, ensure_ascii=False), encoding="utf-8")


def new_features() -> list:
    if not NEW["packages"]:
        return []
    from tianxia.core.registry import FEATURES  # 子行程 chdir 到被比的根之後才有

    return [feature for feature in FEATURES if feature.name in NEW["packages"]]


def new_web() -> frozenset[str]:
    """這幾包 web 宣告的 js、css（facade、drape 不算進行數與規則，版本號照驗）。"""
    return frozenset(name for feature in new_features() for name in feature.web)


def new_ops(server) -> dict[str, set[str]]:
    """這幾包帶來的 op：main_actions、menxia_actions、admin_tools 的鍵（switchboard 那幾張表扣掉）。"""
    ops: dict[str, set[str]] = {"main": set(), "menxia": set(), "admin": set()}
    for feature in new_features():
        ops["main"] |= set(feature.main_actions(server))
        ops["menxia"] |= set(feature.menxia_actions(server))
        ops["admin"] |= set(feature.admin_tools(server))
    for op in ops["main"] | ops["menxia"]:
        note_new("op", op)
    for op in ops["admin"]:
        note_new("管理者動作", op)
    return ops


def is_new_table(name: str) -> bool:
    """只扣帶包名前綴的表（mall_* 的前例）；不帶的照紅，免得順手藏掉別的表。"""
    return any(name == package or name.startswith(f"{package}_") for package in NEW["packages"])


def db_text(path: Path) -> str:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = []
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            if is_new_table(table):
                note_new("表", table)
                continue
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
            rows = []
            for row in con.execute(f"SELECT * FROM {table}").fetchall():
                row = list(row)
                if table == "logins":
                    for name in ("salt", "hash"):
                        if name in cols:
                            row[cols.index(name)] = "<抹掉>"
                if table == "sessions" and "token_hash" in cols:  # 登入狀態進資料庫（審查修正，develop 6d926c17 起）：token 每次隨機
                    row[cols.index("token_hash")] = "<抹掉>"
                rows.append(repr(row))
            rows.sort()
            out.append(f"### {table} {cols}\n" + "\n".join(rows))
        return "\n".join(out) + "\n"
    finally:
        con.close()


class _TrackTable(dict):
    """軌的表：同一個名字再登記一次就丟 ValueError。register_track 全部走到這裡；不擋的話後登記的默默蓋掉前面那一軌，那一軌就少驗了（第 B 波碰到 loom、abacus 各撞一次）。"""

    def __setitem__(self, name: str, scenario: type) -> None:
        if name in self:
            raise ValueError(f"軌名 {name} 登記了兩次：{self[name].__name__} 與 {scenario.__name__}")
        super().__setitem__(name, scenario)


TRACKS = _TrackTable()


# ═══════════════════════════ 軌與子命令的登記：sb/tracks/*.py 載入時自己登記 ═══════════════════════════

BOT_SEATS: dict[str, tuple[tuple[str, ...], Callable[..., None]]] = {}  # bots --seats 的名字 → （跑哪幾種設定, 跑的函式）
SUBCOMMANDS: dict[str, Callable[[list[str]], int]] = {}  # 子命令名 → 處理函式（整串引數給它）；入口的 main 先查這張表


def register_track(name: str, scenario: type, mutation: tuple, profile: str, *, full_same_as: str = "", covers: tuple[str, ...] = ()) -> None:
    """再開一軌（TRACKS、MUTATIONS、MUTANT_PROFILE 三張表一起登記；同一個軌名再登記一次，TRACKS 丟 ValueError）。TRACK_NAMES 由 load_tracks 照檔名算。
    full_same_as：這一軌跟那一軌同一套段落、只有切點不同，整段一個位元組都一樣（那一軌要先登記）。compare 清單上兩軌都在時省這一軌的 base、head 整段；
    後半照舊比那一軌的 base，宣告過時會紅。
    covers（第 107 批）：這一軌走到哪幾包（量法見 COVERS），compare --covers、pick 用；tests/core/test_same_behavior_covers.py 守它非空、包都在。"""
    if full_same_as:
        twin = TRACKS.get(full_same_as)
        if twin is None or not issubclass(scenario, twin) or scenario.PHASES_FIRST + scenario.PHASES_SECOND != twin.PHASES_FIRST + twin.PHASES_SECOND:
            raise ValueError(f"軌 {name} 不能宣告整段同 {full_same_as}：要是它的子類別、段落接起來要一樣")
        FULL_SAME_AS[name] = full_same_as
    TRACKS[name] = scenario
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile
    COVERS[name] = tuple(covers)


def register_bots(seats: str, profiles: tuple[str, ...], runner: Callable[..., None]) -> None:
    """再開一組假人：compare、selftest 在那些設定各跑一次，bots --seats <seats> 叫 runner(根, 設定, 輸出檔, 暫存)。"""
    if seats in BOT_SEATS:
        raise ValueError(f"假人 {seats} 登記了兩次")
    BOT_SEATS[seats] = (tuple(profiles), runner)


def load_tracks() -> None:
    """載入 sb/base.py 與 sb/tracks/ 底下每一檔（照檔名），各檔自己登記；跑完 TRACK_NAMES 才是全部的軌。
    入口 import 時就叫：_setup_child 會把 scripts/ 從 sys.path 拿掉，之後載不到。每個子行程都載入全部的軌，不能只載自己那一軌：
    facade.py 改寫 MapScenario.web，只載 map 的話 map、stack 的輸出就變了。"""
    global TRACK_NAMES
    importlib.import_module("sb.base")
    for path in sorted((Path(__file__).resolve().parent / "tracks").glob("*.py")):
        if path.stem != "__init__":
            importlib.import_module(f"sb.tracks.{path.stem}")
    TRACK_NAMES = tuple(sorted(TRACKS, key=lambda t: (TRACKS[t].__module__ != "sb.base", TRACKS[t].__module__)))  # sorted 穩定：同一檔照登記先後
