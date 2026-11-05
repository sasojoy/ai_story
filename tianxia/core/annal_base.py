"""行狀的底座（全部拆包第 29 批之二；主人：列傳包 features/zhuan；手冊 3.3、3.10）。

各包打完、做完時「記一筆行狀」用的函式與常數留在這裡（note、entry、trim、kept_names、clip、first_sentence、figure_name、on、heard，
盯狀態變化的 mark、watch，與種類常數 SHOWDOWN…STORY、KINDS、GROUPS、UNHEARD），寫進 PlayerState.annals／annals_mark：
核心（engine、event_check）、舊模組 fusion 與各包都經它，不 import 列傳包（核心不准 import 包；smithing 照舊 import 舊名 annals，拿到的是
同一批物件，第 41 批鐵匠鋪合併時改）。列傳包的 standing.py 管查詢與行狀頁那一半（profile、standing、tier_*、xingshi_notes、rows）。
舊名 tianxia/annals.py 是指到 standing.py 的 sys.modules 別名（standing 用 import * 加 _gear、_notable re-export 這裡的名字，同一批物件）。

原本寫在 tianxia/annals.py，一個字沒改（只有 watch、mark 裡兩個延後 import 從 from . 改成 from ..）。與 event_check、omen_base 同樣不進 MODULES。

江湖紀錄只留 30 則、戰報 20 場、每位人物的對話 40 則，季末湊不出一整季，所以另記一份：PlayerState.annals，一則一件事
（AnnalEntry：種類、時刻、地點、人物、一句事實、你說的那一句與他回的那一句、份量）。超過 Config.biography.cap 就先丟輕的。

兩種記法：
- note：有話可說的地方直接記（決戰收場、對話、挑戰本人、頭目戰、截殺、首創、絕學定名、奇遇、伏筆揭曉、名將贈禮）；
- watch：每個動作結束時（Game._log）拿幾樣狀態跟上一次看到的比（PlayerState.annals_mark），變了的記一筆——投靠、叛投、拜師、
  晉升、等級、遊俠名號、同伴、寶物名駒名器、情誼跨格、本命武學、練成絕學。這些改的地方散在十幾個模組裡，一個一個去掛容易漏。

只記、不改任何數值，不碰 Game.rng。假人照樣記（跟真人看不出差別）。開關是 Config.biography.enabled，不掛第一季開關。
"""
from __future__ import annotations

from collections.abc import Iterable

from ..calendar import stamp_text
from ..models import Content
from ..state import AnnalEntry, GameState

SHOWDOWN, FIGURE, FIGHT, DEED = "showdown", "figure", "fight", "deed"
CONQUER = "conquer"  # 翻地與爭搶（輿圖簡化設計 4.5）：推最多、率先攻入一塊地，或拉回最多、守住一塊地
# 起用玉璽碎片的獨門行動（Game.seal_use）：持有者平時藏起來（碎片改版設計第二、三章「行狀只記在用的人自己的行狀裡」），酒肆與買兇找人
# 不讀這一類（heard；FB-643）。本人的行狀頁照「行事」寫、季末的傳歸在出身與行事那一段（GROUPS），跟一般的事一樣
SEAL = "seal"
# 地方痕跡過了門檻、你出過力（減法季批 4，Game._mark_credits）：公開的只有痕跡、不列名字，所以酒肆打聽不到（UNHEARD）；季末的傳照行事寫
MARK = "mark"
# 人物心意到了門檻、你這一週也勸過（減法季批 6，Game._stance_annals）：公開的只有他改做什麼、不列誰勸的，酒肆打聽不到；季末的傳照人物那一段
STANCE = "stance"
# 人物託付的事辦成了（減法季批 6，errands.py；整合設計 5.5「寫進列傳」）：季末的傳照人物那一段
ERRAND = "errand"
# 減法季批 7b（列傳為終點，整合設計第九章；子開關 zhuan_end）：〈天下形勢〉寫到你的名號（xingshi_notes，自己同步那一下記，同 MARK）、
# 季末論功的名次與第幾階（tier_note，收季之後自己同步那一下記；換季時沒同步過的人在 _reset_player_for_new_season 補）。
# 〈天下形勢〉的照行事寫；論功自己一段（biography 的【季末論功】，傳寫在最後一段）
XINGSHI = "xingshi"
TIER = "tier"
# 出陣約戰打了一場（減法季批 3b，Game._duel_report；計畫 8.0 的「3b 約戰結算 → DUEL」）：攻方與應戰的人各記一則（同去的人沒下場不記）。
# 行狀頁的小標、季末的傳都跟其他單挑一樣寫「交手」（GROUPS 歸 FIGHT）；另開一類是給列傳那一小步（7b-1 剩下的）認得出約戰
DUEL = "duel"
# 一條線收了（特殊事件與特殊頓悟，storyline.py；企劃者 2026-10-26「必定會進入傳記中」）：成的、失敗的、季末還沒了的都記一則，份量照結局。
# 行狀頁的小標寫「奇事」，季末的傳照行事寫
STORY = "story"
KINDS = {SHOWDOWN: "大戰", FIGURE: "人物", FIGHT: "交手", DEED: "行事", CONQUER: "攻守", SEAL: "行事", MARK: "行事",
         STANCE: "人物", ERRAND: "人物", XINGSHI: "行事", TIER: "論功", DUEL: "交手", STORY: "奇事"}  # 行狀頁的小標（待 joy 潤）
# 季末的傳（biography._group）照哪一段寫：沒列的照自己的種類（TIER 自己一段）
GROUPS = {SEAL: DEED, MARK: DEED, STANCE: FIGURE, ERRAND: FIGURE, XINGSHI: DEED, DUEL: FIGHT, STORY: DEED}
UNHEARD = frozenset({SEAL, MARK, STANCE})  # 酒肆打聽不到的種類
TEXT_MAX, QUOTE_MAX, REPLY_MAX = 80, 40, 80
STORY_TEXT_MAX = 260  # 奇事收尾寫進傳的那一章（長篇奇事，企劃者 2026-10-27）：照走過的路拼的一段，兩百字上下；其他種類照 TEXT_MAX
MASTERED = "絕學"  # martial_arts.QUALITIES 的最後一品


def on(content: Content) -> bool:
    return content.config.biography.enabled


def heard(entry: AnnalEntry) -> bool:
    """這一則酒肆打聽得到嗎（打聽交情的近來的事、近況、名氣都只算打聽得到的；FB-643）。"""
    return entry.kind not in UNHEARD


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
    keep: Iterable[str] | None = None,
) -> None:
    """記一則行狀。place 沒給就是人此刻所在的地點；time 沒給就是此刻的世界時間（決戰收場給收場那一刻）。
    keep 是這一句裡別的玩家的名號（對手、被點名的人），季末備援列傳照它原樣保留（AnnalEntry.keep）；沒有別人的名號不必給。"""
    if not on(content) or not text:
        return
    state.player.annals.append(entry(state, content, kind, text, weight, figure=figure, quote=quote, reply=reply, place=place, time=time, keep=keep))
    trim(state, content)


def entry(
    state: GameState, content: Content, kind: str, text: str, weight: int, *,
    figure: str = "", quote: str = "", reply: str = "", place: str | None = None, time: float | None = None,
    season=True, keep: Iterable[str] | None = None,
) -> AnnalEntry:
    """寫好一則（note 用它，不記進行狀）。season 是 False 時時刻照舊的寫法（上一季的事，這一季的季曆對不上）。
    keep 去掉空的與重複的，也不放傳主自己的名號（傳裡的「你」就是要換成他的名號）。"""
    p, w = state.player, state.world
    when = w.time if time is None else time
    if place is None:
        loc = content.locations.get(p.location)
        place = loc.name if loc is not None and p.journey is None else ""
    return AnnalEntry(
        kind=kind, time=when, when=stamp_text(when, content, w if season else None), place=place, figure=figure,
        text=clip(text, STORY_TEXT_MAX if kind == STORY else TEXT_MAX), quote=clip(quote, QUOTE_MAX), reply=clip(reply, REPLY_MAX), weight=max(1, min(5, weight)),
        keep=kept_names(keep, p.name),
    )


def kept_names(keep: Iterable[str] | None, own: str = "") -> list[str]:
    """AnnalEntry.keep 存什麼：名字的空白照 clip 收成一個（文字裡的名號是被 clip 收過的，對不上就找不到）、去掉空的與重複的、
    不放傳主自己的名號（own）。"""
    names = (" ".join(str(k).split()) for k in keep or ())
    return list(dict.fromkeys(k for k in names if k and k != own))


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
    from .. import ranger  # ranger 不 import 這裡；延後 import 免得 engine 載入順序繞圈

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
        from .. import ranks

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
