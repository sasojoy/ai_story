"""事件分級（企劃者 2026-10-26「應該有分級…我們現在這批事件滿適配第一階段…後面那些是我們現在欠缺的」；事件分級設計稿）。

現有的事件都是第一階。第二階「州郡大事」、第三階「天下大事」照五道門開（Event.door）：武事看等級、名流看名望、俠義看善名、
綠林看惡名、擂主看擂台名次；門檻在 Config.jianfa.tier_doors。門沒開的那一則抽不到（events.event_candidates）；開到第二、三階的人
抽事件時先照 Config.jianfa.tier_mix 挑一階、再在那一階裡照權重抽（narrow）。第二、三階的檢定不吃第一階的放寬（rules.check_outlook，
Check.tier 由載入時蓋）。掛在減法季的子開關 event_tiers：關著時第二、三階一則都抽不到，第一階照舊。
"""

from __future__ import annotations

import random

from . import arena, renown
from .models import Content, Event
from .rules import jianfa
from .state import GameState

DOORS = ("武事", "名流", "俠義", "綠林", "擂主")
NAMES = {1: "", 2: "州郡大事", 3: "天下大事"}  # 事件卡的小標（第一階不寫）


def on(content: Content, state: GameState) -> bool:
    return jianfa(content, state.world, "event_tiers")


def _reached(state: GameState, content: Content, door: str, need: int) -> bool:
    if door == "武事":
        return state.player.member.level >= need
    if door == "名流":
        return renown.fame_tier(state, content) >= need
    if door in ("俠義", "綠林"):
        return renown.path(state) == ("俠" if door == "俠義" else "寇") and renown.virtue_tier(state, content) >= need
    entry = arena.entry_of(state.world, state.player.name)  # 擂主：名次至少到第幾名
    return entry is not None and entry.rank <= need


def door_tier(state: GameState, content: Content, door: str) -> int:
    """這一道門此刻開到第幾階（1 是都沒開）。關著一律是 1。"""
    if not on(content, state):
        return 1
    gates = content.config.jianfa.tier_doors.get(door, [])
    tier = 1
    for step, need in enumerate(gates, 2):
        if not _reached(state, content, door, need):
            break
        tier = step
    return tier


def open_for(state: GameState, content: Content, event: Event) -> bool:
    """這一則的階此刻抽得到嗎：第一階一律是；第二、三階要那一道門開到那一階。"""
    return event.tier == 1 or (event.door is not None and door_tier(state, content, event.door) >= event.tier)


def top_tier(state: GameState, content: Content) -> int:
    """開到最高的那一階（每一道門取最高）。"""
    return max((door_tier(state, content, door) for door in DOORS), default=1)


def narrow(state: GameState, content: Content, candidates: list[Event], rng: random.Random) -> list[Event]:
    """抽之前先挑一階（照開到第幾階的比重，候選裡沒有的階不算），回那一階的候選。只有一階、關著時原樣回（不動 rng）。"""
    present = sorted({e.tier for e in candidates})
    if len(present) < 2 or not on(content, state):
        return candidates
    mix = content.config.jianfa.tier_mix.get(top_tier(state, content), [1.0])
    weights = [mix[t - 1] if t - 1 < len(mix) else 0.0 for t in present]
    if sum(weights) <= 0:
        return candidates
    tier = rng.choices(present, weights=weights)[0]
    return [e for e in candidates if e.tier == tier]
