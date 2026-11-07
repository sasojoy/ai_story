"""鐵匠鋪的架上（全部拆包第 41 批）：第二層選單（兵器頁、防具頁、素材頁，打造兵器…／打造防具…挑到一半時換成那一步）與選單上按下去的一下
（切頁、買、修、換上、拆解、打造與淬煉的每一步、離開）。原本 Game 上的 8 個方法，Game 只留 smith_options 的一行委派（核心原位的選單叫它）；
choose 的 smith: 由包的 choose 掛鉤接走（Outcome.run 叫 smith）。計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md 1.1。
第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用 tianxia/core/services_list.md 那張清單上的；這一包互相叫直接叫函式。
規則照模組屬性叫（weapons.buy、smithing.step……：測試換掉模組上的，這裡照樣打得到）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import armor  # 共用規則層
from tianxia import weapons  # 共用規則層
from tianxia import equipment  # 共用規則層
from tianxia import economy  # 共用規則層
from tianxia import four_tiers  # 共用規則層
from tianxia import silver  # 共用規則層
from tianxia import team  # 核心
from tianxia.core.option import Option  # 核心
from tianxia.core.travel_base import TravelBlock  # 核心（動身被擋那一句的型別，core_seams）
from tianxia.core import smith_base  # 核心（打造單子讀的那一小半：收店那兩格讀，core_seams）

from . import shop_view
from . import smithing
from . import forge_actions
from . import trade_actions

if TYPE_CHECKING:
    from tianxia.engine import Game


def smith_options(ctx: Game) -> list[Option]:
    """鐵匠鋪的第二層選單（兵器設計 4.1；裝備四欄設計 4.6）：分兵器、防具兩頁（equipment.page；兩欄都開著時預設兵器頁，
    「離開」前一顆切到另一頁；只開一欄就只有那一頁、沒有切頁鈕）。打造兵器…／打造防具…挑到一半（smith_draft）時整份換成那一步。
    兵器頁：架上六把各一顆「買」（買不了的灰掉、寫為什麼；種類對得上身上武學的那一把標出來），手上那把一顆「修」（寫明用掉哪一種素材）
    與「淬煉」（身上那把配不上身上的武學時，按得下去的「修」「淬煉」多一句提醒：白花料與銀兩，加成用不上），
    裝備庫裡配得上身上武學的每把一顆「換上」（配不上的到修練頁換），「打造兵器…」（排在換上與拆解中間：FB-125），
    拆解（_dismantle_options）。防具頁見 _armor_options。裝備庫都只看這一頁那一欄（3.3）。都不花體力。"""
    s, c = ctx.state, ctx.content
    art = team.player_art(s, c, ctx.world, s.player.member.wugong_id)
    fit_kind = weapons.art_weapon(art.id, c, ctx.world) if art is not None else None
    if s.player.smith_draft is not None:
        neigong = team.player_art(s, c, ctx.world, s.player.member.neigong_id)  # 防具的單子標跟內功同屬性的輔料
        return smithing.draft_options(s, c, ctx.world, art, neigong)  # 打造兵器…／打造防具…挑到一半：只畫這一步
    if s.player.smith_page == equipment.MATERIAL_PAGE and trade_on(ctx):
        return material_options(ctx)  # 素材頁：收購、升階（素材與經濟設計第四、五節）
    if equipment.page(s.player, c) == "armor":
        return armor_options(ctx)  # 防具頁（裝備四欄 4.6）
    opts = []
    for item in weapons.stock(s, c):
        problem = weapons.buy_problem(s, c, item.kind)
        note = problem or f"{c.config.weapons.shop_price} 兩"
        mark = weapons.FITS_MARK if c.config.weapons.enabled and item.kind == fit_kind else ""
        opts.append(Option(id=f"smith:buy:{item.kind}", label=f"買【{item.name}】（{weapons.noun(item.kind)}・一階・{note}）{mark}",
                           enabled=problem is None))
    # 身上那把配不上身上的武學（含沒有武學）：加成是 0，修與淬煉照樣按得下去，可是花的料與銀兩看不到回報，按鈕上提醒一句（PM 2026-10-11）
    unfit = weapons.unfit_note(s.player.weapon) if weapons.worn_unfit(s, art, c, ctx.world) else ""
    if s.player.weapon is not None:
        problem = weapons.repair_problem(s, c)
        material = weapons.repair_material(s, c)
        use = f"{c.materials[material].name}×1" if material is not None else "一個一階素材"
        note = problem or f"{use}＋{c.config.weapons.repair_silver} 兩"
        opts.append(Option(id="smith:repair", label=f"修【{s.player.weapon.name}】（鋒利度 {s.player.weapon.edge}・{note}）{unfit if problem is None else ''}",
                           enabled=problem is None))
    temper = smithing.temper_option(s, c)  # 淬煉身上那把（兵器設計 4.7）；空手沒有
    if temper is not None:
        if temper.enabled and unfit:  # 灰掉的（淬滿了、沒料、沒錢）照舊：沒有東西會白花
            temper = temper.model_copy(update={"label": temper.label + unfit})
        opts.append(temper)
    for w in equipment.in_slot(s.player, "weapon"):  # 裝備四欄 3.3：只看武器那一欄
        if weapons.usable(w, art, c, ctx.world) and equipment.wear_problem(s, c, w) is None:  # 穿不上的神器不列（正式季整合 5.8）
            opts.append(Option(id=f"smith:wield:{w.id}", label=f"換上【{w.name}】（{weapons.noun(w.kind)}・{weapons.grade_line(w)}・鋒利度 {w.edge}）"))
    if c.config.weapons.enabled:
        opts.append(smithing.forge_door(s, c))  # 打造兵器…（排在換上與拆解中間：FB-125，兩顆不相鄰）
    opts += dismantle_options(ctx, "weapon")  # 拆解（只看武器那一欄；最多 DISMANTLE_LIST 顆、先問一次）
    return opts + smith_tail(ctx)


def dismantle_options(ctx: Game, slot: str) -> list[Option]:
    """鐵匠鋪那一頁的拆解（兵器設計 4.7.1、裝備四欄 4.8）：裝備庫裡這一欄的，磨損最多、階最低的先、最多 DISMANTLE_LIST 顆，
    每顆先問一次（FB-125：confirm／confirm_yes「拆掉」），標籤寫階品質與淬煉次數（同一個配方好幾件才分得出來）；
    多的一行灰掉的說明指到修練頁。這一欄關著是空的。"""
    c = ctx.content
    if not equipment.on(c, slot):
        return []
    breakable = sorted(equipment.in_slot(ctx.state.player, slot), key=equipment.dismantle_order)
    opts = [
        Option(id=f"smith:dismantle:{w.id}", label=f"拆解【{w.name}】（{equipment.kept(w)}）", enabled=False)  # 5.4：灰掉寫原因
        if w.original else
        Option(id=f"smith:dismantle:{w.id}",
               label=f"拆解【{w.name}】（{equipment.grade_line(w)}）→ {equipment.dismantle_material(c, w).name}×1",
               confirm=equipment.dismantle_confirm(c, w), confirm_yes=equipment.DISMANTLE_YES)  # FB-125：先問一次
        for w in breakable[:equipment.DISMANTLE_LIST]
    ]
    if len(breakable) > equipment.DISMANTLE_LIST:
        opts.append(Option(id="smith:dismantle-more", enabled=False,
                           label=equipment.DISMANTLE_MORE.format(n=len(breakable) - equipment.DISMANTLE_LIST)))
    return opts


def armor_options(ctx: Game) -> list[Option]:
    """鐵匠鋪的防具頁（裝備四欄設計 4.6）：架上剛柔快慢四件各一顆「買」（一階下品；寫這件給你少扣幾成氣血、對不對得上你的內功，
    買不了的灰掉寫為什麼），身上那件一顆「修」（寫明用掉哪一種素材）、一顆「淬煉」，裝備庫裡的防具「換上」（最多 DISMANTLE_LIST 件、最好的先，
    FB-134），「打造防具…」，拆解，兵器也開著時一顆切到兵器頁，最後「離開」。都不花體力。FB-125：打造入口隔開換上與拆解（同兵器頁），
    拆解另外先問一次（confirm／confirm_yes）擋誤按。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    neigong = team.player_art(s, c, ctx.world, p.member.neigong_id)
    rule = c.config.armor
    opts = []
    # 買、修、換上三種鈕的寫法都待 joy 潤；磨損的叫法讀 armor.WEAR_WORD（3.1 的字表），不寫死
    for attribute in armor.SHOP_ATTRIBUTES:
        item = armor.shop_item(attribute)
        problem = armor.buy_problem(s, c, attribute)
        fit = armor.fit_note(item, neigong)
        note = problem or f"{rule.shop_price} 兩"
        opts.append(Option(
            id=f"{armor.BUY}{attribute}", enabled=problem is None,
            label=f"買【{item.name}】（屬{attribute}・一階・少扣 {armor.pct(armor.cut(item, neigong, c))} 氣血{'・' + fit if fit else ''}・{note}）",
        ))
    if p.armor is not None:
        problem = armor.repair_problem(s, c)
        material = equipment.repair_material(s, c)
        use = f"{c.materials[material].name}×1" if material is not None else "一個一階素材"
        note = problem or f"{use}＋{rule.repair_silver} 兩"
        opts.append(Option(id=armor.REPAIR, label=f"修【{p.armor.name}】（{armor.WEAR_WORD} {p.armor.edge}・{note}）", enabled=problem is None))
    temper = smithing.temper_option(s, c, "armor")  # 淬煉身上那件（四欄設計 4.1）；沒穿沒有
    if temper is not None:
        opts.append(temper)
    # FB-134：「換上」最多 DISMANTLE_LIST 件，修好之後減損高的先、同分 id 大的先——跟 armor.wanted 挑換上的鍵一樣，整季機器人與假人
    # 要按的那一顆一定列得出來；多的一行灰掉的說明指到修練頁（同拆解）。淬過的寫「・淬煉 N」（equipment.grade_line）
    spares = sorted((a for a in equipment.in_slot(p, "armor") if equipment.wear_problem(s, c, a) is None),  # 穿不上的神器不列（5.8）
                    key=lambda a: (armor.fresh_cut(a, neigong, c), a.id), reverse=True)
    for a in spares[:equipment.DISMANTLE_LIST]:
        opts.append(Option(id=f"smith:wield:{a.id}", label=f"換上【{a.name}】（屬{a.attribute}・{equipment.grade_line(a)}・{armor.WEAR_WORD} {a.edge}）"))
    if len(spares) > equipment.DISMANTLE_LIST:
        opts.append(Option(id="smith:wield-more", enabled=False,
                           label=equipment.WIELD_MORE.format(n=len(spares) - equipment.DISMANTLE_LIST)))
    opts.append(smithing.forge_door(s, c, "armor"))  # 打造防具…（排在換上與拆解中間：FB-125，同兵器頁）
    return opts + dismantle_options(ctx, "armor") + smith_tail(ctx)


def smith_tail(ctx: Game) -> list[Option]:
    """鐵匠鋪每一頁最後幾顆：收購或升階開著時一顆進素材頁（素材與經濟設計第四、五節），另一欄也開著時一顆切頁（裝備四欄設計 4.6），
    再來永遠按得下去的「離開」。"""
    other = equipment.other_page(ctx.state.player, ctx.content)
    door = [Option(id=f"smith:page:{equipment.MATERIAL_PAGE}", label=equipment.MATERIAL_LABEL)] if trade_on(ctx) else []
    tail = [Option(id=f"smith:page:{other}", label=equipment.PAGE_LABELS[other])] if other is not None else []
    return door + tail + [Option(id="smith:back", label="離開鐵匠鋪")]


def trade_on(ctx: Game) -> bool:
    """鐵匠鋪的素材頁開不開（Config.economy 的收購或升階有一樣開著）。"""
    econ = ctx.content.config.economy
    return econ.sell or econ.upgrade


def material_options(ctx: Game) -> list[Option]:
    """鐵匠鋪的素材頁（素材與經濟設計第四、五節；店面關著時、整季機器人與假人看的那一串）：背包裡收得了的每一種一顆「賣一個」，
    手上有低一階料的每個（屬性, 階）一顆「升一個」（三階寫今天還能換幾個；按不下去的灰掉寫為什麼），回兵器／防具頁，最後「離開」。
    字與按得下去與否都照店面的 shop_view.trade_view（同一份規則）。都不花體力。"""
    s, c = ctx.state, ctx.content
    trade = shop_view.trade_view(s, c, ctx._pill_day()) or {"sell": [], "upgrade": []}
    opts = [
        Option(id=f"smith:sell:{row['id']}", enabled=row["problem"] is None,
               label=economy.SELL_LABEL.format(name=row["name"], price=row["price"], have=row["have"]) + row["dark"])  # 名聲 5.2：（黑市價）
        for row in trade["sell"]
    ]
    for row in trade["upgrade"]:
        if row["have"] <= 0:
            continue  # 選單只列手上有料的（店面四個屬性都列）
        option_id = f"smith:upgrade:{row['attribute']}:{row['tier']}"
        if row["problem"] is not None:
            opts.append(Option(id=option_id, enabled=False,
                               label=economy.UPGRADE_REFUSED.format(low=row["from"], need=row["need"], problem=row["problem"])))
            continue
        left_line = economy.UPGRADE_SEASON_LEFT if row["tier"] == four_tiers.TIER else economy.UPGRADE_LEFT
        left = left_line.format(n=row["left"]) if row["left"] is not None else ""
        opts.append(Option(id=option_id, label=economy.UPGRADE_LABEL.format(
            low=row["from"], need=row["need"], cost=row["cost"], odds=row["odds"], left=left)))
    pages = [Option(id=f"smith:page:{slot}", label=equipment.PAGE_LABELS[slot]) for slot in equipment.SMITH_PAGES if equipment.on(c, slot)]
    return opts + pages + [Option(id="smith:back", label="離開鐵匠鋪")]


def smith(ctx: Game, arg: str) -> list[str]:
    """鐵匠鋪上的選擇（_smith_act）；這一下花了銀兩或素材（買、修、淬煉、開爐；拆解拿到素材不算），再擲一次鐵匠順口（_smith_clue；
    打造隱藏配方設計 6.2、計畫「要 PM 定的」第 3 條）。順口說出的那一句記成店面上這一下的話（shop_clue，店面獨立介面設計 1.4）。"""
    p = ctx.state.player
    p.shop_clue = ""
    silver, mats = p.stats.get("silver", 0), sum(p.materials.values())
    msgs = smith_act(ctx, arg)
    if arg.partition(":")[0] == "sell":
        return msgs  # 收購是鐵匠付你錢：沒花銀兩，不擲鐵匠順口（素材與經濟計畫 B3）
    if p.stats.get("silver", 0) < silver or sum(p.materials.values()) < mats:
        clue = ctx._smith_clue(paid=p.stats.get("silver", 0) < silver)
        if clue:
            p.shop_clue = clue[0]
        msgs = msgs + clue
    return msgs


def smith_act(ctx: Game, arg: str) -> list[str]:
    """鐵匠鋪上的一下（_smith 包著它）：切頁、買、修、換上、拆解（兵器頁或防具頁）、打造與淬煉的每一步，或離開（收起選單、打造的單子
    與停在哪一頁）。做完選單還開著，可以接著挑。"""
    s, c = ctx.state, ctx.content
    verb, _, rest = arg.partition(":")
    if verb == "back":
        equipment.close_smith(s.player)
        return [f"你離開了{weapons.SMITH}。"]
    if verb == "page":  # 切到另一頁（裝備四欄 4.6）：只是換一頁，不回訊息（choose 照它不寫紀錄）
        from_material = s.player.smith_page == equipment.MATERIAL_PAGE
        if (
            rest == equipment.other_page(s.player, c)
            or (rest == equipment.MATERIAL_PAGE and trade_on(ctx))  # 進素材頁（素材與經濟設計第四、五節）
            or (from_material and rest in equipment.SMITH_PAGES and equipment.on(c, rest))  # 從素材頁回兵器或防具頁
        ):
            s.player.smith_page = rest
        return []
    if verb == "sell":  # 素材頁：賣一個（第五節）
        return trade_actions.trade_sell(ctx, rest, 1)
    if verb == "upgrade":  # 素材頁：升一個（第四節），rest 是「屬性:階」
        attribute, _, tier = rest.partition(":")
        return trade_actions.trade_upgrade(ctx, attribute, int(tier) if tier.isdecimal() else 0)
    if verb == smithing.GO_VERB:
        kind, main, aux = smithing.parse_go(f"smith:{arg}")
        return forge_actions.smith_forge_once(ctx, kind, main, aux)[1]
    if verb in smithing.STEP_VERBS:
        if verb in ("temper", "armor-temper"):  # 店面上掌櫃那一句（1.4）：照淬煉之前的擋法
            ctx._shop_after(smithing.temper_problem(s, c, "armor" if verb == "armor-temper" else "weapon"), "temper")
        return smithing.step(s, c, verb, rest)
    if verb == "buy":
        ctx._shop_after(weapons.buy_problem(s, c, rest), "buy")
        return weapons.buy(s, c, rest, team.player_art(s, c, ctx.world, s.player.member.wugong_id), ctx.world)  # 配得上就直接換上（FB-128）
    if verb == "repair":
        ctx._shop_after(weapons.repair_problem(s, c), "repair")
        return weapons.repair(s, c)
    if verb == "armor-buy":
        ctx._shop_after(armor.buy_problem(s, c, rest), "buy")
        return armor.buy(s, c, rest)
    if verb == "armor-repair":
        ctx._shop_after(armor.repair_problem(s, c), "repair")
        return armor.repair(s, c)
    # 換上與拆解兩頁共用 id 開頭（兵:N、甲:N 本來就全角色唯一），照停在哪一頁限定欄位
    if verb == "wield":
        return (armor.wield if equipment.page(s.player, c) == "armor" else weapons.wield)(s, c, rest)
    if verb == "dismantle":
        return (armor.dismantle if equipment.page(s.player, c) == "armor" else weapons.dismantle)(s, c, rest)
    return ["（此刻無法這麼做。）"]


def enter(ctx: Game) -> list[str]:
    """act:smith（鐵匠鋪包的 act 子動詞接走，原本是 Game._act 中段那幾行）：走進鐵匠鋪。"""
    equipment.open_smith(ctx.state.player, ctx.content)  # 打開鐵匠鋪（見 smith_options），不花體力；單子從頭開始（Review Focus 4）、停在第一個開著的那一頁
    ctx.state.player.shop_clue = ""
    ctx._shop_say("enter")  # 店面上掌櫃那一句（店面獨立介面設計 1.4）
    ctx.state.player.smith_rule = shop_view.next_rule(ctx.state, ctx.content)  # 背包有四階時鐵匠講一句神器的規矩（正式季整合 5.10）
    return [f"你走進{weapons.SMITH}，爐火燒得正旺。"]


def sync_close(ctx: Game) -> None:
    """sync.close 的 smithy 那一格（core_seams，全部拆包第 55 批；照原位搬）：同步時開關關了、人被挪走了收店，單子那一欄關了清單子。
    條件跟清失效參照那一格不一樣（drop_stale），不合併。"""
    s, c = ctx.state, ctx.content
    if s.player.picking_smith and not equipment.smith_open(s, c):
        equipment.close_smith(s.player)  # 開關關了、人不在城鎮了（內容改版、管理者挪人）：收起鐵匠鋪，單子與頁一起清
    if s.player.smith_draft is not None and not smith_base.draft_here(s, c, s.player.smith_draft):
        s.player.smith_draft = None  # 單子那一欄關了、另一欄還開著：鐵匠鋪照開（另一頁），這張單子清掉


def drop_stale(ctx: Game) -> None:
    """stale.mid 的 smithy 那一格（core_seams，全部拆包第 55 批；照原位搬）：讀檔時收店與清單子。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if p.picking_smith and not equipment.smith_open(s, c):
        equipment.close_smith(p)  # 武器、防具都關了、人不在城鎮了：收起鐵匠鋪，打造的單子與停在哪一頁一起清
    if p.smith_draft is not None and (
        not p.picking_smith or not smith_base.draft_here(s, c, p.smith_draft) or smith_base.draft_stale(c, p.smith_draft)
    ):
        p.smith_draft = None  # 單子只在鐵匠鋪開著、那一欄也開著時有意義（兵器的單子看武器、防具的單子看防具：一欄關了另一欄還開著，鐵匠鋪照開，那一欄的單子要清）；內容改版拿掉了單子上的種類或素材：選單畫不出來，從頭來


def here_cell(ctx: Game, loc, cost, odds) -> list[Option]:
    """here/smithy 那一格（core_seams，全部拆包第 56 批；原本在 Game._everyday_options）：鐵匠鋪（兵器設計 4.1；裝備四欄 4.6：武器或防具開著就開門）：只是打開第二層選單，不花體力。"""
    return [Option(id="act:smith", label=weapons.SMITH)] if equipment.smith_open(ctx.state, ctx.content) else []


def open_cell(ctx: Game) -> str | None:
    """open/smithy 那一格（core_seams，全部拆包第 56 批；原本在 Game._shop_open）：沒坐著是 None；一步一步的單子開著或這裡不開門了是 ""（核心 or None），不然 smith。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not p.picking_smith:
        return None
    return "smith" if p.smith_draft is None and equipment.smith_open(s, c) else ""


def travel_block(state, content) -> TravelBlock | None:
    """block/smithy 那一格（core_seams，全部拆包第 56 批；原本在 atlas.travel_block，字一字不動）。"""
    return TravelBlock("鐵匠鋪還開著，先離開才能安排前往", to_jianghu=True) if state.player.picking_smith else None
