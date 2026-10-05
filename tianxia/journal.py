"""江湖紀錄：把玩家的每次行動整理成一則 JournalEntry（標題、結果標記、敘事、數值變化），
並產生左欄「剛剛」卡片、戰鬥卡片底下的補充與紀錄列的 HTML。

原始訊息仍照舊寫進 GameState.log；紀錄只是給畫面看的整理，由 engine 在知道是什麼行動的地方建立。
這裡只產生 HTML 字串與樣式，不 import 網頁框架；server.py 把它們原樣送給網頁。
"""
from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import front_lines
from .battlelog import clock_text, split_changes
from .state import GameState, JournalEntry

LOG_BREAK = "\x1e"  # GameState.log 中每次行動結束的分隔標記（不顯示）
MAX_ENTRIES = 30  # 存檔保留最近幾則
LEGACY_TIME = -1.0  # 舊存檔的 log 轉來的紀錄不知道時間
TITLE_MAX = 40  # 舊存檔轉來的標題最長幾個字，超過的截斷
# 修練頁（自創、鍛鍊、療傷、改練）與煉製頁的動作那一則的標題，照底部分頁的名字（FB-047）；同一種連續的會併成一則
PRACTICE = "修練"
CRAFT = "煉製"
ALLOCATE = "配點"  # 升級的屬性點分配到屬性上（武學與成長設計 6.2）；連按幾次併成一則
WORLD_NEWS = "江湖大事"  # 時間流逝時發生的江湖大事那一則的標題；連續的會併成一則
NEWS_PREFIXES = ("【江湖大事】", "【主線】", "【主線改寫】")  # world.py 寫出的大勢門檻、世界事件、主線變化

# 數值變化：「標籤 正負號數字（附註）」，例如「銀兩 -5」「經驗 +15（每人）」
_CHANGE = re.compile(r"^(\S+) ([+-])(\d+(?:\.\d+)?)(（[^）]*）)?$")
_MARKER = re.compile(r"^遇上(奇遇)?【[^】]+】$")  # event_marker 寫出的「遇上【X】」
# 舊存檔裡什麼都沒改變的失敗訊息（門下、閉關、過期的選項）；整組都是這種的不轉成紀錄。
_FAILURE = re.compile(
    r"^(心得不足：.*|沒有這門武學。|本命武學不能散功。|【[^】]+】已經練到第十成。|【[^】]+】尚在第一成，無功可散。"
    r"|沒有這個武學欄。|你尚未習得這門武學。|【[^】]+】是隊中某人的本命武學，不能重複配置。"
    r"|（此刻無法這麼做。）|你現在無法閉關。)$"
)


# ── 數值變化 ──────────────────────────────────────────


def _parse(change: str) -> tuple[tuple[str, str], float] | None:
    """「銀兩 -5」→ (("銀兩", ""), -5.0)；「經驗 +15（每人）」→ (("經驗", "（每人）"), 15.0)；看不懂時回傳 None。"""
    m = _CHANGE.match(change.strip())
    if m is None:
        return None
    value = float(m.group(3))
    return (m.group(1), m.group(4) or ""), -value if m.group(2) == "-" else value


def _format(key: tuple[str, str], value: float) -> str:
    label, suffix = key
    number = int(abs(value)) if float(value).is_integer() else abs(value)
    return f"{label} {'+' if value > 0 else '-'}{number}{suffix}"


def _totals(changes: list[str]) -> tuple[list[tuple[str, object]], dict[tuple[str, str], float]]:
    """依第一次出現的順序列出（"raw", 原文）或（"key", 標籤），並加總每個標籤的數值。"""
    order: list[tuple[str, object]] = []
    totals: dict[tuple[str, str], float] = {}
    for change in changes:
        parsed = _parse(change)
        if parsed is None:
            order.append(("raw", change))
            continue
        key, value = parsed
        if key not in totals:
            totals[key] = 0.0
            order.append(("key", key))
        totals[key] = round(totals[key] + value, 6)
    return order, totals


def combine_changes(changes: list[str]) -> list[str]:
    """同一個標籤的數值加總成一項（例如兩個「銀兩 +10」→「銀兩 +20」），順序依第一次出現；加總為零的省略。"""
    order, totals = _totals(changes)
    return [x if kind == "raw" else _format(x, totals[x]) for kind, x in order if kind == "raw" or totals[x]]


def subtract_changes(changes: list[str], shown: list[str]) -> list[str]:
    """changes 扣掉已經顯示過的 shown（例如戰鬥卡片上的獲得與損失），剩下還沒顯示的部分。"""
    order, totals = _totals(changes)
    _, minus = _totals(shown)
    out = []
    for kind, x in order:
        if kind == "raw":
            if x not in shown:
                out.append(x)
        elif value := round(totals[x] - minus.get(x, 0.0), 6):
            out.append(_format(x, value))
    return out


LOSS_WHEN_UP = frozenset({"內傷"})  # 多了是壞事的數值：增加上紅、減少上綠（FB-049：「內傷 +3」以前是收穫的綠）


def change_class(change: str) -> str:
    """數值變化的顏色：增加 tx-up（綠）、減少 tx-down（紅）；零或看不出正負時不上色。
    LOSS_WHEN_UP 裡的（內傷）反過來：多了是損失。"""
    parsed = _parse(change)
    if parsed is None or parsed[1] == 0:
        return ""
    gain = (parsed[1] > 0) != (parsed[0][0] in LOSS_WHEN_UP)
    return "tx-up" if gain else "tx-down"


# ── 建立紀錄 ──────────────────────────────────────────


def event_marker(title: str, qiyu: bool) -> str:
    """遇上事件時在紀錄裡的寫法：「遇上【酒樓鬥毆】」「遇上奇遇【瀑布怪客】」。"""
    return f"遇上奇遇【{title}】" if qiyu else f"遇上【{title}】"


FRAGMENT_PREFIX = "你聽到一件事："


def fragment_line(text: str) -> str:
    """伏筆的線索片段寫進江湖紀錄的那一行（計畫 T7）：「你聽到一件事：……」。只進自己的紀錄，不發任何傳聞。"""
    return f"{FRAGMENT_PREFIX}{text}"


@dataclass
class Draft:
    """一次行動的紀錄草稿。engine 在行動開始時給標題，行動過程中補上結果標記、打的那一場、
    哪些訊息不寫（場景已經顯示的地點描述、事件開場……），行動結束時用這次的訊息做成一則紀錄。"""

    title: str
    tag: str = ""
    battle_id: int | None = None
    rewrites: list[tuple[str, str | None]] = field(default_factory=list)  # (訊息, 紀錄裡改寫成的文字；None＝不寫)
    changes: list[str] = field(default_factory=list)  # 訊息裡沒有、另外補上的數值變化（例如經驗）
    guide: list[str] = field(default_factory=list)  # 這次行動順便完成的新手引導（記進 JournalEntry.guide，不進敘事）

    def hide(self, msg: str) -> None:
        self.rewrites.append((msg, None))

    def outcome(self, text: str, msg: str) -> None:
        """msg 是這次行動的一個結果：還沒有結果標記時用 text 當標記、msg 不寫；
        已經有標記了（例如打完仗又遇上事件）就把 msg 改寫成 text 留在敘事裡。"""
        if self.tag:
            self.rewrites.append((msg, text))
        else:
            self.tag = text
            self.hide(msg)

    def entry(self, time: float, msgs: list[str]) -> JournalEntry:
        pending = list(self.rewrites)
        kept: list[str] = []
        for msg in msgs:
            hit = next((i for i, (old, _) in enumerate(pending) if old == msg), None)
            if hit is None:
                kept.append(msg)
                continue
            new = pending.pop(hit)[1]
            if new is not None:
                kept.append(new)
        changes, lines = split_changes(kept)
        return JournalEntry(
            time=time, title=self.title, tag=self.tag, lines=lines, changes=combine_changes(self.changes + changes),
            battle_id=self.battle_id, guide=list(self.guide),
        )


def news_entry(time: float, msgs: list[str]) -> JournalEntry | None:
    """時間流逝時的訊息裡挑出江湖大事與主線變化（一般的江湖傳聞不算）；沒有時回傳 None。"""
    news = [m.removeprefix("【江湖大事】") for m in msgs if m.startswith(NEWS_PREFIXES)]
    if not news:
        return None
    return JournalEntry(time=time, title=WORLD_NEWS, tag=news[-1], lines=news if len(news) > 1 else [])


def _story(entry: JournalEntry) -> list[str]:
    """併成一則時這一則貢獻的敘事：有敘事就用敘事，只有結果標記的（例如一次升級）用結果標記。"""
    return entry.lines or ([entry.tag] if entry.tag else [])


def _mergeable_head(state: GameState, entry: JournalEntry) -> JournalEntry | None:
    """最新的一則，同標題（而且不是舊存檔轉來、不知道時間的）才能把 entry 併進去；不能就是 None。"""
    head = state.journal[0] if state.journal else None
    return head if head is not None and head.title == entry.title and head.time >= 0 else None


def _merged(head: JournalEntry, entry: JournalEntry, lines: list[str], battle_id: int | None = None) -> JournalEntry:
    """head 與 entry 併成的一則：時間與結果標記用新的（entry 沒有標記就沿用 head 的）、數值變化加總。"""
    return JournalEntry(
        time=entry.time, title=entry.title, tag=entry.tag or head.tag, lines=lines,
        changes=combine_changes(head.changes + entry.changes), battle_id=battle_id, guide=head.guide + entry.guide,
    )


def add_entry(state: GameState, entry: JournalEntry, merge: bool = False) -> None:
    """最新的放最前面，只留最近 MAX_ENTRIES 則。
    merge=True 且最新一則是同一類（同標題）時併進那一則：敘事依序接上、數值變化加總、時間與結果標記用新的。"""
    head = _mergeable_head(state, entry) if merge else None
    if head is not None:
        state.journal[0] = _merged(head, entry, _story(head) + _story(entry))
        return
    state.journal.insert(0, entry)
    del state.journal[MAX_ENTRIES:]


def add_guide(state: GameState, notes: list[str]) -> None:
    """不在行動裡完成的新手引導（例：打開輿圖）：接在最新一則的 guide 後面，不另起一則（「剛剛」不換）；還沒有紀錄時另起一則。"""
    if state.journal:
        head = state.journal[0]
        state.journal[0] = head.model_copy(update={"guide": head.guide + notes})
    else:
        add_entry(state, JournalEntry(time=state.world.time, title="新手引導", guide=list(notes)))


def add_arrival(state: GameState, entry: JournalEntry, done: bool) -> None:
    """一趟路抵達時的紀錄（sync／advance 補算的抵達）：出發那則（同標題）還是最新的一則就併進去——敘事接上、
    數值變化加總、時間換成抵達的時間、有新的結果標記（例如「喊停，停在 湖邊」）就換新的；不是的話另起一則，
    結果標記寫「抵達」（走完了）或「途中」（只到了中途的站）；併進的是中途另起的那則「途中」、這次又走完了，
    標記改成「抵達」。"""
    head = _mergeable_head(state, entry)
    if head is not None:
        if done and not entry.tag and head.tag == "途中":
            entry = entry.model_copy(update={"tag": "抵達"})
        state.journal[0] = _merged(head, entry, head.lines + entry.lines, battle_id=head.battle_id)
        return
    add_entry(state, entry.model_copy(update={"tag": entry.tag or ("抵達" if done else "途中")}))


def from_legacy_log(log: list[str]) -> list[JournalEntry]:
    """舊存檔只有 log：每組（LOG_BREAK 之間）轉成一則，第一行當標題、其餘分成敘事與數值變化；
    最新的在前，最多 MAX_ENTRIES 則。多行的訊息拆成一行一行，空行略過；整組只有失敗訊息的略過。"""
    groups: list[list[str]] = []
    current: list[str] = []
    for msg in log:
        if msg == LOG_BREAK:
            if current:
                groups.append(current)
                current = []
            continue
        current += [line.strip() for line in str(msg).replace(LOG_BREAK, "\n").split("\n") if line.strip()]
    if current:
        groups.append(current)
    groups = [g for g in groups if not all(_FAILURE.match(line) for line in g)]
    entries = []
    for title, *rest in reversed(groups[-MAX_ENTRIES:]):
        if len(title) > TITLE_MAX:
            rest = [title, *rest]
            title = title[:TITLE_MAX] + "…"
        changes, lines = split_changes(rest)
        entries.append(JournalEntry(time=LEGACY_TIME, title=title, lines=lines, changes=combine_changes(changes)))
    return entries


def card_leftovers(entry: JournalEntry, told: list[str], shown: list[str]) -> tuple[list[str], list[str]]:
    """打了仗的那一則裡，戰鬥卡片沒寫到的敘事與數值變化（例如戰鬥掉出來的破境丹、同時發生的江湖大事）。
    told 是卡片已經講過的話、用那一則寫的原文（battlelog.told_lines：結果裡的敘事與掉落的素材），shown 是卡片上的
    獲得與損失；「遇上【X】」由場景顯示，不算。"""
    lines = [line for line in entry.lines if line not in told and not _MARKER.match(line)]
    return lines, subtract_changes(entry.changes, shown)


# ── 顯示 ──────────────────────────────────────────────


def _esc(text: str) -> str:
    """HTML 跳脫。gr.HTML 的樣板是「${value}」，值原樣插進去、不會再被當成樣板解讀，所以大括號不必另外處理。"""
    return html.escape(text)


def _when(time: float, when: Callable[[float], str]) -> str:
    return "舊紀錄" if time < 0 else when(time)


def _heading(entry: JournalEntry, tag: str | None = None) -> str:
    """標題與旁邊的結果標記；tag 沒給就用這一則的標記（給空字串＝不寫標記）。"""
    tag = entry.tag if tag is None else tag
    shown = f'<span class="tx-tag">{_esc(tag)}</span>' if tag else ""
    return f'<span class="tx-title">{_esc(entry.title)}</span>{shown}'


_NEW_THING = re.compile(
    r"^獲得 |煉成|自創了|習得了|第一次煉成|改練【|^你聽到一件事："
    r"|^你悟得了「|^你學會了【"
    r"|^你以【[^】]+】融入「[^」]+」，(?:衍生出一門|合出來的竟是一門已有的)"
    r"|^你把【[^】]+】與【[^】]+】合而為一，(?:衍生出一門|合出來的竟是一門已有的)"
    r"|^「[^」]+」與「[^」]+」在你心中交融，化成(?:的竟是已有的)?「"
    r"|^【[^】]+】修練有成，從"
)
# 「拿到新東西」的那一行：掃過一道光。玩家一次行動常常吐出五六行訊息，而其中真正值得注意的
# 就是這一行（新素材、新功法、新意境、伏筆的線索片段）——好玩度量表量的也正是這件事。
# 後面那五條照訊息的原文錨在開頭，不能只認幾個字（路上見聞「你學會了那個結的打法」不是新功法）：
# 悟得了＝意境（insights.learn）、學會了＝在各地學基礎武學（library.learn）、衍生出＝合成出新武學、
# 交融化成＝合併出新意境（fusion.fuse／merge）、合而為一＝兩門武學合成（fusion.blend）、修練有成＝修練晉品（Task 9 的字眼）；
# 「合到舊的」（合出來的竟是一門已有的／化成的竟是已有的）拿到的是別人首創的那一門，對這個玩家一樣是新東西，所以也亮；
# 合出來的是自己已經有的那句（「…你已經有了」）什麼也沒拿到，開頭不同，不亮。
# 重複悟到只是化成心得（「又悟到一次」），不算新東西。


def _line_class(line: str) -> str:
    return "tx-line tx-new" if _NEW_THING.search(line) else "tx-line"


def _lines(lines: list[str]) -> str:
    return "".join(
        f'<div class="{_line_class(line)}">{_esc(line).replace(chr(10), "<br>")}</div>' for line in lines
    )


def _body(entry: JournalEntry) -> list[str]:
    """一則要畫出來的敘事：第一行跟結果標記一字不差時不再畫一次（FB-029）。門下動作完成引導時，那次動作自己的那句話
    既是結果標記、也放在 lines 第一行——存著是為了之後併進來的門下動作擠不掉它（見 engine.Game._menxia_entry），
    畫的時候標記已經寫過了。只看第一行：其他紀錄存的東西與畫法都不變。"""
    lines = entry.lines
    return lines[1:] if lines and entry.tag and lines[0] == entry.tag else lines


def _card_story(entry: JournalEntry) -> tuple[str, list[str]]:
    """「剛剛」卡片標題旁的結果標記與底下的敘事，每一句只畫一次（FB-070）。
    同一種連續的門下動作併成一則時（add_entry 的 merge），標記是最新那次的那句話、敘事是每一次照順序（_story），
    所以標記又是敘事的最後一行：以前標記寫一次、敘事再列一遍，修練兩次看起來像三次。這時標記不另寫，敘事照順序畫，
    N 次就是 N 行（數值變化本來就加總好了）。其他照 _body（FB-029：只有一行、跟標記一字不差的不再畫）。
    只管卡片：江湖紀錄的一列摘要要靠標記看出最近一次的結果，點開才看全部（_row 照舊）。"""
    lines = entry.lines
    if len(lines) > 1 and entry.tag and lines[-1] == entry.tag:
        return "", lines
    return entry.tag, _body(entry)


ChipFn = Callable[[str, str], tuple[str, int] | None]
"""數值標籤的換法（FB-064）：(紀錄裡存的一項變化, seed) → (畫面上的字, 對看的人是好事 1／壞事 −1／無關 0)，不是它管的變化回 None。
戰況變化（front_lines.mark）紀錄裡存的是機器可讀的寫法，要由 engine 照內容與看的人的陣營換成一句話；顏色因此在畫的那一刻才定。"""


def _chips(changes: list[str], tag: str, chip: ChipFn | None = None, seed: str = "") -> str:
    """數值標籤。chip 認得的變化（戰況）用它給的字與好壞上色；機器可讀的戰況變化沒人認得（沒交 chip）時不畫，不讓它原樣露給玩家。"""
    shown: list[tuple[str, str]] = []
    for change in changes:
        drawn = chip(change, seed) if chip is not None else None
        if drawn is not None:
            text, favour = drawn
            shown.append((text, "tx-up" if favour > 0 else "tx-down" if favour < 0 else ""))
        elif not front_lines.is_mark(change):
            shown.append((change, change_class(change)))
    if not shown:
        return ""
    chips = "".join(f'<span class="{" ".join(filter(None, ("tx-chg", cls)))}">{_esc(text)}</span>' for text, cls in shown)
    return f'<{tag} class="tx-chgs">{chips}</{tag}>'


def _seed(entry: JournalEntry) -> str:
    """一則紀錄換句子用的 seed：它的時間（同一則永遠同一句；Game._log 回給呼叫端的那句用同一個 seed，兩邊是同一句）。"""
    return str(entry.time)


def card_html(entry: JournalEntry, when_text: Callable[[float], str] = clock_text, chip: ChipFn | None = None) -> str:
    """「剛剛」卡片：時間、標題與結果標記、敘事、數值變化（綠增紅減）。舊存檔轉來的紀錄寫「舊紀錄」。
    when_text 是時間的寫法：第一季由 engine 給季曆（calendar.stamp_text），不給時照舊「第N天 HH:MM」。
    chip：戰況變化的換法（見 ChipFn）。"""
    when = "舊紀錄" if entry.time < 0 else f"剛剛　{when_text(entry.time)}"
    tag, story = _card_story(entry)
    return (
        f'<div class="tx-now"><div class="tx-when">{when}</div><div class="tx-head">{_heading(entry, tag)}</div>'
        f'{_lines(story)}{_chips(entry.changes, "div", chip, _seed(entry))}</div>'
    )


def extra_html(lines: list[str], changes: list[str], chip: ChipFn | None = None, seed: str = "") -> str:
    """戰鬥卡片底下的補充：卡片沒寫到的敘事與數值變化（見 card_leftovers）；都沒有時是空字串。
    changes 全是畫不出來的（例如沒交 chip 的戰況變化）又沒有敘事時，也是空字串。"""
    chips = _chips(changes, "div", chip, seed)
    if not lines and not chips:
        return ""
    return f'<div class="tx-extra">{_lines(lines)}{chips}</div>'


def _row(entry: JournalEntry, when: Callable[[float], str], chip: ChipFn | None = None) -> str:
    """紀錄的一列：時間一欄、標題與結果標記、數值變化。有敘事的一列可以點開，敘事收在裡面。"""
    head = (
        f'<span class="tx-time">{_when(entry.time, when)}</span>'
        f'<span class="tx-main">{_heading(entry)}{_chips(entry.changes, "span", chip, _seed(entry))}</span>'
    )
    body = _body(entry) + entry.guide  # 新手引導在江湖紀錄照舊看得到（「剛剛」卡片不畫，見 card_html）
    if not body:
        return f'<div class="tx-row"><div class="tx-sum">{head}</div></div>'
    return (
        f'<details class="tx-row"><summary class="tx-sum">{head}</summary>'
        f'<div class="tx-body">{_lines(body)}</div></details>'
    )


def rows_html(
    entries: list[JournalEntry], heading: str = "", empty: str = "", when: Callable[[float], str] = clock_text,
    chip: ChipFn | None = None,
) -> str:
    """一則一列（最新的在前）；沒有紀錄時顯示 empty。什麼都沒有時回傳空字串。when 是時間的寫法、chip 是戰況變化的換法（見 card_html）。"""
    if not entries and not heading and not empty:
        return ""
    parts = [f'<div class="tx-heading">{_esc(heading)}</div>'] if heading else []
    parts += [_row(e, when, chip) for e in entries] or ([f'<div class="tx-empty">{_esc(empty)}</div>'] if empty else [])
    return f'<div class="tx-journal">{"".join(parts)}</div>'


# 卡片與紀錄列的樣式：server.py 在 /journal.css 原樣送出（Gradio 時期是交給 gr.HTML 的 css_template）。
# 顏色沿用 Gradio 主題變數的名稱（--border-color-primary 等），web/style.css 把它們接到網頁自己的顏色，
# 亮色與暗色主題都讀得清楚；增減用淡色底加框線表示，文字維持主題的字色。
CSS = """
.tx-now { border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 8px 12px;
  background: var(--background-fill-secondary); line-height: 1.6;
  animation: tx-now-rise 0.28s ease-out; }
/* 「剛剛」那張卡片的內容每次行動都會換掉，所以這個動畫每次都會重播——等於「這是剛發生的事」
   的視覺提示。更早的紀錄列（.tx-row）刻意不動，不然整頁都在閃。 */
@keyframes tx-now-rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
/* 拿到新東西的那一行：掃過一道光，只播一次（見 _line_class） */
@keyframes tx-shine { from { background-position: -150% 0; } to { background-position: 250% 0; } }
.tx-new { border-radius: 4px; background-image: linear-gradient(
    90deg, transparent 0%, rgba(250, 204, 21, 0.30) 45%, rgba(250, 204, 21, 0.30) 55%, transparent 100%);
  background-size: 220% 100%; background-repeat: no-repeat;
  animation: tx-shine 1.15s ease-out 1 both; }
@media (prefers-reduced-motion: reduce) {
  .tx-now, .tx-new { animation: none !important; }
  .tx-new { background-image: none; box-shadow: inset 3px 0 0 rgba(250, 204, 21, 0.9); padding-left: 8px; }
}
.tx-when { font-size: 12px; opacity: 0.7; }
.tx-head { margin: 2px 0; }
.tx-title { font-weight: 600; }
.tx-tag { margin-left: 0.75em; opacity: 0.85; }
.tx-line { margin: 2px 0; }
.tx-extra { border-left: 3px solid var(--border-color-primary); padding: 2px 10px; margin: 2px 0;
  font-size: 14px; line-height: 1.6; }
.tx-chgs { display: inline-flex; flex-wrap: wrap; gap: 4px; margin-left: 0.75em; vertical-align: middle; }
div.tx-chgs { display: flex; margin: 6px 0 2px; }
.tx-chg { font-size: 12px; line-height: 1.5; padding: 0 6px; border-radius: 4px; white-space: nowrap;
  border: 1px solid var(--border-color-primary); }
.tx-up { background: rgba(22, 163, 74, 0.16); border-color: rgba(22, 163, 74, 0.7); }
.tx-down { background: rgba(220, 38, 38, 0.16); border-color: rgba(220, 38, 38, 0.7); }
.tx-heading { font-weight: 600; margin: 4px 0; }
.tx-row { border-bottom: 1px solid var(--border-color-primary); font-size: 14px; line-height: 1.6; }
.tx-sum { display: flex; gap: 10px; padding: 3px 0; }
summary.tx-sum { cursor: pointer; list-style: none; }
summary.tx-sum::-webkit-details-marker { display: none; }
summary.tx-sum .tx-main::after { content: "▸"; margin-left: 0.5em; font-size: 11px; opacity: 0.55; }
details[open] > summary.tx-sum .tx-main::after { content: "▾"; }
.tx-body { padding: 0 0 4px calc(6.5em + 10px); font-size: 13px; opacity: 0.9; }
.tx-time { flex: 0 0 6.5em; font-size: 12px; opacity: 0.7; white-space: nowrap; padding-top: 2px; }
.tx-main { flex: 1; min-width: 0; }
.tx-empty { font-size: 13px; opacity: 0.7; }
"""
