"""行狀（玩家傳第一批，企劃者 2026-10-12：「我要記錄玩家在大戰的行動還有一些值得紀錄的日常活動尤其跟每個歷史人物的對話互動，
然後最後賽季結束時凝結成一個XX（玩家名）傳」）。

江湖紀錄只留 30 則、戰報 20 場、每位人物的對話 40 則，季末湊不出一整季，所以另記一份：PlayerState.annals，一則一件事
（AnnalEntry：種類、時刻、地點、人物、一句事實、你說的那一句與他回的那一句、份量）。超過 Config.biography.cap 就先丟輕的。

兩種記法：
- note：有話可說的地方直接記（決戰收場、對話、挑戰本人、頭目戰、截殺、首創、絕學定名、奇遇、伏筆揭曉、名將贈禮）；
- watch：每個動作結束時（Game._log）拿幾樣狀態跟上一次看到的比（PlayerState.annals_mark），變了的記一筆——投靠、叛投、拜師、
  晉升、等級、遊俠名號、同伴、寶物名駒名器、情誼跨格、本命武學、練成絕學。這些改的地方散在十幾個模組裡，一個一個去掛容易漏。

只記、不改任何數值，不碰 Game.rng。假人照樣記（跟真人看不出差別）。開關是 Config.biography.enabled，不掛第一季開關。
"""
from __future__ import annotations

from .calendar import stamp_text
from .models import Content
from .state import AnnalEntry, GameState

SHOWDOWN, FIGURE, FIGHT, DEED = "showdown", "figure", "fight", "deed"
KINDS = {SHOWDOWN: "大戰", FIGURE: "人物", FIGHT: "交手", DEED: "行事"}  # 行狀頁的小標（待 joy 潤）
TEXT_MAX, QUOTE_MAX, REPLY_MAX = 80, 40, 80
MASTERED = "絕學"  # martial_arts.QUALITIES 的最後一品


def on(content: Content) -> bool:
    return content.config.biography.enabled


def clip(text: str, limit: int) -> str:
    """去掉換行與頭尾空白，超過 limit 字就截斷、補一個「…」。"""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def first_sentence(text: str, limit: int = REPLY_MAX) -> str:
    """人物回的那一段話挑頭一兩句：到第一個句號、問號、驚嘆號（含引號收尾）為止，不夠長再接一句，最後照 limit 截。"""
    text = " ".join(str(text).split())
    out = ""
    for ch in text:
        out += ch
        if ch in "。！？」" and len(out) >= 12:
            break
    return clip(out, limit)


def note(
    state: GameState, content: Content, kind: str, text: str, weight: int, *,
    figure: str = "", quote: str = "", reply: str = "", place: str | None = None, time: float | None = None,
) -> None:
    """記一則行狀。place 沒給就是人此刻所在的地點；time 沒給就是此刻的世界時間（決戰收場給收場那一刻）。"""
    if not on(content) or not text:
        return
    state.player.annals.append(entry(state, content, kind, text, weight, figure=figure, quote=quote, reply=reply, place=place, time=time))
    trim(state, content)


def entry(
    state: GameState, content: Content, kind: str, text: str, weight: int, *,
    figure: str = "", quote: str = "", reply: str = "", place: str | None = None, time: float | None = None,
    season=True,
) -> AnnalEntry:
    """寫好一則（note 用它，不記進行狀）。season 是 False 時時刻照舊的寫法（上一季的事，這一季的季曆對不上）。"""
    p, w = state.player, state.world
    when = w.time if time is None else time
    if place is None:
        loc = content.locations.get(p.location)
        place = loc.name if loc is not None and p.journey is None else ""
    return AnnalEntry(
        kind=kind, time=when, when=stamp_text(when, content, w if season else None), place=place, figure=figure,
        text=clip(text, TEXT_MAX), quote=clip(quote, QUOTE_MAX), reply=clip(reply, REPLY_MAX), weight=max(1, min(5, weight)),
    )


def profile(state: GameState, content: Content) -> dict:
    """收季時這個人的身家（存進 biographies.profile，季末寫傳時當開頭與結尾的材料）。不讀季的狀態：換季那一刻 state.world 不一定是那一季的。"""
    from . import ranger, renown

    p = state.player
    sect = content.sects.get(p.sect) if p.sect else None
    return {
        "name": p.name,
        "faction": content.scenario.faction_name(p.faction, "") if p.faction else "",
        "sect": sect.name if sect is not None else "",
        "rank": p.rank,
        "level": p.member.level,
        "fame": p.stats.get("fame", 0),
        "good": p.stats.get("good", 0),
        "evil": p.stats.get("evil", 0),
        "ranger": ranger.title(content, state) or renown.virtue_title(state, content) or "",  # 名聲開著時寫善惡稱號
        "team": [figure_name(content, cid) for cid in p.team],
        "showdowns": p.showdowns,
        "top_merits": p.top_merits,
        "bounties": p.bounties_done,
        "start": content.scenario.start_location,
        "place": (content.locations[p.location].name if p.location in content.locations else ""),
    }


def trim(state: GameState, content: Content) -> None:
    """超過上限就丟：份量最輕的先丟，同份量丟最早的。剩下的照時間排好（同一刻照記的先後）。"""
    annals, cap = state.player.annals, content.config.biography.cap
    while len(annals) > cap:
        drop = min(range(len(annals)), key=lambda i: (annals[i].weight, annals[i].time, i))
        del annals[drop]


def figure_name(content: Content, figure: str) -> str:
    ch = content.characters.get(figure)
    return ch.name if ch is not None else figure


# ── 看狀態的變化（watch）──────────────────────────────


def _notable(item) -> bool:
    """哪些裝備值得寫：寶物、良駒名駒（二階以上的馬）、名器（照隱藏配方打的）、神器的原品。"""
    return (item.slot == "treasure" or (item.slot == "mount" and item.tier >= 2) or bool(item.secret)
            or item.named_entry is not None or item.original)  # 四階擲出的名器也算（正式季整合 5.2）


def _gear(state: GameState) -> dict[str, str]:
    p = state.player
    items = [p.weapon, p.armor, p.mount, p.treasure, *p.rack, *p.held_gear]
    return {item.id: item.name for item in items if item is not None and _notable(item)}


def mark(state: GameState, content: Content) -> dict:
    """此刻要盯著的幾樣狀態（存進 PlayerState.annals_mark，下一次拿來比）。只放 JSON 存得下的東西。"""
    from . import ranger  # ranger 不 import 這裡；延後 import 免得 engine 載入順序繞圈

    p = state.player
    history = p.dialogue_history
    return {
        "faction": p.faction,
        "sect": p.sect,
        "rank": p.rank,
        "level": p.member.level,
        "ranger": ranger.title(content, state) or "",
        "team": list(p.team),
        "gear": _gear(state),
        "aff": {cid: v for cid, v in p.affinities.items() if cid in content.characters},
        "talked": sorted(cid for cid, h in history.items() if len(h) > p.history_start.get(cid, 0)),
        "taught": sorted(f.split(":", 1)[1] for f in p.flags if f.startswith("學會本命:")),
        "mastered": sorted(a for a, q in p.art_quality.items() if q == MASTERED),
    }


def watch(state: GameState, content: Content, art_name=None) -> None:
    """拿此刻的狀態跟上一次看到的比，變了的各記一筆，再把此刻的記下來。第一次（annals_mark 是 None）只記下來。
    art_name 是「武學 id → 給人看的名字」（Game 傳 team.resolve_art 的那一層；沒給就寫 id）。"""
    if not on(content):
        return
    p = state.player
    now = mark(state, content)
    before = p.annals_mark
    p.annals_mark = now
    if before is None:
        return
    cfg = content.config.biography
    scenario = content.scenario
    if now["faction"] != before.get("faction") and now["faction"] is not None:
        name = scenario.faction_name(now["faction"], now["faction"])
        if before.get("faction") is None:
            note(state, content, DEED, f"投靠{name}。", 4)
        else:
            old = scenario.faction_name(before["faction"], before["faction"])
            note(state, content, DEED, f"離開{old}，叛投{name}。", 5)
    if now["sect"] != before.get("sect") and now["sect"] is not None:
        sect = content.sects.get(now["sect"])
        note(state, content, DEED, f"拜入{sect.name if sect is not None else now['sect']}門下。", 4)
    if now["rank"] > before.get("rank", 0):
        from . import ranks

        head = ranks.title(content, state)
        note(state, content, DEED, f"晉升，受任{head}。" if head else "在陣營裡晉升了一階。", 4)
    step = cfg.level_every
    old_level = before.get("level", now["level"])
    for level in range(old_level + 1, now["level"] + 1):
        if level % step == 0:
            note(state, content, DEED, f"武藝精進，到了第 {level} 級。", 2 if level % (step * 2) else 3)
    if now["ranger"] and now["ranger"] != before.get("ranger"):
        note(state, content, DEED, f"江湖上開始稱你「{now['ranger']}」。", 3)
    for cid in now["team"]:
        if cid not in before.get("team", []) and cid in content.characters:
            note(state, content, FIGURE, f"{figure_name(content, cid)}願意跟你同行。", 4, figure=cid)
    for item_id, name in now["gear"].items():
        if item_id not in before.get("gear", {}):
            note(state, content, DEED, f"得到【{name}】。", 3)
    old_aff = before.get("aff", {})
    for cid, value in now["aff"].items():
        was = old_aff.get(cid, 0)
        crossed = [m for m in cfg.affinity_marks if was < m <= value]
        name = figure_name(content, cid)
        if crossed:
            top = crossed[-1]
            note(state, content, FIGURE, f"跟{name}的情誼到了 {top}。", 3 if top >= 60 else 2, figure=cid)
        elif was - value >= cfg.affinity_drop:
            note(state, content, FIGURE, f"跟{name}的情誼一下子冷了 {was - value}。", 3, figure=cid)
    for cid in now["talked"]:
        if cid not in before.get("talked", []) and cid in content.characters:
            note(state, content, FIGURE, f"第一次跟{figure_name(content, cid)}說上話。", 2, figure=cid)
    for cid in now["taught"]:
        if cid not in before.get("taught", []) and cid in content.characters:
            note(state, content, FIGURE, f"{figure_name(content, cid)}把本命武學傳給了你。", 4, figure=cid)
    for art in now["mastered"]:
        if art not in before.get("mastered", []):
            note(state, content, DEED, f"把【{art_name(art) if art_name else art}】練成了絕學。", 4)


# ── 行狀頁（季中先看，不叫模型）──────────────────────


def rows(state: GameState, content: Content) -> list[dict]:
    """行狀頁要畫的：照時間先後，一則一列（種類的小標、時刻、地點、人物名、事實、你說的、他回的、份量）。"""
    return [
        {
            "kind": KINDS.get(e.kind, e.kind), "when": e.when, "place": e.place,
            "figure": figure_name(content, e.figure) if e.figure else "", "text": e.text,
            "quote": e.quote, "reply": e.reply, "weight": e.weight,
        }
        for e in sorted(state.player.annals, key=lambda e: e.time)
    ]
