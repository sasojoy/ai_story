"""慢慢長出來的純規則（Joy 2026-11-25 對提案表 https://claude.ai/artifact/YUs4edGz4zdhy4pckYeYCv 的三個決定：
商城越快越好、舊角色不要收、說明框一起換）。

新角色（開關開著、站在城門口還沒選路的那一刻）拿到一本 UnfoldBook；之後每次同步、每做一件事看一次身上的東西，
用得到的區塊就長出來（寫進 grown，同時進 fresh 亮紅點，點開那一塊才滅）。長出來就不收回。
沒有這一本的角色（舊角色、假人）全部照舊攤開。純函式、不碰時鐘與模型。

區塊鍵跟網頁 shown() 用的是同一套（底部分頁「tab:<id>」；俠客頁的子分頁「hero:<key>」；俠客頁進去的那幾頁「self:<id>」）。
不在 KEYS 裡的鍵一律照舊畫（江湖頁上的區塊歸江湖頁重排那一條，讀同一本、鍵名另外加）。
"""
from __future__ import annotations

from tianxia.state import GameState, UnfoldBook

# 這一包會藏起來的區塊（順序＝大約會碰到的先後；畫面不看順序）。不在這裡的鍵一律照舊畫
KEYS: tuple[str, ...] = (
    "tab:map",  # 輿圖：開局挑了路、第一封託付信要你去別的地方
    "hero:attrs",  # 屬性：第一次升級、手上有點可配
    "hero:gear",  # 裝備：第一次拿到兵器、防具、坐騎、寶物或素材
    "tab:news",  # 見聞：你做的事第一次上了行狀、記了功、打過一場決戰或揭過懸賞
    "self:annals",  # 行狀：第一筆寫進行狀
    "self:mingtie",  # 名帖匣：第一次收到或交換名帖
    "self:mail",  # 信匣：同名帖匣（帖友＝兩邊都收著對方的名帖；信匣自己還看 main.mail）
    "hero:codex",  # 江湖錄：第一次記下一幕、一個人、一件東西
    "hero:mates",  # 同伴：收養了那個孩子、或第一次有人跟你走
)


def new_book() -> UnfoldBook:
    return UnfoldBook()


def _level(state: GameState) -> int:
    return state.player.member.level


def reached(state: GameState, key: str, *, opening_pending: bool) -> bool:
    """這一塊此刻用不用得到（只看身上的東西；長出來之後不再問）。"""
    p = state.player
    if key == "tab:map":
        return not opening_pending
    if key == "hero:attrs":
        return p.stat_points > 0 or _level(state) >= 2
    if key == "hero:gear":
        return any((p.weapon, p.armor, p.mount, p.treasure, p.heirloom, p.rack, p.held_gear, p.materials))
    if key == "tab:news":
        return bool(p.annals) or p.contrib > 0 or p.showdowns > 0 or p.bounties_done > 0
    if key == "self:annals":
        return bool(p.annals)
    if key in ("self:mingtie", "self:mail"):
        return bool(p.mingtie_box)
    if key == "hero:codex":
        c = p.codex
        return c is not None and bool(c.scenes or c.ended or c.people or c.things or c.gods)
    if key == "hero:mates":
        return p.guard is not None or bool(p.followers) or bool(p.team)
    return True


def grow(state: GameState, *, opening_pending: bool) -> list[str]:
    """看一次：用得到而還沒長出來的寫進 grown 與 fresh。回這一次長出來的鍵。沒有這一本的角色不動。"""
    book = state.player.unfold
    if book is None:
        return []
    new = [k for k in KEYS if k not in book.grown and reached(state, k, opening_pending=opening_pending)]
    book.grown.extend(new)
    book.fresh.extend(k for k in new if k not in book.fresh)
    return new


def hidden(book: UnfoldBook | None) -> list[str]:
    """網頁要藏的鍵（沒有這一本是空的：全部照舊）。"""
    return [] if book is None else [k for k in KEYS if k not in book.grown]


def seen(book: UnfoldBook | None, keys: list[str]) -> None:
    """點開過了：那幾塊的紅點滅。"""
    if book is not None:
        book.fresh = [k for k in book.fresh if k not in set(keys)]
