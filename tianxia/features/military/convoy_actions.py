"""押糧（功能包 military；全部拆包第 33 批；護糧，軍令文件 3.4）：接下糧車、走到終點交糧車。原本 Game 上的 2 個方法（_take_convoy、_convoy_arrives；後者第 26 批起經事件 arrive 的 convoy 那一格叫、委派拿掉）；
名字去掉前導底線。第一個參數是 ctx。會改狀態（扣糧草、記捐獻與貢獻、軍令記功、可能打一場截糧）。押著的糧車記在 PlayerState.convoy（這一包認領）。
"""
from __future__ import annotations

from tianxia import materials, team, wins
from tianxia import orders  # 共用規則層（軍令 orders，第 40 批收進）
from tianxia.rules import front_of
from tianxia.state import Convoy, PlayerState


def take_convoy(ctx) -> list[str]:
    """接下糧車（護糧，軍令文件 3.4）：交出 convoy_grain 份糧草（從低階的慢屬性素材用起，多的不找），記下要送到哪裡。
    不花體力；抵達終點才算數（見 convoy_arrives）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    escort = orders.escort_at(s, c, ctx._side(), p.location)
    need = c.config.convoy_grain
    if escort is None or p.convoy is not None or not materials.take_grain(s, c, need):
        return ["（這裡沒有糧車可接。）"]
    p.convoy = Convoy(order=escort.id, grain=need, from_loc=p.location, to_loc=escort.end)
    text = f"你把 {need} 份糧草裝上車，要送到{c.locations[escort.end].name}。路上當心截糧的。"
    return [text]


def convoy_arrives(ctx, loc_id: str) -> list[str]:
    """糧車到了終點（路過也算）：先有 convoy_ambush_chance 機率撞上敵方截糧隊（探索撞上野怪的打法：不推大勢、
    扣氣血打折），打輸糧車被劫、不算數；打贏或沒遇上就交進營中——記捐獻（軍備文件 4.1）、記一次推動的貢獻、
    替它自己那一道護糧記一次（RF4：已經換週清掉就不算）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    convoy = p.convoy
    if convoy is None or convoy.to_loc != loc_id:
        return []
    p.convoy = None
    msgs: list[str] = []
    enemy = orders.ambusher(c, ctx._side())
    if enemy is not None and ctx.rng.random() < c.config.convoy_ambush_chance:
        msgs.append("快到營門時，半路殺出一隊截糧的人馬！")
        msgs += ctx._squad_encounter(enemy, wild=True)
        if s.battles[0].tier not in team.WIN_TIERS:
            return msgs + ["糧車被劫走了，這一趟不算數。"]
    key = f"{loc_id}:糧草"
    p.donations[key] = p.donations.get(key, 0) + convoy.grain
    # 護糧沒有推動，另記一次第 1 階推動的貢獻（總計畫 T6）
    wins.credit(p, c, s.world, orders.week_of(s, c), c.config.contrib_per_push)
    msgs.append(f"糧車送進了{c.locations[loc_id].name}，一粒不少。")
    return msgs + ctx._order_credit(kind="convoy", location=loc_id, front=front_of(c, loc_id), order=convoy.order)


def defect_clear(p: PlayerState) -> None:
    """叛投 clear 位置的 convoy 那一格（core_effects：全部拆包第 32 批；MilitaryFeature.defection() 登記；原本 defection.clear_progress 那一行）：
    護糧軍令就是押著的糧車（Convoy.order），清的是 convoy；軍令記下的貢獻（contrib、contrib_weeks）在叛投自己的 progress 那一格清。
    不問開關（原位本來就不看：押糧關著也照清）。"""
    p.convoy = None  # 押著的糧車留給舊陣營，交出去的糧草不退【預設】
