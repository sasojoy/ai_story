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

CAST_MAX = 6  # 名錄最多寫幾個人
GAMBLES_PER_ACT = 2  # 一幕最多挑幾次放手一搏寫成拍子（整篇才讀得下去）
SCENE_MAX = 90  # 模型寫的一拍散文上限（字）
HEAD_MAX = 6  # 一拍的小標上限（字）
CAST_LINE_MAX = 40  # 名錄一句的上限（字）
NUM_PREDICT = 1400  # 一次把整篇寫完的預算的下限（小場面）
# 預算照篇幅加（2026-10-31 主機實測：9 拍＋6 人的名錄 1400 寫得完，線上 12 拍＋6 人那一篇缺了 cast、整篇變模板句）。
# 一拍九十字的散文加小標、JSON 的框，名錄一句四十字；只是上限，寫完就停，給寬不花時間
PREDICT_PER_SCENE = 150
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


class TaleReply(BaseModel):
    scenes: list[SceneLine] = Field(default_factory=list)
    cast: list[CastLine] = Field(default_factory=list)


SYSTEM = (
    "你是東漢末年的說書人，替剛打完的一場大戰寫話本。下面每一「拍」都是真的發生過的事，"
    "替每一拍寫一小段：兩三句、九十字以內、繁體中文、半文白、第三人稱，用名號稱呼人。"
    "只寫那一拍寫到的事，不要編造清單上沒有的人名、地名、兵器、傷亡，也不要改變勝負。"
    "**不要寫任何阿拉伯數字**，不要寫標題編號、列點、不要提到遊戲、系統、玩家。"
    "有些拍子附了那個人當場喊的原話：原話會另外原樣引在那一段底下，散文裡**不要引用、不要轉述那句話**，寫他怎麼做、場面怎麼變。"
    "每一拍只寫那一拍的主角，不要把別一拍的人寫進來。"
    "head 是那一拍的小標（六個字以內，可以留空）。"
    "另外替名錄上每個人各寫一句（四十字以內）：照給的事實寫，不要加沒給的戰績。"
    "回傳 scenes（每一拍一筆，id 照抄）與 cast（每個人一筆，name 照抄）。"
)


def messages(material: Material) -> list[dict[str, str]]:
    lines: list[str] = []
    for act in material.acts:
        lines.append(f"【{act.title}】{act.setting}")
        for beat in act.beats:
            said = f"（他當場喊的是「{beat.said.line}」，這句會另外引在底下，散文裡不要引）" if beat.said is not None else ""
            lines.append(f"  {beat.id}：{beat.fact}{said}")
    cast = "\n".join(f"- {c.name}（{c.side}）：{c.fact}" for c in material.cast)
    body = (
        f"這一場：{material.battle_name}\n結果：{material.result}"
        + (f"（{material.reason}）" if material.reason else "")
        + "\n\n" + "\n".join(lines) + f"\n\n名錄：\n{cast}"
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}]


def clean(raw: str, limit: int) -> str:
    """模型寫的一段驗過才用：轉繁體、去掉標記；有阿拉伯數字、太長、提到遊戲的丟掉（回空字串）。換行留著（網頁一行一段）。"""
    text = zh.to_traditional(str(raw or ""))
    text = re.sub(r"[*#>`]+", "", text)
    text = re.sub(r"[ \t　]+", "", text).strip("\n").strip("「」『』\"'“”")
    if not text or len(text) > limit or _DIGITS.search(text) or any(w in text for w in _BANNED):
        return ""
    return text


def predict_budget(material: Material) -> int:
    """這一篇給模型的輸出上限：照拍數與名錄人數加，不低於 NUM_PREDICT。"""
    beats = sum(len(act.beats) for act in material.acts)
    return max(NUM_PREDICT, PREDICT_BASE + PREDICT_PER_SCENE * beats + PREDICT_PER_CAST * len(material.cast))


OTHER_NAME_MIN = 2  # 「寫到別的上陣的人」不認一個字的名號：單字（「霜」「城」）常常只是散文裡的普通字，會把該留的拍誤退成模板句


def _bare(text: str) -> str:
    """比對原話用：只留字，標點、空白都拿掉。"""
    return re.sub(r"[\W_]+", "", text)


def fits(beat: BeatFacts, text: str, others: Sequence[str]) -> bool:
    """模型寫的這一拍對不對得上這一拍（2026-10-31 線上那一篇：原話在散文裡又抄一次、第二拍寫成第三拍的人）。
    只看附了原話的那幾拍（放手一搏）：散文不准抄原話（原話底下另外引）、要寫到喊話的那個人、
    不准寫到別的上陣的人（別一拍的主角）。開篇、倒下、戰局那幾拍寫到誰都照收。"""
    if beat.said is None:
        return True
    line = _bare(beat.said.line)
    if len(line) >= 2 and line in _bare(text):
        return False
    if beat.said.who and beat.said.who not in text:
        return False
    return not any(len(name) >= OTHER_NAME_MIN and name in text and name not in beat.said.who for name in others)


def _gamblers(material: Material) -> tuple[str, ...]:
    """別一拍的主角：整篇放手一搏那幾拍喊話的人。只拿他們比（不拿全部上陣的人）：配錯是拍子之間互換，名單越短越少誤判。"""
    return tuple(sorted({b.said.who for a in material.acts for b in a.beats if b.said is not None and b.said.who}))


def write(client, material: Material) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """B 段（鎖外）：請模型把整篇寫完。回（拍子 id → (小標, 散文), 名號 → 那一句）；叫不動、寫壞的不在裡面（照引擎那一句）。"""
    if client is None:
        return {}, {}
    try:
        reply = client.chat_structured(
            messages(material), TaleReply, temperature=0.8, num_predict=predict_budget(material),
            # 兩個欄位都有預設值：不寫進 required（而且語法強制）的話，模型回 {} 也算合法，整篇靜靜變成模板版
            required_fields=["scenes", "cast"], require_in_schema=True,
        )
    except Exception:  # noqa: BLE001 — 叫不動就用模板
        return {}, {}
    beats = {beat.id: beat for act in material.acts for beat in act.beats}
    names = {c.name for c in material.cast}
    others = _gamblers(material)
    scenes: dict[str, tuple[str, str]] = {}
    for s in reply.scenes:
        text = clean(s.text, SCENE_MAX)
        if s.id in beats and s.id not in scenes and text and fits(beats[s.id], text, others):
            scenes[s.id] = (clean(s.head, HEAD_MAX), text)
    seen: dict[str, int] = {}
    for _head, text in scenes.values():
        seen[text] = seen.get(text, 0) + 1
    scenes = {k: v for k, v in scenes.items() if seen[v[1]] == 1}  # 同一段字掛在兩拍上：至少一拍配錯了，兩拍都照引擎那一句
    cast = {c.name: clean(c.line, CAST_LINE_MAX) for c in reply.cast if c.name in names and clean(c.line, CAST_LINE_MAX)}
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
            Scene(head=scenes.get(beat.id, ("", ""))[0], text=scenes.get(beat.id, ("", beat.fact))[1] or beat.fact,
                  said=beat.said)
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
