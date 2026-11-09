"""單人頭目戰的規則（全部拆包第 12 批從 tianxia/duel.py 搬進單挑包）。Joy 2026-10-10：「多加一些特殊事件，有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）。

在有頭目的地點探索時可能遇上（content/duels.json，DuelBoss）。一場 3～5 回合：每回合你出決戰的三招之一（固守剋強攻、強攻剋奇襲、
奇襲剋固守）或放手一搏（20 字自訂行動：模型在行動鎖外只評成功率、寫成敗兩版劇情，擲骰與推進、損耗全由這裡算）；他也出一招，
回合開始時你看得到他的架勢（有幾成是虛招，DuelTuning.tell_truth）。兩邊爭一條氣勢，你用自己的氣血池（開打時的氣血）。
份量、職位、放手一搏的實力倍數與軍師、參謀照決戰的規則（battle_instance）。數字都在 Config.duel（DuelTuning）。

這個模組只算數字與句子、改 DuelState；遇上、收場（獎勵、戰報、扣回本人的氣血）在 duel_actions.py（Game 留一行委派）。
頭目戰、擂台、奪璽單挑共用的回合引擎（剋、推力、挨打、防具、放手一搏擲一次、勝負、架勢、氣勢的字、選單上的一招、Scene）在核心
tianxia/core/duel_base.py，這裡 re-export 同一批函式物件；鎖外三段式的單子 DuelTextRequest、輸入框底下那一句 DUEL_GAMBLE_NOTE 原本寫在 engine.py。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from pydantic import BaseModel

from tianxia import calendar, prologue, tactics
from tianxia.core import battle_base as battle_instance
from tianxia.core.duel_base import (  # noqa: F401  單挑底層進了核心（全部拆包第 12 批）：同一批函式物件，duel.push_of 這些照舊拿得到
    TELLS, Scene, blow_taken, counter, edge_words, gamble_roll, harm_of, move_label, push_of, success_of, verdict_at,
)
from tianxia.models import BEATS, MOVES, BattleTuning, Content, DuelBoss, DuelFoe, DuelTuning
from tianxia.state import DuelState, GameState

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


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


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
    tactic: tactics.TacticTuning | None = None, trng: random.Random | None = None, cut_cap: float = 1.0,
) -> tuple[int, int, int]:
    """出一招：（氣勢推了多少, 你掉多少氣血, 剋）。見 exchange_full。"""
    out = exchange_full(duel, boss, move, tuning, battle, rng, tactic, trng, cut_cap)
    return out.delta, out.hp, out.beat


def exchange_full(
    duel: DuelState, boss: DuelBoss, move: str, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
    tactic: tactics.TacticTuning | None = None, trng: random.Random | None = None, cut_cap: float = 1.0,
) -> Exchange:
    """出一招。改 duel.edge、duel.hp。參謀被剋時吃虧少一截（同決戰）。推力與挨的打照 push_of、harm_of（奪璽單挑共用）；
    運氣照舊在這裡用 rng 擲一次。duel.bout 在（你帶著本命戰法）時先照戰法打這一回合（tactics.step，亂數是 trng，不碰 rng）：
    招可能被定身、失神、卸勁改掉，剋照無隙改，氣勢多推戰法那一份，他沒打到你的回合你不掉血，戰法回的、焚身這類照池子算
    （他沒有池子，扣他的換成氣勢）。
    頭目戰吃防具（鐵匠鋪與合成流程 3.9）：他打中你的那一下乘過 duel.cut（開打那一刻抄的防具減損）與戰法的化勁（blow_taken），
    合計夾在 cut_cap（Config.armor.total_cap；呼叫端傳，沒傳不夾）；放手一搏失手與戰法自扣（焚身這類）不經過這裡。內傷收場時照乘過之後
    掉的池子算（Game._duel_finish）。頭目沒有防具。cut 是 0（沒穿、防具關著、舊存檔）時一個字不變。"""
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
    harm = harm_of(duel.hp_cap, mine, theirs, beat, tuning)
    if duel.cut > 0:  # 穿了防具：打中你的這一下連同戰法的化勁一起乘（blow_taken）；沒穿照舊
        harm = blow_taken(harm, duel.cut, step.a_cut if step is not None else 0.0, cut_cap)
    hp = min(duel.hp, harm)
    lines: list[str] = []
    if step is not None:
        delta += round(step.push + tactics.pool_push(step.b_hp, tactic))
        if not step.a_hit:
            hp = 0
        elif duel.cut <= 0:  # 穿了防具的，化勁已經跟防具一起乘在 harm 裡了
            hp = round(hp * (1 - step.a_cut))
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


# ── 放手一搏的情境（給模型評成功率、寫成敗兩版劇情：battle_instance.assess_gamble）──────────

SETTING = "江湖上一對一單打獨鬥的"
PLACE = "打鬥"
# 鎖外評好的單子跟現在對不上（M-05，同奪璽 seal_duel.GONE／RESEND）：回這兩句，不重評、不套用
STALE = "這一回合已經結算了，下一回合再出手。"
RESEND = "這一手跟剛才送出的對不上（是不是開了兩個分頁？），請再送一次。"


def scene(content: Content, duel: DuelState) -> Scene:
    boss, foe = foe_of(content, duel)
    return Scene(f"{foe.title}{foe.name}", f"{foe.intro}（第 {duel.round + 1}／{boss.rounds} 回合，{edge_words(duel.edge)}）{duel.tell}")


class DuelTextRequest(BaseModel):
    """頭目戰放手一搏鎖外評估的單子（server.duel_text 的 A 段拿到、B 段送模型、C 段交回 duel_gamble 重驗：同一隻、同一回合、同一句才用）。"""
    boss: str
    round: int
    text: str
    name: str
    faction_name: str
    title: str
    scene: str
    sex: str = "男"  # 性別（gender）：模型寫劇情時的稱呼
    # 擂台（arena_rules）也走這張單子：boss 寫「arena:場次」，多帶對手那一行與擂台的場合（assess_gamble 的 target、setting、place）；
    # 頭目戰空著，server.duel_text 照舊用 duel.SETTING、duel.PLACE
    target: str = ""
    setting: str = ""
    place: str = ""


DUEL_GAMBLE_NOTE = "寫得越險，成了越能扭轉局面；失手時氣勢倒退，重傷的是你自己。這一回合他的招不算。"  # 頭目戰、擂台的輸入框底下那一句（Game.DUEL_GAMBLE_NOTE 指到它）
