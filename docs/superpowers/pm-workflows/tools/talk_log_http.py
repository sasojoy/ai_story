"""往來紀錄的前後比對（主幹合回 develop 第 2 段 D，計畫 docs/superpowers/plans/2026-11-06-develop合回-D.md 第六節）：same_behavior 只清小檔不比，這支補那一塊。
真的開 uvicorn、真的走 HTTP（requests）：同一串步驟打 /api/talk_log 的每一種問法，每一下的回應原文（狀態碼、Content-Type、內文）與最後的 <db>-talk.sqlite、
<db>-talk-archive.sqlite 整份寫進輸出；base 跑一次、head 跑一次（同一個埠，一次開一台），兩份輸出逐位元組比。時鐘、亂數、假模型照 same_behavior（不連 11434）。

    PYTHONHASHSEED=0 python talk_log_http.py run <根> <設定> <輸出> --port <埠> --tmp <暫存>
    python talk_log_http.py compare <輸出甲> <輸出乙>

假人碰不到往來紀錄（server._log_talk 開頭就擋）。走不到的：封存檔裡的舊紀錄（路由只問這一季與上一季，上一季不會被封存；讀封存的那一支在包的單元測試）。"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time as real_time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
import same_behavior as sb  # noqa: E402

PORT = [0]


class RealClient:
    """TestClient 用到的那幾個方法，換成真的走 socket（cookie 在 Session 裡）。"""

    def __init__(self, _app) -> None:
        import requests

        self.session = requests.Session()
        self.base = f"http://127.0.0.1:{PORT[0]}"

    def post(self, url: str, json=None):
        return self.session.post(self.base + url, json=json, timeout=120)

    def get(self, url: str):
        return self.session.get(self.base + url, timeout=120)


class TalkLogHttp(sb.SocializeScenario):
    A, B = "鍾離月", "晏鳴秋"
    PLAYERS = {A: "guan", B: "guan"}
    PHASES_FIRST = ["setup", "seat", "empty", "first_talk", "pages", "other", "season_two", "season_three"]
    PHASES_SECOND: list[str] = []

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.TestClient = RealClient
        import uvicorn

        config = uvicorn.Config(self.server.app, host="127.0.0.1", port=PORT[0], lifespan="off", log_level="warning")
        self.uvicorn = uvicorn.Server(config)
        threading.Thread(target=self.uvicorn.run, daemon=True).start()
        for _ in range(200):
            if self.uvicorn.started:
                break
            real_time.sleep(0.05)
        else:
            raise SystemExit("伺服器起不來")

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))
        sb.CompanionsScenario.seat(self)

    def log(self, who: str | None, query: str, tag: str) -> str:
        """問一次 /api/talk_log，回應原文照寫（who 是 None：沒登入的 Session）。回內文。"""
        self.begin()
        client = self.clients[who] if who is not None else RealClient(None)
        r = client.get("/api/talk_log" + query)
        sb.emit(f"{who} 往來紀錄 {tag} {query} {r.status_code} {r.headers.get('content-type')}", r.text)
        return r.text

    def talk(self, who: str, cid: str, loc: str, rounds: int) -> None:
        """站到他那裡、開口、再談 rounds 輪、告辭。假模型回話。"""
        self.place(who, loc)
        self.fame(who, 9999)
        sb.MODEL["talk"] = {"stance": "suzhan"}
        self.reach(who, cid)
        for _ in range(rounds):
            if not self.chars.load(who).player.pending_companion:
                break
            self.choose(who, "talk:0")
        self.leave(who)
        sb.MODEL["talk"] = None

    def empty(self) -> None:
        """還沒談過：這一季、上一季、不認得的人、太長的 id、before 不是數字、沒登入。"""
        _, cid = self.alone_spot()
        cid = cid or "nobody"
        self.log(self.A, f"?id={cid}", "還沒談過")
        self.log(self.A, f"?id={cid}&season=prev", "上一季")
        self.log(self.A, "?id=nobody", "不認得的人")
        self.log(self.A, "", "沒給 id")
        self.log(self.A, "?id=" + "x" * 60, "太長的 id")
        self.log(self.A, f"?id={cid}&before=abc", "before 不是數字")
        self.log(None, f"?id={cid}", "沒登入")

    def first_talk(self) -> None:
        loc, cid = self.alone_spot()
        if cid is None:
            sb.emit("這份內容沒有只有一位大勢人物的地點", None)
            return
        self.talk(self.A, cid, loc, 2)
        self.log(self.A, f"?id={cid}", "談了三輪")
        self.log(self.A, f"?id={cid}&season=now", "這一季")

    def pages(self) -> None:
        """談超過一頁（一頁 30 句、一輪兩句）：第一頁、照最舊那一句的 id 翻第二頁、翻過頭。"""
        loc, cid = self.alone_spot()
        if cid is None:
            return
        with self.tuned(self.c.config, talk_turns_per_day=40):
            self.talk(self.A, cid, loc, 18)
        text = self.log(self.A, f"?id={cid}", "第一頁")
        import json

        lines = json.loads(text).get("lines") or []
        oldest = lines[-1]["id"] if lines else 0
        text = self.log(self.A, f"?id={cid}&before={oldest}", "第二頁")
        lines = json.loads(text).get("lines") or []
        self.log(self.A, f"?id={cid}&before={lines[-1]['id'] if lines else 1}", "翻過頭")

    def other(self) -> None:
        """別人看不到；第二位人物各算各的（情誼、見過幾次）。"""
        loc, cid = self.alone_spot()
        if cid is None:
            return
        self.log(self.B, f"?id={cid}", "別人的看不到")
        hall, figs = self.hall_spot()
        if hall is not None:
            self.place(self.A, hall)
            self.fame(self.A, 9999)
            self.open_list(self.A)
            sb.MODEL["talk"] = {"stance": "chizhong"}
            self.press(self.A, f"call:{figs[0]}")
            self.leave(self.A)
            sb.MODEL["talk"] = None
            self.log(self.A, f"?id={figs[0]}", "第二位人物")
        self.talk(self.B, cid, loc, 0)
        self.log(self.B, f"?id={cid}", "乙談了一輪")

    def turn(self) -> None:
        self.do(sb.ADMIN, "end_season")
        self.do(sb.ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)

    def season_two(self) -> None:
        loc, cid = self.alone_spot()
        self.turn()
        if cid is None:
            return
        self.log(self.A, f"?id={cid}", "第二季・這一季空的")
        self.log(self.A, f"?id={cid}&season=prev", "第二季・上一季")
        loc, cid = self.alone_spot()
        self.talk(self.A, cid, loc, 1)
        self.log(self.A, f"?id={cid}", "第二季・談了")

    def season_three(self) -> None:
        """第三季第一句：第一季整批搬去封存檔（小檔照整份比）。"""
        self.turn()
        loc, cid = self.alone_spot()
        if cid is None:
            return
        self.talk(self.A, cid, loc, 0)
        self.log(self.A, f"?id={cid}", "第三季・這一季")
        self.log(self.A, f"?id={cid}&season=prev", "第三季・上一季")

    def run(self, part: str, out: Path) -> None:
        sb.emit(f"設定 {self.profile}", None)
        for name in self.PHASES_FIRST:
            getattr(self, name)()
        for side in ("talk", "talk-archive"):
            path = self.db.with_name(f"{self.db.stem}-{side}.sqlite")
            sb.BUF.write(f"## 小檔 {side}\n" + (sb.db_text(path) if path.exists() else "（沒有）\n"))
        out.write_text(sb.BUF.getvalue(), encoding="utf-8", newline="\n")
        print(self.profile, sb.STEP[0], "步", len(sb.BUF.getvalue()), "字")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("root")
    r.add_argument("profile", choices=sb.PROFILES)
    r.add_argument("out")
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--tmp", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args()
    if a.cmd == "compare":
        sys.stdout.reconfigure(encoding="utf-8")
        x, y = Path(a.a).read_bytes(), Path(a.b).read_bytes()
        print("一樣" if x == y else "不一樣：" + sb._first_diff(x, y), len(x), "位元組")
        return 0 if x == y else 1
    PORT[0] = a.port
    tmp = Path(a.tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    db = tmp / f"talk_{a.profile}.db"
    sb._wipe_db(db)
    os.environ["TIANXIA_DB"] = str(db)
    sb._setup_child(Path(a.root).resolve(), a.profile, db)
    TalkLogHttp(Path(a.root).resolve(), a.profile, db).run("all", Path(a.out))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
