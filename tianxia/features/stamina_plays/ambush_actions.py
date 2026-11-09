"""設伏劫道的動作（功能包 tianxia/features/stamina_plays/；原本是 Game 上的 _ambush_*，開發規範手冊 3.2）。
ctx 是 Game（第一階）；只叫 tianxia/core/services_list.md 那張清單上的方法。Game 上的名字掛在 game_api.py 的表（sync、_arrivals、測試與腳本叫的）。
_ambush_fight、_ambush_spoils、_ambush_record 是兩個人之間的事：路過的人（ctx）中了 owner 的埋伏，函式帶兩個 ctx，不把 self 當唯一的人。
encounter.resolve_encounter 一律用模組屬性叫（same_behavior 的 stamina 軌換掉這個屬性來強制伏兵必勝／必敗）。"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia.core import jieyi_base  # 結義第一批「替兄出頭」：伏兵打贏、被埋伏的人有結義兄弟就記一筆仇（開關關著不動）
from tianxia import battlelog, calendar, encounter, four_tiers, gender, prologue, roster, team, wins
from tianxia.characters import name_key
from tianxia.core.services import RaidSpoils
from tianxia.models import Squad
from tianxia.rules import season_one
from tianxia.state import PLAYER

from . import ambush_rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def act(ctx: Game, arg: str) -> list[str]:
    """設伏（ambush:set:<另一頭>）或收伏（ambush:lift）。設伏：重驗、扣體力、季上與角色身上各記一筆。收伏：季上那一筆記收起的時刻。"""
    s, c = ctx.state, ctx.content
    p = s.player
    verb, _, to = arg.partition(":")
    if verb == "lift":
        if p.ambush is None:
            return ["（此刻無法這麼做。）"]
        ambush_rules.lift(s.world, p.ambush, p.name, s.world.time)
        p.ambush = None
        return [ambush_rules.LIFTED]
    cost = c.config.ambush.stamina
    problem = ambush_rules.set_problem(s, c, to)
    if problem is None and p.stamina < cost:
        problem = f"體力不夠（要 {cost} 點）"
    if problem is not None:
        return [problem if problem.startswith("（") else f"（{problem}。）"]
    p.stamina -= cost
    a = ambush_rules.place(s, c, to)
    if ctx._draft is not None:
        ctx._draft.changes.append(f"體力 -{cost}")
    return [ambush_rules.SET_DONE.format(to=c.locations[to].name, until=ctx.stamp(a.until))]


def expire(ctx: Game) -> None:
    """同步時：守著的埋伏到了時刻、或季上那一筆已經不在了（被路過的人打退時季上記了收起、角色那一筆一起清；換季的新季沒有這一筆），
    收起來。到時刻的寫一則江湖紀錄。"""
    s = ctx.state
    post = s.player.ambush
    if post is None:
        return
    if ambush_rules.mine_now(s.world, post, s.player.name) is None:
        s.player.ambush = None
        return
    if ambush_rules.expired(s):
        s.player.ambush = None
        ctx._write(ambush_rules.TITLE, [ambush_rules.EXPIRED.format(to=ctx.content.locations[post.to].name)])


def check(ctx: Game, a: str, b: str, when: float) -> list[str]:
    """路過的人（ctx）在 when 那一刻走完 a—b 那一段：這一段當時有沒有敵對的伏兵。每換一段只查一次字典（WorldState.ambushes[路段鍵]），
    真的要打才讀伏兵的存檔。保護照截殺：雙方過了新手期、同一個伏兵劫同一個人的冷卻、剛被截過的護身（照 when 比）。一段只打一場。"""
    s, c = ctx.state, ctx.content
    w = s.world
    if not w.ambushes or not ambush_rules.on(c):
        return []
    found = w.ambushes.get(ambush_rules.key(a, b))
    if not found:
        return []
    me = s.player
    if prologue.active(s, c) or roster.raid_newbie(s, c):
        return []
    cfg, shield = c.config.ambush, c.config.raid.shield_seconds
    hit = w.raided.get(name_key(me.name))
    if hit is not None and abs(when - hit) < shield:
        return []
    side = ctx._side()
    for amb in sorted(found, key=lambda x: x.set_at):
        if not (amb.set_at <= when < ambush_rules.end_of(amb)) or name_key(amb.owner) == name_key(me.name):
            continue
        if not ambush_rules.maybe_hostile(w, amb, side, me.name):  # 自己人：不必讀他的存檔
            continue
        last = w.raids.get(ctx._raid_key(amb.owner, me.name))
        if last is not None and abs(when - last) < cfg.pair_cooldown_seconds:
            continue
        owner = ctx._load_kin(amb.owner)
        if owner is None or roster.raid_newbie(owner.state, c):
            continue
        if not ambush_rules.hostile(owner.state, s, c):
            continue
        return fight(ctx, owner, amb, when)
    return []


def fight(ctx: Game, owner: Game, amb, when: float) -> list[str]:
    """路過的人（ctx）中了 owner 的埋伏：記冷卻與護身、用本人的威力照單次判定打一場（從伏兵看；亂數用自己的種子，不動 Game.rng），
    贏的搶走輸的一點銀兩與素材、輸的扣氣血（spoils）。伏兵輸了，埋伏散了。雙方各一份戰報；伏兵的存檔在這裡寫回，
    季（冷卻、埋伏的紀錄、通緝交差）由路過的人的 sync／travel 最後一起存。"""
    s, c = ctx.state, ctx.content
    w, me = s.world, s.player
    key = ctx._raid_key(amb.owner, me.name)
    w.raids[key] = max(w.raids.get(key, when), when)
    w.raided[name_key(me.name)] = max(w.raided.get(name_key(me.name), when), when)
    amb.caught += 1
    ours, theirs = ctx._spar_power(owner, ctx), ctx._spar_power(ctx, owner)
    ours_shown, theirs_shown = ctx._spar_power(owner, ctx, seal=False), ctx._spar_power(ctx, owner, seal=False)  # 戰報給對方看的（FB-615）
    result = encounter.resolve_encounter(ours, theirs, random.Random(f"設伏|{amb.owner}|{me.name}|{when}"))
    mirrored = ctx._spar_mirror(result, theirs)
    if result.tier in team.WIN_TIERS:
        winner, loser = owner, ctx
    elif mirrored.tier in team.WIN_TIERS:
        winner, loser = ctx, owner
    else:
        winner = loser = None
    got = spoils(winner, loser) if winner is not None else None
    broke = loser is owner
    if broke:  # 伏兵被打退：埋伏散了（身上那一筆是這一處才清：下線的人晚補算時，伏兵可能已經另設了一處）
        post = owner.state.player.ambush
        if post is not None and ambush_rules.mine_now(w, post, amb.owner) is amb:
            owner.state.player.ambush = None
        amb.lifted_at = max(amb.set_at, when)
    ctx.touched.add(amb.owner)
    record(owner, result, me.name, theirs, ctx, got, as_owner=True, shown=theirs_shown,
           extra=[ambush_rules.BROKEN.format(rival=me.name, to=c.locations[amb.to].name)] if broke else [])
    msgs = record(ctx, mirrored, owner.state.player.name, ours, owner, got, as_owner=False, shown=ours_shown)
    if winner is owner:
        jieyi_base.record_feud(owner, me.name, owner.state.player.name)
        owner._raid_bounty(me.name)  # 伏兵揭了通緝他：交差（寫在伏兵自己的紀錄）
    elif winner is ctx:
        msgs += ctx._raid_bounty(owner.state.player.name)
    ctx._save_kin(owner)
    return msgs


def spoils(ctx: Game, loser: Game) -> RaidSpoils:
    """贏的是 ctx：loser 失銀兩（比例、有上限）、幾個素材（手上最多的、一階先），ctx 拿走（Joy：輸的東西被搶走）；loser 扣氣血上限的
    hp_loss（乘 1−他身上防具的減損；不吃化勁、不變成內傷，同截殺）；第一季規則開著時 ctx 記一點貢獻。"""
    c, cfg = ctx.content, ctx.content.config.ambush
    lp, wp = loser.state.player, ctx.state.player
    purse = lp.stats.get("silver", 0)
    lost = min(cfg.silver_cap, math.ceil(purse * cfg.silver_share)) if purse > 0 else 0
    taken = math.ceil(lost * cfg.take_share)
    lp.stats["silver"] = purse - lost
    wp.stats["silver"] = wp.stats.get("silver", 0) + taken
    goods: list[tuple[str, int]] = []
    left = cfg.materials
    held = sorted(  # 四階搶不走（正式季整合 4.6：四階不在人與人之間轉手）
        ((mid, n) for mid, n in lp.materials.items() if n > 0 and mid in c.materials and not four_tiers.tier4_id(c, mid)),
        key=lambda item: (c.materials[item[0]].tier, -item[1], item[0]),
    )
    for mid, n in held:
        if left <= 0:
            break
        got = min(n, left)
        lp.materials[mid] = n - got
        if lp.materials[mid] <= 0:
            del lp.materials[mid]
        wp.materials[mid] = wp.materials.get(mid, 0) + got
        goods.append((mid, got))
        left -= got
    con = team.con_of(loser.state, c, loser.world, PLAYER)
    cut = team.armor_cut(loser.state, c, loser.world)
    hp, _ = team._apply_toll(c, lp.member, cfg.hp_loss * (1 - cut), agi=team.v1_stat(loser.state, c, "agi"), con=con, injury=0.0,
                             season=loser.state.world)
    contrib = c.config.contrib_per_push * cfg.win_contrib_push if wp.faction is not None and season_one(c, ctx.state.world) else 0
    if contrib:
        wins.credit(wp, c, ctx.state.world, calendar.point(ctx.state.world.time, c, ctx.state.world).week, contrib)
    return RaidSpoils(winner=wp.name, lost=lost, taken=taken, hp=round(hp), contrib=contrib, goods=tuple(goods))


def record(
    ctx: Game, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
    got: RaidSpoils | None, *, as_owner: bool, extra: list[str] | None = None, shown: float | None = None,
) -> list[str]:
    """這一邊（ctx）的戰報與紀錄（同截殺，戰報只列本人）。伏兵這一邊不在行動裡，寫一則「設伏・對手」；路過的人併進這一趟路的那一則。
    shown 同 _spar_record。"""
    s, c = ctx.state, ctx.content
    p = s.player
    squad = Squad(
        id=f"ambush:{rival}", name=rival, difficulty=rival_power,
        attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
    )
    rec = battlelog.new_record(s, c, ctx.world, squad, result, "ambush")
    if shown is not None:
        rec.difficulty = shown
    rec.ours = rec.ours[:1]
    won = got is not None and name_key(got.winner) == name_key(p.name)
    hp_lost: int | None = 0
    him = gender.pronoun(rival_game.state)
    if got is None:
        story = (ambush_rules.OWNER_DRAW if as_owner else ambush_rules.PASSER_DRAW).format(rival=rival, him=him)
    elif won:
        rec.silver = got.taken
        rec.materials += [f"{c.materials[mid].name} ×{n}" for mid, n in got.goods]
        if got.contrib:
            rec.changes.append(f"貢獻 +{got.contrib}")
        story = (ambush_rules.OWNER_WON if as_owner else ambush_rules.PASSER_WON).format(rival=rival, him=him)
    else:
        rec.silver = -got.lost
        rec.changes += [f"{c.materials[mid].name} -{n}" for mid, n in got.goods]
        hp_lost = got.hp
        if got.hp > 0:
            rec.changes.append(f"氣血 -{got.hp}")
        story = (ambush_rules.OWNER_LOST if as_owner else ambush_rules.PASSER_LOST).format(rival=rival, him=him)
    rec.notes.append(story)
    annals.note(s, c, annals.FIGHT, story, 3 if won else 2, keep=[rival])
    ctx._play_rounds(rec, squad, result.tier, hp_lost)
    line = ctx._file_battle(rec)
    msgs = [line, story, *battlelog.gains_list(rec), *ctx._last_wear, *(extra or [])]
    if ctx._draft is None:
        ctx._write(f"{ambush_rules.TITLE}・{rival}" if as_owner else f"中伏・{rival}", msgs, tag=battlelog.outcome_text(rec))
    return msgs
