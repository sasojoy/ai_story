"""宴客（大勢人物擴充第三批「大家一起」；Joy 2026-10-19「第三批開始做」；設計稿
https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2「多人同服的玩法」；數字在 Config.figure_life 的 feast_*）。

- 設宴（maybe_open，figure_life.tick 每一輪叫）：心事是得意或沒有心事、此刻在場的人物擲 feast_chance，在他此刻的地方擺一場
  feast_hours 個世界小時的宴；全服同時最多 feast_max_open 場，上一場開席之後 feast_gap_hours 內不再開。天下大事一句。
  亂數「宴客｜天機｜人物｜第幾輪」，不碰 Game.rng。
- 赴宴：人在那裡、這一場還沒敬過酒就能入席（不花體力）。挑一句固定的敬酒詞（FIXED_SCORE 分），或寫二十字自己的
  （伺服器鎖外請模型評一個分數，score；三段式 Game.feast_text_request → score → Game.feast_toast）。情誼照分數 +1～+feast_affinity_max。
  敵對陣營的人也能混進去寫挑釁的話，分數照評。
- 散席（settle，world.advance_world_state 每一步叫）：分數最高的那一句（一樣高看誰先說）上天下大事，那個人同步時名望 +feast_fame
  （deliver）。
只 import models、state、rules、figure_life、zh、gender；engine、world、server、letters 呼叫它。
功能包 tianxia/features/feast/ 的純規則（開發規範手冊 3.2；原本是 tianxia/feasts.py，那一個名字留成指到這裡的別名）。"""
from __future__ import annotations

import random
import re

from pydantic import BaseModel

from tianxia import gender
from tianxia import figure_life  # 過渡：待搬（人物此刻在哪、心事、站哪一邊）
from tianxia import seal_acts  # 過渡：待搬（收心：一日之內敬酒的情誼 ×2）
from tianxia.models import Content
from tianxia.rules import add_rumor
from tianxia.state import Feast, GameState, Toast

HOUR = 3600.0
TITLE = "宴客"  # 江湖紀錄那一則的標題

# 待 joy 潤：固定的敬酒詞（挑哪一句都是 FIXED_SCORE 分：穩穩的情誼 +2，自己寫得好才拿得到更多）
FIXED_TOASTS = (
    "敬主人一杯，願此間太平。",
    "亂世相逢，先乾為敬。",
    "久仰大名，今日得見，幸甚。",
)
FIXED_SCORE = 40
DEFAULT_SCORE = 40  # 自己寫的敬酒詞評不到分數時（同決戰放手一搏的保底，刻意不高）
TOAST_LIMIT = 20

OPEN_LINE = "{host}在{place}設宴，江湖同道路過皆可入席。"  # 待 joy 潤：天下大事
BEST_LINE = "{host}的宴席散了，席間{name}一句「{text}」最得主人歡心。"  # 待 joy 潤：天下大事
QUIET_LINE = "{host}的宴席散了，席間冷清，沒什麼人來。"  # 待 joy 潤：一個人都沒來（地方傳聞）
JOIN_LABEL = "赴{host}的宴（不花體力）"
DONE_LABEL = "赴{host}的宴（你已經敬過酒了）"
TOAST_LABEL = "敬酒：「{text}」"
LEAVE_LABEL = "離席"
LEFT = "你起身離席。"  # 待 joy 潤
FREE_PROMPT = "敬一句自己的（20字內，主人聽了越高興情誼越多）"
SEATED = "你在{host}的宴席上坐下。席間已有 {n} 人敬過酒。"  # 待 joy 潤
TOASTED = "你舉杯：「{text}」{reaction}"  # 待 joy 潤
REACTIONS = ((80, "{host}拍案大笑，親自替你斟滿。"), (60, "{host}連聲叫好。"), (40, "{host}點頭飲盡。"),
             (20, "{host}淡淡一笑。"), (0, "{host}臉色一沉，滿座無聲。"))  # 待 joy 潤：分數門檻由高到低
BEST_PAID = "你在{host}宴席上那一句「{text}」傳開了，人人稱道。"  # 待 joy 潤：席間最佳的那個人同步時
GONE = "宴席已經散了。"
NOT_HERE = "你不在宴席上。"
TOASTED_BEFORE = "這一場你已經敬過酒了。"
BAD_TEXT = "敬酒詞要寫一到二十個字。"


def on(content: Content) -> bool:
    return figure_life.on(content) and content.config.figure_life.feasts


def find(state: GameState, feast_id: int | None) -> Feast | None:
    return next((f for f in state.world.feasts if f.id == feast_id), None) if feast_id is not None else None


def is_open(state: GameState, f: Feast) -> bool:
    return not f.settled and f.start <= state.world.time < f.end


def open_feasts(state: GameState) -> list[Feast]:
    return [f for f in state.world.feasts if is_open(state, f)]


def hosting(state: GameState, cid: str) -> Feast | None:
    """cid 此刻在擺的那一場（擺宴的人不走動：figure_life._act 先問它）。"""
    return next((f for f in open_feasts(state) if f.host == cid), None)


def here(state: GameState, content: Content) -> list[Feast]:
    """人在這裡、這裡正擺著的宴（在路上不算）。"""
    p = state.player
    if not on(content) or p.journey is not None:
        return []
    return [f for f in open_feasts(state) if f.place == p.location]


def toasted(state: GameState, f: Feast) -> bool:
    key = _key(state.player.name)
    return any(_key(t.name) == key for t in f.toasts)


def _key(name: str) -> str:
    return name.casefold()


def host_name(content: Content, f: Feast) -> str:
    ch = content.characters.get(f.host)
    return ch.name if ch is not None else f.host


def _place(content: Content, loc: str) -> str:
    return content.locations[loc].name if loc in content.locations else loc


# ── 設宴與散席（季的事）────────────────────────────────


def maybe_open(state: GameState, content: Content, cid: str, turn: int) -> None:
    """figure_life.tick 每一輪每位人物叫一次：擲中了就在他此刻的地方擺一場。"""
    if not on(content):
        return
    w, tuning = state.world, content.config.figure_life
    ch = content.characters.get(cid)
    if ch is None or not ch.deep_interaction:
        return
    if len(open_feasts(state)) >= tuning.feast_max_open:
        return
    if w.feasts and w.time - max(f.start for f in w.feasts) < tuning.feast_gap_hours * HOUR:
        return
    place = figure_life.where(state, content, cid)
    if place is None or place not in content.locations or figure_life.mood_any(state, content, cid) not in (None, "得意"):
        return
    if random.Random(f"宴客|{w.tianji}|{cid}|{turn}").random() >= tuning.feast_chance:
        return
    w.feast_seq += 1
    w.feasts.append(Feast(id=w.feast_seq, host=cid, place=place, start=w.time, end=w.time + tuning.feast_hours * HOUR))
    del w.feasts[:-20]
    add_rumor(state, OPEN_LINE.format(host=ch.name, place=_place(content, place)), place, content=content, layer="world")


def settle(state: GameState, content: Content) -> None:
    """時間到了的宴散席：最高分那一句上天下大事（一樣高看先說的）、記下是誰（deliver 補名望）。沒人來只寫一則地方傳聞。
    開關關著也照散（不然關掉那一刻擺著的宴一直不散）。"""
    w = state.world
    for f in w.feasts:
        if f.settled or w.time < f.end:
            continue
        f.settled = True
        host = host_name(content, f)
        if not f.toasts:
            add_rumor(state, QUIET_LINE.format(host=host), f.place, content=content, layer="local")
            continue
        best = max(f.toasts, key=lambda t: (t.score, -t.at))
        f.best = best.name
        add_rumor(state, BEST_LINE.format(host=host, name=best.name, text=best.text), f.place, content=content, layer="world")


def deliver(state: GameState, content: Content) -> list[str]:
    """同步時叫：散席時我那一句是席間最佳、還沒領過，名望 +feast_fame。回傳江湖紀錄的句子（標題 TITLE）。"""
    from tianxia import renown  # noqa: PLC0415  過渡：待搬（renown → rules …：延後載入）

    p = state.player
    out: list[str] = []
    for f in state.world.feasts:
        if not f.settled or not f.best or _key(f.best) != _key(p.name) or f.id in p.feasts_paid:
            continue
        p.feasts_paid.append(f.id)
        mine = next((t for t in f.toasts if _key(t.name) == _key(p.name)), None)
        out.append(BEST_PAID.format(host=host_name(content, f), text=mine.text if mine else ""))
        amount = content.config.figure_life.feast_fame
        if amount:
            out += renown.gain(state, content, "fame", amount)
    return out


# ── 赴宴 ─────────────────────────────────────────────


def affinity_of(content: Content, score: int) -> int:
    """分數 → 情誼 +1～+feast_affinity_max（0 分也有 1：來了就是給面子）。"""
    top = content.config.figure_life.feast_affinity_max
    return max(1, min(top, 1 + max(0, min(100, score)) * (top - 1) // 100))


def reaction(content: Content, f: Feast, score: int) -> str:
    return next(line for floor, line in REACTIONS if score >= floor).format(host=host_name(content, f))


def toast_problem(state: GameState, content: Content, f: Feast | None) -> str | None:
    if f is None or not is_open(state, f) or not on(content):
        return GONE
    if f.place != state.player.location or state.player.journey is not None:
        return NOT_HERE
    if toasted(state, f):
        return TOASTED_BEFORE
    return None


SCENE = "**{host}的宴席**\n\n{host}在{place}擺開酒席，賓客往來。挑一句敬酒，或寫一句自己的——說得好，主人記得住你；散席時最得主人歡心的那一句會傳遍江湖。"  # 待 joy 潤
SCENE_HEARD = "席間已有 {n} 人敬過酒，最近的是："


def scene(state: GameState, content: Content, f: Feast) -> str:
    """坐在宴席上時的場景（Game._own_scene_text）：主人、地方，與最近三句敬酒詞。"""
    text = SCENE.format(host=host_name(content, f), place=_place(content, f.place))
    if f.toasts:
        recent = "\n".join(f"- {t.name}：「{t.text}」" for t in f.toasts[-3:])
        text += f"\n\n{SCENE_HEARD.format(n=len(f.toasts))}\n\n{recent}"
    return text


def clean_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def toast(state: GameState, content: Content, f: Feast, text: str, score: int, fixed: bool) -> list[str]:
    """敬一句（呼叫端已經驗過 toast_problem）：記進這一場、情誼照分數動、收起宴席的選單。"""
    p = state.player
    score = max(0, min(100, int(score)))
    f.toasts.append(Toast(name=p.name, text=text, score=score, at=state.world.time, fixed=fixed))
    p.feasting = None
    before = p.affinities.get(f.host, 0)
    # 收心（玉璽碎片改版第 2 批）：一日之內敬酒的情誼漲幅 ×2
    p.affinities[f.host] = min(100, before + seal_acts.warmer(state.world, content, f.host, affinity_of(content, score)))
    moved = p.affinities[f.host] - before
    msgs = [TOASTED.format(text=text, reaction=reaction(content, f, score))]
    if moved:
        msgs.append(f"{host_name(content, f)}情誼 +{moved}")
    return msgs


# ── 自己寫的敬酒詞：模型只評一個分數（鎖外；server.feast_text）────────


class ToastRequest(BaseModel):
    """A 段（Game.feast_text_request）開的單子：C 段照 feast、名號與那一句認同一件。"""

    feast: int
    host: str
    host_name: str
    host_side: str = ""
    persona: str = ""
    mood: str = ""
    place: str
    name: str
    side: str = ""
    sex: str = "男"
    text: str


class ToastScore(BaseModel):
    score: int = DEFAULT_SCORE


SCORE_PREDICT = 24


def request(state: GameState, content: Content, f: Feast, text: str) -> ToastRequest:
    ch = content.characters.get(f.host)
    persona = "；".join(x for x in ((ch.personality if ch else ""), (ch.situation if ch else "")) if x)
    host_side = figure_life.side_of(content, f.host)
    p = state.player
    side = p.ally or p.faction
    return ToastRequest(
        feast=f.id, host=f.host, host_name=host_name(content, f),
        host_side=content.scenario.faction_name(host_side, host_side or "") if host_side else "",
        persona=persona[:200], mood=figure_life.mood_any(state, content, f.host) or "", place=_place(content, f.place),
        name=p.name, side=content.scenario.faction_name(side, side or "") if side else "散人", sex=gender.of(p), text=text,
    )


_PROMPT_UNSAFE = re.compile(r"[「」『』\"“”‘’'`\x00-\x1f\x7f]+")  # 同 zh.PROMPT_UNSAFE（功能包不 import 還沒搬的 zh）


def _prompt_safe(text: str) -> str:
    """名號、敬酒詞放進提示以前夾掉引號與換行（M-13，同 zh.prompt_safe）。"""
    return _PROMPT_UNSAFE.sub("", str(text or ""))


def score(client, req: ToastRequest) -> int:
    """B 段：主人聽了這一句有多高興（0～100 的整數）。同決戰放手一搏的評分：短提示、只回一個整數。評不到回 DEFAULT_SCORE。"""
    if client is None:
        return DEFAULT_SCORE
    messages = [
        {"role": "system", "content": (
            f"你是東漢末年的{req.host_name}（{req.host_side or '在野'}）。{req.persona}\n"
            f"你在{req.place}設宴，席間有客人向你敬了一句酒。只回 0~100 的整數 score：你聽了有多高興、多記得住這一句。"
            "得體、有趣、切合你的身分與此刻局勢的給高分；平淡的給中間；灌水、亂寫、冒犯你的給低分。"
            "對方站在跟你敵對的那一方、說的是挑釁的話，照你聽了的感受給分。"
        )},
        {"role": "user", "content": (
            (f"你此刻的心事：{req.mood}\n" if req.mood else "")
            + f"敬酒的人：{_prompt_safe(req.name)}（{req.side}{'，女子' if req.sex == '女' else ''}）\n"
            f"敬酒詞：「{_prompt_safe(req.text)}」"  # 名號、敬酒詞夾掉引號與換行（M-13）
        )},
    ]
    try:
        result = client.chat_structured(messages, ToastScore, temperature=0.3, num_predict=SCORE_PREDICT, required_fields=["score"])
    except Exception:
        return DEFAULT_SCORE
    return max(0, min(100, int(result.score)))


def text_problem(text: str) -> str | None:
    if not text or len(text) > TOAST_LIMIT:
        return BAD_TEXT
    return None

