"""極限假人與測試玩家共用的量法（企劃者 2026-11-11「假人要對於各種狀態去測試我們功能的極限」、11/12「拿我們測試玩家的進度做到對比」）。

一個角色此刻的身家量成一列數字（snapshot），極限假人（scripts/limit_bots.py）每天量一次、測試玩家（scripts/tester_progress.py）
從主機那份資料庫量季末與行狀裡的等級里程碑。兩邊用同一支函式，數字才比得起來。只讀不改：不碰 Game.rng、不寫任何狀態。
"""
from __future__ import annotations

from tianxia.core import annal_base
from tianxia import insight_fx

MASTERED = annal_base.MASTERED  # 絕學（martial_arts.QUALITIES 的最後一品）

# 報告上的欄位：鍵 → (名字, 越大越強)。順序就是報告的順序
FIELDS: dict[str, str] = {
    "level": "等級",
    "exp": "經驗",
    "xinde": "心得",
    "silver": "銀兩",
    "fame": "名望",
    "contrib": "貢獻",
    "rank": "官階",
    "insights": "意境",
    "god_insights": "神品意境",
    "arts": "武學",
    "mastered": "絕學",
    "affinity_max": "最高情誼",
    "friends_80": "情誼 80 以上",
    "weapon_tier": "兵器階",
    "weapon_tempers": "兵器淬煉",
    "armor_tier": "防具階",
    "named_gear": "名器與本命",
    "treasure": "寶物",
    "figure_wins": "打贏大勢人物",
    "guard_qing": "親衛情分",
    "guard_tags": "親衛性向合計",
    "stat_points": "屬性點合計",
}


def snapshot(state, content=None) -> dict[str, float]:
    """一個角色此刻的身家。content 可以不給（主機端讀舊存檔時內容可能對不上）：只用存檔本身的欄位。"""
    p = state.player
    stats = p.stats
    gear = [g for g in (p.weapon, p.armor, *p.rack, *getattr(p, "held_gear", [])) if g is not None]
    guard = getattr(p, "guard", None)
    insights = list(p.insights) + [i for i in p.own_insights if i not in p.insights]
    return {
        "level": p.member.level,
        "exp": p.member.exp,
        "xinde": stats.get("xinde", 0),
        "silver": stats.get("silver", 0),
        "fame": stats.get("fame", 0),
        "contrib": p.contrib,
        "rank": p.rank,
        "insights": len(insights),
        "god_insights": sum(1 for i in insights if insight_fx.is_god(state, i)),
        "arts": len(set(p.arts) | {a for a in (p.member.neigong_id, getattr(p.member, "wugong_id", None)) if a}),
        "mastered": sum(1 for q in p.art_quality.values() if q == MASTERED),
        "affinity_max": max(p.affinities.values(), default=0),
        "friends_80": sum(1 for v in p.affinities.values() if v >= 80),
        "weapon_tier": p.weapon.tier if p.weapon else 0,
        "weapon_tempers": p.weapon.tempers if p.weapon else 0,
        "armor_tier": p.armor.tier if p.armor else 0,
        "named_gear": sum(1 for g in gear if g.secret or g.original or g.signature),
        "treasure": 1 if p.treasure else 0,
        "figure_wins": sum(p.figure_wins.values()),
        "guard_qing": guard.qing if guard else 0,
        "guard_tags": sum(guard.tags.values()) if guard else 0,
        "stat_points": sum(stats.get(k, 0) for k in ("str", "agi", "con", "wis", "lore")) + sum(p.attr_alloc.values()),
    }


def level_milestones(state) -> list[tuple[float, int]]:
    """行狀裡「到了第 N 級」的那幾則：[(世界秒, 等級)]。行狀只照 Config.biography.level_every 記里程碑（滿了先丟輕的）。"""
    out = []
    for e in state.player.annals:
        text = e.text
        if e.kind == annal_base.DEED and text.startswith("武藝精進，到了第 "):
            try:
                out.append((e.time, int(text.removeprefix("武藝精進，到了第 ").split(" ")[0])))
            except ValueError:
                continue
    return sorted(out)
