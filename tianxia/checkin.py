"""每日簽到（docs/superpowers/specs/2026-10-17-正式季整合-design.md 6.2～6.4、8.1；正式季整合第 7 批）：21 天季每天簽一次，
丹的日子給回體丹、第 6、13、20 天給一個自己挑屬性的四階（第 6 天連丹兩樣都給），其餘的日子照先後輪流 30 兩、一個一階素材【預設】；
找素材、練功另有機會掉一顆回體丹（engine.Game._pill_find）。數字在 Config.checkin（只有 season21 設定打開，另照開季的章）。

第 N 天照開季那一天（台灣日）起算（12.3 第 43 條），那天沒上線就錯過；季末照舊是第 4 週週一 00:00，週一以外開季這一季就少幾天。
第 21 天只給丹（12.3 第 27 條「丹的日子只給丹」，比 6.2 的表晚）。素材四階關著時第 6 天只給丹、第 13、20 天改給銀兩。

這裡只放規則：第幾天、給什麼、能不能領、領了改背包與銀兩、畫面要的資料。寫江湖紀錄、序章與籌備中由 engine.Game.check_in 擋。
只 import models、state、calendar、materials、four_tiers。玩家看得到的字都待 joy 潤。
"""
from __future__ import annotations

import hashlib

from . import calendar, four_tiers, materials
from .models import Content, Material
from .state import GameState, WorldState

PILLS, TIER4, SILVER, MATERIAL = "pills", "tier4", "silver", "material"

TITLE = "簽到"
DONE = "第 {day} 天，江湖上的老朋友託人捎來一份東西：{gift}。"
TODAY_DONE = "今天已經簽過了，明日 00:00 後再來。"
PICK_FIRST = "今天的份要先挑一種四階料。"
BAD_PICK = "沒有這一種四階料可挑。"
OFF = "這一季沒有簽到。"
HUT = "草廬裡先照師父說的做，出了草廬再簽到。"
NEXT = "明日 {gift}"
STEP_BOTH = "回體丹 {n} 顆，再挑一種四階料（點一種就領）："
STEP_PICK = "挑一種四階料（點一種就領）："
STEP_CLAIM = "今天的份：{gift}"
STEP_DONE = "今天的份領過了：{gift}。"
PILL_FOUND = "獲得 【{name}】一顆——不知誰落下的，正好收著。"

# 七格上的短字與整句（一樣東西一段，「＋」接起來）
SHORT = {PILLS: "丹 {n}", TIER4: "四階", SILVER: "{silver} 兩", MATERIAL: "{tier}"}
SHORT_BOTH = "丹{n}＋四階"  # 第 6 天：格子窄，兩樣擠在一格
FULL = {PILLS: "回體丹 {n} 顆", TIER4: "自己挑的四階料一個", SILVER: "{silver} 兩", MATERIAL: "{tier}素材一個"}
TIER_WORDS = {1: "一階", 2: "二階", 3: "三階"}


def on(content: Content, world: WorldState | None) -> bool:
    """簽到開著沒：設定打開（只有 season21），這一季是 21 天季（開季時蓋的章），而且還沒收季。週末與 14 天一律關著。"""
    return content.config.checkin.enabled and calendar.season21_on(world, content) and not world.ended


def day_of(content: Content, world: WorldState) -> int:
    """這一刻是簽到的第幾天（從 1 起）：開季那一天（台灣日）是第 1 天（12.3 第 43 條）。"""
    return calendar.day_index(world.time, content, world) - calendar.open_day(content, world) + 1


def last_day(content: Content, world: WorldState) -> int:
    """這一季簽到的最後一天是第幾天：季末照舊是最後一週之後的週一 00:00，週一以外開季就少開季前那幾天。"""
    return content.config.season_weeks * 7 - calendar.open_day(content, world)


def _ordinary_index(content: Content, day: int) -> int:
    """day 是第幾個一般的日子（從 0 起）：表上丹與四階以外的日子照先後編號，偶數號給銀兩、奇數號給素材（草圖：1 銀、2 料、4 銀）。"""
    rule = content.config.checkin
    special = set(rule.pill_days) | set(rule.tier4_days)
    return sum(1 for d in range(1, day) if d not in special)


def gifts(content: Content, day: int) -> tuple[str, ...]:
    """第 day 天給哪幾樣（PILLS、TIER4、SILVER、MATERIAL，照這個先後）。素材四階關著時拿掉四階，空了改給銀兩。"""
    rule = content.config.checkin
    kinds = tuple(k for k, days in ((PILLS, rule.pill_days), (TIER4, rule.tier4_days)) if day in days)
    if not four_tiers.on(content):
        kinds = tuple(k for k in kinds if k != TIER4) or ((SILVER,) if day in rule.tier4_days else ())
    if kinds:
        return kinds
    return (SILVER,) if _ordinary_index(content, day) % 2 == 0 else (MATERIAL,)


def needs_pick(content: Content, day: int) -> bool:
    """第 day 天要先挑一種四階料才領得了。"""
    return TIER4 in gifts(content, day)


def _words(content: Content) -> dict:
    rule = content.config.checkin
    return {"n": rule.pills, "silver": rule.silver, "tier": TIER_WORDS[rule.material_tier]}


def short_text(content: Content, day: int) -> str:
    """七格上的短字：「30 兩」「一階」「丹 2」「丹2＋四階」「四階」。"""
    kinds, words = gifts(content, day), _words(content)
    if kinds == (PILLS, TIER4):
        return SHORT_BOTH.format(**words)
    return "＋".join(SHORT[k].format(**words) for k in kinds)


def gift_text(content: Content, day: int) -> str:
    """第 day 天那一份的整句：「回體丹 2 顆＋自己挑的四階料一個」。"""
    words = _words(content)
    return "＋".join(FULL[k].format(**words) for k in gifts(content, day))


def _tier4(content: Content) -> list[Material]:
    return [m for m in content.materials.values() if four_tiers.is_tier4(m)]


def tier4_choices(state: GameState, content: Content) -> list[dict]:
    """挑四階的那四顆（照素材表的先後）：屬性、素材 id、名字、手上有幾個。"""
    bag = state.player.materials
    return [{"attribute": m.attribute, "id": m.id, "name": m.name, "held": bag.get(m.id, 0)} for m in _tier4(content)]


def due(state: GameState, content: Content, world: WorldState) -> int | None:
    """今天還沒簽的話是第幾天；關著、簽過了、不在這一季的日子裡是 None（假人與整季機器人照它）。"""
    if not on(content, world):
        return None
    day = day_of(content, world)
    if not 1 <= day <= last_day(content, world) or day in state.player.checkin_days:
        return None
    return day


def material_for(content: Content, name: str, season: int, day: int) -> str | None:
    """一般日子給的那個素材：照「簽到|季數|名號|第幾天」的種子在那一階裡挑（決定性，不碰 Game.rng）。"""
    return materials.tier_pick(content, None, f"簽到|{season}|{name}|{day}", content.config.checkin.material_tier)


def claim(state: GameState, content: Content, world: WorldState, attribute: str = "") -> tuple[list[str], list[str]] | str:
    """領今天的份：成了回（訊息, 數值變化），不成回原因（什麼都不動）。四階的日子要帶屬性（剛柔快慢）。"""
    if not on(content, world):
        return OFF
    day = day_of(content, world)
    if not 1 <= day <= last_day(content, world):
        return OFF
    p = state.player
    if day in p.checkin_days:
        return TODAY_DONE
    kinds = gifts(content, day)
    pick = None
    if TIER4 in kinds:
        pick = next((m for m in _tier4(content) if m.attribute == attribute), None)
        if pick is None:
            return BAD_PICK if attribute else PICK_FIRST
    rule, got, changes = content.config.checkin, [], []
    if PILLS in kinds:
        p.stamina_pills += rule.pills
        name = content.config.stamina_pill_name
        got.append(f"{name} {rule.pills} 顆")
        changes.append(f"{name} +{rule.pills}")
    if SILVER in kinds:
        p.stats["silver"] = p.stats.get("silver", 0) + rule.silver
        got.append(f"{rule.silver} 兩")
        changes.append(f"銀兩 +{rule.silver}")
    for mid in ([pick.id] if pick is not None else []) + (
            [material_for(content, p.name, p.season_number, day)] if MATERIAL in kinds else []):
        if mid is not None and materials.grant(state, content, mid):
            got.append(f"{content.materials[mid].name}一個")
            changes.append(f"{content.materials[mid].name} +1")
    p.checkin_days.append(day)
    return [DONE.format(day=day, gift="、".join(got))], changes


def view(state: GameState, content: Content, world: WorldState) -> dict:
    """江湖頁「簽到」小標攤開的資料（9.1 第 4 組丙）：今天第幾天、簽了沒、這一週七格（最後一週到季末為止）、今天的份、明天的份、
    挑四階的四顆（四階的日子還沒簽才有）、鈕上面那一句。"""
    day, last = day_of(content, world), last_day(content, world)
    claimed = set(state.player.checkin_days)
    done = day in claimed
    first = (day - 1) // 7 * 7 + 1
    week = []
    for d in range(first, min(first + 6, last) + 1):
        status = "today" if d == day else "future" if d > day else "got" if d in claimed else "miss"
        week.append({"day": d, "label": short_text(content, d), "state": status, "got": d in claimed,
                     "four": TIER4 in gifts(content, d)})
    gift = gift_text(content, day)
    pick = needs_pick(content, day) and not done
    if done:
        step = STEP_DONE.format(gift=gift)
    elif pick:
        step = STEP_BOTH.format(n=content.config.checkin.pills) if PILLS in gifts(content, day) else STEP_PICK
    else:
        step = STEP_CLAIM.format(gift=gift)
    return {
        "day": day, "done": done, "week": week, "gift": gift, "step": step,
        "next": NEXT.format(gift=gift_text(content, day + 1)) if day < last else None,
        "pick": tier4_choices(state, content) if pick else None,
    }


def bot_attribute(content: Content, name: str, season: int) -> str:
    """假人挑的四階屬性（8.1）：照「簽到四階|名號|季數」的種子在四階料裡挑一種（一季三次都一樣）。"""
    pool = _tier4(content)
    digest = hashlib.sha256(f"簽到四階|{name}|{season}".encode()).digest()
    return pool[digest[0] % len(pool)].attribute if pool else ""
