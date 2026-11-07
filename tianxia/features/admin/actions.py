"""季與時刻表的管理者工具（功能包 tianxia/features/admin/；原本 Game 上的 17 個方法，第二輪第 90 批搬進來）。本體照抄，self 換成 ctx（第一階 ctx 就是 Game，
開發規範手冊 3.3）；`g.admin_open_season(now=...)` 這些照舊叫得到（game_api.py 的 TABLE），參數名不動。

包裡互叫不經 ctx（_settle_season_start、_timetable_refusal、_timetable_event、_showdown_mark 直接叫這個檔的）；管理者外殼 is_admin、_admin_refusal 留在 Game
（手冊第十五節波次 B、C 第 14 條），經 ctx。軍情的玩家選單 admin_player_choices 在 features/military/admin_actions.py。
"""
from __future__ import annotations

from tianxia import calendar, divine, timetable
from tianxia.core import features as features_core  # 收季的收兵（接縫掛鉤）
from tianxia.core import seal_base  # 定結果替天命之爭定天命（核心本體）
from tianxia.core.services import PAUSED_REFUSAL
from tianxia.models import Threshold, TimetableEvent, WorldEvent
from tianxia.rules import change_trend, pushable, season_one, season_one_off, trend_name, trend_shown, trend_value
from tianxia.world import _season_vehicle, check_thresholds, end_season, fire_by_id, resume_season_clock, settle_season_start

# 賽季時鐘暫停（線上架構設計第四節、8.3）：伺服器擋動作回的 PAUSED_TEXT 與暫停中的管理者動作回的 PAUSED_REFUSAL 都在核心（core/services.py）。待 S1／joy 潤
PAUSE_LINE = (  # 待 S1／joy 潤
    "賽季時鐘停了：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；"
    "排好的決戰繼續之後照原本的時間開。做完記得按「繼續」。"
)
RESUME_LINE = (  # 待 S1／joy 潤；{skip} 是實際扣了多少（world.resume_skip_text：停不到一個季曆鐘頭就說不另外扣）
    "賽季時鐘接著走了（停了 {minutes} 分鐘）：{skip}；"
    "排好的決戰照原本的時間開，時間在暫停裡過了的現在就開始集結。"
)


def admin_open_season(ctx, now: float) -> list[str]:
    """管理者開季：籌備中 → 進行中。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能開季。）"])
    if not ctx.world.open_season(ctx.content, now):
        return ctx._log(["（現在不是籌備期，無法開季。）"])
    msgs = [f"══ {ctx.content.scenario.name}・開季 ══"]
    msgs += timetable.quiet_notes(ctx.world.get_season(), ctx.content, now)  # 挪不開半夜、照原時間的決戰（企劃者 2026-10-15）
    ctx._write("開季", msgs, tag="管理者")
    return ctx._log(msgs + _settle_season_start(ctx))

def _settle_season_start(ctx) -> list[str]:
    """開季那一刻（世界秒 0）結算第 1 週週一 00:00 的大事（FB-040，見 world.settle_season_start），開季的人那一次
    請求就跑；之後每曆時的交界才跑每曆時的事。放在 open_season／next_season 之後、不在任何 mutate 裡（mutate 不能巢狀）。
    開關關著或舊季什麼都不會發生。公告進自己的江湖紀錄走 _deliver_big_events，跟別人一樣。"""
    msgs: list[str] = []
    ctx.world.mutate_season(lambda season: msgs.extend(settle_season_start(season, ctx.content, ctx.rng)))
    ctx.state.world = ctx.world.get_season()
    ctx._deliver_big_events()
    return msgs


def admin_end_season(ctx, now: float) -> list[str]:
    """管理者立刻收季：進行中 → 休季（之後再由 admin_next_season 開下一季）。照自然收季的做法算結局、
    寫江湖史、附武學榜（world.end_season），只是不必等季末或快轉十幾天——試玩伺服器要收掉這一季用的。
    不推進時間：季的時間停在收季那一刻。now 跟 admin_open_season／admin_next_season 同一種簽名，收季本身用不到。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能收季。）"])
    if ctx.world.season_phase() != "running":
        return ctx._log(["（賽季不在進行中，沒有可以收的。）"])
    if ctx.world.paused_at() is not None:
        return ctx._log([PAUSED_REFUSAL])
    msgs: list[str] = []
    ctx.world.mutate_season(
        lambda s: msgs.extend(end_season(_season_vehicle(ctx.content, s), ctx.content, ctx.world))
    )
    ctx.state.world = ctx.world.get_season()  # 讀回完整的一份（mutate_season 回傳的不含傳聞與江湖史）
    # 收季的收兵（接縫掛鉤，全部拆包第 8 批；決戰包：沒打完的決戰與每一場攻城直接收掉、不套用結果——這一季勝負已經定了，跟自然收季
    # 一樣，FB-015——參戰者各補一則「不算勝負」的江湖紀錄，FB-035）。放在 mutate_season 外面：mutate 不能巢狀，
    # 內層寫的會被外層整份存檔蓋掉；放在讀回賽季之後：收場時間記的是收季那一刻的季時間
    features_core.on_season_close(ctx, reread=False)
    # 收季前結算的、從沒開成的決戰（world.settle_waiting_showdowns）：公告跟別的大事一樣走 _deliver_big_events，
    # 收季那一則不再重複一次
    ctx._deliver_big_events()
    ctx._write("收季", ctx._without_timetable(msgs), tag="管理者")  # 跟開季一樣，管理者自己的江湖紀錄留一則
    return ctx._log(msgs)


def admin_next_season(ctx, now: float) -> list[str]:
    """管理者開下一季：只在休季時有效；管理者自己的角色跟著換季（其他玩家下次同步時換）。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能開啟下一季。）"])
    if ctx.world.season_phase() == "resting":
        # 收季的收兵（接縫掛鉤，全部拆包第 8 批；決戰包）：季自然結束之後沒有人同步過、沒人走到 _battle_status 收掉的決戰與攻城，
        # 換季會直接清掉——先收起來，參戰者才補得到「不算勝負」那一則（FB-035）。收場時間記收掉的那一季的時間（reread：收兵之前讀回賽季）
        features_core.on_season_close(ctx, reread=True)
    if not ctx.world.next_season(ctx.content, now):
        return ctx._log(["（這一季還沒結束，無法開啟下一季。）"])
    ctx._reconcile_season()
    quiet = timetable.quiet_notes(ctx.world.get_season(), ctx.content, now)  # 同開季
    lineup = divine.lineup_note(ctx.content, ctx.world.get_season())  # 這一季現世了哪幾件神器（只回給管理者，FB-400）
    if lineup is not None:
        quiet = [*quiet, lineup]
    if divine.exhausted_now(ctx.world.divine_state(), ctx.world.get_season_number()):  # 新神器用完了（正式季整合 5.6）：提醒管理者
        quiet = [*quiet, divine.EXHAUSTED]
    return ctx._log([f"══ 第 {ctx.world.get_season_number()} 季開始 ══", *quiet] + _settle_season_start(ctx))


def admin_pause_clock(ctx, now: float) -> list[str]:
    """管理者暫停賽季時鐘（線上架構設計第四節、8.3：公告停機時賽季時鐘暫停，季末跟著往後延）：只在進行中有效。
    暫停中季的時間不走、決戰不推、玩家不能行動、假人不出手、不能快轉，別的管理者動作也先擋著；畫面照常可看。
    停機前按，開回來按「繼續」（主機端也可以用 scripts/season_clock.py）。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能暫停賽季。）"])  # 待 S1／joy 潤
    if ctx.world.season_phase() != "running":
        return ctx._log(["（賽季不在進行中，沒有時鐘可以停。）"])  # 待 S1／joy 潤
    if not ctx.world.pause_clock(now):
        return ctx._log(["（賽季時鐘已經停著了。）"])  # 待 S1／joy 潤
    ctx._write("暫停賽季", [PAUSE_LINE], tag="管理者")
    return ctx._log([PAUSE_LINE])


def admin_resume_clock(ctx, now: float) -> list[str]:
    """管理者讓賽季時鐘繼續走：停的這一段不算進賽季、季末往後延，進行中的決戰剩下的時間不變；排好、還沒開的決戰照原本的
    現實時間開（企劃者 2026-10-06 定 B3），原本的時間落在暫停裡的這一刻就開集結（B11；另一場還在打就排隊）。
    繼續、補算、開集結三步都在 world.resume_season_clock（順序只寫在那一個地方，主機端腳本與模擬也走它）；
    這裡把回傳的訊息（繼續的那一行、補算的、集結號角）寫進管理者自己的江湖紀錄。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能讓賽季繼續。）"])  # 待 S1／joy 潤
    msgs = resume_season_clock(ctx.world, ctx.content, now, ctx.rng, RESUME_LINE)
    if msgs is None:
        return ctx._log(["（賽季時鐘沒有暫停。）"])  # 待 S1／joy 潤
    ctx.state.world = ctx.world.get_season()
    ctx._deliver_big_events()  # 補算結算的大事，管理者自己的江湖紀錄馬上補上（別人下次同步補）
    ctx._write("繼續賽季", ctx._without_timetable(msgs), tag="管理者")
    return ctx._log(msgs)


def admin_fires(ctx) -> list[Threshold | WorldEvent]:
    """管理者「觸發大事」的選單：大勢門檻與世界事件，第一季不觸發的 beta 門檻與世界事件不列（計畫 T8；玉璽碎片設計 11.2）。"""
    w = ctx.state.world
    off = season_one_off(ctx.content, w, "thresholds") | season_one_off(ctx.content, w, "world_events")
    return [x for x in [*ctx.content.scenario.thresholds, *ctx.content.scenario.world_events] if x.id not in off]


def admin_fire(ctx, fire_id: str) -> list[str]:
    """管理者直接觸發一則大勢門檻或世界事件：效果跟自然發生一樣，一季只會發生一次。"""
    refusal = ctx._admin_refusal("觸發大事")
    if refusal:
        return ctx._log(refusal)
    if fire_id in ctx.state.world.fired_thresholds:
        return ctx._log(["（這件大事已經發生過了。）"])
    msgs = fire_by_id(ctx.state, ctx.content, fire_id, ctx.world, ctx._flavor_sink(), now=ctx.now)
    if msgs is None:
        return ctx._log(["（沒有這件大事。）"])
    ctx._write("觸發大事", msgs, tag="管理者")
    ctx._save_season()
    return ctx._log(msgs)


def admin_push_trend(ctx, trend_id: str, delta: int) -> list[str]:
    """管理者直接推一條大勢線（正數推高、負數壓低）；推過門檻就照常觸發大事。"""
    refusal = ctx._admin_refusal("推動大勢")
    if refusal:
        return ctx._log(refusal)
    if not trend_shown(ctx.content, ctx.state.world, trend_id):
        return ctx._log(["（沒有這條大勢線。）"])
    if not pushable(ctx.content, ctx.state.world, trend_id):  # 開關開著時的黃巾聲勢由三條戰線合成，change_trend 推它會丟 ValueError
        return ctx._log([f"（{trend_name(ctx.content, trend_id)}由三條戰線合成，不能直接推；請推其中一條戰線。）"])
    msgs = change_trend(ctx.state, ctx.content, trend_id, delta)
    msgs += check_thresholds(ctx.state, ctx.content, ctx.world, ctx._flavor_sink(), now=ctx.now)
    ctx._write("推動大勢", msgs or ["大勢紋絲不動。"], tag="管理者")
    ctx._save_season()
    return ctx._log(msgs)


# ── 管理者：時刻表與救場（計畫 T10）──────────────────────

def _timetable_refusal(ctx, action: str) -> list[str] | None:
    """時刻表類的管理者動作：先照 _admin_refusal，再要這一季有時刻表（第一季；beta 那一季沒有）。"""
    refusal = ctx._admin_refusal(action)
    if refusal:
        return refusal
    if not season_one(ctx.content, ctx.state.world):
        return ["（這一季沒有時刻表。）"]
    return None


def _timetable_event(ctx, event_id: str) -> TimetableEvent | None:
    """管理者定結果、清鎖定、開戰、排時間與伏筆鏈的查表入口：照這一季的時刻表（一般季送天命之爭的 id 也是「沒有這件大事」，玉璽二）。"""
    return next((e for e in timetable.events(ctx.state.world, ctx.content) if e.id == event_id), None)


def admin_schedule(ctx, item: str, at_real: float, now: float) -> list[str]:
    """把三場決戰或季末排在現實時間 at_real：換成世界秒（world.time ＋ (at_real − now) × time_scale）寫進 schedule。
    已經結算或開過集結的不能再排；不能排在過去；三場決戰與季末要照時刻表的順序（嚴格在前一項之後、後一項之前）。"""
    refusal = _timetable_refusal(ctx, "排時間")
    if refusal:
        return ctx._log(refusal)
    s, c = ctx.state, ctx.content
    w = s.world
    items = timetable.schedulable(c, w)
    event = next((e for e in items if e.id == item), None)
    if event is None:
        return ctx._log(["（只有三場決戰與季末能排時間。）"])
    if event.id in w.timeline or event.id in w.showdowns_opened:
        return ctx._log([f"（{event.title}已經結算或開打了，不能再排。）"])
    at = w.time + (at_real - now) * c.config.time_scale
    if at <= w.time + calendar.EPS_SECONDS:
        return ctx._log(["（不能排在已經過去的時間。）"])
    wanted, avoided = at, None
    if event.kind == "showdown":
        at, avoided = _showdown_mark(ctx, at)
    i = items.index(event)
    prev = items[i - 1] if i > 0 else None
    nxt = items[i + 1] if i + 1 < len(items) else None
    order = []
    if prev is not None and at <= timetable.when(s, c, prev):
        order.append(f"要排在{prev.title}之後")
    if nxt is not None and at >= timetable.when(s, c, nxt):
        order.append(f"要排在{nxt.title}之前")
    if order:
        return ctx._log(["（三場決戰與季末要照順序：" + "、".join(order) + "。）"])
    source = _timetable_event(ctx, event.version_from) if event.version_from else None
    if source is not None and source.id not in w.timeline and wanted <= timetable.when(s, c, source):  # 照管理者要的時間判
        return ctx._log([f"（{event.title}要看{source.title}的結果決定版本：要排在它之後。）"])  # 宛城（PM 2026-10-05）
    w.schedule[timetable.schedule_key(event)] = at
    if event.id in w.showdowns_waiting:  # 時間到了在排隊（前一場還在打）：改到之後就拿出隊伍，到了新的時間才開（T10 審查 I2）
        w.showdowns_waiting.remove(event.id)
    ctx._save_season()
    moved = "，對齊整點" if abs(at - wanted) > calendar.EPS_SECONDS else ""
    moved += f"、避開同一刻的{avoided}" if avoided else ""
    if at >= calendar.calendar_end(c, w) and calendar.season_one_on(w, c):
        # FB-439：排到季曆最後一刻之後，季曆時刻停在最後一週週日 23:59，照舊寫會像沒排過去：寫之後多久與現實的日期時刻
        real = at_real + (at - wanted) / c.config.time_scale
        note = moved.lstrip("，、")
        msg = f"已把{event.title}排在{calendar.schedule_text(at, real, c, w)}{f'（{note}）' if note else ''}。"
    else:
        msg = f"已把{event.title}排在{calendar.stamp_text(at, c, w)}（季曆{moved}）。"
    ctx._write("排時間", [msg], tag="管理者")
    return ctx._log([msg])


def _showdown_mark(ctx, at: float) -> tuple[float, str | None]:
    """排定的決戰時間對齊到下一個曆時交界（季的事只在交界把時間到了的決戰記下來，T10 審查 I1）；那一刻剛好有還沒結算的
    一般大事時再往後挪一個曆時——不然同一刻那件大事先結算，排在它前面、還沒開成的決戰會照起點判掉（settle_waiting_showdowns）。"""
    s, c = ctx.state, ctx.content
    mark = calendar.hour_ceil(at, c, s.world)  # 季曆的整點（FB-331：21 天季開季不在整點時，世界秒的整點對不到季曆）
    return timetable.clear_of_events(s, c, mark)


def admin_jump_next(ctx, now: float) -> list[str]:
    """跳到下一件大事：推進到最早那一件還沒結算的大事的時間（決戰是排定的集結開始；開過集結的不算），取整到下一個
    曆時交界（季的事只在交界跑），照常結算、開集結（走 advance）。同一刻的幾件一起結算。決戰還在集結或開打時拒絕。"""
    refusal = _timetable_refusal(ctx, "跳到下一件大事")
    if refusal:
        return ctx._log(refusal)
    ctx.now = now
    battle = ctx.world.get_battle()
    if battle is not None and battle.phase != "ended":
        return ctx._log(["（決戰還沒收場，先等它打完或取消。）"])
    s, c = ctx.state, ctx.content
    w = s.world
    pending = [e for e in timetable._pending(s, c) if e.id not in w.showdowns_opened]  # noqa: SLF001  同一個套件的排序
    if not pending:
        return ctx._log(["（時刻表上沒有下一件大事了。）"])
    cal_hour = calendar.cal_hour_seconds(c, w)
    target = max(timetable.when(s, c, pending[0]), w.time)
    mark = calendar.hour_ceil(target, c, w)  # 季曆的整點（FB-331）
    if mark <= w.time + calendar.EPS_SECONDS:
        mark += cal_hour
    return [f"跳到{pending[0].title}。"] + ctx.advance(mark - w.time)


def admin_set_trend(ctx, trend_id: str, value: int) -> list[str]:
    """定戰況：把一條大勢線直接推到 value（夾在 0～100）；檢查同「推動大勢」（衍生線拒絕），推過門檻照常觸發。"""
    refusal = ctx._admin_refusal("定戰況")
    if refusal:
        return ctx._log(refusal)
    if not trend_shown(ctx.content, ctx.state.world, trend_id):
        return ctx._log(["（沒有這條大勢線。）"])
    if not pushable(ctx.content, ctx.state.world, trend_id):
        return ctx._log([f"（{trend_name(ctx.content, trend_id)}由三條戰線合成，不能直接推；請推其中一條戰線。）"])
    delta = max(0, min(100, value)) - trend_value(ctx.state, ctx.content, trend_id)
    msgs = change_trend(ctx.state, ctx.content, trend_id, delta) if delta else []
    msgs += check_thresholds(ctx.state, ctx.content, ctx.world, ctx._flavor_sink(), now=ctx.now)
    ctx._write("定戰況", msgs or ["大勢紋絲不動。"], tag="管理者")
    ctx._save_season()
    return ctx._log(msgs)


def admin_resolve_event(ctx, event_id: str, key: str) -> list[str]:
    """定結果：管理者直接定一件大事的結果（不含版本的鍵，例如「成」「guan:險勝」），照時刻表結算（公告、江湖史、
    效果都照內容），人人的江湖紀錄照 FB-038 補上。季末用「立刻收季」；決戰正在打的先取消。"""
    refusal = _timetable_refusal(ctx, "定結果")
    if refusal:
        return ctx._log(refusal)
    s, c = ctx.state, ctx.content
    event = _timetable_event(ctx, event_id)
    if event is None:
        return ctx._log(["（沒有這件大事。）"])
    if event.kind == "finale":
        return ctx._log(["（季末請用「立刻收季」。）"])
    if event.id in s.world.timeline:
        return ctx._log([f"（{event.title}已經結算了。）"])
    battle = ctx.world.get_battle()
    running = battle is not None and battle.phase != "ended" and battle.battle_id in c.battles
    if running and c.battles[battle.battle_id].timetable_event == event.id:
        return ctx._log([f"（{event.title}正在打，先取消決戰。）"])
    if event.version_from is not None and event.version_from not in s.world.timeline:
        source = _timetable_event(ctx, event.version_from)
        return ctx._log([f"（{event.title}要等{source.title if source else event.version_from}結算了才知道是哪一版。）"])
    if key not in timetable.result_keys(s, c, event):
        return ctx._log([f"（{event.title}沒有「{key}」這個結果。）"])
    msgs = timetable.resolve(s, c, event, ctx.rng, key=key)
    ctx._save_season()
    mandate = seal_base.mandate_event(c)
    if mandate is not None and event.id == mandate.id:  # 管理者替天命之爭定結果：也定天命（8.3）
        battle = seal_base.mandate_battle(c)
        ctx._mandate_settle(key.split(":")[0], None, battle.name if battle is not None else event.title)
        ctx.state.world = ctx.world.get_season()
    ctx._deliver_big_events()
    return ctx._log(msgs)


def admin_clear_lock(ctx, event_id: str) -> list[str]:
    """清鎖定：拿掉一件大事的伏筆鎖定（第一個做完的人）與之後才做完的名單，結算時照沒人鎖定擲骰。"""
    refusal = _timetable_refusal(ctx, "清鎖定")
    if refusal:
        return ctx._log(refusal)
    w = ctx.state.world
    event = _timetable_event(ctx, event_id)
    if event is None:
        return ctx._log(["（沒有這件大事。）"])
    if event_id not in w.locks:
        return ctx._log([f"（{event.title}沒有人鎖定。）"])
    del w.locks[event_id]
    w.lock_losers.pop(event_id, None)
    ctx._save_season()
    msg = f"已清掉{event.title}的鎖定。"
    ctx._write("清鎖定", [msg], tag="管理者")
    return ctx._log([msg])
