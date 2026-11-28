"""門派論劍內容檔的驗證（features/lunjian/content/lunjian.json）：師兄、試劍客都有名字、有一句，名字不重複（門派不認得的照 generic_elders，測試內容的門派不一樣，不擋）；
禮匣的種類是認得的、權重不是負的。"""
from __future__ import annotations

from . import rules

KINDS = ("mat", "legend", "coin", "move")


def problems(content, table: dict) -> list[str]:
    out = []
    names: set[str] = set()
    groups = [(f"elders.{k}", v) for k, v in table.get("elders", {}).items()]
    groups += [("generic_elders", table.get("generic_elders", [])), ("guests", table.get("guests", []))]
    for where, rows in groups:
        if not rows:
            out.append(f"lunjian.json {where} 是空的")
        for i, r in enumerate(rows):
            name, line = r.get("name", ""), r.get("line", "")
            if not name or not line:
                out.append(f"lunjian.json {where}[{i}] 要有 name 與 line")
            if name in names:
                out.append(f"lunjian.json {where}[{i}] 名字「{name}」重複")
            names.add(name)
    for k in ("box", "top_box"):
        for i, row in enumerate(getattr(content.config.lunjian, k)):
            if len(row) != 3 or row[0] not in KINDS or int(row[1]) <= 0 or float(row[2]) < 0:
                out.append(f"Config.lunjian.{k}[{i}] 要是 [種類（{'、'.join(KINDS)}）, 數量 > 0, 權重 ≥ 0]")
    return out


def check_content(content, need) -> None:
    for p in problems(content, rules.table()):
        need(False, p)
