"""修練頁的換上、餵馬、拆解（全部拆包第 42 批；裝備四欄設計 2.3、5.4、4.8；兵器設計 2.2、4.7.1；鐵匠鋪與合成流程 3.4 批量拆解）。原本 Game 上的 4 個方法，
Game 留四個一行委派給 server（MENXIA_ACTIONS 的 wield、feed、dismantle、dismantle_many）、假人（bot.feed_mount、bot.wear_better）與測試。
計畫 docs/superpowers/plans/2026-11-07-裝備包-第1批.md 1.1。第一個參數 ctx 是 Game（手冊 3.3）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import equipment  # 共用規則層
from tianxia import mounts  # 共用規則層
from tianxia.core.services import not_while_preparing  # 核心

if TYPE_CHECKING:
    from tianxia.engine import Game


def wield_weapon(ctx: Game, item_id: str) -> list[str]:
    """修練頁的「換上」（兵器設計 2.2、裝備四欄設計 2.3）：武器、防具、寶物哪裡都能換（含路上、閉關中；寶物不設限制，企劃者 2026-10-11），
    坐騎路上不能換（equipment.wield 擋）、不花體力，換進那一件自己的欄位；寫一則修練紀錄。網頁照舊送 weapon 這個鍵
    （MENXIA_ACTIONS["wield"]），防具（甲:N）、坐騎（騎:N）、寶物（寶:N）的 id 也走它。"""
    msgs = ctx._log(equipment.wield(ctx.state, ctx.content, item_id, equipment.WIELDABLE))
    if msgs and msgs[0].startswith("你換上了"):
        ctx._menxia_entry(msgs[0], ctx._xinde())
    return msgs


def feed_mount(ctx: Game) -> list[str]:
    """修練頁坐騎那一列的「餵」（裝備四欄 5.4，MENXIA_ACTIONS["feed"]）：閒著時哪裡都能餵（不在路上、不在閉關），
    一個一階素材餵滿、不花銀兩；寫一則修練紀錄。整季機器人與假人也走這裡（bot.feed_mount）。"""
    msgs = ctx._log(mounts.feed(ctx.state, ctx.content))
    if msgs and msgs[0].startswith(mounts.FED_PREFIX):
        ctx._menxia_entry(msgs[0], ctx._xinde())
    return msgs


def dismantle_weapon(ctx: Game, item_id: str) -> list[str]:
    """修練頁裝備庫的「拆解」（兵器設計 4.7.1、裝備四欄設計 4.8）：武器、防具哪裡都能拆、不花體力；坐騎、寶物不能拆；寫一則修練紀錄。"""
    msgs = ctx._log(equipment.dismantle(ctx.state, ctx.content, item_id, equipment.DISMANTLABLE))
    if msgs and msgs[0].startswith(equipment.DISMANTLE_PREFIX):
        ctx._menxia_entry(msgs[0], ctx._xinde())
    return msgs


@not_while_preparing
def dismantle_many(ctx: Game, item_ids: list[str]) -> list[str]:
    """批量拆解（鐵匠鋪與合成流程 3.4；MENXIA_ACTIONS["dismantle_many"]，見 equipment.dismantle_many）：裝備庫裡勾好的一次拆完，
    照 melt_many 的做法——拆不了的跳過寫原因、拆成了寫一則修練紀錄（標記是那一句總結）。同 dismantle_weapon 不擋地點、不花體力。"""
    held = len(ctx.state.player.rack)
    msgs = ctx._log(equipment.dismantle_many(ctx.state, ctx.content, item_ids))
    if len(ctx.state.player.rack) < held:
        ctx._menxia_entry(msgs[0], ctx._xinde())
    return msgs
