"""江湖水漲（企劃者 2026-10-14「玩家變強後好像也沒有更高的挑戰」；數字與量到的原因在 Config.rise）：
大場面、頭目戰、事件檢定跟得上變強的人。純數字，不碰狀態以外的東西、不擲亂數；威力由呼叫端（Game）算好傳進來。

- 大場面（挑戰大勢人物本人、劇情戰的大場面）：難度＝max(內容寫的, 全隊威力 × 倍數)，倍數照你這一季打贏他幾次往上加（big）。
- 頭目戰：他的難度＝max(內容寫的, 你的武學威力 × duel_scale ×（1＋duel_per_meet × 之前遇上幾次）)（duel）。
- 事件檢定：本人等級到了就加深幾點（event_bump）。
只 import models、state。"""
from __future__ import annotations

from .models import Content
from .state import GameState


def on(content: Content) -> bool:
    return content.config.rise.enabled


def draw_floor(content: Content) -> float | None:
    """挑戰大勢人物本人的僵持下緣（encounter.Mods.draw_floor）：江湖水漲開著時收窄到 figure_draw，關著是 None（照一般的 −50%）。"""
    return content.config.rise.figure_draw if on(content) else None


def scale(content: Content, wins: int = 0) -> float:
    """大場面的倍數：big_scale 起，每打贏一次加 per_win，最多 max_scale。"""
    rule = content.config.rise
    return min(rule.max_scale, rule.big_scale + rule.per_win * max(0, wins))


def big(content: Content, base: float, power: float, wins: int = 0) -> float:
    """大場面這一場的難度：內容寫的與「全隊威力 × 倍數」取大的；開關關著照內容寫的。"""
    if not on(content):
        return base
    return max(base, power * scale(content, wins))


def duel(content: Content, base: float, power: float, meets: int = 0) -> float:
    """頭目的難度：內容寫的與「你的武學威力 × duel_scale（第二次遇上再多一截）」取大的。meets 是這一場之前這一季遇上他幾次。"""
    if not on(content):
        return base
    rule = content.config.rise
    return max(base, power * rule.duel_scale * (1 + rule.duel_per_meet * max(0, meets)))


def event_bump(state: GameState, content: Content) -> int:
    """事件檢定加深幾點：本人第 event_from_level 級起每 event_per_levels 級 +1，最多 event_cap。"""
    if not on(content):
        return 0
    rule = content.config.rise
    level = state.player.member.level
    if level < rule.event_from_level:
        return 0
    return min(rule.event_cap, 1 + (level - rule.event_from_level) // rule.event_per_levels)
