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

PROFILES = ("season21", "week7", "test")  # 拿掉二（甲）：none、weekend 關門，不再是可以選的設定
TRACK_NAMES = ("sortie", "duel")  # 第 1 批的一軌（出陣：Scenario）、第 2 批的一軌（出陣約戰：DuelScenario）；各自一個資料庫、各自切一半
BOT_PROFILES = ("week7",)
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
MUTANT_PROFILE = {"sortie": "week7", "duel": "week7"}


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



def _gather_finds_hosts() -> list:
    """gather_finds 住在哪幾個模組：第 13 批之前是 tianxia/explore_modes.py，之後是探索包的 explore_rules（舊名 explore_one 是它的別名）；
    第 13 批做到一半（探索一顆已經改叫 explore_rules、三選一還在）是兩個都有。"""
    hosts = [_explore_rules()] if hasattr(_explore_rules(), "gather_finds") else []
    try:
        from tianxia import explore_modes
    except ImportError:
        return hosts
    return [*hosts, explore_modes] if hasattr(explore_modes, "gather_finds") else hosts


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
        """素材拍這幾下找到的照 mids（一下一顆；用完了照真的找）：gather_finds 換掉（模組屬性；第 13 批之前在 explore_modes、
        之後在探索包的 explore_rules，兩份程式各換自己有的那幾個，同一條佇列），每一次都寫進輸出。"""
        hosts = _gather_finds_hosts()
        reals = [(host, host.gather_finds) for host in hosts]
        queue = list(mids)

        def patched(real):
            def gather_finds(*args, **kwargs):
                if not queue:
                    return real(*args, **kwargs)
                found = [queue.pop(0)]
                emit("找到", found)
                return found

            return gather_finds

        for host, real in reals:
            host.gather_finds = patched(real)
        try:
            yield
        finally:
            for host, real in reals:
                host.gather_finds = real

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
# 第 8 批搬推進與結算、generals、收季的收兵（計畫 2026-11-01-決戰包-第4批.md：三軌的放手一搏穿著絕招〔回合首功〕；另開 progress 一軌
# ProgressScenario：三場決戰三種收場、時間到了在排隊的那一場、假人出招、份量快照補上、管理者收季、季自然收掉、開下一季時收兵，切在打到第三回合）。
# 這一段整塊是決戰的：四條拆包線並行，接在檔尾、最後一行登記（_battle_register_track），PM 合的時候不跟別人的行穿插。


# develop 0425589a 之後才要的兩個固定（註冊限流、資料庫第 9 版 sessions 的 token_hash 抹掉）：這一塊原本自己套一份，
# 合 develop（2026-11-01）時 develop 已經放在共用那一層（Scenario.__init__、db_text），只留那一份。


BATTLE_RATE = 60  # 假模型評的放手一搏成功率（server.battle_text 的 B 段，battle_instance.score_gamble）
BATTLE_STORY = "{name}一聲長嘯，提刀衝進陣中。"  # 假模型補的劇情（server.narrate_once 的 B 段；不寫數字、成敗都是這一句）
BATTLE_ULT = {"move": "m7", "name": "大佛一掌", "look": "moying", "weapon": "劍"}  # 第 8 批：放手一搏的人身上那一招（回合首功演它）
BATTLE_SURE = "一擊必中"  # 第 8 批：放手一搏那一句有這幾個字，假模型評 100（推進一軌第三回合那一搏；決戰、集結兩軍的那兩句沒有，照舊 BATTLE_RATE）
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
                if schema.__name__ == "GambleScore":  # 第 8 批：那一句寫了 BATTLE_SURE 的評 100（一定成：回合首功那一回合走得到）
                    return schema(success_rate=100 if BATTLE_SURE in messages[-1]["content"] else BATTLE_RATE)
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
        # 第 8 批：放手一搏送出那一刻身上穿著絕招（形象包 actions.battle_ult；同 test_looks_mvp 換掉它的做法）——兩位放手一搏的人有一招，
        # 成了的那一回合挑回合首功（Game._advance_battle_round 包著 _round_mvp：回合紀錄多一行、畫面多 battle_mvp）。兩份程式都換同一個
        from tianxia.features.looks import actions as looks_actions

        wearers = {self.GAMBLER, self.LATE_GAMBLER}
        looks_actions.battle_ult = lambda ctx: dict(BATTLE_ULT) if ctx.state.player.name in wearers else None
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


class ProgressScenario(BattleScenario):
    """推進與結算一軌（全部拆包第 8 批；--track progress，自己一個資料庫；計畫 docs/superpowers/plans/2026-11-01-決戰包-第4批.md 第三節 Task 1）。
    同一班人（PLAYERS、序章裡的 NEWBIE）與決戰一軌的小工具，段落自己一套：
    - 第一季 A（target：時刻表的季是長社火攻，不帶設定與測試內容是黃巾決戰）：四位與兩位伺服器假人（PACE_BOTS：直接照 Game 按加入；每一回合
      真人出完招 BotRunner.battle_tick 一次——bot_policy.battle_move → game.battle_now()、決戰包的 bots.score）加入、開打；第一回合官軍放手一搏
      （身上那一招：回合首功）、韓雲起的份量快照擦掉（決戰打到一半上線那一版：他下一次同步補上，_backfill_battle_scores）、再打兩回合（第三回合
      韓雲起放手一搏）、第四回合秦朗月先出招——**這裡切一半**（第四回合收了一部分的招、還沒結算，expect 驗）。後半：補劇情、收齊第四回合的招、打到收場（第五回合起擺一位龍頭上陣的人物陣前敗走、
      最後一擊記在秦朗月身上：收場扣聲威、天下大事、他的補送多名望）、每個人與兩位假人收補送（戰報、紀錄、軍餉、天下大事的最有戲與論功、時間軸）。
    - 第一季 B（時刻表的季：照張曼成那一件定宛城的版本、開宛城；不帶設定：再開黃巾決戰）：秦朗月、韓雲起加入。時刻表的季替官軍擺伏筆鎖定
      （WorldState.locks：收場那一下才讀，戰場上輸了照樣官軍勝、敗因寫鎖定那一句），開打之後廣宗擺進排隊（showdowns_waiting：時間到了、前一場
      還在打），宛城一收場就開（_open_waiting_showdown，expect 驗）；不帶設定開打之後把戰局擺到官軍那一邊（官軍勝）。
    - 第一季 C（時刻表的季：排隊開成的廣宗；不帶設定：再開一場）：秦朗月加入；攻城開著的季管理者替黃巾對汝南荒野下戰書（SIEGES 的 S），韓雲起加入；
      管理者收季——決戰與攻城一起收兵（admin_end_season），兩位收「不算勝負」。
    - 第二季（開下一季、重新投靠）：長社（不帶設定是黃巾決戰）沒人加入——集結截止那一下開打、這一回合逾時那一下保底收場（end_without_fighters：
      時刻表決戰照起點判、不帶設定是兩軍膠著，expect 驗收場了）；再開一場（宛城或黃巾決戰）秦朗月加入、攻城韓雲起加入，時鐘推過季末、這段時間
      **沒人輪詢**，第一個輪詢的人（葉寒舟，沒參戰）那一下補算到季收了、決戰與攻城收兵（_battle_status 季收了那一支；不帶設定沒有攻城，
      _showdown_status 那一支）。
    - 第三季：開一場（長社或黃巾決戰：攻城開著的季跟汝南荒野那一場在同一個大區，鈕帶 @流水號）、秦朗月加入、攻城韓雲起加入，時鐘推過季末、
      沒人輪詢，管理者直接按開下一季（admin_next_season：他那一下同步補算到季收了，看到休季、決戰沒打完——讀回季、收兵；攻城——讀回季、收兵；
      再開下一季）；之後每個人輪詢，收上一季的那一則。
    測試內容沒有決戰（也沒有攻城）：同一串 API 照打，決戰那幾步略過；不帶設定沒有時刻表與攻城。"""

    PACE_BOTS = [("假卯", "guan"), ("假辰", "huang")]  # A 那一場的伺服器假人：兩軍各一
    SIEGES = {**BattleScenario.SIEGES, "S": ("huang", "runan_wilds")}  # 收兵的那幾場攻城：黃巾攻中立的汝南荒野（每一季一場，集結中就收兵）
    SIEGE_PLAYERS = {"韓雲起": ("huang", "S", "強攻")}  # siege_pick 照這一張挑（韓雲起按黃巾那一顆）
    FELL_ROUND = 5  # A 那一場這一回合起擺一位龍頭上陣的人物陣前敗走
    PHASES_FIRST = ["setup", "join", "seat", "pace_bots", "open", "muster", "start", "gamble", "pace"]
    PHASES_SECOND = ["narrate", "finish", "paid", "lock_open", "lock_fight", "close_open", "close", "next_one", "bare", "natural_open",
                     "natural", "next_two", "quiet_open", "quiet", "after"]

    # ── 小工具 ──

    def call(self, who: str, method: str, url: str, body: dict | None = None):
        """同 Scenario.call，另外驗登入沒過期（審查 should：season21 第三季那兩段原本全是 401，開下一季收兵與之後的補送都沒走到，比對是 401 對 401）。"""
        status, data = super().call(who, method, url, body)
        self.expect(status != 401, f"{who} 的登入過期了（{method} {url}）")
        return status, data

    def shelved(self, tag: str, rid: int | None) -> None:
        """那一場收兵了（battles 表裡是沒打完的那一種）；這份內容沒有那一場（rid 是 None）不驗。"""
        b = None if rid is None else self.world.ended_battle(rid)
        self.expect(rid is None or (b is not None and b.unfinished), f"{tag}收兵了（沒打完）")

    def live(self):
        """此刻還沒收場的那一場決戰；收場了、沒有是 None。"""
        b = self.world.get_battle()
        return b if b is not None and b.phase != "ended" else None

    def timetabled(self, b) -> bool:
        d = self.c.battles.get(b.battle_id) if b is not None else None
        return d is not None and d.timetable_event is not None

    def season_row(self, tag: str) -> None:
        """季上收場動到的那幾格：天下大事、江湖史最後幾則、時間軸、伏筆鎖定、排隊與開過的決戰、大勢、旗標、大勢人物此刻的聲威。"""
        s = self.world.get_season()
        emit(f"季 {tag}", {
            "number": self.world.get_season_number(), "phase": self.world.season_phase(), "ended": s.ended, "time": s.time,
            "rumors": [r.text for r in s.rumors][-8:], "chronicle": [r.text for r in s.chronicle][-4:],
            "timeline": {k: [v.key, v.text, v.locked_by] for k, v in sorted(s.timeline.items())},
            "locks": {k: v.side for k, v in sorted(s.locks.items())}, "waiting": list(s.showdowns_waiting),
            "opened": dict(sorted(s.showdowns_opened.items())), "cancelled": list(s.showdowns_cancelled),
            "trends": dict(sorted(s.trends.items())), "flags": sorted(s.flags),
            "figures": {fid: [f.status, f.prestige] for fid, f in sorted(s.figures.items())}})

    def ended_row(self, tag: str, rid: int | None) -> None:
        """battles 表裡那一場（收場、收兵之後從共用狀態拿掉的也讀得到）：結果、沒打完、收兵那一句、收場的季時間、名單與整份的雜湊。"""
        b = None if rid is None else self.world.ended_battle(rid)
        emit(f"那一場 {tag}", None if b is None else {
            "id": b.battle_id, "record": b.record_id, "phase": b.phase, "round": b.round_number, "trend": b.trend,
            "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin, b.outcome_reason], "unfinished": b.unfinished,
            "text": b.unfinished_text, "end": b.end_time, "who": sorted(b.participants),
            "mvps": [[m.round, m.name, m.move] for m in b.mvps],
            "commanders": [[c.fid, c.fallen_round, c.felled_by, c.settled] for c in b.commanders],
            "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()})

    def join_live(self, who: str, tag: str) -> str | None:
        """這個人按那一場決戰的加入（自己陣營那一顆；同一個大區兩場時鈕帶 @，照決戰那一場的）；有挑同伴那一步就不派。"""
        pick = self.pick_of(self.ids(self.main(who)), f"battle:join:{self.PLAYERS.get(who)}")
        emit(f"{who} {tag}", pick)
        if pick is not None:
            self.choose(who, pick)
            self.no_escort(who)
        return pick

    def siege_join(self, tag: str) -> None:
        """攻城開著的季：管理者替黃巾對汝南荒野下戰書（下一個同步的人把它開成集結），韓雲起擺過去按加入（siege_pick；同一個大區兩場時照 @）。"""
        if not self.siege_on():
            return
        side, loc = self.SIEGES["S"]
        self.place(self.LATE_GAMBLER, loc)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        self.call(ADMIN, "GET", "/api/admin")
        pick = self.siege_pick(self.LATE_GAMBLER, self.ids(self.main(self.LATE_GAMBLER)))
        emit(f"{self.LATE_GAMBLER} {tag}按的攻城", pick)
        if pick is not None:
            self.choose(self.LATE_GAMBLER, pick)
            self.no_escort(self.LATE_GAMBLER)
        self.siege_row(tag, ("S",))

    def open_b(self) -> None:
        """B 那一場：時刻表的季照張曼成那一件定宛城的版本（GET /api/admin「定結果」的第一個；已經結算了就不定）、開宛城；不帶設定再開黃巾決戰。"""
        op, battle_id = self.target()
        if op == "start_battle":
            self.do(ADMIN, op, {"id": battle_id})
            return
        from tianxia import timetable

        event = timetable.find(self.c, "wancheng")
        _, data = self.call(ADMIN, "GET", "/api/admin")
        value = next((r["value"] for r in data.get("results", []) if r["value"].startswith(f"{event.version_from}|")), None)
        if value is not None and event.version_from not in self.world.get_season().timeline:
            eid, key = value.split("|", 1)
            self.do(ADMIN, "resolve_event", {"id": eid, "key": key})
        self.do(ADMIN, "start_showdown", {"id": event.id})

    def skip_season(self) -> None:
        """時鐘推過季末（world.season_end_time；照最後一次補算的季時間算剩多少，多推 30 步）：這段時間沒有請求。"""
        from tianxia.world import season_end_time

        s = self.world.get_season()
        left = max(0.0, season_end_time(s, self.c) - s.time) / self.c.config.time_scale
        self.skip(int(left // self.STEP_SECONDS) + 30)

    def bot_act(self, name: str, want: str, tag: str) -> None:
        """照假人程式的做法替一位假人按一顆（鎖裡讀存檔、建 Game、同步、按、存回去）：選單上 id（不看 @）是 want 的那一顆。"""
        from tianxia.engine import Game

        self.begin()
        pick = None
        with self.world.action_lock():
            state = self.chars.load(name)
            if state is None:
                emit(f"{name} {tag}（沒有這個人）", None)
                return
            g = Game(self.c, state, random.Random(STEP[0]), self.world)
            g.client = None
            g.sync(CLOCK[0])
            pick = next((o.id for o in g.options(odds=False) if o.enabled and o.id.split("@")[0] == want), None)
            if pick is not None:
                g.choose(pick)
            self.chars.save(g.state)
        emit(f"{name} {tag}", pick)

    def bot_sync(self, name: str, tag: str) -> None:
        """照假人程式的做法同步一位假人（收補送），存檔那幾格寫進輸出。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            state = self.chars.load(name)
            if state is None:
                return
            g = Game(self.c, state, random.Random(STEP[0]), self.world)
            g.client = None
            g.sync(CLOCK[0])
            self.chars.save(g.state)
        self.me(name, tag)

    def bot_tick(self) -> None:
        """BotRunner.battle_tick 一次（在場還沒出招的假人出招；真人都送出了就不等 BATTLE_DELAY）：每一下新建一份 runner、亂數照步數（前半＋後半是兩個行程）。"""
        from tianxia.bot_runner import BotRunner

        self.begin()
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(STEP[0]), clock=lambda: CLOCK[0])
        report = runner.battle_tick()
        emit("假人出招", {"acted": report.acted, "online": report.online, "skipped": report.skipped, "failed": report.failed})

    def round(self, gamblers: dict[str, str]) -> None:
        """同決戰一軌的 round（gamblers 放手一搏、掛機的那一位不按、其餘照回合數挑三招之一；回合沒結就推過期限再輪詢一次），只是真人出完招之後
        假人在場的話 BotRunner.battle_tick 一次；不打攻城（這一軌的攻城都在集結中就收兵）。"""
        b = self.live()
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
        if any(name in b.participants for name, _ in self.PACE_BOTS):
            self.bot_tick()
        b = self.world.get_battle()
        if b is not None and b.phase == "active" and b.round_number == n:
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.GAMBLER)
        self.battle_row(f"第 {n + 1} 回合之後")

    def fight_out(self, tag: str, fell: bool = False) -> None:
        """打到收場（最多 40 回合）；fell：第 FELL_ROUND 回合起、還沒有人敗走時擺一位龍頭上陣的人物陣前敗走（最後一擊記在秦朗月身上）；有等著補的劇情就補。"""
        for _ in range(40):
            b = self.live()
            if b is None or b.phase != "active":
                break
            if fell and b.round_number >= self.FELL_ROUND and b.commanders and all(c.fallen_round is None for c in b.commanders):
                fid, n = b.commanders[0].fid, b.round_number

                def down(x, fid=fid, n=n) -> None:
                    for c in x.commanders:
                        if c.fid == fid:
                            c.fallen_round, c.felled_by = n, self.GAMBLER

                self.world.mutate_battle(down)
                emit("龍頭上陣的人物陣前敗走", [fid, n])
            self.round({})
            b = self.world.get_battle()
            if b is not None and b.tales:
                self.tell(f"{tag}第 {b.round_number} 回合補劇情")
        self.battle_row(f"{tag}收場")

    def new_season(self, tag: str) -> None:
        """管理者開下一季；每個人同步（換成新的角色）、開局待選的事件選掉、重新投靠（join：體力補滿、過了新手期）。"""
        self.do(ADMIN, "next_season")
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        for who in self.PLAYERS:
            self.settle_choices(who)
        self.join()
        self.season_row(tag)

    # ── 情境（前半）──

    def pace_bots(self) -> None:
        """兩位伺服器假人（兩軍各一）建進資料庫、擺在 A 那一場的大區（同決戰一軌 bots 那一段的做法）。測試內容沒有決戰：略過。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        loc = self.spot(self.target()[1])
        if loc is None:
            emit("這份內容沒有決戰：假人那一段略過", None)
            return
        for i, (name, side) in enumerate(self.PACE_BOTS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(50 + i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
            emit(f"{name} 擺在 A 那一場的大區", [side, loc])

    def muster(self) -> None:
        """同決戰一軌的集結（四位按加入、再看一次），之後兩位假人照 Game 按自己那一軍的加入。"""
        super().muster()
        if self.live() is None:
            return
        for name, side in self.PACE_BOTS:
            self.bot_act(name, f"battle:join:{side}", "集結時按的")
        self.battle_row("假人加入之後")

    def pace(self) -> None:
        """前半的最後一段：韓雲起的份量快照擦掉，他下一次同步就補上（_backfill_battle_scores：只在自己的請求路徑補）；再打兩回合（第三回合韓雲起
        放手一搏，身上那一招）；第四回合秦朗月先出招（同 round 的挑法），別人還沒按。前半停在這裡：第三回合結算過了、第四回合收了一部分的招
        （BattleRound.pending_actions 寫在資料庫裡；不成立就停）——後半由新程式接著收齊、結算這一回合（審查 nit：原本切在第四回合剛開、
        一招都還沒收，接手的只有補劇情）。"""
        b = self.live()
        if b is None:
            emit("沒有開打中的決戰：前半那兩回合略過", None)
            return
        name = self.LATE_GAMBLER
        if name in b.participants:
            self.world.mutate_battle(lambda x: setattr(x.participants[name], "scores", {}))
            emit(f"{name} 的份量快照擦掉", None)
        self.main(name)
        self.battle_row("補上份量快照之後")
        self.round({})
        self.round({name: f"{BATTLE_SURE}：繞到敵後，放火燒糧"})  # 評 100、一定成，身上那一招：這一回合挑回合首功
        b = self.live()
        if b is not None and b.phase == "active":
            first = self.GAMBLER
            moves = sorted(i for i, o in self.ids(self.main(first)).items() if i.startswith("battle:act:") and o.get("enabled"))
            if moves:
                self.choose(first, moves[b.round_number % len(moves)])
        b = self.world.get_battle()
        pending = [] if b is None else sorted(b.round.pending_actions)
        emit("前半停在這裡：這一回合已經出招的", pending)
        self.battle_row("前半停下")
        self.expect(b is not None and b.phase == "active" and b.round_number >= 3 and self.GAMBLER in pending
                    and len(pending) < sum(1 for q in b.participants.values() if not q.eliminated),
                    "前半停在一回合收了一部分的招" + ("" if b is None else f"（此刻 {b.phase}、打過 {b.round_number} 回合、已出招 {pending}）"))

    # ── 情境（後半）──

    def finish(self) -> None:
        """A 打到收場（第五回合起一位龍頭陣前敗走）；季上那幾格。"""
        rid = None if self.live() is None else self.live().record_id
        self.fight_out("A ", fell=True)
        self.ended_row("A 收場", rid)
        self.season_row("A 收場之後")

    def paid(self) -> None:
        """收場之後每個人與兩位假人（照假人程式的做法同步一次）收補送；秦朗月的戰報頁與最上面那一筆。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "A 收補送之後")
        if self.c.battles:
            for name, _ in self.PACE_BOTS:
                self.bot_sync(name, "A 收補送之後")
        _, data = self.call(self.GAMBLER, "GET", "/api/reports")
        rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
        for rid in rows[:1]:
            self.call(self.GAMBLER, "GET", f"/api/reports?id={rid}")

    def lock_open(self) -> None:
        """B：開宛城（不帶設定是黃巾決戰）、秦朗月與韓雲起擺過去加入、集結截止開打；時刻表的季替官軍擺伏筆鎖定、廣宗擺進排隊；不帶設定把戰局
        擺到官軍那一邊。"""
        if not self.c.battles:
            emit("這份內容沒有決戰：B、C 那兩場略過", None)
            return
        self.open_b()
        b = self.live()
        if b is None:
            emit("B 那一場沒開成", None)
            return
        loc = self.spot(b.battle_id)
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.place(who, loc)
            self.join_live(who, "B 那一場按的")
        if self.timetabled(b):
            from tianxia.state import Lock

            event = self.c.battles[b.battle_id].timetable_event

            def lock(s) -> None:
                s.locks[event] = Lock(side="guan", name=self.GAMBLER, time=s.time)

            self.world.mutate_season(lock)
            emit("伏筆鎖定", [event, "guan"])
        self.start()
        b = self.live()
        if b is not None and b.phase == "active":
            if self.timetabled(b):
                def wait(s) -> None:
                    if "guangzong" not in s.showdowns_waiting and "guangzong" not in s.showdowns_opened and "guangzong" not in s.timeline:
                        s.showdowns_waiting.append("guangzong")

                self.world.mutate_season(wait)
                emit("廣宗擺進排隊", list(self.world.get_season().showdowns_waiting))
            # 戰局擺到一邊：時刻表的季擺到黃巾那一邊（戰場上黃巾佔上風，收場照伏筆鎖定官軍勝、敗因寫鎖定那一句）；不帶設定擺到官軍那一邊（官軍勝）
            trend = 30 if self.timetabled(b) else 88
            self.world.mutate_battle(lambda x: setattr(x, "trend", trend))
            emit("戰局擺到一邊", trend)
        self.battle_row("B 開打")

    def lock_fight(self) -> None:
        """B 打到收場：時刻表的季照伏筆鎖定官軍勝（戰場上輸了是險勝、敗因寫鎖定那一句），收場那一下開排隊的廣宗（expect 驗）；兩位收補送。"""
        b = self.live()
        if b is None:
            return
        rid, timed = b.record_id, self.timetabled(b)
        self.fight_out("B ")
        self.ended_row("B 收場", rid)
        self.season_row("B 收場之後")
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.main(who)
            self.me(who, "B 收補送之後")
        nxt = self.live()
        emit("B 收場之後開的那一場", None if nxt is None else [nxt.battle_id, nxt.phase, nxt.record_id])
        self.expect(not timed or (nxt is not None and nxt.battle_id == "guangzong"), "宛城一收場就開了排隊的廣宗")

    def close_open(self) -> None:
        """C：時刻表的季是排隊開成的廣宗（不帶設定再開一場黃巾決戰）；秦朗月擺過去加入。攻城那一場韓雲起加入。"""
        if self.c.battles and self.live() is None and self.target()[0] == "start_battle":
            self.do(ADMIN, "start_battle", {"id": self.target()[1]})
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "C 那一場按的")
        self.siege_join("收季之前")
        self.battle_row("收季之前")

    def close(self) -> None:
        """管理者收季（admin_end_season：讀回收季那一份季之後，沒打完的決戰與每一場攻城收兵，再補大事）；四位收「不算勝負」。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.do(ADMIN, "end_season")
        self.ended_row("收季收兵的決戰", rid)
        self.ended_row("收季收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("管理者收季：決戰", rid)
        self.shelved("管理者收季：攻城", None if slot is None else slot.record_id)
        self.siege_row("收季之後", ("S",))
        self.season_row("收季之後")
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "收季之後")

    def next_one(self) -> None:
        self.new_season("第二季開季")

    def bare(self) -> None:
        """第二季：長社（不帶設定是黃巾決戰）沒人加入——集結截止那一下開打（場上一個人都沒有）、這一回合逾時那一下保底收場（不成立就停）。"""
        if not self.c.battles:
            emit("這份內容沒有決戰：沒人加入的那一場略過", None)
            return
        op, battle_id = self.target()
        if self.live() is None:
            self.do(ADMIN, op, {"id": battle_id})
        b = self.live()
        if b is None:
            emit("沒人加入的那一場沒開成", None)
            return
        rid = b.record_id
        if b.phase == "muster":
            self.skip_past(b.muster_deadline_real)
            self.main(self.IDLER)
        b = self.live()
        if b is not None and b.phase == "active":
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.IDLER)
        self.ended_row("沒人加入的那一場", rid)
        self.season_row("保底收場之後")
        self.expect(self.live() is None, "沒人加入的那一場保底收場了")

    def natural_open(self) -> None:
        """第二季再開一場（宛城；不帶設定黃巾決戰），秦朗月加入；攻城那一場韓雲起加入。"""
        if self.c.battles and self.live() is None:
            self.open_b()
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "季末之前按的")
        self.siege_join("季末之前")
        self.battle_row("季末之前")

    def natural(self) -> None:
        """時鐘推過季末、沒人輪詢；第一個輪詢的人（葉寒舟，沒有參戰）那一下補算到季收了，選單推決戰時看到季收了：沒打完的決戰與每一場攻城收兵
        （_battle_status 季收了那一支；沒有攻城的季走 _showdown_status）。之後兩位收「不算勝負」。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.skip_season()
        self.battle_row("推過季末、還沒人輪詢")
        self.main(self.IDLER)
        self.ended_row("季收了收兵的決戰", rid)
        self.ended_row("季收了收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("季自然收掉：決戰", rid)
        self.shelved("季自然收掉：攻城", None if slot is None else slot.record_id)
        self.season_row("季自然收掉之後")
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.main(who)
            self.me(who, "季自然收掉之後")

    def next_two(self) -> None:
        self.new_season("第三季開季")

    def quiet_open(self) -> None:
        """第三季開一場（長社；不帶設定黃巾決戰），秦朗月加入；攻城那一場韓雲起加入（攻城開著的季跟長社在同一個大區，鈕帶 @）。
        開之前每個人重新登入一次：登入狀態認 accounts.SESSION_SECONDS（30 天，照登入那一刻算），後半開頭那一次登入到第三季季末，season21
        已經超過了（審查 should：原本 quiet、after 兩段全是 401）。放在季末之前：登入會輪詢一次，季末之後才登入就變成「第一個輪詢的人收兵」，
        不是管理者開下一季那一下收。"""
        self.login_all()
        op, battle_id = self.target()
        if self.c.battles and self.live() is None:
            self.do(ADMIN, op, {"id": battle_id})
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "第三季按的")
        self.siege_join("第三季")
        self.battle_row("第三季季末之前")

    def quiet(self) -> None:
        """時鐘推過季末、沒人輪詢；管理者直接按開下一季（admin_next_season：他那一下同步補算到季收了，看到休季、決戰沒打完——讀回季、收兵；攻城——讀回季、
        收兵；再開下一季）。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.skip_season()
        self.battle_row("推過季末、還沒人輪詢")
        self.do(ADMIN, "next_season")
        self.ended_row("開下一季收兵的決戰", rid)
        self.ended_row("開下一季收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("開下一季：決戰", rid)
        self.shelved("開下一季：攻城", None if slot is None else slot.record_id)
        self.season_row("第四季開季")

    def after(self) -> None:
        """每個人輪詢：收上一季的那一則（不算勝負；上一季那一支）。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "第四季開季之後")


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
# 第 8 批：推進一軌（ProgressScenario），改一個字是論功那一則（搬之前在 engine.py 的 _merit_line、之後在 features/battle/progress.py）——
# 後半 A 收場那一下寫進天下大事（season_row 寫出來）。找的那一句要連 f-string 的尾巴（`name}論功：" + `）：progress.py 的模組說明也有
# 「收場與論功：」，只寫「論功：」在搬完的檔裡有兩處、_mutant 找不到剛好一處就停（第 8 批審查）
_PROGRESS_MUTATION = (("tianxia/features/battle/progress.py", "tianxia/engine.py"), ('name}論功：" + ', 'name}論功！" + '))
_battle_register_track("progress", ProgressScenario, _PROGRESS_MUTATION, "week7")


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
TRAIN_BOT_PROFILES = ("week7",)
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
                                         ("軍心為之一振。", "軍心為之一振！")), "week7")


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


# ═══════════════════════════ bout：單挑兩軌（全部拆包第 12 批，dev/bout-1） ═══════════════════════════
# 單人頭目戰、擂台（含看台的場邊事件）搬進 tianxia/features/bout/（計畫 docs/superpowers/plans/2026-11-03-單挑包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後兩行登記（_bout_register_track），PM 合的時候不跟別人的行穿插。同一套段落登記兩軌：bout 切在擂台報名之後、被挑之前
# （WorldState.arena 有人守擂、還沒人來挑；同一刻江小魚的頭目戰第一回合出過招、DuelState 寫進存檔），ring 切在擂台寫到一半（擂台打到一半、
# 場邊那一句等著重寫、守擂的那一筆沒補、坐在擂台邊、記下的俸沒領；審查修正，取代原本切在頭目戰打到一半、跟 bout 重複的 boss 那一軌）。
# 打法照 ExploreScenario 的小工具：抽到哪一類（探索一顆）、頭目的機率（Config.duel.explore_chance 換成 1）在要的那幾步換掉；勝負靠把
# 這一場的氣勢擺在門檻上（直接改資料庫）再出招，打的照真的算。模型：放手一搏的成功率與兩版劇情、台下觀眾的反應、場邊那一句的重寫
# 換成假的（MODEL["bout"] 開著時），其餘照舊不連網路。

BOUT_ONE = "雙刀一交，借勢翻身上台角，反手劈下。"  # 放手一搏寫的那一句（20 字以內）
_BOUT_CLIENTS: dict[type, type] = {}


def _bout_client(base: type) -> type:
    """放手一搏、看台、場邊那一句的假模型（base 是 _setup_child 換好的 client 類別）：SuccessRateJudgment 回 MODEL["bout"] 的成功率與
    兩版劇情（照提示裡的名號開頭）、CrowdJudge 回那一個反應、CrowdLine 回一句寫到該寫的人；其餘照 base。"""
    if base not in _BOUT_CLIENTS:
        import re

        class BoutClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                text = "\n".join(str(m.get("content", "")) for m in messages)
                if schema.__name__ == "SuccessRateJudgment":
                    found = re.search(r"玩家：(.+?)（所屬", text)
                    who = found.group(1) if found else "他"
                    return schema(success_rate=MODEL["bout"]["rate"], reasoning="",
                                  win=f"{who}一刀劈中，對手踉蹌退了三步。", lose=f"{who}一刀劈空，反被逼到台角。")
                if schema.__name__ == "CrowdJudge":
                    return schema(crowd=MODEL["bout"]["crowd"])
                if schema.__name__ == "CrowdLine":
                    found = re.search(r"一定要寫到「(.+?)」", text)
                    return schema(line=f"台下一陣騷動，{found.group(1) if found else ''}趁機穩住了腳步。")
                return super().chat_structured(messages, schema, *a, **k)

        _BOUT_CLIENTS[base] = BoutClient
    return _BOUT_CLIENTS[base]


class BoutScenario(ExploreScenario):
    """單挑（全部拆包第 12 批；--track bout、--track ring，各自一個資料庫）。照調查 area_combat.json 的 features/bout 那一段與派工：
    頭目戰——撞上頭目（不帶設定的舊探索、weekend 的三選一練功、week7／season21 的探索一顆；三選一的找素材在正式內容裡撞不上頭目——
    一類一顆開著時一定給料、不擲頭目，有分支層時按了只展開分支——Game._gather 改叫 _boss_ready() 那一行這裡走不到）、場景與輸入框、出招、放手一搏
    （/api/do/duel_text 鎖外三段式，假模型）、打贏（戰報、掉落、名望、破境丹的擲骰）、打輸、抽身、冷卻中與次數用完（三選一的練功鈕與
    行動列那一行）、穿防具開打（快照的減損、打完照磨）；擂台——打開（名次那一句）、報名、更新分身、挑一場、灰掉的挑擂鈕回原因、出招、
    放手一搏與看台的反應、場邊事件與鎖外重寫那一句（server.crowd_once）、認輸、名次交換、收場卡（店面那一頁）、守的人補戰報、
    換日領俸、坐在擂台邊動身與擂台關了收店；稱號被讀——玩家卡、名帖匣、榜單、狀態列、酒肆查人；伺服器假人（BotRunner：報名、
    挑擂、打到一半的頭目戰照架勢出招、坐在擂台邊只會返回）與整季機器人在頭目戰的選單上挑；收季（前三名、季末獎勵、打到一半的那一場
    作廢、江湖史的歷屆擂主）、開下一季。測試內容沒有頭目、擂台關著：同一串 API 照打（證明關著一個字都不變）。season21 的擂台照週解鎖
    （第 2 週才開）：記憶體裡關掉週解鎖（兩份程式、前後兩個行程都關），seat 那一段照開著的寫一次鎖著的樣子。"""

    PLAYERS = {"江小魚": None, "花無缺": "guan", "鐵心蘭": "huang", "燕南天": None, "邀月": None, "憐星": None}
    NEWBIE = "小仙女"
    # 頭目在哪（content/duels.json）：長社、汝南荒野（黃巾小帥）；南陽荒野、南陽官道（山匪頭子）；豪族塢堡、燕山腳下（河北豪強的門客）
    SEATS = {"江小魚": "changshe", "花無缺": "nanyang_wilds", "鐵心蘭": "yanshan_foot", "燕南天": "yingchuan", "邀月": "yingchuan",
             "憐星": "yingchuan"}
    BOT_SEATS = [("錦衣客", "changshe"), ("黑衣客", "yingchuan"), ("白衣客", "yingchuan"), ("灰衣客", "runan")]
    ALL = ["setup", "seat", "meet", "arena_join", "resume", "duel_more", "duel_lose", "duel_flee", "duel_old", "boss_gate", "arena_fight",
           "arena_more", "arena_refuse", "arena_yield", "defend", "wages", "titles", "depart", "closed", "bots", "season"]
    PHASES_FIRST = ALL[:ALL.index("arena_join") + 1]  # bout：切在擂台報名之後、被挑之前
    PHASES_SECOND = ALL[ALL.index("arena_join") + 1:]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("bout") is not None:
                client.__class__ = _bout_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        if profile == "season21":  # 擂台照週解鎖（第 2 週）：兩個行程都關（不寫輸出：前半＋後半要跟整段一樣）
            self.c.config.jianfa.week_unlock = False

    # ── 小工具 ──

    def begin(self) -> None:
        """每個請求換一份空的勝算記憶、清掉榜單的快取（server.boards_now 照真的 time.monotonic 判斷過期：不清的話跑得快慢決定讀到哪一份）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()
        self.server.BOARDS_CACHE.clear()

    def setup(self) -> None:
        Scenario.setup(self)  # 不擺探索那一軌的高寄萍

    @contextlib.contextmanager
    def model(self, rate: int = 70, crowd: str = "叫好"):
        MODEL["bout"] = {"rate": rate, "crowd": crowd}
        try:
            yield
        finally:
            MODEL.pop("bout", None)

    def me(self, who: str, tag: str) -> None:
        """存檔裡單挑那幾格（單挑包認領的十個欄位），加上氣血、內傷、銀兩、心得、名望、破境丹、防具、最新一份戰報與江湖紀錄的標題。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player

        def dump(x):
            return None if x is None else x.model_dump(mode="json")

        emit(f"{who} {tag}", {
            "duel": dump(p.duel), "duel_tally": dict(sorted(p.duel_tally.items())), "duel_last": list(p.duel_last),
            "arena": dump(p.arena), "arena_last": dump(p.arena_last), "picking_arena": p.picking_arena, "arena_day": p.arena_day,
            "arena_today": p.arena_today, "arena_crowd_seen": dict(sorted(p.arena_crowd_seen.items())),
            "arena_crowd_note": dump(p.arena_crowd_note), "neili": p.member.neili, "injury": p.member.injury,
            "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "fame": p.stats.get("fame", 0),
            "legend": p.legend_items, "armor": dump(p.armor), "battle": dump(state.battles[-1]) if state.battles else None,
            "journal": [e.title for e in state.journal[:4]]})

    def ladder(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"擂台 {tag}", {"entries": {k: e.model_dump(mode="json") for k, e in sorted(w.arena.items())},
                            "pairs": dict(sorted(w.arena_pairs.items())), "seq": w.arena_seq, "closed": w.arena_closed, "day": w.arena_day})

    def arm(self, who: str, level: int = 0) -> None:
        """學一門武學（沒有的話）；level 給了，武學、內功練到那一成。"""
        from tianxia import rules

        c = self.c
        skill = "jichu_quanjiao" if "jichu_quanjiao" in c.skills else sorted(c.skills)[0]

        def fn(state) -> None:
            if state.player.member.wugong_id is None:
                rules.learn_skill(state, c, skill)
            if level:
                state.player.member.wugong_level, state.player.member.neigong_level = level, level

        self.edit_state(who, fn)

    def encounter(self, who: str, mode: str = "PRACTICE") -> bool:
        """在這裡探索、撞上頭目（探索一顆抽到遭遇、頭目的機率換成 1；三選一的季按 mode 那一顆；舊探索照擲）。撞上了是 True。"""
        explore_one = _explore_rules()
        self.place(who, None)  # 體力補滿
        with self.draws(explore_one.ENCOUNTER), self.tweak(self.c.config.duel, explore_chance=1.0):
            self.choose(who, "act:explore")
            opts = self.options(who)
            oid = f"explore:{mode.lower()}"  # 第 13 批之前 explore_modes.option_id(getattr(explore_modes, mode))：同一個字
            if any(i.startswith("explore:") for i in opts):
                emit(f"{who} 三選一的 {oid}", opts.get(oid))
                if (opts.get(oid) or {}).get("enabled"):
                    self.choose(who, oid)
        duel = self.chars.load(who).player.duel
        emit(f"{who} 撞上頭目了嗎", None if duel is None else duel.model_dump(mode="json"))
        return duel is not None

    def bout(self, who: str, prefix: str, edge: float | None, rounds: int = 8) -> None:
        """一路出招到收場（prefix 是 duel 或 arena）：每一招之前把氣勢擺在 edge（None 照打）；招照固守、強攻、奇襲輪著出，鎖住的跳過。"""
        moves = ("固守", "強攻", "奇襲")
        for i in range(rounds):
            p = self.chars.load(who).player
            if (p.duel if prefix == "duel" else p.arena) is None:
                return
            if edge is not None:
                self.edit(who, lambda q: setattr(q.duel if prefix == "duel" else q.arena, "edge", edge))
            opts = self.options(who)
            pick = next((f"{prefix}:{m}" for m in moves[i % 3:] + moves[:i % 3] if (opts.get(f"{prefix}:{m}") or {}).get("enabled")), None)
            if pick is None:
                emit(f"{who} 選單上沒有招", sorted(opts))
                return
            self.choose(who, pick)

    def gamble(self, who: str, text: str = BOUT_ONE, rate: int = 70, crowd: str = "叫好") -> None:
        """放手一搏：頭目戰、擂台都走 /api/do/duel_text（鎖外三段式；假模型評 rate、台下觀眾 crowd）。"""
        with self.model(rate, crowd):
            self.do(who, "duel_text", {"text": text})

    def today(self, who: str) -> int:
        """這個人此刻回體丹那一套的今天（擂台的次數、俸照它換日）。"""
        from tianxia.engine import Game

        self.begin()
        game = Game(self.c, self.chars.load(who), world=self.world)
        game.sync(CLOCK[0])
        return game._pill_day()

    @staticmethod
    def fight_id(foe: str) -> str:
        from tianxia.characters import name_key

        return f"arena:fight:{name_key(foe)}"

    def lock_sync(self, name: str) -> None:
        """沒有帳號的人（bots 那一段補的假人）同步一次：照 BotRunner 在行動鎖裡建一份 Game（不叫模型）、sync、存回去。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load(name), world=self.world)
            game.client = None
            game.sync(CLOCK[0])
            self.chars.save(game.state)

    def boss_note(self, who: str, tag: str) -> None:
        """三選一的練功鈕與行動列底下那一行（頭目在不在、冷卻中、次數用完都寫在這兩處；別的季沒有這一顆，寫探索那一格）。"""
        view = self.main(who)
        oid = "explore:practice"  # 第 13 批之前 explore_modes.option_id(explore_modes.PRACTICE)：同一個字
        emit(f"{who} {tag}", {"practice": self.ids(view).get(oid), "explore": self.ids(view).get("act:explore"),
                              "notes": dict(sorted((view.get("action_notes") or {}).items()))})

    # ── 前半 ──

    def seat(self) -> None:
        """站好位置、學武學（江小魚練到第九成、穿一件三階上品的甲）、有陣營的劇本給花無缺官軍、鐵心蘭黃巾；每個人的擂台入口與探索那一格。
        season21 先照週解鎖開著寫一次（第 1 週擂台還鎖著）。"""
        from tianxia.state import Equipment

        factions = {f.id for f in self.c.scenario.factions}
        for who, loc in self.SEATS.items():
            side = self.PLAYERS[who]
            self.place(who, loc, faction=side if side in factions else "keep")
            self.arm(who, 9 if who == "江小魚" else 0)
        self.edit("江小魚", lambda p: setattr(p, "armor", Equipment(id="江小魚:1", slot="armor", name="試甲", attribute="剛", tier=3,
                                                                    quality="上品", edge=100)))
        if self.profile == "season21":
            with self.tweak(self.c.config.jianfa, week_unlock=True):
                emit("season21 週解鎖開著時的擂台入口", self.options("燕南天").get("act:arena"))
        for who in self.SEATS:
            view = self.main(who)
            emit(f"{who} 的擂台入口與探索", {"arena": self.ids(view).get("act:arena"), "explore": self.ids(view).get("act:explore"),
                                         "note": (view.get("action_notes") or {}).get("act:explore")})

    def meet(self) -> None:
        """江小魚在長社撞上頭目（穿著甲：減損快照進這一場）：場景卡、三招與抽身、輸入框；出一招（第一回合）：頭目戰打到一半，bout 那一軌的切點（arena_join 之後）跨過它。"""
        if not self.encounter("江小魚"):
            return
        view = self.main("江小魚")
        emit("頭目戰的選單", sorted(self.ids(view)))
        self.choose("江小魚", "duel:固守")
        self.me("江小魚", "第一回合之後")

    def arena_join(self) -> None:
        """擂台：憐星打開看一眼就返回；花無缺、鐵心蘭、燕南天依序報名（排第一、二、三）；鐵心蘭再按一次是更新分身；燕南天打開時的名次那一句。
        bout 那一軌切在這裡（有人守擂、還沒人來挑）。"""
        self.choose("憐星", "act:arena")
        self.main("憐星")
        self.choose("憐星", "arena:back")
        for who in ("花無缺", "鐵心蘭", "燕南天"):
            self.place(who, None)
            self.choose(who, "act:arena")
            self.choose(who, "arena:join")
            self.choose(who, "arena:back")
        self.choose("鐵心蘭", "act:arena")
        self.choose("鐵心蘭", "arena:join")
        self.choose("鐵心蘭", "arena:back")
        self.choose("燕南天", "act:arena")
        self.choose("燕南天", "arena:back")
        self.ladder("報名之後")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def duel_more(self) -> None:
        """江小魚接著打（新程式接手舊程式打到一半的那一場）：放手一搏（假模型 70）、再把氣勢擺在 89 一路出招到收場（打贏：掉落、名望、
        破境丹的擲骰、甲照磨）；收場之後在長社再探索一次（冷卻中：不撞頭目）。"""
        if self.chars.load("江小魚").player.duel is None:
            emit("江小魚沒有在打頭目", None)
            return
        self.gamble("江小魚")
        self.me("江小魚", "放手一搏之後")
        self.bout("江小魚", "duel", 89.0)
        self.me("江小魚", "打完頭目")
        self.encounter("江小魚")
        self.me("江小魚", "冷卻中再探索")

    def duel_lose(self) -> None:
        """花無缺在南陽荒野撞上山匪頭子，氣勢擺在 11 一路出招：打輸（掉的氣血扣回本人、兩成變內傷）。三選一的找素材在正式內容裡撞不上頭目
        （一類一顆開著時一定給料、不擲頭目；有分支層時按了只展開分支）：Game._gather 撞頭目那一行這裡走不到。"""
        if self.encounter("花無缺"):
            self.bout("花無缺", "duel", 11.0)
        self.me("花無缺", "打輸頭目")

    def duel_flee(self) -> None:
        """鐵心蘭在燕山腳下撞上河北豪強的門客：放手一搏（模型叫不到：評 40、固定句），再抽身退走（不寫戰報、掉的氣血不回）；走到黃巾大營
        （沒有頭目）看練功鈕與行動列那一行。"""
        if self.encounter("鐵心蘭"):
            self.do("鐵心蘭", "duel_text", {"text": "閉眼亂揮一通。"})
            self.choose("鐵心蘭", "duel:flee")
        self.me("鐵心蘭", "抽身之後")
        self.place("鐵心蘭", "huangjin_camp" if "huangjin_camp" in self.c.locations else None)  # 沒有頭目的地方：練功鈕與行動列寫什麼
        self.boss_note("鐵心蘭", "沒有頭目的地方的練功鈕與行動列")

    @contextlib.contextmanager
    def explore_modes_off(self):
        """舊探索：三選一的開關在記憶體裡關掉（第 13 批之前）；第 13 批之後沒有那個開關，換成它關著時連帶關掉的那幾樣
        （一類一顆、事件五折、觀山石的加成；計畫 2026-11-04-拿掉一-第13批.md 2.1），兩份程式走的是同一條路。
        event_trend_share 搬出來了就是「之後」（Task 2 做完、三選一還在的那一刻兩邊都關）。"""
        cfg = self.c.config
        if not hasattr(cfg, "event_trend_share"):
            with self.tweak(cfg.explore_modes, enabled=False):
                yield
            return
        with self.tweak(cfg, precise_actions=False, event_trend_share=1.0, sense_treasure_points=0):
            if hasattr(cfg, "explore_modes"):
                with self.tweak(cfg.explore_modes, enabled=False):
                    yield
            else:
                yield

    def duel_old(self) -> None:
        """舊探索撞上頭目（三選一的開關在記憶體裡關掉：不帶設定與 weekend 的 act:explore 走 _explore 那一條；探索一顆的季照樣是出門一趟）：
        憐星在汝南荒野撞上黃巾小帥，抽身退走。"""
        self.place("憐星", "runan_wilds")
        with self.explore_modes_off():
            if self.encounter("憐星"):
                self.choose("憐星", "duel:flee")
        self.me("憐星", "舊探索的頭目之後")

    def boss_gate(self) -> None:
        """遇不上頭目的兩種（三選一的練功鈕與行動列那一行寫原因；長社對官軍的人只有頭目、沒有尋常對手，練功那一格才寫頭目）：花無缺剛打完
        山匪頭子（冷卻中）、冷卻擺過去之後長社這一隻次數用完（季的帳與週的帳都擺滿）；再探索一次也不撞上。江小魚剛打完、在長社再看一次。"""
        from tianxia import duel

        self.place("江小魚", "changshe")
        self.boss_note("江小魚", "冷卻中的練功")
        self.place("花無缺", "changshe")
        self.boss_note("花無缺", "冷卻中的練功")
        c = self.c

        def used_up(state) -> None:
            state.player.duel_last = []
            for boss in duel.here(state, c):
                state.player.duel_tally[duel.season_key(state, boss.id)] = c.config.duel.per_boss_season
                if c.config.duel.per_boss_week:
                    state.player.duel_tally[duel.week_key(state, c, boss.id)] = c.config.duel.per_boss_week

        for who in ("花無缺", "江小魚"):
            self.edit_state(who, used_up)
            emit(f"{who} 冷卻擺過去、長社的頭目次數擺滿", None)
            self.boss_note(who, "次數用完的練功")
            self.encounter(who)

    def arena_fight(self) -> None:
        """江小魚報名（排第四）、挑燕南天（第三）：看台的場邊事件機率換成 1；放手一搏（假模型 70、台下「離譜」）——打到一半
        （ArenaFight 第一回合寫進存檔、場邊那一句等著鎖外重寫）。ring 那一軌切在這裡（審查修正：拆成兩段，arena_more 接著打）。"""
        self.place("江小魚", None)
        self.choose("江小魚", "act:arena")
        self.choose("江小魚", "arena:join")
        view = self.main("江小魚")
        emit("江小魚 擂台上挑得到的", sorted(i for i in self.ids(view) if i.startswith("arena:")))
        with self.tweak(self.c.config.arena.crowd, chance=1.0, outrage_chance=1.0):
            self.choose("江小魚", self.fight_id("燕南天"))
            self.gamble("江小魚", crowd="離譜")  # 台下看不下去：場邊事件擲中「離譜」那一種
        self.me("江小魚", "放手一搏之後（擂台打到一半）")

    def arena_more(self) -> None:
        """江小魚接著打燕南天（ring 那一軌是新程式接手舊程式打到一半的那一場）：氣勢擺在 89 出招到收場（大勝：交換名次、留一筆給燕南天、
        收場卡）；伺服器在鎖外重寫場邊那一句（server.crowd_once：ring 那一軌重寫的是舊程式記下的單子）。"""
        with self.tweak(self.c.config.arena.crowd, chance=1.0, outrage_chance=1.0):
            self.bout("江小魚", "arena", 89.0)
        self.me("江小魚", "挑完燕南天")
        self.begin()
        with self.model():
            emit("場邊那一句鎖外重寫", self.server.crowd_once(self.server.game_for("江小魚")))
        self.me("江小魚", "重寫之後")
        self.main("江小魚")
        self.ladder("挑完燕南天")

    def arena_refuse(self) -> None:
        """灰掉的挑擂鈕：今天的次數擺成用完（全部灰掉、寫明日再挑），按下去回原因、不寫紀錄；擺回來。"""
        today = self.today("江小魚")
        left = self.c.config.arena.per_day
        self.edit("江小魚", lambda p: (setattr(p, "arena_day", today), setattr(p, "arena_today", left)))
        emit("江小魚 今天的次數擺成用完", today)
        view = self.main("江小魚")
        emit("江小魚 灰掉的挑擂鈕", {i: o for i, o in sorted(self.ids(view).items()) if i.startswith("arena:")})
        self.choose("江小魚", self.fight_id("花無缺"))
        self.edit("江小魚", lambda p: setattr(p, "arena_today", 1))

    def arena_yield(self) -> None:
        """江小魚挑鐵心蘭（第二），出一招就認輸（落敗：名次不動、留一筆給鐵心蘭）。"""
        self.choose("江小魚", self.fight_id("鐵心蘭"))
        self.bout("江小魚", "arena", None, rounds=1)
        if self.chars.load("江小魚").player.arena is not None:
            self.choose("江小魚", "arena:yield")
        self.me("江小魚", "認輸之後")
        self.choose("江小魚", "arena:back")
        self.ladder("認輸之後")

    def defend(self) -> None:
        """守擂的人下一次同步補戰報與「守擂・挑的人」：燕南天（被挑贏、名次掉一名）、鐵心蘭（守住）。"""
        for who in ("燕南天", "鐵心蘭"):
            self.main(who)
            self.me(who, "補守擂之後")

    def wages(self) -> None:
        """換日（現實時間，同回體丹）：時鐘推過一天，第一個同步的人記前幾名的俸，每個人同步時領。"""
        STEP[0] += 1440
        emit("時鐘推過一天", None)
        self.wages_collect()

    def wages_collect(self) -> None:
        for who in ("花無缺", "鐵心蘭", "江小魚", "燕南天"):
            self.main(who)
            self.me(who, "換日之後")
        self.ladder("換日之後")

    # ── ring 那一軌（審查修正）切點前多走的兩段：bout 那一軌不走 ──

    def ring_yield(self) -> None:
        """鐵心蘭（第二）挑花無缺（第一），一開打就認輸（落敗：名次不動、留一筆給花無缺、兩人都打過一場）；不按返回，坐在擂台邊。"""
        self.place("鐵心蘭", None)
        self.choose("鐵心蘭", "act:arena")
        self.choose("鐵心蘭", self.fight_id("花無缺"))
        if self.chars.load("鐵心蘭").player.arena is not None:
            self.choose("鐵心蘭", "arena:yield")
        self.me("鐵心蘭", "挑花無缺認輸之後")
        self.ladder("鐵心蘭認輸之後")

    def wages_roll(self) -> None:
        """換日（同 wages 那一步，挪到切點前）：時鐘推過一天，邀月（沒上擂台）先同步，記下打過一場的前幾名的俸（還沒領）。"""
        STEP[0] += 1440
        emit("時鐘推過一天", None)
        self.main("邀月")
        self.ladder("換日記俸之後")

    def titles(self) -> None:
        """稱號被讀：花無缺（天下第一）的狀態列與名帖匣；邀月在潁川看他的玩家卡、看榜單、在酒肆打聽他（名氣）。"""
        self.place("花無缺", "yingchuan")
        self.place("邀月", "yingchuan")
        view = self.main("花無缺")
        emit("花無缺 狀態列", view.get("status"))
        self.call("花無缺", "GET", "/api/mingtie")
        self.call("邀月", "GET", "/api/peer?name=花無缺")
        self.call("邀月", "GET", "/api/boards")
        self.choose("邀月", "act:tavern")
        self.do("邀月", "tavern", {"op": "seek", "target": "花無缺", "text": ""})
        self.choose("邀月", "tavern:back")

    def depart(self) -> None:
        """坐在擂台邊動身：鐵心蘭打開擂台，從輿圖安排前往被擋（atlas.travel_block）；Game._depart 在鎖裡直接叫一次（同酒肆那一軌：坐在
        店裡的人平常走不到這一行），擂台跟別的店一起收起來、動身上路。之後擺回原地。"""
        from tianxia import atlas
        from tianxia.engine import Game

        start = self.chars.load("鐵心蘭").player.location
        dest = self.c.locations[start].connections[0] if self.c.locations[start].connections else start
        self.place("鐵心蘭", start)
        self.choose("鐵心蘭", "act:arena")
        self.call("鐵心蘭", "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.me("鐵心蘭", "從輿圖安排前往之後")
        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load("鐵心蘭"), world=self.world)
            game.sync(CLOCK[0])
            route = atlas.way_to(game.state, self.c, dest)
            emit("鐵心蘭 直接動身", game._depart(route, "walk") if route is not None else None)
            self.chars.save(game.state)
        self.me("鐵心蘭", "動身之後")
        self.place("鐵心蘭", start)

    def closed(self) -> None:
        """擂台開關關掉（記憶體裡，做完開回來）：燕南天開著時坐進擂台、照那一刻建一份 Game（沒有收店）；關掉之後不 sync，選單照舊是擂台
        那一串、假人看「返回」照舊 0 分、按得出去。憐星坐進擂台之後關掉、再同步：收店、入口沒了、挑擂與報名都被拒。"""
        from tianxia import bot_policy
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        self.choose("燕南天", "act:arena")
        self.choose("憐星", "act:arena")
        self.begin()
        game = Game(self.c, self.chars.load("燕南天"), world=self.world)
        cfg = self.c.config.arena
        before = cfg.enabled
        cfg.enabled = False
        try:
            menu = game.options(odds=False)
            emit("關掉那一刻 燕南天的選單（沒有 sync）", [o.id for o in menu])
            back = next((o for o in menu if o.id == "arena:back"), None)
            if back is not None:
                emit("關掉那一刻 假人看返回", bot_policy.score(game, back, BotProfile(personality="普通", seed=1)))
                emit("關掉那一刻 返回", game.choose("arena:back"))
            view = self.main("憐星")
            emit("關著 憐星的選單", sorted(self.ids(view)))
            self.choose("憐星", "arena:join")
            self.choose("憐星", "act:arena")
            self.me("憐星", "關著")
        finally:
            cfg.enabled = before

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(13)、時鐘一輪推四分）：同一個資料庫補四個假人——錦衣客在長社撞上頭目
        （打到一半：take_turn 照架勢出招）、黑衣客坐在擂台邊（bot_policy.score 問單挑包「返回」那一顆）、另兩位閒著；bot_policy.ARENA_CHANCE
        換成 1（照舊是 bot_policy 的模組屬性，_arena 那一步照舊在 bot_policy）。整季機器人（bot.pick）在錦衣客的頭目戰選單上挑一顆（不按：
        那一場留給 BotRunner 照架勢打完）；灰衣客走到汝南荒野撞上黃巾小帥，那一場由整季機器人從頭按到尾（season_bot_duel，BotRunner 之前）。
        測試內容沒有頭目、擂台關著：只擺人、照跑。"""
        from collections import Counter

        from tianxia import bot, bot_policy, duel, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        for i, (name, loc) in enumerate(self.BOT_SEATS):
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
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=None, season_number=self.world.get_season_number())
            if loc in self.c.locations:
                p.location, p.journey = loc, None
                p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.picking_arena = i == 1
            self.chars.save(g.state)
            self.arm(name, 6 if i == 0 else 0)
            if i == 0:
                self.begin()
                with self.world.action_lock():
                    g = Game(self.c, self.chars.load(name), rng=random.Random(5), world=self.world)
                    g.client = None
                    g.sync(CLOCK[0])
                    boss = duel.available(g.state, self.c)
                    emit("錦衣客 撞上的頭目", None if boss is None else boss.id)
                    if boss is not None:
                        emit("錦衣客 開打", g._duel_start(boss))
                        emit("整季機器人在頭目戰的選單上挑", bot.pick(g, g.options(odds=False), random.Random(0)))
                    self.chars.save(g.state)
        self.season_bot_duel("灰衣客", "runan_wilds")  # BotRunner 之前：閒著的那一位（打完的冷卻與氣血照帶進 BotRunner）
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(13), clock=lambda: CLOCK[0])
        chance, tick, online = bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))}
        bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds = 1.0, 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_BOUT_TICKS", "30"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online = chance, tick, online
        states = self.chars.all(bots_only=True)
        emit("單挑假人 一輪一輪", dict(sorted(totals.items())))
        emit("單挑假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("單挑假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        self.ladder("假人之後")

    def season_bot_duel(self, name: str, loc: str) -> None:
        """整季機器人把一場頭目戰從頭打到尾（審查修正：以前只挑一顆、沒按下去）：name（剛補的、閒著的假人）走到 loc 撞上頭目，每一招照
        bot.pick 挑、照 Game.choose 按（同 bot.play_season），打到收場。在行動鎖裡、固定種子；測試內容沒有這個地點、沒有頭目：只寫一行。"""
        from tianxia import bot, duel
        from tianxia.engine import Game

        if loc not in self.c.locations:
            emit(f"{name} 整季機器人的頭目戰（這份內容沒有 {loc}）", None)
            return
        self.begin()
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(name), rng=random.Random(7), world=self.world)
            g.client = None
            g.sync(CLOCK[0])
            p = g.state.player
            p.location, p.journey = loc, None
            p.visited.add(loc)
            boss = duel.available(g.state, self.c)  # 經舊名 duel：base（搬包之前）沒有 Game._boss_ready
            emit(f"{name} 撞上的頭目（整季機器人）", None if boss is None else boss.id)
            picks: list[str | None] = []
            if boss is not None:
                g._duel_start(boss)
                rng = random.Random(0)
                while g.state.player.duel is not None and len(picks) < 20:
                    pick = bot.pick(g, g.options(odds=False), rng)
                    picks.append(pick)
                    if pick is None:
                        break
                    g.choose(pick)
            emit(f"{name} 整季機器人按的招", picks)
            self.chars.save(g.state)
        self.me(name, "整季機器人打完頭目")

    def season(self) -> None:
        """收季：江小魚挑花無缺打到一半（出一招）就收季——前三名排好、江湖史記擂主；江小魚同步時那一場作廢；前三名休季同步領季末的獎勵
        （名次被 bots 那一段的假人搶走的，照 BotRunner 在鎖裡同步一次：審查修正，以前只走到第三名）；江湖史的歷屆擂主。開下一季：
        單挑那十個欄位跟著新角色重來、季上的擂台是空的。"""
        self.place("江小魚", None)
        view = self.choose("江小魚", "act:arena")
        fights = [i for i, o in self.ids(view).items() if i.startswith("arena:fight:") and o.get("enabled")]
        emit("江小魚 收季之前挑誰", fights[:1])
        if fights:
            self.choose("江小魚", fights[0])
            self.bout("江小魚", "arena", None, rounds=1)
        self.me("江小魚", "收季之前打到一半")
        self.do(ADMIN, "end_season")
        self.ladder("收季之後")
        players = ("江小魚", "花無缺", "鐵心蘭", "燕南天")
        for who in players:
            view = self.main(who)
            self.me(who, "休季同步之後")
        placed = sorted((e.place, e.name) for e in self.world.get_season().arena.values() if e.place)
        emit("收季之後的前三名", placed)
        for _, name in placed:
            if name not in players:
                self.lock_sync(name)
                self.me(name, "休季同步之後")
        emit("江湖史", view.get("chronicle"))
        self.do(ADMIN, "next_season")
        for who in ("江小魚", "花無缺"):
            self.main(who)
            self.me(who, "換季之後")
        self.ladder("換季之後")


class RingScenario(BoutScenario):
    """同一套段落換個先後，切在擂台寫到一半（--track ring；審查修正，取代切在頭目戰打到一半的 boss 那一軌：那一刻 bout 那一軌的切點
    本來就跨過了）。切的那一刻，舊程式寫下、新程式接手的：江小魚挑燕南天放手一搏過一招（ArenaFight 打到一半）、場邊那一句等著鎖外
    重寫（arena_crowd_note；燕南天那邊的場邊帳記在季上）；鐵心蘭挑花無缺認輸（花無缺守擂的那一筆還沒補）、坐在擂台邊（picking_arena）；
    換過日、邀月同步時記下的俸還沒領（花無缺、鐵心蘭：打過一場的才有）。後半由新程式接著打完、重寫那一句、補戰報、領俸、收店。
    擂台那幾段多走 ring_yield、wages_roll（換日挪到切點前，後半的領俸不再推一天：一軌只推一天，週末季 2.5 天跑不完）。"""

    PHASES_FIRST = [n for n in BoutScenario.ALL[:BoutScenario.ALL.index("arena_fight")] if n != "resume"] + [
        "ring_yield", "wages_roll", "arena_fight"]
    PHASES_SECOND = ["resume", "arena_more", "arena_refuse", "arena_yield", "defend", "wages_collect", "titles", "depart", "closed",
                     "bots", "season"]


def _bout_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：bout 改擂台報名那一句（搬之前在 tianxia/arena.py、之後在包裡的 arena_rules.py），ring 改撞上頭目那一句
# （搬之前在 engine.py 的 _duel_start、之後在包裡的 duel_actions.py）
_bout_register_track("bout", BoutScenario, (("tianxia/features/bout/arena_rules.py", "tianxia/arena.py"),
                                             ("別人隨時可以來挑。", "別人隨時可以來挑！")), "week7")
_bout_register_track("ring", RingScenario, (("tianxia/features/bout/duel_actions.py", "tianxia/engine.py"),
                                             ("攔住了去路！", "攔住了去路。")), "week7")


# ═══════════════════════════ companions：人物情誼一軌（全部拆包第 19 批，dev/companions-1） ═══════════════════════════
# 同伴招募與名下、心意、託付與勸降、來信與委託、/api/figure 的本體從 engine.py 搬進新包 tianxia/features/companions/（stances、errands、letters
# 留成別名；心意的世界那一半進共用規則層 tianxia/stance_world.py；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後一行登記（_companions_register_track），PM 合的時候不跟別人的行穿插。新開的軌用原創名字（第 22 批 PM 認定第 3 條）。

COMPANIONS_TALK = "他沉吟了一會，點了點頭。"  # 假模型寫的對話那一輪
COMPANIONS_LETTER = "少俠台鑒：此事有勞，望勿推辭。"  # 假模型照他的口氣重寫的信
_COMPANIONS_CLIENTS: dict[type, type] = {}


def _companions_client(base: type) -> type:
    """人物對話、勸降、重寫書信的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["talk"] 給了（{stance}）時對話回一輪（心意開著
    那一種 schema 多填 stance）；MODEL["persuade"] 給了（0～100）時勸降回那個分數；MODEL["letter"] 給了時信回那一句。其餘照 base（丟連線錯誤）。"""
    if base not in _COMPANIONS_CLIENTS:
        class CompanionsClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                fields = getattr(schema, "model_fields", {})
                if schema.__name__ == "PersuadeJudgment" and MODEL.get("persuade") is not None:
                    return schema(success_rate=MODEL["persuade"])
                if schema.__name__ == "LetterText" and MODEL.get("letter") is not None:
                    return schema(letter=MODEL["letter"])
                if "option_tags" in fields and MODEL.get("talk") is not None:
                    extra = {"stance": MODEL["talk"]["stance"]} if "stance" in fields else {}
                    return schema(narrative=COMPANIONS_TALK, options=["勸他速攻", "勸他持重", "告辭"],
                                  option_tags=["真誠請教", "坦誠相待", "尋常寒暄"], **extra)
                return super().chat_structured(messages, schema, *a, **k)

        _COMPANIONS_CLIENTS[base] = CompanionsClient
    return _COMPANIONS_CLIENTS[base]


class CompanionsScenario(Scenario):
    """人物情誼（全部拆包第 19 批；--track companions，自己一個資料庫）。
    顧行舟招募：沒到情誼門檻沒有鈕；到了按下去婉拒、要求決鬥（失敗的兩支）、招到（名下、隊伍）；名下滿了灰掉。白鷺汀是黃巾：只追隨官軍的灰掉、
    慢一步按到有主的人回「已經被某某招攬走了」。溫景明按招募之前全服記號還在（同步先減半、按招募那一下清記號，_recruit_one 的 _settle_partings）。
    測試內容走舊的 act:recruit（recruit_at；_recruit）。名下：修練頁的名冊與人物卡（release_view）、移出、加入、本人與部下那兩句、放回江湖、放不是自己的。
    魏長卿在籌備中按名冊（_not_while_preparing）。陶秋水在談盧植（假模型歸一個心意）：選選項記到一筆（貢獻、/api/figure 的 my_stance_today），同一天再說
    不再記；速戰差一筆到門檻（天下大事、江湖史，下一次同步記行狀 _stance_annals）；**前半停在還在談**。石望舒託付自然來（情誼夠、送信日第一順位）、走到地點；
    程遠山、秦照夜各開一件勸降，韋南星一件送信一件探營：**前半切在託付還開著、信還沒回、委託做到一半**。柳聽泉收求援（附委託，沒看過、沒婉拒）。
    後半：陶秋水選下一顆、告辭；石望舒交差（交信、探營、勸降照開到哪一種）；勸降走一遍拒絕（不在地點、沒寫字、太長、沒有這一件）、模型叫不動（什麼都不發生）、
    成了（痕跡、推線、獎勵、行狀、心意 +1）、敗了（打一場）；韋南星探營（花體力、卡留見聞）、婉拒那一封、過了期限作罷（情誼扣）；柳聽泉鎖外重寫信
    （server.letter_once）、收起、婉拒委託、道賀（figure_life.spread 記的 cheers）、邀宴、委託過期、09:00 看守替他送信（server._notice_keys → morning_mail）、
    敬過酒的宴不邀、宴客關著不邀；欠人物的事過了期限，那幾句併進「書信」（debts）。人物頁 /api/figure（有心意有託付、沒有、不認得、太長的 id）。假人（BotRunner；心意直接記一筆 voice_stance、測試內容按舊招募）；時鐘往前推（跨 00:00、
    跨週：daily 換手與持重拉進度、週初歸零）；換季。沒有陣營、沒有託付、沒有盧植的設定寫「沒有」略過，同一串 API 照打。"""

    RECRUITER, RIVAL, DRIFTER, PREP = "顧行舟", "白鷺汀", "溫景明", "魏長卿"
    TALKER, MAILER, RUNNER, ENVOY, LOSER, LAPSER = "陶秋水", "柳聽泉", "石望舒", "程遠山", "秦照夜", "韋南星"
    PLAYERS = {RECRUITER: "guan", RIVAL: "huang", DRIFTER: None, TALKER: "guan", MAILER: "guan", RUNNER: "guan", ENVOY: "guan", LOSER: "guan",
               LAPSER: "guan"}
    BOT_SEATS = ["情甲", "情乙", "情丙"]
    LUZHI = "luzhi"
    PHASES_FIRST = ["setup", "seat", "recruit", "named", "talk", "errands_open", "letters_open", "half"]
    PHASES_SECOND = ["resume", "talk_on", "errands_on", "persuade", "lapse", "letters_on", "debts", "figure_page", "bots", "clock", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _companions_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def everyone(self) -> list[str]:
        return list(self.PLAYERS)

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def tuned(self, owner=None, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config if owner is None else owner
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {k: v for k, v in values.items()})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def on_errands(self) -> bool:
        from tianxia import errands

        return errands.on(self.c, self.world.get_season())

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：心意帳、託付、信、流水號、送信日、等著寫的道賀、隊伍、情誼（這幾位）、體力、貢獻、銀兩、心得，行狀與最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "stance_notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())},
            "errands": [e.model_dump(mode="json") for e in p.errands], "letters": [x.model_dump(mode="json") for x in p.letters],
            "letter_seq": p.letter_seq, "letter_day": p.letter_day, "cheers": list(p.cheers), "team": list(p.team),
            "affinities": dict(sorted(p.affinities.items())), "parted_done": list(p.parted_done), "stamina": p.stamina, "contrib": p.contrib,
            "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "annals": [[a.kind, a.text, a.figure] for a in p.annals],
            "pending_companion": p.pending_companion, "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:3]]})

    def season_view(self, tag: str) -> None:
        """季上這一包碰得到的：心意的計數、此刻照著做的、週；名下（全服）；痕跡；最近的天下大事與江湖史。"""
        s = self.world.get_season()
        emit(f"季上 {tag}", {
            "counts": {k: dict(sorted(v.items())) for k, v in sorted(s.stance_counts.items())},
            "active": {k: v.model_dump(mode="json") for k, v in sorted(s.stance_active.items())}, "week": s.stance_week,
            "owners": {k: [v.owner, list(v.parted_from)] for k, v in sorted(self.world.companions().items()) if v.owner or v.parted_from},
            "marks": dict(sorted(s.marks.items())), "rumors": [r.text for r in s.rumors[-4:]], "chronicle": [r.text for r in s.chronicle[-3:]]})

    def buttons(self, who: str, prefix: str) -> list:
        view = self.main(who)
        return [o for i, o in self.ids(view).items() if i.startswith(prefix)]

    def beside(self, who: str, cid: str) -> None:
        """站到這位人物此刻在的地方（人物活起來的季他會走動）。"""
        from tianxia import figure_life

        loc = figure_life.where(GameStateHolder(self.world.get_season()), self.c, cid)
        emit(f"{cid} 此刻在", loc)
        self.place(who, loc)

    def errand_of(self, who: str, *status) -> object | None:
        state = self.chars.load(who)
        rows = [e for e in state.player.errands if not status or e.status in status]
        return rows[-1] if rows else None

    def give(self, who: str, fid: str, eid: str) -> None:
        """直接開一件（同 errands.offer 挑中之後那一下；Game.persuade 的測試也這樣開）。"""
        from tianxia import errands

        self.edit_state(who, lambda s: errands.give(s, self.c, fid, eid))
        self.me(who, f"開一件 {eid}")

    def press_errand(self, who: str, tag: str) -> None:
        """照身上那一件的種類按「此地」那一顆（交信、探營直接辦；勸降先叫出輸入框、再寫一句）。"""
        e = self.errand_of(who, "open")
        if e is None:
            emit(f"{who} {tag}：身上沒有還開著的託付", None)
            return
        self.place(who, e.target)
        verb = {"letter": "deliver", "scout": "scout", "persuade": "persuade"}[e.kind]
        emit(f"{who} {tag} 選單上那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:{verb}:{e.id}")
        if e.kind == "persuade":
            MODEL["persuade"] = 70
            self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
            MODEL["persuade"] = None
        self.me(who, f"{tag} 之後")

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
        for who in [self.PREP, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            if who == self.PREP:  # 籌備中（管理者還沒開季）：名冊那三顆只回一句（_not_while_preparing；測試內容自動開季，照常做）
                for op in ("join", "leave", "release"):
                    self.call(who, "POST", f"/api/menxia/{op}", {"person": "player"})
                self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)

    def seat(self) -> None:
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
            self.me(who, "站好")

    def recruit(self) -> None:
        """招募：見上。十五位那一套（正式內容）站涿郡、測試內容站 town（舊的 act:recruit）。"""
        who, rival, drifter = self.RECRUITER, self.RIVAL, self.DRIFTER
        if "liubei" not in self.c.characters:
            self.place(who, "town")
            self.main(who)
            emit("舊招募那一顆", self.buttons(who, "act:recruit"))
            with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=0.0):
                self.choose(who, "act:recruit")
            with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=1.0):
                self.choose(who, "act:recruit")
            with self.tuned(recruit_base_chance=9.0):
                for _ in range(4):
                    self.place(who, None)
                    self.choose(who, "act:recruit")
                    self.me(who, "舊招募按一次")
            self.place(rival, "cave")
            emit("此地沒有人招得了", self.choose(rival, "act:recruit"))
            self.season_view("舊招募之後")
            return
        self.beside(who, "guanyu")
        emit("還沒到情誼門檻", self.buttons(who, "act:recruit"))
        self.edit(who, lambda p: p.affinities.update({"liubei": 40, "guanyu": 40, "zhangfei": 40}))
        emit("到了情誼門檻", self.buttons(who, "act:recruit"))
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=0.0):
            self.choose(who, "act:recruit:guanyu")
        self.me(who, "招募被婉拒")
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=1.0):
            self.choose(who, "act:recruit:guanyu")
        self.me(who, "招募被要求決鬥")
        self.world.try_recruit("caocao", who, cap=3)
        self.world.try_recruit("yuanshao", who, cap=3)
        with self.tuned(recruit_base_chance=9.0):
            for _ in range(4):
                if self.world.get_companion("liubei").owner is not None:
                    break
                self.beside(who, "liubei")
                self.choose(who, "act:recruit:liubei")
        self.me(who, "招到一位")
        self.beside(who, "guanyu")
        emit("名下滿了", self.buttons(who, "act:recruit"))
        self.choose(who, "act:recruit:guanyu")
        self.beside(rival, "guanyu")
        self.edit(rival, lambda p: p.affinities.update({"liubei": 40, "guanyu": 40, "zhangfei": 40}))
        emit("黃巾看到的", self.buttons(rival, "act:recruit"))
        self.choose(rival, "act:recruit:guanyu")
        self.choose(rival, "act:recruit:liubei")  # 慢一步：有主了（Refused）
        self.beside(drifter, "xunyu")
        self.edit(drifter, lambda p: p.affinities.update({"xunyu": 90}))
        self.world.update_companion("xunyu", lambda pr: pr.parted_from.append(drifter))
        self.season_view("回江湖的記號")
        with self.tuned(recruit_base_chance=9.0):
            self.choose(drifter, "act:recruit:xunyu")  # 同步先減半、按下去那一下清記號
        self.me(drifter, "回江湖的人再招")
        self.season_view("招募之後")

    def named(self) -> None:
        """名下：修練頁的名冊與人物卡（放他回江湖那一句）、移出、加入、本人與部下那兩句、放回江湖、名冊裡沒有的人、放不是自己的。"""
        who = self.RECRUITER
        roster_rows = (self.call(who, "GET", "/api/menxia")[1] or {}).get("roster") or []
        keys = [r["key"] for r in roster_rows]
        emit("名冊", roster_rows)
        mate = next((k for k in keys if k != "player" and not k.startswith("follower:")), None)
        if mate is not None:
            emit("人物卡的放回江湖", (self.call(who, "GET", f"/api/menxia?person={mate}")[1] or {}).get("release"))
            self.call(who, "POST", "/api/menxia/leave", {"person": mate})
            self.call(who, "POST", "/api/menxia/join", {"person": mate})
        emit("本人那一列的放回江湖", (self.call(who, "GET", "/api/menxia?person=player")[1] or {}).get("release"))
        self.call(who, "POST", "/api/menxia/join", {"person": "player"})
        self.call(who, "POST", "/api/menxia/leave", {"person": "player"})
        self.call(who, "POST", "/api/menxia/release", {"person": "player"})
        self.call(who, "POST", "/api/menxia/join", {"person": "沒這個人"})
        if "follower_guan_spear" in self.c.followers:
            self.edit(who, lambda p: setattr(p, "followers", ["follower_guan_spear"]))
        self.call(who, "POST", "/api/menxia/join", {"person": "follower:0"})
        self.call(who, "POST", "/api/menxia/leave", {"person": "follower:0"})
        self.edit(who, lambda p: setattr(p, "followers", []))
        if mate is not None:
            self.call(who, "POST", "/api/menxia/release", {"person": mate})
            self.me(who, "放回江湖之後")
            self.main(who)
            self.call(self.RIVAL, "POST", "/api/menxia/release", {"person": mate})  # 不在他的名冊上
        self.season_view("名下之後")

    def talk(self) -> None:
        """人物心意：陶秋水在跟盧植談（直接擺成上一輪給了選項；tests/kit/stances_kit.talking 同一個擺法）。速戰差一筆到門檻，選第一顆、模型歸速戰：記一筆
        （貢獻、過門檻：天下大事、江湖史；/api/figure 的 my_stance_today），下一次同步記行狀；再自己說一句：今天記過了不再記。前半停在還在談。"""
        who = self.TALKER
        if self.LUZHI not in self.c.characters:
            emit("這份內容沒有盧植", None)
            return
        self.place(who, "luzhi_camp")
        def talking(p) -> None:
            p.pending_companion = self.LUZHI
            p.last_offered_dialogue[self.LUZHI] = [["勸他趁黃巾未穩速攻廣宗", "告辭"], ["真誠請教", "尋常寒暄"]]
            p.affinities.setdefault(self.LUZHI, 20)

        self.edit(who, talking)
        view = self.main(who)
        emit("談話中的人物頁（main.figure）", view.get("figure") if isinstance(view, dict) else None)

        def nearly(s) -> None:  # 速戰差一筆到門檻（下面這一下就過門檻：天下大事、江湖史；下一次同步記行狀）
            from tianxia import stances

            if stances.on(self.c, s):
                s.stance_week, s.stance_counts = stances.week_of(self.c, s), {self.LUZHI: {"suzhan": 29}}

        self.world.mutate_season(nearly)
        MODEL["talk"] = {"stance": "suzhan"}
        self.choose(who, "talk:0")
        self.me(who, "記到一筆")
        self.season_view("過門檻")
        self.call(who, "GET", f"/api/figure?id={self.LUZHI}")
        self.main(who)  # 下一次同步：這一週勸過的心意到了門檻，記一則行狀（_stance_annals）
        self.me(who, "行狀")
        MODEL["talk"] = {"stance": "chizhong"}
        self.call(who, "POST", "/api/say", {"text": "不如持重些"})  # 今天記過了：不再記、不再給貢獻
        self.me(who, "同一天再說一句")
        MODEL["talk"] = None

    def errands_open(self) -> None:
        """託付：石望舒情誼夠、人物自然來信（送信日第一順位）；程遠山、秦照夜各開一件勸降，韋南星一件送信、一件探營。都不辦（切在這裡）。"""
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.edit(self.RUNNER, lambda p: p.affinities.update({self.LUZHI: 50}) if self.LUZHI in self.c.characters else None)
            self.main(self.RUNNER)
            self.me(self.RUNNER, "關著的季")
            return
        self.edit(self.RUNNER, lambda p: p.affinities.update({self.LUZHI: 50}))
        view = self.main(self.RUNNER)
        emit("託付的信（main.letter、main.errands）", [view.get("letter"), view.get("errands")])
        self.me(self.RUNNER, "託付來了")
        for who in (self.ENVOY, self.LOSER):
            self.edit(who, lambda p: p.affinities.update({self.LUZHI: 50}))
            self.give(who, self.LUZHI, "luzhi_persuade")
        self.edit(self.LAPSER, lambda p: p.affinities.update({self.LUZHI: 50, "huangfusong": 50}))
        self.give(self.LAPSER, self.LUZHI, "luzhi_scout")
        self.give(self.LAPSER, "huangfusong", "huangfu_letter")
        emit("不在地點：選單上沒有那一顆", self.buttons(self.ENVOY, "errand:"))
        self.call(self.ENVOY, "GET", f"/api/figure?id={self.LUZHI}")

    def letters_open(self) -> None:
        """書信：柳聽泉情誼夠的人物焦慮（聲威不到開季的一半），寫求援、附一件委託；信還沒看、委託還沒婉拒（切在這裡）。"""
        from tianxia import figures, letters

        who = self.MAILER
        if not letters.on(self.c) or "qinjie" not in self.c.characters:
            emit("這一季沒有書信", self.main(who).get("letter"))
            return
        self.world.mutate_season(lambda s: setattr(figures._ensure(GameStateHolder(s), self.c, "qinjie"), "prestige", 1))
        self.edit(who, lambda p: p.affinities.update({"qinjie": 40}))
        view = self.main(who)
        emit("求援的信（main.letter）", view.get("letter"))
        self.me(who, "求援來了")

    def half(self) -> None:
        for who in self.everyone():
            self.me(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def talk_on(self) -> None:
        """還在談：選下一顆（今天記過了）、告辭。"""
        who = self.TALKER
        if self.LUZHI not in self.c.characters:
            emit("這份內容沒有盧植", None)
            return
        MODEL["talk"] = {"stance": "xumin"}
        view = self.choose(who, "talk:1")
        self.me(who, "接著談")
        MODEL["talk"] = None
        opts = self.ids(view)
        emit("談話的選單", sorted(opts))
        self.choose(who, "talk:leave")
        self.me(who, "告辭")

    def errands_on(self) -> None:
        """石望舒照身上那一件的種類交差（半舊半新：舊程式開的、新程式辦完）。"""
        self.press_errand(self.RUNNER, "交差")
        self.choose(self.RUNNER, "errand:deliver:e999")
        if self.on_errands():  # 交信：走到就交（道謝信不佔一天一封、情誼照寫的數字給、貢獻、心意 +1、行狀）
            self.give(self.RUNNER, self.LUZHI, "luzhi_letter")
            self.press_errand(self.RUNNER, "交信")
        self.season_view("交差之後")

    def persuade(self) -> None:
        """勸降：拒絕的路、模型叫不動（什麼都不發生）、成了、敗了（打一場）。"""
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.do(self.ENVOY, "persuade_text", {"id": "e1", "text": "放下刀槍"})
            return
        who = self.ENVOY
        e = self.errand_of(who, "open")
        self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍"})  # 還不在地點
        self.place(who, e.target)
        emit("勸降那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:persuade:{e.id}")  # 只叫出輸入框：不寫紀錄
        self.me(who, "叫出輸入框")
        self.do(who, "persuade_text", {"id": e.id, "text": ""})
        self.do(who, "persuade_text", {"id": e.id, "text": "放" * 30})
        self.do(who, "persuade_text", {"id": "e999", "text": "放下刀槍"})
        MODEL["persuade"] = None
        self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍"})  # 模型叫不動
        self.me(who, "模型叫不動")
        jf = self.c.config.jianfa
        with self.tuned(jf, persuade_floor=100, persuade_cap=100):
            MODEL["persuade"] = 70
            self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
        self.me(who, "勸成了")
        self.season_view("勸成了")
        loser = self.LOSER
        e = self.errand_of(loser, "open")
        self.place(loser, e.target)
        with self.tuned(jf, persuade_floor=0, persuade_cap=0):
            self.do(loser, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
        MODEL["persuade"] = None
        self.me(loser, "勸不成、打一場")
        self.choose(loser, f"errand:persuade:{e.id}")  # 那一件沒了

    def lapse(self) -> None:
        """韋南星：探營（花體力、卡留在見聞）；另一封婉拒；再開一件過了期限作罷（情誼扣）。"""
        who = self.LAPSER
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.do(who, "letter_decline", {"id": -1})
            return
        scout = next(e for e in self.chars.load(who).player.errands if e.errand == "luzhi_scout")
        self.place(who, scout.target)
        emit("探營那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:scout:{scout.id}")
        self.me(who, "探營之後")
        emit("見聞裡那張卡", [r.text for r in self.world.get_season().rumors if r.layer == "personal" and r.character == who])
        letter = next(e for e in self.chars.load(who).player.errands if e.errand == "huangfu_letter")
        self.do(who, "letter_decline", {"id": letter.letter})
        self.me(who, "婉拒之後")
        self.do(who, "letter_decline", {"id": letter.letter})  # 第二次：沒有這封信可婉拒
        self.do(who, "letter_decline", {"id": -1})
        self.give(who, "bocai", "bocai_letter")

        def expire(s) -> None:
            s.player.errands[-1].expires = s.world.time - 1

        self.edit_state(who, expire)
        self.main(who)  # 同步：過了期限作罷，情誼扣
        self.me(who, "過了期限")

    def letters_on(self) -> None:
        """柳聽泉：鎖外重寫信（server.letter_once，假模型）、收起、婉拒委託、委託過期；道賀（figure_life.spread 記 cheers）、邀宴；09:00 的看守替他送信；
        敬過酒的宴不邀、宴客關著不邀（審查 M04：之前沒有人敬過酒，這兩個判斷沒有人走到）。"""
        from tianxia import figure_life, letters
        from tianxia.state import Feast, Toast

        who = self.MAILER
        if not letters.on(self.c) or "qinjie" not in self.c.characters:
            emit("這一季沒有書信", self.do(who, "letter_read", {"id": -1}))
            return
        self.main(who)
        game = self.server.game_for(who)
        MODEL["letter"] = COMPANIONS_LETTER
        self.begin()
        emit("鎖外重寫", self.server.letter_once(game))
        MODEL["letter"] = None
        self.begin()
        emit("再寫一次（寫過了）", self.server.letter_once(game))
        self.me(who, "重寫之後")
        self.server.GAMES.clear()
        view = self.main(who)
        card = view.get("letter") if isinstance(view, dict) else None
        emit("小卡", card)
        if card is not None:
            self.do(who, "letter_decline", {"id": card["id"]})
            self.do(who, "letter_read", {"id": card["id"]})
        self.do(who, "letter_read", {"id": -1})  # 沒有這封信
        self.me(who, "收起信")

        def cheers(s) -> None:  # 他欣賞你做的事（figure_life.spread 讓情誼往上動、情誼到 letter_affinity：記著等寫道賀）
            s.player.location = self.c.figures["zhangmancheng"].location
            s.player.affinities["qinjie"] = 45
            emit("風聞", figure_life.spread(s, self.c, "beat", "zhangmancheng", at=s.player.location, side="huang",
                                           text="在宛城打退了張曼成"))
            s.player.letter_day = -1

        self.edit_state(who, cheers)
        self.me(who, "記下道賀")
        self.main(who)
        self.me(who, "道賀的信")

        def feast(s) -> None:
            s.feast_seq += 1
            s.feasts.append(Feast(id=s.feast_seq, host="xushao", place="yingchuan", start=s.time, end=s.time + 2 * 3600))

        self.world.mutate_season(feast)
        self.edit(who, lambda p: (p.affinities.update({"xushao": 40}), setattr(p, "letter_day", -1)))
        self.main(who)
        self.me(who, "邀宴的信")
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.begin()
        game = self.server.game_for(who)
        with self.server._locked(game):
            notes, busy = self.server._notice_keys(game, self.login_of(who), CLOCK[0])
        emit("09:00 的看守", [[n.key for n in notes], busy])
        self.me(who, "看守之後")

        def expire(s) -> None:
            for letter in s.player.letters:
                if letter.task is not None and not letter.lapsed:
                    letter.task.expires = s.world.time - 1

        self.edit_state(who, expire)
        self.main(who)
        self.me(who, "委託過期")

        def toasted_feast(s) -> None:  # 再擺一場、你已經敬過酒：不邀；拿掉那一杯，宴客關著也不邀，開著才邀（_feast_letter 那兩個判斷，第 19 批改寫成 figure_life.feast_invites）
            s.feast_seq += 1
            s.feasts.append(Feast(id=s.feast_seq, host="xushao", place="yingchuan", start=s.time, end=s.time + 2 * 3600,
                                  toasts=[Toast(name=who, text="敬主人一杯", score=40, at=s.time)]))

        def no_toasts(s) -> None:
            for f in s.feasts:
                f.toasts.clear()

        self.world.mutate_season(toasted_feast)
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.main(who)
        self.me(who, "敬過酒的宴不邀")
        self.world.mutate_season(no_toasts)
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        with self.tuned(self.c.config.figure_life, feasts=False):
            self.main(who)
            self.me(who, "宴客關著不邀")
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.main(who)
        self.me(who, "拿掉那一杯才邀")

    def debts(self) -> None:
        """欠人物的事過了期限（ParleyDebt；parley.lapse，第 20 批搬）：同步時那幾句併進「書信」那一則（Game.sync 的 mail → deliver_mail，第 19 批改成帶出入參數的委派；審查 M14）。"""
        from tianxia.state import ParleyDebt

        who = self.MAILER
        cid = "qinjie" if "qinjie" in self.c.characters else next(iter(self.c.characters))

        def owed(s) -> None:
            s.player.parley_debts[cid] = ParleyDebt(kind="owe", condition="silver", due=s.world.time - 1)

        self.edit_state(who, owed)
        self.main(who)
        self.me(who, "欠他的事過了期限")

    def figure_page(self) -> None:
        """人物頁：有心意有託付的、沒有的、不認得的、太長的、沒帶 id。"""
        for who in (self.RUNNER, self.DRIFTER):
            for cid in (self.LUZHI, "bocai", "huangfusong", "zhangjiao", "nosuch", "x" * 80):
                self.call(who, "GET", f"/api/figure?id={cid}")
            self.call(who, "GET", "/api/figure")

    def clock(self) -> None:
        """時鐘往前推：跨 00:00（daily：換手、持重每天拉下對面的進度）、跨週（週初歸零）。先把心意擺成速戰在做事、持重票數追過，跨 00:00 換手，
        盧植那條線上自家佔著的地方擺一條對面的進度，持重拉得下來；痕跡的倍數、人物開的事件（碰過一次 met 今天不再抽到）、推線的倍數都讀世界那一半。"""
        from tianxia import conquest, figures, stances

        season = self.world.get_season()
        if not stances.on(self.c, season):
            emit("這一季沒有心意", stances.push_scale(GameStateHolder(season), self.c, self.LUZHI))
            STEP[0] += 1500
            self.main(self.TALKER)
            self.season_view("跨天")
            return
        from tianxia.state import StanceOn

        def preset(s) -> None:
            s.stance_week = stances.week_of(self.c, s)
            s.stance_counts = {self.LUZHI: {"chizhong": 50, "suzhan": 31}}
            s.stance_active = {self.LUZHI: StanceOn(stance="suzhan", at=s.time, week=s.stance_week)}

        self.world.mutate_season(preset)
        self.season_view("跨天之前")
        holder = GameStateHolder(self.world.get_season())
        emit("世界那一半讀到的", {"active": stances.active(holder, self.c, self.LUZHI).id, "push": stances.push_scale(holder, self.c, self.LUZHI),
                               "mark": stances.mark_scale(holder, self.c, "xiaquyang:band_turned"),
                               "closed": sorted(stances.closed_events(GameStateFor(self.chars.load(self.TALKER), holder.world), self.c))})

        def met(s) -> None:
            stances.met(s, self.c, "stance_luzhi_assault")
            emit("碰過那一則", sorted(stances.closed_events(s, self.c)))

        self.edit_state(self.TALKER, met)
        guarded = None
        if conquest.on(self.c, holder.world):
            fig = figures.state_of(holder, self.c, self.LUZHI)
            side = self.c.figures[self.LUZHI].faction
            guarded = next((loc for loc in conquest.blocks(self.c) if conquest.line_of(holder.world, self.c, loc) == fig.front
                            and conquest.holder(holder.world, self.c, loc) == side), None)
        if guarded is not None:
            self.preset_bar(guarded, "huang", 40.0, self.RIVAL)
        STEP[0] += 1500
        self.main(self.TALKER)
        self.season_view("跨了一天")
        if guarded is not None:
            emit("持重拉下對面的進度", [guarded, conquest.bars(self.world.get_season(), guarded)])
        STEP[0] += 60 * 24 * 8
        self.main(self.TALKER)
        self.season_view("跨了一週")
        self.me(self.TALKER, "跨了一週")

    def bots(self) -> None:
        """假人：BotRunner 十輪（正式內容的假人每天照名號雜湊直接記一筆心意 voice_stance：機會調成 1；測試內容沒有陣營，伺服器假人不出手）。
        整季機器人（bot.pick）站在託付的地點也不按 errand:（永遠按得下去的前綴），測試內容站 town 照挑舊的招募（act:recruit）。"""
        from collections import Counter

        from tianxia import bot, errands, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        start = "luzhi_camp" if "luzhi_camp" in self.c.locations else "town"
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=sides[i % 2] if sides else None,
                               season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, start, None
            p.visited.add(start)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            with self.tuned(self.c.config.jianfa, bot_stance_chance=1.0):
                for _ in range(int(os.environ.get("SB_COMPANIONS_TICKS", "10"))):
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("情誼假人 一輪一輪", dict(sorted(totals.items())))
        self.season_view("假人之後")
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"情誼假人 {name}", {"notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())}, "contrib": p.contrib,
                                     "errands": len(p.errands), "letters": len(p.letters), "team": list(p.team),
                                     "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        solo = Game.new(self.c, "情丁", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.tutorial_step = len(self.c.tutorial.steps)
        if self.on_errands():
            errands.give(solo.state, self.c, self.LUZHI, "luzhi_letter")
            p.location = p.errands[-1].target
        else:
            p.location = "lake" if "lake" in self.c.locations else start  # 測試內容的 town 前半都被招走了
        p.journey = None
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        rng = random.Random(9)
        for _ in range(12):
            picked = bot.pick(solo, solo.options(odds=False), rng)
            if picked is None or picked == "act:on_road":
                break
            solo.choose(picked)
            emit("整季機器人按了", [picked, [e.title for e in solo.state.journal[:1]], list(p.team)])

    def season(self) -> None:
        """收季、開下一季：託付、信、心意帳換季清掉；名下照全服的放掉。看守（morning_mail）：柳聽泉還停在上一季、情誼夠、等著寫道賀。看守那條路進鎖就換了季
        （server._locked → _reload → _reconcile_season：身上的信與道賀都清了），季數那道檢查走不到；所以再拿資料庫裡原樣的那一列直接問一次：拿掉檢查就真的會送
        （審查 M07；morning_mail 開著的 season21、week7，其餘的設定送信日是 None、本來就不送）。"""
        self.do(ADMIN, "end_season")
        self.main(self.RECRUITER)
        self.do(ADMIN, "next_season")
        if "qinjie" in self.c.characters:
            self.edit(self.MAILER, lambda p: (p.affinities.update({"qinjie": 45}), setattr(p, "cheers", ["qinjie|在潁川打退了黃巾"]),
                                              setattr(p, "letter_day", -1)))
        self.begin()
        game = self.server.game_for(self.MAILER)
        with self.server._locked(game):
            emit("看守那條路（進鎖已換季）", [game.morning_mail(CLOCK[0]), len(game.state.player.letters), list(game.state.player.cheers)])
            game.state = self.chars.load(self.MAILER)
            emit("還停在上一季的人", [game.morning_mail(CLOCK[0]), len(game.state.player.letters), list(game.state.player.cheers)])
        for who in self.everyone():
            self.main(who)
            self.me(who, "換季之後")
        self.season_view("換季之後")


class GameStateHolder:
    """世界那一半的函式只讀 state.world：季上直接問時（不是誰的存檔）的最小一份。"""

    def __init__(self, world):
        self.world = world


class GameStateFor:
    """同上，closed_events 另外讀 state.player（這個人今天碰過那一則沒）。"""

    def __init__(self, state, world):
        self.player, self.world = state.player, world


def _companions_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _guide_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：託付辦成了那一句（errands.DONE；搬之前在 tianxia/errands.py、之後在包裡）
_companions_register_track("companions", CompanionsScenario, (("tianxia/features/companions/errands.py", "tianxia/errands.py"),
                                                              ('DONE = "{who}託你的事辦成了。"', 'DONE = "{who}託你的事辦成了！"')), "week7")


# ═══════════════════════════ sense：有所感與頓悟一軌（全部拆包第 24 批，dev/sense-1） ═══════════════════════════
# 有所感（探索撞上、選做法、擲中、畫一筆或順其自然）、自己畫字的意境（看圖取名的三段式）、特殊頓悟（拷問、小試、心魔、取名）的本體從
# engine.py 與 tianxia/sensing.py、epiphany.py、glyph.py、insight_llm.py 搬進新包 tianxia/features/sense/（舊名留成別名；計畫
# docs/superpowers/plans/2026-11-01-有所感包-第1批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記（_sense_register_track），
# PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

SENSE_NAME = ("寒潭孤月", "像深夜的潭水，冷而圓滿。")  # 假模型替自己悟的意境取的名字與一句說明（insight_llm.name 的 B 段）
SENSE_GODS = ["雲外天心", "孤峰雪意", "滄海潮生"]  # 假模型替神品意境一次取的三個名字（epiphany.propose_names 的 B 段）
SENSE_OWN = ("靜水流深", "空山聽雨")  # 自己替神品意境寫的名字（dunwu:own 帶 text）
_SENSE_CLIENTS: dict[type, type] = {}


def _sense_client(base: type) -> type:
    """取名的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["sense"] 開著時，替自己悟的意境取名（naming.NameReply）回
    SENSE_NAME、替神品意境取名（epiphany.GodNames）回 SENSE_GODS；其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _SENSE_CLIENTS:
        class SenseClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if MODEL.get("sense") and schema.__name__ == "NameReply":
                    return schema(name=SENSE_NAME[0], description=SENSE_NAME[1])
                if MODEL.get("sense") and schema.__name__ == "GodNames":
                    return schema(names=list(SENSE_GODS))
                return super().chat_structured(messages, schema, *a, **k)

        _SENSE_CLIENTS[base] = SenseClient
    return _SENSE_CLIENTS[base]


def _sense_test_scene():
    """測試內容沒有有所感的場景：湖邊補一段（同 tianxia/features/sense/tests/test_sensing.py 的湖風；湖邊悟得到柔〔水〕與快〔風〕）。"""
    from tianxia.models import InsightScene, SenseMethod

    return InsightScene(
        id="sb_lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
    )


class SenseScenario(ExploreScenario):
    """有所感與頓悟（全部拆包第 24 批；--track sense，自己一個資料庫）。小工具借探索那一軌的（draws、fights、tweak、edit_state）。
    二十三個網頁上建的散人與一個走草廬的新人（林聽松）：
    - 草廬（不帶、weekend）：序章第 3 步的有所感版（舊探索 _explore_outcome 開卡、做法都對、必中，做法底下沒有小字），順其自然悟到。
    - 探索撞上有所感（探索一顆開著抽到感悟；三選一按靜心感悟；舊探索只留悟意境那一支；測試內容補一段湖邊的場景）：石觀潮選對、擲中、
      順其自然（落回這一處的基本意境、紀錄「有所感・場景」）；晏棲遲選錯（這一處到換日之前悟不出：三選一的灰鈕、舊探索那一行；一類一顆
      給心得）、再探索一次；穆青梧選對、沒擲中（給一點心得）。擲中與否照 sense_rate_range 擺到頂或到底。
    - 自己畫一筆：韋寒汀按「畫下來」（只叫出畫布）、暖機、讀筆畫（讀得出、只點了一下、格式不對）、送一筆讀不出的（400）、畫一筆落回
      基本意境、畫完再送（那一刻已經過去，400）；江照晚畫一筆要取名的——模型擋著，走退路字表、不記首悟；祁問山（假模型取名：
      看圖拿到名字，記首悟「你是第一個」）、賀知秋（同一處、同一個做法、同一筆：不是第一個）。
    - 特殊頓悟（season21、week7 開著；其餘寫「沒有」、照樣有所感）：擲中感悟時保底（epiphany_dry 擺到 pity）、小試照寫好的那一種
      （epiphany._trial 換掉）。顧折柳：拷問四題、靜候（trial_wait_days 擺 0）、心魔打贏、靜心思名（模型擋著，字表）、自己寫沒帶字、挑第一個。
      蘇停雲：探訪三回、心魔打輸——**前半停在「心魔未破」的卡掛著**；後半收下卡、到了再打的時候（retry_at 擺回去）打贏、靜心思名
      （假模型取三個）、自己寫不合格的、合格的。陸聞箏：打贏一場（探索的遭遇）、心魔打贏——**前半停在等著取名**（還沒按靜心思名）；後半
      自己寫一個這一季已經有人用掉的、換一個。溫行簡：拷問答了一題，到季末沒了結（此事未了）。
    - 寫到一半的有所感：紀守拙停在選做法、裴映雪停在感悟狀態（前半停下）；後半紀守拙選對擲中順其自然；裴映雪先在鎖裡直接開單、人走開再
      交回（C 段重驗對不上），再照常畫一筆。
    - 走一趟停在有所感的卡上（season21、week7 開著；其餘寫「沒有」。審查補的：搬了 outing_watch，以前這一軌沒有 /api/do/outing）：
      岑望舒選對擲中、**前半停在感悟狀態**，後半畫一筆、接著走；杜聽瀾**前半停在卡上**，後半選對、畫一筆要取名的（假模型）；辛遠岫順其自然；
      俞照川保底中了頓悟、拷問、心魔打贏、**前半停在等著取名**，後半靜心思名、挑第一個、接著走。一般的一筆沒有數值變化、beat.after 是空的，
      所以計南枝、盧半溪再各走一次，讓悟的那一下（sensing.finish）、思名的那一下（epiphany.fill）多帶一行料：得失要記在那一段。
      method 每一次都把擲特殊頓悟乘多少寫進輸出（走一趟照這一趟幾段、不在路上是 1）。
    - 清失效參照與畫完清掉的（審查補的）：褚臨風**前半停在卡上**，後半人被帶走、下一次讀檔清掉；費疏影畫完清掉 guide_done 與 battle_card
      （畫之前擺一筆真的戰報，不然讀檔就清了、看不出差別）；籌備中（Game._preparing 換成真）阮晴川畫一筆被擋、涂松聲靜心思名不開單。
    - 假人：BotRunner 四個（一個停在有所感的卡、一個停在感悟狀態、一個等著取名〔頓悟開著的季〕、一個閒著），假模型接取名的 B 段
      （SenseJob、EpiphanyJob）；整季機器人在卡上挑哪一顆也寫下來。
    - 收季、開下一季：石觀潮又撞上一張卡沒了結、溫行簡的頓悟沒了結；換季之後看每個人。"""

    PLAYERS = {name: None for name in ("石觀潮", "晏棲遲", "穆青梧", "韋寒汀", "江照晚", "祁問山", "賀知秋", "顧折柳", "蘇停雲", "陸聞箏",
                                       "紀守拙", "裴映雪", "溫行簡",
                                       "岑望舒", "杜聽瀾", "辛遠岫", "俞照川", "計南枝", "盧半溪", "褚臨風", "費疏影", "阮晴川", "涂松聲")}
    NEWBIE = "林聽松"
    BOT_SEATS = ["悟甲", "悟乙", "悟丙", "悟丁"]
    PHASES_FIRST = ["setup", "prologue", "meet", "miss", "canvas", "named", "epiphany", "demon_lost", "pending", "trip_first", "half"]
    PHASES_SECOND = ["resume", "pending_on", "demon_on", "naming_on", "trip_on", "trip_gains", "stale_on", "clears", "preparing", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import insights, ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("sense"):
                client.__class__ = _sense_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        if profile == "test":  # 測試內容沒有有所感的場景：湖邊補一段（前半、後半是兩個行程，各自補；兩份程式同一份內容）
            scene = _sense_test_scene()
            self.c.insight_scenes = {scene.id: scene}

        def ok(loc_id: str) -> bool:
            loc = self.c.locations.get(loc_id)
            return loc is not None and bool(insights.scenes_for(loc, self.c)) and bool(insights.explore_gives(loc, self.c))

        self.spot = next((i for i in ("yingshui", "baima_ford", "lake", *sorted(self.c.locations)) if ok(i)), None)

    # ── 小工具 ──

    def epiphany_on(self) -> bool:
        return bool(self.c.config.epiphany.enabled)

    def me(self, who: str, tag: str) -> None:
        """存檔裡有所感與頓悟碰得到的那幾格：所在、那一份感悟、流水號、選錯的帳、意境與私有意境、頓悟的次數與保底、等著取名的那一個、
        一條線的進度與跳出來的卡、心得、體力、最新三則紀錄（標題、標記、頭幾行、畫的那一筆幾個點）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "sensing": None if p.sensing is None else p.sensing.model_dump(mode="json"), "serial": p.sense_serial,
            "misses": dict(sorted(p.sense_misses.items())), "insights": list(p.insights),
            "own": {k: [v.name, v.attribute, v.note, v.place, len(v.glyph)] for k, v in sorted(p.own_insights.items())},
            "epiphanies": [p.epiphanies, p.epiphany_dry], "god": None if p.god_naming is None else p.god_naming.model_dump(mode="json"),
            "lines": {k: v.model_dump(mode="json") for k, v in sorted(p.storylines.items())}, "open": p.story_open,
            "cards": [x.model_dump(mode="json") for x in p.story_cards], "xinde": p.stats.get("xinde", 0), "stamina": p.stamina,
            "journal": [[e.title, e.tag, list(e.lines)[:4], len(e.glyph)] for e in state.journal[:3]]})

    @contextlib.contextmanager
    def insight_only(self):
        """舊探索（測試內容；序章以外三選一關著的那一種）這一下落在悟意境那一支：Game._explore_weights 只回悟意境（兩份程式都在 engine，
        同一步換、同一步換回）。"""
        from tianxia.engine import Game

        real = Game._explore_weights
        Game._explore_weights = lambda game, loc: [("insight", 1.0)]
        try:
            yield
        finally:
            Game._explore_weights = real

    def sensed(self, who: str) -> None:
        """探索撞上有所感（體力補滿、站到有場景的那一處）：探索一顆開著抽到感悟（draws）；三選一（不帶、weekend）按「靜心感悟」那一顆；
        舊探索（測試內容）只留悟意境那一支。奇遇與頭目這一下不擲（rare_explore_chance、duel.explore_chance 擺 0）。"""
        explore_one = _explore_rules()
        self.place(who, self.spot)
        with self.draws(explore_one.INSIGHT), self.insight_only(), self.tweak(self.c.config, rare_explore_chance=0.0), \
                self.tweak(self.c.config.duel, explore_chance=0.0):
            self.choose(who, "act:explore")
            sense = self.options(who).get("explore:sense")
            if sense is not None and sense.get("enabled"):
                self.choose(who, "explore:sense")
        self.me(who, "探索之後")

    def right_of(self, state, right: bool = True) -> str | None:
        """卡上第一個選得對（right）或選錯的做法（照洗過的順序；序章四景都對）；不在選做法是 None。只讀。"""
        from tianxia import insights

        s = state.player.sensing if state is not None else None
        if s is None or s.stage != "choose":
            return None
        scene, loc = self.c.insight_scenes.get(s.scene), self.c.locations.get(s.location)
        if scene is None or loc is None:
            return None
        pool = insights.pool_attributes(loc, self.c)
        return next((f"sense:{i}" for i, j in enumerate(s.order) if (scene.prologue or scene.methods[j].attribute in pool) == right), None)

    def method(self, who: str, right: bool = True, hit: bool | None = True) -> None:
        """選一個做法（right：選得對不對）；hit 是擲不擲中（sense_rate_range 擺到頂或到底、痕跡不加；None 照擲）。擲中時特殊頓悟的機率
        擺到極小（照樣擲那一顆骰、沒中記一次保底；要頓悟的人另外把保底擺滿，begin_line），不然照固定的亂數偶爾就中了、情境走岔。"""
        oid = self.right_of(self.chars.load(who), right)
        if oid is None:
            emit(f"{who} 卡上沒有{'對' if right else '錯'}的做法可選", None)
            return
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.roll_boost(who))
            if hit is not None:
                stack.enter_context(self.tweak(self.c.config, sense_rate_range=(100, 100) if hit else (0, 0), sense_marks_bonus=0))
            if hit:
                stack.enter_context(self.tweak(self.c.config.epiphany, chances=[1e-9] * 3))
            self.choose(who, oid)
        self.me(who, "選了做法之後")

    @contextlib.contextmanager
    def roll_boost(self, who: str):
        """擲特殊頓悟乘多少寫進輸出（epiphany.roll 包一層，兩份程式同一步換、同一步換回；骰子照常擲）。"""
        from tianxia import epiphany

        real = epiphany.roll

        def roll(state, content, rng, boost: float = 1.0):
            emit(f"{who} 擲特殊頓悟的倍數", boost)
            return real(state, content, rng, boost=boost)

        epiphany.roll = roll
        try:
            yield
        finally:
            epiphany.roll = real

    def seen(self, who: str, tag: str) -> None:
        """走一趟那一份（每一段的 after 在裡面）與有所感碰得到的那幾格。"""
        self.player_view(who, tag)
        self.me(who, tag)

    def trip_out(self, who: str) -> bool:
        """走一趟三段出發、第一段就撞上有所感停下來（抽到感悟；奇遇與頭目這一下不擲）。沒有走一趟的季寫「沒有」、回假。"""
        if self.main(who).get("outing") is None:
            emit(f"{who} 這一季沒有走一趟", None)
            return False
        self.place(who, self.spot)
        with self.draws(_explore_rules().INSIGHT), self.tweak(self.c.config, rare_explore_chance=0.0), \
                self.tweak(self.c.config.duel, explore_chance=0.0):
            self.do(who, "outing", {"n": 3})
        self.seen(who, "出發之後")
        return True

    def god_waiting(self, who: str, start) -> None:
        """start（站到有場景的那一處、撞上卡）之後保底中了特殊頓悟、拷問四題、靜候、心魔打贏，停在等著取名（還沒按靜心思名）。"""
        pity = self.c.config.epiphany.pity
        self.edit(who, lambda p: setattr(p, "epiphany_dry", pity))
        start(who)
        with self.trial("wait"):
            self.method(who, right=True, hit=True)
        with self.tweak(self.c.config.epiphany, trial_wait_days=0.0):
            self.answers(who)
            self.main(who)
        self.demon(who, "大勝")

    def stroke(self, who: str, name: bool) -> list | None:
        """畫哪一筆（glyph.SAMPLES 照屬性排第一個合的）：name 是要悟一個自己的新意境（要取名），否則落回這一處的基本意境。A 段只讀。"""
        from tianxia import glyph, sensing

        state = self.chars.load(who)
        for attr in sorted(glyph.SAMPLES):
            req = sensing.request(state, self.c, self.world, glyph.SAMPLES[attr])
            if not isinstance(req, str) and req.needs_name == name:
                return glyph.SAMPLES[attr]
        return None

    def paint(self, who: str, name: bool, png: str = "AAAA") -> None:
        """畫完那一筆送出（/api/sense：殼的三段式 A、B、C）。"""
        points = self.stroke(who, name)
        if points is None:
            emit(f"{who} 沒有{'要取名' if name else '落回基本意境'}的那一筆", None)
            return
        self.call(who, "POST", "/api/sense", {"points": points, "png": png})
        self.me(who, "畫完之後")

    def finish(self, who: str, rounds: int = 6) -> None:
        """眼前端出來的（事件卡、有所感、頭目）照第一顆按得下去的了結；有所感的感悟狀態一律順其自然（不按「畫下來」）。"""
        from tianxia import sensing

        for _ in range(rounds):
            opts = self.options(who)
            if "act:explore" in opts:
                return
            pick = sensing.LET_GO if sensing.LET_GO in opts else next(
                (i for pre in ("choice:", "sense:", "duel:") for i, o in opts.items()
                 if i.startswith(pre) and o.get("enabled") and i not in (sensing.DRAW, "duel:flee")), None)
            if pick is None:
                return
            self.choose(who, pick)

    @contextlib.contextmanager
    def trial(self, name: str):
        """這一次頓悟的小試照寫好的那一種（epiphany._trial 換掉；同 tianxia/features/sense/tests/test_epiphany.py 的 _begin）。"""
        from tianxia import epiphany

        real = epiphany._trial
        epiphany._trial = lambda state, content: (name, epiphany.TRIALS[name][0], -1)
        try:
            yield
        finally:
            epiphany._trial = real

    def begin_line(self, who: str, trial: str) -> None:
        """有所感選對、擲中，擲特殊頓悟：保底（這一季擲中感悟 pity 次都沒中，下一次必中，不動亂數）、小試照 trial。頓悟關著的季就停在感悟狀態。"""
        pity = self.c.config.epiphany.pity
        self.edit(who, lambda p: setattr(p, "epiphany_dry", pity))
        self.sensed(who)
        with self.trial(trial):
            self.method(who, right=True, hit=True)

    def answers(self, who: str, n: int = 4) -> None:
        """心靈拷問：照選單上第一個答案答 n 題（三題問心、一題心中之形）。"""
        for _ in range(n):
            pick = next((i for i, o in self.options(who).items() if i.startswith("story:") and ":a" in i and o.get("enabled")), None)
            if pick is None:
                emit(f"{who} 沒有要答的", None)
                return
            self.choose(who, pick)

    def demon(self, who: str, tier: str) -> None:
        """去面對心魔（story:<線> 那一顆，fight 段）：仗照寫好的 tier 打。"""
        fight = next((i for i, o in self.options(who).items() if i.startswith("story:") and i.count(":") == 1 and o.get("enabled")), None)
        if fight is None:
            emit(f"{who} 沒有心魔可以面對", None)
            return
        with self.fights(tier):
            self.choose(who, fight)
        self.me(who, f"心魔{tier}之後")

    def own_name(self, who: str, text: str):
        """神品意境自己取一個名字：/api/choose 帶 text（被擋時那一句回給表單）。"""
        return self.call(who, "POST", "/api/choose", {"id": "dunwu:own", "text": text})

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)  # 探索那一軌的 setup 另外擺它自己的人（高寄萍），這一軌不要

    def prologue(self) -> None:
        """草廬（不帶、weekend）：遇險、拜師、看修練頁，按探索——序章第 3 步的有所感版（舊探索開卡、做法都對、必中）；選第一個做法、
        順其自然。沒有草廬的季寫「沒有」。"""
        from tianxia import sensing

        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        self.me(who, "草廬的有所感")
        senses = [i for i, o in self.options(who).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.main(who)
        self.choose(who, sensing.LET_GO)
        self.me(who, "草廬悟到之後")

    def meet(self) -> None:
        """探索撞上有所感：卡上的做法、做法底下的兩行小字（sense_help）、場景；選對、擲中（感悟狀態：畫下來、順其自然）、順其自然。"""
        from tianxia import sensing

        who = "石觀潮"
        self.sensed(who)
        self.main(who)
        self.method(who, right=True, hit=True)
        self.main(who)
        self.choose(who, sensing.LET_GO)
        self.me(who, "順其自然之後")

    def miss(self) -> None:
        """選錯做法（這一處到換日之前悟不出：三選一的「靜心感悟」灰掉、舊探索那一行補一句；一類一顆給心得）、再探索一次（照它自己抽）；
        選對沒擲中（給一點心得）。"""
        who = "晏棲遲"
        self.sensed(who)
        self.method(who, right=False, hit=None)
        self.place(who, self.spot)
        self.main(who)
        self.choose(who, "act:explore")
        self.finish(who)
        self.me(who, "選錯之後再探索")
        who = "穆青梧"
        self.sensed(who)
        self.method(who, right=True, hit=False)

    def canvas(self) -> None:
        """自己畫一筆：「畫下來」只叫出畫布、暖機、讀筆畫（讀得出、只點了一下、格式不對）、送一筆讀不出的、畫一筆落回基本意境、畫完再送；
        江照晚畫一筆要取名的（模型擋著：退路字表、不記首悟）。"""
        from tianxia import glyph, sensing

        who = "韋寒汀"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.DRAW)
        self.call(who, "POST", "/api/sense_warm")
        self.call(who, "POST", "/api/sense_read", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]]})
        self.call(who, "POST", "/api/sense_read", {"points": [[1, 1, 0]]})
        self.call(who, "POST", "/api/sense_read", {"points": "x"})
        self.call(who, "POST", "/api/sense", {"points": [[1, 1, 0]], "png": ""})
        self.paint(who, name=False)
        self.call(who, "POST", "/api/sense", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]], "png": ""})
        who = "江照晚"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        self.paint(who, name=True)

    def named(self) -> None:
        """假模型取名：祁問山畫一筆要取名的（看圖拿到名字：記首悟「你是第一個」）；賀知秋同一處、同一個做法、同一筆（不是第一個）。"""
        MODEL["sense"] = True
        try:
            for who in ("祁問山", "賀知秋"):
                self.sensed(who)
                self.method(who, right=True, hit=True)
                self.paint(who, name=True)
        finally:
            MODEL["sense"] = False

    def epiphany(self) -> None:
        """顧折柳：保底中了特殊頓悟、拷問四題、靜候（trial_wait_days 擺 0）、心魔打贏、靜心思名（模型擋著：字表補三個）、自己寫沒帶字、挑第一個。"""
        from tianxia import sensing

        who = "顧折柳"
        self.begin_line(who, "wait")
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            self.choose(who, sensing.LET_GO)
            return
        with self.tweak(self.c.config.epiphany, trial_wait_days=0.0):
            self.answers(who)
            self.main(who)
        self.demon(who, "大勝")
        self.choose(who, "dunwu:think")
        self.choose(who, "dunwu:own")
        self.choose(who, "dunwu:0")
        self.me(who, "取名之後")

    def demon_lost(self) -> None:
        """蘇停雲：拷問、探訪三回、心魔打輸（「心魔未破」的卡掛著——前半停在這裡）；陸聞箏：拷問、打贏一場（探索的遭遇）、心魔打贏，
        停在等著取名（還沒按靜心思名）。"""
        from tianxia import sensing

        explore_one = _explore_rules()
        for who, trial in (("蘇停雲", "roam"), ("陸聞箏", "win")):
            self.begin_line(who, trial)
            if not self.epiphany_on():
                emit("這一季沒有特殊頓悟", None)
                self.choose(who, sensing.LET_GO)
                continue
            self.answers(who)
            kinds, tier = ((explore_one.MATERIAL,) * 3, None) if trial == "roam" else ((explore_one.ENCOUNTER,), "大勝")
            for kind in kinds:
                self.place(who, self.spot)
                with self.draws(kind), self.fights(tier):
                    self.choose(who, "act:explore")
                self.finish(who)
            self.main(who)
            self.demon(who, "落敗" if trial == "roam" else "大勝")
            self.main(who)

    def pending(self) -> None:
        """寫到一半的：紀守拙停在選做法、裴映雪停在感悟狀態；溫行簡的頓悟答了一題就擱著（到季末沒了結）。"""
        self.sensed("紀守拙")
        self.sensed("裴映雪")
        self.method("裴映雪", right=True, hit=True)
        who = "溫行簡"
        self.begin_line(who, "wait")
        if self.epiphany_on():
            self.answers(who, 1)
        self.me(who, "答了一題")

    def trip_first(self) -> None:
        """走一趟寫到一半（舊程式存下那一趟、新程式接著做完）：岑望舒選對擲中停在感悟狀態、杜聽瀾停在卡上、俞照川等著取名（頓悟開著的季）；
        褚臨風閒著撞上一張卡停著（後半人被帶走）。"""
        if self.trip_out("岑望舒"):
            self.method("岑望舒", right=True, hit=True)
            self.seen("岑望舒", "選了做法")
        self.trip_out("杜聽瀾")
        if self.main("俞照川").get("outing") is not None and self.epiphany_on():
            self.god_waiting("俞照川", self.trip_out)
            self.seen("俞照川", "心魔之後")
        self.sensed("褚臨風")

    def half(self) -> None:
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.me(who, "前半停下")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def trip_on(self) -> None:
        """新程式接手停著的一趟：畫一筆（sense_draw）、畫一筆要取名的（假模型）、順其自然、靜心思名（epiphany_names）；做完接著走。"""
        from tianxia import sensing

        who = "岑望舒"
        if self.main(who).get("outing") is None:
            emit("這一季沒有走一趟", None)
            return
        self.paint(who, name=False)
        self.seen(who, "畫完")
        self.do(who, "outing", {})
        self.seen(who, "接著走")
        who = "杜聽瀾"
        self.method(who, right=True, hit=True)
        MODEL["sense"] = True
        try:
            self.paint(who, name=True)
        finally:
            MODEL["sense"] = False
        self.seen(who, "畫完要取名")
        who = "辛遠岫"
        self.trip_out(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.LET_GO)
        self.seen(who, "順其自然")
        who = "俞照川"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
        self.seen(who, "思名之後")
        self.choose(who, "dunwu:0")
        self.seen(who, "取名之後")
        self.do(who, "outing", {})
        self.seen(who, "接著走")

    def trip_gains(self) -> None:
        """走一趟停在卡上，悟的那一下與思名的那一下多帶一行料（sensing.finish、epiphany.fill 包一層，兩份程式同一步換、同一步換回）：
        outing_watch 要把它記在那一段（beat.after）。沒有這一行的話一般的一筆與思名什麼都不記，看不出那一層在不在。"""
        from tianxia import epiphany, journal, materials, sensing

        who = "計南枝"
        if self.main(who).get("outing") is None:
            emit("這一季沒有走一趟", None)
            return
        self.trip_out(who)
        self.method(who, right=True, hit=True)
        real_finish = sensing.finish

        def finish(*args, **kwargs):
            msgs, own, by_model = real_finish(*args, **kwargs)
            return [*msgs, f"{materials.GRANT_PREFIX}寒鐵屑 ×1"], own, by_model

        sensing.finish = finish
        try:
            self.paint(who, name=False)
        finally:
            sensing.finish = real_finish
        self.seen(who, "畫完帶料")
        who = "盧半溪"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.god_waiting(who, self.trip_out)
        real_fill = epiphany.fill

        def fill(state, *args, **kwargs):
            msgs = real_fill(state, *args, **kwargs)
            journal.add_entry(state, journal.Draft("思名").entry(state.world.time, [f"{materials.GRANT_PREFIX}寒鐵屑 ×1"]))
            return msgs

        epiphany.fill = fill
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
            epiphany.fill = real_fill
        self.seen(who, "思名帶料")

    def stale_on(self) -> None:
        """褚臨風手上一張卡（舊程式存下的）、人被帶走：下一次讀檔清掉作廢的卡（_drop_stale_references 中段），選單不卡。"""
        who = "褚臨風"
        other = next(i for i in sorted(self.c.locations) if i != self.spot)
        self.edit(who, lambda p: setattr(p, "location", other))
        self.main(who)
        self.me(who, "人被帶走之後")

    def clears(self) -> None:
        """費疏影畫完那一筆清掉上一次的引導行與戰報卡（這條路不走 choose）。戰報擺一筆真的（id 不在戰報裡的話讀檔就清掉了，看不出差別）。"""
        from tianxia.state import BattleRecord

        who = "費疏影"
        self.sensed(who)
        self.method(who, right=True, hit=True)

        def dirty(state) -> None:
            state.player.guide_done = ["上一次的引導行"]
            state.battles.insert(0, BattleRecord(id=987654, time=state.world.time, location="河畔", kind="wild", opponent="流寇", ours=[],
                                                 tier="大勝", our_power=1, difficulty=1))
            state.battle_card = 987654

        self.edit_state(who, dirty)
        self.paint(who, name=False)
        state = self.chars.load(who)
        emit(f"{who} 畫完清掉", {"guide_done": list(state.player.guide_done), "battle_card": state.battle_card})

    def preparing(self) -> None:
        """賽季籌備中（Game._preparing 換成真，兩份程式同一步換、同一步換回）：阮晴川畫一筆被擋（sense_request）、涂松聲靜心思名不開單（epiphany_request）。"""
        from tianxia import glyph
        from tianxia.engine import Game

        who, namer = "阮晴川", "涂松聲"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        waiting = self.epiphany_on()
        if waiting:
            self.god_waiting(namer, self.sensed)
        real = Game._preparing
        Game._preparing = lambda game: True
        try:
            self.call(who, "POST", "/api/sense", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]], "png": ""})
            if waiting:
                self.choose(namer, "dunwu:think")
        finally:
            Game._preparing = real
        self.me(who, "籌備中畫")
        if waiting:
            self.me(namer, "籌備中思名")

    def pending_on(self) -> None:
        """新程式接手寫到一半的：紀守拙選對、擲中、順其自然；裴映雪先在鎖裡直接開單、人走開再交回（C 段重驗對不上，不存），再照常畫一筆。"""
        from tianxia import glyph, sensing
        from tianxia.engine import Game

        who = "紀守拙"
        self.main(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.LET_GO)
        self.me(who, "新程式接手之後")
        who = "裴映雪"
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(who), random.Random(0), self.world)
            req = g.sense_request(glyph.SAMPLES[sorted(glyph.SAMPLES)[0]])
            emit(f"{who} 直接開單", req if isinstance(req, str) else req.model_dump(mode="json"))
            if not isinstance(req, str):
                g.state.player.location = next(i for i in sorted(self.c.locations) if i != self.spot)
                emit(f"{who} 人走開了再交回", g.sense_draw(req, ("寒潭孤月", "")))
        self.paint(who, name=False)

    def demon_on(self) -> None:
        """蘇停雲：收下「心魔未破」的卡、到了再打的時候（retry_at 擺回去，同時間過了）、心魔打贏、靜心思名（假模型取三個）、
        自己寫不合格的（那一句回給表單）、合格的。"""
        who = "蘇停雲"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.do(who, "story_seen")

        def due(s) -> None:
            for progress in s.player.storylines.values():
                if progress.retry_at is not None:
                    progress.retry_at = 0.0
        self.edit_state(who, due)
        self.main(who)
        self.demon(who, "大勝")
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
        self.own_name(who, "ab")
        self.own_name(who, SENSE_OWN[0])
        self.me(who, "取名之後")

    def naming_on(self) -> None:
        """陸聞箏：自己寫一個這一季已經有人用掉的名字（擋下來、那一句回給表單）、換一個。"""
        who = "陸聞箏"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.main(who)
        self.own_name(who, SENSE_OWN[0])
        self.own_name(who, SENSE_OWN[1])
        self.me(who, "取名之後")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(17)、時鐘一輪推四步）：四個站在有場景的那一處——悟甲停在有所感的卡、
        悟乙停在感悟狀態、悟丙等著取名（頓悟開著的季：模板挑第一個）、悟丁閒著。假人程式帶一個假模型（取名的 B 段：SenseJob、EpiphanyJob）。
        整季機器人（bot.pick）在悟甲那張卡上挑哪一顆也寫下來。"""
        from collections import Counter

        from tianxia import bot, ollama_client, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile, GodNaming

        loc = self.c.locations[self.spot]
        god = next(iter(self.c.traits.god), None) if self.epiphany_on() else None
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.location, p.journey = self.spot, None
            p.visited.add(self.spot)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            if i in (0, 1):
                emit(f"假人 {name} 撞上有所感", g._sense_here(loc, random.Random(31 + i)))
            if i == 1:
                oid = self.right_of(g.state)
                if oid is not None:
                    with self.tweak(self.c.config, sense_rate_range=(100, 100), sense_marks_bonus=0), \
                            self.tweak(self.c.config.epiphany, chances=[1e-9] * 3):
                        emit(f"假人 {name} 選了做法", g.choose(oid))
            if i == 2 and god is not None:
                p.god_naming = GodNaming(line="頓悟1", god=god.id, attribute=god.attribute, lean=god.lean, place=loc.name)
            if i == 0:
                emit("整季機器人在有所感的卡上挑", bot.pick(g, g.options(odds=False), random.Random(0)))
            self.chars.save(g.state)
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        MODEL["sense"] = True
        totals = Counter()
        try:
            client = ollama_client.OllamaClient.from_config(self.c.config)
            runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0], client=client)
            self.c.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動
            server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
            for _ in range(int(os.environ.get("SB_SENSE_TICKS", "24"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                              named=report.named)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
            MODEL["sense"] = False
        emit("有所感假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"有所感假人 {name}", {
                "sensing": None if p.sensing is None else p.sensing.model_dump(mode="json"), "insights": list(p.insights),
                "own": {k: v.name for k, v in sorted(p.own_insights.items())},
                "god": None if p.god_naming is None else p.god_naming.model_dump(mode="json"),
                "journal": [e.title for e in s.journal[:4]], "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def season(self) -> None:
        """收季、開下一季：石觀潮又撞上一張卡沒了結、溫行簡的頓悟沒了結（此事未了）；換季之後有所感與頓悟的欄位跟著新角色重來。"""
        self.sensed("石觀潮")
        self.do(ADMIN, "end_season")
        for who in ("石觀潮", "溫行簡"):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in ("石觀潮", "溫行簡", "祁問山", "顧折柳", "蘇停雲"):
            self.main(who)
            self.me(who, "換季之後")


def _sense_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：「畫下來」只叫出畫布那一句（搬之前在 engine.py 的 choose、之後在 features/sense/actions.py）
_sense_register_track("sense", SenseScenario, (("tianxia/features/sense/actions.py", "tianxia/engine.py"),
                                                ("（在畫布上一筆畫下心中的形。）", "（在畫布上一筆畫下心中的形！）")), "week7")


# ═══════════════════════════ arts（全部拆包第 23 批「修練」，dev/arts-1）：arts 一軌 ═══════════════════════════
# 改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡三段式、傳功、配點、拜師學藝（learn:）搬進修練包（計畫
# docs/superpowers/plans/2026-11-01-修練包-第1批.md）。這一段整塊是這一批的：接在檔尾、最後兩行登記（_register_track、假人的 --seats arts），
# PM 合的時候不跟別人的行穿插。名號一律原創（PM 11/04）。

ARTS_LINE = "千招落盡，只剩你與那一腿，風聲都慢了下來。"  # 假模型寫的破境卡那一句：合格（八到四十字、沒有數字英文）、跟兩句套句都不一樣
_ARTS_CLIENTS: dict[type, type] = {}


def _arts_client(base: type) -> type:
    """破境卡那一句的假模型（base 是 _setup_child 那一層換好的 client 類別；同 _tavern_client）：LineReading 回 MODEL["ascend_line"] 那一句，
    其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _ARTS_CLIENTS:
        class ArtsClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "LineReading":
                    return schema(line=MODEL["ascend_line"])
                return super().chat_structured(messages, schema, *a, **k)

        _ARTS_CLIENTS[base] = ArtsClient
    return _ARTS_CLIENTS[base]


class ArtsScenario(Scenario):
    """修練（--track arts，自己一個資料庫）：修練頁的每一顆（/api/menxia/<op>、/api/do/allocate、/api/do/ascend_line）與 learn:。
    - 籌備中（管理者還沒開季）：修練頁的動作一律回「賽季籌備中」那一句（裝飾器 _not_while_preparing 搬進核心）。
    - 學藝（learn:）：書院那幾門灰著（書院弟子、俠名）、付不起灰著（按了被擋）、兩處各學一門、學過的不在選單上、再按一次被擋；
      改練（換上庫裡學來的那一門）、換回、沒有這一門。
    - 練成：心得不足、練到第十成（第一下受傷：機率在記憶體裡擺成 1）、練無可練、內功；裝意境（第一格空著時指定第二格、不指定格、沒有這個意境、沒有這門武學）、
      拆下、拆不在槽上的。
    - 熔煉：身上的熔不掉、庫裡沒有、熔庫裡學來的一門、熔一個意境、批量熔煉（一門武學與一個意境）；配點：沒有點、配兩點、沒有這一項、到頂。
    - 破境丹衝絕學：自創一門上品（三段式立意，模型擋著走關鍵字表）、還沒到極處、等契機、沒有丹、體力不足、下品的、沒有這門；
      敗的那一下（機會在記憶體裡壓到 1%：撞回來、下一次多一成），再服丹衝到衝開為止。
      **前半停在這裡**：破境卡寫好了、那一句還沒寫回（PlayerState.ascension.line 是空的）。同一刻另有一位等著定名的舊存檔（PlayerState.naming，
      手上的是自己自創、自己第一個練成的那一門）、一位手上有同一門的人、一位境界卡沒配完的人、一位走到裝意境那一步的序章新人。
    - 後半第一件事：新程式走破境卡三段式（A 開單、B 模型擋著走套句、C 存回）、再按一次（卡上已經有那一句）、收掉。
      接著定名（名字不行、被用掉、定成）與手上同一門的人下一次同步補一則（_deliver_renames）；序章新人接著練成、熔煉（序章的拒絕）；
      傳功給同伴與部下（心得不足、每一項、本人、名冊上沒有）；境界卡（屬性五段在記憶體裡打開：season21、week7）與配點那一句；
      絕學的契機（核心的單打服務 _seize：基礎武學擺成上品第十成，照原本的機會打五場、必中一場〔照舊一句升品〕；自創一門換上、必中一場
      〔破境卡、卡上那一句 via seize：假模型寫得好，線上正常走的那一條，C 段存回模型那一句〕）；追風步的舊品質讀檔時拿掉；最後每個人的修練頁。"""

    PRACTICE, PILL, NAMER, HOLDER, TEACHER, FIGHTER = "墨池", "寒江", "竹影", "松風", "石泉", "雲岫"
    PUPIL = "初學"
    PHASES_FIRST = ["setup", "learn", "switch", "practice", "slot", "melt", "allocate", "create", "pill", "pending", "hut_slot"]
    PHASES_SECOND = ["card", "resume", "naming", "renames", "hut_rest", "teach", "milestone", "seize", "zhuifeng", "pages"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("ascend_line") is not None:
                client.__class__ = _arts_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

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
        players = [self.PRACTICE, self.PILL, self.NAMER, self.HOLDER, self.TEACHER, self.FIGHTER, self.PUPIL]
        for who in players:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        # 籌備中（管理者還沒開季）：修練頁的動作一律擋（_not_while_preparing），定名的 A 段（假人用）也是 None
        who = self.PRACTICE
        self.mx(who, "practice", {"kind": "武學"})
        self.mx(who, "switch", {"art": "jichu_quanjiao"})
        self.mx(who, "slot", {"art": "jichu_quanjiao", "insight": "feng"})
        self.mx(who, "unslot", {"art": "jichu_quanjiao", "insight": "feng"})
        self.mx(who, "melt", {"art": "jichu_quanjiao"})
        self.mx(who, "melt_insight", {"insight": "feng"})
        self.mx(who, "melt_many", {"arts": ["jichu_quanjiao"], "insights": []})
        self.mx(who, "cultivate", {"art": "jichu_quanjiao", "use_legend": True})
        self.mx(who, "name", {"name": "籌備中的名"})
        self.mx(who, "chuangong", {"person": "nobody", "what": "str"})
        self.do(who, "allocate", {"stat": "str"})
        self.menxia(who)
        self.do(ADMIN, "open_season")
        for who in players[:-1]:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        factions = {f.id: f for f in self.c.scenario.factions}
        guan = factions.get("guan")
        if guan is not None and guan.join_at and self.place(self.FIGHTER, guan.join_at[0]):
            self.choose(self.FIGHTER, "faction:guan")
            self.choose(self.FIGHTER, "faction:confirm")
            self.settle_choices(self.FIGHTER)
        for who in players[:-1]:
            self.place(who, None)  # 體力補滿、過了新手期

    # ── 小工具 ──

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def menxia(self, who: str, person: str | None = None):
        return self.call(who, "GET", "/api/menxia" + (f"?person={person}" if person else ""))[1]

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟修練有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        m = p.member
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "wugong": [m.wugong_id, m.wugong_level], "neigong": [m.neigong_id, m.neigong_level], "level": m.level,
            "injury": m.injury, "neili": m.neili, "arts": list(p.arts), "art_levels": dict(sorted(p.art_levels.items())),
            "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())), "insights": list(p.insights),
            "stats": dict(sorted(p.stats.items())), "stat_points": p.stat_points, "milestone_due": p.milestone_due,
            "legend_items": p.legend_items, "legend_fails": dict(sorted(p.legend_fails.items())), "naming": p.naming,
            "renames_told": list(p.renames_told), "ascension": None if p.ascension is None else p.ascension.model_dump(),
            "follower_drill": [d.model_dump() for d in p.follower_drill], "stamina": p.stamina,
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def xinde(self, who: str, amount: int) -> None:
        self.edit(who, lambda p: p.stats.__setitem__("xinde", amount))

    def academy(self) -> str:
        return "lake" if self.profile == "test" else "yingchuan_academy"

    def base_insights(self) -> list[str]:
        """這份內容的基本意境（意境表的前幾個；測試內容另一套）。"""
        return sorted(self.c.insights)[:4]

    def worn(self, who: str) -> str | None:
        return self.chars.load(who).player.member.wugong_id

    def create_art(self, who: str, name: str) -> str | None:
        """自創一門武學（執器、擺式、立意〔三段式：模型擋著，照關鍵字表讀〕、立名）：回那一門的 id（不在手上是 None）。"""
        from tianxia import create

        self.xinde(who, 20000)
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.do(who, "create_intent", {"text": "風過林梢，影不留痕"})
        self.mx(who, "create_name", {"name": name, "move": ""})
        p = self.chars.load(who).player
        own = next((a for a in [p.member.wugong_id, *p.arts] if a and a not in self.c.skills), None)
        emit(f"{who} 自創的那一門", own)
        return own

    # ── 前半 ──

    def lesson_spots(self) -> list[str]:
        """學藝的地方：書院（只教書院弟子、要俠名的，散人都灰著）、潁水與樓桑村（散人學得了、要學費）；測試內容是湖邊。"""
        return ["lake"] if self.profile == "test" else [self.academy(), "yingshui", "loushang_village"]

    def learn(self) -> None:
        """拜師學藝（learn:，修練包的前綴）：書院那幾門灰著（書院弟子、俠名）；付不起灰著、按了被擋；學兩門（兩處各一門）；
        學過的不在選單上、再按一次被擋。"""
        who = self.PRACTICE
        for loc in self.lesson_spots():
            if not self.place(who, loc):
                continue
            self.edit(who, lambda p: p.stats.__setitem__("silver", 0))
            view = self.main(who)
            shown = {i: o for i, o in self.ids(view).items() if i.startswith("learn:")}
            emit(f"{loc} 學藝的鈕（沒錢）", shown)
            if shown:
                self.choose(who, next(iter(shown)))  # 灰著的照樣按（書院弟子、付不起）：被擋
            self.edit(who, lambda p: p.stats.__setitem__("silver", 2000))
            lessons = [i for i, o in self.ids(self.main(who)).items() if i.startswith("learn:") and o.get("enabled")]
            emit(f"{loc} 學藝的鈕", lessons)
            if lessons:
                self.choose(who, lessons[0])
                emit(f"{loc} 學過之後的鈕", [i for i in self.ids(self.main(who)) if i.startswith("learn:")])
                self.choose(who, lessons[0])  # 已經不在選單上：被擋
        self.state_of(who, "學藝之後")

    def switch(self) -> None:
        """改練：換上庫裡的一門、換回原本那一門、沒有這一門。"""
        who = self.PRACTICE
        p = self.chars.load(who).player
        before = p.member.wugong_id
        other = next((a for a in p.arts if a in self.c.skills and self.c.skills[a].kind == "武學"), None)
        if other is not None:
            self.mx(who, "switch", {"art": other})
            if before is not None:
                self.mx(who, "switch", {"art": before})
        self.mx(who, "switch", {"art": "沒有這門"})
        self.state_of(who, "改練之後")

    def practice(self) -> None:
        """練成：心得不足、一路練到第十成（受傷照擲；第一下受傷的機率在記憶體裡擺成 1，兩份程式同一套）、練無可練、內功兩成。"""
        who = self.PRACTICE
        self.xinde(who, 0)
        self.mx(who, "practice", {"kind": "武學"})
        self.xinde(who, 5000)
        cfg = self.c.config
        before, cfg.practice_injury_chance = cfg.practice_injury_chance, 1.0
        try:
            self.mx(who, "practice", {"kind": "武學"})  # 這一番苦練傷了氣血
        finally:
            cfg.practice_injury_chance = before
        for _ in range(9):
            self.mx(who, "practice", {"kind": "武學"})
        for _ in range(2):
            self.mx(who, "practice", {"kind": "內功"})
        self.state_of(who, "練成之後")

    def slot(self) -> None:
        """意境裝卸：指定格（第一格空著時指定第二格：不給 index 會落到第一格，才分得出 index 有沒有傳到底；審查補的，網頁每一次裝都帶 index）、
        不指定格（挑空的那一格）、沒有這個意境、沒有這門武學；拆下、拆不在槽上的。"""
        who = self.PRACTICE
        ins = self.base_insights()
        self.edit(who, lambda p: p.insights.extend(i for i in ins if i not in p.insights))
        art = self.worn(who) or ""
        if len(ins) > 1:
            self.mx(who, "slot", {"art": art, "insight": ins[1], "index": 1})
            emit("指定第二格之後的槽", self.chars.load(who).player.art_slots.get(art))
        if ins:
            self.mx(who, "slot", {"art": art, "insight": ins[0]})
        self.mx(who, "slot", {"art": art, "insight": "沒有這個意境"})
        if ins:
            self.mx(who, "slot", {"art": "沒有這門", "insight": ins[0]})
            self.mx(who, "unslot", {"art": art, "insight": ins[0]})
            self.mx(who, "unslot", {"art": art, "insight": ins[0]})  # 已經不在槽上
        self.state_of(who, "裝卸意境之後")

    def melt(self) -> None:
        """熔煉：身上的熔不掉、庫裡沒有、熔一門、熔一個意境、批量熔煉（武學與意境一起）。"""
        who = self.PRACTICE
        p = self.chars.load(who).player
        self.mx(who, "melt", {"art": p.member.wugong_id or ""})
        self.mx(who, "melt", {"art": "沒有這門"})
        library = [a for a in p.arts]
        if library:
            self.mx(who, "melt", {"art": library[0]})
        p = self.chars.load(who).player
        loose = [i for i in p.insights if not any(i in (slots or []) for slots in p.art_slots.values())]
        if loose:
            self.mx(who, "melt_insight", {"insight": loose[0]})
        p = self.chars.load(who).player
        loose = [i for i in p.insights if not any(i in (slots or []) for slots in p.art_slots.values())]
        self.mx(who, "melt_many", {"arts": list(p.arts), "insights": loose[:1]})
        self.mx(who, "melt_many", {"arts": "不是串列", "insights": []})
        self.state_of(who, "熔煉之後")

    def allocate(self) -> None:
        """配點：沒有點、配兩點、沒有這一項、到頂。"""
        who = self.PRACTICE
        self.edit(who, lambda p: setattr(p, "stat_points", 0))
        self.do(who, "allocate", {"stat": "str"})
        self.edit(who, lambda p: setattr(p, "stat_points", 3))
        self.do(who, "allocate", {"stat": "str"})
        self.do(who, "allocate", {"stat": "str"})
        self.do(who, "allocate", {"stat": "沒有這項"})
        self.edit(who, lambda p: p.stats.__setitem__("agi", self.c.config.stat_cap))
        self.do(who, "allocate", {"stat": "agi"})
        self.state_of(who, "配點之後")

    def create(self) -> None:
        """寒江自創一門（上品），換上身。"""
        who = self.PILL
        own = self.create_art(who, "寒江掌")
        if own is not None and own in self.chars.load(who).player.arts:
            self.mx(who, "switch", {"art": own})
        self.state_of(who, "自創之後")

    def pill(self) -> None:
        """破境丹衝絕學：拒絕的幾種，再服丹衝到衝開為止。前半停在破境卡寫好、那一句還沒寫回。"""
        who = self.PILL
        own = self.worn(who)
        if own is None:
            return
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 還沒到極處（第一成）
        self.edit(who, lambda p: setattr(p.member, "wugong_level", 10))
        self.mx(who, "cultivate", {"art": own})  # 沒勾服丹：等契機那一句
        self.edit(who, lambda p: setattr(p, "legend_items", 0))
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 沒有丹
        self.edit(who, lambda p: (setattr(p, "legend_items", 1), setattr(p, "stamina", 1.0)))
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 體力不足
        neigong = self.chars.load(who).player.member.neigong_id
        if neigong is not None:
            self.mx(who, "cultivate", {"art": neigong, "use_legend": True})  # 下品：品級不靠修練
        self.mx(who, "cultivate", {"art": "沒有這門", "use_legend": True})
        self.edit(who, lambda p: setattr(p, "legend_items", 12))
        cfg = self.c.config
        before, cfg.legend_item_bonus = cfg.legend_item_bonus, 0  # 敗的那一下：機會在記憶體裡壓到 1%（兩份程式同一套），撞回來、下一次多一成
        try:
            self.place(who, None)
            self.mx(who, "cultivate", {"art": own, "use_legend": True})
        finally:
            cfg.legend_item_bonus = before
        for _ in range(12):
            self.place(who, None)
            self.mx(who, "cultivate", {"art": own, "use_legend": True})
            if self.chars.load(who).player.ascension is not None:
                break
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 已經是絕學
        self.state_of(who, "服丹衝關之後")
        emit("破境卡（那一句還沒寫）", (self.main(who).get("status") or {}).get("ascension"))

    def pending(self) -> None:
        """寫到一半的另外三種：等著定名的舊存檔（竹影自創的那一門、自己第一個練成；松風手上也有同一門）、境界卡沒配完的人（石泉）。"""
        own = self.create_art(self.NAMER, "竹影拳")
        if own is not None:
            self.world.claim_master(own, self.NAMER)
            self.edit(self.NAMER, lambda p: setattr(p, "naming", own))
            self.edit(self.HOLDER, lambda p: p.arts.append(own))
            self.menxia(self.NAMER)
        self.edit(self.TEACHER, lambda p: (setattr(p, "stat_points", 2), setattr(p, "milestone_due", 20)))
        for who in (self.NAMER, self.HOLDER, self.TEACHER):
            self.state_of(who, "前半最後")

    def hut_slot(self) -> None:
        """序章新人走到裝意境那一步（同 Scenario.prologue 的前幾步）；沒有序章的季什麼都不做。"""
        from tianxia import sensing

        who = self.PUPIL
        view = self.main(who)
        if not view.get("prologue"):
            emit(f"{who}：這一季沒有序章", None)
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
            self.mx(who, "slot", {"art": "jichu_tuna", "insight": got[0]})  # 序章只准裝師父點名的那一門
            self.mx(who, "slot", {"art": "jichu_quanjiao", "insight": got[0]})
        self.menxia(who)
        self.state_of(who, "序章裝意境之後")

    # ── 後半 ──

    def card(self) -> None:
        """後半第一件事：新程式接著寫破境卡那一句（三段式：A 開單、B 模型擋著走套句、C 存回）；再按一次；收掉。"""
        who = self.PILL
        self.relogin(who)
        emit("破境卡（後半拿到的）", (self.main(who).get("status") or {}).get("ascension"))
        self.do(who, "ascend_line")
        emit("破境卡（寫回之後）", (self.main(who).get("status") or {}).get("ascension"))
        self.do(who, "ascend_line")  # 已經寫過：A 段不開單
        self.mx(who, "ascend_dismiss")
        self.state_of(who, "破境卡收掉之後")

    def resume(self) -> None:
        self.login_all()

    def naming(self) -> None:
        """舊存檔等著定名：名字不行、被用掉、定成。"""
        who = self.NAMER
        self.menxia(who)
        self.mx(who, "name", {"name": ""})
        self.mx(who, "name", {"name": "寒江掌"})
        self.mx(who, "name", {"name": "竹影神拳"})
        self.mx(who, "name", {"name": "再定一次"})  # 已經定過了
        self.state_of(who, "定名之後")

    def renames(self) -> None:
        """手上有同一門的人下一次同步補一則（_deliver_renames）；再同步一次不重複。定名的人自己不補。"""
        self.main(self.HOLDER)
        self.state_of(self.HOLDER, "定名之後同步")
        self.main(self.HOLDER)
        self.main(self.NAMER)
        self.state_of(self.NAMER, "自己定的名同步之後")

    def hut_rest(self) -> None:
        """序章新人（前半停在裝意境那一步）接著練成、熔煉：序章的拒絕（別的一欄、批量熔煉、熔意境）。"""
        who = self.PUPIL
        if not self.main(who).get("prologue"):
            return
        self.menxia(who)
        self.mx(who, "practice", {"kind": "內功"})
        self.mx(who, "practice", {"kind": "武學"})
        self.mx(who, "practice", {"kind": "武學"})
        p = self.chars.load(who).player
        self.mx(who, "melt_many", {"arts": list(p.arts), "insights": list(p.insights)})
        if p.insights:
            self.mx(who, "melt_insight", {"insight": p.insights[0]})
            self.mx(who, "unslot", {"art": "jichu_quanjiao", "insight": p.insights[0]})
        self.mx(who, "melt", {"art": "jichu_tuna"})
        self.state_of(who, "序章練成、熔煉之後")

    def teach(self) -> None:
        """傳功：同伴（練武學、內功、三項屬性、不傳的一項）、部下（第一季規則的季：多練一成、臂力）、心得不足、本人、名冊上沒有。"""
        who = self.TEACHER
        mate = sorted(self.c.characters)[0]
        skills = [sid for sid, s in sorted(self.c.skills.items()) if s.quality == "下品"]
        self.world.try_recruit(mate, who)
        if skills:
            self.world.update_companion(mate, lambda pr: (setattr(pr, "wugong_id", skills[0]), setattr(pr, "neigong_id", skills[-1])))
        if self.c.followers:
            first = sorted(self.c.followers)[0]
            self.edit(who, lambda p: setattr(p, "followers", [first]))
        self.xinde(who, 0)
        self.menxia(who, mate)
        self.mx(who, "chuangong", {"person": mate, "what": "wugong"})
        self.xinde(who, 20000)
        for what in ("wugong", "neigong", "str", "agi", "con", "wis"):
            self.mx(who, "chuangong", {"person": mate, "what": what})
        self.menxia(who, "follower:0")
        for what in ("wugong", "str"):
            self.mx(who, "chuangong", {"person": "follower:0", "what": what})
        self.mx(who, "chuangong", {"person": "player", "what": "str"})
        self.mx(who, "chuangong", {"person": "沒有這個人", "what": "str"})
        emit("同伴的進度", self.world.get_companion(mate).model_dump())
        self.state_of(who, "傳功之後")

    @contextlib.contextmanager
    def milestones_on(self):
        """減法季屬性五段：兩種現役設定（season21、week7）都關著，在記憶體裡打開（兩份程式同一套），做完擺回來。"""
        jf = getattr(self.c.config, "jianfa", None)
        before = getattr(jf, "stat_milestones", None)
        if jf is not None and self.profile in DUEL_PROFILES:
            jf.stat_milestones = True
        try:
            yield
        finally:
            if jf is not None:
                jf.stat_milestones = before

    def milestone(self) -> None:
        """境界卡（減法季屬性五段，milestones_on）：卡、配兩點（配點那一句）、配完收卡。"""
        who = self.TEACHER
        with self.milestones_on():
            emit("境界卡", self.main(who).get("milestone"))
            self.do(who, "allocate", {"stat": "str"})
            emit("境界卡（配了一點）", self.main(who).get("milestone"))
            self.do(who, "allocate", {"stat": "con"})
            emit("境界卡（配完）", self.main(who).get("milestone"))
        self.state_of(who, "境界卡之後")

    def seize(self) -> None:
        """絕學的契機（核心的單打服務 _seize → 修練包）：身上那一門（基礎武學）擺成上品第十成，照寫好的打贏幾場；出陣開著的季在
        汝南荒野出陣，關著的在長社遊歷。再自創一門換上、擺到第十成，打一場必中的：自創的那一門破境（破境卡、江湖史、傳聞），
        卡上那一句走三段式，模型寫得好（假模型；後半第一件事的寒江那一張走模型擋著的套句，只走那一條的話 C 段把模型的句子丟掉也看不出來）。"""
        from tianxia import territory

        who = self.FIGHTER
        p = self.chars.load(who).player
        art = p.member.wugong_id
        if art is None:
            art = next((sid for sid, s in sorted(self.c.skills.items()) if s.quality == "下品" and s.kind == "武學"), None)
            self.edit(who, lambda pl: setattr(pl.member, "wugong_id", art))
        self.edit(who, lambda pl: (pl.art_quality.__setitem__(art, "上品"), setattr(pl.member, "wugong_level", 10)))
        loc = "runan_wilds" if territory.on(self.c) else ("lake" if self.profile == "test" else "changshe")
        self.set_duel(False)  # 約戰開著的季按出陣只打開那張卡（不打）：契機要的是真的打一場（同出陣一軌的攻）
        try:
            self.seize_fights(who, loc, 5)  # 照原本的機會擲（難度比夠的季摸到了又滑走；none、test 的對手太弱，不到 min_ratio 不擲）
            self.seize_sure(who, loc)  # 基礎武學（不是自創的）：照舊一句升品，沒有破境卡
            own = self.create_art(who, "雲岫腿")
            if own is not None and own in self.chars.load(who).player.arts:
                self.mx(who, "switch", {"art": own})
                self.edit(who, lambda pl: setattr(pl.member, "wugong_level", 10))
                self.seize_sure(who, loc)  # 自創的那一門：破境
        finally:
            self.set_duel(True)
        self.state_of(who, "契機之後")
        emit("契機的破境卡", (self.main(who).get("status") or {}).get("ascension"))
        MODEL["ascend_line"] = ARTS_LINE
        try:
            self.do(who, "ascend_line")
        finally:
            MODEL["ascend_line"] = None
        emit("契機的破境卡（寫回之後）", (self.main(who).get("status") or {}).get("ascension"))
        with self.milestones_on():  # 單點突變補的（Task 5）：打過幾場、威力夠大，配點那一句才寫全隊前後；身法不動威力、不寫那一段
            self.do(who, "allocate", {"stat": "str"})
            self.do(who, "allocate", {"stat": "agi"})
        self.state_of(who, "契機之後配點")

    def seize_sure(self, who: str, loc: str) -> None:
        """打一場必中的契機：機會在記憶體裡擺成必中、難度比不設門檻（兩份程式同一套），做完擺回來。"""
        rule = self.c.config.breakthrough
        before = rule.chance, rule.max_chance, rule.min_ratio
        rule.chance, rule.max_chance, rule.min_ratio = 10 ** 6, 100, 0.0
        try:
            self.seize_fights(who, loc, 1)
        finally:
            rule.chance, rule.max_chance, rule.min_ratio = before

    def seize_fights(self, who: str, loc: str, times: int) -> None:
        for i in range(times):
            if not self.place(who, loc):
                return
            self.edit(who, lambda pl: setattr(pl, "sorties_today", 0))
            option = self.ids(self.main(who)).get("act:train")
            emit(f"契機的 act:train（第 {i + 1} 場）", option)
            if not option or not option.get("enabled"):
                break
            with self.winning():
                self.choose(who, "act:train")
            self.settle_choices(who)
            state = self.chars.load(who)
            record = state.battles[0] if state.battles else None
            emit(f"契機那一場（第 {i + 1} 場）", None if record is None else {
                "tier": record.tier, "difficulty": record.difficulty, "our_power": record.our_power, "notes": record.notes})

    def zhuifeng(self) -> None:
        """追風步的舊品質（中間一版寫成了絕學）：讀檔時拿掉（_drop_stale_references → _drop_old_zhuifeng），按一下存回去。
        手上要真的有追風步（單點突變補的，Task 5）：不在手上的那一門，品質讀檔時本來就照「手上有的」清掉，拿不拿掉看不出來。"""
        who = self.PRACTICE

        def fn(p) -> None:
            if "zhuifeng" not in p.arts:
                p.arts.append("zhuifeng")
            p.art_quality["zhuifeng"] = "絕學"

        self.edit(who, fn)
        self.mx(who, "ascend_dismiss")
        p = self.chars.load(who).player
        emit("追風步的品質", {"held": "zhuifeng" in p.arts, "quality": p.art_quality.get("zhuifeng")})

    def pages(self) -> None:
        """每個人最後的修練頁（唯讀那十一個：名冊、功法卡、背包、持有數、功法庫、意境、等著定名的、傳功鈕……）與江湖畫面。"""
        for who in (self.PRACTICE, self.PILL, self.NAMER, self.HOLDER, self.TEACHER, self.FIGHTER, self.PUPIL):
            self.menxia(who)
            self.main(who)


# 假人：none（舊遊歷、沒有第一季規則）、weekend（序章、部下）、week7（減法季）。測試內容的 BotRunner 一個都不上線（acted 0），不跑
ARTS_BOT_PROFILES = ("week7",)
ARTS_SEATS = [("硯甲", "yingchuan_academy"), ("硯乙", "yingchuan"), ("硯丙", "yingchuan"), ("硯丁", "yingchuan")]


def arts_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """修練的假人（--seats arts）：整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）與伺服器假人（BotRunner＋bot_policy.take_turn，
    random.Random(7)、假時鐘、每一輪 +300 秒）四個跑 N 輪——硯甲在潁川書院（學藝：銀兩夠、庫有空）、硯乙身上一門上品第十成、手上有破境丹
    （tend_arts 的服丹衝關）、硯丙自創一門、自己第一個練成、等著定名（絕學定名的 A 段 mastery_request → 假人程式的 B 段〔模型擋著〕→ C 段字表另組）、
    硯丁心得多、名下一位同伴、手上有屬性點（傳功門下、配點）。寫存檔、修練那幾種紀錄的則數、名下同伴的進度、資料庫的雜湊。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot, create
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.ollama_client import OllamaClient
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def content_of():
        return load_content(root / "content", profile=None if profile == "none" else profile)

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title.partition("・")[0] for s in states for e in s.journal).items()))

    def arts_of(state) -> dict:
        p = state.player
        return {"wugong": [p.member.wugong_id, p.member.wugong_level], "neigong": [p.member.neigong_id, p.member.neigong_level],
                "arts": list(p.arts), "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())),
                "stats": dict(sorted(p.stats.items())), "stat_points": p.stat_points, "legend_items": p.legend_items,
                "legend_fails": dict(sorted(p.legend_fails.items())), "naming": p.naming,
                "ascension": None if p.ascension is None else p.ascension.model_dump()}

    content = content_of()
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("修練整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("修練整季機器人 紀錄標題", titles([game.state]))
    emit("修練整季機器人 武學", arts_of(game.state))
    emit("修練整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = content_of()
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    mate = sorted(content.characters)[0]
    for i, (name, loc) in enumerate(ARTS_SEATS):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=41 + i, faction=None, season_number=world.get_season_number())
        p.location, p.journey = loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        if name == "硯甲":
            p.stats["silver"] = 2000
        elif name == "硯乙":
            art = p.member.wugong_id
            if art is not None:
                p.art_quality[art] = "上品"
                p.member.wugong_level = 10
            p.legend_items = 6
        elif name == "硯丙":
            p.stats["xinde"] = 20000
            g.create_begin("武學", "拳腳")
            g.create_pose(create.preset(content, "進擊"))
            g.create_intent("流水不爭先，爭的是滔滔不絕")
            g.create_name("硯丙掌")
            own = next((a for a in [p.member.wugong_id, *p.arts] if a and a not in content.skills), None)
            if own is not None:
                world.claim_master(own, name)
                p.naming = own
        elif name == "硯丁":
            p.stats["xinde"] = 20000
            p.stat_points = 3
            world.try_recruit(mate, name)
        chars.save(g.state)
    clock = [CLOCK0]
    # 假人程式照 run_bots 帶一個 client（_setup_child 換成叫不動的那一個）：絕學定名的 B 段請模型、模型擋著，C 段照字表另組（bot_policy.apply_job）
    client = OllamaClient.from_config(content.config) if content.config.bot_naming else None
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0], client=client)
    totals = Counter()
    for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                      named=report.named)
    states = chars.all(bots_only=True)
    emit("修練假人 一輪一輪", dict(sorted(totals.items())))
    emit("修練假人 紀錄標題", titles(states))
    emit("修練假人 武學", {s.player.name: arts_of(s) for s in states})
    emit("修練假人 名下的同伴", world.get_companion(mate).model_dump())
    emit("修練假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("修練假人 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "修練假人", dict(totals), titles(states))


_arts_bot_runs = _bot_runs


def _bot_runs(tracks: list[str]) -> list[tuple[str, str]]:  # noqa: F811  （arts 第 23 批：arts 那一軌的假人接在後面）
    return _arts_bot_runs(tracks) + ([("arts", p) for p in ARTS_BOT_PROFILES] if "arts" in tracks else [])


def _arts_entry(main_fn):
    """bots ... --seats arts（這一軌的假人）；其餘照原本的 main（一個字不動）。"""

    def entry(argv: list[str] | None = None) -> int:
        args = list(sys.argv[1:] if argv is None else argv)
        if args[:1] == ["bots"] and "--seats" in args and args[args.index("--seats") + 1:args.index("--seats") + 2] == ["arts"]:
            ap = argparse.ArgumentParser()
            ap.add_argument("cmd")
            ap.add_argument("root")
            ap.add_argument("profile", choices=PROFILES)
            ap.add_argument("out")
            ap.add_argument("--tmp", required=True)
            ap.add_argument("--seats")
            a = ap.parse_args(args)
            arts_bots_run(Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
            sys.stdout.flush()
            os._exit(0)
        return main_fn(argv)

    return entry


main = _arts_entry(main)
# 改一個字（selftest）：配點沒有點那一句（搬之前在 engine.py 的 allocate_stat、之後在 features/cultivation/actions.py），week7 墨池配點那一下抓到
_register_track("arts", ArtsScenario, (("tianxia/features/cultivation/actions.py", "tianxia/engine.py"),
                                       ("沒有可以分配的屬性點，升級才會有。", "沒有可以分配的屬性點，升級才會有！")), "week7")


# ═══════════════════════════ talk：人物對話二軌（全部拆包第 20 批，dev/companions-2） ═══════════════════════════
# 人物對話（鎖外三段式 A、B、C：dialogue_request／prepare_dialogue／choose 的重驗）、NPC 智能 2.0（開口求人、開條件、先做後付與食言、
# 他主動開口求你、帶路、陪你出陣與商量打法）的本體從 engine.py 與 tianxia/companion_agent.py、parley.py 搬進 tianxia/features/companions/
# （舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記
# （_talk_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（第 22 批 PM 認定第 3 條）。

TALK_REPLY = "他沉吟了一會，緩緩開口。"
TALK_TERMS = "他想了想：「這事不難，只是你得先拿出一點誠意。」"
TALK_NO = "他搖了搖頭：「這件事，恕我難以從命。」"
TALK_PLAN_NO = "他皺起眉頭：「這個打法行不通。」"
_TALK_CLIENTS: dict[type, type] = {}


def _talk_block(text: str, head: str) -> list[tuple[str, int]]:
    """提示裡「【…head】」底下的一串「- id：說明（份量 N）」→ [(id, 份量)]。"""
    i = text.find(head)
    if i < 0:
        return []
    rows = []
    for line in text[i + len(head):].split("\n")[1:]:
        if not line.startswith("- "):
            break
        ident, _, rest = line[2:].partition("：")
        weight = rest.rsplit("份量 ", 1)[-1].rstrip("）") if "份量" in rest else "0"
        rows.append((ident, int(weight) if weight.isdigit() else 0))
    return rows


def _talk_pick(spec: str, rows: list[tuple[str, int]]) -> str:
    """MODEL["parley"] 裡的 id：寫 'escort:*' 這種星號結尾的取清單上第一個對得上的，其餘照字面（寫清單外的 id 也是一種測法）。"""
    if spec.endswith("*"):
        return next((ident for ident, _ in rows if ident.startswith(spec[:-1])), "")
    return spec


def _talk_client(base: type) -> type:
    """人物對話二軌的假模型（疊在 _companions_client 上）：MODEL["parley"] 給了（{ask、willing、condition、narrative_terms、narrative_no、want、reward…}）
    時，那一輪 CompanionTurn 的 NPC 智能 2.0 欄位換成它；ask、condition、want 的 id 可以寫 'escort:*' 這種星號結尾（照提示裡的清單取第一個）。"""
    if base not in _TALK_CLIENTS:
        class TalkClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                got = super().chat_structured(messages, schema, *a, **k)
                spec = MODEL.get("parley")
                if spec is None or not hasattr(got, "ask"):
                    return got
                text = messages[-1]["content"]
                asks, conds = _talk_block(text, "此刻做得到的事】"), _talk_block(text, "可以開的條件】")
                wants, rewards = _talk_block(text, "想請玩家做的事】"), _talk_block(text, "可以回報的事】")
                update: dict = {}
                for key, value in spec.items():
                    if key == "ask":
                        update[key] = _talk_pick(value, asks)
                    elif key == "condition":
                        update[key] = _talk_pick(value, conds)
                    elif key == "want":
                        update[key] = _talk_pick(value, wants)
                    elif key == "reward":  # 'fit'：第一個份量不比請託大的回報
                        weight = dict(wants).get(update.get("want", ""), 0)
                        update[key] = next((ident for ident, w in rewards if w <= weight), "") if value == "fit" else value
                    else:
                        update[key] = value
                return got.model_copy(update=update)

        _TALK_CLIENTS[base] = TalkClient
    return _TALK_CLIENTS[base]


class TalkScenario(CompanionsScenario):
    """人物對話（全部拆包第 20 批；--track talk，自己一個資料庫）。
    沈鶴年在談盧植（直接擺成上一輪給了選項）：選選項、自己說，**前半停在還在談**。顧映雪模型叫不動：選選項、自己說都結束對話（「無心多談」）。
    葉知秋求見（call:）開口兩種（模型回了、模型叫不動退回體力），交友（act:socialize）一次（在只有秦頡一位的宛城：盧植營兩位以上、交友是名單，不開口）。
    言半山求「指點一招」、模型開條件（交銀）：**前半停在條件還沒答覆**（接、不接兩顆）。後半：接了（交銀、當場做）。
    紀行雲：照擲出來的結果一件一件求（指點、說說敵情、贈物當場做；婉拒；開條件不接；開條件接了打探掛成委託；欠他的那一件請他兌現）。
    燕回聲求贈物、先做後付（模型開條件、擲中）：**前半停在約定還欠著**；後半還他。霍斷橋同一件，後半過了期限（食言：情誼扣、那幾句併進書信）。
    路修遠求帶路（動身，一路不花體力）：**前半停在帶路的路上**；後半每到一站跟他說一句（parley:road）。衛承光求陪你出陣：**前半停在答應了**；
    後半商量打法（talk:plan）、在盧植那一帶（冀州）出陣。葉聽雪交友焦慮的秦頡（他主動開口求你）：**前半停在他開的請託還沒答覆**；後半接下，再去黃巾的投靠點叛投（欠著的都算食言）。冷千山是黃巾，求官軍的盧植（敵對）。
    假人（BotRunner 十輪；bot_policy.score 問 talk:、parley: 的各幾顆）；換季。這份內容沒有盧植的設定用第一位人物，同一串 API 照打。"""

    TALKER, BLOCKED, OPENER, ASKER, DOER = "沈鶴年", "顧映雪", "葉知秋", "言半山", "紀行雲"
    PAYER, LATE, WALKER, BACKER, PLEADER, FOE = "燕回聲", "霍斷橋", "路修遠", "衛承光", "葉聽雪", "冷千山"
    BACKER2 = "宗政遠"
    PLAYERS = {TALKER: "guan", BLOCKED: "guan", OPENER: "guan", ASKER: "guan", DOER: "guan", PAYER: "guan", LATE: "guan", WALKER: "guan",
               BACKER: "guan", BACKER2: "guan", PLEADER: "guan", FOE: "huang"}
    PLEAD_FIG = "qinjie"
    PHASES_FIRST = ["setup", "seat", "opening", "plain", "terms_open", "owe_open", "road_open", "backing_open", "plea_open", "half"]
    PHASES_SECOND = ["resume", "plain_on", "terms_on", "doer", "owe_on", "road_on", "backing_on", "plea_on", "forsake", "foe", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # 上一層（人物情誼一軌的假模型）換好的那一層

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _talk_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    @property
    def fig(self) -> str | None:
        if self.LUZHI in self.c.characters:
            return self.LUZHI
        return sorted(self.c.characters)[0] if self.c.characters else None

    @contextlib.contextmanager
    def parley_on(self, **values):
        """NPC 智能 2.0 開著（正式內容本來就開；測試內容關著，這一下打開）、一天最多求九件、一天最多聊九輪，再加這幾個值（擲骰的 floor 等）。"""
        parley = self.c.config.parley
        with self.tuned(parley, enabled=True, asks_per_day=9, **values), self.tuned(self.c.config, talk_turns_per_day=9):
            yield

    def stand(self, who: str, cid: str | None = None) -> None:
        cid = cid or self.fig
        try:
            self.beside(who, cid)
        except Exception as e:  # noqa: BLE001  （測試內容的人物沒有住處）
            emit(f"{who} 站不到 {cid}", type(e).__name__)
            self.place(who, None)

    def talking(self, who: str, cid: str | None = None, affinity: int = 45) -> None:
        """直接擺成「正在跟他談、上一輪給了選項」（tests/kit/stances_kit.talking 同一個擺法），今天談過的輪數清掉。"""
        cid = cid or self.fig

        def fn(p) -> None:
            p.pending_companion = cid
            p.last_offered_dialogue[cid] = [["勸他速攻", "勸他持重", "告辭"], ["真誠請教", "坦誠相待", "尋常寒暄"]]
            p.affinities[cid] = affinity
            p.talks_today.pop(cid, None)

        self.edit(who, fn)

    def open_call(self, who: str, cid: str | None = None) -> None:
        """求見：站到他那裡、名望夠、打開求見的名單、按他的名字。"""
        cid = cid or self.fig
        self.stand(who, cid)

        def fn(p) -> None:
            p.stats["fame"] = 9999
            p.picking_audience = True

        self.edit(who, fn)
        self.choose(who, f"call:{cid}")

    def open_social(self, who: str, cid: str) -> None:
        """交友（act:socialize）：站到他那裡、按交友。只有他一位的地點才直接開口（兩位以上的地點交友是名單，按的是 call:，那一條走 open_call）。"""
        self.stand(who, cid)
        self.edit(who, lambda p: p.stats.update({"fame": 9999}))  # 名望夠才見得到（同 open_call）
        emit("交友那一顆", self.buttons(who, "act:socialize"))
        view = self.choose(who, "act:socialize")
        if any(i.startswith("choice:") for i in self.ids(view)):  # 先碰上一件留在交友的事（福緣之類）：了結它，再按一次
            self.settle_choices(who)
            self.choose(who, "act:socialize")

    def you(self, who: str, tag: str) -> None:
        """存檔裡對話與 NPC 智能 2.0 碰得到的格子：談話對象與上一輪的選項、情誼、今天聊了幾輪、開的條件、欠的、欠你的、今天求了什麼、守約紀錄、陪你出陣、
        帶路的路、體力銀兩心得、書信、行狀與最新兩則紀錄、對話記錄的尾巴。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "pending": p.pending_companion, "offered": p.last_offered_dialogue, "affinities": dict(sorted(p.affinities.items())),
            "talks_today": dict(sorted(p.talks_today.items())), "terms": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_terms.items())},
            "debts": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_debts.items())}, "owed": dict(sorted(p.parley_owed.items())),
            "days": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_days.items())},
            "records": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_records.items())},
            "backing": p.parley_backing.model_dump(mode="json") if p.parley_backing is not None else None,
            "escort": [p.parley_escort, p.parley_road_leg], "journey": p.journey.model_dump(mode="json") if p.journey is not None else None,
            "location": p.location, "stamina": p.stamina, "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0),
            "materials": dict(sorted(p.materials.items())) if hasattr(p, "materials") else None,
            "letters": [x.model_dump(mode="json") for x in p.letters], "annals": [[a.kind, a.text, a.figure] for a in p.annals],
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]],
            "memos": {k: v.model_dump(mode="json") for k, v in sorted(p.talk_memos.items())},
            "history": {k: v[-2:] for k, v in sorted(p.dialogue_history.items())}, "stance_notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())}})

    def say(self, who: str, text: str, option: str = "talk:say") -> None:
        self.call(who, "POST", "/api/say", {"text": text, "option": option})

    def ask(self, who: str, text: str, tag: str, spec: dict | None, option: str = "talk:say", **tuning) -> None:
        """說一句話，模型的 NPC 智能 2.0 欄位是 spec（None 就是閒聊）；tuning 是這一下擲骰的設定（floor=100 一定中、floor=0 且 willing 0 一定不中）。"""
        MODEL["talk"], MODEL["parley"] = {"stance": "suzhan"}, spec
        try:
            with self.parley_on(**tuning):
                self.say(who, text, option)
        finally:
            MODEL["talk"] = MODEL["parley"] = None
        self.you(who, tag)

    # ── 前半 ──

    def opening(self) -> None:
        """求見開口兩種、交友一次：模型回了（對話開始、選項三顆）、模型叫不動（退回體力、「無心多談」）。"""
        cid = self.fig
        if cid is None:
            emit("這份內容沒有人物", None)
            return
        MODEL["talk"] = None
        self.open_call(self.BLOCKED, cid)
        self.you(self.BLOCKED, "求見、模型叫不動")
        MODEL["talk"] = {"stance": "suzhan"}
        self.open_call(self.OPENER, cid)
        self.you(self.OPENER, "求見、模型回了")
        emit("談話的選單", sorted(self.ids(self.main(self.OPENER))))
        self.choose(self.OPENER, "talk:leave")
        self.edit(self.OPENER, lambda p: setattr(p, "talks_today", {}))
        alone = self.PLEAD_FIG if self.PLEAD_FIG in self.c.characters else cid  # 宛城只有秦頡一位：交友直接開口（盧植營兩位以上、是求見名單）
        self.open_social(self.OPENER, alone)
        self.you(self.OPENER, "交友")
        self.choose(self.OPENER, "talk:leave")
        MODEL["talk"] = None

    def plain(self) -> None:
        """沈鶴年選選項、自己說（前半停在還在談）；顧映雪模型叫不動：選選項、自己說都結束對話。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.TALKER, cid)
        self.talking(self.TALKER, cid)
        MODEL["talk"] = {"stance": "suzhan"}
        view = self.main(self.TALKER)
        emit("談話中的人物頁（main.figure）與選單", [view.get("figure") if isinstance(view, dict) else None, sorted(self.ids(view))])
        with self.tuned(self.c.config, talk_turns_per_day=9):
            self.choose(self.TALKER, "talk:0")
            self.you(self.TALKER, "選了第一顆")
            self.say(self.TALKER, "願聞其詳")
        self.you(self.TALKER, "自己說了一句（停在還在談）")
        MODEL["talk"] = None
        for who, how in ((self.BLOCKED, "選項"), (self.BLOCKED, "自己說")):
            self.stand(who, cid)
            self.talking(who, cid)
            if how == "選項":
                self.choose(who, "talk:0")
            else:
                self.say(who, "請問近況如何")
            self.you(who, f"模型叫不動、{how}")
        self.call(self.BLOCKED, "POST", "/api/say", {"text": "x" * 80})  # 太長
        self.call(self.BLOCKED, "POST", "/api/say", {"text": "沒有談話對象"})

    def terms_open(self) -> None:
        """言半山求指點一招、模型開條件（交銀）、擲不中：條件還沒答覆（前半停在接、不接兩顆）。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.ASKER, cid)
        self.talking(self.ASKER, cid)
        self.ask(self.ASKER, "請你指點我一招", "開了條件", {"ask": "spar", "willing": 0, "condition": "silver", "narrative_terms": TALK_TERMS,
                                                        "narrative_no": TALK_NO}, floor=0)
        emit("接、不接兩顆", self.buttons(self.ASKER, "talk:terms"))

    def owe_open(self) -> None:
        """燕回聲、霍斷橋求贈物、模型開條件（交銀）、擲中：先做後付，他先給，你欠他一件（前半停在約定還欠著）。"""
        cid = self.fig
        if cid is None:
            return
        for who in (self.PAYER, self.LATE):
            self.stand(who, cid)
            self.talking(who, cid)
            self.ask(who, "能否送我些盤纏", "先做後付", {"ask": "gift", "willing": 100, "condition": "silver", "narrative": TALK_REPLY,
                                                        "narrative_terms": TALK_TERMS}, floor=100)
            emit("還他那一顆", self.buttons(who, "talk:repay"))

    def road_open(self) -> None:
        """路修遠求帶路：他親自帶你走一趟（體力不扣、走得慢一點讓前半停在路上）。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.WALKER, cid)
        self.talking(self.WALKER, cid)
        self.ask(self.WALKER, "請帶我去別處", "帶路", {"ask": "escort:*", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100, escort_pace=40.0)
        view = self.main(self.WALKER)
        emit("在路上的選單", sorted(self.ids(view)))

    def backing_open(self) -> None:
        """衛承光求陪你出陣：他答應今天在他那一帶陪你出陣一回（前半停在答應了、還在談）。"""
        cid = self.fig
        if cid is None:
            return
        for who in (self.BACKER, self.BACKER2):
            self.stand(who, cid)
            self.talking(who, cid)
            self.ask(who, "陪我出陣一回", "答應陪你出陣", {"ask": "sortie", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
            emit("商量打法那一顆", self.buttons(who, "talk:plan"))

    def plea_open(self) -> None:
        """葉聽雪求見焦慮的秦頡：他主動開口求你（模型挑了請託與回報）：他開的請託還沒答覆（前半停在接、不接兩顆）。"""
        from tianxia import figures

        cid = self.PLEAD_FIG if self.PLEAD_FIG in self.c.characters else self.fig
        if cid is None:
            return
        if cid == self.PLEAD_FIG:
            self.world.mutate_season(lambda s: setattr(figures._ensure(GameStateHolder(s), self.c, cid), "prestige", 1))
            from tianxia import figure_life

            emit("他此刻的心事", figure_life.mood_any(GameStateHolder(self.world.get_season()), self.c, cid))
        MODEL["talk"], MODEL["parley"] = {"stance": "suzhan"}, {"want": "*", "reward": "fit", "narrative": TALK_TERMS}
        try:
            with self.parley_on():
                if cid == self.PLEAD_FIG:  # 只有他一位的地點：求見名單收起來了，開口走交友（act:socialize）
                    self.open_social(self.PLEADER, cid)
                else:
                    self.open_call(self.PLEADER, cid)
        finally:
            MODEL["talk"] = MODEL["parley"] = None
        self.you(self.PLEADER, "他先開口")
        emit("接下、不接", self.buttons(self.PLEADER, "talk:terms"))

    def half(self) -> None:
        for who in self.PLAYERS:
            self.you(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def plain_on(self) -> None:
        """沈鶴年接著談（選下一顆）、告辭。"""
        if self.fig is None:
            return
        MODEL["talk"] = {"stance": "xumin"}
        with self.tuned(self.c.config, talk_turns_per_day=9):
            self.choose(self.TALKER, "talk:1")
            self.you(self.TALKER, "接著談")
            self.say(self.TALKER, "不如持重些")
        MODEL["talk"] = None
        self.you(self.TALKER, "又說了一句")
        self.choose(self.TALKER, "talk:leave")
        self.you(self.TALKER, "告辭")

    def terms_on(self) -> None:
        """言半山接了條件：交銀（手頭不夠先試一次）、當場指點。"""
        cid = self.fig
        if cid is None:
            return
        with self.parley_on():
            self.edit(self.ASKER, lambda p: p.stats.update({"silver": 0}))
            self.choose(self.ASKER, "talk:terms:yes")
            self.you(self.ASKER, "手頭不夠")
            self.edit(self.ASKER, lambda p: p.stats.update({"silver": 500}))
            self.choose(self.ASKER, "talk:terms:yes")
            self.you(self.ASKER, "交了銀兩")
            self.choose(self.ASKER, "talk:terms:yes")  # 沒有條件可接了
            self.choose(self.ASKER, "talk:leave")

    def doer(self) -> None:
        """紀行雲一件一件求：指點、說說敵情、贈物（都當場做）；婉拒；開條件不接；開條件接了打探掛成委託；欠他的那一件請他兌現；清單外的事當婉拒。"""
        cid = self.fig
        who = self.DOER
        if cid is None:
            return
        self.stand(who, cid)
        self.talking(who, cid)
        for text, ask in (("請指點我一招", "spar"), ("說說敵情吧", "intel"), ("送我點東西", "gift")):
            self.ask(who, text, f"求{ask}、當場做", {"ask": ask, "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
        self.ask(who, "再指點我一招", "婉拒", {"ask": "spar", "willing": 0, "condition": "", "narrative_no": TALK_NO}, floor=0)
        self.ask(who, "天下大勢如何", "只是閒聊", {"ask": "", "willing": 0, "condition": "", "narrative": TALK_REPLY}, floor=0)
        self.ask(who, "把你的刀給我", "清單外的事", {"ask": "refuse", "willing": 100, "condition": "", "narrative_no": TALK_NO}, floor=100)
        self.choose(who, "talk:leave")
        self.edit(who, lambda p: p.talks_today.clear())
        self.talking(who, cid)
        self.ask(who, "指點我一招，我替你辦事", "開條件、打探", {"ask": "gift", "willing": 0, "condition": "scout:*", "narrative_terms": TALK_TERMS}, floor=0)
        self.choose(who, "talk:terms:no")
        self.you(who, "不接條件")
        self.ask(who, "送我些盤纏，我替你辦事", "又開條件", {"ask": "gift", "willing": 0, "condition": "scout:*", "narrative_terms": TALK_TERMS}, floor=0)
        self.choose(who, "talk:terms:yes")
        self.you(who, "接了打探（掛成委託）")
        self.edit(who, lambda p: p.parley_owed.update({cid: "gift"}))  # 今天還做得到的一件（指點今天婉拒過了：那一件只會回「改日」）
        emit("請他兌現那一顆", self.buttons(who, "talk:owed"))
        self.choose(who, "talk:owed")
        self.you(who, "他兌現了")
        self.choose(who, "talk:owed")  # 沒有欠了
        self.choose(who, "talk:leave")

    def owe_on(self) -> None:
        """燕回聲還他欠的銀兩（手頭不夠先試一次）；霍斷橋過了期限：食言（情誼扣、那幾句併進書信）。"""
        cid = self.fig
        if cid is None:
            return
        with self.parley_on():
            self.edit(self.PAYER, lambda p: p.stats.update({"silver": 0}))
            self.choose(self.PAYER, "talk:repay")
            self.you(self.PAYER, "手頭不夠")
            self.edit(self.PAYER, lambda p: p.stats.update({"silver": 500}))
            self.choose(self.PAYER, "talk:repay")
            self.you(self.PAYER, "還了")
            self.choose(self.PAYER, "talk:repay")  # 沒有債了
            self.choose(self.PAYER, "talk:leave")

            def expire(s) -> None:
                for debt in s.player.parley_debts.values():
                    debt.due = s.world.time - 1

            self.edit_state(self.LATE, expire)
            self.main(self.LATE)  # 同步：欠的過了期限
            self.you(self.LATE, "食言")

    def road_on(self) -> None:
        """路修遠在路上每到一站跟他說一句（parley:road）；同一站不能說兩次。"""
        if self.fig is None:
            return
        view = self.main(self.WALKER)
        emit("在路上的選單", sorted(self.ids(view)))
        for text in ("一路有勞", "再問一句"):
            self.ask(self.WALKER, text, "路上說一句", {"ask": "intel", "willing": 100, "condition": "", "narrative": TALK_REPLY}, "parley:road", floor=100)
        self.edit(self.WALKER, lambda p: setattr(p, "parley_road_leg", -1))
        MODEL["talk"] = None
        self.say(self.WALKER, "模型叫不動", "parley:road")
        self.you(self.WALKER, "路上模型叫不動")

    def backing_on(self) -> None:
        """衛承光商量打法（成、不成各一次〔雖然第二次打法已經商量過〕）、出陣。"""
        cid = self.fig
        if cid is None:
            return
        self.ask(self.BACKER, "我想從側翼包抄", "商量打法", {"willing": 100, "narrative": TALK_REPLY, "narrative_no": TALK_PLAN_NO}, "talk:plan", plan_floor=100)
        self.ask(self.BACKER2, "那就正面強攻", "商量不成", {"willing": 0, "narrative": TALK_REPLY, "narrative_no": TALK_PLAN_NO}, "talk:plan", plan_floor=0, plan_cap=0)
        self.ask(self.BACKER2, "再換個打法", "已經商量過了", {"willing": 100, "narrative": TALK_REPLY}, "talk:plan", plan_floor=100)
        self.set_duel(False)
        for who in (self.BACKER, self.BACKER2):
            self.choose(who, "talk:leave")
            self.place(who, self.backing_spot(who))
            emit("出陣那一顆", self.ids(self.main(who)).get("act:train"))
            with self.winning():
                self.choose(who, "act:train")
            self.you(who, "出陣之後")

    def backing_spot(self, who: str) -> str:
        """他那一帶（答應陪你出陣的那一區）裡出得了陣的地方：並肩那一句（BACKED_LINE）只在他那一帶出陣才有；找不到就退回中立地汝南荒野。"""
        from tianxia import figure_life

        state = self.chars.load(who)
        b = state.player.parley_backing if state is not None else None
        for spot in sorted(loc for loc in self.c.locations if b is not None and b.region is not None and figure_life._region(self.c, loc) == b.region):
            self.place(who, spot)
            if self.ids(self.main(who)).get("act:train", {}).get("enabled"):
                emit("他那一帶出陣的地方", spot)
                return spot
        emit("他那一帶沒有出得了陣的地方", None)
        return "runan_wilds"

    def plea_on(self) -> None:
        """葉聽雪接下他的請託：記成你欠他的一件（到期沒做是食言）；再不接的另一位（冷千山沒開口，這裡略）。"""
        if self.fig is None:
            return
        with self.parley_on():
            self.choose(self.PLEADER, "talk:terms:yes")
            self.you(self.PLEADER, "接下請託")
            self.choose(self.PLEADER, "talk:leave")

    def forsake(self) -> None:
        """葉聽雪還欠著秦頡的請託，去黃巾的投靠點叛投（defect:<陣營> → defect:confirm）：欠著的都算食言（情誼扣、那幾句併進書信）。"""
        if self.fig is None:
            return
        who = self.PLEADER
        target = next((f for f in self.c.scenario.factions if f.id != self.PLAYERS[who] and f.join_at), None)
        if target is None:
            emit("沒有別的陣營可叛投", None)
            return
        self.place(who, target.join_at[0])
        ids = [i for i in self.ids(self.main(who)) if i.startswith("defect:")]
        emit("叛投那幾顆", ids)
        if ids:
            self.choose(who, ids[0])
            self.choose(who, "defect:confirm")
        self.you(who, "叛投之後")

    def foe(self) -> None:
        """冷千山（黃巾）求官軍的人物：敵對（意願的天花板再減）；擲中、擲不中各一次。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.FOE, cid)
        self.talking(self.FOE, cid)
        self.ask(self.FOE, "請指點我一招", "敵對、擲不中", {"ask": "spar", "willing": 100, "condition": "", "narrative": TALK_REPLY, "narrative_no": TALK_NO}, floor=0)
        self.ask(self.FOE, "說說敵情吧", "敵對、擲中", {"ask": "intel", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
        self.choose(self.FOE, "talk:leave")

    def bots(self) -> None:
        """假人（人物情誼一軌的 BotRunner 十輪與整季機器人）；加上 bot_policy.score 問 talk:、parley: 的各幾顆（假人只按告辭，其餘不按）。"""
        super().bots()
        from tianxia import bot_policy
        from tianxia.core.option import Option
        from tianxia.state import BotProfile

        self.begin()
        game = self.server.game_for(self.TALKER)
        profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=self.world.get_season_number())
        emit("假人眼中的分數", {oid: bot_policy.score(game, Option(id=oid, label=oid), profile) for oid in (
            "talk:0", "talk:say", "talk:leave", "talk:plan", "talk:terms:yes", "talk:terms:no", "talk:repay", "talk:owed", "talk:clue:a:0",
            "talk:opp:x", "parley:road")})

    def season(self) -> None:
        """收季、開下一季：談話、條件、欠的都跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main(self.TALKER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.you(who, "換季之後")
        self.season_view("換季之後")


def _talk_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _companions_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：指點一招那一句（parley.SPAR_LINE；搬之前在 tianxia/parley.py、之後在包裡），week7 紀行雲求指點、當場做那一下抓到
_talk_register_track("talk", TalkScenario, (("tianxia/features/companions/parley.py", "tianxia/parley.py"),
                                            ('SPAR_LINE = "{name}陪你拆了幾招，隨手點出你的破綻。"', 'SPAR_LINE = "{name}陪你拆了幾招，隨手點出你的破綻！"')), "week7")


# ═══════════════════════════ socialize（全部拆包第 21 批：交友求見） ═══════════════════════════


class SocializeScenario(CompanionsScenario):
    """交友求見（全部拆包第 21 批；--track socialize，自己一個資料庫）。
    交友（act:socialize）：人物在（只有一位的地點，名望夠〔開口、模型回了〕、名望不夠〔被打發或灰掉〕）、人物不在（幾處沒有大勢人物的地點：抽到交友事件就是事件；抽不到才是「此地無人可訪」，那一支這條軌讀不出走到沒有，pytest 換掉 pick_event 才守）。求見（act:call → call:<人物>）：兩位以上的地點打開名單，名望夠〔開口〕、名望不夠〔被打發，一類一顆開著時灰掉、結識事件走結識〕、
    返回、清單外的 id；只有一位時選單上直接列的「求見某某」。次數：前半談過一輪，後半把每日輪數調成 1（談滿，鈕灰掉、寫換日那一刻）、調成 2（談第二輪時自動告辭）。
    結識奇遇：福緣到了交友先發（入門的同伴），到期自己送上門，沒有同伴可給時送賀禮（心得）。**前半停在挑對象挑到一半**（picking_audience：求見名單開著、還沒按）：
    後半一位按人物、一位按返回、一位按了名望不夠的被打發。假人（BotRunner 十輪；bot_policy.score 問 call:、act:call、act:socialize；bot.pick 看求見名單）；換季。
    沒有大勢人物的內容（測試內容）只剩福緣與交友事件，同一串 API 照打。"""

    GREETER, LOWFAME, ABSENT = "雲棲遲", "白景行", "石臨川"
    CALLER, CALLER2, BRUSHED, BRUSHED2 = "趙明遠", "錢若水", "顧雲生", "冷霜降"
    WAITER, WAITER2, WAITER3 = "方子期", "宋寒江", "葉知秋"
    FORTUNE, OVERDUE, GIFT, GIFT2 = "蘇采薇", "秋無痕", "江映月", "夏候清"
    SNUB = "林雪衣"  # 剛被他打敗、他閉門不見
    PLAYERS = {GREETER: "guan", LOWFAME: "guan", ABSENT: "guan", CALLER: "guan", CALLER2: "guan", BRUSHED: "guan", BRUSHED2: "huang",
               WAITER: "guan", WAITER2: "guan", WAITER3: "guan", SNUB: "guan", FORTUNE: "guan", OVERDUE: "guan", GIFT: "guan", GIFT2: "guan"}
    FORTUNES = (FORTUNE, OVERDUE, GIFT, GIFT2)
    TALKER = WAITER  # 沿用人物情誼一軌的假人段落要的名字
    PHASES_FIRST = ["setup", "seat", "alone", "absent", "hall", "fortune", "list_open", "half"]
    PHASES_SECOND = ["resume", "list_on", "talked_out", "bots", "gift", "season"]

    # ── 小工具 ──

    def layout(self) -> dict[str, list[str]]:
        """大勢人物此刻各在哪一處（人物活起來的季他會走動）：地點 → 人物 id。"""
        from tianxia import figure_life

        holder = GameStateHolder(self.world.get_season())
        where: dict[str, list[str]] = {}
        for cid, ch in sorted(self.c.characters.items()):
            if not ch.deep_interaction:
                continue
            try:
                loc = figure_life.where(holder, self.c, cid)
            except Exception:  # noqa: BLE001
                loc = ch.talk_at or ch.recruit_at
            if loc is not None:
                where.setdefault(loc, []).append(cid)
        return where

    def hall_spot(self) -> tuple[str | None, list[str]]:
        """兩位以上大勢人物的地點（交友不直接找人、改按求見指名）；沒有是 (None, [])。"""
        halls = {loc: figs for loc, figs in self.layout().items() if len(figs) >= 2}
        if not halls:
            return None, []
        loc = sorted(halls, key=lambda x: (-len(halls[x]), x))[0]
        return loc, halls[loc]

    def alone_spot(self) -> tuple[str | None, str | None]:
        """只有一位大勢人物的地點（交友直接開口、選單上直接列「求見某某」）；沒有是 (None, None)。"""
        lone = {loc: figs[0] for loc, figs in self.layout().items() if len(figs) == 1}
        if not lone:
            return None, None
        loc = next((x for x, cid in sorted(lone.items()) if cid == "qinjie"), sorted(lone)[0])
        return loc, lone[loc]

    def fame(self, who: str, value: int) -> None:
        self.edit(who, lambda p: p.stats.update({"fame": value}))

    def you(self, who: str, tag: str) -> None:
        """存檔裡交友求見碰得到的格子：在哪、體力、名望、心得、銀兩、福緣、求見名單開著沒、談話對象、今天各聊幾輪、情誼、名下、結識旗標、行狀與最新兩則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "location": p.location, "stamina": p.stamina, "fame": p.stats.get("fame", 0), "xinde": p.stats.get("xinde", 0),
            "silver": p.stats.get("silver", 0), "fortune": p.fortune, "picking": p.picking_audience, "pending": p.pending_companion,
            "talks_today": dict(sorted(p.talks_today.items())), "affinities": dict(sorted(p.affinities.items())), "team": list(p.team),
            "met": sorted(f for f in p.flags if f.startswith("結識:")), "offered": p.last_offered_dialogue,
            "annals": [[a.kind, a.text, a.figure] for a in p.annals][-3:],
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]]})

    def asks(self, who: str, tag: str, cids: list[str]) -> None:
        """伺服器假人與鈕上用的幾個查詢（在這裡交友會不會直接開口、交友是不是白跑一趟、見不見得到某位人物）。"""
        self.begin()
        game = self.server.game_for(who)
        emit(f"{who} {tag} 查詢", {"starts_dialogue": game.socialize_starts_dialogue(), "futile": game.socialize_is_futile(),
                                  "can_meet": {cid: game.can_meet_figure(cid) for cid in cids}})

    def press(self, who: str, option_id: str) -> None:
        """按一顆；先碰上一件留在交友的事（福緣、結識事件之類）就了結它。"""
        view = self.choose(who, option_id)
        if any(i.startswith("choice:") for i in self.ids(view)):
            self.settle_choices(who)

    def leave(self, who: str) -> None:
        state = self.chars.load(who)
        if state is not None and state.player.pending_companion:
            self.choose(who, "talk:leave")

    def reach(self, who: str, cid: str) -> None:
        """只有一位的地點找他說話：選單上有直接的「求見某某」就按它；一類一顆開著時沒有（單人求見併進交友那一顆），改按交友。"""
        if f"call:{cid}" in self.ids(self.main(who)):
            self.press(who, f"call:{cid}")
        else:
            self.press(who, "act:socialize")

    def open_list(self, who: str) -> None:
        """打開求見的名單：行動列上有 act:call（兩位以上的地點）就按它，沒有（舊存檔、改版後）直接擺成挑到一半。"""
        if "act:call" in self.ids(self.main(who)):
            self.choose(who, "act:call")
        else:
            self.edit(who, lambda p: setattr(p, "picking_audience", True))
        self.main(who)

    def seat(self) -> None:
        """福緣先全部記成領過（不然 place 把加入的日子推到很久以前，同步一下就先送上門）；福緣那幾位入座之後再還原。"""
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))
        super().seat()
        for who in self.FORTUNES:
            self.edit_state(who, lambda s: (setattr(s.player, "fortune", False), setattr(s.player, "joined_at", s.world.time)))
        # GIFT、GIFT2 留到後半（同伴全被招走之後）才還原
        for who in (self.GIFT, self.GIFT2):
            self.edit(who, lambda p: setattr(p, "fortune", True))
        self.edit(self.OVERDUE, lambda p: setattr(p, "joined_at", -1.0e9))

    # ── 前半 ──

    def alone(self) -> None:
        """交友，人物在（只有一位的地點）：名望夠 → 開口；名望不夠 → 被打發話或灰掉。模型回了。"""
        loc, cid = self.alone_spot()
        if cid is None:
            emit("這份內容沒有只有一位大勢人物的地點", None)
            return
        # 模型叫不動：開口退回體力（先做：之後名望夠的那位要談滿一輪，後半次數用完那一段才真的談滿）
        self.place(self.GREETER, loc)
        self.fame(self.GREETER, 9999)
        self.reach(self.GREETER, cid)
        self.you(self.GREETER, "求見・模型叫不動")
        self.leave(self.GREETER)
        MODEL["talk"] = {"stance": "suzhan"}
        for who, value, tag in ((self.GREETER, 9999, "名望夠"), (self.LOWFAME, 0, "名望不夠")):
            self.place(who, loc)
            self.fame(who, value)
            self.main(who)
            self.asks(who, f"交友・{tag}", [cid])
            self.press(who, "act:socialize")
            self.you(who, f"交友・{tag}之後")
            if self.chars.load(who).player.pending_companion:
                self.choose(who, "talk:0")  # 談一輪：記一輪（後半次數用完那一段看它）
            self.leave(who)
        # 選單上直接列的「求見某某」：名望夠，按下去開口（今天談過一輪，後半看次數）
        self.place(self.CALLER2, loc)
        self.fame(self.CALLER2, 9999)
        self.reach(self.CALLER2, cid)
        self.you(self.CALLER2, "直接求見")
        if self.chars.load(self.CALLER2).player.pending_companion:
            self.choose(self.CALLER2, "talk:0")  # 談一輪：記一輪（後半看次數）
        self.you(self.CALLER2, "直接求見・談了一輪")
        self.leave(self.CALLER2)
        MODEL["talk"] = None

    def absent(self) -> None:
        """交友，人物不在：幾處沒有大勢人物的地點（抽到交友事件就是事件；「此地無人可訪」那一支只有抽不到時才出現，這裡不保證走到）。"""
        for loc in ("runan_wilds", "nanyang_road", "yu_river", "town"):
            if not self.place(self.ABSENT, loc):
                continue
            self.fame(self.ABSENT, 9999)
            self.main(self.ABSENT)
            self.asks(self.ABSENT, f"交友・{loc}", [])
            self.press(self.ABSENT, "act:socialize")
            self.you(self.ABSENT, f"交友・{loc}之後")

    def hall(self) -> None:
        """求見，兩位以上的地點：名單、名望夠按人物、名望不夠被打發（或灰掉）、返回、清單外的 id、沒有人可以按的 id。"""
        loc, figs = self.hall_spot()
        if loc is None:
            emit("這份內容沒有兩位以上大勢人物的地點", None)
            return
        fig = figs[0]
        MODEL["talk"] = {"stance": "suzhan"}
        self.place(self.CALLER, loc)
        self.fame(self.CALLER, 9999)
        self.main(self.CALLER)
        self.asks(self.CALLER, "求見・名望夠", figs)
        self.open_list(self.CALLER)
        self.press(self.CALLER, f"call:{fig}")
        self.you(self.CALLER, "求見・名望夠")
        if self.chars.load(self.CALLER).player.pending_companion:
            self.choose(self.CALLER, "talk:0")  # 談一輪：記一輪（後半看次數）
        self.you(self.CALLER, "求見・談了一輪")
        self.leave(self.CALLER)
        for who in (self.BRUSHED, self.BRUSHED2):
            self.place(who, loc)
            self.fame(who, 0)
            self.main(who)
            self.asks(who, "求見・名望不夠", figs)
            self.open_list(who)
            self.press(who, f"call:{fig}")
            self.you(who, "求見・名望不夠")
        self.open_list(self.BRUSHED)
        self.press(self.BRUSHED, "call:back")
        self.you(self.BRUSHED, "求見・返回")
        self.press(self.BRUSHED, "call:zhugeliang_not_here")
        self.press(self.BRUSHED, "call:back")
        self.snubbed(loc, figs)
        MODEL["talk"] = None

    def snubbed(self, hall: str, figs: list[str]) -> None:
        """閉門不見（剛被他打敗，現實時間內他不見）：兩位以上的名單裡灰掉、只有一位的地點直接求見與交友都灰掉；硬按也沒事。"""
        from tianxia import figures

        spot, lone = self.alone_spot()
        # 閉門名單只蓋得到大勢人物（figures.of_character）：兩位以上的地點挑「有兩位以上大勢人物」的那一處；找不到就照原本的
        real = {loc: [cid for cid in fs if figures.of_character(self.c, cid) is not None] for loc, fs in self.layout().items()}
        halls = {loc: fs for loc, fs in real.items() if len(fs) >= 2}
        if halls:
            hall = sorted(halls, key=lambda x: (-len(halls[x]), x))[0]
            figs = halls[hall]
        if lone is not None and figures.of_character(self.c, lone) is None:
            lone = None
        names = [cid for cid in [*figs, lone] if cid is not None]
        until = {figures.of_character(self.c, cid): 1.0e12 for cid in names if figures.of_character(self.c, cid) is not None}
        self.edit(self.SNUB, lambda p: p.snubbed_until.update(until))
        self.fame(self.SNUB, 9999)
        self.place(self.SNUB, hall)
        self.main(self.SNUB)
        self.open_list(self.SNUB)
        self.press(self.SNUB, f"call:{figs[0]}")
        self.you(self.SNUB, "閉門不見・名單")
        self.leave(self.SNUB)  # 沒灰掉的話他開口了：告辭，後面的按鈕才不被談話擋住
        self.press(self.SNUB, "call:back")
        if lone is not None:
            self.place(self.SNUB, spot)
            self.main(self.SNUB)
            self.asks(self.SNUB, "閉門不見・只有一位", [lone])
            self.press(self.SNUB, f"call:{lone}")
            self.press(self.SNUB, "act:socialize")
            self.you(self.SNUB, "閉門不見・只有一位")
            self.leave(self.SNUB)

    def fortune(self) -> None:
        """結識奇遇：福緣到了（第 0 天起必定先觸發）交友先發入門的同伴；到期沒發生的自己送上門（同步）。"""
        with self.tuned(self.c.config, fortune_day_min=0):
            self.place(self.FORTUNE, "runan_wilds")
            self.main(self.FORTUNE)
            self.press(self.FORTUNE, "act:socialize")
            self.you(self.FORTUNE, "福緣・交友先發")
        self.main(self.OVERDUE)
        self.you(self.OVERDUE, "福緣・到期自己送上門")
        self.season_view("福緣之後")

    def list_open(self) -> None:
        """挑對象挑到一半（前半切在這裡）：求見名單開著、還沒按；一位名望夠、一位名望不夠、一位站在只有一位的地點（直接求見那顆）。"""
        loc, figs = self.hall_spot()
        if loc is None:
            return
        MODEL["talk"] = None
        self.place(self.WAITER, loc)
        self.fame(self.WAITER, 9999)
        self.open_list(self.WAITER)
        self.place(self.WAITER2, loc)
        self.fame(self.WAITER2, 0)
        self.open_list(self.WAITER2)
        self.place(self.WAITER3, loc)
        self.fame(self.WAITER3, 9999)
        self.open_list(self.WAITER3)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.you(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def list_on(self) -> None:
        """接著挑：名望夠的按人物（每日輪數調成 2：談第二輪時聊滿、自動告辭）；名望不夠的按人物（被打發或灰掉）、再打開、按返回；還有一位直接按返回。"""
        loc, figs = self.hall_spot()
        if loc is None:
            return
        fig = figs[0]
        MODEL["talk"] = {"stance": "suzhan"}
        with self.tuned(self.c.config, talk_turns_per_day=2):
            self.main(self.WAITER)
            self.press(self.WAITER, f"call:{fig}")
            self.you(self.WAITER, "接著按人物")
            for turn in (1, 2):
                if self.chars.load(self.WAITER).player.pending_companion:
                    self.choose(self.WAITER, "talk:0")
                    self.you(self.WAITER, f"談第 {turn} 輪（每日 2 輪，聊滿自動告辭）")
            self.leave(self.WAITER)
        MODEL["talk"] = None
        self.main(self.WAITER2)
        self.press(self.WAITER2, f"call:{fig}")
        self.you(self.WAITER2, "名望不夠的接著按人物")
        self.open_list(self.WAITER2)
        self.press(self.WAITER2, "call:back")
        self.you(self.WAITER2, "接著按返回")
        self.main(self.WAITER3)
        self.press(self.WAITER3, "call:back")
        self.you(self.WAITER3, "直接返回")

    def talked_out(self) -> None:
        """次數用完：每日輪數調成 1，前半談過一輪的人（只有一位的地點直接求見、兩位以上的名單）鈕灰掉、寫換日的那一刻，硬按也沒事。"""
        with self.tuned(self.c.config, talk_turns_per_day=1):
            loc, cid = self.alone_spot()
            if cid is not None:
                self.place(self.CALLER2, loc)
                self.asks(self.CALLER2, "次數用完・只有一位", [cid])
                self.reach(self.CALLER2, cid)
                self.you(self.CALLER2, "次數用完・只有一位")
                self.place(self.GREETER, loc)
                self.main(self.GREETER)
                self.press(self.GREETER, "act:socialize")
                self.you(self.GREETER, "次數用完・交友")
            hall, figs = self.hall_spot()
            if hall is not None:
                self.place(self.CALLER, hall)
                self.main(self.CALLER)
                self.open_list(self.CALLER)
                self.press(self.CALLER, f"call:{figs[0]}")
                self.you(self.CALLER, "次數用完・名單")
                self.press(self.CALLER, "call:back")

    def bots(self) -> None:
        """假人（人物情誼一軌的 BotRunner 十輪與整季機器人）；加上 bot_policy.score 問 call:、act:call、act:socialize 的各幾顆，與整季機器人看求見名單怎麼挑。"""
        super().bots()
        from tianxia import bot, bot_policy
        from tianxia.core.option import Option
        from tianxia.state import BotProfile

        self.begin()
        game = self.server.game_for(self.WAITER)
        profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=self.world.get_season_number())
        cid = (self.hall_spot()[1] or [self.alone_spot()[1] or "luzhi"])[0]
        emit("假人眼中的分數", {oid: bot_policy.score(game, Option(id=oid, label=oid), profile) for oid in (
            f"call:{cid}", "call:back", "call:nobody", "act:call", "act:socialize")})
        loc, figs = self.hall_spot()
        if loc is None:
            return
        for who, value in ((self.BRUSHED, 0), (self.CALLER, 9999)):
            self.place(who, loc)
            self.fame(who, value)
            self.edit(who, lambda p: setattr(p, "picking_audience", True))
            self.begin()
            solo = self.server.game_for(who)
            opts = solo.options(odds=False)
            emit(f"整季機器人眼前的選單（{who}）", [o.id for o in opts])
            emit(f"整季機器人挑的（{who}）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(30)}))
            self.edit(who, lambda p: setattr(p, "picking_audience", False))

    def gift(self) -> None:
        """結識奇遇，沒有同伴可給：同伴全被招走（名下記到別人）之後，到期的送賀禮（心得）、福緣到了的交友也送賀禮。"""
        for cid, ch in sorted(self.c.characters.items()):
            if ch.kind == "recruitable":
                with self.world.action_lock():
                    self.world.update_companion(cid, lambda pr: setattr(pr, "owner", "某位江湖客"))
        self.edit(self.GIFT, lambda p: (setattr(p, "fortune", False), setattr(p, "joined_at", -1.0e9)))
        self.main(self.GIFT)
        self.you(self.GIFT, "賀禮・到期自己送上門")
        self.edit(self.GIFT2, lambda p: setattr(p, "fortune", False))
        with self.tuned(self.c.config, fortune_day_min=0):
            self.place(self.GIFT2, "runan_wilds")
            self.main(self.GIFT2)
            self.press(self.GIFT2, "act:socialize")
            self.you(self.GIFT2, "賀禮・交友")

    def season(self) -> None:
        """收季、開下一季：談話次數、求見名單、福緣都跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main(self.WAITER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.you(who, "換季之後")
        self.season_view("換季之後")


def _social_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（同 _talk_register_track；名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：談滿了的鈕括號裡那一句（「已經談滿 N 輪，…」；搬之前在 engine.py 的 Game._talked_out_note，搬之後在包裡），week7 次數用完那一段抓到
_social_register_track("socialize", SocializeScenario, (("tianxia/engine.py", "tianxia/features/socialize/actions.py", "tianxia/features/socialize/view.py"),
                                                       ('輪，{when}"', '輪！{when}"')), "week7")  # 只改「輪，」那一小段：搬之前是 self._talk_cap()、搬之後是 talk_cap(ctx)，前面的字不同、這一段一樣


# ═══════════════════════════ strip（全部拆包第 13 批「拿掉一」，dev/strip-1）：strip 一軌 ═══════════════════════════
# 探索三選一、找素材「自己說」、城裡操練拿掉（計畫 docs/superpowers/plans/2026-11-04-拿掉一-第13批.md）。這一批不是純搬：week7、season21、test
# 三種設定要一個字都不變，none、weekend 只照拿掉的範圍變。這一軌盯的是「三選一的開關關掉之前還有人在讀」的那幾處（總表第 13 列「先做」）：
# 一類一顆（precise.on）、可重複的事件推大勢的五折、捐軍備推大勢、觀山石（擲中加成與卡上那一句）、討伐懸賞的說法、玩法說明的探索那幾行，
# 活著的小工具（找素材 gather_finds、補料 one_of、領地多給一份的亂數、is_town）、尋敵分級（training 留著的那一半），與舊的 id
# 按下去的回話。名字一律原創（第 22 批認定第 3 條）。這一段整塊是這一批的：接在檔尾、最後一行登記，PM 合的時候不跟別人的行穿插。


class StripScenario(EventScenario):
    """拿掉一（全部拆包第 13 批；--track strip，自己一個資料庫）。小工具借事件那一軌的（card、press）與探索那一軌的（draws、tweak、settle、
    kind_places、first_event、edit_state）。半舊半新切在 half 之後：三張牌寫到一半——舊程式端出來的事件卡（等回答）、有所感（等選做法）、
    今天按過一次操練（只有不帶設定與 weekend 按得到，存檔留著 drill_day、drills_today）；後半第一件事（answer）是新程式接著答完。"""

    PLAYERS = {"韓墨川": "guan", "蘇映秋": "huang", "杜遠山": None, "程聽雪": None, "裴寒舟": "guan", "顧行之": None, "沈晚舟": None}
    NEWBIE = "阮青禾"
    BOT_SEATS = [("寒甲", "yingshui"), ("寒乙", "yingchuan"), ("寒丙", "julu_altar"), ("寒丁", "guangzong")]
    PHASES_FIRST = ["setup", "howto", "menus", "old_ids", "precise", "push_event", "donate", "stone", "strike", "tiers", "home", "half"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]

    # ── 小工具 ──

    def game(self, who: str):
        """這個人此刻的 Game（只讀：算完不存，同伺服器每個請求重建）。"""
        from tianxia.engine import Game

        self.begin()
        return Game(self.c, self.chars.load(who), world=self.world)

    def side(self, who: str) -> str | None:
        want = self.PLAYERS.get(who)
        return want if want in {f.id for f in self.c.scenario.factions} else None

    def base_of(self, who: str) -> str | None:
        """這個人陣營的大本營（第一個投靠點）；沒有陣營是 None。"""
        side = self.side(who)
        faction = next((f for f in self.c.scenario.factions if f.id == side), None)
        return faction.join_at[0] if faction is not None and faction.join_at else None

    def field(self) -> str | None:
        """城外、有對手的地方（照 id 排第一處）；這份內容沒有是 None。"""
        from tianxia.engine import Game

        game = Game(self.c, self.chars.load("杜遠山"), world=self.world)
        cfg = self.c.config
        spots = [i for i, x in sorted(self.c.locations.items()) if cfg.explore_mix_of(x.tags).kind != "town" and game._wild_foes(x)]
        return "yingshui" if "yingshui" in spots else spots[0] if spots else None

    def town(self) -> str | None:
        cfg = self.c.config
        spots = [i for i, x in sorted(self.c.locations.items()) if cfg.explore_mix_of(x.tags).kind == "town"]
        return "yingchuan" if "yingchuan" in spots else spots[0] if spots else None

    def look_here(self, who: str, tag: str) -> None:
        """選單、行動列底下那幾行、四格那一格、main.training（尋敵分級開著沒）、輿圖詳情的那一句與分級。"""
        view = self.main(who)
        emit(f"{who} {tag}", {"options": view.get("options"), "notes": view.get("action_notes"), "training": view.get("training"),
                              "mostly": view.get("mostly")})
        game = self.game(who)
        loc = game.content.locations[game.state.player.location]
        emit(f"{who} {tag} 分級與詳情", {"tier": game._practice_tier(loc), "fierce": game._fierce_line(loc), "detail": game.place_detail(loc.id)})

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)
        for who in self.PLAYERS:
            self.place(who, None, faction=self.side(who))
        self.begin()

    def howto(self) -> None:
        """玩法說明（探索那幾行、殘譜、有所感的「靜心感悟」、交友的事在哪）：有陣營的與散人各看一次；序章裡的新人也看一次。"""
        for who in ("韓墨川", "杜遠山", self.NEWBIE):
            self.call(who, "GET", "/api/howto")

    def menus(self) -> None:
        """各種地點的選單：地點種類各站一次（有陣營的、散人）。"""
        for kind, loc in self.kind_places():
            for who in ("韓墨川", "杜遠山"):
                self.place(who, loc)
                self.look_here(who, f"在{kind}")

    def old_ids(self) -> None:
        """舊的 id 按下去：三選一的幾顆、分支、自己說、操練（week7、season21、test 本來就不在選單上，照 choose 既有的回法回；
        不帶設定與 weekend 的 base 真的做事，head 同樣照 choose 既有的回法回）。"""
        who = "顧行之"
        for spot in (self.field(), self.town()):
            self.place(who, spot)
            for oid in ("explore:gather", "explore:gather:mine", "explore:gather:say", "explore:seek", "explore:sense", "explore:practice",
                        "explore:", "act:drill"):
                self.place(who, spot)
                self.choose(who, oid)
                self.settle(who)
        self.me(who, "按過舊的 id")

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"), "exp": p.member.exp, "level": p.member.level,
            "materials": dict(sorted(p.materials.items())), "explore_seq": p.explore_seq, "drill": [p.drill_day, p.drills_today],
            "pending": state.pending_event, "sensing": p.sensing is not None, "marks": sorted(p.newbie_marks),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def precise(self) -> None:
        """一類一顆還開著（precise.on 不再看三選一的開關）：交友只談話、拜入門派另成一顆、找事件的併池看得出來的地方（選單、紀錄）。"""
        who = "沈晚舟"
        town = self.town()
        self.place(who, town)
        self.look_here(who, "城裡的交友")
        opts = self.options(who)
        for oid in ("act:socialize", "act:call"):
            if opts.get(oid, {}).get("enabled"):
                self.choose(who, oid)
                self.settle(who)
                break
        self.me(who, "交友之後")
        sect = self.first_event(lambda e: any(ch.effect.join_sect for ch in e.choices) and bool(e.locations))
        if sect is not None:
            self.place(who, self.c.events[sect].locations[0])
            self.look_here(who, "門派所在地")
        game = self.game(who)
        from tianxia import events as event_rules
        from tianxia import precise as precise_rules

        emit("這一季一類一顆", {"on": precise_rules.on(self.c, game.state.world),
                              "explore_common": sorted(e.id for e in event_rules.event_candidates(game.state, self.c, "explore", "common"))[:30],
                              "social_common": sorted(e.id for e in event_rules.event_candidates(game.state, self.c, "socialize", "common"))[:30]})

    def push_event(self) -> None:
        """事件推大勢的五折：可重複的打折、一次性的全額（/api/choose 真的按；另外直接問 _shaped 每一條線、每一種來源的量）。"""
        self.trends("事件之前")
        repeat = self.first_event(lambda e: not e.once and not e.qiyu and any(ch.effect.trend for ch in e.choices))
        once = self.first_event(lambda e: e.once and any(ch.effect.trend for ch in e.choices))
        for who, eid in (("韓墨川", repeat), ("蘇映秋", once)):
            if self.card(who, eid):
                self.press(who, lambda ch: bool(ch.effect.trend), f"{eid} 推大勢那一顆")
                self.settle_choices(who)
                self.trends(f"{eid} 之後")
        game = self.game("韓墨川")
        lines = sorted(game._resisted_lines())
        emit("每一條線的量", {line: {src: list(game._shaped(line, 2.0, src)) for src in ("event", "event_once", "donate", "sortie", "duty")}
                             for line in lines})

    def trends(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"大勢 {tag}", {"trends": dict(sorted(s.trends.items())), "accum": dict(sorted(s.trend_accum.items()))})

    def donate(self) -> None:
        """捐軍備推大勢（economy.donate_push 也乘事件那一折）：自家大本營按軍需官那一串。沒有陣營的內容寫沒有。"""
        from tianxia import economy

        emit("捐十點推多少", economy.donate_push(self.c, 10))
        who = "裴寒舟"
        base = self.base_of(who)
        if base is None:
            emit("這份內容沒有大本營", None)
            return
        first = next((m for m in sorted(self.c.materials.values(), key=lambda m: (m.tier, m.id)) if economy.donate_points(self.c, m.id) > 0), None)
        if first is None:
            emit("這份內容沒有捐得了的素材", None)
            return
        self.place(who, base)

        def fn(p):
            p.materials[first.id] = 12
        self.edit(who, fn)
        self.trends("捐之前")
        opts = self.options(who)
        if opts.get("act:donate", {}).get("enabled"):
            opts = self.ids(self.choose(who, "act:donate"))
            pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i != "donate:back"), None)
            if pick is not None:
                self.choose(who, pick)
            self.choose(who, "donate:back")
        self.trends("捐之後")
        self.me(who, "捐之後")

    def stone(self) -> None:
        """觀山石：卡上那一句、靜心感悟擲中多幾個百分點（寶物表裡沒有它的內容照效果直接換 treasures.amount）、真的戴上看修練頁與探索。"""
        from tianxia import sensing, treasures
        from tianxia.state import Equipment

        who = "程聽雪"
        spot = self.field()
        self.place(who, spot)
        emit("觀山石那一句", treasures.effect_text(self.c, "insight"))
        game = self.game(who)
        loc = game.content.locations[game.state.player.location]
        emit("沒戴的擲中", sensing.rate(game.state, self.c, loc))
        fake = lambda st, ct, key: 1.5 if key == "insight" else 1.0  # noqa: E731
        with self.tweak(treasures, amount=fake):
            emit("戴著的擲中", sensing.rate(game.state, self.c, loc))
        stone = next((g for g in self.c.gear.treasures.values() if g.effect == "insight"), None)
        if stone is None:
            emit("這份內容沒有觀山石", None)
            return

        def fn(p):
            p.treasure = Equipment(id="寶:觀山", slot="treasure", name=stone.name, template=stone.id)
        self.edit(who, fn)
        self.call(who, "GET", "/api/menxia")
        game = self.game(who)
        emit("真的戴著的擲中", {"rate": sensing.rate(game.state, self.c, loc), "weights": game._explore_weights(loc)})

    def strike(self) -> None:
        """討伐懸賞的說法：有陣營的、散人；一類一顆關著的那一支（沒蓋章的舊季）。"""
        from tianxia import bounties
        from tianxia.state import Bounty

        spot = self.field()
        game = self.game("韓墨川")
        squad = next((f.id for f in game._wild_foes(self.c.locations[spot])), None) if spot else None
        if squad is None:
            emit("這份內容沒有討伐得了的", None)
            return
        strike = Bounty(id="b-strike", kind="strike", faction=None, week=1, expires=1e12, silver=20, deeds=1, location=spot, squad=squad)
        scout = Bounty(id="b-scout", kind="scout", faction=None, week=1, expires=1e12, silver=20, deeds=1, location=spot)
        for who in ("韓墨川", "杜遠山"):
            state = self.game(who).state  # Game 上那一份才接著這一季（chars.load 的 world 是空的、沒蓋章）
            emit(f"{who} 討伐怎麼交差", bounties.how(self.c, strike, state))
            emit(f"{who} 打探怎麼交差", bounties.how(self.c, scout, state))
        world = self.world.get_season()
        emit("傳聞的說法", bounties.how(self.c, strike, None, world))
        with self.tweak(self.c.config, precise_actions=False):
            emit("一類一顆關著的說法", {who: bounties.how(self.c, strike, self.game(who).state) for who in ("韓墨川", "杜遠山")})

    def tiers(self) -> None:
        """尋敵分級留著的那一半（training.on、tier_of、TIER_WORDS、PLACE_LINE）：輿圖的舊 API、探索一顆打贏的 field2、新手目標「去做」帶去哪。"""
        who = "杜遠山"
        status, view = self.call(who, "GET", f"/api/map?place={self.field() or ''}")
        emit("輿圖詳情", view.get("detail") if isinstance(view, dict) else status)
        game = self.game(who)
        emit("每一處的分級", {i: game._practice_tier(x) for i, x in sorted(self.c.locations.items())})
        emit("新手目標去哪", {go: game._newbie_go(go) for go in ("practice0", "practice1", "practice2", "bounties", "tavern")})
        emit("新手目標", game.newbie_view())

    def home(self) -> None:
        """領地多給一份（_home_gather 用三選一那一顆亂數的名字「探索|…|領地」）、素材那一拍（gather_finds、one_of）：站自家領地，機會定成必中。"""
        explore_one = _explore_rules()

        who = "韓墨川"
        spot = self.base_of(who) or self.field()
        if spot is None:
            return
        self.place(who, spot)
        game = self.game(who)
        with self.tweak(self.c.config.conquest, gather_bonus_chance=1.0):
            emit("領地多給的", game._home_gather(self.c.locations[spot], []))
        from tianxia import conquest

        block = next((i for i, x in sorted(self.c.locations.items()) if conquest.home(self._at(who, i), self.c)), None)
        emit("自家領地", block)
        for where in filter(None, (block, self.field(), self.town())):
            self.place(who, where)
            with self.tweak(self.c.config.conquest, gather_bonus_chance=1.0), self.draws(explore_one.MATERIAL):
                self.explore(who)
            self.me(who, f"在 {where} 探索之後")
        self.place("沈晚舟", self.field())
        with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
            self.explore("沈晚舟")
        self.me("沈晚舟", "遭遇打贏之後")

    def _at(self, who: str, loc: str):
        state = self.chars.load(who)
        state.player.location = loc
        return state

    def half(self) -> None:
        """切點：蘇映秋等著回答一張事件卡（舊程式探索端出來的）、裴寒舟等著選有所感的做法、杜遠山今天按過一次操練（不帶設定、weekend）。"""
        explore_one = _explore_rules()

        self.place("蘇映秋", self.field())
        with self.draws(explore_one.EVENT):
            self.seek("蘇映秋")
        self.me("蘇映秋", "切點")
        self.place("裴寒舟", self.field())
        with self.draws(explore_one.INSIGHT):
            self.choose("裴寒舟", "act:explore")
            opts = self.options("裴寒舟")
            if opts.get("explore:sense", {}).get("enabled"):
                self.choose("裴寒舟", "explore:sense")
        self.me("裴寒舟", "切點")
        self.place("杜遠山", self.town())
        opts = self.options("杜遠山")
        if opts.get("act:drill", {}).get("enabled"):
            self.choose("杜遠山", "act:drill")
        self.me("杜遠山", "切點")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        for who in ("蘇映秋", "裴寒舟"):
            self.settle(who)
            self.me(who, "答完")
        self.main("杜遠山")
        self.me("杜遠山", "接手之後")

    def again(self) -> None:
        """接手之後再走一遍：說明、選單、舊的 id。"""
        self.howto()
        for who in ("韓墨川", "杜遠山"):
            self.place(who, self.field())
            self.look_here(who, "接手之後")
            self.explore(who)
            self.me(who, "接手之後探索")

    def bots(self) -> None:
        """假人：BotRunner＋bot_policy.take_turn（random.Random(17)，時鐘一輪推四分）四個擺在城外、城裡、兩軍的地方；整季機器人讀的那兩處
        （bot.explore_choice、bot.pick）在真的選單上問一次。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        spare = sorted(self.c.locations)
        names = [name for name, _ in self.BOT_SEATS]
        for i, (name, loc) in enumerate(self.BOT_SEATS):
            loc = loc if loc in self.c.locations else spare[i % len(spare)]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            side = sides[i % len(sides)] if sides else None
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            self.chars.save(g.state)
        for name in names:
            self.begin()
            g = Game(self.c, self.chars.load(name), world=self.world)
            opts = g.options(odds=False)
            ids = [o.id for o in opts]
            emit(f"{name} 整季機器人", {"choice": bot.explore_choice(ids), "exp": bot.explore_choice(ids, "exp"),
                                     "pick": bot.pick(g, opts, random.Random(0))})
            emit(f"{name} 假人的分數", {o.id: bot_policy.score(g, o, g.state.player.bot) for o in opts
                                     if o.id.startswith(("act:explore", "act:train", "act:drill", "explore:"))})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_STRIP_TICKS", "30"))):
                STEP[0] += 3
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        emit("假人 紀錄標題", {s.player.name: sorted(Counter(e.title for e in s.journal).items()) for s in states})
        emit("假人 第幾次探索", {s.player.name: s.player.explore_seq for s in states})
        emit("假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})

    def season(self) -> None:
        """收季、開下一季：操練的記號照帶（舊季）、新的一季蓋章（一類一顆、減法季）之後的說明與選單。"""
        self.do(ADMIN, "end_season")
        self.main("杜遠山")
        self.do(ADMIN, "next_season")
        self.me("杜遠山", "換季之後")
        for who in ("杜遠山", "韓墨川"):
            self.look_here(who, "換季之後")
            self.call(who, "GET", "/api/howto")


_events_register_track("strip", StripScenario, (("tianxia/treasures.py",), ("靜心感悟擲中的機會 +", "靜心感悟擲中的機會＋")), "week7")


# ═══════════════════════════ story：一條線＋簽到一軌（全部拆包第 30 批，dev/story-1） ═══════════════════════════
# 一條線（tianxia/storyline.py 與 Game 上 story_*、_story_*、_mirror_squad 十個方法、story: 前綴）與每日簽到（tianxia/checkin.py 與
# Game 上 check_in、_auto_checkin、checkin_view 三個方法）搬進新包 tianxia/features/story/ 與 tianxia/features/checkin/（舊名留成別名；計畫
# docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記（_story_register_track），
# PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

_STORY_CHECKIN_DAY = 6  # 簽到要挑四階的第一天（Config.checkin.tier4_days 的第一個）；前半快轉到這一天、人都還沒領


class StoryScenario(Scenario):
    """一條線＋簽到（全部拆包第 30 批；--track story，自己一個資料庫）。程式組的線（story_start）自己寫五條，內容寫的長篇奇事走真的那一條（賣兒契）：
    - 答題：宋問津開山徑三問，答第一題——**前半停在答到一半**（story_open 還開著）；後半答第二題、先擱著（later）、再按回來、答完（照記號走結局、
      文字照記號換段落）、收卡（story_seen）、答不在選單上的（story:…:a9）。
    - 打一場：呂臨淵打渡口一戰落敗（灰著寫還要等多久、按灰的被擋、行狀與卡）——**前半停在等著再試**；後半時候到了打贏入傳。桑弄潮打鏡中人
      （自己的影子，難度照輸過幾次削弱）輸兩次、第三次贏。
    - 期限：魏守拙的答題段有期限，前半只開線，後半把期限擺成過了，同步時往 late 走、失敗的結局入傳。
    - 長篇奇事（內容寫的線，走事件、多日段、站到各段的地點）：周問舟在汝南荒野遇上賣兒契，前半走幾步停在半路（簽到的快轉排在最前面，等的段與期限都還沒過就跨過切點），後半接著走完；
      杜歸舟後半才在潁川書院遇上臥龍岡的地，一路走完。
    - 季末未了：衛未央、蔡留白各開一條答題線不答，收季之後衛未央同步一次（寫此事未了）、蔡留白不同步（換季那一刻補寫）。
    - 簽到（season21、week7 開著；其餘寫「這一季沒有簽到」，同一串 API 照打）：祝延年、范長歌第 1 天自動領了，快轉到要挑四階的那一天——
      **前半停在當天還沒領**；後半：祝延年沒挑（回要先挑）、挑錯、挑對領了、再領一次（簽過了）；范長歌直接挑對；隔天（普通日）自動領、過了最後一天畫面沒有簽到。
    - 章回主線、探索擲中（審查修正）：韓承業投靠官軍、照 walk 走章回的事件段；陸尋蹤把長篇奇事開頭的機率擺成 1、站到開頭的地方按探索。
    - 假人：BotRunner 兩個（一個眼前有答題、一個閒著；簽到是同步時自動簽的，假人開工那天通常已經領了）；整季機器人站在答題的選單上挑哪一顆。沒有一條線的設定（none、weekend、
      test 的線關著）寫「沒有」，同一串 API 照打。"""

    QUIZ, DUELER, MIRROR, LATE, WALKER = "宋問津", "呂臨淵", "桑弄潮", "魏守拙", "周問舟"
    REST_A, REST_B, SIGNER, LAPSER, WALKER2 = "衛未央", "蔡留白", "祝延年", "范長歌", "杜歸舟"
    PLAYERS = {name: None for name in (QUIZ, DUELER, MIRROR, LATE, WALKER, REST_A, REST_B, SIGNER, LAPSER, WALKER2, "韓承業", "陸尋蹤")}
    NEWBIE = "穆安然"
    BOT_SEATS = ["線甲", "線乙"]
    REAL = "maier"
    # 審查修正（第 30 批）：投靠官軍走章回主線的人、探索擲中內容寫的線的人
    CHAPTER, EXPLORER = "韓承業", "陸尋蹤"
    PHASES_FIRST = ["setup", "sign_first", "quiz_first", "duel_first", "mirror_first", "late_first", "walk_first", "rest_open", "half"]
    PHASES_SECOND = ["resume", "quiz_on", "duel_on", "mirror_on", "late_on", "walk_on", "sign_on", "chapter_on", "explore_on", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.defs = self.story_defs()

    # ── 自己組的幾條線 ──

    def story_defs(self) -> dict:
        from tianxia.models import StoryAnswer, StoryDef, StoryEnding, StoryFail, StoryQuestion, StoryRoute, StoryStage

        squad = sorted(self.c.squads)[0] if self.c.squads else None

        def ask(text: str, left: str, right: str, marks=("攻", "守")):
            return StoryQuestion(text=text, answers=[StoryAnswer(text=left, marks={marks[0]: 1}), StoryAnswer(text=right, marks={marks[1]: 1})])

        def end(line: str, key: str, failed: bool = False, tail: str = ""):
            return StoryEnding(id=key, title=f"{key}的收場", text=f"{{?{line}.攻:你出手得多|你收手得多}}{{!{line}.守:，一路沒有退過}}。{tail}",
                               annal=f"{{name}}在{line}這件事上，{key}地收了場。", failed=failed, weight=3)

        def fail(line: str):
            return StoryFail(title="敗了一陣", card="你落敗退下，{days}後再來。", log="（落敗了，{days}後再試。）", annal=f"{{name}}在{line}落敗了一場。")

        return {
            "quiz": StoryDef(id="sb_quiz", title="山徑三問", intro="山徑口有人攔路，說要問你三件事。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="答完山徑上的三問", next="calm", routes=[StoryRoute(when={"攻": 2}, go="bold")],
                                                questions=[ask("第一問：路遇不平，你如何？", "拔刀相助", "繞道而行"),
                                                           ask("第二問：有人託你送一封信，你如何？", "當場拆開", "原封送到"),
                                                           ask("第三問：夜裡有人敲門，你如何？", "開門去看", "吹燈裝睡")])],
                             endings=[end("sb_quiz", "bold"), end("sb_quiz", "calm")]),
            "duel": StoryDef(id="sb_duel", title="渡口一戰", intro="渡口有人等你比劃一場。",
                             stages=[StoryStage(id="fight", kind="fight", squad=squad, retries=2, hint="去渡口打一場", win="won", lose="lost", fail=fail("渡口"))],
                             endings=[end("sb_duel", "won"), end("sb_duel", "lost", failed=True)]),
            "mirror": StoryDef(id="sb_mirror", title="鏡中人", intro="水裡的人跟你長得一模一樣。",
                               stages=[StoryStage(id="fight", kind="fight", mirror=0.4, mirror_name="鏡中人", mirror_weaken=0.05, mirror_floor=0.1, retries=4,
                                                  hint="面對鏡中人", win="won", lose="lost", fail=fail("鏡邊"))],
                               endings=[end("sb_mirror", "won"), end("sb_mirror", "lost", failed=True)]),
            "late": StoryDef(id="sb_late", title="限期之約", intro="對方說，過了期限就不候了。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="趕在期限之前", days=0.5, late="gone", next="done",
                                                questions=[ask("你赴約嗎？", "赴約", "不赴")])],
                             endings=[end("sb_late", "done"), end("sb_late", "gone", failed=True)]),
            "open": StoryDef(id="sb_open", title="未了之事", intro="有一件事擱在心上。", unfinished="{name}擱在心上的一件事，到季末還沒有了結。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="想一想", next="done", questions=[ask("你怎麼想？", "放下", "不放")])],
                             endings=[end("sb_open", "done")]),
        }

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
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

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def lines_on(self) -> bool:
        from tianxia.rules import jianfa

        return bool(jianfa(self.c, self.world.get_season(), "storylines"))

    def signing_on(self) -> bool:
        from tianxia import checkin

        return bool(checkin.on(self.c, self.world.get_season()))

    def me(self, who: str, tag: str) -> None:
        """存檔裡這兩包碰得到的那幾格：所在、一條線的進度與跳出來的卡、答題開著的那一條、紀念物與跨季旗標、簽過的日子與挑的四階、丹與銀兩、體力、
        行狀、最新三則紀錄、眼前的事件。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "lines": {k: v.model_dump(mode="json", exclude={"custom"}) | {"custom": None if v.custom is None else v.custom.kind}
                      for k, v in sorted(p.storylines.items())}, "open": p.story_open,
            "cards": [x.model_dump(mode="json") for x in p.story_cards], "keepsakes": list(p.keepsakes), "lasting": list(p.lasting),
            "checkin": [list(p.checkin_days), dict(sorted(p.checkin_picks.items()))], "pills": p.stamina_pills, "silver": p.stats.get("silver", 0),
            "stamina": p.stamina, "event": state.pending_event, "annals": [[a.kind, a.text] for a in p.annals],
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def begin_line(self, who: str, key: str) -> None:
        """程式組的線從 Game.story_start 開（鎖裡讀存檔、開、存回；線關著的設定回空的什麼都不動）。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            state = self.chars.load(who)
            state.world = self.world.get_season()
            game = Game(self.c, state, world=self.world)
            msgs = game.story_start(self.defs[key])
            self.chars.save(game.state)
        emit(f"{who} 開線 {key}", msgs)

    def press(self, who: str, line: str, tag: str) -> None:
        """按選單上「未了之事」那一顆（story:<線>；灰著照按，被擋的那一句也要寫出來）。"""
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith("story:")])
        if f"story:{line}" in opts:
            self.choose(who, f"story:{line}")
        else:
            emit(f"{who} {tag} 選單上沒有 story:{line}", None)

    def answer(self, who: str, line: str, arg: str, tag: str) -> None:
        self.choose(who, f"story:{line}:{arg}")
        self.me(who, tag)

    def seen(self, who: str, tag: str) -> None:
        self.do(who, "story_seen")
        self.me(who, tag)

    def retry_now(self, who: str, line: str) -> None:
        """打輸了要等的時候擺成到了（retry_at 回到過去）。"""
        def fn(s):
            progress = s.player.storylines.get(line)
            if progress is not None:
                progress.retry_at = 0.0
        self.edit_state(who, fn)

    def mirror_power(self, who: str) -> None:
        """影子此刻的難度（Game._mirror_squad，輸過幾次削幾次）。"""
        from tianxia import storyline
        from tianxia.engine import Game

        self.begin()
        state = self.chars.load(who)
        state.world = self.world.get_season()
        progress = state.player.storylines.get("sb_mirror")
        pair = None if progress is None else storyline.current(self.c, progress)
        if pair is None:
            emit(f"{who} 影子難度", None)
            return
        emit(f"{who} 影子難度", Game(self.c, state, world=self.world)._mirror_squad(progress, pair[1]).difficulty)

    def walk(self, who: str, rounds: int) -> None:
        """長篇奇事往下走：多日段等完（entered 往前挪）、站到這一段做得了的地方、眼前有事件就選第一個亮的、沒有就按「未了之事」那一顆。"""
        from tianxia import storyline

        for _ in range(rounds):
            state = self.chars.load(who)
            live = storyline.active(state)
            if not live:
                emit(f"{who} 沒有還沒收的線", None)
                return

            def age(s):
                for pr in storyline.active(s):
                    if pr.entered is not None:
                        pr.entered -= 1.0e9
            self.edit_state(who, age)
            pair = storyline.current(self.c, live[0])
            where = pair[1].where.locations if pair is not None else []
            if where and not state.pending_event and state.player.location not in where:
                self.place(who, where[0])
            opts = self.options(who)
            pick = next((i for i, o in opts.items() if i.startswith("choice:") and o.get("enabled")), None) or next(
                (i for i, o in opts.items() if i.startswith("story:") and o.get("enabled")), None)
            if pick is None:
                emit(f"{who} 此刻沒有可按的", [[i, o.get("enabled")] for i, o in opts.items()])
                return
            self.choose(who, pick)
        self.me(who, f"走了 {rounds} 步")

    def forward_to(self, day: int) -> None:
        """管理者快轉（一天一天），快轉到簽到的第 day 天（沒有簽到的設定快轉同樣的天數）。"""
        from tianxia import checkin

        for _ in range(day):
            s = self.world.get_season()
            if checkin.on(self.c, s) and checkin.day_of(self.c, s) >= day:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        s = self.world.get_season()
        emit("簽到第幾天", checkin.day_of(self.c, s) if checkin.on(self.c, s) else None)

    def sign(self, who: str, attribute: str | None, tag: str) -> None:
        """/api/do/checkin（attribute 是四階挑的屬性；None 不帶），前後各看一次江湖頁的簽到小標。"""
        view = self.main(who)
        view = view.get("main", view) if isinstance(view, dict) else {}
        emit(f"{who} {tag} 之前的簽到小標", (view.get("status") or {}).get("checkin"))
        self.do(who, "checkin", {} if attribute is None else {"attribute": attribute})
        self.me(who, tag)

    # ── 前半 ──

    def quiz_first(self) -> None:
        """宋問津開山徑三問，答第一題停在答到一半。"""
        who = self.QUIZ
        self.begin_line(who, "quiz")
        self.main(who)
        self.press(who, "sb_quiz", "開頭")
        self.answer(who, "sb_quiz", "a0", "答了第一題")

    def duel_first(self) -> None:
        """呂臨淵打渡口落敗：灰著寫還要等多久、按灰的被擋。"""
        who = self.DUELER
        self.begin_line(who, "duel")
        self.main(who)
        with self.fights("落敗"):
            self.press(who, "sb_duel", "第一場")
        self.me(who, "落敗之後")
        self.press(who, "sb_duel", "還在等")
        self.me(who, "按灰的之後")

    def mirror_first(self) -> None:
        """桑弄潮打鏡中人，輸第一次。"""
        who = self.MIRROR
        self.begin_line(who, "mirror")
        self.main(who)
        self.mirror_power(who)
        with self.fights("落敗"):
            self.press(who, "sb_mirror", "第一次")
        self.me(who, "輸了第一次")
        self.mirror_power(who)

    def late_first(self) -> None:
        who = self.LATE
        self.begin_line(who, "late")
        self.main(who)
        self.me(who, "只開了線")

    def walk_first(self) -> None:
        """周問舟在潁川荒野遇上賣兒契（內容寫的線）：走幾步停在半路。"""
        from tianxia import storyline

        who = self.WALKER
        line = self.c.storylines.get(self.REAL)
        if line is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        self.place(who, "runan_wilds")
        self.edit_state(who, lambda s: storyline.start(s, self.c, line, custom=False))
        self.me(who, "開了線")
        self.walk(who, 5)

    def rest_open(self) -> None:
        for who in (self.REST_A, self.REST_B):
            self.begin_line(who, "open")
            self.main(who)

    def sign_first(self) -> None:
        """祝延年、范長歌第 1 天自動領（先同步一下）、同一天再領一次（簽過了）；快轉到要挑四階的那一天，人都還沒領。"""
        for who in (self.SIGNER, self.LAPSER):
            self.main(who)
            self.sign(who, None, "第一天再領一次")
        self.forward_to(_STORY_CHECKIN_DAY)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def quiz_on(self) -> None:
        who = self.QUIZ
        self.answer(who, "sb_quiz", "a0", "答了第二題")
        self.answer(who, "sb_quiz", "later", "先擱著")
        self.main(who)
        self.press(who, "sb_quiz", "按回來")
        self.answer(who, "sb_quiz", "a1", "答完")
        self.seen(who, "收卡")
        self.choose(who, "story:sb_quiz:a9")
        self.choose(who, "story:nope")
        self.me(who, "答不在選單上的")

    def duel_on(self) -> None:
        who = self.DUELER
        self.retry_now(who, "sb_duel")
        with self.fights("大勝"):
            self.press(who, "sb_duel", "再打")
        self.me(who, "打贏之後")
        self.seen(who, "收卡")

    def mirror_on(self) -> None:
        who = self.MIRROR
        for tier in ("落敗", "大勝"):
            self.retry_now(who, "sb_mirror")
            self.mirror_power(who)
            with self.fights(tier):
                self.press(who, "sb_mirror", f"再打（{tier}）")
            self.me(who, f"{tier}之後")
        self.seen(who, "收卡")

    def late_on(self) -> None:
        """限期的線：先按一下看選單、把期限擺成過了，下一次同步往 late 走（失敗的結局入傳）。"""
        who = self.LATE

        def fn(s):
            progress = s.player.storylines.get("sb_late")
            if progress is not None:
                progress.due = 0.0
        self.edit_state(who, fn)
        self.main(who)
        self.me(who, "期限過了")
        self.seen(who, "收卡")

    def walk_on(self) -> None:
        """前半停在半路的周問舟過了期限（快轉了五天，賣兒契的期限早過了：往 late 走、收卡）；杜歸舟後半才在潁川書院遇上臥龍岡的地（內容寫的線），
        一路走完。"""
        from tianxia import storyline

        who, line = self.WALKER2, self.c.storylines.get("wolong")
        if line is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        self.walk(self.WALKER, 40)  # 前半停在半路（還在等的段、期限都跨過切點，審查修正），後半接著走完
        self.seen(self.WALKER, "收卡")
        self.place(who, "yingchuan_academy")
        self.edit_state(who, lambda s: storyline.start(s, self.c, line, custom=False))
        self.walk(who, 40)
        self.seen(who, "收卡")

    def chapter_on(self) -> None:
        """章回主線（審查修正）：投靠官軍、章回的線開了，照 walk 的走法按「未了之事」走事件段到 task 段（記帳、存季、chapter_beat 的登記時機）。
        沒有陣營的設定寫「沒有」。"""
        who = self.CHAPTER
        factions = {f.id: f for f in self.c.scenario.factions}
        side = factions.get("guan")
        if side is None or not side.join_at or not self.lines_on():
            emit(f"{who} 這一季沒有章回主線", None)
            return
        self.place(who, side.join_at[0])
        self.choose(who, "faction:guan")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        self.place(who, None)
        self.me(who, "投靠之後")
        self.walk(who, 24)
        self.seen(who, "收卡")

    def explore_on(self) -> None:
        """探索擲中內容寫的線（審查修正，Game._story_begin 的委派）：把長篇奇事開頭的機率擺成 1，站到開頭的地方按探索（三選一開著的季再挑一顆）。"""
        who = self.EXPLORER
        line = self.c.storylines.get(self.REAL)
        if line is None or line.start is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        where = line.start.where
        spot = next(iter(where.locations), None) if where is not None else None
        if spot is None or not self.place(who, spot):
            emit(f"{who} 開頭的地方站不到", None)
            return
        chance = line.start.chance
        line.start.chance = 1.0
        try:
            self.choose(who, "act:explore")
            modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
            if modes:
                self.choose(who, next((m for m in modes if m == "explore:seek"), modes[0]))
        finally:
            line.start.chance = chance
        self.me(who, "探索之後")

    def sign_on(self) -> None:
        """要挑四階的那一天：祝延年不帶屬性（要先挑）、帶錯的、挑對的領了、再領（簽過了）；范長歌直接挑對；隔一天（普通日）自動領；過了最後一天。"""
        self.sign(self.SIGNER, None, "沒挑")
        self.sign(self.SIGNER, "無", "挑錯")
        self.sign(self.SIGNER, "剛", "挑對")
        self.sign(self.SIGNER, "剛", "再領一次")
        self.sign(self.LAPSER, "快", "直接挑對")
        self.do(ADMIN, "fast_forward", {"hours": 24})
        for who in (self.SIGNER, self.LAPSER):
            self.main(who)
            self.me(who, "隔天")

    def bots(self) -> None:
        """假人：BotRunner 兩個（線甲按過「未了之事」、眼前是答題，線乙閒著；簽到是同步時自動簽的）若干輪；整季機器人站在答題的選單上挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        start = next((i for i in ("yingchuan", "town") if i in self.c.locations), sorted(self.c.locations)[0])
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=81 + i, faction=sides[i % 2] if sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, start, None
            p.visited.add(start)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            if i == 0:
                emit(f"{name} 開線", g.story_start(self.defs["open"]))
                emit(f"{name} 按了未了之事（眼前是答題）", g.choose("story:sb_open"))
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(19), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_STORY_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("線假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"線假人 {name}", {"lines": {k: [v.stage, v.ending, v.step] for k, v in sorted(p.storylines.items())}, "open": p.story_open,
                                    "checkin": list(p.checkin_days), "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        solo = Game.new(self.c, "線丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        solo.state.player.tutorial_step = len(self.c.tutorial.steps)
        emit("整季機器人開線", solo.story_start(self.defs["quiz"]))
        emit("整季機器人先按未了之事", solo.choose("story:sb_quiz"))  # 眼前是第一題：選單只剩三個答案（先擱著機器人不按）
        for step in range(8):
            opts = solo.options(odds=False)
            emit("整季機器人眼前的選單", [o.id for o in opts])
            emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
            picked = bot.pick(solo, opts, random.Random(step))
            if picked is None or picked == "act:on_road":
                break
            solo.choose(picked)
            emit("整季機器人按了", [picked, sorted(solo.state.player.storylines), solo.state.player.story_open])

    def season(self) -> None:
        """再快轉兩天（七天的季過了最後一天、二十一天的季只是第 9 天：簽到小標沒有或照常），收季、開下一季：衛未央收季之後同步一次（休季時寫此事未了、
        排卡）、蔡留白不同步（換季那一刻 close_season 補寫）；簽到的帳換季清掉。"""
        for _ in range(2):
            self.do(ADMIN, "fast_forward", {"hours": 24})
        for who in (self.SIGNER, self.LAPSER):
            self.sign(who, None, "又隔兩天")
        self.do(ADMIN, "end_season")
        self.main(self.REST_A)
        self.me(self.REST_A, "休季時同步過")
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "換季之後")


def _story_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _sense_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：選單上「未了之事」那一行的開頭（搬之前在 tianxia/storyline.py、之後在 tianxia/features/story/storyline.py）
_story_register_track("story", StoryScenario, (("tianxia/features/story/storyline.py", "tianxia/storyline.py"),
                                               ('PENDING_HEAD = "未了之事"', 'PENDING_HEAD = "未了之事！"')), "week7")


# ═══════════════════════════ explore（全部拆包第 18 批「探索三」，dev/explore-3）：roam 一軌 ═══════════════════════════
# 序章草廬四景與探索的底：權重（_explore_weights、_explore_can）、野怪（_wild_foes、_here_squads）、自家營寨跟同袍比劃（_drills_with）、
# 練功分級（_practice_tier）、撿破境丹（_legend_find）、舊探索本身（_explore、_explore_outcome；不帶設定、weekend、測試內容走它，
# season21、week7 走出門一趟）。計畫 docs/superpowers/plans/2026-11-04-探索包-第3批.md。名字一律原創（第 22 批認定第 3 條）。
# 這一段整塊是這一批的：接在檔尾、最後一行登記，PM 合的時候不跟別人的行穿插。


class RoamScenario(StripScenario):
    """探索三（全部拆包第 18 批；--track roam，自己一個資料庫）。小工具借拿掉一那一軌的（game、field、town、look_here、me 的位置、bots、season）
    與探索那一軌的（draws、fights、tweak、explore、settle、kind_places）。
    - 草廬（不帶、weekend）：阮青禾遇險、拜師、看修練頁，按探索——序章第 3 步（四景四選一的事件卡，或有所感版的卡）；這一下把破境丹的機率擺到 1，
      序章裡不撿（_explore 最前面那一條）。**前半停在卡上**（舊程式端出來的），後半新程式接著選。沒有草廬的季寫「沒有」。
    - 權重：每種地點、官軍、黃巾、散人各站一次——此刻站著哪幾路隊伍、哪幾路是自己人、野怪、三支的比重、做不做得了、分級，與選單、行動列底下那一行。
    - 野怪：城外按探索，舊探索這一下落在野怪那一支（_explore_weights 只回野怪；官軍打贏、黃巾落敗、散人照打）；出門一趟抽到遭遇。
    - 自家營寨：官軍站官軍的營寨、黃巾站黃巾的營寨（自己人不殺出來：舊探索一無所獲或別的支、出門一趟是跟同袍比劃）、官軍站黃巾的營寨。
    - 破境丹：機率 0／0.5／1（直接叫 _legend_find，連亂數序列一起寫）、帶寶物放大門檻、傳自己的亂數、真的按探索撿到。
    - 分級：每一處、三種身分的 _practice_tier；輿圖詳情最後那一句。
    - 假人、收季：借拿掉一那一軌的，換一批擺位（城外、官軍營寨、黃巾營寨、黃巾的祭壇）。"""

    BOT_SEATS = [("遊甲", "yingshui"), ("遊乙", "guan_camp"), ("遊丙", "huangjin_camp"), ("遊丁", "julu_altar")]
    PHASES_FIRST = ["setup", "weights", "wild", "camp", "legend", "grades", "hut"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]
    WHO = ("韓墨川", "蘇映秋", "杜遠山")  # 官軍、黃巾、散人

    # ── 小工具 ──

    @contextlib.contextmanager
    def only(self, branch: str):
        """舊探索這一下只落在這一支（Game._explore_weights 換掉；兩份程式都在 Game 上，同一步換、同一步換回）。出門一趟不讀它。"""
        from tianxia.engine import Game

        real = Game._explore_weights
        Game._explore_weights = lambda game, loc: [(branch, 1.0)]
        try:
            yield
        finally:
            Game._explore_weights = real

    def spots(self) -> list[str]:
        """各種地點一處、兩邊的營寨、兩軍混站的野地、官軍與散人混站的野地（這份內容沒有的略過）。"""
        out = [loc for _, loc in self.kind_places()]
        for loc in ("guan_camp", "huangjin_camp", "nanyang_wilds", "juma_river", "baima_ford"):
            if loc in self.c.locations and loc not in out:
                out.append(loc)
        return out

    def stand(self, who: str, loc: str, tag: str) -> None:
        """站在某處：此刻站著的隊伍、自己人、野怪、三支的比重與做不做得了、練功分級；再看選單與行動列底下那一行。"""
        self.place(who, loc)
        game = self.game(who)
        here = self.c.locations[game.state.player.location]
        # base 上是 Game 的方法，搬進包之後 Game 不留（只有包裡自己叫）：沒有就叫包裡那一支，兩邊算的是同一件事
        if hasattr(game, "_here_squads"):
            squads = game._here_squads(here.id)
        else:
            from tianxia.features.explore import explore_base
            squads = explore_base.here_squads(game, here.id)
        emit(f"{who} {tag} {here.id}", {
            "squads": squads, "own": [sid for sid in squads if game._drills_with(self.c.squads[sid])],
            "wild": [f.id for f in game._wild_foes(here)], "weights": game._explore_weights(here),
            "can": {b: game._explore_can(b, here) for b in ("insight", "wild", "event")}, "tier": game._practice_tier(here)})
        self.look_here(who, tag)

    def show_legend(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        emit(f"{who} {tag} 破境丹", {"items": p.legend_items, "explore_seq": p.explore_seq, "stamina": p.stamina})

    # ── 前半 ──

    def weights(self) -> None:
        """每種地點 × 官軍、黃巾、散人。"""
        for who in self.WHO:
            for loc in self.spots():
                self.stand(who, loc, "站著")

    def wild(self) -> None:
        """城外按探索：舊探索落在野怪那一支（打贏、落敗、照打）；出門一趟抽到遭遇。野怪帶不帶得出來都看真實的 _wild_foes。"""
        explore_one = _explore_rules()

        spot = self.field()
        for who, tier in (("蘇映秋", "大勝"), ("韓墨川", "落敗"), ("杜遠山", None)):
            self.place(who, spot)
            with self.only("wild"), self.draws(explore_one.ENCOUNTER), self.fights(tier):
                self.explore(who)
            self.me(who, "野怪之後")
        # 照真實的比重自己走（奇遇、頭目也擲）：每個身分在城外多走幾下
        for who in self.WHO:
            for k in range(3):
                self.place(who, spot)
                self.explore(who, k)
            self.me(who, "照真的走三下")

    def camp(self) -> None:
        """自家營寨（自己人不殺出來，跟同袍比劃）與對面的營寨。"""
        explore_one = _explore_rules()

        seats = (("韓墨川", "guan_camp"), ("蘇映秋", "huangjin_camp"), ("裴寒舟", "guan_camp"), ("韓墨川", "huangjin_camp"), ("蘇映秋", "guan_camp"))
        for who, loc in seats:
            if loc not in self.c.locations:
                emit(f"{who} {loc}（這份內容沒有）", None)
                continue
            for k in range(2):
                self.place(who, loc)
                with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                    self.explore(who, k)
                self.me(who, f"在 {loc} 第 {k + 1} 下")

    def legend_pick(self, who: str, chance: float, tag: str) -> None:
        explore_one = _explore_rules()

        self.place(who, self.field())
        with self.tweak(self.c.config, explore_legend_chance=chance), self.draws(explore_one.MATERIAL):
            self.explore(who)
        self.me(who, tag)
        self.show_legend(who, tag)

    def legend(self) -> None:
        """撿破境丹：真的按探索（機率 0／1／0.5）、直接擲、帶寶物、傳自己的亂數。"""
        import random as rnd
        from tianxia import treasures

        for pick, chance in (("沈晚舟", 0.0), ("顧行之", 1.0), ("裴寒舟", 0.5)):
            self.legend_pick(pick, chance, f"機率 {chance}")
        game = self.game("程聽雪")
        for chance in (0.0, 0.5, 1.0):
            with self.tweak(self.c.config, explore_legend_chance=chance):
                got = game._legend_find()
                emit(f"直接擲 機率 {chance}", {"got": got, "items": game.state.player.legend_items,
                                                  "rng": hashlib.sha256(repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]})
        fake = lambda st, ct, key: 2.0 if key == "legend" else 1.0  # noqa: E731
        with self.tweak(self.c.config, explore_legend_chance=0.3), self.tweak(treasures, amount=fake):
            for k in range(4):
                emit(f"帶寶物 第 {k + 1} 擲", {"got": game._legend_find(), "items": game.state.player.legend_items})
        with self.tweak(self.c.config, explore_legend_chance=0.5):
            for seed in (1, 2, 3, 4):
                before = hashlib.sha256(repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]
                emit(f"傳自己的亂數 {seed}", {"got": game._legend_find(rnd.Random(seed)), "own_rng_untouched": before == hashlib.sha256(
                    repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]})

    def grades(self) -> None:
        """每一處的分級（官軍、黃巾、散人各看一次：自己人不算對手）、輿圖詳情最後那一句。"""
        for who in self.WHO:
            game = self.game(who)
            emit(f"{who} 每一處的分級", {i: game._practice_tier(x) for i, x in sorted(self.c.locations.items())})
        spot = self.field()
        for who in self.WHO:
            status, view = self.call(who, "GET", f"/api/map?place={spot or ''}")
            game = self.game(who)
            emit(f"{who} 詳情", {"detail": view.get("detail") if isinstance(view, dict) else status,
                                 "text": game.place_detail(spot) if spot else None})

    def hut(self) -> None:
        """草廬（不帶、weekend）：遇險、拜師、看修練頁，按探索；破境丹的機率擺到 1，序章裡也不撿。**前半停在這一張卡上**。"""
        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        with self.tweak(self.c.config, explore_legend_chance=1.0):
            self.choose(who, "act:explore")
        self.me(who, "草廬探索這一下")
        self.show_legend(who, "草廬")
        view = self.main(who)
        emit("草廬卡上有哪些鈕", sorted(self.ids(view)))

    # ── 後半 ──

    def answer(self) -> None:
        """草廬那張卡：四景四選一挑最後一個（前半挑第一個的話這裡才有不一樣的路），或有所感版選第一個做法、順其自然。"""
        from tianxia import sensing

        who = self.NEWBIE
        opts = self.options(who)
        picks = [i for i, o in opts.items() if i.startswith("choice:") and o.get("enabled")]
        if picks:
            self.choose(who, picks[-1])
        else:
            senses = [i for i, o in opts.items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
            if senses:
                self.choose(who, senses[0])
            if sensing.LET_GO in self.options(who):
                self.choose(who, sensing.LET_GO)
        self.me(who, "草廬答完")
        self.show_legend(who, "草廬答完")
        self.main(who)

    def again(self) -> None:
        """接手之後：城外、官軍營寨、黃巾營寨各站一次再按探索。"""
        for who, loc in (("韓墨川", self.field()), ("蘇映秋", "huangjin_camp"), ("杜遠山", "guan_camp")):
            if loc is None or loc not in self.c.locations:
                continue
            self.stand(who, loc, "接手之後")
            self.explore(who)
            self.me(who, "接手之後探索")


_events_register_track("roam", RoamScenario, (("tianxia/features/explore/explore_base.py", "tianxia/engine.py"), ('一枚——{cfg.legend_item_note}', '一枚——{cfg.legend_item_note}！')), "week7")


# ═══════════════════════════ shut（全部拆包第 14 批「拿掉二」，dev/strip-2）：shut 一軌 ═══════════════════════════
# 週末設定、不帶設定的 14 天季只關門（計畫 docs/superpowers/plans/2026-11-04-拿掉二-第14批.md）。這一批不是純搬：week7、season21、test
# 三種設定要一個字都不變，none、weekend 之後不再是可以選的設定（same_behavior 的 PROFILES 跟著改）。這一軌盯的是「關門之後 week7、season21、
# test 還在讀」的那幾處：設定那一行與季長分岔的季曆（calendar、timetable：照現實天的程式碰上開季時沒蓋章的舊季，weekend_style）、
# 初入江湖兩步（e2_drill、e4_field）與舊步數的對應、新手目標 field2 的兩種字、h_field_lose 的提示、懸賞與序章裡「尋敵」「操練」的字。
# 名字一律原創（第 22 批認定第 3 條）。這一段整塊是這一批的：接在檔尾、最後一行登記，PM 合的時候不跟別人的行穿插。


class ShutScenario(StripScenario):
    """拿掉二（全部拆包第 14 批；--track shut，自己一個資料庫）。小工具借拿掉一那一軌的（game、me、look_here、field、town）。
    半舊半新切在 half 之後：三位新人的初入江湖寫到一半（舊步數 12 對到 e2_drill、e4_field 那一步、e6_shops 之後的一步）、一位練功輸了兩場
    等著提示，後半第一件事（answer）是新程式接著走。"""

    PLAYERS = {"閆臨淵": "guan", "秦明月": "huang", "魏無涯": None, "蕭半夏": None, "仲孫澈": "guan", "杜遠山": None}  # 杜遠山：field() 借拿掉一那一軌的小工具，要有這一位
    NEWBIE = "祁雪衣"
    NEWBIES = ["鄒白露", "宓清和", "祝融山"]  # 初入江湖寫到一半的三位（half 擺局面）
    BOT_SEATS = [("關甲", "yingshui"), ("關乙", "yingchuan"), ("關丙", "julu_altar"), ("關丁", "guangzong")]
    PHASES_FIRST = ["setup", "settings", "calendar_view", "old_season", "tutorial", "goals", "field_lose", "boards", "half"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]

    def fresh(self, who: str, gender: str = "男") -> None:
        """註冊一位新人、建角色（不略過引導）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": gender})

    # ── 前半 ──

    def settings(self) -> None:
        """設定那一行與季長分岔的設定值；季上蓋的章。"""
        from tianxia import content as content_rules

        cfg = self.c.config
        emit("設定那一行", content_rules.profile_line(self.c, None if self.profile in ("none", "test") else self.profile))
        emit("設定值", {k: getattr(cfg, k, None) for k in ("season_one", "season_days", "season21", "season_segments", "server_max_players",
                                                           "late_exp_step", "affinity_gain_scale", "beta_free_refill", "season_weeks")})
        season = self.world.get_season()
        emit("這一季的章", {k: getattr(season, k, None) for k in ("season_one", "season21", "ended", "season_number")})

    def calendar_view(self) -> None:
        """季曆與時刻表：這一季，各個時刻怎麼寫、時刻表每一件排在哪、開季設定對不上時的警告。"""
        from tianxia import calendar, timetable

        season = self.world.get_season()
        emit("季曆", {"weeks": calendar.weeks(self.c, season), "days": calendar.total_days(self.c, season),
                      "weekend_style": calendar.weekend_style(season, self.c), "warning": calendar.profile_warning(self.c, season),
                      "orders_daily": calendar.orders_daily(season, self.c), "words": calendar.week_words(self.c, season)})
        emit("每個時刻", [calendar.stamp_text(d * 86400 + h * 3600, self.c, season) for d in (0, 1, 2, 3, 5, 8, 13, 20) for h in (2, 15)])
        emit("每一週的字", [calendar.week_label(w, self.c, season) for w in range(1, calendar.weeks(self.c, season) + 1)])
        emit("時刻表", [(e.id, e.kind, e.week, round(timetable.when_in(season, self.c, e) - CLOCK0, 1)) for e in timetable.events(season, self.c)])
        emit("時刻表說明", [timetable.default_dates_note(self.c), timetable.mandate_note(self.c, season)])

    def old_season(self) -> None:
        """照現實天的程式碰上開季時沒蓋章的舊季（FB-635、FB-654：休季的舊季照它自己的季曆畫）：記憶體裡複製這一季，換掉章、標休季，
        問一遍季曆、時刻怎麼寫、時刻表每一件的發生時刻與週次（calendar.weekend_style、timetable.happened_at）。"""
        from tianxia import calendar, timetable

        season = self.world.get_season()
        for tag, update in (("舊季休季", {"season21": False, "ended": True}), ("舊季還在跑", {"season21": False, "ended": False}),
                            ("新季休季", {"ended": True})):
            old = season.model_copy(update=update)
            emit(f"{tag} 季曆", {"weekend_style": calendar.weekend_style(old, self.c), "weeks": calendar.weeks(self.c, old),
                                "days": calendar.total_days(self.c, old), "warning": calendar.profile_warning(self.c, old)})
            emit(f"{tag} 每個時刻", [calendar.stamp_text(d * 86400, self.c, old) for d in (0, 1, 3, 6, 9, 14)])
            emit(f"{tag} 時刻表", [(e.id, round(timetable.happened_at(old, self.c, e) - CLOCK0, 1), timetable.happened_week(old, self.c, e))
                                 for e in timetable.events(old, self.c)])

    def tutorial(self) -> None:
        """新人從頭走：第一眼的選單與說明，照第一個可按的選項往下走幾步（初入江湖的字）。內容裡的初入江湖步驟與提示也各列一遍。"""
        emit("引導的步驟", [(s.id, getattr(s, "kind", None)) for s in self.c.tutorial.steps])
        emit("提示", sorted(self.c.hints) if isinstance(self.c.hints, dict) else [h.id for h in self.c.hints.hints] if hasattr(self.c.hints, "hints")
             else None)
        who = "新客"  # NEWBIE 在 setup 註冊過了，再註冊會 400、後面全 401
        self.fresh(who)
        self.call(who, "GET", "/api/howto")
        for step in range(8):
            opts = self.ids(self.main(who))
            pick = next((i for i, o in sorted(opts.items()) if o.get("enabled") and not i.startswith(("act:rest", "move", "map"))), None)
            if pick is None:
                break
            self.choose(who, pick)
            self.settle_choices(who)
        self.me(who, "走了幾步")

    def goals(self) -> None:
        """新手目標：什麼都沒做、做了 field2、全做了；任務卡（/api/main 的 newbie）與 newbie_view 的字。"""
        who = "仲孫澈"
        for name in (who, "魏無涯", "蕭半夏"):  # 新手期裡才有這一塊（place 把加入時刻擺到很久以前，這裡擺回此刻）
            self.edit(name, lambda p: setattr(p, "joined_at", CLOCK[0]))
        emit(f"{who} 目標 開頭", self.game(who).newbie_view())
        self.edit(who, lambda p: (p.newbie_marks.add("field2"), p.newbie_done.add("field2")))
        emit(f"{who} 目標 field2", self.game(who).newbie_view())
        self.edit(who, lambda p: (p.newbie_marks.update(["level5", "merge", "create", "bounty", "tavern", "side", "arena"]),
                                  p.newbie_done.update(["level5", "merge", "create", "bounty", "tavern", "side", "arena"])))
        emit(f"{who} 目標 全做", self.game(who).newbie_view())
        self.main(who)
        for other in ("魏無涯", "蕭半夏"):
            emit(f"{other} 目標", self.game(other).newbie_view())
            self.call(other, "GET", "/api/howto")

    def field_lose(self) -> None:
        """h_field_lose（練功連輸兩場，僵持不算）：0、1、2 場落敗、再多一場僵持。每一步看 _hint_triggers，也走 /api/main 看提示框。"""
        from tianxia import training
        from tianxia.state import BattleRecord

        who = "蕭半夏"
        spot = self.field() or self.town()
        self.place(who, spot)

        def lose(tier: str):
            def fn(state):
                state.battles.insert(0, BattleRecord(id=len(state.battles) + 1, time=CLOCK[0], location="某處", kind="wild", label=training.PRACTICE,
                                                     opponent="某隊", ours=[], tier=tier, our_power=1.0, difficulty=2.0))
            return fn
        emit("沒輸", self.game(who)._hint_triggers({"h_field_lose", "h_lose"}))
        for tag, tier in (("輸一場", "落敗"), ("輸兩場", "落敗"), ("再一場僵持", "僵持")):
            self.edit_state(who, lose(tier))
            emit(tag, self.game(who)._hint_triggers({"h_field_lose", "h_lose"}))
            view = self.main(who)
            emit(f"{tag} 提示框", [view.get("guide") if isinstance(view, dict) else None, self.game(who).guide_box()])

    def boards(self) -> None:
        """榜（懸賞榜的「尋敵」「操練」字）：城裡、城外各看一次；有陣營的、散人。"""
        for who in ("閆臨淵", "魏無涯"):
            for where in filter(None, (self.town(), self.field())):
                self.place(who, where)
                self.call(who, "GET", "/api/boards")
                self.look_here(who, f"在{where}")

    def half(self) -> None:
        """切點：三位新人把 tutorial_step 手擺到 e2_drill、e4_field、e3_cultivate（步數 13）寫到一半，只看第一眼；後半再往下走。舊步數對應表（onboarding < 5）這一軌沒走到，真的新人建角色直接是 18。"""
        steps = [s.id for s in self.c.tutorial.steps]
        picks = [12, steps.index("e4_field") if "e4_field" in steps else len(steps) - 1, 13]
        for who, step in zip(self.NEWBIES, picks):
            self.fresh(who, "女")
            self.edit_state(who, lambda st: setattr(st, "pending_event", None))  # 開局端出來的那張卡先放掉
            self.edit(who, lambda p, step=step: (setattr(p, "tutorial_step", step), setattr(p, "location", self.town() or p.location),
                                                 p.visited.add(p.location)))  # 出了草廬（初入江湖的步驟在城裡才算）
            view = self.main(who)
            emit(f"{who} 切點", {"step": self.chars.load(who).player.tutorial_step, "options": sorted(self.ids(view)),
                               "guide": self.game(who).guide_box()})

    # ── 後半 ──

    def answer(self) -> None:
        """新程式接著走完那三位的初入江湖：第一個可按的選項往下，最多六步。"""
        for who in self.NEWBIES:
            for _ in range(6):
                opts = self.ids(self.main(who))
                pick = next((i for i, o in sorted(opts.items()) if o.get("enabled") and not i.startswith(("act:rest", "move", "map"))), None)
                if pick is None:
                    break
                self.choose(who, pick)
                self.settle_choices(who)
            self.me(who, "接手之後")

    def again(self) -> None:
        """接手之後再走一遍：設定那一行、季曆、新手目標、提示。"""
        self.settings()
        self.calendar_view()
        self.goals()
        self.field_lose()

    def season(self) -> None:
        """收季、開下一季：新的一季蓋章之後的設定、季曆與說明；新人的目標與選單。"""
        self.do(ADMIN, "end_season")
        self.main("魏無涯")
        self.do(ADMIN, "next_season")
        self.settings()
        self.calendar_view()
        for who in ("魏無涯", "仲孫澈", self.NEWBIE):
            self.look_here(who, "換季之後")
            self.call(who, "GET", "/api/howto")
            emit(f"{who} 換季之後的目標", self.game(who).newbie_view())


_events_register_track("shut", ShutScenario, (("tianxia/features/guide/newbie.py", "tianxia/newbie.py"),
                                              ("到匪寇橫行的地方出門探索，打贏一場", "到匪寇橫行的地方出門探索，打贏兩場")), "week7")


# ═══════════════════════════ figact：大勢人物的行動（全部拆包第 31 批，dev/figure-acts-1） ═══════════════════════════
# 挑戰大勢人物本人（Game 上 _challenge 等 13 個）、護衛犒軍探望（aid:，figure_aid）、助他一臂或壞他的事（plan:）、月旦評（yuedan）、管理者救回人物
# 搬進新包 tianxia/features/figure_acts/（舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後一行登記（_figact_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

FIGACT_YUE = "少年英發，前程無量"  # 假模型寫的月旦評（八到十六字，不含名號）
_FIGACT_CLIENTS: dict[type, type] = {}


def _figact_client(base: type) -> type:
    """月旦評的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["yuedan"] 給了（"all"＝每個人都寫、"mixed"＝第二個人寫太短）時，
    YuedanBatch 照名單回評語；其餘照 base（丟連線錯誤，月旦評照固定句發）。"""
    if base not in _FIGACT_CLIENTS:
        class FigActClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "YuedanBatch" and MODEL.get("yuedan"):
                    import re

                    names = re.findall(r"^\d+\. (.+?)（", messages[-1]["content"], re.M)
                    lines = [{"name": n, "line": "太短" if MODEL["yuedan"] == "mixed" and i == 1 else FIGACT_YUE} for i, n in enumerate(names)]
                    return schema.model_validate({"lines": lines})
                return super().chat_structured(messages, schema, *a, **k)

        _FIGACT_CLIENTS[base] = FigActClient
    return _FIGACT_CLIENTS[base]


class FigActScenario(Scenario):
    """大勢人物的行動（全部拆包第 31 批；--track figact，自己一個資料庫）。
    挑戰本人（官軍大本營「常社」的皇甫嵩，黃巾的人挑他）：封雲舟打贏（模型判讀回了；寶物、三階、四階的機會調成必中；他敗走、情誼、聲威、閉門不見、
    戰報與江湖紀錄）、同一天再打贏一次（聲威一天只扣一次）、閉門不見時按灰鈕；寧無咎打成僵持、岳臨風落敗、尹疏桐在模型叫不動時打贏；選單上的勝算與灰鈕、
    官軍的人看不到挑戰鈕、散人沒有陣營沒有鈕。護衛犒軍探望（aid:）：葛望之護衛皇甫嵩、紀長庚來挑戰被護衛擋下或闖過；莊子衿犒軍（聲威被打掉才有）；
    魏敬之在官軍大本營探望退場等著回來的朱儁（朱儁是內容表上的人，這裡直接擺成退場）；黃巾的人看不到護衛鈕；護衛下線時替人物擋下的挑戰，回來同步補名望與心得。
    助他一臂與壞他的事（plan:）：擺一件開著的盤算（孫堅在宛城），蘇引鳳（官軍，只能助他）、段無咎（黃巾，只能壞他）、何不言（散人，兩樣都行）、
    重複、不在那裡；**前半停在助他一臂還沒結**（盤算還沒到點），後半快轉過了到點，結果進同步的紀錄。
    月旦評（A 鎖內拿單子、B 鎖外請模型、C 鎖內重驗才發）：快轉到第 2 週自然評一批，**前半停在寫到一半**（單子在、還沒寫）；後半先在模型叫不動時發（固定句）、
    再擺一批在模型回了時發（有一句寫太短退回固定句）、再擺一批等太久照固定句發；玩家卡上的評語。管理者救回人物（叫回選單、救回、沒退場的、不是管理者）。
    假人：BotRunner 兩個（官軍，站在常社；bot_policy.score 問 aid:、體力花不完時 _stamina_play 挑 aid:）；整季機器人在常社的選單（aid:、act:challenge: 都不按）；換季。
    沒有大勢人物的內容（測試內容）、護衛犒軍關著的設定，同一串 API 照打，寫「沒有」。"""

    GUAN_HALL = "changshe"  # 官軍的皇甫嵩一開始就在這裡（時刻表的季是波才先到；seat 依此刻誰在哪挑一處兩軍都有人物的地點）
    HUANG_WIN, HUANG_WIN2, HUANG_DRAW, HUANG_LOSE, HUANG_DEAD = "封雲舟", "寧無咎", "岳臨風", "尹疏桐", "紀長庚"
    GUARD, RALLIER, VISITOR = "葛望之", "莊子衿", "魏敬之"
    GUAN_PEER = "沈夜航"  # 官軍的人去挑戰同陣營的人物：沒有鈕
    HELPER, BLOCKER, FREE = "蘇引鳳", "段無咎", "何不言"
    VIEWER, STRANGER = "謝臨川", "鄭無雙"  # 月旦評：玩家卡的看的人、被評到的人（跟看的人站在同一處）
    PLAYERS = {HUANG_WIN: "huang", HUANG_WIN2: "huang", HUANG_DRAW: "huang", HUANG_LOSE: "huang", HUANG_DEAD: "huang",
               GUARD: "guan", RALLIER: "guan", VISITOR: "guan", GUAN_PEER: "guan", HELPER: "guan", BLOCKER: "huang", FREE: None,
               VIEWER: None, STRANGER: None}
    BOT_SEATS = ["人甲", "人乙"]
    PHASES_FIRST = ["setup", "seat", "challenge", "guarded", "rally_visit", "yuedan_open", "plan_open", "half"]
    PHASES_SECOND = ["resume", "plan_settle", "yuedan_on", "admin", "bots", "season"]

    hall = GUAN_HALL
    foe, bocai_side, friend, fallen = "nobody", "nobody", "nobody", "nobody"  # seat 挑：黃巾的人挑誰、官軍的人挑誰、護衛犒軍誰、退場等著回來的是誰
    plan_stop, plan_who, plan_place = "nobody", "nobody", None

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _figact_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        self.c.config.figure_life.yuedan_wait_seconds = 10 ** 9  # 等太久照固定句發：預設的 900 世界秒幾步就到了，這裡先壓住，要的那一段再調

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    @contextlib.contextmanager
    def tuned(self, owner=None, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config if owner is None else owner
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {k: v for k, v in values.items()})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
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
    def drops(self):
        """寶物、三階、四階的機會調成必中（一人一季的上限照設定）。"""
        cfg = self.c.config
        before = (cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance)
        cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance = 1.0, 1.0, 1.0
        emit("掉落機會調成必中", None)
        try:
            yield
        finally:
            cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance = before

    def game(self, who: str):
        """鎖外只讀的一份 Game（讀選單、算勝算；不存檔）。"""
        from tianxia.engine import Game

        self.begin()
        state = self.chars.load(who)
        state.world = self.world.get_season()
        return Game(self.c, state, world=self.world)

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    def edit_world(self, fn) -> None:
        self.world.mutate_season(fn)

    def on(self) -> bool:
        """這份內容有大勢人物、有陣營（挑戰本人看這個）。"""
        return bool(self.c.figures) and bool(self.c.scenario.factions)

    def base_of(self, faction: str) -> str | None:
        f = self.c.scenario.find_faction(faction)
        return f.join_at[0] if f is not None and f.join_at else None

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、體力銀兩心得名望、打贏他幾次、這一季掉過什麼（寶物、三四階）、閉門不見、擾亂一天一次的帳、情誼、背包裡三四階素材、
        行狀、最新三則紀錄、最新一場戰報。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        mats = self.c.materials
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "stamina": p.stamina, "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0),
            "fame": p.stats.get("fame", 0), "wins": dict(sorted(p.figure_wins.items())), "rare": p.figure_rare_drops,
            "tier3": dict(sorted(p.tier3_drops.items())), "tier4": [list(p.tier4_wins), p.tier4_challenge_drops],
            "treasure": sorted(p.treasure_drops), "snub": dict(sorted(p.snubbed_until.items())), "dented": dict(sorted(p.figure_dented.items())),
            "aff": dict(sorted(p.affinities.items())), "mats": {k: v for k, v in sorted(p.materials.items()) if v > 0 and k in mats and mats[k].tier >= 3},
            "annals": [[a.kind, a.text] for a in p.annals][-4:], "journal": [[e.title, e.tag, list(e.lines)[:5]] for e in state.journal[:3]],
            "battle": None if not state.battles else state.battles[-1].model_dump(mode="json")})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：人物的聲威與狀態、站崗的護衛、犒軍探望的次數帳、盤算、月旦評、補給護衛的那幾句、世界旗標、最新天下大事與江湖史。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "figures": {k: v.model_dump(mode="json") for k, v in sorted(w.figures.items())},
            "guards": [g.model_dump(mode="json") for g in w.figure_guards], "tally": dict(sorted(w.aid_tally.items())),
            "credits": {k: list(v) for k, v in sorted(w.guard_credits.items())}, "plans": [x.model_dump(mode="json") for x in w.plans],
            "yuedan": [x.model_dump(mode="json") for x in w.yuedan], "yuedan_week": w.yuedan_week, "flags": sorted(getattr(w, "flags", []) or []),
            "rumors": [r.text for r in w.rumors][-4:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def week_of(self) -> int:
        from tianxia import calendar

        s = self.world.get_season()
        return calendar.point(s.time, self.c, s).week

    def forward_to_week(self, week: int) -> None:
        """管理者快轉（一天一天）到季曆第 week 週（季不夠長就快轉到頭）。"""
        for _ in range(40):
            if self.week_of() >= week:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        emit("季曆第幾週", self.week_of())

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        opts = self.options(who)
        have = opts.get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> None:
        """選單上這幾種開頭的選項（id、字、灰不灰）。"""
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])

    # ── 前半 ──

    def seat(self) -> None:
        """挑一處兩軍都有人物的地點（此刻誰在哪看存檔：時刻表的季波才先在常社，其他季皇甫嵩在）：黃巾的人在那裡挑官軍的人物、官軍的人挑黃巾的人物，
        官軍的人在那裡護衛、犒軍；探望的人站官軍的報到處，退場等著回來的是另一位官軍人物；盤算的人之後再站過去。"""
        from tianxia import figures

        g = self.game(self.VIEWER)
        c = self.c
        best = None
        for loc in sorted(c.locations):
            ids = figures.present_at(g.state, c, loc)
            guan = [f for f in ids if c.figures[f].faction == "guan" and figures.can_challenge(g.state, c, f)]
            huang = [f for f in ids if c.figures[f].faction == "huang" and figures.can_challenge(g.state, c, f)]
            score = (bool(guan) + bool(huang), loc == self.GUAN_HALL)
            if (guan or huang) and (best is None or score > best[0]):
                best = (score, loc, guan, huang)
        if best is not None:
            _, self.hall, guan, huang = best
            self.foe = ("huangfusong" if "huangfusong" in guan else guan[0]) if guan else "nobody"
            self.bocai_side = huang[0] if huang else "nobody"
            self.friend = self.foe if self.foe != "nobody" else next((f for f in figures.present_at(g.state, c, self.hall) if c.figures[f].faction == "guan"), "nobody")
            self.fallen = next((f for f, d in c.figures.items() if d.faction == "guan" and f != self.friend), "nobody")
        emit("挑的地點與人物", {"hall": self.hall, "foe": self.foe, "bocai_side": self.bocai_side, "friend": self.friend, "fallen": self.fallen})
        for who, side in self.PLAYERS.items():
            if who == self.VISITOR:
                self.place(who, self.base_of("guan") or self.hall, side)
            else:
                self.place(who, self.hall, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        emit("大勢人物表", {"on": self.on(), "aid": self.c.config.figure_aid.enabled, "plans": self.c.config.plans.enabled,
                           "yuedan": self.c.config.figure_life.yuedan})
        self.world_view("開場")

    def yuedan_open(self) -> None:
        """快轉到第 2 週：月旦評跨進新的一週自然評一批（單子在、還沒寫）；前半就停在這個狀態。"""
        self.forward_to_week(2)
        for who in (self.VIEWER, self.STRANGER, self.HUANG_WIN):
            self.main(who)
        self.world_view("第 2 週")

    def challenge(self) -> None:
        """挑戰皇甫嵩：選單、勝算、打贏（掉落必中）、閉門不見、同一天再打贏、僵持、落敗、模型叫不動時打贏；官軍的人與散人看不到鈕。"""
        fid = self.foe
        for who in (self.HUANG_WIN, self.GUAN_PEER, self.FREE):
            self.main(who)
            self.menu(who, "挑戰之前", "act:challenge:")
            self.me(who, "挑戰之前")
        # 打贏
        MODEL["judge"] = True
        try:
            with self.fights("大勝"), self.drops():
                self.press(self.HUANG_WIN, f"act:challenge:{fid}", "打贏")
        finally:
            MODEL["judge"] = False
        self.me(self.HUANG_WIN, "打贏之後")
        self.world_view("打贏之後")
        self.menu(self.HUANG_WIN, "閉門不見", "act:challenge:")
        with self.fights("大勝"):
            self.press(self.HUANG_WIN, f"act:challenge:{fid}", "閉門不見硬按")
        # 閉門不見解了（擺成到了）再打贏：同一天聲威不再扣
        self.edit(self.HUANG_WIN, lambda p: p.snubbed_until.clear())
        with self.fights("險勝"), self.drops():
            self.press(self.HUANG_WIN, f"act:challenge:{fid}", "解了之後再贏")
        self.me(self.HUANG_WIN, "再贏之後")
        # 僵持、落敗
        with self.fights("僵持"):
            self.press(self.HUANG_WIN2, f"act:challenge:{fid}", "僵持")
        self.me(self.HUANG_WIN2, "僵持之後")
        with self.fights("落敗"):
            self.press(self.HUANG_DRAW, f"act:challenge:{fid}", "落敗")
        self.me(self.HUANG_DRAW, "落敗之後")
        # 模型叫不動（判讀走固定句）
        with self.fights("大勝"), self.drops():
            self.press(self.HUANG_LOSE, f"act:challenge:{fid}", "沒有判讀打贏")
        self.me(self.HUANG_LOSE, "沒有判讀打贏之後")
        # 官軍的人挑黃巾的人物（含打贏之後的敗走，另一個方向）
        with self.fights("大勝"), self.drops():
            self.press(self.GUAN_PEER, f"act:challenge:{self.bocai_side}", "官軍打贏黃巾的人物")
        self.me(self.GUAN_PEER, "官軍打贏之後")
        # 清單外：不在這裡的人物、沒有的人物
        self.choose(self.HUANG_LOSE, f"act:challenge:{self.bocai_side}")  # 同陣營的人物：打不得
        self.choose(self.HUANG_LOSE, "act:challenge:nobody")
        self.world_view("挑戰之後")

    def guarded(self) -> None:
        """護衛：葛望之護衛皇甫嵩（再按一次是灰的）；黃巾的人看不到護衛鈕；紀長庚來挑戰，護衛擋下或闖過；下線時替人物擋下的挑戰，回來同步補名望與心得。"""
        fid = self.friend
        self.main(self.GUARD)
        self.menu(self.GUARD, "護衛之前", "aid:")
        self.press(self.GUARD, f"aid:guard:{fid}", "護衛")
        self.menu(self.GUARD, "護衛之後", "aid:")
        self.press(self.GUARD, f"aid:guard:{fid}", "再護衛一次")
        self.me(self.GUARD, "護衛之後")
        def harden(s) -> None:
            for post in s.figure_guards:
                post.power = 1.0e9

        self.edit_world(harden)  # 護衛的身手壓到最高：第一個來的過不去
        self.menu(self.HUANG_DEAD, "黃巾的人", "aid:", "act:challenge:")
        with self.fights("大勝"):
            self.press(self.HUANG_DEAD, f"act:challenge:{fid}", "被護衛擋")
        self.me(self.HUANG_DEAD, "被護衛擋之後")
        def weaken(s) -> None:
            for post in s.figure_guards:
                post.power = 1.0

        self.edit_world(weaken)  # 護衛的身手壓到最低：下一個來的闖得過去（那一班散、打到他本人）
        with self.fights("大勝"):
            self.press(self.HUANG_WIN2, f"act:challenge:{fid}", "闖護衛")
        self.me(self.HUANG_WIN2, "闖護衛之後")
        self.world_view("護衛之後")
        self.main(self.GUARD)  # 回來同步：補名望、心得
        self.me(self.GUARD, "回來同步")
        # 清單外的 aid:
        for bad in ("aid:guard:nobody", "aid:guard:", f"aid:wave:{fid}", f"aid:rally:{self.bocai_side}"):
            self.choose(self.GUARD, bad)

    def rally_visit(self) -> None:
        """犒軍（聲威被打掉了才有；扣體力、銀兩，補到一天的上限）、同一天再犒；探望（官軍報到處，退場等著回來的朱儁；一天一次）。"""
        fid = self.friend
        self.menu(self.RALLIER, "犒軍之前", "aid:")
        self.press(self.RALLIER, f"aid:rally:{fid}", "犒軍")
        self.press(self.RALLIER, f"aid:rally:{fid}", "再犒一次")
        self.me(self.RALLIER, "犒軍之後")
        self.world_view("犒軍之後")
        # 朱儁退場等著回來
        from tianxia.state import FigureState

        def fall(s) -> None:
            if self.fallen in self.c.figures:
                fs = s.figures.get(self.fallen) or FigureState(prestige=0)
                fs.prestige, fs.status, fs.front, fs.location = 0, "retired", None, ""
                fs.back_at, fs.back_front = s.time + 100 * 3600, "yingru"
                s.figures[self.fallen] = fs

        self.edit_world(fall)
        self.main(self.VISITOR)
        self.menu(self.VISITOR, "探望之前", "aid:")
        self.press(self.VISITOR, f"aid:visit:{self.fallen}", "探望")
        self.press(self.VISITOR, f"aid:visit:{self.fallen}", "再探望一次")
        self.press(self.VISITOR, "aid:visit:nobody", "探望沒有的人")
        self.me(self.VISITOR, "探望之後")
        self.world_view("探望之後")

    def plan_open(self) -> None:
        """第 2 週這一刻自然開著的一件盤算（內容的行程到了公告的時候；沒有就擺一件）：站對邊的人助他一臂、站錯邊的人按助他一臂被擋、散人壞他的事、重複、
        插過手又按另一顆、不在那裡、沒有這一件；**前半停在助他一臂還沒結**（到點還要一陣子）。"""
        from tianxia.state import Plan

        s = self.world.get_season()
        pair = None
        for plan in s.plans:
            found = next(((it, st) for it in self.c.itineraries for st in it.stops if st.id == plan.stop and st.contest), None)
            if not plan.settled and found is not None and plan.place in self.c.locations:
                pair, self.plan_stop, self.plan_who, self.plan_place = found, plan.stop, plan.who, plan.place
                break
        if pair is None:
            pair = next(((it, st) for it in self.c.itineraries for st in it.stops if st.contest and st.place in self.c.locations), None)
            if pair is None:
                emit("這份內容沒有盤算", None)
                return
            self.plan_who, self.plan_stop, self.plan_place = pair[0].who, pair[1].id, pair[1].place

            def seed(w) -> None:
                w.plans = [x for x in w.plans if x.stop != self.plan_stop]
                w.plans.append(Plan(stop=self.plan_stop, who=self.plan_who, place=self.plan_place, open_at=w.time, due=w.time + 12 * 3600))

            self.edit_world(seed)
        side = pair[1].contest.side
        emit("盤算", {"stop": self.plan_stop, "who": self.plan_who, "place": self.plan_place, "side": side})
        ally, wrong = (self.HELPER, self.BLOCKER) if side == "guan" else (self.BLOCKER, self.HELPER)
        for who in (ally, wrong, self.FREE):
            self.place(who, self.plan_place)
        for who in (ally, wrong, self.FREE):
            self.main(who)
            self.menu(who, "盤算之前", "plan:")
        stop = self.plan_stop
        self.press(ally, f"plan:help:{stop}", "助他一臂")
        self.press(ally, f"plan:help:{stop}", "助他一臂（重複）")
        self.press(ally, f"plan:block:{stop}", "壞他的事（插過手了）")
        self.press(wrong, f"plan:help:{stop}", "站錯邊助他一臂")
        self.press(self.FREE, f"plan:block:{stop}", "散人壞他的事")
        self.choose(self.FREE, "plan:help:nobody")
        self.place(self.GUARD, self.hall)
        self.choose(self.GUARD, f"plan:help:{stop}")  # 不在那裡
        for who in (ally, wrong, self.FREE):
            self.menu(who, "盤算之後", "plan:")
            self.me(who, "盤算之後")
        self.world_view("盤算還沒結")

    PICKS = ("hall", "foe", "bocai_side", "friend", "fallen", "plan_stop", "plan_who", "plan_place")

    def half(self) -> None:
        for who in [*self.PLAYERS, ADMIN]:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".figact.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".figact.json").read_text(encoding="utf-8")).items():  # 前半挑的地點與人物（後半是新的行程）
            setattr(self, k, v)
        self.login_all()

    def plan_settle(self) -> None:
        """快轉過了到點：盤算結算，助他一臂與壞他的事的人下一次同步收到結果（紀錄、情誼）。"""
        for _ in range(10):  # 快轉到這一件盤算結算為止（十二小時一跳）
            plan = next((x for x in self.world.get_season().plans if x.stop == self.plan_stop), None)
            if plan is None or plan.settled:
                break
            self.do(ADMIN, "fast_forward", {"hours": 12})
        self.world_view("盤算到點之後")
        for who in (self.HELPER, self.BLOCKER, self.FREE):
            self.main(who)
            self.me(who, "盤算結算之後")

    def yuedan_pending(self) -> list[str]:
        return [e.name for e in self.world.get_season().yuedan if not e.published]

    def seed_batch(self, names: list[str]) -> None:
        """擺一批還沒寫的月旦評（跟 tick 自己評的一樣：固定句、還沒寫、還沒發）。"""
        from tianxia import yuedan
        from tianxia.state import YuedanEntry

        def seed(s) -> None:
            week = max(self.week_of(), 1)
            for n in names:
                s.yuedan.append(YuedanEntry(week=week, name=n, board="名人", fact="名望 9", line=yuedan.fixed_line("名人", n), at=s.time))

        self.edit_world(seed)

    def yuedan_on(self) -> None:
        """月旦評的 A、B、C：前半留下的那一批在模型叫不動時發（固定句）；擺一批在模型回了時發（一句寫太短退回固定句）；擺一批等太久照固定句發；
        沒有單子的時候叫一次；玩家卡上的評語。"""
        emit("等著發的", self.yuedan_pending())
        MODEL["yuedan"] = None
        emit("模型叫不動 yuedan_once", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
        emit("等著發的（發完）", self.yuedan_pending())
        self.world_view("模型叫不動發完")
        emit("沒有單子 yuedan_once", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
        for mode in ("mixed", "all"):
            self.seed_batch([self.STRANGER, self.VIEWER, self.HUANG_WIN])
            MODEL["yuedan"] = mode
            try:
                emit(f"模型回了 yuedan_once {mode}", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
            finally:
                MODEL["yuedan"] = None
            self.world_view(f"模型回了發完 {mode}")
        self.seed_batch([self.STRANGER, self.HELPER])
        with self.tuned(self.c.config.figure_life, yuedan_wait_seconds=0.0):
            self.main(self.VIEWER)
            self.do(ADMIN, "fast_forward", {"hours": 1})
        self.world_view("等太久發完")
        for who in (self.VIEWER, self.STRANGER):
            self.main(who)
        emit("玩家卡", self.call(self.VIEWER, "GET", f"/api/peer?name={self.STRANGER}")[1])

    def admin(self) -> None:
        """管理者救回人物：叫回選單（朱儁退場等著）、救回、沒退場的、不是管理者、沒有這個人。"""
        view = self.call(ADMIN, "GET", "/api/admin")[1]
        emit("叫回人物選單", view.get("fallen") if isinstance(view, dict) else view)
        self.do(self.HELPER, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": "nobody"})
        self.do(ADMIN, "revive_figure", {})
        view = self.call(ADMIN, "GET", "/api/admin")[1]
        emit("叫回人物選單（救回之後）", view.get("fallen") if isinstance(view, dict) else view)
        self.world_view("救回之後")
        self.main(self.VISITOR)
        self.menu(self.VISITOR, "救回之後", "aid:")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在常社、體力滿）若干輪；直接問 bot_policy.score 對 aid:、plan: 各幾分；體力花不完時 _stamina_play 挑到什麼（機會調成必挑）；
        整季機器人在常社的選單挑哪一顆（aid:、act:challenge: 都不按）。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        spot = self.hall if self.hall in self.c.locations else sorted(self.c.locations)[0]
        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, spot, None
            p.visited.add(spot)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        for name in self.BOT_SEATS[:1]:
            self.begin()
            g = Game(self.c, self.chars.load(name), world=self.world)
            g.state.world = self.world.get_season()
            g.sync(CLOCK[0])
            profile = g.state.player.bot
            rows = [[o.id, o.enabled, bot_policy.score(g, o, profile)] for o in g.options(odds=False, tick=False) if o.id.startswith(("aid:", "plan:", "act:challenge:"))]
            emit(f"假人 {name} 問 score", rows)
            before = bot_policy.PLAY_CHANCE
            bot_policy.PLAY_CHANCE = 2.0
            try:
                emit(f"假人 {name} _stamina_play", bot_policy._stamina_play(g, random.Random(5)))
            finally:
                bot_policy.PLAY_CHANCE = before
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_FIGACT_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("人假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"人假人 {name}", {"loc": p.location, "stamina": p.stamina, "silver": p.stats.get("silver", 0),
                                    "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                    "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "人丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, spot, None
        p.visited.add(spot)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：護衛的崗、犒軍探望的帳、盤算、月旦評、人物的聲威與打贏幾次都隨季換掉。"""
        self.do(ADMIN, "end_season")
        self.main(self.HUANG_WIN)
        self.do(ADMIN, "next_season")
        self.world_view("換季之後")
        for who in (self.HUANG_WIN, self.GUARD, self.VISITOR, self.HELPER):
            self.main(who)
            self.me(who, "換季之後")
            self.menu(who, "換季之後", "aid:", "plan:", "act:challenge:")


def _figact_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _story_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：月旦評發出去那一則的開頭（搬之前在 tianxia/yuedan.py、之後在 tianxia/features/figure_acts/yuedan.py）
_figact_register_track("figact", FigActScenario, (("tianxia/features/figure_acts/yuedan.py", "tianxia/yuedan.py"),
                                                  ('HEAD = "{critic}月旦評（{week}）："', 'HEAD = "{critic}月旦評！（{week}）："')), "week7")


# ═══════════════════════════ zhuan：列傳一軌（全部拆包第 29 批，dev/zhuan-1） ═══════════════════════════
# 列傳（tianxia/biography.py、zhuan_end.py、zhuan_html.py 與 Game 上寫傳、休季三顆、行狀頁的 20 個方法、server 的列傳那一段與 5 條路由、zhuan: 前綴）
# 搬進新包 tianxia/features/zhuan/（舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-列傳包-第1批.md）。這一段整塊是這一批的：接在檔尾、最後一行
# 登記（_zhuan_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。

ZHUAN_FIGURES = ("luzhi", "zhujun", "caocao")  # 評曰與親筆評曰的人物（正式內容有；測試內容沒有就改拿人物表的前三位）


class ZhuanScenario(Scenario):
    """列傳（--track zhuan，自己一個資料庫）。休季的選單、行狀頁、寫傳 A（鎖內開單）→ B（鎖外叫模型）→ C（鎖內重驗再存）、人物評曰、三張票、
    分享與公開頁、換季之後讀舊的一季，全部經公開的 API；寫傳的背景執行緒改成當場跑完（不然「回應」與「寫完」是賽跑，雜湊不穩）。
    - 岑書瀾（官軍）：模型擋著（DeadClient）→ 規則版；分享、收回、再分享（同一個代碼）、公開頁、收回之後 404。**前半就寫好了**。
    - 封硯秋（黃巾）：買插畫、紀念印、親筆評曰兩張與重修列傳；前半用掉插畫、紀念印、第一張評曰、用規則版寫成（買了的評曰寫成固定句）；
      後半模型回了重寫、第二張評曰在寫成之後才用（QUOTE_LATER）、重寫次數用完被擋。
    - 葛臨川（官軍）：情誼高的三位人物白送評曰；前半只買了紀念印、傳還沒寫；後半模型回了才寫（正文＋三條 VerdictText）。
    - 邵玄度（散人）：插畫票不賣、按不到；規則版寫成。桓子衿（官軍）只有系統記的行狀（投靠、季末論功）：寫得成、立刻分享。紀懷素（新人，一則行狀都沒有）：
      讀不到、寫不了、分享不了。
    - 屈懷瑾（黃巾）：收季之後一直沒回來過，管理者開下一季之後才第一次同步（換季那一刻 _zhuan_past 補季末論功），再讀、寫、分享舊的一季。
    - 擠在一起的：同一篇已經在寫（ZHUAN_JOBS 有）就不再開；不存在的季；沒有登入。
    - 半舊半新：前半停在「休季、票買了用了一半、有人寫成了有人沒寫、有人分享出去了」，後半接著寫、重寫、換季。
    - 假人：BotRunner 兩個在休季與換季之後各跑幾輪（其中一個手上有紀念印的票，看它按不按 zhuan:seal；沒有行狀的假人沒有傳）。
    五種設定：none、weekend（列傳為終點關著：休季一顆灰鈕，傳照寫）、season21、week7、test（行狀關著：每一條都回「不能」）。"""

    RULE, MODEL_W, FREE, LONE, EMPTY, LAPSED = "岑書瀾", "封硯秋", "葛臨川", "邵玄度", "桓子衿", "屈懷瑾"
    PLAYERS = {RULE: "guan", MODEL_W: "huang", FREE: "guan", LONE: None, EMPTY: "guan", LAPSED: "huang"}
    NEWBIE = "紀懷素"
    BOT_SEATS = ["冊甲", "冊乙"]
    PHASES_FIRST = ["setup", "seed", "close", "tickets", "first_writes", "half"]
    PHASES_SECOND = ["resume", "second_writes", "after_written", "pages", "bots", "roll", "old_season", "bots_again"]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    def figs(self) -> list[str]:
        have = [f for f in ZHUAN_FIGURES if f in self.c.characters]
        return have if len(have) == len(ZHUAN_FIGURES) else sorted(self.c.characters)[:3]

    @contextlib.contextmanager
    def inline(self):
        """server 的背景執行緒（write_zhuan 的 zhuan-<季>）當場跑完：不用另一條執行緒，回應裡的 writing 與寫完的內容就不是賽跑。"""
        real = self.server.threading

        class Inline:
            def __init__(self, target=None, name=None, daemon=None, **kw):
                self.target = target

            def start(self):
                self.target()

        class Shim:
            Thread = Inline

            def __getattr__(self, n):
                return getattr(real, n)

        self.server.threading = Shim()
        try:
            yield
        finally:
            self.server.threading = real

    def zwrite(self, who: str, body: dict, model: bool = False):
        """POST /api/zhuan/write（背景執行緒當場跑完、模型擋著或回了）。"""
        MODEL["zhuan"] = model
        try:
            with self.inline():
                return self.call(who, "POST", "/api/zhuan/write", body)
        finally:
            MODEL["zhuan"] = False

    def number(self, who: str) -> int:
        return self.chars.load(who).player.season_number

    def me(self, who: str, tag: str) -> None:
        from tianxia.characters import name_key
        from tianxia.wallet import Wallet

        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        tier = self.world.get_season().final_tiers.get(who)
        emit(f"{who} {tag}", {
            "season": p.season_number, "loc": p.location, "faction": p.faction, "contrib": p.contrib, "seen": p.xingshi_seen,
            "annals": [[a.kind, a.text, a.weight, a.figure] for a in p.annals],
            "tickets": [[r.item, r.season, r.data, r.refunded] for r in Wallet(self.world.db).purchases(name_key(who))],
            "tier": None if tier is None else tier.model_dump(mode="json"),
            "journal": [[e.title, list(e.lines)[:3]] for e in state.journal[:3]], "jobs": sorted(self.server.ZHUAN_JOBS)})

    def zopts(self, who: str, tag: str) -> list[str]:
        """休季選單上 season: 與 zhuan: 開頭的幾顆（灰的也寫）。"""
        opts = self.options(who)
        got = [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(("zhuan:", "season:"))]
        emit(f"{who} {tag} 休季選單", got)
        return [i for i, _, on in got if i.startswith("zhuan:") and on]

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def write(self, who: str, tag: str, *, rewrite: bool = False, model: bool = False, season: int | None = None) -> None:
        """POST /api/zhuan/write（模型擋著或回了），再讀一次那一季。"""
        n = self.number(who) if season is None else season
        self.zwrite(who, {"season": n, "rewrite": rewrite}, model)
        self.call(who, "GET", f"/api/zhuan?season={n}")
        self.me(who, tag)

    def share(self, who: str, public: bool, tag: str, season: int | None = None) -> str | None:
        n = self.number(who) if season is None else season
        import secrets

        real = secrets.token_urlsafe
        secrets.token_urlsafe = lambda nbytes=None: f"zc{STEP[0] + 1:04d}"  # 分享代碼是 secrets.token_urlsafe(6)：隨機的，換成照步數的固定代碼
        try:
            code, view = self.call(who, "POST", "/api/zhuan/share", {"season": n, "public": public})
        finally:
            secrets.token_urlsafe = real
        url = view.get("url") if isinstance(view, dict) else None
        emit(f"{who} {tag} 分享網址", url)
        return url

    def page(self, tag: str, url: str | None) -> None:
        """公開頁（不用登入）：整頁的 sha256、長度與開頭。"""
        if not url:
            emit(f"頁面 {tag}", "沒有網址")
            return
        path = "/zhuan/" + url.rsplit("/zhuan/", 1)[-1]
        self.begin()
        r = self.TestClient(self.server.app).get(path)
        emit(f"頁面 {tag} {path}", {"status": r.status_code, "len": len(r.text), "sha": hashlib.sha256(r.text.encode("utf-8")).hexdigest(),
                                     "head": r.text[:160], "has": [k for k in ("評曰", "<img", "朱印", "og:image") if k in r.text]})

    # ── 前半 ──

    def seed(self) -> None:
        """每個人站到陣營的投靠點、記兩三則行狀、擺貢獻（收季時排名次）與跟人物的情誼（評曰的寫手）。桓子衿一則行狀都沒有。"""
        from tianxia import annals

        figs, sides = self.figs(), {f.id: f for f in self.c.scenario.factions}
        affinity = {self.MODEL_W: {figs[0]: 55, figs[1]: 45}, self.FREE: {figs[0]: 75, figs[1]: 72, figs[2]: 80},
                    self.LONE: {figs[0]: 50}, self.LAPSED: {figs[0]: 76}}
        for i, (who, side) in enumerate(self.PLAYERS.items()):
            f = sides.get(side) if side else None
            self.place(who, f.join_at[0] if f is not None and f.join_at else None, side)

            def fn(s, who=who, i=i):
                p = s.player
                if who != self.EMPTY:
                    annals.note(s, self.c, annals.DEED, f"{who}在城外守了一夜。", 3)
                    annals.note(s, self.c, annals.DEED, f"{who}替路過的商旅解了圍。", 2)
                p.contrib = 0 if who == self.EMPTY else 60 - 9 * i
                if who == self.LAPSED:
                    p.contrib = 60  # 到 min_contribution（40）以上才有階，換季補論功才走得到
                p.affinities.update(affinity.get(who, {}))
            self.edit_state(who, fn)
            self.me(who, "擺好行狀")
        # 〈天下形勢〉一篇寫到岑書瀾與屈懷瑾（同步時記一則；屈懷瑾要換季才補，走 xingshi_notes 的換季那一條）
        from tianxia.state import XingshiEssay

        names = f"{self.RULE}與{self.LAPSED}"
        self.world.mutate_season(lambda s: s.xingshi.append(XingshiEssay(key=1, time=1000, n=1, essay=f"潁川一帶，{names}連日奔走。", line="是日：兩軍相持。")))

    def close(self) -> None:
        """管理者收季；除了屈懷瑾，每個人同步一次進休季（季末論功、〈天下形勢〉各記一則行狀）並看行狀頁。"""
        self.do(ADMIN, "end_season")
        emit("收季之後的名次", {k: v.model_dump(mode="json") for k, v in sorted(self.world.get_season().final_tiers.items())})
        for who in self.PLAYERS:
            if who == self.LAPSED:
                continue
            self.main(who)
            self.me(who, "收季之後")
            self.call(who, "GET", "/api/annals")

    def tickets(self) -> None:
        """商城買票（管理者補發元寶）、休季選單上的鈕、用掉一部分：封硯秋用插畫、紀念印、第一張親筆評曰；葛臨川蓋紀念印；邵玄度的插畫票不賣、按不到。"""
        buys = {self.MODEL_W: ["zhuan_art", "zhuan_seal", "zhuan_quote", "zhuan_quote", "rewrite_zhuan"], self.FREE: ["zhuan_seal", "zhuan_quote"],
                self.LONE: ["zhuan_art", "zhuan_seal"], self.EMPTY: ["zhuan_seal"], self.RULE: ["zhuan_seal"]}
        for n, (who, items) in enumerate(buys.items()):  # 編號只認英數字、底線、減號（其餘伺服器產隨機的）
            self.do(ADMIN, "mall_reissue", {"name": who, "amount": 1500, "note": "對照", "ref": f"zhuan-grant-{n}"})
            for k, item in enumerate(items):
                self.call(who, "POST", "/api/mall/buy", {"item": item, "ref": f"zhuan-buy-{n}-{k}"})
            self.me(who, "買完")
        for who in (self.MODEL_W, self.FREE, self.LONE, self.EMPTY, self.RULE):
            ids = self.zopts(who, "買完之後")
            if who == self.MODEL_W:
                for pick in ("zhuan:pick_art", "zhuan:seal", next((i for i in ids if i.startswith("zhuan:quote:")), "zhuan:quote:nope")):
                    self.choose(who, pick)
                self.choose(who, "zhuan:seal")  # 用過了
                self.choose(who, "zhuan:quote:nope")  # 不在選單上
            elif who in (self.FREE, self.EMPTY):
                self.choose(who, "zhuan:seal")
            elif who == self.LONE:
                self.choose(who, "zhuan:pick_art")
            self.zopts(who, "用完之後")
            self.me(who, "用完票")

    def first_writes(self) -> None:
        """前半寫成的（模型擋著，規則版）：岑書瀾（分享出去）、封硯秋（買的評曰寫成固定句）、邵玄度；先擋掉不合規矩的（沒寫過不能重寫、不存在的季、新人沒有傳）。"""
        n = self.number(self.RULE)
        self.zwrite(self.RULE, {"season": n, "rewrite": True})  # 還沒寫過，不能重寫
        self.zwrite(self.RULE, {"season": 99})
        self.call(self.RULE, "GET", "/api/zhuan?season=99")
        self.call(self.EMPTY, "GET", f"/api/zhuan?season={n}")
        self.zwrite(self.EMPTY, {"season": n})
        self.share(self.EMPTY, True, "寫成就分享")
        for path in (f"/api/zhuan?season={n}", "/api/annals"):  # 一則行狀都沒有的新人：讀不到、寫不了、分享不了
            self.call(self.NEWBIE, "GET", path)
        self.zwrite(self.NEWBIE, {"season": n})
        self.share(self.NEWBIE, True, "沒有傳")
        self.call(self.RULE, "GET", f"/api/zhuan?season={n}")
        self.write(self.RULE, "規則版寫成")
        self.zwrite(self.RULE, {"season": n})  # 寫過了，不能再「寫」
        url = self.share(self.RULE, True, "公開")
        self.page("岑書瀾 公開", url)
        self.write(self.MODEL_W, "規則版寫成（買了評曰）")
        self.write(self.LONE, "規則版寫成")
        self.main(self.RULE)
        self.main(self.MODEL_W)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in self.PLAYERS:
            if who != self.LAPSED:
                self.main(who)
                self.zopts(who, "接手")

    def second_writes(self) -> None:
        """模型回了：葛臨川才寫（正文＋三條評曰）；封硯秋重寫（買了重修列傳，一季能重寫兩次）；岑書瀾重寫一次（模型擋著）；同一篇已經在寫就不再開。"""
        n = self.number(self.FREE)
        self.write(self.FREE, "模型回了寫成", model=True)
        self.write(self.MODEL_W, "模型回了重寫一", rewrite=True, model=True)
        self.write(self.RULE, "模型擋著重寫", rewrite=True)
        key = (self.LONE.casefold(), n)
        self.server.ZHUAN_JOBS[key] = 0.0  # 這一篇已經在寫
        try:
            self.zwrite(self.LONE, {"season": n, "rewrite": True})
            self.call(self.LONE, "GET", f"/api/zhuan?season={n}")
        finally:
            self.server.ZHUAN_JOBS.pop(key, None)

    def after_written(self) -> None:
        """封硯秋寫成之後才用第二張親筆評曰（QUOTE_LATER，要下一次重修才寫進去），再重寫兩次（第二次是買的那一張，第三次被擋）。"""
        who = self.MODEL_W
        ids = self.zopts(who, "寫成之後")
        pick = next((i for i in ids if i.startswith("zhuan:quote:")), None)
        if pick is not None:
            self.choose(who, pick)
        self.write(who, "模型回了重寫二", rewrite=True, model=True)
        self.write(who, "重寫次數用完", rewrite=True, model=True)
        self.zopts(who, "重寫之後")

    def pages(self) -> None:
        """分享：封硯秋（有插畫、紀念印）、葛臨川、屈懷瑾還沒寫（分享不了）；岑書瀾收回再分享（同一個代碼）、收回之後公開頁 404；不認得的代碼。"""
        for who in (self.MODEL_W, self.FREE):
            self.page(f"{who} 公開", self.share(who, True, "公開"))
        self.share(self.LAPSED, True, "還沒寫")
        self.share(self.RULE, False, "收回")
        self.page("岑書瀾 收回之後", "https://x/zhuan/" + (self.world.biography(self.number(self.RULE), self.RULE) or {}).get("share_code", "none"))
        self.page("岑書瀾 再公開", self.share(self.RULE, True, "再公開"))
        self.page("不認得的代碼", "https://x/zhuan/nope-nope")
        self.call(self.RULE, "GET", "/api/annals")
        client = self.TestClient(self.server.app)
        self.begin()
        r = client.get(f"/api/zhuan?season={self.number(self.RULE)}")
        emit("沒登入讀傳", [r.status_code, r.text[:120]])

    def bot_seats(self) -> None:
        """休季開著時加入的兩個假人（冊甲手上有紀念印的票）。"""
        from tianxia import annals
        from tianxia.characters import name_key
        from tianxia.engine import Game
        from tianxia.state import BotProfile
        from tianxia.wallet import Wallet

        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=sides[i % 2] if sides else None, season_number=self.world.get_season_number())
            g.client = None
            p.faction = p.bot.faction
            p.contrib = 30 - 10 * i
            annals.note(g.state, self.c, annals.DEED, f"{name}在渡口守了半日。", 3)
            self.chars.save(g.state)
            if i == 0:
                Wallet(self.world.db).post(name_key(name), 500, "grant", "zhuan:bot", time=CLOCK[0])
                self.begin()
                g2 = Game(self.c, self.chars.load(name), world=self.world)
                g2.client = None
                emit(f"{name} 買紀念印", g2.mall_buy("zhuan_seal", "zhuan-bot-1"))
                self.chars.save(g2.state)

    def bot_rounds(self, tag: str, rounds: int) -> None:
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(rounds):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit(f"假人 {tag} 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name} {tag}", {"season": p.season_number, "annals": [[a.kind, a.text] for a in p.annals], "journal": [[e.title, list(e.lines)[:2]] for e in s.journal[:2]],
                                         "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def bots(self) -> None:
        self.bot_seats()
        self.bot_rounds("休季", 4)

    def roll(self) -> None:
        """管理者開下一季：屈懷瑾這時才第一次同步（沒回來過，_zhuan_past 補季末論功再存行狀）；其他人第一次同步也是換季那一刻。"""
        self.old = self.world.get_season_number()
        self.do(ADMIN, "next_season")
        emit("換季之後的賽季", [self.world.get_season_number(), self.world.season_phase()])
        for who in [self.LAPSED, *(w for w in self.PLAYERS if w != self.LAPSED)]:
            self.main(who)
            self.me(who, "換季之後")
            self.call(who, "GET", "/api/annals")
            self.zopts(who, "換季之後")

    def old_season(self) -> None:
        """讀舊的一季（過去的季照存起來的行狀與身家）：屈懷瑾寫（模型回了，白送的評曰開單時照身家）、分享、公開頁；封硯秋、葛臨川的舊傳；新的一季不能寫。"""
        old = self.world.get_season_number() - 1
        for who in (self.MODEL_W, self.FREE, self.RULE, self.LONE, self.EMPTY):
            self.call(who, "GET", f"/api/zhuan?season={old}")
        self.write(self.LAPSED, "舊的一季寫成", model=True, season=old)
        self.page("屈懷瑾 公開", self.share(self.LAPSED, True, "公開", season=old))
        self.write(self.LAPSED, "舊的一季重寫", rewrite=True, season=old)
        self.write(self.EMPTY, "舊的一季沒有行狀", season=old)
        self.zwrite(self.RULE, {"season": old + 1})
        self.zwrite(self.RULE, {"season": old, "rewrite": True})

    def bots_again(self) -> None:
        self.bot_rounds("換季之後", 3)


def _zhuan_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _story_register_track）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：蓋紀念印那一句（搬之前在 tianxia/zhuan_end.py、之後在 tianxia/features/zhuan/zhuan_end.py）
_zhuan_register_track("zhuan", ZhuanScenario, (("tianxia/features/zhuan/zhuan_end.py", "tianxia/zhuan_end.py"),
                                               ('SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}。"', 'SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}！"')), "season21")


# ═══════════════════════════ military：軍情一軌（全部拆包第 33 批，dev/military-1） ═══════════════════════════
# 軍情（軍令卡與應召、押糧、第 2 階行動、第 3／4 階行動、席次輪替與召見：Game 上 17 個方法與 rank_actions.py）搬進新包 tianxia/features/military/
# （計畫 docs/superpowers/plans/2026-11-05-軍情包-第1批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記（_military_register_track），
# PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。


class MilitaryScenario(Scenario):
    """軍情一軌（--track military，自己一個資料庫）。
    軍令卡：管理者重發本週軍令（natural 的發法）後各陣營看卡；再各擺一道護糧軍令（湊兩次就達成）。押糧：糧草不夠按灰鈕、有糧接下糧車（第二次按已押著一車）、
    散人與不在起點的按了被擋；**前半停在押糧走到一半**（糧車在路上、軍令還沒交）；後半快轉到抵達：官軍的人沒遇上截糧隊、黃巾的人撞上截糧隊打輸（糧車被劫）、
    官軍第二個人送到把軍令湊滿（達成、軍情）。第 2 階行動：官軍黃巾各一人，按到今天做滿變灰、體力不夠、散人按了被擋。第 3、4 階行動：照內容挑做得了的地點，
    按到這週做滿；有資格的人抄帳補缺（席次，第 4 階在任）。召見與應召：貢獻夠了同步自然發召見（**前半停在召見還沒去應**，後半走到召見地點應召、演晉升奇遇）；
    管理者替他發召見（散人、已有召見、已有資格、不存在的名號）、輪替席次（第 1 週沒有上一週、快轉到第 2 週之後輪替）、重發軍令。換季。
    假人：BotRunner 兩個（官軍，站在有戰線的地方；bot_policy 的 act: 那幾顆）；整季機器人眼前的選單。
    沒有軍令的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    G_RUN, G_RUN2, H_RUN = "蕭鐵崖", "顧長庚", "雷驚瀾"
    G_R2, H_R2 = "沈孤鴻", "祁連山"
    G_R3, H_R3 = "宋斷虹", "嚴寒江"
    G_SEAT, H_SEAT = "洛雲歸", "燕無歸"
    G_CALL, H_CALL = "戚望舒", "范潛龍"
    LONE = "白無相"
    PLAYERS = {G_RUN: "guan", G_RUN2: "guan", H_RUN: "huang", G_R2: "guan", H_R2: "huang", G_R3: "guan", H_R3: "huang",
               G_SEAT: "guan", H_SEAT: "huang", G_CALL: "guan", H_CALL: "huang", LONE: None}
    BOT_SEATS = ["營甲", "營乙"]
    PHASES_FIRST = ["setup", "seat", "orders", "convoy_take", "rank2", "rank34", "summons_open", "half"]
    PHASES_SECOND = ["resume", "answer", "convoy_arrive", "admin", "bots", "season"]

    PICKS = ("slots", "hub", "act3")
    slots: dict = {}
    hub = "nobody"
    act3: dict = {}

    # ── 小工具 ──

    @contextlib.contextmanager
    def tuned(self, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", dict(values))
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    @contextlib.contextmanager
    def fights(self, tier: str):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None:
                kwargs["tier"] = tier
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        have = self.options(who).get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> dict:
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])
        return opts

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、陣營、體力、貢獻與每週貢獻、階與資格、押著的糧車、手上的召見、第 2 階今天做了幾次、第 3 4 階這週做了幾次、
        捐獻、最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "stamina": p.stamina, "contrib": p.contrib, "weeks": dict(sorted(p.contrib_weeks.items())), "rank": p.rank, "qualified": p.qualified,
            "convoy": None if p.convoy is None else p.convoy.model_dump(mode="json"),
            "summons": None if p.summons is None else p.summons.model_dump(mode="json"),
            "rank2_days": dict(sorted(p.rank2_days.items())), "rank_weeks": dict(sorted(p.rank_action_weeks.items())),
            "donations": dict(sorted(p.donations.items())), "pushed": dict(sorted(p.pushed.items())),
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：軍令、席次與帳、陣營軍情與天下大事的尾巴、戰線的值。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "orders": [o.model_dump(mode="json") for o in w.orders], "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "ledger": {k: {n: dict(sorted(x.items())) for n, x in sorted(v.items())} for k, v in sorted(w.seat_ledger.items())},
            "rumors": [r.text for r in w.rumors][-5:], "chronicle": [r.text for r in w.chronicle][-3:], "hooked": getattr(w, "hooked_week", None)})

    def week_of(self) -> int:
        from tianxia import calendar

        s = self.world.get_season()
        return calendar.point(s.time, self.c, s).week

    def forward_to_week(self, week: int) -> None:
        for _ in range(40):
            if self.week_of() >= week:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        emit("季曆第幾週", self.week_of())

    def grain(self, who: str, n: int) -> None:
        """背包裡放 n 份糧草（慢屬性的素材，從最低階的那一種放）。"""
        mats = sorted((m for m in self.c.materials.values() if m.attribute == "慢"), key=lambda m: (m.tier, m.id))
        if mats:
            self.edit(who, lambda p: p.materials.__setitem__(mats[0].id, n))

    def hop(self, who: str) -> None:
        """走一步（選單上第一個能走的地方）；押著糧車的人，終點先改成這一步（這樣一步就抵達，不必走完一整條路）。"""
        move = next((i for i, o in self.options(who).items() if i.startswith("move:") and o.get("enabled")), None)
        emit(f"{who} 走的那一步", move)
        if move is None:
            return
        dest = move.split(":")[1]
        self.edit(who, lambda p: setattr(p.convoy, "to_loc", dest) if p.convoy is not None else None)
        self.choose(who, move)

    def spot(self, side: str | None, key: int) -> str:
        """這一陣營押糧的起點（0）、終點（1）、截糧的地點（2）；沒有這一道（測試內容）就用 hub。"""
        got = self.slots.get(side)
        return self.hub if got is None else got[1 + key]

    # ── 前半 ──

    def seat(self) -> None:
        """挑地點：每個陣營押糧的起點與終點（內容的插槽表第一條有這個陣營的戰線）、有戰線的地方（hub）、第 3 4 階行動做得了的地方。"""
        from tianxia import rank_actions
        from tianxia.rules import front_of

        c = self.c
        self.slots = {}
        for front, by in sorted(c.orders.slots.items()):
            for side, sl in sorted(by.items()):
                self.slots.setdefault(side, (front, sl.escort[0], sl.escort[1], sl.intercept))
        fronted = [loc for loc in sorted(c.locations) if front_of(c, loc) is not None]
        self.hub = self.slots["guan"][1] if "guan" in self.slots else (fronted[0] if fronted else sorted(c.locations)[0])
        state = self.chars.load(ADMIN)
        state.world = self.world.get_season()
        self.act3 = {}
        for side in ("guan", "huang"):
            state.player.faction = side
            for a in c.orders.rank_actions:
                if a.faction != side:
                    continue
                for loc in sorted(c.locations):
                    if rank_actions.where_ok(state, c, a, loc):
                        self.act3.setdefault(side, loc)
                        break
        emit("挑的地點", {"slots": {k: list(v) for k, v in sorted(self.slots.items())}, "hub": self.hub, "act3": self.act3,
                         "orders_on": bool(c.orders.templates), "rank2": sorted(c.orders.rank2), "rank_actions": [a.id for a in c.orders.rank_actions]})
        for who, side in self.PLAYERS.items():
            home = self.spot(side, 0) if who in (self.G_RUN, self.G_RUN2, self.H_RUN) else self.hub
            self.place(who, home, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        self.world_view("開場")

    def orders(self) -> None:
        """軍令卡：管理者重發本週軍令（兩次，第二次換掉沒達成的）、各看一遍；再把各陣營的軍令換成一道護糧（湊兩次達成）。"""
        from tianxia import orders
        from tianxia.engine import Game
        from tianxia.state import Order

        self.do(ADMIN, "issue_orders")
        for who in (self.G_RUN, self.H_RUN, self.LONE):
            self.main(who)
        self.do(ADMIN, "issue_orders")
        self.world_view("重發之後")
        shell = Game.for_world(self.c, self.world)
        week = orders.period_of(shell.state, self.c)

        def put(s) -> None:
            s.orders[:] = [o for o in s.orders if not o.id.startswith("mb:")]
            for side, (front, start, end, _icp) in sorted(self.slots.items()):
                s.orders.append(Order(id=f"mb:{side}:escort", template="escort", faction=side, week=week, front=front, start=start, end=end,
                                      location=start, quota=2, text=f"（對照）{side}護糧"))

        self.world.mutate_season(put)
        for who in (self.G_RUN, self.H_RUN, self.LONE):
            self.main(who)
        self.world_view("擺護糧之後")

    def convoy_take(self) -> None:
        """押糧：顧長庚沒糧草（灰鈕）；蕭鐵崖與雷驚瀾放糧草接下糧車，蕭鐵崖再按一次（已押著一車）；散人按了被擋；接了的兩個人各走一步（前半停在路上）。"""
        self.menu(self.G_RUN2, "沒有糧草", "act:convoy")
        self.press(self.G_RUN2, "act:convoy", "沒有糧草")
        need = self.c.config.convoy_grain
        for who in (self.G_RUN, self.H_RUN):
            self.grain(who, need + 2)
            self.menu(who, "有糧草", "act:convoy")
            self.press(who, "act:convoy", "接糧車")
        self.menu(self.G_RUN, "已押著一車", "act:convoy")
        self.press(self.G_RUN, "act:convoy", "再接一車")
        self.press(self.LONE, "act:convoy", "散人")
        for who in (self.G_RUN, self.H_RUN):
            self.hop(who)
            self.me(who, "押糧走到一半")

    def rank2(self) -> None:
        """第 2 階行動：官軍黃巾各一人在有戰線的地方，按到今天做滿（灰）；再按一次被擋；體力不夠的人；階不夠的人按了被擋。"""
        for who in (self.G_R2, self.H_R2):
            self.place(who, self.hub)
            self.edit(who, lambda p: setattr(p, "rank", 2))
            self.menu(who, "第 2 階", "act:rank2")
            for k in range(max(1, int(self.c.config.rank2_daily)) + 1):
                self.press(who, "act:rank2", f"第 {k + 1} 次")
            self.me(who, "做滿之後")
        self.place(self.G_R2, None)
        self.edit(self.G_R2, lambda p: (p.rank2_days.clear(), setattr(p, "stamina", 0.0)))  # 今天的次數清掉，才輪得到「體力不夠」那一句（審查：原本被「今天做滿」擋在前面）
        self.menu(self.G_R2, "體力沒了", "act:rank2")
        self.press(self.G_R2, "act:rank2", "體力沒了")
        self.press(self.LONE, "act:rank2", "散人")

    def rank34(self) -> None:
        """第 3、4 階行動：宋斷虹、嚴寒江第 3 階在做得了的地方，每顆按到這週做滿再多按一次；洛雲歸、燕無歸有資格（貢獻帳在第 1 週），同步抄帳補缺、在任是第 4 階。"""
        for who, side in ((self.G_R3, "guan"), (self.H_R3, "huang")):
            self.place(who, self.act3.get(side, self.hub))
            self.edit(who, lambda p: setattr(p, "rank", 3))
            opts = self.menu(who, "第 3 階", "act:rank:")
            for oid in [i for i in opts if i.startswith("act:rank:")][:2]:
                for k in range(4):
                    self.press(who, oid, f"第 {k + 1} 次")
            self.me(who, "第 3 階做完")
        for who, side in ((self.G_SEAT, "guan"), (self.H_SEAT, "huang")):
            self.place(who, self.act3.get(side, self.hub))
            self.edit(who, lambda p: (setattr(p, "rank", 3), setattr(p, "qualified", True), p.contrib_weeks.update({1: 40 if p.faction == "guan" else 30})))
            self.main(who)
            self.menu(who, "有資格", "act:rank:")
            self.me(who, "抄帳補缺之後")
        self.world_view("席次之後")

    def summons_open(self) -> None:
        """召見：戚望舒貢獻夠了，同步自然發召見（前半停在還沒去應）；范潛龍留給管理者；管理者在第 1 週輪替席次（沒有上一週）。"""
        self.edit(self.G_CALL, lambda p: setattr(p, "contrib", 10 ** 6))
        self.main(self.G_CALL)
        self.me(self.G_CALL, "發了召見")
        self.do(ADMIN, "rotate_seats")

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".military.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".military.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        for who in list(self.clients):  # 登入就同步：路上的糧車在這一刻抵達（雷驚瀾撞上截糧隊打輸、蕭鐵崖沒遇上），機率與仗的結果先調好
            if who == self.H_RUN:
                with self.tuned(convoy_ambush_chance=1.0), self.fights("落敗"):
                    self.relogin(who)
            elif who == self.G_RUN:
                with self.tuned(convoy_ambush_chance=0.0), self.fights("大勝"):
                    self.relogin(who)
            else:
                self.relogin(who)
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "接手")

    def answer(self) -> None:
        """應召：戚望舒走到召見的地點，按應召、把晉升奇遇演完。"""
        state = self.chars.load(self.G_CALL)
        summons = None if state is None else state.player.summons
        if summons is None:
            emit("戚望舒沒有召見", None)
            self.press(self.G_CALL, "act:summons", "沒有召見")
            return
        self.place(self.G_CALL, summons.location)
        self.menu(self.G_CALL, "在召見的地點", "act:summons")
        self.press(self.G_CALL, "act:summons", "應召")
        self.settle_choices(self.G_CALL, 10)
        self.me(self.G_CALL, "應召之後")

    def convoy_arrive(self) -> None:
        """押糧抵達：蕭鐵崖沒遇上截糧隊、軍令記一次；雷驚瀾撞上截糧隊打輸（糧車被劫）；顧長庚補糧草接下糧車、走一步、抵達，把官軍這道護糧湊滿（達成）。"""
        need = self.c.config.convoy_grain
        self.grain(self.G_RUN2, need + 2)
        self.press(self.G_RUN2, "act:convoy", "接糧車")
        self.hop(self.G_RUN2)
        for who, chance, tier in ((self.G_RUN, 0.0, "大勝"), (self.H_RUN, 1.0, "落敗"), (self.G_RUN2, 1.0, "大勝")):  # 顧長庚撞上截糧隊、打贏、照樣送到（審查：原本機率 0.0，一場仗都沒打）
            for _ in range(10):
                self.do(ADMIN, "fast_forward", {"hours": 1})
                with self.tuned(convoy_ambush_chance=chance), self.fights(tier):
                    self.main(who)
                state = self.chars.load(who)
                if state is None or state.player.convoy is None:
                    break
            self.me(who, "抵達之後")
        self.world_view("抵達之後")

    def admin(self) -> None:
        """管理者：替范潛龍發召見（再發一次〔已有〕、替散人、替有資格的人、不存在的名號）；快轉到第 2 週之後輪替席次；重發軍令；看席次後的第 4 階選單。"""
        for who in (self.H_CALL, self.H_CALL, self.LONE, self.G_SEAT, "無此人"):
            self.do(ADMIN, "summon", {"name": who})
        self.main(self.H_CALL)
        self.me(self.H_CALL, "管理者發了召見")
        self.forward_to_week(2)
        self.do(ADMIN, "rotate_seats")
        self.do(ADMIN, "issue_orders")
        self.world_view("輪替之後")
        for who in (self.G_SEAT, self.H_SEAT, self.G_R3):
            self.main(who)
            self.menu(who, "輪替之後", "act:rank:")
            self.me(who, "輪替之後")
        for who in (self.H_CALL, self.G_CALL, self.LONE, self.G_SEAT, "無此人"):  # 管理頁「玩家個人劇情」查名號（召見的計畫經它回給管理頁）
            self.call(ADMIN, "POST", "/api/admin/player", {"name": who})
        self.pause()

    def pause(self) -> None:
        """賽季時鐘暫停中：發軍令、輪替席次、發召見、有資格的人同步（抄帳什麼都不做）、走一步、答事件；繼續之後再同步一次（審查：這一路原本沒人走到）。"""
        self.do(ADMIN, "pause_clock")
        self.edit(self.G_R3, lambda p: (setattr(p, "qualified", True), p.contrib_weeks.update({1: 55})))
        self.do(ADMIN, "issue_orders")
        self.do(ADMIN, "rotate_seats")
        self.do(ADMIN, "summon", {"name": self.G_R3})
        for who in (self.G_R3, self.G_SEAT, self.H_SEAT):
            self.main(who)
            self.me(who, "暫停中")
        self.hop(self.G_R3)
        self.settle_choices(self.G_R3, 3)
        self.me(self.G_R3, "暫停中走了一步")
        self.world_view("暫停中")
        self.do(ADMIN, "resume_clock")
        for who in (self.G_R3, self.G_SEAT):
            self.main(who)
            self.me(who, "繼續之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在有戰線的地方、體力滿）若干輪；整季機器人眼前的選單挑哪一顆。"""
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
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.spot("guan", 0), None
            p.visited.add(p.location)
            p.rank = 2 if i == 0 else 1
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_MILITARY_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "rank2_days": dict(sorted(p.rank2_days.items())), "convoy": p.convoy is not None,
                                  "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "營丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey, p.rank = "guan" if "guan" in sides else None, self.spot("guan", 0), None, 2
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：手上的召見、押著的糧車、每週貢獻帳、席次怎麼帶。"""
        self.place(self.G_RUN2, self.spot("guan", 0))  # 收季時押著一車、不交（審查：休季時有車也回 None、換季帶不帶，原本沒人走到）
        self.grain(self.G_RUN2, self.c.config.convoy_grain + 2)
        self.press(self.G_RUN2, "act:convoy", "收季前接車")
        self.main(self.G_RUN2)
        self.me(self.G_RUN2, "收季前押著")
        self.do(ADMIN, "end_season")
        for who in (self.G_SEAT, self.G_CALL, self.H_CALL, self.G_RUN2):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.G_SEAT, self.G_CALL, self.H_CALL, self.G_RUN2, self.H_RUN):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


def _military_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _zhuan_register_track）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：糧車被劫那一句（搬之前在 engine.py 的 _convoy_arrives、之後在 tianxia/features/military/convoy_actions.py；第 2 項是之後的檔名，
# 搬的人照實際的檔名改這一個字串）
_military_register_track("military", MilitaryScenario, (("tianxia/features/military/convoy_actions.py", "tianxia/engine.py"),
                                                        ('"糧車被劫走了，這一趟不算數。"', '"糧車被劫走了，這一趟不算數！"')), "week7")


# ═══════════════════════════ outlets：銀兩出口一軌（全部拆包第 43 批，dev/outlets-1） ═══════════════════════════
# 銀兩出口與捐軍備（捐素材、捐銀兩、名師指點、買破境丹、看火候、打點門路與那一間「打點」店；`donate:`、`dadian:` 兩個前綴）。這一段整塊是
# 這一批的，接在檔尾、最後一行是 `_outlets_register_track`，PM 合的時候不跟別人的行穿插。計畫 docs/superpowers/plans/2026-11-05-銀兩出口包-第1批.md。

OUTLETS_NAMES = {"賀萬鈞": "guan", "裴雲舟": "huang", "邢孤雁": "guan", "霍青萍": None, "史臨淵": "guan", "駱風吟": "guan", "柳尋芳": "guan",
                 "計玄機": "guan", "石開山": "guan"}


class OutletsScenario(Scenario):
    """銀兩出口一軌（--track outlets，自己一個資料庫）。
    捐素材：自家大本營的軍需官那一串（打開、按一種、按離開）、直接捐（一種、幾種一起）、散人被擋、背包是空的、今天的點數收不下（切一半、其餘留著、
    一顆都收不下）、不在大本營、換天之後又能捐。捐銀兩：一下捐多少、錢不夠（灰）、今天的兩數捐滿、點數跟捐素材共用；散人、不在大本營被擋。
    醫館：名師指點（成、請了還沒用、錢不夠）、買破境丹（成、這一季買滿、錢不夠）。打點門路：大勢人物所在的地方（成、今天打過了、情誼到頂、錢不夠、
    人物不在此地）。看火候：有鐵匠鋪的城鎮（成、請了還沒開爐、錢不夠）。「打點」那一間店：進去、在裡頭做一樣（掮客換一句）、離開、動身、銀兩出口關了被收起。
    **前半停在兩處寫到一半**：一個人坐在「打點」店裡沒結、一個人開著軍需官那一串沒結；後半是新的行程，接著在裡面按。
    假人：BotRunner 兩個（官軍，站在自家大本營、背包有多的素材、手上有錢）；整季機器人與假人眼前的選單與分數（act:dadian、act:donate、dadian:、donate:）。
    設定：season21、week7（銀兩出口、捐軍備都開著）、test（兩樣都關著；同一串 API 照打，寫「沒有」）。"""

    DONOR_G, DONOR_H, POOR, LONE = "賀萬鈞", "裴雲舟", "邢孤雁", "霍青萍"
    CLINIC, FIG, SMITH = "史臨淵", "駱風吟", "柳尋芳"
    SHOP_IN, DONATE_IN = "計玄機", "石開山"
    PLAYERS = dict(OUTLETS_NAMES)
    BOT_SEATS = ["糧官甲", "糧官乙"]
    PHASES_FIRST = ["setup", "seat", "materials", "silver_gift", "bribe", "furnace", "shop", "open_two", "half"]
    PHASES_SECOND = ["resume", "in_shop", "in_donate", "shut", "depart", "next_day", "bots", "season"]
    PICKS = ("base", "clinic", "fig_loc", "fig_id", "smith", "mats")
    base: dict = {}
    clinic = fig_loc = fig_id = smith = ""
    mats: list = []

    # ── 小工具 ──

    @contextlib.contextmanager
    def tuned(self, owner_name: str, **values):
        """這一下把 Config 上某一塊（economy、silver_outlets）的設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = getattr(self.c.config, owner_name)
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {owner_name: dict(values)})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        have = self.options(who).get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> dict:
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])
        return opts

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、陣營、銀兩、背包、軍需帳與銀兩帳的天與數、請過的指點與火候、買過幾枚丹、打點過的人與情誼、兩間店開著沒、
        最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "silver": p.stats.get("silver", 0), "materials": dict(sorted(p.materials.items())), "legend_items": p.legend_items,
            "donate": [p.donate_day, p.donated_today], "silver_donate": [p.silver_donate_day, p.silver_donated],
            "mentor": [p.mentor_day, p.mentor_ready], "furnace": [p.furnace_day, p.furnace_ready], "bought": p.legend_silver_bought,
            "bribed": dict(sorted(p.bribed.items())), "affinities": dict(sorted(p.affinities.items())),
            "picking": [p.picking_donate, p.picking_dadian], "shop": [p.shop_line, p.shop_clue, p.shop_hold], "contrib": p.contrib,
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：軍備存量、戰線的值。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {"armaments": {k: dict(sorted(v.items())) for k, v in sorted(w.armaments.items())},
                           "rumors": [r.text for r in w.rumors][-3:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def forward_day(self) -> None:
        """時鐘往前走整整一天（回體丹的換日看現實鐘〔台灣 00:00〕，admin 的 fast_forward 只動賽季的鐘；一天的帳隔天重算）。"""
        STEP[0] += 1440

    def day_reset(self, who: str) -> None:
        """把這個人一天一次的帳清掉（捐素材的點數、捐銀兩的兩數、指點、火候、打點）：不必真的過一天就能再走一遍。"""
        def fn(p) -> None:
            p.donate_day, p.donated_today, p.silver_donate_day, p.silver_donated = -1, 0, -1, 0
            p.mentor_day, p.mentor_ready, p.furnace_day, p.furnace_ready = -1, False, -1, False
            p.bribed.clear()
        self.edit(who, fn)

    def bag(self, who: str, **by_slot: int) -> None:
        """背包放素材：slot 名字是 low（最低階捐得了的）、high（最高階捐得了的）。"""
        pick = {"low": self.mats[0] if self.mats else None, "high": self.mats[-1] if self.mats else None}
        self.edit(who, lambda p: [p.materials.__setitem__(pick[k], n) for k, n in by_slot.items() if pick.get(k)])

    def silver_of(self, who: str, n: int) -> None:
        self.edit(who, lambda p: p.stats.update({"silver": n}))

    # ── 前半 ──

    def seat(self) -> None:
        """挑地點：兩個陣營的大本營（投靠點）、有醫館的城鎮、有大勢人物（有對話人物）在的地方、有鐵匠鋪的城鎮、捐得了的素材（照階排）。"""
        from tianxia import economy, equipment, figures, territory
        from tianxia.engine import Game

        c = self.c
        bases = territory.bases(c)
        self.base = {}
        for loc, side in sorted(bases.items()):
            self.base.setdefault(side, loc)
        first = sorted(c.locations)[0]
        self.clinic = next((loc for loc in sorted(c.locations) if "醫館" in (c.locations[loc].tags or [])), first)
        shell = Game.for_world(c, self.world)
        s = shell.state
        self.fig_loc, self.fig_id = first, ""
        for loc in sorted(c.locations):
            got = [fid for fid in figures.present_at(s, c, loc) if c.figures[fid].character is not None]
            if got:
                self.fig_loc, self.fig_id = loc, got[0]
                break
        self.smith = first
        for loc in sorted(c.locations):
            s.player.location, s.player.journey = loc, None
            if equipment.smith_open(s, c):
                self.smith = loc
                break
        self.mats = [m.id for m in sorted(c.materials.values(), key=lambda m: (m.tier, m.id)) if economy.donate_points(c, m.id) > 0]
        emit("挑的地點", {"base": self.base, "clinic": self.clinic, "fig": [self.fig_loc, self.fig_id], "smith": self.smith, "mats": self.mats[:1] + self.mats[-1:],
                         "donate_on": bool(c.config.economy.donate), "silver_on": bool(c.config.silver_outlets.enabled)})
        home = lambda side: self.base.get(side, first)  # noqa: E731
        spots = {self.DONOR_G: home("guan"), self.DONOR_H: home("huang"), self.POOR: home("guan"), self.LONE: home("guan"), self.CLINIC: self.clinic,
                 self.FIG: self.fig_loc, self.SMITH: self.smith, self.SHOP_IN: self.clinic, self.DONATE_IN: home("guan")}
        for who, side in self.PLAYERS.items():
            self.place(who, spots[who], side)
            self.silver_of(who, 0 if who == self.POOR else 2000)
        self.world_view("開場")

    def materials(self) -> None:
        """捐素材：賀萬鈞打開軍需官那一串、按一種、直接捐一種、幾種一起捐、按離開；裴雲舟把一天的點數設得很小（切一半、其餘留著、一顆都收不下）；
        邢孤雁背包空的；霍青萍是散人。"""
        self.bag(self.DONOR_G, low=12, high=3)
        self.bag(self.DONOR_H, low=9, high=2)
        low, high = (self.mats[0], self.mats[-1]) if self.mats else ("none", "none")
        self.menu(self.DONOR_G, "捐之前", "act:donate")
        self.press(self.DONOR_G, "act:donate", "打開軍需官")
        opts = self.menu(self.DONOR_G, "軍需官那一串", "donate:")
        pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i not in ("donate:back", "donate:room")), None)
        if pick is not None:
            self.press(self.DONOR_G, pick, "按一種")
        self.press(self.DONOR_G, "donate:back", "離開")
        self.me(self.DONOR_G, "按完軍需官")
        self.do(self.DONOR_G, "donate", {"material": low, "count": 2})
        self.do(self.DONOR_G, "donate", {"items": [{"material": low, "count": 1}, {"material": high, "count": 1}, {"material": "none_such", "count": 1}]})
        self.do(self.DONOR_G, "donate", {"material": "none_such", "count": 1})
        self.do(self.DONOR_G, "donate", {"items": "壞的"})
        self.me(self.DONOR_G, "直接捐完")
        with self.tuned("economy", donate_daily_cap=4):
            self.press(self.DONOR_H, "act:donate", "點數很小")
            self.menu(self.DONOR_H, "點數很小", "donate:")
            self.do(self.DONOR_H, "donate", {"material": high, "count": 2})  # 一顆都收不下（單顆比今天的點數大）
            self.do(self.DONOR_H, "donate", {"material": low, "count": 9})  # 切一半、其餘留著
            self.do(self.DONOR_H, "donate", {"material": low, "count": 1})  # 今天捐滿了
            self.menu(self.DONOR_H, "捐滿之後", "donate:", "act:donate")
        self.me(self.DONOR_H, "切一半之後")
        self.press(self.DONOR_H, "donate:back", "離開")
        self.press(self.POOR, "act:donate", "背包空的")
        self.menu(self.POOR, "背包空的", "donate:")
        self.do(self.POOR, "donate", {"material": low, "count": 1})
        self.press(self.POOR, "donate:back", "離開")
        self.press(self.LONE, "act:donate", "散人")
        self.do(self.LONE, "donate", {"material": low, "count": 1})
        self.place(self.DONOR_G, self.clinic)
        self.bag(self.DONOR_G, low=3)
        self.do(self.DONOR_G, "donate", {"material": low, "count": 1})  # 不在大本營
        self.place(self.DONOR_G, self.base.get("guan", self.clinic))
        self.world_view("捐素材之後")

    def enter(self, who: str) -> None:
        """走進「打點」那一間店（五樣都在店裡，不在店裡按只算清單外）。"""
        self.press(who, "act:dadian", "進店")

    def leave(self, who: str) -> None:
        self.press(who, "dadian:back", "離開店")

    def silver_gift(self) -> None:
        """捐銀兩：賀萬鈞進店，按到今天的兩數捐滿（一下 donate_step 兩）再多按一次；裴雲舟今天的點數已經滿了；邢孤雁錢不夠；霍青萍是散人。"""
        self.enter(self.DONOR_G)
        self.menu(self.DONOR_G, "捐銀兩前", "act:silver_donate")
        for k in range(14):
            self.press(self.DONOR_G, "act:silver_donate", f"第 {k + 1} 下")
            if k in (2, 5):
                self.me(self.DONOR_G, f"捐銀兩 {k + 1} 下")
        self.me(self.DONOR_G, "捐銀兩之後")
        self.leave(self.DONOR_G)
        self.press(self.DONOR_G, "act:silver_donate", "沒進店直接按（清單外）")
        self.enter(self.DONOR_H)
        self.menu(self.DONOR_H, "點數滿了", "act:silver_donate")
        self.press(self.DONOR_H, "act:silver_donate", "點數滿了")
        self.leave(self.DONOR_H)
        self.enter(self.POOR)
        self.menu(self.POOR, "錢不夠", "act:silver_donate")
        self.press(self.POOR, "act:silver_donate", "錢不夠")
        self.edit(self.POOR, lambda p: p.stats.update({"silver": 3}))
        self.press(self.POOR, "act:silver_donate", "不到一點")
        self.leave(self.POOR)
        self.silver_of(self.POOR, 0)
        self.press(self.LONE, "act:dadian", "散人")
        self.press(self.LONE, "act:silver_donate", "散人")
        with self.tuned("silver_outlets", donate_daily_silver=150, donate_step=100):
            self.silver_of(self.DONOR_H, 500)
            self.edit(self.DONOR_H, lambda p: (setattr(p, "donated_today", 0), setattr(p, "donate_day", -1)))
            self.enter(self.DONOR_H)
            for k in range(3):
                self.press(self.DONOR_H, "act:silver_donate", f"兩數上限第 {k + 1} 下")
            self.leave(self.DONOR_H)
        self.me(self.DONOR_H, "兩數上限之後")
        self.world_view("捐銀兩之後")

    def bribe(self) -> None:
        """打點門路：駱風吟進店，在大勢人物所在的地方按打點（成、今天打過了）、再按一個不在這裡的人物、情誼到頂（上限調成 0）、錢不夠、不在這裡的人。"""
        fid = self.fig_id or "none_such"
        self.enter(self.FIG)
        self.menu(self.FIG, "有人物", "act:bribe:")
        self.press(self.FIG, f"act:bribe:{fid}", "第一次")
        self.press(self.FIG, f"act:bribe:{fid}", "今天打點過了")
        self.press(self.FIG, "act:bribe:none_such", "不在這裡的人物")
        self.me(self.FIG, "打點之後")
        self.silver_of(self.FIG, 10)
        self.day_reset(self.FIG)
        self.press(self.FIG, f"act:bribe:{fid}", "隔天錢不夠")
        self.silver_of(self.FIG, 500)
        self.day_reset(self.FIG)
        with self.tuned("silver_outlets", bribe_max=0):
            self.menu(self.FIG, "情誼到頂", "act:bribe:")
            self.press(self.FIG, f"act:bribe:{fid}", "情誼到頂")
        self.press(self.FIG, f"act:bribe:{fid}", "錢夠了再打點")
        self.leave(self.FIG)
        self.place(self.FIG, self.clinic)
        self.press(self.FIG, f"act:bribe:{fid}", "人物不在這裡（沒進店）")
        self.place(self.FIG, self.fig_loc)
        self.me(self.FIG, "打點完")

    def furnace(self) -> None:
        """看火候：柳尋芳進店（有鐵匠鋪的城鎮），按（成、請了還沒開爐、錢不夠）；今天不能再請；不在鐵匠鋪的城鎮。"""
        self.enter(self.SMITH)
        self.menu(self.SMITH, "有鐵匠鋪", "act:furnace")
        self.press(self.SMITH, "act:furnace", "第一次")
        self.press(self.SMITH, "act:furnace", "請了還沒開爐")
        self.edit(self.SMITH, lambda p: setattr(p, "furnace_ready", False))
        self.press(self.SMITH, "act:furnace", "今天請過了")
        self.day_reset(self.SMITH)
        self.silver_of(self.SMITH, 1)
        self.press(self.SMITH, "act:furnace", "隔天錢不夠")
        self.leave(self.SMITH)
        self.me(self.SMITH, "看火候之後")
        self.press(self.FIG, "act:furnace", "不在鐵匠鋪")

    def shop(self) -> None:
        """「打點」那一間店：史臨淵進去、看選單、在裡頭請一次名師指點（掮客換一句）、再請一次、買丹（錢不夠、買到這一季買滿）、離開；
        散人看不到這間店；銀兩出口關著時按進去。"""
        self.menu(self.CLINIC, "此地還能做", "act:dadian")
        self.enter(self.CLINIC)
        self.menu(self.CLINIC, "店裡", "act:", "dadian:")
        self.silver_of(self.CLINIC, 20)
        self.press(self.CLINIC, "act:buy_legend", "錢不夠買丹")
        self.press(self.CLINIC, "act:mentor", "錢不夠請指點")
        self.silver_of(self.CLINIC, 5000)
        self.press(self.CLINIC, "act:mentor", "店裡請指點")
        self.press(self.CLINIC, "act:mentor", "店裡再請一次")
        for k in range(4):
            self.press(self.CLINIC, "act:buy_legend", f"買丹第 {k + 1} 次")
        self.me(self.CLINIC, "買丹買滿")
        self.day_reset(self.CLINIC)
        self.press(self.CLINIC, "act:mentor", "清了帳再請指點")
        self.leave(self.CLINIC)
        self.me(self.CLINIC, "出店之後")
        self.menu(self.LONE, "散人", "act:dadian")
        self.press(self.LONE, "act:dadian", "散人進店")
        with self.tuned("silver_outlets", enabled=False):
            self.menu(self.CLINIC, "銀兩出口關著", "act:dadian", "act:mentor")
            self.press(self.CLINIC, "act:dadian", "關著進店")
            self.press(self.CLINIC, "act:mentor", "關著請指點")
            self.press(self.CLINIC, "act:silver_donate", "關著捐銀兩")
            self.press(self.CLINIC, "act:buy_legend", "關著買丹")
            self.press(self.CLINIC, "act:furnace", "關著看火候")
            self.press(self.CLINIC, "act:bribe:none_such", "關著打點")

    def open_two(self) -> None:
        """寫到一半的兩個人：計玄機坐在「打點」店裡沒離開，石開山開著軍需官那一串沒離開（前半停在這裡）。"""
        self.place(self.SHOP_IN, self.clinic)
        self.silver_of(self.SHOP_IN, 3000)
        self.press(self.SHOP_IN, "act:dadian", "進店")
        self.main(self.SHOP_IN)
        self.place(self.DONATE_IN, self.base.get("guan", self.clinic))
        self.bag(self.DONATE_IN, low=6, high=1)
        self.press(self.DONATE_IN, "act:donate", "打開軍需官")
        self.main(self.DONATE_IN)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".outlets.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".outlets.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        for who in list(self.clients):
            self.relogin(who)
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "接手")

    def in_shop(self) -> None:
        """接著坐在店裡的人：看選單、請一次指點（掮客換一句）、買丹、離開。"""
        self.menu(self.SHOP_IN, "接手後店裡", "act:", "dadian:")
        self.press(self.SHOP_IN, "act:mentor", "接手後請指點")
        self.press(self.SHOP_IN, "act:buy_legend", "接手後買丹")
        self.press(self.SHOP_IN, "dadian:back", "接手後離開")
        self.me(self.SHOP_IN, "出店之後")
        self.main(self.SHOP_IN)

    def in_donate(self) -> None:
        """接著開著軍需官那一串的人：按一種、按離開；離開之後再按一次 donate:back（清單外）。"""
        opts = self.menu(self.DONATE_IN, "接手後軍需官", "donate:")
        pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i not in ("donate:back", "donate:room")), None)
        if pick is not None:
            self.press(self.DONATE_IN, pick, "接手後按一種")
        self.press(self.DONATE_IN, "donate:back", "接手後離開")
        self.press(self.DONATE_IN, "donate:back", "離開之後再按")
        self.me(self.DONATE_IN, "離開軍需官之後")

    def shut(self) -> None:
        """店開著、設定在這之間被關掉：計玄機再進店、石開山再開軍需官，這時把銀兩出口與捐軍備關掉，一同步就收店。"""
        self.press(self.SHOP_IN, "act:dadian", "再進店")
        self.press(self.DONATE_IN, "act:donate", "再開軍需官")
        self.me(self.SHOP_IN, "關掉之前")
        with self.tuned("silver_outlets", enabled=False):
            self.main(self.SHOP_IN)
            self.me(self.SHOP_IN, "銀兩出口關掉之後")
        with self.tuned("economy", donate=False):
            self.main(self.DONATE_IN)
            self.me(self.DONATE_IN, "捐軍備關掉之後")
            self.choose(self.DONATE_IN, "donate:back")
        self.main(self.SHOP_IN)
        self.main(self.DONATE_IN)

    def depart(self) -> None:
        """坐在店裡動身：計玄機進店之後走一步，店收起來；石開山開著軍需官也走一步。"""
        for who in (self.SHOP_IN, self.DONATE_IN):
            self.press(who, "act:dadian" if who == self.SHOP_IN else "act:donate", "進店再動身")
            # 坐著的選單是店裡那一串、沒有 move:：照酒肆軌，在鎖裡直接叫一次 Game._depart（收店那一行就在它裡面）
            from tianxia import atlas
            from tianxia.engine import Game

            here = self.chars.load(who).player.location
            dest = self.c.locations[here].connections[0]
            self.begin()
            with self.world.action_lock():
                game = Game(self.c, self.chars.load(who), world=self.world)
                game.sync(CLOCK[0])
                route = atlas.way_to(game.state, self.c, dest)
                emit(f"{who} 直接動身", game._depart(route, "walk") if route is not None else None)
                self.chars.save(game.state)
            self.me(who, "動身之後")

    def next_day(self) -> None:
        """換天：每一本帳重算（捐素材的點數、捐銀兩的兩數、指點與火候一天一次、打點每位一天一次）。"""
        self.forward_day()
        self.place(self.DONOR_G, self.base.get("guan", self.clinic))
        self.silver_of(self.DONOR_G, 2000)
        self.bag(self.DONOR_G, low=5)
        self.enter(self.DONOR_G)
        self.press(self.DONOR_G, "act:silver_donate", "換天捐銀兩")
        self.leave(self.DONOR_G)
        self.do(self.DONOR_G, "donate", {"material": self.mats[0] if self.mats else "none_such", "count": 5})
        self.me(self.DONOR_G, "換天之後")
        self.world_view("換天之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在自家大本營、背包有多的素材、手上有錢）若干輪；假人眼前的選單與分數；整季機器人眼前的選單挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        home = self.base.get("guan", sorted(self.c.locations)[0])
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, home, None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 900
            for mid in self.mats[:2]:
                p.materials[mid] = 30
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_OUTLETS_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "silver": p.stats.get("silver", 0), "materials": dict(sorted(p.materials.items())),
                                  "donate": [p.donate_day, p.donated_today], "picking": [p.picking_donate, p.picking_dadian],
                                  "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "糧官丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, home, None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        p.stats["silver"] = 900
        for mid in self.mats[:2]:
            p.materials[mid] = 30
        p.bot = BotProfile(personality="普通", seed=77, faction=p.faction, season_number=self.world.get_season_number())
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        emit("假人眼前的分數", [[o.id, bot_policy.score(solo, o, p.bot)] for o in opts if o.id in ("act:donate", "act:dadian")])
        for flag, door in (("picking_donate", "act:donate"), ("picking_dadian", "act:dadian")):
            if not any(o.id == door for o in opts):
                emit(f"{door} 不在選單上，直接擺 {flag}", None)
            setattr(p, flag, True)
            inside = solo.options(odds=False)
            emit(f"坐在店裡 {flag} 的選單", [o.id for o in inside])
            emit(f"坐在店裡 {flag} 的分數", [[o.id, bot_policy.score(solo, o, p.bot)] for o in inside])
            emit(f"坐在店裡 {flag} 整季機器人挑的", sorted({str(bot.pick(solo, inside, random.Random(k))) for k in range(40)}))
            setattr(p, flag, False)

    def season(self) -> None:
        """收季、開下一季：手上的指點與火候、買過幾枚丹、開著的店、各本帳怎麼帶。"""
        self.place(self.CLINIC, self.clinic)
        self.silver_of(self.CLINIC, 5000)
        self.press(self.CLINIC, "act:dadian", "收季前進店")
        self.me(self.CLINIC, "收季前")
        self.do(ADMIN, "end_season")
        for who in (self.CLINIC, self.DONOR_G, self.DONATE_IN):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.CLINIC, self.DONOR_G, self.DONATE_IN, self.POOR):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


def _outlets_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _military_register_track）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：捐軍備記貢獻那一句（搬之前在 engine.py 的 _credit_donation、之後在 tianxia/features/outlets/ 的捐軍備動作檔；
# 第 2 項是之前的檔名，搬的人照實際的檔名改第 1 項的字串）
_outlets_register_track("outlets", OutletsScenario, (("tianxia/features/outlets/donate_actions.py", "tianxia/engine.py"),
                                                     ('msgs.append(f"貢獻 +{total}")', 'msgs.append(f"貢獻 +{total}！")')), "week7")


# ═══════════════════════════ craft：煉製與自創一軌（全部拆包第 44 批，dev/craft-1） ═══════════════════════════
# 意境合成與揣摩（取名三段式 A、B、C：Game.forge_request／server.prepare_forge／Game.forge 的重驗；預覽 /api/forge_line）、自創五步
# （執器、擺式、立意〔三段式〕、成形、立名）、重悟帖（重骰形、重讀這句意〔三段式〕）、作罷的本體從 engine.py 與 tianxia/create.py 搬進
# tianxia/features/craft/（舊名留成別名；計畫 docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md）。這一段整塊是這一批的：接在檔尾、
# 最後一行登記（_craft_register_track），PM 合的時候不跟別人的行穿插。角色與意境、武學、招式的名字都是原創的（第 22 批 PM 認定第 3 條）。

CRAFT_READ = {"score": 82, "attributes": ["柔", "虛"], "lean": "正", "move": "拂雲式", "say": "身子一擰便繞了過去"}
CRAFT_REREAD = {"score": 71, "attributes": ["剛"], "lean": "邪", "move": "裂冰式", "say": "掌勢一沉便壓了下去"}
_CRAFT_CLIENTS: dict[type, type] = {}


def _craft_client(base: type) -> type:
    """煉製與自創的假模型（疊在 _setup_child 那一層上）：MODEL["craft_name"]（{name, description}）給了時 NameReply 回它（取名、挑一個）；
    MODEL["craft_read"]（IntentReading 的欄位）給了時 IntentReading 回它。沒給的照 base（立刻丟連線錯誤＝模型擋著）。"""
    if base not in _CRAFT_CLIENTS:
        class CraftClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "NameReply" and MODEL.get("craft_name") is not None:
                    return schema(**MODEL["craft_name"])
                if schema.__name__ == "IntentReading" and MODEL.get("craft_read") is not None:
                    return schema(**MODEL["craft_read"])
                return super().chat_structured(messages, schema, *a, **k)

        _CRAFT_CLIENTS[base] = CraftClient
    return _CRAFT_CLIENTS[base]


class CraftScenario(Scenario):
    """煉製與自創（全部拆包第 44 批；--track craft，自己一個資料庫）。
    - 籌備中（管理者還沒開季）：煉製頁與自創的每一顆都回「賽季籌備中」，開爐的 A 段（forge_request）是 None。
    - 煉製頁的預覽（/api/forge_line）：空爐、放一個、放兩個（合得了、合不了）、放武學、放不認得的、形狀不對的 body。
    - 開爐的取名三段式：被拒絕的幾種（爐裡一個、放武學、不在手上、同一種只有一份、心得不夠）不開單；兩種不同的意境首創——模型回了（名字進
      江湖）、模型擋著（走退路字表）、模型回的名字撞了現成的意境（C 段重驗過不了，走退路字表）；同一個配方第二個人合（已登記，不叫模型）；
      同一種的兩份是揣摩（不取名）；揣摩到極處被擋。
    - 自創五步：執器（種類不對、形不對）、擺式、立意〔三段式：太短、太長、模型回了、模型擋著走關鍵字表〕、成形、回頭（立意回擺式免費、成形回頭
      用掉一次重來、沒得回）、立名（名字太短、撞名、招名不合、做成了寫一則紀錄）、作罷（沒有單子、付過了的）；重悟帖（沒有帖、重骰形、重讀這句意
      〔三段式：模型回了、模型擋著不扣帖〕、骰滿了）。
    - **前半停在自創走到一半**：擺式那一步（剛執器）、立意那一步（剛擺好式）、成形還沒立名（手上有兩張重悟帖，已經重骰過一次）、舊存檔的三步單子
      （沒有 form，讀檔時收掉）、煉製頁的那一爐已經合好一個意境還沒再合。
    - 後半第一件事：新程式接著走——擺式的接著擺、立意的接著三段式、成形的重讀（模型回了）、重骰（骰滿）、回頭、立名；舊單子被收掉、重開；
      煉製頁接著合；煉製頁與門下頁的資料（create_view）。換季：走到一半的單子跟新角色重來。
    - 假人：BotRunner 兩個（心得多、手上有意境；bot_policy.tend_arts 的合一爐與自創一門）；整季機器人眼前的選單。
    沒有自創的內容（測試內容若關著）同一串 API 照打，寫被擋的那一句。"""

    FORGER, BLOCKED, DEEPER = "墨簷", "雲杪", "竹渚"
    MAKER, SECOND, REROLLER = "霜葉", "寒汀", "松檐"
    H_POSE, H_INTENT, H_NAME, H_OLD, H_FURNACE = "星砌", "石岫", "葦渡", "舊簿", "爐前"
    PLAYERS = [FORGER, BLOCKED, DEEPER, MAKER, SECOND, REROLLER, H_POSE, H_INTENT, H_NAME, H_OLD, H_FURNACE]
    BOT_SEATS = ["匠甲", "匠乙"]
    PHASES_FIRST = ["setup", "preview", "refused", "forge_first", "forge_again", "deepen", "create_steps", "create_name", "reroll", "half"]
    PHASES_SECOND = ["resume", "views", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _craft_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    @contextlib.contextmanager
    def model(self, name: dict | None = None, read: dict | None = None):
        """這幾下模型回的東西（取名／挑一個；讀這一句意）；出來就是擋著。"""
        MODEL["craft_name"], MODEL["craft_read"] = name, read
        emit("模型", {"name": name, "read": read})
        try:
            yield
        finally:
            MODEL["craft_name"] = MODEL["craft_read"] = None

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def menxia(self, who: str):
        return self.call(who, "GET", "/api/menxia")[1]

    def line(self, who: str, body: dict):
        return self.call(who, "POST", "/api/forge_line", body)[1]

    def forge(self, who: str, ids) -> None:
        self.mx(who, "forge", {"insights": ids})

    def give(self, who: str, insights: list[str], xinde: int = 20000) -> None:
        def fn(p):
            p.insights.extend(i for i in insights if i not in p.insights)
            p.stats["xinde"] = xinde
            p.stamina = float(self.c.config.stamina_max)
        self.edit(who, fn)

    def base_insights(self) -> list[str]:
        return sorted(self.c.insights)[:6]

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟煉製與自創有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "insights": list(p.insights), "own": sorted(p.own_insights), "arts": list(p.arts), "wugong": p.member.wugong_id,
            "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())),
            "xinde": p.stats.get("xinde"), "stamina": p.stamina, "created_count": p.created_count, "rerolls": p.create_rerolls,
            "creating": None if p.creating is None else p.creating.model_dump(),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def recipes(self, tag: str) -> None:
        """全服登記的配方（名字進江湖）：整份資料庫的雜湊。"""
        emit(tag, hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

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
        for who in self.PLAYERS:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        # 籌備中：煉製頁與自創的每一顆都擋
        who = self.FORGER
        ins = self.base_insights()
        self.line(who, {"insights": ins[:2]})
        self.forge(who, ins[:2])
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": {}})
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_name", {"name": "籌備中的名", "move": ""})
        self.mx(who, "create_cancel")
        self.mx(who, "create_reroll")
        self.do(who, "create_intent", {"text": "籌備中的一句意"})
        self.do(who, "create_reread", {"text": "籌備中的一句意"})
        self.menxia(who)
        self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, None)  # 體力補滿、過了新手期
        ins = self.base_insights()
        for who in self.PLAYERS:
            self.give(who, ins)
        self.edit(self.DEEPER, lambda p: p.insights.extend(f"{ins[0]}~{n}" for n in (2, 3, 4) if f"{ins[0]}~{n}" not in p.insights))

    def preview(self) -> None:
        """煉製頁選了東西就更新說明（/api/forge_line）：空爐、一個、兩個不同的、兩份同一種、放武學、不認得的、形狀不對的。"""
        who, ins = self.FORGER, self.base_insights()
        art = self.chars.load(who).player.member.wugong_id or "jichu_quanjiao"  # 測試內容的人手上沒有武學
        for body in ({}, {"insights": []}, {"insights": ins[:1]}, {"insights": ins[:2]}, {"insights": [ins[0], ins[0]]},
                     {"insights": ins[1:3]}, {"insights": ins[2:4]}, {"art": art, "insights": ins[:1]}, {"insights": ["沒有這個意境"]},
                     {"insights": [ins[0], "沒有這個意境"]}, {"insights": "不是串列"}, {"insights": [ins[0], 3]}):
            self.line(who, body)
        self.line(self.DEEPER, {"insights": [ins[0], f"{ins[0]}~2"]})
        self.line(self.DEEPER, {"insights": [f"{ins[0]}~2", f"{ins[0]}~3"]})

    def refused(self) -> None:
        """開爐被拒絕的幾種（不開取名的單子、什麼都不收）：爐裡一個、三個、放武學、不在手上、同一種只有一份、心得不夠、體力不夠。"""
        who, ins = self.FORGER, self.base_insights()
        art = self.chars.load(who).player.member.wugong_id or "jichu_quanjiao"  # 測試內容的人手上沒有武學
        with self.model({"name": "不該用到的名", "description": "不會用到"}):
            self.forge(who, ins[:1])
            self.forge(who, ins[:3])
            self.forge(who, [])
            self.mx(who, "forge", {"art": art, "insights": ins[:2]})
            self.forge(who, [ins[0], "沒有這個意境"])
            self.forge(who, [ins[0], ins[0]])
            self.edit(who, lambda p: p.stats.__setitem__("xinde", 0))
            self.forge(who, ins[:2])
            self.edit(who, lambda p: (p.stats.__setitem__("xinde", 20000), setattr(p, "stamina", 0.0)))
            self.forge(who, ins[:2])
            self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
        self.state_of(who, "被拒絕之後")

    def forge_first(self) -> None:
        """兩種不同的意境首創：模型回了（名字進江湖）、模型擋著（退路字表）、模型回的名字撞了現成的意境（走退路字表）。"""
        ins = self.base_insights()
        with self.model({"name": "霧簷意", "description": "簷下霧氣不散的意思"}):
            self.forge(self.FORGER, ins[:2])
        self.state_of(self.FORGER, "模型回了之後")
        self.forge(self.BLOCKED, ins[2:4])  # 模型擋著
        self.state_of(self.BLOCKED, "模型擋著之後")
        clash = self.c.insights[ins[0]].name
        with self.model({"name": clash, "description": "撞名的說明"}):
            self.forge(self.DEEPER, ins[4:6])
        self.state_of(self.DEEPER, "撞名之後")
        self.recipes("首創之後")

    def forge_again(self) -> None:
        """同一個配方第二個人合（已登記，不叫模型）；同一個人再合一次（已經悟得）；合到舊的意境。"""
        ins = self.base_insights()
        with self.model({"name": "不該再取的名", "description": "不會用到"}):
            self.forge(self.MAKER, ins[:2])
            self.forge(self.MAKER, ins[:2])
            self.forge(self.SECOND, ins[2:4])
        self.state_of(self.MAKER, "第二個人合之後")
        self.state_of(self.SECOND, "第二個人合之後")

    def deepen(self) -> None:
        """同一種的兩份是揣摩（不取名）：揣摩幾次，揣摩到極處被擋。"""
        who, ins = self.DEEPER, self.base_insights()
        with self.model({"name": "不該取的名", "description": "不會用到"}):
            for _ in range(4):
                held = [i for i in self.chars.load(who).player.insights if i == ins[0] or i.startswith(f"{ins[0]}~")]
                if len(held) < 2:
                    break
                self.forge(who, held[:2])
                self.edit(who, lambda p: (p.stats.__setitem__("xinde", 20000), setattr(p, "stamina", float(self.c.config.stamina_max))))
        self.state_of(who, "揣摩之後")

    def create_steps(self) -> None:
        """自創的前三步：種類不對、形不對、沒執器就擺式、立意（太短、太長、模型回了）、回頭。"""
        from tianxia import create

        who = self.MAKER
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})  # 沒執器
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_cancel")  # 沒有單子
        self.mx(who, "create_reroll")
        self.mx(who, "create_begin", {"kind": "不是內功也不是武學", "form": "拳腳"})
        self.mx(who, "create_begin", {"kind": "武學", "form": "沒有這種兵器"})
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.do(who, "create_intent", {"text": "還沒擺式"})  # 擺式還沒做
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(who, "create_pose", {"pose": "不是字典"})
        self.do(who, "create_intent", {"text": "短"})
        self.do(who, "create_intent", {"text": "這是一句寫得太長太長太長太長太長太長太長太長太長太長太長太長的意"})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "風過林梢，影不留痕"})  # 三段式：模型回了
        self.state_of(who, "立意之後")
        self.mx(who, "create_back", {"to": "name"})  # 不能往前
        self.mx(who, "create_back", {"to": "intent"})  # 成形之後回頭：用掉一次重來
        self.mx(who, "create_back", {"to": "pose"})  # 沒有重來了（立意那一步不再走回頭用掉的）
        self.state_of(who, "回頭之後")
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        self.do(who, "create_intent", {"text": "水落石出，不留餘地"})  # 模型擋著：關鍵字表
        self.state_of(who, "模型擋著立意之後")

    def create_name(self) -> None:
        """立名：太短、撞名（先有人用了）、招名不合、成功；另一個人模型擋著走完、作罷（付過了）。"""
        from tianxia import create

        who = self.MAKER
        self.mx(who, "create_name", {"name": "拳", "move": ""})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": "太長太長太長"})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": "拂雲式"})
        self.state_of(who, "立名之後")
        self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 單子已經收了
        who = self.SECOND
        self.mx(who, "create_begin", {"kind": "內功", "form": self.inner_form()})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        self.do(who, "create_intent", {"text": "靜水深流，不爭一日"})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 撞名
        self.mx(who, "create_cancel")  # 付過了：作罷
        self.state_of(who, "作罷之後")
        self.mx(who, "create_cancel")
        self.menxia(who)

    def inner_form(self) -> str:
        """內功的行功之法（表上第一個；沒有就空著，讓引擎回那一句）。"""
        from tianxia import create

        forms = create.forms_of(self.c, "內功")
        return forms[0].key if forms else ""

    def reroll(self) -> None:
        """重悟帖：沒有帖、重骰形（模型不用）、重讀這句意（模型回了、模型擋著不扣帖、改寫太短）、骰滿了。"""
        from tianxia import create

        who = self.REROLLER
        self.mx(who, "create_reroll")  # 沒有單子
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(who, "create_reroll")  # 還沒成形
        self.do(who, "create_reread", {"text": "還沒成形的重讀"})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "寒潭映月，一劍西來"})
        self.mx(who, "create_reroll")  # 沒有帖
        self.do(who, "create_reread", {"text": "寒潭映月，一劍西來"})
        self.edit(who, lambda p: setattr(p, "create_rerolls", 6))
        self.mx(who, "create_reroll")
        self.state_of(who, "重骰形之後")
        self.do(who, "create_reread", {"text": "寒潭映月，一劍西來"})  # 模型擋著：不扣帖
        self.do(who, "create_reread", {"text": "短"})
        with self.model(read=CRAFT_REREAD):
            self.do(who, "create_reread", {"text": "寒潭映月，劍氣橫秋"})
        self.state_of(who, "重讀之後")
        for _ in range(4):  # 骰到上限
            self.mx(who, "create_reroll")
        self.state_of(who, "骰滿之後")

    def half(self) -> None:
        """前半停在這裡：擺式那一步、立意那一步、成形還沒立名（兩張帖，重骰過一次）、舊存檔的三步單子、煉製頁那一爐合好一個。"""
        from tianxia import create
        from tianxia.state import CreateDraft

        self.mx(self.H_POSE, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_INTENT, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_INTENT, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(self.H_NAME, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_NAME, "create_pose", {"pose": create.preset(self.c, "進擊")})
        with self.model(read=CRAFT_READ):
            self.do(self.H_NAME, "create_intent", {"text": "蘆葦蕩裡，一葉渡江"})
        self.edit(self.H_NAME, lambda p: setattr(p, "create_rerolls", 2))
        self.mx(self.H_NAME, "create_reroll")
        self.edit(self.H_OLD, lambda p: setattr(p, "creating", CreateDraft(kind="武學", step="name")))  # 沒有 form：三步時代的單子
        ins = self.base_insights()
        with self.model({"name": "星砌意", "description": "階前星影的意思"}):
            self.forge(self.H_FURNACE, ins[:2])
        for who in (self.H_POSE, self.H_INTENT, self.H_NAME, self.H_OLD, self.H_FURNACE):
            self.state_of(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        """新程式接著走：擺式的接著擺、立意的接著三段式、成形的重讀與重骰再立名、舊單子收掉重開、煉製頁接著合。"""
        from tianxia import create

        self.login_all()
        for who in (self.H_POSE, self.H_INTENT, self.H_NAME, self.H_OLD, self.H_FURNACE):
            self.state_of(who, "接手時")
        who = self.H_POSE
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "星河落處，萬籟俱寂"})
        self.mx(who, "create_name", {"name": "星砌拳", "move": ""})
        self.state_of(who, "走完之後")
        who = self.H_INTENT
        self.do(who, "create_intent", {"text": "石上清泉，流而不竭"})  # 模型擋著
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_cancel")
        self.state_of(who, "作罷之後")
        who = self.H_NAME
        with self.model(read=CRAFT_REREAD):
            self.do(who, "create_reread", {"text": "蘆葦蕩裡，一葉渡江"})
        self.mx(who, "create_reroll")  # 骰滿了
        self.mx(who, "create_name", {"name": "葦渡掌", "move": "裂冰式"})
        self.state_of(who, "走完之後")
        who = self.H_OLD
        self.menxia(who)
        self.mx(who, "create_name", {"name": "舊簿掌", "move": ""})  # 單子被收掉了
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.state_of(who, "舊單子之後")
        who = self.H_FURNACE
        ins = self.base_insights()
        with self.model({"name": "星砌意", "description": "階前星影的意思"}):
            self.forge(who, ins[:2])  # 已經悟得
            self.forge(who, ins[2:4])
        self.state_of(who, "走完之後")
        self.recipes("接手之後")

    def views(self) -> None:
        """煉製頁與門下頁的資料（create_view、預覽）：每個人看一遍。"""
        ins = self.base_insights()
        for who in self.PLAYERS:
            self.menxia(who)
            self.line(who, {"insights": ins[:2]})
            self.main(who)

    def bots(self) -> None:
        """伺服器假人兩個（BotRunner：bot_policy.tend_arts 合一爐、自創一門）：心得多、手上有意境。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        ins = self.base_insights()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            p.insights.extend(i2 for i2 in ins if i2 not in p.insights)
            p.stats["xinde"] = 20000
            p.stamina = float(self.c.config.stamina_max)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_CRAFT_TICKS", "12"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                              named=report.named)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"insights": list(p.insights), "arts": list(p.arts), "created": p.created_count,
                                  "creating": None if p.creating is None else p.creating.model_dump(),
                                  "titles": dict(sorted(Counter(e.title.partition("・")[0] for e in s.journal).items())),
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        from tianxia import bot

        solo = Game.new(self.c, "匠丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        p = solo.state.player
        p.insights.extend(i2 for i2 in ins if i2 not in p.insights)
        p.stats["xinde"] = 20000
        p.tutorial_step = len(self.c.tutorial.steps)
        emit("整季機器人挑的爐", sorted({str(bot.pick_forge(solo, random.Random(k))) for k in range(30)}))

    def season(self) -> None:
        """收季、開下一季：走到一半的單子跟新角色重來。"""
        self.do(ADMIN, "end_season")
        for who in (self.H_INTENT, self.H_OLD, self.REROLLER):
            self.menxia(who)
        self.do(ADMIN, "next_season")
        for who in (self.H_INTENT, self.H_OLD, self.REROLLER, self.MAKER):
            self.menxia(who)
            self.state_of(who, "換季之後（動作前的存檔）")
            self.main(who)  # status.create.draft 才看得到單子有沒有清掉（/api/menxia 沒有單子）
            self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 單子清了應回「你還沒起意」
            self.state_of(who, "換季之後（動作後）")
        self.line(self.MAKER, {"insights": self.base_insights()[:2]})


def _craft_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _military_register_track）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：重悟帖沒有帖那一句（搬之前在 tianxia/create.py、之後在 tianxia/features/craft/ 的規則模組；第 2 項是之後的檔名，
# 搬的人照實際的檔名改這一個字串）。抓到的地方：松檐重骰形的第一下
_craft_register_track("craft", CraftScenario, (("tianxia/features/craft/create.py", "tianxia/create.py"),
                                               ('NO_REROLL = "手上沒有重悟帖：萬寶閣買得到。"', 'NO_REROLL = "手上沒有重悟帖：萬寶閣買得到！"')), "week7")


# ═══════════════════════════ world：世界層一軌（全部拆包第 25 批，dev/core-world-1） ═══════════════════════════
# 世界層掛鉤（世界一步、每週、每天；世界層的開季與換季；全服收季；開集結）：world.py、sqlite_world.py 裡直接叫包與舊模組的地方改叫核心的
# 掛鉤，world.py 收進核心本體（計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記
# （_world_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。


class WorldScenario(Scenario):
    """世界層一軌（全部拆包第 25 批；--track world，自己一個資料庫）。順序就是行為：每一段都把世界層這一下動到的帳（季曆、週初與每天的掛鉤跑到哪、
    軍令與懸賞、宴席、擂台名次、題壁、決戰、天下大事與江湖史的尾巴）寫出來，同一步裡誰先推誰後推，天下大事與江湖史的先後就看得出來。
    開季（setup：管理者開季、開季那一刻結算第 1 週；21 天季第一件決戰在開季那一刻自然開集結）；擺局面：宴席兩桌（三個世界時之後散、四百天之後才散）、
    擂台五個人（四個打過、一個沒打過）、題壁兩則（花錢的、預設的）；一次快轉跨過下一個週一再進四成（同一個請求裡跨好幾個季曆天與一個週一；
    快散的那一桌散席）；照時刻表開集結（管理者開第一件還沒開過的決戰：起點照戰線、屯糧、玉璽、龍頭上陣那四格）再取消；**前半停在世界一步推到一半**
    （週初與每天的掛鉤跑到這一週的中間；一連串的宴席剛擺、後半那一次快轉的每一個世界時散一桌；季上記下一場待開的仗；擂台還沒排名次；題壁在）。
    後半：接手那一下同步處理待開的仗；再一次快轉跨過下一個週一再進四成（週初與每天的掛鉤；那一連串的宴席一步散一桌）；大勢門檻開集結（管理者觸發標了開戰的門檻）
    再取消；假人（BotRunner 兩個、整季機器人眼前的選單）；管理者立刻收季（擂台前三名、榜單、四勝利）；開下一季（題壁照帶、玉璽、神器、開季結算）；
    新的一季再擺擂台與兩桌宴席，一次快轉從開季推到季末自然收季（同一個請求裡跨過每一個週一與每一個季曆天；同一步裡先散席、再收季、再排擂台）；
    再開下一季。
    沒有時刻表、沒有門檻開戰的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    G1, G2, H1, H2, LONE = "穆遠舟", "賀青崖", "邵寒汀", "童晚照", "柯半山"
    PLAYERS = {G1: "guan", G2: "guan", H1: "huang", H2: "huang", LONE: None}
    BOT_SEATS = ["世甲", "世乙"]
    PHASES_FIRST = ["setup", "seat", "stage", "days", "muster_table", "half"]
    PHASES_SECOND = ["resume", "weeks", "muster_trend", "bots", "close_now", "next_one", "close_due", "next_two"]

    # ── 小工具 ──

    def hub(self) -> str:
        return self.c.scenario.start_location

    def point(self) -> dict:
        from tianxia import calendar

        s = self.world.get_season()
        at = calendar.point(s.time, self.c, s)
        return {"time": round(s.time, 3), "week": at.week, "weekday": at.weekday, "hour": at.hour, "cal_day": at.cal_day}

    @staticmethod
    def _digest_of(items) -> str:
        return hashlib.sha256(json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

    def season_view(self, tag: str) -> None:
        """世界層這一下動到的帳：季曆與掛鉤跑到哪、軍令與懸賞（雜湊）、宴席、擂台、題壁、決戰、時刻表、天下大事與江湖史的尾巴。"""
        w = self.world.get_season()
        b = self.world.get_battle()
        emit(f"世界 {tag}", {
            "season": self.world.get_season_number(), "phase": self.world.season_phase(), "at": self.point(),
            "hooked_week": w.hooked_week, "hooked_day": w.hooked_day, "ended": w.ended, "ending": w.ending_id,
            "timeline": list(w.timeline), "waiting": list(w.showdowns_waiting), "opened": dict(w.showdowns_opened),
            "pending": w.pending_battle, "fired": sorted(w.fired_thresholds),
            "orders": [len(w.orders), self._digest_of(w.orders)], "bounties": [len(w.bounties), self._digest_of(w.bounties)],
            "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "feasts": [[f.id, f.settled, f.best] for f in w.feasts],
            "arena": [[e.name, e.rank, e.place, e.bouts] for e in sorted(w.arena.values(), key=lambda e: (e.rank, e.name))],
            "arena_closed": w.arena_closed,
            "inscriptions": [[i.id, i.preset, i.text] for i in w.inscriptions], "inscription_seq": w.inscription_seq,
            "battle": None if b is None else [b.battle_id, b.phase, hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()[:16]],
            "rumors": [r.text for r in w.rumors][-8:], "chronicle": [r.text for r in w.chronicle][-8:]})

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {"loc": p.location, "faction": p.faction, "stamina": p.stamina, "silver": p.stats.get("silver"),
                              "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:4]]})

    def forward(self, hours: int, tag: str) -> None:
        """管理者快轉 hours 個世界時（Game.advance：同一個請求裡一步一步推，跨過的季曆天、週一都在這一下）。"""
        emit(f"快轉 {tag}", {"hours": hours, "before": self.point()})
        self.do(ADMIN, "fast_forward", {"hours": hours})
        self.season_view(f"快轉之後 {tag}")

    def hours_to(self, target: float) -> int:
        import math

        return max(1, math.ceil((target - self.world.get_season().time) / 3600))

    def stage_feasts(self, tag: str, ends: list[tuple[float, bool]]) -> None:
        """擺宴席（設宴是宴客包的事；這裡只要散席：ends 是 [(距現在幾個世界秒散, 有沒有人敬酒)]）。主人是內容的第一個對話人物。"""
        from tianxia.state import Feast, Toast

        host = sorted(self.c.characters)[0] if self.c.characters else "nobody"
        names = [self.G1, self.H1, self.LONE]

        def fn(s) -> None:
            for span, toasted in ends:
                s.feast_seq += 1
                toasts = [Toast(name=n, text=f"敬{n}一杯，願江湖太平{i}。", score=60 + 7 * i, at=s.time + i) for i, n in enumerate(names)] if toasted else []
                s.feasts.append(Feast(id=s.feast_seq, host=host, place=self.hub(), start=s.time, end=s.time + span, toasts=toasts))

        self.world.mutate_season(fn)
        emit(f"擺宴席 {tag}", {"host": host, "ends": ends})

    def stage_arena(self, tag: str) -> None:
        """擺擂台（報名、挑擂是單挑包的事；這裡只要收季那一刻排前三名）：四個打過的、一個沒打過的。"""
        from tianxia.characters import name_key
        from tianxia.state import ArenaEntry

        rows = [(self.G1, 1, 5, 1), (self.H1, 2, 3, 2), (self.G2, 3, 2, 2), (self.H2, 4, 1, 3), (self.LONE, 5, 0, 0)]

        def fn(s) -> None:
            s.arena = {}
            s.arena_closed = False
            for name, rank, wins, losses in rows:
                s.arena[name_key(name)] = ArenaEntry(name=name, power=100.0 + wins, hp_cap=120.0, rank=rank, wins=wins, losses=losses,
                                                     joined=float(rank))

        self.world.mutate_season(fn)
        emit(f"擺擂台 {tag}", [list(r) for r in rows])

    def stage_inscriptions(self) -> None:
        """題壁兩則（走一趟的路牌；花錢的換季照帶、預設的一季一清）。"""
        from tianxia.state import Inscription

        def fn(s) -> None:
            s.inscription_seq += 1
            s.inscriptions.append(Inscription(id=s.inscription_seq, place=self.hub(), text="路遠莫愁前無知己", author=self.G1, preset=False, time=s.time))
            s.inscription_seq += 1
            s.inscriptions.append(Inscription(id=s.inscription_seq, place=self.hub(), text="此路通往前方", author="", preset=True, time=s.time))

        self.world.mutate_season(fn)
        emit("擺題壁", None)

    def showdowns(self) -> list[str]:
        from tianxia import timetable

        return [e.id for e in timetable.events(self.world.get_season(), self.c) if e.kind == "showdown"]

    def cancel(self, tag: str) -> None:
        self.do(ADMIN, "cancel_battle")
        self.season_view(f"取消之後 {tag}")

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        self.season_view("開季之後")

    def seat(self) -> None:
        for who, side in self.PLAYERS.items():
            self.place(who, self.hub(), side)
            self.edit(who, lambda p: p.stats.update({"silver": 300}))
        for who in self.PLAYERS:
            self.main(who)
        self.season_view("坐定")

    def into_next_week(self, weeks: int) -> float:
        """從現在往後跨過 weeks 個週一、再進那一週的四成（季曆的週照這一季蓋的章；7 天的季一週不到兩個季曆天，21 天季一週七天）。"""
        from tianxia import calendar

        s = self.world.get_season()
        week = calendar.point(s.time, self.c, s).week
        start, after = calendar.week_start(week + weeks, self.c, s), calendar.week_start(week + weeks + 1, self.c, s)
        return start + 0.4 * (after - start)

    def stage(self) -> None:
        """宴席兩桌（一桌散在下一個週一 00:00〔同一步裡週初的掛鉤、月旦評、人物行事也寫〕、一桌四百天之後才散〔兩次收季都還沒散〕；第三桌前半最後才擺）、
        擂台、題壁。"""
        from tianxia import calendar

        s = self.world.get_season()
        monday = calendar.week_start(calendar.point(s.time, self.c, s).week + 1, self.c, s)
        self.stage_feasts("前半", [(max(3600.0, monday - 1.0 - s.time), True), (400 * 86400.0, True)])
        self.stage_arena("前半")
        self.stage_inscriptions()
        self.season_view("擺好")

    def days(self) -> None:
        """一次快轉跨過下一個週一、再進那一週的四成：同一個請求裡跨過好幾個季曆天（21 天季每天 00:00 的掛鉤跑好幾次）與一個週一；快散的那一桌散席。"""
        self.forward(self.hours_to(self.into_next_week(1)), "跨天")
        self.main(self.G1)
        self.me(self.G1, "跨天之後")

    def muster_table(self) -> None:
        """照時刻表開集結（管理者開第一件還沒開過的決戰：world.open_showdown → _open_claimed，起點照戰線、屯糧、玉璽、龍頭上陣），看一眼再取消。
        21 天季開季那一刻第一件就自然開了集結（settle_season_start → 等著開 → start_pending_battle → open_waiting_showdown）：先看一眼、取消，再開下一件。"""
        ids = self.showdowns()
        emit("時刻表的決戰", ids)
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.season_view("自然開的集結")
            self.cancel("自然開的")
        w = self.world.get_season()
        left = [i for i in ids if i not in w.showdowns_opened and i not in w.timeline]
        if not left:
            return
        # 兩軍屯的糧，屯糧這一下打開（三種設定都關著：關著的話屯糧那一格什麼都不寫，跟起點、龍頭上陣對調看不出來）
        self.world.mutate_season(lambda s: setattr(s, "supply", {"guan": 30, "huang": 12}))
        stock = self.c.config.stockpile
        before, stock.enabled = stock.enabled, True
        emit("擺屯糧", {"guan": 30, "huang": 12, "enabled_before": before})
        try:
            self.do(ADMIN, "start_showdown", {"id": left[0]})
        finally:
            stock.enabled = before
        self.season_view("時刻表開集結")
        self.main(self.H1)
        self.cancel("時刻表")

    def half(self) -> None:
        """前半停在世界一步推到一半：週初與每天的掛鉤跑到這一週的中間；擺一連串的宴席（後半那一次快轉一步散一桌）；季上記下一場待開的仗
        （背景推進跨過開戰門檻那樣：base 記下、head 下一次同步開——第一季規則的季照 season_one_off 不開，照樣寫出來）。"""
        s = self.world.get_season()
        # 一連串的宴席，後半那一次快轉的每一個世界時散一桌（單數有人敬酒、雙數冷清）：世界一步裡人物行事、盤算、月旦評寫傳聞的那幾步，同一步都有一桌
        # 散席，誰先誰後寫進天下大事的先後（宴客包那一格跟它前後的格對調看得出來）
        span = self.hours_to(self.into_next_week(1)) + 2
        self.stage_feasts("前半最後（一連串）", [(k * 3600.0 - 1.0, k % 2 == 1) for k in range(1, span + 1)])
        battle = next(iter(sorted({th.starts_battle for th in self.c.scenario.thresholds if th.starts_battle})), None) or next(iter(sorted(self.c.battles)), None)
        emit("記下待開的那一場", battle)
        if battle is not None:
            self.world.mutate_season(lambda s: setattr(s, "pending_battle", battle))
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in self.PLAYERS:
            self.main(who)
        self.season_view("接手")

    def weeks(self) -> None:
        """再一次快轉跨過下一個週一、再進那一週的四成（7 天的季與 21 天季都只有三週：前半進第 2 週、這裡進第 3 週，季末留給自然收季那一段
        一次推完）：週初的掛鉤（席次、軍令、懸賞、心意歸零）與每天的掛鉤在同一個請求裡跑；那一連串的宴席一步散一桌。前半記下的那一場仗在接手那一下同步
        （start_pending_battle）就處理了，這裡先收掉還開著的。"""
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.cancel("接手開的")
        self.forward(self.hours_to(self.into_next_week(1)), "跨週")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "跨週之後")

    def muster_trend(self) -> None:
        """大勢門檻開集結：管理者觸發標了開戰的門檻（_fire → _open_battle；第一季規則的季不開 beta 那一場，照樣寫出來），開了就取消。
        背景推進那一條（記下待開、下一次同步開）在切點那一下走過。沒有標開戰的門檻就什麼都不按。"""
        marked = sorted(th.id for th in self.c.scenario.thresholds if th.starts_battle)
        emit("標了開戰的門檻", marked)
        for fid in marked:
            self.do(ADMIN, "fire", {"id": fid})
            self.season_view(f"觸發 {fid}")
            self.cancel(f"觸發 {fid}")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在開局的地方、體力滿）若干輪（每一輪同步都推世界一步）；整季機器人眼前的選單。"""
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
            p.bot = BotProfile(personality="普通", seed=81 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_WORLD_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.season_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "世丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, self.hub(), None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def close_now(self) -> None:
        """管理者立刻收季（world.end_season：結局、痕跡、四勝利、擂台前三名、榜單；收兵）：第三桌宴席還沒散。"""
        self.do(ADMIN, "end_season")
        self.season_view("立刻收季之後")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "收季之後")

    def next_one(self) -> None:
        """開下一季（sqlite_world.next_season：玉璽、首創、題壁照帶、神器、天命、藏碎片、挪開半夜；開季那一刻結算）。"""
        self.do(ADMIN, "next_season")
        self.season_view("開下一季之後")
        for who in (self.G1, self.H2):
            self.main(who)
            self.me(who, "換季之後")

    def close_due(self) -> None:
        """新的一季：擺擂台與兩桌宴席（一桌在季末之前散、一桌季末還沒散），一次快轉推到季末自然收季（同一步裡先散席、再收季、再排擂台）。"""
        from tianxia import world as world_module

        s = self.world.get_season()
        end = world_module.season_end_time(s, self.c)
        self.stage_arena("新的一季")
        self.stage_feasts("新的一季", [(max(1.0, end - s.time), True), (end - s.time + 86400.0, True)])  # 第一桌剛好在收季那一步散
        self.forward(self.hours_to(end) + 2, "推到季末")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "自然收季之後")

    def next_two(self) -> None:
        self.do(ADMIN, "next_season")
        self.season_view("再開下一季之後")
        self.main(self.G1)
        self.me(self.G1, "再換季之後")


def _world_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _craft_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：集結號角那一句（world._open_battle：時刻表與大勢門檻兩條開集結的路都寫它；world.py 收進核心本體不搬家）
_world_register_track("world", WorldScenario, (("tianxia/world.py",), ("的集結號角已經吹響！", "的集結號角已經吹響。")), "week7")


# ═══════════════════════════ effects：效果與叛投一軌（全部拆包第 32 批，dev/core-effects-1） ═══════════════════════════
# 效果與叛投掛鉤（核心批）：rules.apply_effect 照效果欄位分派給主人（晉升、帶兵、招同伴、伏筆、碎片、屯糧、四勝利記帳，還有一條線的一步），
# 叛投那一刻各包清自己的進度（計畫 docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記
# （_effects_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。
# 對照用的事件（FX_PREFIX 開頭）只加進這一個子行程手上的內容（actions 是空的：探索抽不到，只擺到眼前），效果的值照內容裡第一則寫了那個欄位的
# 事件抄（沒有的照 fallback 補），base 與 head 加的一模一樣；只打公開的 API 按下去。

FX_PREFIX = "sbfx_"
FX_SKIP = ("next_event", "contribution")  # apply_effect 不讀的兩個欄位（串接是事件檢定的事；contribution 只准寫在隨口應對的分岔上）


class EffectsScenario(Scenario):
    """效果與叛投一軌（全部拆包第 32 批；--track effects，自己一個資料庫）。
    一則一種（single）：照 apply_effect 的分派順序，每一種主人在別處的欄位各擺一則事件到眼前按下去——靠山、捐糧（四勝利記帳）、伏筆片段、符文殘片、
    一般伏筆、召見往下一段、晉升、部下、結識同伴、伏筆物品與計數、玉璽碎片（舊鏈的世界旗標）、一條線的一步；按之前擺好那一種要的（糧草、召見、線的進度）。
    一則好幾種（combined）：內容裡每一個欄位抄一個值併成一則（next_event、contribution 除外），官軍、黃巾、散人各按一次（同一則效果帶好幾個欄位時，
    回話的先後、世界旗標與存檔寫入的先後都看得出來）。
    叛投（defect_full）：官軍的人手上擺滿會被清的進度（押著的糧車〔護糧軍令〕、階與召見與第 4 階資格與「只缺一個機會」、部下與傳功、貢獻與每週貢獻、
    豪強兩本帳、捐獻、舊陣營引薦人排著的提示〔師父的一條不動〕、機緣與靠山、響應的集體密謀、第四階席次與帳、揭著的舊陣營懸賞、寫了 side 的同伴、
    欠著人物的請託〔NPC 智能〕），在黃巾的投靠點按叛投、確定。
    **前半停在兩件寫到一半的事**：一則好幾種的事件卡擺在眼前還沒按（效果還沒套）、另一個人按了叛投還在確認畫面上（先按、還沒確定）。
    後半：新程式接著按那一張卡、按「確定叛投」；假人（BotRunner 兩個眼前擺著那一則好幾種的卡、整季機器人眼前的選單與挑法：叛投那幾顆照排除）；收季、開下一季。
    沒有陣營、沒有那些內容的（測試內容）同一串 API 照打，寫「沒有」。"""

    G1, H1, G2, H2, LONE, WAIT = "岑望川", "鍾雨樵", "裴映川", "藺秋原", "閔遠帆", "盧聽濤"
    DF1, DF2, LEAD = "殷照野", "談秋聲", "范清和"
    PLAYERS = {G1: "guan", H1: "huang", G2: "guan", H2: "huang", LONE: None, WAIT: "guan", DF1: "guan", DF2: "guan", LEAD: "guan"}
    BOT_SEATS = ["效甲", "效乙"]
    PHASES_FIRST = ["setup", "seat", "single", "combined", "defect_full", "half"]
    PHASES_SECOND = ["resume", "answer", "confirm", "bots", "season"]
    # 一則一種：（格, 抄哪幾個欄位, 誰按）；照 apply_effect 的先後排（計畫第一節 1.2）
    SINGLES = (
        ("patron", ("patron",), "G1"),
        ("grain", ("donate_grain",), "H1"),
        ("fs_fragments", ("fs_fragments",), "H1"),
        ("runic", ("runic",), "H1"),
        ("event_mods", ("event_mods",), "G1"),
        ("summons_next", ("summons_next",), "G1"),
        ("promote", ("promote",), "G1"),
        ("followers", ("followers",), "G1"),
        ("recruit", ("recruit",), "G1"),
        ("foreshadow", ("clue_items", "fs_counters"), "H1"),
        ("shard", ("world_flags_add",), "G1"),
        ("story", ("story",), "G1"),
    )

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.singles = {slot: self.single_effect(slot, fields) for slot, fields, _who in self.SINGLES}
        self.combo = self.combined_effect()
        self.inject()

    # ── 對照用的事件（每個子行程照內容算一次：前半、後半兩個行程算出來的一樣） ──

    def hub(self) -> str:
        return self.c.scenario.start_location

    def sample(self, field: str):
        """內容裡第一則（照事件 id、選項、先成後敗）寫了這個欄位的效果的值；沒有是 None。"""
        import copy

        for eid in sorted(self.c.events):
            if eid.startswith(FX_PREFIX):
                continue
            for ch in self.c.events[eid].choices:
                for eff in (ch.effect, ch.fail_effect):
                    value = getattr(eff, field)
                    if value:
                        return copy.deepcopy(value)
        return None

    def fallback(self, field: str):
        """內容裡沒有人寫的欄位補一個（正式內容沒有結識同伴的事件；測試內容沒有晉升、伏筆那幾種）。補不出來是 None。"""
        c = self.c
        if field == "patron":
            return "cao"
        if field == "promote":
            return 2
        if field == "runic":
            return 2
        if field == "followers":
            return [sorted(c.followers)[0]] if c.followers else None
        if field == "donate_grain":
            return {self.hub(): 3}
        if field == "insights":  # 正式內容沒有事件給意境：第一個地點探索悟得到的基本意境
            got = next((i for loc in sorted(c.locations) for i in c.locations[loc].insights), None)
            return [got] if got else None
        if field == "gear":  # 正式內容沒有事件給寶物：掉落池的第一件，沒有就一匹良駒
            return next((tid for tid, t in sorted(c.gear.treasures.items()) if getattr(t, "pool", True)), "good_horse")
        if field == "fs_counters":  # 伏筆的隱藏計數（官銀）
            return {"guanyin": 1}
        if field == "recruit":
            free = [cid for cid in sorted(c.characters) if c.characters[cid].kind is not None and c.characters[cid].side in (None, "guan")]
            return free[0] if free else None
        return None

    def single_effect(self, slot: str, fields: tuple[str, ...]) -> dict | None:
        if slot == "shard":  # 舊鏈的玉璽碎片：劇本的碎片旗標（沒寫就換一個對照用的旗標，照樣是「這一下新立的世界旗標」）
            return {"world_flags_add": [self.c.scenario.jade_seal_flag or f"{FX_PREFIX}flag"], "chronicle": "{name}在對照的路上拾得一物。"}
        if slot == "story":  # 一條線的一步：挑一步有紀念物的（「收進行囊」那一句才看得出這一格在回話裡的先後）；沒有就照 sample
            import copy

            steps = [eff.story for eid in sorted(self.c.events) if not eid.startswith(FX_PREFIX) for ch in self.c.events[eid].choices
                     for eff in (ch.effect, ch.fail_effect) if eff.story is not None]
            kept = next((s for s in steps if s.keepsake), None)
            if kept is not None:
                return {"story": copy.deepcopy(kept)}
        out = {}
        for f in fields:
            value = self.sample(f)
            value = self.fallback(f) if value is None else value
            if value is not None:
                out[f] = value
        return out or None

    def combined_effect(self) -> dict:
        """每一個欄位抄一個值（next_event、contribution 除外）；七種主人在別處的照一則一種那一份補齊。"""
        from tianxia.models import Effect

        out = {}
        for f in Effect.model_fields:
            if f in FX_SKIP:
                continue
            value = self.sample(f)
            value = self.fallback(f) if value is None else value
            if value is not None:
                out[f] = value
        for kw in self.singles.values():
            for f, value in (kw or {}).items():
                out.setdefault(f, value)
        if (self.singles.get("story") or {}).get("story") is not None:  # 一條線那一步用有紀念物的那一步（回話裡排最後的那一句）
            out["story"] = self.singles["story"]["story"]
        flag = self.c.scenario.jade_seal_flag
        if flag and flag not in out.get("world_flags_add", []):
            out["world_flags_add"] = [*out.get("world_flags_add", []), flag]
        return out

    def inject(self) -> None:
        from tianxia.models import Choice, Effect, Event

        def event(eid: str, kw: dict) -> Event:
            return Event(id=eid, title=f"對照・{eid.removeprefix(FX_PREFIX)}", text="（對照用的事件：只擺到眼前）", actions=[],
                         choices=[Choice(text="照辦", effect=Effect(**kw))])

        for slot, kw in self.singles.items():
            if kw is not None:
                self.c.events[f"{FX_PREFIX}{slot}"] = event(f"{FX_PREFIX}{slot}", kw)
        self.c.events[f"{FX_PREFIX}all"] = event(f"{FX_PREFIX}all", self.combo)

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    def factions_on(self) -> bool:
        return any(f.id == "huang" for f in self.c.scenario.factions) and any(f.id == "guan" for f in self.c.scenario.factions)

    def grain(self, who: str, n: int) -> None:
        """背包裡放 n 份糧草（慢屬性的素材，每一種都放：捐糧照 foreshadow.spend_grain 從哪一種扣都看得出來）。"""
        mats = sorted(m.id for m in self.c.materials.values() if m.attribute == "慢")
        self.edit(who, lambda p: p.materials.update({m: n for m in mats}))

    def prep(self, who: str, kw: dict) -> None:
        """按之前擺好這一則要的：糧草（捐糧）、還沒去的第 3 階召見（召見往下一段；陣營的人）、那一條線還沒收的進度（一條線的一步）。"""
        from tianxia.state import StoryProgress, Summons

        if kw.get("donate_grain"):
            self.grain(who, 40)
        if kw.get("summons_next") and self.PLAYERS.get(who):
            self.edit(who, lambda p: setattr(p, "summons", Summons(rank=3, location=self.hub())))
        step = kw.get("story")
        if step is not None and step.line:
            self.edit(who, lambda p: p.storylines.setdefault(step.line, StoryProgress(line=step.line, stage=f"{FX_PREFIX}stage")))

    @contextlib.contextmanager
    def old_shard(self, on: bool):
        """舊鏈的玉璽碎片那一下：玉璽碎片關著（開著的話舊鏈不寫跨季紀錄，三種設定都看不到這一格）、劇本有碎片旗標（測試內容沒寫就用對照用的那一個）；
        出來還原。"""
        if not on:
            yield
            return
        seal, scen = self.c.config.seal, self.c.scenario
        before = (seal.enabled, scen.jade_seal_flag)
        seal.enabled, scen.jade_seal_flag = False, scen.jade_seal_flag or f"{FX_PREFIX}flag"
        emit("舊鏈的玉璽碎片這一下", {"seal_enabled_before": before[0], "flag": scen.jade_seal_flag})
        try:
            yield
        finally:
            seal.enabled, scen.jade_seal_flag = before

    def card(self, who: str, eid: str) -> bool:
        if eid not in self.c.events:
            emit(f"{who}：這份內容沒有 {eid}", None)
            return False
        self.edit_state(who, lambda s: setattr(s, "pending_event", eid))
        return True

    def press_card(self, who: str, tag: str) -> None:
        opts = self.ids(self.main(who))
        emit(f"{who} {tag} 卡上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith("choice:")])
        self.choose(who, "choice:0")

    def me(self, who: str, tag: str) -> None:
        """存檔裡效果與叛投碰得到的那幾格（主人在別處的都列；其餘看段落的資料庫雜湊）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player

        def dump(x):
            return None if x is None else x.model_dump(mode="json")

        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "ally": p.ally, "sect": p.sect, "defected": p.defected, "pending": [p.pending_defect, p.pending_ally],
            "rank": p.rank, "qualified": p.qualified, "hinted": list(p.rank_hinted), "stall": p.summons_stall, "summons": dump(p.summons),
            "followers": list(p.followers), "drill": [dump(d) for d in p.follower_drill], "patron": p.patron, "contrib": p.contrib,
            "weeks": dict(sorted(p.contrib_weeks.items())), "ledgers": dict(sorted(p.ledgers.items())), "lean": p.lean_changed,
            "donations": dict(sorted(p.donations.items())), "convoy": dump(p.convoy), "runic": p.runic_pieces,
            "fragments": {k: list(v) for k, v in sorted(p.fragments.items())}, "clues": dict(sorted(p.clue_items.items())),
            "counters": dict(sorted(p.fs_counters.items())), "hints": [[n.id, n.by] for n in p.hint_queue],
            "opp": [list(p.opp_done), dict(sorted(p.opp_counts.items())), dict(sorted(p.opp_items.items())), list(p.opp_clues)],
            "stories": {k: [v.stage, dict(sorted(v.marks.items())), v.go, v.ending] for k, v in sorted(p.storylines.items())},
            "keepsakes": list(p.keepsakes), "flags": sorted(p.flags), "stats": dict(sorted(p.stats.items())),
            "affinity": dict(sorted(p.affinities.items())), "materials": dict(sorted(p.materials.items())),
            "debts": sorted(p.parley_debts), "pending_event": state.pending_event,
            "journal": [[e.title, e.tag, list(e.lines)[:6]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "flags": sorted(w.flags), "event_mods": dict(sorted(w.event_mods.items())),
            "plots": [[x.id, x.faction, x.status, list(x.members), dict(sorted(x.parts.items()))] for x in w.plots],
            "bounties": [[b.id, b.faction, list(b.takers)] for b in w.bounties if b.id.startswith(FX_PREFIX)],
            "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "ledger": {k: {n: dict(sorted(x.items())) for n, x in sorted(v.items())} for k, v in sorted(w.seat_ledger.items())},
            "pushers": {k: sorted(v) for k, v in sorted(w.active_pushers.items())},
            "jade": [[f.number, f.finder, f.text] for f in self.world.get_jade_seal_fragments()],
            "rumors": [r.text for r in w.rumors][-8:], "chronicle": [r.text for r in w.chronicle][-4:]})

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        emit("對照用的事件", {eid: self.c.events[eid].choices[0].effect.model_dump(mode="json", exclude_defaults=True)
                              for eid in sorted(self.c.events) if eid.startswith(FX_PREFIX)})

    def seat(self) -> None:
        on = self.factions_on()
        for who, side in self.PLAYERS.items():
            self.place(who, self.hub(), side if on else None)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("坐定")

    def single(self) -> None:
        """一則一種：照 apply_effect 的先後，一種一則按下去（同一個人接連按，前一則留下的會被下一則讀到：召見往下一段之後才晉升）。"""
        for slot, _fields, who_key in self.SINGLES:
            who = getattr(self, who_key)
            kw = self.singles[slot]
            if kw is None:
                emit(f"一則一種 {slot}：這份內容沒有", None)
                continue
            self.prep(who, kw)
            if self.card(who, f"{FX_PREFIX}{slot}"):
                with self.old_shard(slot == "shard"):
                    self.press_card(who, f"一則一種 {slot}")
                self.me(who, f"一則一種 {slot} 之後")
        self.world_view("一則一種之後")

    def combined(self) -> None:
        """一則好幾種：官軍、黃巾、散人各按一次。"""
        for who in (self.G2, self.H2, self.LONE):
            self.prep(who, self.combo)
            if self.card(who, f"{FX_PREFIX}all"):
                self.press_card(who, "一則好幾種")
                self.me(who, "一則好幾種之後")
        self.world_view("一則好幾種之後")

    def stage_defector(self, who: str, n: int) -> None:
        """叛投之前手上擺滿會被清的進度（n 讓兩個人擺的數不一樣）；全服那一側：響應的密謀、席次與帳、揭著的懸賞、寫了 side 的同伴。"""
        from tianxia import roster
        from tianxia.state import Bounty, Convoy, FollowerDrill, HintNote, ParleyDebt, Plot, Summons

        c, side = self.c, "guan"
        now = self.world.get_season().time
        far = now + 30 * 86400.0
        follower = sorted(c.followers)[0] if c.followers else None
        opp = c.opportunities[0].id if c.opportunities else f"{FX_PREFIX}opp"
        debtor = sorted(c.characters)[0] if c.characters else None
        trek = sorted(i for i in c.locations if i != self.hub())

        def fn(p) -> None:
            p.rank, p.qualified, p.rank_hinted, p.summons_stall = 3, True, [3], "（對照）沒有人能引見"
            p.summons = Summons(rank=4, location=self.hub())
            p.followers = [follower] * n if follower else []
            p.follower_drill = [FollowerDrill(cheng=n, arm=1)] if follower else []
            p.contrib, p.contrib_weeks = 5 + n, {1: 2, 2: 3 + n}
            p.ledgers, p.lean_changed = {"guan": 4, "huang": n}, 1
            p.donations = {f"{self.hub()}:糧草": 6 + n}
            p.convoy = Convoy(order=f"{FX_PREFIX}escort", grain=4 + n, from_loc=self.hub(), to_loc=trek[0] if trek else self.hub())
            p.hint_queue = [HintNote(id=f"{FX_PREFIX}old", speaker="（對照）引薦人", text="（對照）舊陣營排著的話。", by=side),
                            HintNote(id=f"{FX_PREFIX}mentor", speaker="（對照）師父", text="（對照）師父排著的話。")]
            p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts = [opp], {opp: n}, {opp: "（對照）信物"}, {opp: "front"}
            p.opp_tried, p.opp_pieces, p.opp_clues, p.patron = {opp: 1}, {opp: ["a"]}, [opp], "cao"
            p.runic_pieces, p.fragments = 2, {f"{FX_PREFIX}chain": [0]}
            if debtor is not None:
                p.parley_debts = {debtor: ParleyDebt(kind="plea", condition="silver", due=far)}

        self.edit(who, fn)

        def world_fn(s) -> None:
            s.plots.append(Plot(id=9900 + n, opp=opp, faction=side, leader=self.LEAD, shown=self.LEAD, members=[self.LEAD, who],
                                parts={"a": who, "b": self.LEAD}, deadline=far))
            s.seats.setdefault(side, []).append(who)
            s.seat_ledger.setdefault(side, {})[who] = {1: 3 + n}
            s.bounties.append(Bounty(id=f"{FX_PREFIX}{n}", kind="scout", faction=side, week=1, expires=far, silver=10, deeds=1, quota=2,
                                     location=self.hub(), takers=[who]))

        self.world.mutate_season(world_fn)
        mate = next((cid for cid in sorted(c.characters) if c.characters[cid].side == side and roster.owned_by(self.world, cid) is None), None)
        emit(f"{who} 名下寫了 side 的同伴", [mate, mate is not None and self.world.try_recruit(mate, who, cap=3)])

    def to_target(self, who: str) -> str | None:
        target = next((f for f in self.c.scenario.factions if f.id == "huang" and f.join_at), None)
        if target is None:
            return None
        self.place(who, target.join_at[0])
        ids = [i for i in self.ids(self.main(who)) if i.startswith("defect:")]
        emit(f"{who} 叛投那幾顆", ids)
        return "defect:huang" if "defect:huang" in ids else (ids[0] if ids else None)

    def defect_full(self) -> None:
        """官軍的人手上擺滿會被清的進度，在黃巾的投靠點按叛投、確定。"""
        if not self.factions_on():
            emit("叛投：這份內容沒有兩軍", None)
            return
        self.stage_defector(self.DF1, 1)
        self.me(self.DF1, "叛投之前")
        self.world_view("叛投之前")
        oid = self.to_target(self.DF1)
        if oid is not None:
            self.choose(self.DF1, oid)
            self.choose(self.DF1, "defect:confirm")
        self.me(self.DF1, "叛投之後")
        self.world_view("叛投之後")

    def half(self) -> None:
        """前半停在兩件寫到一半的事：一則好幾種的事件卡擺在盧聽濤眼前還沒按；談秋聲按了叛投、停在確認畫面上。"""
        self.prep(self.WAIT, self.combo)
        self.card(self.WAIT, f"{FX_PREFIX}all")
        self.me(self.WAIT, "前半停在這裡")
        if self.factions_on():
            self.stage_defector(self.DF2, 2)
            oid = self.to_target(self.DF2)
            if oid is not None:
                self.choose(self.DF2, oid)
            self.me(self.DF2, "前半停在這裡")
        self.world_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.WAIT, self.DF2, self.G1):
            self.main(who)

    def answer(self) -> None:
        """新程式接著按前半擺在眼前的那一張卡（效果在新程式這一下才套）。"""
        self.press_card(self.WAIT, "接手")
        self.me(self.WAIT, "接手之後")
        self.world_view("接手之後")

    def confirm(self) -> None:
        """新程式接著按「確定叛投」（前半按了叛投、確認畫面還開著）。"""
        if not self.factions_on():
            return
        emit(f"{self.DF2} 確認畫面上", sorted(self.ids(self.main(self.DF2))))
        self.choose(self.DF2, "defect:confirm")
        self.me(self.DF2, "確定之後")
        self.world_view("確定之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在開局的地方，眼前擺著那一則好幾種的卡）若干輪；整季機器人站在黃巾的投靠點、眼前擺著那一張卡的選單與挑法
        （叛投那幾顆照排除；卡上有結識同伴的那一顆照 bot.pick 先挑）。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            g.state.pending_event = f"{FX_PREFIX}all"
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(31), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_EFFECTS_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "pending_event": s.pending_event,
                                  "card": [[e.title, list(e.lines)] for e in s.journal if e.title.startswith("對照")][:1],
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "效丙", rng=random.Random(7), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        target = next((f for f in self.c.scenario.factions if f.id == "huang" and f.join_at), None)
        p.faction, p.location, p.journey = ("guan" if on else None), (target.join_at[0] if target is not None else self.hub()), None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（投靠點）", [o.id for o in opts])
        emit("整季機器人挑的（投靠點）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        solo.state.pending_event = f"{FX_PREFIX}all"
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（卡上）", [o.id for o in opts])
        emit("整季機器人挑的（卡上）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(20)}))

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.world_view("收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.G1)
        self.me(self.G1, "換季之後")
        self.world_view("換季之後")


def _effects_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _world_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：叛投之後新陣營那一則陣營軍情（defection.defect；第 35 批陣營成包時那一行搬進包，這裡要多寫包裡的檔）
_effects_register_track("effects", EffectsScenario, (("tianxia/defection.py",), ("投奔過來了。", "投奔過來了！")), "week7")


class StaminaScenario(WorldScenario):
    """體力玩法與閉關一軌（全部拆包第 39 批：設伏、屯糧進 stamina_plays，閉關進 seclusion；--track stamina，自己一個資料庫）。
    設伏（ambush:set／lift）：埋（扣體力、季上與角色身上各一筆、守著不能移動）、中伏（敵對陣營的人走過那一段：自然、伏兵必勝、伏兵必敗各一場；
    自己人、散人走過不打）、撤（自己收伏）、守滿到時刻自己收；不能設的幾種（散人沒揭通緝、守著還要再設、城鎮旁、設伏關著的季）灰著或寫原因。
    屯糧（works:stockpile）：設定關著（三種設定的預設）沒有鈕、硬按寫「此刻無法這麼做」；打開之後官軍、黃巾各在自己的大本營屯幾下，
    **開集結那一刻結算**（管理者開時刻表上第一件決戰：起點照戰線、屯糧、玉璽、龍頭上陣四格，屯糧換成起點的偏移、天下大事一句、屯的量清空）。
    閉關（/api/do/seclude 1～12 小時、act:break 提早出關）：越界的小時夾住、閉關中再閉寫「現在無法閉關」、閉關中只剩提前出關與擂台、
    自己滿時自然出關（sync 結算）、提前出關。
    **審查查出沒走到的**（說明不寫成涵蓋了）：新人的序章拒絕（新人按閉關回的是「你現在無法閉關。」，走 _idle 那一支，三種設定都沒有序章）、
    修練頁 /api/menxia 的 seclude_blocked（這一軌沒請求修練頁）、假人守著走不開先收伏（bot_policy 那一支要有決戰集結才走到）、
    硬按的拒絕（都被 Game.choose 的「此刻無法這麼做」擋在核心，到不了包裡的 set_problem）、平手、偏移不是 0 的開集結；這幾支靠 ast 逐條比對舊新相同。
    **前半停在三件寫到一半的事**：設伏埋了還沒人走過、閉關閉到一半（十二小時才過一小時不到）、兩軍屯了糧還沒開集結。
    後半：新程式接著讓人走過那一段、提前出關、開集結結算；假人（BotRunner 四個：路上兩個、大本營兩個，其中一個先埋好伏〔守著走不開，先收伏〕；
    整季機器人眼前的選單與挑法、bot_policy.score 對 ambush:／works: 的分數）；收季、開下一季。
    沒有陣營的內容（測試內容）同一串 API 照打：設伏、屯糧寫「沒有」，閉關照走。"""

    A, B1, B2, B3, C, D, E, F, G = "曲臨淵", "項疏影", "宗無咎", "霍青鸞", "尹遙岑", "屈寒松", "鄂南風", "樊聽雪", "裘半夏"
    NEWBIE = "初出茅廬"
    PLAYERS = {A: "guan", B1: "huang", B2: "huang", B3: "huang", C: "guan", D: "huang", E: "guan", F: "huang", G: None}
    BOT_SEATS = ["伏甲", "伏乙", "糧甲", "糧乙"]
    PHASES_FIRST = ["setup", "seat", "refuse", "stock_off", "stock_on", "ambush_set", "seclude_start", "half"]
    PHASES_SECOND = ["resume", "hits", "lift_expire", "seclude_end", "muster", "bots", "season"]

    # ── 小工具 ──

    def pair(self) -> tuple[str, str]:
        """（埋伏的人站的地方, 路的另一頭）：第一對兩頭都不是城鎮的路（照地點 id 排序，connections 的順序）。"""
        from tianxia import ambush

        for a in sorted(self.c.locations):
            for to in self.c.locations[a].connections:
                if ambush.road_ok(self.c, a, str(to)):
                    return a, str(to)
        return self.hub(), self.hub()

    def base_of(self, side: str) -> str:
        from tianxia import territory

        try:
            bases = territory.bases(self.c)
        except Exception:  # noqa: BLE001
            bases = {}
        return next((loc for loc, owner in sorted(bases.items()) if owner == side), self.hub())

    def set_stock(self, on: bool) -> None:
        """屯糧的開關（三種設定的預設都關著）：同一個行程裡共用 CONTENT，每個行程各自設。"""
        self.c.config.stockpile.enabled = on

    def kinds(self, who: str, tag: str) -> dict:
        """此刻選單上跟這一軌有關的那幾顆（設伏、屯糧、提前出關、移動），連同開著與否與標籤。"""
        view = self.main(who)
        mine = {i: [o.get("enabled"), o.get("label")] for i, o in self.ids(view).items()
                if i.startswith(("ambush:", "works:", "act:break")) or i.startswith("move:")}
        emit(f"{who} 選單 {tag}", mine)
        return mine

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        post = None if p.ambush is None else p.ambush.model_dump(mode="json")
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"),
            "materials": dict(sorted(p.materials.items())), "ambush": post, "busy_until": p.busy_until,
            "seclusion": [p.seclusion_start, p.seclusion_done], "contrib": p.contrib,
            "journal": [[e.title, e.tag, list(e.lines)[:4], list(e.changes)[:3]] for e in state.journal[:4]]})

    def stock_view(self, tag: str) -> None:
        """季上跟體力玩法有關的帳：各軍屯了幾下、各段路上的埋伏、決戰（含起點偏移與快照的屯量）、天下大事的尾巴。"""
        w = self.world.get_season()
        b = self.world.get_battle()
        emit(f"世界 {tag}", {
            "supply": dict(sorted(w.supply.items())),
            "ambushes": {k: [[a.owner, a.at, a.to, a.set_at, a.until, a.lifted_at, a.caught, a.side] for a in v] for k, v in sorted(w.ambushes.items())},
            "raids": dict(sorted(w.raids.items())), "raided": dict(sorted(w.raided.items())),
            "battle": None if b is None else [b.battle_id, b.phase, b.trend, b.trend_start, dict(sorted(b.supply_lean.items()))],
            "opened": dict(w.showdowns_opened), "rumors": [r.text for r in w.rumors][-4:], "chronicle": [r.text for r in w.chronicle][-3:]})

    @contextlib.contextmanager
    def tilt(self, shift: float):
        """設伏打這一場的判定平移（encounter.resolve_encounter 的 shift：正的偏伏兵，負的偏路過的人；威力、亂數照算，只多一個平移）。"""
        from tianxia import encounter

        real = encounter.resolve_encounter

        def resolve(our_power, difficulty, rng, positional_shift=0.0, mods=None, **kw):
            own = kw.pop("shift", positional_shift)
            return real(our_power, difficulty, rng, shift=own + shift, mods=mods, **kw)

        encounter.resolve_encounter = resolve
        emit("這一下的判定平移", shift)
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    def refill(self, who: str) -> None:
        self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))

    # ── 前半 ──

    def seat(self) -> None:
        at, to = self.pair()
        emit("設伏的那一段路", [at, to])
        mats = sorted(self.c.materials)[:2]

        def purse(p) -> None:
            p.stats["silver"] = 400
            for mid in mats:
                p.materials[mid] = p.materials.get(mid, 0) + 6

        spots = {self.A: at, self.G: at, self.B1: to, self.B2: to, self.B3: to, self.C: self.base_of("guan"), self.D: self.base_of("huang"),
                 self.E: self.hub(), self.F: self.hub()}
        for who, side in self.PLAYERS.items():
            self.place(who, spots[who], side)
            self.edit(who, purse)
        for who in self.PLAYERS:
            self.main(who)
        self.stock_view("坐定")

    def refuse(self) -> None:
        """設不了伏的幾種：散人沒揭通緝（灰著或沒有鈕、硬按寫原因）、城鎮旁邊（硬按）、序章裡不閉關（新人）。"""
        at, to = self.pair()
        self.kinds(self.G, "散人")
        self.choose(self.G, f"ambush:set:{to}")
        town = next((i for i, loc in sorted(self.c.locations.items()) if i not in (at, to) and not loc.prologue_only), self.hub())
        self.place(self.C, town)
        self.kinds(self.C, "城裡")
        self.choose(self.C, f"ambush:set:{to}")
        self.place(self.C, self.base_of("guan"))
        self.kinds(self.NEWBIE, "新人")
        self.do(self.NEWBIE, "seclude", {"hours": 3})
        self.main(self.NEWBIE)

    def stock_off(self) -> None:
        """設定關著（預設）：C 站在自家大本營，沒有屯糧鈕、硬按寫「此刻無法這麼做」。"""
        self.set_stock(False)
        self.kinds(self.C, "屯糧關著")
        self.choose(self.C, "works:stockpile")
        self.stock_view("屯糧關著硬按之後")

    def stock_on(self) -> None:
        """打開之後：官軍 C、黃巾 D 各在自己的大本營屯幾下（官軍多一下）；散人 G 屯不了；在別人的地方屯不了（C 站到黃巾大本營）。"""
        self.set_stock(True)
        for who, n in ((self.C, 3), (self.D, 2)):
            for _ in range(n):
                self.refill(who)
                self.kinds(who, "屯糧開著")
                self.choose(who, "works:stockpile")
            self.me(who, "屯糧之後")
        self.refill(self.G)
        self.choose(self.G, "works:stockpile")
        away = self.base_of("huang")
        if away != self.base_of("guan"):
            self.place(self.C, away)
            self.kinds(self.C, "別人的地方")
            self.choose(self.C, "works:stockpile")
            self.place(self.C, self.base_of("guan"))
        self.stock_view("屯糧之後")

    def ambush_set(self) -> None:
        """A 在路上埋伏（官軍）：選單上的鈕、埋下去（體力、季上與身上各一筆）、再按一次設別段、守著想移動（灰掉、硬按）。**後半才有人走過**。"""
        at, to = self.pair()
        self.refill(self.A)
        self.kinds(self.A, "埋之前")
        self.choose(self.A, f"ambush:set:{to}")
        self.kinds(self.A, "埋了")
        self.choose(self.A, f"ambush:set:{to}")
        self.choose(self.A, f"move:{to}")
        self.me(self.A, "埋了之後")
        self.stock_view("埋了之後")

    def seclude_start(self) -> None:
        """E 閉關十二小時（99 夾成 12；**前半只過去一小時不到**）、閉關中再閉、閉關中想做別的；F 閉關一小時（0 夾成 1）。"""
        self.refill(self.E)
        self.do(self.E, "seclude", {"hours": 99})
        self.me(self.E, "閉關開始")
        self.kinds(self.E, "閉關中")
        self.do(self.E, "seclude", {"hours": 3})
        self.choose(self.E, "act:explore")
        self.do(self.F, "seclude", {"hours": 0})
        self.me(self.F, "閉關開始")

    def half(self) -> None:
        self.me(self.A, "前半最後")
        self.me(self.E, "前半最後")
        self.stock_view("前半最後（埋著、閉關著、兩軍屯著）")

    # ── 後半 ──

    def resume(self) -> None:
        self.set_stock(True)  # 設定是各行程自己的：先開，再登入（登入回的選單就有屯糧鈕）
        self.login_all()
        self.stock_view("後半開頭")

    def ensure_ambush(self) -> None:
        """A 沒有埋伏（被打退、守滿了）就補一個。"""
        at, to = self.pair()
        self.main(self.A)
        state = self.chars.load(self.A)
        if state is not None and state.player.ambush is None:
            self.refill(self.A)
            self.choose(self.A, f"ambush:set:{to}")

    def pass_by(self, who: str, tag: str) -> None:
        """who 從路的另一頭走過 A 站的那一頭（步行），快轉一小時走完，各看一眼。"""
        at, to = self.pair()
        self.place(who, to)
        self.choose(who, f"move:{at}")
        self.do(ADMIN, "fast_forward", {"hours": 1})
        self.main(who)
        self.main(self.A)
        self.me(who, f"走過 {tag}")
        self.me(self.A, f"被走過 {tag}")
        self.stock_view(f"走過 {tag}")

    def hits(self) -> None:
        """自己人（同軍的 C）、散人 G 走過不打；敵對的 B1 自然打、B2 伏兵必勝、B3 伏兵必敗（被打退，埋伏散了）。每一次先補好埋伏。"""
        for who, tag in ((self.C, "自己人"), (self.G, "散人")):
            self.ensure_ambush()
            self.pass_by(who, tag)
        self.ensure_ambush()
        self.pass_by(self.B1, "自然")
        self.ensure_ambush()
        with self.tilt(800.0):
            self.pass_by(self.B2, "伏兵勝")
        self.ensure_ambush()
        with self.tilt(-800.0):
            self.pass_by(self.B3, "伏兵敗")

    def lift_expire(self) -> None:
        """A 埋好之後自己收伏；再埋、守滿三小時沒人來（快轉四小時，自己同步時收起來）。"""
        self.ensure_ambush()
        self.kinds(self.A, "收伏之前")
        self.choose(self.A, "ambush:lift")
        self.kinds(self.A, "收伏之後")
        self.refill(self.A)
        self.ensure_ambush()
        self.do(ADMIN, "fast_forward", {"hours": 4})
        self.main(self.A)
        self.me(self.A, "守滿之後")
        self.stock_view("守滿之後")

    def seclude_end(self) -> None:
        """F 的一小時早滿了（同步時自然出關）；E 還在閉關：提前出關（心得照小時算）；出關之後再閉一次、十二小時快轉走完自然出關。"""
        self.me(self.F, "自然出關之前")
        self.main(self.F)
        self.me(self.F, "自然出關之後")
        self.kinds(self.E, "提前出關之前")
        self.choose(self.E, "act:break")
        self.me(self.E, "提前出關之後")
        self.refill(self.E)
        self.do(self.E, "seclude", {"hours": 2})
        self.do(ADMIN, "fast_forward", {"hours": 3})
        self.main(self.E)
        self.me(self.E, "第二次自然出關之後")

    def muster(self) -> None:
        """照時刻表開集結：兩軍屯的量換成起點的偏移（屯糧那一格；排在起點之後、玉璽之前）、天下大事一句、屯的量清空。
        開季自然開的集結先取消；屯糧關著的對照也看一次（設定關掉、屯的量留著，開集結什麼都不寫）。"""
        ids = self.showdowns()
        emit("時刻表的決戰", ids)
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.cancel("自然開的")
        w = self.world.get_season()
        left = [i for i in ids if i not in w.showdowns_opened and i not in w.timeline]
        emit("開集結之前的屯量", dict(sorted(w.supply.items())))
        if not left:
            return
        self.do(ADMIN, "start_showdown", {"id": left[0]})
        self.stock_view("開集結")
        self.cancel("時刻表")
        self.stock_view("開集結取消之後")

    def bots(self) -> None:
        """假人：BotRunner 四個（路上官軍〔先埋好伏：守著走不開，先收伏〕、路上黃巾、自家大本營的官軍、黃巾；體力滿）若干輪；整季機器人站在大本營眼前的選單與挑法；
        bot_policy.score 對設伏、屯糧、收伏的分數。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        at, to = self.pair()
        spots = [("guan", at), ("huang", to), ("guan", self.base_of("guan")), ("huang", self.base_of("huang"))]
        on = bool(self.c.scenario.factions)
        for i, name in enumerate(self.BOT_SEATS):
            side, loc = spots[i]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=side if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            if i == 0:
                opt = next((o for o in g.options(odds=False) if o.id.startswith("ambush:set:") and o.enabled), None)
                emit("伏甲先埋好", None if opt is None else opt.id)
                if opt is not None:
                    g.choose(opt.id)
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        chance = bot_policy.PLAY_CHANCE
        try:
            # 前一段照原樣（體力花不完時才 5% 的機會玩一下）；後一段把機會拉到 1，設伏、屯糧的挑選與守著走不開先收伏才一定走到
            for stage, rounds in (("照原樣", int(os.environ.get("SB_STAMINA_TICKS", "6"))), ("必玩", 8)):
                bot_policy.PLAY_CHANCE = chance if stage == "照原樣" else 1.0
                for _ in range(rounds):
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.PLAY_CHANCE = chance
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "stamina": s.player.stamina, "silver": s.player.stats.get("silver"),
                                  "ambush": None if s.player.ambush is None else s.player.ambush.model_dump(mode="json"),
                                  "journal": [[e.title, e.tag, list(e.lines)[:3]] for e in s.journal[:5]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.stock_view("假人之後")
        for name, (side, loc) in (("效丙", ("guan", at)), ("效丁", ("guan", self.base_of("guan")))):
            self.begin()
            solo = Game.new(self.c, name, rng=random.Random(7), world=self.world, graduated=True)
            solo.client = None
            solo.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                solo.choose(first)
            p = solo.state.player
            p.bot = BotProfile(personality="普通", seed=99, faction=side if on else None, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = p.bot.faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            opts = solo.options(odds=False)
            mine = [o for o in opts if o.id.startswith(("ambush:", "works:"))]
            emit(f"{name} 眼前的選單", [o.id for o in opts])
            emit(f"{name} 的分數", {o.id: bot_policy.score(solo, o, p.bot) for o in mine})
            emit(f"{name} 整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
            emit(f"{name} 體力花不完時", [bot_policy._stamina_play(solo, random.Random(k)) for k in range(6)])
            class Prefer(random.Random):  # 擲骰一定過、挑清單時先挑屯糧（有就挑，沒有照第一顆）
                def random(self) -> float:
                    return 0.0

                def choice(self, seq):
                    return next((x for x in seq if x.startswith("works:")), seq[0])

            bot_policy.PLAY_CHANCE = 1.0  # 機會拉到 1：選單上按得下去的設伏、屯糧一顆顆挑（體力用完就不玩了）
            try:
                emit(f"{name} 先挑屯糧", [bot_policy._stamina_play(solo, Prefer(3)) for _ in range(2)])
                played = [bot_policy._stamina_play(solo, random.Random(k)) for k in range(6)]
            finally:
                bot_policy.PLAY_CHANCE = chance
            emit(f"{name} 必玩", played)

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.stock_view("收季之後")
        self.me(self.A, "收季之後")
        self.me(self.E, "收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.A)
        self.me(self.A, "換季之後")
        self.me(self.E, "換季之後")
        self.stock_view("換季之後")


def _stamina_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _effects_register_track，名字分開免得幾塊都在時互相蓋掉）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：收伏那一句（ambush.LIFTED；第 39 批設伏搬進包時規則檔換位置，這裡要多寫包裡的檔）
_stamina_register_track("stamina", StaminaScenario, (("tianxia/features/stamina_plays/ambush_rules.py", "tianxia/ambush.py"),
                                                      ("你收起埋伏，從路邊撤了回來。", "你收起埋伏，從路邊撤了回來！")), "week7")


# ═══════════════════════════ landturn：地盤一軌（全部拆包第 46 批，dev/territory-acts-1） ═══════════════════════════
# 地盤（Game 上的戰書與攻城時段、22:00 換天、〈天下形勢〉三段式、地盤畫面的資料、分紅與守城功補送、管理者五個救場工具；tianxia/conquest_day.py、
# xingshi.py；/api/xingshi）搬進新包 tianxia/features/territory_acts/（計畫 docs/superpowers/plans/2026-11-06-地盤包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、`if __name__` 之前，最後一行登記（_landturn_register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。

_LANDTURN_CLIENTS: dict[type, type] = {}
LANDTURN_ESSAY = "天下形勢一日三變，官軍黃巾各據一方，鄉野之間人心浮動，商旅避路而行，驛馬晝夜不息，城中百姓閉戶觀望。" * 3


def _landturn_client(base: type) -> type:
    """〈天下形勢〉的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["xingshi"] 給了（"good"＝回一篇夠長的、"short"＝回太短的）時回文章；
    其餘照 base（丟連線錯誤，照固定段）。"""
    if base not in _LANDTURN_CLIENTS:
        class LandTurnClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "XingshiReply" and MODEL.get("xingshi"):
                    return schema.model_validate({"essay": LANDTURN_ESSAY if MODEL["xingshi"] == "good" else "太短"})
                return super().chat_structured(messages, schema, *a, **k)

        _LANDTURN_CLIENTS[base] = LandTurnClient
    return _LANDTURN_CLIENTS[base]


class LandTurnScenario(Scenario):
    """地盤一軌（--track landturn，自己一個資料庫）。
    戰書：散人、不在任的第 4 階、進度不到門檻、不存在的地點各按一次被擋；在任的第 4 階（官軍）下戰書排一場攻城（時段、天下大事、江湖紀錄、那一塊凍結），
    同一天第二張被擋（一邊一天一張），黃巾的在任第 4 階併進同一場；江湖畫面的 conquest（時程表、每一塊、能不能下戰書）、管理者頁的下拉選單。
    分紅：一塊推滿易手（兩個人分紅、其中一個當場同步補、另一個留到後半）、守城功（一筆擺進帳裡）。**前半停在戰書下了、還沒到攻城時段**（那一場排著、
    分紅有人還沒領、一張戰書的時段被擺成「伺服器停過」的樣子、一張〈天下形勢〉的單 A 段拿走了而 C 段還沒收；land 撥過一次 22:00，那張前半就收掉了，所以另開一張）。
    後半：登入就補（分紅）；沒跨過 22:00 什麼都不變；同步跨過 22:00（第一個看到新的一天的人觸發：前一天沒開成的作罷、新的一天可以再下戰書、開一張〈天下形勢〉的單）；
    〈天下形勢〉三段式（A 拿單、B 鎖外請模型〔叫不動／回了／回太短〕、C 收；進度條 xingshi_mark、/api/xingshi）；沒人在線的排程（server.world_step）跨過 22:00；管理者快轉
    跨過 22:00（日子只准往前走）；單開了超過寬限照固定段收；佇列沒讓這一趟跑把單放回去。管理者五個救場工具（定一塊歸誰、定進度、立刻下戰書、取消一場攻城、
    現在就開一篇天下形勢）各幾種擋與成。假人：BotRunner 兩個、整季機器人眼前的選單。換季。
    地盤要劇本有陣營、寫了 territory：測試內容走不到（同一串 API 照打，寫「沒有」）。"""

    G_SEAT, G_LAY, G_PAY = "段臨川", "蘇折柳", "魏啟明"
    H_SEAT, H_PAY = "梁破軍", "傅雁來"
    LONE = "尹無涯"
    NEWBIE = "初來客"
    PLAYERS = {G_SEAT: "guan", G_LAY: "guan", G_PAY: "guan", H_SEAT: "huang", H_PAY: "huang", LONE: None}
    BOT_SEATS = ["營丁", "營戊"]
    PHASES_FIRST = ["setup", "land", "refuse", "letter", "pay", "half"]
    PHASES_SECOND = ["resume", "quiet", "turn1", "essay1", "turn2", "essay2", "turn3", "essay3", "tickets", "admin", "bots", "season"]

    PICKS = ("blocks",)
    blocks: dict = {}

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _landturn_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def clock_to(self, day: int, hour: int, minute: int = 0) -> None:
        """時鐘撥到第 day 天（CLOCK0 那天是第 0 天，台灣 12:00）當地的 hour:minute（只准往前；下一個請求再 +1 步）。"""
        target = CLOCK0 - 12 * 3600 + day * 86400 + hour * 3600 + minute * 60
        STEP[0] = max(STEP[0], int((target - CLOCK0) // STEP_SECONDS))
        from tianxia import conquest_day

        emit(f"時鐘撥到 第 {day} 天 {hour:02d}:{minute:02d}",
             {"offset": self.c.config.pill_day_utc_offset_hours, "key": conquest_day.day_key(CLOCK0 + (STEP[0] + 1) * STEP_SECONDS, self.c.config)})

    def on(self) -> bool:
        from tianxia import conquest, territory

        w = self.world.get_season()
        return bool(territory.on(self.c) and conquest.on(self.c, w))

    def essay_on(self) -> bool:
        from tianxia import xingshi

        return xingshi.on(self.c, self.world.get_season())

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "silver": p.stats.get("silver"), "level": p.member.level, "points": p.stat_points,
            "journal": [[e.title, e.tag, list(e.lines)[:5]] for e in state.journal[:3]],
            "state": hashlib.sha256(state.model_dump_json().encode("utf-8")).hexdigest()})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：領地爭奪的整份帳（時程表、每塊的條、分紅、日誌、settled_key、一邊一天一張）與〈天下形勢〉（收下的、等著的單、讀到哪裡）、傳聞與天下大事的尾巴。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "time": w.time, "ended": w.ended,
            "conquest": None if w.conquest is None else w.conquest.model_dump(mode="json"),
            "xingshi": [e.model_dump(mode="json") for e in w.xingshi],
            "ticket": None if w.xingshi_ticket is None else w.xingshi_ticket.model_dump(mode="json"),
            "mark": None if w.xingshi_mark is None else w.xingshi_mark.model_dump(mode="json"),
            "rumors": [r.text for r in w.rumors][-6:], "chronicle": [r.text for r in w.chronicle][-4:]})

    def seat(self, who: str, side: str) -> None:
        """這一週在任的第 4 階（有資格、席次上有名）。"""
        self.edit(who, lambda p: setattr(p, "qualified", True))
        self.world.mutate_season(lambda s: s.seats.__setitem__(side, [who]))

    def file_letter(self, who: str, loc: str, tag: str) -> None:
        emit(f"{who} {tag} 下戰書 {loc}", None)
        self.do(who, "conquest_letter", {"loc": loc})
        self.me(who, tag)

    def view(self, who: str, tag: str) -> None:
        """江湖畫面上這一包的鍵（conquest、xingshi、xingshi_mark）與 /api/xingshi（形勢頁）。"""
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        emit(f"{who} {tag} 畫面上", {k: main.get(k) for k in ("conquest", "xingshi", "xingshi_mark")})
        self.call(who, "GET", "/api/xingshi")

    # ── 前半 ──

    def land(self) -> None:
        """挑地點：A（開季沒人佔的塊，雙方都推得）、B（推滿易手的）、C（守城功）、D（換天之後再下一張戰書的）；在任的第 4 階；人站到 A 去。"""
        from tianxia import conquest, xingshi

        self.clock_to(1, 9, 0)
        c = self.c
        w = self.world.get_season()
        emit("設定開關", {"territory_on": self.on(), "xingshi_on": self.essay_on(), "xingshi_lines": bool(c.xingshi_lines),
                       "xingshi_enabled": c.config.xingshi.enabled, "letter_at": c.config.conquest.letter_at, "settle_hour": c.config.conquest.settle_hour})
        if not self.on():
            emit("這一季沒有地盤：戰書、換天、形勢、分紅、救場都走不到（同一串 API 照打，看擋的那一句）", None)
            self.blocks = {}
        else:
            capturable = [loc for loc in sorted(conquest.blocks(c)) if conquest.capturable(c, loc)]
            neutral = [loc for loc in capturable if conquest.holder(w, c, loc) is None]
            pool = neutral + [loc for loc in capturable if loc not in neutral]
            pick = lambda i: pool[i % len(pool)] if pool else "nowhere"  # noqa: E731
            self.blocks = {"A": pick(0), "B": pick(1), "C": pick(2), "D": pick(3)}
        emit("挑的地點", {"blocks": self.blocks, "holders": {k: conquest.holder(w, c, v) for k, v in self.blocks.items() if v in c.locations}})
        home = self.blocks.get("A", "nowhere")
        for who, side in self.PLAYERS.items():
            self.place(who, home if home in c.locations else None, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        self.seat(self.G_SEAT, "guan")
        self.seat(self.H_SEAT, "huang")
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("開場")

    def refuse(self) -> None:
        """下不了戰書的幾種：散人、不在任、進度不到門檻、不存在的地點。"""
        a = self.blocks.get("A", "nowhere")
        self.file_letter(self.LONE, a, "散人")
        self.file_letter(self.G_LAY, a, "不在任")
        self.file_letter(self.G_SEAT, a, "進度不到")
        self.file_letter(self.G_SEAT, "nowhere", "沒有這個地點")
        self.view(self.G_SEAT, "下戰書之前")

    def letter(self) -> None:
        """在任的第 4 階下戰書：官軍下 A（排一場、凍結）、同一天第二張被擋、黃巾併進同一場；各看一遍江湖畫面與管理者頁的下拉選單。"""
        a, b = self.blocks.get("A", "nowhere"), self.blocks.get("B", "nowhere")
        if self.on():
            self.preset_bar(a, "guan", 85.0, self.G_PAY)
            self.preset_bar(a, "huang", 70.0, self.H_PAY)
            self.preset_bar(b, "guan", 80.0, self.G_PAY)
        self.view(self.G_SEAT, "進度到了")
        self.view(self.LONE, "散人看")
        self.file_letter(self.G_SEAT, a, "官軍下")
        self.file_letter(self.G_SEAT, b, "同一天第二張")
        self.file_letter(self.H_SEAT, a, "黃巾併進去")
        self.view(self.G_SEAT, "下了之後")
        self.view(self.H_SEAT, "黃巾看")
        self.call(ADMIN, "GET", "/api/admin")
        self.world_view("下了戰書")

    def pay(self) -> None:
        """分紅與守城功：B 推滿易手（G_PAY、G_LAY 分紅），只有 G_PAY 同步補；守城功擺一筆給 H_PAY（C，沒人去同步）。"""
        from tianxia.state import ConquestPayout

        b, cc = self.blocks.get("B", "nowhere"), self.blocks.get("C", "nowhere")
        if self.on():
            self.preset_bar(b, "guan", 90.0, self.G_PAY)

            def two(s) -> None:
                s.conquest.fights[b].bars["guan"].pushers = {self.G_PAY: 60.0, self.G_LAY: 30.0}

            self.world.mutate_season(two)

            def guard(s) -> None:
                s.conquest.payouts.append(ConquestPayout(name=self.H_PAY, kind="guard", loc=cc, side="huang", share=1.0, top=True,
                                                         time=s.time, silver=40, exp=30, fame=5))

            self.world.mutate_season(guard)
        self.do(ADMIN, "conquest_progress", {"id": b, "side": "guan", "value": 100})
        self.world_view("推滿之後（分紅還沒領）")
        self.main(self.G_PAY)
        self.me(self.G_PAY, "同步補了分紅")
        self.world_view("一個人領了")

    def half(self) -> None:
        """前半停在戰書下了、還沒到攻城時段：那一場排著；黃巾併進去的那一場，時段擺成「伺服器停過、時辰沒到」（換天時照作罷收）。"""
        def stale(s) -> None:
            if s.conquest is None:
                return
            for slot in s.conquest.schedule:
                if slot.status == "planned":
                    slot.at = slot.muster_at = s.time + 10 ** 8

        self.world.mutate_season(stale)
        if self.essay_on():  # 〈天下形勢〉寫到一半：land 撥過 22:00 的那張單前半就收掉了，這裡另開一張、A 段拿走、C 段還沒收（後半的同步照寬限收）
            self.do(ADMIN, "xingshi_now")
            self.begin()
            game = self.server.game_for(self.G_SEAT)
            with self.server._locked(game):
                req = game.xingshi_request()
            emit("前半拿走單子（A 段）", None if req is None else {"n": req.n, "key": req.key})
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".landturn.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".landturn.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        self.login_all()  # 登入就同步：沒領的分紅在這裡補（G_LAY、H_PAY）
        for who in (self.G_LAY, self.H_PAY, self.G_PAY):
            self.me(who, "登入之後")
        self.world_view("登入之後")

    def quiet(self) -> None:
        """同一天、沒跨過 22:00：換天的掛鉤什麼都不做（settled_key 不動）。"""
        self.clock_to(1, 10, 30)
        for who in (self.G_SEAT, self.LONE):
            self.main(who)
        self.world_view("沒跨過")

    def turn1(self) -> None:
        """同步跨過 22:00：第一個看到新的一天的人觸發——前一天沒開成的那一場作罷、開一張〈天下形勢〉的單；新的一天官軍可以再下一張戰書。"""
        self.clock_to(1, 22, 5)
        self.view(self.G_SEAT, "跨過 22:00")
        self.world_view("換天一")
        d = self.blocks.get("D", "nowhere")
        if self.on():
            self.preset_bar(d, "guan", 75.0, self.G_PAY)
        self.file_letter(self.G_SEAT, d, "新的一天再下")
        self.view(self.H_SEAT, "黃巾看")
        for who in (self.G_LAY, self.LONE):
            self.main(who)

    def essay(self, tag: str) -> None:
        self.view(self.G_SEAT, f"{tag} 單子開著")
        self.world_view(f"{tag} 單子開著")
        emit(f"{tag} xingshi_once", self.server.xingshi_once(self.server.game_for(self.G_SEAT)))
        self.view(self.G_SEAT, f"{tag} 收下之後")
        self.world_view(f"{tag} 收下之後")

    def essay1(self) -> None:
        """B 段模型叫不動：照固定段收。"""
        MODEL["xingshi"] = None
        self.essay("叫不動")

    def turn2(self) -> None:
        """沒人在線，伺服器排程（server.world_step）跨過 22:00 也換天。"""
        self.clock_to(2, 22, 5)
        self.begin()
        emit("排程 world_step", self.server.world_step(time.time))
        self.world_view("換天二（排程）")

    def essay2(self) -> None:
        """B 段模型回了一篇夠長的。"""
        MODEL["xingshi"] = "good"
        try:
            self.essay("模型回了")
        finally:
            MODEL["xingshi"] = None

    def turn3(self) -> None:
        """管理者快轉跨過 22:00（advance）；之後現實時鐘的人同步，日子只准往前走（不重排、不倒退）。"""
        self.do(ADMIN, "fast_forward", {"hours": 24})
        self.world_view("換天三（快轉）")
        self.clock_to(3, 9, 0)
        self.main(self.G_SEAT)
        self.world_view("快轉之後現實時鐘的人同步")

    def essay3(self) -> None:
        """B 段模型回了太短的：過不了 clean，照固定段。"""
        MODEL["xingshi"] = "short"
        self.do(ADMIN, "xingshi_now")  # 快轉那一張單，現實時鐘的人一同步就過了寬限收掉了：這一張另外開
        try:
            self.essay("回太短")
        finally:
            MODEL["xingshi"] = None

    def tickets(self) -> None:
        """單子的其他走法：管理者現在就開一篇（兩次：第二次先把還在等的收掉）；佇列沒讓這一趟跑（單子放回去、隔 retry 再試）；開了超過寬限照固定段收。"""
        self.do(ADMIN, "xingshi_now")
        self.view(self.G_SEAT, "現在就開一篇")
        self.do(ADMIN, "xingshi_now")
        self.world_view("開了第二篇")
        real_queue = self.server.QUEUE

        class Skip:
            def run(self, *a, **k):
                from llm_queue import Busy

                raise Busy("same_behavior")

        self.server.QUEUE = Skip()
        try:
            emit("佇列沒輪到 xingshi_once", self.server.xingshi_once(self.server.game_for(self.G_SEAT)))
        finally:
            self.server.QUEUE = real_queue
        self.world_view("放回去之後")
        STEP[0] += 30  # 超過 grace_seconds（900 秒）：下一個同步的人照固定段收
        self.main(self.G_SEAT)
        self.world_view("過了寬限")
        self.view(self.LONE, "散人看形勢")

    def admin(self) -> None:
        """管理者五個救場工具：定一塊歸誰（成、本來就這樣、不是搶得下的、不是兩軍）、定進度（部分、推滿、不是此刻佔著的那一方才收）、立刻下戰書（成、已有一場、不收）、
        取消一場攻城（成、找不到）、現在就開一篇天下形勢（上面已走）；非管理者按了被擋；管理者頁的下拉選單。"""
        a, b, cc, d = (self.blocks.get(k, "nowhere") for k in ("A", "B", "C", "D"))
        self.do(self.G_SEAT, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": "nowhere", "side": "guan"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "dragon"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": ""})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "huang", "value": 55})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "huang", "value": 0})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "nobody", "value": 10})
        self.do(ADMIN, "conquest_progress", {"id": a, "side": "huang", "value": 100})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "huang"})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "huang"})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "guan"})
        self.do(ADMIN, "admin_conquest_letter", {"id": "nowhere", "side": "guan"})
        self.call(ADMIN, "GET", "/api/admin")
        self.main(self.G_SEAT)  # 下一個同步的人把剛下的戰書開成集結
        w = self.world.get_season()
        slots = [] if w.conquest is None else [s.id for s in w.conquest.schedule if s.status not in ("done", "void")]
        emit("還沒打完的攻城", slots)
        for sid in slots[:1] + ["no-such-slot"]:
            self.do(ADMIN, "conquest_cancel", {"id": sid})
        self.do(ADMIN, "xingshi_now")
        self.world_view("救場之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在 A）若干輪，跨過 22:00 再若干輪；整季機器人眼前的選單挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        home = self.blocks.get("A", "nowhere")
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.journey = p.bot.faction, None
            if home in self.c.locations:
                p.location = home
                p.visited.add(home)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for k in range(int(os.environ.get("SB_LANDTURN_TICKS", "8"))):
                if k == 4:
                    self.clock_to(4, 22, 10)
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "營己", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.journey = "guan" if "guan" in sides else None, None
        if home in self.c.locations:
            p.location = home
            p.visited.add(home)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：戰書、時程表、分紅、形勢單怎麼處理。"""
        self.do(ADMIN, "end_season")
        for who in (self.G_SEAT, self.H_SEAT, self.LONE):
            self.view(who, "收季之後")
        self.do(ADMIN, "next_season")
        for who in (self.G_SEAT, self.H_SEAT, self.LONE):
            self.view(who, "換季之後")
            self.me(who, "換季之後")
        self.world_view("換季之後")


def _landturn_register_track(name: str, scenario: type, mutation: tuple, profile: str) -> None:
    """再開一軌（TRACKS、TRACK_NAMES、MUTATIONS、MUTANT_PROFILE 四張表一起登記；同 _military_register_track）。"""
    global TRACK_NAMES
    TRACKS[name] = scenario
    TRACK_NAMES = (*TRACK_NAMES, name)
    MUTATIONS[name] = mutation
    MUTANT_PROFILE[name] = profile


# 改一個字（selftest）：前一天沒開成的攻城作罷那一句（搬之前在 tianxia/conquest_day.py、之後在 tianxia/features/territory_acts/conquest_day.py；
# 第 2 項是之後的檔名，搬的人照實際的檔名改這一個字串）
_landturn_register_track("landturn", LandTurnScenario, (("tianxia/features/territory_acts/conquest_day.py", "tianxia/conquest_day.py"),
                                                        ('VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷。"',
                                                         'VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷！"')), "week7")


if __name__ == "__main__":
    sys.exit(main())
