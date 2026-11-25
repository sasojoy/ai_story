"""合璧榜（意境合成改版批四）：這一季全服合出過的意境，誰首創、合璧成神過幾回、第一個成神的是誰。只讀，不叫模型。

資料：意境本身在這一季的 insights 表（WorldStateStore.merged_insights，照登記的先後）；合璧成神的紀錄在 WorldState.he_gods
（fusion._v2_compound 合璧成神那一下記）。改版沒開的季沒有這一頁（路由回 404）。"""
from __future__ import annotations

from tianxia import fusion, insight_fx
from tianxia.content import Content
from tianxia.state import GameState
from tianxia.world_state import WorldStateStore


def on(content: Content, state: GameState) -> bool:
    return fusion.v2_on(content, state)


def rows(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """{rows: [...], gods: 這一季合璧成神幾回}。每一列：意境名、路、首創（論武的兩個人）、成神幾回、第一個成神的人與他悟出的真意、
    自己是不是成神過。成神過的排前面（回數多的先），其餘照合出來的先後。"""
    gods_of = state.world.he_gods
    me = state.player.name
    out = []
    for order, ins in enumerate(world.merged_insights()):
        gods = gods_of.get(ins.id, [])
        first = gods[0] if gods else None
        top = insight_fx.grand(content, first[1]) if first else None
        makers = [n for n in (ins.creator_shown or ins.creator, ins.co_creator) if n]
        out.append({
            "name": ins.name, "path": ins.attribute, "by": makers, "gods": len(gods),
            "first": first[0] if first else None, "grand": top.name if top is not None else None,
            "mine": any(g[0] == me for g in gods), "_order": order,
        })
    out.sort(key=lambda r: (-r["gods"], r["_order"]))
    for r in out:
        del r["_order"]
    return {"rows": out, "gods": sum(r["gods"] for r in out)}
