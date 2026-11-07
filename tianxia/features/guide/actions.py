"""新手引導包的動作（全部拆包第 22 批：原本 Game 上的 31 個方法，計畫 docs/superpowers/plans/2026-11-01-新手引導包-第1批.md 1.1）。
Game 留 24 個一行委派（server、測試、別的功能在叫的），其餘 7 個只有這一包在叫。第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用
tianxia/core/services_list.md 那張清單上的；這一包互相叫直接叫函式，只有被測試換掉的 _hint_triggers 與 _note_action 經 ctx。
最後一段是核心原位與出陣包叫的服務（Game._opening_on……的本體）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas, figures  # 共用規則層（輿圖 atlas 第 50 批收進、大勢人物 figures 第 40 批收進）
from tianxia import equipment, mounts, place_state, treasures  # 共用規則層
from tianxia.characters import name_key
from tianxia import attrset, insight_fx, training, journal, library, martial_arts, roster, team  # 核心、共用規則層
from tianxia.core import omen_base, seal_base, services  # 核心：碰到才說的伏筆、玉璽碎片、簽到問核心的查詢服務（包不能 import 包）
from tianxia import prologue as prologue_rules  # 共用規則層；Game.new 有個參數也叫 prologue，跟 engine 一樣叫 prologue_rules
from tianxia import step as step_rules  # 核心本體（第 36 批收進 MODULES）：「你這一步」的 REF、place
from tianxia.models import TutorialStep
from tianxia.rules import season_one, stance_rule_note
from tianxia.state import HintNote

from . import enlist, howto, newbie, opening, rules
from . import hints as hint_rules  # 跟 engine 一樣叫 hint_rules：函式裡有區域變數叫 hints

if TYPE_CHECKING:
    from tianxia.engine import Game

GRADUATE_TRIES = 12  # graduate 每一步最多試幾次；照著走卻一直前進不了（內容改版、賽季籌備中）就放棄、直接出師（原 Game.GRADUATE_TRIES）
PROLOGUE_TABS = ("practice", "craft")  # 序章裡打開這兩頁才記旗標（原 Game.PROLOGUE_TABS）
NO_REST = "（打坐已經拿掉了：體力會隨時辰自己回來，急用就服回體丹。）"  # 舊分頁按到 act:rest



def hire_here(ctx) -> bool:
    """五項屬性的季，此地酒肆有還沒有主的人可招（招募同伴包 hire；這裡照內容與名冊判，不 import 別的功能包）：h_recruit 改指向酒肆招募。"""
    s, c = ctx.state, ctx.content
    if not (c.config.hire.enabled and attrset.on(c, s.world)):
        return False
    return any(ch.hire_at == s.player.location and roster.owned_by(ctx.world, cid) is None for cid, ch in c.characters.items())

def note_action(ctx: Game, action: str) -> list[str]:
    """做完一個行動，引導（說書人的步驟與入伍段）看這一步完成了沒（rules.note_action），回那幾行（呼叫端交給 _guide）。
    叫模組屬性：tests/core/test_engine.py 換的是 tianxia.features.guide.rules.note_action。第二輪第 98 批從 Game 本體搬進來。"""
    return rules.note_action(ctx.state, ctx.content, ctx.world, action)


def note_gift(ctx: Game) -> None:
    """建角色時送了回體丹：江湖紀錄開場那一則多一行（explain-1：以前送了二十顆卻沒有任何紀錄）。接在開場那一則裡、不另起一則：
    「剛剛」不換（序章第一屏照舊什麼都不放），江湖紀錄裡看得到。只寫字，不擲骰、不動數值（假人、整季機器人照樣有這一行）。"""
    entries = ctx.state.journal
    line = howto.gift_line(ctx.content)
    if entries and entries[0].tag == journal.SEASON_START:
        entries[0] = entries[0].model_copy(update={"lines": [*entries[0].lines, line]})
    else:
        ctx._write(ctx.content.scenario.name, [line], tag=journal.SEASON_START)


def graduate(ctx: Game) -> None:
    """假人與整季機器人的序章（Game.new(graduated=True)）：把草廬前面的步驟用真的行動走一遍（遇險、拜師、探索悟意境、
    合成、換上練到第三成、修練、打坐、雪恥、配點、熔雜學），最後一步「出師」跟略過一樣交給 prologue.finish(purse=True)
    （站到起點、盤纏、體力補滿）。每一步做什麼照那一步的完成條件（TutorialStep.done_when）與寫好的欄位走，選項與屬性
    用 ctx.rng 挑（四門師門功夫、擋或喊，種子決定）；等級、功夫的品質與成數、內傷、銀兩都是真的打出來、練出來的，所以
    永遠跟真人走完草廬一模一樣，不是另外抄一份清單。
    走不下去就放棄：某一步連試 GRADUATE_TRIES 次沒前進（內容改版讓這一步照著走不通、賽季還在籌備中什麼都不能做），
    直接 finish，等於一個略過序章的人；假人不會卡在草廬。
    不叫模型（師門配方有寫好的名字、雪恥的結果是寫好的，用不到；ctx.client 先收起來，結束還回去）；也不碰共用賽季
    的時鐘（序章裡的行動只推玩家自己的進度）。走序章留下的江湖紀錄、戰報、對話框都清掉，假人看起來跟沒走序章時一樣乾淨。"""
    t, s, p = ctx.content.tutorial, ctx.state, ctx.state.player
    prologue_rules.begin(s, ctx.content)
    client, ctx.client = ctx.client, None
    try:
        tries, last = 0, p.tutorial_step
        while prologue_rules.active(s, ctx.content) and p.tutorial_step < t.prologue_steps - 1:  # 出師那一步由 finish 給
            tries = tries + 1 if p.tutorial_step == last else 1
            last = p.tutorial_step
            if tries > GRADUATE_TRIES or not graduate_pass(ctx, t.steps[p.tutorial_step]):
                break
    finally:
        ctx.client = client
    prologue_rules.finish(s, ctx.content, ctx.world, purse=True)
    prologue_rules.skip_onboarding(s, ctx.content)  # 初入江湖（新手引導第四段）是給真人看的
    s.journal, s.log, s.battles, s.battle_card = [], [], [], None
    p.guide_done, p.guide_outro = [], False


def graduate_pass(ctx: Game, step: TutorialStep) -> bool:
    """序章裡照這一步的完成條件做一個行動；這一步沒有可以做的（不認得的條件）回 False。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    goal = step.done_when
    if s.pending_event is not None:  # 事件擋著：挑一個走得到這一步旗標的選項（四景之類的，哪一個看種子）
        event = c.events[s.pending_event]
        needed = set(goal.condition.flags_all)
        options = [o for o in ctx.options(odds=False) if o.enabled and o.id.removeprefix("choice:").isdigit()]
        good = [
            o for o in options if needed <= prologue_rules.choice_flags(c, event.id, int(o.id.removeprefix("choice:")))
        ] or options
        if not good:
            return False
        ctx.choose(ctx.rng.choice(good).id)
        return True
    if p.sensing is not None:  # 草廬的有所感：做法都選得對；不畫，順其自然落回那個基本意境（假人不叫模型）
        ctx.choose(ctx._sense_prologue_choice())  # 按哪一顆問有所感包（查詢服務，全部拆包第 24 批：包不 import 包）
        return True
    fused = prologue_rules.slotted_arts(s, c, ctx.world)
    if goal.action == "view_tab":
        tab = next((flag.removeprefix("看過:") for flag in goal.condition.flags_all if flag.startswith("看過:")), "")
        view_tab(ctx, tab)
    elif step.explore_event is not None or step.explore_scene is not None:
        ctx.choose("act:explore")
    elif goal.fused:  # 武學重構：把悟到的意境裝進師父點名的那一門
        if not p.insights or step.fuse_base is None:
            return False
        ctx.slot_insight(step.fuse_base, ctx.rng.choice(p.insights))
    elif goal.fused_level and fused:
        art = fused[0]
        if art.id not in (p.member.wugong_id, p.member.neigong_id):
            ctx.switch_art(art.id)
        else:
            ctx.practice(art.kind)
    elif goal.deepened and p.insights:  # 揣摩（意境效果池：同一種意境的兩份）
        base = insight_fx.base_id(p.insights[0])
        pair = insight_fx.pieces(ctx.state, base)[:2]
        if len(pair) < 2:
            return False
        ctx.forge(None, pair)
    elif goal.action in ("rest", "train", "explore"):
        ctx.choose(f"act:{goal.action}")
    elif goal.action == "pill":  # 序章服回體丹（新手引導重做）：假人也真的服一顆（同真人，看不出來）
        ctx.take_stamina_pill(pill_only=True)
    elif goal.action == "allocate" and attrset.on(c, ctx.state.world):  # 五項屬性的季：這一步是挑成長配比（同真人）
        if p.growth_preset is None:
            ctx.pick_growth(ctx.rng.choice([preset.key for preset in c.config.attributes.v2.presets]))
        elif p.stat_points > 0:
            ctx.allocate_stat(ctx.rng.choice(attrset.keys(c)))
        else:
            return False
    elif goal.action == "allocate":
        open_stats = [k for k in team.COMBAT_STATS if p.stats.get(k, 0) < c.config.stat_cap]
        if not open_stats:
            return False
        ctx.allocate_stat(ctx.rng.choice(open_stats))
    elif "melt" in (goal.action, *goal.any_action) and step.melt_only:
        ctx.melt_art(step.melt_only)
    else:
        return False
    return True


def begin_enlistment(ctx: Game, faction_before: str | None) -> None:
    """這一下才投靠的人開始入伍段（新手引導計畫二，設計 4.1）：動作之前還沒有陣營、現在有了（投靠，或拜入陣營名下的門派）。
    已經有陣營的人不開始——換版當下就投靠了的舊存檔不走入伍段（設計 7.2）、叛投也不重來（preflight F1，所以也不需要存檔遷移）。
    框換成引薦人：剛投靠這一下不算完成任何一步（Review Focus 1）——框上若還是說書人的步驟或結語，它們的「✔」照舊留著。"""
    if faction_before is None and ctx.state.player.faction is not None and prologue_rules.onboard_step(ctx.state, ctx.content):
        prologue_rules.skip_onboarding(ctx.state, ctx.content)  # 初入江湖還沒走完就投靠了：剩下的交給引薦人帶，不兩個人搶一個框
    if faction_before is not None or not enlist.begin_if_joined(ctx.state, ctx.content):
        return
    p = ctx.state.player
    if not rules.tutorial_active(ctx.state, ctx.content) and not p.guide_outro:
        p.guide_done = []
    ctx._journal_guide(enlist.told(ctx.state, ctx.content))  # 引薦人迎你進營的話，記在這一則（設計 6.2）；不進「剛剛」、不進完成列


def greet_rejoin(ctx: Game, faction_before: str | None) -> None:
    """第二季起再投靠：入伍段早就走完（所以不重走），引薦人只打個招呼（設計 7.1、10.6；話寫在 tutorial.json 入伍段的 rejoin）。
    這一下才從散人變成有陣營（叛投不算，faction_before 不是 None）、入伍段走完、沒略過引導、不是假人、沒關提示才有——
    第一次投靠走的是入伍段；略過的人沒有要誰帶，跟開季那一句（s_return）一樣不打招呼。走提示的佇列（hints.queue_note）：
    同樣上框、按「知道了」收起、記進江湖紀錄；每季都要說，所以不記進 hints_seen；by 記哪一邊，叛投時作廢。事件型的，當場排。"""
    p = ctx.state.player
    if faction_before is not None or p.faction is None or p.guide_skipped or not enlist.done(ctx.state, ctx.content):
        return
    who = enlist.recruiter(ctx.state, ctx.content)
    if who is not None and who.rejoin:
        text = enlist.line(who, "rejoin", ctx.state, ctx.content)  # 豪強分屬兩軍的季有另一版就照它
        hint_rules.queue_note(ctx.state, HintNote(id="s_rejoin", speaker=who.name, text=text, by=p.faction))


def enlist_glow(ctx: Game, option_ids: list[str]) -> list[str]:
    """入伍段「出一次力」那一步，選單上能完成它的那幾顆（FB-093，enlist.glow）；初入江湖這一步要按的（prologue.onboard_glow）；
    網頁讓它們發光。"""
    return enlist.glow(ctx.state, ctx.content, option_ids) + prologue_rules.onboard_glow(ctx.state, ctx.content, option_ids)


def guide_box(ctx: Game) -> dict | None:
    """行動列上方的對話框（引導重做設計 8.1、6.2）：引導還沒做完是目前這一步的話；剛走完、結語還沒按「知道了」是結語；
    其他（略過、早就做完的舊角色）是 None。done 是上一次行動完成的那幾行（✔ 與獎勵）。框上寫的人照這一步
    （TutorialStep.speaker），沒寫就是 Tutorial.speaker；這一步沒有話（序章第一步）時不畫框。
    還有事件待處理時，這一步的話換成「先把眼前的「事件名」了結」（每一步都一樣，步驟本身不動；結語照舊）。
    key 認的是「哪一步」（TutorialStep.id，結語是 "outro"），不看那一句話：網頁記玩家收起的那一步記的是它（FB-076）——
    事件的句子每遇到新事件就換一句，記句子的話收起的框每個新事件都會自己又展開。
    pending 標這一句是不是「先把眼前的「…」了結」：它只是重複底下事件卡片已經寫的話，展開時事件的最後一個選項被擠出第一屏，
    所以網頁預設把這一句收成一行（玩家沒按過「收起」也一樣；框上有要看的完成列〔done〕時不收；只有這一句，新的一步照舊展開，
    玩家仍可點開，FB-076）。結語永遠是 False。
    碰到才說（新手引導計畫三）排在最後：步驟 → 結語 → 入伍段（進行中或結尾）→ 提示，一次一條（hint_box）。略過新手引導的人
    不畫前面那三段，但提示照樣有（設計 7.3：「不再提示」是另一個開關）。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    t = c.tutorial
    todo = rules.steps(s, c)
    if ctx._preparing() or s.world.ended:  # 籌備中、休季什麼都不能做，不叫人去探索（FB-045～052 審查 I1）
        return None
    if p.guide_skipped:  # 略過的人不再畫引導的框，換季、第一季多出的步驟也一樣（8.1.4；畫面批次審查 I4）；提示不受影響
        return hint_box(ctx)
    if p.tutorial_step < len(todo):
        step = todo[p.tutorial_step]
        if not step.text or (prologue_rules.active(s, c) and (s.pending_event or s.player.sensing is not None)):
            return None  # 序章第一步（還沒遇到師父）、序章的事件或草廬四景的有所感端出來的時候：畫面就是那一張（新手引導計畫一）
        def fill(text: str) -> str:  # 序章的話裡的 {武學}：換成合成出來的那一門
            return prologue_rules.fill(text, s, c, ctx.world)

        # 眼前有事件還沒了結時是 guide.pending_line，不推這一步；了結後原樣回來（FB-063；「下一步」也用同一句）
        pending = rules.pending_line(s, c) is not None
        box = {
            "speaker": rules.speaker_of(c, step), "key": step.id, "scene": fill(step.scene), "text": fill(rules.step_text(s, c)),
            # 收起來那一行（網頁用 line || text）：待處理時話已經換成「先把眼前的「…」了結」，這一步自己的短提示不能留著
            # ——收著的框寫著短提示、跟事件擋著路互相矛盾（序章之外的步驟也可能有 line；序章自己在事件出現時整個框不畫，見上）
            "line": "" if pending else fill(rules.step_words(s, c, step)[1]), "done": list(p.guide_done), "end": False, "pending": pending,
        }
        if step.paged:  # 話太長的序章步驟：網頁照空一行切成幾頁（只有分頁的步驟才帶這個鍵）
            box["paged"] = True
        if prologue_rules.onboard_step(s, c) is not None:  # 初入江湖：老周的話不切成三行（同入伍段，要照著做的話整段看得到）
            box["full"] = True
        return box
    if p.guide_outro and t.outro:
        return {
            "speaker": t.speaker, "key": "outro", "scene": "", "text": t.outro, "line": "", "done": list(p.guide_done), "end": True,
            "pending": False,
        }
    # 引導與結語都過去了：入伍段（新手引導計畫二），再來是碰到才說（計畫三）。順序固定是 步驟 → 結語 → 入伍段 → 提示，「知道了」只收框上那一個
    return enlist.box(s, c) or hint_box(ctx)


def hint_box(ctx: Game) -> dict | None:
    """碰到才說的框：排著的第一條。眼前有事件或有所感還沒了結時不出（F3）：提示的框是 end 的、網頁不會收成一行，擺在事件的選項上面會把最後
    一個選項擠出第一屏（FB-076）；它排著等，事件了結之後上框。key 是那一條的 id，pending 永遠是 False；full：話不被切掉（設計 6.2）；
    hint：這是碰到才說的框（結語、入伍段的框沒有這個鍵）——網頁認它，在修練頁、煉製頁也畫（在那兩頁做的事觸發的提示不必切回江湖頁才看到）。"""
    p = ctx.state.player
    # 有所感（悟意境設計第零節）的卡也一樣：選做法、畫一筆都佔著畫面，跟事件待處理同一種等法。跟人物談話也是（explain-1）：
    # 對話的幾個選項跟事件的選項一樣佔著畫面，第一次談話說的 h_bond 擺在上面會把「告辭」擠出第一屏；告辭之後上框
    if not p.hint_queue or ctx.state.pending_event is not None or p.sensing is not None or p.pending_companion is not None:
        return None
    note = p.hint_queue[0]
    return {
        "speaker": note.speaker, "key": note.id, "scene": "", "text": note.text, "line": "", "done": [], "end": True,
        "pending": False, "full": True, "hint": True,
    }


def hint_up(ctx: Game) -> HintNote | None:
    """對話框此刻顯示的就是排著的第一條提示（前面沒有引導的步驟、結語、入伍段，也沒有事件擋著）時，那一條；不然是 None。"""
    p = ctx.state.player
    if not p.hint_queue:
        return None
    box = guide_box(ctx)
    note = p.hint_queue[0]
    return note if box is not None and box["end"] and box["key"] == note.id else None


def surface_hint(ctx: Game) -> None:
    """提示上框的那一刻（第一次）才算說過：記進 hints_seen、把說的話記進江湖紀錄（設計 6.2「說過的話都記進見聞」，控制者裁示 N1、N12）。
    排進佇列時還不算：前面有別的框、事件擋著、不再提示或換季把它清掉了，之後碰到還有機會聽到。冪等（一條只記一次），
    所以可以放心地在每個可能讓框換成提示的地方叫：排進去之後（_hint）、按「知道了」之後（下一條上框）、行動與同步的最後（事件了結、
    引導走完、入伍段走完）。在行動裡寫進這一則的 guide，不在行動裡（同步、按「知道了」）接在最新一則的 guide 後面。"""
    note = hint_up(ctx)
    if note is not None and hint_rules.show(ctx.state, ctx.content, note):
        ctx._journal_guide([f"【{note.speaker}】{note.text}"])


def drop_stale_hints(ctx: Game) -> None:
    """排著還沒上框、條件已經不成立的拿掉（新手引導重做：療好傷才輪到「內傷去醫館」那一條就不說；沒說過，之後再受傷還會說）。"""
    p = ctx.state.player
    p.hint_queue = [n for n in p.hint_queue if n.shown or not (n.id == "h_injury" and p.member.injury < 1)]


def hint(ctx: Game, hint_id: str) -> None:
    """碰到某個玩法：排一條提示（序章裡不排，序章本身在教；新手引導計畫三）。說過的、已經排著的、關了提示的、假人都不排；
    輪得到上框就當場上框（surface_hint）。"""
    if not prologue_rules.active(ctx.state, ctx.content):
        hint_rules.queue(ctx.state, ctx.content, [hint_id])
        surface_hint(ctx)


def hint_triggers(ctx: Game, only: set[str] | None = None) -> list[str]:
    """此刻成立的碰到才說（設計 5.2）：看的都是角色現在的狀態（修練失敗留下熟練度、戰報裡有一場沒打贏的、路上見聞真的發生過……），
    「第一次」由 hints_seen 管。順序照設計的表：師父的在前、引薦人的在後。h_snubbed（被名將打發）與 h_mandate（玉璽碎片的秘密
    揭開）不看狀態，是事件發生時自己叫 _hint，不在這裡。only 給了就只算裡面的條：_check_hints 只算書裡有、還沒說過、也還沒排著的，
    其餘每次行動與每次同步都是白算一遍（決戰要讀資料庫、大勢人物要算此刻的所在）。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player

    def want(hint_id: str) -> bool:
        return only is None or hint_id in only

    on: list[str] = []
    if want("h_merge") and len(p.insights) >= 2:
        on.append("h_merge")
    if want("h_clash"):
        wugong = team.player_art(s, c, ctx.world, p.member.wugong_id) if p.member.wugong_id else None
        neigong = team.player_art(s, c, ctx.world, p.member.neigong_id) if p.member.neigong_id else None
        if wugong and neigong and martial_arts.counters(wugong.attribute, neigong.attribute):  # 相剋是一對一對的，兩個方向都一樣
            on.append("h_clash")
    # 第一場沒打贏的仗：僵持與落敗都算（以前只算落敗：身法閃成僵持的人師父不開口）；決戰與挑戰本人不在這三種裡
    if want("h_lose") and any(r.tier not in team.WIN_TIERS for r in s.battles if r.kind in ("train", "sortie", "wild", "event")):
        on.append("h_lose")
    if want("h_injury") and p.member.injury > 0:
        on.append("h_injury")
    # 新手引導重做（2026-10-22）：練功連輸兩場（僵持不算輸）、心得第一次夠自創、第一次到有酒肆的城、點數沒配又升了一級
    if want("h_field_lose") and sum(1 for r in s.battles if r.label == training.PRACTICE and r.tier not in team.WIN_TIERS
                                    and r.tier != "僵持") >= 2:
        on.append("h_field_lose")
    if want("h_create") and ctx._create_on() and p.created_count == 0 and ctx._create_allowed() is None \
            and p.stats.get("xinde", 0) >= ctx._create_price():
        on.append("h_create")
    if want("h_tavern") and ctx._tavern_on() and ctx._tavern_here() and p.location not in prologue_rules.onboard_towns(c):  # 老周在那裡教過酒肆
        on.append("h_tavern")
    if want("h_points") and p.stat_points >= 2:
        on.append("h_points")
    # 「這裡能學新的底」：只算現在學得了的（learn 擋下的——名望、學費、門派、陣營、持有滿了——都不算，不然師父說能學、按下去卻是「學不了」）
    if want("h_basic_art") and any(problem is None for _, problem in library.lessons_here(s, c)):
        on.append("h_basic_art")
    if want("h_recruit") and (ctx._recruit_target() is not None or ctx._recruitable_here() or hire_here(ctx)):
        on.append("h_recruit")
    if want("h_free_text") and s.pending_event:
        event = c.events.get(s.pending_event)
        if event is not None and ctx._free_text_of(event) is not None:
            on.append("h_free_text")
    if want("h_road") and p.recent_sights:  # 路上見聞真的發生過才會記
        on.append("h_road")
    if want("h_cap") and library.held_count(s) >= library.cap_of(s, c) - 5:
        on.append("h_cap")
    status = ctx._battle_status(tick=False) if want("h_spectator") or want("h_showdown") else None
    watching = status is not None and ctx._watching_battle(*status)
    # 散人只在決戰所在的大區、還沒投效時才說（N3）：人在別處不算「遇上」；說的是可以臨時投效（試玩回饋 2026-10-08）
    if want("h_spectator") and status is not None and p.faction is None and p.name not in status[0].participants \
            and ctx._at_battle(status[1]):
        on.append("h_spectator")
    if want("h_foreshadow") and omen_base.heard_any(s):
        on.append("h_foreshadow")
    if want("h_event_reveal") and p.events_seen:
        on.append("h_event_reveal")
    if want("h_promotion") and p.summons is not None:
        on.append("h_promotion")
    if want("h_showdown") and status is not None and p.faction is not None and status[0].phase == "muster" and not watching:
        on.append("h_showdown")
    # 大勢人物本人（人物表上的人，第一季的規則開著才有）：不是「這裡有可以交友的人物」（_figures_here 連陶謙、曹操、劉備也列，F1）
    if want("h_figure") and season_one(c, s.world) and figures.present_at(s, c, p.location):
        on.append("h_figure")
    on += _more_triggers(ctx, want)
    return on


SETTLED_LEVEL = 5  # 簽到、萬寶閣這種「不是碰到一個玩法」的：升到這一級（新手目標第一條）才說，開局那幾步不被打斷


def _more_triggers(ctx: Game, want) -> list[str]:
    """補新手教學（2026-11-05）的十一條：截殺自保、簽到、萬寶閣、形象、玉璽碎片、宴客、傳功、坐騎、寶物、地點變樣、戰記分享；加上歷練快滿了。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    w = s.world
    on: list[str] = []
    # 截殺自保：過了截殺的新手期（而且投靠了一方，散人只有被通緝才截得到），或第一次被人截殺過
    if want("h_raid_guard") and c.config.raid.enabled and not w.ended and c.scenario.factions and (
            name_key(p.name) in w.raided or (p.faction is not None and not roster.raid_newbie(s, c))):
        on.append("h_raid_guard")
    if want("h_checkin") and services.checkin_on(c, w) and len(p.checkin_days) >= 2:  # 第二天又來：簽到是天天的事
        on.append("h_checkin")
    if want("h_mall") and c.config.mall.enabled and p.member.level >= SETTLED_LEVEL:
        on.append("h_mall")
    # 形象：上過一次擂台（看過自己那副模樣）；形象開著＝商城開著而且有形象可賣（looks.rules.on 同一條；包不能 import 包）
    if want("h_looks") and c.config.mall.enabled and c.looks and any(r.kind == "arena" for r in s.battles):
        on.append("h_looks")
    if want("h_seal") and seal_base.on(c) and seal_base.key(p.name) in seal_base.holders(ctx.world.seal_state().registry):
        on.append("h_seal")
    # 宴客：人在擺著的宴席那裡（同 feast.rules.is_open；包不能 import 包）
    if want("h_feast") and any(not f.settled and f.start <= w.time < f.end and f.place == p.location for f in w.feasts):
        on.append("h_feast")
    if want("h_chuangong") and ctx._chuangong_ready():
        on.append("h_chuangong")
    if want("h_mount") and mounts.on(c) and (p.mount is not None or equipment.in_slot(p, "mount")):
        on.append("h_mount")
    if want("h_treasure") and treasures.on(c) and (p.treasure is not None or equipment.in_slot(p, "treasure")):
        on.append("h_treasure")
    if want("h_place") and place_state.on(c) and place_state.kind_at(w, c, p.location) != place_state.PEACE:
        on.append("h_place")
    # 戰記：打完一場決戰或奪璽單挑（只有這兩種有戰記）
    if want("h_tale") and any(r.kind in ("showdown", "seal") for r in s.battles):
        on.append("h_tale")
    # 歷練快滿了（五項屬性的季）：這一季從事件得來的屬性到 event_hint_at（到頂之前說一次，再磨下去長進有限）
    if want("h_lilian") and attrset.on(c, w) and attrset.event_total(s) >= c.config.attributes.v2.event_hint_at:
        on.append("h_lilian")
    return on


def queue_triggered_hints(ctx: Game) -> None:
    """成立的狀態提示排一條進佇列（N2，控制者裁示）：同一時間最多一條狀態提示在框上或排著——佇列裡還有一條沒按「知道了」的狀態提示時，
    不管是行動還是同步都不再排新的（伺服器每個動作都是先 sync 再做動作，兩次檢查各排一條就變成連著兩個框；人閒著不動、
    同步每十秒問一次也不會排成一長串）；按過「知道了」之後的下一次檢查，條件還成立才排下一條（開局一排「知道了」是引導重做
    要拿掉的）。事件型的（h_snubbed、h_mandate、開季那一句、再投靠的招呼）當場排，不吃這個限速，也不算在裡面。
    排不進去的（散人碰到沒有散人版的陣營提示）不算名額，接著看後面的。不看的時候：假人、關了提示、籌備中與休季（框不畫，
    排進去就算說過會白白丟掉，F7）、序章。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    drop_stale_hints(ctx)
    if p.bot or p.hints_off or any(n.id in hint_rules.STATE for n in p.hint_queue):
        return
    # 只算書裡有的狀態提示（事件型的不看狀態，留在 waiting 裡也沒東西可算，只會讓下面的提早返回永遠用不上），還沒說過、也還沒排著的（N10）
    waiting = {h.id for h in c.hints.hints if h.id in hint_rules.STATE} - p.hints_seen
    if not waiting or ctx._preparing() or s.world.ended or prologue_rules.active(s, c):
        return
    for hint_id in ctx._hint_triggers(waiting):
        queued = len(p.hint_queue)
        hint_rules.queue(s, c, [hint_id])
        if len(p.hint_queue) > queued:
            return


def check_hints(ctx: Game) -> None:
    """每次行動、修練頁與配點的動作、出發、同步做完之後看一遍（新手引導計畫三）：該說的排進佇列，輪到的上框（surface_hint）。
    呼叫的位置都在記進江湖紀錄之前，說的話才記在這一次行動那一則。"""
    check_newbie(ctx)
    queue_triggered_hints(ctx)
    surface_hint(ctx)


def check_newbie(ctx: Game) -> None:
    """做到的新手目標發獎勵，那一句記進這一則江湖紀錄的引導那幾行（不另起一則；假人一樣拿：畫面上看不出誰是假人）。"""
    got = newbie.grant(ctx.state, ctx.content)
    if got:
        ctx._journal_guide([f"{line}{change}" for line, change in got])


def nearest_to(ctx: Game, targets: set[str]) -> str | None:
    """離這裡最近的那一個地點（先照摸清的路，都走不到照所有開放的地點，同 clinic.nearest）；這裡就是的話回這裡。"""
    s, c = ctx.state, ctx.content
    if s.player.location in targets:
        return s.player.location
    for found in (atlas.routes(s, c), atlas.shortest_routes(s, c)):
        reachable = [route for loc_id, route in found.items() if loc_id in targets and route.path]
        if reachable:
            return min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path)).path[-1]
    return None


def newbie_go(ctx: Game, go: str) -> dict:
    """「去做」：{"tab": 分頁} 或 {"move": 地點 id, "place": 名字}（網頁打開移動清單、把那一個亮起來；人就在那裡是 {"tab": "jianghu"}）。"""
    c = ctx.content
    if go in ("craft", "practice", "map"):
        return {"tab": go}
    if go.startswith("practice"):
        tier = int(go[-1])
        targets = {loc.id for loc in c.locations.values() if ctx._practice_tier(loc) == tier}
    elif go == "tavern":
        targets = {loc.id for loc in c.locations.values() if ctx._tavern_at(loc.id)}
    else:  # 懸賞榜、擂台都在城鎮類的地點
        targets = {loc.id for loc in c.locations.values() if training.is_town(c, loc)}
    where = nearest_to(ctx, targets)
    if where is None or where == ctx.state.player.location:
        return {"tab": "jianghu"}
    return {"move": where, "place": c.locations[where].name}


def newbie_view(ctx: Game) -> dict | None:
    """任務卡上「新手目標」那一塊：引導（序章、初入江湖）走完、新手期裡、還有沒做完的才有。一次亮最上面三條。"""
    s, c = ctx.state, ctx.content
    if not newbie.active(s, c) or prologue_rules.onboard_step(s, c) is not None:
        return None
    rows = [{"key": goal.key, "text": newbie.text_of(s, c, goal), "reward": newbie.reward_text(c, goal), "go": newbie_go(ctx, goal.go),
             "drifter": goal.key == "side" and s.player.faction is None} for goal in newbie.todo(s)]
    return {"title": newbie.TITLE, "rows": rows, "done": len(s.player.newbie_done), "total": len(newbie.GOALS)}


# core_step（全部拆包第 36 批「你這一步」）：newbie 那一格（core/features.py 的 STEP_ORDER：伏筆之後、去投靠之前）
def newbie_step_items(ctx: Game, status: dict) -> list[dict]:
    """「你這一步」的新手目標那幾件（原本 weekcard._steps 的新手目標那一段）：讀殼算好傳進來的 status["newbie"]（newbie_view 那一份，不重算），
    每一條一件、多一個 i（第幾條）。"""
    out: list[dict] = []
    view = status.get("newbie")
    if view:
        for i, r in enumerate(view["rows"]):
            out.append({"kind": "newbie", "text": r["text"], "i": i, "reward": r.get("reward", ""), step_rules.REF: ("newbie", r.get("key"), r.get("go"))})
    return out


def newbie_step_place(ctx: Game, ref: tuple) -> tuple:
    """新手目標那一件的 (id, target, None)（原本 step._target 的新手目標那一支）：「去做」帶去的地點（newbie_go 的 move），不是地點的 target 是 None。"""
    return ref[1], step_rules.place(ctx, (ref[2] or {}).get("move")), None


def newbie_drifter(ctx: Game) -> list[str]:
    """任務卡「就當散人」：記下這一條（投靠一方或就當散人）。只改自己的記號，獎勵照平常的檢查發。"""
    p = ctx.state.player
    if p.faction is not None or not newbie.active(ctx.state, ctx.content):
        return []
    p.newbie_marks.add(newbie.DRIFTER)
    check_newbie(ctx)
    return [newbie.DRIFTER_LINE]


def set_hints_off(ctx: Game, value: bool) -> None:
    """設定頁的「不再提示」：打開時排著的清掉（沒上過框的不算說過，關掉再打開還聽得到）；對話框的引導與入伍段不受影響。"""
    ctx.state.player.hints_off = bool(value)
    if value:
        ctx.state.player.hint_queue = []


def guide_ack(ctx: Game) -> list[str]:
    """對話框的「知道了」：只收框上看得到的那一個（順序見 guide_box）——提示就是排著的第一條（接著下一條上框）；結語還沒按、入伍段
    已經走完時，按下去是結語，入伍段的結尾留到下一個框（F8）；引導的步驟還在框上時沒有「知道了」可按，什麼都不收。
    收之前先讓框上的提示上框（surface_hint）：框是別的狀態改變（引導走完、事件了結）讓它輪到的、還沒有任何呼叫把它記成說過時，
    不能憑空吞掉一條（記說過、記進江湖紀錄都要在它被收掉之前）。"""
    p = ctx.state.player
    surface_hint(ctx)
    if hint_up(ctx) is not None:
        p.hint_queue.pop(0)
    elif p.guide_outro:
        p.guide_outro = False
    elif not rules.tutorial_active(ctx.state, ctx.content):
        p.enlist_end = False
    p.guide_done = []
    surface_hint(ctx)  # 結語、入伍段的結尾、上一條提示收掉之後，後面等著的提示輪到上框
    return []


def rest(ctx: Game) -> list[str]:
    """序章教體力那一步的調息（新手引導設計 3.1）：一下回滿。打坐本身 2026-10-12 拿掉了（企劃者「打坐也拿掉」：體力只靠時間
    與一天有上限的回體丹），選單上只在這一步有這顆（_everyday_options）；不在這一步按到（舊分頁）只回一句。"""
    line = prologue_rules.instant_rest(ctx.state, ctx.content)
    if not line:
        return [NO_REST]
    ctx.state.player.stamina = float(ctx.content.config.stamina_max)
    return [line]


def skip_tutorial(ctx: Game) -> list[str]:
    steps = len(rules.steps(ctx.state, ctx.content))
    if (ctx.state.player.tutorial_step >= steps and not enlist.active(ctx.state, ctx.content)
            and not enlist.waiting(ctx.state, ctx.content)):
        return []  # 引導走完了、入伍段也沒在進行、也不會再開始（beta 季、內容沒有入伍段、早就走完、略過過）：沒有什麼好略過的
    # 在序章裡略過：站到起點、拿出師的盤纏（設計 7.3）；序章外略過照舊
    purse = prologue_rules.finish(
        ctx.state, ctx.content, ctx.world, purse=prologue_rules.active(ctx.state, ctx.content),
    )
    ctx.state.player.tutorial_step = steps
    ctx.state.player.guide_done, ctx.state.player.guide_outro = [], False  # 略過後對話框不再出現（8.1.4）
    ctx.state.player.guide_skipped = True
    enlist.skip(ctx.state, ctx.content)  # 入伍段也略過（設計 7.3），之後投靠不開始
    ctx._write("新手引導", purse, tag="已略過")
    surface_hint(ctx)  # 略過讓框換成排在引導後面的提示：同一下上框（記說過、記進江湖紀錄），不等下一次同步
    return ctx._log(["（已略過新手引導。）"] + purse)


def view_orders(ctx: Game) -> list[str]:
    """軍令卡出現在畫面上（網頁在入伍段第一步、卡片真的進了畫面才送，F5）：看入伍段這一步有沒有完成；不寫紀錄、不換「剛剛」。"""
    ctx._guide(ctx._note_action("view_orders"))
    return []


def view_map(ctx: Game) -> list[str]:
    ctx.state.player.flags.add("看過地圖")
    ctx._guide(ctx._note_action("view_map"))  # 接在最新一則，「剛剛」不換
    return []


def view_tab(ctx: Game, tab: str) -> list[str]:
    """打開修練或煉製頁（網頁在序章裡才送）：記一個旗標（看過:practice），看引導這一步有沒有完成；不寫紀錄、不換「剛剛」。"""
    if tab not in PROLOGUE_TABS:
        return []
    ctx.state.player.flags.add(f"看過:{tab}")
    ctx._guide(ctx._note_action("view_tab"))
    return []


def prologue_view(ctx: Game) -> dict | None:
    """序章的畫面要亮什麼、發光什麼（prologue.view）；不在序章是 None。"""
    return prologue_rules.view(ctx.state, ctx.content)


def onboard_view(ctx: Game) -> dict | None:
    """初入江湖的畫面要亮什麼、發光什麼（prologue.onboard_view）；不在初入江湖是 None。"""
    return prologue_rules.onboard_view(ctx.state, ctx.content)


def prologue_recap(ctx: Game) -> str:
    """設定頁的「重看序章」（設計 7.1）：序章的事件與師父的話照順序排成一頁，只能讀。沒有序章是空字串。
    只看內容、不看這個角色走到哪一步（{武學} 寫成「新武學」，每個人合出來的不一樣的話不寫死）。"""
    t = ctx.content.tutorial
    if t.location is None:
        return ""
    events = ctx.content.events
    parts: list[str] = []
    event_id = t.start_event
    seen: set[str] = set()
    while event_id is not None and event_id in events and event_id not in seen:  # 開場那一則一路接下去（遇險、拜師）
        seen.add(event_id)
        event = events[event_id]
        parts.append(f"**{event.title}**\n\n{event.text}")
        # 走下去的那個選項（有接下一則的、沒有就第一個）的結果文字：遇險的下場、師父收徒之後那一段（T7 審查 M5）
        choice = next((ch for ch in event.choices if ch.effect.next_event), event.choices[0])
        if choice.effect.text:
            parts.append(choice.effect.text)
        event_id = choice.effect.next_event
    for step in t.steps[: t.prologue_steps]:
        text = "\n\n".join(x for x in (step.scene, step.text) if x)
        if text:
            parts.append(text.replace("{武學}", "新武學"))
        sights = events.get(step.explore_event) if step.explore_event else None
        if sights is not None:  # 探索那一步之後：四景的引子與每一景悟到的那一句
            parts.append("\n\n".join([f"**{sights.title}**\n\n{sights.text}"] + [ch.effect.text for ch in sights.choices if ch.effect.text]))
        scene = ctx.content.insight_scenes.get(step.explore_scene) if step.explore_scene else None
        if scene is not None:  # 草廬四景是有所感的場景：場景的引子與卡上的每一個做法（悟到的句子是引擎照屬性寫的，不寫死）
            parts.append("\n\n".join([f"**{scene.title}**\n\n{scene.text}"] + [m.text for m in scene.methods]))
    if t.leave_text:
        parts.append(t.leave_text)
    return "\n\n---\n\n".join(parts)


def quest_text(ctx: Game) -> str:
    return rules.quest_text(ctx.state, ctx.content, ctx.world)


# ── 核心原位與出陣包叫的服務（Game 上一行的委派；計畫 1.4）──


def opening_on(ctx: Game) -> bool:
    return opening.on(ctx.content, ctx.state.world)


def opening_begin(ctx: Game) -> None:
    opening.begin(ctx.state, ctx.content)


def opening_pending(ctx: Game) -> bool:
    return opening.pending(ctx.state, ctx.content)


def opening_deliver(ctx: Game) -> list[str]:
    return opening.deliver(ctx.state, ctx.content)


def opening_gate(ctx: Game) -> str:
    return opening.GATE


def tutorial_intro(ctx: Game) -> list[str]:
    return rules.tutorial_intro(ctx.content)


def base_step_count(ctx: Game) -> int:
    return rules.base_step_count(ctx.content)


def guide_speakers(ctx: Game) -> set[str]:
    return rules.speakers(ctx.content)


def enlist_done(ctx: Game, state) -> bool:
    return enlist.done(state, ctx.content)


def mark_veteran(ctx: Game) -> bool:
    return enlist.mark_veteran(ctx.state, ctx.content)


def enlist_expire(ctx: Game) -> list[str]:
    return enlist.expire(ctx.state, ctx.content)


def deliver_enlist(ctx: Game) -> None:
    """sync.deliver 的 enlist 那一格（core_seams，全部拆包第 55 批）：第一道軍令一週還沒做完：引薦人照樣說結語（FB-094）；說的話記進江湖紀錄。不進回話。"""
    ctx._guide(enlist_expire(ctx))


def carry_season(ctx: Game, old, fresh) -> None:
    """season.carry 的 guide 那一格，排最前面（core_seams，全部拆包第 55 批；照原位搬，不看開關）。序章的 begin、skip_onboarding 會寫 fresh，後面的格照蓋，跟原本一樣。"""
    c = ctx.content
    # 做完或略過（skip_tutorial 也是設成步數）：看不分季的那幾步；第一季多的兩步排在後面，回鍋的人接著做（計畫 T6）。
    # 舊存檔先換算成新引導的步數（設計 7.2）
    step = prologue_rules.migrated_step(old.player, c)
    carried = step >= base_step_count(ctx)
    if carried:
        fresh.player.tutorial_step = step
        fresh.player.guide_skipped = old.player.guide_skipped  # 略過的人換季也不畫對話框（畫面批次審查 I4）
    elif prologue_rules.has(c):
        if step < c.tutorial.prologue_steps and not old.player.bot:
            prologue_rules.begin(fresh, c)  # 序章沒走完就換季：回草廬從第一步重來（Review Focus 5）
        else:
            # 序章走完了、後面的步驟還沒做完（或是假人、腳本）：從序章之後的起始步重來，不再回草廬；假人不走初入江湖
            t = c.tutorial
            fresh.player.tutorial_step = t.prologue_steps
            if old.player.bot:
                prologue_rules.skip_onboarding(fresh, c)
    if enlist_done(ctx, old):
        fresh.player.enlist_step = old.player.enlist_step  # 入伍段只走一次（設計 7.1）；沒走完的下一季投靠時從頭走
    # 碰到才說（新手引導計畫三）：說過的與「不再提示」的開關帶到下一季，排著還沒上框的不帶（沒說過，下一季碰到還會說）。
    # 引導走完的回鍋玩家，開季時師父送你下山一句（設計 7.1）；略過引導的人沒有要誰帶（控制者裁示），假人、關了提示的、內容沒寫的也不送
    fresh.player.hints_seen = set(old.player.hints_seen)
    fresh.player.hints_off = old.player.hints_off
    book = c.hints
    if carried and not old.player.guide_skipped and not old.player.bot and not old.player.hints_off and book.season_return:
        fresh.player.hint_queue = [HintNote(id="s_return", speaker=book.head, text=book.season_return)]
    fresh.player.newbie_marks, fresh.player.newbie_done = old.player.newbie_marks, old.player.newbie_done  # 新手目標只有一輪


# ── 玩法說明（全部拆包第 59 批「引導二」）：Game 留一行委派的四個；句子在 howto.py，這裡只照這個人此刻的狀態把引數算好 ──


def top_up_line(ctx: Game, added: int) -> str:
    """回體丹補到送的數字那一行（Game._top_up_pills：讀檔那一刻，沒有掛鉤）。"""
    return howto.top_up_line(ctx.content, added)


def howto_text(ctx: Game) -> str:
        """設定抽屜的「玩法說明」（Markdown，explain-1 第四項；explain-2 加了這一季在打什麼、名望、投靠與軍令、三方、修練與煉製）：
        數字讀設定（howto.page）。序章略過的人也看得到（設定抽屜誰都打得開；新手期江湖頁另有一個入口）。招募那一句只在內容裡
        真的有人能招募時才寫。"""
        c = ctx.content
        rule = stance_rule_note(ctx.state, c) if season_one(c, ctx.state.world) else ""  # 「這一季在打什麼」那一節的收季規則（explain-2）
        return howto.page(
            c, ctx.state.world, recruitable=any(ch.kind == "recruitable" for ch in c.characters.values()), rule=rule,
        )


def stamina_help(ctx: Game, newbie: bool, button: bool) -> list[str]:
    """點體力條看的說明（status_data 表 help 那一格的 stamina_help；第 66 批的表裡，那一格留在核心、照舊叫委派）。button：體力條上有沒有那顆鈕。"""
    s, c = ctx.state, ctx.content
    return howto.stamina_lines(
        c, s.world, newbie, s.player.stamina_pills, button=button, today=ctx.pills_left_today(),
        card=ctx._pill_card_bonus() if c.config.stamina_pills_per_day > 0 else 0,  # 月卡（FB-480）：上限照 pill_cap 寫
    )


def war_help(ctx: Game) -> dict[str, list[str]]:
    """點戰況圖卡、態勢、大事、主線看的說明（status_data 表 war 那一格的 war_help：同上）。"""
    return howto.war_help(ctx.state, ctx.content)


def glow_slot(ctx: Game, frame) -> dict:
    """main 表的 glow 那一格（全部拆包第 66 批）：入伍段「出一次力」：選單上能完成它的那幾顆（FB-093）；網頁讓它們發光，「此地還能做」攤開。
    改 guide 那一格已經合進去的 view["guide"]，自己沒有鍵。"""
    if frame.view["guide"] is not None:
        frame.view["guide"]["glow"] = enlist_glow(ctx, [o.id for o in frame.options if o.enabled])
    return {}
