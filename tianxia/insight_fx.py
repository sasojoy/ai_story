"""意境效果池（武學重構第二批；Joy 2026-10-20「每個意境可能有3-4種效果，其中一個是大獎，一般效果有層數，越高越強，
大獎是高級效果，意境品質越好越容易合出來，每個意境可能出1-2個效果」）。

| 東西 | 是什麼 |
|---|---|
| 一份意境 | 手上的一個意境 id；同一種可以有好幾份（第一份是原本的 id，第二份起「feng~2」），每一份各自的品質與效果 |
| 品質 | 下品、中品、上品：悟到時擲（Config.arts.insight_quality_odds；最濃的地方、悟性往上推），越好越容易出第二個效果與大獎 |
| 效果池 | 每一路（屬性）兩個一般功效（content/traits.json 的 general，第一個鍵是屬性、第二個寫 id）加一個大獎（那一路的高階技能） |
| 效果 | 一份意境一到兩個（insight_max_effects）：一般功效有層數（一重到三重），大獎沒有層數 |
| 揣摩 | 同一種意境兩份揉成一份：同一個一般功效的層數相加、品質取好的、沒有大獎時照品質擲一次；第二份用掉 |
| 合成 | 兩個不同的意境合出那一路（insights.PAIR_ATTRIBUTES）的一份新的，照兩份裡較好的品質擲，大獎機會加倍 |

存在 PlayerState.insight_fx（id → state.InsightFx）；這一版之前悟到的沒有紀錄，照舊的樣子算（record：基本意境是那一路第一個功效、
層數照 insight_strength；合出來的是大獎；秘方的只有特別功效），品質當中品。擲骰用自己的亂數（天機｜名號｜那一份｜…），不碰 Game.rng。
"""
from __future__ import annotations

import random

from .models import Content, GeneralTrait, HighTrait
from .state import GameState, InsightFx
from .world_state import WorldStateStore

PIECE = "~"
QUALITIES = ("下品", "中品", "上品")
LEGACY_QUALITY = "中品"
MAX_LAYERS = 3
LAYER_MARKS = {1: "一重", 2: "二重", 3: "三重"}
GRAND_MARK = "大獎"  # 待 joy 潤


def base_id(insight_id: str | None) -> str | None:
    """一份意境是哪一種：「feng~2」→「feng」；第一份、私有的、合出來的照原樣。"""
    if not insight_id:
        return insight_id
    return insight_id.split(PIECE, 1)[0]


def pieces(state: GameState, base: str) -> list[str]:
    """手上這一種意境的每一份（照悟到的先後）。"""
    return [i for i in state.player.insights if base_id(i) == base]


def new_piece_id(state: GameState, base: str) -> str:
    """下一份的 id：第一份就是那一種的 id，之後 feng~2、feng~3…（拿掉過的號碼可以再用）。"""
    p = state.player
    if base not in p.insights:
        return base
    n = 2
    while f"{base}{PIECE}{n}" in p.insights:
        n += 1
    return f"{base}{PIECE}{n}"


def room_for(state: GameState, content: Content, base: str) -> bool:
    return len(pieces(state, base)) < content.config.arts.insight_piece_cap


# ── 效果池 ───────────────────────────────────────────────


def generals(content: Content, attribute: str) -> list[GeneralTrait]:
    return [t for t in content.traits.general if t.attribute == attribute]


def grand_of(content: Content, attribute: str) -> HighTrait | None:
    return next((h for h in content.traits.high if h.attribute == attribute), None)


def general(content: Content, key: str) -> GeneralTrait | None:
    return next((t for t in content.traits.general if t.key == key), None)


def grand(content: Content, grand_id: str | None) -> HighTrait | None:
    if not grand_id:
        return None
    return next((h for h in content.traits.high if h.id == grand_id), None)


# ── 一份意境的效果 ────────────────────────────────────────


def record(state: GameState, content: Content, world: WorldStateStore, insight_id: str, ins=None) -> InsightFx:
    """這一份的品質與效果：擲過的照紀錄；沒有紀錄（這一版之前悟到的、腳本塞進去的）照舊的樣子算，不存。"""
    got = state.player.insight_fx.get(insight_id)
    if got is not None:
        return got
    from . import arts, insights  # noqa: PLC0415  arts 會 import 這個模組

    ins = ins if ins is not None else insights.resolve(insight_id, content, world, state)
    if ins is None:
        return InsightFx(quality=LEGACY_QUALITY)
    if ins.secret_special:
        return InsightFx(quality=LEGACY_QUALITY)
    if arts.is_compound(content, ins):
        g = grand_of(content, ins.attribute)
        if g is not None:
            return InsightFx(quality=LEGACY_QUALITY, grand=g.id)
    layers = max(1, min(MAX_LAYERS, int(state.player.insight_strength.get(insight_id, ins.rank or 1))))
    return InsightFx(quality=LEGACY_QUALITY, general={ins.attribute: layers})


def quality_of(state: GameState, insight_id: str) -> str:
    got = state.player.insight_fx.get(insight_id)
    return got.quality if got is not None else LEGACY_QUALITY


def strength(state: GameState, insight_id: str) -> int:
    """這一份最深的一般功效是幾重（沒有一般功效的、沒有紀錄的照舊存檔的強度）：卡上的三節玉、揣摩到頂沒、兼容並蓄挑屬性都看它。"""
    got = state.player.insight_fx.get(insight_id)
    if got is not None:
        return max([1, *got.general.values()]) if got.general else 1
    return max(1, min(MAX_LAYERS, int(state.player.insight_strength.get(insight_id, 1))))


def effects(content: Content, fx: InsightFx) -> list[dict]:
    """畫卡用的效果清單：一般功效在前（照層數多的先），大獎在後。每一個 {key, name, layers, grand, desc}。"""
    from . import traits  # noqa: PLC0415

    out: list[dict] = []
    for key, layers in sorted(fx.general.items(), key=lambda kv: -kv[1]):
        t = general(content, key)
        if t is None:
            out.append({"key": key, "name": key, "layers": layers, "grand": False, "desc": ""})
            continue
        number = min(t.cap, t.per_layer * layers)
        extra = min(t.extra_cap, t.extra_per_layer * layers)
        desc = t.desc.replace("{value}", traits._value(t.hook, number)).replace("{extra}", traits._value(t.hook, extra))
        out.append({"key": key, "name": t.name, "layers": layers, "grand": False, "desc": desc})
    g = grand(content, fx.grand)
    if g is not None:
        out.append({"key": g.id, "name": g.name, "layers": 0, "grand": True, "desc": g.desc})
    return out


def label(content: Content, fx: InsightFx) -> str:
    """一行寫完：「掠影二重・流光」。"""
    parts = [f"{e['name']}{LAYER_MARKS.get(e['layers'], '')}" if not e["grand"] else e["name"] for e in effects(content, fx)]
    return "・".join(parts)


# ── 擲 ───────────────────────────────────────────────────


def _tianji(world: WorldStateStore) -> int:
    from . import secret_recipes  # noqa: PLC0415

    return secret_recipes.tianji_of(world)


def _rng(state: GameState, world: WorldStateStore, *parts: object) -> random.Random:
    p = state.player
    return random.Random("|".join(str(x) for x in ("悟", _tianji(world), p.name, *parts, p.own_serial, len(p.insights))))


def roll_quality(state: GameState, content: Content, rng: random.Random, strong: bool = False) -> str:
    cfg = content.config.arts
    odds = [max(0.0, float(cfg.insight_quality_odds.get(q, 0))) for q in QUALITIES]
    at = rng.choices(range(len(QUALITIES)), weights=odds if sum(odds) > 0 else None)[0]
    if strong:
        at += 1
    wis = int(state.player.stats.get("wis", 5))
    if rng.random() < min(cfg.insight_quality_wis_cap, max(0, wis - 5) * cfg.insight_quality_per_wis):
        at += 1
    return QUALITIES[min(at, len(QUALITIES) - 1)]


def roll_effects(content: Content, attribute: str, quality: str, rng: random.Random, compound: bool = False) -> InsightFx:
    """照品質擲一到兩個效果（見檔頭）。內容沒有功效表時只記那一路一層（測試內容）。"""
    cfg = content.config.arts
    pool = generals(content, attribute)
    if not pool:
        return InsightFx(quality=quality, general={attribute: 1})
    first = rng.choice(pool)
    fx = InsightFx(quality=quality, general={first.key: 1})
    second = cfg.insight_second.get(quality, 0.0) + (cfg.compound_second_bonus if compound else 0.0)
    if cfg.insight_max_effects >= 2 and rng.random() < second:
        g = grand_of(content, attribute)
        chance = cfg.insight_grand.get(quality, 0.0) * (cfg.compound_grand_scale if compound else 1.0)
        if g is not None and rng.random() < chance:
            fx.grand = g.id
        else:
            others = [t for t in pool if t.key != first.key]
            if others:
                fx.general[rng.choice(others).key] = 1
            elif g is not None:
                fx.grand = g.id
    return fx


def roll(
    state: GameState, content: Content, world: WorldStateStore, piece_id: str, *, strong: bool = False,
    quality: str | None = None, compound: bool = False,
) -> InsightFx:
    """這一份剛悟到（或合出來）：擲品質與效果、記下來。quality 給了就不擲品質（合出來的照兩份較好的）。"""
    from . import insights  # noqa: PLC0415

    ins = insights.resolve(piece_id, content, world, state)
    attribute = ins.attribute if ins is not None else ""
    rng = _rng(state, world, piece_id)
    q = quality if quality in QUALITIES else roll_quality(state, content, rng, strong)
    fx = roll_effects(content, attribute, q, rng, compound)
    state.player.insight_fx[piece_id] = fx
    return fx


def copy(state: GameState, content: Content, world: WorldStateStore, src: str, dst: str) -> InsightFx:
    fx = record(state, content, world, src).model_copy(deep=True)
    state.player.insight_fx[dst] = fx
    return fx


def better(a: str, b: str) -> str:
    return a if QUALITIES.index(a if a in QUALITIES else LEGACY_QUALITY) >= QUALITIES.index(b if b in QUALITIES else LEGACY_QUALITY) else b


def deepen(content: Content, a: InsightFx, b: InsightFx, rng: random.Random | None) -> InsightFx:
    """揣摩：兩份揉成一份（見檔頭）。rng 是 None 時不擲大獎（預覽用）。"""
    cfg = content.config.arts
    quality = better(a.quality, b.quality)
    general: dict[str, int] = dict(a.general)
    for key, layers in b.general.items():
        general[key] = min(MAX_LAYERS, general.get(key, 0) + layers)
    grand_id = a.grand or b.grand
    room = cfg.insight_max_effects - len(general) - (1 if grand_id else 0)
    if grand_id is None and room > 0 and rng is not None:
        attribute = next((t.attribute for t in content.traits.general if t.key in general), None)
        g = grand_of(content, attribute) if attribute else None
        if g is not None and rng.random() < cfg.insight_grand.get(quality, 0.0) * cfg.deepen_grand_scale:
            grand_id = g.id
    while len(general) + (1 if grand_id else 0) > cfg.insight_max_effects and len(general) > 1:
        weakest = min(general, key=lambda k: (general[k], k in a.general))  # 層數最少的；一樣少先拿掉第二份帶來的
        general.pop(weakest)
    return InsightFx(quality=quality, general=general, grand=grand_id)


def grand_chance(content: Content, a: InsightFx, b: InsightFx) -> float:
    """揣摩時擲到大獎的機會（預覽卡寫）：已經有大獎、或揉完沒有空位是 0。"""
    merged = deepen(content, a, b, None)
    if merged.grand is not None:
        return 0.0
    if len(merged.general) >= content.config.arts.insight_max_effects:
        return 0.0
    cfg = content.config.arts
    return min(1.0, cfg.insight_grand.get(merged.quality, 0.0) * cfg.deepen_grand_scale)


def deepen_rng(state: GameState, world: WorldStateStore, keep: str, gone: str) -> random.Random:
    return _rng(state, world, "揣摩", keep, gone)


def drop(state: GameState, insight_id: str) -> None:
    """這一份不在手上了（熔掉、揣摩用掉）：紀錄跟著拿掉。"""
    state.player.insight_fx.pop(insight_id, None)
    state.player.insight_strength.pop(insight_id, None)
