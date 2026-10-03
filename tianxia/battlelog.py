"""遭遇/劇情戰紀錄（sanguo-companions 合併大幅簡化，取代舊的逐回合戰報）：把一次
encounter.EncounterResult 存成 BattleRecord，並產生場景卡片與戰報列表的文字。全服決戰補送給參戰者的那一筆
（kind 是 showdown，Game._deliver_battle_results 建的）也在這裡畫，沒有威力與難度、改寫站哪一邊與大勢。
"""
from __future__ import annotations

import re

from . import team
from .encounter import EncounterResult, describe_result
from .models import Content, Squad
from .state import BattleRecord, Fighter, GameState
from .world_state import WorldStateStore

MAX_RECORDS = 20  # 存檔保留最近幾場
TIER_WORDS = {"大勝": "大勝", "險勝": "險勝", "僵持": "平手", "落敗": "落敗"}
KIND_WORDS = {"train": "歷練", "event": "劇情", "wild": "探索遇敵", "showdown": "決戰"}
NO_RECORD = "（還沒有戰報。）"
DAY = 86400
HOUR = 3600
_NUMERIC_CHANGE = re.compile(r"^\S+ [+-]\d+(\.\d+)?$")  # 例如「名望 +3」「銀兩 -10」


def split_changes(msgs: list[str]) -> tuple[list[str], list[str]]:
    """把一串訊息（apply_effect、歷練加成……的回傳）分成（數值變化, 敘事文字）兩份，各自保留原順序。
    數值變化是「標籤 + 正負號 + 數字」這種格式，例如「名望 +3」；其餘一律算敘事文字。"""
    changes = [m for m in msgs if _NUMERIC_CHANGE.match(m)]
    notes = [m for m in msgs if not _NUMERIC_CHANGE.match(m)]
    return changes, notes


# ── 建立紀錄 ──────────────────────────────────────────


def new_record(
    state: GameState, content: Content, world: WorldStateStore, squad: Squad, result: EncounterResult,
    kind: str, event: str = "",
) -> BattleRecord:
    """剛打完、還沒發獎懲時呼叫。獲得與損失（exp、xinde、silver、notes）由 engine 發完獎懲後填入，
    再交給 add_record。"""
    p = state.player
    keys = team.team_keys(state)
    names = [team.member_name(state, content, key) for key in keys]
    levels = [p.member.level] + [world.get_companion(k).level for k in state.player.team]
    return BattleRecord(
        id=state.battle_seq + 1,
        time=state.world.time,
        location=content.locations[p.location].name,
        kind=kind,
        event=event,
        opponent=squad.name,
        ours=[Fighter(name=name, level=level) for name, level in zip(names, levels)],
        tier=result.tier,
        our_power=result.our_power,
        difficulty=result.difficulty,
    )


def add_record(state: GameState, record: BattleRecord) -> None:
    """最新的放最前面，只留最近 MAX_RECORDS 場。"""
    state.battle_seq = record.id
    state.battles.insert(0, record)
    del state.battles[MAX_RECORDS:]


def find(state: GameState, record_id: int | None) -> BattleRecord | None:
    return next((r for r in state.battles if r.id == record_id), None)


# ── 文字 ──────────────────────────────────────────────


def clock_text(time: float) -> str:
    """遊戲時間，例如「第2天 14:05」。"""
    return f"第{int(time // DAY) + 1}天 {int(time % DAY // HOUR):02d}:{int(time % HOUR // 60):02d}"


def outcome_text(record: BattleRecord) -> str:
    """結果的短句，例如「擊退劫道山賊（大勝）」；江湖紀錄拿它當那一則的結果標記。決戰的結果本身就是一句話（「官軍大勝」）。"""
    if record.kind == "showdown":
        return record.tier
    return f"{TIER_WORDS[record.tier]}{record.opponent}"


def summary_line(record: BattleRecord) -> str:
    """紀錄裡的一行摘要，例如「⚔ 揚州城郊：大勝劫道山賊」。"""
    return f"⚔ {record.location}：{outcome_text(record)}"


def list_label(record: BattleRecord) -> str:
    """戰報列表的一列：「大勝　第12場　第1天 08:30　揚州城郊　vs 劫道山賊」。"""
    return f"{record.tier}　第{record.id}場　{clock_text(record.time)}　{record.location}　vs {record.opponent}"


def _title(record: BattleRecord) -> str:
    return f"### ⚔ {record.location}・對陣 {record.opponent}"


def _when(record: BattleRecord) -> str:
    kind = KIND_WORDS[record.kind] + (f"：{record.event}" if record.event else "")
    return f"{clock_text(record.time)}　{kind}"


def _result_line(record: BattleRecord) -> str:
    if record.kind == "showdown":  # 全服決戰沒有我方威力與對手難度：寫結果與自己站的那一邊
        return f"**{record.tier}**　你站在{record.side}"
    return f"**{record.tier}**　我方威力 {record.our_power:.0f}　對手難度 {record.difficulty:.0f}"


def gains_list(record: BattleRecord) -> list[str]:
    """獲得與損失的每一項，例如 ["經驗 +15（每人）", "心得 +12", "銀兩 +10", "精鐵砂 ×1", "臂力 +1"]。"""
    parts = []
    if record.exp:
        parts.append(f"經驗 +{record.exp}（每人）")
    if record.xinde:
        parts.append(f"心得 +{record.xinde}")
    if record.silver:
        parts.append(f"銀兩 {record.silver:+d}")
    parts += record.materials
    return parts + record.changes


def gains_text(record: BattleRecord) -> str:
    return "　".join(gains_list(record)) or "無"


def story_text(record: BattleRecord) -> str:
    """結果的敘事文字（選項效果文字、升級、拜師等），不含【江湖傳聞】那一行；沒有時是空字串。"""
    return "　".join(n for n in record.notes if not n.startswith("【江湖傳聞】"))


def _story_block(record: BattleRecord) -> list[str]:
    story = story_text(record)
    return [f"**結果**　{story}"] if story else []


def _gains_block(record: BattleRecord) -> list[str]:
    """獲得與損失那一行。全服決戰沒有經驗、銀兩這些得失，只有大勢的增減，寫成「大勢」那一行；上一季打的那一場，
    大勢的增減寫在結果的敘事裡（標了第幾季），沒有這一行。"""
    if record.kind == "showdown":
        return [f"**大勢**　{'　'.join(record.changes)}"] if record.changes else []
    return [f"**獲得與損失**　{gains_text(record)}"]


def card_text(record: BattleRecord) -> str:
    """場景裡的戰鬥卡片（Markdown）：標題、時間與類型、結果、（劇情結果）、獲得與損失。"""
    return "\n\n".join([
        _title(record),
        _when(record),
        _result_line(record),
        *_story_block(record),
        *_gains_block(record),
    ])


def _ours_line(record: BattleRecord) -> str:
    return "、".join(f"{f.name} Lv{f.level}" for f in record.ours)


def detail_text(record: BattleRecord) -> str:
    """戰報分頁下方的完整內容（Markdown）：陣容、結果、（劇情結果）、得失。全服決戰不列陣容（站哪一邊寫在結果那一行）。"""
    return "\n\n".join([
        _title(record),
        f"{_when(record)}　第 {record.id} 場",
        *([] if record.kind == "showdown" else [f"**我方**　{_ours_line(record)}"]),
        _result_line(record),
        *_story_block(record),
        *_gains_block(record),
    ])
