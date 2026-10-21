"""季曆（計畫第六節）：世界時鐘照舊走真實秒，體力、走路、打坐、決戰回合都看它；另外把一季壓成
season_weeks 週的「季曆」——季曆秒＝世界秒 × cal_scale。第一季的規則（時刻表的週次、週初發軍令、伏筆的夜裡）
一律看季曆。濃縮版 2.5 天、12 週時 cal_scale 是 33.6：一週是真實 5 小時，夜裡每 43 分鐘有 11 分鐘。

季長照這一季開季時蓋的章（WorldState.length_days）：設定中途換了，正在跑的這一季週次不會移動；沒有章的舊季照預設的 14 天。
21 天季（Config.season21，正式季整合設計 1.1）：season_weeks 3、季長 21 天，cal_scale 是 1（季曆就是現實的三週），另加一段偏移
（WorldState.cal_offset）：開季那一刻離那一週台灣週一 00:00 多遠。世界秒照舊從開季那一刻算；只有這裡把它換成季曆，其他季偏移是 0。
7 天濃縮季（同一套骨架，season21 也打開；企劃者 2026-10-20）另寫 Config.season_segments（[2, 2, 3]）：季曆的「週」換成三段
（第 1～2、3～4、5～7 天），CalPoint.week 是第幾段、weekday 是段裡第幾天；錨點是開季那一天的台灣 00:00，畫面寫「第 N 天 HH:MM」。
每個函式都收一個 season；只有沒有季可看的呼叫端（例如蓋章本身之前）才不給，那時照現在的設定。

只是換算，不改任何狀態；引擎不讀電腦時鐘，時間一律是傳進來的世界秒。"""
from __future__ import annotations

import math
import time as time_module  # 只拿 gmtime 換算傳進來的現實秒（FB-439），不讀時鐘；叫 time_module 是因為這個檔的參數多半叫 time
from typing import NamedTuple

from .models import Config, Content, TimetableEvent
from .state import WorldState
from .world_state import season_length_days

MINUTE = 60
HOUR = 3600
DAY = 86400
WEEK = 7 * DAY
WEEKDAYS = "一二三四五六日"  # weekday 0＝週一
NIGHT_FROM, NIGHT_UNTIL = 23, 5  # 夜裡＝子時到寅時，季曆 23:00～04:59（伏筆文件 3.1）
# 浮點誤差，照單位分開命名，不要混用：
EPS_MINUTES = 1e-6  # 季曆換算成整分時（以分為單位）：世界秒乘回季曆常差一點點，不然整點會算成前一分鐘
EPS_SECONDS = 1e-6  # 比較世界秒時：剛好在大事時刻、曆時交界、週初的那一刻要算「到了」
EPS_CAL_HOURS = 1e-9  # 找下一個曆時交界時的浮點誤差（以曆時為單位）：剛好停在交界上的時間不能被算成上一個曆時（同 world.EPS_CAL_HOURS）


class CalPoint(NamedTuple):
    week: int  # 第幾週，從 1 起、最多 season_weeks
    weekday: int  # 0＝週一
    hour: int
    minute: int
    cal_day: int  # 季曆第幾天，從 1 起、跨整季


def season_one_on(season: WorldState, content: Content) -> bool:
    """季曆與季的事只在開關開著、而且這一季開季時也是開的才跑：開關打開時還在跑的舊季不補算（計畫 T2）。"""
    return content.config.season_one and season.season_one


def season21_on(season: WorldState | None, content: Content) -> bool:
    """21 天季的骨架（季曆＝現實週、錨點、21 天的時刻表、不提前收季、今天＝現實一天）：設定開著、這一季開季時也蓋了章。"""
    return season is not None and content.config.season21 and season.season21


def week7_on(season: WorldState | None, content: Content) -> bool:
    """7 天濃縮季（企劃者 2026-10-20）：照現實天的季（season21_on），季曆的週換成段（Config.season_segments）。
    內容照天另寫的那一份（TimetableEvent.real7、FigureDef.active_from_day7、Condition.cal_day_*7）與「第 N 天」的寫法只看它。"""
    return season21_on(season, content) and bool(content.config.season_segments)


LEGACY_SEASON_WEEKS: int = Config.model_fields["season_weeks"].default  # 週末式季曆的週數（12）：Config 的預設，週末與 14 天的季都是它


def weekend_style(season: WorldState | None, content: Content) -> bool:
    """休季的這一季用的是週末式季曆（12 週、每週 7 天、沒有段），這個程式的設定卻已經是照現實天的（Config.season21）：
    季曆的週數（season_weeks）與段（season_segments）不蓋在季上，直接讀設定會把這一季的時刻照新程式的季曆算
    （FB-635：舊 week7 的季休季了，換上新 week7 的程式、開下一季之前，上一季的時刻全擠進「第 1 週・週二」）。
    開季時沒蓋 season21 的章就是週末式的季（舊的 week7、週末、14 天），休季之後它的時刻照它自己的季曆畫。
    只管休季（season.ended）：還在跑的季（換程式沒等休季，啟動時 profile_warning 印的那一種）時刻表、曆時交界還是照新設定在跑，
    只換畫面會讓畫面和大事對不上，那一種照舊（FB-520：新程式要等休季再部署）。
    設定沒開 season21 的程式（週末、14 天）本來就是週末式，不必換，一個字都不變。沒有季（蓋章之前）照設定。"""
    return season is not None and season.ended and content.config.season21 and not season.season21


def weeks(content: Content, season: WorldState | None = None) -> int:
    """季曆一共幾週（狀態列的 weeks、輿圖的 weeks_total、季曆最後一刻）：照這一季自己的季曆（weekend_style）。"""
    return LEGACY_SEASON_WEEKS if weekend_style(season, content) else content.config.season_weeks


def _segments(content: Content, season: WorldState | None = None) -> list[int]:
    """季曆的段（7 天濃縮季 [2, 2, 3]，其他季是空的）：週末式的季沒有段（weekend_style）。"""
    return [] if weekend_style(season, content) else list(content.config.season_segments)


def _week_days(content: Content, season: WorldState | None = None) -> list[int]:
    """季曆每一週幾天：7 天濃縮季照段（[2, 2, 3]），其他季一律 season_weeks 個 7 天。季曆的長度與週的分法照設定
    （season_weeks 不在章上；設定與章對不上時 profile_warning 印一行），只有開季時沒蓋 season21 的章、設定卻是照現實天的季
    照它自己的週末式季曆（weekend_style，FB-635）。給了 season 才看得出是哪一種。"""
    return _segments(content, season) or [7] * weeks(content, season)


def total_days(content: Content, season: WorldState | None = None) -> int:
    """季曆一共幾天：週末與 14 天的季 84（12 週）、21 天季 21、7 天濃縮季 7。"""
    return sum(_week_days(content, season))


def _split(day: int, content: Content, season: WorldState | None = None) -> tuple[int, int]:
    """季曆第 day 天（從 0 起）在第幾週（從 1 起）、那一週的第幾天（從 0 起）。沒有段時就是 day // 7 + 1、day % 7。"""
    segments = _segments(content, season)
    if not segments:
        return day // 7 + 1, day % 7
    start = 0
    for week, length in enumerate(segments, 1):
        if day < start + length:
            return week, day - start
        start += length
    beyond = day - start  # 季曆之外（point 夾在季末，碰不到）：之後照 7 天一週往下數
    return len(segments) + beyond // 7 + 1, beyond % 7


def _week_start_day(week: int, content: Content, season: WorldState | None = None) -> int:
    """第 week 週週初是季曆第幾天（從 0 起）。沒有段時就是 (week − 1) × 7；段數之後照 7 天一週往下數。"""
    segments = _segments(content, season)
    if not segments or week <= 1:
        return (week - 1) * 7
    return sum(segments[:week - 1]) + max(0, week - 1 - len(segments)) * 7


def _offset(content: Content, season: WorldState | None) -> float:
    """季曆的偏移（季曆秒）：21 天季是開季那一刻離那一週台灣週一 00:00 多遠，其他季是 0（一個字都不變）。"""
    return season.cal_offset if season21_on(season, content) else 0.0


def offset_at(time: float, content: Content, season: WorldState | None) -> float:
    """世界秒 time 那一刻的季曆偏移（FB-332）：21 天季暫停再繼續之後偏移加了暫停的長度，繼續之前的時刻照當時的偏移（cal_offset_history），
    之後照現在的。其他季是 0（同 _offset）。"""
    if not season21_on(season, content):
        return 0.0
    for until, offset in season.cal_offset_history:
        if time < until:
            return offset
    return season.cal_offset


def anchor_offset(now: float, content: Content) -> float:
    """開季那一刻（現實的 epoch 秒）離那一週台灣週一 00:00 幾秒（正式季整合設計 1.1：週一以外開季，第一週就短幾天）。
    台灣照 pill_day_utc_offset_hours（同回體丹的換日）；1970-01-01 是週四。
    7 天濃縮季（Config.season_segments）錨在開季那一天的台灣 00:00：沒有週可對，開季那天就是第 1 天，週幾開都是 7 天。"""
    local = now + content.config.pill_day_utc_offset_hours * HOUR
    days = math.floor(local / DAY)
    if content.config.season_segments:
        return local - days * DAY
    return local - (days - (days + 3) % 7) * DAY


# 待 joy 潤（FB-157）：主機的人看的那一行，兩個程式啟動時印
PROFILE_MISMATCH = "⚠ 這一季開季時第一季規則是開著的，這個程式的設定卻是關著的：這樣跑會把第一季的規則全關掉、懸賞也會重掛。兩個程式都要帶同一份設定（TIANXIA_PROFILE）。"
# 21 天季（season21）跟這個程式的設定對不上的那一行（兩個方向都印）：season_weeks 沒蓋在季上，季曆、時刻表會整個算錯。待 joy 潤
# FB-520（整合預演）：季中換上新程式時設定的名字沒變（week7 從週末式改成照現實天）、內容換了，舊的那一句「帶開季時那一份設定」
# 叫人做的事沒用；PM 定不擋（擋了伺服器起不來更糟），只把該怎麼辦寫清楚：沒帶設定就補上，換了程式就等休季、要回舊程式就還原備份。
SEASON21_MISMATCH = (
    "⚠ 正在跑的這一季是用另一種季曆開的（21 天、7 天照現實天，或週末式），跟這個程式現在的設定對不上：照這樣跑，季曆與時刻表會整個算錯。"
    "如果是兩個程式沒帶開季時那一份設定（TIANXIA_PROFILE），補上再開；如果是季中換了新程式（設定檔的名字一樣、內容換過，"
    "例：week7 從週末式改成照現實天），新程式要等休季再部署——現在要回到舊程式，請還原部署前的備份。"
)


def profile_warning(content: Content, season: WorldState | None) -> str | None:
    """啟動時設定對不上的那一行（FB-157；server.main、run_bots.main 印）：這一季蓋了第一季的章、這個程式卻沒開第一季規則（換版時
    其中一個程式沒帶 TIANXIA_PROFILE=weekend）。反過來（開關剛打開、還在跑的季開季時是關的）是正常的換季過渡，不印。沒有季是 None。
    季收了（休季）也不印：週末的季收了、主機故意不帶設定重開好開 14 天的下一季，這時印「要帶同一份設定」會叫人帶錯（審查）。"""
    if season is None or season.ended:
        return None
    if season.season21 != content.config.season21:  # 21 天季的章跟設定對不上（兩個方向）：season_weeks 不在章上，季曆整個對不上
        return SEASON21_MISMATCH
    if season.season21 and season.length_days != content.config.season_days:  # 照現實天的季，7 天與 21 天互相帶錯（週與段不在章上）
        return SEASON21_MISMATCH
    if not season.season_one or content.config.season_one:
        return None
    return PROFILE_MISMATCH


def cal_scale(content: Content, season: WorldState | None = None) -> float:
    """季曆秒 ÷ 世界秒。季長照 season 蓋的章（沒有章的舊季照 DEFAULT_SEASON_DAYS）；不給 season 時照現在的設定。"""
    days = season_length_days(season, content) if season is not None else content.config.season_days
    return total_days(content, season) / days


def point(time: float, content: Content, season: WorldState | None = None) -> CalPoint:
    """世界秒落在季曆的哪一刻。季末那一刻（或之後）寫成最後一週週日 23:59，不會冒出不存在的下一週。
    7 天濃縮季的 week 是第幾段、weekday 是段裡第幾天（季末夾在第 7 天 23:59）。"""
    total = total_days(content, season) * DAY
    # 照那一刻當時的偏移（FB-332：暫停再繼續之後，以前寫下的時刻不跟著往後挪）；現在與之後的時刻就是 cal_offset
    cal = min(max(0.0, time * cal_scale(content, season) + offset_at(time, content, season)), total - MINUTE)
    minutes = math.floor(cal / MINUTE + EPS_MINUTES)
    day, minute_of_day = divmod(minutes, 24 * 60)
    week, weekday = _split(day, content, season)
    return CalPoint(
        week=week, weekday=weekday, hour=minute_of_day // 60, minute=minute_of_day % 60, cal_day=day + 1,
    )


def week_start(week: int, content: Content, season: WorldState | None = None) -> float:
    """第 week 週週一 00:00 的世界秒（21 天季在週一以外開季時，第 1 週週一是負的：開季之前）。7 天濃縮季是第 week 段的第一天 00:00。"""
    return (_week_start_day(week, content, season) * DAY - _offset(content, season)) / cal_scale(content, season)


def week_seconds(content: Content, season: WorldState | None = None) -> float:
    """「一週」那麼長的世界秒（通緝退押金、入伍最後一步收尾、軍令看下一件大事有多近）：季曆的一週 WEEK ÷ cal_scale；
    7 天濃縮季照週算的換成段，一段平均（7 ÷ 3 天）。"""
    if week7_on(season, content):
        return total_days(content) / len(content.config.season_segments) * DAY / cal_scale(content, season)
    return WEEK / cal_scale(content, season)


def event_time(event: TimetableEvent, content: Content, season: WorldState | None = None) -> float:
    return week_start(event.week, content, season) + event.day * DAY / cal_scale(content, season)


def is_night(time: float, content: Content, season: WorldState | None = None) -> bool:
    hour = point(time, content, season).hour
    return hour >= NIGHT_FROM or hour < NIGHT_UNTIL


def cal_hour_seconds(content: Content, season: WorldState | None = None) -> float:
    """一個曆時是幾個世界秒：季的事每跨過一個曆時跑一次（world.advance_world_state）。"""
    return HOUR / cal_scale(content, season)


def next_hour_mark(time: float, content: Content, season: WorldState | None = None) -> float:
    """從世界秒 time 到下一個曆時交界還有幾個世界秒（world.advance_world_state 停在這裡跑季的事）：交界照季曆的整點，
    21 天季在 10:30 開季時第一個交界在 30 分鐘後；偏移是 0 時跟以前（世界秒照曆時的整數倍）一模一樣。"""
    hour = cal_hour_seconds(content, season)
    shift = _offset(content, season) / cal_scale(content, season)
    return (math.floor((time + shift) / hour + EPS_CAL_HOURS) + 1) * hour - (time + shift)


def hour_shift(content: Content, season: WorldState | None = None) -> float:
    """季曆的偏移換成世界秒（21 天季開季不在整點時，季曆的整點在世界秒的哪裡）；其他季是 0。"""
    return _offset(content, season) / cal_scale(content, season)


def hour_ceil(time: float, content: Content, season: WorldState | None = None) -> float:
    """世界秒 time 當下或之後的第一個季曆整點（FB-331：管理者排決戰、跳到下一件照季曆的整點對齊，季的事也在那裡跑）。
    剛好在整點上（差 EPS_SECONDS 以內）就是那一刻。偏移是 0 時跟以前的 ceil((t − EPS)/曆時)×曆時 一模一樣。"""
    hour, shift = cal_hour_seconds(content, season), hour_shift(content, season)
    return math.ceil((time + shift - EPS_SECONDS) / hour) * hour - shift


def hour_floor(time: float, content: Content, season: WorldState | None = None) -> float:
    """世界秒 time 當下或之前的最後一個季曆整點（timetable.quiet_place 往前挪用）；偏移是 0 時跟以前一模一樣。"""
    hour, shift = cal_hour_seconds(content, season), hour_shift(content, season)
    return math.floor((time + shift) / hour + 1e-9) * hour - shift


def day_index(time: float, content: Content, season: WorldState | None = None) -> int:
    """世界秒 time 落在季曆第幾天（從 0 起）。跟 point 不同，不夾在季末：管理者把季末往後排時「今天」照樣換（rules.game_day）。"""
    cal = time * cal_scale(content, season) + _offset(content, season)
    return math.floor(cal / MINUTE + EPS_MINUTES) // (24 * 60)


def open_day(content: Content, season: WorldState | None = None) -> int:
    """開季那一刻落在季曆第幾天（從 0 起，同 day_index）：21 天季是開季那一天離第 1 週週一幾天（簽到照它起算，12.3 第 43 條），
    其他季是 0。照開季時的偏移（offset_at(0)），暫停再繼續、偏移加了暫停的長度之後也不變。"""
    return math.floor(offset_at(0.0, content, season) / MINUTE + EPS_MINUTES) // (24 * 60)


def world_day(time: float, content: Content, season: WorldState | None) -> int:
    """「今天」的帳記的號碼（從 0 起；人物一天被打掉、回了多少、護衛犒軍探望、同一位人物一天只扣一次聲威）：21 天季是季曆第幾天
    （台灣 00:00 換日，正式季整合設計 1.3），其他季照舊世界天 int(time // DAY)。rules.world_day 同一個。"""
    return day_index(time, content, season) if season21_on(season, content) else int(time // DAY)


def cal_days(time: float, content: Content, season: WorldState | None = None) -> float:
    """世界秒 time 離第 1 週週一 00:00 幾個季曆天（含零頭；21 天季的人物照天數出兵用）。"""
    return (time * cal_scale(content, season) + _offset(content, season)) / DAY


# ── 畫面上的時間 ─────────────────────────────────────────


def day_clock_text(time: float) -> str:
    """沒有季曆時的寫法，例如「第2天 14:05」（戰報、江湖紀錄、地圖一直以來的樣子）。"""
    return f"第{int(time // DAY) + 1}天 {int(time % DAY // HOUR):02d}:{int(time % HOUR // 60):02d}"


def day_text(time: float) -> str:
    """沒有季曆時江湖史、傳聞只寫天數，例如「第2天」。"""
    return f"第{int(time // DAY) + 1}天"


def day_start(day: int, content: Content, world: WorldState) -> float:
    """季曆第 day 天 00:00 的世界秒（21 天季每天 00:00 的軍令截止、懸賞期限；正式季第 5 批）。day 從 1 算，可以是小數。"""
    return week_start(1, content, world) + (day - 1) * DAY / cal_scale(content, world)


PAST_END = "季曆最後一刻（{end}）之後 {span}，現實 {real}"  # 待 joy 潤（FB-439）


def calendar_end(content: Content, season: WorldState | None = None) -> float:
    """季曆最後一刻之後那一瞬（最後一週之後的週一 00:00）的世界秒：季曆時刻到這裡就停在最後一週週日 23:59（point）。"""
    return week_start(weeks(content, season) + 1, content, season)


def nominal_end(content: Content, season: WorldState) -> float:
    """這一季名義上的季末（世界秒；管理者往後排的季末不算，那是 world.season_end_time）：照現實天的季（21 天季、7 天濃縮季）是季曆
    最後一刻之後那一瞬（calendar_end，照錨點：週三 14:00 開的 7 天季是 7 天減 14 小時），其他季是季長 × DAY（偏移是 0，一個字都不變）。
    timetable.finale_default（季末的預設時刻）與 bounties.to_season_end（「到季末」，FB-500）共用這一個。"""
    if season21_on(season, content):
        return calendar_end(content, season)
    return season_length_days(season, content) * DAY


def span_text(seconds: float) -> str:
    """一段現實時間寫成最多兩個單位：「2 天 3 小時」「5 小時」「1 小時 20 分鐘」「40 分鐘」；不到一分鐘寫「不到一分鐘」。"""
    minutes = int(seconds // MINUTE)
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{n} {unit}" for n, unit in ((days, "天"), (hours, "小時"), (mins, "分鐘")) if n][:2]
    return " ".join(parts) or "不到一分鐘"


def schedule_text(time: float, real: float, content: Content, season: WorldState | None) -> str:
    """管理者排時間的回覆寫的時刻（FB-439）：季曆之內照 stamp_text；排到季曆最後一刻之後（季末往後排）時季曆時刻停在週日 23:59，
    照寫的話看起來像沒排過去，改寫「季曆最後一刻（…）之後 N 天 M 小時，現實 11/11 03:00」（現實照台灣時間，real 是那一刻的現實秒）。"""
    end = calendar_end(content, season)
    if not season_one_on(season, content) or time < end:
        return stamp_text(time, content, season)
    local = time_module.gmtime(real + content.config.pill_day_utc_offset_hours * HOUR)
    return PAST_END.format(
        end=stamp_text(end, content, season), span=span_text((time - end) / content.config.time_scale),
        real=f"{local.tm_mon}/{local.tm_mday} {local.tm_hour:02d}:{local.tm_min:02d}",
    )


def point_text(at: CalPoint, *, by_day: bool = False) -> str:
    """季曆時刻唯一的寫法「第 3 週・週二 21:40」（N 前後有空格）：狀態列第二行、下一件、江湖史、傳聞、軍令截止都走這裡，
    不要在別處自己拼（FB-062 之後 PM 定：全部跟狀態列第二行一樣）。
    by_day（7 天濃縮季，week7_on）寫「第 3 天 21:40」：季曆的週是段、星期也不是現實的星期，只寫第幾天（待 joy 潤）。"""
    if by_day:
        return f"第 {at.cal_day} 天 {at.hour:02d}:{at.minute:02d}"
    return f"第 {at.week} 週・週{WEEKDAYS[at.weekday]} {at.hour:02d}:{at.minute:02d}"


# ── 7 天濃縮季的「週」是段（FB-501，PM 2026-10-20）────────────────────
# 季曆有段的季（week7_on）畫面上寫「週」的地方，換字一律走 week_word／week_label（網頁走 week_words 送的那一份）；
# 其他季（21 天、週末、14 天）照原本的字，一個字都不變。7 天季的字待 joy 潤。
# 軍令的字（ORDER_KEYS）另照「這一季的軍令是不是每天發」（orders_daily：照現實天的季，21 天季也是；FB-502，PM 2026-10-20
# 推翻 FB-501 那一批「21 天季不動」）；週末、14 天照原本的字。
WEEK_WORDS = {  # 鍵：(照週的季, 7 天濃縮季；軍令的那幾個是軍令每天發的季)
    "this": ("本週", "這一段"),  # 本週大事、本週在任
    "this_one": ("這一週", "這一段"),  # 頭目「這一週他不再現身」
    "this_short": ("這週", "這一段"),  # 第 3、4 階行動「這週已經做滿 N 次」（FB-503）
    "each": ("每週", "每段"),  # 名聲：每週通緝、每週貼海捕文書
    "order_this": ("本週", "今日"),  # 軍令：21 天季、7 天季每天一道
    "order_that": ("這週", "今天"),  # 軍令的傳聞「這週連敗幾陣」
    "order_each": ("每週一", "每天"),  # 玩法說明、主線「每週一有軍令」
    "order_every": ("每週", "每天"),  # 入伍段引薦人「上頭每週發幾道軍令」（content/tutorial.json 的 {每週}）
    "realign": ("星期", "日子"),  # 暫停再繼續：季曆對回現實的星期（21 天季）／日子（7 天季）
}
ORDER_KEYS = ("order_this", "order_that", "order_each", "order_every")  # 照 orders_daily 換的那幾個（FB-502）


def orders_daily(season: WorldState | None, content: Content) -> bool:
    """這一季的軍令每天 00:00 發一道（正式季整合設計 7.1）：照現實天的季（21 天季、7 天濃縮季）；其他季每週一發。
    orders.daily 與軍令的字（ORDER_KEYS）都問它。"""
    return season21_on(season, content)


def week_word(key: str, content: Content, season: WorldState | None) -> str:
    """WEEK_WORDS[key] 照季挑一個：軍令的字（ORDER_KEYS）照軍令每天發不發（orders_daily），其餘照 7 天濃縮季（week7_on）；
    是的話後一個，不然前一個（原本的字）。"""
    on = orders_daily(season, content) if key in ORDER_KEYS else week7_on(season, content)
    return WEEK_WORDS[key][1 if on else 0]


def segment_days(week: int, content: Content) -> tuple[int, int]:
    """第 week 週（7 天濃縮季是第幾段）是季曆第幾天到第幾天（從 1 起）：[2, 2, 3] 的第 3 段是 (5, 7)。"""
    days = _week_days(content)
    first = _week_start_day(week, content) + 1
    return first, first + (days[week - 1] if 0 < week <= len(days) else 7) - 1


def week_label(week: int, content: Content, season: WorldState | None, *, form: str = "") -> str:
    """「第 N 週」照季寫：7 天濃縮季寫「第 N 段（第 a～b 天）」（FB-501；待 joy 潤）。form：
    ""＝「第 N 週」、"tight"＝「第N週」（管理者時刻表）、"end"＝「第 N 週週末」（天下怎麼變；7 天季「第 N 段末（第 b 天）」）、
    "inner"＝括號裡用的（月旦評；7 天季「第 N 段・第 a～b 天」）。"""
    if not week7_on(season, content):
        return {"tight": f"第{week}週", "end": f"第 {week} 週週末"}.get(form, f"第 {week} 週")
    first, last = segment_days(week, content)
    if form == "end":
        return f"第 {week} 段末（第 {last} 天）"
    if form == "inner":
        return f"第 {week} 段・第 {first}～{last} 天"
    return f"第 {week} 段（第 {first}～{last} 天）"


def week_words(content: Content, season: WorldState | None) -> dict | None:
    """給網頁的那一份（status.calendar.words；網頁 calWords／wkWord／wkName）：7 天濃縮季的 WEEK_WORDS 與每一段的 week_label
    （names、ends）；21 天季只有軍令的那幾個（ORDER_KEYS，FB-502；沒有 names，網頁的「週」照原本的字）；其他季是 None，網頁照原本的字。"""
    if not week7_on(season, content):
        if not orders_daily(season, content):
            return None
        return {key: WEEK_WORDS[key][1] for key in ORDER_KEYS}
    weeks = range(1, len(content.config.season_segments) + 1)
    return {
        **{key: pair[1] for key, pair in WEEK_WORDS.items()},
        "names": [week_label(w, content, season) for w in weeks],
        "ends": [week_label(w, content, season, form="end") for w in weeks],
    }


def stamp_text(time: float, content: Content, season: WorldState | None, *, clock: bool = True) -> str:
    """玩家看得到的遊戲時間，全部走這裡：第一季（開關開著、這一季也蓋了章）寫成狀態列那樣的「第 3 週・週二 21:40」（point_text）；
    其他時候照舊——clock 時「第2天 14:05」，不要時刻（江湖史、傳聞）時「第2天」，一個字都不變。
    season 是 None（例如上一季的江湖史）一律照舊。"""
    if season is not None and season_one_on(season, content):
        return point_text(point(time, content, season), by_day=week7_on(season, content))
    return day_clock_text(time) if clock else day_text(time)
