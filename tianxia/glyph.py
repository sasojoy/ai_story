"""感悟狀態畫的那一筆（悟意境設計 0.2 第 4 步、0.2a）：純規則、不看模型，同一筆永遠讀出同一個結果。

前端送來的是一筆的點位 [[x, y, 毫秒], …]（一筆畫到底，手指離開畫布就算畫完）。這裡把它讀成幾個看得懂的特徵——
直或彎（硬折角幾處、總共轉了多少）、頭尾接不接、畫得快或慢、往上或往下——再照固定的順序對到一個「畫出來的屬性」：

1. 畫得快、折角不到兩處 → 快（短而急的一筆）
2. 頭尾相接、硬折角兩處以上 → 慢（閉合方正）
3. 硬折角兩處以上 → 剛（折角多）
4. 一路圓轉（總共轉過半圈以上）→ 柔（圓弧、波浪、圈）
5. 頭尾相接 → 慢；畫得慢 → 慢
6. 其餘（差不多是一條直線）→ 剛

屬性只由這裡定，模型只看圖寫名字與說明（實測同一張鋸齒圖被形容成「震盪」「連波」「連峰」，形容會飄，不能拿來定屬性）。

玩家面前不寫任何筆畫的幾何（折角、圓轉、快慢……，企劃者 2026-10-06：「會降低玩家的驚喜感」）。規則另外多讀幾樣
（大小、蜿蜒、橫直、升沉、頭尾、起筆收筆的緩急），換成意象與質感的詞（Glyph.imagery：「熊熊烈火般的剛烈」「氣象開闊」），
只交給模型當線索、模型叫不動時當說明的退路。
點位是客戶端送的：亂送的點頂多讓玩家挑到他要的屬性，跟老老實實畫一筆一樣，不必防。"""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_POINTS = 600  # 一筆最多收幾個點（再多就截掉；手機一秒大約 60 個點，十秒夠了）
MIN_POINTS = 2
RESAMPLE = 64  # 讀特徵時先重新取樣成等距的這麼多點
THUMB = 32  # 存縮圖的點數
SHARP_DEG = 60.0  # 一處硬折角：方向一下子轉了這麼多度以上
BEND_MIN = 15.0  # 一個點轉這麼多度以上，才算是在折（64 點的圓每點只轉五六度、波浪的峰頂十來度）
BEND_SPAN = 4  # 一處折角最多跨幾個點（抹平之後一個角會攤在三四個點上）
SMOOTH = 1  # 量轉角之前，每個點跟前後各幾個點取平均
STRAIGHT = 0.08  # 每一點離頭尾連線都不到全長的這幾成，就是一道直線
CLOSED_SHARE = 0.18  # 頭尾的距離在外框對角線的這幾成以內算接上了
FAST_MS = 600  # 畫完不到這麼多毫秒算快
SLOW_MS = 1500  # 超過這麼多毫秒算慢
CURVE_DEG = 180.0  # 總共轉過這麼多度（半圈）以上、硬折角又少，算一路圓轉
TOO_SMALL = 3.0  # 外框比這還小（畫布座標）就是點了一下，不算一筆
CANVAS = 256  # 網頁畫布的邊長（web/app.js 的 SENSE_SIZE）：量「畫得多大」用
BIG = 0.55  # 外框對角線佔畫布對角線這幾成以上算畫得大
SMALL = 0.25  # 這幾成以下算畫得小
WINDING = 3.0  # 筆畫全長是外框對角線的這幾倍以上算蜿蜒繁複
PLAIN = 1.3  # 這幾倍以下算簡淨（差不多一道過去）
FLAT = 2.0  # 寬是高的這幾倍以上算橫（反過來算直）
SURGE = 1.6  # 前三分之一跟後三分之一的速度差這幾倍以上，算起筆急收筆緩（或反過來）


class GlyphError(ValueError):
    """送來的不是一筆讀得出來的畫（點太少、格式不對、只點了一下）。"""


@dataclass(frozen=True)
class Glyph:
    attribute: str  # 剛、柔、快、慢
    corners: int  # 硬折角幾處
    turning: float  # 總共轉了幾度
    closed: bool  # 頭尾接上了
    duration: int  # 畫了幾毫秒
    rising: bool  # 往上走（畫布的 y 越往下越大：終點比起點高）
    points: list[list[int]]  # 等距取樣、縮到 0～100 的點位（存進意境、畫縮圖）
    size: float = 0.0  # 外框對角線佔畫布對角線的幾成
    winding: float = 1.0  # 筆畫全長是外框對角線的幾倍
    lie: str = ""  # 「橫」「直」或空字串（不偏哪邊）
    surge: str = ""  # 「急收緩」（起筆急、收筆緩）、「緩收急」（先慢後快）或空字串

    def imagery(self) -> list[str]:
        """這一筆的意象與質感（最多四個詞，照固定順序挑，同一筆永遠一樣）：只交給模型當線索、當說明的退路，不直接給玩家看
        筆畫本身。第一個詞跟著畫出來的屬性走，其餘看大小、蜿蜒、頭尾、升沉、橫直、緩急。"""
        words = [ATTRIBUTE_IMAGERY.get(self.attribute, "")]
        if self.size >= BIG:
            words.append("氣象開闊")
        elif self.size <= SMALL:
            words.append("凝而不散")
        if self.winding >= WINDING:
            words.append("層層相疊、纏綿不絕")
        elif self.winding <= PLAIN:
            words.append("簡淨，一往無前")
        if self.closed:
            words.append("圓融自足，自成一方天地")
        elif self.rising:
            words.append("有升騰之勢")
        else:
            words.append("有沉墜之意")
        if self.surge == "急收緩":
            words.append("來勢洶洶而餘韻悠長")
        elif self.surge == "緩收急":
            words.append("先斂後發，蓄勢待放")
        elif self.lie == "橫":
            words.append("橫亙如地平")
        elif self.lie == "直":
            words.append("上下貫通")
        return [w for w in words if w][:4]

    def mood(self) -> str:
        """意象串成一句（給模型的線索）：「熊熊烈火般的剛烈、氣象開闊、有升騰之勢」。"""
        return "、".join(self.imagery())


ATTRIBUTE_IMAGERY = {  # 畫出來的屬性 → 意象（附錄 A 的四象：風快、火剛、水柔、山慢）
    "剛": "熊熊烈火般的剛烈",
    "柔": "流水般的綿柔",
    "快": "疾風般的迅捷",
    "慢": "山岳般的沉穩厚重",
}


def _clean(points) -> list[tuple[float, float, float]]:
    if not isinstance(points, list):
        raise GlyphError("畫的那一筆格式不對。")
    out: list[tuple[float, float, float]] = []
    for item in points[:MAX_POINTS]:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            raise GlyphError("畫的那一筆格式不對。")
        try:
            x, y, t = (float(v) for v in item[:3])
        except (TypeError, ValueError):
            raise GlyphError("畫的那一筆格式不對。") from None
        if not all(math.isfinite(v) for v in (x, y, t)):
            raise GlyphError("畫的那一筆格式不對。")
        if out and x == out[-1][0] and y == out[-1][1]:
            continue  # 手指停著不動的重複點
        out.append((x, y, t))
    if len(out) < MIN_POINTS:
        raise GlyphError("只點了一下，沒有畫成一筆。")
    return out


def _resample(pts: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    """沿著筆畫等距取 n 個點（畫得快慢不同、點的疏密不同，等距之後才比得了轉角）。"""
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg)
    if total <= 0:
        return [pts[0]] * n
    step, out, acc, i = total / (n - 1), [pts[0]], 0.0, 0
    for k in range(1, n - 1):
        target = k * step
        while i < len(seg) - 1 and acc + seg[i] < target:
            acc += seg[i]
            i += 1
        share = (target - acc) / seg[i] if seg[i] > 0 else 0.0
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        out.append((x0 + (x1 - x0) * share, y0 + (y1 - y0) * share))
    out.append(pts[-1])
    return out


def read(points) -> Glyph:
    """把一筆讀成特徵與屬性。點位格式不對、只點了一下丟 GlyphError（訊息可以直接給玩家看）。"""
    raw = _clean(points)
    xs, ys = [p[0] for p in raw], [p[1] for p in raw]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    diag = math.hypot(width, height)
    if diag < TOO_SMALL:
        raise GlyphError("只點了一下，沒有畫成一筆。")
    pts = _resample([(p[0], p[1]) for p in raw], RESAMPLE)
    soft = _smooth(pts)  # 手指會抖：先抹平一點再量轉角，不然抖出來的小轉角會加成一圈圈
    angles = []
    for i in range(1, len(pts) - 1):
        a = math.atan2(soft[i][1] - soft[i - 1][1], soft[i][0] - soft[i - 1][0])
        b = math.atan2(soft[i + 1][1] - soft[i][1], soft[i + 1][0] - soft[i][0])
        turn = math.degrees(b - a)
        turn = (turn + 180) % 360 - 180
        angles.append(turn)
    corners, bends = _corners(angles)
    smooth = [a for i, a in enumerate(angles) if i not in bends]  # 硬折角那幾個點不算進「圓轉」
    turning = 0.0 if _straight(pts) else sum(abs(a) for a in smooth)
    closed = math.dist(pts[0], pts[-1]) <= CLOSED_SHARE * diag
    duration = int(max(0.0, raw[-1][2] - raw[0][2]))
    rising = raw[-1][1] < raw[0][1]
    attribute = _attribute(corners, turning, closed, duration)
    scale = 100 / max(width, height)
    box = [[round((x - min(xs)) * scale), round((y - min(ys)) * scale)] for x, y in _resample(pts, THUMB)]
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    lie = "橫" if width >= FLAT * height else "直" if height >= FLAT * width else ""
    return Glyph(
        attribute, corners, round(turning, 1), closed, duration, rising, box,
        size=round(min(1.0, diag / (CANVAS * math.sqrt(2))), 2), winding=round(length / diag, 2), lie=lie, surge=_surge(raw),
    )


def _surge(raw: list[tuple[float, float, float]]) -> str:
    """起筆與收筆的緩急：前三分之一的點跟後三分之一的點各自的速度（畫布單位／毫秒）比一比。時間都一樣（沒有計時）就是空字串。"""
    third = len(raw) // 3
    if third < 2:
        return ""

    def speed(part):
        dist = sum(math.dist(part[i][:2], part[i + 1][:2]) for i in range(len(part) - 1))
        spent = part[-1][2] - part[0][2]
        return dist / spent if spent > 0 else None

    head, tail = speed(raw[: third + 1]), speed(raw[-third - 1:])
    if not head or not tail:
        return ""
    if head >= SURGE * tail:
        return "急收緩"
    if tail >= SURGE * head:
        return "緩收急"
    return ""


def _corners(angles: list[float]) -> tuple[int, set[int]]:
    """硬折角：連著幾個點（最多 BEND_SPAN 個）往同一邊轉、加起來超過 SHARP_DEG 度算一處——等距取樣常把一個角切成兩三個小轉。
    回（幾處, 屬於折角的那些點）。圓弧每一點只轉一點點（64 點的圓一點約 6 度），湊不成一處。"""
    count, bends, i = 0, set(), 0
    while i < len(angles):
        if abs(angles[i]) < BEND_MIN:
            i += 1
            continue
        j, total = i, 0.0
        while j < len(angles) and j - i < BEND_SPAN and abs(angles[j]) >= BEND_MIN and angles[j] * angles[i] > 0:
            total += angles[j]
            j += 1
        if abs(total) >= SHARP_DEG:
            count += 1
            bends.update(range(i, j))
        i = j
    return count, bends


def _straight(pts: list[tuple[float, float]]) -> bool:
    """差不多是一道直線：每一點離頭尾連線都不到全長的 STRAIGHT 幾成（手抖出來的小彎不算圓轉）。頭尾接上的不是直線。"""
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    chord = math.dist(pts[0], pts[-1])
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if chord <= 0 or length <= 0:
        return False
    far = max(abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / chord for x, y in pts)
    return far <= STRAIGHT * length


def _smooth(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """前後各 SMOOTH 個點取平均（頭尾不動）。"""
    out = []
    for i in range(len(pts)):
        lo, hi = max(0, i - SMOOTH), min(len(pts), i + SMOOTH + 1)
        window = pts[lo:hi]
        out.append((sum(p[0] for p in window) / len(window), sum(p[1] for p in window) / len(window)))
    return out


def _attribute(corners: int, turning: float, closed: bool, duration: int) -> str:
    if duration < FAST_MS and corners <= 1:
        return "快"  # 短而急的一筆
    if closed and corners >= 2:
        return "慢"  # 閉合方正
    if corners >= 2:
        return "剛"  # 折角多
    if turning >= CURVE_DEG:
        return "柔"  # 圓弧、波浪、圈
    if closed or duration >= SLOW_MS:
        return "慢"
    return "剛"  # 直直一道


def _wave() -> list[list[float]]:
    return [[i * 6, 50 + 25 * math.sin(i / 3), i * 70] for i in range(30)]


def _square() -> list[list[float]]:
    corners = [(10, 10), (90, 10), (90, 90), (10, 90), (12, 12)]
    out, t = [], 0
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        for k in range(10):
            out.append([x0 + (x1 - x0) * k / 10, y0 + (y1 - y0) * k / 10, t])
            t += 60
    out.append([12, 12, t])
    return out


# 假人與整季機器人不會畫：照它想要的屬性挑一筆現成的（悟意境設計 0.4），送出去一樣走 read，讀出來就是那個屬性
SAMPLES: dict[str, list[list[float]]] = {
    "剛": [[0, 80, 0], [25, 10, 200], [50, 80, 400], [75, 10, 600], [100, 80, 800]],  # 鋸齒
    "柔": _wave(),  # 波浪，慢慢畫
    "快": [[0, 90, 0], [50, 50, 120], [100, 10, 250]],  # 一道急急的斜線
    "慢": _square(),  # 方框，頭尾相接，慢慢畫
}
