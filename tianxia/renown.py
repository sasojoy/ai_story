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

from . import four_tiers, gender
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


NEWS_UP = "江湖上傳開了{name}的名號。"  # 跨過威震州郡那一刻的天下大事（4.5）；一季一人一次
NEWS_UP_FLAG = "名號傳開"  # 傳過了（玩家旗標；換季跟角色一起清空）
NEWS_BIG = "天下聞名的{name}在{place}與{foe}一戰，{tier}。"  # 天下聞名打完大場面的天下大事（4.5）
NEWS_BIG_FLAG = "天下聞名點名:"  # 「天下聞名點名:<遊戲日>」→ 這一天點名過幾次（玩家旗標，只留今天的）


def news_up_due(state: GameState, content: Content, up: list[str]) -> bool:
    """這一下升到威震州郡（news_tier）、還沒傳過：天下大事傳一句。"""
    tier = content.config.renown.news_tier
    return on(content, "news") and FAME_TITLES[tier] in up and NEWS_UP_FLAG not in state.player.flags


def famed_news_due(state: GameState, content: Content, day: int) -> bool:
    """天下聞名打完大場面，這一個遊戲日還能點名（famed_news_per_day 則以內）：能的話記一筆、回 True。"""
    cfg = content.config.renown
    if not on(content, "news") or fame_tier(state, content) < cfg.famed_tier:
        return False
    flags = state.player.flags
    key = f"{NEWS_BIG_FLAG}{day}"
    used = [f for f in flags if f.startswith(NEWS_BIG_FLAG)]
    today = [f for f in used if f.startswith(key + ":")]
    if len(today) >= cfg.famed_news_per_day:
        return False
    flags -= {f for f in used if not f.startswith(key + ":")}  # 只留今天的
    flags.add(f"{key}:{len(today) + 1}")
    return True


def duel_chance(state: GameState, content: Content) -> float:
    """頭目遇上的機會乘多少（設計 4.4：小有名氣 1.1、名動一方以上 1.2）：只放大門檻，擲的還是同一顆骰。關著是 1。"""
    if not on(content, "duel"):
        return 1.0
    return content.config.renown.duel_chance[fame_tier(state, content)]


def duel_reward(state: GameState, content: Content) -> float:
    """名動一方以上打贏頭目：經驗、銀兩、心得乘多少（4.4）；名望、素材照舊。"""
    cfg = content.config.renown
    return cfg.duel_reward if on(content, "duel") and fame_tier(state, content) >= cfg.duel_reward_tier else 1.0


def duel_meet_line(state: GameState, content: Content) -> str:
    """遇上頭目時多半句（4.4「寫原因」）：機會有放大才寫。"""
    return f"你{fame_title(state, content)}，攔路的也多了。" if duel_chance(state, content) > 1.0 else ""


def duel_paid_line(state: GameState, content: Content) -> str:
    """打贏頭目的得失那一句（4.4）：賞有多才寫。"""
    k = duel_reward(state, content)
    if k <= 1.0:
        return ""
    tenths = round((k - 1) * 10)
    more = f"{'兩' if tenths == 2 else _CN[tenths]}成" if 0 < tenths < 10 else f"{round((k - 1) * 100)}%"
    return f"（{fame_title(state, content)}：賞多{more}）"


def arena_famed(state: GameState, content: Content) -> bool:
    """擂台上天下聞名（設計 4.7）：排在他後面 famous_reach 名內的人都挑得到他。寫進 ArenaEntry.famed（報名、更新分身、同步時）。"""
    return on(content, "arena_reach") and fame_tier(state, content) >= len(FAME_TITLES) - 1


def ranger_exp_note(state: GameState, content: Content, factor: float) -> list[str]:
    """散人打贏的經驗多了幾成時寫的那一行（設計 6.3）：「（江湖遊俠：打贏的經驗多 5%）」；explain 關著、沒有加成是空的。"""
    title = virtue_title(state, content)
    if factor <= 1.0 or not title or not on(content, "explain"):
        return []
    return [f"（{title}：打贏的經驗多 {round((factor - 1) * 100)}%）"]


def ranger_bounty_note(state: GameState, content: Content, factor: float) -> list[str]:
    """散人懸賞的銀兩乘上去時寫的那一行（設計 6.3）：「（天下名俠：賞銀 ×1.25）」；explain 關著、沒有加成是空的。"""
    title = virtue_title(state, content)
    if factor <= 1.0 or not title or not on(content, "explain"):
        return []
    return [f"（{title}：賞銀 ×{factor:g}）"]


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


GREENWOOD_FLAG = "綠林開寨"  # 綠林山寨的 unlock_flag（名聲 5.1）：lessons 開著時開季立（world._open_greenwood）


def _lesson_perks(content: Content, way: str, tier: int) -> list[str]:
    """正邪武學（5.1）：走這條路、這一段起肯教的那幾門，照內容的 LearnRule.title 組；lessons 關著不寫。"""
    if not on(content, "lessons"):
        return []
    return [
        f"{content.locations[s.learn.at].name}教{s.name}" for s in content.skills.values()
        if s.learn is not None and s.learn.title is not None and s.learn.title.path == way and s.learn.title.tier == tier
        and s.learn.at in content.locations
    ]


VIRTUE_PERKS.append(_lesson_perks)

# ── 誰歡迎你（設計 4.3、5.2）──────────────────────────────

REGARD_WAY = {"敬俠": "俠", "喜狠": "寇"}  # 有這種看法的人物，見面時情誼起步看哪一條路
MEET_FAME = "{name}早聽過你的名號。（情誼 +{n}）"  # 待 joy 潤
MEET_VIRTUE = "{name}早聽說你是{title}。（情誼 +{n}）"
COLD_LINE = "{name}聽過你的名聲，神色淡淡的。"
MEET_FAME_FLAG = "初見:{cid}:名"  # 名望那一份給過了（一季一位人物一次）
MEET_VIRTUE_FLAG = "初見:{cid}:{way}"  # 後面接給到第幾段：「初見:liubei:俠2」


def _affinity_perks(content: Content, way: str, tier: int) -> list[str]:
    """善惡各段的情誼那一項（5.2）：敬俠／喜狠的人見面情誼 +3×段；寇第 1 段起敬俠的人對你冷淡。affinity 關著不寫。"""
    if not on(content, "affinity"):
        return []
    who = "敬俠" if way == "俠" else "喜狠"
    out = [f"{who}的人見面情誼 +{content.config.renown.virtue_affinity * tier}"]
    if way == "寇" and tier == 1:
        out.append("敬俠的人對你冷淡")
    return out


VIRTUE_PERKS.append(_affinity_perks)


# ── 俠的醫館、寇的黑市（設計 5.2）──────────────────────────────


def clinic_factor(state: GameState, content: Content) -> float:
    """俠一路 clinic_tier（一方豪俠）以上，療傷 × clinic_share（八五折），跟地盤、名望的折扣疊乘（team._price_here）。"""
    cfg = content.config.renown
    return cfg.clinic_share if on(content, "clinic") and meets(state, content, "俠", cfg.clinic_tier) else 1.0


def clinic_part(state: GameState, content: Content) -> str:
    """療傷打折的俠那一半：「一方豪俠・八五折」；沒打折是空字串。skillview.heal_note 跟地盤、名望那幾段寫在同一個括號（FB-294）。"""
    factor = clinic_factor(state, content)
    if factor >= 1.0 or not on(content, "explain"):
        return ""
    return f"{virtue_title(state, content)}・{discount_word(factor)}"


def reasons_text(parts: list[str]) -> str:
    """價錢後面那一個括號：「（威震州郡・九折，州郡大俠・八五折）」；沒有原因是空字串（名聲 4.1、FB-294：原因只寫一個括號）。"""
    parts = [x for x in parts if x]
    return f"（{'，'.join(parts)}）" if parts else ""


def black_market_price(state: GameState, content: Content, tier: int) -> int | None:
    """寇一路 black_market_tier（綠林好漢）以上，鐵匠鋪收這一階素材的黑市價（一階 3、二階 8）；不是寇、沒寫這一階是 None。"""
    cfg = content.config.renown
    if not (on(content, "black_market") and meets(state, content, "寇", cfg.black_market_tier)):
        return None
    return _dark_prices(content).get(tier)


def _dark_prices(content: Content) -> dict[int, int]:
    """黑市收哪幾階、各幾兩：Config.renown.black_market_prices，三階只在素材四階開著時收（正式季整合 4.2、6.6：24 兩；關著照舊只收
    一、二階），四階一律不收（同 economy.sell_tiers；這裡不 import economy，economy 會 import 這裡）。"""
    top = four_tiers.TOP_COMMON if four_tiers.on(content) else 2
    return {t: p for t, p in content.config.renown.black_market_prices.items() if t <= top}


def _trade_perks(content: Content, way: str, tier: int) -> list[str]:
    cfg = content.config.renown
    out = []
    if way == "俠" and tier == cfg.clinic_tier and on(content, "clinic"):
        out.append(f"醫館療傷{discount_word(cfg.clinic_share)}")
    prices = _dark_prices(content)
    if way == "寇" and tier == cfg.black_market_tier and on(content, "black_market") and prices:
        out.append("鐵匠鋪收購" + "、".join(f"{_CN[t]}階 {p} 兩" for t, p in sorted(prices.items())))
    return out


VIRTUE_PERKS.append(_trade_perks)

# ── 俠寇選項（設計 5.3）──────────────────────────────

NEEDS = "要{title}才做得來"  # 稱號不夠時那一顆選項底下的第二行（待 joy 潤）
CHOICE_PERK = "事件裡多出{way}的做法"


def needs_line(state: GameState, way: str, tier: int) -> str:
    return NEEDS.format(title=named(VIRTUE_TITLES[way][tier], state))


def _choice_perks(content: Content, way: str, tier: int) -> list[str]:
    """俠寇選項（5.3）：內容裡有要這一條路、這一段的選項才寫；virtue_choices 關著不寫。"""
    if not on(content, "virtue_choices"):
        return []
    has = any(ch.needs is not None and ch.needs.path == way and ch.needs.tier == tier
              for ev in content.events.values() for ch in ev.choices)
    return [CHOICE_PERK.format(way=way)] if has else []


VIRTUE_PERKS.append(_choice_perks)


def _wanted_perks(content: Content, way: str, tier: int) -> list[str]:
    """官府通緝（5.4）：寇 official_tier 段起官府每週貼海捕文書（賞照段）；俠 official_hunter_tier 段揭得了。official_wanted 關著不寫。"""
    if not on(content, "official_wanted"):
        return []
    cfg = content.config.renown
    if way == "寇" and tier >= cfg.official_tier and tier in cfg.official_silver:
        return [f"官府每週貼你的海捕文書（賞 {cfg.official_silver[tier]} 兩）"]
    if way == "俠" and tier == cfg.official_hunter_tier:
        return ["揭得了官府通緝"]
    return []


VIRTUE_PERKS.append(_wanted_perks)


def _cold_to(state: GameState, content: Content, character_id: str) -> bool:
    """敬俠的人遇上寇（善惡第 1 段以上）：冷淡（5.2）。"""
    ch = content.characters.get(character_id)
    return (on(content, "affinity") and ch is not None and ch.regard == "敬俠" and path(state) == "寇"
            and virtue_tier(state, content) >= 1)


def first_meet(state: GameState, content: Content, character_id: str) -> list[str]:
    """開始跟這位人物對話時（companion_agent.start_dialogue）的情誼起步（設計 4.3、5.2）：
    - 名望：威震州郡（fame_affinity_tier）以上 +fame_affinity，一季一位人物一次；還不到不記，升上去之後下一次對話照給。
    - 善惡：敬俠的人遇上俠、喜狠的人遇上寇，+virtue_affinity × 段；記給到第幾段，升段之後補多出來的那幾段；換了路不收回。
    情誼夾在 0～100，寫的是實際加了多少。affinity 關著回空。只改情誼與旗標。"""
    if not on(content, "affinity"):
        return []
    cfg, p = content.config.renown, state.player
    ch = content.characters.get(character_id)
    if ch is None:
        return []
    out: list[str] = []

    def bump(n: int) -> int:
        before = p.affinities.get(character_id, 0)
        p.affinities[character_id] = max(0, min(100, before + n))
        return p.affinities[character_id] - before

    flag = MEET_FAME_FLAG.format(cid=character_id)
    if flag not in p.flags and fame_tier(state, content) >= cfg.fame_affinity_tier:
        p.flags.add(flag)
        n = bump(cfg.fame_affinity)
        if n:
            out.append(MEET_FAME.format(name=ch.name, n=n))
    way = REGARD_WAY.get(ch.regard or "")
    if way is not None and path(state) == way and not _cold_to(state, content, character_id):
        tier = virtue_tier(state, content)
        head = MEET_VIRTUE_FLAG.format(cid=character_id, way=way)
        given = max((int(f[len(head):]) for f in p.flags if f.startswith(head) and f[len(head):].isdigit()), default=0)
        if tier > given:
            p.flags -= {f for f in p.flags if f.startswith(head)}
            p.flags.add(f"{head}{tier}")
            n = bump(cfg.virtue_affinity * (tier - given))
            if n:
                out.append(MEET_VIRTUE.format(name=ch.name, title=virtue_title(state, content), n=n))
    return out


def cold(state: GameState, content: Content, character_id: str, delta: int) -> int:
    """冷淡（5.2）：敬俠的人遇上寇，這一輪加的情誼打 cold_share 折、四捨五入、至少 +1；扣的照扣。其他情況原樣回傳。"""
    if delta <= 0 or not _cold_to(state, content, character_id):
        return delta
    return max(1, int(delta * content.config.renown.cold_share + 0.5))


def prompt_lines(state: GameState, content: Content, character_id: str) -> str:
    """人物對話的系統提示多的幾行（5.2，prompt 開著）：玩家的稱號（只帶稱號、不帶數字），人物有看法時另起一行他對這種人的看法。
    每行以換行結尾；什麼都沒有是空字串。"""
    if not on(content, "prompt"):
        return ""
    ch = content.characters.get(character_id)
    him = gender.pronoun(state)
    fame, virtue = fame_title(state, content), virtue_title(state, content)
    if fame and virtue:
        line = f"江湖上稱{him}「{fame}」，人稱「{virtue}」。"
    elif fame or virtue:
        line = f"江湖上稱{him}「{fame or virtue}」。"
    else:
        line = ""
    out = f"【玩家的名聲】{line}\n" if line else ""
    if ch is not None and ch.regard is not None:
        if _cold_to(state, content, character_id):
            view = f"看不起打家劫舍的人，對{him}冷淡"
        else:
            view = "敬重行俠仗義的人" if ch.regard == "敬俠" else "欣賞敢下狠手的人"
        out += f"【{ch.name}對這種人的看法】{view}\n"
    return out


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


# ── 狀態列、說明卡與玩家卡（設計 2.5、6.1、十一之二 1B、2C、3B）──────────────────────────────

SOURCES = {  # 說明卡最底下那一行（待 joy 潤）
    "fame": "事件的選擇；出陣攻打贏、挑戰大勢人物本人打贏、決戰自己出手（自己那一邊大勝再多）；首功、頭目戰、擂台、首創被人照著合。"
            "檢定失手、做了丟臉的事會掉。",
    "virtue": "事件的選擇；散人交懸賞照你走的路記善名或惡名。稱號看兩個誰高，一樣多算俠。",
}
SCALE_NOTE = "這一季 {days:g} 天，門檻是週末季的 {k:g} 倍。"


def _ladder(rows: tuple[str, ...], bars: list[int], perks: Callable[[int], list[str]], state: GameState | None = None) -> list[dict]:
    return [{"title": named(rows[t], state) if state is not None else rows[t], "at": bars[t - 1], "perks": perks(t)}
            for t in range(1, len(bars) + 1)]


def scale_note(world: WorldState, content: Content) -> str | None:
    """長的季多一句門檻乘了幾倍（說明卡、玩法說明）；週末季、沒有章是 None。"""
    from .world_state import season_length_days  # noqa: PLC0415

    k = scale(world)
    return SCALE_NOTE.format(days=season_length_days(world, content), k=k) if k > 1 else None


def status(state: GameState, content: Content) -> dict | None:
    """狀態列「名聲」那一行與說明卡的資料（status_data["renown"]）：短版稱號、名望與善惡各自的段、門檻、還差多少、四段各給什麼，
    散人另有的好處、長的季的倍數、名聲從哪裡來。開關關著是 None。"""
    if not on(content):
        return None
    st, w = state.player.stats, state.world
    fb, vb = fame_bars(content, w), virtue_bars(content, w)
    ft, vt, way = fame_tier(state, content), virtue_tier(state, content), path(state)
    fame, value, top = st.get("fame", 0), virtue_value(state), len(fb)
    return {
        "short": titles(state, content),
        "fame": {
            "n": fame, "tier": ft, "title": FAME_TITLES[ft],
            "at": fb[ft] if ft < top else None, "gap": fb[ft] - fame if ft < top else None,
            "next": FAME_TITLES[ft + 1] if ft < top else None,
            "ladder": _ladder(FAME_TITLES, fb, lambda t: fame_perks(content, t)),
        },
        "virtue": {
            "good": st.get("good", 0), "evil": st.get("evil", 0), "path": way,
            "by": content.config.stat_names.get(BOOKS[way], BOOKS[way]), "tier": vt,
            "title": virtue_title(state, content) or "",
            "at": vb[vt] if vt < top else None, "gap": vb[vt] - value if vt < top else None,
            "next": named(VIRTUE_TITLES[way][vt + 1], state) if vt < top else None,
            "ladder": {w_: _ladder(VIRTUE_TITLES[w_], vb, lambda t, w_=w_: virtue_perks(content, w_, t), state) for w_ in PATHS},
        },
        "sanren": sanren_perks(state, content),
        "scale_note": scale_note(w, content),
        "sources": SOURCES,
    }


def card(state: GameState, content: Content) -> dict | None:
    """玩家卡（設計 2.5、十一之二 3B）：只寫稱號、不寫數字；path 是善惡那一個稱號的路（沒有善惡稱號是 None）。開關關著是 None。"""
    if not on(content):
        return None
    return {"titles": titles(state, content), "path": path(state) if virtue_title(state, content) else None}


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
