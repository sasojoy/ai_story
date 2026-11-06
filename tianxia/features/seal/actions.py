"""玉璽碎片的季流程（全部拆包第 27 批從 Game 搬來，計畫 docs/superpowers/plans/2026-11-07-玉璽包-第1批.md 1.1；Game 留一行委派）：
抄本重抄、探索撿到、戴著碎片的份量快照、天命之爭的份量加權、補送、奪璽單挑的戰報、天命之爭定天命、時刻表決戰收場。

- 包裡互叫直接叫函式（補送 deliver_results 叫 file_seal、copy_heirloom；撿到 seal_find 叫 deliver_results）；叫回 Game 的都經 ctx：
  同包的 duel_actions.challenge（第 28 批搬進來，直接叫）、自己的委派 _mandate_settle（scripts/measure_seal.py 換掉 Game._mandate_settle，經 ctx 才打得到）。
- 事件 outing 的 seal 那一格叫 seal_find、battle_end 的 seal 那一格叫 settle（__init__.py 的 bus()，在叫的那一下才照模組屬性找：
  scripts/measure_seal.py 換掉這裡的 settle）。碎片的規則叫 seal.<名字>（模組屬性：tests/acts/test_conquest_rules.py 換掉 seal.find）。
- 擲骰一律是 seal.dice（密鹽），不碰 Game.rng；取數的先後照原本。
"""
from __future__ import annotations

from tianxia import battle_instance, battlelog, conquest, library, renown, treasures  # 共用規則層
from tianxia import journal
from tianxia.core import annal_base as annals
from tianxia.models import BattleDef
from tianxia.rules import learn_skill
from tianxia.state import BattleRecord, JournalEntry

from . import duel_actions, duel_rules, seal


def copy_heirloom(ctx) -> None:
    """抄本照全服登記重抄（玉璽碎片設計 7.4）：只讀 world 那一列，不讀季。sync 與 _drop_stale_references 都叫，所以 _kin 也重抄。
    碎片關著（測試內容、主機關了開關）不讀資料庫：每次建 Game 都會走到這裡。"""
    reg = ctx.world.seal_state().registry if seal.on(ctx.content) else None
    seal.copy_heirloom(ctx.state, ctx.content, reg)


def seal_find(ctx, loc_id: str) -> list[str]:
    """領地爭奪的季，探索撿玉璽碎片（領地爭奪設計 3.9、4.8；計畫 Task 14）：探索的四種（找素材、找事件、靜心感悟、練功）收尾各叫一次。
    只在這一季藏著一片、人就站在藏碎片的那一塊、那一塊不在剛易手的冷卻期（conquest.cooling）、手上還沒有碎片（一人一片）時擲 seal.find
    （那一塊此刻歸你的陣營機率高一點）；
    別的塊、沒藏碎片的季一律不擲、不碰任何登記。擲中就把那一片記到自己名下（登記記一筆 emerge，所以補紀錄、同一季學會混元一氣、
    天命之季的判斷都照現世的老路），清掉藏處；接著 deliver_results 馬上補送。天下大事與江湖史都不寫是在哪裡撿到的。
    骰子是密鹽的亂數，不碰 Game.rng；寫登記用一次 world.mutate、寫入時整個重驗（別人搶先撿走了就落空）。回要接在探索結果後面的句子。
    讀探索包認領的 PlayerState.explore_seq（這個人第幾次探索）：包讀別包的欄位，第 55 批（補算收接縫）改查詢服務。"""
    c, s = ctx.content, ctx.state
    if not seal.on(c) or not conquest.on(c, s.world):
        return []
    view = ctx.world.seal_state()
    cache = seal.live_cache(view.registry, view.season)
    p = s.player
    if cache is None or cache.loc != loc_id or seal.shard_of(view.registry, p.name) is not None:
        return []
    if conquest.cooling(s.world, c, loc_id):  # 翻地與爭搶：剛易手還在冷卻的那一塊加成暫停，碎片也不擲（輿圖簡化設計 4.1）
        return []
    side = ctx._side()  # allied.side_of（＝rules.side_of）：豪強依附一軍就是那一軍（FB-571，同地盤折扣）；散人沒有自家、不乘（PM 裁決）：side 是 None，不能跟沒人佔的 None 湊成自家
    own = side is not None and conquest.holder(s.world, c, loc_id) == side
    if not seal.find(view.registry, view.tianji, p.name, p.explore_seq, own, c.config.seal):
        return []
    found = {"ok": False}

    def _apply(shared) -> None:
        reg = seal.filled(shared.seal, c)
        now = seal.live_cache(reg, shared.season_number)
        if now is None or now.loc != loc_id or seal.key(p.name) in seal.holders(reg):  # 寫入時重驗：被別人搶先、或自己剛有了一片
            return
        shard = reg.shards[now.shard]
        season = shared.season_number
        shard.state, shard.holder, shard.since_season, shard.emerged_round = "held", p.name, season, reg.round
        reg.emerge_season, reg.cache = season, None
        text = seal.FIND_GOT.format(name=p.name, shard=c.seal[shard.id].name)
        seal.log(reg, season, "emerge", shard=shard.id, holder=p.name, text=text)
        seal.rumor(shared.season, text)
        seal.chronicle(shared.season, text)
        found["ok"] = True

    ctx.world.mutate(_apply)
    if not found["ok"]:
        return []
    deliver_results(ctx)  # 傳承那一格、混元一氣、紀錄一則、行狀一筆（同現世的得主）
    return [seal.FIND_SCENE]


def seal_bare(ctx) -> battle_instance.SealBare | None:
    """戴著玉璽碎片（改版開著，treasures.power_scale 不是 1）時，不含碎片戰力的威力與份量（快照進 BattleParticipant.seal_bare，
    奪璽單挑用）；沒有是 None。份量照加入那一刻的算法（騎兵、部下照乘，單挑時 seal_duel.unmounted 再拿掉）。"""
    if treasures.power_scale(ctx.state, ctx.content) == 1.0:
        return None
    return battle_instance.SealBare(power=ctx._battle_power(seal=False), scores=ctx._battle_scores(seal=False))


def mandate_weight(ctx, definition: BattleDef | None, scores: dict[str, float]) -> dict[str, float]:
    """天命之爭：手上有碎片的人到場，份量 × Config.seal.mandate.holder_weight（玉璽碎片設計 8.3；只在這一場，碎片本身不加威力）。
    真人、假人、臨時投效的散人都走這裡（_battle_choose、_enlist、_backfill_battle_scores）。"""
    c = ctx.content
    if not seal.on(c) or not seal.is_mandate_battle(c, definition):
        return scores
    if seal.shard_of(ctx.world.seal_state().registry, ctx.state.player.name) is None:
        return scores
    w = c.config.seal.mandate.holder_weight
    return {move: round(value * w, 1) for move, value in scores.items()}


def deliver_results(ctx) -> None:
    """玉璽碎片的事補送到自己手上（玉璽碎片設計 5.9、3.3）：全服登記流水號 > PlayerState.seal_seen、跟自己有關的每一筆——
    現世拿到（紀錄；同一季才學 emerge_skill）、單挑收場（戰報 kind seal＋紀錄；同一季才給名望）、沒打完、隱沒、管理者指定。
    收場那一下不改任何人的存檔（這一季沒上線過的持有者一同步就整個換成新角色，寫進去的會不見，FB-027），每個人自己同步時補；
    跨季才回來也補得到戰報與紀錄。補完照登記重抄抄本。"""
    c = ctx.content
    if not c.seal:
        return
    p = ctx.state.player
    reg = ctx.world.seal_state().registry
    fresh = [e for e in reg.history if e.seq > p.seal_seen]
    if not fresh:
        return
    p.seal_seen = max(e.seq for e in fresh)
    current, me = ctx.world.get_season_number(), seal.key(p.name)
    for e in fresh:
        if e.kind == "mandate":  # 天命之爭定下來（8.3）：那一刻手上有碎片的人以合璽之人留名；天命未定不寫
            mine = next((sid for sid, name in e.holders.items() if seal.key(name) == me and sid in c.seal), None)
            if mine is not None and e.result:
                line = seal.MANDATE_MINE.format(shard=c.seal[mine].name)
                ctx._write(seal.SEAL_TITLE, [line] + ([e.text] if e.text else []), tag=f"『{c.seal[mine].name}』")
                if e.season == current:
                    annals.note(ctx.state, c, annals.DEED, line, 5, place=e.where)
            continue
        if me not in (seal.key(e.holder), seal.key(e.other)) or e.shard not in c.seal:
            continue
        shard = c.seal[e.shard].name
        same = e.season == current
        if e.kind == "emerge":
            lines = [seal.GOT.format(shard=shard, effect=seal.shard_text(c, e.shard))]
            skill = c.config.seal.emerge_skill
            if same and skill and skill in c.skills and skill not in library.owned_arts(ctx.state) and not library.full(ctx.state, c):
                lines += learn_skill(ctx.state, c, skill)  # 混元一氣改給現世的得主（11.2 第 4 條）
            if same:
                annals.note(ctx.state, c, annals.DEED, e.text or lines[0], 5, place="")
            ctx._write(seal.SEAL_TITLE, lines, tag=f"『{shard}』")
        elif e.kind in ("take", "keep"):
            file_seal(ctx, e, shard, same)
        elif e.kind == "unsettled":
            other = e.other if seal.key(e.holder) == me else e.holder
            ctx._write(seal.SEAL_TITLE, [seal.UNSETTLED_MINE.format(other=other, shard=shard)], tag=f"『{shard}』")
        elif e.kind == "sink" and seal.key(e.other) == me:
            ctx._write(seal.SEAL_TITLE, [seal.SUNK_MINE.format(shard=shard)], tag=f"『{shard}』")
        elif e.kind == "recall" and seal.key(e.holder) == me:  # 喚回（8.2）：只拿碎片，不學 emerge_skill（要 PM 定的第 5 條）
            line = seal.RECALLED_MINE.format(where=e.where or "", shard=shard, effect=seal.shard_text(c, e.shard))
            ctx._write(seal.SEAL_TITLE, [line], tag=f"『{shard}』")
        elif e.kind == "scatter" and seal.key(e.other) == me:  # 天命之季之後七片散去（8.4）：抄本在最後的 copy_heirloom 照登記清掉
            ctx._write(seal.SEAL_TITLE, [seal.SCATTER_MINE.format(shard=shard)], tag=f"『{shard}』")
        elif e.kind == "assign" and seal.key(e.holder) == me:  # 管理者指定給你（公告不寫管理者，紀錄寫成拿到）
            ctx._write(seal.SEAL_TITLE, [seal.GOT.format(shard=shard, effect=seal.shard_text(c, e.shard))], tag=f"『{shard}』")
    copy_heirloom(ctx)


def file_seal(ctx, e, shard: str, same: bool) -> None:
    """一場奪璽單挑寫成自己的戰報（kind seal，回合一行一行；持有者的那份照挑戰者的翻過來寫）與一則紀錄；名望只在同一季才給（5.9）。"""
    c, s, cfg = ctx.content, ctx.state, ctx.content.config.seal
    challenger = e.holder if e.kind == "take" else e.other  # take：holder 是挑戰者、other 是失主；keep：holder 是持有者、other 是挑戰者
    mine = "challenger" if seal.key(challenger) == seal.key(s.player.name) else "holder"
    if mine == "challenger":
        other = e.other if e.kind == "take" else e.holder  # 挑戰者看的是持有者
    else:
        other = challenger  # 持有者看的是挑戰者
    won = e.result in duel_rules.WIN_VERDICTS
    if e.kind == "take":
        head, fame = (seal.WON, 0) if mine == "challenger" else (seal.LOST, cfg.fame["lose"])
    elif mine == "holder":
        head, fame = seal.KEPT, cfg.fame["keep"]
    else:
        head, fame = (seal.MISSED, cfg.fame["near"]) if won else (seal.FAILED, 0)
    notes = [head.format(other=other, shard=shard)] + ([e.text] if e.text else [])
    if mine in e.absent:  # 整場一手都沒自己出（FB-174）
        notes.append(seal.PROXY_LINE)
    elif mine in e.proxied:  # 自己出過手、只有幾回合逾時被代出；舊資料沒有 absent 也走這一句（比較溫和、一定是真的）
        notes.append(seal.PROXY_SOME_LINE)
    notes += [seal.FRESH_LINE] if mine == "holder" and e.fresh else []
    changes = []
    if same and fame:
        changes += renown.gain(s, c, "fame", fame)  # 加名望一律走 renown.gain（名聲設計 3.2）
    label = "" if same else f"第 {e.season} 季・"
    when = e.at if same and e.at is not None else s.world.time  # 單挑收場那一刻（FB-175）；跨季才回來照補送那一刻
    record = BattleRecord(
        id=s.battle_seq + 1, time=when, location=f"{label}{e.where or '陣前'}", kind="seal", event=f"『{shard}』",
        opponent=other, ours=[], tier=duel_rules.side_tier(e.result, e.edge, mine, c.config.duel), our_power=0.0, difficulty=0.0,
        notes=notes, changes=list(changes),
        rounds=list(e.lines),
    )
    battlelog.add_record(s, record)
    s.battle_card = record.id
    journal.add_entry(s, JournalEntry(time=when, title=f"{label}奪璽・『{shard}』", tag=notes[0], lines=notes[1:],
                                      changes=changes, battle_id=record.id))
    if same:
        annals.note(s, c, annals.DEED, notes[0], 5 if e.kind == "take" else 4, place=e.where, keep=[other])


def mandate_settle(ctx, winner: str, record: int | None, battle_name: str) -> None:
    """天命之爭定下來（8.3）：winner 是得天命的那一軍，"" 是天命未定（保底收場）。一次 world.mutate：這一季記下 mandate_result（季末
    的結局看它）、登記記一筆 mandate（這一刻每一片在誰手上＝合璽之人）、天下大事與江湖史各一句。不是天命之季、或已經定過，什麼都不做。
    settle 與管理者「定結果」叫它（經 Game 的委派 _mandate_settle）；可能跑在 Game.for_world，不碰 ctx.state.player。"""
    c = ctx.content
    if not seal.on(c):  # 主機中途關掉碎片：天命不定（季末照 world.end_season 寫天命未定），管理者「定結果」也一樣
        return
    names = {f.id: f.name for f in c.scenario.factions}

    def _apply(shared) -> None:
        season = shared.season
        if not season.mandate or season.mandate_result is not None:
            return
        reg = seal.filled(shared.seal, c)
        holders = {s.id: s.holder for s in reg.shards.values() if s.state == "held" and s.holder and s.id in c.seal}
        season.mandate_result = winner
        if winner:
            text = seal.MANDATE_WON.format(side=names.get(winner, winner))
            if holders:
                text += seal.MANDATE_NAMES.format(names="、".join(holders[s] for s in c.seal if s in holders))
        else:
            text = seal.MANDATE_UNSETTLED.format(battle=battle_name)
        seal.log(reg, shared.season_number, "mandate", result=winner, holders=holders, record=record, where=battle_name, text=text)
        seal.rumor(season, text)
        seal.chronicle(season, text)

    ctx.world.mutate(_apply)


def settle(ctx, battle: battle_instance.BattleInstance, definition: BattleDef, result: dict) -> None:
    """時刻表決戰收場時的玉璽碎片（事件 battle_end 的 seal 那一格：決戰包 progress.settle_showdown 發布；result 是算進伏筆鎖定的官方結果，
    不讀 battle.outcome_side，3.3）：璽動那一場決定要不要開奪璽單挑（Task 8），再從勝方挑現世的得主；後挑的排除前面挑中的人。
    只寫全服登記、單挑、天下大事、江湖史（一次 world.mutate），戰報那一行寫進這一場（mutate_battle 的 seal_notes）；
    兩人的存檔等各自同步時補（deliver_results，5.9）。可能跑在 Game.for_world（玩家是空白的），不碰 ctx.state.player。
    天命之季標了 seal 的前兩場另外喚回一片（8.2）；天命之爭只定天命（ctx._mandate_settle）。亂數全是 seal.dice，不碰 ctx.rng。"""
    c = ctx.content
    if not seal.on(c):
        return
    if seal.is_mandate_battle(c, definition):  # 天命之爭（8.3）：不璽動、不現世、不喚回、不掛單挑，只定天命
        winner = "" if seal.deserted(battle, definition) else str(result.get("side") or "")
        ctx._mandate_settle(winner, battle.record_id, definition.name)
        return
    cfg = c.config.seal
    view = ctx.world.seal_state()
    reg = seal.filled(view.registry, c)
    winner, margin = str(result.get("side") or ""), str(result.get("margin") or "")
    need = seal.threshold(battle, cfg)
    held = seal.holders(reg)
    picked: set[str] = set()
    notes: list[str] = []
    # 保底收場（end_without_fighters：兩軍都沒人還能打）：不打單挑、現世落空（設計 4.5 邊界 3、3.3）；小伺服器的旁觀散人也不補
    deserted = seal.deserted(battle, definition)
    duel = None
    shard_now = reg.shards.get(battle.seal_shard or "")
    if (not deserted and shard_now is not None and battle.seal_holder
            and seal.key(shard_now.holder) == seal.key(battle.seal_holder)):
        duel = duel_actions.challenge(ctx, battle, definition, reg, view.tianji, winner, margin, need, held)
        if duel is not None:
            picked.add(seal.key(duel.challenger.name))
            notes.append(seal.DUEL_NOTE.format(challenger=duel.challenger.name, holder=duel.holder.name))
    found = None
    emerge = reg.shards.get(battle.seal_emerge or "")
    if emerge is not None and emerge.state == "hidden" and not deserted:
        rows = seal.emerge_rows(battle, c, winner, need, held, picked)
        found = seal.weighted_pick(rows, seal.dice(reg.salt, view.tianji, "seal-emerge", battle.record_id), cfg.challenger_pool)
    recalled = None  # 喚回（8.2；PM 辛）：天命之季、標了 seal 的前兩場；排在挑戰者之後、排除剛挑去單挑的人；不算現世
    if seal.mandate_now(reg, view.season) and not deserted and definition.timetable_event in seal.recall_events(c):
        rows = seal.emerge_rows(battle, c, winner, need, held, picked)
        recalled = seal.roll_recall(reg, view.tianji, definition.timetable_event, rows, cfg.challenger_pool)
    shard_name = c.seal[battle.seal_emerge].name if battle.seal_emerge in c.seal else ""
    emerged = {"ok": False}

    def _apply(shared) -> None:
        reg_ = seal.filled(shared.seal, c)
        reg_.last_showdown, reg_.last_showdown_dueled, reg_.last_showdown_where = battle.record_id, False, definition.name
        if battle.seal_shard is not None and battle.seal_shard in c.seal:
            shard_label = c.seal[battle.seal_shard].name
            if duel is not None:
                shared.seal_duels.append(duel)
                reg_.last_showdown_dueled = True
                call = duel_rules.CALL if duel.challenger.name in battle.participants else duel_rules.CALL_QA  # 旁觀散人沒有「戰功居前」
                seal.rumor(shared.season, call.format(challenger=duel.challenger.name, holder=duel.holder.name, shard=shard_label))
            elif battle.seal_holder:
                seal.rumor(shared.season, seal.no_duel_text(c, battle.seal_holder, shard_label))  # 改版：不點名
        if battle.seal_emerge is None:
            return
        shard = reg_.shards[battle.seal_emerge]
        if found is None or shard.state != "hidden" or seal.key(found) in seal.holders(reg_):  # 落空：照舊未現世，只寫天下大事
            seal.rumor(shared.season, seal.EMERGE_LOST.format(battle=definition.name))
            return
        season = shared.season_number
        shard.state, shard.holder, shard.since_season, shard.emerged_round = "held", found, season, reg_.round
        reg_.emerge_season = season
        text = seal.EMERGE_GOT.format(name=found, battle=definition.name, shard=shard_name)
        seal.log(reg_, season, "emerge", shard=shard.id, holder=found, record=battle.record_id, text=text)
        seal.rumor(shared.season, text)
        seal.chronicle(shared.season, text)
        emerged["ok"] = True

    ctx.world.mutate(_apply)
    if recalled is not None:
        shard_id, name = recalled

        def _recall(shared) -> None:
            reg_ = seal.filled(shared.seal, c)
            shard = reg_.shards[shard_id]
            if shard.state != "sunk" or seal.key(name) in seal.holders(reg_):  # 寫入時重驗：這一刻已經不是隱沒、或他已經有一片
                return
            shard.state, shard.holder, shard.since_season, shard.absent = "held", name, shared.season_number, 0  # emerged_round 不動
            text = seal.RECALL.format(name=name, battle=definition.name, shard=c.seal[shard_id].name)
            seal.log(reg_, shared.season_number, "recall", shard=shard_id, holder=name, record=battle.record_id, where=definition.name,
                     text=text)
            seal.rumor(shared.season, text)
            seal.chronicle(shared.season, text)

        ctx.world.mutate(_recall)
    if emerged["ok"]:  # 寫入時重驗沒過（落空）就不寫戰報那一行
        notes.append(seal.EMERGE_NOTE.format(name=found))
    if notes:
        ctx.world.mutate_battle(lambda b: b.seal_notes.extend(notes) if b.record_id == battle.record_id else None)
