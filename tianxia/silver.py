"""銀兩出口（docs/superpowers/specs/2026-10-17-正式季整合-design.md 6.5；正式季整合第 9 批）：21 天季多五種花銀兩的地方——
捐銀兩進軍需帳、名師指點、看火候、買破境丹、打點門路（塞門房）。數字在 Config.silver_outlets（只有 season21 設定打開，另照開季的章）。

這裡只放規則：能不能、多少錢、做了改什麼（背包、銀兩、當天的計數、下一次修練或打造的加成）。人在哪裡（大本營、醫館、鐵匠鋪、
人物所在）由 engine.Game 問；記貢獻、軍備存量、推大勢跟捐素材同一條（Game._credit_donation）。只 import models、state、calendar，
cultivation、fusion、smithing 都能叫它。「一天」由呼叫端給（Game.econ_day，回體丹的換日）。玩家看得到的字都待 joy 潤。
"""
from __future__ import annotations

from . import calendar
from .models import Content
from .state import GameState, WorldState

DONATE_LABEL = "捐銀兩 {silver} 兩（貢獻 +{points}）"
DONATE_REFUSED = "捐銀兩（{problem}）"
DONATE_DONE = "你把 {silver} 兩銀子交給軍需官，記進{faction}的糧秣。"
DONATE_TITLE = "捐銀兩"
SILVER_SHORT = "還差 {short} 兩"
DAILY_FULL = "今天已捐滿 {cap} 兩，明日 00:00 後再捐"
POINTS_FULL = "今天已捐滿 {cap} 點，明日 00:00 後再捐"

MENTOR_LABEL = "名師指點（{silver} 兩：下一次修練升品的機會 +{bonus}%）"
MENTOR_REFUSED = "名師指點（{problem}）"
MENTOR_DONE = "老大夫領你去見一位隱居的前輩，聽他把修練的關竅點撥了一遍：下一次修練升品的機會多 {bonus}%。"
MENTOR_READY = "已經請過了，還沒修練"
MENTOR_TODAY = "今天請過了，明日 00:00 後再來"
MENTOR_TITLE = "名師指點"

FURNACE_LABEL = "看火候（{silver} 兩：下一爐的品質好一些）"
FURNACE_REFUSED = "看火候（{problem}）"
FURNACE_DONE = "老師傅答應下一爐親自替你看火候：不論打造還是合成，出好東西的機會大一些。"
FURNACE_READY = "已經請過了，還沒開爐"
FURNACE_TODAY = "今天請過了，明日 00:00 後再來"
FURNACE_PROLOGUE = "初入江湖，還請不動老師傅"
FURNACE_TITLE = "看火候"

LEGEND_LABEL = "買{name}一枚（{silver} 兩・這一季還能買 {left} 枚）"
LEGEND_REFUSED = "買{name}（{problem}）"
LEGEND_DONE = "醫館的老大夫從藥櫃最底層取出一枚{name}，包好遞給你。"
LEGEND_FULL = "這一季能買的都買過了"
LEGEND_TITLE = "買丹"

BRIBE_LABEL = "打點門路・{name}（{silver} 兩：情誼 +{gain}）"
BRIBE_REFUSED = "打點門路・{name}（{problem}）"
BRIBE_DONE = "你塞了些銀子給{name}的門房，門房答應替你說幾句好話。"
BRIBE_TODAY = "今天打點過了"
BRIBE_TOP = "情誼到這裡，得當面去處了"
BRIBE_TITLE = "打點門路"


def on(content: Content, world: WorldState | None) -> bool:
    """銀兩出口開著沒：設定打開（只有 season21），而且這一季是 21 天季（開季時蓋的章）。週末與 14 天一律關著。"""
    return content.config.silver_outlets.enabled and calendar.season21_on(world, content)


def _short(state: GameState, price: int) -> str | None:
    short = price - state.player.stats.get("silver", 0)
    return SILVER_SHORT.format(short=short) if short > 0 else None


def _pay(state: GameState, price: int) -> list[str]:
    p = state.player
    p.stats["silver"] = p.stats.get("silver", 0) - price
    return [f"銀兩 -{price}"] if price else []


# ── 捐銀兩進軍需帳 ──


def _donated_today(state: GameState, day: int) -> int:
    p = state.player
    return p.silver_donated if p.silver_donate_day == day else 0


def donate_amount(state: GameState, content: Content, day: int, room_points: int) -> int:
    """這一下捐多少兩：一下 donate_step 兩，再照手上的、今天還收得下的點數（room_points，跟捐素材共用）× 每點幾兩、今天還能捐的兩數
    切，取整到每點幾兩的倍數。捐不了是 0。"""
    cfg = content.config.silver_outlets
    per = cfg.donate_per_point
    left = cfg.donate_daily_silver - _donated_today(state, day)
    amount = min(cfg.donate_step, state.player.stats.get("silver", 0), room_points * per, left)
    return max(0, amount // per * per)


def donate_problem(state: GameState, content: Content, day: int, room_points: int, points_cap: int) -> str | None:
    """捐不了的原因（捐得了是 None）：今天的兩數捐滿、今天的點數捐滿（跟捐素材共用）、手上不到一點的錢。"""
    cfg = content.config.silver_outlets
    if _donated_today(state, day) >= cfg.donate_daily_silver:
        return DAILY_FULL.format(cap=cfg.donate_daily_silver)
    if room_points <= 0:
        return POINTS_FULL.format(cap=points_cap)
    if donate_amount(state, content, day, room_points) <= 0:
        return _short(state, cfg.donate_per_point)
    return None


def take_donation(state: GameState, content: Content, day: int, room_points: int) -> tuple[int, int]:
    """真的收下：扣銀兩、記今天的兩數與點數（捐素材的那本 donated_today），回（幾兩, 幾點）；捐不了是 (0, 0)、什麼都不動。"""
    if donate_problem(state, content, day, room_points, 0) is not None:
        return 0, 0
    amount = donate_amount(state, content, day, room_points)
    points = amount // content.config.silver_outlets.donate_per_point
    p = state.player
    p.stats["silver"] = p.stats.get("silver", 0) - amount
    p.silver_donated, p.silver_donate_day = _donated_today(state, day) + amount, day
    p.donated_today = (p.donated_today if p.donate_day == day else 0) + points
    p.donate_day = day
    return amount, points
