"""寶物與好馬的來源（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；裝備三）。

- 寶物：一件一種效果、不分階品、不磨損、不能拆，身上只配一件（PlayerState.treasure）；隨時能換（2.3【定】，企劃者 2026-10-11：
  不設限制，走修練頁的「換上」equipment.wield）。效果的數字在 Config.treasures.effects，內容（content/gear.json）只寫名字與效果種類。
  所有掛點都經過 amount（沒穿、開關關著、效果對不上都回中性值），畫面寫的機率與實際擲的是同一個數。
- 好馬：良駒（懸賞的重賞、奇遇；毛色與品質照那一筆的種子）與名駒（名將贈禮；專名照 template 從內容讀）；馬本身的規則在 mounts，
  新的一匹一律從 mounts.new_mount 開。
- 四種來源：懸賞的重賞（bounty_prize；掛單時擲在 bounties.issue）、名將贈禮（gifts_due，Game.choose／answer_event 最後叫）、
  奇遇（grant_effect，rules.apply_effect 的 Effect.gear）、挑戰本人掉落（challenge_drop，Game._challenge）。
- 不重複（6.5）：掉落池只抽你還沒有的（身上、裝備庫、寄放的都算，照 template 認）；都有了給 dup_silver 兩。
- 寄放（6.5）：懸賞的重賞與名將贈禮在裝備庫滿了時放進 PlayerState.held_gear，同步與快轉時 deliver_held 補發（閉關中也補）。

擲骰一律用自己的 random.Random(種子)，不碰 Game.rng（FB-129：整季測試與量表的基準不位移）。
只 import models、state、equipment、mounts；不 import team、rules、cultivation、bounties、materials（它們反過來呼叫這裡）。
玉璽碎片（玉璽碎片設計 7.2～7.4）在寶物欄多一格「傳承」（PlayerState.heirloom，不進裝備庫、不換）：_cells 多加那一格（只看
Config.seal.enabled、不看寶物的開關，查 Config.seal.effects）、MULTIPLY 加碎片的乘法鍵，八個掛點都不用動；不重複照 template，
不假設「換季全清」。rows、card_line 照兩格各自的開關（玉璽碎片設計第十節）；碎片的七句字也在這裡（seal 轉呼叫，字只留一份）。
"""
from __future__ import annotations

import math
import random

from . import calendar, equipment, mounts
from .models import GOOD_HORSE, Content, SteedDef
from .state import Equipment, GameState, PlayerState

# 乘的效果（中性值 1）；其餘是加的（中性值 0）。碎片的乘法鍵（玉璽碎片設計 7.2）也在這裡；talk_turns、dodge、fuse_points 是加的。
# 改版（Config.seal.revamp）多的兩個乘法鍵：injury（螭首）、chuangong（歸心）；keep_silver（金角）是加的（1＝有）
MULTIPLY = frozenset({"cultivate", "insight", "legend", "hp_cap", "practice", "stamina_regen", "mate_exp", "injury", "chuangong"})
EFFECT_TEXT = {  # 待 joy 潤：角色卡、修練頁、拿到時那一句（數字照 Config.treasures.effects；{item} 是破境丹的名字 Config.legend_item_name）
    "cultivate": "衝絕學的機會 ×{x}",
    "insight": "探索悟得意境的機會 ×{x}",
    "win_xinde_pct": "打贏的心得 +{pct}",
    "win_exp_pct": "打贏的經驗 +{pct}",
    "seclusion": "閉關的心得 +{pct}",
    "audience": "求見門檻 −{n}",
    "win_material": "打贏時有 {pct} 的機會多掉一個素材",
    "legend": "探索撿到{item}的機會 ×{x}",
}
INSIGHT_SENSE_TEXT = "靜心感悟擲中的機會 +{n} 個百分點"  # 待 joy 潤：探索三選一開著時觀山石那一句（effect_text）
SEAL_EFFECT_TEXT = {  # 待 joy 潤：玉璽碎片的七種效果（數字照 Config.seal.effects；seal.effect_text 轉呼叫這裡，字只留一份）
    "hp_cap": "氣血上限 ×{x}", "talk_turns": "每位人物每日多談 {n} 輪", "practice": "練成的心得 ×{x}",
    "dodge": "落敗閃成僵持的機會 +{pct}", "stamina_regen": "體力回復 ×{x}", "fuse_points": "自創的意分 +{n}",
    "mate_exp": "同伴拿到的經驗 ×{x}",
}
SEAL_POWER_TEXT = "戰力 ×{x}"  # 待 joy 潤：改版每片都有的那一半（Config.seal.revamp.power），排在最前面
SEAL_REVAMP_TEXT = {  # 待 joy 潤：改版的常駐成長、生活效果（玉璽碎片改版第三章；數字照 Config.seal.revamp.effects）
    "injury": "一場仗變成內傷的 ×{x}", "talk_turns": "每位人物每日多談 {n} 輪", "audience": "求見門檻 −{n}",
    "practice": "練成的心得 ×{x}", "keep_silver": "落敗不失銀兩", "stamina_regen": "體力回復 ×{x}",
    # 赤璋：武學重構之後合成不擲品質，改加自創的意分（create.seal_points；PM 2026-10-21 合 develop 時定，改版 +10、關著照舊 +5）
    "fuse_points": "自創的意分 +{n}", "mate_exp": "同伴拿到的經驗 ×{x}", "chuangong": "傳功的心得 ×{x}",
}
KEEP_SILVER = "懷中的『{shard}』護住了錢囊，銀兩分文未失。"  # 待 joy 潤：金角（改版）落敗那一下，戰報與江湖紀錄（Game._lose_silver）
HEIRLOOM_LABEL = "傳承"  # 待 joy 潤：寶物段那一列的小標、角色卡那一行的開頭
GOT = "你得到了寶物【{name}】（{effect}）。"  # 待 joy 潤
GOT_HORSE = "你得到一匹{grade}的【{name}】。"  # 待 joy 潤（grade 是 mounts.grade：「良駒・中品」）
DUP = "你已經有一件【{name}】了，換成銀兩 {silver}。"  # 待 joy 潤（6.5：奇遇給的那一件已經有了）
ALL_OWNED = "這幾樣寶物你都有了，換成銀兩 {silver}。"  # 待 joy 潤（6.5：掉落池都有了）
NO_ROOM = "裝備庫滿了，【{name}】帶不走。"  # 待 joy 潤（6.5：奇遇當下拿不了就沒了）
HELD = "裝備庫滿了，【{name}】先寄放著；拆掉幾件用不上的兵器或防具，騰出空位之後回來就補給你。"  # 待 joy 潤（6.5；2.2 的「拆掉幾件」提醒）
HELD_TITLE = "寄放"  # 待 joy 潤：補發那一則江湖紀錄的標題
HELD_ARRIVED = "寄放的【{name}】送到了。"  # 待 joy 潤
EMPTY = "身上沒有寶物。"  # 待 joy 潤：修練頁寶物那一段身上空著
RACK_NOTE = "寶物買不到、打不出，只從懸賞、名將、奇遇與打敗大勢人物得來；隨時能換。"  # 待 joy 潤：修練頁寶物那一段底下
HEIRLOOM_NOTE = "傳承那一件是玉璽碎片，跟著你走，不能換下。"  # 待 joy 潤（FB-180）：有傳承時寶物段底下多這一句；寶物關著時只寫這一句
WHERE = "買不到、打不出，只從懸賞、名將、奇遇與打敗大勢人物得來。"  # 待 joy 潤（FB-138）：身上什麼裝備都沒有時，修練頁寶物那一行寫哪裡得來
LOST = "這件寶物的來歷已經失傳"  # 待 joy 潤：內容拿掉了這一件（template 查不到，效果不算）
HELD_NOTE = "寄放著：{names}——裝備庫騰出空位，下次回來就補給你。"  # 待 joy 潤：修練頁「裝備」塊底下
PRIZE_SLOTS = {"treasure": "treasure", "horse": "mount"}  # 重賞（Bounty.prize）→ 那一欄：那一欄關著就不掛、不發
PRIZE_WORDS = {"treasure": "寶物一件", "horse": "良駒一匹"}  # 待 joy 潤（6.4：掛單時只記「寶物一件」或「良駒一匹」）
PRIZE_NOTE = "・另有重賞：{what}"  # 待 joy 潤：懸賞榜、懸賞卡、揭下的回話，接在賞的那一段後面
PRIZE_GOT = "{issuer}另有重賞，交到你手上。"  # 待 joy 潤
GIFT_LINE = "{general}把【{gift}】交到你手上：『你我投緣，這個你拿著。』"  # 待 joy 潤（6.3；GiftDef.line 沒寫時用這一句）：他就在你身邊
GIFT_SENT_LINE = "{general}託人送來【{gift}】，捎話說：『你我投緣，這個你拿著。』"  # 待 joy 潤（FB-139）：他不在你身邊
GIFT_TITLE = "名將贈禮"  # 待 joy 潤（FB-139、FB-149）：名將贈禮與本命兵器另起一則江湖紀錄，不接在當下那個動作裡
HORSE_GAIN_LINE = "良駒【{name}】"  # 待 joy 潤：出陣掉的良駒寫在戰報「得失」那一格（FB-430，同 GAIN_LINE）
GAIN_LINE = "寶物【{name}】"  # 待 joy 潤：戰報「得失」那一格（同 weapons.GAIN_LINE：素材寫「精鐵砂 ×1」，寶物寫「寶物【烏木名刺】」）
DROP_LINE = "{who}走得匆忙，落下了【{name}】，你撿了起來。"  # 待 joy 潤（6.4 挑戰本人；FB-140：前一句已經是「某某敗走。」，不再寫一次敗走）


def on(content: Content) -> bool:
    return equipment.on(content, "treasure")


def revamp_on(content: Content) -> bool:
    """玉璽碎片改版開著（同 seal.revamp_on；treasures 不 import seal）：碎片開著（Config.seal.enabled＋內容有七片）、子開關開著。"""
    cfg = content.config.seal
    return cfg.enabled and cfg.revamp.enabled and bool(content.seal)


def effect_of(content: Content, item: Equipment | None) -> str | None:
    """這一件寶物的效果鍵（照 template 查寶物表）；不是寶物那一欄、沒有 template、內容拿掉了是 None（效果不算）。"""
    if item is None or item.slot != "treasure" or item.template is None:
        return None
    tdef = content.gear.treasures.get(item.template)
    return tdef.effect if tdef is not None else None


def effect_text(content: Content, key: str) -> str:
    """「求見門檻 −3」「打贏的心得 +20%」（待 joy 潤）：數字照 Config.treasures.effects；百分比 .5 進位（不用 round／:.0%，同 mounts.pct）。
    探索悟意境（觀山石）照探索三選一的開關寫（PM 2026-10-16）：開著時是靜心感悟擲中的機會多幾個百分點（Config.explore_modes.sense_treasure_points），
    關著才是探索悟意境那一支的比重 ×{x}。"""
    if key == "insight" and content.config.explore_modes.enabled:
        return INSIGHT_SENSE_TEXT.format(n=f"{content.config.explore_modes.sense_treasure_points:g}")
    value = content.config.treasures.effects.get(key, 0.0)
    return EFFECT_TEXT.get(key, "").format(
        x=f"{value:g}", pct=f"{math.floor(value * 100 + 0.5)}%", n=f"{value:g}", item=content.config.legend_item_name,
    )


def seal_effect_text(content: Content, key: str) -> str:
    """碎片那一句（「練成的心得 ×0.9」）：數字照 Config.seal.effects（改版關著的那一個效果）。"""
    value = content.config.seal.effects.get(key, 0.0)
    return SEAL_EFFECT_TEXT.get(key, "").format(x=f"{value:g}", n=f"{value:g}", pct=f"{math.floor(value * 100 + 0.5)}%")


def heirloom_text(content: Content, shard) -> str:
    """傳承那一格的說明（傳承那一列、角色卡、拿到時、碎片卡；seal.shard_text 轉呼叫這裡）。shard 是 ShardDef。改版開著：
    「戰力 ×1.1、每位人物每日多談 2 輪、求見門檻 −5」（戰力在前，效果照 content/seal.json 的 effects 順序；待 joy 潤）；
    關著照舊一句（seal_effect_text）。"""
    if not revamp_on(content):
        return seal_effect_text(content, shard.effect)
    cfg = content.config.seal.revamp
    parts = [SEAL_POWER_TEXT.format(x=f"{cfg.power:g}")]
    for key in shard.effects:
        value = cfg.effects.get(key, 0.0)
        parts.append(SEAL_REVAMP_TEXT.get(key, "").format(x=f"{value:g}", n=f"{value:g}"))
    return "、".join(part for part in parts if part)


def _cells(state: GameState, content: Content, source: str | None = None) -> list[tuple[str, float]]:
    """身上每一格寶物的（效果鍵, 數字）：一般那一格看寶物的開關（PlayerState.treasure：Config.treasures.enabled、查
    Config.treasures.effects）；傳承那一格只看 Config.seal.enabled 與 content/seal.json（PlayerState.heirloom，查 Config.seal.effects，
    玉璽碎片設計 7.2），其他掛點都不用動。所以寫成一格一格往清單裡加，不在一般那一格空著時提早回傳。
    改版開著（revamp_on）時傳承那一格換成改版的效果：這一片 effects 的每一個鍵各一格，數字查 Config.seal.revamp.effects
    （玉璽碎片改版第三章；螭首、金角的舊效果因此不給）。source："treasure" 只算一般那一格、"heirloom" 只算傳承那一格、None 兩格都算
    （求見門檻的折抵要分開寫名字，rules.audience_parts）。"""
    cells: list[tuple[str, float]] = []
    key = effect_of(content, state.player.treasure) if on(content) and source != "heirloom" else None
    if key is not None:
        cells.append((key, content.config.treasures.effects.get(key, 1.0 if key in MULTIPLY else 0.0)))
    heir = state.player.heirloom  # 傳承那一格（玉璽碎片設計 7.2）：只看 Config.seal.enabled 與內容的七片，不看寶物的開關
    shard = content.seal.get(heir.template) if heir is not None and heir.template and content.config.seal.enabled else None
    if shard is not None and source != "treasure":
        if revamp_on(content):
            table = content.config.seal.revamp.effects
            cells += [(k, table.get(k, 1.0 if k in MULTIPLY else 0.0)) for k in shard.effects]
        else:
            cells.append((shard.effect, content.config.seal.effects.get(shard.effect, 1.0 if shard.effect in MULTIPLY else 0.0)))
    return cells


def amount(state: GameState, content: Content, effect: str, source: str | None = None) -> float:
    """這個效果此刻的數字（設計 6.1：所有掛點都經過這裡）：乘的效果是倍數（沒有是 1）、加的是加多少（沒有是 0）；
    好幾格都是同一個鍵時乘的相乘、加的相加（玉璽碎片設計 7.2）。沒帶、開關關著、效果對不上都回中性值。source 見 _cells。"""
    multiply = effect in MULTIPLY
    total = 1.0 if multiply else 0.0
    for key, value in _cells(state, content, source):
        if key == effect:
            total = total * value if multiply else total + value
    return total


def power_scale(state: GameState, content: Content) -> float:
    """持有者本人的戰力倍數（玉璽碎片改版第三章：每片都是 ×Config.seal.revamp.power，乘在 team.player_boost 的 factor）：
    改版開著、傳承那一格有內容認得的碎片才是那個數，不然 1（同伴、部下不經過這裡）。"""
    heir = state.player.heirloom
    if heir is None or not heir.template or heir.template not in content.seal or not revamp_on(content):
        return 1.0
    return content.config.seal.revamp.power


def heirloom_name(state: GameState) -> str:
    """傳承那一格的名字（求見門檻的折抵寫碎片的名字，rules.audience_parts）；沒有是「玉璽碎片」。"""
    heir = state.player.heirloom
    return heir.name if heir is not None else "玉璽碎片"


def audience_name(state: GameState) -> str:
    """求見門檻被寶物抵掉時寫給玩家看的名字（名聲設計 6.3，rules.audience_parts）：身上那件寶物的名字；沒有寫「寶物」。"""
    item = state.player.treasure
    return item.name if item is not None else "寶物"


def extra_drop(state: GameState, content: Content, dropped: list[str], season: int, record_id: int) -> str | None:
    """寶物「打贏多掉一個素材」（設計 6.2）：這一場掉了素材時，win_material 的機率從這一場**實際掉到的**素材裡挑一種、多給一個
    （計畫「要 PM 定的」第 3 條甲）；回那一種的 id，沒中、沒帶、開關關著、這一場沒掉素材都是 None（不擲）。只在遊歷、探索野怪、
    序章外由 Game._battle_rewards 叫（挑戰本人、劇情戰不吃）。發素材是 engine 的事（treasures 不 import materials）。
    自己一份亂數（寶|素材|季數|名號|戰報流水號；流水號每季從 1 算起，所以要有季數；開頭的「素材」跟挑戰本人掉寶物那一份分開），
    不碰 Game.rng（FB-129）。"""
    chance = amount(state, content, "win_material")
    if chance <= 0 or not dropped:
        return None
    rng = random.Random(f"寶|素材|{season}|{state.player.name}|{record_id}")
    if rng.random() >= chance:
        return None
    return rng.choice(list(dict.fromkeys(dropped)))  # 照掉落的順序去重：同一種掉兩筆不加重


def owned_templates(p: PlayerState) -> set[str]:
    """手上已經有的（6.5：身上的寶物與坐騎、裝備庫、寄放的都算，照 template 認）。"""
    items = [p.treasure, p.mount, *p.rack, *p.held_gear]
    return {item.template for item in items if item is not None and item.template}


def refresh_names(p: PlayerState, content: Content) -> None:
    """讀檔時照內容重寫名字（設計 3.1：名字照 template 從內容讀，joy 改名不動存檔）：身上的寶物與坐騎、裝備庫、寄放的每一件有
    template 的，name 改成 content/gear.json 的名字；內容拿掉了就留著舊名字當備份。Game._drop_stale_references 每次建 Game 都叫，
    所以 item.name 永遠是內容的名字——equipment.store／wield 的三句、mounts.name_of、馬市的鈕都不用改。"""
    book = content.gear
    for item in (p.treasure, p.mount, *p.rack, *p.held_gear):
        if item is None or not item.template:
            continue
        found = book.treasures.get(item.template) if item.slot == "treasure" else book.steeds.get(item.template)
        if found is not None:
            item.name = found.name


def new_treasure(state: GameState, content: Content, tid: str) -> Equipment:
    """新的一件寶物（四欄共用的流水號 +1，id「寶:N」）：名字照寶物表，不分階品。"""
    return Equipment(id=equipment.next_id(state, "treasure"), slot="treasure", name=content.gear.treasures[tid].name, template=tid)


def new_steed(state: GameState, steed: SteedDef) -> Equipment:
    """新的一匹名駒（5.7：三階、專名，品質照內容）：走裝備二的 mounts.new_mount（「裝備三的良駒、名駒也從這裡開」，之後它多了
    預設欄位〔例如飽足〕兩邊才不會走樣），再補上 template（名駒的 id）。"""
    item = mounts.new_mount(state, name=steed.name, tier=3, quality=steed.quality)
    item.template = steed.id
    return item


def good_horse(state: GameState, content: Content, rng: random.Random) -> Equipment:
    """一匹良駒（5.7；懸賞的重賞與奇遇）：毛色照那一筆的種子挑（5.6），品質照 Config.treasures.horse_quality 的權重（下 50／中 30／上 20）。
    先抽毛色、再抽品質（順序不能換，不然同一筆擲出來的馬會變）。"""
    coat = rng.choice(mounts.COATS)
    table = content.config.treasures.horse_quality
    quality = rng.choices(list(table), weights=list(table.values()))[0]
    return mounts.new_mount(state, name=mounts.horse_name(coat, 2), tier=2, quality=quality)


def pick_pool(state: GameState, content: Content, rng: random.Random) -> str | None:
    """從掉落池抽一件你還沒有的（6.5，照 template 認；排序後再抽，同一個種子永遠同一件）；都有了是 None。"""
    have = owned_templates(state.player)
    left = sorted(t.id for t in content.gear.treasures.values() if t.pool and t.id not in have)
    return rng.choice(left) if left else None


def room_for(state: GameState, content: Content, slot: str) -> bool:
    """拿得下這一欄的新東西（2.2）：身上這一欄空著，或裝備庫（四欄合算）還有空位——就是 equipment.rack_full 的反面。
    閉關中拿到的寶物照一般的規則（企劃者 2026-10-11 拿掉了先放裝備庫的例外）。"""
    return not equipment.rack_full(state, content, slot)


def deliver(state: GameState, content: Content, item: Equipment, *, hold: bool = False) -> list[str]:
    """拿到一件（2.2、6.5）：拿得下就照 equipment.store（那一欄空著穿上，否則進裝備庫）；拿不下時 hold（懸賞的重賞、名將贈禮）
    寄放進 held_gear，不然（奇遇、挑戰本人）寫明帶不走。"""
    p = state.player
    if room_for(state, content, item.slot):
        return [equipment.store(state, item)]
    if hold:
        p.held_gear.append(item)
        return [HELD.format(name=item.name)]
    return [NO_ROOM.format(name=item.name)]


def deliver_held(state: GameState, content: Content) -> list[str]:
    """寄放的東西補發（6.5；Game._deliver_held_gear 同步與快轉時叫）：那一欄開著、拿得下就照 2.2 補（那一欄空著就穿上，否則進
    裝備庫），一次補到裝備庫滿為止，補不完的（與那一欄關著的）留著。閉關中也補（計畫「要 PM 定的」第 4 條：寶物閉關中本來就能換）。"""
    p = state.player
    if not p.held_gear:
        return []
    lines: list[str] = []
    kept: list[Equipment] = []
    for item in p.held_gear:
        if equipment.on(content, item.slot) and room_for(state, content, item.slot):
            lines += [HELD_ARRIVED.format(name=item.name), equipment.store(state, item)]
        else:
            kept.append(item)
    p.held_gear = kept
    return lines


def _silver(state: GameState, content: Content, line: str) -> list[str]:
    """改給 dup_silver 兩（6.5）：那一句加「銀兩 +N」。"""
    n = content.config.treasures.dup_silver
    state.player.stats["silver"] = state.player.stats.get("silver", 0) + n
    return [line, f"銀兩 +{n}"]


def _give_horse(state: GameState, content: Content, rng: random.Random, *, hold: bool, got: list[str] | None = None) -> list[str]:
    """got 給了就把戰報「得失」那一格的字（HORSE_GAIN_LINE）接上去（出陣，FB-430）。"""
    item = good_horse(state, content, rng)
    if got is not None:
        got.append(HORSE_GAIN_LINE.format(name=item.name))
    return [GOT_HORSE.format(grade=mounts.grade(item), name=item.name), *deliver(state, content, item, hold=hold)]


def _give_pool(state: GameState, content: Content, rng: random.Random, *, hold: bool, got: list[str] | None = None) -> list[str]:
    """從掉落池給一件你還沒有的；都有了改給銀兩。呼叫端（不寄放的）先確認拿得下。got 給了就把「得失」那一格的字接上去（FB-430）。"""
    tid = pick_pool(state, content, rng)
    if tid is None:
        return _silver(state, content, ALL_OWNED.format(silver=content.config.treasures.dup_silver))
    item = new_treasure(state, content, tid)
    if got is not None:
        got.append(GAIN_LINE.format(name=item.name))
    effect = effect_text(content, content.gear.treasures[tid].effect)
    return [GOT.format(name=item.name, effect=effect), *deliver(state, content, item, hold=hold)]


def grant_effect(state: GameState, content: Content, gear_id: str, season: int) -> list[str]:
    """奇遇（6.4：Effect.gear，rules.apply_effect 叫）：寫的是掉落池的一件寶物、或 good_horse（一匹良駒）。那一欄關著什麼都不做；
    手上已經有同一件寶物改給 dup_silver 兩（6.5）；良駒照給（不是一人一件）；當下拿不了就沒了、寫明帶不走、不佔流水號（不寄放）。
    良駒的毛色與品質用自己一份亂數（季數＋名號＋good_horse＋四欄共用的流水號），不碰 Game.rng。"""
    p = state.player
    if gear_id == GOOD_HORSE:
        if not mounts.on(content):
            return []
        if not room_for(state, content, "mount"):
            return [NO_ROOM.format(name=mounts.TIER_NAMES[2])]
        rng = random.Random(f"奇遇|{season}|{p.name}|{gear_id}|{p.weapon_serial}")
        return _give_horse(state, content, rng, hold=False)
    tdef = content.gear.treasures.get(gear_id)
    if tdef is None or not on(content):
        return []
    if gear_id in owned_templates(p):
        return _silver(state, content, DUP.format(name=tdef.name, silver=content.config.treasures.dup_silver))
    if not room_for(state, content, "treasure"):
        return [NO_ROOM.format(name=tdef.name)]
    item = new_treasure(state, content, gear_id)
    return [GOT.format(name=item.name, effect=effect_text(content, tdef.effect)), *deliver(state, content, item)]


# ---- 看得到（2.5）：修練頁每一列、角色卡那一行、寄放著哪幾件 ----

def _row(content: Content, item: Equipment) -> dict:
    """修練頁寶物那一段的一列：名字、效果（effect 是鍵、effect_text 是給人看的那一句）。寶物隨時能換（2.3【定】），沒有「能不能換」
    的旗標；寶物不能拆，沒有拆解。"""
    key = effect_of(content, item)
    return {"id": item.id, "name": item.name, "effect": key or "", "effect_text": effect_text(content, key) if key else LOST}


def rows(state: GameState, content: Content) -> dict:
    """修練頁的寶物那一段（skillview.gear_rows）：身上那件、裝備庫裡的寶物（寶物的開關關著時 worn 是 None、rack 是空的），
    加上傳承那一列 heirloom（玉璽碎片的抄本，只看 Config.seal.enabled；不能換下、沒有鈕）。"""
    p = state.player
    heir = p.heirloom if content.config.seal.enabled and p.heirloom is not None and p.heirloom.template in content.seal else None
    out = {"worn": None, "rack": [], "heirloom": None}
    if heir is not None:
        shard = content.seal[heir.template]
        out["heirloom"] = {"id": heir.id, "name": heir.name, "effect": shard.effect, "effect_text": heirloom_text(content, shard)}
    if on(content):
        out["worn"] = _row(content, p.treasure) if p.treasure is not None else None
        out["rack"] = [_row(content, t) for t in equipment.in_slot(p, "treasure")]
    return out


def rack_note(state: GameState, content: Content) -> str:
    """修練頁寶物那一段底下那一行（FB-180）：寶物開著照舊寫 RACK_NOTE；身上有傳承時多 HEIRLOOM_NOTE（「隨時能換」不包括它）；
    寶物關著、只有傳承那一列時只寫 HEIRLOOM_NOTE。"""
    heir = rows(state, content)["heirloom"] is not None
    if not on(content):
        return HEIRLOOM_NOTE if heir else ""
    return RACK_NOTE + (HEIRLOOM_NOTE if heir else "")


def card_line(state: GameState, content: Content) -> str:
    """本人卡上的「寶物」那一行（2.5，待 joy 潤）：「寶物　【烏木名刺】求見門檻 −3」，沒帶或開關關著不寫；加上傳承那一行
    「傳承　【雲篆】練成的心得 ×0.9」（玉璽碎片設計第十節：只看 Config.seal.enabled 與 content/seal.json，不看寶物的開關）。
    兩行都有時用換行接；都沒有是空字串。"""
    lines = []
    item = state.player.treasure
    if item is not None and on(content):
        key = effect_of(content, item)
        lines.append(f"寶物　【{item.name}】{effect_text(content, key) if key else LOST}")
    heir = state.player.heirloom
    shard = content.seal.get(heir.template) if heir is not None and heir.template and content.config.seal.enabled else None
    if shard is not None:
        lines.append(f"{HEIRLOOM_LABEL}　【{heir.name}】{heirloom_text(content, shard)}")
    return "\n".join(lines)


def held_note(state: GameState) -> str:
    """修練頁「裝備」塊底下那一行（寄放著哪幾件，6.5）；沒有寄放的是空字串。"""
    held = state.player.held_gear
    return HELD_NOTE.format(names="、".join(f"【{item.name}】" for item in held)) if held else ""


# ---- 懸賞的重賞（6.4）----

def prize_on(content: Content, prize: str | None) -> bool:
    """這一種重賞的那一欄開著沒（寶物看寶物、良駒看坐騎）。"""
    return prize is not None and equipment.on(content, PRIZE_SLOTS.get(prize, ""))


def bounty_prize(state: GameState, content: Content, season: int, bounty_id: str, prize: str, issuer: str) -> list[str]:
    """懸賞的重賞（6.4）：第一個交差的人拿（bounties._complete 判）。哪一件寶物、良駒的毛色與品質到這一刻才定，用自己一份亂數
    （季數＋名號＋懸賞 id；季數一定要有：懸賞 id 每季從 b1 算起、選項 id 在網頁上看得到，少了季數，記下哪幾號中過、下一季就專挑那幾張），不碰 Game.rng。寶物只抽你還沒有的，
    都有了改給銀兩；裝備庫滿了寄放（held_gear），不作廢。那一欄關著什麼都不給。"""
    if not prize_on(content, prize):
        return []
    rng = random.Random(f"bounty-prize|{season}|{state.player.name}|{bounty_id}")
    head = [PRIZE_GOT.format(issuer=issuer)]
    if prize == "horse":
        return head + _give_horse(state, content, rng, hold=True)
    return head + _give_pool(state, content, rng, hold=True)


def arena_prize(state: GameState, content: Content, season: int, place: int) -> list[str]:
    """擂台季末前幾名的寶物（ArenaTuning.prize_treasure；休季同步時 Game._deliver_arena 補）：掉落池裡你還沒有的一件，都有了換銀兩；
    裝備庫滿了寄放。亂數用自己的（季數＋名號＋名次），不碰 Game.rng。寶物關著什麼都不給。"""
    if not on(content):
        return []
    return _give_pool(state, content, random.Random(f"arena-prize|{season}|{state.player.name}|{place}"), hold=True)


# ---- 名將贈禮（6.4）----

def gifts_due(state: GameState, content: Content, present: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """名將贈禮（6.4）：跟哪一位名將的情誼到了 gift_affinity、這一季他還沒送過人（WorldState.general_gifts），就把贈禮交給你，記下給了誰
    （呼叫端那一下動作最後 _save_season 存回去）。贈禮是名駒時看坐騎的開關、是寶物時看寶物的開關；那一欄關著不送也不記（開了之後
    照樣送得出去）。裝備庫滿了寄放。名將贈禮與名駒本來就一人一件（6.5），不用查重複。Game.choose／answer_event 最後各叫一次：
    情誼從對話、事件、隨口應對來都走得到。present 是此刻站在你身邊的人物：他在就當面交給你，不在就託人送來（FB-139）。"""
    p, w, cfg = state.player, state.world, content.config.treasures
    lines: list[str] = []
    for gift in content.gear.gifts:
        if gift.character in w.general_gifts or p.affinities.get(gift.character, 0) < cfg.gift_affinity:
            continue
        steed = content.gear.steeds.get(gift.gear)
        if not equipment.on(content, "mount" if steed is not None else "treasure"):
            continue
        w.general_gifts[gift.character] = p.name
        item = new_steed(state, steed) if steed is not None else new_treasure(state, content, gift.gear)
        general = content.characters[gift.character].name
        line = (gift.line or GIFT_LINE) if gift.character in present else GIFT_SENT_LINE
        lines.append(line.format(general=general, gift=item.name))
        lines += deliver(state, content, item, hold=True)
    return lines


# ---- 挑戰本人掉落（6.4）----

def _week(state: GameState, content: Content) -> int:
    return calendar.point(state.world.time, content, state.world).week


def week_full(state: GameState, content: Content) -> bool:
    """這一週（季曆）挑戰本人掉的寶物到了 Config.figure_treasure_weekly 件（0＝不設，週末與 14 天的季）。"""
    weekly = content.config.figure_treasure_weekly
    return bool(weekly) and state.player.treasure_weeks.count(_week(state, content)) >= weekly

def challenge_drop(state: GameState, content: Content, figure: str, season: int, record_id: int) -> tuple[Equipment | None, list[str]]:
    """打贏大勢人物本人（Game._challenge 打贏那一支、_rout 之後）：challenge_chance 掉一件掉落池裡你還沒有的寶物（都有了改給銀兩）。
    同一位人物對同一個人每季只掉一次（treasure_drops），一人一季最多 figure_treasure_cap 件（挑戰每季都有設計丁 (c)，叛投不清）；
    寶物關著、掉過、到了上限、裝備庫滿了（寶物欄有東西、裝備庫也滿）都不擲，也不記
    「掉過」——騰出空位之後再打贏還有機會。自己一份亂數（季數＋名號＋戰報流水號；流水號每季從 1 起，所以要有季數），不碰 Game.rng。
    回（掉出來的那一件, 江湖紀錄的話）；換成銀兩時那一件是 None。"""
    p, cfg = state.player, content.config.treasures
    cap = content.config.figure_treasure_cap  # 丁 (c)：挑戰本人掉的寶物一人一季最多幾件（照 treasure_drops 的長度；0＝不設）
    if not on(content) or figure in p.treasure_drops or not room_for(state, content, "treasure") or (cap and len(p.treasure_drops) >= cap):
        return None, []
    if week_full(state, content):  # 每週上限（21 天季，正式季整合 3.8）：到了不擲、也不記掉過
        return None, []
    rng = random.Random(f"寶|{season}|{p.name}|{record_id}")
    if rng.random() >= cfg.challenge_chance:
        return None, []
    p.treasure_drops.add(figure)
    p.treasure_weeks.append(_week(state, content))
    tid = pick_pool(state, content, rng)
    if tid is None:
        return None, _silver(state, content, ALL_OWNED.format(silver=cfg.dup_silver))
    item = new_treasure(state, content, tid)
    who = content.figures[figure].name if figure in content.figures else figure
    return item, [DROP_LINE.format(who=who, name=item.name), *deliver(state, content, item)]


# ---- 出陣攻打贏的稀有掉落（正式季整合 2.6，第 4 批）----

SORTIE_TREASURE = "敵陣裡翻出一件好東西。"  # 待 joy 潤：出陣掉寶物那一句（接著 GOT）
SORTIE_HORSE = "敵將棄下的坐騎還繫在營外。"  # 待 joy 潤：出陣掉良駒那一句（接著 GOT_HORSE）


def sortie_rare(state: GameState, content: Content, season: int, record_id: int) -> tuple[list[str], list[str], int]:
    """出陣攻打贏另擲寶物與良駒（2.6；Config.sortie）：寶物從挑戰本人的掉落池抽你還沒有的（都有了換銀兩），帳另記一本
    （PlayerState.sortie_treasures，一季 treasure_cap 件，不讀挑戰本人的額度）；良駒一季 horse_cap 匹。那一欄關著、到了上限、
    裝備庫滿了都不擲也不記。自己一份亂數（出陣稀有|季數|名號|戰報流水號|用途），不碰 Game.rng。
    回（江湖紀錄的話, 戰報「得失」那一格的字〔寶物【X】、良駒【X】，FB-430〕, 掉落池都有了換的銀兩〔算進得失的銀兩，FB-434〕）。"""
    p, cfg = state.player, content.config.sortie
    silver = p.stats.get("silver", 0)
    lines: list[str] = []
    gains: list[str] = []
    seed = f"出陣稀有|{season}|{p.name}|{record_id}"
    if (on(content) and p.sortie_treasures < cfg.treasure_cap and room_for(state, content, "treasure")
            and random.Random(seed + "|寶物").random() < cfg.rare_treasure):
        p.sortie_treasures += 1
        lines += [SORTIE_TREASURE, *_give_pool(state, content, random.Random(seed + "|寶物抽"), hold=False, got=gains)]
    if (equipment.on(content, "mount") and p.sortie_horses < cfg.horse_cap and room_for(state, content, "mount")
            and random.Random(seed + "|良駒").random() < cfg.rare_horse):
        p.sortie_horses += 1
        lines += [SORTIE_HORSE, *_give_horse(state, content, random.Random(seed + "|良駒抽"), hold=False, got=gains)]
    return lines, gains, p.stats.get("silver", 0) - silver


# ---- 機器人（設計第九節）：整季機器人與伺服器假人共用 ----

# 挑寶物的固定順序：打仗拿得多的先（打贏經驗、心得，再來修練、悟意境、打贏多掉素材、破境丹）；機器人不閉關，閉關排最後
# （裝備四欄第九節「有好幾件時照固定順序挑一件，不每步換」）
BOT_ORDER = ("win_exp_pct", "win_xinde_pct", "cultivate", "insight", "win_material", "legend", "audience", "seclusion")


def wanted(state: GameState, content: Content) -> str | None:
    """裝備庫裡有照 BOT_ORDER 比身上排得前面的寶物就回它的 id（同一順位照 id），不然 None；寶物關著也是 None。寶物不設限制
    （2.3【定】），不看日界、不看閉關：身上已經是排最前面的就回 None，所以不會每步換。效果認不出來的（內容拿掉了）排最後。"""
    p = state.player
    if not on(content):
        return None

    def rank(item: Equipment) -> int:
        key = effect_of(content, item)
        return BOT_ORDER.index(key) if key in BOT_ORDER else len(BOT_ORDER)

    best = min(equipment.in_slot(p, "treasure"), key=lambda t: (rank(t), t.id), default=None)
    if best is None or (p.treasure is not None and rank(best) >= rank(p.treasure)):
        return None
    return best.id
