"""地盤畫面的資料（功能包 territory_acts；全部拆包第 46 批）：領地爭奪的 main_view 那一格（時程表、每一塊的翻地資料、能不能下戰書）與管理者頁的下拉選單。
原本 Game 上的 conquest_view、_siege_you／region_name／live／join／margin、admin_conquest_choices。只讀。
"""
from __future__ import annotations

from tianxia import atlas  # 共用規則層（輿圖資料 atlas，第 50 批收進）
from tianxia import battle_instance, conquest
from tianxia import ranks  # 共用規則層（階級 ranks，第 40 批收進）
from tianxia.models import Content

from . import conquest_day, letter_actions

SIEGE_STATUS = {"planned": "未開", "waiting": "即將集結", "open": "集結・交戰中", "void": "作罷"}
SIEGE_TAKEN = "{side}拿下"
SIEGE_HELD = "守住了"


def siege_status_text(content: Content, slot) -> str:
    """時程表上一場攻城的狀態那幾個字（待 joy 潤）。"""
    if slot.status == "done":
        return SIEGE_TAKEN.format(side=content.scenario.faction_name(slot.winner, slot.winner)) if slot.winner else SIEGE_HELD
    return SIEGE_STATUS.get(slot.status, "")


def conquest_view(ctx) -> dict | None:
    """領地爭奪的畫面資料（server.main_view 的 conquest；輿圖第 3、4 批畫）：today 是時程表（戰書排的攻城：地點、攻方、時刻、狀態、誰下的），
    blocks 是每一塊的翻地資料（conquest.block_view：誰佔著、開季的種類、每一條進度、冷卻幾分、被哪一場戰書凍結〔時刻照 stamp_text〕、正在推的人、
    激戰、每一邊的集火、看的人攻或守推不推得動與原因），here 是自己腳下那一塊（不是區塊是 None），letter 是自己能不能下戰書（只有在任的第 4 階
    有 can／why 與自己那一邊進度到門檻的塊）。開關關著、季收了是 None。誰推的只寫名號，真人假人一樣。"""
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.ended or w.conquest is None:
        return None
    side = ctx._conquest_side()
    names = {f.id: f.name for f in c.scenario.factions}
    live = siege_live(ctx) if any(slot.status == "open" for slot in w.conquest.schedule) else None
    today = [{
        "id": slot.id, "loc": slot.loc, "place": c.locations[slot.loc].name,
        "attackers": [names.get(a, a) for a in slot.attackers], "time": ctx.stamp(slot.at), "minute": slot.minute,
        "status": slot.status, "status_text": siege_status_text(c, slot),
        "by": {names.get(a, a): conquest_day.BY_WORDS.get(slot.by.get(a, ""), "") for a in slot.attackers},
        # 輿圖第三版第 5 批（卡上「戰書／攻城／攻城戰果」那一段）：sides 是攻方的陣營 id；you 是看的人站得進哪一格（siege.slots 同一套：
        # 攻方 attack、被打的那一方 defend、散人與不是兩軍的人 help〔臨時投效或助守〕、另一軍站不進去是空的）；margin 是打完那一場的大勝／險勝
        "sides": list(slot.attackers), "you": siege_you(ctx, slot, side), "margin": siege_margin(ctx, slot),
        # FB-690：region 是那一塊的大區名（加入要人在那一區）；join 是集結・交戰中那一場看的人此刻加不加得進去（_siege_join）
        "region": region_name(ctx, slot.loc), "join": siege_join(ctx, slot, side, live),
    } for slot in w.conquest.schedule]
    blocks: dict[str, dict] = {}
    for loc in conquest.blocks(c):
        row = conquest.block_view(w, c, loc, side)
        if row["frozen"] is not None:
            row["frozen"]["time"] = ctx.stamp(row["frozen"].pop("at"))
        row["holder_name"] = names.get(row["holder"], "") if row["holder"] else ""
        for line in row["bars"]:
            line["name"] = names.get(line["side"], line["side"])
        blocks[loc] = row
    p = ctx.state.player
    here = blocks.get(p.location) if p.journey is None else None
    letter = None
    if side is not None and ranks.rank_of(ctx.state) == ranks.SEAT_RANK:
        ready = [loc for loc in conquest.blocks(c) if conquest.bar(w, loc, side) >= c.config.conquest.letter_at]
        letter = {"used": w.conquest.letter_days.get(side) == letter_actions.letter_key(ctx), "at": c.config.conquest.letter_at,
                  "ready": [{"id": loc, "name": c.locations[loc].name, "why": letter_actions.letter_problem(ctx, loc) or ""} for loc in ready]}
    return {"today": today, "blocks": blocks, "here": here, "letter": letter, "muster": c.config.conquest.muster_minutes}

def siege_you(ctx, slot, side: str | None) -> str:
    """看的人站得進這一場攻城的哪一格（卡上那顆鈕寫什麼；siege.slots 同一套）：攻方 attack、此刻佔著那一塊的那一軍 defend、
    散人與不是兩軍的人 help（臨時投效攻方或助守）、另一軍站不進去是空字串。打完、作罷的也照算（卡上那時不畫鈕）。"""
    if side is None:
        return "help"
    if side in slot.attackers:
        return "attack"
    return "defend" if conquest.holder(ctx.state.world, ctx.content, slot.loc) == side else ""

def region_name(ctx, loc_id: str) -> str:
    region = atlas.region_of(ctx.content, loc_id) if loc_id in ctx.content.locations else None
    return region.name if region is not None else ""

def siege_live(ctx) -> tuple[list[battle_instance.BattleInstance], set[int]]:
    """此刻集結或開打的全服戰鬥（決戰與攻城）與自己此刻加得進去的那幾場的流水號（_joinable：人在那一區、不在路上、站得進去、
    還沒在任何一場的名單上）。conquest_view 有集結・交戰中的攻城時才讀一次。"""
    showdown = ctx.world.get_battle()
    live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + ctx._sieges()
    return live, {b.record_id for b in ctx._joinable()}

def siege_join(ctx, slot, side: str | None, live) -> str:
    """FB-690：集結・交戰中那一場看的人此刻加不加得進去（卡上那顆鈕照它畫，跟江湖頁的加入鈕同一套 _joinable）：go＝加得進去、
    in＝已經在這一場、busy＝已經在別的一場、far＝站得進去但人不在那一區（或在路上）、空字串＝站不進去（另一軍）或不是集結・交戰中。"""
    if slot.status != "open" or live is None or not siege_you(ctx, slot, side):
        return ""
    battles, joinable = live
    battle = next((b for b in battles if b.siege is not None and slot.record_id is not None and b.record_id == slot.record_id), None)
    if battle is None:
        return ""
    name = ctx.state.player.name
    if name in battle.participants:
        return "in"
    if any(name in b.participants for b in battles):
        return "busy"
    return "go" if battle.record_id in joinable else "far"

def siege_margin(ctx, slot) -> str:
    """打完那一場的大勝／險勝（收場那一下 siege._note_result 記在 day_log）；還沒打完、作罷、找不到是空字串。"""
    if slot.status != "done" or ctx.state.world.conquest is None:
        return ""
    return next((n.margin for n in reversed(ctx.state.world.conquest.day_log)
                 if n.result and n.key == slot.key and n.loc == slot.loc and n.minute == slot.minute), "")

def admin_choices(ctx) -> dict | None:
    """設定頁管理者工具「領地爭奪」那一組的下拉選單（server.admin_choices 的 conquest；打開領地爭奪，PM 2026-10-22）：只在領地爭奪開著、
    季還沒收的季有，其餘 None（網頁不畫）。blocks 是搶得下來的區塊（字寫此刻歸誰、每一條進度、冷卻、被戰書凍結），sides 是交戰兩軍
    （admin_conquest_set／progress／letter 只收這兩軍），sieges 是時程表上還沒打完、沒作罷的攻城（admin_conquest_cancel 的 id）。
    只給管理者看；字待 joy 潤。"""
    c, w = ctx.content, ctx.state.world
    if not conquest.on(c, w) or w.ended or w.conquest is None:
        return None
    names = {f.id: f.name for f in c.scenario.factions}
    blocks = []
    for loc in conquest.blocks(c):
        if not conquest.capturable(c, loc):
            continue
        held = conquest.holder(w, c, loc)
        bits = [names.get(held, held) if held else "沒人佔"]
        bits += [f"{names.get(s, s)} {conquest._int(v)}" for s, v in sorted(conquest.bars(w, loc).items(), key=lambda kv: (-kv[1], kv[0]))]
        if conquest.cooling(w, c, loc):
            bits.append(f"冷卻 {conquest.cooling_minutes(w, c, loc)} 分")
        if conquest.frozen(w, loc) is not None:
            bits.append("戰書凍結")
        name = c.locations[loc].name  # 問句寫地名（label 後面的括號不能拿來切：潁川郡（陽翟）自己就有括號）
        blocks.append({"id": loc, "name": name, "label": f"{name}（{'・'.join(bits)}）"})
    sides = [{"id": s, "label": names.get(s, s)} for s in conquest.SIDES]
    sieges = [{
        "id": slot.id,
        "label": f"{c.locations[slot.loc].name}：{'、'.join(names.get(a, a) for a in slot.attackers)}攻・{siege_status_text(c, slot)}・{ctx.stamp(slot.at)}",
    } for slot in w.conquest.schedule if slot.status not in ("done", "void")]
    return {"blocks": blocks, "sides": sides, "sieges": sieges}
