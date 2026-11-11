"""軍令卡上「怎麼出力」那一行（軍情包，第二輪第 97 批從共用規則層 tianxia/atlas.py 搬來，字與本體一個不改）：order_how（軍令卡多寫的一行，
order_actions.orders_view 叫）、strike_how（打擊：怎麼打、他在哪）、siege_how（攻城：記得到的地點），與這幾句的字。只讀，不改狀態。
打擊點 _strike_place 輿圖包也讀，留在 atlas。

test_for 照包挑，這幾個檔挑不到，改了另外跑（-n 4）：tests/acts/test_conquest_flip.py、tests/acts/test_conquest_siege.py、tests/figures/test_orders.py、
tests/server/test_push_resistance.py、tianxia/features/map/tests/test_open_map.py；tianxia/features/sortie/tests/ 的 test_sortie、test_sortie_duel、
test_sortie_duel_words、test_sortie_duel_howto。"""
from __future__ import annotations

from tianxia import conquest, orders, territory  # 共用規則層（地盤、軍令）
from tianxia.atlas import is_known, region_of  # 共用規則層（atlas 留下的那一半）
from tianxia.atlas import _strike_place  # noqa: SLF001  同上（兩半原本在同一個檔）
from tianxia.models import Content
from tianxia.rules import trend_name
from tianxia.state import GameState, Order


def strike_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上打擊那道多寫的一行：怎麼打（到他所在的地方挑戰他本人、打贏記一次），以及他在哪。
    他的所在摸清了才寫地點名字；沒摸清只寫大區（沒有大區的內容就只說沒摸清），不洩漏沒摸清的地點（見 is_known）。
    他眼下挑戰不了（跟挑戰按鈕同一份規則，figures.can_challenge）就直說，不指路。"""
    name = orders.figure_name(content, order.figure)
    loc_id = _strike_place(state, content, order)
    if loc_id is None:
        where = "他眼下沒在戰線上領兵，挑戰不了"
    elif is_known(state, content, loc_id):
        where = f"他現在在{content.locations[loc_id].name}"
    elif (region := region_of(content, loc_id)) is not None:
        where = f"他現在在{region.name}一帶，那裡你還沒摸清"
    else:
        where = "他在哪裡你還沒摸清"
    return f"到{name}所在的地方挑戰他本人，打贏記一次（{where}）。"


SIEGE_NAMED_MAX = 2  # 攻城記得了次數的地點（orders.siege_places）只有這麼幾處時，軍令卡寫出地名（FB-221，PM 2026-10-14）；更多照舊寫「一帶」
SIEGE_AT = "到{where}遊歷，打贏一場{enemy}記一次{note}。"  # 待 joy 潤（FB-221）
SIEGE_UNSEEN = "（那裡你還沒摸清）"  # 待 joy 潤（FB-221）：記得了次數的地方都還沒摸清，只寫大區
SIEGE_SOME_UNSEEN = "（另一處你還沒摸清）"  # 待 joy 潤（FB-221）：兩處裡摸清了一處
SIEGE_AT_SORTIE = "到{where}出陣，打贏一場{enemy}記一次{note}。"  # 待 joy 潤：出陣開著時的攻城（設計第七節）
# 領地爭奪開著時（裁決 20；翻地與爭搶 PM 2026-10-20 第 1 條）：攻城認這一邊此刻進度最高、推得動的那一塊，打贏那裡的守軍（敵方的兵、中立駐軍都算），卡上照 siege_places 寫；待 joy 潤
SIEGE_CONQUEST_FOE = "守軍"
SIEGE_AREA_CONQUEST = "到{front}一帶我軍進度最高的幾處出陣，打贏一場守軍記一次。"  # 並列最高的多過 SIEGE_NAMED_MAX（全是 0 時就是那一帶推得動的每一處）
SIEGE_NONE_CONQUEST = "{front}一帶此刻沒有我軍推得動的地方（剛易手、下了戰書、或碰不到），在那裡打贏記不到。"
# 約戰開著（減法季批 3b，QA 順帶）：貼約戰、打贏一場就記一次——對面是真人、補位的人還是守軍都算，不寫「守軍」。待 joy 潤
SIEGE_AREA_DUEL = "到{front}一帶我軍進度最高的幾處出陣，打贏一場記一次。"
INTERCEPT_SORTIE = "到{place}出陣，撞上對面的運糧隊、打贏記一次。"  # 待 joy 潤（FB-248：出陣開著時糧隊只在這一處，orders.intercept_spots）
# 領地爭奪開著時（裁決 24、FB-565；翻地與爭搶 PM 2026-10-20 第 1 條）：守城記的是自家被對面推得最高、守得動的那幾塊（orders.defend_places），
# 卡上照它寫，輿圖也只標那幾處；沒有就直說此刻沒有可守的（記不到）。投票與 22:00 公告拿掉了，不再寫「被公告要攻」（dev/flip-1 收尾）。待 joy 潤
DEFEND_ACT_SORTIE = "出陣守一回，或按「{duty}」（收在「此地還能做」裡）"
DEFEND_ACT_PLAIN = "按「{duty}」（收在「此地還能做」裡）"
# 約戰開著（減法季批 3b）：守城是應戰守住（巡哨、傳道、保境安民不再算守城）。待 joy 潤
DEFEND_ACT_DUEL = "，對面在那裡約戰時去應戰、守住"
DEFEND_AT_CONQUEST = "到{where}{act}，做一次記一次。"  # 對面推得最高的自家地方只有一兩處（SIEGE_NAMED_MAX）時寫出地名
DEFEND_AREA_CONQUEST = "到{front}一帶對面推得最高的幾處自家地方{act}，做一次記一次。"  # 並列最高的多過 SIEGE_NAMED_MAX
DEFEND_NONE_CONQUEST = "{front}一帶此刻沒有對面在推、守得動的自家地方（剛易手的也守不動），沒有可守的，守了也記不到。"
# 約戰的季發了守城、此刻又沒人來打（orders.idle_defend_places；Joy 2026-11-11 決定卡「兩個都做」）：在自家地方巡哨、傳道，一天記一次
DEFEND_IDLE_DUEL = "{front}一帶沒人來打：在自家地方按「{duty}」，一天記一次。"  # 待 joy 潤
# 自家被戰書凍結的那一塊（FB-605，PM 2026-10-21）：照樣列進守城，那一場攻城站守方、守住記一次（出陣守、守勢行動在那裡不算）。待 joy 潤
DEFEND_SIEGE_CONQUEST = "{where}正等著一場攻城：加入那一場、站守方，守住記一次。"


def siege_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上攻城那道多寫的一行（FB-221）：記得了次數的地點（orders.siege_places：這條戰線上有敵方陣營隊伍的地方）只有一兩處時
    寫出地名（「到官軍大營遊歷，打贏一場官軍記一次。」）——潁川汝南的黃巾只有官軍大營記得到，寫「一帶」會讓人在潁川郊野、長社白打。
    沒摸清的地點同打擊（strike_how）只寫大區（沒有大區寫戰線），不洩漏名字。三處以上、或一處都沒有（舊存檔），照舊寫那條戰線一帶。
    出陣開著時說「出陣」、地點照控制方（設計第七節：攻城認出陣的攻打贏）。
    領地爭奪開著時（裁決 20；翻地與爭搶）：地點是此刻進度最高的那一塊（siege_places），對手寫「守軍」（中立駐軍也算）；這條線此刻沒有推得動的地方就直說
    記不到，不指「某一帶敵方的地盤」（那裡打贏記不到：列與記功同一個判斷）。"""
    front = trend_name(content, order.front) if order.front else "戰線"
    places = orders.siege_places(content, order.faction, order.front, state.world) if order.front else []
    enemy = content.scenario.faction_name(orders.ENEMY.get(order.faction or "")) or "對面的兵"
    if conquest.on(content, state.world):
        if not places:
            return SIEGE_NONE_CONQUEST.format(front=front)
        duel = conquest.duel_on(content, state.world)
        if len(places) > SIEGE_NAMED_MAX:
            return (SIEGE_AREA_DUEL if duel else SIEGE_AREA_CONQUEST).format(front=front)
        enemy = "" if duel else SIEGE_CONQUEST_FOE  # 約戰開著：打贏一場就記，不分對面是誰（真人、補位、守軍）
    if not places or len(places) > SIEGE_NAMED_MAX:
        return f"到{front}一帶遊歷，打贏一場對面的兵記一次。"
    known = [content.locations[loc_id].name for loc_id in places if is_known(state, content, loc_id)]
    hidden: list[str] = []
    for loc_id in places:
        if not is_known(state, content, loc_id):
            region = region_of(content, loc_id)
            area = f"{region.name if region is not None else front}一帶"
            if area not in hidden:
                hidden.append(area)
    note = "" if not hidden else SIEGE_SOME_UNSEEN if known else SIEGE_UNSEEN
    template = SIEGE_AT_SORTIE if territory.on(content) else SIEGE_AT
    return template.format(where="或".join(known + hidden), enemy=enemy, note=note)


def order_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上多寫的一行：這道軍令怎麼出力（FB-093：以前要等做完一次，引薦人的結語才說）。打擊照 strike_how、攻城照 siege_how；
    守城寫陣營自己的守勢行動（巡哨、傳道、保境安民），那一顆收在「此地還能做」裡。截糧、護糧的地點都是軍令本身就寫出來的，不多洩漏。"""
    if order.template == "strike":
        return strike_how(state, content, order)
    if order.template == "siege":
        return siege_how(state, content, order)
    def place(loc_id: str | None) -> str:
        return content.locations[loc_id].name if loc_id in content.locations else "那裡"

    front = trend_name(content, order.front) if order.front else "戰線"
    if order.template == "defend":
        duty = content.orders.duties.get(order.faction)
        name = duty.name if duty else "守勢"
        if conquest.on(content, state.world):  # 領地爭奪（裁決 24、FB-565）：只寫記得到的那幾處，列與記同一個判斷
            listed = orders.defend_places(content, state.world, order)
            if not listed:
                if orders.idle_defend_places(content, state.world, order):
                    return DEFEND_IDLE_DUEL.format(front=front, duty=name)
                return DEFEND_NONE_CONQUEST.format(front=front)
            sieged = [loc_id for loc_id in listed if conquest.frozen(state.world, loc_id) is not None]  # 被戰書凍結的（FB-605）：記攻城戰守住
            places = [loc_id for loc_id in listed if loc_id not in sieged]
            parts: list[str] = []
            if places:
                if conquest.duel_on(content, state.world):  # 約戰開著：守城記的是應戰守住（Game._duel_result 的 duty）
                    act = DEFEND_ACT_DUEL
                else:
                    act = (DEFEND_ACT_SORTIE if territory.on(content) else DEFEND_ACT_PLAIN).format(duty=name)
                if len(places) > SIEGE_NAMED_MAX:
                    parts.append(DEFEND_AREA_CONQUEST.format(front=front, act=act))
                else:
                    parts.append(DEFEND_AT_CONQUEST.format(where="或".join(content.locations[loc_id].name for loc_id in places), act=act))
            if sieged:
                parts.append(DEFEND_SIEGE_CONQUEST.format(where="、".join(content.locations[loc_id].name for loc_id in sieged)))
            return "".join(parts)
        return f"在{front}一帶按「{name}」（收在「此地還能做」裡），做一次記一次。"
    if order.template == "intercept":
        if territory.on(content):
            return INTERCEPT_SORTIE.format(place=place(order.location))
        return f"到{place(order.location)}或附近遊歷，撞上對面的運糧隊、打贏記一次。"
    if order.template == "escort":
        return (f"帶 {content.config.convoy_grain} 份糧草到{place(order.start)}接下糧車，"
                f"送到{place(order.end)}記一次。")
    return ""
