"""same_behavior 的調度與固定層：compare、selftest、子行程的假時鐘假模型與資料庫文字、軌的登記表（第二輪第 70 批）。"""
from __future__ import annotations

import concurrent.futures
import hashlib
import importlib
import io
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

PROFILES = ("season21", "week7", "test")  # 拿掉二（甲）：none、weekend 關門，不再是可以選的設定
TRACK_NAMES: tuple[str, ...] = ()  # 全部的軌：load_tracks 載完才算（sortie、duel 在前，再照檔名排，同一檔照登記先後）；別的檔讀 harness.TRACK_NAMES，不要 from … import（拿到舊的空值）
CLOCK0 = 1792900800.0  # 2026-10-25 04:00 UTC（台灣 12:00；1792900800 mod 86400 = 14400）
STEP_SECONDS = 60.0
ADMIN = "掌門"
# selftest 故意改的一個字：每一軌一句（舊名的檔、搬進包的檔兩處找），在 MUTANT_PROFILE 那一種設定跑
MUTATIONS: dict[str, tuple] = {}
MUTANT_PROFILE: dict[str, str] = {}
TRACK_REQUIRES: dict[str, str] = {}  # 只有部分根起得來的軌（軌名 → 根上要有的檔）：沒有那個檔的根，compare、selftest 略過這一軌（_tracks_on）


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


def _child(args: list[str], log: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
    with log.open("w", encoding="utf-8") as fh:
        done = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "same_behavior.py"), *args], env=env, stdout=fh, stderr=subprocess.STDOUT)
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


def _run_set(chains: list[list[tuple[list[str], Path]]], workers: int) -> None:
    """chains：每一串是先後要跑的幾個子行程（引數, log）——前半＋後半是同一串；串與串之間平行跑。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for f in [pool.submit(lambda chain=chain: [_child(*step) for step in chain]) for chain in chains]:
            f.result()


def _bot_runs(tracks: list[str]) -> list[tuple[str, str]]:
    """（seats, 設定）：每一軌登記的假人（register_bots）跑它登記的那幾種設定；軌不在清單上的不跑。"""
    return [(seats, p) for seats, (profiles, _) in BOT_SEATS.items() if seats in tracks for p in profiles]


def compare(base: Path, head: Path, tmp: Path, profiles: list[str], workers: int, bots: bool, label: str = "compare",
            tracks: list[str] | None = None) -> bool:
    tmp.mkdir(parents=True, exist_ok=True)
    tracks = tracks or list(TRACK_NAMES)
    chains, outputs = [], {}
    for t in tracks:
        for p in profiles:
            n = f"{t}_{p}"
            o = {k: tmp / f"{label}_{k}_{n}.txt" for k in ("base", "head", "base1", "head2")}
            dbs = {k: tmp / f"{label}_{k}_{n}.db" for k in ("base", "head", "half")}
            outputs[(t, p)] = o
            run = ["--tmp", str(tmp), "--track", t]
            chains.append([(["run", str(base), p, str(o["base"]), *run, "--db", str(dbs["base"])], tmp / f"{label}_base_{n}.log")])
            chains.append([(["run", str(head), p, str(o["head"]), *run, "--db", str(dbs["head"])], tmp / f"{label}_head_{n}.log")])
            chains.append([
                (["run", str(base), p, str(o["base1"]), *run, "--db", str(dbs["half"]), "--part", "first"], tmp / f"{label}_base1_{n}.log"),
                (["run", str(head), p, str(o["head2"]), *run, "--db", str(dbs["half"]), "--part", "second"], tmp / f"{label}_head2_{n}.log"),
            ])
    bot_out = {}
    if bots:
        for seats, p in [r for r in _bot_runs(tracks) if r[1] in profiles]:  # --profiles 給什麼就跑什麼
            n = f"{seats}_{p}"
            bot_out[(seats, p)] = {k: tmp / f"{label}_bots_{k}_{n}.txt" for k in ("base", "head")}
            for k, root in (("base", base), ("head", head)):
                chains.append([(["bots", str(root), p, str(bot_out[(seats, p)][k]), "--tmp", str(tmp / f"{label}_bots_{k}_{n}"),
                                 "--seats", seats], tmp / f"{label}_bots_{k}_{n}.log")])
    started = time.time()
    _run_set(chains, workers)
    ok = True
    print(f"跑完 {time.time() - started:.0f} 秒")
    for (t, p), o in outputs.items():
        hb, nb, bb = _digest(o["base"])
        hh, nh, bh = _digest(o["head"])
        hx, nx, bx = _digest(o["base1"], o["head2"])
        same, half = hb == hh, hb == hx
        ok &= same and half
        print(f"{t:6} {p:9} 整段 base {nb} 行 {bb} 位元組 {hb[:16]}｜head {hh[:16]} {'一樣' if same else '不一樣'}"
              f"｜base 前半＋head 後半 {hx[:16]} {'一樣' if half else '不一樣'}")
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
    return ok


def _mutant(base: Path, tmp: Path, track: str) -> Path:
    """base 抄一份、那一軌的一句改一個字（MUTATIONS[track]：舊名的檔與搬進包的檔兩處找，哪一處有就改哪一處）。"""
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


def selftest(base: Path, tmp: Path, profiles: list[str], workers: int, tracks: list[str] | None = None) -> bool:
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
            for k in ("a", "b"):
                chains.append([(["run", str(base), p, str(o[k]), *run, "--db", str(tmp / f"self_{k}_{n}.db")], tmp / f"self_{k}_{n}.log")])
            chains.append([
                (["run", str(base), p, str(o["first"]), *run, "--db", str(tmp / f"self_half_{n}.db"), "--part", "first"], tmp / f"self_first_{n}.log"),
                (["run", str(base), p, str(o["second"]), *run, "--db", str(tmp / f"self_half_{n}.db"), "--part", "second"],
                 tmp / f"self_second_{n}.log"),
            ])
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
        line = (f"{t:6} {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}｜前半＋後半 {'一樣' if ha == hx else '不一樣'}")
        if p == MUTANT_PROFILE[t]:
            hm, _, _ = _digest(o["mut"])
            caught = hm != ha
            ok &= caught
            line += f"｜改一個字 {'抓得到' if caught else '抓不到'}"
            if caught:
                line += "（" + _first_diff(o["a"].read_bytes(), o["mut"].read_bytes()).split("：")[0] + "）"
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
    sides = ("talk", "talk-archive", "tale", "narration", "archive", "push")
    names = [db.name, f"{db.name}.state.json"] + [f"{db.stem}-{side}.sqlite" for side in sides]
    for name in names:
        for suffix in ("", "-wal", "-shm"):
            p = db.with_name(name + suffix)
            if p.exists():
                p.unlink()


def emit(tag: str, value) -> None:
    BUF.write(f"## {STEP[0]:04d} {tag}\n")
    BUF.write(json.dumps(value, ensure_ascii=False) + "\n")


def db_text(path: Path) -> str:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = []
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
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


def register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、MUTATIONS、MUTANT_PROFILE 三張表一起登記；同一個軌名再登記一次，TRACKS 丟 ValueError）。TRACK_NAMES 由 load_tracks 照檔名算。"""
    TRACKS[name] = scenario
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


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
