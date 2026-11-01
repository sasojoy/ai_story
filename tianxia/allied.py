"""第一季豪強分屬兩軍（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md；企劃者 2026-10-15 定稿）。

蓋了第一季章、而且豪強分屬兩軍的章是開著的季（on），劇本裡有 allies 的陣營（地方豪強）要依附其中一軍，算那一軍的人：
敵我一律讀 side_of；頭銜、門派、部下、晉升、行動表、機緣照舊讀 PlayerState.faction。名冊（faction_rolls）的鍵寫 roll_key
（「haoqiang@guan」），資料庫結構不動。開關關著時 side_of 就是 faction、roll_key 就是陣營 id，一個字都不變。
只 import models、state、calendar。"""
from __future__ import annotations

import hashlib

from . import calendar
from .models import Content, FactionDef
from .state import GameState, WorldState

SEP = "@"
ALLY_PREFIX = "faction:ally:"  # 選邊鈕（Game._ally_options）
CAP_RANK = 3  # 企劃者 2026-10-15：「純官軍或者純黃巾才有辦法升到最高軍階，豪強版的只能升到三階」
# 新寫的字（joy 10/15：這種句子由 AI 產生）
ALLY_LABEL = "{faction}（依附{ally}）"  # 狀態列、玩家卡、確認畫面
ALLY_SHORT = "{faction}・依附{ally}"  # 「此地還有」名字後面的括號裡（FB-275：括號裡不再套括號）
ALLY_COUNT = "（其中{short} {n} 人）"  # 名冊那一句（企劃者第 3 題甲）
ALLY_PICK = "地方豪強這一季要依附官軍或黃巾其中一邊，算那一邊的人：決戰、地盤、出陣、軍令、貢獻都照那一邊。{counts}。挑一邊。"
ALLY_AFTER_SECT = "拜入之後，先挑依附哪一邊，才算入了夥：決戰、地盤、出陣、軍令、貢獻都照那一邊。{counts}。"
ALLY_BUTTON = "依附{ally}（目前 {n} 人）"
ALLY_DONE = "你依附了{ally}。"
ALLY_FIRST = "先挑依附哪一邊，才能安排前往"
# 選邊那一刻人已經在決戰的參戰名單上（先臨時投效了另一邊，FB-273）：集結時跟著換過去，開打了照決戰的規則不能改投、這一場照舊
ALLY_REJOINED = "{battle}的集結名單上，你也跟著換到{ally}那一邊。"
ALLY_STAYS = "{battle}已經開打，這一場你照舊站在{old}那一邊；打完這一場才算{ally}的人。"


def on(content: Content, world: WorldState) -> bool:
    """這一季豪強分屬兩軍：蓋了第一季的章（calendar.season_one_on，同 rules.season_one）。2026-10-31 起沒有自己的開關與章
    （Config.haoqiang_allied、WorldState.haoqiang_allied 拿掉；舊存檔裡的鍵讀進來時丟掉）。"""
    return calendar.season_one_on(world, content)


def allies_of(content: Content, faction_id: str | None) -> list[FactionDef]:
    """這個陣營可以依附的幾軍（照劇本的順序）；不是要依附的陣營是空的。"""
    found = content.scenario.find_faction(faction_id)
    return [f for f in content.scenario.factions if found is not None and f.id in found.allies]


def side_of(state: GameState, content: Content) -> str | None:
    """敵我的一個讀法：依附的季、依附了一軍的人是那一軍；其他人是自己的陣營（散人 None）。"""
    p = state.player
    if p.ally is not None and on(content, state.world):
        return p.ally
    return p.faction


def needs_ally(state: GameState, content: Content) -> bool:
    """投靠了要依附的陣營、還沒挑一邊（拜入曹氏莊院那一下）：選單只剩選邊（Game.options）。"""
    p = state.player
    return on(content, state.world) and p.ally is None and bool(allies_of(content, p.faction))


def rank_cap(state: GameState, content: Content) -> int | None:
    """豪強分屬兩軍的季，要依附的陣營（豪強）最多升到第 CAP_RANK 階；其他人不設上限（None）。第 4 階席次因此只給純官軍、純黃巾。"""
    p = state.player
    return CAP_RANK if on(content, state.world) and allies_of(content, p.faction) else None


def roll_key(faction: str, ally: str | None) -> str:
    """名冊的鍵：依附了一軍是「陣營@那一軍」，其他是陣營 id。"""
    return f"{faction}{SEP}{ally}" if ally else faction


def split_key(key: str) -> tuple[str, str | None]:
    """名冊的鍵 → （陣營, 依附的那一軍或 None）。"""
    faction, _, ally = key.partition(SEP)
    return faction, ally or None


def side_of_key(key: str | None) -> str | None:
    """名冊的鍵 → 算哪一方。"""
    if key is None:
        return None
    faction, ally = split_key(key)
    return ally or faction


def faction_totals(rolls: dict[str, int]) -> dict[str, int]:
    """名冊照陣營（身分）數：補假人、腳本照它。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        faction = split_key(key)[0]
        out[faction] = out.get(faction, 0) + n
    return out


def side_totals(rolls: dict[str, int]) -> dict[str, int]:
    """名冊照那一方數：名冊那一句、假人選邊照它。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        side = side_of_key(key) or key
        out[side] = out.get(side, 0) + n
    return out


def gentry_totals(rolls: dict[str, int]) -> dict[str, int]:
    """每一軍裡有幾個依附的人（名冊那一句的括號）。"""
    out: dict[str, int] = {}
    for key, n in rolls.items():
        ally = split_key(key)[1]
        if ally is not None:
            out[ally] = out.get(ally, 0) + n
    return out


def label(content: Content, faction_id: str | None, ally: str | None) -> str:
    """「地方豪強（依附官軍）」；沒有依附是陣營名（散人、劇本沒有的陣營是空字串）。"""
    name = content.scenario.faction_name(faction_id, "") or ""
    return ALLY_LABEL.format(faction=name, ally=content.scenario.faction_name(ally, ally)) if ally and name else name


def label_of(state: GameState, content: Content) -> str:
    """這個人此刻的陣營名號：依附的季寫依附哪一軍（label），其他季是陣營名；散人是空字串。"""
    p = state.player
    return label(content, p.faction, p.ally if on(content, state.world) else None)


def side_text(state: GameState, content: Content) -> str:
    """「此地還有」名字後面括號裡那一個（social.side）：依附的季寫「地方豪強・依附官軍」（FB-275：看得出是哪一邊的人），
    其他季、其他人是陣營名；散人是空字串。"""
    p = state.player
    name = content.scenario.faction_name(p.faction, "") or ""
    if p.ally and name and on(content, state.world):
        return ALLY_SHORT.format(faction=name, ally=content.scenario.faction_name(p.ally, p.ally))
    return name


def short_name(faction: FactionDef) -> str:
    """名冊括號裡的叫法：態勢那一套（rules.STANCE_NAMES：「豪強」），沒有就是陣營名。"""
    from .rules import STANCE_NAMES  # noqa: PLC0415  rules → allied：在函式裡 import，避免循環

    return STANCE_NAMES.get(faction.id, faction.name)


def roster_text(content: Content, world: WorldState, rolls: dict[str, int]) -> str:
    """名冊那一句（企劃者第 3 題甲）：依附的季照兩軍寫、括號寫豪強（「目前官軍 12 人（其中豪強 3 人）、黃巾軍 9 人」；括號裡是 0
    不寫）；其他季照陣營寫（「目前官軍 N 人、黃巾軍 M 人、地方豪強 K 人」）。人數照 side_totals，跟人數緩衝、假人選邊同一個數。"""
    factions = content.scenario.factions
    if not on(content, world):
        counts = faction_totals(rolls)
        return "目前" + "、".join(f"{f.name} {counts.get(f.id, 0)} 人" for f in factions)
    sides, gentry = side_totals(rolls), gentry_totals(rolls)
    short = "、".join(short_name(f) for f in factions if f.allies)
    parts = []
    for f in (f for f in factions if not f.allies):
        n = gentry.get(f.id, 0)
        parts.append(f"{f.name} {sides.get(f.id, 0)} 人" + (ALLY_COUNT.format(short=short, n=n) if n else ""))
    return "目前" + "、".join(parts)


def pick_side(name: str, option_ids: list[str], rolls: dict[str, int]) -> str | None:
    """假人選邊（設計第十三節）：選單上的選邊鈕裡，那一軍此刻人少的（照 side_totals，跟名冊那一句同一個數）；一樣多照名號雜湊，
    不碰任何亂數。沒有選邊鈕是 None。伺服器假人（bot_policy）與整季機器人（bot.pick）共用。"""
    picks = [i for i in option_ids if i.startswith(ALLY_PREFIX)]
    if not picks:
        return None
    sides = side_totals(rolls)

    def key(option_id: str) -> tuple[int, str]:
        side = option_id.removeprefix(ALLY_PREFIX)
        return sides.get(side, 0), hashlib.sha256(f"{name}|{side}".encode()).hexdigest()

    return min(picks, key=key)

