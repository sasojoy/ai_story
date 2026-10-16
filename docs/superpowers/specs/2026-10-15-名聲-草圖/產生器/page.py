"""把 gen.py 畫好的每一種（data.json）與遊戲的樣式（game.css）組成一頁。"""
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

HERE = Path(tempfile.gettempdir()) / "renown-sketch"  # gen.py 寫的 data.json、game.css
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "renown-sketch.html"
data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
css = (HERE / "game.css").read_text(encoding="utf-8")
assert "</script" not in css
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

SECTIONS = [
    ("A", "top", "一、狀態列收起時：名號旁邊的兩個稱號",
     "設計 2.5：現在散人收起時寫「散人・江湖遊俠」的地方，改接兩個稱號的短版（名望小有名氣起、善惡第 1 段起），例如「名動一方・一方豪俠」。官軍、黃巾的人前面還有頭銜，放不下時怎麼收？每一種底下另附走寇的散人那一條。"),
    ("B", "card", "二、狀態列展開時：「名聲」那一行與說明卡",
     "設計 2.5、6.1：頭銜底下多一行「名聲」，原本那一行「名望 27・善名 18・惡名 3」的數字移進說明卡。點了開說明卡：兩個稱號、下一段還差多少、名望與善惡每一段給什麼（第四、五節的表），散人另列遊俠名號留下來的好處。這一處最重要，多畫一種（2D：推薦的那一種換成走寇的散人）。"),
    ("C", "peer", "三、玩家卡：別人的名聲",
     "設計 2.5：點「此地還有」的名字打開玩家卡，只寫稱號、不寫數字；點了開的是通用說明（各段代表什麼），不是他的數字。這裡是顧長風點開韓七。"),
    ("D", "merit", "四、決戰「本場戰功」：名字後面的稱號",
     "設計 2.5、4.5：戰局條底下兩軍各列前三名，名字後面用小字寫稱號（善惡第 1 段起、名望要名動一方才寫），加入決戰時快照。這是真的宛城之戰打到第三回合、輪到你出招的畫面：三招排在場景底下，這一塊越高、三招越往下（FB-136）。"),
    ("E", "opt", "五、事件選項：稱號不夠時",
     "設計 5.3：俠才有、寇才有的選項，稱號不夠的人也看得到、按不下去，寫要什麼稱號。這裡是走寇的韓七（江湖巨寇）碰上「米價一日三漲」，俠的新選項要一方豪俠（附錄 A 的第一則）。"),
    ("F", "cross", "六、跨段那一刻的江湖紀錄",
     "設計 3.3、6.4：跨過一段時，這一下那一則江湖紀錄接一行「你的名號傳開了……」，再一行寫這一段多了什麼；得失那一排接差距。這裡是顧長風照「米價一日三漲」盯著量米，名望 24 → 25 跨進名動一方。"),
]

sections = "\n".join(
    f"""  <section id="{key}">
    <h2>{title}</h2>
    <p class="ask">{ask}</p>
    <div class="row" data-group="{group}"></div>
  </section>""" for group, key, title, ask in SECTIONS)

page = f"""<title>名聲畫面草圖</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap">
<style>
/* 版面：六段，每段一排手機（375 寬的真畫面縮小放進框裡，可上下捲）；外框只管排版與說明，遊戲畫面照遊戲自己的樣子 */
:root {{
  --bg: #f1f2ee; --card: #ffffff; --ink: #1d2126; --muted: #59606a; --line: #d6d9d2; --accent: #8a5a12; --accent-bg: #f4ead6; --mark: #d0513a;
  --display: "Noto Serif TC", "Songti TC", "PMingLiU", serif;
  --body: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --bg: #14161a; --card: #1d2025; --ink: #e9e6df; --muted: #9ba2ac; --line: #30343b; --accent: #e3b468; --accent-bg: #33291a; --mark: #ef7a63; color-scheme: dark; }}
}}
:root[data-theme="dark"] {{ --bg: #14161a; --card: #1d2025; --ink: #e9e6df; --muted: #9ba2ac; --line: #30343b; --accent: #e3b468; --accent-bg: #33291a; --mark: #ef7a63; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.7 var(--body); }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 56px; }}
h1 {{ font: 700 28px/1.3 var(--display); margin: 0 0 6px; text-wrap: balance; }}
.lede {{ color: var(--muted); max-width: 66ch; margin: 0; }}
.bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin-top: 14px; }}
.themes {{ display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; background: var(--card); }}
.themes button {{ border: 0; background: none; color: var(--muted); font: 500 13px var(--body); padding: 5px 14px; cursor: pointer; }}
.themes button[aria-pressed="true"] {{ background: var(--accent-bg); color: var(--accent); font-weight: 700; }}
.themes button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
.key {{ font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 8px; }}
.key i {{ display: inline-block; width: 26px; height: 14px; border: 2.5px dashed var(--mark); border-radius: 4px; }}
.who {{ margin: 16px 0 0; padding: 10px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--card); font-size: 14px; max-width: 80ch; }}
.who p {{ margin: 0; }}
.who b {{ font-family: var(--display); }}
.who .note {{ margin-top: 4px; font-size: 13px; color: var(--muted); }}
section {{ margin-top: 44px; }}
h2 {{ font: 700 21px/1.4 var(--display); margin: 0 0 4px; text-wrap: balance; }}
.ask {{ color: var(--muted); margin: 0 0 16px; max-width: 70ch; }}
.row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 22px; align-items: start; }}
.opt {{ display: grid; gap: 10px; min-width: 0; }}
.phone {{ width: 100%; max-width: 300px; justify-self: center; border-radius: 22px; padding: 8px; background: var(--card); border: 1px solid var(--line); box-shadow: 0 6px 18px rgba(0,0,0,.08); }}
.phone.sub {{ border-radius: 14px; padding: 6px; box-shadow: none; }}
.sublabel {{ justify-self: center; width: 100%; max-width: 300px; margin: -2px 0 -6px; font-size: 12px; color: var(--muted); }}
.screen {{ position: relative; width: 100%; overflow: hidden; border-radius: 14px; }}
.phone.sub .screen {{ border-radius: 9px; }}
.screen iframe {{ position: absolute; left: 0; top: 0; width: 375px; border: 0; transform-origin: 0 0; background: #fff; }}
.cap {{ display: grid; gap: 4px; min-width: 0; }}
.cap h3 {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; margin: 0; font: 700 16px/1.5 var(--display); }}
.cap h3 .id {{ font: 500 12px var(--body); letter-spacing: .08em; color: var(--muted); }}
.rec {{ font: 700 12px var(--body); letter-spacing: .06em; color: var(--accent); background: var(--accent-bg); border: 1px solid var(--accent); border-radius: 999px; padding: 0 8px; }}
.cap ul {{ margin: 0; padding-left: 1.2em; color: var(--muted); font-size: 14px; }}
.foot {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; max-width: 78ch; }}
.foot h2 {{ color: var(--ink); font-size: 18px; }}
.foot p, .foot li {{ margin: 0 0 6px; }}
.foot b {{ color: var(--ink); }}
</style>

<div class="wrap">
  <h1>名聲：五處新畫面</h1>
  <p class="lede">第 3 塊「名聲」的畫面要加在五個地方（第五處分成事件選項與江湖紀錄兩段）。每一處畫了兩三種，說明卡多畫一種；都是拿真的遊戲畫面改的：同一份 app.js 與 style.css，資料是用正式內容建的示範角色、照真的引擎拿的。紅色虛線框是新加的那一塊；標「推薦」的是我的建議。手機畫面可以上下捲。</p>
  <div class="bar">
    <div class="themes" role="group" aria-label="畫面的深淺">
      <button type="button" id="theme-system" data-mode="system" aria-pressed="true">跟系統</button>
      <button type="button" id="theme-light" data-mode="light" aria-pressed="false">淺色</button>
      <button type="button" id="theme-dark" data-mode="dark" aria-pressed="false">深色</button>
    </div>
    <span class="key"><i aria-hidden="true"></i>新加的那一塊</span>
  </div>
  <div class="who">
    <p><b>顧長風</b>　官軍・屯長，第 14 級。名望 27：名動一方，再 23 到威震州郡。善名 18、惡名 3：一方豪俠，再 12 到州郡大俠。</p>
    <p><b>韓七</b>　散人，第 12 級。名望 12：小有名氣。善名 4、惡名 22：照惡名算，江湖巨寇。</p>
    <p class="note">週末季（門檻倍數 1）。兩人都站在汝南集市；決戰那一處移到宛城。字都待 joy 潤。</p>
  </div>

{sections}

  <div class="foot">
    <h2>推薦一覽</h2>
    <ul>
      <li><b>一 → 1A</b>：一行不變、第一屏不多佔、字不縮；散人原本看得到遊俠名號的地方照舊看得到稱號。名望稱號收掉時，展開就看得到。</li>
      <li><b>二 → 2B</b>：抽屜跟玩家卡、設定同一種，自己捲、不撐高黏在頂上的狀態列；名望、善惡分兩頁，一段一列看得清楚；玩家卡點別人的名聲開同一張。</li>
      <li><b>三 → 3A</b>：跟自己的狀態列同一行同一個寫法，學一次就看得懂別人的，也有地方點開說明。3B 的上色可以之後加在 3A 的字上。</li>
      <li><b>四 → 4A</b>：不加高度，三招不被往下推（B 高 41px、C 高 76px）；一行只放得下一個，名望優先（名動一方才寫，本來就是那一段「被看見」的好處）。</li>
      <li><b>五（選項）→ 5B</b>：「俠」「寇」一個字標在編號那一格，有稱號的人也看得出這一顆是名聲換來的；原因在第二行，選項的字不變長。</li>
      <li><b>五（紀錄）→ 6B</b>：「剛剛」收著只露開頭幾行，接在最後的兩行常常被蓋住；得失那一排收著也看得到，多一顆金色的「名號傳開」，點了開名聲抽屜。</li>
    </ul>
    <h2>怎麼畫的</h2>
    <p>引擎：正式內容、週末設定，用 Game 建兩個示範角色與一場宛城之戰（六個人打到第三回合），拿 server.main_view 與玩家卡的資料。名聲的資料照設計第二、四、五節的表算好，加在 status.renown、玩家卡與本場戰功那幾列上（引擎還沒有這些欄位）。</p>
    <p>畫面：webharness 的假瀏覽器跑真的 app.js（render），只改了草圖要的幾個地方（名號那一塊、玩家卡、本場戰功、選項、說明卡），新加的樣子另寫一小段 CSS。收起時放不放得下，假瀏覽器量不到字寬，用字數估；真的做時照 fitBars 量。俠青、寇赭、名望金的顏色待 joy 對。</p>
  </div>
</div>

<script type="text/plain" id="game-css">{css}</script>
<script type="application/json" id="data">{blob}</script>
<script>
(function () {{
  var base = document.getElementById("game-css").textContent;
  var data = JSON.parse(document.getElementById("data").textContent);
  var DARK = "@media (prefers-color-scheme: dark)";
  var mode = "system";
  var frames = [];
  // 遊戲的深色寫在 prefers-color-scheme 裡：淺色把它關掉、深色把它變成一律套用
  function cssFor(m) {{
    if (m === "light") return base.split(DARK).join("@media not all");
    if (m === "dark") return base.split(DARK).join("@media all");
    return base;
  }}
  function doc(v, m) {{
    return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=375">'
      + "<style>" + cssFor(m) + "</style></head><body><div id=\\"app\\">" + v.html + "</div></body></html>";
  }}
  function fit(screen, frame, h) {{
    var s = screen.clientWidth / 375;
    frame.style.height = h + "px";
    frame.style.transform = "scale(" + s + ")";
    screen.style.height = Math.round(h * s) + "px";
  }}
  function phone(v, sub) {{
    var p = document.createElement("div");
    p.className = sub ? "phone sub" : "phone";
    var screen = document.createElement("div");
    screen.className = "screen";
    var frame = document.createElement("iframe");
    frame.title = v.title;
    frame.setAttribute("loading", "lazy");
    screen.appendChild(frame);
    p.appendChild(screen);
    var f = {{ frame: frame, v: v, screen: screen }};
    frame.addEventListener("load", function () {{ focus(f); }});
    frames.push(f);
    return p;
  }}
  // 要看的那一塊不在第一屏時（事件的選項），只捲手機裡面（scrollIntoView 會連外面這一頁一起捲）
  function focus(f) {{
    if (!f.v.focus) return;
    try {{
      var d = f.frame.contentDocument, w = f.frame.contentWindow, el = d.querySelector(f.v.focus);
      if (el) w.scrollTo(0, el.getBoundingClientRect().top + w.scrollY - 360);
    }} catch (e) {{ /* 看不到裡面就照頂端 */ }}
  }}
  function paint() {{
    frames.forEach(function (f) {{ f.frame.srcdoc = doc(f.v, mode); fit(f.screen, f.frame, f.v.h); }});
  }}
  Object.keys(data).forEach(function (group) {{
    var row = document.querySelector('[data-group="' + group + '"]');
    data[group].forEach(function (v) {{
      var opt = document.createElement("div");
      opt.className = "opt";
      opt.appendChild(phone({{ html: v.html, h: v.h, focus: v.focus, title: v.id + " " + v.name }}, false));
      if (v.sub) {{
        var lab = document.createElement("div");
        lab.className = "sublabel";
        lab.textContent = v.sub.label;
        opt.appendChild(lab);
        opt.appendChild(phone({{ html: v.sub.html, h: v.sub.h, title: v.id + " " + v.sub.label }}, true));
      }}
      var cap = document.createElement("div");
      cap.className = "cap";
      var h = '<h3><span class="id">' + v.id + "</span>" + v.name + (v.rec ? '<span class="rec">推薦</span>' : "") + "</h3><ul>";
      v.notes.forEach(function (n) {{ h += "<li>" + n + "</li>"; }});
      cap.innerHTML = h + "</ul>";
      opt.appendChild(cap);
      row.appendChild(opt);
    }});
  }});
  function setMode(m, fromViewer) {{
    mode = m;
    document.querySelectorAll(".themes button").forEach(function (b) {{ b.setAttribute("aria-pressed", String(b.dataset.mode === m)); }});
    if (!fromViewer) {{
      if (m === "system") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", m);
    }}
    paint();
  }}
  document.querySelectorAll(".themes button").forEach(function (b) {{
    b.addEventListener("click", function () {{ setMode(b.dataset.mode, false); }});
  }});
  // 看的人在外面切了深淺（根元素的 data-theme）：手機畫面跟著換
  var t0 = document.documentElement.getAttribute("data-theme");
  new MutationObserver(function () {{
    var t = document.documentElement.getAttribute("data-theme");
    var m = t === "dark" || t === "light" ? t : "system";
    if (m !== mode) setMode(m, true);
  }}).observe(document.documentElement, {{ attributes: true, attributeFilter: ["data-theme"] }});
  setMode(t0 === "dark" || t0 === "light" ? t0 : "system", true);
  window.addEventListener("resize", function () {{ frames.forEach(function (f) {{ fit(f.screen, f.frame, f.v.h); }}); }});
}})();
</script>
"""
OUT.write_text(page, encoding="utf-8")
print(OUT, len(page))

# 預覽用：每一種各一頁（375 寬直接看），只放在草圖的暫存資料夾
if len(sys.argv) > 2:
    one = Path(sys.argv[2])
    one.mkdir(parents=True, exist_ok=True)
    for group in data.values():
        for v in group:
            for key, item in ((v["id"], v), (v["id"] + "s", v.get("sub"))):
                if item:
                    (one / f"{key}.html").write_text('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=375">'
                                                     f'<style>{css}</style></head><body><div id="app">{item["html"]}</div></body></html>', encoding="utf-8")
