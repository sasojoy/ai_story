"""地盤易手（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第四節）。

戰線地點（line_of：地點的 train_trend 寫了戰線；寫 front 的照所在大區的戰線，洛陽兩處的大區沒有戰線就不算）有一個控制方：
- 大本營（劇本陣營的 join_at，含不在戰線上的投靠點）永遠歸那一方；
- Scenario.territory.fixed（廣宗）開季照寫，只照大事易手；
- Scenario.territory.lines 裡的可易手地點照拔河（戰線的值對各地點的門檻，±band 不動）、豪強割據（≥geju_one 每條線一處、
  ≥geju_two 兩處、<geju_release 交還）與大事指定（assign：留到規則算出來的控制方改變那一刻）。
存在 WorldState.territory（整份 JSON，資料庫結構不動）；None＝這一季還沒算過：第一次算不發天下大事（設計第六節）。
拔河看的線照 rules.resolve_trend：第一季是那條戰線，規則關著的季是黃巾聲勢（三條線上的地點一起動，那種季沒有割據）。
只讀寫 WorldState；天下大事與江湖史直接記進 world.rumors／world.chronicle（rules.add_rumor 要 GameState）。
開關（Config.territory.enabled）關著或劇本沒寫 territory：controller 回 None，squads_at 照 Location.enemies。
rules → territory 只在 rules.change_trend 裡延後 import；這裡 import rules 整個模組、呼叫時才取屬性。"""
from __future__ import annotations

from . import rules
from .models import FRONT_KEY, Content
from .state import Rumor, TerritoryState, WorldState

FLIP_LINE = "{place}落入{side}之手。"  # 待 joy 潤：易手那一刻的天下大事與江湖史（設計 4.3 第 2 點）
RETAKE_LINE = "{side}收復{place}。"  # 待 joy 潤（FB-252）：這一季佔過那裡的一方再拿回來（TerritoryState.held）
CONTROL_LINE = "此刻由{side}控制"  # 待 joy 潤：輿圖詳情欄局勢那一行


def on(content: Content) -> bool:
    return content.config.territory.enabled and bool(content.scenario.factions) and content.scenario.territory is not None


def line_of(content: Content, loc_id: str) -> str | None:
    """這個地點是哪一條戰線上的戰線地點（只看內容，不看季）；不是戰線地點是 None。出陣只在這種地點（sortie.mode）。"""
    loc = content.locations.get(loc_id)
    if loc is None:
        return None
    fronts = set(rules.front_ids(content))
    for key in loc.train_trend:
        line = rules.front_of(content, loc_id) if key == FRONT_KEY else key
        if line in fronts:
            return line
    return None


def bases(content: Content) -> dict[str, str]:
    """大本營：劇本陣營的投靠點 → 那個陣營（設計 4.1）。"""
    return {loc_id: f.id for f in content.scenario.factions for loc_id in f.join_at}


def sides(content: Content, line: str) -> tuple[str | None, str | None]:
    """這條戰線兩頭是誰：（目標往 0 推的陣營, 目標往 100 推的陣營）；照劇本陣營的 goals（內容寫的戰線 id，不換鍵）。"""
    low = next((f.id for f in content.scenario.factions if f.goals.get(line, 0) < 0), None)
    high = next((f.id for f in content.scenario.factions if f.goals.get(line, 0) > 0), None)
    return low, high


def geju_side(content: Content) -> str | None:
    """割據佔地的那一方：目標推豪強割據的陣營。"""
    return next((f.id for f in content.scenario.factions if f.goals.get(rules.GEJU, 0) > 0), None)


def threshold(j: int, k: int) -> float:
    """從低的那一頭數第 j 個（1 起算）、共 k 個可易手地點的門檻：75 − 50 ×（j − 0.5）÷ k（設計 4.2）。"""
    return 75 - 50 * (j - 0.5) / k


def line_value(world: WorldState, content: Content, line: str) -> int:
    """拔河看的值：這條戰線照這一季的規則換成真的會動的線（第一季是它自己；規則關著的季是黃巾聲勢）。"""
    return rules.world_trend_value(world, content, rules.resolve_trend(content, world, line) or line)


def _tug(prev: str | None, value: float, t: float, low: str, high: str, band: int) -> str:
    if value >= t + band:
        return high
    if value <= t - band:
        return low
    if prev in (low, high):
        return prev
    return high if value >= t else low  # 第一次算、剛好在緩衝裡：照門檻


def _recompute(world: WorldState, content: Content, t: TerritoryState) -> dict[str, str]:
    """可易手地點照規則此刻歸誰（拔河、割據），順便更新 t.tug 與 t.geju；回傳 {地點: 控制方}。"""
    cfg = content.config.territory
    haoqiang = geju_side(content)
    geju = rules.world_trend_value(world, content, rules.GEJU) if rules.trend_shown(content, world, rules.GEJU) else None
    held = list(t.geju)
    result: dict[str, str] = {}
    for line, spots in content.scenario.territory.lines.items():
        low, high = sides(content, line)
        if low is None or high is None or not spots:
            continue
        value = line_value(world, content, line)
        k = len(spots)
        for j, loc_id in enumerate(spots, start=1):
            t.tug[loc_id] = _tug(t.tug.get(loc_id), value, threshold(j, k), low, high, cfg.band)
        if haoqiang is None or geju is None or geju < cfg.geju_release:
            held = [loc_id for loc_id in held if loc_id not in spots]
        else:
            mine = [loc_id for loc_id in held if loc_id in spots]
            want = 2 if geju >= cfg.geju_two else 1 if geju >= cfg.geju_one else 0
            free = sorted(
                (loc_id for loc_id in spots if loc_id not in mine),
                key=lambda loc_id: (abs(threshold(spots.index(loc_id) + 1, k) - value), spots.index(loc_id)),
            )
            held += free[: max(0, want - len(mine))]
        for loc_id in spots:
            result[loc_id] = haoqiang if haoqiang is not None and loc_id in held else t.tug[loc_id]
    t.geju = held
    return result


def _control_now(world: WorldState, content: Content, t: TerritoryState) -> dict[str, str]:
    control = dict(bases(content))
    for loc_id, side in content.scenario.territory.fixed.items():
        control[loc_id] = t.control.get(loc_id, side)
    for loc_id, side in _recompute(world, content, t).items():
        if t.pinned.get(loc_id) == side and loc_id in t.control:
            control[loc_id] = t.control[loc_id]  # 大事指定的留著：規則算出來的還跟指定那一刻一樣
        else:
            t.pinned.pop(loc_id, None)
            control[loc_id] = side
    return control


def _announce(world: WorldState, content: Content, t: TerritoryState, before: dict[str, str]) -> None:
    """換了控制方的地點各發一句天下大事、記一筆江湖史：這一季佔過那裡的一方再拿回來寫「收復」（RETAKE_LINE，FB-252），
    否則「落入…之手」（FLIP_LINE）。發完把此刻的控制方記進 t.held。"""
    for loc_id, side in t.control.items():
        if before.get(loc_id) not in (None, side):
            line = RETAKE_LINE if side in t.held.get(loc_id, []) else FLIP_LINE
            text = line.format(place=content.locations[loc_id].name, side=content.scenario.faction_name(side, side))
            world.rumors.append(Rumor(time=world.time, text=text, location=loc_id, layer="world"))
            world.chronicle.append(Rumor(time=world.time, text=text))
    _remember(t)


def _remember(t: TerritoryState) -> None:
    for loc_id, side in t.control.items():
        sides = t.held.setdefault(loc_id, [])
        if side not in sides:
            sides.append(side)


def update(world: WorldState, content: Content) -> None:
    """重算一次（設計 4.2 最後一段）：rules.change_trend 真的動了一條線、決戰結果直接寫進季（Game._apply_outcome_trends_and_flags）、
    推進世界（world.advance_world_state）時叫。這一季第一次算（world.territory 是 None）不發天下大事；之後控制方換了的地點各發
    一句天下大事、記一筆江湖史。開關關著什麼都不做。"""
    if not on(content):
        return
    first = world.territory is None
    t = world.territory or TerritoryState()
    before = dict(t.control)
    t.control = _control_now(world, content, t)
    world.territory = t
    if first:
        _remember(t)  # 開季（第一次算）的控制方也算佔過：之後拿回來是收復
    else:
        _announce(world, content, t, before)


def assign(world: WorldState, content: Content, given: dict[str, str]) -> None:
    """大事指定易手（TimetableOutcome.control，設計 4.2 第 3 點）：先照規則算一次，再把指定的地點換成指定的那一方。可易手的地點記下
    「這一刻規則算出來的控制方」（pinned），之後規則算出來的改變那一刻才回到規則；固定的地點（廣宗）換了就是換了。大本營不收
    （載入時也擋）。換了的地點照樣發天下大事。"""
    if not on(content) or not given:
        return
    update(world, content)
    t = world.territory
    base, fixed, haoqiang = bases(content), content.scenario.territory.fixed, geju_side(content)
    before = dict(t.control)
    for loc_id, side in given.items():
        if loc_id in base or loc_id not in t.control:
            continue
        if loc_id not in fixed:
            t.pinned[loc_id] = haoqiang if haoqiang is not None and loc_id in t.geju else t.tug[loc_id]
        t.control[loc_id] = side
    _announce(world, content, t, before)


def controller(world: WorldState, content: Content, loc_id: str) -> str | None:
    """這個地點此刻歸誰；不是戰線地點也不是大本營、或開關關著是 None。這一季還沒算過時照規則現算（不存，Review Focus 4）。"""
    if not on(content):
        return None
    t = world.territory
    if t is not None and loc_id in t.control:
        return t.control[loc_id]
    if loc_id in bases(content):
        return bases(content)[loc_id]
    if line_of(content, loc_id) is None and loc_id not in content.scenario.territory.fixed:
        return None
    return _control_now(world, content, (t or TerritoryState()).model_copy(deep=True)).get(loc_id)


def squads_at(world: WorldState, content: Content, loc_id: str) -> list[str]:
    """這個地點此刻站的隊伍（設計 4.3 第 1 點）：寫了 garrison 的地點是無陣營的那幾路（Location.enemies 裡的，誰控制都在）加上
    控制方那一組；其餘（開關關著、大本營沒寫 garrison）照 Location.enemies。遊歷、出陣、探索、懸賞、攻城、輿圖都讀它。"""
    loc = content.locations[loc_id]
    side = controller(world, content, loc_id)
    garrison = content.scenario.territory.garrison.get(loc_id) if side is not None else None
    if not garrison:
        return list(loc.enemies)
    neutral = [sid for sid in loc.enemies if sid in content.squads and content.squads[sid].faction is None]
    return neutral + [sid for sid in garrison.get(side, []) if sid not in neutral]


def price_factor(world: WorldState, content: Content, faction: str | None, loc_id: str) -> float:
    """地盤福利（設計 4.3 第 3 點）：在自己陣營控制的地方 own_price、別的陣營控制的地方 enemy_price；散人、沒有控制方是 1。"""
    side = controller(world, content, loc_id)
    if side is None or faction is None:
        return 1.0
    cfg = content.config.territory
    return cfg.own_price if side == faction else cfg.enemy_price
