"""坐騎（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第五節；裝備二）：移動以省體力為主（疾行的體力，步行的時間；企劃者 2026-10-12 拿掉趕路），
另有三個用途——決戰騎兵（5.9）、截殺追逃（5.10）、落敗策馬脫身（5.11）；飽足度與餵、馬市、馬的名字與階、修練頁每一列與角色卡那一行。

數字全部乘飽足係數（edge_floor＋（1－edge_floor）×飽足度／100，5.4）；腳力＝省體力那一列（含品質）×飽足係數（5.1）。
只 import models、state、equipment（3.4：atlas 反過來 import 這裡算步調與腳力，engine、skillview、bot 也呼叫它），
不 import team、rules、atlas。開關是 Config.mounts.enabled（equipment.on(content, "mount")），不掛第一季開關（2.6）。
好馬（良駒、名駒）的來源是裝備三：這裡的數字、名字、比較都照階與品質寫，容得下良駒、名駒；名駒的專名到時候照 template 從內容讀，
所以這裡與引擎寫給玩家看的馬名都經過 name_of。例外：equipment.store（騎上、放上裝備庫）與 equipment.wield（換上）是四欄共用的，
直接用 item.name——裝備三要在 equipment 加依欄位取名的掛鉤，不能只改 name_of（計畫「範圍與取捨」）。
"""
from __future__ import annotations

import hashlib
import math

from . import equipment
from .equipment import NO_REPAIR_MATERIAL, RACK_FULL, repair_material
from .models import Content
from .state import Equipment, GameState, PlayerState

MARKET = "馬市"  # 選單上那一顆、紀錄的標題（待 joy 潤）
MARKET_TAG = "馬市"  # 地點標籤（content/locations.json：涿郡、汝南集市、宛城、下曲陽，5.5）；不寫死地點 id
TIER_NAMES = {1: "駑馬", 2: "良駒", 3: "名駒"}  # 5.6（待 joy 潤）
NOUNS = {1: "馬", 2: "駒", 3: "駒"}  # 名字＝毛色＋這個字；名駒的專名是裝備三的內容（template），還沒有時照「駒」（待 joy 潤）
COATS = ("棗騮", "青驄", "黑鬃", "白蹄", "花斑", "黃棕")  # 待 joy 潤：12 個名字都過了 naming.name_problem、沒在內容裡出現過
# 馬的圖（Joy 2026-10-17「我要真的水墨畫」，圖由她另外產）：每種毛色一張、兩匹名駒各一張，檔名 web/horse-<鍵>.webp；
# 鍵照毛色的拼音、名駒照 template。圖還沒放進 web/ 的鍵，網頁照舊畫原本的色塊（server.HORSE_ART 只列真的有檔的）
COAT_ART = {"棗騮": "zaoliu", "青驄": "qingcong", "黑鬃": "heizong", "白蹄": "baiti", "花斑": "huaban", "黃棕": "huangzong"}
STEED_ART = {"tashuang_ju": "tashuang", "polang_ju": "polang"}
WEAR_WORD = equipment.WEAR_WORDS["mount"]  # 「飽足度」：寫到它的地方都讀這個，不寫死（3.1、2.5）
HUNGRY_WARNING = "你的{name}餓得直打響鼻，餵牠一把料吧。"  # 待 joy 潤（5.4）
NO_MOUNT = "身上沒有坐騎"  # 待 joy 潤：「餵」灰掉時的原因
NOT_HUNGRY = "還不餓"  # 待 joy 潤
FEED_ON_ROAD = "在路上，停下來再餵"  # 待 joy 潤
FEED_SECLUDED = "閉關中"  # 待 joy 潤
FED = "你拿{material}把【{name}】餵飽了。"  # 待 joy 潤；Game.feed_mount 照開頭 FED_PREFIX 寫修練紀錄
FED_PREFIX = "你拿"
EMPTY = "身上沒有坐騎。"  # 待 joy 潤：修練頁坐騎那一段身上空著
RACK_NOTE = "城裡的馬市買得到駑馬；一個一階素材就餵得飽。"  # 待 joy 潤：修練頁坐騎那一段底下
MARKET_WHERE = "馬市買得到駑馬：{names}。"  # 待 joy 潤（FB-138）：身上什麼裝備都沒有時，修練頁坐騎那一行寫哪裡買得到；{names} 是帶「馬市」標籤的地點名字
CAVALRY_LINE = "你騎著{name}上陣，強攻、奇襲多 {pct}"  # 待 joy 潤（5.9）：決戰畫面，接在「你的職位」那一行後面
CAVALRY_REPORT = "你騎著{name}出陣"  # 待 joy 潤（5.9）：決戰的戰報與江湖紀錄
RAID_FLEE_ASK = "{him}的馬比你快，{odds}會被{him}跑掉。"  # 待 joy 潤（5.10）：截殺鈕的確認句後面
RAID_FLED = "{rival}一夾{horse}的馬腹跑了，你追之不及。"  # 待 joy 潤：發起的人那一則
RAID_ESCAPED = "{rival}半路攔你，你一夾{horse}的馬腹，策馬脫身。"  # 待 joy 潤：被截殺的人那一則
RAID_FLED_TAG = "{him}策馬跑了"  # {him}：他／她（gender.pronoun）  # 待 joy 潤
RAID_ESCAPED_TAG = "策馬脫身"  # 待 joy 潤
ESCAPED_LOSS = "你策馬脫身，銀兩沒丟。"  # 待 joy 潤（5.11）：落敗時保住那一成銀兩，戰報與紀錄各一句
ON_ROAD = "在路上"  # 待 joy 潤：修練頁裝備庫那一列「換上」灰掉時的原因（2.3：路上不能換坐騎）
NOT_MARKET = "這裡沒有馬市"  # 待 joy 潤
BOUGHT = "你花 {price} 兩買下一匹【{name}】。"  # 待 joy 潤
ENTERED = "你走進馬市，馬嘶聲此起彼落。"  # 待 joy 潤：打開馬市（Game._act）
LEAVE = "離開馬市"  # 待 joy 潤：馬市選單最後那一顆
LEFT = "你離開了馬市。"  # 待 joy 潤
STALE = "馬市的情形變了，這一下沒有作用；照現在的畫面再選一次。"  # 待 joy 潤（FB-195：兩個分頁搶，同懸賞榜 FB-162 的 bounties.STALE）
TRAVEL_BLOCKED = "馬市還開著，先離開才能安排前往"  # 待 joy 潤：atlas.travel_block（同鐵匠鋪那一句）
BUY = "market:buy"
FEED = "market:feed"
WIELD = "market:wield:"
BACK = "market:back"
FEED_AT = 50  # 整季機器人與假人飽足低於這裡才餵（設計第九節：約每 10 段一次）


def on(content: Content) -> bool:
    return equipment.on(content, "mount")


def riding(state: GameState, content: Content) -> Equipment | None:
    """身上那匹；開關關著、沒騎是 None。"""
    item = state.player.mount
    return item if on(content) and item is not None and item.slot == "mount" else None


def _cell(table: dict[str, float], item: Equipment) -> float:
    return table.get(str(item.tier), 0.0)


def fed_factor(content: Content, item: Equipment) -> float:
    """飽足係數（5.1、5.4）：餓到底剩 edge_floor，吃飽是 1。"""
    floor = content.config.mounts.edge_floor
    return floor + (1 - floor) * max(0, min(100, item.edge)) / 100


def _quality(content: Content, item: Equipment) -> float:
    return content.config.mounts.quality_bonus.get(item.quality, 0.0)


def speed_of(content: Content, item: Equipment) -> float:
    """這一匹路上快幾成（5.1）：路上快那一列（含品質）×飽足係數。"""
    return (_cell(content.config.mounts.speed, item) + _quality(content, item)) * fed_factor(content, item)


def leg_power(content: Content, item: Equipment | None) -> float:
    """這一匹的腳力（5.1）：省體力那一列（含品質）×飽足係數。不是坐騎、開關關著是 0。"""
    if item is None or item.slot != "mount" or not on(content):
        return 0.0
    return (_cell(content.config.mounts.stamina_save, item) + _quality(content, item)) * fed_factor(content, item)


def fresh_power(content: Content, item: Equipment | None) -> float:
    """吃飽的腳力：機器人比較兩匹用（不然餓了的好馬會被當成比較差的），馬市「買」鈕寫的也是它。"""
    return leg_power(content, item.model_copy(update={"edge": 100})) if item is not None else 0.0


def saving(state: GameState, content: Content) -> float:
    """身上那匹省幾成疾行的體力（腳力，5.1）；沒騎馬是 0。atlas.route_stamina、截殺追逃都讀它。"""
    return leg_power(content, riding(state, content))


def pace(state: GameState, content: Content) -> float:
    """步調（5.3）：步行的時間乘它（拿掉趕路之前出發的趕路也是）＝1－路上快（含品質）×飽足係數；沒騎馬是 1。出發時快照進 Journey.pace。"""
    item = riding(state, content)
    return 1.0 if item is None else 1 - speed_of(content, item)


def cavalry(state: GameState, content: Content) -> float:
    """決戰騎兵（5.9）：強攻、奇襲的份量多幾成＝騎兵那一列×飽足係數（品質不加）；沒騎馬是 0。"""
    item = riding(state, content)
    return 0.0 if item is None else _cell(content.config.mounts.cavalry, item) * fed_factor(content, item)


def escape(state: GameState, content: Content) -> float:
    """落敗策馬脫身的機會（5.11）：脫身那一列×飽足係數（品質不加）；沒騎馬是 0。必敗問句與 Game._lose_silver 都讀它。"""
    item = riding(state, content)
    return 0.0 if item is None else _cell(content.config.mounts.escape, item) * fed_factor(content, item)


def raid_flee(content: Content, attacker: GameState, target: GameState) -> float:
    """截殺追逃（5.10）：被截殺的人策馬脫身的機會＝守方腳力－攻方腳力，夾在 0～raid_escape_cap。開關關著兩邊都是 0。"""
    gap = saving(target, content) - saving(attacker, content)
    return max(0.0, min(content.config.mounts.raid_escape_cap, gap))


def abilities(content: Content, item: Equipment) -> dict[str, float]:
    """這一匹的四項本事（修練頁坐騎那一列與店面的馬廄共用；5.1）：疾行省幾成體力（腳力，save）、步行快幾成（speed）、決戰強攻奇襲多幾成
    （cavalry）、落敗脫身的機會（escape）——都照這一匹自己的階、品質與飽足算（同 cavalry()／escape() 的公式，只是不看身上騎的是不是牠）。"""
    rule, fed = content.config.mounts, fed_factor(content, item)
    return {
        "save": leg_power(content, item), "speed": speed_of(content, item),
        "cavalry": _cell(rule.cavalry, item) * fed, "escape": _cell(rule.escape, item) * fed,
    }


# ---- 字 ----

def half_up(x: float) -> int:
    """四捨五入、.5 一律進位（5.2；不用 round：Python 的 round 把 .5 捨到偶數，round(4.5) 是 4）。多補一個 1e-9：表裡的數字
    相乘常常差一點點才到 .5（30×(1－0.55)＝13.499999999999998），單用 math.floor(x＋0.5) 會漏掉那一個進位；1e-9 比任何有意義的
    差距小得多，只救浮點誤差。這一批坐騎的數字（體力、幾成、百分比）都走這裡。"""
    return math.floor(x + 0.5 + 1e-9)


def tenths(chance: float) -> int:
    """幾成：四捨五入、.5 進位（half_up）。"""
    return half_up(chance * 10)


def odds_text(chance: float) -> str:
    """寫給玩家看的機會（截殺確認句、必敗問句）：「約 3 成」；不到半成寫「不到一成」。待 joy 潤。"""
    n = tenths(chance)
    return f"約 {n} 成" if n else "不到一成"


def pct(ratio: float) -> str:
    """寫成整數百分比（設計 2.5 的例子：25%×0.8＝20%）：.5 進位（half_up），同 tenths 與 atlas.ride_stamina。
    不用 f"{ratio:.0%}"：它跟 round 一樣把 .5 捨到偶數，餓到底的駑馬省 12.5% 會寫成 12%、騎兵 2.5% 寫成 2%；
    也不單用 floor(x＋0.5)：餓了一半的駑馬脫身 0.30×0.75＝22.499999999999996 個百分點會寫成 22%、該寫 23%。"""
    return f"{half_up(ratio * 100)}%"


def coat_for(loc_id: str) -> str:
    """馬市那一匹的毛色（5.6）：照地點 id 的 sha256 挑，同一處永遠一樣、正式內容四處不一樣。取前 8 個位元組當整數：
    只取第一個位元組的話涿郡、宛城會撞成同一色（`test_four_markets_in_the_real_content_each_sell_their_own_coat` 鎖住）。"""
    digest = hashlib.sha256(loc_id.encode("utf-8")).digest()
    return COATS[int.from_bytes(digest[:8], "big") % len(COATS)]


def horse_name(coat: str, tier: int) -> str:
    """「棗騮馬」「青驄駒」（5.6）。"""
    return coat + NOUNS.get(tier, "馬")


def name_of(item: Equipment) -> str:
    """寫給玩家看的馬名。這一批就是 item.name；裝備三的名駒、名將贈禮照 template 從內容讀（joy 改名不動存檔）時改這裡，
    另外 equipment.store／wield 的三句（騎上、放上裝備庫、換上）直接用 item.name，要在 equipment 另加掛鉤（見模組說明）。"""
    return item.name


def grade(item: Equipment) -> str:
    """「駑馬・下品」（5.6：坐騎不用 equipment.grade 的「一階下品」）。"""
    return f"{TIER_NAMES.get(item.tier, '')}・{item.quality}"


# ---- 飽足與餵（5.4） ----

def hunger(state: GameState, content: Content, mode: str) -> list[str]:
    """抵達新的一站（Game._arrivals 的 new_leg）：身上那匹扣飽足度（步行、趕路 −5，疾行 −10）；第一次低到 edge_warn 以下回一句提醒
    （只一次，餵過或換一匹才重設）。沒騎馬、開關關著不扣。結伴同行時每個人照自己的馬扣（各自那一份 Game 的 _arrivals）。"""
    item, rule = riding(state, content), content.config.mounts
    if item is None:
        return []
    item.edge = max(0, item.edge - rule.hunger.get(mode, 0))
    if item.edge < rule.edge_warn and not state.player.hunger_warned:
        state.player.hunger_warned = True
        return [HUNGRY_WARNING.format(name=name_of(item))]
    return []


def feed_problem(state: GameState, content: Content) -> str | None:
    """餵不了的原因：沒騎馬（或開關關著）、在路上、閉關中、吃飽了、沒有一階素材。閒著時哪裡都能餵（不看打坐、選單，見計畫「範圍與取捨」）。"""
    p = state.player
    item = riding(state, content)
    if item is None:
        return NO_MOUNT
    if p.journey is not None:
        return FEED_ON_ROAD
    if p.busy_until is not None:
        return FEED_SECLUDED
    if item.edge >= 100:
        return NOT_HUNGRY
    if repair_material(state, content) is None:
        return NO_REPAIR_MATERIAL
    return None


def feed_note(state: GameState, content: Content) -> str:
    """「餵」鈕上那一段（修練頁、馬市）：餵得了寫用哪一種素材（「精鐵砂×1」），餵不了寫為什麼。"""
    problem = feed_problem(state, content)
    if problem is not None:
        return problem
    return f"{content.materials[repair_material(state, content)].name}×1"


def feed(state: GameState, content: Content) -> list[str]:
    """餵（5.4）：一個一階素材（屬性不限，背包裡最多的那一種，同修兵器），飽足回滿，不花銀兩；重設提醒。"""
    problem = feed_problem(state, content)
    if problem is not None:
        return [f"（{problem}。）"]
    p = state.player
    material = repair_material(state, content)
    p.materials[material] -= 1
    if not p.materials[material]:
        del p.materials[material]
    p.mount.edge, p.hunger_warned = 100, False
    return [FED.format(material=content.materials[material].name, name=name_of(p.mount))]


# ---- 馬市（5.5）：買、餵、換、離開 ----

def close_market(p: PlayerState) -> None:
    """收起馬市：選單與店面上馬販那一句（店面獨立介面設計 1.4）一起清。凡是把 picking_market 設成 False 的地方都走這裡
    （離開、讀檔修補、同步時人不在馬市、出發），同 equipment.close_smith。"""
    p.picking_market = False
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""


def market_here(state: GameState, content: Content) -> bool:
    """這裡有開著的馬市：坐騎開著、人不在路上、地點有「馬市」標籤。"""
    if not on(content) or state.player.journey is not None:
        return False
    return MARKET_TAG in (content.locations[state.player.location].tags or [])


def market_names(content: Content) -> list[str]:
    """帶「馬市」標籤的地點名字（內容裡的先後）；不寫死地名，內容換了跟著換。"""
    return [loc.name for loc in content.locations.values() if MARKET_TAG in (loc.tags or [])]


def where(state: GameState, content: Content) -> str:
    """修練頁坐騎那一段「哪裡買得到」（FB-138）：列出每一處馬市的名字；人正站在馬市多接一句「此地就有」；內容裡沒有馬市就不寫。"""
    names = market_names(content)
    if not names:
        return ""
    return MARKET_WHERE.format(names="、".join(names)) + (equipment.WHERE_HERE if market_here(state, content) else "")


def shop_item(state: GameState, content: Content) -> Equipment:
    """馬市那一匹（還沒買，id 是「架:馬」）：駑馬下品，毛色照這一處（5.6）。「買」鈕寫它、買下來照它新開一匹。"""
    name = horse_name(coat_for(state.player.location), 1)
    return Equipment(id="架:馬", slot="mount", name=name, tier=1, quality="下品")


def new_mount(state: GameState, *, name: str, tier: int, quality: str) -> Equipment:
    """新的一匹（四欄共用的流水號 +1，id「騎:N」）。裝備三的良駒、名駒也從這裡開。"""
    return Equipment(id=equipment.next_id(state, "mount"), slot="mount", name=name, tier=tier, quality=quality)


def rack_full(state: GameState, content: Content) -> bool:
    return equipment.rack_full(state, content, "mount")


def price(state: GameState, content: Content) -> int:
    """馬市一匹駑馬下品的價錢（5.5）：Config.mounts.shop_price，照所在地的地盤福利（出陣探索與地盤設計 4.3），四捨五入。
    mounts 只 import models、state、equipment：territory 延後 import。"""
    from . import territory  # noqa: PLC0415

    factor = territory.price_here(state, content)  # 地盤福利（照依附那一軍）× 名望的店家折扣（名聲設計 4.1）
    return int(content.config.mounts.shop_price * factor + 0.5)


def buy_problem(state: GameState, content: Content) -> str | None:
    if not market_here(state, content):
        return NOT_MARKET  # 選單關了、人走了：引擎層自己也再驗一次
    if rack_full(state, content):
        return RACK_FULL
    short = price(state, content) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def buy(state: GameState, content: Content) -> list[str]:
    """買一匹駑馬下品（5.5）：身上沒馬就直接騎上，不然放進裝備庫（equipment.store）。"""
    problem = buy_problem(state, content)
    if problem is not None:
        return [f"（{problem}。）"]
    cost = price(state, content)
    state.player.stats["silver"] -= cost
    shop = shop_item(state, content)
    item = new_mount(state, name=shop.name, tier=shop.tier, quality=shop.quality)
    return [BOUGHT.format(price=cost, name=name_of(item)), equipment.store(state, item)]


def stale_problem(state: GameState, content: Content, arg: str) -> str:
    """馬市的選項按下去時已經不在選單上、或灰掉了（兩個分頁搶，FB-195）：這一下為什麼不成。arg 是 market: 後面那一段。
    買照 buy_problem、餵照 feed_problem、換上照裝備庫裡還有沒有那一匹；都沒有更具體的原因就是 STALE。只讀。"""
    verb, _, rest = arg.partition(":")
    problem = None
    if verb == "buy":
        problem = buy_problem(state, content)
    elif verb == "feed":
        problem = feed_problem(state, content)
    elif verb == "wield" and not any(m.id == rest for m in equipment.in_slot(state.player, "mount")):
        problem = equipment.WIELD_MISSING.rstrip("。")
    return problem or STALE


def wield(state: GameState, content: Content, item_id: str) -> list[str]:
    """馬市的「換上」：只看坐騎那一欄；路上不能換由 equipment.wield 擋（Slot.road_locked）。"""
    return equipment.wield(state, content, item_id, ("mount",))


# ---- 機器人（設計第九節）：整季機器人（bot.visit_market）與伺服器假人（bot_policy.MARKET_SCORE）共用 ----

def better_mount(state: GameState, content: Content) -> str | None:
    """裝備庫裡比身上那匹快的（比吃飽的腳力 fresh_power，餓了的好馬不吃虧）最快那一匹的 id（同樣快照 id）；沒有是 None。
    馬市的 wanted 與整季機器人、假人在修練頁換馬（bot.wear_better，裝備三）共用這一份比法，改比法只改這裡。坐騎關著時腳力都是 0，回 None。"""
    p = state.player
    best = max(equipment.in_slot(p, "mount"), key=lambda m: (fresh_power(content, m), m.id), default=None)
    if best is None or fresh_power(content, best) <= fresh_power(content, p.mount) + 1e-9:
        return None
    return best.id


def wanted(state: GameState, content: Content, reserve: int = 0) -> str | None:
    """在馬市最該按的那一顆（整季機器人與伺服器假人共用）：裝備庫裡有比身上快的（比吃飽的腳力，餓了的好馬不吃虧）就換上；
    身上沒有坐騎、付得起馬價＋reserve 就買（馬市只賣駑馬：身上有馬就不買第二匹）；飽足低於 FEED_AT、餵得了就餵。不在馬市是 None。"""
    if not market_here(state, content):
        return None
    p = state.player
    better = better_mount(state, content)  # 裝備庫裡有比身上快的就換上（比法同 bot.wear_better）
    if better is not None:
        return f"{WIELD}{better}"
    if p.mount is None and buy_problem(state, content) is None and \
            p.stats.get("silver", 0) >= price(state, content) + reserve:
        return BUY
    if p.mount is not None and p.mount.edge < FEED_AT and feed_problem(state, content) is None:
        return FEED
    return None


# ---- 看得到（2.5）：修練頁每一列、角色卡那一行 ----

def _row(state: GameState, content: Content, item: Equipment, worn: bool) -> dict:
    """修練頁坐騎那一段的一列：階品、飽足度（wear_word）、疾行省幾成（save）、路上快幾成（speed）、決戰強攻奇襲多幾成（cavalry）、
    落敗脫身的機會（escape）——設計 2.5：路上快、騎兵、脫身寫在修練頁這一列，不擠進角色卡；每一項都照這一匹自己的階、品質與飽足算
    （同 cavalry()／escape() 的公式，只是不看身上騎的是不是牠）。身上那匹另給「餵」鈕的能不能按（feed）與那一段字（feed_note：
    用哪一種素材，或為什麼不行）。每一列給「換上」能不能按（wield_ok）與原因（wield_note）：路上不能換坐騎（2.3），網頁照它把裝備庫
    那一列的「換上」灰掉，不必按了才知道。裝備庫裡的沒有「餵」，也沒有拆解（4.8）。"""
    got = abilities(content, item)
    on_road = state.player.journey is not None
    row = {
        "id": item.id, "name": name_of(item), "tier": item.tier, "quality": item.quality, "grade": grade(item),
        "edge": item.edge, "wear_word": WEAR_WORD,  # 網頁照這個字寫「飽足度 N」（3.1 的字表，不在網頁寫死）
        "save": pct(got["save"]), "speed": pct(got["speed"]), "cavalry": pct(got["cavalry"]), "escape": pct(got["escape"]),
        "feed": False, "feed_note": "", "wield_ok": not on_road, "wield_note": ON_ROAD if on_road else "", "art": art_of(item),
    }
    if worn:
        row["feed"] = feed_problem(state, content) is None
        row["feed_note"] = feed_note(state, content)
    return row


def art_of(item: Equipment) -> str:
    """這一匹用哪一張圖（COAT_ART、STEED_ART 的鍵）：名駒照 template，其餘照名字開頭的毛色；都對不上是空字串。"""
    if item.template in STEED_ART:
        return STEED_ART[item.template]
    return next((key for coat, key in COAT_ART.items() if item.name.startswith(coat)), "")


def rows(state: GameState, content: Content) -> dict:
    """修練頁的坐騎那一段（skillview.gear_rows）：身上那匹、裝備庫裡的馬。開關關著時 worn 是 None、rack 是空的。"""
    p = state.player
    if not on(content):
        return {"worn": None, "rack": []}
    return {
        "worn": _row(state, content, p.mount, True) if p.mount is not None else None,
        "rack": [_row(state, content, m, False) for m in equipment.in_slot(p, "mount")],
    }


def card_line(state: GameState, content: Content) -> str:
    """本人卡上的「坐騎」那一行（2.5，待 joy 潤）：沒騎或開關關著是空字串。路上快、騎兵、脫身寫在修練頁那一列（_row 的 speed、
    cavalry、escape），不擠進角色卡。"""
    item = riding(state, content)
    if item is None:
        return ""
    return f"坐騎　【{name_of(item)}】{grade(item)}・{WEAR_WORD} {item.edge}，疾行省 {pct(leg_power(content, item))} 體力"
