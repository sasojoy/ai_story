"""馬的來路的動作（Joy 2026-11-10 選擇卡選「奪馬＋馴野馬＋論功賜馬」；開關 Config.horses.enabled，預設關）。

- 奪馬：事件 win 的 horses 那一格。打贏 Config.horses.seize_squads 列的那幾路（騎馬的），照那一路的機率牽走一匹良駒；一人一季最多 seize_cap 匹。
  種子「奪馬|季數|名號|地點|隊伍|四欄共用的流水號」，不碰 Game.rng。拿不下（裝備庫滿）就不擲、不記。
- 馴野馬：pastures 那幾處有野馬群，連 tame_steps 步，每步花 tame_stamina 體力與一個一階素材（背包裡最多的那一種，同餵馬）；最後一步擲 tame_chance，
  成了給一匹良駒（品質照 Config.treasures.horse_quality），wild_steed_chance 是名駒（named_steeds 那幾匹專名的，全服一季每匹一個主人，上天下大事）；不成野馬跑掉、從頭來。
  每一處每一週全服只馴得走 herd_per_week 匹（WorldState.horses_herds，被別人馴走就沒了）；一人一季最多 tame_cap 匹。走開了就從頭來。
- 論功賜馬：事件 showdown_pay 的 horses 那一格。決戰（不含攻城）得勝那一方、自己出手過的人，照戰功排名：第 1 名名駒（同上那幾匹，都有主了改良駒上品）、第 2～3 名良駒上品。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from tianxia import calendar, equipment, mounts, treasures
from tianxia.core import battle_base
from tianxia.core.option import Option
from tianxia.rules import add_rumor

from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game


def _cfg(ctx: Game):
    return ctx.content.config.horses


def on(ctx: Game) -> bool:
    return _cfg(ctx).enabled and mounts.on(ctx.content)


def _season(ctx: Game) -> int:
    return ctx.world.get_season_number()


def _new_horse(ctx: Game, rng: random.Random, tier: int, quality: str | None = None):
    """一匹新的（先抽毛色、再抽品質；quality 給了就不抽）。良駒的品質權重同懸賞與奇遇（Config.treasures.horse_quality）。"""
    coat = rng.choice(mounts.COATS)
    if quality is None:
        table = ctx.content.config.treasures.horse_quality
        quality = rng.choices(list(table), weights=list(table.values()))[0]
    return mounts.new_mount(ctx.state, name=mounts.horse_name(coat, tier), tier=tier, quality=quality)


# ── 奪馬（事件 win）──

def win(ctx: Game, loc_id: str, squad_id: str) -> list[str]:
    if not on(ctx):
        return []
    cfg, s = _cfg(ctx), ctx.state
    p = s.player
    chance = cfg.seize_squads.get(squad_id)
    if not chance or p.horses_seized >= cfg.seize_cap or not treasures.room_for(s, ctx.content, "mount"):
        return []
    rng = random.Random(f"奪馬|{_season(ctx)}|{p.name}|{loc_id}|{squad_id}|{p.weapon_serial}")
    if rng.random() >= chance:
        return []
    item = _new_horse(ctx, rng, 2)
    p.horses_seized += 1
    squad = ctx.content.squads.get(squad_id)
    foe = squad.name if squad is not None else "敵陣"
    return [rules.SEIZE_LINE.format(foe=foe, grade=mounts.grade(item), name=item.name), *treasures.deliver(s, ctx.content, item, hold=True)]


def free_steed(ctx: Game, rng: random.Random) -> str | None:
    """還沒有主人的那幾匹名駒裡挑一匹（排序後再挑，同一個種子永遠同一匹）；都有主了是 None。"""
    taken = set(ctx.state.world.horses_steeds)
    free = sorted(i for i in _cfg(ctx).named_steeds if i not in taken and i in ctx.content.gear.steeds)
    return rng.choice(free) if free else None


def claim_steed(ctx: Game, steed_id: str, *, shared: bool) -> bool:
    """記下這一匹有主了。shared（收場補送那一條：同步時不會寫回共用賽季）走 world.mutate_season 原子地搶，手上那一份也跟著記；
    動作裡（馴馬）只改手上那一份，動作最後的 _save_season 寫回。搶輸（別人剛拿走）回 False。"""
    if not shared:
        ctx.state.world.horses_steeds.append(steed_id)
        return True
    won: list[bool] = []

    def _claim(season) -> None:
        won.append(steed_id not in season.horses_steeds)
        if won[0]:
            season.horses_steeds.append(steed_id)

    ctx.world.mutate_season(_claim)
    if won and won[0] and steed_id not in ctx.state.world.horses_steeds:
        ctx.state.world.horses_steeds.append(steed_id)
    return bool(won and won[0])


# ── 論功賜馬（事件 showdown_pay）──

def merit_rank(battle, tuning, me) -> int | None:
    """自己在自己那一邊排第幾（戰功大於 0、自己出手過的人裡；同分照名號，同戰局條）。不在名次上是 None。"""
    rows = sorted(
        ((q, battle_base.merit(tuning, q)) for q in battle.participants.values() if q.faction == me.faction),
        key=lambda row: (-row[1], row[0].name),
    )
    ranked = [q.name for q, m in rows if m > 0 and q.acted_rounds > 0]
    return ranked.index(me.name) + 1 if me.name in ranked else None


def showdown_pay(ctx: Game, battle, me, lines: list[str]) -> list[str]:
    if not on(ctx) or battle.siege is not None or not battle.outcome_side or me.faction != battle.outcome_side or me.acted_rounds < 1:
        return []
    cfg, s = _cfg(ctx), ctx.state
    rank = merit_rank(battle, ctx.content.config.battle, me)
    tier = rules.merit_tier(rank, cfg.merit_steed_top, cfg.merit_horse_top) if rank is not None else None
    if tier is None:
        return []
    rng = random.Random(f"論功賜馬|{battle.record_id}|{s.player.name}")
    steed_id = free_steed(ctx, rng) if tier == 3 else None
    if steed_id is not None and claim_steed(ctx, steed_id, shared=True):
        item = treasures.new_steed(s, ctx.content.gear.steeds[steed_id])
    else:  # 不是第一名，或四匹名駒這一季都有主了：良駒上品
        item = _new_horse(ctx, rng, 2, cfg.merit_horse_quality)
    lines.append(rules.MERIT_LINE.format(rank=rank, grade=mounts.grade(item), name=item.name))
    lines += treasures.deliver(s, ctx.content, item, hold=True)
    return [rules.MERIT_GAIN.format(name=item.name)]


# ── 馴野馬 ──

def _week(ctx: Game) -> int:
    return calendar.point(ctx.state.world.time, ctx.content, ctx.state.world).week


def step_now(ctx: Game) -> int:
    """這一下是第幾步（從 1 起）：在別處馴到一半的不算。"""
    p = ctx.state.player
    return (p.horses_tame if p.horses_tame_at == p.location else 0) + 1


def tame_problem(ctx: Game) -> str | None:
    cfg, s = _cfg(ctx), ctx.state
    p = s.player
    if p.horses_tamed >= cfg.tame_cap:
        return rules.TAME_CAPPED
    if s.world.horses_herds.get(rules.herd_key(_week(ctx), p.location), 0) >= cfg.herd_per_week:
        return rules.TAME_GONE
    if not treasures.room_for(s, ctx.content, "mount"):
        return rules.TAME_NO_ROOM
    if equipment.repair_material(s, ctx.content) is None:
        return rules.TAME_NO_MATERIAL
    return None


def options(ctx: Game) -> list[Option]:
    if not on(ctx):
        return []
    p, cfg = ctx.state.player, _cfg(ctx)
    if p.journey is not None or p.busy_until is not None or p.location not in cfg.pastures:
        return []
    note = rules.TAME_STEP_NOTE.format(step=step_now(ctx), steps=cfg.tame_steps)
    problem = tame_problem(ctx)
    option = ctx._cost_option(f"{rules.KIND}:tame", rules.TAME_LABEL, cfg.tame_stamina, note=f"{note}・{problem}" if problem else note)
    if problem is not None:
        option.enabled = False
    return [option]


def choose(ctx: Game, arg: str) -> list[str]:
    if arg != "tame" or not on(ctx):
        return []
    cfg, s, c = _cfg(ctx), ctx.state, ctx.content
    p = s.player
    if p.location not in cfg.pastures or p.journey is not None or p.busy_until is not None:
        return []
    problem = tame_problem(ctx)
    if problem is not None or p.stamina < cfg.tame_stamina:
        return [f"（{problem or '體力不夠'}。）"]
    step = step_now(ctx)
    material = equipment.repair_material(s, c)
    materials_name = c.materials[material].name
    p.materials[material] -= 1
    if not p.materials[material]:
        del p.materials[material]
    p.stamina -= cfg.tame_stamina
    if step < cfg.tame_steps:
        p.horses_tame, p.horses_tame_at = step, p.location
        return [rules.TAME_STEP[min(step, len(rules.TAME_STEP)) - 1].format(material=materials_name), f"體力 -{cfg.tame_stamina}"]
    p.horses_tame, p.horses_tame_at = 0, ""
    rng = random.Random(f"馴野馬|{_season(ctx)}|{p.name}|{p.location}|{p.weapon_serial}")
    if rng.random() >= cfg.tame_chance:
        return [rules.TAME_FAIL, f"體力 -{cfg.tame_stamina}"]
    w = s.world
    key = rules.herd_key(_week(ctx), p.location)
    w.horses_herds[key] = w.horses_herds.get(key, 0) + 1
    steed_id = free_steed(ctx, rng) if rng.random() < cfg.wild_steed_chance else None
    steed = steed_id is not None and claim_steed(ctx, steed_id, shared=False)
    item = treasures.new_steed(s, c.gear.steeds[steed_id]) if steed else _new_horse(ctx, rng, 2)
    p.horses_tamed += 1
    out = [rules.TAME_DONE.format(material=materials_name, grade=mounts.grade(item), name=item.name)]
    out += treasures.deliver(s, c, item)
    if steed:
        place = c.locations[p.location].name
        add_rumor(s, rules.TAME_STEED.format(who=p.name, place=place, name=item.name), p.location, content=c, named=True)
    out.append(f"體力 -{cfg.tame_stamina}")
    return out
