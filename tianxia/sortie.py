"""出陣（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第二節；遊歷改版）。

只有投靠了陣營的人、只在戰線地點（territory.line_of）；照這裡此刻歸誰（territory.controller）分攻、守、攪局。每人每天
Config.sortie.per_day 次（攻守攪局共用），跟回體丹同一套換日（Game._pill_day：pill_now 的現實時間、pill_day_utc_offset_hours 的 00:00）。
這裡只放純規則（開關、次數、哪一種、推多少、字）；打一場、發獎勵、記功在 engine.Game._sortie。
選項 id 照留 act:train（設計第二節：程式裡的 id 可以照留）：伺服器的大場面判讀（server.may_judge_fight）、網頁行動列、機器人、量表都認它。"""
from __future__ import annotations

from typing import Literal

from . import rules, territory
from .models import Content
from .state import PlayerState, WorldState

Mode = Literal["attack", "hold", "stir"]
NAME = "出陣"  # 待 joy 潤
MODE_NAMES: dict[str, str] = {"attack": "攻", "hold": "守", "stir": "攪局"}  # 待 joy 潤
LEFT_NOTE = "今日還能 {n} 次"  # 待 joy 潤：鈕上體力後面那一段
USED_UP = "今日已出陣 {n} 次，明日 00:00 後再出陣"  # 待 joy 潤（設計 2.3；鈕上不帶句號，行動列底下那一行補句號）
HOLD_LINE = "你在{place}整頓營伍、巡守要道，替自家守住這一處。"  # 待 joy 潤
STIR_LINE = "你在{place}四處放話、暗中撥弄兩邊，這一帶的局面又亂了幾分。"  # 待 joy 潤
PROLOGUE_FIGHT = "雪恥"  # 待 joy 潤：序章那一場寫好的仗（不算出陣次數，鈕上與紀錄標題寫它）
# 戰線正好 50 時攪局推不動（FB-253）：鈕灰著寫 STIR_FLAT（格子裡只露最後一小句「攪不動」）、底下那一行寫 STIR_FLAT_LINE。待 joy 潤
STIR_FLAT = "戰局正在中間，攪不動"
STIR_FLAT_LINE = "這條戰線正在中間，攪局推不動；等戰局偏向一邊再來（不花次數）。"
# 散人站在戰線地點（FB-250）：出陣那一顆灰著寫這個原因（不寫「不在戰線」）；行動列底下那一行寫 RANGER_LINE。待 joy 潤
RANGER_NOTE = "散人不能出陣"
RANGER_LINE = "散人不能出陣：投靠陣營之後才有。散人靠懸賞、事件與找素材撞上的仗出力。"
RANGER_LINE_PRECISE = "散人不能出陣：投靠陣營之後才有。散人靠懸賞、事件與練功打的仗出力。"  # 一類一顆（FB-420；待 joy 潤）


MERIT_LINE = "軍功賞銀 {silver} 兩已記上。"  # 待 joy 潤：出陣攻打贏的軍功賞（正式季整合 2.6），寫進這一場戰報的敘事


def on(content: Content) -> bool:
    """出陣開著：Config.sortie.enabled，而且劇本有陣營（不看第一季開關，同懸賞、叛投）。"""
    return content.config.sortie.enabled and bool(content.scenario.factions)


def ranger_here(content: Content, faction: str | None, loc_id: str, world: WorldState | None = None) -> bool:
    """散人站在戰線地點（FB-250）：投靠了陣營的人在這裡會有出陣，散人沒有——那一格寫原因，不寫「不在戰線」。
    領地爭奪在這一季生效時（給了 world）出陣在每一塊區塊都有，照區塊判（不只戰線地點）。"""
    if faction is not None or not on(content):
        return False
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    if conquest.on(content, world):
        return loc_id in conquest.blocks(content)
    return territory.line_of(content, loc_id) is not None


def left_today(p: PlayerState, content: Content, today: int) -> int:
    """今天還能出陣幾次（today 是 Game._pill_day）。"""
    return max(0, content.config.sortie.per_day - (p.sorties_today if p.sortie_day == today else 0))


def spend(p: PlayerState, today: int) -> None:
    p.sorties_today = (p.sorties_today if p.sortie_day == today else 0) + 1
    p.sortie_day = today


def mode(content: Content, world: WorldState, faction: str | None, loc_id: str, foes: bool) -> Mode | None:
    """在這裡出陣是哪一種；None＝這裡沒有出陣鈕（散人、不是戰線地點、別人的地盤卻沒有能打的隊伍）。
    foes：這裡有能打的對手（Game._sortie_foes：控制方的隊伍，加上截糧帶來的敵方運糧隊）。
    陣營在這條戰線上沒有目標（豪強）一律攪局；別人控制的地方攻；自己控制的（地盤關著時：這裡沒有能打的）守，
    有截糧的運糧隊照打。"""
    if faction is None or not on(content):
        return None
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    if conquest.on(content, world):  # 領地爭奪（計畫 Task 6）：每一塊區塊都有出陣；自家的守（有截糧的運糧隊照打），別人的、中立的攻
        if loc_id not in conquest.blocks(content):
            return None
        if conquest.holder(world, content, loc_id) == faction:
            return "attack" if foes else "hold"
        return "attack" if foes else None
    line = territory.line_of(content, loc_id)
    side = content.scenario.find_faction(faction)
    if line is None or side is None:
        return None
    if not side.goals.get(line):
        return "stir"
    controller = territory.controller(world, content, loc_id)
    if controller is not None and controller != faction:
        return "attack" if foes else None
    return "attack" if foes else "hold"


def pushes(content: Content, world: WorldState, faction: str, loc_id: str, how: Mode) -> dict[str, float]:
    """這一下推哪幾條線、各推多少（季長倍數與盡頭阻力在 Game.push_trend 再打）：攻是地點寫的量（train_trend）往自己陣營的目標推；
    守是攻的 hold_share；攪局是攻的 hold_share、往 50 拉（線在 50 什麼都不推）。鍵照 rules.resolve_trend 換過（規則關著的季是黃巾聲勢）。"""
    loc = content.locations[loc_id]
    goals = rules.resolve_goals(content, world, content.scenario.faction(faction).goals)
    share = 1.0 if how == "attack" else content.config.sortie.hold_share
    out: dict[str, float] = {}
    for key, delta in loc.train_trend.items():
        target = rules.resolve_trend(content, world, key, loc_id)
        if target is None:
            continue
        if how == "stir":
            value = rules.world_trend_value(world, content, target)
            direction = -1 if value > 50 else 1 if value < 50 else 0
        else:
            direction = goals.get(target, 0)
        amount = abs(delta) * direction * share
        if amount:
            out[target] = out.get(target, 0.0) + amount
    return out
