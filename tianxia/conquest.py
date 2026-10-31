"""領地爭奪（第 38 項改版；設計 docs/superpowers/specs/2026-10-20-領地爭奪-design.md，計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md）。

第一季的地圖分成三種區塊（Scenario.territory.blocks，一塊＝一個地點）：中立（高階獎勵，兩軍爭奪）、官軍與黃巾各自的陣營領地。
- 地盤開著（territory.on）就是領地爭奪，沒有開關、不看開季的章（2026-10-27 舊的拔河與割據拿掉）；判斷一律走 on(content, world)。
- 開著時控制方只照佔領（攻城戰的結果、時刻表指定、管理者改），不拔河、不割據；此刻的控制方照舊記在 TerritoryState.control
  （所以讀控制方的地方都不用改），開季中立而沒人佔的區塊不在裡面（controller 回 None）。
- 三條戰線的值＝佔領的基準＋其他來源累積的偏移，夾在 0～100（設計 4.7）；值照舊存在 world.trends[戰線]，讀線的地方都不用改。
  rules.change_trend 推的是偏移（apply_push，夾值只在顯示那一刻做，FB-530）；決戰收場、管理者這類直接改了線的，下一次 reweigh
  照上一次的基準重錨偏移。
- 出陣不推線、推那一塊的進度（翻地與爭搶，輿圖簡化設計第四章，計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）：每一塊對每個攻方
  各一條 0～100（ConquestState.fights，BlockFight.bars），攻推自己那一條、守（此刻佔著的那一方）把每一條都拉下，任一條到 100 當場易手（flip：
  分紅、冷卻、加成暫停）；沒人推的每個季曆日往回（decay）；同一邊一起推有集火（focus_bonus）；混戰的判定在出陣包（features/sortie/actions.do_clash），
  這裡只給「誰剛在這裡推過」（clash_names）。翻地對 N 方成立：進度、帳、控制方都照陣營 id 存（設計第九章第 12 條）。
- 攻城戰（siege.py）改成第 4 階的人下戰書觸發（letter_problem；排時段在 conquest_day.py）；投票與每天 22:00 的公告結算拿掉了。
只讀寫 WorldState；天下大事與江湖史照 territory._announce。territory 反過來在函式裡延後 import 這裡。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import calendar, rules, seal_acts, territory
from .battle_instance import CENTER, FrontNote
from .characters import name_key
from .models import BattleDef, BlockDef, Content
from .state import (
    Bar, BlockFight, ConquestPayout, ConquestState, DayNote, GameState, PushMark, Rumor, SiegeSlot, TerritoryState, WorldState,
)

SIDES = territory.SIDES  # 交戰兩軍（設計 4.1：豪強不佔地）；戰線往 100 是黃巾、往 0 是官軍（劇本的 goals）
NEUTRAL = "neutral"
NEUTRAL_LINE = "中立地・高階獵場，還沒有人佔"  # 待 joy 潤：輿圖詳情欄局勢那一行（還沒人佔的中立地）
NEUTRAL_HELD = "（開季是中立地）"  # 待 joy 潤：被佔下的中立地，接在「此刻由某某控制」後面


def on(content: Content, world: WorldState | None = None) -> bool:
    """這一季照領地爭奪的規則：地盤開著（territory.on）就是，不看季（world 只是舊的呼叫寫法，留著不用）。"""
    return territory.on(content)


def blocks(content: Content) -> dict[str, BlockDef]:
    """地點 → 區塊（Scenario.territory.blocks）；劇本沒寫是空的。"""
    t = content.scenario.territory
    return dict(t.blocks) if t is not None else {}


def start_kind(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這個區塊開季那一刻的種類（neutral／guan／huang）：這一季算過就讀抄下來的（之後內容改了不跟著動），沒算過照內容；不是區塊是 None。"""
    if world is not None and world.conquest is not None and loc_id in world.conquest.start:
        return world.conquest.start[loc_id]
    block = blocks(content).get(loc_id)
    return block.kind if block is not None else None


def line_of(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這個區塊算進哪一條戰線（BlockDef.line）；不是區塊、或不算進任何一條是 None。"""
    block = blocks(content).get(loc_id)
    return block.line if block is not None else None


def capturable(content: Content, loc_id: str) -> bool:
    """搶得下來的區塊：是區塊、不是大本營（投靠點，設計 3.2）、不是 fixed（廣宗只照廣宗決戰易手）。"""
    t = content.scenario.territory
    return loc_id in blocks(content) and loc_id not in territory.bases(content) and (t is None or loc_id not in t.fixed)


def adjacent(content: Content, loc_id: str) -> list[str]:
    """跟這一塊有路直通的區塊（設計 3.2「輿圖上有路直通」）：照 Location.connections（兩個方向都算），不穿過不是區塊的地點；照內容順序。"""
    table = blocks(content)
    loc = content.locations.get(loc_id)
    if loc is None:
        return []
    near = {str(x) for x in loc.connections}
    near |= {other for other, place in content.locations.items() if loc_id in {str(x) for x in place.connections}}
    return [other for other in table if other in near and other != loc_id]


def reach(content: Content, side: str) -> set[str]:
    """side 開季持有的區塊（大本營、fixed 也算）出發、只走 side 自己與中立的區塊（adjacent：有路直通、不穿過不是區塊的地點）走得到的
    區塊，照內容的開季種類、不看劇情開放了沒。content.check_conquest_blocks 拿它驗「每一塊中立地每一方都走得到」（輿圖簡化設計 3.2，
    PM 2026-10-21）；side 是劇本裡任何一方都行，不只兩軍。"""
    table = blocks(content)
    seen = {loc for loc, block in table.items() if block.kind == side}
    todo = list(seen)
    while todo:
        for nxt in adjacent(content, todo.pop()):
            if nxt not in seen and table[nxt].kind in (side, NEUTRAL):
                seen.add(nxt)
                todo.append(nxt)
    return seen


def holder(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這一塊此刻歸誰（中立而沒人佔是 None）：這一季算過照 TerritoryState.control，還沒算過照開季的種類。"""
    t = world.territory if world is not None else None
    if world is not None and world.conquest is not None and t is not None:
        return t.control.get(loc_id)
    kind = start_kind(world, content, loc_id)
    return kind if kind in SIDES else None


def neutral_squads(world: WorldState | None, content: Content, loc_id: str) -> list[str]:
    """開季中立的區塊站的隊伍（設計 3.3；territory.squads_at 在開關開著時叫）：地點自己的流寇野獸（Location.enemies 裡沒有陣營的）
    加上中立駐軍（Scenario.territory.neutral_garrison，待 joy）；不看控制方，佔下之後對兩邊都照打。不動 Location.enemies
    （探索事件的 combat 守門讀它）。"""
    loc = content.locations[loc_id]
    own = [sid for sid in loc.enemies if sid in content.squads and content.squads[sid].faction is None]
    extra = content.scenario.territory.neutral_garrison.get(loc_id, []) if content.scenario.territory is not None else []
    return own + [sid for sid in extra if sid not in own]


HOME_GATHER_LINE = "自家地盤，多撿了一份。"  # 待 joy 潤：人站在自家領地找素材多給的那一個（設計 4.5）

# ── 翻地與爭搶（輿圖簡化設計第四章）：每一塊對每個攻方一條 0～FULL 的進度 ──
FULL = 100.0
# 推完那一句（輿圖簡化設計第五章起進度看得到數字，卡上畫進度條）。待 joy 潤
PUSH_LINE = "你在{place}替{side}推進了 {moved}，進度 {value}／100{notes}。"
FOCUS_NOTE = "，集火 +{pct}%"  # 一小時內同一邊還有別人推過這一塊（設計 4.2）
CLASH_NOTE = "，混戰得勝推得更多"  # 撞上對面、打贏了那一下（設計 4.3）
PULL_LINE = "你在{place}守了一陣，把對面的進度拉回了 {moved}{notes}。"
# 這一下不到半點（四捨五入是 0）：不寫「推進了 0」「拉回了 0」，寫「一點」（翻地 QA 順帶：拉回 0.41 寫成「拉回了 0」接「全數歸零」）。待 joy 潤
PUSH_LITTLE = "你在{place}替{side}推進了一點，進度 {value}／100{notes}。"
PULL_LITTLE = "你在{place}守了一陣，把對面的進度拉回了一點{notes}。"
PULL_ZERO = "對面在{place}的進度全數歸零。"
FLIP_LINE = "{place}的進度推滿了，當場易手！"  # 推滿那一下，接著是 territory 的「落入／收復」天下大事
GUARDED_LINE = "{place}守住了：對面的進度從五成以上被拉回零。"  # 守城功（設計 4.5）
TOP_TAKE = "{name}率先攻入{place}。"  # 江湖史：推最多的那一個（設計 4.5）
TOP_GUARD = "{name}力保{place}不失。"  # 江湖史：守城功拉回最多的那一個
PAYOUT_NEXT = "推過這一塊的人照出力分紅，稍後送到。"
# 推不動的原因（行動列底下出陣那一行、卡上、鈕上；push_problem）。待 joy 潤
WHY_COOLING = "剛易手，{n} 分後才能再推"  # 設計 4.1【企劃者】
WHY_FROZEN = "已下戰書，進度凍結到那一場攻城打完"  # 設計 4.4
# FB-552（PM 2026-10-20）：被戰書凍結的那一塊，原因照那一場攻城在哪一步寫（_step）——開了集結就叫人去加入，開打了就說在打。待 joy 潤
WHY_MUSTER = "這一塊的攻城正在集結，去加入攻城"
WHY_FIGHTING = "這一塊的攻城正在開打"
FROZEN_WHY = {"planned": WHY_FROZEN, "muster": WHY_MUSTER, "fight": WHY_FIGHTING}
WHY_OUT = "這裡搶不下來"  # 大本營、廣宗
WHY_CUT = "這裡跟自家的領地不相連"
WHY_NO_FOE = "這裡找不到對手"
WHY_LOCKED = "劇情還沒走到這裡"
WHY_IDLE = "沒有人在推這裡，守了也拉不動"
WHY_OWN = "這裡是自家的地方"
WHY_OFF = "這一季沒有翻地"
# 玉璽碎片改版第 3 批：有人起用『螭首』鎮住了這一塊（seal_acts.held；攻、守、事件、戰書都推不動，那一天也不回）。待 joy 潤
WHY_HELD = "這一塊被鎮住了，{until} 之前誰都推不動"
# 戰書（設計 4.4）拒絕的原因。待 joy 潤
LETTER_LOW = "進度要到 {at} 才能下戰書（此刻 {value}）"
LETTER_USED = "{side}今天已經下過戰書了，{hour}:00 之後才能再下"
LETTER_JOINED = "{side}已經對這一塊下了戰書"
LETTER_OPEN = "這一塊的攻城已經開了集結"


@dataclass
class Pushed:
    """push 的結果：這一下推（拉）動了多少、自己那一條推完是多少（守是剩下最高的那一條）、有沒有當場易手、有沒有守城功、要寫的句子。"""

    moved: float = 0.0
    value: float = 0.0
    flipped: bool = False
    guarded: bool = False
    lines: list[str] = field(default_factory=list)


def sortie_foes(world: WorldState, content: Content, loc_id: str, own: str | None) -> list[str]:
    """出陣攻打的對手（Game._sortie_foes 在開關開著時叫；截糧的運糧隊另外由呼叫端加）：自家控制的區塊沒有（守）；開季中立的區塊是
    那裡站的全部（中立駐軍與流寇野獸，計畫 Task 6）；別人控制的陣營區塊是控制方站的隊伍，那裡沒寫 garrison 時照
    Scenario.territory.side_garrison（控制方的巡邏，待 joy），不然官軍的城鎮誰都攻不了。不是區塊是空的；別人的大本營與廣宗
    （搶不下來，不在爭奪之列）也是空的——不給攻、輿圖不畫 ⚔（計畫第八章裁決 18）。"""
    if loc_id not in blocks(content):
        return []
    side = holder(world, content, loc_id)
    if side is not None and side == own:
        return []
    if not capturable(content, loc_id):
        return []
    squads = territory.squads_at(world, content, loc_id)
    if start_kind(world, content, loc_id) == NEUTRAL:
        return squads
    if side is None:
        return [sid for sid in squads if content.squads[sid].faction != own]
    mine = [sid for sid in squads if content.squads[sid].faction == side]
    return mine or list(content.scenario.territory.side_garrison.get(side, []))


def _step(world: WorldState, slot: SiegeSlot) -> str:
    """一場攻城在哪一步：planned（planned、waiting：下了戰書、還沒開集結）、muster（開了集結、還沒到開打的時刻）、fight（開打了、還在打）、
    done、void。"""
    if slot.status in ("planned", "waiting"):
        return "planned"
    if slot.status == "open":
        return "muster" if world.time < slot.at else "fight"
    return slot.status


def siege_state(world: WorldState | None, loc_id: str) -> str | None:
    """這一塊的攻城在哪一步（FB-552：出陣那一行照實寫）：沒排過是 None；其餘照 _step（planned＝下了戰書、還沒開集結，那一塊的進度凍結；
    muster、fight 也凍結；done、void 解凍）。這一塊排了不只一場時取最後排的那一場（時程表照先後）。只讀 WorldState，不判進度推不推得動
    （push_problem 判；被凍結時的原因照這一步寫，FROZEN_WHY）。"""
    if world is None or world.conquest is None:
        return None
    slots = [slot for slot in world.conquest.schedule if slot.loc == loc_id]
    return _step(world, slots[-1]) if slots else None


def direction(content: Content, side: str | None, loc_id: str) -> int:
    """side 推這一塊的進度往哪邊：往 100 那一方 +1、往 0 那一方 −1（照那條線的兩頭；不算進任何一條線的照兩軍：黃巾 +1、官軍 −1）。"""
    line = line_of(None, content, loc_id)
    low, high = _sides(content, line) if line else ("guan", "huang")
    return 1 if side == high else -1 if side == low else 0


def sortie_nominal(content: Content, loc_id: str, how: str) -> float:
    """出陣推進度的名目量（貢獻照它記；計畫 2.3）：max(1, 地點寫的推量合計) ×（攻 1、守 Config.sortie.hold_share）。"""
    loc = content.locations[loc_id]
    share = 1.0 if how == "attack" else content.config.sortie.hold_share
    return max(1.0, float(sum(abs(v) for v in loc.train_trend.values()))) * share


def _seconds(content: Content, minutes: float) -> float:
    """現實分鐘換成世界秒（time_scale 1 時一樣）。"""
    return minutes * 60 * content.config.time_scale


def fight_of(world: WorldState | None, loc_id: str) -> BlockFight | None:
    """這一塊的翻地帳（沒推過是 None）；只讀。"""
    state = world.conquest if world is not None else None
    return state.fights.get(loc_id) if state is not None else None


def _fight(world: WorldState, content: Content, loc_id: str) -> BlockFight:
    """這一塊的翻地帳，沒有就開一本（這一季還沒算過先算）。"""
    if world.conquest is None:
        update(world, content)
    return world.conquest.fights.setdefault(loc_id, BlockFight())


def bar(world: WorldState | None, loc_id: str, side: str | None) -> float:
    """side 在這一塊的那一條進度（0～FULL）；沒推過是 0。"""
    fight = fight_of(world, loc_id)
    found = fight.bars.get(side) if fight is not None and side is not None else None
    return found.value if found is not None else 0.0


def bars(world: WorldState | None, loc_id: str) -> dict[str, float]:
    """這一塊此刻每一條大於 0 的進度（攻方 → 值）。"""
    fight = fight_of(world, loc_id)
    return {side: b.value for side, b in fight.bars.items() if b.value > 0} if fight is not None else {}


def cooling_left(world: WorldState | None, content: Content, loc_id: str) -> float:
    """剛易手的冷卻還剩幾個世界秒（設計 4.1【企劃者】）；沒有是 0。"""
    fight = fight_of(world, loc_id)
    if fight is None or fight.flipped_at is None or not on(content, world):
        return 0.0
    return max(0.0, fight.flipped_at + _seconds(content, content.config.conquest.cooldown_minutes) - world.time)


def cooling(world: WorldState | None, content: Content, loc_id: str) -> bool:
    """這一塊剛易手、還在冷卻：兩邊都推不動，領地加成暫停（價錢福利、找素材多一份、感悟加點），中立駐軍只掉一階（drop_cap），碎片不擲。"""
    return cooling_left(world, content, loc_id) > 0


def cooling_minutes(world: WorldState | None, content: Content, loc_id: str) -> int:
    """冷卻還剩幾分鐘（無條件進位，寫給人看）。"""
    left = cooling_left(world, content, loc_id)
    return math.ceil(left / 60 / content.config.time_scale) if left > 0 else 0


def frozen(world: WorldState | None, loc_id: str) -> SiegeSlot | None:
    """這一塊被戰書凍結（設計 4.4：下了之後那一塊的進度凍結到那一場打完）：時程表上還沒打、或在打的那一場；沒有是 None。"""
    state = world.conquest if world is not None else None
    if state is None:
        return None
    return next((s for s in state.schedule if s.loc == loc_id and s.status in ("planned", "waiting", "open")), None)


def besieged(world: WorldState | None, content: Content, side: str | None, loc_id: str) -> bool:
    """side 佔著的這一塊被戰書凍結、正等著（或正在打）一場攻城（FB-605）：守城軍令照樣列它，記功在那一場攻城站守方、守住時記一次。
    開關關著、搶不下來、不是 side 的都不算。"""
    if not on(content, world) or side is None or loc_id not in blocks(content) or not capturable(content, loc_id):
        return False
    return holder(world, content, loc_id) == side and frozen(world, loc_id) is not None


def _target_problem(world: WorldState, content: Content, side: str, loc_id: str) -> str | None:
    """side 能不能把這一塊當成目標（設計 3.2、4.1；PM 2026-10-20 第 3 條：找不到對手的不算）：搶得下來、此刻不是 side 的、劇情開放了、
    跟 side 此刻控制的某一塊直通、那裡出陣攻打找得到對手。能是 None，不能是原因。"""
    if not capturable(content, loc_id):
        return WHY_OUT
    if holder(world, content, loc_id) == side:
        return WHY_OWN
    if not _opened(world, content, loc_id):
        return WHY_LOCKED
    if not any(holder(world, content, x) == side for x in adjacent(content, loc_id)):
        return WHY_CUT
    if not sortie_foes(world, content, loc_id, side):
        return WHY_NO_FOE
    return None


def _held_why(world: WorldState | None, content: Content, loc_id: str) -> str | None:
    """這一塊此刻被碎片鎮住（seal_acts.held：替此刻的主人鎮的、還沒期滿）：WHY_HELD 寫到什麼時候；沒有是 None。"""
    act = seal_acts.held(world, content, loc_id, holder(world, content, loc_id))
    if act is None:
        return None
    return WHY_HELD.format(until=calendar.stamp_text(seal_acts.ends(act), content, world))


def push_problem(world: WorldState | None, content: Content, side: str | None, loc_id: str, how: str | None) -> str | None:
    """side 此刻在這一塊攻（attack）或守（hold）推不推得動進度：推得動是 None，不然回原因（WHY_*，行動列底下那一行、卡上照寫）。
    攻＝這一塊是 side 的目標（_target_problem）；守＝此刻是 side 的、搶得下來、有哪一條 > 0；兩者都要不在冷卻、沒被戰書凍結
    （凍結的原因照那一場在哪一步：FROZEN_WHY，FB-552）、沒被碎片鎮住（WHY_HELD：玉璽碎片改版第 3 批的鎮地，誰都推不動）。"""
    if not on(content, world) or side is None or how not in ("attack", "hold") or loc_id not in blocks(content):
        return WHY_OFF
    if not capturable(content, loc_id):
        return WHY_OUT
    if cooling(world, content, loc_id):
        return WHY_COOLING.format(n=cooling_minutes(world, content, loc_id))
    slot = frozen(world, loc_id)
    if slot is not None:
        return FROZEN_WHY.get(_step(world, slot), WHY_FROZEN)
    hold = _held_why(world, content, loc_id)
    if hold is not None:
        return hold
    if how == "hold":
        if holder(world, content, loc_id) != side:
            return WHY_OUT
        return None if bars(world, loc_id) else WHY_IDLE
    return _target_problem(world, content, side, loc_id)


def focus_bonus(world: WorldState | None, content: Content, loc_id: str, side: str, name: str) -> float:
    """集火（設計 4.2）：focus_minutes 內同一邊還有幾個別人在這一塊出陣過，每多一個人多 focus_step、最多 focus_cap（0.3＝多三成）。"""
    fight = fight_of(world, loc_id)
    if fight is None:
        return 0.0
    cfg = content.config.conquest
    since = world.time - _seconds(content, cfg.focus_minutes)
    others = {m.name for m in fight.marks if m.side == side and m.at >= since and name_key(m.name) != name_key(name)}
    return min(cfg.focus_cap, cfg.focus_step * len(others))


def clash_names(world: WorldState | None, content: Content, loc_id: str, side: str, name: str) -> list[str]:
    """混戰的對象（設計 4.3）：clash_minutes 內在這一塊出陣過、跟 side 不同一邊的人（最近的在前、不重複）。人還在不在這裡、保護
    （新手期、冷卻、護身）由出陣包（features/sortie/actions.clash_target）讀了存檔再判。"""
    fight = fight_of(world, loc_id)
    if fight is None:
        return []
    since = world.time - _seconds(content, content.config.conquest.clash_minutes)
    out: list[str] = []
    for m in sorted(fight.marks, key=lambda x: -x.at):
        if m.at >= since and m.side != side and name_key(m.name) != name_key(name) and m.name not in out:
            out.append(m.name)
    return out


def _keep_seconds(content: Content) -> float:
    cfg = content.config
    return max(cfg.presence_seconds * cfg.time_scale, _seconds(content, cfg.conquest.focus_minutes),
               _seconds(content, cfg.conquest.clash_minutes))


def mark(world: WorldState, content: Content, loc_id: str, name: str, side: str, how: str, moved: float) -> None:
    """記一筆出陣（「正在推這裡的人」、集火、混戰讀它）；順手清掉太舊的。"""
    fight = _fight(world, content, loc_id)
    since = world.time - _keep_seconds(content)
    fight.marks = [m for m in fight.marks if m.at >= since] + [PushMark(name=name, side=side, how=how, moved=moved, at=world.time)]


def pushers(world: WorldState | None, content: Content, loc_id: str) -> list[dict]:
    """「正在推這裡的人」（設計 4.2，同「此地還有」的窗口 presence_seconds）：每個人一列（名號、哪一邊、最後一次是攻或守、這段時間推了多少），
    照哪一邊、推得多的在前。只有名號，不寫是不是假人。"""
    fight = fight_of(world, loc_id)
    if fight is None:
        return []
    since = world.time - content.config.presence_seconds * content.config.time_scale
    rows: dict[str, dict] = {}
    for m in sorted(fight.marks, key=lambda x: x.at):
        if m.at < since:
            continue
        row = rows.setdefault(name_key(m.name), {"name": m.name, "side": m.side, "how": m.how, "moved": 0.0})
        row["side"], row["how"] = m.side, m.how
        row["moved"] += m.moved
    return sorted(rows.values(), key=lambda r: (r["side"], -r["moved"], r["name"]))


def clashing(world: WorldState | None, content: Content, loc_id: str) -> bool:
    """激戰（設計 4.3：天下圖上紅光一閃一閃）：clash_minutes 內有兩邊以上在這一塊出陣過。"""
    fight = fight_of(world, loc_id)
    if fight is None:
        return False
    since = world.time - _seconds(content, content.config.conquest.clash_minutes)
    return len({m.side for m in fight.marks if m.at >= since}) >= 2


def _int(x: float) -> int:
    """四捨五入（.5 往上，同專案的寫法 int(x + 0.5)）。"""
    return int(x + 0.5)


def _little(moved: float) -> bool:
    """這一下推（拉）動了、可是四捨五入寫出來是 0：那一句改寫「一點」（PUSH_LITTLE、PULL_LITTLE）。"""
    return moved > 0 and _int(moved) == 0


def _note_day(world: WorldState, content: Content, loc_id: str, side: str, by: str, reason: str) -> None:
    """〈天下形勢〉讀的 day_log 記一筆（推滿易手、補缺退回）：哪一天照最近一次換天（settled_key）、時刻照季曆的那一刻。"""
    state = world.conquest
    at = calendar.point(world.time, content, world)
    state.day_log.append(DayNote(key=state.settled_key, side=side, loc=loc_id, minute=at.hour * 60 + at.minute, by=by, reason=reason))


def _payout(world: WorldState, content: Content, loc_id: str, side: str, kind: str, shares: dict[str, float]) -> None:
    """分紅（設計 4.5）：總額照這一塊開季的種類（中立全額、陣營 faction_pool_share；守城功再乘 guard_pool_share），照 shares（這一輪推了多少）
    的比例分銀兩、經驗、名望（四捨五入，都分到 0 的不發）；推最多的那一個記江湖史（TOP_TAKE／TOP_GUARD），行狀在他補的那一下記。
    記在 ConquestState.payouts，每個人自己同步時補（Game._deliver_conquest）。"""
    shares = {name: amount for name, amount in shares.items() if amount > 0}
    total = sum(shares.values())
    if total <= 0:
        return
    cfg = content.config.conquest
    scale = 1.0 if start_kind(world, content, loc_id) == NEUTRAL else cfg.faction_pool_share
    if kind == "guard":
        scale *= cfg.guard_pool_share
    top = min(shares, key=lambda n: (-shares[n], n))
    place = content.locations[loc_id].name
    for name, amount in sorted(shares.items(), key=lambda kv: (-kv[1], kv[0])):
        part = amount / total
        pay = ConquestPayout(
            name=name, kind=kind, loc=loc_id, side=side, share=round(part, 4), top=name == top, time=world.time,
            silver=_int(cfg.take_silver * scale * part), exp=_int(cfg.take_exp * scale * part), fame=_int(cfg.take_fame * scale * part),
        )
        if pay.silver or pay.exp or pay.fame or pay.top:
            world.conquest.payouts.append(pay)
    world.chronicle.append(Rumor(time=world.time, text=(TOP_TAKE if kind == "take" else TOP_GUARD).format(name=top, place=place)))


def flip(world: WorldState, content: Content, loc_id: str, side: str, note: bool = True) -> list[str]:
    """這一塊易手給 side（推滿那一下、攻城戰打贏；設計 4.1、4.4）：這一輪推過 side 那一條的人照出力分紅、推最多的上江湖史；
    控制方改成 side（set_control：「落入／收復」天下大事、江湖史、三條線當場重算）；所有條與守城功的帳清掉；冷卻從這一刻起算、記下這一刻
    之前歸誰（flipped_from，玉璽碎片改版第 3 批的補缺讀）；day_log 記一筆（by="flip"，〈天下形勢〉寫成「某某率先攻入」）——攻城戰打贏的不記
    （note=False：siege 自己記那一場的結果，同一件事不寫兩條）。回要寫進紀錄的句子。side 不是劇本的陣營、搶不下來的區塊不動（回空的）。"""
    if not capturable(content, loc_id) or content.scenario.find_faction(side) is None:
        return []
    fight = _fight(world, content, loc_id)
    before = holder(world, content, loc_id)
    shares = dict(fight.bars[side].pushers) if side in fight.bars else {}
    _payout(world, content, loc_id, side, "take", shares)
    set_control(world, content, loc_id, side)
    fight.bars, fight.guards, fight.alarm, fight.flipped_at, fight.flipped_from = {}, {}, False, world.time, before
    if note:
        top = min(shares, key=lambda n: (-shares[n], n)) if shares else ""
        _note_day(world, content, loc_id, side, "flip", top)
    return [PAYOUT_NEXT] if shares else []


def restore(world: WorldState, content: Content, loc_id: str, side: str) -> None:
    """玉璽碎片改版第 3 批的補缺：這一塊當場退回 side（原主），照翻地的規則記一次易手——set_control（「落入／收復」天下大事、江湖史、
    三條線當場重算、替別人鎮著的鎮地結束）、所有條與守城功的帳清掉、冷卻重新起算（加成暫停）、flipped_from 記退回之前歸誰。
    不分紅（沒有人推滿它）。day_log 記一筆（by="mend"，reason 空的：不記是誰，持有者要藏；〈天下形勢〉照時間順序寫「拿下某地，旋即被補回」，
    FB-646）。呼叫端（Game.seal_use）先驗過 seal_acts.mend_rows。"""
    if not capturable(content, loc_id) or content.scenario.find_faction(side) is None:
        return
    fight = _fight(world, content, loc_id)
    before = holder(world, content, loc_id)
    set_control(world, content, loc_id, side)
    fight.bars, fight.guards, fight.alarm, fight.flipped_at, fight.flipped_from = {}, {}, False, world.time, before
    _note_day(world, content, loc_id, side, "mend", "")  # conquest_day.MEND（conquest_day 反過來 import 這裡）


def halve(world: WorldState, content: Content, loc_id: str, sides: list[str]) -> None:
    """攻城戰打輸（設計 4.4「打輸進度砍半」）：這幾個攻方在這一塊的條各砍一半（這一輪的帳照留）。"""
    fight = fight_of(world, loc_id)
    if fight is None:
        return
    for side in sides:
        if side in fight.bars:
            fight.bars[side].value /= 2


def push(
    world: WorldState, content: Content, loc_id: str, side: str, name: str, amount: float, how: str, notes: str = "",
) -> Pushed:
    """推（how="attack"：side 那一條往上 amount）或拉（how="hold"：每一條都往下 amount）這一塊的進度；呼叫端已經確認 push_problem 是 None、
    算好了 amount（人數緩衝、集火、混戰）。攻：記進這一輪的帳、到 alarm_at 記一筆警報，到 FULL 當場 flip。守：拉回的量記在守城的帳，
    每一條都歸零時——這一輪有哪一條到過 alarm_at——守城功分紅（_payout）。不記出陣那一筆（mark 由呼叫端記）。notes 接在那一句裡。"""
    fight = _fight(world, content, loc_id)
    place = content.locations[loc_id].name
    cfg = content.config.conquest
    fight.last_push = world.time
    out = Pushed()
    if how == "attack":
        line = fight.bars.setdefault(side, Bar())
        before = line.value
        line.value = min(FULL, before + max(0.0, amount))
        out.moved, out.value = line.value - before, line.value
        line.pushers[name] = line.pushers.get(name, 0.0) + out.moved
        if line.value >= cfg.alarm_at:
            fight.alarm = True
        out.lines.append((PUSH_LITTLE if _little(out.moved) else PUSH_LINE).format(
            place=place, side=content.scenario.faction_name(side, side), moved=_int(out.moved), value=_int(out.value), notes=notes))
        if line.value >= FULL:
            out.flipped = True
            out.lines.append(FLIP_LINE.format(place=place))
            out.lines += flip(world, content, loc_id, side)
        return out
    for other, line in list(fight.bars.items()):
        cut = min(line.value, max(0.0, amount))
        line.value -= cut
        out.moved += cut
        if line.value <= 1e-9:
            del fight.bars[other]
    fight.guards[name] = fight.guards.get(name, 0.0) + out.moved
    out.value = max((b.value for b in fight.bars.values()), default=0.0)
    out.lines.append((PULL_LITTLE if _little(out.moved) else PULL_LINE).format(place=place, moved=_int(out.moved), notes=notes))
    if not fight.bars:
        out.lines.append(PULL_ZERO.format(place=place))
        if fight.alarm:
            out.guarded = True
            out.lines.append(GUARDED_LINE.format(place=place))
            _payout(world, content, loc_id, side, "guard", fight.guards)
            out.lines.append(PAYOUT_NEXT)
        fight.guards, fight.alarm = {}, False
    return out


def _still(world: WorldState, content: Content, loc_id: str) -> bool:
    """這一塊此刻誰都推不動（push_problem 的那三種）：剛易手的冷卻、被戰書凍結、被碎片鎮住。"""
    return cooling(world, content, loc_id) or frozen(world, loc_id) is not None or _held_why(world, content, loc_id) is not None


def pull(world: WorldState, content: Content, loc_id: str, side: str, amount: float) -> Pushed:
    """把這一塊上 side（攻方）那一條往下拉 amount、夾 0（減法季出陣約戰：守方贏了拉攻方那一條，企劃者 2026-10-24 第 1 件；
    計畫第四節 4.0 之二）。別的攻方的條不動；冷卻、戰書凍結、碎片鎮住（_still，同 push_problem 的「誰都推不動」）與關著的季什麼都不動。
    拉到 0 的那一條拿掉（這一輪的帳一起清），全部歸零時守城的帳與警報清掉；guarded 是「拉之前有警報、拉完全部歸零」——要不要照設計 4.5
    分守城功由呼叫端定，這裡不分紅、不記 guards、不寫句子。value 是 side 那一條拉完剩多少。"""
    out = Pushed(value=bar(world, loc_id, side))
    fight = fight_of(world, loc_id)
    if not on(content, world) or fight is None or side not in fight.bars or amount <= 0 or _still(world, content, loc_id):
        return out
    line = fight.bars[side]
    out.moved = min(line.value, amount)
    line.value -= out.moved
    out.value = line.value
    fight.last_push = world.time
    if line.value <= 1e-9:
        del fight.bars[side]
        out.value = 0.0
    if not fight.bars:
        out.guarded = fight.alarm
        fight.guards, fight.alarm = {}, False
    return out


def guard_pull(
    world: WorldState, content: Content, loc_id: str, side: str, amount: float, *, name: str = "", holder_side: str | None = None,
) -> Pushed:
    """約戰守方贏了（減法季批 3b-2，計畫 4.0 之三第 11 條）：把 side（攻方）那一條拉下 amount（pull），拉的量記進這一輪的守城帳（name 是應戰的人；
    守軍迎戰給空字串、不記帳）。拉之前到過警報線、拉完全部歸零（Pushed.guarded）時照翻地設計 4.5 分守城功（_payout 的 "guard"：總額同攻下的一半，
    照這一輪拉了多少分給拉過的人；PM 四之五第 4 件），holder_side 是那一份記在哪一邊（守方那一軍）。句子不寫在這裡（約戰的戰報自己寫），
    守住分紅的那兩句照舊放 lines。"""
    fight = fight_of(world, loc_id)
    guards = dict(fight.guards) if fight is not None else {}
    out = pull(world, content, loc_id, side, amount)
    if out.moved <= 0:
        return out
    if name:
        guards[name] = guards.get(name, 0.0) + out.moved
    fight = fight_of(world, loc_id)
    if fight is not None and fight.bars:
        fight.guards = guards
    elif out.guarded and guards and holder_side is not None:
        place = content.locations[loc_id].name
        _payout(world, content, loc_id, holder_side, "guard", guards)
        out.lines += [GUARDED_LINE.format(place=place), PAYOUT_NEXT]
    return out


def tally(world: WorldState, content: Content, day: int, side: str, name: str, moved: float) -> None:
    """記今天這一邊、這個人推（拉）動了多少（ConquestState.tally；出陣回報的小籤讀 today_moved）。day 是 Game._pill_day（同出陣次數換日），
    換了一天第一次記時整本清掉重記。沒推動（moved 0）不記。"""
    if moved <= 0:
        return
    if world.conquest is None:
        update(world, content)
    book = world.conquest.tally
    if book.day != day:
        book.day, book.sides, book.people = day, {}, {}
    book.sides[side] = book.sides.get(side, 0.0) + moved
    key = name_key(name)
    book.people[key] = book.people.get(key, 0.0) + moved


def today_moved(world: WorldState | None, day: int, side: str | None, name: str | None = None) -> float:
    """今天（day 同 tally）這一邊（給了 name 是這個人）推（拉）動的合計；不是今天的帳是 0。"""
    book = world.conquest.tally if world is not None and world.conquest is not None else None
    if book is None or book.day != day:
        return 0.0
    if name is not None:
        return book.people.get(name_key(name), 0.0)
    return book.sides.get(side, 0.0) if side is not None else 0.0


def decay(world: WorldState, content: Content) -> None:
    """每日回（設計 4.1、第九章第 1 條）：每跨過一個季曆日交界，前一整個季曆日沒人推過的塊，每一條往回 decay_per_day；歸零的那一條拿掉
    （這一輪的帳一起清），全部歸零時守城的帳與警報也清。被戰書凍結的不回；那一天被碎片鎮過的也不回（玉璽碎片改版第 3 批的鎮地：
    「對面的進度不漲、也不回」，seal_acts.held_during）。這一季第一次只記下今天。world.advance_world_state 每一步叫。"""
    state = world.conquest
    if state is None or not on(content, world):
        return
    today = calendar.day_index(world.time, content, world)
    if state.decay_day < 0 or state.decay_day > today:
        state.decay_day = today
        return
    step = content.config.conquest.decay_per_day
    while state.decay_day < today:
        state.decay_day += 1
        ended = calendar.day_start(state.decay_day, content, world)  # 剛過完的那一天（從 0 起算第 decay_day−1 天）的 00:00
        for loc_id, fight in state.fights.items():
            if not fight.bars or frozen(world, loc_id) is not None:
                continue
            if seal_acts.held_during(world, content, loc_id, ended, calendar.day_start(state.decay_day + 1, content, world)):
                continue
            if fight.last_push is not None and fight.last_push >= ended:
                continue
            for side, line in list(fight.bars.items()):
                line.value = max(0.0, line.value - step)
                if line.value <= 1e-9:
                    del fight.bars[side]
            if not fight.bars:
                fight.guards, fight.alarm = {}, False


def letter_problem(world: WorldState | None, content: Content, side: str | None, loc_id: str, key: int) -> str | None:
    """side 對這一塊下戰書不成的原因（階由呼叫端看；key 是 conquest_day.day_key 的今天）；成是 None。進度要到 letter_at、這一塊推得動
    （目標、不冷卻、沒被碎片鎮住）、這一邊這一天還沒下過；別的攻方已經下了、還沒開集結的那一塊可以併進同一場（不算凍結）。"""
    if not on(content, world) or side is None:
        return WHY_OFF
    cfg = content.config.conquest
    if world.conquest.letter_days.get(side) == key:
        return LETTER_USED.format(side=content.scenario.faction_name(side, side), hour=f"{cfg.settle_hour:02d}")
    slot = frozen(world, loc_id)
    if slot is not None:
        if side in slot.attackers:
            return LETTER_JOINED.format(side=content.scenario.faction_name(side, side))
        if slot.status == "open":
            return LETTER_OPEN
    if not capturable(content, loc_id):
        return WHY_OUT
    if cooling(world, content, loc_id):
        return WHY_COOLING.format(n=cooling_minutes(world, content, loc_id))
    hold = _held_why(world, content, loc_id)
    if hold is not None:
        return hold
    problem = _target_problem(world, content, side, loc_id)
    if problem is not None:
        return problem
    value = bar(world, loc_id, side)
    if value < cfg.letter_at:
        return LETTER_LOW.format(at=_int(cfg.letter_at), value=_int(value))
    return None


def focus_blocks(world: WorldState | None, content: Content, side: str | None, how: str) -> list[str]:
    """軍令改讀（PM 2026-10-20 第 1 條、設計 4.5）：每一條戰線（與不算進戰線的那一組）各挑——攻（attack）：side 推得動的目標裡 side 那一條
    最高的那幾塊（並列都算；全是 0 時就是那裡所有推得動的目標）；守（defend）：side 佔著、守得動的塊裡被推得最高（別人最高的那一條）的那幾塊，
    沒人在推就沒有。照內容順序。軍令卡、記功、假人、輿圖標記都問它（列與記同一個判斷，FB-531、FB-565）。
    守另外一律列 side 佔著、被戰書凍結的那幾塊（FB-605，PM 2026-10-21：正等著一場攻城，正是最該守的地方；守不動進度，記功改在那一場攻城站守方、
    守住時記一次——orders._counts 的 SIEGE_GUARD）。"""
    if not on(content, world) or side is None:
        return []
    groups: dict[str | None, list[tuple[str, float]]] = {}
    out: set[str] = set()
    for loc_id in blocks(content):
        if how == "attack":
            if push_problem(world, content, side, loc_id, "attack") is not None:
                continue
            score = bar(world, loc_id, side)
        else:
            if besieged(world, content, side, loc_id):
                out.add(loc_id)
                continue
            if push_problem(world, content, side, loc_id, "hold") is not None:
                continue
            score = max(bars(world, loc_id).values(), default=0.0)
        groups.setdefault(line_of(world, content, loc_id), []).append((loc_id, score))
    for rows in groups.values():
        top = max(score for _, score in rows)
        out |= {loc_id for loc_id, score in rows if score == top}
    return [loc_id for loc_id in blocks(content) if loc_id in out]


def drop_cap(world: WorldState | None, content: Content, loc_id: str | None) -> int | None:
    """打贏這裡的隊伍掉的素材最高幾階：開季中立的區塊在冷卻期只掉一階（設計 4.1：駐軍照打、高階回饋暫停）；其餘 None（照舊）。"""
    if loc_id is None or not on(content, world) or start_kind(world, content, loc_id) != NEUTRAL:
        return None
    return 1 if cooling(world, content, loc_id) else None


def block_view(world: WorldState | None, content: Content, loc_id: str, side: str | None) -> dict:
    """一塊地給畫面的資料（輿圖的卡、天下圖的「正在翻」「激戰」；第 3、4 批畫它）：誰佔著、開季的種類、搶不搶得下、每一條進度、
    冷卻還剩幾分、被哪一場戰書凍結、正在推的人、激戰、每一邊此刻的集火、看的人（side）此刻攻或守推不推得動與原因。時刻由 engine 照
    calendar.stamp_text 補（Game.conquest_view）。"""
    held = holder(world, content, loc_id)
    rows = sorted(bars(world, loc_id).items(), key=lambda kv: (-kv[1], kv[0]))
    since = world.time - _seconds(content, content.config.conquest.focus_minutes) if world is not None else 0.0
    fight = fight_of(world, loc_id)
    recent: dict[str, set[str]] = {}
    for m in (fight.marks if fight is not None else []):
        if m.at >= since:
            recent.setdefault(m.side, set()).add(name_key(m.name))
    cfg = content.config.conquest
    how = "hold" if side is not None and held == side else "attack"
    slot = frozen(world, loc_id)
    return {
        "id": loc_id, "holder": held, "start": start_kind(world, content, loc_id), "capturable": capturable(content, loc_id),
        "bars": [{"side": s, "value": _int(v)} for s, v in rows],
        "cooling": cooling_minutes(world, content, loc_id),
        "frozen": {"slot": slot.id, "attackers": list(slot.attackers), "at": slot.at, "status": slot.status} if slot is not None else None,
        "pushers": [{**row, "moved": _int(row["moved"])} for row in pushers(world, content, loc_id)],
        "clash": clashing(world, content, loc_id),
        "focus": {s: _int(min(cfg.focus_cap, cfg.focus_step * max(0, len(names) - 1)) * 100) for s, names in recent.items()},
        "how": how if side is not None else None,
        "why": push_problem(world, content, side, loc_id, how) if side is not None else None,
    }


def is_home(world: WorldState, content: Content, side: str | None, loc_id: str) -> bool:
    """這一塊算不算 side 的地盤（設計 4.5、4.6；開關開著才有）：有一方的照此刻的控制方；散人（side None）照開季的種類——開季中立的
    區塊不論此刻歸誰都算散人的。不是區塊一律不算。剛易手還在冷卻的不算（加成暫停，輿圖簡化設計 4.1）。"""
    if not on(content, world) or loc_id not in blocks(content) or cooling(world, content, loc_id):
        return False
    if side is None:
        return start_kind(world, content, loc_id) == NEUTRAL
    return holder(world, content, loc_id) == side


def home(state: GameState, content: Content) -> bool:
    """人此刻站在自家領地（吃加成）：開關開著、不在路上、所在是區塊，而且是自己那一邊控制的（豪強分屬兩軍：依附那一軍，rules.side_of），
    散人是開季中立的區塊。只在人站在那裡時才吃（設計 3.4）。"""
    p = state.player
    if p.journey is not None or p.location is None:
        return False
    return is_home(state.world, content, rules.side_of(state, content), p.location)


def _opened(world: WorldState, content: Content, loc_id: str) -> bool:
    """劇情開放了（同 atlas.is_unlocked，但不看人站在哪裡）：不是序章專屬、unlock_flag 立了或第一季直接開放的地點。"""
    loc = content.locations[loc_id]
    if loc.prologue_only:
        return False
    if loc_id in rules.season_one_off(content, world, "unlocks"):
        return True
    return not loc.unlock_flag or loc.unlock_flag in world.flags


def _clamp(x: float) -> int:
    """夾在 0～100、四捨五入（.5 往上：不用 round 的銀行家捨入，免得同一個值兩邊各算一次結果不同）。"""
    return max(0, min(100, math.floor(x + 0.5)))


def _fronts(content: Content) -> list[str]:
    return list(rules.front_ids(content))


def _sides(content: Content, line: str) -> tuple[str | None, str | None]:
    """這條線兩頭是誰（往 0 推的、往 100 推的；territory.sides）。"""
    return territory.sides(content, line)


def weight_of(world: WorldState | None, content: Content, loc_id: str) -> float:
    """一塊的權重（設計 4.7）：開季中立的 neutral_weight、陣營的 faction_weight；大本營與 fixed 不算（0）。"""
    if not capturable(content, loc_id):
        return 0.0
    cfg = content.config.conquest
    return cfg.neutral_weight if start_kind(world, content, loc_id) == NEUTRAL else cfg.faction_weight


def line_weight(content: Content, line: str, world: WorldState | None = None) -> float:
    """基準的分母（Config.conquest.weigh_by）：neutral＝這條線開季中立的權重和（裁決 5）；total＝這條線所有可奪區塊的權重和。"""
    only_neutral = content.config.conquest.weigh_by == "neutral"
    return sum(
        weight_of(world, content, loc) for loc, block in blocks(content).items()
        if block.line == line and (not only_neutral or start_kind(world, content, loc) == NEUTRAL)
    )


def gained(world: WorldState, content: Content, line: str, side: str) -> float:
    """side 在這條線上「佔得」的權重：此刻歸它、開季不是它的區塊（開季兩邊都是 0，基準在 50；計畫 2.2）。"""
    return sum(
        weight_of(world, content, loc) for loc, block in blocks(content).items()
        if block.line == line and holder(world, content, loc) == side and start_kind(world, content, loc) != side
    )


def base(world: WorldState, content: Content, line: str) -> float:
    """佔領的基準（設計 4.7）：50＋share×（往 100 那一方佔得－往 0 那一方佔得）÷分母；分母是 0（這條線沒有可奪的區塊）時是 50。"""
    low, high = _sides(content, line)
    weight = line_weight(content, line, world)
    if not weight or low is None or high is None:
        return 50.0
    share = content.config.conquest.share
    return 50.0 + share * (gained(world, content, line, high) - gained(world, content, line, low)) / weight


def value(world: WorldState, content: Content, line: str) -> int:
    """這條線此刻該是多少：夾過的（基準＋偏移）。"""
    state = world.conquest
    offset = state.offset.get(line, 0.0) if state is not None else 0.0
    return _clamp(base(world, content, line) + offset)


def _start(world: WorldState, content: Content) -> ConquestState:
    """這一季第一次算：抄下每塊開季的種類，偏移從此刻的戰線起算（裁決 5：劇本起點 40／35／55，不是 50）。"""
    state = ConquestState(start={loc: block.kind for loc, block in blocks(content).items()})
    world.conquest = state
    for line in _fronts(content):
        state.base[line] = 50.0
        state.offset[line] = rules.world_trend_value(world, content, line) - 50.0
    return state


def _sync(world: WorldState, content: Content, state: ConquestState) -> None:
    """別處直接改了線（決戰收場、管理者、舊的直接寫法）：值跟「上一次的基準＋偏移」對不上時，照上一次的基準重錨偏移（推進牆的部分丟掉）。"""
    for line in _fronts(content):
        before = state.base.get(line, 50.0)
        now = rules.world_trend_value(world, content, line)
        if now != _clamp(before + state.offset.get(line, 0.0)):
            state.offset[line] = now - before


def reweigh(world: WorldState, content: Content) -> None:
    """照此刻的佔領重算三條線（易手只動基準、偏移不動），寫回 world.trends、重算黃巾聲勢、蓋這一週的地盤快照。"""
    state = world.conquest or _start(world, content)
    _sync(world, content, state)
    for line in _fronts(content):
        state.base[line] = base(world, content, line)
        world.trends[line] = _clamp(state.base[line] + state.offset.get(line, 0.0))
    rules.recompute_trends(world, content)
    if world.territory is not None:
        territory._snapshot(world, content, world.territory)


def update(world: WorldState, content: Content) -> None:
    """territory.update 在開關開著時改叫這裡：這一季第一次算抄下開季的種類與控制方（不發天下大事）；之後不拔河、不割據，
    只把別處直接改了的線重錨、重算。控制方只由 set_control（攻城戰、管理者）與 assign（時刻表指定）改。"""
    t = world.territory
    if world.conquest is None or t is None:
        t = t or TerritoryState()
        t.control = {loc: kind for loc, kind in ((x, b.kind) for x, b in blocks(content).items()) if kind in SIDES}
        t.tug, t.geju, t.pinned, t.forts = {}, [], {}, {}
        world.territory = t
        _start(world, content)
        territory._remember(t)  # 開季的控制方也算佔過：之後拿回來是收復
        reweigh(world, content)
        if calendar.point(world.time, content, world).week == 1:  # 開季那一刻：版圖變化第 1 週的易手跟它比（FB-264）
            t.weeks[territory.START_WEEK] = t.weeks[1].model_copy(deep=True)
        return
    reweigh(world, content)


def _announce(world: WorldState, content: Content, t: TerritoryState, before: dict[str, str]) -> None:
    """換了控制方的區塊各發一句天下大事、記一筆江湖史（同 territory._announce 的句子：落入／收復）；跟它不同的是中立地第一次被佔
    （之前沒有控制方）也發。放回中立（管理者）不發。"""
    for loc_id, side in t.control.items():
        if before.get(loc_id) != side:
            line = territory.RETAKE_LINE if side in t.held.get(loc_id, []) else territory.FLIP_LINE
            text = line.format(place=content.locations[loc_id].name, side=content.scenario.faction_name(side, side))
            world.rumors.append(Rumor(time=world.time, text=text, location=loc_id, layer="world"))
            world.chronicle.append(Rumor(time=world.time, text=text))
            fight = fight_of(world, loc_id)
            if fight is not None:  # 新的主人在自己的地方沒有攻的那一條（管理者、時刻表指定易手時；推滿與攻城戰在 flip 整本清掉）
                fight.bars.pop(side, None)
            seal_acts.hold_lapse(world, loc_id, side)  # 替原主鎮著的鎮地（玉璽碎片改版第 3 批）當場結束
    territory._remember(t)


def set_control(world: WorldState, content: Content, loc_id: str, side: str | None) -> bool:
    """把一塊改成 side 的（None＝放回中立，只給管理者用）；不是搶得下來的區塊、或 side 不是劇本的陣營不收（回 False；翻地對 N 方成立，
    輿圖簡化設計第九章第 12 條——管理者那一顆另外只收兩軍）。易手照舊發天下大事、記江湖史（territory._announce：落入／收復），重算三條線。"""
    if not capturable(content, loc_id) or (side is not None and content.scenario.find_faction(side) is None):
        return False
    if world.conquest is None or world.territory is None:
        update(world, content)
    t = world.territory
    before = dict(t.control)
    if side is None:
        t.control.pop(loc_id, None)
        seal_acts.hold_lapse(world, loc_id, None)  # 放回中立（管理者）：_announce 不發，鎮地照樣結束
    else:
        t.control[loc_id] = side
    _announce(world, content, t, before)
    reweigh(world, content)
    return True


def assign(world: WorldState, content: Content, given: dict[str, str]) -> None:
    """時刻表結果指定的易手（TimetableOutcome.control）：指定了就是指定了（不記 pinned、不回到規則）；大本營不收，fixed 照收。"""
    if world.conquest is None or world.territory is None:
        update(world, content)
    t = world.territory
    fixed = content.scenario.territory.fixed
    before = dict(t.control)
    for loc_id, side in given.items():
        if side in SIDES and (capturable(content, loc_id) or loc_id in fixed):
            t.control[loc_id] = side
    _announce(world, content, t, before)
    reweigh(world, content)


def apply_push(world: WorldState, content: Content, line: str, delta: int) -> int:
    """其他來源推一條戰線（rules.change_trend 在開關開著時叫）：推的是偏移（設計 4.7「其他來源」），夾值只在顯示那一刻做（FB-530）。
    推過牆的那一截丟掉（同以前）：往 100 推時未夾的（基準＋偏移）最多 max(原本的, 100)，往 0 推時最少 min(原本的, 0)——基準已經在牆外時
    往牆那一邊推整個丟掉、偏移不動，往回推照實記進偏移。回實際推動量（顯示的值前後差）。寫回 world.trends，之後的 recompute_trends、
    territory.update 照舊由呼叫端做。"""
    state = world.conquest
    if state is None or world.territory is None:
        update(world, content)
        state = world.conquest
    _sync(world, content, state)  # 別處直接寫過線、還沒重算：先照上一次的基準重錨
    now = rules.world_trend_value(world, content, line)
    floor = state.base.get(line, base(world, content, line))
    raw = floor + state.offset.get(line, 0.0)
    pushed = raw + delta
    if delta > 0 and pushed > 100:
        pushed = max(raw, 100.0)
    elif delta < 0 and pushed < 0:
        pushed = min(raw, 0.0)
    state.offset[line] = pushed - floor
    after = _clamp(pushed)
    world.trends[line] = after
    return after - now


def targets(world: WorldState, content: Content, side: str) -> list[str]:
    """side 此刻能挑成目標的區塊（設計 3.2；_target_problem）：搶得下來、此刻不是 side 的、跟 side 此刻控制的某一塊直通、劇情開放了、
    那裡出陣攻打找得到對手（PM 2026-10-20 第 3 條：找不到對手的推不了、不列進軍令與戰書的目標）；照內容順序。冷卻、凍結不看（推不推得動
    另外問 push_problem）。"""
    return [loc for loc in blocks(content) if _target_problem(world, content, side, loc) is None]


def progress_shift(world: WorldState, content: Content, loc_id: str, attackers: list[str]) -> int:
    """攻城戰的起點照進度偏幾點（設計 4.4）：只有一個攻方時，他那一條離 50 每 10 點偏 start_shift_per_10、夾 ±start_shift_cap，往他那一邊
    （往黃巾為正：戰局照決戰以官軍為正向，siege.start_trend 拿 50 減它）；兩軍同時攻（三方混戰）不偏。"""
    if len(attackers) != 1:
        return 0
    cfg = content.config.conquest
    side = attackers[0]
    shift = int((bar(world, loc_id, side) - 50) / 10 * cfg.start_shift_per_10)
    return max(-cfg.start_shift_cap, min(cfg.start_shift_cap, shift)) * direction(content, side, loc_id)


# ── 時刻表決戰的起點照哪一條戰線（企劃者 2026-10-22 選計畫 2026-10-22-長社火攻主場 第七節第 4 條：不另加主場偏移、補一句說明）──
# 起點本來就照戰線的戰況算（battle_instance.start_from_front），領地爭奪開著時戰況又照佔領算（reweigh）；天下大事寫偏幾點與那條線上的地盤，
# 決戰畫面只寫一行偏幾點。數字是開集結那一刻的快照（BattleInstance.front_note），不事後重算。陣營名、線名照劇本讀。待 joy 潤
# FB-686（PM 2026-10-22）：起點照的是整條線的戰況（開季的態勢＋之後的易手與推動），不是數地盤——偏幾點與地盤分成兩句、不用因果連起來
# （冀州開季官軍佔 5 處、黃巾軍佔 2 處，起點卻往黃巾軍偏：開季的態勢本來就偏黃巾）
FRONT_RUMOR = "{battle}開集結：戰局起點照{line}此刻的戰況{lean}（戰況從開季的態勢算起，之後的易手與各路推動都算在裡面）。{line}一帶的地盤此刻{held}。"  # 天下大事
FRONT_LEAN = "往{side}偏了 {n} 點"
FRONT_EVEN = "不偏不倚"
FRONT_HELD = "{side}佔 {n} 處"
FRONT_OPEN = "{n} 處還沒人佔"
# FB-685（PM 2026-10-22）：決戰畫面只留一行短句、數字不在句尾（375／360／320 都本來就一行：最長「起點偏黃巾軍 12 點：潁川汝南戰況」
# 約 15.6 個字寬，320 寬那一段放得下 16.6 個）；佔幾處的明細只寫在天下大事那一則
FRONT_SCENE = "起點{lean}：{line}戰況"  # 決戰畫面，標題底下
FRONT_SCENE_LEAN = "偏{side} {n} 點"
FRONT_SCENE_EVEN = "不偏"


def line_holdings(world: WorldState | None, content: Content, line: str) -> tuple[dict[str, int], int]:
    """這條戰線上的區塊此刻各歸誰：（陣營 id → 幾處，還沒人佔的幾處）。大本營與 fixed（廣宗）也算，跟輿圖上看到的一樣
    （不算的話開季的冀州寫成「黃巾軍佔 0 處」，張角明明在廣宗）；它們不會易手，只是每一季都一樣多。"""
    held: dict[str, int] = {}
    unheld = 0
    for loc_id, block in blocks(content).items():
        if block.line != line:
            continue
        side = holder(world, content, loc_id)
        if side is None:
            unheld += 1
        else:
            held[side] = held.get(side, 0) + 1
    return held, unheld


def front_note(world: WorldState | None, content: Content, definition: BattleDef, start: int) -> FrontNote | None:
    """時刻表決戰開集結那一刻的快照（world._open_claimed 記進 BattleInstance.front_note）：只在領地爭奪開著的季、寫了戰線的決戰
    （攻城範本不算）；其餘是 None，什麼都不寫。start 是照戰況換算的起點（屯糧、天命之爭偏之前）。交戰兩軍照決戰的順序一定列（0 也列），
    別的陣營佔著才列（照劇本的順序）。"""
    if definition.front is None or definition.siege or not on(content, world):
        return None
    held, unheld = line_holdings(world, content, definition.front)
    sides = [f.id for f in definition.factions]
    order = sides + [f.id for f in content.scenario.factions if f.id not in sides and held.get(f.id)]
    return FrontNote(line=definition.front, start=start, held={side: held.get(side, 0) for side in order}, open=unheld)


def _front_lean(definition: BattleDef, note: FrontNote, lean: str, even: str) -> str:
    """起點往哪一軍偏幾點（戰局以 factions[0] 為正向，同 start_from_front）；剛好在中線寫 even。"""
    shift = note.start - CENTER
    if shift == 0 or len(definition.factions) < 2:
        return even
    return lean.format(side=(definition.factions[0] if shift > 0 else definition.factions[1]).name, n=abs(shift))


def _line_name(content: Content, note: FrontNote) -> str:
    return next((t.name for t in content.scenario.trends if t.id == note.line), note.line)


def front_rumor(content: Content, definition: BattleDef, note: FrontNote) -> str:
    """開集結那一則天下大事（照快照）：先寫起點照戰況偏幾點，另一句寫那條線上的地盤（FB-686：兩件分開說）。"""
    names = {f.id: f.name for f in content.scenario.factions} | {f.id: f.name for f in definition.factions}
    parts = [FRONT_HELD.format(side=names.get(side, side), n=n) for side, n in note.held.items()]
    if note.open:
        parts.append(FRONT_OPEN.format(n=note.open))
    return FRONT_RUMOR.format(battle=definition.name, line=_line_name(content, note), held="、".join(parts),
                              lean=_front_lean(definition, note, FRONT_LEAN, FRONT_EVEN))


def front_scene(content: Content, definition: BattleDef, note: FrontNote | None) -> str:
    """決戰畫面標題底下那一行（照開集結那一刻的快照，不重算；FB-685：只寫偏幾點，一行）；沒有快照（舊資料、領地爭奪關著、沒寫戰線）
    是空字串。"""
    if note is None:
        return ""
    return FRONT_SCENE.format(lean=_front_lean(definition, note, FRONT_SCENE_LEAN, FRONT_SCENE_EVEN), line=_line_name(content, note))
