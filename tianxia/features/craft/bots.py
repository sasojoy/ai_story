"""假人的煉製與自創（第二輪第 101 批：FORGE_TRIES、MERGE_SHARE、FORGE_RESERVE、ForgePlan、pick_forge、CREATE_RESERVE、CREATE_INTENTS、create_art、_name_draft 從 bot 搬來，_forge 從 bot_policy 搬來；舊名 re-export 同一批物件）。
沒有掛鉤：bot.forge_and_cultivate、bot_policy.tend_arts 經舊名叫，先後留在殼（它們同時排煉製、修練、鐵匠鋪三包的事，包不准 import 包）。要換 MERGE_SHARE、FORGE_RESERVE 換這裡（pick_forge 讀這個檔的模組全域）；bot.FORGE_RESERVE 是同一個數的舊名，殼的 tend_arts 讀那一份。
取名的單子（ForgeJob、NamingSlot、NO_NAME）四包開單，在共用層 bot_base，一律寫 `bot_base.X`。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, NamedTuple

from tianxia import arts as arts_mod
from tianxia import bot_base, insight_fx, insights, naming, team, weapons
from tianxia import fusion  # 共用規則層（合成與揣摩，第 87 批登記）

from . import create

if TYPE_CHECKING:
    from tianxia.engine import Game

FORGE_TRIES = 4  # 意境＋意境試幾組（被擋下就換一組）
MERGE_SHARE = 0.3  # 手上有兩個以上意境時，這麼多的機會開一爐（煉製只剩意境＋意境）
FORGE_RESERVE = 20  # 三種合成都花體力（武學與成長設計 12.1）：體力留這麼多給探索與遊歷，多出來的才拿去合成
CREATE_RESERVE = 50  # 自創付完心得要剩這麼多（練成、揣摩還要用）
CREATE_INTENTS = ("風過林梢，影不留痕", "山不動而勢壓人", "一息吐納，百脈皆通", "水無常形，隨勢而走", "烈火燎原，一往無前")


class ForgePlan(NamedTuple):
    """挑好的一爐（還沒開）：兩個意境（煉製只剩意境＋意境，Joy 2026-10-21）；意境合成改版開著時另帶傾注與立意。"""

    insight_ids: tuple[str, ...]
    pour: bool = False
    intent: str | None = None

    def __repr__(self) -> str:  # 改版沒開時（兩格都是預設）照舊只寫 insight_ids：比對工具與紀錄看到的字一個不變
        extra = "".join(f", {k}={getattr(self, k)!r}" for k in ("pour", "intent") if getattr(self, k) != self._field_defaults[k])
        return f"ForgePlan(insight_ids={self.insight_ids!r}{extra})"


# 意境合成改版：第一次合一對時的立意，一型一句（照 fusion.FORM_WORDS 的關鍵字讀得出那一型）
V2_INTENTS = {"攻": "一往無前，焚盡一切", "守": "守住不退", "變": "詭變如影", "心": "心定如山"}


def pick_forge(game: Game, rng: random.Random, merge_share: float | None = None) -> ForgePlan | None:
    """挑一爐（整季機器人與伺服器假人共用）：體力低於 FORGE_RESERVE、手上不到兩個意境、或什麼都合不了就是 None。
    只挑、不開爐，什麼都不改。merge_share 沒給就在呼叫的當下讀模組常數 MERGE_SHARE（量平衡的腳本改它要有效）。"""
    merge_share = MERGE_SHARE if merge_share is None else merge_share
    state, content, world = game.state, game.content, game.world
    p = state.player
    if len(p.insights) < 2 or p.stamina < FORGE_RESERVE or rng.random() >= merge_share:
        return None
    if fusion.v2_on(content, state):
        return _pick_v2(game, rng)
    for _ in range(FORGE_TRIES):
        a = rng.choice(p.insights)  # 意境效果池：同一份放兩次合不了，第二格從其餘的挑（同一種的另一份就是揣摩）
        b = rng.choice([i for i in p.insights if i != a])
        if fusion.merge_problem(state, content, world, a, b) is None:
            return ForgePlan((a, b))
    return None


def _pick_v2(game: Game, rng: random.Random) -> ForgePlan | None:
    """意境合成改版的挑法（真人看得到的同一張預覽：fusion.v2_preview）：
    1. 手上兩份三重湊得成一對、四條都齊（在那一路最濃的地方、這一季的秘訣也對上）：傾注、合璧成神；
    2. 兩份三重湊得成一對但還差地方或秘訣：這一對留著不合（等走到地方、等時辰），其餘照舊隨機挑；
    3. 第一次合的一對寫一句立意（型隨機）。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    deep = [i for i in p.insights if insight_fx.strength(state, i) >= insight_fx.MAX_LAYERS and not insight_fx.is_god(state, i)]
    held: set[str] = set()
    for i, a in enumerate(deep):
        for b in deep[i + 1:]:
            if fusion.merge_problem(state, content, world, a, b, pour=True) is not None:
                continue
            look = fusion.v2_preview(state, content, world, a, b, pour=True)
            if not look or not look["can_pour"]:
                continue
            if look["god"]:
                return ForgePlan((a, b), pour=True, intent=_intent(rng) if look["ask_intent"] else None)
            held.update((a, b))
    loose = [i for i in p.insights if i not in held]
    if len(loose) < 2:
        return None
    for _ in range(FORGE_TRIES):
        a = rng.choice(loose)
        b = rng.choice([i for i in loose if i != a])
        if fusion.merge_problem(state, content, world, a, b) is None:
            look = fusion.v2_preview(state, content, world, a, b)
            return ForgePlan((a, b), intent=_intent(rng) if look and look["ask_intent"] else None)
    return None


def _intent(rng: random.Random) -> str:
    return V2_INTENTS[rng.choice(fusion.FORMS)]


def infuse_spare(game: Game) -> list[str]:
    """意境合成改版：同一路的凡、佳（不帶真意、沒裝著）化進那一路最深的一份，攢著加深；不擲亂數，改版沒開什麼都不做。
    珍品留著（三重的珍品是合璧成神要的料）。一次只化一路。"""
    state, content, world = game.state, game.content, game.world
    if not fusion.v2_on(content, state):
        return []
    p = state.player
    by_path: dict[str, list[str]] = {}
    for i in p.insights:
        ins = insights.resolve(i, content, world, state)
        if ins is not None:
            by_path.setdefault(ins.attribute, []).append(i)
    for ids in by_path.values():
        bodies = sorted((i for i in ids if not insight_fx.is_god(state, i)), key=lambda i: -insight_fx.strength(state, i))
        for body in bodies:
            spare = [
                i for i in ids if i != body and insight_fx.look(insight_fx.record(state, content, world, i, None)) in ("凡", "佳")
                and insight_fx.strength(state, i) <= insight_fx.strength(state, body) and arts_mod.where_slotted(state, i) is None
            ]
            if spare and fusion.infuse_problem(state, content, world, body, spare) is None:
                return game.infuse(body, spare)
    return []


def create_art(game: Game, rng: random.Random) -> bool:
    """自創一門（tianxia/create.py 五步一次走完）：心得付完還剩 CREATE_RESERVE 才做。種類挑身上那一門比較弱的那一種；
    兵器照身上武學的種類（推不出來隨機），行功之法隨機；架式從預設的幾個挑一個再稍微動一下；意從 CREATE_INTENTS 挑、
    照關鍵字表讀（假人不叫模型）；名字走退路字表（看得出來是假人：之後要補模型取名）。伺服器假人與整季機器人共用。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    if p.creating is not None and p.creating.paid and p.creating.step == "name":
        return _name_draft(game)  # 立意時付過心得的單子（上一次取名取不到）：接著取名，不丟掉
    if create.allowed(state, content) is not None or p.stats.get("xinde", 0) - create.price(state, content) < CREATE_RESERVE:
        return False
    if p.creating is not None:
        game.create_cancel()
    worn = [(team.player_art(state, content, world, a), k) for a, k in ((p.member.wugong_id, "武學"), (p.member.neigong_id, "內功"))]
    kind = min(worn, key=lambda x: x[0].top_power if x[0] is not None else 0)[1]
    forms = [f.key for f in create.forms_of(content, kind)]
    if not forms:
        return False
    form = weapons.art_weapon(p.member.wugong_id, content, world) if kind == "武學" else None
    game.create_begin(kind, form if form in forms else rng.choice(forms))
    if p.creating is None:
        return False
    names = [x.name for x in content.create_forms.presets] or [create.DEFAULT_PRESET]
    pose = create.preset(content, rng.choice(names))
    pose = {k: v + rng.uniform(-15, 15) for k, v in pose.items()}
    game.create_pose(pose)
    game.create_intent(rng.choice(CREATE_INTENTS))
    if p.creating is None or p.creating.step != "name":
        game.create_cancel()
        return False
    return _name_draft(game)


def _name_draft(game: Game) -> bool:
    """替成了形的單子取名（退路字表）。都撞名就留著單子（心得立意時付過了），下一次接著取：第一次用原本那一批，
    之後照這一刻的時辰換一批（不然每次都撞同幾個名字）。"""
    p = game.state.player
    draft = p.creating
    seed = f"自創|{p.name}|{p.created_count}" + (f"|{int((game.now or 0) // 3600)}" if draft.name_tries else "")
    draft.name_tries += 1
    for salt in range(naming.CLAIM_ATTEMPTS):
        name = naming.fallback_name(game.content, seed, draft.kind, salt=salt)
        game.create_name(name)
        if p.creating is None:
            return True
    return False


def _forge(game: Game, plan: ForgePlan, slot: bot_base.NamingSlot | None) -> list[str]:
    """開一爐。要模型取名（或挑）的：輪得到就開單交給假人程式（B、C 段在 bot_runner），輪不到這一爐不開——
    用字表的名字搶下首創，名字的樣子看得出是假人（企劃者 2026-10-05）。不必叫模型的（配方有了、只有一個候選）照開，
    給 NO_NAME，鎖內一定不叫模型。"""
    insight_ids = list(plan.insight_ids)
    request = game.forge_request(None, insight_ids, named_outside=True)
    extra = {"pour": True} if plan.pour else {}
    if plan.intent:
        extra["intent"] = plan.intent
    if request is None:
        return game.forge(None, insight_ids, proposed=bot_base.NO_NAME, **extra)
    if slot is not None and slot.open and slot.job is None:
        slot.job = (bot_base.PourJob(plan.insight_ids, request, pour=plan.pour, intent=plan.intent) if plan.pour or plan.intent
                    else bot_base.ForgeJob(plan.insight_ids, request))
    elif slot is not None:
        slot.skipped += 1
    return []
