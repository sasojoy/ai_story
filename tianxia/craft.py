"""煉製：兩樣素材 → 一門功法（無限煉製第二刀，見 docs/superpowers/specs/2026-10-01-無限煉製-design.md §5）。

**責任切開的方式**（專案原則「數值全部由規則引擎決定，執行時不接 LLM」的解法，見設計 §二）：

| 誰 | 做什麼 |
|---|---|
| LLM | **只產出名字＋一句說明**。一個數字都不碰。 |
| 引擎 | 素材 → 品質機率分佈的位移、屬性、擲骰（名字的雜湊）、成本、全服登記 |

無限的可能來自命名空間，不是數值自由度。而且因為配方有全服快取，LLM 的成本**只在全服
第一次發現某個配方時付一次**，之後是純查表（零 LLM 呼叫、零亂數、全服看到同一個結果）。

LLM 呼叫刻意在檔案鎖**外面**（照 battle_instance.py 既有的先例），只有登記那一步進鎖。
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel

from . import materials, zh
from .martial_arts import QUALITIES, MartialArt, counters, generate_from_name
from .models import Content, Material
from .ollama_client import OllamaClient
from .state import GameState
from .world_state import WorldStateStore

MATERIALS_PER_CRAFT = 2  # 一次吃兩樣（可以同種）；三樣留給「功法 ＋ 功法」那一步
KINDS = ("內功", "武學")

# 品質權重的三個錨點（設計 §5.4）：平均階 1.0／2.0／3.0，中間線性內插。
# 1.0 那一列**刻意等於 martial_arts.CREATED_QUALITY_WEIGHTS**——隨手撿的凡品煉出來的東西，
# 不該比自己取個名字強。
QUALITY_ANCHORS: dict[float, dict[str, float]] = {
    1.0: {"下品": 55.0, "中品": 33.0, "上品": 11.5, "絕學": 0.5},
    2.0: {"下品": 28.0, "中品": 44.0, "上品": 26.0, "絕學": 2.0},
    3.0: {"下品": 8.0, "中品": 37.0, "上品": 48.0, "絕學": 7.0},
}
COUNTER_TIER_BONUS = 0.5  # 兩樣素材相剋時，平均階額外 +0.5（「相剋相生」，設計 §5.3）
MAX_TIER = 3.0

NAME_MIN_CHARS, NAME_MAX_CHARS = 2, 6
NAME_ATTEMPTS = 3  # LLM 最多試幾次（第一次 + 兩次重生成）；全部失敗就走決定性組名
CLAIM_ATTEMPTS = 4  # 名字被占用時，用決定性組名換名字再試幾次


class CraftedName(BaseModel):
    """LLM 唯一被允許回傳的東西：名字與一句說明。這裡刻意沒有任何數字欄位。"""

    name: str
    description: str = ""


# ── 配方與成本 ────────────────────────────────────────────


def recipe_key(material_ids: list[str], kind: str) -> str:
    """配方鍵：素材 id 排序後接起來，再加上要煉的種類。排序保證 A+B 與 B+A 是同一個配方。"""
    return "+".join(sorted(material_ids)) + "|" + kind


def cost(content: Content, material_ids: list[str]) -> int:
    """煉製要花多少心得（設計 §5.5）：base × 素材數 + per_tier × 階總和。

    照實測校準：整季心得收入 20~96，兩個凡品 16、兩個天品 51，所以一季能煉 1~6 次，
    想多煉就得刻意閉關。**不沿用 `Config.xinde_cost_factor`**（那是為「練功要花心得」訂的，
    單門練滿要 900，跟實際收入差 20 倍以上）。
    """
    cfg = content.config
    tiers = sum(content.materials[mid].tier for mid in material_ids if mid in content.materials)
    return cfg.craft_xinde_base * len(material_ids) + cfg.craft_xinde_per_tier * tiers


def mean_tier(a: Material, b: Material) -> float:
    """兩樣素材的平均階，相剋時 +0.5（上限 3.0）。這個值決定品質的機率分佈。"""
    base = (a.tier + b.tier) / 2
    if opposed(a, b):
        base += COUNTER_TIER_BONUS
    return min(MAX_TIER, base)


def quality_weights(tier: float) -> dict[str, float]:
    """依平均階在三個錨點之間線性內插出品質權重；鍵照 QUALITIES 的順序排（累積分佈有順序）。"""
    points = sorted(QUALITY_ANCHORS)
    tier = min(max(tier, points[0]), points[-1])
    low = max((p for p in points if p <= tier), default=points[0])
    high = min((p for p in points if p >= tier), default=points[-1])
    if low == high:
        return {q: QUALITY_ANCHORS[low][q] for q in QUALITIES}
    ratio = (tier - low) / (high - low)
    return {
        q: QUALITY_ANCHORS[low][q] + (QUALITY_ANCHORS[high][q] - QUALITY_ANCHORS[low][q]) * ratio
        for q in QUALITIES
    }


def opposed(a: Material, b: Material) -> bool:
    """兩樣素材是不是一組相剋對（剛柔、快慢）。"""
    return counters(a.attribute, b.attribute) or counters(b.attribute, a.attribute)


def result_attribute(a: Material, b: Material) -> str | None:
    """煉出來的功法屬性（設計 §5.3）；None＝交給名字的雜湊決定（保留一點意外）。

    - 兩樣同屬性 → 該屬性（獎勵專一的配方）
    - 一組相剋對（剛柔、快慢）→ **階高的那一樣**；同階就交給名字
    - 其他（不相剋的異屬性）→ 交給名字

    設計文件 §5.3 原本寫「相剋時取**克方**的屬性」，實作時發現那句話無法成立：
    `martial_arts.ATTRIBUTE_COUNTERS` 是**相互**相剋的（剛克柔、柔也克剛），沒有單方面的
    克方。改成「階高者勝」——同時也讓「拿好素材去配」這件事更有意義。
    """
    if a.attribute == b.attribute:
        return a.attribute
    if opposed(a, b) and a.tier != b.tier:
        return a.attribute if a.tier > b.tier else b.attribute
    return None


# ── 名字：LLM 只負責這個 ───────────────────────────────────


def _describe(material: Material) -> str:
    return f"{material.name}（{materials.tier_label(material)}・屬{material.attribute}）——{material.description}"


def _messages(a: Material, b: Material, kind: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是武俠小說裡替功法取名的人。玩家把兩樣材料投進爐中，煉成一門功法。"
                "你只負責取名字、寫一句話的說明，**絕對不要提到任何數字、品質、等級或威力**。"
                "全程使用繁體中文。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"材料一：{_describe(a)}\n"
                f"材料二：{_describe(b)}\n"
                f"要煉的是一門{kind}。\n\n"
                f"name：{NAME_MIN_CHARS}～{NAME_MAX_CHARS} 個中文字的功法名稱，必須原創，"
                "不可使用金庸等武俠小說裡的專有名詞，不要標點符號。\n"
                "description：20 字以內，說這門功法打起來是什麼樣子。"
            ),
        },
    ]


def clean_name(raw: str) -> str:
    """把 LLM 回的名字整理乾淨：去掉空白與書名號之類的包裝，再轉成繁體。"""
    name = (raw or "").strip()
    for ch in "【】《》「」〈〉『』()（）[]<>\"'“”‘’ \t\n　":
        name = name.replace(ch, "")
    return zh.to_traditional(name)


def name_problem(name: str, content: Content) -> str | None:
    """名字過不了過濾的原因；None＝可以用。

    **一定要在登記之前跑**：名字會永久進全服的配方表，事後補救不了（設計 §5.7）。
    """
    if not (NAME_MIN_CHARS <= len(name) <= NAME_MAX_CHARS):
        return f"長度要 {NAME_MIN_CHARS}~{NAME_MAX_CHARS} 個字"
    if not all("一" <= ch <= "鿿" for ch in name):
        return "只能是中文字"
    for banned in content.banned_names:
        if banned and banned in name:
            return f"用到了既有作品的專有名詞（{banned}）"
    if any(name == m.name for m in content.materials.values()):
        return "跟素材同名"
    if any(name == ch.name for ch in content.characters.values()):
        return "跟人物同名"
    if any(name == sk.name for sk in content.skills.values()):
        return "跟本命武學同名"
    return None


def propose_name(
    client: OllamaClient, content: Content, a: Material, b: Material, kind: str,
) -> tuple[str | None, str]:
    """請 LLM 命名，回傳（通過過濾的名字, 一句說明）；試完都不行就回 (None, "")。"""
    messages = _messages(a, b, kind)
    for _ in range(NAME_ATTEMPTS):
        try:
            reply = client.chat_structured(messages, CraftedName, required_fields=["name"])
        except Exception:  # noqa: BLE001  連不上、404、逾時——一律當作這次沒取到名字
            return None, ""
        if reply is None:
            return None, ""
        name = clean_name(reply.name)
        if name_problem(name, content) is None:
            return name, zh.to_traditional((reply.description or "").strip())
    return None, ""


def fallback_name(content: Content, key: str, kind: str, salt: int = 0) -> str:
    """決定性組名（設計 §5.6）：LLM 不可用、或產出的名字過不了過濾／撞名時用。

    同一個配方永遠組出同一個名字，所以離線也能玩、全服也一致。`tests/test_real_content.py`
    的整季模擬把 LLM mock 掉，走的就是這條路，所以它不是裝飾品。
    """
    names = content.craft_names
    suffixes = names.neigong if kind == "內功" else names.wugong
    digest = hashlib.sha256(f"{key}#{salt}".encode()).digest()
    return names.prefixes[digest[0] % len(names.prefixes)] + suffixes[digest[1] % len(suffixes)]


# ── 煉製 ──────────────────────────────────────────────────


def can_craft(state: GameState, content: Content, material_ids: list[str], kind: str) -> str | None:
    """不能煉的原因；None＝可以煉。"""
    if kind not in KINDS:
        return f"只能煉內功或武學，不是「{kind}」。"
    if len(material_ids) != MATERIALS_PER_CRAFT:
        return f"一次要投入 {MATERIALS_PER_CRAFT} 樣素材。"
    for mid in set(material_ids):
        if mid not in content.materials:
            return "選了不存在的素材。"
        if materials.held(state, mid) < material_ids.count(mid):
            return f"{content.materials[mid].name}不夠。"
    price = cost(content, material_ids)
    if state.player.stats.get("xinde", 0) < price:
        return f"心得不足：煉製需要 {price} 點，你只有 {state.player.stats.get('xinde', 0)} 點。"
    return None


def craft(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient,
    material_ids: list[str], kind: str,
) -> tuple[MartialArt | None, list[str]]:
    """煉製一門功法，回傳（功法, 訊息）；不能煉時回傳 (None, [原因])。

    流程（設計 §5.2）：檢查 → 查配方快取 → 命中就直接用登記在案的那一門（零 LLM）→
    沒命中才請 LLM 命名 → 過濾 → 依素材決定屬性與品質權重 → 鎖內登記 → 扣素材與心得。
    """
    problem = can_craft(state, content, material_ids, kind)
    if problem is not None:
        return None, [problem]

    a, b = (content.materials[mid] for mid in material_ids)
    key = recipe_key(material_ids, kind)

    art = world.lookup_recipe(key)
    first_time = False
    if art is None:
        name, note = propose_name(client, content, a, b, kind)
        weights = quality_weights(mean_tier(a, b))
        attribute = result_attribute(a, b)
        for attempt in range(CLAIM_ATTEMPTS):
            if name is None:
                name = fallback_name(content, key, kind, salt=attempt)
            candidate = generate_from_name(name, kind, name, weights=weights, attribute=attribute)
            candidate.creator = state.player.name
            candidate.note = note
            art, first_time = world.claim_recipe(key, candidate)
            if art is not None:
                break
            name = None  # 名字被占用了（別人的自創功法或別的配方），換一個決定性的名字再試
            note = ""
        if art is None:
            return None, ["爐火熄了，這一次什麼也沒煉成（名字都被用掉了，再試一次）。"]

    for mid in material_ids:
        materials.take(state, mid)
    price = cost(content, material_ids)
    state.player.stats["xinde"] = max(0, state.player.stats.get("xinde", 0) - price)

    msgs = [_result_line(art, a, b, first_time), f"心得 -{price}"]
    msgs += _store(state, art)
    return art, msgs


def _result_line(art: MartialArt, a: Material, b: Material, first_time: bool) -> str:
    head = (
        f"你把{a.name}與{b.name}投進爐中，煉成了一門{art.kind}【{art.name}】"
        f"（{art.quality}・屬{art.attribute}）！"
    )
    if art.note:
        head += f"\n{art.note}"
    if first_time:
        return head + "\n這個配方是江湖上第一次煉成——從此它就叫這個名字。"
    creator = art.creator or "不知名的前人"
    return head + f"\n這個配方由{creator}首創，你照著煉出了同一門功法。"


def _store(state: GameState, art: MartialArt) -> list[str]:
    """煉出來的功法放哪：對應的欄位空著就直接配上身，否則進功法庫。

    **第一刀之後才發現 `team.py` 根本沒有散功／換功法的函式**，所以這裡先讓空欄位直接配上，
    免得煉出絕學卻裝不上去（設計 §六）。真正的「改練」（把庫裡的換上來、熟練度各自保留）
    是第三刀的事。
    """
    member = state.player.member
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    if getattr(member, slot) is None:
        setattr(member, slot, art.id)
        setattr(member, slot.replace("_id", "_level"), 1)
        return [f"你當場就把【{art.name}】練到了第一成。"]
    if art.id not in state.player.arts:
        state.player.arts.append(art.id)
    return [f"【{art.name}】先收進功法庫（你已經有一門{art.kind}了）。"]
