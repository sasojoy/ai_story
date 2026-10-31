"""探索一顆的動作（功能包 tianxia/features/explore/；原本是 Game 上探索一顆的 15 個方法，開發規範手冊 3.2、主動搬六包第 3＋4 批）。

**名字陷阱**：名字帶 outing 的（`outing_on`、`outing_foe`、`outing_weights`、`outing_plan_at`、`outing_plan`、`outing_option`、
`outing_fight`、`outing_event`、`outing_ledger`）是探索一顆（出門一趟只碰上一件事）的，不是走一趟；這一批兩樣都進這一包，不改名。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx、explore_one 模組換成
explore_rules）；函式名＝原本的方法名去掉前導底線，一個例外：`_outing_plan(loc)` 是 `outing_plan_at`（跟 `outing_plan()` 分開）。
Game 上留 9 個一行委派（核心原位：選單那一格、`_act` 的 act:explore、行動列底下那一行、紀錄的標題、輿圖；server 的 mostly 與輿圖；
bot_policy；腳本；測試）。包裡互相叫直接叫這裡的函式；只有 `_outing_plan`、`outing_plan`、`_outing_on`、`odds` 經 ctx 叫
（這一包的 tests/test_explore_one.py 換掉 game._outing_plan、test_explore_one_2e 換掉 game.odds：換掉的才打得到）。
擲骰都用自己的亂數（explore_rules.rng_for），Game.rng 一次都不多、不少（頭目戰與仗本身照它們原本的）。
"""
from __future__ import annotations

import contextlib
import functools
import random
from dataclasses import dataclass

from tianxia import battlelog  # 過渡：待搬（戰報：出門一趟・遭遇的標籤、拆得失）
from tianxia import bounties  # 過渡：待搬（懸賞榜：討伐那一路、打探交差、打贏交差）
from tianxia import duel as duel_rules  # 過渡：待搬（頭目戰：此刻遇得上的頭目）
from tianxia import events as event_rules  # 過渡：待搬（事件：抽不抽得到、藏起來的、照輪替抽）
from tianxia import explore_modes  # 過渡：待搬（探索三選一，企劃者 10/31 定不搬：找素材那一套 gather_finds、補料 one_of）
from tianxia import growth  # 過渡：待搬（三道閘：今天第幾場、疲勞、對手的檔）
from tianxia import insights  # 過渡：待搬（悟不悟得出）
from tianxia import journal, team
from tianxia import mapdata  # 過渡：待搬（輿圖：勝算的字、關著時的「多半」）
from tianxia import mapview  # 過渡：待搬（輿圖：哪些地點畫得出來）
from tianxia import materials  # 過渡：待搬（素材的發放）
from tianxia import prologue as prologue_rules  # 過渡：待搬（序章裡探索照舊是寫好的那幾步）
from tianxia import renown  # 過渡：待搬（名聲：頭目的倍數）
from tianxia import sensing  # 過渡：待搬（有所感：這一處今天悟錯過沒）
from tianxia import storyline  # 過渡：待搬（一條線：開頭擲不擲中）
from tianxia import territory  # 過渡：待搬（地盤：這一處此刻歸誰）
from tianxia.core.option import Option
from tianxia.events import event_candidates, pick_event  # 過渡：待搬（事件：候選、抽一則）
from tianxia.models import DuelBoss, Location, Squad
from tianxia.rules import jianfa

from . import explore_rules, outing_rules


@dataclass(frozen=True)
class OutingPlan:
    """減法季探索一顆（整合設計 4.1）：這一處此刻出門一趟會怎麼抽（Game._outing_plan；鈕上的小字、行動列底下那一行、真的出門、假人打分數
    都讀這一份，說的跟擲的不會走樣）。只讀，不擲骰。"""

    kind: str  # 這一處算哪一種地點（explore_rules.kind_of：town、temple、ford、wild、hill、camp）
    weights: dict[str, int]  # 這一趟四類事的比重（explore_rules.weights；這裡此刻抽不到事件、悟不出的那一類已經是 0；接了討伐懸賞只有遭遇）
    how: str | None  # 遭遇打誰：bounty 討伐懸賞那一路（對它必敗時不算，2e）、spar 自家營寨跟同袍比劃、foe 這裡最弱的對手、town 城裡的地痞；都沒有是 None
    foe: Squad | None  # 那一路
    boss: DuelBoss | None  # 遭遇有機會撞上的頭目（接了這裡的討伐懸賞不擲）
    hint: str  # 鈕上括號裡最後那一段小字，也是四格探索那一格的小字（/api/main 的 mostly；explore_rules.hint_of：地點種類的字加上面 weights 最重的一類；有賞、同袍比劃）；最後兩個字是輿圖名字旁（map_mostly）

    @property
    def foe_note(self) -> str | None:
        """行動列底下那一行補的那一句（howto.OUTING_FOE 的鍵）；一般的對手不補。"""
        return self.how if self.how in ("town", "spar", "bounty") else None


def outing_on(ctx) -> bool:
    """探索一顆在這一季開著（Config.jianfa 的 explore_one＋開季的章，rules.jianfa），而且不在序章裡（序章照舊按「探索」走寫好的那幾步）。
    開著時選單上只剩一顆「探索」（act:explore，出門一趟），不畫三選一（explore:*）、尋敵、城裡操練。"""
    return jianfa(ctx.content, ctx.state.world, "explore_one") and not prologue_rules.active(ctx.state, ctx.content)


def outing_foe(ctx, loc: Location, kind: str) -> tuple[str | None, Squad | None]:
    """遭遇拍打誰（設計 4.1，PM 2026-10-25 第 3 件）：手上有這裡的討伐懸賞、那一路不是自己人，就是它（bounty；易手了也找得到，同
    _gather_foe）；**可是對那一路的勝算是必敗時不算**（2e，FB-880，企劃者 2026-10-26「勝算是必敗時不強制打懸賞，照原本的表抽」）：
    問的是鈕上寫勝算的同一個函式（odds，固定種子、不碰 Game.rng），必敗就當這一處沒有這張懸賞，往下照沒有懸賞時挑；變強到不再必敗
    就又是它。自家營寨（營類、此刻歸自己這一邊、有自家的隊伍）是跟同袍比劃（spar，_sortie_host 那一路）；否則這裡此刻站的、
    不是自家的隊伍裡最弱的一路（foe）；城類的地點自己沒有對手才換成地痞（town，Config.jianfa.town_foes 的第一路）。都沒有是 (None, None)。"""
    s, c = ctx.state, ctx.content
    for b in bounties.mine(s, c):
        if b.kind == "strike" and b.location == loc.id and b.squad in c.squads and not ctx._drills_with(c.squads[b.squad]):
            if ctx.odds(b.squad) == mapdata.LOSE_WORD:
                continue  # 打不贏的懸賞不強制：這一處當作沒有它（沒有放棄，手上還揭著）
            return "bounty", c.squads[b.squad]
    side = ctx._side()
    if kind == explore_rules.CAMP and side is not None and territory.controller(s.world, c, loc.id) == side:
        host = ctx._sortie_host(loc)
        if host is not None:
            return "spar", host
    foes = ctx._wild_foes(loc)
    if foes:
        return "foe", min(foes, key=lambda foe: foe.difficulty)  # 同分取這裡列的第一路
    if kind == explore_rules.TOWN:
        sid = next((sid for sid in c.config.jianfa.town_foes if sid in c.squads), None)
        if sid is not None:
            return "town", c.squads[sid]
    return None, None


def outing_weights(ctx, loc: Location, *, has_foes: bool, bounty_here: bool, hidden: set[str] | None = None) -> dict[str, int]:
    """這一處這一趟四類事的比重（explore_rules.weights：表照標籤或 explore_mix、危險度、懸賞、有沒有對手），再把此刻做不到的歸 0：
    抽不到事件（一次性、可重複的都沒有）事件是 0，悟不出（insights.explore_gives 是空的，或這個遊戲日在這裡選錯過做法）感悟是 0——
    那一份照比重分給其餘的。只讀，不擲骰。hidden：藏起來的事件（events.hidden_events），替好幾處一起問時（map_mostly）先算好給。"""
    s, c = ctx.state, ctx.content
    weights = explore_rules.weights(c.config.jianfa, loc, has_foes=has_foes, bounty_here=bounty_here)
    # 一次性與奇遇（rare）加可重複的（common）就是全部（pool=None），一趟只問一次，找到一則就夠
    if not event_rules.has_event_candidates(s, c, "explore", hidden=hidden):
        weights[explore_rules.EVENT] = 0
    if not insights.explore_gives(loc, c) or sensing.missed_today(s, c, loc):
        weights[explore_rules.INSIGHT] = 0
    return weights


def outing_plan_at(ctx, loc: Location, *, hidden: set[str] | None = None) -> OutingPlan:
    """這一處此刻出門一趟怎麼抽（OutingPlan）：比重照 _outing_weights。這裡沒有一般對手（也沒有討伐懸賞）遭遇就是 0，那一份分給其餘三類；
    頭目不算對手（FB-815：只有頭目的地點不是一定撞上他）——他是這一趟另外擲的（_explore_one：5% × 名聲倍數），擲中那一趟才是
    遭遇。接了討伐懸賞：這一趟就是遭遇（weights 只有遭遇，explore_rules.encounter_only）；對懸賞那一路是必敗時不算（_outing_foe，2e），
    整份（對手、頭目、比重、小字）跟沒有這張懸賞時一樣。只讀，不擲骰（判勝算也不碰 Game.rng）。"""
    s, c = ctx.state, ctx.content
    cfg = c.config.jianfa
    kind = explore_rules.kind_of(cfg, loc).kind
    how, foe = outing_foe(ctx, loc, kind)
    boss = None if how == "bounty" else duel_rules.available(s, c)  # 接了懸賞：遭遇就是懸賞那一路，不擲頭目
    weights = outing_weights(ctx, loc, has_foes=foe is not None, bounty_here=how == "bounty", hidden=hidden)
    return OutingPlan(kind=kind, weights=weights, how=how, foe=foe, boss=boss, hint=explore_rules.hint_of(kind, how, weights))


def mostly_here(ctx) -> str:
    """四格探索那一格的小字（/api/main 的 mostly；雲端批 5 的欄位，網頁 m.mostly）：探索一顆開著時是出門一趟的那一份
    （_outing_plan 的 hint：地點種類的字，招牌類此刻的比重是 0 才改寫比重最高的那一類；接了討伐懸賞「…有賞」、自家營寨「同袍比劃」，跟鈕上括號那一段同一個字）；
    關著照雲端的 mapdata.mostly_here（照地點的小圖）。在路上是空字串。"""
    plan = ctx.outing_plan()
    if plan is not None:
        return plan.hint
    return mapdata.mostly_here(ctx.state, ctx.content)


def outing_plan(ctx) -> OutingPlan | None:
    """探索一顆開著時，這裡此刻出門一趟怎麼抽（假人打分數、量表讀；同 _outing_plan）；關著、序章裡、在路上是 None。"""
    p = ctx.state.player
    if not ctx._outing_on() or p.journey is not None:
        return None
    return ctx._outing_plan(ctx.content.locations[p.location])


def map_mostly(ctx) -> dict[str, str] | None:
    """輿圖第一層名字旁的兩個字（2f，FB-886；PM 2026-10-26「照這一處自己的比重寫，跟鈕上同一套」）：每一個畫得出來的地點，這個人**站過去之後**
    鈕上小字的最後兩個字（explore_rules.tail_of：多事、多敵、多料、多悟、參半，接了這裡的討伐懸賞「有賞」、自家營寨「比劃」）。
    替每一處「假裝站過去」叫 _outing_plan（鈕、四格、行動列那一行讀的同一個函式，不另寫一份判斷）：危險度、有沒有對手（看的人是哪一邊、
    這一處此刻歸誰）、懸賞、自家營寨、抽不到事件、悟不出感悟都算進去，也就不看他現在站在哪。探索一顆沒開著、序章裡（探索鈕是寫好的幾步，
    沒有比重可看）是 None，名字旁照舊（mapdata.place_mostly）。只讀，不擲骰、不動存檔（站回原處），在路上也算得出。"""
    if not ctx._outing_on():
        return None
    out: dict[str, str] = {}
    hidden = event_rules.hidden_events(ctx.state, ctx.content)  # 藏起來的事件不看站在哪，四十幾處共用一份，不必每處重算
    for loc_id in mapview.open_places(ctx.state, ctx.content):
        with standing_at(ctx, loc_id):
            plan = ctx._outing_plan(ctx.content.locations[loc_id], hidden=hidden)
        out[loc_id] = explore_rules.tail_of(plan.how, plan.weights)
    return out


@contextlib.contextmanager
def standing_at(ctx, loc_id: str):
    """裡面的讀取都當作這個人已經站在 loc_id（沒有在路上）：state 換成一份淺拷貝（只有 player 的位置與路上換掉，其餘還是同一批物件，不動它們），
    出了範圍（含丟例外）換回原來那一份。給「站過去之後會怎樣」的只讀查詢用（map_mostly）：事件抽得到嗎、對手是誰、勝算的地利都看
    state.player.location，一處一處改函式簽名既費事又會漏，換一份 state 才跟真的站過去一樣。範圍裡不准寫。"""
    home = ctx.state
    ctx.state = home.model_copy(update={"player": home.player.model_copy(update={"location": loc_id, "journey": None})})
    try:
        yield
    finally:
        ctx.state = home


def outing_option(ctx, loc: Location) -> Option:
    """探索一顆的鈕：「探索（體力 15・城裡多事）」，括號裡最後那一段是這一處多半給什麼（同 /api/main 的 mostly，mostly_here）。"""
    return ctx._cost_option("act:explore", "探索", ctx.content.config.jianfa.explore_stamina, note=ctx._outing_plan(loc).hint)


def explore_one(ctx) -> list[str]:
    """出門一趟（減法季探索一顆，整合設計 4.1）：扣 explore_stamina（15），照這一處的比重（_outing_plan）抽**一件事**
    （explore_rules.draw；2d，企劃者 2026-10-26「只抽一件事情」，同天體力改 15）：遭遇、事件、素材、感悟其中一件，感悟不連兩趟，
    接了討伐懸賞這一趟就是遭遇（打懸賞那一路，交了差回原表）。素材與遭遇當場結算；事件或感悟端出來等玩家選；遭遇上撞到頭目時，
    那一趟收在頭目戰。回來寫成一段（content/outing_lines.json：出門那一句加這一件事的一句），後面一行「得：…　失：…」；
    這一趟沒收穫補一個一階素材；收尾照舊擲回體丹、殘譜、破境丹、打探懸賞、玉璽碎片。
    擲骰都用自己的亂數（explore_rules.rng_for），不碰 Game.rng（頭目戰與仗本身照它們原本的）。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.jianfa
    loc = c.locations[p.location]
    plan = ctx._outing_plan(loc)
    p.stamina -= cfg.explore_stamina
    p.explore_seq += 1
    roll = functools.partial(explore_rules.rng_for, ctx.world.get_season_number(), p.name, p.explore_seq)
    last_loc, _, last_kind = p.outing_last.partition(":")
    weights = plan.weights
    if plan.boss is not None and plan.foe is None and plan.how != "bounty":
        # 這裡只有頭目、沒有一般對手（官軍在長社，FB-815）：這一趟照 5% × 名聲倍數擲一次他；擲中了這一趟就是遭遇（頭目擋路），
        # 沒擲中就當這裡沒有對手——遭遇那一格已經分給其餘三類（plan.weights 的遭遇是 0）
        if roll("頭目").random() < c.config.duel.explore_chance * renown.duel_chance(s, c):
            weights = explore_rules.encounter_only()
    beat = explore_rules.draw(roll("拍"), weights, last_choice=last_kind if last_loc == loc.id else None)
    # 一條線（特殊事件）：在開頭的地方擲中了，這一趟就是那條線的第一段（關著、沒有線不擲；用自己的亂數，不動拍子）
    boost = outing_rules.rare_boost(s, c)  # 走一趟：段數越多，稀有的越容易來（不在路上是 1）
    strand = storyline.roll_start(s, c, roll("奇事"), boost=boost)
    if strand is not None:
        beat = explore_rules.EVENT
    say, lines = roll("段落"), c.outing_lines
    story = [explore_rules.line(lines, "open", plan.kind, say, place=loc.name)]
    if ctx._draft is not None and not ctx._draft.tag:
        ctx._draft.tag = explore_rules.BEAT_WORDS[beat]
    before = len(ctx._draft.changes) if ctx._draft is not None else 0
    out: list[str] = []
    got_any, boss, choice = False, None, ""
    ctx._outing_close = set()
    ctx._beat = {"kind": beat, "rare": strand is not None, "won": None}  # 走一趟讀這一段是什麼（_outing_walk）
    rng = roll("結算")
    if beat == explore_rules.MATERIAL:  # 素材：找素材一定給的那一套（不展開分支；屬性照這裡的素材）
        mids = explore_modes.gather_finds(c, loc, rng, sure=True, boost=boost)
        ctx._beat["rare"] = any(c.materials[m].tier >= 2 for m in mids if m in c.materials)
        top = next((c.materials[m].name for m in mids if m in c.materials and c.materials[m].tier >= outing_rules.FEAT_TIER), "")
        if top:  # 稀世的素材：這一趟收的時候記一則行狀（outing.FEAT_ANNAL）
            ctx._beat["feat"], ctx._beat["feat_kind"] = top, outing_rules.FEAT_TREASURE
        found = [granted for mid in mids if (granted := materials.grant(s, c, mid))]
        found += ctx._home_gather(loc, mids)  # 領地爭奪：站在自家領地多給的那一個
        items = explore_rules.items_of(found, materials.GRANT_PREFIX)
        if items:
            story.append(explore_rules.line(lines, "material", "found", say, place=loc.name, item=items))
            got_any = True
        out += found
    elif beat == explore_rules.ENCOUNTER:
        if plan.boss is not None and (plan.foe is None or rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c)):
            boss = plan.boss  # 頭目擋路（5% × 名聲倍數；這裡只有頭目時直接對上）：頭目戰收在這一趟最後
            story.append(explore_rules.line(lines, "encounter", "boss", say, place=loc.name, foe=ctx._boss_face(boss)))
            got_any = True
        elif plan.foe is not None:
            msgs, key, won = outing_fight(ctx, loc, plan)
            ctx._beat["won"], ctx._beat["lost"] = won, key in ("lose", "town_lose")
            ctx._beat["foe"] = outing_rules.foe_look(plan.foe)  # 畫面照它挑對手的圖（黃巾、官兵、家丁、盜匪、猛獸）
            if won and ctx._outing_upset:  # 開打前勝算凶險以下還打贏：以弱勝強，這一趟收的時候記一則行狀
                ctx._beat["feat"], ctx._beat["feat_kind"] = plan.foe.name, outing_rules.FEAT_UPSET
            story.append(explore_rules.line(lines, "encounter", key, say, place=loc.name, foe=plan.foe.name))
            out += msgs
            got_any = won
    elif beat == explore_rules.EVENT:  # 要選的：事件（野類偏旅人那一類）；擲中了一條線就是那條線的第一段
        msgs = ctx._story_begin(strand) if strand is not None else outing_event(ctx, loc, plan.kind, rng, boost)
        if msgs:
            story.append(explore_rules.line(lines, "event", "lead", say, place=loc.name))
            out += msgs
            got_any, choice = True, beat
    elif beat == explore_rules.INSIGHT:  # 要選的：感悟（有所感）
        story.append(explore_rules.line(lines, "insight", "lead", say, place=loc.name))
        out += ctx._sense_here(loc, rng)
        got_any, choice = True, beat
    if boss is not None:
        out += ctx._duel_start(boss)
    if not got_any:  # 這一趟沒收穫（素材找不到料、遭遇打輸或沒對手）：補一個一階素材（設計 4.1【PM】）
        kinds = {c.materials[m].attribute for m in loc.materials if m in c.materials}
        mid = explore_modes.one_of(c, kinds, 1, roll("補"))
        granted = materials.grant(s, c, mid) if mid is not None else None
        if granted:
            story.append(explore_rules.line(lines, "close", "empty", say, place=loc.name,
                                          item=explore_rules.items_of([granted], materials.GRANT_PREFIX)))
            out.append(granted)
    # 收尾的幾樣先算（打探懸賞交差在 45 級換成心得時，那一句「境界已到」也在這裡面，段落結尾要看得到它，FB-818）
    extras = ctx._pill_find(roll("回體丹")) + ctx._scrap_find() + ctx._legend_find(roll("破境丹"))
    extras += bounties.on_explore(s, c, ctx.world, loc.id) + ctx._seal_find(loc.id)  # 打探懸賞：出門一趟就算
    if any(line.startswith(team.CAPPED_XINDE.partition("，")[0]) for line in out + extras):
        ctx._outing_close.add("capped")
    for key in explore_rules.LINE_KEYS["close"]:  # 段落結尾：疲勞打了折、對手配不上你、境界已到（三道閘，設計 4.2）
        if key in ctx._outing_close:
            story.append(explore_rules.line(lines, "close", key, say, place=loc.name))
    p.outing_last = f"{loc.id}:{choice}" if choice else ""
    ledger = outing_ledger(ctx, out + extras, before)
    return ["".join(story)] + ([ledger] if ledger else []) + out + extras


def outing_fight(ctx, loc: Location, plan: OutingPlan) -> tuple[list[str], str, bool]:
    """遭遇拍打的那一場：回（訊息, outing_lines 的 encounter 鍵, 打贏了沒）。自家營寨跟同袍比劃：不打、不掉東西，照 _sortie_host 那一路
    的心得經驗 camp_spar_share（三成，_drill_gains；算仗）。其餘照探索的野怪打（_squad_encounter(wild=True)：扣氣血減半、不問模型、不推大勢），戰報標
    「出門一趟・遭遇」；城裡的地痞戰利（銀兩、心得、掉的素材）乘 town_loot_scale、不算討伐；其餘打贏算討伐懸賞的交差。"""
    s, c = ctx.state, ctx.content
    cfg, foe = c.config.jianfa, plan.foe
    ctx._outing_upset = False
    gate = fight_gate(ctx, foe)  # 三道閘的前兩道（疲勞、對手配不配得上你）：這一場的經驗、心得、銀兩、掉的素材一起乘
    if plan.how == "spar":  # 對手那一路心得、經驗的 camp_spar_share（三成）乘三道閘的倍數（PM 2026-10-26：以前全額）
        return ctx._drill_gains(foe, cfg.camp_spar_share * gate, "camp_spar", echo=False), "spar", True  # 心得只由草稿記（FB-830）
    town = plan.how == "town"
    ctx._loot_scale = cfg.town_loot_scale if town else 1.0
    ctx._gate_scale = gate
    ctx._drop_scale = gate * ctx._loot_scale
    card = s.battle_card
    try:
        msgs = ctx._squad_encounter(foe.id, wild=True)
    finally:
        ctx._loot_scale = ctx._drop_scale = ctx._gate_scale = 1.0
    record = next((r for r in s.battles if r.id == s.battle_card), None) if s.battle_card != card else None
    won = record is not None and record.tier in team.WIN_TIERS
    # 以弱勝強：打贏了才回頭看開打那一刻的威力對這一路的勝算（team.odds_word，固定種子、不碰 Game.rng；沒打贏、沒懸賞的趟都不算勝算，2e）
    ctx._outing_upset = won and team.odds_word(record.our_power, foe) in outing_rules.FEAT_ODDS
    if not won:
        ctx._outing_close.discard("outlevel")  # FB-881：「對手配不上你，所得有限」只在打贏、真的因為對手檔打了折才寫；輸了、平手不寫
    if record is not None:
        record.label = battlelog.OUTING_LABEL
    if won and not town:
        done = bounties.on_win(s, c, ctx.world, loc.id, foe.id)
        changes, notes = battlelog.split_changes(done, for_record=True)
        record.changes += changes
        record.notes += notes
        msgs += done
    if won and not town and (ctx._practice_tier(loc) or 0) >= 1:
        s.player.newbie_marks.add("field2")  # 新手目標：在二級以上的地方打贏一場（這一季沒有尋敵，遭遇拍打贏也算，FB-816）
    tier = record.tier if record is not None else "落敗"
    if town:
        return msgs, "town_win" if won else "town_draw" if tier == "僵持" else "town_lose", won  # 平手有自己的句子（FB-819）
    return msgs, "win" if won else "draw" if tier == "僵持" else "lose", won


def fight_gate(ctx, foe: Squad) -> float:
    """遭遇拍這一場的倍數（減法季三道閘的前兩道，整合設計 4.2；Config.jianfa 的 drill_gates）：今天第幾場（PlayerState.fights_today，
    台灣 00:00 換日、照 _pill_day）的疲勞（growth.fatigue_factor：前 drill_full_per_day 場 1，之後每場 ×drill_decay，最低 drill_floor）
    乘對手的檔（growth.outlevel_factor：對手難度的檔比自己等級的檔低一檔 0.5、兩檔 0.1）。關著是 1、也不記場數（存檔一個鍵都不多）。
    打了折的那一道記進 _outing_close（段落結尾那一句：tired、outlevel）；outlevel 在 _outing_fight 看到這一場沒打贏時收回（FB-881：
    輸了、平手沒拿到東西，不是因為對手檔）。"""
    s, c = ctx.state, ctx.content
    if not jianfa(c, s.world, "drill_gates"):
        return 1.0
    cfg, p = c.config.jianfa, s.player
    today = ctx._pill_day()
    n = growth.nth_fight(fight_day=p.fight_day, fights_today=p.fights_today, today=today)
    p.fight_day, p.fights_today = today, n
    tired = growth.fatigue_factor(cfg, n)
    matched = growth.outlevel_factor(cfg, p.member.level, foe.difficulty)
    if tired < 1:
        ctx._outing_close.add("tired")
    if matched < 1:
        ctx._outing_close.add("outlevel")
    return tired * matched


def fatigue_next(ctx) -> float:
    """下一場遭遇的疲勞倍數（同 _fight_gate 的第一道，只讀、不記場數）：假人打探索的分數、量表讀；三道閘關著是 1。"""
    s, c = ctx.state, ctx.content
    if not jianfa(c, s.world, "drill_gates"):
        return 1.0
    p = s.player
    n = growth.nth_fight(fight_day=p.fight_day, fights_today=p.fights_today, today=ctx._pill_day())
    return growth.fatigue_factor(c.config.jianfa, n)


def outing_event(ctx, loc: Location, kind: str, rng: random.Random, boost: float = 1.0) -> list[str]:
    """事件拍（設計 4.1）：一次性奇遇先擲 rare_explore_chance（可重複的一則都沒有時直接是它）；沒中照防重複輪替抽這裡可重複的事件，
    野類的地點有標了「旅人」的就在那幾則裡抽（救助旅人那一類）。抽到就端出來（pending_event），一則都沒有是空的。"""
    s, c = ctx.state, ctx.content
    common = event_candidates(s, c, "explore", "common")
    if event_candidates(s, c, "explore", "rare") and (rng.random() < c.config.rare_explore_chance * boost or not common):
        if ctx._beat is not None:
            ctx._beat["rare"] = True
        return ctx._present(pick_event(s, c, "explore", rng, "rare"), "explore")
    travelers = [e for e in common if explore_rules.TRAVELER in e.tags] if kind == explore_rules.WILD else []
    event = event_rules.pick_from(s, c, travelers, "explore", rng) if travelers else None
    event = event or pick_event(s, c, "explore", rng, "common")
    return ctx._present(event, "explore") if event is not None else []


def outing_ledger(ctx, msgs: list[str], since: int) -> str:
    """出門一趟最後那一行「得：…　失：…」：這一趟的訊息裡撿到的東西（「獲得 精鐵砂 ×1」，只列這種「名 ×數量」的；破境丹、回體丹
    那一句說明不是一樣東西，帳上只列它後面的「破境丹 +1」，FB-831）與數值變化，加上草稿裡另外補的（仗的經驗，since 之後那幾筆）；
    同一個標籤加總，增加的寫在「得」、減少的（與內傷）寫在「失」。"""
    extra = ctx._draft.changes[since:] if ctx._draft is not None else []
    changes, notes = battlelog.split_changes(msgs)
    totals = journal.combine_changes(changes + extra)
    grants = (note.removeprefix(materials.GRANT_PREFIX) for note in notes if note.startswith(materials.GRANT_PREFIX))
    items = explore_rules.merge_items(item for item in grants if explore_rules.is_item(item))
    gains = items + [ch for ch in totals if journal.change_class(ch) == "tx-up"]
    losses = [ch for ch in totals if journal.change_class(ch) == "tx-down"]
    return explore_rules.ledger(gains, losses)
