"""擺式的幾何（共用規則層；全部拆包第 44 批從 create.py 抽出來）：火柴人九個角度 → 兩手兩腳的座標 → 勢與偏向。
`moves.stance_of_art`（以意成招認勢，共用規則層）要用，原本在 create 函式裡 import；create 進煉製包之後共用層不能 import 包，
所以這一段留在共用層，create 照名字 re-export（create.stance_of、icon_pose、preset、POSE_KEYS、pose_read 照舊拿得到）。
只 import martial_arts、models，不 import 別的規則模組。"""
from __future__ import annotations

import math

from .martial_arts import ATTRIBUTES, MartialArt
from .models import Content

POSE_KEYS = ("t", "lS", "lE", "rS", "rE", "lH", "lK", "rH", "rK")
TORSO_LIMIT = 35
DEFAULT_PRESET = "起手"

# 火柴人的骨架（跟 web/app.js 的 RIG 同一組數字：拖出來的角度照同一個幾何讀）
CX, SY, HIPY = 110.0, 96.0, 146.0
UA, FA, TH, SH = 27.0, 25.0, 31.0, 29.0
POSE_FLOOR = 0.35  # 最強那一路不到這麼多就是「平正，不偏」

FLAT_LINE = "此式平正，不偏一路"  # 待 joy 潤


def preset(content: Content, name: str = DEFAULT_PRESET) -> dict[str, float]:
    p = next((x for x in content.create_forms.presets if x.name == name), None)
    angles = dict(p.angles) if p is not None else {}
    return {k: float(angles.get(k, 0.0)) for k in POSE_KEYS}


# 功法卡上的小圖：自創的照自己擺的式；其餘照兵器挑一個預設的架式（內功與推不出兵器的照 None）
ICON_PRESET = {"拳腳": "起手", "劍": "進擊", "刀": "進擊", "槍": "進擊", "棍": "守禦", "弓弩": "奇變", None: "守禦"}


def icon_pose(content: Content, art: MartialArt, weapon: str | None) -> dict[str, float]:
    if art.pose:
        return {k: float(art.pose.get(k, 0.0)) for k in POSE_KEYS}
    return preset(content, ICON_PRESET.get(weapon if art.kind == "武學" else None, DEFAULT_PRESET))


def _norm(d: float) -> float:
    d = math.fmod(d, 360.0)
    if d > 180:
        d -= 360
    elif d < -180:
        d += 360
    return d


def clean_pose(pose: dict, base: dict[str, float]) -> dict[str, float]:
    """網頁送來的九個角度：不是數字的照 base，其餘正規化到 ±180，上身傾夾在 ±TORSO_LIMIT。"""
    out = {k: float(base.get(k, 0.0)) for k in POSE_KEYS}
    for k in POSE_KEYS:
        try:
            v = float((pose or {}).get(k, out[k]))
        except (TypeError, ValueError, AttributeError):
            continue
        if not math.isfinite(v):
            continue
        v = max(-TORSO_LIMIT, min(TORSO_LIMIT, v)) if k == "t" else _norm(v)
        out[k] = round(v, 1)
    return out


def joints(pose: dict[str, float]) -> dict[str, tuple[float, float]]:
    """九個角度 → 兩手兩腳的座標（跟網頁的火柴人同一個幾何；0 度朝下、正的往右）。"""
    r = math.radians
    t = r(pose.get("t", 0.0))

    def chain(x, y, a1, l1, a2, l2):
        e = (x + math.sin(a1) * l1, y + math.cos(a1) * l1)
        return (e[0] + math.sin(a1 + a2) * l2, e[1] + math.cos(a1 + a2) * l2)

    return {
        "lHa": chain(CX - 9, SY, r(pose.get("lS", 0)) + t, UA, r(pose.get("lE", 0)), FA),
        "rHa": chain(CX + 9, SY, r(pose.get("rS", 0)) + t, UA, r(pose.get("rE", 0)), FA),
        "lFt": chain(CX - 7, HIPY, r(pose.get("lH", 0)), TH, r(pose.get("lK", 0)), SH),
        "rFt": chain(CX + 7, HIPY, r(pose.get("rH", 0)), TH, r(pose.get("rK", 0)), SH),
    }


def _features(pose: dict[str, float]) -> tuple[float, float, bool, float, bool, float]:
    """（手伸多遠, 手抬多高, 雙手收胸, 馬步多寬, 提腿, 前後傾）——偏向與勢都照它讀（跟網頁 poseRead 同一套幾何）。"""
    j = joints(pose)
    lh, rh, lf, rf = j["lHa"], j["rHa"], j["lFt"], j["rFt"]
    reach = max(abs(rh[0] - CX), abs(lh[0] - CX)) / (UA + FA)
    high = max(SY - rh[1], SY - lh[1]) / (UA + FA)
    tucked = math.hypot(rh[0] - CX, rh[1] - (SY + 20)) < 30 and math.hypot(lh[0] - CX, lh[1] - (SY + 20)) < 30
    spread = abs(lf[0] - rf[0]) / (TH + SH)
    lift = min(lf[1], rf[1]) < HIPY + TH * 1.3
    return reach, high, tucked, spread, lift, pose.get("t", 0.0)


def stance_of(pose: dict[str, float]) -> str:
    """以意成招的「勢」（moves.STANCE_TIMING）：提腿是變勢；雙手收胸、或馬步寬而手不出是守勢；手伸得遠或身子前傾是攻勢；其餘起勢。"""
    reach, _high, tucked, spread, lift, lean = _features(pose)
    if lift:
        return "變勢"
    if tucked or (spread > 1.1 and reach < 0.95):
        return "守勢"
    if reach >= 1.0 or lean <= -10:
        return "攻勢"
    return "起勢"


def pose_scores(pose: dict[str, float]) -> dict[str, float]:
    """姿勢讀出來的偏向（只有剛柔快慢虛實；陰陽靠兵器與意）。"""
    reach, high, tucked, spread, lift, lean = _features(pose)
    s = {a: 0.0 for a in ("剛", "柔", "快", "慢", "實", "虛")}
    s["剛"] += max(0.0, reach - 0.95) * 8 + max(0.0, high - 0.15) * 2
    if tucked:
        s["柔"] += 1.6
    s["實"] += max(0.0, spread - 0.9) * 3
    s["慢"] += max(0.0, spread - 1.1) * 2
    if lift:
        s["虛"] += 2.0
        s["快"] += 1.0
    if lean < -12:
        s["快"] += (-lean - 12) / 15
    if lean > 10:
        s["慢"] += (lean - 10) / 15
    return s


def pose_read(pose: dict[str, float]) -> list[str]:
    """最強的一路（不到 POSE_FLOOR 是空的＝平正），第二路要過 POSE_FLOOR 又有第一路的六成才算。"""
    ranked = sorted(pose_scores(pose).items(), key=lambda kv: (-kv[1], ATTRIBUTES.index(kv[0])))
    if ranked[0][1] < POSE_FLOOR:
        return []
    out = [ranked[0][0]]
    if ranked[1][1] > POSE_FLOOR and ranked[1][1] > ranked[0][1] * 0.6:
        out.append(ranked[1][0])
    return out


def read_text(attrs: list[str]) -> str:
    if not attrs:
        return FLAT_LINE
    return "此式偏" + attrs[0] + ("、兼" + attrs[1] if len(attrs) > 1 else "")
