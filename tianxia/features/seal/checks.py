"""玉璽包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

from tianxia.models import Condition, Content
from tianxia.naming import SEAL_CLASH, name_problem


def validate_seal(c: Content, need) -> None:
    """玉璽碎片（玉璽碎片設計 13.4、8.5）：係數都不超過 1（一場最多 cap）；沒有 content/seal.json 可以（碎片關著：時刻表的標記與
    emerge_skill 都不檢查——測試內容沒有混元一氣，預設的 emerge_skill 不能讓它載入失敗）；有就 emerge_skill 認得、剛好七片、名字不重複、
    效果鍵在 Config.seal.effects（改版的 effects 在 Config.seal.revamp.effects）、名字過命名過濾；時刻表不是空的時標 emerge 的剛好一件、標了 seal 的都是決戰。
    天命之爭（玉璽二）：最多一件、是決戰、沒標 seal、有它的戰鬥、mandate_endings 指到交戰兩軍與標了 mandate 的結局；標了 mandate 的結局都有人指。"""
    cfg = c.config.seal
    for label, table in (("side_factor", cfg.side_factor), ("take_share", cfg.take_share)):
        need(all(0 <= v <= 1 for v in table.values()), f"Config.seal.{label}：係數不能超過 1（一場被奪最多 cap）")
    if not c.seal:
        return
    need(cfg.emerge_skill is None or cfg.emerge_skill in c.skills, f"Config.seal.emerge_skill：{cfg.emerge_skill} 不是內容裡的武學")
    need(len(c.seal) == 7, f"content/seal.json：要剛好七片，現在 {len(c.seal)} 片")
    need(len({s.name for s in c.seal.values()}) == len(c.seal), "content/seal.json：七片的名字要不重複")
    for shard in c.seal.values():
        need(shard.effect in cfg.effects, f"content/seal.json：{shard.id} 的效果 {shard.effect} 不在 Config.seal.effects")
        for key in shard.effects:  # 改版的常駐效果（玉璽碎片改版第三章）：開關關著也檢查，打開那一刻不會才發現內容寫錯
            need(key in cfg.revamp.effects, f"content/seal.json：{shard.id} 的改版效果 {key} 不在 Config.seal.revamp.effects")
        problem = name_problem(shard.name, c)
        need(problem in (None, SEAL_CLASH), f"content/seal.json：{shard.id} 的名字「{shard.name}」{problem}")
    acts = [shard.act for shard in c.seal.values() if shard.act is not None]  # 獨門行動（改版第 2 批）：一種只給一片
    need(len(acts) == len(set(acts)), f"content/seal.json：同一種獨門行動只能給一片（{acts}）")
    mandates = c.mandate_timetable  # 天命之爭（玉璽二；8.3、8.5）
    need(len(mandates) <= 1, "時刻表：標 mandate_only 的天命之爭最多一件")
    endings = {e.id: e for e in c.scenario.endings}
    for event in mandates:
        where = f"時刻表 {event.id}（天命之爭）"
        need(event.kind == "showdown" and event.seal is None, f"{where}：天命之爭要是決戰、不能標 seal（它本身不璽動）")
        battle = next((b for b in c.battles.values() if b.timetable_event == event.id), None)
        need(battle is not None, f"{where}：battles.json 要有一筆 timetable_event 是 {event.id} 的戰鬥")
        armies = {f.id for f in battle.factions} if battle is not None else set()
        need(bool(event.mandate_endings) and set(event.mandate_endings) <= armies, f"{where}：mandate_endings 的鍵要是交戰兩軍")
        for side, ending_id in event.mandate_endings.items():
            ending = endings.get(ending_id)
            need(ending is not None and ending.mandate and ending.season_one,
                 f"{where}：{side} 的結局 {ending_id} 要是劇本裡標了 mandate 的第一季結局")
    for ending in c.scenario.endings:
        if ending.mandate:
            need(any(ending.id in e.mandate_endings.values() for e in mandates), f"結局 {ending.id}：標了 mandate 卻沒有天命之爭指到它")
            need(ending.condition == Condition() and not (ending.stance_min or ending.stance_max or ending.stance_top),
                 f"結局 {ending.id}：天命結局不寫條件與態勢（照天命之爭的結果挑）")
    if not c.timetable:
        return
    marked = [e for e in c.timetable if e.seal is not None]
    need(all(e.kind == "showdown" for e in marked), "時刻表：seal 只能標在決戰（kind 是 showdown）")
    need(sum(1 for e in marked if e.seal == "emerge") == 1, "時刻表：標 seal: emerge 的決戰要剛好一件")
