"""擂台的場邊事件（Joy 2026-10-17：「擂台對戰優化，僅僅擂台，加入一些隨機特殊的事件，例如跟玩家或對手玩家友好的武將在台下看到，
用花生米當暗器偷偷相助，或是玩家的放手一搏太離譜雖然也有可能成功，但是引起觀眾憤怒被丟東西之類的，讓擂台不那麼死板又加入一些玩家
在世界努力過的元素，還有應用我們LLM的智能，但是也不要太容易觸發，會變成很膩或是主導戰場走向」；Config.arena.crowd）。

PM 定的預設：
- 不常發生：一場最多一件（ArenaFight.crowd_done）；每回合出完招（或放手一搏）之後擲一次 chance，這一回合要至少一件合條件才擲。
  同一種事件落在同一個人身上一天最多一次（挑的人記 PlayerState.arena_crowd_seen，守的人記 ArenaEntry.crowd_seen；天照回體丹換日）。
- 不主導勝負：一件只推氣勢 edge 幾點（往得利那一邊）、或只動氣血上限的 pool 幾成。
- 觸發條件都是真資料（CrowdSide，snapshot 抄的）：情誼到 patron_affinity 的人物台下暗助（patron）、名望稱號到 fame_tier 走俠的有人喝采
  （cheer）、善惡稱號到 virtue_tier 走寇的被噓被砸（boo）、擂台連勝到 streak 或天下第一台下喊名號（champion）、veteran_hours 內打贏決戰
  的有弟兄吶喊（veteran）、帶著同伴的同伴台下遞兵器（mate）；放手一搏被模型判成「離譜」時觀眾發火（outrage，另擲 outrage_chance）。
- 守擂的分身那一邊也會被幫、被噓，只看他報名時抄的底細與名次（ArenaEntry）。
- 亂數用 arena.rng_for 另開用途「場邊」，不碰 Game.rng。
- 模型：放手一搏評完分另問一次觀眾反應（judge_gamble，清單值，引擎驗；叫不動當「平常」），場邊那一句請模型照當下兩人、那位武將、
  這回合的招重寫（write_line，鎖外背景寫，Game.apply_arena_crowd 重驗）；固定句在 content/arena_crowd.json。數值一律引擎算。

只讀寫傳進來的 ArenaFight 與那兩份 CrowdSide；記帳、紀錄、換句子在 engine.Game（「擂台」那一段）。
"""
from __future__ import annotations

import random
import re
from typing import NamedTuple

from pydantic import BaseModel

from . import gender, renown, zh
from .models import ArenaCrowdTuning, Content
from .state import ArenaEntry, ArenaFight, CrowdNote, CrowdSide, GameState, WorldState
from .world_state import WorldStateStore

KINDS = ("patron", "cheer", "boo", "champion", "veteran", "mate", "outrage")
FIELDS = ("name", "rival", "helper", "title", "battle")
SAMPLE = {"name": "某甲", "rival": "某乙", "helper": "某丙", "title": "名動一方", "battle": "長社火攻"}  # 驗固定句填不填得進去
PREFIX = "〔場邊〕"
LABELS = ("叫好", "平常", "離譜")  # 放手一搏的觀眾反應（judge_gamble）
OUTRAGE_LABEL = "離譜"
WRITE_LIMIT = 50  # 模型寫的那一句最多幾個字（要四十字內；多給一點餘裕）
_DIGITS = re.compile(r"[0-9０-９]")


class Happening(NamedTuple):
    kind: str
    side: str  # me／foe：得利或吃虧的那一邊
    helper: str = ""
    title: str = ""
    battle: str = ""


def on(content: Content) -> bool:
    return content.config.arena.enabled and content.config.arena.crowd.enabled and bool(content.arena_crowd)


def snapshot(state: GameState, content: Content, world: WorldStateStore | None = None) -> CrowdSide:
    """此刻的底細（開打那一刻的挑的人、報名那一刻的守擂分身）：只抄名字與段數。"""
    p, cfg = state.player, content.config.arena.crowd
    team = set(p.team)
    friends = [
        (n, cid) for cid, n in p.affinities.items()
        if n >= cfg.patron_affinity and cid in content.characters and cid not in team
    ]
    patron = max(friends)[1] if friends else ""
    mate = next((content.characters[cid].name for cid in p.team if cid in content.characters), "")
    veteran = ""
    horizon = state.world.time - cfg.veteran_hours * 3600
    for record in reversed(state.battles):
        if record.kind == "showdown" and record.time >= horizon and record.side and record.tier.startswith(record.side):
            veteran = record.event or record.opponent
            break
    path = renown.path(state)
    return CrowdSide(
        patron=patron, patron_name=content.characters[patron].name if patron else "", mate=mate,
        fame_tier=renown.fame_tier(state, content), fame_title=renown.fame_title(state, content) or "",
        virtue_path=path, virtue_tier=renown.virtue_tier(state, content), virtue_title=renown.virtue_title(state, content) or "",
        veteran=veteran, sex=gender.of(state),
    )


def _champion_title(entry: ArenaEntry | None, cfg: ArenaCrowdTuning) -> str:
    if entry is None:
        return ""
    if entry.rank == 1 and entry.bouts:
        return "天下第一"
    return "擂台連勝" if entry.streak >= cfg.streak else ""


def candidates(fight: ArenaFight, world: WorldState, me: str, cfg: ArenaCrowdTuning) -> list[Happening]:
    """這一回合合條件的場邊事件（兩邊都看）。outrage 不在這裡（只跟著離譜的放手一搏來）。"""
    from . import arena  # noqa: PLC0415 — arena 不 import 這裡，避免循環

    out: list[Happening] = []
    entries = {"me": arena.entry_of(world, me), "foe": world.arena.get(fight.foe_key)}
    for side, crowd in (("me", fight.crowd_me), ("foe", fight.crowd_foe)):
        if crowd is not None:
            if crowd.patron_name:
                out.append(Happening("patron", side, helper=crowd.patron_name))
            if crowd.virtue_path == "俠" and crowd.fame_tier >= cfg.fame_tier and crowd.fame_title:
                out.append(Happening("cheer", side, title=crowd.fame_title))
            if crowd.virtue_path == "寇" and crowd.virtue_tier >= cfg.virtue_tier and crowd.virtue_title:
                out.append(Happening("boo", side, title=crowd.virtue_title))
            if crowd.veteran:
                out.append(Happening("veteran", side, battle=crowd.veteran))
            if crowd.mate:
                out.append(Happening("mate", side, helper=crowd.mate))
        title = _champion_title(entries[side], cfg)
        if title:
            out.append(Happening("champion", side, title=title))
    return out


def seen(fight_side: str, kind: str, today: int, mine: dict[str, int], theirs: dict[str, int]) -> bool:
    return (mine if fight_side == "me" else theirs).get(kind) == today


def roll(
    fight: ArenaFight, world: WorldState, me: str, cfg: ArenaCrowdTuning, today: int, mine_seen: dict[str, int],
    foe_seen: dict[str, int], rng: random.Random, label: str = "",
) -> Happening | None:
    """這一回合有沒有場邊事件（呼叫端先問 on）：一場最多一件；放手一搏判成離譜時先擲 outrage_chance，沒中照一般的擲。"""
    if fight.crowd_done:
        return None
    if label == OUTRAGE_LABEL and not seen("me", "outrage", today, mine_seen, foe_seen) and rng.random() < cfg.outrage_chance:
        return Happening("outrage", "me")
    pool = [h for h in candidates(fight, world, me, cfg) if not seen(h.side, h.kind, today, mine_seen, foe_seen)]
    if not pool or rng.random() >= cfg.chance:
        return None
    return rng.choices(pool, weights=[max(0.0, cfg.weights.get(h.kind, 1.0)) for h in pool])[0]


class Applied(NamedTuple):
    edge: int  # 氣勢動了多少（挑的人的角度）
    hp: int  # 那一邊的氣血動了多少（正的是回）
    side: str


def apply(fight: ArenaFight, happening: Happening, cfg: ArenaCrowdTuning) -> Applied:
    """套效果：推氣勢（往得利那一邊）或動那一邊的池子。夾在 0～100、池子的上下限。"""
    sign = 1 if happening.side == "me" else -1
    edge = 0
    hp = 0
    if happening.kind in cfg.edge:
        before = fight.edge
        fight.edge = max(0.0, min(100.0, fight.edge + sign * cfg.edge[happening.kind]))
        edge = round(fight.edge - before)
    if happening.kind in cfg.pool:
        target = fight.me if happening.side == "me" else fight.foe
        want = cfg.pool[happening.kind] * target.hp_cap
        moved = min(want, target.hp_cap - target.hp) if want > 0 else max(want, -max(0.0, target.hp - 1))  # 被砸不會砸到見底
        target.hp += moved
        hp = round(moved)
    fight.crowd_done = True
    return Applied(edge, hp, happening.side)


def names(fight: ArenaFight, me: str, side: str) -> tuple[str, str]:
    """（那一邊的名號, 對手的名號）。"""
    return (me, fight.foe.name) if side == "me" else (fight.foe.name, me)


def fixed_text(content: Content, happening: Happening, name: str, rival: str, rng: random.Random) -> str:
    pool = content.arena_crowd.get(happening.kind) or [""]
    return rng.choice(pool).format(name=name, rival=rival, helper=happening.helper, title=happening.title, battle=happening.battle)


def numbers(applied: Applied, side_is_me: bool) -> str:
    """括號裡的數字（引擎寫的；模型重寫只換句子那一截）。"""
    parts = []
    if applied.edge:
        parts.append(f"氣勢 {applied.edge:+d}")
    if applied.hp:
        parts.append(f"{'你' if side_is_me else '他'}氣血 {applied.hp:+d}")
    return f"（{'，'.join(parts)}）" if parts else ""


def line_of(text: str, applied: Applied) -> str:
    return f"{PREFIX}{text}{numbers(applied, applied.side == 'me')}"


# ── 模型 ──


class CrowdJudge(BaseModel):
    crowd: str = "平常"


JUDGE_PREDICT = 24


def judge_gamble(client, text: str, title: str, name: str) -> str:
    """放手一搏台下觀眾怎麼看（只評這一句本身離不離譜，跟成功率分開問：評分那一次的提示不動）：叫好／平常／離譜，清單以外、
    叫不動都是平常。"""
    if client is None:
        return "平常"
    messages = [
        {"role": "system", "content": (
            "你是江湖擂台台下的觀眾。玩家在擂台上寫了一句放手一搏的招數，只判斷台下觀眾的反應，回 crowd 一個詞："
            "「叫好」＝漂亮、有膽識、精彩；「平常」＝普通的招；「離譜」＝荒唐、下三濫、不講武德、亂寫一通，讓觀眾看不下去。多數招都是平常。"
        )},
        {"role": "user", "content": f"擂台：【{title}】\n出手的人：{zh.prompt_safe(name)}\n他寫的招：「{zh.prompt_safe(text)}」"},  # M-13
    ]
    try:
        result = client.chat_structured(
            messages, CrowdJudge, temperature=0.3, num_predict=JUDGE_PREDICT,
            required_fields=["crowd"], require_in_schema=True,  # 不開的話模型可以整個略過 crowd，白跑一趟（實測，FB-904）
        )
    except Exception:
        return "平常"
    label = zh.to_traditional(str(result.crowd or "")).strip()
    return label if label in LABELS else "平常"


class CrowdLine(BaseModel):
    line: str = ""


WHAT = {
    "patron": "台下跟{name}交好的{helper}偷偷出手相助（例如彈一粒花生米當暗器打{rival}），{name}因此佔了一點便宜",
    "cheer": "台下有人認出{name}這位「{title}」，滿場喝采，{name}精神一振",
    "boo": "台下有人認出{name}是「{title}」，噓聲四起、往台上丟東西，{name}被砸中",
    "champion": "台下觀眾齊聲喊這位{title}{name}的名號，{rival}被喊得心浮氣躁",
    "veteran": "台下有跟{name}一起打過{battle}的弟兄在吶喊助威，{name}出手更狠",
    "mate": "{name}的同伴{helper}在台下遞上一把兵器或一口水，{name}緩過一口氣",
    "outrage": "{name}剛才那一招太過離譜，台下觀眾看不下去，往台上亂扔東西砸{name}",
}


def write_line(client, note: CrowdNote) -> str:
    """請模型把場邊那一句照當下重寫（一句、四十字內、第三人稱、要寫到該寫到的人、不寫數字）；不合用回空字串（照固定句）。"""
    if client is None:
        return ""
    what = WHAT[note.kind].format(name=note.name, rival=note.rival, helper=note.helper, title=note.title, battle=note.battle)
    must = note.helper or note.name
    messages = [
        {"role": "system", "content": (
            "你是說書人，替江湖擂台寫一句台下發生的插曲。只寫一句、四十字以內、繁體中文、第三人稱，用名號稱呼人（不用「你」）；"
            f"一定要寫到「{must}」；不要寫任何數字、不要寫勝負，要有畫面、可以好笑。"
        )},
        {"role": "user", "content": (
            f"擂台上：{note.name if note.side == 'me' else note.rival}對{note.rival if note.side == 'me' else note.name}的分身。"
            f"這一回合挑的人{('寫了一句放手一搏：「' + note.move + '」') if note.kind == 'outrage' else ('出了' + (note.move or '一招'))}"
            f"{('，守擂的分身出了' + note.his) if note.his else ''}。\n插曲：{what}。\n請給 line。"
        )},
    ]
    try:
        result = client.chat_structured(
            messages, CrowdLine, temperature=0.8, num_predict=160,
            required_fields=["line"], require_in_schema=True,  # 同上（FB-904）
        )
    except Exception:
        return ""
    return clean(result.line, must, (note.name, note.rival, note.helper))


def clean(raw: str, must: str, names: tuple[str, ...] = ()) -> str:
    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[\s*#>`_]+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > WRITE_LIMIT or _DIGITS.search(text) or must not in text or zh.stray_latin(text, must, *names):
        return ""
    bare = text
    for n in (must, *names):
        bare = bare.replace(n, "") if n else bare
    if any(ch in bare for ch in "你妳"):
        return ""
    return text if text[-1] in "。！？…" else text + "。"
