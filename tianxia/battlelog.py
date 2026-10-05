"""遭遇/劇情戰紀錄（sanguo-companions 合併大幅簡化，取代舊的逐回合戰報）：把一次
encounter.EncounterResult 存成 BattleRecord，並產生場景卡片與戰報列表的文字。全服決戰補送給參戰者的那一筆
（kind 是 showdown，Game._deliver_battle_results 建的）也在這裡畫，沒有威力與難度、改寫站哪一邊與大勢。
勝負一次算好之後照結果演出的 3～5 回合（武學與成長設計 8.2）：數字在 rounds.py，句子在這裡（round_lines）。
"""
from __future__ import annotations

import random
import re
from collections.abc import Callable

from . import calendar, front_lines, team
from . import rounds as rounds_mod  # state 也有一個 Fighter（戰報的陣容），這裡用別名免得混淆
from .encounter import EncounterResult, describe_result
from .models import Content, Squad
from .state import BattleRecord, Fighter, GameState
from .world_state import WorldStateStore

MAX_RECORDS = 20  # 存檔保留最近幾場
TIER_WORDS = {"大勝": "大勝", "險勝": "險勝", "僵持": "平手", "落敗": "落敗"}
KIND_WORDS = {"train": "遊歷", "event": "劇情", "wild": "探索遇敵", "showdown": "決戰"}
NO_RECORD = "（還沒有戰報。）"
DAY = 86400
HOUR = 3600
_NUMERIC_CHANGE = re.compile(r"^\S+ [+-]\d+(\.\d+)?$")  # 例如「名望 +3」「銀兩 -10」


def split_changes(msgs: list[str], *, for_record: bool = False) -> tuple[list[str], list[str]]:
    """把一串訊息（apply_effect、遊歷加成……的回傳）分成（數值變化, 敘事文字）兩份，各自保留原順序。
    數值變化是「標籤 + 正負號 + 數字」這種格式，例如「名望 +3」；其餘一律算敘事文字。
    for_record：這兩份是要記進戰報（BattleRecord）的——戰況變化（front_lines.mark）不收：戰鬥卡片的「獲得與損失」
    是不上色的字、而戰況變化的顏色要看畫面的人站哪一邊，所以它留在江湖紀錄裡、由卡片底下的補充用標籤畫（FB-064）。"""
    if for_record:
        msgs = [m for m in msgs if not front_lines.is_mark(m)]
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
    """遊戲時間，例如「第2天 14:05」。第一季的季曆寫法由呼叫端用 calendar.stamp_text 換掉（見 list_label 的 when）。"""
    return calendar.day_clock_text(time)


def outcome_text(record: BattleRecord) -> str:
    """結果的短句，例如「擊退劫道山賊（大勝）」；江湖紀錄拿它當那一則的結果標記。決戰的結果本身就是一句話（「官軍大勝」）。"""
    if record.kind == "showdown":
        return record.tier
    return f"{TIER_WORDS[record.tier]}{record.opponent}"


def summary_line(record: BattleRecord) -> str:
    """紀錄裡的一行摘要，例如「⚔ 揚州城郊：大勝劫道山賊」。"""
    return f"⚔ {record.location}：{outcome_text(record)}"


def list_label(record: BattleRecord, when: Callable[[float], str] = clock_text) -> str:
    """戰報列表的一列：「大勝　第12場　第1天 08:30　揚州城郊　vs 劫道山賊」。when 是時間的寫法（第一季給季曆）。"""
    return f"{record.tier}　第{record.id}場　{when(record.time)}　{record.location}　vs {record.opponent}"


def _title(record: BattleRecord) -> str:
    return f"### ⚔ {record.location}・對陣 {record.opponent}"


def _when(record: BattleRecord, when: Callable[[float], str]) -> str:
    kind = KIND_WORDS[record.kind] + (f"：{record.event}" if record.event else "")
    return f"{when(record.time)}　{kind}"


def _result_line(record: BattleRecord) -> str:
    if record.kind == "showdown":  # 全服決戰沒有我方威力與對手難度：寫結果與自己站的那一邊
        return f"**{record.tier}**　你站在{record.side}"
    return f"**{record.tier}**　我方威力 {record.our_power:.0f}　對手難度 {record.difficulty:.0f}"


def gains_list(record: BattleRecord) -> list[str]:
    """獲得與損失的每一項，例如 ["經驗 +15（每人）", "心得 +12", "銀兩 +10", "精鐵砂 ×1", "氣血 -48"]。"""
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


def round_lines(content: Content, played: list[rounds_mod.Round], rng: random.Random) -> list[str]:
    """把回合寫成一行一行的句子：照出手那門武學（對手照它自己）的屬性挑句型（content/combat_lines.json）。
    我方：「沈浪以【旋風腿】身形一晃，搶到側面出手，對手氣勢 -18」，沒打中寫「，被對方架開」；沒學武學的沒有「以【】」、
    句型從 bare 挑。對手：「山賊掄起兵刃猛砸過來，你氣血 -24」，沒打中寫「，被你閃開了」；這一場不扣氣血（amount 是
    None，劇情戰）就只寫怎麼出手。rng 是呼叫端給的那一份（引擎用名號＋戰報流水號當種子，不碰 Game.rng）。"""
    lines = content.combat_lines
    out = []
    for r in played:
        parts = []
        for beat in r.beats:
            if beat.side == "ours":
                how = rng.choice(lines.ours.get(beat.attribute, []) or lines.bare) if beat.art else rng.choice(lines.bare)
                art = f"以【{beat.art}】" if beat.art else ""
                tail = f"，對手氣勢 -{beat.amount}" if beat.amount else "，被對方架開"
                parts.append(f"{beat.actor}{art}{how}{tail}")
            else:
                how = rng.choice(lines.theirs.get(beat.attribute, []) or lines.theirs_any)
                tail = "" if beat.amount is None else f"，你氣血 -{beat.amount}" if beat.amount else "，被你閃開了"
                parts.append(f"{beat.actor}{how}{tail}")
        out.append(f"第{r.number}回合　" + "；".join(parts) + "。")
    return out


def _rounds_block(record: BattleRecord) -> list[str]:
    """戰報的「過程」：一回合一行（Markdown 清單）。大場面有模型寫的那一版（narration，武學與成長設計 8.3）就寫它、一段話，
    取代範本句子的回合。決戰與舊戰報沒有。"""
    if record.narration:
        return [f"**過程**\n{record.narration}"]
    if not record.rounds:
        return []
    return ["**過程**\n" + "\n".join(f"- {line}" for line in record.rounds)]


def _story_block(record: BattleRecord) -> list[str]:
    story = story_text(record)
    return [f"**結果**　{story}"] if story else []


def _gains_block(record: BattleRecord) -> list[str]:
    """獲得與損失那一行。全服決戰沒有經驗、銀兩這些得失，只有大勢的增減，寫成「大勢」那一行；上一季打的那一場，
    大勢的增減寫在結果的敘事裡（標了第幾季），沒有這一行。"""
    if record.kind == "showdown":
        return [f"**大勢**　{'　'.join(record.changes)}"] if record.changes else []
    return [f"**獲得與損失**　{gains_text(record)}"]


def card_text(record: BattleRecord, when: Callable[[float], str] = clock_text) -> str:
    """場景裡的戰鬥卡片（Markdown）：標題、時間與類型、結果、（過程）、（劇情結果）、獲得與損失。when 是時間的寫法（見 list_label）。
    過程整段都在；「剛剛」那張卡片只露第一回合、點了才攤開，是網頁的事（web/app.js 的 roundsFold）。"""
    return "\n\n".join([
        _title(record),
        _when(record, when),
        _result_line(record),
        *_rounds_block(record),
        *_story_block(record),
        *_gains_block(record),
    ])


def _ours_line(record: BattleRecord) -> str:
    return "、".join(f"{f.name} Lv{f.level}" for f in record.ours)


def detail_text(record: BattleRecord, when: Callable[[float], str] = clock_text) -> str:
    """戰報分頁下方的完整內容（Markdown）：陣容、結果、（過程）、（劇情結果）、得失。全服決戰不列陣容（站哪一邊寫在結果那一行）。
    when 是時間的寫法（第一季給季曆，見 list_label）。"""
    return "\n\n".join([
        _title(record),
        f"{_when(record, when)}　第 {record.id} 場",
        *([] if record.kind == "showdown" else [f"**我方**　{_ours_line(record)}"]),
        _result_line(record),
        *_rounds_block(record),
        *_story_block(record),
        *_gains_block(record),
    ])
