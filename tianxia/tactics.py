"""一般的仗的回合與本命戰法（Joy 2026-10-15：「我沒說可以合，你這些說是武學卻更像寶物的功能」「你去看看三國志戰略版的武器跟戰法」，
決策卡選「全部改回合制」；定案 /mnt/project-files/plan/本命戰法定案.md）。

一般的仗（遊歷、出陣、探索野怪、劇情戰、挑戰大勢人物本人）照舊先擲一次單次判定（encounter.resolve_encounter，同一顆 Game.rng），
這裡把擲出來的差距攤成一回合一回合的氣勢（50 起，Config.tactics.span 換算），每一回合兩邊各出一招（強攻、奇襲、固守，同決戰與頭目戰
的剋制），本命戰法在回合裡發動：讓對手陷入某種狀態（卸勁、亂神、定身、失神……）、自己連環、無隙、借力、化影，或給對手焚身、風沙、血創。
沒有戰法時每一回合加起來剛好回到那個差距（結果、Game.rng 的順序、勝率都跟以前一模一樣）；戰法改了的氣勢在收場時換回差距，
再照原本的門檻判結果——所以戰法真的會把險勝打成大勝、把落敗撐成僵持。

狀態：
| 狀態 | 做什麼 |
|---|---|
| 卸勁 | 出不了強攻（對手被卸勁時，你的自動出招挑不會被剋的那一招） |
| 亂神 | 不能放手一搏；一般的仗裡他的招被你看穿（你一定出剋他的那一招） |
| 定身 | 這一回合出不了手 |
| 失神 | 這一回合亂出招，Config.tactics.self_hit 的機會打到自己 |
| 守一 | 不受上面四種控制 |
| 連環 | 這一回合再推一次 |
| 無隙 | 出招不會被剋 |
| 借力 | 挨強攻時把一部分還回去 |
| 化影 | 這一回合不掉氣血 |
| 焚身、風沙、血創 | 每一回合扣對手的氣血池（換成氣勢，Config.tactics.dot），可疊 |
| 霧 | 雙方都可能打空 |

只算數字與句子：誰帶著哪一門（Holder）、這一場的條件（Ctx）由 team 算好傳進來；回氣血、自扣氣血記在 Clash.hp，由 Game 照它改本人與同伴。
亂數由呼叫端給（引擎用「名號｜戰報流水號｜回合」當種子），不碰 Game.rng。只 import models。
"""
from __future__ import annotations

import random

from pydantic import BaseModel, Field

from .models import BEATS, MOVES, Content, TacticDef, TacticTuning

CONTROLS = ("卸勁", "亂神", "定身", "失神")  # 守一擋得下的
DOTS = ("焚身", "風沙", "血創")
LEAD = "〔"  # 戰法句一律以「〔戰法名〕」開頭（同功效句，battlelog.TRAIT_LEAD：網頁收著的卡片先藏起來）
TITLE = "本命戰法"
PLAYER_KEY = "player"  # 同 state.PLAYER（這裡不 import state）


class Holder(BaseModel):
    """這一場誰帶著哪一門本命戰法：本人身上練著的兩門、同伴練著的兩門。"""

    who: str  # 名字（本人寫名號、同伴寫人物名）
    key: str  # 回氣血、自扣氣血的對象：PLAYER_KEY 或同伴 id
    skill: str  # 武學 id
    figure: str | None = None  # 這門戰法是哪位人物的（仁義聚眾認關羽、張飛）
    tactic: TacticDef


class Ctx(BaseModel):
    """這一場的條件：戰法的條件與加成看它。"""

    foe: str  # 對手的名字（句子用）
    our_agility: float = 5.0
    foe_agility: float = 5.0
    night: bool = False
    mount_tier: int = 0  # 身上那匹馬的階；沒騎馬是 0
    good: int = 0
    evil: int = 0
    followers: int = 0
    foe_faction: str | None = None
    own_turf: bool = False  # 這裡此刻歸你的陣營
    hp_ratio: float = 1.0  # 本人開打時的氣血 ÷ 上限
    team: list[str] = Field(default_factory=list)  # 本人與出戰同伴的鍵（回氣血照它）


class Turn(BaseModel):
    number: int
    ours: str | None  # 你這一方出的招；None＝定身、出不了手
    theirs: str | None
    beat: int  # 你剋中 +1、被剋 −1、其他 0
    push: float  # 這一回合氣勢動了多少（往你這邊是正的）
    edge: float  # 回合結束時的氣勢
    landed: bool = True  # 對手這一回合打到你（本人掉的氣血照它分）
    lines: list[str] = Field(default_factory=list)  # 這一回合發動的戰法（〔名〕開頭）


class Clash(BaseModel):
    turns: list[Turn]
    margin: float  # 收場換回的差距（沒有戰法時就是擲出來的那一個）
    stopped: bool = False  # 提前收場
    hp: dict[str, float] = Field(default_factory=dict)  # 鍵 → 回（正）或自扣（負）氣血上限的幾成
    fired: list[str] = Field(default_factory=list)  # 發動過的戰法名（照先後，可重複）

    @property
    def shifted(self) -> bool:
        return bool(self.fired)

    def blocked_share(self) -> float:
        """打了的回合裡，對手沒打到你的比例（定身、失神打到自己、打空、化影）：本人這一場掉的氣血照它少扣。"""
        if not self.turns:
            return 0.0
        return sum(not t.landed for t in self.turns) / len(self.turns)


# ── 卡上那一句 ─────────────────────────────────────────


def value_text(key: str, value: float) -> str:
    return f"{round(value * 100, 1):g}%" if key.endswith("_pct") else f"{value:g}"


def desc_text(tactic: TacticDef) -> str:
    """說明裡的 {鍵} 換成數字；發動率另外寫在 when_text。"""
    return tactic.desc.format(**{k: value_text(k, v) for k, v in tactic.params.items()})


def when_text(tactic: TacticDef) -> str:
    """什麼時候發動、發動率：「出招・每回合 40%・蓄力 1 回合」「起手・第 1 回合必定」「乘勢・剋中對手後 45%」。"""
    rate = "必定" if tactic.rate >= 1 else f"{round(tactic.rate * 100)}%"
    span = f"前 {tactic.rounds} 回合" if tactic.rounds > 1 else "第 1 回合" if tactic.rounds == 1 else "每回合"
    if tactic.timing == "乘勢":
        text = f"剋中對手後 {rate}"
    elif tactic.timing == "心法":
        text = f"{span}一直在" if tactic.rounds else "一直在"
    elif tactic.timing == "騎戰":
        text = "騎著馬才有"
    else:
        text = f"{span}{rate}" if rate == "必定" else f"{span} {rate}"
    if tactic.prep:
        text += f"・蓄力 {tactic.prep} 回合"
    return f"{tactic.timing}・{text}"


def card_text(tactic: TacticDef) -> str:
    """功法卡、修練頁、角色卡那一段：「本命戰法〔長坂一喝〕出招・每回合 40%：一聲大喝……」。"""
    return f"{TITLE}〔{tactic.name}〕{when_text(tactic)}：{desc_text(tactic)}"


# ── 一場仗 ───────────────────────────────────────────


def counter(mine: str | None, his: str | None) -> int:
    if mine is None or his is None:
        return 0
    if BEATS[mine] == his:
        return 1
    if BEATS[his] == mine:
        return -1
    return 0


def answer_to(move: str) -> str:
    """剋這一招的那一招。"""
    return next(m for m in MOVES if BEATS[m] == move)


def best_against(options: list[str], allowed: list[str]) -> str:
    """對手只能出 options 裡的招時，你在 allowed 裡挑最不吃虧的（剋得多、被剋得少；一樣照 MOVES 的順序）。"""
    return max(allowed, key=lambda m: sum(counter(m, o) for o in options))


def base_path(margin: float, effective: float, rounds: int, tuning: TacticTuning, rng: random.Random) -> tuple[list[str], list[str], list[float]]:
    """沒有戰法時的回合：兩邊各出什麼招、每一回合氣勢動多少。剋中的回合推得多、被剋的回合推得少，加起來剛好是擲出來的差距
    （span × 差距 ÷ 對手強度）。中途的氣勢夾在 50 ± (stop − band) × 第幾回合 ÷ (回合數 − 1) 以內（最後一回合除外，懸殊的仗最後一回合一口氣推到底），
    所以沒有戰法時不會還沒打完就提前收場。"""
    whole = tuning.span * margin / max(1.0, abs(effective))
    ours = [rng.choice(MOVES) for _ in range(rounds)]
    theirs = [rng.choice(MOVES) for _ in range(rounds)]
    beats = [counter(a, b) * tuning.counter for a, b in zip(ours, theirs, strict=True)]
    wobble = [rng.uniform(-tuning.wobble, tuning.wobble) for _ in range(rounds - 1)] + [0.0]
    total_beat = sum(beats)
    marks, run = [], 0.0
    reach = tuning.stop - tuning.band
    for k in range(1, rounds + 1):
        run += beats[k - 1]
        mark = whole * k / rounds + run - total_beat * k / rounds + wobble[k - 1]
        if k == rounds:
            mark = whole
        else:  # 夾的範圍一回合一回合放寬：懸殊的仗氣勢一路往一邊壓，不會第一回合就到頂、中間幾回合不動
            cap = reach * k / (rounds - 1)
            mark = max(-cap, min(cap, mark))
        marks.append(mark)
    pushes = [marks[0]] + [marks[k] - marks[k - 1] for k in range(1, rounds)]
    return ours, theirs, pushes


class _Side(BaseModel):
    states: dict[str, int] = Field(default_factory=dict)  # 狀態 → 還剩幾回合（這一回合算在內）
    later: dict[str, int] = Field(default_factory=dict)  # 下一回合才生效的
    dots: list[tuple[str, float, int]] = Field(default_factory=list)  # （名字, 每回合扣幾成, 還剩幾回合）

    def has(self, name: str) -> bool:
        return self.states.get(name, 0) > 0

    def tick(self) -> None:
        self.states = {k: v - 1 for k, v in self.states.items() if v > 1}
        self.dots = [(n, pct, left - 1) for n, pct, left in self.dots if left > 1]
        for k, v in self.later.items():
            self.states[k] = max(self.states.get(k, 0), v)
        self.later = {}


class _Fight:
    """一場仗打到一半的樣子；KINDS 裡的每一種戰法改它。"""

    def __init__(self, holders: list[Holder], ctx: Ctx, tuning: TacticTuning, rng: random.Random):
        self.holders, self.ctx, self.t, self.rng = holders, ctx, tuning, rng
        self.us, self.foe = _Side(), _Side()
        self.round = 0
        self.edge = 50.0
        self.delta = 0.0  # 這一回合戰法改了多少氣勢
        self.strike = 0.0  # 你這一方一回合的出手（連環、推力加成照它算；同 Config.tactics.strike）
        self.lines: list[str] = []
        self.hp: dict[str, float] = {}
        self.fired: list[str] = []
        self.pending: dict[str, int] = {}  # 蓄力中的戰法 → 第幾回合出手
        self.stacks: dict[str, int] = {}
        self.chain = False
        self.know = False  # 這一回合看穿了對手的招
        self.no_guard = False
        self.flawless = False  # 無隙
        self.veiled = False  # 化影
        self.push_mod = 0.0  # 你這一回合的推力多幾成
        self.foe_cut = 0.0  # 對手這一回合的推力少幾成
        self.guard_mod = 0.0  # 出固守時推力多幾成
        self.rebound = 0.0  # 挨強攻時還回去的比例
        self.extra = 0.0  # 這一回合另外推的氣勢（援兵）

    # 共用的小動作
    def say(self, h: Holder, text: str) -> None:
        self.lines.append(f"{LEAD}{h.tactic.name}〕{h.who}{text}")
        self.fired.append(h.tactic.name)

    def heal(self, key: str, pct: float) -> None:
        self.hp[key] = self.hp.get(key, 0.0) + pct

    def put(self, side: _Side, name: str, turns: int, *, now: bool, by: Holder | None = None) -> bool:
        """給一方加一個狀態；守一擋控制（回傳 False）。now：這一回合就生效（出招、起手），否則下一回合（乘勢）。"""
        if name in CONTROLS and side.has("守一"):
            if side is self.us:
                self.lines.append(f"{LEAD}守一〕心神守住，{name}沒能沾身")
            return False
        book = side.states if now else side.later
        book[name] = max(book.get(name, 0), turns)
        return True

    def burn(self, name: str, pct: float, turns: int, stacks: int = 1) -> None:
        same = [d for d in self.foe.dots if d[0] == name]
        if len(same) >= stacks:
            self.foe.dots.remove(same[0])
        self.foe.dots.append((name, pct, turns))

    def rate(self, h: Holder) -> float:
        bonus = 0.0
        for other in self.holders:
            if other.tactic.kind == "rally" and h.figure in other.tactic.allies:
                bonus += other.tactic.params.get("boost_pct", 0.0)
        return h.tactic.rate + bonus

    def roll(self, chance: float) -> bool:
        return self.rng.random() < chance


# ── 三十六種戰法（kind → 做法）。起手、出招、騎戰在出招之前，乘勢在剋中之後，心法每回合都問 ──────


def _chase_disarm(f: _Fight, h: Holder) -> None:  # 曹操〔橫槊賦詩〕
    f.chain = True
    turns = int(h.tactic.params.get("turns", 1))
    f.put(f.foe, "卸勁", turns, now=False)
    f.say(h, f"橫槊追擊，這一回合連環，{f.ctx.foe}卸勁 {turns} 回合")


def _opening_ward(f: _Fight, h: Holder) -> None:  # 曹操〔亂世心術〕
    turns = int(h.tactic.params.get("turns", 2))
    f.put(f.us, "守一", turns, now=True)
    f.say(h, f"心如止水，守一 {turns} 回合")


def _disarm(f: _Fight, h: Holder) -> None:  # 劉備〔雙股回鋒〕
    turns = int(h.tactic.params.get("turns", 1))
    if f.put(f.foe, "卸勁", turns, now=False):
        f.say(h, f"雙劍回鋒，{f.ctx.foe}卸勁 {turns} 回合")


def _rally(f: _Fight, h: Holder) -> None:  # 劉備〔仁義聚眾〕
    pct = h.tactic.params.get("heal_pct", 0.0)
    for key in f.ctx.team:
        f.heal(key, pct)
    if f.round == 1:
        f.say(h, "振臂一呼，眾人每一回合都緩過一口氣")


def _heavy_blow(f: _Fight, h: Holder) -> None:  # 關羽〔青龍拖刀〕：蓄力一回合，下一回合出手
    f.push_mod += h.tactic.params.get("mult", 1.7) - 1
    state = "卸勁" if f.roll(0.5) else "亂神"
    turns = int(h.tactic.params.get("turns", 1))
    landed = f.put(f.foe, state, turns, now=True)
    f.say(h, "拖刀回斬，這一下推力加重" + (f"，{f.ctx.foe}{state} {turns} 回合" if landed else ""))


def _cleanse(f: _Fight, h: Holder) -> None:  # 關羽〔刮骨定神〕
    cleared = [s for s in CONTROLS if f.us.has(s)]
    for s in cleared:
        f.us.states.pop(s, None)
    f.heal(h.key, h.tactic.params.get("heal_pct", 0.0))
    f.say(h, "刮骨定神，" + (f"解了{'、'.join(cleared)}，" if cleared else "") + f"回氣血 {value_text('heal_pct', h.tactic.params.get('heal_pct', 0.0))}")


def _roar(f: _Fight, h: Holder) -> None:  # 張飛〔長坂一喝〕
    state = "定身" if f.roll(h.tactic.params.get("stun_pct", 0.3)) else "失神"
    turns = int(h.tactic.params.get("turns", 1))
    if f.put(f.foe, state, turns, now=True):
        f.say(h, f"一聲大喝，{f.ctx.foe}{state} {turns} 回合")


def _unbroken(f: _Fight, h: Holder) -> None:  # 張飛〔丈八狂瀾〕
    f.flawless = True
    f.no_guard = True
    if f.round == 1:
        f.say(h, f"蛇矛狂掃，前 {h.tactic.rounds} 回合無隙，只攻不守")


def _vanguard(f: _Fight, h: Holder) -> None:  # 孫堅〔先登斬將〕
    f.chain = True
    f.say(h, "先登陷陣，這一回合連環")


def _tiger(f: _Fight, h: Holder) -> None:  # 孫堅〔猛虎餘威〕
    p = h.tactic.params
    step = 2 if f.edge < 50 else 1
    n = min(int(p.get("stacks", 5)), f.stacks.get(h.tactic.name, 0) + step)
    f.stacks[h.tactic.name] = n
    f.push_mod += n * p.get("stack_pct", 0.0)
    if n >= int(p.get("stacks", 5)) and not f.stacks.get(h.tactic.name + "|說", 0):
        f.stacks[h.tactic.name + "|說"] = 1
        f.say(h, f"越戰越勇，餘威疊滿 {n} 層")


def _awe(f: _Fight, h: Holder) -> None:  # 袁紹〔世家威儀〕
    f.foe_cut += h.tactic.params.get("cut_pct", 0.0)
    f.say(h, f"四世三公的排場一擺，{f.ctx.foe}氣餒，這一回合推力大減")


def _waver(f: _Fight, h: Holder) -> None:  # 袁紹〔猶疑兩端〕
    p = h.tactic.params
    if f.roll(0.5):
        f.push_mod += p.get("up_pct", 0.0)
        if f.round == 1:
            f.say(h, "這一回合拿定了主意，出手極重")
    else:
        f.push_mod -= p.get("down_pct", 0.0)


def _rebound_guard(f: _Fight, h: Holder) -> None:  # 陶謙〔丹陽鐵壁〕：出固守時借力
    f.rebound += h.tactic.params.get("share_pct", 0.0)


def _veil(f: _Fight, h: Holder) -> None:  # 陶謙〔寬厚養氣〕
    p = h.tactic.params
    chance = p.get("chance_pct", 0.0) + min(p.get("good_cap_pct", 0.0), f.ctx.good // max(1, int(p.get("good_step", 20))) * p.get("per_good_pct", 0.0))
    if f.roll(chance):
        f.veiled = True
        f.say(h, "氣息綿長，化影，這一回合不掉氣血")


def _thunder(f: _Fight, h: Holder) -> None:  # 張角〔天雷符〕：蓄力一回合，下一回合落雷
    p = h.tactic.params
    hits = int(p.get("hits", 5))
    f.extra += hits * p.get("dot_pct", 0.0) * 100 * f.t.dot
    stunned = (f.foe.has("霧") or f.us.has("霧") or any(d[0] == "風沙" for d in f.foe.dots)) and any(
        f.roll(p.get("stun_pct", 0.0)) for _ in range(hits)
    )
    if stunned and f.put(f.foe, "定身", 1, now=True):
        f.say(h, f"落雷 {hits} 下，借著霧沙劈中{f.ctx.foe}，定身 1 回合")
    else:
        f.say(h, f"落雷 {hits} 下，劈得{f.ctx.foe}焦頭爛額")


def _curse(f: _Fight, h: Holder) -> None:  # 張角〔黃天咒〕
    turns = int(h.tactic.params.get("turns", 2))
    if f.put(f.foe, "亂神", turns, now=True):
        f.say(h, f"念起黃天咒，{f.ctx.foe}亂神 {turns} 回合，自己也失神 1 回合")
    else:
        f.say(h, "念起黃天咒，自己失神 1 回合")
    f.put(f.us, "失神", 1, now=False)


def _sand(f: _Fight, h: Holder) -> None:  # 張寶〔揚沙術〕
    turns = int(h.tactic.params.get("turns", 3))
    f.burn("風沙", h.tactic.params.get("dot_pct", 0.0), turns)
    f.say(h, f"揚起漫天黃沙，{f.ctx.foe}陷入風沙 {turns} 回合")


def _fog(f: _Fight, h: Holder) -> None:  # 張寶〔霧鎖山川〕
    turns = int(h.tactic.params.get("turns", 3))
    f.put(f.us, "霧", turns, now=True)
    f.put(f.foe, "霧", turns, now=True)
    one = f.ctx.our_agility > f.ctx.foe_agility
    f.say(h, f"起霧 {turns} 回合" + ("，你身法快，只有對手會打空" if one else "，雙方都可能打空"))


def _bloodrage(f: _Fight, h: Holder) -> None:  # 張梁〔人公血戰〕
    p = h.tactic.params
    lost = max(0.0, 1 - f.ctx.hp_ratio)
    more = min(p.get("cap_pct", 0.0), int(lost * 10) * p.get("per_pct", 0.0))
    f.push_mod += more
    if more and f.round == 1:
        f.say(h, "血越流越狠，推力加重")


def _oath(f: _Fight, h: Holder) -> None:  # 張梁〔黃巾血誓〕
    f.heal(h.key, -h.tactic.params.get("cost_pct", 0.0))
    f.put(f.us, "連環", 1, now=False)
    f.put(f.us, "無隙", 1, now=False)
    f.say(h, "以血立誓，下一回合連環、無隙")


def _butcher(f: _Fight, h: Holder) -> None:  # 何進〔屠刀〕
    p = h.tactic.params
    turns = int(p.get("turns", 2))
    f.burn("血創", p.get("dot_pct", 0.0), turns, stacks=int(p.get("stacks", 3)))
    f.say(h, f"一刀見血，{f.ctx.foe}血創 {turns} 回合")


def _marshal(f: _Fight, h: Holder) -> None:  # 何進〔大將軍府〕
    more = f.ctx.followers * h.tactic.params.get("per_pct", 0.0)
    f.push_mod += more
    if more and f.round == 1:
        f.say(h, f"部下 {f.ctx.followers} 人列陣，推力加重")


def _fire(f: _Fight, h: Holder) -> None:  # 皇甫嵩〔長社火攻〕：蓄力一回合，下一回合放火
    p = h.tactic.params
    turns = int(p.get("turns", 3))
    pct = p.get("dot_pct", 0.0)
    double = h.tactic.foe_faction is not None and f.ctx.foe_faction == h.tactic.foe_faction
    f.burn("焚身", pct * (p.get("faction_mult", 2.0) if double else 1.0), turns)
    f.say(h, f"火攻得手，{f.ctx.foe}焚身 {turns} 回合" + ("，黃巾營寨燒得加倍" if double else ""))


def _steady(f: _Fight, h: Holder) -> None:  # 皇甫嵩〔持重〕：氣勢落後時固守加重
    if f.edge < 50:
        f.guard_mod += h.tactic.params.get("guard_pct", 0.0)


def _surge(f: _Fight, h: Holder) -> None:  # 朱儁〔疾如潮〕
    f.chain = True
    f.say(h, "趁勢疾進，這一回合連環")


def _tide(f: _Fight, h: Holder) -> None:  # 朱儁〔潮生潮落〕
    p = h.tactic.params
    if f.round % 2:
        f.push_mod += p.get("odd_pct", 0.0)
    else:
        f.heal(h.key, p.get("heal_pct", 0.0))
    if f.round == 1:
        f.say(h, "潮起推進、潮落回氣，一回合一變")


def _foresight(f: _Fight, h: Holder) -> None:  # 盧植〔經緯〕
    f.put(f.us, "看穿", 1, now=False)
    f.say(h, "看穿了來路，下一回合出剋他的那一招")


def _ward_all(f: _Fight, h: Holder) -> None:  # 盧植〔海內儒宗〕
    f.put(f.us, "守一", max(1, h.tactic.rounds), now=True)
    if f.round == 1:
        f.say(h, f"正氣護身，前 {h.tactic.rounds} 回合自己與同伴守一")


def _cavalry(f: _Fight, h: Holder) -> None:  # 董卓〔涼州鐵蹄〕
    p = h.tactic.params
    if f.round == 1 or f.roll(p.get(f"t{max(1, min(3, f.ctx.mount_tier))}_pct", 0.0)):
        f.chain = True
        f.say(h, "鐵蹄踏陣，這一回合連環")


def _brutal(f: _Fight, h: Holder) -> None:  # 董卓〔暴虐〕
    turns = int(h.tactic.params.get("turns", 1))
    f.heal(h.key, -h.tactic.params.get("cost_pct", 0.0))
    if f.put(f.foe, "失神", turns, now=False):
        f.say(h, f"下手狠毒，{f.ctx.foe}失神 {turns} 回合")


def _night_raid(f: _Fight, h: Holder) -> None:  # 波才〔長社夜襲〕
    f.stacks["夜襲"] = 1
    f.push_mod += h.tactic.params.get("mult", 2.0) - 1
    f.say(h, "趁夜突襲，這一回合奇襲推力加倍")


def _reinforce(f: _Fight, h: Holder) -> None:  # 波才〔三十六方〕
    if f.roll(h.tactic.params.get("chance_pct", 0.0)):
        f.extra += h.tactic.params.get("strikes", 1.0) * f.strike
        f.say(h, "黃巾援兵趕到，推了一把")


def _divine(f: _Fight, h: Holder) -> None:  # 張曼成〔神上使〕：放手一搏失手時才有，一般的仗沒有放手一搏
    return


def _sacrifice(f: _Fight, h: Holder) -> None:  # 張曼成〔祭天〕：每贏一回合疊一層（在回合結束時算，見 _after）
    n = f.stacks.get(h.tactic.name, 0)
    f.push_mod += n * h.tactic.params.get("stack_pct", 0.0)


def _hold_city(f: _Fight, h: Holder) -> None:  # 趙弘〔死守宛城〕
    f.guard_mod += h.tactic.params.get("guard_pct", 0.0)
    f.rebound += h.tactic.params.get("share_pct", 0.0)


def _gatekeep(f: _Fight, h: Holder) -> None:  # 趙弘〔把關〕
    chance = h.tactic.params.get("turf_pct" if f.ctx.own_turf else "chance_pct", 0.0)
    if f.roll(chance) and f.put(f.foe, "卸勁", 1, now=True):
        f.say(h, f"把住關口，{f.ctx.foe}這一回合卸勁")


KINDS = {
    "chase_disarm": _chase_disarm, "opening_ward": _opening_ward, "disarm": _disarm, "rally": _rally,
    "heavy_blow": _heavy_blow, "cleanse": _cleanse, "roar": _roar, "unbroken": _unbroken, "vanguard": _vanguard,
    "tiger": _tiger, "awe": _awe, "waver": _waver, "rebound_guard": _rebound_guard, "veil": _veil, "thunder": _thunder,
    "curse": _curse, "sand": _sand, "fog": _fog, "bloodrage": _bloodrage, "oath": _oath, "butcher": _butcher,
    "marshal": _marshal, "fire": _fire, "steady": _steady, "surge": _surge, "tide": _tide, "foresight": _foresight,
    "ward_all": _ward_all, "cavalry": _cavalry, "brutal": _brutal, "night_raid": _night_raid, "reinforce": _reinforce,
    "divine": _divine, "sacrifice": _sacrifice, "hold_city": _hold_city, "gatekeep": _gatekeep,
}
GUARD_KINDS = ("rebound_guard", "hold_city", "steady")  # 出固守才起作用的：自動出招多出固守


def _in_span(h: Holder, round_: int) -> bool:
    return h.tactic.rounds == 0 or round_ <= h.tactic.rounds


def _busy(f: _Fight, h: Holder) -> bool:
    """它要給的狀態對手身上還在：這一回合不擲（不然同一句一回合接一回合重講）。"""
    kind = h.tactic.kind
    dots = {d[0] for d in f.foe.dots}
    return (
        (kind == "sand" and "風沙" in dots) or (kind == "fire" and "焚身" in dots)
        or (kind == "curse" and f.foe.has("亂神")) or (kind == "roar" and (f.foe.has("定身") or f.foe.has("失神")))
        or (kind == "disarm" and (f.foe.has("卸勁") or "卸勁" in f.foe.later))
        or (kind == "foresight" and "看穿" in f.us.later)
    )


def _opening(f: _Fight) -> None:
    """回合開始：蓄力好的出手、起手與騎戰擲發動率、心法每回合都問。"""
    for h in f.holders:
        t = h.tactic
        if f.pending.get(t.name) == f.round:
            del f.pending[t.name]
            KINDS[t.kind](f, h)
            continue
        if t.name in f.pending:
            continue
        if t.timing == "起手" and _in_span(h, f.round) and f.roll(f.rate(h)):
            KINDS[t.kind](f, h)
        elif t.timing == "心法" and _in_span(h, f.round):
            KINDS[t.kind](f, h)
        elif t.timing == "騎戰" and f.ctx.mount_tier > 0:
            KINDS[t.kind](f, h)


def _strike(f: _Fight) -> None:
    """出招：每回合擲發動率；要蓄力的這一回合只說一句，下一回合出手。"""
    for h in f.holders:
        t = h.tactic
        if t.timing != "出招" or t.name in f.pending or _busy(f, h):
            continue
        rate = f.rate(h)
        if t.kind == "heavy_blow" and f.edge > 50:
            rate += t.params.get("lead_pct", 0.0)
        if t.kind == "night_raid" and f.ctx.night:
            rate = 1.0
        if not f.roll(rate):
            continue
        if t.prep:
            f.pending[t.name] = f.round + t.prep
            f.lines.append(f"{LEAD}{t.name}〕{h.who}蓄力")
            continue
        KINDS[t.kind](f, h)


def _follow(f: _Fight, beat: int) -> None:
    """乘勢：你剋中對手之後才擲。"""
    if beat <= 0:
        return
    for h in f.holders:
        t = h.tactic
        if t.timing != "乘勢" or _busy(f, h):
            continue
        rate = f.rate(h)
        if t.kind == "brutal":
            p = t.params
            rate += min(p.get("evil_cap_pct", 0.0), f.ctx.evil // max(1, int(p.get("evil_step", 10))) * p.get("per_evil_pct", 0.0))
        if f.roll(rate):
            KINDS[t.kind](f, h)


def play(
    margin: float, effective: float, rounds: int, holders: list[Holder], ctx: Ctx, tuning: TacticTuning, rng: random.Random,
) -> Clash:
    """一場一般的仗一回合一回合打。margin 是單次判定擲出來的差距、effective 是判定用的對手強度（破甲之後）；回傳每一回合與收場的差距。
    沒有 holders 時一樣演回合，差距照原樣回傳。"""
    ours, theirs, pushes = base_path(margin, effective, rounds, tuning, rng)
    f = _Fight(holders, ctx, tuning, rng)
    guardish = any(h.tactic.kind in GUARD_KINDS for h in holders)
    turns: list[Turn] = []
    total = 0.0
    stopped = False
    for k in range(rounds):
        f.round = k + 1
        f.lines, f.delta, f.extra = [], 0.0, 0.0
        f.chain = f.us.has("連環")
        f.flawless = f.us.has("無隙")
        f.know = f.us.has("看穿")
        f.no_guard = f.veiled = False
        f.push_mod = f.foe_cut = f.guard_mod = f.rebound = 0.0
        base_beat = counter(ours[k], theirs[k])
        f.strike = tuning.strike  # 你這一方一回合的出手照對手的算：戰法的推力加成不跟著懸殊的差距放大
        if holders:
            _opening(f)
            _strike(f)
        a, b = ours[k], theirs[k]
        foe_self = us_self = False
        if holders:
            # 對手：定身出不了手、失神亂出（可能打到自己）、卸勁出不了強攻
            if f.foe.has("定身"):
                b = None
            elif f.foe.has("失神"):
                b = rng.choice(MOVES)
                foe_self = rng.random() < tuning.self_hit
                if foe_self:
                    f.lines.append(f"{LEAD}失神〕{ctx.foe}亂了陣腳，一招打在自己身上")
            elif f.foe.has("卸勁") and b == "強攻":
                b = rng.choice(["奇襲", "固守"])
            # 你：自己的狀態先，再照看得到多少挑招
            allowed = [m for m in MOVES if not (m == "強攻" and f.us.has("卸勁")) and not (m == "固守" and f.no_guard)]
            if f.us.has("定身"):
                a = None
            elif f.us.has("失神"):
                a = rng.choice(MOVES)
                us_self = rng.random() < tuning.self_hit
                if us_self:
                    f.lines.append(f"{LEAD}失神〕你這一方心神一亂，一招打在自己身上")
            elif b is not None and (f.know or f.foe.has("亂神")):
                a = answer_to(b) if answer_to(b) in allowed else best_against([b], allowed)
            elif f.foe.has("卸勁") and not f.foe.has("失神"):
                a = best_against(["奇襲", "固守"], allowed)
            elif guardish and "固守" in allowed and rng.random() < tuning.prefer_guard:
                a = "固守"
            elif a not in allowed:
                a = rng.choice(allowed)
            if f.stacks.pop("夜襲", None) and a is not None:  # 夜襲：這一回合一定出奇襲
                a = "奇襲"
        beat = counter(a, b)
        if beat < 0 and f.flawless:
            beat = 0
        if holders:
            f.delta += (beat - base_beat) * tuning.counter
            landed = b is not None and not foe_self
            if b is None:
                f.delta += tuning.strike
            if foe_self:
                f.delta += 2 * tuning.strike
            if a is None:
                f.delta -= f.strike
            if us_self:
                f.delta -= 2 * tuning.strike
            if f.us.has("霧"):  # 霧：照各自的機會打空；你身法快只有對手會打空
                miss = 0.3
                for h in holders:
                    if h.tactic.kind == "fog":
                        miss = h.tactic.params.get("miss_pct", miss)
                if landed and rng.random() < miss:
                    landed = False
                    f.delta += tuning.strike
                    f.lines.append(f"{LEAD}霧〕{ctx.foe}在霧裡一招打空")
                if a is not None and ctx.our_agility <= ctx.foe_agility and rng.random() < miss:
                    f.delta -= f.strike
                    f.lines.append(f"{LEAD}霧〕你這一方在霧裡一招打空")
            if a == "固守":
                f.push_mod += f.guard_mod
                if b == "強攻":
                    f.delta += f.rebound * tuning.strike
            if a is not None:
                f.delta += f.push_mod * f.strike
                if f.chain:
                    f.delta += f.strike
            if landed:
                f.delta += f.foe_cut * tuning.strike
            f.delta += f.extra
            for _name, pct, _left in f.foe.dots:
                f.delta += pct * 100 * tuning.dot
            if f.veiled:
                landed = False
            _follow(f, beat)
        else:
            landed = True
        push = pushes[k] + f.delta
        total += f.delta
        f.edge += push
        if holders:
            for h in holders:  # 祭天：贏下這一回合疊一層，滿了下一回合連環
                if h.tactic.kind == "sacrifice" and push > 0:
                    full = int(h.tactic.params.get("stacks", 5))
                    n = f.stacks.get(h.tactic.name, 0) + 1
                    if n >= full:
                        f.put(f.us, "連環", 1, now=False)
                        f.say(h, f"祭天 {full} 層滿了，下一回合連環")
                        n = 0
                    f.stacks[h.tactic.name] = n
        turns.append(Turn(number=k + 1, ours=a, theirs=b, beat=beat, push=push, edge=max(0.0, min(100.0, f.edge)),
                          landed=landed, lines=list(f.lines)))
        f.us.tick()
        f.foe.tick()
        if abs(f.edge - 50) >= tuning.stop and k < rounds - 1:
            stopped = True
            break
    if not f.fired and not total:
        final = margin
    elif stopped:
        final = (f.edge - 50) * max(1.0, abs(effective)) / tuning.span
    else:
        final = margin + total * max(1.0, abs(effective)) / tuning.span
    return Clash(turns=turns, margin=final, stopped=stopped, hp=f.hp, fired=f.fired)


# ── 誰帶著哪一門 ────────────────────────────────────────


def of(content: Content, skill_id: str | None) -> TacticDef | None:
    skill = content.skills.get(skill_id) if skill_id else None
    return skill.tactic if skill is not None else None


def figure_of(content: Content, skill_id: str) -> str | None:
    """這門本命武學是哪位人物的（人物表的 starting_wugong／starting_neigong）。"""
    for ch in content.characters.values():
        if skill_id in (ch.starting_wugong, ch.starting_neigong):
            return ch.id
    return None


def holders_of(content: Content, rows: list[tuple[str, str, str | None, str | None]]) -> list[Holder]:
    """（名字, 鍵, 武學 id, 內功 id）一列一個人 → 帶著本命戰法的那幾門（武學在前）。同一門戰法兩個人都帶著時只算第一個
    （本人在前）：同一招不會一回合發兩次。"""
    out: list[Holder] = []
    seen: set[str] = set()
    for who, key, wugong, neigong in rows:
        for skill_id in (wugong, neigong):
            tactic = of(content, skill_id)
            if tactic is None or tactic.name in seen:
                continue
            seen.add(tactic.name)
            out.append(Holder(who=who, key=key, skill=skill_id, figure=figure_of(content, skill_id), tactic=tactic))
    return out
