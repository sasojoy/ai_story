"""檢查 content/events_outcomes.json（分岔事件初版，減法季整合設計 5.1、5.9）。

引擎還沒讀這個檔（批 4 才接），所以 content.validate 管不到它；這一支替它把關：
每則的 id 在 content/events/*.json 找得到、2～4 種後果、最後一種是對不上的 fallback、
判法三選一（check／combat／cost）、難度在這則固定選項的帶子裡、combat 是這則已有的隊伍、
stats 只有允許的鍵（博聞一律不給）、marks 的地點是這則的第一個地點、痕跡名 2～4 個中文字且同一則不重複、
貢獻 1～4、文字沒有簡體、沒有「假人」那幾個詞、敘事裡不寫阿拉伯數字。
作惡的後果（企劃者 2026-10-24 第 8 件 a：effect 的 good 為負）：原事件有作惡固定選項（stats.evil 為正）才准有、一則最多一種、
不算在 2～4 種裡、不是最後一種；不記貢獻；給的不准比原事件的作惡選項多（俠寇選項也算）。
其他後果給的不准比這則「有檢定或打仗的開放選項」多（俠寇選項不算）。
用法：python scripts/check_outcomes.py [檔案路徑]
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED_STATS = {"silver", "fame", "good", "xinde", "str", "agi", "con", "wis"}
CHECK_STATS = {"str", "agi", "con", "wis"}
FORBIDDEN_WORDS = ("假人", "機器人", "bot")
CJK = re.compile(r"^[一-鿿]{2,4}$")
DIGITS = re.compile(r"[0-9０-９]")


def _events_by_id() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((ROOT / "content" / "events").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data if isinstance(data, list) else data.get("events", data):
            out[event["id"]] = event
    return out


def _locations() -> dict[str, dict]:
    data = json.loads((ROOT / "content" / "locations.json").read_text(encoding="utf-8"))
    return {loc["id"]: loc for loc in (data if isinstance(data, list) else data.get("locations", data))}


def _inside(x: float, y: float, pts: list) -> bool:
    n = len(pts)
    j = n - 1
    hit = False
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            hit = not hit
        j = i
    return hit


def _region_of(loc: dict) -> str | None:
    data = json.loads((ROOT / "content" / "map.json").read_text(encoding="utf-8"))
    for region in data.get("regions", []):
        pts = [(p[0], p[1]) if isinstance(p, (list, tuple)) else (p["x"], p["y"]) for p in region["points"]]
        if _inside(loc["x"], loc["y"], pts):
            return region["id"]
    return None


def _is_evil(outcome: dict) -> bool:
    """作惡的後果（企劃者 2026-10-24 第 8 件 a）：effect 的 good 為負。"""
    return (outcome.get("effect") or {}).get("stats", {}).get("good", 0) < 0


def _simplified(text: str) -> bool:
    try:
        from tianxia import zh
    except Exception:  # noqa: BLE001 — 退而求其次用一份常見簡體字表
        common = "这说话军发国会对时们么没见间开关门问长东车马书学语产业内历后头里气动电队战过还进运远"
        return any(ch in text for ch in common)
    same = str.maketrans("臺", "台")  # 原事件也寫「灶台」：台、臺兩種寫法都是正字，不算簡體（退回手寫表時會把台換成臺）
    return zh.to_traditional(text).translate(same) != text.translate(same)


def main(path: Path) -> int:
    problems: list[str] = []
    warnings: list[str] = []
    doc = json.loads(path.read_text(encoding="utf-8"))
    events = _events_by_id()
    locations = _locations()
    by_region: dict[str, int] = {}
    seen: set[str] = set()

    def text_ok(where: str, text: str, *, narrative: bool = True) -> None:
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}：沒有文字")
            return
        if _simplified(text):
            problems.append(f"{where}：有簡體字：{text}")
        for word in FORBIDDEN_WORDS:
            if word in text:
                problems.append(f"{where}：寫了「{word}」")
        if narrative and DIGITS.search(text):
            problems.append(f"{where}：敘事裡寫了數字：{text}")
        if narrative and not 20 <= len(text) <= 90:
            warnings.append(f"{where}：長度 {len(text)} 字（成了那一段建議 40～80；失手與 fallback 照原事件可以短）")

    for entry in doc.get("events", []):
        eid = entry.get("id")
        where = f"[{eid}]"
        if eid in seen:
            problems.append(f"{where}：重複")
        seen.add(eid)
        event = events.get(eid)
        if event is None:
            problems.append(f"{where}：content/events 裡沒有這則事件")
            continue
        if entry.get("title") != event["title"]:
            problems.append(f"{where}：標題不符（{entry.get('title')} / {event['title']}）")
        if not event.get("free_text") and not entry.get("needs_free_text"):
            problems.append(f"{where}：這則事件沒有隨口應對，又沒標 needs_free_text")
        locs = event.get("locations") or []
        if not locs:
            problems.append(f"{where}：事件沒有地點")
            continue
        first = locs[0]
        if entry.get("location") != first:
            problems.append(f"{where}：location 要是這則事件的第一個地點 {first}")
        if first not in locations:
            problems.append(f"{where}：地點 {first} 不在 locations.json")
        else:
            region = _region_of(locations[first])
            if entry.get("region") != region:
                problems.append(f"{where}：region 寫 {entry.get('region')}，地點 {first} 算在 {region}")
        by_region[entry.get("region", "?")] = by_region.get(entry.get("region", "?"), 0) + 1
        diffs = [c["check"]["difficulty"] for c in event.get("choices", []) if c.get("check")]
        band = (min(diffs), max(diffs)) if diffs else (3, 8)
        squads = {c["combat"] for c in event.get("choices", []) if c.get("combat")}
        outcomes = entry.get("outcomes") or []
        evil_ones = [o for o in outcomes if _is_evil(o)]
        if not 2 <= len(outcomes) - len(evil_ones) <= 4:
            problems.append(f"{where}：後果要 2～4 種（作惡那一種另算），有 {len(outcomes) - len(evil_ones)}")
        if len(evil_ones) > 1:
            problems.append(f"{where}：作惡的後果最多一種，有 {len(evil_ones)}")
        evil_choices = [c for c in event.get("choices", []) if c.get("effect", {}).get("stats", {}).get("evil", 0) > 0]
        if evil_ones and not evil_choices:
            problems.append(f"{where}：原事件沒有作惡的固定選項，不能有作惡的後果")
        open_choices = [c for c in event.get("choices", []) if not c.get("needs")]
        graded = [c for c in open_choices if c.get("check") or c.get("combat")] or open_choices
        marks_seen: set[str] = set()
        ids_seen: set[str] = set()
        for i, o in enumerate(outcomes):
            ow = f"{where} 後果 {o.get('id')}"
            if o.get("id") in ids_seen:
                problems.append(f"{ow}：id 重複")
            ids_seen.add(o.get("id"))
            text_ok(f"{ow} 的 tag", o.get("tag", ""), narrative=False)
            if "：" not in o.get("tag", ""):
                problems.append(f"{ow}：tag 要寫成「類名：怎麼做」")
            eff = o.get("effect") or {}
            last = i == len(outcomes) - 1
            text_ok(f"{ow} 的 effect", eff.get("text", ""), narrative=not last)
            if last:
                text_ok(f"{ow} 的 effect", eff.get("text", ""), narrative=False)
            kinds = [k for k in ("check", "combat", "cost") if k in o]
            if last:
                if kinds or any(k in eff for k in ("stats", "marks", "contribution")) or "fail_effect" in o:
                    problems.append(f"{ow}：最後一種要是對不上的 fallback（沒有判法、stats、marks、contribution、fail_effect）")
                continue
            if len(kinds) != 1:
                problems.append(f"{ow}：判法要 check／combat／cost 三選一，有 {kinds}")
            if "check" in o:
                ck = o["check"]
                stat = ck.get("stat")
                if stat == "best_of":
                    if not ck.get("stats") or not set(ck["stats"]) <= CHECK_STATS:
                        problems.append(f"{ow}：best_of 的 stats 不對：{ck.get('stats')}")
                elif stat not in CHECK_STATS:
                    problems.append(f"{ow}：check 的 stat 不對：{stat}")
                d = ck.get("difficulty")
                if not isinstance(d, int) or not 3 <= d <= 8:
                    problems.append(f"{ow}：難度 {d} 不在 3～8")
                elif not band[0] <= d <= band[1]:
                    problems.append(f"{ow}：難度 {d} 超出這則固定選項的帶子 {band}")
            if "combat" in o and o["combat"] not in squads:
                problems.append(f"{ow}：combat {o['combat']} 不是這則事件已有的隊伍 {sorted(squads)}")
            if "cost" in o:
                cost = o["cost"]
                if set(cost) != {"silver"} or not isinstance(cost["silver"], int) or cost["silver"] <= 0:
                    problems.append(f"{ow}：cost 只能是正的 silver：{cost}")
            stats = eff.get("stats", {})
            bad = set(stats) - ALLOWED_STATS
            if bad:
                problems.append(f"{ow}：stats 有不准的鍵 {sorted(bad)}")
            evil = _is_evil(o)
            rivals = evil_choices if evil else graded
            for key, value in stats.items():
                best = max((c.get("effect", {}).get("stats", {}).get(key, 0) for c in rivals), default=0)
                if value > 0 and value > best:
                    kind = "原事件的作惡選項" if evil else "有檢定或打仗的開放選項"
                    problems.append(f"{ow}：{key} +{value} 比{kind}最多的 +{best} 還多")
            for key in eff.get("marks", {}):
                loc_id, _, name = key.partition(":")
                if loc_id != first:
                    problems.append(f"{ow}：痕跡的地點 {loc_id} 要是 {first}")
                if not CJK.match(name):
                    problems.append(f"{ow}：痕跡名「{name}」要是 2～4 個中文字")
                if name in marks_seen:
                    problems.append(f"{ow}：痕跡名「{name}」在同一則裡重複")
                marks_seen.add(name)
            if "marks" not in eff:
                problems.append(f"{ow}：沒有痕跡")
            c = eff.get("contribution")
            if evil:  # 作惡不能是最後一種：最後一種照上面 fallback 的規矩，不准有 stats
                if c:
                    problems.append(f"{ow}：作惡的後果不記貢獻（contribution {c}）")
            elif not isinstance(c, int) or not 1 <= c <= 4:
                problems.append(f"{ow}：contribution {c} 要在 1～4")
            fe = o.get("fail_effect")
            if "cost" not in o:
                if not fe:
                    problems.append(f"{ow}：check／combat 要有 fail_effect")
                else:
                    text_ok(f"{ow} 的 fail_effect", fe.get("text", ""), narrative=False)
                    if DIGITS.search(fe.get("text", "")):
                        problems.append(f"{ow}：fail_effect 的敘事裡寫了數字")
                    if set(fe.get("stats", {})) - ALLOWED_STATS:
                        problems.append(f"{ow}：fail_effect 的 stats 有不准的鍵")
                    st = fe.get("stamina")
                    if st is not None and not -20 <= st <= -5:
                        problems.append(f"{ow}：fail_effect 的 stamina {st} 要在 −20～−5")
    total = sum(by_region.values())
    for region, n in sorted(by_region.items()):
        print(f"{region}: {n} 則")
        if n < 4:
            problems.append(f"大區 {region} 只有 {n} 則（要至少 4）")
    print(f"總計 {total} 則")
    for w in warnings:
        print("警告：", w)
    if problems:
        for p in problems:
            print("問題：", p)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "content" / "events_outcomes.json"
    raise SystemExit(main(target))
