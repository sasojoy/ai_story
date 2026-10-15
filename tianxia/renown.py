"""名聲（核心玩法重整第 3 塊，docs/superpowers/specs/2026-10-15-名聲-design.md）：人人兩個稱號，名望稱號（五段）與善惡稱號（俠、寇各四段）。

名望＝江湖上多少人認得你；善名、惡名＝你是怎樣的人（企劃者定）。名望不加戰力。
純規則：段、稱號、門檻、季長倍數、名望那一半的折扣、得失後面的差距、跨段比對、說明卡的資料。開關都在 Config.renown（RenownTuning）；
titles 關著時這裡每個函式都回「沒有」（段 0、空清單、None、倍數 1），其他開關要 titles 開著才有作用（on）。
門檻乘季長倍數：開季時蓋進 WorldState.renown_scale（world_state.stamp_season），這裡只讀那一欄（scale）。
只 import models、state、gender、world_state；rules、ranger、territory、team、bounties、arena……反過來呼叫它。"""
from __future__ import annotations

from . import gender
from .models import Content
from .state import GameState, WorldState

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


def price_factor(state: GameState, content: Content) -> float:
    """名望那一半的店家折扣（設計 4.1）：第 1～4 段各一個倍數；沒到、開關關著是 1。地盤那一半另外乘（territory.price_here）。"""
    t = fame_tier(state, content) if on(content, "discount") else 0
    return content.config.renown.discounts[t - 1] if t > 0 else 1.0
