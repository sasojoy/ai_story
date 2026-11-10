"""客服官的手（客服自動受理第 217 批；設計 6.2、第七節，企劃者 2026-11-10「照計畫繼續」）：客服官 session 只能跑這一支，
經 /api/support/*（Authorization: Bearer <.local/support.json 的 bot_token>）看清單、看單、回覆、註記、結單。

- 不 import tianxia，只打 HTTP（requests；測試注入 TestClient）。session 只用 .request(method, url, headers=, json=)。
- 回覆與註記的字一律從 stdin 讀（客服官沒有寫檔的權限；沒有 --file）。stdin 空的或只有空白不送。
- 鎖定模式（環境變數 TIANXIA_SUPPORT_LOCKED=1，cli.cmd 設）：--config、--url、--inbox 只從環境變數
  TIANXIA_SUPPORT_CONFIG、TIANXIA_SUPPORT_URL、TIANXIA_SUPPORT_INBOX 讀，命令列上出現一律拒絕（結束碼 2，什麼都不打）。
- 結束碼：0 成功；1 伺服器拒絕（那一句原樣印）、單找不到、stdin 空的；2 token 沒設或不對、連不上、參數不對、鎖定模式拒收。
- 永遠不印 token、不印帳號（login）、不印 Email／手機（帳號卡只印綁了哪幾種）。
- 預設路徑一律從這支腳本所在的 repo 根算（從 C:\\Ray\\tianxia-support\\ 啟動，工作目錄不是 repo）。
退版：這支刪掉就沒了，遊戲不受影響。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "http://127.0.0.1:7861"
LOCK_ENV = "TIANXIA_SUPPORT_LOCKED"
PATH_ENVS = {"--config": "TIANXIA_SUPPORT_CONFIG", "--url": "TIANXIA_SUPPORT_URL", "--inbox": "TIANXIA_SUPPORT_INBOX"}

LABELS = {
    "admin": "請管理者",  # 待 joy 潤
    "human": "等真人",  # 待 joy 潤
    "answered": "等玩家",  # 待 joy 潤
    "desk": "待客服官",  # 待 joy 潤
}
COUNTS = "請管理者 {admin}・等真人 {human}・等玩家 {answered}・待客服官 {desk}"  # 待 joy 潤
NO_TICKETS = "沒有沒結的單。"  # 待 joy 潤
WHO = {
    "internal": "內部註記",  # 待 joy 潤
    "system": "系統",  # 待 joy 潤
    "auto": "自動回覆",  # 待 joy 潤
    "staff": "客服",  # 待 joy 潤
    "player": "玩家",  # 待 joy 潤
}
STATUS = {"open": "處理中", "answered": "已回覆", "closed": "已結"}  # 待 joy 潤（同玩家看到的三種）
BAD_TOKEN = "客服官的 token 沒設或不對（看 .local/support.json 的 bot_token，跟伺服器的客服官設定）。"  # 待 joy 潤
LOCKED = "鎖定模式：--config、--url、--inbox 不能在命令列上給（只照環境變數）。"  # 待 joy 潤
EMPTY = "EMPTY：stdin 沒有字，沒送。"  # 待 joy 潤
BAD_HUMAN = "--human 只收 Discord 的數字 ID。"  # 待 joy 潤
UNREACHABLE = "連不上伺服器（{url}）。"  # 待 joy 潤
BAD_STATUS = "伺服器回 {code}。"  # 待 joy 潤
GONE = "帳號卡：這個帳號不在了（或換過人）。"  # 待 joy 潤
CARD = "帳號卡：名號 {character}・建帳號 {created}・綁了 {binds}・餘額 {balance}"  # 待 joy 潤
NO_BINDS = "沒有"  # 待 joy 潤
LEDGER = "  帳本 {time} {delta:+d} {reason} {note}"  # 待 joy 潤
SAVED = "截圖 {seq}：{path}"  # 待 joy 潤
DONE = {
    "wait": "回好了：#{id}（等玩家）",  # 待 joy 潤
    "close": "回好了並結單：#{id}",  # 待 joy 潤
    "admin": "記好了：#{id}（請管理者處理）",  # 待 joy 潤
    "closed": "結好了：#{id}",  # 待 joy 潤
}
KINDS = ("png", "jpg", "webp")
SUMMARY = 30


class _Done(Exception):
    def __init__(self, code: int):
        self.code = code


def _when(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return str(ts)


def _say(text: str) -> None:
    print(text, flush=True)


def _locked() -> bool:
    return os.environ.get(LOCK_ENV) == "1"


def _parser(locked: bool) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="support_cli", description="客服官：看清單、看單、回覆、註記、結單。", allow_abbrev=False)  # 待 joy 潤
    if not locked:
        p.add_argument("--config", default=None)
        p.add_argument("--url", default=None)
        p.add_argument("--inbox", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue", allow_abbrev=False)
    one = sub.add_parser("ticket", allow_abbrev=False)
    one.add_argument("n", type=int)
    ans = sub.add_parser("answer", allow_abbrev=False)
    ans.add_argument("n", type=int)
    ans.add_argument("--close", action="store_true")
    ans.add_argument("--human", default=None)
    note = sub.add_parser("note", allow_abbrev=False)
    note.add_argument("n", type=int)
    close = sub.add_parser("close", allow_abbrev=False)
    close.add_argument("n", type=int)
    return p


def _read_config(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class _Desk:
    def __init__(self, session, url: str, token: str):
        self.session, self.url, self.token = session, url.rstrip("/"), token

    def call(self, method: str, path: str, body=None):
        """回 2xx 的回應；其他照結束碼的規矩印一句、丟 _Done。例外的字不印。"""
        try:
            r = self.session.request(method, self.url + path, headers={"Authorization": f"Bearer {self.token}"}, json=body)
        except Exception:  # noqa: BLE001 連不上、逾時：只印網址，不印例外的字
            _say(UNREACHABLE.format(url=self.url))
            raise _Done(2) from None
        code = int(r.status_code)
        if 200 <= code < 300:
            return r
        try:
            data = r.json()
        except ValueError:
            data = {}
        data = data if isinstance(data, dict) else {}
        if code == 400 and isinstance(data.get("error"), str):
            _say(data["error"])
            raise _Done(1)
        if code == 404:
            detail = data.get("detail")
            if isinstance(detail, str) and detail and detail != "Not Found":
                _say(detail)  # 單找不到（「找不到這張單。」）
                raise _Done(1)
            _say(BAD_TOKEN)
            raise _Done(2)
        _say(BAD_STATUS.format(code=code))
        raise _Done(2)


def _label(t: dict) -> str:
    if t.get("admin_flag"):
        return "admin"
    if t.get("human"):
        return "human"
    if t.get("status") == "answered":
        return "answered"
    return "desk"


def _summary(text: str) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= SUMMARY else flat[:SUMMARY] + "…"


def _queue(desk: _Desk) -> int:
    desk.call("POST", "/api/support/sweep", {})
    q = desk.call("GET", "/api/support/queue").json()
    counts = dict.fromkeys(LABELS, 0)
    tickets = q.get("tickets", [])
    if not tickets:
        _say(NO_TICKETS)
    for t in tickets:
        kind = _label(t)
        counts[kind] += 1
        _say(f"#{t['id']} {LABELS[kind]} {t.get('category_name', '')} {t.get('character', '')} {_when(t.get('updated'))} {_summary(t.get('body', ''))}")
    _say(COUNTS.format(**counts))
    return 0


def _who(r: dict) -> str:
    if r.get("internal"):
        return WHO["internal"]
    if r.get("system"):
        return WHO["system"]
    if r.get("auto"):
        return WHO["auto"]
    if r.get("staff"):
        return WHO["staff"]
    return WHO["player"]


def _ticket(desk: _Desk, n: int, inbox: Path) -> int:
    t = desk.call("GET", f"/api/support/ticket/{n}").json()
    account = t.get("account") or {}
    _say(f"#{t['id']}・{t.get('category_name', '')}・{STATUS.get(t.get('status'), t.get('status'))}・{account.get('character', '')}・"
         f"{t.get('version', '')}・{_when(t.get('created'))}")
    if t.get("admin_flag"):
        _say(LABELS["admin"])
    if t.get("human"):
        _say(LABELS["human"])
    _say(str(t.get("body", "")))
    for r in t.get("replies", []):
        _say(f"── {_who(r)}・{_when(r.get('created'))}")
        _say(str(r.get("body", "")))
    card = t.get("card") or {}
    if card.get("gone"):
        _say(GONE)
    else:
        binds = "、".join(str(b.get("name", "")) for b in card.get("binds", [])) or NO_BINDS
        _say(CARD.format(character=card.get("character") or "", created=_when(card.get("created")), binds=binds,
                         balance=card.get("balance", 0)))
        for e in card.get("ledger", []):
            _say(LEDGER.format(time=_when(e.get("time")), delta=int(e.get("delta", 0)), reason=e.get("reason", ""), note=e.get("note") or ""))
    for f in t.get("files", []):
        seq, kind = int(f.get("seq", 0)), str(f.get("kind", ""))
        if kind not in KINDS or seq <= 0:
            continue
        data = desk.call("GET", f"/api/support/file/{n}/{seq}").content
        path = Path(inbox) / str(n) / f"{seq}.{kind}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        _say(SAVED.format(seq=seq, path=path.resolve()))
    return 0


def _stdin_text() -> str:
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    return raw.decode("utf-8", errors="replace").lstrip("\ufeff").strip()


def main(argv=None, session=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    locked = _locked()
    if locked and any(a == flag or a.startswith(flag + "=") for a in argv for flag in PATH_ENVS):
        _say(LOCKED)
        return 2
    try:
        opts = _parser(locked).parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if locked:
        config, url, inbox = (os.environ.get(PATH_ENVS[f]) for f in ("--config", "--url", "--inbox"))
    else:
        config, url, inbox = opts.config, opts.url, opts.inbox
    cfg = _read_config(Path(config) if config else ROOT / ".local" / "support.json")
    url = url or (cfg.get("server_url") if isinstance(cfg.get("server_url"), str) and cfg.get("server_url") else DEFAULT_URL)
    inbox = Path(inbox) if inbox else ROOT / ".local" / "support-inbox"
    token = cfg.get("bot_token")
    if not isinstance(token, str) or not token.strip():
        _say(BAD_TOKEN)
        return 2
    if opts.cmd == "answer" and opts.human is not None and not (opts.human.isascii() and opts.human.isdigit()):
        _say(BAD_HUMAN)
        return 2
    body = None
    if opts.cmd in ("answer", "note"):
        body = _stdin_text()
        if not body:
            _say(EMPTY)
            return 1
    desk = _Desk(session if session is not None else requests.Session(), url, token.strip())
    try:
        if opts.cmd == "queue":
            return _queue(desk)
        if opts.cmd == "ticket":
            return _ticket(desk, opts.n, inbox)
        if opts.cmd == "close":
            desk.call("POST", "/api/support/close", {"id": opts.n})
            _say(DONE["closed"].format(id=opts.n))
            return 0
        then = "admin" if opts.cmd == "note" else ("close" if opts.close else "wait")
        payload = {"id": opts.n, "body": body, "then": then}
        if opts.cmd == "answer" and opts.human:
            payload["relay_from"] = opts.human
        desk.call("POST", "/api/support/answer", payload)
        _say(DONE[then].format(id=opts.n))
        return 0
    except _Done as e:
        return e.code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
