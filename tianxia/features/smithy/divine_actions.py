"""神器原品定名與以器配招（全部拆包第 41 批）：修練頁裝備庫那一列的表單，或「沿用譜名」那一顆。沒有模型、不是三段式（smithing.name_divine 只過
naming.name_problem 與 forge_secrets.divine_name_problem），所以不在鎖外。原本 Game 上的 2 個方法，Game 留 name_divine、bind_art 的一行委派
（連同 @_not_while_preparing 裝飾器）給 server、假人（bot.keep_book_names）與測試。計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.1。
第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING



from . import smithing

if TYPE_CHECKING:
    from tianxia.engine import Game


def name_divine(ctx: Game, item_id: str, name: str = "", keep: bool = False) -> list[str]:
    """神器原品定名（smithing.name_divine；修練頁裝備庫那一列的表單，或「沿用譜名」那一顆）：定成了才寫江湖紀錄，
    江湖史與傳聞寫進共用賽季所以要存回（不合格、被用掉、不是你的都只回一句話）。"""
    xinde = ctx._xinde()
    ok, msgs = smithing.name_divine(ctx.state, ctx.content, ctx.world, item_id, name, keep=keep)
    msgs = ctx._log(msgs)
    if ok:
        ctx._menxia_entry(msgs[0], xinde)
        ctx._save_season()
    return msgs


def bind_art(ctx: Game, item_id: str, art_id: str) -> list[str]:
    """以器配招（玩家武學追上本命定案 四；smithing.bind_art）：神器原品綁自己一門有絕招的絕學。綁成了才寫江湖紀錄。"""
    xinde = ctx._xinde()
    ok, msgs = smithing.bind_art(ctx.state, ctx.content, ctx.world, item_id, art_id)
    msgs = ctx._log(msgs)
    if ok:
        ctx._menxia_entry(msgs[0], xinde)
    return msgs
