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
伺服器上的取名在行動鎖外（最終審查 Critical 1）：forge_request（A，鎖內）→ naming.generate（B，鎖外）→
fuse／merge(proposed=...)（C，鎖內，整個重驗再登記、收費）。沒給 proposed 才在這裡叫模型（整季機器人、腳本、測試）。
「已經有了」一律照功法的 id 認（改名之後顯示的名字跟 id 不一樣）。
"""
from __future__ import annotations

from . import insights, library, naming, team
from .martial_arts import Insight, MartialArt, generate_from_name, shown_creator
from .models import Content
from .ollama_client import OllamaClient
from .rules import display_name
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
    cap = library.cap_of(state, content)
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
    """不能合成的原因；None＝可以。合出來的那一門你已經有了也不准（合成的意義是拿到你還沒有的武學）。
    「你已經有了」排在花費與持有上限之前：同一爐連按兩下、開兩個分頁時，第二下在 C 段重驗看見的真正變化是
    「已經有了」，不是第一下花掉之後才不夠的心得、或剛好被第一下填滿的持有（企劃者 2026-10-05：不能重複扣）。"""
    if art_id not in library.owned_arts(state):
        return "你沒有這門武學。"
    if insight_id not in state.player.insights:
        return "你還沒悟到這個意境。"
    if team.player_art(state, content, world, art_id) is None or insights.resolve(insight_id, content, world) is None:
        return "找不到它的資料。"  # 存檔裡記著、內容與全服登記裡都沒有（失效的引用）
    known = world.lookup_recipe(fuse_key(art_id, insight_id))
    if known is not None and known.id in library.owned_arts(state):
        return f"這一爐合出來還是【{known.name}】，你已經有了——換一個意境吧。"
    if library.full(state, content):
        return _full_line(state, content)
    return _xinde_line(state, content.config.fuse_xinde, "合成")


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


def forge_request(
    state: GameState, content: Content, world: WorldStateStore, art_id: str | None, insight_ids: list[str],
) -> naming.NamingRequest | None:
    """A 段（行動鎖內、很快；Game.forge_request 的本體）：這一爐要不要模型取名？要就開一張單子給 B 段（naming.generate）。
    不要的時候回 None：放的不是一門武學＋一個意境、也不是兩個意境；這一爐會被拒絕（拒絕的話留給 C 段照常回）；
    配方這一季已經有人登記（查表就好）。只讀，不改任何東西。"""
    if art_id and len(insight_ids) == 1:
        insight_id = insight_ids[0]
        if fuse_problem(state, content, world, art_id, insight_id) is not None:
            return None
        key = fuse_key(art_id, insight_id)
        if world.lookup_recipe(key) is not None:
            return None
        base = team.player_art(state, content, world, art_id)
        return naming.NamingRequest("fuse", key, base.kind, _fuse_messages(base, insights.resolve(insight_id, content, world)))
    if not art_id and len(insight_ids) == 2:
        a, b = insight_ids
        if merge_problem(state, content, world, a, b) is not None:
            return None
        key = merge_key(a, b)
        if world.lookup_insight_recipe(key) is not None:
            return None
        return naming.NamingRequest(
            "merge", key, "意境", _merge_messages(insights.resolve(a, content, world), insights.resolve(b, content, world)),
        )
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


def fuse(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None,
    art_id: str, insight_id: str, proposed: tuple[str | None, str] | None = None,
) -> tuple[MartialArt | None, list[str]]:
    """武學＋意境 → 新武學，回傳（新武學, 訊息）；不能合成時回 (None, [原因])，什麼都不收、不登記。
    proposed：鎖外先取好的（名字, 說明），見 _named。進來先整個重驗（A 段之後狀態可能變了：意境熔掉、心得花掉、
    配方被別人或自己的另一個請求登記了），再登記、收費。"""
    problem = fuse_problem(state, content, world, art_id, insight_id)
    if problem is not None:
        return None, [problem]
    base = team.player_art(state, content, world, art_id)
    insight = insights.resolve(insight_id, content, world)
    key = fuse_key(art_id, insight_id)
    art = world.lookup_recipe(key)
    first = False
    if art is None:
        name, note = _named(client, content, world, _fuse_messages(base, insight), proposed)
        tianji = world.read().tianji
        for candidate_name in _candidates(content, world, key, base.kind, tianji, name):
            candidate = generate_from_name(
                candidate_name, base.kind, candidate_name, tianji, weights=LOW_ONLY, attribute=insight.attribute,
            )
            candidate = candidate.model_copy(update={
                "origin": "fused", "creator": state.player.name, "creator_shown": display_name(state),
                "note": note if candidate_name == name else "",  # 說明是模型替它那個名字寫的；換成退路名字就不帶
                "insight": insight.id, "base": art_id, "lean": insight.lean,
            })
            art, first = world.claim_recipe(key, candidate)  # 同時有人先登記了：拿到的是人家登記的那一門
            if art is not None:
                break  # 名字被占用（claim 回 None）就換下一個名字再試
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
    return head + f"\n這一門由{shown_creator(art) or '不知名的前人'}首創，你照著合出了同一門。"


def merge_problem(state: GameState, content: Content, world: WorldStateStore, a: str, b: str) -> str | None:
    """不能合併的原因；None＝可以。合出來的意境你已經悟得了也不准；跟 fuse_problem 一樣排在花費與持有上限之前。"""
    held = state.player.insights
    if a not in held or b not in held:
        return "兩個意境都要是你悟得的。"
    if insights.resolve(a, content, world) is None or insights.resolve(b, content, world) is None:
        return "找不到它的資料。"
    known = world.lookup_insight_recipe(merge_key(a, b))
    if known is not None and known.id in held:
        return f"這兩個合起來還是「{known.name}」，你已經悟得了。"
    if library.full(state, content):
        return _full_line(state, content)
    problem = _xinde_line(state, content.config.merge_xinde, "合併")
    if problem is not None:
        return problem
    if state.player.stamina < content.config.merge_stamina:  # 合併要花體力，合成不用（企劃者 2026-10-05）
        return f"體力不足：合併一次要 {content.config.merge_stamina}。"
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
    proposed: tuple[str | None, str] | None = None,
) -> tuple[Insight | None, list[str]]:
    """意境＋意境 → 新意境，回傳（新意境, 訊息）；不能合併時回 (None, [原因])，什麼都不收、不登記。
    proposed 與重驗同 fuse。"""
    problem = merge_problem(state, content, world, a, b)
    if problem is not None:
        return None, [problem]
    ia, ib = insights.resolve(a, content, world), insights.resolve(b, content, world)
    key = merge_key(a, b)
    result = world.lookup_insight_recipe(key)
    first = False
    if result is None:
        name, note = _named(client, content, world, _merge_messages(ia, ib), proposed)
        tianji = world.read().tianji
        for candidate_name in _candidates(content, world, key, "意境", tianji, name):
            candidate = Insight(
                id=candidate_name, name=candidate_name, attribute=insights.merged_attribute(ia, ib, candidate_name),
                lean=insights.merged_lean(ia, ib), creator=state.player.name, creator_shown=display_name(state),
                note=note if candidate_name == name else "", parents=sorted([a, b]),
            )
            result, first = world.claim_insight_recipe(key, candidate)
            if result is not None:
                break
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
    head += "\n這是江湖上第一次有人悟出這個意境。" if first else f"\n這個意境由{shown_creator(result) or '不知名的前人'}首悟。"
    return result, [head, f"心得 -{price}", f"體力 -{tired}"]
