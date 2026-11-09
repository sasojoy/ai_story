"""陣營包：玩法說明「投靠與軍令」「各陣營有什麼不同」兩節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from collections.abc import Sequence

from tianxia import allied as allied_rules
from tianxia import calendar, conquest, rules, territory
from tianxia.core.howto_base import SOME_PLACES
from tianxia.core.howto_base import order_pushers as _order_pushers
from tianxia.core.howto_base import section as _section
from tianxia.models import Content
from tianxia.rules import STANCE_NAMES  # 態勢卡上三方的叫法（官軍、黃巾、豪強）：說明跟卡上同一個叫法
from tianxia.state import WorldState

CONQUEST_JOIN = "在官軍、黃巾的領地與中立地出陣：別人的地方打贏把那一塊的進度往你那一邊推，自家的地方守一回、推一半"
# 約戰開著（減法季批 3b；FB-857）：沒有零風險的守，出陣是貼約戰、守就是應戰；取代上面那一句（sortie_duel.on 的季）。待 joy 潤
CONQUEST_JOIN_DUEL = "在官軍、黃巾的領地與中立地出陣：別人的地方、中立地封好三招貼約戰，打贏把那一塊的進度往你那一邊推，自家的地方等對面來約、應戰守住了把進度拉回來"


# ── 投靠、軍令與三方（explain-2 第二項）──────────────────────────────


def _place_names(content: Content, ids: Sequence[str]) -> str:
    return "、".join(content.locations[i].name for i in ids if i in content.locations)


def join_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「投靠與軍令」那一節：投靠（劇本有陣營才寫）；軍令、晉升、叛投只在第一季（orders、ranks、defection 都掛在開關後面）。"""
    cfg = content.config
    if not content.scenario.factions:
        return []
    allied = rules.haoqiang_allied(content, season)  # 豪強分屬兩軍的季：豪強先挑依附哪一邊、算那一邊的人（新寫）
    gentry_on = allied_rules.gentry_on(content, season)  # 拿掉豪強的季（企劃者 2026-11-07）：不寫豪強那幾句
    # FB-112：推線只說有些地方；散人與不是交戰兩軍的陣營（地方豪強，Joy 2026-10-13）可以在決戰的大區臨時投效兩軍之一，
    # 只算那一場（Game._free_agent、_enlist_options；不進投靠名冊、不算叛投）。決戰的職位這一版不寫（控制者裁示：戰鬥那條線還在改，戰場上本來就寫著）
    gentry = ("" if not gentry_on else "地方豪強要先挑依附官軍或黃巾，算那一邊的人，決戰也站那一邊。" if allied
              else "陣營不是交戰的兩軍時，跟散人一樣臨時投效。")
    lines = [
        "**投靠**：在陣營收人的地方按「投靠」，要再確認一次；也可以拜入陣營名下的門派。投靠之後，"
        f"{(CONQUEST_JOIN_DUEL if conquest.duel_on(content, season) else CONQUEST_JOIN) if territory.on(content) else SOME_PLACES + '，推向你那一邊，遇上自己陣營的隊伍是操練'}"
        "；全服決戰替自己的陣營出戰，"
        f"{gentry}"
        "散人照樣能玩，只是沒有軍令與晉升；遇上決戰，人到了決戰的大區，可以臨時投效交戰兩軍之一，只算那一場，打完照樣是散人。",
    ]
    if not calendar.season_one_on(season, content):
        return lines
    from tianxia import orders  # noqa: PLC0415  orders → timetable、figures：只有第一季的這幾行用到

    kinds = "、".join(orders.KIND_NAMES.values())
    # 湊滿額度那一刻的效果照 orders.json（FB-112：打擊不推線，是挫大勢人物的聲威）
    pushing = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES if any(t.kind == k and t.effect.trend > 0 for t in content.orders.templates)]
    denting = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES
               if any(t.kind == k and t.effect.figure_prestige < 0 for t in content.orders.templates)]
    effects = [f"{'、'.join(pushing)}推一把戰況"] if pushing else []
    effects += [f"{'、'.join(denting)}挫大勢人物的聲威"] if denting else []
    met = f"全陣營湊滿額度的那一刻一起見效（{'，'.join(effects)}）" if effects else "全陣營湊滿額度的那一刻一起見效"
    lines += [
        # 軍令每天一道的季（21 天季、7 天濃縮季）：「每天發令」「今日的軍令卡」（calendar.week_word，FB-501、FB-502）
        f"**軍令**：{calendar.week_word('order_each', content, season)}發令（{kinds}，各陣營拿到的不一樣），照做一次記一次功；{met}。"
        f"{calendar.week_word('order_this', content, season)}的軍令卡在江湖頁行動列底下。",
        f"**晉升**：替陣營出力記貢獻（推 1 點戰況記 {cfg.contrib_per_push}），到 {cfg.rank2_contrib} 會有人召見，去應召就晉升；"
        f"自己陣營的大勢人物，你每晉升一階，求見他的門檻就低 {cfg.audience_rank_discount}。"
        + (f"地方豪強最多做到第 {allied_rules.CAP_RANK} 階。" if gentry_on else ""),
        "**叛投**：一季一次，到別的陣營收人的地方叛投；晉升、召見、部下、這一季的貢獻歸零，屬性、武學、同伴、銀兩不動。"
        + ("換依附的一邊、豪強與同一邊的官軍或黃巾互換，也算叛投。" if gentry_on else ""),
    ]
    return lines


def faction_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「三方有什麼不同」：每個陣營在哪裡投靠、往哪裡推、拿得到哪幾種軍令、守勢與晉升之後多的行動、頭銜。
    全照內容（劇本的陣營與目標、orders.json 的軍令範本、守勢行動、第 2 階行動、第 3、4 階行動）與 ranks.TITLES；第一季才有。"""
    if not calendar.season_one_on(season, content) or not content.scenario.factions:
        return []
    from tianxia import orders, ranks  # noqa: PLC0415  第一季的這一節才用到

    fronts = set(rules.front_ids(content))
    pushers = _order_pushers(content)
    out = []
    for faction in allied_rules.factions_of(content, season):  # 拿掉豪強的季只寫官軍、黃巾
        fid = faction.id
        goals = faction.goals
        pushed = {d for key, d in goals.items() if key in fronts}
        if faction.allies:  # 豪強分屬兩軍：豪強那一列另寫
            titles = [t for t in ranks.TITLES.get(fid, []) if t][:allied_rules.CAP_RANK]
            where = _place_names(content, faction.join_at)
            head = f"**{faction.name}**" + (f"（在{where}投靠）" if where else "")
            sides = "或".join(a.name for a in allied_rules.allies_of(content, fid))
            duty = content.orders.duties.get(fid)
            acts = [f"在戰線上的差事是「{duty.name}」"] if duty is not None else []
            acts += [f"第 {a.rank} 階起多「{a.name}」" for a in sorted(content.orders.rank_actions, key=lambda a: a.rank)
                     if a.faction == fid and a.rank <= allied_rules.CAP_RANK]
            title = f"；頭銜從{titles[0]}做到{titles[-1]}（第 {allied_rules.CAP_RANK} 階為止）" if len(titles) > 1 else ""
            out.append(f"{head}：依附{sides}，照那一邊推戰線、接那一邊的軍令；{'，'.join(acts) or '沒有額外的行動'}{title}。")
            continue
        if pushed:
            side = STANCE_NAMES["guan"] if pushed == {-1} else STANCE_NAMES["huang"] if pushed == {1} else "各自"
            aim = f"把戰線往{side}那一邊推"
        else:
            aim = "照地方本來的方向推"
        kinds = [orders.KIND_NAMES[k] for k in orders.KIND_NAMES if any(t.kind == k and t.side == fid for t in content.orders.templates)]
        orders_text = (f"軍令只有{kinds[0]}" if len(kinds) == 1 else f"軍令有{'、'.join(kinds)}") if kinds else "沒有軍令"
        if kinds and fid not in pushers:  # 豪強只有打擊：湊滿額度是挫大勢人物的聲威，不推線（FB-112）
            orders_text += "，不推戰線"
        acts = []
        duty = content.orders.duties.get(fid)
        if duty is not None:
            acts.append(f"在戰線上的差事是「{duty.name}」")
        rank2 = content.orders.rank2.get(fid)
        if rank2 is not None:
            acts.append(f"第 2 階起多「{rank2.name}」")
        acts += [f"第 {a.rank} 階起多「{a.name}」" for a in sorted(content.orders.rank_actions, key=lambda a: a.rank) if a.faction == fid]
        titles = [t for t in ranks.TITLES.get(fid, []) if t]
        title = f"；頭銜從{titles[0]}做到{titles[-1]}" if len(titles) > 1 else ""
        where = _place_names(content, faction.join_at)
        head = f"**{faction.name}**" + (f"（在{where}投靠）" if where else "")
        out.append(f"{head}：{aim}。{orders_text}；{'，'.join(acts) or '沒有額外的行動'}{title}。")
    return out


def join_section(content: Content, season: WorldState) -> list[str]:
    """「投靠與軍令」那一節（HOWTO_ORDER 的 join）。"""
    return _section("投靠與軍令", join_lines(content, season))


def factions_section(content: Content, season: WorldState) -> list[str]:
    """「各陣營有什麼不同」那一節（factions）。"""
    return _section("各陣營有什麼不同", faction_lines(content, season))
