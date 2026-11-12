"""稱號與官職的動作（設計稿 v5）：同步時的每週結算、此刻戴哪一個（含名號簿與紀錄）、換戴、狀態列的資料。
只 import 核心、共用規則層與自己這一包。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import journal, leaderboard
from tianxia.characters import CharacterStore
from tianxia.rules import add_rumor

from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def mandate_names(ctx: Game) -> list[str]:
    """受命於天：這一季天命之爭定下來那一刻手上有碎片的人，而且自己就在得天命的那一軍（玉璽登記的 mandate 那一筆）。"""
    p = ctx.state.player
    if not p.faction or not hasattr(ctx.world, "seal_state"):
        return []
    number = ctx.world.get_season_number()
    for e in reversed(ctx.world.seal_state().registry.history):
        if e.kind == "mandate" and e.season == number:
            return list(e.holders.values()) if e.result and e.result == p.faction else []
    return []


def _board(ctx: Game) -> dict[str, list]:
    store = CharacterStore(ctx.world.db) if hasattr(ctx.world, "db") else None
    return leaderboard.compute_boards(ctx.content, ctx.world, store, top=None)


def settle(ctx: Game) -> bool:
    """季曆換週之後第一個同步的人替全服結算週名號（頒給這一刻的名次），寫江湖傳聞、存回共用賽季。結算了回 True。"""
    c, w = ctx.content, ctx.state.world
    if not rules.due(c, w):
        return False
    new = rules.holders_from(c, w, _board(ctx))
    for line in rules.rumors(w.titles_holders, new):
        add_rumor(ctx.state, line, content=c)
    w.titles_holders = new
    w.titles_week = rules.week_of(c, w)
    ctx._save_season()
    return True


def choices(ctx: Game) -> list[dict]:
    return rules.available(ctx.state, ctx.content, mandate_names(ctx))


def wear(ctx: Game) -> list[str]:
    """照此刻手上有的換上該戴的那一個；新拿到的名號收進名號簿（一則紀錄）、戴著的那一個沒了寫一句。回寫進紀錄的那幾行。"""
    p = ctx.state.player
    held = choices(ctx)
    lines: list[str] = []
    for t in held:
        if t["id"] in (rules.OFFICIAL, rules.SEASON_TITLE):
            continue  # 官職跟著階走、論功的稱號換季時已經記過，都不收進名號簿
        entry = rules.book_entry(p.season_number, t["name"])
        if entry not in p.title_book:
            p.title_book.append(entry)
            lines.append(rules.GOT_LINE.format(title=t["name"]))
            if t["id"] in rules.BY_ID and rules.BY_ID[t["id"]].span == rules.SEASON:
                add_rumor(ctx.state, rules.RUMOR_SEASON.format(name=p.name, title=t["name"]), content=ctx.content)
    now = rules.pick_worn(held, p.titles_pin)
    old = dict(p.titles_worn)
    worn = {k: now[k] for k in ("id", "name", "grade")} if now else {}
    if old and old.get("id") not in {t["id"] for t in held}:
        lines.append(rules.LOST_LINE.format(
            old=old.get("name", ""), now=rules.NOW_WEAR.format(title=now["name"]) if now else rules.NOW_NONE))
    if p.titles_pin and p.titles_pin not in {t["id"] for t in held}:
        p.titles_pin = ""  # 挑的那一個沒了：回到自動（下次拿到不會自己跳回去，免得一直換來換去）
    p.titles_worn = worn
    if lines:
        head = ctx.state.journal[0] if ctx.state.journal else None
        if head is not None and head.battle_id is not None and head.battle_id == ctx.state.battle_card:
            # 最新一則是「剛剛」那張戰鬥卡片（例：決戰收場那一下頒了名號）：接在那一則後面，不另起一則把卡片蓋掉
            journal.add_guide(ctx.state, lines)
        else:
            ctx._write(rules.JOURNAL_TITLE, lines)
    return lines


def on_sync(ctx: Game) -> None:
    settle(ctx)
    wear(ctx)


def set_pin(ctx: Game, tid: str) -> list[str]:
    """換戴：tid 是手上有的那一個的 id，"" 是自動（戴最高檔的）。"""
    if not rules.on(ctx.content):
        return [rules.PIN_BAD]
    p = ctx.state.player
    held = choices(ctx)
    if tid and tid not in {t["id"] for t in held}:
        return [rules.PIN_BAD]
    p.titles_pin = tid
    wear(ctx)
    if not tid:
        return [rules.PIN_AUTO]
    return [rules.PIN_OK.format(title=p.titles_worn.get("name", ""))]


def view(ctx: Game) -> dict:
    """江湖畫面頂層的 titles（換戴那一格與狀態列頭銜讀它）。"""
    return rules.view(ctx.state, choices(ctx))


def worn_of(state) -> dict:
    """別人讀的那一格（名帖、玩家卡、決戰、榜單）：存檔裡此刻戴著的（{"id","name","grade"}），沒戴是 {}。"""
    return dict(state.player.titles_worn)
