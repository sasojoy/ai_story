"""武學與裝備的唯讀卡片（第二輪第 88 批從 tianxia/skillview.py 切出來）：狀態列（stat_uses、practice_hint）、療傷鈕（heal_note、heal_button）、
榜單（shown_art、shown_gear）、功法卡（art_card）、裝備那一塊（gear_rows）與修練頁兩邊都讀的小零件。只讀狀態與內容、只產生文字，不改任何東西。

共用規則層（core/registry.py 的 SHARED）：engine、leaderboard 與修練、煉製、裝備、鐵匠鋪四包讀；不 import 任何一包，連函式裡都不行。

另外要跑的：讀這一檔的測試（`git grep -l "import art_cards" -- tests tianxia/features` 列的那幾個；test_for 改這一檔照共用層的規矩只挑邊界測試加煙霧）。
"""
from __future__ import annotations

from . import armor, arts as arts_mod, clinic, equipment, forge_secrets, fusion, insight_fx, insights, might, mounts, moves, pose, renown, tactics as tactics_mod, team, traits, treasures, weapons
from .core import seal_base, smith_base
from .library import level_of
from .martial_arts import MAX_LEVEL, MartialArt, power_at, shown_creator
from .models import Content
from .state import GameState
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
    from . import attrset  # noqa: PLC0415

    if state is not None and attrset.on(content, state.world):  # 五項屬性的季：名字與一句說明照 content/attributes_v2.json
        return [(a.name, a.blurb) for a in content.attributes_v2]
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


def fx_traits(content: Content, fx, insight=None) -> list[dict]:
    """卡上的效果籤：一般功效寫層數，大獎 layers 0、grand true；給了意境、它是秘方合出來的，再加那一條特別功效（special true）。"""
    out = [{"name": e["name"], "layers": e["layers"], "grand": e["grand"]} for e in insight_fx.effects(content, fx)]
    sp = arts_mod.special_of(content, insight.secret_special) if insight is not None and insight.secret_special else None
    if sp is not None:
        out.append({"name": sp.name, "layers": 0, "grand": False, "special": True})
    return out


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
        "pose": pose.icon_pose(content, art, weapon), "weapon": weapon,
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
        "temper_max": equipment.temper_cap(item, content), "wear_note": equipment.wear_note(item, content),  # 鐵匠鋪與合成流程 3.6
        "edge": item.edge if live else None, "wear_word": equipment.WEAR_WORDS.get(slot, ""),
        "tactic": tactics_mod.item_lines(content, item),
    }
HIGH_MORE = "多一半"  # 同一個真意第二份：發動的機會多一半
HIGH_LONGER = "多撐一回合"  # 本來就每次發動的真意（鎮岳、金身）第二份


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


def _look(content: Content, art: MartialArt) -> dict:
    """自創那一門撞到了什麼（moves.marks_of）：look 是卡上那一行，tier 是品相凡佳珍神（撞到幾樣）；不是自創的都是空的。"""
    if not moves.is_own(content, art):
        return {"look": "", "tier": None}
    marks = moves.marks_of(art.slot_colors, art.move_fire, art.move_rare)
    return {"look": moves.look_text(marks), "tier": moves.tier_of(marks)}


SCORE_NOTE = "秘方特效只算會發動的那一條"  # Joy 2026-10-28


def score_note(state: GameState, content: Content, world: WorldStateStore, art) -> str:
    """槽裡有不發動的秘方特效時，評分旁邊寫一句（arts.idle_specials）；沒有是空字串。"""
    return SCORE_NOTE if arts_mod.idle_specials(state, content, world, art) else ""


def level_bar(level: int) -> str:
    """熟練度的十格進度條，例如第 4 成是「●●●●○○○○○○」。

    手機上「第4成」三個字要讀過才知道練到哪，一條十格的條子一眼就看得出來還有多少可練——
    門下頁是玩家反覆回來按鍵的地方，這個資訊值得可以瞄一眼就懂。
    """
    level = max(0, min(MAX_LEVEL, level))
    return "●" * level + "○" * (MAX_LEVEL - level)


def gear_rows(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """修練頁「裝備」那一塊（server.menxia_view 的 gear；裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎、寶物），
    每段是身上那件與裝備庫裡同一欄的（各欄模組的 rows）、段名、空著時那一句、底下那一句。
    格數四欄合算：used 是裝備庫裡全部的件數（關著的欄位的東西也佔格子），cap 是 Config.weapons.rack_cap。
    武器、防具兩段每一列多 divine：還等著你定名的神器原品是 {"pattern": 譜名, "unit": 量詞}（修練頁那一列底下畫定名表單；量詞照
    equipment.unit_for：防具一件、拳套一副、其他兵器一把，FB-197），其餘 None；裝備庫裡等著定名的原品排最前面（網頁預設只列前 8 件，不排前面表單會被藏起來）。
    bind：自己手上還沒以器配招的神器原品是 {"options": [{id, name, bond}…]}（配得上的絕學，可以是空的），其餘 None；
    綁了的、名器同氣的那一句接在 tactic 後面（smith_base.bond_lines）。
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
    if equipment.on(content, "treasure") or (seal_base.on(content) and state.player.heirloom is not None):
        slots.append({"slot": "treasure", "label": equipment.SLOTS["treasure"].label, "empty": treasures.EMPTY,
                      "note": treasures.rack_note(state, content), "where": treasures.WHERE, **treasures.rows(state, content)})
    pending = forge_secrets.unnamed_originals(state, world)  # 還等著定名的神器原品（打造隱藏配方設計 5.2）：那一列底下畫定名表單
    owned = {item.id: item for item in forge_secrets.owned_gear(state.player)}
    options = smith_base.bind_options(state, content, world)
    for block in slots:
        if block["slot"] in ("weapon", "armor"):
            for row in [block["worn"], *block["rack"]]:
                if row is not None and (item := owned.get(row["id"])) is not None:
                    # 鑄器配招（玩家武學追上本命定案 四）：綁了哪一門、名器同氣接在特技那幾行後面；還沒綁的神器原品多一組 bind
                    row["tactic"] = [*row.get("tactic", []), *smith_base.bond_lines(state, content, world, item)]
                    row["bind"] = ({"options": [{"id": a, "name": n, "bond": d.split("：", 1)[-1]} for a, n, d in options]}
                                   if item.original and item.secret and not item.signature and not smith_base.bound_alive(state, item) else None)
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
