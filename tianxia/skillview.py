"""「門下」頁的說明文字（sanguo-companions 合併大幅簡化，取代舊的武學欄/資質/相剋說明）：
只讀狀態與內容、只產生文字，不改任何東西。新制度下每人最多一門內功、一門武學，沒有多個
自選欄、沒有流派資質相剋，這裡的文字因此比舊版精簡很多。
"""
from __future__ import annotations

from . import team
from .martial_arts import MAX_LEVEL, power_at
from .models import Content
from .state import PLAYER, GameState
from .world_state import WorldStateStore


def rules_line(content: Content) -> str:
    return "每人最多學一門內功、一門武學：自創功法（取名決定屬性/威力/成長性）或鍛鍊已知武學。"


def practice_hint(state: GameState, content: Content) -> str | None:
    """主畫面的練功提示：心得擱到 `xinde_hint_threshold` 以上、而且確實還有功夫可以練時才回傳一句話。

    心得目前完全不是貨幣（`team.practice`/`create_skill` 兩條路徑都免費、無限次，
    `Config.xinde_cost_factor` 沒有任何地方讀），所以這句話的用途不是「你存夠錢了」，而是把
    「在江湖裡攢到的心得」跟「門下的練功動作」接起來。實測隨機玩完一整季的心得收入只有
    20~96（刻意閉關才會多），所以門檻故意訂得低；真正需要這句話的是從來沒進過門下、心得
    一路擱著而武學還停在第一成的玩家。兩門都練到第十成就不再提示，免得變成嘮叨。
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
    if not todo:
        return None
    return f"💡 你已攢下 {xinde} 點心得。去「門下」自創或鍛鍊{'、'.join(todo)}不花一分一毫，別讓它擱著。"


def _art_label(content: Content, world: WorldStateStore, skill_id: str | None, level: int) -> str:
    if skill_id is None:
        return "（尚未習得）"
    art = team.resolve_art(skill_id, content, world)
    if art is None:
        return skill_id
    return f"{art.name}（{art.quality}・屬{art.attribute}）第{level}成"


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
