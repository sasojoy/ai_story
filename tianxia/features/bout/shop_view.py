"""擂台的店面畫面資料（擂台賽設計；Joy 2026-10-14「擂台應該要是獨立的一頁」；第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）。

只讀：不改數值、不碰亂數、不 import engine。page 是店面那一頁的組法（Feature.shop_view 轉交；core/features.shop_page 問）。
靠 tianxia/shopview.py 那個殼的測試（tests/gear/test_four_tiers.py、test_weapons.py、tests/arts/test_renown_trade.py、tests/battle/test_tactics_bouts.py……）改這一檔時 test_for 挑不到：另外跑 scripts/test_for.py tianxia/shopview.py。
"""
from __future__ import annotations

from tianxia import tactics
from tianxia.characters import name_key
from tianxia.core import duel_base as duel_rules  # 單挑底層（全部拆包第 12 批進核心）：氣勢的一句話、選單上的一招
from tianxia.models import MOVES, Content
from tianxia.state import GameState
from tianxia.world_state import WorldStateStore

from . import arena_rules as arena

# ── 擂台（擂台賽設計；Joy 2026-10-14「擂台應該要是獨立的一頁，你這樣太混雜了」）：跟三間店同一層，台下、擂台榜兩頁，打到一半整頁是這一場 ──
ARENA_SIGN = "江湖擂台"  # 待 joy 潤：招牌（擂台哪裡都上得了，不寫地名）
ARENA_LINES = {  # 待 joy 潤：主事那一句（照你此刻的情形，不擲骰）
    "new": "擂台主事拱手：「報上名號、留個分身守擂，排到榜尾；往前三名內的人，你都挑得。」",
    "joined": "擂台主事拱手：「台上的人都留了分身。贏了，名次跟他換。」",
    "top": "擂台主事拱手：「天下第一，就等著別人來挑了。」",
    "fight": "台下圍了一圈人，等著看這一場。",
    "won": "台下一陣喝采。",
    "lost": "台下有人搖頭，也有人替你可惜。",
    "drew": "台下議論紛紛，分不出高下。",
}
YIELD_ASK = "認輸下台？這一場算你落敗。"  # 待 joy 潤：認輸先問一次
NO_ENTRY = "你還沒報名守擂。報了名排到榜尾，挑得了排在你前面三名內的人，旁人也挑得到你的分身。"  # 待 joy 潤
JOIN_NOTE = "報名、更新分身、挑擂都不花體力，一天挑 {n} 次；分身照此刻的身手，名次與戰績不動。"  # 待 joy 潤
NOBODY_YET = "擂台榜上還沒有人。"  # 待 joy 潤
WAGES_NOTE = "每天 00:00 照名次發俸：第一名銀兩 {silver}、名望 {fame}；前 {n} 名都有。"  # 待 joy 潤：擂台榜底下


def _fight_view(state: GameState, content: Content) -> dict:
    fight = state.player.arena
    log = list(fight.lines)
    lock = tactics.locks(fight.bout)  # 本命戰法（第二批）：使不出來的招灰掉、身上的狀態、看穿了架勢一定是真的
    return {
        "id": fight.id,  # 擂台動畫：認是不是同一場（換一場從頭演）
        "looks": arena.looks_view(fight.looks, fight.skins, fight.fx),  # 擂台動畫：兩邊手上的兵器種類與形象
        "picks": [list(x) for x in fight.picks],  # 擂台動畫：每回合兩邊出的招（照招演）
        "bursts": [list(x) for x in fight.bursts],  # 招式動畫：每回合兩邊綁了招式的那一門發動了沒（發動了才疊光效）
        "foe": fight.foe.name,
        "arts": list((state.world.arena.get(fight.foe_key).arts if state.world.arena.get(fight.foe_key) else [])),
        "round": fight.round + 1,
        "rounds": fight.rounds,
        "edge": round(fight.edge),
        "edge_words": duel_rules.edge_words(fight.edge),
        "me": {"name": state.player.name, "hp": round(fight.me.hp), "cap": round(fight.me.hp_cap)},
        "foe_hp": {"name": fight.foe.name, "hp": round(fight.foe.hp), "cap": round(fight.foe.hp_cap)},
        "tell": fight.tell,
        "tell_note": (tactics.SEEN_NOTE if lock.sees else arena.TELL_NOTE).strip("（）"),
        "status": tactics.status_text(fight.bout),
        "howto": arena.HOWTO,
        "log": log,
        "moves": [{"id": f"arena:{m}", "move": m, "label": duel_rules.move_label(m) + (tactics.lock_note(m) if m in lock.no_moves else ""),
                   "enabled": m not in lock.no_moves} for m in MOVES],
        "yield": {"id": arena.YIELD_ID, "label": "認輸", "confirm": YIELD_ASK},
        "gamble": {"op": "duel_text", "prompt": arena.PROMPT_SHORT, "note": arena.GAMBLE_NOTE,
                   "locked": tactics.NO_GAMBLE.strip("（）") if lock.no_gamble else ""},
    }


def _ring_short(w, me: str, foe, content: Content, left: int, problem: str | None) -> list[str] | None:
    """挑不了的那一顆鈕上寫的兩行（粗字、小字）：冷卻寫還要等多久、次數用完寫幾點換日（Joy 2026-10-16「看不出還有多久才能打」）；
    整句原因照舊在 why。挑得了是 None。"""
    if problem is None:
        return None
    if left <= 0:
        return ["明日 00:00", "今天挑完了"]
    wait = arena.cool_left(w, me, foe, content.config.arena)
    if wait > 0:
        return [arena.wait_text(wait / content.config.time_scale) + "後", "可再挑"]
    return [problem, ""]


def arena_view(state: GameState, content: Content, world: WorldStateStore, power: float, left: int, bare: float | None = None) -> dict:
    """擂台那一頁：打到一半是這一場（fight）；不然是台下（自己的名次、稱號與分身，報名鈕，挑得到的人各一張、挑擂鈕）與擂台榜（board），
    剛打完的那一場有收場卡（result，PlayerState.arena_last）。鈕都是現在的選項 id（arena:join、arena:fight:<名號鍵>、arena:<招>、
    arena:yield、arena:back），挑不挑得了照 arena.challengers（同選單）。left 是今天還能挑幾次。只讀。
    bare：自己不含玉璽碎片戰力的威力（改版 FB-625：挑人卡上的「身手」兩邊都照不含碎片的算）；不給就是 power。"""
    p, w, cfg = state.player, state.world, content.config.arena
    mine = arena.entry_of(w, p.name)
    result = p.arena_last
    if p.arena is not None:
        mood = "fight"
    elif result is not None:
        mood = "won" if result.tier in arena.WIN_TIERS else "drew" if result.tier == "僵持" else "lost"
    else:
        mood = "new" if mine is None else "top" if mine.rank == 1 else "joined"
    me = {
        "joined": mine is not None,
        "rank": mine.rank if mine is not None else None,
        "title": arena.title_for(mine.rank) if mine is not None else None,
        "record": arena.record_text(mine) if mine is not None else "",
        "arts": list(mine.arts) if mine is not None else [],
        "note": JOIN_NOTE.format(n=cfg.per_day) if mine is not None else NO_ENTRY,
        "join": {"id": arena.JOIN_ID, "label": "更新分身" if mine is not None else "報名守擂", "enabled": power > 0,
                 "why": None if power > 0 else arena.NO_ARTS},
    }
    foes = []
    for e, problem in arena.challengers(w, content, p.name, left):
        foes.append({
            "id": f"arena:fight:{name_key(e.name)}", "name": e.name, "rank": e.rank, "title": arena.title_for(e.rank),
            "record": arena.record_text(e), "arts": list(e.arts), "strength": "身手" + arena.strength_words(content, power if bare is None else bare, e.shown),
            "enabled": problem is None, "why": problem, "short": _ring_short(w, p.name, e, content, left, problem),
            "famed": arena.FAMED_NOTE.format(n=arena.reach_of(e, cfg)) if e.famed else "",  # 名聲 4.7
        })
    nobody = ""
    if mine is not None and not foes:
        nobody = arena.NOBODY if mine.rank == 1 else arena.NOBODY_AHEAD
    rows = [dict(row, me=name_key(row["name"]) == name_key(p.name)) for row in arena.board(w, cfg)]
    top_silver, top_fame = cfg.wages[0] if cfg.wages else (0, 0)
    return {
        "shop": "arena",
        "sign": ARENA_SIGN,
        "silver": p.stats.get("silver", 0),
        "purse": f"今天還能挑 {left} 次" if left > 0 else arena.SPENT_PURSE,
        "line": ARENA_LINES[mood],
        "back": arena.BACK_ID,
        "me": me,
        "foes": foes,
        "nobody": nobody,
        "board": rows,
        "board_empty": "" if rows else NOBODY_YET,
        "wages": WAGES_NOTE.format(silver=top_silver, fame=top_fame, n=len(cfg.wages)) if cfg.wages else "",
        "fight": _fight_view(state, content) if p.arena is not None else None,
        "result": {"id": result.id, "foe": result.foe, "tier": result.tier, "lines": list(result.lines),
                   "changes": list(result.changes), "looks": arena.looks_view(result.looks, result.skins, result.fx), "picks": [list(x) for x in result.picks], "bursts": [list(x) for x in result.bursts]} if result is not None and p.arena is None else None,
    }


def page(ctx) -> dict:
    """擂台那一頁（原本 core/page_view.shop_view 那一支）。arena_actions 在函式裡 import，免得多一條最外層的路。"""
    from . import arena_actions  # noqa: PLC0415

    s, c = ctx.state, ctx.content
    return arena_view(s, c, ctx.world, ctx._battle_power(), arena_actions.arena_left(ctx), bare=ctx._battle_power(seal=False))
