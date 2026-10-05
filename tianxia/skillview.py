"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import craft, materials, team
from .martial_arts import MAX_LEVEL, MartialArt, power_at
from .models import Content
from .state import PLAYER, GameState
from .world_state import WorldStateStore


def rules_line(content: Content) -> str:
    return "每人最多學一門內功、一門武學：自創功法（取名決定屬性/威力/成長性）或鍛鍊已知武學。"


def practice_hint(state: GameState, content: Content) -> str | None:
    """主畫面的練功提示：心得擱到 `xinde_hint_threshold` 以上、而且確實有事可做時才回傳一句話。

    心得的去處有兩個：鍛鍊（免費，已決定維持免費）與**煉製**（真的要花心得，見 craft.py）。
    實測隨機玩完一整季的心得收入只有 20~96，所以門檻故意訂得低；真正需要這句話的是從來沒
    進過門下、心得一路擱著而武學還停在第一成的玩家。兩門都練滿、又煉不動時就不再提示，
    免得變成嘮叨；文字也只列出真正做得到的那幾件事。休季時什麼都不能做，也不提示（FB-047）。
    去處照底部分頁的名字寫「修練」「煉製」（舊的門下頁已經拆成這兩頁，FB-047）。
    """
    xinde = state.player.stats.get("xinde", 0)
    if xinde < content.config.xinde_hint_threshold or state.world.ended:
        return None
    member = state.player.member
    todo = [
        kind
        for kind, slot, level_slot in (
            ("內功", "neigong_id", "neigong_level"), ("武學", "wugong_id", "wugong_level"),
        )
        if getattr(member, slot) is None or getattr(member, level_slot) < MAX_LEVEL
    ]
    parts = []
    if todo:
        parts.append(f"去「修練」鍛鍊{'、'.join(todo)}（不花一分一毫）")
    if _can_afford_a_craft(state, content, xinde):
        parts.append("到「煉製」拿素材煉製新功法")
    if not parts:
        return None
    return f"💡 你已攢下 {xinde} 點心得。{'，或'.join(parts)}。"


def _can_afford_a_craft(state: GameState, content: Content, xinde: int) -> bool:
    """手上的素材湊得出一爐、而且心得付得起最便宜的那一爐嗎？"""
    cheapest = _cheapest_pair(state, content)
    return cheapest is not None and xinde >= craft.cost(content, cheapest)


def _cheapest_pair(state: GameState, content: Content) -> list[str] | None:
    """背包裡最便宜的兩樣素材（階最低的兩個，可以是同一種的兩個）；湊不出兩個就 None。"""
    held: list[str] = []
    for material, count in materials.bag_contents(state, content):
        held += [material.id] * count
    if len(held) < craft.MATERIALS_PER_CRAFT:
        return None
    held.sort(key=lambda mid: content.materials[mid].tier)
    return held[: craft.MATERIALS_PER_CRAFT]


def craft_line(
    state: GameState, content: Content, material_ids: list[str],
    world: WorldStateStore | None = None,
) -> str:
    """門下煉製那一塊的說明：成本、目前心得，或者為什麼還不能開爐。"""
    xinde = state.player.stats.get("xinde", 0)
    if len(material_ids) != craft.MATERIALS_PER_CRAFT:
        return (
            f"**煉製**　選 {craft.MATERIALS_PER_CRAFT} 樣素材煉成一門功法。凡品配方不花心得；"
            f"用到靈品、天品要花心得（遊歷打贏、操練、閉關都能得到）。目前心得 {xinde}。"
        )
    price = craft.cost(content, material_ids)
    names = "＋".join(content.materials[mid].name for mid in material_ids if mid in content.materials)
    problem = craft.can_craft(state, content, material_ids, world)
    # 種類開爐才揭曉（craft.result_kind），這裡刻意不說是內功還是武學
    if price == 0:
        head = f"**煉製**　{names} → 一門功法（開爐才知道是內功還是武學），凡品配方不花心得。"
    else:
        head = f"**煉製**　{names} → 一門功法（開爐才知道是內功還是武學），花 {price} 點心得（你有 {xinde} 點）。"
    return head if problem is None else f"{head}\n⚠ {problem}"


def art_library(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    """功法庫（煉出來但沒配上身的）：（顯示文字, 功法 id），給「改練」的選單用。

    跟底下的 `library()` 不是同一件事：那個列的是「目前配在身上、可以鍛鍊的」兩門。
    """
    out = []
    for art_id in state.player.arts:
        art = team.player_art(state, content, world, art_id)
        if art is None:
            continue
        level = state.player.art_levels.get(art_id, 1)
        out.append((f"{art.kind}　{art.name}（{art.quality}・屬{art.attribute}）第{level}成", art_id))
    return out


def bag_text(state: GameState, content: Content) -> str:
    """門下頁的「煉製素材」那一塊：背包內容，階高的排前面（素材是煉製的材料，見 craft.py）。"""
    items = materials.bag_contents(state, content)
    if not items:
        return "**煉製素材**　還沒撿到任何素材——打贏對手、四處探索，或在奇遇裡拿到。"
    lines = ["**煉製素材**　煉製功法的材料，分凡品、靈品、天品三階。"]
    lines += [
        f"- {m.name} ×{n}　{materials.tier_label(m)}・屬{m.attribute}　{m.description}"
        for m, n in items
    ]
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
    now, cap = team.member_neili(content, member)
    lines = [
        f"### {name}",
        f"第 {member.level} 級　氣血 {now:.0f}/{cap:.0f}",
        f"內功　{_art_label(content, world, member.neigong_id, member.neigong_level, own)}",
        f"武學　{_art_label(content, world, member.wugong_id, member.wugong_level, own)}",
    ]
    return "\n".join(lines)


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
    return art_card(art, level)


def art_card(art: MartialArt, level: int) -> str:
    """一門功法的功法卡（無限煉製設計 §8；FB-006）：名字・品質・屬性、目前熟練度與威力、
    第一成／第十成的威力、來源，最後是煉製時模型寫的那句說明。

    來源分三種（FB-017）：煉製（origin == "crafted"）寫「煉製（某某 首創）」，creator 是第一個煉出這個配方的人；
    取名自創（"created"）寫「自創（某某 所創）」；其他是本命武學。
    說明句只有真的有字時才有那一行：退路字表取名的功法、自創與本命武學都沒有說明，
    這時整行省略——不留空行、不出現 None（QA 寫進 FB-006 的驗收）。
    """
    nxt = "已達第十成" if level >= MAX_LEVEL else f"{power_at(art, level + 1):.1f}"
    if art.origin == "crafted":
        source = "煉製" + (f"（{art.creator} 首創）" if art.creator else "")
    elif art.origin == "created":
        source = "自創" + (f"（{art.creator} 所創）" if art.creator else "")
    else:
        source = "本命武學"
    lines = [
        f"【{art.name}】{art.quality}・屬{art.attribute}",
        f"第{level}成 {level_bar(level)}，威力 {power_at(art, level):.1f}（下一成：{nxt}）",
        f"第一成 {power_at(art, 1):.1f}　第十成 {power_at(art, MAX_LEVEL):.1f}",
        f"來源：{source}",
    ]
    note = art.note.strip()
    if note:
        lines.append(note)
    return "\n".join(lines)
