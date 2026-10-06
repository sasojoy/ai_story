"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import cultivation, fusion, insights, materials, prologue, team, traits
# 不 import 整個 library 模組：這個檔案自己有一個叫 library() 的函式
from .library import cap_of, held_count, level_of, melt_problem, melt_value, owned_arts
from .martial_arts import MAX_LEVEL, MartialArt, next_quality, power_at, shown_creator
from .models import Content
from .state import PLAYER, GameState
from .world_state import WorldStateStore


# 五屬性各管什麼（武學與成長設計 6.1、6.3）：狀態列＋鈕底下那一行（計畫二最終審查 M2）。點數配了收不回來（6.2），身法、悟性、
# 博聞又看不到立即的變化，所以按之前要讀得到。名字照 Config.stat_names（見 stat_uses），這裡只寫用途；只寫玩家本人身上的事
STAT_USES = {
    "str": "武學威力",
    "agi": "打完一場少損氣血・落敗有機會閃成平手",
    "con": "內功威力・氣血上限・少受內傷",
    "wis": "修練機率・探索悟得意境・閉關心得",
    "lore": "武學與意境的持有上限",
}
# 事件檢定、隨口應對讀得到五項（設計 6.1、6.3），但正式內容還沒有任何事件檢定博聞，所以先寫「前四項」（PM 2026-10-05）。
# joy 加了第一個檢定（或隨口應對看）博聞的事件之後，改回「事件的檢定也看這五項。」——
# tests/test_engine.py 的 test_the_stat_note_says_four_until_an_event_checks_lore 到時候會失敗提醒
STAT_CHECK_NOTE = "事件的檢定看前四項。"


def stat_uses(content: Content) -> list[tuple[str, str]]:
    """五屬性的（名字, 用途），順序同 team.COMBAT_STATS——也就是狀態列 attrs、＋鈕的順序。"""
    names = content.config.stat_names
    return [(names.get(key, key), STAT_USES[key]) for key in team.COMBAT_STATS]


def rules_line(content: Content) -> str:
    return "身上一門內功、一門武學：花心得練成，用意境修練衝品質；武學也能在「煉製」融意境衍生新武學，或兩門武學合成一門新的。"


def practice_hint(state: GameState, content: Content) -> str | None:
    """主畫面的提示：心得擱到 `xinde_hint_threshold` 以上、而且確實有事可做時才回傳一句話。

    心得的去處（武學與成長設計第四節）：練成（身上這一門還沒第十成、付得起下一成）與合成（手上有意境、
    持有沒滿、付得起一次，見 fusion.can_forge）。兩樣都做不了就閉嘴，免得變成嘮叨。休季時什麼都不能做，也不提示（FB-047）。
    去處照底部分頁的名字寫「修練」「煉製」（舊的門下頁已經拆成這兩頁，FB-047）。
    """
    xinde = state.player.stats.get("xinde", 0)
    if xinde < content.config.xinde_hint_threshold or state.world.ended:
        return None
    todo = [kind for kind in ("內功", "武學") if team.can_practise(state, content, kind)]
    parts = []
    if todo:
        parts.append(f"去「修練」練成{'、'.join(todo)}")
    if fusion.can_forge(state, content):  # 手上有意境、持有沒滿、付得起一次合成或合併才提；光有意境不算
        parts.append("去「煉製」拿意境合成新武學")
    if not parts:
        return None
    return f"💡 你已攢下 {xinde} 點心得。{'，或'.join(parts)}。"


def _known_recipe(state: GameState, content: Content, world: WorldStateStore, key: str) -> str:
    """爐子上那一組武學的配方有沒有人合過（武學與成長設計 13.6）：已知的寫「會合出【X】」與它的功效，沒人合過的寫「沒人合過」，
    不預告會長出什麼。合出來的那一門你已經有了就不寫（下面的 ⚠ 本來就會說「你已經有了」）。只在放進爐裡的都是你的東西時才會
    呼叫（forge_line 先擋下了不是你的），所以不會拿它探別人合出了什麼。"""
    known = world.lookup_recipe(key)
    if known is None:
        return "\n沒人合過。"
    if known.id in owned_arts(state):
        return ""
    return f"\n會合出【{known.name}】。{traits.card_line(content, known)}"


def forge_line(
    state: GameState, content: Content, world: WorldStateStore, art_id: str | None, insight_ids: list[str],
    other_art: str | None = None,
) -> str:
    """煉製頁的說明：放了什麼、會做哪一種、花多少心得，或者為什麼還不能開爐。other_art 有、insight_ids 空的是武學＋武學。"""
    refusal = prologue.fuse_problem(state, content, art_id, insight_ids, other_art)  # 序章裡只准照劇本合成（跟 Game.forge 同一個判斷）
    if refusal is not None:
        return f"⚠ {refusal}"
    cfg, xinde = content.config, state.player.stats.get("xinde", 0)
    count = f"武學與意境 {held_count(state)}/{cap_of(state, content)}"
    owned, held = owned_arts(state), state.player.insights
    # 預覽不能拿來探：不是你的武學、還沒悟到的意境，先於一切（查名字、屬性、種類）就回開爐時會說的那句拒絕，
    # 不然隨便塞一個 id（龍頭人物的本命武學、別人首創的）就看得到它叫什麼、屬什麼。
    if art_id and other_art and not insight_ids:
        if art_id not in owned or other_art not in owned:
            return f"⚠ {fusion.blend_problem(state, content, world, art_id, other_art)}"
        a, b = team.player_art(state, content, world, art_id), team.player_art(state, content, world, other_art)
        if a is None or b is None:
            return "（選了不存在的東西。）"
        shape = fusion.blend_shape(a, b, fusion.recipe_seed(world, fusion.blend_key(art_id, other_art))[1])
        head = (
            f"**合成**　【{a.name}】＋【{b.name}】→ 一門新{shape.kind}（屬{shape.attribute}，從下品起修），"
            f"花 {cfg.fuse_xinde} 點心得、{cfg.fuse_stamina} 點體力（你有 {xinde} 點心得）。"
        )
        head += _known_recipe(state, content, world, fusion.blend_key(art_id, other_art))
        problem = fusion.blend_problem(state, content, world, art_id, other_art)
    elif art_id and not other_art and len(insight_ids) == 1:
        if art_id not in owned or insight_ids[0] not in held:
            return f"⚠ {fusion.fuse_problem(state, content, world, art_id, insight_ids[0])}"
        base = team.player_art(state, content, world, art_id)
        insight = insights.resolve(insight_ids[0], content, world)
        if base is None or insight is None:
            return "（選了不存在的東西。）"
        head = (
            f"**合成**　【{base.name}】＋「{insight.name}」→ 一門新{base.kind}"
            f"（屬{insight.attribute}，從下品起修），"
            f"花 {cfg.fuse_xinde} 點心得、{cfg.fuse_stamina} 點體力（你有 {xinde} 點心得）。"
        )
        head += _known_recipe(state, content, world, fusion.fuse_key(art_id, insight_ids[0]))
        problem = fusion.fuse_problem(state, content, world, art_id, insight_ids[0])
    elif not art_id and not other_art and len(insight_ids) == 2:
        if any(i not in held for i in insight_ids):
            return f"⚠ {fusion.merge_problem(state, content, world, *insight_ids)}"
        a, b = (insights.resolve(i, content, world) for i in insight_ids)
        if a is None or b is None:
            return "（選了不存在的東西。）"
        head = (  # 三種合成都花體力（設計 12.1）：不夠的話下面的 ⚠ 會說
            f"**合併**　「{a.name}」＋「{b.name}」→ 一個新的意境，"
            f"花 {cfg.merge_xinde} 點心得、{cfg.merge_stamina} 點體力（你有 {xinde} 點心得）。"
        )
        problem = fusion.merge_problem(state, content, world, *insight_ids)
    else:
        return (
            "**煉製**　放一門武學和一個意境，衍生出一門新武學（底留著）；放兩門武學，合出一門新的；"
            f"或放兩個意境，合出新的意境。{count}。"
        )
    return head if problem is None else f"{head}\n⚠ {problem}"


def art_rows(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """修練與煉製兩頁的武學清單：身上的在前，再來功法庫。每門一列：品質（自己那一份）、第幾成、融的意境、
    修練與熔煉按不按得下去與為什麼。只讀狀態，不改東西。"""
    p, member = state.player, state.player.member
    rows = []
    for art_id in owned_arts(state):
        art = team.player_art(state, content, world, art_id)  # 自己那一份：品質照自己修練到的
        if art is None:
            continue
        level = level_of(state, art_id)
        insight = insights.resolve(art.insight, content, world) if art.insight else None
        insight_name = insight.name if insight else None
        problem = prologue.cultivate_problem(state, content) or cultivation.cultivate_problem(state, content, world, art_id)
        legend = None
        if problem is None:
            target = next_quality(art.quality)
            failures = p.art_mastery.get(art_id, 0)
            note = f"{cultivation.odds_for(state, content, target, failures)}% 晉為{target}・體力 {content.config.cultivate_stamina}"
            legend = _legend_choice(state, content, target, failures)
        else:
            note = problem
        stuck = melt_problem(state, art_id, art.name, only=prologue.melt_only(state, content))  # 跟 library.melt_art 同一個判斷
        rows.append({
            "id": art_id, "name": art.name, "kind": art.kind, "quality": art.quality, "attribute": art.attribute,
            "level": level, "worn": art_id in (member.neigong_id, member.wugong_id), "insight": insight_name,
            "card": art_card(art, level, insight_name, parent_names(art, content, world), traits.card_line(content, art)),
            "cultivate": {"ok": problem is None, "note": note, "legend": legend},
            "melt": {
                "ok": stuck is None,
                "note": stuck if stuck is not None else f"退回心得 {melt_value(state, content, world, art_id)}",
            },
        })
    return rows


def _legend_choice(state: GameState, content: Content, target: str, failures: int) -> dict | None:
    """修練頁上「服下破境丹」那一格（預設不勾）要的資料：下一步是絕學、手上有丹才有，否則 None。
    note 是勾了之後機率欄換成的那一句；加成機率照 cultivation.boost_for 算，跟實際擲的一致。"""
    boost = cultivation.boost_for(state, content, target, use_legend=True)
    if not boost:
        return None
    cfg, count = content.config, state.player.legend_items
    return {
        "count": count,
        "bonus": boost,
        "label": f"服下{cfg.legend_item_name}（+{boost}%，剩 {count} 枚）",
        "note": f"{cultivation.odds_for(state, content, target, failures, boost)}% 晉為{target}"
                f"（含{cfg.legend_item_name} +{boost}%）・體力 {cfg.cultivate_stamina}",
    }


def insight_rows(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """悟得的意境，照悟得的先後。"""
    rows = []
    blocked = prologue.melt_insight_problem(state, content)  # 序章裡不熔意境（跟 Game.melt_insight 的拒絕同一個判斷）；平常是 None
    for insight_id in state.player.insights:
        insight = insights.resolve(insight_id, content, world)
        if insight is not None:
            rows.append({
                "id": insight_id, "name": insight.name, "attribute": insight.attribute, "lean": insight.lean,
                "note": insight.note, "melt": content.config.melt_insight_xinde, "blocked": blocked,
            })
    return rows


def bag_text(state: GameState, content: Content) -> str:
    """背包：隨身帶著的材料（糧草、伏筆要用），階高的排前面。"""
    items = materials.bag_contents(state, content)
    pills = state.player.legend_items
    if not items and pills <= 0:
        return "**背包**　還沒有東西——打贏對手、沿路採集，或在奇遇裡拿到。"
    lines = ["**背包**　隨身帶著的材料，分凡品、靈品、天品三階。"] if items else ["**背包**　隨身帶著的東西。"]
    lines += [
        f"- {m.name} ×{n}　{materials.tier_label(m)}・屬{m.attribute}　{m.description}"
        for m, n in items
    ]
    if pills > 0:  # 傳奇道具破境丹（企劃者 2026-10-05）：不是材料，列在最後
        if items:  # 材料那行標題寫「材料，分三階」：丹接在底下會被當成材料，另起小標題（空行隔開，標題才不會併進上一項）
            lines += ["", "**傳奇道具**"]
        lines.append(f"- {content.config.legend_item_name} ×{pills}　{content.config.legend_item_note}")
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
    return f"{art.name}（{art.quality}・屬{art.attribute}）第{level}成 {level_bar(level)}"


def member_card(state: GameState, content: Content, world: WorldStateStore, key: str) -> str:
    """一個人的角色卡：等級、氣血、內功、武學。部下（計畫 T5）只有武學：沒有等級、不扣氣血。"""
    if key.startswith(team.FOLLOWER_KEY):
        follower = dict(team.follower_rows(state, content)).get(key)
        if follower is None:
            return ""
        return "\n".join([
            f"### {follower.name}",
            "部下：一直跟著你出戰，只算威力、不扣氣血；不能對話，也不能散功。",
            f"武學　{_art_label(content, world, follower.wugong, follower.wugong_level)}",
        ])
    if key == PLAYER:
        member = state.player.member
        name = state.player.name
    else:
        member = world.get_companion(key)
        name = content.characters[key].name
    own = state if key == PLAYER else None  # 玩家那一列顯示自己修練到的品質；同伴照全服登記的
    now, cap = team.member_neili(content, member, team.con_of(state, content, world, key))  # 本人與同伴各照自己的根骨
    lines = [
        f"### {name}",
        f"第 {member.level} 級　氣血 {now:.0f}/{cap:.0f}",
        f"內功　{_art_label(content, world, member.neigong_id, member.neigong_level, own)}",
        f"武學　{_art_label(content, world, member.wugong_id, member.wugong_level, own)}",
    ]
    if key == PLAYER and (boosts := boost_line(state, content, world)):  # 共鳴與功效只算本人，同伴的卡這一版不寫加成那一行
        lines.append(boosts)
    return "\n".join(lines)


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
        bonus = team.stat_bonus(content, stats.get(key, team.BASE_STAT))
        if art is not None and bonus:
            parts.append(f"{word} {_pct(bonus)}（{stat_name}）")
    pair = team.pairing(content, wugong, neigong)
    if pair != 1:
        parts.append(f"內外搭配 {_pct(pair - 1)}")
    for art in (wugong, neigong):
        echo = team.resonance(state, content, art)
        if echo != 1:
            parts.append(f"【{art.name}】共鳴 {_pct(echo - 1)}")
    return "威力加成：" + "・".join(parts) if parts else ""


def library(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    """武學庫：（顯示文字, kind），kind 是「內功」或「武學」（練功時鍛鍊哪一欄）。"""
    member = state.player.member
    items = []
    for kind, slot_id, level in (
        ("內功", member.neigong_id, member.neigong_level),
        ("武學", member.wugong_id, member.wugong_level),
    ):
        if slot_id:
            items.append((f"{kind}　{_art_label(content, world, slot_id, level, state)}", kind))
    return items


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
    return art_card(art, level, parent_names=parent_names(art, content, world), trait_line=traits.card_line(content, art))


def parent_names(art: MartialArt, content: Content, world: WorldStateStore) -> list[str]:
    """武學＋武學的兩門來源的名字（art.parents，設計 12.3）：功法卡寫「由【甲】與【乙】衍生」要的。其他功法是空的；
    找不到資料的來源不寫（art_card 只認剛好兩個名字）。"""
    parents = (team.resolve_art(parent_id, content, world) for parent_id in art.parents)
    return [parent.name for parent in parents if parent is not None]


def art_card(
    art: MartialArt, level: int, insight_name: str | None = None, parent_names: list[str] | None = None,
    trait_line: str = "",
) -> str:
    """一門功法的功法卡（無限煉製設計 §8；FB-006）：名字・品質・屬性（有傾向再加正邪）、目前熟練度與威力、
    第一成／第十成的威力、來源與融的意境，最後是模型寫的那句說明。

    來源（FB-017、武學與成長設計 3.4）：合成（origin == "fused"）寫「合成（某某 首創）」，某某是第一個合出這個配方的人
    寫給別人看的名號（shown_creator：名號；這一版之前匿名行走的人記下的是「某位少俠」，照舊）；
    基礎武學（"basic"）寫「基礎武學」；舊資料的煉製（"crafted"）寫「煉製（某某 首創）」、取名自創（"created"）寫
    「自創（某某 所創）」；其他是本命武學。insight_name 是這門武學融的意境的名字（沒融過就不給、不寫）。
    parent_names 是武學＋武學的兩門來源的名字（設計 12.3），有兩個才寫「由【甲】與【乙】衍生」。
    trait_line 是功效那一行（traits.card_line，設計 13.6：這一門自己的功效，數字照這一份的品質算），有字時接在來源那一行之後；
    三處呼叫端（art_rows、detail、Game.art_detail）都要給，不給（內容沒有功效、舊的呼叫）就沒有這一行。
    說明句只有真的有字時才有那一行：退路字表取名的功法、自創與本命武學都沒有說明，
    這時整行省略——不留空行、不出現 None（QA 寫進 FB-006 的驗收）。
    """
    nxt = "已達第十成" if level >= MAX_LEVEL else f"{power_at(art, level + 1):.1f}"
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
        f"【{art.name}】{art.quality}・屬{art.attribute}" + (f"・{art.lean}派" if art.lean != "無" else ""),
        f"第{level}成 {level_bar(level)}，威力 {power_at(art, level):.1f}（下一成：{nxt}）",
        f"第一成 {power_at(art, 1):.1f}　第十成 {power_at(art, MAX_LEVEL):.1f}",
        f"來源：{source}"
        + (f"　由【{parent_names[0]}】與【{parent_names[1]}】衍生" if parent_names and len(parent_names) == 2 else "")
        + (f"　意境：「{insight_name}」" if insight_name else ""),
    ]
    if trait_line:
        lines.append(trait_line)
    note = art.note.strip()
    if note:
        lines.append(note)
    return "\n".join(lines)
