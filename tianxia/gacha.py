"""招賢：用元寶單抽或十連，從卡池（人物資料標了「招賢」管道的人）抽人。

機率公開、同品階的人平均分配；連續 config.gacha_pity 抽沒出天品，那一抽必得天品；十連至少一名
config.gacha_ten_floor（地品）以上，和天品保底分開算。新人照入門規則（roster.recruit）入門、先列候補；
抽到已入門的人換成心得（config.duplicate_xinde），受付費心得護欄限制：本季招賢心得超過 gacha_xinde_half
之後減半、補到 gacha_xinde_cap 為止，之後改給銀兩（gacha_silver）。境界上限（設計文件 1c §5.6 第 3 層）
等 1b 的境界系統再接。價格、重複換算與護欄的數字都是暫定・另談，全在 config。
亂數只在真的抽的時候用（Game.rng），看頁面、按不下去都不動亂數。
"""
from __future__ import annotations

import html
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


# ── 江湖紀錄與摘要 ─────────────────────────────────────────


def tag(content: Content, pulls: list[Pull]) -> str:
    """江湖紀錄的結果標記，點名品階最高的那一位（同品階時新入門優先，再來是先抽到的），例如「得地品【陸沉舟】」。"""
    order = {tier: i for i, tier in enumerate(COMPANION_TIERS)}
    best = min(pulls, key=lambda x: (order[content.characters[x.character].tier], not x.new))
    ch = content.characters[best.character]
    return f"得{ch.tier}品【{ch.name}】"


def summary(pulls: list[Pull], count: int) -> str:
    """抽完顯示在招賢分頁的一句話，例如「十連：新入門 2 人，重複 8 人（心得 +70）。」"""
    new = sum(x.new for x in pulls)
    parts = [f"新入門 {new} 人"] if new else []
    if len(pulls) > new:
        totals = (("心得", sum(x.xinde for x in pulls)), ("銀兩", sum(x.silver for x in pulls)))
        gains = "、".join(f"{name} +{amount}" for name, amount in totals if amount)
        parts.append(f"重複 {len(pulls) - new} 人" + (f"（{gains}）" if gains else ""))
    return f"{label(count)}：{'，'.join(parts)}。"


# ── 招賢分頁的文字 ─────────────────────────────────────────

NO_PULLS = "（還沒有招賢過。按「單抽」或「十連」，抽到的人會列在這裡。）"
TIER_CLASS = {"天": "gc-t1", "地": "gc-t2", "玄": "gc-t3", "黃": "gc-t4"}  # 結果卡左邊色條的顏色


def button(state: GameState, content: Content, count: int) -> tuple[str, bool]:
    """「單抽」「十連」按鈕的（文字, 按得下去）：「單抽（元寶 100）」「十連（元寶 1000・至少一名地品以上）」；
    抽不成時寫原因，例如「十連（元寶不足，要 1000）」「單抽（賽季已落幕）」。"""
    reason = block(state, content, count)
    if reason:
        return f"{label(count)}（{reason}）", False
    extra = f"・至少一名{content.config.gacha_ten_floor}品以上" if count == TEN else ""
    return f"{label(count)}（元寶 {cost(content, count)}{extra}）", True


def head(state: GameState, content: Content) -> str:
    """分頁最上面一行（Markdown）：元寶、保底倒數、本季招賢心得。"""
    cfg, p = content.config, state.player
    left = max(1, cfg.gacha_pity - p.gacha_pity)
    return f"**元寶** {p.yuanbao}　｜　再 **{left}** 抽必得天品　｜　本季招賢心得 {p.gacha_xinde}／{cfg.gacha_xinde_cap}"


def _pct(value: float) -> str:
    return f"{round(value, 2):g}%"


def _by_tier(values: dict[str, int]) -> str:
    """「黃 10、玄 20、地 50、天 100」：由低到高。"""
    return "、".join(f"{tier} {values[tier]}" for tier in reversed(COMPANION_TIERS))


def rules_text(state: GameState, content: Content) -> str:
    """公開的機率、保底、重複換算與卡池（Markdown）；卡池每人標出品階與單人機率，已入門的人註明。"""
    cfg = content.config
    rates = "　".join(f"{tier}品 {_pct(cfg.gacha_rates[tier])}" for tier in COMPANION_TIERS)
    paras = [
        f"**機率**　{rates}（同品階的人平均分配）",
        f"**保底**　連續 {cfg.gacha_pity} 抽沒出天品，第 {cfg.gacha_pity} 抽必得天品，抽到天品就重新算；"
        f"十連至少一名{cfg.gacha_ten_floor}品以上（和天品保底分開算）",
        f"**重複**　已入門的人化為心得（{_by_tier(cfg.duplicate_xinde)}）；本季招賢心得超過 {cfg.gacha_xinde_half} "
        f"之後減半、最多補到 {cfg.gacha_xinde_cap}，滿了之後改給銀兩（{_by_tier(cfg.gacha_silver)}）",
        "**卡池**",
    ]
    members = state.player.members
    items = []
    for tier, ids in pool(content).items():
        names = "、".join(content.characters[cid].name + ("（已入門）" if cid in members else "") for cid in ids)
        items.append(f"- {tier}品（每人 {_pct(cfg.gacha_rates[tier] / len(ids))}）：{names}")
    return "\n\n".join(paras) + "\n\n" + "\n".join(items)


def cards_html(state: GameState, content: Content) -> str:
    """最近一次的結果卡（HTML），依抽到的順序：名字、品階、流派、統御、本命（黃品寫「本命　無」），
    以及「新入門」或「重複 → 心得 +50」「重複 → 銀兩 +50」。還沒抽過時是 NO_PULLS。"""
    pulls = state.player.gacha_last
    if not pulls:
        return f'<div class="gc-empty">{html.escape(NO_PULLS)}</div>'
    return f'<div class="gc-cards">{"".join(_card(content, x) for x in pulls)}</div>'


def _card(content: Content, x: Pull) -> str:
    ch = content.characters[x.character]
    innate = content.skills[ch.innate].name if ch.innate else "無"
    if x.new:
        result = '<div class="gc-result gc-new">新入門</div>'
    else:
        gain = f"銀兩 +{x.silver}" if x.silver else f"心得 +{x.xinde}"
        result = f'<div class="gc-result">重複 → {gain}</div>'
    return (
        f'<div class="gc-card {TIER_CLASS[ch.tier]}"><div class="gc-name">{html.escape(ch.name)}</div>'
        f"<div>{ch.tier}品・{ch.style}・統御 {ch.command}</div><div>本命　{html.escape(innate)}</div>{result}</div>"
    )


# 結果卡的樣式（介面層交給 gr.HTML 的 css_template，會自動限定在該元件內）。和 journal.CSS 一樣，
# 這裡不能出現反引號、「${」或「{{」；底色與框線用 Gradio 主題變數，品階只用左邊的色條區分。
CSS = """
.gc-cards { display: flex; flex-wrap: wrap; gap: 8px; }
.gc-card { flex: 0 1 150px; min-width: 130px; border: 1px solid var(--border-color-primary); border-left-width: 4px;
  border-radius: 8px; padding: 6px 10px; background: var(--background-fill-secondary); font-size: 13px; line-height: 1.6; }
.gc-name { font-weight: 600; font-size: 15px; }
.gc-t1 { border-left-color: #C9A227; }
.gc-t2 { border-left-color: #8B5CF6; }
.gc-t3 { border-left-color: #3B82F6; }
.gc-t4 { border-left-color: #9CA3AF; }
.gc-result { margin-top: 2px; }
.gc-new { font-weight: 600; color: #16A34A; }
.gc-empty { font-size: 13px; opacity: 0.7; }
"""
