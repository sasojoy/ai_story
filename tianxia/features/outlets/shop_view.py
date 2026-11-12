"""軍需帳與打點的店面畫面資料（素材與經濟 B6；21 天季的銀兩出口；第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）。

只讀：不改數值、不碰亂數、不 import engine。店共用的（掌櫃那一句、素材格的排序、階名）在 core/shop_base。page 是店面那一頁的組法（Feature.shop_view 轉交；core/features.shop_page 問）。
包外讀這一檔的測試改這一檔時 test_for 挑不到：另外跑 `git grep -l outlets_shop -- tests tianxia/features` 列的那幾個。
"""
from __future__ import annotations

from tianxia import economy, equipment, four_tiers, rules, silver
from tianxia import prologue as prologue_rules
from tianxia.core.shop_base import TIER_NAMES, attribute_rank, line_text
from tianxia.models import Content
from tianxia.state import GameState

# ── 軍需帳（素材與經濟 B6，企劃者 2026-10-15 選草圖 B3）──
DONATE_SIGN = "{place}・{faction}軍需帳"  # 待 joy 潤：招牌
DONATE_CAP = "背包的素材（點一下挑要捐的；{points}）"  # 待 joy 潤
DONATE_EMPTY = "背包裡沒有素材。"  # 待 joy 潤
DONATE_TIER4_ONLY = "軍需官只收一到三階的料，四階的留著打神器。"  # 待 joy 潤（FB-343）：背包裡只剩四階（四階不能捐，正式季整合 4.6）
# 軍需帳最上面那一格還沒捐時的一句（捐了換成結果；待 joy 潤）：第一季規則開著時記貢獻
DONATE_HINT = "捐的記進陣營的軍備，也替陣營推一點大勢。"  # 豪強照依附的那一邊推；這裡不寫「戰線」（大本營不一定在戰線上）
DONATE_HINT_S1 = "捐的記成貢獻、記進陣營的軍備，也替陣營推一點大勢。"


def dadian_view(state: GameState, content: Content, *, day: int, room: int, base: bool, clinic: bool, smith: bool,
                bribe: list[str], prologue: bool) -> dict:
    """「打點」那一間店（21 天季的銀兩出口；企劃者挑第 9 批畫面乙：茶樓雅間、一本攤開的帳簿）：Game.shop_view 在這間店開著時給。
    五樣都列：左頁「修為」名師指點、看火候、買破境丹，右頁「人情」打點門路（此地談得上話的每一位一筆）、捐銀兩。每一筆
    {id（這裡按得下的選項 id，做不了是 None）, name, price, desc, tick, ok, note（做不了的原因或去處）}：按得下去的送原本的選項 id；
    這裡做得了但被擋（今天請過了、錢不夠）的照 silver 的原因寫，這裡做不了的寫去哪裡做（silver.WHERE）。身上掛著還沒用掉的寫在帳底下（hang）。
    base／clinic／smith 是此地有沒有自家大本營、醫館、鐵匠鋪（Game 判），bribe 是此地打點得了的大勢人物，day 是回體丹的換日。"""
    p, cfg = state.player, content.config.silver_outlets

    def entry(oid, name, price, desc, tick, here, problem, where):
        ok = here and problem is None
        return {"id": oid if ok else None, "name": name, "price": price, "desc": desc, "tick": tick, "ok": ok,
                "note": "" if ok else (problem if here else where)}

    odds = cfg.furnace_odds
    pill = content.config.legend_item_name
    left = [
        entry("act:mentor", "名師指點", f"{cfg.mentor_silver} 兩", silver.MENTOR_DESC.format(bonus=cfg.mentor_bonus), silver.ONCE_DAILY,
              clinic, silver.mentor_problem(state, content, day) if clinic else None, silver.WHERE["mentor"]),
        entry("act:furnace", "看火候", f"{cfg.furnace_silver} 兩",
              silver.FURNACE_DESC.format(low=f"{odds.get('下品', 0):g}", mid=f"{odds.get('中品', 0):g}", high=f"{odds.get('上品', 0):g}"),
              silver.ONCE_DAILY, smith, silver.furnace_problem(state, content, day, prologue) if smith else None, silver.WHERE["furnace"]),
        entry("act:buy_legend", f"買{pill}", f"{cfg.legend_silver} 兩", silver.LEGEND_DESC,
              silver.LEGEND_LEFT.format(left=silver.legend_left(state, content)), clinic,
              silver.legend_problem(state, content) if clinic else None, silver.WHERE["legend"]),
    ]
    right = []
    for fid in bribe:
        name, cid = content.figures[fid].name, content.figures[fid].character
        now = p.affinities.get(cid, 0)
        right.append(entry(f"act:bribe:{fid}", f"打點門路・{name}", f"{cfg.bribe_silver} 兩",
                           silver.BRIBE_DESC.format(name=name, now=now, then=now + silver.bribe_gain(state, content, fid), top=cfg.bribe_max),
                           silver.BRIBE_DAILY, True, silver.bribe_problem(state, content, fid, day), ""))
    if not bribe:
        right.append(entry(None, "打點門路", f"{cfg.bribe_silver} 兩", silver.BRIBE_DESC_AWAY.format(gain=cfg.bribe_affinity, top=cfg.bribe_max),
                           silver.BRIBE_DAILY, False, None, silver.WHERE["bribe"]))
    donated = p.silver_donated if p.silver_donate_day == day else 0
    tick = silver.DONATE_LEFT.format(left=max(0, cfg.donate_daily_silver - donated))
    problem = silver.donate_problem(state, content, day, room, content.config.economy.donate_daily_cap) if base else None
    if base and problem is None:
        tick = f"{silver.DONATE_NOW.format(silver=silver.donate_amount(state, content, day, room))}・{tick}"
    if content.config.economy.donate:  # 捐軍備關著（Joy 2026-11-12「捐軍備功能先拿掉」）：捐銀兩那一格也不列
        right.append(entry("act:silver_donate", "捐銀兩", f"每 {cfg.donate_per_point} 兩", silver.DONATE_DESC.format(per=cfg.donate_per_point),
                           tick, base, problem, silver.WHERE["donate" if p.faction else "donate_ranger"]))
    hang = [line for ready, line in ((p.mentor_ready, silver.HANG_MENTOR), (p.furnace_ready, silver.HANG_FURNACE)) if ready]
    return {
        "shop": "dadian", "sign": silver.SHOP, "silver": p.stats.get("silver", 0), "line": line_text(state, content, "dadian"),
        "back": "dadian:back",
        "pages": [{"head": silver.PAGE_SELF, "entries": left}, {"head": silver.PAGE_FAVOR, "entries": right}],
        "hang": silver.HANG_HEAD + "・".join(hang) if hang else "",
    }


def donate_view(state: GameState, content: Content, day: int) -> dict:
    """大本營的軍需帳（素材與經濟設計第六節；Game.shop_view 在軍需官那一串開著時給）：招牌、軍需官那一句、出店（donate:back）、
    陣營四種軍備的存量（同銀兩出口包 armament_view 的順序）、今天還能捐幾點與上限，背包裡每一種素材一格（照剛柔快慢、再照階排：份量、
    今天最多收得下幾個 take〔economy.donate_take〕、捐不了的原因〔economy.donate_problem〕、進哪一樣軍備）。捐出送
    MAIN_ACTIONS["donate"] 的 items（挑好的幾種一起捐，一則紀錄）。day 是回體丹的換日。"""
    p = state.player
    econ = content.config.economy
    stock = state.world.armaments.get(p.faction or "", {})
    cells = []
    for material, held in sorted(
        ((content.materials[mid], n) for mid, n in p.materials.items() if n > 0 and mid in content.materials),
        key=lambda pair: (attribute_rank(pair[0].attribute), pair[0].tier, pair[0].id),
    ):
        points = economy.donate_points(content, material.id)
        if points <= 0:
            continue
        cells.append({
            "id": material.id, "name": material.name, "attribute": material.attribute, "tier": material.tier,
            "tier_word": TIER_NAMES.get(material.tier, ""), "have": held, "points": points,
            "take": economy.donate_take(state, content, material.id, held, day),
            "problem": economy.donate_problem(state, content, material.id, day),
            "armament": economy.armament_of(content, material.attribute) or economy.DONATE_MISC,
        })
    points_text = "、".join(f"{TIER_NAMES[t]} {n} 點" for t, n in sorted(econ.donate_points.items()) if t in TIER_NAMES)
    room = economy.donate_room(state, content, day)
    return {
        "shop": "donate",
        "sign": DONATE_SIGN.format(place=content.locations[p.location].name, faction=content.scenario.faction_name(p.faction or "", "")),
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "donate"),
        "back": "donate:back",
        "stock": [{"name": name, "attribute": attribute, "points": stock.get(attribute, 0)} for attribute, name in econ.armaments.items()],
        "room": room,
        "cap": econ.donate_daily_cap,
        "room_text": economy.DONATE_LEFT.format(n=room) if room > 0 else economy.DONATE_FULL.format(cap=econ.donate_daily_cap),
        "caption": DONATE_CAP.format(points=points_text),
        "hint": DONATE_HINT_S1 if rules.season_one(content, state.world) else DONATE_HINT,
        "empty": DONATE_TIER4_ONLY if not cells and any(  # FB-343：只剩四階時說四階不收，不說沒有素材
            n > 0 and four_tiers.tier4_id(content, mid) for mid, n in p.materials.items()) else DONATE_EMPTY,
        "cells": cells,
    }


def page(ctx, shop: str) -> dict:
    """軍需帳、打點那一頁（原本 core/page_view.shop_view 那兩支）。silver_actions 在函式裡 import，免得多一條最外層的路。"""
    from . import silver_actions  # noqa: PLC0415

    s, c = ctx.state, ctx.content
    if shop == "donate":
        return donate_view(s, c, ctx._pill_day())
    day = ctx._pill_day()
    base = ctx._at_own_base()
    return dadian_view(s, c, day=day, room=economy.donate_room(s, c, day) if base else 0, base=base,
                       clinic=ctx._at_clinic_town(), smith=equipment.smith_open(s, c), bribe=silver_actions.bribe_targets(ctx),
                       prologue=prologue_rules.active(s, c))
