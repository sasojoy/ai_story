"""合成與合併（武學與成長設計 3.2、3.4）。

| 誰 | 做什麼 |
|---|---|
| 模型 | 只取名字＋一句說明，一個數字都不碰 |
| 引擎 | 配方、屬性、正邪、品質、成本、全服登記 |

合成：武學＋意境 → 新武學，底留著；種類跟著底；屬性與正邪跟著意境；品質一律從下品起修、從第一成開始
（全服登記的那一筆是下品，玩家拿到的那一份也是，不繼承底的品質——企劃者 2026-10-05 改了設計 3.4：
絕學的底合出絕學的複本、馬上熔掉就賺 40 心得，是個無本的金錢迴圈；底的好壞只留在底身上，
新武學靠修練一階一階往上爬，熔的時候才領得到那幾階的加給，見 library.melt_refund）。
合併：意境＋意境（可以是同一個）→ 新意境，兩個都留著；屬性與正邪照 insights 的規則。合併要花體力（Config.merge_stamina）、
合成不花——合併→熔掉→再合併每一圈淨賺心得，企劃者 2026-10-05 的裁示是不擋、讓每一圈都付一次體力。
配方全服共享：第一個合出來的人等模型取名（叫不動就走退路字表），之後查表、不用等。
「已經有了」一律照功法的 id 認（改名之後顯示的名字跟 id 不一樣）。
"""
from __future__ import annotations

from . import insights, library, naming, team
from .martial_arts import Insight, MartialArt, generate_from_name
from .models import Content
from .ollama_client import OllamaClient
from .state import GameState
from .world_state import WorldStateStore

FUSE_PREFIX = "融|"
MERGE_PREFIX = "合|"
LOW_ONLY = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}


def fuse_key(art_id: str, insight_id: str) -> str:
    return f"{FUSE_PREFIX}{art_id}+{insight_id}"


def merge_key(a: str, b: str) -> str:
    return MERGE_PREFIX + insights.merge_key(a, b)


def _full_line(state: GameState, content: Content) -> str:
    cap = library.holding_cap(content, state.player.member.level)
    return f"武學與意境已經滿了（{library.held_count(state)}/{cap}），先熔掉一些。"


def _xinde_line(state: GameState, price: int, what: str) -> str | None:
    xinde = state.player.stats.get("xinde", 0)
    return None if xinde >= price else f"心得不足：{what}要 {price} 點，你只有 {xinde} 點。"


def can_forge(state: GameState, content: Content) -> bool:
    """現在有沒有可能開爐：持有沒滿、有意境，而且付得起一次合成（還要有武學）或一次合併（還要有體力）。
    只看結構、不查全服配方表（那要打資料庫；狀態列每次輪詢都會算這個），所以「合出來的你已經有了」這種
    要真的按下去才知道的情形不在這裡擋。"""
    cfg, held = content.config, state.player.insights
    if not held or library.full(state, content):
        return False
    xinde = state.player.stats.get("xinde", 0)
    can_merge = xinde >= cfg.merge_xinde and state.player.stamina >= cfg.merge_stamina  # 合併花體力，合成不花
    return can_merge or (bool(library.owned_arts(state)) and xinde >= cfg.fuse_xinde)


def fuse_problem(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> str | None:
    """不能合成的原因；None＝可以。合出來的那一門你已經有了也不准（合成的意義是拿到你還沒有的武學）。"""
    if art_id not in library.owned_arts(state):
        return "你沒有這門武學。"
    if insight_id not in state.player.insights:
        return "你還沒悟到這個意境。"
    if team.player_art(state, content, world, art_id) is None or insights.resolve(insight_id, content, world) is None:
        return "找不到它的資料。"  # 存檔裡記著、內容與全服登記裡都沒有（失效的引用）
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.fuse_xinde, "合成")
    if problem is not None:
        return problem
    known = world.lookup_recipe(fuse_key(art_id, insight_id))
    if known is not None and known.id in library.owned_arts(state):
        return f"這一爐合出來還是【{known.name}】，你已經有了——換一個意境吧。"
    return None


def _fuse_messages(base: MartialArt, insight: Insight) -> list[dict[str, str]]:
    base_note = f"——{base.note}" if base.note else ""
    insight_note = f"——{insight.note}" if insight.note else ""
    return [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"底：一門{base.kind}【{base.name}】（屬{base.attribute}）{base_note}\n"
            f"融入的意境：「{insight.name}」（屬{insight.attribute}）{insight_note}\n"
            f"兩者結合，從底衍生出一門新的{base.kind}；名字要看得出是從底變出來的。\n\n{naming.FORMAT_RULES}"
        )},
    ]


def fuse(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None,
    art_id: str, insight_id: str,
) -> tuple[MartialArt | None, list[str]]:
    """武學＋意境 → 新武學，回傳（新武學, 訊息）；不能合成時回 (None, [原因])。"""
    problem = fuse_problem(state, content, world, art_id, insight_id)
    if problem is not None:
        return None, [problem]
    base = team.player_art(state, content, world, art_id)
    insight = insights.resolve(insight_id, content, world)
    key = fuse_key(art_id, insight_id)
    art = world.lookup_recipe(key)
    first = False
    if art is None:
        name, note = naming.propose(client, content, _fuse_messages(base, insight))
        tianji = world.read().tianji
        for attempt in range(naming.CLAIM_ATTEMPTS):
            if name is None:
                name = naming.fallback_name(content, key, base.kind, salt=attempt)
            candidate = generate_from_name(name, base.kind, name, tianji, weights=LOW_ONLY, attribute=insight.attribute)
            candidate = candidate.model_copy(update={
                "origin": "fused", "creator": state.player.name, "note": note,
                "insight": insight.id, "base": art_id, "lean": insight.lean,
            })
            art, first = world.claim_recipe(key, candidate)  # 同時有人先登記了：拿到的是人家登記的那一門
            if art is not None:
                break
            name, note = None, ""  # 名字被占用：換一個決定性的名字再試
        if art is None:
            return None, ["爐火熄了，這一次什麼也沒合成（名字都被用掉了，再試一次）。"]
    if art.id in library.owned_arts(state):  # 先被別人登記的那一門，剛好是你已經有的：不收錢、不重複收
        return None, [f"這一爐合出來還是【{art.name}】，你已經有了——換一個意境吧。"]
    price = content.config.fuse_xinde
    state.player.stats["xinde"] = state.player.stats.get("xinde", 0) - price
    # 新武學一律從登記的品質（下品）起修，不看底現在是什麼品質：store_art 不帶 quality，就不會記一筆個人品質
    msgs = [_fuse_line(base, insight, art, first), f"心得 -{price}"]
    return art, msgs + library.store_art(state, art)


def _fuse_line(base: MartialArt, insight: Insight, art: MartialArt, first: bool) -> str:
    head = (
        f"你以【{base.name}】融入「{insight.name}」，衍生出一門{art.kind}【{art.name}】"
        f"（{art.quality}・屬{art.attribute}）！"
    )
    if art.note:
        head += f"\n{art.note}"
    if first:
        return head + "\n這是江湖上第一次有人合出這一門——從此它就叫這個名字。"
    return head + f"\n這一門由{art.creator or '不知名的前人'}首創，你照著合出了同一門。"


def merge_problem(state: GameState, content: Content, world: WorldStateStore, a: str, b: str) -> str | None:
    """不能合併的原因；None＝可以。合出來的意境你已經悟得了也不准。"""
    held = state.player.insights
    if a not in held or b not in held:
        return "兩個意境都要是你悟得的。"
    if insights.resolve(a, content, world) is None or insights.resolve(b, content, world) is None:
        return "找不到它的資料。"
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.merge_xinde, "合併")
    if problem is not None:
        return problem
    if state.player.stamina < content.config.merge_stamina:  # 合併要花體力，合成不用（企劃者 2026-10-05）
        return f"體力不足：合併一次要 {content.config.merge_stamina}。"
    known = world.lookup_insight_recipe(merge_key(a, b))
    if known is not None and known.id in held:
        return f"這兩個合起來還是「{known.name}」，你已經悟得了。"
    return None


def _merge_messages(a: Insight, b: Insight) -> list[dict[str, str]]:
    a_note = f"——{a.note}" if a.note else ""
    b_note = f"——{b.note}" if b.note else ""
    return [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"意境一：「{a.name}」（屬{a.attribute}）{a_note}\n"
            f"意境二：「{b.name}」（屬{b.attribute}）{b_note}\n"
            f"兩個意境融成一個新的意境。名字要像一種境界或天地之象，不是招式名。\n\n{naming.FORMAT_RULES}"
        )},
    ]


def merge(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, a: str, b: str,
) -> tuple[Insight | None, list[str]]:
    """意境＋意境 → 新意境，回傳（新意境, 訊息）；不能合併時回 (None, [原因])。"""
    problem = merge_problem(state, content, world, a, b)
    if problem is not None:
        return None, [problem]
    ia, ib = insights.resolve(a, content, world), insights.resolve(b, content, world)
    key = merge_key(a, b)
    result = world.lookup_insight_recipe(key)
    first = False
    if result is None:
        name, note = naming.propose(client, content, _merge_messages(ia, ib))
        for attempt in range(naming.CLAIM_ATTEMPTS):
            if name is None:
                name = naming.fallback_name(content, key, "意境", salt=attempt)
            candidate = Insight(
                id=name, name=name, attribute=insights.merged_attribute(ia, ib, name),
                lean=insights.merged_lean(ia, ib), creator=state.player.name, note=note, parents=sorted([a, b]),
            )
            result, first = world.claim_insight_recipe(key, candidate)
            if result is not None:
                break
            name, note = None, ""
        if result is None:
            return None, ["兩股意念始終融不到一塊（名字都被用掉了，再試一次）。"]
    if result.id in state.player.insights:  # 先被別人登記的那一個，剛好是你已經悟得的：不收錢、不重複
        return None, [f"這兩個合起來還是「{result.name}」，你已經悟得了。"]
    price, tired = content.config.merge_xinde, content.config.merge_stamina
    state.player.stats["xinde"] = state.player.stats.get("xinde", 0) - price
    state.player.stamina -= tired  # 真的合成了才扣：被拒絕、名字都被用掉的都不收體力，跟心得同一個點
    state.player.insights.append(result.id)
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，化成「{result.name}」（屬{result.attribute}）！"
    if result.note:
        head += f"\n{result.note}"
    head += "\n這是江湖上第一次有人悟出這個意境。" if first else f"\n這個意境由{result.creator or '不知名的前人'}首悟。"
    return result, [head, f"心得 -{price}", f"體力 -{tired}"]
