"""新手引導包的內容檢查（掛鉤 check_content，content.validate 的 check_features 那一行叫；關著的包照驗）。

碰到才說（content/hints.json）那一塊原本寫在 tianxia/content.py 的 validate 裡；核心不准 import 包（content.py 原本 import hints），全部拆包
第 22 批搬進這裡，句子與檢查的順序照抄。入伍段（tutorial.json 的 enlist）、開局（opening.json）那兩塊不 import 引導的模組，照舊留在 content.py。
"""
from __future__ import annotations

from collections.abc import Callable

from tianxia.models import Content


def check_hints(c: Content, need: Callable[[bool, str], None]) -> None:
    from . import hints as hint_rules  # noqa: PLC0415
    from tianxia.zh import to_traditional  # noqa: PLC0415

    faction_ids = [f.id for f in c.scenario.factions]
    # ── 碰到才說（新手引導計畫三）：id 不重複、只能是設計 5.2 的十八條（hints.KNOWN）；師父的條要有 text、引薦人的條要有 texts，
    # texts 的鍵是劇本的陣營、每一句都不是空的；寫反了（師父的條寫 texts、引薦人的條寫 text）多半是填錯欄位，載入時就報錯 ──
    need(bool(c.hints.head.strip()), "hints.json：head 不能是空的（師父那幾條框上寫的字）")
    hint_ids: set[str] = set()
    for hint in c.hints.hints:
        where = f"hints.json：{hint.id}"
        need(hint.id not in hint_ids, f"{where} 重複")
        hint_ids.add(hint.id)
        need(hint.id in hint_rules.KNOWN, f"{where} 不認得（只認設計 5.2 的十八條與 h_bond，見 hints.KNOWN）")
        if hint.by == "mentor":
            need(bool(hint.text.strip()), f"{where}：師父的提示要有 text")
            need(not hint.texts and not hint.drifter, f"{where}：師父的提示不寫 texts、drifter（那是引薦人的提示才有的）")
        else:
            need(bool(hint.texts), f"{where}：引薦人的提示要有 texts（陣營 id → 那一位說的話）")
            need(not hint.text, f"{where}：引薦人的提示不寫 text（寫在 texts 裡，散人版寫 drifter）")
            need(not hint.season_one, f"{where}：引薦人的提示不寫 season_one（第一季那一句只有師父的條有）")
            need(not hint.explore_one, f"{where}：引薦人的提示不寫 explore_one（出門探索那一句只有師父的條有）")
        for faction_id, line in hint.texts.items():
            need(faction_id in faction_ids, f"{where}：texts 有不是劇本陣營的 {faction_id}")
            need(bool(line.strip()), f"{where}：texts 的 {faction_id} 是空的")
        for faction_id, line in hint.allied.items():  # 豪強分屬兩軍的季另一版：只換 texts 裡有的那一位說的話
            need(faction_id in hint.texts, f"{where}：allied 的 {faction_id} 在 texts 裡沒有")
            need(bool(line.strip()) and to_traditional(line) == line, f"{where}：allied 的 {faction_id} 要是繁體、不能是空的")
        # 句子裡的 {名字} 只能是設定裡有的數（hints.values，explain-1）：寫錯名字的話框上會留著大括號
        for line in (hint.text, hint.drifter, hint.season_one, hint.explore_one, *hint.texts.values(), *hint.allied.values()):
            bad = hint_rules.unknown(c, line)
            need(not bad, f"{where}：不認得的 {{{'}、{'.join(bad)}}}（只認 {sorted(hint_rules.values(c))}）")
