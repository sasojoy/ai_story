"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import fusion, insights, materials, team
from .library import held_count, holding_cap  # 不 import 整個 library 模組：這個檔案自己有一個叫 library() 的函式
from .martial_arts import MAX_LEVEL, MartialArt, power_at
from .models import Content
from .state import PLAYER, GameState
from .world_state import WorldStateStore


def rules_line(content: Content) -> str:
    return "身上一門內功、一門武學：花心得練成，用意境修練衝品質；武學也能在「煉製」融意境衍生新武學。"


def practice_hint(state: GameState, content: Content) -> str | None:
    """主畫面的提示：心得擱到 `xinde_hint_threshold` 以上、而且確實有事可做時才回傳一句話。

    心得的去處（武學與成長設計第四節）：練成（身上這一門還沒第十成、付得起下一成）與合成（手上有意境、
    持有沒滿、付得起一次，見 fusion.can_forge）。兩樣都做不了就閉嘴，免得變成嘮叨。休季時什麼都不能做，也不提示（FB-047）。
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
        if getattr(member, slot) is not None and getattr(member, level_slot) < MAX_LEVEL
        and xinde >= team.practice_price(content, getattr(member, level_slot))
    ]
    parts = []
    if todo:
        parts.append(f"去「修練」練成{'、'.join(todo)}")
    if fusion.can_forge(state, content):  # 手上有意境、持有沒滿、付得起一次合成或合併才提；光有意境不算
        parts.append("去「煉製」拿意境合成新武學")
    if not parts:
        return None
    return f"💡 你已攢下 {xinde} 點心得。{'，或'.join(parts)}。"


def forge_line(
    state: GameState, content: Content, world: WorldStateStore, art_id: str | None, insight_ids: list[str],
) -> str:
    """煉製頁的說明：放了什麼、會做哪一種、花多少心得，或者為什麼還不能開爐。"""
    cfg, xinde = content.config, state.player.stats.get("xinde", 0)
    count = f"武學與意境 {held_count(state)}/{holding_cap(content, state.player.member.level)}"
    if art_id and len(insight_ids) == 1:
        base = team.player_art(state, content, world, art_id)
        insight = insights.resolve(insight_ids[0], content, world)
        if base is None or insight is None:
            return "（選了不存在的東西。）"
        head = (
            f"**合成**　【{base.name}】＋「{insight.name}」→ 一門新{base.kind}"
            f"（屬{insight.attribute}，品質跟【{base.name}】一樣是{base.quality}），"
            f"花 {cfg.fuse_xinde} 點心得（你有 {xinde} 點）。"
        )
        problem = fusion.fuse_problem(state, content, world, art_id, insight_ids[0])
    elif not art_id and len(insight_ids) == 2:
        a, b = (insights.resolve(i, content, world) for i in insight_ids)
        if a is None or b is None:
            return "（選了不存在的東西。）"
        head = f"**合併**　「{a.name}」＋「{b.name}」→ 一個新的意境，花 {cfg.merge_xinde} 點心得（你有 {xinde} 點）。"
        problem = fusion.merge_problem(state, content, world, *insight_ids)
    else:
        return f"**煉製**　放一門武學和一個意境，衍生出一門新武學（底留著）；或放兩個意境，合出新的意境。{count}。"
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
    """背包：隨身帶著的材料（糧草、伏筆要用），階高的排前面。"""
    items = materials.bag_contents(state, content)
    if not items:
        return "**背包**　還沒有東西——打贏對手、沿路採集，或在奇遇裡拿到。"
    lines = ["**背包**　隨身帶著的材料，分凡品、靈品、天品三階。"]
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
