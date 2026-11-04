"""五項屬性（屬性與跨季架構 v2 第三節；第 ② 階段第 1 批，2026-11-04）：武力、統御、悟性、身法、魅力（Joy 11/4 定顯示名混搭；
鍵 str、lead、int、spd、cha）。

規則都在 Config.attributes.v2（AttrV2Rules）：主機開關加上開季時蓋的章（WorldState.attrs_v2）才算，正在跑的季一個字都不變。
- 本人的值不存進存檔的 stats，讀的時候算：base ＋（等級 − 1）× 這一季的配比 ＋ 送點自己配的（PlayerState.attr_alloc）。
  配比季初自己挑（五套預設或自己配，合計固定），沒挑的照 default_preset 長；季中改配比一律回溯。
- 舊的鍵（臂力、身法、根骨、悟性）照 legacy 對到新的一項：內容的檢定照舊寫 agi、wis，不必改；博聞拔掉。
- 還沒改寫成新尺度的舊讀點（修練機率、悟意境、閉關心得……）讀 v1_value：新尺度的值換回舊尺度（5 起、每級約 0.2），
  公式不動也照樣有作用，之後一處一處改成走效果表。
這個模組不 import team（team 反過來 import 這裡）。
"""
from __future__ import annotations

from .models import Content
from .state import GameState

CUSTOM = "custom"
V1_BASE = 5  # 舊尺度的起點（team.BASE_STAT）


def on(content: Content, world) -> bool:
    """這一季是五項屬性：主機的開關開著，而且這一季開季時蓋了章。world 是 WorldState（None 一律舊規則）。"""
    return world is not None and content.config.attributes.v2.enabled and bool(getattr(world, "attrs_v2", False))


def keys(content: Content) -> tuple[str, ...]:
    return tuple(content.config.attributes.v2.keys)


def key_of(content: Content, key: str) -> str | None:
    """內容與舊程式寫的鍵在新的季是哪一項：新的鍵照原樣，舊的照 legacy 對過去；對不到（博聞、銀兩……）是 None。"""
    cfg = content.config.attributes.v2
    if key in cfg.keys:
        return key
    return cfg.legacy.get(key)


def names(content: Content, world) -> dict[str, str]:
    """這一季畫面上的名字（鍵 → 顯示名）：新的季五項照 content/attributes_v2.json（武力、統御……），其餘照 Config.stat_names。"""
    out = dict(content.config.stat_names)
    if on(content, world):
        out.update({a.key: a.name for a in content.attributes_v2})
    return out


def preset(content: Content, key: str | None):
    return next((p for p in content.config.attributes.v2.presets if p.key == key), None)


def split(state: GameState, content: Content) -> dict[str, int]:
    """這個人這一季每級怎麼長：自己配的、挑的那一套，或還沒挑時的預設。"""
    p = state.player
    if p.growth_preset == CUSTOM and p.growth_custom:
        return dict(p.growth_custom)
    chosen = preset(content, p.growth_preset) or preset(content, content.config.attributes.v2.default_preset)
    return dict(chosen.split)


def value(state: GameState, content: Content, key: str) -> float:
    """本人這一項現在多少（key 是新的鍵）。"""
    cfg = content.config.attributes.v2
    level = state.player.member.level
    return float(cfg.base + (level - 1) * split(state, content).get(key, 0) + state.player.attr_alloc.get(key, 0))


def values(state: GameState, content: Content) -> dict[str, float]:
    return {k: value(state, content, k) for k in keys(content)}


def expect(content: Content, level: int, key: str | None = None) -> float:
    """這個等級的「平均人」這一項有多少（第五節 expect(level, attr)）：均分的配比、送點也均分。key 先不分（五項一樣）。"""
    cfg = content.config.attributes.v2
    n = len(cfg.keys)
    return cfg.base + (level - 1) * cfg.per_level / n + (level // cfg.bonus_every) * cfg.bonus_points / n


def v1_value(state: GameState, content: Content, new_value: float) -> float:
    """新尺度的值換回舊尺度（5 起、每級約 stat_points_per_level ÷ 5）：還沒改寫的舊公式照舊讀得到差別。"""
    cfg = content.config.attributes.v2
    ratio = cfg.per_level / max(1, content.config.stat_points_per_level)
    return V1_BASE + (new_value - cfg.base) / ratio


def legacy(state: GameState, content: Content, key: str, default: float = V1_BASE) -> float:
    """本人舊尺度的一項屬性（team.v1_stat 的本體；不 import team 的模組直接叫這裡）：舊的季照存檔（沒有這一項當 default），
    五項屬性的季照 legacy 對到新的一項、換回舊尺度，對不到的（博聞）當基準。"""
    if on(content, getattr(state, "world", None)):
        new = key_of(content, key)
        return v1_value(state, content, value(state, content, new)) if new else float(V1_BASE)
    return state.player.stats.get(key, default)


def foe_level(content: Content, difficulty: float) -> float:
    """對手的難度換成等級（Config.attributes.v2.foe_levels，中間照直線、兩頭夾住）。"""
    table = content.config.attributes.v2.foe_levels
    if difficulty <= table[0][0]:
        return table[0][1]
    for (p0, l0), (p1, l1) in zip(table, table[1:]):
        if difficulty <= p1:
            return l0 + (l1 - l0) * (difficulty - p0) / (p1 - p0)
    return table[-1][1]


def grown(content: Content, level: float, aptitude: float) -> float:
    """資質 aptitude（平均是 foe_aptitude）的人長到 level 級，一項有多少：跟平均人同一條曲線，照資質放大縮小成長的那一截。"""
    cfg = content.config.attributes.v2
    return cfg.base + (expect(content, level) - cfg.base) * aptitude / cfg.foe_aptitude


def foe_values(content: Content, squad, level: float | None = None) -> dict[str, float]:
    """對手的五項（第四節「同一把尺」）：等級照隊伍寫的、沒寫照難度換；資質照隊伍寫的、沒寫當平均。"""
    cfg = content.config.attributes.v2
    lv = level if level is not None else (squad.level if getattr(squad, "level", None) else foe_level(content, squad.difficulty))
    apt = getattr(squad, "aptitude", {}) or {}
    return {k: grown(content, lv, apt.get(k, cfg.foe_aptitude)) for k in cfg.keys}


def from_v1(content: Content, level: int, v1: dict[str, float]) -> dict[str, float]:
    """舊尺度的人（同伴照內容寫的臂力、身法……）換成新的五項：對得到的照 legacy 反過來換，魅力這種沒有舊值的當平均人。"""
    cfg = content.config.attributes.v2
    ratio = cfg.per_level / max(1, content.config.stat_points_per_level)
    back = {new: old for old, new in cfg.legacy.items()}
    return {k: (cfg.base + (v1[back[k]] - V1_BASE) * ratio if back.get(k) in v1 else expect(content, level)) for k in cfg.keys}


def bonus_between(content: Content, before: int, after: int) -> int:
    """從第 before 級升到第 after 級送幾點（每 bonus_every 級 bonus_points 點）。"""
    cfg = content.config.attributes.v2
    return (after // cfg.bonus_every - before // cfg.bonus_every) * cfg.bonus_points


def growth_problem(content: Content, key: str, custom: dict[str, int] | None = None) -> str | None:
    """挑配比對不對：預設的五套之一，或自己配（五項寫齊、每項至少 custom_min、合計 per_level）。對的回 None。"""
    cfg = content.config.attributes.v2
    if key != CUSTOM:
        return None if preset(content, key) is not None else "（沒有這一套配比。）"
    custom = custom or {}
    names = {a.key: a.name for a in content.attributes_v2} or content.config.stat_names
    if set(custom) != set(cfg.keys) or any(not isinstance(v, int) for v in custom.values()):
        return f"自己配要寫齊{'、'.join(names.get(k, k) for k in cfg.keys)}。"
    if any(v < cfg.custom_min for v in custom.values()):
        return f"每一項每級至少長 {cfg.custom_min} 點。"
    if sum(custom.values()) != cfg.per_level:
        return f"五項合計要是 {cfg.per_level} 點（現在 {sum(custom.values())}）。"
    return None


def pick(state: GameState, content: Content, key: str, custom: dict[str, int] | None = None) -> str:
    """挑這一季的配比（回溯：照現在的等級整條重算）。回一句給玩家看的話；挑不成回的是理由（呼叫端先問 growth_problem）。"""
    p = state.player
    p.growth_preset = key
    p.growth_custom = dict(custom) if key == CUSTOM else {}
    names = {a.key: a.name for a in content.attributes_v2} or content.config.stat_names
    rows = split(state, content)
    plan = "、".join(f"{names.get(k, k)} {rows[k]}" for k in keys(content))
    title = "自己配" if key == CUSTOM else preset(content, key).name
    return f"這一季照「{title}」長：每升一級 {plan}。"


def view(state: GameState, content: Content) -> dict:
    """狀態列的配比那一塊（網頁畫挑配比的鈕）：挑了哪一套、每一套怎麼長、自己配的規矩。"""
    cfg = content.config.attributes.v2
    names = {a.key: a.name for a in content.attributes_v2} or content.config.stat_names
    return {
        "chosen": state.player.growth_preset,
        "presets": [{"key": p.key, "name": p.name, "split": [[names.get(k, k), p.split[k]] for k in cfg.keys]} for p in cfg.presets],
        "keys": [[k, names.get(k, k)] for k in cfg.keys],
        "per_level": cfg.per_level,
        "custom_min": cfg.custom_min,
        "now": [[names.get(k, k), v] for k, v in split(state, content).items()],
    }
