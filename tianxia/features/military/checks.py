"""軍情包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

import functools

from tianxia.core.content_base import TIMETABLE_SIDES, check_traditional as _check_traditional
from tianxia.models import Content, STATS
from tianxia.zh import to_traditional


def check_promotions(c: Content, need, known) -> None:
    """晉升（content/promotions.json、followers.json，計畫 T5）：陣營在劇本裡、每陣營每階一筆；人物在人物表；地點存在
    （或 nearest_base）；奇遇存在；有接手的人就要有接手版的奇遇與召見；部下的陣營存在、武學在 skills.json；
    promote／followers 只寫在晉升奇遇的選項上，給的部下是那個陣營的。
    第 2 階寫 location／event_main／summons_text，第 3、4 階寫 legs（正式版丙一）：每段有版本、版本的人物與地點存在、
    before_event 在時刻表；各段的版本事件都算晉升奇遇。選項效果的 summons_next（只有最後一段以前的奇遇、寫自己的 id）、
    patron（只有晉升奇遇）、event_mods（只有擲骰的時刻表大事）在這裡查。
    奇遇的選項要跟它在 legs 裡的位置對得上（最終審查 m3）：promote 只能是 2～4、而且等於那一則所屬的那一階；
    非最後一段的每個選項（檢定、戰鬥的輸贏兩邊也一樣）要往下一段（summons_next）或結束召見（promote），最後一段的每個選項要
    promote——不然召見留在原地，「應召」（不花體力）又能重演同一幕、獎勵白拿。"""
    factions = {f.id for f in c.scenario.factions}
    seen: set[tuple[str, int]] = set()
    promo_events: dict[str, str] = {}
    unfinished: set[str] = set()  # 第 3、4 階奇遇的各段裡，不是最後一段的版本事件：只有它們的選項可以寫 summons_next
    last_events: set[str] = set()  # 最後一段的版本事件：每個選項都要晉升
    leg_ranks: dict[str, set[int]] = {}  # 各段的版本事件 → 它在哪幾階的 legs 裡（promote 要等於那一階）
    for promo in c.promotions:
        where = f"promotions.json 的 {promo.faction}／第 {promo.rank} 階"
        need(promo.faction in factions, f"{where}：陣營不在劇本裡")
        need((promo.faction, promo.rank) not in seen, f"{where}：同一個陣營的同一階寫了兩筆")
        seen.add((promo.faction, promo.rank))
        known(where, [x for x in (promo.figure, promo.successor) if x is not None], c.figures, "人物")
        if promo.location and promo.location != "nearest_base":  # 第 3、4 階的 location 空著（地點寫在各段），空的不查
            known(where, [promo.location], c.locations, "地點")
        need(
            (promo.successor is None) == (promo.event_handoff is None) == (promo.summons_handoff is None),
            f"{where}：有接手的人就要有接手版的奇遇與召見，沒有就都不寫",
        )
        for event_id in filter(None, (promo.event_main, promo.event_handoff)):
            known(where, [event_id], c.events, "事件")
            promo_events[event_id] = promo.faction
        if promo.rank == 2:
            need(bool(promo.location and promo.event_main and promo.summons_text),
                 f"{where}：第 2 階要寫 location、event_main、summons_text")
        else:
            need(bool(promo.legs), f"{where}：第 {promo.rank} 階要寫 legs")
        for i, leg in enumerate(promo.legs):
            need(bool(leg.casts), f"{where}：第 {i + 1} 段沒有版本")
            if leg.location and leg.location != "nearest_base":  # 段的地點有寫才查
                known(where, [leg.location], c.locations, "地點")
            for cast in leg.casts:
                known(where, [cast.event], c.events, "事件")
                promo_events[cast.event] = promo.faction  # 各段的奇遇都算晉升奇遇：最後一段的選項才寫 promote、followers，下面那條檢查要認得它
                leg_ranks.setdefault(cast.event, set()).add(promo.rank)
                if i < len(promo.legs) - 1:
                    unfinished.add(cast.event)
                else:
                    last_events.add(cast.event)
                known(where, [cast.figure] if cast.figure else [], c.figures, "人物")
                known(where, [cast.at] if cast.at else [], c.locations, "地點")
                need(cast.figure is not None or cast.at is not None or leg.location is not None,
                     f"{where}：第 {i + 1} 段的 {cast.event} 不知道在哪裡演")
                need(cast.before_event is None or any(e.id == cast.before_event for e in c.timetable),
                     f"{where}：before_event {cast.before_event} 不在時刻表")
        for line in promo.patron_lines.values():
            known(where, list(line.affinity), c.characters, "人物")
    rolled = {e.id for e in c.timetable if e.roll_side is not None}  # event_mods 只對擲骰的大事有意義（timetable.add_mod）
    timetable_ids = {e.id for e in c.timetable}
    for fid, follower in c.followers.items():
        where = f"followers.json 的 {fid}"
        need(follower.faction in factions, f"{where}：陣營不在劇本裡")
        known(where, [follower.wugong], c.skills, "武學")
    for event in c.events.values():
        for choice in event.choices:
            for effect in (choice.effect, choice.fail_effect):  # 檢定輸的那一邊也一樣（promo_hao_4 的摔角是第一則在 fail_effect 晉升的）
                if effect.promote is None and not effect.followers:
                    continue
                where = f"事件 {event.id}"
                need(event.id in promo_events, f"{where}：promote／followers 只能寫在晉升奇遇（promotions.json 的事件）")
                known(where, effect.followers, c.followers, "部下")
                side = promo_events.get(event.id)
                need(all(c.followers[f].faction == side for f in effect.followers if f in c.followers),
                     f"{where}：給的部下要是 {side} 的")
    # 第 3、4 階的三種新效果（正式版丙一）：選項的 effect 與 fail_effect 都查
    for event in c.events.values():
        for choice in event.choices:
            where = f"事件 {event.id}"
            # 這個選項會走到的效果：檢定、戰鬥有輸贏兩邊；沒有的話 fail_effect 不會被用到
            sides = (choice.effect, choice.fail_effect) if choice.check is not None or choice.combat else (choice.effect,)
            if event.id in unfinished:
                need(all(e.summons_next is not None or e.promote is not None for e in sides),
                     f"{where}：非最後一段的選項每一邊（檢定、戰鬥的輸贏也一樣）都要寫 summons_next（往下一段）或 promote（結束召見），"
                     "不然召見留在原地，「應召」又能重演同一幕")
            if event.id in last_events:
                need(all(e.promote is not None for e in sides),
                     f"{where}：最後一段的選項每一邊（檢定、戰鬥的輸贏也一樣）都要寫 promote，不然召見留在原地，「應召」又能重演同一幕")
            for effect in (choice.effect, choice.fail_effect):
                if effect.donate_grain or effect.runic:
                    # 捐糧（記貢獻）與符文殘片自己不看陣營：只准寫在晉升奇遇（召見只發給自己陣營的人），或事件／選項的條件寫了
                    # factions 的地方，沒投靠的人、別的陣營的人才領不到（丙二審查）
                    reachable = event.id in promo_events or bool(event.condition.factions) or bool(choice.condition.factions)
                    need(reachable, f"{where}：donate_grain／runic 只能寫在晉升奇遇，或條件寫了 factions 的事件、選項"
                                    "（不然散人與別的陣營的人也領得到貢獻與殘片）")
                if effect.promote is not None:
                    need(2 <= effect.promote <= 4, f"{where}：promote 要在 2～4 之間（第 2 到 4 階），寫了 {effect.promote}")
                    ranks_here = leg_ranks.get(event.id)
                    need(not ranks_here or effect.promote in ranks_here,
                         f"{where}：promote 要寫 {'、'.join(str(r) for r in sorted(ranks_here or ()))}"
                         f"（這一則在那一階的 legs 裡），寫了 {effect.promote}")
                if effect.summons_next is not None:
                    if effect.summons_next != event.id:
                        need(False, f"{where}：summons_next 要寫這一則自己的 id")
                    else:
                        need(event.id in unfinished, f"{where}：summons_next 只能寫在晉升奇遇的最後一段以前（最後一段演完就是晉升）")
                if effect.patron is not None:
                    need(event.id in promo_events, f"{where}：patron 只能寫在晉升奇遇（promotions.json 的事件）")
                for mod in effect.event_mods:
                    need(mod.event in timetable_ids, f"{where}：event_mods 的 {mod.event} 不在時刻表")
                    need(mod.event not in timetable_ids or mod.event in rolled,
                         f"{where}：event_mods 的 {mod.event} 不是擲骰的大事（固定、決戰、季末沒有成功率可改）")


def check_opportunities(c: Content, need, known, front_ids: list[str]) -> None:
    """機緣（content/opportunities.json、orders.json 的 rank2，正式版乙一）：id 不重複；陣營存在；kind 對應的那一塊要寫、
    別的不能寫；人物、地點、大區、戰線存在；累積型的來源行動（第 2 階行動、守勢行動）自己陣營要有；有東西要送的天時地利型
    要寫送的選項與送到的那一句；文字只能繁體。front_ids 是 validate 的那一份戰線清單。
    乙二：拼圖型（拿法寫全、東西與處的 key 不重複、官軍交給誰與豪強的靠山）、推理型（天機存在、嫌疑人剛好是那個天機的候選、
    每個嫌疑人的特徵都有片段）、集體密謀型（每一處寫 front 或 at、跟 how 一致、need_parts 不超過處數）；請命的陣營與人物存在。"""
    from tianxia.core import omen_base  # noqa: PLC0415  軍情第 34 批：天機表在核心的 omen_base（原本延後 import foreshadow）

    ids = [o.id for o in c.opportunities]
    need(len(set(ids)) == len(ids), "opportunities.json：機緣 id 重複")
    factions = {f.id for f in c.scenario.factions}
    regions = {r.id for r in c.map.regions}
    trend_ids = {t.id for t in c.scenario.trends}
    derived_ids = {t.id for t in c.scenario.trends if t.derived}  # 衍生線（開關開著時由戰線合成的黃巾聲勢）
    for o in c.opportunities:
        where = f"機緣 {o.id}"
        need(o.faction in factions, f"{where}：沒有陣營 {o.faction}")
        blocks = {"bond": o.bond, "accumulate": o.accumulate, "timing": o.timing,
                  "puzzle": o.puzzle, "deduce": o.deduce, "plot": o.plot}
        need(blocks[o.kind] is not None, f"{where}：kind 是 {o.kind}，要寫 {o.kind} 那一塊")
        need(all(v is None for k, v in blocks.items() if k != o.kind), f"{where}：只能寫 {o.kind} 那一塊")
        texts = [o.name]
        if o.bond is not None:
            known(where, [o.bond.character], c.characters, "人物")
            texts += [o.bond.topic, o.bond.text]
        if o.accumulate is not None:
            a = o.accumulate
            need(a.source != "rank2" or o.faction in c.orders.rank2, f"{where}：來源是第 2 階行動，這個陣營卻沒有（orders.json 的 rank2）")
            need(a.source != "duty" or o.faction in c.orders.duties, f"{where}：來源是守勢行動，這個陣營卻沒有（orders.json 的 duties）")
            texts += [a.tick, a.milestone, a.item, a.label, a.done]
        if o.timing is not None:
            t = o.timing
            known(where, t.at + [h.at for h in t.hosts], c.locations, "地點")
            known(where, [h.figure for h in t.hosts], c.figures, "人物")
            need(all(r in regions for r in t.clue_regions), f"{where}：clue_regions 有不存在的大區")
            need(t.deliver_front is None or t.deliver_front in front_ids, f"{where}：deliver_front {t.deliver_front} 不是戰線")
            need(t.when != "night" or bool(t.at), f"{where}：夜裡要寫地點")
            need(t.when != "dawn" or bool(t.hosts), f"{where}：黎明要寫主持人")
            need((t.item is None) == (t.deliver_front is None), f"{where}：item 與 deliver_front 要一起寫")
            need(t.item is None or bool(t.deliver_label.strip()), f"{where}：有 item 就要寫 deliver_label（交東西的選項）")
            need(t.item is None or bool(t.done.strip()), f"{where}：有 item 就要寫 done（交到那一刻的敘事）")
            texts += [t.clue, t.label, t.ok, t.fail, t.deliver_label, t.done] + ([t.item] if t.item else [])
        if o.puzzle is not None:
            keys = [piece.key for piece in o.puzzle.pieces]
            need(bool(keys), f"{where}：拼圖至少要有一樣東西")
            need(len(set(keys)) == len(keys), f"{where}：東西 key 重複")
            for piece in o.puzzle.pieces:
                need(piece.how != "ask" or (piece.front is not None and piece.figure is not None and piece.topic),
                     f"{where}：{piece.key} 是 ask，要寫 front、figure、topic")
                need(piece.how != "ask" or "*" in piece.lines, f"{where}：{piece.key} 的 lines 要有 \"*\"（沒列到的人說的那一句）")
                need(piece.how == "ask" or piece.at is not None, f"{where}：{piece.key} 要寫 at")
                need(piece.how != "check" or piece.check is not None, f"{where}：{piece.key} 是 check，要寫 check")
                known(where, [piece.front] if piece.front else [], front_ids, "戰線")
                known(where, [piece.at] if piece.at else [], c.locations, "地點")
                known(where, [k for k in piece.lines if k != "*"] + ([piece.figure] if piece.figure else []), c.figures, "人物")
                texts += [piece.name, piece.topic, piece.label, piece.ok, piece.fail] + list(piece.lines.values())
            pr = o.puzzle.present
            need(pr.at is not None or bool(pr.patrons), f"{where}：交給誰要寫 at 或 patrons")
            need(pr.at is None or pr.figure is not None, f"{where}：官軍的交付要寫 figure")
            known(where, [pr.at] if pr.at else [], c.locations, "地點")
            known(where, [pr.figure] if pr.figure else [], c.figures, "人物")
            known(where, [x.character for x in pr.patrons.values()], c.characters, "人物")
            known(where, [x.at for x in pr.patrons.values()], c.locations, "地點")
            texts += [pr.stand_in, pr.label, pr.done] + [x.done for x in pr.patrons.values()]
        if o.deduce is not None:
            d = o.deduce
            need(d.tianji in omen_base.TIANJI, f"{where}：天機 {d.tianji} 不存在")
            need({s.id for s in d.suspects} == set(omen_base.TIANJI.get(d.tianji, ())),
                 f"{where}：嫌疑人要跟天機 {d.tianji} 的候選一樣")
            keys = {t.key for t in d.traits}
            need(all(set(s.traits) <= keys for s in d.suspects), f"{where}：嫌疑人有沒寫片段的特徵")
            need(all(t.region in regions for t in d.traits), f"{where}：特徵有不存在的大區")
            need(bool(d.askers), f"{where}：至少要有一位指認的人")
            known(where, [h.figure for h in d.askers], c.figures, "人物")
            known(where, [h.at for h in d.askers], c.locations, "地點")
            known(where, list(d.trend), trend_ids, "大勢線")  # 指對了推哪條線（戰線；衍生線不能直接推）
            need(not set(d.trend) & derived_ids, f"{where}：trend 不能推衍生線（要推就推它的來源線）")
            texts += [d.label, d.right, d.wrong] + [s.name for s in d.suspects] + [t.text for t in d.traits]
        if o.plot is not None:
            pl = o.plot
            keys = [x.key for x in pl.parts]
            need(bool(keys), f"{where}：集體密謀至少要有一處")
            need(len(set(keys)) == len(keys), f"{where}：各處的 key 重複")
            need(pl.how != "check" or pl.check is not None, f"{where}：check 類要寫 check")
            need(all((x.front is None) != (x.at is None) for x in pl.parts), f"{where}：每一處寫 front 或 at 其中一個")
            need(pl.how != "win" or all(x.front is not None for x in pl.parts), f"{where}：win 類每一處都要寫 front")
            need(pl.how != "check" or all(x.at is not None for x in pl.parts), f"{where}：check 類每一處都要寫 at")
            known(where, [x.front for x in pl.parts if x.front], front_ids, "戰線")
            need(pl.need_parts is None or 0 < pl.need_parts <= len(pl.parts), f"{where}：need_parts 超出處數")
            known(where, [x.at for x in pl.parts if x.at], c.locations, "地點")
            texts += [pl.part_label, pl.part_ok, pl.part_fail, pl.start_text, pl.done_text, pl.helper_text,
                      pl.fail_text] + [x.name for x in pl.parts]
        for text in texts:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    for faction_id, action in c.orders.rank2.items():
        need(faction_id in factions, f"orders.json rank2：沒有陣營 {faction_id}")
        for text in (action.name, action.ok, action.fail):
            need(to_traditional(text) == text, f"orders.json rank2.{faction_id}：文字只能用繁體中文（「{text[:12]}」）")
    # 第 3、4 階的行動（正式版戊一）：id 不重複、陣營存在、標籤是某個地點真的帶的（拼錯的那個行動哪裡都不會出現）、檢定的屬性認得、
    # 有檢定就要寫沒過的那一句。標籤不看地點在不在戰線上：validate 遇到壞掉的大區多邊形還會繼續跑，atlas.region_of 會丟 ValueError
    rank_action_ids = [a.id for a in c.orders.rank_actions]
    need(len(set(rank_action_ids)) == len(rank_action_ids), "orders.json rank_actions：id 重複")
    place_tags = {t for loc in c.locations.values() for t in loc.tags}
    for a in c.orders.rank_actions:
        where = f"orders.json rank_actions.{a.id}"
        need(a.faction in factions, f"{where}：沒有陣營 {a.faction}")
        need(bool(a.id) and ":" not in a.id, f"{where}：id 不能是空的、也不能有冒號（選項是 act:rank:<id>，軍令記功的 kind 也是它）")
        need(set(a.tags) <= place_tags, f"{where}：tags 裡有的標籤，沒有任何地點帶：{sorted(set(a.tags) - place_tags)}")
        need("{地點}" in a.ok, f"{where}：ok 要寫 {{地點}}（成功的那一句要說在哪裡）")
        if a.check is not None:
            known(where, [a.check.stat], STATS, "屬性")
        need(a.check is None or bool(a.fail.strip()), f"{where}：有檢定就要寫 fail（沒過的那一句）")
        for text in (a.name, a.ok, a.fail):
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    for faction_id, petition in c.orders.petition.items():
        need(faction_id in factions, f"orders.json petition：沒有陣營 {faction_id}")
        known(f"orders.json petition.{faction_id}", petition.characters, c.characters, "人物")
        need(to_traditional(petition.label) == petition.label, f"orders.json petition.{faction_id}：文字只能用繁體中文（「{petition.label[:12]}」）")


def check_foreshadows(
    c: Content, need, known, region_ids: list[str], front_ids: list[str], counters_written: dict[str, str],
) -> None:
    """伏筆（content/foreshadows.json，計畫 T7）：鏈的大事在時刻表上、陣營在劇本裡；片段的大區是大區、事件與人物存在；
    最後一步的地點、物品、人物存在，答案是選項之一或 tianji:<天機>（天機的選項要剛好是候選）；文字只用繁體中文。
    伏筆計數：效果寫的要有鏈讀，鏈讀的要有效果寫（官銀由 guanyin 的規則寫）。"""
    from tianxia.core.omen_base import FIGURE_SLOT, GUANYIN, TIANJI, TIANJI_ANSWER, asks_of, trips  # noqa: PLC0415  軍情第 34 批：核心的 omen_base

    fs = c.foreshadows
    faction_ids = [f.id for f in c.scenario.factions]
    item_ids = [item.id for item in fs.items]
    chain_ids = [ch.id for ch in fs.chains]
    for label, ids in (("伏筆物品", item_ids), ("伏筆", chain_ids)):
        duplicated = sorted({x for x in ids if ids.count(x) > 1})
        need(not duplicated, f"{label} id 重複：{'、'.join(duplicated)}")
    events = {e.id: e for e in c.timetable}

    check_text = functools.partial(_check_traditional, need)

    for item in fs.items:
        need(bool(item.name.strip()), f"伏筆物品 {item.id}：name 不能是空的")
        check_text(f"伏筆物品 {item.id}", item.name)

    counters_read: set[str] = set()
    items_read: set[str] = set()

    def check_requires(where: str, req, top: bool = True) -> None:
        known(where, req.clue_items, item_ids, "伏筆物品")
        items_read.update(req.clue_items)
        known(where, req.affinity, c.characters, "人物")
        for key in req.donations:
            loc, sep, kind = key.partition(":")
            need(bool(sep and kind), f"{where}：捐獻 {key!r} 要寫成「據點 id:種類」")
            known(where, [loc], c.locations, "地點")
        counters_read.update(req.counters)
        amounts = [*req.clue_items.values(), *req.donations.values(), *req.affinity.values(), *req.counters.values()]
        need(req.grain >= 0 and all(n >= 0 for n in amounts), f"{where}：條件的數量不能是負的")
        need(top or req.check is None, f"{where}：檢定不能寫在 any_of 裡")
        for sub in req.any_of:
            check_requires(where, sub, top=False)

    def check_wrong(where: str, wrong) -> None:
        known(where, wrong.lose_items, item_ids, "伏筆物品")
        known(where, wrong.affinity, c.characters, "人物")
        check_text(where, wrong.text)

    def check_ask(where: str, ask) -> None:
        option_ids = [o.id for o in ask.options]
        need(len(set(option_ids)) == len(option_ids), f"{where}：選項 id 重複")
        check_text(where, ask.question)
        for o in ask.options:
            check_text(where, o.text)
            if o.wrong is not None:
                check_wrong(f"{where} 選項 {o.id}", o.wrong)
        if ask.answer.startswith(TIANJI_ANSWER):
            key = ask.answer.removeprefix(TIANJI_ANSWER)
            known(where, [key], TIANJI, "天機")
            if key in TIANJI:
                need(
                    sorted(option_ids) == sorted(TIANJI[key]),
                    f"{where}：天機 {key} 的選項要剛好是{'、'.join(TIANJI[key])}（寫的是{'、'.join(option_ids)}）",
                )
        else:
            need(ask.answer in option_ids, f"{where}：答案 {ask.answer} 不是選項之一，也不是 tianji:<天機>")

    for ch in fs.chains:
        where = f"伏筆 {ch.id}"
        known(where, [ch.event], events, "時刻表大事")
        known(where, [ch.side], faction_ids, "陣營")
        # 豪強第三方的鏈 2026-10-31 拿掉（T-05）：鏈只能是會鎖定大事的兩方
        need(ch.side in TIMETABLE_SIDES, f"{where}：side 只能是 guan 或 huang（寫的是 {ch.side}；豪強第三方的鏈已經拿掉）")
        event = events.get(ch.event)
        versions = set(event.versions.values()) if event is not None else set()
        if ch.front is not None:
            known(where, [ch.front], front_ids, "戰線")  # 戰線 id，不是大區（同時刻表）
        need(
            ch.front is not None or event is None or event.front is not None,
            f"{where}：要寫 front（{ch.event} 沒有戰線，最後一步的戰況看不到任何一條線）",
        )
        if event is not None and event.kind != "showdown" and ch.side in TIMETABLE_SIDES:  # 決戰的結果由 T8 給鍵
            need(ch.side in event.lock_result, f"{where}：{ch.event} 的 lock_result 沒有 {ch.side}，鎖定了也改不了結果")
        if ch.invalid_if.figure_out is not None:
            known(where, [ch.invalid_if.figure_out], c.characters, "人物")
        for i, f in enumerate(ch.fragments):
            fw = f"{where} 片段{i + 1}"
            known(fw, [f.region], region_ids, "大區")
            check_text(fw, f.text)
            for text in f.versions.values():
                check_text(fw, text)
            known(fw, f.versions, versions, "版本")
            if f.source == "event":
                need(f.event is not None, f"{fw}：來源是 event 就要寫 event")
                if f.event is not None:
                    known(fw, [f.event], c.events, "事件")
            else:
                need(f.event is None, f"{fw}：只有來源是 event 的才寫 event")
            if f.source == "talk":
                need(f.character is not None and bool(f.topic.strip()), f"{fw}：來源是 talk 就要寫 character 與 topic")
                speakers = [x for x in (f.character, f.stand_in) if x is not None]
                known(fw, speakers, c.characters, "人物")
                for fid in speakers:  # 對話得找得到人：要有對話的地方（talk_at）而且能深度對話
                    who = c.characters.get(fid)
                    need(
                        who is None or (who.talk_at is not None and who.deep_interaction),
                        f"{fw}：{fid} 沒有 talk_at（或不能深度對話），這一則永遠聽不到",
                    )
                check_text(fw, f.topic)
            else:
                need(
                    f.character is None and f.stand_in is None and not f.topic and f.affinity_min == 0,
                    f"{fw}：只有來源是 talk 的才寫 character、stand_in、topic、affinity_min",
                )
        final = ch.final
        if final.steps:
            need(final.location is None, f"{where}：寫了 steps 就不要在 final 上寫 location（每一趟各寫各的）")
            need(
                not (final.question or final.options or final.answer or final.then or final.label),
                f"{where}：寫了 steps 就把 label、題目寫在每一趟裡",
            )
        else:
            need(final.location is not None, f"{where}：最後一步要寫 location（或寫 steps）")
        check_requires(f"{where} 最後一步", final.requires)
        seen: set[str] = set()
        for i, trip in enumerate(trips(final)):
            tw = f"{where} 第 {i + 1} 趟" if final.steps else f"{where} 最後一步"
            if trip.location is not None:
                known(tw, [trip.location], c.locations, "地點")
                need(trip.location not in seen, f"{where}：兩趟不能在同一個地點（{trip.location}）")
                seen.add(trip.location)
            else:
                need(not final.steps, f"{tw}：每一趟都要寫 location")
            need(bool(trip.label.strip()), f"{tw}：要寫 label（選單上的字）")
            if trip is not final:
                check_requires(tw, trip.requires)
            need(
                bool(trip.question) or (not trip.options and trip.answer is None and not trip.then),
                f"{tw}：有選項、答案或追問就要寫 question",
            )
            need(not trip.question or bool(trip.options), f"{tw}：題目要有選項")
            need(not trip.question or trip.answer is not None, f"{tw}：題目要有答案（answer）")
            check_wrong(tw, trip.wrong)
            for text in (trip.label, trip.unready, trip.success_text):
                check_text(tw, text)
        for aw, ask in asks_of(ch):
            if ask.options:  # 沒有選項的題上面已經報了
                check_ask(f"{where} {aw}", ask)
        need(bool(final.success_text.strip()), f"{where}：要寫 success_text（完成時的敘事）")
        check_text(where, final.success_text)
        for text in final.success_versions.values():
            check_text(where, text)
        known(where, final.success_versions, versions, "版本")
        known(where, [x for x in (final.figure, final.stand_in) if x is not None], c.characters, "人物")
        texts = [final.success_text, *final.success_versions.values(), *(step.success_text for step in final.steps)]
        uses_figure = any(FIGURE_SLOT in text for text in texts)
        need(final.figure is not None or not uses_figure, f"{where}：用了 {FIGURE_SLOT} 就要寫 figure")
        if final.window == "during_muster":
            need(event is None or event.kind == "showdown", f"{where}：window 是 during_muster 的只能用在決戰（{ch.event} 不是）")

    rule = fs.guanyin
    if rule is not None:
        known("伏筆的官銀", [rule.side, rule.squad_faction], faction_ids, "陣營")
        known("伏筆的官銀", rule.regions, region_ids, "大區")
        check_text("伏筆的官銀", rule.text)
        counters_written.setdefault(GUANYIN, "伏筆的官銀")
    for key, where in sorted(counters_written.items()):
        need(key in counters_read, f"{where}：伏筆計數 {key} 寫了卻沒有任何一條鏈讀它")
    for item_id in item_ids:
        need(item_id in items_read, f"伏筆物品 {item_id}：沒有任何一條鏈的條件讀它")
    for key in sorted(counters_read - set(counters_written)):
        need(False, f"伏筆計數 {key}：有鏈讀它，卻沒有任何效果（或官銀的規則）寫它")
