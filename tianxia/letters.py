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

from . import bounties, calendar, errands, figure_life, gender, prologue, rules, zh
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


def mail_day(content: Content, world, real_now: float | None) -> int | None:
    """減法季「09:00 來信」（整合設計第十章，批 9）：現實時間 real_now 落在第幾個送信日——當地 mail_hour（9）點起算的 24 小時
    （時區照 pill_day_utc_offset_hours，跟回體丹同一個）。一個送信日最多一封，所以新的信總是 9 點以後才到。
    減法季的 morning_mail 沒開、或沒給現實時間（舊的呼叫端）回 None，照舊用遊戲日。"""
    if real_now is None or not rules.jianfa(content, world, "morning_mail"):
        return None
    cfg = content.config
    return int((real_now + (cfg.pill_day_utc_offset_hours - cfg.jianfa.mail_hour) * 3600) // 86400)


def deliver(state: GameState, content: Content, real_now: float | None = None) -> list[str]:
    """同步時叫（Game.sync）：過了期限的委託作罷各補一句；這個遊戲日還沒收過信，就看有沒有人該寫一封（道賀先、求援後）。
    減法季的季照送信日算（mail_day，real_now 是 Game.now；伺服器的看守 9 點替開了推播的人先送，Game.morning_mail）。
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
    msgs += errands.lapse(state, content)  # 減法季批 6：託付過了期限作罷、情誼扣（沒有託付的季是空的）
    day = mail_day(content, w, real_now)
    if day is None:
        day = int(w.time // DAY)
    if w.ended or p.letter_day == day or prologue.active(state, content) or not content.characters:
        return msgs
    rng = random.Random(f"書信|{w.tianji}|{p.name}|{day}")
    # 託付 → 道賀 → 邀宴 → 求援（減法季批 6）；託付照它自己的情誼門檻 errand_affinity（PM 2026-10-26），其餘三種照 letter_affinity
    floor = content.config.jianfa.errand_affinity
    errand = errands.offer(state, content, rng, lambda cid: _reachable(state, content, cid, floor))
    if errand is not None:  # 託付的信 errands.give 已經放進信箱
        p.letter_day = day
        return msgs + [errands.ARRIVED.format(who=_name(content, errand.sender))]
    letter = _cheer_letter(state, content) or _feast_letter(state, content) or _help_letter(state, content, rng)
    if letter is None:
        return msgs
    p.letter_day = day
    p.letters.append(letter)
    del p.letters[:-content.config.figure_life.letters_keep]
    return msgs + [ARRIVED.format(who=_name(content, letter.sender))]


def _name(content: Content, cid: str) -> str:
    ch = content.characters.get(cid)
    return ch.name if ch is not None else cid


def _reachable(state: GameState, content: Content, cid: str, floor: int | None = None) -> bool:
    """聯絡得上：能深度對話、情誼到 floor（沒給照 figure_life.letter_affinity；託付另給 Config.jianfa.errand_affinity）、人在場。"""
    ch = content.characters.get(cid)
    need = content.config.figure_life.letter_affinity if floor is None else floor
    return (ch is not None and ch.deep_interaction
            and state.player.affinities.get(cid, 0) >= need
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
    from .features.feast import rules as feasts  # noqa: PLC0415  宴客（功能包）→ figure_life：延後載入

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
    out = {"id": letter.id, "kind": letter.kind, "sender": _name(content, letter.sender), "text": letter.text, "task": None,
           "open": letter.kind == "託付"}  # 開局那一封（opening.py）一到就攤開：人物開口的話要看得到，不是只露一行
    t = letter.task
    if t is not None:
        live = not letter.lapsed and not t.done_by and t.expires > state.world.time
        out["task"] = {"title": bounties.title(content, t), "how": bounties.how(content, t, state),
                       "reward": bounties.commission_reward(state, content, t),
                       "due": f"期限 {bounties.due_text(t, content, state.world)}", "live": live,
                       "state": "辦成了" if t.done_by else "作罷了" if letter.lapsed or not live else ""}
    errand = errands.letter_card(state, content, letter) if letter.kind == "託付" else None
    if errand is not None:  # 減法季批 6：託付的信附那一件（主機側計畫 1.3 的 main.errands 同一筆）；不是託付的信沒有這個鍵
        out["errand"] = errand
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
    if letter is not None and letter.task is None and letter.kind == "託付":
        declined = errands.decline(state, content, letter_id)  # 減法季批 6：託付的信，婉拒那一件（不扣情誼）
        if declined is not None:
            return declined or [NO_LETTER]
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
    errand: bool = False  # 減法季批 6：這封「託付」是人物每週託的那一件（errands.py），不是開局第一分鐘那一封；task 是那一件做什麼


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
    errand = errands.by_letter(state, letter.id) if letter.kind == "託付" and letter.task is None else None
    task = bounties.how(content, letter.task, state) if letter.task else errands.task_text(content, errand) if errand else ""
    return LetterNote(
        id=letter.id, kind=letter.kind, sender=letter.sender, sender_name=_name(content, letter.sender), persona=persona[:200],
        mood=letter.mood, about=letter.about, task=task,
        hero=gender.hero(state.player), player=state.player.name, fixed=letter.text, errand=errand is not None,
    )


def write(client, note: LetterNote) -> str:
    """B 段：請模型照他的口氣把信重寫成一段（繁體、不寫數字、一百二十字內）；不合用回空字串（照固定句）。"""
    if client is None:
        return ""
    if note.kind == "求援":
        what = f"他此刻{note.mood}，寫信向{note.hero}求援，託的事是：{note.task}（事情要寫進信裡，可以換成他的說法）"
    elif note.kind == "託付" and note.errand:  # 減法季批 6：人物每週託的那一件（errands.py）
        what = (f"他照眼下的處境寫信託{note.hero}一件事：{note.task}（事情與地點要寫進信裡，可以換成他的說法；"
                "順口說一句為什麼託給對方、這件事對眼下的戰局有什麼用）")
    elif note.kind == "託付":  # 開局第一分鐘（opening.py）：初到江湖的人，他在城門口開口託第一件事
        what = (f"{note.hero}剛到潁川、還沒投靠任何一方，他看中了這個生面孔，開口託{note.hero}一件事：{note.task}"
                "（事情要寫進信裡，可以換成他的說法；順口說一句為什麼託給一個生面孔）")
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
        result = client.chat_structured(
            messages, LetterText, temperature=0.8, num_predict=LETTER_PREDICT,
            required_fields=["letter"], require_in_schema=True,  # 不開的話每封信都白跑一趟（實測）
        )
    except Exception:
        return ""
    return clean(result.letter, note.player, note.sender_name, note.about, note.task)


def clean(raw: str, *known: str) -> str:
    """known 是提示裡本來就有的字（名號、寫信的人、事由）：英文只能是這些裡面有的（M-07）。"""
    text = zh.to_traditional(str(raw or "")).strip()
    text = re.sub(r"[*#>`_]+", "", text)
    text = re.sub(r"\s+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > WRITE_LIMIT or _DIGITS.search(text) or zh.stray_latin(text, *known):
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
