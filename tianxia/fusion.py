"""合成與合併（武學與成長設計 3.2、3.4）。

| 誰 | 做什麼 |
|---|---|
| 模型 | 只取名字＋一句說明，一個數字都不碰 |
| 引擎 | 配方、屬性、正邪、品質、成本、全服登記 |

合成：武學＋意境 → 新武學，底留著；種類跟著底；屬性與正邪跟著意境；從第一成開始。全服登記的那一筆是下品；
玩家拿到的那一份照這一爐的搭配擲（企劃者 2026-10-06：底的品質與成數、意境的來歷、屬性合不合、悟性，見 fuse_odds；
普通搭配平均是 Config.fuse_quality_odds 的下品五成、中品三成、上品兩成；序章那一爐固定下品），
擲到的那幾階熔的時候不給加給（library.melt_value）。不繼承底的品質——企劃者 2026-10-05 改了設計 3.4：
絕學的底合出絕學的複本、馬上熔掉就賺 40 心得，是個無本的金錢迴圈；底的好壞只留在底身上，
新武學靠修練一階一階往上爬，熔的時候才領得到那幾階的加給，見 library.melt_refund。
合併：意境＋意境（可以是同一個）→ 新意境，兩個都留著；屬性與正邪照 insights 的規則。合併要花體力（Config.merge_stamina）——
合併→熔掉→再合併每一圈淨賺心得，企劃者 2026-10-05 的裁示是不擋、讓每一圈都付一次體力。
武學＋武學（設計 12.3）：兩門都留著，新武學的種類、屬性、正邪、記的意境都由兩門與配方決定（blend_shape），兩門來源記在
MartialArt.parents；配方鍵 blend_key 不分先後。
三種合成同一套價錢（設計 12.1）：一律 Config.fuse_xinde／merge_xinde 心得＋fuse_stamina／merge_stamina 體力，真的合成了才收。
合到舊的（設計 12.2）：一個組合這一季第一次被合時，規則（landing）決定會不會合到一個已知的合成物；候選兩個以上由模型挑
（A 段開「挑」的單，B 段 naming.pick，C 段 landing.choose 重驗），不然規則挑。合到的那一門登記成這個配方（link_recipe），
本身不動；合到你已經有的不收錢。
配方全服共享：第一個合出來的人等模型取名（叫不動就走退路字表），之後查表、不用等。
伺服器上的取名在行動鎖外（最終審查 Critical 1）：forge_request（A，鎖內）→ naming.generate（B，鎖外）→
fuse／merge(proposed=...)（C，鎖內，整個重驗再登記、收費）。沒給 proposed 才在這裡叫模型（整季機器人、腳本、測試）。
「已經有了」一律照功法的 id 認（改名之後顯示的名字跟 id 不一樣）。
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from . import insights, landing, library, naming, sensing, team, traits
from .martial_arts import ATTRIBUTE_COUNTERS, Insight, MartialArt, generate_from_name, shown_creator
from .models import Content, PresetRecipe
from .ollama_client import OllamaClient
from .rules import add_rumor, season_one
from .state import Echo, GameState
from .world_state import WorldStateStore

FUSE_PREFIX = "融|"
MERGE_PREFIX = "合|"
LOW_ONLY = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}  # 全服登記的那一份一律是下品


@dataclass(frozen=True)
class QualityOdds:
    """一爐合成出新武學時，自己那一份的品質機率（%，下品＋中品＋上品＝100）與說明那一句的原因（最多兩個）。"""

    odds: dict[str, float]
    reasons: tuple[str, ...] = ()


def _points(content: Content, scored: list[tuple[str, float]]) -> QualityOdds:
    """把各因素的分數加成造化分，從普通搭配的平均（Config.fuse_quality_odds）往上或往下推，上品、下品各自夾住，中品是剩下的。"""
    cfg = content.config
    rule = cfg.fuse_quality
    base = cfg.fuse_quality_odds
    total = sum(base.values()) or 1
    up0, low0 = base.get("上品", 0) * 100 / total, base.get("下品", 0) * 100 / total
    score = sum(points for _, points in scored)
    up = min(max(up0 + score * rule.up_per_point, rule.up_range[0]), rule.up_range[1])
    low = min(max(low0 - score * rule.low_per_point, rule.low_range[0]), rule.low_range[1])
    up, low = round(up), round(low)
    odds = {"下品": float(low), "中品": float(max(0, 100 - up - low)), "上品": float(up)}
    shown = sorted((item for item in scored if abs(item[1]) >= rule.shown_from), key=lambda item: -abs(item[1]))
    reasons = []
    for factor, points in shown:
        line = rule.lines.get(factor, ["", ""])[0 if points > 0 else 1]
        if line and len(reasons) < 2:
            reasons.append(line)
    return QualityOdds(odds, tuple(reasons))


def _art_points(state: GameState, content: Content, arts: list[tuple[str, MartialArt]]) -> list[tuple[str, float]]:
    """底的品質與成數（兩門時取平均）＋悟性。"""
    rule = content.config.fuse_quality
    quality = sum(rule.base_quality.get(art.quality, 0) for _, art in arts) / len(arts)
    levels = [library.level_of(state, art_id) or 1 for art_id, _ in arts]
    level = (sum(levels) / len(levels) - rule.level_center) * rule.level_point
    wis = (team.stat_factor(content, state.player.stats.get("wis", team.BASE_STAT)) - 1) * 100 * rule.wis_weight
    return [("quality", quality), ("level", level), ("wis", wis)]


def _attribute_points(content: Content, a: str, b: str) -> float:
    rule = content.config.fuse_quality
    if a == b:
        return rule.same_attribute
    return rule.counter_attribute if ATTRIBUTE_COUNTERS.get(a) == b else 0.0


def insight_points(state: GameState, content: Content, insight: Insight) -> float:
    """意境的來歷：內容寫好的基本意境 0；有正邪的（善名、惡名悟來的）、合併出來的另外加分；自己首悟的再加。"""
    rule = content.config.fuse_quality
    points = rule.insight_merged if insight.parents else (rule.insight_lean if insight.lean != "無" else 0.0)
    if insight.creator and insight.creator == state.player.name:
        points += rule.insight_own
    return points


def fuse_odds(state: GameState, content: Content, art_id: str, base: MartialArt, insight: Insight) -> QualityOdds:
    """武學＋意境這一爐的品質機率：底自己那一份的品質與成數、意境的來歷、兩者屬性合不合、你的悟性。
    照這一爐的組成算，配方有沒有人合過、會不會合到舊的都一樣。"""
    scored = _art_points(state, content, [(art_id, base)])
    scored.append(("insight", insight_points(state, content, insight)))
    scored.append(("attribute", _attribute_points(content, base.attribute, insight.attribute)))
    return _points(content, scored)


def blend_odds(state: GameState, content: Content, a: str, art_a: MartialArt, b: str, art_b: MartialArt) -> QualityOdds:
    """武學＋武學這一爐的品質機率：兩門自己那一份的品質與成數（平均）、兩門屬性合不合、你的悟性。"""
    scored = _art_points(state, content, [(a, art_a), (b, art_b)])
    scored.append(("attribute", _attribute_points(content, art_a.attribute, art_b.attribute)))
    return _points(content, scored)


def roll_quality(odds: QualityOdds | None, rng: random.Random | None) -> str:
    """擲合成出新武學自己那一份的品質。rng 或 odds 是 None 時不擲、照劇本是下品（序章那一爐、直接呼叫的腳本與測試）。"""
    if rng is None or odds is None or not any(odds.odds.values()):
        return "下品"
    return rng.choices(list(odds.odds), weights=list(odds.odds.values()))[0]


def quality_odds_text(odds: QualityOdds) -> str:
    """合成前的說明寫這一爐的機率，不寫確定的品級：「下品 19%、中品 46%、上品 35%（兩股氣息相投、底子厚實）」。"""
    text = "、".join(f"{q} {round(w)}%" for q, w in odds.odds.items() if w > 0)
    return text + (f"（{'、'.join(odds.reasons)}）" if odds.reasons else "")


OWN_TOKEN = "屬:"


def fuse_key(art_id: str, insight_id: str, attribute: str | None = None) -> str:
    """武學＋意境的配方鍵。私有意境（感悟悟來的，insights.is_own）沒有全服的 id：照它的屬性認（悟意境設計 0.2b 第 4 點），
    寫成「融|底+屬:柔」——誰拿自己悟的哪一個柔意境融這門底，合出來的都是全服同一門；attribute 就是那個屬性。"""
    if insights.is_own(insight_id):
        return f"{FUSE_PREFIX}{art_id}+{OWN_TOKEN}{attribute}"
    return f"{FUSE_PREFIX}{art_id}+{insight_id}"


def fuse_key_for(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> str:
    """fuse_key，私有意境的屬性從這個玩家自己的存檔查。查不到（失效的引用）照 id 寫——那一爐本來就會被擋下來。"""
    insight = insights.resolve(insight_id, content, world, state)
    return fuse_key(art_id, insight_id, insight.attribute if insight is not None else None)


def merge_key(a: str, b: str) -> str:
    return MERGE_PREFIX + insights.merge_key(a, b)


BLEND_PREFIX = "兼|"
KINDS = ("內功", "武學")


def blend_key(a: str, b: str) -> str:
    """武學＋武學的配方鍵：兩門 id 排序後接起來（A＋B 與 B＋A 是同一個配方，設計 12.3）。"""
    return BLEND_PREFIX + "+".join(sorted((a, b)))


@dataclass(frozen=True)
class Shape:
    """武學＋武學本來會得到的（設計 12.3）：種類、屬性、正邪，以及修練要記的意境。"""

    kind: str
    attribute: str
    lean: str
    insight: str | None
    insight_attr: str | None = None  # 修練認的意境屬性（私有意境融出來的那一門 insight 是 None、只記屬性）


def _bit(seed: str, what: str) -> int:
    return hashlib.sha256(f"{seed}|{what}".encode("utf-8")).digest()[0] % 2


def blend_shape(a: MartialArt, b: MartialArt, seed: str) -> Shape:
    """設計 12.3：兩門同種類就是那一種，一內一外由配方決定（兩種各半）；屬性、正邪照意境合併的規則；
    修練記屬性跟結果一樣的那一門的意境，兩門都一樣或都不一樣由配方挑一門，挑到的那門沒記意境（基礎武學）就用另一門的。
    跟參數順序無關。seed 是 recipe_seed 的第二個值。"""
    first, second = sorted((a, b), key=lambda art: art.id)
    kind = a.kind if a.kind == b.kind else KINDS[_bit(seed, "kind")]
    attribute = insights.merged_attribute(first, second, seed)
    matching = [art for art in (first, second) if art.attribute == attribute]
    keeper = matching[0] if len(matching) == 1 else (first, second)[_bit(seed, "insight")]
    other = second if keeper is first else first
    held = keeper if keeper.insight or keeper.insight_attr else other
    return Shape(kind, attribute, insights.merged_lean(first, second), held.insight, held.insight_attr)


def merge_shape(world: WorldStateStore, a: Insight, b: Insight) -> tuple[str, str]:
    """意境＋意境本來會得到的（屬性, 正邪）：配方種子（天機＋配方鍵）加上兩個來源決定，跟參數順序無關（設計 12.6）。
    merge 照它登記，煉製頁的預覽（skillview.forge_line）照它寫——兩邊同一個函式，預覽不會跟結果各說各話（FB-082）。"""
    seed = recipe_seed(world, merge_key(a.id, b.id))[1]
    return insights.merged_attribute(a, b, seed), insights.merged_lean(a, b)


def _full_line(state: GameState, content: Content) -> str:
    cap = library.cap_of(state, content)
    return f"武學與意境已經滿了（{library.held_count(state)}/{cap}），先熔掉一些。"


def _xinde_line(state: GameState, price: int, what: str) -> str | None:
    xinde = state.player.stats.get("xinde", 0)
    return None if xinde >= price else f"心得不足：{what}要 {price} 點，你只有 {xinde} 點。"


def _stamina_line(state: GameState, need: int, what: str) -> str | None:
    return None if state.player.stamina >= need else f"體力不足：{what}一次要 {need}。"


def _charge(state: GameState, xinde: int, stamina: int) -> list[str]:
    """真的合成了才收（設計 12.1）：心得與體力一起扣，回寫成數值變化的兩行。被拒絕、合到你已經有的都不收。"""
    p = state.player
    p.stats["xinde"] = p.stats.get("xinde", 0) - xinde
    p.stamina -= stamina
    return [f"心得 -{xinde}", f"體力 -{stamina}"]


def recipe_seed(world: WorldStateStore, key: str) -> tuple[int, str]:
    """這一季的天機與這個配方的種子：同一個配方同一季，屬性、種類、合不合到舊的都一樣（設計 12.2、12.6）。"""
    tianji = world.read().tianji
    return tianji, f"{tianji}|{key}"


PICK_SYSTEM = (
    "你是武俠小說裡的說書人。有人把兩樣東西合在一起，結果是下面清單裡的哪一個？"
    "你只負責挑，**不要提到任何數字、品質或威力**。全程使用繁體中文。"
)
PICK_RULES = (
    "從清單裡挑一個意思最接近的。name 只回清單上的名字本身、一字不改，不要帶括號、屬性或說明；description 留空。"
)


def _dash_note(thing: MartialArt | Insight) -> str:
    """送給模型的提示裡，一門武學或一個意境名字後面的「——說明」；沒有說明就是空的。"""
    return f"——{thing.note}" if thing.note else ""


def _pick_messages(what: str, items: list[MartialArt] | list[Insight]) -> list[dict[str, str]]:
    listing = "\n".join(f"- {i.name}（屬{i.attribute}）" + _dash_note(i) for i in items)
    return [
        {"role": "system", "content": PICK_SYSTEM},
        {"role": "user", "content": f"{what}\n\n清單：\n{listing}\n\n{PICK_RULES}"},
    ]


def _pick_request(
    kind: str, key: str, name_kind: str, messages: list[dict[str, str]], items: list[MartialArt] | list[Insight],
) -> naming.NamingRequest | None:
    """合到舊的：候選兩個以上才要模型挑、開「挑」的單；只有一個就是它，不必開單。"""
    if len(items) < 2:
        return None
    return naming.NamingRequest(kind, key, name_kind, messages, choices=tuple(i.name for i in items))


def _picked(
    client: OllamaClient | None, proposed: tuple[str | None, str] | None,
    messages: list[dict[str, str]], items: list[MartialArt] | list[Insight],
) -> str | None:
    """合到舊的要挑哪一個名字：只有一個候選不必問；鎖外先挑好的（proposed，C 段）照用；沒給才在這裡問模型
    （整季機器人、腳本、測試）。對不上候選的名字交給 landing.choose 改由規則挑。"""
    if len(items) < 2:
        return None
    if proposed is not None:
        return naming.clean_name(proposed[0]) if proposed[0] else None
    name, _ = naming.pick(client, messages, tuple(i.name for i in items))
    return name


def _arrival(art: MartialArt, first: bool, landed: bool) -> str:
    """新武學那一則訊息的後半：模型寫的說明（有的話），再接首創、照著合、或合到舊的那一句。"""
    tail = f"\n{art.note}" if art.note else ""
    if art.preset:  # 師門功夫沒有首創者：老手的另一個配方合到它，也寫師門傳下來的（不是「不知名的前人」）
        return tail + "\n這是師門傳下來的路數。"
    if first:
        return tail + "\n這是江湖上第一次有人合出這一門——從此它就叫這個名字。"
    by = shown_creator(art) or "不知名的前人"
    return tail + (f"\n這一門由{by}首創。" if landed else f"\n這一門由{by}首創，你照著合出了同一門。")


def _special_and_note(content: Content, new_traits: list[str], key: str, tianji: int) -> tuple[str | None, str]:
    """新武學的特別功效（配方加這一季的天機擲，13.4）與取名提示那一行（寫著它的一般功效 new_traits 與特別功效）。
    一般功效是來路定的，由呼叫端先算好（traits.inherit_fuse／inherit_blend）。A 段開單、C 段登記與取名都走這一個——
    同一個配方、同一季的天機，算出來一樣，單子上的提示才跟登記的那一門對得上。"""
    special_id = traits.roll_special(content, key, tianji)
    return special_id, traits.naming_note(content, new_traits, special_id)


def _special_rumor(state: GameState, content: Content, art: MartialArt, first: bool) -> list[str]:
    """第一次合出帶特別功效的武學：江湖上傳一句（13.4，不寫配方），也回給玩家看。後來照著合的人不再傳。
    這是世界層的傳聞：具名（named=True），寫真正的名號、不照匿名行走改成「某位少俠」（企劃者定：只有地方傳聞才有不具名這回事），
    首創者那一門武學自己的 creator_shown 也一律寫名號（傳聞分層第七節）。
    不帶地點：天下大事沒有發生地，輿圖的 ✦ 與地點詳情才不會把鑄功法的人此刻的位置標給每個陣營（傳聞分層一，F4）。"""
    special = traits.special(content, art.special) if first else None
    if special is None:
        return []
    line = f"江湖上傳開了：{state.player.name}合出一門帶〔{special.name}〕的【{art.name}】。"
    add_rumor(state, line, None, content=content, named=True)
    return [line]


ECHO_RUMOR = "江湖上照著{who}首創的{thing}練出來的人越來越多了。"


def echo(state: GameState, content: Content, thing: MartialArt | Insight, first: bool) -> None:
    """首創名望回饋（Config.first_echo）：你合出別人首創的那一門（照著合、合到舊的都算），在這一季的 WorldState.echoes 記你一筆；
    首創者自己的 Game 同步時補名望（Game._deliver_echoes），這裡不去動別人的角色。一個人一門只算一次、最多算 cap 個人，湊滿那一下
    江湖上傳一句（具名：首創者記下的名號）。自己首創的、師門配方、內容寫好的（沒有首創者）不記；第一季沒開著時什麼都不做。"""
    me = state.player.name
    if first or not thing.creator or thing.creator == me or getattr(thing, "preset", False):
        return
    if not season_one(content, state.world):
        return
    rule = content.config.first_echo
    shown = f"【{thing.name}】" if isinstance(thing, MartialArt) else f"「{thing.name}」"
    entry = state.world.echoes.setdefault(thing.id, Echo(creator=thing.creator, name=shown))
    if me in entry.followers or len(entry.followers) >= rule.cap:
        return
    entry.followers.append(me)
    if len(entry.followers) == rule.cap:
        add_rumor(state, ECHO_RUMOR.format(who=shown_creator(thing) or thing.creator, thing=shown), None, content=content, named=True)


def can_forge(state: GameState, content: Content) -> bool:
    """現在有沒有可能拿意境開爐：持有沒滿、有意境，而且付得起一次武學＋意境（還要有武學）或一次合併（設計 12.1：
    兩種都花心得與體力）。只看結構、不查全服配方表（那要打資料庫；狀態列每次輪詢都會算這個），所以「合出來的你已經有了」
    這種要真的按下去才知道的情形不在這裡擋。武學＋武學不算：主畫面的提示講的是拿意境去合成。"""
    cfg, held = content.config, state.player.insights
    if not held or library.full(state, content):
        return False
    xinde, stamina = state.player.stats.get("xinde", 0), state.player.stamina
    can_merge = xinde >= cfg.merge_xinde and stamina >= cfg.merge_stamina
    can_fuse = bool(library.owned_arts(state)) and xinde >= cfg.fuse_xinde and stamina >= cfg.fuse_stamina
    return can_merge or can_fuse


def lineage_has(art_id: str, insight: Insight, content: Content, world: WorldStateStore) -> bool:
    """這門武學的血統裡（它自己、它的底、底的底……武學＋武學的兩門來源也算）有沒有融過這個意境（企劃者 2026-10-06 回報：
    意境合成不會用掉，「武學＋風 → 乙、乙＋風 → 丙……」可以無限往上疊，每一代都把風的屬性推到功效第一位）。
    全服的意境照 id 認；私有意境（悟意境設計 0.2b）的 id 不進全服登記，照它的屬性認——跟配方鍵 fuse_key 認私有意境的方法一樣，
    融過任何一個同屬性私有意境的血統，也不能再融同屬性的私有意境。"""
    own = insights.is_own(insight.id)
    seen: set[str] = set()
    todo = [art_id]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        art = team.resolve_art(current, content, world)
        if art is None:
            continue
        if (art.insight is None and art.insight_attr == insight.attribute) if own else art.insight == insight.id:
            return True
        todo += [a for a in [art.base, *art.parents] if a]
    return False


def fuse_problem(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> str | None:
    """不能合成的原因；None＝可以。血統裡融過這個意境的不准（lineage_has）；合出來的那一門你已經有了也不准
    （合成的意義是拿到你還沒有的武學）。
    「你已經有了」排在花費與持有上限之前：同一爐連按兩下、開兩個分頁時，第二下在 C 段重驗看見的真正變化是
    「已經有了」，不是第一下花掉之後才不夠的心得、或剛好被第一下填滿的持有（企劃者 2026-10-05：不能重複扣）。"""
    if art_id not in library.owned_arts(state):
        return "你沒有這門武學。"
    if insight_id not in state.player.insights:
        return "你還沒悟到這個意境。"
    if team.player_art(state, content, world, art_id) is None or insights.resolve(insight_id, content, world, state) is None:
        return "找不到它的資料。"  # 存檔裡記著、內容與全服登記裡都沒有（失效的引用）
    insight = insights.resolve(insight_id, content, world, state)
    if lineage_has(art_id, insight, content, world):
        return f"【{team.player_art(state, content, world, art_id).name}】的來歷裡早已融過「{insight.name}」——同一股意，再融也只是舊路重走。"
    known = world.lookup_recipe(fuse_key_for(state, content, world, art_id, insight_id))
    if known is not None and known.id in library.owned_arts(state):
        return f"這一爐合出來還是【{known.name}】，你已經有了——換一組試試吧。"
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.fuse_xinde, "合成")
    return problem if problem is not None else _stamina_line(state, content.config.fuse_stamina, "合成")


def _fuse_messages(base: MartialArt, insight: Insight, *, note: str = "") -> list[dict[str, str]]:
    """note 是 traits.naming_note 那一行（新武學的功效，取名要配得上它）；沒有功效的內容傳空的，提示跟以前一樣。"""
    base_note, insight_note = _dash_note(base), _dash_note(insight)
    return [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"底：一門{base.kind}【{base.name}】（屬{base.attribute}）{base_note}\n"
            f"融入的意境：「{insight.name}」（屬{insight.attribute}）{insight_note}\n"
            f"兩者結合，從底衍生出一門新的{base.kind}；名字要看得出是從底變出來的。\n{note}\n{naming.FORMAT_RULES}"
        )},
    ]


def forge_request(
    state: GameState, content: Content, world: WorldStateStore, art_id: str | None, insight_ids: list[str],
    other_art: str | None = None,
) -> naming.NamingRequest | None:
    """A 段（行動鎖內、很快；Game.forge_request 的本體）：這一爐要不要模型取名？要就開一張單子給 B 段（naming.generate）。
    不要的時候回 None：放的不是一門武學＋一個意境、兩門武學、也不是兩個意境；這一爐會被拒絕（拒絕的話留給 C 段照常回）；
    配方這一季已經有人登記（查表就好）；合到舊的、而且只有一個候選（就是它，不必問模型）。
    要模型的有兩種：沒人合過、長新的 → 取名的單；合到舊的、候選兩個以上 → 挑一個的單（choices）。只讀，不改任何東西。
    other_art 有、insight_ids 空的是武學＋武學（art_id 是第一門）。"""
    if art_id and other_art and not insight_ids:
        if blend_problem(state, content, world, art_id, other_art) is not None:
            return None
        key = blend_key(art_id, other_art)
        if world.lookup_recipe(key) is not None:
            return None
        art_a = team.player_art(state, content, world, art_id)
        art_b = team.player_art(state, content, world, other_art)
        tianji, seed = recipe_seed(world, key)
        shape = blend_shape(art_a, art_b, seed)
        candidates = landing.art_candidates(world, shape.kind, shape.attribute, shape.lean)
        if landing.lands(content, key, tianji, len(candidates)):
            return _pick_request("blend", key, shape.kind, _pick_messages(_blend_what(art_a, art_b), candidates), candidates)
        _, trait_note = _special_and_note(content, traits.inherit_blend(art_a, art_b, shape.attribute), key, tianji)
        return naming.NamingRequest("blend", key, shape.kind, _blend_messages(art_a, art_b, shape.kind, note=trait_note))
    if art_id and not other_art and len(insight_ids) == 1:
        insight_id = insight_ids[0]
        if fuse_problem(state, content, world, art_id, insight_id) is not None:
            return None
        key = fuse_key_for(state, content, world, art_id, insight_id)
        if world.lookup_recipe(key) is not None:
            return None
        if preset_for(content, art_id, insight_id) is not None:
            return None  # 師門配方：名字寫好了，不用模型（fuse 也不擲合到舊的）
        base = team.player_art(state, content, world, art_id)
        insight = insights.resolve(insight_id, content, world, state)
        tianji, _ = recipe_seed(world, key)
        candidates = landing.art_candidates(world, base.kind, insight.attribute, insight.lean)
        if landing.lands(content, key, tianji, len(candidates)):
            return _pick_request("fuse", key, base.kind, _pick_messages(_fuse_what(base, insight), candidates), candidates)
        _, trait_note = _special_and_note(content, traits.inherit_fuse(base, insight.attribute), key, tianji)
        return naming.NamingRequest("fuse", key, base.kind, _fuse_messages(base, insight, note=trait_note))
    if not art_id and not other_art and len(insight_ids) == 2:
        a, b = insight_ids
        if merge_problem(state, content, world, a, b) is not None:
            return None
        key = merge_key(a, b)
        ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
        if insights.is_own(a) or insights.is_own(b):  # 有私有意境的合併：沒有配方、每次都叫模型（悟意境設計 0.2b 第 4 點）
            return naming.NamingRequest("merge", key, "意境", _merge_messages(ia, ib))
        if world.lookup_insight_recipe(key) is not None:
            return None
        tianji, seed = recipe_seed(world, key)
        candidates = landing.insight_candidates(
            world, insights.merged_attribute(ia, ib, seed), insights.merged_lean(ia, ib),
        )
        if landing.lands(content, key, tianji, len(candidates)):
            return _pick_request("merge", key, "意境", _pick_messages(_merge_what(ia, ib), candidates), candidates)
        return naming.NamingRequest("merge", key, "意境", _merge_messages(ia, ib))
    return None


def _named(
    client: OllamaClient | None, content: Content, world: WorldStateStore, messages: list[dict[str, str]],
    proposed: tuple[str | None, str] | None,
) -> tuple[str | None, str]:
    """首次合出來的配方要的名字與說明。proposed 是鎖外先取好的（server：A 鎖內備料、B 鎖外取名，這裡是 C）：
    再過一次完整的過濾（naming.recheck），鎖裡不叫模型——(None, "") 也一樣，直接走退路字表。
    沒給 proposed（整季機器人、腳本、測試直接呼叫 Game.forge）才照舊在這裡叫模型。
    兩條路都擋角色的名號（FB-069，world.is_character_name）。"""
    if proposed is not None:
        return naming.recheck(content, proposed, person=world.is_character_name)
    return naming.propose(client, content, messages, person=world.is_character_name)


def _candidates(content: Content, world: WorldStateStore, key: str, kind: str, tianji: int, name: str | None):
    """登記時依序試的名字：先試模型取的（有的話），再試退路字表——種子是配方鍵＋這一季的天機、鹽從 0 起，
    所以一個配方換到的退路名字只看它自己，不看誰先到（兩個配方同時拿到同一個模型名字時，後到的那一個每次都換成同一個）。
    退路字表組出來的名字剛好是某個角色的名號就跳過（FB-069）。"""
    if name is not None:
        yield name
    for salt in range(naming.CLAIM_ATTEMPTS):
        fallback = naming.fallback_name(content, key, kind, salt=salt, tianji=tianji)
        if not world.is_character_name(fallback):
            yield fallback


def preset_for(content: Content, art_id: str, insight_id: str) -> PresetRecipe | None:
    """師門配方（content/preset_recipes.json，新手引導計畫一）：這個底融這個意境的名字與說明由內容寫好，不叫模型、也不走退路字表，
    也不擲「合到舊的」——師門傳下來的是同一門，新人不該拿到陌生人合出來的武學。"""
    return next((r for r in content.preset_recipes if r.base == art_id and r.insight == insight_id), None)


def _fuse_what(base: MartialArt, insight: Insight) -> str:
    return f"一門{base.kind}【{base.name}】（屬{base.attribute}）融入意境「{insight.name}」（屬{insight.attribute}）。"


def fuse(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None,
    art_id: str, insight_id: str, proposed: tuple[str | None, str] | None = None, rng: random.Random | None = None,
) -> tuple[MartialArt | None, list[str]]:
    """武學＋意境 → 新武學（或合到一門已知的），回傳（那一門, 訊息）；不能合成時回 (None, [原因])，什麼都不收、不登記新的武學。
    合到你已經有的那一門也是 (None, [原因])、也不收錢，但配方照樣記下來（link_recipe；下一次按之前 fuse_problem 就知道）。
    proposed：鎖外先取好的（名字, 說明）或先挑好的（名字, ""），見 _named、_picked。進來先整個重驗（A 段之後狀態可能變了：
    意境熔掉、心得或體力花掉、配方被別人或自己的另一個請求登記了、候選多了），再登記、收費。"""
    problem = fuse_problem(state, content, world, art_id, insight_id)
    if problem is not None:
        return None, [problem]
    base = team.player_art(state, content, world, art_id)
    insight = insights.resolve(insight_id, content, world, state)
    own = insights.is_own(insight_id)
    key = fuse_key(art_id, insight_id, insight.attribute)
    preset = preset_for(content, art_id, insight_id)  # 師門配方：這一季誰先合、後合都是它，所以先算好（_fuse_line 也要看）
    art, first, landed = world.lookup_recipe(key), False, False
    if art is None:
        tianji, _ = recipe_seed(world, key)
        candidates = landing.art_candidates(world, base.kind, insight.attribute, insight.lean)
        if preset is None and landing.lands(content, key, tianji, len(candidates)):
            name = _picked(client, proposed, _pick_messages(_fuse_what(base, insight), candidates), candidates)
            art, landed = world.link_recipe(key, landing.choose(candidates, key, tianji, name).id, state.player.name)
        else:
            # 功效（13.3、13.4）：長新武學才定——一般功效照來路、特別功效照配方擲；取名之前就算好，提示才寫得出來。
            # 師門配方也有一般功效，但沒有特別功效（從隱蔽的草廬裡傳不出「江湖上傳開了」）
            new_traits = traits.inherit_fuse(base, insight.attribute)
            if preset is not None:
                special_id, name, note = None, preset.name, preset.note
                if world.is_character_name(preset.name):  # 有人的名號就是這個名字（FB-069）：這一季改走退路字表，不寫那句說明
                    name, note = None, ""
            else:
                special_id, trait_note = _special_and_note(content, new_traits, key, tianji)
                name, note = _named(client, content, world, _fuse_messages(base, insight, note=trait_note), proposed)
            for candidate_name in _candidates(content, world, key, base.kind, tianji, name):
                candidate = generate_from_name(
                    candidate_name, base.kind, candidate_name, tianji, weights=LOW_ONLY, attribute=insight.attribute,
                )
                candidate = candidate.model_copy(update={
                    # 師門配方沒有首創者（誰先合出來都一樣）：不記名號、標 preset，卡片寫師門、江湖史不列
                    "origin": "fused", "creator": None if preset else state.player.name,
                    "creator_shown": None if preset else state.player.name, "preset": preset is not None,
                    "note": note if candidate_name == name else "",  # 說明是模型替它那個名字寫的；換成退路名字就不帶
                    # 私有意境不進全服登記（別人查不到它）：只記屬性，修練時拿手上同屬性的意境來修（悟意境設計 0.2b）
                    "insight": None if own else insight.id, "insight_attr": insight.attribute,
                    "base": art_id, "lean": insight.lean,
                    "traits": new_traits, "special": special_id,
                })
                art, first = world.claim_recipe(key, candidate)  # 同時有人先登記了：拿到的是人家登記的那一門
                if art is not None:
                    break  # 名字被占用（claim 回 None）就換下一個名字再試
        if art is None:
            return None, ["爐火熄了，這一次什麼也沒合成（名字都被用掉了，再試一次）。"]
    if art.id in library.owned_arts(state):  # 合到的、先被別人登記的，剛好是你已經有的：不收錢、不重複收
        if landed:  # 這一爐才把這一組登記到那一門：新摸清一條練法（FB-078）；不是這一爐登記的（別人先到）照舊說「已經有了」
            return None, [_new_road(f"【{art.name}】", "練法", f"【{base.name}】＋「{insight.name}」")]
        return None, [f"這一爐合出來還是【{art.name}】，你已經有了——換一組試試吧。"]
    cfg = content.config
    # 新武學自己那一份的品質照這一爐的搭配擲（fuse_odds；序章 rng 是 None，固定下品），從擲到的那一品接著修
    quality = roll_quality(fuse_odds(state, content, art_id, base, insight), rng)
    msgs = [_fuse_line(base, insight, art, first, landed, preset=preset is not None, quality=quality)] + _charge(
        state, cfg.fuse_xinde, cfg.fuse_stamina,
    )
    msgs += _special_rumor(state, content, art, first)
    echo(state, content, art, first)
    return art, msgs + _store_forged(state, content, world, art, quality)


def _store_forged(
    state: GameState, content: Content, world: WorldStateStore, art: MartialArt, quality: str | None = None,
) -> list[str]:
    """合成出來的新武學放哪（fuse、blend 共用）：同 library.store_art（quality 是擲到的自己那一份品質）；進了功法庫（沒有直接上身）的，再接兩句——
    跟身上同一種那門的比較（W6，team.compare_with_worn；沒東西可比就沒有這一句），與一句指路（W5）：結果說「收進功法庫」，
    修練頁的清單也叫「功法庫」，最後這句把兩邊接起來，所以排在最後。學藝、事件教的武學不走這裡。"""
    stored = library.store_art(state, art, quality)
    if not stored or art.id not in state.player.arts:
        return stored
    note = team.compare_with_worn(state, content, world, art)
    return stored + ([note] if note else []) + [library.SWITCH_HINT]


def _new_road(result: str, road: str, ingredients: str) -> str:
    """這一爐把一組新的配方登記到你已經有的那一個（合到舊的、剛好是自己的）：同一個結果可以有好幾條路，不收心得、體力，
    但你多摸清了一條——之後誰合這一組都直接查表拿到它（FB-078，企劃者裁決）。result 連括號一起給（武學【】、意境「」）。待 joy 潤。"""
    return f"這一爐的路數，竟又歸到{result}——你多摸清了一條{road}（{ingredients}）。不收心得、體力。"


def _fuse_line(
    base: MartialArt, insight: Insight, art: MartialArt, first: bool, landed: bool = False, preset: bool = False,
    quality: str | None = None,
) -> str:
    verb = "合出來的竟是一門已有的" if landed else "衍生出一門"
    head = (
        f"你以【{base.name}】融入「{insight.name}」，{verb}{art.kind}【{art.name}】"
        f"（{quality or art.quality}・屬{art.attribute}）！"
    )
    if preset:  # 師門配方：每個新人合的都是師門傳下來的同一門，不寫成「由先到的那個新人首創」
        return head + (f"\n{art.note}" if art.note else "") + "\n這是師門傳下來的路數。"
    return head + _arrival(art, first, landed)


def merge_problem(state: GameState, content: Content, world: WorldStateStore, a: str, b: str) -> str | None:
    """不能合併的原因；None＝可以。合出來的意境你已經悟得了也不准；跟 fuse_problem 一樣排在花費與持有上限之前。"""
    held = state.player.insights
    if a not in held or b not in held:
        return "兩個意境都要是你悟得的。"
    ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
    if ia is None or ib is None:
        return "找不到它的資料。"
    if insights.is_own(a) or insights.is_own(b):
        made = _own_merged(state, a, b)
        if made is not None:
            return f"這兩個你已經合過了，化成的「{made.name}」還在你心裡。"
    else:
        known = world.lookup_insight_recipe(merge_key(a, b))
        if known is not None and known.id in held:
            return f"這兩個合起來還是「{known.name}」，你已經悟得了。"
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.merge_xinde, "合併")
    if problem is not None:
        return problem
    return _stamina_line(state, content.config.merge_stamina, "合併")  # 三種合成都花體力（設計 12.1）


def _own_merged(state: GameState, a: str, b: str) -> Insight | None:
    """這兩個合出來、還在手上的私有意境（同一對不給一直合：每次都要叫模型，合出來的又是一個新的）。"""
    parents = sorted([a, b])
    p = state.player
    return next((i for i in p.own_insights.values() if i.parents == parents and i.id in p.insights), None)


def _merge_messages(a: Insight, b: Insight) -> list[dict[str, str]]:
    a_note, b_note = _dash_note(a), _dash_note(b)
    return [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"意境一：「{a.name}」（屬{a.attribute}）{a_note}\n"
            f"意境二：「{b.name}」（屬{b.attribute}）{b_note}\n"
            f"兩個意境融成一個新的意境。名字要像一種境界或天地之象，不是招式名。\n\n{naming.FORMAT_RULES}"
        )},
    ]


def _merge_what(a: Insight, b: Insight) -> str:
    return f"意境「{a.name}」（屬{a.attribute}）與「{b.name}」（屬{b.attribute}）融成一個意境。"


def merge(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, a: str, b: str,
    proposed: tuple[str | None, str] | None = None,
) -> tuple[Insight | None, list[str]]:
    """意境＋意境 → 新意境（或合到一個已知的），回傳（那一個, 訊息）；不能合併時回 (None, [原因])，什麼都不收、不登記新的意境。
    合到你已經悟得的那一個也是 (None, [原因])、也不收錢，但配方照樣記下來（link_insight_recipe；下一次按之前 merge_problem 就知道）。
    屬性與正邪在取名之前就照配方定好（設計 12.6），才找得到合到舊的候選。proposed 與重驗同 fuse。"""
    problem = merge_problem(state, content, world, a, b)
    if problem is not None:
        return None, [problem]
    ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
    key = merge_key(a, b)
    tianji = recipe_seed(world, key)[0]
    attribute, lean = merge_shape(world, ia, ib)
    if insights.is_own(a) or insights.is_own(b):
        return _merge_own(state, content, world, client, ia, ib, attribute, lean, key, proposed)
    result, first, landed = world.lookup_insight_recipe(key), False, False
    if result is None:
        candidates = landing.insight_candidates(world, attribute, lean)
        if landing.lands(content, key, tianji, len(candidates)):
            name = _picked(client, proposed, _pick_messages(_merge_what(ia, ib), candidates), candidates)
            picked = landing.choose(candidates, key, tianji, name)
            result, landed = world.link_insight_recipe(key, picked.id, state.player.name)
        else:
            name, note = _named(client, content, world, _merge_messages(ia, ib), proposed)
            for candidate_name in _candidates(content, world, key, "意境", tianji, name):
                candidate = Insight(
                    id=candidate_name, name=candidate_name, attribute=attribute, lean=lean,
                    creator=state.player.name, creator_shown=state.player.name,
                    note=note if candidate_name == name else "", parents=sorted([a, b]),
                )
                result, first = world.claim_insight_recipe(key, candidate)
                if result is not None:
                    break
        if result is None:
            return None, ["兩股意念始終融不到一塊（名字都被用掉了，再試一次）。"]
    if result.id in state.player.insights:  # 合到的、先被別人登記的，剛好是你已經悟得的：不收錢、不重複
        if landed:  # 同 fuse：這一爐才登記的新配方（FB-078）
            return None, [_new_road(f"「{result.name}」", "悟法", f"「{ia.name}」＋「{ib.name}」")]
        return None, [f"這兩個合起來還是「{result.name}」，你已經悟得了。"]
    state.player.insights.append(result.id)
    verb = "化成的竟是已有的" if landed else "化成"
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，{verb}「{result.name}」（屬{result.attribute}）！"
    if result.note:
        head += f"\n{result.note}"
    head += "\n這是江湖上第一次有人悟出這個意境。" if first else f"\n這個意境由{shown_creator(result) or '不知名的前人'}首悟。"
    cfg = content.config
    echo(state, content, result, first)
    # 真的合成了才扣：被拒絕、名字都被用掉的都不收體力，跟心得同一個點
    return result, [head] + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


def _merge_own(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, ia: Insight, ib: Insight,
    attribute: str, lean: str, key: str, proposed: tuple[str | None, str] | None,
) -> tuple[Insight | None, list[str]]:
    """有私有意境的合併（悟意境設計 0.2b）：合出來的也是私有的——不登記、不擲合到舊的、每次都叫模型取名
    （proposed 是鎖外取好的；沒給才在這裡叫），名字只跟自己手上的比（sensing.own_name）。"""
    if proposed is None:
        proposed = _named(client, content, world, _merge_messages(ia, ib), None)
    p = state.player
    name, note, _ = sensing.own_name(state, content, world, f"{key}|{p.name}|{p.own_serial + 1}", proposed)
    result = sensing.add_own(state, Insight(
        id="", name=name, attribute=attribute, lean=lean, creator=p.name, creator_shown=p.name, note=note,
        parents=sorted([ia.id, ib.id]), place=ia.place or ib.place,
    ))
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，化成「{result.name}」（屬{result.attribute}）！"
    if result.note:
        head += f"\n{result.note}"
    head += "\n這份領悟是你自己的，江湖上沒有第二份。"
    cfg = content.config
    return result, [head] + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


def blend_problem(state: GameState, content: Content, world: WorldStateStore, a: str, b: str) -> str | None:
    """不能把兩門武學合在一起的原因；None＝可以。跟 fuse_problem 同一個順序：「你已經有了」排在花費與持有上限之前。"""
    owned = library.owned_arts(state)
    if a == b:
        return "要放兩門不同的武學。"
    if a not in owned or b not in owned:
        return "兩門都要是你會的武學。"
    if team.player_art(state, content, world, a) is None or team.player_art(state, content, world, b) is None:
        return "找不到它的資料。"
    known = world.lookup_recipe(blend_key(a, b))
    if known is not None and known.id in owned:
        return f"這兩門合出來還是【{known.name}】，你已經有了——換一門吧。"
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.fuse_xinde, "合成")
    return problem if problem is not None else _stamina_line(state, content.config.fuse_stamina, "合成")


def _blend_messages(a: MartialArt, b: MartialArt, kind: str, *, note: str = "") -> list[dict[str, str]]:
    """note 同 _fuse_messages：新武學的功效那一行。"""
    a_note, b_note = _dash_note(a), _dash_note(b)
    return [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"第一門：{a.kind}【{a.name}】（屬{a.attribute}）{a_note}\n"
            f"第二門：{b.kind}【{b.name}】（屬{b.attribute}）{b_note}\n"
            f"兩門合而為一，衍生出一門新的{kind}；名字要看得出是兩門合起來的。\n{note}\n{naming.FORMAT_RULES}"
        )},
    ]


def _blend_what(a: MartialArt, b: MartialArt) -> str:
    return f"{a.kind}【{a.name}】（屬{a.attribute}）與{b.kind}【{b.name}】（屬{b.attribute}）合而為一。"


def blend(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None,
    a: str, b: str, proposed: tuple[str | None, str] | None = None, rng: random.Random | None = None,
) -> tuple[MartialArt | None, list[str]]:
    """武學＋武學 → 新武學（或合到一門已知的），兩門都留著（設計 12.3）；不能合時回 (None, [原因])，什麼都不收、不登記新的武學。
    合到你已經有的那一門（放進爐裡的那兩門也算）也是 (None, [原因])、也不收錢，但配方照樣記下來。
    跟 fuse 同一套：價錢、合到舊的、取名三段與重驗都一樣；底（base）是 None，兩門來源記在 parents。"""
    problem = blend_problem(state, content, world, a, b)
    if problem is not None:
        return None, [problem]
    art_a, art_b = team.player_art(state, content, world, a), team.player_art(state, content, world, b)
    key = blend_key(a, b)
    tianji, seed = recipe_seed(world, key)
    shape = blend_shape(art_a, art_b, seed)
    art, first, landed = world.lookup_recipe(key), False, False
    if art is None:
        candidates = landing.art_candidates(world, shape.kind, shape.attribute, shape.lean)
        if landing.lands(content, key, tianji, len(candidates)):
            name = _picked(client, proposed, _pick_messages(_blend_what(art_a, art_b), candidates), candidates)
            art, landed = world.link_recipe(key, landing.choose(candidates, key, tianji, name).id, state.player.name)
        else:
            new_traits = traits.inherit_blend(art_a, art_b, shape.attribute)  # 功效同 fuse：來路與配方定，取名之前算好
            special_id, trait_note = _special_and_note(content, new_traits, key, tianji)
            name, note = _named(client, content, world, _blend_messages(art_a, art_b, shape.kind, note=trait_note), proposed)
            for candidate_name in _candidates(content, world, key, shape.kind, tianji, name):
                candidate = generate_from_name(
                    candidate_name, shape.kind, candidate_name, tianji, weights=LOW_ONLY, attribute=shape.attribute,
                )
                candidate = candidate.model_copy(update={
                    "origin": "fused", "creator": state.player.name, "creator_shown": state.player.name,
                    "note": note if candidate_name == name else "",
                    "insight": shape.insight, "insight_attr": shape.insight_attr, "base": None, "parents": sorted([a, b]), "lean": shape.lean,
                    "traits": new_traits, "special": special_id,
                })
                art, first = world.claim_recipe(key, candidate)
                if art is not None:
                    break
        if art is None:
            return None, ["爐火熄了，這一次什麼也沒合成（名字都被用掉了，再試一次）。"]
    lead, follow = (art_a, art_b) if a <= b else (art_b, art_a)  # 照 id 排，跟 parents、功法卡的「由【甲】與【乙】衍生」同一個先後（FB-073）
    if art.id in library.owned_arts(state):  # 合到的、先被別人登記的，剛好是你已經有的：不收錢、不重複收
        if landed:  # 同 fuse：這一爐才登記的新配方（FB-078）
            return None, [_new_road(f"【{art.name}】", "練法", f"【{lead.name}】＋【{follow.name}】")]
        return None, [f"這兩門合出來還是【{art.name}】，你已經有了——換一門吧。"]
    cfg = content.config
    quality = roll_quality(blend_odds(state, content, a, art_a, b, art_b), rng)  # 同 fuse：照這一爐的搭配擲
    verb = "合出來的竟是一門已有的" if landed else "衍生出一門"
    head = (
        f"你把【{lead.name}】與【{follow.name}】合而為一，{verb}{art.kind}【{art.name}】"
        f"（{quality}・屬{art.attribute}）！"
    )
    msgs = [head + _arrival(art, first, landed)] + _charge(state, cfg.fuse_xinde, cfg.fuse_stamina)
    msgs += _special_rumor(state, content, art, first)
    echo(state, content, art, first)
    return art, msgs + _store_forged(state, content, world, art, quality)
