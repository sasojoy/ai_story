"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」；Config.bounties）。

- 官軍、黃巾每週一 00:00（季曆；第一季走 world.WEEK_HOOKS、規則關著的季走 tick，都叫 issue）各自動掛討伐兩張、打探、護送各一張（Config.bounties.kinds）：討伐是到指定的地方遊歷、
  打贏一場對頭陣營的隊伍；打探是到指定的地方探索一次；護送是在起點的城鎮接下、走到終點的城鎮。掛 auto_weeks 週，過期的下榜。
- 投靠了陣營的人可以在玩家卡上花銀兩通緝一個敵對陣營的人（押金就是賞金）；接了通緝的人在卡上對他「截殺」，照截殺的規則打，
  打贏就完成。沒人完成就在 post_weeks 週後下榜，押金在掛單的人下次同步時退回（deliver_refunds）。
- 散人兩邊的都能接，陣營的人只能接自己陣營的（can_take）；接了才算，一個人同時最多接 max_taken 張。
  前 quota 個完成的人各拿一份：銀兩（遊俠名號到第 4 階的散人另有加成）與經驗，散人另記俠名（ranger.add_deeds）。
- 求藝、求兵（懸賞榜設計第四節）：劇本的每個陣營（官軍、黃巾、地方豪強）每週一各掛一張求藝（交一門指定屬性、合成出來的武學或內功）、
  一張求兵（交一把指定種類與屬性的兵器）。不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前 give_quota 個交的有賞；
  散人三方都能交，陣營的人只交自己陣營的、拿全額。

每季都有（企劃者 2026-10-10「整個懸賞榜每季都有」，懸賞榜設計 2.2）：只看 Config.bounties.enabled、劇本有沒有陣營、這一季收了沒有（active），
不看第一季開關；關著時每個函式都什麼都不做、回空的。
過了期限只有一個問法（past_due，FB-152、FB-153）：這一季收了，榜上的一律算過了；寫「到季末」的單撐到季真的收了；其他的照自己的期限。
只改 GameState（玩家與共用的季）；不 import engine、world（world 會 import 這裡，掛 WEEK_HOOKS）。"""
from __future__ import annotations

import math
import random
from typing import NamedTuple

from . import calendar, equipment, gender, library, materials, ranger, roster, team, treasures, weapons
from .characters import name_key
from .martial_arts import QUALITIES
from .models import WEAPON_KINDS, Content, Location
from .state import Bounty, GameState, Weapon, WorldState
from .world_state import WorldStateStore, season_length_days

KIND_NAMES = {"strike": "討伐", "scout": "打探", "escort": "護送", "wanted": "通緝", "art": "求藝", "arms": "求兵"}
GIVE_KINDS = ("art", "arms")  # 求藝、求兵：不用揭，在懸賞榜上直接交（懸賞榜設計第四節）
FULL_PAY = ("wanted", "art", "arms")  # 陣營的人也拿全額的（通緝是押金照數給；求藝、求兵企劃者 2026-10-10 定）
NO_TAKE = "這一張不用揭，在懸賞榜上直接交。"  # 待 joy 潤
NOT_NOW = "（此刻無法這麼做。）"
GONE = "這張懸賞已經下榜了。"  # 待 joy 潤
ONLY_FUSED = "這一張要的是江湖上新合出來的功夫；基礎武學、師門傳下來的配方都不收。"  # 待 joy 潤（FB-158：師門配方也是自己在火爐合的，只寫「合成出來」會讓人以為合用）
GIVEN_PREFIX = "【懸賞】你把"
GIVEN = GIVEN_PREFIX + "【{name}】交給了{issuer}（{title}），賞銀送到。"  # 待 joy 潤：交出的第一行（取代 _complete 的「交差了」那一行）
EMPTY_HANDS = "你現在空著手。"  # 待 joy 潤：交的是手上那把
RACK_FULL_SILVER = "裝備庫滿了，那把{name}折成銀兩 {silver}。"  # 待 joy 潤：求藝送的兵器放不下
HAND_IN_VERBS = ("pick", "unpick", "give")  # 挑一件、回到懸賞榜、交出：江湖紀錄併成一則（Game.choose，懸賞榜設計 4.8）
UNITS = {"art": "門", "arms": "把"}
GIVE_YES = "交出"  # 待 joy 潤：確認層上那一顆（Option.confirm_yes）
STUCK = "這幾張你現在交不出：{titles}（求藝要江湖上新合出來的功夫、師門配方不算、不能是身上正在練的；求兵要種類與屬性都對得上的兵器）"  # 待 joy 潤
MORE = {  # 待 joy 潤：第三層只列最不值錢的 give_list 件（設計 4.4），多的收成這一行
    "art": "還有 {n} 門合用的沒列出來（列的是熔掉最不值錢的；要交別的，先把前面這幾門熔掉、改練或交掉）",
    "arms": "還有 {n} 把合用的沒列出來（列的是最不值錢的；要交別的，先把前面這幾把拆掉或交掉）",
}
WORN_NOTE = "【{name}】身上正在練，先改練別的才能交"  # 待 joy 潤
NAMING_NOTE = "【{name}】還等著定名，先替它定名"  # 待 joy 潤
UNPICK = "回到懸賞榜"  # 待 joy 潤：第三層最後一顆（bounty:unpick）
UNPICKED = "你回到懸賞榜前。"  # 待 joy 潤：按了 bounty:unpick 的回話（Game._bounty）
TEMPERED_NOTE = "淬煉過 {n} 次，賞銀不會多給。"  # 待 joy 潤：第三層交兵器的確認句
HELD_NOTE = "這是你手上那把，交了你就空手了。"  # 待 joy 潤：同上，交的是手上那把
HAVE = "你身上合用的："  # 待 joy 潤：懸賞卡那一列（have_text）；fitting 連手上那把兵器也算，所以寫「身上」不寫「庫裡」
NOT_YOURS = "這一張不是給你的。"  # 待 joy 潤；fit_problem 的拒絕句（設計 4.5）都寫成常數，測試引用常數，潤字不必改測試
GIVEN_BEFORE = "這一張你已經交過了。"  # 待 joy 潤
NO_ART = "你的功法庫裡沒有這一門。"  # 待 joy 潤
WORN_ART = "身上正在練的不能交，先改練別的。"  # 待 joy 潤
UNNAMED = "先替它定名，再談交出去。"  # 待 joy 潤
NO_DATA = "找不到它的資料。"  # 待 joy 潤
WANT_ART = "這一張要屬{attribute}的。"  # 待 joy 潤
NO_WEAPON = "裝備庫裡沒有這一件。"  # 待 joy 潤
ORIGINAL_KEPT = "神器的原品交不得"  # 待 joy 潤（打造隱藏配方設計 5.4：手上那把也不收）
ONLY_ORIGINAL = "（你身上對得上的只有神器的原品，原品交不得）"  # 待 joy 潤：灰掉那一行裡、只有原品對得上的那一張後面（FB-145）
WANT_ARMS = "這一張要屬{attribute}的{noun}。"  # 待 joy 潤（noun 照 _noun）
ART_GIFTS = "・素材，偶有兵器"  # 待 joy 潤：求藝的賞那一段最後（兵器關著只寫「・素材」）
ENEMY = {"guan": "huang", "huang": "guan"}  # 自動掛單的兩個陣營與他們的對頭（同軍令）
BOARD = "懸賞榜"
SEASON_END = "到季末"  # 待 joy 潤：期限到季末或過了季末時寫這個（due_text）
LAPSED_FULL = "【懸賞】「{title}」名額被別人交滿了，你手上這一張作廢。"  # 待 joy 潤（FB-121 第 5 件，deliver_lapses）
LAPSED_DUE = "【懸賞】「{title}」過了期限，你手上這一張作廢。"  # 待 joy 潤
LAPSED_SEASON = "【懸賞】這一季收了，你手上「{title}」作廢。"  # 待 joy 潤（FB-152、FB-153：寫「到季末」的單撐到季真的收了；收季那一刻手上揭著的都補這一句，第 11、12 週掛的一樣）
LAPSED_SIDE = "【懸賞】你改投{faction}，手上「{title}」是別的陣營掛的，這一張作廢。"  # 待 joy 潤（FB-151：投靠、叛投那一下；換版前就換了陣營的存檔由 deliver_lapses 補同一句）
STRANDED_JOIN = "投靠之後，手上 {n} 張別的陣營掛的懸賞會作廢。"  # 待 joy 潤（FB-151：投靠的確認畫面）
STRANDED_LOST = "手上 {n} 張{faction}掛的懸賞作廢"  # 待 joy 潤（FB-151：叛投確認畫面「會失去」清單裡的一項，faction 是舊陣營）
WANTED_NEWBIE = "你初入江湖，還在新手期，截殺不了人，這張通緝先別揭。"  # 待 joy 潤（FB-154：揭的人自己還在截殺的新手期；跟 post_problem 的「…初入江湖，還在新手期，通緝不了他。」同一個口氣）
HELD_FULL = "你手上已經有 {count} 張了，先交了差再說。"  # 待 joy 潤（FB-155：count 是手上真的有幾張，不是上限；截殺關了又開時可以超過上限）
BOARD_EMPTY = "榜上的懸賞都有人交了。"  # 待 joy 潤（FB-156：榜開著、看得到的單被別人交光，第二層只剩「返回」時灰掉的那一行；Game._bounty_options 的 bounty:empty）


def active(state: GameState, content: Content) -> bool:
    """懸賞榜開著：設定開著（Config.bounties.enabled）、劇本有陣營（沒有陣營就沒有人掛單）、這一季還沒收（休季沒有榜：不開榜、不掛單、
    卡上沒有通緝鈕，FB-152）。不看第一季開關（懸賞榜設計 2.2）。作廢與退押金（deliver_lapses、deliver_refunds）不問這一個：
    收季之後揭著的人、掛單的人同步時才收到那一句與押金。"""
    return content.config.bounties.enabled and bool(content.scenario.factions) and not state.world.ended


def is_town(content: Content, loc_id: str) -> bool:
    loc = content.locations[loc_id]
    return content.config.explore_mix_of(loc.tags).kind == "town"


def board_here(state: GameState, content: Content) -> bool:
    """這裡看得到懸賞榜：懸賞榜開著（active）、人在城鎮類的地點。"""
    return active(state, content) and is_town(content, state.player.location)


def week_seconds(state: GameState, content: Content) -> float:
    return calendar.WEEK / calendar.cal_scale(content, state.world)


def quota(content: Content) -> int:
    cfg = content.config
    return max(cfg.bounties.quota_min, math.ceil(cfg.bounties.quota_base * cfg.server_max_players / 100))


def _loc_name(content: Content, loc_id: str | None) -> str:
    return content.locations[loc_id].name if loc_id in content.locations else ""


def _noun(b: Bounty) -> str:
    """求兵要的那一種兵器寫成玩家看的字：照 weapons.NOUNS（拳腳寫「拳套」、弓弩寫「弩」，跟兵器名、鐵匠鋪挑種類那一步同一套；
    「一把屬剛的拳腳」不通）。FB-133（同一把一下寫拳套、一下寫拳腳）還沒定案，joy 定了另一種寫法就改這裡。"""
    return weapons.NOUNS.get(b.weapon_kind or "", b.weapon_kind or "")


def title(content: Content, b: Bounty) -> str:
    """短標題：「討伐・黃巾游騎（南陽郊野）」「打探・嵩山深處」「護送・新野→宛城」「通緝・某某」「求藝・剛」「求兵・屬柔的劍」。"""
    kind = KIND_NAMES.get(b.kind, b.kind)
    if b.kind == "art":
        return f"{kind}・{b.attribute}"
    if b.kind == "arms":
        return f"{kind}・屬{b.attribute}的{_noun(b)}"
    if b.kind == "strike":
        return f"{kind}・{_loc_name(content, b.location)}的{_enemy_name(content, b)}"
    if b.kind == "escort":
        return f"{kind}・{_loc_name(content, b.location)}→{_loc_name(content, b.end)}"
    if b.kind == "wanted":
        return f"{kind}・{b.target}"
    return f"{kind}・{_loc_name(content, b.location)}"


def how(content: Content, b: Bounty) -> str:
    """怎麼完成（一句）。"""
    if b.kind == "strike":
        return f"到{_loc_name(content, b.location)}遊歷，打贏一場{_enemy_name(content, b)}的隊伍"
    if b.kind == "scout":
        return f"到{_loc_name(content, b.location)}探索一次"
    if b.kind == "escort":
        return f"在{_loc_name(content, b.location)}接下，走到{_loc_name(content, b.end)}"
    if b.kind == "art":  # 待 joy 潤
        return f"在城鎮的懸賞榜交出一門屬{b.attribute}、合成出來的武學或內功（交了就沒了）"
    if b.kind == "arms":  # 待 joy 潤；手上那把也收（企劃者 2026-10-10，懸賞榜設計 14.1 丙）
        return f"在城鎮的懸賞榜交出一把屬{b.attribute}的{_noun(b)}（裝備庫裡、手上的都行，什麼品質都收，交了就沒了）"
    return f"找到{b.target}，在對方的玩家卡上截殺並打贏"


def _enemy_name(content: Content, b: Bounty) -> str:
    return content.scenario.faction_name(ENEMY.get(b.faction or "")) or "敵軍"


def issuer(content: Content, b: Bounty) -> str:
    return content.scenario.faction_name(b.faction) or "江湖"


def _left(b: Bounty) -> int:
    return b.quota - len(b.done_by)


def to_season_end(b: Bounty, content: Content, world: WorldState) -> bool:
    """這一張的期限寫「到季末」：到期在名義季長（開季時蓋的章）或之後。第 11 週掛的正好到季末、第 12 週掛的在季末後一週。
    比的是名義季長，不是真正收季的時刻：第一季管理者可以把季末往後排（Game.admin_schedule），這種單要撐到季真的收了（past_due）。"""
    return b.expires >= season_length_days(world, content) * calendar.DAY - calendar.EPS_SECONDS


def past_due(b: Bounty, content: Content, world: WorldState) -> bool:
    """這一張過了期限（FB-152、FB-153）：所有看期限的地方都問這一個（open_bounties、post_problem、deliver_refunds、deliver_lapses、issue）。
    這一季收了（world.ended）一律算過了——第 11 週與第 12 週掛的一樣，不是一張「過了期限」、一張一直掛到下一季開；
    寫「到季末」的單（to_season_end）在季真的收之前都不算——管理者把季末往後排時，名義季末過了它也還在；其他的照自己的 expires。"""
    if world.ended:
        return True
    return not to_season_end(b, content, world) and b.expires <= world.time


def due_text(b: Bounty, content: Content, world: WorldState) -> str:
    """給玩家看的期限（懸賞榜設計 3.5）：第一季寫「第 5 週・週一 00:00」、規則關著寫「第11天 12:00」（calendar.stamp_text，跟 Game.stamp
    同一個寫法；這裡不能 import engine）。到季末或過了季末一律寫「到季末」（to_season_end）：規則關著時 stamp_text 不會夾，14 天的季第 11、12 週掛的單
    會寫成這一季沒有的「第15天 00:00」「第16天 04:00」。真正的 expires 不夾：懸賞榜是開下一季時才跟著 WorldState 整個重來；收季那一刻手上還揭著的單由 deliver_lapses 作廢（FB-152）。"""
    if to_season_end(b, content, world):
        return SEASON_END
    return calendar.stamp_text(b.expires, content, world)


def due_line(state: GameState, content: Content, b: Bounty) -> str:
    """「期限 第11天 12:00・名額還剩 2」：懸賞榜每一行、懸賞卡每一列、揭下的回話都寫它（FB-121 第 5 件）。待 joy 潤：寫法。"""
    return f"期限 {due_text(b, content, state.world)}・名額還剩 {_left(b)}"


def open_bounties(state: GameState, content: Content) -> list[Bounty]:
    """榜上還有效的（沒過期〔past_due〕、還有名額）；休季（active 為假）一張都沒有。截殺關著（Config.raid.enabled）時通緝不算：只能靠截殺交差，揭了也交不了
    （mine、take、hunting、status、整季機器人與假人都經過這裡，自然看不到、揭不了、不佔格）；押金照期限退（deliver_refunds 直接掃榜）。"""
    if not active(state, content):
        return []
    w, raids = state.world, content.config.raid.enabled
    return [b for b in w.bounties if not past_due(b, content, w) and _left(b) > 0 and (raids or b.kind != "wanted")]


def _takeable(name: str, faction: str | None, b: Bounty) -> bool:
    """name 這個人、投靠 faction（None 是散人）接不接得了這一張：can_take 與 stranded（換陣營之後還接不接得了）共用這一套。"""
    if b.kind == "wanted" and name_key(b.target or "") == name_key(name):
        return False
    if b.poster is not None and name_key(b.poster) == name_key(name):
        return False
    return faction is None or faction == b.faction


def can_take(state: GameState, b: Bounty) -> bool:
    """這個人接不接得了這一種：散人兩邊都能接；陣營的人只能接自己陣營的；通緝不能接自己的。"""
    p = state.player
    return _takeable(p.name, p.faction, b)


def stranded(state: GameState, content: Content, faction_id: str | None) -> list[Bounty]:
    """手上揭著、還沒交、還有效，可是投靠 faction_id 之後就接不了（同 can_take 的規則）的單（FB-151：投靠、叛投那一下要作廢的）。
    投靠的確認畫面、叛投的確認畫面用它數張數，drop_stranded 用它拿掉名字。過期的、名額滿的不算（open_bounties 已經濾掉；它們由 deliver_lapses 說原因，而陣營的原因排第一，所以一張又過期又接不了的單，說的是陣營那一句）；
    求藝、求兵沒人揭，不會在裡面。"""
    p = state.player
    me = name_key(p.name)
    return [
        b for b in open_bounties(state, content)
        if me in (name_key(t) for t in b.takers) and me not in (name_key(t) for t in b.done_by)
        and not _takeable(p.name, faction_id, b)
    ]


def drop_stranded(state: GameState, content: Content, faction_id: str | None) -> list[str]:
    """投靠或叛投 faction_id 的那一下（Game.choose、defection.defect）：手上新陣營接不了的單拿掉名字，每張回一句原因（FB-151）。
    改的是共用的季（takers），呼叫端的動作結束時存季（choose 的結尾統一存）。要在 p.faction 改之前或之後呼叫都行：只看名字與 faction_id。"""
    me = name_key(state.player.name)
    faction = content.scenario.faction_name(faction_id, "別的陣營")
    msgs: list[str] = []
    for b in stranded(state, content, faction_id):
        b.takers = [t for t in b.takers if name_key(t) != me]
        msgs.append(LAPSED_SIDE.format(faction=faction, title=title(content, b)))
    return msgs


def mine(state: GameState, content: Content) -> list[Bounty]:
    """我接了、還沒完成、還有效的；接了之後換了陣營、接不了的不算。"""
    name = name_key(state.player.name)
    return [
        b for b in open_bounties(state, content)
        if name in (name_key(t) for t in b.takers) and can_take(state, b)
    ]


def visible(state: GameState, content: Content) -> list[Bounty]:
    """這個人在懸賞榜上看得到的（FB-121 第 3 件）：手上揭了的，加上接得了（can_take）、自己還沒交過的。「懸賞榜（N 張）」的 N
    只算這些（0 張不畫那顆鈕：打開只有「返回」就是 FB 抱怨的事），榜上列的也是這些，所以 N 等於打開之後列出的張數。
    不查武學與兵器，所以不收 world。"""
    me = name_key(state.player.name)
    held = {b.id for b in mine(state, content)}
    return [
        b for b in open_bounties(state, content)
        if b.id in held or (can_take(state, b) and me not in (name_key(t) for t in b.done_by))
    ]


def take_problem(state: GameState, content: Content, b: Bounty) -> str | None:
    """「接下」按不按得下去（拒絕的話）。"""
    if b.kind in GIVE_KINDS:  # 不擋的話整季機器人會把它們揭滿 max_taken 的格子，擋掉討伐與打探（懸賞榜設計 4.3）
        return NO_TAKE
    p = state.player
    name = name_key(p.name)
    if name in (name_key(t) for t in b.done_by):
        return "這一張你已經交過差了。"
    if not can_take(state, b):
        return "這一張不是給你接的。"
    if b.kind == "wanted" and roster.raid_newbie(state, content):  # 通緝只能靠截殺交差，自己還在新手期就截殺不了（Game.raid_refusal）：揭了白佔一格（FB-154）
        return WANTED_NEWBIE
    held = len(mine(state, content))
    if held >= content.config.bounties.max_taken:
        return HELD_FULL.format(count=held)  # 寫手上真的有幾張，不是上限：截殺關了又開，通緝回到手上時會超過上限（FB-155）
    if b.kind == "escort" and p.location != b.location:
        return f"要在{_loc_name(content, b.location)}接。"
    return None


def reward_text(state: GameState, content: Content, b: Bounty) -> str:
    """賞的那一段（選單、懸賞卡、揭下的回話共用）：「賞銀 20・經驗 15・俠名 +3」。俠名只有散人看得到（ranger.active）。
    求藝多寫心得與「素材，偶有兵器」；求兵的銀兩照交的那一把，寫成一段範圍（每顆交出鈕上另寫實拿多少，懸賞榜設計 4.7）。"""
    cfg = content.config.bounties
    deeds = b.deeds if ranger.active(state, content) else 0
    exp = _exp(state, content, b)
    xinde = cfg.xinde.get(b.kind, 0)
    if b.kind == "arms":
        low, high = (_silver(state, content, b, base=price * cfg.arms_tier["1"])
                     for price in (min(cfg.arms_silver.values()), max(cfg.arms_silver.values())))
        silver = f"{low}～{high}（照品質，高階另加）"  # 待 joy 潤
    else:
        silver = str(_silver(state, content, b))
    text = f"賞銀 {silver}" + (f"・經驗 {exp}" if exp else "") + (f"・心得 {xinde}" if xinde else "") + (f"・俠名 +{deeds}" if deeds else "")
    if b.kind == "art":
        text += ART_GIFTS if content.config.weapons.enabled else "・素材"
    if b.prize and not b.done_by and treasures.prize_on(content, b.prize):  # 重賞（裝備四欄 6.4）：只給第一個交差的人，給出去了就不再寫
        text += treasures.PRIZE_NOTE.format(what=treasures.PRIZE_WORDS[b.prize])
    return text


def _share(state: GameState, content: Content, b: Bounty) -> float:
    """陣營的人做自己陣營掛的討伐、打探、護送只拿 faction_share；通緝的賞金是押金，照數給；求藝、求兵拿全額（FULL_PAY）。"""
    if b.kind in FULL_PAY or state.player.faction is None:
        return 1.0
    return content.config.bounties.faction_share


def _silver(state: GameState, content: Content, b: Bounty, base: int | None = None) -> int:
    """實拿的銀兩：這一張的 silver（求兵是 base：交的那一把的 arms_silver × arms_tier，懸賞榜設計 4.7）× 第 4 階散人的加成 × 陣營的成數。
    base 傳的是底數，還沒乘加成：不要在呼叫端先乘，不然會乘兩次。通緝照押金給。"""
    if b.kind == "wanted":
        return b.silver
    amount = b.silver if base is None else base
    return round(amount * ranger.bounty_factor(state, content) * _share(state, content, b))


def _exp(state: GameState, content: Content, b: Bounty) -> int:
    return round(content.config.bounties.exp.get(b.kind, 0) * _share(state, content, b))


def take(state: GameState, content: Content, bounty_id: str) -> list[str]:
    b = next((x for x in open_bounties(state, content) if x.id == bounty_id), None)
    if b is None:
        return ["這張懸賞已經揭下了。"]
    problem = take_problem(state, content, b)
    if problem is not None:
        return [problem]
    if name_key(state.player.name) not in (name_key(t) for t in b.takers):
        b.takers.append(state.player.name)
    return [f"你揭下了「{title(content, b)}」：{how(content, b)}。（{reward_text(state, content, b)}；{due_line(state, content, b)}）"]


def drop(state: GameState, content: Content, bounty_id: str) -> list[str]:
    name = name_key(state.player.name)
    for b in state.world.bounties:
        if b.id == bounty_id and name in (name_key(t) for t in b.takers):
            b.takers = [t for t in b.takers if name_key(t) != name]
            return [f"你把「{title(content, b)}」放回了榜上。"]
    return ["你手上沒有這一張。"]


def _complete(state: GameState, content: Content, world: WorldStateStore, b: Bounty, silver: int | None = None) -> list[str]:
    """交差：記進 done_by、拿掉 takers，發銀兩（silver 是求兵照那一把傳進來的底數，交給 _silver 乘加成）、經驗、散人的俠名；這一張有重賞、你是第一個交差的，另給重賞（treasures.bounty_prize）。"""
    p = state.player
    name = name_key(p.name)
    first = not b.done_by  # 重賞只給第一個交差的人（裝備四欄 6.4）：記進 done_by 之前看
    b.takers = [t for t in b.takers if name_key(t) != name]
    b.done_by.append(p.name)
    silver = _silver(state, content, b, base=silver)
    p.stats["silver"] = p.stats.get("silver", 0) + silver
    p.bounties_done += 1
    msgs = [f"【懸賞】「{title(content, b)}」交差了，{issuer(content, b)}的賞銀送到。", f"銀兩 +{silver}"]
    exp = _exp(state, content, b)
    if exp:
        msgs.append(f"經驗 +{exp}")
        msgs += team.add_team_exp(state, content, world, exp)
    deeds = ranger.add_deeds(state, content, b.deeds)
    if deeds:
        msgs.insert(2, f"俠名 +{deeds}")
    if b.prize and first:  # 哪一件到這一刻才定（季數＋名號＋懸賞 id 的亂數）；裝備庫滿了寄放
        msgs += treasures.bounty_prize(state, content, world.get_season_number(), b.id, b.prize, issuer(content, b))
    return msgs


def _done(state: GameState, content: Content, world: WorldStateStore, match) -> list[str]:
    msgs: list[str] = []
    for b in mine(state, content):
        if match(b):
            msgs += _complete(state, content, world, b)
    return msgs


def on_win(state: GameState, content: Content, world: WorldStateStore, loc_id: str, squad_id: str) -> list[str]:
    """遊歷打贏：在討伐的地點打贏一場對頭陣營的隊伍就交差（哪一支都算）。"""
    enemy = content.squads[squad_id].faction if squad_id in content.squads else None
    return _done(
        state, content, world,
        lambda b: b.kind == "strike" and b.location == loc_id and enemy is not None and enemy == ENEMY.get(b.faction or ""),
    )


def on_explore(state: GameState, content: Content, world: WorldStateStore, loc_id: str) -> list[str]:
    return _done(state, content, world, lambda b: b.kind == "scout" and b.location == loc_id)


def on_arrive(state: GameState, content: Content, world: WorldStateStore, loc_id: str) -> list[str]:
    return _done(state, content, world, lambda b: b.kind == "escort" and b.end == loc_id)


def on_raid_win(state: GameState, content: Content, world: WorldStateStore, target: str) -> list[str]:
    key = name_key(target)
    return _done(state, content, world, lambda b: b.kind == "wanted" and name_key(b.target or "") == key)


def hunting(state: GameState, content: Content, target: str) -> bool:
    """我接了通緝這個人、還沒完成（截殺的鈕看它：散人、同陣營的人也能對他下手）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and name_key(b.target or "") == key for b in mine(state, content))


# ── 求藝、求兵：在懸賞榜上直接交（懸賞榜設計第四節）──────────────────────────────


def _art_of(art_id: str, content: Content, world: WorldStateStore, memo: dict | None):
    """全服共享的那一門（team.resolve_art）；memo 是同一次呼叫裡查過的（world.get_skill 沒有快取，每次是一條 SQLite 查詢，設計 4.9）。"""
    if memo is None:
        return team.resolve_art(art_id, content, world)
    if ("art", art_id) not in memo:
        memo[("art", art_id)] = team.resolve_art(art_id, content, world)
    return memo[("art", art_id)]


def _weapon(state: GameState, item_id: str) -> Weapon | None:
    """手上那把或裝備庫的武器欄裡 id 是 item_id 的那一把（求兵准交手上那把，企劃者 2026-10-10，14.1 丙）；都沒有是 None。
    裝備庫混放武器與防具（裝備一）：只看武器那一欄，防具 id（「甲:N」）一律當沒有。
    兵器 id 是「兵:3」：呼叫端照 partition 切一次，不要 split。"""
    p = state.player
    if p.weapon is not None and p.weapon.id == item_id:
        return p.weapon
    return next((w for w in equipment.in_slot(p, "weapon") if w.id == item_id), None)


def fit_problem(
    state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str, memo: dict | None = None,
) -> str | None:
    """這件東西合不合這一張（設計 4.5 第 3～7 條）；None＝合用。只看東西本身，不看人在哪裡、榜開沒開：江湖頁的懸賞卡
    （status、fitting）人在城外也照它列。拒絕的話待 joy 潤；跟 library.melt_problem 判斷一樣的幾條，字另寫（那裡寫的是「熔」）。"""
    p = state.player
    if b.kind not in GIVE_KINDS:
        return NOT_NOW
    if not can_take(state, b):
        return NOT_YOURS
    if name_key(p.name) in (name_key(t) for t in b.done_by):
        return GIVEN_BEFORE  # 一張一人只交一次
    if b.kind == "arms":
        if not content.config.weapons.enabled:
            return NOT_NOW
        w = _weapon(state, item_id)
        if w is None:
            return NO_WEAPON
        if w.original:
            return ORIGINAL_KEPT  # 5.4：一季全服只有一把，交了就上不了神器譜；仿品照一般兵器收（_arms_base 照三階上品）
        if w.kind != b.weapon_kind or w.attribute != b.attribute:
            return WANT_ARMS.format(attribute=b.attribute, noun=_noun(b))
        return None
    if item_id not in library.owned_arts(state):
        return NO_ART
    if item_id in (p.member.neigong_id, p.member.wugong_id):
        return WORN_ART
    if item_id == p.naming:
        return UNNAMED  # 熔了、交了，全服的第一人登記還在，那門就永遠沒有人替它定名
    art = _art_of(item_id, content, world, memo)
    if art is None:
        return NO_DATA  # 存檔記著、內容與全服登記都沒有的失效引用（同 fusion.fuse_problem）；後面才放心讀 origin
    if item_id in content.skills or art.origin != "fused" or art.preset:
        return ONLY_FUSED  # 基礎武學、內容寫好的、師門配方都不收；秘方合出來的收（設計 14.1 甲）
    if art.attribute != b.attribute:
        return WANT_ART.format(attribute=b.attribute)
    return None


def _quality_rank(quality: str) -> int:
    return QUALITIES.index(quality) if quality in QUALITIES else 0


def _melt(state: GameState, content: Content, world: WorldStateStore, art_id: str, memo: dict) -> int:
    """熔掉能換幾點心得：一律取 library.melt_value（熔煉頁、排序、標籤、確認句同一個數，不自己算）。"""
    if ("melt", art_id) not in memo:
        memo[("melt", art_id)] = library.melt_value(state, content, world, art_id)
    return memo[("melt", art_id)]


def _cheapness(state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str, memo: dict) -> tuple:
    """「最不值錢的先」（設計 4.4）：求藝照熔煉值（_melt，熔煉頁與確認句同一個數）、品質（低的先；PM 2026-10-11：
    熔煉值只算自己修練上去的幾階，合成時擲到上品的跟下品的可以同值，打平時不能先交掉上品的）、再照名字；求兵照賞銀的底數
    （_arms_base：arms_silver[品質] × arms_tier[階]，底數低的先；PM 2026-10-12，三階下品 80 比一階中品 35 值錢，不照品質優先）、
    鋒利度（低的先）、id。"""
    if b.kind == "arms":
        w = _weapon(state, item_id)
        return (_arms_base(content, w), w.edge, w.id)
    art = _art_of(item_id, content, world, memo)
    quality = team.art_quality(state, art)  # 同 team.player_art(...).quality，用查過的那份少一次資料庫
    return (_melt(state, content, world, item_id, memo), _quality_rank(quality), art.name)


def fitting(state: GameState, content: Content, world: WorldStateStore, b: Bounty, memo: dict | None = None) -> list[str]:
    """這一張合用的那幾件 id（fit_problem 過得了），最不值錢的先。不看人在哪裡（卡片在城外也列）。
    求藝先用便宜的條件濾掉內容武學、身上的、等著定名的，剩下的每門查一次（存進 memo；status 一次查好幾張時共用）。"""
    memo = {} if memo is None else memo
    p = state.player
    if b.kind == "arms":
        candidates = ([p.weapon.id] if p.weapon is not None else []) + [w.id for w in equipment.in_slot(p, "weapon")]
    elif b.kind == "art":
        skip = {p.member.neigong_id, p.member.wugong_id, p.naming}
        candidates = [a for a in p.arts if a not in content.skills and a not in skip]
    else:
        return []
    items = [i for i in candidates if fit_problem(state, content, world, b, i, memo) is None]
    return sorted(items, key=lambda i: _cheapness(state, content, world, b, i, memo))


def _arms_base(content: Content, w: Weapon) -> int:
    """求兵交這一把的銀兩底數（設計 4.7）：arms_silver[品質] × arms_tier[階]，還沒乘名號加成（交給 _silver 乘）。淬煉不加錢。"""
    cfg = content.config.bounties
    return cfg.arms_silver[w.quality] * cfg.arms_tier[str(w.tier)]


def pick_label(state: GameState, content: Content, b: Bounty, count: int) -> str:
    """懸賞榜第二層，交得出的求藝、求兵那一行（設計 4.3 第 1 點）：「交出… 官軍・求藝・剛（賞…；你有 2 門合用；期限…・名額還剩 3）」。
    待 joy 潤（整行；Task 4 的 test_the_board_lists_hand_ins_first_then_takes_then_one_greyed_line 鎖了整行，潤了一起改）。"""
    return (f"交出… {issuer(content, b)}・{title(content, b)}（{reward_text(state, content, b)}；你有 {count} {UNITS[b.kind]}合用；"
            f"{due_line(state, content, b)}）")


def only_original(state: GameState, b: Bounty) -> bool:
    """這一張求兵，身上（手上那把或裝備庫）有種類與屬性都對得上的、可是是神器原品（fit_problem 回 ORIGINAL_KEPT）：交不出的原因
    不是「沒有對得上的兵器」（FB-145）。只在交不出的那幾張上問（engine 的懸賞榜第二層），所以「只有原品」由呼叫端保證。"""
    if b.kind != "arms":
        return False
    p = state.player
    held = ([p.weapon] if p.weapon is not None else []) + equipment.in_slot(p, "weapon")
    return any(w.original and w.kind == b.weapon_kind and w.attribute == b.attribute for w in held)


def stuck_label(content: Content, asks: list[Bounty], kept: frozenset[str] | set[str] = frozenset()) -> str:
    """懸賞榜第二層，交不出的求藝、求兵收成的那一行灰掉的（設計 4.3 第 3 點）：選單才不會長到手機第一屏放不下（FB-128）。
    kept：身上只有神器原品對得上的那幾張（only_original）的 id，那一張後面照實寫 ONLY_ORIGINAL（FB-145）。"""
    return STUCK.format(titles="、".join(
        f"{issuer(content, b)}・{title(content, b)}" + (ONLY_ORIGINAL if b.id in kept else "") for b in asks))


def pick_line(content: Content, b: Bounty) -> str:
    """按了「交出…」的回話（待 joy 潤）。"""
    return f"你替「{issuer(content, b)}・{title(content, b)}」挑一件要交的東西。"


def _offer(state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str, memo: dict) -> tuple[str, str]:
    """第三層一顆交出鈕的（標籤, 確認句）（設計 4.4，待 joy 潤）。求藝寫種類、品質、第幾成與熔掉能換多少心得；求兵寫階品、鋒利度、
    實拿多少銀兩（照 _silver：散人第 4 階的加成算在裡面），淬過的寫明不加錢，手上那把寫明交了就空手。"""
    who = issuer(content, b)
    if b.kind == "art":
        art = team.player_art(state, content, world, item_id)
        level, melt = library.level_of(state, item_id), _melt(state, content, world, item_id, memo)
        return (f"交出【{art.name}】（{art.kind}・{art.quality}・第{level}成；熔掉能換 {melt} 心得）",
                f"把【{art.name}】（{art.quality}・第{level}成）交給{who}？交了就沒了；熔掉的話能換 {melt} 心得。")
    w = _weapon(state, item_id)
    held = w is state.player.weapon
    silver = _silver(state, content, b, base=_arms_base(content, w))
    ask = f"把【{w.name}】（{weapons.grade(w)}）交給{who}？交了就沒了。"
    if w.tempers:
        ask += TEMPERED_NOTE.format(n=w.tempers)
    if held:
        ask += HELD_NOTE
    return f"交出【{w.name}】（{weapons.grade(w)}・鋒利度 {w.edge}{'・在手上' if held else ''}）→ 賞銀 {silver}", ask


def hand_in_options(
    state: GameState, content: Content, world: WorldStateStore, b: Bounty, items: list[str], memo: dict | None = None,
) -> list:
    """懸賞榜第三層（替 b 挑一件，設計 4.4）：合用的（items，fitting 排好的）最不值錢的 give_list 件各一顆交出，每顆先問一次
    （確認只在網頁那一層；give 自己整個重驗）；多的收成一行灰掉的；身上正在練、等著定名的那門要是對得上，灰掉寫原因；
    最後永遠按得下去的「回到懸賞榜」。只讓交最不值錢的這幾件是有意的：交出去就沒了，該交的是最捨得的。"""
    from .engine import Option  # noqa: PLC0415  engine 會 import 這裡（同 smithing.temper_option）

    memo = {} if memo is None else memo
    p, cfg = state.player, content.config.bounties
    opts = []
    for item in items[:cfg.give_list]:
        label, ask = _offer(state, content, world, b, item, memo)
        opts.append(Option(id=f"bounty:give:{b.id}:{item}", label=label, confirm=ask, confirm_yes=GIVE_YES))
    if len(items) > cfg.give_list:
        opts.append(Option(id="bounty:more", label=MORE[b.kind].format(n=len(items) - cfg.give_list), enabled=False))
    if b.kind == "art":
        worn = (p.member.neigong_id, p.member.wugong_id)
        for art_id in dict.fromkeys(a for a in (*worn, p.naming) if a):
            art = _art_of(art_id, content, world, memo)
            if art is None or art_id in content.skills or art.origin != "fused" or art.preset or art.attribute != b.attribute:
                continue  # 本來就不合用的不列
            note = WORN_NOTE if art_id in worn else NAMING_NOTE
            opts.append(Option(id=f"bounty:give:{b.id}:{art_id}", label=note.format(name=art.name), enabled=False))
    opts.append(Option(id="bounty:unpick", label=UNPICK))
    return opts


def give_choice(state: GameState, content: Content, world: WorldStateStore) -> tuple[str, str] | None:
    """（懸賞 id, 東西 id）：此地懸賞榜上第一張交得出的求藝、求兵，與第三層排第一、按得下去的那一件（最不值錢的；設計 9.1）。
    整季機器人與伺服器假人共用（照 weapons.wanted 的做法），照這個挑、不隨機：同分隨機會把最好的那門交掉。
    手上那把兵器不交（交了要空手、少一截威力；真人看得到確認句自己決定）——設計 9.1 寫的是「排第一的那一件」，跳過手上那把是
    計畫的取捨 3，PM 2026-10-11 確認：整季機器人與伺服器假人不交手上那把，真人可以。城外、榜關著、沒得交是 None。"""
    if not board_here(state, content):
        return None
    held = state.player.weapon.id if state.player.weapon is not None else None
    memo: dict = {}
    for b in visible(state, content):
        if b.kind not in GIVE_KINDS:
            continue
        for item in fitting(state, content, world, b, memo)[:content.config.bounties.give_list]:
            if b.kind != "arms" or item != held:
                return b.id, item
    return None


def give_problem(state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str) -> str | None:
    """第三層的交出鈕亮不亮、give 真的交之前都走這裡（設計 4.5 第 1、2 條，再接 fit_problem）：懸賞榜看得到、這一張還在榜上。"""
    if not board_here(state, content):
        return NOT_NOW
    if b.id not in {x.id for x in open_bounties(state, content)}:
        return GONE  # 過期了，或名額滿了
    return fit_problem(state, content, world, b, item_id)


class GiftRolls(NamedTuple):
    """求藝另給的那幾樣擲出來的結果（gift_rolls）。"""

    second: bool  # 再給一個同屬性二階素材
    armed: bool  # 給一把兵器
    top: bool  # 那把是上品（不然中品）
    spare: str  # 身上的武學推不出兵器種類時用的種類


def gift_rolls(season: int, name: str, bounty_id: str, cfg) -> GiftRolls:
    """求藝的擲骰（設計 4.7）：自己一份亂數（季數＋名號＋懸賞 id），不碰 Game.rng；照固定順序每次都抽四次（二階素材、兵器、品質、
    退路的種類），用不用得到都抽，同一個人交同一張永遠同一個結果（一張一人只能交一次，也重擲不了）。種子一定要有季數：
    懸賞 id 每季從 b1 算起，選項 id（bounty:pick:b17）在網頁上看得到，少了季數，記下哪幾號送兵器、下一季就專挑那幾張。"""
    rng = random.Random(f"bounty-gift|{season}|{name}|{bounty_id}")
    second = rng.random() < cfg.art_material2_chance
    armed = rng.random() < cfg.art_weapon_chance
    top = rng.random() < cfg.art_weapon_top_chance
    return GiftRolls(second, armed, top, rng.choice(WEAPON_KINDS))


def _art_gifts(state: GameState, content: Content, world: WorldStateStore, b: Bounty) -> list[str]:
    """求藝另給的（設計 4.7）：這張屬性的一階素材 art_materials 個，再看擲骰給一個同屬性二階、一把一階兵器（種類配身上那門武學，
    推不出來〔空著、內功、舊的自創武學〕用退路的種類；屬性同這張；上品或中品）。裝備庫滿了改給同品質的 arms_silver（那把兵器照價折，
    不乘名號加成；不學裝備四欄 6.5 寄放：架上 40 兩就買得到的一階貨，折錢就是等價）。兵器開關關著不給也不折。"""
    cfg, p = content.config.bounties, state.player
    rolls = gift_rolls(world.get_season_number(), p.name, b.id, cfg)
    msgs: list[str] = []
    for tier, count in ((1, cfg.art_materials), (2, 1 if rolls.second else 0)):
        pool = materials.by_tier(content, tier, b.attribute)  # 挑不到這個屬性時退回同階全部（內容缺一角也不會炸）
        line = materials.grant(state, content, pool[0].id, count) if pool else None
        if line:
            msgs.append(line)
    if not rolls.armed or not content.config.weapons.enabled:
        return msgs
    kind = weapons.art_weapon(p.member.wugong_id, content, world) or rolls.spare
    quality = "上品" if rolls.top else "中品"
    name = weapons.shop_name(kind, b.attribute)  # 跟鐵匠鋪架上的下品同名，靠 weapons.grade 寫出的階品分辨
    if weapons.rack_full(state, content):
        silver = cfg.arms_silver[quality]
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        return msgs + [RACK_FULL_SILVER.format(name=name, silver=silver), f"銀兩 +{silver}"]
    w = weapons.new_weapon(state, name=name, kind=kind, attribute=b.attribute, tier=1, quality=quality)
    return msgs + [weapons.GAIN_LINE.format(name=w.name), weapons.store(state, content, w)]


def give(state: GameState, content: Content, world: WorldStateStore, bounty_id: str, item_id: str) -> list[str]:
    """交出（設計 4.5～4.7）：整個重驗（確認只在網頁那一層，引擎、假人、腳本都不會先問），交掉那一件，再發賞。
    求藝：拿掉那一門與它的私有紀錄（library.remove_art），不退心得；全服登記的那一門不動。求兵：拿掉那一把（手上那把交了就空手、
    鈍了的提醒重設，不自動換一把上手），銀兩照它的品質與階。陣營的人也拿全額；散人另記俠名。"""
    b = next((x for x in state.world.bounties if x.id == bounty_id), None)
    if b is None:
        return [GONE]
    problem = give_problem(state, content, world, b, item_id)
    if problem is not None:
        return [problem]
    p, cfg = state.player, content.config.bounties
    emptied = False
    if b.kind == "art":
        name = team.resolve_art(item_id, content, world).name
        library.remove_art(state, item_id)
        msgs = _complete(state, content, world, b)
    else:
        w = _weapon(state, item_id)
        name = w.name
        if p.weapon is w:
            p.weapon, p.edge_warned, emptied = None, False, True
        else:
            p.rack.remove(w)
        msgs = _complete(state, content, world, b, silver=_arms_base(content, w))
    msgs[0] = GIVEN.format(name=name, issuer=issuer(content, b), title=title(content, b))
    xinde = cfg.xinde.get(b.kind, 0)
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        msgs.append(f"心得 +{xinde}")
    if b.kind == "art":
        msgs += _art_gifts(state, content, world, b)
    if emptied:
        msgs.append(EMPTY_HANDS)
    return msgs


# ── 通緝（玩家花銀兩掛的）──────────────────────────────


def post_problem(state: GameState, content: Content, target_state: GameState, amount: int | None = None) -> str | None:
    """通緝這個人按不按得下去：懸賞榜與截殺都開著、你投靠了陣營、他是敵對陣營的人、他過了新手期、你手上沒有還掛著的通緝、錢夠。"""
    if not active(state, content) or not content.config.raid.enabled:
        return "（此刻無法這麼做。）"
    p, t = state.player, target_state.player
    if p.faction is None or t.faction is None or p.faction == t.faction:
        return "只能通緝敵對陣營的人。"
    if roster.raid_newbie(target_state, content):  # 截殺不了還在新手期的人：押了錢也只能等退（懸賞榜設計 6.2、14.1 丁）
        return f"{t.name}初入江湖，還在新手期，通緝不了{gender.pronoun(t)}。"  # 待 joy 潤
    me = name_key(p.name)
    if any(b.kind == "wanted" and b.poster and name_key(b.poster) == me and not past_due(b, content, state.world) and _left(b) > 0
           for b in state.world.bounties):
        return "你已經掛著一張通緝了，等它揭下再說。"
    cfg = content.config.bounties
    purse = p.stats.get("silver", 0)
    if purse < cfg.post_min:
        return f"通緝至少要押 {cfg.post_min} 兩。"
    if amount is not None and not cfg.post_min <= amount <= min(cfg.post_max, purse):
        return f"賞金要在 {cfg.post_min}～{min(cfg.post_max, purse)} 兩之間。"
    return None


def post(state: GameState, content: Content, target_state: GameState, amount: int) -> list[str]:
    problem = post_problem(state, content, target_state, amount)
    if problem is not None:
        return [problem]
    p, w = state.player, state.world
    p.stats["silver"] = p.stats.get("silver", 0) - amount
    w.bounty_seq += 1
    b = Bounty(
        id=f"b{w.bounty_seq}", kind="wanted", faction=p.faction, week=calendar.point(w.time, content, w).week,
        expires=w.time + content.config.bounties.post_weeks * week_seconds(state, content), silver=amount,
        deeds=content.config.bounties.deeds.get("wanted", 0), quota=1, poster=p.name, target=target_state.player.name,
    )
    w.bounties.append(b)
    return [f"你押了 {amount} 兩，在懸賞榜上通緝{b.target}。", f"銀兩 -{amount}"]


def deliver_refunds(state: GameState, content: Content) -> list[str]:
    """我掛的通緝過期了（past_due：寫「到季末」的撐到收季）、沒人完成：押金退回（掛單的人同步時呼叫）。"""
    p, w = state.player, state.world
    me = name_key(p.name)
    msgs: list[str] = []
    for b in w.bounties:
        if (b.kind == "wanted" and not b.refunded and not b.done_by and past_due(b, content, w)
                and b.poster and name_key(b.poster) == me):
            b.refunded = True
            p.stats["silver"] = p.stats.get("silver", 0) + b.silver
            msgs += [f"【懸賞】你通緝{b.target}的那一張沒人揭成，押金退回。", f"銀兩 +{b.silver}"]
    return msgs


def deliver_lapses(state: GameState, content: Content) -> list[str]:
    """我揭了、還沒交差的那一張被別人交滿了名額、過了自己的期限、或這一季收了：拿掉我的名字、補一句（FB-121 第 5 件；寫法同 deliver_refunds，同步時呼叫）。
    過了期限還有人揭著的單，issue 掛新單時先留著（等揭的人同步時在這裡拿掉），不然他回來只看到那一張默默不見了。
    原因照「哪一個先發生」說，優先序：
    1. 陣營（FB-151）：名字還留在自己陣營接不了的單上（換版之前就換了陣營的存檔、不經過 Game.choose 就改了陣營的入口），不管過期、名額滿與否，
       那才是它先消失的原因；
    2. 名額滿了（FB-121）：揭的人在榜上看到它少了一張，早於季收；
    3. 自己的期限（沒寫「到季末」的單，到期在季末之前）：揭的人一直沒同步、季先收了，照樣說「過了期限」；
    4. 這一季收了（FB-152、FB-153）：寫「到季末」的單、和季收了時還沒到期的，同一句，第 11 週與第 12 週掛的一樣。
    季還在跑時，寫「到季末」的單不在這裡作廢（管理者把季末往後排也一樣，past_due）。一樣拿掉名字、只說一次。"""
    p, w = state.player, state.world
    me = name_key(p.name)
    msgs: list[str] = []
    for b in w.bounties:
        if me not in (name_key(t) for t in b.takers) or me in (name_key(t) for t in b.done_by):
            continue
        name = title(content, b)
        if p.faction is not None and p.faction != b.faction:  # 同 _takeable 的陣營那一條
            line = LAPSED_SIDE.format(faction=content.scenario.faction_name(p.faction, "別的陣營"), title=name)
        elif _left(b) <= 0:
            line = LAPSED_FULL.format(title=name)
        elif not past_due(b, content, w):
            continue
        elif not to_season_end(b, content, w) and b.expires <= w.time:  # 自己的期限先到（不管季收了沒有）
            line = LAPSED_DUE.format(title=name)
        else:  # 寫「到季末」的、或季收了時還沒到期的：past_due 為真只剩季收了這一個原因
            line = LAPSED_SEASON.format(title=name)
        b.takers = [t for t in b.takers if name_key(t) != me]
        msgs.append(line)
    return msgs


# ── 每週一自動掛單 ──────────────────────────────


def prize_rolls(tianji: int, week: int, faction: str, content: Content) -> tuple[bool, bool]:
    """這一邊這一週有沒有重賞（裝備四欄 6.4）：寶物、良駒各擲一次、分開擲。自己一份亂數（天機＋週次＋陣營；天機是開季時蓋進季裡的
    WorldState.tianji，不然每一季同一週的重賞都一樣）：不碰掛單那一份（bounty|…，同時挑討伐、打探、護送的地點），插進去擲的話
    之後每一張單的地點都會位移。兩個都照抽、不管開關開不開（開關只決定掛不掛上去）。"""
    cfg = content.config.treasures
    rng = random.Random(f"bounty-prize|{tianji}|{week}|{faction}")
    return rng.random() < cfg.bounty_treasure_chance, rng.random() < cfg.bounty_horse_chance


def _hang_prizes(w: WorldState, content: Content, week: int) -> None:
    """重賞掛上去（6.4）：官軍、黃巾這一週新掛的討伐，寶物掛第一張、良駒掛第二張（只中一個就掛第一張；討伐不夠就少掛）。
    那一欄關著的不掛。issue 一週只跑一次，所以「這一週、這一邊的討伐」就是這一批剛掛的。"""
    for faction in ENEMY:
        strikes = [b for b in w.bounties if b.week == week and b.faction == faction and b.kind == "strike"]
        treasure, horse = prize_rolls(w.tianji, week, faction, content)
        prizes = [prize for prize, hit in (("treasure", treasure), ("horse", horse)) if hit and treasures.prize_on(content, prize)]
        for b, prize in zip(strikes, prizes):
            b.prize = prize


def tick(state: GameState, content: Content) -> list[str]:
    """第一季規則關著的季的週初掛單（world.advance_world_state 每一步、world.settle_season_start 開季那一刻）：季曆跨進新的一週
    就掛這一週的（只掛這一週，以前的週不補掛；同一週只掛一次，見 issue 的兩道擋）。每一步最多一小時，所以最多晚一小時掛，
    期限錨在週初、不會跟著延後。不回傳訊息。"""
    w = state.world
    return issue(state, content, calendar.point(w.time, content, w).week)


def _opened(loc: Location, w: WorldState) -> bool:
    """這個地點全服來說開放了沒（FB-150：週初掛單只挑已開放的地點，不然揭的人「無法安排前往這裡」、那張單白占一個名額）。
    規則同 atlas.is_unlocked 去掉看人的那一半：不是序章專屬的地點，而且 unlock_flag 沒設或已經在世界旗標裡。
    不 import atlas（它 import rules、orders、figures，怕繞成環），所以在這裡照寫一份；那邊改了這邊要跟著改。"""
    return not loc.prologue_only and (not loc.unlock_flag or loc.unlock_flag in w.flags)


def _strike(content: Content, w: WorldState, faction: str, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    enemy = ENEMY[faction]
    spots = [
        (loc_id, sid) for loc_id, loc in content.locations.items() if loc_id not in used and _opened(loc, w)
        for sid in loc.enemies if sid in content.squads and content.squads[sid].faction == enemy
    ]
    return rng.choice(spots) if spots else None


def _scout(content: Content, w: WorldState, rng: random.Random, used: set[str]) -> str | None:
    """打探的地點：危險度 2 以上、不是城鎮、已開放；used 是榜上還有效的打探已經用掉的地點（不分陣營）。"""
    spots = [
        loc_id for loc_id, loc in content.locations.items()
        if loc.danger >= 2 and not is_town(content, loc_id) and loc_id not in used and _opened(loc, w)
    ]
    return rng.choice(spots) if spots else None


def _escort(content: Content, w: WorldState, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    """護送的起點與終點：兩個不相鄰的已開放城鎮；used 是榜上還有效的護送已經用掉的終點（不分陣營）。"""
    towns = [loc_id for loc_id, loc in content.locations.items() if is_town(content, loc_id) and _opened(loc, w)]
    pairs = [
        (a, b) for a in towns for b in towns
        if a != b and b not in {str(x) for x in content.locations[a].connections} and b not in used
    ]
    return rng.choice(pairs) if pairs else None


def _spread(rng: random.Random, attributes: list[str], n: int) -> list[str]:
    """n 個屬性（求藝、求兵每一方一個）：先不重複地抽，陣營比屬性多時再補可以重複的。不寫死 3：give_attributes 只要求至少一個，
    少於陣營數時 rng.sample(attributes, 3) 會丟 ValueError（懸賞榜設計 4.1）。"""
    picks = rng.sample(list(attributes), min(n, len(attributes)))
    return picks + [rng.choice(list(attributes)) for _ in range(n - len(picks))]


def issue(state: GameState, content: Content, week: int, rng: random.Random | None = None) -> list[str]:
    """週初掛單（第一季：world.WEEK_HOOKS；規則關著的季：tick）：陣營掛的舊單下榜（通緝照自己的期限），兩個陣營各掛 kinds 裡的每一張
    （只挑已開放的地點〔_opened，FB-150：南華觀要等 xi_open 立起來〕，避開榜上還有效〔沒過期、名額沒滿〕的同種單已經用掉的地點，
    不管是哪一週掛的：討伐看同一個陣營、打探不分陣營、護送不重複終點；濾完沒地方可挑就跳過那一張），劇本的每個陣營再各掛
    give_kinds 裡的每一種（求藝、求兵）；討伐另外擲重賞（寶物、良駒，_hang_prizes）。不回傳訊息。
    rng 不用（介面跟其他週初掛鉤一樣）。
    兩道擋（懸賞榜設計 3.2）：只掛「這一週」（week 要等於此刻的季曆週，同 orders.issue；不然停機補算、管理者快轉會把以前的週補掛出來），
    這一週掛過了不再掛（bounty_week）。期限錨在週初：week_start(週次＋auto_weeks)，晚掛也不會多掛。"""
    w, cfg = state.world, content.config.bounties
    if not active(state, content) or week != calendar.point(w.time, content, w).week or week <= w.bounty_week:
        return []
    w.bounty_week = week
    # 自己一份亂數（週次、流水號、此刻的戰況）：不動季的 rng，排在後面的大事擲骰不會因為多了懸賞榜而位移
    # 天機（開季時蓋進季裡）：每一季同一週的單不一樣；天機是 0（測試、量表、功能上線前開的季）時種子一字不差，基準不位移（計畫「要 PM 定的」第 1 條）
    salt = f"|{w.tianji}" if w.tianji else ""
    rng = random.Random(f"bounty|{week}|{w.bounty_seq}|{sorted(w.trends.items())}{salt}")
    w.bounties = [
        b for b in w.bounties
        if not past_due(b, content, w)
        or (b.kind == "wanted" and not b.refunded and not b.done_by)  # 過期的通緝留到押金退回
        or b.takers  # 過期了還有人揭著：留到他們同步時聽到那一句（deliver_lapses）
    ]
    expires = calendar.week_start(week + cfg.auto_weeks, content, w)
    # 同一地點不重複掛（FB-121 第 2 件：同一處兩張一樣的單，一次遊歷或探索交兩張差）：避開榜上還有效的同種單已經用掉的地點。
    # 討伐只看同一個陣營（兩邊打的對頭不同，on_win 不會一次交兩張）；打探不分陣營；護送不分陣營、不重複終點。濾完沒地方可挑就跳過那一張
    live = [b for b in w.bounties if not past_due(b, content, w) and _left(b) > 0]
    scouted = {b.location for b in live if b.kind == "scout"}
    ends = {b.end for b in live if b.kind == "escort"}
    for faction in ENEMY:
        if faction not in {f.id for f in content.scenario.factions}:
            continue
        used = {b.location for b in live if b.kind == "strike" and b.faction == faction}
        for kind in cfg.kinds:
            spec: dict = {}
            if kind == "strike":
                spot = _strike(content, w, faction, rng, used)
                if spot is None:
                    continue
                used.add(spot[0])
                spec = {"location": spot[0], "squad": spot[1]}
            elif kind == "scout":
                loc = _scout(content, w, rng, scouted)
                if loc is None:
                    continue
                scouted.add(loc)
                spec = {"location": loc}
            elif kind == "escort":
                pair = _escort(content, w, rng, ends)
                if pair is None:
                    continue
                ends.add(pair[1])
                spec = {"location": pair[0], "end": pair[1]}
            else:
                continue
            w.bounty_seq += 1
            w.bounties.append(Bounty(
                id=f"b{w.bounty_seq}", kind=kind, faction=faction, week=week, expires=expires,
                silver=cfg.silver.get(kind, 0), deeds=cfg.deeds.get(kind, 0), quota=quota(content), **spec,
            ))
    # 求藝、求兵（懸賞榜設計 4.1）：劇本的每個陣營（含地方豪強，照劇本的順序）各掛 give_kinds 裡的每一種；屬性從 give_attributes 挑，
    # 同一期同一種各方不重複，求兵另挑種類（可以重複）。兵器開關關著不掛求兵。另開一份亂數：從上面那一份抽的話，
    # 後面每一張討伐、打探、護送的地點都會位移。種子帶天機（天機是 0 時照舊），每一季第 1 週的屬性不再一樣（設計 14.2 第 7 條，裝備三一起做）
    give_rng = random.Random(f"bounty-give|{week}|{sorted(w.trends.items())}{salt}")
    factions = [f.id for f in content.scenario.factions]
    asks: dict[str, list[tuple[str, str | None]]] = {}
    for kind in cfg.give_kinds:
        if kind not in GIVE_KINDS or (kind == "arms" and not content.config.weapons.enabled):
            continue
        attributes = _spread(give_rng, cfg.give_attributes, len(factions))
        asks[kind] = [(a, give_rng.choice(WEAPON_KINDS) if kind == "arms" else None) for a in attributes]
    for i, faction in enumerate(factions):
        for kind, picks in asks.items():
            attribute, weapon_kind = picks[i]
            w.bounty_seq += 1
            w.bounties.append(Bounty(
                id=f"b{w.bounty_seq}", kind=kind, faction=faction, week=week, expires=expires, silver=cfg.silver.get(kind, 0),
                deeds=cfg.deeds.get(kind, 0), quota=cfg.give_quota, attribute=attribute, weapon_kind=weapon_kind,
            ))
    _hang_prizes(w, content, week)  # 重賞（裝備四欄 6.4）：另一份亂數，上面掛出來的單一張都不動
    return []


def targets(state: GameState, content: Content) -> list[str]:
    """假人往哪裡走：手上每一張要去的地點（討伐、打探：那裡；護送：終點）。"""
    out = []
    for b in mine(state, content):
        if b.kind == "escort":
            out.append(b.end)
        elif b.kind in ("strike", "scout"):
            out.append(b.location)
    return [loc for loc in out if loc in content.locations]


def _row(state: GameState, content: Content, b: Bounty) -> dict:
    return {"id": b.id, "title": title(content, b), "how": how(content, b), "reward": reward_text(state, content, b),
            "issuer": issuer(content, b), "due": due_line(state, content, b)}


def have_text(state: GameState, content: Content, world: WorldStateStore, b: Bounty, items: list[str], memo: dict | None = None) -> str:
    """懸賞卡那一列的「你身上合用的：【烈焰掌】、【回風腿】等 3 門」（items 照 fitting 排好的，最不值錢的先寫兩件；待 joy 潤）。
    兵器多寫階品（求藝送的、鐵匠鋪買的同名，例「厚背刀」，靠階品分辨），手上那把再寫「在手上」（fitting 連手上那把也算，
    所以開頭寫「身上」不寫「庫裡」）。"""
    memo = {} if memo is None else memo

    def named(item: str) -> str:
        if b.kind == "art":
            return f"【{_art_of(item, content, world, memo).name}】"
        w = _weapon(state, item)
        return f"【{w.name}】（{weapons.grade(w)}{'・在手上' if w is state.player.weapon else ''}）"

    more = f"等 {len(items)} {UNITS[b.kind]}" if len(items) > 2 else ""
    return HAVE + "、".join(named(i) for i in items[:2]) + more


def status(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """狀態用（江湖頁的懸賞卡）：我手上揭了的每一張（標題、怎麼完成、賞、期限與名額），再加上身上有合用東西的求藝、求兵（多一個 have）。
    合用照 fitting 判、不看人在哪裡：人在城外也列，知道去城鎮交（不能用 give_problem，它要人在城鎮，設計 4.9）。
    每次 /api/main 都算：只在榜上有接得了、自己還沒交過的求藝、求兵時才找合用的；查過的武學存進這一次的 memo。"""
    rows = [_row(state, content, b) for b in mine(state, content)]
    me = name_key(state.player.name)
    memo: dict = {}
    for b in open_bounties(state, content):
        if b.kind not in GIVE_KINDS or not can_take(state, b) or me in (name_key(t) for t in b.done_by):
            continue
        items = fitting(state, content, world, b, memo)
        if items:
            rows.append({**_row(state, content, b), "have": have_text(state, content, world, b, items, memo)})
    return rows
