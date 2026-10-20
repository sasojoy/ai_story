"""探索三選一（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第三節）：找素材、找事件、靜心感悟。

act:explore 留作展開的入口（engine.IDLE_MARK：切磋、論武、假人、網頁都認它是「閒著」）：開關開著時按了不花體力、只回 PICK 那一句；
三種各自一個 id（explore:gather|seek|sense），一樣的體力。這裡放純規則（id、字、找素材給什麼、撞不撞怪、自己的亂數）；
打一場、抽事件、有所感在 engine.Game._explore_mode。擲骰一律用自己的亂數（rng_for），不碰 Game.rng。
開關（Config.explore_modes.enabled）關著時引擎照舊照地點比例自動抽（Game._explore）。"""
from __future__ import annotations

import random

from pydantic import BaseModel

from typing import TYPE_CHECKING

from . import calendar, insights, materials
from .models import Content, GatherBranch, Location

if TYPE_CHECKING:
    from .state import GameState, WorldState

PREFIX = "explore:"
GATHER, SEEK, SENSE = "gather", "seek", "sense"
MODES = (GATHER, SEEK, SENSE)
PRACTICE = "practice"  # 練功（一類一顆開著才有，正式季整合 2.5；不在 MODES：舊的三選一沒有它）
NAMES = {GATHER: "找素材", SEEK: "找事件", SENSE: "靜心感悟", PRACTICE: "練功"}  # 待 joy 潤
PICK = "探索要選一種：找素材、找事件，或靜心感悟。"  # 待 joy 潤：按「探索」本身的回話
NO_SENSE = "這裡悟不出什麼"  # 待 joy 潤（設計 3.3；鈕上不帶句號）
SENSE_LATER = "選錯了做法，這裡要過一陣子才悟得出"  # 待 joy 潤：這個遊戲日在這裡選錯過做法
GATHER_LINE = "你在{place}四下翻找。"  # 待 joy 潤
GATHER_NONE = "翻了一陣，沒找到什麼能用的。"  # 待 joy 潤
FOE_LINE = "你正翻找著，{foe}突然殺出！"  # 待 joy 潤
SEEK_NONE = "你四處走走，這一帶眼下沒什麼事。"  # 待 joy 潤
SEEK_EMPTY = "這一帶眼下沒什麼事"  # 待 joy 潤：一類一顆的找事件池子空了（鈕上，不帶句號；正式季整合 2.7）
PRACTICE_LINE = "你在{place}找上{foe}練手。"  # 待 joy 潤：練功開打那一句
NO_FOE = "這裡沒有可以練手的對手"  # 待 joy 潤（設計 2.5；鈕上不帶句號）
NO_FOE_NEAR = "，最近的在{place}"  # 待 joy 潤：接在 NO_FOE 後面
BOSS_NOTE = "頭目"  # 待 joy 潤：這裡只有頭目時鈕上那一格
BOSS_COOLING = "頭目{wait}後才會再現身"  # 待 joy 潤：兩場頭目戰之間的冷卻（wait 是 arena.wait_text 的現實倒數）
BOSS_GONE_WEEK = "這一週他不再現身"  # 待 joy 潤：21 天季這一週的次數用完
BOSS_GONE_SEASON = "這一季他不再現身"  # 待 joy 潤：一季的次數用完
BOSS_BACK_DAY = "，第 {day} 天 00:00 再來"  # 待 joy 潤：7 天濃縮季接在「這一段他不再現身」後面，下一段第一天重算（FB-501）


def boss_gone(state: GameState, content: Content) -> str:
    """頭目的次數用完時練功鈕上那一格（FB-501）：per_boss_week 設了照「這一週」（7 天濃縮季「這一段」，calendar.week_word，
    寫出下一段第一天 00:00 再來；最後一段沒有下一段，寫「這一季」），否則照「這一季」。21 天季一個字都不變。"""
    if not content.config.duel.per_boss_week:
        return BOSS_GONE_SEASON
    w = state.world
    if not calendar.week7_on(w, content):
        return BOSS_GONE_WEEK
    week = calendar.point(w.time, content, w).week
    if week >= len(content.config.season_segments):
        return BOSS_GONE_SEASON
    first, _ = calendar.segment_days(week + 1, content)
    return f"{calendar.week_word('this_one', content, w)}他不再現身" + BOSS_BACK_DAY.format(day=first)

# ── 找素材分支（第 32 項；docs/superpowers/plans/2026-10-18-找素材分支.md）──
# 按「找素材」照地點地形展開幾條路（content/gather_branches.json），每條一定給素材、差在屬性；最後一顆「自己說…」。
# 這裡有兩條以上才有分支層：一條（或城鎮）時「找素材」照舊直接做，不多一層。選項 id 是 explore:gather:<分支 id>、explore:gather:say。
SAY = "say"
SAY_ID = f"{PREFIX}{GATHER}:{SAY}"
SAY_MAX = 20  # 「自己說」最多幾個字（同隨口應對）
SAY_ROLL = "自己說"  # 「自己說」成不成那一擲的用途（rng_for）
GATHER_PICK = "找素材要挑一條路：照這一帶的地形，或者自己說說怎麼找。"  # 待 joy 潤：按「找素材」入口本身的回話（不花體力）
DEEP_LINE = "山風穿谷，你忽然心有所感。"  # 待 joy 潤：深入時悟到這一帶的意境，接 insights.learn 那幾句
SAY_LABEL = "自己說…"  # 待 joy 潤
SAY_NOTE = "寫得好多一份"  # 待 joy 潤：鈕上體力後面那一段（【預設】企劃者 2026-10-19 照 PM 先定的：多一個同屬性一階、再擲一次二階）
SAY_BAD = f"（寫下你的找法，{SAY_MAX} 字以內。）"  # 按「自己說…」本身、或字數不對
SAY_NONE = "（這裡此刻沒法照自己的法子找。）"  # 待 joy 潤：A 段開不了單（不在分支層、體力不夠、換了地方）
SAY_GONE = "（你已經換了做法，這句話沒派上用場。）"  # 待 joy 潤：C 段對不上（換了地點、中間做了別的探索、字不同）
SAY_SAID = "你：「{text}」（{rate}）"  # 紀錄裡寫你那一句與成算（同隨口應對的寫法）


class GatherTextRequest(BaseModel):
    """「自己說」的單子（A 段開、B 段送模型、C 段重驗）：在哪、第幾次探索（PlayerState.explore_seq）、那一句、模型可以挑的屬性
    （這裡所有分支的屬性聯集，say_choices）。place、tags 只是給模型看的。"""

    location: str
    place: str
    tags: list[str]
    seq: int
    text: str
    choices: list[str]


def branches_on(content: Content, world: WorldState | None) -> bool:
    """找素材分支開著沒：Config.gather_branches 打開、內容有分支表、一類一顆（precise.on：設定＋開季蓋章＋探索三選一）也開著——
    分支只接在「找素材一定給、不打仗」之後（第 3 批）。分支本身不蓋章（PM）。"""
    from . import precise  # noqa: PLC0415  precise 反過來 import 這一份

    return content.config.gather_branches.enabled and bool(content.gather_branches) and precise.on(content, world)


def branches_here(content: Content, loc: Location) -> list[GatherBranch]:
    """這裡有哪幾條分支（照內容的順序）：地點標籤對得上一個、危險度到 min_danger。城鎮類一條都沒有。"""
    if is_town(content, loc):
        return []
    tags = set(loc.tags)
    return [b for b in content.gather_branches.values() if tags & set(b.tags) and loc.danger >= b.min_danger]


def layered(content: Content, world: WorldState | None, loc: Location) -> list[GatherBranch]:
    """這裡有沒有分支層：開關開著、這裡兩條以上就回那幾條，否則空的（找素材照舊直接做）。"""
    if not branches_on(content, world):
        return []
    here = branches_here(content, loc)
    return here if len(here) >= 2 else []


def branch_option(branch_id: str) -> str:
    return f"{PREFIX}{GATHER}:{branch_id}"


def _loc_attributes(content: Content, loc: Location) -> list[str]:
    """這裡寫的素材（Location.materials）的屬性，照寫的順序、不重複；沒寫是空的（gather_finds 那時從同階全部挑）。"""
    out: list[str] = []
    for mid in loc.materials:
        attr = content.materials[mid].attribute if mid in content.materials else None
        if attr is not None and attr not in out:
            out.append(attr)
    return out


def branch_attributes(content: Content, loc: Location, branch: GatherBranch) -> list[str]:
    """這條分支給哪幾種屬性：照內容寫的；深入照這裡的素材（同找素材本來的）。"""
    return _loc_attributes(content, loc) if branch.deep else list(branch.attributes)


def say_choices(content: Content, loc: Location) -> list[str]:
    """「自己說」模型可以挑的屬性：這裡所有分支的屬性聯集（照分支的順序）。第一個是模型挑壞了時的退路（第一條分支的第一種）。"""
    out: list[str] = []
    for branch in branches_here(content, loc):
        out += [a for a in branch_attributes(content, loc, branch) if a not in out]
    return out


def say_text(text: str | None) -> str | None:
    """「自己說」那句話能不能送：去頭尾空白、中間連著的空白併成一個，1～SAY_MAX 字才算數；不行就是 None。"""
    if text is None:
        return None
    text = " ".join(str(text).split())
    return text if 0 < len(text) <= SAY_MAX else None


def deep_insight(content: Content, loc: Location, rng: random.Random) -> str | None:
    """深入另擲的悟意境（Config.gather_branches.deep_insight_chance）：悟不出的地方（insights.explore_gives 是空的）不擲；
    中了從這裡悟得到的挑一個（同一顆 rng）。回意境 id，沒中是 None。"""
    pool = insights.explore_gives(loc, content)
    if not pool or rng.random() >= content.config.gather_branches.deep_insight_chance:
        return None
    return rng.choice(pool)


def say_bonus(content: Content, loc: Location, rng: random.Random, attribute: str) -> list[str]:
    """「自己說」寫得好多給的（【預設】）：一個同屬性一階，say_bonus_second 開著時再照危險度（second_tier）擲一次同屬性二階。"""
    found = [_one(content, {attribute}, 1, rng)]
    if content.config.gather_branches.say_bonus_second and rng.random() < content.config.explore_modes.second_tier.get(loc.danger, 0.0):
        found.append(_one(content, {attribute}, 2, rng))
    return [mid for mid in found if mid is not None]


def on(content: Content) -> bool:
    return content.config.explore_modes.enabled


def option_id(mode: str) -> str:
    return f"{PREFIX}{mode}"


def rng_for(season: int, name: str, serial: int, what: str) -> random.Random:
    """這一次探索、這一個用途自己的亂數：季數｜名號｜第幾次探索（PlayerState.explore_seq）｜用途。決定性，不動 Game.rng。"""
    return random.Random(f"探索|{season}|{name}|{serial}|{what}")


def is_town(content: Content, loc: Location) -> bool:
    return content.config.explore_mix_of(loc.tags).kind == "town"


def _one(content: Content, kinds: set[str], tier: int, rng: random.Random) -> str | None:
    """這一階、這幾種屬性的素材挑一個（一個都沒有就從同階全部挑）；同階一個都沒有是 None。"""
    pool = [m for m in materials.by_tier(content, tier) if m.attribute in kinds] or materials.by_tier(content, tier)
    return rng.choice(pool).id if pool else None


def gather_finds(
    content: Content, loc: Location, rng: random.Random, sure: bool = False, attributes: list[str] | None = None,
) -> list[str]:
    """找素材撿到的素材 id（設計 3.1 的表）：屬性照這裡寫的素材（Location.materials），沒寫就從同階全部挑；城鎮 town_chance 一個一階；
    其餘一個一階（素材與經濟設計第七節：Config.economy.gather_cut 開著時是 gather_first_chance〔七成〕，關著一定給、不擲骰），
    照危險度 second_tier 的機會再一個二階。三階不從這裡來。
    sure（一類一顆，正式季整合 2.4）：一定給——城鎮一定一個一階、城外一定一個一階（不擲 town_chance、gather_first_chance），二階照舊。
    attributes（找素材分支，第 32 項）：給了就拿它當屬性的池子，數量的規則一個字不變；沒給（None）跟以前一模一樣。"""
    cfg = content.config.explore_modes
    econ = content.config.economy
    if attributes:
        kinds = set(attributes)
    else:
        kinds = {content.materials[m].attribute for m in loc.materials if m in content.materials}

    def one(tier: int) -> str | None:
        return _one(content, kinds, tier, rng)

    if is_town(content, loc):
        found = [one(1)] if sure or rng.random() < cfg.town_chance else []
    else:
        found = [one(1)] if sure or not econ.gather_cut or rng.random() < econ.gather_first_chance else []
        if rng.random() < cfg.second_tier.get(loc.danger, 0.0):
            found.append(one(2))
    return [mid for mid in found if mid is not None]


def encounter_due(content: Content, loc: Location, rng: random.Random) -> bool:
    """找素材撞不撞上怪：城鎮不撞，其餘 encounter_chance。"""
    return not is_town(content, loc) and rng.random() < content.config.explore_modes.encounter_chance
