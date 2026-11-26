"""俠客頁重排送給頁面的那一格（main.xiake）。

排法全在網頁（web/xiake.js）；資料都是 /api/main 與 /api/menxia 原本就有的。這裡只多給一樣：
- faces：同伴的立繪（web/img/figures/full/<人物>.webp 有圖才給；同伴那一塊排成立繪方格，沒有圖的網頁照名字第一個字畫）。
"""
from __future__ import annotations

from pathlib import Path

from tianxia import roster  # 共用規則層：名冊的順序（本人、同伴、部下）

WEB = Path(__file__).resolve().parents[3] / "web"


def face(cid: str) -> str | None:
    return f"/static/img/figures/full/{cid}.webp" if (WEB / "img" / "figures" / "full" / f"{cid}.webp").is_file() else None


def status(ctx) -> dict:
    out: dict = {"on": True}
    faces = {}
    for _label, key in roster.roster_lines(ctx.state, ctx.content, ctx.world):
        src = face(key) if key in ctx.content.characters else None
        if src:
            faces[key] = src
    if faces:
        out["faces"] = faces
    return out
