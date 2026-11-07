"""修練頁的唯讀資料（全部拆包第 23 批）：原本 Game 上「門下頁面」那一段（server.menxia_view 叫的功法卡、名冊、背包、持有數、功法庫、
意境、等著定名的那一門），Game 留一行委派。說明那一層照舊在 skillview（還沒搬的舊模組，共用規則層 SHARED_LATER）。只讀。"""
from __future__ import annotations

from tianxia import library, team, traits
from tianxia import skillview  # 過渡：待搬（門下頁的說明；共用規則層 SHARED_LATER）


def skill_detail(ctx, kind: str) -> str:
    return skillview.detail(ctx.state, ctx.content, ctx.world, kind)


def art_detail(ctx, art_id: str) -> str:
    """這個角色擁有的一門功法的功法卡（FB-006；功法庫先看卡再改練）。熟練度：配在身上的看身上
    那一欄，功法庫裡的看換下來時存的 art_levels（沒存過從第一成算，跟 team.switch_art 一致）。
    不是自己的、或內容與共用世界裡都找不到時回一句話。"""
    level = library.level_of(ctx.state, art_id)
    art = None if level is None else team.player_art(ctx.state, ctx.content, ctx.world, art_id)
    if art is None:
        return "（找不到這門功法。）"
    return skillview.art_card(
        art, level, parent_names=skillview.parent_names(art, ctx.content, ctx.world),
        trait_line=traits.card_line(ctx.content, art),
        compare_line=team.compare_with_worn(ctx.state, ctx.content, ctx.world, art),  # W6
        gen_word=skillview.gen_word(art, ctx.content, ctx.world),
    )


def member_card(ctx, key: str) -> str:
    return skillview.member_card(ctx.state, ctx.content, ctx.world, key)


def roster_cards(ctx) -> list[dict]:
    return skillview.roster_cards(ctx.state, ctx.content, ctx.world)


def menxia_rules(ctx) -> str:
    return skillview.rules_line(ctx.content)


def attribute_note(ctx) -> str:
    """修練頁與煉製頁摺起來的「屬性有什麼用」那一句（W2）。"""
    return skillview.attribute_line(ctx.content)


def bag_text(ctx) -> str:
    return skillview.bag_text(ctx.state, ctx.content)


def holdings(ctx) -> dict:
    """武學與意境的持有數與上限（武學與成長設計 4.5）。"""
    return {
        "count": library.held_count(ctx.state),
        "cap": library.cap_of(ctx.state, ctx.content),
    }


def art_rows(ctx) -> list[dict]:
    return skillview.art_rows(ctx.state, ctx.content, ctx.world)


def insight_rows(ctx) -> list[dict]:
    return skillview.insight_rows(ctx.state, ctx.content, ctx.world)


def naming_row(ctx) -> dict | None:
    """等著自己取正式名字的那一門（第一個練成絕學）；沒有是 None。"""
    art_id = ctx.state.player.naming
    art = team.resolve_art(art_id, ctx.content, ctx.world) if art_id else None
    return None if art is None else {"id": art_id, "name": art.name}
