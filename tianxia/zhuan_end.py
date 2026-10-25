"""列傳為終點（減法季整合設計第九章；主機側計畫第八節，批 7b）：季末的列傳是一季的終點。

這一份管三件事（純規則；讀寫錢包、存檔的是 Game）：
- 四件只對準列傳的商品用掉的票（mall.EFFECTS 的 zhuan_art、zhuan_seal、zhuan_quote；購買那一列就是票，用了在那一列的 data
  記 used、season，親筆評曰另記 fid）：列傳插畫的圖庫鍵（illustration_for，<陣營>_<win|lose>，圖檔由雲端批 8 放
  web/img/zhuan/）、紀念印上的字（seal_text）、休季那三顆行動（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物>）。
- 深交上限（enforce_deep_cap）：同時情誼漲得過 Config.signature_affinity（70）的人物最多 Config.jianfa.deep_figures（3）位，
  深交名額（deep_slot，只這一季）每張多一位；第 4 位起情誼停在 69。情誼沒有單一的寫入口（計畫 8.0 第 5 條），所以在
  Game._log 裡事後夾（動作與同步都會走到）。
- 人物評曰（批 7b-2，見檔尾）。

開關是 Config.jianfa 的子開關 zhuan_end ＋ 開季的章（on → rules.jianfa）；關著什麼都不做、商城不上架這四件（MallWindow.rule）。
不讀時鐘、不碰 Game.rng。只 import models、state（wins、rules 在函式裡延後 import）。新寫給玩家看的字都待 joy 潤。"""
from __future__ import annotations

from .models import Content
from .state import GameState, WorldState

TITLE = "列傳"  # 江湖紀錄的標題（休季用票）
PREFIX = "zhuan:"
PICK_ART, SEAL = "zhuan:pick_art", "zhuan:seal"
QUOTE = "zhuan:quote:"
ART, SEAL_TICKET, QUOTE_TICKET, DEEP_SLOT = "zhuan_art", "zhuan_seal", "zhuan_quote", "deep_slot"  # mall.EFFECTS 的鍵
ART_DIR = "zhuan"  # 圖檔在 web/img/zhuan/<鍵>.webp（雲端批 8 放；沒有檔案時伺服器不給 src）
SEASON_NAME = "{scenario}・第 {n} 季"

# 待 joy 潤
ART_BUTTON = "用列傳插畫：列傳開頭配一幅水墨"
SEAL_BUTTON = "蓋紀念印：{seal}"
QUOTE_BUTTON = "請{name}寫一句親筆評曰（情誼 {value}）"
ART_DONE = "列傳開頭配上了一幅水墨。"
SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}。"
QUOTE_DONE = "你請{name}替你的列傳寫一句評曰。"
QUOTE_LATER = "你的列傳已經寫成，下一次重修時這一句才會寫進去。"
DEEP_FULL = "你已深交{n}位人物，{name}的情誼停在 {cap}。"
DEEP_NOTE = "已深交{n}位"
DEEP_TITLE = "深交"
_DIGITS = "〇一二三四五六七八九十"


def on(content: Content, world: WorldState | None) -> bool:
    from .rules import jianfa  # noqa: PLC0415

    return jianfa(content, world, "zhuan_end")


def _cn(n: int) -> str:
    return _DIGITS[n] if 0 <= n <= 10 else str(n)


# ── 列傳插畫與紀念印 ──


def illustration_for(state: GameState, content: Content, season: WorldState) -> str:
    """列傳插畫的圖庫鍵「<陣營>_<win|lose>」（第一批 6 張：三方各贏、各輸；設計第九章）。兩軍看結局贏的是不是自己；豪強看照哪一本論功
    （那一本是贏的那一軍才算贏；沒論功照此刻幫的那一軍）；和局都是 lose。散人、季還沒收是空字串。"""
    from .wins import winner_of  # noqa: PLC0415

    p = state.player
    faction = content.scenario.find_faction(p.faction)
    if faction is None or not season.ended:
        return ""
    winner = winner_of(season, content)
    if faction.allies:
        result = season.final_tiers.get(p.name)
        side = result.ledger_used if result is not None and result.ledger_used in faction.allies else p.ally
        won = winner is not None and side == winner
    else:
        won = winner == faction.id
    return f"{faction.id}_{'win' if won else 'lose'}"


def art_path(key: str) -> str:
    """圖庫鍵 → web/img 底下的路徑（不含副檔名）；伺服器照 scene_art 的做法看檔案在不在。"""
    return f"{ART_DIR}/{key}"


def seal_text(content: Content, season_number: int, profile: dict) -> str:
    """紀念印上的字：季名「黃巾之亂・第 N 季」，有論功時接名次與第幾階（照身家 annals.standing 的 tier_side、final_rank、tier）。"""
    from .wins import TIER_NAMES  # noqa: PLC0415

    parts = [SEASON_NAME.format(scenario=content.scenario.name, n=season_number)]
    if profile.get("final_rank"):
        parts.append(f"{profile.get('tier_side', '')}第 {profile['final_rank']} 名")
    if profile.get("tier"):
        parts.append(f"{TIER_NAMES[profile['tier']]}「{profile.get('tier_title', '')}」")
    return "・".join(parts)


def season_tickets(purchases, season: int) -> dict:
    """這一季用掉、沒退的票（Wallet.purchases 的那幾筆）：{"art": 用了插畫票, "seal": 用了紀念印, "quotes": [請了哪幾位人物]}。"""
    out = {"art": False, "seal": False, "quotes": []}
    for b in purchases:
        if b.refunded is not None or not b.data.get("used") or b.data.get("season") != season:
            continue
        if b.data.get(ART):
            out["art"] = True
        if b.data.get(SEAL_TICKET):
            out["seal"] = True
        if b.data.get(QUOTE_TICKET) and b.data.get("fid"):
            out["quotes"].append(b.data["fid"])
    return out


def unused(purchases, effect: str) -> list:
    """帶著 effect、沒退、還沒用掉的那幾筆（舊的在前；同 mall.tokens，只是拿已經讀好的那一份，不再讀資料庫）。"""
    return [b for b in reversed(purchases) if b.refunded is None and b.data.get(effect) and not b.data.get("used")]


def extras(content: Content, season_number: int, profile: dict, tickets: dict) -> dict:
    """列傳多畫的那幾樣（休季的 biography_entry、讀傳的 biography_view、公開頁都照它）：tier 季末論功（{tier, title, rank, of, side}；
    沒有階是 None）、illustration 插畫的圖庫鍵（第一階白送，或這一季用了插畫票；沒有是 None）、seal 紀念印的字（這一季蓋了才有）。"""
    tier = profile.get("tier") or 0
    art = profile.get("illustration") or None
    return {
        "tier": {"tier": tier, "title": profile.get("tier_title", ""), "rank": profile.get("final_rank", 0),
                 "of": profile.get("final_of", 0), "side": profile.get("tier_side", "")} if tier else None,
        "illustration": art if art and (tier == 1 or tickets.get("art")) else None,
        "seal": seal_text(content, season_number, profile) if tickets.get("seal") else None,
    }


def quote_figures(state: GameState, content: Content, taken: set[str]) -> list[tuple[str, int]]:
    """親筆評曰挑得到的人物（設計第九章：情誼 letter_affinity〔40〕以上、signature_affinity〔70〕以下；70 以上本來就白送）：
    [(人物 id, 情誼)]，情誼高的在前；taken 是這一季已經替你寫的（白送的與請過的）。"""
    low, high = content.config.figure_life.letter_affinity, content.config.signature_affinity
    picks = [(cid, v) for cid, v in state.player.affinities.items() if cid in content.characters and low <= v < high and cid not in taken]
    return sorted(picks, key=lambda x: (-x[1], x[0]))


# ── 深交上限 ──


def deep_cap(content: Content, slots: int = 0) -> int:
    return content.config.jianfa.deep_figures + max(0, slots)


def deep_pending(state: GameState, content: Content) -> bool:
    """此刻有沒有「情誼過了 70、還不在深交名單上」的人物（Game 先問這個，有才去讀錢包算名額）。"""
    p, edge = state.player, content.config.signature_affinity
    return any(v >= edge and cid in content.characters and cid not in p.deep_order for cid, v in p.affinities.items())


def enforce_deep_cap(state: GameState, content: Content, slots: int = 0) -> list[str]:
    """深交上限（企劃者 2026-10-24：同時情誼漲得過 signature_affinity 的人物最多 deep_figures 位，深交名額每張多一位）：
    還在 70 以上的照先來後到留在 PlayerState.deep_order（掉到 70 以下的讓出位子），新過 70 的照情誼高、id 排，有位子就進名單，
    沒位子就夾在 69、回一句。回這一下夾了誰的那幾句。"""
    p, edge = state.player, content.config.signature_affinity
    deep = {cid for cid, v in p.affinities.items() if v >= edge and cid in content.characters}
    order = [cid for cid in p.deep_order if cid in deep]
    fresh = sorted((cid for cid in deep if cid not in order), key=lambda cid: (-p.affinities[cid], cid))
    cap = deep_cap(content, slots)
    lines: list[str] = []
    for cid in fresh:
        if len(order) < cap:
            order.append(cid)
            continue
        p.affinities[cid] = edge - 1
        lines.append(DEEP_FULL.format(n=_cn(cap), name=content.characters[cid].name, cap=edge - 1))
    p.deep_order = order
    return lines


def deep_note(state: GameState, content: Content, cid: str, slots: int = 0) -> str:
    """人物頁（談話畫面名字旁的情誼）多寫的「已深交三位」：深交名單滿了、這一位不在名單上、情誼已經停在門檻下面那一格才寫；其餘是空字串。"""
    p, edge = state.player, content.config.signature_affinity
    cap = deep_cap(content, slots)
    if cid in p.deep_order or len(p.deep_order) < cap or p.affinities.get(cid, 0) < edge - 1:
        return ""
    return DEEP_NOTE.format(n=_cn(cap))
