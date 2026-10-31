"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、習得武學。"""
from __future__ import annotations

import math
import random
import re
from collections.abc import Callable
from typing import Literal, NamedTuple

from . import calendar, front_lines, gender, insights, library, materials, renown, rise, roster, seal_acts, team, treasures  # 與 roster 互相 import：只能引入整個模組、呼叫時才取屬性，不能 from .roster import …
from .allied import on as haoqiang_allied  # noqa: F401  豪強分屬兩軍：設計寫 rules.haoqiang_allied、rules.side_of，其他模組照這兩個名字讀
from .allied import side_of  # noqa: F401
from .martial_arts import content_art
from .models import BEST_OF, DEFAULT_SEASON_DAYS, FRONT_KEY, Check, Condition, Content, Effect, Ending, FactionDef, Trend
from .state import PLAYER, GameState, Rumor, RumorLayer, WorldState
from .world_state import JADE_SEAL_FRAGMENT_COUNT, WorldStateStore, length_factor, season_length_days  # noqa: F401
# length_factor：季長倍數（名聲設計 2.4、決戰道具 2.2 共用），定義在 world_state（stamp_season 要用），從這裡轉出去叫 rules.length_factor

DAY = 86400


def display_name(state: GameState) -> str:
    """地方傳聞裡的單獨事件寫的名字：選了「匿名行走」的人是「某位少俠」（女的是「某位女俠」，gender.anon；傳聞分層第七節）。只有那裡看匿名——天下大事、
    陣營軍情、江湖史、排行榜一律寫名號（state.player.name），不要拿這個去寫那些（企劃者 2026-10-06）。"""
    return gender.anon(state) if state.player.anonymous else state.player.name  # 某位少俠／某位女俠


def audience_bar(state: GameState, content: Content, companion_id: str) -> int:
    """這位人物此刻對你的求見門檻（武學與成長設計 9.1）：名望門檻（CharacterDef.audience_fame），投靠了他的陣營的人
    此刻的階（ranks.rank_of）每比第 1 階高一階抵 audience_rank_discount 點；投靠了但還沒晉升過的人一點都不抵。敵對陣營，
    以及不在大勢人物表上的人物只看名望；散人照遊俠名號的階抵（ranger.audience_discount，對所有人物都算）；寶物另扣 treasures.amount 的 audience。最低 0。
    第 4 階只算這一週在任的（企劃者裁決 E4，2026-10-07）：有資格、沒在任（候缺）的算第 3 階；週一掉出席次，門檻跟著回去。
    rank_of 是唯一讀階的地方（不另讀 PlayerState.rank 或 qualified）；ranks 會 import rules，所以在函式裡 import。"""
    parts = audience_parts(state, content, companion_id)
    return max(0, parts.bar - sum(n for _, n in parts.discounts))


class AudienceParts(NamedTuple):
    bar: int  # 這一季的名望門檻（乘過季長倍數）
    discounts: list[tuple[str, int]]  # （哪一項, 抵幾點），乘過倍數；沒有的不列


def audience_parts(state: GameState, content: Content, companion_id: str) -> AudienceParts:
    """求見門檻拆開（名聲設計 6.3）：門檻與每一項折抵——同陣營的階（ranks.rank_of 每比第 1 階高一階抵 audience_rank_discount）、
    散人的遊俠名號（名聲開著時是善惡稱號的段，ranger.audience_discount）、寶物（treasures.amount 的 audience，只算寶物那一格）、
    玄紐（玉璽碎片改版：傳承那一格的 audience，另列一項、寫碎片的名字）。
    長的季整條一起乘季長倍數（名聲 2.4，折抵跟著門檻同比例，renown.scale；沒有章、名聲關著是 1，跟以前一字不差）。"""
    from . import ranger, ranks, renown  # noqa: PLC0415  ranks、ranger → rules：在函式裡 import，避免循環

    k = renown.scale(state.world)
    bar = content.characters[companion_id].audience_fame
    figure = next((f for f in content.figures.values() if f.character == companion_id), None)
    p = state.player
    parts: list[tuple[str, int]] = []
    if figure is not None and p.faction is not None and p.faction == figure.faction:
        rank = (ranks.rank_of(state) - 1) * content.config.audience_rank_discount
        if rank:
            parts.append((f"{content.scenario.faction_name(p.faction, p.faction)}的階", rank))
    ranger_cut = ranger.audience_discount(state, content)  # 散人的遊俠名號：每一階抵幾點，對所有人物都算（陣營的人是 0）
    if ranger_cut:
        parts.append((renown.virtue_title(state, content) or ranger.title(content, state) or "遊俠名號", ranger_cut))
    treasure = round(treasures.amount(state, content, "audience", source="treasure"))  # 寶物「求見門檻」（裝備四欄 6.2）：扣完遊俠名號再扣
    if treasure:
        parts.append((treasures.audience_name(state), treasure))
    shard = round(treasures.amount(state, content, "audience", source="heirloom"))  # 玄紐（玉璽碎片改版）：另列一項、寫碎片的名字
    if shard:
        parts.append((treasures.heirloom_name(state), shard))
    return AudienceParts(int(bar * k + 0.5), [(name, int(n * k + 0.5)) for name, n in parts])


def audience_hint(state: GameState, content: Content, companion_id: str) -> str:
    """求見被打發時括號裡那一段（Game._brush_off）：「名望還差 10」；名聲的 explain 開著時再寫門檻與每一項折抵
    「名望還差 10；門檻 25，江湖遊俠抵 3」（名聲設計 6.3）。"""
    from . import renown  # noqa: PLC0415

    gap = audience_bar(state, content, companion_id) - state.player.stats.get("fame", 0)
    hint = f"名望還差 {gap}"
    if not renown.on(content, "explain"):
        return hint
    parts = audience_parts(state, content, companion_id)
    cuts = "、".join(f"{name}抵 {n}" for name, n in parts.discounts)
    return f"{hint}；門檻 {parts.bar}" + (f"，{cuts}" if cuts else "")


def can_meet(state: GameState, content: Content, companion_id: str) -> bool:
    """見得到這位大勢人物：名望到了他的求見門檻（audience_bar：名望，同陣營的階級可以抵一段），或是透過他的「結識」
    事件認識過（企劃者 2026-10-02 決定）。引擎的求見與交友對話、伏筆的對話片段（名望不夠的人改從行動偷聽，
    foreshadow.hear_after_action）都用這一個判斷，不要在別處再寫一份。"""
    p = state.player
    if f"結識:{companion_id}" in p.flags or p.stats.get("fame", 0) >= audience_bar(state, content, companion_id):
        return True
    return seal_acts.heart_open(state.world, content, companion_id)  # 收心（玉璽碎片改版第 2 批）：一日之內求見不看門檻


def current_day(state: GameState) -> int:
    """賽季第幾天（從 1 開始），照世界天（24 個世界小時）：beta 主線的 day_min／day_max、beta 那一季的新立門戶福緣用它。
    「每天幾次」「當天不能再…」這種上限不用它，用 game_day（跟著季長縮）。"""
    return int(state.world.time // DAY) + 1


# ── 遊戲日（企劃者 2026-10-08：「1 天是照現實的一天，但週末期間有縮時的話，就要等比例調整。」）──────────
# 以「遊戲日」為單位的上限（同一位人物一天談幾輪、路上收穫一天幾次、有所感選錯了當天不再悟、地方痕跡一人一天一次）
# 都照這裡的長度換日：現實 24 小時 ×（這一季蓋章的季長 ÷ 14 天）。14 天的季剛好 24 小時（一個字都不變）；週末 2.5 天的季
# 約 4.3 小時。換成季曆，兩種季都是 6 個曆日。季長照開季時蓋的章（world_state.season_length_days，跟季曆同一個章），
# 設定中途換了也不會動到正在跑的這一季。開關關著的 beta 季一樣照這條算：14 天的季照舊 24 小時，別的季長照比例。
# 每日推力上限、新手期、第 2 階行動、機緣的「當天」本來就是季曆天，不走這裡。

FULL_SEASON_DAYS = DEFAULT_SEASON_DAYS  # 一個遊戲日剛好是現實一天的季長（正式版 14 天）；短的季照比例縮


def day_seconds(content: Content, world: WorldState) -> float:
    """一個遊戲日有幾個世界秒：DAY × 季長 ÷ FULL_SEASON_DAYS（季長照 world 蓋的章；沒有章的舊季照 14 天）。21 天季是季曆的一天
    （DAY ÷ cal_scale，就是現實的一天，正式季整合設計 1.3）。"""
    if calendar.season21_on(world, content):
        return DAY / calendar.cal_scale(content, world)
    return DAY * season_length_days(world, content) / FULL_SEASON_DAYS


def game_day(content: Content, world: WorldState, time: float | None = None) -> int:
    """世界秒 time（不給就是此刻）落在這一季的第幾個遊戲日（從 1 起）。上限的帳記的是這個號碼：記的是別的號碼就當前幾天的。
    21 天季照季曆的天（台灣 00:00 換日；週三開季的第一天是第 3 天），季末往後排也照樣換（calendar.day_index 不夾在季末）。"""
    t = world.time if time is None else time
    if calendar.season21_on(world, content):
        return calendar.day_index(t, content, world) + 1
    return int(t // day_seconds(content, world)) + 1


def world_day(content: Content, world: WorldState, time: float | None = None) -> int:
    """「今天」的帳記的號碼（從 0 起；figures、engine 的一天只扣一次、figure_aid、figure_life 用）：21 天季是季曆第幾天減 1
    （台灣 00:00 換日，正式季整合設計 1.3），其他季照舊 int(time // DAY)（calendar.world_day）。"""
    return calendar.world_day(world.time if time is None else time, content, world)


def day_ends(content: Content, world: WorldState, time: float | None = None) -> float:
    """time（不給就是此刻）所在的遊戲日結束、下一個遊戲日開始的那一刻（世界秒）：game_day 在這一刻剛好換成下一天
    （n × 一天的長度碰上浮點誤差時，往後挪到第一個真的換了日的值，寫出來的時刻跟真的換日的那一刻不會差一點）。"""
    day = game_day(content, world, time)
    start = calendar.week_start(1, content, world) if calendar.season21_on(world, content) else 0.0  # 21 天季從第 1 週週一 00:00 數
    end = start + day * day_seconds(content, world)
    while game_day(content, world, end) <= day:
        end = math.nextafter(end, math.inf)
    return end


def day_turn(content: Content, world: WorldState, time: float | None = None) -> tuple[str, str | None]:
    """下一次換日寫給玩家看是哪一種（FB-102）：
    - ("at", 時刻)：換日在真的季末之前、寫得出來——一律走 calendar.stamp_text（第一季「第 3 週・週五 00:00」，開關關著「第3天 00:00」）；
    - ("later", None)：換日在真的季末（排定的季末，管理者可以往後排）之前，可是在名義季長之後：季曆只寫到最後一週週日 23:59，
      寫不出那一刻，但還會換日、上限照樣重算——句子不承諾時刻、也不說「這一季之內」（「過一陣子」，待 joy 潤）；
    - ("season", None)：換日在收季那一刻或之後（最後一個遊戲日、管理者把季末提前）：「這一季之內不會再…」才是真的。
    開關關著時「第N天 HH:MM」只寫到分：不是整分的換日（短的 beta 季）往後進位，寫出來的那一刻不會早於真的換日。
    什麼時候換日不在這裡改（rules.day_ends）。"""
    from .world import season_end_time  # noqa: PLC0415  world → rules：在函式裡 import，避免循環

    end = day_ends(content, world, time)
    if end >= season_end_time(world, content) - calendar.EPS_SECONDS:
        return ("season", None)
    # 名義季末照 calendar.nominal_end（FB-505，同 FB-500）：照現實天的季扣開季偏移（週三 14:00 開的 7 天季是 7 天減 14 小時），
    # 其他季就是季長 × DAY（一個字都不變）
    if end >= calendar.nominal_end(content, world) - calendar.EPS_SECONDS:
        return ("later", None)
    if not calendar.season_one_on(world, content):
        end = math.ceil(end / calendar.MINUTE - calendar.EPS_MINUTES) * calendar.MINUTE
    return ("at", calendar.stamp_text(end, content, world))


def day_ends_text(content: Content, world: WorldState, time: float | None = None) -> str | None:
    """換日那一刻的寫法（day_turn 的 "at"）；寫不出來（"later"、"season"）回 None。寫句子的地方用 day_turn 分三種說法（FB-102）。"""
    kind, moment = day_turn(content, world, time)
    return moment if kind == "at" else None


def add_world_flags(state: GameState, flags) -> None:
    """加入世界旗標並記錄第一次成立的時間；已存在的旗標不重設時間。"""
    w = state.world
    for flag in flags:
        if flag not in w.flags:
            w.flags.add(flag)
            w.flag_times[flag] = w.time


def check_condition(cond: Condition, state: GameState, content: Content | None = None) -> bool:
    """content 只有季曆的條件（night、week_min、week_max）用得到：沒給，或第一季開關關著（這一季開季時沒開）時，
    寫了這三個的條件一律不成立——beta 季沒有季曆（計畫 T7）。"""
    p, w = state.player, state.world
    if any(p.stats.get(k, 0) < v for k, v in cond.min_stats.items()):
        return False
    if any(p.stats.get(k, 0) > v for k, v in cond.max_stats.items()):
        return False
    if not set(cond.flags_all) <= p.flags or set(cond.flags_none) & p.flags:
        return False
    if cond.sects and p.sect not in cond.sects:
        return False
    if cond.no_sect and p.sect is not None:
        return False
    for key, need in cond.story_marks.items():  # 一條線的記號（storyline.py）：那條線沒開過算 0
        line, _, mark = key.partition(":")
        progress = p.storylines.get(line)
        if (progress.marks.get(mark, 0) if progress is not None else 0) < need:
            return False
    for key, most in cond.story_marks_max.items():
        line, _, mark = key.partition(":")
        progress = p.storylines.get(line)
        if (progress.marks.get(mark, 0) if progress is not None else 0) > most:
            return False
    if cond.level_min is not None and p.member.level < cond.level_min:
        return False
    # 擁有的武學都算（身上兩欄＋功法庫）：事件教的武學在欄位滿了時收進功法庫（F2），只看身上的話「還沒學過才出現」的
    # 付費課程（潁川汝南鏢局的追風步）學完還會一直回來、再收一次錢
    known_skills = set(library.owned_arts(state))
    if any(s not in known_skills for s in cond.skills_all):
        return False
    if any(s in known_skills for s in cond.skills_none):
        return False
    if any(w.trends.get(t, 0) < v for t, v in cond.trend_min.items()):
        return False
    if any(w.trends.get(t, 0) > v for t, v in cond.trend_max.items()):
        return False
    if not set(cond.world_flags_all) <= w.flags or set(cond.world_flags_none) & w.flags:
        return False
    day = current_day(state)
    if cond.day_min is not None and day < cond.day_min:
        return False
    if cond.day_max is not None and day > cond.day_max:
        return False
    if not set(cond.revealed_all) <= w.revealed or set(cond.revealed_none) & w.revealed:
        return False
    for flag, hours in cond.flag_age_hours.items():
        if flag not in w.flag_times or w.time - w.flag_times[flag] < hours * 3600:
            return False
    if set(cond.members_none) & set(p.team):
        return False
    if any(w.marks.get(k, 0) < v for k, v in cond.marks_min.items()):
        return False
    if any(w.marks.get(k, 0) > v for k, v in cond.marks_max.items()):
        return False
    # 豪強分屬兩軍：陣營與依附的那一軍都算（寫了 haoqiang 的照舊成立、寫了依附那一軍的也成立）；沒給 content 讀不到季的章，只比陣營
    mine = {p.faction, side_of(state, content) if content is not None else None} - {None}
    if cond.factions and not mine & set(cond.factions):
        return False
    if mine & set(cond.factions_none):
        return False
    if cond.controlled_by:  # 這裡此刻歸誰控制（地盤易手）：沒有 content、開關關著、不是戰線地點都不成立
        from . import territory  # noqa: PLC0415  territory → rules：在函式裡 import，避免循環

        if content is None or territory.controller(state.world, content, state.player.location) not in cond.controlled_by:
            return False
    if cond.ranger_min is not None or cond.ranger_path is not None:
        from . import ranger  # noqa: PLC0415  ranger → rules：在函式裡 import，避免循環

        if content is None or not ranger.active(state, content):
            return False
        if cond.ranger_min is not None and ranger.tier(state, content) < cond.ranger_min:
            return False
        if cond.ranger_path is not None and ranger.path(state, content) != cond.ranger_path:
            return False
    if cond.fame_tier is not None:  # 名聲：名望到這一季的第幾段（照季長倍數）；名聲關著照那一段沒乘倍數的門檻比名望（同改之前的 min_stats）
        from . import renown  # noqa: PLC0415

        if content is None:
            return False
        if renown.on(content):
            if renown.fame_tier(state, content) < cond.fame_tier:
                return False
        elif p.stats.get("fame", 0) < content.config.renown.fame_thresholds[cond.fame_tier - 1]:
            return False
    if cond.virtue_path is not None or cond.virtue_min is not None:  # 名聲 5.2、5.3：走哪一條路、善惡到第幾段（名聲關著一律不成立）
        from . import renown  # noqa: PLC0415

        if content is None or not renown.on(content):
            return False
        if cond.virtue_path is not None and renown.path(state) != cond.virtue_path:
            return False
        if cond.virtue_min is not None and renown.virtue_tier(state, content) < cond.virtue_min:
            return False
    if any(p.clue_items.get(k, 0) < v for k, v in cond.clue_items.items()):
        return False
    if cond.grain_min:  # 帶了糧（晉升奇遇 3.2；正式版丙二）：要 content 才算得出糧草與換算
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環

        if content is None or materials.grain_of(state, content) < foreshadow.need(content, cond.grain_min):
            return False
    if cond.fight_tiers:
        # 這次行動打的那一場：battle_card 每次行動開頭清掉、打完才指向那筆紀錄，所以上一次行動留下的紀錄不算
        fought = next((r for r in state.battles if r.id == state.battle_card), None)
        if fought is None or fought.tier not in cond.fight_tiers:
            return False
    if (cond.night is not None or cond.week_min is not None or cond.week_max is not None
            or cond.cal_day_min is not None or cond.cal_day_max is not None
            or cond.cal_day_min7 is not None or cond.cal_day_max7 is not None):
        if content is None or not calendar.season_one_on(w, content):
            return False
        if cond.night is not None and calendar.is_night(w.time, content, w) != cond.night:
            return False
        at = calendar.point(w.time, content, w)
        if calendar.week7_on(w, content):  # 7 天濃縮季照天數、讀 7 天的那一份（開季那天是第 1 天）
            if ((cond.cal_day_min7 is not None and at.cal_day < cond.cal_day_min7)
                    or (cond.cal_day_max7 is not None and at.cal_day > cond.cal_day_max7)):
                return False
        elif calendar.season21_on(w, content):  # 21 天季照天數、不看週（正式季整合設計 1.2 給開發 6）
            if ((cond.cal_day_min is not None and at.cal_day < cond.cal_day_min)
                    or (cond.cal_day_max is not None and at.cal_day > cond.cal_day_max)):
                return False
        elif (cond.week_min is not None and at.week < cond.week_min) or (cond.week_max is not None and at.week > cond.week_max):
            return False
    if cond.any_of and not any(check_condition(sub, state, content) for sub in cond.any_of):
        return False
    return True


class CheckOutlook(NamedTuple):
    """一次檢定的勝算：本人這項屬性現在的數值（含等級成長）、熟練加成、兩者相加減難度的差值、成功率（0～1）。"""

    stat_value: float
    bonus: int
    gap: float
    chance: float


def check_outlook(check: Check, state: GameState, content: Content, world: WorldStateStore) -> CheckOutlook:
    """每一個事件檢定都看本人的屬性（企劃者 2026-10-05「探索應該沒有本人跟夥伴之分了」：Check.by 讀得進來、不再有作用），
    本人的熟練加成（Check.practice，joy #15）照舊加上。差值每 +1，成功率 +10%；範圍 5%～95%。
    擲骰（roll_check）與選項括號裡的數值、心裡話那一檔（events.choice_label）都出自這一個函式的同一個差值，
    所以標籤講的和實際擲出來的不會對不起來。江湖水漲（rise.event_bump）：本人等級高了，難度在這裡多加幾點，內容寫的不動。"""
    stat_value = check_stat_value(check, state, content, world)
    bonus = team.practice_bonus(state, content, check)
    gap = stat_value + bonus - check.difficulty - rise.event_bump(state, content)  # 江湖水漲：等級高了檢定加深（Config.rise）
    if jianfa(content, state.world) and check.tier == 1:  # 減法季：第一階事件放寬（Config.jianfa.event_ease，企劃者 2026-10-26）；
        gap += content.config.jianfa.event_ease  # 第二、三階事件的檢定不放寬（事件分級設計稿）；關著一個字都不變
    return CheckOutlook(stat_value, bonus, gap, min(0.95, max(0.05, 0.5 + gap * 0.1)))


def check_stat_value(check: Check, state: GameState, content: Content, world: WorldStateStore) -> float:
    """檢定看的本人那一項屬性（含等級成長）：一般是 check.stat；stat 是 BEST_OF 時取 check.stats 裡最高的那一項
    （減法季整合設計 5.9：「出力」那一種後果，臂力與悟性誰高看誰）。"""
    if check.stat == BEST_OF:
        return max(team.check_value(state, content, world, PLAYER, stat) for stat in check.stats)
    return team.check_value(state, content, world, PLAYER, check.stat)


def check_gap(check: Check, state: GameState, content: Content, world: WorldStateStore) -> float:
    """本人的屬性（含熟練加成）減難度：選項括號裡挑哪一檔心裡話看它，擲骰的成功率也是它換算的（check_outlook）。"""
    return check_outlook(check, state, content, world).gap


def check_chance(check: Check, state: GameState, content: Content, world: WorldStateStore) -> float:
    return check_outlook(check, state, content, world).chance


def practice_line(check: Check, state: GameState, content: Content, world: WorldStateStore) -> str:
    """吃到熟練加成時，併進選項括號裡的那一句（例如「這種事你幹得多了。」）；沒吃到是空字串。"""
    if team.practice_bonus(state, content, check) <= 0:
        return ""
    rule = content.config.practice_bonus[check.practice]
    from . import renown  # noqa: PLC0415

    line = rule.line_explained if renown.on(content, "explain") and rule.line_explained else rule.line  # 名聲 6.3：說出是惡名讓你手熟
    return line.replace("{who}", "你")


def roll_check(check: Check, state: GameState, content: Content, world: WorldStateStore, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state, content, world)


FREE_TEXT_MIN_RATE, FREE_TEXT_MAX_RATE = 5, 85  # 隨口應對的成功率夾在這之間：再會寫也不會穩贏，寫得爛也不會必敗
FREE_TEXT_PER_POINT = 4  # 相關屬性每比 5 高（低）1 點，成功率 +4（−4）


def free_text_rate(llm_rate: int, choice, state: GameState, content: Content, world: WorldStateStore) -> int:
    """隨口應對的成功率（百分比）：LLM 評的 0～100，加上本人這項屬性的修正（跟一般檢定一樣只看本人，choice.by 不再有作用），
    夾在 5～85。choice 是 models.FreeTextChoice。"""
    return stat_rate(llm_rate, choice.stat, state, content, world)


def stat_rate(llm_rate: int, stat: str, state: GameState, content: Content, world: WorldStateStore) -> int:
    """LLM 評的 0～100 加上本人 stat 這項屬性的修正（每比 5 多一點 +FREE_TEXT_PER_POINT），夾在 5～85。隨口應對（照事件寫的屬性）
    與找素材的「自己說」（固定悟性，第 32 項）共用。"""
    return value_rate(llm_rate, team.check_value(state, content, world, PLAYER, stat))


def value_rate(llm_rate: int, value: float, base: float = 5) -> int:
    """stat_rate 的算法：LLM 評的分數加上（屬性值 − base）× FREE_TEXT_PER_POINT，夾在 5～85。隨口應對分岔的檢定（outcomes.rate，
    屬性值是 check_stat_value：best_of 取最高）也走它，base 換成那一種後果的難度（PM 2026-10-25 第 3 件）；其餘照舊是 5。"""
    rate = round(llm_rate + (value - base) * FREE_TEXT_PER_POINT)
    return max(FREE_TEXT_MIN_RATE, min(FREE_TEXT_MAX_RATE, rate))


def rate_words(rate: int) -> str:
    """成功率寫成「成算」：四捨五入到一成（85% 是九成，不用 round 的銀行家進位），不到一成寫「一成不到」。"""
    if rate < 10:
        return "成算一成不到"
    tenths = min(9, int(rate / 10 + 0.5))
    return f"成算{'一二三四五六七八九'[tenths - 1]}成"


_MARKS_TOKEN = re.compile(r"\{marks:([^{}]+)\}")


def fuzzy_count(n: int) -> str:
    """地方痕跡的人數只給模糊說法、不列名字（看不出誰是假人，伺服器假人設計第五節）。"""
    if n <= 0:
        return "還沒有人"
    if n <= 2:
        return "一兩個人"
    if n <= 9:
        return "幾個人"
    if n <= 19:
        return "十來個人"
    if n <= 49:
        return "幾十個人"
    return "上百人"


def fill_marks(text: str, state: GameState) -> str:
    """把文字裡的 {marks:地點:痕跡} 換成這個痕跡目前的模糊人數；寫給這個人看的稱呼照性別換（gender.address：女的「少俠」→「女俠」）。
    事件的本文與結果都經過這裡（也只寫給這個人看），所以內容裡寫死給玩家的稱呼在這裡換一次就好。"""
    text = gender.address(text, state)
    if "{?" in text or "{!" in text or "{said:" in text:  # 長篇奇事：照一條線的記號換段落、引自己寫過的話（storyline.vary）
        from . import storyline  # noqa: PLC0415  storyline → rules：延後 import

        text = storyline.vary(text, state)
    if "{marks:" not in text:
        return text
    return _MARKS_TOKEN.sub(lambda m: fuzzy_count(state.world.marks.get(m.group(1), 0)), text)


def add_marks(marks: dict[str, int], state: GameState, content: Content) -> None:
    """留下地方痕跡：同一個人對同一個痕跡，同一個遊戲日只算第一次（不讓一個人刷出整條變化）。遊戲日跟著季長縮（game_day）。"""
    day = game_day(content, state.world)
    for key, n in marks.items():
        if state.player.mark_days.get(key) == day:
            continue
        state.player.mark_days[key] = day
        state.world.marks[key] = state.world.marks.get(key, 0) + n * _stance_mark_scale(key, state, content)
        _note_mark_helper(key, state, content)


def _stance_mark_scale(key: str, state: GameState, content: Content) -> int:
    """人物心意（減法季批 6，恤民）讓這一條痕跡記一筆算幾筆；關著是 1（先問開關：關著連 stances 都不載）。stances → rules：延後 import。"""
    if not jianfa(content, state.world, "stances"):
        return 1
    from . import stances  # noqa: PLC0415

    return stances.mark_scale(state, content, key)


def _note_mark_helper(key: str, state: GameState, content: Content) -> None:
    """痕跡看得見開著時（減法季批 4）記下替有痕跡規則的痕跡出過力的人（WorldState.mark_helpers）：跨過門檻那一刻他們各記一則行狀
    （Game._mark_credits）。過了門檻之後出的力不記；沒有痕跡規則的痕跡（事件條件讀的那些）不記；關著一個字都不寫。"""
    w = state.world
    if key in w.marks_fired or not jianfa(content, w, "marks_visible") or not any(r.mark == key for r in content.mark_rules):
        return
    names = w.mark_helpers.setdefault(key, [])
    if state.player.name not in names:
        names.append(state.player.name)


def fail_stamina(amount: int, content: Content) -> int:
    """事件失敗另扣的體力（只縮扣的，不縮給的）乘 event_fail_stamina_scale、四捨五入（15 → 8、5 → 3；體力平衡提案第〇節）。"""
    if amount >= 0:
        return amount
    return -int(-amount * content.config.event_fail_stamina_scale + 0.5)


def failed(effect: Effect, content: Content) -> Effect:
    """檢定失敗、隨口應對失敗、劇情戰落敗（企劃者裁決 E6，2026-10-07）要套的 fail_effect：扣的體力照 fail_stamina 縮過。"""
    stamina = fail_stamina(effect.stamina, content)
    return effect if stamina == effect.stamina else effect.model_copy(update={"stamina": stamina})


# 隨口應對判成惡行而且成了（FB-223）：潤色沒寫成時的收尾（潤色寫成了就換成潤色那一段，Game.add_gamble_narration）。待 joy 潤
EVIL_DONE = "事情照你的意思成了，只是這件事，你不會想讓人知道。"


def evil_success(effect: Effect) -> Effect:
    """隨口應對的做法被判成惡行、而且擲中了（FB-223，企劃者 2026-10-14）：內容寫好的成功效果是照善果寫的，換成惡行的版本——
    加的善名換成加同樣多的惡名（照舊走 apply_effect：遊俠名號照實際動了多少記帳，散人走寇那一條照常）、扣惡名的拿掉、
    情誼只留扣的（對人家做了惡事，不會因此更親近）；結果句換成 EVIL_DONE，傳聞與江湖史（照善果寫的）拿掉。
    其他（銀兩、經驗、心得、名望、素材、地方痕跡……）照給；扣善名的照扣。"""
    stats: dict[str, int] = {}
    for key, delta in effect.stats.items():  # 照原本的順序：江湖紀錄的得失照這個順序寫
        if key == "good" and delta > 0:
            key = "evil"
        elif key == "evil" and delta < 0:
            continue
        stats[key] = stats.get(key, 0) + delta
    affinity = {who: delta for who, delta in effect.affinity.items() if delta < 0}
    return effect.model_copy(update={"text": EVIL_DONE, "stats": stats, "affinity": affinity, "rumor": "", "chronicle": ""})


def check_result_line(success: bool) -> tuple[str, str]:
    """檢定的結果：（江湖紀錄的標記, 敘事裡的那一行）。一律是本人出手，所以不寫誰（企劃者 2026-10-05），
    只寫「成功」「失敗」——事件選項、隨口應對、伏筆的最後一步都用這一個。"""
    word = "成功" if success else "失敗"
    return word, f"（{word}）"


def add_rumor(
    state: GameState, text: str, location: str | None = None, *, content: Content | None = None,
    layer: RumorLayer = "world", named: bool = True, faction: str | None = None,
) -> None:
    """記一則傳聞（傳聞分層設計第二節）。給了 content 與地點時，順便記下地點所在的大區。
    誰聽得到哪一則照 audible（地方傳聞看這裡記下的大區）；faction：陣營軍情只給這個陣營的人。"""
    add_season_rumor(state.world, text, location, content=content, layer=layer, named=named, faction=faction)


def add_season_rumor(
    season: WorldState, text: str, location: str | None = None, *, content: Content | None = None,
    layer: RumorLayer = "world", named: bool = True, faction: str | None = None,
) -> None:
    """同 add_rumor，直接記在一季上（手上沒有角色的 GameState 時用：WorldStateStore.mutate_season 裡）。"""
    from . import atlas  # atlas → world → rules：在函式裡 import，避免循環

    region = None
    if content is not None and location is not None and location in content.locations:
        found = atlas.region_of(content, location)
        region = found.id if found is not None else None
    season.rumors.append(
        Rumor(time=season.time, text=text, location=location, layer=layer, region=region, named=named, faction=faction)
    )


class Ears(NamedTuple):
    """一個人此刻聽得到什麼（傳聞分層設計第二、三節）：audible 照它判斷一則傳聞。大區要算多邊形，所以先算好一次（ears_of），
    整份傳聞清單共用。之後的計畫往這裡加欄位，不另寫一條規則：見聞紀錄（1b：聽過的地方傳聞，離開大區後還翻得到）、
    刺探帶回的敵情（1c）。"""

    faction: str | None  # 自己的陣營；散人是 None
    name: str  # 名號（個人線索只給這個名號）
    layered: bool  # 第一季的規則開著：地方傳聞照大區與傳聞板過濾。關著（beta）只看陣營與名號，跟以前一模一樣
    regions: frozenset[str]  # 此刻人在哪些大區（here_regions）
    since: float  # 傳聞板上最舊的那一刻（世界秒）：比它早的地方傳聞已經撤下了
    ally: str | None = None  # 豪強分屬兩軍：依附的那一軍（陣營軍情也聽得到，軍令發令與湊滿額度的傳聞才收得到）；其他人 None


def recent_seconds(days: float, content: Content, world: WorldState) -> float:
    """「最近幾天」換成世界秒：第一季照季曆天（跟著 weekend 設定縮，PM 2026-10-06 的時間單位裁定），
    beta（開關關著、或這一季開季時沒開）照世界天，跟以前一樣。"""
    return days * DAY / calendar.cal_scale(content, world) if season_one(content, world) else days * DAY


def here_regions(state: GameState, content: Content) -> frozenset[str]:
    """此刻人在哪些大區（傳聞分層 3.1「人在那個大區」）：人在某一站，是那一站的大區；在路上，是這段路兩頭的大區——
    兩頭不同區時兩區都算（跟沿途打聽同一個算法），所以一路走過去，經過的大區都聽得到。地圖沒有大區時是空的。"""
    from . import atlas  # atlas → world → rules：在函式裡 import，避免循環

    spot = atlas.road_spot(state, content)
    places = (state.player.location,) if spot is None else (spot.behind, spot.ahead)
    return frozenset(region.id for loc_id in places if (region := atlas.region_of(content, loc_id)) is not None)


def ears_of(state: GameState, content: Content) -> Ears:
    """這個人此刻的 Ears。地方傳聞板留最近 Config.rumor_board_days 天（季曆天）。"""
    p, w = state.player, state.world
    if not season_one(content, w):
        return Ears(faction=p.faction, name=p.name, layered=False, regions=frozenset(), since=0.0)
    since = w.time - recent_seconds(content.config.rumor_board_days, content, w)
    side = side_of(state, content)
    return Ears(faction=p.faction, name=p.name, layered=True, regions=here_regions(state, content), since=since,
                ally=side if side != p.faction else None)


def audible(rumor: Rumor, ears: Ears) -> bool:
    """這個人聽不聽得到這則傳聞（傳聞分層設計第二、三節）。見聞頁、沿途打聽、輿圖的 ✦ 與地點詳情、龍頭人物的近況、
    「你不在的時候」都照這一條，不要在別處另寫一份：
    - 陣營軍情只給那個陣營的人（散人沒有）、個人線索只給那個名號、天下大事人人都聽得到；
    - 地方傳聞（第一季的規則開著時）只給此刻人在那個大區的人，而且只留傳聞板上最近幾天的；沒有大區的（地圖沒有大區、發生地不明）
      人人都聽得到，但一樣只留板上的。
    - 陣營軍情一定要寫是哪個陣營、個人線索一定要寫是誰（layer 與欄位對不上時 fail closed：沒有人聽得到）。
    開關關著（beta）時只看陣營與名號，跟以前的 can_hear 一模一樣。"""
    if rumor.faction not in (None, ears.faction, ears.ally) or rumor.character not in (None, ears.name):
        return False
    # fail closed：寫成陣營軍情卻沒寫是哪個陣營、寫成個人線索卻沒寫是誰，沒有人聽得到（不會因為少寫一個欄位就人人聽見）
    if (rumor.layer == "faction" and rumor.faction is None) or (rumor.layer == "personal" and rumor.character is None):
        return False
    if not ears.layered or rumor.layer != "local":
        return True
    # 地方傳聞：只留板上最近幾天的；沒有大區的（地圖沒有大區、或發生地不明）沒有大區可比，人人聽得到，但一樣撤板
    return rumor.time >= ears.since and (rumor.region is None or rumor.region in ears.regions)


def can_hear(rumor: Rumor, state: GameState) -> bool:
    """只看陣營與名號那一半（beta 的規則）：等於不分大區、不看傳聞板的 audible。引擎裡列傳聞的地方都改走 audible＋ears_of
    （大區與傳聞板要 content 才算得出來）；這個留給手上沒有 content 的呼叫端。"""
    p = state.player
    return audible(rumor, Ears(faction=p.faction, name=p.name, layered=False, regions=frozenset(), since=0.0))


def add_chronicle(state: GameState, text: str) -> None:
    state.world.chronicle.append(Rumor(time=state.world.time, text=text))


def trend_name(content: Content, trend_id: str) -> str:
    return next(t.name for t in content.scenario.trends if t.id == trend_id)


def pending_event_title(state: GameState, content: Content) -> str | None:
    """現在待處理的那則事件，玩家看得到的名字（多段事件 next_event 是現在的這一段）；沒有待處理的事件、
    或內容裡找不到那則事件（存檔指著已經拿掉的事件）時是 None。說書人的框、「下一步」與輿圖的前往都從這裡拿名字（FB-063）。"""
    event = content.events.get(state.pending_event) if state.pending_event else None
    return event.title if event is not None else None


# ── 第一季濃縮版：戰線與開關（2026-10-04 計畫 T1）─────────────────
# 內容只寫一份（三條戰線、front 鍵）。第一季的規則沒開時（開關關著，或這一季開季時沒蓋「開」的章），
# 下面的換算讓規則與畫面跟 beta 那一季一模一樣：三條戰線與 front 都算黃巾聲勢，第一季才有的其他線不存在。

HUANGJIN = "huangjin"  # 黃巾聲勢：開關開著時是三條戰線的加權（Trend.derived）


def season_one(content: Content, world: WorldState) -> bool:
    """第一季濃縮版的規則在這一季開了沒：開關開著，而且這一季開季時也蓋了「開」的章（T2 的 calendar.season_one_on）。
    開關打開時還在跑的 beta 那一季照舊用 beta 的規則，新規則從開關打開後開的下一季起算（PM 2026-10-04）。"""
    return calendar.season_one_on(world, content)


def jianfa(content: Content, world: WorldState | None, part: str | None = None) -> bool:
    """減法季的規則在這一季開了沒（Config.jianfa，企劃者 2026-10-24）：主機的開關開著，而且這一季開季時也蓋了章
    （WorldState.jianfa_on，world_state.stamp_season）。正在跑的季照它自己的章；開關關掉時一律照關著（主機的緊急開關）。
    part 給了再看那一個子開關（JianfaRules 的欄位，例："explore_one"；整合設計第十二章）。
    減法季的規則改動一律先問這一個（畫面的改動不掛開關）；world 是 None 一律是假。"""
    cfg = content.config.jianfa
    if world is None or not cfg.enabled or not world.jianfa_on:
        return False
    return part is None or bool(getattr(cfg, part))


OffKind = Literal["thresholds", "storylines", "battles", "events", "milestones", "world_events", "unlocks"]


def season_one_off(content: Content, world: WorldState, kind: OffKind) -> frozenset[str]:
    """第一季不觸發的那一種 beta 內容（Scenario.season_one_off 的 thresholds／storylines／battles／events／milestones／
    world_events，與第一季直接開放的地點 unlocks）的 id。
    只在 season_one 成立時有東西：開關關著、或這一季開季時沒開（beta 那一季），一律是空的，beta 照舊。"""
    if not season_one(content, world):
        return frozenset()
    return frozenset(getattr(content.scenario.season_one_off, kind))


def _trend(content: Content, trend_id: str) -> Trend | None:
    return next((t for t in content.scenario.trends if t.id == trend_id), None)


def front_of(content: Content, loc_id: str) -> str | None:
    """地點所在大區的戰線（MapRegion.front）；洛陽這類沒有戰況的大區、或地圖沒有大區時是 None。只讀內容，開關關著也照算。"""
    from . import atlas  # atlas → world → rules：在函式裡 import，避免循環

    region = atlas.region_of(content, loc_id)
    return region.front if region is not None else None


def front_ids(content: Content) -> list[str]:
    """戰線：地圖上有大區把它當 front 的線，照劇本 trends 的順序。"""
    used = {region.front for region in content.map.regions if region.front}
    return [t.id for t in content.scenario.trends if t.id in used]


def trend_shown(content: Content, world: WorldState, trend_id: str) -> bool:
    """這條線在這一季的規則下存在嗎：第一季的規則沒開時，第一季才有的線（Trend.season_one）不顯示、不推；
    （豪強割據 2026-10-31 連豪強第三方一起拿掉，T-05。）"""
    trend = _trend(content, trend_id)
    if trend is None:
        return False
    return season_one(content, world) or not trend.season_one


def pushable(content: Content, world: WorldState, trend_id: str) -> bool:
    """可以直接推的線：存在，而且不是第一季規則下的衍生線（黃巾聲勢由三條戰線合成）。"""
    trend = _trend(content, trend_id)
    return trend_shown(content, world, trend_id) and not (trend.derived and season_one(content, world))


def resolve_trend(content: Content, world: WorldState, key: str, location: str | None = None) -> str | None:
    """內容寫的大勢鍵 → 這一次真的要推（或讀）的那條線；None＝這次不推。
    第一季的規則開著（season_one）：front 是 location 所在大區的戰線（洛陽沒有戰況→None），其他照寫。
    沒開（beta 照舊）：front 與三條戰線都算它們合成的那條線（黃巾聲勢），第一季才有的其他線→None。"""
    if season_one(content, world):
        if key == FRONT_KEY:
            return front_of(content, location) if location is not None else None
        return None if _trend(content, key) is not None and not trend_shown(content, world, key) else key
    if key == FRONT_KEY:
        return next((t.id for t in content.scenario.trends if t.derived), None)
    total = next((t.id for t in content.scenario.trends if key in t.derived), None)
    if total is not None:
        return total
    return key if trend_shown(content, world, key) else None


def resolve_trends(
    content: Content, world: WorldState, trends: dict[str, int], location: str | None = None,
) -> dict[str, int]:
    """一整份推動照 resolve_trend 換鍵：換到同一條線的加總，換成 None 的丟掉。"""
    out: dict[str, int] = {}
    for key, delta in trends.items():
        target = resolve_trend(content, world, key, location)
        if target is not None:
            out[target] = out.get(target, 0) + delta
    return out


def resolve_goals(content: Content, world: WorldState, goals: dict[str, int]) -> dict[str, int]:
    """陣營目標照 resolve_trend 換鍵（開關關著時三條戰線都算黃巾聲勢）：目標只有方向，換到同一條線時留第一個。"""
    out: dict[str, int] = {}
    for key, direction in goals.items():
        target = resolve_trend(content, world, key)
        if target is not None:
            out.setdefault(target, direction)
    return out


def world_trend_value(world: WorldState, content: Content, trend_id: str) -> int:
    """一條線現在的值：開關開著時衍生線（黃巾聲勢）照來源線現算；存檔裡沒有這條線（內容改版前開的那一季）時用劇本的起始值。"""
    trend = _trend(content, trend_id)
    if trend is not None and trend.derived and season_one(content, world):
        return _weighted(world, content, trend)
    if trend_id in world.trends:
        return world.trends[trend_id]
    return trend.start if trend is not None else 0


def _weighted(world: WorldState, content: Content, trend: Trend) -> int:
    """衍生線的值：來源線的加權和，四捨五入到整數（int(x + 0.5)；先 round 到小數六位，免得 44.4999… 這種浮點雜訊）。"""
    total = sum(world_trend_value(world, content, source) * weight for source, weight in trend.derived.items())
    return int(round(total, 6) + 0.5)


def recompute_trends(world: WorldState, content: Content) -> None:
    """開關開著時，把每條衍生線（黃巾聲勢）存成來源線的加權和——條件、門檻與直接讀 trends 的地方讀的是存下來的值。
    開關關著時不動（beta 那一季的黃巾聲勢是一般的線）。"""
    if not season_one(content, world):
        return
    for trend in content.scenario.trends:
        if trend.derived:
            world.trends[trend.id] = _weighted(world, content, trend)


def is_revealed(world: WorldState, content: Content, trend_id: str) -> bool:
    """這條線浮現了沒：記在 revealed 裡，或者本來就是公開的線（內容改版前開的那一季沒記到新加的公開線，照樣算浮現）。"""
    if trend_id in world.revealed:
        return True
    trend = _trend(content, trend_id)
    return trend is not None and not trend.hidden


def trend_value(state: GameState, content: Content, trend_id: str) -> int:
    """同 world_trend_value，讀這個角色看到的那一份賽季。讀戰線、黃巾聲勢一律走這裡。"""
    return world_trend_value(state.world, content, trend_id)


def seed_trends(world: WorldState, content: Content) -> None:
    """一季剛開始的大勢：照劇本的起始值，公開的線記成已浮現；第一季的規則沒開時不放第一季才有的線（照這一季的章，所以要先蓋章再種）。"""
    trends = [t for t in content.scenario.trends if trend_shown(content, world, t.id)]
    world.trends = {t.id: t.start for t in trends}
    world.revealed = {t.id for t in trends if not t.hidden}
    recompute_trends(world, content)  # 開關開著時黃巾聲勢從三條戰線的起始值算（40／35／55 → 45）


def in_chaos(state: GameState, content: Content, front: str) -> bool:
    """亂局：戰況在 chaos_low～chaos_high 之間（含兩端，第一季設計 4.2「戰況在 35～65 之間的戰線」）。"""
    cfg = content.config
    return cfg.chaos_low <= trend_value(state, content, front) <= cfg.chaos_high


def chaos_fronts(state: GameState, content: Content) -> list[str]:
    """在亂局裡的戰線 id（照 front_ids 的順序）。江湖頁圖卡的「亂局」標與亂局帶、只在亂局做得了的軍階行動、軍令挑線
    讀的都是這一份（FB-065；豪強割據 2026-10-31 拿掉）。"""
    return [front for front in front_ids(content) if in_chaos(state, content, front)]


_COUNT_WORDS = "零一二三四五六七八九十"


def count_word(n: int) -> str:
    """幾條、幾件寫給玩家看：十以內寫國字（「三條戰線」），再多寫數字。態勢卡與玩法說明（howto）共用這一個寫法。"""
    return _COUNT_WORDS[n] if 0 <= n < len(_COUNT_WORDS) else str(n)


def stance_sum_note(content: Content) -> str:
    """官軍、黃巾的態勢是幾條戰況合起來的（FB-065；權重不印）：「三條戰線合計」。"""
    return f"{count_word(len(front_ids(content)))}條戰線合計"


_STANCE_SIDES = ("guan", "huang")


def stance_sides(content: Content, world: WorldState) -> tuple[str, ...]:
    """這一季有態勢的幾方：官軍、黃巾（豪強割據與第三方豪強 2026-10-31 拿掉，T-05；豪強分屬兩軍）。"""
    return _STANCE_SIDES


def stances(state: GameState, content: Content) -> dict[str, int]:
    """態勢（第一季設計 4.4）：官軍＝100－黃巾聲勢，黃巾＝黃巾聲勢。"""
    huangjin = trend_value(state, content, HUANGJIN)
    return {"guan": 100 - huangjin, "huang": huangjin}
# 態勢卡上三方的叫法（web/app.js 的 STANCE_NAMES 同一份；陣營本身叫黃巾軍、地方豪強）；玩法說明（howto）照它寫，跟卡上同一個叫法
STANCE_NAMES = {"guan": "官軍", "huang": "黃巾", "haoqiang": "豪強"}
_STANCE_COMPLEMENT = {"guan": "huang", "huang": "guan"}  # 官軍＝100－黃巾：兩邊互為補數；豪強沒有另一方可換


MANDATE_RULE = "天命之季不提前收季：天命之爭得勝的一方得天命；沒有分出天命，就到季末比高低。"  # 待 joy 潤：態勢卡底下那一句
# 整季都不提前收、又不是天命之季（21 天季，正式季整合設計 1.1）的那一句；finale 是「到季末，…」那半句（待 joy 潤）
NO_EARLY_RULE = "這一季不會提前收場：{finale}"

# 提前收季只看戰線（FB-254，企劃者 2026-10-15）：只有官軍、黃巾的態勢（黃巾聲勢）到了門檻才提前收季
EARLY_END_SIDES = frozenset({"guan", "huang"})


def ends_early(ending: Ending) -> bool:
    """這一種第一季結局到了門檻會不會提前收季（world.decisive_ending）：有態勢門檻（stance_min／stance_max），而且只看官軍、黃巾。"""
    sides = set(ending.stance_min) | set(ending.stance_max)
    return bool(sides) and sides <= EARLY_END_SIDES


def decisive_week(season: WorldState, content: Content) -> int:
    """這一季從第幾週起才會提前收季：21 天季一律 season_weeks + 1（一定打滿三週，正式季整合設計 1.1）；天命之季照
    Config.seal.mandate.decisive_from_week（13，等於不提前收，玉璽碎片設計 8.2）；其餘照 decisive_from_week。不改
    Config.decisive_from_week，一般季的節奏不變。"""
    if calendar.season21_on(season, content):
        return content.config.season_weeks + 1
    return content.config.seal.mandate.decisive_from_week if season.mandate else content.config.decisive_from_week


def _one_bar(ending: Ending) -> tuple[str, int] | None:
    """一種結局的態勢門檻寫得成「哪一方在幾分以上」嗎：只有一個條件時回（那一方, 分數）——stance_max 換成另一方（黃巾 ≤ 15 就是
    官軍 ≥ 85，兩邊互為補數）；兩個條件合成一種、或換不到另一方（豪強）回 None。"""
    if len(ending.stance_min) + len(ending.stance_max) != 1:
        return None
    if ending.stance_min:
        ((side, bar),) = ending.stance_min.items()
        return side, bar
    ((side, bar),) = ending.stance_max.items()
    return (_STANCE_COMPLEMENT[side], 100 - bar) if side in _STANCE_COMPLEMENT else None


def stance_rule_note(state: GameState, content: Content) -> str:
    """態勢卡底下那一句收季規則（第一季設計 4.4；正式版辛；FB-254）：門檻從第一季結局算，不寫死。待 joy 潤。
    會提前收季的結局（ends_early：只看官軍、黃巾）換成「哪一方到幾分」：stance_min 的那一方到那個值；stance_max 的黃巾 ≤ 15
    就是官軍 ≥ 85（官軍與黃巾互為補數）。同一方有幾個門檻取最小的。數字都一樣寫「官軍或黃巾的態勢一到 85」，不一樣照每一方寫自己的
    （「官軍一到 85、黃巾一到 90」）；兩個條件合成一種的結局換不出「哪一方到幾分」，寫一句不帶數字的話，不報算不出來的數字。
    其餘有態勢門檻的到季末才判：「否則到季末，某方的態勢在 N 以上是某結局，不然比高低。」；
    寫不成「哪一方在幾分以上」的也寫一句不帶數字的話。第 decisive_from_week 週以前寫「第 N 週起」，之後不寫。
    整季都不提前收的季（decisive_week 超過 season_weeks）：蓋了天命之季的章寫 MANDATE_RULE；其餘（21 天季，正式季整合設計 1.1）
    會提前收的那幾種也到季末才判，寫 NO_EARLY_RULE。沒有任何有態勢門檻的結局時是空字串。"""
    start = decisive_week(state.world, content)
    whole = start > content.config.season_weeks  # 整季都不提前收：天命之季（8.2）、21 天季（1.1）
    reach: dict[str, int] = {}  # 一方 → 它到幾分就收季
    early, unclear = False, False
    late: list[str] = []  # 季末才判的門檻：「某方的態勢在 N 以上是某結局」
    late_unclear = False
    shown = set(stance_sides(content, state.world))
    for e in content.scenario.endings:
        if not e.season_one or not (e.stance_min or e.stance_max):
            continue
        if not (set(e.stance_min) | set(e.stance_max)) <= shown:  # 這一季沒有的一方：那個結局不參與
            continue
        bar = _one_bar(e)
        if whole or not ends_early(e):  # 季末才判（整季不提前收的季，黃巾聲勢 ≥85、≤15 也只影響季末的結局，1.1）
            if bar is None:
                late_unclear = True
            else:
                late.append(f"{STANCE_NAMES[bar[0]]}的態勢在 {bar[1]} 以上是{e.title}")
            continue
        early = True
        if bar is None:  # 兩個條件合成一種：不是「哪一方到幾分」
            unclear = True
            continue
        reach[bar[0]] = min(reach.get(bar[0], 100), bar[1])
    if not early and not late and not late_unclear:
        return ""
    if whole and state.world.mandate:  # 天命之季：整季都不提前收（8.2）
        return MANDATE_RULE
    if late_unclear:
        finale = "到季末，先看態勢有沒有到結局的門檻，再比高低。"
    elif late:
        finale = "到季末，" + "、".join(late) + "，不然比高低。"
    else:
        finale = "到季末比高低。"
    if not early:
        rule = finale
    elif unclear or not reach:
        rule = f"官軍或黃巾的態勢到了決勝的門檻，這一季當場收場；否則{finale}"
    elif len(set(reach.values())) == 1:
        who = "或".join(STANCE_NAMES[side] for side in _STANCE_SIDES if side in reach)
        rule = f"{who}的態勢一到 {min(reach.values())}，這一季當場收場；否則{finale}"
    else:
        rule = "、".join(f"{STANCE_NAMES[side]}一到 {reach[side]}" for side in _STANCE_SIDES if side in reach)
        rule += f"，這一季當場收場；否則{finale}"
    if whole:  # 21 天季：一定打滿三週（1.1）
        return NO_EARLY_RULE.format(finale=finale)
    week = calendar.point(state.world.time, content, state.world).week
    return f"第 {start} 週起，{rule}" if early and week < start else rule


def change_trend(
    state: GameState, content: Content, trend_id: str, delta: int, reveal: bool = True
) -> list[str]:
    """推動大勢線。隱藏線只有在 reveal=True 且正向推進時才會浮現；未浮現前其他推動一律無效。

    已浮現的大勢線，每次真的推動（夾在 0~100 之後實際有變化）都會多回傳一則顯示用的
    訊息，跟「銀兩 -5」「名望 +1」同一種呈現方式——改這個之前，大勢線只有「第一次浮現」
    那一刻才有任何文字反饋，之後不管是打贏遭遇戰、選了某個事件分支推動了多少，玩家在
    劇情文字裡完全看不到，必須自己點開「江湖大勢」分頁才看得到數字，等於看不出自己的
    行動有沒有用。sim_tick()（背景虛擬玩家，每小時自動微幅推動）刻意不接住這個回傳值，
    所以背景推動依然維持安靜，不會洗版；只有玩家自己選擇/打贏的那一刻才會顯示。

    第一季的規則開著時（season_one），三條戰線的變動不寫數字（FB-064）：回機器可讀的「大勢@<線 id> ±N」
    （front_lines.mark），畫面上由 front_chip／humanize 換成「潁川汝南：官軍步步進逼」這樣的一句話；其他的線與
    開關關著時一個字都不變。"""
    w = state.world
    trend = _trend(content, trend_id)
    if trend is not None and trend.derived and season_one(content, w):
        raise ValueError(f"「{trend.name}」由別的線合成，不能直接推（推它的來源線）：{trend_id}")
    msgs: list[str] = []
    if not is_revealed(w, content, trend_id):
        if not reveal or delta <= 0:
            return msgs
        w.revealed.add(trend_id)
        msgs.append(f"（江湖暗流湧動——「{trend_name(content, trend_id)}」浮上檯面。）")
    before = world_trend_value(w, content, trend_id)
    from . import conquest  # noqa: PLC0415  conquest → rules：在函式裡 import，避免循環

    if conquest.on(content, w) and trend_id in front_ids(content):
        actual = conquest.apply_push(w, content, trend_id, delta)  # 領地爭奪：其他來源推的是偏移（設計 4.7），值照舊寫回 w.trends
    else:
        after = min(100, max(0, before + delta))
        w.trends[trend_id] = after
        actual = after - before
    if actual:
        recompute_trends(w, content)  # 開關開著時推了戰線，黃巾聲勢跟著重算
        from . import territory  # noqa: PLC0415  territory → rules：在函式裡 import，避免循環

        territory.update(w, content)  # 戰線動了：地盤重算（出陣探索與地盤設計 4.2）
        if season_one(content, w) and is_side_trend(content, trend_id):
            # FB-064：戰線不給玩家看數字（看不出是哪一邊、也看不出好壞）。這裡回機器可讀的寫法，
            # 江湖紀錄照舊把同一條線的變動加總；畫出來的那一刻才換成一句話、照看的人的陣營上色（front_chip、humanize）
            msgs.append(front_lines.mark(trend_id, actual))
        else:
            msgs.append(f"（{trend_name(content, trend_id)} {'+' if actual >= 0 else ''}{actual}）")
    return msgs


# ── 戰況變化的說法（FB-064）──────────────────────────────────


def is_side_trend(content: Content, trend_id: str) -> bool:
    """變動要寫成「哪一方佔了便宜」的線：三條戰線。其他的線（玉璽線索、開關關著時的黃巾聲勢）照舊寫數字。"""
    return trend_id in front_ids(content)


def can_draw_side_change(content: Content, trend_id: str) -> bool:
    """這條線的戰況變化畫得出來嗎：內容裡有這條線，而且它還是戰線。紀錄裡存的是機器可讀的寫法，存檔可能比內容舊
    （內容改版拿掉了那條線）：畫不出來的一律丟掉，不當機、也不把原文露給玩家（front_chip、humanize 都先問這一關）。"""
    return _trend(content, trend_id) is not None and is_side_trend(content, trend_id)


def _beneficiary(content: Content, trend_id: str, delta: int) -> FactionDef | None:
    """這一次往這個方向動，是哪一個陣營佔了便宜：陣營目標（goals）的方向跟變動同號的那一個。
    戰況 0 是官軍穩控、100 是黃巾控制，這件事寫在內容裡（官軍 goals −1、黃巾 +1），不在程式裡。"""
    return next(
        (f for f in content.scenario.factions if (goal := f.goals.get(trend_id, 0)) and (goal > 0) == (delta > 0)), None,
    )


def front_text(content: Content, trend_id: str, delta: int, seed: str) -> str:
    """戰況變化的一句話（不寫數字）。戰線：「{戰線}：{陣營}{句子}」，陣營是往那個方向動時佔便宜的一方，
    句子照變動的大小（front_lines.band_of）在 content/front_lines.json 挑。
    一段有好幾句時照 seed 與線、段雜湊挑一句，不動引擎的亂數；seed 通常是那則紀錄的時間，同一則永遠同一句。"""
    lines = content.front_lines
    side = _beneficiary(content, trend_id, delta)
    band = front_lines.band_of(delta)
    pool = (lines.by_side.get(side.id, {}).get(band) if side is not None else None) or lines.generic[band]
    name = lines.sides.get(side.id, side.name) if side is not None else ""
    phrase = front_lines.pick(pool, f"{seed}|{trend_id}|{band}")
    return f"{trend_name(content, trend_id)}：{name}{phrase}"


def front_favour(content: Content, viewer: str | None, trend_id: str, delta: int) -> int:
    """這一次變動對看畫面的人（viewer＝他的陣營 id，散人是 None）是好事（1）、壞事（−1）還是無關（0）：
    他的陣營對這條線有目標（goals）時，方向一致是好事、相反是壞事；沒有目標的（散人、戰線上的豪強）一律 0。"""
    faction = content.scenario.find_faction(viewer)
    goal = faction.goals.get(trend_id, 0) if faction is not None else 0
    if not goal:
        return 0
    return 1 if (goal > 0) == (delta > 0) else -1


def front_chip(content: Content, viewer: str | None, change: str, seed: str) -> tuple[str, int] | None:
    """一項機器可讀的戰況變化（front_lines.mark，江湖紀錄加總過的）→ (畫面上的一句話, 對 viewer 的好壞 1／0／−1)；
    不是這種變化、或那條線內容裡已經沒有（can_draw_side_change）回 None，journal 就丟掉這枚標籤。
    journal 畫數值標籤時用；顏色在畫的那一刻才決定，紀錄裡存的東西不帶任何一方的立場。"""
    parsed = front_lines.unmark(change)
    if parsed is None or not can_draw_side_change(content, parsed[0]):
        return None
    trend_id, delta = parsed
    return front_text(content, trend_id, delta, seed), front_favour(content, viewer, trend_id, delta)


def humanize(content: Content, msgs: list[str], seed: str) -> list[str]:
    """一串訊息裡機器可讀的戰況變化換成一句話：同一條線的變動先加總（−1 與 −2 是 −3 一句話），放在那條線第一次出現的位置，
    加總為零的拿掉；那條線內容裡已經沒有的（can_draw_side_change）也拿掉，原文不外露。
    給 Game._log（回給呼叫端與存進 log 的話；管理者工具列的提示也是），沒有這種變化時原樣回傳。"""
    totals: dict[str, int] = {}
    for msg in msgs:
        parsed = front_lines.unmark(msg)
        if parsed is not None:
            totals[parsed[0]] = totals.get(parsed[0], 0) + parsed[1]
    if not totals:
        return msgs
    out: list[str] = []
    said: set[str] = set()
    for msg in msgs:
        parsed = front_lines.unmark(msg)
        if parsed is None:
            out.append(msg)
        elif can_draw_side_change(content, parsed[0]) and totals[parsed[0]] and parsed[0] not in said:
            said.add(parsed[0])
            out.append(front_text(content, parsed[0], totals[parsed[0]], seed))
    return out


def learn_skill(state: GameState, content: Content, skill_id: str) -> list[str]:
    """事件教的武學（追風步、混元一氣）：欄位空著就配上身，否則收進功法庫（library.store_art）。
    這裡不看持有上限，跟悟意境一樣——付了錢、奇遇給的東西不能因為滿了就憑空消失（武學與成長設計附錄 B.1）。
    已經會的（身上或功法庫）不重複收。"""
    skill = content.skills[skill_id]
    if skill_id in library.owned_arts(state):
        return []
    stored = library.store_art(state, content_art(skill.id, skill.name, skill.kind, skill.attribute, skill.quality, lean=skill.lean, affinity=skill.affinity))
    return [f"你習得了【{skill.name}】！"] + (stored if skill_id in state.player.arts else [])


def apply_effect(
    effect: Effect, state: GameState, content: Content, world: WorldStateStore,
    push: Callable[..., list[str]] | None = None, once: bool = False,
) -> list[str]:
    """套用一則效果。push 是玩家造成的大勢推動要交給誰處理（Game.push_trend：人數緩衝、每曆日上限、貢獻帳，
    呼叫時帶 source="event"）；沒給就照舊直接 change_trend（管理者、引導獎勵等沒有「玩家個人推動」的呼叫端）。
    once：這一則出自標了 once 的事件。它、或這一則效果這一下新立世界旗標（例：擊敗波才立 bocai_defeated），算一季只會發生一次的事，
    推大勢時帶 source="event_once"：規則關著的季不照季長縮放（FB-166，PM 2026-10-13；季再長也不會多發生一次）。"""
    p = state.player
    names = content.config.stat_names
    msgs: list[str] = []
    if effect.text:
        msgs.append(fill_marks(effect.text, state))
    for key, delta in effect.stats.items():  # 照實際動了多少寫、沒動就不寫（跟下面的情誼一樣）
        before = p.stats.get(key, 0)
        after = max(0, before + delta)
        capped = key in team.COMBAT_STATS and delta > 0 and after > content.config.stat_cap
        if capped:  # 五屬性每項最高 stat_cap（武學與成長設計 6.2）；已經超過的舊存檔不往下拉，只是不再加
            after = max(before, content.config.stat_cap)
        p.stats[key] = after
        if after != before:
            msgs.append(f"{names.get(key, key)} {after - before:+d}")
        if key in ("good", "evil"):
            from . import ranger  # noqa: PLC0415  ranger → rules：在函式裡 import，避免循環

            ranger.note_gain(state, content, key, after - before)  # 散人的遊俠名號照實際加了多少記帳
        if capped:  # 被上限夾掉了，玩家要知道是到頂、不是事件沒效果
            msgs.append(f"（{names.get(key, key)}已到頂 {content.config.stat_cap}）")
    if any(key in ("good", "evil") for key in effect.stats):
        msgs += insights.grant_by_name(state, content, world)  # 善名、惡名到門檻悟得浩然、血煞（只悟一次）
    for material_id, count in effect.materials.items():
        line = materials.grant(state, content, material_id, count)
        if line:
            msgs.append(line)
    for insight_id in effect.insights:
        msgs += insights.learn(state, content, world, insight_id)
    if effect.gear is not None:  # 奇遇給的寶物或良駒（裝備四欄 6.4）：自己一份亂數，不碰 Game.rng
        msgs += treasures.grant_effect(state, content, effect.gear, world.get_season_number())
    if effect.stamina:
        p.stamina = min(content.config.stamina_max, max(0.0, p.stamina + effect.stamina))
        msgs.append(f"體力 {'+' if effect.stamina > 0 else ''}{effect.stamina}")
    for character_id, delta in effect.affinity.items():  # 情誼（計畫 T5）：夾在 0～100，訊息寫實際動了多少，沒動就不寫
        before = p.affinities.get(character_id, 0)
        p.affinities[character_id] = max(0, min(100, before + renown.warmed(content, delta)))  # 加的放慢（Config.affinity_gain_scale）
        if p.affinities[character_id] != before:
            msgs.append(f"{content.characters[character_id].name}情誼 {p.affinities[character_id] - before:+d}")
    if effect.patron is not None:  # 豪強的靠山（晉升奇遇 4.2；正式版丙一）
        p.patron = effect.patron
    if (effect.donate_grain or effect.fs_fragments or effect.runic) and season_one(content, state.world):  # 黃巾的第 3、4 階奇遇（正式版丙二）：開關關著什麼都不做
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環
        from .wins import credit  # noqa: PLC0415  只引這個函式（同 push：apply_effect 的參數就叫 push）；wins → rules 延後 import

        for loc_id, base in effect.donate_grain.items():  # 捐糧：同護糧送到（Game._convoy_arrives）——記捐獻、記一次推動的貢獻；糧不夠、換算出 0 份就什麼都不記
            amount = foreshadow.need(content, base)
            lines = foreshadow.spend_grain(state, content, amount)
            if lines:
                msgs += lines
                key = f"{loc_id}:糧草"
                p.donations[key] = p.donations.get(key, 0) + amount
                week = calendar.point(state.world.time, content, state.world).week
                credit(p, content, state.world, week, content.config.contrib_per_push)
        for ref in effect.fs_fragments:  # 直接給片段：「鏈 id:片段序號」；不發傳聞
            chain_id, _, index = ref.rpartition(":")
            if index.isdecimal():
                msgs += foreshadow.grant_fragment(state, content, chain_id, int(index), world)
        p.runic_pieces += effect.runic
    if effect.event_mods:  # 一般伏筆（伏筆文件 4.4）：那件大事還沒結算才算；不寫字（暗中的）
        from . import timetable  # noqa: PLC0415  timetable → rules：在函式裡 import，避免循環

        for mod in effect.event_mods:
            if mod.event not in state.world.timeline:
                timetable.add_mod(state, content, mod.event, mod.side, mod.amount)
    if effect.summons_next is not None:  # 晉升奇遇演完一段：召見往下一段（正式版丙一）；放在 promote 前面，下一段的召見那一句先出
        from . import ranks  # noqa: PLC0415  ranks → rules：在函式裡 import，避免循環

        msgs += ranks.next_leg(state, content, effect.summons_next)
    if effect.promote is not None or effect.followers:  # 晉升奇遇（計畫 T5）：開關關著時 ranks 什麼都不做
        from . import ranks  # noqa: PLC0415  ranks → rules：在函式裡 import，避免循環

        if effect.promote is not None:
            msgs += ranks.promote(state, content, effect.promote)
        msgs += ranks.add_followers(state, content, effect.followers)
    p.flags |= set(effect.flags_add)
    p.flags -= set(effect.flags_remove)
    for skill_id in effect.learn_skills:
        msgs += learn_skill(state, content, skill_id)
    if effect.join_sect:
        sect = content.sects[effect.join_sect]
        p.sect = sect.id
        msgs.append(f"你拜入了{sect.name}！")
        owner = content.scenario.sect_owner(sect.id)
        if owner is not None and p.faction is None:
            p.faction = owner.id
            msgs.append(f"你從此是{owner.name}的人了。")
    if effect.leave_sect and p.sect:
        msgs.append(f"你叛出了{content.sects[p.sect].name}。")
        p.flags.add(f"叛出:{p.sect}")
        p.sect = None
    if effect.recruit:
        msgs += roster.recruit(state, content, world, effect.recruit)
    single = once or any(flag not in state.world.flags for flag in effect.world_flags_add)  # 旗標在下面才立：這裡看的是立之前
    for trend_id, delta in resolve_trends(content, state.world, effect.trend, state.player.location).items():
        # front 與戰線先照這一季的規則換成真的要推的線，再照舊交給 push（Game.push_trend，T3）或 change_trend
        source = "event_once" if single else "event"
        msgs += change_trend(state, content, trend_id, delta) if push is None else push(trend_id, delta, source=source)
    jade_seal_flag = content.scenario.jade_seal_flag
    seal_on = content.config.seal.enabled and bool(content.seal)  # 玉璽碎片開著：舊鏈不再寫跨季紀錄（玉璽碎片設計 11.2 第 2 條）
    newly_found_shard = (
        not seal_on and jade_seal_flag is not None and jade_seal_flag in effect.world_flags_add
        and jade_seal_flag not in state.world.flags
    )
    add_world_flags(state, effect.world_flags_add)
    add_marks(effect.marks, state, content)
    if effect.clue_items or effect.fs_counters:  # 伏筆的準備事件：開關關著時什麼都不給、不寫字（foreshadow.grant）
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環

        msgs += foreshadow.grant(state, content, effect.clue_items, effect.fs_counters)
    name = state.player.name  # 江湖史與玉璽碎片（天下大事）一律寫名號；只有下面的地方傳聞看匿名（傳聞分層設計第七節）
    if effect.rumor:
        text = effect.rumor.format(name=display_name(state), him=gender.pronoun(state))  # {him}：寫傳聞主角的他／她
        add_rumor(  # 玩家觸發的傳聞記在當時所在地：地方傳聞的單獨事件，觸發者可以選匿名（傳聞分層設計第七節）
            state, text, state.player.location, content=content, layer="local", named=not state.player.anonymous,
        )
        msgs.append(f"【江湖傳聞】{text}")
    if effect.chronicle:
        add_chronicle(state, effect.chronicle.format(name=name))
    if newly_found_shard:
        fragment_text = effect.chronicle.format(name=name) if effect.chronicle else f"{name}取得了傳國玉璽的一塊碎片。"
        fragment = world.record_jade_seal_fragment(name, content.scenario.name, fragment_text)
        if fragment is not None:
            msgs.append(f"🏺 【天下大事】{name}尋得傳國玉璽第 {fragment.number} 塊碎片！（{fragment.number}/{JADE_SEAL_FRAGMENT_COUNT} 已現世）")
    step = effect.story
    progress = p.storylines.get(step.line) if step is not None else None
    if progress is not None and progress.ending is None:  # 一條線的一步（storyline.py）：記號加上去、記下往哪裡，動作結束時 storyline.tick 才走
        for key, value in step.marks.items():
            progress.marks[key] = progress.marks.get(key, 0) + value
        if step.go:
            progress.go = step.go
    if step is not None and step.keepsake and step.keepsake not in p.keepsakes:  # 紀念物：線收了也給（例：交契之後才拿到的）
        p.keepsakes.append(step.keepsake)
        msgs.append(f"（收進行囊：{step.keepsake}）")
    if step is not None and step.keepsake_drop in p.keepsakes:
        p.keepsakes.remove(step.keepsake_drop)
    return msgs
