"""長篇奇事的內容產生器共用工具：段落、選項、事件、把一條線寫進 content/。"""
import json
from pathlib import Path


def P(*paras: str) -> str:
    """段落用空行接起來（網頁照 Markdown 畫成一段一段）。"""
    return "\n\n".join(x.strip() for x in paras if x and x.strip())


def step(line: str, marks: dict | None = None, go: str | None = None, keepsake: str | None = None, drop: str | None = None) -> dict:
    out = {"line": line}
    if marks:
        out["marks"] = marks
    if go:
        out["go"] = go
    if keepsake:
        out["keepsake"] = keepsake
    if drop:
        out["keepsake_drop"] = drop
    return out


def eff(text: str, story: dict | None = None, **extra) -> dict:
    out = {"text": text}
    out.update(extra)
    if story:
        out["story"] = story
    return out


def choice(text: str, effect: dict, *, check: tuple[str, int] | None = None, fail: dict | None = None,
           combat: str | None = None, condition: dict | None = None) -> dict:
    out = {"text": text}
    if condition:
        out["condition"] = condition
    if check:
        out["check"] = {"stat": check[0], "difficulty": check[1]}
    if combat:
        out["combat"] = combat
    out["effect"] = effect
    if fail is not None:
        out["fail_effect"] = fail
    return out


def free(prompt: str, effect: dict, fail: dict | None = None, stat: str = "wis") -> dict:
    return {"prompt": prompt, "stat": stat, "effect": effect, "fail_effect": fail if fail is not None else effect}


def event(eid: str, title: str, image: str, text: str, choices: list, free_text: dict | None = None) -> dict:
    out = {"id": eid, "image": image, "title": title, "actions": [], "text": text, "choices": choices}
    if free_text:
        out["free_text"] = free_text
    return out


def write(root: Path, file_name: str, events: list, line: dict, squads: list | None = None) -> None:
    """事件寫成 content/events/<file_name>；線換掉 storylines.json 裡同 id 的那一條（沒有就加在後面）；隊伍同理。"""
    (root / "events" / file_name).write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path = root / "storylines.json"
    lines = json.loads(path.read_text(encoding="utf-8"))
    lines = [x for x in lines if x["id"] != line["id"]] + [line]
    path.write_text(json.dumps(lines, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if squads:
        path = root / "squads.json"
        have = json.loads(path.read_text(encoding="utf-8"))
        ids = {s["id"] for s in squads}
        have = [s for s in have if s["id"] not in ids] + squads
        path.write_text(json.dumps(have, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
