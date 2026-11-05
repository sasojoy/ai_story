"""全服決戰「打」那一半之三：推進與結算（全部拆包第 8 批；計畫 docs/superpowers/plans/2026-11-01-決戰包-第4批.md）。原本 Game 上的 20 個方法，
本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3）；名字去掉前導底線（Game 的 _battle_now 與 battle_now 都轉到 battle_now：公開的那一個
本來就只是轉手）。Game 留 14 個一行委派（核心原位與別的功能在叫、測試直接叫或換掉的），其餘 6 個只有這裡叫。另加收季的收兵 close_season（原本寫在
Game.admin_end_season、admin_next_season 裡的兩段，核心經 on_season_close 接縫掛鉤叫：__init__.py）。

- 我在哪一場：battles_now、battle_now、mutate_battle_of、mutate_battle_now
- 一回合一回合推：battle_status（先決戰、再每一場攻城各推一次；季收了每一場收兵）、showdown_status（時刻表決戰那一格：tick 時把時間到了就該
  發生的事追到現在、剛收場就套結果）、battle_for_me（序章裡一律當作沒有，FB-113）、advance_battle_round（集結逾時、假人補位、沒人能打的保底、
  回合逾時、結算；回合首功包在外面）、run_battle_tick
- 收兵：shelve_unfinished_battle（季終、管理者取消決戰：不算勝負）、close_season（管理者收季、開下一季：沒打完的決戰與每一場攻城）
- 收場與論功：apply_battle_outcome、apply_outcome_trends_and_flags、settle_showdown（時刻表決戰）、open_waiting_showdown（時間到了、在等前一場
  打完的那一場）、merit_line、highlight_line
- 只能觀戰與整個取代畫面：watching_battle、fighting；份量快照補上：backfill_battle_scores（決戰打到一半上線那一版；收場補送那一格先叫它）

留在 Game 的經 ctx：被測試換掉的 _battle_status（tests/core/test_engine.py、tests/arts/test_hints.py：數一次請求推幾次）、_apply_battle_outcome
（tests/server/test_server.py：套用結果時壞一次）、_deliver_battle_results（tests/core/test_renown_cross.py）、戰力快照（核心的單打服務：_battle_scores
〔換掉〕、_battle_gear、_battle_role、_battle_road）；形象包的 _round_mvp（回合首功：決戰包不 import 形象包）；玉璽的 _mandate_weight、_seal_bare、
_deliver_seal_results（決戰收場的 _seal_settle 改發事件 battle_end：ctx.publish，第 26 批）；時刻表大事的 _deliver_big_events；地盤的 _conquest_side；Game 上的暫時旗標 _battle_ref（寄放）。這一包自己的
（sieges、muster、generals、escorts、這一檔互相叫）直接叫函式：測試只是直接叫 Game 上的委派、沒有換掉它們（手冊第十五節 PM 11/01）。
"""
from __future__ import annotations

from tianxia import allied, battle_instance, siege, territory, timetable  # 共用規則層（豪強依附、戰鬥規則核心、攻城、地盤、時刻表）
from tianxia import prologue as prologue_rules  # 共用規則層（序章；照 engine 的叫法）
from tianxia import seal  # 過渡：待搬（玉璽：天命之爭）
from tianxia.models import BattleDef
from tianxia.rules import recompute_trends, resolve_trends, season_one, world_trend_value
from tianxia.state import Rumor, TimelineResult, WorldState
from tianxia.world import _season_vehicle, showdown_key  # 核心本體：季的事用的空殼玩家、時刻表決戰照實際那一版的結果鍵
from tianxia.world import open_waiting_showdown as open_waiting  # 核心本體：開時間到了、在等的那一場決戰

from . import escorts, generals, muster, sieges

# ── 好幾場戰鬥並存（領地爭奪第二批 Task 10）：時刻表決戰一場（world.get_battle）＋攻城戰一串（world.get_sieges）──
# 沒有攻城戰時一切照舊（這一季沒開領地爭奪時 sieges 不讀資料庫、回空的）。有的時候每個人看「自己的那一場」（battle_now）：
# 選單、場景、出招、放手一搏都照它；全服的推進（battle_status 的 tick）每一場各推一次。


def backfill_battle_scores(ctx) -> None:
    """自己在戰局上的份量快照是空的（決戰打到一半上線這一版：上線前就在場上的人沒有 scores），補上現在的；
    已經有快照的人不動（加入之後換武學不影響這一場）。只在玩家自己的請求路徑呼叫（sync、_battle_choose）：
    份量只有那個玩家自己的 Game 算得出來，排程的 Game（Game.for_world）玩家是空白的，絕不能呼叫、
    world_tick 裡也沒有人呼叫它。倒下的人不補（用不到）。"""
    status = ctx._battle_status(tick=False)
    if status is None:
        return
    battle, definition = status
    name = ctx.state.player.name
    me = battle.participants.get(name)
    if me is None or me.scores or me.eliminated:
        return
    scores, road, role = ctx._mandate_weight(definition, ctx._battle_scores()), ctx._battle_road(), ctx._battle_role()
    gear, bare = ctx._battle_gear(), ctx._seal_bare()

    def _fill(b: battle_instance.BattleInstance) -> None:
        mine = b.participants.get(name)
        if mine is not None and not mine.scores:  # 鎖裡再看一次：別的路徑剛補過就不蓋掉
            mine.scores = dict(scores)
            mine.seal_bare = mine.seal_bare or bare  # 玉璽碎片改版：份量一起補的，不含碎片的那一份也補
            mine.attribute = mine.attribute or road
            mine.role = mine.role or role
            mine.mount, mine.cavalry = mine.mount or gear["mount"], mine.cavalry or gear["cavalry"]
            mine.troops, mine.troop_bonus = mine.troops or gear["troops"], mine.troop_bonus or gear["troop_bonus"]
            mine.cut = mine.cut or gear["cut"]  # 奪璽單挑吃的防具減損（3.9），上線前就在場上的人補現在的

    mutate_battle_of(ctx, battle, _fill)


def battles_now(ctx) -> list[battle_instance.BattleInstance]:
    """全服此刻的每一場：決戰那一格（收場了照舊在，同 get_battle）在前，再照開集結的先後是還沒收場的攻城戰。"""
    showdown = ctx.world.get_battle()
    return ([showdown] if showdown is not None else []) + sieges.sieges(ctx)


def battle_now(ctx) -> battle_instance.BattleInstance | None:
    """這個人看的那一場：沒有攻城戰時就是決戰那一格（world.get_battle，一個字都不變）。有攻城戰時照這個順序：按鈕指定的那一場
    （_battle_ref：加入鈕帶 @流水號）＞自己是參戰者的那一場＞自己站得進去的那一場（joinable 的第一場，FB-566：同一個大區兩場同時
    集結、排在前面的那一場自己站不進去時，以前回排第一的那一場，選單沒有加入鈕、場景寫「插不上手」）＞自己大區裡集結中或開打的
    （決戰在前）＞決戰那一格——別處的攻城戰不畫在別人的場景上（全服都看會很吵；決戰照舊全服看得到）。
    Game.battle_now（假人程式與 bot_policy 讀它，取代 world.get_battle）與 Game._battle_now 都轉到這裡。"""
    showdown = ctx.world.get_battle()
    found = sieges.sieges(ctx)
    if not found:
        return showdown
    live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + found
    if ctx._battle_ref is not None:
        return next((b for b in live if b.record_id == ctx._battle_ref), None)
    name = ctx.state.player.name
    mine = next((b for b in live if name in b.participants), None)
    if mine is not None:
        return mine
    joinable = muster.joinable(ctx)  # FB-566：自己站得進去的那一場先
    if joinable:
        return joinable[0]
    here = muster.in_region(ctx, live)
    return here[0] if here else showdown


def mutate_battle_of(ctx, battle: battle_instance.BattleInstance, fn) -> battle_instance.BattleInstance | None:
    """改這一場（照它是決戰還是攻城走 store 的那一個；同 mutate_battle：fn 在交易裡改、回改完的那一場）。"""
    if battle.siege is not None and battle.record_id is not None:
        return ctx.world.mutate_siege(battle.record_id, fn)
    return ctx.world.mutate_battle(fn)


def mutate_battle_now(ctx, fn) -> battle_instance.BattleInstance | None:
    """改這個人看的那一場（battle_now）；沒有就不動、回 None。"""
    battle = battle_now(ctx)
    return None if battle is None else mutate_battle_of(ctx, battle, fn)


def battle_status(ctx, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
    """目前這場全服戰鬥的最新狀態（有攻城戰時是這個人看的那一場，battle_now）。沒有攻城戰時照舊（showdown_status）。
    有攻城戰時：季收了，決戰與每一場攻城都收兵；tick 時決戰與每一場攻城各推一次（同一次請求裡一場只推一次，見 showdown_status
    的說明），再回這個人看的那一場（收場了是 None）。"""
    found = sieges.sieges(ctx)
    if not found:
        return showdown_status(ctx, tick)
    if ctx.state.world.ended:
        if tick:
            showdown = ctx.world.get_battle()
            if showdown is not None and showdown.phase != "ended":
                shelve_unfinished_battle(ctx)
            for b in found:
                sieges.shelve_siege(ctx, b)
        return None
    if tick and ctx.world.paused_at() is None:
        showdown_status(ctx, tick=True)
        for b in found:
            sieges.tick_siege(ctx, b)
    focus = battle_now(ctx)
    if focus is None or focus.phase == "ended":
        return None
    definition = sieges.definition_of(ctx, focus)
    return None if definition is None else (focus, definition)


def showdown_status(ctx, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
    """目前這場全服戰鬥的最新狀態。tick=True 時順便處理所有「只要時間到了就該自動
    發生」的事（集結逾時自動分配、回合逾時代選保守行動、機器人立刻選、全員選完就
    結算）——不管是誰的畫面刷新到這裡，都會把戰鬥狀態追趕到跟現實時間一致，誰先連線
    誰先看到，別人下次連線也會看到同一份結果（跟 _reconcile_season 同一套精神）。
    tick=False 只單純讀取，不會推進任何東西——options()/scene_text() 同一次畫面刷新
    都會各呼叫一次這個方法，只讓其中一個（options()）真的推進，避免同一次刷新裡
    推進兩次（純機器人對戰、沒有人類卡著等行動時，兩次推進會在一次畫面刷新裡偷跑
    兩回合，而不是一回合）。沒有進行中的戰鬥，或戰鬥已經結束，回傳 None。"""
    raw = ctx.world.get_battle()
    if raw is None:
        return None
    if ctx.state.world.ended:
        # 季結束了：沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了），參戰者回到休季畫面（試玩回饋 FB-015）；
        # 參戰者各補一則「沒打完、不算勝負」的江湖紀錄（FB-035）
        if tick and raw.phase != "ended":
            shelve_unfinished_battle(ctx)
        return None
    definition = ctx.content.battles.get(raw.battle_id)
    if definition is None:
        return None
    if not tick or ctx.world.paused_at() is not None:  # 暫停中只讀：集結截止、回合逾時、補位、結算都等繼續之後
        return None if raw.phase == "ended" else (raw, definition)
    was_ended = raw.phase == "ended"
    battle, _ = run_battle_tick(ctx, definition)
    battle = battle or raw
    if battle.phase == "ended":
        if not was_ended:
            ctx._apply_battle_outcome(battle)  # 經 Game：tests/server/test_server.py 換掉它（套用結果時壞一次，下一次輪詢重新套）
        return None
    return battle, definition


def battle_for_me(ctx, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
    """這個人的選單、場景、放手一搏、決戰的動作看的那一場：同 battle_status（tick 照樣把戰鬥追到現在），只是序章裡一律當作
    沒有（FB-113）——草廬與序章開場都在潁川汝南，以前長社火攻集結時新人第一個畫面就是兩顆投效，按了之後序章被戰場蓋掉、
    又走不開。不給投效與加入、不畫戰場；修好之前就上了名單的人也一樣（只是被代選固守，收場不領軍餉，見 view.showdown_pay）。"""
    status = ctx._battle_status(tick=tick)  # 經 Game：tests/core/test_engine.py、tests/arts/test_hints.py 換掉它（數一次請求推幾次）
    return None if prologue_rules.active(ctx.state, ctx.content) else status


def shelve_unfinished_battle(ctx, text: str = "") -> None:
    """季終時還沒打完的決戰收起來（自然收季見 battle_status、管理者收季見 close_season；呼叫端先確認
    有一場還沒收場的）。不算結果：不動大勢、不寫旗標、不寫江湖史、不加戰報（FB-015）；但每個參戰者要有交代（FB-035）。

    做法是先在 battles 表把它標成 ended＋unfinished、end_time 記收季那一刻，再從共用狀態拿掉：
    ended_battles 讀得到它，參戰者各自同步時用 _deliver_battle_results 補一則江湖紀錄（下線的、跨季才回來的也補得到）。
    兩步不能併成一次 mutate：決戰拿掉之後，存檔就不再寫那一列了，標記會丟掉。
    標成 ended 不會被當成「剛打完」套結果：showdown_status 對本來就 ended 的不再套（was_ended）、
    apply_battle_outcome 認得 unfinished 直接不動，而且拿掉之後 get_battle 本來就看不到它。
    最後也補給自己，跟 apply_battle_outcome 一樣：收場那一下的那個人當場就看得到。"""
    end_time = ctx.state.world.time

    def _mark(b: battle_instance.BattleInstance) -> None:
        b.phase = "ended"
        b.unfinished = True
        b.unfinished_text = text  # 空的照季終收兵那一句（管理者取消決戰另外寫，T10 審查 I3）
        b.outcome_title = battle_instance.UNFINISHED_TITLE
        b.end_time = end_time

    ctx.world.mutate_battle(_mark)
    ctx.world.clear_battle()
    ctx._deliver_battle_results()


def close_season(ctx, reread: bool) -> None:
    """收季的收兵（核心經 on_season_close 接縫掛鉤叫；原本寫在 Game.admin_end_season、admin_next_season 裡的兩段，全部拆包第 8 批搬來，
    先後照舊）：沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了，跟自然收季一樣，見 battle_status，FB-015），參戰者各補一則
    「不算勝負」的江湖紀錄（FB-035）；攻城戰同上（領地爭奪第二批）。
    - 管理者立刻收季（reread=False）：呼叫端剛讀回收季那一份季（收場時間記收季那一刻的季時間），在 mutate_season 外面（mutate 不能巢狀）。
    - 開下一季（reread=True；呼叫端只在休季時叫）：季自然結束之後沒有人同步過、沒人走到 battle_status 收掉它，換季會直接清掉——先收起來，
      參戰者才補得到交代。收場時間記收掉的那一季的時間，所以收決戰之前、收攻城之前各讀回一次手上那一份季。"""
    battle = ctx.world.get_battle()
    if battle is not None and battle.phase != "ended":
        if reread:
            ctx.state.world = ctx.world.get_season()
        shelve_unfinished_battle(ctx)
    if reread:
        ctx.state.world = ctx.world.get_season()
    for siege_battle in sieges.sieges(ctx):
        sieges.shelve_siege(ctx, siege_battle)


def advance_battle_round(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[str]:
    """核心推進邏輯（在呼叫端的 mutate_battle callback 裡原地修改 battle）：
    集結逾時自動分配、機器人補位、場上沒人能打又逾時就用保底結果收場、回合逾時代選
    保守行動、全員到齊就結算並請 LLM 潤色。回傳這次呼叫如果真的結算了一回合（或收場）
    的敘事訊息，沒有結算就是空清單。這是
    run_battle_tick()（被動追趕，options()/scene_text() 用）跟 muster.battle_choose_in()
    的 act 分支（玩家自己送出行動，可能剛好湊滿全員）共用的同一份邏輯，確保兩條
    路徑的推進規則完全一致——只是呼叫的時間點跟是否先 submit_action 不同。"""
    now = ctx.now
    tuning = ctx.content.config.battle  # 三招的數字（排程的 Game 與玩家的 Game 讀同一份內容，所以結算一致）
    if battle.phase == "muster" and now >= battle.muster_deadline_real:
        battle_instance.close_muster(battle, definition, ctx.rng, now, tuning=tuning)
        if siege.void_absent(ctx.content, battle):  # 攻城戰（領地爭奪第二批）：攻方一個人都沒到，這一場作罷
            battle.end_time = ctx.state.world.time
            return [battle.unfinished_text]
        siege.lone_army(ctx.content, battle, definition)  # 三方混戰只有一軍到場（裁決 23）：轉回單方攻中立地
        siege.size_melee_guard(ctx.content, battle)  # 三方混戰（裁決 22）：守將的池子照兩軍到場的人數定
    if battle.phase != "active":
        return []
    for p in list(battle.participants.values()):
        if p.is_bot and not p.eliminated and not p.away and p.name not in battle.round.pending_actions:
            tag = battle_instance.bot_choose_action(battle, definition, p.name, ctx.rng, tuning=tuning)
            if tag:
                battle_instance.submit_action(battle, p.name, tag)
    ended = battle_instance.end_without_fighters(battle, definition, now, tuning=tuning)  # 兩軍沒人能打、回合逾時：用保底結果收場
    if ended:
        battle.end_time = ctx.state.world.time  # 收場時的賽季時間：參戰者的戰報用（FB-027）
        return ended
    timed_out = now - battle.round.opened_real >= definition.round_seconds
    if timed_out and not battle_instance.round_is_complete(battle):
        battle_instance.fill_timed_out_actions(battle, definition, tuning=tuning)
    if not battle_instance.round_is_complete(battle, timed_out=timed_out):  # 只剩掛機的人：逾時代選完就結算（FB-173）
        return []
    battle_instance.fill_idle_actions(battle, definition, tuning=tuning)  # 不等掛機的人：其他人送齊了，替他們代選
    msgs = ctx._round_mvp(battle, lambda: battle_instance.resolve_round(  # 回合 MVP 包在外面（looks；純展示，數字一個不動）
        battle, definition, ctx.rng, now=now, tuning=tuning, tactic=ctx.content.config.tactics))
    if battle.phase == "ended":
        battle.end_time = ctx.state.world.time
    # 每回合最前面那一行出招比例只留在回合紀錄（戰報）裡，場景上的比例只由「對面上一回合」那一段寫一次（審查 I1）。
    # 場景的記錄就是系統判定的那幾句（第一句是 resolve_round 寫的「誰佔了上風、為什麼」），不叫模型潤色：結算在行動鎖裡，
    # 以前每回合在鎖內等模型最多 in_lock_model_timeout 秒，全服所有人的動作都跟著等（試玩回饋 2026-10-08）
    shown = battle_instance.without_mix_line(battle, msgs)
    narration = "\n".join(shown)
    if narration:
        battle.narrative_log.append(narration)
    return shown or ["這一回合結算了。"]


def run_battle_tick(ctx, definition: BattleDef) -> tuple[battle_instance.BattleInstance | None, list[str]]:
    """在 mutate_battle 裡跑一次 advance_battle_round，給被動追趕（options()/scene_text()）用。"""
    captured: dict[str, list[str]] = {"msgs": []}

    def _apply(b: battle_instance.BattleInstance) -> None:
        captured["msgs"] = advance_battle_round(ctx, b, definition)

    battle = ctx.world.mutate_battle(_apply)
    return battle, captured["msgs"]


def apply_battle_outcome(ctx, battle: battle_instance.BattleInstance) -> None:
    """戰鬥剛結束這一刻，把結果套用到共用賽季（大勢推動／世界旗標），順便留一筆
    江湖史——這裡故意不在 mutate_battle 的 callback 裡面做（寫入交易雖然可以巢狀，但 mutate 的
    callback 裡再呼叫 mutate_season，內層寫的會被外層的整份存檔蓋掉，database.rewriting 會直接丟
    RuntimeError），所以是呼叫端在拿到 mutate_battle 的結果、callback 已經結束之後才呼叫，
    順序上一定晚於戰鬥本身的結算。

    結果也要套到自己手上的 ctx.state.world：結算可能發生在 choose()／travel() 的 options() tick 裡，
    而它們收尾的 _save_season 會把這份記憶體裡的賽季整份寫回去——不跟著改，剛寫進資料庫的大勢與旗標
    就被比較舊的那份蓋掉了（江湖史是另一張表，不受影響，所以只有它倖存）。江湖史那一則只寫資料庫，
    不寫記憶體，免得存兩次。

    最後把結果補送給自己（收場那一下的那個人當場就看得到）；別的參戰者各自同步時補（FB-027）。

    季終收兵的決戰（unfinished，見 shelve_unfinished_battle）沒有結果可套，不會走到這裡；萬一走到，直接不動。

    時刻表決戰（第一季的三場大戲，計畫 T8）不套保底的 BattleOutcome，改走 settle_showdown。不論哪一種，收場之後
    都看有沒有時間到了、在等這一場打完的決戰，有就立刻開（見 open_waiting_showdown）。"""
    if battle.siege is not None:  # 攻城戰（領地爭奪第二批）：易手、作罷、時程表另外收（sieges.settle_siege）
        sieges.settle_siege(ctx, battle)
        return
    if battle.unfinished:
        return
    if any(c.fallen_round is not None and not c.settled for c in battle.commanders):  # 龍頭上陣：敗走的人扣聲威（只扣一次）
        generals.after_battle(ctx.world, ctx.content, battle)
        ctx.state.world = ctx.world.get_season()  # 這一刻手上那一份跟資料庫一致（同 settle_showdown），讀回來免得被 _save_season 蓋掉
    if escorts.due(battle):  # 歷史武將同行：隨主人上陣的同伴收場那一刻全服放回江湖（只放一次）
        escorts.after_battle(ctx.world, ctx.content, battle)
    definition = ctx.content.battles.get(battle.battle_id)
    line = highlight_line(battle, definition)
    if line:  # 這一場最有戲的放手一搏，全服的天下大事傳聞（試玩回饋 2026-10-08）；收場只走這裡一次
        ctx.world.mutate_season(lambda season: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
    line = merit_line(ctx, battle, definition)
    if line:  # 兩軍各一位首功（Joy 2026-10-10 個人戰功），天下大事傳聞具名
        ctx.world.mutate_season(lambda season: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
    if definition is not None and definition.timetable_event is not None and season_one(ctx.content, ctx.state.world):
        settle_showdown(ctx, battle, definition)
    else:
        if battle.outcome_world_flags or battle.outcome_trend_delta or battle.outcome_title:

            def _apply(season: WorldState) -> None:
                apply_outcome_trends_and_flags(ctx, season, battle)
                if battle.outcome_title:
                    season.chronicle.append(Rumor(time=season.time, text=f"【{battle.outcome_title}】{battle.outcome_text}"))

            ctx.world.mutate_season(_apply)
            apply_outcome_trends_and_flags(ctx, ctx.state.world, battle)
        ctx._deliver_battle_results()
    open_waiting_showdown(ctx)


def merit_line(ctx, battle: battle_instance.BattleInstance, definition: BattleDef | None) -> str:
    """收場時的論功那一則：兩軍各自戰功最高的人（battle_instance.top_merit；臨時投效的人算在投效的那一軍）；
    都沒人出過手就不寫。單方攻中立地時守將那一格寫守軍（battle_instance.side_names，FB-540）。"""
    if definition is None:
        return ""
    tuning = ctx.content.config.battle
    heads = [
        (side, top) for fid, side in battle_instance.side_names(battle, definition).items()
        if (top := battle_instance.top_merit(battle, tuning, fid)) is not None
    ]
    if not heads:
        return ""
    return f"{definition.name}論功：" + "，".join(
        f"{side}首功{p.name}" + (f"（{'・'.join(p.renown)}）" if p.renown else "") for side, p in heads) + "。"  # 名聲 4.5


def highlight_line(battle: battle_instance.BattleInstance, definition: BattleDef | None) -> str:
    """收場時那一則傳聞：這一場最有戲的放手一搏（battle.highlight）。天下大事傳聞照慣例具名（假人不寫放手一搏，不會出現）。"""
    h = battle.highlight
    if h is None:
        return ""
    where = definition.name if definition is not None else battle.battle_id
    head = f"{where}上，{h.name}放手一搏：「{h.text}」"
    if h.won:
        return f"{head}——成算不到{h.rate // 10 + 1}成，竟然成了。{h.story}".rstrip()
    return f"{head}——沒成，倒成了兩軍口中的笑談。{h.story}".rstrip()


def settle_showdown(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> None:
    """時刻表決戰收場（計畫 T8）：照 battle_instance.decide_result 判誰贏、大勝或險勝——這一刻才讀
    WorldState.locks（鎖定只在這裡看，起點、推力、選項都不看，戰鬥系統 4.3）——再交給 timetable.resolve 結算那一格
    （它自己加宛城的版本前綴，公告、江湖史、戰況、人物都照時刻表）。保底的 BattleOutcome 不套、不寫江湖史。

    戰鬥那一列的結果改成時刻表那一格（標題「官軍大勝」、文字是公告、大勢變化是那一格的戰況），參戰者的戰報照
    W13／FB-027 補送時就寫這個；公告進每個人的江湖紀錄走 _deliver_big_events（FB-038）。

    resolve 改的是資料庫裡的那一份賽季（mutate_season），手上的 ctx.state.world 跟著讀回來：結算發生在 options() 的
    推進裡，接下來 choose() 收尾的 _save_season 會把手上那一份整份寫回去，不讀回來就把結果蓋掉了。這一刻手上那一份
    跟資料庫一致（每個動作開頭的 sync 剛讀過、推進戰鬥之前還沒改它），讀回來不會丟東西。"""
    event = timetable.find(ctx.content, definition.timetable_event) if definition.timetable_event else None  # 天命之爭也找得到（玉璽二）
    result: dict[str, object] = {}
    unsettled = seal.is_mandate_battle(ctx.content, definition) and seal.deserted(battle, definition)  # 天命未定（玉璽二）

    def _resolve(season: WorldState) -> None:
        lock = season.locks.get(definition.timetable_event)
        winner, margin = battle_instance.decide_result(
            battle, definition, lock.side if lock is not None else None, definition.defender or definition.factions[0].id,
        )
        result["title"] = f"{timetable.SIDE_NAMES.get(winner, winner)}{margin}"
        result["side"], result["margin"] = winner, margin
        result["reason"] = battle_instance.overruled_reason(
            battle, definition, lock.side if lock is not None else None, definition.defender or definition.factions[0].id,
        )
        if event is None:
            return
        if unsettled:  # 天命之爭保底收場：天命未定（8.3；要 PM 定的第 4 條），時間軸記成跳過，不公告哪一軍勝、沒有勝方加給
            season.timeline[event.id] = TimelineResult(key=timetable.SKIPPED, time=season.time)
            result.update(title=seal.MANDATE_UNSETTLED_TITLE, side="", margin="", reason="", text="", trends={})
            return
        key = showdown_key(definition, winner, margin)  # 帶上實際打的那一版（審查 M-1）
        timetable.resolve(_season_vehicle(ctx.content, season), ctx.content, event, ctx.rng, key=key)
        done = season.timeline.get(event.id)
        outcome = event.outcomes.get(done.key) if done is not None else None
        result["text"] = done.text if done is not None else ""
        result["trends"] = dict(outcome.trends) if outcome is not None else {}

    ctx.world.mutate_season(_resolve)

    def _relabel(b: battle_instance.BattleInstance) -> None:
        if b.record_id != battle.record_id:
            return
        b.outcome_title = str(result["title"])
        b.outcome_side, b.outcome_margin = str(result.get("side") or ""), str(result.get("margin") or "")
        if result.get("reason"):  # 伏筆鎖定的一方贏了、戰場上卻是另一方佔上風：敗因不能寫成戰場那一邊贏
            b.outcome_reason = str(result["reason"])
        b.outcome_text = str(result.get("text") or b.outcome_text or "")
        b.outcome_trend_delta = dict(result.get("trends") or {})  # 只給戰報顯示：已經由 resolve 套過了
        b.outcome_world_flags = []

    ctx.world.mutate_battle(_relabel)
    ctx.publish("battle_end", battle, definition, result)  # 事件 battle_end（第 26 批）：玉璽碎片：先挑挑戰者、再挑現世的得主（3.3、4.5）；只寫登記、天下大事、江湖史，接著讀回的賽季看得到
    ctx.state.world = ctx.world.get_season()
    ctx._deliver_big_events()
    ctx._deliver_battle_results()
    ctx._deliver_seal_results()


def open_waiting_showdown(ctx) -> None:
    """時間到了、在等前一場打完的時刻表決戰，前一場一收場就開（Review Focus 2：開不成時留著記號，等它收場立刻開）。
    開了的話手上的那一份賽季跟著讀回來（季上記了「開過了」，之後存檔不能蓋掉它）。集結的消息不另外寫紀錄：
    場景上每個人都看得到集結。"""
    if not ctx.state.world.showdowns_waiting:
        return
    if open_waiting(ctx.world, ctx.content, ctx.now):
        ctx.state.world = ctx.world.get_season()


def apply_outcome_trends_and_flags(ctx, season: WorldState, battle: battle_instance.BattleInstance) -> None:
    """決戰結果的大勢變化與世界旗標，套到 season 上（資料庫裡的那份與記憶體裡的那份共用這一段）。
    內容寫的是戰線：照 rules.resolve_trends 換鍵（開關關著時是黃巾聲勢）；存檔沒有那條線時從起始值算起。"""
    for trend_id, delta in resolve_trends(ctx.content, season, battle.outcome_trend_delta).items():
        season.trends[trend_id] = max(0, min(100, world_trend_value(season, ctx.content, trend_id) + delta))
    recompute_trends(season, ctx.content)  # 開關開著時推了戰線，黃巾聲勢跟著重算（這裡不經 change_trend）
    territory.update(season, ctx.content)  # 決戰結果直接寫進季、不經 change_trend：地盤在這裡重算
    for flag in battle.outcome_world_flags:
        if flag not in season.flags:
            season.flags.add(flag)
            season.flag_times[flag] = season.time


def watching_battle(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
    """這個人此刻打不了這場仗、只能在一旁看（options() 照常給平常的選項，場景上仍看得到戰場）：
    - 參戰者離開了決戰的大區（人在區外，或這一趟路正要走出大區；區內站與站之間走動不算）：這回合不出手，
      照常遊玩，回來才回到戰場；
    - 還沒參戰的人不在決戰的大區、或在路上（地圖擴充設計第六節：人要在現場才能加入）。
    全服決戰不能把打不了仗的人鎖住。"""
    me = battle.participants.get(ctx.state.player.name)
    if me is not None:
        return me.away
    if battle.siege is not None and not siege.slots(battle.siege, ctx._conquest_side()):
        return True  # 攻城戰（領地爭奪第二批）：這一仗沒有自己站得進去的格（另一軍攻中立地，裁決 8），照常遊玩
    return not muster.at_battle(ctx, definition)


def fighting(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
    """開打了、自己在場上打得了這一場：戰鬥選單取代整份選單（options），戰場取代整個場景（scene_text）。兩邊都問這一個，
    選單照常給的人場景上就看得到自己眼前的事。不是的人：集結中、只能觀戰（watching_battle）、開打了還沒投效的散人與豪強
    （FB-109：以前選單照給、場景卻只剩戰場，事件內文、有所感、人物的回話、投靠的確認都看不到）。"""
    if battle.phase == "muster" or watching_battle(ctx, battle, definition):
        return False
    if ctx.state.player.name not in battle.participants and allied.needs_ally(ctx.state, ctx.content):
        return False  # 拜入曹氏莊院還沒挑一邊（FB-273）：先挑，選單只剩那兩顆
    return not (muster.free_agent(ctx, definition) and ctx.state.player.name not in battle.participants)
