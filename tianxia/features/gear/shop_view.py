"""馬市的店面畫面資料（店面獨立介面設計第三節；第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）。

只讀：不改數值、不碰亂數、不 import engine。店共用的（掌櫃那一句）在 core/shop_base。page 是店面那一頁的組法（Feature.shop_view 轉交；core/features.shop_page 問）。
靠 tianxia/shopview.py 那個殼的測試（tests/gear/test_four_tiers.py、test_weapons.py、tests/arts/test_renown_trade.py、tests/battle/test_tactics_bouts.py……）改這一檔時 test_for 挑不到：另外跑 scripts/test_for.py tianxia/shopview.py。
"""
from __future__ import annotations

from tianxia import equipment, mounts, territory
from tianxia.core.shop_base import line_text
from tianxia.models import Content
from tianxia.state import Equipment, GameState
from tianxia.world_state import WorldStateStore

# ── 馬市（第三節）──
NO_HORSE = "還沒有馬"  # 待 joy 潤：沒有馬時「你騎的」那一間
STALL_WHO = {"worn": "你騎的", "sale": "待售", "rack": "裝備庫"}  # 待 joy 潤：馬廄上那一行
ABILITY_NAMES = (("save", "省體力"), ("speed", "路上快"), ("cavalry", "決戰騎兵"), ("escape", "落敗脫身"))  # 同修練頁坐騎那一列（待 joy 潤）
FASTER, SLOWER, SAME = "比你騎的快", "比你騎的慢", "跟你騎的一樣快"  # 待 joy 潤：照卡上「路上快」那一條比（含飽足，FB-194）
HUNGRY_NOTE = "沒吃飽，四項本事都跟著打了折"  # 待 joy 潤：你騎的那匹飽足不到 100 時，飽足長條底下
BUY_TEXT = "買下 {price} 兩"  # 待 joy 潤
FEED_TEXT, WIELD_TEXT = "餵", "換上"  # 待 joy 潤


def _coat(item: Equipment) -> int:
    """馬廄裡那匹的毛色（畫法用）：名字開頭對上 mounts.COATS 的第幾個；名駒、名將贈禮的專名對不上是 -1（網頁畫成預設色）。"""
    return next((i for i, coat in enumerate(mounts.COATS) if item.name.startswith(coat)), -1)


def _bars(content: Content, item: Equipment) -> list[dict]:
    """四項本事的長條（第三節）：數字同修練頁那一列（mounts.abilities），value 是長條的寬（整數百分比，.5 進位同 mounts.pct）。"""
    got = mounts.abilities(content, item)
    return [{"key": key, "label": label, "value": mounts.half_up(got[key] * 100), "text": mounts.pct(got[key])} for key, label in ABILITY_NAMES]


def _speed_shown(content: Content, item: Equipment) -> int:
    """卡上「路上快」那一條寫的數（整數百分比，含飽足）：「比你騎的快／慢」照它比（FB-194）。"""
    return mounts.half_up(mounts.abilities(content, item)["speed"] * 100)


def _stall(content: Content, item: Equipment, role: str, sub: str, action: dict) -> dict:
    return {
        "id": item.id, "role": role, "who": STALL_WHO[role], "empty": False, "name": mounts.name_of(item), "grade": mounts.grade(item),
        "sub": sub, "coat": _coat(item), "art": mounts.art_of(item), "bars": _bars(content, item), "fed": None, "compare": "", "action": action,
    }


def market_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """馬市的店面（第三節）：一排馬廄——你騎的（沒有馬是一間空的）、馬販待售的那匹（mounts.shop_item）、裝備庫裡的馬一匹一間。
    每一間：名字、階品、四項本事的長條；你騎的那匹多飽足長條。卡上那一顆照現在的選項 id：你騎的「餵」（market:feed，做不了照
    mounts.feed_problem）、待售的「買下」（market:buy，mounts.buy_problem）、裝備庫裡的「換上」（market:wield:<id>，選單本來就每一匹
    各列一顆）與「比你騎的快／慢」（照卡上「路上快」那一條的數字比：乘了飽足、畫面上的整數百分比，卡上的數字與那一句對得上，FB-194；
    機器人換馬照舊比吃飽的腳力 mounts.better_mount）。focus：進門預設點著的那一間（你騎的，沒有馬就待售的）。world 沒用到（三間店同一個呼叫法）。"""
    p = state.player
    stalls: list[dict] = []
    if p.mount is not None:
        problem = mounts.feed_problem(state, content)
        worn = _stall(content, p.mount, "worn", mounts.grade(p.mount), {
            "id": mounts.FEED, "label": FEED_TEXT, "use": mounts.feed_note(state, content) if problem is None else "",
            "enabled": problem is None, "why": problem,
        })
        worn["fed"] = {"word": mounts.WEAR_WORD, "value": p.mount.edge, "note": HUNGRY_NOTE if p.mount.edge < 100 else ""}
        stalls.append(worn)
    else:
        stalls.append({"id": "", "role": "worn", "who": STALL_WHO["worn"], "empty": True, "name": NO_HORSE})
    sale, price = mounts.shop_item(state, content), mounts.price(state, content)
    problem = mounts.buy_problem(state, content)
    note = territory.price_note(state, content)  # 名聲 4.1：馬價後面寫原因
    stalls.append(_stall(content, sale, "sale", f"{mounts.TIER_NAMES.get(sale.tier, '')}・{price} 兩{note}", {
        "id": mounts.BUY, "label": BUY_TEXT.format(price=price), "use": "", "enabled": problem is None, "why": problem,
    }))
    ridden = _speed_shown(content, p.mount) if p.mount is not None else None
    for item in equipment.in_slot(p, "mount"):
        stall = _stall(content, item, "rack", mounts.grade(item),
                       {"id": f"{mounts.WIELD}{item.id}", "label": WIELD_TEXT, "use": "", "enabled": True, "why": None})
        if ridden is not None:
            mine = _speed_shown(content, item)
            stall["compare"] = FASTER if mine > ridden else SLOWER if mine < ridden else SAME
        stalls.append(stall)
    return {
        "shop": "market",
        "sign": f"{content.locations[p.location].name}{mounts.MARKET}",
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "market"),
        "back": mounts.BACK,
        "stalls": stalls,
        "focus": p.mount.id if p.mount is not None else sale.id,
    }


def page(ctx) -> dict:
    """馬市那一頁（原本 core/page_view.shop_view 最後那一句）。"""
    return market_view(ctx.state, ctx.content, ctx.world)
