"""截殺的動作（功能包 tianxia/features/peers/；原本是 Game 上的 raid_shown、raid_refusal、raid_odds、raid_targets、raid、raid_flee_odds、_raid_fled、
_raid_spoils、_raid_record；全部拆包第 38 批搬進來，行為一個字不變）。ctx 是 Game；只叫 tianxia/core/services_list.md 那張清單上的方法。

截殺（Config.raid；企劃者 2026-10-08 在決策卡選「有限制地開」）：玩家卡上的一顆鈕，不必對方同意。每季都有、不看第一季開關（企劃者 2026-10-10，懸賞榜設計 2.2）；
Config.raid.enabled 是主機的緊急開關，關著時通緝一起收。兩個人都投靠了陣營、而且是不同陣營時才有；散人只能截殺自己揭了通緝的那個人。對方下線、在忙也照打：
他在「此地還有」的名單上（presence_seconds 內同步過、不在路上）就行，他回來在戰報與江湖紀錄裡看得到。真人假人一樣。

fled、take_spoils、raid_record、flee_odds 一律經 ctx（Game 上的一行委派）叫：scripts/sim_season_one.py、sim_server_bots.py 用 mock.patch.object(Game, …) 數截殺，
tests/gear/test_mounts.py 換 Game.raid_flee_odds。打贏的交差 ctx._raid_bounty 是事件 raid_win 的發布點（懸賞榜，第 45 批），位置不動。
策馬脫身那一擲用自己的亂數（random.Random(字串)），不動 ctx.rng。encounter.resolve_encounter 一律用模組屬性叫。"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from tianxia import battlelog, calendar, encounter, figure_life, gender, mounts, renown, roster, team, wins
from tianxia.core import bounty_base
from tianxia.core import guard_base  # 親衛隊長（殺手，第三批 Joy 2026-11-09「好」）：截殺時本人的威力 ×(1+Config.guard.perks)；第四批起也寫他在一旁的那一句（raid_lines）
from tianxia.core import identity_base  # 綁手機才能截殺（帳號與客服第 205 批；核心，phone_gate 預設關）
from tianxia.core import jieyi_base  # 結義第一批（Joy 2026-11-09）：義不相殘、替兄出頭；開關 Config.jieyi.enabled 關著時一個字不變
from tianxia.characters import name_key
from tianxia.core import annal_base as annals
from tianxia.core import presence
from tianxia.core.services import RaidSpoils
from tianxia.models import Squad
from tianxia.rules import season_one
from tianxia.state import PLAYER

from . import spar_actions

if TYPE_CHECKING:
    from tianxia.engine import Game

# 撞過一場混戰之後，截殺的拒絕話照實寫（FB-607：混戰跟截殺共用冷卻與護身那一本，以前一律寫「截殺過」「被人截殺過」）。待 joy 潤
RAID_AFTER_CLASH = "你跟{them}不久前才在混戰裡交過手，過一陣子再說。"
RAID_SHIELD_CLASH = "{them}剛跟人混戰過，元氣未復，這時下手太不講江湖道義。"


def is_shown(ctx, other: Game) -> bool:
    """卡上要不要畫「截殺」：截殺開著（Config.raid.enabled）、這一季還沒收、兩個人都投靠了陣營、而且不同陣營；或是你揭了通緝他的懸賞
    （散人、同陣營的人也行）。每季都有，不看第一季開關（懸賞榜設計 2.2 第 3 點）；休季（這一季收了）不畫，跟通緝鈕、懸賞榜一樣
    （FB-163：以前還畫著灰的，原因寫成「城裡耳目眾多」「你此刻正忙」）；raid_targets 與 raid_refusal 都先問這裡。"""
    mine, theirs = ctx._side(), other._side()  # 豪強分屬兩軍：同一邊的不能截殺
    if not ctx.content.config.raid.enabled or ctx.state.world.ended:
        return False
    them = other.state.player.name
    if jieyi_base.sworn(ctx.content, ctx.world, ctx.state.player.name, them):  # 義不相殘：結義兄弟之間不畫截殺（通緝也揭不了）
        return False
    if jieyi_base.feud_against(ctx.content, ctx.world, ctx.state.player.name, them, ctx.now) is not None:  # 替兄出頭：不看陣營
        return True
    if mine is not None and theirs is not None and mine != theirs:
        return True
    return bounty_base.hunting(ctx.state, ctx.content, other.state.player.name)


def refusal(ctx, other: Game) -> str | None:
    """「截殺」按不按得下去（拒絕的話；能是 None）：不在城鎮類的地點、兩個人都過了新手期、你閒著付得起體力、
    你上一次截殺他已經過了冷卻、他沒有剛被人截殺過。對方忙不忙不看（截殺不必他同意）。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.raid
    if not is_shown(ctx, other):
        if cfg.enabled and jieyi_base.sworn(c, ctx.world, s.player.name, other.state.player.name):
            return jieyi_base.SWORN_NO  # 卡上不畫，直接打 API 才看得到
        return "（此刻無法這麼做。）"
    loc = c.locations[s.player.location]
    if c.config.explore_mix_of(loc.tags).kind == "town":
        return "城裡耳目眾多，不便動手。"
    if roster.raid_newbie(s, c):  # 新手期從各自加入的那一刻算，不看第一季開關（懸賞榜設計 14.1 丁）
        return "你初入江湖，還在新手期，先別結這種仇。"
    them = other.state.player.name
    if roster.raid_newbie(other.state, c):
        return f"{them}初入江湖，還在新手期，下不了這個手。"
    problem = spar_actions.who_problem(ctx, ctx, me=True, what="截殺", cost=cfg.stamina)
    if problem is not None:
        return problem
    w = s.world
    key = ctx._raid_key(s.player.name, them)
    last = w.raids.get(key)
    if last is not None and w.time - last < cfg.pair_cooldown_seconds:
        if w.clashes.get(key) == last:  # 那一筆是混戰寫的（翻地與爭搶）：照實寫交過手，不寫截殺過（FB-607）
            return RAID_AFTER_CLASH.format(them=them)
        return f"你不久前才截殺過{them}，過一陣子再說。"
    hit = w.raided.get(name_key(them))
    avenging = jieyi_base.feud_against(c, ctx.world, s.player.name, them, ctx.now) is not None  # 替兄出頭不看他剛被截過的護身
    if hit is not None and w.time - hit < cfg.shield_seconds and not avenging:
        if w.clashed.get(name_key(them)) == hit:
            return RAID_SHIELD_CLASH.format(them=them)
        return f"{them}剛被人截殺過，元氣未復，這時下手太不講江湖道義。"
    return None


def odds_word(ctx, other: Game) -> str:
    """截殺的勝算（「有把握」這種字，同遊歷的按鈕）：本人對本人的威力，照固定種子模擬。兩邊都照**不含玉璽碎片**的威力算
    （改版 FB-625：給別人看的字不能讓人對同一個人看出他有沒有碎片，持有者自己看也照這一份，免得畫面對不上；
    打起來 raid() 照含碎片的威力擲，勝負不變）。"""
    theirs = ctx._spar_power(other, ctx, seal=False)
    squad = Squad(id=f"raid:{other.state.player.name}", name=other.state.player.name, difficulty=theirs)
    return team.odds_word(ctx._spar_power(ctx, other, seal=False), squad)


def targets(ctx) -> list[tuple[str, str]]:
    """此地截殺得了的人與勝算：[(名號, 勝算)]，照名號排序（假人挑對象用；真人看卡上的鈕）。截殺關著時是空的（raid_shown 擋）；
    散人只有揭了通緝的那個人。"""
    out = []
    for state in presence.here(ctx):
        other = ctx._kin(state)
        if is_shown(ctx, other) and refusal(ctx, other) is None:
            out.append((state.player.name, odds_word(ctx, other)))
    return out


def raid(ctx, other: Game) -> list[str]:
    """截殺 other：重驗、付體力、記冷卻，用本人的威力照單次判定打一場（從發起的人看）。輸的一方失一點銀兩（贏的拿走一部分）
    與一點氣血（不變成內傷）；他身上的防具照減損少扣、也只有他磨（裝備四欄 4.4、4.5）；贏的一方記一點本季貢獻；平手誰都不失什麼。
    雙方各一份戰報與一則江湖紀錄。被截殺的人騎的馬比較快時，開打之前先擲策馬脫身（raid_flee_odds、_raid_fled）。"""
    if not identity_base.phone_ok(ctx, "raid"):  # 只問動手的人（第 205 批）
        return [identity_base.PHONE_NEEDED]
    problem = refusal(ctx, other)
    if problem is not None:
        return [problem]
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.raid
    me, them = s.player, other.state.player
    feud = jieyi_base.feud_against(c, ctx.world, me.name, them.name, ctx.now)  # 替兄出頭（結義第一批）：打之前先認這一筆
    me.stamina -= cfg.stamina
    s.world.raids[ctx._raid_key(me.name, them.name)] = s.world.time
    s.world.raided[name_key(them.name)] = s.world.time
    # 策馬脫身（裝備四欄 5.10）：付完體力、記完冷卻才擲（跑掉了冷卻照算，不然可以一直按到追上），用自己的亂數、不動 Game.rng
    flee = ctx.raid_flee_odds(other)
    if flee > 0 and random.Random(f"截殺脫身|{me.name}|{them.name}|{s.world.time}").random() < flee:
        return ctx._raid_fled(other)
    ours, theirs = ctx._spar_power(ctx, other), ctx._spar_power(other, ctx)
    ours *= 1 + guard_base.perk(s, c, "raid")
    ours_shown, theirs_shown = ctx._spar_power(ctx, other, seal=False), ctx._spar_power(other, ctx, seal=False)  # 戰報給對方看的（FB-615）
    result = encounter.resolve_encounter(ours, theirs, ctx.rng)
    mirrored = ctx._spar_mirror(result, theirs)
    if result.tier in team.WIN_TIERS:
        winner, loser = ctx, other
    elif mirrored.tier in team.WIN_TIERS:
        winner, loser = other, ctx
    else:
        winner = loser = None
    # 名聲 5.4：交差之前先判會不會交到官府通緝（打贏了、手上揭著他的官府通緝），把惡名少的那一點算進輸的那一邊，兩邊的戰報才寫得到
    official = winner is ctx and renown.on(c, "official_wanted") and bounty_base.official_hit(s, c, them.name)
    spoils = winner._raid_spoils(loser, evil=c.config.renown.official_evil_loss if official else 0) if winner is not None else None
    ctx.touched.add(them.name)
    other._raid_record(mirrored, me.name, ours, ctx, spoils, attacker=False, shown=ours_shown)
    msgs = ctx._raid_record(result, them.name, theirs, other, spoils, attacker=True, shown=theirs_shown)
    if winner is ctx and feud is not None:  # 替兄出頭打贏：贏到的那一份轉給受害的兄弟，仇結清；這一下不再記成新的仇
        msgs += jieyi_base.avenge(ctx, them.name, spoils.taken)
    elif winner is ctx:
        jieyi_base.record_feud(ctx, them.name, me.name)  # 他有結義兄弟：記一筆仇
    if winner is ctx:
        msgs += ctx._raid_bounty(them.name)
        heard = figure_life.spread(s, c, "raid", name_key(them.name), at=me.location, side=them.faction,
                                   text=f"在{c.locations[me.location].name}截殺了{them.name}")
        if heard and ctx._draft is None:
            ctx._write(figure_life.HEARSAY_TITLE, heard)
        msgs += heard
    # 冷卻與交差（通緝那一張的 done_by／takers）都在共用賽季：最後存一次。玩家卡走 peer_act、server.act 都只存角色，
    # 以前在打之前就存了季，交差改的沒存回去，同一張可以一直揭、一直領，過期還照退押金（FB-119）
    ctx._save_season()
    return msgs


def flee_odds(ctx, other: Game) -> float:
    """被截殺的 other 策馬脫身的機會（裝備四欄 5.10）：他的腳力減你的腳力，夾在 0～raid_escape_cap；坐騎關著是 0。
    截殺鈕的確認句（raid.buttons）與 raid() 真正擲的都讀這一個。"""
    return mounts.raid_flee(ctx.content, ctx.state, other.state)


def fled(ctx, other: Game) -> list[str]:
    """截殺時被截殺的人策馬脫身（裝備四欄 5.10）：不打、誰都不失銀兩與氣血、不寫戰報、不磨兵器防具、不扣飽足；發起的人的體力
    已經付了、冷卻已經記了（raid 在擲之前做完）。雙方各一則江湖紀錄。冷卻在共用賽季，最後存一次（FB-119：玩家卡走 peer_act、
    server.act 都只存角色）。scripts/sim_season_one.py 照這個函式數跑掉幾次。"""
    s, c = ctx.state, ctx.content
    me, them = s.player, other.state.player
    horse = mounts.name_of(them.mount)
    ctx.touched.add(them.name)
    other._write(f"遭{me.name}截殺", [mounts.RAID_ESCAPED.format(rival=me.name, horse=horse)], tag=mounts.RAID_ESCAPED_TAG)
    msgs = [f"體力 -{c.config.raid.stamina}", mounts.RAID_FLED.format(rival=them.name, horse=horse)]
    if ctx._draft is None:
        ctx._write(f"截殺・{them.name}", msgs, tag=mounts.RAID_FLED_TAG.format(him=gender.pronoun(them)))
    ctx._save_season()
    return msgs


def take_spoils(ctx, loser: Game, evil: int = 0) -> RaidSpoils:
    """贏的是 ctx：loser 失銀兩（比例、有上限）與氣血（上限的一成弱，乘 1−他身上防具的減損；不吃化勁、不變成內傷，裝備四欄 4.4），
    ctx 拿走一部分銀兩、記一點貢獻。evil 是 loser 惡名少幾點（名聲 5.4：贏的人揭著他的官府通緝；夾在 0）。"""
    c, cfg = ctx.content, ctx.content.config.raid
    lp, wp = loser.state.player, ctx.state.player
    purse = lp.stats.get("silver", 0)
    lost = min(cfg.silver_cap, math.ceil(purse * cfg.silver_share)) if purse > 0 else 0
    taken = math.ceil(lost * cfg.take_share)
    lp.stats["silver"] = purse - lost
    wp.stats["silver"] = wp.stats.get("silver", 0) + taken
    con = team.con_of(loser.state, c, loser.world, PLAYER)
    cut = team.armor_cut(loser.state, c, loser.world)  # 截殺輸的一方只吃防具（裝備四欄 4.4）：不吃化勁，也就不必夾合計上限
    hp, _ = team._apply_toll(c, lp.member, cfg.hp_loss * (1 - cut), agi=team.v1_stat(loser.state, c, "agi"), con=con, injury=0.0,
                             season=loser.state.world)
    # 散人（揭了通緝）不記貢獻；第一季規則關著的季沒有晉升，也不記（懸賞榜設計 2.2 第 4 點，寫法同軍餉 _showdown_pay）
    contrib = c.config.contrib_per_push * cfg.win_contrib_push if wp.faction is not None and season_one(c, ctx.state.world) else 0
    if contrib:
        wins.credit(wp, c, ctx.state.world, calendar.point(ctx.state.world.time, c, ctx.state.world).week, contrib)
    cut = min(evil, lp.stats.get("evil", 0))
    if cut > 0:
        lp.stats["evil"] = lp.stats.get("evil", 0) - cut
    return RaidSpoils(winner=wp.name, lost=lost, taken=taken, hp=round(hp), contrib=contrib, evil=cut)


def raid_record(
    ctx, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
    spoils: RaidSpoils | None, *, attacker: bool, shown: float | None = None,
) -> list[str]:
    """這一邊的戰報與紀錄。對手寫成一支只為這一場存在的隊伍（同切磋），戰報只列本人。shown 同 _spar_record。"""
    s, c = ctx.state, ctx.content
    p = s.player
    squad = Squad(
        id=f"raid:{rival}", name=rival, difficulty=rival_power,
        attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
    )
    record = battlelog.new_record(s, c, ctx.world, squad, result, "raid")
    if shown is not None:
        record.difficulty = shown
    record.ours = record.ours[:1]
    won = spoils is not None and name_key(spoils.winner) == name_key(p.name)
    hp_lost: int | None = 0
    if spoils is None:
        story = f"你攔下{rival}動手，兩人鬥了半天不分高下，各自退開。" if attacker else \
            f"{rival}半路攔下你動手，兩人鬥了半天不分高下，各自退開。"
    elif won:
        record.silver = spoils.taken
        if spoils.contrib:
            record.changes.append(f"貢獻 +{spoils.contrib}")
        story = f"你攔下{rival}動手，{rival}不敵，丟下銀兩走了。" if attacker else \
            f"{rival}半路截殺你，反被你打退，丟下銀兩走了。"
    else:
        record.silver = -spoils.lost
        hp_lost = spoils.hp
        if spoils.hp > 0:
            record.changes.append(f"氣血 -{spoils.hp}")
        if spoils.evil:  # 名聲 5.4
            record.changes.append(bounty_base.BEATEN_OFFICIAL.format(n=spoils.evil, winner=spoils.winner))
        story = f"你攔下{rival}動手，卻不是{gender.pronoun(rival_game.state)}的對手，只得丟下銀兩脫身。" if attacker else \
            f"{rival}半路截殺你，你不敵，丟下銀兩脫身。"
    record.notes.append(story)
    guarded = guard_base.raid_lines(s, c, rival_game.state, "even" if spoils is None else "won" if won else "lost")  # 親衛隊長第四批：他在一旁的那一句
    record.notes += guarded
    annals.note(s, c, annals.FIGHT, story, 3 if won else 2, keep=[rival])  # 行狀：截殺與被截殺（兩邊各記自己的；對手的名號原樣留，FB-9020）
    ctx._play_rounds(record, squad, result.tier, hp_lost)
    line = ctx._file_battle(record)
    msgs = [line, story, *guarded, *battlelog.gains_list(record), *ctx._last_wear]
    if attacker:
        msgs.insert(0, f"體力 -{c.config.raid.stamina}")
    if ctx._draft is None:
        ctx._write(f"截殺・{rival}" if attacker else f"遭{rival}截殺", msgs, tag=battlelog.outcome_text(record))
    return msgs
