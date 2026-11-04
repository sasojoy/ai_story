"""工作包說明：這是第 12 批（頭目戰、擂台）QA 用的，留著當範本。
環境變數：QA_DIR（暫存資料夾，放 repo 外面；底下要有 HEAD、BASE 兩份工作樹）、QA_PORTS（預設 8161,8162）、QA_HOST（預設 qachk）。
要換成你這一批的：flow()、帳號名單、/__qa/peek 讀的欄位。用法看工作包的「共用-環境與做法.md」第六節。"""
"""單挑包第 1 批（全部拆包第 12 批：單人頭目戰、擂台、場邊事件）QA：兩台真伺服器逐位元組比（照 b8-chk/s/drive.py、b22-chk/s/drive.py 改）。
python drive.py <season21|week7> <hb|hh|bb|mh> [snap]
  hb：A＝HEAD（埠 8169、Host bout1chk.localhost:8169）、B＝BASE（埠 8170、Host 127.0.0.1:8170）；hh／bb：同一份跑兩台（看凍不凍得住）；
  mh：A＝MUT（HEAD 改一個字，看比對有沒有牙）、B＝HEAD。
  snap：在三個點（頭目戰打到一半、擂台收場之後、收季之前看稱號）把 A 的資料庫備份下來（B 也備），給截圖用。
每一步：兩台的假時鐘各往前推 DT 秒，同一個請求（同帳號各自的 cookie）先打 A 再打 B，等鎖外的背景執行緒停了，狀態碼與內容逐位元組比。
收場 taskkill /T，兩個資料庫（與旁邊的小檔）逐表比。密碼是這兩台暫存伺服器的測試值（照帳號雜湊、寫在 local/），不印。"""
import difflib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
CHK = Path(os.environ["QA_DIR"]).resolve()
PY = sys.executable
T0 = 1793430000  # 2026-10-31 15:00 台灣
DT = 2.0
profile, mode = sys.argv[1], sys.argv[2]
SNAP = len(sys.argv) > 3 and sys.argv[3] == "snap"
ROOTS = {"h": CHK / "HEAD", "b": CHK / "BASE", "m": CHK / "MUT"}
A_ROOT, B_ROOT = ROOTS[mode[0]], ROOTS[mode[1]]
PORTS = tuple(int(x) for x in os.environ.get("QA_PORTS", "8161,8162").split(","))
HOSTS = (f"{os.environ.get('QA_HOST', 'qachk')}.localhost:{PORTS[0]}", f"127.0.0.1:{PORTS[1]}")
stamp = time.strftime("%H%M%S")
RUN = f"{profile}-{mode}-{stamp}"
OUT = CHK / "out" / RUN
OUT.mkdir(parents=True, exist_ok=True)
for d in ("db", "logs", "local", "snap"):
    (CHK / d).mkdir(exist_ok=True)

ADMIN = ("qa12admin", "驗收官")
BOSS = ("qa12boss", "程聽松")  # 打單人頭目：贏一次、輸一次
R1 = ("qa12ring1", "范映雪")  # 擂台：先報名（第一名）
R2 = ("qa12ring2", "柯遠帆")  # 擂台：後報名、挑范映雪
W7 = ("qa12w7", "鍾離岫")  # week7 那一位
ARMOR = {"id": "甲:1", "slot": "armor", "name": "試甲", "attribute": "剛", "tier": 3, "quality": "上品", "edge": 100}
SKILL = "jichu_quanjiao"
MOVES = ("固守", "強攻", "奇襲")


def pw(login: str) -> str:
    v = "pw-" + hashlib.sha256(("b12chk|" + login).encode()).hexdigest()[:14]
    (CHK / "local" / f"{login}.pw").write_text(v, encoding="utf-8")
    return v


def stop_tree(proc) -> None:
    """關掉伺服器整棵行程（Windows 用 taskkill /T，其他系統直接 kill）。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def listening(port: int, seconds: float = 120) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def start(label: str, root: Path, port: int, db: Path):
    env = os.environ.copy()
    env.update(QA_ROOT=str(root), QA_T0=str(T0), QA_PORT=str(port), TIANXIA_DB=str(db), TIANXIA_ADMINS="驗收官",
               PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", TIANXIA_PROFILE=profile)
    env.pop("TIANXIA_PUBLIC_URL", None)
    log = open(CHK / "logs" / f"srv-{RUN}-{label}.log", "w", encoding="utf-8")
    proc = subprocess.Popen([PY, "-u", "-X", "utf8", str(Path(__file__).with_name("serve.py"))], cwd=str(root), env=env, stdout=log,
                            stderr=subprocess.STDOUT)
    print(label, root.name, "port", port, "pid", proc.pid, "db", db.name, flush=True)
    return proc, log


def vapid():
    """兩份工作樹的 .local/webpush_vapid.pem 用同一把（第一次產生、存在 local/）。"""
    key = CHK / "local" / "webpush_vapid.pem"
    if not key.exists():
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        k = ec.generate_private_key(ec.SECP256R1())
        key.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    for r in {A_ROOT, B_ROOT}:
        (r / ".local").mkdir(exist_ok=True)
        shutil.copyfile(key, r / ".local" / "webpush_vapid.pem")
    return hashlib.sha256(key.read_bytes()).hexdigest()[:12]


class Pair:
    def __init__(self):
        self.sess = [{}, {}]
        self.n = 0
        self.diffs = []
        self.lines = []
        self.clock = T0
        self.status = {}

    def s(self, i, who):
        return self.sess[i].setdefault(who, requests.Session())

    def raw(self, i, method, path, who=None, body=None):
        url = f"http://127.0.0.1:{PORTS[i]}{path}"
        h = {"Host": HOSTS[i]}
        sess = self.s(i, who) if who else requests
        r = sess.request(method, url, json=body if method == "POST" else None, headers=h, timeout=300)
        return r.status_code, r.content

    def idle(self, i):
        j = None
        for _ in range(600):
            j = requests.get(f"http://127.0.0.1:{PORTS[i]}/__qa/idle", timeout=30).json()
            if not j["busy"] and not j["tale_running"]:
                return
            time.sleep(0.05)
        print("  !! 背景執行緒一直沒停", i, j, flush=True)

    def tick(self, dt=DT):
        got = [requests.post(f"http://127.0.0.1:{PORTS[i]}/__qa/clock", json={"dt": dt}, timeout=30).json()["t"] for i in (0, 1)]
        assert got[0] == got[1], got
        self.clock = got[0]

    def call(self, who, method, path, body=None, note="", dt=DT):
        self.tick(dt)
        got = []
        for i in (0, 1):
            got.append(self.raw(i, method, path, who, body))
            self.idle(i)
        self.n += 1
        same = got[0][0] == got[1][0] and got[0][1] == got[1][1]
        self.status[(got[0][0], got[1][0])] = self.status.get((got[0][0], got[1][0]), 0) + 1
        sha = [hashlib.sha256(g[1]).hexdigest()[:12] for g in got]
        shown = {k: ("<抹>" if k in ("password", "again") else v) for k, v in body.items()} if isinstance(body, dict) else body
        try:
            data = json.loads(got[0][1].decode("utf-8"))
        except Exception:  # noqa: BLE001
            data = {"_raw": got[0][1][:200].decode("utf-8", "replace")}
        msg = ""
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("detail") or ""
        msg = str(msg).replace("\n", " ")[:140]
        line = (f"{self.n:04d} {'==' if same else '!!'} {got[0][0]}/{got[1][0]} {len(got[0][1])}B {sha[0]} {who or '-'} {method} {path} "
                f"{json.dumps(shown, ensure_ascii=False) if shown else ''} {note} → {msg}")
        self.lines.append(line)
        (OUT / f"{self.n:04d}-A.bin").write_bytes(got[0][1])
        if not same:
            (OUT / f"{self.n:04d}-B.bin").write_bytes(got[1][1])
            self.diffs.append(line)
        print(line, flush=True)
        return data

    def qa(self, method, route, body=None, note=""):
        """擺位、查詢：兩台各打一次 /__qa/<route>（不推時鐘、不算步數），兩台的回應也比一次。"""
        got = []
        for i in (0, 1):
            url = f"http://127.0.0.1:{PORTS[i]}/__qa/{route}"
            r = requests.request(method, url, json=body if method == "POST" else None, timeout=300)
            got.append(r.json())
            self.idle(i)
        if got[0] != got[1]:
            line = f"QA !! {route} {json.dumps(body, ensure_ascii=False)} A={json.dumps(got[0], ensure_ascii=False)[:600]} B={json.dumps(got[1], ensure_ascii=False)[:600]}"
            self.diffs.append(line)
            print(line, flush=True)
        line = f"     {route} {json.dumps(body, ensure_ascii=False) if body else ''} {note} → {json.dumps(got[0], ensure_ascii=False)[:900]}"
        self.lines.append(line)
        print(line, flush=True)
        return got[0]

    def note(self, text):
        self.lines.append("# " + text)
        print("#", text, flush=True)

    # 小工具
    def main(self, who, note=""):
        return self.call(who, "GET", "/api/main", note=note)

    def choose(self, who, oid, note=""):
        return self.call(who, "POST", "/api/choose", {"id": oid}, note=note)

    def do(self, who, op, body=None, note=""):
        return self.call(who, "POST", f"/api/do/{op}", body or {}, note=note)

    def peek(self, who, note=""):
        return self.qa("POST", "peek", {"name": who}, note)

    def ladder(self, note=""):
        return self.qa("GET", "ladder", note=note)

    def edit(self, body, note=""):
        return self.qa("POST", "edit", body, note)

    def tweak(self, path, value):
        return self.qa("POST", "tweak", {"path": path, "value": value})

    def force(self, *draws):
        return self.qa("POST", "force", {"draws": list(draws)})

    def skip(self, seconds, note=""):
        self.tick(seconds)
        self.note(f"時鐘推 {seconds:.0f} 秒 → {self.clock:.0f}（{note}）")

    def backup(self, tag, dbs):
        if not SNAP:
            return
        for side, db in zip(("A", "B"), dbs):
            dst = CHK / "snap" / f"{profile}-{tag}-{side}.db"
            a = sqlite3.connect(str(db), timeout=30)
            b = sqlite3.connect(str(dst))
            a.backup(b)
            b.close()
            a.close()
        (CHK / "snap" / f"{profile}-{tag}-clock.txt").write_text(str(self.clock), encoding="utf-8")
        self.note(f"快照 {tag}（時鐘 {self.clock}）")


def view_of(v):
    return (v.get("main", v) or {}) if isinstance(v, dict) else {}


def opts(v):
    m = view_of(v)
    return {o["id"]: o for o in (m.get("options") or [])} if isinstance(m, dict) else {}


def flow(X: Pair, dbs):
    info = X.qa("GET", "info")
    keys = info["keys"]

    def settle(who, rounds=6):
        for _ in range(rounds):
            first = [i for i, o in opts(X.main(who, "開局待選")).items() if i.startswith("choice:") and o.get("enabled")]
            if not first:
                return
            X.choose(who, first[0], "開局待選")

    def make(acct, sex):
        login, who = acct
        X.call(who, "POST", "/api/register", {"login": login, "password": pw(login), "again": pw(login)})
        X.call(who, "POST", "/api/character", {"name": who, "gender": sex})
        settle(who)

    def show(who, tag, prefix=("duel:", "arena:", "act:arena", "act:explore", "explore:")):
        v = X.main(who, tag)
        m = view_of(v)
        o = opts(v)
        X.note(f"{who} {tag}：鈕 {[(i, o[i].get('label'), o[i].get('enabled')) for i in sorted(o) if i.startswith(prefix)]}")
        notes = m.get("action_notes") or {}
        X.note(f"{who} {tag}：行動列那一行 {json.dumps({k: v for k, v in sorted(notes.items()) if 'explore' in k or 'arena' in k}, ensure_ascii=False)}")
        if m.get("free_text") or m.get("free_text_note"):
            X.note(f"{who} {tag}：輸入框 {json.dumps([m.get('free_text'), m.get('free_text_note'), m.get('free_text_op')], ensure_ascii=False)}")
        return v

    def explore(who, tag):
        """探索一顆：抽到遭遇（/__qa/force），有三選一的季按練功那一顆。"""
        X.edit({"name": who, "stamina_full": True}, "體力補滿")
        X.force("ENCOUNTER")
        v = X.choose(who, "act:explore", tag)
        o = opts(v) if opts(v) else opts(X.main(who, tag))
        ex = sorted(i for i in o if i.startswith("explore:"))
        if ex:
            X.note(f"{who} 三選一 {[(i, o[i].get('label'), o[i].get('enabled')) for i in ex]}")
            pick = next((i for i in ex if "practice" in i and o[i].get("enabled")), None)
            if pick:
                X.choose(who, pick, tag)
        X.force()
        d = X.peek(who, f"{tag}之後")
        return d.get("duel") is not None

    def bout(who, prefix, edge, rounds=8, tag=""):
        for k in range(rounds):
            d = X.peek(who)
            if d.get(prefix) is None:
                return
            if edge is not None:
                X.edit({"name": who, f"{prefix}_edge": edge}, f"氣勢擺在 {edge}")
            o = opts(X.main(who, f"{tag} 第 {k + 1} 招之前"))
            pick = next((f"{prefix}:{m}" for m in MOVES[k % 3:] + MOVES[:k % 3] if (o.get(f"{prefix}:{m}") or {}).get("enabled")), None)
            if pick is None:
                X.note(f"{who} 選單上沒有招 {sorted(o)}")
                return
            X.choose(who, pick, tag)

    def reports(who):
        X.call(who, "GET", "/api/reports")

    def fight_id(name):
        return f"arena:fight:{keys[name]}"

    # ── 開季、建角色 ──
    X.call(None, "GET", "/")
    X.call(None, "GET", "/static/app.js")
    X.qa("POST", "admin", {"login": ADMIN[0], "password": pw(ADMIN[0]), "name": ADMIN[1]})
    X.call(ADMIN[1], "POST", "/api/login", {"login": ADMIN[0], "password": pw(ADMIN[0])})
    X.do(ADMIN[1], "open_season")
    players = [BOSS, R1, R2] if profile == "season21" else [W7]
    for acct, sex in zip(players, ("男", "女", "男")):
        make(acct, sex)
    fighter = BOSS[1] if profile == "season21" else W7[1]

    # ── 單人頭目戰：長社（黃巾小帥），穿一件甲 ──
    X.edit({"name": fighter, "loc": "changshe", "stamina_full": True, "veteran": True, "learn": [SKILL, 9], "armor": ARMOR}, "長社、練到第九成、穿甲")
    show(fighter, "長社 開打之前")
    X.peek(fighter, "開打之前")
    X.tweak("duel.explore_chance", 1.0)
    if explore(fighter, "探索撞上頭目"):
        show(fighter, "頭目戰的選單")
        X.choose(fighter, "duel:固守", "第一回合")
        X.backup("boss", dbs)
        X.do(fighter, "duel_text", {"text": "我藉著塵土翻身而起，一掌拍向他持刀的手腕。"}, "放手一搏")
        X.peek(fighter, "放手一搏之後")
        show(fighter, "放手一搏之後")
        bout(fighter, "duel", 89.0, tag="打贏頭目")
        X.peek(fighter, "打贏頭目之後")
        show(fighter, "打贏頭目之後")
        reports(fighter)
    explore(fighter, "冷卻中再探索")
    show(fighter, "冷卻中")
    if profile == "season21":
        X.skip(info["cooldown"] / max(info["time_scale"], 1e-6) + 120, "頭目的冷卻擺過去")
        show(fighter, "冷卻過了")
        if explore(fighter, "再撞上頭目"):
            bout(fighter, "duel", 11.0, tag="打輸頭目")
            X.peek(fighter, "打輸頭目之後")
            show(fighter, "打輸頭目之後")
            reports(fighter)
        X.skip(info["cooldown"] / max(info["time_scale"], 1e-6) + 120, "頭目的冷卻又擺過去")
        show(fighter, "次數用完")
        explore(fighter, "次數用完再探索")
        X.peek(fighter, "次數用完再探索之後")
    X.tweak("duel.explore_chance", 0.05)

    # ── 擂台 ──
    if profile == "season21":
        ring = [R1[1], R2[1]]
        for who, lv in zip(ring, (5, 4)):
            X.edit({"name": who, "loc": "yingchuan", "stamina_full": True, "veteran": True, "learn": [SKILL, lv]}, f"潁川、練到第 {lv} 成")
        show(R1[1], "第 1 週（擂台照週解鎖）")
        X.choose(R1[1], "act:arena", "第 1 週按擂台")
        X.tweak("jianfa.week_unlock", False)
        first, second = ring
    else:
        X.edit({"name": ADMIN[1], "loc": "yingchuan", "stamina_full": True, "veteran": True, "learn": [SKILL, 4]}, "管理者也上擂台")
        X.edit({"name": W7[1], "loc": "yingchuan", "stamina_full": True}, "到潁川")
        first, second = W7[1], ADMIN[1]
    show(first, "擂台入口")
    X.choose(first, "act:arena", "打開擂台")
    show(first, "擂台第二層")
    X.choose(first, "arena:join", "報名")
    X.choose(first, "arena:back", "返回")
    X.choose(second, "act:arena", "打開擂台")
    X.choose(second, "arena:join", "報名")
    show(second, "報名之後")
    X.choose(second, "arena:join", "再按一次：更新分身")
    X.ladder("兩人報名之後")
    X.tweak("arena.crowd.chance", 1.0)
    X.tweak("arena.crowd.outrage_chance", 1.0)
    X.choose(second, fight_id(first), f"挑{first}")
    show(second, "擂台打到一半")
    X.do(second, "duel_text", {"text": "我踏前半步虛晃一招，引他出手再側身反擊。"}, "擂台的放手一搏")
    X.peek(second, "擂台放手一搏之後")
    X.backup("ring", dbs)
    bout(second, "arena", 89.0, tag="擂台打贏")
    X.peek(second, "擂台收場之後")
    show(second, "擂台收場卡")
    X.ladder("擂台收場之後")
    X.choose(second, "arena:back", "返回")
    X.main(first, "守擂的人補戰報")
    X.peek(first, "守擂補戰報之後")
    reports(first)
    reports(second)
    # 名次掉下來的人挑回去：出一招就認輸
    X.choose(first, "act:arena", "打開擂台")
    show(first, "名次掉下來之後")
    X.choose(first, fight_id(second), f"挑{second}")
    bout(first, "arena", None, rounds=1, tag="出一招")
    if X.peek(first).get("arena") is not None:
        X.choose(first, "arena:yield", "認輸")
    X.peek(first, "認輸之後")
    show(first, "認輸之後（同一對冷卻：灰掉的挑擂鈕）")
    X.choose(first, fight_id(second), "按灰掉的挑擂鈕")
    X.choose(first, "arena:back", "返回")
    X.main(second, "守擂的人補戰報（守住）")
    X.ladder("認輸之後")
    X.tweak("arena.crowd.chance", 0.0)
    X.tweak("arena.crowd.outrage_chance", 0.0)
    # 換日領俸
    X.skip(86400 + 60, "換日（現實時間）")
    for who in (first, second, fighter):
        X.main(who, "換日之後")
        X.peek(who, "換日之後")
    X.ladder("換日之後")

    # ── 稱號被讀：狀態列、名帖、玩家卡、榜單、酒肆查人 ──
    reader = fighter if profile == "season21" else W7[1]
    top = second
    X.edit({"name": reader, "loc": "yingchuan", "stats": {"silver": 500}, "stamina_full": True}, "到潁川、帶銀兩")
    X.edit({"name": top, "loc": "yingchuan"}, "站在潁川")
    v = X.main(top, "擂主的狀態列")
    X.note(f"{top} 狀態列 {json.dumps(view_of(v).get('status'), ensure_ascii=False)[:600]}")
    X.call(top, "GET", "/api/mingtie")
    X.call(reader, "GET", f"/api/peer?name={top}")
    X.call(reader, "GET", "/api/boards")
    X.choose(reader, "act:tavern", "進酒肆")
    X.do(reader, "tavern", {"op": "seek", "target": top, "text": ""}, "查人")
    X.choose(reader, "tavern:back", "出酒肆")
    X.backup("titles", dbs)

    # ── 每個人的 /api/main 與 /api/reports ──
    everyone = [a[1] for a in players] + [ADMIN[1]]
    for who in everyone:
        X.main(who, "收尾")
        reports(who)
    X.call(ADMIN[1], "GET", "/api/admin")

    # ── 收季：前三名、季末獎勵、江湖史的歷屆擂主；開下一季 ──
    X.do(ADMIN[1], "end_season")
    X.ladder("收季之後")
    for who in everyone:
        v = X.main(who, "休季同步")
        X.peek(who, "休季同步之後")
    X.note(f"江湖史 {json.dumps(view_of(v).get('chronicle'), ensure_ascii=False)[:800]}")
    for who in everyone:
        reports(who)
    X.do(ADMIN[1], "next_season")
    for who in everyone:
        X.main(who, "換季之後")
        X.peek(who, "換季之後")
    X.ladder("換季之後")


def dump(path: Path):
    mask = {"salt", "hash", "token", "session", "cookie"}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        rows = []
        for row in con.execute(f"SELECT * FROM {table}").fetchall():
            rows.append(repr(["<抹掉>" if any(m in c.lower() for m in mask) else v for c, v in zip(cols, row)]))
        out[table] = sorted(rows)
    con.close()
    return out


def dbcmp(a: Path, b: Path, lines: list):
    da, db_ = dump(a), dump(b)
    bad = 0
    for t in sorted(set(da) | set(db_)):
        ra, rb = da.get(t), db_.get(t)
        if ra == rb:
            lines.append(f"  {t}: 一樣（{len(ra or [])} 列）")
            continue
        bad += 1
        lines.append(f"  {t}: 不一樣（{len(ra or [])} 對 {len(rb or [])} 列）")
        d = [x for x in difflib.unified_diff(ra or [], rb or [], lineterm="", n=0) if not x.startswith(("---", "+++", "@@"))]
        for line in d[:6]:
            lines.append("      " + line[:600])
    lines.append(f"  不一樣的表：{bad}")
    return bad


def main():
    dbs = [CHK / "db" / f"{RUN}-A.db", CHK / "db" / f"{RUN}-B.db"]
    procs = []
    X = Pair()
    t_start = time.time()
    try:
        print("vapid", vapid(), flush=True)
        procs.append(start("A", A_ROOT, PORTS[0], dbs[0]))
        procs.append(start("B", B_ROOT, PORTS[1], dbs[1]))
        for port in PORTS:
            if not listening(port):
                print("server did not come up", port, flush=True)
                return
        X.qa("GET", "where")
        flow(X, dbs)
    except Exception as exc:  # noqa: BLE001
        import traceback

        X.note(f"腳本中途停了：{type(exc).__name__}: {exc}")
        X.lines.append(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        for proc, log in procs:
            stop_tree(proc)
            log.close()
        time.sleep(2)
        report = [f"run {RUN}  A={A_ROOT.name}:{PORTS[0]} B={B_ROOT.name}:{PORTS[1]}  requests={X.n}  diff={len(X.diffs)}  "
                  f"secs={time.time() - t_start:.0f}  status={ {f'{k[0]}/{k[1]}': v for k, v in sorted(X.status.items())} }"]
        report += ["差異："] + (X.diffs or ["  （沒有）"])
        if all(d.exists() for d in dbs):
            report.append("資料庫逐表比：")
            dbcmp(dbs[0], dbs[1], report)
            for suffix in ("-push.sqlite", "-tale.sqlite", "-narration.sqlite", "-archive.sqlite"):
                sa, sb = (d.with_name(f"{d.stem}{suffix}") for d in dbs)
                if sa.exists() and sb.exists():
                    report.append(f"小檔 {suffix}：")
                    dbcmp(sa, sb, report)
                elif sa.exists() != sb.exists():
                    report.append(f"小檔 {suffix}：只有一邊有（A {sa.exists()}、B {sb.exists()}）")
        side = sorted(p.name for p in (CHK / "db").glob(f"{RUN}-A*"))
        report.append("A 旁邊的檔：" + ", ".join(side))
        text = "\n".join(report)
        (CHK / f"cmp-{RUN}.txt").write_text(text + "\n\n步驟：\n" + "\n".join(X.lines) + "\n", encoding="utf-8")
        print(text, flush=True)


main()
