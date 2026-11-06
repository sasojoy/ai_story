"""探索表的小字與小函式（全部拆包第 50 批「輿圖二」移到核心；主人：核心，探索包、有所感包、輿圖包都讀；手冊 3.3、3.10 的查詢服務）。

下面三樣原本分別寫在 tianxia/mapdata.py（LOSE_WORD）、探索包的 explore_rules.py（六種地點、四類事、「多半」那兩個字的算法）、
有所感包的 sensing.py（terrain_tags）；輿圖包要用、又不能 import 探索包與有所感包，第 49 批先寄放在 core/services.py 檔尾的 # map 那一段，
第 50 批整段一個字沒改搬到這裡（第 49 批 PM 認定第 3 條；services.py 不留 re-export）。純函式，照 config 與地點的標籤算，不碰 Game。
原本的模組 re-export 同一個物件：`explore_rules.kind_of is explore_base.kind_of`、`explore_actions.LOSE_WORD is explore_base.LOSE_WORD`、
`sensing.terrain_tags is explore_base.terrain_tags`、`mapdata.LOSE_WORD is explore_base.LOSE_WORD`。

跟探索包的 tianxia/features/explore/explore_base.py（第 18 批）同檔名、不同模組：一律寫完整路徑 `from tianxia.core import explore_base`。
同 omen_base、convoy_base 不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from ..models import Location

if TYPE_CHECKING:
    from ..jianfa_numbers import ExploreOneTable, JianfaNumbers

LOSE_WORD = "必敗"  # 這種勝算的出陣建議照樣列，但排到最後、網頁畫淡（企劃者 10/15 從對比圖選乙）；探索挑懸賞時對這一路是必敗就不強制

TOWN, TEMPLE, FORD, WILD, HILL, CAMP = "town", "temple", "ford", "wild", "hill", "camp"  # 六種地點（jianfa_numbers.ExploreKind）
EVENT, ENCOUNTER, MATERIAL, INSIGHT = "event", "encounter", "material", "insight"
KINDS = (EVENT, ENCOUNTER, MATERIAL, INSIGHT)  # 一趟可能發生的四類事（比重的鍵照這個順序）
FILL = MATERIAL  # 什麼都抽不出來（比重全是 0）補素材
PLACE_WORDS = {TOWN: "城裡", TEMPLE: "寺裡", FORD: "渡口", WILD: "野外", HILL: "山裡", CAMP: "營裡"}
BEAT_MOSTLY = {EVENT: "多事", ENCOUNTER: "多敵", MATERIAL: "多料", INSIGHT: "多悟"}  # 比重最高的那一類寫成哪兩個字
BALANCED = "參半"  # 最高的有兩類以上並列


def match(cfg: JianfaNumbers, tags: Iterable[str]) -> ExploreOneTable | None:
    """這組地點標籤靠自己對得上哪一張表：照 `explore_tables` 的順序，第一張有共同標籤的；一個都對不上是 None。
    內容驗證（每個正式地點都歸得到一張）問它；探索本身問 `kind_of`。"""
    have = set(tags)
    return next((t for t in cfg.explore_tables if have & set(t.tags)), None)


def kind_of(cfg: JianfaNumbers, loc) -> ExploreOneTable:
    """這一處用哪一張表：`match`；標籤一張都對不上的歸最後一張（野）。"""
    return match(cfg, loc.tags) or cfg.explore_tables[-1]


def mostly_of(weights: Mapping[str, float]) -> str:
    """「多半」那兩個字照比重寫：四類裡比重最高的那一類（BEAT_MOSTLY），並列最高寫「參半」；全是 0 的那一趟補素材（FILL）所以寫「多料」。"""
    top = max((weights.get(kind, 0) for kind in KINDS), default=0)
    if top <= 0:
        return BEAT_MOSTLY[FILL]
    best = [kind for kind in KINDS if weights.get(kind, 0) == top]
    return BALANCED if len(best) > 1 else BEAT_MOSTLY[best[0]]


def table_weights(table: ExploreOneTable) -> dict[str, int]:
    """一張表的四欄（事件、遭遇、素材、感悟），照 KINDS 的順序。"""
    return {EVENT: table.event, ENCOUNTER: table.encounter, MATERIAL: table.material, INSIGHT: table.insight}


def mostly_in(table: ExploreOneTable) -> str:
    """這一種地點的「多半」兩個字，照它的表算（沒有危險度、不看誰站在那裡）：序章裡沒有比重可看時輿圖名字旁的退路
    （平常是 Game.map_mostly 照每一處自己的比重，tail_of）。"""
    return mostly_of(table_weights(table))


def hint_in(table: ExploreOneTable) -> str:
    """這一種地點的小字，照它的表算（沒有危險度）：玩法說明列六張表的樣子、沒有比重可看時的退路。"""
    return PLACE_WORDS[table.kind] + mostly_in(table)


def terrain_tags(loc: Location) -> list[str]:
    """地點標籤裡的地形（河畔、城鎮……）：設施的標籤（馬市，裝備四欄 5.5；醫館，clinic.CLINIC_TAG；酒肆，tavern.TAG）不算地形。
    有所感標題的括號與輿圖抽屜名字旁的地形（意境提示設計第五節）共用。"""
    from .. import mounts  # noqa: PLC0415  共用規則層

    return [tag for tag in loc.tags if tag not in (mounts.MARKET_TAG, "醫館", "酒肆")]
