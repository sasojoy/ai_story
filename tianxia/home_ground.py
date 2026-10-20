"""主場（輿圖重製 1c，企劃者 2026-10-20「長社火攻照長社此刻歸誰定難易」；BattleDef.home、Config.conquest.home_shift／home_away_share）。

時刻表決戰在內容裡寫「看哪一塊的控制方」（home.block）與「主場人物是誰」（home.figure）；領地爭奪開著的季（conquest.on），開集結那一刻
（world._open_claimed，排在屯糧練兵、天命之爭、龍頭上陣之前）照那一塊此刻歸誰：
- 主場人物那一方佔著：他坐鎮那裡，龍頭上陣全額；戰局起點往那一方偏 home_shift。
- 對面佔著：起點往佔著的那一方偏 home_shift；主場人物遠道而來，上陣份量 × home_away_share（generals.pick 叫 weight）。
- 還沒人佔（中立）：起點不偏，主場人物照常上陣。
三種都把主場人物調到那一塊（他開季可能站在外圈，龍頭上陣照所在挑人的那幾場挑不到他）；只調在場（active）的人——被打退、退場、
下獄、還沒出場的照現在的規則不動、不上陣。偏移跟屯糧練兵、天命之爭的一樣直接加在 trend 與 trend_start 上，另外夾著不推進
「一開打就壓倒性收場」那一帶（50±decisive_margin），已經在帶外的不拉回來；跟屯糧練兵的偏移合計夾在 ±home_stack_cap（stack，
works.on_muster 叫；企劃者 2026-10-20 答主場優勢要「錦上添花」，PM 定合計 ±8）。開集結那一刻的樣子快照進 BattleInstance.home，決戰畫面照它寫。
領地爭奪關著、或這一場沒寫主場時什麼都不做：三種季一個字都不變。長社火攻是第一個用的；宛城、廣宗先不套。
只 import models、state、battle_instance、conquest、figures；world 與 generals 反過來叫這裡。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import battle_instance, conquest, figures
from .models import BattleDef, Content
from .state import GameState, Rumor, WorldState

if TYPE_CHECKING:
    from .world_state import WorldStateStore

# 待 joy 潤：天下大事（開集結那一刻）；holder 是佔著那一塊的那一軍（決戰定義裡的名字）
RUMOR_HELD = "{battle}開集結：{holder}早已據{block}，{figure}閉城以待。"  # 主場人物那一方佔著
RUMOR_AWAY = "{battle}開集結：{holder}早已據{block}，{figure}遠道而來。"  # 對面佔著
RUMOR_OPEN = "{battle}開集結：{block}還沒有人佔下，{figure}引兵趕到。"  # 還沒人佔
RUMOR_HELD_ALONE = "{battle}開集結：{holder}早已據{block}。"  # 主場人物不在場（被打退、退場……）
RUMOR_OPEN_ALONE = "{battle}開集結：{block}還沒有人佔下。"
# 待 joy 潤：決戰畫面那一句
SCENE_HELD = "主場：{block}此刻在{holder}手裡"
SCENE_OPEN = "主場：{block}還沒有人佔下"
SCENE_FIGURE = {"held": "，{figure}坐鎮城中", "away": "，{figure}遠道而來，上陣的份量打了折", "open": "，{figure}引兵趕到"}
SCENE_SHIFT = "；戰局起點往{side}偏了 {n} 點。"
SCENE_STILL = "；戰局起點不偏。"


def holder_now(world: WorldState | None, content: Content, definition: BattleDef) -> str | None:
    """這一場的主場此刻歸誰：交戰兩軍之一的 id、還沒人佔是 conquest.NEUTRAL；沒寫主場、領地爭奪關著是 None（什麼都不做）。
    佔著的不是這一場交戰的兩軍（不會發生：區塊只歸兩軍）也當中立。"""
    home = definition.home
    if home is None or not conquest.on(content, world):
        return None
    side = conquest.holder(world, content, home.block)
    return side if side in {f.id for f in definition.factions} else conquest.NEUTRAL


def _case(content: Content, definition: BattleDef, holder: str) -> str:
    """held（主場人物那一方佔著）、away（對面佔著）、open（還沒人佔）。"""
    if holder == conquest.NEUTRAL:
        return "open"
    fig = content.figures.get(definition.home.figure) if definition.home is not None else None
    return "held" if fig is not None and fig.faction == holder else "away"


def shift_of(content: Content, definition: BattleDef, holder: str) -> int:
    """起點往佔著的那一方偏幾點（正的往 factions[0]，同 trend 的方向）；還沒人佔不偏。"""
    if holder == conquest.NEUTRAL:
        return 0
    n = content.config.conquest.home_shift
    return n if holder == definition.factions[0].id else -n


def _clamp(trend: int, shift: int, definition: BattleDef) -> int:
    """加上偏移，夾在 0～100；往外推時不推進 50±decisive_margin 那一帶（已經在帶外的不拉回來）。"""
    edge = definition.decisive_margin - 1
    moved = trend + shift
    if shift > 0:
        moved = min(moved, max(trend, battle_instance.CENTER + edge))
    elif shift < 0:
        moved = max(moved, min(trend, battle_instance.CENTER - edge))
    return max(0, min(100, moved))


def stack(content: Content, note: battle_instance.HomeNote | None, raw: int) -> int:
    """屯糧練兵那一份偏移（raw，works.lean）照主場夾過之後還剩多少（PM 2026-10-20：主場與屯糧合計夾在 ±home_stack_cap 以內，同方向疊加時
    才撞得到）。主場那一份已經在 cap 外（N 調得比 cap 大）時不往回拉，只是不再往外加。沒有主場（領地爭奪關著、這一場沒寫）原樣回。"""
    if note is None:
        return raw
    cap = content.config.conquest.home_stack_cap
    total = note.shift + raw
    if total > cap:
        total = max(cap, note.shift)
    elif total < -cap:
        total = min(-cap, note.shift)
    return total - note.shift


def weight(state: GameState, content: Content, definition: BattleDef, fid: str) -> float:
    """龍頭上陣的份量乘多少（generals.pick）：主場人物、那一塊歸他的對面時是 home_away_share，其餘 1。"""
    home = definition.home
    if home is None or fid != home.figure:
        return 1.0
    holder = holder_now(state.world, content, definition)
    if holder is None or _case(content, definition, holder) != "away":
        return 1.0
    return content.config.conquest.home_away_share


def on_muster(world: WorldStateStore, content: Content, definition: BattleDef) -> list[str]:
    """剛開集結（world._open_claimed，不在任何 mutate 裡）：照主場此刻歸誰把主場人物調過去、起點偏過去、快照進這一場、天下大事一句。
    沒有主場、領地爭奪關著回空、不寫入。"""
    holder = holder_now(world.get_season(), content, definition)
    if holder is None:
        return []
    from .world import _season_vehicle  # noqa: PLC0415  world → home_ground：延後 import（同 generals）

    home = definition.home
    case = _case(content, definition, holder)
    shift = shift_of(content, definition, holder)
    names = {f.id: f.name for f in definition.factions}
    text: dict[str, str] = {}
    moved: list[str] = []

    def _go(season: WorldState) -> None:
        vehicle = _season_vehicle(content, season)
        if home.figure in content.figures and figures.state_of(vehicle, content, home.figure).status == "active":
            figures._ensure(vehicle, content, home.figure).location = home.block  # noqa: SLF001  同 figure_life 的走動
            moved.append(home.figure)
        place = content.locations[home.block].name
        who = figures.name_of(content, home.figure)
        if moved:
            line = {"held": RUMOR_HELD, "away": RUMOR_AWAY, "open": RUMOR_OPEN}[case]
        else:
            line = RUMOR_OPEN_ALONE if case == "open" else RUMOR_HELD_ALONE
        text["line"] = line.format(battle=definition.name, holder=names.get(holder, holder), block=place, figure=who)
        season.rumors.append(Rumor(time=season.time, text=text["line"], location=home.block, layer="world"))

    world.mutate_season(_go)
    note = battle_instance.HomeNote(holder=holder, shift=shift, figure=moved[0] if moved else None)

    def _snap(b: battle_instance.BattleInstance) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.home = note
            b.trend = b.trend_start = _clamp(b.trend, shift, definition)

    world.mutate_battle(_snap)
    return [f"🏯 【天下大事】{text['line']}"]


def scene_line(content: Content, definition: BattleDef, battle: battle_instance.BattleInstance) -> str:
    """決戰畫面那一句（照開集結那一刻的快照）；沒有主場是空字串。"""
    note = battle.home
    if note is None or definition.home is None or definition.home.block not in content.locations:
        return ""
    names = {f.id: f.name for f in definition.factions}
    place = content.locations[definition.home.block].name
    case = _case(content, definition, note.holder)
    head = (SCENE_OPEN if case == "open" else SCENE_HELD).format(block=place, holder=names.get(note.holder, note.holder))
    who = SCENE_FIGURE[case].format(figure=figures.name_of(content, note.figure)) if note.figure else ""
    if note.shift:
        side = definition.factions[0] if note.shift > 0 else definition.factions[1]
        tail = SCENE_SHIFT.format(side=side.name, n=abs(note.shift))
    else:
        tail = SCENE_STILL
    return head + who + tail
