"""切磋的動作（功能包 tianxia/features/peers/；原本是 Game 上的 _spar_problem、_spars_left、_spar_answer_problem、spar_refusal、spar_invite、_spar、
_spar_record；全部拆包第 38 批搬進來，行為一個字不變）。ctx 是 Game；只叫 tianxia/core/services_list.md 那張清單上的方法。

切磋掛在玩家卡上（spar.py 登記進 social.ACTIONS）：發邀請、答應、婉拒、收回都是按的那個人自己的動作，在他自己那一把行動鎖裡做；
對方那一份照 social 的做法拿（actions.peer：此刻在這裡的人、不補算時間、賽季接上這一份），做完存回去。邀請存在這一季的 WorldState.invites。
who_problem 論武、截殺也問（what 換字）。「是假人」不影響任何一句話。
encounter.resolve_encounter 一律用模組屬性叫（same_behavior 與 tianxia/features/peers/tests/test_raid.py 換掉這個屬性來強制勝負）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import battlelog, encounter, gender, prologue as prologue_rules, team
from tianxia.core import presence
from tianxia.models import Squad
from tianxia.rules import season_one

from . import invite_actions, invites, pair_actions, social

if TYPE_CHECKING:
    from tianxia.engine import Game


def who_problem(ctx, who: Game, *, me: bool, what: str = "切磋", cost: int | None = None) -> str | None:
    """這個人此刻能不能切磋（論武也問這一個，what 換成「論武」）：拒絕的話；能是 None。不在序章、閒著（Game.is_idle：
    不在事件、路上、閉關、決戰裡）、體力付得起（cost 沒給是一次遊歷）。me 是說話的人自己（「你」），不然寫對方的名號。"""
    s, c = who.state, ctx.content
    name = "你" if me else s.player.name
    if prologue_rules.active(s, c):
        return f"{name}還在草廬學藝，下山之後才能{what}。"
    if not who.is_idle():
        return f"{name}此刻正忙，騰不出手來{what}。"
    cost = c.config.action_cost["train"] if cost is None else cost
    if s.player.stamina < cost:
        return f"{name}體力不夠（{what}要 {cost} 點）。"
    return None


def left(ctx, other: str) -> int:
    """這一對人這個遊戲日還能切磋幾場（Spar.per_pair_day）。"""
    return pair_actions.pair_left(ctx, ctx.state.world.spar_tally, ctx.content.config.spar.per_pair_day, other)


def answer_problem(ctx, inv, other: Game, *, for_sender: bool = False) -> str | None:
    """答應切磋時這一場還打不打得成：還在發邀請的那個地點、兩個人都閒著付得起體力、這一對這個遊戲日還沒打滿。
    for_sender：寫給發邀請的那個人看（「你」是他，_tell_sender 用）。"""
    if inv.location != ctx.state.player.location:
        return presence.GONE
    for who in (ctx, other):
        problem = who_problem(ctx, who, me=(who is ctx) != for_sender)
        if problem is not None:
            return problem
    if left(ctx, other.state.player.name) <= 0:
        return social.pair_full(ctx, "spar")
    return None


def refusal(ctx, other: Game) -> str | None:
    """玩家卡上「切磋」按不按得下去（拒絕的話；能是 None）：規則開著、兩個人都閒著、付得起體力、今天這一對還沒打滿、
    之間沒有一張還在等的邀請。休季（這一季收了）卡上不畫，直接打 API 也是這一句（FB-169）。"""
    s, c = ctx.state, ctx.content
    if not season_one(c, s.world) or s.world.ended:
        return "（此刻無法這麼做。）"
    for who, me in ((ctx, True), (other, False)):
        problem = who_problem(ctx, who, me=me)
        if problem is not None:
            return problem
    if left(ctx, other.state.player.name) <= 0:
        return social.pair_full(ctx, "spar")
    if invites.between(s.world, s.player.name, other.state.player.name, "spar") is not None:
        return "已經有一張切磋的邀請在等回覆了。"
    return None


def send(ctx, other: Game) -> list[str]:
    """玩家卡上的「切磋」：向這個人發一張邀請，他在 invite_ttl_seconds 內答應才打。被拒絕只回一句話。"""
    s = ctx.state
    problem = refusal(ctx, other)
    if problem is not None:
        return [problem]
    name = other.state.player.name
    invites.expire(s.world)
    invites.send(s.world, ctx.content, "spar", s.player.name, name, s.player.location)
    ctx._save_season()
    ctx.touched.add(name)  # 他的選單、他看你的那張卡要多出答應、婉拒
    him = gender.pronoun(other.state)
    return [f"你向{name}抱拳，邀{him}過幾招；等{him}回覆。"]


def spar(ctx, inv, other: Game) -> list[str]:
    """答應一場切磋：重驗（還在發邀請的那個地點、兩個人都閒著、體力付得起、今天這一對還沒打滿），雙方各花一次遊歷的體力，
    用本人的威力照單次判定打一場（從發邀請的那一方算，收的一方照鏡像），不扣氣血、不掉銀兩；雙方各一份戰報（回合演出不帶數字）
    與一則江湖紀錄，經驗與心得照 Config.spar。驗不過就把邀請收掉（answer_invite 已經收了）、說一句為什麼，發邀請的那個人也收到一句。"""
    c = ctx.content
    me, them = ctx.state.player, other.state.player
    problem = answer_problem(ctx, inv, other)
    if problem is not None:
        invite_actions.tell_sender(ctx, inv, other, answer_problem(ctx, inv, other, for_sender=True))
        return [problem]
    cost = c.config.action_cost["train"]
    me.stamina -= cost
    them.stamina -= cost
    pair_actions.pair_tick(ctx, ctx.state.world.spar_tally, them.name)
    ctx._save_season()
    ours, theirs = ctx._spar_power(ctx, other), ctx._spar_power(other, ctx)
    ours_shown, theirs_shown = ctx._spar_power(ctx, other, seal=False), ctx._spar_power(other, ctx, seal=False)  # 戰報給對方看的（先算：記完戰報可能升級）
    result = encounter.resolve_encounter(theirs, ours, ctx.rng)  # 從發邀請的那一方看：他的威力對上你的
    spar_record(other, result, me.name, ours, ctx, shown=ours_shown)
    return spar_record(ctx, ctx._spar_mirror(result, ours), them.name, theirs, other, shown=theirs_shown)


def spar_record(ctx, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
                 *, shown: float | None = None) -> list[str]:
    """這一邊的戰報、獎勵與紀錄。對手寫成一支只為這一場存在的隊伍（名號、威力、身上那一門的屬性），戰報只列本人。
    shown：戰報上「對手威力 N」寫的數字＝對手不含玉璽碎片的威力（改版 FB-615；打起來照 result，含碎片）；不給就照 result。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.spar
    p = s.player
    squad = Squad(
        id=f"spar:{rival}", name=rival, difficulty=rival_power,
        attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
    )
    record = battlelog.new_record(s, c, ctx.world, squad, result, "spar")
    if shown is not None:
        record.difficulty = shown
    record.ours = record.ours[:1]
    xinde = cfg.win_xinde if result.tier in team.WIN_TIERS else cfg.draw_xinde if result.tier in team.DRAW_TIERS else cfg.lose_xinde
    p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
    record.xinde = xinde
    before = p.member.level
    maxed_note = ctx._record_exp(record, cfg.exp, "spar")  # 先換（滿級才換）；升到滿級那一下剩下的不換
    ups = team.add_exp(c, p.member, cfg.exp, p.name, "spar")  # 切磋是仗（減法季 45 級以後照算）
    if p.member.level > before:
        points = team.level_points(ctx.state, c, before, p.member.level)
        p.stat_points += points
        if points:
            ups.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
    record.notes += [n for n in maxed_note if not n.startswith("心得 +")]  # 戰報敘事只留那一句；心得算在得失
    record.notes += ups
    ctx._play_rounds(record, squad, result.tier, None)
    line = ctx._file_battle(record, team_exp=False)
    # 兩邊對稱（FB-244）：各寫各自拿到的經驗與心得（只有本人拿，不寫「（每人）」）、各連自己的戰報
    msgs = [line] + ([f"經驗 +{cfg.exp}"] if record.exp else []) + [f"心得 +{xinde}"] + maxed_note + ups + ctx._last_wear  # 滿級不寫經驗（FB-451）
    if ctx._draft is None:  # 對方那一邊（或從玩家卡答應、沒有草稿）：替他記一則，連到這一份戰報
        ctx._write(f"切磋・{rival}", msgs, tag=battlelog.outcome_text(record), battle_id=record.id)
    else:  # 答應的那一方（自己按的，這次行動的草稿寫這一則）：結果那一句照樣寫進敘事，跟發邀請的那一方一樣（FB-117）
        ctx._draft.keep(line)
    return msgs
