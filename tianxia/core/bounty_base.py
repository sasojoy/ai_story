"""懸賞榜「別人讀」的那一半（全部拆包第 45 批；照 smith_base、convoy_base、omen_base、seal_base）：懸賞榜包 features/bounties/rules.py 的純函式與字句原樣搬來，
包 re-export 同一批物件。誰讀：核心的事件檢定（join_note）、Game 原位（收店、榜的入口、投靠那一下作廢、第 2 週才開）、共用規則層的 figure_life（求援與人物懸賞）、
讀懸賞榜的包（人物情誼、陣營、探索、新手引導、輿圖、玩家互動、體力玩法、酒肆、移動；要寫交差的走事件與 ctx 的委派）。只靠核心與共用規則層就跑得起來，不 import 包。

- 字句：KIND_NAMES、OFFICIAL、ENEMY、BOARD、SEASON_END、BROWSE_VERBS、PICKED、UNPICKED、RALLY_AID、RALLY_POSTED、STRIKE_* 六句、LAPSED_SIDE、LAPSED_LEAN、STRANDED_JOIN、
  STRANDED_LOST、BEATEN_OFFICIAL（BEATEN_OFFICIAL 是截殺讀的）。
- 榜：active、is_town、board_here、close_board、open_bounties、visible、mine；期限 to_season_end、past_due、due_text；標題與怎麼完成 title、how、issuer、enemy_name。
- 接不接得了：_side_ok、_takeable、_side、can_take、stranded、join_note、drop_stranded；截殺讀的 hunting、official_hit；委託 open_commissions。
- 掛單的地點：_opened、_strike_spots。
- 人物掛的（寫季）：post_rally、post_figure（figure_life 的 _maybe_rally 一處、on_fall 每一位各叫一次；只寫 state.py 定義的 w.rallies、w.bounties、w.bounty_seq，不讀包）。
- commission_line：委託的賞那一句（書信那張卡與懸賞卡同一句；ask_text 是「他兌現」的字，呼叫端問人物情誼包要好傳進來）。
- 假人往哪裡走（第二輪第 89 批從包 rules.py 搬來）：targets、它讀的 rallies、army_of。移動包 bots._bounty_hop 讀 targets，共用層 bot_base._bounty_here 讀 mine，包不必為了這個碰懸賞榜包。

`how` 原本問 sortie.on，出陣包不能讀，換成它的本體 territory.on（同第 49、50 批）。同 event_check 不進 MODULES。
改這一份 scripts/test_for.py 照名字挑寫到它的測試檔（core/*_base 那一條）；懸賞榜包 README「另外要跑的」那一串另外跑。
本模組裡彼此叫的名字（mine、title、issuer……）測試換的是包 rules 那一份（tianxia/features/explore/tests/test_drill_gates_engine.py 換 _complete 讀的 title、issuer，那幾個函式留在 rules）；
探索包 explore_actions 經 bounty_base.mine 叫（test_explore_one 換這一份）。
"""
from __future__ import annotations

import math
import random

from .. import allied, calendar, territory, weapons
from ..characters import name_key
from ..models import Choice, Content, Location
from ..state import Bounty, GameState, PlayerState, WorldState

KIND_NAMES = {"strike": "討伐", "scout": "打探", "escort": "護送", "wanted": "通緝", "arms": "求兵"}
# 挑一件、回到懸賞榜只是在榜上翻頁：只有這一句回話時不寫江湖紀錄（包的 Outcome.quiet）；交出每一張各一則、各寫各的得失（FB-161：
# 以前挑、回、交併成一則，連交幾張時得失加總在一起，分不出哪一張給了多少）
BROWSE_VERBS = ("pick", "unpick")
PICKED = "你替「{what}」挑一件要交的東西。"  # 待 joy 潤：按了 bounty:pick 的回話（pick_line）
UNPICKED = "你回到懸賞榜前。"  # 待 joy 潤：按了 bounty:unpick 的回話（Game._bounty）
ENEMY = {"guan": "huang", "huang": "guan"}  # 自動掛單的兩個陣營與他們的對頭（同軍令）
BOARD = "懸賞榜"
SEASON_END = "到季末"  # 待 joy 潤：期限到季末或過了季末時寫這個（due_text）
LAPSED_SIDE = "【懸賞】你改投{faction}，手上「{title}」是別的陣營掛的，這一張作廢。"  # 待 joy 潤（FB-151：投靠、叛投那一下；換版前就換了陣營的存檔由 deliver_lapses 補同一句）
LAPSED_LEAN = "【懸賞】你改幫{faction}，手上「{title}」是{poster}掛的，這一張作廢。"  # 待 joy 潤（FB-811：三陣營四勝利開著、豪強改幫另一軍那一下；不能用 LAPSED_SIDE 的「改投」，上一行才說改幫不算叛投）
STRANDED_JOIN = "投靠之後，手上 {n} 張別的陣營掛的懸賞會作廢。"  # 待 joy 潤（FB-151：投靠的確認畫面）
STRANDED_LOST = "手上 {n} 張{faction}掛的懸賞作廢"  # 待 joy 潤（FB-151：叛投確認畫面「會失去」清單裡的一項，faction 是舊陣營）
OFFICIAL = "官府"  # 官府通緝（名聲 5.4）的掛單人
BEATEN_OFFICIAL = "惡名 -{n}（你被揭了官府海捕文書的{winner}打敗了）"  # 待 joy 潤（名聲 5.4：被截殺的寇那一份）
STRIKE_SORTIE = "出陣攻打贏"  # 待 joy 潤（FB-249）：出陣開著時討伐怎麼交差
STRIKE_GATHER = "找素材撞上的那一場也算"  # 待 joy 潤：多的那半句（散人不出陣，討伐靠這裡；只剩沒有一類一顆章的季寫得到）
# 一類一顆生效的季（FB-420）：找素材不打仗，討伐在練功交差（待 joy 潤）
STRIKE_PRECISE = "到{target}尋敵或出陣攻打贏一場{enemy}的隊伍"
STRIKE_PRACTICE = "到{target}尋敵打贏一場{enemy}的隊伍"
# 減法季探索一顆開著的季（Config.jianfa 的 explore_one）：沒有「尋敵」這顆鈕了，討伐在出門一趟的遭遇拍交差（FB-817；待 joy 潤）
STRIKE_OUTING = "到{target}出門探索或出陣攻打贏一場{enemy}的隊伍"
STRIKE_OUTING_RANGER = "到{target}出門探索打贏一場{enemy}的隊伍"
RALLY_AID = "；或去護衛、犒軍{who}"  # 待 joy 潤
RALLY_POSTED = "{who}向{side}各路同袍求援：{how}。"  # 待 joy 潤：陣營軍情


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
    from tianxia import week_unlock  # noqa: PLC0415  繞回來的 import，呼叫時才取

    return active(state, content) and is_town(content, state.player.location) and week_unlock.open(state, content, "bounties")


def close_board(p: PlayerState) -> None:
    """收起懸賞榜：選單、第三層挑到哪一張、店面上榜吏那一句（店面獨立介面設計 1.4）一起清。凡是把 picking_bounty 設成 False 的地方
    都走這裡（離開、讀檔修補、出發），同 equipment.close_smith。"""
    p.picking_bounty, p.bounty_pick = False, None
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""


def sit_at_board(p: PlayerState) -> None:
    """坐到榜前（core_seams，全部拆包第 56 批）：酒肆牆上的懸賞榜那一下只打開榜，不像 bounties.actions.enter 另外清挑到哪一張、掌櫃那一句。"""
    p.picking_bounty = True


def done_count(p: PlayerState) -> int:
    """這一季完成了幾張懸賞（core_seams，全部拆包第 56 批）：新手目標、傳、傳承的量表讀它，不直接碰懸賞榜包認領的欄位。"""
    return p.bounties_done


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


def how(content: Content, b: Bounty, state: GameState | None = None, world: WorldState | None = None) -> str:
    """怎麼完成（一句）。討伐在出陣開著時寫出陣攻（與找素材撞上），不寫遊歷（FB-249）；一類一顆在這一季生效時
    （precise.on，要給 state 或 world）寫練功（FB-420：找素材不打仗了），看的人是散人（不出陣）只寫練功。懸賞卡、告示、紙上、揭下的回話、
    傳聞與書信都走這一句；只給 world 的（陣營傳聞，沒有看的人）照陣營的人寫（FB-435）。"""
    world = state.world if state is not None else world
    if b.motive == "求援":  # 求援委託：護衛、犒軍那位人物也算（大勢人物擴充第三批，跟「大勢人物參戰與護衛」對齊）
        return how(content, b.model_copy(update={"motive": None}), state, world) + RALLY_AID.format(who=issuer(content, b))
    if b.kind == "strike":
        from tianxia import precise  # noqa: PLC0415  延後 import 只是保險
        from tianxia.rules import jianfa  # noqa: PLC0415

        target = _loc_name(content, b.location)
        if precise.on(content, world):
            ranger = state is not None and state.player.faction is None  # 散人不出陣
            if jianfa(content, world, "explore_one"):  # 減法季探索一顆：出門一趟的遭遇拍（FB-817）
                line = STRIKE_OUTING if territory.on(content) and not ranger else STRIKE_OUTING_RANGER
            else:
                line = STRIKE_PRECISE if territory.on(content) and not ranger else STRIKE_PRACTICE
            return line.format(target=target, enemy=_enemy_name(content, b))
        if territory.on(content):
            ways = f"{STRIKE_SORTIE}，{STRIKE_GATHER}"
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


def open_bounties(state: GameState, content: Content) -> list[Bounty]:
    """榜上還有效的（沒過期〔past_due〕、還有名額）；休季（active 為假）一張都沒有。截殺關著（Config.raid.enabled）時通緝不算：只能靠截殺交差，揭了也交不了
    （mine、take、hunting、status、整季機器人與假人都經過這裡，自然看不到、揭不了、不佔格）；押金照期限退（deliver_refunds 直接掃榜）。"""
    if not active(state, content):
        return []
    w, raids = state.world, content.config.raid.enabled
    return [b for b in w.bounties if not past_due(b, content, w) and _left(b) > 0 and (raids or b.kind != "wanted")]


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


def join_note(state: GameState, content: Content, choice: Choice) -> str:
    """事件選項會拜入陣營名下的門派（Effect.join_sect）、因而投靠那個陣營時，手上有新陣營接不了的懸賞：選項那一行後面多一個括號，
    寫跟投靠的確認畫面同一句（STRANDED_JOIN，張數照 stranded 數；FB-159，原本只有選下去之後才補作廢的句子）。
    已經有陣營的人拜入不換陣營（rules.apply_effect），門派不歸任何陣營的也不會，這兩種都沒有；成功與失敗的效果都看（先成功）。
    沒有要警告的是空字串。"""
    if state.player.faction is not None:
        return ""
    for effect in (choice.effect, choice.fail_effect):
        owner = content.sect_faction(effect.join_sect)
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


def post_rally(state: GameState, content: Content, cid: str) -> Bounty | None:
    """cid（大勢人物）對自己陣營全部人發一件求援委託（figure_life.tick：心事焦慮時擲中）：在他所在那一區，有對頭站著的地方就討伐，
    否則打探那一區危險度 2 以上、不是城鎮的地方。同一位一次一件。懸賞榜關著、他不是交戰兩軍、那一區什麼都挑不出來回 None。"""
    from tianxia import atlas, figure_life  # noqa: PLC0415  atlas → world → rules：延後載入

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


def open_commissions(state: GameState, content: Content) -> list[Bounty]:
    """身上還沒辦完、沒過期、沒婉拒的委託（求援書信附的，letters.py）。休季沒有。"""
    w = state.world
    if w.ended:
        return []
    return [x.task for x in state.player.letters
            if x.task is not None and not x.lapsed and not x.task.done_by and x.task.expires > w.time]


def official_hit(state: GameState, content: Content, target: str) -> bool:
    """我手上揭著官府通緝這個人（名聲 5.4）：截殺打贏時被打的寇惡名少一點（Game.raid 交差之前先問）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and b.auto_by == "官府" and name_key(b.target or "") == key for b in mine(state, content))


def hunting(state: GameState, content: Content, target: str) -> bool:
    """我接了通緝這個人、還沒完成（截殺的鈕看它：散人、同陣營的人也能對他下手）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and name_key(b.target or "") == key for b in mine(state, content))


def is_browse_line(line: str) -> bool:
    """這一行是不是挑一件、回到懸賞榜的回話（pick_line、UNPICKED）：包的 Outcome.quiet 照它判斷這一下只是翻頁、不寫紀錄（FB-161）。"""
    head, _, tail = PICKED.partition("{what}")
    return line == UNPICKED or (len(line) > len(head) + len(tail) and line.startswith(head) and line.endswith(tail))


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


def post_figure(state: GameState, content: Content, cid: str, motive: str, region: str | None, spot: str | None) -> Bounty | None:
    """人物掛一張懸賞（大勢人物擴充第二批，figure_life.on_fall）：討伐，掛單的是 cid 那一方，打的是對頭；地點在 region 那一區，
    倒下的地方（spot）有對頭的隊伍就掛那裡，否則照那一區的地點挑（自己一份亂數：天機｜人物｜此刻）。賞銀是一般討伐的
    revenge_silver_scale 倍，掛 revenge_cal_days 個季曆天。懸賞榜關著、cid 不是交戰兩軍、那一區沒有對頭站著的地方、
    同一位人物還有一張有效的同一種，都不掛（回 None）。"""
    from tianxia import atlas  # noqa: PLC0415  atlas → world → rules：延後載入
    from tianxia.relations import side_of  # noqa: PLC0415

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


def commission_line(content: Content, b: Bounty, ask_text: str) -> str:
    """委託的賞（書信那張卡、懸賞卡）：「賞銀 30・張梁情誼 +5」；ask_text 是 NPC 智能 2.0的條件（辦成了他兌現你求的那一件）寫給人看的字，沒有條件傳空字串。待 joy 潤。
    人物情誼的 letters.view 沒有 ctx（殼與測試都只給 state、content），懸賞榜包的 commission_reward 有：兩邊各自問到 ask_text 再叫這裡，同一句字。"""
    parts = [f"賞銀 {b.silver}"] if b.silver else []
    amount = content.config.figure_life.commission_affinity
    if amount and b.figure in content.characters:
        parts.append(f"{content.characters[b.figure].name}情誼 +{amount}")
    if b.parley_ask:
        parts.append(f"他兌現：{ask_text}")
    return "・".join(parts)


def army_of(state: GameState, content: Content) -> str | None:
    """站哪一軍（名聲 4.6）：照 rules.side_of（就是 allied.side_of；豪強分屬兩軍的季，依附官軍或黃巾的豪強是那一軍），
    只認官軍、黃巾；散人、沒有依附的第三方豪強（14 天的季）是 None。"""
    side = allied.side_of(state, content)
    return side if side in ENEMY else None


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


def targets(state: GameState, content: Content) -> list[str]:
    """假人往哪裡走：手上每一張要去的地點（討伐、打探：那裡；護送：終點）。"""
    out = []
    for b in mine(state, content) + open_commissions(state, content) + rallies(state, content):  # 委託、求援也去（擴充第二、三批）
        if b.kind == "escort":
            out.append(b.end)
        elif b.kind in ("strike", "scout"):
            out.append(b.location)
    return [loc for loc in out if loc in content.locations]
