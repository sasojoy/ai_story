"""遊歷的回合演出（武學與成長設計 8.2）：勝負照 encounter.resolve_encounter 一次算好，這裡照結果拆成 3～5 回合。
只管數字與誰出手；句子在 battlelog（照屬性挑 content/combat_lines.json）。回合加起來剛好等於結果，中途不翻盤。

亂數由呼叫端給：引擎用「名號｜戰報流水號」當種子的自己一份（計畫三 G3），不碰 Game.rng——演出是畫面上的事，
不能讓接下來的擲骰跟著位移，而且同一筆戰報每次演出來都一樣。
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel

ROUNDS = {"大勝": (3, 3), "險勝": (4, 4), "僵持": (5, 5), "落敗": (3, 4)}  # 每種結果演幾回合（最少, 最多）【預設】
END_MORALE = {"大勝": 0, "險勝": 0, "僵持": 50, "落敗": 80}  # 打完對手還剩幾成氣勢
FOE_AGILITY_BASE, FOE_AGILITY_PER = 5.0, 1 / 20  # 對手的身法照難度換算：5＋難度÷20【預設】


class Fighter(BaseModel):
    name: str
    art: str | None  # 出手的武學名；沒學武學是 None
    attribute: str | None


class Foe(BaseModel):
    name: str
    attribute: str | None
    agility: float


class Beat(BaseModel):
    """一回合裡的一下出手。ours：對手的氣勢掉幾成；theirs：我方（玩家本人）的氣血掉多少。
    theirs 的 amount 是 None：這一場本來就不扣氣血（劇情戰，計畫三 G5），只寫怎麼出手、不寫打中沒有。"""

    side: Literal["ours", "theirs"]
    actor: str
    art: str | None
    attribute: str | None
    amount: int | None


class Round(BaseModel):
    number: int
    beats: list[Beat]


def foe_agility(difficulty: float) -> float:
    return FOE_AGILITY_BASE + difficulty * FOE_AGILITY_PER


def split(total: int, parts: int, rng: random.Random) -> list[int]:
    """把 total 拆成 parts 份：每份不少於 0、加起來剛好等於 total（最後一份補零頭）。"""
    if parts <= 0:
        return []
    weights = [rng.random() + 0.5 for _ in range(parts)]
    whole = sum(weights)
    shares = [int(total * w / whole) for w in weights]
    shares[-1] += total - sum(shares)
    return shares


def play(
    tier: str, fighters: list[Fighter], foe: Foe, our_agility: float, hp_lost: int | None, rng: random.Random,
) -> list[Round]:
    """照結果演出回合：對手的氣勢從 100 掉到 END_MORALE[tier]、玩家掉的氣血剛好是 hp_lost（None：這一場不扣氣血，
    對手的出手不帶數字）。身法比對手高（或一樣）就我方先出手；有武學的人輪流出手（本人在前），都沒有就本人空手上。"""
    low, high = ROUNDS[tier]
    count = rng.randint(low, high)
    morale = split(100 - END_MORALE[tier], count, rng)
    hurt = [None] * count if hp_lost is None else split(max(0, hp_lost), count, rng)
    acting = [f for f in fighters if f.art] or fighters[:1]
    we_first = our_agility >= foe.agility
    played = []
    for i in range(count):
        actor = acting[i % len(acting)]
        ours = Beat(side="ours", actor=actor.name, art=actor.art, attribute=actor.attribute, amount=morale[i])
        theirs = Beat(side="theirs", actor=foe.name, art=None, attribute=foe.attribute, amount=hurt[i])
        played.append(Round(number=i + 1, beats=[ours, theirs] if we_first else [theirs, ours]))
    return played
