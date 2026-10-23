"""開口求人（Joy 2026-10-23「先做看看」；設計稿 https://claude.ai/artifact/KtRz62jWShogpaXEzv2sbt；Config.parley）。

對話裡「自己說」那一句也可以是求他做事。三段式跟對話同一條（模型在鎖外）：
  A 引擎照此刻的事實列兩份清單（他做得到的事、他可以開的條件），每件事帶份量 1～3，一起放進「自己說」那一輪的提示；
  B 模型當談判者：照他的性格與處境，挑清單上的一件（或不是在求事）、評一個意願（0～100）、要不要開條件，寫答應／開條件／婉拒三版回話；
  C 引擎驗清單、照情誼與份量夾意願（天花板）、用自己的亂數擲：中了當場做，沒中有條件就是先付後做（你接了才算），沒中沒條件就婉拒。
第一批：當場做、先付後做、婉拒；五件事（帶路、並肩出陣、指點一招、給情報、贈物）；條件是交銀、交素材，或打探、討伐的委託
（同書信的委託，辦成了下回見面他兌現）。食言、先做後付、人物主動開口、同行中的自由文字是第二批。
這個模組只放純規則與字；真的去做（出發、發心得、給東西、掛委託）在 Game（engine.py 的 _parley_*）。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import atlas, bounties, calendar, figure_life, figures, materials
from .calendar import DAY
from .models import Content
from .rules import game_day
from .state import Bounty, GameState, ParleyDay

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


def ceiling(content: Content, affinity: int, weight: int, hostile: bool) -> int:
    """意願的天花板：情誼那一檔的上限，減份量、敵對再減，最低 floor。"""
    cfg = content.config.parley
    _, top = band(content, affinity)
    cut = cfg.weight_cut[max(0, min(len(cfg.weight_cut) - 1, weight - 1))]
    return max(cfg.floor, top - cut - (cfg.enemy_cut if hostile else 0))


def roll(state: GameState, cid: str) -> int:
    """引擎自己的一份亂數（不碰 Game.rng）：名號｜人物｜這一位今天第幾件｜世界秒，擲 1～100。"""
    p = state.player
    record = p.parley_days.get(cid)
    seq = record.asks if record is not None else 0
    return random.Random(f"開口|{p.name}|{cid}|{seq}|{state.world.time:.0f}").randint(1, 100)


def decide(
    content: Content, asks: list[Item], conditions: list[Item], ask_id: str | None, willing: int | None,
    condition_id: str | None, affinity: int, hostile: bool, dice: int,
) -> Decision:
    """C 段：驗模型挑的、夾意願、照骰子定結果。模型挑了清單外的事當婉拒（份量照 1 算），不在清單上的條件當沒開。"""
    if not ask_id:
        return Decision(None, None, 0, 0, None)
    by_id = {a.id: a for a in asks}
    ask = by_id.get(ask_id)
    if ask_id == REFUSE or ask is None:
        return Decision(ask or Item(ask_id, ask_id), None, 0, 0, "no")
    cond = {c.id: c for c in conditions}.get(condition_id or "")
    raw = max(0, min(100, int(willing or 0)))
    cap = ceiling(content, affinity, ask.weight, hostile)
    chance = max(content.config.parley.floor, min(raw, cap))
    if dice <= chance:
        return Decision(ask, None, raw, chance, "do")
    if cond is not None:
        return Decision(ask, cond, raw, chance, "terms")
    return Decision(ask, None, raw, chance, "no")


def prompt_block(content: Content, cid: str, asks: list[Item], conditions: list[Item], affinity: int, hostile: bool) -> str:
    """接在「自己說」那一輪 user 訊息後面的一段：兩份清單、怎麼挑、多填哪幾個欄位。情誼只給一個詞，不給數字。"""
    name = _name(content, cid)
    word, _ = band(content, affinity)
    ask_lines = "\n".join(f"- {a.id}：{a.detail}（份量 {a.weight}）" for a in asks) or "（此刻沒有）"
    cond_lines = "\n".join(f"- {c.id}：{c.detail}" for c in conditions)
    side = "；你們分屬敵對的兩方，你對他天生戒備" if hostile else ""
    return (
        f"\n【開口求人】玩家這句話如果是在求{name}做一件事，從下面「{name}此刻做得到的事」挑最貼近的一件填 ask；"
        f"只是閒聊、寒暄、請教道理，ask 留空字串。求的事不在清單上，ask 填 \"{REFUSE}\"。\n"
        f"【{name}此刻做得到的事】\n{ask_lines}\n"
        f"【{name}可以開的條件】\n{cond_lines}\n"
        f"【你們的情誼】{word}{side}。\n"
        f"willing 填 0～100：照{name}的性格、此刻的處境與心事、你們的情誼、玩家說話的方式，他「不要任何條件就答應」的意願。"
        "condition 填上面條件清單的一個 id，或留空字串：他想先要玩家做點什麼才肯答應，就開條件。份量大的事、情誼淺的人，多半要開條件。\n"
        "narrative 寫他答應時的反應；narrative_terms 寫他開條件時說的話（要說出條件）；narrative_no 寫他婉拒時的反應。"
        "三段都用第三人稱、兩三句；只寫他的反應，不寫結果的數字。系統照你給的意願擲骰，選一段給玩家看。\n"
        "JSON 多這幾個欄位：\"ask\": \"...\", \"willing\": 0, \"condition\": \"...\", \"narrative_terms\": \"...\", \"narrative_no\": \"...\""
    )


def result_line(content: Content, cid: str, decision: Decision) -> str:
    """結果那一行（江湖紀錄裡人物的話後面）。"""
    name = _name(content, cid)
    what = decision.ask.label if decision.ask is not None else ""
    if decision.kind == "do":
        return DID_LINE.format(name=name, what=what)
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
