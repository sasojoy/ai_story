"""客服的橋（客服自動受理第 217 批；設計 6.1、第七節，企劃者 2026-11-10「照計畫繼續」）：主機上一支小程式，唯讀開客服單的旁檔，
每 15 秒看一次有沒有新單、玩家再回一句、玩家按了找真人、單上補了截圖，有就貼到 Discord 的 #客服（webhook），並在 --log 檔記一行
（NEW 12／REPLY 12／HUMAN 12／FILE 12：客服官的 Monitor 盯這個檔）。

- 不 import tianxia（同 scripts/monitor.py）：旁檔與截圖的資料夾照 store.store_path、store.files_dir 的檔名規則自己算
  （<db stem>-support.sqlite、<db stem>-support-files/<單號>/<seq>.<kind>），類別名自己一份 CATEGORIES（測試釘死跟包一樣）。
- 只讀旁檔（mode=ro），不建表、不寫；進度記在 --state（預設 .local/support_bridge.json），逐張記：
  {"new": [貼過 NEW 的單號…], "reply": 貼過的玩家回覆最大 id, "flag": 最大 flags.id, "file": 最大 files.id}。
- 新單等 grace（60）秒、或已有一張圖才貼（圖跟著一起上）；還在等的單，它的玩家回覆、找真人也先停著，不越過。
- 貼到 Discord 的字不帶帳號（login）、Email、手機；payload_json 一律帶 allowed_mentions（單裡寫 @everyone 也點不到人；
  找真人只點 .local/support.json 的 mention 那兩個 ID）。
- 預設路徑一律從這支腳本所在的 repo 根算（橋從 C:\\Ray\\tianxia-support\\ 啟動，工作目錄不是 repo）。
退版：這支刪掉就沒了，遊戲不受影響（不在遊戲的程式路徑上）。"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

# 類別 id → 顯示的字（同 tianxia/features/support/rules.py 的 CATEGORIES；這支不能 import 包，測試釘死兩份一樣）
CATEGORIES: dict[str, str] = {
    "account": "帳號",  # 待 joy 潤
    "mall": "商城",  # 待 joy 潤
    "game": "遊戲問題",  # 待 joy 潤
    "other": "其他",  # 待 joy 潤
}

KINDS = ("NEW", "REPLY", "HUMAN", "FILE")
TEXT_MAX = 1900  # Discord 一則上限 2,000 字，留一點給頭一行以外的東西
CUT = "…"  # 待 joy 潤
REPLY_LEAD = "玩家再回："  # 待 joy 潤
HUMAN_LEAD = "玩家要找真人"  # 待 joy 潤
FILE_LEAD = "補一張截圖"  # 待 joy 潤


@dataclass
class Event:
    """一則要貼的事。ref：NEW 是單號、REPLY 是 replies.id、HUMAN 是 flags.id、FILE 是 files.id。text：NEW 是單的全文、REPLY 是那一則，
    其他空的。files：要一起上的圖（NEW 帶那張單此刻全部的圖、FILE 帶那一張）。mention：要點 mention 那兩個 ID（只有 HUMAN）。
    covers：這一則貼成功之後，files 的水位可以走到哪（掃描時算好：比它小的圖都已經跟 NEW 或 FILE 上去了）。"""
    kind: str
    ticket_id: int
    ref: int
    text: str
    files: list[Path]
    mention: bool
    covers: int = field(default=0, compare=False)


def empty_state() -> dict:
    return {"new": [], "reply": 0, "flag": 0, "file": 0}


def paths(db: Path) -> tuple[Path, Path]:
    """(旁檔, 截圖的資料夾)：同 store.store_path、store.files_dir。"""
    db = Path(db)
    return db.with_name(f"{db.stem}-support.sqlite"), db.with_name(f"{db.stem}-support-files")


def _files_dir_of(conn: sqlite3.Connection) -> Path:
    """連線開的旁檔 → 截圖的資料夾（<stem>-support.sqlite → <stem>-support-files）。"""
    main = next(r for r in conn.execute("PRAGMA database_list") if r[1] == "main")
    sidecar = Path(main[2])
    return sidecar.with_name(sidecar.stem + "-files")


def scan(conn: sqlite3.Connection, state: dict, now: float, grace: float) -> list[Event]:
    """這一輪要貼的，照先後：NEW（單號小的先）→ REPLY（replies.id 序，只看玩家的）→ HUMAN（flags.id 序，只看 kind='human'）→
    FILE（files.id 序，只對之前就貼過 NEW 的單）。還沒貼 NEW 的單的 REPLY、HUMAN：那一種停在它前面，後面同種的都等。
    呼叫端要一輪的四張表看到同一個快照，就先 BEGIN 再叫。"""
    posted = {int(t) for t in state.get("new", [])}
    folder = _files_dir_of(conn)
    file_rows = conn.execute("SELECT id, ticket_id, seq, kind FROM files WHERE id > ? ORDER BY id", (int(state.get("file", 0)),)).fetchall()
    with_files = {int(r[0]) for r in conn.execute("SELECT DISTINCT ticket_id FROM files")}
    by_ticket: dict[int, list] = {}
    for r in conn.execute("SELECT id, ticket_id, seq, kind FROM files ORDER BY ticket_id, seq"):
        by_ticket.setdefault(int(r[1]), []).append(r)

    def path_of(r) -> Path:
        return folder / str(int(r[1])) / f"{int(r[2])}.{r[3]}"

    events: list[Event] = []
    fresh: set[int] = set()
    for tid, body, created in conn.execute("SELECT id, body, created FROM tickets ORDER BY id"):
        tid = int(tid)
        if tid in posted:
            continue
        if now - float(created) >= grace or tid in with_files:
            fresh.add(tid)
            events.append(Event("NEW", tid, tid, body, [path_of(r) for r in by_ticket.get(tid, [])], False))
    shown = posted | fresh
    for rid, tid, body in conn.execute(
            "SELECT id, ticket_id, body FROM replies WHERE id > ? AND staff = 0 ORDER BY id", (int(state.get("reply", 0)),)):
        if int(tid) not in shown:
            break
        events.append(Event("REPLY", int(tid), int(rid), body, [], False))
    for fid, tid, kind in conn.execute("SELECT id, ticket_id, kind FROM flags WHERE id > ? ORDER BY id", (int(state.get("flag", 0)),)):
        if kind != "human":
            continue  # relay（客服官轉達）不貼；後面有 HUMAN 貼了水位就走過它
        if int(tid) not in shown:
            break
        events.append(Event("HUMAN", int(tid), int(fid), "", [], True))
    for r in file_rows:
        if int(r[1]) in posted:
            events.append(Event("FILE", int(r[1]), int(r[0]), "", [path_of(r)], False))
    # 圖的水位：照先後一則一則貼，貼到第 k 則為止哪些圖上去了（NEW 帶的、FILE 那一張），水位走到「比它小的都上去了」的最大 id
    pending = [int(r[0]) for r in file_rows]
    attached = {int(r[0]): int(r[1]) for r in file_rows}
    done: set[int] = set()
    mark = int(state.get("file", 0))
    for e in events:
        if e.kind == "NEW":
            done.update(f for f, t in attached.items() if t == e.ticket_id)
        elif e.kind == "FILE":
            done.add(e.ref)
        while pending and pending[0] in done:
            mark = pending.pop(0)
        e.covers = mark
    return events


def advance(state: dict, event: Event) -> None:
    """一則貼成功（或照規矩跳過）之後：進度往前走。"""
    if event.kind == "NEW" and event.ticket_id not in state["new"]:
        state["new"].append(event.ticket_id)
    elif event.kind == "REPLY":
        state["reply"] = max(int(state["reply"]), event.ref)
    elif event.kind == "HUMAN":
        state["flag"] = max(int(state["flag"]), event.ref)
    state["file"] = max(int(state["file"]), event.covers, event.ref if event.kind == "FILE" else 0)


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))


def render(event: Event, ticket_row, mention_ids=()) -> str:
    """貼到 #客服 的字：頭一行「#單號・類別・名號・版本・送單時間」，接著 NEW 是全文、REPLY 是那一則、HUMAN 點 mention 的 ID、FILE 一句。
    只讀單的 id、category、character、version、created、body：帳號（login）不讀。超過 TEXT_MAX 截掉補「…」。"""
    t = ticket_row
    head = "・".join((f"#{int(t['id'])}", CATEGORIES.get(t["category"], t["category"]), t["character"] or "", t["version"] or "", _when(t["created"])))
    if event.kind == "NEW":
        text = f"{head}\n{event.text}"
    elif event.kind == "REPLY":
        text = f"{head}\n{REPLY_LEAD}{event.text}"
    elif event.kind == "HUMAN":
        text = f"{head}\n{HUMAN_LEAD} " + " ".join(f"<@{i}>" for i in mention_ids)
    else:
        text = f"{head}\n{FILE_LEAD}"
    if len(text) > TEXT_MAX:
        text = text[: TEXT_MAX - len(CUT)] + CUT
    return text


def load_state(path: Path) -> dict:
    """進度檔不在＝全空（第一次開：先 --once --dry-run 把舊單記成貼過）。壞了丟 ValueError（呼叫端停下來，不重貼全部）。"""
    path = Path(path)
    if not path.exists():
        return empty_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state")
    state = empty_state()
    state["new"] = sorted({int(t) for t in data.get("new", [])})
    for key in ("reply", "flag", "file"):
        state[key] = int(data.get(key, 0))
    return state


def save_state(path: Path, state: dict) -> None:
    """暫存檔＋os.replace（寫到一半掛了，舊的那份還在）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def log_line(path: Path, text: str) -> None:
    """--log 檔附加一行（utf-8、馬上 flush）：只有 NEW 12、REPLY 12、HUMAN 12、FILE 12 四種，客服官的 Monitor 每一行都醒。"""
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
        f.flush()


MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
DEAD_WARN = "webhook 回 {code}：這一則跳過不貼（webhook 壞了或被刪了？看一下 .local/support.json）。"  # 待 joy 潤


def post(webhook: str, content: str, files: list[Path], mention_ids: list[str], post_fn=requests.post) -> str:
    """貼一則（multipart：payload_json＋files[i]）。payload_json 一律帶 allowed_mentions：一般 {"parse": []}（單裡寫 @everyone、<@某人> 也點不到）、
    要點人時 {"parse": [], "users": mention_ids}。回 "ok"（2xx）／"retry"（逾時、連不上、429、5xx：這一輪停、下一輪再來）／
    "dead"（其他 4xx：印一句警告、照樣前進，不然永遠卡在同一則）。例外的字不印（requests 的例外字串帶 webhook 網址＝金鑰）。"""
    allowed: dict = {"parse": []}
    if mention_ids:
        allowed["users"] = [str(i) for i in mention_ids]
    parts: dict = {"payload_json": (None, json.dumps({"content": content, "allowed_mentions": allowed}, ensure_ascii=False), "application/json")}
    for i, p in enumerate(files):
        try:
            data = Path(p).read_bytes()
        except OSError:
            continue  # 列在、檔不見了：不貼那一張（遊戲那邊看圖也是 404）
        kind = Path(p).suffix.lstrip(".")
        parts[f"files[{i}]"] = (Path(p).name, data, MIME.get(kind, "application/octet-stream"))
    try:
        r = post_fn(webhook, files=parts, timeout=20)
    except requests.RequestException:
        return "retry"
    code = int(r.status_code)
    if 200 <= code < 300:
        return "ok"
    if code == 429 or code >= 500:
        return "retry"
    print(DEAD_WARN.format(code=code), file=sys.stderr)
    return "dead"


NO_HOOK = "金鑰檔沒有 discord_webhook：只記 log、不貼 Discord（進度照樣往前）。"  # 待 joy 潤
BAD_CONFIG = "金鑰檔讀不到或格式不對：當成沒有 webhook，只記不貼。"  # 待 joy 潤
BAD_STATE = "進度檔讀不到或格式不對：先停下來（不然會把舊單全部重貼一次）；修好或刪掉再開。"  # 待 joy 潤
STUCK = "已經連續 {n} 輪沒貼成（旁檔讀不到或 Discord 沒回）；照樣繼續試。"  # 待 joy 潤
DRY = "（只記不貼）"  # 待 joy 潤
ALIVE_EVERY = 300


def _open_ro(sidecar: Path) -> sqlite3.Connection:
    conn = sqlite3.connect("file:" + Path(sidecar).as_posix() + "?mode=ro", uri=True, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _config(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        print(BAD_CONFIG, file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(BAD_CONFIG, file=sys.stderr)
        return {}
    return data


def _round(db: Path, state: dict, state_path: Path, log: Path, webhook: str | None, mention: list[str], grace: float,
           post_fn, now: float) -> bool:
    """一輪。回 False＝這一輪沒做完（旁檔讀不到、Discord 要再試）：停在那一則，進度不越過。"""
    sidecar, _ = paths(db)
    if not sidecar.exists():
        return True
    try:
        conn = _open_ro(sidecar)
        try:
            conn.execute("BEGIN")  # 四張表同一個快照
            events = scan(conn, state, now, grace)
            rows = {}
            for tid in {e.ticket_id for e in events}:
                row = conn.execute("SELECT id, category, character, version, created, body FROM tickets WHERE id = ?", (tid,)).fetchone()
                rows[tid] = dict(row)
            conn.execute("ROLLBACK")
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    for e in events:
        ids = list(mention) if e.mention else []
        if webhook:
            got = post(webhook, render(e, rows[e.ticket_id], ids), e.files, ids, post_fn)
            if got == "retry":
                return False
        advance(state, e)
        save_state(state_path, state)
        log_line(log, f"{e.kind} {e.ticket_id}")
        print(f"{e.kind} {e.ticket_id}" + ("" if webhook else DRY), flush=True)
    return True


def main(argv=None, *, post_fn=None, clock=time.time, sleep=time.sleep) -> int:
    """post_fn、clock、sleep 給測試注入（預設 requests.post、time.time、time.sleep）。"""
    p = argparse.ArgumentParser(description="客服的橋：新單、玩家再回、找真人、補圖貼到 #客服。")  # 待 joy 潤
    p.add_argument("--db", default=os.environ.get("TIANXIA_DB") or str(ROOT / "saves" / "tianxia.db"))
    p.add_argument("--config", default=str(ROOT / ".local" / "support.json"))
    p.add_argument("--state", default=str(ROOT / ".local" / "support_bridge.json"))
    p.add_argument("--log", required=True)
    p.add_argument("--interval", type=float, default=15.0)
    p.add_argument("--grace", type=float, default=60.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    try:
        opts = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    post_fn = post_fn or requests.post
    cfg = _config(Path(opts.config))
    hook = cfg.get("discord_webhook")
    webhook = None if opts.dry_run or not isinstance(hook, str) or not hook.strip() else hook.strip()
    mention = [str(i) for i in cfg.get("mention", []) if str(i).isdigit()] if isinstance(cfg.get("mention"), list) else []
    if webhook is None and not opts.dry_run:
        print(NO_HOOK, file=sys.stderr)
    state_path = Path(opts.state)
    try:
        state = load_state(state_path)
    except (OSError, ValueError, TypeError):
        print(BAD_STATE, file=sys.stderr)
        return 2
    log = Path(opts.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    fails = 0
    alive = None
    while True:
        now = clock()
        if alive is None or now - alive >= ALIVE_EVERY:
            alive = now
            print(f"ALIVE {_when(now)}", flush=True)
        ok = _round(Path(opts.db), state, state_path, log, webhook, mention, opts.grace, post_fn, now)
        fails = 0 if ok else fails + 1
        if fails and fails % 10 == 0:
            print(STUCK.format(n=fails), file=sys.stderr, flush=True)
        if opts.once:
            return 0 if ok else 1
        sleep(opts.interval)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
