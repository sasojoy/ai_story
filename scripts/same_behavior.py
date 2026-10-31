"""前後一字不變的對照（開發規範手冊第 2 階「主動搬六包」；批次表 docs/superpowers/plans/2026-10-31-主動搬六包-批次.md 第二節）。

同一支腳本拿兩份程式（base、head：各是一個解開的 git archive 或工作樹）各跑一次，比輸出的 sha256，逐位元組、不排序鍵
（/api/main 的鍵順序算行為）。只打公開的 API（FastAPI 的 TestClient）；擺局面（站哪裡、陣營、新手期、體力、軍令）直接改資料庫，
伺服器每次進鎖本來就從資料庫重讀。第 1 批（出陣）收進來；之後每一批加自己的情境，第 11 批全部重跑。情境分軌（--track）：
sortie 是第 1 批的（Scenario：出陣本體、混戰、出陣回報），duel 是第 2 批的（DuelScenario：出陣約戰）；每一軌自己一個資料庫、
自己切一半（同一個切點放不下兩種窗：混戰的 10 分與約戰的 10 分）。之後的批可以接在某一軌的段落後面，或照這樣再開一軌。

用法（python 不加 -I：-I 會連 PYTHONHASHSEED 一起忽略；子行程自己帶 PYTHONHASHSEED=0）：
  python scripts/same_behavior.py compare --base <根> --head <根> --tmp <暫存資料夾> [--profiles none,weekend,...] [--tracks sortie,duel]
      [--jobs 4] [--no-bots]
  python scripts/same_behavior.py selftest --base <根> --tmp <暫存資料夾> [--tracks ...]   同一份跑兩次一樣、前半＋後半＝整段、改一個字抓得到
  python scripts/same_behavior.py run <根> <設定> <輸出檔> --tmp <暫存資料夾> [--track sortie|duel] [--part all|first|second] [--db <資料庫檔>]
  python scripts/same_behavior.py bots <根> <設定> <輸出檔> --tmp <暫存資料夾> [--seats sortie|duel]

設定：none（不帶）、weekend、season21、week7，與 test（tests/fixtures/content，測試內容）。

固定的那幾層（不固定的話同一份程式跑兩次就不一樣，比對本身不穩）：
- 亂數：伺服器每個請求都 Game(CONTENT, state) 不傳 rng（engine 的 `self.rng = rng or random.Random()`）——這裡把
  random.Random.__init__ 換成「沒給種子就用 12345 + 7919 × 步數」，Game 的預設 rng、各處沒給種子的 Random() 都是這一顆；每個請求之前
  random.seed(步數)（模組層的 random.random()），並清空 server.GAMES（每個請求重建 Game，等於每一下之間重開伺服器：
  前半＋後半跟整段才比得了）。
- 時間：time.time 換成「CLOCK0 + 步數 × 60 秒、同一個請求裡每叫一次 +0.5 秒」；server._monotonic（鎖內模型的斷路器、大場面判讀
  與取名的預算）讀同一顆鐘、讀的時候不往前推（不然機器慢的那一次預算先用完、斷路器開得久，結果跟著牆上的時間變）。
- 模型：OllamaClient.from_config 照原樣建好之後換成不連網路的 client（chat_* 立刻丟連線錯誤、warm 什麼都不做；絕不打 11434）。
  大場面判讀那一步換成回固定判讀的（Judgment(advantage=8)），act:train 走 server.may_judge_fight → prepare_fight 那一條。
- 資料庫轉成文字：每一張表、每一列（列照 repr 排序：列的先後不是行為）；帳號的 salt、hash 抹掉（每次隨機）。

半舊半新（批次表「舊程式寫到一半、新程式接手」）：--part first 跑完那一軌的 PHASES_FIRST 停（存下步數），--part second 開同一個
資料庫接著跑 PHASES_SECOND。compare 比「base 整段」＝「base 前半＋head 後半」；selftest 比「base 整段」＝「base 前半＋base 後半」。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import io
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

PROFILES = ("none", "weekend", "season21", "week7", "test")
TRACK_NAMES = ("sortie", "duel")  # 第 1 批的一軌（出陣：Scenario）、第 2 批的一軌（出陣約戰：DuelScenario）；各自一個資料庫、各自切一半
BOT_PROFILES = ("weekend", "week7")
DUEL_BOT_PROFILES = ("season21", "week7")  # 約戰的假人（推現實時鐘的整季機器人、BotRunner 兩軍各 4 個）：約戰開著的兩種
DUEL_PROFILES = ("season21", "week7")  # 減法季開著、出陣換成約戰的季：先照原樣（約戰）走一段，攻守混戰那幾段把約戰關掉走
CLOCK0 = 1792900800.0  # 2026-10-25 08:00 UTC（台灣 16:00）
STEP_SECONDS = 60.0
ADMIN = "掌門"
# selftest 故意改的一個字：每一軌一句（舊名的檔、搬進包的檔兩處找），在 MUTANT_PROFILE 那一種設定跑
MUTATIONS = {
    "sortie": (("tianxia/features/sortie/rules.py", "tianxia/sortie.py"), ("這一下沒推動。", "這一下沒推動！")),  # 出陣回報打輸那一句
    "duel": (("tianxia/features/sortie/duel_rules.py", "tianxia/sortie_duel.py"),
             ('WHY_JOINED = "已經同去了"', 'WHY_JOINED = "已經同去了！"')),  # 同去按第二次那一句
}
MUTANT_PROFILE = {"sortie": "weekend", "duel": "week7"}


# ═══════════════════════════ 調度（compare、selftest） ═══════════════════════════


def _child(args: list[str], log: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
    with log.open("w", encoding="utf-8") as fh:
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), *args], env=env, stdout=fh, stderr=subprocess.STDOUT)
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
    """（seats, 設定）：出陣那一軌的假人（整季機器人＋BotRunner 四個）跑 BOT_PROFILES，約戰那一軌的（推現實時鐘的整季機器人＋BotRunner 兩軍
    各 4 個）跑 DUEL_BOT_PROFILES。"""
    out = [("sortie", p) for p in BOT_PROFILES] if "sortie" in tracks else []
    return out + ([("duel", p) for p in DUEL_BOT_PROFILES] if "duel" in tracks else [])


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
        for seats, p in _bot_runs(tracks):
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
    for seats, p in _bot_runs(tracks):
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
    here = str(Path(__file__).resolve().parent)
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

    def from_config(cls, cfg):
        client = real_from_config(cls, cfg)
        client.__class__ = JudgeClient if MODEL["judge"] else DeadClient
        return client

    ollama_client.OllamaClient.from_config = classmethod(from_config)


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


# ═══════════════════════════ 子行程：TestClient 情境 ═══════════════════════════


class Scenario:
    """一種設定的整段情境。每一段（PHASES 的一個名字）是一個方法；段落結束寫資料庫的雜湊，最後寫整份資料庫。"""

    def __init__(self, root: Path, profile: str, db: Path):
        self.root, self.profile, self.db = root, profile, db
        import server

        server._monotonic = _fake_monotonic  # 斷路器與模型預算的時鐘（server 每次叫都讀模組層的 _monotonic）
        # 審查 S-10（develop 6d926c17 起）：同一個來源 IP 一小時最多註冊 5 個帳號；TestClient 全是同一個來源，不放開的話第 6 個人起註冊不了
        server.REGISTER_LIMIT = 10 ** 6
        if profile == "test":
            from tianxia.content import load_content

            server.CONTENT = load_content(root / "tests" / "fixtures" / "content")
        self.server = server
        self.c = server.CONTENT
        from fastapi.testclient import TestClient

        from tianxia.characters import CharacterStore
        from tianxia.sqlite_world import open_world

        self.TestClient = TestClient
        self.world = open_world()
        self.chars = CharacterStore(self.world.db)
        self.clients: dict[str, object] = {}
        self.passwords: dict[str, str] = {}
        self.duel_default = self.c.config.jianfa.sortie_duel if hasattr(self.c.config, "jianfa") else None
        self.big_default = self.c.config.big_fight_difficulty

    # ── 打 API ──

    def begin(self) -> None:
        STEP[0] += 1
        CLOCK[0] = CLOCK0 + STEP[0] * STEP_SECONDS
        random.seed(STEP[0])
        self.server.GAMES.clear()  # 每個請求重建 Game（rng 只看資料庫與這一步）

    def call(self, who: str, method: str, url: str, body: dict | None = None):
        self.begin()
        client = self.clients[who]
        r = client.post(url, json=body if body is not None else {}) if method == "POST" else client.get(url)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = r.text[:300]
        emit(f"{who} {method} {url} {json.dumps(body, ensure_ascii=False) if body else ''} {r.status_code}", data)
        return r.status_code, data

    def main(self, who: str):
        return self.call(who, "GET", "/api/main")[1]

    def choose(self, who: str, option_id: str):
        return self.call(who, "POST", "/api/choose", {"id": option_id})[1]

    def do(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/do/{op}", body or {})[1]

    @staticmethod
    def ids(view) -> dict[str, dict]:
        main = view.get("main", view) if isinstance(view, dict) else {}
        return {o["id"]: o for o in main.get("options", [])} if isinstance(main, dict) else {}

    def settle_choices(self, who: str, rounds: int = 6) -> None:
        """待選的事件（開局三選一、投靠之後的入伍）：照第一個選項選掉。"""
        for _ in range(rounds):
            first = [i for i, o in self.ids(self.main(who)).items() if i.startswith("choice:") and o.get("enabled")]
            if not first:
                return
            self.choose(who, first[0])

    # ── 擺局面（直接改資料庫；伺服器每次進鎖重讀） ──

    def edit(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state.player)
            self.chars.save(state)

    def place(self, name: str, loc: str | None, faction: str | None = "keep") -> bool:
        if loc is not None and loc not in self.c.locations:
            fallback = sorted(i for i, x in self.c.locations.items() if x.enemies)  # 測試內容沒有正式的地點：換一處遊歷打得到人的
            emit(f"{name} → {loc}（這份內容沒有這個地點）→ {fallback[0] if fallback else '略過'}", None)
            if not fallback:
                return False
            loc = fallback[0]

        def fn(p):
            if loc is not None:
                p.location, p.journey = loc, None
                p.visited.add(loc)
            if faction != "keep":
                p.faction = faction
            p.stamina = float(self.c.config.stamina_max)
            p.joined_at = -1.0e9  # 過了新手期（截殺與混戰的保護）
        self.edit(name, fn)
        return True

    def set_duel(self, on: bool) -> None:
        if self.profile in DUEL_PROFILES:
            self.c.config.jianfa.sortie_duel = on and self.duel_default

    def contested(self, *locs: str) -> bool:
        """這份內容有地盤、這幾處都是區塊（出陣開著的季才走得到出陣那幾段；none、test 沒有地盤）。"""
        from tianxia import conquest, territory

        return territory.on(self.c) and all(loc in conquest.blocks(self.c) for loc in locs)

    def preset_bar(self, loc: str, side: str, value: float, by: str) -> None:
        """把這一塊 side 那一條進度直接擺到 value（推的人記 by；到過警報線就記警報，同 conquest.push）：只靠出陣推，十幾步推不到那麼高。"""
        from tianxia import conquest
        from tianxia.state import Bar, BlockFight

        def fn(s) -> None:
            if s.conquest is None:
                conquest.update(s, self.c)
            fight = s.conquest.fights.setdefault(loc, BlockFight())
            fight.bars[side] = Bar(value=value, pushers={by: value})
            fight.alarm = fight.alarm or value >= self.c.config.conquest.alarm_at

        self.world.mutate_season(fn)
        emit(f"擺進度 {loc} {side} {value}", None)

    @contextlib.contextmanager
    def winning(self):
        """這一下的仗照寫好的打贏：team.fight 帶 tier（同序章雪恥那一場：威力、難度、亂數照算，判定出來之後只把結果換成大勝）。
        要的是打贏之後出陣包那幾支（推滿易手、截糧打贏、一類一顆之前的三成），本人練到頂也只是「難分勝負」。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None:
                kwargs["tier"] = "大勝"
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    def relogin(self, who: str) -> None:
        """重新登入一個帳號（後半是新的行程，記憶體裡的工作階段都不在了；整段也照樣登入，兩邊的步數才對得上）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.call(who, "POST", "/api/login", {"login": self.login_of(who), "password": self.passwords[who]})

    def login_all(self) -> None:
        """重新登入每一個帳號（前半＋後半在這裡接）。"""
        for who in list(self.clients):
            self.relogin(who)

    @staticmethod
    def login_of(who: str) -> str:
        return "zhangmen" if who == ADMIN else "u" + hashlib.sha256(who.encode()).hexdigest()[:10]

    def phase_end(self, name: str) -> None:
        emit(f"段落 {name} 資料庫", hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

    # ── 情境 ──

    PLAYERS = {  # 名號：陣營（None＝散人；序章那一位另外）
        "沈浪": "guan", "李尋歡": "guan", "傅紅雪": "guan", "蕭十一郎": "guan",
        "楚留香": "huang", "陸小鳳": "huang", "花滿樓": "huang", "西門吹雪": "huang",
    }
    NEWBIE = "新人"
    CLASHES = [  # （黃巾先出陣的人, 官軍撞上去的人, 地點）：每一對只撞一次（冷卻、護身）
        ("陸小鳳", "李尋歡", "nanyang_road"), ("花滿樓", "傅紅雪", "nanyang_wilds"),
        ("西門吹雪", "蕭十一郎", "yu_river"), ("楚留香", "沈浪", "lulin_zhai"),
    ]
    NEWCOMER = ("韓青川", "huang")  # pull_mark 才來的黃巾：守時撞上的混戰要一個沒被撞過（沒有護身、沒有這一對的冷卻）的人
    # pull_mark、pull、host、flip、drill 是審查之後加的（dev/sortie-1 審查：守把對面拉下來、守時的混戰、推滿易手、截糧打贏、
    # 一類一顆之前的三成原本都沒走到）。前半切在 pull_mark 之後（審查：原本切點跨過去的只有今天的次數）：涿郡黃巾那一條是 90、
    # 韓青川剛在那裡攻過（混戰的窗口開著、還沒被撞），後半第一件事就是官軍在那裡守、撞上他——正式上線就是這種舊程式寫到一半的局面。
    PHASES_FIRST = ["setup", "prologue", "ranger", "join", "duel_on", "out_of_contest", "attack", "hold", "clash", "pull_mark"]
    PHASES_SECOND = ["pull", "resume", "used_up", "win", "host", "flip", "convoy", "drill", "judge", "season"]

    def setup(self) -> None:
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        self.do(ADMIN, "open_season")
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)

    def prologue(self) -> None:
        """序章走到雪恥（出陣開著時 act:train 叫雪恥、不算出陣次數；關著叫遊歷）：照 tests/season/test_real_content._walk_the_hut 的步驟，全走 API。"""
        from tianxia import sensing

        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)  # season21、week7 開局是開局第一分鐘（opening），測試內容沒有序章
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.call(who, "POST", "/api/menxia/slot", {"art": "jichu_quanjiao", "insight": got[0]})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/forge", {"insights": [got[0], f"{got[0]}~2"]})
        self.do(who, "pill")
        view = self.main(who)
        emit("序章的 act:train", self.ids(view).get("act:train"))
        self.choose(who, "act:train")

    def ranger(self) -> None:
        """散人站在區塊上：出陣灰著寫「散人不能出陣」、底下那一行寫原因（出陣關著的季照舊是遊歷）。"""
        if self.place("沈浪", "runan_wilds"):
            view = self.main("沈浪")
            emit("散人的 act:train", self.ids(view).get("act:train"))
            emit("散人那一行", (view.get("action_notes") or {}).get("act:train"))
        if "act:train" in self.ids(self.main("沈浪")) and self.ids(self.main("沈浪"))["act:train"].get("enabled"):
            self.choose("沈浪", "act:train")  # 出陣關著的季：遊歷

    def join(self) -> None:
        factions = {f.id: f for f in self.c.scenario.factions}
        for who, side in self.PLAYERS.items():
            if side not in factions or not factions[side].join_at:
                continue
            if not self.place(who, factions[side].join_at[0]):
                continue
            self.choose(who, f"faction:{side}")
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, None)  # 體力補滿、過了新手期

    def duel_on(self) -> None:
        """約戰開著的季（season21、week7）照原樣：按出陣只打開出陣前那張卡（不寫紀錄）；截糧的運糧隊經過照舊攻打（_squad_encounter；
        這一場傅紅雪打輸，截糧打贏在 convoy）。"""
        if self.profile not in DUEL_PROFILES:
            return
        self.set_duel(True)
        if self.place("李尋歡", "runan_wilds"):
            view = self.main("李尋歡")
            emit("約戰的 act:train", self.ids(view).get("act:train"))
            self.choose("李尋歡", "act:train")
        self.intercept("guan", "yanshan_foot")
        if self.place("傅紅雪", "yanshan_foot"):
            view = self.main("傅紅雪")
            emit("約戰開著、截糧的 act:train", self.ids(view).get("act:train"))
            self.choose("傅紅雪", "act:train")
        self.clear_orders()
        for who in ("李尋歡", "傅紅雪"):
            self.place(who, None)

    def out_of_contest(self) -> None:
        self.set_duel(False)
        if self.place("沈浪", "huangjin_camp"):
            view = self.main("沈浪")
            emit("別人大本營的 act:train", self.ids(view).get("act:train"))
            emit("別人大本營那一行", (view.get("action_notes") or {}).get("act:train"))

    def attack(self) -> None:
        """中立地攻：鈕上寫對手與勝算、必敗先問（confirm）；打完的出陣回報（main.front）。"""
        self.set_duel(False)
        for loc in ("runan_wilds", "hilltop_wilds"):
            if self.place("沈浪", loc):
                view = self.main("沈浪")
                emit(f"{loc} 的 act:train", self.ids(view).get("act:train"))
                emit(f"{loc} 那一行", (view.get("action_notes") or {}).get("act:train"))
                out = self.choose("沈浪", "act:train")
                emit(f"{loc} 出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def hold(self) -> None:
        """自家地守：黃巾先在官軍的涿郡攻一下，官軍守（零風險）。楚留香這一下推不動（進度照舊 0），守的回報是「對面的進度都已歸零」
        （推不動、不撞混戰）；把對面拉下來與守時撞上混戰在 pull_mark／pull。"""
        self.set_duel(False)
        if self.place("楚留香", "zhuo_county"):
            self.choose("楚留香", "act:train")
        if self.place("沈浪", "zhuo_county"):
            view = self.main("沈浪")
            emit("自家地的 act:train", self.ids(view).get("act:train"))
            out = self.choose("沈浪", "act:train")
            emit("守的出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def clash(self) -> None:
        """混戰：黃巾先在那一塊出陣，官軍 clash_minutes 內跟著出陣就撞上（贏、輸、平各一次以上）。"""
        self.set_duel(False)
        for theirs, ours, loc in self.CLASHES:
            if not (self.place(theirs, loc) and self.place(ours, loc)):
                continue
            self.choose(theirs, "act:train")
            out = self.choose(ours, "act:train")
            main = out.get("main") if isinstance(out, dict) else None
            latest = (main or {}).get("latest")
            emit(f"混戰 {ours}→{theirs}", {"latest": latest, "front": (main or {}).get("front")})
            self.main(theirs)  # 被撞的那一方的紀錄

    def resume(self) -> None:
        # 記憶體裡的設定也要接上前半最後那一段（混戰：約戰關著）：後半是新的行程，CONTENT 是剛載入的（selftest 抓到過：
        # 沒接上的話 season21、week7 的江湖畫面多一個 sorties 鍵）
        self.set_duel(False)
        self.login_all()

    def used_up(self) -> None:
        """用完今天的次數：灰著寫「今日已出陣 N 次」、底下那一行補句號。"""
        self.set_duel(False)
        if not self.place("沈浪", "hilltop_wilds"):
            return
        for _ in range(8):
            option = self.ids(self.main("沈浪")).get("act:train")
            if not option or not option.get("enabled"):
                break
            self.place("沈浪", None)
            self.choose("沈浪", "act:train")
        view = self.main("沈浪")
        emit("用完的 act:train", self.ids(view).get("act:train"))
        emit("用完那一行", (view.get("action_notes") or {}).get("act:train"))

    def win(self) -> None:
        """打得贏的出陣（本人的武學、內功練到第九成）：攻推得動進度（出陣回報畫進度條）、拿戰利與經驗；楚留香在官軍的涿郡攻兩下，
        官軍守（守拿自家那一路的數字）。楚留香在涿郡打不贏，那一條照舊是 0，守的回報是「都已歸零」；拉下來在 pull。"""
        self.set_duel(False)
        for who in ("蕭十一郎", "楚留香"):
            self.edit(who, lambda p: (setattr(p.member, "wugong_level", 9), setattr(p.member, "neigong_level", 9)))
        for who, loc, times in (("蕭十一郎", "hilltop_wilds", 2), ("蕭十一郎", "lulin_zhai", 1), ("楚留香", "zhuo_county", 2),
                                ("李尋歡", "zhuo_county", 1)):
            for _ in range(times):
                if not self.place(who, loc):
                    break
                view = self.main(who)
                emit(f"{who} 在 {loc} 的 act:train", self.ids(view).get("act:train"))
                out = self.choose(who, "act:train")
                emit(f"{who} 在 {loc} 的出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def front(self, tag: str, out) -> None:
        main = out.get("main") if isinstance(out, dict) else None
        emit(tag, {"latest": (main or {}).get("latest"), "front": (main or {}).get("front")})

    def newcomer(self, who: str, side: str) -> bool:
        """後來才進江湖的一位：註冊、建角色、略過引導、投靠（同 setup、join），過了新手期。"""
        factions = {f.id: f for f in self.c.scenario.factions}
        if side not in factions or not factions[side].join_at:
            return False
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        self.do(who, "skip_tutorial")
        self.settle_choices(who)
        if not self.place(who, factions[side].join_at[0]):
            return False
        self.choose(who, f"faction:{side}")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        return self.place(who, None)

    def pull_mark(self) -> None:
        """守把對面拉下來的前半：官軍的涿郡，黃巾那一條擺到 90（十幾步推不到那麼高），新來的黃巾韓青川在那裡攻一下——推得動，
        記下他此刻在這一塊出陣過（混戰的對象；打輸也記一筆 0）。"""
        self.set_duel(False)
        if not self.contested("zhuo_county"):
            return
        who, side = self.NEWCOMER
        if not self.newcomer(who, side):
            return
        self.preset_bar("zhuo_county", side, 90.0, who)
        if self.place(who, "zhuo_county"):
            emit(f"{who} 在涿郡的 act:train", self.ids(self.main(who)).get("act:train"))
            self.front(f"{who} 在涿郡攻", self.choose(who, "act:train"))

    def pull(self) -> None:
        """守時撞上混戰、守把對面拉下來：傅紅雪在涿郡守（黃巾那一條 > 0，推得動）撞上 clash_minutes 內攻過的韓青川；李尋歡接著守
        （韓青川剛被撞過、有護身，不再撞）——兩下的回報都是「黃巾軍的進度被拉到 N／100」（撞輸的那一下白跑、照舊 90）。
        這是後半的第一段：混戰的窗口只有 clash_minutes（10 分＝10 步），所以先只登入這兩位、馬上守，其餘的人等 resume 再登入。"""
        self.set_duel(False)
        if not self.contested("zhuo_county"):
            return
        for who in ("傅紅雪", "李尋歡"):
            self.relogin(who)
        for who in ("傅紅雪", "李尋歡"):
            if self.place(who, "zhuo_county"):
                emit(f"{who} 守涿郡的 act:train", self.ids(self.main(who)).get("act:train"))
                self.front(f"{who} 守涿郡", self.choose(who, "act:train"))

    def host(self) -> None:
        """守拿自家那一路的數字（_sortie_host）：涿郡沒有駐著官軍那一路，前面的守都不拿；黃巾的大本營（不在爭奪之列、推不動）
        守照拿——黃巾渠帥那一路，一類一顆開著全額（hold_share 1.0）。"""
        self.set_duel(False)
        if not self.contested("huangjin_camp"):
            return
        if self.place("西門吹雪", "huangjin_camp"):
            emit("大本營守的 act:train", self.ids(self.main("西門吹雪")).get("act:train"))
            self.front("大本營守", self.choose("西門吹雪", "act:train"))

    def flip(self) -> None:
        """推滿易手：荒丘（中立）官軍那一條擺到 99，蕭十一郎這一下打贏（winning）就推滿——「被你這一下推滿，落入官軍之手」、
        小籤「易手・這一下是你推滿的」、易手的分紅。"""
        self.set_duel(False)
        if not self.contested("hilltop_wilds"):
            return
        self.preset_bar("hilltop_wilds", "guan", 99.0, "蕭十一郎")
        if self.place("蕭十一郎", "hilltop_wilds"):
            emit("推滿那一下的 act:train", self.ids(self.main("蕭十一郎")).get("act:train"))
            with self.winning():
                self.front("推滿那一下", self.choose("蕭十一郎", "act:train"))

    def drill(self) -> None:
        """一類一顆之前（precise_actions 關著，test_sortie.py 也這樣測）：攻打贏照操練拿對手三成（sortie_drill；銀兩是 sortie_silver_share），
        守在自家大本營拿 _sortie_host 那一路的三成（hold_share 是 None）。記憶體裡關掉、做完開回來（同 set_duel）。"""
        self.set_duel(False)
        if not self.contested("nanyang_wilds", "huangjin_camp"):
            return
        cfg = self.c.config
        before, cfg.precise_actions = cfg.precise_actions, False
        try:
            if self.place("花滿樓", "nanyang_wilds"):
                emit("三成的攻 act:train", self.ids(self.main("花滿樓")).get("act:train"))
                with self.winning():
                    self.front("三成的攻", self.choose("花滿樓", "act:train"))
            if self.place("陸小鳳", "huangjin_camp"):
                emit("三成的守 act:train", self.ids(self.main("陸小鳳")).get("act:train"))
                self.front("三成的守", self.choose("陸小鳳", "act:train"))
        finally:
            cfg.precise_actions = before

    def intercept(self, side: str, loc: str) -> None:
        from tianxia import orders, territory
        from tianxia.engine import Game
        from tianxia.state import Order

        if loc not in self.c.locations or not territory.on(self.c):
            return
        shell = Game.for_world(self.c, self.world)
        week = orders.period_of(shell.state, self.c)
        front = territory.line_of(self.c, loc)
        self.world.mutate_season(lambda s: (s.orders.clear(), s.orders.append(Order(
            id=f"sb:{side}:intercept", template="intercept", faction=side, week=week, front=front, location=loc, quota=99,
            text="（對照）"))))

    def clear_orders(self) -> None:
        self.world.mutate_season(lambda s: s.orders.clear())

    def convoy(self) -> None:
        """截糧的運糧隊經過自家的區塊：出陣就是去截它。第一下照打（李尋歡打不過，落敗）；第二下打贏（winning：截糧打贏、出陣的獎勵、
        軍令記功）。"""
        self.set_duel(False)
        self.intercept("guan", "yanshan_foot")
        if self.place("李尋歡", "yanshan_foot"):
            view = self.main("李尋歡")
            emit("截糧的 act:train", self.ids(view).get("act:train"))
            emit("截糧那一行", (view.get("action_notes") or {}).get("act:train"))
            self.choose("李尋歡", "act:train")
            if self.contested("yanshan_foot") and self.place("李尋歡", None):
                with self.winning():
                    self.front("截糧打贏", self.choose("李尋歡", "act:train"))
        self.clear_orders()

    def judge(self) -> None:
        """大場面判讀：難度門檻調低、模型換成回固定判讀的，act:train 走 server.may_judge_fight → prepare_fight（鎖外判讀、鎖內套用）。"""
        self.set_duel(False)
        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            if self.place("傅紅雪", "hilltop_wilds"):
                view = self.main("傅紅雪")
                emit("大場面的 act:train", self.ids(view).get("act:train"))
                self.choose("傅紅雪", "act:train")
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def season(self) -> None:
        """收季、開下一季：sortie_day、sorties_today 照帶（換季不能多出一輪陣），不看地盤開不開（dev/sortie-1 審查）——
        地盤關著的設定（none、test）這兩格本來沒人動，先擺成「今天出陣過 3 次」；接著再換一季、換季前把第一季規則關掉
        （休季換設定：地盤從開變關），照樣照帶。"""
        from tianxia import territory

        self.set_duel(self.duel_default is not None)
        if not territory.on(self.c):
            self.edit("沈浪", lambda p: (setattr(p, "sortie_day", int(CLOCK0 // 86400)), setattr(p, "sorties_today", 3)))
        self.do(ADMIN, "end_season")
        self.main("沈浪")
        self.do(ADMIN, "next_season")
        view = self.main("沈浪")
        emit("換季之後的 act:train", self.ids(view).get("act:train"))
        p = self.chars.load("沈浪").player
        emit("換季之後的次數", {"sortie_day": p.sortie_day, "sorties_today": p.sorties_today})
        self.main(self.NEWBIE)
        cfg = self.c.config
        self.do(ADMIN, "end_season")
        before, cfg.season_one = cfg.season_one, False
        try:
            self.do(ADMIN, "next_season")
            view = self.main("沈浪")
            emit("地盤關掉再換季之後的 act:train", self.ids(view).get("act:train"))
            p = self.chars.load("沈浪").player
            emit("地盤關掉再換季之後的次數", {"sortie_day": p.sortie_day, "sorties_today": p.sorties_today})
        finally:
            cfg.season_one = before

    def run(self, part: str, out: Path) -> None:
        state_file = Path(str(self.db) + ".state.json")
        if part == "second":
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            STEP[0], self.passwords = saved["step"], saved["passwords"]
            self.clients = {who: None for who in saved["clients"]}
            phases = self.PHASES_SECOND
        else:
            phases = self.PHASES_FIRST + (self.PHASES_SECOND if part == "all" else [])
        if part != "second":
            emit(f"設定 {self.profile}", None)  # 後半不寫：前半＋後半要跟整段一個位元組都不差
        for name in phases:
            getattr(self, name)()
            self.phase_end(name)
        if part == "first":
            state_file.write_text(json.dumps({"step": STEP[0], "passwords": self.passwords, "clients": list(self.clients)},
                                             ensure_ascii=False), encoding="utf-8")
        else:
            BUF.write("## 資料庫\n" + db_text(self.db))
        out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
        print(self.profile, part, STEP[0], "步", len(BUF.getvalue()), "字")


class DuelScenario(Scenario):
    """出陣約戰（主動搬六包第 2 批；--track duel，自己一個資料庫）。照調查 survey_duel.json behavior_check 的十一步：
    /api/main 的 sortie_card、sorties 與 act:train 那一格；按 act:train 只回 PICK、不寫紀錄；sortie_go 封三招；對面看 can_answer 與
    duel:open、duel:answered 通知；sortie_answer、sortie_join（也走 /api/choose 的 sortie:* 那一條）；拒絕的路（散人貼、次數用完、應自己的、
    三招不對、散人應、別區、在路上、同一邊應戰、冷卻、不認得的動詞、已有人應戰、你已應戰、已經同去、不是同袍同去、同去的次數、在路上同去、
    在路上貼、暫停中）；
    時鐘推過窗分三條路結算——下一個人的 sync（D0、D4、D6）、沒有玩家的 world_tick（server.world_step：D1、D2、D5）、管理者快轉的
    Game.advance（D7：/api/do/fast_forward 先 sync，經 API 走不到 advance 裡那一處，這裡照 server 的做法拿鎖、只叫 advance）；
    沒人應戰時假人補位（D0）、連假人都沒有由守軍迎戰（D4）；暫停時窗往後挪（D5）；快轉到季末之後還沒打的作廢、退次數與體力（D8）；
    截糧與 /api/map/state 的 convoy；約戰開著時巡哨那一點貢獻（_duty_credit）。三回合有兩場照寫好的打（rounds，同
    tests/kit/duel_kit.rounds_go：單次判定換成給的結果、照樣用掉一次那一場的亂數）：守方贏拉回（D0）、推滿易手（D2）那兩支才走得到；
    其餘照那一場自己的亂數。
    season21、week7 約戰開著；none、weekend、test 關著，同一串 API 照打，證明關著時一個字都不變（鈕回「此刻無法這麼做」、main 沒有
    sortie_card、sorties 兩個鍵）。半舊半新切在 D6 剛貼出去、還沒人應戰的那一刻（批次表第二節；正式上線就是這種局面）：後半先只登入應戰的
    那一位、馬上應戰（窗只有 10 分＝10 步），其餘的人再登入、窗滿了結算。"""

    PLAYERS = {  # 名號：陣營（甲是官軍、乙是黃巾）
        "甲一": "guan", "甲二": "guan", "甲三": "guan", "甲四": "guan", "甲五": "guan", "甲六": "guan", "甲七": "guan", "甲八": "guan",
        "甲九": "guan",
        "乙一": "huang", "乙二": "huang", "乙三": "huang", "乙四": "huang", "乙五": "huang", "乙六": "huang", "乙七": "huang",
        "乙八": "huang",
    }
    NEWBIE = "丙一"  # Scenario.setup 註冊、不投靠的那一位：這一軌的散人
    BOT = ("假乙", "huang")  # 只有黃巾那一邊有一個假人：官軍貼的沒人應由他補位（D0），黃巾貼的連假人都沒有由守軍迎戰（D4）
    LOC, FAR = "runan_wilds", "nanyang_road"  # 汝南荒野（潁汝的中立地，兩軍開季都碰得到）、南陽官道（別區的中立地）
    MOVES = "強攻,固守,奇襲"
    PHASES_FIRST = ["setup", "join", "seat", "look", "pick", "refuse_post", "post_d0", "refuse_answer", "fill", "post_d1", "answer_d1",
                    "settle_tick", "flip", "garrison", "pause", "post_d6"]
    PHASES_SECOND = ["answer_d6", "settle_d6", "convoy", "duty", "advance_d7", "void_d8", "season"]

    # ── 小工具 ──

    def begin(self) -> None:
        """同 Scenario.begin，另外每個請求換一份空的勝算記憶（server.ODDS_MEMO）：伺服器整個行程共用那一份，前半＋後半是兩個行程，
        後半的第一下沒有前半記住的字（selftest 抓到過：weekend 的「尋敵」鈕整段寫「凶險」、後半重算寫「必敗」——同一個鍵、記住的字跟
        重算的不一樣，見回報）。出陣那一軌（第 1 批）沒碰到，照舊不換，雜湊跟第 1 批記的同一種算法。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        """時鐘推過 steps 分（不打 API；下一個請求的時鐘照步數算）。"""
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 分", None)

    def duel_of(self, attacker: str) -> str:
        """這個人最近貼的那一張約戰的 id；約戰關著的季沒有，回一個不存在的 id（照樣打 API，證明關著）。"""
        duels = sorted(self.world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
        return next((d.id for d in reversed(duels) if d.attacker.name == attacker), "s0-none")

    def duels(self, tag: str) -> None:
        """全服的約戰此刻的樣子（world.sorties，照開的先後）。"""
        rows = []
        for d in sorted(self.world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id)):
            rows.append({"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
                         "defender": None if d.defender is None else [d.defender.name, d.defender.garrison],
                         "expires_at": d.expires_at, "settled_at": d.settled_at, "tier": None if d.result is None else d.result.tier,
                         "report": d.report})
        emit(f"約戰 {tag}", rows)

    def notices(self, who: str) -> None:
        """手機通知那一串（notices.current：server 的通知看守讀同一份；duel:open、duel:answered）。"""
        from tianxia import notices

        state = self.chars.load(who)
        state.world = self.world.get_season()
        got = notices.current(state, self.c, self.world.get_battle(), self.world.sortie_duels())
        emit(f"{who} 的通知", [n.model_dump() for n in got])

    def player(self, who: str, tag: str) -> None:
        """存檔裡跟約戰有關的那幾格（次數、冷卻、體力、貢獻、內傷、紀錄幾則）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {"stamina": p.stamina, "sortie_day": p.sortie_day, "sorties_today": p.sorties_today,
                              "answer_day": p.answer_day, "answers_today": p.answers_today, "sortie_cooldown_until": p.sortie_cooldown_until,
                              "answer_cooldown_until": p.answer_cooldown_until, "duty_day": p.duty_day, "duties_today": p.duties_today,
                              "contrib": p.contrib, "injury": p.member.injury, "journal": len(state.journal), "battles": len(state.battles)})

    def post(self, who: str, moves: str | None = None) -> None:
        self.do(who, "sortie_go", {"moves": moves or self.MOVES})

    def answer(self, who: str, attacker: str, moves: str = "固守,固守,固守") -> None:
        self.do(who, "sortie_answer", {"id": self.duel_of(attacker), "moves": moves})

    def join_duel(self, who: str, attacker: str) -> None:
        self.do(who, "sortie_join", {"id": self.duel_of(attacker)})

    def tick(self, tag: str) -> None:
        """伺服器排程的一下（server.world_step：那一份沒有玩家的 Game；每一下重建，同每個請求重建 Game）。"""
        self.begin()
        self.server.WORLD_GAME = None
        msgs = self.server.world_step(time.time)
        self.server.WORLD_GAME = None
        emit(f"排程 {tag}", msgs)

    @contextlib.contextmanager
    def rounds(self, tier: str):
        """這一下結算的三回合照 tier 打（攻方的角度；同 duel_kit.rounds_go：照樣用掉一次那一場的亂數）。"""
        from tianxia import encounter

        real = encounter.resolve_encounter

        def fake(ours, theirs, rng, *a, **k):
            rng.random()
            return encounter.EncounterResult(tier=tier, margin=10.0, our_power=ours, difficulty=theirs)

        encounter.resolve_encounter = fake
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    def reports(self, *who: str) -> None:
        for name in who:
            self.call(name, "GET", "/api/reports")
            self.call(name, "GET", "/api/annals")

    def today(self) -> int:
        """此刻的回體丹那一天（Game._pill_day；台灣 00:00 換日）。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        shell.now = CLOCK[0]
        return shell._pill_day()

    # ── 情境 ──

    def seat(self) -> None:
        """補位的假人（只寫進資料庫、沒有帳號；同 bots_run 的擺法），擺在汝南荒野。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        name, side = self.BOT
        self.begin()
        with self.world.action_lock():
            g = Game.new(self.c, name, world=self.world, graduated=True)
            g.client = None
            g.sync(time.time())
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=11, faction=side, season_number=self.world.get_season_number())
            p.faction = side
            if self.LOC in self.c.locations:
                p.location, p.journey = self.LOC, None
                p.visited.add(self.LOC)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        emit(f"擺好 {name}", None)

    def look(self) -> None:
        """站在汝南荒野的兩軍與散人、站在南陽官道的黃巾：/api/main（sortie_card、sorties、act:train 那一格與底下那一行）。"""
        for who, loc in (("甲一", self.LOC), ("乙一", self.LOC), (self.NEWBIE, self.LOC), ("乙六", self.FAR)):
            if self.place(who, loc):
                view = self.main(who)
                emit(f"{who} 的 act:train", self.ids(view).get("act:train"))
                emit(f"{who} 那一行", (view.get("action_notes") or {}).get("act:train"))

    def pick(self) -> None:
        """約戰開著：按出陣那一格只打開出陣前那張卡（sortie_duel.PICK），不花體力、不寫紀錄。"""
        self.player("甲一", "按之前")
        self.choose("甲一", "act:train")
        self.player("甲一", "按了出陣那一格")

    def refuse_post(self) -> None:
        """貼不成的兩條（約戰還沒有之前）：散人貼、今天的次數用完（都不扣體力、不寫紀錄）。"""
        self.post(self.NEWBIE)
        if self.place("甲二", self.LOC):
            day = self.today()
            self.edit("甲二", lambda p: (setattr(p, "sortie_day", day), setattr(p, "sorties_today", 2)))
            self.post("甲二")
        for who in (self.NEWBIE, "甲二"):
            self.player(who, "貼不成之後")

    def post_d0(self) -> None:
        """乙五先上路（往南陽官道）；甲一在汝南荒野貼 D0；對面看得到應戰（can_answer）、手機通知「有人約戰」。"""
        self.place("乙五", self.LOC)
        self.call("乙五", "POST", "/api/travel", {"place": self.FAR, "mode": "walk"})
        self.post("甲一")
        self.duels("D0 貼了")
        self.player("甲一", "貼了 D0")
        self.main("乙一")
        self.notices("乙一")
        self.notices("甲一")

    def refuse_answer(self) -> None:
        """D0 還開著（窗 10 分＝10 步，這一段 8 下）：應戰拒絕的路——應自己的、三招不對、散人、別區、在路上、同一邊只能同去；再貼一張
        （冷卻）、不認得的動詞。都不扣次數、不扣體力、不寫紀錄。"""
        self.answer("甲一", "甲一")
        self.answer("乙一", "甲一", "強攻,強攻")
        self.answer(self.NEWBIE, "甲一")
        self.answer("乙六", "甲一")
        self.answer("乙五", "甲一")
        self.place("甲三", self.LOC)
        self.answer("甲三", "甲一")
        self.post("甲一")
        self.choose("甲一", "sortie:zzz")
        self.duels("拒絕之後")
        for who in ("甲一", "乙一", "乙五", "乙六", "甲三", self.NEWBIE):
            self.player(who, "拒絕之後")

    def fill(self) -> None:
        """D0 沒人應（官軍那一條先擺到 40）：窗滿了排程關著，下一個同步的人（站在別處的甲四）替它結算——補位的是黃巾的假人（卡上、戰報、
        行狀只寫名號），守方三回合全勝、把官軍那一條拉回。"""
        if self.contested(self.LOC):
            self.preset_bar(self.LOC, "guan", 40.0, "甲一")
        self.skip(11)
        self.place("甲四", "nanyang_wilds")
        with self.rounds("落敗"):
            self.main("甲四")
        self.duels("D0 結算了")
        self.reports("甲一")
        self.player("甲一", "D0 結算之後")
        self.player(self.BOT[0], "補位之後")
        self.main("甲一")

    def post_d1(self) -> None:
        """甲五在汝南荒野貼 D1（走 /api/choose 的 sortie:go）。"""
        if self.place("甲五", self.LOC):
            self.choose("甲五", f"sortie:go:{self.MOVES}")
        self.duels("D1 貼了")

    def answer_d1(self) -> None:
        """乙一應 D1（先到的那一位；攻方的通知「有人應了」）；乙二第二個應、乙一再應；甲三同去（走 /api/choose 的 sortie:join）、
        再按一次；乙二同去、甲二（次數用完）同去；甲六上路之後同去、貼（在路上，dev/sortie-2 審查：_duel_join_extra 在路上那一條原本沒走到）。
        D1 的窗 10 分＝10 步：同去都在貼之後第 9 步以內。"""
        self.place("乙一", self.LOC)
        self.answer("乙一", "甲五")
        self.notices("甲五")
        self.place("乙二", self.LOC)
        self.answer("乙二", "甲五")
        self.answer("乙一", "甲五")
        self.choose("甲三", f"sortie:join:{self.duel_of('甲五')}")
        self.join_duel("甲三", "甲五")
        self.join_duel("乙二", "甲五")
        self.join_duel("甲二", "甲五")
        if self.place("甲六", self.LOC):
            self.call("甲六", "POST", "/api/travel", {"place": self.FAR, "mode": "walk"})
        self.join_duel("甲六", "甲五")
        self.post("甲六")
        self.duels("D1 應了、同去了")
        for who in ("乙一", "乙二", "甲三", "甲二", "甲六"):
            self.player(who, "應戰、同去之後")

    def settle_tick(self) -> None:
        """D1 窗滿：沒有人同步，伺服器排程那一下（server.world_step）結算（照那一場自己的亂數）；兩邊與同去的各一份戰報、一則紀錄。"""
        self.skip(11)
        self.tick("D1")
        self.duels("D1 結算了")
        self.reports("甲五", "乙一", "甲三")
        for who in ("甲五", "乙一", "甲三"):
            self.player(who, "D1 結算之後")
        self.main("甲五")
        self.main("乙一")

    def flip(self) -> None:
        """D2：黃巾的乙二在南陽郊野貼（黃巾那一條擺到 99），甲四應；窗滿了排程那一下結算——攻方三回合全勝、推滿易手。"""
        if self.contested("nanyang_wilds"):
            self.preset_bar("nanyang_wilds", "huang", 99.0, "乙二")
        if self.place("乙二", "nanyang_wilds"):
            self.main("乙二")
            self.post("乙二")
        self.answer("甲四", "乙二")
        self.skip(11)
        with self.rounds("大勝"):
            self.tick("D2")
        self.duels("D2 結算了")
        self.reports("乙二", "甲四")
        self.main("乙二")
        self.main("甲四")

    def garrison(self) -> None:
        """D4：黃巾的乙三在涿郡（官軍的）貼，沒人應、官軍那一邊沒有假人：守軍迎戰；下一個同步的人結算（照那一場自己的亂數）。"""
        if self.place("乙三", "zhuo_county"):
            self.main("乙三")
            self.post("乙三")
        self.skip(11)
        self.main("甲九")
        self.duels("D4 結算了")
        self.reports("乙三")
        self.main("乙三")

    def pause(self) -> None:
        """D5：甲六在淯水河畔貼；管理者暫停賽季時鐘（暫停中應戰、貼約戰回「賽季暫停中」），停到 D5 的窗原本該滿了之後——暫停中到時的不結算：
        排程那一下、一個人的同步都不收（dev/sortie-2 審查：原本只停 5 分，暫停中沒有一張到時）；再停 5 分，繼續之後窗往後挪停的長度；
        乙四應（走 /api/choose 的 sortie:answer），窗滿了排程結算。"""
        if self.place("甲六", "yu_river"):
            self.post("甲六")
        self.duels("D5 貼了")
        self.do(ADMIN, "pause_clock")
        self.place("乙四", "yu_river")
        self.answer("乙四", "甲六")
        self.post("甲七")
        self.skip(11)  # D5 的窗（10 分）在暫停中滿了
        self.tick("暫停中")
        self.main("乙四")
        self.duels("暫停中到時")
        self.skip(5)
        self.do(ADMIN, "resume_clock")
        self.duels("繼續之後")
        self.main("乙四")
        self.choose("乙四", f"sortie:answer:{self.duel_of('甲六')}:奇襲,強攻,固守")
        self.skip(11)
        self.tick("D5")
        self.duels("D5 結算了")
        self.reports("甲六", "乙四")

    def post_d6(self) -> None:
        """前半的最後一下：甲七在綠林山寨貼 D6、還沒人應戰（半舊半新切在這裡）。"""
        if self.place("甲七", "lulin_zhai"):
            self.main("甲七")
            self.post("甲七")
        self.duels("D6 貼了")

    def answer_d6(self) -> None:
        """後半的第一段：只先登入乙七、站到綠林山寨、馬上應 D6（新程式應舊程式貼的那一張；整段也照樣在這裡登入，步數才對得上）；
        其餘的人再登入。"""
        self.relogin("乙七")
        self.place("乙七", "lulin_zhai")
        self.answer("乙七", "甲七", "奇襲,奇襲,撤退")
        self.duels("D6 應了")
        self.login_all()

    def settle_d6(self) -> None:
        """D6 窗滿：下一個同步的人結算（新程式結算舊程式貼、新程式應的那一張）。"""
        self.skip(11)
        self.main("甲七")
        self.duels("D6 結算了")
        self.reports("甲七", "乙七")
        self.main("乙七")

    def convoy(self) -> None:
        """約戰開著、截糧的運糧隊經過自家的燕山腳：出陣那一格是「出陣・截糧」、照舊打運糧隊；輿圖的疊層那一處帶 convoy。"""
        self.intercept("guan", "yanshan_foot")
        if self.place("甲九", "yanshan_foot"):
            view = self.main("甲九")
            emit("截糧的 act:train", self.ids(view).get("act:train"))
            emit("截糧那一行", (view.get("action_notes") or {}).get("act:train"))
            self.call("甲九", "GET", "/api/map/state")
            self.choose("甲九", "act:train")
            self.player("甲九", "截糧之後")
        self.clear_orders()

    def duty(self) -> None:
        """約戰開著：巡哨（act:duty）收進此地、不佔出陣的次數，一天第一次記一點貢獻（_duty_credit）；第二次不記。"""
        if self.place("甲九", "zhuo_county"):
            view = self.main("甲九")
            emit("守勢的 act:duty", self.ids(view).get("act:duty"))
            for _ in range(2):
                self.place("甲九", None)
                if (self.ids(self.main("甲九")).get("act:duty") or {}).get("enabled"):
                    self.choose("甲九", "act:duty")
            self.player("甲九", "巡哨之後")

    def advance_d7(self) -> None:
        """D7：甲八在白馬津貼、乙八應；窗滿了，管理者快轉那一條（Game.advance）結算。/api/do/fast_forward 先 sync（窗滿了的在 sync 就結算掉），
        經 API 走不到 advance 裡那一處；整季機器人（bot.play_season）只 advance、不 sync，走的就是它——這裡照 server 的做法拿鎖、重讀管理者，
        只叫 advance（不 sync），再存回。"""
        for who in ("甲八", "乙八"):
            self.place(who, "baima_ford")
        self.post("甲八")
        self.answer("乙八", "甲八")
        self.skip(11)
        self.begin()
        game = self.server.game_for(ADMIN)
        with self.server._locked(game):
            game.now = time.time()
            msgs = game.advance(60)
            self.server.open_characters().save(game.state)
        self.server.GAMES.clear()
        emit("管理者快轉（只 advance）D7", msgs)
        self.duels("D7 結算了")
        self.reports("甲八", "乙八")
        for who in ("甲八", "乙八"):
            self.player(who, "D7 結算之後")

    def void_d8(self) -> None:
        """D8：甲九在拒馬河畔貼、乙五應；管理者快轉到季末（/api/do/fast_forward：季收了），下一個同步的人（攻方自己）替還沒打的那一張作廢——
        攻方退一次出陣（同一天才退）與體力、應戰的人退一次應戰與體力，冷卻不退。"""
        for who in ("甲九", "乙五"):
            self.place(who, "juma_river")
            # 體力擺到一半：滿的話退回來的那一下被上限與之後的回體力蓋掉，退多退少都看不出來（突變「攻方少退 1 點」抓不到過）
            self.edit(who, lambda p: setattr(p, "stamina", 100.0))
        self.post("甲九")
        self.answer("乙五", "甲九")
        for who in ("甲九", "乙五"):
            self.player(who, "D8 之前")
        self.do(ADMIN, "fast_forward", {"hours": 24 * 60})
        self.duels("快轉到季末之後")
        self.main("甲九")
        self.duels("D8 作廢了")
        for who in ("甲九", "乙五"):
            self.player(who, "作廢之後")
        self.main("乙五")

    def season(self) -> None:
        """開下一季（快轉已經收了季）：約戰清掉（sqlite_world 換季）、新的一季沒有卡。"""
        self.do(ADMIN, "next_season")
        self.duels("下一季")
        self.main("甲一")
        self.main("乙一")


TRACKS = {"sortie": Scenario, "duel": DuelScenario}  # 第 1 批的一軌（出陣）、第 2 批的一軌（約戰）：各自一個資料庫、各自切一半


# ═══════════════════════════ 子行程：假人 ═══════════════════════════


def bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """整季機器人（bot.play_season，種子 3）與伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(7)、假時鐘）各跑 N 輪：
    寫存檔、世界與資料庫的雜湊、各種紀錄標題的次數（看得出出陣那幾段有沒有走到）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title for s in states for e in s.journal).items()))

    content = load_content(root / "content", profile=profile)
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("整季機器人 紀錄標題", titles([game.state]))
    # 約戰開著的季（week7）它貼過一張（bot.pick 最後那一行的 duel_go）：紀錄只留最近 30 則（journal.MAX_ENTRIES）、標題裡看不到，這裡寫出來。
    # 現實時刻一直是開季那一刻（play_season 不動 game.now），那一張永遠不到時；只 advance 的結算在 duel_bots_run 那一段（推現實時鐘）
    emit("整季機器人 約戰", _duel_rows(world))
    emit("整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("假甲", "guan", "hilltop_wilds"), ("假乙", "guan", "runan_wilds"), ("假丙", "huang", "runan_wilds"),
             ("假丁", "huang", "nanyang_road")]
    for i, (name, side, loc) in enumerate(seats):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=11 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    emit("假人程式 一輪一輪", dict(sorted(totals.items())))
    emit("假人程式 紀錄標題", titles(states))
    emit("假人程式 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("假人程式 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "假人", dict(totals))


def _duel_rows(world) -> list[dict]:
    """world.sorties 的每一張（照開的先後）：誰貼、誰應、同去幾人、補位還是守軍、結果、什麼時候結算。"""
    duels = sorted(world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
    return [{"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
             "defender": None if d.defender is None else [d.defender.name, d.defender.garrison], "filled": bool(d.report.get("filled")),
             "tier": None if d.result is None else d.result.tier, "settled_at": d.settled_at} for d in duels]


DUEL_SEATS = [  # 約戰（第 2 批）：兩軍各 4 個，擺在兩軍都約得到的區塊與它們的大區裡（汝南荒野、南陽三處、涿郡）
    ("甲兵一", "guan", "runan_wilds"), ("甲兵二", "guan", "runan_wilds"), ("甲兵三", "guan", "nanyang_road"), ("甲兵四", "guan", "yu_river"),
    ("乙兵一", "huang", "runan_wilds"), ("乙兵二", "huang", "runan_wilds"), ("乙兵三", "huang", "nanyang_wilds"),
    ("乙兵四", "huang", "zhuo_county"),
]


def duel_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """約戰的假人（--seats duel）兩段。
    一、整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）：observe 每一步把現實時鐘（game.now）往前推一分（同情境一步一分）——
    play_season 自己從不動現實時刻（bots 那一份的整季機器人在 week7 貼了一張、永遠不到時、冷卻也永遠不過），推了之後它照 bot.pick 最後那一行
    （duel_go）一張一張貼，窗滿了由它自己的 Game.advance 結算（整季機器人只 advance、不 sync、沒有排程：dev/sortie-2 審查，「只 advance 的
    結算組合」原本只有情境的 D7 一場）。寫 world.sorties 的每一張、存檔、戰報、紀錄標題與資料庫的雜湊。
    二、BotRunner＋bot_policy.take_turn（random.Random(7)、假時鐘、每一輪 +300 秒）兩軍各 4 個跑 N 輪——假人貼約戰（bot.duel_go）、應戰與同去
    （bot_policy.duel_play）、到時由 BotRunner._duel_tick 結算。寫 world.sorties 的每一張（誰貼、誰應、同去幾人、補位還是守軍、結果）、
    應戰與同去的次數、戰報、紀錄標題、存檔、各塊進度與資料庫的雜湊。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    content = load_content(root / "content", profile=profile)
    play_world = open_world(tmp / "play.db")
    moved = [0]

    def observe(g) -> None:  # 開始之前叫一次、之後每一步叫一次
        moved[0] += 1
        g.now = CLOCK0 + moved[0] * STEP_SECONDS

    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=play_world, now=CLOCK0,
                           observe=observe)
    rows = _duel_rows(play_world)
    emit("約戰整季機器人 約戰", rows)
    emit("約戰整季機器人 次數", dict(sorted(Counter(r["status"] for r in rows).items())))
    emit("約戰整季機器人 紀錄標題", dict(sorted(Counter(e.title for e in game.state.journal).items())))
    emit("約戰整季機器人 戰報", hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in game.state.battles], ensure_ascii=False)
                                                 .encode("utf-8")).hexdigest())
    emit("約戰整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("約戰整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())
    print(profile, "約戰整季機器人", moved[0], "步", dict(Counter((r["status"], r["defender"][1] if r["defender"] else None) for r in rows)))

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "duel.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "duel.db")
    for i, (name, side, loc) in enumerate(DUEL_SEATS):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="積極", seed=21 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_DUEL_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    duels = sorted(world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
    rows = [{"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
             "defender": None if d.defender is None else [d.defender.name, d.defender.garrison], "filled": bool(d.report.get("filled")),
             "tier": None if d.result is None else d.result.tier} for d in duels]
    counts = Counter()
    for d in duels:
        counts["約戰"] += 1
        counts["同去"] += len(d.attacker.allies)
        if d.defender is not None:
            counts["守軍" if d.defender.garrison else "補位" if d.report.get("filled") else "應戰"] += 1
        counts[d.status] += 1
    states = chars.all(bots_only=True)
    emit("約戰假人 一輪一輪", dict(sorted(totals.items())))
    emit("約戰假人 約戰", rows)
    emit("約戰假人 次數", dict(sorted(counts.items())))
    emit("約戰假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
    emit("約戰假人 戰報", {s.player.name: hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in s.battles], ensure_ascii=False)
                                                                   .encode("utf-8")).hexdigest() for s in states})
    emit("約戰假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    season = world.get_season()
    emit("約戰假人 各塊進度", hashlib.sha256((season.conquest.model_dump_json() if season.conquest is not None else "").encode("utf-8"))
         .hexdigest())
    emit("約戰假人 資料庫", hashlib.sha256(db_text(tmp / "duel.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "約戰假人", dict(totals), dict(counts))


# ═══════════════════════════ 入口 ═══════════════════════════


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("root")
    r.add_argument("profile", choices=PROFILES)
    r.add_argument("out")
    r.add_argument("--tmp", required=True)
    r.add_argument("--db")
    r.add_argument("--part", choices=("all", "first", "second"), default="all")
    r.add_argument("--track", choices=tuple(TRACKS), default="sortie")
    b = sub.add_parser("bots")
    b.add_argument("root")
    b.add_argument("profile", choices=PROFILES)
    b.add_argument("out")
    b.add_argument("--tmp", required=True)
    b.add_argument("--seats", choices=("sortie", "duel"), default="sortie")
    for name in ("compare", "selftest"):
        x = sub.add_parser(name)
        x.add_argument("--base", required=True)
        if name == "compare":
            x.add_argument("--head", required=True)
            x.add_argument("--no-bots", action="store_true")
        x.add_argument("--tmp", required=True)
        x.add_argument("--profiles", default=",".join(PROFILES))
        x.add_argument("--tracks", default=",".join(TRACK_NAMES))
        x.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        tmp = Path(a.tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        db = Path(a.db) if a.db else tmp / f"sb_{a.profile}.db"
        if a.part in ("all", "first"):
            for suffix in ("", "-wal", "-shm", "-push.sqlite", ".state.json"):
                p = Path(str(db) + suffix)
                if p.exists():
                    p.unlink()
        _setup_child(Path(a.root).resolve(), a.profile, db)
        TRACKS[a.track](Path(a.root).resolve(), a.profile, db).run(a.part, Path(a.out))
        sys.stdout.flush()
        os._exit(0)  # TestClient 留下的執行緒不等
    if a.cmd == "bots":
        (duel_bots_run if a.seats == "duel" else bots_run)(Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
        sys.stdout.flush()
        os._exit(0)
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = [p for p in a.profiles.split(",") if p]
    tracks = [t for t in a.tracks.split(",") if t]
    if a.cmd == "compare":
        ok = compare(Path(a.base).resolve(), Path(a.head).resolve(), Path(a.tmp), profiles, a.jobs, not a.no_bots, tracks=tracks)
    else:
        ok = selftest(Path(a.base).resolve(), Path(a.tmp), profiles, a.jobs, tracks=tracks)
    print("全部一樣" if ok else "有不一樣的")
    return 0 if ok else 1



# ═══════════════════════════ explore（主動搬六包第 3＋4 批：走一趟、探索一顆） ═══════════════════════════
# 這一段整段是第 3＋4 批加的（派工單：新情境寫成一段接在檔尾、一行登記）——情境 ExploreScenario（自己一個資料庫、自己切一半）、
# 假人 explore_bots_run，與四個子命令 explore-run、explore-bots、explore-compare、explore-selftest。上面原本的 run、compare、selftest、
# bots 一個字不動（出陣那一軌照舊用它們）；dev/sortie-2 把那幾個改成分軌（--track），合併之後可以把這一段收成 --track explore。
#
# 抽到哪一類（explore_one.draw）、仗打成怎樣（team.fight 的 tier）、幾個機率（rare_explore_chance、explore_legend_chance、
# duel.explore_chance、outing_trace_chance）在要的那幾步照寫好的換掉（模組屬性與記憶體裡的設定，兩份程式同一步換、同一步換回）；
# 換掉的 draw 把引擎算給它的比重寫進輸出（head 算錯比重照樣抓得到）。其餘照固定的亂數自己走。

EXPLORE_BOT_PROFILES = ("season21", "week7")  # 走一趟、探索一顆開著的兩種（不帶、weekend、測試內容關著）
EXPLORE_MUTANT_PROFILE = "week7"
# selftest 故意改的一個字：走一趟（同一趟留第二句那一句）、探索一顆（紀錄的結果標記「得料」）各一句；舊名的檔、搬進包的檔兩處找。
# 那兩處在整檔照搬的規則模組裡；動作模組（本體從 Game 搬過去、self 換成 ctx 的那兩個檔）另各改一處（審查修正）：探索一顆每一下少扣
# 1 體力、走一趟中途離開不收成「中途離開」——搬之前在 engine.py，搬進包之後在 explore_actions.py、outing_actions.py
EXPLORE_MUTATIONS = {
    "outing": (("tianxia/features/explore/outing_rules.py", "tianxia/outing.py"),
               ('SAY_AGAIN = "這一趟已經留過一句了。"', 'SAY_AGAIN = "這一趟已經留過一句了！"')),
    "explore_one": (("tianxia/features/explore/explore_rules.py", "tianxia/explore_one.py"),
                    ('MATERIAL: "得料"', 'MATERIAL: "得料！"')),
    "explore_actions": (("tianxia/features/explore/explore_actions.py", "tianxia/engine.py"),
                        ("p.stamina -= cfg.explore_stamina\n", "p.stamina -= cfg.explore_stamina - 1\n")),
    "outing_actions": (("tianxia/features/explore/outing_actions.py", "tianxia/engine.py"),
                       ("if trip.place != p.location:", "if trip.place != p.location and False:")),
}



def _explore_rules():
    """探索一顆的純規則模組：base 是 tianxia/explore_one.py，head 是指到探索包 explore_rules 的別名（同一個模組物件；換掉它的屬性兩邊都打得到）。"""
    from tianxia import explore_one

    return explore_one


class ExploreScenario(Scenario):
    """走一趟與探索一顆（第 3＋4 批）。照調查 plan.json order 3、6 的 behavior_check：各種地點按探索、事件卡等回答、遭遇、稀有、
    分級事件、隨口應對分岔（假模型）、45 級閘、掉落與破境丹、頭目、自家營寨比劃；走一趟一、三、五段、停下來、結算卡、題壁留言與
    預設三句、題壁墨（萬寶閣）、別人看得到痕跡、管理者抹掉、拒絕的情況。不帶、weekend、測試內容裡這兩樣關著：main.outing 是 None、
    四個 op 都回「此刻無法」、act:explore 走舊探索與三選一。
    半舊半新兩個切點都在前半的最後一段（half）：胡鐵花開一趟五段走到第二段停（等選事件）、姬冰雁探索出一張事件卡等回答；
    後半第一件事（answer）是新程式接著選完、走完、回答。"""

    PLAYERS = {"葉開": None, "丁靈琳": None, "路小佳": None, "燕南飛": None, "孟星魂": None, "高寄萍": "guan", "姬冰雁": None,
               "胡鐵花": None}
    NEWBIE = "初出茅廬"
    PHASES_FIRST = ["setup", "prologue", "places", "beats", "trip", "ink", "seen", "refuse", "half"]
    PHASES_SECOND = ["resume", "answer", "fight", "rare", "tiered", "freetext", "capped", "drops", "boss", "spar", "erase", "maps",
                     "season"]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def draws(self, *kinds: str):
        """探索一顆這幾下抽到的類別照 kinds 的順序（用完了照真的抽）；每一次都把引擎給的比重、上一趟的類別寫進輸出。"""
        explore_one = _explore_rules()

        real, queue = explore_one.draw, list(kinds)

        def draw(rng, weights, *, last_choice=None):
            forced = queue.pop(0) if queue else None
            emit("抽", {"weights": dict(weights), "last": last_choice, "forced": forced})
            return forced if forced is not None else real(rng, weights, last_choice=last_choice)

        explore_one.draw = draw
        try:
            yield
        finally:
            explore_one.draw = real

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）；None 照打。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None and tier is not None:
                kwargs["tier"] = tier
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    @contextlib.contextmanager
    def finds(self, *mids: str):
        """素材拍這幾下找到的照 mids（一下一顆；用完了照真的找）：explore_modes.gather_finds 換掉（模組屬性；探索三選一不搬，
        兩份程式叫的是同一個模組的同一個名字），每一次都寫進輸出。"""
        from tianxia import explore_modes

        real, queue = explore_modes.gather_finds, list(mids)

        def gather_finds(*args, **kwargs):
            if not queue:
                return real(*args, **kwargs)
            found = [queue.pop(0)]
            emit("找到", found)
            return found

        explore_modes.gather_finds = gather_finds
        try:
            yield
        finally:
            explore_modes.gather_finds = real

    @contextlib.contextmanager
    def tweak(self, obj, **values):
        """記憶體裡的設定這幾步換掉（兩份程式同一步換、同一步換回）。"""
        old = {k: getattr(obj, k) for k in values}
        for k, v in values.items():
            setattr(obj, k, v)
        try:
            yield
        finally:
            for k, v in old.items():
                setattr(obj, k, v)

    @contextlib.contextmanager
    def answer_model(self):
        """隨口應對的假模型：歸類回清單上的第一種、成算 70；判善惡回預設（中）；其餘照舊不連網路。"""
        import requests

        from tianxia import ollama_client

        wrapped = ollama_client.OllamaClient.from_config.__func__

        def chat_structured(client, messages, schema, *a, **k):
            fields = getattr(schema, "model_fields", {})
            if "outcome" in fields:
                ids = (fields["outcome"].json_schema_extra or {}).get("enum") or [""]
                return schema(outcome=ids[0], success_rate=70)
            if schema.__name__ == "SuccessRateJudgment":
                return schema(success_rate=70)
            if schema.__name__ == "MoralJudgment":
                return schema()
            raise requests.ConnectionError("same_behavior：不連模型")

        def from_config(cls, cfg):
            client = wrapped(cls, cfg)
            client.__class__ = type("AnswerClient", (type(client),), {"chat_structured": chat_structured})
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        try:
            yield
        finally:
            ollama_client.OllamaClient.from_config = classmethod(wrapped)

    def options(self, who: str) -> dict[str, dict]:
        return self.ids(self.main(who))

    def settle(self, who: str, rounds: int = 10) -> None:
        """這一下端出來要選的（事件、有所感、頭目戰的招）：照第一顆按得下去的選掉，直到探索回到選單上（或選不動）。"""
        from tianxia import sensing

        for _ in range(rounds):
            opts = self.options(who)
            if "act:explore" in opts:
                return
            pick = next((i for pre in ("choice:", "sense:", "duel:") for i, o in opts.items()
                         if i.startswith(pre) and o.get("enabled") and i not in (sensing.LET_GO, "duel:flee")), None)
            pick = pick or (sensing.LET_GO if sensing.LET_GO in opts else None)
            if pick is None:
                return
            self.choose(who, pick)

    def explore(self, who: str, nth: int = 0) -> None:
        """按一下探索：探索一顆開著是出門一趟；三選一開著（weekend）只回展開的那一句，再照 nth 輪流按一顆；接著選掉端出來的。"""
        self.choose(who, "act:explore")
        modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
        if modes:
            self.choose(who, modes[nth % len(modes)])
        self.settle(who)

    def walk(self, who: str, n: int, rounds: int = 10) -> None:
        """走一趟 n 段：出發，停在要選的事上就選掉、接著走，直到收了（關著的季只回一句「此刻無法」）。"""
        out = self.do(who, "outing", {"n": n})
        for _ in range(rounds):
            main = out.get("main") if isinstance(out, dict) else None
            trip = ((main or {}).get("outing") or {}).get("trip") if isinstance(main, dict) else None
            if not trip or trip.get("end"):
                return
            if trip.get("waiting"):
                self.settle(who)
            out = self.do(who, "outing", {})

    def kind_places(self) -> list[tuple[str, str]]:
        """（地點種類, 這一種照 id 排的第一個地點）：城、寺、渡、野、山、營。"""
        explore_one = _explore_rules()

        cfg = self.c.config.jianfa
        out = []
        for kind in (explore_one.TOWN, explore_one.TEMPLE, explore_one.FORD, explore_one.WILD, explore_one.HILL, explore_one.CAMP):
            loc = next((i for i, x in sorted(self.c.locations.items()) if explore_one.kind_of(cfg, x).kind == kind), None)
            if loc is not None:
                out.append((kind, loc))
        return out

    def first_event(self, test) -> str | None:
        """照 id 排第一則合 test 的事件（探索抽得到的優先）。"""
        evs = sorted(self.c.events.values(), key=lambda e: ("explore" not in e.actions, e.id))
        return next((e.id for e in evs if test(e)), None)

    def player_view(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        emit(tag, {"outing": None if p.outing is None else p.outing.model_dump(), "outing_last": p.outing_last,
                   "explore_seq": p.explore_seq, "fights": [p.fight_day, p.fights_today], "stamina": p.stamina})

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        self.place("高寄萍", None, faction="guan")  # 自家營寨比劃要有陣營（直接擺：投靠那一段是出陣那一軌驗的）

    def prologue(self) -> None:
        """序章的舊探索（草廬四景，_explore_outcome），接著按一下走一趟一段。有序章的只有不帶、weekend，那兩種走一趟本來就關著
        （回「此刻無法」是因為關著，不是因為在序章裡）；season21、week7 沒有序章，那一下是真的出發。所以 outing_go 的「序章裡不走」
        那一條在這五種設定裡都碰不到（審查修正：原本這裡寫成驗到了）。"""
        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
        else:
            self.choose(who, "choice:0")
            self.choose(who, "choice:0")
            self.do(who, "view_tab", {"tab": "practice"})
            self.choose(who, "act:explore")
            self.settle(who)
        self.do(who, "outing", {"n": 1})

    def places(self) -> None:
        """各種地點各按兩下探索（照固定的亂數自己抽）：鈕上的小字、行動列底下那一行、四格那一格的 mostly、結果那一段與帳。"""
        who = ["葉開", "丁靈琳", "路小佳", "燕南飛", "孟星魂", "姬冰雁"]
        for i, (kind, loc) in enumerate(self.kind_places()):
            name = who[i % len(who)]
            for k in range(2):
                self.place(name, loc)
                view = self.main(name)
                emit(f"{kind} {loc} 的探索", {"option": self.ids(view).get("act:explore"),
                                            "note": (view.get("action_notes") or {}).get("act:explore"),
                                            "mostly": view.get("mostly"), "outing": view.get("outing")})
                self.explore(name, i + k)
                self.player_view(name, f"{name} 探索之後")

    def beats(self) -> None:
        """四類各一下（照寫好的抽）：事件卡等你回答、有所感、素材、遭遇打贏與打輸。"""
        explore_one = _explore_rules()

        for kind, tier in ((explore_one.EVENT, None), (explore_one.INSIGHT, None), (explore_one.MATERIAL, None),
                           (explore_one.ENCOUNTER, "大勝"), (explore_one.ENCOUNTER, "落敗")):
            if not self.place("燕南飛", "yingshui"):
                return
            with self.draws(kind), self.fights(tier):
                out = self.choose("燕南飛", "act:explore")
            emit(f"{kind} {tier or ''} 那一下", (out.get("main") or {}).get("latest") if isinstance(out, dict) else None)
            self.settle("燕南飛")
        self.player_view("燕南飛", "燕南飛 四類之後")

    def trip(self) -> None:
        """走一趟：段數選單、n=2 不收、五段（第二段停在事件上、選完接著走；有一段打贏）、結算卡、預設句留言、同一趟再留一句被擋。"""
        explore_one = _explore_rules()

        if not self.place("葉開", "yingshui"):
            return
        emit("段數選單", self.main("葉開").get("outing"))
        self.do("葉開", "outing", {"n": 2})
        with self.draws(explore_one.MATERIAL, explore_one.EVENT, explore_one.MATERIAL, explore_one.ENCOUNTER, explore_one.MATERIAL), \
                self.fights("大勝"):
            self.walk("葉開", 5)
        self.player_view("葉開", "葉開 走完五段")
        self.do("葉開", "outing_say", {"preset": 0})
        self.do("葉開", "outing_say", {"preset": 1})
        with self.draws(explore_one.MATERIAL):
            self.place("葉開", "yingshui")
            self.walk("葉開", 1)  # 第二趟（Outing.n 加一）：一段

    def ink(self) -> None:
        """自己寫的一句要一張題壁墨：沒有回 NO_INK → 管理者補發元寶 → 萬寶閣買題壁墨 → 再寫；遊記（模型不在，照模板）。"""
        explore_one = _explore_rules()

        if not self.place("丁靈琳", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL, explore_one.MATERIAL):
            self.walk("丁靈琳", 3)
        line = "江湖路遠，後會有期"
        self.do("丁靈琳", "outing_say", {"text": line})
        self.do(ADMIN, "mall_reissue", {"name": "丁靈琳", "amount": 200, "note": "對照", "ref": "sb-reissue-1"})  # 不給編號伺服器會產一個隨機的
        self.call("丁靈琳", "POST", "/api/mall/buy", {"item": "inscribe_ink", "ref": "sb-ink-1"})
        self.do("丁靈琳", "outing_say", {"text": line})
        self.do("丁靈琳", "outing_tale")
        self.do("丁靈琳", "outing_tale")  # 請過了：不再開單

    def seen(self) -> None:
        """別人看得到痕跡：路小佳在同一處走五段，路上的那一行一定擲中（outing_trace_chance 換成 1），一趟最多兩行（outing_trace_cap
        換成 2；正式是 1）：這一處有人，第一行一定是遠處有人揮手，第二行才輪得到刻在石頭上的別人的留言（葉開、丁靈琳剛在這裡留過）。"""
        explore_one = _explore_rules()

        if not self.place("路小佳", "yingshui"):
            return
        with self.draws(*[explore_one.MATERIAL] * 5), \
                self.tweak(self.c.config.jianfa, outing_trace_chance=1.0, outing_trace_cap=2):
            self.walk("路小佳", 5)
        self.player_view("路小佳", "路小佳 路上看到的")

    def refuse(self) -> None:
        """拒絕：體力不夠、在路上、走到一半人離開（收成「中途離開」）。"""
        explore_one = _explore_rules()

        if not self.place("燕南飛", "yingshui"):
            return
        self.edit("燕南飛", lambda p: setattr(p, "stamina", 5.0))
        self.do("燕南飛", "outing", {"n": 5})
        self.place("燕南飛", None)
        move = next((i for i, o in self.options("燕南飛").items() if i.startswith("move:") and o.get("enabled")), None)
        if move is not None:
            self.choose("燕南飛", move)
            self.do("燕南飛", "outing", {"n": 1})
        if self.place("孟星魂", "yingshui"):
            with self.draws(explore_one.MATERIAL, explore_one.EVENT):
                self.do("孟星魂", "outing", {"n": 3})
            self.place("孟星魂", "yingchuan")
            self.do("孟星魂", "outing", {})
            self.do("孟星魂", "outing_say", {"preset": 0})  # 中途離開的那一趟不能留言
            self.settle("孟星魂")
            self.player_view("孟星魂", "孟星魂 中途離開")

    def half(self) -> None:
        """前半的最後一段（半舊半新的切點）：胡鐵花開一趟五段走到第二段停（等選事件）；姬冰雁出門一趟抽到事件、卡等回答。"""
        explore_one = _explore_rules()

        if self.place("胡鐵花", "yingshui"):
            with self.draws(explore_one.MATERIAL, explore_one.EVENT):
                self.do("胡鐵花", "outing", {"n": 5})
            self.player_view("胡鐵花", "胡鐵花 停在第二段")
        if self.place("姬冰雁", "nanyang_wilds"):
            with self.draws(explore_one.EVENT):
                self.choose("姬冰雁", "act:explore")
            modes = [i for i, o in self.options("姬冰雁").items() if i.startswith("explore:") and o.get("enabled")]
            if modes:  # 三選一的季：找事件那一顆
                self.choose("姬冰雁", next((m for m in modes if m == "explore:seek"), modes[0]))
            emit("姬冰雁 等回答", self.chars.load("姬冰雁").pending_event)

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        """新程式接手：姬冰雁回答舊程式端出來的事件卡；胡鐵花選完那件事（走一趟記下那一下的得失）、接著走完。"""
        explore_one = _explore_rules()

        self.settle("姬冰雁")
        self.player_view("姬冰雁", "姬冰雁 回答之後")
        self.settle("胡鐵花")
        self.player_view("胡鐵花", "胡鐵花 選完")
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL, explore_one.MATERIAL):
            out = self.do("胡鐵花", "outing", {})
            for _ in range(6):
                trip = (((out.get("main") or {}).get("outing") or {}).get("trip") if isinstance(out, dict) else None) or {}
                if not trip or trip.get("end"):
                    break
                if trip.get("waiting"):
                    self.settle("胡鐵花")
                out = self.do("胡鐵花", "outing", {})
        self.player_view("胡鐵花", "胡鐵花 走完")

    def fight(self) -> None:
        """遭遇：散人在官軍大營撞上北軍五校（必敗）照寫好的打贏＝以弱勝強（行狀、世界記事）；走一趟裡也打贏一次；城裡的地痞照打。"""
        explore_one = _explore_rules()

        if self.place("燕南飛", "guan_camp"):
            emit("必敗的探索", self.options("燕南飛").get("act:explore"))
            with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                self.choose("燕南飛", "act:explore")
            self.place("燕南飛", "guan_camp")
            with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                self.walk("燕南飛", 1)
            self.player_view("燕南飛", "燕南飛 以弱勝強")
        town = next((loc for kind, loc in self.kind_places() if kind == "town"), None)
        if town is not None and self.place("丁靈琳", town):
            with self.draws(explore_one.ENCOUNTER, explore_one.ENCOUNTER):
                self.choose("丁靈琳", "act:explore")
                self.settle("丁靈琳")
                self.place("丁靈琳", None)
                with self.fights("僵持"):
                    self.choose("丁靈琳", "act:explore")
            self.settle("丁靈琳")

    def rare(self) -> None:
        """稀有與稀世：
        - 一次性奇遇必中（rare_explore_chance 換成 1）：站在此刻有一次性奇遇可抽的地點（白馬寺：鎮山塔；深山：飛瀑）出門一趟抽到事件，
          走的是事件拍的稀有那一支（outing_event）。路小佳按一下探索；葉開走一趟一段，那一段記成稀有（"rare": true）。
        - 稀世的素材：丁靈琳走一趟一段抽到素材，找到的換成一顆 FEAT_TIER 階以上的（finds；gather_finds 只給一、二階，自己走不到），
          收的時候記一則行狀與世界記事。
        - 五段的一趟照固定的亂數自己抽（段數越多稀有的越容易來）。"""
        explore_one = _explore_rules()
        from tianxia import outing

        if self.place("路小佳", "baima_temple"):
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.choose("路小佳", "act:explore")
            emit("路小佳 稀有的事件", self.chars.load("路小佳").pending_event)
            self.settle("路小佳")
        if self.place("葉開", "deep_mountain"):
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.walk("葉開", 1)
            self.player_view("葉開", "葉開 稀有的一段")
        top = sorted(m.id for m in self.c.materials.values() if m.tier >= outing.FEAT_TIER)
        emit("稀世的素材", top[:1])
        if top and self.place("丁靈琳", "yingshui"):
            with self.draws(explore_one.MATERIAL), self.finds(top[0]):
                self.walk("丁靈琳", 1)
            self.player_view("丁靈琳", "丁靈琳 稀世的一段")
        if self.place("葉開", "nanyang_wilds"):
            self.walk("葉開", 5)
            self.player_view("葉開", "葉開 自己抽的五段")

    def tiered(self) -> None:
        """分級事件經探索一顆抽出來：武事那一道門開到第二階（等級拉到門檻）的人，站在一則第二階武事事件掛的地點（不是野類：野類先抽旅人）
        出門一趟抽到事件——事件分級挑第二階（tier_mix 換成只有第二階）、一次性奇遇不擲（rare_explore_chance 換成 0）——走的是
        outing_event → pick_event 端出來（場景卡上那一行），選第一個。三選一的季照找事件那一顆按。"""
        explore_one = _explore_rules()

        cfg = self.c.config.jianfa

        def fits(e) -> bool:
            loc = self.c.locations.get(e.locations[0]) if e.locations else None
            return e.tier == 2 and e.door == "武事" and "explore" in e.actions and loc is not None \
                and explore_one.kind_of(cfg, loc).kind != explore_one.WILD

        ev = self.first_event(fits)
        emit("分級事件", ev)
        if ev is None or not self.place("孟星魂", self.c.events[ev].locations[0]):
            return
        need = (cfg.tier_doors.get("武事") or [1])[0]
        self.edit("孟星魂", lambda p: setattr(p.member, "level", max(p.member.level, need)))
        mix = {**cfg.tier_mix, 2: [0.0, 1.0], 3: [0.0, 1.0, 0.0]}
        with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=0.0), self.tweak(cfg, tier_mix=mix):
            self.choose("孟星魂", "act:explore")
            modes = [i for i, o in self.options("孟星魂").items() if i.startswith("explore:") and o.get("enabled")]
            if modes:  # 三選一的季：找事件那一顆
                self.choose("孟星魂", next((m for m in modes if m == "explore:seek"), modes[0]))
        emit("孟星魂 抽到的分級事件", self.chars.load("孟星魂").pending_event)
        self.settle("孟星魂")

    def freetext(self) -> None:
        """隨口應對的分岔（假模型）：走一趟停在事件上，換成一則寫了後果的事件，回一句話；接著走完。"""
        explore_one = _explore_rules()

        ev = self.first_event(lambda e: e.free_text is not None and bool(e.free_text.outcomes)) or \
            self.first_event(lambda e: e.free_text is not None)
        emit("隨口應對的事件", ev)
        if ev is None or not self.place("路小佳", "yingshui"):
            return
        with self.draws(explore_one.EVENT):
            self.do("路小佳", "outing", {"n": 3})
        self.edit_state("路小佳", lambda s: setattr(s, "pending_event", ev))
        emit("隨口應對那一顆", {i: o for i, o in self.options("路小佳").items() if not i.startswith(("move:", "act:"))})
        with self.answer_model():
            self.call("路小佳", "POST", "/api/answer", {"text": "我上前扶他一把，問他要往哪裡去。"})
        self.settle("路小佳")
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL):
            self.do("路小佳", "outing", {})
        self.player_view("路小佳", "路小佳 隨口應對之後")

    def capped(self) -> None:
        """45 級閘：45 級的人出門一趟打贏一場、撿一次素材（經驗換心得、段落結尾「境界已到」）。"""
        explore_one = _explore_rules()

        if not self.place("孟星魂", "nanyang_wilds"):
            return
        self.edit("孟星魂", lambda p: setattr(p.member, "level", 45))
        with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
            self.choose("孟星魂", "act:explore")
        self.settle("孟星魂")
        self.place("孟星魂", None)
        with self.draws(explore_one.MATERIAL):
            self.choose("孟星魂", "act:explore")
        self.settle("孟星魂")
        self.player_view("孟星魂", "孟星魂 45 級")

    def drops(self) -> None:
        """掉落與破境丹：破境丹必中（explore_legend_chance 換成 1）出門兩趟。"""
        explore_one = _explore_rules()

        if not self.place("姬冰雁", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.ENCOUNTER), self.tweak(self.c.config, explore_legend_chance=1.0), \
                self.fights("大勝"):
            self.choose("姬冰雁", "act:explore")
            self.settle("姬冰雁")
            self.place("姬冰雁", None)
            self.choose("姬冰雁", "act:explore")
        self.settle("姬冰雁")
        self.player_view("姬冰雁", "姬冰雁 掉落")

    def boss(self) -> None:
        """頭目：長社（只有頭目、沒有一般對手）出門一趟抽到遭遇，頭目擋路、頭目戰照第一招打完；頭目機率換成 1 再擲一次。"""
        explore_one = _explore_rules()

        if not self.place("燕南飛", "changshe"):
            return
        emit("長社的探索", self.options("燕南飛").get("act:explore"))
        with self.draws(explore_one.ENCOUNTER), self.tweak(self.c.config.duel, explore_chance=1.0), self.fights("大勝"):
            self.choose("燕南飛", "act:explore")
            self.settle("燕南飛", rounds=14)
        self.player_view("燕南飛", "燕南飛 頭目之後")

    def spar(self) -> None:
        """自家營寨：官軍的人在官軍大營出門一趟抽到遭遇是跟同袍比劃（出陣包的 _sortie_host 那一路的三成，不打、不掉東西）。"""
        explore_one = _explore_rules()

        if not self.place("高寄萍", "guan_camp"):
            return
        view = self.main("高寄萍")
        emit("自家營寨的探索", {"option": self.ids(view).get("act:explore"), "note": (view.get("action_notes") or {}).get("act:explore")})
        with self.draws(explore_one.ENCOUNTER):
            self.choose("高寄萍", "act:explore")
        self.settle("高寄萍")
        self.player_view("高寄萍", "高寄萍 比劃之後")

    def erase(self) -> None:
        """管理者抹掉一則留言（不是管理者按到回「只有管理者能這麼做」）；抹過的再抹一次回「此刻無法」。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        ids = [i.id for i in shell.state.world.inscriptions]
        emit("留言", [i.model_dump() for i in shell.state.world.inscriptions])
        target = ids[0] if ids else 1
        self.do("葉開", "outing_erase", {"id": target})
        self.do(ADMIN, "outing_erase", {"id": target})
        self.do(ADMIN, "outing_erase", {"id": target})

    def maps(self) -> None:
        """輿圖名字旁的兩個字（map_mostly：替每一處假裝站過去）：底圖與疊層。"""
        if self.place("葉開", "yingshui"):
            self.call("葉開", "GET", "/api/map/base")
            self.call("葉開", "GET", "/api/map/state")

    def season(self) -> None:
        """收季、開下一季：走一趟、探索一顆認領的欄位跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main("葉開")
        self.do(ADMIN, "next_season")
        view = self.main("葉開")
        emit("換季之後", {"outing": view.get("outing"), "option": self.ids(view).get("act:explore")})
        self.player_view("葉開", "葉開 換季之後")


def explore_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """走一趟、探索一顆的假人：整季機器人（bot.play_season，種子 5）與伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(9)、
    假時鐘，八個站在不在爭奪之列的地點的假人：take_turn 的走一趟那兩段——停著的先接著走、挑到探索就挑段數出發——只有它走得到）
    各跑 N 輪：寫存檔、世界與資料庫的雜湊、各種紀錄標題的次數（看得出「走一趟・某地」「出門一趟・某地」有沒有走到）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title for s in states for e in s.journal).items()))

    content = load_content(root / "content", profile=profile)
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=5, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("探索 整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("探索 整季機器人 紀錄標題", titles([game.state]))
    emit("探索 整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("探甲", "guan", "yingshui"), ("探乙", "guan", "yingchuan"), ("探丙", "huang", "yingshui"), ("探丁", "huang", "nanyang_road"),
             ("探戊", "guan", "changshe"), ("探己", "huang", "guan_camp"), ("探庚", "guan", "guan_camp"), ("探辛", "huang", "nanyang_wilds")]
    for i, (name, side, loc) in enumerate(seats):
        if loc not in content.locations:
            continue
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        p.stamina = float(content.config.stamina_max)
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(9), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_EXPLORE_TICKS", "160"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    trips = Counter((s.player.outing.total, s.player.outing.end) for s in states if s.player.outing is not None)
    emit("探索 假人程式 一輪一輪", dict(sorted(totals.items())))
    emit("探索 假人程式 紀錄標題", titles(states))
    emit("探索 假人程式 最後一趟", {f"{t}段 {e or '還在路上'}": n for (t, e), n in sorted(trips.items())})
    emit("探索 假人程式 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("探索 假人程式 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "探索假人", dict(totals), dict(trips))


def _explore_mutant(base: Path, tmp: Path, which: str) -> Path:
    files, (old, new) = EXPLORE_MUTATIONS[which]
    dest = tmp / f"mutant_{which}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=shutil.ignore_patterns(".git", "saves", ".local", "__pycache__", "node_modules", ".venv", "docs"))
    for rel in files:
        path = dest / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if text.count(old) == 1:
            path.write_text(text.replace(old, new), encoding="utf-8")
            return dest
    raise RuntimeError(f"找不到要改的那一句（{which}）")


def explore_compare(base: Path, head: Path, tmp: Path, profiles: list[str], workers: int, bots: bool, label: str = "ecompare") -> bool:
    """同 compare，跑的是 ExploreScenario（explore-run）與 explore_bots_run（explore-bots）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    chains, outputs = [], {}
    for p in profiles:
        o = {k: tmp / f"{label}_{k}_{p}.txt" for k in ("base", "head", "base1", "head2")}
        dbs = {k: tmp / f"{label}_{k}_{p}.db" for k in ("base", "head", "half")}
        outputs[p] = o
        chains.append([(["explore-run", str(base), p, str(o["base"]), "--tmp", str(tmp), "--db", str(dbs["base"])], tmp / f"{label}_base_{p}.log")])
        chains.append([(["explore-run", str(head), p, str(o["head"]), "--tmp", str(tmp), "--db", str(dbs["head"])], tmp / f"{label}_head_{p}.log")])
        chains.append([
            (["explore-run", str(base), p, str(o["base1"]), "--tmp", str(tmp), "--db", str(dbs["half"]), "--part", "first"],
             tmp / f"{label}_base1_{p}.log"),
            (["explore-run", str(head), p, str(o["head2"]), "--tmp", str(tmp), "--db", str(dbs["half"]), "--part", "second"],
             tmp / f"{label}_head2_{p}.log"),
        ])
    bot_out = {}
    if bots:
        for p in EXPLORE_BOT_PROFILES:
            bot_out[p] = {k: tmp / f"{label}_bots_{k}_{p}.txt" for k in ("base", "head")}
            for k, root in (("base", base), ("head", head)):
                chains.append([(["explore-bots", str(root), p, str(bot_out[p][k]), "--tmp", str(tmp / f"{label}_bots_{k}_{p}")],
                                tmp / f"{label}_bots_{k}_{p}.log")])
    started = time.time()
    _run_set(chains, workers)
    print(f"跑完 {time.time() - started:.0f} 秒")
    ok = True
    for p, o in outputs.items():
        hb, nb, bb = _digest(o["base"])
        hh, _, _ = _digest(o["head"])
        hx, _, _ = _digest(o["base1"], o["head2"])
        same, half = hb == hh, hb == hx
        ok &= same and half
        print(f"explore {p:9} 整段 base {nb} 行 {bb} 位元組 {hb[:16]}｜head {hh[:16]} {'一樣' if same else '不一樣'}"
              f"｜base 前半＋head 後半 {hx[:16]} {'一樣' if half else '不一樣'}")
        if not same:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
        if not half:
            print("  半舊半新：" + _first_diff(o["base"].read_bytes(), o["base1"].read_bytes() + o["head2"].read_bytes()))
    for p, o in bot_out.items():
        hb, nb, bb = _digest(o["base"])
        hh, _, _ = _digest(o["head"])
        ok &= hb == hh
        print(f"探索假人 {p:9} {nb} 行 {bb} 位元組 base {hb[:16]}｜head {hh[:16]} {'一樣' if hb == hh else '不一樣'}")
        if hb != hh:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
    return ok


def explore_selftest(base: Path, tmp: Path, profiles: list[str], workers: int) -> bool:
    """同 selftest：同一份跑兩次一樣、前半＋後半（base 接 base）＝整段、改一個字（走一趟、探索一顆各一份 mutant，跑 week7）抓得到差；
    假人跑兩次一樣。"""
    tmp.mkdir(parents=True, exist_ok=True)
    mutants = {w: _explore_mutant(base, tmp, w) for w in EXPLORE_MUTATIONS}
    chains, outs = [], {}
    for p in profiles:
        o = {k: tmp / f"eself_{k}_{p}.txt" for k in ("a", "b", "first", "second", *(f"mut_{w}" for w in mutants))}
        outs[p] = o
        for k in ("a", "b"):
            chains.append([(["explore-run", str(base), p, str(o[k]), "--tmp", str(tmp), "--db", str(tmp / f"eself_{k}_{p}.db")],
                            tmp / f"eself_{k}_{p}.log")])
        chains.append([
            (["explore-run", str(base), p, str(o["first"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_half_{p}.db"), "--part", "first"],
             tmp / f"eself_first_{p}.log"),
            (["explore-run", str(base), p, str(o["second"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_half_{p}.db"), "--part", "second"],
             tmp / f"eself_second_{p}.log"),
        ])
        if p == EXPLORE_MUTANT_PROFILE:
            for w, root in mutants.items():
                chains.append([(["explore-run", str(root), p, str(o[f"mut_{w}"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_mut_{w}_{p}.db")],
                                tmp / f"eself_mut_{w}_{p}.log")])
    bot_out = {}
    for p in EXPLORE_BOT_PROFILES:
        bot_out[p] = {k: tmp / f"eself_bots_{k}_{p}.txt" for k in ("a", "b")}
        for k in ("a", "b"):
            chains.append([(["explore-bots", str(base), p, str(bot_out[p][k]), "--tmp", str(tmp / f"eself_bots_{k}_{p}")],
                            tmp / f"eself_bots_{k}_{p}.log")])
    started = time.time()
    _run_set(chains, workers)
    print(f"跑完 {time.time() - started:.0f} 秒")
    ok = True
    for p, o in outs.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        hx, _, _ = _digest(o["first"], o["second"])
        ok &= ha == hb and ha == hx
        line = f"explore {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}｜前半＋後半 {'一樣' if ha == hx else '不一樣'}"
        if p == EXPLORE_MUTANT_PROFILE:
            for w in mutants:
                hm, _, _ = _digest(o[f"mut_{w}"])
                caught = hm != ha
                ok &= caught
                line += f"｜改一個字（{w}）{'抓得到' if caught else '抓不到'}"
                if caught:
                    line += "（" + _first_diff(o["a"].read_bytes(), o[f"mut_{w}"].read_bytes()).split("：")[0] + "）"
        print(line)
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
        if ha != hx:
            print("  " + _first_diff(o["a"].read_bytes(), o["first"].read_bytes() + o["second"].read_bytes()))
    for p, o in bot_out.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        ok &= ha == hb
        print(f"探索假人 {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}")
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
    return ok


def _explore_entry(main_fn):
    """explore 的四個子命令；其餘照原本的 main（一個字不動）。"""

    def entry(argv: list[str] | None = None) -> int:
        args = list(sys.argv[1:] if argv is None else argv)
        if not args or args[0] not in ("explore-run", "explore-bots", "explore-compare", "explore-selftest"):
            return main_fn(argv)
        ap = argparse.ArgumentParser(description="走一趟、探索一顆的前後一字不變（主動搬六包第 3＋4 批）")
        sub = ap.add_subparsers(dest="cmd", required=True)
        r = sub.add_parser("explore-run")
        r.add_argument("root")
        r.add_argument("profile", choices=PROFILES)
        r.add_argument("out")
        r.add_argument("--tmp", required=True)
        r.add_argument("--db")
        r.add_argument("--part", choices=("all", "first", "second"), default="all")
        b = sub.add_parser("explore-bots")
        b.add_argument("root")
        b.add_argument("profile", choices=PROFILES)
        b.add_argument("out")
        b.add_argument("--tmp", required=True)
        for name in ("explore-compare", "explore-selftest"):
            x = sub.add_parser(name)
            x.add_argument("--base", required=True)
            if name == "explore-compare":
                x.add_argument("--head", required=True)
                x.add_argument("--no-bots", action="store_true")
            x.add_argument("--tmp", required=True)
            x.add_argument("--profiles", default=",".join(PROFILES))
            x.add_argument("--jobs", type=int, default=4)
        a = ap.parse_args(args)
        if a.cmd == "explore-run":
            tmp = Path(a.tmp)
            tmp.mkdir(parents=True, exist_ok=True)
            db = Path(a.db) if a.db else tmp / f"sbx_{a.profile}.db"
            if a.part in ("all", "first"):
                for suffix in ("", "-wal", "-shm", "-push.sqlite", ".state.json"):
                    p = Path(str(db) + suffix)
                    if p.exists():
                        p.unlink()
            _setup_child(Path(a.root).resolve(), a.profile, db)
            ExploreScenario(Path(a.root).resolve(), a.profile, db).run(a.part, Path(a.out))
            sys.stdout.flush()
            os._exit(0)  # TestClient 留下的執行緒不等
        if a.cmd == "explore-bots":
            explore_bots_run(Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
            sys.stdout.flush()
            os._exit(0)
        sys.stdout.reconfigure(encoding="utf-8")
        profiles = [p for p in a.profiles.split(",") if p]
        if a.cmd == "explore-compare":
            ok = explore_compare(Path(a.base).resolve(), Path(a.head).resolve(), Path(a.tmp), profiles, a.jobs, not a.no_bots)
        else:
            ok = explore_selftest(Path(a.base).resolve(), Path(a.tmp), profiles, a.jobs)
        print("全部一樣" if ok else "有不一樣的")
        return 0 if ok else 1

    return entry


main = _explore_entry(main)  # explore（第 3＋4 批）一行登記：多四個子命令，其餘照原本的 main


if __name__ == "__main__":
    sys.exit(main())
