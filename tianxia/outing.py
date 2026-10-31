"""走一趟（企劃者 2026-10-29～30；設計稿 https://claude.ai/artifact/RJu4dK5cZoQcEe8SHphktc）：按一次探索走一、三、五段，
每一段就是現行的一次探索（Game._explore_one：一樣的表、一樣扣體力、一樣寫一則江湖紀錄），只是串起來演。

- 素材、遭遇自動走；端出要選的事（事件、有所感、頭目）就停在那一段，玩家選完再接著走（Game.outing_go 不帶段數）。
- 打輸、一段走完氣血低於上限的 outing_turn_back 就回頭；沒走的段不扣體力（體力是一段一段扣的）。
- 段數越多稀有的越容易來（rare_boost）：奇遇事件、一條線的開頭、二階素材、特殊頓悟的機率乘這一趟的倍數。畫面不寫倍數。

- 走完可以在這一處留一句話（say）：預設句免費，自己寫的要一張題壁墨（商城 inscribe，先只能用元寶買），過字表與模型、
  後面掛名號；一處留最近 outing_keep 則，管理者可以刪。之後來這裡走一趟的人，路上會看到刻在石頭、樹上的這一句（trace 那一行，
  不佔段數，一趟最多 outing_trace_cap 行，自己寫的比預設句容易抽到）；這一處 24 小時內有別人，遠處會有個人朝你揮手。
- 畫面上方有塊路碑（stele）：最後一則題壁墨寫的，沒有就是最多人留的那一句預設句；點開看這一處全部的留言。
- 撿到四階素材、勝算凶險以下還打贏（feat）：自動記一則行狀、世界記事一筆；別的不記（Joy 10/30）。

這裡只放純規則（開關、倍數、這一趟還在不在路上、留言、畫面那一份）；走路本身在引擎（Game.outing_go、Game._outing_walk）。
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel

from . import explore_one
from .models import Content
from .rules import jianfa
from .state import GameState, Inscription, Outing, OutingBeat

DONE, LOST, HURT, TIRED, LEFT = "done", "lost", "hurt", "tired", "left"
# 收尾那一句（待 joy 潤）：走完不另說，結算卡自己寫「走完一趟」
END_LINES = {
    LOST: "負傷退回，剩下的路不走了。",
    HURT: "氣血見底，先回頭了。",
    TIRED: "體力不夠，先回頭了。",
    LEFT: "人已經離開了那裡，這一趟就到這裡。",
}
END_TITLES = {DONE: "走完一趟", LOST: "負傷退回", HURT: "回頭", TIRED: "回頭", LEFT: "中途離開"}
# 選段數時那一行（Joy 10/30「有顯示多段的時候越容易獲得更好獎勵的資訊就夠了」；待 joy 潤）
MORE_IS_RARER = "走得越遠，越容易碰上稀有的東西。"
INK = "inscribe"  # 題壁墨：商城的效果名（mall.EFFECTS）；買了得一張，自己寫一句用掉一張
TRACE = "trace"  # 路上看到的那一行（留言、遠處的人）：OutingBeat.kind，不佔段數
# 預設句（免費；假人也從這裡挑）
PRESETS = ("蒼天已死", "吾到此一遊", "天佑大漢")  # Joy 10/30 定的三句（以前十句：「選項有點太多了」）
SURFACES = ("路邊的石頭", "一棵老樹的樹幹", "半截斷碑", "破廟的牆", "橋頭的欄杆")  # 留言刻在哪（照留言 id 挑，同一則每次一樣）
SEEN_LINE = "{surface}上刻著一行字：「{text}」——{author}"
WAVE_LINE = "遠處山坡上，{name}朝你揮了揮手。"
# 留言那一格（待 joy 潤）
TRIP_TITLE = "走一趟・{place}"  # 一趟收了寫的那一則江湖紀錄（整趟的得失加總）；留一句併進這一則，「剛剛」才不會只剩留字（Joy 10/31）
SAY_DONE = "你在{place}留下一句：「{text}」"
SAY_AGAIN = "這一趟已經留過一句了。"
SAY_NOT_HERE = "要人在這一處，走完一趟才能留言。"
SAY_EMPTY = "寫點什麼再留。"
NO_INK = "自己寫的要用一張題壁墨，你手上沒有，先到萬寶閣買。"
ERASED = "那一句已經抹掉了。"
# 值得記下來的一段（Joy 10/30：每一趟都能收進行狀太多、沒價值；「真的出現超級稀有的物品或是奇蹟逆轉的戰役這種類型的才有價值被記錄」）：
# 撿到四階素材、勝算凶險以下還打贏，自動記一則行狀、世界記事一筆。以前結算卡有「收進行狀」鈕，拿掉了（待 joy 潤）
FEAT_TIER = 4  # 素材幾階以上算稀世
FEAT_ODDS = ("凶險", "必敗")  # 開打前的勝算是這幾個字還打贏，算以弱勝強
FEAT_TREASURE, FEAT_UPSET = "treasure", "upset"
FEAT_ANNAL = {FEAT_TREASURE: "在{place}一帶走了一趟，撿到了世間少見的{what}。", FEAT_UPSET: "在{place}一帶撞上{what}，看著必輸的一仗，硬是打贏了。"}
FEAT_DEED = {FEAT_TREASURE: "{name}在{place}一帶撿到了世間少見的{what}。", FEAT_UPSET: "{name}在{place}一帶以弱勝強，打退了{what}。"}
FEAT_NOTE = "這一趟記進了行狀。"
# 遭遇的對手畫成哪一種人（Joy 10/30「現在敵人只有黃巾軍，如果我本身就是黃巾不是很奇怪嗎」）：先看隊伍的陣營，沒有陣營的照名字認
LOOK_HUANG, LOOK_GUAN, LOOK_RETAINER, LOOK_BANDIT, LOOK_BEAST = "huang", "guan", "retainer", "bandit", "beast"
_FACTION_LOOK = {"huang": LOOK_HUANG, "guan": LOOK_GUAN, "haoqiang": LOOK_RETAINER}
_NAME_LOOK = (("黃巾", LOOK_HUANG), ("官軍", LOOK_GUAN), ("門卒", LOOK_GUAN), ("家丁", LOOK_RETAINER), ("護院", LOOK_RETAINER),
              ("部曲", LOOK_RETAINER), ("虎", LOOK_BEAST))
TALE_MAX = 80  # 遊記最多幾個字
DEED_KIND = "outing"  # 世界記事（deeds.record）的種類：走一趟撿到稀世的東西、以弱勝強（FEAT_DEED）
_ZH = "零一二三四五六七八九十"
_DIGITS = re.compile(r"[0-9０-９]|[一二三四五六七八九十兩]+(?=[段場顆次件])")  # 遊記不准有數字：阿拉伯數字，與「三段」「兩場」這種數量
_BANNED = ("假人", "機器人", "外掛", "遊戲", "系統", "玩家")


def on(content: Content, state: GameState) -> bool:
    """走一趟開著：減法季的探索一顆開著，而且 outing 子開關也開著（rules.jianfa）。"""
    world = state.world
    return jianfa(content, world, "explore_one") and jianfa(content, world, "outing")


def segments(content: Content) -> list[int]:
    return list(content.config.jianfa.outing_segments)


def active(state: GameState) -> Outing | None:
    """還在路上的那一趟（沒收、人還在出發的地方）；沒有是 None。"""
    trip = state.player.outing
    if trip is None or trip.end or trip.place != state.player.location:
        return None
    return trip


def rare_boost(state: GameState, content: Content) -> float:
    """此刻稀有的東西乘多少：在路上照這一趟幾段（Config.jianfa.outing_rare），不在路上是 1（跟以前一模一樣）。"""
    trip = active(state)
    if trip is None or not on(content, state):
        return 1.0
    return float(content.config.jianfa.outing_rare.get(str(trip.total), 1.0))


def cost(content: Content, total: int) -> int:
    return content.config.jianfa.explore_stamina * total


def view(state: GameState, content: Content) -> dict | None:
    """/api/main 的 outing：網頁照它畫探索鈕的段數選單（picker）與走一趟的畫面（trip）。關著是 None（網頁照舊一顆探索）。"""
    if not on(content, state):
        return None
    p = state.player
    picker = [{"n": n, "stamina": cost(content, n), "ok": p.stamina >= cost(content, n)} for n in segments(content)]
    trip = p.outing
    out = {"picker": picker, "note": MORE_IS_RARER, "trip": None}
    if trip is not None:
        out["trip"] = {
            "place": content.locations[trip.place].name if trip.place in content.locations else trip.place,
            # 背景畫哪一套：這一處的地點種類（探索那六張表，explore_one.kind_of）
            "scene": explore_one.kind_of(content.config.jianfa, content.locations[trip.place]).kind if trip.place in content.locations else explore_one.WILD,
            "n": trip.n, "total": trip.total, "done": trip.done, "end": trip.end,
            "waiting": not trip.end and bool(trip.beats) and trip.beats[-1].stop,
            "title": END_TITLES.get(trip.end, ""), "end_line": END_LINES.get(trip.end, ""),
            "beats": [b.model_dump() for b in trip.beats],
            "said": trip.said, "can_say": say_ok(state) is not None, "presets": list(PRESETS),
            "say_max": content.config.jianfa.outing_say_max,
            "diary": trip.tale or (template_tale(trip, content) if trip.end else ""), "diary_done": trip.tale_done,
            "feat_note": FEAT_NOTE if trip.end and any(b.feat for b in trip.beats) else "",
            "stele": stele(state, trip.place, own=bool(trip.said)),
        }
    return out


_NOTE = re.compile(r"^(\S+ [+-]\d+(?:\.\d+)?)（.*）$")  # 「善名 +1（離「江湖遊俠」還差 31）」後面那段說明


def plain(change: str) -> str:
    """數值變化後面接的說明（離下一個名號還差多少）拿掉：加總的時候同一個標籤才併得起來。"""
    hit = _NOTE.match(change)
    return hit.group(1) if hit else change


def ledger_parts(text: str) -> list[str]:
    """「得：a、b　失：c」拆回一樣一樣（a、b、c，說明拿掉）；空字串是空的。"""
    out: list[str] = []
    for part in text.split("　"):
        if part.startswith(("得：", "失：")):
            out += [plain(x) for x in part[2:].split("、") if x]
    return out


def trip_totals(trip: Outing) -> tuple[list[str], list[str]]:
    """整趟的得失（結算卡與「走一趟」那一則江湖紀錄）：(撿到的東西「名 ×N」, 數值變化「標籤 ±N」)。每一段的得失、停下來選完的得失
    （OutingBeat.after，含選項另外扣的體力）、每一段探索扣的體力都加進去；同一樣加總。"""
    from . import journal  # journal 牽著 battlelog；這裡用到才拿

    parts = [x for b in trip.beats for x in ledger_parts(b.ledger) + ledger_parts(b.after)]
    spent = sum(b.spent for b in trip.beats)
    items = explore_one.merge_items(x for x in parts if explore_one.is_item(x))
    changes = journal.combine_changes([x for x in parts if not explore_one.is_item(x)] + ([f"體力 -{spent}"] if spent > 0 else []))
    return items, changes


def foe_look(squad) -> str:
    """這一路對手畫成哪一種人（LOOK_*）：有陣營照陣營，沒有照名字裡的字，都不是就是綠林盜匪。"""
    look = _FACTION_LOOK.get(squad.faction or "")
    if look:
        return look
    return next((v for k, v in _NAME_LOOK if k in squad.name), LOOK_BANDIT)


def stele(state: GameState, place: str, *, own: bool = False) -> dict | None:
    """畫面上方那塊路碑（Joy 10/30）：這一處留過的話。碑上那一句是最後一則用題壁墨寫的；沒有人用過題壁墨，是最多人留的那一句預設句
    （一樣多取最近留的）；ink 是碑上那一句是題壁墨寫的（畫面要畫得更顯眼，Joy 10/30）。own（這一趟自己剛留過一句）：碑上先是自己那一句（Joy 10/30「要」），mine 標出來。
    all 是點開看到的全部，新的在前。這一處沒人留過是 None。"""
    here = [i for i in state.world.inscriptions if i.place == place]
    if not here:
        return None
    mine = [i for i in here if i.author == state.player.name] if own else []
    inked = [i for i in here if not i.preset]
    if mine:
        top = max(mine, key=lambda i: i.id)
        return {"text": top.text, "author": top.author, "n": 0, "mine": True, "ink": not top.preset,
                "all": [{"text": i.text, "author": i.author, "ink": not i.preset} for i in sorted(here, key=lambda i: -i.id)]}
    if inked:
        top, n = max(inked, key=lambda i: i.id), 0
    else:
        counts = Counter(i.text for i in here)
        top = max(here, key=lambda i: (counts[i.text], i.id))
        n = counts[top.text]
    return {"text": top.text, "author": top.author if not top.preset else "", "n": n, "ink": not top.preset,
            "all": [{"text": i.text, "author": i.author, "ink": not i.preset} for i in sorted(here, key=lambda i: -i.id)]}


def say_ok(state: GameState) -> Outing | None:
    """此刻能在這一趟留一句：這一趟收了（走完或回頭；中途離開不算）、還沒留過、人還在這一處。不行是 None。"""
    trip = state.player.outing
    if trip is None or not trip.end or trip.end == LEFT or trip.said or trip.place != state.player.location:
        return None
    return trip


def inscribe(state: GameState, content: Content, text: str, *, preset: bool) -> Inscription:
    """把這一句刻在這一趟的地點（WorldState.inscriptions），同一處只留最近 outing_keep 則。呼叫端驗過能留、驗過字。"""
    w, trip = state.world, state.player.outing
    w.inscription_seq += 1
    item = Inscription(id=w.inscription_seq, place=trip.place, text=text, author=state.player.name, preset=preset, time=w.time)
    w.inscriptions.append(item)
    here = [i for i in w.inscriptions if i.place == trip.place]
    drop = {i.id for i in here[:-content.config.jianfa.outing_keep]}
    w.inscriptions = [i for i in w.inscriptions if i.id not in drop]
    trip.said = text
    return item


def erase(state: GameState, ins_id: int) -> bool:
    before = len(state.world.inscriptions)
    state.world.inscriptions = [i for i in state.world.inscriptions if i.id != ins_id]
    return len(state.world.inscriptions) < before


def traces_left(trip: Outing, content: Content) -> int:
    return content.config.jianfa.outing_trace_cap - sum(1 for b in trip.beats if b.kind == TRACE)


def trace_rng(state: GameState, trip: Outing) -> random.Random:
    """路上那幾行用的亂數：照名號、此刻的季曆時間、走到第幾段（不動 Game.rng，別的亂數一個都不變）。"""
    return random.Random(f"{state.player.name}:{state.world.time:.3f}:{trip.done}:trace")


def seen_beat(state: GameState, content: Content, trip: Outing, rng: random.Random) -> OutingBeat | None:
    """路上看到一則別人的留言（這一處、不是自己留的、這一趟還沒看過的）：自己寫的比預設句容易抽到 outing_trace_custom 倍。沒有是 None。"""
    shown = {b.ref for b in trip.beats if b.kind == TRACE}
    pool = [i for i in state.world.inscriptions
            if i.place == trip.place and i.author != state.player.name and i.id not in shown]
    if not pool:
        return None
    custom = content.config.jianfa.outing_trace_custom
    item = rng.choices(pool, weights=[1.0 if i.preset else custom for i in pool])[0]
    surface = SURFACES[item.id % len(SURFACES)]
    return OutingBeat(kind=TRACE, text=SEEN_LINE.format(surface=surface, text=item.text, author=item.author), ref=item.id)


def wave_beat(names: list[str], rng: random.Random) -> OutingBeat | None:
    """這一處有別人（「此地還有」那一份名單）：遠處有人揮手。沒有人是 None。"""
    if not names:
        return None
    return OutingBeat(kind=TRACE, text=WAVE_LINE.format(name=rng.choice(sorted(names))))


# ── 遊記（設計稿第七節）：結算卡上的帳一個字都不靠模型；底下三四句遊記是模型寫的，鎖外三段式（server.outing_tale），
# 不准有數字、不准提遊戲；叫不動、不合用就留空，畫面用照每一段拼的模板（template_tale）。只有自己看得到，可以收進行狀 ──

def zh_count(n: int) -> str:
    """數量的中文（「兩樣」不寫「二樣」）；十以上寫「好幾」。"""
    return "兩" if n == 2 else _ZH[n] if 0 <= n <= 10 else "好幾"


def template_tale(trip: Outing, content: Content) -> str:
    """模型不在時的遊記：照每一段的類別拼兩三句（不寫數字以外的細節，數字用中文）。"""
    place = content.locations[trip.place].name if trip.place in content.locations else trip.place
    walked = [b for b in trip.beats if b.kind != TRACE]
    parts: list[str] = []
    mats = sum(1 for b in walked if b.kind == "material")
    fights = [b for b in walked if b.kind == "encounter"]
    if mats:
        parts.append(f"沿路撿了{zh_count(mats)}樣東西")
    if fights:
        won = sum(1 for b in fights if b.won)
        parts.append(f"跟人動了{zh_count(len(fights))}回手" + ("，都占了上風" if won == len(fights) else ""))
    if any(b.kind == "insight" for b in walked):
        parts.append("走著走著心頭一動")
    if any(b.kind == "event" for b in walked):
        parts.append("還碰上一樁事")
    if any(b.kind == TRACE and b.ref for b in trip.beats):
        parts.append("在路邊看見前人留的字")
    if any(b.kind == TRACE and not b.ref for b in trip.beats):
        parts.append("遠遠有人朝你揮手")
    head = f"這一趟在{place}走了{zh_count(len(walked))}段。"
    body = "，".join(parts) + "。" if parts else ""
    tail = END_LINES.get(trip.end, "天色將晚，收拾回程。")
    return head + body + tail


@dataclass(frozen=True)
class TaleRequest:
    """遊記的單子（A 段開、B 段送模型、C 段照 place、beats、time 認是不是同一趟）。"""

    name: str
    place: str
    beats: int
    n: int  # 第幾趟（Outing.n）
    facts: tuple[str, ...]


class TaleReply(BaseModel):
    tale: str


def tale_request(state: GameState, content: Content) -> TaleRequest | None:
    """這一趟收了、還沒請過模型：開單（每一段那一行、路上看到的、怎麼收尾）。不行是 None。"""
    trip = state.player.outing
    if trip is None or not trip.end or trip.tale_done:
        return None
    place = content.locations[trip.place].name if trip.place in content.locations else trip.place
    facts = [b.text for b in trip.beats if b.text] + [END_LINES.get(trip.end, "走完了這一趟，平安回來。")]
    return TaleRequest(name=state.player.name, place=place, beats=len(trip.beats), n=trip.n, facts=tuple(facts))


def same_trip(state: GameState, req: TaleRequest) -> Outing | None:
    trip = state.player.outing
    if trip is None or not trip.end or trip.tale_done or len(trip.beats) != req.beats or trip.n != req.n:
        return None
    return trip


def tale_messages(req: TaleRequest) -> list[dict[str, str]]:
    facts = "\n".join(f"- {f}" for f in req.facts)
    return [
        {"role": "system", "content": (
            "你替東漢末年一個江湖人寫遊記。下面是他這一趟在某地沿路發生的事，照先後寫成一段遊記，"
            "三四句、八十字以內、繁體中文、半文半白、用「你」稱他。只寫清單裡有的事，不要編造清單裡沒有的人名、地名、物名；"
            "不要寫任何數字（也不要寫「三段」「兩場」這種數量），不要寫標題或列點，不要提到遊戲、系統、玩家。"
        )},
        {"role": "user", "content": f"地點：{req.place}\n這一趟的事：\n{facts}\n請給 tale。"},
    ]


def tale_clean(raw: str, req: TaleRequest) -> str | None:
    """模型寫的遊記驗過才用：轉繁體、去掉標記與換行；有數字、太長、提到遊戲的丟掉（回 None）。"""
    from . import zh  # noqa: PLC0415

    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[*#>`_]+", "", text)
    text = re.sub(r"\s+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > TALE_MAX or _DIGITS.search(text) or any(w in text for w in _BANNED):
        return None
    return text if text[-1] in "。！？…」" else text + "。"


def tale_write(client, req: TaleRequest) -> str | None:
    """B 段（鎖外）：請模型寫遊記；叫不動、不合用回 None。"""
    if client is None:
        return None
    try:
        result = client.chat_structured(tale_messages(req), TaleReply, temperature=0.8, num_predict=320, required_fields=["tale"])
    except Exception:  # noqa: BLE001 — 叫不動就用模板
        return None
    return tale_clean(result.tale, req)
