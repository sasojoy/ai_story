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
    "tab:craft",  # 武學頁的「煉製」：身上第一次有兩個合得起來的意境（要問共用層 fusion，由包算好放進 ready）
    "self:create",  # 武學頁的「自創」：心得第一次夠自創一門
    # 江湖頁上的（江湖頁重排第六批的表，PM 2026-11-25 同意；畫在 main.js 那一頁，那一條自己照 shown() 藏）
    "jh:peers",  # 這裡的人裡的俠客：交過名帖、有同門，或到 5 級
    "jh:sortie",  # 出陣牌：投靠一方
    "jh:duty",  # 軍務牌：投靠一方
    "jh:sign:bounties",  # 懸賞榜：第一件託付辦完
    "jh:sign:smith",  # 鐵匠鋪：跟俠客頁的裝備同一刻
    "jh:sign:arena",  # 擂台：到 10 級，或第一次切磋
    "jh:sign:dadian",  # 打點：銀兩第一次到 Config.unfold.sign_silver_dadian
    "jh:sign:market",  # 馬市：銀兩第一次到 Config.unfold.sign_silver_market
)
READY_KEYS = frozenset({"tab:craft"})  # 要問世界才知道的（包算好傳進 ready）


# 提案表：跟小事卡、紅點重疊的那幾句說明（合成、配點、自創）新角色不再說：開本那一刻記成說過
REPLACED_HINTS = ("h_merge", "h_points", "h_create")


def new_book() -> UnfoldBook:
    return UnfoldBook()


def _level(state: GameState) -> int:
    return state.player.member.level


def reached(state: GameState, key: str, *, opening_pending: bool, ready: frozenset[str] = frozenset(), create_price: int = 0,
            sign_silver: tuple[int, int] = (0, 0)) -> bool:
    """這一塊此刻用不用得到（只看身上的東西；長出來之後不再問）。ready：包算好的（READY_KEYS）；create_price：自創第一門要的心得；
    sign_silver：打點、馬市兩塊招牌各要的銀兩。"""
    p = state.player
    if key == "jh:peers":
        return bool(p.mingtie_box) or p.sect is not None or _level(state) >= 5
    if key in ("jh:sortie", "jh:duty"):
        return p.faction is not None
    if key == "jh:sign:bounties":
        return any(e.status == "done" for e in p.errands)
    if key == "jh:sign:smith":
        key = "hero:gear"
    if key == "jh:sign:arena":
        return _level(state) >= 10 or any(b.kind == "spar" for b in state.battles)
    if key in ("jh:sign:dadian", "jh:sign:market"):
        return not opening_pending and p.stats.get("silver", 0) >= sign_silver[key == "jh:sign:market"]  # 開局的盤纏就夠打點：城門口先不畫
    if key in READY_KEYS:
        return key in ready
    if key == "self:create":
        return create_price > 0 and p.stats.get("xinde", 0) >= create_price
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


def grow(state: GameState, *, opening_pending: bool, ready: frozenset[str] = frozenset(), create_price: int = 0,
         sign_silver: tuple[int, int] = (0, 0)) -> list[str]:
    """看一次：用得到而還沒長出來的寫進 grown 與 fresh。回這一次長出來的鍵。沒有這一本的角色不動。"""
    book = state.player.unfold
    if book is None or book.old:
        return []
    new = [k for k in KEYS if k not in book.grown and reached(state, k, opening_pending=opening_pending, ready=ready, create_price=create_price,
                                                      sign_silver=sign_silver)]
    book.grown.extend(new)
    book.fresh.extend(k for k in new if k not in book.fresh)
    return new


def hidden(book: UnfoldBook | None) -> list[str]:
    """網頁要藏的鍵（沒有這一本是空的：全部照舊）。"""
    return [] if book is None or book.old else [k for k in KEYS if k not in book.grown]  # 舊角色那一本（old）也是全部照舊


def seen(book: UnfoldBook | None, keys: list[str]) -> None:
    """點開過了：那幾塊的紅點滅。"""
    if book is not None:
        book.fresh = [k for k in book.fresh if k not in set(keys)]
