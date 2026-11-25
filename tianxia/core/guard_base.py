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

收尾（Joy 2026-11-25「前三項還沒開工的開工來做」；設計稿第五節「酒肆：聽得到別人親衛的傳聞…只講出路與一件事，不講心性」「切磋、論武：對方的親衛在旁邊說一句」）：
- rumor_line(other, content)：酒肆打聽交情（tavern 包 rules.ties_player_lines，打聽度 3 以上）多一句他的傳聞：出路與撿到他的那一件事，不講心性。
- spar_line(rival, content, outcome)：切磋那一場，對手帶著的他在一旁說一句（peers 包 spar_actions.spar_record 讀；outcome 從看的人那一邊算）。
- discuss_line(rival, content)：論武那一場，對手帶著的他在一旁的那一句（peers 包 discuss_actions.discuss 讀）。
都看開關、投效了、帶在身邊（along）；自己的那一位不在自己的戰報裡說（截殺那一句已經有了）。
"""
from __future__ import annotations

from .. import gender
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


# ── 收尾：酒肆的傳聞、切磋論武時他在一旁（待 joy 潤）──

# 傳聞裡怎麼叫他（只講出路，不講心性）
PATH_WORD = {"將軍": "會帶兵的", "謀士": "肚裡有計的", "遊俠": "遊俠", "鐵匠": "會打鐵的", "農夫": "種地出身的",
             "乞丐": "討過飯的", "殺手": "下手極冷的", "弓箭手": "弓手", "醫者": "會看病的", "斥候": "探路的"}
# 撿到他的那一件事（content 的 openings 的 id；{him}＝主人的他／她）
OPENING_DEED = {"soldiers": "從亂兵刀下救出來的", "slaves": "從人販子的車上買下來的", "river": "從河裡撈起來的",
                "spy": "從一群要打死{pron}的村人手裡帶走的", "fever": "發著高燒，從破廟裡背出來的", "thief": "偷了{him}的錢袋，{him}反倒收留下來的"}
RUMOR = "聽說{owner}身邊那個{word}{gname}，是{him}{deed}。"  # 待 joy 潤
RUMOR_PLAIN = "聽說{owner}身邊那個{word}{gname}，是{him}當年撿回來的孩子。"  # 待 joy 潤

# 心性粗分三樣：恩深、敬重 warm；淡然 plain；怨懟、恨極 cold
_MOOD = {"恩深": "warm", "敬重": "warm", "淡然": "plain", "怨懟": "cold", "恨極": "cold"}
# 切磋那一場（outcome 從看的人那一邊：won 是你贏了他的主人）
SPAR_RIVAL = {  # 待 joy 潤
    "won": {"warm": "{owner}的親衛{gname}搶上來扶住{owner}，回頭對你說：「下回換我來領教。」",
            "plain": "{owner}的親衛{gname}在一旁看完，朝你點了點頭。",
            "cold": "{owner}的親衛{gname}看著{owner}輸了，竟輕輕笑了一聲。"},
    "lost": {"warm": "{owner}的親衛{gname}在一旁鬆了口氣，對你抱拳：「承讓了。」",
             "plain": "{owner}的親衛{gname}在一旁收起兵器，什麼也沒說。",
             "cold": "{owner}的親衛{gname}瞥了你一眼，又瞥了{owner}一眼，轉身走開。"},
    "even": {"warm": "{owner}的親衛{gname}在一旁拍手：「好！再打三十招也分不出高下。」",
             "plain": "{owner}的親衛{gname}在一旁看著，說了一句：「都沒使全力。」",
             "cold": "{owner}的親衛{gname}靠在樹下打了個呵欠。"},
}
DISCUSS_RIVAL = {  # 待 joy 潤
    "warm": "{owner}的親衛{gname}在一旁替兩人添茶，聽得入了神。",
    "plain": "{owner}的親衛{gname}守在門口，沒讓閒人進來。",
    "cold": "{owner}的親衛{gname}在一旁聽得不耐煩，先出去了。",
}


def rumor_line(other: GameState, content: Content) -> str:
    b = _along(other, content)
    if b is None or not b.name:
        return ""
    him = gender.pronoun(other)
    deed = OPENING_DEED.get(b.opening, "").replace("{pron}", _pron(b))
    word = PATH_WORD.get(b.path, b.path)
    fmt = RUMOR if deed else RUMOR_PLAIN
    return fmt.format(owner=other.player.name, word=word, gname=b.name, him=him, deed=deed.replace("{him}", him))


def _mood(content: Content, b: GuardBook) -> str:
    return _MOOD.get(band(content, b.qing), "plain")


def spar_line(rival: GameState, content: Content, outcome: str) -> str:
    b = _along(rival, content)
    if b is None or not b.name:
        return ""
    pool = SPAR_RIVAL.get(outcome, SPAR_RIVAL["even"])
    return pool[_mood(content, b)].format(owner=rival.player.name, gname=b.name)


def discuss_line(rival: GameState, content: Content) -> str:
    b = _along(rival, content)
    if b is None or not b.name:
        return ""
    return DISCUSS_RIVAL[_mood(content, b)].format(owner=rival.player.name, gname=b.name)
