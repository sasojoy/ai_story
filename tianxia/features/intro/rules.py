"""開局前導的規則（純函式）：讀這一包的內容檔、新角色要不要先看畫本、記看過、畫本給網頁的樣子、內容檢查。

要不要看（pending）：開關開著、還停在城門口三選一（核心服務 ctx._opening_pending，主人新手引導）、身上沒有「看過」旗標。
看過記在 PlayerState.flags（SEEN），不另開欄位；換季跟著新角色重來，可是新一季城門口那一幕也會再來一次，照舊不再自動播
（旗標每季清掉時，新角色站到城門口還沒看過，會再播一次；Joy 要的是「新玩家」，換季重看一次可以從設定跳過）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / "content" / "intro.json"
WEB_IMG = HERE.parents[2] / "web" / "img"
SEEN = "看過:開場"
MAX_SECONDS = 60.0  # Joy 2026-11-10「想壓在60秒內」


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def pending(ctx) -> bool:
    """這個角色現在要先看畫本嗎（開關由呼叫的人先問）。"""
    return ctx._opening_pending() and SEEN not in ctx.state.player.flags


def mark_seen(ctx) -> list[str]:
    ctx.state.player.flags.add(SEEN)
    return []


def book(content) -> dict:
    """給網頁的畫本：圖換成 /static/img/ 的網址、人物補上名字。"""
    data = load()
    scenes = []
    for s in data["scenes"]:
        figs = [{"name": content.characters[f["id"]].name, "tag": f["tag"], "side": f["side"],
                 "image": f"/static/img/figures/full/{f['id']}.webp"} for f in s.get("figures", []) if f["id"] in content.characters]
        scenes.append({"image": f"/static/img/{s['image']}", "pan": s["pan"], "seconds": s["seconds"],
                       "lines": s["lines"], "cry": s.get("cry", []), "figures": figs})
    return {"scenes": scenes, "go": data["go"], "skip": data["skip"], "again": data["again"], "replay": data["replay"]}


def check(content, data: dict | None = None) -> list[str]:
    data = load() if data is None else data
    out: list[str] = []
    scenes = data.get("scenes") or []
    if not scenes:
        out.append("開局前導：一幕都沒有")
    total = sum(float(s.get("seconds", 0)) for s in scenes)
    if total > MAX_SECONDS:
        out.append(f"開局前導：加起來 {total:g} 秒，超過 {MAX_SECONDS:g} 秒")
    for n, s in enumerate(scenes, 1):
        if not (WEB_IMG / s.get("image", "")).is_file():
            out.append(f"開局前導第 {n} 幕：找不到圖 web/img/{s.get('image')}")
        if not s.get("lines") or not all(isinstance(x, str) and x for x in s["lines"]):
            out.append(f"開局前導第 {n} 幕：沒有字")
        if len(s.get("pan", [])) != 2:
            out.append(f"開局前導第 {n} 幕：pan 要兩個數")
        if len(s.get("figures", [])) > 2:
            out.append(f"開局前導第 {n} 幕：人物最多兩位")
        for f in s.get("figures", []):
            # 人物表對不上的不擋（測試內容的人物表只有幾個人）：book 不放那一位；正式內容的四位由測試鎖
            if not (WEB_IMG / "figures" / "full" / f"{f.get('id')}.webp").is_file():
                out.append(f"開局前導第 {n} 幕：{f['id']} 沒有立繪")
            if f.get("side") not in ("l", "r"):
                out.append(f"開局前導第 {n} 幕：{f.get('id')} 的 side 要是 l 或 r")
    for key in ("go", "skip", "again", "replay"):
        if not data.get(key):
            out.append(f"開局前導：少了 {key} 的字")
    return out
