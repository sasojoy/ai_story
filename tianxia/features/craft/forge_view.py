"""煉製頁的預覽與提示（第二輪第 88 批從 tianxia/skillview.py 切出來，煉製包獨用的那一半）：只讀狀態與內容、只產生文字，不改任何東西。

另外要跑的：包外讀這一檔的測試（`git grep -l "import forge_view" -- tests tianxia/features` 列的那幾個），test_for 挑不到。
"""
from __future__ import annotations

from tianxia import arts as arts_mod, fusion, insight_fx, insights, prologue
from tianxia.art_cards import fx_traits
from tianxia.library import cap_of, held_count
from tianxia.models import Content
from tianxia.state import GameState
from tianxia.world_state import WorldStateStore


def _known_insight_recipe(state: GameState, world: WorldStateStore, key: str) -> str:
    """意境＋意境的配方有沒有人合過（FB-082）：已知的寫「會合出「X」（屬…）」，沒人合過的寫「沒人合過」；
    合出來的那一種你手上已經有了寫「再合一份」（意境效果池：每一份各自擲效果）。只在兩個都是你悟得的時候才會呼叫。（待 joy 潤）"""
    known = world.lookup_insight_recipe(key)
    if known is None:
        return "\n沒人合過。"
    if known.id in state.player.insights:
        return AGAIN_PIECE.format(name=known.name)
    return f"\n會合出「{known.name}」（屬{known.attribute}）。"


AGAIN_PIECE = "\n再合一份「{name}」，效果另擲。"  # 待 joy 潤


def _strip_note(note: str) -> str | None:
    """_known_insight_recipe 那類「\n…。」的句子拿掉換行；空的是 None。"""
    text = note.strip()
    return text or None


# 煉製頁的說明那一行（W4）：爐裡只合意境（Joy 2026-10-21 拿掉武學＋武學、武學＋意境）；句子待 joy 潤
FORGE_ONE_INSIGHT = "再放一個意境：不同的合出新的意境，同一種的兩份是揣摩。"
FORGE_EMPTY = "放兩個意境：不同的合出新的意境，同一種的兩份揣摩加深。武學的意境到「修練」去裝。"


def forge_line(state: GameState, content: Content, world: WorldStateStore, insight_ids: list[str]) -> str:
    """煉製頁的說明：放了什麼、會做哪一種、花多少心得，或者為什麼還不能開爐。"""
    refusal = prologue.fuse_problem(state, content, insight_ids)  # 序章裡只准照劇本（跟 Game.forge 同一個判斷）
    if refusal is not None and len(insight_ids) == 2:
        return f"⚠ {refusal}"
    cfg, xinde = content.config, state.player.stats.get("xinde", 0)
    count = f"武學與意境 {held_count(state)}/{cap_of(state, content)}"
    held = state.player.insights
    if len(insight_ids) != 2:
        return f"**煉製**　{FORGE_ONE_INSIGHT if insight_ids else FORGE_EMPTY}{count}。"
    # 預覽不能拿來探：還沒悟到的意境，先於一切（查名字、屬性）就回開爐時會說的那句拒絕
    if any(i not in held for i in insight_ids):
        return f"⚠ {fusion.merge_problem(state, content, world, *insight_ids)}"
    a, b = (insights.resolve(i, content, world, state) for i in insight_ids)
    if a is None or b is None:
        return "（選了不存在的東西。）"
    if fusion.same_kind(state, a, b):
        merged, chance = _deepen_preview(state, content, world, a, b)
        head = (
            f"**揣摩**　兩份「{a.name}」揉成一份（{insight_fx.label(content, merged)}・{fire_of(chance, merged)['word']}），另一份用掉，"
            f"花 {cfg.merge_xinde} 點心得、{cfg.merge_stamina} 點體力（你有 {xinde} 點心得）。"
        )
    elif a.id == b.id:
        head = f"**揣摩**　「{a.name}」要兩份才揣摩得了。"
    else:
        attribute, _ = fusion.merge_shape(world, a, b, content, state)  # 跟 fusion.merge 真的登記的同一個函式算的（FB-082）
        high = arts_mod.high_of(content, attribute)
        skill = f"〔{high.name}〕" if high is not None else "一招"
        head = (
            f"**合併**　「{a.name}」＋「{b.name}」→ 一個新的意境（屬{attribute}・裝進槽是{skill}），"
            f"花 {cfg.merge_xinde} 點心得、{cfg.merge_stamina} 點體力（你有 {xinde} 點心得）。"
        )
        head += _known_insight_recipe(state, world, fusion.merge_key(*insight_ids))
    problem = fusion.merge_problem(state, content, world, *insight_ids)
    return head if problem is None else f"{head}\n⚠ {problem}"


def forge_preview(state: GameState, content: Content, world: WorldStateStore, insight_ids: list[str]) -> dict | None:
    """預覽卡；合成改版開著時多一個 he（fusion.v2_preview：火候、真意、成神四條），關著一個鍵都不多。
    insight_ids 是 routes.ForgePicks 時帶著網頁勾的傾注（pour）。"""
    card = _forge_preview(state, content, world, insight_ids)
    if card is not None and fusion.v2_on(content, state):
        card["he"] = fusion.v2_preview(state, content, world, *insight_ids, pour=bool(getattr(insight_ids, "pour", False)))
    return card


def _forge_preview(state: GameState, content: Content, world: WorldStateStore, insight_ids: list[str]) -> dict | None:
    """煉製頁的預覽卡（合成前就看得到合出來的樣子，跟出爐卡同一個形狀）。兩格都放好、而且都是你的意境時才給；
    其餘是 None，網頁照舊畫 forge_line 那一行。每一格都跟 forge_line 同一套函式算。
    鍵：kind（合併／揣摩）、made、attribute、attribute_why、gen、depth、quality、why、near、odds、slots、
    traits、keep、level、known、cost、problem、fire、grand_pct（合併而且那一路有真意：整數，同 _compound_grand，火候四段照它分，網頁寫「真意 N%」；
    揣摩、那一路沒有真意是 None，不寫「真意 0%」）。"""
    if len(insight_ids) != 2 or prologue.fuse_problem(state, content, insight_ids) is not None:
        return None
    cfg, xinde = content.config, state.player.stats.get("xinde", 0)
    held = state.player.insights
    empty = {"attribute_why": None, "gen": None, "depth": None, "near": None, "odds": None, "why": [], "keep": None, "level": None,
             "grand_pct": None}
    if any(i not in held for i in insight_ids):
        return None
    a, b = (insights.resolve(i, content, world, state) for i in insight_ids)
    if a is None or b is None:
        return None
    merge_cost = f"心得 {cfg.merge_xinde}・體力 {cfg.merge_stamina}（你有 {xinde} 點心得）"
    if a.id == b.id or fusion.same_kind(state, a, b):
        merged, chance = _deepen_preview(state, content, world, a, b)
        return {
            **empty, "kind": "揣摩", "made": f"「{a.name}」{insight_fx.label(content, merged)}", "attribute": a.attribute, "quality": None, "slots": None,
            "fire": fire_of(chance, merged),
            "traits": fx_traits(content, merged, a),
            "depth": "；".join(f"〔{e['name']}〕{e['desc']}" for e in insight_fx.effects(content, merged) if e["desc"]) or None,
            "keep": DEEPEN_KEEP,
            "known": None, "cost": merge_cost, "problem": fusion.merge_problem(state, content, world, *insight_ids),
        }
    attribute, _ = fusion.merge_shape(world, a, b, content, state)
    high = arts_mod.high_of(content, attribute)
    quality = insight_fx.better(insight_fx.quality_of(state, a.id), insight_fx.quality_of(state, b.id))
    pool = [t.name for t in insight_fx.generals(content, attribute)]
    grand = _compound_grand(content, quality) if high is not None else None  # 那一路沒有真意（high 是 None）就沒有這個數
    return {
        **empty, "kind": "合併", "made": "一個新的意境", "attribute": attribute, "quality": None, "slots": None,
        "fire": fire_of(grand or 0), "grand_pct": grand,
        "traits": [{"name": n, "layers": 1, "maybe": True} for n in pool] + ([{"name": high.name, "layers": 0, "grand": True, "maybe": True}] if high is not None else []),
        "depth": (f"擲一到兩個效果：{'或'.join(pool)}" + (f"，真意〔{high.name}〕：{high.desc}" if high is not None else "")) if pool else None,
        "known": _strip_note(_known_insight_recipe(state, world, fusion.merge_key(*insight_ids))),
        "cost": merge_cost, "problem": fusion.merge_problem(state, content, world, *insight_ids),
    }


# 爐火（招式與絕學稿案第五輪，Joy 2026-10-21 按建議）：預覽不寫品級、不寫機率，只寫火候四段與一句話。
# 引擎照真的大獎機會（百分比）分段；揣摩另看揉好那一份的品相，已經很好的不會寫成火弱。字待 joy 潤
FIRES = (
    ("火弱", "兩道意揉得勉強，能成，火候不足。"),
    ("火平", "兩道意相合，火候平平。"),
    ("火旺", "兩道意相契，爐火正旺。"),
    ("火熾", "兩道意一觸即融，爐火熾白，隱隱有光。"),
)
FIRE_CUTS = (10, 30, 55)  # 大獎機會 < 10% 火弱、< 30% 火平、< 55% 火旺，其餘火熾


def fire_of(chance: int, merged=None) -> dict:
    """{level 0～3, word, line}：chance 是大獎機會（百分比整數）；merged 是揣摩揉好的那一份（品相凡佳珍神各墊到 0～3）。"""
    level = sum(chance >= cut for cut in FIRE_CUTS)
    if merged is not None:
        level = max(level, insight_fx.LOOKS.index(insight_fx.look(merged)))
    word, line = FIRES[level]
    return {"level": level, "word": word, "line": line}


DEEPEN_KEEP = "同一個功效的層數相加（最多三重）；另一份用掉。"  # 待 joy 潤（第四輪起不寫品質）


def _deepen_preview(state: GameState, content: Content, world: WorldStateStore, a, b) -> tuple:
    """揣摩之後那一份的樣子（不擲大獎）與擲到大獎的機會（百分比整數）。"""
    if a.id == b.id:
        fx = insight_fx.record(state, content, world, a.id, a)
        return fx, 0
    fa, fb = insight_fx.record(state, content, world, a.id, a), insight_fx.record(state, content, world, b.id, b)
    return insight_fx.deepen(content, fa, fb, None), round(insight_fx.grand_chance(content, fa, fb) * 100)


def _compound_grand(content: Content, quality: str) -> int:
    cfg = content.config.arts
    second = min(1.0, cfg.insight_second.get(quality, 0.0) + cfg.compound_second_bonus)
    return round(second * min(1.0, cfg.insight_grand.get(quality, 0.0) * cfg.compound_grand_scale) * 100)


def _no(problem: str) -> dict:
    """一樣合不了的東西在清單上怎麼標：short 是兩三個字（fusion.Refusal），why 是按下去時會說的那一整句。"""
    return {"short": getattr(problem, "short", "合不了"), "why": str(problem)}


def forge_picks(state: GameState, content: Content, world: WorldStateStore, insight_ids: list[str]) -> dict | None:
    """爐裡只放了一個意境時，另一格還能放什麼（企劃者 2026-10-10「合過的意境不能合，常常丟上去按合成才知道」）：
    {"insights": {id: 合不了的標記或 None}}。每一格都照開爐時同一個判斷算（序章的 prologue.fuse_problem，再來
    fusion.merge_problem），不另寫一套。爐是空的、放滿了、放的不是你的：None。"""
    held = state.player.insights
    if len(insight_ids) != 1 or insight_ids[0] not in held:
        return None
    ins = {}
    for insight_id in held:  # 同一個意境也能放兩次（揣摩加深）
        problem = prologue.fuse_problem(state, content, [insight_ids[0], insight_id]) or fusion.merge_problem(
            state, content, world, insight_ids[0], insight_id)
        ins[insight_id] = None if problem is None else _no(problem)
    return {"insights": ins}
