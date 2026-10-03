"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import craft, materials, team
from .martial_arts import MAX_LEVEL, power_at
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
    免得變成嘮叨；文字也只列出真正做得到的那幾件事。
    """
    xinde = state.player.stats.get("xinde", 0)
    if xinde < content.config.xinde_hint_threshold:
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
        parts.append(f"鍛鍊{'、'.join(todo)}（不花一分一毫）")
    if _can_afford_a_craft(state, content, xinde):
        parts.append("拿素材煉製新功法")
    if not parts:
        return None
    return f"💡 你已攢下 {xinde} 點心得。去「門下」{'，或'.join(parts)}。"


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
    state: GameState, content: Content, material_ids: list[str], kind: str,
    world: WorldStateStore | None = None,
) -> str:
    """門下煉製那一塊的說明：成本、目前心得，或者為什麼還不能開爐。"""
    xinde = state.player.stats.get("xinde", 0)
    if len(material_ids) != craft.MATERIALS_PER_CRAFT:
        return (
            f"**煉製**　選 {craft.MATERIALS_PER_CRAFT} 樣素材煉成一門功法。凡品配方不花心得；"
            f"用到靈品、天品要花心得（歷練打贏、操練、閉關都能得到）。目前心得 {xinde}。"
        )
    price = craft.cost(content, material_ids)
    names = "＋".join(content.materials[mid].name for mid in material_ids if mid in content.materials)
    problem = craft.can_craft(state, content, material_ids, kind, world)
    if price == 0:
        head = f"**煉製**　{names} → 一門{kind}，凡品配方不花心得。"
    else:
        head = f"**煉製**　{names} → 一門{kind}，花 {price} 點心得（你有 {xinde} 點）。"
    return head if problem is None else f"{head}\n⚠ {problem}"


def art_library(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    """功法庫（煉出來但沒配上身的）：（顯示文字, 功法 id），給「改練」的選單用。

    跟底下的 `library()` 不是同一件事：那個列的是「目前配在身上、可以鍛鍊的」兩門。
    """
    out = []
    for art_id in state.player.arts:
        art = team.resolve_art(art_id, content, world)
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


def _art_label(content: Content, world: WorldStateStore, skill_id: str | None, level: int) -> str:
    if skill_id is None:
        return "（尚未習得）"
    art = team.resolve_art(skill_id, content, world)
    if art is None:
        return skill_id
    return f"{art.name}（{art.quality}・屬{art.attribute}）第{level}成 {level_bar(level)}"


def member_card(state: GameState, content: Content, world: WorldStateStore, key: str) -> str:
    """一個人的角色卡：等級、氣血、內功、武學。"""
    if key == PLAYER:
        member = state.player.member
        name = state.player.name
    else:
        member = world.get_companion(key)
        name = content.characters[key].name
    now, cap = team.member_neili(content, member)
    lines = [
        f"### {name}",
        f"第 {member.level} 級　氣血 {now:.0f}/{cap:.0f}",
        f"內功　{_art_label(content, world, member.neigong_id, member.neigong_level)}",
        f"武學　{_art_label(content, world, member.wugong_id, member.wugong_level)}",
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
            items.append((f"{kind}　{_art_label(content, world, slot_id, level)}", kind))
    return items


def detail(state: GameState, content: Content, world: WorldStateStore, kind: str) -> str:
    """kind 是「內功」或「武學」：目前這一門的詳細說明。"""
    member = state.player.member
    skill_id = member.neigong_id if kind == "內功" else member.wugong_id
    level = member.neigong_level if kind == "內功" else member.wugong_level
    if skill_id is None:
        return f"你還沒有{kind}。"
    art = team.resolve_art(skill_id, content, world)
    if art is None:
        return f"（找不到武學資料：{skill_id}）"
    now = power_at(art, level)
    nxt = "已達第十成" if level >= 10 else f"{power_at(art, level + 1):.1f}"
    origin = "自創" if art.origin == "created" else "本命武學"
    creator = f"（{art.creator} 所創）" if art.creator else ""
    return (
        f"【{art.name}】{art.quality}・屬{art.attribute}\n"
        f"第{level}成，威力 {now:.1f}（下一成：{nxt}）\n"
        f"來源：{origin}{creator}"
    )
