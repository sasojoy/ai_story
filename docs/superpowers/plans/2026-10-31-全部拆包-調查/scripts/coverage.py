"""覆蓋檢查：總表（附錄甲的人看的裁定＋附錄丙的機器可讀裁定）＋ area_*.json，對 inventory.json 比。

四種東西各要剛好一個主人（一個包、core、shared〔共用規則層，算核心那一側〕、drop，或 split〔明確裁定拆兩半〕）：
  Game 的方法、tianxia 的模組（不含測試）、server 的路由、app.js 的頂層宣告（另印頂層函式的數字）。
另外順便查測試檔（tests/ 與 tianxia/features/*/tests/）。

用法：python coverage.py [總表.md]（預設同資料夾上一層的 全部拆包-總表.md）
"""
import collections
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
D = Path(__file__).resolve().parent.parent
MD = Path(sys.argv[1]) if len(sys.argv) > 1 else D / "全部拆包-總表.md"
VERBOSE = "-v" in sys.argv

inv = json.load(open(D / "inventory.json", encoding="utf-8"))

# ---------- 宇宙 ----------
U = {}
U["method"] = {m["name"]: m["lines"] for m in inv["game_methods"]}
U["module"] = {m["path"]: m["lines"] for m in inv["modules"] if not m["is_test"]}
U["route"] = {r["path"]: r["lines"] for r in inv["server_routes"]}
U["app"] = {d["name"]: d["lines"] for d in inv["web"]["app_js"]["top_level"]}
APP_KIND = {d["name"]: d["kind"] for d in inv["web"]["app_js"]["top_level"]}
FUNC_KINDS = {"function", "async function", "const arrow/function"}
WT = Path(inv["meta"]["worktree"])
test_files = sorted(
    str(p.relative_to(WT)).replace("\\", "/")
    for p in list((WT / "tests").rglob("test_*.py")) + list((WT / "tianxia" / "features").rglob("test_*.py"))
)
U["test"] = {Path(t).stem: 0 for t in test_files}
KINDS = ["method", "module", "route", "app", "test"]
KIND_ZH = {"method": "Game 方法", "module": "模組", "route": "路由", "app": "app.js 頂層宣告", "test": "測試檔"}

STEM = collections.defaultdict(list)  # 模組短名 → 路徑
for p in U["module"]:
    STEM[p[len("tianxia/"):-3]].append(p)
    STEM[Path(p).stem].append(p)


def mod_lookup(tok: str) -> list[str]:
    tok = tok.strip().rstrip("/")
    if tok.endswith("/*") or tok.endswith("/（已成包）"):
        tok = tok.split("/*")[0]
    t = tok[len("tianxia/"):] if tok.startswith("tianxia/") else tok
    if t.endswith(".py"):
        t = t[:-3]
    if f"tianxia/{t}.py" in U["module"]:
        return [f"tianxia/{t}.py"]
    # 資料夾：tianxia/features/feast/ → 底下全部
    folder = f"tianxia/{t}/"
    under = [p for p in U["module"] if p.startswith(folder)]
    if under:
        return under
    if t in STEM and len(set(STEM[t])) == 1:
        return [STEM[t][0]]
    return []


# ---------- area_*.json ----------
NORM = {k: f"features/{k}" for k in ["tavern", "smithy", "gear", "outlets", "arts", "craft", "sense"]}
area_own = {k: collections.defaultdict(set) for k in KINDS}


def clean(n: str) -> str:
    return re.split(r"[（( ]", n.strip())[0]


for a in ["core", "action", "combat", "growth", "world"]:
    data = json.load(open(D / f"area_{a}.json", encoding="utf-8"))
    for pk, pv in data["assign"].items():
        owner = NORM.get(pk, pk)
        for n in pv.get("game_methods", []):
            area_own["method"][clean(n)].add((a, owner))
        for n in pv.get("modules", []):
            found = re.findall(r"tianxia/[A-Za-z0-9_/]+(?:\.py|/)", n)
            if not found:
                for part in re.split(r"[、，,]", n):
                    m = re.match(r"^([a-z_0-9]+)(?:[（( ]|$)", part.strip())
                    if m:
                        found.append(m.group(1))
            for f in found:
                for p in mod_lookup(f):
                    area_own["module"][p].add((a, owner))
        for n in pv.get("routes", []):
            area_own["route"][clean(n)].add((a, owner))
        for n in pv.get("app_js", []):
            for part in re.split(r"[、，, ]+", n):
                part = re.split(r"[（(]", part)[0].strip()
                if part:
                    area_own["app"][part].add((a, owner))
        for n in pv.get("tests", []):
            for t in re.findall(r"(test_[A-Za-z0-9_]+)", n):
                area_own["test"][t].add((a, owner))

# ---------- 總表 ----------
text = MD.read_text(encoding="utf-8")
ZH = {
    "商城": "features/mall", "宴客": "features/feast", "出陣": "features/sortie", "探索": "features/explore",
    "決戰": "features/battle", "單挑": "features/bout", "酒肆": "features/tavern", "人物情誼": "features/companions",
    "交友求見": "features/socialize", "新手引導": "features/guide", "引導": "features/guide", "修練": "features/arts",
    "有所感": "features/sense", "玉璽": "features/seal", "列傳": "features/zhuan", "一條線": "features/story",
    "簽到": "features/checkin", "大勢人物": "features/figures", "軍情": "features/orders", "陣營": "features/faction",
    "玩家互動": "features/peers", "體力玩法": "features/stamina_plays", "閉關": "features/seclusion",
    "鐵匠鋪": "features/smithy", "裝備": "features/gear", "銀兩出口": "features/outlets", "煉製": "features/craft",
    "懸賞榜": "features/bounties", "懸賞": "features/bounties", "地盤": "features/territory", "移動": "features/travel",
    "輿圖": "features/map", "戰記": "features/tale", "手機通知": "features/notify", "通知": "features/notify",
    "共用規則層": "shared", "核心": "core", "整套拿掉": "drop", "拿掉": "drop",
}


def zh_owner(s: str) -> str | None:
    if "拆兩半" in s or "一半" in s:
        return "split"
    best = None
    for k, v in ZH.items():
        i = s.find(k)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(k) > best[1])):
            best = (i, len(k), v)
    return best[2] if best else None


def section(title_re: str) -> str:
    m = re.search(title_re, text, flags=re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, flags=re.M)
    return rest[: n.start()] if n else rest


ruling = {k: {} for k in KINDS}  # name → (owner, 來源)
conflict_rulings = []


def put(kind, name, owner, src):
    if name in ruling[kind] and ruling[kind][name][0] != owner:
        conflict_rulings.append((kind, name, ruling[kind][name], (owner, src)))
    ruling[kind][name] = (owner, src)


# 附錄甲（人看的表）
A = section(r"^## 附錄甲")
cur = None
header = None
for line in A.splitlines():
    s = line.strip()
    if s.startswith("**"):
        head = s.strip("*")
        cur = ("method" if head.startswith("方法") else "module" if head.startswith("模組") else
               "test" if head.startswith("測試") else None)
        header = None
        continue
    if not s.startswith("|") or cur is None:
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if header is None:
        header = cells
        continue
    if set(s) <= set("|-: "):
        continue
    if cur == "test":
        rc, nc = 0, 1
    else:
        rc = header.index("裁定") if "裁定" in header else 1
        nc = 0
    owner = zh_owner(cells[rc])
    if owner is None:
        continue
    for tok in re.findall(r"`([^`]+)`", cells[nc]):
        if cur == "method" and tok in U["method"]:
            put("method", tok, owner, "甲")
        elif cur == "module":
            for p in mod_lookup(tok):
                put("module", p, owner, "甲")
        elif cur == "test":
            for t in re.findall(r"(test_[A-Za-z0-9_]+)", tok):
                if t.endswith("_") or "*" in tok:
                    for real in U["test"]:
                        if real.startswith(t):
                            put("test", real, owner, "甲")
                else:
                    put("test", t, owner, "甲")

# 附錄丙（機器可讀）：| 種類 | 歸到 | 名字 |；種類＝方法／模組／路由／app.js／測試
C = section(r"^## 附錄丙")
KMAP = {"方法": "method", "模組": "module", "路由": "route", "app.js": "app", "測試": "test"}
bad_c = []
for line in C.splitlines():
    s = line.strip()
    if not s.startswith("|"):
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 3 or cells[0] not in KMAP:
        continue
    kind, owner = KMAP[cells[0]], cells[1].strip("` ")
    for tok in re.findall(r"`([^`]+)`", cells[2]):
        if kind == "module":
            ps = mod_lookup(tok)
            if not ps:
                bad_c.append((kind, tok))
            for p in ps:
                put(kind, p, owner, "丙")
        elif tok in U[kind]:
            put(kind, tok, owner, "丙")
        else:
            bad_c.append((kind, tok))

# ---------- 合起來 ----------
VALID = lambda o: o in {"core", "shared", "drop"} or o.startswith("features/") or o.startswith("split")
final = {k: {} for k in KINDS}
report = {}
for kind in KINDS:
    missing, dups = [], []
    for name in U[kind]:
        if name in ruling[kind]:
            final[kind][name] = ruling[kind][name][0]
            continue
        owners = {o for _, o in area_own[kind].get(name, set())}
        side = {("core" if o in ("core", "shared") else o) for o in owners}
        if not owners:
            missing.append(name)
        elif len(side) > 1:
            dups.append((name, sorted(owners)))
        else:
            final[kind][name] = sorted(owners)[0]
    extra = sorted(n for n in area_own[kind] if n not in U[kind])
    invalid = sorted((n, o) for n, o in final[kind].items() if not VALID(o))
    report[kind] = (missing, dups, extra, invalid)

print(f"總表：{MD.name}")
for kind in KINDS:
    missing, dups, extra, invalid = report[kind]
    tot = len(U[kind])
    print(f"\n== {KIND_ZH[kind]}：{tot} 個；有主人 {len(final[kind])}；沒歸 {len(missing)}；重複（沒裁定的衝突） {len(dups)}；主人寫錯 {len(invalid)}")
    if kind == "app":
        fn = [n for n in U["app"] if APP_KIND[n] in FUNC_KINDS]
        fm = [n for n in missing if APP_KIND[n] in FUNC_KINDS]
        fd = [n for n, _ in dups if APP_KIND[n] in FUNC_KINDS]
        print(f"   其中頂層函式 {len(fn)} 個：沒歸 {len(fm)}、重複 {len(fd)}")
    if missing:
        print("   沒歸：", "、".join(missing[:400]))
    for n, o in dups:
        print("   重複：", n, o)
    for n, o in invalid:
        print("   主人寫錯：", n, o)
    if extra and VERBOSE:
        print("   （area 裡有、清單裡沒有的名字，多半是寫法不同）：", "、".join(extra[:80]))

if bad_c:
    print("\n附錄丙裡對不到清單的名字：", bad_c)
if conflict_rulings:
    print("\n附錄甲、丙互相打架：")
    for c in conflict_rulings:
        print("  ", c)

# 每包的數字（方法）
per = collections.defaultdict(lambda: [0, 0])
for n, o in final["method"].items():
    per[o][0] += 1
    per[o][1] += U["method"][n]
print("\n== 每包 Game 方法／行")
for o, (c, l) in sorted(per.items(), key=lambda x: -x[1][1]):
    print(f"   {o}: {c}／{l}")
print("   合計", sum(v[0] for v in per.values()), "／", sum(v[1] for v in per.values()),
      "；清單", len(U["method"]), "／", sum(U["method"].values()))
json.dump({k: final[k] for k in KINDS}, open(Path(__file__).parent / "final_owner.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=0)
