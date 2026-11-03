"""寫三份鏡頭檔：used、poor（爐火看不了的兩種，甲乙）、open（四處挑定的真實畫面＋另外兩組對比）。python mkshots.py <資料夾>"""
import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
FREEZE = ("window.fetch = () => new Promise(() => {}); const st = document.createElement('style'); "
          "st.textContent = '*,*::before,*::after{transition:none!important;animation:none!important} #toast{display:none!important}'; "
          "document.head.appendChild(st);")
WAIT = "await new Promise((ok) => setTimeout(ok, 400));"
TAG = "document.querySelector('.fu-tag').textContent = %s;"

used = [
    {"name": "對比-小籤-甲-看不了寫短字-used", "w": 375, "h": 812, "tab": "forge", "pre": FREEZE},
    {"name": "對比-小籤-乙-看不了寫原因-used", "w": 375, "h": 812, "tab": "forge", "pre": FREEZE + TAG % json.dumps("今天看過了")},
]
poor = [
    {"name": "對比-小籤-甲-看不了寫短字-poor", "w": 375, "h": 812, "tab": "forge", "pre": FREEZE},
    {"name": "對比-小籤-乙-看不了寫原因-poor", "w": 375, "h": 812, "tab": "forge", "pre": FREEZE + TAG % json.dumps("還差 40 兩")},
]
ready = [{"name": "爐火小籤-看過了-375淺", "w": 375, "h": 812, "tab": "forge"}]

BREW = "document.querySelector('[data-act=\"shop-brew\"][data-attr=\"柔\"][data-tier=\"2\"]').click();"
RACK_TOP = "document.querySelector('.rk-cap').scrollIntoView({ block: 'start' });"
RACK_LOW = "document.querySelector('.shop-more')?.click(); " + WAIT + " [...document.querySelectorAll('.rk-row')].pop().scrollIntoView({ block: 'end' });"
ALBUM = "document.querySelector('.dv-album').scrollIntoView({ block: 'center' });"
RIGHT = "@media (max-width: 359px) { .shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) %s; } .shop-layer .rk-btns { grid-column: 3; grid-row: 1; } }"
VERTICAL = ".shop-layer .dv-cell { writing-mode: vertical-rl; }"
PROTO = (".shop-layer .dv-cell { width: 3.9em; height: 3.9em; min-height: 0; aspect-ratio: auto; border-radius: 50%; padding: 2px; font-size: 0.73em; }"
         " .shop-layer .dv-cell br { display: none; }")
opened = []
for w, h, tag, dark in ((375, 812, "375淺", False), (375, 812, "375深", True), (1280, 900, "1280", False)):
    opened.append({"name": f"爐火小籤-{tag}", "w": w, "h": h, "dark": dark, "tab": "forge"})
for w, h, tag, dark in ((375, 812, "375淺", False), (375, 812, "375深", True), (320, 700, "320淺", False), (1280, 900, "1280", False)):
    opened.append({"name": f"熬的小單-{tag}", "w": w, "h": h, "dark": dark, "tab": "forge", "pre": BREW, "wait": 800})
for w, h, tag, dark in ((375, 812, "375淺", False), (375, 812, "375深", True), (320, 700, "320淺", False), (1280, 900, "1280", False)):
    opened.append({"name": f"裝備庫二乘二-{tag}", "w": w, "h": h, "dark": dark, "tab": "rack", "pre": RACK_TOP})
opened.append({"name": "裝備庫二乘二-最長的原因-375淺", "w": 375, "h": 812, "tab": "rack", "pre": RACK_LOW})
for w, h, tag, dark in ((375, 812, "375淺", False), (375, 812, "375深", True), (1280, 900, "1280", False)):
    opened.append({"name": f"收藏冊圓印-{tag}", "w": w, "h": h, "dark": dark, "tab": "divine", "pre": ALBUM})
opened += [
    {"name": "對比-裝備庫320-甲-二乘二改排名字底下", "w": 320, "h": 700, "tab": "rack", "pre": RACK_LOW},
    {"name": "對比-裝備庫320-乙-照舊排右邊-欄寬52%", "w": 320, "h": 700, "tab": "rack", "css": RIGHT % "52%", "pre": RACK_LOW},
    {"name": "對比-裝備庫320-丙-照舊排右邊-欄寬11.4em", "w": 320, "h": 700, "tab": "rack", "css": RIGHT % "11.4em", "pre": RACK_LOW},
    {"name": "對比-長名字-甲-橫寫折兩行", "w": 375, "h": 812, "tab": "divine", "pre": ALBUM},
    {"name": "對比-長名字-乙-直寫右起", "w": 375, "h": 812, "tab": "divine", "css": VERTICAL, "pre": ALBUM},
    {"name": "對比-長名字-丙-原型的縮字", "w": 375, "h": 812, "tab": "divine", "css": PROTO, "pre": ALBUM},
]
for name, shots in (("used", used), ("poor", poor), ("ready", ready), ("open", opened)):
    (OUT / f"shots_{name}.json").write_text(json.dumps(shots, ensure_ascii=False), encoding="utf-8")
print("ok", len(opened))
