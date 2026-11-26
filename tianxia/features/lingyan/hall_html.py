"""凌煙閣的頁（/lingyan）：伺服器直接吐一整頁 HTML（同列傳的公開頁 zhuan_html，不經過 web/app.js）。

樣子照介面設計規範：色票一律讀 /static/style.css 的 :root（深色模式自動跟著換），名字楷書、說明 sans、點得到的 44px。
一季一卷：卷軸頭尾兩根軸，卷裡一個人一格（名號方印、名號、第幾次上閣的朱絲、事蹟朱印、評曰）。最新的兩卷攤開，更早的收成一行。
文字一律跳脫。只 import 標準函式庫與這一包。
"""
from __future__ import annotations

from html import escape

from .hall import Cell, Scroll

NUM = "〇一二三四五六七八九"


def cn_number(n: int) -> str:
    """季數寫成中文（1～99）：十、十一、二十、二十三。"""
    if n < 10:
        return NUM[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else NUM[tens]) + "十" + (NUM[ones] if ones else "")


def times_text(times: int) -> str:
    return f"{cn_number(times)}入凌煙" if times >= 2 else ""  # 待 joy 潤


def seal(name: str) -> str:
    """名號的方印（陰刻）：四字兩行兩列、其餘一直行，右行先讀（列傳包 zhuan_html.seal 同一條算法；包不 import 別包，這裡另寫一份）。"""
    chars = list(name)[:6]
    n = len(chars)
    cols = 2 if n >= 4 else 1
    rows = -(-n // cols)
    cell = 40 / max(rows, cols)
    glyphs = "".join(
        f'<text x="{46 - (k // rows + 0.5) * (40 / cols):.1f}" y="{6 + (k % rows + 0.5) * (40 / rows):.1f}" font-size="{cell * 0.86:.1f}">{escape(ch)}</text>'
        for k, ch in enumerate(chars)
    )
    return (f'<svg class="ly-seal" viewBox="0 0 52 52" aria-hidden="true"><rect x="2" y="2" width="48" height="48" rx="3"/>'
            f'<rect class="rim" x="5" y="5" width="42" height="42" rx="1.5"/>{glyphs}</svg>')


CSS = """
body{background:var(--paper);color:var(--ink);margin:0;min-height:100vh;padding:0 0 env(safe-area-inset-bottom,0)}
.ly{max-width:640px;margin:0 auto;padding:0 16px 40px}
.ly-top{display:flex;align-items:center;min-height:52px}
.ly-top a{display:inline-flex;align-items:center;min-height:44px;color:var(--ink-2);font:600 14px var(--sans);text-decoration:none}
.ly-hero{position:relative;height:200px;margin:0 -16px 4px;overflow:hidden}
.ly-hero img{display:block;width:100%;height:100%;object-fit:cover;-webkit-mask-image:linear-gradient(#000 55%,transparent);mask-image:linear-gradient(#000 55%,transparent)}
.ly-plaque{position:absolute;top:18px;right:22px;writing-mode:vertical-rl;padding:14px 8px;border:3px solid #c9a25a;border-radius:4px;
background:linear-gradient(#5b3b22,#3e2716);color:#f1d48a;font:700 26px/1 var(--kai);letter-spacing:.3em;box-shadow:0 3px 10px rgba(0,0,0,.35)}
.ly-lead{margin:0 0 6px;font:400 17px/1.7 var(--kai);color:var(--ink)}
.ly-note{margin:0 0 16px;font:13px/1.6 var(--sans);color:var(--ink-2)}
.ly-live{display:flex;gap:10px;align-items:center;margin:0 0 18px;padding:12px 14px;border:1.5px dashed var(--line);border-radius:12px;
font:15px/1.6 var(--kai);color:var(--ink-2)}
.ly-live b{flex:none;padding:2px 8px;border:2px solid var(--accent);border-radius:3px;color:var(--accent);font:700 14px var(--kai);transform:rotate(-4deg)}
.ly-scroll{position:relative;margin:0 0 22px;padding:22px 14px 20px;background:var(--card);border-radius:4px;box-shadow:var(--shadow)}
.ly-scroll::before,.ly-scroll::after{content:"";position:absolute;left:-8px;right:-8px;height:12px;border-radius:6px;
background:linear-gradient(#8a5a33,#5b3b22 55%,#3e2716)}
.ly-scroll::before{top:-6px}.ly-scroll::after{bottom:-6px}
.ly-sh{display:flex;align-items:baseline;gap:10px;margin:0 0 12px;padding-left:10px;border-left:3px solid var(--ink)}
.ly-sh h2{margin:0;font:700 20px/1.3 var(--kai);letter-spacing:.12em}
.ly-sh small{font:14px/1.4 var(--kai);color:var(--ink-2)}
.ly-cells{display:grid;gap:10px}
.ly-cell{display:grid;grid-template-columns:52px 1fr;gap:12px;padding:12px;background:var(--card-2);border-radius:10px}
.ly-seal{width:52px;height:52px;fill:none}
.ly-seal rect{fill:var(--accent)}.ly-seal .rim{fill:none;stroke:var(--card);stroke-width:1.2}
.ly-seal text{fill:var(--card);font-family:var(--kai);font-weight:700;text-anchor:middle;dominant-baseline:central}
.ly-name{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:0 0 6px}
.ly-name b{font:700 19px/1.3 var(--kai);word-break:break-all}
.ly-times{padding:0 7px;border:1px solid var(--accent);border-radius:2px;color:var(--accent);font:600 12.5px/1.6 var(--kai)}
.ly-honors{display:grid;gap:5px;margin:0;padding:0;list-style:none}
.ly-honors li{display:flex;align-items:baseline;gap:8px;font:13.5px/1.5 var(--sans);color:var(--ink-2)}
.ly-honors li b{flex:none;padding:0 6px;border:1.5px solid var(--accent);border-radius:2px;color:var(--accent);font:700 13.5px/1.5 var(--kai);letter-spacing:.04em}
.ly-ping{display:flex;gap:8px;margin:10px 0 0;padding-top:8px;border-top:1px dashed var(--line)}
.ly-ping .chop{flex:none;display:grid;place-items:center;width:22px;height:22px;border-radius:2px;background:var(--accent);color:var(--card);font:700 13px var(--kai)}
.ly-ping p{margin:0;font:15px/1.6 var(--kai);color:var(--ink)}
.ly-read{display:inline-flex;align-items:center;min-height:44px;margin-top:2px;color:var(--accent);font:600 14px var(--sans);text-decoration:none}
details.ly-old{margin:0 0 12px;background:var(--card);border-radius:10px;box-shadow:var(--shadow)}
details.ly-old>summary{display:flex;align-items:center;gap:10px;min-height:48px;padding:0 14px;cursor:pointer;list-style:none;font:700 17px var(--kai)}
details.ly-old>summary::-webkit-details-marker{display:none}
details.ly-old>summary small{font:400 13px var(--sans);color:var(--ink-2)}
details.ly-old>summary::after{content:"▾";margin-left:auto;color:var(--ink-2);font:13px var(--sans)}
details.ly-old[open]>summary::after{content:"▴"}
details.ly-old .ly-scroll{margin:6px 8px 18px;box-shadow:none}
.ly-empty{margin:8px 0 20px;padding:22px 16px;border:1.5px dashed var(--line);border-radius:12px;text-align:center;font:16px/1.8 var(--kai);color:var(--ink-2)}
.ly-help{margin:20px 0 0}
.ly-help summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font:600 14px var(--sans);color:var(--ink-2)}
.ly-help ul{margin:0;padding:10px 14px 10px 30px;background:var(--card-2);border-radius:10px;font:13.5px/1.8 var(--sans);color:var(--ink-2)}
@media (prefers-color-scheme: dark){.ly-hero img{filter:brightness(.78) saturate(.85)}}
"""

HERO = "/static/img/events/academy.webp"  # 待畫：凌煙閣本身的一張（之後換）
LEAD = "一座不會清的閣。每一季收季那一刻，這一季最出眾的人掛上來，往後每一季都看得到。"  # 待 joy 潤
LIVE = "這一季還在打。收季那一刻，這一季的人掛上閣。"  # 待 joy 潤
EMPTY = "閣裡還空著。<br>這一季收季那一刻，第一卷就掛上來。"  # 待 joy 潤
HELP = (  # 待 joy 潤
    "擂台季末守在第一的、各陣營論功第一的、決戰首功最多的、名人宗師武學善惡五張榜的第一名、這一季第一個練成絕學的，收季時掛上閣。",
    "同一個人一季只佔一格，幾樣事蹟寫在同一格裡；第二次上閣起，名號旁邊多一道朱絲。",
    "列傳公開分享了的，格子裡掛一句評曰，點了讀全篇。",
    "閣裡只寫名號與事蹟，不寫等級與身家。",
)


def cell_html(c: Cell) -> str:
    times = f'<span class="ly-times">{escape(times_text(c.times))}</span>' if c.times >= 2 else ""
    honors = "".join(f"<li><b>{escape(h.label)}</b>{f'<span>{escape(h.deed)}</span>' if h.deed else ''}</li>" for h in c.honors)
    ping = (f'<div class="ly-ping"><span class="chop" aria-hidden="true">評</span><p>{escape(c.verdict)}</p></div>' if c.verdict else "")
    read = f'<a class="ly-read" href="/zhuan/{escape(c.code)}">讀{escape(c.name)}的列傳 ›</a>' if c.code else ""  # 待 joy 潤
    return (f'<article class="ly-cell">{seal(c.name)}<div><p class="ly-name"><b>{escape(c.name)}</b>{times}</p>'
            f'<ul class="ly-honors">{honors}</ul>{ping}{read}</div></article>')


def scroll_html(s: Scroll) -> str:
    ending = f"<small>{escape(s.ending)}</small>" if s.ending else ""
    return (f'<section class="ly-scroll"><div class="ly-sh"><h2>第{cn_number(s.number)}季</h2>{ending}</div>'
            f'<div class="ly-cells">{"".join(cell_html(c) for c in s.cells)}</div></section>')


OPEN = 2  # 最新的幾卷攤開


def page(scrolls: list[Scroll], live: bool, logged_in: bool = True) -> str:
    live_html = f'<div class="ly-live"><b>未掛</b><span>{LIVE}</span></div>' if live and scrolls else ""  # 閣還空著時空框那一句就說了，不寫兩次
    if scrolls:
        shown = "".join(scroll_html(s) for s in scrolls[:OPEN])
        old = "".join(
            f'<details class="ly-old"><summary>第{cn_number(s.number)}季<small>{escape(s.ending)}・{len(s.cells)} 人</small></summary>{scroll_html(s)}</details>'
            for s in scrolls[OPEN:]
        )
        body = shown + old
    else:
        body = f'<div class="ly-empty">{EMPTY}</div>'
    helps = "".join(f"<li>{escape(x)}</li>" for x in HELP)
    back = '<a href="/">‹ 回江湖</a>' if logged_in else '<a href="/">也去江湖走一遭 ›</a>'  # 待 joy 潤
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>凌煙閣・天下大勢</title><meta name="robots" content="noindex">
<meta name="theme-color" content="#f4ede0" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#16130f" media="(prefers-color-scheme: dark)">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=LXGW+WenKai+TC:wght@400;700&display=swap">
<link rel="stylesheet" href="/static/style.css"><style>{CSS}</style></head>
<body><div class="ly"><nav class="ly-top">{back}</nav>
<header class="ly-hero"><img src="{HERO}" alt=""><div class="ly-plaque">凌煙閣</div></header>
<p class="ly-lead">{LEAD}</p>
{live_html}{body}
<details class="ly-help"><summary>？ 誰上得了閣</summary><ul>{helps}</ul></details>
</div></body></html>"""


def missing() -> str:
    """沒登入時那一頁（回 401）：請他先登入。"""
    return """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>凌煙閣・天下大勢</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/static/style.css">
<style>body{background:var(--paper);color:var(--ink)}main{max-width:480px;margin:20vh auto 0;padding:0 16px;text-align:center;font:16px/1.8 var(--kai)}
a{display:inline-flex;align-items:center;min-height:44px;color:var(--accent);font-weight:700}</style></head>
<body><main><p>登入之後才看得到凌煙閣。</p><a href="/">去登入 ›</a></main></body></html>"""  # 待 joy 潤
