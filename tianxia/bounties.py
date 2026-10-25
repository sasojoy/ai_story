"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」；Config.bounties）。

- 官軍、黃巾每週一 00:00（季曆；第一季走 world.WEEK_HOOKS、規則關著的季走 tick，都叫 issue）各自動掛討伐兩張、打探、護送各一張（Config.bounties.kinds）：討伐是到指定的地方遊歷、
  打贏一場對頭陣營的隊伍；打探是到指定的地方探索一次；護送是在起點的城鎮接下、走到終點的城鎮。掛 auto_weeks 週，過期的下榜。
- 投靠了陣營的人可以在玩家卡上花銀兩通緝一個敵對陣營的人（押金就是賞金）；接了通緝的人在卡上對他「截殺」，照截殺的規則打，
  打贏就完成。沒人完成就在 post_weeks 週後下榜，押金在掛單的人下次同步時退回（deliver_refunds）。
- 散人兩邊的都能接，陣營的人只能接自己陣營的（can_take）；接了才算，一個人同時最多接 max_taken 張。
  前 quota 個完成的人各拿一份：銀兩（遊俠名號到第 4 階的散人另有加成）與經驗，散人另記俠名（ranger.add_deeds）。
- 求兵（懸賞榜設計第四節）：劇本的每個陣營（官軍、黃巾、地方豪強）每週一各掛一張求兵（交一把指定種類與屬性的兵器）。
  不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前 give_quota 個交的有賞；散人三方都能交，陣營的人只交自己陣營的、拿全額。
  求藝（交一門合成出來的武學）企劃者 2026-10-21 拿掉（「懸賞榜直接把武學拿掉」：武學不再合成，熔爐只合意境，求藝沒有來源）；
  舊存檔榜上還掛著的求藝，讀季的時候丟掉（state.WorldState._drop_retired_bounties）。

每季都有（企劃者 2026-10-10「整個懸賞榜每季都有」，懸賞榜設計 2.2）：只看 Config.bounties.enabled、劇本有沒有陣營、這一季收了沒有（active），
不看第一季開關；關著時每個函式都什麼都不做、回空的。
過了期限只有一個問法（past_due，FB-152、FB-153）：這一季收了，榜上的一律算過了；寫「到季末」的單撐到季真的收了；其他的照自己的期限。
只改 GameState（玩家與共用的季）；不 import engine、world（world 會 import 這裡，掛 WEEK_HOOKS）。"""
from __future__ import annotations

import math
import random
from typing import NamedTuple

from . import allied, calendar, equipment, gender, materials, ranger, renown, roster, team, territory, treasures, weapons
from .characters import name_key
from .models import WEAPON_KINDS, Choice, Content, Location
from .state import Bounty, GameState, PlayerState, Weapon, WorldState
from .world_state import WorldStateStore

KIND_NAMES = {"strike": "討伐", "scout": "打探", "escort": "護送", "wanted": "通緝", "arms": "求兵"}
GIVE_KINDS = ("arms",)  # 求兵：不用揭，在懸賞榜上直接交（懸賞榜設計第四節）；求藝企劃者 2026-10-21 拿掉
FULL_PAY = ("wanted", "arms")  # 陣營的人也拿全額的（通緝是押金照數給；求兵企劃者 2026-10-10 定）
NO_TAKE = "這一張不用揭，在懸賞榜上直接交。"  # 待 joy 潤
NOT_NOW = "（此刻無法這麼做。）"
GONE = "這張懸賞已經下榜了。"  # 待 joy 潤
STALE = "榜上的情形變了，這一下沒有作用；照現在的畫面再選一次。"  # 待 joy 潤（FB-162：兩個分頁搶同一張，慢的那一頁按下去的懸賞選項已經不在選單上，又沒有更具體的原因可說）
GIVEN_PREFIX = "【懸賞】你把"
GIVEN = GIVEN_PREFIX + "【{name}】交給了{issuer}（{title}），賞銀送到。"  # 待 joy 潤：交出的第一行（取代 _complete 的「交差了」那一行）
EMPTY_HANDS = "你現在空著手。"  # 待 joy 潤：交的是手上那把
# 挑一件、回到懸賞榜只是在榜上翻頁：只有這一句回話時不寫江湖紀錄（Game.choose）；交出每一張各一則、各寫各的得失（FB-161：
# 以前挑、回、交併成一則，連交幾張時得失加總在一起，分不出哪一張給了多少）
BROWSE_VERBS = ("pick", "unpick")
PICKED = "你替「{what}」挑一件要交的東西。"  # 待 joy 潤：按了 bounty:pick 的回話（pick_line）
GIVE_YES = "交出"  # 待 joy 潤：確認層上那一顆（Option.confirm_yes）
STUCK = "這幾張你現在交不出：{titles}（求兵要種類與屬性都對得上的兵器）"  # 待 joy 潤（2026-10-21 拿掉求藝那半句）
# 待 joy 潤：第三層只列最不值錢的 give_list 件（設計 4.4），多的收成這一行
MORE = "還有 {n} {unit}合用的沒列出來（列的是最不值錢的；要交別的，先把前面這幾{unit}拆掉或交掉）"
UNPICK = "回到懸賞榜"  # 待 joy 潤：第三層最後一顆（bounty:unpick）
UNPICKED = "你回到懸賞榜前。"  # 待 joy 潤：按了 bounty:unpick 的回話（Game._bounty）
TEMPERED_NOTE = "淬煉過 {n} 次，賞銀不會多給。"  # 待 joy 潤：第三層交兵器的確認句
HELD_NOTE = "這是你手上那{unit}，交了你就空手了。"  # 待 joy 潤：同上，交的是手上那把（量詞照種類，終審 F4）
HAVE = "你身上合用的："  # 待 joy 潤：懸賞卡那一列（have_text）；fitting 連手上那把兵器也算，所以寫「身上」不寫「庫裡」
NOT_YOURS = "這一張不是給你的。"  # 待 joy 潤；fit_problem 的拒絕句（設計 4.5）都寫成常數，測試引用常數，潤字不必改測試
GIVEN_BEFORE = "這一張你已經交過了。"  # 待 joy 潤
NO_WEAPON = "裝備庫裡沒有這一件。"  # 待 joy 潤
ORIGINAL_KEPT = "神器的原品交不得"  # 待 joy 潤（打造隱藏配方設計 5.4：手上那把也不收）
SIGNATURE_KEPT = "本命兵器交不得"  # 待 joy 潤（打造第三批：手上那把也不收）
ONLY_ORIGINAL = "（你身上對得上的只有神器的原品，原品交不得）"  # 待 joy 潤：灰掉那一行裡、只有原品對得上的那一張後面（FB-145）
ONLY_SIGNATURE = "（你身上對得上的只有名將的本命兵器，本命兵器交不得）"  # 待 joy 潤（打造第三批；FB-145 的本命兵器版）
WANT_ARMS = "這一張要屬{attribute}的{noun}。"  # 待 joy 潤（noun 照 _noun）
# 21 天季每張附的那一樣（正式季整合設計 6.1 第 2 點）：賞那一段最後寫一句（待 joy 潤）
ATTACH_NOTES = {"strike": "・二階素材（偶有三階）", "scout": "・{pill} 一顆", "escort": "・二階素材"}
# 21 天季的懸賞卡與告示把賞拆成小籤（企劃者挑第 5 批畫面第三組丙）：reward_tags 一格一樣，重賞那一格與「照等級」那一句
PRIZE_TAG = "重賞：{what}"  # 待 joy 潤
GIFT_SHORT = {"strike": "＋二階", "escort": "＋二階", "scout": "＋{pill}"}  # 待 joy 潤：告示正面附贈那一格（FB-391，紙上那一格的短寫）；求藝那一格 2026-10-21 跟求藝一起拿掉
LEVEL_NOTE = "賞照你第 {level} 級"  # 待 joy 潤
ENEMY = {"guan": "huang", "huang": "guan"}  # 自動掛單的兩個陣營與他們的對頭（同軍令）
BOARD = "懸賞榜"
SEASON_END = "到季末"  # 待 joy 潤：期限到季末或過了季末時寫這個（due_text）
LAPSED_FULL = "【懸賞】「{title}」名額被別人交滿了，你手上這一張作廢。"  # 待 joy 潤（FB-121 第 5 件，deliver_lapses）
LAPSED_DUE = "【懸賞】「{title}」過了期限，你手上這一張作廢。"  # 待 joy 潤
LAPSED_SEASON = "【懸賞】這一季收了，你手上「{title}」作廢。"  # 待 joy 潤（FB-152、FB-153：寫「到季末」的單撐到季真的收了；收季那一刻手上揭著的都補這一句，第 11、12 週掛的一樣）
LAPSED_SIDE = "【懸賞】你改投{faction}，手上「{title}」是別的陣營掛的，這一張作廢。"  # 待 joy 潤（FB-151：投靠、叛投那一下；換版前就換了陣營的存檔由 deliver_lapses 補同一句）
LAPSED_LEAN = "【懸賞】你改幫{faction}，手上「{title}」是{poster}掛的，這一張作廢。"  # 待 joy 潤（FB-811：三陣營四勝利開著、豪強改幫另一軍那一下；不能用 LAPSED_SIDE 的「改投」，上一行才說改幫不算叛投）
STRANDED_JOIN = "投靠之後，手上 {n} 張別的陣營掛的懸賞會作廢。"  # 待 joy 潤（FB-151：投靠的確認畫面）
STRANDED_LOST = "手上 {n} 張{faction}掛的懸賞作廢"  # 待 joy 潤（FB-151：叛投確認畫面「會失去」清單裡的一項，faction 是舊陣營）
WANTED_NEWBIE = "你初入江湖，還在新手期，截殺不了人，這張通緝先別揭。"  # 待 joy 潤（FB-154：揭的人自己還在截殺的新手期；跟 post_problem 的「…初入江湖，還在新手期，通緝不了他。」同一個口氣）
HELD_FULL = "你手上已經有 {count} 張了，先交了差再說。"  # 待 joy 潤（FB-155：count 是手上真的有幾張，不是上限；截殺關了又開時可以超過上限）
BOARD_EMPTY = "榜上的懸賞都有人交了。"  # 待 joy 潤（FB-156：榜開著、看得到的單被別人交光，第二層只剩「返回」時灰掉的那一行；Game._bounty_options 的 bounty:empty）
NOT_HELD = "你手上沒有這一張。"  # 待 joy 潤：放棄一張手上沒有的（drop）；Game._bounty 照它記掌櫃的情況
PRIZE_GATE = "這張重賞的單，名動一方以上的人才揭得到。"  # 名聲 4.2（take_problem；店面告示照它灰掉、寫原因）
OFFICIAL = "官府"  # 官府通緝（名聲 5.4）的掛單人
OFFICIAL_GATE = "要{title}才揭得了官府的海捕文書"  # 待 joy 潤（名聲 5.4：俠一路一方豪俠以上才揭得了）
POSTED_FACTION = "{faction}貼出了通緝你的告示（{title}）。"  # 待 joy 潤（名聲 4.6：被掛的人收到）
POSTED_OFFICIAL = "官府貼出了海捕文書，畫的是你（{title}）。"  # 待 joy 潤（名聲 5.4）
BEATEN_OFFICIAL = "惡名 -{n}（你被揭了官府海捕文書的{winner}打敗了）"  # 待 joy 潤（名聲 5.4：被截殺的寇那一份）
UNPICK_ID = "bounty:unpick"  # 第三層最後一顆（hand_in_options）：店面認得它（shopview.BACKS）


def active(state: GameState, content: Content) -> bool:
    """懸賞榜開著：設定開著（Config.bounties.enabled）、劇本有陣營（沒有陣營就沒有人掛單）、這一季還沒收（休季沒有榜：不開榜、不掛單、
    卡上沒有通緝鈕，FB-152）。不看第一季開關（懸賞榜設計 2.2）。作廢與退押金（deliver_lapses、deliver_refunds）不問這一個：
    收季之後揭著的人、掛單的人同步時才收到那一句與押金。"""
    return content.config.bounties.enabled and bool(content.scenario.factions) and not state.world.ended


def is_town(content: Content, loc_id: str) -> bool:
    loc = content.locations[loc_id]
    return content.config.explore_mix_of(loc.tags).kind == "town"


def board_here(state: GameState, content: Content) -> bool:
    """這裡看得到懸賞榜：懸賞榜開著（active）、人在城鎮類的地點、這一季走到開榜的那一週（減法季 6.6 第 2 週，week_unlock.open；
    規則關著一律開）。榜鎖著時系統通緝照掛（post_auto 不問這裡）、揭了的單照交，只是榜不畫、不能揭新的。"""
    from . import week_unlock  # 繞回來的 import，呼叫時才取

    return active(state, content) and is_town(content, state.player.location) and week_unlock.open(state, content, "bounties")


def close_board(p: PlayerState) -> None:
    """收起懸賞榜：選單、第三層挑到哪一張、店面上榜吏那一句（店面獨立介面設計 1.4）一起清。凡是把 picking_bounty 設成 False 的地方
    都走這裡（離開、讀檔修補、出發），同 equipment.close_smith。"""
    p.picking_bounty, p.bounty_pick = False, None
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""


def week_seconds(state: GameState, content: Content) -> float:
    """通緝的「一週」（post_weeks 照它退押金）：季曆一週；7 天濃縮季是一段的平均（calendar.week_seconds）。"""
    return calendar.week_seconds(content, state.world)


def quota(content: Content) -> int:
    cfg = content.config
    return max(cfg.bounties.quota_min, math.ceil(cfg.bounties.quota_base * cfg.server_max_players / 100))


def _loc_name(content: Content, loc_id: str | None) -> str:
    return content.locations[loc_id].name if loc_id in content.locations else ""


def _noun(b: Bounty) -> str:
    """求兵要的那一種兵器寫成玩家看的字：照 weapons.NOUNS（拳腳寫「拳套」、弓弩寫「弩」，跟兵器名、鐵匠鋪挑種類那一步同一套；
    「一把屬剛的拳腳」不通）。FB-133（同一把一下寫拳套、一下寫拳腳）還沒定案，joy 定了另一種寫法就改這裡。"""
    return weapons.NOUNS.get(b.weapon_kind or "", b.weapon_kind or "")


def unit_of(b: Bounty) -> str:
    """求兵照兵器的量詞（拳套一副、其他一把；FB-160）；其他種類沒有量詞。"""
    return weapons.unit(b.weapon_kind or "") if b.kind == "arms" else ""


def title(content: Content, b: Bounty) -> str:
    """短標題：「討伐・黃巾游騎（南陽郊野）」「打探・嵩山深處」「護送・新野→宛城」「通緝・某某」「求兵・屬柔的劍」。"""
    kind = KIND_NAMES.get(b.kind, b.kind)
    if b.motive == "求援":  # 人物對整個陣營發的（大勢人物擴充第三批）：「求援・汝南的黃巾軍」「求援・嵩山深處」
        where = f"{_loc_name(content, b.location)}的{_enemy_name(content, b)}" if b.kind == "strike" else _loc_name(content, b.location)
        return f"求援・{where}"
    if b.kind == "arms":
        return f"{kind}・屬{b.attribute}的{_noun(b)}"
    if b.kind == "strike" and b.motive in ("復仇", "追剿"):  # 人物掛的（大勢人物擴充第二批）：「復仇・汝南的官軍」
        return f"{b.motive}・{_loc_name(content, b.location)}的{_enemy_name(content, b)}"
    if b.kind == "strike":
        return f"{kind}・{_loc_name(content, b.location)}的{_enemy_name(content, b)}"
    if b.kind == "escort":
        return f"{kind}・{_loc_name(content, b.location)}→{_loc_name(content, b.end)}"
    if b.kind == "wanted" and b.auto_by is not None:  # 系統掛的（名聲 4.6、5.4）：「官府通緝・某某（江湖巨寇）」「黃巾軍通緝・某某（威震州郡）」
        return f"{issuer(content, b)}{kind}・{b.target}" + (f"（{b.renown_title}）" if b.renown_title else "")
    if b.kind == "wanted":
        return f"{kind}・{b.target}"
    return f"{kind}・{_loc_name(content, b.location)}"


STRIKE_SORTIE = "出陣攻打贏"  # 待 joy 潤（FB-249）：出陣開著時討伐怎麼交差
STRIKE_GATHER = "找素材撞上的那一場也算"  # 待 joy 潤：探索三選一開著時多的那半句（散人不出陣，討伐靠這裡）
# 一類一顆生效的季（FB-420）：找素材不打仗，討伐在練功交差（待 joy 潤）
STRIKE_PRECISE = "到{target}尋敵或出陣攻打贏一場{enemy}的隊伍"
STRIKE_PRACTICE = "到{target}尋敵打贏一場{enemy}的隊伍"


def how(content: Content, b: Bounty, state: GameState | None = None, world: WorldState | None = None) -> str:
    """怎麼完成（一句）。討伐在出陣開著時寫出陣攻（與探索三選一的找素材撞上），不寫遊歷（FB-249）；一類一顆在這一季生效時
    （precise.on，要給 state 或 world）寫練功（FB-420：找素材不打仗了），看的人是散人（不出陣）只寫練功。懸賞卡、告示、紙上、揭下的回話、
    傳聞與書信都走這一句；只給 world 的（陣營傳聞，沒有看的人）照陣營的人寫（FB-435）。"""
    world = state.world if state is not None else world
    if b.motive == "求援":  # 求援委託：護衛、犒軍那位人物也算（大勢人物擴充第三批，跟「大勢人物參戰與護衛」對齊）
        return how(content, b.model_copy(update={"motive": None}), state, world) + RALLY_AID.format(who=issuer(content, b))
    if b.kind == "strike":
        from . import explore_modes, precise, sortie  # 延後 import 只是保險

        target = _loc_name(content, b.location)
        if precise.on(content, world):
            ranger = state is not None and state.player.faction is None  # 散人不出陣
            line = STRIKE_PRECISE if sortie.on(content) and not ranger else STRIKE_PRACTICE
            return line.format(target=target, enemy=_enemy_name(content, b))
        if sortie.on(content):
            ways = f"{STRIKE_SORTIE}，{STRIKE_GATHER}" if explore_modes.on(content) else STRIKE_SORTIE
            return f"到{target}打贏一場{_enemy_name(content, b)}的隊伍（{ways}）"
        return f"到{target}遊歷，打贏一場{_enemy_name(content, b)}的隊伍"
    if b.kind == "scout":
        return f"到{_loc_name(content, b.location)}探索一次"
    if b.kind == "escort" and b.motive == "委託":  # 書信附的委託：信已經在你手上
        return f"替{issuer(content, b)}把書信送到{_loc_name(content, b.end)}"
    if b.kind == "escort":
        return f"在{_loc_name(content, b.location)}接下，走到{_loc_name(content, b.end)}"
    if b.kind == "arms":  # 待 joy 潤；手上那把也收（企劃者 2026-10-10，懸賞榜設計 14.1 丙）
        return f"在城鎮的懸賞榜交出一{unit_of(b)}屬{b.attribute}的{_noun(b)}（裝備庫裡、手上的都行，什麼品質都收，交了就沒了）"
    return f"找到{b.target}，在對方的玩家卡上截殺並打贏"


def _enemy_name(content: Content, b: Bounty) -> str:
    return content.scenario.faction_name(ENEMY.get(b.faction or "")) or "敵軍"


def enemy_name(content: Content, b: Bounty) -> str:
    """討伐要打的那一方（figure_life 寫復仇懸賞那一句用）。"""
    return _enemy_name(content, b)


def issuer(content: Content, b: Bounty) -> str:
    if b.figure is not None and b.figure in content.characters:  # 人物掛的、人物託的（大勢人物擴充第二批）
        return content.characters[b.figure].name
    if b.auto_by == "官府":  # 名聲 5.4
        return OFFICIAL
    return content.scenario.faction_name(b.faction) or "江湖"


def _left(b: Bounty) -> int:
    return b.quota - len(b.done_by)


def to_season_end(b: Bounty, content: Content, world: WorldState) -> bool:
    """這一張的期限寫「到季末」：到期在名義季末（calendar.nominal_end：季長照開季時蓋的章）或之後。第 11 週掛的正好到季末、第 12 週掛的在季末後一週。
    比的是名義季末，不是真正收季的時刻：第一季管理者可以把季末往後排（Game.admin_schedule），這種單要撐到季真的收了（past_due）。
    照現實天的季（21 天、7 天）名義季末要扣開季偏移（FB-500：週三 14:00 開的 7 天季季末是 7 天減 14 小時，以前比季長 × DAY，
    剛好在季末到期的第 6 天那一批判不成「到季末」）；週末、14 天的季偏移是 0，照舊是季長 × DAY。"""
    return b.expires >= calendar.nominal_end(content, world) - calendar.EPS_SECONDS


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


def due_short(b: Bounty, content: Content, world: WorldState) -> str:
    """店面告示上那一行短的（FB-196，草圖「期限 第 6 週・剩 2」）：第一季只寫週次、規則關著只寫第幾天，到季末寫「到季末・剩 N」。
    兩欄的告示在 375 寬放不下 due_line 那一整行；完整的時刻與「名額還剩 N」留在點開的紙上。待 joy 潤：寫法。
    週次寫最後還有效的那一週（PM 2026-10-14）：自動掛的單在第 N 週週一 00:00 到期，第 N 週一開始就過了，寫「到第 N−1 週」；
    到期不在週一 00:00 的（管理者改過、照實際時刻的）寫到期那一刻所在的週「期限 第 N 週」。第 1 週週一 00:00 沒有前一週，照後者寫。
    7 天濃縮季（week7_on）週是段，對不上任何東西：每一張都照到期那一刻寫第幾天（00:00 到期寫「到第 N−1 天」，其餘「期限 第 N 天」），
    不分每天掛的那一批、大勢人物的追剿復仇、系統與玩家掛的通緝（FB-506）；其他季一個字不變（21 天季仍只有每天那一批寫週幾，其餘寫週次）。"""
    left = _left(b)
    if to_season_end(b, content, world):
        return f"{SEASON_END}・剩 {left}"
    if calendar.week7_on(world, content):  # 7 天濃縮季：只寫第幾天（calendar.point_text 的 by_day；待 joy 潤）。不看 b.day：追剿、復仇、系統與玩家掛的通緝沒有第幾天，也照到期那一刻寫（FB-506）
        at = calendar.point(b.expires, content, world)
        if (at.hour, at.minute) == (0, 0):
            return f"到第 {calendar.point(b.expires - 1, content, world).cal_day} 天・剩 {left}"
        return f"期限 第 {at.cal_day} 天・剩 {left}"
    if b.day and calendar.season21_on(world, content):  # 21 天季每天一批：在某天 00:00 到期，寫最後還有效的那一天（待 joy 潤）
        at = calendar.point(b.expires, content, world)
        if (at.hour, at.minute) == (0, 0):
            last = calendar.point(b.expires - 1, content, world)
            return f"到第 {last.week} 週週{calendar.WEEKDAYS[last.weekday]}・剩 {left}"
        return f"期限 第 {at.week} 週週{calendar.WEEKDAYS[at.weekday]}・剩 {left}"
    if calendar.season_one_on(world, content):
        at = calendar.point(b.expires, content, world)
        if (at.weekday, at.hour, at.minute) == (0, 0, 0) and at.week > 1:
            return f"到第 {at.week - 1} 週・剩 {left}"
        return f"期限 第 {at.week} 週・剩 {left}"
    return f"期限 {calendar.day_text(b.expires)}・剩 {left}"


def open_bounties(state: GameState, content: Content) -> list[Bounty]:
    """榜上還有效的（沒過期〔past_due〕、還有名額）；休季（active 為假）一張都沒有。截殺關著（Config.raid.enabled）時通緝不算：只能靠截殺交差，揭了也交不了
    （mine、take、hunting、status、整季機器人與假人都經過這裡，自然看不到、揭不了、不佔格）；押金照期限退（deliver_refunds 直接掃榜）。"""
    if not active(state, content):
        return []
    w, raids = state.world, content.config.raid.enabled
    return [b for b in w.bounties if not past_due(b, content, w) and _left(b) > 0 and (raids or b.kind != "wanted")]


def army_of(state: GameState, content: Content) -> str | None:
    """站哪一軍（名聲 4.6）：照 rules.side_of（就是 allied.side_of；豪強分屬兩軍的季，依附官軍或黃巾的豪強是那一軍），
    只認官軍、黃巾；散人、沒有依附的第三方豪強（14 天的季）是 None。"""
    side = allied.side_of(state, content)
    return side if side in ENEMY else None


def _side_ok(side: str | None, b: Bounty) -> bool:
    """陣營這一關（_takeable 的後半、deliver_lapses 的換陣營那一條共用；side 是那一邊，_side）：官府通緝不看陣營（名聲 5.4）；
    其餘（含陣營通緝，名聲 4.6）散人兩邊都能接、陣營的人只接自己那一邊的（依附的豪強照依附那一軍）。"""
    if b.auto_by == "官府":
        return True
    return side is None or side == b.faction


def _takeable(name: str, faction: str | None, b: Bounty) -> bool:
    """name 這個人、投靠 faction（None 是散人）接不接得了這一張：can_take 與 stranded（換陣營之後還接不接得了）共用這一套。
    官府通緝的稱號只在揭的那一刻看（take_problem），之後掉段照留。"""
    if b.kind == "wanted" and name_key(b.target or "") == name_key(name):
        return False
    if b.poster is not None and name_key(b.poster) == name_key(name):
        return False
    return _side_ok(faction, b)


def _side(state: GameState) -> str | None:
    """敵我照那一邊（同 allied.side_of）：豪強分屬兩軍的季依附了一軍的人是那一軍。PlayerState.ally 只在那種季寫（投靠那一下照
    allied.on），換季角色重來，所以手上沒有 content 的地方（can_take）照它讀也一樣。"""
    p = state.player
    return p.ally or p.faction


def can_take(state: GameState, b: Bounty) -> bool:
    """這個人接不接得了這一種：散人兩邊都能接；陣營的人只能接自己陣營的（豪強分屬兩軍：依附那一軍的）；通緝不能接自己的。"""
    return _takeable(state.player.name, _side(state), b)


def stranded(state: GameState, content: Content, faction_id: str | None) -> list[Bounty]:
    """手上揭著、還沒交、還有效，可是投靠 faction_id 之後就接不了（同 can_take 的規則）的單（FB-151：投靠、叛投那一下要作廢的）。
    投靠的確認畫面、叛投的確認畫面用它數張數，drop_stranded 用它拿掉名字。過期的、名額滿的不算（open_bounties 已經濾掉；它們由 deliver_lapses 說原因，而陣營的原因排第一，所以一張又過期又接不了的單，說的是陣營那一句）；
    求兵沒人揭，不會在裡面。"""
    p = state.player
    me = name_key(p.name)
    return [
        b for b in open_bounties(state, content)
        if me in (name_key(t) for t in b.takers) and me not in (name_key(t) for t in b.done_by)
        and not _takeable(p.name, faction_id, b)
    ]


def stale_line(state: GameState, content: Content, world: WorldStateStore, arg: str) -> str:
    """懸賞選項（Game.choose 的 bounty:<arg>）已經不在選單上時回給玩家的一句（FB-162：兩個分頁搶同一張、慢的那一頁按下去）。
    arg 是 bounty: 後面那一段（take／drop／pick／give:懸賞 id:東西 id…）。找不到那一張了是 GONE；交出的先看引擎自己的拒絕
    （give_problem：交過了、東西不在了、名額滿了……，跟照舊的 give 同一套話）；都沒有更具體的原因就是 STALE。
    只讀，不改狀態、不寫紀錄。"""
    verb, _, rest = arg.partition(":")
    bounty_id, _, item = rest.partition(":")
    if verb in ("take", "drop", "pick", "give"):
        b = next((x for x in state.world.bounties if x.id == bounty_id), None)
        if b is None:
            return GONE
        if verb == "give":
            return give_problem(state, content, world, b, item) or STALE
    return STALE


def join_note(state: GameState, content: Content, choice: Choice) -> str:
    """事件選項會拜入陣營名下的門派（Effect.join_sect）、因而投靠那個陣營時，手上有新陣營接不了的懸賞：選項那一行後面多一個括號，
    寫跟投靠的確認畫面同一句（STRANDED_JOIN，張數照 stranded 數；FB-159，原本只有選下去之後才補作廢的句子）。
    已經有陣營的人拜入不換陣營（rules.apply_effect），門派不歸任何陣營的也不會，這兩種都沒有；成功與失敗的效果都看（先成功）。
    沒有要警告的是空字串。"""
    if state.player.faction is not None:
        return ""
    for effect in (choice.effect, choice.fail_effect):
        owner = content.scenario.sect_owner(effect.join_sect) if effect.join_sect else None
        held = stranded(state, content, owner.id) if owner is not None else []
        if held:
            return f"（{STRANDED_JOIN.format(n=len(held))}）"
    return ""


def drop_stranded(state: GameState, content: Content, faction_id: str | None, *, lean: bool = False) -> list[str]:
    """投靠或叛投 faction_id 的那一下（Game.choose、defection.defect）：手上新陣營接不了的單拿掉名字，每張回一句原因（FB-151）。
    lean：豪強改幫另一軍（Game._lean_step，三陣營四勝利）不是換陣營，那一句寫「改幫…是某某掛的」（LAPSED_LEAN，FB-811），不寫「改投」。
    改的是共用的季（takers），呼叫端的動作結束時存季（choose 的結尾統一存）。要在 p.faction 改之前或之後呼叫都行：只看名字與 faction_id。"""
    me = name_key(state.player.name)
    faction = content.scenario.faction_name(faction_id, "別的陣營")
    msgs: list[str] = []
    for b in stranded(state, content, faction_id):
        b.takers = [t for t in b.takers if name_key(t) != me]
        if lean:
            msgs.append(LAPSED_LEAN.format(faction=faction, poster=content.scenario.faction_name(b.faction, "別的陣營"), title=title(content, b)))
        else:
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
    rule = content.config.renown
    if b.auto_by == "官府" and not renown.meets(state, content, "俠", rule.official_hunter_tier):  # 名聲 5.4：俠一路一方豪俠以上
        return OFFICIAL_GATE.format(title=renown.named(renown.VIRTUE_TITLES["俠"][rule.official_hunter_tier], state))
    if renown.on(content, "prize_gate") and has_prize(content, b) and renown.fame_tier(state, content) < rule.prize_tier:
        return PRIZE_GATE  # 名聲 4.2：重賞給出去之後就是一般的單（has_prize 看 done_by），手上揭著的不收回
    if b.kind == "wanted" and roster.raid_newbie(state, content):  # 通緝只能靠截殺交差，自己還在新手期就截殺不了（Game.raid_refusal）：揭了白佔一格（FB-154）
        return WANTED_NEWBIE
    held = len(mine(state, content))
    if held >= content.config.bounties.max_taken:
        return HELD_FULL.format(count=held)  # 寫手上真的有幾張，不是上限：截殺關了又開，通緝回到手上時會超過上限（FB-155）
    if b.kind == "escort" and p.location != b.location:
        return f"要在{_loc_name(content, b.location)}接。"
    return None


def has_prize(content: Content, b: Bounty) -> bool:
    """這一張還掛著重賞（裝備四欄 6.4）：只給第一個交差的人，給出去了就不再寫；那一欄的裝備關著也不寫。reward_text 與店面告示上的
    「另有重賞」共用。"""
    return bool(b.prize) and not b.done_by and treasures.prize_on(content, b.prize)


class RewardBits(NamedTuple):
    """賞的每一樣（reward_text 接成一行、reward_tags 拆成小籤，兩邊讀同一份）。silver 是寫出來的字（求兵是一段範圍），
    silver_short 只有數字（告示角上的朱印）；deed 是（帳的名字, 功績）或 None；gift 是附的那一樣（不帶開頭的「・」）。"""

    silver: str
    silver_short: str
    exp: int
    xinde: int
    deed: tuple[str, int] | None
    gift: str
    prize: str


def reward_bits(state: GameState, content: Content, b: Bounty) -> RewardBits:
    """賞的那幾樣（照 reward_text 原本的算法）：功績只有散人看得到（ranger.active）；名聲開著時功績記成善名或惡名（deed_word）。
    求兵的銀兩照交的那一把，寫成一段範圍（每顆交出鈕上另寫實拿多少，懸賞榜設計 4.7）；21 天季滿級經驗換成心得（3.5）。"""
    cfg = content.config.bounties
    deeds = b.deeds if ranger.active(state, content) else 0
    exp = _exp(state, content, b)
    xinde = cfg.xinde.get(b.kind, 0)
    if exp and team.maxed(content, state.player.member):  # 滿級：經驗換成心得（3.5，第 8 批起每一種季都是）
        xinde, exp = xinde + team.as_xinde(content, exp), 0
    if b.kind == "arms":
        low, high = (_silver(state, content, b, base=price * cfg.arms_tier["1"])
                     for price in (min(cfg.arms_silver.values()), max(cfg.arms_silver.values())))
        short = f"{low}～{high}"
        silver = f"{short}（照品質，高階另加）"  # 待 joy 潤
    else:
        silver = short = str(_silver(state, content, b))
    gift = ""
    if b.kind in ATTACH_NOTES and _daily_pay(state, content, b):
        gift = ATTACH_NOTES[b.kind].format(pill=content.config.stamina_pill_name)
    prize = treasures.PRIZE_WORDS[b.prize] if has_prize(content, b) else ""  # 重賞只給第一個交差的人，給出去了就不再寫
    return RewardBits(silver, short, exp, xinde, (deed_word(state, content), deeds) if deeds else None, gift.removeprefix("・"), prize)


def reward_text(state: GameState, content: Content, b: Bounty) -> str:
    """賞的那一段（選單、懸賞卡、揭下的回話共用）：「賞銀 20・經驗 15・俠名 +3」，附的那一樣與重賞接在後面（reward_bits）。"""
    r = reward_bits(state, content, b)
    text = f"賞銀 {r.silver}" + (f"・經驗 {r.exp}" if r.exp else "") + (f"・心得 {r.xinde}" if r.xinde else "") \
        + (f"・{r.deed[0]} +{r.deed[1]}" if r.deed else "")
    if r.gift:
        text += f"・{r.gift}"
    if r.prize:
        text += treasures.PRIZE_NOTE.format(what=r.prize)
    return text


def reward_tags(state: GameState, content: Content, b: Bounty) -> list[dict] | None:
    """21 天季的懸賞卡與放大的紙把賞拆成小籤（企劃者挑第 5 批畫面第三組丙）：一樣一格，{"k": 名目, "v": 數字}；附的那一樣
    {"v": …, "kind": "gift"}（金框）、重賞 {"v": …, "kind": "prize"}（紅框）。週末與 14 天的季是 None：網頁照舊寫 reward_text 那一行。"""
    if not calendar.season21_on(state.world, content):
        return None
    r = reward_bits(state, content, b)
    tags = [{"k": "銀", "v": r.silver}]
    if r.exp:
        tags.append({"k": "經驗", "v": str(r.exp)})
    if r.xinde:
        tags.append({"k": "心得", "v": str(r.xinde)})
    if r.deed:
        tags.append({"k": r.deed[0], "v": f"+{r.deed[1]}"})
    if r.gift:
        tags.append({"v": r.gift, "kind": "gift"})
    if r.prize:
        tags.append({"v": PRIZE_TAG.format(what=r.prize), "kind": "prize"})
    return tags


def gift_short(state: GameState, content: Content, b: Bounty) -> str:
    """告示正面附贈那一格（FB-391）：有附的那一樣（reward_bits 的 gift）才有，照種類寫短的；沒有是空字串。"""
    if not reward_bits(state, content, b).gift:
        return ""
    return GIFT_SHORT.get(b.kind, "").format(pill=content.config.stamina_pill_name)


def level_note(state: GameState, content: Content, b: Bounty) -> str:
    """賞照揭的人的等級長的那幾張（_daily_pay）寫「賞照你第 N 級」；其餘空字串。"""
    return LEVEL_NOTE.format(level=state.player.member.level) if _daily_pay(state, content, b) else ""


def deed_word(state: GameState, content: Content) -> str:
    """功績記在哪一本帳的字（reward_text）：名聲開著時照此刻走的路寫善名或惡名（名聲設計 2.3），關著寫俠名。"""
    if not renown.on(content):
        return "俠名"
    key = renown.BOOKS[renown.path(state)]
    return content.config.stat_names.get(key, key)


def _share(state: GameState, content: Content, b: Bounty) -> float:
    """陣營的人做自己陣營掛的討伐、打探、護送只拿 faction_share；通緝的賞金是押金，照數給；求兵拿全額（FULL_PAY）。"""
    if b.kind in FULL_PAY or state.player.faction is None:
        return 1.0
    return content.config.bounties.faction_share


def _silver(state: GameState, content: Content, b: Bounty, base: int | None = None) -> int:
    """實拿的銀兩：這一張的 silver（求兵是 base：交的那一把的 arms_silver × arms_tier，懸賞榜設計 4.7）× 第 4 階散人的加成 × 陣營的成數。
    base 傳的是底數，還沒乘加成：不要在呼叫端先乘，不然會乘兩次。通緝照押金給。"""
    if b.kind == "wanted":
        return b.silver
    amount = b.silver if base is None else base
    if _daily_pay(state, content, b):  # 21 天季（6.1）：等級 × 每級的錢；求兵照那一把再加這一份
        per = content.config.season21_daily.silver_per_level.get(b.kind, 0) * state.player.member.level
        amount = per if base is None else base + per
    return round(amount * ranger.bounty_factor(state, content) * _share(state, content, b))


def _exp(state: GameState, content: Content, b: Bounty) -> int:
    if _daily_pay(state, content, b):  # 21 天季（6.1）：這一級升下一級的經驗 × 比例
        ratio = content.config.season21_daily.exp_ratio.get(b.kind, 0)
        return round(team.level_cost(content.config, state.player.member.level) * ratio * _share(state, content, b))
    return round(content.config.bounties.exp.get(b.kind, 0) * _share(state, content, b))


def _daily_pay(state: GameState, content: Content, b: Bounty) -> bool:
    """這一張照 21 天季的算法給（正式季整合設計 6.1）：賞照揭的人的等級長、討伐打探護送各附一樣東西。通緝照押金，不算。"""
    return calendar.season21_on(state.world, content) and b.kind in content.config.season21_daily.exp_ratio


def _attached(state: GameState, content: Content, world: WorldStateStore, b: Bounty) -> list[str]:
    """21 天季每張附的那一樣（6.1 第 2 點）：討伐給這一路對手屬性的二階一個、另擲 strike_tier3_chance 一個同屬性三階；
    打探給一顆回體丹；護送給終點那一處屬性的二階一個。對手、終點沒寫屬性就照同階隨便一個（materials.by_tier 退回同階全部）。
    自己一份亂數（季數＋名號＋懸賞 id），不碰 Game.rng；陣營的人也全給（一半的只有銀兩與經驗）。"""
    if b.kind not in ATTACH_NOTES or not _daily_pay(state, content, b):
        return []
    if b.kind == "scout":
        state.player.stamina_pills += 1
        return [f"{content.config.stamina_pill_name} +1"]
    rng = random.Random(f"bounty-attach|{world.get_season_number()}|{state.player.name}|{b.id}")
    if b.kind == "strike":
        squad = content.squads.get(b.squad or "")
        attribute = squad.attribute if squad is not None else None
    else:
        loc = content.locations.get(b.end or "")  # 終點的屬性照它的素材（Location.materials 是素材 id，同路邊採集）
        found = [content.materials[m].attribute for m in (loc.materials if loc is not None else []) if m in content.materials]
        attribute = rng.choice(found) if found else None
    msgs: list[str] = []
    tiers = [2] + ([3] if b.kind == "strike" and rng.random() < content.config.season21_daily.strike_tier3_chance else [])
    for tier in tiers:
        pool = materials.by_tier(content, tier, attribute)
        line = materials.grant(state, content, rng.choice(pool).id, 1) if pool else None
        if line:
            msgs.append(line)
    return msgs


def take(state: GameState, content: Content, bounty_id: str) -> list[str]:
    b = next((x for x in open_bounties(state, content) if x.id == bounty_id), None)
    if b is None:
        return ["這張懸賞已經揭下了。"]
    problem = take_problem(state, content, b)
    if problem is not None:
        return [problem]
    if name_key(state.player.name) not in (name_key(t) for t in b.takers):
        b.takers.append(state.player.name)
    return [f"你揭下了「{title(content, b)}」：{how(content, b, state)}。（{reward_text(state, content, b)}；{due_line(state, content, b)}）"]


def drop(state: GameState, content: Content, bounty_id: str) -> list[str]:
    name = name_key(state.player.name)
    for b in state.world.bounties:
        if b.id == bounty_id and name in (name_key(t) for t in b.takers):
            b.takers = [t for t in b.takers if name_key(t) != name]
            return [f"你把「{title(content, b)}」放回了榜上。"]
    return [NOT_HELD]


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
    if exp and team.maxed(content, p.member):  # 滿級：本人的經驗照 5 換 1 換成心得（3.5，team.maxed_xinde），同伴照拿經驗
        gained = team.maxed_xinde(state, content, exp)
        if gained:
            msgs += [team.MAXED_XINDE.format(n=gained), f"心得 +{gained}"]  # 跟其他來源同一句（FB-452）
        msgs += team.add_team_exp(state, content, world, exp)
    elif exp:
        msgs.append(f"經驗 +{exp}")
        msgs += team.add_team_exp(state, content, world, exp)
    msgs += _attached(state, content, world, b)
    msgs[2:2] = ranger.add_deeds(state, content, b.deeds)  # 散人的功績（名聲開著時記成善名或惡名）
    if b.kind != "wanted":  # 通緝照押金給，沒有加成（_silver）
        msgs += renown.ranger_bounty_note(state, content, ranger.bounty_factor(state, content))  # 名聲 6.3：加成說出原因
    if b.prize and first:  # 哪一件到這一刻才定（季數＋名號＋懸賞 id 的亂數）；裝備庫滿了寄放
        msgs += treasures.bounty_prize(state, content, world.get_season_number(), b.id, b.prize, issuer(content, b))
    msgs += _figure_thanks(state, content, b, content.config.figure_life.revenge_affinity)
    return msgs


def _figure_thanks(state: GameState, content: Content, b: Bounty, amount: int) -> list[str]:
    """人物掛的、人物託的（大勢人物擴充第二批）交差了：那位人物的情誼加 amount（最多 100）。"""
    if b.figure is None or b.figure not in content.characters or amount <= 0:
        return []
    p = state.player
    before = p.affinities.get(b.figure, 0)
    p.affinities[b.figure] = min(100, before + amount)
    moved = p.affinities[b.figure] - before
    return [f"{content.characters[b.figure].name}情誼 +{moved}"] if moved else []


RALLY_AID = "；或去護衛、犒軍{who}"  # 待 joy 潤
RALLY_DONE = "【求援】{who}的求援你辦成了：「{title}」。"  # 待 joy 潤
RALLY_POSTED = "{who}向{side}各路同袍求援：{how}。"  # 待 joy 潤：陣營軍情


def rallies(state: GameState, content: Content) -> list[Bounty]:
    """我看得到、還辦得了的求援委託（WorldState.rallies；大勢人物擴充第三批）：掛單的是我這一邊（army_of：官軍、黃巾，依附的豪強
    照依附那一軍）、沒過期、還有名額、我還沒辦過。不用揭，辦成了前 quota 個有賞。懸賞榜關著、休季沒有。"""
    w = state.world
    side = army_of(state, content)
    if not active(state, content) or side is None:
        return []
    me = name_key(state.player.name)
    return [b for b in w.rallies
            if b.faction == side and b.expires > w.time and _left(b) > 0 and me not in (name_key(t) for t in b.done_by)]


def _complete_rally(state: GameState, content: Content, b: Bounty) -> list[str]:
    """求援委託辦成了：銀兩 b.silver（同委託，不乘加成）、那位人物情誼 +rally_affinity，他寫一封道謝信。"""
    from . import letters  # letters → bounties

    p = state.player
    b.done_by.append(p.name)
    p.stats["silver"] = p.stats.get("silver", 0) + b.silver
    msgs = [RALLY_DONE.format(who=issuer(content, b), title=title(content, b))]
    if b.silver:
        msgs.append(f"銀兩 +{b.silver}")
    msgs += _figure_thanks(state, content, b, content.config.figure_life.rally_affinity)
    return msgs + letters.thank(state, content, b)


def on_aid(state: GameState, content: Content, cid: str) -> list[str]:
    """護衛、犒軍了大勢人物（對話人物 id cid；Game._aid_act）：他發的求援委託算辦成。"""
    msgs: list[str] = []
    for b in rallies(state, content):
        if b.figure == cid:
            msgs += _complete_rally(state, content, b)
    return msgs


def rally_reward(content: Content, b: Bounty) -> str:
    """求援委託的賞：「賞銀 30・皇甫嵩情誼 +5」（名額寫在 due_line）。待 joy 潤。"""
    parts = [f"賞銀 {b.silver}"] if b.silver else []
    amount = content.config.figure_life.rally_affinity
    if amount and b.figure in content.characters:
        parts.append(f"{content.characters[b.figure].name}情誼 +{amount}")
    return "・".join(parts)


def post_rally(state: GameState, content: Content, cid: str) -> Bounty | None:
    """cid（大勢人物）對自己陣營全部人發一件求援委託（figure_life.tick：心事焦慮時擲中）：在他所在那一區，有對頭站著的地方就討伐，
    否則打探那一區危險度 2 以上、不是城鎮的地方。同一位一次一件。懸賞榜關著、他不是交戰兩軍、那一區什麼都挑不出來回 None。"""
    from . import atlas, figure_life  # atlas → world → rules：延後載入

    side = figure_life.side_of(content, cid)
    w, tuning = state.world, content.config.figure_life
    if not active(state, content) or side not in ENEMY:
        return None
    if any(b.figure == cid and b.expires > w.time and _left(b) > 0 for b in w.rallies):
        return None
    spot = figure_life.where(state, content, cid)
    region = figure_life._region(content, spot)
    if region is None:
        return None

    def in_region(loc_id: str) -> bool:
        found = atlas.region_of(content, loc_id)
        return found is not None and found.id == region

    rng = random.Random(f"求援|{w.tianji}|{cid}|{w.time}")
    spec: dict
    strikes = [x for x in _strike_spots(content, w, side, set()) if in_region(x[0])]
    if strikes:
        loc, squad = rng.choice(strikes)
        spec = {"kind": "strike", "location": loc, "squad": squad}
    else:
        scouts = [loc_id for loc_id, loc in content.locations.items()
                  if loc.danger >= 2 and not is_town(content, loc_id) and _opened(loc, w) and in_region(loc_id)]
        if not scouts:
            return None
        spec = {"kind": "scout", "location": rng.choice(scouts)}
    w.bounty_seq += 1
    made = Bounty(
        id=f"r{w.bounty_seq}", faction=side, week=calendar.point(w.time, content, w).week,
        expires=w.time + tuning.rally_cal_days * 24 * calendar.cal_hour_seconds(content, w),
        silver=tuning.rally_silver, deeds=0, quota=tuning.rally_quota, figure=cid, motive="求援", **spec,
    )
    w.rallies = [b for b in w.rallies if b.expires > w.time][-20:] + [made]
    return made


COMMISSION_DONE = "【委託】{who}託你的事辦成了：「{title}」。"  # 待 joy 潤


def open_commissions(state: GameState, content: Content) -> list[Bounty]:
    """身上還沒辦完、沒過期、沒婉拒的委託（求援書信附的，letters.py）。休季沒有。"""
    w = state.world
    if w.ended:
        return []
    return [x.task for x in state.player.letters
            if x.task is not None and not x.lapsed and not x.task.done_by and x.task.expires > w.time]


def _complete_commission(state: GameState, content: Content, b: Bounty) -> list[str]:
    """委託辦成了：銀兩 b.silver（不乘散人加成與陣營成數，委託是那位人物私下給的）、那位人物情誼 +commission_affinity。"""
    p = state.player
    b.done_by.append(p.name)
    p.stats["silver"] = p.stats.get("silver", 0) + b.silver
    msgs = [COMMISSION_DONE.format(who=issuer(content, b), title=title(content, b))]
    if b.silver:
        msgs.append(f"銀兩 +{b.silver}")
    from . import parley  # parley → bounties：延後載入

    settled = parley.settle_task(state, content, b.id, b.figure)  # 第二批：欠他的那一件（先做後付、接了他的請託）做到了，守約 +1
    if b.parley_ask:  # NPC 智能 2.0的條件（parley.py）：辦成了，下回見面他兌現答應你的那一件
        p.parley_owed[b.figure] = b.parley_ask
        msgs.append(parley.COMMISSION_OWED.format(name=issuer(content, b)))
        if not settled:  # 你求他、他開的條件：做到了也記一筆守約
            parley.keep(state, content, b.figure, title(content, b))
    return msgs + _figure_thanks(state, content, b, content.config.figure_life.commission_affinity)


def _done(state: GameState, content: Content, world: WorldStateStore, match) -> list[str]:
    msgs: list[str] = []
    for b in mine(state, content):
        if match(b):
            msgs += _complete(state, content, world, b)
    for b in open_commissions(state, content):  # 求援書信附的委託（大勢人物擴充第二批）：照同一套交差
        if match(b):
            msgs += _complete_commission(state, content, b)
    for b in rallies(state, content):  # 求援委託（第三批）：不用揭，自己這一邊的人辦成就算
        if match(b):
            msgs += _complete_rally(state, content, b)
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


def official_hit(state: GameState, content: Content, target: str) -> bool:
    """我手上揭著官府通緝這個人（名聲 5.4）：截殺打贏時被打的寇惡名少一點（Game.raid 交差之前先問）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and b.auto_by == "官府" and name_key(b.target or "") == key for b in mine(state, content))


def hunting(state: GameState, content: Content, target: str) -> bool:
    """我接了通緝這個人、還沒完成（截殺的鈕看它：散人、同陣營的人也能對他下手）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and name_key(b.target or "") == key for b in mine(state, content))


# ── 求兵：在懸賞榜上直接交（懸賞榜設計第四節；求藝企劃者 2026-10-21 拿掉）──────────────────────────────


def _weapon(state: GameState, item_id: str) -> Weapon | None:
    """手上那把或裝備庫的武器欄裡 id 是 item_id 的那一把（求兵准交手上那把，企劃者 2026-10-10，14.1 丙）；都沒有是 None。
    裝備庫混放武器與防具（裝備一）：只看武器那一欄，防具 id（「甲:N」）一律當沒有。
    兵器 id 是「兵:3」：呼叫端照 partition 切一次，不要 split。"""
    p = state.player
    if p.weapon is not None and p.weapon.id == item_id:
        return p.weapon
    return next((w for w in equipment.in_slot(p, "weapon") if w.id == item_id), None)


def fit_problem(
    state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str,
) -> str | None:
    """這件東西合不合這一張（設計 4.5 第 3～7 條）；None＝合用。只看東西本身，不看人在哪裡、榜開沒開：江湖頁的懸賞卡
    （status、fitting）人在城外也照它列。拒絕的話待 joy 潤。world 現在沒用到（求藝在的時候查全服的武學），留著呼叫端不必改。"""
    p = state.player
    if b.kind not in GIVE_KINDS:
        return NOT_NOW
    if not can_take(state, b):
        return NOT_YOURS
    if name_key(p.name) in (name_key(t) for t in b.done_by):
        return GIVEN_BEFORE  # 一張一人只交一次
    if not content.config.weapons.enabled:
        return NOT_NOW
    w = _weapon(state, item_id)
    if w is None:
        return NO_WEAPON
    if w.original:
        return SIGNATURE_KEPT if w.signature is not None else ORIGINAL_KEPT  # 5.4：一季全服只有一把，交了就上不了神器譜（本命兵器同）；仿品照一般兵器收（_arms_base 照三階上品）
    if w.kind != b.weapon_kind or w.attribute != b.attribute:
        return WANT_ARMS.format(attribute=b.attribute, noun=_noun(b))
    return None


def _cheapness(content: Content, w: Weapon) -> tuple:
    """「最不值錢的先」（設計 4.4）：照賞銀的底數（_arms_base：arms_silver[品質] × arms_tier[階]，底數低的先；PM 2026-10-12，
    三階下品 80 比一階中品 35 值錢，不照品質優先）、鋒利度（低的先）、id。"""
    return (_arms_base(content, w), w.edge, w.id)


def fitting(state: GameState, content: Content, world: WorldStateStore, b: Bounty) -> list[str]:
    """這一張合用的那幾件 id（fit_problem 過得了），最不值錢的先。不看人在哪裡（卡片在城外也列）。不是求兵是空的。"""
    if b.kind != "arms":
        return []
    p = state.player
    held = ([p.weapon] if p.weapon is not None else []) + equipment.in_slot(p, "weapon")
    items = [w for w in held if fit_problem(state, content, world, b, w.id) is None]
    return [w.id for w in sorted(items, key=lambda w: _cheapness(content, w))]


def _arms_base(content: Content, w: Weapon) -> int:
    """求兵交這一把的銀兩底數（設計 4.7）：arms_silver[品質] × arms_tier[階]，還沒乘名號加成（交給 _silver 乘）。淬煉不加錢。"""
    cfg = content.config.bounties
    return cfg.arms_silver[w.quality] * cfg.arms_tier[str(w.tier)]


def pick_label(state: GameState, content: Content, b: Bounty, count: int) -> str:
    """懸賞榜第二層，交得出的求兵那一行（設計 4.3 第 1 點）：「交出… 官軍・求兵・屬柔的劍（賞…；你有 2 把合用；期限…・名額還剩 3）」。
    待 joy 潤（整行；Task 4 的 test_the_board_lists_hand_ins_first_then_takes_then_one_greyed_line 鎖了整行，潤了一起改）。"""
    return (f"交出… {issuer(content, b)}・{title(content, b)}（{reward_text(state, content, b)}；你有 {count} {unit_of(b)}合用；"
            f"{due_line(state, content, b)}）")


def only_original(state: GameState, b: Bounty) -> str:
    """這一張求兵，身上（手上那把或裝備庫）有種類與屬性都對得上的、可是是神器原品或名將本命兵器（fit_problem 回 ORIGINAL_KEPT／
    SIGNATURE_KEPT）：交不出的原因不是「沒有對得上的兵器」（FB-145）。回灰掉那一行裡接在這一張後面的字：對得上的裡面有神器原品回
    ONLY_ORIGINAL（兩樣都有時說原品），只有本命兵器回 ONLY_SIGNATURE，都沒有是空字串。只在交不出的那幾張上問（engine 的懸賞榜
    第二層），所以「只有原品」由呼叫端保證。"""
    if b.kind != "arms":
        return ""
    p = state.player
    held = ([p.weapon] if p.weapon is not None else []) + equipment.in_slot(p, "weapon")
    fitting = [w for w in held if w.original and w.kind == b.weapon_kind and w.attribute == b.attribute]
    if any(w.signature is None for w in fitting):
        return ONLY_ORIGINAL
    return ONLY_SIGNATURE if fitting else ""


def stuck_label(content: Content, asks: list[Bounty], kept: dict[str, str] | None = None) -> str:
    """懸賞榜第二層，交不出的求兵收成的那一行灰掉的（設計 4.3 第 3 點）：選單才不會長到手機第一屏放不下（FB-128）。
    kept：身上只有神器原品或本命兵器對得上的那幾張（only_original）的 id → 接在後面的字（ONLY_ORIGINAL／ONLY_SIGNATURE，FB-145）。"""
    kept = kept or {}
    return STUCK.format(titles="、".join(f"{issuer(content, b)}・{title(content, b)}" + kept.get(b.id, "") for b in asks))


def pick_line(content: Content, b: Bounty) -> str:
    """按了「交出…」的回話（待 joy 潤）。"""
    return PICKED.format(what=f"{issuer(content, b)}・{title(content, b)}")


def is_browse_line(line: str) -> bool:
    """這一行是不是挑一件、回到懸賞榜的回話（pick_line、UNPICKED）：Game.choose 照它判斷這一下只是翻頁、不寫紀錄（FB-161）。"""
    head, _, tail = PICKED.partition("{what}")
    return line == UNPICKED or (len(line) > len(head) + len(tail) and line.startswith(head) and line.endswith(tail))


def _offer(state: GameState, content: Content, b: Bounty, item_id: str) -> tuple[str, str]:
    """第三層一顆交出鈕的（標籤, 確認句）（設計 4.4，待 joy 潤）：寫階品、鋒利度、實拿多少銀兩（照 _silver：散人第 4 階的加成算在
    裡面），淬過的寫明不加錢，手上那把寫明交了就空手。"""
    who = issuer(content, b)
    w = _weapon(state, item_id)
    held = w is state.player.weapon
    silver = _silver(state, content, b, base=_arms_base(content, w))
    ask = f"把【{w.name}】（{weapons.grade(w)}）交給{who}？交了就沒了。"
    if w.tempers:
        ask += TEMPERED_NOTE.format(n=w.tempers)
    if held:
        ask += HELD_NOTE.format(unit=equipment.unit_for("weapon", w.kind))
    return f"交出【{w.name}】（{weapons.grade(w)}・鋒利度 {w.edge}{'・在手上' if held else ''}）→ 賞銀 {silver}", ask


def hand_in_options(
    state: GameState, content: Content, world: WorldStateStore, b: Bounty, items: list[str],
) -> list:
    """懸賞榜第三層（替 b 挑一件，設計 4.4）：合用的（items，fitting 排好的）最不值錢的 give_list 件各一顆交出，每顆先問一次
    （確認只在網頁那一層；give 自己整個重驗）；多的收成一行灰掉的；最後永遠按得下去的「回到懸賞榜」。
    只讓交最不值錢的這幾件是有意的：交出去就沒了，該交的是最捨得的。"""
    from .engine import Option  # engine 會 import 這裡（同 smithing.temper_option）

    cfg = content.config.bounties
    opts = []
    for item in items[:cfg.give_list]:
        label, ask = _offer(state, content, b, item)
        opts.append(Option(id=f"bounty:give:{b.id}:{item}", label=label, confirm=ask, confirm_yes=GIVE_YES))
    if len(items) > cfg.give_list:
        opts.append(Option(id="bounty:more", label=MORE.format(n=len(items) - cfg.give_list, unit=unit_of(b)), enabled=False))
    opts.append(Option(id=UNPICK_ID, label=UNPICK))
    return opts


def give_choice(state: GameState, content: Content, world: WorldStateStore) -> tuple[str, str] | None:
    """（懸賞 id, 東西 id）：此地懸賞榜上第一張交得出的求兵，與第三層排第一、按得下去的那一件（最不值錢的；設計 9.1）。
    整季機器人與伺服器假人共用（照 weapons.wanted 的做法），照這個挑、不隨機：同分隨機會把最好的那把交掉。
    手上那把兵器不交（交了要空手、少一截威力；真人看得到確認句自己決定）——設計 9.1 寫的是「排第一的那一件」，跳過手上那把是
    計畫的取捨 3，PM 2026-10-11 確認：整季機器人與伺服器假人不交手上那把，真人可以。城外、榜關著、沒得交是 None。"""
    if not board_here(state, content):
        return None
    held = state.player.weapon.id if state.player.weapon is not None else None
    for b in visible(state, content):
        if b.kind not in GIVE_KINDS:
            continue
        for item in fitting(state, content, world, b)[:content.config.bounties.give_list]:
            if item != held:
                return b.id, item
    return None


def give_problem(state: GameState, content: Content, world: WorldStateStore, b: Bounty, item_id: str) -> str | None:
    """第三層的交出鈕亮不亮、give 真的交之前都走這裡（設計 4.5 第 1、2 條，再接 fit_problem）：懸賞榜看得到、這一張還在榜上。"""
    if not board_here(state, content):
        return NOT_NOW
    if b.id not in {x.id for x in open_bounties(state, content)}:
        return GONE  # 過期了，或名額滿了
    return fit_problem(state, content, world, b, item_id)


def give(state: GameState, content: Content, world: WorldStateStore, bounty_id: str, item_id: str) -> list[str]:
    """交出（設計 4.5～4.7）：整個重驗（確認只在網頁那一層，引擎、假人、腳本都不會先問），交掉那一把（手上那把交了就空手、
    鈍了的提醒重設，不自動換一把上手），再發賞：銀兩照它的品質與階。陣營的人也拿全額；散人另記俠名。"""
    b = next((x for x in state.world.bounties if x.id == bounty_id), None)
    if b is None:
        return [GONE]
    problem = give_problem(state, content, world, b, item_id)
    if problem is not None:
        return [problem]
    p, cfg = state.player, content.config.bounties
    emptied = False
    w = _weapon(state, item_id)
    if p.weapon is w:
        p.weapon, p.edge_warned, emptied = None, False, True
    else:
        p.rack.remove(w)
    msgs = _complete(state, content, world, b, silver=_arms_base(content, w))
    msgs[0] = GIVEN.format(name=w.name, issuer=issuer(content, b), title=title(content, b))
    xinde = cfg.xinde.get(b.kind, 0)
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        msgs.append(f"心得 +{xinde}")
    if emptied:
        msgs.append(EMPTY_HANDS)
    return msgs


# ── 通緝（玩家花銀兩掛的）──────────────────────────────


def post_problem(state: GameState, content: Content, target_state: GameState, amount: int | None = None) -> str | None:
    """通緝這個人按不按得下去：懸賞榜與截殺都開著、你投靠了陣營、他是敵對陣營的人、他過了新手期、你手上沒有還掛著的通緝、錢夠。"""
    if not active(state, content) or not content.config.raid.enabled:
        return "（此刻無法這麼做。）"
    p, t = state.player, target_state.player
    mine, theirs = _side(state), _side(target_state)  # 豪強分屬兩軍：同一邊的不算敵對
    if mine is None or theirs is None or mine == theirs:
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
        id=f"b{w.bounty_seq}", kind="wanted", faction=_side(state), week=calendar.point(w.time, content, w).week,
        expires=w.time + content.config.bounties.post_weeks * week_seconds(state, content), silver=amount,
        deeds=content.config.bounties.deeds.get("wanted", 0), quota=1, poster=p.name, target=target_state.player.name,
    )
    w.bounties.append(b)
    return [f"你押了 {amount} 兩，在懸賞榜上通緝{b.target}。", f"銀兩 -{amount}"]


def post_auto(state: GameState, content: Content) -> list[str]:
    """系統掛的通緝（名聲 4.6、5.4）：在本人這一輪（Game.own_turn_checks：伺服器的 act／act_look、假人自己那一輪）檢查，
    這一週還沒掛就掛，回被掛的人收到的那幾句。兩種可以同時都有：
    - 陣營通緝：威震州郡（wanted_tier）以上、站官軍或黃巾（army_of）的人，對面那一軍掛；散人、第三方豪強不掛。
    - 官府通緝：寇一路江湖巨寇（official_tier）以上，不看陣營（散人的寇也掛）。
    一週一張、名額 1、期限到這一週結束、不用押錢（poster 空著）；新手期、截殺或懸賞榜關著、這一季收了都不掛。只改共用的季。"""
    if not active(state, content) or not content.config.raid.enabled or roster.raid_newbie(state, content):
        return []
    p, w, rcfg = state.player, state.world, content.config.renown
    week = calendar.point(w.time, content, w).week
    me = name_key(p.name)

    def posted(by: str) -> bool:
        return any(b.kind == "wanted" and b.auto_by == by and b.week == week and name_key(b.target or "") == me for b in w.bounties)

    def hang(by: str, faction: str | None, silver: int, title: str) -> None:
        w.bounty_seq += 1
        w.bounties.append(Bounty(
            id=f"b{w.bounty_seq}", kind="wanted", faction=faction, week=week, expires=calendar.week_start(week + 1, content, w),
            silver=silver, deeds=content.config.bounties.deeds.get("wanted", 0), quota=1, target=p.name, auto_by=by,
            renown_title=title,
        ))

    out: list[str] = []
    army, tier = army_of(state, content), renown.fame_tier(state, content)
    enemy = ENEMY.get(army or "")
    if (renown.on(content, "faction_wanted") and enemy is not None and tier >= rcfg.wanted_tier and tier in rcfg.wanted_silver
            and enemy in {f.id for f in content.scenario.factions} and not posted("陣營")):
        title = renown.FAME_TITLES[tier]
        hang("陣營", enemy, rcfg.wanted_silver[tier], title)
        out.append(POSTED_FACTION.format(faction=content.scenario.faction_name(enemy, enemy), title=title))
    vt = renown.virtue_tier(state, content)
    if (renown.on(content, "official_wanted") and renown.path(state) == "寇" and vt >= rcfg.official_tier
            and vt in rcfg.official_silver and not posted("官府")):
        title = renown.virtue_title(state, content) or ""
        hang("官府", None, rcfg.official_silver[vt], title)
        out.append(POSTED_OFFICIAL.format(title=title))
    return out


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
        side = _side(state)
        if side is not None and not _side_ok(side, b):  # 同 _takeable 的陣營那一條（豪強分屬兩軍：依附那一軍；官府通緝不看陣營，名聲 5.4）
            line = LAPSED_SIDE.format(faction=content.scenario.faction_name(side, "別的陣營"), title=name)
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


def prize_rolls_day(tianji: int, day: int, faction: str, content: Content) -> tuple[bool, bool]:
    """21 天季每天每邊的重賞（正式季整合設計 6.1 第 3 點）：寶物、良駒各擲一次（Season21Daily 的機率），種子「天機｜第幾天｜陣營」，
    同 prize_rolls 不碰掛單那一份。"""
    cfg = content.config.season21_daily
    rng = random.Random(f"bounty-prize-day|{tianji}|{day}|{faction}")
    return rng.random() < cfg.prize_treasure_chance, rng.random() < cfg.prize_horse_chance


def _hang_prizes_day(w: WorldState, content: Content, day: int) -> None:
    """21 天季的重賞掛上去（6.1 第 3 點【PM】）：寶物掛當天的討伐、良駒掛當天的打探或護送（那一張沒掛出來就掛討伐，討伐已經有寶物就沒了）。
    那一欄關著的不掛。"""
    for faction in ENEMY:
        today = [b for b in w.bounties if b.day == day and b.faction == faction]
        strike = next((b for b in today if b.kind == "strike"), None)
        second = next((b for b in today if b.kind in ("scout", "escort")), None)
        treasure, horse = prize_rolls_day(w.tianji, day, faction, content)
        if treasure and strike is not None and treasures.prize_on(content, "treasure"):
            strike.prize = "treasure"
        target = second if second is not None else (strike if strike is not None and strike.prize is None else None)
        if horse and target is not None and treasures.prize_on(content, "horse"):
            target.prize = "horse"


def tick(state: GameState, content: Content) -> list[str]:
    """第一季規則關著的季的週初掛單（world.advance_world_state 每一步、world.settle_season_start 開季那一刻）：季曆跨進新的一週
    就掛這一週的（只掛這一週，以前的週不補掛；同一週只掛一次，見 issue 的兩道擋）。每一步最多一小時，所以最多晚一小時掛，
    期限錨在週初、不會跟著延後。不回傳訊息。
    第一季的週初掛鉤跑過的週（hooked_week）也算掛過（FB-157）：bounty_week 上線之前的舊存檔是 0，換版時其中一個程式沒帶週末設定，
    這一季就走到這裡，會把掛鉤已經掛過的那一週再掛一批。掛鉤自己（world.WEEK_HOOKS）先記 hooked_week 再叫 issue，所以這道擋只放在這裡。"""
    w = state.world
    week = calendar.point(w.time, content, w).week
    if week <= w.hooked_week:
        return []
    return issue(state, content, week)


def _opened(loc: Location, w: WorldState) -> bool:
    """這個地點全服來說開放了沒（FB-150：週初掛單只挑已開放的地點，不然揭的人「無法安排前往這裡」、那張單白占一個名額）。
    規則同 atlas.is_unlocked 去掉看人的那一半：不是序章專屬的地點，而且 unlock_flag 沒設或已經在世界旗標裡。
    不 import atlas（它 import rules、orders、figures，怕繞成環），所以在這裡照寫一份；那邊改了這邊要跟著改。"""
    return not loc.prologue_only and (not loc.unlock_flag or loc.unlock_flag in w.flags)


def _strike_spots(content: Content, w: WorldState, faction: str, used: set[str]) -> list[tuple[str, str]]:
    """討伐掛得出去的（地點, 隊伍）：這一方的對頭此刻站在那裡（territory.squads_at：地盤易手照控制方，設計第七節）、地點開放了、
    榜上同一個陣營的討伐還沒用掉。"""
    enemy = ENEMY[faction]
    return [
        (loc_id, sid) for loc_id, loc in content.locations.items() if loc_id not in used and _opened(loc, w)
        for sid in territory.squads_at(w, content, loc_id) if sid in content.squads and content.squads[sid].faction == enemy
    ]


def _strike(content: Content, w: WorldState, faction: str, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    spots = _strike_spots(content, w, faction, used)
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
    """n 個屬性（求兵每一方一個）：先不重複地抽，陣營比屬性多時再補可以重複的。不寫死 3：give_attributes 只要求至少一個，
    少於陣營數時 rng.sample(attributes, 3) 會丟 ValueError（懸賞榜設計 4.1）。"""
    picks = rng.sample(list(attributes), min(n, len(attributes)))
    return picks + [rng.choice(list(attributes)) for _ in range(n - len(picks))]


def commission_reward(state: GameState, content: Content, b: Bounty) -> str:
    """委託的賞（書信那張卡、懸賞卡）：「賞銀 30・張梁情誼 +5」。待 joy 潤。"""
    parts = [f"賞銀 {b.silver}"] if b.silver else []
    amount = content.config.figure_life.commission_affinity
    if amount and b.figure in content.characters:
        parts.append(f"{content.characters[b.figure].name}情誼 +{amount}")
    if b.parley_ask:  # NPC 智能 2.0的條件：辦成了他兌現你求的那一件
        from . import parley  # parley → bounties：延後載入

        parts.append(f"他兌現：{parley.ask_label(content, b.parley_ask)}")
    return "・".join(parts)


def post_figure(state: GameState, content: Content, cid: str, motive: str, region: str | None, spot: str | None) -> Bounty | None:
    """人物掛一張懸賞（大勢人物擴充第二批，figure_life.on_fall）：討伐，掛單的是 cid 那一方，打的是對頭；地點在 region 那一區，
    倒下的地方（spot）有對頭的隊伍就掛那裡，否則照那一區的地點挑（自己一份亂數：天機｜人物｜此刻）。賞銀是一般討伐的
    revenge_silver_scale 倍，掛 revenge_cal_days 個季曆天。懸賞榜關著、cid 不是交戰兩軍、那一區沒有對頭站著的地方、
    同一位人物還有一張有效的同一種，都不掛（回 None）。"""
    from . import atlas  # atlas → world → rules：延後載入

    from .relations import side_of

    side = side_of(content, cid)
    if not active(state, content) or side not in ENEMY or region is None:
        return None
    w, cfg, tuning = state.world, content.config.bounties, content.config.figure_life
    if any(b.figure == cid and b.motive == motive for b in open_bounties(state, content)):
        return None

    def in_region(loc_id: str) -> bool:
        found = atlas.region_of(content, loc_id)
        return found is not None and found.id == region

    spots = [x for x in _strike_spots(content, w, side, set()) if in_region(x[0])]
    if not spots:
        return None
    here = [x for x in spots if x[0] == spot]
    pick = here[0] if here else random.Random(f"人物懸賞|{w.tianji}|{cid}|{w.time}").choice(spots)
    w.bounty_seq += 1
    made = Bounty(
        id=f"b{w.bounty_seq}", kind="strike", faction=side, week=calendar.point(w.time, content, w).week,
        expires=w.time + tuning.revenge_cal_days * 24 * calendar.cal_hour_seconds(content, w),
        silver=round(cfg.silver.get("strike", 0) * tuning.revenge_silver_scale), deeds=cfg.deeds.get("strike", 0),
        quota=quota(content), location=pick[0], squad=pick[1], figure=cid, motive=motive,
    )
    w.bounties.append(made)
    return made


def issue(state: GameState, content: Content, week: int, rng: random.Random | None = None) -> list[str]:
    """週初掛單（第一季：world.WEEK_HOOKS；規則關著的季：tick）：陣營掛的舊單下榜（通緝照自己的期限），兩個陣營各掛 kinds 裡的每一張
    （只挑已開放的地點〔_opened，FB-150：南華觀要等 xi_open 立起來〕，避開榜上還有效〔沒過期、名額沒滿〕的同種單已經用掉的地點，
    不管是哪一週掛的：討伐看同一個陣營、打探不分陣營、護送不重複終點；濾完沒地方可挑就跳過那一張），劇本的每個陣營再各掛
    give_kinds 裡的每一種（求兵）；討伐另外擲重賞（寶物、良駒，_hang_prizes）。不回傳訊息。
    rng 不用（介面跟其他週初掛鉤一樣）。
    兩道擋（懸賞榜設計 3.2）：只掛「這一週」（week 要等於此刻的季曆週，同 orders.issue；不然停機補算、管理者快轉會把以前的週補掛出來），
    這一週掛過了不再掛（bounty_week）。期限錨在週初：week_start(週次＋auto_weeks)，晚掛也不會多掛。"""
    w, cfg = state.world, content.config.bounties
    if calendar.season21_on(w, content):  # 21 天季改走每天那一串（issue_day）
        return []
    if not active(state, content) or week != calendar.point(w.time, content, w).week or week <= w.bounty_week:
        return []
    w.bounty_week = week
    # 自己一份亂數（週次、流水號、此刻的戰況）：不動季的 rng，排在後面的大事擲骰不會因為多了懸賞榜而位移
    # 天機（開季時蓋進季裡）：每一季同一週的單不一樣；天機是 0（測試、量表、功能上線前開的季）時種子一字不差，基準不位移（計畫「要 PM 定的」第 1 條）
    salt = f"|{w.tianji}" if w.tianji else ""
    rng = random.Random(f"bounty|{week}|{w.bounty_seq}|{sorted(w.trends.items())}{salt}")
    _clear_stale(w, content)
    expires = calendar.week_start(week + cfg.auto_weeks, content, w)
    _hang_bills(w, content, rng, cfg.kinds, week=week, day=0, expires=expires)
    # 求兵（懸賞榜設計 4.1；求藝企劃者 2026-10-21 拿掉）：劇本的每個陣營（含地方豪強，照劇本的順序）各掛 give_kinds 裡的每一種；屬性從 give_attributes 挑，
    # 同一期同一種各方不重複，求兵另挑種類（可以重複）。兵器開關關著不掛求兵。另開一份亂數：從上面那一份抽的話，
    # 後面每一張討伐、打探、護送的地點都會位移。種子帶天機（天機是 0 時照舊），每一季第 1 週的屬性不再一樣（設計 14.2 第 7 條，裝備三一起做）
    give_rng = random.Random(f"bounty-give|{week}|{sorted(w.trends.items())}{salt}")
    _hang_asks(w, content, give_rng, cfg.give_kinds, week=week, day=0, expires=expires)
    _hang_prizes(w, content, week)  # 重賞（裝備四欄 6.4）：另一份亂數，上面掛出來的單一張都不動
    return []


def issue_day(state: GameState, content: Content, day: int, rng: random.Random | None = None) -> list[str]:
    """21 天季每天 00:00 掛一批（world.DAY_HOOKS；正式季整合設計 7.2）：官軍、黃巾各掛討伐一張，再一張打探或護送（單數天打探、
    雙數天護送）；雙數天劇本的每個陣營（豪強分屬兩軍時不掛豪強那一張）再各一張求兵（兵器關著不掛）。單數天原本掛的求藝
    企劃者 2026-10-21 拿掉（「懸賞榜直接把武學拿掉」），單數天就沒有要交東西的那一張。
    期限 bounty_days 天後的 00:00；名額、地點不重複、只挑已開放的地點照 issue。重賞每天每邊擲（_hang_prizes_day）。
    兩道擋同 issue：只掛今天（day 要等於此刻的季曆第幾天，停機補算跨過的天不補），掛過了不再掛（bounty_day）。其他季什麼都不做。"""
    w, cfg = state.world, content.config.bounties
    if not calendar.season21_on(w, content) or not active(state, content):
        return []
    at = calendar.point(w.time, content, w)
    if day != at.cal_day or day <= w.bounty_day:
        return []
    w.bounty_day = day
    salt = f"|{w.tianji}" if w.tianji else ""
    rng = random.Random(f"bounty-day|{day}|{w.bounty_seq}|{sorted(w.trends.items())}{salt}")
    _clear_stale(w, content)
    expires = calendar.day_start(day + content.config.season21_daily.bounty_days, content, w)
    second = "scout" if day % 2 else "escort"
    _hang_bills(w, content, rng, [k for k in ("strike", second) if k in cfg.kinds], week=at.week, day=day, expires=expires)
    give_rng = random.Random(f"bounty-give-day|{day}|{sorted(w.trends.items())}{salt}")
    _hang_asks(w, content, give_rng, ["arms"] if day % 2 == 0 and "arms" in cfg.give_kinds else [], week=at.week, day=day, expires=expires)
    _hang_prizes_day(w, content, day)
    return []


def _clear_stale(w: WorldState, content: Content) -> None:
    """陣營掛的舊單下榜（issue、issue_day 共用）：過期的拿掉，通緝照自己的期限，過期了還有人揭著的留著。"""
    w.bounties = [
        b for b in w.bounties
        if not past_due(b, content, w)
        or (b.kind == "wanted" and b.poster and not b.refunded and not b.done_by)  # 過期的通緝留到押金退回（系統掛的沒有押金，照一般的單下榜）
        or b.takers  # 過期了還有人揭著：留到他們同步時聽到那一句（deliver_lapses）
    ]


def _hang_bills(w: WorldState, content: Content, rng: random.Random, kinds: list[str], *, week: int, day: int, expires: float) -> None:
    """官軍、黃巾各掛 kinds 裡的每一張討伐、打探、護送（issue、issue_day 共用）。"""
    cfg = content.config.bounties
    # 同一地點不重複掛（FB-121 第 2 件：同一處兩張一樣的單，一次遊歷或探索交兩張差）：避開榜上還有效的同種單已經用掉的地點。
    # 討伐只看同一個陣營（兩邊打的對頭不同，on_win 不會一次交兩張）；打探不分陣營；護送不分陣營、不重複終點。濾完沒地方可挑就跳過那一張
    live = [b for b in w.bounties if not past_due(b, content, w) and _left(b) > 0]
    scouted = {b.location for b in live if b.kind == "scout"}
    ends = {b.end for b in live if b.kind == "escort"}
    for faction in ENEMY:
        if faction not in {f.id for f in content.scenario.factions}:
            continue
        used = {b.location for b in live if b.kind == "strike" and b.faction == faction}
        for kind in kinds:
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
                id=f"b{w.bounty_seq}", kind=kind, faction=faction, week=week, day=day, expires=expires,
                silver=cfg.silver.get(kind, 0), deeds=cfg.deeds.get(kind, 0), quota=quota(content), **spec,
            ))


def _hang_asks(w: WorldState, content: Content, give_rng: random.Random, give_kinds: list[str], *, week: int, day: int,
               expires: float) -> None:
    """劇本的每個陣營各掛 give_kinds 裡的每一種求兵（issue、issue_day 共用；求藝企劃者 2026-10-21 拿掉）。"""
    cfg = content.config.bounties
    # 豪強分屬兩軍的季（企劃者 2026-10-15）：豪強那一張不掛，豪強交依附那一軍的（一批 10 張）
    factions = [f.id for f in content.scenario.factions if not (f.allies and allied.on(content, w))]
    asks: dict[str, list[tuple[str, str]]] = {}
    for kind in give_kinds:
        if kind not in GIVE_KINDS or not content.config.weapons.enabled:  # 兵器關著不掛求兵
            continue
        attributes = _spread(give_rng, cfg.give_attributes, len(factions))
        asks[kind] = [(a, give_rng.choice(WEAPON_KINDS)) for a in attributes]
    for i, faction in enumerate(factions):
        for kind, picks in asks.items():
            attribute, weapon_kind = picks[i]
            w.bounty_seq += 1
            w.bounties.append(Bounty(
                id=f"b{w.bounty_seq}", kind=kind, faction=faction, week=week, day=day, expires=expires,
                silver=cfg.silver.get(kind, 0), deeds=cfg.deeds.get(kind, 0), quota=cfg.give_quota, attribute=attribute,
                weapon_kind=weapon_kind,
            ))


def targets(state: GameState, content: Content) -> list[str]:
    """假人往哪裡走：手上每一張要去的地點（討伐、打探：那裡；護送：終點）。"""
    out = []
    for b in mine(state, content) + open_commissions(state, content) + rallies(state, content):  # 委託、求援也去（擴充第二、三批）
        if b.kind == "escort":
            out.append(b.end)
        elif b.kind in ("strike", "scout"):
            out.append(b.location)
    return [loc for loc in out if loc in content.locations]


def _row(state: GameState, content: Content, b: Bounty) -> dict:
    row = {"id": b.id, "title": title(content, b), "how": how(content, b, state), "reward": reward_text(state, content, b),
           "issuer": issuer(content, b), "due": due_line(state, content, b)}
    tags = reward_tags(state, content, b)
    if tags is not None:  # 21 天季：賞拆成小籤、照等級的那一句（週末與 14 天的季沒有這兩個鍵）
        row.update(tags=tags, level=level_note(state, content, b))
    return row


def have_text(state: GameState, content: Content, world: WorldStateStore, b: Bounty, items: list[str]) -> str:
    """懸賞卡那一列的「你身上合用的：【厚背刀】（一階中品）、【厚背刀】（一階上品・在手上）等 3 把」（items 照 fitting 排好的，
    最不值錢的先寫兩件；待 joy 潤）。兵器寫階品（鐵匠鋪買的與別處來的同名，例「厚背刀」，靠階品分辨），手上那把再寫「在手上」
    （fitting 連手上那把也算，所以開頭寫「身上」不寫「庫裡」）。"""

    def named(item: str) -> str:
        w = _weapon(state, item)
        return f"【{w.name}】（{weapons.grade(w)}{'・在手上' if w is state.player.weapon else ''}）"

    more = f"等 {len(items)} {unit_of(b)}" if len(items) > 2 else ""
    return HAVE + "、".join(named(i) for i in items[:2]) + more


def status(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """狀態用（江湖頁的懸賞卡）：我手上揭了的每一張（標題、怎麼完成、賞、期限與名額），再加上身上有合用東西的求兵（多一個 have）。
    合用照 fitting 判、不看人在哪裡：人在城外也列，知道去城鎮交（不能用 give_problem，它要人在城鎮，設計 4.9）。
    每次 /api/main 都算：只在榜上有接得了、自己還沒交過的求兵時才找合用的。"""
    rows = [_row(state, content, b) for b in mine(state, content)]
    rows += [{**_row(state, content, b), "reward": commission_reward(state, content, b), "commission": True}
             for b in open_commissions(state, content)]  # 委託（大勢人物擴充第二批）：跟手上揭了的排在一起
    rows += [{**_row(state, content, b), "reward": rally_reward(content, b), "commission": True}
             for b in rallies(state, content)]  # 求援委託（第三批）
    me = name_key(state.player.name)
    for b in open_bounties(state, content):
        if b.kind not in GIVE_KINDS or not can_take(state, b) or me in (name_key(t) for t in b.done_by):
            continue
        items = fitting(state, content, world, b)
        if items:
            rows.append({**_row(state, content, b), "have": have_text(state, content, world, b, items)})
    return rows
