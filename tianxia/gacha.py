"""招賢：用元寶單抽或十連，從卡池（人物資料標了「招賢」管道的人）抽人。

機率公開、同品階的人平均分配；連續 config.gacha_pity 抽沒出天品，那一抽必得天品；十連至少一名
config.gacha_ten_floor（地品）以上，和天品保底分開算。新人照入門規則（roster.recruit）入門、先列候補；
抽到已入門的人換成心得（config.duplicate_xinde），受付費心得護欄限制：本季招賢心得超過 gacha_xinde_half
之後減半、補到 gacha_xinde_cap 為止，之後改給銀兩（gacha_silver）。境界上限（設計文件 1c §5.6 第 3 層）
等 1b 的境界系統再接。價格、重複換算與護欄的數字都是暫定・另談，全在 config。
亂數只在真的抽的時候用（Game.rng），看頁面、按不下去都不動亂數。
"""
from __future__ import annotations

import random

from . import roster
from .models import COMPANION_TIERS, Content, in_gacha_pool
from .state import GameState, Pull

SINGLE, TEN = 1, 10  # 單抽、十連
TOP = COMPANION_TIERS[0]  # 保底必得的品階（天品）


def pool(content: Content) -> dict[str, list[str]]:
    """卡池：品階 → 人物 id（依內容順序）；只列有人的品階，依天地玄黃排。
    誰在卡池裡由 models.in_gacha_pool 決定（載入時的卡池檢查也用它）。"""
    found = {
        tier: [cid for cid, ch in content.characters.items() if ch.tier == tier and in_gacha_pool(ch)]
        for tier in COMPANION_TIERS
    }
    return {tier: ids for tier, ids in found.items() if ids}


def label(count: int) -> str:
    return "單抽" if count == SINGLE else "十連"


def cost(content: Content, count: int) -> int:
    return content.config.gacha_single if count == SINGLE else content.config.gacha_ten


def block(state: GameState, content: Content, count: int) -> str:
    """抽不成的原因（「元寶不足，要 1000」「賽季已落幕」）；抽得成時是空字串。"""
    if count not in (SINGLE, TEN):
        return "沒有這種抽法"
    if state.world.ended:
        return "賽季已落幕"
    price = cost(content, count)
    if state.player.yuanbao < price:
        return f"元寶不足，要 {price}"
    return ""


def floor_tiers(content: Content) -> list[str]:
    """十連保證的品階：config.gacha_ten_floor 與比它高的（預設是天、地）。"""
    return list(COMPANION_TIERS[: COMPANION_TIERS.index(content.config.gacha_ten_floor) + 1])


def roll_tier(state: GameState, content: Content, rng: random.Random, floor: bool = False) -> str:
    """這一抽的品階。保底到了（這是連續第 gacha_pity 抽沒出天品）就是天品，不用亂數；
    floor（十連的最後一抽，前九抽都沒有地品以上）時只在 floor_tiers 之間照機率的比例抽（預設天 3：地 12）；
    其餘照 config.gacha_rates。"""
    cfg = content.config
    if state.player.gacha_pity + 1 >= cfg.gacha_pity:
        return TOP
    tiers = floor_tiers(content) if floor else list(COMPANION_TIERS)
    return rng.choices(tiers, weights=[cfg.gacha_rates[t] for t in tiers])[0]


def pull(state: GameState, content: Content, rng: random.Random, count: int) -> list[str]:
    """招賢 count 抽（呼叫前已確認 block 是空字串）：扣元寶，一抽一抽依序抽品階、再在同品階裡平均抽一位；
    新人入門，已入門的人換成心得或銀兩（同一次十連抽到同一位新人兩次，第二次就算重複）。
    結果依序記在 PlayerState.gacha_last。回傳江湖紀錄用的訊息：「元寶 -1000」、每一抽一句，
    以及每筆心得、銀兩（紀錄裡會加總成一項）。"""
    p = state.player
    price = cost(content, count)
    p.yuanbao -= price
    msgs = [f"元寶 -{price}"]
    pulls: list[Pull] = []
    drawable, floor = pool(content), floor_tiers(content)
    for i in range(count):
        short = count == TEN and i == TEN - 1 and all(content.characters[x.character].tier not in floor for x in pulls)
        tier = roll_tier(state, content, rng, floor=short)
        cid = rng.choice(drawable[tier])
        p.gacha_pity = 0 if tier == TOP else p.gacha_pity + 1
        if cid in p.members:
            result, lines = _duplicate(state, content, cid)
        else:
            result, lines = Pull(character=cid, new=True), roster.recruit(state, content, cid)
        pulls.append(result)
        msgs += lines
    p.gacha_last = pulls
    return msgs


def _duplicate(state: GameState, content: Content, cid: str) -> tuple[Pull, list[str]]:
    """抽到已入門的人：照 config.duplicate_xinde 換成心得，受付費心得護欄限制——本季招賢心得超過 gacha_xinde_half
    之後減半（剛好等於不算超過）、最多補到 gacha_xinde_cap；已經滿了就改給 gacha_silver 的銀兩。"""
    cfg, p = content.config, state.player
    ch = content.characters[cid]
    head = f"【{ch.name}】（{ch.tier}品）重複"
    got = p.gacha_xinde
    if got >= cfg.gacha_xinde_cap:
        silver = cfg.gacha_silver[ch.tier]
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        note = f"（本季招賢心得已滿 {cfg.gacha_xinde_cap}）"
        return Pull(character=cid, new=False, silver=silver), [f"{head} → 銀兩 +{silver}{note}", f"銀兩 +{silver}"]
    amount, note = cfg.duplicate_xinde[ch.tier], ""
    if got > cfg.gacha_xinde_half:
        amount, note = amount // 2, f"（本季招賢心得已超過 {cfg.gacha_xinde_half}，減半）"
    if amount > cfg.gacha_xinde_cap - got:
        amount, note = cfg.gacha_xinde_cap - got, f"（補到本季上限 {cfg.gacha_xinde_cap}）"
    p.gacha_xinde += amount
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    return Pull(character=cid, new=False, xinde=amount), [f"{head} → 心得 +{amount}{note}", f"心得 +{amount}"]
