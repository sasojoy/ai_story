"""奪璽單挑的玩法（全部拆包第 28 批從 Game 搬來，計畫 docs/superpowers/plans/2026-11-06-玉璽包-第2批.md；Game 留一行委派）：
璽動那一場收場挑挑戰者與開單挑（challenge、challengers、spectators、side_of）、單挑往前推（tick）、選單上的三招與出招（options、act）、
放手一搏的輸入框與兩段（free_text_prompt、free_text_note、text_request、gamble）、江湖頁的奪璽卡與背景輪詢（duel_card、watch）。

- 純規則在同包的 duel_rules.py（一律照模組屬性叫 duel_rules.<名字>：scripts/measure_seal.py 換掉 duel_rules.finish／resolve／open_round）。
- challenge 裡的 challengers、spectators 一定經 ctx 叫（scripts/measure_seal.py 換的是 Game._seal_challengers／_seal_spectators）；
  叫回 Game 的都經 ctx：_log、_write、_deliver_seal_results、_quick_client、_kin、_load_kin、_showdown_status、_duel_side、now、state、world、content。
- 方法本體文字、先後、訊息一個字不改（self 換成 ctx）。
"""
from __future__ import annotations

from tianxia import atlas, attrset, gender, roster, tactics, team  # 共用規則層
from tianxia.core import battle_base as battle_instance  # 決戰的資料型別與判定（第 54 批進核心）
from tianxia import prologue as prologue_rules
from tianxia.characters import CharacterStore
from tianxia.core import duel_base
from tianxia.core.option import Option
from tianxia.core.services import PAUSED_TEXT
from tianxia.models import FREE_TEXT_MAX, MOVES, BattleDef
from tianxia.state import new_game_state
from tianxia.world_state import SealDuel, SealSide

from . import duel_rules, seal


def challenge(ctx, battle, definition: BattleDef, reg, tianji: int, winner: str, margin: str, need: int, held: set[str],
) -> SealDuel | None:
    """璽動那一場收場：持有者那一方打得怎樣（照璽動那一刻的快照，4.5）；不是大勝就挑挑戰者（4.6）、照 5.3 抓雙方的快照、開一場
    下戰書的單挑（還沒寫進去，呼叫端的 world.mutate 寫）。挑不出人回 None（懷璽不失、算動過）。"""
    cfg = ctx.content.config.seal
    holder = battle.seal_holder
    snap = battle.seal_holder_side
    moved = snap is not None and ctx.world.faction_of(holder) != battle.seal_holder_faction  # 璽動之後陣營變了：算旁觀、不套過濾
    side = None if moved else snap
    tier = seal.tier_for(side, winner, margin)
    if tier == "大勝" or not winner:
        return None
    armies = [f.id for f in definition.factions]
    foe = winner if side is None else next((f for f in armies if f != side), winner)
    blocked = None if side is None else battle.seal_holder_faction  # 只在快照陣營沒變時擋「自己人合演轉手」
    rows = ctx._seal_challengers(battle, foe, need, holder, blocked, held)
    if len(battle.participants) < cfg.small_battle:
        rows += ctx._seal_spectators(definition, battle, held)
    shard = reg.shards[battle.seal_shard]
    name = seal.weighted_pick([(n, m) for n, m, _ in rows], seal.dice(reg.salt, tianji, "seal-duel", battle.record_id),
                              cfg.challenger_pool, prefer=shard.former)
    if name is None:
        return None
    challenger = next(s for n, _, s in rows if n == name)
    me = battle.participants.get(holder)
    guarded = me is not None and me.acted_rounds >= need  # 護璽：自己出手滿門檻（臨時投效的散人也算，只多這一條，4.5）
    keeper = duel_rules.side_from_participant(me, battle.seal_holder_faction) if me is not None else side_of(ctx, holder)
    cap = min(cfg.cap, cfg.cap * cfg.side_factor.get(tier, 0.0) * (cfg.guard if guarded else 1.0))
    duel_rules.faced(ctx.content, challenger, keeper)  # 五項屬性的季：兩邊照對方真正的五項重算；舊的季不動
    return duel_rules.open_duel(
        f"{battle.record_id}:{shard.id}", shard.id, battle.record_id, definition.timetable_event, definition.name, tier, cap,
        challenger, keeper, ctx.now, cfg,
    )

def challengers(ctx, battle, side: str, need: int, holder: str, blocked: str | None, held: set[str]) -> list:
    """挑戰者的候選（4.6）：那一邊（交戰兩軍之一）的參戰者、自己出手滿 need 回合、不是持有者、手上沒有碎片、這一季沒叛投過與
    不在新手期（加入時的快照）、此刻名冊上的陣營不跟持有者的快照陣營相同（blocked；None 不擋）。回（名號, 戰功, 快照）；不看假人。"""
    tuning = ctx.content.config.battle
    out = []
    for p in battle.participants.values():
        if p.faction != side or not seal.challenger_ok(p, need, held, holder):  # 同畫面那一句（hint_names，FB-177）
            continue
        now_faction = ctx.world.faction_of(p.name)
        if blocked is not None and now_faction == blocked:
            continue
        out.append((p.name, battle_instance.merit(tuning, p), duel_rules.side_from_participant(p, now_faction)))
    return out

def spectators(ctx, definition: BattleDef, battle, held: set[str]) -> list:
    """小伺服器的退路（PM 癸；計畫「要 PM 定的」第 2 條）：收場那一刻人在決戰的大區、presence_seconds 內同步過、不在路上、名冊上
    不是交戰兩軍（散人、地方豪強：Joy 2026-10-13 起豪強在決戰跟散人一樣臨時投效）、不是參戰者也不是持有者、不在新手期與序章、這一季沒叛投過、手上沒有碎片的人。戰功當 0；身手照他的存檔算（不存回去）。"""
    if not hasattr(ctx.world, "db") or definition.region is None:
        return []
    store = CharacterStore(ctx.world.db)
    since = ctx.now - ctx.content.config.presence_seconds
    region = definition.region
    armies = {f.id for f in definition.factions}
    here = [loc for loc in ctx.content.locations if (r := atlas.region_of(ctx.content, loc)) is not None and r.id == region]
    out = []
    for loc in here:
        for state in store.present(loc, since):
            name = state.player.name
            if (name in battle.participants or seal.key(name) == seal.key(battle.seal_holder) or seal.key(name) in held
                    or state.player.journey is not None or state.player.defected or ctx.world.faction_of(name) in armies):
                continue
            kin = ctx._kin(state)
            if roster.newbie(kin.state, ctx.content) or prologue_rules.active(kin.state, ctx.content):
                continue
            out.append((name, 0, duel_rules.side_from(  # 不含玉璽碎片的戰力（改版：奪璽單挑不吃；手上有碎片的本來就擋掉了）
                name, None, kin._battle_power(seal=False), kin._battle_scores(mounted=False, seal=False), kin._battle_role(),
                kin._battle_neili_cap(), kit=team.self_side(kin.state, ctx.content, kin.world), cut=kin._duel_cut(),  # 防具照他的存檔現算（3.9）
                card=team.pvp_card(kin.state, ctx.content, kin.world),
            )))
    return out

def side_of(ctx, name: str) -> SealSide:
    """沒參戰的持有者的快照（5.3）：觸發結算的人就是他用 ctx；否則讀他的存檔建一份不叫模型的 Game（不 sync、不存回、不記 last_seen），
    讀不到（沒有資料庫）就照新角色。這一季沒上線過（seen_real，舊存檔退回 last_real，早於 opened_real；opened_real 是 None 一律當
    上線過）記成 fresh、身手照新角色。"""
    opened = ctx.world.seal_state().registry.opened_real
    game = ctx if seal.key(ctx.state.player.name) == seal.key(name) else (ctx._load_kin(name) or ctx._kin(new_game_state(ctx.content, name)))
    seen = game.state.player.seen_real if game.state.player.seen_real is not None else game.state.last_real
    fresh = opened is not None and (seen is None or seen < opened)
    if fresh and game is not ctx:
        game = ctx._kin(new_game_state(ctx.content, name))
    return duel_rules.side_from(  # 不含玉璽碎片的戰力（改版：奪璽單挑不吃，碎片才搶得走）
        name, ctx.world.faction_of(name), game._battle_power(seal=False), game._battle_scores(mounted=False, seal=False),
        game._battle_role(), game._battle_neili_cap(), fresh=fresh, kit=team.self_side(game.state, ctx.content, game.world),
        cut=game._duel_cut(),  # 沒參戰的持有者：防具照他的存檔現算（鐵匠鋪與合成流程 3.9；fresh 的是新角色，沒穿＝0）
        card=team.pvp_card(game.state, ctx.content, game.world),
    )

def my_duel(ctx) -> tuple[SealDuel | None, str | None]:
    """排第一的那一場奪璽單挑，與自己是哪一邊（不在裡面是 None）。"""
    duels = ctx.world.seal_state().duels if seal.on(ctx.content) else []
    if not duels:
        return None, None
    return duels[0], duel_rules.side_of(duels[0], ctx.state.player.name)

def tick(ctx) -> None:
    """把奪璽單挑推到現在（5.4）：options(tick=True) 與 world_tick 叫，一次最多結算一回合。自己的請求（own_request）而且自己是一方時
    順便記 last_seen（15 秒最多寫一次）。先讀一次 world 那一列，沒事做就不開 mutate（每 10 秒的輪詢不寫）。季、角色都不動；
    自己是一方就順便補給自己（_deliver_seal_results，Task 10）。"""
    if not seal.on(ctx.content):
        return
    view = ctx.world.seal_state()
    if not view.duels or view.paused:
        return
    duel = view.duels[0]
    me = ctx.state.player.name
    who = duel_rules.side_of(duel, me) if me else None
    cfg = ctx.content.config.seal
    if not duel_rules.needs_write(duel, who, ctx.now, cfg, own=ctx.own_request, ended=ctx.state.world.ended):
        return

    def _apply(shared) -> None:
        if ctx.own_request and who is not None and shared.seal_duels and shared.seal_duels[0].id == duel.id:
            duel_rules.note_seen(shared.seal_duels[0], who, ctx.now, cfg)
        duel_rules.advance(shared, ctx.content, ctx.now)

    ctx.world.mutate(_apply)
    ctx._deliver_seal_results()  # 自己是一方、剛好由自己收場時當場看得到（不是一方時什麼都不做）

def options(ctx) -> list[Option]:
    """單挑的一方、這一場開打了：三招（寫剋哪一招）擺在選單最前面；送過了換成一顆灰的「已出招」；這一回合判成不在場的三招灰掉、
    寫中性的字（5.5，不寫代打）。放手一搏走輸入框（seal_free_text_prompt，Task 9），選單上沒有。"""
    duel, who = my_duel(ctx)
    if duel is None or who is None or duel.phase != "active":
        return []
    cfg = ctx.content.config.seal
    problem = duel_rules.submit_problem(duel, who, cfg)
    if problem == duel_rules.SENT:
        left = max(0, int((duel.opened_real or ctx.now) + cfg.round_seconds - ctx.now))
        label = f"（{duel_rules.SENT}：已出招 {duel_rules.sent(duel)}／2，最遲 {left // 60} 分 {left % 60} 秒）"
        return [Option(id="seal:waiting", label=label, enabled=False)]
    late = f"（{problem}）" if problem else ""
    held = tactics.locks(duel.bout, duel_rules.BOUT_SIDE[who]).no_moves  # 本命戰法：卸勁、只攻不守
    return [Option(id=f"seal:{m}", label=duel_base.move_label(m) + late + (tactics.lock_note(m) if m in held else ""),
                   enabled=problem is None and m not in held) for m in MOVES]

def act(ctx, move: str) -> list[str]:
    """選單上的一招（seal:<招>）：在一次 world.mutate 裡重驗、記下這一手，然後推一步（湊齊了而且滿 20 秒才結算）。"""
    if move not in MOVES:
        return ["（此刻無法這麼做。）"]
    out: list[str] = []
    me, cfg = ctx.state.player.name, ctx.content.config.seal

    def _apply(shared) -> None:
        duel = shared.seal_duels[0] if shared.seal_duels else None
        who = duel_rules.side_of(duel, me) if duel is not None else None
        problem = duel_rules.GONE if who is None else duel_rules.submit_problem(duel, who, cfg)
        if not problem and move in tactics.locks(duel.bout, duel_rules.BOUT_SIDE[who]).no_moves:
            problem = tactics.NO_MOVE.strip("（）").format(move=move)
        if problem:
            out.append(f"（{problem}）")
            return
        duel_rules.submit(duel, who, move=move)
        duel_rules.note_seen(duel, who, ctx.now, cfg)
        out.append(f"你出了{move}。")
        out.extend(duel_rules.advance(shared, ctx.content, ctx.now))

    ctx.world.mutate(_apply)
    ctx._deliver_seal_results()
    return out

def free_text_prompt(ctx) -> str | None:
    """奪璽單挑的放手一搏輸入框（5.7）：自己是一方、這一回合在場、還沒出手、這一場還沒搏滿兩次才有。"""
    duel, who = my_duel(ctx)
    if duel is None or who is None or duel_rules.submit_problem(duel, who, ctx.content.config.seal, text=True):
        return None
    return duel_rules.PROMPT

def free_text_note(ctx) -> str | None:
    return duel_rules.GAMBLE_NOTE if free_text_prompt(ctx) is not None else None

def text_request(ctx, text: str) -> duel_rules.TextRequest | list[str]:
    """奪璽放手一搏的 A 段（鎖內、只讀，5.7）：驗證他是這場單挑的一方、這一回合開始時判他在場、還沒送出、還能搏、文字 20 字以內，
    開單子（單挑 id、回合、哪一邊、文字、名號、場景、對手那一行）。判成不在場的這一回合不開單。"""
    if ctx.world.paused_at() is not None:
        return [f"（{PAUSED_TEXT}。）"]
    duel, who = my_duel(ctx)
    if duel is None or who is None:
        return ["（此刻無法這麼做。）"]
    problem = duel_rules.submit_problem(duel, who, ctx.content.config.seal, text=True)
    if problem:
        return [f"（{problem}）"]
    text = text.strip()[:FREE_TEXT_MAX]
    if not text:
        return ["（請先輸入你想做的事。）"]
    me, foe = getattr(duel, who), getattr(duel, duel_rules.other(who))
    title, scene_text = duel_rules.scene(duel, who, ctx.content)
    return duel_rules.TextRequest(
        duel=duel.id, round=duel.round, side=who, text=text, name=me.name, faction_name=ctx._duel_side(),
        title=title, scene=scene_text, target=duel_rules.foe_line(me, foe, ctx.content), sex=gender.of(ctx.state),
    )

def gamble(ctx, text: str, rate: int | None = None, stories: tuple[str, str] | None = None,
    request: duel_rules.TextRequest | None = None,
) -> list[str]:
    """奪璽放手一搏的 C 段（5.7）：鎖內重驗，同一場、同一回合、同一邊、同一句才採用，記進 pending（送出不等於結算，湊齊而且滿 20 秒才算）。
    回合對不上直接回「這一回合已經結算」，不重評、不套用（鎖內重評會把第 r 回合寫的那一句套到第 r＋1 回合；頭目戰、擂台同一條）。
    沒給 request（腳本、測試）就在這裡開單；沒給分數就用 _quick_client 在鎖內評，評不到是 40。"""
    if request is None:
        request = text_request(ctx, text)
        if isinstance(request, list):
            return ctx._log(request)
    if rate is None:
        verdict = battle_instance.assess_gamble(
            ctx._quick_client(), duel_base.Scene(request.title, request.scene), request.faction_name, request.text, request.name,
            setting=duel_rules.SETTING, place=duel_rules.PLACE, target=request.target, sex=request.sex,
        )
        rate, stories = verdict.rate, (verdict.win, verdict.lose)
    checked = text.strip()[:FREE_TEXT_MAX]
    me, cfg = ctx.state.player.name, ctx.content.config.seal
    out: list[str] = []

    def _apply(shared) -> None:
        duel = shared.seal_duels[0] if shared.seal_duels else None
        if duel is None or duel.id != request.duel or duel.round != request.round or duel.phase != "active":
            out.append(f"（{duel_rules.GONE}）")
            return
        who = duel_rules.side_of(duel, me)
        if who != request.side or checked != request.text:
            out.append(f"（{duel_rules.RESEND}）")
            return
        problem = duel_rules.submit_problem(duel, who, cfg, text=True)
        if problem:
            out.append(f"（{problem}）")
            return
        charmed = None if rate is None else int(rate) + round(attrset.charm(ctx.state, ctx.content, "gamble"))  # 魅力（五項屬性的季）
        duel_rules.submit(duel, who, text=checked, rate=charmed, stories=stories)
        duel_rules.note_seen(duel, who, ctx.now, cfg)
        out.append(f"你放手一搏：「{checked}」")
        out.extend(duel_rules.advance(shared, ctx.content, ctx.now))

    ctx.world.mutate(_apply)
    ctx._deliver_seal_results()
    return ctx._log(out)

def duel_card(ctx) -> dict | None:
    """江湖頁的「奪璽」卡（5.10）：排第一的那一場，全服看得到；沒有是 None。"""
    duels = ctx.world.seal_state().duels if seal.on(ctx.content) else []
    if not duels:
        return None
    paused = ctx.world.paused_at()  # 暫停中倒數停在按下暫停的那一刻（同決戰那一格，FB-179）
    return duel_rules.card(duels[0], ctx.state.player.name or None, ctx.now if paused is None else paused, ctx.content)

def watch(ctx) -> bool:
    """網頁在背景也要輪詢（5.5）：自己是單挑的一方；或此刻有一場被璽動、還沒收場的決戰，自己是那一片的持有者或那一場的參戰者
    （挑戰者要到收場才確定）。"""
    if not seal.on(ctx.content):
        return False
    _, who = my_duel(ctx)
    if who is not None:
        return True
    status = ctx._showdown_status(tick=False)  # 璽動只在時刻表決戰（攻城戰不璽動）
    if status is None or not status[0].seal_shard:
        return False
    battle, me = status[0], ctx.state.player.name
    return seal.key(battle.seal_holder) == seal.key(me) or me in battle.participants
