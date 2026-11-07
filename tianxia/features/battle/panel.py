"""決戰的戰場面板（Joy 2026-11-06「大決戰優化：更讓玩家投入在決戰中」，設計稿 JsNAYuqgMn3JJoTENCKza6 方案甲）：江湖頁最上面那一塊——
一個倒數、兩邊上陣人物的血條、自己這一方的主將令、自己的陣中氣血、一回合一行的戰報，與關鍵時刻（開打、主將重創、主將敗走）的覆蓋要演的那幾件事。

只讀、不推進（同 view.battle_gauge：progress.battle_for_me(tick=False)）；數字都照這一場的資料原樣送，網頁不另算。
收場那一下的覆蓋不在這裡：收場之後這一場不再是「此刻看的那一場」，網頁照「剛剛」那張戰鬥卡片的戰局條（main.card_gauge）演。"""
from __future__ import annotations

import re

from . import generals, progress
from . import instance as battle_instance
from .view import gauge_of

HIT = re.compile(r"([^\s：，。、]+?)氣血 -(\d+)")  # 戰報裡打到上陣人物的那一截（「…直撲皇甫嵩：皇甫嵩氣血 -27…」、守將那一句同一個寫法）
FEED_ROUNDS = 3  # 面板上直接看得到的回合數（更早的收在場景卡的完整戰報裡）
HURT_MARKS = (50, 30)  # 主將氣血掉到這幾成時各演一次「重創」（設計稿第二節 ②）

# 主將喊的話（設計稿六之 4：先寫死；Joy 11/6 選方案甲時照推薦）。照人物 id 找，沒寫的照 OPEN_SAY／FALL_SAY 的通用句
OPEN_SAYS = {  # 待 joy 潤
    "huangfusong": "風起了。今夜，讓城下的黃巾見識官軍的火。",
    "zhujun": "諸君隨我壓上去，一步也別退！",
    "bocai": "黃天當立！把官軍趕回洛陽去！",
    "liupi": "兄弟們，跟著我殺！",
    "zhangjiao": "蒼天已死，黃天當立——今日便是甲子之日！",
    "zhangbao": "天兵在此，誰敢擋我？",
    "zhangliang": "人公將軍在此，殺！",
    "luzhi": "穩住陣腳，聽號令行事。",
    "zhangmancheng": "宛城是我們的，一寸也不讓！",
    "zhaohong": "替渠帥報仇！殺！",
    "hanzhong": "守住宛城，就是守住我們的命！",
    "sunjian": "江東孫文台在此，誰來一戰！",
}
OPEN_SAY = "眾將士聽令：今日一戰，定要{foe}片甲不留！"  # 待 joy 潤
FALL_SAYS = {  # 待 joy 潤
    "bocai": "撤……快撤！",
    "liupi": "撤！快撤！",
    "huangfusong": "傳令下去，退守營寨……",
    "zhujun": "可惡，先退一步！",
}
FALL_SAY = "撤！快撤！"  # 待 joy 潤


def _say(book: dict[str, str], fallback: str, fid: str, **kw) -> str:
    return (book.get(fid) or fallback).format(**kw)


def _viewer_side(ctx, battle) -> str | None:
    """同 view.battle_gauge：在場上看自己那一邊，還沒加入看自己陣營那一邊；攻城戰站不進任何一格的兩邊都不算我方。"""
    from . import siege_rules  # 攻城誰站哪一格

    p = battle.participants.get(ctx.state.player.name)
    side = p.faction if p is not None else ctx._side()
    if p is None and battle.siege is not None and not siege_rules.slots(battle.siege, ctx._conquest_side()):
        return None
    return side


def _chief(c) -> dict:
    return {
        "fid": c.fid, "name": c.name, "rank": generals.RANK_NAMES[min(c.rank, len(generals.RANK_NAMES) - 1)],
        "hp": round(c.neili), "cap": round(c.neili_cap), "fallen": c.fallen_round is not None, "by": c.felled_by,
    }


def _feed(battle, first: str, left: str, me) -> list[dict]:
    """最近 FEED_ROUNDS 回合，一回合一行（新的在前）：誰佔上風那一句（冒號前那一截）、打到上陣人物的那幾句、自己那一回合出了什麼。"""
    log, out = battle.narrative_log, []
    chiefs = [c.name for c in battle.commanders]
    side_of = {c.name: c.faction for c in battle.commanders}
    swings = {s.round: s.delta for s in battle.swings}
    for k, entry in enumerate(reversed(log[-FEED_ROUNDS:])):
        n = battle.round_number - k
        rows = [line for line in entry.split("\n") if line.strip()]
        if n <= 0 or not rows:
            continue
        head = rows[0].split("：", 1)[0].removeprefix("這一回合")
        delta = swings.get(n, 0)
        lead = "tie" if not delta else ("left" if (delta > 0) == (left == first) else "right")
        hits: dict[str, int] = {}  # 上陣人物這一回合被打掉多少（同一位好幾句加起來），一位一格
        falls = []
        for r in rows[1:]:
            for name, hp in HIT.findall(r):
                if name in chiefs:
                    hits[name] = hits.get(name, 0) + int(hp)
            if "陣前敗走" in r:
                falls.append(r)
        hits = [{"name": n, "hp": hp, "side": "left" if side_of.get(n) == left else "right"} for n, hp in hits.items()]
        mine = me.moves.get(n, "").split("；", 1)[0] if me is not None else ""
        out.append({"n": n, "lead": lead, "text": head, "hits": hits, "falls": falls, "mine": mine})
    return out


def _beats(battle, ctx, left: str, names: dict[str, str]) -> list[dict]:
    """關鍵時刻（設計稿第二節「關鍵時刻的覆蓋」）：開打、上陣人物血掉到五成／三成、敗走。每一件一個 id，網頁記得演過的不再演，
    同時好幾件沒演過只演最新的那一件（排在後面的）。"""
    if battle.phase != "active":
        return []
    out: list[dict] = []
    mine = [c for c in battle.commanders if c.faction == left]
    foes = [c for c in battle.commanders if c.faction != left]
    caller = min(mine or foes, key=lambda c: c.rank, default=None)
    foe = next((nm for fid, nm in names.items() if fid != (caller.faction if caller else left)), "敵軍")
    beat = {"id": "open", "kind": "open", "round": 0}
    if caller is not None:
        beat |= {"fid": caller.fid, "name": caller.name, "say": _say(OPEN_SAYS, OPEN_SAY, caller.fid, foe=foe)}
    if foes and mine:
        beat["foe"] = {"fid": min(foes, key=lambda c: c.rank).fid, "name": min(foes, key=lambda c: c.rank).name}
    out.append(beat)
    for c in battle.commanders:
        side = "left" if c.faction == left else "right"
        if c.fallen_round is not None:
            out.append({"id": f"fall:{c.fid}", "kind": "fall", "fid": c.fid, "name": c.name, "side": side,
                        "by": c.felled_by, "say": _say(FALL_SAYS, FALL_SAY, c.fid), "round": c.fallen_round,
                        "mine": c.felled_by == ctx.state.player.name})
            continue
        pct = round(100 * c.neili / c.neili_cap) if c.neili_cap else 100
        mark = min((m for m in HURT_MARKS if pct <= m), default=None)
        if mark is not None:
            out.append({"id": f"hurt:{c.fid}:{mark}", "kind": "hurt", "fid": c.fid, "name": c.name, "side": side,
                        "pct": pct, "round": battle.round_number})
    return sorted(out, key=lambda b: (b["round"], {"open": 0, "hurt": 1, "fall": 2}[b["kind"]]))


def battle_panel(ctx) -> dict | None:
    """江湖頁最上面的戰場面板（main.battle_panel）；沒有此刻看的那一場、序章裡是 None。"""
    status = progress.battle_for_me(ctx, tick=False)
    if status is None:
        return None
    battle, definition = status
    g = gauge_of(ctx, battle, definition, _viewer_side(ctx, battle))
    left, right = g["left"]["id"], g["right"]["id"]
    names = battle_instance.side_names(battle, definition)
    paused = ctx.world.paused_at()
    now = ctx.now if paused is None else paused
    if battle.phase == "muster":
        due, span = max(0, int(battle.muster_deadline_real - now)), int(definition.muster_seconds)
        sent = present = 0
        act = ""
    else:
        due, span = max(0, int(battle.round.opened_real + definition.round_seconds - now)), int(definition.round_seconds)
        sent, present = battle_instance.round_progress(battle, definition)
        act = battle_instance.current_act(battle, definition).title
    me = battle.participants.get(ctx.state.player.name)
    mine = me.faction if me is not None else _viewer_side(ctx, battle)
    caller = battle_instance.caller(battle, mine) if mine is not None else None
    move = battle.orders.get(mine) if mine is not None else None
    order = None
    if caller is not None and move and battle.phase == "active" and mine != battle_instance.GUARD:
        order = {"name": caller.name, "fid": caller.fid, "move": move, "pct": round(ctx.content.config.battle.generals.order_bonus * 100)}
    you = None
    if me is not None:
        tag = battle.round.pending_actions.get(me.name) if battle.phase == "active" else None
        picked = next((o for o in battle_instance.current_act(battle, definition).options if o.tag == tag), None) if tag else None
        # 送出了什麼：固定招寫招名，放手一搏寫「放手一搏」（待 joy 潤），逾時代選的不在這裡（那時已經結算了）
        sent_move = (picked.move or ("放手一搏" if picked.free_text else picked.text)) if picked is not None else (tag or None)
        you = {"hp": round(me.neili), "cap": round(me.neili_cap), "out": me.eliminated, "sent": sent_move,
               "side": "left" if me.faction == left else "right"}
    return {
        "key": f"{battle.record_id if battle.record_id is not None else battle.battle_id}:{battle.muster_deadline_real:.0f}",
        "name": g["name"], "phase": battle.phase, "round": g["round"], "total": g["total"], "act": act,
        "due": due, "span": span, "paused": paused is not None, "sent": sent, "present": present,
        "left": g["left"], "right": g["right"],
        "chiefs": {key: [_chief(c) for c in sorted(battle.commanders, key=lambda c: c.rank) if c.faction == fid]
                   for key, fid in (("left", left), ("right", right))},
        "order": order, "me": you,
        "feed": _feed(battle, definition.factions[0].id, left, me) if battle.phase == "active" else [],
        "beats": _beats(battle, ctx, left, names),
    }

