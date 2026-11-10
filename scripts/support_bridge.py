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
