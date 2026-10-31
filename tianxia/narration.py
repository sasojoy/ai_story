"""事件旁白每週改寫（減法季整合設計第十章，批 10；子開關 rules.jianfa(..., "rewrite_narration")）。

骨架不動：選項、檢定、效果、數字一個字都不碰，只換事件卡上面那一段旁白（Event.text）。模型每「一週」（季曆的週；7 天的季是
一段，約兩天）把每一則重寫一次，全服只生一份，認（第幾季, 第幾週, 事件 id）存在資料庫旁邊的小檔（NarrationStore），
同一週裡每個人看到同一段；這一週還沒寫到、寫壞了、模型連不上，照內容原文。

不改寫的（eligible）：序章、開局、伏筆、晉升奇遇、一次性奇遇與奇遇（once、qiyu）、福緣、只由別的事件串接的（actions 空的）。
批 4 的分岔後果（隨口應對的後果文字）等主機那邊接好再納入：那是選了之後的結果，不是這一段旁白，這裡先不碰。

寫的人是伺服器的背景執行緒（server.narration_round）：不在行動鎖裡、排在真人後面、省電模式沒人在線時不叫模型；假人程式不叫。
引擎只讀：Game.narration（伺服器塞進來的查詢函式；沒有就是 None，一律原文）。這個模組不讀時鐘。"""
from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

from . import calendar, events, foreshadow, rules, zh
from .models import Content, Event
from .state import WorldState

Lookup = Callable[[int, int, str], "str | None"]  # (第幾季, 第幾週, 事件 id) → 改寫好的旁白；沒有是 None

NUM_PREDICT = 600  # 一段旁白（原文多半一百多字）加一點餘裕：只加不減（模型與假人那一份導覽「num_predict 只加不減」）
# 改寫的長度要在原文的幾倍之間（太短是漏了事，太長是加了戲）。上限原本 1.6：2026-10-26 主機整週實測發現
# 99% 的改寫都比原文長（平均 1.19 倍、最長 1.53），1.6 等於沒在擋。SYSTEM 補了「字數不可以多於原文」之後
# 同一批 30 則平均 0.97 倍、最長 1.03，1.25 留的是模型偶爾不聽話時的餘裕。
MIN_RATIO, MAX_RATIO = 0.6, 1.25
_MARKS = re.compile(r"\{marks:[^}]+\}")
_DIGITS = re.compile(r"[0-9０-９]")
_KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")
_LATIN = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]")

SYSTEM = (
    "你替一款東漢末年黃巾之亂的武俠文字遊戲潤飾事件的旁白。使用者給你一則事件的標題與原文，請換一種說法重寫同一件事："
    "人、地、物、發生了什麼、誰說了什麼都照原文，不添新的人名、地名、門派與兵器，不改任何數目，不加結局，不替讀者做決定。"
    "標題只是讓你知道這是哪一件事，不要寫進旁白。"
    "用第二人稱「你」，繁體中文，只寫旁白本身：不要標題、不要列點、不要引號包起整段、不要解說。"
    "原文裡像 {marks:…} 這種大括號標記要原樣留著、一個字都不能改。"
    "有人說話時照原文用「」把話括起來，原文有幾個引號就有幾個。"
    "語感照原文：短句、口語的武俠白話，不是現代書面語。字數不可以多於原文，跟原文一樣長最好；"
    "但也不要為了短而壓成文言、省掉原文交代的事。"
    "「換一種說法」可以換句子的排法（語序、斷句、先說哪一件），但換完一定要讀得順、意思跟原文一樣："
    "寧可保守，也不要為了「有換過」就把句子拆亂、寫出不通的句子、或把同一句話說兩次。"
    "原文挑過的那些具體的詞（器物、動作、神態：博局、石鎖、拄著、砍過、喊得）照原樣留著，不要換成同義詞，換了多半更差；"
    "想不出別的說法的那一句，照原文抄回來就好。"
    "這幾種寫法一律不要（都是把旁白寫長、寫成現代文章的毛病）："
    "一、改原文的量詞——原文寫「一個」「幾個」「十幾個」就照寫，不要換成「一名」「幾名」「十幾名」。"
    "二、在句子前面補「在……」「此時……」「就在這……」把句子框起來。"
    "三、加「正忙於」「進行」「處於……的狀態」「顯得」「察覺」「表示」「注意到」「明顯」這類交代與解釋的話。"
    "四、原文直接接引號說話的，前面不要補「對你說」「開口道」「命令你」。"
    "五、原文沒有的文言虛詞不要自己加（其、其中、將其、並、然而、因此、由於、立於、之下），"
    "現代詞也不要（民眾、過程、狀態、情緒、動作、邀請、協助、控訴、販售）。"
    "六、每一句都是「誰、做了什麼」的走法：做事的人照原文留在動作前面，原文是主動就主動（不要改成「被」字句），"
    "交代人在哪、東西在哪的那一截（「劉備身旁」「集市角落」）也留在它說明的那個人、那件東西前面。"
)


def on(content: Content, world: WorldState | None) -> bool:
    return rules.jianfa(content, world, "rewrite_narration")


def period(content: Content, world: WorldState) -> int:
    """現在是第幾「週」：季曆的週（21 天季七天一週；7 天的季是一段，約兩天，calendar.point 的 week）。"""
    return calendar.point(world.time, content, world).week


def eligible(content: Content) -> list[str]:
    """這一季要改寫的事件（照 id 排，背景執行緒照這個順序寫）：從池子裡抽得到的那些（actions 不空），扣掉奇遇與一次性的、福緣、
    伏筆的、晉升的；序章、開局、晉升召見都是串接或指定的（actions 空的），本來就不在裡面。"""
    skip = foreshadow.event_ids(content) | {x for p in content.promotions for x in (p.event_main, p.event_handoff) if x}
    return sorted(
        e.id for e in content.events.values()
        if e.actions and not events.is_rare(e) and not e.fortune and e.id not in skip
    )


def text_of(content: Content, world: WorldState | None, event: Event, season: int, lookup: Lookup | None) -> str:
    """事件卡上要畫的旁白（還沒套 fill_marks）：這一季開著改寫、這一週寫好了就用改寫的，否則照原文。"""
    if lookup is None or world is None or not on(content, world) or event.id not in _eligible_set(content):
        return event.text
    try:
        written = lookup(season, period(content, world), event.id)
    except Exception:  # noqa: BLE001  小檔讀不到（被鎖、壞了）：照原文，不能讓事件端不上來
        return event.text
    return written or event.text


_ELIGIBLE: dict[int, frozenset[str]] = {}


def _eligible_set(content: Content) -> frozenset[str]:
    key = id(content)
    found = _ELIGIBLE.get(key)
    if found is None:
        found = _ELIGIBLE[key] = frozenset(eligible(content))
    return found


def _names(content: Content) -> list[str]:
    """不能憑空冒出來的專有名詞：人物、地點、門派、陣營的名字（原文有的才准有）。"""
    found = [ch.name for ch in content.characters.values()]
    found += [loc.name for loc in content.locations.values()]
    found += [f.name for f in content.scenario.factions]
    found += [s.name for s in content.sects.values()]
    return [n for n in found if n and len(n) >= 2]


def _repeats(out: str, original: str) -> bool:
    """同一句話寫了兩次（原文自己沒有重複的那一句才算壞）：照句號、問號、驚嘆號斷句，只看夠長的句子。"""
    cut = [s for s in re.split(r"[。！？]", out) if len(s.strip()) >= 8]
    return any(cut.count(s) > 1 and original.count(s) < cut.count(s) for s in cut)


def clean(content: Content, original: str, text: str | None) -> str | None:
    """模型寫的能不能用：轉繁體、去 markdown 的標記與包住整段的引號、併成一段；長度在原文的 MIN_RATIO～MAX_RATIO 倍之間；
    {marks:…} 標記一個不少、一個不多；引號「」跟原文一樣多；沒有阿拉伯數字（原文有的照原文）、假名、英文字母；不冒出原文沒有的人名、地名、門派、陣營；
    不用到禁用名單（既有作品的專有名詞）。過不了是 None（照原文）。"""
    out = zh.to_traditional(str(text or "")).strip()
    # 清 markdown 之前先把 {marks:...} 收起來：標記的 id 多半帶底線（yingchuan_academy、zhuo_county……），
    # 底下那一行為了拿掉強調符號會連標記裡的底線一起吃掉，於是跟原文比標記永遠不相等、改寫永遠退回原文
    # （2026-10-26 主機整週實測：退回的 25 則裡 22 則是這樣來的，模型其實一字不差地照抄了標記）。
    kept = _MARKS.findall(out)
    for i, mark in enumerate(kept):
        out = out.replace(mark, f"\x00{i}\x00", 1)
    out = re.sub(r"^[#>*\-\s]+", "", out, flags=re.MULTILINE)
    out = re.sub(r"[*_`#]", "", out)
    for i, mark in enumerate(kept):
        out = out.replace(f"\x00{i}\x00", mark, 1)
    out = "".join(p.strip() for p in out.split("\n") if p.strip())
    if "【" not in original:  # 模型自己加的標題（內容的原文裡一個全角方括號都沒有）：拿掉開頭那一個，後面照用
        out = re.sub(r"^【[^】]{0,16}】[，。：\s]*", "", out)
    if len(out) >= 2 and out[0] in "「『\"“" and out[-1] in "」』\"”" and out.count(out[0]) == 1:
        out = out[1:-1].strip()
    if not out or out == original:
        return None
    if not (MIN_RATIO * len(original) <= len(out) <= MAX_RATIO * len(original)):
        return None
    if sorted(_MARKS.findall(out)) != sorted(_MARKS.findall(original)):
        return None
    # 引號一個不少（2026-10-26 主機實測：改寫把「」整對吃掉的有一成四，對話沒有引號玩家一眼看得出來）
    if any(out.count(q) != original.count(q) for q in "「」"):
        return None
    if _repeats(out, original):  # 搬句子搬到把同一句寫兩次（同一輪實測遇到）
        return None
    bare = _MARKS.sub("", out)
    if _DIGITS.findall(bare) != _DIGITS.findall(_MARKS.sub("", original)) or _KANA.search(bare) or _LATIN.search(bare):
        return None
    if any(n in out and n not in original for n in _names(content)):
        return None
    if any(b and b in out and b not in original for b in content.banned_name_list()):
        return None
    return out


def write(client, content: Content, event: Event) -> str | None:
    """請模型改寫一則（鎖外；server.narration_round）。叫不動、寫壞了、沒有 client 都是 None（照原文）。不碰狀態。"""
    if client is None:
        return None
    messages = [
        {"role": "system", "content": SYSTEM},
        # 標題標明是參考、原文標明是原文：原本直接餵「【標題】\n原文」，模型照著格式回，旁白開頭長出【壕溝之外】這種自訂標題
        {"role": "user", "content": f"標題（參考，不要寫進旁白）：{event.title}\n原文（{len(event.text)} 字）：{event.text}"},
    ]
    try:
        reply = client.chat_text(messages, temperature=0.9, num_predict=NUM_PREDICT)
    except Exception:  # noqa: BLE001  模型叫不動：照原文
        return None
    return clean(content, event.text, reply)


class NarrationStore:
    """改寫好的旁白（資料庫旁邊的小檔 <db>-narration.sqlite；不進遊戲資料庫的結構）。一筆一則：（季, 週, 事件 id）→ 旁白；
    丟了只是這一週照原文、背景再寫一次。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS narration (season INTEGER NOT NULL, week INTEGER NOT NULL, event TEXT NOT NULL, "
                "text TEXT NOT NULL, PRIMARY KEY (season, week, event))")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def get(self, season: int, week: int, event_id: str) -> str | None:
        with contextlib.closing(self._conn()) as conn:
            row = conn.execute("SELECT text FROM narration WHERE season = ? AND week = ? AND event = ?",
                               (season, week, event_id)).fetchone()
        return row[0] if row else None

    def put(self, season: int, week: int, event_id: str, text: str) -> None:
        """記一則（同一則寫兩次以先寫的為準：同一週大家看同一段）；順手清掉兩週以前的。"""
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO narration VALUES (?, ?, ?, ?)", (season, week, event_id, text))
            conn.execute("DELETE FROM narration WHERE season < ? OR (season = ? AND week < ?)", (season, season, week - 1))

    def done(self, season: int, week: int) -> set[str]:
        with contextlib.closing(self._conn()) as conn:
            return {r[0] for r in conn.execute("SELECT event FROM narration WHERE season = ? AND week = ?", (season, week))}
