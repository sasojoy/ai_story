"""異聞兩個內容檔的驗證（設計 3.1、3.3）。check(content, openings, lines) 回 (硬擋, 只警告)；check_content 只把硬擋交給 need。
句數少於 season_cap 只警告；到了 season_cap 句才硬擋「六種每一種至少三句」（不然有的地點永遠撞不見），不到只警告。"""
from __future__ import annotations

import json

from tianxia.core.content_base import NUMBER_IN_TEXT
from tianxia.zh import to_traditional

from . import rules

TITLE_MAX, HOOK_MAX, GUESS_MAX, PLACE_WORD_MAX, THING_WORD_MAX = 8, 60, 14, 6, 4
PER_KIND = 3
FORBIDDEN = ("假人", "機器人", "bot")


def _text_problems(where: str, text: str, limit: int | None, names: list[str]) -> list[str]:
    out = []
    if not str(text).strip():
        out.append(f"{where}：空白")
        return out
    if limit is not None and len(text) > limit:
        out.append(f"{where}：超過 {limit} 字（「{text[:12]}」）")
    if to_traditional(text) != text:
        out.append(f"{where}：只能用繁體中文（「{text[:12]}」）")
    if NUMBER_IN_TEXT.search(text):
        out.append(f"{where}：不能寫阿拉伯數字（「{text[:12]}」）")
    for name in names:
        if name and name in text:
            out.append(f"{where}：不能出現大勢人物的名字「{name}」")
    return out


def check(content, openings: list[dict], lines: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    names = [ch.name for ch in content.characters.values()] if content is not None else []
    cap = content.config.yiwen.season_cap if content is not None else 30
    seen: set[str] = set()
    per_kind = dict.fromkeys(rules.KINDS, 0)
    for i, o in enumerate(openings):
        oid = str(o.get("id", ""))
        where = f"yiwen_openings.json 第 {i + 1} 句（{oid}）"
        if not oid or not oid.isascii() or not oid.replace("_", "").isalnum():
            errors.append(f"{where}：id 只能是英數")
        if oid in seen:
            errors.append(f"{where}：id 重複")
        seen.add(oid)
        kinds = o.get("kinds") or []
        if not 1 <= len(kinds) <= 3 or any(k not in rules.KINDS for k in kinds):
            errors.append(f"{where}：kinds 要是 {'、'.join(rules.KINDS)} 之中一到三個")
        for k in kinds:
            if k in per_kind:
                per_kind[k] += 1
        errors += _text_problems(f"{where} title", str(o.get("title", "")), TITLE_MAX, names)
        errors += _text_problems(f"{where} hook", str(o.get("hook", "")), HOOK_MAX, names)
        guesses = o.get("guesses") or []
        if len(guesses) != 3:
            errors.append(f"{where}：guesses 要三個")
        for g in guesses:
            errors += _text_problems(f"{where} guesses", str(g), GUESS_MAX, names)
        errors += _text_problems(f"{where} place_word", str(o.get("place_word", "")), PLACE_WORD_MAX, names)
        errors += _text_problems(f"{where} thing_word", str(o.get("thing_word", "")), THING_WORD_MAX, names)
        if o.get("frame"):
            errors += _text_problems(f"{where} frame", str(o["frame"]), HOOK_MAX, names)
    if len(openings) < cap:
        warns.append(f"yiwen_openings.json：只有 {len(openings)} 句，少於一季 {cap} 則")
    short = [rules.KINDS[k] for k, n in per_kind.items() if n < PER_KIND]
    if short:
        msg = f"yiwen_openings.json：{'、'.join(short)}不到 {PER_KIND} 句"
        (errors if len(openings) >= cap else warns).append(msg)
    for group, need in rules.LINE_GROUPS.items():
        got = lines.get(group) or []
        if len(got) < need:
            errors.append(f"yiwen_lines.json {group}：至少 {need} 句（現在 {len(got)}）")
        slots = rules.LINE_SLOTS.get(group.partition(".")[0], set())
        for text in got:
            where = f"yiwen_lines.json {group}"
            errors += _text_problems(where, str(text), None, [])
            used = set(rules.SLOT.findall(str(text)))
            if used - slots:
                errors.append(f"{where}：填空只能用 {sorted(slots)}（「{text[:12]}」）")
            filled = rules.fill(str(text), **dict.fromkeys(slots, "甲"))
            if rules.SLOT.search(filled):
                errors.append(f"{where}：填空填不進去（「{text[:12]}」）")
            if any(word in str(text) for word in FORBIDDEN):
                errors.append(f"{where}：不能寫「假人」「機器人」這類字")
    return errors, warns


def check_content(content, need) -> None:
    errors, _ = check(content, load(rules.FILES["openings"]), rules.lines())
    for problem in errors:
        need(False, problem)


def load(path) -> list[dict]:
    """開場檔照檔裡的樣子讀成陣列（重複的 id 不併掉，驗得出來）。"""
    with open(path, encoding="utf-8") as fh:
        return list(json.load(fh).get("openings", []))
