"""江湖紀錄：把玩家的每次行動整理成一則 JournalEntry（標題、結果標記、敘事、數值變化），
並產生左欄「剛剛」卡片與紀錄列的 HTML。

原始訊息仍照舊寫進 GameState.log；紀錄只是給畫面看的整理，由 engine 在知道是什麼行動的地方建立。
這裡只產生 HTML 字串與樣式，不 import gradio。
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .battlelog import clock_text, split_changes
from .state import GameState, JournalEntry

LOG_BREAK = "\x1e"  # GameState.log 中每次行動結束的分隔標記（不顯示）
MAX_ENTRIES = 30  # 存檔保留最近幾則
LEGACY_TIME = -1.0  # 舊存檔的 log 轉來的紀錄不知道時間
TITLE_MAX = 40  # 舊存檔轉來的標題最長幾個字，超過的截斷
_SIGNED = re.compile(r"([+-])(\d+(?:\.\d+)?)$")  # 數值變化最後的「+3」「-10」


# ── 建立紀錄 ──────────────────────────────────────────


@dataclass
class Draft:
    """一次行動的紀錄草稿。engine 在行動開始時給標題，行動過程中補上結果標記、打的那一場、
    哪些訊息不寫（場景已經顯示的地點描述、事件開場……），行動結束時用這次的訊息做成一則紀錄。"""

    title: str
    tag: str = ""
    battle_id: int | None = None
    rewrites: list[tuple[str, str | None]] = field(default_factory=list)  # (訊息, 紀錄裡改寫成的文字；None＝不寫)
    changes: list[str] = field(default_factory=list)  # 訊息裡沒有、另外補上的數值變化（例如經驗）

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
            time=time, title=self.title, tag=self.tag, lines=lines, changes=self.changes + changes,
            battle_id=self.battle_id,
        )


def add_entry(state: GameState, entry: JournalEntry) -> None:
    """最新的放最前面，只留最近 MAX_ENTRIES 則。"""
    state.journal.insert(0, entry)
    del state.journal[MAX_ENTRIES:]


def from_legacy_log(log: list[str]) -> list[JournalEntry]:
    """舊存檔只有 log：每組（LOG_BREAK 之間）轉成一則，第一行當標題、其餘分成敘事與數值變化；
    最新的在前，最多 MAX_ENTRIES 則。多行的訊息拆成一行一行，空行略過。"""
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
    entries = []
    for title, *rest in reversed(groups[-MAX_ENTRIES:]):
        if len(title) > TITLE_MAX:
            rest = [title, *rest]
            title = title[:TITLE_MAX] + "…"
        changes, lines = split_changes(rest)
        entries.append(JournalEntry(time=LEGACY_TIME, title=title, lines=lines, changes=changes))
    return entries


# ── 顯示 ──────────────────────────────────────────────


def change_class(change: str) -> str:
    """數值變化的顏色：增加 tx-up（綠）、減少 tx-down（紅）；零或看不出正負時不上色。"""
    m = _SIGNED.search(change.strip())
    if not m or float(m.group(2)) == 0:
        return ""
    return "tx-up" if m.group(1) == "+" else "tx-down"


def _esc(text: str) -> str:
    """HTML 跳脫；大括號與錢號也轉成實體，免得被 Gradio 的 HTML 樣板當成樣板語法。"""
    return html.escape(text).replace("{", "&#123;").replace("}", "&#125;").replace("$", "&#36;")


def _when(time: float) -> str:
    return "舊紀錄" if time < 0 else clock_text(time)


def _heading(entry: JournalEntry) -> str:
    tag = f'<span class="tx-tag">{_esc(entry.tag)}</span>' if entry.tag else ""
    return f'<span class="tx-title">{_esc(entry.title)}</span>{tag}'


def _chips(changes: list[str], tag: str) -> str:
    if not changes:
        return ""
    chips = "".join(
        f'<span class="{" ".join(filter(None, ("tx-chg", change_class(c))))}">{_esc(c)}</span>' for c in changes
    )
    return f'<{tag} class="tx-chgs">{chips}</{tag}>'


def card_html(entry: JournalEntry) -> str:
    """「剛剛」卡片：時間、標題與結果標記、敘事、數值變化（綠增紅減）。"""
    when = "剛剛" if entry.time < 0 else f"剛剛　{clock_text(entry.time)}"
    lines = "".join(f'<div class="tx-line">{_esc(line).replace(chr(10), "<br>")}</div>' for line in entry.lines)
    return (
        f'<div class="tx-now"><div class="tx-when">{when}</div><div class="tx-head">{_heading(entry)}</div>'
        f'{lines}{_chips(entry.changes, "div")}</div>'
    )


def _row(entry: JournalEntry) -> str:
    """紀錄的一列：時間一欄、標題與結果標記、數值變化；敘事只放在滑鼠提示裡。"""
    hint = f' title="{_esc(chr(10).join(entry.lines))}"' if entry.lines else ""
    return (
        f'<div class="tx-row"{hint}><span class="tx-time">{_when(entry.time)}</span>'
        f'<span class="tx-main">{_heading(entry)}{_chips(entry.changes, "span")}</span></div>'
    )


def rows_html(entries: list[JournalEntry], heading: str = "", empty: str = "") -> str:
    """一則一列（最新的在前）；沒有紀錄時顯示 empty。什麼都沒有時回傳空字串。"""
    if not entries and not heading and not empty:
        return ""
    parts = [f'<div class="tx-heading">{_esc(heading)}</div>'] if heading else []
    parts += [_row(e) for e in entries] or ([f'<div class="tx-empty">{_esc(empty)}</div>'] if empty else [])
    return f'<div class="tx-journal">{"".join(parts)}</div>'


# 卡片與紀錄列的樣式（介面層交給 gr.HTML 的 css_template，會自動限定在該元件內）。
# 顏色用 Gradio 主題變數，亮色與暗色主題都讀得清楚；增減用淡色底加框線表示，文字維持主題的字色。
CSS = """
.tx-now { border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 8px 12px;
  background: var(--background-fill-secondary); line-height: 1.6; }
.tx-when { font-size: 12px; opacity: 0.7; }
.tx-head { margin: 2px 0; }
.tx-title { font-weight: 600; }
.tx-tag { margin-left: 0.75em; opacity: 0.85; }
.tx-line { margin: 2px 0; }
.tx-chgs { display: inline-flex; flex-wrap: wrap; gap: 4px; margin-left: 0.75em; vertical-align: middle; }
div.tx-chgs { display: flex; margin: 6px 0 2px; }
.tx-chg { font-size: 12px; line-height: 1.5; padding: 0 6px; border-radius: 4px; white-space: nowrap;
  border: 1px solid var(--border-color-primary); }
.tx-up { background: rgba(22, 163, 74, 0.16); border-color: rgba(22, 163, 74, 0.7); }
.tx-down { background: rgba(220, 38, 38, 0.16); border-color: rgba(220, 38, 38, 0.7); }
.tx-heading { font-weight: 600; margin: 4px 0; }
.tx-row { display: flex; gap: 10px; padding: 3px 0; border-bottom: 1px solid var(--border-color-primary);
  font-size: 14px; line-height: 1.6; }
.tx-time { flex: 0 0 6.5em; font-size: 12px; opacity: 0.7; white-space: nowrap; padding-top: 2px; }
.tx-main { flex: 1; min-width: 0; }
.tx-empty { font-size: 13px; opacity: 0.7; }
"""
