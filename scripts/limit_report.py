"""極限假人的報告：把 scripts/limit_bots.py 的結果（一個 json 一場）合成一頁 HTML，跟同場的普通假人、對照組、測試玩家（scripts/tester_progress.py
的摘要）並排，自動標三種：還在漲（最後四分之一季還漲一成以上、又沒到上限）、太快封頂（7 天季第 3 天、21 天季第 7 天以前就滿級）、
輾壓（比對照組強 1.5 倍以上，或贏過所有測試玩家）。判準是設計稿第三題的建議（Joy 11/12「有問題是我們自己定義，可以拿測試玩家的進度做對比」）。

執行：python scripts/limit_report.py --runs <limit_bots 的 --out> [--testers tester_summary.json] --html out.html [--json out.json]
"""
from __future__ import annotations

import argparse
import html
import io
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from limit_metrics import FIELDS  # noqa: E402

MAX_LEVEL = 50
FAST_DAY = {"week7": 3, "season21": 7}
DOMINANT = 1.5
STILL_RISING = 0.10
# 每一種極限假人看哪幾欄（第一欄是主要那一欄，畫曲線）
WATCH = {
    "control": ("level", "xinde", "silver", "contrib"),
    "level": ("level", "exp", "xinde"),
    "insight": ("insights", "god_insights", "mastered", "arts"),
    "friend": ("affinity_max", "friends_80", "treasure", "named_gear"),
    "silver": ("silver", "weapon_tier", "weapon_tempers", "armor_tier", "named_gear"),
    "raid": ("silver", "level", "fame"),
    "merit": ("contrib", "rank", "fame"),
    "guard": ("guard_qing", "guard_tags", "level"),
    "thrift": ("level", "xinde", "silver", "contrib"),
    "strongest": ("level", "insights", "mastered", "weapon_tier", "guard_tags"),
    "grinder": ("level", "xinde", "silver", "contrib"),
    "overlord": ("contrib", "affinity_max", "silver", "fame"),
}
CAPS = {"level": MAX_LEVEL}


def load_runs(folder: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _curve(runs: list[dict], key: str, who: str = "me", agg: str = "max") -> list[float]:
    """幾個種子平均的每日曲線：who＝me 是極限假人，bots 是同場普通假人（agg 取最高或中位數）。"""
    days = max((len(r["curve"]) for r in runs), default=0)
    out = []
    for d in range(days):
        vals = []
        for r in runs:
            if d < len(r["curve"]):
                row = r["curve"][d][who]
                vals.append(row.get(key) if who == "me" else (row.get(key) or {}).get(agg))
        out.append(_mean(vals) or 0.0)
    return out


def flags(profile: str, focus: str, runs: list[dict], control: list[dict], testers: dict | None) -> list[tuple[str, str]]:
    out = []
    keys = WATCH.get(focus, ("level",))
    for key in keys:
        curve = _curve(runs, key)
        if len(curve) >= 4 and curve[-1] > 0:
            q = curve[-1 - max(1, len(curve) // 4)]
            cap = CAPS.get(key)
            if (curve[-1] - q) / curve[-1] > STILL_RISING and (cap is None or curve[-1] < cap):
                out.append(("還在漲", f"{FIELDS[key]}最後四分之一季還漲了 {round((curve[-1] - q) / curve[-1] * 100)}%（{q:g} → {curve[-1]:g}）"))
        if key == "level" and testers:
            for level, row in sorted(((int(k), v) for k, v in (testers.get("milestones_now") or {}).items()), reverse=True):
                day = next((i + 1 for i, v in enumerate(curve) if v >= level), None)  # 曲線是每天結束時量的：第 d 天＝d 天以內
                if day is not None and day < row["fastest"]:
                    out.append(("贏過所有測試玩家", f"第 {day} 天就到 {level} 級，測試玩家最快 {row['fastest']:g} 天"))
                    break
        if key == "level":
            hit = next((i + 1 for i, v in enumerate(curve) if v >= MAX_LEVEL), None)
            if hit is not None and hit <= FAST_DAY.get(profile, 3):
                out.append(("太快封頂", f"第 {hit} 天就滿 {MAX_LEVEL} 級"))
        mine = _mean([r["final"].get(key) for r in runs])
        base = _mean([r["final"].get(key) for r in control]) if control and focus != "control" else None
        if base and mine and mine >= DOMINANT * base and mine - base >= 3:
            out.append(("輾壓", f"{FIELDS[key]} {mine:g}，對照組 {base:g}（{mine / base:.1f} 倍）"))
        top = (testers or {}).get("now", {}).get(key, {}).get("max")
        day = int((testers or {}).get("day_now") or 0)  # 測試玩家的數字是這一季第幾天量的：極限假人也拿同一天比，不拿季末比
        then = curve[day - 1] if 0 < day <= len(curve) else mine
        if top is not None and then is not None and then > top and key in keys[:2]:
            out.append(("贏過所有測試玩家", f"第 {day} 天{FIELDS[key]} {then:g}，測試玩家最高 {top:g}"))
    vb = _mean([r.get("vs_benming") for r in runs])
    if vb is not None and vb > 0.50:
        out.append(("贏過本命", f"季末擂台對同等級的本命贏 {round(vb * 100)}%（目標是本命贏 50～52%，也就是這一邊 48～50%）"))
    return out  # 擂台對同場普通假人只印數字、不標：伺服器假人每天才上線一到五小時，誰都贏得了它們（本命 50～52% 要另外量）


def _spark(series: list[tuple[str, list[float], str]], cap: float | None = None) -> str:
    """幾條每日曲線畫在同一張小圖（SVG，顏色用頁面的變數）。"""
    w, h, pad = 300, 90, 6
    top = max([max(s, default=0) for _, s, _ in series] + [cap or 0, 1])
    days = max(len(s) for _, s, _ in series) or 1
    def pts(s):
        return " ".join(f"{pad + i * (w - 2 * pad) / max(1, days - 1):.1f},{h - pad - v / top * (h - 2 * pad):.1f}" for i, v in enumerate(s))
    lines = "".join(f'<polyline fill="none" stroke="var({var})" stroke-width="{2 if i == 0 else 1.5}" points="{pts(s)}"/>'
                    for i, (_, s, var) in enumerate(series) if s)
    end = series[0][1]
    dot = f'<circle cx="{pad + (len(end) - 1) * (w - 2 * pad) / max(1, days - 1):.1f}" cy="{h - pad - end[-1] / top * (h - 2 * pad):.1f}" r="3" fill="var(--seal)"/>' if end else ""
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="每日曲線"><line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="var(--line)"/>'
            f'{lines}{dot}<text x="{w - pad}" y="12" text-anchor="end" fill="var(--ink2)" font-size="10">{top:g}</text></svg>')


def build(runs: list[dict], testers: dict | None) -> tuple[str, dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in runs:
        if "crash" not in r:
            groups[(r["profile"], r["focus"])].append(r)
    profiles = sorted({p for p, _ in groups})
    data, cards = {}, []
    for profile in profiles:
        control = groups.get((profile, "control"), [])
        cards.append(f'<h2>{"7 天季" if profile == "week7" else "21 天季" if profile == "season21" else html.escape(profile)}</h2><div class="grid">')
        for focus in WATCH:
            rs = groups.get((profile, focus))
            if not rs:
                continue
            keys = WATCH[focus]
            fl = flags(profile, focus, rs, control, testers if profile == (testers or {}).get("profile", "week7") else None)
            arena = _mean([r["arena_vs_bots"]["mean"] for r in rs])
            main = keys[0]
            spark = _spark([("我", _curve(rs, main), "--seal"), ("普通假人最高", _curve(rs, main, "bots"), "--ink2"),
                            ("對照組", _curve(control, main) if focus != "control" else [], "--jade")], CAPS.get(main))
            rows = "".join(
                f"<tr><td>{FIELDS[k]}</td><td class='n'>{_mean([r['final'][k] for r in rs]):g}</td>"
                f"<td class='n'>{_fmt(_mean([r['bots_final'].get(k, {}).get('max') for r in rs]))}</td>"
                f"<td class='n'>{_fmt(_mean([c['final'][k] for c in control]) if control else None)}</td>"
                f"<td class='n'>{_fmt((testers or {}).get('now', {}).get(k, {}).get('max'))}</td></tr>" for k in keys)
            extra = ""
            raids = [r.get("raids", {}) for r in rs]
            if any(raids):
                extra = f"<p class='note'>截殺：打 {_mean([x.get('打', 0) for x in raids]):g} 場、搶到銀兩 {_mean([x.get('搶到銀兩', 0) for x in raids]):g}、被截 {_mean([x.get('被打', 0) for x in raids]):g} 次</p>"
            tags = "".join(f'<li><span class="tag">{html.escape(a)}</span> {html.escape(b)}</li>' for a, b in fl) or '<li class="ok">沒有標紅</li>'
            label = rs[0]["label"]
            cards.append(
                f'<article class="card"><header><h3>{html.escape(label)}</h3><span>{len(rs)} 個種子・每天 {rs[0]["hours"]:g} 小時</span></header>'
                f'<div class="spark">{spark}<p class="legend"><i class="k1"></i>{FIELDS[main]}・極限假人 <i class="k2"></i>普通假人最高 <i class="k3"></i>對照組</p></div>'
                f'<div class="tbl"><table><tr><th>季末</th><th>它</th><th>普通最高</th><th>對照組</th><th>測試玩家最高</th></tr>{rows}</table></div>'
                f'{extra}<p class="note">季末擂台：對同等級本命 {_fmt_pct(_mean([r.get("vs_benming") for r in rs]))}・對同場普通假人 {_fmt_pct(arena)}</p><ul class="flags">{tags}</ul></article>')
            data[f"{profile}/{focus}"] = {"flags": fl, "arena": arena, "vs_benming": _mean([r.get("vs_benming") for r in rs]), "final": {k: _mean([r["final"][k] for r in rs]) for k in keys}}
        cards.append("</div>")
    return PAGE.replace("{{CARDS}}", "".join(cards)).replace("{{TESTERS}}", _tester_line(testers)), data


def _fmt(v) -> str:
    return "—" if v is None else f"{v:g}"


def _fmt_pct(v) -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def _tester_line(t: dict | None) -> str:
    if not t:
        return "這一版還沒有測試玩家的數字（主機抽完再補）。"
    return f"測試玩家：第 {t.get('season_now')} 季第 {t.get('day_now')} 天，{t.get('n_now')} 人；「測試玩家最高」是此刻的最高，不是季末。"


PAGE = """<title>極限假人報告</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=LXGW+WenKai+TC:wght@400;700&family=Noto+Sans+TC:wght@400;500&display=swap">
<style>
:root{--paper:#f5f2ea;--card:#fbf9f4;--ink:#22201c;--ink2:#6b655b;--line:#d9d2c3;--seal:#a8322a;--jade:#3f6b5c;--wash:#ece6d8;
--display:"LXGW WenKai TC","Kaiti TC","KaiTi",serif;--body:"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#1a1916;--card:#23211d;--ink:#ebe6db;--ink2:#a9a294;--line:#3a362f;--seal:#e0685d;--jade:#7fb5a2;--wash:#2b2823;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#1a1916;--card:#23211d;--ink:#ebe6db;--ink2:#a9a294;--line:#3a362f;--seal:#e0685d;--jade:#7fb5a2;--wash:#2b2823;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.6}
.wrap{max-width:1000px;margin:0 auto;padding-block:24px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:18px}
h1,h2,h3{font-family:var(--display);margin:0;text-wrap:balance}h1{font-size:28px}h2{font-size:22px;margin-top:12px}h3{font-size:18px}
.lead,.note{color:var(--ink2)}.note{font-size:13px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:14px;display:flex;flex-direction:column;gap:8px;min-width:0}
.card header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px}.card header span{font-size:12px;color:var(--ink2)}
svg{width:100%;height:auto;display:block}
.legend{font-size:12px;color:var(--ink2);margin:2px 0 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.legend i{display:inline-block;width:14px;height:2px}.k1{background:var(--seal)}.k2{background:var(--ink2)}.k3{background:var(--jade)}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--ink2);font-weight:500;background:var(--wash)}td.n{text-align:right;font-variant-numeric:tabular-nums}
.flags{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px;font-size:13px}
.tag{display:inline-block;font-size:12px;padding:0 6px;border:1px solid var(--seal);color:var(--seal);border-radius:3px}.ok{color:var(--jade)}
</style>
<div class="wrap">
<h1>極限假人報告</h1>
<p class="lead">每張卡是一種只追一件事的假人，玩完整季。紅線是它，灰線是同場普通假人裡最高的，綠線是同樣在線時數、普通玩法的對照組。</p>
<p class="note">{{TESTERS}}</p>
<p class="note">這一版還沒量準的：財神（鐵匠鋪裡一直衝淬煉，人卡在城裡、等級起不來）、親衛狂（情分、性向幾乎沒長，跑法沒按到教他的那幾顆）、
截殺狂（野地很少碰到人，一季只截到幾場）。這三張卡的數字先別當天花板。擂台對同場普通假人的贏面只當參考：普通假人每天只上線一到五小時。</p>
{{CARDS}}
<p class="note">判準：最後四分之一季還漲一成以上算還在漲；7 天季第 3 天、21 天季第 7 天以前滿級算太快封頂；比對照組多 1.5 倍以上、或贏過所有測試玩家算輾壓。
跟人物說話用固定分（寬鬆）頂替模型；放手一搏、隨口應對沒算。只走玩家按得到的鈕，不改規則。</p>
</div>
"""


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--testers", default=None, help="tester_progress.py 印的那一行摘要存成的 json")
    parser.add_argument("--html", required=True)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    runs = [r for folder in args.runs for r in load_runs(Path(folder))]
    testers = json.loads(Path(args.testers).read_text(encoding="utf-8")) if args.testers else None
    page, data = build(runs, testers)
    Path(args.html).write_text(page, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for key, d in data.items():
        print(key, d["flags"], d["arena"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
