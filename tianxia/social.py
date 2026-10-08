"""玩家之間的互動（企劃者 2026-10-08「假設 A 玩家在長社，B 玩家也過去的話，兩人可以做什麼互動」）。

第一層：看得到彼此。場景底下列「此地還有誰」（`here`），點名字打開一張玩家卡（`card`）：名號、門派・陣營・頭銜、等級、
身上兩門武學（只寫名字與品質），以及卡上的動作鈕。

卡上的動作是一張登記表（`ACTIONS`）：每一種互動寫一個 `CardAction`，用 `register` 登記，就會出現在每一張卡上——
`buttons` 決定這張卡上畫哪幾顆鈕（可以一顆都不畫），`run` 是按下去之後做的事。贈物、結伴同行、打招呼、切磋、論武都掛在這裡。
引擎的門面是 `Game.peers_here`、`Game.peer_card`、`Game.peer_act`（拒絕的話與對方不在這裡都在那裡擋）。

伺服器假人跟真人一模一樣（伺服器假人設計第五節）：名單、卡、按鈕、拒絕的話一律不看 `PlayerState.bot`。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import prologue as prologue_rules
from . import ranks, team
from .characters import CharacterStore
from .state import GameState

if TYPE_CHECKING:
    from .engine import Game
    from .models import Content

GONE = "他已經不在這裡了。"  # 對方離開了、下線太久、或根本沒有這個人：一律這一句（不讓人試出名號在不在）


@dataclass
class CardButton:
    """玩家卡上的一顆鈕。id 是送回 /api/peer/act 的 action（同一種互動可以有好幾顆，例如每一種禮節一顆，用 arg 分開）。"""

    action: str  # CardAction.id
    label: str
    arg: str = ""  # 同一種互動的哪一個（禮節、送哪一樣）；run 收到的 params["arg"]
    note: str = ""  # 鈕上的小字（花多少、為什麼按不下去）
    enabled: bool = True
    confirm: str = ""  # 按下去之前先問一次的話；空的直接送
    amount: int = 0  # >0：按下去要先填一個數量（1～amount），送 params["amount"]

    def view(self) -> dict:
        return {
            "action": self.action, "label": self.label, "arg": self.arg, "note": self.note,
            "enabled": self.enabled, "confirm": self.confirm, "amount": self.amount,
        }


@dataclass
class CardAction:
    """卡上的一種互動。buttons(game, other) 畫鈕；run(game, other, params) 做事、回給按的人看的訊息。
    other 是對方那一份 Game（不叫模型、沒有補算時間：替別人寫東西不能讓他看起來剛剛上過線）；run 改了 other.state，
    Game.peer_act 會存回去。數值一律由這裡的規則定，params 只是玩家挑的東西，要自己驗。"""

    id: str
    buttons: Callable[[Game, Game], list[CardButton]]
    run: Callable[[Game, Game, dict], list[str]]
    order: int = 100  # 卡上由上而下的順序（小的在前）


ACTIONS: dict[str, CardAction] = {}


def register(action: CardAction) -> CardAction:
    ACTIONS[action.id] = action
    return action


def visible(state: GameState, content: Content) -> bool:
    """這個人看得到別人、也被別人看得到：不在路上（人在兩地之間）、不在草廬序章裡（序章是一個人的）。"""
    return state.player.journey is None and not prologue_rules.active(state, content)


def here(game: Game) -> list[GameState]:
    """此地還有誰：跟你同一個地點、presence_seconds 之內同步過、不在路上也不在序章裡的人，照名號排序；你自己看不到人時是空的。"""
    s, c = game.state, game.content
    if not visible(s, c) or not hasattr(game.world, "db"):
        return []
    since = game.now - c.config.presence_seconds
    return [o for o in CharacterStore(game.world.db).present(s.player.location, since, s.player.name) if visible(o, c)]


def side(state: GameState, content: Content) -> str:
    """名單上名字後面括號裡那一個：陣營，沒有陣營是「散人」。"""
    return content.scenario.faction_name(state.player.faction) or "散人"


def affiliation(state: GameState, content: Content) -> str:
    """門派・陣營・頭銜（有哪幾樣寫哪幾樣），都沒有是散人——跟狀態列同一個寫法（Game.status_data）。"""
    p = state.player
    sect = content.sects[p.sect].name if p.sect else None
    faction = content.scenario.faction_name(p.faction)
    return "・".join(name for name in (sect, faction, ranks.title(content, state)) if name) or "散人"


def arts(other: Game) -> list[dict]:
    """身上兩門（內功、武學）：名字（改過名的照改過的寫）與他自己那一份的品質。沒有的那一欄不寫。"""
    s, c = other.state, other.content
    rows = []
    for kind, skill_id in (("內功", s.player.member.neigong_id), ("武學", s.player.member.wugong_id)):
        art = team.resolve_art(skill_id, c, other.world)
        if art is not None:
            rows.append({"kind": kind, "name": art.name, "quality": team.art_quality(s, art)})
    return rows


def card(game: Game, other: Game) -> dict:
    """玩家卡（第一層）：給網頁畫的資料。動作鈕照登記表的順序，每一種互動自己決定畫不畫。"""
    o = other.state
    buttons = [
        b.view()
        for action in sorted(ACTIONS.values(), key=lambda a: (a.order, a.id))
        for b in action.buttons(game, other)
    ]
    return {
        "name": o.player.name,
        "affiliation": affiliation(o, other.content),
        "level": o.player.member.level,
        "arts": arts(other),
        "actions": buttons,
    }

