"""把 W2 的 tools/shoot.mjs 抄成第二輪重拍用的 shoot2.mjs：埠與主機名換成 w2b、抽屜那兩張改成真觸控（一排卡＝點把手一下、全開＝把手拖到頂），
浮著的那幾樣只量看得到的（第二輪起被抽屜蓋住、會疊到的會收起來），另外記收起來的是哪幾樣。"""
import os

WT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1"
W2B = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b"
src = os.path.join(WT, "docs", "superpowers", "specs", "2026-10-30-輿圖表現-草圖", "W2", "tools", "shoot.mjs")
with open(src, encoding="utf-8", newline="") as f:
    text = f.read().replace("\r\n", "\n")
subs = [
    ("// node shoot_fix.mjs <輸出資料夾>", "// （W2 第二輪 2026-10-31：抽屜那兩張改成真觸控——一排卡＝點把手一下、全開＝把手拖到頂；浮著的只量看得到的）\n// node shoot_fix.mjs <輸出資料夾>"),
    ('const ORIGIN = "http://w2fix.localhost:8181";', 'const ORIGIN = "http://w2b.localhost:8183";'),
    ("port: 9481,", "port: 9670,"),
    ('  const hud = all(".mv-area, .mv-q, .mv-mini, .mv-fab button").map(R);',
     '  const seen = (e) => getComputedStyle(e).visibility !== "hidden";\n'
     '  const hud = all(".mv-area, .mv-q, .mv-mini, .mv-mini-c, .mv-fab button").filter(seen).map(R);\n'
     '  const hudHidden = [["area", "#mv-area"], ["q", "#mv-q"], ["mini", "#mv-mini"], ["fab", "#mv-fab"]].filter(([, s]) => { const e = document.querySelector(s); return e && !seen(e); }).map(([k]) => k);'),
    ("    mode: S.mapMode, sel: S.mapSel,", "    hudHidden, mode: S.mapMode, sel: S.mapSel,"),
    ('    if (s.drawer) { await page.eval(`mapStop(${JSON.stringify(s.drawer)})`); await sleep(900); }',
     '    if (s.drawer) {\n'
     '      // 真觸控：一排卡＝點把手一下（FB-9090：以前 pointerup 換格，click 落到滑上來的卡）；全開＝把手拖到頂（FB-9093：放手剛好是那一格也重排）\n'
     '      const gb = await page.eval(`(() => { const r = document.getElementById("mgrab").getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`);\n'
     '      if (s.drawer === "row") { await tap(gb[0], gb[1]); r.grabTap = gb; }\n'
     '      else {\n'
     '        await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: gb[0], y: gb[1], id: 1 }] });\n'
     '        for (let i = 1; i <= 16; i++) { await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: gb[0], y: gb[1] - (1000 * i) / 16, id: 1 }] }); await sleep(16); }\n'
     '        await sleep(60);\n'
     '        await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });\n'
     '        r.grabDrag = gb;\n'
     '      }\n'
     '      await sleep(1100);\n'
     '    }'),
]
for a, b in subs:
    assert text.count(a) == 1, a
    text = text.replace(a, b)
with open(os.path.join(W2B, "shoot2.mjs"), "w", encoding="utf-8", newline="") as f:
    f.write(text)
with open(os.path.join(W2B, "shots2.json"), "w", encoding="utf-8") as f:
    f.write("""[
  { "name": "W2-3-去輿圖-375", "w": 375, "h": 812, "goto": true },
  { "name": "W2-4-去輿圖護糧-375", "w": 375, "h": 812, "goto": "escort" },
  { "name": "W2-5-抽屜一排卡-375", "w": 375, "h": 812, "drawer": "row" },
  { "name": "W2-6-抽屜全開-375", "w": 375, "h": 812, "drawer": "full" }
]
""")
print("written")
