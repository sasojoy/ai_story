"""玩家卡的動作登記表（全部拆包第 45 批，第 37 批 PM 認定第 3 條）：`CardButton`、`CardAction`、`ACTIONS`、`register` 原本寫在玩家互動包的 social.py。
卡上的每一種互動（贈物、結伴同行、打招呼、切磋、論武、截殺、遞名帖、通緝）都寫一個 CardAction、register 登記，就會出現在每一張卡上：玩家互動包的五個卡模組
與懸賞榜包的通緝（features/bounties/wanted.py）各登記各的，都讀這一張，包不必為了登記一顆鈕 import 別的包。social 從這裡 re-export 同一批物件（`social.ACTIONS is cards.ACTIONS`），
玩家互動包、server.py 照舊經 social. 讀。同 presence：核心本體的一部分（不進 MODULES、不進 FEATURES）。
卡上由上而下照 (order, id) 排，跟登記的先後無關（通緝 65 的位置不變）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tianxia.engine import Game


@dataclass
class CardButton:
    """玩家卡上的一顆鈕。id 是送回 /api/peer/act 的 action（同一種互動可以有好幾顆，例如每一種禮節一顆，用 arg 分開）。"""

    action: str  # CardAction.id
    label: str
    arg: str = ""  # 同一種互動的哪一個（禮節、送哪一樣）；run 收到的 params["arg"]
    note: str = ""  # 鈕上的小字（花多少、為什麼按不下去）
    enabled: bool = True
    confirm: str = ""  # 按下去之前先問一次的話；空的直接送
    amount: int = 0  # >0：按下去要先填一個數量（amount_min～amount），送 params["amount"]
    amount_min: int = 1  # 數量的下限（輸入框的 min 與提示字）：贈物是 1，通緝是 post_min（FB-121 第 6 件）
    choices: list[dict] = field(default_factory=list)  # 有的話先挑一樣（[{id, label, max}]），送 params["choice"]；數量上限照那一樣的 max
    # 同一種互動裡「每一樣東西一顆」的鈕（論武出哪一樣）：同一個 group 的鈕網頁收成一個下拉清單（每一項寫 pick）配一顆寫 group 的鈕，
    # 卡片不會隨東西變多一直變長。空的照常一顆一顆畫
    group: str = ""
    pick: str = ""
    # >0：按下去先攤開一格輸入框（可以留空），最多這麼多字，送 params["text"]（挑釁附一句話）；伺服器在行動鎖外先審過（speech）
    text: int = 0

    def view(self) -> dict:
        return {
            "action": self.action, "label": self.label, "arg": self.arg, "note": self.note,
            "enabled": self.enabled, "confirm": self.confirm, "amount": self.amount, "amount_min": self.amount_min,
            "choices": self.choices,
            "group": self.group, "pick": self.pick, "text": self.text,
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
    # 按下去之前要不要先請模型（論武的首創取名）：回 naming.NamingRequest 就由伺服器在行動鎖外取名（三段式的 A 段，只讀），
    # 取好的（名字, 說明）放進 params["proposed"] 再交給 run；不給或回 None 照常直接 run
    request: Callable[[Game, Game, dict], object] | None = None
    # 帶玩家打的一句話（params["text"]）的互動：(那一句, speech 的種類) 交給伺服器在行動鎖外請模型審，結果放進 params["verdict"]；
    # 不給或回 None 不審（C 段的字表照樣由 run 自己查）
    screen: Callable[[Game, Game, dict], tuple[str, str] | None] | None = None


ACTIONS: dict[str, CardAction] = {}


def register(action: CardAction) -> CardAction:
    ACTIONS[action.id] = action
    return action
