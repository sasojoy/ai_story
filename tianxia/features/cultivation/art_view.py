"""修練頁（門下）的說明文字與功法列（第二輪第 88 批從 tianxia/skillview.py 切出來，修練包獨用的那一半；原本的說明：「門下」頁的說明文字，
sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，
沒有多個自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。別包也要讀的卡片在共用層 tianxia/art_cards.py。

另外要跑的：靠舊名殼 skillview 的測試都在 `scripts/test_for.py tianxia/skillview.py` 挑的那一份。
"""
from __future__ import annotations

from tianxia import armor, arts as arts_mod, atlas, encounter, forge_secrets, insight_fx, insights, martial_arts, materials, might, mounts, moves, pose, prologue, renown, roster, tactics as tactics_mod, team, traits, treasures, weapons
from tianxia.art_cards import (
    _high_word, _look, _stack_cells, _stack_scope, _stat_numbers, art_card, fifth_ring, fx_traits, gen_word, level_bar, parent_names, score_note, slot_rows, tactic_line,
)
from tianxia.core.services import item_for  # 「去萬寶閣」停在哪一件（核心的錢包服務，3.10）
from tianxia.library import TOWN_TAG, level_of, melt_confirm, melt_note, melt_problem, melt_value, owned_arts
from tianxia.martial_arts import QUALITIES, MartialArt, power_at
from tianxia.models import Content
from tianxia.state import PLAYER, GameState
from tianxia.world_state import WorldStateStore

from . import cultivation


STAT_STEP = {  # 多配一點多了什麼（Game.allocate_stat 那一句冒號後面）
    "str": "武學威力 {bonus}",
    "agi": "閃避 {dodge_up}、少損氣血 {bonus}",
    "con": "內功威力 {bonus}、氣血上限 {hp}",
    "wis": "修練與衝關 {bonus}、感悟 {sense}",
    "lore": "持有 {slots} 格",
}


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
            "pose": pose.icon_pose(content, art, weapon),  # 功法卡上的小火柴人：自創的照自己擺的式，其餘照兵器挑預設架式
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
TOPPED = "{name}已到頂，再裝不加"


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
                "note": insight_note(content, insight, fx), "melt": content.config.melt_insight_xinde, "blocked": blocked,
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


def insight_note(content: Content, insight, fx) -> str:
    """意境的說明。頓悟悟成的神品意境，修好之前存檔記的是沒換數字的模板（{stun_pct}），照它的模板重寫一次。"""
    if "{" in (insight.note or "") and fx is not None:
        god = insight_fx.grand(content, fx.grand)
        if god is not None:
            return god.desc
    return insight.note


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
