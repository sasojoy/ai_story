"""擂台賽（隨時挑擂；docs/superpowers/specs/2026-10-14-擂台賽-design.md）。Joy 2026-10-14：「我再想開一個擂台賽，讓他們可以報名，然後可以
對戰，但是如何對戰我還沒想好，因為很難兩個人都同時在線」，在選擇卡選了「隨時挑擂」：報名的人留下一份守擂的分身，別人隨時來挑，
對的是分身，只算本季。同一天又定了配套（PM 轉述 Joy：「挑戰只能挑戰距離自己三名內」「讓玩家沒體力時隨時能挑戰，所以不一定要鎖死在
城鎮」「第一名或是前幾名有什麼獎勵或是稱號」）：

- 名次制（不是積分）：報名排到榜尾，只能挑排在自己前面 reach（3）名以內的人；挑的人贏了兩人交換名次，僵持、輸了都不動。
- 不花體力，一個人一天挑 per_day（10）次，照回體丹那一套的現實時間換日（Game._pill_day）；哪裡都能報名、挑擂（路上、閉關中也行）。
- 稱號照此刻的名次（title_of）：第一「天下第一」、二三「擂台三甲」、四到十「擂台十傑」，掉出就沒了。
- 每天換日那一刻照名次記一筆俸（roll_day → ArenaEntry.wages，本人同步時領）；季末前三名名望與寶物、江湖史記「擂主」（跨季的歷屆擂主照它）。

- 守擂的人記在這一季的 WorldState.arena（名號鍵 → ArenaEntry）；換季整個重來。
- 一場（ArenaFight，挑的人身上）照頭目戰與奪璽單挑的純函式打：duel.push_of、harm_of、gamble_roll、verdict_at；分身的招照奪璽單挑的
  代打（份量的 proxy_power 次方加權），回合開始時擲好、給挑的人看一句架勢。兩邊的池子都從滿的開始，打完不扣回角色。
- 亂數全用自己的（「擂台|季|名號|場次|回合|用途」），不碰 Game.rng。

只算數字與句子、改傳進來的 ArenaFight 與 WorldState；戰報、江湖紀錄、補送在 Game（engine.py 的「擂台」那一段）。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from . import battle_instance, tactics
from . import prologue as prologue_rules
from . import duel as duel_rules
from .characters import name_key
from .models import MOVES, ArenaTuning, Content, DuelTuning
from .state import ArenaEntry, ArenaFight, ArenaSide, GameState, PlayerState, WorldState

DAY = 86400
WIN_TIERS = ("大勝", "險勝")
SCORES = {"大勝": 1.0, "險勝": 1.0, "僵持": 0.5, "落敗": 0.0}
FLIP = {"大勝": "落敗", "險勝": "落敗", "僵持": "僵持", "落敗": "險勝"}  # 守的人那一邊（挑的人落敗時守的人照氣勢再分，見 defender_tier）
TITLES = ((1, "天下第一"), (3, "擂台三甲"), (10, "擂台十傑"))  # （到第幾名, 稱號）：PM 2026-10-14 定，字句不必問 Joy

JOIN_ID = "arena:join"
BACK_ID = "arena:back"
YIELD_ID = "arena:yield"  # 認輸下台（整季機器人不按它：bot.pick）

# 待 joy 潤
ARENA = "擂台"
JOIN = "報名守擂（排到榜尾，留下此刻的身手當分身）"
UPDATE = "更新守擂分身（換成此刻的身手）"
BACK = "返回"
YIELD = "認輸下台（算落敗）"
NO_ARTS = "你身上還沒有武學，上不了擂台。"
JOINED = "你在擂台登記了名號，排在第 {rank} 名，留下一份分身守擂：{arts}。別人隨時可以來挑。"
UPDATED = "你換了一份守擂的分身：{arts}。名次與戰績照舊。"
JOIN_FIRST = "先報名守擂"
BEHIND = "排在你後面"
OUT_OF_REACH = "只能挑前 {n} 名內的人"
FAMED_NOTE = "天下聞名：排在他後面 {n} 名內的人都挑得到他"  # 名聲 4.7（擂台那一頁挑得到的人那一格）
COOLING = "剛挑過，{wait}後可再挑"  # wait 是現實的倒數（wait_text）
SPENT = "今天的 {n} 次挑完了，明日 00:00 後再挑"  # 照回體丹的現實時間換日（Game._pill_day）
SPENT_PURSE = "明日 00:00 再挑"  # 擂台那一頁右上角（窄）
LEFT = "今天還能挑 {n} 次"
NOBODY = "你前面沒有人了：你就是天下第一。"
NOBODY_AHEAD = "擂台上還沒有別人守擂。"
OPENING = "{foe}的分身跳上擂台，抱拳道：「請。」"
FOE_ARTS = "他守擂用的是{arts}。"
TELL_NOTE = "（架勢不一定是真的。）"
HOWTO = "固守剋強攻、強攻剋奇襲、奇襲剋固守；也可以在下面寫一句，放手一搏。"
YIELDED = "你拱手認輸，跳下擂台。"
STANDING = "你在擂台排第 {rank} 名{title}，{record}。"
UNRANKED = "你還沒報名守擂。報了名排到榜尾，可以挑排在你前面 {n} 名內的人。"
TOP = "擂台前列：{names}。"
GAMBLE_NOTE = "寫得越險，成了越能扭轉局面；失手時氣勢倒退，重傷的是你自己。這一回合他的招不算。"
PROMPT = "放手一搏：寫下你要怎麼對付他（20 字以內）"
PROMPT_SHORT = "放手一搏：寫一句（20 字內）"  # 擂台那一頁的輸入框（窄）
SETTING = "江湖擂台上一對一比武的"  # 給 battle_instance.assess_gamble
PLACE = "擂台"
SWAPPED = "擂台名次 第 {before} → 第 {after} 名"
KEPT = "擂台名次 第 {rank} 名（不變）"
NEW_FIRST = "擂台易主：{winner}擊敗{loser}，登上擂台天下第一。"
STREAK = "{name}在擂台上連勝 {n} 場，一時無人能擋。"
HIGHLIGHT = "擂台上最令人印象深刻的一幕：{name}放手一搏——「{text}」，竟然成了！"
DEFENDED = "{name}上擂台挑你留下的分身。"
UNSETTLED = "這一季收了，擂台上沒打完的那一場不算。"
SEASON_TOP = "本季擂台前三名：{names}。"
CHAMPION = "本季擂主：{name}。"  # 江湖史跨季保留；歷屆擂主照這個開頭找（champions）
CHAMPION_HEAD = "本季擂主："
CHAMPIONS_TITLE = "### 歷屆擂主"
WAGE = "擂台第 {rank} 名（{title}）的俸發下來了：銀兩 +{silver}、名望 +{fame}。"
PRIZE = "本季擂台第 {place} 名：名望 +{fame}。"


def held_kind(p: PlayerState) -> str:
    """擂台動畫：手上兵器的種類（models.WEAPON_KINDS）；沒拿兵器是空字串（空手）。只給畫面用，不碰數字。"""
    return p.weapon.kind if p.weapon is not None else ""


def looks_view(looks: list[str]) -> dict:
    """擂台動畫給網頁的兩邊兵器種類（舊的一場沒記：兩邊都當空手）。"""
    me, foe = (list(looks) + ["", ""])[:2]
    return {"me": me, "foe": foe}


def on(content: Content) -> bool:
    return content.config.arena.enabled


def here(state: GameState, content: Content) -> bool:
    """此刻打得開擂台：開關開著、季在跑、不在序章、這一季走到開擂台的那一週（減法季 6.6 第 2 週，week_unlock.open；規則關著一律開）。
    哪裡都行（路上、閉關中也行；PM 轉述 Joy 2026-10-14「不一定要鎖死在城鎮」）。"""
    from . import week_unlock  # week_unlock → rules → … 繞回來，呼叫時才取

    return on(content) and not state.world.ended and not prologue_rules.active(state, content) and week_unlock.open(state, content, "arena")


def entry_of(world: WorldState, name: str) -> ArenaEntry | None:
    return world.arena.get(name_key(name))


def ladder(world: WorldState) -> list[ArenaEntry]:
    """守擂的人照名次排（第一名在前）。"""
    return sorted(world.arena.values(), key=lambda e: (e.rank, e.joined, name_key(e.name)))


def title_of(world: WorldState, name: str) -> str | None:
    """此刻的稱號（TITLES）：沒報名、十名以外是 None。"""
    entry = entry_of(world, name)
    if entry is None:
        return None
    return next((title for last, title in TITLES if entry.rank <= last), None)


def title_for(rank: int) -> str | None:
    return next((title for last, title in TITLES if rank <= last), None)


def pair_key(me: str, foe: str) -> str:
    return f"{name_key(me)}>{name_key(foe)}"


def day_of(world: WorldState) -> int:
    return int(world.time // DAY)


def left_today(state: GameState, cfg: ArenaTuning, today: int) -> int:
    """今天還能挑幾次（per_day；照現實時間換日，同回體丹）。"""
    p = state.player
    return max(0, cfg.per_day - (p.arena_today if p.arena_day == today else 0))


def spend(state: GameState, today: int) -> None:
    p = state.player
    p.arena_today = (p.arena_today if p.arena_day == today else 0) + 1
    p.arena_day = today


def cool_left(world: WorldState, me: str, foe: ArenaEntry, cfg: ArenaTuning) -> float:
    """你挑這個人的冷卻還剩幾個世界秒（pair_cooldown_seconds，開打那一刻起算）；0＝沒在冷卻。"""
    last = world.arena_pairs.get(pair_key(me, foe.name))
    if last is None or not 0 <= world.time - last < cfg.pair_cooldown_seconds:
        return 0.0
    return cfg.pair_cooldown_seconds - (world.time - last)


def wait_text(real_seconds: float) -> str:
    """給玩家看的現實倒數：「約 40 分鐘」「約 2 小時 15 分」（分鐘四捨五入、至少 1 分；Joy 2026-10-16「看不出還有多久才能打」）。
    只寫現實的倒數、不寫季曆時刻（同路上的倒數，FB-062：季曆跑得比現實快，寫時刻玩家算不出來）。"""
    minutes = max(1, int(real_seconds / 60 + 0.5))
    if minutes < 60:
        return f"約 {minutes} 分鐘"
    hours, rest = divmod(minutes, 60)
    return f"約 {hours} 小時" + (f" {rest} 分" if rest else "")


def reach_of(foe: ArenaEntry, cfg: ArenaTuning) -> int:
    """排在他後面幾名內的人挑得到他：平常 reach；天下聞名的人（ArenaEntry.famed，名聲 4.7）放寬到 famous_reach。"""
    return max(cfg.reach, cfg.famous_reach) if foe.famed else cfg.reach


def challenge_problem(world: WorldState, me: str, foe: ArenaEntry, cfg: ArenaTuning, left: int,
                      time_scale: float = 1.0) -> str | None:
    """挑不挑得了這個人：先報名、他要排在你前面 reach 名以內（天下聞名的人放寬，reach_of）、今天還有次數、冷卻。
    None＝可以（守擂的人一天被挑幾場不設限，Joy 2026-10-15）。冷卻寫還要等多久（世界秒 ÷ time_scale ＝ 現實秒）。"""
    mine = entry_of(world, me)
    if mine is None:
        return JOIN_FIRST
    if foe.rank >= mine.rank:
        return BEHIND
    if mine.rank - foe.rank > reach_of(foe, cfg):
        return OUT_OF_REACH.format(n=cfg.reach)
    if left <= 0:
        return SPENT.format(n=cfg.per_day)
    wait = cool_left(world, me, foe, cfg)
    if wait > 0:
        return COOLING.format(wait=wait_text(wait / time_scale))
    return None


def note_challenge(world: WorldState, me: str, foe: ArenaEntry) -> None:
    """開打那一刻記冷卻（同截殺：開打就算，認輸、沒打完也算）。"""
    world.arena_pairs[pair_key(me, foe.name)] = world.time


def challengers(world: WorldState, content: Content, me: str, left: int) -> list[tuple[ArenaEntry, str | None]]:
    """挑得到的人：排在你前面 reach 名以內的，加上前面 famous_reach 名內天下聞名的（名次高的先），各自挑不挑得了
    （challenge_problem；None＝挑得了）。沒報名是空的。選單與擂台那一頁共用。"""
    cfg = content.config.arena
    mine = entry_of(world, me)
    if mine is None:
        return []
    rows = [e for e in ladder(world) if e.rank < mine.rank and mine.rank - e.rank <= reach_of(e, cfg)]
    return [(e, challenge_problem(world, me, e, cfg, left, content.config.time_scale)) for e in rows]


def join(world: WorldState, entry: ArenaEntry) -> ArenaEntry:
    """報名：排到榜尾。"""
    entry.rank = len(world.arena) + 1
    world.arena[name_key(entry.name)] = entry
    return entry


def swap(mine: ArenaEntry, foe: ArenaEntry) -> bool:
    """挑的人贏了：他排在你前面就交換名次（打的那一陣子名次可能被別人換過，照收場這一刻的名次）。換了是 True。"""
    if foe.rank >= mine.rank:
        return False
    mine.rank, foe.rank = foe.rank, mine.rank
    return True


def record_text(entry: ArenaEntry) -> str:
    if not entry.bouts:
        return "還沒打過"
    text = f"{entry.wins} 勝 {entry.losses} 負" + (f" {entry.draws} 和" if entry.draws else "")
    return text + (f"・連勝 {entry.streak}" if entry.streak >= 2 else "")


def board(world: WorldState, cfg: ArenaTuning) -> list[dict]:
    """擂台榜（擂台那一頁、見聞「榜單」分頁）：名次、名號、稱號、勝、負、和、連勝。"""
    return [
        {"rank": e.rank, "name": e.name, "title": title_for(e.rank), "wins": e.wins, "losses": e.losses, "draws": e.draws,
         "streak": e.streak}
        for e in ladder(world)[:cfg.board_size]
    ]


def standing(world: WorldState, name: str, cfg: ArenaTuning) -> list[str]:
    """打開擂台時的頭一句：你的名次、稱號與戰績，加上前三名。"""
    me = entry_of(world, name)
    if me is None:
        lines = [UNRANKED.format(n=cfg.reach)]
    else:
        title = title_for(me.rank)
        lines = [STANDING.format(rank=me.rank, title=f"（{title}）" if title else "", record=record_text(me))]
    top = ladder(world)[:3]
    if top:
        lines.append(TOP.format(names="、".join(f"{e.name}（第 {e.rank} 名）" for e in top)))
    return lines


def roll_day(world: WorldState, cfg: ArenaTuning, today: int) -> bool:
    """換日（現實時間，同回體丹）：第一次看到新的一天，前 len(wages) 名、打過至少一場的各記一筆俸（[天, 名次]），本人同步時領。
    第一次（arena_day 是 -1）只記今天、不發。季收了不發。動了 WorldState 是 True。

    **這個日子只准往前走**（2026-10-14 線上：擂台的俸無限發放）。「今天」是每個 Game 各算各的
    （Game._pill_day 讀 pill_now＝now＋advanced_real，而 advanced_real 只有管理者的「時間快轉」會加，
    加完留在那個 Game 物件上直到伺服器重開）。於是快轉過的那個人認為今天是 20741、其他人是 20740，
    舊的寫法無條件把 arena_day 設成自己的今天，兩邊輪流同步就讓它在 20740／20741 之間來回跳，
    每跳回來一次就再記一輪俸——線上一個人累積到 144 筆（4320 銀、144 名望）。
    往回的那一下現在直接當沒事（回 False），同一天也不再記第二筆。"""
    if world.ended or world.arena_day >= today or not world.arena:  # 擂台上沒人：不記天（同步什麼都沒有時不存季）
        return False
    if 0 <= world.arena_day < today:
        for e in ladder(world)[:len(cfg.wages)]:
            if e.bouts and not any(day == today for day, _ in e.wages):  # 同一天只記一筆（再保險一層）
                e.wages.append([today, e.rank])
    world.arena_day = today
    return True


def champions(chronicles: list[tuple[int, list[str]]]) -> str:
    """歷屆擂主（江湖史底下一段，跨季）：各季江湖史裡「本季擂主：」那一句。chronicles 是（季, 那一季江湖史的句子），新的一季在前。"""
    rows = []
    for number, texts in chronicles:
        for text in texts:
            if text.startswith(CHAMPION_HEAD):
                rows.append(f"- 第 {number} 季：{text.removeprefix(CHAMPION_HEAD).rstrip('。')}")
    return f"{CHAMPIONS_TITLE}\n\n" + "\n".join(rows) if rows else ""


def strength_words(content: Content, mine: float, theirs: float) -> str:
    """身手跟你比（字同奪璽單挑的 foe_line）。"""
    tuning = content.config.battle
    ratio = battle_instance.strength(tuning, theirs) / max(1.0, battle_instance.strength(tuning, mine))
    return ("遠比你強" if ratio >= 1.5 else "比你強" if ratio >= 1.1 else "跟你不相上下" if ratio > 0.9
            else "比你弱" if ratio > 0.6 else "遠比你弱")


def foe_line(me: ArenaSide, foe: ArenaSide, content: Content) -> str:
    """給模型評成功率的那一行（同奪璽單挑 seal_duel.foe_line：只寫比較）。"""
    words = strength_words(content, me.power, foe.power).replace("你", "玩家")
    hurt = "，已經帶傷" if foe.hp < foe.hp_cap * 0.5 else ""
    return f"{foe.name}（身手{words}{hurt}）"


def rng_for(season: int, name: str, fight: ArenaFight, what: str) -> random.Random:
    return random.Random(f"擂台|{season}|{name_key(name)}|{fight.id}|{fight.round + 1}|{what}")


def roll_next(fight: ArenaFight, rng: random.Random, cfg: ArenaTuning, tuning: DuelTuning) -> None:
    """分身下一回合的招與你看到的架勢（同奪璽單挑的代打：先取招、再取真假、再取句子）。"""
    values = [max(0.0, fight.foe.scores.get(m, 0.0)) for m in MOVES]
    top = max(values)
    weights = [(v / top) ** cfg.proxy_power for v in values] if top > 0 else [1.0] * len(MOVES)
    fight.move = rng.choices(MOVES, weights=weights)[0]
    true = rng.random() < tuning.tell_truth or tactics.locks(fight.bout).sees  # 看穿、他亂神：架勢一定是真的
    shown = fight.move if true else rng.choice([m for m in MOVES if m != fight.move])
    fight.tell = rng.choice(duel_rules.TELLS[shown])


def _weight(side: ArenaSide, move: str, content: Content) -> float:
    return side.scores.get(move) or battle_instance.strength(content.config.battle, side.power) * content.config.duel.foe_fit


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


def _pool(side: ArenaSide, lost: int) -> int:
    """池子扣 lost（負的是回，回到上限為止）：回實際扣了多少（取整數：池子是小數，見底那一下扣的是剩的那一截，
    回合那一句照 :+d 寫，小數會丟 ValueError——2026-10-16 量表的假人擂台每一回合見底都炸）。"""
    lost = min(side.hp, lost) if lost > 0 else max(-(side.hp_cap - side.hp), lost)
    side.hp -= lost
    return round(lost)


class Exchange(NamedTuple):
    delta: int
    mine_hp: int
    foe_hp: int
    beat: int
    mine: str | None
    his: str | None
    lines: list[str]


def exchange(fight: ArenaFight, move: str, content: Content, rng: random.Random, trng: random.Random | None = None,
             ) -> tuple[int, int, int, int]:
    """你出一招、分身出他擲好的那一招：（氣勢推了多少, 你掉多少, 他掉多少, 剋）。見 exchange_full。"""
    out = exchange_full(fight, move, content, rng, trng)
    return out.delta, out.mine_hp, out.foe_hp, out.beat


def exchange_full(fight: ArenaFight, move: str, content: Content, rng: random.Random, trng: random.Random | None = None) -> Exchange:
    """你出一招、分身出他擲好的那一招。兩邊各扣自己的池子（同奪璽單挑）。fight.bout 在（有人帶著本命戰法）時先照戰法打這一回合
    （tactics.step，亂數是 trng）：招可能被改掉、剋照無隙改、氣勢多推戰法那一份、沒挨打的那一邊不掉血、回的與焚身這類照池子算。"""
    tuning, battle, tt = content.config.duel, content.config.battle, content.config.tactics
    me, foe = fight.me, fight.foe
    his = fight.move
    step = None
    if fight.bout is not None and trng is not None:
        step = tactics.step(fight.bout, move, his, fight.edge, tt, trng, a_ratio=me.hp / max(1.0, me.hp_cap),
                            b_ratio=foe.hp / max(1.0, foe.hp_cap), b_auto=True)
        move, his = step.a_move, step.b_move
    mine, theirs = _weight(me, move or "", content), _weight(foe, his or "", content)
    beat = step.beat if step is not None else duel_rules.counter(move, his)
    luck = rng.uniform(-tuning.luck, tuning.luck) * tactics.luck_scale(fight.bout if step is not None else None)
    push = round(tactics.scale_push(duel_rules.push_of(mine, theirs, beat, me.role, tuning, battle, luck, foe_role=foe.role), step))
    my_hp = duel_rules.harm_of(me.hp_cap, mine, theirs, beat, tuning)
    foe_hp = duel_rules.harm_of(foe.hp_cap, theirs, mine, -beat, tuning)
    lines: list[str] = []
    if step is not None:
        push += round(step.push)
        my_hp = (round(my_hp * (1 - step.a_cut)) if step.a_hit else 0) - round(step.a_hp * me.hp_cap)
        foe_hp = (round(foe_hp * (1 - step.b_cut)) if step.b_hit else 0) - round(step.b_hp * foe.hp_cap)
        lines = list(step.lines)
        guarded, said = tactics.guard_pool(fight.bout, "a", me.hp, my_hp, me.hp_cap)
        my_hp = round(guarded)
        lines += said
        guarded, said = tactics.guard_pool(fight.bout, "b", foe.hp, foe_hp, foe.hp_cap)
        foe_hp = round(guarded)
        lines += said
    my_hp, foe_hp = _pool(me, my_hp), _pool(foe, foe_hp)
    before = fight.edge
    fight.edge = _clamp(fight.edge + push)
    if step is not None:
        lines += tactics.close_round(fight.bout, fight.edge - before, tt, trng)
    return Exchange(round(fight.edge - before), my_hp, foe_hp, beat, move, his, lines)


def gamble(fight: ArenaFight, rate: int, content: Content, rng: random.Random, trng: random.Random | None = None,
           lines: list[str] | None = None) -> tuple[bool, int, int, int]:
    """放手一搏（同頭目戰：分身這一回合的招不算、他不扣血）：（成了沒有, 氣勢推了多少, 你掉多少, 實際的成功率）。
    fight.bout 在時戰法照打這一回合（回氣血、援兵、焚身這類），失手時神上使有機會改成功；句子加進 lines。"""
    me, foe = fight.me, fight.foe
    tuning, battle, tt = content.config.duel, content.config.battle, content.config.tactics
    won, delta, hp, rate = duel_rules.gamble_roll(rate, me.hp_cap, me.power, me.role, tuning, battle, rng)
    out: list[str] = []
    step = None
    if fight.bout is not None and trng is not None:
        if not won:
            saved = tactics.divine_save(fight.bout.a.holders, trng)
            if saved is not None:
                won = True
                delta, hp = duel_rules.success_of(rate, me.hp_cap, me.power, tuning, battle)
                out.append(tactics.divine_line(saved))
        step = tactics.step(fight.bout, tactics.GAMBLE, fight.move, fight.edge, tt, trng, a_ratio=me.hp / max(1.0, me.hp_cap),
                            b_ratio=foe.hp / max(1.0, foe.hp_cap))
        delta += round(step.push)
        hp -= round(step.a_hp * me.hp_cap)
        guarded, said = tactics.guard_pool(fight.bout, "a", me.hp, hp, me.hp_cap)
        hp = round(guarded)
        foe_hp, said_b = tactics.guard_pool(fight.bout, "b", foe.hp, -round(step.b_hp * foe.hp_cap), foe.hp_cap)
        _pool(foe, round(foe_hp))
        out += step.lines + said + said_b
    hp = _pool(me, hp)
    before = fight.edge
    fight.edge = _clamp(fight.edge + delta)
    if step is not None:
        out += tactics.close_round(fight.bout, fight.edge - before, tt, trng)
    if lines is not None:
        lines += out
    return won, round(fight.edge - before), hp, rate


def verdict(fight: ArenaFight, tuning: DuelTuning) -> str | None:
    """分出勝負沒有（挑的人的角度，同奪璽單挑）：你的池子見底或氣勢到底落敗；他的池子見底大勝；氣勢到頂提前大勝（寫大勝）；
    打滿看氣勢。還沒是 None。"""
    if fight.me.hp <= 0 or fight.edge <= tuning.early_lose:
        return "落敗"
    if fight.foe.hp <= 0 or fight.edge >= tuning.early_win:
        return "大勝"
    return duel_rules.verdict_at(fight.edge, fight.me.hp, fight.round, fight.rounds, tuning)


def defender_tier(tier: str, edge: float, tuning: DuelTuning) -> str:
    """守的人那一邊的結果（戰報那一格）：挑的人落敗時照收場的氣勢分大勝、險勝（同奪璽單挑的 side_tier）。"""
    if tier == "落敗":
        return "大勝" if 100 - edge >= tuning.big else "險勝"
    return FLIP[tier]


def note_result(entry: ArenaEntry, score: float) -> None:
    """記一場的戰績與連勝（挑、守都走這裡）。"""
    if score >= 1:
        entry.wins += 1
        entry.streak += 1
        entry.best_streak = max(entry.best_streak, entry.streak)
    elif score > 0:
        entry.draws += 1
        entry.streak = 0
    else:
        entry.losses += 1
        entry.streak = 0


def scene_text(fight: ArenaFight) -> str:
    return (f"第 {fight.round + 1}／{fight.rounds} 回合，{duel_rules.edge_words(fight.edge)}。"
            f"你的氣血 {fight.me.hp:.0f}／{fight.me.hp_cap:.0f}，他 {fight.foe.hp:.0f}／{fight.foe.hp_cap:.0f}。{fight.tell}")


def scene(fight: ArenaFight) -> duel_rules.Scene:
    """assess_gamble 讀的 title 與 text。"""
    return duel_rules.Scene(f"擂台・{fight.foe.name}的分身", scene_text(fight))


def close_season(world: WorldState, cfg: ArenaTuning) -> list[str]:
    """收季那一刻（world.end_season）：前三名、打過至少一場的記名次（補獎勵看它），回江湖史的句子（前三名、本季擂主）；
    沒人上榜是空的。只排一次。"""
    if world.arena_closed:
        return []
    world.arena_closed = True
    top = [e for e in ladder(world) if e.bouts][:len(cfg.prizes)]
    for i, e in enumerate(top, 1):
        e.place = i
    if not top:
        return []
    return [SEASON_TOP.format(names="、".join(f"{e.name}（第 {i} 名）" for i, e in enumerate(top, 1))),
            CHAMPION.format(name=top[0].name)]
