"""量地（groundSvg）的框涵蓋率、#mk 的大小與節點數：python measure_ground.py <工作樹> <版本（git rev 或 work）> <輸出 json>
版本是 git rev 時把那一版的 web/ 四個檔（webharness.APP_FILES）接起來當 app 跑；work＝工作樹現在的。
局面：season21 開季（官軍站潁川郡）＋ QA 的局面（_cover_state：汝南荒野中立官軍在推、荒丘剛易手、潁川書院戰書）。TIANXIA_DB 由外面設。"""
import io
import json
import os
import subprocess
import sys

ROOT, REV, OUT = sys.argv[1:4]
sys.path.insert(0, os.path.join(ROOT, "tests"))
for d in sorted(os.listdir(os.path.join(ROOT, "tests"))):
    if os.path.isdir(os.path.join(ROOT, "tests", d)) and not d.startswith(("_", ".")):
        sys.path.insert(0, os.path.join(ROOT, "tests", d))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import test_map_web as T  # noqa: E402
import webharness  # noqa: E402
import server  # noqa: E402

app = str(webharness.APP)
if REV != "work":
    parts = [subprocess.run(["git", "show", f"{REV}:web/{f}"], capture_output=True, check=True).stdout.decode("utf-8").replace("\r\n", "\n") for f in webharness.APP_FILES]
    app = os.path.join(os.path.dirname(OUT), f"app_{REV[:8]}.js")
    open(app, "w", encoding="utf-8").write("(() => {\n" + "".join(parts) + "})();\n")

game = T._game(profile="season21")
base = game.map_base()
names = {p["id"]: p["name"] for p in base["places"]}
blocks = sorted(set(game.map_state()["places"]) - T._patches(base))
res = {"rev": REV}
for label, st in (("open", game.map_state()), ("scene", T._cover_state(game))):
    sortie = [x for x in blocks if st["places"][x]["sortie"]]
    want = [[x, T.FRAME_KINDS["rim"]] for x in blocks] + [[st["here"], T.FRAME_KINDS["here"]]] + [[x, T.FRAME_KINDS["sortie"]] for x in sortie]
    if label == "scene":
        want.append(["yingchuan_academy", T.FRAME_KINDS["letter"]])
    k = 2 ** (-round(__import__("math").log2(1.15) * 3) / 3)
    script = T.COVER_JS + f"""
const svg = H.groundSvg(H.S.mapBase, H.S.mapState, {k}, H.S.mapState.now_week);
const tags = svg.match(/<[a-zA-Z][^>]*>/g) || [];
const kinds = {{}};
for (const t of tags) {{ const n = t.match(/^<([a-zA-Z]+)/)[1]; kinds[n] = (kinds[n] || 0) + 1; }}
return {{ len: svg.length, elements: tags.length, kinds, cover: landCover(H.S.mapBase, svg, {json.dumps(want)}) }};"""
    payload = {"m": server.main_view(game), "script": script, "S": {"mapBase": base, "mapState": st}, "menxia": None, "stored": {}, "responses": {}, "app": app}
    out = webharness.run(T.DRIVER, payload, timeout=120)
    rows = [{"id": c["id"], "name": names[c["id"]], "kind": c["classes"][0], "cover": round(c["cover"], 4), "region": round(c["region"], 4) if c["region"] is not None else None} for c in out["cover"]]
    res[label] = {"len": out["len"], "elements": out["elements"], "kinds": out["kinds"], "rows": rows}
    rims = [r for r in rows if r["kind"] == "ld-rim" or r["kind"] == "w-cool"]
    print(label, "len", out["len"], "elements", out["elements"], out["kinds"])
    print("  rims < 95%:", sum(r["cover"] < 0.95 for r in rows if r["kind"] in ("ld-rim",)), "of", len(rims), " min", min(r["cover"] for r in rows))
    for r in rows:
        if r["kind"] != "ld-rim":
            print("  ", r["name"], r["kind"], r["cover"], "region", r["region"])
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
