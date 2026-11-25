"""/terms、/privacy 兩頁的 HTML（不用登入、手機好讀；顏色照 web/style.css 的紙與墨，跟著系統的深色模式）。"""
from __future__ import annotations

from html import escape

from . import rules

STYLE = """
:root { --paper:#f4ede0; --card:#fbf7ef; --ink:#2a241d; --ink-2:#6b6155; --line:#ddd1bc; --accent:#a8322a; }
@media (prefers-color-scheme: dark) { :root { --paper:#1d1915; --card:#26211b; --ink:#ece3d3; --ink-2:#b3a691; --line:#3d352b; --accent:#d2574a; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif; }
main { max-width:720px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-family:"Noto Serif TC","Songti TC","PMingLiU",serif; font-size:26px; margin:8px 0 4px; }
.meta { color:var(--ink-2); font-size:14px; margin:0 0 20px; }
nav { display:flex; gap:16px; font-size:15px; margin-bottom:8px; flex-wrap:wrap; }
nav a { color:var(--accent); text-decoration:none; }
nav a[aria-current] { color:var(--ink); font-weight:600; }
section { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin:12px 0; }
h2 { font-size:17px; margin:0 0 6px; }
p { margin:6px 0; }
footer { color:var(--ink-2); font-size:13px; margin-top:24px; }
.rating { display:flex; gap:12px; align-items:center; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 14px; margin:12px 0; }
.rating b { flex:none; display:grid; place-items:center; width:52px; height:52px; border-radius:10px; background:#e0a526; color:#2a241d; font-size:17px; line-height:1.1; text-align:center; }
.rating ul { margin:0; padding:0; list-style:none; font-size:13px; color:var(--ink-2); line-height:1.6; }
"""


def rating_html(data: dict) -> str:
    """遊戲分級標識與警語（遊戲軟體分級管理辦法第 11～13 條：起始網頁旁明顯標示、不小於 45×45 像素）。"""
    m = data["rating_mark"]
    lines = "".join(f"<li>{escape(x)}</li>" for x in [f"{data['rating']}：{m['age']}"] + list(m["lines"]))
    return f'<div class="rating" role="note" aria-label="遊戲分級"><b>{escape(m["short"])}</b><ul>{lines}</ul></div>'


def page(doc: str, data: dict) -> str:
    d = data["docs"][doc]
    c = data["company"]
    nav = "".join(
        f'<a href="/{key}"{" aria-current=\"page\"" if key == doc else ""}>{escape(data["docs"][key]["title"])}</a>' for key in rules.DOCS
    ) + '<a href="/">回到遊戲</a>'
    body = "".join(
        f'<section><h2>{escape(s["h"])}</h2>{"".join(f"<p>{escape(rules.fill(p, data))}</p>" for p in s["p"])}</section>' for s in d["sections"]
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>天下大勢 {escape(d["title"])}</title><style>{STYLE}</style></head>
<body><main><nav>{nav}</nav><h1>{escape(d["title"])}</h1>
<p class="meta">最後更新 {escape(d["updated"])}・版本 {escape(data["version"])}</p>{rating_html(data)}{body}
<footer>{escape(c["name"])}・統編 {escape(c["tax_id"])}・{escape(c["address"])}・{escape(c["email"])}</footer></main></body></html>"""
