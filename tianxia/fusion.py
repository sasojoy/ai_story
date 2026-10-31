"""武學合成與意境合成（武學重構，Joy 2026-10-20「我想改整個架構，不要縫縫補補」；定案 /mnt/project-files/plan/武學重構定案.md）。

| 誰 | 做什麼 |
|---|---|
| 模型 | 只取名字＋一句說明，一個數字都不碰 |
| 引擎 | 配方、品級、意境的屬性與正邪、成本、全服登記 |

煉製只剩意境合成（Joy 2026-10-21「武學跟武學或是武學跟意境乾脆不要合成了，意境跟意境能合成就好」）：
武學＋武學（blend）拿掉了，新武學只從自創來（create.py）；以前合出來的照舊讀得到（配方鍵 blend_key「兼|」留著認舊的）。
意境合成（merge）：同一個意境合自己 → 強度升一級（●→●●→●●●，arts.MAX_STRENGTH；不登記、不取名）；
兩個不同的意境 → 一個複合的新意境（就是那個屬性的高階技能，traits.json 的 high），屬性與正邪照 insights 的規則、
種子是天機＋配方鍵；秘方合中的帶一條特別功效（Insight.secret_special）。兩個都留著。
價錢：Config.merge_xinde 心得＋merge_stamina 體力，真的合成了才收。
武學＋意境的合成拿掉了：意境直接裝進武學的槽（arts.py）。
伺服器上的取名在行動鎖外：forge_request（A，鎖內）→ naming.generate（B，鎖外）→ merge(proposed=...)（C，鎖內，
整個重驗再登記、收費）。沒給 proposed 才在這裡叫模型（整季機器人、腳本、測試）。
「已經有了」一律照功法的 id 認（改名之後顯示的名字跟 id 不一樣）。
打造（smithing）借用這裡的品質機率零件：QualityOdds、odds_from_points、roll_quality、quality_odds_text、天時地利三個判斷。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import annals, arts as arts_mod, calendar, insight_fx, insights, library, naming, rules, secret_recipes, sensing
from .martial_arts import Insight, MartialArt, shown_creator
from .models import Content
from .ollama_client import OllamaClient
from .rules import add_chronicle, add_rumor, season_one
from .state import Echo, GameState, GearFind, WeaponRecipe
from .world_state import WorldStateStore

FUSE_PREFIX = "融|"  # 舊配方鍵（武學＋意境）：這一版之前登記的照舊讀得到，不再登記新的
MERGE_PREFIX = "合|"
BLEND_PREFIX = "兼|"  # 舊配方鍵（武學＋武學，2026-10-21 拿掉）：以前登記的照舊讀得到
KINDS = ("內功", "武學")


# 合不了的原因帶兩三個字的 short（煉製頁清單上標用）；類別搬到 arts，裝槽的拒絕也帶得上
Refusal = arts_mod.Refusal
_refuse = arts_mod.refuse


@dataclass(frozen=True)
class Partner:
    """論武（玩家互動第二層，企劃者 2026-10-08）：兩個人各出一樣合成。這一爐有一樣是對方出的（lent，武學或意境的 id）：
    不必是你的、也不佔你的持有；價錢各付一半（price：心得, 體力）；第一次合出來的首創算兩人共有（creator 照舊是開爐的人，
    co_creator 記對方，寫給別人看的是「甲、乙」）。私有意境不能拿來論武（別人沒有它）。"""

    lent: str
    name: str  # 對方的名號
    price: tuple[int, int]
    # 這一爐的配方是對方剛剛在同一次論武裡首創的（發邀請的那一方接著照配方合出同一門）：那一句寫「江湖上第一次…你與某某一起首創的」；
    # 之後同一對人再論、或熔掉自己再合，不是第一次（FB-243）
    fresh: bool = False


def half_price(xinde: int, stamina: int) -> tuple[int, int]:
    """論武一人付一半，各自無條件進位（5 → 3）：兩個人合起來不比一個人開爐便宜到哪裡去。"""
    return (xinde + 1) // 2, (stamina + 1) // 2


def _lent(partner: Partner | None, thing_id: str) -> bool:
    return partner is not None and partner.lent == thing_id


def _price(content: Content, partner: Partner | None, kind: str) -> tuple[int, int]:
    cfg = content.config
    full = (cfg.merge_xinde, cfg.merge_stamina) if kind == "merge" else (cfg.fuse_xinde, cfg.fuse_stamina)
    return partner.price if partner is not None else full


def _makers(state: GameState, partner: Partner | None) -> dict:
    """新登記的那一筆記誰：開爐的人；論武時加上對方（co_creator），寫給別人看的是兩個名號。"""
    me = state.player.name
    if partner is None:
        return {"creator": me, "creator_shown": me}
    return {"creator": me, "creator_shown": f"{me}、{partner.name}", "co_creator": partner.name}


# ── 品質機率的零件（打造用；武學合成不擲品質了）────────────────────


@dataclass(frozen=True)
class QualityOdds:
    """一爐打造的品質機率（%，下品＋中品＋上品＝100）與說明那一句的原因（最多兩個）。fixed 是不擲骰時定的那一品（打造不用）。"""

    odds: dict[str, float]
    reasons: tuple[str, ...] = ()
    fixed: str | None = None
    short_of: float | None = None


def odds_from_points(scored: list[tuple[str, float]], rule, base: dict[str, float]) -> QualityOdds:
    """把各因素的分數加成造化分，從 base（普通搭配的平均）往上或往下推，上品、下品各自夾住，中品是剩下的。
    rule 要有 up_per_point、low_per_point、up_range、low_range、shown_from、lines（SmithQuality 有）。"""
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


def roll_quality(odds: QualityOdds | None, rng: random.Random | None) -> str:
    """擲品質。rng 或 odds 是 None 時不擲、照劇本是下品。"""
    if odds is not None and odds.fixed:
        return odds.fixed
    if rng is None or odds is None or not any(odds.odds.values()):
        return "下品"
    return rng.choices(list(odds.odds), weights=list(odds.odds.values()))[0]


def quality_odds_text(odds: QualityOdds, near: float = 0) -> str:
    """打造的開爐鈕寫這一爐的機率：「下品 19%、中品 46%、上品 35%（兩股氣息相投）」。"""
    if odds.fixed:
        return odds.fixed + (f"（{'；'.join(odds.reasons)}）" if odds.reasons else "")
    text = "、".join(f"{q} {round(w)}%" for q, w in odds.odds.items() if w > 0)
    return text + (f"（{'、'.join(odds.reasons)}）" if odds.reasons else "")


def terrain_here(state: GameState, content: Content, attribute: str) -> bool:
    """天時地利的「地利」（打造）：此地探索悟得到這個屬性的意境。"""
    here = content.locations.get(state.player.location)
    return here is not None and any(
        content.insights[i].attribute == attribute for i in insights.explore_gives(here, content)
    )


def battlefield_here(state: GameState, content: Content) -> bool:
    """天時地利的「戰場」（打造）：人在營寨類地點，或（第一季）所在大區的戰線正在亂局。"""
    here = content.locations.get(state.player.location)
    return here is not None and (
        content.config.explore_mix_of(here.tags).kind == "camp"
        or (season_one(content, state.world) and rules.front_of(content, here.id) in rules.chaos_fronts(state, content))
    )


def calm_now(state: GameState, hours: float) -> bool:
    """天時地利的「心靜」（打造）：出關之後 hours 遊戲小時之內。"""
    p, w = state.player, state.world
    return p.seclusion_done is not None and 0 <= w.time - p.seclusion_done <= hours * calendar.HOUR


# ── 配方鍵 ───────────────────────────────────────────────


def fuse_key(art_id: str, insight_id: str, attribute: str | None = None) -> str:
    """舊的武學＋意境配方鍵（只讀舊登記用）。"""
    if insights.is_own(insight_id):
        return f"{FUSE_PREFIX}{art_id}+屬:{attribute}"
    return f"{FUSE_PREFIX}{art_id}+{insight_id}"


def merge_key(a: str, b: str) -> str:
    return MERGE_PREFIX + insights.merge_key(a, b)


def blend_key(a: str, b: str) -> str:
    """武學＋武學的配方鍵：兩門 id 排序後接起來（A＋B 與 B＋A 是同一個配方，設計 12.3）。"""
    return BLEND_PREFIX + "+".join(sorted((a, b)))


def recipe_seed(world: WorldStateStore, key: str) -> tuple[int, str]:
    """這一季的天機與這個配方的種子：同一個配方同一季，屬性都一樣（設計 12.6）。"""
    tianji = world.tianji()
    return tianji, f"{tianji}|{key}"


def merge_shape(world: WorldStateStore, a: Insight, b: Insight, content: Content | None = None, state: GameState | None = None) -> tuple[str, str]:
    """意境＋意境合出來的（屬性, 正邪）：配方種子（天機＋配方鍵）加上兩個來源決定，跟參數順序無關（設計 12.6）。
    merge 照它登記，煉製頁的預覽照它寫——兩邊同一個函式，預覽不會跟結果各說各話（FB-082）。"""
    seed = recipe_seed(world, merge_key(a.id, b.id))[1]
    return insights.merged_attribute(a, b, seed), insights.merged_lean(a, b)


# ── 共用的小零件 ──────────────────────────────────────────


def _full_line(state: GameState, content: Content) -> str:
    cap = library.cap_of(state, content)
    return _refuse(f"武學與意境已經滿了（{library.held_count(state)}/{cap}），先熔掉一些。", "持有滿了")


def _xinde_line(state: GameState, price: int, what: str) -> str | None:
    xinde = state.player.stats.get("xinde", 0)
    return None if xinde >= price else _refuse(f"心得不足：{what}要 {price} 點，你只有 {xinde} 點。", "心得不足")


def _stamina_line(state: GameState, need: int, what: str) -> str | None:
    return None if state.player.stamina >= need else _refuse(f"體力不足：{what}一次要 {need}。", "體力不足")


def _charge(state: GameState, xinde: int, stamina: int) -> list[str]:
    """真的合成了才收（設計 12.1）：心得與體力一起扣，回寫成數值變化的兩行。被拒絕的不收。"""
    p = state.player
    p.stats["xinde"] = p.stats.get("xinde", 0) - xinde
    p.stamina -= stamina
    return [f"心得 -{xinde}", f"體力 -{stamina}"]


def _dash_note(thing: MartialArt | Insight) -> str:
    """送給模型的提示裡，一門武學或一個意境名字後面的「——說明」；沒有說明就是空的。"""
    return f"——{thing.note}" if thing.note else ""


FIRST_ART = "\n這是江湖上第一次有人合出這一門——從此它就叫這個名字。"
FIRST_INSIGHT = "\n這是江湖上第一次有人悟出這個意境。"
OWN_FIRST_INSIGHT = "\n這個意境是你首悟的。"
CO_FIRST_INSIGHT = "\n這是江湖上第一次有人悟出這個意境——你與{other}一起首悟的。"
CO_OWN_INSIGHT = "\n這個意境是你與{other}首悟的。"


def made_first(msgs: list[str]) -> bool:
    """這一爐的回話寫了「江湖上第一次有人合出（悟出）」：這一爐首創了（論武的另一方照它判斷是不是剛剛一起首創的，FB-243）。"""
    marks = (FIRST_ART.strip(), FIRST_INSIGHT.strip())
    return any(mark in msg for msg in msgs for mark in marks)


def _founders_line(other: str, together: bool, first: str, own: str, solo: str) -> str:
    if not other:
        return solo
    return (first if together else own).format(other=other)


def _together(partner: Partner | None, other: str | None) -> bool:
    return bool(other) and partner is not None and partner.fresh and partner.name == other


def _partner_of(thing: MartialArt | Insight, me: str) -> str | None:
    """這一門（這個意境）的首創者裡有你：回另一位共同首創者（論武，co_creator）；只有你自己是空字串；首創者裡沒有你是 None。"""
    if not me or me not in (thing.creator, thing.co_creator):
        return None
    return (thing.co_creator if me == thing.creator else thing.creator) or ""


ECHO_RUMOR = "江湖上照著{who}首創的{thing}練出來的人越來越多了。"
ECHO_RUMOR_FORGED = "江湖上照著{who}首創的{thing}打出來的人越來越多了。"  # 待 joy 潤：兵器配方


def echo(
    state: GameState, content: Content, thing: MartialArt | Insight | WeaponRecipe | GearFind, first: bool, made: str = "練",
) -> None:
    """首創名望回饋（Config.first_echo）：你合出（或打出，made="打"）別人首創的那一門，在這一季的 WorldState.echoes 記你一筆；
    首創者自己的 Game 同步時補名望（Game._deliver_echoes）。一個人一門只算一次、最多算 cap 個人，湊滿那一下江湖上傳一句。
    自己首創的、師門配方、內容寫好的不記；第一季沒開著時什麼都不做。"""
    me = state.player.name
    if first or not thing.creator or me in (thing.creator, thing.co_creator) or getattr(thing, "preset", False):
        return
    if not season_one(content, state.world):
        return
    rule = content.config.first_echo
    shown = f"「{thing.name}」" if isinstance(thing, Insight) else f"【{thing.name}】"
    entry = state.world.echoes.setdefault(thing.id, Echo(creator=thing.creator, co_creator=thing.co_creator, name=shown, made=made))
    if me in entry.followers or len(entry.followers) >= rule.cap:
        return
    entry.followers.append(me)
    if len(entry.followers) == rule.cap:
        template = ECHO_RUMOR if made == "練" else ECHO_RUMOR_FORGED
        add_rumor(state, template.format(who=shown_creator(thing) or thing.creator, thing=shown), None, content=content, named=True)


def rename_echo(state: GameState, thing_id: str, name: str) -> None:
    """神器原品定名之後（smithing.name_divine）：echo 記下的那一筆名字改成新的。"""
    entry = state.world.echoes.get(thing_id)
    if entry is not None:
        entry.name = f"【{name}】"


def can_forge(state: GameState, content: Content) -> bool:
    """現在有沒有可能開爐（狀態列提示用）：持有沒滿，而且付得起一次意境合成（手上至少兩個意境）。只看結構、不查全服配方表。"""
    cfg = content.config
    if library.full(state, content):
        return False
    xinde, stamina = state.player.stats.get("xinde", 0), state.player.stamina
    return len(state.player.insights) >= 2 and xinde >= cfg.merge_xinde and stamina >= cfg.merge_stamina


def _named(
    client: OllamaClient | None, content: Content, world: WorldStateStore, messages: list[dict[str, str]],
    proposed: tuple[str | None, str] | None,
) -> tuple[str | None, str]:
    """首次合出來的配方要的名字與說明。proposed 是鎖外先取好的（C 段）：再過一次完整的過濾，鎖裡不叫模型；
    沒給才照舊在這裡叫模型。兩條路都擋角色的名號（FB-069）。"""
    if proposed is not None:
        return naming.recheck(content, proposed, person=world.is_character_name)
    return naming.propose(client, content, messages, person=world.is_character_name)


def _candidates(content: Content, world: WorldStateStore, key: str, kind: str, tianji: int, name: str | None):
    """登記時依序試的名字：先試模型取的（有的話），再試退路字表（種子是配方鍵＋這一季的天機）。"""
    if name is not None:
        yield name
    for salt in range(naming.CLAIM_ATTEMPTS):
        fallback = naming.fallback_name(content, key, kind, salt=salt, tianji=tianji)
        if not world.is_character_name(fallback):
            yield fallback


def _makers_shown(state: GameState, thing: MartialArt | Insight) -> str:
    return getattr(thing, "creator_shown", None) or state.player.name


def _secret_lines(
    state: GameState, content: Content, world: WorldStateStore, secret, thing: str, first: bool, made=None,
) -> list[str]:
    """合中秘方：結果多一句「暗合口訣」，記進武學譜；這一季第一個合中的，江湖上傳一句、寫進江湖史。"""
    if secret is None:
        return []
    cfg = content.config.secrets
    fresh = secret_recipes.solve(state, secret_recipes.tianji_of(world), secret)
    lines = [cfg.hit_line] if cfg.hit_line else []
    if fresh:
        lines += secret_recipes.solved_lines(state, content, world)
    if first:
        who = _makers_shown(state, made) if made is not None else state.player.name
        rumor = cfg.rumor.format(who=who, thing=thing)
        add_rumor(state, rumor, None, content=content, named=True)
        add_chronicle(state, cfg.chronicle.format(who=who, thing=thing))
        lines.append(rumor)
    return lines


# ── 意境合成（意境＋意境）──────────────────────────────────

DEEPEN_LINE = "你把「{name}」反覆揣摩，體會又深了一層（{mark}）。"  # 同＋同（待 joy 潤）
MIXED_LINE = "你把兩份「{name}」揉成了一份。"  # 揣摩：兩份的功效不同、層數沒有變深（待 joy 潤）
PIECE_LINE = "這一份是{look}品：{label}。"  # 待 joy 潤（品相凡佳珍神，底子不給玩家看）
GOD_DEED = "合出一份神品的「{name}」。"  # 待 joy 潤（神品只進自己的事蹟，不進江湖史）
GRAND_LINE = "揉到深處，悟出了真意〔{name}〕！"  # 待 joy 潤
DEEPEST = "「{name}」已經體會到極處（{mark}），再揣摩也深不下去了。"
SAME_PIECE = "揣摩要同一種意境的兩份：再悟一次「{name}」，就有第二份。"  # 待 joy 潤
PIECE_FULL = "「{name}」你手上已經有 {n} 份了，先揣摩或熔掉一份。"  # 待 joy 潤


def same_kind(state: GameState, ia: Insight, ib: Insight) -> bool:
    """揣摩的兩份是不是同一種：同一種意境的兩份（feng、feng~2）；自己悟的（私有）沒有第二份，同屬性、都不是合出來的就算同一種。"""
    if ia.id == ib.id:
        return False
    if insights.is_own(ia.id) and insights.is_own(ib.id):
        return ia.attribute == ib.attribute and not ia.parents and not ib.parents
    return insight_fx.base_id(ia.id) == insight_fx.base_id(ib.id)
GOD_KEPT = "頓悟悟來的神品意境是獨一份的境界，不能拿去揣摩、合成。"  # 待 joy 潤
OWN_IN_DISCUSS = "心裡那份自己悟的意境，說不出口，論武時拿不出來。"


def merge_problem(
    state: GameState, content: Content, world: WorldStateStore, a: str, b: str, partner: Partner | None = None,
) -> str | None:
    """不能合併的原因；None＝可以。同一個意境合自己是加深強度（到頂不准）；不同的合出來的你已經悟得了也不准。"""
    held = state.player.insights
    if (a not in held and not _lent(partner, a)) or (b not in held and not _lent(partner, b)):
        return "兩個意境都要是你悟得的。"
    if partner is not None and (insights.is_own(a) or insights.is_own(b)):
        return OWN_IN_DISCUSS
    ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
    if ia is None or ib is None:
        return "找不到它的資料。"
    if insight_fx.is_god(state, a) or insight_fx.is_god(state, b):  # 特殊頓悟的神品意境：不能揣摩、不能合成（tianxia/epiphany.py）
        return _refuse(GOD_KEPT, "神品")
    if a == b:
        if partner is not None:
            return _refuse("論武要兩個不同的意境。", "同一個")
        return _refuse(SAME_PIECE.format(name=ia.name), "要兩份")
    if same_kind(state, ia, ib):  # 揣摩（意境效果池）：同一種的兩份揉成一份
        if partner is not None:
            return _refuse("論武要兩個不同的意境。", "同一種")
        fa, fb = insight_fx.record(state, content, world, a, ia), insight_fx.record(state, content, world, b, ib)
        merged = insight_fx.deepen(content, fa, fb, None)
        if (merged.general, merged.grand) == (fa.general, fa.grand) and insight_fx.grand_chance(content, fa, fb) == 0:
            return _refuse(DEEPEST.format(name=ia.name, mark=arts_mod.strength_mark(arts_mod.MAX_STRENGTH)), "已到極處")
    else:
        secret = secret_recipes.match_merge(content, world, ia, ib)
        if secret is None and (insights.is_own(a) or insights.is_own(b)):
            made = _own_merged(state, a, b)
            if made is not None:
                return _refuse(f"這兩個你已經合過了，化成的「{made.name}」還在你心裡。", "已經有了")
        else:
            known = world.lookup_insight_recipe(secret_recipes.key(secret) if secret is not None else merge_key(a, b))
            if known is not None and not insight_fx.room_for(state, content, known.id):
                n = len(insight_fx.pieces(state, known.id))
                return _refuse(PIECE_FULL.format(name=known.name, n=n), "已經夠了")
        if library.full(state, content):
            return _full_line(state, content)
    xinde, stamina = _price(content, partner, "merge")
    problem = _xinde_line(state, xinde, "合併")
    if problem is not None:
        return problem
    return _stamina_line(state, stamina, "合併")


def _own_merged(state: GameState, a: str, b: str) -> Insight | None:
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


def merge(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, a: str, b: str,
    proposed: tuple[str | None, str] | None = None, partner: Partner | None = None,
) -> tuple[Insight | None, list[str]]:
    """意境＋意境：同一個合自己 → 強度升一級；兩個不同的 → 一個複合的新意境（高階技能）。回（那一個, 訊息）；
    不能合時回 (None, [原因])，什麼都不收。屬性與正邪在取名之前就照配方定好（設計 12.6）。"""
    problem = merge_problem(state, content, world, a, b, partner)
    if problem is not None:
        return None, [problem]
    ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
    if same_kind(state, ia, ib):
        return _deepen(state, content, world, ia, ib)
    key = merge_key(a, b)
    tianji = recipe_seed(world, key)[0]
    attribute, lean = merge_shape(world, ia, ib)
    secret = secret_recipes.match_merge(content, world, ia, ib)  # 秘方（照左右兩格；私有意境照屬性認）先於私有的合併
    if secret is None and (insights.is_own(a) or insights.is_own(b)):
        return _merge_own(state, content, world, client, ia, ib, attribute, lean, key, proposed)
    if secret is not None:
        key = secret_recipes.key(secret)
    result, first = world.lookup_insight_recipe(key), False
    if result is None:
        if secret is not None:
            name, note = (None if world.is_character_name(secret.name) else secret.name), secret.note
            special = secret_recipes.special_for(content, secret, tianji)
        else:
            name, note = _named(client, content, world, _merge_messages(ia, ib), proposed)
            special = None
        for candidate_name in _candidates(content, world, key, "意境", tianji, name):
            candidate = Insight(
                id=candidate_name, name=candidate_name, attribute=attribute, lean=lean, **_makers(state, partner),
                note=note if candidate_name == name else "", parents=sorted([insight_fx.base_id(a), insight_fx.base_id(b)]),
                secret=secret.id if secret is not None else None, secret_special=special,
            )
            result, first = world.claim_insight_recipe(key, candidate)
            if result is not None:
                break
        if result is None:
            return None, ["兩股意念始終融不到一塊（名字都被用掉了，再試一次）。"]
    if not insight_fx.room_for(state, content, result.id):
        return None, [PIECE_FULL.format(name=result.name, n=len(insight_fx.pieces(state, result.id)))]
    piece = insight_fx.new_piece_id(state, result.id)  # 合出來的也一份一份的（再合一次是第二份）
    quality = insight_fx.better(insight_fx.quality_of(state, a), insight_fx.quality_of(state, b))
    state.player.insights.append(piece)
    fx = insight_fx.roll(state, content, world, piece, quality=quality, compound=True)
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，化成「{result.name}」（屬{result.attribute}・{insight_fx.look(fx)}・{arts_mod.skill_name(content, result, fx)}）！"
    if result.note:
        head += f"\n{result.note}"
    other = None if first else _partner_of(result, state.player.name)
    if first:
        head += FIRST_INSIGHT
    elif other is not None:
        head += _founders_line(other, _together(partner, other), CO_FIRST_INSIGHT, CO_OWN_INSIGHT, OWN_FIRST_INSIGHT)
    else:
        head += f"\n這個意境由{shown_creator(result) or '不知名的前人'}首悟。"
    echo(state, content, result, first)
    _god(state, content, result.name, fx)
    if first:
        annals.note(state, content, annals.DEED, f"江湖上第一個悟出意境「{result.name}」。", 3)
    extra = _secret_lines(state, content, world, secret, f"「{result.name}」", first, result)
    mine = result if piece == result.id else result.model_copy(update={"id": piece})
    return mine, [head] + extra + _charge(state, *_price(content, partner, "merge"))


def _god(state: GameState, content: Content, name: str, fx, *before) -> None:
    """合出（或揣摩成）神品：寫一句進自己的事蹟（招式與絕學稿案第五輪）。本來就是神品的再揉一次不另寫。"""
    if insight_fx.look(fx) == "神" and all(insight_fx.look(b) != "神" for b in before):
        annals.note(state, content, annals.DEED, GOD_DEED.format(name=name), 2)


def _deepen(state: GameState, content: Content, world: WorldStateStore, ia: Insight, ib: Insight) -> tuple[Insight, list[str]]:
    """揣摩（意境效果池）：同一種意境的兩份揉成一份——同一個一般功效的層數相加（最多三重）、品質取好的、
    沒有大獎時照品質擲一次（insight_fx.deepen）。裝在槽上的那一份留下（都裝著留第一份），另一份用掉、從槽上拆下。"""
    p = state.player
    keep, gone = ia, ib
    if arts_mod.where_slotted(state, gone.id) is not None and arts_mod.where_slotted(state, keep.id) is None:
        keep, gone = gone, keep
    fa = insight_fx.record(state, content, world, keep.id, keep)
    fb = insight_fx.record(state, content, world, gone.id, gone)
    before = insight_fx.strength(state, keep.id)
    merged = insight_fx.deepen(content, fa, fb, insight_fx.deepen_rng(state, world, keep.id, gone.id))
    p.insight_fx[keep.id] = merged
    p.insight_strength.pop(keep.id, None)
    where = arts_mod.where_slotted(state, gone.id)
    if where is not None:
        p.art_slots[where] = [None if i == gone.id else i for i in p.art_slots[where]]
    p.insights.remove(gone.id)
    insight_fx.drop(state, gone.id)
    p.own_insights.pop(gone.id, None)
    after = insight_fx.strength(state, keep.id)
    head = DEEPEN_LINE.format(name=keep.name, mark=arts_mod.strength_mark(after)) if after > before else MIXED_LINE.format(name=keep.name)
    lines = [head, PIECE_LINE.format(look=insight_fx.look(merged), label=insight_fx.label(content, merged))]
    _god(state, content, keep.name, merged, fa, fb)
    if merged.grand and not fa.grand and not fb.grand:
        g = insight_fx.grand(content, merged.grand)
        lines.append(GRAND_LINE.format(name=g.name if g else merged.grand))
    cfg = content.config
    return keep, lines + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


def _merge_own(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, ia: Insight, ib: Insight,
    attribute: str, lean: str, key: str, proposed: tuple[str | None, str] | None,
) -> tuple[Insight | None, list[str]]:
    """有私有意境的合併（悟意境設計 0.2b）：合出來的也是私有的——不登記、每次都叫模型取名，名字只跟自己手上的比。"""
    if proposed is None:
        proposed = _named(client, content, world, _merge_messages(ia, ib), None)
    p = state.player
    name, note, _ = sensing.own_name(state, content, world, f"{key}|{p.name}|{p.own_serial + 1}", proposed)
    result = sensing.add_own(state, Insight(
        id="", name=name, attribute=attribute, lean=lean, creator=p.name, creator_shown=p.name, note=note,
        parents=sorted([ia.id, ib.id]), place=ia.place or ib.place,
    ))
    quality = insight_fx.better(insight_fx.quality_of(state, ia.id), insight_fx.quality_of(state, ib.id))
    fx = insight_fx.roll(state, content, world, result.id, quality=quality, compound=True)
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，化成「{result.name}」（屬{result.attribute}・{insight_fx.look(fx)}・{arts_mod.skill_name(content, result, fx)}）！"
    if result.note:
        head += f"\n{result.note}"
    head += "\n這份領悟是你自己的，江湖上沒有第二份。"
    _god(state, content, result.name, fx)
    cfg = content.config
    return result, [head] + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


# ── A 段 ─────────────────────────────────────────────────

# 爐裡只合意境（Joy 2026-10-21 拿掉武學＋武學、武學＋意境）：放了武學、放不到兩個意境、論武拿武學出來時的那一句（待 joy 潤）
ART_IN_FURNACE = "爐裡只合意境：武學不再拿來合，意境到「修練」去裝進武學的槽。"
TWO_INSIGHTS = "放兩個意境：不同的合出新的意境，同一種的兩份是揣摩。"
DISCUSS_ARTS_GONE = _refuse("論武只合意境，武學不再拿來合了。", "只合意境")


def forge_request(
    state: GameState, content: Content, world: WorldStateStore, art_id: str | None, insight_ids: list[str],
    partner: Partner | None = None,
) -> naming.NamingRequest | None:
    """A 段（行動鎖內、很快；Game.forge_request 的本體）：這一爐要不要模型取名？要就開一張單子給 B 段（naming.generate）。
    不要的時候回 None：放的不是兩個意境（煉製只剩意境合成）；這一爐會被拒絕；配方這一季已經有人登記；秘方（名字內容寫好了）；
    同一個意境合自己（加深強度、不取名）。只讀，不改任何東西。"""
    if not art_id and len(insight_ids) == 2:
        a, b = insight_ids
        if a == b or merge_problem(state, content, world, a, b, partner) is not None:
            return None
        if same_kind(state, insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)):
            return None  # 揣摩：不取名
        key = merge_key(a, b)
        ia, ib = insights.resolve(a, content, world, state), insights.resolve(b, content, world, state)
        if secret_recipes.match_merge(content, world, ia, ib) is not None:
            return None
        if insights.is_own(a) or insights.is_own(b):
            return naming.NamingRequest("merge", key, "意境", _merge_messages(ia, ib))
        if world.lookup_insight_recipe(key) is not None:
            return None
        return naming.NamingRequest("merge", key, "意境", _merge_messages(ia, ib))
    return None
