"""行狀的查詢與行狀頁那一半（全部拆包第 29 批之二；列傳包 features/zhuan）。

收季時的身家（profile）、季末論功的那幾樣（standing、tier_*）、〈天下形勢〉寫到名號（xingshi_notes）、行狀頁要畫的列（rows）。
記一筆行狀的那一半（note、entry、watch 與種類常數）在 tianxia/core/annal_base.py。原本寫在 tianxia/annals.py，一個字沒改
（延後 import 改成絕對路徑）。
"""
from __future__ import annotations

import re

from tianxia.core.annal_base import KINDS, TIER, XINGSHI, clip, figure_name, note
from tianxia.models import Content
from tianxia.state import GameState, WorldState

TIER_LINE = "季末論功，{who}出力排第 {rank}（共 {of} 人），得{tier}「{title}」。"  # 待 joy 潤
TIER_GENTRY = "替{side}"  # 豪強照哪一本排：替哪一軍（和局兩本合計寫 TIER_BOTH）
TIER_BOTH = "替兩軍"
XINGSHI_LINE = "名號上了〈天下形勢〉第 {n} 篇：「{said}」"  # 待 joy 潤：said 是文章裡寫到名號的那一句
XINGSHI_SAID_MAX = 50


def profile(state: GameState, content: Content, season: WorldState | None = None) -> dict:
    """收季時這個人的身家（存進 biographies.profile，季末寫傳時當開頭與結尾的材料）。不讀 state.world：換季那一刻 state.world
    不一定是那一季的。season 是那一季的 WorldState：列傳為終點開著（減法季批 7b，zhuan_end）時多貢獻與季末論功（standing）；
    沒給、關著一個鍵都不多。"""
    from tianxia import ranger, renown

    p = state.player
    sect = content.sects.get(p.sect) if p.sect else None
    extra = standing(state, content, season) if season is not None and _zhuan_end(content, season) else {}
    return {
        "name": p.name,
        "faction": content.scenario.faction_name(p.faction, "") if p.faction else "",
        "sect": sect.name if sect is not None else "",
        "rank": p.rank,
        "level": p.member.level,
        "fame": p.stats.get("fame", 0),
        "good": p.stats.get("good", 0),
        "evil": p.stats.get("evil", 0),
        "ranger": ranger.title(content, state) or renown.virtue_title(state, content) or "",  # 名聲開著時寫善惡稱號
        "team": [figure_name(content, cid) for cid in p.team],
        "showdowns": p.showdowns,
        "top_merits": p.top_merits,
        "bounties": p.bounties_done,
        "start": content.scenario.start_location,
        "place": (content.locations[p.location].name if p.location in content.locations else ""),
        **extra,
    }


def _zhuan_end(content: Content, season: WorldState | None) -> bool:
    from tianxia.rules import jianfa  # noqa: PLC0415  rules 那一側很大，延後 import

    return jianfa(content, season, "zhuan_end")


def standing(state: GameState, content: Content, season: WorldState) -> dict:
    """季末論功的那幾樣（減法季批 7b；profile 開著時接在後面）：contrib 這一季的貢獻；有論功（投靠了劇本裡的陣營、四勝利開著）時多
    ledger_used 照哪一本排、tier_side 那一本寫給人看的（「官軍」「替官軍」「替兩軍」）、final_rank 第幾名、final_of 那一池幾人、
    tier 第幾階（0 是沒到門檻）、tier_title 稱號（WorldState.final_tiers）。投靠了劇本裡的陣營、季收了的多 illustration：列傳插畫的
    圖庫鍵（zhuan_end.illustration_for；第一階白送、買了插畫票的休季用掉才畫）。有人替你寫評曰的多 verdicts（zhuan_end.writers：
    [{fid, reason}]，批 7b-2）。"""
    from tianxia.core.services import illustration_for, writers  # noqa: PLC0415

    p = state.player
    out: dict = {"contrib": p.contrib}
    art = illustration_for(state, content, season)
    if art:
        out["illustration"] = art
    free = writers(state, content, season)  # 季末替你寫評曰的人物（批 7b-2；買了請的照票，不在這裡）：以前的季照這一份開單
    if free:
        out["verdicts"] = [{"fid": w.fid, "reason": w.reason} for w in free]
    result = season.final_tiers.get(p.name)
    if result is not None:
        out.update(ledger_used=result.ledger_used, tier_side=_tier_side(state, content, result.ledger_used), final_rank=result.rank,
                   final_of=result.of, tier=result.tier, tier_title=result.title)
    return out


def _tier_side(state: GameState, content: Content, ledger_used: str | None) -> str:
    """照哪一本排寫給人看的：兩軍寫陣營名，豪強寫替哪一軍（和局兩本合計寫「替兩軍」）。"""
    from tianxia.wins import BOTH  # noqa: PLC0415

    p, scenario = state.player, content.scenario
    faction = scenario.find_faction(p.faction)
    if ledger_used == BOTH:
        return TIER_BOTH
    if faction is not None and faction.allies and ledger_used:
        return TIER_GENTRY.format(side=scenario.faction_name(ledger_used, ledger_used))
    return scenario.faction_name(p.faction, "") if p.faction else ""


def tier_text(state: GameState, content: Content, season: WorldState) -> str:
    """季末論功那一則行狀的字（有階才有；沒有是空字串）。"""
    from tianxia.wins import TIER_NAMES  # noqa: PLC0415

    result = season.final_tiers.get(state.player.name)
    if result is None or not result.tier:
        return ""
    return TIER_LINE.format(who=_tier_side(state, content, result.ledger_used), rank=result.rank, of=result.of,
                            tier=TIER_NAMES[result.tier], title=result.title)


def tier_note(state: GameState, content: Content, season: WorldState) -> bool:
    """收季之後記一則季末論功（TIER，份量 5，時刻是收季那一刻）：列傳為終點開著、季收了、有階、還沒記過才記。記了回 True。"""
    if not (season.ended and _zhuan_end(content, season)) or any(e.kind == TIER for e in state.player.annals):
        return False
    text = tier_text(state, content, season)
    if not text:
        return False
    note(state, content, TIER, text, 5, place="", time=season.time)
    return True


def _said(text: str, name: str) -> str:
    """文章裡寫到名號的那一句（到句號、問號、驚嘆號為止，句尾的標點拿掉：行狀接進傳裡時後面會補「。」），太長照 XINGSHI_SAID_MAX 截；
    找不到是空字串。"""
    for sentence in re.split(r"(?<=[。！？])", text):
        if name in sentence:
            return clip(sentence.strip().rstrip("。！？"), XINGSHI_SAID_MAX)
    return ""


def xingshi_notes(state: GameState, content: Content, season: WorldState) -> bool:
    """〈天下形勢〉寫到你的名號（減法季批 7b；判斷同網頁推送 notices.current：文章或「是日」那一句寫到名號）：上一次看到第幾篇
    （PlayerState.xingshi_seen）之後收下的每一篇各記一則（XINGSHI，份量 3，時刻是收下那一刻），再記下看到哪一篇。
    列傳為終點關著什麼都不做。記了回 True。"""
    p = state.player
    if not _zhuan_end(content, season) or not p.name:
        return False
    fresh = [e for e in season.xingshi if e.n > p.xingshi_seen]
    if not fresh:
        return False
    noted = False
    for essay in fresh:
        if p.name in essay.essay or p.name in essay.line:
            said = _said(essay.essay, p.name) or _said(essay.line, p.name)
            note(state, content, XINGSHI, XINGSHI_LINE.format(n=essay.n, said=said), 3, place="", time=essay.time)
            noted = True
    p.xingshi_seen = max(e.n for e in fresh)
    return noted


# ── 行狀頁（季中先看，不叫模型）──────────────────────


def rows(state: GameState, content: Content) -> list[dict]:
    """行狀頁要畫的：照時間先後，一則一列（種類的小標、時刻、地點、人物名、事實、你說的、他回的、份量）。"""
    return [
        {
            "kind": KINDS.get(e.kind, e.kind), "when": e.when, "place": e.place,
            "figure": figure_name(content, e.figure) if e.figure else "", "text": e.text,
            "quote": e.quote, "reply": e.reply, "weight": e.weight,
        }
        for e in sorted(state.player.annals, key=lambda e: e.time)
    ]
