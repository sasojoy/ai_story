"""content/personas.json 的檢查（功能包的 check_content）：人物要在、一人最多三條、id 與兩頭的叫法不重複、叫法不是 NONE、五段都有字。"""
from __future__ import annotations

from . import rules

MAX_AXES = 3


def check(content, need) -> None:
    for cid, rows in content.personas.items():
        where = f"personas.json 的 {cid}"
        need(cid in content.characters, f"{where}：人物表沒有這個人")
        need(1 <= len(rows) <= MAX_AXES, f"{where}：一人一到 {MAX_AXES} 條性子（現在 {len(rows)} 條）")
        ids = [a.id for a in rows]
        need(len(ids) == len(set(ids)), f"{where}：性子 id 重複")
        ends = [e for a in rows for e in a.ends]
        need(len(ends) == len(set(ends)), f"{where}：兩頭的叫法重複（模型照叫法歸類，要分得開）")
        need(rules.NONE not in ends, f"{where}：叫法不能是 {rules.NONE}")
        for a in rows:
            for i, st in enumerate(a.stages):
                need(bool(st.text.strip()) and bool(st.short.strip()), f"{where}.{a.id} 第 {i} 段：text、short 都要有字")
