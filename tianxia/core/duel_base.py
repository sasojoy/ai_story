"""單挑底層（全部拆包第 12 批：總表 3.2 第 12 列「單挑底層移進核心」、附錄甲「duel 拆兩半，底層留核心」）。

頭目戰（單挑包）、擂台（單挑包）、奪璽單挑（tianxia/seal_duel.py，之後進玉璽包）三種一對一的打法共用的回合引擎：剋、一招的推力、
挨的打、乘過防具之後挨多少、放手一搏擲一次、勝負、架勢的句子、氣勢的一句話、選單上的一招、給模型評放手一搏的場景。
只算數字與句子，不碰存檔、不碰 Game。原本寫在 tianxia/duel.py，函式照抄、名字不變；單挑包的 duel_rules（舊名 tianxia.duel）
從這裡 re-export 同一批函式物件，`from tianxia import duel` 照舊拿得到。別的包要用一律 import 這裡（包不能 import 包）。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from . import battle_base as battle_instance
from ..models import BEATS, BattleTuning, DuelTuning

# 他出招之前你看到的架勢（每一招兩句，挑一句）。文字待內容方改
TELLS: dict[str, tuple[str, ...]] = {
    "強攻": ("他沉肩墜肘，腳下一蹬，像是要硬衝過來。", "他把兵刃高高舉起，眼裡全是殺氣。"),
    "固守": ("他退了半步，門戶守得嚴嚴實實。", "他氣息一沉，像一塊石頭似的等你上門。"),
    "奇襲": ("他眼珠亂轉，腳下悄悄往你側面繞。", "他身形一晃，看不出下一步要從哪裡來。"),
}


def counter(mine: str, his: str) -> int:
    """剋：你剋他 +1、他剋你 −1、同招或不相干 0。"""
    if BEATS[mine] == his:
        return 1
    if BEATS[his] == mine:
        return -1
    return 0


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


def blow_taken(harm: int, cut: float, tactic_cut: float, cap: float) -> int:
    """對手打中你的那一下，乘過防具與化勁之後挨多少（鐵匠鋪與合成流程 3.9；頭目戰、擂台、奪璽單挑共用，harm_of 本身不動、呼叫端乘）。
    cut 是開打那一刻抄的防具減損（含耐久，DuelState／ArenaSide／SealSide 的 cut）；tactic_cut 是戰法的化勁這一回合挨的打少幾成
    （tactics.Step.a_cut／b_cut——單挑裡化勁本來就是戰法，所以快照不重複抄它）。沒有防具（cut 是 0）就是原本的 round(harm × (1 − 化勁))，
    一個字不變；有防具兩份相加、合計夾在 cap（Config.armor.total_cap），同一般的仗，但穿了防具不會比赤膊挨得多（戰法的化勁自己超過 cap 時照戰法的，FB-9031）。
    只乘「打中的那一下」：放手一搏失手扣的、戰法自扣的不經過這裡。"""
    reduced = tactic_cut if cut <= 0 else max(tactic_cut, min(cap, tactic_cut + cut))
    return round(harm * (1 - reduced))


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


def move_label(move: str) -> str:
    """選單上的一招：寫它剋哪一招（「固守（剋強攻）」）。頭目戰、擂台、奪璽單挑的選單與店面都用這一個。"""
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


class Scene(NamedTuple):
    """assess_gamble 只讀 title 與 text：決戰傳那一幕，頭目戰、擂台、奪璽單挑傳這個。"""

    title: str
    text: str
