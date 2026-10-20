"""領地爭奪（第 38 項改版；設計 docs/superpowers/specs/2026-10-20-領地爭奪-design.md，計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md）。

第一季的地圖分成三種區塊（Scenario.territory.blocks，一塊＝一個地點）：中立（高階獎勵，兩軍爭奪）、官軍與黃巾各自的陣營領地。
- 開季蓋章（WorldState.conquest_on，world_state.stamp_season）；判斷開沒開一律走 on(content, world)，不要只看設定。
- 開著時控制方只照佔領（攻城戰的結果、時刻表指定、管理者改），不拔河、不割據；此刻的控制方照舊記在 TerritoryState.control
  （所以讀控制方的地方都不用改），開季中立而沒人佔的區塊不在裡面（controller 回 None）。
- 三條戰線的值＝佔領的基準＋其他來源累積的偏移，夾在 0～100（設計 4.7）；值照舊存在 world.trends[戰線]，讀線的地方都不用改。
  rules.change_trend 推的是偏移（apply_push，夾值只在顯示那一刻做，FB-530）；決戰收場、管理者這類直接改了線的，下一次 reweigh
  照上一次的基準重錨偏移。
- 出陣不推線、推攻城目標的進度（ConquestState.progress；第二批起只有今天公告、還沒開打的目標推得動，progress_open）。
- 第二批：每天投票、22:00 結算排時程表在 conquest_day.py，攻城戰在 siege.py。
只讀寫 WorldState；天下大事與江湖史照 territory._announce。territory 反過來在函式裡延後 import 這裡。"""
from __future__ import annotations

import math

from . import calendar, rules, territory
from .models import BlockDef, Content
from .state import ConquestState, GameState, Rumor, TerritoryState, WorldState

SIDES = ("guan", "huang")  # 交戰兩軍（設計 4.1：豪強不佔地）；戰線往 100 是黃巾、往 0 是官軍（劇本的 goals）
NEUTRAL = "neutral"
NEUTRAL_LINE = "中立地・高階獵場，還沒有人佔"  # 待 joy 潤：輿圖詳情欄局勢那一行（還沒人佔的中立地）
NEUTRAL_HELD = "（開季是中立地）"  # 待 joy 潤：被佔下的中立地，接在「此刻由某某控制」後面


def eligible(content: Content) -> bool:
    """這份內容與設定開得了領地爭奪（不看季）：劇本有官軍與黃巾、寫了區塊；劇本有要依附的陣營（豪強）時豪強分屬兩軍也開著（設計 4.1、4.10）。"""
    scen = content.scenario
    ids = {f.id for f in scen.factions}
    if not set(SIDES) <= ids or scen.territory is None or not scen.territory.blocks:
        return False
    if any(f.allies for f in scen.factions) and not content.config.haoqiang_allied:
        return False
    return True


def on(content: Content, world: WorldState | None) -> bool:
    """這一季照領地爭奪的規則：主機的開關開著、這一季開季時蓋了章、地盤本身開著（territory.on）。world 是 None 一律是假。"""
    return bool(world is not None and content.config.conquest.enabled and world.conquest_on and territory.on(content))


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

# ── 攻城目標的進度（設計 3.7、4.4；計畫 2.3）：0～100，往黃巾為正（戰線的方向），沒寫是 50 ──
# 玩家看到的一句話（同戰況變化不露數字的規矩）：照推完之後、從推的那一方看的局面挑一句。待 joy 潤
PROGRESS_LINES = (
    (30, "{place}一帶，我軍已佔盡上風。"),
    (1, "{place}一帶，我軍漸佔上風。"),
    (0, "{place}一帶，兩軍相持不下。"),
    (-100, "{place}一帶敵勢仍盛，我軍扳回了幾分。"),
)


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


def progress_open(world: WorldState, content: Content, loc_id: str) -> bool:
    """這一塊的進度推得動（計畫 2.3）：第二批起只有今天公告、還沒開打（時程表上 planned、waiting）的目標；打完或作罷歸 50
    （conquest_day.void、siege 收場）。搶不下來的區塊（大本營、廣宗）一律推不動。"""
    if not on(content, world) or not capturable(content, loc_id) or world.conquest is None:
        return False
    return any(slot.loc == loc_id and slot.status in ("planned", "waiting") for slot in world.conquest.schedule)


def siege_state(world: WorldState | None, loc_id: str) -> str | None:
    """這一塊今天的攻城在哪一步（FB-552：出陣那一行照實寫，不再一律寫「今天沒有公告攻城」）：今天沒排過是 None；
    planned＝公告了、還沒開打（planned、waiting：進度推得動，progress_open）；muster＝開了集結、還沒到開打的時刻；fight＝開打了、還在打；
    done＝打完了；void＝作罷了。這一塊排了不只一場時取最後排的那一場（時程表照先後）。只讀 WorldState，不判進度推不推得動。"""
    if world is None or world.conquest is None:
        return None
    slots = [slot for slot in world.conquest.schedule if slot.loc == loc_id]
    if not slots:
        return None
    slot = slots[-1]
    if slot.status in ("planned", "waiting"):
        return "planned"
    if slot.status == "open":
        return "muster" if world.time < slot.at else "fight"
    return slot.status


def progress_of(world: WorldState, loc_id: str) -> float:
    state = world.conquest
    return state.progress.get(loc_id, 50.0) if state is not None else 50.0


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


def push_progress(world: WorldState, content: Content, side: str, loc_id: str, amount: float) -> float:
    """side 把這一塊的進度往自己那一邊推 amount（夾 0～100），回新值。推不動（不是進度開著的區塊、side 不是兩頭之一）照原值回。"""
    before = progress_of(world, loc_id)
    sign = direction(content, side, loc_id)
    if not sign or not progress_open(world, content, loc_id) or world.conquest is None:
        return before
    after = max(0.0, min(100.0, before + sign * amount))
    world.conquest.progress[loc_id] = after
    return after


def progress_shift(world: WorldState, content: Content, loc_id: str) -> int:
    """攻城戰的起點照進度偏幾點（設計 4.4，第二批才用）：每偏 50 十點偏 start_shift_per_10，夾 ±start_shift_cap；往黃巾為正。"""
    cfg = content.config.conquest
    shift = int((progress_of(world, loc_id) - 50) / 10 * cfg.start_shift_per_10)
    return max(-cfg.start_shift_cap, min(cfg.start_shift_cap, shift))


def progress_line(content: Content, loc_id: str, value_after: float, side: str) -> str:
    """推完之後那一句（不寫數字）：從推的那一方看，進度站在自己那一邊多少挑 PROGRESS_LINES。"""
    mine = (value_after - 50) * direction(content, side, loc_id)
    text = next(line for floor, line in PROGRESS_LINES if mine >= floor)
    return text.format(place=content.locations[loc_id].name)


def is_home(world: WorldState, content: Content, side: str | None, loc_id: str) -> bool:
    """這一塊算不算 side 的地盤（設計 4.5、4.6；開關開著才有）：有一方的照此刻的控制方；散人（side None）照開季的種類——開季中立的
    區塊不論此刻歸誰都算散人的。不是區塊一律不算。"""
    if not on(content, world) or loc_id not in blocks(content):
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
    territory._remember(t)


def set_control(world: WorldState, content: Content, loc_id: str, side: str | None) -> bool:
    """把一塊改成 side 的（None＝放回中立，只給管理者用）；不是搶得下來的區塊、或 side 不是兩軍之一不收（回 False）。
    易手照舊發天下大事、記江湖史（territory._announce：落入／收復），重算三條線。"""
    if not capturable(content, loc_id) or (side is not None and side not in SIDES):
        return False
    if world.conquest is None or world.territory is None:
        update(world, content)
    t = world.territory
    before = dict(t.control)
    if side is None:
        t.control.pop(loc_id, None)
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
    """side 此刻能挑成目標的區塊（設計 3.2）：搶得下來、此刻不是 side 的、跟 side 此刻控制的某一塊直通、劇情開放了；照內容順序。"""
    mine = {loc for loc in blocks(content) if holder(world, content, loc) == side}
    return [
        loc for loc in blocks(content)
        if capturable(content, loc) and holder(world, content, loc) != side and _opened(world, content, loc)
        and any(x in mine for x in adjacent(content, loc))
    ]
