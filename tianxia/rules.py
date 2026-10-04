"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、習得武學。"""
from __future__ import annotations

import random
import re
from collections.abc import Callable
from typing import Literal

from . import calendar, materials, roster, team  # 與 roster 互相 import：只能引入整個模組、呼叫時才取屬性，不能 from .roster import …
from .models import FRONT_KEY, Check, Condition, Content, Effect, Trend
from .state import PLAYER, GameState, Rumor, RumorLayer, WorldState
from .world_state import JADE_SEAL_FRAGMENT_COUNT, WorldStateStore

DAY = 86400


def display_name(state: GameState) -> str:
    return "某位少俠" if state.player.anonymous else state.player.name


def current_day(state: GameState) -> int:
    """賽季第幾天（從 1 開始）。"""
    return int(state.world.time // DAY) + 1


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
    known_skills = {p.member.neigong_id, p.member.wugong_id} - {None}
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


def check_chance(check: Check, state: GameState, content: Content, world: WorldStateStore) -> float:
    """出手者的屬性每高於難度 1 點，成功率 +10%；範圍 5%～95%。"""
    key = team.check_actor(state, content, world, check)
    value = team.check_value(state, content, world, key, check.stat)
    return min(0.95, max(0.05, 0.5 + (value - check.difficulty) * 0.1))


def roll_check(check: Check, state: GameState, content: Content, world: WorldStateStore, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state, content, world)


FREE_TEXT_MIN_RATE, FREE_TEXT_MAX_RATE = 5, 85  # 隨口應對的成功率夾在這之間：再會寫也不會穩贏，寫得爛也不會必敗
FREE_TEXT_PER_POINT = 4  # 相關屬性每比 5 高（低）1 點，成功率 +4（−4）


def free_text_rate(llm_rate: int, choice, state: GameState, content: Content, world: WorldStateStore) -> int:
    """隨口應對的成功率（百分比）：LLM 評的 0～100，加上屬性修正（照 choice.by 取出手者，跟一般檢定同一個函式），
    夾在 5～85。choice 是 models.FreeTextChoice。"""
    key = team.check_actor(state, content, world, choice)
    value = team.check_value(state, content, world, key, choice.stat)
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


def add_marks(marks: dict[str, int], state: GameState) -> None:
    """留下地方痕跡：同一個人對同一個痕跡，同一個遊戲日只算第一次（不讓一個人刷出整條變化）。"""
    day = current_day(state)
    for key, n in marks.items():
        if state.player.mark_days.get(key) == day:
            continue
        state.player.mark_days[key] = day
        state.world.marks[key] = state.world.marks.get(key, 0) + n


def check_who(check: Check, state: GameState, content: Content, world: WorldStateStore) -> str:
    """選項與結果上寫的出手者：本人檢定寫「本人」；隊伍檢定寫「某某出手」，派出的是本人時寫「本人出手」。"""
    if check.by == "self":
        return "本人"
    key = team.check_actor(state, content, world, check)
    return "本人出手" if key == PLAYER else f"{team.member_name(state, content, key)}出手"


def add_rumor(
    state: GameState, text: str, location: str | None = None, *, content: Content | None = None,
    layer: RumorLayer = "world", named: bool = True,
) -> None:
    """記一則傳聞（傳聞分層設計第二節）。給了 content 與地點時，順便記下地點所在的大區。
    第 1 期只先把資料記對；誰看得到哪一層，是傳聞分層的規則實作（線上架構第 2 期之後）。"""
    from . import atlas  # atlas → world → rules：在函式裡 import，避免循環

    region = None
    if content is not None and location is not None and location in content.locations:
        found = atlas.region_of(content, location)
        region = found.id if found is not None else None
    state.world.rumors.append(
        Rumor(time=state.world.time, text=text, location=location, layer=layer, region=region, named=named)
    )


def add_chronicle(state: GameState, text: str) -> None:
    state.world.chronicle.append(Rumor(time=state.world.time, text=text))


def trend_name(content: Content, trend_id: str) -> str:
    return next(t.name for t in content.scenario.trends if t.id == trend_id)


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


def recompute_derived(state: GameState, content: Content) -> None:
    """同 recompute_trends，對這個角色看到的那一份賽季。"""
    recompute_trends(state.world, content)


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


def stances(state: GameState, content: Content) -> dict[str, int]:
    """三方態勢（第一季設計 4.4）：官軍＝100－黃巾聲勢，黃巾＝黃巾聲勢，豪強＝豪強割據。"""
    huangjin = trend_value(state, content, HUANGJIN)
    return {"guan": 100 - huangjin, "huang": huangjin, "haoqiang": trend_value(state, content, GEJU)}


def geju_tick(state: GameState, content: Content, cal_hours: float) -> None:
    """豪強割據的自然漲落（第一季設計 4.2）：每有一條戰線在亂局，每曆日漲 geju_chaos_per_day；三條都穩下來時每曆日
    落 geju_calm_per_day。不足一點的累積在 trend_accum["geju"]。背景推動，不回傳訊息（同虛擬玩家）。
    由 T2 的 world.season_hour 每曆時呼叫一次（cal_hours＝1）。開關關著、劇本沒有割據、或地圖沒有戰線時什麼都不做。"""
    fronts = front_ids(content)
    if not season_one(content, state.world) or _trend(content, GEJU) is None or not fronts:
        return
    cfg = content.config
    chaos = sum(1 for front in fronts if in_chaos(state, content, front))
    per_day = chaos * cfg.geju_chaos_per_day if chaos else -cfg.geju_calm_per_day
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
    所以背景推動依然維持安靜，不會洗版；只有玩家自己選擇/打贏的那一刻才會顯示。"""
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
        msgs.append(f"（{trend_name(content, trend_id)} {'+' if actual >= 0 else ''}{actual}）")
    return msgs


def learn_skill(state: GameState, content: Content, skill_id: str) -> list[str]:
    """每人最多學一門內功、一門武學（設計文件六.4）：對應的欄位已經有人時直接跳過，不覆蓋。"""
    member = state.player.member
    skill = content.skills[skill_id]
    slot = "neigong_id" if skill.kind == "內功" else "wugong_id"
    if getattr(member, slot) == skill_id:
        return []
    if getattr(member, slot) is not None:
        return [f"你已經學了一門{skill.kind}，【{skill.name}】這次先無緣習得。"]
    setattr(member, slot, skill_id)
    setattr(member, slot.replace("_id", "_level"), 1)
    return [f"你習得了【{skill.name}】！"]


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
    for key, delta in effect.stats.items():
        p.stats[key] = max(0, p.stats.get(key, 0) + delta)
        msgs.append(f"{names.get(key, key)} {'+' if delta >= 0 else ''}{delta}")
    for material_id, count in effect.materials.items():
        line = materials.grant(state, content, material_id, count)
        if line:
            msgs.append(line)
    if effect.stamina:
        p.stamina = min(content.config.stamina_max, max(0.0, p.stamina + effect.stamina))
        msgs.append(f"體力 {'+' if effect.stamina > 0 else ''}{effect.stamina}")
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
    add_marks(effect.marks, state)
    if effect.clue_items or effect.fs_counters:  # 伏筆的準備事件：開關關著時什麼都不給、不寫字（foreshadow.grant）
        from . import foreshadow  # noqa: PLC0415  foreshadow → rules：在函式裡 import，避免循環

        msgs += foreshadow.grant(state, content, effect.clue_items, effect.fs_counters)
    name = display_name(state)
    if effect.rumor:
        text = effect.rumor.format(name=name)
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
