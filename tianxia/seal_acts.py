"""玉璽碎片改版的璽效查詢（共用規則層；全部拆包第 51 批「玉璽三」把 `seal_acts` 拆兩半，計畫 docs/superpowers/plans/2026-11-06-玉璽包-第3批.md）。
目標、灰掉的原因、碎片卡、字句、次數與時間、起用那一下（`pull`）、`clash`／`clash_plan` 搬進玉璽包 `tianxia/features/seal/acts.py`
（舊名不留別名：這一層不能 import 包）；這裡留別的模組讀的 16 個璽效查詢與它們自己要的小東西。

玉璽碎片改版第 2 批：獨門行動——引將（玄紐）、頒詔（雲篆）、承露（承露）、傳檄（赤璋）、收心（歸心）
（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第三、四、五、五之一章；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-2.md）；
第 3 批：鎮地（螭首）、補缺（金角），建在翻地與爭搶（conquest.py）上（計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-3.md）。

- 生效中的行動記在季上（WorldState.seal_acts；SealAct 不記是誰）。掛點讀這裡的查詢：pinned（引將釘住的大勢人物；人物活起來不搬他）、
  edict_sense／edict_cultivate（頒詔：sensing.rate、cultivation.peak_scale）、dew_factor／dew_clinic（承露：Game._advance_player_local、
  team 的療傷）、writ_factor（傳檄：Game.push_trend、Game._push_progress）、heart_open／heart_scale（收心：rules.can_meet、
  companion_agent._apply_turn、feasts.toast）。改版關著一律中性值（季上那一本本來就是空的，查詢再擋一次）。
- 引將期滿回原處（tick：world.advance_world_state 每一步、人物活起來走動之前叫；期滿那一刻另外切一段，next_end）、被時刻表或退場搬動時
  先回原處再提早結束（release：figures._change、_hand_over、plans._move 叫）。
- 鎮地：生效中的那一塊誰都推不動（held：conquest.push_problem、letter_problem 問；held_during：conquest.decay 問，那一天鎮過就不回），
  那一塊換了主人當場結束（hold_lapse：conquest._announce、set_control 叫）。
- 只 import models、state、calendar、treasures；atlas、figures、rules 在函式裡延後 import。不擲骰、不讀時鐘。字待 joy 潤。
- 改這一份 scripts/test_for.py 挑得比以前少（全部拆包第 50 批量的）：atlas 拆兩半之後 import 的模組少於 AGGREGATOR_FANOUT（15），不再算彙整的
  模組，往上找會穿過它，依賴這一份的模組從 12 個變成 17 個、import 它們的測試檔 141 個，超過 IMPORT_CAP（120），只挑直接 import 它的測試檔
  ＋核心測試＋煙霧；以前經 atlas、chiefs、conquest、figure_life、figures、howto、orders、plans 挑到的另外 110 個留給每日整套。
  第 51 批登記進 registry.SHARED 之後照「共用層照上面那一條挑」走。
  另外跑（-n 4）：tests/seal/ 整個資料夾、玉璽包的 tianxia/features/seal/tests/ 整個資料夾、tests/figures/test_plans.py、tests/acts/ 的
  test_conquest_flip、test_conquest_rules、test_conquest_siege，要當場全驗用 --all。"""
from __future__ import annotations

import math

from . import calendar, treasures
from .models import Content
from .state import GameState, SealAct, WorldState

EPS = calendar.EPS_SECONDS
BACK = "{figure}坐鎮期滿，回到了{place}。"  # 引將期滿（天下大事；人物移動本來就寫天下大事）
def on(content: Content) -> bool:
    """改版開著（同 seal.revamp_on；seal 反過來叫這裡，所以照 treasures 那一條讀）。"""
    return treasures.revamp_on(content)


def tuning(content: Content):
    return content.config.seal.revamp.acts

# ── 生效中的 ───────────────────────────────────────────────

def ends(act: SealAct) -> float:
    return act.ended if act.ended is not None else act.until


def active(act: SealAct, t: float) -> bool:
    """生效的區間 [開始, 期滿或提前結束)。"""
    return act.start <= t + EPS and t < ends(act) - EPS


def live(world: WorldState, kind: str | None = None, t: float | None = None) -> list[SealAct]:
    t = world.time if t is None else t
    return [a for a in world.seal_acts if (kind is None or a.kind == kind) and active(a, t)]


def pinned(world: WorldState | None, fid: str) -> SealAct | None:
    """引將：此刻把 fid 釘住的那一筆（還沒期滿回原處、也還沒提前結束）；沒有是 None。人物活起來的走動、跟隨、趕往都問它。"""
    if world is None:
        return None
    return next((a for a in world.seal_acts if a.kind == "yinjiang" and a.target == fid and a.ended is None), None)


def edict_sense(world: WorldState, content: Content) -> int:
    """頒詔：靜心感悟擲中的機會多幾個百分點（sensing.rate 夾在上限之內）；沒有是 0。"""
    if not on(content):
        return 0
    return tuning(content).sense_points * len(live(world, "banzhao"))


def edict_cultivate(world: WorldState, content: Content) -> float:
    """頒詔的第二半：衝絕學的機會倍數（企劃者 2026-10-21：武學重構之後修練不再擲升品，後半句從「修練升品 ×1.2」改成
    「衝絕學的機會 ×1.2」）。只有 cultivation.peak_scale 叫這一處（跟寶物「cultivate」同一個倍數位置；契機 seize 與服丹 force_odds
    都經過它，在上限之內）；沒有是 1。Config.seal.revamp.acts.cultivate 設 1 等於拿掉這一半。"""
    factor = 1.0
    if on(content):
        for _ in live(world, "banzhao"):
            factor *= tuning(content).cultivate
    return factor


def region_of(content: Content, loc_id: str | None) -> str | None:
    """地點所在的大區 id（atlas.region_of）；不是地點、地圖沒有大區是 None。"""
    from . import atlas  # noqa: PLC0415  atlas → world → rules → …：延後 import

    if not loc_id or loc_id not in content.locations:
        return None
    region = atlas.region_of(content, loc_id)
    return region.id if region is not None else None

def dew_factor(state: GameState, content: Content, seconds: float) -> float:
    """承露的體力（PM 五之一 4）：這一段回復（世界秒 [此刻 − seconds, 此刻]）跟所在大區的承露重疊幾秒，那幾秒多乘（stamina − 1）；
    在路上照身後那一站的大區。沒有承露、改版關著是 1。"""
    w = state.world
    if seconds <= 0 or not w.seal_acts or not on(content):
        return 1.0
    region = region_of(content, state.player.location)
    begin, end = w.time - seconds, w.time
    overlap = sum(
        max(0.0, min(end, ends(a)) - max(begin, a.start)) for a in w.seal_acts if a.kind == "chenglu" and a.target == region
    )
    return 1.0 + (tuning(content).stamina - 1.0) * min(seconds, overlap) / seconds


def dew_clinic(state: GameState, content: Content) -> bool:
    """承露：人在承露那一區、此刻不在路上（醫館療傷不收錢）。"""
    if not state.world.seal_acts or not on(content) or state.player.journey is not None:
        return False
    region = region_of(content, state.player.location)
    return region is not None and any(a.target == region for a in live(state.world, "chenglu"))


def goal(content: Content, world: WorldState, side: str | None, line: str) -> int:
    """side 那一軍在 line 上的目標（往 100 是 +1、往 0 是 −1；規則關著的季三條戰線合成黃巾聲勢，照 rules.resolve_goals）；沒有是 0。"""
    from .rules import resolve_goals  # noqa: PLC0415

    faction = content.scenario.find_faction(side) if side else None
    return resolve_goals(content, world, faction.goals).get(line, 0) if faction is not None else 0


def writ_factor(world: WorldState, content: Content, line: str | None, side: str | None, direction: float | None = None) -> float:
    """傳檄：side 那一軍的人在 line 上往 direction（正：往 100；None＝往那一軍的目標，區塊進度用）推，此刻有照那一軍算、指定這條線的
    傳檄，而且方向是那一軍的目標，就乘 push（好幾筆相乘，PM 五之一 7）；其餘是 1。"""
    if not line or side is None or not world.seal_acts or not on(content):
        return 1.0
    factor = 1.0
    for act in live(world, "chuanxi"):
        if act.target != line or act.side != side:
            continue
        aim = goal(content, world, side, line)
        if aim and (direction is None or aim * direction > 0):
            factor *= tuning(content).push
    return factor


def heart_open(world: WorldState, content: Content, character_id: str) -> bool:
    """收心：此刻有指定他的收心（求見不看門檻）。"""
    return on(content) and any(a.target == character_id for a in live(world, "shouxin"))


def heart_scale(world: WorldState, content: Content, character_id: str) -> float:
    """收心：跟他說話、宴客敬酒加的情誼倍數；沒有是 1。"""
    factor = 1.0
    if on(content):
        for act in live(world, "shouxin"):
            if act.target == character_id:
                factor *= tuning(content).affinity
    return factor


def warmer(world: WorldState, content: Content, character_id: str, delta: int) -> int:
    """收心放大加的情誼（「漲幅」；扣的照舊），四捨五入（同 renown.warmed 的進位）。"""
    if delta <= 0:
        return delta
    scale = heart_scale(world, content, character_id)
    return delta if scale == 1.0 else math.floor(delta * scale + 0.5 + 1e-9)


# ── 鎮地：誰都推不動、那一天不回、換了主人就結束 ─────────────────────

def held(world: WorldState | None, content: Content, loc_id: str, holder: str | None) -> SealAct | None:
    """鎮地：此刻替這一塊的主人（holder，conquest.holder）鎮住它的那一筆（好幾筆取最晚期滿的）；沒有、改版關著是 None。
    conquest.push_problem（攻、守、事件都推不動）與 letter_problem（下不了戰書）問它。"""
    if world is None or not world.seal_acts or holder is None or not on(content):
        return None
    rows = [a for a in live(world, "zhendi") if a.target == loc_id and a.side == holder]
    return max(rows, key=ends, default=None)


def held_during(world: WorldState, content: Content, loc_id: str, begin: float, end: float) -> bool:
    """鎮地：世界秒 [begin, end) 之間這一塊有沒有鎮過（conquest.decay：那一天鎮過就不回——「對面的進度不漲、也不回」）。"""
    if not world.seal_acts or not on(content):
        return False
    return any(a.kind == "zhendi" and a.target == loc_id and a.start < end and ends(a) > begin for a in world.seal_acts)


def hold_lapse(world: WorldState, loc_id: str, side: str | None) -> None:
    """這一塊換了主人（side，放回中立是 None）：替別人鎮著的那幾筆當場結束（攻城戰打贏、時刻表、管理者、補缺；conquest._announce、
    set_control 叫）。不看開關：關著時季上那一本本來就是空的。"""
    for act in world.seal_acts:
        if act.kind == "zhendi" and act.target == loc_id and act.side != side and act.ended is None and active(act, world.time):
            act.ended = world.time
def _back(state: GameState, content: Content, act: SealAct) -> bool:
    """回原處：他還在場、還站在被引到的地方才搬回去；回傳搬了沒。"""
    from . import figures  # noqa: PLC0415

    now = figures.state_of(state, content, act.target)
    if now.status != "active" or now.location != act.place or not act.origin or act.origin == act.place:
        return False
    figures._ensure(state, content, act.target).location = act.origin  # noqa: SLF001
    return True


def release(state: GameState, content: Content, fid: str) -> bool:
    """引將提前結束（PM 五之一 1：時刻表要搬他、他被打到退場、接位的人要搬他——時刻表優先）：先回原處、記下結束的那一刻。
    不另寫天下大事（時刻表與退場那一句本來就會寫）。沒被引著回 False。"""
    act = pinned(state.world, fid)
    if act is None:
        return False
    _back(state, content, act)
    act.ended = state.world.time
    return True


def tick(state: GameState, content: Content) -> list[str]:
    """期滿回原處（world.advance_world_state 每一步、人物活起來走動之前）：天下大事一句（BACK）。不看開關：關掉之前引出去的照樣回去。"""
    w = state.world
    if not w.seal_acts:
        return []
    from . import figures  # noqa: PLC0415
    from .rules import add_rumor  # noqa: PLC0415

    lines: list[str] = []
    for act in w.seal_acts:
        if act.kind != "yinjiang" or act.ended is not None or w.time + EPS < act.until:
            continue
        act.ended = act.until
        if _back(state, content, act):
            place = content.locations[act.origin].name if act.origin in content.locations else act.origin
            line = BACK.format(figure=figures.name_of(content, act.target), place=place)
            add_rumor(state, line, act.origin, content=content, layer="world")
            lines.append(line)
    return lines


def next_end(world: WorldState) -> float | None:
    """下一個還沒處理的引將期滿在什麼時候（world.advance_world_state 在那一刻另切一段）；沒有是 None。"""
    pending = [a.until for a in world.seal_acts if a.kind == "yinjiang" and a.ended is None]
    return min(pending) if pending else None
