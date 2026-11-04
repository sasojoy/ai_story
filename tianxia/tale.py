"""戰記（Joy 2026-10-29，原稱「戰役話本」）：決戰收場之後，說書人把那一場寫成一篇話本，全服一份。
戰報頁右上的「戰記 ›」與江湖史的目錄都讀它（畫面在 `web/app.js` 的 taleLink／taleHtml／taleIndexHtml，
契約見 `tests/web/test_tale_web.py`）；產生、寫法、存放在這裡與 `server.py`。

分工照總則（CLAUDE.md「數值全部由規則引擎決定」）：

- **引擎給料**：幾幕、每一幕的時辰行、哪一邊佔上風、誰在哪一幕倒下、名錄挑誰，以及**玩家原話一字不改**（Scene.said）。
- **模型只寫字**：每一拍的小標與散文、名錄上每個人那一句。寫壞、叫不動就用引擎自己那一句（plain），
  不讓玩家一直卡在「史官還在落筆」（照「走一趟」遊記 outing.template_tale 的做法）。

這一份不讀電腦時鐘：時辰行由呼叫端算好傳進來（stamp），made_at 也是傳進來的。
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from . import zh
from .battle_instance import CENTER, BattleInstance, BattleRoundRecord, GambleMoment
from .models import BattleDef

CAST_MAX = 8  # 名錄最多寫幾個人（企劃者 2026-11-04「篇幅都很短」：原本 6，11 人的場子漏掉一半）
GAMBLES_PER_ACT = 4  # 一幕最多挑幾次放手一搏寫成拍子（同上：原本 2——廣宗那一場真的發生 24 次，整篇只寫得出 6 次）
SCENE_MAX = 120  # 模型寫的一拍散文上限（字）（同上：原本 90。提示詞裡寫成中文「一百二十」，改這裡要一起改）
HEAD_MAX = 6  # 一拍的小標上限（字）
CAST_LINE_MAX = 40  # 名錄一句的上限（字）
NUM_PREDICT = 1400  # 一趟的預算的下限（小場面）
# **一幕一趟、名錄一趟**（企劃者 2026-11-04 要更長、更連貫）：以前整篇一趟，而 within_budget 把單趟逾時壓到剩下的一半
# （180 秒的預算＝一趟 90 秒），拍子一多就寫不完、整篇靜靜變成墊底句（2026-10-31 線上 12 拍那一篇就是）。
# 拆開之後每一趟都比以前小，壞掉也只壞那一幕；總時間由呼叫端的 next_client 把關。
# 一拍一百二十字的散文加小標、JSON 的框，名錄一句四十字；只是上限，寫完就停，給寬不花時間
PREDICT_PER_SCENE = 190
PREDICT_PER_CAST = 70
PREDICT_BASE = 200

_DIGITS = re.compile(r"[0-9０-９]")  # 模型不准寫阿拉伯數字（數字只能是引擎的；引擎自己那幾句用中文數字）
_BANNED = ("遊戲", "系統", "玩家", "伺服器", "假人", "機器人", "bot", "BOT", "Bot")  # 「假人」那幾個字任何地方都不准出現
_ZH = ("零", "一", "兩", "三", "四", "五", "六", "七", "八", "九", "十")

TITLE_SUFFIX = "戰記"  # 標題一律「<戰名>戰記」（Joy 2026-10-29 改名時定的）
LEAD_LINE = "{side}壓了上去。"  # 待 joy 潤
EVEN_LINE = "兩邊誰也沒佔到便宜。"
FELL_LINE = "{names}倒在這一幕。"
GAMBLE_WON_LINE = "{name}放手一搏，成了。"
GAMBLE_LOST_LINE = "{name}放手一搏，沒成。"
OPEN_LINE = "{name}帶著人馬到了。"
CLOSE_NO = "收場"  # 最後一幕的「回」寫「收場」（前端沒給 no 才寫「第N回」）
CAST_FELL = "倒在第{n}回合。"
CAST_GAMBLE = "放手一搏成了{n}次。"
CAST_LED = "帶頭出手{n}個回合。"
CAST_SLEW = "陣前擊退了{n}位上陣的人物。"
CAST_STOOD = "挨了打還站著。"


def _count(n: int) -> str:
    """數量的中文（「兩次」不寫「二次」）；十以上寫「好幾」。"""
    return _ZH[n] if 0 <= n <= 10 else "好幾"


# ── 回給網頁的形狀（欄位名就是 /api/tale 的契約）────────────────────────────


class Said(BaseModel):
    """玩家原話：網頁畫成金線引言、自己加「」。一字不改，不經過模型。"""

    who: str
    side: str = ""
    line: str


class Scene(BaseModel):
    head: str = ""  # 小標；空的網頁就不畫
    text: str  # 散文，換行分段
    said: Said | None = None


class Act(BaseModel):
    title: str
    no: str = ""  # 不給網頁寫「第N回」；收場那一幕給「收場」
    banner: str = ""  # 這一幕最上面的時辰行
    scenes: list[Scene] = Field(default_factory=list)


class CastEntry(BaseModel):
    name: str
    side: str = ""
    line: str


class Tale(BaseModel):
    status: str = "ready"
    title: str
    season: int
    battle_name: str
    result: str
    acts: list[Act] = Field(default_factory=list)
    cast: list[CastEntry] = Field(default_factory=list)
    made_at: float = 0.0


# ── 引擎備的料 ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BeatFacts:
    """一拍：引擎認定「這裡有戲」的一件事。fact 是引擎自己寫的那一句（模型寫壞就用它），said 是玩家原話。"""

    id: str  # 「2-1」＝第二幕第一拍（模型照這個鍵回）
    fact: str
    said: Said | None = None
    # 以下三樣戰報本來就有、以前沒帶進戰記（企劃者 2026-11-04「玩家有點另一個玩家，在戰報中有的互動到戰記被輕輕一筆帶過」）
    target: str = ""  # 這一下點名衝著誰（GambleMoment.target）；沒點名是空的
    won: bool | None = None  # 成了沒（None＝不是放手一搏那種拍子）
    story: str = ""  # 戰報當場播出去的那一句（玩家已經讀過）：模型照它接著鋪開，模型寫壞也拿它當墊底，不要退回「某某放手一搏，成了」


@dataclass(frozen=True)
class ActFacts:
    title: str
    banner: str
    setting: str  # 這一幕的情境（BattleAct.text），只給模型當背景，不直接寫進戰記
    beats: tuple[BeatFacts, ...]


@dataclass(frozen=True)
class CastFacts:
    name: str
    side: str
    fact: str


@dataclass(frozen=True)
class Material:
    """寫一篇戰記要的全部料（都是引擎算好的事實）。"""

    record_id: int
    season: int
    battle_name: str
    result: str
    reason: str  # 勝負的關鍵（BattleInstance.outcome_reason）；沒有是空的
    acts: tuple[ActFacts, ...]
    cast: tuple[CastFacts, ...]

    @property
    def title(self) -> str:
        return f"{self.battle_name}{TITLE_SUFFIX}"


def _acts_of_rounds(rounds: Sequence[BattleRoundRecord]) -> dict[int, list[BattleRoundRecord]]:
    """回合照幕分組（照回合自己記的 act_index，不重算換幕）。"""
    out: dict[int, list[BattleRoundRecord]] = {}
    for r in rounds:
        out.setdefault(r.act_index, []).append(r)
    for group in out.values():
        group.sort(key=lambda r: (r.round_number, r.id or 0))
    return out


def _lead_line(rounds: Sequence[BattleRoundRecord], names: dict[str, str], sides: Sequence[str]) -> str:
    """這一幕打完戰局偏向誰（只寫一句話，不寫數字：戰況變化不對玩家露數字）。"""
    if not rounds or len(sides) < 2:
        return EVEN_LINE
    trend = rounds[-1].trend_after
    if trend == CENTER:
        return EVEN_LINE
    side = sides[0] if trend > CENTER else sides[1]
    return LEAD_LINE.format(side=names.get(side, side))


def _dramatic(moments: Sequence[GambleMoment], highlight: GambleMoment | None) -> list[GambleMoment]:
    """這一幕挑哪幾次放手一搏：全場最有戲的那一次先（highlight），其餘成功的先、名號排序定序（同一場每次挑出來一樣）。"""
    picked = [m for m in moments if highlight is not None and (m.name, m.round) == (highlight.name, highlight.round)]
    rest = sorted((m for m in moments if m not in picked), key=lambda m: (m.won is False, m.round, m.name))
    return (picked + rest)[:GAMBLES_PER_ACT]


def gather(
    definition: BattleDef, instance: BattleInstance, rounds: Sequence[BattleRoundRecord], *,
    season: int, side_names: dict[str, str], stamp: Callable[[float], str] = lambda _: "",
) -> Material:
    """把收場的一場決戰整理成寫戰記的料。只讀，不碰狀態、不叫模型、不讀時鐘（時辰行走 stamp）。"""
    sides = [f.id for f in definition.factions]
    by_act = _acts_of_rounds(rounds)
    act_of_round = {r.round_number: r.act_index for r in rounds}
    acts: list[ActFacts] = []
    for index, act in enumerate(definition.acts):
        group = by_act.get(index, [])
        if index and not group:  # 壓倒性提前收場：沒打到的幕不寫（第一幕一定寫，哪怕沒結算過回合）
            continue
        beats: list[BeatFacts] = []
        if not index:  # 開篇那一拍：誰到了
            lead = sorted({p.faction for p in instance.participants.values() if p.faction in sides})
            who = "、".join(side_names.get(s, s) for s in lead) or side_names.get(sides[0], sides[0])
            beats.append(BeatFacts(id="1-1", fact=OPEN_LINE.format(name=who)))
        moments = [
            m for p in instance.participants.values() for m in p.gambles
            if act_of_round.get(m.round, -1) == index and m.text
        ]
        for moment in _dramatic(moments, instance.highlight):
            line = GAMBLE_WON_LINE if moment.won else GAMBLE_LOST_LINE
            beats.append(BeatFacts(
                id=f"{index + 1}-{len(beats) + 1}",
                fact=line.format(name=moment.name),
                said=Said(who=moment.name, side=side_names.get(moment.faction, moment.faction), line=moment.text),
                target=moment.target, won=moment.won, story=moment.story,
            ))
        numbers = {r.round_number for r in group}
        fallen = sorted(p.name for p in instance.participants.values() if p.fell_round in numbers)
        if fallen:
            beats.append(BeatFacts(id=f"{index + 1}-{len(beats) + 1}", fact=FELL_LINE.format(names="、".join(fallen[:3]))))
        beats.append(BeatFacts(id=f"{index + 1}-{len(beats) + 1}", fact=_lead_line(group, side_names, sides)))
        banner = stamp(group[0].resolved_real) if group else ""
        acts.append(ActFacts(title=act.title, banner=banner, setting=act.text, beats=tuple(beats)))
    return Material(
        record_id=instance.record_id or 0, season=season, battle_name=definition.name,
        result=instance.outcome_title or "", reason=instance.outcome_reason,
        acts=tuple(acts), cast=tuple(_cast(instance, side_names)),
    )


def _cast(instance: BattleInstance, side_names: dict[str, str]) -> list[CastFacts]:
    """名錄挑誰：最有戲的那一搏先，其餘照「搏成幾次、擊退幾人、帶頭幾回合、倒下」排；一人一句事實，模型照它寫。"""
    people = list(instance.participants.values())
    highlight = instance.highlight.name if instance.highlight is not None else ""

    def rank(p) -> tuple:
        return (p.name != highlight, -p.gambles_won, -p.slew, -p.led_rounds, -p.hurt_dealt, p.name)

    out: list[CastFacts] = []
    for p in sorted(people, key=rank)[:CAST_MAX]:
        if p.gambles_won:
            fact = CAST_GAMBLE.format(n=_count(p.gambles_won))
        elif p.slew:
            fact = CAST_SLEW.format(n=_count(p.slew))
        elif p.led_rounds:
            fact = CAST_LED.format(n=_count(p.led_rounds))
        elif p.stood_marked:
            fact = CAST_STOOD
        else:
            fact = ""
        if p.fell_round:
            fact = (fact + CAST_FELL.format(n=_count(p.fell_round))).strip()
        out.append(CastFacts(name=p.name, side=side_names.get(p.faction, p.faction), fact=fact or CAST_STOOD))
    return out


# ── 請模型寫（鎖外；server 的三段式 B 段）──────────────────────────────


class SceneLine(BaseModel):
    id: str
    head: str = ""
    text: str


class CastLine(BaseModel):
    name: str
    line: str


class ActReply(BaseModel):  # 一幕一趟
    scenes: list[SceneLine] = Field(default_factory=list)


class CastReply(BaseModel):  # 名錄一趟
    cast: list[CastLine] = Field(default_factory=list)


SYSTEM = (
    "你是東漢末年的說書人，替剛打完的一場大戰寫話本。下面每一「拍」都是真的發生過的事，照順序替這一幕的每一拍寫一小段："
    "三到五句、一百二十字以內、繁體中文、半文白、第三人稱，用名號稱呼人。"
    "**這一幕要像一段連著的文字**：後一拍接著前一拍寫（前一拍誰得了手、誰倒下、戰線往哪邊去，下一拍接得上），"
    "不要每一拍都從頭開始、不要每一拍都重講一次戰局。"
    "不要編造清單上沒有的人名、地名、兵器、傷亡，也不要改變勝負。"
    "**不要寫任何阿拉伯數字**，不要寫標題編號、列點、不要提到遊戲、系統、玩家。"
    "有些拍子附了那個人當場喊的原話：原話會另外原樣引在那一段底下，散文裡**不要引用、不要轉述那句話**，寫他怎麼做、場面怎麼變。"
    "寫了「衝著誰」的那一拍，**那兩個人都要寫到**：寫他們怎麼碰上、對手怎麼應、這一下成了沒有。"
    "除此之外一拍只寫那一拍的主角，不要把別一拍的主角寫進來。"
    "附了「戰報上寫的是」的拍子，照那一句接著鋪開（同一件事寫細、寫進場面裡），不要改掉結果、也不要只是照抄。"
    "head 是那一拍的小標：六個字以內、**每一拍都要給**，像章回的小標（例：「火起糧倉」「城頭斷箭」）。"
    "回傳 scenes（這一幕每一拍一筆，id 照抄）。"
)

CAST_SYSTEM = (
    "你是東漢末年的說書人，替剛打完的一場大戰寫話本的名錄。替名錄上每個人各寫一句（四十字以內）、繁體中文、半文白、第三人稱："
    "照給的事實寫，不要加沒給的戰績、不要改變勝負。"
    "**不要寫任何阿拉伯數字**，不要寫列點、不要提到遊戲、系統、玩家。每一句都用他的名號開頭。"
    "回傳 cast（每個人一筆，name 照抄）。"
)


def _beat_line(beat: BeatFacts) -> str:
    """一拍寫給模型的那一行：引擎的事實，加上戰報有、以前沒帶進來的那幾樣（點名、成敗、當場播的那一句）。"""
    bits: list[str] = []
    if beat.said is not None:
        bits.append(f"他當場喊的是「{beat.said.line}」，這句會另外原樣引在底下，散文裡不要引、不要轉述")
    if beat.target:
        bits.append(f"**衝著{beat.target}來的**，這一拍要寫到{beat.target}怎麼應")
    if beat.won is not None:
        bits.append("這一下成了" if beat.won else "這一下沒成")
    if beat.story:
        bits.append(f"戰報上寫的是「{beat.story}」")
    return f"  {beat.id}：{beat.fact}" + (f"（{'；'.join(bits)}）" if bits else "")


def _head(material: Material) -> str:
    """每一趟都給的開頭：哪一場、結果，還有整場分幾幕（寫一幕的時候也知道自己在整篇的哪裡）。"""
    acts = "、".join(f"「{a.title}」" for a in material.acts)
    return (
        f"這一場：{material.battle_name}\n結果：{material.result}"
        + (f"（{material.reason}）" if material.reason else "")
        + (f"\n整場分這幾幕：{acts}" if acts else "")
    )


def act_messages(material: Material, act: ActFacts) -> list[dict[str, str]]:
    """一幕一趟（企劃者 2026-11-04）：只給這一幕的拍子，整場的輪廓在開頭那幾行。"""
    lines = "\n".join(_beat_line(beat) for beat in act.beats)
    body = f"{_head(material)}\n\n要寫的是這一幕——【{act.title}】{act.setting}\n{lines}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}]


def cast_messages(material: Material) -> list[dict[str, str]]:
    cast = "\n".join(f"- {c.name}（{c.side}）：{c.fact}" for c in material.cast)
    return [{"role": "system", "content": CAST_SYSTEM},
            {"role": "user", "content": f"{_head(material)}\n\n名錄：\n{cast}"}]


def _without_names(text: str, names: Sequence[str]) -> str:
    """比對「模型自己寫的字」用：把場上的名號從句子裡挖掉（長的先挖）。
    名號裡本來就有阿拉伯數字（管理者建的角色，例「Rayal2」）時不挖的話，只要提到他整句都會被數字那一關丟掉——
    企劃者 2026-11-04 讀到的那一篇裡，24 次放手一搏有 7 次旁白是空的、7 次都是提到他，戰記那兩拍也退成了墊底句。"""
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        text = text.replace(name, "")
    return text


def clean(raw: str, limit: int, names: Sequence[str] = ()) -> str:
    """模型寫的一段驗過才用：轉繁體、去掉標記；有阿拉伯數字、太長、提到遊戲的丟掉（回空字串）。換行留著（網頁一行一段）。
    names 是場上的名號：數字那一關不算名號裡本來就有的（_without_names）。"""
    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[*#>`]+", "", text)
    text = re.sub(r"[ \t　]+", "", text).strip("\n").strip("「」『』\"'“”")
    if not text or len(text) > limit or any(w in text for w in _BANNED):
        return ""
    return "" if _DIGITS.search(_without_names(text, names)) else text


def act_budget(act: ActFacts) -> int:
    """這一幕給模型的輸出上限：照拍數加，不低於 NUM_PREDICT。只是上限，寫完就停。"""
    return max(NUM_PREDICT, PREDICT_BASE + PREDICT_PER_SCENE * len(act.beats))


def cast_budget(material: Material) -> int:
    """名錄那一趟的輸出上限。"""
    return max(NUM_PREDICT, PREDICT_BASE + PREDICT_PER_CAST * len(material.cast))


OTHER_NAME_MIN = 2  # 「寫到別的上陣的人」不認一個字的名號：單字（「霜」「城」）常常只是散文裡的普通字，會把該留的拍誤退成模板句


def _bare(text: str) -> str:
    """比對原話用：只留字，標點、空白都拿掉。"""
    return re.sub(r"[\W_]+", "", text)


def fits(beat: BeatFacts, text: str, others: Sequence[str]) -> bool:
    """模型寫的這一拍對不對得上這一拍（2026-10-31 線上那一篇：原話在散文裡又抄一次、第二拍寫成第三拍的人）。
    只看附了原話的那幾拍（放手一搏）：散文不准抄原話（原話底下另外引）、要寫到喊話的那個人、
    不准寫到別的上陣的人（別一拍的主角）。開篇、倒下、戰局那幾拍寫到誰都照收。

    **他點名的那個對手不算「別一拍的主角」**（企劃者 2026-11-04「玩家有點另一個玩家，在戰報中有的互動到戰記被輕輕一筆帶過」）：
    以前對手剛好也被挑成拍子的話，寫出這兩個人交手就整段被退成墊底句——想看的互動是這一關擋掉的。"""
    if beat.said is None:
        return True
    line = _bare(beat.said.line)
    if len(line) >= 2 and line in _bare(text):
        return False
    if beat.said.who and beat.said.who not in text:
        return False
    kin = (beat.said.who, beat.target)  # 這一拍的主角與他點名的對手（接起來比會多出「馬上」這種假的子字串，所以一個一個比）
    return not any(len(name) >= OTHER_NAME_MIN and name in text and not any(name in one for one in kin)
                   for name in others)


def _gamblers(material: Material) -> tuple[str, ...]:
    """別一拍的主角：整篇放手一搏那幾拍喊話的人。只拿他們比（不拿全部上陣的人）：配錯是拍子之間互換，名單越短越少誤判。"""
    return tuple(sorted({b.said.who for a in material.acts for b in a.beats if b.said is not None and b.said.who}))


def known_names(material: Material) -> tuple[str, ...]:
    """場上的名號（名錄上的、喊話的、被點名的）：數字那一關不算它們裡面本來就有的數字（_without_names）。"""
    out = {c.name for c in material.cast}
    for act in material.acts:
        for beat in act.beats:
            if beat.said is not None:
                out.add(beat.said.who)
            out.add(beat.target)
    return tuple(sorted(n for n in out if n))


_INLINE_HEAD = re.compile(r"^[\s]*[【〔]([^】〕\n]{1,10})[】〕][\s　]*")


def _head_out(head: str, text: str) -> tuple[str, str]:
    """小標寫進散文開頭了就挖出來（2026-11-04 第 8 季廣宗實測：head 欄 17 拍全空，模型把小標寫成散文第一行的
    「【雙軍對峙】」）。head 有預設值＝可省略，模型就用自己的方式給；提示詞講幾次都一樣，所以在這裡收。
    挖在 clean 之前：不然【小標】會一起算進那一拍的字數上限。"""
    if head.strip():
        return head, text
    m = _INLINE_HEAD.match(text or "")
    return (m.group(1), text[m.end():]) if m else (head, text)


def _write_act(client, material: Material, act: ActFacts, names: Sequence[str],
               others: Sequence[str]) -> dict[str, tuple[str, str]]:
    """一幕一趟：回這一幕的（拍子 id → (小標, 散文)）。叫不動、寫壞的不在裡面（那幾拍照引擎那一句）。"""
    try:
        reply = client.chat_structured(
            act_messages(material, act), ActReply, temperature=0.8, num_predict=act_budget(act),
            # scenes 有預設值：不寫進 required（而且語法強制）的話，模型回 {} 也算合法，這一幕靜靜變成墊底句
            required_fields=["scenes"], require_in_schema=True,
        )
    except Exception:  # noqa: BLE001 — 叫不動就用墊底句
        return {}
    beats = {beat.id: beat for beat in act.beats}
    out: dict[str, tuple[str, str]] = {}
    for s in reply.scenes:
        raw_head, raw_text = _head_out(s.head, s.text)
        text = clean(raw_text, SCENE_MAX, names)
        if s.id in beats and s.id not in out and text and fits(beats[s.id], text, others):
            out[s.id] = (clean(raw_head, HEAD_MAX, names), text)
    return out


def _write_cast(client, material: Material, names: Sequence[str]) -> dict[str, str]:
    """名錄那一趟：回（名號 → 那一句）。"""
    try:
        reply = client.chat_structured(
            cast_messages(material), CastReply, temperature=0.8, num_predict=cast_budget(material),
            required_fields=["cast"], require_in_schema=True,
        )
    except Exception:  # noqa: BLE001
        return {}
    want = {c.name for c in material.cast}
    lines = ((c.name, clean(c.line, CAST_LINE_MAX, names)) for c in reply.cast)
    return {name: line for name, line in lines if name in want and line}


def write(client, material: Material, *,
          next_client: Callable[[], object] | None = None) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """B 段（鎖外）：**一幕一趟、名錄一趟**請模型寫（企劃者 2026-11-04 要更長、更連貫；以前整篇一趟）。
    回（拍子 id → (小標, 散文), 名號 → 那一句）；叫不動、寫壞的不在裡面（照引擎那一句）。

    `next_client` 每一趟給一個新的 client（呼叫端照剩下的時間重算預算，回 None＝時間用完了，剩下的照引擎那一句）；
    不給就每一趟都用同一個。時間的帳在呼叫端算：這一份不讀電腦時鐘。"""
    names = known_names(material)
    others = _gamblers(material)
    scenes: dict[str, tuple[str, str]] = {}
    use = client
    for act in material.acts:
        if use is None:
            break  # 預算用完了：剩下的幕照引擎那一句（只少那幾幕，不是整篇垮掉）
        scenes.update(_write_act(use, material, act, names, others))
        use = next_client() if next_client is not None else client
    seen: dict[str, int] = {}
    for _small, text in scenes.values():
        seen[text] = seen.get(text, 0) + 1
    scenes = {k: v for k, v in scenes.items() if seen[v[1]] == 1}  # 同一段字掛在兩拍上：至少一拍配錯了，兩拍都照引擎那一句
    cast = _write_cast(use, material, names) if use is not None else {}
    return scenes, cast


# ── 組成整篇 ──────────────────────────────────────────────────────────


def compose(
    material: Material, scenes: dict[str, tuple[str, str]] | None = None,
    cast_lines: dict[str, str] | None = None, *, made_at: float = 0.0,
) -> Tale:
    """引擎的料 ＋ 模型寫的字 → 一篇戰記。模型沒寫到的那一拍照引擎自己那一句（所以一定有東西可看）。"""
    scenes = scenes or {}
    cast_lines = cast_lines or {}
    acts: list[Act] = []
    for index, act in enumerate(material.acts):
        drawn = [
            # 墊底的順序：模型寫的 → 戰報當場播的那一句（玩家已經讀過，接得上）→ 引擎的「某某放手一搏，成了」
            # （企劃者 2026-11-04「有些直接寫放手一搏成了，感覺根本沒讀懂他的行為」）
            Scene(head=scenes.get(beat.id, ("", ""))[0],
                  text=scenes.get(beat.id, ("", ""))[1] or beat.story or beat.fact, said=beat.said)
            for beat in act.beats
        ]
        acts.append(Act(title=act.title, banner=act.banner, scenes=drawn,
                        no=CLOSE_NO if index == len(material.acts) - 1 and index else ""))
    cast = [CastEntry(name=c.name, side=c.side, line=cast_lines.get(c.name) or c.fact) for c in material.cast]
    return Tale(title=material.title, season=material.season, battle_name=material.battle_name,
                result=material.result, acts=acts, cast=cast, made_at=made_at)


def plain(material: Material, *, made_at: float = 0.0) -> Tale:
    """模型不在時的戰記：整篇照引擎自己那幾句。"""
    return compose(material, made_at=made_at)


# ── 存放（資料庫旁邊的小檔，不動 SCHEMA_VERSION）─────────────────────────


class TaleStore:
    """寫好的戰記（`<db>-tale.sqlite`；不進遊戲資料庫的結構）。一場一筆：流水號 → 整篇。
    丟了只是那幾場沒有戰記、背景再寫一次。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS tales (record_id INTEGER PRIMARY KEY, season INTEGER NOT NULL, "
                "data TEXT NOT NULL, made_at REAL NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def get(self, record_id: int) -> Tale | None:
        with contextlib.closing(self._conn()) as conn:
            row = conn.execute("SELECT data FROM tales WHERE record_id = ?", (record_id,)).fetchone()
        if not row:
            return None
        try:
            return Tale.model_validate(json.loads(row[0]))
        except Exception:  # noqa: BLE001 — 讀不懂的舊格式當作沒有，背景會重寫
            return None

    def put(self, record_id: int, tale: Tale) -> None:
        """記一篇（同一場寫兩次以先寫的為準：全服看同一篇）。"""
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO tales VALUES (?, ?, ?, ?)",
                         (record_id, tale.season, tale.model_dump_json(), tale.made_at))

    def done(self, season: int) -> set[int]:
        with contextlib.closing(self._conn()) as conn:
            return {r[0] for r in conn.execute("SELECT record_id FROM tales WHERE season = ?", (season,))}

    def listing(self, season: int) -> list[tuple[int, Tale]]:
        """那一季寫好的戰記，新的在前（江湖史的目錄）：（流水號, 整篇）。"""
        with contextlib.closing(self._conn()) as conn:
            rows = conn.execute("SELECT record_id, data FROM tales WHERE season = ? ORDER BY record_id DESC",
                                (season,)).fetchall()
        out: list[tuple[int, Tale]] = []
        for record_id, data in rows:
            with contextlib.suppress(Exception):
                out.append((record_id, Tale.model_validate(json.loads(data))))
        return out
