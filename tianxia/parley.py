"""開口求人（Joy 2026-10-23「先做看看」；設計稿 https://claude.ai/artifact/KtRz62jWShogpaXEzv2sbt；Config.parley）。

對話裡「自己說」那一句也可以是求他做事。三段式跟對話同一條（模型在鎖外）：
  A 引擎照此刻的事實列兩份清單（他做得到的事、他可以開的條件），每件事帶份量 1～3，一起放進「自己說」那一輪的提示；
  B 模型當談判者：照他的性格與處境，挑清單上的一件（或不是在求事）、評一個意願（0～100）、要不要開條件，寫答應／開條件／婉拒三版回話；
  C 引擎驗清單、照情誼與份量夾意願（天花板）、用自己的亂數擲：中了當場做，沒中有條件就是先付後做（你接了才算），沒中沒條件就婉拒。
第一批：當場做、先付後做、婉拒；五件事（帶路、並肩出陣、指點一招、給情報、贈物）；條件是交銀、交素材，或打探、討伐的委託
（同書信的委託，辦成了下回見面他兌現）。
第二批：先做後付（擲中又開了條件：他先做、你欠他一件，期限內沒做到是食言）；守約紀錄與食言（情誼扣、他的盟友聽說、
每一筆還沒抵掉的食言讓天花板減 broken_cut；做到一件抵一筆）；人物主動開口（你求見他時他有心事，對話第一句就是他的請託，
接了是一件委託、做到他回報一件事）；同行中的自由文字（帶路的路上每到一站跟他說一句、陪你出陣之前跟他商量打法，
模型評成功率、引擎夾在 plan_floor～plan_cap 擲）。
這個模組只放純規則與字；真的去做（出發、發心得、給東西、掛委託）在 Game（engine.py 的 _parley_*）。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import atlas, bounties, calendar, figure_life, figures, materials
from .calendar import DAY
from .models import Content
from .rules import game_day
from .state import Bounty, GameState, ParleyDay, ParleyDebt, ParleyRecord, TalkMemo

ASK_KINDS = ("escort", "sortie", "spar", "intel", "gift")  # 第一批的五件事；ask id 是「種類」或「種類:地點」
REFUSE = "refuse"

# 待 joy 潤：引擎自己寫的那幾句
DID_LINE = "（你求{name}{what}，他答應了。）"
TERMS_LINE = "（你求{name}{what}。他開了條件：{cond}。）"
NO_LINE = "（你求{name}{what}，他沒有答應。）"
TERMS_FALLBACK = "{name}沉吟片刻：「這件事不難，你先替我{cond}。」"
NO_FALLBACK = "{name}搖了搖頭，沒有答應。"
TERMS_ACCEPT = "答應他：{cond}"
TERMS_DECLINE = "不答應"
TERMS_DECLINED = "你沒有接下{name}的條件，這件事就此作罷。"
TERMS_SHORT = "你手頭不夠，辦不到這個條件。"
OWED_BUTTON = "請{name}兌現：{what}"
OWED_DONE = "{name}記得答應過你的事。"
OWED_LATER = "{name}點了點頭：「答應你的事我記著，只是此刻辦不到，改日吧。」"
COMMISSION_OWED = "下回見到{name}，他會兌現答應你的事。"
SPAR_LINE = "{name}陪你拆了幾招，隨手點出你的破綻。"
GIFT_LINE = "{name}送了你一點東西。"
INTEL_HEAD = "（{name}說起的事：{facts}。）"
BACKING_LINE = "{name}答應今天在{region}陪你出陣一回：下一次在那一帶出陣，他的部曲與你並肩。"
BACKED_LINE = "〔{name}的部曲與你並肩，這一仗威力 +{pct}%〕"
ESCORT_LINE = "{name}親自帶你抄近路往{place}，一路不花你半分體力。"
# 第二批（待 joy 潤）
OWE_LINE = "（你求{name}{what}，他答應了，先替你做。你欠他一件：{cond}，{due}之前。）"
REPAY_BUTTON = "還{name}：{cond}"
REPAID = "你把欠{name}的還了：{cond}。"
KEPT_MEMO = "答應他的事做到了：{cond}"
BROKEN_MEMO = "答應他的事沒做到：{cond}"
BROKEN_LINE = "【食言】你答應{name}的事沒做到（{cond}），{name}情誼 -{amount}。"
HEARD_LINE = "{names}聽說你對{name}食言，情誼各 -{amount}。"
HEARD_TEXT = "聽說你答應{name}的事沒做到"
PLEA_ACCEPT = "接下：{cond}（他回報：{what}）"
PLEA_DECLINE = "不接"
PLEA_DECLINED = "你沒有接下{name}的請託。"
PLEA_TAKEN = "你接下了{name}的請託：{cond}，{due}之前。做到了，下回見到他，他兌現：{what}。"
ROAD_BUTTON = "跟{name}說…"
PLAN_BUTTON = "跟{name}商量打法…"
PLAN_HIT = "（{name}照你的打法布置：這一仗他的部曲出力加倍。）"
PLAN_MISS = "（打法沒談攏：這一仗他的部曲幫不上忙。）"


@dataclass(frozen=True)
class Item:
    """清單上的一件：id 給模型挑、label 給玩家看、weight 是份量（只有他做的事有）、detail 是給模型的說明。"""

    id: str
    label: str
    weight: int = 0
    detail: str = ""


@dataclass(frozen=True)
class Decision:
    """引擎驗完、夾完、擲完的結果。kind：do 當場做、terms 他開了條件、no 婉拒；ask 是 None 表示這一句不是在求事。"""

    ask: Item | None
    condition: Item | None
    willing: int
    chance: int
    kind: str | None


def on(content: Content) -> bool:
    return content.config.parley.enabled


def day_of(state: GameState, content: Content, cid: str) -> ParleyDay:
    """這位人物今天的開口紀錄（換日就重來，不存回去：要記的呼叫端自己寫進 parley_days）。"""
    today = game_day(content, state.world)
    record = state.player.parley_days.get(cid)
    return record if record is not None and record.day == today else ParleyDay(day=today)


def touch(state: GameState, content: Content, cid: str) -> ParleyDay:
    record = day_of(state, content, cid)
    state.player.parley_days[cid] = record
    return record


def asks_left(state: GameState, content: Content, cid: str) -> int:
    return max(0, content.config.parley.asks_per_day - day_of(state, content, cid).asks)


def _name(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def _place(content: Content, loc: str) -> str:
    return content.locations[loc].name if loc in content.locations else loc


def region_of(state: GameState, content: Content, cid: str) -> str | None:
    return figure_life._region(content, figure_life.where(state, content, cid))


def enemy(state: GameState, content: Content, cid: str, side: str | None) -> bool:
    """你跟他是不是敵對的兩方：交戰兩軍、各站一邊才算（散人、豪強、站中立的人物都不算）。"""
    his = figure_life.side_of(content, cid)
    return side is not None and his is not None and bounties.ENEMY.get(side) == his


def can_leave(state: GameState, content: Content) -> bool:
    """跟他上路走不走得了：交談中本來就擋著前往（atlas.travel_block），帶路是談完就走，所以不看交談這一條。"""
    p = state.player
    talking, p.pending_companion = p.pending_companion, None
    try:
        return atlas.travel_block(state, content) is None
    finally:
        p.pending_companion = talking


def _escort_places(state: GameState, content: Content, cid: str) -> list[Item]:
    """帶路的目的地：他那一區的地點與他常去的地方，走得到的、不是這裡的，近的先，最多 escort_places 個。
    同一區份量 1、跨區 2。設伏守著、序章、在路上這類走不了的時候（atlas.travel_block）一個都沒有。"""
    if state.player.journey is not None or not can_leave(state, content):
        return []
    here = state.player.location
    region = region_of(state, content, cid)
    ch = content.characters.get(cid)
    pool = list(atlas.region_locations(content, region)) if region else []
    for loc in (ch.haunts if ch is not None else []):
        if loc not in pool:
            pool.append(loc)
    found: list[tuple[float, Item]] = []
    for loc in pool:
        if loc == here or loc not in content.locations or content.locations[loc].prologue_only:
            continue
        route = atlas.way_to(state, content, loc)
        if route is None:
            continue
        loc_region = figure_life._region(content, loc)
        here_region = figure_life._region(content, here)
        weight = 1 if loc_region is not None and loc_region == here_region else 2
        found.append((route.minutes, Item(f"escort:{loc}", f"帶路到{_place(content, loc)}", weight,
                                          f"親自帶玩家走到{_place(content, loc)}（{'同一帶' if weight == 1 else '跨區'}）")))
    found.sort(key=lambda x: x[0])
    return [item for _, item in found[: content.config.parley.escort_places]]


def intel_facts(state: GameState, content: Content, cid: str) -> list[str]:
    """給情報講的事：跟他敵對的大勢人物（他沒站邊就是全部）此刻在哪、心事如何，他那一區的先、最多 intel_count 件。
    只講公開得到的事實（人物在哪、心事）；誰在哪裡設伏永遠不講。"""
    side = figure_life.side_of(content, cid)
    foe = bounties.ENEMY.get(side or "")
    region = region_of(state, content, cid)
    rows: list[tuple[int, str]] = []
    for fid, fig in content.figures.items():
        if fig.character == cid or (foe is not None and fig.faction != foe):
            continue
        now = figures.state_of(state, content, fid)
        if now.status != "active" or now.location not in content.locations:
            continue
        mood = figures.mood_of(state, content, fid)
        name = _name(content, fig.character) if fig.character else fid
        text = f"{name}在{_place(content, now.location)}" + (f"，{mood}" if mood else "")
        near = 0 if figure_life._region(content, now.location) == region else 1
        rows.append((near, text))
    rows.sort(key=lambda x: x[0])
    return [text for _, text in rows[: content.config.parley.intel_count]]


def ask_items(state: GameState, content: Content, cid: str, side: str | None, can_sortie: bool) -> list[Item]:
    """他此刻做得到的事（模型只能從這裡挑）。今天婉拒過的、今天指點過的不列；can_sortie 是呼叫端算的「這個人出得了陣」。"""
    record = day_of(state, content, cid)
    name = _name(content, cid)
    items = list(_escort_places(state, content, cid))
    his = figure_life.side_of(content, cid)
    region = region_of(state, content, cid)
    backing = state.player.parley_backing
    backed = backing is not None and backing.day == game_day(content, state.world)
    if can_sortie and his is not None and his == side and region is not None and not backed:
        items.append(Item("sortie", f"陪你出陣（{_region_name(content, region)}一帶）", 2,
                          f"今天在{_region_name(content, region)}一帶陪玩家出陣一回，他的部曲同列"))
    if not record.spar:
        items.append(Item("spar", "指點一招", 1, f"跟玩家過幾招、點出破綻（{name}親自出手，不傷人）"))
    facts = intel_facts(state, content, cid)
    if facts:
        items.append(Item("intel", "說說敵情", 1, "把這些事告訴玩家：" + "；".join(facts)))
    items.append(Item("gift", "贈點東西", 1, "從手頭給玩家一點素材或銀兩"))
    return [item for item in items if item.id not in record.refused]


def _region_name(content: Content, region: str | None) -> str:
    found = next((r for r in content.map.regions if r.id == region), None) if region else None
    return found.name if found is not None else "這"


def condition_items(state: GameState, content: Content, cid: str, rng: random.Random) -> list[Item]:
    """他可以開的條件（模型只能從這裡挑；大小照你求的那件事的份量，在 condition_text 定）。交素材要你身上有三份同一樣一階素材；
    打探、討伐挑他那一區的地方（討伐只有交戰兩軍的人物開得出來）。"""
    w = state.world
    items = [Item("silver", "交一筆銀兩", detail="玩家交銀兩給他（數目系統定）")]
    need = content.config.parley.material_terms
    held = [(materials.held(state, m.id), m.id) for m in materials.by_tier(content, 1)]
    held = [x for x in held if x[0] >= need]
    if held:
        held.sort(key=lambda x: (-x[0], x[1]))
        items.append(Item(f"material:{held[0][1]}", f"交三份{content.materials[held[0][1]].name}",
                          detail=f"玩家交 {need} 份{content.materials[held[0][1]].name}給他"))
    region = region_of(state, content, cid)

    def near(loc_id: str) -> bool:
        return region is None or figure_life._region(content, loc_id) == region

    scouts = [loc_id for loc_id, loc in content.locations.items()
              if loc.danger >= 2 and not bounties.is_town(content, loc_id) and bounties._opened(loc, w) and near(loc_id)
              and loc_id != state.player.location]  # 叫你打探你正站著的地方沒有意思
    if scouts:
        loc = rng.choice(sorted(scouts))
        items.append(Item(f"scout:{loc}", f"替他打探{_place(content, loc)}", detail=f"玩家先去{_place(content, loc)}探索一回"))
    side = figure_life.side_of(content, cid)
    if side in bounties.ENEMY:
        strikes = sorted(x for x in bounties._strike_spots(content, w, side, set()) if near(x[0]))
        if strikes:
            loc, squad = rng.choice(strikes)
            items.append(Item(f"strike:{loc}:{squad}", f"替他討伐{_place(content, loc)}",
                              detail=f"玩家先去{_place(content, loc)}打贏一場對頭的隊伍"))
    return items


def condition_text(content: Content, condition: Item, weight: int) -> str:
    """條件給玩家看的那一句（交銀照份量定價）。"""
    if condition.id == "silver":
        return f"交 {silver_of(content, weight)} 兩銀子"
    return condition.label


def silver_of(content: Content, weight: int) -> int:
    terms = content.config.parley.silver_terms
    return terms[max(0, min(len(terms) - 1, weight - 1))]


def band(content: Content, affinity: int) -> tuple[str, int]:
    """情誼落在哪一檔：（那一檔的說法，意願的天花板）。"""
    cfg = content.config.parley
    word, top = cfg.band_words[0], cfg.bands[0][1]
    for i, (low, cap) in enumerate(cfg.bands):
        if affinity >= low:
            word, top = cfg.band_words[min(i, len(cfg.band_words) - 1)], cap
    return word, top


def ceiling(content: Content, affinity: int, weight: int, hostile: bool, broken: int = 0) -> int:
    """意願的天花板：情誼那一檔的上限，減份量、敵對再減、每一筆還沒抵掉的食言（broken，見 broken_of）再減，最低 floor。"""
    cfg = content.config.parley
    _, top = band(content, affinity)
    cut = cfg.weight_cut[max(0, min(len(cfg.weight_cut) - 1, weight - 1))]
    return max(cfg.floor, top - cut - (cfg.enemy_cut if hostile else 0) - cfg.broken_cut * broken)


def roll(state: GameState, cid: str) -> int:
    """引擎自己的一份亂數（不碰 Game.rng）：名號｜人物｜這一位今天第幾件｜世界秒，擲 1～100。"""
    p = state.player
    record = p.parley_days.get(cid)
    seq = record.asks if record is not None else 0
    return random.Random(f"開口|{p.name}|{cid}|{seq}|{state.world.time:.0f}").randint(1, 100)


def decide(
    content: Content, asks: list[Item], conditions: list[Item], ask_id: str | None, willing: int | None,
    condition_id: str | None, affinity: int, hostile: bool, dice: int, broken: int = 0, can_owe: bool = False,
) -> Decision:
    """C 段：驗模型挑的、夾意願、照骰子定結果。模型挑了清單外的事當婉拒（份量照 1 算），不在清單上的條件當沒開。
    擲中：沒開條件當場做；開了條件、而且還能欠他（can_owe，見 can_owe）是先做後付（owe），不能欠就變成先付後做（terms）。
    沒中：開了條件是先付後做，沒開是婉拒。"""
    if not ask_id:
        return Decision(None, None, 0, 0, None)
    by_id = {a.id: a for a in asks}
    ask = by_id.get(ask_id)
    if ask_id == REFUSE or ask is None:
        return Decision(ask or Item(ask_id, ask_id), None, 0, 0, "no")
    cond = {c.id: c for c in conditions}.get(condition_id or "")
    raw = max(0, min(100, int(willing or 0)))
    cap = ceiling(content, affinity, ask.weight, hostile, broken)
    chance = max(content.config.parley.floor, min(raw, cap))
    if dice <= chance and cond is not None:
        return Decision(ask, cond, raw, chance, "owe" if can_owe else "terms")
    if dice <= chance:
        return Decision(ask, None, raw, chance, "do")
    if cond is not None:
        return Decision(ask, cond, raw, chance, "terms")
    return Decision(ask, None, raw, chance, "no")


# 這三種輪次模型一定要寫出來的欄位（寫進送出去的 schema 的 required，空字串照樣算答了；companion_agent.generate_turn）。
# CompanionTurn 的這些欄位都有預設值 None，不寫進 schema 的話模型可以整個略過（2026-10-24 主機實測：ask 空白 14/30、
# 商量打法 willing 沒填 4/30）。只有那一輪帶了對應的提示才要，平常的閒聊不要
ASK_FIELDS = ("ask", "willing", "condition", "narrative_terms", "narrative_no")
PLAN_FIELDS = ("willing", "narrative_no")
PLEA_FIELDS = ("want", "reward")


def prompt_block(content: Content, cid: str, asks: list[Item], conditions: list[Item], affinity: int, hostile: bool) -> str:
    """接在「自己說」那一輪 user 訊息後面的一段：兩份清單、怎麼挑、多填哪幾個欄位。情誼只給一個詞，不給數字。"""
    name = _name(content, cid)
    word, _ = band(content, affinity)
    ask_lines = "\n".join(f"- {a.id}：{a.detail}（份量 {a.weight}）" for a in asks) or "（此刻沒有）"
    cond_lines = "\n".join(f"- {c.id}：{c.detail}" for c in conditions)
    side = "；你們分屬敵對的兩方，你對他天生戒備" if hostile else ""
    return (
        f"\n【開口求人】先判斷玩家這句話是不是在求{name}做一件事，結果一定要填在 ask：是在求事，就從下面「{name}此刻做得到的事」"
        f"挑最貼近的一件，把它的 id 原樣填進 ask（例：要他帶路去某地，就填那個地方的 escort id）；"
        f"只是閒聊、寒暄、請教道理，ask 填空字串；求的事不在清單上，ask 填 \"{REFUSE}\"。"
        f"ask 只管玩家求的是什麼，跟{name}要不要開條件無關：就算他要先開條件，ask 也照樣填玩家求的那件事。\n"
        f"【{name}此刻做得到的事】\n{ask_lines}\n"
        f"【{name}可以開的條件】\n{cond_lines}\n"
        f"【你們的情誼】{word}{side}。\n"
        f"willing 填 0～100：照{name}的性格、此刻的處境與心事、你們的情誼、玩家說話的方式，他「不要任何條件就答應」的意願。"
        f"condition 填上面「{name}可以開的條件」的一個 id，或空字串：他想先要玩家做點什麼才肯答應，就開條件。份量大的事、情誼淺的人，多半要開條件。"
        f"condition 只能是條件清單上的 id 或空字串，不能填 \"{REFUSE}\"（婉拒是系統照 willing 擲骰決定的）。\n"
        "narrative 寫他答應時的反應；narrative_terms 寫他開條件時說的話（要說出條件）；narrative_no 寫他婉拒時的反應。"
        "三段都用第三人稱、兩三句；只寫他的反應，不寫結果的數字。系統照你給的意願擲骰，選一段給玩家看。\n"
        "JSON 一定要多這五個欄位，一個都不能省：\"ask\": \"...\", \"willing\": 0, \"condition\": \"...\", \"narrative_terms\": \"...\", \"narrative_no\": \"...\""
    )


def result_line(content: Content, cid: str, decision: Decision, due: str = "") -> str:
    """結果那一行（江湖紀錄裡人物的話後面）。"""
    name = _name(content, cid)
    what = decision.ask.label if decision.ask is not None else ""
    if decision.kind == "do":
        return DID_LINE.format(name=name, what=what)
    if decision.kind == "owe" and decision.condition is not None:
        return OWE_LINE.format(name=name, what=what, cond=condition_text(content, decision.condition, decision.ask.weight), due=due or "期限")
    if decision.kind == "terms" and decision.condition is not None:
        return TERMS_LINE.format(name=name, what=what, cond=condition_text(content, decision.condition, decision.ask.weight))
    return NO_LINE.format(name=name, what=what)


def commission(state: GameState, content: Content, cid: str, condition: Item, ask: Item, seq: int) -> Bounty | None:
    """打探、討伐的條件掛成一件委託（同書信的委託：只在你身上、照懸賞榜交差）；辦成了他欠你 ask 那一件（bounties._complete_commission）。"""
    kind, _, rest = condition.id.partition(":")
    w = state.world
    tuning = content.config.figure_life
    side = figure_life.side_of(content, cid)
    spec: dict
    if kind == "scout":
        spec = {"kind": "scout", "location": rest}
    elif kind == "strike":
        loc, _, squad = rest.partition(":")
        spec = {"kind": "strike", "location": loc, "squad": squad}
    else:
        return None
    return Bounty(
        id=f"c{seq}", faction=side if side in bounties.ENEMY else None,
        week=calendar.point(w.time, content, w).week,
        expires=w.time + tuning.commission_days * DAY,
        silver=0, deeds=0, figure=cid, motive="委託", parley_ask=ask.id, **spec,
    )


def ask_label(content: Content, ask_id: str) -> str:
    """欠你的那一件給玩家看的字（兌現的鈕）。"""
    kind, _, rest = ask_id.partition(":")
    if kind == "escort":
        return f"帶路到{_place(content, rest)}"
    return {"sortie": "陪你出陣", "spar": "指點一招", "intel": "說說敵情", "gift": "贈點東西"}.get(kind, ask_id)


# ── 第二批：守約、食言、人物主動開口、同行中的自由文字 ────────────


def record(state: GameState, cid: str) -> ParleyRecord:
    """這位人物的守約紀錄（沒有就開一份記上）。"""
    return state.player.parley_records.setdefault(cid, ParleyRecord())


def broken_of(state: GameState, cid: str) -> int:
    """他那邊天花板要扣幾筆：還沒抵掉的食言加上聽說的。"""
    found = state.player.parley_records.get(cid)
    return 0 if found is None else found.owing + len(found.heard)


def can_owe(state: GameState, content: Content, cid: str) -> bool:
    """他肯不肯先做後付：你在他這裡沒有欠著、沒有沒答覆的條件、也還沒欠滿 owe_limit 位。"""
    p = state.player
    return cid not in p.parley_debts and cid not in p.parley_terms and len(p.parley_debts) < content.config.parley.owe_limit


def due_of(state: GameState, content: Content, weight: int) -> float:
    """條件的期限（世界秒）：照委託的遊戲日數，份量 3 多 heavy_days 天。"""
    days = content.config.figure_life.commission_days + (content.config.parley.heavy_days if weight >= 3 else 0)
    return state.world.time + days * DAY


def due_text(state: GameState, content: Content, due: float) -> str:
    return calendar.stamp_text(due, content, state.world)


def _memo(state: GameState, cid: str, text: str) -> None:
    """兌現、交差、食言時由引擎寫一句事實進「上回談了什麼」（不重做那一套，只蓋過最新的一句）。"""
    state.player.talk_memos[cid] = TalkMemo(text=text, at=state.world.time, place=state.player.location or "")


def keep(state: GameState, content: Content, cid: str, cond: str) -> None:
    """做到了一件答應他的事：守約 +1，先抵一筆自己的食言、沒有就抵一筆聽說的。"""
    found = record(state, cid)
    found.kept += 1
    if found.owing:
        found.owing -= 1
    elif found.heard:
        found.heard.pop(0)
    _memo(state, cid, KEPT_MEMO.format(cond=cond))


def _break(state: GameState, content: Content, cid: str, debt: ParleyDebt, cond: str) -> list[str]:
    """食言：情誼扣（先做後付扣得多）、紀錄記一筆、他的盟友聽說（情誼各扣、記一筆聽說、多一句風聞）。"""
    from . import relations  # noqa: PLC0415  relations 只 import models、state

    p, cfg = state.player, content.config.parley
    name = _name(content, cid)
    amount = cfg.owe_broken if debt.kind == "owe" else cfg.plea_broken
    p.affinities[cid] = max(0, p.affinities.get(cid, 0) - amount)
    found = record(state, cid)
    found.broken += 1
    found.owing += 1
    _memo(state, cid, BROKEN_MEMO.format(cond=cond))
    msgs = [BROKEN_LINE.format(name=name, cond=cond, amount=amount)]
    told = []
    for ally in relations.allies(content, cid):
        if ally not in content.characters:
            continue
        p.affinities[ally] = max(0, p.affinities.get(ally, 0) - cfg.heard_broken)
        record(state, ally).heard.append(cid)
        notes = p.hearsay.setdefault(ally, [])
        notes.append(HEARD_TEXT.format(name=name))
        del notes[:-content.config.figure_life.hearsay_keep]
        told.append(_name(content, ally))
    if told and cfg.heard_broken:
        msgs.append(HEARD_LINE.format(names="、".join(told), name=name, amount=cfg.heard_broken))
    return msgs


def _cond_label(content: Content, condition: str) -> str:
    kind, _, rest = condition.partition(":")
    if kind == "material":
        return f"交三份{content.materials[rest].name}" if rest in content.materials else "交三份素材"
    if kind in ("scout", "strike"):
        loc = rest.partition(":")[0]
        return f"替他{'打探' if kind == 'scout' else '討伐'}{_place(content, loc)}"
    return "交一筆銀兩"


def debt_text(content: Content, debt: ParleyDebt) -> str:
    """欠他的那一件給玩家看的字（交銀照份量寫數目）。"""
    return condition_text(content, Item(debt.condition, _cond_label(content, debt.condition)), debt.weight)


def lapse(state: GameState, content: Content) -> list[str]:
    """同步時叫（Game.sync）：過了期限還沒做到的欠，一件一件算食言；附的委託一起作罷。"""
    p = state.player
    msgs: list[str] = []
    for cid, debt in list(p.parley_debts.items()):
        if debt.due > state.world.time:
            continue
        del p.parley_debts[cid]
        for letter in p.letters:
            if letter.task is not None and letter.task.id == debt.task:
                letter.lapsed = letter.read = True
        msgs += _break(state, content, cid, debt, debt_text(content, debt))
    return msgs


def forsake_all(state: GameState, content: Content) -> list[str]:
    """叛投：欠著的全部當場算食言（接了又走人）。"""
    msgs: list[str] = []
    for cid, debt in list(state.player.parley_debts.items()):
        debt.due = state.world.time
    msgs += lapse(state, content)
    return msgs


def settle_task(state: GameState, content: Content, task_id: str, cid: str | None) -> bool:
    """一件委託辦成了（bounties._complete_commission）：是欠他的那一件就清掉、記一筆守約；回 True 表示是開口求人的委託。"""
    p = state.player
    if cid is None:
        return False
    debt = p.parley_debts.get(cid)
    if debt is not None and debt.task == task_id:
        del p.parley_debts[cid]
        keep(state, content, cid, debt_text(content, debt))
        return True
    return False


def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """對話提示多的一行（companion_agent.build_system_prompt）：守約紀錄。開關關著、還沒有任何紀錄是空的。"""
    if not on(content):
        return ""
    found = state.player.parley_records.get(cid)
    if found is None or not (found.promised or found.broken or found.heard):
        return ""
    name = _name(content, cid)
    parts = [f"玩家答應過{name} {found.promised} 件事，做到 {found.kept} 件"]
    if found.broken:
        parts.append(f"食言 {found.broken} 件")
    heard = [_name(content, other) for other in dict.fromkeys(found.heard)]
    if heard:
        parts.append(f"{name}聽說玩家答應{'、'.join(heard)}的事沒做到")
    return f"【守約紀錄】{'，'.join(parts)}。（他會因此信或不信玩家，可以自然地提起）\n"


def pleading(state: GameState, content: Content, cid: str) -> str | None:
    """他此刻有沒有事要求你：心事在 plea_moods 裡、今天還沒開口求過、你跟他之間沒有沒了的事。回他的心事，或 None。"""
    p = state.player
    if not on(content) or day_of(state, content, cid).plea:
        return None
    if cid in p.parley_debts or cid in p.parley_terms or cid in p.parley_owed or len(p.parley_debts) >= content.config.parley.owe_limit:
        return None
    mood = figure_life.mood_any(state, content, cid)
    return mood if mood in content.config.parley.plea_moods else None


def wants(state: GameState, content: Content, cid: str, rng: random.Random) -> list[Item]:
    """他想請你做的事（打探、討伐，跟條件清單同一套地點）：打探份量 1、討伐 2；最多 plea_wants 件。"""
    found = []
    for item in condition_items(state, content, cid, rng):
        kind = item.id.partition(":")[0]
        if kind == "scout":
            found.append(Item(item.id, item.label, 1, item.detail.replace("玩家先去", "玩家去")))
        elif kind == "strike":
            found.append(Item(item.id, item.label, 2, item.detail.replace("玩家先去", "玩家去")))
    return found[: content.config.parley.plea_wants]


def plea_prompt(content: Content, cid: str, mood: str, wanted: list[Item], rewards: list[Item]) -> str:
    """他主動開口那一輪（求見的開場）接在提示後面的一段：要他挑一件請託、挑一件回報，開場那段話就是他開口相求。"""
    name = _name(content, cid)
    want_lines = "\n".join(f"- {w.id}：{w.detail}（份量 {w.weight}）" for w in wanted)
    reward_lines = "\n".join(f"- {r.id}：{r.detail}（份量 {r.weight}）" for r in rewards)
    return (
        f"\n【{name}有求於玩家】{name}此刻{mood}，玩家剛好來見他。如果照他的性格與處境，他會開口請玩家幫忙，"
        f"就從「{name}想請玩家做的事」挑一件填 want，再從「{name}可以回報的事」挑一件填 reward（份量不能比 want 大）；"
        f"narrative 就寫他開口請託的話（說出要玩家做什麼、事成之後怎麼回報），不寫數字。他不想求人，want 留空字串，照平常開場。\n"
        f"【{name}想請玩家做的事】\n{want_lines}\n"
        f"【{name}可以回報的事】\n{reward_lines}\n"
        "JSON 一定要多這兩個欄位（不求人就都填空字串）：\"want\": \"...\", \"reward\": \"...\""
    )


def plea_pick(wanted: list[Item], rewards: list[Item], want_id: str | None, reward_id: str | None) -> tuple[Item, Item] | None:
    """C 段驗他主動開口挑的：請託在清單上、回報在清單上而且份量不比請託大；不成立就當他沒開口。"""
    want = {w.id: w for w in wanted}.get((want_id or "").strip())
    reward = {r.id: r for r in rewards}.get((reward_id or "").strip())
    if want is None or reward is None or reward.weight > want.weight:
        return None
    return want, reward


def road_items(asks: list[Item]) -> list[Item]:
    """帶路的路上求得到的事：只有沿路做得到的（指點、說說敵情、贈物）。"""
    return [a for a in asks if a.id in ("spar", "intel", "gift")]


def plan_prompt(content: Content, cid: str, region: str | None) -> str:
    """出陣前跟他商量打法（同放手一搏）：模型只評成功率、寫成敗兩版。接在「自己說」那一輪後面。"""
    name = _name(content, cid)
    return (
        f"\n【商量打法】{name}今天答應在{_region_name(content, region)}一帶陪玩家出陣一回，玩家這一句是他想好的打法。"
        f"照{name}的性格、用兵的眼光與這一帶的情勢，判斷這個打法成功的機會，填 willing（0～100）。"
        f"narrative 寫打法成了、{name}怎麼配合（兩三句）；narrative_no 寫打法不成、{name}怎麼否決或怎麼落空（兩三句）。"
        "ask 留空字串。系統照你給的機會擲骰，選一段給玩家看。"
        "JSON 一定要多這兩個欄位：\"willing\": 0, \"narrative_no\": \"...\""
    )


def plan_roll(state: GameState, cid: str) -> int:
    """商量打法的骰（不碰 Game.rng）：名號｜人物｜世界秒。"""
    return random.Random(f"打法|{state.player.name}|{cid}|{state.world.time:.0f}").randint(1, 100)
