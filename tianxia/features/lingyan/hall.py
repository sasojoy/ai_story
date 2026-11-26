"""凌煙閣的規則：每一季收季之後，從已經跨季存著的紀錄排出那一季上閣的人（不另存一份、不開收季掛鉤、資料庫不升版）。

上閣的事蹟與讀哪裡（都是收季那一刻就定下、往後不再變的）：
- 擂台天下第一：那一季的 WorldState.arena 季末名次 place == 1（擂台包收季時寫的）
- 論功第一：那一季的 WorldState.final_tiers 每一本帳第一名、而且有階（四勝利開著的季才有）
- 決戰首功：那一季收場的每一場決戰（battles 表），兩軍各自的首功（同決戰包的 top_merit：至少按過一招、戰功最高、至少 1 分），
  首功次數最多的那一位
- 各榜第一：收季時寫進江湖史的榜單那一行（leaderboard.chronicle_lines：「第 N 季名人榜：甲（名望 120）、乙……」）的第一名
- 第一個練成絕學：那一季江湖史裡第一則「某某把【甲】練成絕學，為之定名【乙】。」（修練包 cultivation.py 的那一句）
- 評曰：那一季的列傳（biographies 表）有公開分享、寫了「評曰」的，掛那一句、連到公開的傳

同一個人（名號的 casefold）一季只佔一格，事蹟疊在那一格上；第幾次上閣照季數往前數。假人跟真人一樣排（畫面上看不出來）。
只 import 核心與共用規則層。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tianxia import leaderboard
from tianxia.core import battle_base

# 一格上的事蹟，照這個先後排（越前面越大）；格子之間照每一格最大的那一件排
ARENA = "arena"
MERIT = "merit"
TOP = "top"
BOARD = "board"
MASTER = "master"
ORDER = (ARENA, MERIT, TOP, BOARD, MASTER)

# 各榜第一要讀的榜（擂台另讀季末名次，武學、內功只上天下武學榜那一張）；照這個先後
BOARD_KINDS = ("名人", "宗師", "武學", "善人", "惡人")
BOARD_HONOR = {  # 待 joy 潤
    "名人": "名動天下",
    "宗師": "一代宗師",
    "武學": "武冠群倫",
    "善人": "仁義第一",
    "惡人": "惡名第一",
}

MASTER_LINE = re.compile(r"^(?P<who>.+?)把【(?P<old>[^】]+)】練成絕學，為之定名【(?P<name>[^】]+)】。$")
BOARD_LINE = re.compile(r"^第 \d+ 季(?P<label>[^：]+)：(?P<names>.+)$")
VERDICT = re.compile(r"^評曰[：:]?")
VERDICT_MAX = 48  # 格子上只掛評曰的頭一段，長的截在這裡加「……」


@dataclass
class Honor:
    kind: str  # ORDER 裡的一個
    label: str  # 朱印上的字（四字）
    deed: str  # 底下一行小字


@dataclass
class Cell:
    name: str
    honors: list[Honor] = field(default_factory=list)
    verdict: str = ""  # 列傳的評曰（公開分享了才有）
    code: str = ""  # 公開的傳的分享代碼
    times: int = 1  # 這是第幾次上閣（含這一季）

    @property
    def key(self) -> str:
        return self.name.casefold()

    def rank(self) -> tuple[int, int]:
        return min(ORDER.index(h.kind) for h in self.honors), -len(self.honors)


@dataclass
class Scroll:
    number: int
    ending: str  # 那一季的結局（ending_title），沒有是空字串
    cells: list[Cell]


def _cell(cells: dict[str, Cell], name: str) -> Cell:
    key = name.casefold()
    if key not in cells:
        cells[key] = Cell(name=name)
    return cells[key]


def _arena(season, cells: dict[str, Cell]) -> None:
    for entry in season.arena.values():
        if entry.place == 1:
            deed = f"守擂 {entry.wins} 勝" if entry.wins else "季末守在榜首"  # 待 joy 潤
            _cell(cells, entry.name).honors.append(Honor(ARENA, "天下第一", deed))  # 待 joy 潤


def _merit(season, content, cells: dict[str, Cell]) -> None:
    for name, tier in season.final_tiers.items():
        if tier.rank == 1 and tier.tier >= 1:
            side = content.scenario.faction_name(tier.ledger_used, "") if tier.ledger_used else ""
            label = "論功第一"  # 待 joy 潤
            deed = "・".join(x for x in (f"{side}" if side else "", tier.title) if x) or "這一季出力最多"  # 待 joy 潤
            _cell(cells, name).honors.append(Honor(MERIT, label, deed))


def top_merit(battle, tuning) -> dict[str, str]:
    """一場決戰兩邊各自的首功（陣營 id → 名號）：同決戰包 instance.top_merit 的判斷（至少按過一招、戰功最高、至少 1 分；同分照名號）。"""
    out: dict[str, str] = {}
    for side in sorted({p.faction for p in battle.participants.values()}):
        rows = sorted(
            ((p, battle_base.merit(tuning, p)) for p in battle.participants.values() if p.faction == side),
            key=lambda row: (-row[1], row[0].name),
        )
        best = next((p for p, m in rows if m > 0 and p.acted_rounds > 0), None)
        if best is not None:
            out[side] = best.name
    return out


def _tops(battles, content, cells: dict[str, Cell]) -> None:
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for battle in battles:
        for name in top_merit(battle, content.config.battle).values():
            counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
            names.setdefault(name.casefold(), name)
    if not counts:
        return
    best = max(counts.values())
    key = min(k for k, n in counts.items() if n == best)
    _cell(cells, names[key]).honors.append(Honor(TOP, "決戰首功", f"首功 {best} 次"))  # 待 joy 潤


def _first_of(names: str) -> tuple[str, str] | None:
    """榜單那一行的第一名（名號, 後面那一段）。名號只准中文（naming），所以「（」「【」一定是名號的後面。"""
    head = names.split("、", 1)[0]
    m = re.match(r"^(?P<who>[^（【]+)(?:（(?P<paren>.*)）|(?P<rest>【.*))?$", head)
    if m is None:
        return None
    return m["who"], (m["paren"] or m["rest"] or "")


def _boards(lines: list[str], cells: dict[str, Cell]) -> None:
    labels = {label: kind for kind, label, _ in leaderboard.BOARDS}
    seen: set[str] = set()
    found: dict[str, tuple[str, str]] = {}
    for text in lines:
        m = BOARD_LINE.match(text)
        if m is None or labels.get(m["label"]) not in BOARD_KINDS or m["label"] in seen:
            continue
        seen.add(m["label"])
        first = _first_of(m["names"])
        if first is not None:
            found[labels[m["label"]]] = first
    for kind in BOARD_KINDS:
        if kind in found:
            who, rest = found[kind]
            # 只有天下武學榜寫那一門武學的名字；名望、善惡名、絕學門數這種點數不寫給玩家看（PM 2026-11-26 照 Joy 字少的常規），只留印
            deed = re.sub(r"（.*$", "", rest) if kind == "武學" else ""
            _cell(cells, who).honors.append(Honor(BOARD, BOARD_HONOR[kind], deed))


def _master(lines: list[str], cells: dict[str, Cell]) -> None:
    for text in lines:
        m = MASTER_LINE.match(text)
        if m is not None:
            _cell(cells, m["who"]).honors.append(Honor(MASTER, "絕學首成", f"【{m['name']}】"))  # 待 joy 潤
            return


def verdict_of(text: str) -> str:
    """列傳裡「評曰」那一段的頭一句（去掉「評曰：」）；長的截掉加「……」。沒有是空字串。"""
    para = next((p.strip() for p in (text or "").split("\n\n") if p.strip().startswith("評曰")), "")
    line = VERDICT.sub("", para).strip()
    return line if len(line) <= VERDICT_MAX else line[:VERDICT_MAX] + "……"


def scroll(number: int, season, content, chronicle: list[str], battles, bios: dict[str, dict]) -> Scroll:
    """一季的卷：season 是那一季的 WorldState（收了季的），chronicle 是那一季江湖史的字（照時間），battles 是那一季收場的決戰，
    bios 是那一季公開的傳（名號 casefold → {code, text}）。"""
    cells: dict[str, Cell] = {}
    _arena(season, cells)
    _merit(season, content, cells)
    _tops(battles, content, cells)
    _boards(chronicle, cells)
    _master(chronicle, cells)
    for cell in cells.values():
        bio = bios.get(cell.key)
        if bio:
            cell.verdict = verdict_of(bio.get("text") or "")
            cell.code = bio.get("code") or ""
        cell.honors.sort(key=lambda h: ORDER.index(h.kind))
    ordered = sorted(cells.values(), key=lambda c: (*c.rank(), c.name))
    return Scroll(number=number, ending=season.ending_title or "", cells=ordered)


def count_times(scrolls: list[Scroll]) -> None:
    """每一格是那個人第幾次上閣（照季數由舊到新數）。scrolls 的先後不拘。"""
    seen: dict[str, int] = {}
    for s in sorted(scrolls, key=lambda s: s.number):
        for cell in s.cells:
            seen[cell.key] = seen.get(cell.key, 0) + 1
            cell.times = seen[cell.key]


def hall(store, content) -> tuple[list[Scroll], bool]:
    """閣裡全部的卷（新的在前）與這一季是不是還在跑（還沒掛上去）。只讀：收了季的每一季都排一次。"""
    current = store.get_season_number()
    live = store.get_season()
    ended = {n: store.past_season(n) for n in range(1, current)}
    if live.ended:
        ended[current] = live
    chronicle = dict(store.chronicle_before(current + 1))
    bios = _public_bios(store)
    scrolls = []
    for number, season in ended.items():
        if season is None or not season.ended:
            continue
        lines = [r.text for r in sorted(chronicle.get(number, []), key=lambda r: r.time)]
        s = scroll(number, season, content, lines, store.season_ended_battles(number), bios.get(number, {}))
        if s.cells:
            scrolls.append(s)
    count_times(scrolls)
    scrolls.sort(key=lambda s: -s.number)
    return scrolls, store.season_phase() == "running"


def _public_bios(store) -> dict[int, dict[str, dict]]:
    """公開分享中、寫成了的傳：季 → 名號 casefold → {code, text}。"""
    db = getattr(store, "db", None)
    if db is None:
        return {}
    with db.snapshot() as conn:
        rows = conn.execute(
            "SELECT season, key, share_code, text FROM biographies WHERE public = 1 AND text IS NOT NULL AND share_code IS NOT NULL",
        ).fetchall()
    out: dict[int, dict[str, dict]] = {}
    for row in rows:
        out.setdefault(row["season"], {})[row["key"]] = {"code": row["share_code"], "text": row["text"]}
    return out
