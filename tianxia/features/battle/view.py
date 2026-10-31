"""全服決戰「看」那一半（主動搬六包第 5 批）：原本 Game 上的 31 個方法，本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3），
包裡互相叫直接叫函式，模組層的字在 rules.py；「打」那一半（集結、投效、挑同伴、推進、結算、攻城、管理者——還在 Game，第 6～8 批搬）與別的功能
一律經 ctx.<名>（tianxia/core/services.py 的清單：測試換掉的 Game 方法才打得到）。Game 留 22 個一行委派（server、核心原位、測試在叫），
另外 9 個只有這裡叫。

- 場景：battle_scene_text（集結中、開打的畫面）、chief_lines（龍頭上陣）、round_blocks／fold_war_lines（一回合一段、一軍的戰法摺成一列）、
  idle_note（掛機）、battle_spotlight（點名與顯眼）、round_wait（已送出／在場）、escort_line（隨你出陣的同伴）、watch_text（只能觀戰的原因）
- 戰局條與攻城條：gauge_of、battle_gauge、siege_banner、record_gauge（戰報頁）、card_gauge（「剛剛」那張卡片）、battle_on_screen
- 收場補送：deliver_battle_results、restore_showdowns（補回被洗掉的戰報）、showdown_lines、file_showdown、annal_showdown（行狀）、
  showdown_pay（軍餉）、showdown_credits、showdown_tier4（時刻表決戰得勝的四階料）
- 放手一搏：battle_free_text_prompt、battle_free_text_note、battle_text_check、battle_text_request（鎖外三段式的 A 段）、
  submit_battle_custom_action（C 段）
- 補劇情：battle_tale_request（A 段）、apply_battle_tales（C 段）、tale_battles——鎖外的 B 段與背景執行緒照舊在 server（戰記線不動）
"""
from __future__ import annotations

import random

from tianxia import calendar, gender, journal, team
from tianxia import annals  # 過渡：待搬（行狀）
from tianxia import battle_instance, battlelog, tactics  # 過渡：待搬（戰鬥規則核心；共用規則層的名單第 15 批登記）
from tianxia import conquest, siege  # 過渡：待搬（地盤、攻城）
from tianxia import cultivation, four_tiers, materials, mounts, renown, roster  # 過渡：待搬（絕學的契機、四階料、素材、坐騎、名聲、同伴）
from tianxia import figure_life, front_lines, generals, seal, wins  # 過渡：待搬（人物風聞、戰線、龍頭上陣、玉璽、三陣營四勝利）
from tianxia import prologue as prologue_rules  # 過渡：待搬（序章；照 engine 的叫法）
from tianxia.core.services import PAUSED_TEXT
from tianxia.models import MOVES, BattleDef
from tianxia.rules import can_draw_side_change, front_text, resolve_trends, season_one
from tianxia.state import BattleRecord, JournalEntry

from . import rules


def escort_line(ctx, e: battle_instance.Escort) -> str:
    """決戰畫面上自己的那一位（別人的不列，第五節「讀得下去」）。"""
    if e.fallen_round is not None:
        return rules.ESCORT_FELL.format(name=e.name)
    return rules.ESCORT_SCENE.format(name=e.name, hp=round(e.neili), cap=round(e.neili_cap))


def deliver_battle_results(ctx) -> None:
    """收場的全服決戰補送到自己手上（FB-027）：自己的名號在參戰名單上（含下線的、中途倒下的；觀戰的不在名單上）、
    還沒補過的，每一場寫一則江湖紀錄、加一筆戰報。

    為什麼是「下次同步時補」、不是收場那一下去改每個參戰者的角色：那會在一筆交易裡改幾十列，而且跟伺服器、假人
    程式記憶體裡各自的 Game 打架（它們之後存檔會把別人寫進去的蓋掉）。資料庫是唯一的真實來源，戰鬥也一直留在
    battles 表裡，所以每個人自己的 Game 在 sync（伺服器每個請求、假人每一輪）與自己收場的那一下自己補。
    不分季別：決戰的結果常常就把季收掉，休季、下一季才回來的人也要補到。不是自己參戰的那幾場也記成處理過，
    之後不必再讀（收場的決戰名單不會再變）。只讀處理過的最大流水號之後收場的：決戰照開戰的先後收場，比它小的
    不會再有新收場的（見 WorldStateStore.ended_battles）。季終沒打完就收起來的決戰（unfinished）也在這裡補，
    內容只是一則「不算勝負」的江湖紀錄（FB-035，見 _file_showdown）。"""
    p = ctx.state.player
    restore_showdowns(ctx)
    seen = p.battle_results_seen
    # 攻城戰跟決戰、別的攻城戰同時打（領地爭奪第二批）：先開的可能晚收場，往回讓 RESULT_LOOKBACK 場、補過的用流水號跳過
    fresh = ctx.world.ended_battles(after=max(0, max(seen, default=0) - rules.RESULT_LOOKBACK), skip=set(seen))
    if not fresh:
        return
    current = ctx.world.get_season_number()
    for season, battle in fresh:
        me = battle.participants.get(p.name)
        if me is not None:
            file_showdown(ctx, battle, me, None if season == current else season)
        p.battle_results_seen.append(battle.record_id)


def restore_showdowns(ctx) -> None:
    """補回被洗掉的決戰戰報（PM 2026-10-14：以前決戰跟遊歷共用最近 20 場，收場兩小時就被十幾場遊歷擠掉）：這一季收場、自己參戰過、
    已經補過（battle_results_seen）卻不在戰報裡的決戰，照 battles 表重建一筆（_showdown_lines 那幾句與完整戰況）。只補戰報：
    軍餉、名望、江湖紀錄、行狀當時都發過了，不再發、不寫紀錄、不放「剛剛」的卡片。一季只查一次（showdowns_restored）。"""
    c, s, p = ctx.content, ctx.state, ctx.state.player
    season = ctx.world.get_season_number()
    if p.showdowns_restored == season:
        return
    p.showdowns_restored = season
    seen = set(p.battle_results_seen)
    have_refs = {r.battle_ref for r in s.battles if r.kind in battlelog.SHOWDOWN_KINDS}
    have_old = {(r.event, r.time): r for r in s.battles if r.kind == "showdown"}  # 這一版以前的戰報沒有 battle_ref：照戰名與收場時刻認
    added = False
    for battle in ctx.world.season_ended_battles(season):
        me = battle.participants.get(p.name)
        definition = ctx._definition_of(battle)
        if me is None or definition is None or battle.unfinished or battle.record_id not in seen or battle.record_id in have_refs:
            continue
        time = battle.end_time if battle.end_time is not None else s.world.time
        if (definition.name, time) in have_old:  # 還留著的舊戰報：補上 battle_ref，戰報頁就照 battles 表畫完整戰況
            kept = have_old[(definition.name, time)]
            kept.battle_ref = kept.battle_ref if kept.battle_ref is not None else battle.record_id
            continue
        sides = battle_instance.side_names(battle, definition)  # 守將那一格寫守軍（FB-540）
        side = sides.get(me.faction, me.faction)
        foes = "、".join(n for fid, n in sides.items() if fid != me.faction) or "敵軍"
        lines, *_ = showdown_lines(ctx, battle, me, side, sides)
        s.battle_seq += 1
        s.battles.append(BattleRecord(
            id=s.battle_seq, time=time, location=ctx._battle_region_name(definition) if definition.region else definition.name,
            kind="siege" if battle.siege is not None else "showdown", event=definition.name, opponent=foes, ours=[], tier=battle.outcome_title or "收場", our_power=0.0,
            difficulty=0.0, side=side, notes=[*lines, rules.RESTORED_NOTE], gauge=gauge_of(ctx, battle, definition, me.faction),
            log=round_blocks(ctx, battle, definition, last=None, oldest_first=True, me=me), battle_ref=battle.record_id,
        ))
        added = True
    if added:
        s.battles.sort(key=lambda r: r.time, reverse=True)  # 補回來的照收場時刻排進去（sort 是穩定的：同一時刻照原本的先後）


def showdown_lines(
    ctx, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, side: str, sides: dict[str, str],
) -> tuple[list[str], str, int | None, list]:
    """決戰戰報裡跟自己有關的那幾句（結果、勝負的關鍵、職位、出手幾回合、帶頭、點名、倒下、戰功排第幾）：收場補戰報（_file_showdown）
    與補回被洗掉的戰報（_restore_showdowns）共用。回（那幾句, 職位名, 戰功名次, 名次表）。"""
    c = ctx.content
    tuning = c.config.battle
    lines = [t for t in (battle.outcome_text, battle.outcome_reason) if t]
    lines += battle.seal_notes  # 玉璽碎片：下戰書、現世的得主（5.9 最後一條、3.3）
    role = battle_instance.role_name(c.config.battle, me.role)
    lines.append(f"你以{role}出陣，出手 {me.acted_rounds} 回合" if role else f"你出手 {me.acted_rounds} 回合")
    if me.mount:
        lines.append(mounts.CAVALRY_REPORT.format(name=me.mount))  # 騎著馬出陣（裝備四欄 5.9）；原句「你以…出陣」不動
    if me.troops:
        lines.append(rules.TROOPS_REPORT.format(names=me.troops))  # 帶著部下出陣（PM 2026-10-12）
    if me.led_rounds:  # 出固定招的人也有名字（Joy 2026-10-10）
        lines.append(f"你帶頭衝陣、替自己這一邊佔了上風 {me.led_rounds} 回合")
    if me.hurt_dealt >= 0.5:
        lines.append(f"你的放手一搏點名打傷了對手，打掉他們氣血 {round(me.hurt_dealt)}")
    if me.targeted_by:
        lines.append(f"{'、'.join(me.targeted_by)}在陣上點名要對付你" + (
            f"，你被打掉氣血 {round(me.hurt_taken)}" if me.hurt_taken >= 0.5 else "，卻沒能傷到你"))
    elif me.hurt_taken >= 0.5:
        lines.append(f"你太顯眼，被對面集火，打掉氣血 {round(me.hurt_taken)}")
    if me.fell_round is not None:
        lines.append(f"你在第 {me.fell_round} 回合倒下，轉為觀戰")
    mine = battle_instance.merit(tuning, me)
    ranking = battle_instance.merit_ranking(battle, tuning, me.faction) if me.faction in sides else []  # 豪強也排（Joy 2026-10-13）
    rank = next((i for i, (q, _) in enumerate(ranking, 1) if q.name == me.name), None)
    if rank is not None:  # 個人戰功（Joy 2026-10-10）：自己這一邊排第幾、怎麼來的
        parts = "、".join(battle_instance.merit_parts(me))
        lines.append(f"你的戰功 {mine}，在{side}排第 {rank}／{len(ranking)}" + (f"（{parts}）" if parts else ""))
    return lines, role, rank, ranking


def file_showdown(
    ctx, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, earlier: int | None,
) -> None:
    """一場收場的決戰寫成自己的一則江湖紀錄與一筆戰報（kind 是 showdown），「剛剛」放這一場的卡片。
    earlier 是上一季（或更早）打的那一季的編號，這一季打的是 None：上一季的標明季別，大勢的增減寫進敘事、
    不放進數值變化——數值變化看起來像剛發生在你身上的。

    季終收兵的決戰（unfinished，FB-035）沒有結果：只寫一則江湖紀錄交代一聲，不加戰報、不放「剛剛」的戰鬥卡片。"""
    c, s = ctx.content, ctx.state
    definition = ctx._definition_of(battle)  # 攻城戰的名字是「攻城・地點」（領地爭奪第二批）
    # 自己站哪一方（臨時投效的是投效的那一軍）；單方攻中立地時守將那一格寫守軍（battle_instance.side_names，FB-540）
    sides = battle_instance.side_names(battle, definition) if definition is not None else {}
    armies = dict(sides)
    name = definition.name if definition is not None else battle.battle_id
    side = sides.get(me.faction, me.faction)
    foes = "、".join(n for fid, n in armies.items() if fid != me.faction) or "敵軍"
    where = ctx._battle_region_name(definition) if definition is not None and definition.region else name
    outcome = battle.outcome_title or "收場"
    label = "" if earlier is None else f"第 {earlier} 季・"
    time = battle.end_time if battle.end_time is not None else s.world.time
    if battle.unfinished:
        lines = [battle.unfinished_text or battle_instance.UNFINISHED_TEXT]
        lines += [f"你出手 {me.acted_rounds} 回合"] if me.acted_rounds else []
        journal.add_entry(s, JournalEntry(time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines))
        return
    lines, role, rank, ranking = showdown_lines(ctx, battle, me, side, sides)
    tuning = c.config.battle
    h = battle.highlight
    fame = 0
    highlight_changes = showdown_pay(ctx, battle, me, lines) if earlier is None else []
    if earlier is None and me.escort is not None and roster.on(c) and battle.siege is None:  # 歷史武將同行：隨你上陣的那一位回江湖了（攻城戰不放，裁決 14）
        lines += ctx._escort_home(me.escort)
    if earlier is None:
        s.player.showdowns += 1
        if h is not None and h.name == me.name and h.won and tuning.highlight_fame:  # 這一場最有戲的那一搏是自己的、而且成了
            fame += tuning.highlight_fame
            lines.append("你那一搏成了這一仗最令人印象深刻的一幕，江湖上傳開了。")
        top = battle_instance.top_merit(battle, tuning, me.faction) if me.faction in sides else None
        if top is not None and top.name == me.name:  # 這一邊的首功
            s.player.top_merits += 1
            fame += tuning.top_fame
            lines.append(f"你是{side}這一仗的首功，名字傳遍了江湖。")
        if fame:
            highlight_changes += renown.gain(s, c, "fame", fame)  # 名聲設計 3.2
        # 風聞（大勢人物擴充）：打贏的那一邊戰功前三名，那一區同一方的人物聽說了。助守中立地的守將（站的是另一軍那一格）
        # 不是替那一軍出戰，不加那一軍人物的情誼（PM 2026-10-21，FB-540）
        if (definition is not None and definition.region and battle.outcome_side == me.faction
                and rank is not None and rank <= 3 and me.faction != battle_instance.neutral_guard(battle)):
            lines += figure_life.spread(s, c, "merit", str(battle.record_id), at=None, side=me.faction,
                                        text=f"在{name}立了戰功", region=definition.region)
    rule = c.config.breakthrough
    if earlier is None and me.acted_rounds >= rule.showdown_rounds:  # 絕學的契機（方案 C）：這一季的決戰裡真的出過手
        lines += cultivation.seize(s, c, ctx.world, rule.showdown_ratio, ctx.rng)
    trends = {t.id: t.name for t in c.scenario.trends}
    moved = resolve_trends(c, s.world, battle.outcome_trend_delta)  # 開關關著時戰線都寫成黃巾聲勢
    # 第一季規則開著時，戰線與豪強割據的增減不寫數字（FB-064，同 change_trend）：這一季的是機器可讀的標籤，畫在戰鬥卡片
    # 底下、照看的人的陣營上色，戰報不收（「大勢」那一行不寫，跟遊歷的戰鬥卡片一樣）；上一季的寫進敘事，就直接是那一句話
    # （敘事沒有顏色）。其他的線、開關關著時照舊是帶正負號的數字。
    moves = {tid: d for tid, d in moved.items() if d}
    in_words = season_one(c, s.world)

    def plain(tid: str) -> str:
        return f"{trends.get(tid, tid)} {moves[tid]:+d}"

    if earlier is None:
        changes = [front_lines.mark(tid, d) if in_words and can_draw_side_change(c, tid) else plain(tid) for tid, d in moves.items()]
        record_changes = [plain(tid) for tid in moves if not (in_words and can_draw_side_change(c, tid))]
        changes += highlight_changes
        record_changes += highlight_changes
    else:
        changes, record_changes = [], []
        lines += [
            f"（第 {earlier} 季）" + (front_text(c, tid, d, str(time)) if in_words and can_draw_side_change(c, tid) else plain(tid))
            for tid, d in moves.items()
        ]
    record = BattleRecord(
        id=s.battle_seq + 1, time=time, location=f"{label}{where}", kind="siege" if battle.siege is not None else "showdown",
        event=name, opponent=foes,
        ours=[], tier=outcome, our_power=0.0, difficulty=0.0, side=side, notes=list(lines), changes=list(record_changes),
        gauge=gauge_of(ctx, battle, definition, me.faction) if definition is not None else None,
        log=round_blocks(ctx, battle, definition, last=None, oldest_first=True, me=me) if definition is not None else [],
        battle_ref=battle.record_id,
    )
    battlelog.add_record(s, record)
    s.battle_card = record.id
    journal.add_entry(s, JournalEntry(
        time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines, changes=changes,
        battle_id=record.id,
    ))
    annal_showdown(ctx, battle, me, name, side, role, rank, len(ranking), earlier, time)


def annal_showdown(
    ctx, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, name: str, side: str, role: str,
    rank: int | None, ranked: int, earlier: int | None, time: float,
) -> None:
    """一場決戰寫進行狀（玩家傳）：站哪邊、職位、出手幾回合、帶頭佔上風、首功或戰功排名、倒下、結果；每一次放手一搏另一則
    （原句、播出來的那一版劇情、成敗、點名了誰）。上一季的決戰（earlier）接在存起來的那一季後面（角色已經重來了）。"""
    c, s = ctx.content, ctx.state
    if not annals.on(c):
        return
    tuning = c.config.battle
    top = battle_instance.top_merit(battle, tuning, me.faction) if rank is not None else None
    parts = [f"{name}，你站在{side}" + (f"以{role}出陣" if role else ""), f"出手 {me.acted_rounds} 回合"]
    if me.led_rounds:
        parts.append(f"帶頭佔了 {me.led_rounds} 回合上風")
    if top is not None and top.name == me.name:
        parts.append("是這一邊的首功")
    elif rank is not None and rank <= 3:
        parts.append(f"戰功排第 {rank}／{ranked}")
    if me.fell_round is not None:
        parts.append(f"第 {me.fell_round} 回合倒下")
    parts.append(f"結果{battle.outcome_title or '收場'}")
    place = ctx._battle_region_name(c.battles[battle.battle_id]) if battle.battle_id in c.battles and c.battles[battle.battle_id].region else ""
    won = bool(battle.outcome_side) and battle.outcome_side == me.faction
    entries = [annals.entry(
        s, c, annals.SHOWDOWN, "，".join(parts) + "。", 5 if won or (top is not None and top.name == me.name) else 4,
        place=place, time=time, season=earlier is None,
    )]
    for bet in me.gambles:  # 迴圈變數原本叫 g：邊界測試把 ctx、g、game 都當成 Game 掃（搬包時唯一改了的一個名字，行為不變）
        what = f"在{name}陣上放手一搏" + ("，成了" if bet.won else "，沒成") + (f"，點名{bet.target}" if bet.target else "") + "。"
        entries.append(annals.entry(
            s, c, annals.SHOWDOWN, what, 4 if bet.won else 3, quote=bet.text, reply=bet.story, place=place, time=time, season=earlier is None,
            keep=[bet.target],  # 點名的人（參戰的玩家）的名號原樣留，沒點名是空的（FB-9020）
        ))
    if earlier is None:
        s.player.annals += entries
        annals.trim(s, c)
    else:
        for e in entries:
            ctx.world.add_saved_annal(earlier, s.player.name, e.model_dump())


def showdown_pay(
    ctx, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, lines: list[str],
) -> list[str]:
    """決戰的軍餉（Config.showdown_pay）：照個人戰功發銀兩與經驗（最多 share_cap 倍），贏的一方另加；投靠了陣營、替自己陣營出戰的人另記本季貢獻
    （照推大勢的帳）。回傳要寫在「得失」的那幾樣（「銀兩 +N」的慣例），升級的話照 add_exp 的訊息接在 lines 後面。
    天命之爭得天命的那一軍：銀兩與經驗 × Config.seal.mandate.pay_scale、名望 +fame（貢獻不加倍，玉璽二）。
    序章裡的人不發（FB-113）：修好之前在序章裡投效、出手的新人，以前 1 級大勝拿 120 經驗、序章中途升到 5 級（FB-122）。"""
    c, s = ctx.content, ctx.state
    if prologue_rules.active(s, c):
        return []
    pay, p = c.config.showdown_pay, s.player
    full = pay.full_rounds * max(1, c.config.battle.merit_points.get("acted", 0))  # 只出手 full_rounds 回合的戰功算一倍
    share = max(pay.idle_share, min(pay.share_cap, battle_instance.merit(c.config.battle, me) / full))
    won = bool(battle.outcome_side) and me.faction == battle.outcome_side
    bonus = pay.win_bonus.get(battle.outcome_margin, 0.0) if won else 0.0
    destiny = won and seal.on(c) and seal.is_mandate_battle(c, c.battles.get(battle.battle_id))  # 得天命的那一軍（8.3；要 PM 定的第 3 條；碎片關著時天命不定，不加給）
    scale = c.config.seal.mandate.pay_scale if destiny else 1
    half = c.config.conquest.pay_share if battle.siege is not None else 1.0  # 攻城戰（領地爭奪第二批）：決戰的幾成（設計 4.4）
    silver = round(pay.silver * share * (1 + bonus) * half) * scale
    exp = round(pay.exp * share * (1 + bonus) * half) * scale
    changes = []
    if destiny and c.config.seal.mandate.fame:
        changes += renown.gain(s, c, "fame", c.config.seal.mandate.fame)  # 名聲設計 3.2
    if silver:
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        changes.append(f"銀兩 +{silver}")
    if exp and team.maxed(c, p.member):  # 滿級：經驗照 5 換 1 換成心得（3.5）
        gained = team.maxed_xinde(s, c, exp, "showdown")
        if gained:
            lines.append(team.MAXED_XINDE.format(n=gained))  # 跟其他來源同一句（FB-452）
            changes.append(f"心得 +{gained}")
    elif exp:  # 同伴不進決戰（人物資質設計 14.5）：只給本人；升級給屬性點同切磋。決戰是仗（減法季 45 級以後照算）
        before = p.member.level
        lines += team.add_exp(c, p.member, exp, p.name, "showdown")
        if p.member.level > before:
            points = team.level_points(ctx.state, c, before, p.member.level)
            p.stat_points += points
            if points:
                lines.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
        changes.append(f"經驗 +{exp}")
    for chief in battle.commanders:  # 龍頭上陣：最後一擊擊退大將的人
        if chief.felled_by == me.name and c.config.battle.generals.slay_fame:
            changes += renown.gain(s, c, "fame", c.config.battle.generals.slay_fame)
            lines.append(rules.SLAY_LINE.format(name=chief.name))
    if me.acted_rounds >= 1:  # 名聲 3.1：自己出手至少 1 回合（同首功）；掛機被代為固守的回合不算
        rout = ctx._deed_fame("showdown_rout") if won and battle.outcome_margin == "大勝" else []
        changes += journal.combine_changes(ctx._deed_fame("showdown") + rout)
    if showdown_credits(ctx, me):  # 替自己這一方出戰才記（豪強分屬兩軍：依附那一軍）；臨時投效的不記
        push_points = pay.contrib_push + (pay.win_contrib_push.get(battle.outcome_margin, 0) if won else 0)
        contrib = round(c.config.contrib_per_push * push_points * share * half)
        if contrib and season_one(c, s.world):
            # 豪強記參戰那一刻那一邊那一本（計畫 5.0 第 12 條：中途改幫另一軍，這一場照舊記原來那一軍）
            wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib, side=me.faction)
            changes.append(f"貢獻 +{contrib}")
    if changes:
        lines.append(f"{'得勝的' if won else ''}軍餉發下來了。")
    return changes + showdown_tier4(ctx, battle, me, lines)


def showdown_credits(ctx, me: battle_instance.BattleParticipant) -> bool:
    """這一場的戰功記不記貢獻：站的是自己這一方（豪強分屬兩軍：依附那一軍）才記，臨時投效的不記。三陣營四勝利開著的季，
    豪強站的是它能幫的那一軍就記（記參戰那一刻那一邊那一本，_showdown_pay），不看此刻幫誰——中途改幫另一軍，這一場照舊算。"""
    side = ctx._side()
    if side is not None and me.faction == side:
        return True
    p = ctx.state.player
    return ctx._four_wins() and me.faction in wins.allies(p, ctx.content)


def watch_text(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
    """只能觀戰時，場景上說明為什麼：參戰後離開了大區、或還沒到戰場。"""
    if ctx.state.player.name in battle.participants:
        region = ctx._battle_region_name(definition)
        return f"你離開了{region}，這回合不出手；人回到{region}就能再出手。"
    if battle.siege is not None and not siege.slots(battle.siege, ctx._conquest_side()):
        return siege.watch_line(ctx.content, battle.siege)  # 攻城戰：另一軍站不進守將那一格（裁決 8）
    return f"{ctx._absent_reason(definition)}。"


def gauge_of(ctx, battle: battle_instance.BattleInstance, definition: BattleDef, side: str | None) -> dict:
    """battle_instance.gauge 的參數：時刻表決戰（第一季開著）照偏離中線分大勝，其餘照 outcomes 的門檻。"""
    timetable = definition.timetable_event is not None and season_one(ctx.content, ctx.state.world)
    return battle_instance.gauge(battle, definition, side, timetable, ctx.content.config.battle, ctx.state.player.name)


def battle_gauge(ctx) -> dict | None:
    """場景裡畫著的這場決戰（集結、開打）的戰局條（Joy 2026-10-10）；沒有、序章裡是 None。只讀，不推進戰鬥。
    自己在場上就站自己那一邊看；還沒加入的看自己陣營那一邊；散人、第三方看第一方在左。"""
    status = ctx._battle_for_me(tick=False)
    if status is None:
        return None
    battle, definition = status
    p = battle.participants.get(ctx.state.player.name)
    side = p.faction if p is not None else ctx._side()
    if p is None and battle.siege is not None and not siege.slots(battle.siege, ctx._conquest_side()):
        # FB-693：攻城戰裡自己站不進任何一格（另一軍看單方攻中立地：守將借的是那一軍的格），兩邊都不標「我方」、第一方在左
        side = None
    g = gauge_of(ctx, battle, definition, side)
    # 這一回合還剩幾秒逾時（同 _round_wait）：網頁每秒自己倒數「最遲 M 分 S 秒後結算」，不等十秒一次的輪詢（Joy 2026-10-13）。
    # 暫停中、集結中是 None（不倒數）
    if battle.phase == "active" and ctx.world.paused_at() is None:
        g["due"] = max(0, int(battle.round.opened_real + definition.round_seconds - ctx.now))
    return g


def siege_banner(ctx) -> dict | None:
    """場景裡畫著的這一場是攻城戰時，畫面最上面那一條（領地爭奪第三批 A，企劃者挑甲：「攻城・地點｜守方：某某」，siege.banner）；
    決戰、沒有戰鬥、序章裡是 None。同 battle_gauge 看同一場（_battle_for_me），只讀。"""
    status = ctx._battle_for_me(tick=False)
    if status is None or status[0].siege is None:
        return None
    return siege.banner(ctx.content, status[0])


def record_gauge(ctx, record_id: int | None) -> dict | None:
    """戰報頁那一筆是決戰時收場那一刻的戰局條；不是決戰、找不到是 None。"""
    record = battlelog.find(ctx.state, record_id) if record_id is not None else None
    return record.gauge if record is not None else None


def card_gauge(ctx) -> dict | None:
    """「剛剛」那張戰鬥卡片是一場決戰時，收場那一刻的戰局條（BattleRecord.gauge）；不是就 None。"""
    if not ctx.shows_battle_card():
        return None
    record = battlelog.find(ctx.state, ctx.state.battle_card)
    return record.gauge if record is not None else None


def battle_scene_text(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
    header = f"**{definition.name}**"
    # 攻城戰（領地爭奪第二批）：誰攻、守方是誰寫在畫面最上面那一條（siege_banner，第三批 A），場景不再寫一次（PM）；
    # 只留那一條沒說到的（三方混戰的規矩、沒到場的那一軍，siege.scene_note）
    if battle.siege is not None and (note := siege.scene_note(ctx.content, battle.siege, battle)):
        header += "\n\n" + note
    if front := conquest.front_scene(ctx.content, definition, battle.front_note):  # 起點照哪一條戰線（開集結那一刻的快照）
        header += "\n\n" + front
    if battle.seal_shard and battle.seal_shard in ctx.content.seal:  # 璽動（4.3）：參戰的人知道打完可能有單挑
        header += "\n\n" + seal.stir_text(ctx.content, battle.seal_holder or "", ctx.content.seal[battle.seal_shard].name, scene=True)
    if seal.on(ctx.content) and seal.is_mandate_battle(ctx.content, definition):  # 天命之爭（8.3）：碎片在哪一軍、懷璽的人份量加重
        shift = seal.lean_shift(battle.seal_lean, definition, ctx.content.config.seal)  # 同集結那一刻的算法（FB-186）
        weight = seal.MANDATE_WEIGHT if seal.holders(ctx.world.seal_state().registry) else ""  # 全服沒人持有就不寫（FB-189）
        header += "\n\n" + seal.MANDATE_SCENE.format(
            lean=seal.lean_text(battle.seal_lean, definition), weight=weight,
            shift=seal.shift_text(shift, battle.seal_lean, definition, extra=battle.front_note is not None),  # FB-687
        )
    names = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫守軍（FB-540）
    if battle.phase == "muster" and battle.commanders:  # 龍頭上陣：集結時就看得到誰親自上陣（三方混戰多一格守軍）
        header += "\n\n" + "\n".join(
            f"{names[fid]}：{text}" for fid in battle_instance.fields(battle, definition) if (text := generals.lineup(battle, fid)))
    watching = ctx._watching_battle(battle, definition)
    watch_line = watch_text(ctx, battle, definition)
    if battle.phase == "muster":
        paused = ctx.world.paused_at()  # 暫停中集結不倒數：停在按下暫停那一刻剩下的
        remaining = max(0, int(battle.muster_deadline_real - (ctx.now if paused is None else paused)))
        left = f"{remaining // 60} 分 {remaining % 60} 秒"
        if watching:
            return f"{header}\n\n集結中，還剩現實 {left}。{watch_line}"
        me = battle.participants.get(ctx.state.player.name)
        if me is not None:
            side = names.get(me.faction, me.faction)
            leaving = "；走出這一區就不算在場" if definition.region is not None else ""
            joined = "臨時投效" if ctx._free_agent(definition) else "加入"
            if me.faction == battle_instance.neutral_guard(battle):
                joined = siege.HELP_GUARD_TITLE  # 「你已助守【守軍】」（FB-540）
            role = battle_instance.role_text(ctx.content.config.battle, me.role)
            role = f"你的職位：{role}。" if role else ""
            ride = mounts.CAVALRY_LINE.format(name=me.mount, pct=mounts.pct(me.cavalry)) + "。" if me.mount else ""  # 騎著馬（5.9）：沒騎馬一個字都不多
            ride += rules.TROOPS_LINE.format(names=me.troops, pct=mounts.pct(me.troop_bonus)) + "。" if me.troops else ""  # 帶著部下
            ride += rules.ESCORT_MUSTER.format(name=me.escort.name) if me.escort is not None else ""  # 隨你出陣的同伴（歷史武將同行）
            return f"{header}\n\n你已{joined}【{side}】，集結還剩現實 {left}。{role}{ride}集結結束就開打，在那之前照常行動{leaving}。"
        if ctx._free_agent(definition):
            who = "你是散人" if ctx.state.player.faction is None else f"你是{ctx._own_side_name()}，不是交戰的兩軍"
            can = "可以臨時投效其中一方，只算這一場"
            if battle_instance.neutral_guard(battle) is not None:  # 單方攻中立地：一邊是攻方、一邊是助守（FB-540）
                can = siege.FREE_AGENT_GUARD.format(
                    who="、".join(names.get(a, a) for a in battle.siege.attackers), place=ctx.content.locations[battle.siege.loc].name)
            return f"{header}\n\n集結中，還剩現實 {left}。{who}，{can}；集結期間照常行動。"
        return f"{header}\n\n集結中，還剩現實 {left}。選擇陣營加入；集結期間照常行動。"
    act = battle_instance.current_act(battle, definition)
    # 第幾回合／一共幾回合（戰鬥系統設計 3.2）：讓人知道還要打多久；收場的決戰不會走到這裡。
    # 已送出／在場：讓等待看起來是在等人，不是壞了（試玩回饋 2026-10-08）
    count = f"（第 {battle.round_number + 1}／{battle_instance.total_rounds(definition)} 回合・{round_wait(ctx, battle, definition)}）"
    lines = [header, *idle_note(ctx, battle), f"【{act.title}】{count}{battle_instance.act_text(battle, definition)}"]
    p = battle.participants.get(ctx.state.player.name)
    mine = p.faction if p is not None else ctx._side()
    if p is None and mine is not None and mine == battle_instance.neutral_guard(battle):
        mine = None  # FB-543：單方攻中立地，守將站的是這個人陣營的 id，人沒參戰（旁觀）：守將的令不是他這邊的令，不寫。助守的人（p 在守將那一格）照寫
    lines += chief_lines(ctx, battle, definition, mine)
    lines += round_blocks(ctx, battle, definition)
    if p is not None and (role := battle_instance.role_text(ctx.content.config.battle, p.role)):
        lines.append(f"你的職位：{role}")
    if p is not None and p.mount:
        lines.append(mounts.CAVALRY_LINE.format(name=p.mount, pct=mounts.pct(p.cavalry)))  # 騎著馬上陣（裝備四欄 5.9，加入時的快照）
    if p is not None and p.troops:
        lines.append(rules.TROOPS_LINE.format(names=p.troops, pct=mounts.pct(p.troop_bonus)))  # 帶著部下上陣（加入時的快照）
    if p is not None and p.escort is not None:
        lines.append(escort_line(ctx, p.escort))  # 隨你出陣的同伴（氣血、敗走；別人的不列）
    if p is not None:
        last = []  # 上一回合的兩句併成一段 markdown 引用（「> 」、段內換行）：網頁在 .scene blockquote 底下縮成小字、淡色
        enemy = next((f for f in definition.factions if f.id != p.faction), None)
        seen = battle.last_mix.get(enemy.id) if enemy is not None else None
        if seen:  # 這回合的比例要到結算才揭曉，畫面只寫上一回合（設計 3.4）
            parts = "・".join(f"{m} {round(seen[m] * 100)}%" for m in MOVES)
            last.append(f"> 對面上一回合（{names.get(enemy.id, enemy.name)}）：{parts}")
        if p.last_result:
            last.append(f"> 你上一回合：{p.last_result}")
        if last:
            lines.append("\n".join(last))
        lines += battle_spotlight(ctx, battle, definition, p)
    if p is not None and p.eliminated:
        lines.append("（你已經倒下，只能在一旁觀戰。）")
    elif watching:  # 倒下的人不會再出手，不必再說「回到大區就能再出手」
        lines.append(watch_line)
    return "\n\n".join(lines)


def chief_lines(ctx, battle: battle_instance.BattleInstance, definition: BattleDef, side: str | None) -> list[str]:
    """龍頭上陣：兩邊上陣的人物（氣血、敗走），自己這一方這一回合的將令。沒有人物上陣是空的。"""
    if not battle.commanders:
        return []
    names = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫守軍（FB-540）
    rows = [f"{rules.SIDE_TAG.format(side=names[fid])}{text}"  # 三方混戰多一格守軍（裁決 22）
            for fid in battle_instance.fields(battle, definition) if (text := generals.lineup(battle, fid))]
    order = battle_instance.order_text(battle, side, ctx.content.config.battle) if side is not None else ""
    return ["\n".join(rows)] + ([order] if order else [])


def round_blocks(
    ctx, battle: battle_instance.BattleInstance, definition: BattleDef, *, last: int | None = rules.ROUND_BLOCKS,
    oldest_first: bool = False, me: battle_instance.BattleParticipant | None = None,
) -> list[str]:
    """場景上最近五段戰況，一回合一段、新的在上（Joy 2026-10-14「大決戰因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）：
    每一段是「##### 第 N 回合」加一行一條的清單，網頁照標題把舊的幾回合收成一行（app.js 的 roundBlocks）。
    narrative_log 開打那一句之後一回合一筆（apply_battle_tales 也照這個算），所以倒數第 k 筆是第（round_number − k）回合；
    開打那一句（第 0 筆）照舊一段話。每一條是哪一軍的（Joy 2026-10-14「看不出誰是官軍誰是黃巾」）：開頭是參戰者的名號就照他
    站的那一邊，開頭是交戰一方的名字就是那一方，前面加「〔官軍〕」（SIDE_TAG；網頁 roundBlocks 換成那一軍顏色的小標籤）；
    誰佔上風、各路奇招互相牽扯、換幕這幾句不分邊，不加。
    收場時寫進自己戰報的那一份（Joy 2026-10-14「決戰能不能把完整戰報在戰報那邊可以展開」，_file_showdown）：last 是 None＝整場、
    oldest_first 照先後、me 是自己，每一段最後一條寫自己這一回合出了什麼（MY_MOVE）。"""
    log = battle.narrative_log
    sides = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫〔守軍〕（FB-540）
    owner = {c.name: c.faction for c in battle.commanders} | {n: q.faction for n, q in battle.participants.items()}
    names = sorted(owner, key=len, reverse=True)  # 名號長的先比：「沈浪」不能先認走「沈浪子」

    def side_of(item: str) -> str:
        if item.startswith(tactics.LEAD) and "〕" in item:  # 招那一句「〔招名〕某某……」：照招名後面的名號認
            item = item.split("〕", 1)[1]
        who = next((n for n in names if item.startswith(n)), None)
        fid = owner[who] if who is not None else next((f for f, nm in sides.items() if item.startswith(nm)), None)
        return rules.SIDE_TAG.format(side=sides[fid]) if fid in sides else ""
    out = []
    for k, entry in enumerate(reversed(log if last is None else log[-last:])):
        n = battle.round_number - k
        rows = [line for line in entry.split("\n") if line.strip()]
        if n <= 0 or not rows:
            out.append(entry)
            continue
        items: list[str] = []
        for line in rows:  # 誰放手一搏寫了什麼、接著那一句成敗，併成同一條（人多時一眼看得出哪一句是誰的）
            if items and rules.GAMBLE_SAID in items[-1] and "\n" not in items[-1] and rules.GAMBLE_SAID not in line:
                items[-1] += f"\n  {line}"
            else:
                items.append(line)
        mine = [rules.MY_MOVE.format(move=me.moves[n])] if me is not None and n in me.moves else []
        rows_md = fold_war_lines(ctx, battle, items, sides, owner, names, side_of)
        out.append(f"{rules.ROUND_HEAD.format(n=n)}\n\n" + "\n".join([*rows_md, *(f"- {m}" for m in mine)]))
    return out[::-1] if oldest_first else out


def fold_war_lines(ctx, battle: battle_instance.BattleInstance, items: list[str], sides: dict[str, str],
                    owner: dict[str, str], names: list[str], side_of) -> list[str]:
    """一回合的每一條寫成清單的一列（「- 〔官軍〕……」）；一軍發動戰法的那幾句（〔招名〕開頭，自己的不算）有 WAR_FOLD_MIN 句以上就在
    第一句的位置換成一列摘要「官軍本回合 9 人發動武學：回氣血 4、加重 2」，那幾句縮排成它底下的一層（網頁畫成點開才看）。"""
    me = ctx.state.player.name
    label = {kind: name for name, kinds in rules.WAR_FOLD_KINDS.items() for kind in kinds}
    # 這一場記下的（tactic_kinds）為準；這一版以前打的場沒記，照內容武學的戰法與功效補（玩家取了名的招認不出來，歸「其他」）
    book = ctx.content.traits
    known = {sk.tactic.name: sk.tactic.kind for sk in ctx.content.skills.values() if sk.tactic is not None}
    known |= {t.name: t.tactic.kind for t in [*book.general, *book.special, *book.high] if t.tactic is not None}
    known |= battle.tactic_kinds
    groups: dict[str, list[tuple[str, str]]] = {}  # 陣營 → [(誰, 那一句)]
    for item in items:
        if not item.startswith(tactics.LEAD) or "〕" not in item:
            continue
        body = item.split("〕", 1)[1]
        who = next((x for x in names if body.startswith(x)), None)
        if who is None or who == me or owner.get(who) not in sides:
            continue
        groups.setdefault(owner[who], []).append((who, item))
    folded = {fid: rows for fid, rows in groups.items() if len(rows) >= rules.WAR_FOLD_MIN}
    taken = {item: fid for fid, rows in folded.items() for _, item in rows}
    out: list[str] = []
    for item in items:
        if item not in taken:
            out.append(f"- {side_of(item)}{item}")
            continue
        rows = folded.pop(taken[item], None)
        if rows is None:  # 這一軍的摘要已經寫過了
            continue
        kinds = [known.get(line[len(tactics.LEAD):].split("〕", 1)[0]) for _, line in rows]
        counts: dict[str, int] = {}
        for kind in kinds if any(kinds) else []:  # 一句都認不出來（舊的場、全是自創的招）：只寫幾個人，不分類
            name = label.get(kind or "", "其他")
            counts[name] = counts.get(name, 0) + 1
        order = [*rules.WAR_FOLD_KINDS, "其他"]
        parts = "、".join(f"{k} {counts[k]}" for k in order if k in counts)
        fid = taken[item]
        head = rules.WAR_FOLD.format(side=sides[fid], n=len({who for who, _ in rows})) + (f"：{parts}" if parts else "")
        out.append(f"- {rules.SIDE_TAG.format(side=sides[fid])}{head}")
        out.extend(f"    - {line}" for _, line in rows)
    return out


def idle_note(ctx, battle: battle_instance.BattleInstance) -> list[str]:
    """掛機的人自己看到的那一句（Joy 2026-10-10 掛機懲罰），放在戰場名字底下第一行。"""
    p = battle.participants.get(ctx.state.player.name)
    if p is None or p.eliminated or battle.phase != "active":
        return []
    if battle_instance.idle(p):
        return ["**你上一回合沒出手**，系統替你固守了；這一回合大家不等你，按任何一招就不算掛機。"]
    return []


def battle_spotlight(
    ctx, battle: battle_instance.BattleInstance, definition: BattleDef, p: battle_instance.BattleParticipant,
) -> list[str]:
    """點名與顯眼（Joy 2026-10-10）：上一回合誰盯上了你、你被牽制了沒有、這一幕還能不能放手一搏、你是不是顯眼的人；倒下的人只剩
    璽動那一場「戰功居前」那一句（FB-177：挑挑戰者不看倒下，畫面照同一條），其餘跟倒下無關的不寫。"""
    if battle.phase != "active":
        return []
    merit = battle.seal_shard and p.name in seal.hint_names(battle, ctx.content, seal.holders(ctx.world.seal_state().registry))
    if p.eliminated:
        return [seal.merit_hint(ctx.content)] if merit else []
    out = []
    hunters = battle.last_targets.get(p.name)
    if hunters:
        out.append(f"{'、'.join(hunters)}盯上了你。")
    if battle_instance.pinned(battle, p):
        out.append("你被牽制住了，這一回合只能固守。")
    elif definition.free_text_gamble is not None and not battle_instance.can_gamble(battle, definition, p):
        out.append("這一幕你已經放手一搏過了，下一幕才能再搏。")
    if battle.marked.get(p.name) == battle.act_index:
        out.append("你在這一幕太顯眼了，對面的強攻會往你身上招呼。")
    if merit:
        out.append(seal.merit_hint(ctx.content))  # 璽動那一場戰功居前（4.3）：不露數字、不露名次；改版兩軍都給、字有條件
    return out


def round_wait(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
    """「已送出 X／在場 Y，最遲 M 分 S 秒後結算」：在場的人都送出就提早結算，不然等這一回合逾時（暫停中停在按下暫停那一刻）。"""
    sent, present = battle_instance.round_progress(battle, definition)  # 跟結算等的是同一批人
    idlers = battle_instance.idle_count(battle, definition)  # 掛機的不等（Joy 2026-10-10），另外寫
    paused = ctx.world.paused_at()
    left = max(0, int(battle.round.opened_real + definition.round_seconds - (ctx.now if paused is None else paused)))
    due = f"最遲 {left // 60} 分 {left % 60} 秒後結算" if left else "時間到了，即將結算"
    return f"已送出 {sent}／在場 {present}" + (f"（掛機 {idlers} 人不等）" if idlers else "") + f"，{due}"


def battle_free_text_prompt(ctx) -> str | None:
    """這回合是否有自訂行動的輸入框可以用，有的話回傳提示語（見 BattleOption.free_text
    ——設計討論：魯莽這類選項該是玩家自己想出來的招，不是從清單挑一個）；沒有（不在
    戰鬥中、集結期、已經出局、這回合已經選過）就回傳 None，server.py 用這個決定輸入框
    要不要顯示。序章裡沒有（_battle_for_me）。"""
    status = ctx._battle_for_me(tick=False)
    if status is None:
        return None
    battle, definition = status
    name = ctx.state.player.name
    p = battle.participants.get(name)
    if battle.phase != "active" or p is None or p.eliminated or p.away or name in battle.round.pending_actions:
        return None
    option = next((o for o in battle_instance.options_for(battle, definition, name) if o.free_text), None)
    return option.text if option else None


def battle_free_text_note(ctx) -> str | None:
    """有放手一搏輸入框時（battle_free_text_prompt 不是 None）回傳輸入框旁邊的說明，否則 None；
    再失手一次就會倒下時（battle_instance.one_miss_left）後面多 BATTLE_GAMBLE_LAST。"""
    if battle_free_text_prompt(ctx) is None:
        return None
    battle, definition = ctx._battle_for_me(tick=False)
    p = battle.participants[ctx.state.player.name]
    if definition.free_text_gamble is not None and battle_instance.one_miss_left(p, definition.free_text_gamble):
        return f"{rules.BATTLE_GAMBLE_NOTE}{rules.BATTLE_GAMBLE_LAST}"
    return rules.BATTLE_GAMBLE_NOTE


def battle_text_check(ctx, text: str, tick: bool) -> tuple[BattleDef, str, str, str] | list[str]:
    """放手一搏現在送不送得出去：送得出去回傳（這場的定義, 選項的 tag, 截到 20 字的文字, 自己站的那一方的名字），
    不行回傳要給玩家看的那一句。tick 照 _battle_status。"""
    if ctx.world.paused_at() is not None:  # 不走 choose()：暫停中自己擋，不然送出去會把這一回合結算掉
        return [f"（{PAUSED_TEXT}。）"]
    status = ctx._battle_for_me(tick=tick)  # 序章裡送不出去（FB-113）
    if status is None:
        return ["（此刻無法這麼做。）"]
    battle, definition = status
    name = ctx.state.player.name
    p = battle.participants.get(name)
    if p is None or p.eliminated or p.away or name in battle.round.pending_actions:
        return ["（此刻無法這麼做。）"]
    option = next((o for o in battle_instance.options_for(battle, definition, name) if o.free_text), None)
    if option is None:
        return ["（此刻無法這麼做。）"]
    text = text.strip()[:20]
    if not text:
        return ["（請先輸入你想做的事。）"]
    faction_name = battle_instance.side_names(battle, definition).get(p.faction, p.faction)  # 助守中立地寫守軍（FB-540）
    return definition, option.tag, text, faction_name


def battle_text_request(ctx, text: str) -> rules.BattleTextRequest | list[str]:
    """放手一搏的階段 A（server.py 在行動鎖內、很快地呼叫）：送得出去就回傳要在鎖外送模型評成功率的單子，不行回傳那一句話。
    只讀，不推進戰鬥（同 free_text_request）。"""
    checked = battle_text_check(ctx, text, tick=False)
    if isinstance(checked, list):
        return checked
    definition, _, text, faction_name = checked
    battle = ctx._battle_now()
    return rules.BattleTextRequest(
        battle_id=definition.id, act_index=battle.act_index, faction_name=faction_name, text=text,
        name=ctx.state.player.name, sex=gender.of(ctx.state),
        target=battle_instance.target_line(battle, definition, ctx.state.player.name, text, ctx.content.config.battle),
    )


def submit_battle_custom_action(
    ctx, text: str, llm_rate: int | None = None, stories: tuple[str, str] | None = None,
) -> list[str]:
    """自訂行動輸入框的送出：截到 20 字，查到這回合對應的 free_text 選項，機制效果
    還是走它的 tag（跟按按鈕完全一樣的查表邏輯），玩家打的字只會被餵給 LLM 評成功率。
    這裡用 tick=True（不是 tick=False）——跟 _battle_choose() 不一樣，這個方法不是
    透過 choose() 進來的，choose() 開頭那次 self.options(odds=False) 呼叫順便推進
    過一次集結逾時/回合逾時的保護在這裡沒有發生過，這個方法是自己的入口，必須自己
    負責先追趕一次，不然集結剛好逾時的那一刻送出的行動會在 submit_action() 裡被
    「battle.phase 還是 muster」悄悄吃掉（見那次遇到的真實 bug）。
    llm_rate 是 server.py 在行動鎖外評好的成功率（battle_text_request 開的單子；試玩回饋 2026-10-08：鎖內等模型全服跟著等）；
    沒給（直接呼叫的測試、腳本）就在這裡評，用 _quick_client 的短逾時複本，評不到就是保底值。
    stories 是同一次模型呼叫寫好的（成功版, 失敗版）劇情（battle_instance.assess_gamble）；擲骰後播對應的那一版。"""
    checked = battle_text_check(ctx, text, tick=True)
    if isinstance(checked, list):
        return checked
    definition, tag, text, faction_name = checked
    if llm_rate is None:
        battle = ctx._battle_now()
        act = battle_instance.current_act(battle, definition)
        target = battle_instance.target_line(battle, definition, ctx.state.player.name, text, ctx.content.config.battle)
        verdict = battle_instance.assess_gamble(
            ctx._quick_client(), act, faction_name, text, ctx.state.player.name, target=target, sex=gender.of(ctx.state),
        )
        llm_rate, stories = verdict.rate, (verdict.win, verdict.lose)
    return ctx._submit_battle_action(
        ctx.state.player.name, definition, tag, text, llm_rate, stories, sex=gender.of(ctx.state),
    )


def battle_tale_request(ctx) -> rules.BattleTaleRequest | None:
    """回合結算後補放手一搏劇情的 A 段（server.narrate_battle 在行動鎖內、很快地呼叫）：這一場有等著補劇情的放手一搏，
    回傳最早那一回合的一批（battle_instance.tales_due）；沒有回 None。只讀。有攻城戰時（領地爭奪第二批）決戰先、再照攻城的先後，
    第一場有等著補的那一場（收場了、還沒在每天結算時拿掉的攻城也算：最後一回合的劇情收場之後才寫好）。"""
    battle = next((b for b in tale_battles(ctx) if b.tales and b.battle_id in ctx.content.battles), None)
    if battle is None:
        return None
    definition = ctx._definition_of(battle)
    due = battle_instance.tales_due(battle)
    names = battle_instance.side_names(battle, definition)  # 助守中立地寫守軍（FB-540）
    return rules.BattleTaleRequest(
        battle_id=battle.battle_id, record_id=battle.record_id, opened=battle.muster_deadline_real,
        act_index=min(due[0].act_index, len(definition.acts) - 1),
        items=[battle_instance.TaleItem(
            name=t.name, faction_name=names.get(t.faction, t.faction), text=t.text, won=t.won, target=t.target, sex=t.sex,
        ) for t in due],
        done=[(t.round, t.name) for t in due],
    )


def apply_battle_tales(ctx, request: rules.BattleTaleRequest, stories: dict[str, str]) -> int:
    """補劇情的 C 段：還是同一場才補（battle_instance.apply_tales）；回傳補了幾句。換了一場（收場後開了下一場）什麼都不動。
    有攻城戰時照流水號找那一場（決戰或攻城）。"""
    battle = next((b for b in tale_battles(ctx) if b.record_id == request.record_id), None)
    if battle is None or (battle.battle_id, battle.record_id, battle.muster_deadline_real) != (
        request.battle_id, request.record_id, request.opened,
    ):
        return 0
    patched = {"n": 0}

    def _apply(b: battle_instance.BattleInstance) -> None:
        patched["n"] = battle_instance.apply_tales(b, request.done, stories)

    ctx._mutate_battle_of(battle, _apply)
    return patched["n"]


def tale_battles(ctx) -> list[battle_instance.BattleInstance]:
    """補放手一搏劇情看的那幾場：決戰那一格，加上共用狀態裡的攻城（收場了、還沒在每天結算時拿掉的也算）；沒開領地爭奪只有決戰。"""
    showdown = ctx.world.get_battle()
    sieges = ctx.world.get_sieges() if conquest.on(ctx.content, ctx.state.world) else []
    return ([showdown] if showdown is not None else []) + sieges


def showdown_tier4(ctx, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, lines: list[str]) -> list[str]:
    """時刻表決戰得勝給一個四階（正式季整合 4.5，第 4 批）：長社、宛城、廣宗這種時刻表上的決戰，得勝那一方出手滿門檻的人各一個
    （門檻照奪璽單挑挑人那一條 seal.threshold：min(3, 實打回合)，參戰不到 small_battle 人放寬到 1）；臨時投效替得勝那一軍出手夠了也算。
    保底收場（沒有贏家）、天命之爭不給。屬性隨機（名號＋那一場的 record_id）。回要寫在得失的那一樣，戰報那一句接在 lines。"""
    c, s = ctx.content, ctx.state
    definition = c.battles.get(battle.battle_id)
    if (not four_tiers.on(c) or not c.config.four_tiers.showdown or definition is None or not definition.timetable_event
            or seal.is_mandate_battle(c, definition) or not battle.outcome_side or me.faction != battle.outcome_side
            or me.acted_rounds < seal.threshold(battle, c.config.seal)):
        return []
    rng = random.Random(f"決戰四階|{s.player.name}|{battle.record_id}")
    pool = sorted(m.id for m in c.materials.values() if m.tier == four_tiers.TIER)
    if not pool:
        return []
    mid = rng.choice(pool)
    line = materials.grant(s, c, mid)
    if not line:
        return []
    lines.append(rules.SHOWDOWN_TIER4.format(name=c.materials[mid].name))
    return [f"{c.materials[mid].name} ×1"]


def battle_on_screen(ctx) -> bool:
    """場景上此刻畫著一場全服戰鬥（同 scene_text 讀的那一場；只讀、不推進）。server.main_view 拿它認出「選單這一下把決戰推到
    收場了」，場景要重讀（手機介面自檢 U-06）。"""
    return ctx._battle_for_me(tick=False) is not None
