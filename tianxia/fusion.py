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

共用規則層（第二輪第 87 批收進 registry.SHARED）：不 import 功能包；私有意境的取名與收進存檔走同一層的 insights。
改這一份 scripts/test_for.py 只挑自己檔名＋煙霧＋邊界（收進來之前挑 76 個檔）。另外跑（-n 4）直接讀到它的：
tests/arts/ 的 test_in_lock_model_timeout、test_library、test_secret_recipes；tests/battle/test_one_art；tests/bots/ 的 test_bot、test_bot_policy、test_bot_runner；
tests/core/test_journal；tests/server/test_server；tianxia/features/ 的 craft/tests/test_forge_picks、cultivation/tests/test_arts_pages_two、test_cultivation、
guide/tests/test_prologue、map/tests/test_real_map、peers/tests/test_discuss、test_social、seal/tests/test_seal_duel、test_seal_mandate、
sense/tests/test_epiphany、test_sensing、smithy/tests/test_armor_forge、test_forge_divine、test_forge_secrets、test_shop、test_weapons_forge；
這幾包的 tianxia/features/<包>/tests/test_<包>_shell：battle、bounties、bout、companions、craft、cultivation、guide、map、military、peers、seclusion、sense、socialize、tale、travel。
經武學卡片 art_cards、煉製頁 forge_view 讀到它的，看 `git grep -lE "import (art_cards|forge_view)" -- tests tianxia/features` 列的那幾個。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .core import annal_base as annals
from . import arts as arts_mod, calendar, insight_fx, insights, library, naming, rules, secret_recipes
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
    首創者自己的 Game 同步時補名望（煉製包 actions.deliver_echoes）。一個人一門只算一次、最多算 cap 個人，湊滿那一下江湖上傳一句。
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
    pour: bool = False,
) -> str | None:
    """不能合併的原因；None＝可以。同一個意境合自己是加深強度（到頂不准）；不同的合出來的你已經悟得了也不准。
    pour 是合成改版的傾注（兩份都用掉）：論武不行、改版沒開不行；傾注不佔持有（兩份換一份），持有滿了照樣能合。"""
    held = state.player.insights
    if pour and partner is not None:
        return _refuse(POUR_WITH_PARTNER, "論武")
    if pour and not v2_on(content, state):
        return _refuse("這一季還不能傾注。", "還沒開")  # 待 joy 潤
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
        if library.full(state, content) and not pour:
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
    intent: str | None = None, pour: bool = False,
) -> tuple[Insight | None, list[str]]:
    """意境＋意境：同一個合自己 → 強度升一級；兩個不同的 → 一個複合的新意境（高階技能）。回（那一個, 訊息）；
    不能合時回 (None, [原因])，什麼都不收。屬性與正邪在取名之前就照配方定好（設計 12.6）。
    合成改版開著（v2_on）：a 是左格主料；intent 是第一次合這個配方時寫的立意（挑型）；pour 是傾注。見「意境合成改版」那一段。"""
    problem = merge_problem(state, content, world, a, b, partner, pour)
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
        return _merge_own(state, content, world, client, ia, ib, attribute, lean, key, proposed, intent, pour)
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
    v2_lines: list[str] = []
    if v2_on(content, state):
        fx, v2_lines = _v2_compound(state, content, world, ia, ib, result, piece, key, intent, pour, partner.lent if partner else None)
        state.player.insight_fx[piece] = fx
    else:
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
    return mine, [head] + v2_lines + extra + _charge(state, *_price(content, partner, "merge"))


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
    v2_lines: list[str] = []
    if v2_on(content, state):
        merged, v2_lines = _v2_deepen(state, content, world, keep, fa, fb)
    else:
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
    lines += v2_lines
    if merged.grand and not fa.grand and not fb.grand and not v2_lines:
        g = insight_fx.grand(content, merged.grand)
        lines.append(GRAND_LINE.format(name=g.name if g else merged.grand))
    cfg = content.config
    return keep, lines + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


def _merge_own(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None, ia: Insight, ib: Insight,
    attribute: str, lean: str, key: str, proposed: tuple[str | None, str] | None,
    intent: str | None = None, pour: bool = False,
) -> tuple[Insight | None, list[str]]:
    """有私有意境的合併（悟意境設計 0.2b）：合出來的也是私有的——不登記、每次都叫模型取名，名字只跟自己手上的比。"""
    if proposed is None:
        proposed = _named(client, content, world, _merge_messages(ia, ib), None)
    p = state.player
    name, note, _ = insights.own_name(state, content, world, f"{key}|{p.name}|{p.own_serial + 1}", proposed)
    result = insights.add_own(state, Insight(
        id="", name=name, attribute=attribute, lean=lean, creator=p.name, creator_shown=p.name, note=note,
        parents=sorted([ia.id, ib.id]), place=ia.place or ib.place,
    ))
    quality = insight_fx.better(insight_fx.quality_of(state, ia.id), insight_fx.quality_of(state, ib.id))
    v2_lines: list[str] = []
    if v2_on(content, state):
        fx, v2_lines = _v2_compound(state, content, world, ia, ib, result, result.id, key, intent, pour, None)
        state.player.insight_fx[result.id] = fx
    else:
        fx = insight_fx.roll(state, content, world, result.id, quality=quality, compound=True)
    head = f"「{ia.name}」與「{ib.name}」在你心中交融，化成「{result.name}」（屬{result.attribute}・{insight_fx.look(fx)}・{arts_mod.skill_name(content, result, fx)}）！"
    if result.note:
        head += f"\n{result.note}"
    head += "\n這份領悟是你自己的，江湖上沒有第二份。"
    _god(state, content, result.name, fx)
    cfg = content.config
    return result, [head] + v2_lines + _charge(state, cfg.merge_xinde, cfg.merge_stamina)


# ── 意境合成改版（Config.craft；設計稿 https://claude.ai/artifact/G4m44hK3At7x2bmqoAbceu ，Joy 2026-11-10「好」）──────────
# 開關開著、而且這一季開季時蓋了章（WorldState.craft_v2）才走這一段；關著一個字都不變。
# 合成（兩個不同的）：一般功效照左格主料那一路對到的那一個（不擲）；真意照「路 × 立意的型」對到合璧真意（traits.merged），
# 有沒有看火候（兩份層數＋上品 1＋地利 1，到 Config.craft.heat_need 就有；差一有 near_chance 自足）；每爐 bonus_chance 多帶一個一重。
# 傾注（pour）：兩份都用掉，新的一份承襲較淺的層數。合璧成神：兩份三重、傾注、那一路最濃之地、這一季的秘訣，四條齊了一定是神品。
# 神品只從合璧成神來：合成路（陽陰虛實）的一份帶真意時最多二重、一個一般功效（clamp）。揣摩也照火候，不擲。
# 化入（infuse）：同一路的其他份化成意蘊，攢滿加一重；不給真意、不算成神、不加熟。立意挑型第四批接模型，這一批照關鍵字。

PAIR_ORDER: dict[str, tuple[str, str]] = {"陽": ("剛", "快"), "陰": ("柔", "慢"), "虛": ("快", "柔"), "實": ("剛", "慢")}
FORMS = ("攻", "守", "變", "心")
FORM_WORDS = {  # 立意那一句的關鍵字（模型叫不動或第四批之前照這張；同自創的偏向表做法）待 joy 潤
    "攻": ("攻", "殺", "破", "斬", "焚", "燒", "擊", "衝", "猛", "盡", "滅", "劈"),
    "守": ("守", "護", "擋", "固", "穩", "盾", "防", "不退", "不動", "堅", "壁"),
    "變": ("變", "奇", "幻", "詭", "閃", "巧", "化", "轉", "影", "迷", "亂"),
    "心": ("心", "意", "念", "靜", "忍", "恨", "魂", "神", "志", "定"),
}
SECRETS = ("zishi", "maoshi", "calm", "main_top")  # 這一季每一路的秘訣照天機挑一條（secret_of）
SECRET_HINTS = {  # 熟到 Config.craft.hint_at 給的那一句（待 joy 潤）
    "zishi": "爐火最旺在夜半子時。",
    "maoshi": "天將亮未亮的卯時，兩股意念最肯相合。",
    "calm": "閉關出來，心還靜著的時候開爐。",
    "main_top": "主料要是上品的那一份。",
}
HE_GOD_LINE = "四條齊了：兩股意念擰成一線，合璧成神，悟出真意〔{grand}〕！"  # 待 joy 潤
HE_GOD_DEED = "在{place}合璧成神：「{name}」悟出真意〔{grand}〕。"  # 待 joy 潤
HE_GRAND_LINE = "火候到了，帶出真意〔{grand}〕。"  # 待 joy 潤
HE_NEAR_LINE = "火候差一分，爐火卻自己湊足了：帶出真意〔{grand}〕！"  # 待 joy 潤
HE_BONUS_LINE = "意外之喜：多悟出一個「{name}」。"  # 待 joy 潤
HE_POUR_LINE = "你把兩份全數傾注進去，兩個來源都化進了這一份。"  # 待 joy 潤
POUR_WITH_PARTNER = "論武時不能傾注：另一份不是你的。"  # 待 joy 潤
INFUSE_LINE = "你把 {n} 份化進「{name}」，攢了 {got} 點意蘊。"  # 待 joy 潤
INFUSE_UP = "「{name}」又深了一層（{mark}）。"  # 待 joy 潤
INFUSE_LEFT = "再 {left} 點意蘊加一重。"  # 待 joy 潤


def v2_on(content: Content, state: GameState) -> bool:
    """合成改版在這一季開了沒：主機的開關開著，而且這一季開季時也蓋了章（WorldState.craft_v2）。"""
    return content.config.craft.enabled and state.world.craft_v2


def main_general(content: Content, path: str, main_attribute: str) -> str | None:
    """合出來那一路的一般功效照主料（左格）定：陽是剛＋快，主剛 → 陽的第一個（乘勝），主快 → 第二個（朝陽）。
    主料不在那一對裡（浩然、血煞、第二層合成塌回來源的）照那一路第一個。沒有功效表是 None（測試內容）。"""
    pool = insight_fx.generals(content, path)
    if not pool:
        return None
    order = PAIR_ORDER.get(path)
    if order is not None and main_attribute in order and len(pool) > order.index(main_attribute):
        return pool[order.index(main_attribute)].key
    return pool[0].key


def form_from_intent(intent: str | None, key: str) -> str:
    """立意那一句挑型：照關鍵字表，出現最多的那一型；一個都沒有（或沒寫）照配方鍵的雜湊挑一型，同一個配方一定一樣。"""
    text = (intent or "").strip()
    counts = {form: sum(text.count(w) for w in words) for form, words in FORM_WORDS.items()}
    best = max(FORMS, key=lambda f: (counts[f], -FORMS.index(f)))
    if counts[best] > 0:
        return best
    import hashlib  # noqa: PLC0415

    return FORMS[hashlib.sha256(key.encode("utf-8")).digest()[0] % len(FORMS)]


def note_of(state: GameState, key: str):
    return state.player.fusion_book.get(key)


def form_of(state: GameState, key: str, intent: str | None = None) -> str:
    """這個配方的型：爐譜上記過的照用（想換第四批用重悟帖）；第一次照這一次的立意。"""
    note = note_of(state, key)
    return note.form if note is not None else form_from_intent(intent, key)


def _remember(state: GameState, key: str, form: str) -> None:
    """合了一次：爐譜記下型、熟 +1（論武合的也算）。"""
    from .state import FusionNote  # noqa: PLC0415

    note = state.player.fusion_book.get(key)
    if note is None:
        note = state.player.fusion_book[key] = FusionNote(form=form)
    note.uses += 1


def grand_for(content: Content, path: str, form: str) -> str | None:
    """這一路、這一型的真意：陽陰虛實對到合璧真意（traits.merged）；基本四路照原本那一路的真意（崩山……）。"""
    if path in PAIR_ORDER:
        hit = next((g for g in content.traits.merged if g.attribute == path and g.form == form), None)
        if hit is not None:
            return hit.id
    top = insight_fx.grand_of(content, path)
    return top.id if top is not None else None


def strongest_here(state: GameState, content: Content, path: str) -> bool:
    """地利：人在那一路最濃的地方。基本四路是此地最濃的意境就是那一路；陽陰虛實是此地最濃的是那一對的其中一路，
    而且那一對在這裡都悟得到（正式內容每一路兩三處）。"""
    here = content.locations.get(state.player.location)
    strong = insights.strong_of(here, content)
    if here is None or strong is None or strong not in content.insights:
        return False
    top = content.insights[strong].attribute
    pair = PAIR_ORDER.get(path)
    if pair is None:
        return top == path
    gives = {content.insights[i].attribute for i in insights.explore_gives(here, content) if i in content.insights}
    return top in pair and set(pair) <= gives


def heat(state: GameState, content: Content, a: str, b: str, path: str) -> int:
    """火候：兩份最深的一般功效層數相加，品質（兩份較好的）是上品 +1，在那一路最濃之地 +1。"""
    quality = insight_fx.better(insight_fx.quality_of(state, a), insight_fx.quality_of(state, b))
    return (
        insight_fx.strength(state, a) + insight_fx.strength(state, b)
        + (1 if quality == "上品" else 0) + (1 if strongest_here(state, content, path) else 0)
    )


def secret_of(world: WorldStateStore, path: str) -> str:
    """這一季這一路的秘訣：照天機與路挑一條（同一季全服一樣，換季換）。"""
    import hashlib  # noqa: PLC0415

    seed = f"合璧|{secret_recipes.tianji_of(world)}|{path}".encode("utf-8")
    return SECRETS[hashlib.sha256(seed).digest()[0] % len(SECRETS)]


def secret_met(state: GameState, content: Content, world: WorldStateStore, path: str, main: str) -> bool:
    """這一季的秘訣這一刻湊到了沒（main 是主料那一份的 id）。"""
    which = secret_of(world, path)
    if which in ("zishi", "maoshi"):
        hour = calendar.point(state.world.time, content, state.world).hour
        return hour in ((23, 0) if which == "zishi" else (5, 6))
    if which == "calm":
        return calm_now(state, content.config.craft.calm_hours)
    return insight_fx.quality_of(state, main) == "上品"


def secret_hint(state: GameState, content: Content, world: WorldStateStore, key: str, path: str) -> str | None:
    """熟到 hint_at 的配方，秘訣給一句提示；不到是 None。"""
    note = note_of(state, key)
    if note is None or note.uses < content.config.craft.hint_at:
        return None
    return SECRET_HINTS[secret_of(world, path)]


def god_conditions(
    state: GameState, content: Content, world: WorldStateStore, a: str, b: str, path: str, pour: bool,
) -> dict[str, bool]:
    """合璧成神的四條（a 是主料）：兩份都三重、傾注、那一路最濃之地、這一季的秘訣。只有陽陰虛實四路有合璧。"""
    if path not in PAIR_ORDER:
        return {"layers": False, "pour": pour, "place": False, "secret": False}
    deep = insight_fx.MAX_LAYERS
    return {
        "layers": insight_fx.strength(state, a) >= deep and insight_fx.strength(state, b) >= deep,
        "pour": pour,
        "place": strongest_here(state, content, path),
        "secret": secret_met(state, content, world, path, a),
    }


def _clamp(fx, compound: bool):
    """神品只從合璧成神來：合成路的一份帶真意時，最多二重、一個一般功效（照層數最深的留）。"""
    from .state import InsightFx  # noqa: PLC0415

    if not compound or fx.grand is None or not fx.general:
        return fx
    keep = max(fx.general, key=lambda k: fx.general[k])
    return InsightFx(quality=fx.quality, general={keep: min(fx.general[keep], insight_fx.MAX_LAYERS - 1)}, grand=fx.grand)


def _bonus(content: Content, fx, path: str, rng: random.Random) -> str | None:
    """意外之喜：還有空位時 bonus_chance 多帶一個一重的一般功效（那一路另一個）。回它的鍵，沒帶是 None。"""
    room = content.config.arts.insight_max_effects - len(fx.general) - (1 if fx.grand else 0)
    if room <= 0 or rng.random() >= content.config.craft.bonus_chance:
        return None
    other = next((t for t in insight_fx.generals(content, path) if t.key not in fx.general), None)
    if other is None:
        return None
    fx.general[other.key] = 1
    return other.key


def _bonus_line(content: Content, fx, extra: str | None) -> list[str]:
    """意外之喜那一句：多帶的那一個還留著才寫（被「神品只從合璧成神來」收掉的不寫）。"""
    t = insight_fx.general(content, extra) if extra is not None and extra in fx.general else None
    return [HE_BONUS_LINE.format(name=t.name)] if t is not None else []


def _fired(content: Content, h: int, rng: random.Random) -> str | None:
    """火候到了是 "full"；差一擲 near_chance 中了是 "near"；其餘 None。"""
    need = content.config.craft.heat_need
    if h >= need:
        return "full"
    if h == need - 1 and rng.random() < content.config.craft.near_chance:
        return "near"
    return None


def _drop_piece(state: GameState, piece: str) -> None:
    """一份用掉（傾注、化入）：從槽上拆下、拿出持有、紀錄跟著清掉。"""
    p = state.player
    where = arts_mod.where_slotted(state, piece)
    if where is not None:
        p.art_slots[where] = [None if i == piece else i for i in p.art_slots[where]]
    if piece in p.insights:
        p.insights.remove(piece)
    insight_fx.drop(state, piece)
    p.own_insights.pop(piece, None)


def _v2_compound(
    state: GameState, content: Content, world: WorldStateStore, ia: Insight, ib: Insight, result: Insight, piece: str,
    key: str, intent: str | None, pour: bool, lent: str | None,
) -> tuple[object, list[str]]:
    """合成改版的一份合成：回 (那一份的效果, 多寫的幾行)。見這一段的開頭。"""
    from .state import InsightFx  # noqa: PLC0415

    path = result.attribute
    quality = insight_fx.better(insight_fx.quality_of(state, ia.id), insight_fx.quality_of(state, ib.id))
    form = form_of(state, key, intent)
    _remember(state, key, form)
    general = main_general(content, path, ia.attribute)
    grand_id = grand_for(content, path, form)
    top = insight_fx.grand(content, grand_id)
    gname = top.name if top is not None else ""
    conds = god_conditions(state, content, world, ia.id, ib.id, path, pour)
    lines: list[str] = []
    if all(conds.values()) and general is not None and grand_id is not None:
        fx = InsightFx(quality=quality, general={general: insight_fx.MAX_LAYERS}, grand=grand_id)
        lines.append(HE_GOD_LINE.format(grand=gname))
        here = content.locations.get(state.player.location)
        annals.note(state, content, annals.DEED, HE_GOD_DEED.format(place=here.name if here else "爐前", name=result.name, grand=gname), 3)
    else:
        layers = min(insight_fx.strength(state, ia.id), insight_fx.strength(state, ib.id)) if pour else 1
        fx = InsightFx(quality=quality, general={general: layers} if general is not None else {})
        rng = insight_fx._rng(state, world, piece, "合璧")
        fired = _fired(content, heat(state, content, ia.id, ib.id, path), rng) if grand_id is not None else None
        if fired is not None:
            fx.grand = grand_id
            lines.append((HE_GRAND_LINE if fired == "full" else HE_NEAR_LINE).format(grand=gname))
        extra = _bonus(content, fx, path, rng)
        fx = _clamp(fx, True)
        lines += _bonus_line(content, fx, extra)
    if pour:
        for gone in (ia.id, ib.id):
            if gone != lent:
                _drop_piece(state, gone)
        lines.insert(0, HE_POUR_LINE)
    return fx, lines


def _v2_deepen(state: GameState, content: Content, world: WorldStateStore, keep: Insight, fa, fb) -> tuple[object, list[str]]:
    """合成改版的揣摩：層數相加（最多三重）、品質取好的；沒有真意時看火候（不擲），差一有自足；也有意外之喜。"""
    merged = insight_fx.deepen(content, fa, fb, None)
    compound = arts_mod.is_compound(content, keep)
    path = keep.attribute
    lines: list[str] = []
    rng = insight_fx.deepen_rng(state, world, keep.id, "合璧")
    if merged.grand is None:
        key = (secret_recipes.PREFIX + keep.secret if keep.secret else MERGE_PREFIX + "+".join(keep.parents)) if compound else ""
        grand_id = grand_for(content, path, form_of(state, key) if compound else "攻")
        room = content.config.arts.insight_max_effects - len(merged.general)
        layers = max([0, *fa.general.values()]) + max([0, *fb.general.values()])
        quality_bonus = 1 if merged.quality == "上品" else 0
        h = layers + quality_bonus + (1 if strongest_here(state, content, path) else 0)
        fired = _fired(content, h, rng) if grand_id is not None and room > 0 else None
        if fired is not None:
            merged.grand = grand_id
            top = insight_fx.grand(content, grand_id)
            lines.append((HE_GRAND_LINE if fired == "full" else HE_NEAR_LINE).format(grand=top.name if top else grand_id))
    extra = _bonus(content, merged, path, rng)
    already = insight_fx.look(fa) == "神" or insight_fx.look(fb) == "神"
    if not already:
        merged = _clamp(merged, compound)
    lines += _bonus_line(content, merged, extra)
    return merged, lines


def infuse_problem(state: GameState, content: Content, world: WorldStateStore, body: str, others: list[str]) -> str | None:
    """化入不行的原因；None＝可以。本體要是你的、不是頓悟神品、有一般功效、還沒到頂；化掉的那幾份要同一路、
    不帶真意、沒裝在槽上、不是頓悟神品。"""
    if not v2_on(content, state):
        return _refuse("這一季還不能化入。", "還沒開")  # 待 joy 潤
    held = state.player.insights
    if body not in held:
        return "本體要是你手上的一份。"  # 待 joy 潤
    if insight_fx.is_god(state, body):
        return _refuse(GOD_KEPT, "神品")
    ib = insights.resolve(body, content, world, state)
    fb = insight_fx.record(state, content, world, body, ib)
    if ib is None or not fb.general:
        return _refuse("這一份沒有能加深的功效。", "加不深")  # 待 joy 潤
    if insight_fx.strength(state, body) >= _cap(content, ib, fb):
        return _refuse(DEEPEST.format(name=ib.name, mark=arts_mod.strength_mark(insight_fx.strength(state, body))), "已到極處")
    if not others or len(set(others)) != len(others) or body in others:
        return "挑幾份要化進去的。"  # 待 joy 潤
    for other in others:
        io = insights.resolve(other, content, world, state) if other in held else None
        if io is None:
            return "要化的那幾份都要是你手上的。"  # 待 joy 潤
        if io.attribute != ib.attribute:
            return _refuse(f"「{io.name}」跟本體不是同一路，只能熔掉。", "不同路")  # 待 joy 潤
        fo = insight_fx.record(state, content, world, other, io)
        if insight_fx.is_god(state, other) or fo.grand is not None:
            return _refuse(f"「{io.name}」帶著真意，化不得。", "有真意")  # 待 joy 潤
        if arts_mod.where_slotted(state, other) is not None:
            return _refuse(f"「{io.name}」還裝在槽上，先拆下來。", "裝著")  # 待 joy 潤
    return None


def _cap(content: Content, ins: Insight, fx) -> int:
    """化入加得到幾重：三重；合成路帶真意的那一份二重（神品只從合璧成神來）。"""
    return insight_fx.MAX_LAYERS - (1 if fx.grand is not None and arts_mod.is_compound(content, ins) else 0)


def infuse(state: GameState, content: Content, world: WorldStateStore, body: str, others: list[str]) -> tuple[bool, list[str]]:
    """化入：others 那幾份化成意蘊（凡 1、佳 2、珍 3），攢滿 yun_per_layer 點本體最深的一般功效加一重（到頂為止）。
    被化的用掉；不收錢、不給真意、不加熟、不擲骰。回 (做了沒, 訊息)。"""
    problem = infuse_problem(state, content, world, body, others)
    if problem is not None:
        return False, [problem]
    cfg = content.config.craft
    p = state.player
    ib = insights.resolve(body, content, world, state)
    fb = insight_fx.record(state, content, world, body, ib).model_copy(deep=True)
    got = sum(cfg.yun_points.get(insight_fx.look(insight_fx.record(state, content, world, o)), 0) for o in others)
    for other in others:
        _drop_piece(state, other)
    total = p.fusion_yun.get(body, 0) + got
    lines = [INFUSE_LINE.format(n=len(others), name=ib.name, got=got)]
    key = max(fb.general, key=lambda k: fb.general[k])
    cap = _cap(content, ib, fb)
    while total >= cfg.yun_per_layer and fb.general[key] < cap:
        total -= cfg.yun_per_layer
        fb.general[key] += 1
        lines.append(INFUSE_UP.format(name=ib.name, mark=arts_mod.strength_mark(fb.general[key])))
    if fb.general[key] >= cap:
        total = 0
    p.insight_fx[body] = fb
    p.insight_strength.pop(body, None)
    if total > 0:
        p.fusion_yun[body] = total
        lines.append(INFUSE_LEFT.format(left=cfg.yun_per_layer - total))
    else:
        p.fusion_yun.pop(body, None)
    return True, lines


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
