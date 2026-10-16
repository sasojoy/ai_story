"""合成的深度（合成與意境改法定案，企劃者 2026-10-16「合出來的意境不知道好壞，然後合成也一直無限往下沒有邏輯，本意是LLM
可以用創意做出新火花」；數字在 Config.fusion_depth）。

| 東西 | 做什麼 |
|---|---|
| 意境的重數 | 悟來的一重；合一次取兩個來源高的那一重再加一，最多 max_rank 重，到頂的不能再合（rank_of） |
| 圓融／駁雜 | 兩個來源相生或同屬性是圓融，其餘硬湊是駁雜（harmony）；一重不分 |
| 意境給幾層 | 融進武學時給 重數 ±1（圓融多一層、駁雜少一層，layers_of） |
| 武學的代數 | 基礎與內容寫的第零代；合一次多一代，最多 max_gen 代，到頂的不能再合（gen_of）；玩家看到的是境界：初成、精進、化境（gen_label） |
| 一脈相承 | 新屬性跟底的主屬性相同或相生：底的層數整串留著疊上；相剋：打散；不相干：留一半（fuse_traits、blend_traits） |
| 首創的走向 | 引擎照配方排幾種特別功效，模型挑一種、寫一句招意；清單外、叫不動照配方挑（directions、choose） |

舊存檔：這一版之前登記的武學與意境沒有 gen／rank／harmony，照血統（MartialArt.base、parents；Insight.parents）補算，
不重來、不改存檔。相生：剛快生陽、柔慢生陰、快柔生虛、剛慢生實（insights.PAIR_ATTRIBUTES），陰陽虛實與它的兩個來源也算相生；
相剋照 martial_arts.counters。
"""
from __future__ import annotations

import hashlib

from . import insights
from .martial_arts import Insight, MartialArt, counters
from .models import Content
from .state import GameState
from .world_state import WorldStateStore

SAME, BORN, CLASH, APART = "same", "born", "clash", "apart"
HARMONY, DISCORD = "圓融", "駁雜"
RANK_WORDS = ("", "一重", "二重", "三重", "四重", "五重")
GEN_WORDS = ("", "初成", "精進", "化境", "化境", "化境")  # 武學的境界（Joy 2026-10-16：玩家看不到「第幾代」）
RELATION_WORDS = {SAME: "一脈相承", BORN: "相生相承", CLASH: "相剋", APART: "不相干"}

# 玩家看得到的句子（待 joy 潤）
RANK_TOP = "「{name}」已是{rank}，圓滿了，不能再合。"
GEN_TOP = "【{name}】此功已臻化境，不能再往下合。"
KEEP_LINE = {  # 煉製頁的說明：這一爐的功效層數怎麼傳
    SAME: "與底同源，一脈相承：舊的功效全留著，疊上新的",
    BORN: "與底相生：舊的功效全留著，疊上新的",
    CLASH: "與底相剋：舊的功效打散，只剩新的",
    APART: "與底不相干：舊的功效只留一半",
}


def relation(a: str, b: str) -> str:
    """兩個屬性的關係：同一個、相生、相剋、不相干。"""
    if a == b:
        return SAME
    if counters(a, b):
        return CLASH
    if frozenset({a, b}) in insights.PAIR_ATTRIBUTES:
        return BORN
    for pair, made in insights.PAIR_ATTRIBUTES.items():
        if (made == a and b in pair) or (made == b and a in pair):
            return BORN
    return APART


def harmony(a: str, b: str) -> str:
    """兩個意境合在一起是圓融（同屬性相疊、相生）還是駁雜（其餘硬湊）。"""
    return HARMONY if relation(a, b) in (SAME, BORN) else DISCORD


def merge_attribute(a, b, seed: str) -> str:
    """意境＋意境合出來的屬性：陰陽虛實跟它自己的來源相生（陽＋剛）時合出陰陽虛實那一個；其他照 insights.merged_attribute
    （同屬性、兩兩相生照表、其餘照配方雜湊挑一個）。打造與武學＋武學照舊用 merged_attribute。"""
    for pair, made in insights.PAIR_ATTRIBUTES.items():
        if (made == a.attribute and b.attribute in pair) or (made == b.attribute and a.attribute in pair):
            return made
    return insights.merged_attribute(a, b, seed)


def _parents(insight: Insight, content: Content, world: WorldStateStore, state: GameState | None) -> list[Insight]:
    found = (insights.resolve(i, content, world, state) for i in insight.parents)
    return [i for i in found if i is not None]


def rank_of(
    insight: Insight, content: Content, world: WorldStateStore, state: GameState | None = None, _depth: int = 0,
) -> int:
    """這個意境幾重：記了的照記的；這一版之前合的照兩個來源補算（取高的再加一）；悟來的一重。最多 max_rank。"""
    top = content.config.fusion_depth.max_rank
    if insight.rank:
        return min(top, insight.rank)
    if not insight.parents:
        return 1
    if _depth > 8:  # 舊資料萬一有環，不要無窮遞迴
        return top
    parents = _parents(insight, content, world, state)
    below = max((rank_of(p, content, world, state, _depth + 1) for p in parents), default=1)
    return min(top, below + 1)


def harmony_of(insight: Insight, content: Content, world: WorldStateStore, state: GameState | None = None) -> str | None:
    """圓融、駁雜，或一重的 None：記了的照記的；這一版之前合的照兩個來源的屬性補算（來源查不到的當駁雜）。"""
    if insight.harmony:
        return insight.harmony
    if not insight.parents:
        return None
    parents = _parents(insight, content, world, state)
    if len(insight.parents) == 2 and insight.parents[0] == insight.parents[1] and parents:
        return HARMONY  # 自己跟自己合
    if len(parents) < 2:
        return DISCORD
    return harmony(parents[0].attribute, parents[1].attribute)


def merged_depth(a: Insight, b: Insight, content: Content, world: WorldStateStore, state: GameState | None) -> tuple[int, str]:
    """這兩個合出來會是幾重、圓融還是駁雜。"""
    top = content.config.fusion_depth.max_rank
    rank = min(top, max(rank_of(a, content, world, state), rank_of(b, content, world, state)) + 1)
    return rank, harmony(a.attribute, b.attribute)


def rank_problem(a: Insight, b: Insight, content: Content, world: WorldStateStore, state: GameState | None) -> tuple[str, str] | None:
    """兩個裡面有到頂的：（那一句, 兩三個字）；都還能合是 None。"""
    top = content.config.fusion_depth.max_rank
    for thing in (a, b):
        if rank_of(thing, content, world, state) >= top:
            return RANK_TOP.format(name=thing.name, rank=RANK_WORDS[min(top, len(RANK_WORDS) - 1)]), "已到頂"
    return None


def layers_of(insight: Insight, content: Content, world: WorldStateStore, state: GameState | None = None) -> int:
    """融進武學時這個意境給幾層功效：重數，圓融多 harmony_bonus、駁雜少 clash_penalty，至少一層。"""
    cfg = content.config.fusion_depth
    rank = rank_of(insight, content, world, state)
    mood = harmony_of(insight, content, world, state) if rank > 1 else None
    bonus = cfg.harmony_bonus if mood == HARMONY else -cfg.clash_penalty if mood == DISCORD else 0
    return max(1, rank + bonus)


def label(insight: Insight, content: Content, world: WorldStateStore, state: GameState | None = None) -> str:
    """卡上那幾個字：「二重・圓融」「一重」。"""
    rank = rank_of(insight, content, world, state)
    word = RANK_WORDS[min(rank, len(RANK_WORDS) - 1)]
    mood = harmony_of(insight, content, world, state) if rank > 1 else None
    return f"{word}・{mood}" if mood else word


def gen_of(art: MartialArt | None, content: Content, world: WorldStateStore, _depth: int = 0) -> int:
    """這門武學第幾代：記了的照記的；內容寫的（基礎、本命、部下的）與舊的自創、煉製（沒有底）第零代；這一版之前合的照底或
    兩門來源補算（找不到來源的當第一代）。最多 max_gen。"""
    from . import team  # team 會 import fusion、fusion 會 import 這裡

    if art is None:
        return 0
    top = content.config.fusion_depth.max_gen
    if art.gen is not None:
        return min(top, art.gen)
    if art.id in content.skills or art.origin in ("historical", "basic") or (art.origin != "fused" and not art.base and not art.parents):
        return 0
    if _depth > 8:
        return top
    sources = [team.resolve_art(i, content, world) for i in ([art.base] if art.base else []) + list(art.parents)]
    sources = [s for s in sources if s is not None]
    if not sources:
        return 1
    return min(top, max(gen_of(s, content, world, _depth + 1) for s in sources) + 1)


def gen_label(gen: int) -> str:
    return GEN_WORDS[min(gen, len(GEN_WORDS) - 1)] if gen > 0 else ""


def gen_problem(art: MartialArt, content: Content, world: WorldStateStore) -> str | None:
    """這門已經到頂（max_gen 代）：那一句；還能合是 None。"""
    gen = gen_of(art, content, world)
    if gen >= content.config.fusion_depth.max_gen:
        return GEN_TOP.format(name=art.name)
    return None


def _kept(content: Content, old: list[str], rel: str) -> list[str]:
    if rel in (SAME, BORN):
        return list(old)
    if rel == CLASH:
        return []
    return old[: int(len(old) * content.config.fusion_depth.apart_keep)]


def fuse_traits(content: Content, base: MartialArt, attribute: str, layers: int) -> list[str]:
    """武學＋意境的一般功效（屬性的清單，一個屬性一層）：新意境的屬性 layers 層排在前面，底的照它跟底的主屬性的關係傳下來
    （_kept），一門最多 max_layers 層、擠掉最舊的。只傳一般功效，特別功效不傳。"""
    from .traits import traits_of

    out = [attribute] * layers + _kept(content, traits_of(base), relation(attribute, base.attribute))
    return out[: content.config.fusion_depth.max_layers]


def blend_traits(content: Content, a: MartialArt, b: MartialArt, attribute: str) -> list[str]:
    """武學＋武學：合出來的屬性一層，兩門各照自己的主屬性跟它的關係傳下來（照 id 排，不分先後）。"""
    from .traits import traits_of

    out = [attribute]
    for art in sorted((a, b), key=lambda x: x.id):
        out += _kept(content, traits_of(art), relation(attribute, art.attribute))
    return out[: content.config.fusion_depth.max_layers]


def fuse_relation(base: MartialArt, attribute: str) -> str:
    return relation(attribute, base.attribute)


# ── 首創的走向 ─────────────────────────────────────────


def directions(content: Content, key: str, tianji: int) -> list[str]:
    """這一門首創時排給模型挑的幾種走向（特別功效的 id，只從共用的 pool 挑）：照「天機|配方鍵」排，同一個配方同一季永遠一樣。"""
    pool = sorted(t.id for t in content.traits.special if t.pool)
    pool.sort(key=lambda sid: hashlib.sha256(f"{tianji}|{key}|走向|{sid}".encode("utf-8")).digest())
    return pool[: content.config.fusion_depth.directions]


def rule_pick(options: list[str], key: str, tianji: int) -> str | None:
    """模型沒挑（清單外、叫不動、假人與整季機器人）時照配方挑一種。"""
    if not options:
        return None
    digest = hashlib.sha256(f"{tianji}|{key}|走向挑".encode("utf-8")).digest()
    return options[digest[0] % len(options)]


MARK_OPEN, MARK_CLOSE = "〔", "〕"


def mark(direction: str, note: str) -> str:
    """模型挑的走向寫在說明前面（「〔連環〕一句招意」），C 段照它認；說明本身是那一句招意。"""
    return f"{MARK_OPEN}{direction}{MARK_CLOSE}{note}"


def choose(content: Content, options: list[str], note: str, key: str, tianji: int) -> tuple[str | None, str]:
    """C 段：說明開頭寫了清單上的走向（mark）就用它、說明換成後面那一句招意；沒寫、寫了清單外的照配方挑、說明照舊。
    回（特別功效 id, 說明）。"""
    from .traits import special

    names = {special(content, sid).name: sid for sid in options if special(content, sid) is not None}
    if note.startswith(MARK_OPEN) and MARK_CLOSE in note:
        picked, rest = note[1:].split(MARK_CLOSE, 1)
        if picked.strip() in names:
            return names[picked.strip()], rest.strip()
        note = rest.strip()
    return rule_pick(options, key, tianji), note


def direction_lines(content: Content, options: list[str]) -> str:
    """取名提示裡排給模型的走向：一行一種，名字與一句說明（不寫數字以外的東西也行，說明本來就是內容寫的）。"""
    from .traits import special

    rows = [special(content, sid) for sid in options]
    return "\n".join(f"- {sp.name}：{sp.desc}" for sp in rows if sp is not None)
