"""裝備的唯讀畫面資料（全部拆包第 42 批）：修練頁「裝備」那一塊、見聞「榜單」的神器譜。原本 Game 上的 2 個方法，Game 留兩個一行委派給 server
（menxia_view 的 gear 鍵、/api/boards 最後一張）。計畫 docs/superpowers/plans/2026-11-07-裝備包-第1批.md 1.1。第一個參數 ctx 是 Game。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import forge_secrets  # 共用規則層
from tianxia import art_cards  # 共用規則層（裝備那一塊的列）

from . import signature_arms

if TYPE_CHECKING:
    from tianxia.engine import Game


def gear_rows(ctx: Game) -> dict:
    """修練頁「裝備」那一塊的資料（art_cards.gear_rows；裝備四欄設計 2.5）。"""
    return art_cards.gear_rows(ctx.state, ctx.content, ctx.world)


def divine_book_view(ctx: Game) -> list[dict]:
    """見聞「榜單」的神器譜（打造隱藏配方設計 5.5；Joy 2026-10-17「神器譜移到排行榜」，原本接在江湖史後面）：跨季，新的一季在前，
    同一季打出來的神器在前、名將本命兵器在後。一筆 {season, name, text, ref}（ref 認那一把，點開看卡用，leaderboard.gear_card）；都沒有是空的。"""
    rows = forge_secrets.divine_entries(ctx.world.divine_records())
    rows += signature_arms.book_entries(ctx.content, ctx.world.signature_records())
    rows.sort(key=lambda row: -row[0])  # 穩定排序：同一季照原來的先後
    return [{"season": season, "name": name, "text": text, "ref": ref} for season, name, text, ref in rows]
