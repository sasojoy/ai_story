"""出陣（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第二節；遊歷改版）。

只有投靠了陣營的人、只在戰線地點（territory.line_of）；照這裡此刻歸誰（territory.controller）分攻、守、攪局。每人每天
Config.sortie.per_day 次（攻守攪局共用），跟回體丹同一套換日（Game._pill_day：pill_now 的現實時間、pill_day_utc_offset_hours 的 00:00）。
這裡只放純規則（開關、次數、哪一種、推多少、字）；打一場、發獎勵、記功在 engine.Game._sortie。
選項 id 照留 act:train（設計第二節：程式裡的 id 可以照留）：伺服器的大場面判讀（server.may_judge_fight）、網頁行動列、機器人、量表都認它。"""
from __future__ import annotations

from typing import Literal

from . import rules, territory
from .models import Content
from .state import FrontChip, FrontReport, FrontRow, PlayerState, WorldState

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
RANGER_LINE_PRECISE = "散人不能出陣：投靠陣營之後才有。散人靠懸賞、事件與尋敵打的仗出力。"  # 一類一顆（FB-420；待 joy 潤）
RANGER_LINE_OUTING = "散人不能出陣：投靠陣營之後才有。散人靠懸賞、事件與出門探索打的仗出力。"  # 減法季探索一顆開著（沒有尋敵了，FB-817；待 joy 潤）
# 領地爭奪：別人的大本營與廣宗搶不下來、不推進度，不給攻（計畫第八章裁決 18）：出陣那一顆灰著寫 OUT_NOTE、行動列底下那一行寫 OUT_LINE。待 joy 潤
# OUT_NOTE 是行動列格子裡的小字：一行約 60 px、10 px 的字只放得下六個（同 RANGER_NOTE），「此地」兩個字留給底下那一行
OUT_NOTE = "不在爭奪之列"
OUT_LINE = "此地不在爭奪之列：各家的大本營與廣宗搶不下來，出陣推不了進度，這裡不能攻。"
# 領地爭奪：守勢行動（巡哨、傳道、保境安民）只守自家的地方（計畫第八章裁決 24，PM 2026-10-20）：別人的區塊（含大本營、廣宗）、還沒佔下的
# 中立地，那一顆灰著寫原因（跟出陣用完同一種寫法：「{名字}（{原因}）」，在「此地還能做」裡），按下去什麼都不給。待 joy 潤
DUTY_OUT_OTHER = "守勢只守自家的地盤，這裡歸別人"
DUTY_OUT_OPEN = "守勢只守自家的地盤，這裡還沒人佔"


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


def out_of_contest(content: Content, world: WorldState | None, faction: str | None, loc_id: str) -> bool:
    """領地爭奪在這一季生效時，投靠了陣營的人站在搶不下來、又不是自家的區塊（別人的大本營、廣宗；計畫第八章裁決 18）：這裡沒有出陣
    （截糧的運糧隊經過時例外，那時 mode 是攻），那一格灰著寫 OUT_NOTE。"""
    if faction is None or not on(content):
        return False
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    return (conquest.on(content, world) and loc_id in conquest.blocks(content) and not conquest.capturable(content, loc_id)
            and conquest.holder(world, content, loc_id) != faction)


def duty_problem(content: Content, world: WorldState | None, faction: str | None, loc_id: str) -> str:
    """領地爭奪在這一季生效時，守勢行動（巡哨、傳道、保境安民）站的地方不是自家的區塊（別人的大本營與區塊、廣宗、還沒佔下的中立地）：
    灰掉的原因（DUTY_OUT_OTHER／DUTY_OUT_OPEN）；給得了（自家的區塊、不是區塊的地點、關著的季）是空字串。faction 是依附那一軍的
    side（Game._side：豪強分屬兩軍的季是依附的那一軍）。不是區塊的地點（南華觀、豪強三處投靠點）誰也不佔，這一版不動。"""
    if faction is None:
        return ""
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    if not conquest.on(content, world) or loc_id not in conquest.blocks(content):
        return ""
    holder = conquest.holder(world, content, loc_id)
    if holder == faction:
        return ""
    return DUTY_OUT_OPEN if holder is None else DUTY_OUT_OTHER


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


# ── 出陣回報（企劃者 2026-10-23 在草稿上選「寫數字」）：領地爭奪開著時，出陣那一下在「剛剛」卡片底下多一塊——那一塊的進度條、一句話、
# 幾顆小籤（今天自己推了多少、全軍今天推了多少、軍令進度）。Game._sortie 打完叫 report，存在那一則江湖紀錄（JournalEntry.front）。待 joy 潤
REPORT_TITLE = "{place}・進度"
REPORT_COUNT = "你今日出陣 {n}/{cap}"
REPORT_FLIP = "{place}被你這一下推滿，落入{side}之手。"
REPORT_ATTACK = "{place}{holder}。{side}的進度 {value}／100，再推 {left} 就{take}。"
REPORT_HELD_BY = "歸{side}"
REPORT_OPEN = "還沒有人佔"
REPORT_TAKE = "易手"
REPORT_TAKE_OPEN = "佔下"
REPORT_STALLED = "這一下沒推動。"  # 打輸守軍、混戰輸了
REPORT_HOLD = "{place}{side}守著。{rival}的進度被拉到 {value}／100，推到 100 才奪得走。"
REPORT_HOLD_CLEAR = "{place}{side}守著，對面的進度都已歸零。"
REPORT_BLOCKED = "{place}此刻推不動進度：{why}。"
CHIP_FLIP = "易手・這一下是你推滿的"
CHIP_MINE = "今天你替{side}推了 {n}"
CHIP_ALL = "全軍今天 {n}"
CHIP_ORDER = "軍令「{kind}」{done}/{quota}"
CHIP_ORDER_DONE = "軍令「{kind}」{done}/{quota} 已達成"


def amount_text(x: float) -> str:
    """小籤上的量：四捨五入成整數（同 conquest.PUSH_LINE）；推動了卻不到半點寫「不到 1」，沒推是 0。"""
    n = int(x + 0.5)
    return str(n) if n > 0 or x <= 0 else "不到 1"


def report(
    content: Content, world: WorldState, loc_id: str, side: str, how: str, *, before: dict[str, float], moved: float, flipped: bool,
    why: str | None, used: int, mine_today: float, side_today: float, orders: list[tuple[str, int, int, bool]],
) -> FrontReport:
    """出陣回報（FrontReport）：before 是這一下之前每一條進度（攻方 → 值），world 是這一下之後；moved 是這一下自己推（拉）動了多少；
    why 是這一下之前推不推得動（conquest.push_problem）；used 是今天已出陣幾次（含這一下）；orders 是（軍令種類名, 陣營完成次數, 額度, 達成了沒）。"""
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    place = content.locations[loc_id].name
    name = lambda f: content.scenario.faction_name(f, f)  # noqa: E731
    held = conquest.holder(world, content, loc_id)
    after = conquest.bars(world, loc_id)
    rows = [
        FrontRow(side=f, name=name(f), value=int(after.get(f, 0.0) + 0.5), before=int(before.get(f, 0.0) + 0.5), mine=f == side)
        for f in sorted(set(after) | set(before), key=lambda f: (f != side, -after.get(f, 0.0), f))
        if not (flipped and f == side)  # 推滿那一下所有條都清掉：自己那一條另外畫成滿的
    ]
    if flipped:
        rows.insert(0, FrontRow(side=side, name=name(side), value=100, before=int(before.get(side, 0.0) + 0.5), mine=True))
    elif how == "attack" and why is None and not any(r.mine for r in rows):  # 推得動、還沒推上來（打輸了）：自己那一條照樣畫一條空的
        rows.insert(0, FrontRow(side=side, name=name(side), value=0, before=0, mine=True))
    if flipped:
        text = REPORT_FLIP.format(place=place, side=name(side))
    elif why is not None and why != conquest.WHY_IDLE:
        text = REPORT_BLOCKED.format(place=place, why=why)
    elif how == "attack":
        value = int(after.get(side, 0.0) + 0.5)
        text = (REPORT_STALLED if moved <= 0 else "") + REPORT_ATTACK.format(
            place=place, holder=REPORT_HELD_BY.format(side=name(held)) if held else REPORT_OPEN, side=name(side), value=value,
            left=100 - value, take=REPORT_TAKE if held else REPORT_TAKE_OPEN)
    else:
        rivals = sorted(((v, f) for f, v in after.items() if f != side), reverse=True)
        text = (REPORT_HOLD.format(place=place, side=name(side), rival=name(rivals[0][1]), value=int(rivals[0][0] + 0.5)) if rivals
                else REPORT_HOLD_CLEAR.format(place=place, side=name(side)))
    chips = [FrontChip(text=CHIP_FLIP, kind="flip")] if flipped else []
    chips += [FrontChip(text=CHIP_MINE.format(side=name(side), n=amount_text(mine_today))),
              FrontChip(text=CHIP_ALL.format(side=name(side), n=amount_text(side_today)))]
    chips += [FrontChip(text=(CHIP_ORDER_DONE if done else CHIP_ORDER).format(kind=kind, done=n, quota=quota))
              for kind, n, quota, done in orders]
    return FrontReport(
        loc=loc_id, title=REPORT_TITLE.format(place=place), count=REPORT_COUNT.format(n=used, cap=content.config.sortie.per_day),
        holder=held, side=side, rows=rows, text=text, chips=chips,
    )
