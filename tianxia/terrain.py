"""武學隨地理環境（地利；企劃者 10/17 清單第 36 項，計畫 docs/superpowers/plans/2026-10-18-武學隨地理環境.md）。

一般的仗（遊歷、出陣、探索撞上的野怪、練功、劇情戰、挑戰大勢人物本人：走 team._styled_fighters 的那幾種）裡，本人與出戰同伴
身上的武學、內功一門一門比這一地最濃的意境（insights.strong_of）：同一路 ×Config.terrain_arts.match、被它剋 ×clash，其餘不動。
武學的倍數乘在武學威力、內功的乘在內功威力（encounter.Boost.outer_scale／inner_scale）。部下不吃；決戰、擂台、頭目戰、
奪璽單挑、護衛、切磋、截殺、設伏都不經 _styled_fighters，不算；江湖水漲浮難度用的 power_vs(terrain=False) 不算。不擲骰。

這裡只有數字與字：哪一處最濃（strong_at、here）、一門的倍數（factor）、戰報那一句（note）、輿圖那一行（place_line）。
team 反過來呼叫它（把兩門的屬性傳進來），這個模組只 import models、state、insights、martial_arts。"""
from __future__ import annotations

from collections.abc import Sequence

from .insights import strong_of
from .martial_arts import ATTRIBUTE_COUNTERS, counters
from .models import Content, InsightDef
from .state import GameState

PLACE_LINE = "此地{name}氣最濃：{good}的功夫在這裡得勢，{bad}的施展不開。"  # 輿圖地利那一行（待 joy 潤）


def strong_at(content: Content, loc_id: str | None) -> InsightDef | None:
    """這一處的地利照哪一個意境：開關開著、意境提示開著（strong_of 自己問）、不是序章專屬的地方，才回最濃的那一個。"""
    if not content.config.terrain_arts.enabled or loc_id is None:
        return None
    loc = content.locations.get(loc_id)
    if loc is None or loc.prologue_only:
        return None
    strong = strong_of(loc, content)
    return content.insights.get(strong) if strong is not None else None


def here(state: GameState, content: Content) -> InsightDef | None:
    """玩家此刻腳下的地利；在路上沒有地點，也就沒有地利。"""
    p = state.player
    return None if p.journey is not None else strong_at(content, p.location)


def side(attribute: str | None, strong: InsightDef | None) -> str | None:
    """那一門跟這裡的意境：同一路 "match"、被它剋 "clash"、不相干（或沒有那一門、沒有地利）None。"""
    if attribute is None or strong is None:
        return None
    if attribute == strong.attribute:
        return "match"
    return "clash" if counters(strong.attribute, attribute) else None


def factor(attribute: str | None, content: Content, strong: InsightDef | None) -> float:
    """那一門在這裡的威力倍數。"""
    cfg = content.config.terrain_arts
    return {"match": cfg.match, "clash": cfg.clash}.get(side(attribute, strong), 1.0)


def note(
    content: Content, strong: InsightDef | None, mine: Sequence[str | None], mates: Sequence[tuple[str, Sequence[str | None]]],
) -> list[str]:
    """戰報那一句（計畫 2.2）：一場最多一句。本人兩門（mine：屬性）有一門同一路寫那一句、否則有一門被剋寫相剋那一句；
    本人兩門都沒吃到時，第一位有一門同一路的同伴（mates：(名字, 兩門的屬性)）寫同伴那一句；都沒有是空的。不寫倍數。"""
    if strong is None:
        return []
    lines = content.config.terrain_arts.lines
    sides = {side(a, strong) for a in mine}
    for key in ("match", "clash"):
        if key in sides:
            text = lines.get(f"{key}:{strong.id}")
            return [text] if text else []
    name = next((who for who, attrs in mates if any(side(a, strong) == "match" for a in attrs)), None)
    text = lines.get("mate_match")
    return [text.format(name=name)] if name is not None and text else []


def place_line(content: Content, loc_id: str) -> str:
    """輿圖上這一處地利那一行（不帶標題）：「此地水氣最濃：柔勁的功夫在這裡得勢，剛猛的施展不開。」；沒有地利是空字串。
    被剋的那一路照 ATTRIBUTE_COUNTERS 反查（最濃的那一種剋誰）。"""
    strong = strong_at(content, loc_id)
    if strong is None:
        return ""
    words = content.config.terrain_arts.words
    bad = ATTRIBUTE_COUNTERS.get(strong.attribute, "")
    return PLACE_LINE.format(name=strong.name, good=words.get(strong.attribute, strong.attribute), bad=words.get(bad, bad))
