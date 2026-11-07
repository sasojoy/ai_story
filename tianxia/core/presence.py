"""「此地還有」的判斷與狀態列的身分字（查詢服務；全部拆包第 37 批「玩家互動一」先拆出來：計畫 docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md 1.8）。

原本寫在 tianxia/social.py：此地還有誰（here：窗口 `Config.presence_seconds` 之內同步過、不在路上也不在序章裡）、看得到彼此（visible）、
名單上名字後面括號裡的陣營（side）、狀態列與玩家卡的「門派・陣營・頭銜」（affiliation）、對方不在這裡的那一句（GONE）。
酒肆包（查人、客人名單）、探索包（走一趟結算卡）、截殺、通緝、狀態列都讀它；玩家互動包（tianxia/features/peers/）的 social 從這裡 re-export 同一批函式物件。
函式照抄、名字不變。同 arena_ranks、event_check：核心本體的一部分（不進 MODULES、不進 FEATURES）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import allied, ranger, ranks
from .. import prologue as prologue_rules
from ..characters import CharacterStore
from ..state import GameState
from . import arena_ranks

if TYPE_CHECKING:
    from ..engine import Game
    from ..models import Content

GONE = "對方已經不在這裡了。"  # 對方離開了、下線太久、或根本沒有這個人：一律這一句（不讓人試出名號在不在）


def window(content: Content) -> float:
    """「此地還有」的窗口（秒）：Config.presence_seconds。酒肆查人的「此刻」不能比它寬（tests 守）。"""
    return content.config.presence_seconds


def visible(state: GameState, content: Content) -> bool:
    """這個人看得到別人、也被別人看得到：不在路上（人在兩地之間）、不在草廬序章裡（序章是一個人的）。"""
    return state.player.journey is None and not prologue_rules.active(state, content)


def here(game: Game) -> list[GameState]:
    """此地還有誰：跟你同一個地點、presence_seconds 之內同步過、不在路上也不在序章裡的人，照名號排序；你自己看不到人時是空的。
    存檔不含賽季（characters.py），讀回來的每一份接上你這一份的季（同 Game._peer）：看季的讀法（豪強分屬兩軍的 allied.on）才讀得到
    這一季的章——沒接的話依附黃巾軍的豪強在名單上寫回「地方豪強」（FB-275 複驗）。"""
    s, c = game.state, game.content
    if not visible(s, c) or not hasattr(game.world, "db"):
        return []
    since = game.now - window(c)
    found = CharacterStore(game.world.db).present(s.player.location, since, s.player.name)
    for o in found:
        o.world = s.world
    return [o for o in found if visible(o, c)]


def side(state: GameState, content: Content) -> str:
    """名單上名字後面括號裡那一個：陣營，沒有陣營是「散人」；豪強分屬兩軍的季寫依附哪一邊（allied.side_text，FB-275）。"""
    return allied.side_text(state, content) or "散人"


def affiliation(state: GameState, content: Content) -> str:
    """門派・陣營・頭銜・擂台稱號・上一季論功的稱號（有哪幾樣寫哪幾樣），都沒有是散人；散人有遊俠名號時寫「散人・江湖遊俠」（有門派時門派代替「散人」）。
    狀態列（Game.status_data）與玩家卡都用這一個。"""
    p = state.player
    sect = content.sects[p.sect].name if p.sect else None
    faction = allied.label_of(state, content) or None  # 豪強分屬兩軍的季寫「地方豪強（依附官軍）」
    named = ranger.title(content, state)
    ring = arena_ranks.title_of(state.world, p.name) if arena_ranks.on(content) else None  # 擂台的稱號照此刻的名次，掉出就沒了（PM 2026-10-14）
    if faction is None and named is not None:
        base = f"{sect or '散人'}・{named}"
    else:
        base = "・".join(name for name in (sect, faction, ranks.title(content, state)) if name) or "散人"
    base = f"{base}・{ring}" if ring else base
    # 上一季論功的稱號（減法季設計 3.3；PlayerState.season_title，換季時掛上）：沒有是空字串，一個字都不多
    return f"{base}・{p.season_title}" if p.season_title else base
