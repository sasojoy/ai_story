"""坐騎（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第五節；裝備二）：移動以省體力為主（趕路、疾行的體力，步行、趕路的時間），
另有三個用途——決戰騎兵（5.9）、截殺追逃（5.10）、落敗策馬脫身（5.11）；飽足度與餵、馬市、馬的名字與階、修練頁每一列與角色卡那一行。

數字全部乘飽足係數（edge_floor＋（1－edge_floor）×飽足度／100，5.4）；腳力＝省體力那一列（含品質）×飽足係數（5.1）。
只 import models、state、equipment（3.4：atlas 反過來 import 這裡算步調與腳力，engine、skillview、bot 也呼叫它），
不 import team、rules、atlas。開關是 Config.mounts.enabled（equipment.on(content, "mount")），不掛第一季開關（2.6）。
好馬（良駒、名駒）的來源是裝備三：這裡的數字、名字、比較都照階與品質寫，容得下良駒、名駒；名駒的專名到時候照 template 從內容讀，
所以這裡與引擎寫給玩家看的馬名都經過 name_of。例外：equipment.store（騎上、放上裝備庫）與 equipment.wield（換上）是四欄共用的，
直接用 item.name——裝備三要在 equipment 加依欄位取名的掛鉤，不能只改 name_of（計畫「範圍與取捨」）。
"""
from __future__ import annotations

import hashlib
import math

from . import equipment
from .models import Content
from .state import Equipment, GameState

MARKET = "馬市"  # 選單上那一顆、紀錄的標題（待 joy 潤）
MARKET_TAG = "馬市"  # 地點標籤（content/locations.json：涿郡、汝南集市、宛城、下曲陽，5.5）；不寫死地點 id
TIER_NAMES = {1: "駑馬", 2: "良駒", 3: "名駒"}  # 5.6（待 joy 潤）
NOUNS = {1: "馬", 2: "駒", 3: "駒"}  # 名字＝毛色＋這個字；名駒的專名是裝備三的內容（template），還沒有時照「駒」（待 joy 潤）
COATS = ("棗騮", "青驄", "黑鬃", "白蹄", "花斑", "黃棕")  # 待 joy 潤：12 個名字都過了 naming.name_problem、沒在內容裡出現過
WEAR_WORD = equipment.WEAR_WORDS["mount"]  # 「飽足度」：寫到它的地方都讀這個，不寫死（3.1、2.5）


def on(content: Content) -> bool:
    return equipment.on(content, "mount")


def riding(state: GameState, content: Content) -> Equipment | None:
    """身上那匹；開關關著、沒騎是 None。"""
    item = state.player.mount
    return item if on(content) and item is not None and item.slot == "mount" else None


def _cell(table: dict[str, float], item: Equipment) -> float:
    return table.get(str(item.tier), 0.0)


def fed_factor(content: Content, item: Equipment) -> float:
    """飽足係數（5.1、5.4）：餓到底剩 edge_floor，吃飽是 1。"""
    floor = content.config.mounts.edge_floor
    return floor + (1 - floor) * max(0, min(100, item.edge)) / 100


def _quality(content: Content, item: Equipment) -> float:
    return content.config.mounts.quality_bonus.get(item.quality, 0.0)


def speed_of(content: Content, item: Equipment) -> float:
    """這一匹路上快幾成（5.1）：路上快那一列（含品質）×飽足係數。"""
    return (_cell(content.config.mounts.speed, item) + _quality(content, item)) * fed_factor(content, item)


def leg_power(content: Content, item: Equipment | None) -> float:
    """這一匹的腳力（5.1）：省體力那一列（含品質）×飽足係數。不是坐騎、開關關著是 0。"""
    if item is None or item.slot != "mount" or not on(content):
        return 0.0
    return (_cell(content.config.mounts.stamina_save, item) + _quality(content, item)) * fed_factor(content, item)


def fresh_power(content: Content, item: Equipment | None) -> float:
    """吃飽的腳力：機器人比較兩匹用（不然餓了的好馬會被當成比較差的），馬市「買」鈕寫的也是它。"""
    return leg_power(content, item.model_copy(update={"edge": 100})) if item is not None else 0.0


def saving(state: GameState, content: Content) -> float:
    """身上那匹省幾成趕路、疾行的體力（腳力，5.1）；沒騎馬是 0。atlas.route_stamina、截殺追逃都讀它。"""
    return leg_power(content, riding(state, content))


def pace(state: GameState, content: Content) -> float:
    """步調（5.3）：步行、趕路的時間乘它＝1－路上快（含品質）×飽足係數；沒騎馬是 1。出發時快照進 Journey.pace。"""
    item = riding(state, content)
    return 1.0 if item is None else 1 - speed_of(content, item)


def cavalry(state: GameState, content: Content) -> float:
    """決戰騎兵（5.9）：強攻、奇襲的份量多幾成＝騎兵那一列×飽足係數（品質不加）；沒騎馬是 0。"""
    item = riding(state, content)
    return 0.0 if item is None else _cell(content.config.mounts.cavalry, item) * fed_factor(content, item)


def escape(state: GameState, content: Content) -> float:
    """落敗策馬脫身的機會（5.11）：脫身那一列×飽足係數（品質不加）；沒騎馬是 0。必敗問句與 Game._lose_silver 都讀它。"""
    item = riding(state, content)
    return 0.0 if item is None else _cell(content.config.mounts.escape, item) * fed_factor(content, item)


def raid_flee(content: Content, attacker: GameState, target: GameState) -> float:
    """截殺追逃（5.10）：被截殺的人策馬脫身的機會＝守方腳力－攻方腳力，夾在 0～raid_escape_cap。開關關著兩邊都是 0。"""
    gap = saving(target, content) - saving(attacker, content)
    return max(0.0, min(content.config.mounts.raid_escape_cap, gap))


# ---- 字 ----

def tenths(chance: float) -> int:
    """幾成：四捨五入、.5 進位（不用 round：round(2.5) 是 2）。"""
    return int(chance * 10 + 0.5)


def odds_text(chance: float) -> str:
    """寫給玩家看的機會（截殺確認句、必敗問句）：「約 3 成」；不到半成寫「不到一成」。待 joy 潤。"""
    n = tenths(chance)
    return f"約 {n} 成" if n else "不到一成"


def pct(ratio: float) -> str:
    """寫成整數百分比（設計 2.5 的例子：25%×0.8＝20%）：.5 進位，同 tenths 與 atlas 的 math.floor(x + 0.5)。
    不用 f"{ratio:.0%}"：它跟 round 一樣把 .5 捨到偶數，餓到底的駑馬省 12.5% 會寫成 12%、騎兵 2.5% 寫成 2%。"""
    return f"{math.floor(ratio * 100 + 0.5)}%"


def coat_for(loc_id: str) -> str:
    """馬市那一匹的毛色（5.6）：照地點 id 的 sha256 挑，同一處永遠一樣、正式內容四處不一樣。取前 8 個位元組當整數：
    只取第一個位元組的話涿郡、宛城會撞成同一色（Task 4 的測試鎖住）。"""
    digest = hashlib.sha256(loc_id.encode("utf-8")).digest()
    return COATS[int.from_bytes(digest[:8], "big") % len(COATS)]


def horse_name(coat: str, tier: int) -> str:
    """「棗騮馬」「青驄駒」（5.6）。"""
    return coat + NOUNS.get(tier, "馬")


def name_of(item: Equipment) -> str:
    """寫給玩家看的馬名。這一批就是 item.name；裝備三的名駒、名將贈禮照 template 從內容讀（joy 改名不動存檔）時改這裡，
    另外 equipment.store／wield 的三句（騎上、放上裝備庫、換上）直接用 item.name，要在 equipment 另加掛鉤（見模組說明）。"""
    return item.name


def grade(item: Equipment) -> str:
    """「駑馬・下品」（5.6：坐騎不用 equipment.grade 的「一階下品」）。"""
    return f"{TIER_NAMES.get(item.tier, '')}・{item.quality}"
