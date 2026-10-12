"""公開的傳（玩家傳第二批，/zhuan/<代碼>）：不用登入的唯讀頁，伺服器直接吐一整頁 HTML（不經過 web/app.js）。

LINE、FB 只讀伺服器回的 HTML 抓預覽，所以標題、摘要、題簽圖都寫在 <head> 的 Open Graph 裡。文字一律跳脫；樣子跟遊戲裡讀傳共用
web/zhuan.css（同一份標記；竹簡，不用武學譜那本書，企劃者 2026-10-12），預設橫排，右上角可以切直書
（記在這個瀏覽器的 localStorage，跟遊戲裡同一個鍵）。手機上「分享」叫系統的分享選單（Web Share API），沒有就複製網址。
只 import 標準函式庫與 tianxia.biography。
"""
from __future__ import annotations

from html import escape

from tianxia import biography

# 這一頁自己的版面：頁尾、提示；顏色照 zhuan.css 竹簡的變數
CSS = """
*{box-sizing:border-box}
html,body{margin:0}
body{font:16px/1.6 -apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0);min-height:100vh}
footer{max-width:640px;margin:26px auto 0;padding:0 16px 40px;color:var(--zh-sub);font:14px/1.7 var(--zh-font);text-align:center}
footer a{color:inherit;font-weight:700;text-decoration:underline}
.toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0));transform:translateX(-50%);background:var(--zh-btn-ink);color:var(--zh-btn);
padding:8px 16px;border-radius:999px;font-size:14px}
"""

SCRIPT = """
(function(){
  var KEY="tx-zhuan-vertical",text=document.querySelector(".zh-text"),btn=document.getElementById("vert");
  function set(on){text.classList.toggle("vertical",on);btn.setAttribute("aria-pressed",on?"true":"false");}
  try{set(localStorage.getItem(KEY)==="1");}catch(e){}
  btn.addEventListener("click",function(){var on=!text.classList.contains("vertical");set(on);try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}});
  function toast(msg){var d=document.createElement("div");d.className="toast";d.textContent=msg;document.body.appendChild(d);setTimeout(function(){d.remove();},2200);}
  document.getElementById("share").addEventListener("click",function(){
    var url=location.href.split("#")[0],title=document.title;
    if(navigator.share){navigator.share({title:title,url:url}).catch(function(){});return;}
    if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){toast("網址已複製");},function(){prompt("複製這個網址",url);});}
    else prompt("複製這個網址",url);
  });
})();
"""

def seal(name: str) -> str:
    """名號的方印（陰刻）：四字兩行兩列、其餘一直行，右行先讀。web/app.js 的 zhuanSeal 同一條算法。"""
    chars = list(name)[:6]
    n = len(chars)
    cols = 2 if n >= 4 else 1
    rows = -(-n // cols)
    cell = 40 / max(rows, cols)
    glyphs = "".join(
        f'<text x="{46 - (k // rows + 0.5) * (40 / cols):.1f}" y="{6 + (k % rows + 0.5) * (40 / rows):.1f}" font-size="{cell * 0.86:.1f}">{escape(ch)}</text>'
        for k, ch in enumerate(chars)
    )
    return (f'<svg class="zh-seal" viewBox="0 0 52 52" role="img" aria-label="{escape(name)}"><rect x="2" y="2" width="48" height="48" rx="3"/>'
            f'<rect class="rim" x="5" y="5" width="42" height="42" rx="1.5"/>{glyphs}</svg>')


def head(title: str, sub: str) -> str:
    """篇名那一塊（web/app.js 的 zhuanHead 同一份標記）。"""
    return (f'<header class="zh-head"><div class="zh-orn" aria-hidden="true">{"<i></i>" * 6}</div>'
            f'<div class="zh-label" style="--slip-size:{slip_size(title)}px"><h1 class="zh-title">{escape(title)}</h1></div>'
            f'<p class="zh-sub">{escape(sub)}</p></header>')


def slip_size(title: str) -> int:
    """題簽的字級：篇名的字數越多字越小，一律排進一條直書的題簽（四字以內 30px）。web/app.js 的 slipSize 同一條算法。"""
    return min(30, int(176 / len(title) / 1.3))


def page(row: dict, scenario: str, url: str, image: str) -> str:
    """一篇公開的傳。row 是 biographies 的一列（WorldStateStore.biography_by_code）；url 是這一頁的網址，image 是題簽圖的網址。"""
    name = row["name"]
    title = biography.title(name)
    paras = [p for p in row["text"].split("\n\n") if p.strip()]
    lead = biography.lead(row["text"])
    body = "".join(
        f'<p class="{"ping" if p.startswith("評曰") else ""}">{escape(p)}</p>' for p in paras
    )
    sub = f"天下大勢・第 {row['season']} 季・{scenario}"
    meta = "".join(
        f'<meta property="{k}" content="{escape(v)}">'
        for k, v in (("og:type", "article"), ("og:site_name", "天下大勢"), ("og:title", title), ("og:description", lead),
                     ("og:url", url), ("og:image", image), ("og:image:width", "1200"), ("og:image:height", "630"))
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{escape(title)}・天下大勢</title><meta name="description" content="{escape(lead)}"><meta name="robots" content="noindex">
{meta}<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="/static/zhuan.css"><style>{CSS}</style></head>
<body class="zh zh-bamboo">{head(title, sub)}
<div class="zh-tools"><button id="vert" aria-pressed="false">直書</button><button id="share">分享</button></div>
<main class="zh-body"><article class="zh-text">{body}</article><div class="zh-seals">{seal(name)}</div></main>
<footer>這是《天下大勢》裡一位江湖人物的列傳。<br><a href="/">也去江湖走一遭 ›</a></footer>
<script>{SCRIPT}</script></body></html>"""


def missing() -> str:
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>查無此傳・天下大勢</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/static/zhuan.css"><style>{CSS}</style></head>
<body class="zh zh-bamboo"><main class="zh-body" style="padding-top:20vh"><article class="zh-text"><p>史館裡查無此傳——也許作者已經收回，或是網址抄錯了。</p></article></main>
<footer><a href="/">回到江湖 ›</a></footer></body></html>"""
