"""出陣的純規則（功能包 tianxia/features/sortie/；原 tianxia/sortie.py，那個名字留成指到這裡的別名）。
出陣探索與地盤設計（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md）第二節；遊歷改版。

只有投靠了陣營的人、只在領地爭奪的區塊（conquest.blocks）；照這裡此刻歸誰（conquest.holder）分攻、守。每人每天
Config.sortie.per_day 次（攻守共用），跟回體丹同一套換日（Game._pill_day：pill_now 的現實時間、pill_day_utc_offset_hours 的 00:00）。
舊出陣的推線與攪局 2026-10-27 拿掉（企劃者選「拿掉舊玩法和它的測試」）：出陣推的是那一塊的進度（conquest）。
這裡只放純規則（開關、次數、哪一種、字）；打一場、發獎勵、記功在這一包的 actions.sortie（Game._sortie 留一行委派）。
選項 id 照留 act:train（設計第二節：程式裡的 id 可以照留）：伺服器的大場面判讀（server.may_judge_fight）、網頁行動列、機器人、量表都認它。"""
from __future__ import annotations

from typing import Literal

from tianxia import territory  # 過渡：待搬（地盤：出陣的開關就是地盤的，territory.on）
from tianxia.models import Content
from tianxia.state import FrontChip, FrontReport, FrontRow, PlayerState, WorldState

Mode = Literal["attack", "hold"]
NAME = "出陣"  # 待 joy 潤
MODE_NAMES: dict[str, str] = {"attack": "攻", "hold": "守"}  # 待 joy 潤
LEFT_NOTE = "今日還能 {n} 次"  # 待 joy 潤：鈕上體力後面那一段
USED_UP = "今日已出陣 {n} 次，明日 00:00 後再出陣"  # 待 joy 潤（設計 2.3；鈕上不帶句號，行動列底下那一行補句號）
HOLD_LINE = "你在{place}整頓營伍、巡守要道，替自家守住這一處。"  # 待 joy 潤
PROLOGUE_FIGHT = "雪恥"  # 待 joy 潤：序章那一場寫好的仗（不算出陣次數，鈕上與紀錄標題寫它）
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

# 混戰（輿圖簡化設計 4.3）：出陣時撞上對面正在推這一塊的人。待 joy 潤（原本寫在 engine.py；那邊留 test_raid 要的三個名字）
CLASH_TITLE = "混戰・{rival}"
CLASH_HIT_TITLE = "遭{rival}撞上"
CLASH_OPEN = "{rival}正在{place}替{side}出力，兩人撞個正著，當場動起手來。"
CLASH_WON = "你逼退了{rival}，這一下推得更多。"
CLASH_LOST = "你被{rival}逼退，這一趟白跑了。"
CLASH_DRAW = "兩人鬥了一陣不分高下，各自退開，你照樣出陣。"
CLASH_LOST_TAG = "混戰落敗"  # 出陣那一則的結果（輸了白跑）
CLASH_THEIRS_WON = "{rival}在{place}出陣，撞上了你；你逼退了{him}，{him}那一下白跑了。"
CLASH_THEIRS_LOST = "{rival}在{place}出陣，撞上了你；你不敵，{him}那一下推得更多。"
CLASH_THEIRS_DRAW = "{rival}在{place}出陣，撞上了你；兩人鬥了一陣不分高下，各自退開。"


def on(content: Content) -> bool:
    """出陣開著：地盤（＝領地爭奪）開著就有（territory.on），沒有開關。"""
    return territory.on(content)


def ranger_here(content: Content, faction: str | None, loc_id: str, world: WorldState | None = None) -> bool:
    """散人站在區塊上（FB-250）：投靠了陣營的人在這裡會有出陣，散人沒有——那一格寫原因，不寫「不在戰線」。"""
    if faction is not None or not on(content):
        return False
    from tianxia import conquest  # noqa: PLC0415  過渡：待搬（conquest → territory → rules：在函式裡 import）

    return loc_id in conquest.blocks(content)


def out_of_contest(content: Content, world: WorldState | None, faction: str | None, loc_id: str) -> bool:
    """領地爭奪在這一季生效時，投靠了陣營的人站在搶不下來、又不是自家的區塊（別人的大本營、廣宗；計畫第八章裁決 18）：這裡沒有出陣
    （截糧的運糧隊經過時例外，那時 mode 是攻），那一格灰著寫 OUT_NOTE。"""
    if faction is None or not on(content):
        return False
    from tianxia import conquest  # noqa: PLC0415  過渡：待搬（conquest → territory → rules：在函式裡 import）

    return (loc_id in conquest.blocks(content) and not conquest.capturable(content, loc_id)
            and conquest.holder(world, content, loc_id) != faction)


def duty_problem(content: Content, world: WorldState | None, faction: str | None, loc_id: str) -> str:
    """領地爭奪在這一季生效時，守勢行動（巡哨、傳道、保境安民）站的地方不是自家的區塊（別人的大本營與區塊、廣宗、還沒佔下的中立地）：
    灰掉的原因（DUTY_OUT_OTHER／DUTY_OUT_OPEN）；給得了（自家的區塊、不是區塊的地點、關著的季）是空字串。faction 是依附那一軍的
    side（Game._side：豪強分屬兩軍的季是依附的那一軍）。不是區塊的地點（南華觀、豪強三處投靠點）誰也不佔，這一版不動。"""
    if faction is None:
        return ""
    from tianxia import conquest  # noqa: PLC0415  過渡：待搬（conquest → territory → rules：在函式裡 import）

    if not on(content) or loc_id not in conquest.blocks(content):
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
    """在這裡出陣是哪一種；None＝這裡沒有出陣鈕（散人、不是區塊、別人的或中立的卻沒有能打的隊伍）。
    foes：這裡有能打的對手（Game._sortie_foes：conquest.sortie_foes，加上截糧帶來的敵方運糧隊）。
    領地爭奪（計畫 Task 6）：每一塊區塊都有出陣；自家的守（有截糧的運糧隊照打），別人的、中立的攻。"""
    if faction is None or not on(content):
        return None
    from tianxia import conquest  # noqa: PLC0415  過渡：待搬（conquest → territory → rules：在函式裡 import）

    if loc_id not in conquest.blocks(content):
        return None
    if conquest.holder(world, content, loc_id) == faction:
        return "attack" if foes else "hold"
    return "attack" if foes else None


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
# 小籤寫字不寫數字（企劃者 2026-10-26「出陣寫字」）：推的量照 Config.sortie.chip_*_steps 分三級，軍令照完成幾成分級。進度條、「你今日出陣 n/5」照舊
CHIP_MINE = "今天你替{side}{n}"
CHIP_ALL = "全軍今天{n}"
CHIP_ORDER = "軍令「{kind}」{done}"
CHIP_ORDER_DONE = "軍令「{kind}」已達成"
AMOUNT_NONE = "還沒推動"
AMOUNT_WORDS = ("推了一點", "推了不少", "推了一大截")  # 待 joy 潤
ORDER_WORDS = ((0.0, "還沒起頭"), (0.5, "剛起頭"), (0.8, "過半"), (1.0, "快成了"))  # 完成幾成「不到」這個數用這一句；待 joy 潤


def amount_words(x: float, steps: tuple[float, float]) -> str:
    """小籤上的量：沒推（四捨五入不到 0.5 也算推了一點）寫「還沒推動」，其餘照 steps 分三級。"""
    if x <= 0:
        return AMOUNT_NONE
    return AMOUNT_WORDS[sum(x >= s for s in steps)]


def order_words(done: int, quota: int) -> str:
    """軍令進度：0 次「還沒起頭」，不到一半「剛起頭」，不到八成「過半」，其餘「快成了」（達成了另一句 CHIP_ORDER_DONE）。"""
    if done <= 0 or quota <= 0:
        return ORDER_WORDS[0][1]
    share = done / quota
    return next((w for cap, w in ORDER_WORDS[1:] if share < cap), ORDER_WORDS[-1][1])


def report(
    content: Content, world: WorldState, loc_id: str, side: str, how: str, *, before: dict[str, float], moved: float, flipped: bool,
    why: str | None, used: int, mine_today: float, side_today: float, orders: list[tuple[str, int, int, bool]],
) -> FrontReport:
    """出陣回報（FrontReport）：before 是這一下之前每一條進度（攻方 → 值），world 是這一下之後；moved 是這一下自己推（拉）動了多少；
    why 是這一下之前推不推得動（conquest.push_problem）；used 是今天已出陣幾次（含這一下）；orders 是（軍令種類名, 陣營完成次數, 額度, 達成了沒）。"""
    from tianxia import conquest  # noqa: PLC0415  過渡：待搬（conquest → territory → rules：在函式裡 import）

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
    cfg = content.config.sortie
    chips += [FrontChip(text=CHIP_MINE.format(side=name(side), n=amount_words(mine_today, cfg.chip_mine_steps))),
              FrontChip(text=CHIP_ALL.format(side=name(side), n=amount_words(side_today, cfg.chip_all_steps)))]
    chips += [FrontChip(text=(CHIP_ORDER_DONE if done else CHIP_ORDER).format(kind=kind, done=order_words(n, quota)))
              for kind, n, quota, done in orders]
    return FrontReport(
        loc=loc_id, title=REPORT_TITLE.format(place=place), count=REPORT_COUNT.format(n=used, cap=content.config.sortie.per_day),
        holder=held, side=side, rows=rows, text=text, chips=chips,
    )
