"""新武學系統（取代 battle.py 的舊武學欄位）：品質／熟練度／威力／屬性四個欄位，見設計文件六。

武學分兩個來源：
- **本命武學**：歷史人物的固定武學，內容裡手寫（見 content/skills.json 重皮後的內容），
  情誼滿門檻才習得，品質穩定是「絕學」（見 QUALITY_BASE_POWER 最高一級）。
- **自創功法**：玩家自己取名，本模組的 generate_from_name() 依名字決定屬性／品質／
  威力／成長性——名字本身就是配方，同一個名字每次生成結果都一樣（純函式、無亂數狀態），
  這樣「已被佔用的名字」查得到就代表這個配方已經被人用掉了，不需要另外存生成結果。
  絕學機率極小但沒有結構性排除（設計文件六.2.1），跟本命武學穩定拿絕學形成對比。
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

QUALITIES = ("下品", "中品", "上品", "絕學")
ATTRIBUTES = ("陰", "陽", "剛", "柔", "快", "慢", "虛", "實")

# 各品質的威力區間（第一成～第十成線性內插，比照 tianxia 既有 skill_value 的作法）。
QUALITY_BASE_POWER = {"下品": 8, "中品": 16, "上品": 28, "絕學": 50}
QUALITY_TOP_POWER = {"下品": 24, "中品": 44, "上品": 72, "絕學": 120}

# 自創功法抽到各品質的機率（%，加總 100）；絕學極小機率，呼應設計文件六.2.1。
CREATED_QUALITY_WEIGHTS = {"下品": 55.0, "中品": 33.0, "上品": 11.5, "絕學": 0.5}

MAX_LEVEL = 10


class MartialArt(BaseModel):
    id: str
    name: str
    kind: str  # "內功" 或 "武學"
    quality: str  # QUALITIES 其中之一
    attribute: str  # ATTRIBUTES 其中之一
    base_power: float
    top_power: float
    # "historical"（本命武學，內容手寫）、"basic"（基礎武學，內容手寫）、"fused"（合成）；
    # 舊資料還有 "created"（玩家取名自創）與 "crafted"（舊的素材煉製，已經沒有了）
    origin: str = "created"
    creator: str | None = None  # 合成首創者；舊的自創、煉製功法照舊；內容武學為 None
    note: str = ""  # 模型寫的一句話描述（只有語意、沒有數字）；自創與本命武學是空的
    insight: str | None = None  # 最後融的意境 id（武學與成長設計 3.4）；修練要用它
    base: str | None = None  # 合成的底（功法 id）
    lean: str = "無"  # 正、邪、無：跟著最後融的意境（設計 7.3）


class Insight(BaseModel):
    """一個意境（武學與成長設計 3.2）。基本意境（風火水山、浩然、血煞）寫在 content/insights.json；
    合併出來的存在全服（world.get_insight），名字就是 id。只有語意，沒有數字。"""

    id: str
    name: str
    attribute: str  # ATTRIBUTES 其中之一
    lean: str = "無"  # 正、邪、無（設計 7.3）
    creator: str | None = None  # 合併出來的：第一個合出來的人；基本意境是 None
    note: str = ""  # 模型寫的一句說明；基本意境是內容的 desc
    parents: list[str] = Field(default_factory=list)  # 合併出來的：兩個來源的 id（排序過）


def power_at(art: MartialArt, level: int) -> float:
    """第 level 成（1~10）的威力，第一成是 base_power、第十成是 top_power，中間線性。"""
    level = max(1, min(MAX_LEVEL, level))
    return art.base_power + (art.top_power - art.base_power) * (level - 1) / (MAX_LEVEL - 1)


def _hash_bytes(name: str, tianji: int = 0) -> bytes:
    """天機 0 用名字本身（保留既有配方）；之後每一季在名字前面加上天機，同名長出不同的武學。"""
    key = name.strip() if tianji == 0 else f"{tianji}|{name.strip()}"
    return hashlib.sha256(key.encode("utf-8")).digest()


def _weighted_pick(digest_byte: int, weights: dict[str, float]) -> str:
    """用 0~255 的一個位元組，依 weights 的比重決定落在哪一項（累積分佈）。"""
    total = sum(weights.values())
    roll = (digest_byte / 256.0) * total
    acc = 0.0
    for key, weight in weights.items():
        acc += weight
        if roll < acc:
            return key
    return next(reversed(weights))


def generate_from_name(
    name: str, kind: str, skill_id: str, tianji: int = 0,
    weights: dict[str, float] | None = None, attribute: str | None = None,
) -> MartialArt:
    """自創功法：名字即配方，純函式、同名同結果，見模組說明。

    - 屬性：取雜湊第一個位元組對 8 取餘數，映射到 ATTRIBUTES。
    - 品質：取雜湊第二個位元組，依 CREATED_QUALITY_WEIGHTS 抽（絕學機率極小但存在）。
    - 威力：品質決定第一成/第十成的區間（QUALITY_BASE_POWER/TOP_POWER），區間內再用
      第三個位元組做小幅微調（±10%），同品質的武學威力才不會完全一樣。
    - tianji：這一季的天機（見 world_state.SharedWorldState.tianji），同一季內同名同結果，
      換季後重新洗牌。

    `weights` 與 `attribute` 是給合成用的（見 tianxia/fusion.py，武學與成長設計 3.4）：
    合成要讓「品質固定下品」、「屬性由融入的意境決定」，但擲骰仍然來自名字的雜湊。
    兩個都不傳時行為跟以前**完全一樣**（取名自創那條路徑的結果不受影響，有測試保護）。
    `weights` 的鍵要照 QUALITIES 的順序排（_weighted_pick 走的是累積分佈，順序有意義）。
    """
    digest = _hash_bytes(name, tianji)
    attribute = attribute or ATTRIBUTES[digest[0] % len(ATTRIBUTES)]
    quality = _weighted_pick(digest[1], weights or CREATED_QUALITY_WEIGHTS)
    jitter = 0.9 + (digest[2] / 255.0) * 0.2  # 0.9~1.1
    return MartialArt(
        id=skill_id,
        name=name,
        kind=kind,
        quality=quality,
        attribute=attribute,
        base_power=round(QUALITY_BASE_POWER[quality] * jitter, 1),
        top_power=round(QUALITY_TOP_POWER[quality] * jitter, 1),
        origin="created",
    )


def historical_art(skill_id: str, name: str, kind: str, attribute: str, quality: str = "絕學") -> MartialArt:
    """內容手寫的武學，不經過機率生成：本命武學穩定給絕學品質（設計文件七.1／六.2.1）；部下用的通用武學照內容標的品質。"""
    return MartialArt(
        id=skill_id,
        name=name,
        kind=kind,
        quality=quality,
        attribute=attribute,
        base_power=QUALITY_BASE_POWER[quality],
        top_power=QUALITY_TOP_POWER[quality],
        origin="historical",
    )


def content_art(skill_id: str, name: str, kind: str, attribute: str, quality: str) -> MartialArt:
    """內容手寫的武學：下品是基礎武學（武學與成長設計附錄 B，origin "basic"）；
    其他品質照舊走 historical_art（本命武學的絕學、部下用的上品武學，來源標本命，不算基礎武學）。
    威力照品質的區間、不加微調。"""
    if quality != "下品":
        return historical_art(skill_id, name, kind, attribute, quality)
    return MartialArt(
        id=skill_id, name=name, kind=kind, quality=quality, attribute=attribute,
        base_power=QUALITY_BASE_POWER[quality], top_power=QUALITY_TOP_POWER[quality], origin="basic",
    )


def with_quality(art: MartialArt, quality: str) -> MartialArt:
    """同一門武學換一個品質（修練是各練各的，設計 3.5）：威力照新品質的區間，保留這門武學原本那一點微調。
    品質一樣就原封不動回傳。"""
    if quality == art.quality:
        return art
    scale = art.base_power / QUALITY_BASE_POWER[art.quality]
    return art.model_copy(update={
        "quality": quality,
        "base_power": round(QUALITY_BASE_POWER[quality] * scale, 1),
        "top_power": round(QUALITY_TOP_POWER[quality] * scale, 1),
    })


def next_quality(quality: str) -> str | None:
    """修練的下一品；絕學是頂，回 None。"""
    i = QUALITIES.index(quality)
    return QUALITIES[i + 1] if i + 1 < len(QUALITIES) else None


# 屬性相剋：陰陽剛柔快慢虛實，比照 tianxia 設計文件（design.md §六）原本構想的「內功陰陽剛柔、
# 招式快慢虛實」。每組是一對相剋（前者克後者，克方在單次判定裡有加成，見設計文件六.3）。
ATTRIBUTE_COUNTERS = {
    "陽": "陰", "陰": "陽",
    "剛": "柔", "柔": "剛",
    "快": "慢", "慢": "快",
    "實": "虛", "虛": "實",
}


def counters(attacker: str, defender: str) -> bool:
    """attacker 的屬性是否克制 defender 的屬性。"""
    return ATTRIBUTE_COUNTERS.get(attacker) == defender
