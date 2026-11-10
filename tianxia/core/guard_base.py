"""親衛隊長「別人讀」的那一點（親衛隊長第三批；Joy 2026-11-09「好」：開核心唯讀掛鉤〔親衛哪一路、哪檔心性〕，各處套 Config.guard，先合時數字全 0）。
跟 seal_base、bounty_base 同一型：只讀 PlayerState.guard 與 Config.guard，不 import 包（親衛隊長包 features/guard 寫）。

- of(state)：投效了的那一位（GuardBook）；還沒投效、沒有是 None。
- band(content, qing)：心性那一檔（照 Config.guard.bands；包的 rules.band 同一條）。
- perk(state, content, key)：這一位此刻給本人的加成。開關關著、沒有投效、留在住處（along 關著）都是 0；
  否則 = Config.guard.perks[出路][key] + Config.guard.band_perks[心性][key]（沒寫的是 0）。原位問一次、照自己的單位夾一次：

  鍵              出路      原位                                                     單位
  big_fight       將軍      core/combat.fight_with：大場面判讀的優勢                    百分點（照舊夾在 ±big_fight_swing）
  ambush          謀士      stamina_plays 包 ambush_actions：伏兵的威力                 倍數加成（×(1+值)）
  bounty_pct      遊俠      bounties 包 rules._complete：懸賞交差的賞銀                 比例（×(1+值)，四捨五入；0 不動）
  forge_points    鐵匠      smithy 包 smithing.forge_odds：這一爐的造化分                點（0 不加這一項）
  stamina_day     農夫      guard 包自己 on_day：每天回幾點體力                          整數
  tavern_asks     乞丐      tavern 包 rules.asks_left：一天多問酒家幾次                   整數
  raid            殺手      peers 包 raid_actions.raid：截殺時本人的威力                  倍數加成（×(1+值)）
  fight_pp        弓箭手    team._fight：每一場單次判定先放一箭                           百分點（換成判定差距的平移；0 不動）
  toll_cut        醫者      team.take_encounter_toll 本人那一份：少扣幾成氣血              成數（併進化勁＋防具，照舊夾 total_cap）
  explore_legend  斥候      explore 包 explore_base：探索撿破境丹的門檻                   倍數加成（×(1+值)）
  dodge           恩深、敬重 team.dodge_chance：落敗閃成僵持（band_perks）                 機會（加在身法上，照舊夾 0～1）
"""
from __future__ import annotations

from ..models import Content
from ..state import GameState, GuardBook


def of(state: GameState) -> GuardBook | None:
    b = state.player.guard
    return b if b is not None and b.stage == "sworn" and b.path else None


def band(content: Content, qing: int) -> str:
    t = content.config.guard
    for floor, name in t.bands:
        if qing >= floor:
            return name
    return t.hate_band


def perk(state: GameState, content: Content, key: str) -> float:
    t = content.config.guard
    b = of(state) if t.enabled else None
    if b is None or not b.along:
        return 0.0
    return float(t.perks.get(b.path, {}).get(key, 0.0)) + float(t.band_perks.get(band(content, b.qing), {}).get(key, 0.0))
