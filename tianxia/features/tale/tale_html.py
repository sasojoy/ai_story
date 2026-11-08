"""戰記頁（Joy 2026-11-04「戰記應該要可以分享，讓我們的用戶去吸引其他人進來玩，考慮讓他獨立一頁，做漂亮一些」）。

伺服器直接吐一整頁 HTML（同 zhuan_html.py 公開的傳）：
- 公開的分享頁 `/zhanji/<代碼>`：不用登入，帶 Open Graph（LINE、FB 只讀伺服器回的 HTML 抓預覽），底下一塊招攬新人。
- 遊戲裡戰報頁的「戰記 ›」疊一層 iframe 開同一頁（`?in=1`）：頂條左邊「‹ 返回」叫遊戲收起這一層，不畫招攬。
標記只有這一份；樣子在 web/tale.css。文字一律跳脫。名錄只寫名號與陣營，不寫帳號，也不寫誰是假人（戰記本來就不知道）。
只 import 標準函式庫。
"""
from __future__ import annotations

from html import escape

CN = "零一二三四五六七八九十"
TOC_NO = "壹貳參肆伍陸柒捌玖拾"
ACT_NO = "第{n}回"
SIDE_CLASS = {"guan": "guan", "huang": "huang"}  # 陣營 id → 顏色（官軍石青、黃巾金，同戰局條）；其餘（守軍）灰
CAST_NOTE = "這一場在場的人"
COLOPHON = "說書人記"
CTA_TITLE = "下一場仗，你也可以在場"  # 待 joy 潤
CTA_TEXT = "《天下大勢》是一款文字武俠。每一場決戰都由在場的人一回合一回合打出來，再由說書人寫成戰記。"  # 待 joy 潤
CTA_GO = "進入江湖"
SHARE = "分享"
BACK = "‹ 返回"


def cn_count(n: int) -> str:
    """一到十寫中文，十一到九十九寫「十一」「二十三」，再多寫阿拉伯數字（標題列的小字）。"""
    if 0 <= n <= 10:
        return CN[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return f"{'' if tens == 1 else CN[tens]}十{CN[ones] if ones else ''}"
    return str(n)


def side_class(view: dict, name: str) -> str:
    """名字（官軍、黃巾軍、守軍）→ 顏色；照這一場兩邊的對照，認不得是空的（灰）。"""
    for side in view.get("sides") or []:
        if side.get("name") == name:
            return side.get("cls", "")
    return ""


def paras(text: str, first: bool) -> str:
    lines = [x.strip() for x in str(text or "").split("\n") if x.strip()]
    return "".join(f'<p{" class=\"first\"" if first and i == 0 else ""}>{escape(x)}</p>' for i, x in enumerate(lines))


def act_html(view: dict, act: dict, i: int) -> str:
    no = act.get("no") or ACT_NO.format(n=cn_count(i + 1))
    when = f'<p class="zj-when">{escape(act["banner"])}</p>' if act.get("banner") else ""
    body: list[str] = []
    for k, scene in enumerate(act.get("scenes") or []):
        if scene.get("head"):
            body.append(f'<h3>{escape(scene["head"])}</h3>')
        body.append(paras(scene.get("text", ""), first=k == 0))
        said = scene.get("said")
        if said:
            who = escape(said.get("who", "")) + (f'・{escape(said["side"])}' if said.get("side") else "")
            body.append(f'<blockquote class="zj-said"><q>{escape(said.get("line", ""))}</q>'
                        f'<cite><span class="zj-dot {side_class(view, said.get("side", ""))}"></span>{who}</cite></blockquote>')
    return (f'<section class="zj-act" id="act{i + 1}"><header class="zj-act-h"><span class="zj-no">{escape(no)}</span>'
            f'<h2>{escape(act.get("title", ""))}</h2>{when}</header>{"".join(body)}</section>')


def toc_html(view: dict) -> str:
    acts = view.get("acts") or []
    if len(acts) < 2:
        return ""
    links = []
    for i, act in enumerate(acts):
        mark = act.get("no") if act.get("no") and not act["no"].startswith("第") else TOC_NO[i % len(TOC_NO)]
        links.append(f'<a href="#act{i + 1}"><i>{escape(mark)}</i>{escape(act.get("title", ""))}</a>')
    if view.get("cast"):
        links.append(f'<a href="#cast"><i>錄</i>{CAST_NOTE}</a>')
    return f'<nav class="zj-toc" aria-label="目錄">{"".join(links)}</nav>'


def cast_html(view: dict) -> str:
    cast = view.get("cast") or []
    if not cast:
        return ""
    def row(c: dict) -> str:
        side = c.get("side") or ""
        small = f"<small>{escape(side)}</small>" if side else ""
        return (f'<li><i class="zj-chop {side_class(view, side)}">{escape((c.get("name") or "?")[0])}</i>'
                f'<b>{escape(c.get("name", ""))}{small}</b><span>{escape(c.get("line", ""))}</span></li>')
    rows = "".join(row(c) for c in cast)
    return f'<section class="zj-cast" id="cast"><h2>名錄</h2><p>{CAST_NOTE}</p><ul>{rows}</ul></section>'


def result_html(view: dict) -> str:
    sides = view.get("sides") or []
    facts = [f"<span><b>{cn_count(len(view.get('acts') or []))}</b>回</span>"]
    if view.get("present"):
        facts.append(f"<span><b>{cn_count(int(view['present']))}</b>人在場</span>")
    if view.get("when"):
        facts.append(f"<span>{escape(view['when'])}</span>")
    band = ""
    if len(sides) >= 2:
        def side(s: dict) -> str:
            won = " won" if s.get("won") else ""
            return f'<div class="zj-side {s.get("cls", "")}{won}"><b>{escape(s.get("name", ""))}</b></div>'
        band = f'<div class="zj-sides">{side(sides[0])}<div class="zj-stamp">{escape(view.get("stamp", ""))}</div>{side(sides[1])}</div>'
    return f'<div class="zj-result">{band}<p class="zj-facts">{"".join(facts)}</p></div>'


def page(view: dict, *, url: str, image: str, embedded: bool = False) -> str:
    """一篇戰記。view 是 routes.tale_page_view 拼好的那一份（標題、封面、兩邊、幾幕、名錄……）；url 是分享網址，image 是預覽圖網址。
    embedded：遊戲裡那一層（?in=1）。"""
    title = view["title"]
    lead = view.get("lead") or view.get("sub") or ""
    meta = "".join(
        f'<meta property="{k}" content="{escape(v)}">'
        for k, v in (("og:type", "article"), ("og:site_name", "天下大勢"), ("og:title", f"{title}・天下大勢"), ("og:description", lead),
                     ("og:url", url), ("og:image", image))
    )
    left = (f'<button class="zj-back" id="zj-back" type="button">{BACK}</button>' if embedded else '<a href="/">天下大勢</a>')
    bar = f'<div class="zj-bar">{left}<button class="zj-share" id="zj-share" type="button" data-url="{escape(url)}">{SHARE}</button></div>'
    acts = '<div class="zj-rule"></div>'.join(act_html(view, a, i) for i, a in enumerate(view.get("acts") or []))
    cta = ("" if embedded else
           f'<section class="zj-cta"><h2>{CTA_TITLE}</h2><p>{CTA_TEXT}</p><div class="row"><a class="zj-btn" href="/">{CTA_GO}</a></div></section>')
    sub = f'<p class="zj-sub">{escape(view["sub"])}</p>' if view.get("sub") else ""
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{escape(title)}・天下大勢</title><meta name="description" content="{escape(lead)}"><meta name="robots" content="noindex">
{meta}<meta name="twitter:card" content="summary_large_image"><meta name="theme-color" content="#16120e">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="/static/tale.css"></head>
<body class="zj{' in' if embedded else ''}"><div class="zj-page">{bar}
<header class="zj-hero"><img src="{escape(view.get('cover', ''))}" alt="">
<div class="zj-hero-text"><div class="zj-kicker">{escape(view.get('kicker', ''))}</div>
<div class="zj-title"><h1>{escape(view.get('battle_name') or title)}</h1><span class="zj-seal">戰記</span></div>{sub}</div></header>
{result_html(view)}{toc_html(view)}<main>{acts}</main>{cast_html(view)}
<p class="zj-colophon"><span>{COLOPHON}</span><i>天下<br>大勢</i></p>{cta}</div>
<script src="/static/tale_page.js"></script></body></html>"""


def missing() -> str:
    return """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>查無此戰記・天下大勢</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/static/tale.css"></head>
<body class="zj"><div class="zj-page"><p class="zj-missing">史館裡查無這一篇戰記，也許網址抄錯了。<br><a href="/">回到江湖 ›</a></p></div></body></html>"""
