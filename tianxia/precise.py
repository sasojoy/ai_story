"""一類一顆（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第二章；正式季整合第 3 批）：每一顆行動鈕只給一類東西，
按了一定拿到那一類，運氣只決定拿到多少。找素材一定給、不打仗；練功（新）一定打一場；找事件寫這裡多半給哪一類；交友只談話；
靜心感悟選錯給心得、不鎖；應召不再換掉別的鈕。

開關 Config.precise_actions，照開季蓋章（WorldState.precise_actions）；探索三選一（Config.explore_modes）也開著時才生效——
找素材只存在於三選一裡（10.1）。關著時一個字都不變。這裡放不看引擎的純規則，engine.Game 接線。
"""
from __future__ import annotations

from . import explore_modes, territory
from .models import Choice, Content, Effect, Event
from .state import GameState, WorldState

MEET_FLAG = "結識:"  # 結識事件立的旗標（rules.can_meet 看到它就不看名望門檻）


def on(content: Content, world: WorldState | None) -> bool:
    """一類一顆開著沒：設定打開、這一季開季時也蓋了章、探索三選一開著。"""
    return (content.config.precise_actions and world is not None and world.precise_actions
            and explore_modes.on(content))


def _effects(event: Event) -> list[Effect]:
    effects = [e for choice in event.choices for e in (choice.effect, choice.fail_effect)]
    if event.free_text is not None:
        effects += [event.free_text.effect, event.free_text.fail_effect]
    return effects


def meets(event: Event) -> set[str]:
    """這則事件結識得到的人物 id（選項立「結識:X」旗標）。"""
    return {flag.removeprefix(MEET_FLAG) for e in _effects(event) for flag in e.flags_add if flag.startswith(MEET_FLAG)}


def joins_sect(event: Event) -> bool:
    """拜入門派的事件（選項帶 join_sect）：一類一顆開著時改成「此地還能做」的一顆（2.7【PM】），不再從交友抽。"""
    return any(e.join_sect for e in _effects(event))


def kept_social(event: Event) -> bool:
    """一類一顆開著時還留在交友的事件（2.7【PM】）：結識（名望不夠時見到人物的另一條路）與一次性、奇遇（搬進找事件會落進 2.5% 的奇遇池）。
    一次性的那幾則不是人物類，是 2.8「交友只談話」的例外（待企劃者）。"""
    return bool(meets(event)) or event.once or event.qiyu


def field_with_foes(state: GameState, content: Content) -> bool:
    """所在地是城外、而且站著不是自己陣營的隊伍（地盤易手照控制方，territory.squads_at；同 Game._wild_foes 的敵我）。"""
    loc = content.locations[state.player.location]
    if explore_modes.is_town(content, loc):
        return False
    mine = state.player.faction
    return any(
        sid in content.squads and (content.squads[sid].faction is None or content.squads[sid].faction != mine)
        for sid in territory.squads_at(state.world, content, loc.id)
    )


def actions_of(event: Event, state: GameState, content: Content) -> set[str]:
    """這則事件此刻算在哪幾種行動的池子裡（events.event_candidates 照它篩）。開關關著照內容寫的 actions。開著時：
    交友事件除了留在交友的（kept_social）都併進找事件（explore）；拜入門派的改成 sect（Game 的「此地還能做」）；
    戰後事件（actions 寫 train 的，已改寫成不必剛打過一場）在城外有對手的地方併進找事件（2.5【PM】）——內容照舊寫 train，
    開關關著的季照舊接在仗後面。"""
    acts = set(event.actions)
    if not on(content, state.world):
        return acts
    if "socialize" in acts:
        if joins_sect(event):
            acts = (acts - {"socialize"}) | {"sect"}
        elif not kept_social(event):
            acts = (acts - {"socialize"}) | {"explore"}
    if "train" in acts and field_with_foes(state, content):
        acts.add("explore")
    return acts


# ── 找事件鈕上的「這裡多半給」（2.7【PM】）──
# 名望、善名、惡名分開寫；屬性點、學武學、伏筆物品、痕跡、拜門派不算；回體力與寶物、良駒算「裝備與丹藥」；動手打贏算「經驗」。
STAT_KINDS = {"fame": "名望", "good": "善名", "evil": "惡名", "silver": "銀兩", "xinde": "心得"}  # 待 joy 潤
EXP_KIND, MATERIAL_KIND, INSIGHT_KIND, AFFINITY_KIND, COMPANION_KIND, GEAR_KIND = (
    "經驗", "素材", "意境", "情誼", "同伴", "裝備與丹藥")  # 待 joy 潤
_KINDS: dict[int, tuple[Choice, tuple[str, ...]]] = {}  # 選項 → 成功時給的幾類（照內容算一次；id 撞號時比對物件本身）


def effect_kinds(effect: Effect) -> list[str]:
    kinds = [STAT_KINDS[k] for k, v in effect.stats.items() if v > 0 and k in STAT_KINDS]
    if effect.materials:
        kinds.append(MATERIAL_KIND)
    if effect.insights:
        kinds.append(INSIGHT_KIND)
    if any(v > 0 for v in effect.affinity.values()):
        kinds.append(AFFINITY_KIND)
    if effect.recruit:
        kinds.append(COMPANION_KIND)
    if effect.stamina > 0 or effect.gear:
        kinds.append(GEAR_KIND)
    return kinds


def choice_kinds(choice: Choice, content: Content) -> tuple[str, ...]:
    """這個選項成功（檢定過、打贏、沒有檢定）時給哪幾類。快取起來（內容不會變）。"""
    hit = _KINDS.get(id(choice))
    if hit is not None and hit[0] is choice:
        return hit[1]
    kinds = effect_kinds(choice.effect)
    if choice.combat and choice.combat in content.squads and content.squads[choice.combat].exp > 0:
        kinds.insert(0, EXP_KIND)
    found = tuple(dict.fromkeys(kinds))
    _KINDS[id(choice)] = (choice, found)
    return found


def top_kinds(shares: dict[str, float]) -> list[str]:
    """取出現機會最多的兩類；只有一類過三成時只寫那一類。shares 是每一類的機會（0～1）。"""
    ranked = sorted((k for k, v in shares.items() if v > 0), key=lambda k: -shares[k])
    over = [k for k in ranked if shares[k] > 0.3]
    return over if len(over) == 1 else ranked[:2]
