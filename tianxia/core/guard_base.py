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

第四批（Joy 2026-11-10「全部做完一起上」）：別人看得見他。
- card_line(state, content)：名帖、玩家卡上那一行「親衛隊長小明（將軍）」（peers 包 mingtie.earned 讀）；開關關著、沒投效是空的。
- raid_lines(state, content, rival_state, outcome)：截殺那一場戰報裡他的那一句（peers 包 raid_actions.raid_record 讀）：
  自己帶在身邊的照心性說一句，對手帶著的也寫一句（兩邊各看到各自的）。outcome 是 won／lost／even。
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


def _along(state: GameState, content: Content) -> GuardBook | None:
    b = of(state) if content.config.guard.enabled else None
    return b if b is not None and b.along else None


def card_line(state: GameState, content: Content) -> str:
    b = of(state) if content.config.guard.enabled else None
    return f"親衛隊長{b.name}（{b.path}）" if b is not None and b.name else ""  # 設計稿第六節「親衛隊長 小明（將軍）」；待 joy 潤


# 截殺那一場他的那一句（待 joy 潤）：恩深、敬重的拚命，淡然的盡本分，怨懟、恨極的袖手
RAID_OWN = {
    "won": {"恩深": "{name}護在你身側，替你封住了退路。", "敬重": "{name}在一旁掠陣，對手幾次想走都被{pron}攔回來。",
            "淡然": "{name}在一旁看著，等你收了手才走過來。", "怨懟": "{name}站得遠遠的，像是在看別人的事。", "恨極": "{name}在一旁看完，什麼也沒說。"},
    "lost": {"恩深": "{name}搶上來架開對手，硬把你拖了出來。", "敬重": "{name}擋在你前面斷後，你才脫得了身。",
             "淡然": "{name}拉了你一把，兩人一起退開。", "怨懟": "{name}沒有上前，看著你丟下銀兩。", "恨極": "{name}在一旁看著你輸，嘴角動了一下。"},
    "even": {"恩深": "{name}一直守在你背後，對手始終繞不過去。", "敬重": "{name}在一旁按著兵器，對手不敢戀戰。",
             "淡然": "{name}在一旁等著，沒有插手。", "怨懟": "{name}抱著手看，沒有插手。", "恨極": "{name}抱著手看，沒有插手。"},
}
RAID_RIVAL = "{rival}身邊跟著{gname}，一路盯著你。"  # {gname}＝card_line  # 待 joy 潤


def _pron(b: GuardBook) -> str:
    return "她" if b.sex == "女" else "他"


def raid_lines(state: GameState, content: Content, rival_state: GameState | None, outcome: str) -> list[str]:
    out: list[str] = []
    own = _along(state, content)
    if own is not None:
        pool = RAID_OWN.get(outcome, RAID_OWN["even"])
        out.append(pool.get(band(content, own.qing), pool["淡然"]).replace("{name}", own.name).replace("{pron}", _pron(own)))
    theirs = _along(rival_state, content) if rival_state is not None else None
    if theirs is not None:
        out.append(RAID_RIVAL.replace("{rival}", rival_state.player.name).replace("{gname}", card_line(rival_state, content)))
    return out
