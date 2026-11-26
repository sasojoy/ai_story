"""地方大事內容檔的驗證（features/difang/content/difang.json）：三幕都寫了、第一二幕有事件（id 不重複、至少兩個做法）、第三幕一場有對手與打法、做法的屬性是有的、地點在內容裡、繁體不寫阿拉伯數字。"""
from __future__ import annotations

from tianxia.core.content_base import NUMBER_IN_TEXT
from tianxia.zh import to_traditional

from . import rules

STATS = ("str", "agi", "con", "wis")


def _way_texts(where: str, ways: list[dict]) -> list[tuple[str, str]]:
    out = []
    for j, w in enumerate(ways):
        out.append((f"{where}.ways[{j}].label", w.get("label", "")))
        keys = ("hit", "miss") if w.get("stat") else ("line",)
        out += [(f"{where}.ways[{j}].{k}", w.get(k, "")) for k in keys]
    return out


def _texts(a: dict) -> list[tuple[str, str]]:
    out = [("title", a.get("title", "")), ("hook", a.get("hook", ""))]
    for i, x in enumerate(a.get("acts", [])):
        out += [(f"acts[{i}].name", x.get("name", "")), (f"acts[{i}].line", x.get("line", ""))]
        for j, e in enumerate(x.get("events", [])):
            w = f"acts[{i}].events[{j}]"
            out += [(f"{w}.title", e.get("title", "")), (f"{w}.scene", e.get("scene", ""))] + _way_texts(w, e.get("ways", []))
        if i == rules.ACTS - 1:
            out += [(f"acts[{i}].title", x.get("title", "")), (f"acts[{i}].scene", x.get("scene", ""))] + _way_texts(f"acts[{i}]", x.get("ways", []))
    for k in ("done", "failed"):
        out += [(f"{k}.line", a.get(k, {}).get("line", "")), (f"{k}.chronicle", a.get(k, {}).get("chronicle", ""))]
    return out


def problems(content, table: dict[str, dict]) -> list[str]:
    out = []
    regions = {r.id for r in content.map.regions}
    for aid, a in table.items():
        where = f"difang.json {aid}"
        acts = a.get("acts", [])
        if len(acts) != rules.ACTS:
            out.append(f"{where}：要剛好 {rules.ACTS} 幕")
            continue
        ids = [e.get("id") for x in acts[:2] for e in x.get("events", [])]
        if len(ids) != len(set(ids)):
            out.append(f"{where}：事件 id 重複")
        for i, x in enumerate(acts[:2]):
            if not x.get("events"):
                out.append(f"{where}：第{'一二'[i]}幕沒有事件")
            out += [f"{where} {e.get('id')}：做法少於兩個" for e in x.get("events", []) if len(e.get("ways", [])) < 2]
        ways = [w for x in acts[:2] for e in x.get("events", []) for w in e.get("ways", [])]
        if not acts[2].get("foe") or not acts[2].get("ways"):
            out.append(f"{where}：第三幕沒寫對手或打法")
        out += [f"{where}：第三幕的打法要寫屬性" for w in acts[2].get("ways", []) if not w.get("stat")]
        out += [f"{where}：做法的屬性 {w.get('stat')} 不認得" for w in ways + acts[2].get("ways", []) if w.get("stat") and w.get("stat") not in STATS]
        if regions and a.get("place") not in content.locations:
            out.append(f"{where}：地點 {a.get('place')} 不在內容裡")
        out += [f"{where}：大區 {r} 不在輿圖上" for r in a.get("regions", []) if regions and r not in regions]
        for field, text in _texts(a):
            if not str(text).strip():
                out.append(f"{where} {field}：空白")
            elif to_traditional(text) != text:
                out.append(f"{where} {field}：只能用繁體中文")
            elif NUMBER_IN_TEXT.search(text):
                out.append(f"{where} {field}：不能寫阿拉伯數字")
    return out


def check_content(content, need) -> None:
    """正式內容（輿圖上有這幾個大區）才驗地點與大區；測試內容只驗字與三幕。"""
    real = {r.id for r in content.map.regions} >= {r for a in rules.affairs().values() for r in a.get("regions", [])}
    for p in problems(content, rules.affairs()):
        if real or ("地點" not in p and "大區" not in p):
            need(False, p)
