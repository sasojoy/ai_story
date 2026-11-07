"""推大勢（核心本體；第二輪第 80 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第80批.md，導覽 docs/guide/大勢人物與賽季.md）：
玩家自己造成的大勢推動與它旁邊那幾樣——季長倍數、每人每日上限、事件五折與盡頭阻力、零頭、領地爭奪的進度、文字的事的貢獻。原本是 Game 上的 12 個方法，
本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3），函式名拿掉開頭的底線，Game 留 11 個一行委派（出陣、事件檢定、人物情誼、軍情、server、假人、測試與 Game 原位在叫；
只有這裡叫的 resisted_line 不留）。push_trend 的 int 與 float 細節照舊（float(delta)、amount != int(amount)、int(amount)、不乘 1.0 那段註解）。

- 推力：season_scale、daily_push_cap、resisted_lines、shaped、carry、resisted_line、goals、push_room、push_trend
- 進度：push_progress、event_progress
- 文字的事的貢獻：deed_points

哪些經 ctx（手冊第十五節「換掉的才打得到」；tests/core/boundary_tables.py 的 PUSHING_VIA_CTX 守）：
- 被測試換掉的 3 個 Game 方法（daily_push_cap、_push_room、push_trend），模組裡只有 daily_push_cap 有人互叫：push_trend、push_room → ctx.daily_push_cap()（test_seal_acts 換 Game.daily_push_cap）。
  push_room、push_trend 模組裡沒有人互叫，都經委派（train_actions、step_actions、event_check、_squad_encounter、server、假人），打得到。其他互叫直接叫函式（不多跳一層）。
- 包的委派（CORE_DELEGATE_CALLERS）：event_progress → _story_tick（一條線，位置不動：前面提早回那一支、後面接在 push_progress 之後那一支）。
- 留在 Game 上的：state、content、_side、_pill_day；push_progress 讀 ctx._clash_won、寫 ctx._sortie_marked、ctx._sortie_moved、ctx._sortie_flipped：那是 Game 的欄位，不是這裡的模組變數。

名字的綁法照 engine：engine 拿名字的（change_trend、front_ids、is_revealed、resolve_goals、resolve_trend、world_trend_value、season_length_days）這裡也拿名字，叫模組屬性的（calendar、conquest、push、seal_acts、
territory、wins、outcome_rules）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣；deed_points 的 wins_rules.credit 這裡寫 wins.credit，engine 的 wins_rules 與 wins 是同一個模組的兩個別名。
engine 自己的 DAY 跟 calendar.DAY 同值同型別（86400）。引擎的 change_trend 換成假的腳本（scripts/sim_trend_sources.py）要連這裡的 pushing.change_trend 一起換。
engine 在 `from .core import combat` 之後才 import 這一份（這裡 import 的模組那時都已經載入，載入順序不變）。同 event_check 不進 MODULES、不進 FEATURES；這裡不 import 包。

改這一份要跑的測試：
- scripts/test_for.py：這個檔在 CORE_SERVICES。hunk 落在函式、類別、常數上 → 名字的功能群＋這個檔的底（檔名有 push、conquest、season21、fronts、gentry、outcomes 的，量到 31 個檔）＋邊界測試；
  函式以外（import、這段說明、模組層）或指名了卻沒有差 → 核心測試＋煙霧。互叫經 ctx 的（push_trend、push_room → ctx.daily_push_cap）不會往上算（_core_refs 只看 ast.Name），daily_push_cap 自己認得 push、push 就在底裡。
- 寫到這些名字、可是檔名不在底裡的只拿它當準備動作，留給閘門（why 寫幾個檔），要當場驗直接給檔名（test_seal_acts、test_explain、test_prologue 那三條換掉方法的）。
- same_behavior：compare --tracks surge（這一批開的一軌：傳檄、零頭、不會動的推動、阻力關著、不是 21 天季、文字的事），其餘經 events、train、strip、outlets、military、sortie、companions。
- 反方向（第 36 批認定第 1 條）：這裡 import 的模組都是核心或共用層，test_for.pick 在搬之前、之後挑的一樣，沒有少挑到的，不必另外跑。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .. import calendar, conquest, push, seal_acts, territory, wins
from .. import outcomes as outcome_rules
from ..calendar import DAY
from ..rules import change_trend, front_ids, is_revealed, resolve_goals, resolve_trend, world_trend_value
from ..world_state import season_length_days

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）


def deed_points(ctx, points: int, *, capped: bool = True) -> int:
    """記 points 點陣營貢獻進「文字的事」那一本（整合設計 5.3：分岔的後果、心意一筆、託付辦成了；減法季批 4、6）：有那一邊才記
    （散人不記，同推線），一天（季曆日）最多 Config.jianfa.deed_contribution_cap，超過的不記（PlayerState.deed_day／deed_today）。
    capped=False（託付辦成了，PM 2026-10-26：一週才一件，共用的話分岔記滿那一天託付就記不到）：照數全記，也不佔那一天的額度。
    走 wins.credit：兩軍照舊加 contrib 與那一週的帳，豪強另記此刻幫的那一軍那一本。回實際記了幾點。"""
    s, c = ctx.state, ctx.content
    if not points or ctx._side() is None:
        return 0
    w, p = s.world, s.player
    at = calendar.point(w.time, c, w)
    if not capped:
        wins.credit(p, c, w, at.week, points)
        return points
    if p.deed_day != at.cal_day:
        p.deed_day, p.deed_today = at.cal_day, 0
    room = outcome_rules.contribution_room(points, p.deed_today, c.config.jianfa.deed_contribution_cap)
    if room:
        p.deed_today += room
        wins.credit(p, c, w, at.week, room)
    return room


def push_room(ctx, trend_id: str) -> float:
    """自己今天在這條線上還推得動多少（每人每曆日上限，緩衝後的量）：跟 push_trend 走 push.py 的同一個算法（push.room）。
    第一季的規則沒開時 push_trend 不設上限，這裡也是無限。"""
    s, c = ctx.state, ctx.content
    if not calendar.season_one_on(s.world, c):
        return math.inf
    day = calendar.point(s.world.time, c, s.world).cal_day
    return push.room(s.player.pushed, day, trend_id, ctx.daily_push_cap())


def season_scale(ctx) -> float:
    """季長倍數（FB-165，企劃者 2026-10-12「要隨著賽季長度而調整」）：min(1, Config.drill_push_base_days ÷ 這一季的季長)。
    季長照開季時蓋的章（world_state.season_length_days，季曆用的同一個），不讀電腦時鐘：週末設定（2.5 天）是 1，14 天約 0.18，
    季越長越小。規則關著的季事件的大勢效果照它縮放（push_trend）；操練另見 drill_scale。"""
    days = season_length_days(ctx.state.world, ctx.content)
    return min(1.0, ctx.content.config.drill_push_base_days / days) if days > 0 else 1.0


def daily_push_cap(ctx) -> float:
    """每人每曆日每條線推得動多少（第一季，push.split_by_cap 的上限）：Config.daily_push_cap；盡頭阻力開著時再乘季長倍數
    （設計 5.2：週末設定 1，7 天的季約 0.36）。push_trend 與 _push_room 都讀它。"""
    cfg = ctx.content.config
    if calendar.season21_on(ctx.state.world, ctx.content):  # 21 天季：自己的上限，不乘季長倍數（正式季整合設計 7.4）
        return cfg.season21_daily.push_daily_cap
    return cfg.daily_push_cap * (season_scale(ctx) if cfg.push_resistance.enabled else 1.0)


def resisted_lines(ctx) -> set[str]:
    """盡頭阻力與事件五折只管戰線（設計 5.1、3.2）：三條戰線照這一季的規則換成真的會動的線——第一季是三條戰線本身，
    規則關著的季是它們合成的那一條（黃巾聲勢）。玉璽線索不算。"""
    c, w = ctx.content, ctx.state.world
    return {line for front in front_ids(c) if (line := resolve_trend(c, w, front)) is not None}


def shaped(ctx, trend_id: str, delta: float, source: str) -> tuple[float, bool]:
    """玩家這一下真的要推多少（設計 3.2、5.1、5.2）：可重複的事件推戰線打 event_trend_share；第一季的出陣乘季長倍數（規則關著的季
    照舊在 push_trend 那一條縮）；再照推之前的戰線打盡頭阻力。回傳（推的量, 有沒有被阻力打折）。開關都關著時原樣回傳。"""
    c, w = ctx.content, ctx.state.world
    cfg = c.config
    amount = float(delta)
    if trend_id not in resisted_lines(ctx):
        return amount, False
    if source == "event":
        amount *= cfg.event_trend_share
    season21 = calendar.season21_on(w, c)
    if season21 and source in ("sortie", "donate", "event"):  # 21 天季（7.4）：出陣、捐軍備、可重複的事件同一個速度，不乘季長倍數
        amount *= cfg.season21_daily.push_speed
    if not cfg.push_resistance.enabled:
        return amount, False
    if source in ("sortie", "donate") and calendar.season_one_on(w, c) and not season21:  # 捐軍備照出陣（素材與經濟設計第六節第 2 點）
        amount *= season_scale(ctx)
    share = push.resistance_share(world_trend_value(w, c, trend_id), amount, push.tuning_for(w, c))
    return amount * share, share < 1


def carry(ctx, trend_id: str, amount: float) -> int:
    """把縮放後的推力 amount 加進這一季這條線的零頭（WorldState.trend_accum，同一條線一個值、正負抵銷），回傳滿了的整數點數。
    決定性，不擲骰、不動 Game.rng。"""
    w = ctx.state.world
    whole, rest = push.take_whole(w.trend_accum.get(trend_id, 0.0), amount)
    if rest:
        w.trend_accum[trend_id] = rest
    else:
        w.trend_accum.pop(trend_id, None)
    return whole


def push_progress(ctx, loc_id: str, nominal: float, source: str, how: str | None = None) -> list[str]:
    """領地爭奪：推（攻：自己那一條往上）或拉（守：每一條往下）這一塊的進度（翻地與爭搶，輿圖簡化設計 4.1、4.2）。推多少＝nominal ×
    Config.conquest.progress_scale（出陣）÷ √n（n 同推線的人數緩衝），出陣再乘集火（conquest.focus_bonus）與混戰得勝（_clash_won）；
    事件（source="event"）推 event_progress、不乘 progress_scale、不吃集火、不記出陣那一筆。推不動（conquest.push_problem）是空的。
    出陣照推線那一本帳記貢獻（名目量）、記一筆出陣（conquest.mark：正在推的人、集火、混戰讀它）、進活躍名單。推滿當場易手（conquest.flip）。
    how 沒給照這裡此刻是不是自己的（自己的守、不是的攻）。回那幾句話。"""
    s, c = ctx.state, ctx.content
    w, p = s.world, s.player
    side = ctx._side()
    if side is None:
        return []
    how = how or ("hold" if conquest.holder(w, c, loc_id) == side else "attack")
    if conquest.push_problem(w, c, side, loc_id, how) is not None:
        return []
    cfg = c.config
    window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
    scale = cfg.conquest.progress_scale if source == "sortie" else 1.0
    # 傳檄（玉璽碎片改版第 2 批）：這一塊算進的那條線有照自家算的傳檄，進度同樣放大（人數緩衝之前）；沒有時一個字都不變
    if (writ := seal_acts.writ_factor(w, c, conquest.line_of(w, c, loc_id), side)) != 1.0:
        scale *= writ
    amount = push.buffered(nominal * scale, push.active_count(s, side, w.time, window))
    notes = ""
    if source == "sortie":
        focus = conquest.focus_bonus(w, c, loc_id, side, p.name)
        if focus:
            amount *= 1 + focus
            notes += conquest.FOCUS_NOTE.format(pct=round(focus * 100))
        if ctx._clash_won:
            amount *= cfg.conquest.clash_scale
            notes += conquest.CLASH_NOTE
    done = conquest.push(w, c, loc_id, side, p.name, amount, how, notes)
    conquest.tally(w, c, ctx._pill_day(), side, p.name, done.moved)  # 今天推了多少（出陣回報的小籤）
    if source == "sortie":
        conquest.mark(w, c, loc_id, p.name, side, how, done.moved)
        ctx._sortie_marked = True
        ctx._sortie_moved += done.moved
        ctx._sortie_flipped = ctx._sortie_flipped or done.flipped
        if calendar.season_one_on(w, c):
            gained = push.contribution(nominal, 1.0, 1.0, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
            wins.credit(p, c, w, calendar.point(w.time, c, w).week, gained)
    w.active_pushers.setdefault(side, {})[p.name] = w.time
    w.active_pushers = push.drop_stale(w.active_pushers, w.time, window)
    return done.lines


def event_progress(ctx) -> list[str]:
    """領地爭奪：在一塊區塊做完一則事件，往自己那一邊推一次進度（Config.conquest.event_progress；計畫 2.3）：自己的地方是拉、別人的與中立地是推。
    散人、在路上、事件還串著下一則、開關關著、此刻推不動都是空的。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if s.pending_event is not None or p.journey is not None or not conquest.on(c, s.world) or p.location is None:
        return ctx._story_tick()  # 一條線：段落事件了結了，照記下的那一步往下走（下一段就在這裡時直接端出來）
    return push_progress(ctx, p.location, c.config.conquest.event_progress, "event") + ctx._story_tick()


def resisted_line(ctx) -> str:
    """盡頭阻力打了折的那一下接哪一句（FB-432）：人站在自家陣營控制的地方（守、巡哨、傳道、在自家地盤碰上的事）推過頭是
    STEADY_LINE，其餘（攻、散人、沒有控制方的地方）照舊 RESISTED_LINE。"""
    side, loc = ctx._side(), ctx.state.player.location
    mine = side is not None and loc is not None and territory.controller(ctx.state.world, ctx.content, loc) == side
    return push.STEADY_LINE if mine else push.RESISTED_LINE


def goals(ctx) -> dict[str, int]:
    """自己陣營的目標，照 rules.resolve_goals 換過鍵（開關關著時三條戰線都算黃巾聲勢）；散人是空的。
    照那一邊（_side）：豪強分屬兩軍的季是依附那一軍的目標，所以豪強的守勢行動、修築塢堡、遊歷也往那一軍推。"""
    faction = ctx.content.scenario.find_faction(ctx._side())
    return resolve_goals(ctx.content, ctx.state.world, faction.goals) if faction is not None else {}


def push_trend(ctx, trend_id: str, delta: float, *, source: str) -> list[str]:
    """玩家自己造成的大勢推動一律走這裡（遊歷、出陣、操練、事件效果；sim_tick、時刻表、決戰、管理者不是個人推動，不走）。
    第一季設計第七節的規則，掛在第一季開關後面——開關關著（或這一季開季時是關的）就是 change_trend，一個字都不變：
    1. 陣營人數緩衝：推力 ÷ √n，n＝自己陣營 active_window_days 個曆日內推過大勢的成員（含自己這一次、含假人，最少 1）；
    2. 每人每曆日對每條線的上限（緩衝後算）：超過的部分不推大勢；
    3. 貢獻帳：替自己陣營的目標方向推才記，contrib_per_push × 推力（不打緩衝的折），超過上限的部分只記 over_cap_contrib_ratio；
    4. 散人照推、照受上限，n 當 1，不記貢獻也不進活躍名單。
    緩衝後常有小數：不足一點的記在全服的 trend_accum（每條線一個），滿一點才真的推；回傳 change_trend 的訊息
    （第一季規則開著時戰線是機器可讀的戰況變化，畫面上換成一句話，見 front_lines；開關關著是既有的「（黃巾聲勢 +2）」），
    只有整數真的動了才有。
    出陣探索與地盤（2026-10-14）：推之前先照 _shaped 打事件五折、第一季出陣的季長倍數、盡頭阻力（三個開關都關著時一個字都不變），
    打了阻力的那一下後面多一句 push.RESISTED_LINE（站在自家控制的地方是 STEADY_LINE，_resisted_line）；每人每曆日上限讀 daily_push_cap；
    貢獻照收到的 delta（名目量）全額記。
    source 是註記（"train"、"sortie"、"drill"、"event"、"event_once"……），不存檔。"""
    s, c = ctx.state, ctx.content
    w, p = s.world, s.player
    amount, resisted = shaped(ctx, trend_id, delta, source)
    # 傳檄（玉璽碎片改版第 2 批）：那一軍的人在那條線上往自家目標推，乘在盡頭阻力與季長倍數之後、人數緩衝與每人每日上限之前（上限照舊）；
    # 貢獻照收到的 delta（名目量）記、不跟著放大。沒有傳檄時一個字都不變（不乘 1.0：int 會變成 float）
    if (writ := seal_acts.writ_factor(w, c, trend_id, ctx._side(), amount)) != 1.0:
        amount *= writ
    tail = [resisted_line(ctx)] if resisted else []
    if not calendar.season_one_on(w, c):
        # 規則關著的季，事件的大勢效果照季長縮放（FB-165，PM 2026-10-12：季長是週末的 5.6 倍、門檻不變，每一下照舊推就一定提早
        # 收季）：零頭跟操練記在同一個 trend_accum，滿一點才推、才寫推動那一行。隱藏線浮現的那一下照原本的量（浮現的規則不變）。
        # 遊歷打贏（source="train"）也照季長縮放（企劃者 2026-10-13，FB-168：不縮放的話兩天裡兩邊的遊歷就能把黃巾聲勢從 25
        # 推到 60 或砸到 0，決戰「要嘛第一天開、要嘛整季不開」）。決戰收場不走這裡、不縮放；操練的縮放在出陣包 train_actions.drill_push 先算好，
        # 傳進來的已經是整數點數。一季只會發生一次的事件（source="event_once"：事件標了 once，或這一下新立世界旗標，
        # rules.apply_effect 判斷）照原本的量（FB-166）。出陣（source="sortie"）跟遊歷打贏一樣照季長縮放；打過折
        # （事件五折、盡頭阻力）的量有零頭，一律記進 trend_accum。
        scale = season_scale(ctx) if source in ("event", "train", "sortie", "donate") else 1.0
        if (scale < 1 or amount != int(amount)) and is_revealed(w, c, trend_id):
            whole = carry(ctx, trend_id, amount * scale)
            return (change_trend(s, c, trend_id, whole) if whole else []) + tail
        return change_trend(s, c, trend_id, int(amount)) + tail
    if amount == 0 or (amount < 0 and not is_revealed(w, c, trend_id)):  # 開季時才補蓋章的季沒記到新加的公開線，照樣算浮現
        return []  # change_trend 也不會動的推動：不能拿來刷貢獻、也不算活躍
    cfg = c.config
    now = w.time
    at = calendar.point(now, c, w)
    window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
    key = f"{at.cal_day}:{trend_id}"
    side = ctx._side()  # 人數緩衝、貢獻、活躍名單都照那一邊（豪強分屬兩軍：依附的那一軍）
    pushed = push.buffered(abs(amount), push.active_count(s, side, now, window))
    used = push.used_today(p.pushed, at.cal_day, trend_id)
    moved, _ = push.split_by_cap(pushed, used, ctx.daily_push_cap())  # 還推得動多少只在 push.room_left 算（_push_room 也走它）
    p.pushed = push.recent_days(p.pushed, at.cal_day)
    p.pushed[key] = used + moved

    msgs: list[str] = []
    if moved > 0:
        whole, rest = push.take_whole(w.trend_accum.get(trend_id, 0.0), moved if amount > 0 else -moved)
        if rest:
            w.trend_accum[trend_id] = rest
        else:
            w.trend_accum.pop(trend_id, None)
        if whole:
            msgs = change_trend(s, c, trend_id, whole)

    if side is not None:  # 散人：照推，但不記貢獻、不進活躍名單
        faction = c.scenario.find_faction(side)
        goal = faction.goals.get(trend_id, 0) if faction is not None else 0
        # 捐軍備（source="donate"）的貢獻照捐的份量在 donate_actions.take 記，推力不另記（PM 2026-10-15）
        if source != "donate" and goal and (goal > 0) == (amount > 0):  # 替自己陣營的目標方向推；逆著推、這條線沒有目標都不記
            gained = push.contribution(abs(delta), pushed, moved, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
            wins.credit(p, c, w, at.week, gained)
        w.active_pushers.setdefault(side, {})[p.name] = now
    w.active_pushers = push.drop_stale(w.active_pushers, now, window)  # 順手清掉超過時窗的人，名單不會一直長
    return msgs + tail
