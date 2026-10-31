"""單人頭目戰（Joy 2026-10-10：「多加一些特殊事件，有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）。

在有頭目的地點探索時可能遇上（content/duels.json，DuelBoss）。一場 3～5 回合：每回合你出決戰的三招之一（固守剋強攻、強攻剋奇襲、
奇襲剋固守）或放手一搏（20 字自訂行動：模型在行動鎖外只評成功率、寫成敗兩版劇情，擲骰與推進、損耗全由這裡算）；他也出一招，
回合開始時你看得到他的架勢（有幾成是虛招，DuelTuning.tell_truth）。兩邊爭一條氣勢，你用自己的氣血池（開打時的氣血）。
份量、職位、放手一搏的實力倍數與軍師、參謀照決戰的規則（battle_instance）。數字都在 Config.duel（DuelTuning）。

這個模組只算數字與句子、改 DuelState；遇上、收場（獎勵、戰報、扣回本人的氣血）在 Game（engine.py）。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from . import battle_instance, calendar, prologue, tactics
from .models import BEATS, MOVES, BattleTuning, Content, DuelBoss, DuelFoe, DuelTuning
from .state import DuelState, GameState

# 他出招之前你看到的架勢（每一招兩句，挑一句）。文字待內容方改
TELLS: dict[str, tuple[str, ...]] = {
    "強攻": ("他沉肩墜肘，腳下一蹬，像是要硬衝過來。", "他把兵刃高高舉起，眼裡全是殺氣。"),
    "固守": ("他退了半步，門戶守得嚴嚴實實。", "他氣息一沉，像一塊石頭似的等你上門。"),
    "奇襲": ("他眼珠亂轉，腳下悄悄往你側面繞。", "他身形一晃，看不出下一步要從哪裡來。"),
}
COUNTER_WORDS = {1: "你這一招正剋住他", -1: "他這一招正剋住你", 0: "兩邊招式相當"}


def season_key(state: GameState, boss_id: str) -> str:
    return f"{state.player.season_number}:{boss_id}"


def week_key(state: GameState, content: Content, boss_id: str) -> str:
    """這一隻這一週（季曆週）遇上幾次的帳（正式季整合 2.5：21 天季每週 per_boss_week 次）。"""
    week = calendar.point(state.world.time, content, state.world).week
    return f"{state.player.season_number}:w{week}:{boss_id}"


def used_up(state: GameState, content: Content, boss_id: str) -> bool:
    """這一隻的次數用完了沒：per_boss_week 設了（21 天季）照這一週算，否則照這一季的 per_boss_season。"""
    tuning, tally = content.config.duel, state.player.duel_tally
    if tuning.per_boss_week:
        return tally.get(week_key(state, content, boss_id), 0) >= tuning.per_boss_week
    return tally.get(season_key(state, boss_id), 0) >= tuning.per_boss_season


def cooldown_left(state: GameState, tuning: DuelTuning) -> float:
    """離冷卻結束還有幾世界秒（不在冷卻是 0）。"""
    last = state.player.duel_last
    if not cooling(state, tuning):
        return 0.0
    return tuning.cooldown_seconds - (state.world.time - last[1])


def cooling(state: GameState, tuning: DuelTuning) -> bool:
    """上一場頭目戰開打到現在還沒過 cooldown_seconds（同一季的世界秒；換了季就不算）。"""
    last = state.player.duel_last
    if len(last) != 2 or int(last[0]) != state.player.season_number:
        return False
    return 0 <= state.world.time - last[1] < tuning.cooldown_seconds


def available(state: GameState, content: Content) -> DuelBoss | None:
    """此刻在這裡遇得上的頭目（照 id 排第一個）：不在序章、沒有正在打的、不在冷卻、這一隻的次數還沒用完（used_up）。"""
    p, tuning = state.player, content.config.duel
    if p.duel is not None or prologue.active(state, content) or cooling(state, tuning):
        return None
    for boss in here(state, content):
        if not used_up(state, content, boss.id):
            return boss
    return None


def here(state: GameState, content: Content) -> list[DuelBoss]:
    """站在這裡的頭目（照 id 排），不管冷卻與次數。"""
    return [b for b in sorted(content.duels.values(), key=lambda b: b.id) if state.player.location in b.locations]


def foe_index(boss: DuelBoss, faction: str | None) -> int:
    """照玩家的陣營挑面貌：第一個不是自己人的（散人就是第一個）。載入時檢查過每個陣營都挑得到。"""
    return next((i for i, foe in enumerate(boss.foes) if faction is None or foe.side != faction), 0)


def foe_of(content: Content, duel: DuelState) -> tuple[DuelBoss, DuelFoe]:
    boss = content.duels[duel.boss]
    return boss, boss.foes[duel.foe]


def roll_next(duel: DuelState, foe: DuelFoe, tuning: DuelTuning, rng: random.Random) -> None:
    """擲他下一回合的招與你看到的架勢：招照他的偏好（沒寫的當 1）；架勢 tell_truth 的機會照實，其餘是另一招的架勢（虛招）。
    你看穿了、或他亂神（本命戰法）時架勢一定是真的（照樣擲，亂數順序不變）。"""
    weights = [foe.moves.get(m, 1.0) for m in MOVES]
    duel.move = rng.choices(MOVES, weights=weights)[0]
    true = rng.random() < tuning.tell_truth or tactics.locks(duel.bout).sees
    shown = duel.move if true else rng.choice([m for m in MOVES if m != duel.move])
    duel.tell = rng.choice(TELLS[shown])


def foe_difficulty(duel: DuelState, boss: DuelBoss) -> float:
    """這一場他的難度：開打時快照的（江湖水漲浮上來的，rise.duel）；舊存檔沒有快照照內容寫的。"""
    return boss.difficulty if duel.difficulty is None else duel.difficulty


def foe_strength(battle: BattleTuning, tuning: DuelTuning, boss: DuelBoss, difficulty: float | None = None) -> float:
    """他的份量：照決戰的實力算他的難度（difficulty 給了就用它，沒給照內容寫的），乘適性的基準（foe_fit）。"""
    return battle_instance.strength(battle, boss.difficulty if difficulty is None else difficulty) * tuning.foe_fit


def counter(mine: str, his: str) -> int:
    """剋：你剋他 +1、他剋你 −1、同招或不相干 0。"""
    if BEATS[mine] == his:
        return 1
    if BEATS[his] == mine:
        return -1
    return 0


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


def push_of(
    mine: float, theirs: float, beat: int, role: str, tuning: DuelTuning, battle: BattleTuning, luck: float, foe_role: str = "",
) -> int:
    """一招的推力（往「我」算）：push_base ×（2 × 我 ÷ 兩邊 − 1）＋ counter_push × 剋 ＋ 運氣。我被剋而且我是參謀、或我剋人而對方是
    參謀時，剋的那一截減半（role_counter_relief）。luck 是呼叫端擲好的（頭目戰照舊用 Game.rng，奪璽單挑用 seal.dice）。"""
    ratio = mine / (mine + theirs) if mine + theirs > 0 else 0.5
    relief = 1 - battle.role_counter_relief
    weight = beat * relief if (beat < 0 and role == "lore") or (beat > 0 and foe_role == "lore") else beat
    return round(tuning.push_base * (2 * ratio - 1) + tuning.counter_push * weight + luck)


def harm_of(hp_cap: float, mine: float, theirs: float, beat: int, tuning: DuelTuning) -> int:
    """我這一招挨的打（還沒跟剩下的池子取小）：上限 × hit × 剋制倍數（被剋 hit_countered、剋人 hit_countering）× √(對方 ÷ 我)（夾住）。"""
    harm = tuning.hit_countered if beat < 0 else tuning.hit_countering if beat > 0 else 1.0
    scale = max(0.5, min(tuning.hit_scale_max, (theirs / mine) ** 0.5)) if mine > 0 else tuning.hit_scale_max
    return round(hp_cap * tuning.hit * harm * scale)


def gamble_roll(
    rate: int, hp_cap: float, power: float, role: str, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
) -> tuple[bool, int, int, int]:
    """放手一搏擲一次：（成了沒有, 推力〔還沒夾〕, 扣多少池子〔還沒跟剩下的取小〕, 實際的成功率）。軍師 +role_gamble_rate；
    成了乘實力倍數，沒成的不乘。亂數取一次。"""
    rate = max(0, min(100, rate + (battle.role_gamble_rate if role == "wis" else 0)))
    risk = 100 - rate
    if rng.random() * 100 < rate:
        return True, *success_of(rate, hp_cap, power, tuning, battle), rate
    delta = -min(round(tuning.fail_cap), round(risk * tuning.fail_per_risk))
    return False, delta, round(hp_cap * (tuning.fail_hp_base + risk * tuning.fail_hp_per_risk)), rate


def success_of(rate: int, hp_cap: float, power: float, tuning: DuelTuning, battle: BattleTuning) -> tuple[int, int]:
    """放手一搏成了的（推力〔還沒夾〕, 扣多少池子）：照風險、乘實力倍數（神上使把失手改成功也照這個算）。"""
    might = battle_instance.strength(battle, power) / battle.gamble_strength_ref
    might = max(battle.gamble_strength_min, min(battle.gamble_strength_max, might))
    return max(1, round((tuning.gamble_base + (100 - rate) * tuning.gamble_per_risk) * might)), round(hp_cap * tuning.success_hp)


def verdict_at(edge: float, hp: float, round_: int, rounds: int, tuning: DuelTuning) -> str | None:
    """verdict 的本體：池子見底或氣勢到 early_lose 以下提前落敗、到 early_win 以上提前大勝；打滿 rounds 回合看氣勢。還沒是 None。"""
    if hp <= 0 or edge <= tuning.early_lose:
        return "落敗"
    if edge >= tuning.early_win:
        return "大勝"
    if round_ < rounds:
        return None
    if edge >= tuning.big:
        return "大勝"
    if edge >= tuning.win:
        return "險勝"
    return "僵持" if edge > tuning.draw else "落敗"


class Exchange(NamedTuple):
    """出一招的結果：氣勢推了多少、你掉多少氣血（本命戰法回的算負的）、剋、兩邊實際出的招（定身是 None）、戰法的句子。"""

    delta: int
    hp: int
    beat: int
    mine: str | None
    his: str | None
    lines: list[str]


def exchange(
    duel: DuelState, boss: DuelBoss, move: str, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
    tactic: tactics.TacticTuning | None = None, trng: random.Random | None = None,
) -> tuple[int, int, int]:
    """出一招：（氣勢推了多少, 你掉多少氣血, 剋）。見 exchange_full。"""
    out = exchange_full(duel, boss, move, tuning, battle, rng, tactic, trng)
    return out.delta, out.hp, out.beat


def exchange_full(
    duel: DuelState, boss: DuelBoss, move: str, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
    tactic: tactics.TacticTuning | None = None, trng: random.Random | None = None,
) -> Exchange:
    """出一招。改 duel.edge、duel.hp。參謀被剋時吃虧少一截（同決戰）。推力與挨的打照 push_of、harm_of（奪璽單挑共用）；
    運氣照舊在這裡用 rng 擲一次。duel.bout 在（你帶著本命戰法）時先照戰法打這一回合（tactics.step，亂數是 trng，不碰 rng）：
    招可能被定身、失神、卸勁改掉，剋照無隙改，氣勢多推戰法那一份，他沒打到你的回合你不掉血，戰法回的、焚身這類照池子算
    （他沒有池子，扣他的換成氣勢）。"""
    step = None
    his = duel.move
    if duel.bout is not None and tactic is not None and trng is not None:
        step = tactics.step(duel.bout, move, his, duel.edge, tactic, trng, a_ratio=duel.hp / max(1.0, duel.hp_cap), b_auto=True)
        move, his = step.a_move, step.b_move
    mine = duel.scores.get(move or "", 0.0) or battle_instance.strength(battle, duel.power) * tuning.foe_fit
    theirs = foe_strength(battle, tuning, boss, foe_difficulty(duel, boss))
    beat = step.beat if step is not None else counter(move, his)
    luck = rng.uniform(-tuning.luck, tuning.luck) * tactics.luck_scale(duel.bout if step is not None else None)
    delta = push_of(mine, theirs, beat, duel.role, tuning, battle, luck)
    delta = round(tactics.scale_push(delta, step))
    hp = min(duel.hp, harm_of(duel.hp_cap, mine, theirs, beat, tuning))
    lines: list[str] = []
    if step is not None:
        delta += round(step.push + tactics.pool_push(step.b_hp, tactic))
        hp = round(hp * (1 - step.a_cut)) if step.a_hit else 0
        hp -= round(step.a_hp * duel.hp_cap)
        lines = list(step.lines)
        guarded, said = tactics.guard_pool(duel.bout, "a", duel.hp, hp, duel.hp_cap)
        hp = round(guarded)
        lines += said
        hp = min(duel.hp, hp) if hp > 0 else max(-(duel.hp_cap - duel.hp), hp)
    before = duel.edge
    duel.edge = _clamp(duel.edge + delta)
    duel.hp -= hp
    if step is not None:
        lines = lines + tactics.close_round(duel.bout, duel.edge - before, tactic, trng)
    return Exchange(round(duel.edge - before), round(hp), beat, move, his, lines)  # 池子見底時 hp 是剩的那一截（小數）


def gamble(
    duel: DuelState, rate: int, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
    tactic: tactics.TacticTuning | None = None, trng: random.Random | None = None, lines: list[str] | None = None,
) -> tuple[bool, int, int, int]:
    """放手一搏：（成了沒有, 氣勢推了多少, 你掉多少氣血, 實際的成功率）。成功率是模型評的再加軍師的（夾在 0～100）；
    成了的推進乘實力倍數（同決戰），沒成的不乘。這一回合他的招不算（你搶了先手，或自己栽了）。擲骰照 gamble_roll（奪璽單挑共用）。
    duel.bout 在時戰法照打這一回合（只剩回氣血、援兵、焚身這類），失手時神上使有機會改成功；戰法的句子加進 lines。"""
    won, delta, hp, rate = gamble_roll(rate, duel.hp_cap, duel.power, duel.role, tuning, battle, rng)
    extra = 0.0
    if duel.bout is not None and tactic is not None and trng is not None:
        if not won:
            saved = tactics.divine_save(duel.bout.a.holders, trng)
            if saved is not None:
                won = True
                delta, hp = success_of(rate, duel.hp_cap, duel.power, tuning, battle)
                if lines is not None:
                    lines.append(tactics.divine_line(saved))
        step = tactics.step(duel.bout, tactics.GAMBLE, duel.move, duel.edge, tactic, trng, a_ratio=duel.hp / max(1.0, duel.hp_cap))
        extra = step.push + tactics.pool_push(step.b_hp, tactic)
        hp -= round(step.a_hp * duel.hp_cap)
        guarded, said = tactics.guard_pool(duel.bout, "a", duel.hp, hp, duel.hp_cap)
        hp = round(guarded)
        if lines is not None:
            lines += step.lines + said
    hp = min(duel.hp, hp) if hp > 0 else max(-(duel.hp_cap - duel.hp), hp)
    before = duel.edge
    duel.edge = _clamp(duel.edge + delta + round(extra))
    duel.hp -= hp
    if duel.bout is not None and tactic is not None and trng is not None:
        more = tactics.close_round(duel.bout, duel.edge - before, tactic, trng)
        if lines is not None:
            lines += more
    return won, round(duel.edge - before), round(hp), rate


def verdict(duel: DuelState, boss: DuelBoss, tuning: DuelTuning) -> str | None:
    """打完這一回合分出勝負沒有：池子見底或氣勢到 early_lose 以下提前落敗、到 early_win 以上提前大勝；打滿回合看氣勢。還沒是 None。"""
    return verdict_at(duel.edge, duel.hp, duel.round, boss.rounds, tuning)


def shown_move(duel: DuelState) -> str | None:
    """你看到的架勢是哪一招的（不一定是他真的要出的）。"""
    return next((m for m, tells in TELLS.items() if duel.tell in tells), None)


def answer_to(duel: DuelState) -> str | None:
    """剋得住你看到的架勢的那一招（假人照它出招：真人也是看架勢出招）。"""
    shown = shown_move(duel)
    return next((m for m in MOVES if BEATS[m] == shown), None) if shown else None


def move_label(move: str) -> str:
    """選單上的一招：寫它剋哪一招（「固守（剋強攻）」）。"""
    return f"{move}（剋{BEATS[move]}）"


def edge_words(edge: float, viewer: str = "你") -> str:
    """氣勢的一句話（場景用）。viewer 是句子裡的那個人（奪璽單挑給圍觀的人看時寫挑戰者的名號）；頭目戰不傳。"""
    if edge >= 75:
        return f"{viewer}大佔上風"
    if edge >= 58:
        return f"{viewer}略佔上風"
    if edge > 42:
        return "兩邊僵持不下"
    if edge > 25:
        return f"{viewer}落了下風"
    return f"{viewer}被壓著打"


# ── 放手一搏的情境（給模型評成功率、寫成敗兩版劇情：battle_instance.assess_gamble）──────────

SETTING = "江湖上一對一單打獨鬥的"
PLACE = "打鬥"
# 鎖外評好的單子跟現在對不上（M-05，同奪璽 seal_duel.GONE／RESEND）：回這兩句，不重評、不套用
STALE = "這一回合已經結算了，下一回合再出手。"
RESEND = "這一手跟剛才送出的對不上（是不是開了兩個分頁？），請再送一次。"


class Scene(NamedTuple):
    """assess_gamble 只讀 title 與 text：決戰傳那一幕，頭目戰傳這個。"""

    title: str
    text: str


def scene(content: Content, duel: DuelState) -> Scene:
    boss, foe = foe_of(content, duel)
    return Scene(f"{foe.title}{foe.name}", f"{foe.intro}（第 {duel.round + 1}／{boss.rounds} 回合，{edge_words(duel.edge)}）{duel.tell}")
