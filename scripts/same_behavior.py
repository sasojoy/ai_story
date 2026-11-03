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


# ═══════════════════════════ battle：決戰一軌（主動搬六包第 5 批 dev/battle-1、全部拆包第 6 批 dev/battle-2） ═══════════════════════════
# 全服決戰「看」那一半（畫面、戰報、補送、放手一搏補劇情）搬進 tianxia/features/battle/（計畫 docs/superpowers/plans/2026-10-31-決戰包-第1批.md）；
# 第 6 批接著搬管理者的決戰工具與攻城（計畫 2026-11-01-決戰包-第2批.md：BattleScenario 加 admin、siege_*、resting 幾段）。
# 第 7 批搬集結、投效、挑同伴（計畫 2026-11-01-決戰包-第3批.md：BattleScenario 加 muster_*、late、wander 幾段與 bots 那一段的大區外假人，
# 同一套段落另外登記成 muster 一軌、切在集結中）。
# 這一段整塊是決戰的：四條拆包線並行，接在檔尾、最後一行登記（_battle_register_track），PM 合的時候不跟別人的行穿插。


# develop 0425589a 之後才要的兩個固定（註冊限流、資料庫第 9 版 sessions 的 token_hash 抹掉）：這一塊原本自己套一份，
# 合 develop（2026-11-01）時 develop 已經放在共用那一層（Scenario.__init__、db_text），只留那一份。


BATTLE_RATE = 60  # 假模型評的放手一搏成功率（server.battle_text 的 B 段，battle_instance.score_gamble）
BATTLE_STORY = "{name}一聲長嘯，提刀衝進陣中。"  # 假模型補的劇情（server.narrate_once 的 B 段；不寫數字、成敗都是這一句）
_BATTLE_CLIENTS: dict[type, type] = {}


def _battle_client(base: type) -> type:
    """放手一搏評分、補劇情的假模型（base 是 _setup_child 換好的 client 類別）：GambleScore 回 BATTLE_RATE、TaleBatch 照單子上的名號
    每人一句 BATTLE_STORY，其餘照 base（丟連線錯誤、大場面判讀）。這兩種回答之前先把送來的提示整份寫進輸出（messages 與其餘參數）：
    假模型不看提示，單子上的幕（act_index）、陣營名、原句、點名、性別、成敗改了，回的還是同一句，不寫進輸出就比不出來（審查 should；
    提示由 battle_instance.score_gamble／write_tales 照 view.battle_text_request／battle_tale_request 開的單子組，兩份程式組法一樣）。"""
    if base not in _BATTLE_CLIENTS:
        import re

        class BattleClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ in ("GambleScore", "TaleBatch"):
                    emit(f"模型單子 {schema.__name__}", {"messages": messages, "rest": repr((a, sorted(k.items())))})
                if schema.__name__ == "GambleScore":
                    return schema(success_rate=BATTLE_RATE)
                if schema.__name__ == "TaleBatch":
                    names = re.findall(r"^\d+\. (.+?)（", messages[-1]["content"], re.M)
                    return schema(lines=[{"name": n, "story": BATTLE_STORY.format(name=n)} for n in names])
                return super().chat_structured(messages, schema, *a, **k)

        _BATTLE_CLIENTS[base] = BattleClient
    return _BATTLE_CLIENTS[base]


def _still(phase):
    """第 7 批插進來的段落（BattleScenario.still）：這一段裡的每一個請求，決戰與攻城的期限都跟著時鐘往後挪那一步。"""

    def run(self, *a, **k):
        with self.still():
            return phase(self, *a, **k)

    run.__name__, run.__doc__ = phase.__name__, phase.__doc__
    return run


class BattleScenario(Scenario):
    """全服決戰「看」那一半（主動搬六包第 5 批；--track battle，自己一個資料庫）。照 plan.json order 4 的 behavior_check：管理者開季、
    開戰（不帶設定：start_battle 黃巾決戰；weekend、season21、week7：start_showdown 長社火攻）；官軍、黃巾、豪強、散人各一人擺在決戰的大區，
    集結中看畫面（場景、戰局條、選單）、加入（兩軍 battle:join、散人與豪強照引擎給的鈕 join 或 enlist）；集結截止開打；第一回合官軍放手一搏
    （/api/do/battle_text，假模型評 BATTLE_RATE）、散人掛機到逾時、其餘出招——**這裡切一半**（那一回合結算了、劇情還沒補：
    批次表「舊程式寫到一半」）；後半重新登入，server.narrate_once 補劇情（假模型），打到收場（第二幕黃巾再搏一次、再補一次）；每個人打
    /api/main 收補送（江湖紀錄、戰報、軍餉、行狀、戰功）、/api/reports 與 ?id=；一位的決戰戰報從存檔拿掉、showdowns_restored 歸零，下一次
    同步補回來（RESTORED_NOTE，照收場時刻排進兩筆尋常的戰報中間）；伺服器假人（BotRunner）打另一場、整季機器人（week7）帶一場；收季、
    開下一季（battle_results_seen 照帶），那一場收場之後還沒同步過的假人換季之後才補到（上一季那一支）。季終收兵那一支（unfinished）
    走不到（時刻表的季開不出第三場：長社、廣宗開過了，宛城要等第 3 週那件大事結算才知道是哪一版），由 tianxia/features/battle/tests/test_showdown_delivery.py 守。
    序章裡的那一位（NEWBIE）一路看：序章不畫戰場。測試內容沒有決戰：同一串 API 照打（證明關著一個字都不變），假人那一段略過。

    第 6 批（決戰「打」a：管理者的決戰工具與攻城，dev/battle-2；計畫 docs/superpowers/plans/2026-11-01-決戰包-第2批.md）插進來的段：
    admin（開戰之前按得到的被拒）、admin_trial（第 5 批那一場收場之後：開了再取消，與那時候按得到的被拒）——管理者的決戰工具一樣一樣按，
    成的與被拒的各一次；siege_*（地盤開著的 weekend、season21、week7：六場攻城，見 SIEGES；none、test 沒有地盤，那幾段什麼都不打）；
    resting（收季之後再按一輪，season 那一段裡）。前半照舊停在 gamble：同一刻兩場攻城（A、B）打了一兩回合、還沒收場（round 接一行
    siege_round：決戰每一回合攻城的真人也各出一招）——後半由 head 打完兩場攻城、結算、補送。

    第 7 批（決戰「打」b：集結、投效、挑同伴，dev/battle-3；計畫 docs/superpowers/plans/2026-11-01-決戰包-第3批.md）插進來的段：muster_seat（六位新人
    MUSTER_PLAYERS 直接建進資料庫再登入、擺位置；秦朗月、顧長風、莫問天、石破浪名下各一位同伴）、muster_pick（挑同伴與「再想想」、臨時投效再改投、同一個
    大區兩場打得進去時照 @流水號加入——潁汝多一場攻城 G、集結被拒的路）、muster_more（顧長風挑好同伴加入、江映雪投靠豪強之後集結名單跟著換邊）、
    late（開打之後：停在挑同伴的才挑〔改成晚到〕、晚到、晚到臨時投效、再按另一邊被擋）、wander（參戰者走出大區、喊停）、muster_deliver（同伴回江湖、
    情誼減半、同一次同步清記號）；bots 那一段多一位名下有同伴、站在大區外的官軍假人（趕路、挑同伴的分數）。這一軌照舊切在 gamble；同一套段落另外
    登記成 muster 一軌（MusterScenario），切在 muster_pick 之後——舊程式寫到兩位按了加入、停在挑同伴（escort_pick 寫進存檔）就停，新程式接著挑。
    第 7 批插進來的請求不吃決戰與攻城的時間（審查 should：原本吃掉集結那 30 分鐘與第一回合的 180 秒——season21 的長社火攻在 muster_more 裡就開打、
    第一幕全是逾時；weekend、week7 的第一回合在 late 裡逾時，放手一搏落到第二回合）：上面那幾段（_still）、narrate 裡新人的重新登入、名下有第 7 批
    給的同伴的人按「不派」那一下，每一步之前把決戰與攻城的期限往後挪那一步（still、hold），G 在 muster_more 最後取消；第 5、6 批的集結截止、
    開打那一刻與每一回合的逾時照那幾段原本的請求算，跟第 6 批的情境一樣（有決戰的四種設定逐回合比過：哪幾回合逾時、第幾回合換幕、兩次放手一搏
    落在哪一回合、第九回合收場，都跟第 6 批那一版一樣；收場的勝負照多出來的參戰者變了）。第 7 批的人加入之後不出招（第一回合逾時代為固守，之後不再等他們），出招的照舊是第 5 批那三位與攻城的真人。gamble 開頭、
    siege_start 開頭、muster_more 最後各驗一次（expect）：放手一搏打的是第一回合、攻城截止之前決戰還在集結，不成立就停。"""

    PLAYERS = {"秦朗月": "guan", "韓雲起": "huang", "柳青崖": "haoqiang", "葉寒舟": None}
    NEWBIE = "白小樓"  # Scenario.setup 註冊、不略過引導的那一位
    GAMBLER, LATE_GAMBLER, IDLER = "秦朗月", "韓雲起", "葉寒舟"
    # 伺服器假人：兩軍各二，擺在第二場決戰的大區（bots 那一段）
    BOT_SEATS = [("假戊", "guan"), ("假己", "guan"), ("假庚", "huang"), ("假辛", "huang")]
    # 第 6 批：六場攻城（名字：(攻方, 地點)）。A 官軍攻中立的南陽官道：守將（那裡最強的一路隊伍）守住；B 黃巾攻官軍的涿郡：攻下、易手；
    # C 集結中管理者取消（_cancel_siege）；D 集結中收季（_shelve_siege）；E 伺服器假人那一場：黃巾守住自己的新野（守城軍令記一次，_siege_guards）；
    # F 黃巾攻官軍的洛陽官道、那一區沒有人、一個人都沒到：作罷（siege.void_absent 之後照樣經 _settle_siege）。結果是跑出來的（照兩份程式同一套
    # 亂數），寫在這裡是情境走到哪幾支：守將守住、攻下易手、陣營守住、作罷、取消、季終收兵。每一場自己一個大區（D 在決戰收場之後才開）：同一個
    # 大區兩場以上一起集結的話加入鈕帶 @流水號，第 5 批那幾位的加入會被改掉
    SIEGES = {"A": ("guan", "nanyang_road"), "B": ("huang", "zhuo_county"), "C": ("huang", "xiaquyang"), "D": ("guan", "runan_wilds"),
              "E": ("guan", "xinye"), "F": ("huang", "luoyang_road"),
              "G": ("huang", "hilltop_wilds")}  # 第 7 批：決戰的大區（潁汝）裡多一場，黃巾與散人在那一區看得到兩場（加入鈕帶 @流水號）
    # 攻城的真人（名號：(陣營, 哪一場, 每一回合出哪一招)）：A 兩位官軍攻、一位散人助守【守軍】；B 黃巾一位攻（固守）、官軍一位守（強攻）；C 黃巾一位
    SIEGE_PLAYERS = {"程破軍": ("guan", "A", "強攻"), "方定遠": ("guan", "A", "奇襲"), "孟無涯": (None, "A", "固守"),
                     "杜飛沙": ("huang", "B", "固守"), "季長安": ("guan", "B", "強攻"), "譚小滿": ("huang", "C", "強攻")}
    SIEGE_BOT_SEATS = [("假壬", "guan"), ("假癸", "guan"), ("假子", "huang"), ("假丑", "huang")]  # E 那一場的假人：兩軍各二
    # 戰書緊接在開戰之後下（siege_open）、攻城的真人之後才建（siege_seat）：攻城的集結截止跟決戰的差不到一分鐘，siege_start 把時鐘推過攻城的截止時
    # 決戰才剛開打（season21 的長社火攻開季就開了集結、截止得更早，一樣在這一下開打）——決戰第一回合照第 5 批的樣子在 gamble 打
    # （第 7 批插進來的段落照 still 不吃這段時間；gamble 開頭 expect 驗）
    # 第 7 批：六位新人（名號：(陣營, 擺在哪)）。region＝那一場決戰的大區（spot）、hilltop＝荒丘（同一個大區，G 那一塊）、away＝那一場決戰的大區外（away_spot）。
    # 顧長風按加入、挑同伴、再想想、再按加入停在挑，後半才挑；莫問天按加入停在挑，開打了才挑（改成晚到）；江映雪（散人）臨時投效官軍再改投黃巾，
    # 後半到曹氏莊院投靠豪強；石破浪在荒丘看得到兩場、先按 G 那一場的 @ 停在挑同伴、再想想，照 @流水號加入決戰；嚴不悔、沐晚晴集結時在大區外，開打之後才到（晚到、晚到臨時投效）
    MUSTER_PLAYERS = {"顧長風": ("guan", "region"), "莫問天": ("guan", "region"), "江映雪": (None, "region"), "石破浪": ("huang", "hilltop"),
                      "嚴不悔": ("huang", "away"), "沐晚晴": (None, "away")}
    # 名下各一位同伴（秦朗月集結時照舊按「不派」：muster 那一段本來就這樣按；石破浪是審查之後加的：先按 G 那一場停在挑、再想想）
    ESCORTERS = ("秦朗月", "顧長風", "莫問天", "石破浪")
    AWAY_BOT = ("假寅", "guan")  # bots 那一段：名下一位同伴、站在大區外的官軍假人
    PHASES_FIRST = ["setup", "join", "seat", "look", "admin", "open", "siege_open", "siege_seat", "muster_seat", "muster", "muster_pick",
                    "muster_more", "siege_muster", "siege_cancel", "siege_start", "start", "late", "gamble"]
    PHASES_SECOND = ["narrate", "wander", "fight", "siege_end", "deliver", "muster_deliver", "reports", "restore", "admin_trial", "siege_after",
                     "bots", "siege_bots", "siege_shelve", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _battle_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        self.late_done = False
        self.stills = 0  # still() 疊了幾層：大於 0 時每一個請求都是第 7 批插進來的（begin 先挪期限）

    # ── 小工具 ──

    STEP_SECONDS = 10.0  # 這一軌一步只推十秒：決戰一回合最多等 180 秒（round_seconds），一步一分的話出招的請求還沒送齊回合就逾時了

    def begin(self) -> None:
        """同 Scenario.begin，只是一步 STEP_SECONDS（十秒）；同約戰那一軌，每個請求換一份空的勝算記憶（前半＋後半是兩個行程，集結中那幾位
        選單上的勝算字才對得上）。第 7 批插進來的請求（still 裡）先把決戰與攻城的期限往後挪這一步（hold）。"""
        STEP[0] += 1
        if self.stills:
            self.hold()
        CLOCK[0] = CLOCK0 + STEP[0] * self.STEP_SECONDS
        random.seed(STEP[0])
        self.server.GAMES.clear()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 步", None)

    def expect(self, ok: bool, what: str) -> None:
        """情境自己驗的前提：不成立就停、不往下比（審查 should：第 7 批插進來的段落吃掉了集結的時間，第 5、6 批決戰那一段的節奏悄悄變了，
        base 與 head 跑同一套段落，比對照樣相等，看不出來）。"""
        if not ok:
            raise RuntimeError(f"情境的前提不成立（第 {STEP[0]} 步）：{what}")

    @contextlib.contextmanager
    def still(self):
        """這一段裡的請求是第 7 批插進來的（審查 should）：決戰與攻城的時鐘不走——每一步之前把期限往後挪那一步（hold），集結截止與每一回合的
        逾時照第 5、6 批那幾段的請求算，跟沒有這幾段時一樣（集結那 30 分鐘、一回合 180 秒放不下第 7 批的幾十個請求：season21 的長社火攻
        開季就開了集結、截止最早，原本在第 7 批的段落裡就開打了；late 那九個請求排在開打與放手一搏之間，第一回合在 late 裡逾時）。"""
        self.stills += 1
        try:
            yield
        finally:
            self.stills -= 1

    def hold(self) -> None:
        """還沒收場的決戰與攻城：期限往後挪一步（battle_instance.shift_deadlines，管理者暫停再繼續的同一個做法：集結中挪集結截止、開打了挪這一回合
        開放的時間）。賽季的時鐘照走。都收場了（或還沒開）什麼都不寫。"""
        from tianxia import battle_instance

        b = self.world.get_battle()
        if (b is None or b.phase == "ended") and all(s.phase == "ended" for s in self.world.get_sieges()):
            return

        def fn(state) -> None:
            for x in ([state.active_battle] if state.active_battle is not None else []) + list(state.sieges):
                battle_instance.shift_deadlines(x, self.STEP_SECONDS)

        self.world.mutate(fn)

    def relogin(self, who: str) -> None:
        """同 Scenario.relogin；第 7 批的新人（MUSTER_PLAYERS）重新登入那一下照第 7 批插進來的請求算（still：narrate 那一段的 login_all）。"""
        with self.still() if who in self.MUSTER_PLAYERS else contextlib.nullcontext():
            super().relogin(who)

    def no_escort(self, who: str) -> None:
        """有挑同伴那一步就按「不派」。名下的同伴是第 7 批給的（ESCORTERS）：那一下照第 7 批插進來的請求算（still）。"""
        if "battle:escort:none" in self.ids(self.main(who)):
            with self.still() if who in self.ESCORTERS else contextlib.nullcontext():
                self.choose(who, "battle:escort:none")

    def skip_past(self, deadline: float) -> None:
        """時鐘推到下一個請求剛過 deadline（begin 的時刻是 CLOCK0 + 步數 × STEP_SECONDS）。"""
        self.skip(max(0, int((deadline - CLOCK0) // self.STEP_SECONDS) - STEP[0]))

    def target(self) -> tuple[str, str]:
        """管理者開的那一場：(管理者工具, 決戰 id)。"""
        return ("start_battle", "huangjin_showdown") if self.profile in ("none", "test") else ("start_showdown", "changshe_fire")

    def second(self) -> tuple[str, str]:
        """假人打的第二場（bots 那一段）：不帶設定照樣是黃巾決戰（收場了可以再開），時刻表的季開廣宗（另一個大區）。"""
        return ("start_battle", "huangjin_showdown") if self.profile in ("none", "test") else ("start_showdown", "guangzong")

    def spot(self, battle_id: str) -> str | None:
        """那一場決戰的大區裡挑一處（長社在潁汝就站長社，不然照 id 排第一個）；這份內容沒有那一場是 None。"""
        from tianxia import atlas

        definition = self.c.battles.get(battle_id)
        if definition is None or definition.region is None:
            return None
        spots = sorted(i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == definition.region)
        return "changshe" if "changshe" in spots else (spots[0] if spots else None)

    def battle_row(self, tag: str) -> None:
        """共用狀態裡那一場決戰此刻的樣子（整份的雜湊與看得懂的那幾格；整份資料庫每一段另有雜湊）。"""
        from tianxia import battle_instance

        b = self.world.get_battle()
        if b is None:
            emit(f"決戰 {tag}", None)
            return
        emit(f"決戰 {tag}", {
            "id": b.battle_id, "record": b.record_id, "phase": b.phase, "round": b.round_number, "act": b.act_index,
            "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin], "tales": [[t.round, t.name, t.won] for t in b.tales],
            "log": len(b.narrative_log), "unfinished": b.unfinished,
            "who": {n: [q.faction, q.eliminated, battle_instance.idle(q), q.acted_rounds] for n, q in sorted(b.participants.items())},
            "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()})

    def me(self, who: str, tag: str) -> None:
        """存檔裡決戰補送動到的那幾格：銀兩、經驗、名望、心得、這一季參戰幾場與首功、補過的決戰、戰報、行狀、最近的紀錄標題。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "stats": dict(sorted(p.stats.items())), "level": p.member.level, "exp": p.member.exp, "points": p.stat_points,
            "showdowns": p.showdowns, "top_merits": p.top_merits, "seen": p.battle_results_seen, "restored": p.showdowns_restored,
            "card": state.battle_card,
            "battles": [[r.id, r.kind, r.event, r.tier, r.side, r.notes, r.changes, r.gauge, len(r.log), r.battle_ref] for r in state.battles],
            "annals": [a.model_dump(mode="json") for a in p.annals][-6:], "journal": [e.title for e in state.journal][:10]})

    def join_pick(self, who: str, ids: dict[str, dict]) -> str | None:
        """集結時這個人按哪一顆：自己陣營的 battle:join；散人臨時投效官軍、豪強臨時投效黃巾（豪強分屬兩軍的季照引擎給的 join）。"""
        side = self.PLAYERS.get(who)
        live = sorted(i for i, o in ids.items() if (i.startswith("battle:join:") or i.startswith("battle:enlist:")) and o.get("enabled"))
        for want in (f"battle:join:{side}", "battle:enlist:guan" if side is None else "battle:enlist:huang"):
            if want in live:
                return want
        return live[0] if live else None

    def round(self, gamblers: dict[str, str]) -> None:
        """一回合：gamblers 裡的人放手一搏（/api/do/battle_text），掛機的那一位不按，其餘照回合數挑三招之一；回合沒結（第一回合在等掛機的）
        就把時鐘推過這一回合的期限、再輪詢一次（逾時代為固守，之後不再等他）。"""
        b = self.world.get_battle()
        if b is None or b.phase != "active":
            return
        n = b.round_number
        for who in self.PLAYERS:
            if who == self.IDLER:
                continue
            if who in gamblers:
                self.do(who, "battle_text", {"text": gamblers[who]})
                continue
            moves = sorted(i for i, o in self.ids(self.main(who)).items() if i.startswith("battle:act:") and o.get("enabled"))
            if moves:
                self.choose(who, moves[n % len(moves)])
        self.siege_round()  # 第 6 批：同時在打的攻城，攻城的真人也出這一回合（沒有開打中的攻城什麼都不打）
        b = self.world.get_battle()
        if b is not None and b.phase == "active" and b.round_number == n:
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.GAMBLER)
        self.battle_row(f"第 {n + 1} 回合之後")

    def tell(self, tag: str) -> None:
        """放手一搏的劇情：照伺服器出了鎖之後的那一條（server.narrate_once：A 鎖內開單、B 鎖外假模型一整批寫、C 鎖內補），寫到沒有等著的。"""
        for _ in range(4):
            self.begin()
            got = self.server.narrate_once(self.server.game_for(self.GAMBLER))
            emit(f"{tag}：補了幾句", got)
            if got is None:
                break
        self.main(self.GAMBLER)

    # ── 情境 ──

    def seat(self) -> None:
        """四個人擺在那一場決戰的大區（體力補滿、過了新手期）。這份內容沒有那一場（測試內容）就照原地補體力。第二幕放手一搏的那一位
        是女子（Scenario.setup 一律建男的）：補劇情的單子上有「女子」那一格，提示寫進輸出之後性別改了才比得出來。"""
        loc = self.spot(self.target()[1])
        for who in self.PLAYERS:
            self.place(who, loc)
        self.edit(self.LATE_GAMBLER, lambda p: setattr(p, "gender", "女"))
        emit(f"{self.LATE_GAMBLER} 改成女子", None)

    def look(self) -> None:
        """開戰之前：畫面上沒有戰局條、沒有攻城條、輸入框是空的；戰報頁是空的。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.call(self.GAMBLER, "GET", "/api/reports")
        self.do(self.GAMBLER, "battle_text", {"text": "火燒連營"})  # 沒有決戰：送不出去、模型一次都不叫

    def open(self) -> None:
        op, battle_id = self.target()
        self.do(ADMIN, op, {"id": battle_id})
        self.battle_row("開了集結")

    def muster(self) -> None:
        """集結中：每個人先看一次（集結中、選陣營加入）、按加入（有挑同伴那一步就不派），再看一次（你已加入、職位、還剩幾分）。"""
        for who in self.PLAYERS:
            pick = self.join_pick(who, self.ids(self.main(who)))
            emit(f"{who} 集結時按的", pick)
            if pick is None:
                continue
            self.choose(who, pick)
            self.no_escort(who)  # 秦朗月名下有第 7 批給的同伴：按「不派」那一下照第 7 批插進來的請求算
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.battle_row("集結中")

    def start(self) -> None:
        """集結截止：第一個輪詢的人把它推到開打（options 順便推進、一次請求只推一次）；每個人看開打的畫面（回合、三招的份量、輸入框）。"""
        b = self.world.get_battle()
        if b is not None and b.phase == "muster":
            self.skip_past(b.muster_deadline_real)
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.battle_row("開打")

    def gamble(self) -> None:
        """第一回合：官軍放手一搏、散人掛機（回合等到逾時、代為固守）、其餘出招；這一回合結算之後劇情還沒補（場景上是固定句，等
        narrate_once）——前半停在這裡。這一回合是第一回合（第一幕、還沒有一回合逾時），不然就停。"""
        b = self.world.get_battle()
        self.expect(b is None or (b.phase == "active" and b.round_number == 0 and b.act_index == 0),
                    "放手一搏打的是第一回合" + ("" if b is None else f"（此刻 {b.phase}、第 {b.round_number + 1} 回合、第 {b.act_index + 1} 幕）"))
        self.round({self.GAMBLER: "火燒連營，直搗敵陣"})
        self.main(self.GAMBLER)

    def narrate(self) -> None:
        self.login_all()
        self.tell("第一回合補劇情")

    def fight(self) -> None:
        """打到收場：第二幕的第一回合黃巾放手一搏、有等著補的劇情就補；其餘照回合數出招，掛機的一直不按。"""
        for _ in range(40):
            b = self.world.get_battle()
            if b is None or b.phase != "active":
                break
            gamblers = {}
            if b.act_index >= 1 and not self.late_done:
                gamblers, self.late_done = {self.LATE_GAMBLER: "繞到敵後，放火燒糧"}, True
            self.round(gamblers)
            b = self.world.get_battle()
            if b is not None and b.tales:
                self.tell(f"第 {b.round_number} 回合補劇情")
        self.battle_row("收場")

    def deliver(self) -> None:
        """收場之後每個人打 /api/main：下一次同步把那一場補到自己手上（江湖紀錄、戰報、軍餉、名望、行狀、戰功；「剛剛」是那一場的卡片與
        收場那一刻的戰局條）。序章裡的那一位不在名單上，什麼都不補。第一位要經同步才補到那一場的人（crossing_who）同步之前先擺 crossing
        （核心收接縫，全部拆包第 11 批）。"""
        who_x = self.crossing_who()
        for who in [*self.PLAYERS, self.NEWBIE]:
            if who == who_x:
                self.crossing(who)
            self.main(who)
            self.me(who, "收補送之後")

    def crossing_who(self) -> str:
        """名單上第一位還沒補到收場那一場的人：自己最後一手收了場的那一位在 _battle_choose 那一下就補了（_settle_showdown 叫補送，不經
        sync；第 11 批審查：原本擺在秦朗月身上，他那一則「長社火攻」不是 deliver_results 那一格補的，挪動那一格比不出差），其餘參戰的人
        要等自己下一次同步，才經 sync 的 deliver_results 補到。內容裡沒有決戰（測試內容）照舊是秦朗月。"""
        b = self.world.get_battle()
        if b is not None and b.phase == "ended":
            for who in self.PLAYERS:
                state = self.chars.load(who)
                if who in b.participants and state is not None and b.record_id not in state.player.battle_results_seen:
                    return who
        return self.GAMBLER

    def crossing(self, who: str) -> None:
        """同一次同步收好幾包的補送（核心收接縫，全部拆包第 11 批；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.3）：收場之後
        這個人（crossing_who：還沒補到那一場、這一下同步才經 deliver_results 補到的那一位）同步之前，季上替他擺一筆護衛補帳（還在 engine
        的 _deliver_guard_credits）、一則酒肆的風聲、一張他雇的過期殺手單。那一下同步依序補：決戰的補送（決戰包，deliver_results 的位置：
        補份量快照之後、玉璽碎片之前）→ 護衛 → 風聲、殺手單（酒肆包，deliver_notices 的位置：護衛之後、領地爭奪換天之前）。deliver 那一行
        me 的江湖紀錄標題看得出三格的先後：決戰的補送挪過護衛、挪到酒肆後面，酒肆那三個挪過護衛、挪到決戰前面，都抓得到；沒越過護衛的
        看不出來（決戰的補送只在補份量快照與護衛之間挪、越過玉璽碎片與改名那幾格，它們這一下什麼都不寫）。三個 deliver 不看酒肆開關，
        測試內容沒有酒肆也照擺照送；測試內容沒有決戰，只看得出護衛與酒肆兩格。"""
        from tianxia import figure_aid
        from tianxia.characters import name_key
        from tianxia.state import TavernHit, Whisper

        other = self.LATE_GAMBLER if who == self.GAMBLER else self.GAMBLER
        state = self.chars.load(who)
        place = state.player.location if state is not None else self.c.scenario.start_location
        now = CLOCK0 + STEP[0] * self.STEP_SECONDS

        def fn(s) -> None:
            s.guard_credits.setdefault(who, []).append(figure_aid.CREDIT_LINE.format(name="某人", who=other))
            s.tavern_whispers.setdefault(name_key(who), []).append(Whisper(kind="seek", who=other, place=place, time=s.time, named=True))
            s.tavern_hit_seq += 1
            s.tavern_hits.append(TavernHit(id=s.tavern_hit_seq, client=who, target=other, tier=0, price=20, place=place,
                                           placed_real=now - 7200, until_real=now - 60))

        self.world.mutate_season(fn)
        emit(f"季上替{who}擺一筆護衛補帳、一則風聲、一張過期的殺手單（同一下同步收三個位置的補送）", place)

    def reports(self) -> None:
        """戰報頁：列表、預設那一筆（決戰的完整戰況與收場那一刻的戰局條）、再點最舊的那一筆——這時每個人只有那一場決戰一筆，點的就是
        預設那一筆；列表裡決戰排在最上面、補回來的照時刻排進去，在 restore 那一段擺了兩筆尋常的戰報才走得到（審查 nit）。"""
        for who in self.PLAYERS:
            _, data = self.call(who, "GET", "/api/reports")
            rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
            for rid in rows[-1:]:
                self.call(who, "GET", f"/api/reports?id={rid}")

    def restore(self) -> None:
        """被洗掉的決戰戰報補回來（_restore_showdowns，一季查一次）：官軍那一位的決戰戰報從存檔拿掉、showdowns_restored 歸零，下一次同步
        照 battles 表重建一筆（軍餉與名望不再發，RESTORED_NOTE）。拿掉的同時擺兩筆尋常的戰報（收場前後各一分鐘）：補回來的那一筆要照
        收場時刻排進兩筆中間（restore_showdowns 的 sort），戰報頁的列表決戰排最上面，再點最舊的那一筆（審查 nit：原本每人只有一筆）。"""
        from tianxia import battlelog
        from tianxia.state import BattleRecord

        with self.world.action_lock():
            state = self.chars.load(self.GAMBLER)
            if state is not None:
                gone = [r for r in state.battles if r.kind in battlelog.SHOWDOWN_KINDS]
                state.battles = [r for r in state.battles if r.kind not in battlelog.SHOWDOWN_KINDS]
                at = gone[0].time if gone else state.world.time
                for dt in (60.0, -60.0):  # 存檔裡新的在前
                    state.battle_seq += 1
                    state.battles.append(BattleRecord(id=state.battle_seq, time=at + dt, location="某地", kind="train", opponent="山賊",
                                                      ours=[], tier="大勝", our_power=1.0, difficulty=1.0))
                state.player.showdowns_restored = 0
                self.chars.save(state)
        self.main(self.GAMBLER)
        self.me(self.GAMBLER, "補回戰報之後")
        _, data = self.call(self.GAMBLER, "GET", "/api/reports")
        rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
        for rid in rows[-1:]:
            self.call(self.GAMBLER, "GET", f"/api/reports?id={rid}")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy，random.Random(7)、時鐘一輪推一分）：另開一場（second），四個假人擺在那一場的大區，跑到加入、出招
        （battle_tick）、收場，收場之後再跑三輪就停——這三輪裡輪到動的假人才同步、收到補送（week7、none 只有一位，weekend、season21 三位；
        審查 nit），其餘的在換季之後（season 那一段）同步一次，走 file_showdown 上一季的那一支。整季機器人（bot.play_season，week7、種子 5）：observe 第一步替它投靠官軍、擺進長社、開一場長社火攻，
        之後每一步把它的現實時鐘推一分，讓它自己打完一場。測試內容沒有決戰：略過。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        op, battle_id = self.second()
        loc = self.spot(battle_id)
        if loc is None:
            emit("這份內容沒有決戰：假人那一段略過", None)
            return
        self.do(ADMIN, op, {"id": battle_id})
        self.battle_row("假人那一場開了集結")
        for i, (name, side) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        away = self.away_bot(battle_id, 41 + len(self.BOT_SEATS))  # 第 7 批：大區外、名下有同伴的那一位（趕路、挑同伴）
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(7), clock=lambda: CLOCK[0])
        online = server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))} | away
        # 擺好的四個一直在線（作息照種子，可能正好不在）；一輪動不動照舊擲 act_chance（集結三十分鐘夠他們走到「加入」），出招照 battle_tick
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_BATTLE_TICKS", "90"))):
                STEP[0] += 5  # 一輪推一分（這一軌一步十秒）
                self.begin()
                for report in (runner.tick(), runner.battle_tick()):
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                b = self.world.get_battle()
                if b is not None and b.phase == "ended" and totals["after_end"] >= 3:
                    break
                if b is not None and b.phase == "ended":
                    totals["after_end"] += 1
        finally:
            server_bots.is_online = online
        self.battle_row("假人那一場")
        states = self.chars.all(bots_only=True)
        emit("決戰假人 一輪一輪", dict(sorted(totals.items())))
        emit("決戰假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("決戰假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        for s in states:
            self.me(s.player.name, "假人收補送之後")
        if self.profile == "week7":
            self.season_bot()

    def season_bot(self) -> None:
        """整季機器人（bot.play_season）打一場：自己一個資料庫（這一軌的資料庫旁邊），種子 5、SB_BATTLE_PLAY_STEPS 步。"""
        from collections import Counter

        from tianxia import bot
        from tianxia.content import load_content
        from tianxia.sqlite_world import open_world
        from tianxia.world import open_showdown

        path = self.db.with_name(self.db.stem + "-play.db")
        for suffix in ("", "-wal", "-shm", "-push.sqlite"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        content = load_content(self.root / "content", profile=self.profile)
        world = open_world(path)
        spot = self.spot("changshe_fire")
        seen = {"opened": False}

        def observe(g) -> None:
            g.now += 60.0  # 現實時鐘一步推一分（play_season 自己不推）：集結會截止、回合會逾時
            if seen["opened"] or g.state.world.ended:
                return
            seen["opened"] = True
            p = g.state.player
            p.faction, p.location, p.journey = "guan", spot, None
            p.visited.add(spot)
            open_showdown(g.world, g.content, "changshe_fire", g.now)
            g.state.world = g.world.get_season()

        game = bot.play_season(content, seed=5, max_steps=int(os.environ.get("SB_BATTLE_PLAY_STEPS", "160")), world=world, now=CLOCK0,
                               observe=observe)
        battle = world.get_battle()
        emit("整季機器人的決戰", None if battle is None else {
            "phase": battle.phase, "round": battle.round_number, "outcome": battle.outcome_title,
            "who": sorted(battle.participants), "sha": hashlib.sha256(battle.model_dump_json().encode("utf-8")).hexdigest()})
        emit("整季機器人 紀錄標題", dict(sorted(Counter(e.title for e in game.state.journal).items())))
        emit("整季機器人 戰報", [[r.kind, r.event, r.tier, r.notes, r.changes] for r in game.state.battles if r.kind == "showdown"])
        emit("整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
        emit("整季機器人 資料庫", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest())

    def season(self) -> None:
        """收季、開下一季：補過的決戰照帶（battle_results_seen，不再補一次）、這一季參戰幾場與首功跟著新角色重來。假人那一場收場之後
        還沒同步過的假人，換季之後第一次同步才補到（審查 nit）：file_showdown 上一季那一支——紀錄與戰報標「第 N 季・」、不發軍餉、
        行狀接在存起來的上一季後面（add_saved_annal）。"""
        from tianxia.engine import Game

        self.do(ADMIN, "end_season")
        for who in self.PLAYERS:
            self.main(who)
        self.resting()  # 第 6 批：休季時管理者的決戰工具一律被擋；季終收兵的那一場攻城（D）
        self.do(ADMIN, "next_season")
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "換季之後")
        last = self.world.get_season_number() - 1
        for name, _ in self.BOT_SEATS:  # 照假人程式的做法：鎖裡讀存檔、建 Game、同步、存回去（測試內容沒有擺假人：略過）
            self.begin()
            with self.world.action_lock():
                state = self.chars.load(name)
                if state is None:
                    continue
                g = Game(self.c, state, random.Random(STEP[0]), self.world)
                g.client = None
                g.sync(CLOCK[0])
                self.chars.save(g.state)
            self.me(name, "換季之後同步")
            book = self.world.biography(last, name)
            emit(f"{name} 第 {last} 季存起來的行狀", None if book is None else [[a["kind"], a["text"]] for a in book["annals"]][-4:])

    # ── 第 6 批：管理者的決戰工具（admin、resting）──

    def live_showdown(self) -> bool:
        b = self.world.get_battle()
        return b is not None and b.phase != "ended"

    def trial(self) -> str | None:
        """admin_trial 開了再取消的那一場（立刻開戰的 id）：不帶設定是黃巾決戰（world.start_battle 那一支）；時刻表的季是宛城（時刻表那一支：
        world.open_showdown）——還不知道是哪一版的季（weekend、week7）先按開它被擋（要等張曼成那一件結算），「定結果」定了張曼成（GET /api/admin
        的 results 第一個），那一版才出現在立刻開戰的選單上；season21 開季就知道了。測試內容沒有決戰是 None。"""
        if not self.c.battles:
            return None
        if self.target()[0] == "start_battle":
            return self.target()[1]
        from tianxia import timetable

        event = timetable.find(self.c, "wancheng")
        _, data = self.call(ADMIN, "GET", "/api/admin")
        found = next((b["id"] for b in data.get("battles", []) if b["id"].startswith(event.id)), None)
        if found is not None:
            return found
        self.do(ADMIN, "start_showdown", {"id": event.id})  # 要等張曼成那一件結算了才知道是哪一版
        value = next((r["value"] for r in data.get("results", []) if r["value"].startswith(f"{event.version_from}|")), None)
        if value is not None:
            eid, key = value.split("|", 1)
            self.do(ADMIN, "resolve_event", {"id": eid, "key": key})
        _, data = self.call(ADMIN, "GET", "/api/admin")
        return next((b["id"] for b in data.get("battles", []) if b["id"].startswith(event.id)), None)

    def admin(self) -> None:
        """管理者的決戰工具，開戰之前按得到的那幾種被拒（GET /api/admin 看立刻開戰的選單〔admin_battles〕、三場大戲的鈕〔admin_showdowns、
        _showdown_refusal〕、時刻表那幾列〔cancelled_showdowns〕）：不是管理者按開戰（伺服器擋）；暫停中按開戰、開這一場、取消決戰
        （_admin_refusal），繼續；立刻開戰沒有這一場；開這一場時刻表上沒有（不帶設定：這一季沒有時刻表）；沒有進行中的決戰時取消決戰被擋——
        season21 的長社火攻開季就開了集結：改成另開廣宗被擋（已經有一場戰鬥在進行），不取消它（第 5 批那一場照打）。成的那幾顆在 open（開這一場、
        立刻開戰）、admin_trial（開了再取消）、bots（開這一場）。"""
        op, target = self.target()
        self.call(ADMIN, "GET", "/api/admin")
        self.do(self.GAMBLER, "start_battle", {"id": target})  # 不是管理者：伺服器擋
        self.do(ADMIN, "pause_clock")
        self.do(ADMIN, "start_battle", {"id": target})
        self.do(ADMIN, "start_showdown", {"id": target})
        self.do(ADMIN, "cancel_battle")
        self.do(ADMIN, "resume_clock")
        self.do(ADMIN, "start_battle", {"id": "no_such_battle"})
        self.do(ADMIN, "start_showdown", {"id": "no_such_event"})
        if self.live_showdown():
            second = self.second()[1]
            self.do(ADMIN, "start_battle", {"id": second})
            self.do(ADMIN, "start_showdown", {"id": second})
        else:
            self.do(ADMIN, "cancel_battle")

    def admin_trial(self) -> None:
        """開了再取消（第 5 批那一場收場、補送完之後）：取消決戰被擋（沒有進行中的）、開這一場長社被擋（已經結算了；不帶設定：沒有時刻表）；
        試開一場（trial），再開一次、開別場都擋（已經有一場戰鬥在進行、已經開打過了），取消（不算勝負、天下大事一句、記進 showdowns_cancelled），
        之後開這一場宛城被擋（開打後被取消，要收尾用定結果）；前後 GET /api/admin（時刻表那幾列的「開打後取消」）。"""
        op, target = self.target()
        self.do(ADMIN, "cancel_battle")
        self.do(ADMIN, "start_showdown", {"id": target})
        trial = self.trial()
        emit("試開的那一場", trial)
        if trial is None:
            return
        self.do(ADMIN, "start_battle", {"id": trial})
        # 那一場的大區裡有一位加入（不帶設定：秦朗月在潁川汝南；時刻表的季：A 那一場打完的程破軍在南陽）：取消之後他補一則「不算勝負」——
        # file_showdown 沒打完那一支（第 5 批的情境走不到，見 docstring 開頭）
        joiner = self.GAMBLER if op == "start_battle" else next(iter(self.SIEGE_PLAYERS))
        joined = joiner in self.clients
        if joined:
            ids = self.ids(self.main(joiner))
            pick = next((i for i in sorted(ids) if i.startswith("battle:join:") and ids[i].get("enabled")), None)
            emit(f"{joiner} 試開那一場按的", pick)
            if pick is not None:
                self.choose(joiner, pick)
                self.no_escort(joiner)
        self.battle_row("試開")
        self.do(ADMIN, "start_battle", {"id": trial})
        if op == "start_showdown":
            self.do(ADMIN, "start_battle", {"id": self.second()[1]})
            self.do(ADMIN, "start_showdown", {"id": self.second()[1]})
            self.do(ADMIN, "start_showdown", {"id": "wancheng"})
        self.call(ADMIN, "GET", "/api/admin")
        self.do(ADMIN, "cancel_battle")
        self.battle_row("取消之後")
        self.call(ADMIN, "GET", "/api/admin")
        if op == "start_showdown":
            self.do(ADMIN, "start_showdown", {"id": "wancheng"})
        if joined:
            self.main(joiner)
            self.me(joiner, "試開那一場取消之後")

    def resting(self) -> None:
        """收季之後（休季）管理者的決戰工具一律被擋（賽季沒有在進行）；季終收兵的那一場攻城（D）收起來了，秦朗月補一則不算勝負。"""
        op, target = self.target()
        self.do(ADMIN, "start_battle", {"id": target})
        self.do(ADMIN, "start_showdown", {"id": target})
        self.do(ADMIN, "cancel_battle")
        if self.siege_on():
            self.siege_row("季終收兵之後", ("D",))
            self.me(self.GAMBLER, "季終收兵之後")

    # ── 第 6 批：攻城（地盤開著的季；SIEGES、SIEGE_PLAYERS）──

    def siege_on(self) -> bool:
        from tianxia import territory

        return territory.on(self.c)

    def recruit(self, who: str, side: str | None, loc: str) -> bool:
        """攻城的真人：兩軍的照 Scenario.newcomer（註冊、建角色、略過引導、投靠）；散人只註冊、建角色、略過引導。擺到 loc（體力補滿、過了新手期）。"""
        if side is not None:
            if not self.newcomer(who, side):
                return False
        else:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        return self.place(who, loc)

    def slot_of(self, key: str):
        """時程表上那一場（最後排的那一筆：SIEGES 的那一塊、攻方有那一軍）；沒有是 None。"""
        side, loc = self.SIEGES[key]
        season = self.world.get_season()
        if season.conquest is None:
            return None
        return next((s for s in reversed(season.conquest.schedule) if s.loc == loc and side in s.attackers), None)

    def siege_row(self, tag: str, keys=None) -> None:
        """這幾場攻城此刻的樣子：時程表那一筆（狀態、流水號、誰拿下）、那一塊歸誰與兩軍的進度、那一場（還在共用狀態裡的，或已經拿掉、
        從 battles 表讀的）的回合、戰局、結果、名單、SiegeInfo 與整份的雜湊。"""
        from tianxia import conquest

        season = self.world.get_season()
        live = {b.record_id: b for b in self.world.get_sieges()}
        out = {}
        for key in keys or self.SIEGES:
            slot = self.slot_of(key)
            if slot is None:
                continue
            loc = self.SIEGES[key][1]
            b = None if slot.record_id is None else live.get(slot.record_id) or self.world.ended_battle(slot.record_id)
            out[key] = {
                "slot": [slot.id, slot.status, slot.record_id, slot.winner, slot.attackers],
                "holder": conquest.holder(season, self.c, loc),
                "bars": {s: round(v, 3) for s, v in sorted(conquest.bars(season, loc).items())},
                "battle": None if b is None else {
                    "id": b.battle_id, "phase": b.phase, "round": b.round_number, "trend": b.trend,
                    "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin], "unfinished": b.unfinished,
                    "who": {n: [q.faction, q.eliminated, q.acted_rounds] for n, q in sorted(b.participants.items())},
                    "siege": None if b.siege is None else b.siege.model_dump(mode="json"),
                    "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()},
            }
        emit(f"攻城 {tag}", out)

    def siege_pick(self, who: str, ids: dict[str, dict]) -> str | None:
        """攻城集結時這個人按哪一顆：兩軍的按自己那一軍的加入、散人按助守【守軍】；同一個大區有兩場打得進去時鈕帶「@流水號」，按自己那一場的。"""
        side, key, _ = self.SIEGE_PLAYERS[who]
        slot = self.slot_of(key)
        rid = None if slot is None else slot.record_id
        live = sorted(i for i, o in ids.items() if (i.startswith("battle:join:") or i.startswith("battle:enlist:")) and o.get("enabled"))
        mine = [i for i in live if "@" not in i or i.endswith(f"@{rid}")]
        if side is not None:
            return next((i for i in mine if i.split("@")[0] == f"battle:join:{side}"), mine[0] if mine else None)
        return next((i for i in mine if "助守" in ids[i].get("label", "")), mine[0] if mine else None)

    def siege_round(self) -> None:
        """攻城這一回合：還在場上的攻城真人各出一招（SIEGE_PLAYERS 寫的那一招；鈕上沒有就照第一顆）。沒有開打中的攻城什麼都不打。"""
        if not self.siege_on():
            return
        live = [b for b in self.world.get_sieges() if b.phase == "active"]
        for who, (_, _, move) in self.SIEGE_PLAYERS.items():
            b = next((x for x in live if who in x.participants), None)
            if b is None or b.participants[who].eliminated:
                continue
            ids = self.ids(self.main(who))
            acts = sorted(i for i, o in ids.items() if i.startswith("battle:act:") and o.get("enabled"))
            if acts:
                self.choose(who, next((i for i in acts if f"（{move}" in ids[i].get("label", "")), acts[0]))
        if live:
            self.siege_row("這一回合之後", ("A", "B"))

    def siege_seat(self) -> None:
        """攻城的真人建好角色（一位十來個請求，攻城與決戰都還在集結），擺在各自那一場的地點。"""
        if not self.siege_on():
            return
        for who, (side, key, _) in self.SIEGE_PLAYERS.items():
            self.recruit(who, side, self.SIEGES[key][1])
        self.siege_row("人到齊了", ("A", "B", "C", "F"))

    def siege_open(self) -> None:
        """開戰之後管理者立刻下四張戰書（admin_conquest_letter：不看階與門檻、集結馬上開）——A、B、C、F；下一個同步的人（GET /api/admin）把它們
        開成集結（siege.open_waiting）。F 在洛陽，那一區沒有人：沒有人加入。"""
        if not self.siege_on():
            emit("這一季沒有地盤：攻城那幾段略過", None)
            return
        for key in ("A", "B", "C", "F"):
            side, loc = self.SIEGES[key]
            self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        self.call(ADMIN, "GET", "/api/admin")  # 領地爭奪那一組的 sieges（取消一場攻城的下拉選單）
        self.siege_row("開了集結", ("A", "B", "C", "F"))

    def siege_muster(self) -> None:
        """攻城集結中：每一位看一次、按加入（散人按助守；有挑同伴那一步就不派），再看一次。"""
        if not self.siege_on():
            return
        for who in self.SIEGE_PLAYERS:
            pick = self.siege_pick(who, self.ids(self.main(who)))
            emit(f"{who} 攻城集結時按的", pick)
            if pick is None:
                continue
            self.choose(who, pick)
            self.no_escort(who)
        for who in self.SIEGE_PLAYERS:
            self.main(who)
        self.siege_row("集結中", ("A", "B", "C"))

    def siege_cancel(self) -> None:
        """集結中管理者「取消一場攻城」（admin_conquest_cancel → _cancel_siege → _shelve_siege：不算勝負、不發軍餉、不易手），C 那一位補一則；
        再按一次被擋（已經作罷）。"""
        if not self.siege_on():
            return
        slot = self.slot_of("C")
        if slot is None:
            emit("C 那一場沒排上", None)
            return
        self.do(ADMIN, "conquest_cancel", {"id": slot.id})
        self.do(ADMIN, "conquest_cancel", {"id": slot.id})
        self.main("譚小滿")
        self.me("譚小滿", "攻城取消之後")
        self.siege_row("取消之後", ("C",))

    def siege_start(self) -> None:
        """攻城的集結截止（戰書比決戰晚幾步下，截止也晚幾步）：時鐘推過最晚的那一場，攻城的真人各看一次——第一個同步的人把決戰與每一場攻城都
        推到開打（_battle_status：先決戰、再每一場攻城各推一次，_tick_siege；沒人到的作罷）；start 那一段接著看決戰開打的畫面。
        到這裡為止決戰還在集結（season21 的長社火攻開季就開了集結、截止最早：集結那幾段要放得進去），不然就停。"""
        b = self.world.get_battle()
        self.expect(b is None or b.phase == "muster", f"攻城截止之前決戰還在集結（此刻 {None if b is None else b.phase}）")
        if not self.siege_on():
            return
        mustering = [b for b in self.world.get_sieges() if b.phase == "muster"]
        if mustering:
            self.skip_past(max(b.muster_deadline_real for b in mustering))
        for who in self.SIEGE_PLAYERS:
            self.main(who)
        self.siege_row("開打", ("A", "B", "F"))

    def siege_end(self) -> None:
        """攻城打到收場（決戰收場時還沒收場的：照回合出招，回合沒結就把時鐘推過期限）：A 守將守住、B 攻下易手；收場之後攻城的真人各打一次
        /api/main 收補送（戰報 kind siege、軍餉與貢獻乘 pay_share），存檔那幾格寫進輸出。"""
        if not self.siege_on():
            return
        first = next(iter(self.SIEGE_PLAYERS))
        for _ in range(12):
            live = [b for b in self.world.get_sieges() if b.phase != "ended"]
            if not live:
                break
            before = {b.record_id: b.round_number for b in live}
            self.siege_round()
            stuck = [b for b in self.world.get_sieges() if b.phase == "active" and before.get(b.record_id) == b.round_number]
            if stuck:
                self.skip_past(max(b.round.opened_real + self.c.battles[b.battle_id].round_seconds for b in stuck))
                self.main(first)
        self.siege_row("收場")
        for who in self.SIEGE_PLAYERS:
            self.main(who)
            self.me(who, "攻城收補送之後")

    def siege_after(self) -> None:
        """易手之後的地盤與管理者那一頁：GET /api/admin（長社結算了、宛城開打後取消；領地爭奪那一組的此刻歸誰、冷卻）、輿圖的狀態
        （/api/map/state）、戰報頁攻城那一筆；替黃巾再對涿郡下一張戰書被擋（B 攻下之後已經是黃巾的了）。"""
        self.call(ADMIN, "GET", "/api/admin")
        if not self.siege_on():
            return
        self.call(next(iter(self.SIEGE_PLAYERS)), "GET", "/api/map/state")
        for who in self.SIEGE_PLAYERS:
            _, data = self.call(who, "GET", "/api/reports")
            rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
            for rid in rows[:1]:
                self.call(who, "GET", f"/api/reports?id={rid}")
        side, loc = self.SIEGES["B"]
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})

    def siege_bots(self) -> None:
        """伺服器假人打一場攻城（照 bots 那一段的寫法：BotRunner＋bot_policy，random.Random(9)、時鐘一輪推一分）：E 官軍攻黃巾的新野，
        四個假人（兩軍各二）擺在那一塊，管理者下戰書，跑到加入、出招（battle_tick）、收場，收場之後再跑三輪就停。"""
        if not self.siege_on():
            emit("這一季沒有地盤：攻城的假人那一段略過", None)
            return
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        side, loc = self.SIEGES["E"]
        for i, (name, faction) in enumerate(self.SIEGE_BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(20 + i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=faction, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(9), clock=lambda: CLOCK[0])
        online = server_bots.is_online
        seeds = {61 + i for i in range(len(self.SIEGE_BOT_SEATS))}
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_SIEGE_TICKS", "90"))):
                STEP[0] += 5  # 一輪推一分（這一軌一步十秒）
                self.begin()
                for report in (runner.tick(), runner.battle_tick()):
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                slot = self.slot_of("E")
                done = slot is not None and slot.status in ("done", "void")
                if done and totals["after_end"] >= 3:
                    break
                if done:
                    totals["after_end"] += 1
        finally:
            server_bots.is_online = online
        self.siege_row("假人那一場", ("E",))
        names = {n for n, _ in self.SIEGE_BOT_SEATS}
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("攻城假人 一輪一輪", dict(sorted(totals.items())))
        emit("攻城假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("攻城假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        for s in states:
            self.me(s.player.name, "假人攻城收補送之後")

    def siege_shelve(self) -> None:
        """季終收兵那一場（D）：官軍攻中立的汝南荒野，秦朗月擺過去加入；集結中就收季（season 那一段，admin_end_season → _shelve_siege）。"""
        if not self.siege_on():
            return
        side, loc = self.SIEGES["D"]
        self.place(self.GAMBLER, loc)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        ids = self.ids(self.main(self.GAMBLER))
        pick = next((i for i in sorted(ids) if i.split("@")[0] == f"battle:join:{side}" and ids[i].get("enabled")), None)
        emit(f"{self.GAMBLER} 季終之前加入的", pick)
        if pick is not None:
            self.choose(self.GAMBLER, pick)
            self.no_escort(self.GAMBLER)
        self.siege_row("季終之前", ("D",))

    # ── 第 7 批：集結、投效、挑同伴（MUSTER_PLAYERS、ESCORTERS、AWAY_BOT）──

    def enroll(self, who: str, side: str | None) -> None:
        """一位新人直接建進資料庫（同假人那一段：Game.new graduated、開局待選的事件選掉、過了新手期；兩軍的人直接記陣營）、綁一個帳號，
        再照 API 登入——一位只花兩步，集結那 30 分鐘才放得下第 7 批的幾段（照 API 註冊、略過引導、投靠一位要十來步）。"""
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        self.begin()
        g = Game.new(self.c, who, rng=random.Random(STEP[0]), world=self.world, graduated=True, sex="男")
        g.client = None
        g.sync(CLOCK[0])
        for _ in range(6):  # 開局待選的事件：選掉
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            g.choose(first)
        p = g.state.player
        p.tutorial_step = len(self.c.tutorial.steps)
        p.joined_at = -1.0e9
        if side is not None and any(f.id == side for f in self.c.scenario.factions):
            p.faction = side
        self.passwords[who] = "pw-" + self.login_of(who)
        store = AccountStore(self.world.db)
        with self.world.db.transaction():
            self.chars.save(g.state)
            store.register(self.login_of(who), self.passwords[who])
            store.bind_character(self.login_of(who), who)
        emit(f"{who} 建進資料庫", {"faction": p.faction, "location": p.location})
        self.clients[who] = self.TestClient(self.server.app)
        self.call(who, "POST", "/api/login", {"login": self.login_of(who), "password": self.passwords[who]})

    def mate_for(self, side: str | None) -> str | None:
        """還沒有主的同伴裡挑一位（照 id 排第一個；不是大勢人物、陣營寫的是 side 或沒寫）；歷史武將同行關著（測試內容）是 None。"""
        from tianxia import roster

        if not roster.on(self.c):
            return None
        return next((cid for cid in sorted(self.c.characters) if cid not in self.c.figures and self.c.characters[cid].side in (None, side)
                     and self.world.get_companion(cid).owner is None), None)

    def give_mate(self, who: str, side: str | None) -> None:
        """名下一位同伴（招進來、放進隊伍、情誼 80），同 tests/battle/test_companions_battle._ride_in。"""
        cid = self.mate_for(side)
        if cid is None:
            emit(f"{who} 名下的同伴（歷史武將同行關著）", None)
            return
        ok = self.world.try_recruit(cid, who, cap=3)

        def fn(p) -> None:
            if cid not in p.team:
                p.team.append(cid)
            p.affinities[cid] = 80

        self.edit(who, fn)
        emit(f"{who} 名下的同伴", [cid, ok])

    def mates(self, who: str, tag: str) -> None:
        """同伴那幾格：隊伍、情誼、減過了沒（parted_done）、還在挑的那一下（escort_pick），全服那一份的主人與從誰身邊回江湖。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        cids = sorted(set(p.team) | set(p.affinities) | {c for c, pr in self.world.companions().items() if who in (pr.owner, *pr.parted_from)})
        emit(f"{who} 同伴 {tag}", {
            "team": list(p.team), "affinities": {c: p.affinities.get(c) for c in cids}, "parted_done": list(p.parted_done),
            "escort_pick": p.escort_pick,
            "world": {c: [self.world.get_companion(c).owner, list(self.world.get_companion(c).parted_from)] for c in cids}})

    def escorts_row(self, tag: str) -> None:
        """那一場決戰上每一位隨你出陣的同伴（份量、氣血、敗走、回江湖了沒）與每個人站哪一邊、在不在場（away）。"""
        b = self.world.get_battle()
        emit(f"決戰的同伴與在場 {tag}", None if b is None else {
            n: [q.faction, q.away, None if q.escort is None else [q.escort.cid, q.escort.score, round(q.escort.neili, 1), q.escort.fallen_round,
                                                                   q.escort.released]]
            for n, q in sorted(b.participants.items())})

    def showdown_ref(self) -> int | None:
        b = self.world.get_battle()
        return None if b is None else b.record_id

    def pick_of(self, ids: dict[str, dict], want: str) -> str | None:
        """選單上那一顆（want 是不帶 @ 的 id）：同一個大區兩場以上時鈕帶「@流水號」，挑決戰那一場的；按不下去的不算。"""
        rid = self.showdown_ref()
        return next((i for i in sorted(ids) if i.split("@")[0] == want and ids[i].get("enabled")
                     and ("@" not in i or i.endswith(f"@{rid}"))), None)

    def press(self, who: str, want: str, tag: str) -> str | None:
        ids = self.ids(self.main(who))
        pick = self.pick_of(ids, want)
        emit(f"{who} {tag}", pick)
        if pick is not None:
            self.choose(who, pick)
        return pick

    def away_spot(self) -> str | None:
        """大區外的一處：照 id 排第一個、不在那一場決戰的大區（審查 should：原本連每一場攻城的大區也避開，攻城開著的季五個大區全佔滿——
        決戰與 G 在潁汝、A 南陽、B 幽州、C 冀州、F 洛陽——一處都找不到、照舊站在潁川〔潁汝〕，「集結時人在大區外」只有不帶設定走到）。
        正式內容排第一的是冀州的白馬津：攻城開著的季那裡有 C 在集結（集結中就取消、不開打），嚴不悔、沐晚晴站在那裡不按 C 的鈕、不會加進 C
        （集結截止不拉旁人進來，battle_instance.close_muster 只分已報名、沒選邊的人）。那一場決戰有大區、卻找不到大區外的一處就停（expect）。"""
        from tianxia import atlas

        def region(loc: str | None) -> str | None:
            r = atlas.region_of(self.c, loc) if loc in self.c.locations else None
            return None if r is None else r.id

        d = self.c.battles.get(self.target()[1])
        busy = d.region if d is not None else None
        found = next((i for i in sorted(self.c.locations) if region(i) != busy), None)
        emit("大區外的一處", found)
        self.expect(d is None or d.region is None or found is not None, "那一場決戰的大區外找得到一處（嚴不悔、沐晚晴集結時站在那裡）")
        return found

    @_still
    def muster_seat(self) -> None:
        """第 7 批的六位新人建好、擺好（region：那一場決戰的大區；hilltop：荒丘，同一個大區；away：那一場決戰的大區外）；秦朗月、顧長風、
        莫問天、石破浪名下各一位同伴（歷史武將同行開著的季）。"""
        spots = {"region": self.spot(self.target()[1]), "hilltop": "hilltop_wilds", "away": self.away_spot()}
        for who, (side, where) in self.MUSTER_PLAYERS.items():
            self.enroll(who, side)
            self.place(who, spots[where])
        for who in self.ESCORTERS:
            self.give_mate(who, self.PLAYERS.get(who, self.MUSTER_PLAYERS.get(who, (None,))[0]))

    @_still
    def muster_pick(self) -> None:
        """集結中第 7 批的加入那幾種與被拒的路——攻城開著的季先在潁汝多開一場（G：黃巾攻中立的荒丘）：黃巾與散人站在那一區看得到兩場、
        加入與投效的鈕帶 @流水號（_battle_menu），官軍那一格是守將、站不進去。
        顧長風：按加入 → 挑同伴那一步（名下每一位一顆、「不派」「再想想」）→ 再想想 → 再按加入，停在挑；莫問天：按加入，停在挑。
        江映雪（散人）：臨時投效官軍 → 改投黃巾。石破浪：先按一顆壞掉的 @，再按 G 那一場的 @（名下有同伴：停在挑、escort_pick 記著 @G）→
        再想想，再照決戰那一場的 @ 加入（不派）。被拒：韓雲起按官軍的加入（不在選單上）、
        沐晚晴在大區外按投效（看不到戰場）。集結一軌的前半停在這一段之後。"""
        if self.siege_on():
            side, loc = self.SIEGES["G"]
            self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
            self.call(ADMIN, "GET", "/api/admin")  # 下一個同步的人把它開成集結
            self.siege_row("潁汝多一場", ("G",))
        who = "顧長風"
        pick = self.press(who, "battle:join:guan", "集結時按的")
        if pick is not None and "battle:escort:back" in self.ids(self.main(who)):
            self.choose(who, "battle:escort:back")
            self.main(who)
            self.choose(who, pick)
        self.mates(who, "按了加入、停在挑")
        self.press("莫問天", "battle:join:guan", "集結時按的")
        self.mates("莫問天", "按了加入、停在挑")
        for want in ("battle:enlist:guan", "battle:enlist:huang"):
            if self.press("江映雪", want, "集結時按的") is not None and "battle:escort:none" in self.ids(self.main("江映雪")):
                self.choose("江映雪", "battle:escort:none")
        who = "石破浪"
        emit(f"{who} 看到的戰鬥鈕", sorted(i for i in self.ids(self.main(who)) if i.startswith("battle:")))
        self.choose(who, "battle:join:huang@abc")  # 壞掉的流水號：不在選單上
        g = self.slot_of("G") if self.siege_on() else None
        if g is not None and g.record_id is not None:
            # 照 @流水號按 G 那一場（不是排第一的決戰：審查 nit，按 @1 的話不帶流水號也落在同一場，@ 整個被忽略也比不出來）——名下有同伴，
            # 停在挑，記下的那一下帶著 @G（PlayerState.escort_pick）；再想想，回頭照決戰那一場的 @ 加入
            self.choose(who, f"battle:join:huang@{g.record_id}")
            self.mates(who, "按了 G 那一場的加入、停在挑")
            self.choose(who, "battle:escort:back")
        self.press(who, "battle:join:huang", "集結時按的")
        self.no_escort(who)
        self.choose("韓雲起", "battle:join:guan")  # 只能站自己陣營那一邊：選單上沒有
        self.main("沐晚晴")
        # 人在大區外：看不到戰場、沒有決戰的投效鈕。按的是決戰那一顆在潁汝的 id（攻城開著的季潁汝有決戰與 G 兩場，鈕帶 @流水號）——她站的冀州
        # 有 C 在集結，不帶 @ 的那一顆是 C 的，按了就加進 C
        self.choose("沐晚晴", "battle:enlist:guan" + (f"@{self.showdown_ref()}" if self.siege_on() else ""))
        self.battle_row("第 7 批的人加入之後")
        self.escorts_row("集結中")

    @_still
    def muster_more(self) -> None:
        """集結一軌的後半從這裡接（重新登入）：顧長風挑好同伴加入（集結中，照加入帶著那一位）；江映雪到曹氏莊院（同一個大區）投靠地方豪強，
        豪強分屬兩軍的季挑了依附哪一軍、集結名單跟著換到那一邊（_ally_follows_battle，FB-273）；豪強不分屬兩軍的季照舊臨時投效著。
        最後管理者取消 G（同 C：admin_conquest_cancel）——G 只為了集結時潁汝有兩場，留著的話 siege_start 要把時鐘推過它的截止（比 A、B、F 晚
        將近一個集結），第 5、6 批的決戰與攻城就晚那麼久才開打。"""
        self.login_all()
        who = "顧長風"
        ids = self.ids(self.main(who))
        pick = next((i for i in sorted(ids) if i.startswith("battle:escort:") and i not in ("battle:escort:none", "battle:escort:back")), None)
        emit(f"{who} 挑的同伴", pick)
        if pick is not None:
            self.choose(who, pick)
        self.mates(who, "挑好同伴之後")
        who = "江映雪"
        hq = next((f for f in self.c.scenario.factions if f.id == "haoqiang"), None)
        if hq is None or "cao_manor" not in hq.join_at or not self.place(who, "cao_manor"):
            emit("投靠豪強那一段略過（這份內容沒有地方豪強或曹氏莊院）", None)
        else:
            self.choose(who, "faction:haoqiang")
            b = self.world.get_battle()
            now_side = b.participants[who].faction if b is not None and who in b.participants else None
            ally = next((i for i in sorted(self.ids(self.main(who))) if i.startswith("faction:ally:") and i.rpartition(":")[2] != now_side), None)
            emit(f"{who} 選邊", ally)
            if ally is not None:
                self.choose(who, ally)
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        self.battle_row("第 7 批後半的人加入之後")
        self.escorts_row("集結中（後半）")
        b = self.world.get_battle()
        self.expect(b is None or b.phase == "muster", f"第 7 批集結那幾段做完時決戰還在集結（此刻 {None if b is None else b.phase}）")
        slot = self.slot_of("G") if self.siege_on() else None
        if slot is not None:
            self.do(ADMIN, "conquest_cancel", {"id": slot.id})
            self.siege_row("G 取消之後", ("G",))

    @_still
    def late(self) -> None:
        """開打之後才到：莫問天集結時按了加入、停在挑同伴，現在才挑（改成晚到、帶著那一位）；嚴不悔（黃巾）擺進決戰的大區，按「加入戰局」；
        沐晚晴（散人）擺進大區，晚到臨時投效官軍——人多的那一邊（晚到照投效的那一軍記，不照「補人少的那一邊」分；Task 5 的單點突變抓到
        原本投效黃巾時兩種一樣），再按黃巾那一顆被擋（開打之後鈕上沒有改投）。"""
        who = "莫問天"
        ids = self.ids(self.main(who))
        pick = next((i for i in sorted(ids) if i.startswith("battle:escort:") and i not in ("battle:escort:none", "battle:escort:back")), None)
        emit(f"{who} 開打之後才挑的同伴", pick)
        if pick is not None:
            self.choose(who, pick)
        self.mates(who, "開打之後挑了")
        loc = self.spot(self.target()[1])
        for who, want in (("嚴不悔", "battle:join_late"), ("沐晚晴", "battle:enlist:guan")):
            self.place(who, loc)
            if self.press(who, want, "開打之後按的") is not None and "battle:escort:none" in self.ids(self.main(who)):
                self.choose(who, "battle:escort:none")
        self.choose("沐晚晴", "battle:enlist:huang")
        self.battle_row("晚到之後")
        self.escorts_row("開打")

    @_still
    def wander(self) -> None:
        """參戰者走出決戰的大區、再喊停（_sync_battle_presence：出發那一下記離開；喊停那一下這一趟只剩下一站，落回大區就不算離開；抵達時
        再記一次）：顧長風（帶著同伴：主人離開大區時同伴也不在場上）往大區外的一處走（照 id 排、第一站還在大區裡的第一處），喊停。之後
        照回合輪詢，抵達那一下照路程。"""
        from tianxia import atlas

        who = "顧長風"
        b = self.world.get_battle()
        d = self.c.battles.get(b.battle_id) if b is not None else None
        if b is None or b.phase != "active" or d is None or d.region is None or who not in b.participants:
            emit("走出大區那一段略過（沒有開打中、有大區的決戰）", None)
            return
        state = self.chars.load(who)
        inside = {i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == d.region}
        dest = None
        for cand in sorted(i for i in self.c.locations if i not in inside):
            route = atlas.way_to(state, self.c, cand)
            if route is not None and len(route.path) >= 2 and route.path[0] in inside:
                dest = cand
                break
        emit(f"{who} 往大區外走", dest)
        if dest is None:
            return
        self.call(who, "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.escorts_row("走出大區之後")
        if "act:halt" in self.ids(self.main(who)):
            self.choose(who, "act:halt")
        self.escorts_row("喊停之後")

    @_still
    def muster_deliver(self) -> None:
        """第 7 批的新人收補送（下一次同步）：帶著同伴的顧長風、莫問天——同伴打完回江湖（file_showdown → escort_home：拿出隊伍、一句、情誼減半，
        settle_partings(write=False) 那一句併進決戰那一則紀錄），同一次同步後段的 settle_partings 看到 parted_done、清掉全服的記號（FB-361）；
        再同步一次什麼都不變（照實寫，審查 nit：另起一則「同伴回江湖」、同步時才減半的那一支——收場在輪詢組畫面時、角色沒存——四種設定都沒走到）。
        秦朗月、石破浪不派，沒有那一句。"""
        for who in self.MUSTER_PLAYERS:
            self.main(who)
            self.me(who, "收補送之後")
        for who in self.ESCORTERS:
            self.mates(who, "收補送之後")
            self.main(who)
            self.mates(who, "再同步一次之後")

    @_still
    def away_bot(self, battle_id: str, seed: int) -> set[int]:
        """假人那一場：一位官軍假人站在那一場的大區外、名下一位同伴（BotRunner 的 _toward_battle 照 rally_region 趕路，到了按加入、停在挑同伴：
        battle:escort:* 照決戰包的分數〔None：不按〕）。回它的種子（一直在線），這份內容沒有那一場是空的。"""
        from tianxia import atlas
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        d = self.c.battles.get(battle_id)
        if d is None or d.region is None:
            return set()
        name, side = self.AWAY_BOT
        inside = {i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == d.region}
        start = self.c.scenario.start_location
        loc = start if start not in inside else next(i for i in sorted(self.c.locations) if i not in inside)
        self.begin()
        g = Game.new(self.c, name, rng=random.Random(30), world=self.world, graduated=True)
        g.client = None
        g.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            g.choose(first)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=seed, faction=side, season_number=self.world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.joined_at = -1.0e9
        self.chars.save(g.state)
        emit(f"{name} 站在大區外", loc)
        self.give_mate(name, side)
        return {seed}


class MusterScenario(BattleScenario):
    """集結一軌（全部拆包第 7 批；--track muster）：決戰一軌同一套段落（整段一模一樣），半舊半新切在集結中——base 開了集結、幾位加入、
    顧長風與莫問天按了加入停在挑同伴（PlayerState.escort_pick 寫進存檔）就停，head 接著挑、投效、投靠豪強換邊、開打、晚到、收場。"""

    PHASES_FIRST = BattleScenario.PHASES_FIRST[:BattleScenario.PHASES_FIRST.index("muster_pick") + 1]
    PHASES_SECOND = BattleScenario.PHASES_FIRST[BattleScenario.PHASES_FIRST.index("muster_pick") + 1:] + BattleScenario.PHASES_SECOND


def _battle_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 dev/tavern-1 的 _register_track，名字分開免得兩塊都在時
    互相蓋掉）：之後的批照這一行接，不改上面那幾張表的原文。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：第 7 批換成這一批搬的一句（晚到的人趕到戰場；搬之前在 engine.py、之後在 features/battle/muster.py）——決戰一軌
# 前半走到（late）、集結一軌後半走到。第 5、6 批那兩句（view.py 的「軍餉發下來了。」、admin.py 的「（沒有進行中的決戰。）」）在計畫第五節
# 的單點突變裡照樣驗
_BATTLE_MUTATION = (("tianxia/features/battle/muster.py", "tianxia/engine.py"), ("你趕到了戰場，這一回合就能出手。", "你趕到了戰場，這一回合就能出手！"))
_battle_register_track("battle", BattleScenario, _BATTLE_MUTATION, "week7")
_battle_register_track("muster", MusterScenario, _BATTLE_MUTATION, "week7")  # 第 7 批：同一套段落，切在集結中


# ═══════════════════════════ tavern：酒肆一軌（主動搬六包第 10 批，dev/tavern-1） ═══════════════════════════
# 酒肆的引擎那一半搬進 tianxia/features/tavern/（計畫 docs/superpowers/plans/2026-10-31-酒肆包-第1批.md）。這一段整塊是酒肆的：
# 三條拆包線並行，接在檔尾、最後一行登記（_register_track），PM 合的時候不跟別人的行穿插。

# develop 0425589a 之後才要的兩個固定（註冊限流、資料庫第 9 版 sessions 的 token_hash 抹掉）：這一塊原本自己套一份（換掉 Scenario.__init__、
# 模組層的 db_text），合 develop（2026-11-01）時 develop 已經放在共用那一層（Scenario.__init__、db_text），只留那一份。


TAVERN_CHATTER = ["靠窗的腳夫：「今兒這酒倒是沒摻水。」", "喝悶酒的老卒：「城外又不太平了。」"]  # 假模型寫的鄰桌閒談
TAVERN_UNSURE = "客官，這事我不清楚。"  # 假模型的酒家：說不上來（退一半、指一條路）
TAVERN_REPLY = "客官，潁川一帶近來還算太平，城外倒是常有人走動。"  # 假模型的酒家：正常回話
_TAVERN_CLIENTS: dict[type, type] = {}


def _tavern_client(base: type) -> type:
    """問酒家、鄰桌閒談的假模型（base 是 _setup_child 那一層換好的 client 類別）：AskReply 回 MODEL["tavern"] 那一句、ChatterReply 回
    TAVERN_CHATTER，其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _TAVERN_CLIENTS:
        class TavernClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "AskReply":
                    return schema(reply=MODEL["tavern"])
                if schema.__name__ == "ChatterReply":
                    return schema(lines=list(TAVERN_CHATTER))
                return super().chat_structured(messages, schema, *a, **k)

        _TAVERN_CLIENTS[base] = TavernClient
    return _TAVERN_CLIENTS[base]


class TavernScenario(Scenario):
    """酒肆（主動搬六包第 10 批；--track tavern，自己一個資料庫）。照調查 survey_tavern.json 的 behavior_check：進酒肆、看（main.shop）、
    聽消息、查人（確切、託付留意、查無此人、自己、人物）、交情、素材、題壁、請酒（換日再請）、藏行跡、反查、保鏢、問酒家（鎖外三段式，
    假模型）、鄰桌閒談（server.chatter_once，假模型）、牆上的懸賞榜、買殺手；被打聽的人收風聲、殺手在城外做一件事時找上（得手）、
    站在城外下線回來時找上（失手）、同一對人連著失手（加價五成、威力 +0.1、最多 3 次）、雇主收結果、過期退一半、託付留意捎信與到期；
    得手之後的護身期內殺手不擲、藏了行跡的人殺手的打聽度少一截、酒肆關著時殺手不擲（審查之後補的：原本只走到買與欄位）；
    同一次同步收到風聲、殺手單的結果、託付到期與書信（sync 裡三個 deliver 的先後與位置，crossing）；酒肆開關關著時（記憶體裡關）坐著的人照樣出得去、三個 deliver 照樣送；伺服器假人（BotRunner）進酒肆；換季。
    殺手那一場用 killer(tier)：tavern.find_chance 換成 1（或 0）、單次判定照 tier（本人這一邊的結果）。
    四種正式設定都站潁川一帶；測試內容沒有酒肆、沒有陣營，同一串 API 照打（證明關著一個字都不變），假人那一段略過。
    半舊半新切在 hire 之後：四張殺手單沒結、風聲沒送到、託付沒回音（批次表第二節「還沒結的殺手單」）。"""

    PLAYERS = {"葉開": None, "阿飛": None, "丁鵬": None, "孟星魂": None, "郭大路": None}  # 都是散人
    NEWBIE = "燕七"  # 不略過引導（none、weekend 還在序章：不在酒肆、沒有入口）
    # 葉開打聽、阿飛雇主（都坐在潁川）；丁鵬被打聽、被殺手得手（潁川郊野）；孟星魂被通緝、連著失手（潁水河畔）；
    # 郭大路被託付留意、站在城外下線時殺手失手（長社）
    SEATS = {"葉開": "yingchuan", "阿飛": "yingchuan", "丁鵬": "yingchuan_wilds", "孟星魂": "yingshui", "郭大路": "changshe"}
    FAME = {"丁鵬": 300, "孟星魂": 120, "郭大路": 0}
    BOT_SEATS = [("柳長街", "guan", "yingchuan"), ("卓東來", "huang", "wan_city"), ("王動", "guan", "runan"), ("鐵中棠", "huang", "zhuo_county")]
    PHASES_FIRST = ["setup", "seat", "enter", "ops", "keeper", "chatter", "board", "hire"]
    PHASES_SECOND = ["resume", "whispers", "strike", "away", "streak", "lapse", "watch", "crossing", "trace", "depart", "closed", "bots",
                     "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("tavern") is not None:
                client.__class__ = _tavern_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同約戰那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，城外那幾位選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 分", None)

    def now(self) -> float:
        """下一個請求之前的現實時刻（同 begin 的算法）。"""
        return CLOCK0 + STEP[0] * STEP_SECONDS

    def tav(self, who: str, op: str, target: str = "", text: str = ""):
        """店面那一頁的動作（/api/do/tavern → MAIN_ACTIONS["tavern"] → Game.tavern_do）。"""
        return self.do(who, "tavern", {"op": op, "target": target, "text": text})

    def me(self, who: str, tag: str) -> None:
        """存檔裡酒肆那幾格（酒肆包認領的十個欄位），加上銀兩、名望、惡名、氣血。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "silver": p.stats.get("silver", 0), "fame": p.stats.get("fame", 0), "evil": p.stats.get("evil", 0), "neili": p.member.neili,
            "picking_tavern": p.picking_tavern, "tavern_notes": [n.model_dump() for n in p.tavern_notes], "tavern_heard": p.tavern_heard,
            "tavern_known": p.tavern_known, "tavern_treat_day": p.tavern_treat_day, "whispers": [w.model_dump() for w in p.whispers],
            "hidden_until": p.hidden_until, "tavern_watches": [w.model_dump() for w in p.tavern_watches],
            "tavern_guard_until": p.tavern_guard_until, "tavern_shield_until": p.tavern_shield_until})

    def hits(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"季上的殺手單 {tag}", [h.model_dump() for h in s.tavern_hits])
        emit(f"季上還沒送的風聲 {tag}", {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_whispers.items())})

    @contextlib.contextmanager
    def killer(self, tier: str | None):
        """殺手那一場定死：tier 給了，tavern.find_chance 換成 1、單次判定照 tier（本人這一邊的結果，照樣用掉那一場的一個亂數），
        記下殺手威力 ÷ 本人威力；tier 是 None，find_chance 換成 0（擲了、找不到）。換的都是模組屬性（tianxia.tavern 是包裡 rules 的別名）。
        也記下殺手擲的那一下的打聽度（find_chance 拿到的 reach：藏行跡扣 hide_reach；一個都沒有＝殺手沒擲）。"""
        from tianxia import encounter, tavern

        real_find, real_resolve = tavern.find_chance, encounter.resolve_encounter
        seen: list[float] = []
        reaches: list[int] = []

        def fake(mine, theirs, rng, *a, **k):
            rng.random()
            seen.append(round(theirs / mine, 6) if mine else None)  # 選單上的勝算也走這裡（照樣換成 tier）
            return encounter.EncounterResult(tier=tier, margin=0.0, our_power=mine, difficulty=theirs)

        def find(c, reach):
            reaches.append(reach)
            return 1.0 if tier else 0.0

        tavern.find_chance = find
        if tier:
            encounter.resolve_encounter = fake
        try:
            yield seen
        finally:
            tavern.find_chance, encounter.resolve_encounter = real_find, real_resolve
            emit(f"殺手那一場（{tier or '找不到'}）殺手威力 ÷ 本人威力", seen)
            emit(f"殺手那一場（{tier or '找不到'}）殺手擲的打聽度", reaches)

    def act_outside(self, who: str) -> None:
        """在城外做一件事（choose 最後那一下是殺手檢查）：體力補滿，選單上第一個按得下去的 act:explore／act:train／act:socialize；
        都沒有（出門一趟碰上的事件待選）就選那一則事件第一個按得下去的選項。"""
        self.place(who, None)
        ids = self.ids(self.main(who))
        pick = next((i for i in ("act:explore", "act:train", "act:socialize") if (ids.get(i) or {}).get("enabled")), None)
        pick = pick or next((i for i, o in ids.items() if i.startswith("choice:") and o.get("enabled")), None)
        emit(f"{who} 在城外做的事", pick)
        if pick is not None:
            self.choose(who, pick)

    def unpair(self, client: str, target: str) -> None:
        """錯開同一對人 hit_pair_hours 一次的限制、清掉截殺那一道護身（時鐘推不了那麼遠）：直接改季上的單子與 raided。"""
        from tianxia.characters import name_key

        gap = self.c.config.tavern.hit_pair_hours * 3600 + 10

        def fn(s) -> None:
            for h in s.tavern_hits:
                if name_key(h.client) == name_key(client) and name_key(h.target) == name_key(target):
                    h.placed_real -= gap
            s.raided.pop(name_key(target), None)

        self.world.mutate_season(fn)
        emit(f"錯開 {client}→{target} 的冷卻、清掉護身", None)

    # ── 前半 ──

    def seat(self) -> None:
        """站好位置、給銀兩與名望（直接改資料庫）；季上擺兩張通緝（孟星魂、郭大路：揭了的通緝不必先查也雇得了殺手、名氣 +1）。"""
        from tianxia import tavern
        from tianxia.state import Bounty

        for who, loc in self.SEATS.items():
            self.place(who, loc)
            fame = self.FAME.get(who)

            def fn(p, fame=fame) -> None:
                p.stats["silver"] = 900
                if fame is not None:
                    p.stats["fame"] = fame

            self.edit(who, fn)
        emit("城外嗎", {loc: tavern.town(self.c, loc) for loc in self.SEATS.values() if loc in self.c.locations})

        def post(s) -> None:
            for poster, target in (("阿飛", "孟星魂"), ("葉開", "郭大路")):
                s.bounty_seq += 1
                s.bounties.append(Bounty(id=f"b{s.bounty_seq}", kind="wanted", faction=None, week=1, expires=s.time + 30 * 86400,
                                         silver=50, deeds=0, quota=1, poster=poster, target=target))

        self.world.mutate_season(post)
        emit("擺兩張通緝：孟星魂、郭大路", None)
        for who in [*self.PLAYERS, self.NEWBIE]:
            emit(f"{who} 的 act:tavern", self.ids(self.main(who)).get("act:tavern"))

    def enter(self) -> None:
        """入口：還沒進店的 tavern_do 被拒；act:tavern 打開店面（main.shop）；阿飛也進同一間。"""
        self.tav("葉開", "news")
        out = self.choose("葉開", "act:tavern")
        emit("葉開 酒肆裡的選單", sorted(self.ids(out)))
        self.choose("阿飛", "act:tavern")

    def ops(self) -> None:
        """店面那一頁的動作一樣一樣做（成的與被拒的各一次）；選單上那幾顆（tavern:news、treat、hide、trace）走 /api/choose，
        是酒肆包的 choose 掛鉤接走的那一條。"""
        c = self.c
        self.choose("葉開", "tavern:news")
        self.tav("葉開", "news")
        self.tav("葉開", "seek", "丁鵬")
        self.tav("葉開", "seek", "郭大路", "watch")  # 問不清楚：多付一點託酒家留意
        self.tav("葉開", "seek", "郭大路", "watch")  # 同一個人再託
        self.tav("葉開", "seek", "查無此人")
        self.tav("葉開", "seek", "葉開")
        self.tav("葉開", "seek", "")
        figure = next((f for f in c.figures.values() if f.character in c.characters), None)
        fname = c.characters[figure.character].name if figure is not None else "曹操"
        self.tav("葉開", "seek", fname, "watch")  # 人物一問就清楚：不託
        self.tav("葉開", "ties", "丁鵬")
        self.tav("葉開", "ties", fname)
        mats = sorted(c.materials.values(), key=lambda m: (m.tier, m.id))
        for tier in (1, 3):
            m = next((m for m in mats if m.tier == tier), None)
            if m is not None:
                self.tav("葉開", "material", m.id)
        self.tav("葉開", "material", "沒有這樣東西")
        self.tav("葉開", "wall", "", "潁川城頭月，照我一壺酒。")
        self.tav("葉開", "wall", "", "假人寫的字")
        self.tav("葉開", "wall", "", "字" * (c.config.tavern.wall_chars + 1))
        self.tav("葉開", "wall", "", "")
        self.choose("葉開", "tavern:treat")
        self.tav("葉開", "treat")  # 今天請過了
        self.edit("葉開", lambda p: setattr(p, "tavern_treat_day", p.tavern_treat_day - 1))  # 換日（請酒照回體丹那一天）
        emit("葉開 請酒那一天擺成昨天", None)
        self.tav("葉開", "treat")
        self.choose("葉開", "tavern:hide")
        self.tav("葉開", "hide")
        self.choose("葉開", "tavern:trace")  # 沒人打聽：不收錢
        self.tav("葉開", "guard")
        self.tav("葉開", "guard")
        self.tav("葉開", "bogus")
        self.me("葉開", "店面做完")

    def keeper(self) -> None:
        """問酒家（/api/do/tavern_ask：A 鎖內開單 → B 鎖外請模型 → C 鎖內重驗才收錢）：叫不動模型退全額、問秘密收一半（不叫模型）、
        說不清楚退一半、正常回話、空的、太長。"""
        q = "潁川城外近來太平嗎？"
        self.do("葉開", "tavern_ask", {"text": q})
        self.do("葉開", "tavern_ask", {"text": "神器配方怎麼湊？"})
        try:
            MODEL["tavern"] = TAVERN_UNSURE
            self.do("葉開", "tavern_ask", {"text": "精鐵砂好不好用？"})
            MODEL["tavern"] = TAVERN_REPLY
            self.do("葉開", "tavern_ask", {"text": q})
            self.do("葉開", "tavern_ask", {"text": ""})
            self.do("葉開", "tavern_ask", {"text": "問" * (self.c.config.tavern.ask_chars + 1)})
        finally:
            MODEL.pop("tavern", None)

    def chatter(self) -> None:
        """鄰桌閒談（server.chatter_once：A 鎖內開單、B 鎖外請模型寫〔假模型〕、C 鎖內重驗才記）；第二次這一陣子不再寫。"""
        try:
            MODEL["tavern"] = TAVERN_REPLY
            for _ in range(2):
                self.begin()
                emit("鄰桌閒談 chatter_once", self.server.chatter_once(self.server.game_for("葉開")))
        finally:
            MODEL.pop("tavern", None)
        self.main("葉開")

    def board(self) -> None:
        """牆上的懸賞榜：tavern:board 收起酒肆、打開懸賞榜；返回之後再進酒肆、出酒肆、再進（葉開接下來一直坐在酒肆裡）。"""
        if "tavern:board" in self.ids(self.main("葉開")):
            out = self.choose("葉開", "tavern:board")
            if "bounty:back" in self.ids(out):
                self.choose("葉開", "bounty:back")
        else:
            emit("牆上沒有懸賞榜", None)
        self.choose("葉開", "act:tavern")
        self.choose("葉開", "tavern:back")
        self.choose("葉開", "act:tavern")

    def hire(self) -> None:
        """買殺手：阿飛沒查過就雇（要先查到過）、壞的檔次、查了雇丁鵬、再雇被拒（身上已有別人的單）、雇被通緝的郭大路加封口；
        葉開雇被通緝的孟星魂、查了雇坐在城裡的阿飛（殺手等著，之後擺成過期）。切在這裡：四張單沒結、風聲沒送、託付沒回音。"""
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "seek", "丁鵬")
        self.tav("阿飛", "hit", "丁鵬", "9")
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "hit", "丁鵬", "1")
        self.tav("阿飛", "hit", "郭大路", "2:hush")
        self.tav("葉開", "hit", "孟星魂", "0")
        self.tav("葉開", "seek", "阿飛")
        self.tav("葉開", "hit", "阿飛", "0")
        self.hits("前半最後")

    # ── 後半 ──

    def resume(self) -> None:
        """重新登入每一個帳號（登入也同步：被雇的人下線那一段殺手照樣擲一次，find_chance 換成 0：找不到，殺手留到後面那幾段）。"""
        with self.killer(None):
            self.login_all()

    def whispers(self) -> None:
        """被打聽、被雇的人自己同步時收風聲；下線那一段殺手照樣擲一次（find_chance 換成 0：找不到）。"""
        with self.killer(None):
            for who in ("丁鵬", "孟星魂"):
                self.main(who)
        self.me("丁鵬", "收了風聲")

    def strike(self) -> None:
        """丁鵬在城外做完一件事：殺手找上門，這一場殺手贏（氣血剩 1、銀兩照丟、之後一陣子殺手找不上）；雇主阿飛同步收「得手」與惡名。
        阿飛同一對人 hit_pair_hours 內再雇被拒（審查：HIT_PAIR 原本沒有走到）。
        護身（審查：原本只寫了欄位，沒走到效果）：清掉截殺那一道護身（不然它先擋），葉開雇一張找丁鵬，丁鵬在 tavern_shield_until 之內
        再到城外做一件事——殺手不擲（killer 記不到打聽度）。這一張留著（後面那幾段丁鵬都在城裡）。"""
        from tianxia.characters import name_key

        with self.killer("落敗"):
            self.act_outside("丁鵬")
        self.me("丁鵬", "殺手得手之後")
        self.main("阿飛")
        self.me("阿飛", "收了得手")
        self.tav("阿飛", "hit", "丁鵬", "0")  # 同一對人 hit_pair_hours 內再雇：被拒（HIT_PAIR；上一張結了，不是 HIT_TAKEN 擋的）
        self.world.mutate_season(lambda s: s.raided.pop(name_key("丁鵬"), None))
        emit("清掉丁鵬截殺那一道護身（只留殺手得手的護身）", None)
        self.tav("葉開", "hit", "丁鵬", "0")
        with self.killer("落敗"):
            self.act_outside("丁鵬")
        self.me("丁鵬", "護身期內在城外做完一件事")

    def away(self) -> None:
        """郭大路站在城外下線（seat 那一下之後就沒同步過），時鐘再推過十二分：回來同步時殺手照下線那一段擲，這一場對方贏
        （撿到銀兩、名望、雇主可能被供出）；阿飛同步收「失手」。"""
        self.skip(12)
        with self.killer("大勝"):
            self.main("郭大路")
        self.me("郭大路", "打退殺手之後")
        self.main("阿飛")

    def streak(self) -> None:
        """同一個雇主找同一個人連著失手：孟星魂先進潁川雇保鏢（殺手威力照 guard_scale 打折）、藏行跡（殺手的打聽度扣 hide_reach，
        killer 記下打聽度）再回城外；四輪平手——每一輪孟星魂在城外做一件事、葉開同步收「平手」、錯開冷卻與護身、再雇一張：價錢 +五成、
        威力 +0.1，第三次之後不再加（第五張在 crossing 出手，威力跟第四張一樣）。"""
        self.place("孟星魂", "yingchuan")
        self.choose("孟星魂", "act:tavern")
        self.tav("孟星魂", "guard")
        self.tav("孟星魂", "hide")
        self.choose("孟星魂", "tavern:back")
        self.place("孟星魂", "yingshui")
        for _ in range(4):
            with self.killer("僵持"):
                self.act_outside("孟星魂")
            self.main("葉開")
            self.unpair("葉開", "孟星魂")
            self.tav("葉開", "hit", "孟星魂", "0")
        self.hits("連著失手之後")

    def lapse(self) -> None:
        """葉開雇去找坐在城裡的阿飛的那一張擺成已經到期：阿飛同步時收成過期，葉開同步領回一半。"""
        until = self.now() - 1

        def fn(s) -> None:
            for h in s.tavern_hits:
                if h.target == "阿飛" and not h.done:
                    h.until_real = until

        self.world.mutate_season(fn)
        emit("葉開找阿飛的那一張擺成到期", None)
        self.main("阿飛")
        self.main("葉開")
        self.me("葉開", "領了退款")

    def watch(self) -> None:
        """託付留意：郭大路走進潁川、名望到頂（直接改資料庫），葉開同步時捎信「打聽到了」；再託一個查無此人的、擺成到期：捎一句沒聽到準信。"""
        self.place("郭大路", "yingchuan")
        self.edit("郭大路", lambda p: p.stats.__setitem__("fame", 100000))
        self.main("郭大路")
        self.main("葉開")
        self.tav("葉開", "seek", "查無此人", "watch")
        until = self.now() - 1

        def fn(p) -> None:
            p.tavern_watches = [w.model_copy(update={"until_real": until}) if w.target == "查無此人" else w for w in p.tavern_watches]

        self.edit("葉開", fn)
        emit("查無此人那一筆託付擺成到期", None)
        self.main("葉開")
        self.me("葉開", "託付收尾")

    def crossing(self) -> None:
        """sync 裡三個 deliver 的先後與位置（審查：之前沒有一次同步同時收到兩樣，換順序、整段挪到 on_sync 前面都抓不到）：
        葉開先託酒家留意一個查無此人的；孟星魂在城外做一件事，葉開連著失手三次之後的那一張出手、平手（價錢與威力停在上限）；阿飛在潁川的
        酒肆查藏了行跡的葉開（風聲記在季上）；葉開那一筆託付擺成到期、身上擺一封委託過期的信（letters.deliver 排在三個 deliver 後面，
        寫「書信」那一則）。然後葉開同步一次：風聲、殺手單的結果、託付到期、書信四則在同一下，江湖紀錄的先後照 sync 的順序。
        三個 deliver 的前後再各夾一格會寫紀錄的：前一格護衛補帳（_deliver_guard_credits）、後面翻地的守城分紅（_deliver_conquest，有領地
        爭奪的季）——三行整段挪過它們（例：挪到 _deliver_big_events 前面、挪到 _marks_tick 之後）也看得出來。_marks_tick、
        _stance_annals、_zhuan_tick 只寫行狀、不讀惡名，跟三個 deliver 的先後只能靠這兩格看。"""
        from tianxia import figure_aid
        from tianxia.state import Bounty, ConquestPayout, Letter

        c = self.c
        self.tav("葉開", "seek", "查無此人", "watch")
        with self.killer("僵持"):
            self.act_outside("孟星魂")
        self.unpair("葉開", "孟星魂")  # 錯開冷卻、清掉截殺那一道護身（closed 那一段再雇一張找他）
        self.tav("阿飛", "seek", "葉開")
        figure = next((f for f in c.figures.values() if f.character in c.characters), None)
        world_now = self.world.get_season().time
        until = self.now() - 1

        def fn(p) -> None:
            p.tavern_watches = [w.model_copy(update={"until_real": until}) if w.target == "查無此人" else w for w in p.tavern_watches]
            if figure is not None:
                task = Bounty(id="letter-crossing", kind="strike", faction=None, week=1, expires=world_now - 1, silver=0, deeds=0,
                              figure=figure.character, motive="委託")
                p.letters.append(Letter(id=900, kind="求援", sender=figure.character, at=world_now - 60, text="（求援）", task=task))

        self.edit("葉開", fn)
        emit("葉開 查無此人那一筆託付擺成到期、身上擺一封委託過期的信", figure.character if figure is not None else None)

        def bracket(s) -> None:  # 三個 deliver 前後緊鄰、會寫江湖紀錄的兩格：前面的護衛補帳、後面的翻地分紅（有領地爭奪的季）
            who = figure.name if figure is not None else "某人"
            s.guard_credits.setdefault("葉開", []).append(figure_aid.CREDIT_LINE.format(name=who, who="郭大路"))
            if s.conquest is not None and c.scenario.factions and "yingchuan" in c.locations:
                s.conquest.payouts.append(ConquestPayout(name="葉開", kind="guard", loc="yingchuan", side=c.scenario.factions[0].id,
                                                         silver=5, share=0.5, time=s.time))

        self.world.mutate_season(bracket)
        emit("季上擺葉開的護衛補帳與一筆守城分紅（三個 deliver 的前一格與後面那一格）", None)
        self.main("葉開")
        emit("葉開 同一下同步收到的（江湖紀錄新的在前）", [e.title for e in self.chars.load("葉開").journal[:8]])
        self.hits("同一下同步之後")

    def trace(self) -> None:
        """丁鵬進潁川的酒肆反查（有沒有問不出名號的風聲，照前半雇殺手那一下聽到風聲的是不是生面孔）。"""
        self.place("丁鵬", "yingchuan")
        self.choose("丁鵬", "act:tavern")
        self.choose("丁鵬", "tavern:trace")
        self.choose("丁鵬", "tavern:back")

    def depart(self) -> None:
        """坐在酒肆裡動身（核心收接縫，全部拆包第 11 批：Game._depart 收店那一行換成店面登記的收店，排在擂台之後）。丁鵬坐進潁川的酒肆：
        從輿圖安排前往被擋（atlas.travel_block「還坐在酒肆裡」）；Game._depart 本身（輿圖、移動、折返、人物帶路都從它出發，坐在店裡的人
        平常走不到這一行）在鎖裡直接叫一次：酒肆跟擂台、鐵匠鋪那幾間一起收起來、動身上路。之後擺回潁川。測試內容沒有潁川：同一串照打。"""
        from tianxia import atlas
        from tianxia.engine import Game

        start = "yingchuan" if "yingchuan" in self.c.locations else self.c.scenario.start_location
        dest = self.c.locations[start].connections[0] if self.c.locations[start].connections else start
        self.place("丁鵬", start)
        self.settle_choices("丁鵬")  # 前面出門碰上的事件還在待選：選掉（不然選單是那一則事件，沒有進酒肆那一顆）
        self.place("丁鵬", start)
        self.choose("丁鵬", "act:tavern")
        self.me("丁鵬", "動身之前")
        self.call("丁鵬", "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.me("丁鵬", "從輿圖安排前往之後")
        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load("丁鵬"), world=self.world)
            game.sync(CLOCK[0])
            route = atlas.way_to(game.state, self.c, dest)
            emit("丁鵬 直接動身", game._depart(route, "walk") if route is not None else None)
            self.chars.save(game.state)
        self.me("丁鵬", "動身之後")
        emit("丁鵬 動身之後的選單", sorted(self.ids(self.main("丁鵬"))))
        self.place("丁鵬", start)

    def closed(self) -> None:
        """酒肆開關關掉（記憶體裡，做完開回來）。開著時郭大路先坐進潁川的酒肆、照那一刻建一份 Game（建的時候開著，沒有收店）；
        關掉之後不 sync：選單照舊是酒肆那一串、假人看「出酒肆」照舊 0 分、按得出去（搬包之前 choose 那一支不看開關）。
        季上擺一則給丁鵬的風聲、一張阿飛找丁鵬的過期單子：關著照樣送到、照樣退一半（三個 deliver 不看開關）。
        坐在酒肆裡的葉開同步就收店、入口沒了、店面的動作與 tavern:news 都被拒。
        殺手不擲（審查：原本沒有人帶著活單站在城外）：開著時葉開再雇一張找孟星魂，關著時孟星魂在城外做一件事——killer 記不到打聽度。"""
        from tianxia import bot_policy
        from tianxia.characters import name_key
        from tianxia.engine import Game
        from tianxia.state import BotProfile, TavernHit, Whisper

        self.tav("葉開", "hit", "孟星魂", "0")
        self.choose("郭大路", "act:tavern")
        self.begin()
        game = Game(self.c, self.chars.load("郭大路"), world=self.world)
        cfg = self.c.config.tavern
        before = cfg.enabled
        cfg.enabled = False
        try:
            menu = game.options(odds=False)
            emit("關掉那一刻 郭大路的選單（沒有 sync）", [o.id for o in menu])
            back = next((o for o in menu if o.id == "tavern:back"), None)
            if back is not None:
                emit("關掉那一刻 假人看出酒肆", bot_policy.score(game, back, BotProfile(personality="普通", seed=1)))
                emit("關掉那一刻 出酒肆", game.choose("tavern:back"))
            now = self.now()

            def fn(s) -> None:
                s.tavern_whispers.setdefault(name_key("丁鵬"), []).append(
                    Whisper(kind="seek", who="葉開", place="yingchuan", time=s.time, named=True))
                s.tavern_hit_seq += 1
                s.tavern_hits.append(TavernHit(id=s.tavern_hit_seq, client="阿飛", target="丁鵬", tier=0, price=20, place="yingchuan",
                                               placed_real=now - 7200, until_real=now - 60))

            self.world.mutate_season(fn)
            emit("關著時季上擺一則風聲、一張過期的單子", None)
            view = self.main("葉開")
            emit("關著 葉開的 act:tavern", self.ids(view).get("act:tavern"))
            self.tav("葉開", "news")
            self.choose("葉開", "tavern:news")
            self.main("丁鵬")
            self.main("阿飛")
            self.me("丁鵬", "關著收了風聲")
            with self.killer("落敗"):
                self.act_outside("孟星魂")
            self.hits("關著")
        finally:
            cfg.enabled = before

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(7)、時鐘一輪推五分）：同一個資料庫補四個坐在有酒肆的城裡的假人
        （第一個已經坐在酒肆裡：bot_policy.score 問酒肆包「出酒肆」那一顆），bot_policy.TAVERN_CHANCE 換成 0.5（照舊是 bot_policy 的
        模組屬性，_tavern 那一步照舊在 bot_policy），跑 SB_TAVERN_TICKS 輪。整季機器人的 bot.pick 在酒肆的選單上不按 tavern:。
        測試內容沒有酒肆、沒有陣營：略過。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots, tavern
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        if not tavern.on(self.c) or not self.c.scenario.factions:
            emit("這份內容沒有酒肆或陣營：假人那一段略過", None)
            return
        for i, (name, side, loc) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉（不然選單是那一則事件，不是酒肆）
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 600
            p.picking_tavern = i == 0
            self.chars.save(g.state)
        self.begin()
        first = Game(self.c, self.chars.load(self.BOT_SEATS[0][0]), world=self.world)
        emit("整季機器人在酒肆的選單上挑", bot.pick(first, first.options(odds=False), random.Random(0)))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(7), clock=lambda: CLOCK[0])
        chance, tick, online = bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {31 + i for i in range(len(self.BOT_SEATS))}
        bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds = 0.5, 10 ** 6  # 在線的假人每一輪都動
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)  # 擺好的四個一直在線（作息照種子，傍晚多半不在）
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_TAVERN_TICKS", "40"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online = chance, tick, online
        states = self.chars.all(bots_only=True)
        emit("酒肆假人 一輪一輪", dict(sorted(totals.items())))
        emit("酒肆假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("酒肆假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        self.hits("假人之後")

    def season(self) -> None:
        """收季：坐在酒肆裡的人照坐（休季也能喝酒、題壁），雇殺手被擋、畫面的 hits.ended；開下一季：酒肆那十個欄位跟著新角色重來、
        季上的酒肆欄位是空的。"""
        self.place("阿飛", "yingchuan")
        self.choose("阿飛", "act:tavern")
        self.do(ADMIN, "end_season")
        self.main("阿飛")
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "wall", "", "收季了，再喝一壺。")
        self.do(ADMIN, "next_season")
        for who in ("葉開", "丁鵬"):
            self.main(who)
            self.me(who, "換季之後")
        s = self.world.get_season()
        emit("換季之後季上的酒肆", {"walls": {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_walls.items())},
                                   "whispers": {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_whispers.items())},
                                   "treats": dict(sorted(s.tavern_treats.items())), "hits": [h.model_dump() for h in s.tavern_hits],
                                   "seq": s.tavern_hit_seq, "chatter": dict(sorted(s.tavern_chatter.items()))})


def _register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記）：之後的批照這一行接，不改上面那幾張表的原文。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


_register_track("tavern", TavernScenario, (("tianxia/features/tavern/rules.py", "tianxia/tavern.py"), ("滿堂叫好。", "滿堂叫好！")), "week7")


# ═══════════════════════════ core-events：事件檢定一軌（全部拆包第 16 批，dev/core-events-1） ═══════════════════════════
# 事件檢定（端出事件卡、選項的檢定與結果、效果套用、事件裡打一場、隨口應對的三段式）的本體從 engine.py 搬進核心本體
# tianxia/core/event_check.py（計畫 docs/superpowers/plans/2026-11-01-事件檢定進核心.md）。這一段整塊是這一批的：接在檔尾、最後一行登記
# （_events_register_track），PM 合的時候不跟別人的行穿插。探索那一軌（ExploreScenario）已經走到的：各種地點按探索、事件卡等回答
# （半舊半新）、分級事件經探索抽出來、隨口應對的分岔（假模型、第一種）——這一軌補它沒走到的：檢定成與敗（rules.check_chance 定死）、
# 串接（成了串、敗了串）、付錢的選項、事件裡打一場（贏、輸、大場面判讀）、一次性事件不再出現、走一趟途中的事件、隨口應對（模型擋著退回、
# 假模型成與敗、潤色插回、判成惡行、分岔四條、錢不夠）、第二階事件的那一行、說書的口訣、交友碰上事件、伺服器假人在事件卡上挑、換季。

EVENT_NARRATION = "你照著心裡的盤算行事，旁人看得目瞪口呆。"  # 假模型的潤色（server.answer_event 的 D 段；不寫數字、成敗都是這一句）
EVENT_TEXT = "我上前好言相勸，請他先把話說清楚。"  # 隨口應對寫的那一句（20 字以內）
_EVENT_CLIENTS: dict[type, type] = {}


def _event_client(base: type) -> type:
    """隨口應對的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["event"] 給了（{rate, moral, outcome, narrate}）時，
    評分回 rate、判善惡回 moral、歸類回 outcome（不在清單上回第一種）、潤色回 narrate；其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _EVENT_CLIENTS:
        class EventClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                say = MODEL.get("event")
                fields = getattr(schema, "model_fields", {})
                if say is not None and "outcome" in fields:
                    ids = (fields["outcome"].json_schema_extra or {}).get("enum") or [""]
                    return schema(outcome=say["outcome"] if say.get("outcome") in ids else ids[0], success_rate=say["rate"])
                if say is not None and schema.__name__ == "SuccessRateJudgment":
                    return schema(success_rate=say["rate"])
                if say is not None and schema.__name__ == "MoralJudgment":
                    return schema(moral=say["moral"])
                return super().chat_structured(messages, schema, *a, **k)

            def chat_text(self, messages, *a, **k):
                say = MODEL.get("event")
                if say is not None and say.get("narrate"):
                    return say["narrate"]
                return super().chat_text(messages, *a, **k)

        _EVENT_CLIENTS[base] = EventClient
    return _EVENT_CLIENTS[base]


class EventScenario(ExploreScenario):
    """事件檢定（全部拆包第 16 批；--track events，自己一個資料庫）。小工具借探索那一軌的（draws、fights、tweak、settle、walk、
    kind_places、first_event、edit_state）。事件多半直接擺到眼前（pending_event 寫進存檔，伺服器每次進鎖重讀；選項、檢定、效果、
    串接、打一場、隨口應對都是真的走 /api/choose、/api/answer），端出來那一下（_present）走探索、串接、序章、交友、走一趟。
    正式內容四種設定挑同一批事件（醉漢、乞丐、壇前講道、寒山鐘、逃卒、租債、白馬津押鏢、茶館）；測試內容沒有的（付錢、隨口應對、
    第二階、說書）寫「沒有」略過，同一串 API 照打。
    半舊半新切在 half 之後：五張事件卡等回答（舊程式串出來的、舊程式探索端出來的、有分岔的隨口應對、要打的、沒有分岔的隨口應對），
    後半第一件事（answer）是新程式接著回答。"""

    PLAYERS = {"沈勝衣": None, "白玉京": None, "風四娘": None, "連城璧": None, "柳若松": None, "司馬超群": "guan", "謝曉峰": None,
               "蕭秋雨": None}
    NEWBIE = "孫小紅"  # 不略過引導（不帶、weekend 走草廬；season21、week7 是開局第一分鐘）
    BOT_SEATS = [("事甲", "yingshui"), ("事乙", "julu_altar"), ("事丙", "guangzong"), ("事丁", "market_town")]
    PHASES_FIRST = ["setup", "prologue", "cards", "check", "pay", "fight", "once", "trip", "dead", "half"]
    PHASES_SECOND = ["resume", "answer", "said", "evil", "branches", "tiered", "tale", "social", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("event") is not None:
                client.__class__ = _event_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，事件卡上動手那一顆的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def event_of(self, prefer: str, test) -> str | None:
        """正式內容挑 prefer 那一則（合 test 的話），否則照 id 排第一則合 test 的（探索抽得到的優先）；都沒有是 None。"""
        if prefer in self.c.events and test(self.c.events[prefer]):
            return prefer
        return self.first_event(test)

    def card(self, who: str, eid: str | None) -> bool:
        """把這則事件直接擺到他眼前（等回答）：站到事件的地點（沒寫地點的照舊站著），體力補滿。"""
        if eid is None:
            emit(f"{who}：這份內容沒有合適的事件", None)
            return False
        event = self.c.events[eid]
        if not self.place(who, event.locations[0] if event.locations else None):
            return False
        self.edit_state(who, lambda s: setattr(s, "pending_event", eid))
        return True

    def press(self, who: str, test, tag: str) -> bool:
        """眼前那一則照內容的順序，第一顆合 test、選單上有而且按得下去的按下去；沒有就寫下選單上有哪幾顆。"""
        state = self.chars.load(who)
        eid = state.pending_event if state is not None else None
        opts = self.options(who)
        if eid is None:
            emit(f"{who} {tag}：眼前沒有事件", None)
            return False
        for i, ch in enumerate(self.c.events[eid].choices):
            oid = f"choice:{i}"
            if test(ch) and opts.get(oid, {}).get("enabled"):
                self.choose(who, oid)
                return True
        emit(f"{who} {tag}：沒有合的那一顆", sorted(opts))
        return False

    def say(self, who: str, text: str = EVENT_TEXT):
        """隨口應對（/api/answer：server.answer_event 的 A、B、C 段，擲完骰有潤色的再 D、E 段）。"""
        return self.call(who, "POST", "/api/answer", {"text": text})

    def seek(self, who: str) -> None:
        """按一下探索：探索一顆開著就是出門一趟；三選一的季（weekend）按「找事件」那一顆；舊探索照它自己擲。"""
        self.choose(who, "act:explore")
        modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
        if modes:
            self.choose(who, "explore:seek" if "explore:seek" in modes else modes[0])

    @contextlib.contextmanager
    def odds(self, value: float):
        """這幾下事件檢定的成功率定死（rules.check_chance 換成 value：roll_check 照樣用掉 Game.rng 那一顆骰，比的門檻換掉；
        選項上寫的心裡話照 check_gap，不動）。"""
        from tianxia import rules

        real = rules.check_chance
        rules.check_chance = lambda *a, **k: value
        try:
            yield
        finally:
            rules.check_chance = real

    @contextlib.contextmanager
    def model(self, **say):
        """這幾下的隨口應對換成假模型（_event_client）：預設 70 分、判「中」、歸類回第一種、潤色回 EVENT_NARRATION。"""
        MODEL["event"] = {"rate": 70, "moral": "中", "outcome": None, "narrate": EVENT_NARRATION, **say}
        try:
            yield
        finally:
            MODEL["event"] = None

    @contextlib.contextmanager
    def judged(self):
        """大場面判讀（同出陣那一軌的 judge）：難度門檻調低、模型換成回固定判讀的。"""
        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            yield
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def me(self, who: str, tag: str) -> None:
        """存檔裡事件檢定碰得到的那幾格：眼前的事件、看過的事件、體力、數值、旗標、戰報幾份、文字的事那一本的帳、最新三則紀錄的標題、
        最後三則行狀。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "pending": state.pending_event, "seen": sorted(p.seen_events), "stamina": p.stamina, "stats": dict(sorted(p.stats.items())),
            "flags": sorted(p.flags), "battles": len(state.battles), "deed": [p.deed_day, p.deed_today],
            "journal": [e.title for e in state.journal[:3]], "annals": [a.text for a in p.annals[-3:]]})

    def plain_free(self) -> str | None:
        return self.event_of("jz_gz_deserter", lambda e: e.free_text is not None and not e.free_text.outcomes
                             and not e.free_text.outcomes_only)

    def branch_free(self) -> str | None:
        return self.event_of("jz_hz_rentdebt", lambda e: e.free_text is not None and len({o.kind for o in e.free_text.outcomes}) >= 3)

    def checked(self) -> str | None:
        return self.event_of("drunk_token", lambda e: any(ch.check and not ch.combat for ch in e.choices) and bool(e.actions))

    def combat(self) -> str | None:
        return self.event_of("jizhou_altar_sermon", lambda e: any(ch.combat for ch in e.choices) and bool(e.actions))

    @staticmethod
    def paid(ch) -> bool:
        return bool(ch.condition.min_stats.get("silver")) and ch.effect.stats.get("silver", 0) < 0 and ch.check is None and ch.combat is None

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)
        if self.c.scenario.factions:
            self.place("司馬超群", None, faction="guan")  # 分岔成了要記貢獻（_deed_credit：散人不記）

    def prologue(self) -> None:
        """序章的草廬（不帶、weekend 才有）：開頭兩則事件選第一個（序章的 _apply 把「你悟得了…」那一句藏起來）、草廬四景
        （舊探索端出的事件，_present）選掉；season21、week7 是開局第一分鐘的事件卡（settle_choices 選掉）。"""
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
        self.me(who, "序章之後")

    def cards(self) -> None:
        """探索一顆碰到事件卡（各種地點：城、寺、渡、野、山、營，各抽一次事件）：端出來那一下的選單、事件卡的樣子（event_opts）、
        隨口應對的提示語、分級的那一行（/api/main）；照第一顆選掉。舊探索與三選一照它自己擲（找事件那一顆）。"""
        explore_one = _explore_rules()

        names = ["沈勝衣", "白玉京", "風四娘", "連城璧", "柳若松", "謝曉峰"]
        for i, (kind, loc) in enumerate(self.kind_places()):
            who = names[i % len(names)]
            if not self.place(who, loc):
                continue
            with self.draws(explore_one.EVENT):
                self.seek(who)
            self.me(who, f"{kind} {loc} 端出來的")
            self.settle(who)
            self.me(who, f"{kind} {loc} 選完")

    def check(self) -> None:
        """要檢定的選項：成（rules.check_chance 定成 1）、敗（定成 0）各一次；成了串到下一則（effect.next_event：_apply 端出來）、
        敗了串到下一則（fail_effect.next_event）也各一次（醉漢那一則兩條都有）。"""
        ev = self.checked()
        emit("要檢定的事件", ev)
        alone = lambda ch: ch.check is not None and ch.combat is None and not ch.effect.next_event and not ch.fail_effect.next_event  # noqa: E731
        for who, value, tag in (("沈勝衣", 1.0, "成"), ("白玉京", 0.0, "敗")):
            if self.card(who, ev):
                with self.odds(value):
                    self.press(who, alone, f"檢定{tag}")
                self.me(who, f"檢定{tag}之後")
        for who, value, test, tag in (("風四娘", 1.0, lambda ch: ch.check is not None and bool(ch.effect.next_event), "成了串下去"),
                                      ("連城璧", 0.0, lambda ch: ch.check is not None and bool(ch.fail_effect.next_event), "敗了串下去")):
            if self.card(who, ev):
                with self.odds(value):
                    self.press(who, test, tag)
                self.me(who, tag)
                self.settle(who)

    def pay(self) -> None:
        """付錢的選項（condition.min_stats.silver＝價錢、effect 扣銀兩）：錢剛好夠，那一顆在、按下去扣錢；少一兩，那幾顆不在選單上，
        只按得到不花錢的。"""
        ev = self.event_of("beggar", lambda e: any(self.paid(ch) for ch in e.choices) and bool(e.actions))
        emit("付錢的事件", ev)
        if ev is None:
            return
        price = next(ch.condition.min_stats["silver"] for ch in self.c.events[ev].choices if self.paid(ch))
        for who, silver in (("謝曉峰", price), ("蕭秋雨", price - 1)):
            if self.card(who, ev):
                self.edit(who, lambda p, silver=silver: p.stats.__setitem__("silver", silver))
                if not self.press(who, self.paid, f"付錢（身上 {silver} 兩）"):
                    self.press(who, lambda ch: ch.check is None and ch.combat is None, "錢不夠，按不花錢的那一顆")
                self.me(who, f"付錢之後（原本 {silver} 兩）")

    def fight(self) -> None:
        """事件裡打一場（固定選項的 combat：_event_battle）：打贏、打輸各一次（team.fight 照 tier）；再一次大場面判讀（server.may_judge_fight
        認 choice:N → prepare_fight → 鎖內 _judged 用掉、_narrate 照勝負挑一版）。第三場照真的打（不定結果），那一位身法擺到 60
        （閃避的機會夾成 1，打完擺回 5）：劇情戰不閃（dodge=False；定了結果的那兩場 team.fight 在閃避之前就回了，看不出來），
        閃了的話落敗一定變僵持。"""
        ev = self.combat()
        emit("打一場的事件", ev)
        hit = lambda ch: ch.combat is not None  # noqa: E731
        self.edit("蕭秋雨", lambda p: p.stats.__setitem__("agi", 60))
        for who, tier in (("白玉京", "大勝"), ("風四娘", "落敗"), ("蕭秋雨", None)):
            if self.card(who, ev):
                with self.fights(tier):
                    self.press(who, hit, f"事件裡打一場（{tier or '照真的打'}）")
                self.me(who, f"打一場之後（{tier or '照真的打'}）")
        self.edit("蕭秋雨", lambda p: p.stats.__setitem__("agi", 5))
        with self.judged():
            if self.card("連城璧", ev):
                with self.fights("大勝"):
                    self.press("連城璧", hit, "大場面判讀")
                self.me("連城璧", "大場面之後")

    def once(self) -> None:
        """一次性事件（Event.once）：一次性奇遇必中（rare_explore_chance 換成 1）站在它的地點出門兩趟——第一趟端出來、選掉
        （_present 記進 seen_events、效果帶 once 推大勢），第二趟它不再出現（pick_event 跳過看過的一次性事件）。"""
        explore_one = _explore_rules()

        ev = self.event_of("hanshan_bell", lambda e: e.once and "explore" in e.actions and bool(e.locations))
        emit("一次性事件", ev)
        if ev is None:
            return
        for k in range(2):
            if not self.place("蕭秋雨", self.c.events[ev].locations[0]):
                return
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.seek("蕭秋雨")
            self.me("蕭秋雨", f"一次性事件那一處第 {k + 1} 趟")
            self.settle("蕭秋雨")
        emit("一次性事件看過了", ev in self.chars.load("蕭秋雨").player.seen_events)

    def trip(self) -> None:
        """走一趟途中的事件（探索一顆開著的季）：三段，第二段停在事件上（waiting），檢定定成 1、選掉，接著走完；關著的季回「此刻無法」。"""
        explore_one = _explore_rules()

        if not self.place("沈勝衣", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.EVENT, explore_one.MATERIAL), self.odds(1.0):
            self.walk("沈勝衣", 3)
        self.me("沈勝衣", "走一趟之後")

    def dead(self) -> None:
        """隨口應對、模型擋著（DeadClient：評分、歸類、判善惡、潤色全丟連線錯誤）：沒有分岔的那一則退回 40、照屬性修正擲；有分岔的
        （分岔開著的季）退回最後一種、必成，關著的季照舊用 stat 擲。被擋下來的：寫太長（21 字）、眼前沒有事件、這一則沒有隨口應對。"""
        plain, branch = self.plain_free(), self.branch_free()
        emit("隨口應對的事件", {"plain": plain, "branch": branch})
        for who, ev in (("謝曉峰", plain), ("蕭秋雨", branch)):
            if self.card(who, ev):
                self.say(who, "一" * 21)
                self.say(who)
                self.me(who, "隨口應對（模型擋著）之後")
        self.edit_state("沈勝衣", lambda s: setattr(s, "pending_event", None))
        self.say("沈勝衣")
        if self.card("沈勝衣", self.event_of("beggar", lambda e: e.free_text is None)):
            self.say("沈勝衣")
            self.settle("沈勝衣")

    def half(self) -> None:
        """前半的最後一段（半舊半新的切點）：五張事件卡等回答——白玉京是舊程式串出來的（要檢定的那一顆成了、effect.next_event 由 _apply
        端出來；測試內容沒有的話擺不必檢定的串接）、柳若松是舊程式出門一趟抽到事件端出來的（_present）、風四娘有分岔的隨口應對、
        連城璧要打一場、謝曉峰沒有分岔的隨口應對（後三張直接擺上）。"""
        explore_one = _explore_rules()

        chain = self.event_of("drunk_token", lambda e: any(ch.check is not None and ch.effect.next_event for ch in e.choices)) or \
            self.first_event(lambda e: any(ch.effect.next_event for ch in e.choices))
        if self.card("白玉京", chain):
            with self.odds(1.0):
                self.press("白玉京", lambda ch: bool(ch.effect.next_event), "串出下一則")
        ev = self.combat()
        if self.place("柳若松", self.c.events[ev].locations[0] if ev and self.c.events[ev].locations else None):
            with self.draws(explore_one.EVENT):
                self.seek("柳若松")
        self.card("風四娘", self.branch_free())
        self.card("連城璧", self.combat())
        self.card("謝曉峰", self.plain_free())
        for who in ("白玉京", "柳若松", "風四娘", "連城璧", "謝曉峰"):
            self.me(who, "等回答")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        """新程式接手前半留下的五張卡：串出來的那一則照第一顆選（檢定定成 0：敗）、探索端出來的照第一顆選、有分岔的那一則寫一句
        （假模型歸到掏錢那一種、身上錢夠）、要打的那一則打一場大場面（判讀、打贏）、沒有分岔的那一則寫一句（假模型 100 分、潤色）。"""
        with self.odds(0.0):
            self.settle("白玉京")
        self.me("白玉京", "新程式選完串出來的")
        self.settle("柳若松")
        self.me("柳若松", "新程式選完探索端出來的")
        self.edit("風四娘", lambda p: p.stats.__setitem__("silver", 40))
        branch = self.branch_free()
        cost = next((o.id for o in self.c.events[branch].free_text.outcomes if o.kind == "cost"), None) if branch else None
        with self.model(rate=70, outcome=cost):
            self.say("風四娘")
        self.me("風四娘", "新程式回答分岔")
        with self.judged(), self.fights("大勝"):
            self.press("連城璧", lambda ch: ch.combat is not None, "新程式打那一場")
        self.me("連城璧", "新程式打完")
        with self.model(rate=100):
            self.say("謝曉峰")
        self.me("謝曉峰", "新程式回答隨口應對")

    def said(self) -> None:
        """沒有分岔的隨口應對（假模型）：100 分（夾成 85）、0 分（夾成 5），潤色接在「你：「…」」後面；潤色把結果句整句寫進去了
        （FB-124：潤色＝固定的那一句＋成功的結果句）就拿掉引擎那一行。"""
        plain = self.plain_free()
        if plain is None:
            emit("這份內容沒有隨口應對", None)
            return
        told = EVENT_NARRATION + self.c.events[plain].free_text.effect.text
        for who, rate, narrate in (("沈勝衣", 100, EVENT_NARRATION), ("白玉京", 0, EVENT_NARRATION), ("柳若松", 100, told)):
            if self.card(who, plain):
                with self.model(rate=rate, narrate=narrate):
                    self.say(who)
                self.me(who, f"隨口應對 {rate} 分之後")

    def evil(self) -> None:
        """判成惡行而且擲中了（FB-223）：沒有分岔的那一則，假模型 100 分、判「惡」——成功效果換成惡行的版本、行狀寫「行了一件惡事」、
        潤色照惡行寫、換掉 EVIL_DONE 那一句；有分岔的那一則歸到最後一種（走開）、判「惡」（分岔關著的季照舊用 stat 擲）。"""
        from tianxia import event_llm

        plain, branch = self.plain_free(), self.branch_free()
        leave = self.c.events[branch].free_text.outcomes[-1].id if branch else None
        for who, ev, outcome in (("連城璧", plain, None), ("蕭秋雨", branch, leave)):
            if self.card(who, ev):
                with self.model(rate=100, moral=event_llm.MORAL_EVIL, outcome=outcome):
                    self.say(who)
                self.me(who, "判成惡行之後")

    def branches(self) -> None:
        """隨口應對的分岔四條（分岔開著的季；關著照舊用 stat 擲）：司馬超群（官軍：成了記貢獻 _deed_credit）——掏錢那一種身上錢不夠
        （回 NOT_ENOUGH_SILVER、事件還停著）、錢夠（必成）；檢定那一種 100 分、0 分；打仗那一種打贏、打輸。"""
        branch = self.branch_free()
        emit("分岔的事件", branch)
        if branch is None:
            return
        kinds = {}
        for o in self.c.events[branch].free_text.outcomes:
            kinds.setdefault(o.kind, o.id)
        who = "司馬超群"
        for silver in (0, 40):
            if self.card(who, branch):
                self.edit(who, lambda p, silver=silver: p.stats.__setitem__("silver", silver))
                with self.model(rate=70, outcome=kinds.get("cost")):
                    self.say(who)
                self.me(who, f"掏錢那一種（身上 {silver} 兩）")
        for rate in (100, 0):
            if self.card(who, branch):
                with self.model(rate=rate, outcome=kinds.get("check")):
                    self.say(who)
                self.me(who, f"檢定那一種（{rate} 分）")
        for tier in ("大勝", "落敗"):
            if self.card(who, branch):
                with self.model(rate=70, outcome=kinds.get("combat")), self.fights(tier):
                    self.say(who)
                self.me(who, f"打仗那一種（{tier}）")

    def tiered(self) -> None:
        """第二階事件（州郡大事）擺到眼前：/api/main 的 event_tier 寫那一行與框色；要檢定的那一顆成（check 的 tier 是 2：不吃減法季的放寬）。"""
        ev = self.event_of("t2_baima_escort", lambda e: e.tier == 2)
        emit("第二階事件", ev)
        if self.card("連城璧", ev):
            with self.odds(1.0):
                self.press("連城璧", lambda ch: ch.check is not None, "第二階的檢定")
            self.me("連城璧", "第二階之後")

    def tale(self) -> None:
        """說書的事件了結時多一句口訣（_tale_clue：Config.secrets.tale_chance、鑄器那一句 Config.forge_secrets.tale_chance 都換成 1，
        擲的是自己的雜湊、不動 Game.rng）。"""
        tales = [e for e in self.c.config.secrets.tale_events if e in self.c.events]
        ev = next((e for e in tales if any(ch.check for ch in self.c.events[e].choices)), tales[0] if tales else None)
        emit("說書的事件", ev)
        if self.card("風四娘", ev):
            with self.tweak(self.c.config.secrets, tale_chance=1.0), self.tweak(self.c.config.forge_secrets, tale_chance=1.0), \
                    self.odds(1.0):
                self.press("風四娘", lambda ch: ch.combat is None and not ch.condition.min_stats, "說書")
            self.me("風四娘", "說書之後")

    def social(self) -> None:
        """交友（舊的 _encounter 沒碰上人物、一類一顆的「一次性」「結識」那兩種 → _present(事件, "socialize")）：在四處按交友，
        端出事件就選掉、開了對話就告辭；按不了的寫下來（一類一顆的季，這裡沒有能說上話的人是灰的）。"""
        for who, loc in (("謝曉峰", "yingchuan"), ("蕭秋雨", "market_town"), ("沈勝衣", "zhuo_county"), ("白玉京", "wan_city"),
                         ("柳若松", "yingshui")):
            if not self.place(who, loc):
                continue
            if not self.options(who).get("act:socialize", {}).get("enabled"):
                emit(f"{who} 在 {loc} 按不了交友", None)
                continue
            self.choose(who, "act:socialize")
            for _ in range(4):
                opts = self.options(who)
                if "talk:leave" in opts:
                    self.choose(who, "talk:leave")
                elif any(i.startswith("choice:") for i in opts):
                    self.settle(who)
                else:
                    break
            self.me(who, f"{loc} 交友之後")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(11)、時鐘一輪推五分）：同一個資料庫補四個假人，眼前各擺一張
        事件卡（要檢定的、付錢的、要打的、有隨口應對的：假人照 bot_policy.score 的 choice 那一段挑、不寫字），站在事件多的地點，
        跑 SB_EVENT_TICKS 輪（探索端出來的事件也一樣選）。整季機器人的 bot.pick 在事件卡上挑哪一顆也寫下來。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        paid = self.event_of("beggar", lambda e: any(self.paid(ch) for ch in e.choices) and bool(e.actions))
        cards = [self.checked(), paid, self.combat(), self.plain_free()]
        sides = [f.id for f in self.c.scenario.factions]
        spare = sorted(self.c.locations)
        names = [name for name, _ in self.BOT_SEATS]
        for i, (name, loc) in enumerate(self.BOT_SEATS):
            loc = loc if loc in self.c.locations else spare[i % len(spare)]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            side = sides[i % len(sides)] if sides else None
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            g.state.pending_event = cards[i]
            self.chars.save(g.state)
        self.begin()
        first = Game(self.c, self.chars.load(names[0]), world=self.world)
        emit("整季機器人在事件卡上挑", bot.pick(first, first.options(odds=False), random.Random(0)))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(11), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)  # 擺好的四個一直在線
        totals = Counter()
        try:
            for n in range(int(os.environ.get("SB_EVENT_TICKS", "40"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                if n == 0:  # 第一輪之後就寫：四十輪跑完，第一輪那一則早被擠出江湖紀錄（只留 30 則），卡直接寫進存檔、不在看過的事件裡
                    emit("事件假人 第一輪答了眼前的卡", self.answered(names, cards))
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        states = self.chars.all(bots_only=True)
        emit("事件假人 一輪一輪", dict(sorted(totals.items())))
        emit("事件假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("事件假人 看過的事件", {s.player.name: sorted(s.player.seen_events) for s in states})
        emit("事件假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})

    def answered(self, names: list[str], cards: list[str | None]) -> dict:
        """擺好的那幾個假人眼前那一張卡答了沒（dev/core-events-1 審查：輸出本身看不出四個假人答了卡）：卡還在不在眼前、
        江湖紀錄裡那一則事件的標題（「狼頭鐵牌・扶他起身，順手摸走鐵牌」：事件名・選了哪一顆）。只讀存檔。"""
        out = {}
        for name, card in zip(names, cards):
            s = self.chars.load(name)
            title = self.c.events[card].title if card in self.c.events else str(card)
            out[name] = {"卡": card, "還在眼前": s.pending_event == card,
                         "紀錄": [e.title for e in s.journal if e.title == title or e.title.startswith(title + "・")]}
        return out

    def season(self) -> None:
        """收季、開下一季：眼前擺著一張事件卡的人（休季時選單只剩休季那一顆、隨口應對被擋；開下一季之後那一張照換季的規矩）。"""
        self.card("沈勝衣", self.checked())
        self.do(ADMIN, "end_season")
        self.main("沈勝衣")
        self.say("沈勝衣")
        self.do(ADMIN, "next_season")
        self.main("沈勝衣")
        self.me("沈勝衣", "換季之後")


def _events_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：事件選項按下去那一行（_choose；搬之前在 engine.py、之後在 tianxia/core/event_check.py）
_events_register_track("events", EventScenario, (("tianxia/core/event_check.py", "tianxia/engine.py"),
                                                  ('msgs = [f"▸ {choice.text}"]', 'msgs = [f"▸ {choice.text}！"]')), "week7")


# ═══════════════════════════ sortie（全部拆包第 17 批「出陣三」，dev/sortie-3）：train 一軌 ═══════════════════════════
# 序章雪恥、舊遊歷、跟自家隊伍操練、守勢（act:duty）、遊歷推大勢收進出陣包（計畫 docs/superpowers/plans/2026-11-01-出陣包-第3批.md）。
# 這一段整塊是這一批的：接在檔尾、最後兩行登記（_register_track、假人的 --seats train），PM 合的時候不跟別人的行穿插。


class TrainScenario(Scenario):
    """出陣三（--track train，自己一個資料庫）：act:train 那一格的另一半與守勢。
    - 序章雪恥（none、weekend 有序章）：照寫好的險勝；另一個新人把那一步的結果在記憶體裡換成落敗（打輸那一支）。
    - 舊遊歷（地盤關著的 none、test）：散人在長社（必敗先問、打輸、照寫好的打贏推大勢與戰後事件）、潁水河畔（不推大勢）；地盤開著的季是灰格。
    - 跟自家隊伍操練：none 的官軍大營（全是自己人「操練・零風險」）、南陽郊野（兩種都有）、黃巾別部營寨；test 把湖邊的水寇記憶體裡換成官軍；
      地盤開著的季（weekend 倍數 1、season21、week7 小於 1）把汝南荒野的對手記憶體裡換成自家的，出陣攻打撞上自己人改操練（推大勢走 _drill_push）；
      兩種都有：汝南荒野的中立駐軍在記憶體裡多塞一路自家的（原本那一路照舊是外人）。
    - 遊歷推大勢：官軍照寫好的打贏兩下（減法季關著的 none、test；減法季開著的 season21、week7 由上面的操練推），每一下寫各線與零頭。
    - 並肩出陣（_act 的 train 那一支包在外面的）：沒商量、商量沒成、商量成了。
    - 大場面判讀：舊遊歷的 _train_pick、操練不判、約戰開著不判、出陣照判。
    - 守勢（weekend、season21、week7）：一天第一次（前半）、同一天第二次（後半第一件事：新程式接舊程式記到一半的那一天）、中立地灰著、
      weekend 次數用完灰著、約戰開著隔天照記。約戰開著的季按一次出陣那一格（卡）。
    半舊半新切在雪恥打完、還沒配點，與守勢一天記了一次的那一刻。"""

    PLAYERS = {"官甲": "guan", "官乙": "guan", "黃甲": "huang"}
    RANGER = "遊俠"
    NEWBIES = ("雪恥甲", "雪恥乙")
    PHASES_FIRST = ["setup", "hut_win", "hut_lose", "duty_first"]
    PHASES_SECOND = ["duty_second", "hut_after", "resume", "wander", "drill", "push", "backed", "judge", "duty_more", "card"]

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
        for who in [*self.NEWBIES, self.RANGER, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        for who in [self.RANGER, *self.PLAYERS]:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        factions = {f.id: f for f in self.c.scenario.factions}
        for who, side in self.PLAYERS.items():
            if side not in factions or not factions[side].join_at or not self.place(who, factions[side].join_at[0]):
                continue
            self.choose(who, f"faction:{side}")
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        for who in [self.RANGER, *self.PLAYERS]:
            self.place(who, None)  # 體力補滿、過了新手期

    # ── 小工具 ──

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟遊歷、操練、守勢有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"), "exp": p.member.exp,
            "level": p.member.level, "injury": p.member.injury, "sortie_day": p.sortie_day, "sorties_today": p.sorties_today,
            "duty_day": p.duty_day, "duties_today": p.duties_today, "contrib": p.contrib, "pushed": dict(sorted(p.pushed.items())),
            "pending": state.pending_event, "step": p.tutorial_step, "battles": len(state.battles),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def trends(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"大勢 {tag}", {"trends": dict(sorted(s.trends.items())), "accum": dict(sorted(s.trend_accum.items()))})

    def today(self) -> int:
        """此刻的回體丹那一天（Game._pill_day；台灣 00:00 換日）。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        shell.now = CLOCK[0]
        return shell._pill_day()

    def train(self, who: str, tag: str, times: int = 1, win: bool = False) -> None:
        """按 act:train（先看鈕與底下那一行；每一下補滿體力、今天出陣的次數歸零〔出陣開著的季：這一軌要的是遊歷、操練那幾支，
        次數用完在 duty_more 另外擺〕、之後把戰後事件照第一個選項選掉）。win：照寫好的打贏（winning）。"""
        for i in range(times):
            self.place(who, None)
            self.edit(who, lambda p: setattr(p, "sorties_today", 0))
            view = self.main(who)
            emit(f"{tag} 的 act:train（第 {i + 1} 下）", self.ids(view).get("act:train"))
            emit(f"{tag} 那一行", (view.get("action_notes") or {}).get("act:train"))
            option = self.ids(view).get("act:train")
            if not option or not option.get("enabled"):
                return
            if win:
                with self.winning():
                    self.choose(who, "act:train")
            else:
                self.choose(who, "act:train")
            self.settle_choices(who)
            self.state_of(who, f"{tag} 之後（第 {i + 1} 下）")

    def duty(self, who: str, tag: str) -> None:
        view = self.main(who)
        option = self.ids(view).get("act:duty")
        emit(f"{tag} 的 act:duty", option)
        if option and option.get("enabled"):
            self.choose(who, "act:duty")
            self.settle_choices(who)
        self.state_of(who, f"{tag} 之後")

    def with_duty(self) -> bool:
        from tianxia import orders
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        return orders.active(shell.state, self.c)

    @contextlib.contextmanager
    def factions_of(self, **changes):
        """記憶體裡把幾支隊伍換成別的陣營（做完換回來；兩份程式同一套）。"""
        before = {sid: self.c.squads[sid].faction for sid in changes if sid in self.c.squads}
        for sid in before:
            self.c.squads[sid].faction = changes[sid]
        emit("換陣營的隊伍", {sid: changes[sid] for sid in sorted(before)})
        try:
            yield
        finally:
            for sid, faction in before.items():
                self.c.squads[sid].faction = faction

    # ── 序章雪恥 ──

    def walk_hut(self, who: str) -> bool:
        """序章走到雪恥那一步（同 Scenario.prologue，全走 API）；沒有序章的季回 False。"""
        from tianxia import sensing

        view = self.main(who)
        if not view.get("prologue"):
            emit(f"{who}：這一季沒有序章", None)
            self.settle_choices(who)
            return False
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
        return True

    def hut_fight(self, who: str, tag: str) -> None:
        view = self.main(who)
        emit(f"{tag} 的 act:train", self.ids(view).get("act:train"))
        emit(f"{tag} 那一行", (view.get("action_notes") or {}).get("act:train"))
        self.choose(who, "act:train")
        self.state_of(who, f"{tag} 之後")

    def hut_win(self) -> None:
        if self.walk_hut(self.NEWBIES[0]):
            self.hut_fight(self.NEWBIES[0], "雪恥（照寫好的險勝）")

    def hut_lose(self) -> None:
        if not self.walk_hut(self.NEWBIES[1]):
            return
        step = next(s for s in self.c.tutorial.steps if s.force_tier)
        before, step.force_tier = step.force_tier, "落敗"
        try:
            self.hut_fight(self.NEWBIES[1], "雪恥（換成落敗）")
        finally:
            step.force_tier = before

    def hut_after(self) -> None:
        """後半：雪恥打完、還沒配點的那兩位接著走（新程式接舊程式的序章）：配點、熔蠻牛拳。"""
        for who in self.NEWBIES:
            self.relogin(who)
        for who in self.NEWBIES:
            if not self.main(who).get("prologue"):
                continue
            self.do(who, "allocate", {"stat": "str"})
            self.call(who, "POST", "/api/menxia/melt", {"art": "manniu_quan"})
            self.state_of(who, "配點、熔煉之後")

    # ── 守勢 ──

    def duty_first(self) -> None:
        """官甲在自家的涿郡守勢（這一天第一次）。約戰開著（season21、week7）：記一點貢獻；weekend：佔一次出陣、推所在戰線、記守城。"""
        if not self.with_duty():
            emit("這一季沒有守勢", None)
            return
        if self.place("官甲", "zhuo_county"):
            self.duty("官甲", "守勢第一次")

    def duty_second(self) -> None:
        """後半第一件事：同一天再守一次（約戰開著不再記貢獻；weekend 再佔一次出陣）。"""
        self.relogin("官甲")
        if not self.with_duty():
            return
        if self.place("官甲", "zhuo_county"):
            self.duty("官甲", "守勢第二次（同一天）")

    def duty_more(self) -> None:
        """中立地灰著（領地爭奪：不是自家的區塊）；weekend 次數用完灰著；約戰開著的季隔天照記一點。"""
        if not self.with_duty():
            return
        from tianxia import territory

        self.set_duel(self.duel_default is not None)
        if self.place("官甲", "runan_wilds"):
            self.duty("官甲", "中立地的守勢")
            self.choose("官甲", "act:duty")
        if territory.on(self.c) and self.profile not in DUEL_PROFILES and self.place("官乙", "zhuo_county"):
            today = self.today()
            self.edit("官乙", lambda p: (setattr(p, "sortie_day", today), setattr(p, "sorties_today", self.c.config.sortie.per_day)))
            self.duty("官乙", "次數用完的守勢")
            self.choose("官乙", "act:duty")
        if self.profile in DUEL_PROFILES and self.place("官甲", "zhuo_county"):
            self.edit("官甲", lambda p: setattr(p, "duty_day", p.duty_day - 1))  # 昨天記的：今天照記
            self.duty("官甲", "隔天的守勢")

    # ── 舊遊歷、操練、推大勢 ──

    def wander(self) -> None:
        """散人的遊歷：長社（必敗先問、打輸、照寫好的打贏推大勢、戰後事件）、潁水河畔（不推大勢）；地盤開著的季是灰的「散人不能出陣」。"""
        self.set_duel(False)
        if self.place(self.RANGER, "changshe"):
            self.train(self.RANGER, "長社", times=2)
            self.train(self.RANGER, "長社（照寫好的打贏）", times=2, win=True)
        if self.place(self.RANGER, "yingshui"):
            self.train(self.RANGER, "潁水河畔")
        self.trends("散人遊歷之後")

    def drill(self) -> None:
        """跟自家隊伍操練（_drill、_drill_push、drill_scale）。"""
        from tianxia import territory

        self.set_duel(False)
        if self.profile == "test":
            self.place("官乙", "lake", faction="guan")  # 測試內容沒有陣營：記一個「官軍」、湖邊的水寇在記憶體裡也記成官軍
            with self.factions_of(thug="guan"):
                self.train("官乙", "湖邊的自己人", times=3)
            self.place("官乙", None, faction=None)
        elif not territory.on(self.c):
            if self.place("官乙", "guan_camp"):
                self.train("官乙", "官軍大營", times=2)
            if self.place("官乙", "nanyang_wilds"):
                self.train("官乙", "南陽郊野（兩種都有）", times=3)
            if self.place("黃甲", "huangjin_camp"):
                self.train("黃甲", "黃巾別部營寨")
        else:  # 汝南荒野（開季中立）站的那幾路（territory.squads_at：中立駐軍與流寇野獸）在記憶體裡換成官軍
            foes = sorted(territory.squads_at(self.world.get_season(), self.c, "runan_wilds"))
            with self.factions_of(**{sid: "guan" for sid in foes}):
                if self.place("官乙", "runan_wilds"):
                    self.train("官乙", "汝南荒野全是自己人（出陣）", times=2)
            # 兩種都有（修正輪）：汝南荒野只站一路（nz_kuibing），換第一路就是全部，跟「全是自己人」一模一樣、鈕上沒有「或與自己人操練」。
            # 改成 nz_kuibing 照舊是外人，中立駐軍那一格在記憶體裡多塞一路自家的（官軍最弱、不是大場面的那一路）：出陣攻打的池子兩路，
            # rng 在自己人與外人之間挑。（不能拿站兩路的區塊換一路的陣營：Location.enemies 裡的換了陣營就不算中立的流寇，
            # conquest.neutral_squads 把它濾掉，池子又剩一路。）
            with self.neutral_plus("runan_wilds", self.weakest("guan")):
                if self.place("官乙", "runan_wilds"):
                    self.train("官乙", "汝南荒野兩種都有（出陣）", times=8)
        self.trends("操練之後")

    def weakest(self, side: str) -> str:
        """這一邊最弱、不是大場面的那一路隊伍（兩份程式同一份內容，挑到的一樣）。"""
        from tianxia import styles

        return min((q.difficulty, sid) for sid, q in self.c.squads.items() if q.faction == side and not styles.is_big(self.c, q))[1]

    @contextlib.contextmanager
    def neutral_plus(self, loc: str, sid: str):
        """記憶體裡在開季中立的這一塊的中立駐軍（Scenario.territory.neutral_garrison）多塞一路（做完拿掉；兩份程式同一套）。"""
        garrison = self.c.scenario.territory.neutral_garrison
        before = garrison.get(loc)
        garrison[loc] = [*(before or []), sid]
        emit(f"{loc} 的中立駐軍多一路", {"squad": sid, "garrison": garrison[loc]})
        try:
            yield
        finally:
            if before is None:
                garrison.pop(loc, None)
            else:
                garrison[loc] = before

    def push(self) -> None:
        """遊歷推大勢（減法季關著：none、test）：官甲照寫好的打贏兩下，長社（test 是湖邊）推往自己陣營的目標（test 沒有陣營：照地點的方向）。"""
        from tianxia import territory

        if territory.on(self.c):
            return
        if self.place("官甲", "changshe"):
            self.train("官甲", "長社（官軍打贏）", times=2, win=True)
        self.trends("遊歷打贏之後")

    def backed(self) -> None:
        """並肩出陣（Game._act 的 train 那一支包在外面的）：今天答應陪你、你在他那一帶——沒商量 +30%、商量沒成打空、商量成了 +60%。"""
        from tianxia.rules import game_day
        from tianxia.state import ParleyBacking

        self.set_duel(False)
        figure = next(iter(self.c.characters))
        loc = "changshe" if self.profile in ("none", "test") else "runan_wilds"
        for plan in (None, False, True):
            if not self.place("官甲", loc):
                return
            self.main("官甲")
            # 這一季此刻是第幾天：讀全服的季（同 Game.for_world）。角色檔裡的 world 是殘根（time 0、season21 的章 False），
            # 照它算永遠是第 1 天——season21 開季那天是第 7 天，並肩那一支在 season21 一次都走不到（修正輪）
            day = game_day(self.c, self.world.get_season())
            self.edit("官甲", lambda p, plan=plan, day=day: setattr(p, "parley_backing", ParleyBacking(figure=figure, region=None, day=day, plan=plan)))
            self.train("官甲", f"並肩出陣（打法 {plan}）")

    @contextlib.contextmanager
    def judge_calls(self, tag: str):
        """這一段伺服器在鎖外叫了哪幾路大場面判讀（server.prepare_fight → fight_llm.judge），段落結束寫出來。修正輪加的：操練、
        約戰開著時那張卡都不寫判讀的字（判讀回來之後操練照樣操練、約戰照樣只回卡），JudgeClient 又是立刻回，叫沒叫光看回應與資料庫
        看不出來——train_squad 的約戰那道關拿掉、操練那道關拿掉都比不出差（審查員量的）。"""
        from tianxia import fight_llm

        real, calls = fight_llm.judge, []

        def judge(client, request, *args, **kwargs):
            calls.append(request.squad_id)
            return real(client, request, *args, **kwargs)

        fight_llm.judge = judge
        try:
            yield
        finally:
            fight_llm.judge = real
            emit(f"{tag} 叫了大場面判讀", calls)

    def judge(self) -> None:
        """大場面判讀（server.may_judge_fight → prepare_fight → Game._fight_squad）：舊遊歷照 _train_pick 挑的那一路判；操練不判；
        約戰開著時出陣那一格是卡、不判；出陣照判。每一下寫叫了哪幾路（judge_calls）。"""
        from tianxia import territory

        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            if not territory.on(self.c):
                if self.place(self.RANGER, "yingshui"):
                    with self.judge_calls("大場面的舊遊歷"):
                        self.train(self.RANGER, "大場面的舊遊歷")
                if self.profile == "none" and self.place("官乙", "guan_camp"):
                    with self.judge_calls("大場面的操練"):
                        self.train("官乙", "大場面的操練")
            else:
                if self.profile in DUEL_PROFILES:
                    self.set_duel(True)
                    if self.place("官甲", "runan_wilds"):
                        with self.judge_calls("大場面、約戰開著"):
                            self.train("官甲", "大場面、約戰開著")
                self.set_duel(False)
                if self.place("官甲", "runan_wilds"):
                    with self.judge_calls("大場面的出陣"):
                        self.train("官甲", "大場面的出陣")
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def card(self) -> None:
        """約戰開著的季（season21、week7）按一次出陣那一格：打開出陣前那張卡（不寫紀錄）。"""
        if self.profile not in DUEL_PROFILES:
            return
        self.set_duel(True)
        if self.place("官乙", "runan_wilds"):
            self.train("官乙", "約戰開著的出陣那一格")

    def resume(self) -> None:
        self.set_duel(False)
        self.login_all()


# 舊遊歷與操練（none）、守勢與出陣（weekend）、約戰開著的守勢（week7）。測試內容的 BotRunner 一個都不上線（acted 0），不跑
TRAIN_BOT_PROFILES = ("none", "weekend", "week7")
TRAIN_SEATS = [("操兵甲", "guan", "guan_camp"), ("操兵乙", "guan", "changshe"), ("操兵丙", "huang", "huangjin_camp"),
               ("操兵丁", "huang", "nanyang_wilds"), ("操兵戊", "guan", "zhuo_county")]
# 修正輪：weekend（地盤開著、約戰關著）照原樣擺，BotRunner 336 次行動一則出陣、守勢都沒有（只有城裡操練），三軌的假人也沒有一個按過非約戰的
# 守勢。這兩位那一顆照原本的分數再加一道軍令的分（bot_policy.ORDER_SCORE；原本是 None〔不會按〕的照舊不按）：涿郡（官軍自家的區塊）的守勢走
# 非約戰那一支（佔出陣次數、推線、記守城、次數用完灰掉），南陽郊野的黃巾出陣經 train_fight。兩份程式同一套。
TRAIN_FOCUS = {"weekend": {"操兵戊": "act:duty", "操兵丁": "act:train"}}


@contextlib.contextmanager
def _train_focus(profile: str):
    from tianxia import bot_policy

    focus = TRAIN_FOCUS.get(profile, {})
    real = bot_policy.score

    def score(game, option, bot_profile):
        value = real(game, option, bot_profile)
        if value is not None and focus.get(game.state.player.name) == option.id:
            value += bot_policy.ORDER_SCORE
        return value

    if focus:
        bot_policy.score = score
    try:
        yield
    finally:
        bot_policy.score = real


def train_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """出陣三的假人（--seats train）：整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）與伺服器假人（BotRunner＋bot_policy.take_turn，
    random.Random(7)、假時鐘、每一輪 +300 秒）五個擺在官軍大營、長社、黃巾別部營寨、南陽郊野、涿郡（測試內容擺在湖邊、小鎮）跑 N 輪：
    寫存檔、戰報、紀錄標題（遊歷、操練、守勢、出陣各幾則）、大勢與資料庫的雜湊。"""
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

    def content_of():
        if profile == "test":
            return load_content(root / "tests" / "fixtures" / "content")
        return load_content(root / "content", profile=None if profile == "none" else profile)

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title.partition("・")[0] for s in states for e in s.journal).items()))

    def tagged(states) -> dict:
        """這一包的那幾種紀錄照（標題頭、標籤）數（修正輪）：標題頭分不出兩種操練——城裡操練（act:drill，training 那一包）是標題頭「操練」、
        標籤「校場過招」，這一包跟自家隊伍操練是標題頭「遊歷」或「出陣」、標籤「操練」；打仗的標籤是勝負加對手。"""
        heads = ("遊歷", "出陣", "雪恥", "操練", "巡哨", "傳道", "保境安民")
        found = Counter(f"{e.title.partition('・')[0]}／{e.tag}" for s in states for e in s.journal if e.title.partition("・")[0] in heads)
        return dict(sorted(found.items()))

    content = content_of()
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("出陣三整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("出陣三整季機器人 紀錄標題", titles([game.state]))
    emit("出陣三整季機器人 這一包的紀錄（標題頭／標籤）", tagged([game.state]))
    emit("出陣三整季機器人 戰報", hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in game.state.battles], ensure_ascii=False)
                                               .encode("utf-8")).hexdigest())
    emit("出陣三整季機器人 大勢", dict(sorted(world.get_season().trends.items())))
    emit("出陣三整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = content_of()
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("操兵甲", None, "lake"), ("操兵乙", None, "town")] if profile == "test" else TRAIN_SEATS
    for i, (name, side, loc) in enumerate(seats):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    emit("出陣三假人 偏好", TRAIN_FOCUS.get(profile, {}))
    with _train_focus(profile):
        for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
            clock[0] += 300.0
            report = runner.tick()
            totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    emit("出陣三假人 一輪一輪", dict(sorted(totals.items())))
    emit("出陣三假人 紀錄標題", titles(states))
    emit("出陣三假人 這一包的紀錄（標題頭／標籤）", tagged(states))
    emit("出陣三假人 戰報", {s.player.name: hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in s.battles], ensure_ascii=False)
                                                           .encode("utf-8")).hexdigest() for s in states})
    emit("出陣三假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("出陣三假人 大勢", dict(sorted(world.get_season().trends.items())))
    emit("出陣三假人 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "出陣三假人", dict(totals), tagged(states), "整季機器人", tagged([game.state]))


_sortie3_bot_runs = _bot_runs


def _bot_runs(tracks: list[str]) -> list[tuple[str, str]]:  # noqa: F811  （sortie 第 17 批：train 那一軌的假人接在後面）
    return _sortie3_bot_runs(tracks) + ([("train", p) for p in TRAIN_BOT_PROFILES] if "train" in tracks else [])


def _sortie3_entry(main_fn):
    """bots ... --seats train（這一軌的假人）；其餘照原本的 main（一個字不動）。"""

    def entry(argv: list[str] | None = None) -> int:
        args = list(sys.argv[1:] if argv is None else argv)
        if args[:1] == ["bots"] and "--seats" in args and args[args.index("--seats") + 1:args.index("--seats") + 2] == ["train"]:
            ap = argparse.ArgumentParser()
            ap.add_argument("cmd")
            ap.add_argument("root")
            ap.add_argument("profile", choices=PROFILES)
            ap.add_argument("out")
            ap.add_argument("--tmp", required=True)
            ap.add_argument("--seats")
            a = ap.parse_args(args)
            train_bots_run(Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
            sys.stdout.flush()
            os._exit(0)
        return main_fn(argv)

    return entry


main = _sortie3_entry(main)
# 改一個字（selftest）：操練那一句（搬之前在 engine.py 的 _drill、之後在 features/sortie/train_actions.py），none 的官軍大營操練到
_register_track("train", TrainScenario, (("tianxia/features/sortie/train_actions.py", "tianxia/engine.py"),
                                         ("軍心為之一振。", "軍心為之一振！")), "none")


# ═══════════════════════════ guide：新手引導一軌（全部拆包第 22 批，dev/guide-1） ═══════════════════════════
# 引導框、碰到才說、新手目標、開局第一分鐘、入伍段的本體從 engine.py 搬進新包 tianxia/features/guide/（tianxia/guide.py、hints.py、
# newbie.py、opening.py、enlist.py 留成別名；計畫 docs/superpowers/plans/2026-11-01-新手引導包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後一行登記（_guide_register_track），PM 合的時候不跟別人的行穿插。


class GuideScenario(Scenario):
    """新手引導（全部拆包第 22 批；--track guide，自己一個資料庫）。六個網頁上建的新角色（/api/character：Game.new(prologue=True)）——
    葉孤城從開局走：week7、season21 是城門口三選一（還沒選就簽到被擋那一句、選了之後人物的信與護送委託、收起信）；不帶與 weekend 是草廬
    （一步一步看框：遇險、拜師、看修練頁、四景、裝意境、練到第三成、揣摩、服丹，**前半停在這裡**，後半雪恥、配點、熔煉、出師、
    初入江湖的頭幾步、/api/prologue 重看序章）；測試內容是說書人三步（探索、去湖邊、看地圖）與結語「知道了」。
    江小魚碰到才說：擺出狀態（兩個意境、點數沒配、看過事件）一次觸發一串，一條一條上框、按「知道了」（前半最後一條上框沒按），
    後半再擺內傷＋眼前一則事件（排著不上框）、療好再同步（排著的拿掉）、交友（事件型的）。
    花無缺新手目標：就當散人（第一條，**切在這裡**），後半升到第 5 級（第二條）。燕南天、鐵心蘭入伍段：投靠、看軍令卡（**前半停在第一道
    軍令**），後半燕南天照選單發光的那一顆出一次力、按掉結尾；鐵心蘭一週沒做完被收。蘇櫻：不再提示、看地圖、看修練頁（序章外）、
    重看序章，後半略過新手引導（草廬裡略過拿出師的盤纏）、再按一次、打開提示、知道了。假人：Game.new(graduated=True)（草廬的季走
    _graduate、開局的季站在城門口挑一顆；標成假人才同步，第一位交友一次）＋BotRunner 三十輪。最後收季、開下一季（開季那一句 s_return、
    再投靠的 s_rejoin）。
    沒有開局、草廬、陣營、入伍段、提示的設定寫「沒有」略過，同一串 API 照打。"""

    WALKER, ENLIST, LATE, HINTS, GOALS, SKIP = "葉孤城", "燕南天", "鐵心蘭", "江小魚", "花無缺", "蘇櫻"
    BOT_SEATS = ["引甲", "引乙", "引丙"]
    PHASES_FIRST = ["setup", "gate", "hut", "hints", "goals", "enlist", "skip", "half"]
    PHASES_SECOND = ["resume", "hut_on", "hints_on", "goals_on", "enlist_on", "skip_on", "bots", "season"]

    def everyone(self) -> list[str]:
        return [self.WALKER, self.ENLIST, self.LATE, self.HINTS, self.GOALS, self.SKIP]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    def me(self, who: str, tag: str) -> None:
        """存檔裡引導碰得到的那幾格：步數、所在、眼前的事件、完成列、結語、略過、入伍段、提示（說過、排著、關了沒）、新手目標的兩本帳、
        丹與銀兩、陣營、旗標、信、最新三則紀錄（標題、標記、引導那幾行）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "step": p.tutorial_step, "loc": p.location, "journey": p.journey is not None, "pending": state.pending_event,
            "done": list(p.guide_done), "outro": p.guide_outro, "skipped": p.guide_skipped,
            "enlist": [p.enlist_step, p.enlist_end, p.enlist_since], "seen": sorted(p.hints_seen),
            "queue": [[n.id, n.speaker, n.text, n.shown] for n in p.hint_queue], "off": p.hints_off,
            "newbie": [sorted(p.newbie_marks), sorted(p.newbie_done)], "pills": p.stamina_pills, "silver": p.stats.get("silver", 0),
            "faction": p.faction, "flags": sorted(p.flags), "letters": [x.model_dump(mode="json") for x in p.letters],
            "journal": [[e.title, e.tag, list(e.guide)] for e in state.journal[:3]]})

    @staticmethod
    def view_of(view) -> dict:
        """GET /api/main 回的是畫面本身，POST 的動作回 {main, message}：兩種都拿到畫面。"""
        return (view.get("main", view) or {}) if isinstance(view, dict) else {}

    def in_hut(self, who: str) -> bool:
        return bool(self.view_of(self.main(who)).get("prologue"))

    def past(self, who: str) -> None:
        """引導走完（不是略過）：草廬的季直接擺到起點、步數擺到走完（草廬那幾步是葉孤城的事）；開局的季選掉城門口三選一；
        測試內容擺到走完。"""
        steps, start = len(self.c.tutorial.steps), self.c.scenario.start_location
        if self.in_hut(who):
            def fn(s) -> None:
                s.pending_event, s.player.sensing, s.player.journey = None, None, None
                s.player.location = start
                s.player.visited.add(start)
                s.player.tutorial_step = steps
            self.edit_state(who, fn)
        else:
            self.settle_choices(who)
            self.edit_state(who, lambda s: setattr(s.player, "tutorial_step", max(s.player.tutorial_step, steps)))
        self.me(who, "引導走完")

    def arrive(self, who: str, rounds: int = 40) -> None:
        """在路上的話一直同步到抵達（每一步推一分鐘）。"""
        n = 0
        while n < rounds and self.chars.load(who).player.journey is not None:
            self.main(who)
            n += 1
        emit(f"{who} 同步了 {n} 次抵達", self.chars.load(who).player.location)

    def ack(self, who: str, rounds: int, tag: str) -> None:
        """同步一次（排一條、上框）、按「知道了」，照 rounds 次。"""
        for k in range(rounds):
            self.main(who)
            self.me(who, f"{tag} 第 {k + 1} 條")
            self.do(who, "guide_ack")

    def sides(self) -> list:
        return [f for f in self.c.scenario.factions if f.join_at] if self.c.tutorial.enlist is not None else []

    def join(self, who: str, faction) -> None:
        self.place(who, faction.join_at[0])
        self.choose(who, f"faction:{faction.id}")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        self.me(who, f"投靠 {faction.id} 之後")

    # ── 前半 ──

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
        for who in self.everyone():
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            self.me(who, "建好")

    def gate(self) -> None:
        """開局第一分鐘：三選一還沒選就簽到（opening.GATE）、選第二顆（那位人物的信到、附一件護送委託）、收起信。"""
        who = self.WALKER
        o = self.c.opening
        if o is None or self.chars.load(who).pending_event != o.event:
            emit("這一季沒有開局第一分鐘", None)
            return
        self.do(who, "checkin")
        self.choose(who, "choice:1")
        self.me(who, "選完三選一")
        for letter in self.chars.load(who).player.letters:
            self.do(who, "letter_read", {"id": letter.id})
        self.me(who, "收起信")

    def hut(self) -> None:
        """草廬前七步（照 Scenario.prologue，全走 API；每一下回的 /api/main 帶著框）；測試內容是說書人第一步（探索）。"""
        from tianxia import sensing

        who = self.WALKER
        if not self.in_hut(who):
            if self.c.tutorial.location is None and self.chars.load(who).player.tutorial_step < len(self.c.tutorial.steps):
                self.choose(who, "act:explore")
                self.settle_choices(who)
                self.me(who, "說書人第一步之後")
            else:
                emit("這一季沒有草廬", None)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        self.me(who, "四景之後")
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.call(who, "POST", "/api/menxia/slot", {"art": "jichu_quanjiao", "insight": got[0]})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/forge", {"insights": [got[0], f"{got[0]}~2"]})
        self.do(who, "pill")
        self.me(who, "服丹之後")

    def hints(self) -> None:
        """碰到才說：引導走完的江小魚擺出兩個意境（h_merge）、兩點沒配（h_points）、看過一則事件（h_event_reveal）——一次同步排一條、
        上框，按「知道了」換下一條；三條之後再同步一次，最後一條上了框沒按（前半停在這裡）。"""
        who = self.HINTS
        self.past(who)
        insights = [i for i, x in self.c.insights.items()][:2]
        event = next((e for e in sorted(self.c.events) if not e.startswith(("prologue", "opening"))), None)

        def fn(p) -> None:
            p.insights.extend(i for i in insights if i not in p.insights)
            p.stat_points = 2
            p.stats["xinde"] = 999  # 心得夠自創第一門（h_create）
            if event is not None:
                p.events_seen.append(event)
        self.edit(who, fn)
        self.ack(who, 3, "提示")
        self.main(who)
        self.me(who, "上了框還沒按")

    def goals(self) -> None:
        """新手目標：引導走完、新手期裡的花無缺按任務卡的「就當散人」（side 那一條：回體丹）。前半停在這裡（八條做了一條）。"""
        who = self.GOALS
        self.past(who)
        self.do(who, "newbie_drifter")
        self.me(who, "就當散人之後")

    def enlist(self) -> None:
        """入伍段：燕南天投靠第一軍、鐵心蘭投靠第二軍（引薦人迎進營）、看過軍令卡（第一步做完）；前半停在第一道軍令。"""
        sides = self.sides()
        if len(sides) < 2:
            emit("這份內容沒有陣營或入伍段", None)
            return
        for who, faction in ((self.ENLIST, sides[0]), (self.LATE, sides[1])):
            self.past(who)
            self.join(who, faction)
            self.do(who, "view_orders")
            self.me(who, "看過軍令卡")

    def skip(self) -> None:
        """設定頁的幾樣：不再提示、看地圖、看修練頁（序章外：只記旗標）、不認得的分頁、重看序章。"""
        who = self.SKIP
        self.do(who, "hints_off", {"value": True})
        self.do(who, "view_map")
        self.do(who, "view_tab", {"tab": "practice"})
        self.do(who, "view_tab", {"tab": "nope"})
        self.call(who, "GET", "/api/prologue")
        self.me(who, "設定頁之後")

    def half(self) -> None:
        for who in self.everyone():
            self.me(who, "前半停下")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def hut_on(self) -> None:
        """草廬後四步：雪恥、配點、熔蠻牛拳、出師（去潁川、一路同步到抵達）；初入江湖的頭幾步（療傷、操練、看地圖）；重看序章。
        測試內容：去湖邊（第二步）、看地圖（第三步）、結語按「知道了」。開局的季寫「沒有」。一開頭在鎖裡直接叫一次調息（rest_direct）。"""
        who = self.WALKER
        self.rest_direct(who)
        if self.in_hut(who):
            self.choose(who, "act:train")
            self.do(who, "allocate", {"stat": "str"})
            self.call(who, "POST", "/api/menxia/melt", {"art": "manniu_quan"})
            self.me(who, "熔煉之後")
            self.choose(who, "move:yingchuan")
            self.arrive(who)
            opts = self.ids(self.main(who))
            for oid in ("act:heal", "act:drill"):
                if opts.get(oid, {}).get("enabled"):
                    self.choose(who, oid)
                    self.settle_choices(who)
            self.do(who, "view_map")
            self.me(who, "初入江湖")
            self.call(who, "GET", "/api/prologue")
        elif self.c.tutorial.location is None and "move:lake" in self.ids(self.main(who)):
            self.choose(who, "move:lake")
            self.arrive(who)
            self.do(who, "view_map")
            self.me(who, "說書人走完")
            self.do(who, "guide_ack")
            self.me(who, "結語按掉")
        else:
            emit("這一季沒有草廬", None)

    def hints_on(self) -> None:
        """新程式接手前半那一條（按掉）、接著排的再按四條；擺內傷＋眼前一則事件（h_injury 排著、事件擋著不上框）、療好、清掉事件再同步
        （排著還沒上框、條件不成立的拿掉）；交友一次（事件型的碰到才說）。"""
        from tianxia import prologue

        who = self.HINTS
        self.do(who, "guide_ack")
        towns = [i for i, loc in sorted(self.c.locations.items()) if "酒肆" in (loc.tags or []) and i not in prologue.onboard_towns(self.c)]
        if towns:
            self.place(who, towns[-1])  # 第一次到有酒肆的城（h_tavern；老周教過酒肆的那幾城不算）
        self.ack(who, 4, "新程式的提示")
        event = next((e for e in sorted(self.c.events) if not e.startswith(("prologue", "opening")) and self.c.events[e].choices), None)

        def hurt(s) -> None:
            s.player.member.injury = 1
            s.pending_event = event
        self.edit_state(who, hurt)
        self.main(who)
        self.me(who, "內傷排著、事件擋著")

        def heal(s) -> None:
            s.player.member.injury = 0
            s.pending_event = None
        self.edit_state(who, heal)
        self.main(who)
        self.me(who, "療好之後")
        self.do(who, "guide_ack")
        if self.ids(self.main(who)).get("act:socialize", {}).get("enabled"):
            self.choose(who, "act:socialize")
            for _ in range(3):
                opts = self.ids(self.main(who))
                if "talk:leave" in opts:
                    self.choose(who, "talk:leave")
                elif any(i.startswith("choice:") for i in opts):
                    self.settle_choices(who)
                else:
                    break
        self.me(who, "交友之後")

    def goals_on(self) -> None:
        """新程式接手：升到第 5 級（level5 那一條：同步時發）、再按一次就當散人（記過了，什麼都不發）。"""
        who = self.GOALS
        self.edit(who, lambda p: setattr(p.member, "level", 5))
        self.main(who)
        self.me(who, "升到第 5 級之後")
        self.do(who, "newbie_drifter")
        self.me(who, "再按一次就當散人")

    def enlist_on(self) -> None:
        """新程式接手入伍段：燕南天照選單上發光的第一顆出一次力（沒有發光的照守勢、遊歷），按掉結尾；鐵心蘭的第一道軍令擺成一週前
        開始的（enlist.expire：引薦人照樣說結語）、按掉。"""
        if len(self.sides()) < 2:
            emit("這份內容沒有陣營或入伍段", None)
            return
        who = self.ENLIST
        self.place(who, None)
        view = self.main(who)
        glow = (self.view_of(view).get("guide") or {}).get("glow") or []
        emit(f"{who} 發光的", glow)
        opts = self.ids(view)
        press = next((i for i in [*glow, "act:duty", "act:train"] if opts.get(i, {}).get("enabled")), None)
        if press is not None:
            with self.winning():
                self.choose(who, press)
            self.settle_choices(who)
        self.me(who, "出一次力之後")
        self.do(who, "guide_ack")
        self.me(who, "結尾按掉")
        late = self.LATE
        self.edit(late, lambda p: setattr(p, "enlist_since", -1.0e9))
        self.main(late)
        self.me(late, "一週沒做完")
        self.do(late, "guide_ack")
        self.me(late, "結語按掉")

    def rest_direct(self, who: str) -> None:
        """act:rest 背後的 _rest（序章教體力那一步的調息）：正式內容的草廬已經沒有那一步，選單上不會有這一顆（序章裡選單只給這一步的
        動作，草廬外 choose 先擋「此刻無法這麼做」），公開的路走不到——在鎖裡直接叫，不存（同酒肆一軌在鎖裡直接叫 _depart，第 11 批
        PM 認定第 5 條）。在草廬裡：眼前這一步暫時寫成「一坐就回滿」（TutorialStep.instant_rest，叫完就拿掉）、體力擺到 0，叫一次（回滿、
        說那一句）；接著不寫，再叫一次（打坐已經拿掉那一句）。"""
        from tianxia import prologue
        from tianxia.engine import Game

        with self.world.action_lock():
            state = self.chars.load(who)
            step = prologue.step(state, self.c)
            if step is not None:
                g = Game(self.c, state, random.Random(0), self.world)
                g.state.player.stamina = 0.0
                step.instant_rest = "（調息：一坐就回滿。）"
                try:
                    emit(f"{who} 直接叫調息（這一步一坐就回滿）", [g._rest(), g.state.player.stamina])
                finally:
                    step.instant_rest = ""
            emit(f"{who} 直接叫調息", Game(self.c, self.chars.load(who), random.Random(0), self.world)._rest())

    def skip_on(self) -> None:
        """略過新手引導（草廬裡略過：站到起點、出師的盤纏；入伍段也算走完）、再按一次（沒有好略過的）、打開提示、知道了。"""
        who = self.SKIP
        self.do(who, "skip_tutorial")
        self.me(who, "略過之後")
        self.do(who, "skip_tutorial")
        self.do(who, "hints_off", {"value": False})
        self.main(who)
        self.do(who, "guide_ack")
        self.me(who, "打開提示之後")

    def bots(self) -> None:
        """伺服器假人：Game.new(graduated=True)（內容有草廬的走 _graduate：真的走一遍草廬；開局的季站在城門口，挑第一顆）三個，
        BotRunner＋bot_policy.take_turn 三十輪（random.Random(13)、時鐘一輪推四步）。假人的新手目標照拿、提示不排；整季機器人在城門口挑哪一顆
        也寫下來。照 bot_runner._add_bot 的先後：建好就標成假人（BotProfile、陣營、季數），才同步——先同步的話那一下排的狀態提示沒被
        「假人不排」擋住，佇列裡一直排著一條，之後的檢查走不到假人那道擋（審查 dev/guide-1 第 1 條）。第一位另外交友一次（_act 交友之後
        叫 _hint("h_bond")：事件型的碰到才說，只有 hints.queue_note 擋假人）。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=sides[i % len(sides)] if sides else None,
                               season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            if i == 0:
                emit("整季機器人在開局挑", bot.pick(g, g.options(odds=False), random.Random(0)))
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            if i == 0:
                self.bot_socialize(g, name)
            p.stats["silver"] = 200
            self.chars.save(g.state)
            emit(f"假人 {name} 建好", {"step": p.tutorial_step, "loc": p.location, "newbie": sorted(p.newbie_done),
                                     "queue": [n.id for n in p.hint_queue], "journal": [e.title for e in g.state.journal[:4]]})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(13), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_GUIDE_TICKS", "30"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("引導假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"引導假人 {name}", {"step": p.tutorial_step, "faction": p.faction, "enlist": [p.enlist_step, p.enlist_end],
                                    "newbie": [sorted(p.newbie_marks), sorted(p.newbie_done)], "seen": sorted(p.hints_seen),
                                    "queue": [n.id for n in p.hint_queue], "guide": p.guide_done,
                                    "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def bot_socialize(self, g, name: str) -> None:
        """假人交友一次（不經伺服器：假人只走 Game 的公開行動）：站到江小魚交友的那一城（有酒肆、老周沒教過的最後一城，同 hints_on），
        交友、告辭或了結接著的事件，寫下說過與排著的提示（假人兩樣都該是空的）。"""
        from tianxia import prologue

        p = g.state.player
        towns = [i for i, loc in sorted(self.c.locations.items()) if "酒肆" in (loc.tags or []) and i not in prologue.onboard_towns(self.c)]
        if towns:
            p.location = towns[-1]
            p.visited.add(towns[-1])
        on = {o.id for o in g.options(odds=False) if o.enabled}
        if "act:socialize" in on:
            emit(f"假人 {name} 交友", g.choose("act:socialize"))
        elif "act:call" in on:  # 探索三選一的季（不帶、weekend）：交友是打開求見名單，挑第一位見得到的（_open_dialogue 也叫 h_bond）
            g.choose("act:call")
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("call:") and o.enabled), None)
            emit(f"假人 {name} 求見", [first, g.choose(first) if first is not None else None])
        else:
            emit(f"假人 {name} 此地不能交友", [p.location, sorted(on)])
            return
        for _ in range(3):
            opts = [o.id for o in g.options(odds=False) if o.enabled]
            if "talk:leave" in opts:
                g.choose("talk:leave")
            elif any(i.startswith("choice:") for i in opts):
                g.choose(next(i for i in opts if i.startswith("choice:")))
            else:
                break
        emit(f"假人 {name} 交友之後", {"seen": sorted(p.hints_seen), "queue": [n.id for n in p.hint_queue],
                                    "journal": [e.title for e in g.state.journal[:2]]})

    def season(self) -> None:
        """收季、開下一季：每個人換季之後的引導（做完的步數、略過、入伍段走完、說過的提示、新手目標照帶；開季那一句 s_return）；
        燕南天再投靠同一邊（入伍段早就走完：引薦人打個招呼 s_rejoin），兩句都按掉。"""
        self.do(ADMIN, "end_season")
        self.main(self.WALKER)
        self.do(ADMIN, "next_season")
        for who in self.everyone():
            self.main(who)
            self.me(who, "換季之後")
        self.do(self.HINTS, "guide_ack")
        self.me(self.HINTS, "開季那一句按掉")
        sides = self.sides()
        if sides:
            self.join(self.ENLIST, sides[0])
            for k in range(3):  # 開季那一句、碰到的人物、再投靠的招呼（照排的順序一條一條上框）
                self.do(self.ENLIST, "guide_ack")
                self.me(self.ENLIST, f"換季之後按掉第 {k + 1} 條")


def _guide_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：任務卡「就當散人」那一句（newbie.DRIFTER_LINE；搬之前在 tianxia/newbie.py、之後在包裡）
_guide_register_track("guide", GuideScenario, (("tianxia/features/guide/newbie.py", "tianxia/newbie.py"),
                                                ("就當個散人，天下照樣走得。", "就當個散人，天下照樣走得！")), "week7")


if __name__ == "__main__":
    sys.exit(main())
