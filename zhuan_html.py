"""公開的傳（玩家傳第二批，/zhuan/<代碼>）：不用登入的唯讀頁，伺服器直接吐一整頁 HTML（不經過 web/app.js）。

LINE、FB 只讀伺服器回的 HTML 抓預覽，所以標題、摘要、題簽圖都寫在 <head> 的 Open Graph 裡。文字一律跳脫；版面是武學譜那本書的配色
（--bk-*，暗色時換成燈下的舊紙），預設橫排，右上角可以切直書（記在這個瀏覽器的 localStorage）。手機上「分享」叫系統的分享選單
（Web Share API），沒有就複製網址。只 import 標準函式庫與 tianxia.biography。
"""
from __future__ import annotations

from html import escape

from tianxia import biography

FONT = "https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;700&display=swap"

CSS = """
:root{--paper:#f2e5c6;--paper2:#e8d6ad;--ink:#241a11;--ink2:#6d5a43;--rule:#a9814b;--cover:#2f4a5c;--cover2:#1d3140;--slip:#f6edd8;--seal:#b3261e;--seal-ink:#fbf3e2;
--serif:"Noto Serif TC","Noto Serif CJK TC","Source Han Serif TC","Songti TC","PMingLiU",serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--paper:#2b241b;--paper2:#221c15;--ink:#efe1c3;--ink2:#b39e7f;--rule:#8a6a3e;--cover:#23394a;--cover2:#142431;--slip:#e9dcc0;--seal:#c4372c;color-scheme:dark}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper2);color:var(--ink)}
body{font:16px/1.6 -apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0)}
.cover{position:relative;height:220px;overflow:hidden;background:linear-gradient(180deg,var(--cover2) 0%,var(--cover) 72%)}
.cover svg{position:absolute;left:0;right:0;bottom:0;width:100%;height:120px}
.cover .far{fill:rgba(233,220,192,.16)}.cover .near{fill:rgba(63,125,92,.45)}
.moon{position:absolute;top:42px;left:46px;width:34px;height:34px;border-radius:50%;background:rgba(246,237,216,.6);box-shadow:0 0 24px 6px rgba(246,237,216,.18)}
.slip{position:absolute;top:22px;right:32px;padding:16px 10px;writing-mode:vertical-rl;background:var(--slip);border:2px solid var(--seal);
box-shadow:inset 0 0 0 3px var(--slip),inset 0 0 0 4px var(--seal),0 4px 12px rgba(0,0,0,.25)}
.slip h1{margin:0;font:700 30px/1 var(--serif);letter-spacing:10px;color:#241a11}
.sub{position:absolute;left:18px;bottom:14px;margin:0;color:var(--slip);font-size:13px;letter-spacing:1px;text-shadow:0 1px 3px rgba(0,0,0,.5)}
.bar{display:flex;gap:8px;justify-content:flex-end;padding:12px 16px 0;max-width:640px;margin:0 auto}
.bar button{font:600 14px var(--serif);color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:999px;padding:6px 14px;cursor:pointer}
.bar button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.leaf{max-width:640px;margin:12px auto 0;padding:0 16px}
.text{padding:22px 20px;border:2px solid var(--rule);background:var(--paper);
box-shadow:inset 0 0 0 4px var(--paper),inset 0 0 0 5px var(--rule),0 3px 10px rgba(60,40,20,.18);
font:17px/2.05 var(--serif);letter-spacing:.04em;text-align:justify}
.text p{margin:0 0 1em;text-indent:2em}
.text p.ping{margin-top:1.4em;padding-top:1em;border-top:1px solid var(--rule);text-indent:0}
.text p:last-child{margin-bottom:0}
.vertical .text{writing-mode:vertical-rl;height:72vh;min-height:420px;overflow-x:auto;overflow-y:hidden;line-height:2.2;
background:repeating-linear-gradient(to left,transparent 0 calc(2.2em - 1px),rgba(169,129,75,.3) calc(2.2em - 1px) 2.2em) var(--paper)}
.vertical .text p{margin:0 0 0 1.1em;text-indent:2em}
.vertical .text p.ping{border-top:0;border-right:1px solid var(--rule);padding:0 1em 0 0;margin:0 1.4em 0 0;text-indent:0}
.seal{display:block;width:64px;height:64px;margin:18px 6px 0 auto;transform:rotate(-5deg)}
.seal rect{fill:var(--seal)}.seal text{fill:var(--seal-ink);font:700 22px var(--serif);text-anchor:middle;dominant-baseline:central}
footer{max-width:640px;margin:22px auto 40px;padding:0 16px;color:var(--ink2);font:14px/1.7 var(--serif);text-align:center}
footer a{color:var(--seal);font-weight:700;text-decoration:none}
.toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0));transform:translateX(-50%);background:var(--ink);color:var(--paper);
padding:8px 16px;border-radius:999px;font-size:14px}
"""

SCRIPT = """
(function(){
  var KEY="tx-zhuan-vertical",root=document.documentElement,btn=document.getElementById("vert");
  function set(on){root.classList.toggle("vertical",on);btn.setAttribute("aria-pressed",on?"true":"false");
    if(on){var t=document.querySelector(".text");t.scrollLeft=t.scrollWidth;}}
  try{set(localStorage.getItem(KEY)==="1");}catch(e){}
  btn.addEventListener("click",function(){var on=!root.classList.contains("vertical");set(on);try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}});
  function toast(msg){var d=document.createElement("div");d.className="toast";d.textContent=msg;document.body.appendChild(d);setTimeout(function(){d.remove();},2200);}
  document.getElementById("share").addEventListener("click",function(){
    var url=location.href.split("#")[0],title=document.title;
    if(navigator.share){navigator.share({title:title,url:url}).catch(function(){});return;}
    if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){toast("網址已複製");},function(){prompt("複製這個網址",url);});}
    else prompt("複製這個網址",url);
  });
})();
"""

HILLS = (
    '<svg viewBox="0 0 375 120" preserveAspectRatio="none" aria-hidden="true">'
    '<path class="far" d="M0 86 C40 58 70 64 104 46 C134 30 160 52 190 40 C226 26 258 48 292 36 C326 24 352 40 375 34 V120 H0Z"/>'
    '<path class="near" d="M0 104 C36 86 72 96 110 80 C150 64 178 88 222 76 C262 66 300 86 340 74 C356 70 366 72 375 70 V120 H0Z"/>'
    "</svg>"
)
SEAL = '<svg class="seal" viewBox="0 0 64 64" aria-label="天下大勢"><rect x="2" y="2" width="60" height="60" rx="6"/>' \
       '<text x="20" y="20">天</text><text x="44" y="20">大</text><text x="20" y="44">下</text><text x="44" y="44">勢</text></svg>'


def page(row: dict, scenario: str, url: str, image: str) -> str:
    """一篇公開的傳。row 是 biographies 的一列（WorldStateStore.biography_by_code）；url 是這一頁的網址，image 是題簽圖的網址。"""
    name = row["name"]
    head = biography.title(name)
    paras = [p for p in row["text"].split("\n\n") if p.strip()]
    lead = biography.lead(row["text"])
    body = "".join(
        f'<p class="{"ping" if p.startswith("評曰") else ""}">{escape(p)}</p>' for p in paras
    )
    sub = f"天下大勢・第 {row['season']} 季・{scenario}"
    meta = "".join(
        f'<meta property="{k}" content="{escape(v)}">'
        for k, v in (("og:type", "article"), ("og:site_name", "天下大勢"), ("og:title", head), ("og:description", lead),
                     ("og:url", url), ("og:image", image), ("og:image:width", "1200"), ("og:image:height", "630"))
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{escape(head)}・天下大勢</title><meta name="description" content="{escape(lead)}"><meta name="robots" content="noindex">
{meta}<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="{FONT}"><style>{CSS}</style></head>
<body><header class="cover">{HILLS}<i class="moon" aria-hidden="true"></i><div class="slip"><h1>{escape(head)}</h1></div>
<p class="sub">{escape(sub)}</p></header>
<div class="bar"><button id="vert" aria-pressed="false">直書</button><button id="share">分享</button></div>
<main class="leaf"><article class="text">{body}</article>{SEAL}</main>
<footer>這是《天下大勢》裡一位江湖人物的列傳。<br><a href="/">也去江湖走一遭 ›</a></footer>
<script>{SCRIPT}</script></body></html>"""


def missing() -> str:
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>查無此傳・天下大勢</title><meta name="robots" content="noindex"><style>{CSS}</style></head>
<body><main class="leaf" style="padding-top:20vh"><article class="text"><p>史館裡查無此傳——也許作者已經收回，或是網址抄錯了。</p></article></main>
<footer><a href="/">回到江湖 ›</a></footer></body></html>"""
