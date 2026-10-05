"""戰況變化的說法（FB-064）：第一季規則開著時，推動戰線、豪強割據的那一行不再寫「（潁川汝南 -1）」，
改成一句話——「潁川汝南：官軍步步進逼」「豪強趁亂坐大」——畫面上是一枚數值標籤，顏色照看的人站哪一邊。

句子在 content/front_lines.json，依變動的大小分三段（BANDS），一段有好幾句時照那一則紀錄的時間與戰線雜湊挑一句——
同一則永遠是同一句，也不動引擎的亂數（同 check_lines）。純文字與雜湊，不 import 內容模型以外的東西。

機器可讀的寫法（mark）：engine 與規則回傳的訊息裡，戰況變化寫成「大勢@<線 id> ±N」，格式跟其他數值變化（「銀兩 -5」）
同一套，所以江湖紀錄照舊把同一則裡同一條線的變動加總（−1 與 −2 合成 −3）、再換成一句話——換句話一律發生在畫出來的
那一刻（journal 的標籤、Game._log 的回話），數字不會到玩家眼前。"""
from __future__ import annotations

import re
import zlib

MARK = "大勢@"  # 機器可讀的戰況變化的標籤開頭；畫面上不會出現（journal 換成一句話，沒得換的就不畫）
_MARKED = re.compile(rf"^{re.escape(MARK)}(\S+) ([+-]\d+)$")

# (檔案裡的鍵, 這一段變動大小的下限)：由大到小。小＝變動 1、中＝2～3、大＝4 以上（企劃者 2026-10-05）
BANDS: tuple[tuple[str, int], ...] = (("4+", 4), ("2-3", 2), ("1", 1))
BAND_KEYS: tuple[str, ...] = tuple(key for key, _ in BANDS)
GEJU_KEYS: tuple[str, ...] = ("up", "down")  # 豪強割據：漲、落


def mark(trend_id: str, delta: int) -> str:
    """「大勢@yingru -1」：這一次真的動了的戰況（夾過 0～100 之後的實際變動）。"""
    return f"{MARK}{trend_id} {delta:+d}"


def is_mark(msg: str) -> bool:
    return msg.startswith(MARK)


def unmark(change: str) -> tuple[str, int] | None:
    """「大勢@yingru -3」→ ("yingru", -3)；不是這種寫法回 None。"""
    m = _MARKED.match(change.strip())
    return (m.group(1), int(m.group(2))) if m else None


def band_of(delta: int) -> str:
    """變動的大小（看絕對值）落在哪一段。"""
    size = abs(delta)
    for key, low in BANDS:
        if size >= low:
            return key
    return BANDS[-1][0]


def pick(pool: list[str], seed: str) -> str:
    """一段有好幾句時，照 seed 雜湊挑一句（同一個 seed 永遠同一句）。"""
    if len(pool) == 1:
        return pool[0]
    return pool[zlib.crc32(seed.encode("utf-8")) % len(pool)]
