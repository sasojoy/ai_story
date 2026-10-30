"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import armor, arts as arts_mod, atlas, clinic, roster, create as create_mod, cultivation, encounter, equipment, forge_secrets, fusion, insight_fx, insights, martial_arts, materials, might, mounts, moves, prologue, renown, seal, smithing, tactics as tactics_mod, team, traits, treasures, weapons
from .core.services import item_for  # 「去萬寶閣」停在哪一件（核心的錢包服務，3.10）
from .library import TOWN_TAG, cap_of, held_count, level_of, melt_confirm, melt_note, melt_problem, melt_value, owned_arts
from .martial_arts import (
    MAX_LEVEL, QUALITIES, MartialArt, power_at, shown_creator,
)
from .models import Content
from .state import PLAYER, GameState
from .world_state import WorldStateStore


# 五屬性各管什麼（武學與成長設計 6.1、6.3）：狀態列＋鈕底下那一行（計畫二最終審查 M2）。點數配了收不回來（6.2），身法、悟性、
# 博聞又看不到立即的變化，所以按之前要讀得到。名字照 Config.stat_names（見 stat_uses），這裡只寫用途；只寫玩家本人身上的事
STAT_USES = {
    "str": "武學威力",
    "agi": "打完一場少損氣血・落敗有機會閃成平手",
    "con": "內功威力・氣血上限・少受內傷",
    "wis": "探索悟得意境・衝關",  # 閉關 Joy 2026-10-25 拿掉了（畫面上沒有入口），不再寫
    "lore": "武學與意境的持有上限",
}
# 事件檢定、隨口應對讀得到五項（設計 6.1、6.3），但正式內容還沒有任何事件檢定博聞，所以先寫「前四項」（PM 2026-10-05）。
# joy 加了第一個檢定（或隨口應對看）博聞的事件之後，改回「事件的檢定也看這五項。」——
# tests/core/test_engine.py 的 test_the_stat_note_says_four_until_an_event_checks_lore 到時候會失敗提醒
STAT_CHECK_NOTE = "事件的檢定看前四項。"



def tactic_line(content: Content, art: MartialArt, level: int | None) -> str:
    """功法卡上那一句招（tactics.card_text 蓋印）；自創的招還生時後面補「（招還生）」。沒有招是空字串。"""
    sig = tactics_mod.of_art(content, art, level)
    if sig is None:
        return ""
    text = tactics_mod.card_text(sig, tactics_mod.title_of(sig, art))
    if moves.is_own(content, art) and art.move_rare:  # 撞到稀有路數的招：後面補小章（網頁畫成「稀有路數」那一枚）
        text += f"（{moves.RARE_WORD}）"
    if level is not None and moves.is_own(content, art) and not moves.ascended(art):
        if moves.raw(content, level):
            text += f"（{moves.RAW_WORD}）"
        elif level >= MAX_LEVEL:
            text += f"（{RIPE_MOVE}）"
    if moves.is_own(content, art) and (tail := traits.ultimate_of(content, art)) is not None:  # 破境之後接一行後勁
        text += "\n" + tactics_mod.card_text(tail, traits.AFTER_TITLE)
    return text


RIPE_MOVE = "將升"  # 待 joy 潤：第十成還沒破境，招那一行標的
RIPE_NOTE = "圓滿・待破境"  # 待 joy 潤


def fifth_ring(content: Content, art: MartialArt, level: int | None) -> dict | None:
    """第五個玉環（招式與絕學稿案第三節）：自創的才有；破境了亮（寫絕招的名字），還沒破境是暗的（第十成寫圓滿・待破境）。"""
    if not moves.is_own(content, art):
        return None
    if moves.ascended(art):
        move = moves.move_of(content, art)
        return {"on": True, "name": move.name if move is not None else art.name, "note": ""}
    return {"on": False, "name": "", "note": RIPE_NOTE if (level or 0) >= MAX_LEVEL else "破境"}

def stat_uses(content: Content, state: GameState | None = None) -> list[tuple[str, str]]:
    """五屬性的（名字, 用途），順序同 team.COMBAT_STATS——也就是狀態列 attrs、＋鈕的順序。
    減法季屬性五段開著（state 給了、這一季 Config.jianfa 的 stat_milestones）：用途換成「現在給你什麼」的數字（stat_lines，設計 4.5「看得見」）；
    關著照舊只寫用途。"""
    names = content.config.stat_names
    if state is not None and _milestones(state, content):
        lines = stat_lines(state, content)
        return [(names.get(key, key), lines[key]) for key in team.COMBAT_STATS]
    return [(names.get(key, key), STAT_USES[key]) for key in team.COMBAT_STATS]


def _milestones(state: GameState, content: Content) -> bool:
    from .rules import jianfa  # noqa: PLC0415  rules → team → …

    return jianfa(content, state.world, "stat_milestones")


def _signed_pct(ratio: float) -> str:
    """+12%、-6%（整數就不寫小數）。"""
    return f"{ratio:+.0%}" if round(ratio * 100, 6).is_integer() else f"{ratio:+.1%}"


# 減法季屬性五段（設計 4.5「看得見」）：角色卡、＋鈕底下那一行寫「現在給你什麼」；配點那一刻寫加了這一點多了什麼。字都待 joy 潤
STAT_NOW = {
    "str": "武學威力 {bonus}",
    "agi": "少損氣血 {saved}・閃避 {dodge}",
    "con": "內功威力 {bonus}・氣血上限 {hp}・少受內傷 {saved}",
    "wis": "修練與衝關 ×{factor}・感悟 {sense}",
    "lore": "持有 {slots} 格",
}
STAT_STEP = {  # 多配一點多了什麼（Game.allocate_stat 那一句冒號後面）
    "str": "武學威力 {bonus}",
    "agi": "閃避 {dodge_up}、少損氣血 {bonus}",
    "con": "內功威力 {bonus}、氣血上限 {hp}",
    "wis": "修練與衝關 {bonus}、感悟 {sense}",
    "lore": "持有 {slots} 格",
}


def _stat_numbers(state: GameState, content: Content, value: float, base: float) -> dict[str, str]:
    """一項屬性從 base 到 value 給的那幾個數字（每一點照這一季，team.per_point）：威力加成（bonus）、少損氣血與少受內傷（saved，
    照到 value 為止的總量）、閃避（dodge 總量、dodge_up 這一段）、氣血上限（hp）、修練與衝關的倍數（factor）、感悟（sense）、持有格（slots）。"""
    season = state.world
    delta = value - base
    rate = team.per_point(content, season, "bonus_per_point")
    dodge = team.per_point(content, season, "dodge_per_point")
    per_lore = team.per_point(content, season, "holding_per_lore_point")
    level = state.player.member.level
    hp = team.neili_cap(content, level, value, season=season) - team.neili_cap(content, level, base, season=season)
    slots = (max(0, int(value) - team.BASE_STAT) - max(0, int(base) - team.BASE_STAT)) * per_lore
    return {
        "bonus": _signed_pct(rate * delta),
        "saved": f"{max(0.0, rate * (value - team.BASE_STAT)):.0%}",
        "dodge": f"{max(0.0, dodge * (value - team.BASE_STAT)):.0%}",
        "dodge_up": _signed_pct(dodge * delta),
        "hp": f"{hp:+.0f}",
        "factor": f"{team.stat_factor(content, value, season):.2f}",
        "sense": f"{team.per_point(content, season, 'sense_rate_per_wis') * delta:+.0f}%",
        "slots": f"{slots:+.0f}",
    }


def stat_lines(state: GameState, content: Content) -> dict[str, str]:
    """五項各寫「現在給你什麼」（減法季屬性五段，設計 4.5）：從基準 5 到現在的值，照這一季每一點的效果（team.per_point）。"""
    stats = state.player.stats
    out = {}
    for key in team.COMBAT_STATS:
        value = float(stats.get(key, team.BASE_STAT))
        out[key] = STAT_NOW[key].format(**_stat_numbers(state, content, value, team.BASE_STAT))
    return out


def stat_step(state: GameState, content: Content, key: str, before: float) -> str:
    """多配一點（before → before＋1）多了什麼（Game.allocate_stat 那一句冒號後面；減法季屬性五段）。"""
    return STAT_STEP[key].format(**_stat_numbers(state, content, before + 1, before))


def rules_line(content: Content) -> str:
    return "身上一門內功、一門武學：花心得練成；意境就是技能，裝進武學的意境槽（收得下的屬性才裝得進去）；在「煉製」兩門武學合成一門新的、意境揣摩得更深，或用心得自創一門。"


ARTS_ATTRIBUTES = "剛柔快慢陰陽虛實"  # 武學的八個屬性，寫給玩家看的順序（FB-089）；跟升級配點的五項（臂力身法根骨悟性博聞）是兩回事
ATTRIBUTE_ORDER = "陰陽剛柔快慢虛實"  # 相剋的一對怎麼排字（設計 6.1 的順序）：「陰陽」「剛柔」，不寫成「陽陰」


def attribute_line(content: Content) -> str:
    """修練頁與煉製頁各摺一行的「屬性有什麼用」（W2）。屬性的規則有三條：內功與武學同屬性整個人威力加成（team.pairing，
    Config.pairing_bonus）、兩門是相剋的一對打折（Config.pairing_penalty，哪幾對看 martial_arts.ATTRIBUTE_COUNTERS）、
    武學克住對手的屬性時乘 encounter.COUNTER_BONUS。這裡一個數字都不自己寫，全部讀那幾處，改了規則這一句跟著變。
    句子待 joy 潤。"""
    cfg = content.config
    pairs: list[str] = []
    for attacker, defender in martial_arts.ATTRIBUTE_COUNTERS.items():  # 表是雙向的（陽克陰、陰克陽）：每一對只寫一次
        pair = "".join(sorted((attacker, defender), key=ATTRIBUTE_ORDER.find))
        if pair not in pairs:
            pairs.append(pair)
    penalty = _pct(-cfg.pairing_penalty).replace("-", "−")  # 減號用 −，跟加號並排好讀
    # FB-089：「屬性」有兩個意思（升級配的五項、武學的剛柔快慢陰陽虛實），這一句講的是後者，開頭先把名字寫全；
    # 八個字的順序是企劃者定的「剛柔快慢陰陽虛實」（ARTS_ATTRIBUTES，測試擋它跟 martial_arts.ATTRIBUTES 是同一組字）
    return (
        f"武學的屬性（{ARTS_ATTRIBUTES}）：內功與武學同屬，威力 {_pct(cfg.pairing_bonus)}；"
        f"兩門相剋（{'、'.join(pairs)}）威力 {penalty}；武學克住對手的屬性，威力 ×{encounter.COUNTER_BONUS:g}。"
    )


def practice_hint(state: GameState, content: Content) -> str | None:
    """主畫面的提示：確實有事可做、而且付得起時才回傳一句話（心得還要至少 `xinde_hint_threshold`，現在是 0：explain-2 起
    只看「付得起、做得了」，第一件做得了的事就提示——以前要攢到 50，新人心得 34 不知道拿去哪裡用，FB-100）。

    心得的去處（武學與成長設計第四節）：練成（身上這一門還沒第十成、付得起下一成）與合成（手上有意境、
    持有沒滿、付得起一次，見 fusion.can_forge）。兩樣都做不了就閉嘴，免得變成嘮叨。休季時什麼都不能做，也不提示（FB-047）。
    去處照畫面寫：練成的鈕就在俠客頁身上那一門的卡上（分頁 2026-10-24 從「修練」改成「俠客」，這句就寫在那一頁上，不寫「去修練」）、煉製照底部分頁的名字（FB-047）。
    """
    xinde = state.player.stats.get("xinde", 0)
    if xinde < content.config.xinde_hint_threshold or state.world.ended:
        return None
    todo = [kind for kind in ("內功", "武學") if team.can_practise(state, content, kind)]
    parts = []
    if todo:
        parts.append(f"點上面身上的武學練成{'、'.join(todo)}")
    if fusion.can_forge(state, content):  # 手上有意境、持有沒滿、付得起一次合成或合併才提；光有意境不算
        parts.append("去「煉製」把兩個意境合成新的")  # 待 joy 潤
    if not parts:
        return None
    return f"💡 你已攢下 {xinde} 點心得。{'，或'.join(parts)}。"


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
    """煉製頁的預覽卡（合成前就看得到合出來的樣子，跟出爐卡同一個形狀）。兩格都放好、而且都是你的意境時才給；
    其餘是 None，網頁照舊畫 forge_line 那一行。每一格都跟 forge_line 同一套函式算。
    鍵：kind（合併／揣摩）、made、attribute、attribute_why、gen、depth、quality、why、near、odds、slots、
    traits、keep、level、known、cost、problem。"""
    if len(insight_ids) != 2 or prologue.fuse_problem(state, content, insight_ids) is not None:
        return None
    cfg, xinde = content.config, state.player.stats.get("xinde", 0)
    held = state.player.insights
    empty = {"attribute_why": None, "gen": None, "depth": None, "near": None, "odds": None, "why": [], "keep": None, "level": None}
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
    return {
        **empty, "kind": "合併", "made": "一個新的意境", "attribute": attribute, "quality": None, "slots": None,
        "fire": fire_of(_compound_grand(content, quality) if high is not None else 0),
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


def fx_traits(content: Content, fx, insight=None) -> list[dict]:
    """卡上的效果籤：一般功效寫層數，大獎 layers 0、grand true；給了意境、它是秘方合出來的，再加那一條特別功效（special true）。"""
    out = [{"name": e["name"], "layers": e["layers"], "grand": e["grand"]} for e in insight_fx.effects(content, fx)]
    sp = arts_mod.special_of(content, insight.secret_special) if insight is not None and insight.secret_special else None
    if sp is not None:
        out.append({"name": sp.name, "layers": 0, "grand": False, "special": True})
    return out


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


def heal_note(state: GameState, content: Content) -> str:
    """療傷鈕上的價錢：付得起全治寫「內傷 N・M 兩」，只付得起一部分寫「治 N 點・M 兩（還剩 K 點）」（team.heal_plan）。
    醫館那一顆（engine._heal_option）與修練頁那一顆（heal_button 的 note）共用。"""
    from . import territory  # noqa: PLC0415  territory → rules：延後 import

    points, cost, left = team.heal_plan(state, content, state.player.member)
    if team.heal_free(state, content):  # 承露那一區（玉璽碎片改版第 2 批）：不收錢，不寫折扣的原因
        return f"內傷 {int(state.player.member.injury)}・{team.HEAL_FREE_NOTE}"
    # 名聲 4.1、5.2：價錢後面寫原因，地盤、名望、俠的醫館折扣寫在同一個括號（FB-294）；名聲關著是空的
    why = renown.reasons_text(territory.price_parts(state, content, heal=True) + [renown.clinic_part(state, content)])
    if left > 0:
        return f"治 {points} 點・{cost} 兩（還剩 {left} 點）{why}"
    return f"內傷 {int(state.player.member.injury)}・{cost} 兩{why}"


def heal_button(state: GameState, content: Content) -> dict:
    """修練頁「療傷」鈕要的資料（FB-082）：ok 是按不按得下去，why 是按不下去的原因（跟 team.heal 回的是同一句）。
    鈕上的字（內傷與價錢）是卷軸卡自己寫的：內傷讀狀態列、價錢讀 menxia 的 heal_cost（team.heal_cost，每 2 點內傷 1 兩，
    真的收的就是這個數），所以這裡不送字（review-ap3 M4）。內傷不到 1 點狀態列不寫（int），鈕也不亮。
    醫館（企劃者 2026-10-12）：不在醫館時灰掉，clinic 是「這裡沒有醫館，最近的在…」那一句，網頁照它寫在鈕上；在醫館是 None。"""
    member = state.player.member
    if int(member.injury) < 1:
        return {"ok": False, "why": "氣血無恙，不用療傷。", "clinic": None, "note": None}
    where = clinic.problem(state, content)
    problem = team.heal_problem(state, content, member, where)
    return {"ok": problem is None, "why": problem, "clinic": where, "note": heal_note(state, content) if problem is None else None}


def _nearest_town(state: GameState, content: Content) -> tuple[str | None, bool]:
    """（離玩家最近的城鎮名字, 玩家人就在城鎮裡）：路程照 atlas.routes（只走摸清的路）；一座都走不到時名字是 None。"""
    towns = {loc_id for loc_id, loc in content.locations.items() if TOWN_TAG in loc.tags}
    here = state.player.location
    if here in towns:
        return content.locations[here].name, True
    reachable = [(route.minutes, loc_id) for loc_id, route in atlas.routes(state, content).items() if loc_id in towns]
    return (content.locations[min(reachable)[1]].name if reachable else None), False


def relearn_note(state: GameState, content: Content, art_id: str) -> str | None:
    """熔掉這一門之後怎麼拿回來（FB-081）：開局送的基礎武學在任何城鎮免費重學（library._taught_here）、各地教的基礎武學
    回教它的那個地方、花原價學；合成出來的與內容直接給的絕學沒有重學的地方，是 None。寫給玩家看的一句話——
    連「江湖頁『此地還能做』」都寫上：「學…」的選項不在行動列、收在那個摺疊裡（待 joy 潤）。"""
    skill = content.skills.get(art_id)
    if skill is None:
        return None
    find = f"在江湖頁「此地還能做」找「學{skill.name}」。"
    if art_id in content.config.starter_skills:
        name, here = _nearest_town(state, content)
        if here:
            return f"熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學{skill.name}」。"
        near = f"（離你最近的是{name}）" if name else ""
        return f"熔了還能免費重學：到任何城鎮{near}，{find}"
    if skill.learn is not None:
        fee = f"學費 {skill.learn.silver} 兩" if skill.learn.silver else "免費"
        return f"熔了想拿回來，到{content.locations[skill.learn.at].name}再學一次（{fee}），{find}"
    return None


def art_rows(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """修練與煉製兩頁的武學清單：身上的在前，再來功法庫。每門一列：品質（自己那一份）、第幾成、融的意境、
    修練與熔煉按不按得下去與為什麼。只讀狀態，不改東西。"""
    member = state.player.member
    rows = []
    hut = prologue.active(state, content)
    for art_id in owned_arts(state):
        art = team.player_art(state, content, world, art_id)  # 自己那一份：品質照自己修練到的
        if art is None:
            continue
        level = level_of(state, art_id)
        insight_name = None  # 武學重構：沒有「融的意境」了（網頁還讀這個鍵；槽裡裝的在 slots）
        # 修練（武學重構）：只剩上品到了極處服丹強行衝絕學那一格；還沒到極處、不是上品都灰掉寫原因
        problem = cultivation.cultivate_problem(state, content, world, art_id, use_legend=True)
        legend = None
        if problem is None:
            note = f"上品已到極處：等一場硬仗的契機，或服丹強行衝關・體力 {content.config.cultivate_stamina}"  # 待 joy 潤
            legend = _force_choice(state, content, world, art_id)
        else:
            note = problem
        stuck = melt_problem(state, art_id, art.name, only=prologue.melt_only(state, content), content=content)  # 跟 library.melt_art 同一個判斷
        value = melt_value(state, content, world, art_id) if stuck is None else 0
        worn = art_id in (member.neigong_id, member.wugong_id)
        relearn = None if worn else relearn_note(state, content, art_id)  # 熔了怎麼拿回來（FB-081）：身上正在練的不能熔，不寫
        weapon = weapons.art_weapon(art_id, content, world) if art.kind == "武學" else None
        compare = team.compare_with_worn(state, content, world, art)  # 跟身上同一種那門比的一句（W6、FB-088）；身上那門自己是空字串
        row = {
            "id": art_id, "name": art.name, "kind": art.kind, "quality": art.quality, "attribute": art.attribute,
            "level": level, "worn": worn, "insight": insight_name,
            "card": art_card(
                art, level, insight_name, parent_names(art, content, world), traits.card_line(content, art), compare,
                gen_word=gen_word(art, content, world),
            ),
            "gen": "",  # 武學重構：沒有境界了（網頁的篩選還讀這個鍵）
            "affinity": arts_mod.affinity_text(art),  # 相容屬性（「快、陽、虛」或「兼容並蓄」）
            "slots": slot_rows(state, content, world, art),  # 意境槽：每格裝的那一招（None 是空的）；寫死的武學是空清單
            "colors": arts_mod.slot_colors(state, content, art),  # 每一格收哪幾種屬性（跟 slots 一樣長；[] 是任色）
            # 攤開空格挑意境時，跟這一門（穿著的照身上兩門）撞到同效果的那幾份寫一句（stack_parts）：{意境 id: 「先手算五成」}；
            # 有任何一份撞到時 stack_rule 是規則那一句，挑的地方寫一次
            "stack": (stack := {} if arts_mod.fixed(content, art_id) else {
                i: "；".join(p) for i in state.player.insights if not arts_mod.where_slotted(state, i) and (p := stack_parts(state, content, world, art, i))}),
            "stack_rule": STACK_RULE if stack else "",
            "pose": create_mod.icon_pose(content, art, weapon),  # 功法卡上的小火柴人：自創的照自己擺的式，其餘照兵器挑預設架式
            "weapon": weapon,  # 小圖上手裡拿什麼（內功、推不出來的是 None）
            "rating": arts_mod.rating(content, art, level or 1, state, world),  # 戰力：威力 ×（1＋槽裡技能的加成）
            # 評分（第三批）：槽裡效果的分數加總，沒有上限；不是衝絕學的門檻（Joy 2026-10-20），只拿來比高下、排武學榜
            "score": arts_mod.score(state, content, world, art),
            "score_note": score_note(state, content, world, art),  # 評分旁邊那一句（秘方特效只算發動的那一條）；沒有是空字串
            # 本命戰法或小戰法那一句（tactics.card_text）：直接寫在卡上，學來的武學靠它看得出跟別門不一樣（Joy 2026-10-21）；沒有是空字串
            # 自創的招照這一門練到的成數算（前幾成還生，卡上補一句）
            "tactic": tactic_line(content, art, level),
            "fifth": fifth_ring(content, art, level),  # 自創的第五個玉環（破境的絕招）；不是自創是 None
            # 戰力（招式與絕學稿案第四輪）：庫裡這一門換上身之後全身的戰力；身上那一門是 None（看狀態列那個數）
            "might": None if worn else might.with_art(state, content, world, art_id),
            **_look(content, art),  # 自創的品相（純、渾、透、稀有路數；兩樣珍、三樣神）
            "compare": compare,  # 卷軸卡直接把它寫在功法庫那張卡的鈕上面（改練之前看得到）；點開「詳情」時功法卡裡也有
            "cultivate": {
                "ok": problem is None, "note": note, "legend": legend,  # 服丹衝關（心得換丹、心得衝關都拿掉了，Joy 2026-10-21）
                "xinde": None,  # 網頁與舊測試還讀這個鍵：一律沒有
                # 到了極處、手上沒丹：引去萬寶閣買破境丹（那一件商品的 id；商城關著、沒賣、或不缺丹是 None）
                "shop": item_for(content, "legend") if cultivation.needs_pill(state, content, world, art_id) else None,
            },
            "melt": {
                "ok": stuck is None,
                "note": stuck if stuck is not None else melt_note(value),
                "value": value,  # 熔了退多少心得（批量熔煉合計用）
                # 熔煉鈕按下去的確認框問什麼：整句在這裡寫好（W9 的直話＋FB-081 的去哪裡重學，見 library.melt_confirm）；熔不掉的沒有
                "confirm": melt_confirm(art.name, value, relearn) if stuck is None else "",
            },
            "relearn": relearn,  # 合成的、內容直接給的絕學沒有重學的地方，是 None
            "judge": melt_judge(state, content, world, art, level),  # 批量熔煉每一列判斷好壞的資料（威力、比身上強弱、功效、絕招）
        }
        if hut:  # 序章：這一列在這一步可以發光的鍵由伺服器說（T7 走查 W-A、W-B）；序章外沒有這個鍵
            row["glow"] = prologue.art_glow(state, content, world, art_id, cultivate_ok=problem is None, melt_ok=stuck is None)
        rows.append(row)
    # 功法庫多了要找得到（FB-085）：身上的在前，再照品質（絕學＞上品＞中品＞下品，自己那一份）、成多的先、最後比名字；
    # 修練頁與煉製頁畫的是同一份，所以兩頁的順序一樣
    rows.sort(key=lambda r: (not r["worn"], -QUALITIES.index(r["quality"]), -(r["level"] or 0), r["name"]))
    return rows


def shown_art(state: GameState, content: Content, world: WorldStateStore, kind: str) -> dict | None:
    """榜單點開的唯讀功法卡（Joy 2026-10-22「上榜的武學其他玩家應該要可以點的開來看卡」）：主人身上那一門內功或武學，
    跟主人修練頁那張同一份料（品質、品相、成數、評分、意境槽與功效、招、功法卡的字），照主人那一份畫。
    只放看的東西：修練、熔煉、改練、比身上、換上後戰力這些只有主人自己按得到的都不給。kind 是「內功」或「武學」；那一欄空著是 None。"""
    member = state.player.member
    art_id = member.neigong_id if kind == "內功" else member.wugong_id
    art = team.player_art(state, content, world, art_id) if art_id else None
    if art is None:
        return None
    level = level_of(state, art_id)
    weapon = weapons.art_weapon(art_id, content, world) if art.kind == "武學" else None
    return {
        "id": art_id, "name": art.name, "kind": art.kind, "quality": art.quality, "attribute": art.attribute, "level": level,
        "card": art_card(art, level, None, parent_names(art, content, world), traits.card_line(content, art), gen_word=gen_word(art, content, world)),
        "affinity": arts_mod.affinity_text(art),
        "slots": slot_rows(state, content, world, art), "colors": arts_mod.slot_colors(state, content, art),
        "pose": create_mod.icon_pose(content, art, weapon), "weapon": weapon,
        "score": arts_mod.score(state, content, world, art), "score_note": score_note(state, content, world, art),
        "tactic": tactic_line(content, art, level), "fifth": fifth_ring(content, art, level),
        **_look(content, art),
    }


def shown_gear(content: Content, item, live: bool = True) -> dict:
    """榜單神器譜點開的唯讀裝備卡（同 shown_art）：名字、種類、屬性、階品、淬煉、磨損、特技；item 是 state.Equipment。
    威力加成看配的是哪一門武學，因人而異，不寫。live 是假的（那一件已經不在主人手上，照譜上記的拼一件）時淬煉、磨損是 None。"""
    slot = item.slot
    return {
        "name": item.name, "slot": slot, "what": weapons.noun(item.kind) if slot == "weapon" else equipment.SLOTS[slot].label,
        "attribute": item.attribute, "grade": equipment.grade(item), "tempers": item.tempers if live else None,
        "temper_max": (content.config.weapons if slot == "weapon" else content.config.armor).temper_max,
        "edge": item.edge if live else None, "wear_word": equipment.WEAR_WORDS.get(slot, ""),
        "tactic": tactics_mod.item_lines(content, item),
    }


def melt_judge(state: GameState, content: Content, world: WorldStateStore, art: MartialArt, level: int) -> dict:
    """批量熔煉那一列要的判斷資料（企劃者 2026-10-16「分解的時候無法判斷武學或內功意境的好壞」）：只讀、只顯示。
    power 是現在這一成的威力（同功法卡）；worn_diff 是跟身上同一種那門比（第一成對第一成，同 team.compare_with_worn 的數字；
    身上那一欄空著、這門就是身上那門是 None）；traits 是一般功效的名字與層數（照這一門自己的清單，不乘品質）、special 是特別功效、
    ultimate 是絕學立招的絕招、tactic 是本命戰法或學來的武學的小戰法（都是名字，沒有是 None），tactic_title 是卡上寫哪一種。"""
    member = state.player.member
    worn_id = member.neigong_id if art.kind == "內功" else member.wugong_id
    diff = None
    if worn_id is not None and worn_id != art.id:
        worn = team.player_art(state, content, world, worn_id)
        if worn is not None:
            diff = round(power_at(art, 1) - power_at(worn, 1), 1)
    names = []
    if content.traits.general:
        mine = traits.traits_of(art)
        names = [{"name": traits.general(content, a).name, "layers": mine.count(a), "tier": 1}
                 for a in dict.fromkeys(mine)]
        names += [{"name": sp.name, "layers": 1, "tier": 2}
                  for sp in (traits.special(content, sid) for sid in art.extra_specials) if sp is not None]
        for top in traits.highs_of(content, art):
            names.append({"name": top.name, "layers": 1, "tier": 3})
    special = traits.special(content, art.special)
    ult = traits.ultimate_of(content, art)
    sig = tactics_mod.of_art(content, art)  # 本命戰法或小戰法（自創借來的也算）
    return {
        "power": round(power_at(art, level), 1),
        "worn_diff": diff,
        "traits": names,
        "special": special.name if special is not None else None,
        "ultimate": ult.name if ult is not None else None,
        "tactic": sig.name if sig is not None else None,
        "tactic_title": tactics_mod.title_of(sig, art) if sig is not None else None,  # 招名前面那一枚印（本命、看家、私印）
    }


# ── 同效果好幾份（Joy 2026-10-22 選「第二份算半」；「玩家需要知道這個知識」）────────────
# 打仗照身上兩門一起算（traits.loadout），所以穿在身上的那一門照兩門一起看；沒穿的照它自己。格子上寫「先手算五成」「流光多一半」，
# 裝意境之前寫這一份會算幾成、到頂了沒。數字照 traits.stack_value，跟打仗、戰力、評分同一條。字待 joy 潤
STACK_RULE = "同效果第二份起算一半，最多一倍半"
HIGH_MORE = "多一半"  # 同一個真意第二份：發動的機會多一半
HIGH_LONGER = "多撐一回合"  # 本來就每次發動的真意（鎮岳、金身）第二份
TOPPED = "{name}已到頂，再裝不加"


def _stack_scope(state: GameState, content: Content, world: WorldStateStore, art: MartialArt) -> list[MartialArt]:
    member = state.player.member
    if art.id not in (member.wugong_id, member.neigong_id):
        return [art]
    out = []
    for art_id in (member.wugong_id, member.neigong_id):
        a = art if art_id == art.id else team.player_art(state, content, world, art_id)
        if a is not None:
            out.append(a)
    return out


def _stack_cells(state: GameState, content: Content, world: WorldStateStore, scope: list[MartialArt]) -> list[tuple[str, int, float, object]]:
    """範圍裡每一格：(武學 id, 第幾格, 品級倍數, 那一份的效果)；照武學、格子的先後。"""
    out = []
    for a in scope:
        if arts_mod.fixed(content, a.id):
            continue
        mult = traits.multiplier(content, a.quality) * (1 + moves.look_bonus(content, a))
        for i, insight_id in enumerate(arts_mod.slots_of(state, content, a)):
            ins = insights.resolve(insight_id, content, world, state) if insight_id else None
            if ins is not None:
                out.append((a.id, i, mult, insight_fx.record(state, content, world, insight_id, ins)))
    return out


def _high_word(top, n: int) -> str:
    if n == 2:
        return HIGH_MORE if (top.tactic.rate or 0) < 1 else HIGH_LONGER
    return "不加" if n > 2 else ""


def slot_stack_marks(state: GameState, content: Content, world: WorldStateStore, art: MartialArt) -> dict[int, str]:
    """這一門每一格同效果的那一份算了幾成：{第幾格: 「先手算五成・流光多一半」}；照算的格子不寫。"""
    cfg = content.config.arts
    cells = _stack_cells(state, content, world, _stack_scope(state, content, world, art))
    per_key: dict[str, list[tuple[float, tuple[str, int]]]] = {}
    for art_id, i, mult, fx in cells:
        for key, n in fx.general.items():
            t = traits.general(content, key)
            per_key.setdefault(key, []).append((t.per_layer * min(arts_mod.MAX_STRENGTH, n) * mult, (art_id, i)))
    marks: dict[tuple[str, int], list[str]] = {}
    for key, rows in per_key.items():
        if len(rows) < 2:
            continue
        t = traits.general(content, key)
        for x, (_, at) in zip(traits.stack_shares([v for v, _ in rows], t.cap, cfg.stack_share, cfg.stack_ceiling), rows):
            if x < 0.95:
                marks.setdefault(at, []).append(t.name + traits.share_word(x))
    seen: dict[str, int] = {}
    for art_id, i, _, fx in cells:
        top = insight_fx.grand(content, fx.grand) if fx.grand else None
        if top is None:
            continue
        seen[fx.grand] = seen.get(fx.grand, 0) + 1
        if (word := _high_word(top, seen[fx.grand])):
            marks.setdefault((art_id, i), []).append(top.name + word)
    return {i: "・".join(words) for (art_id, i), words in marks.items() if art_id == art.id}


def stack_hint(state: GameState, content: Content, world: WorldStateStore, art: MartialArt, insight_id: str) -> str:
    """把這一份意境裝進這一門之前的一句：身上（或這一門）已經有同一個功效、同一個真意時，寫這一份算幾成、到頂了沒；
    沒有撞到的是空字串。"""
    parts = stack_parts(state, content, world, art, insight_id)
    return f"{STACK_RULE}：{'；'.join(parts)}" if parts else ""


def stack_parts(state: GameState, content: Content, world: WorldStateStore, art: MartialArt, insight_id: str) -> list[str]:
    """stack_hint 冒號後面那幾段（「先手算五成」「先手已到頂，再裝不加」「流光多一半」）。"""
    ins = insights.resolve(insight_id, content, world, state)
    if ins is None or arts_mod.fixed(content, art.id):
        return []
    cfg = content.config.arts
    fx = insight_fx.record(state, content, world, insight_id, ins)
    cells = _stack_cells(state, content, world, _stack_scope(state, content, world, art))
    mult = traits.multiplier(content, art.quality) * (1 + moves.look_bonus(content, art))
    parts = []
    for key, n in fx.general.items():
        t = traits.general(content, key)
        had = [t.per_layer * min(arts_mod.MAX_STRENGTH, m) * c_mult for _, _, c_mult, f in cells for k, m in f.general.items() if k == key]
        if not had:
            continue
        mine = t.per_layer * min(arts_mod.MAX_STRENGTH, n) * mult
        x = traits.stack_shares(had + [mine], t.cap, cfg.stack_share, cfg.stack_ceiling)[-1]
        if x < 0.05:
            parts.append(TOPPED.format(name=t.name))
        elif x < 0.95:
            topped = traits.stack_value(had + [mine], t.cap, cfg.stack_share, cfg.stack_ceiling) >= t.cap * cfg.stack_ceiling - 1e-9
            parts.append(f"{t.name}{traits.share_word(x)}" + ("，裝了就到頂" if topped else ""))
    top = insight_fx.grand(content, fx.grand) if fx.grand else None
    if top is not None:
        n = 1 + sum(1 for _, _, _, f in cells if f.grand == fx.grand)
        if n > 2:
            parts.append(TOPPED.format(name=top.name))
        elif (word := _high_word(top, n)):
            parts.append(top.name + word)
    return parts


def slot_rows(state: GameState, content: Content, world: WorldStateStore, art: MartialArt) -> list[dict | None]:
    """修練頁一門武學的意境槽：每格 {id, name, attribute, skill, mark, strength} 或 None（空格）。寫死的武學是空清單。
    stack 是同效果好幾份時這一份算了幾成（slot_stack_marks；照算的是空字串）。"""
    rows: list[dict | None] = []
    stacks = slot_stack_marks(state, content, world, art) if not arts_mod.fixed(content, art.id) else {}
    idle = arts_mod.idle_specials(state, content, world, art)  # 同一門第二條起的秘方特效不發動、不算分：籤灰掉、底下寫為什麼
    for n_slot, insight_id in enumerate(arts_mod.slots_of(state, content, art)):
        if insight_id is None:
            rows.append(None)
            continue
        ins = insights.resolve(insight_id, content, world, state)
        if ins is None:
            rows.append(None)
            continue
        strength = arts_mod.strength_of(state, insight_id)
        fx = insight_fx.record(state, content, world, insight_id, ins)
        rows.append({
            "id": insight_id, "name": ins.name, "attribute": ins.attribute, "skill": arts_mod.skill_name(content, ins, fx),
            "mark": arts_mod.strength_mark(strength), "strength": strength, "desc": arts_mod.skill_desc(content, ins, strength, fx),
            "quality": fx.quality, "fx": fx_traits(content, fx, ins),  # 意境效果池：這一份的品質與每一個效果（大獎 grand）
            "look": insight_fx.look(fx),  # 品相凡佳珍神（玉環上那一枚印；底子 quality 不給玩家看）
            "stack": stacks.get(n_slot, ""),
            "idle": idle.get(n_slot, ""),
        })
        if n_slot in idle:
            for t in rows[-1]["fx"]:
                if t.get("special"):
                    t["idle"] = True
    return rows


def _force_choice(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> dict:
    """上品到了極處的那一門：「服下破境丹」那一格是強行衝關（待 joy 潤）。網頁照舊畫（count、bonus、label、note）；
    bonus 是這一次衝開的機會（cultivation.force_odds，跟實際擲的一致）。"""
    cfg, count = content.config, state.player.legend_items
    odds = cultivation.force_odds(state, content, world, art_id)
    return {
        "count": count,
        "bonus": odds,
        "label": f"服下{cfg.legend_item_name}強行衝關（剩 {count} 枚）",
        "note": f"約 {odds}% 衝開・體力 {cfg.cultivate_stamina}" + (f"・已衝過 {tried} 次" if (tried := cultivation.fails_of(state, art_id)) else ""),  # 待 joy 潤
    }


def _look(content: Content, art: MartialArt) -> dict:
    """自創那一門撞到了什麼（create.marks_of）：look 是卡上那一行，tier 是品相凡佳珍神（撞到幾樣）；不是自創的都是空的。"""
    if not moves.is_own(content, art):
        return {"look": "", "tier": None}
    marks = create_mod.marks_of(art.slot_colors, art.move_fire, art.move_rare)
    return {"look": create_mod.look_text(marks), "tier": create_mod.tier_of(marks)}


def _fits(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> list[dict]:
    """這一份意境裝得進身上哪一門的哪一格（招式與絕學稿案第四輪：從意境這邊也裝得了）：{art, name, i}，i 從 0 起。"""
    member, out = state.player.member, []
    for art_id in (member.wugong_id, member.neigong_id):
        if art_id is None or arts_mod.slot_problem(state, content, world, art_id, insight_id) is not None:
            continue
        art = team.resolve_art(art_id, content, world)
        ins = insights.resolve(insight_id, content, world, state)
        slots = arts_mod.slots_of(state, content, art)
        out.append({"art": art_id, "name": art.name,
                    "i": arts_mod._open_slot(slots, arts_mod.colors_of(art, len(slots)), ins.attribute if ins else ""),
                    "stack": stack_hint(state, content, world, team.player_art(state, content, world, art_id), insight_id)})
    return out


def insight_effects(content: Content, fx, insight=None) -> list[dict]:
    """意境卡的功效，一個一句白話（traits 的 desc）：{name, layers, grand, special, desc}；秘方合出來的多一條特別功效。"""
    out = [{"name": e["name"], "layers": e["layers"], "grand": e["grand"], "special": False, "desc": e["desc"]}
           for e in insight_fx.effects(content, fx)]
    sp = arts_mod.special_of(content, insight.secret_special) if insight is not None and insight.secret_special else None
    if sp is not None:
        out.append({"name": sp.name, "layers": 0, "grand": False, "special": True, "desc": getattr(sp, "desc", "")})
    return out


def insight_rows(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """悟得的意境，照悟得的先後。"""
    rows = []
    blocked = prologue.melt_insight_problem(state, content)  # 序章裡不熔意境（跟 Game.melt_insight 的拒絕同一個判斷）；平常是 None
    for insight_id in state.player.insights:
        insight = insights.resolve(insight_id, content, world, state)
        if insight is not None:
            fx = insight_fx.record(state, content, world, insight_id, insight)
            strength = insight_fx.strength(state, insight_id)
            row = {
                "id": insight_id, "name": insight.name, "attribute": insight.attribute, "lean": insight.lean,
                # 武學重構：意境就是技能——那一招叫什麼、強度（●～●●●）、裝在哪一門上（None 沒裝）
                "skill": arts_mod.skill_name(content, insight, fx), "strength": strength,
                "mark": arts_mod.strength_mark(strength),
                "skill_desc": arts_mod.skill_desc(content, insight, strength, fx),
                "slotted": _slotted_name(state, content, world, insight_id),
                "depth": f"〔{arts_mod.skill_name(content, insight, fx)}〕",
                "rank": strength, "mood": None,  # 批量熔煉的篩選還讀這兩個鍵
                # 意境效果池：同一種可以有好幾份，每一份的品質與效果（大獎 grand）；piece 是第幾份（第一份 1）
                "quality": fx.quality, "fx": fx_traits(content, fx, insight), "grand": fx.grand is not None,
                # 意境卡（招式與絕學稿案第五輪）：品相凡佳珍神（底子 quality 不給玩家看）、每個功效一句白話、裝得進哪裡
                "look": insight_fx.look(fx), "effects": insight_effects(content, fx, insight),
                "fits": [] if arts_mod.where_slotted(state, insight_id) else _fits(state, content, world, insight_id),
                # 裝在身上哪一格最強、戰力會到多少（might.best_place；Joy 2026-10-21「合出來我根本看不懂這是不是好的」）；裝著的不算
                "best": None if arts_mod.where_slotted(state, insight_id) else might.best_place(state, content, world, insight_id),
                "piece": insight_fx.pieces(state, insight_fx.base_id(insight_id)).index(insight_id) + 1 if not insights.is_own(insight_id) else 1,
                "note": insight.note, "melt": content.config.melt_insight_xinde, "blocked": blocked,
                # 感悟悟來的私有意境（悟意境設計 0.2b）：在哪裡悟的、畫的那一筆（修練頁畫小縮圖）
                "own": insights.is_own(insight_id), "place": insight.place, "glyph": insight.glyph,
            }
            why = _idle_why(state, content, world, insight_id)  # 裝在一門上、秘方特效卻不是那一門發動的那一條
            if why:
                row["idle"] = why
                for t in (*row["fx"], *row["effects"]):
                    if t.get("special"):
                        t["idle"] = True
            if blocked is not None:  # 在序章裡（跟上面的拒絕同一個條件）：煉製頁這一步要放進爐子的意境發光（T7 走查 W-B）
                row["glow"] = prologue.insight_glow(state, content)
            rows.append(row)
    return rows


SCORE_NOTE = "秘方特效只算會發動的那一條"  # Joy 2026-10-28


def score_note(state: GameState, content: Content, world: WorldStateStore, art) -> str:
    """槽裡有不發動的秘方特效時，評分旁邊寫一句（arts.idle_specials）；沒有是空字串。"""
    return SCORE_NOTE if arts_mod.idle_specials(state, content, world, art) else ""


def _idle_why(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> str:
    """這一份裝著、它的秘方特效卻不發動時那一句（arts.idle_specials）；沒裝、沒秘方特效、會發動都是空字串。"""
    art_id = arts_mod.where_slotted(state, insight_id)
    art = team.player_art(state, content, world, art_id) if art_id else None
    if art is None:
        return ""
    idle = arts_mod.idle_specials(state, content, world, art)
    return next((why for i, held in enumerate(arts_mod.slots_of(state, content, art)) if held == insight_id and (why := idle.get(i))), "")


def _slotted_name(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> str | None:
    art_id = arts_mod.where_slotted(state, insight_id)
    if art_id is None:
        return None
    art = team.resolve_art(art_id, content, world)
    return art.name if art else art_id


def bag_text(state: GameState, content: Content) -> str:
    """背包：隨身帶著的材料（糧草、伏筆要用），階高的排前面。"""
    items = materials.bag_contents(state, content)
    pills, stamina_pills = state.player.legend_items, state.player.stamina_pills
    if not items and pills <= 0 and stamina_pills <= 0:
        return "**背包**　還沒有東西——打贏對手、沿路採集，或在奇遇裡拿到。"
    # 階名照內容裡有的階寫（正式內容四階：凡品、靈品、天品、神品；測試內容三階）
    tiers = sorted({m.tier for m in content.materials.values()} & set(materials.TIER_NAMES))
    names = "、".join(materials.TIER_NAMES[t] for t in tiers)
    lines = [f"**背包**　隨身帶著的材料，分{names}{forge_secrets.TIER_WORDS.get(len(tiers), len(tiers))}階。"] if items else ["**背包**　隨身帶著的東西。"]
    lines += [
        f"- {m.name} ×{n}　{materials.tier_label(m)}・屬{m.attribute}　{m.description}"
        for m, n in items
    ]
    if pills > 0:  # 傳奇道具破境丹（企劃者 2026-10-05）：不是材料，列在最後
        if items:  # 材料那行標題寫「材料，分三階」：丹接在底下會被當成材料，另起小標題（空行隔開，標題才不會併進上一項）
            lines += ["", "**傳奇道具**"]
        lines.append(f"- {content.config.legend_item_name} ×{pills}　{content.config.legend_item_note}")
    if stamina_pills > 0:  # 回體丹（內測贈送）：同樣不是材料；在狀態列體力條旁邊按「服丹」吃
        if items or pills > 0:
            lines += ["", "**丹藥**"]
        cfg = content.config
        how = (
            f"每顆回 {cfg.stamina_pill_restore} 點，在狀態列體力條旁邊按「服丹」。"
            if not cfg.beta_free_refill else
            # 測試期間一鍵補滿（Config.beta_free_refill）：那顆鈕改叫補滿、直接補到滿、不花丹；丹先留著（新寫，待 joy 潤）
            f"每顆回 {cfg.stamina_pill_restore} 點；測試期間狀態列體力條旁的「{cfg.beta_free_refill_label}」免費、不花丹，丹先留著。"
        )
        lines.append(f"- {cfg.stamina_pill_name} ×{stamina_pills}　{cfg.stamina_pill_note}{how}")
    return "\n".join(lines)


def level_bar(level: int) -> str:
    """熟練度的十格進度條，例如第 4 成是「●●●●○○○○○○」。

    手機上「第4成」三個字要讀過才知道練到哪，一條十格的條子一眼就看得出來還有多少可練——
    門下頁是玩家反覆回來按鍵的地方，這個資訊值得可以瞄一眼就懂。
    """
    level = max(0, min(MAX_LEVEL, level))
    return "●" * level + "○" * (MAX_LEVEL - level)


def _art_label(
    content: Content, world: WorldStateStore, skill_id: str | None, level: int, state: GameState | None = None,
) -> str:
    """一門功法的一行說明。給了 state 就是玩家自己那一份（品質照自己修練到的）；同伴、部下不給。"""
    if skill_id is None:
        return "（尚未習得）"
    art = team.player_art(state, content, world, skill_id) if state is not None else team.resolve_art(skill_id, content, world)
    if art is None:
        return skill_id
    attr = f"・屬{art.attribute}" if art.attribute else ""  # 兼容並蓄的沒有屬性
    return f"{art.name}（{art.quality}{attr}）第{level}成 {level_bar(level)}"


def member_card(state: GameState, content: Content, world: WorldStateStore, key: str) -> str:
    """一個人的角色卡：等級、氣血、內功、武學。部下（計畫 T5）只有武學：沒有等級、不扣氣血。"""
    if key.startswith(team.FOLLOWER_KEY):
        follower = dict(team.follower_rows(state, content)).get(key)
        if follower is None:
            return ""
        drill = team.drill_of(state, key)
        lines = [
            f"### {follower.name}",
            "部下：一直跟著你出戰，只算威力、不扣氣血；不能對話，也不能散功。武學跟著你的等級長進。",
            f"武學　{_art_label(content, world, follower.wugong, team.follower_level(state, content, follower, key))}",
            f"威力　{round(team.follower_power(state, content, world, follower, key))}",
        ]
        if drill.cheng or drill.arm:  # 傳功（Config.chuangong）：多練的成數、傳的臂力
            parts = ([f"武學多練 {drill.cheng} 成"] if drill.cheng else []) + (
                [f"{content.config.stat_names.get('str', '臂力')} +{drill.arm}"] if drill.arm else [])
            lines.append("傳功　" + "、".join(parts))
        return "\n".join(lines)
    if key == PLAYER:
        member = state.player.member
        name = state.player.name
    else:
        member = world.get_companion(key)
        name = content.characters[key].name
    own = state if key == PLAYER else None  # 玩家那一列顯示自己修練到的品質；同伴照全服登記的
    now, cap = team.member_neili(content, member, team.con_of(state, content, world, key), season=state.world)  # 本人與同伴各照自己的根骨
    lines = [
        f"### {name}",
        f"第 {member.level} 級　氣血 {now:.0f}/{cap:.0f}",
        f"內功　{_art_label(content, world, member.neigong_id, member.neigong_level, own)}",
        f"武學　{_art_label(content, world, member.wugong_id, member.wugong_level, own)}",
    ]
    if key == PLAYER and (weapon := weapons.card_line(state, content, world, team.player_art(state, content, world, member.wugong_id))):
        lines.append(weapon)  # 兵器（兵器設計 3.6）：空手或開關關著不寫
    if key == PLAYER and (worn_armor := armor.card_line(state, content, team.player_art(state, content, world, member.neigong_id))):
        lines.append(worn_armor)  # 防具（裝備四欄設計 2.5）：沒穿或開關關著不寫；對上的是內功（武器看武學、防具看內功）
    if key == PLAYER and (horse := mounts.card_line(state, content)):
        lines.append(horse)  # 坐騎（裝備四欄設計 2.5）：沒騎或開關關著不寫
    if key == PLAYER and (worn_treasure := treasures.card_line(state, content)):
        lines.append(worn_treasure)  # 寶物（裝備四欄設計 2.5）：沒帶或開關關著不寫
    # 本命戰法與小戰法（tactics.py）：身上練著的各一行；同伴練著自己的本命武學也會發動（連招），一樣寫
    levels = team.own_levels(state) if key == PLAYER else {}  # 自創的招前幾成還生
    lines += [t for t in (tactics_mod.line_of_id(content, s, world, levels.get(s)) for s in (member.wugong_id, member.neigong_id)) if t]
    if key != PLAYER and member.taught:  # 傳功（Config.chuangong）傳給他的屬性
        lines.append("傳功　" + "、".join(f"{content.config.stat_names.get(k, k)} +{n}" for k, n in member.taught.items() if n))
    if key == PLAYER and (boosts := boost_line(state, content, world)):  # 共鳴與功效只算本人，同伴的卡這一版不寫加成那一行
        lines.append(boosts)
    return "\n".join(lines)


def _art_cell(content: Content, world: WorldStateStore, kind: str, skill_id: str | None, level: int, state: GameState | None = None) -> dict:
    """門下卡上的一門：{"kind", "name", "quality", "attribute", "level"}；還沒學是 name 空字串（網頁寫「尚未習得」）。"""
    art = None
    if skill_id is not None:
        art = team.player_art(state, content, world, skill_id) if state is not None else team.resolve_art(skill_id, content, world)
    if art is None:
        return {"kind": kind, "name": "", "quality": "", "attribute": "", "level": 0}
    return {"kind": kind, "name": art.name, "quality": art.quality, "attribute": art.attribute or "", "level": level}


def roster_cards(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """俠客頁「門下」一人一張卡（Joy 2026-10-26「門下顯示優化」）：名冊的順序（本人、同伴、部下），每人
    {"key", "name", "role"（本人／出戰／在門下／部下）, "level"（部下 None）, "hp", "hp_max"（部下 None）, "arts": [內功, 武學]（部下只有武學）}。
    點了照舊是名冊那一下（person），細節在角色卡。"""
    out = []
    for _label, key in roster.roster_lines(state, content, world):
        if key.startswith(team.FOLLOWER_KEY):
            follower = dict(team.follower_rows(state, content)).get(key)
            if follower is None:
                continue
            out.append({"key": key, "name": follower.name, "role": "部下", "level": None, "hp": None, "hp_max": None,
                        "arts": [_art_cell(content, world, "武學", follower.wugong, team.follower_level(state, content, follower, key))]})
            continue
        if key == PLAYER:
            member, name, own, role = state.player.member, state.player.name, state, "本人"
        else:
            member, name, own = world.get_companion(key), content.characters[key].name, None
            role = "出戰" if key in state.player.team else "在門下"
        now, cap = team.member_neili(content, member, team.con_of(state, content, world, key), season=state.world)
        out.append({"key": key, "name": name, "role": role, "level": member.level, "hp": round(now), "hp_max": round(cap),
                    "arts": [_art_cell(content, world, "內功", member.neigong_id, member.neigong_level, own),
                             _art_cell(content, world, "武學", member.wugong_id, member.wugong_level, own)]})
    return out


def gear_rows(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """修練頁「裝備」那一塊（server.menxia_view 的 gear；裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎、寶物），
    每段是身上那件與裝備庫裡同一欄的（各欄模組的 rows）、段名、空著時那一句、底下那一句。
    格數四欄合算：used 是裝備庫裡全部的件數（關著的欄位的東西也佔格子），cap 是 Config.weapons.rack_cap。
    武器、防具兩段每一列多 divine：還等著你定名的神器原品是 {"pattern": 譜名, "unit": 量詞}（修練頁那一列底下畫定名表單；量詞照
    equipment.unit_for：防具一件、拳套一副、其他兵器一把，FB-197），其餘 None；裝備庫裡等著定名的原品排最前面（網頁預設只列前 8 件，不排前面表單會被藏起來）。
    bind：自己手上還沒以器配招的神器原品是 {"options": [{id, name, bond}…]}（配得上的絕學，可以是空的），其餘 None；
    綁了的、名器同氣的那一句接在 tactic 後面（smithing.bond_lines）。
    held_note：寄放著哪幾件（6.5），沒有是空字串。
    where（FB-138）：每一段「哪裡買得到、哪裡得來」那一句（equipment.smith_where、mounts.where、treasures.WHERE），讀內容的地點標籤；
    網頁在每一段身上與裝備庫都空著、也沒有寄放時畫精簡的一塊，每段一行寫 empty 加 where。內容裡沒有那種地點時是空字串。"""
    member = state.player.member
    slots = []
    if equipment.on(content, "weapon"):
        art = team.player_art(state, content, world, member.wugong_id)
        slots.append({"slot": "weapon", "label": equipment.SLOTS["weapon"].label, "empty": weapons.EMPTY, "note": weapons.RACK_NOTE,
                      "where": equipment.smith_where(state, content), **weapons.rows(state, content, world, art)})
    if equipment.on(content, "armor"):
        neigong = team.player_art(state, content, world, member.neigong_id)
        slots.append({"slot": "armor", "label": equipment.SLOTS["armor"].label, "empty": armor.EMPTY, "note": armor.RACK_NOTE,
                      "where": equipment.smith_where(state, content), **armor.rows(state, content, neigong)})
    if equipment.on(content, "mount"):
        slots.append({"slot": "mount", "label": equipment.SLOTS["mount"].label, "empty": mounts.EMPTY, "note": mounts.RACK_NOTE,
                      "where": mounts.where(state, content), **mounts.rows(state, content)})
    if equipment.on(content, "treasure") or (seal.on(content) and state.player.heirloom is not None):
        slots.append({"slot": "treasure", "label": equipment.SLOTS["treasure"].label, "empty": treasures.EMPTY,
                      "note": treasures.rack_note(state, content), "where": treasures.WHERE, **treasures.rows(state, content)})
    pending = forge_secrets.unnamed_originals(state, world)  # 還等著定名的神器原品（打造隱藏配方設計 5.2）：那一列底下畫定名表單
    owned = {item.id: item for item in forge_secrets.owned_gear(state.player)}
    options = smithing.bind_options(state, content, world)
    for block in slots:
        if block["slot"] in ("weapon", "armor"):
            for row in [block["worn"], *block["rack"]]:
                if row is not None and (item := owned.get(row["id"])) is not None:
                    # 鑄器配招（玩家武學追上本命定案 四）：綁了哪一門、名器同氣接在特技那幾行後面；還沒綁的神器原品多一組 bind
                    row["tactic"] = [*row.get("tactic", []), *smithing.bond_lines(state, content, world, item)]
                    row["bind"] = ({"options": [{"id": a, "name": n, "bond": d.split("：", 1)[-1]} for a, n, d in options]}
                                   if item.original and item.secret and not item.signature and not smithing.bound_alive(state, item) else None)
                if row is not None:
                    row.setdefault("bind", None)
                    # unit：表單那一句「打出這把／件／副神器」的量詞（FB-197），照 equipment.unit_for，網頁不另寫一份
                    row["divine"] = ({"pattern": pending[row["id"]], "unit": equipment.unit_for(block["slot"], row.get("kind", ""))}
                                     if row["id"] in pending else None)
            # 等著定名的原品排在裝備庫最前面（終審 I1）：手上已經有一把時原品放在最後一格，網頁只預設列前 8 件，表單會被「再列 N 件」藏起來；
            # 照有沒有 divine 排（穩定排序，其餘維持放進去的先後），定了名就回到原位
            block["rack"].sort(key=lambda row: row["divine"] is None)
    for block in slots:
        for row in block.get("rack", []):
            row["might"] = might.with_gear(state, content, world, row["id"])  # 換上後的戰力（招式與絕學稿案第四輪）
    return {"cap": content.config.weapons.rack_cap, "used": len(state.player.rack), "slots": slots, "held_note": treasures.held_note(state)}


def _pct(ratio: float) -> str:
    """加成寫成帶正負號的百分比，最多一位小數、整數就不寫「.0」：共鳴是名聲 ÷ 2 %，+0.5%、+7.5% 照實寫，不湊整。"""
    return f"{ratio:+.1%}".replace(".0%", "%")


def boost_line(state: GameState, content: Content, world: WorldStateStore) -> str:
    """本人卡上的一行：這時候威力吃到哪些加成，有才寫、都沒有就是空字串。

    臂力乘的是武學（外功）那一項、根骨乘的是內功那一項（設計 6.1），內功那一項還要再被縮小才進總威力，
    所以寫成「武學 +12%（臂力）」「內功 +6%（根骨）」，說清楚加成的是哪一門；那一欄沒有功法就不寫。
    其後是內外搭配與各門功法的正邪共鳴。"""
    member, stats = state.player.member, state.player.stats
    wugong = team.player_art(state, content, world, member.wugong_id)
    neigong = team.player_art(state, content, world, member.neigong_id)
    parts = []
    for art, word, key, stat_name in ((wugong, "武學", "str", "臂力"), (neigong, "內功", "con", "根骨")):
        bonus = team.stat_bonus(content, stats.get(key, team.BASE_STAT), state.world)
        if art is not None and bonus:
            parts.append(f"{word} {_pct(bonus)}（{stat_name}）")
    pair = team.pairing(content, wugong, neigong)
    if pair != 1:
        parts.append(f"內外搭配 {_pct(pair - 1)}")
    for art in (wugong, neigong):
        echo = team.resonance(state, content, art)
        if echo != 1:
            parts.append(_echo_part(state, content, art, echo))
    return "威力加成：" + "・".join(parts) if parts else ""


def _echo_part(state: GameState, content: Content, art: MartialArt, echo: float) -> str:
    """正邪共鳴那一段（名聲設計 5.1）：explain 開著時寫「你是一方豪俠：【守義劍】正派，吃善名 22，+11%」——功法的正邪跟你走的路
    對得上、而且有善惡稱號才寫稱號；關著照舊「【守義劍】共鳴 +11%」。"""
    if not renown.on(content, "explain"):
        return f"【{art.name}】共鳴 {_pct(echo - 1)}"
    key = "good" if art.lean == "正" else "evil"
    way = "俠" if art.lean == "正" else "寇"
    title = renown.virtue_title(state, content) if renown.path(state) == way else None
    book = content.config.stat_names.get(key, key)
    text = f"【{art.name}】{art.lean}派，吃{book} {state.player.stats.get(key, 0)}，{_pct(echo - 1)}"
    return f"你是{title}：{text}" if title else text


def detail(state: GameState, content: Content, world: WorldStateStore, kind: str) -> str:
    """kind 是「內功」或「武學」：目前這一門的詳細說明。"""
    member = state.player.member
    skill_id = member.neigong_id if kind == "內功" else member.wugong_id
    level = member.neigong_level if kind == "內功" else member.wugong_level
    if skill_id is None:
        return f"你還沒有{kind}。"
    art = team.player_art(state, content, world, skill_id)
    if art is None:
        return f"（找不到武學資料：{skill_id}）"
    return art_card(
        art, level, parent_names=parent_names(art, content, world), trait_line=traits.card_line(content, art),
        gen_word=gen_word(art, content, world),
    )


def gen_word(art: MartialArt, content: Content, world: WorldStateStore) -> str:
    """武學重構之後沒有境界了：一律空字串（功法卡那一行不畫）。留著讓 art_card 的呼叫端不改。"""
    return ""


def parent_names(art: MartialArt, content: Content, world: WorldStateStore) -> list[str]:
    """武學＋武學的兩門來源的名字（art.parents，設計 12.3）：功法卡寫「由【甲】與【乙】衍生」要的。其他功法是空的；
    找不到資料的來源不寫（art_card 只認剛好兩個名字）。"""
    parents = (team.resolve_art(parent_id, content, world) for parent_id in art.parents)
    return [parent.name for parent in parents if parent is not None]


def power_line(art: MartialArt, level: int) -> str:
    """功法卡的威力那一行（W1：威力只寫這一行，不再另起一行寫第一成、第十成）：目前這一成與它的威力，括號裡是下一成與第十成的威力。
    第九成的下一成就是第十成，只寫一個數字；已經第十成沒有下一成。數字都是 martial_arts.power_at 算的，這裡只排版。"""
    head = f"第{level}成 {level_bar(level)}，威力 {power_at(art, level):.1f}"
    if level >= MAX_LEVEL:
        return head + POWER_MAXED
    top = f"{power_at(art, MAX_LEVEL):.1f}"
    if level == MAX_LEVEL - 1:
        return head + POWER_NEXT_IS_TOP.format(top=top)
    return head + POWER_NEXT.format(next=f"{power_at(art, level + 1):.1f}", top=top)


# 威力那一行括號裡的句子（待 joy 潤）
POWER_NEXT = "（下一成 {next}・第十成 {top}）"
POWER_NEXT_IS_TOP = "（下一成即第十成 {top}）"
POWER_MAXED = "（已達第十成）"


def art_card(
    art: MartialArt, level: int, insight_name: str | None = None, parent_names: list[str] | None = None,
    trait_line: str = "", compare_line: str = "", gen_word: str = "",
) -> str:
    """一門功法的功法卡（無限煉製設計 §8；FB-006）：名字・品質・屬性（有傾向再加正邪）、目前熟練度與威力
    （連同下一成與第十成的威力，W1 併成一行）、來源與融的意境，最後是模型寫的那句說明。

    來源（FB-017、武學與成長設計 3.4）：合成（origin == "fused"）寫「合成（某某 首創）」，某某是第一個合出這個配方的人
    寫給別人看的名號（shown_creator：名號；這一版之前匿名行走的人記下的是「某位少俠」，照舊）；
    基礎武學（"basic"）寫「基礎武學」；舊資料的煉製（"crafted"）寫「煉製（某某 首創）」、取名自創（"created"）寫
    「自創（某某 所創）」；其他是本命武學。insight_name 是這門武學融的意境的名字（沒融過就不給、不寫）。
    parent_names 是武學＋武學的兩門來源的名字（設計 12.3），有兩個才寫「由【甲】與【乙】衍生」。
    trait_line 是功效那一行（traits.card_line，設計 13.6：這一門自己的功效，數字照這一份的品質算），有字時接在來源那一行之後；
    三處呼叫端（art_rows、detail、Game.art_detail）都要給，不給（內容沒有功效、舊的呼叫）就沒有這一行。
    compare_line 是跟身上同一種那門比的一句（W6，team.compare_with_worn）：只有功法庫裡的功法才給，身上那門自己的卡不比；
    有字時接在功效那一行之後、說明句之前。
    說明句只有真的有字時才有那一行：退路字表取名的功法、自創與本命武學都沒有說明，
    這時整行省略——不留空行、不出現 None（QA 寫進 FB-006 的驗收）。
    """
    creator = shown_creator(art)  # 寫給別人看的名號：名號（首創一律具名，傳聞分層第七節）；這一版之前匿名記下的「某位少俠」照舊
    if art.preset:  # 師門配方（新手引導）：沒有首創者
        source = "師門傳下來的功夫"
    elif art.origin == "fused":
        source = "合成" + (f"（{creator} 首創）" if creator else "")
    elif art.origin == "basic":
        source = "基礎武學"
    elif art.origin == "crafted":
        source = "煉製" + (f"（{creator} 首創）" if creator else "")
    elif art.origin == "created":
        source = "自創" + (f"（{creator} 所創）" if creator else "")
    else:
        source = "本命武學"
    lines = [
        f"【{art.name}】{art.quality}" + (f"・屬{art.attribute}" if art.attribute else "")  # 兼容並蓄的沒有屬性，不留「・屬」
        + (f"・{art.lean}派" if art.lean != "無" else ""),
        power_line(art, level),
        f"來源：{source}" + (f"・{gen_word}" if gen_word else "")
        + (f"　由【{parent_names[0]}】與【{parent_names[1]}】衍生" if parent_names and len(parent_names) == 2 else "")
        + (f"　意境：「{insight_name}」" if insight_name else ""),
    ]
    if trait_line:
        lines.append(trait_line)
    if compare_line:
        lines.append(compare_line)
    note = art.note.strip()
    if note:
        lines.append(note)
    return "\n".join(lines)
