"""書信與委託（大勢人物擴充第二批「人與人」；Joy 2026-10-18「做」；設計稿
https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2 第五節；數字在 Config.figure_life）。

情誼到 letter_affinity 的人物，在規則觸發時派人送一封信，一人一個遊戲日最多一封：
- 道賀：你剛做了他欣賞的事（figure_life.spread 讓他的情誼往上動的那幾件，記在 PlayerState.cheers），先寫這一種；
- 求援：他此刻的心事是焦慮或悲憤（figure_life.mood_any），附一件委託（討伐、打探、護送，跟懸賞榜同一套；Bounty，motive「委託」，
  只在你身上）。辦成了照 bounties._complete_commission：銀兩 commission_silver、他的情誼 +commission_affinity。
  同一位人物身上還有一件沒辦完的委託就不再寫求援。
寫信用自己一份亂數（天機｜名號｜遊戲日），不碰 Game.rng。信的固定句寫在這裡；伺服器鎖外請模型照他的口氣重寫（write、clean，
三段式：Game.letter_request → write → Game.apply_letter），寫不出來照固定句。宴客的邀請是第三批。
只有 engine 與 server import 它。"""
from __future__ import annotations

import random
import re

from pydantic import BaseModel

from . import bounties, calendar, figure_life, gender, prologue, zh
from .calendar import DAY
from .models import Content
from .state import Bounty, GameState, Letter

TITLE = "書信"  # 江湖紀錄那一則的標題
ARRIVED = "{who}派人送來一封信。"  # 待 joy 潤：江湖紀錄那一句
LAPSED = "【委託】{who}託你的事過了期限，作罷了。"  # 待 joy 潤
DECLINED = "你回了{who}的信，婉拒了這件委託。"  # 待 joy 潤
NO_LETTER = "沒有這封信。"

HELP_TEXT = {  # 待 joy 潤：求援的固定句（模型寫不出來時照這一句）
    "焦慮": "{hero}台鑒：{place}一帶戰事吃緊，我這邊捉襟見肘。念在往日情分，望{hero}助我一臂之力：{task}。",
    "悲憤": "{hero}台鑒：同袍新喪，此仇不共戴天。聽聞{hero}身手了得，望能助我一臂之力：{task}。",
}
CHEER_TEXT = "{hero}台鑒：聽說你{about}，我拍案叫好。他日相見，當浮一大白。"  # 待 joy 潤：道賀的固定句
FEAST_TEXT = "{hero}台鑒：我在{place}略備薄酒，{hero}若得閒，務請光臨。"  # 待 joy 潤：邀宴的固定句（第三批）
THANK_TEXT = "{hero}台鑒：{task}一事，多虧{hero}出手相助，此情銘記於心。"  # 待 joy 潤：求援委託辦成了的道謝（第三批）
HELP_MOODS = ("焦慮", "悲憤")
CHEERS_KEEP = 5
WRITE_LIMIT = 120  # 模型寫的信最多幾個字（超過照固定句）
_DIGITS = re.compile(r"[0-9０-９]")


def on(content: Content) -> bool:
    return figure_life.on(content) and content.config.figure_life.letters


def note_cheer(state: GameState, content: Content, cid: str, text: str) -> None:
    """figure_life.spread 讓 cid 的情誼往上動、情誼到了 letter_affinity：記下來，等著寫道賀信（最多 CHEERS_KEEP 件，舊的先丟）。"""
    if not on(content) or state.player.affinities.get(cid, 0) < content.config.figure_life.letter_affinity:
        return
    state.player.cheers = [c for c in state.player.cheers if not c.startswith(f"{cid}|")] + [f"{cid}|{text}"]
    del state.player.cheers[:-CHEERS_KEEP]


def deliver(state: GameState, content: Content) -> list[str]:
    """同步時叫（Game.sync）：過了期限的委託作罷各補一句；這個遊戲日還沒收過信，就看有沒有人該寫一封（道賀先、求援後）。
    回傳江湖紀錄的句子（標題 TITLE）。開關關著、休季、序章裡什麼都不做。"""
    if not on(content):
        return []
    p, w = state.player, state.world
    msgs = []
    for letter in p.letters:
        t = letter.task
        if t is not None and not letter.lapsed and not t.done_by and t.expires <= w.time:
            letter.lapsed = True
            msgs.append(LAPSED.format(who=_name(content, letter.sender)))
    day = int(w.time // DAY)
    if w.ended or p.letter_day == day or prologue.active(state, content) or not content.characters:
        return msgs
    letter = _cheer_letter(state, content) or _feast_letter(state, content) or _help_letter(state, content, random.Random(f"書信|{w.tianji}|{p.name}|{day}"))
    if letter is None:
        return msgs
    p.letter_day = day
    p.letters.append(letter)
    del p.letters[:-content.config.figure_life.letters_keep]
    return msgs + [ARRIVED.format(who=_name(content, letter.sender))]


def _name(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def _reachable(state: GameState, content: Content, cid: str) -> bool:
    ch = content.characters.get(cid)
    return (ch is not None and ch.deep_interaction
            and state.player.affinities.get(cid, 0) >= content.config.figure_life.letter_affinity
            and figure_life.where(state, content, cid) is not None)


def _next_id(state: GameState) -> int:
    state.player.letter_seq += 1
    return state.player.letter_seq


def _cheer_letter(state: GameState, content: Content) -> Letter | None:
    p = state.player
    while p.cheers:
        cid, _, about = p.cheers.pop(0).partition("|")
        if _reachable(state, content, cid):
            text = CHEER_TEXT.format(hero=gender.hero(p), about=about)
            return Letter(id=_next_id(state), kind="道賀", sender=cid, at=state.world.time, about=about, text=text)
    return None


def _feast_letter(state: GameState, content: Content) -> Letter | None:
    """情誼夠的人物正在擺宴、這一場還沒邀過你、你還沒敬過酒：寫一封邀宴（第三批，feasts.py）。"""
    from . import feasts  # noqa: PLC0415  feasts → figure_life

    if not feasts.on(content):
        return None
    p = state.player
    for f in feasts.open_feasts(state):
        if feasts.toasted(state, f) or not _reachable(state, content, f.host):
            continue
        if any(x.kind == "邀宴" and x.sender == f.host and x.at >= f.start for x in p.letters):
            continue
        place = content.locations[f.place].name if f.place in content.locations else ""
        return Letter(id=_next_id(state), kind="邀宴", sender=f.host, at=state.world.time, about=place,
                      text=FEAST_TEXT.format(hero=gender.hero(p), place=place))
    return None


def thank(state: GameState, content: Content, task: Bounty) -> list[str]:
    """求援委託辦成了（bounties._complete_rally）：那位人物寫一封道謝信（不佔一天一封的額度：是回你的信）。回傳江湖紀錄的句子。"""
    cid = task.figure
    if not on(content) or cid is None or cid not in content.characters:
        return []
    p = state.player
    p.letters.append(Letter(id=_next_id(state), kind="道謝", sender=cid, at=state.world.time,
                            about=bounties.title(content, task),
                            text=THANK_TEXT.format(hero=gender.hero(p), task=bounties.title(content, task))))
    del p.letters[:-content.config.figure_life.letters_keep]
    return [ARRIVED.format(who=_name(content, cid))]


def _help_letter(state: GameState, content: Content, rng: random.Random) -> Letter | None:
    p, w = state.player, state.world
    busy = {b.figure for b in bounties.open_commissions(state, content)}
    asking = [(cid, mood) for cid in content.characters
              if cid not in busy and _reachable(state, content, cid)
              and (mood := figure_life.mood_any(state, content, cid)) in HELP_MOODS]
    rng.shuffle(asking)
    for cid, mood in asking:
        task = commission(state, content, cid, rng)
        if task is None:
            continue
        place = figure_life.where(state, content, cid)
        text = HELP_TEXT[mood].format(hero=gender.hero(p), place=content.locations[place].name if place in content.locations else "",
                                      task=bounties.how(content, task, state))
        return Letter(id=task_id(task), kind="求援", sender=cid, at=w.time, mood=mood, text=text, task=task)
    return None


def task_id(task: Bounty) -> int:
    return int(task.id.removeprefix("c"))


def commission(state: GameState, content: Content, cid: str, rng: random.Random) -> Bounty | None:
    """cid 託的一件事：在他所在的那一區，討伐（他是交戰兩軍、那一區有對頭站著的地方）、打探（危險度 2 以上、不是城鎮）、
    護送（把東西送到那一區另一個城鎮）挑一種。那一區什麼都沒有就照全圖挑。都挑不出來回 None。"""
    from . import atlas  # noqa: PLC0415  atlas → world → rules：延後載入

    w, p = state.world, state.player
    side = figure_life.side_of(content, cid)
    region = figure_life._region(content, figure_life.where(state, content, cid))

    def near(loc_id: str) -> bool:
        found = atlas.region_of(content, loc_id)
        return region is None or (found is not None and found.id == region)

    choices: list[dict] = []
    if side in bounties.ENEMY:
        strikes = [x for x in bounties._strike_spots(content, w, side, set()) if near(x[0])]
        if strikes:
            loc, squad = rng.choice(strikes)
            choices.append({"kind": "strike", "location": loc, "squad": squad})
    scouts = [loc_id for loc_id, loc in content.locations.items()
              if loc.danger >= 2 and not bounties.is_town(content, loc_id) and bounties._opened(loc, w) and near(loc_id)]
    if scouts:
        choices.append({"kind": "scout", "location": rng.choice(scouts)})
    towns = [loc_id for loc_id, loc in content.locations.items()
             if bounties.is_town(content, loc_id) and bounties._opened(loc, w) and loc_id != p.location]
    ends = [t for t in towns if near(t)] or towns
    if ends:
        choices.append({"kind": "escort", "end": rng.choice(ends), "location": p.location})
    if not choices:
        return None
    spec = rng.choice(choices)
    tuning = content.config.figure_life
    return Bounty(
        id=f"c{_next_id(state)}", faction=side if side in bounties.ENEMY else None,
        week=calendar.point(w.time, content, w).week,
        expires=w.time + tuning.commission_days * DAY,
        silver=tuning.commission_silver, deeds=0, figure=cid, motive="委託", **spec,
    )


def unread(state: GameState) -> Letter | None:
    """江湖頁那張小卡畫哪一封：最新一封還沒看過的。"""
    return next((x for x in reversed(state.player.letters) if not x.read), None)


def find(state: GameState, letter_id: int) -> Letter | None:
    return next((x for x in state.player.letters if x.id == letter_id), None)


def view(state: GameState, content: Content) -> dict | None:
    """江湖頁「剛剛」上面那張小卡（server.main_view 的 letter）：沒有沒看過的信是 None。"""
    letter = unread(state)
    if letter is None or not on(content):
        return None
    out = {"id": letter.id, "kind": letter.kind, "sender": _name(content, letter.sender), "text": letter.text, "task": None}
    t = letter.task
    if t is not None:
        live = not letter.lapsed and not t.done_by and t.expires > state.world.time
        out["task"] = {"title": bounties.title(content, t), "how": bounties.how(content, t, state),
                       "reward": bounties.commission_reward(state, content, t),
                       "due": f"期限 {bounties.due_text(t, content, state.world)}", "live": live,
                       "state": "辦成了" if t.done_by else "作罷了" if letter.lapsed or not live else ""}
    return out


def read(state: GameState, letter_id: int) -> list[str]:
    letter = find(state, letter_id)
    if letter is None:
        return [NO_LETTER]
    letter.read = True
    return []


def decline(state: GameState, content: Content, letter_id: int) -> list[str]:
    """婉拒這封信附的委託（不扣情誼：託人辦事，答不答應是你的事）。"""
    letter = find(state, letter_id)
    if letter is None or letter.task is None or letter.lapsed or letter.task.done_by:
        return [NO_LETTER]
    letter.lapsed = letter.read = True
    return [DECLINED.format(who=_name(content, letter.sender))]


# ── 模型照他的口氣重寫（鎖外；server.write_letter）────────────


class LetterNote(BaseModel):
    """還等著模型重寫的那一封（Game.letter_request；C 段照 id 與固定句認同一封）。"""

    id: int
    kind: str
    sender: str
    sender_name: str
    persona: str = ""
    mood: str = ""
    about: str = ""
    task: str = ""
    hero: str
    player: str
    fixed: str


LETTER_MAX = 100  # 提示詞要他寫一百字以內
LETTER_PREDICT = LETTER_MAX * 3 + 120  # 240 不夠：2026-10-19 線上被截斷過（模型會寫超過）


class LetterText(BaseModel):
    letter: str = ""


def request(state: GameState, content: Content) -> LetterNote | None:
    """A 段（只讀）：最新一封還沒重寫過、還沒看過的信。"""
    if not on(content):
        return None
    letter = unread(state)
    if letter is None or letter.written:
        return None
    ch = content.characters.get(letter.sender)
    persona = "；".join(x for x in ((ch.personality if ch else ""), (ch.situation if ch else "")) if x)
    return LetterNote(
        id=letter.id, kind=letter.kind, sender=letter.sender, sender_name=_name(content, letter.sender), persona=persona[:200],
        mood=letter.mood, about=letter.about, task=bounties.how(content, letter.task, state) if letter.task else "",
        hero=gender.hero(state.player), player=state.player.name, fixed=letter.text,
    )


def write(client, note: LetterNote) -> str:
    """B 段：請模型照他的口氣把信重寫成一段（繁體、不寫數字、一百二十字內）；不合用回空字串（照固定句）。"""
    if client is None:
        return ""
    if note.kind == "求援":
        what = f"他此刻{note.mood}，寫信向{note.hero}求援，託的事是：{note.task}（事情要寫進信裡，可以換成他的說法）"
    elif note.kind == "邀宴":
        what = f"他在{note.about}設宴，寫信邀{note.hero}來赴宴（地點要寫進信裡）"
    elif note.kind == "道謝":
        what = f"{note.hero}替他辦成了「{note.about}」，他寫信道謝"
    else:
        what = f"他聽說{note.hero}{note.about}，寫信道賀"
    messages = [
        {"role": "system", "content": (
            f"你是東漢末年的{note.sender_name}。{note.persona}\n"
            f"寫一封很短的信給江湖上的{note.hero}「{note.player}」，用你自己的口氣、半文半白、繁體中文、一百字以內。"
            "稱對方為「" + note.hero + "」或名號；不要寫任何阿拉伯數字，不要寫署名以外的標記，不要寫 markdown。"
        )},
        {"role": "user", "content": f"{what}。\n請給 letter。"},
    ]
    try:
        result = client.chat_structured(messages, LetterText, temperature=0.8, num_predict=LETTER_PREDICT, required_fields=["letter"])
    except Exception:
        return ""
    return clean(result.letter)


def clean(raw: str) -> str:
    text = zh.to_traditional(str(raw or "")).strip()
    text = re.sub(r"[*#>`_]+", "", text)
    text = re.sub(r"\s+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > WRITE_LIMIT or _DIGITS.search(text):
        return ""
    return text


def apply(state: GameState, note: LetterNote, text: str) -> bool:
    """C 段：還是同一封、還沒重寫過、固定句沒動過才換。寫不出來（空字串）也標成寫過了（不再叫模型）。換了是 True。"""
    letter = find(state, note.id)
    if letter is None or letter.written or letter.text != note.fixed:
        return False
    letter.written = True
    if not text:
        return False
    letter.text = text
    return True
