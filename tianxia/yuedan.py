"""月旦評（大勢人物擴充第三批「大家一起」；設計稿 https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2
「多人同服的玩法」；數字在 Config.figure_life 的 yuedan_*）。

許劭（characters.json 的 xushao）每週一評 yuedan_count 個人：照名人榜、善人榜、惡人榜輪流挑（leaderboard.compute_boards，
真人假人一樣、看不出來），第 yuedan_from_week 週起。先寫固定句（照榜與名號雜湊挑一句），伺服器鎖外請模型替每個人寫一句
八到十六字的評語（write、clean；三段式 Game.yuedan_request → write → Game.apply_yuedan），寫好了一起上天下大事與江湖史；
等過 yuedan_wait_seconds 還沒寫好（模型叫不動、伺服器沒開背景寫字）照固定句發（tick）。被評的人的玩家卡上掛這一週那一句
（line_for）。只是名聲，不加數值。
只 import models、state、rules、calendar、leaderboard、figure_life、zh；world、engine、server、social 呼叫它。"""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from . import calendar, figure_life, zh
from .models import Content
from .rules import add_chronicle, add_rumor
from .state import GameState, YuedanEntry

CRITIC = "xushao"
BOARDS = ("名人", "善人", "惡人")  # 輪流挑的順序
FIXED = {  # 待 joy 潤：模型寫不出來時的固定評語（照名號雜湊挑一句）
    "名人": ("名動四方，一時無兩", "聲聞州郡，眾望所歸", "少年得志，未可量也"),
    "善人": ("急人之難，有古俠風", "仁厚有餘，鄉里稱善", "行義不倦，可託大事"),
    "惡人": ("行事乖張，人皆側目", "梟雄之姿，可畏可懼", "鋒芒太露，終恐自傷"),
}
HEAD = "{critic}月旦評（{week}）："  # 待 joy 潤；week 照季寫（calendar.week_label 的 inner：「第 2 週」，7 天濃縮季「第 2 段・第 3～4 天」，FB-501）
CARD_LINE = "月旦評：「{line}」"  # 玩家卡上那一行（待 joy 潤）
LINE_MIN, LINE_MAX = 6, 18  # 模型寫的評語幾個字算數（設計稿八到十六字，留一點餘地）
_DIGITS = re.compile(r"[0-9０-９]")


def on(content: Content) -> bool:
    return figure_life.on(content) and content.config.figure_life.yuedan and CRITIC in content.characters


def critic_name(content: Content) -> str:
    return content.characters[CRITIC].name


def fixed_line(board: str, name: str) -> str:
    lines = FIXED[board]
    return lines[int(hashlib.sha256(f"月旦|{board}|{name}".encode()).hexdigest(), 16) % len(lines)]


def pick(board: dict[str, list], count: int) -> list[tuple[str, str, str]]:
    """名人、善人、惡人三張榜輪流往下挑還沒挑過的人，挑滿 count 個：(名號, 榜, 那一段事實)。榜都空了就少挑。"""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    rows = {kind: list(board.get(kind, [])) for kind in BOARDS}
    while len(out) < count and any(rows.values()):
        for kind in BOARDS:
            while rows[kind]:
                row = rows[kind].pop(0)
                key = row[0].casefold()
                if key not in seen:
                    seen.add(key)
                    out.append((row[0], kind, row[2]))
                    break
            if len(out) >= count:
                break
    return out


def tick(state: GameState, content: Content, world) -> None:
    """world.advance_world_state 每一步叫（給了 store 才叫：要掃角色）：跨進新的一週（第 yuedan_from_week 週起）就評這一週的，
    等太久還沒寫好的照固定句發。"""
    if not on(content) or world is None:
        return
    w = state.world
    week = calendar.point(w.time, content, w).week
    tuning = content.config.figure_life
    if week >= tuning.yuedan_from_week and week > w.yuedan_week:
        from . import leaderboard  # noqa: PLC0415  leaderboard → team → …：延後載入

        w.yuedan_week = week
        board = leaderboard.compute_boards(content, world)
        w.yuedan = [e for e in w.yuedan if e.week >= week - 1]  # 只留上一週與這一週（玩家卡掛一週）
        w.yuedan += [YuedanEntry(week=week, name=name, board=kind, fact=fact, line=fixed_line(kind, name), at=w.time)
                     for name, kind, fact in pick(board, tuning.yuedan_count)]
    pending = waiting(state)
    if pending and w.time - pending[0].at >= tuning.yuedan_wait_seconds:
        publish(state, content)


def waiting(state: GameState) -> list[YuedanEntry]:
    """還沒發出去的那一批（同一週的）。"""
    return [e for e in state.world.yuedan if not e.published]


def publish(state: GameState, content: Content) -> None:
    """把還沒發的那一批寫成一則天下大事、一行江湖史。"""
    batch = waiting(state)
    if not batch:
        return
    week = calendar.week_label(batch[0].week, content, state.world, form="inner")
    text = HEAD.format(critic=critic_name(content), week=week) + "；".join(f"{e.name}「{e.line}」" for e in batch) + "。"
    add_rumor(state, text, content.characters[CRITIC].talk_at, content=content, layer="world")
    add_chronicle(state, text)
    for e in batch:
        e.published = True


def line_for(state: GameState, content: Content, name: str) -> str:
    """這個人這一週（上一週評的也算，評語掛一週）的評語，寫在玩家卡上；沒有是空字串。"""
    if not on(content):
        return ""
    week = calendar.point(state.world.time, content, state.world).week
    key = name.casefold()
    found = [e for e in state.world.yuedan if e.published and e.name.casefold() == key and e.week >= week - 1]
    return CARD_LINE.format(line=found[-1].line) if found else ""


# ── 模型寫評語（鎖外；server.write_yuedan）──────────────


class YuedanNote(BaseModel):
    """A 段（Game.yuedan_request）：還沒發、還沒寫過的那一批。C 段照週次與名單認同一批。"""

    week: int
    critic: str
    people: list[tuple[str, str, str]]  # (名號, 榜, 事實)


class YuedanLine(BaseModel):
    name: str = ""
    line: str = ""


class YuedanBatch(BaseModel):
    lines: list[YuedanLine] = Field(default_factory=list)


def request(state: GameState, content: Content) -> YuedanNote | None:
    if not on(content):
        return None
    batch = [e for e in waiting(state) if not e.written]
    if not batch:
        return None
    return YuedanNote(week=batch[0].week, critic=critic_name(content), people=[(e.name, e.board, e.fact) for e in batch])


def write(client, note: YuedanNote) -> dict[str, str]:
    """B 段：請模型替每個人寫一句八到十六字的評語（品評人物、半文言）。回傳 名號 → 評語；寫壞的、名單外的不在裡面。"""
    if client is None or not note.people:
        return {}
    listing = "\n".join(f"{i}. {name}（{kind}榜上有名：{fact}）" for i, (name, kind, fact) in enumerate(note.people, 1))
    messages = [
        {"role": "system", "content": (
            f"你是東漢末年以品評人物聞名的{note.critic}，每月初一在汝南評論天下人物（月旦評）。替下面每一位寫一句評語："
            "八到十六個字、半文言、繁體中文，像「治世之能臣，亂世之奸雄」那樣有褒有貶、一語中的；不要寫數字、不要寫名號本身、"
            "不要用「他」「她」。回傳 lines：每一位一筆，name 照抄名號，line 是那一句。"
        )},
        {"role": "user", "content": f"這一回要評的人：\n{listing}"},
    ]
    try:
        result = client.chat_structured(messages, YuedanBatch, temperature=0.8, num_predict=60 + 50 * len(note.people),
                                        required_fields=["lines"])
    except Exception:
        return {}
    wanted = {name for name, _, _ in note.people}
    out: dict[str, str] = {}
    for item in result.lines:
        name = str(item.name or "").strip()
        if name in wanted and name not in out:
            line = clean(item.line, name)
            if line:
                out[name] = line
    return out


def clean(raw: str, name: str = "") -> str:
    text = zh.to_traditional(str(raw or "")).strip()
    text = re.sub(r"[*#>`_\s]+", "", text).strip("「」『』\"'“”。")
    if not (LINE_MIN <= len(text) <= LINE_MAX) or _DIGITS.search(text) or (name and name in text) or zh.stray_latin(text):
        return ""
    return text


def apply(state: GameState, content: Content, note: YuedanNote, lines: dict[str, str]) -> bool:
    """C 段：還是同一週、同一批（還沒發）才換上寫好的評語，然後發出去。寫不出來（空的）也照固定句發。發了回 True。"""
    batch = waiting(state)
    if not batch or batch[0].week != note.week or [e.name for e in batch] != [p[0] for p in note.people]:
        return False
    for e in batch:
        e.written = True
        if lines.get(e.name):
            e.line = lines[e.name]
    publish(state, content)
    return True
