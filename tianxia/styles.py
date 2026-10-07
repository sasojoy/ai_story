"""一門打不遍（企劃者 2026-10-07 選甲）：大場面的對手各有路數。

大場面的對手（頭目、大勢人物本人、難度到 big_fight_difficulty，同 Game.is_big）最怕哪一路（soft）、最會對付哪一路（hard），
照「天機｜style｜隊伍 id」的 sha256 從 Config.styles.attributes 裡挑：同一季同一個對手固定，換季（天機 +1）就換，抄不了去年的答案。
上陣的人身上武學的屬性落在 soft，這個人的威力乘 1＋soft_bonus；落在 hard 乘 1－hard_penalty。玩家因此要養幾門不同屬性的武學、
上陣前改練（team.switch_art 不用重練）。

只在第一季開著時有（rules.season_one）；開關關著時 style_of 一律是 None，beta 一個字都不變。
提示一律含蓄：戰報裡打贏、用的又剛好是軟處時一句，打輸、用的是他拿手對付的那一路時一句（lines）；勝算本來就照實算；
大場面判讀與人物對話拿 words 的打法描述給模型（fight_line、talk_line），不寫屬性名、不寫倍數給玩家。
這個模組只讀內容與全服的天機，不改狀態。
"""
from __future__ import annotations

import hashlib
from typing import NamedTuple

from . import rules
from .encounter import Boost
from .models import Content, Squad
from .state import GameState
from .world_state import WorldStateStore

LOSING_TIERS = ("僵持", "落敗")


class Style(NamedTuple):
    soft: str  # 最怕的那一路（屬性）
    hard: str  # 最會對付的那一路


def is_big(content: Content, squad: Squad) -> bool:
    """大場面：對手標了頭目、是大勢人物本人（figures 的 squad），或難度到 big_fight_difficulty（武學與成長設計 8.3）。"""
    own = {fig.squad for fig in content.figures.values()}
    return squad.boss or squad.id in own or squad.difficulty >= content.config.big_fight_difficulty


def pick(tianji: int, squad_id: str, attributes: list[str]) -> Style:
    """照天機與隊伍 id 挑兩路不同的屬性。用 hashlib，不用 Python 內建的 hash（那個每次執行都不同）。"""
    pool = list(dict.fromkeys(attributes))
    n = int.from_bytes(hashlib.sha256(f"{tianji}|style|{squad_id}".encode()).digest()[:8], "big")
    soft = pool[n % len(pool)]
    rest = [a for a in pool if a != soft]
    return Style(soft, rest[(n // len(pool)) % len(rest)])


def style_of(state: GameState, content: Content, world: WorldStateStore, squad: Squad) -> Style | None:
    """這一路對手的路數；不是大場面、或第一季沒開著是 None。"""
    if not rules.season_one(content, state.world) or not is_big(content, squad):
        return None
    return pick(world.read().tianji, squad.id, content.config.styles.attributes)


def factor(content: Content, style: Style | None, attribute: str | None) -> float:
    """身上武學屬 attribute 的人打這一路對手，威力乘多少。"""
    if style is None or not attribute:
        return 1.0
    rule = content.config.styles
    if attribute == style.soft:
        return 1 + rule.soft_bonus
    if attribute == style.hard:
        return 1 - rule.hard_penalty
    return 1.0


def styled(boosts: list[Boost], attributes: list[str | None], content: Content, style: Style | None) -> list[Boost]:
    """每個人的加成再乘上他那一門武學對這一路對手的倍數（乘在 Boost.factor：整個人的乘數）。"""
    if style is None:
        return boosts
    return [
        b.model_copy(update={"factor": b.factor * factor(content, style, a)}) if factor(content, style, a) != 1.0 else b
        for b, a in zip(boosts, attributes, strict=True)
    ]


def note(content: Content, style: Style | None, attribute: str | None, tier: str) -> list[str]:
    """戰報裡含蓄的一句：打贏、用的是他怕的那一路；或沒打贏、用的是他拿手對付的那一路。其他時候不說。"""
    if style is None or not attribute:
        return []
    lines = content.config.styles.lines
    if attribute == style.soft and tier not in LOSING_TIERS:
        return [lines["soft"]]
    if attribute == style.hard and tier in LOSING_TIERS:
        return [lines["hard"]]
    return []


def fight_line(content: Content, style: Style | None) -> str:
    """大場面判讀給模型看的對手路數（接在對手那一行後面）。"""
    if style is None:
        return ""
    words = content.config.styles.words
    return (
        f"；此人的路數：最吃不消屬{style.soft}（{words[style.soft]}）的打法，"
        f"最會對付屬{style.hard}（{words[style.hard]}）的打法"
    )


def talk_line(content: Content, style: Style | None, name: str) -> str:
    """人物對話的系統提示多一段：他自己的武藝習慣，只能不經意流露。"""
    if style is None:
        return ""
    words = content.config.styles.words
    return (
        f"【{name}的武藝習慣（不要直說，更不要說出屬性的名稱；只有話題碰到武藝、交手、戰事時才不經意流露一兩句，"
        f"例如抱怨、自誇或回憶吃過的虧）】生平最吃不消「{words[style.soft]}」那一路的打法；"
        f"最拿手對付「{words[style.hard]}」那一路的打法。\n"
    )
