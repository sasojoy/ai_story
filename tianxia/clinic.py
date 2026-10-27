"""醫館（企劃者 2026-10-12「療傷我認為不能隨地療傷，應該去城鎮有醫館的地方讓玩家不能無腦打怪升級」）：
療傷（清內傷、氣血回滿，team.heal）只在帶「醫館」標籤的地點做得了。修練頁的療傷鈕、江湖頁「此地還能做」的療傷、
Game.heal 都問這裡；離開醫館時寫最近的一家在哪。氣血隨時間回、打坐、閉關、吸取與回春都只回到「上限－內傷」，內傷只有醫館治得好。
Config.heal_at_clinic 關著時哪裡都能療傷（測試內容關著）。只 import models、state、atlas。
《符水與湯藥》湯藥那條路收在 zhongjing_owes（仲景欠你一次）：這一季療傷打 Config.zhongjing_clinic_share 折，第一次用到時大夫多一句。"""

from __future__ import annotations

from . import atlas
from .models import Content
from .state import GameState

CLINIC_TAG = "醫館"  # 地點標籤（content/locations.json）；不寫死地點 id
HEAL = "醫館療傷"  # 江湖頁「此地還能做」那一顆（act:heal）
NONE_HERE = "這裡沒有醫館"


def on(content: Content) -> bool:
    return content.config.heal_at_clinic


def clinics(content: Content) -> list[str]:
    """帶醫館標籤的地點 id，照內容順序。"""
    return [loc_id for loc_id, loc in content.locations.items() if CLINIC_TAG in (loc.tags or [])]


def here(state: GameState, content: Content) -> bool:
    """人在醫館裡：開關關著時哪裡都算；在路上不算（還沒走進哪一家）。"""
    if not on(content):
        return True
    if state.player.journey is not None:
        return False
    return CLINIC_TAG in (content.locations[state.player.location].tags or [])


def nearest(state: GameState, content: Content) -> atlas.Route | None:
    """離所在地路程最近的醫館：先照摸清的路找（atlas.routes），一家都走不到時照所有開放的地點找；都沒有是 None。
    在路上時照身後那一站（player.location）算。"""
    targets = set(clinics(content))
    for found in (atlas.routes(state, content), atlas.shortest_routes(state, content)):
        reachable = [route for loc_id, route in found.items() if loc_id in targets and route.path]
        if reachable:
            return min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path))
    return None


def problem(state: GameState, content: Content) -> str | None:
    """不在醫館時的那一句（「這裡沒有醫館，最近的在宛城。」）；在醫館或開關關著是 None。"""
    if here(state, content):
        return None
    route = nearest(state, content)
    if route is None:
        return f"{NONE_HERE}。"
    return f"{NONE_HERE}，最近的在{content.locations[route.path[-1]].name}。"


ZHONGJING = "zhongjing_owes"  # 《符水與湯藥》湯藥的結局立的旗標（content/storylines.json 的 fuzhi）；flags 換季就清
ZHONGJING_TOLD = "zhongjing_owes_told"  # 大夫那一句說過了
ZHONGJING_LINE = ("醫館的大夫多說了一句：「南陽張家二郎的信，我看過。他說你來了就少收一點。"
                  "他還說，你要是先冷後熱、不出汗，別自己硬撐。」")


def zhongjing_factor(state: GameState, content: Content) -> float:
    """仲景欠你一次：療傷價錢的倍數（team._price_here 乘上它）；沒有旗標是 1。"""
    return content.config.zhongjing_clinic_share if ZHONGJING in state.player.flags else 1.0


def zhongjing_note(state: GameState) -> list[str]:
    """第一次靠仲景的名字少付錢時大夫多說的那一句（一季一次）；沒有旗標或說過了是空的。"""
    flags = state.player.flags
    if ZHONGJING not in flags or ZHONGJING_TOLD in flags:
        return []
    flags.add(ZHONGJING_TOLD)
    return [ZHONGJING_LINE]
