"""名聲（核心玩法重整第 3 塊，docs/superpowers/specs/2026-10-15-名聲-design.md）：人人兩個稱號，名望稱號（五段）與善惡稱號（俠、寇各四段）。

名望＝江湖上多少人認得你；善名、惡名＝你是怎樣的人（企劃者定）。名望不加戰力。
純規則：段、稱號、門檻、季長倍數、名望那一半的折扣、得失後面的差距、跨段比對、說明卡的資料。開關都在 Config.renown（RenownTuning）；
titles 關著時這裡每個函式都回「沒有」（段 0、空清單、None、倍數 1），其他開關要 titles 開著才有作用（on）。
門檻乘季長倍數：開季時蓋進 WorldState.renown_scale（world_state.stamp_season），這裡只讀那一欄（scale）。
只 import models、state、gender、world_state；rules、ranger、territory、team、bounties、arena……反過來呼叫它。"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import gender
from .models import Content
from .state import GameState, RenownSeen, WorldState

FAME_TITLES = ("無名小卒", "小有名氣", "名動一方", "威震州郡", "天下聞名")  # 第 0 段只寫在說明卡上，狀態列不寫
PATHS = ("俠", "寇")
VIRTUE_TITLES: dict[str, tuple[str, ...]] = {  # 第 0 段沒有稱號
    "俠": ("", "江湖遊俠", "一方豪俠", "州郡大俠", "天下名俠"),
    "寇": ("", "綠林好漢", "江湖巨寇", "州郡大盜", "天下大盜"),
}
FEMALE_TITLES = {"綠林好漢": "綠林女傑"}  # 女的換字（PM 2026-10-12）：只換寫死是男子的那幾個，其餘不分男女
BOOKS = {"俠": "good", "寇": "evil"}  # 走哪一條路看哪一本帳
_CN = "〇一二三四五六七八九"


def on(content: Content, switch: str = "titles") -> bool:
    """這一樣開著沒：titles 關著時一律沒有（設計第八節：其他開關都要 titles 開著才有作用）。"""
    cfg = content.config.renown
    return cfg.titles and (switch == "titles" or bool(getattr(cfg, switch)))


def scale(world: WorldState) -> float:
    """門檻乘幾倍：開季時蓋的章（world_state.stamp_season）；沒有章（上線那一刻正在跑的季、scale 關著）是 1。"""
    return world.renown_scale or 1.0


def _bars(base: list[int], world: WorldState) -> list[int]:
    k = scale(world)
    return [max(1, int(b * k + 0.5)) for b in base]  # 四捨五入照專案的寫法（round 逢 .5 取偶數）


def fame_bars(content: Content, world: WorldState) -> list[int]:
    """名望第 1～4 段的門檻（這一季乘過倍數）。"""
    return _bars(content.config.renown.fame_thresholds, world)


def virtue_bars(content: Content, world: WorldState) -> list[int]:
    """善惡第 1～4 段的門檻（沿用遊俠名號的 Config.ranger.thresholds，這一季乘過倍數）。"""
    return _bars(content.config.ranger.thresholds, world)


def tier_of(value: int, bars: list[int]) -> int:
    return sum(1 for need in bars if value >= need)


def fame_tier(state: GameState, content: Content) -> int:
    """名望第幾段（0～4）；開關關著是 0。"""
    if not on(content):
        return 0
    return tier_of(state.player.stats.get("fame", 0), fame_bars(content, state.world))


def path(state: GameState) -> str:
    """走哪一條路：惡名比善名高是寇，其餘（一樣多也算）是俠（設計 2.2）。"""
    st = state.player.stats
    return "寇" if st.get("evil", 0) > st.get("good", 0) else "俠"


def virtue_value(state: GameState) -> int:
    """稱號照哪一個數算：走俠看善名、走寇看惡名。"""
    return state.player.stats.get(BOOKS[path(state)], 0)


def virtue_tier(state: GameState, content: Content) -> int:
    """善惡第幾段（0～4）；開關關著是 0。"""
    if not on(content):
        return 0
    return tier_of(virtue_value(state), virtue_bars(content, state.world))


def named(title: str, state: GameState) -> str:
    """稱號照性別換字（綠林好漢 → 綠林女傑）。"""
    return FEMALE_TITLES.get(title, title) if gender.female(state) else title


def fame_title(state: GameState, content: Content) -> str | None:
    t = fame_tier(state, content)
    return FAME_TITLES[t] if t > 0 else None


def virtue_title(state: GameState, content: Content) -> str | None:
    t = virtue_tier(state, content)
    return named(VIRTUE_TITLES[path(state)][t], state) if t > 0 else None


def titles(state: GameState, content: Content, fame_from: int = 1) -> list[str]:
    """稱號的短版：名望（fame_from 段起才寫：狀態列、玩家卡第 1 段起，決戰名單名動一方起）在前、善惡（第 1 段起）在後；沒有的不寫。"""
    out = []
    t = fame_tier(state, content)
    if t >= fame_from and t > 0:
        out.append(FAME_TITLES[t])
    virtue = virtue_title(state, content)
    if virtue:
        out.append(virtue)
    return out


def meets(state: GameState, content: Content, way: str, tier: int) -> bool:
    """走 way 那一條路、到第 tier 段了沒（俠寇選項、正邪武學、官府通緝共用）。開關關著一律不成立。"""
    return path(state) == way and virtue_tier(state, content) >= tier


def discount_word(factor: float) -> str:
    """0.94 → 「九四折」、0.9 → 「九折」、1.2 → 「貴兩成」。"""
    pct = int(factor * 100 + 0.5)
    if pct < 100:
        tens, ones = divmod(pct, 10)
        return f"{_CN[tens]}{_CN[ones] if ones else ''}折"
    extra = pct - 100
    if extra % 10:
        return f"貴{extra}%"
    return f"貴{'兩' if extra == 20 else _CN[extra // 10]}成"


def gain(state: GameState, content: Content, key: str, n: int) -> list[str]:
    """加（n 是負的就扣）名望、善名或惡名，不低於 0；回寫進紀錄的那一行（實際動了多少，沒動是空的）。
    引擎直接加名望的地方一律走這裡（設計 3.2）；事件照舊走 rules.apply_effect。差距在動作結束時統一接（annotate）。
    不看開關：關著時照舊加、照舊寫那一行（跟改之前一字不差）。"""
    p = state.player
    before = p.stats.get(key, 0)
    after = max(0, before + n)
    p.stats[key] = after
    return [f"{content.config.stat_names.get(key, key)} {after - before:+d}"] if after != before else []


def price_factor(state: GameState, content: Content) -> float:
    """名望那一半的店家折扣（設計 4.1）：第 1～4 段各一個倍數；沒到、開關關著是 1。地盤那一半另外乘（territory.price_here）。"""
    t = fame_tier(state, content) if on(content, "discount") else 0
    return content.config.renown.discounts[t - 1] if t > 0 else 1.0


# ── 得失後面的差距（設計 6.4）──────────────────────────────

_PLAIN = re.compile(r"^(\S+) ([+-])(\d+)$")  # 還沒接過差距的「名望 +1」


def gap_note(state: GameState, content: Content, key: str) -> str:
    """名望、善名、惡名加了之後接的那一句：離下一段還差多少；已經到頂寫「已是…」；加的不是稱號照著算的那一本帳時，說稱號照哪一本算。"""
    names = content.config.stat_names
    st = state.player.stats
    if key == "fame":
        t, bars = fame_tier(state, content), fame_bars(content, state.world)
        return f"（已是{FAME_TITLES[4]}）" if t >= 4 else f"（離「{FAME_TITLES[t + 1]}」還差 {bars[t] - st.get('fame', 0)}）"
    way = path(state)
    mine = BOOKS[way]
    if key != mine:
        mine_name, key_name = names.get(mine, mine), names.get(key, key)
        if st.get(mine, 0) > st.get(key, 0):
            return f"（{mine_name}還比{key_name}高，稱號照{mine_name}算）"
        return f"（稱號照{mine_name}算，{key_name}要比{mine_name}高才換路）"
    t, bars = virtue_tier(state, content), virtue_bars(content, state.world)
    if t >= 4:
        return f"（已是{named(VIRTUE_TITLES[way][4], state)}）"
    return f"（離「{named(VIRTUE_TITLES[way][t + 1], state)}」還差 {bars[t] - virtue_value(state)}）"


def annotate(changes: list[str], state: GameState, content: Content) -> list[str]:
    """同一個標籤（名望、善名、惡名）的數字合成一行、排在第一次出現的地方；總和是正的接差距，扣的不接，總和 0 的拿掉。
    其他行照原樣；已經接過差距的行（後面有括號）不動，同一下叫兩次也一樣。開關關著原樣回傳。"""
    if not on(content):
        return list(changes)
    keys = {content.config.stat_names.get(k, k): k for k in ("fame", "good", "evil")}
    out: list[str | None] = []
    totals: dict[str, int] = {}
    slot: dict[str, int] = {}
    for line in changes:
        m = _PLAIN.match(line)
        key = keys.get(m.group(1)) if m else None
        if key is None:
            out.append(line)
            continue
        if key not in slot:
            slot[key] = len(out)
            out.append(None)
            totals[key] = 0
        totals[key] += int(m.group(3)) * (-1 if m.group(2) == "-" else 1)
    for key, at in slot.items():
        total = totals[key]
        if total:
            label = content.config.stat_names.get(key, key)
            out[at] = f"{label} {total:+d}" + (gap_note(state, content, key) if total > 0 else "")
    return [x for x in out if x is not None]


# ── 每一段給什麼（說明卡、跨段那一行）──────────────────────────────


def fame_perks(content: Content, tier: int) -> list[str]:
    """名望第 tier 段給什麼（設計第四節的表），照開關組；數字讀 Config。沒做好、開關關著的不寫。"""
    cfg = content.config.renown
    out: list[str] = []
    if on(content, "discount"):
        out.append(("店家" if tier == 1 else "") + discount_word(cfg.discounts[tier - 1]))
    if tier == 1:
        out.append("狀態列、玩家卡寫你的稱號")
        if on(content, "duel"):
            out.append("頭目找上門的機會多一成")
    elif tier == 2:
        if on(content, "prize_gate"):
            out.append("掛重賞的懸賞揭得到")
        out.append("決戰名單標你的稱號")
        if on(content, "duel"):
            out.append("頭目多兩成、打贏的賞也多兩成")
    elif tier == 3:
        if on(content, "affinity"):
            out.append(f"名將見面時情誼 +{cfg.fame_affinity}")
        if on(content, "news"):
            out.append("天下大事傳開你的名號")
        if on(content, "faction_wanted"):
            out.append("敵方陣營每週通緝你")
    elif tier == 4:
        if on(content, "news"):
            out.append("打大場面天下大事都點名")
        if on(content, "faction_wanted"):
            out.append("通緝的賞更高")
        if on(content, "arena_reach"):
            out.append(f"擂台上排在你後面 {content.config.arena.famous_reach} 名內的人挑得到你")
    return out


# 善惡各段給什麼：乙線每一樣（正邪武學、情誼、醫館、黑市、俠寇選項、官府通緝）各自登記一個 (content, 路, 段) -> list[str]，
# 照開關回空清單——甲線先上時說明卡不會寫還沒做的東西。散人另有的好處見 sanren_perks。
VIRTUE_PERKS: list[Callable[[Content, str, int], list[str]]] = []


def virtue_perks(content: Content, way: str, tier: int) -> list[str]:
    """善惡第 tier 段（way 那一條路）給什麼：人人都有的那幾樣（VIRTUE_PERKS 登記的）。"""
    return [line for fn in VIRTUE_PERKS for line in fn(content, way, tier)]


def sanren_perks(state: GameState, content: Content) -> list[list[str]] | None:
    """散人另有的好處（遊俠名號留下來的，設計 2.3）：[項目, 說明]，數字照此刻的善惡段；不是散人、劇本沒有陣營是 None。"""
    if state.player.faction is not None or not content.scenario.factions:
        return None
    cfg, t = content.config.ranger, virtue_tier(state, content)
    pct = lambda x: round(x * 100)  # noqa: E731
    return [
        ["求見門檻", f"每段抵 {cfg.audience_per_tier}，你現在抵 {t * cfg.audience_per_tier}"],
        ["打贏的經驗", f"每段 +{pct(cfg.exp_per_tier)}%，你現在 +{pct(t * cfg.exp_per_tier)}%"],
        ["招募", f"第 2 段起每段 +{pct(cfg.recruit_per_tier)}%，你現在 +{pct(max(0, t - 1) * cfg.recruit_per_tier)}%"],
        ["散人奇遇", f"第 {cfg.qiyu_tier} 段起遇得上"],
        ["懸賞的銀兩", f"第 {cfg.bounty_bonus_tier} 段 ×{cfg.bounty_bonus:g}"],
    ]


PERKS = "這一段多了：{perks}。"


def perk_line(perks: list[str]) -> str:
    return PERKS.format(perks="；".join(perks)) if perks else ""


# ── 跨段那一刻（設計 3.3）──────────────────────────────

UP_FAME = "你的名號傳開了，江湖上漸漸有人稱你「{title}」。"
UP_VIRTUE = "江湖上開始有人叫你「{title}」。"
SWITCH = "江湖上不再叫你「{old}」，改叫你「{new}」。"
DOWN = "江湖上漸漸不再提你「{title}」的名號。"
TOLD_TITLE = "名聲"  # 同步時發現的跨段、第一次的說明那一則的標題
TOLD = ("江湖上開始用兩個稱號認你：一個看名望（江湖上多少人認得你），一個看善名、惡名（你是怎樣的人）。"
        "點狀態列的名號，再點「名聲」那一行，看得到每一段給什麼、下一段還差多少。")


@dataclass
class Crossing:
    lines: list[str] = field(default_factory=list)
    up: list[str] = field(default_factory=list)  # 這一下升上去的新稱號（得失那一排的金色籤）
    annals: list[tuple[str, int]] = field(default_factory=list)  # 行狀：(一句, 份量)
    first: bool = False  # 上線之後第一次看：只記段


def watch(state: GameState, content: Content, day: int) -> Crossing:
    """跟上一次看到的段（PlayerState.renown_seen）比：
    - 升段：只在超過這一季到過的最高段時寫（卡在門檻邊上的人不會一再收到），接一行這一段多了什麼；行狀一般 2、高段 3。
    - 換路（善名、惡名誰高換了）、掉段：各自一個遊戲日最多寫一次（day 是此刻的遊戲日，rules.game_day）。
    上線之後第一次看（renown_seen 是 None）只記段。開關關著什麼都不做。"""
    out = Crossing()
    if not on(content):
        return out
    p = state.player
    f, way, v = fame_tier(state, content), path(state), virtue_tier(state, content)
    seen = p.renown_seen
    if seen is None:
        p.renown_seen = RenownSeen(
            fame=f, path=way, virtue=v, best_fame=f, best_xia=v if way == "俠" else 0, best_kou=v if way == "寇" else 0,
        )
        out.first = True
        return out
    if f > seen.best_fame:
        title = FAME_TITLES[f]
        out.lines += [UP_FAME.format(title=title), perk_line(fame_perks(content, f))]
        out.up.append(title)
        out.annals.append((UP_FAME.format(title=title), 3 if f >= 3 else 2))
        seen.best_fame = f
    elif f < seen.fame and seen.fame_drop_day != day:
        out.lines.append(DOWN.format(title=FAME_TITLES[seen.fame]))
        seen.fame_drop_day = day
    switched = way != seen.path and seen.virtue > 0 and v > 0
    if switched and seen.path_day != day:
        old = named(VIRTUE_TITLES[seen.path][seen.virtue], state)
        out.lines.append(SWITCH.format(old=old, new=named(VIRTUE_TITLES[way][v], state)))
        seen.path_day = day
    best = seen.best_xia if way == "俠" else seen.best_kou
    if v > best:
        title = named(VIRTUE_TITLES[way][v], state)
        if not switched:
            out.lines.append(UP_VIRTUE.format(title=title))
        out.lines.append(perk_line(virtue_perks(content, way, v)))
        out.up.append(title)
        out.annals.append((UP_VIRTUE.format(title=title), 3 if v >= 3 else 2))
        if way == "俠":
            seen.best_xia = v
        else:
            seen.best_kou = v
    elif v < seen.virtue and way == seen.path and seen.path_day != day:
        out.lines.append(DOWN.format(title=named(VIRTUE_TITLES[way][seen.virtue], state)))
        seen.path_day = day
    seen.fame, seen.path, seen.virtue = f, way, v
    out.lines = [line for line in out.lines if line]
    return out
