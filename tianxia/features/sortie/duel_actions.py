"""出陣約戰的動作（功能包 tianxia/features/sortie/；原本是 Game 上出陣約戰的 33 個方法加 _duty_credit，主動搬六包第 2 批）。
減法季批 3b（整合設計 4.3；計畫 docs/superpowers/plans/2026-10-24-減法季-主機側實作計畫.md 第四節 4.0 之二、之三）。

貼（sortie_go）、應戰（sortie_answer）、同去（sortie_join）各在一次 world.mutate 裡重驗再寫（先按的那一位才進得去）；窗滿了伺服器排程
（world_tick）、任何人的同步（sync）、快轉（advance）、假人程式（sortie_duel_tick）誰先到誰結算（duel_tick → duel_rules.advance，只往前走），
結算那一下就把季的進度與兩邊（含同去的）做完。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx；sortie_duel、sortie 兩個名字
照舊，是包裡的 duel_rules、rules）。函式名＝原本的方法名去掉前導底線，兩個例外：`_sortie_duel_tick` 是 `duel_tick`（跟
`sortie_duel_tick` 分開）、`_duel_power_of` 是 `duel_power_of(state, content, world)`（原本就是 staticmethod）。Game 上留 16 個一行委派
（server、假人、測試與核心原位還在叫：三處結算、選單那一格、choose 最前面、行動列底下那一行、_act、守勢行動、輿圖）。包裡互相叫直接叫
這裡與 actions 的函式；只有 `sorties_left` 經 ctx 叫（tests/bots/test_bot_policy_conquest.py 換掉 Game.sorties_left，換掉的才打得到）。
一場結算開好幾份 Game（duel_party → ctx._load_kin，存回 ctx._save_kin）：別人那一份上做的直接叫這裡的函式（duel_void(g, …)、
duel_report(g, …)），軍令記在 attacker、defender 那兩份上（_order_credit，服務清單的過渡）。
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from typing import TYPE_CHECKING

from tianxia import calendar, journal, team
from tianxia import allied  # 過渡：待搬（豪強依附的那一軍：補位的人算哪一邊）
from tianxia import annals  # 過渡：待搬（行狀：約戰那一筆交手）
from tianxia import atlas  # 過渡：待搬（大區：同一區才應得了戰）
from tianxia import battlelog  # 過渡：待搬（戰報）
from tianxia import conquest  # 過渡：待搬（地盤：區塊、進度、推、拉、集火、易手）
from tianxia import encounter  # 過渡：待搬（整隊威力）
from tianxia import howto  # 過渡：待搬（行動列底下那一行的句子）
from tianxia import orders  # 過渡：待搬（軍令：截糧的運糧隊、攻城軍令對不對）
from tianxia import precise  # 過渡：待搬（一類一顆：打贏的獎勵怎麼算）
from tianxia import prologue as prologue_rules  # 過渡：待搬（序章裡沒有約戰）
from tianxia import push  # 過渡：待搬（人數緩衝、貢獻、活躍名單）
from tianxia import ranger  # 過渡：待搬（遊俠名號：經驗倍數）
from tianxia import ranks  # 過渡：待搬（晉升：離下一階還差多少）
from tianxia import seal_acts  # 過渡：待搬（玉璽：傳檄的倍數、補位的人在哪一區）
from tianxia import server_bots  # 過渡：待搬（這一季的假人：補位）
from tianxia import treasures  # 過渡：待搬（寶物：內傷、經驗心得的加成）
from tianxia import wins  # 過渡：待搬（三陣營四勝利：貢獻記在哪一軍）
from tianxia.calendar import DAY
from tianxia.characters import CharacterStore, name_key
from tianxia.core.option import Option
from tianxia.core.services import PAUSED_TEXT, drill_share
from tianxia.guide import note_action  # 過渡：待搬（入伍段的「出一次力」）
from tianxia.journal import Draft
from tianxia.models import Content, Location, Squad
from tianxia.rules import front_of
from tianxia.state import PLAYER, BattleRecord, Fighter, GameState
from tianxia.world_state import SortieDuel, SortieSide, WorldStateStore

from . import actions as sortie_actions
from . import duel_rules as sortie_duel
from . import rules as sortie

if TYPE_CHECKING:
    from tianxia.engine import Game


def duel_on(ctx: Game) -> bool:
    """約戰在這一季開著（sortie_duel.on：減法季的 sortie_duel 子開關、出陣、領地爭奪都在這一季生效）。關著一律照舊。"""
    return sortie_duel.on(ctx.content, ctx.state.world)


def answers_left(ctx: Game) -> int:
    """今天還能應戰幾次（Config.sortie.answer_per_day，跟出陣分開算；換日同出陣）。"""
    return sortie_duel.answers_left(ctx.state.player, ctx.content.config.sortie, ctx._pill_day())


def duel_power_of(state: GameState, content: Content, world: WorldStateStore) -> float:
    """約戰封招那一刻的威力快照：整隊（本人、出戰的同伴、部下，同出陣打駐軍的算法），對手的屬性不算（計畫 4.0 之三第 7 條）。"""
    members, conditions, boosts = team._fighters(state, content, world)
    return encounter.team_power(members, team.team_arts(state, content, world), None, conditions, boosts)


def duel_power(ctx: Game) -> float:
    return duel_power_of(ctx.state, ctx.content, ctx.world)


def duel_region(ctx: Game) -> tuple[str | None, str]:
    """此刻站在哪一個大區（id, 名字）；在路上、地圖沒有大區是 (None, "")。"""
    p = ctx.state.player
    if p.journey is not None or p.location is None:
        return None, ""
    region = atlas.region_of(ctx.content, p.location)
    return (region.id, region.name) if region is not None else (None, "")


def duel_convoy_here(ctx: Game) -> bool:
    """這週截糧的運糧隊正打這裡經過（orders.extra_enemies）：約戰開著時出陣那一格照舊攻打運糧隊、不貼約戰（設計 4.3）。"""
    p = ctx.state.player
    if p.journey is not None or p.location is None:
        return False
    return bool(orders.extra_enemies(ctx.state, ctx.content, p.location, ctx._side()))


def duel_squad(ctx: Game, loc_id: str) -> Squad | None:
    """這一塊此刻的駐軍（conquest.sortie_foes，不含運糧隊）裡經驗最高的那一路（同 _sortie_host 的挑法，同分取先列的）：守軍迎戰的威力、
    打贏的戰利、守方贏的經驗心得都照它。貼的那一刻抄進 SortieDuel.report["squad"]。"""
    ids = conquest.sortie_foes(ctx.state.world, ctx.content, loc_id, ctx._conquest_side())
    squads = [ctx.content.squads[sid] for sid in ids]
    return max(squads, key=lambda q: q.exp) if squads else None


def sortie_go_problem(ctx: Game, moves: list[str] | None = None) -> str | None:
    """貼不了約戰的那一句（不含括號；貼得了是 None）：暫停、休季、三招不對（給了 moves 才驗）、散人、在路上、不是區塊、今天的次數、冷卻、
    這一塊推不動（自家的寫「等對面來約」，sortie_duel.open_problem）、體力。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.sortie
    if ctx.world.paused_at() is not None:
        return PAUSED_TEXT
    if s.world.ended:
        return sortie_duel.WHY_RESTING
    if moves is not None and (why := sortie_duel.moves_problem(cfg, moves)) is not None:
        return why
    side = ctx._conquest_side()
    block_why = None
    if side is not None and p.journey is None:
        if p.location not in conquest.blocks(c):
            block_why = sortie_duel.WHY_NOT_BLOCK
        else:
            block_why = conquest.push_problem(s.world, c, side, p.location, "attack")
    return sortie_duel.open_problem(
        cfg, ctx.now, side=side, left=ctx.sorties_left(), cooldown_until=p.sortie_cooldown_until, block_why=block_why,
        stamina=p.stamina, traveling=p.journey is not None,
    )


def duel_option(ctx: Game, loc: Location) -> Option | None:
    """約戰開著時出陣那一格（id 照留 act:train，計畫 4.0 之三第 2 條）：散人、不是區塊、別人搶不下來的區塊是 None（options 照舊寫散人、
    不在爭奪之列）；截糧的運糧隊經過時照舊攻打運糧隊；其餘按了只打開出陣前那張卡（不花體力），貼不了時灰著寫原因。"""
    s, c = ctx.state, ctx.content
    side = ctx._conquest_side()
    if side is None or loc.id not in conquest.blocks(c):
        return None
    cfg = c.config.sortie
    left = ctx.sorties_left()
    if duel_convoy_here(ctx):
        if left <= 0:
            return Option(id="act:train", label=f"{sortie.NAME}（{sortie.USED_UP.format(n=cfg.jianfa_per_day)}）", enabled=False)
        return ctx._cost_option("act:train", f"{sortie.NAME}・{sortie_duel.CONVOY_NAME}", cfg.jianfa_stamina,
                                 note=sortie.LEFT_NOTE.format(n=left))
    if not conquest.capturable(c, loc.id):
        if conquest.holder(s.world, c, loc.id) != side:
            return None
        return Option(id="act:train", label=f"{sortie.NAME}（{sortie.OUT_NOTE}）", enabled=False)  # 自家的大本營、廣宗
    problem = sortie_go_problem(ctx)
    if problem is not None and problem != sortie_duel.WHY_TIRED.format(n=cfg.jianfa_stamina):
        # 格子只放得下四個字（FB-670）：整句在行動列底下那一行（_duel_line）與卡上的 why_not
        return Option(id="act:train", label=f"{sortie.NAME}（{sortie_duel.cell_note(problem)}）", enabled=False)
    return ctx._cost_option("act:train", sortie.NAME, cfg.jianfa_stamina, note=sortie.LEFT_NOTE.format(n=left))  # 體力不夠照別格灰


def duel_line(ctx: Game, loc: Location) -> str:
    """約戰開著時行動列底下出陣那一行（howto.duel_line）：散人、不在爭奪之列照舊；截糧、貼得了、等對面來約、其他原因各一句。"""
    if ctx._conquest_side() is None or (
            not conquest.capturable(ctx.content, loc.id) and conquest.holder(ctx.state.world, ctx.content, loc.id) != ctx._conquest_side()):
        return sortie_actions.sortie_line(ctx, loc)
    if loc.id in conquest.blocks(ctx.content) and not conquest.capturable(ctx.content, loc.id) and not duel_convoy_here(ctx):
        return sortie.OUT_LINE  # 自家的大本營、廣宗：不在爭奪之列
    return howto.duel_line(ctx.content, sortie_go_problem(ctx), ctx.sorties_left(), answers_left(ctx),
                           convoy=duel_convoy_here(ctx))


def duel_entry(ctx: Game) -> list[str]:
    """約戰開著時按出陣那一格（act:train）：截糧的運糧隊經過時攻打運糧隊（扣一次出陣與 jianfa_stamina，照舊打一場、算截糧，約戰開著時出陣
    不推進度）；其餘只打開出陣前那張卡（sortie_duel.PICK，不花體力、不寫紀錄，同探索的入口）。"""
    s, c = ctx.state, ctx.content
    if not duel_convoy_here(ctx):
        return [sortie_duel.PICK]
    p = s.player
    p.stamina -= c.config.sortie.jianfa_stamina
    sortie.spend(p, ctx._pill_day())
    squad = orders.extra_enemies(s, c, p.location, ctx._side())[0]
    return ctx._squad_encounter(squad, as_sortie=True) + ctx._guide(note_action(s, c, ctx.world, "order"))


def duel_choice(ctx: Game, option_id: str) -> list[str]:
    """sortie:go:<三招>、sortie:answer:<約戰 id>:<三招>、sortie:join:<約戰 id>（choose 最前面接走的）。"""
    verb, _, rest = option_id.removeprefix(sortie_duel.PREFIX).partition(":")
    if verb == "go":
        return sortie_go(ctx, rest)
    if verb == "answer":
        duel_id, _, moves = rest.rpartition(":")
        return sortie_answer(ctx, duel_id, moves)
    if verb == "join":
        return sortie_join(ctx, rest)
    return ctx._log(["（此刻無法這麼做。）"])


def duel_who(ctx: Game, side: str | None) -> str:
    return ctx.content.scenario.faction_name(side, side or "")


def sortie_go(ctx: Game, moves) -> list[str]:
    """貼約戰（MAIN_ACTIONS 的 sortie_go、選項 sortie:go:<三招>；設計 4.3）：重驗（sortie_go_problem）之後在 world.mutate 裡貼一張——攻方的快照
    （整隊威力、封好的三招、站的大區）、這一塊的駐軍抄成守軍、駐軍那一路與今天記進 report；扣一次出陣與 jianfa_stamina、寫冷卻、記一則江湖紀錄。"""
    s, c = ctx.state, ctx.content
    if not duel_on(ctx):
        return ctx._log(["（此刻無法這麼做。）"])
    moves = sortie_duel.parse_moves(moves)
    problem = sortie_go_problem(ctx, moves)
    if problem is not None:
        return ctx._log([f"（{problem}。）"])
    p, cfg = s.player, c.config.sortie
    loc = c.locations[p.location]
    side = ctx._conquest_side()
    region, region_name = duel_region(ctx)
    squad = duel_squad(ctx, loc.id)
    garrison = None
    if squad is not None:
        holder = conquest.holder(s.world, c, loc.id) or ""
        garrison = SortieSide(name=squad.name, side=holder, power=float(squad.difficulty), region=region, garrison=True)
    me = SortieSide(name=p.name, side=side, power=duel_power(ctx), moves=moves, region=region)
    today = ctx._pill_day()
    tag = hashlib.sha256(name_key(p.name).encode()).hexdigest()[:8]
    duel_id = f"s{ctx.world.get_season_number()}-{int(ctx.now * 1000)}-{tag}"
    refused: list[str] = []

    def _apply(shared) -> None:
        if duel_id in shared.sorties:  # 同一刻按了兩次（兩個分頁）：第二張不貼
            refused.append(sortie_duel.WHY_COOL.format(n=c.config.sortie.cooldown_minutes))
            return
        duel = sortie_duel.open(shared, id=duel_id, block=loc.id, region=region, place=loc.name, region_name=region_name,
                                attacker=me, now=ctx.now, cfg=cfg, garrison=garrison)
        duel.report.update({"squad": squad.id if squad is not None else "", "day": today})

    ctx.world.mutate(_apply)
    if refused:
        return ctx._log([f"（{refused[0]}。）"])
    sortie.spend(p, today)
    p.stamina -= cfg.jianfa_stamina
    p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, ctx.now + cfg.cooldown_minutes * 60)
    line = sortie_duel.GO_LINE.format(place=loc.name, side=duel_who(ctx, side), moves="、".join(moves), window=f"{cfg.window_minutes:g}")
    ctx._write(sortie_duel.GO_TITLE.format(place=loc.name), [line], tag=sortie_duel.LABEL)
    ctx._guide(note_action(s, c, ctx.world, "order"))  # 入伍段「出一次力」：貼一張約戰就算
    return ctx._log([line])


def sortie_answer(ctx: Game, duel_id: str, moves) -> list[str]:
    """應戰（MAIN_ACTIONS 的 sortie_answer、選項 sortie:answer:<id>:<三招>）：在 world.mutate 裡照 sortie_duel.answer_problem 重驗——先按的那一位
    是守方，第二位回「已有人應戰」、什麼都不扣（Review Focus 第 2 條）；成了扣一次應戰與 answer_stamina、記一則江湖紀錄。"""
    s, c = ctx.state, ctx.content
    if not duel_on(ctx):
        return ctx._log(["（此刻無法這麼做。）"])
    if ctx.world.paused_at() is not None:
        return ctx._log([f"（{PAUSED_TEXT}。）"])
    p, cfg = s.player, c.config.sortie
    moves = sortie_duel.parse_moves(moves)
    if (why := sortie_duel.moves_problem(cfg, moves)) is not None:
        return ctx._log([f"（{why}。）"])
    side = ctx._conquest_side()
    region, _ = duel_region(ctx)
    left = answers_left(ctx)
    power = duel_power(ctx)  # 封招那一刻的快照（在 mutate 外面算：裡面只讀寫 world 那一列）
    got: list[SortieDuel] = []
    refused: list[str] = []

    def _apply(shared) -> None:
        duel = shared.sorties.get(duel_id)
        why = sortie_duel.WHY_GONE if duel is None else sortie_duel.answer_problem(
            cfg, duel, ctx.now, name=p.name, side=side, region=region, answers_left=left, stamina=p.stamina,
            cooldown_until=p.answer_cooldown_until, traveling=p.journey is not None,
        )
        if why is not None:
            refused.append(why)
            return
        sortie_duel.answer(duel, SortieSide(name=p.name, side=side, power=power, moves=moves, region=region), ctx.now)
        got.append(duel.model_copy(deep=True))

    ctx.world.mutate(_apply)
    if refused:
        return ctx._log([f"（{refused[0]}。）"])
    duel = got[0]
    sortie_duel.spend_answer(p, ctx._pill_day())
    p.stamina -= cfg.answer_stamina
    line = sortie_duel.ANSWER_LINE.format(rival=duel.attacker.name, place=duel.place, side=duel_who(ctx, side), moves="、".join(moves))
    ctx._write(sortie_duel.GO_TITLE.format(place=duel.place), [line], tag=sortie_duel.LABEL)
    return ctx._log([line])


def duel_join_extra(ctx: Game, duel: SortieDuel) -> str | None:
    """同去比 sortie_duel.join_problem 多驗的（PM 四之五第 6 件：同去算一次出陣、要站在那一塊所在的大區）：在路上、不在那個大區、
    今天的出陣次數、出陣的冷卻、體力。"""
    p, cfg = ctx.state.player, ctx.content.config.sortie
    region, _ = duel_region(ctx)
    if p.journey is not None:
        return sortie_duel.WHY_ROAD
    if duel.region is not None and region != duel.region:
        return sortie_duel.WHY_FAR.format(region=duel.region_name or duel.region).replace("應得了戰", "同得了去")
    if ctx.sorties_left() <= 0:
        return sortie.USED_UP.format(n=cfg.jianfa_per_day)
    if sortie_duel.cooling(p.sortie_cooldown_until, ctx.now):
        return sortie_duel.WHY_COOL.format(n=sortie_duel._minutes_left(p.sortie_cooldown_until, ctx.now))
    if p.stamina < cfg.jianfa_stamina:
        return sortie_duel.WHY_TIRED.format(n=cfg.jianfa_stamina)
    return None


def sortie_join(ctx: Game, duel_id: str) -> list[str]:
    """同去（MAIN_ACTIONS 的 sortie_join、選項 sortie:join:<id>；集火）：在 world.mutate 裡重驗（join_problem＋_duel_join_extra），記進攻方的
    allies；扣一次出陣與 jianfa_stamina、寫冷卻、在那一塊記一筆出陣（conquest.mark，結算時攻方的集火把它算進去）、記一則江湖紀錄。"""
    s, c = ctx.state, ctx.content
    if not duel_on(ctx):
        return ctx._log(["（此刻無法這麼做。）"])
    if ctx.world.paused_at() is not None:
        return ctx._log([f"（{PAUSED_TEXT}。）"])
    p, cfg = s.player, c.config.sortie
    side = ctx._conquest_side()
    got: list[SortieDuel] = []
    refused: list[str] = []

    def _apply(shared) -> None:
        duel = shared.sorties.get(duel_id)
        why = sortie_duel.WHY_GONE if duel is None else (
            sortie_duel.join_problem(duel, ctx.now, name=p.name, side=side) or duel_join_extra(ctx, duel))
        if why is not None:
            refused.append(why)
            return
        sortie_duel.join(duel, p.name)
        got.append(duel.model_copy(deep=True))

    ctx.world.mutate(_apply)
    if refused:
        return ctx._log([f"（{refused[0]}。）"])
    duel = got[0]
    sortie.spend(p, ctx._pill_day())
    p.stamina -= cfg.jianfa_stamina
    p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, ctx.now + cfg.cooldown_minutes * 60)
    conquest.mark(s.world, c, duel.block, p.name, side, "attack", 0.0)
    ctx._save_season()
    line = sortie_duel.JOIN_LINE.format(rival=duel.attacker.name, place=duel.place, side=duel_who(ctx, side))
    ctx._write(sortie_duel.GO_TITLE.format(place=duel.place), [line], tag=sortie_duel.LABEL)
    ctx._guide(note_action(s, c, ctx.world, "order"))
    return ctx._log([line])


def duel_mine(ctx: Game, duel: SortieDuel) -> bool:
    me = name_key(ctx.state.player.name)
    if me in {name_key(duel.attacker.name), *(name_key(n) for n in duel.attacker.allies)}:
        return True
    return duel.defender is not None and not duel.defender.garrison and name_key(duel.defender.name) == me


def sortie_cards(ctx: Game) -> list[dict] | None:
    """main.sorties（欄位表 1.3；sortie_duel.card）：約戰關著、序章裡是 None；散人是空的。還沒打的約戰兩邊都列（對面的是應戰、同袍的是同去、
    自己的是 mine），結算完（或作廢）的只列自己有份的、留 keep_hours。同去那一顆照 _duel_join_extra 再驗；不同區的照 place_minutes 寫步行幾分。
    多一個 result：看的人這一場的結果（大勝、險勝、僵持、落敗；沒結算是 None）；sides（兩軍的名字，同 sortie_card.sides）與 answer_stamina（應戰的體力）
    每一張都帶：站的地方不是區塊時沒有 sortie_card，網頁的陣營名與底鈕的體力只能從這裡拿（FB-9003）。還沒打的另帶約戰那一塊此刻的樣子
    （holder、bars、to_flip、foe_pushing；應戰卡寫這一場牽動什麼，FB-9004）。"""
    s, c = ctx.state, ctx.content
    if not duel_on(ctx) or prologue_rules.active(s, c):
        return None
    side = ctx._conquest_side()
    if side is None:
        return []
    p, cfg, w = s.player, c.config.sortie, s.world
    region, _ = duel_region(ctx)
    keep = cfg.keep_hours * 3600
    left = answers_left(ctx)
    sides ={x: c.scenario.faction_name(x, x) for x in conquest.SIDES}
    duels = sorted(ctx.world.sortie_duels().values(),
                   key=lambda d: (d.status not in ("open", "answered"), -(d.settled_at or d.opened_at), d.id))
    out: list[dict] = []
    for duel in duels:
        live = duel.status in ("open", "answered")
        if not live and (not duel_mine(ctx, duel) or (duel.settled_at is not None and ctx.now - duel.settled_at >= keep)):
            continue
        far = duel.region is not None and region != duel.region
        card = sortie_duel.card(
            duel, p.name, side, region, ctx.now, cfg, answers_left=left, stamina=p.stamina, cooldown_until=p.answer_cooldown_until,
            traveling=p.journey is not None, travel_minutes=ctx.place_minutes(duel.block) if far else None,
        )
        if card["role"] == "join" and card["can_join"] and (extra := duel_join_extra(ctx, duel)) is not None:
            card["can_join"], card["why_not"] = False, extra
        card["result"] = sortie_duel.side_tier(duel, p.name)
        # 出陣約戰網頁（FB-9003）：站的地方不是區塊（豪族塢堡、南華觀……）就沒有 sortie_card，卡上的陣營名與應戰的體力要從每一張約戰卡自己帶
        card["sides"], card["answer_stamina"] = dict(sides), cfg.answer_stamina
        # 應戰卡寫的是這一場牽動的那一塊（FB-9004，不是看的人自己推這一塊）：還沒打的帶約戰那一塊此刻歸誰、兩條進度（mine 是看的人這一邊、
        # theirs 是約戰那一軍）、約戰那一軍離翻走還差多少、幾人在推——站在哪裡都一樣，守住了拉回的就是 theirs
        if card["status"] in ("open", "answered"):
            bars = conquest.bars(w, duel.block)
            foe = bars.get(duel.attacker.side, 0.0)
            card["holder"] = conquest.holder(w, c, duel.block)
            card["bars"] = {"mine": round(bars.get(side, 0.0)), "theirs": round(foe)}
            card["to_flip"] = max(0, round(conquest.FULL - foe))
            card["foe_pushing"] = sum(1 for row in conquest.pushers(w, c, duel.block) if row["side"] == duel.attacker.side)
        out.append(card)
    return out


def duel_amount(ctx: Game, side: str, loc_id: str, base: float, name: str) -> tuple[float, float]:
    """約戰推（拉）的量（計畫 4.0 之三第 11 條）：base（名目量 × 結果倍率）× progress_scale × 傳檄 ÷ √n（side 這一邊的活躍人數，含 name）
    ×（1＋集火：side 一小時內在這一塊出陣過的別人，含同去的）。回（量, 集火）。"""
    s, c = ctx.state, ctx.content
    w, cfg = s.world, c.config
    amount = base * sortie_duel.progress_scale(c)
    if (writ := seal_acts.writ_factor(w, c, conquest.line_of(w, c, loc_id), side)) != 1.0:
        amount *= writ
    window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
    recent = {n for n, last in w.active_pushers.get(side, {}).items() if w.time - last <= window} | {name}
    amount = push.buffered(amount, len(recent))
    focus = conquest.focus_bonus(w, c, loc_id, side, name)
    return amount * (1 + focus), focus


def duel_loot(ctx: Game, squad: Squad | None) -> str:
    """出陣前那張卡「贏了」那一段的戰利（一句話）：照 _sortie_full（一類一顆開著）或 _sortie_drill 的算法；沒有駐軍是空字串。"""
    if squad is None:
        return ""
    s, c = ctx.state, ctx.content
    cfg = c.config.sortie
    if precise.on(c, s.world):
        exp, xinde = round(squad.exp * cfg.reward_scale), round(squad.reward_xinde * cfg.reward_scale)
        silver = squad.reward_silver + s.player.member.level * cfg.merit_silver_per_level
    else:
        share = c.config.drill_reward_share
        exp, xinde = drill_share(squad.exp, share), drill_share(squad.reward_xinde, share)
        silver = int(squad.reward_silver * c.config.economy.sortie_silver_share + 0.5) if c.config.economy.sortie_silver else 0
    return sortie_duel.LOOT_LINE.format(exp=exp, xinde=xinde, silver=silver)


def sortie_card(ctx: Game) -> dict | None:
    """main.sortie_card（欄位表 1.3 的「出陣前那張卡」；main.sortie 是出陣開著的布林、照舊）：約戰關著、序章、散人、在路上、不是區塊是 None。
    這一塊（此刻歸誰、兩條各幾成與對面那一條是哪一軍、離易手、對面幾人在推、同袍幾人與集火、運糧隊）、贏了（推一程、貢獻、離下一階、戰利、
    翻了分紅、軍令對不對、戰書還差）、今天還能幾次、冷卻、能封的招、貼不了的原因、兩軍的名字、約戰窗幾分鐘、應戰的體力（出陣約戰網頁丙，
    2026-10-28：網頁不寫死陣營名、10 分、12）。自家的地方（搶得下來、此刻是自己這一邊的；按出陣只會「等對面來約」）：to_flip 是對面離翻走
    這裡還差多少、gain 是 None（守就是應戰，推不了自家的條）。"""
    s, c = ctx.state, ctx.content
    if not duel_on(ctx) or prologue_rules.active(s, c):
        return None
    p, w = s.player, s.world
    side = ctx._conquest_side()
    loc = p.location
    if side is None or p.journey is not None or loc not in conquest.blocks(c):
        return None
    cfg, qcfg = c.config.sortie, c.config.conquest
    bars = conquest.bars(w, loc)
    mine = bars.get(side, 0.0)
    theirs = max((v for k, v in bars.items() if k != side), default=0.0)
    foe = next((x for x in conquest.SIDES if x != side), None)  # 交戰兩軍只有兩邊：對面那一條就是另一軍的
    holder = conquest.holder(w, c, loc)
    own = conquest.capturable(c, loc) and holder == side
    nominal = conquest.sortie_nominal(c, loc, "attack")
    est, focus = duel_amount(ctx, side, loc, nominal * cfg.result_scale["win"], p.name)
    squad = duel_squad(ctx, loc)
    fight = conquest.fight_of(w, loc)
    pushed = dict(fight.bars[side].pushers) if fight is not None and side in fight.bars else {}
    total = sum(pushed.values()) + est
    part = (pushed.get(p.name, 0.0) + est) / total if total > 0 else 0.0
    pool = qcfg.take_silver * (1.0 if conquest.start_kind(w, c, loc) == conquest.NEUTRAL else qcfg.faction_pool_share)
    rank = ranks.rank_of(s)
    rank_next = max(0, ranks.threshold(c, rank + 1) - p.contrib) if 1 <= rank < 3 and calendar.season_one_on(w, c) else None
    line = conquest.line_of(w, c, loc)
    order_match = any(
        o.template == "siege" and not o.done and o.front == line and loc in orders.siege_places(c, side, line, w)
        for o in orders.current(s, c, side) if o.front is not None
    )
    convoy = orders.extra_enemies(s, c, loc, ctx._side()) if p.journey is None else []
    cooldown = p.sortie_cooldown_until if sortie_duel.cooling(p.sortie_cooldown_until, ctx.now) else None
    contribution = push.contribution(nominal, 1.0, 1.0, c.config.contrib_per_push, c.config.over_cap_contrib_ratio) \
        if calendar.season_one_on(w, c) else 0
    return {
        "block": loc, "place": c.locations[loc].name, "holder": holder,
        "sides": {x: c.scenario.faction_name(x, x) for x in conquest.SIDES},
        "bars": {"mine": round(mine), "theirs": round(theirs), "theirs_side": foe},
        "to_flip": max(0, round(conquest.FULL - (theirs if own else mine))),
        "foe_pushing": sum(1 for row in conquest.pushers(w, c, loc) if row["side"] != side),
        "allies": round(focus / qcfg.focus_step) if qcfg.focus_step > 0 else 0, "focus_bonus": round(focus, 2),
        "convoy_at": c.squads[convoy[0]].name if convoy else None,
        "gain": None if own else {
            "push": round(est), "contribution": contribution, "rank_next": rank_next, "loot": duel_loot(ctx, squad),
            "dividend": round(pool * part), "order_match": order_match, "letter_gap": max(0, round(qcfg.letter_at - mine)),
        },
        "left_today": ctx.sorties_left(), "cooldown_until": cooldown, "cost": cfg.jianfa_stamina,
        "moves": list(cfg.moves), "why_not": sortie_go_problem(ctx) or "",
        "window_minutes": cfg.window_minutes, "answer_stamina": cfg.answer_stamina,
    }


def duel_candidates_for(ctx: Game) -> Callable[[SortieDuel], list[SortieSide]]:
    """到時沒有真人應戰時能補位的人（sortie_duel.advance 的 candidates_for；計畫 4.0 之三第 15 條）：這一季的假人裡跟攻方不同一軍（兩軍之一）、
    不在路上、今天還有應戰次數、體力夠、不在輸了的冷卻裡的。威力照 _duel_power_of 抄；同區優先由 sortie_duel.bot_answer 挑。真人不補位。"""
    if not hasattr(ctx.world, "db"):
        return lambda duel: []
    c, cfg = ctx.content, ctx.content.config.sortie
    season, today = ctx.world.get_season_number(), ctx._pill_day()
    pool: list[list[SortieSide]] = []

    def candidates(duel: SortieDuel) -> list[SortieSide]:
        if not pool:
            rows: list[SortieSide] = []
            for state in CharacterStore(ctx.world.db).all(bots_only=True):
                p = state.player
                if p.bot is None or not server_bots.active(p.bot, season) or p.journey is not None or p.location is None:
                    continue
                state.world = ctx.state.world  # 存檔不帶季（exclude）：豪強依附哪一軍、威力都照手上這一份季算
                side = allied.side_of(state, c)
                if side not in conquest.SIDES:
                    continue
                if sortie_duel.answers_left(p, cfg, today) <= 0 or p.stamina < cfg.answer_stamina \
                        or sortie_duel.cooling(p.answer_cooldown_until, ctx.now):
                    continue
                rows.append(SortieSide(name=p.name, side=side, power=duel_power_of(state, c, ctx.world),
                                       region=seal_acts.region_of(c, p.location)))
            pool.append(rows)
        return [row for row in pool[0] if row.side != duel.attacker.side]

    return candidates


def duel_tick(ctx: Game) -> list[SortieDuel]:
    """把到時的約戰結算掉（sortie_duel.advance）：world_tick（伺服器排程）、sync（排程關著時下一個同步的人替它收）、advance 都叫；假人程式另外
    每一輪叫 sortie_duel_tick。先只讀 world 那一列（sortie_duels）看有沒有到時的（季收了的、還沒打的也算），沒有就不開 world.mutate；advance
    只碰 open／answered 的（結算過的在 world 那一列已經是 settled），兩個程式輪流同步不重複、不倒退。標好結果之後在同一把鎖裡把季的進度與
    兩邊做完（_settle_duel）、存季。關著、暫停中什麼都不做。回這一下結算或作廢的那幾張。"""
    if not duel_on(ctx) or ctx.world.paused_at() is not None:
        return []
    ended = ctx.state.world.ended
    if not any(d.status in ("open", "answered") and (ended or sortie_duel.due(d, ctx.now))
               for d in ctx.world.sortie_duels().values()):
        return []
    cfg = ctx.content.config.sortie
    candidates = duel_candidates_for(ctx)
    done: list[SortieDuel] = []

    def _apply(shared) -> None:
        waiting = {key for key, d in shared.sorties.items() if d.status == "open" and d.defender is None}
        for duel in sortie_duel.advance(shared, cfg, ctx.now, candidates):
            if duel.id in waiting and duel.defender is not None and not duel.defender.garrison:
                duel.report["filled"] = True  # 補位的人：結算時扣他一次應戰與體力（同真人應戰）
            done.append(duel.model_copy(deep=True))

    ctx.world.mutate(_apply)
    for duel in done:
        settle_duel(ctx, duel)
    if done:
        ctx._save_season()
    return done


def sortie_duel_tick(ctx: Game, now: float) -> int:
    """假人程式每一輪替窗滿了的約戰結算（bot_runner.BotRunner.tick；伺服器排程關著、也沒有人同步時，十分鐘到了照樣收）：讀回這一季、推到 now。
    回這一下結算或作廢了幾張。"""
    ctx.now = now
    ctx.state.world = ctx.world.get_season()
    return len(duel_tick(ctx))


def duel_party(ctx: Game, name: str) -> Game | None:
    """這一場的一方（自己就是那一位時是自己，不然照 _load_kin 讀出來、季接上手上這一份）。讀不到是 None。"""
    if name and name_key(name) == name_key(ctx.state.player.name):
        return ctx
    return ctx._load_kin(name)


def settle_duel(ctx: Game, duel: SortieDuel) -> None:
    """一張約戰結算（或作廢）之後（計畫 4.0 之三第 8、11～16 條）：季的進度改在 ctx.state.world；攻方、同去的、應戰的人（含補位的）各一份戰報與
    一則江湖紀錄，自己就是那一方時改自己，別人改完存回（_save_kin）。守軍什麼都不拿。"""
    roles: list[tuple[str, str]] = [(duel.attacker.name, "attacker"), *((n, "ally") for n in duel.attacker.allies)]
    d = duel.defender
    if d is not None and not d.garrison:
        roles.append((d.name, "defender"))
    games: dict[str, Game] = {}
    for name, _ in roles:
        g = duel_party(ctx, name)
        if g is not None:
            games[name_key(name)] = g
    try:
        if duel.status == "void":
            for name, role in roles:
                if (g := games.get(name_key(name))) is not None:
                    duel_void(g, duel, role)
            return
        duel_result(ctx, duel, roles, games)
    finally:
        for g in games.values():
            if g is not ctx:
                ctx._save_kin(g)


def duel_void(ctx: Game, duel: SortieDuel, role: str) -> None:
    """沒打成（季終、連守軍都沒有；PM 四之五第 5 件）：攻方與同去的退一次出陣（同一天才退次數）與 jianfa_stamina，應戰了的人退一次應戰與
    answer_stamina；冷卻不退。記一則江湖紀錄。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.sortie
    today = ctx._pill_day()
    if role == "defender":
        sortie_duel.spend_answer(p, today, -1)
        p.stamina = min(float(c.config.stamina_max), p.stamina + cfg.answer_stamina)
    else:
        if p.sortie_day == today and duel.report.get("day") == today:
            p.sorties_today = max(0, p.sorties_today - 1)
        p.stamina = min(float(c.config.stamina_max), p.stamina + cfg.jianfa_stamina)
    ctx._write(sortie_duel.GO_TITLE.format(place=duel.place), [sortie_duel.VOID_LINE.format(place=duel.place)], tag=sortie_duel.LABEL)


def duel_result(ctx: Game, duel: SortieDuel, roles: list[tuple[str, str]], games: dict[str, Game]) -> None:
    """結算了的那一張：軍令照推（拉）之前的清單記（FB-608）→ 推攻方那一條或拉回（守方贏）→ 貢獻 → 每一方的戰報、戰利或經驗心得、
    氣血內傷、冷卻、紀錄（_duel_report）。"""
    s, c = ctx.state, ctx.content
    w, cfg = s.world, c.config.sortie
    loc, side, d = duel.block, duel.attacker.side, duel.defender
    squad = c.squads.get(duel.report.get("squad") or "")
    how, scale = sortie_duel.scale_of(duel, cfg)
    tier = duel.result.tier
    nominal = conquest.sortie_nominal(c, loc, "attack")
    attacker = games.get(name_key(duel.attacker.name))
    defender = games.get(name_key(d.name)) if d is not None and not d.garrison else None
    drafts = {key: Draft(sortie_duel.GO_TITLE.format(place=duel.place)) for key in games}  # 結果標記照戰報（_file_battle 填）
    saved = {key: g._draft for key, g in games.items()}
    msgs: dict[str, list[str]] = {key: [] for key in games}
    for key, g in games.items():
        g._draft = drafts[key]
    try:
        # 軍令：推（拉）之前的清單（推滿易手、拉回歸零的那一下推完就不在清單上了）
        if tier in ("big", "win") and attacker is not None and squad is not None:
            msgs[name_key(duel.attacker.name)] += attacker._order_credit(
                side=side, kind="win", location=loc, front=front_of(c, loc), squad=squad.id, squad_faction=squad.faction)
        if how == "pull" and defender is not None:
            msgs[name_key(d.name)] += defender._order_credit(side=d.side, kind="duty", location=loc, front=conquest.line_of(w, c, loc))
        moved, credited = duel_move(ctx, duel, how, scale, nominal)
        week = calendar.point(w.time, c, w).week
        points = push.contribution(nominal * scale, 1.0, 1.0, c.config.contrib_per_push, c.config.over_cap_contrib_ratio) \
            if credited and calendar.season_one_on(w, c) else 0
        for name, role in roles:
            g = games.get(name_key(name))
            if g is None:
                continue
            if points and (role in ("attacker", "ally")) == (how == "push"):
                # 帳記貼（應）約戰那一刻替的那一軍（FB-856）：攻方與同去的是攻方那一軍（同去要同一軍），應戰的是守方那一軍；
                # 豪強窗內改幫，結算時 p.ally 已經是新的那一軍，不照它記
                mine = side if role in ("attacker", "ally") else (d.side if d is not None else None)
                wins.credit(g.state.player, c, w, week, points, side=mine)
                msgs[name_key(name)].append(f"貢獻 +{points}")
            msgs[name_key(name)] += duel_report(g, duel, role, squad, moved)
        for key, g in games.items():
            journal.add_entry(g.state, g._draft.entry(w.time, msgs[key]))
    finally:
        for key, g in games.items():
            g._draft = saved[key]


def duel_move(ctx: Game, duel: SortieDuel, how: str, scale: float, nominal: float) -> tuple[list[str], bool]:
    """這一塊怎麼動（季的進度，ctx.state.world）：攻方大勝、勝、僵持推攻方那一條（conquest.push；推不動照舊打完、不推、不記貢獻）；攻方敗拉攻方
    那一條（conquest.guard_pull，守城功照翻地設計 4.5）。回（寫給兩邊的句子，記不記貢獻）。"""
    s, c = ctx.state, ctx.content
    w = s.world
    loc, side, place = duel.block, duel.attacker.side, duel.place
    name = duel_who(ctx, side)
    if how == "push":
        if scale <= 0:
            return [], False
        why = conquest.push_problem(w, c, side, loc, "attack")
        if why is not None:
            return [sortie_duel.MOVE_STILL.format(place=place, why=why)], False
        amount, _ = duel_amount(ctx, side, loc, nominal * scale, duel.attacker.name)
        done = conquest.push(w, c, loc, side, duel.attacker.name, amount, "attack")
        conquest.mark(w, c, loc, duel.attacker.name, side, "attack", done.moved)
        conquest.tally(w, c, ctx._pill_day(), side, duel.attacker.name, done.moved)
        window = c.config.active_window_days * DAY / calendar.cal_scale(c, w)
        for who in (duel.attacker.name, *duel.attacker.allies):
            w.active_pushers.setdefault(side, {})[who] = w.time
        w.active_pushers = push.drop_stale(w.active_pushers, w.time, window)
        if done.flipped:
            return [sortie_duel.MOVE_FLIP.format(place=place, side=name), conquest.PAYOUT_NEXT], True
        return [sortie_duel.MOVE_LINES[duel.result.tier].format(place=place, side=name)], True
    d = duel.defender
    if conquest._still(w, c, loc):  # noqa: SLF001  剛易手、戰書凍結、碎片鎮住：誰都動不了（同 conquest.pull）
        return [sortie_duel.MOVE_STILL.format(place=place, why=conquest.push_problem(w, c, side, loc, "attack") or "")], False
    amount, _ = duel_amount(ctx, side, loc, nominal * scale, duel.attacker.name)
    holder = d.side if d is not None and d.side in conquest.SIDES else None
    pulled = conquest.guard_pull(w, c, loc, side, amount, name="" if d is None or d.garrison else d.name, holder_side=holder)
    key = "pull" if pulled.moved > 0 else "hold"
    return [sortie_duel.MOVE_LINES[key].format(place=place, side=name), *pulled.lines], d is not None and not d.garrison


def duel_toll(ctx: Game, share: float, lost: bool) -> list[str]:
    """三回合扣的氣血（share 是氣血上限的幾成，照舊吃身法、根骨、防具減損，一部分變內傷：team._apply_toll）；輸的另加內傷 lose_injury。"""
    s, c = ctx.state, ctx.content
    p = s.player
    msgs: list[str] = []
    hurt = 0.0
    if share > 0:
        cut = min(c.config.armor.total_cap, team.armor_cut(s, c, ctx.world))
        lost_hp, hurt = team._apply_toll(c, p.member, share * (1 - cut), agi=p.stats.get("agi", team.BASE_STAT),
                                         con=team.con_of(s, c, ctx.world, PLAYER), injury=treasures.amount(s, c, "injury"))
        if round(lost_hp) > 0:
            msgs.append(f"氣血 -{lost_hp:.0f}")
    if lost and c.config.sortie.lose_injury > 0:
        p.member.injury += c.config.sortie.lose_injury
        hurt += c.config.sortie.lose_injury
    if hurt >= 1:
        msgs.append(f"內傷 +{hurt:.0f}")
    return msgs


def duel_hold_gains(ctx: Game, squad: Squad, record) -> list[str]:
    """守方贏了（真人或補位的人）：跟攻方打贏一樣的經驗心得（那一塊駐軍那一路的 reward_scale 倍；一類一顆關著照三成），不給銀兩與掉落（PM）。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.sortie
    if precise.on(c, s.world):
        xinde = round(squad.reward_xinde * cfg.reward_scale * (1 + treasures.amount(s, c, "win_xinde_pct")))
        exp = round(squad.exp * cfg.reward_scale * (1 + treasures.amount(s, c, "win_exp_pct")) * ranger.exp_factor(s, c))
    else:
        share = c.config.drill_reward_share
        xinde, exp = drill_share(squad.reward_xinde, share), drill_share(squad.exp, share)
    msgs: list[str] = []
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = (record.xinde or 0) + xinde
        msgs.append(f"心得 +{xinde}")
    msgs += ctx._record_exp(record, exp, "answer")  # 應戰是仗（growth.exp_source；45 級以後照樣升，不乘遭遇拍的兩道閘）
    levels, record.levelups = team.grant_team_exp(s, c, ctx.world, exp, "answer")
    record.notes += levels
    return msgs + levels


def duel_report(ctx: Game, duel: SortieDuel, role: str, squad: Squad | None, moved: list[str]) -> list[str]:
    """這一方的戰報（kind sortie、label 約戰；三回合各一行、對面是誰、結果、這一塊怎麼動、離易手還差、離下一階、同去的、戰利或經驗心得、
    氣血內傷、截糧、下一次什麼時候）、行狀一筆、冷卻；補位的人扣一次應戰與體力。回寫進這一則江湖紀錄的話。"""
    s, c = ctx.state, ctx.content
    p, w, cfg = s.player, s.world, c.config.sortie
    result, d = duel.result, duel.defender
    fought = role != "ally"
    mine = d if role == "defender" else duel.attacker
    rival = duel.attacker if role == "defender" else d
    tier_word = sortie_duel.side_tier(duel, p.name) or sortie_duel.TIER_WORDS[result.tier]
    record = BattleRecord(
        id=s.battle_seq + 1, time=w.time, location=duel.place, kind="sortie", label=sortie_duel.LABEL,
        opponent=sortie_duel.GARRISON if rival is None or rival.garrison else rival.name, ours=[Fighter(name=p.name, level=p.member.level)],
        tier=tier_word, our_power=mine.power if mine is not None else 0.0, difficulty=rival.power if rival is not None else 0.0,
        rounds=sortie_duel.round_lines(duel),
    )
    record.notes.append(sortie_duel.vs_line(duel))
    if duel.attacker.allies:
        record.notes.append(sortie_duel.VS_ALLIES.format(names="、".join(duel.attacker.allies)))
    record.notes.append(sortie_duel.TALLY_LINE.format(wins=result.wins, losses=result.losses, draws=result.draws, attacker=duel.attacker.name))
    record.notes += moved
    bar = conquest.bar(w, duel.block, duel.attacker.side)
    who = duel_who(ctx, duel.attacker.side)
    if bar > 0:
        record.notes.append(sortie_duel.GAP_LINE.format(side=who, place=duel.place, value=round(bar), left=max(0, round(conquest.FULL - bar))))
    msgs: list[str] = []
    won = tier_word in team.WIN_TIERS
    if fought and won and squad is not None:
        rng, ctx.rng = ctx.rng, random.Random(f"約戰戰利|{duel.id}|{p.name}")  # 掉落用這一場自己的亂數（不碰 Game.rng）
        try:
            msgs += sortie_actions.sortie_rewards(ctx, squad, record) if role == "attacker" else duel_hold_gains(ctx, squad, record)
        finally:
            ctx.rng = rng
        if role == "attacker":
            msgs += ctx._deed_fame("sortie")  # 名聲 3.1：出陣攻打贏 +1
    if role == "defender" and duel.report.get("filled"):
        sortie_duel.spend_answer(p, ctx._pill_day())  # 補位的人：同真人應戰扣一次應戰與體力
        p.stamina = max(0.0, p.stamina - cfg.answer_stamina)
    lost = fought and tier_word == "落敗"
    if fought:
        share = result.defender_toll if role == "defender" else result.attacker_toll
        toll = duel_toll(ctx, share, lost)
        record.changes += toll
        msgs += toll
        after = sortie_duel.cooldown_after(duel, p.name, cfg)
        if after.sortie is not None:
            p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, after.sortie)
        if after.answer is not None:
            p.answer_cooldown_until = max(p.answer_cooldown_until or 0.0, after.answer)
        if lost:
            record.notes.append(sortie_duel.LOSE_LINE.format(n=f"{cfg.lose_cooldown_minutes:g}"))
        annal_line = sortie_duel.ANNAL_ANSWER_LINE if role == "defender" else sortie_duel.ANNAL_LINE  # 應戰的人（含補位的）另一句（FB-897）
        annals.note(s, c, annals.DUEL, annal_line.format(  # 地點寫約戰的那一塊（結算時人可能已經走了）
            place=duel.place, rival=rival.name if rival is not None and not rival.garrison else sortie_duel.GARRISON, tier=tier_word), 2,
            place=duel.place, keep=[rival.name] if rival is not None and not rival.garrison else None)  # 對手是玩家：名號原樣留（FB-9020）；守軍不必
    rank = ranks.rank_of(s)
    if 1 <= rank < 3 and calendar.season_one_on(w, c):
        record.notes.append(sortie_duel.RANK_LINE.format(n=max(0, ranks.threshold(c, rank + 1) - p.contrib)))
    if orders.extra_enemies(s, c, duel.block, ctx._side()):
        record.notes.append(sortie_duel.CONVOY_LINE.format(place=duel.place))
    left, answers = ctx.sorties_left(), answers_left(ctx)
    record.notes.append(sortie_duel.NEXT_LINE.format(
        sortie=sortie_duel.NEXT_DONE if left <= 0 else sortie_duel.minutes_text(p.sortie_cooldown_until, ctx.now),
        answer=sortie_duel.NEXT_DONE if answers <= 0 else sortie_duel.minutes_text(p.answer_cooldown_until, ctx.now),
    ))
    if fought:
        line = ctx._file_battle(record)
    else:
        battlelog.add_record(s, record)
        line = battlelog.summary_line(record)
        if ctx._draft is not None:
            ctx._draft.outcome(battlelog.outcome_text(record), line)
            ctx._draft.battle_id = record.id
    return [line, sortie_duel.vs_line(duel), *moved, *msgs]


def duty_credit(ctx: Game) -> list[str]:
    """約戰開著的季巡哨、傳道、保境安民那一點貢獻（企劃者 2026-10-24 第 2 件：Config.sortie.duty_contribution，一天 duty_per_day 次；
    duty_day／duties_today 照 _pill_day 換日）。第一季的規則關著（沒有貢獻）、今天記滿了是空的。"""
    s, c = ctx.state, ctx.content
    p, w, cfg = s.player, s.world, c.config.sortie
    today = ctx._pill_day()
    if p.duty_day != today:
        p.duty_day, p.duties_today = today, 0
    if cfg.duty_contribution <= 0 or p.duties_today >= cfg.duty_per_day or not calendar.season_one_on(w, c):
        return []
    p.duties_today += 1
    wins.credit(p, c, w, calendar.point(w.time, c, w).week, cfg.duty_contribution)
    return [f"貢獻 +{cfg.duty_contribution}"]
