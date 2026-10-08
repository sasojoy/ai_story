"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、習得武學。"""
from __future__ import annotations

import math
import random
import re
from collections.abc import Callable
from typing import Literal, NamedTuple

from . import calendar, front_lines, insights, library, materials, roster, team  # 與 roster 互相 import：只能引入整個模組、呼叫時才取屬性，不能 from .roster import …
from .martial_arts import content_art
from .models import DEFAULT_SEASON_DAYS, FRONT_KEY, Check, Condition, Content, Effect, FactionDef, Trend
from .state import PLAYER, GameState, Rumor, RumorLayer, WorldState
from .world_state import JADE_SEAL_FRAGMENT_COUNT, WorldStateStore, season_length_days

DAY = 86400


def display_name(state: GameState) -> str:
    """地方傳聞裡的單獨事件寫的名字：選了「匿名行走」的人是「某位少俠」（傳聞分層第七節）。只有那裡看匿名——天下大事、
    陣營軍情、江湖史、排行榜一律寫名號（state.player.name），不要拿這個去寫那些（企劃者 2026-10-06）。"""
    return "某位少俠" if state.player.anonymous else state.player.name


def audience_bar(state: GameState, content: Content, companion_id: str) -> int:
    """這位人物此刻對你的求見門檻（武學與成長設計 9.1）：名望門檻（CharacterDef.audience_fame），投靠了他的陣營的人
    此刻的階（ranks.rank_of）每比第 1 階高一階抵 audience_rank_discount 點；投靠了但還沒晉升過的人一點都不抵。散人、敵對陣營，
    以及不在大勢人物表上的人物只看名望。最低 0。
    第 4 階只算這一週在任的（企劃者裁決 E4，2026-10-07）：有資格、沒在任（候缺）的算第 3 階；週一掉出席次，門檻跟著回去。
    rank_of 是唯一讀階的地方（不另讀 PlayerState.rank 或 qualified）；ranks 會 import rules，所以在函式裡 import。"""
    from . import ranks  # noqa: PLC0415  ranks → rules：在函式裡 import，避免循環

    bar = content.characters[companion_id].audience_fame
    figure = next((f for f in content.figures.values() if f.character == companion_id), None)
    p = state.player
    if figure is not None and p.faction is not None and p.faction == figure.faction:
        bar -= (ranks.rank_of(state) - 1) * content.config.audience_rank_discount
    return max(0, bar)


def can_meet(state: GameState, content: Content, companion_id: str) -> bool:
    """見得到這位大勢人物：名望到了他的求見門檻（audience_bar：名望，同陣營的階級可以抵一段），或是透過他的「結識」
    事件認識過（企劃者 2026-10-02 決定）。引擎的求見與交友對話、伏筆的對話片段（名望不夠的人改從行動偷聽，
    foreshadow.hear_after_action）都用這一個判斷，不要在別處再寫一份。"""
    p = state.player
    return f"結識:{companion_id}" in p.flags or p.stats.get("fame", 0) >= audience_bar(state, content, companion_id)


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
    """一個遊戲日有幾個世界秒：DAY × 季長 ÷ FULL_SEASON_DAYS（季長照 world 蓋的章；沒有章的舊季照 14 天）。"""
    return DAY * season_length_days(world, content) / FULL_SEASON_DAYS


def game_day(content: Content, world: WorldState, time: float | None = None) -> int:
    """世界秒 time（不給就是此刻）落在這一季的第幾個遊戲日（從 1 起）。上限的帳記的是這個號碼：記的是別的號碼就當前幾天的。"""
    t = world.time if time is None else time
    return int(t // day_seconds(content, world)) + 1


def day_ends(content: Content, world: WorldState, time: float | None = None) -> float:
    """time（不給就是此刻）所在的遊戲日結束、下一個遊戲日開始的那一刻（世界秒）：game_day 在這一刻剛好換成下一天
    （n × 一天的長度碰上浮點誤差時，往後挪到第一個真的換了日的值，寫出來的時刻跟真的換日的那一刻不會差一點）。"""
    day = game_day(content, world, time)
    end = day * day_seconds(content, world)
    while game_day(content, world, end) <= day:
        end = math.nextafter(end, math.inf)
    return end


def day_ends_text(content: Content, world: WorldState, time: float | None = None) -> str | None:
    """換日那一刻寫給玩家看：一律走 calendar.stamp_text——第一季是「第 3 週・週五 00:00」（point_text），
    開關關著是「第3天 00:00」。不要在別處自己拼時間。
    寫不出來時回 None，呼叫端改寫「這一季之內不會再…」（day-scale 審查 M2）：換日在收季那一刻或之後（最後一個遊戲日、管理者把
    季末提前），或在名義季長之後（管理者把季末延後：季曆只到最後一週週日 23:59，寫出來會是一個什麼都不會重算的時刻）。
    開關關著時「第N天 HH:MM」只寫到分：不是整分的換日（短的 beta 季）往後進位，寫出來的那一刻不會早於真的換日。"""
    from .world import season_end_time  # noqa: PLC0415  world → rules：在函式裡 import，避免循環

    end = day_ends(content, world, time)
    last = min(season_end_time(world, content), season_length_days(world, content) * DAY)
    if end >= last - calendar.EPS_SECONDS:
        return None
    if not calendar.season_one_on(world, content):
        end = math.ceil(end / calendar.MINUTE - calendar.EPS_MINUTES) * calendar.MINUTE
    return calendar.stamp_text(end, content, world)


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
    if cond.factions and p.faction not in cond.factions:
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
    if cond.night is not None or cond.week_min is not None or cond.week_max is not None:
        if content is None or not calendar.season_one_on(w, content):
            return False
        if cond.night is not None and calendar.is_night(w.time, content, w) != cond.night:
            return False
        week = calendar.point(w.time, content, w).week
        if (cond.week_min is not None and week < cond.week_min) or (cond.week_max is not None and week > cond.week_max):
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
    所以標籤講的和實際擲出來的不會對不起來。"""
    stat_value = team.check_value(state, content, world, PLAYER, check.stat)
    bonus = team.practice_bonus(state, content, check)
    gap = stat_value + bonus - check.difficulty
    return CheckOutlook(stat_value, bonus, gap, min(0.95, max(0.05, 0.5 + gap * 0.1)))


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
    return rule.line.replace("{who}", "你")


def roll_check(check: Check, state: GameState, content: Content, world: WorldStateStore, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state, content, world)


FREE_TEXT_MIN_RATE, FREE_TEXT_MAX_RATE = 5, 85  # 隨口應對的成功率夾在這之間：再會寫也不會穩贏，寫得爛也不會必敗
FREE_TEXT_PER_POINT = 4  # 相關屬性每比 5 高（低）1 點，成功率 +4（−4）


def free_text_rate(llm_rate: int, choice, state: GameState, content: Content, world: WorldStateStore) -> int:
    """隨口應對的成功率（百分比）：LLM 評的 0～100，加上本人這項屬性的修正（跟一般檢定一樣只看本人，choice.by 不再有作用），
    夾在 5～85。choice 是 models.FreeTextChoice。"""
    value = team.check_value(state, content, world, PLAYER, choice.stat)
    rate = round(llm_rate + (value - 5) * FREE_TEXT_PER_POINT)
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
    """把文字裡的 {marks:地點:痕跡} 換成這個痕跡目前的模糊人數。"""
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
        state.world.marks[key] = state.world.marks.get(key, 0) + n


def fail_stamina(amount: int, content: Content) -> int:
    """事件失敗另扣的體力（只縮扣的，不縮給的）乘 event_fail_stamina_scale、四捨五入（15 → 8、5 → 3；體力平衡提案第〇節）。"""
    if amount >= 0:
        return amount
    return -int(-amount * content.config.event_fail_stamina_scale + 0.5)


def failed(effect: Effect, content: Content) -> Effect:
    """檢定失敗、隨口應對失敗、劇情戰落敗（企劃者裁決 E6，2026-10-07）要套的 fail_effect：扣的體力照 fail_stamina 縮過。"""
    stamina = fail_stamina(effect.stamina, content)
    return effect if stamina == effect.stamina else effect.model_copy(update={"stamina": stamina})


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
    from . import atlas  # atlas → world → rules：在函式裡 import，避免循環

    region = None
    if content is not None and location is not None and location in content.locations:
        found = atlas.region_of(content, location)
        region = found.id if found is not None else None
    state.world.rumors.append(
        Rumor(time=state.world.time, text=text, location=location, layer=layer, region=region, named=named, faction=faction)
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
    return Ears(faction=p.faction, name=p.name, layered=True, regions=here_regions(state, content), since=since)


def audible(rumor: Rumor, ears: Ears) -> bool:
    """這個人聽不聽得到這則傳聞（傳聞分層設計第二、三節）。見聞頁、沿途打聽、輿圖的 ✦ 與地點詳情、龍頭人物的近況、
    「你不在的時候」都照這一條，不要在別處另寫一份：
    - 陣營軍情只給那個陣營的人（散人沒有）、個人線索只給那個名號、天下大事人人都聽得到；
    - 地方傳聞（第一季的規則開著時）只給此刻人在那個大區的人，而且只留傳聞板上最近幾天的；沒有大區的（地圖沒有大區、發生地不明）
      人人都聽得到，但一樣只留板上的。
    - 陣營軍情一定要寫是哪個陣營、個人線索一定要寫是誰（layer 與欄位對不上時 fail closed：沒有人聽得到）。
    開關關著（beta）時只看陣營與名號，跟以前的 can_hear 一模一樣。"""
    if rumor.faction not in (None, ears.faction) or rumor.character not in (None, ears.name):
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
# 內容只寫一份（三條戰線、豪強割據、front 鍵）。第一季的規則沒開時（開關關著，或這一季開季時沒蓋「開」的章），
# 下面的換算讓規則與畫面跟 beta 那一季一模一樣：三條戰線與 front 都算黃巾聲勢，第一季才有的其他線（豪強割據）不存在。

HUANGJIN = "huangjin"  # 黃巾聲勢：開關開著時是三條戰線的加權（Trend.derived）
GEJU = "geju"  # 豪強割據


def season_one(content: Content, world: WorldState) -> bool:
    """第一季濃縮版的規則在這一季開了沒：開關開著，而且這一季開季時也蓋了「開」的章（T2 的 calendar.season_one_on）。
    開關打開時還在跑的 beta 那一季照舊用 beta 的規則，新規則從開關打開後開的下一季起算（PM 2026-10-04）。"""
    return calendar.season_one_on(world, content)


OffKind = Literal["thresholds", "storylines", "battles", "events", "milestones"]


def season_one_off(content: Content, world: WorldState, kind: OffKind) -> frozenset[str]:
    """第一季不觸發的那一種 beta 內容（Scenario.season_one_off 的 thresholds／storylines／battles／events／milestones）的 id。
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
    """這條線在這一季的規則下存在嗎：第一季的規則沒開時，第一季才有的線（Trend.season_one）不顯示、不推。"""
    trend = _trend(content, trend_id)
    return trend is not None and (season_one(content, world) or not trend.season_one)


def pushable(content: Content, world: WorldState, trend_id: str) -> bool:
    """可以直接推的線：存在，而且不是第一季規則下的衍生線（黃巾聲勢由三條戰線合成）。"""
    trend = _trend(content, trend_id)
    return trend_shown(content, world, trend_id) and not (trend.derived and season_one(content, world))


def resolve_trend(content: Content, world: WorldState, key: str, location: str | None = None) -> str | None:
    """內容寫的大勢鍵 → 這一次真的要推（或讀）的那條線；None＝這次不推。
    第一季的規則開著（season_one）：front 是 location 所在大區的戰線（洛陽沒有戰況→None），其他照寫。
    沒開（beta 照舊）：front 與三條戰線都算它們合成的那條線（黃巾聲勢），第一季才有的其他線（豪強割據）→None。"""
    if season_one(content, world):
        if key == FRONT_KEY:
            return front_of(content, location) if location is not None else None
        return key
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
    """同 world_trend_value，讀這個角色看到的那一份賽季。讀戰線、黃巾聲勢、割據一律走這裡。"""
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
    """在亂局裡的戰線 id（照 front_ids 的順序）。geju_tick 的漲落、江湖頁圖卡的「亂局」標與亂局帶、態勢那一行、
    見聞→大勢的割據說明，讀的都是這一份（FB-065），所以畫面上寫的條數與漲落的方向跟實際漲落永遠一致。"""
    return [front for front in front_ids(content) if in_chaos(state, content, front)]


def chaos_note(state: GameState, content: Content, players: int | None = None) -> str:
    """豪強割據現在為什麼漲或落（FB-065），江湖頁態勢那一行（「豪強 32（…）」）與見聞→大勢的割據說明共用這一句：
    有戰線在亂局就漲（geju_tick：每條每曆日漲 geju_chaos_per_day × 人數係數），一條都沒有就落（每曆日落 geju_calm_per_day）。
    條數寫阿拉伯數字；只寫方向與條數，不寫速度，也不寫是哪幾條（圖卡自己標）。
    漲速乘人數係數（geju_rise_factor）：名冊空著（players 是 0）時有戰線在亂局也一點不漲，這句不能說漸長，改說還沒有人
    投靠、暫時不動（FB-065 M1）。每曆日的變動讀 geju_per_day，跟 geju_tick 同一個算式；players 是 None＝不知道名冊，
    不縮放，照舊說漸長。回落不乘係數，所以名冊空著、沒有戰線在亂局時還是漸消。"""
    count = len(chaos_fronts(state, content))
    if not count:
        return "沒有戰線在亂局，割據漸消"
    if geju_per_day(state, content, players) > 0:
        return f"{count} 條戰線在亂局，割據漸長"
    if geju_rise_factor(content, players) == 0:
        return f"{count} 條戰線在亂局，但還沒有人投靠，割據暫時不動"
    return f"{count} 條戰線在亂局，割據不動"  # 名冊有人，是設定把漲速調成 0：不能怪名冊


_COUNT_WORDS = "零一二三四五六七八九十"


def stance_sum_note(content: Content) -> str:
    """官軍、黃巾的態勢是幾條戰況合起來的（FB-065；權重不印）：「三條戰線合計」。"""
    count = len(front_ids(content))
    return f"{_COUNT_WORDS[count] if count < len(_COUNT_WORDS) else count}條戰線合計"


def stances(state: GameState, content: Content) -> dict[str, int]:
    """三方態勢（第一季設計 4.4）：官軍＝100－黃巾聲勢，黃巾＝黃巾聲勢，豪強＝豪強割據。"""
    huangjin = trend_value(state, content, HUANGJIN)
    return {"guan": 100 - huangjin, "huang": huangjin, "haoqiang": trend_value(state, content, GEJU)}


_STANCE_SIDES = ("guan", "huang", "haoqiang")
_STANCE_NAMES = {"guan": "官軍", "huang": "黃巾", "haoqiang": "豪強"}  # 態勢卡上三方的叫法（web/app.js 的 STANCE_NAMES 同一份；陣營本身叫黃巾軍、地方豪強）
_STANCE_COMPLEMENT = {"guan": "huang", "huang": "guan"}  # 官軍＝100－黃巾：兩邊互為補數；豪強沒有另一方可換


def stance_rule_note(state: GameState, content: Content) -> str:
    """態勢卡底下那一句收季規則（第一季設計 4.4；正式版辛）：門檻從第一季結局算，不寫死。
    每一個決定性結局（有 stance_min／stance_max 的）換成「哪一方到幾分」：stance_min 的那一方到那個值；stance_max 的黃巾 ≤ 15
    就是官軍 ≥ 85（官軍與黃巾互為補數）。同一方有幾個門檻取最小的。三方都有、數字也一樣（這一季都是 85）才寫「哪一方的態勢一到 85」；
    數字不一樣或只有幾方有門檻，就照每一方寫自己的（「官軍一到 85、黃巾一到 85、豪強一到 90」）；換不出「哪一方到幾分」的
    （豪強的 stance_max，或兩個條件合成一種的結局）就寫一句不帶數字的話，不報算不出來的數字。
    第 decisive_from_week 週以前寫「第 N 週起」，之後不寫。沒有決定性結局時是空字串。"""
    reach: dict[str, int] = {}  # 一方 → 它到幾分就收季
    decisive, unclear = False, False
    for e in content.scenario.endings:
        if not e.season_one or not (e.stance_min or e.stance_max):
            continue
        decisive = True
        if len(e.stance_min) + len(e.stance_max) != 1:  # 兩個條件合成一種：不是「哪一方到幾分」
            unclear = True
            continue
        for side, bar in e.stance_min.items():
            reach[side] = min(reach.get(side, 100), bar)
        for side, bar in e.stance_max.items():
            other = _STANCE_COMPLEMENT.get(side)
            if other is None:  # 豪強 ≤ 幾分：換不出另一方到幾分
                unclear = True
            else:
                reach[other] = min(reach.get(other, 100), 100 - bar)
    if not decisive:
        return ""
    ending = "這一季當場收場；否則到季末比高低。"
    if unclear or not reach:
        rule = f"哪一方的態勢到了決勝的門檻，{ending}"
    elif set(reach) == set(_STANCE_SIDES) and len(set(reach.values())) == 1:
        rule = f"哪一方的態勢一到 {min(reach.values())}，{ending}"
    else:
        rule = "、".join(f"{_STANCE_NAMES[side]}一到 {reach[side]}" for side in _STANCE_SIDES if side in reach) + f"，{ending}"
    week = calendar.point(state.world.time, content, state.world).week
    start = content.config.decisive_from_week
    return f"第 {start} 週起，{rule}" if week < start else rule


def geju_rise_factor(content: Content, players: int | None) -> float:
    """割據漲速的人數係數（企劃者 2026-10-05，測試階段「依據人數等比例調整」）：min(1, players ÷ geju_full_players)。
    players 是這一季投靠了陣營的人數（投靠名冊，真人與假人一樣算）；沒人投靠就是 0（割據不漲），湊滿 geju_full_players 人
    以上是 1（設計的速度）。players 是 None＝不知道名冊（沒有資料庫可查的純函式呼叫）：不縮放，照設計的速度。"""
    if players is None:
        return 1.0
    return min(1.0, max(0, players) / content.config.geju_full_players)


def geju_per_day(state: GameState, content: Content, players: int | None = None) -> float:
    """割據每曆日的自然變動（漲為正、落為負）：每有一條戰線在亂局漲 geju_chaos_per_day × 人數係數（geju_rise_factor），
    一條都沒有就落 geju_calm_per_day（回落不乘係數）。geju_tick 實際漲落與畫面上的說明（chaos_note）讀的是這同一個算式，
    所以畫面說漲就是在漲、說不動就是不動（FB-065 M1）。players 的意思同 geju_rise_factor（None＝不縮放）。"""
    cfg = content.config
    chaos = len(chaos_fronts(state, content))
    return chaos * cfg.geju_chaos_per_day * geju_rise_factor(content, players) if chaos else -cfg.geju_calm_per_day


def geju_tick(state: GameState, content: Content, cal_hours: float, players: int | None = None) -> None:
    """豪強割據的自然漲落（第一季設計 4.2）：每有一條戰線在亂局，每曆日漲 geju_chaos_per_day × 人數係數
    （geju_rise_factor：這一季投靠名冊 players 人，占 geju_full_players 的比例，至多 1）；三條都穩下來時每曆日
    落 geju_calm_per_day（回落不乘係數）。不足一點的累積在 trend_accum["geju"]。背景推動，不回傳訊息（同虛擬玩家）。
    由 T2 的 world.season_hour 每曆時呼叫一次（cal_hours＝1），players 由 advance_world_state 每次推進查一次名冊帶進來。
    開關關著、劇本沒有割據、或地圖沒有戰線時什麼都不做。"""
    fronts = front_ids(content)
    if not season_one(content, state.world) or _trend(content, GEJU) is None or not fronts:
        return
    per_day = geju_per_day(state, content, players)  # 畫面上寫的條數與漸長／不動／漸消（chaos_note）讀同一個算式
    w = state.world
    pending = w.trend_accum.get(GEJU, 0.0) + per_day * cal_hours / 24
    whole = int(pending + (1e-9 if pending > 0 else -1e-9))  # 往零取整；容一點浮點誤差，24 個 1/24 才剛好湊成 1
    w.trend_accum[GEJU] = pending - whole
    if whole:
        change_trend(state, content, GEJU, whole, reveal=False)


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

    第一季的規則開著時（season_one），三條戰線與豪強割據的變動不寫數字（FB-064）：回機器可讀的「大勢@<線 id> ±N」
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
    after = min(100, max(0, before + delta))
    w.trends[trend_id] = after
    actual = after - before
    if actual:
        recompute_trends(w, content)  # 開關開著時推了戰線，黃巾聲勢跟著重算
        if season_one(content, w) and is_side_trend(content, trend_id):
            # FB-064：戰線與豪強割據不給玩家看數字（看不出是哪一邊、也看不出好壞）。這裡回機器可讀的寫法，
            # 江湖紀錄照舊把同一條線的變動加總；畫出來的那一刻才換成一句話、照看的人的陣營上色（front_chip、humanize）
            msgs.append(front_lines.mark(trend_id, actual))
        else:
            msgs.append(f"（{trend_name(content, trend_id)} {'+' if actual >= 0 else ''}{actual}）")
    return msgs


# ── 戰況變化的說法（FB-064）──────────────────────────────────


def is_side_trend(content: Content, trend_id: str) -> bool:
    """變動要寫成「哪一方佔了便宜」的線：三條戰線與豪強割據。其他的線（玉璽線索、開關關著時的黃巾聲勢）照舊寫數字。"""
    return trend_id == GEJU or trend_id in front_ids(content)


def can_draw_side_change(content: Content, trend_id: str) -> bool:
    """這條線的戰況變化畫得出來嗎：內容裡有這條線，而且它還是戰線或豪強割據。紀錄裡存的是機器可讀的寫法，存檔可能比內容舊
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
    句子照變動的大小（front_lines.band_of）在 content/front_lines.json 挑；割據：整句話（已經有「豪強」，不再接陣營名）。
    一段有好幾句時照 seed 與線、段雜湊挑一句，不動引擎的亂數；seed 通常是那則紀錄的時間，同一則永遠同一句。"""
    lines = content.front_lines
    if trend_id == GEJU:
        key = "up" if delta > 0 else "down"
        return front_lines.pick(lines.geju[key], f"{seed}|{trend_id}|{key}")
    side = _beneficiary(content, trend_id, delta)
    band = front_lines.band_of(delta)
    pool = (lines.by_side.get(side.id, {}).get(band) if side is not None else None) or lines.generic[band]
    name = lines.sides.get(side.id, side.name) if side is not None else ""
    phrase = front_lines.pick(pool, f"{seed}|{trend_id}|{band}")
    return f"{trend_name(content, trend_id)}：{name}{phrase}"


def front_favour(content: Content, viewer: str | None, trend_id: str, delta: int) -> int:
    """這一次變動對看畫面的人（viewer＝他的陣營 id，散人是 None）是好事（1）、壞事（−1）還是無關（0）：
    他的陣營對這條線有目標（goals）時，方向一致是好事、相反是壞事；沒有目標的（散人、戰線上的豪強、割據上的官軍與黃巾）一律 0。"""
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
    stored = library.store_art(state, content_art(skill.id, skill.name, skill.kind, skill.attribute, skill.quality))
    return [f"你習得了【{skill.name}】！"] + (stored if skill_id in state.player.arts else [])


def apply_effect(
    effect: Effect, state: GameState, content: Content, world: WorldStateStore,
    push: Callable[..., list[str]] | None = None,
) -> list[str]:
    """套用一則效果。push 是玩家造成的大勢推動要交給誰處理（Game.push_trend：人數緩衝、每曆日上限、貢獻帳，
    呼叫時帶 source="event"）；沒給就照舊直接 change_trend（管理者、引導獎勵等沒有「玩家個人推動」的呼叫端）。"""
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
    if effect.stamina:
        p.stamina = min(content.config.stamina_max, max(0.0, p.stamina + effect.stamina))
        msgs.append(f"體力 {'+' if effect.stamina > 0 else ''}{effect.stamina}")
    for character_id, delta in effect.affinity.items():  # 情誼（計畫 T5）：夾在 0～100，訊息寫實際動了多少，沒動就不寫
        before = p.affinities.get(character_id, 0)
        p.affinities[character_id] = max(0, min(100, before + delta))
        if p.affinities[character_id] != before:
            msgs.append(f"{content.characters[character_id].name}情誼 {p.affinities[character_id] - before:+d}")
    if effect.patron is not None:  # 豪強的靠山（晉升奇遇 4.2；正式版丙一）
        p.patron = effect.patron
    if (effect.donate_grain or effect.fs_fragments or effect.runic) and season_one(content, state.world):  # 黃巾的第 3、4 階奇遇（正式版丙二）：開關關著什麼都不做
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環
        from .push import add_contribution  # noqa: PLC0415  只引這個函式：不能 import push 整個模組，apply_effect 的參數就叫 push

        for loc_id, base in effect.donate_grain.items():  # 捐糧：同護糧送到（Game._convoy_arrives）——記捐獻、記一次推動的貢獻；糧不夠、換算出 0 份就什麼都不記
            amount = foreshadow.need(content, base)
            lines = foreshadow.spend_grain(state, content, amount)
            if lines:
                msgs += lines
                key = f"{loc_id}:糧草"
                p.donations[key] = p.donations.get(key, 0) + amount
                week = calendar.point(state.world.time, content, state.world).week
                add_contribution(p, week, content.config.contrib_per_push)
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
        owner = next((f for f in content.scenario.factions if sect.id in f.sects), None)
        if owner is not None and p.faction is None:
            p.faction = owner.id
            msgs.append(f"你從此是{owner.name}的人了。")
    if effect.leave_sect and p.sect:
        msgs.append(f"你叛出了{content.sects[p.sect].name}。")
        p.flags.add(f"叛出:{p.sect}")
        p.sect = None
    if effect.recruit:
        msgs += roster.recruit(state, content, world, effect.recruit)
    for trend_id, delta in resolve_trends(content, state.world, effect.trend, state.player.location).items():
        # front 與戰線先照這一季的規則換成真的要推的線，再照舊交給 push（Game.push_trend，T3）或 change_trend
        msgs += change_trend(state, content, trend_id, delta) if push is None else push(trend_id, delta, source="event")
    jade_seal_flag = content.scenario.jade_seal_flag
    newly_found_shard = (
        jade_seal_flag is not None and jade_seal_flag in effect.world_flags_add and jade_seal_flag not in state.world.flags
    )
    add_world_flags(state, effect.world_flags_add)
    add_marks(effect.marks, state, content)
    if effect.clue_items or effect.fs_counters:  # 伏筆的準備事件：開關關著時什麼都不給、不寫字（foreshadow.grant）
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環

        msgs += foreshadow.grant(state, content, effect.clue_items, effect.fs_counters)
    name = state.player.name  # 江湖史與玉璽碎片（天下大事）一律寫名號；只有下面的地方傳聞看匿名（傳聞分層設計第七節）
    if effect.rumor:
        text = effect.rumor.format(name=display_name(state))
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
    return msgs
