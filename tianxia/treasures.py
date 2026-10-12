"""寶物與好馬的來源（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；裝備三）。

- 寶物：一件一種效果、不分階品、不磨損、不能拆，身上只配一件（PlayerState.treasure）；隨時能換（2.3【定】，企劃者 2026-10-11：
  不設限制，走修練頁的「換上」equipment.wield）。效果的數字在 Config.treasures.effects，內容（content/gear.json）只寫名字與效果種類。
  所有掛點都經過 amount（沒穿、開關關著、效果對不上都回中性值），畫面寫的機率與實際擲的是同一個數。
- 好馬：良駒（懸賞的重賞、奇遇；毛色與品質照那一筆的種子）與名駒（名將贈禮；專名照 template 從內容讀）；馬本身的規則在 mounts，
  新的一匹一律從 mounts.new_mount 開。
- 四種來源：懸賞的重賞（bounty_prize；掛單時擲在 bounties.issue）、名將贈禮（gifts_due，Game.choose／answer_event 最後叫）、
  奇遇（grant_effect，rules.apply_effect 的 Effect.gear）、挑戰本人掉落（challenge_drop，Game._challenge）。
- 不重複（6.5）：掉落池只抽你還沒有的（身上、裝備庫、寄放的都算，照 template 認）；都有了給 dup_silver 兩。
- 寄放（6.5）：懸賞的重賞與名將贈禮在裝備庫滿了時放進 PlayerState.held_gear，同步與快轉時 deliver_held 補發（閉關中也補）。

擲骰一律用自己的 random.Random(種子)，不碰 Game.rng（FB-129：整季測試與量表的基準不位移）。
只 import models、state、equipment、mounts；不 import team、rules、cultivation、bounties、materials（它們反過來呼叫這裡）。
玉璽碎片（玉璽碎片設計 7.2～7.4）之後在寶物欄多一格「傳承」（PlayerState.heirloom，不進裝備庫、不換）：_cells 多加那一格（只看
Config.seal.enabled、不看寶物的開關，查 Config.seal.effects）、MULTIPLY 加碎片的乘法鍵，八個掛點都不用動；不重複照 template，
不假設「換季全清」。rows、card_line 現在照寶物的開關回空，玉璽一要改成照兩格各自的開關（玉璽碎片設計第十節）。
"""
from __future__ import annotations

import math
import random

from . import equipment, mounts
from .models import Content, SteedDef
from .state import Equipment, GameState, PlayerState

MULTIPLY = frozenset({"cultivate", "insight", "legend"})  # 乘的效果（中性值 1）；其餘是加的（中性值 0）。玉璽一把碎片的乘法鍵加進來
EFFECT_TEXT = {  # 待 joy 潤：角色卡、修練頁、拿到時那一句（數字照 Config.treasures.effects；{item} 是破境丹的名字 Config.legend_item_name）
    "cultivate": "修練升品的機會 ×{x}",
    "insight": "探索悟得意境的機會 ×{x}",
    "win_xinde_pct": "打贏的心得 +{pct}",
    "win_exp_pct": "打贏的經驗 +{pct}",
    "seclusion": "閉關的心得 +{pct}",
    "audience": "求見門檻 −{n}",
    "win_material": "打贏時有 {pct} 的機會多掉一個素材",
    "legend": "探索撿到{item}的機會 ×{x}",
}


def on(content: Content) -> bool:
    return equipment.on(content, "treasure")


def effect_of(content: Content, item: Equipment | None) -> str | None:
    """這一件寶物的效果鍵（照 template 查寶物表）；不是寶物那一欄、沒有 template、內容拿掉了是 None（效果不算）。"""
    if item is None or item.slot != "treasure" or item.template is None:
        return None
    tdef = content.gear.treasures.get(item.template)
    return tdef.effect if tdef is not None else None


def effect_text(content: Content, key: str) -> str:
    """「求見門檻 −3」「打贏的心得 +20%」（待 joy 潤）：數字照 Config.treasures.effects；百分比 .5 進位（不用 round／:.0%，同 mounts.pct）。"""
    value = content.config.treasures.effects.get(key, 0.0)
    return EFFECT_TEXT.get(key, "").format(
        x=f"{value:g}", pct=f"{math.floor(value * 100 + 0.5)}%", n=f"{value:g}", item=content.config.legend_item_name,
    )


def _cells(state: GameState, content: Content) -> list[tuple[str, float]]:
    """身上每一格寶物的（效果鍵, 數字）。這一批只有一般那一格（PlayerState.treasure：看 Config.treasures.enabled、查
    Config.treasures.effects）；玉璽一在這裡多加傳承那一格（PlayerState.heirloom：只看 Config.seal.enabled、不看寶物的開關，
    查 Config.seal.effects），其他掛點都不用動（玉璽碎片設計 7.2）。所以寫成一格一格往清單裡加，不在一般那一格空著時提早回傳。"""
    cells: list[tuple[str, float]] = []
    key = effect_of(content, state.player.treasure) if on(content) else None
    if key is not None:
        cells.append((key, content.config.treasures.effects.get(key, 1.0 if key in MULTIPLY else 0.0)))
    return cells


def amount(state: GameState, content: Content, effect: str) -> float:
    """這個效果此刻的數字（設計 6.1：所有掛點都經過這裡）：乘的效果是倍數（沒有是 1）、加的是加多少（沒有是 0）；
    好幾格都是同一個鍵時乘的相乘、加的相加（玉璽碎片設計 7.2）。沒帶、開關關著、效果對不上都回中性值。"""
    multiply = effect in MULTIPLY
    total = 1.0 if multiply else 0.0
    for key, value in _cells(state, content):
        if key == effect:
            total = total * value if multiply else total + value
    return total


def extra_drop(state: GameState, content: Content, dropped: list[str], season: int, record_id: int) -> str | None:
    """寶物「打贏多掉一個素材」（設計 6.2）：這一場掉了素材時，win_material 的機率從這一場**實際掉到的**素材裡挑一種、多給一個
    （計畫「要 PM 定的」第 3 條甲）；回那一種的 id，沒中、沒帶、開關關著、這一場沒掉素材都是 None（不擲）。只在遊歷、探索野怪、
    序章外由 Game._battle_rewards 叫（挑戰本人、劇情戰不吃）。發素材是 engine 的事（treasures 不 import materials）。
    自己一份亂數（寶|素材|季數|名號|戰報流水號；流水號每季從 1 算起，所以要有季數；開頭的「素材」跟挑戰本人掉寶物那一份分開），
    不碰 Game.rng（FB-129）。"""
    chance = amount(state, content, "win_material")
    if chance <= 0 or not dropped:
        return None
    rng = random.Random(f"寶|素材|{season}|{state.player.name}|{record_id}")
    if rng.random() >= chance:
        return None
    return rng.choice(list(dict.fromkeys(dropped)))  # 照掉落的順序去重：同一種掉兩筆不加重


def owned_templates(p: PlayerState) -> set[str]:
    """手上已經有的（6.5：身上的寶物與坐騎、裝備庫、寄放的都算，照 template 認）。"""
    items = [p.treasure, p.mount, *p.rack, *p.held_gear]
    return {item.template for item in items if item is not None and item.template}


def refresh_names(p: PlayerState, content: Content) -> None:
    """讀檔時照內容重寫名字（設計 3.1：名字照 template 從內容讀，joy 改名不動存檔）：身上的寶物與坐騎、裝備庫、寄放的每一件有
    template 的，name 改成 content/gear.json 的名字；內容拿掉了就留著舊名字當備份。Game._drop_stale_references 每次建 Game 都叫，
    所以 item.name 永遠是內容的名字——equipment.store／wield 的三句、mounts.name_of、馬市的鈕都不用改。"""
    book = content.gear
    for item in (p.treasure, p.mount, *p.rack, *p.held_gear):
        if item is None or not item.template:
            continue
        found = book.treasures.get(item.template) if item.slot == "treasure" else book.steeds.get(item.template)
        if found is not None:
            item.name = found.name


def new_treasure(state: GameState, content: Content, tid: str) -> Equipment:
    """新的一件寶物（四欄共用的流水號 +1，id「寶:N」）：名字照寶物表，不分階品。"""
    return Equipment(id=equipment.next_id(state, "treasure"), slot="treasure", name=content.gear.treasures[tid].name, template=tid)


def new_steed(state: GameState, steed: SteedDef) -> Equipment:
    """新的一匹名駒（5.7：三階、專名，品質照內容）：走裝備二的 mounts.new_mount（「裝備三的良駒、名駒也從這裡開」，之後它多了
    預設欄位〔例如飽足〕兩邊才不會走樣），再補上 template（名駒的 id）。"""
    item = mounts.new_mount(state, name=steed.name, tier=3, quality=steed.quality)
    item.template = steed.id
    return item
