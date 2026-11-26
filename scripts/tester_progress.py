"""主機端：測試玩家的進度（極限假人的基準；企劃者 2026-11-12「拿我們測試玩家的進度做到對比 例如2天就能滿等 跑贏所有測試玩家」）。只讀不改。

讀線上那份資料庫（唯讀 mode=ro，不走 open_database：那一條會照版本跑遷移），只看真人（characters.is_bot = 0；管理者的名號另外扣掉），
寫一份 json：
- 這一季（還在跑的季）：每個人此刻的身家（scripts/limit_metrics.snapshot，極限假人同一支）＋行狀裡「到了第 N 級」是季的第幾天；
- 以前的季（biographies）：季末的等級、貢獻、名望＋同樣的等級里程碑。
**不寫名號**：每個人只是一個流水號（同 play_metrics：表上只有真人，列出名號等於從缺席看出誰是假人）。

執行（主機）：.venv/Scripts/python.exe scripts/tester_progress.py --out .local/tester_progress.json
（沒給 --db 照 TIANXIA_DB 或 saves/tianxia.db）。把產出的 json 交給 scripts/limit_report.py --testers。
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from limit_metrics import level_milestones, snapshot  # noqa: E402
from tianxia.content import load_content, serving_profile  # noqa: E402
from tianxia.database import default_path  # noqa: E402
from tianxia.state import AnnalEntry, GameState  # noqa: E402

DAY = 86400.0


def _milestones_days(pairs) -> list[list[float]]:
    return [[round(t / DAY, 2), level] for t, level in pairs]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--out", default=str(ROOT / ".local" / "tester_progress.json"))
    args = parser.parse_args()
    path = Path(args.db) if args.db else default_path()
    content = load_content(ROOT / "content", profile=serving_profile())
    admins = {a.casefold() for a in content.config.admins}
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    season_row = conn.execute("SELECT data FROM world WHERE id = 1").fetchone() if _has(conn, "world") else None
    season = json.loads(season_row["data"]) if season_row else {}
    latest = conn.execute("SELECT data FROM seasons ORDER BY number DESC LIMIT 1").fetchone() if _has(conn, "seasons") else None
    season_time = float(json.loads(latest["data"]).get("time", 0.0)) if latest else 0.0
    humans = [r for r in conn.execute("SELECT key, name, data FROM characters WHERE is_bot = 0") if r["name"].casefold() not in admins]
    human_keys = {r["key"] for r in humans}
    current, unreadable, stale = [], 0, 0
    for r in humans:
        try:
            state = GameState.model_validate_json(r["data"])
        except Exception:
            unreadable += 1
            continue
        if state.player.member.level <= 1 and not state.player.annals:
            continue  # 註冊了沒玩的不算
        if state.player.season_number != season.get("season_number"):
            stale += 1
            continue  # 這一季還沒上線過：存檔還是上一季季末的樣子（登入才換季），那一份已經在列傳裡
        current.append({"now": snapshot(state, content), "levels": _milestones_days(level_milestones(state)), "key": r["key"],
                        "season_day": round(season_time / DAY, 2), "season": state.player.season_number})
    # 每天按了哪幾顆（playlog 的 action_counts；第 7 版起才有）：照等級排的流水號，不帶名號
    current.sort(key=lambda row: -row["now"]["level"])
    if _has(conn, "action_counts"):
        for row in current:
            days = {}
            for a in conn.execute("SELECT day, buttons FROM action_counts WHERE owner = ? AND season = ? ORDER BY day",
                                  (row["key"], season.get("season_number"))):
                days[int(a["day"])] = json.loads(a["buttons"] or "{}")
            row["buttons"] = days
    for row in current:
        row.pop("key", None)
    past: dict[int, list] = {}
    if _has(conn, "biographies"):
        for r in conn.execute("SELECT season, key, annals, profile FROM biographies"):
            if r["key"] not in human_keys:
                continue
            profile = json.loads(r["profile"] or "{}")
            try:
                entries = [AnnalEntry.model_validate(e) for e in json.loads(r["annals"] or "[]")]
            except Exception:
                entries = []
            levels = sorted((e.time, int(e.text.removeprefix("武藝精進，到了第 ").split(" ")[0])) for e in entries
                            if e.text.startswith("武藝精進，到了第 "))
            past.setdefault(int(r["season"]), []).append({
                "level": profile.get("level"), "contrib": profile.get("contrib"), "fame": profile.get("fame"),
                "levels": _milestones_days(levels),
            })
    out = {"db": path.name, "profile": serving_profile(), "season_now": season.get("season_number"),
           "current": current, "unreadable": unreadable, "stale": stale, "past": {str(k): v for k, v in sorted(past.items())}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary(out), ensure_ascii=False, separators=(",", ":")))
    print(f"這一季 {len(current)} 人、以前 {sum(len(v) for v in past.values())} 筆列傳（{len(past)} 季）、讀不懂 {unreadable}、這一季還沒上線 {stale}；寫到 {args.out}")
    return 0


MILESTONES = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)


def _level_days(rows) -> dict:
    """每個里程碑：幾個人到了、最快第幾天、中位數第幾天。"""
    out = {}
    for level in MILESTONES:
        days = sorted(d for r in rows for d, lv in r["levels"] if lv == level)
        if days:
            out[level] = {"n": len(days), "fastest": days[0], "median": days[len(days) // 2]}
    return out


def summary(out: dict) -> dict:
    """給人看、也給 limit_report 用的小摘要：每一季的等級里程碑（最快、中位數）、季末等級最高與中位數；這一季每一欄的最高與中位數。"""
    cur = out["current"]
    fields = sorted(cur[0]["now"]) if cur else []
    now = {k: {"max": max(r["now"][k] for r in cur), "median": sorted(r["now"][k] for r in cur)[len(cur) // 2]} for k in fields}
    past = {}
    for season, rows in out["past"].items():
        levels = sorted(r["level"] or 0 for r in rows)
        past[season] = {"n": len(rows), "level_max": levels[-1] if levels else 0, "level_median": levels[len(levels) // 2] if levels else 0,
                        "milestones": _level_days(rows)}
    top = []
    for row in cur[:5]:  # 等級最高的五個人：每天按最多的十二顆、季到此刻的身家（不帶名號）
        days = {d: dict(sorted(b.items(), key=lambda kv: -kv[1])[:12]) for d, b in (row.get("buttons") or {}).items()}
        top.append({"now": row["now"], "levels": row["levels"], "buttons": days})
    return {"season_now": out["season_now"], "stale": out.get("stale"), "top": top, "day_now": cur[0]["season_day"] if cur else None, "n_now": len(cur),
            "now": now, "milestones_now": _level_days(cur), "past": past}


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


if __name__ == "__main__":
    raise SystemExit(main())
