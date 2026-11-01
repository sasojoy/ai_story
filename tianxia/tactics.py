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

from .models import BEATS, MOVES, CharacterDef, Content, TacticBond, TacticDef, TacticTuning

CONTROLS = ("卸勁", "亂神", "定身", "失神")  # 守一擋得下的
DOTS = ("焚身", "風沙", "血創")
LEAD = "〔"  # 戰法句一律以「〔戰法名〕」開頭（同功效句，battlelog.TRAIT_LEAD：網頁收著的卡片先藏起來）
# 招的印記（招式與絕學稿案第一節，Joy 2026-10-21 按建議）：卡上不寫分類（「本命戰法」「小戰法」），招名前面蓋一枚印——
# 人物的本命寫「本命」（朱印）、學來的武學寫「看家」（墨印，看家本領）、自創的寫創的人名號的第一個字（私印）、絕招寫「絕」（金印）。
# 網頁照開頭這幾個字畫成印（app.js 的 tacticHtml）
TITLE = "本命"
MINOR_TITLE = "看家"  # 學來的武學帶的（TacticDef.minor）
ULTIMATE_SEAL = "絕"
IMMUNE_KEYS = {"stun": "定身", "daze": "失神", "disarm": "卸勁", "confuse": "亂神"}  # immune 那一種的 params 鍵 → 狀態
SHRUG = "{state}沒能沾身"
PLAYER_KEY = "player"  # 同 state.PLAYER（這裡不 import state）
FOE_KEY = "foe"  # 對手那一方的鍵（他回的、自扣的氣血不算到你身上）
OUR_SIDE = "你這一方"  # 一般的仗裡你這一邊的叫法


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
    foe_fired: list[str] = Field(default_factory=list)  # 對手那一方發動過的（挑戰大勢人物本人）

    @property
    def shifted(self) -> bool:
        return bool(self.fired or self.foe_fired)

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
        text = (f"{span}一直在" if tactic.rounds else "一直在") if rate == "必定" else f"{span if tactic.rounds else '每回合'} {rate}"
    elif tactic.timing == "騎戰":
        text = "騎著馬才有"
    elif tactic.timing == "應招":
        text = f"{'前 ' + str(tactic.rounds) + ' 回合' if tactic.rounds > 1 else '第 1 回合' if tactic.rounds == 1 else ''}兩邊出招之後" + (
            "" if rate == "必定" else f" {rate}")
    else:
        text = f"{span}{rate}" if rate == "必定" else f"{span} {rate}"
    if tactic.prep:
        text += f"・蓄力 {tactic.prep} 回合"
    return f"{tactic.timing}・{text}"


def title_of(tactic: TacticDef, art=None) -> str:
    """招名前面蓋哪一枚印：自創的武學（moves.is_own 那一種：來歷是自創、有創的人）寫創的人名號的第一個字，
    學來的寫「看家」，其餘「本命」。"""
    if art is not None and art.id and getattr(art, "origin", "") == "created" and getattr(art, "creator", None):
        if getattr(art, "quality", "") == "絕學":  # 破境之後自己的招是絕招：金印「絕」
            return ULTIMATE_SEAL
        who = getattr(art, "creator_shown", None) or getattr(art, "creator", None) or ""
        if who[:1]:
            return who[:1]
    return MINOR_TITLE if tactic.minor else TITLE


def card_text(tactic: TacticDef, title: str | None = None) -> str:
    """功法卡、修練頁、角色卡那一段：「本命〔長坂一喝〕出招・每回合 40%：一聲大喝……」；兵器卡寫「特技〔虛影〕……」。"""
    # 本命底蘊照實際寫（19.5%，PM 2026-10-16）：以前 round 到整數、又是逢五取偶，19.5 寫成 20、22.5 寫成 22
    tail = MIGHT_NOTE.format(pct=f"{round(tactic.might * 100, 1):g}") if tactic.might else ""
    title = title or title_of(tactic)
    return f"{title}〔{tactic.name}〕{when_text(tactic)}：{desc_text(tactic)}{tail}"


MIGHT_NOTE = "（本命底蘊：擂台、奪璽單挑每一回合推力 +{pct}%）"  # TacticDef.might


GEAR_TITLE = "特技"
# 自己挑招的仗裡改剋制的重控場（長坂一喝、經緯、黃天咒、天雷符）：那邊一回合的勝負幾乎全看剋不剋，照 Config.tactics.bout_control_share 打折
BOUT_CONTROL = frozenset({"roar", "foresight", "curse", "thunder"})
BOND_TITLE = "人器合一"


def bonded(tactic: TacticDef, bond: TacticBond) -> TacticDef:
    """人器合一：名將本命兵器在身上、也練著那位名將的本命時，他那一門戰法照 bond 加強（發動率、蓄力、回合、數字各加）。"""
    params = dict(tactic.params)
    for key, more in bond.params.items():
        params[key] = params.get(key, 0.0) + more
    return tactic.model_copy(update={
        "rate": max(0.0, min(1.0, tactic.rate + bond.rate)), "prep": max(0, min(1, tactic.prep + bond.prep)),
        "rounds": max(0, tactic.rounds + bond.rounds), "params": params,
    })


def bond_fits(h: Holder, figure: str, bond: TacticBond) -> bool:
    """名將本命兵器的人器合一加強的是不是這一門：那位名將的本命、名字是卡上寫的那一門（TacticBond.tactic）。
    team.own_extras 與量表（scripts/measure_tactics.py）都問這一條，另一門照舊。"""
    return h.figure == figure and h.tactic.name == bond.tactic


def copied(tactic: TacticDef, share: float) -> TacticDef:
    """神器的仿品：特技的發動率打折（心法那一種每回合照它擲）。"""
    return tactic.model_copy(update={"rate": tactic.rate * share})


def item_tactic(content: Content, item) -> tuple[TacticDef, TacticBond | None, str | None] | None:
    """一件兵器或防具的特技（第三批）：（特技, 人器合一, 名將本命兵器的人物 id）。名將本命兵器照 gear.json 的 signature_arms，
    神器原品照配方寫的、仿品發動率乘 Config.tactics.copy_rate；一般兵器、名器、坐騎、寶物是 None。item 是 state.Equipment（不 import state）。"""
    if item is None:
        return None
    if getattr(item, "signature", None):
        arm = next((a for a in content.gear.signature_arms if a.character == item.signature), None)
        return (arm.tactic, arm.bond, item.signature) if arm is not None and arm.tactic is not None else None
    copy_of = getattr(item, "copy_of", None)
    recipe = getattr(item, "secret", None) or (copy_of.split("|", 1)[1] if copy_of else None)
    found = content.forge_secrets.get(recipe) if recipe else None
    if found is None or found.tactic is None or not (getattr(item, "original", False) or copy_of is not None):
        return None
    if getattr(item, "original", False):
        return found.tactic, None, None
    return copied(found.tactic, content.config.tactics.copy_rate), None, None


def item_lines(content: Content, item) -> list[str]:
    """兵器卡、防具卡、修練頁那一列寫的特技（與人器合一）：「特技〔虛影〕起手・前 2 回合 20%：化影……」。沒有特技是空的。"""
    found = item_tactic(content, item)
    if found is None:
        return []
    tactic, bond, _figure = found
    out = [card_text(tactic, GEAR_TITLE)]
    if bond is not None:
        out.append(f"{BOND_TITLE}：{bond.desc}")
    return out


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


class Status(BaseModel):
    """一方身上的狀態。一般的仗一場打完就丟；頭目戰、擂台、奪璽單挑存在 Bout 裡跨回合（每一回合是一次請求）。"""

    name: str = ""  # 句子裡怎麼叫這一方（「你這一方」、對手的名字）
    states: dict[str, int] = Field(default_factory=dict)  # 狀態 → 還剩幾回合（這一回合算在內）
    later: dict[str, int] = Field(default_factory=dict)  # 下一回合才生效的
    dots: list[tuple[str, float, int]] = Field(default_factory=list)  # （名字, 每回合扣幾成, 還剩幾回合）
    misses: float = 0.0  # 霧裡這一方出招打空的機會（霧鎖山川照施放者的身法定）
    reflect: float = 0.0  # 守一擋下控制時反彈回施放者的機會（亂世心術）
    reflect_by: str = ""
    wards: int = 0  # 守一擋下了幾次控制（海內儒宗）
    immune: dict[str, tuple[float, str, str]] = Field(default_factory=dict)  # 這一回合不受哪幾種控制：狀態 →（機會, 戰法名, 那一句）（穩、不動、嶽峙鎧）
    # 一直在的心法（timing 心法、必定）這一仗已經寫過一次的（「誰｜招名」）：之後每回合照樣生效，戰報不再重複（招式與絕學稿案第一節）
    told: list[str] = Field(default_factory=list)

    def has(self, name: str) -> bool:
        return self.states.get(name, 0) > 0

    def tick(self) -> None:
        self.states = {k: v - 1 for k, v in self.states.items() if v > 1}
        self.dots = [(n, pct, left - 1) for n, pct, left in self.dots if left > 1]
        for k, v in self.later.items():
            self.states[k] = max(self.states.get(k, 0), v)
        self.later = {}


class _Fight:
    """一方在一場仗裡打到一半的樣子；KINDS 裡的每一種戰法改它。兩邊都帶著戰法時各一個，us／foe 是同兩份 Status 對調。"""

    def __init__(
        self, holders: list[Holder], ctx: Ctx, tuning: TacticTuning, rng: random.Random, *, us: Status | None = None,
        foe: Status | None = None, pending: dict[str, int] | None = None, stacks: dict[str, int] | None = None,
        unit: float | None = None,
    ):
        self.holders, self.ctx, self.t, self.rng = holders, ctx, tuning, rng
        self.us = us if us is not None else Status(name=OUR_SIDE)
        self.foe = foe if foe is not None else Status(name=ctx.foe)
        self.round = 0
        self.edge = 50.0  # 這一方看出去的氣勢（越高越佔上風）
        self.strike = tuning.strike if unit is None else unit  # 一回合的出手（連環、推力加成、定身照它算）
        self.lines: list[str] = []
        self.hp: dict[str, float] = {}
        self.fired: list[str] = []
        self.pending = pending if pending is not None else {}  # 蓄力中的戰法 → 第幾回合出手
        self.stacks = stacks if stacks is not None else {}
        self.planned: str | None = None  # 頭目戰、擂台、奪璽單挑：這一方這一回合自己挑好的招（夜襲只在出奇襲時發）
        self.war = False  # 決戰：沒有單一的對手，只算自己身上的
        self.bout = False  # 頭目戰、擂台、奪璽單挑：招在戰法之前就挑好了
        self.pvp = False  # 擂台、奪璽單挑（Bout.pvp）：本命底蘊只在這裡算
        self.mine: str | None = None  # 這一回合自己實際出的招（乘勢、應招看它）
        self.begin(0, 50.0, self.lines)

    def begin(self, round_: int, edge: float, lines: list[str]) -> None:
        """回合開始：這一回合的旗標從狀態讀、加成歸零。"""
        self.round, self.edge, self.lines = round_, edge, lines
        self.chain = self.us.has("連環")
        self.flawless = self.us.has("無隙")
        self.know = self.us.has("看穿")
        self.no_guard = self.veiled = False
        self.push_mod = self.foe_cut = self.guard_mod = self.rebound = 0.0
        self.extra = 0.0  # 這一回合另外推的氣勢（援兵）
        self.dmg = 0.0  # 這一回合扣對手氣血池的幾成（焚身、風沙、血創、落雷）
        self.pierce = False  # 貫日：剋中對手時他的化影、借力對你無效
        self.no_borrow = False  # 這一回合借力落空（被貫日剋中、被破甲）
        self.ally_fires = 0  # 這一回合同伴發動了幾次戰法（昭義）
        if round_ > 0:
            self.arm()
            if self.pvp:  # 本命底蘊（TacticDef.might）：本人身上練著的本命，擂台、奪璽單挑每一回合推力多一點
                self.push_mod += sum(h.tactic.might for h in self.holders if h.figure and h.key == PLAYER_KEY)

    def arm(self) -> None:
        """回合開始：不受控制的那幾種（穩、不動、嶽峙鎧）照這一回合擲好，記在自己的狀態上（對手的控制在 put 裡看）。"""
        self.us.immune = {}
        for h in self.holders:
            t = h.tactic
            if t.kind != "immune" or not _usable(self, h) or not _in_span(h, self.round):
                continue
            if t.rate < 1 and not self.roll(t.rate):
                continue
            for key, chance in t.params.items():
                state = IMMUNE_KEYS.get(key)
                if state is None or chance <= 0:
                    continue
                old = self.us.immune.get(state)
                both = 1 - (1 - (old[0] if old else 0.0)) * (1 - min(1.0, chance))
                by = (h.tactic.name, h.tactic.say or SHRUG) if old is None or chance >= old[0] else old[1:]
                self.us.immune[state] = (both, *by)

    # 共用的小動作
    def say(self, h: Holder, text: str, **extra: str) -> None:
        """發動的那一句：「〔戰法名〕名字＋這一句」。戰法寫了 say（功效、神器、名將本命兵器）就用它（{foe}、{鍵} 換成數字）。"""
        if h.tactic.say:
            values = {k: value_text(k, v) for k, v in h.tactic.params.items()}
            text = h.tactic.say.format(foe=self.ctx.foe, **{**values, **extra})
        steady = h.tactic.timing == "心法" and h.tactic.rate >= 1
        mark = f"{h.who}|{h.tactic.name}"
        if not steady or mark not in self.us.told:
            self.lines.append(f"{LEAD}{h.tactic.name}〕{h.who}{text}")
            if steady:
                self.us.told.append(mark)
        self.fired.append(h.tactic.name)
        if h.key not in (PLAYER_KEY, FOE_KEY):
            self.ally_fires += 1

    def heal(self, key: str, pct: float) -> None:
        self.hp[key] = self.hp.get(key, 0.0) + pct

    def put(self, side: Status, name: str, turns: int, *, now: bool) -> bool:
        """給一方加一個狀態；守一擋控制（回傳 False），擋下的那一方帶著亂世心術時有機會反彈回施放者。
        now：這一回合就生效（出招、起手），否則下一回合（乘勢）。"""
        if name in CONTROLS and side.has("守一"):
            side.wards += 1
            self.lines.append(f"{LEAD}守一〕{side.name}心神守住，{name}沒能沾身")
            if side is self.foe and side.reflect and self.rng.random() < side.reflect and not self.us.has("守一"):
                book = self.us.states if now else self.us.later
                book[name] = max(book.get(name, 0), turns)
                self.lines.append(f"{LEAD}{side.reflect_by}〕{side.name}把{name}反彈回去，{self.us.name}{name} {turns} 回合")
            return False
        if name in side.immune:
            chance, by, said = side.immune[name]
            if self.rng.random() < chance:
                self.lines.append(f"{LEAD}{by}〕{side.name}" + said.format(state=name, foe=self.ctx.foe))
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
        share = self.t.bout_control_share if self.bout and h.tactic.kind in BOUT_CONTROL else 1.0
        return (h.tactic.rate + bonus) * share

    def roll(self, chance: float) -> bool:
        return self.rng.random() < chance


# ── 三十六種戰法（kind → 做法）。起手、出招、騎戰在出招之前，乘勢在剋中之後，心法每回合都問 ──────


def _chase_disarm(f: _Fight, h: Holder) -> None:  # 曹操〔橫槊賦詩〕
    f.chain = True
    turns = int(h.tactic.params.get("turns", 1))
    if f.war:
        f.say(h, "橫槊追擊，這一回合連環")
        return
    f.put(f.foe, "卸勁", turns, now=False)
    f.say(h, f"橫槊追擊，這一回合連環，{f.ctx.foe}卸勁 {turns} 回合")


def _opening_ward(f: _Fight, h: Holder) -> None:  # 曹操〔亂世心術〕
    turns = int(h.tactic.params.get("turns", 2))
    f.put(f.us, "守一", turns, now=True)
    # 反彈有好幾個來源時取最高的（亂世心術、絕招〔穩〕、梟風槍〔挾勢〕都走這裡）：後發動的不蓋掉前面的、沒寫反彈的不清成 0
    # （PM 2026-10-16：以前挾勢比亂世心術晚發動，帶著梟風槍反彈反而是 0%）
    pct = h.tactic.params.get("reflect_pct", 0.0)
    if pct > f.us.reflect:
        f.us.reflect, f.us.reflect_by = pct, h.tactic.name
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
    if f.war:
        f.say(h, "拖刀回斬，這一下推力加重")
        return
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
        f.say(h, f"一聲大喝，{f.ctx.foe}{state} {turns} 回合", state=state)  # 自創的招 say 寫了 {state}


def _unbroken(f: _Fight, h: Holder) -> None:  # 張飛〔丈八狂瀾〕
    f.flawless = True
    f.no_guard = True
    if f.round == 1:
        f.say(h, f"蛇矛狂掃，前 {h.tactic.rounds} 回合無隙，只攻不守")


def _vanguard(f: _Fight, h: Holder) -> None:  # 孫堅〔先登斬將〕
    f.chain = True
    if h.tactic.params.get("chain_next", 0) > 0:  # 人器合一（江潮槍）：下一回合也連環
        f.put(f.us, "連環", 1, now=False)
        f.say(h, "先登陷陣，這一回合與下一回合都連環")
        return
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
    f.dmg += hits * p.get("dot_pct", 0.0)
    stunned = (f.foe.has("霧") or f.us.has("霧") or any(d[0] == "風沙" for d in f.foe.dots)) and any(
        f.roll(p.get("stun_pct", 0.0)) for _ in range(hits)
    )
    if stunned and f.put(f.foe, "定身", 1, now=True):
        f.say(h, f"落雷 {hits} 下，借著霧沙劈中{f.ctx.foe}，定身 1 回合")
    else:
        f.say(h, f"落雷 {hits} 下，劈得{f.ctx.foe}焦頭爛額")


def _curse(f: _Fight, h: Holder) -> None:  # 張角〔黃天咒〕
    turns = int(h.tactic.params.get("turns", 2)) + (1 if f.bout else 0)  # 自己挑招的仗：這一回合的招早送出了，多亂一回合才看得到
    if f.put(f.foe, "亂神", turns, now=True):
        f.say(h, f"念起黃天咒，{f.ctx.foe}亂神 {turns} 回合，自己也失神 1 回合")
    else:
        f.say(h, "念起黃天咒，自己失神 1 回合")
    f.put(f.us, "失神", 1, now=False)


def _sand(f: _Fight, h: Holder) -> None:  # 張寶〔揚沙術〕
    turns = int(h.tactic.params.get("turns", 3))
    f.burn("風沙", h.tactic.params.get("dot_pct", 0.0), turns)
    f.say(h, f"揚起漫天黃沙，{f.ctx.foe}陷入風沙 {turns} 回合")


def _fog(f: _Fight, h: Holder) -> None:  # 張寶〔霧鎖山川〕：施放者身法快時只有對手會打空
    turns = int(h.tactic.params.get("turns", 3))
    miss = h.tactic.params.get("miss_pct", 0.3)
    f.put(f.us, "霧", turns, now=True)
    f.put(f.foe, "霧", turns, now=True)
    one = f.ctx.our_agility > f.ctx.foe_agility
    f.foe.misses = miss
    f.us.misses = 0.0 if one else miss
    f.say(h, f"起霧 {turns} 回合" + (f"，{f.us.name}身法快，只有{f.ctx.foe}會打空" if one else "，雙方都可能打空"))


def _bloodrage(f: _Fight, h: Holder) -> None:  # 張梁〔人公血戰〕
    p = h.tactic.params
    lost = max(0.0, 1 - f.ctx.hp_ratio)
    more = min(p.get("cap_pct", 0.0), int(lost * 10) * p.get("per_pct", 0.0))
    f.push_mod += more
    if more and not f.stacks.get(h.tactic.name + "|說", 0):
        f.stacks[h.tactic.name + "|說"] = 1
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


def _ward_all(f: _Fight, h: Holder) -> None:  # 盧植〔海內儒宗〕：守一；每擋下一次控制推力加重
    # 守一給到第 rounds 回合為止（卡上「前 3 回合」）：起手每回合都會進來，以前每次重給 rounds 回合，第 3 回合又給 3 回合、撐到第 5 回合
    span = h.tactic.rounds
    f.put(f.us, "守一", max(1, span - f.round + 1) if span else 1, now=True)
    f.push_mod += f.us.wards * h.tactic.params.get("per_ward_pct", 0.0)
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
    if f.planned is not None and f.planned != "奇襲":  # 自己挑招的仗：沒出奇襲就不發
        return
    f.stacks["夜襲"] = 1
    f.push_mod += h.tactic.params.get("mult", 2.0) - 1
    f.say(h, "趁夜突襲，這一回合奇襲推力加倍")


def _reinforce(f: _Fight, h: Holder) -> None:  # 波才〔三十六方〕
    if f.roll(h.tactic.params.get("chance_pct", 0.0)):
        f.extra += h.tactic.params.get("strikes", 1.0) * f.strike
        f.say(h, "黃巾援兵趕到，推了一把")


def _divine(f: _Fight, h: Holder) -> None:  # 張曼成〔神上使〕：放手一搏失手時才有（divine_save），這裡不做事
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


# ── 第三批：玩家自己的武學功效、神器與名將本命兵器的特技（句子多半寫在內容的 say）──────────


def _shadow(f: _Fight, h: Holder) -> None:  # 輕身、玄晶劍〔虛影〕、掠影衫〔殘影〕
    f.veiled = True
    f.say(h, "身形一晃，這一回合化影")


def _mist(f: _Fight, h: Holder) -> None:  # 險：起霧一回合，雙方都可能打空，身法高的那一方少打空
    miss = h.tactic.params.get("miss_pct", 0.3)
    f.put(f.us, "霧", 1, now=True)
    f.put(f.foe, "霧", 1, now=True)
    fast = f.t.mist_fast_share
    f.us.misses = miss * (fast if f.ctx.our_agility > f.ctx.foe_agility else 1.0)
    f.foe.misses = miss * (fast if f.ctx.foe_agility > f.ctx.our_agility else 1.0)
    f.say(h, "兵行險著，四下起霧")


def _drain(f: _Fight, h: Holder) -> None:  # 吸取：剋中對手時回氣血
    pct = h.tactic.params.get("heal_pct", 0.0)
    f.heal(h.key, pct)
    f.say(h, f"收了{f.ctx.foe}散逸的氣勁，回氣血 {value_text('heal_pct', pct)}")


def _mend(f: _Fight, h: Holder) -> None:  # 回春：每回合開始回氣血
    f.heal(h.key, h.tactic.params.get("heal_pct", 0.0))
    if not f.stacks.get(h.tactic.name + "|說", 0):
        f.stacks[h.tactic.name + "|說"] = 1
        f.say(h, "氣血一回合一回合慢慢回了過來")


def _break(f: _Fight, h: Holder) -> None:  # 破甲：強攻剋中時，對手下一回合固守、借力落空
    if f.mine != "強攻":
        return
    if f.put(f.foe, "破甲", 1, now=False):
        f.say(h, f"破開了{f.ctx.foe}的架子，他下一回合固守、借力都不管用")


def _momentum(f: _Fight, h: Holder) -> None:  # 乘勝：每贏一回合疊一層（回合結束時算，見 _after）
    n = f.stacks.get(h.tactic.name, 0)
    f.push_mod += min(f.t.momentum_cap, n * h.tactic.params.get("step_pct", 0.0))


def _insight(f: _Fight, h: Holder) -> None:  # 悟招：每被剋中一次疊一層（_settle 裡算）
    f.push_mod += f.stacks.get(h.tactic.name, 0) * h.tactic.params.get("step_pct", 0.0)


def _quiet(f: _Fight, h: Holder) -> None:  # 不在回合開始做事的：immune（arm）、last_stand（見底時）、應招那幾種（_answer）
    return


def _pierce(f: _Fight, h: Holder) -> None:  # 貫日槍〔貫日〕
    f.pierce = True


def _flawless(f: _Fight, h: Holder) -> None:  # 裂雷矛〔雷吼〕：前幾回合無隙（只攻不守那一半沒有）
    f.flawless = True
    if f.round == 1:
        f.say(h, f"一聲雷吼，前 {h.tactic.rounds} 回合無隙")


def _zhaoyi(f: _Fight, h: Holder) -> None:  # 雲紋雙鋒〔昭義〕：同伴每發動一次戰法回氣血（回合結束時算，見 _after）
    return


# ── 絕學立招（玩家武學追上本命）：自己合成的武學練成絕學時，層數最多的功效升成的那一招（名字是那門絕學的名字）──────────


def _swift(f: _Fight, h: Holder) -> None:  # 先手：剋中後連環，對手有機會定身
    f.chain = True
    turns = int(h.tactic.params.get("turns", 1))
    if f.war:
        f.say(h, "搶得先機，這一回合連環")
        return
    stunned = f.roll(h.tactic.params.get("stun_pct", 0.0)) and f.put(f.foe, "定身", turns, now=False)
    f.say(h, "搶得先機，這一回合連環" + (f"，{f.ctx.foe}定身 {turns} 回合" if stunned else ""))


def _shatter(f: _Fight, h: Holder) -> None:  # 破甲：強攻剋中後對手卸勁幾回合
    if f.mine != "強攻":
        return
    turns = int(h.tactic.params.get("turns", 2))
    if f.put(f.foe, "卸勁", turns, now=False):
        f.say(h, f"一擊破開了{f.ctx.foe}的架子，卸勁 {turns} 回合")


def _leech(f: _Fight, h: Holder) -> None:  # 吸取：剋中後對手血創，扣多少回多少
    p = h.tactic.params
    turns, pct = int(p.get("turns", 2)), p.get("dot_pct", 0.0)
    f.burn("血創", pct, turns)
    f.heal(h.key, pct * turns)
    f.say(h, f"一招見血，{f.ctx.foe}血創 {turns} 回合，扣多少回多少")


def _haze(f: _Fight, h: Holder) -> None:  # 險：起霧幾回合（同險的霧），霧裡對手出招有機會失神（之後每回合在 _strike 擲）
    p = h.tactic.params
    turns, miss = int(p.get("turns", 2)), p.get("miss_pct", 0.3)
    f.put(f.us, "霧", turns, now=True)
    f.put(f.foe, "霧", turns, now=True)
    fast = f.t.mist_fast_share
    f.us.misses = miss * (fast if f.ctx.our_agility > f.ctx.foe_agility else 1.0)
    f.foe.misses = miss * (fast if f.ctx.foe_agility > f.ctx.our_agility else 1.0)
    dazed = f.roll(p.get("daze_pct", 0.0)) and f.put(f.foe, "失神", 1, now=True)
    f.say(h, f"兵行險著，起霧 {turns} 回合" + (f"，{f.ctx.foe}在霧裡失神" if dazed else ""))


def _last_rally(f: _Fight, h: Holder) -> None:  # 厚：氣血見底（或氣勢落後太多）時一場一次，這一回合連環、守一
    p = h.tactic.params
    used = h.tactic.name + "|用"
    if f.stacks.get(used, 0) or not (f.ctx.hp_ratio <= p.get("hp_pct", 0.3) or f.edge <= p.get("edge", 35.0)):
        return
    f.stacks[used] = 1
    turns = int(p.get("turns", 1))
    f.chain = True
    f.put(f.us, "守一", turns, now=True)
    f.say(h, f"退無可退，這一回合連環，守一 {turns} 回合")


# ── 武學技能分檔（Joy 2026-10-17）：合成擲得到的高階技能（content/traits.json 的 high）。對電腦對手也有效：都直接改那一回合的勝負或氣血 ──


def _flash(f: _Fight, h: Holder) -> None:  # 流光：這一回合連環、無隙
    f.chain = True
    f.flawless = True
    f.say(h, "身法一閃，這一回合連環、無隙")


def _scorch(f: _Fight, h: Holder) -> None:  # 烈陽：剋中後對手焚身幾回合
    p = h.tactic.params
    turns = int(p.get("turns", 2))
    f.burn("焚身", p.get("dot_pct", 0.0), turns)
    f.say(h, f"烈勁透體，{f.ctx.foe}焚身 {turns} 回合")


def _golden(f: _Fight, h: Holder) -> None:  # 金身：氣血見底時一場一次，守一、回氣血
    p = h.tactic.params
    used = h.tactic.name + "|用"
    if f.stacks.get(used, 0) or f.ctx.hp_ratio > p.get("hp_pct", 0.3):
        return
    f.stacks[used] = 1
    turns = int(p.get("turns", 1))
    f.put(f.us, "守一", turns, now=True)
    f.heal(h.key, p.get("heal_pct", 0.0))
    f.say(h, f"金身護體，守一 {turns} 回合，回氣血 {value_text('heal_pct', p.get('heal_pct', 0.0))}")


KINDS = {
    "chase_disarm": _chase_disarm, "opening_ward": _opening_ward, "disarm": _disarm, "rally": _rally,
    "heavy_blow": _heavy_blow, "cleanse": _cleanse, "roar": _roar, "unbroken": _unbroken, "vanguard": _vanguard,
    "tiger": _tiger, "awe": _awe, "waver": _waver, "rebound_guard": _rebound_guard, "veil": _veil, "thunder": _thunder,
    "curse": _curse, "sand": _sand, "fog": _fog, "bloodrage": _bloodrage, "oath": _oath, "butcher": _butcher,
    "marshal": _marshal, "fire": _fire, "steady": _steady, "surge": _surge, "tide": _tide, "foresight": _foresight,
    "ward_all": _ward_all, "cavalry": _cavalry, "brutal": _brutal, "night_raid": _night_raid, "reinforce": _reinforce,
    "divine": _divine, "sacrifice": _sacrifice, "hold_city": _hold_city, "gatekeep": _gatekeep,
    "shadow": _shadow, "mist": _mist, "drain": _drain, "mend": _mend, "borrow": _quiet, "break": _break, "momentum": _momentum,
    "insight": _insight, "immune": _quiet, "last_stand": _quiet, "assault": _quiet, "pierce": _pierce, "quake": _quiet,
    "first_shot": _quiet, "zhaoyi": _zhaoyi, "flawless": _flawless,
    "swift": _swift, "shatter": _shatter, "streak": _quiet, "leech": _leech, "haze": _haze, "last_rally": _last_rally,
    "flash": _flash, "bulwark": _quiet, "scorch": _scorch, "elude": _quiet, "golden": _golden,
}
GUARD_KINDS = ("rebound_guard", "hold_city", "steady")  # 出固守才起作用的：自動出招多出固守
# 決戰裡發得了的（沒有單一的對手：只算自己身上的連環、無隙、化影、推力加減、固守加重、回氣血與自扣；
# 卸勁、亂神、定身、失神、霧、看穿、借力、焚身風沙血創落雷、守一都不在決戰裡）。神上使在決戰的放手一搏照樣發（divine_save）
WAR_KINDS = (
    "chase_disarm", "rally", "heavy_blow", "cleanse", "unbroken", "vanguard", "tiger", "waver", "veil", "bloodrage", "oath",
    "marshal", "steady", "surge", "tide", "cavalry", "night_raid", "reinforce", "sacrifice", "hold_city",
    # 第三批：化影、回氣血、乘勝、無隙；斬將與墜星的強攻加重在 war_round 另算，化勁少挨的打也是。
    # 悟招（insight）不在這裡（PM 2026-10-16）：決戰只記你剋中、不記被剋（battle_instance 傳的 beat 是 1 或 0），層數疊不起來，卡上寫決戰不發
    "shadow", "drain", "mend", "momentum", "flawless", "zhaoyi",
    # 絕學立招：連環、連勝無隙、退無可退的連環
    "swift", "streak", "last_rally",
)


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
        or (kind in ("mist", "haze") and (f.us.has("霧") or f.foe.has("霧")))
        or (kind == "shatter" and (f.foe.has("卸勁") or "卸勁" in f.foe.later))
        or (kind == "scorch" and "焚身" in dots)
    )


def _usable(f: _Fight, h: Holder) -> bool:
    return not f.war or h.tactic.kind in WAR_KINDS


def _opening(f: _Fight) -> None:
    """回合開始：蓄力好的出手、起手與騎戰擲發動率、心法每回合都問。"""
    for h in f.holders:
        t = h.tactic
        if not _usable(f, h):
            continue
        if f.pending.get(t.name) == f.round:
            del f.pending[t.name]
            KINDS[t.kind](f, h)
            continue
        if t.name in f.pending:
            continue
        if t.timing == "起手" and _in_span(h, f.round) and f.roll(f.rate(h)):
            KINDS[t.kind](f, h)
        elif t.timing == "心法" and _in_span(h, f.round) and (t.rate >= 1 or t.kind == "immune" or f.roll(f.rate(h))):
            KINDS[t.kind](f, h)  # 神器的仿品：心法那一種每回合照打了折的發動率擲（immune 在 arm 擲過）
        elif t.timing == "騎戰" and f.ctx.mount_tier > 0:
            KINDS[t.kind](f, h)


def _strike(f: _Fight) -> None:
    """出招：每回合擲發動率；要蓄力的這一回合只說一句，下一回合出手。"""
    for h in f.holders:
        t = h.tactic
        if t.kind == "haze" and f.foe.has("霧") and _usable(f, h) and not f.foe.has("失神"):  # 霧還在：對手出招有機會失神
            if f.roll(t.params.get("daze_pct", 0.0)) and f.put(f.foe, "失神", 1, now=True):
                f.say(h, f"霧裡看不清來路，{f.ctx.foe}失神")
            continue
        if t.timing != "出招" or t.name in f.pending or _busy(f, h) or not _usable(f, h):
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
    """乘勢：這一方剋中對手之後才擲。"""
    if beat <= 0:
        return
    for h in f.holders:
        t = h.tactic
        if t.timing != "乘勢" or _busy(f, h) or not _usable(f, h):
            continue
        rate = f.rate(h)
        if t.kind == "brutal":
            p = t.params
            rate += min(p.get("evil_cap_pct", 0.0), f.ctx.evil // max(1, int(p.get("evil_step", 10))) * p.get("per_evil_pct", 0.0))
        if f.roll(rate):
            KINDS[t.kind](f, h)


def _after(f: _Fight, won: bool) -> None:
    """回合結束：祭天贏下這一回合疊一層，滿了下一回合連環；乘勝贏一回合疊一層、輸一回合減半；昭義照同伴這一回合發動了幾次回氣血。"""
    for h in f.holders:
        if h.tactic.kind == "momentum" and _usable(f, h):
            n = f.stacks.get(h.tactic.name, 0)
            f.stacks[h.tactic.name] = n + 1 if won else n // 2
            if won and n == 0 and not f.stacks.get(h.tactic.name + "|說", 0):
                f.stacks[h.tactic.name + "|說"] = 1
                f.say(h, "越打越順，推力一回合比一回合重")
        if h.tactic.kind == "streak" and _usable(f, h):  # 乘勝的絕招：連贏幾回合，下一回合無隙
            # 無隙那一回合贏的不算連贏（Joy 2026-10-23「甲 加一半」的共同修正）：不然開打無隙一贏就接著無隙，一路鎖死
            n = (f.stacks.get(h.tactic.name, 0) + (0 if f.flawless else 1)) if won else 0
            if n >= int(h.tactic.params.get("wins", 2)):
                f.put(f.us, "無隙", int(h.tactic.params.get("turns", 1)), now=False)
                f.say(h, f"連贏 {n} 回合，下一回合無隙")
                n = 0
            f.stacks[h.tactic.name] = n
        if h.tactic.kind == "zhaoyi" and f.ally_fires:
            pct = h.tactic.params.get("heal_pct", 0.0) * f.ally_fires
            f.heal(h.key, pct)
            f.say(h, f"同伴戰法連發，回氣血 {value_text('heal_pct', pct)}")
        if h.tactic.kind == "sacrifice" and won:
            full = int(h.tactic.params.get("stacks", 5))
            n = f.stacks.get(h.tactic.name, 0) + 1
            if n >= full:
                f.put(f.us, "連環", 1, now=False)
                f.say(h, f"祭天 {full} 層滿了，下一回合連環")
                n = 0
            f.stacks[h.tactic.name] = n


def _allowed(me: _Fight) -> list[str]:
    return [m for m in MOVES if not (m == "強攻" and me.us.has("卸勁")) and not (m == "固守" and me.no_guard)]


def _pick(me: _Fight, base: str | None, his: str | None, rng: random.Random, t: TacticTuning, *, smart: bool, guardish: bool,
          ) -> tuple[str | None, bool]:
    """一般的仗裡這一方自動出的招：（招, 打到自己沒有）。定身出不了手、失神亂出（可能打到自己）、卸勁出不了強攻；
    smart（這一方帶著戰法）時看穿或對手亂神就出剋他的那一招、對手卸勁就挑不吃虧的、帶著固守戰法的多出固守。"""
    if me.us.has("定身"):
        return None, False
    if me.us.has("失神"):
        move = rng.choice(MOVES)
        hit = rng.random() < t.self_hit
        if hit:
            me.lines.append(f"{LEAD}失神〕{me.us.name}心神一亂，一招打在自己身上")
        return move, hit
    allowed = _allowed(me)
    if smart:
        if his is not None and (me.know or me.foe.has("亂神")):
            return (answer_to(his) if answer_to(his) in allowed else best_against([his], allowed)), False
        if me.foe.has("卸勁") and not me.foe.has("失神"):
            return best_against(["奇襲", "固守"], allowed), False
        if guardish and "固守" in allowed and rng.random() < t.prefer_guard:
            return "固守", False
    if base not in allowed:
        return rng.choice(allowed), False
    return base, False


def _settle(
    f: _Fight, g: _Fight, a: str | None, b: str | None, *, a_off: bool, b_off: bool, a_self: bool, b_self: bool,
    base_beat: int | None, rng: random.Random,
) -> tuple[int, float, bool, bool]:
    """兩邊的招定了之後這一回合怎麼算（f 是「我」、g 是對手）：（剋, 氣勢往我多推多少, 對手打到我沒有, 我打到對手沒有）。
    base_beat 給了（一般的仗）就把剋的改變也換成氣勢（底下那一條已經照原本的招算過一次）；頭目戰、擂台、奪璽單挑的剋由呼叫端照招算。
    off：這一方定身、出不了手；self：失神打到自己。"""
    t, u = f.t, f.strike
    beat = counter(a, b)
    if beat < 0 and f.flawless:
        beat = 0
    if beat > 0 and g.flawless:
        beat = 0
    # 破甲：被破了架子的那一方這一回合固守剋不住強攻、借力落空
    if beat < 0 and a == "強攻" and f.foe.has("破甲"):
        beat = 0
    if beat > 0 and b == "強攻" and f.us.has("破甲"):
        beat = 0
    f.no_borrow = f.us.has("破甲")
    g.no_borrow = f.foe.has("破甲")
    if beat > 0 and f.pierce:  # 貫日：剋中對手時，他的化影、借力對你無效
        g.veiled, g.no_borrow = False, True
    if beat < 0 and g.pierce:
        f.veiled, f.no_borrow = False, True
    f.mine, g.mine = a, b
    d = (beat - base_beat) * t.counter if base_beat is not None else 0.0
    hit_me = b is not None and not b_self
    hit_him = a is not None and not a_self
    more, stop_him = _answer(f, a, b)
    less, stop_me = _answer(g, b, a)
    d += more - less
    if stop_him:
        hit_me = False
    if stop_me:
        hit_him = False
    if b_off:
        d += u
    if b_self:
        d += 2 * u
    if a_off:
        d -= u
    if a_self:
        d -= 2 * u
    if f.us.has("霧"):  # 霧：照各自的機會打空（霧鎖山川照施放者的身法定誰會打空）
        if hit_me and f.foe.misses and rng.random() < f.foe.misses:
            hit_me = False
            d += u
            f.lines.append(f"{LEAD}霧〕{f.foe.name}在霧裡一招打空")
        if a is not None and f.us.misses and rng.random() < f.us.misses:
            hit_him = False
            d -= u
            f.lines.append(f"{LEAD}霧〕{f.us.name}在霧裡一招打空")
    if a == "固守":
        f.push_mod += f.guard_mod
        if b == "強攻" and not f.no_borrow:
            d += f.rebound * u
    if b == "固守":
        g.push_mod += g.guard_mod
        if a == "強攻" and not g.no_borrow:
            d -= g.rebound * u
    scaled = f.bout  # 頭目戰、擂台、奪璽單挑：推力加減直接乘在那一回合的推力上（Step.a_mod／b_mod、scale_push），不另換成一擊
    if a is not None:
        d += 0.0 if scaled else f.push_mod * u
        if f.chain and not scaled:  # 自己挑招的仗：連環是這一回合的推力再來一次（Step.a_mod +1）
            d += u
    if b is not None:
        d -= 0.0 if scaled else g.push_mod * u
        if g.chain and not scaled:
            d -= u
    if hit_me and not scaled:
        d += f.foe_cut * u
    if hit_him and not scaled:
        d -= g.foe_cut * u
    d += f.extra - g.extra
    f.dmg += sum(pct for _n, pct, _left in f.foe.dots)
    g.dmg += sum(pct for _n, pct, _left in f.us.dots)
    if f.veiled:
        hit_me = False
    if g.veiled:
        hit_him = False
    chained = f.chain
    _follow(f, beat)
    if f.chain and not chained and a is not None and not scaled:  # 乘勢的連環這一回合就推（橫槊賦詩、疾如潮）
        d += u
    if g.holders:
        chained = g.chain
        _follow(g, -beat)
        if g.chain and not chained and b is not None and not scaled:
            d -= u
    _countered(f, beat < 0)
    _countered(g, beat > 0)
    return beat, d, hit_me, hit_him


def _last_stand(f: _Fight) -> bool:
    """護命：這一方帶著、這一場還沒用過就用掉（寫一句），回 True。"""
    for h in f.holders:
        if h.tactic.kind == "last_stand" and not f.stacks.get(h.tactic.name + "|用", 0) and _usable(f, h):
            f.stacks[h.tactic.name + "|用"] = 1
            f.say(h, "護住要害，這一回合化影")
            return True
    return False


def _countered(f: _Fight, hit: bool) -> None:
    """悟招：被剋中一次記一層看破（下一回合起推力加重）。"""
    if not hit:
        return
    for h in f.holders:
        if h.tactic.kind == "insight" and _usable(f, h):
            n = f.stacks.get(h.tactic.name, 0)
            if n < int(h.tactic.params.get("stacks", 3)):
                f.stacks[h.tactic.name] = n + 1
                f.say(h, f"吃了一記，看破了一層來路（{n + 1} 層）")


def _answer(f: _Fight, mine: str | None, his: str | None) -> tuple[float, bool]:
    """應招：兩邊的招定了之後這一方的特技（化勁、借力、斬將、墜星、撼地、先發……）：（氣勢往這一方多推多少, 對手這一回合打不到你）。"""
    out, stop = 0.0, False
    u = f.strike
    for h in f.holders:
        t, p = h.tactic, h.tactic.params
        if t.timing != "應招" or not _usable(f, h) or not _in_span(h, f.round):
            continue
        if t.kind == "borrow":  # 化勁、借力、凝波甲〔卸力〕：挨強攻時把那一下的一部分還回去
            if his == "強攻" and not f.no_borrow and p.get("chance_pct", 0.0) > 0 and f.roll(p.get("chance_pct", 0.0) * f.rate(h)):
                out += p.get("share_pct", 0.5) * u
                dazed = p.get("daze_pct", 0.0) > 0 and f.roll(p["daze_pct"]) and f.put(f.foe, "失神", 1, now=False)
                f.say(h, f"借著{f.ctx.foe}的來勢，反手送了回去" + (f"，{f.ctx.foe}失神 1 回合" if dazed else ""))
        elif t.kind == "assault":  # 赤魄長刀〔斬將〕、隕星刀〔墜星〕：出強攻推力加重，墜星另有機會讓對手定身
            if mine != "強攻" or not f.roll(f.rate(h)):
                continue
            out += p.get("push_pct", 0.0) * u
            stunned = his is not None and p.get("stun_pct", 0.0) > 0 and f.roll(p["stun_pct"]) and f.put(f.foe, "定身", 1, now=True)
            if stunned:
                out += u
                stop = True
            f.say(h, "強攻加重" + (f"，{f.ctx.foe}定身，這一回合出不了手" if stunned else ""))
        elif t.kind == "quake":  # 撼山棍〔撼地〕：每次固守，對手下一回合有機會卸勁
            if mine == "固守" and f.roll(p.get("chance_pct", 0.0) * f.rate(h)) and f.put(f.foe, "卸勁", 1, now=False):
                f.say(h, f"一棍頓地，{f.ctx.foe}下一回合卸勁")
        elif t.kind == "elude":  # 迷蹤：對手這一擊打空（他推不動你、你不掉氣血）
            if his is not None and f.roll(f.rate(h)):
                out += u
                stop = True
                f.say(h, f"身形飄忽，{f.ctx.foe}這一擊打空")
        elif t.kind == "bulwark":  # 鎮岳：前幾回合被剋中時那一下的推力少吃一半，一半機會不掉氣血
            if counter(mine, his) < 0 and f.roll(f.rate(h)):
                out += p.get("cut_pct", 0.5) * u
                shrug = f.roll(p.get("guard_pct", 0.5))
                stop = stop or shrug
                f.say(h, "穩如山岳，這一下只吃了一半" + ("，沒傷到氣血" if shrug else ""))
        elif t.kind == "rebound_guard":  # 自創的應招〔反照〕：出固守、對手強攻時擲發動率，他吃自己那一下的一部分（心法那一種見 _rebound_guard）
            if mine == "固守" and his == "強攻" and not f.no_borrow and f.roll(f.rate(h)):
                f.rebound += p.get("share_pct", 0.0)
                f.say(h, f"{f.ctx.foe}一記強攻撞在牆上，自己吃了回去")
        elif t.kind == "first_shot":  # 追電弩〔先發〕：對手出了被你剋的招，他那一回合定身
            if counter(mine, his) > 0 and f.roll(f.rate(h)) and f.put(f.foe, "定身", 1, now=True):
                out += u
                stop = True
                f.say(h, f"先發制人，{f.ctx.foe}定身，這一回合出不了手")
    return out, stop


def mirror(ctx: Ctx, name: str = "") -> Ctx:
    """對手那一方的條件（沒另外給時）：身法對調、同一個夜裡。"""
    return Ctx(foe=name or OUR_SIDE, our_agility=ctx.foe_agility, foe_agility=ctx.our_agility, night=ctx.night)


def play(
    margin: float, effective: float, rounds: int, holders: list[Holder], ctx: Ctx, tuning: TacticTuning, rng: random.Random,
    foe_holders: list[Holder] | None = None, foe_ctx: Ctx | None = None,
) -> Clash:
    """一場一般的仗一回合一回合打。margin 是單次判定擲出來的差距、effective 是判定用的對手強度（破甲之後）；回傳每一回合與收場的差距。
    foe_holders 是對手那一方的本命戰法（挑戰大勢人物本人：他自己的兩門），foe_ctx 是他那一方的條件（沒給照 mirror）。
    兩邊都沒有戰法時一樣演回合，差距照原樣回傳。"""
    foe_holders = list(foe_holders or [])
    ours, theirs, pushes = base_path(margin, effective, rounds, tuning, rng)
    us, foe = Status(name=OUR_SIDE), Status(name=ctx.foe)
    f = _Fight(holders, ctx, tuning, rng, us=us, foe=foe)
    g = _Fight(foe_holders, foe_ctx or mirror(ctx), tuning, rng, us=foe, foe=us)
    active = bool(holders or foe_holders)
    guard_us = any(h.tactic.kind in GUARD_KINDS for h in holders)
    guard_foe = any(h.tactic.kind in GUARD_KINDS for h in foe_holders)
    turns: list[Turn] = []
    total = 0.0
    stopped = False
    edge = 50.0
    carry: list[str] = []  # 上一回合收尾才發動的那幾句（乘勝、祭天、昭義）：排在下一回合前面
    for k in range(rounds):
        lines: list[str] = carry
        carry = []
        f.begin(k + 1, edge, lines)
        g.begin(k + 1, 100 - edge, lines)
        base_beat = counter(ours[k], theirs[k])
        if holders:
            _opening(f)
            _strike(f)
        if foe_holders:
            _opening(g)
            _strike(g)
        a, b = ours[k], theirs[k]
        if active:
            b, b_self = _pick(g, b, None, rng, tuning, smart=bool(foe_holders), guardish=guard_foe)
            a, a_self = _pick(f, a, b, rng, tuning, smart=True, guardish=guard_us)
            if foe_holders and b is not None and a is not None and not g.us.has("失神") and (g.know or g.foe.has("亂神")):
                allowed = _allowed(g)
                b = answer_to(a) if answer_to(a) in allowed else best_against([a], allowed)
            if f.stacks.pop("夜襲", None) and a is not None:  # 夜襲：這一回合一定出奇襲
                a = "奇襲"
            if g.stacks.pop("夜襲", None) and b is not None:
                b = "奇襲"
            beat, d, landed, _ = _settle(f, g, a, b, a_off=a is None, b_off=b is None, a_self=a_self, b_self=b_self,
                                         base_beat=base_beat, rng=rng)
            d += (f.dmg - g.dmg) * 100 * tuning.dot
        else:
            beat, d, landed = base_beat, 0.0, True
        push = pushes[k] + d
        if active:  # 護命：氣勢要見底的那一回合留一口氣、化影（一場一次）
            floor = 50 - tuning.stop + 1
            if push < 0 and edge + push < floor and _last_stand(f):
                d += floor - (edge + push)
                push, landed = floor - edge, False
            elif push > 0 and edge + push > 100 - floor and _last_stand(g):
                d -= edge + push - (100 - floor)
                push = 100 - floor - edge
        total += d
        edge += push
        if active:
            mark = len(lines)
            _after(f, push > 0)
            _after(g, push < 0)
            carry = lines[mark:]
            del lines[mark:]
        turns.append(Turn(number=k + 1, ours=a, theirs=b, beat=beat, push=push, edge=max(0.0, min(100.0, edge)),
                          landed=landed, lines=list(lines)))
        us.tick()
        foe.tick()
        if abs(edge - 50) >= tuning.stop and k < rounds - 1:
            stopped = True
            break
    if not f.fired and not g.fired and not total:
        final = margin
    elif stopped:
        final = (edge - 50) * max(1.0, abs(effective)) / tuning.span
    else:
        final = margin + total * max(1.0, abs(effective)) / tuning.span
    return Clash(turns=turns, margin=final, stopped=stopped, hp=f.hp, fired=f.fired, foe_fired=g.fired)


# ── 自己挑招的仗：頭目戰、擂台、奪璽單挑（每一回合是一次請求，狀態存在 Bout 裡）──────────

GAMBLE = "text"  # 這一方這一回合放手一搏（同 seal_duel.TEXT）


class BoutSide(BaseModel):
    """一方：誰帶著哪幾門戰法、條件、身上的狀態與蓄力、層數。也是加入決戰、報名擂台時快照的那一份（狀態是空的）。"""

    holders: list[Holder] = Field(default_factory=list)
    ctx: Ctx
    status: Status = Field(default_factory=Status)
    pending: dict[str, int] = Field(default_factory=dict)
    stacks: dict[str, int] = Field(default_factory=dict)


class Bout(BaseModel):
    """一場自己挑招的仗兩邊的戰法（a 是挑的人／你、b 是對手）。兩邊都沒有戰法時不開（None），一個字都不變。"""

    a: BoutSide
    b: BoutSide
    round: int = 0  # 打完了幾回合
    pvp: bool = False  # 兩邊都是玩家（擂台、奪璽單挑）：本命底蘊（TacticDef.might）只在這種仗算


class Step(BaseModel):
    """一回合戰法改了什麼：兩邊實際出的招（定身是 None、失神亂出、卸勁出不了強攻）、剋、氣勢往 a 多推多少、
    誰挨了打（定身、打空、打到自己、化影的那一邊沒挨打）、兩邊的氣血池照上限回或扣幾成、這一回合的句子。"""

    a_move: str | None = None
    b_move: str | None = None
    beat: int = 0
    push: float = 0.0
    a_hit: bool = True
    b_hit: bool = True
    a_hp: float = 0.0
    b_hp: float = 0.0
    a_cut: float = 0.0  # 這一方這一回合挨的打少幾成（化勁）
    b_cut: float = 0.0
    a_mod: float = 0.0  # 這一回合往 a 推的那一份推力多幾成（乘勝、悟招、斬將、青龍拖刀……減去對手的氣餒），見 scale_push
    b_mod: float = 0.0
    lines: list[str] = Field(default_factory=list)


def scale_push(push: float, step: Step | None) -> float:
    """頭目戰、擂台、奪璽單挑：這一回合招式推的氣勢照推力加減乘（往 a 的乘 a_mod、往 b 的乘 b_mod），最少剩一成。"""
    if step is None or not push:
        return push
    return push * max(0.1, 1 + (step.a_mod if push > 0 else step.b_mod))


def toll_cut(holders: list[Holder]) -> float:
    """化勁：挨的打少幾成（頭目戰、擂台、奪璽單挑、決戰；一般的仗照 team.take_encounter_toll 那一份，不在這裡另算）。"""
    return min(1.0, sum(h.tactic.params.get("toll_pct", 0.0) for h in holders))


def luck_scale(bout: Bout | None) -> float:
    """穩：這一回合運氣的起伏乘多少（兩邊帶著的都算，起伏是兩邊共用的一個數）。"""
    if bout is None:
        return 1.0
    out = 1.0
    for side in (bout.a, bout.b):
        for h in side.holders:
            out *= max(0.0, 1 - h.tactic.params.get("luck_pct", 0.0))
    return out


def guard_pool(bout: Bout | None, side: str, before: float, harm: float, cap: float) -> tuple[float, list[str]]:
    """護命（頭目戰、擂台、奪璽單挑）：這一下會把池子打空時，這一回合化影、池子至少留一成（一場一次）。回（改過的扣多少, 句子）。"""
    if bout is None or harm < before:
        return harm, []
    me = bout.a if side == "a" else bout.b
    for h in me.holders:
        if h.tactic.kind == "last_stand" and not me.stacks.get(h.tactic.name + "|用", 0):
            me.stacks[h.tactic.name + "|用"] = 1
            keep = h.tactic.params.get("keep_pct", 0.1) * cap
            return max(0.0, before - keep), [f"{LEAD}{h.tactic.name}〕{h.who}護住要害，這一回合化影"]
    return harm, []


def side_for(holders: list[Holder], ctx: Ctx) -> BoutSide:
    return BoutSide(holders=holders, ctx=ctx)


def open_bout(
    a: BoutSide | None, b: BoutSide | None, a_name: str, b_name: str, *, a_faction: str | None = None, b_faction: str | None = None,
    b_agility: float | None = None, pvp: bool = False,
) -> Bout | None:
    """開一場：兩邊的快照換上這一場的對手（名字、身法、陣營），狀態從空的起。b 沒有快照（頭目）時身法照 b_agility。
    兩邊都沒有戰法回 None（打起來一個字都不變）。"""
    if not (a and a.holders) and not (b and b.holders):
        return None
    a = a or BoutSide(ctx=Ctx(foe=b_name))
    b = b or BoutSide(ctx=Ctx(foe=a_name, our_agility=5.0 if b_agility is None else b_agility))
    sa = BoutSide(holders=a.holders, ctx=a.ctx.model_copy(update={
        "foe": b_name, "foe_agility": b.ctx.our_agility, "foe_faction": b_faction}), status=Status(name=a_name))
    sb = BoutSide(holders=b.holders, ctx=b.ctx.model_copy(update={
        "foe": a_name, "foe_agility": a.ctx.our_agility, "foe_faction": a_faction}), status=Status(name=b_name))
    return Bout(a=sa, b=sb, pvp=pvp)


def _fights(bout: Bout, tuning: TacticTuning, rng: random.Random, a_ratio: float, b_ratio: float) -> tuple[_Fight, _Fight]:
    a, b = bout.a, bout.b
    unit = tuning.bout_strike
    f = _Fight(a.holders, a.ctx.model_copy(update={"hp_ratio": a_ratio}), tuning, rng, us=a.status, foe=b.status,
               pending=a.pending, stacks=a.stacks, unit=unit)
    g = _Fight(b.holders, b.ctx.model_copy(update={"hp_ratio": b_ratio}), tuning, rng, us=b.status, foe=a.status,
               pending=b.pending, stacks=b.stacks, unit=unit)
    f.bout = g.bout = True
    f.pvp = g.pvp = bout.pvp
    return f, g


def _forced(me: _Fight, move: str, auto: bool, his: str | None, rng: random.Random, t: TacticTuning,
            read: bool = False) -> tuple[str | None, bool]:
    """自己挑好的招被狀態改掉：定身出不了手、失神亂出（可能打到自己）、卸勁或只攻不守時換一招（寫一句）。
    auto（頭目、擂台的分身、奪璽單挑代打的那一邊）回合開始時就看穿、或對手亂神（read）時出剋他的那一招。"""
    if me.us.has("定身"):
        me.lines.append(f"{LEAD}定身〕{me.us.name}定在原地，這一回合出不了手")
        return None, False
    if me.us.has("失神"):
        picked = rng.choice(MOVES)
        hit = rng.random() < t.self_hit
        # 一定要寫出「你挑的那一招變成了什麼」（Joy 2026-10-19「明明我選強攻，為什麼出來變固守……對話中也沒有描述清楚」）：
        # 回合那一行的開頭寫的是實際出的招（「你固守」），玩家挑的是強攻，中間只有這一句能解釋。舊的寫法打到自己時
        # 只寫「一招打在自己身上」，完全沒提招被換掉；沒打到自己時寫「亂出了固守」也看不出那是替換掉你挑的那一招。
        # 句型照卸勁那一支的「使不出X，改出Y」，玩家認得。
        swap = f"使不出{move}，亂出了{picked}" if picked != move else f"{move}出得七零八落"
        me.lines.append(f"{LEAD}失神〕{me.us.name}心神一亂，{swap}" + ("，這一招還打在自己身上" if hit else ""))
        return picked, hit
    allowed = _allowed(me)
    if auto and read and his is not None and his != GAMBLE:
        return (answer_to(his) if answer_to(his) in allowed else best_against([his], allowed)), False
    if move not in allowed:
        picked = rng.choice(allowed)
        why = "卸勁" if move == "強攻" and me.us.has("卸勁") else "只攻不守"
        me.lines.append(f"{LEAD}{why}〕{me.us.name}使不出{move}，改出{picked}")
        return picked, False
    return move, False


def step(
    bout: Bout, a_move: str, b_move: str, edge: float, tuning: TacticTuning, rng: random.Random, *,
    a_ratio: float = 1.0, b_ratio: float = 1.0, a_auto: bool = False, b_auto: bool = False,
) -> Step:
    """打一回合（還沒推氣勢、還沒扣池子）：a_move／b_move 是兩邊挑好的招或 GAMBLE（放手一搏），edge 是 a 看出去的氣勢，
    ratio 是兩邊氣血池剩幾成（人公血戰）。有人放手一搏的回合兩邊的招都不算（同頭目戰），戰法只剩回氣血、援兵與焚身這類。
    呼叫端照回傳的招算剋與推力（duel.push_of、harm_of），氣勢再加 push、池子照 a_hp／b_hp，最後叫 close_round。"""
    f, g = _fights(bout, tuning, rng, a_ratio, b_ratio)
    lines: list[str] = []
    n = bout.round + 1
    # 看不看得穿照回合開始時的狀態：自己挑招的一方這一回合的招早就送出了，這一回合才上的看穿、亂神下一回合才看得到（架勢），
    # 自動出招的一方也一樣，兩邊公平
    a_read = bout.a.status.has("看穿") or bout.b.status.has("亂神")
    b_read = bout.b.status.has("看穿") or bout.a.status.has("亂神")
    f.begin(n, edge, lines)
    g.begin(n, 100 - edge, lines)
    gam = GAMBLE in (a_move, b_move)
    f.planned = None if a_move == GAMBLE else a_move
    g.planned = None if b_move == GAMBLE else b_move
    for side in (f, g):
        if side.holders:
            _opening(side)
            _strike(side)
    out = Step(lines=lines)
    if gam:
        out.push = f.extra - g.extra
        f.dmg += sum(pct for _n, pct, _left in f.foe.dots)
        g.dmg += sum(pct for _n, pct, _left in f.us.dots)
        out.a_move = None if a_move == GAMBLE else a_move
        out.b_move = None if b_move == GAMBLE else b_move
    else:
        # 兩邊都看得穿就互相抵掉：誰都不臨時改招（不然後算的那一邊永遠贏）
        a_read, b_read = a_read and not b_read, b_read and not a_read
        b, b_self = _forced(g, b_move, b_auto, None, rng, tuning, b_read)
        a, a_self = _forced(f, a_move, a_auto, b, rng, tuning, a_read)
        if b_auto and b_read and b is not None and a is not None and not g.us.has("失神") and not g.us.has("定身"):
            allowed = _allowed(g)
            b = answer_to(a) if answer_to(a) in allowed else best_against([a], allowed)
        out.beat, out.push, out.a_hit, out.b_hit = _settle(
            f, g, a, b, a_off=a is None, b_off=b is None, a_self=a_self, b_self=b_self, base_beat=None, rng=rng)
        out.a_move, out.b_move = a, b
        out.a_mod = (f.push_mod + (1.0 if f.chain else 0.0) if a is not None else 0.0) - g.foe_cut
        out.b_mod = (g.push_mod + (1.0 if g.chain else 0.0) if b is not None else 0.0) - f.foe_cut
        f.stacks.pop("夜襲", None)
        g.stacks.pop("夜襲", None)
    out.a_hp = sum(f.hp.values()) - (0.0 if f.veiled else g.dmg)
    out.b_hp = sum(g.hp.values()) - (0.0 if g.veiled else f.dmg)
    out.a_cut, out.b_cut = toll_cut(f.holders), toll_cut(g.holders)
    if f.veiled:
        out.a_hit = False
    if g.veiled:
        out.b_hit = False
    out.lines = list(lines)  # pydantic 建 Step 時抄了一份：之後加的句子要再放回去
    return out


def pool_push(hp: float, tuning: TacticTuning) -> float:
    """沒有氣血池的那一方（頭目）掉的氣血換成氣勢（往另一方）：同一般的仗的換法（dot ÷ strike），一擊照 bout_strike。"""
    return -hp * 100 * tuning.dot / max(1e-9, tuning.strike) * tuning.bout_strike


def close_round(bout: Bout, push: float, tuning: TacticTuning, rng: random.Random) -> list[str]:
    """回合結束（氣勢推好了）：祭天疊層、兩邊的狀態少一回合。回這時候多出來的句子。"""
    f, g = _fights(bout, tuning, rng, bout.a.ctx.hp_ratio, bout.b.ctx.hp_ratio)
    lines: list[str] = []
    f.lines = g.lines = lines
    _after(f, push > 0)
    _after(g, push < 0)
    bout.a.status.tick()
    bout.b.status.tick()
    bout.round += 1
    return lines


class Locks(BaseModel):
    """下一回合這一方的選單受什麼限制、看不看得穿對手。"""

    no_moves: list[str] = Field(default_factory=list)
    no_gamble: bool = False
    sees: bool = False  # 看穿了，或對手亂神：對手的架勢一定是真的
    notes: list[str] = Field(default_factory=list)  # 身上的狀態（畫面那一行）


def locks(bout: Bout | None, side: str = "a") -> Locks:
    if bout is None:
        return Locks()
    me, him = (bout.a, bout.b) if side == "a" else (bout.b, bout.a)
    n = bout.round + 1
    out = Locks()
    if me.status.has("卸勁"):
        out.no_moves.append("強攻")
    if any(h.tactic.kind == "unbroken" and _in_span(h, n) for h in me.holders):
        out.no_moves.append("固守")
    out.no_gamble = me.status.has("亂神")
    out.sees = me.status.has("看穿") or him.status.has("亂神")
    out.notes = [f"{k}（{v} 回合）" for k, v in me.status.states.items() if v > 0 and k not in ("霧",)] + [
        f"{name}（{left} 回合）" for name, _pct, left in me.status.dots
    ]
    return out


def status_text(bout: Bout | None, side: str = "a") -> str:
    """畫面上那一行：「你身上：卸勁（1 回合）、焚身（2 回合）」；沒有狀態是空字串。"""
    notes = locks(bout, side).notes
    if not notes:
        return ""
    me = bout.a if side == "a" else bout.b
    return f"{me.status.name}身上：{'、'.join(notes)}"


def lock_note(move: str) -> str:
    """選單上灰掉的那一招後面那幾個字：卸勁出不了強攻、丈八狂瀾只攻不守出不了固守。"""
    return "・卸勁中" if move == "強攻" else "・只攻不守"


NO_MOVE = "（{move}這一回合使不出來。）"
NO_GAMBLE = "（你亂了心神，這一回合沒法放手一搏。）"
SEEN_NOTE = "（看穿了，這一招是真的。）"


def round_line(line: str, fired: list[str]) -> str:
    """頭目戰、擂台、奪璽單挑那一回合的一行：戰法的句子接在後面（每一句〔名〕開頭）。"""
    return line + ("" if not fired else "　" + "　".join(fired))


def divine_save(holders: list[Holder], rng: random.Random) -> Holder | None:
    """神上使：放手一搏失手時擲一次，中了回帶著它的那一門（失手改成功）。沒帶著不擲、不動亂數。"""
    for h in holders:
        if h.tactic.kind == "divine":
            return h if rng.random() < h.tactic.params.get("chance_pct", 0.0) else None
    return None


DIVINE_LINE = "{lead}{name}〕神上使附身，{who}這一搏失手改成了！"


def divine_line(h: Holder) -> str:
    return DIVINE_LINE.format(lead=LEAD, name=h.tactic.name, who=h.who)


# ── 決戰：沒有單一的對手，只算自己身上的（WAR_KINDS）──────────────


class War(BaseModel):
    """決戰裡一個人這一回合戰法改了什麼：份量多幾成（連環、推力加減、固守加重、援兵）、剋制係數至少 1（無隙）、
    挨的打乘多少（化影 0）、氣血池回或扣上限的幾成、這一回合發動了哪幾門（〔名〕開頭）。"""

    force: float = 1.0
    unbeaten: bool = False
    damage: float = 1.0
    hp: float = 0.0
    lines: list[str] = Field(default_factory=list)
    kinds: dict[str, str] = Field(default_factory=dict)  # 戰法名 → kind（決戰戰況把一軍的那幾句摺成一行時分類用，決戰包 features/battle/view.fold_war_lines）


def war_round(side: BoutSide, move: str | None, beat: int, round_: int, edge: float, hp_ratio: float,
              tuning: TacticTuning, rng: random.Random) -> War:
    """決戰裡一個人這一回合：move 是他出的固定招（放手一搏是 None）、beat 是他剋中對面（剋制係數 > 1 是 +1）、
    edge 是他那一邊看出去的戰局。份量的加成照 Config.tactics.war_scale 縮（一個人的份量要跟幾十個人分）。"""
    f = _Fight(side.holders, side.ctx.model_copy(update={"hp_ratio": hp_ratio}), tuning, rng, us=side.status,
               foe=Status(name="敵陣"), pending=side.pending, stacks=side.stacks, unit=1.0)
    f.war = True
    lines: list[str] = []
    f.begin(round_, edge, lines)
    f.planned = move
    _opening(f)
    _strike(f)
    chained = f.chain
    if move is not None:
        f.mine = move
        _follow(f, beat)
        _countered(f, beat < 0)
    out = War(lines=lines, unbeaten=f.flawless, kinds={h.tactic.name: h.tactic.kind for h in f.holders} if lines else {})
    if move is not None:
        more = f.push_mod + (f.guard_mod if move == "固守" else 0.0) + (1.0 if f.chain or chained else 0.0) + f.extra
        for h in f.holders:  # 斬將、墜星：出強攻推力加重（決戰裡沒有單一的對手可以定身）
            if h.tactic.kind == "assault" and move == "強攻" and _in_span(h, round_) and f.roll(f.rate(h)):
                more += h.tactic.params.get("push_pct", 0.0)
                f.say(h, "強攻加重")
        out.force = max(0.0, 1 + more * tuning.war_scale)
    out.damage = 0.0 if f.veiled else 1.0 - toll_cut(f.holders)
    out.hp = sum(f.hp.values())
    f.stacks.pop("夜襲", None)
    return out


def war_close(side: BoutSide, won: bool, tuning: TacticTuning, rng: random.Random) -> list[str]:
    """決戰裡一個人的回合結束：祭天疊層、狀態少一回合。"""
    f = _Fight(side.holders, side.ctx, tuning, rng, us=side.status, foe=Status(), pending=side.pending, stacks=side.stacks)
    f.war = True
    _after(f, won)
    side.status.tick()
    return f.lines


# ── 誰帶著哪一門 ────────────────────────────────────────


def of(content: Content, skill_id: str | None) -> TacticDef | None:
    skill = content.skills.get(skill_id) if skill_id else None
    return skill.tactic if skill is not None else None


def figure_arts(content: Content, character: CharacterDef) -> list[str]:
    """這位人物的本命武學與本命內功（FB-640）：人物表 starting_wugong／starting_neigong 裡品質是絕學的那幾門（十八位大勢人物的
    都是，各寫一個本命戰法；寫本命戰法的一定是絕學，content.check_signature_arts 擋）。歷史武將同行補的起始武學（FB-364：
    王允、華佗……）是各地教的內容武學（下品的帶小戰法、上品的什麼都不帶），不是本命：誰的都不算（figure_of）、情誼到了不教
    （companion_agent）、名帖不寫「親傳」（mingtie）；玩家照樣在各地學得到。"""
    out = []
    for skill_id in (character.starting_wugong, character.starting_neigong):
        skill = content.skills.get(skill_id) if skill_id else None
        if skill is not None and skill.quality == "絕學":
            out.append(skill_id)
    return out


def of_art(content: Content, art, level: int | None = None) -> TacticDef | None:
    """這一門帶的戰法：內容寫的（本命戰法、小戰法），或自創長出來的招（moves.move_of；level 給了照那一成算生不生）。"""
    if art is None:
        return None
    tactic = of(content, art.id)
    if tactic is not None:
        return tactic
    from . import moves  # moves 會 import create，create 會 import 這個模組

    return moves.move_of(content, art, level)


def of_id(content: Content, skill_id: str | None, world=None, level: int | None = None) -> TacticDef | None:
    """認 id 的那一種：內容裡的照 of；全服登記的（自創）查 world 算它的招。world 是 None 只認內容。"""
    if not skill_id or skill_id in content.skills or world is None:
        return of(content, skill_id)
    return of_art(content, world.get_skill(skill_id), level)


def line_of_id(content: Content, skill_id: str | None, world=None, level: int | None = None) -> str | None:
    """角色卡那一行：認 id 找招（of_id），蓋上那一門的印（title_of）。沒有招是 None。"""
    tactic = of_id(content, skill_id, world, level)
    if tactic is None:
        return None
    art = world.get_skill(skill_id) if world is not None and skill_id not in content.skills else None
    return card_text(tactic, title_of(tactic, art))


def figure_of(content: Content, skill_id: str) -> str | None:
    """這門本命武學是哪位人物的（figure_arts）；學來的武學（小戰法，同伴起始帶的那幾門也是）不是誰的，None。"""
    for ch in content.characters.values():
        if skill_id in figure_arts(content, ch):
            return ch.id
    return None


def holders_of(
    content: Content, rows: list[tuple[str, str, str | None, str | None]], world=None,
    levels: dict[str, int] | None = None, mine: dict | None = None,
) -> list[Holder]:
    """（名字, 鍵, 武學 id, 內功 id）一列一個人 → 帶著本命戰法的那幾門（武學在前）。同一門戰法兩個人都帶著時只算第一個
    （本人在前）：同一招不會一回合發兩次。給了 world 才認得自創的招（of_id）；levels 是本人那兩門練到第幾成（自創的招還生不生），
    mine 是本人那兩門自己那一份（team.player_art：破境了的自創招升為絕招）。"""
    out: list[Holder] = []
    seen: set[str] = set()
    for who, key, wugong, neigong in rows:
        for skill_id in (wugong, neigong):
            level = (levels or {}).get(skill_id) if key == PLAYER_KEY else None
            own = (mine or {}).get(skill_id) if key == PLAYER_KEY else None
            tactic = of_art(content, own, level) if own is not None else of_id(content, skill_id, world, level)
            if tactic is None or tactic.name in seen:
                continue
            seen.add(tactic.name)
            out.append(Holder(who=who, key=key, skill=skill_id, figure=figure_of(content, skill_id), tactic=tactic))
    return out
