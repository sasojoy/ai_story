"""全服狀態：所有玩家共讀共寫的一份資料（設計文件四.3／四.4／六.2）——資料模型與存取介面。

存的東西：
- **自創武學命名登記與煉製配方**：武學名稱同一季全服不能重名；配方的結果全服共享，第一個煉出來的人定義它。
- **同伴性情漂移**：歷史人物的「當下性情」是全服玩家共同形塑的；這裡只存 tag 累積計數與語意化後的一句話
  （把計數轉成一句話是 companion_agent.py 的事）。
- **同伴進度與招募狀態**：每位歷史人物全服唯一（設計文件四.4），等級／武學是人物本身的屬性，不是某個玩家
  存檔裡的副本；玩家存檔只留「我對這位人物的好感度」。
- **共享賽季**（大勢、門檻、主線、結局）、投靠名冊、全服決戰，以及跨季的傳國玉璽碎片。

怎麼存不在這個模組：`WorldStateStore` 是介面（線上架構設計第二、三節）。第 1 期的實作是
`sqlite_world.SqliteWorldStore`：每個會寫的方法自己是一筆交易，呼叫端在 action_lock() 裡時併進那一筆。
第 2 期的世界主迴圈會換成「記憶體裡一份＋每個動作寫進資料庫」，介面不變。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .battle_instance import BattleInstance
from .martial_arts import MartialArt
from .models import BattleDef, Content
from .state import Rumor, WorldState

SeasonPhase = Literal["preparing", "running", "resting"]  # 籌備（管理者還沒開季）／進行中／休季（這一季已結束）

JADE_SEAL_FRAGMENT_COUNT = 7  # 設計文件九.2：七塊碎片＝跨季長線，不是單季目標


class JadeSealFragment(BaseModel):
    """跨季持久記錄的一塊傳國玉璽碎片（設計文件九）：找到後永遠留在這裡，不會因為任何
    玩家開新季、甚至之後換到別的季別劇本而被清掉——這正是「跨季」的字面意思。"""

    number: int  # 第幾塊（1~JADE_SEAL_FRAGMENT_COUNT），依找到的先後順序
    finder: str  # 找到的玩家名號
    season_name: str  # 當時是哪一季主題劇本找到的（例如「黃巾之亂」）
    text: str  # 給玩家看的一句話紀錄（通常取自觸發事件的 chronicle 文字）


class CompanionProgress(BaseModel):
    """一位歷史人物（可招募的 7 位）目前的等級/武學/招募狀態，全服共用一份。"""

    level: int = 1
    exp: int = 0
    neili: float | None = None  # 氣血，None＝回滿（滿＝上限 − 內傷）
    injury: float = 0.0  # 內傷，同 state.Member.injury
    neigong_id: str | None = None
    neigong_level: int = 1
    wugong_id: str | None = None
    wugong_level: int = 1
    owner: str | None = None  # 目前招募他的玩家名號；None＝自由之身，誰都能嘗試招募


class SharedWorldState(BaseModel):
    created_skills: dict[str, MartialArt] = Field(default_factory=dict)  # 鍵是武學名稱
    recipes: dict[str, str] = Field(default_factory=dict)  # 煉製配方鍵 -> 功法名稱（功法本體存在 created_skills）；每季清空，見 next_season
    companion_tag_counts: dict[str, dict[str, int]] = Field(default_factory=dict)  # 人物 id -> {tag: 次數}
    companion_drift_note: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 目前漂移後的一句話性情
    companion_drift_synthesized_at: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 上次語意化時的 tag 總數
    companions: dict[str, CompanionProgress] = Field(default_factory=dict)  # 人物 id -> 進度/招募狀態
    event_flavor: dict[str, str] = Field(default_factory=dict)  # 江湖大事 id -> 全服共用的一次性潤色句（設計文件 8.2 第 4 點）
    jade_seal_fragments: list[JadeSealFragment] = Field(default_factory=list)  # 跨季持久（設計文件九.2）

    # ── 共享賽季（真正共享的大勢/門檻/主線/結局，取代原本每個玩家各自獨立的 WorldState）──
    # 上面那些欄位不跟著 season 整個換掉，但換季時武學命名登記、煉製配方、同伴進度會照
    # 「跨季不滾雪球」清空，玉璽碎片等才是永遠留著；season 本身每次開新賽季會被整個換掉
    # （見 next_season）。season_number 從 1 起算，
    # season_last_real 是這個賽季的共用時鐘上次對到現實時間的時間點（None＝還沒對過）。
    season: WorldState = Field(default_factory=WorldState)
    season_number: int = 1
    season_last_real: float | None = None
    season_opened: bool = False  # 這一季管理者開季了沒；False＝籌備中（見 season_phase）
    tianji: int = 0  # 天機：每次換季 +1，自創武學「名字 → 數值」的配方跟著換（跨季不滾雪球第三條）
    faction_rolls: dict[str, str] = Field(default_factory=dict)  # 這一季的投靠名冊：玩家名號 → 陣營 id
    # （真人與伺服器假人一起記，不記誰是假人；陣營人數看這份，換季清空，見 next_season）

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）────────
    # 同一時間最多一場（先簡化成這樣；真的需要同時好幾場再擴充成 list/dict）。
    active_battle: BattleInstance | None = None

    def season_phase(self) -> SeasonPhase:
        if not self.season.storyline or not self.season_opened:
            return "preparing"
        return "resting" if self.season.ended else "running"


def fresh_season(content: Content) -> WorldState:
    """照劇本種出一季全新的共用賽季（大勢起始值、公開的大勢線、第一條主線）。"""
    trends = content.scenario.trends
    return WorldState(
        trends={t.id: t.start for t in trends},
        revealed={t.id for t in trends if not t.hidden},
        storyline=content.scenario.storylines[0].id,
    )


def jade_seal_summary(fragments: list[JadeSealFragment]) -> str:
    if not fragments:
        return "傳國玉璽的七塊碎片，至今尚無人尋獲過一塊。"
    lines = [f"傳國玉璽：{len(fragments)}/{JADE_SEAL_FRAGMENT_COUNT} 塊碎片已現世——"]
    lines += [f"　第 {f.number} 塊：{f.finder}（{f.season_name}）{f.text}" for f in fragments]
    return "\n".join(lines)


class WorldStateStore(Protocol):
    """全服狀態的存取介面。引擎只認這個介面，實作見 sqlite_world.SqliteWorldStore。

    交易：每個會寫的方法自己就是一筆交易（讀→改→寫回一起成功或一起撤回）；呼叫端在 action_lock()
    裡時，併進那一筆。「補算時間＋做動作＋存檔」整段一律包在 action_lock() 裡（app.py、假人程式）。"""

    def action_lock(self, timeout: float | None = None) -> AbstractContextManager[object]:
        """一個動作＝一筆交易（線上架構設計 3.1）。timeout=None 等到拿到為止（伺服器）；給秒數時等不到就丟
        TimeoutError（假人程式跳過這一輪，不卡住正在等 LLM 的真人）。出錯時整個動作一起撤回。可以巢狀。"""
        ...

    def read(self) -> SharedWorldState: ...

    def mutate(self, fn: Callable[[SharedWorldState], None]) -> SharedWorldState:
        """讀取→套用 fn(state)→寫回，同一筆交易，回傳套用後的狀態。fn 直接原地修改 state。"""
        ...

    # ── 武學命名登記與煉製配方（這一季）──
    def is_skill_name_taken(self, name: str) -> bool: ...

    def claim_skill_name(self, art: MartialArt) -> bool:
        """把 art 登記成這一季的自創武學；名字已經有人用過就不登記。回傳有沒有登記成功（原子判斷，
        不會有兩個玩家同時取到同一個名字都成功）。"""
        ...

    def lookup_recipe(self, key: str) -> MartialArt | None:
        """這個配方這一季已經有人煉出來過嗎？有就回傳登記在案的那一門（全服看到同一個結果）。"""
        ...

    def claim_recipe(self, key: str, art: MartialArt) -> tuple[MartialArt | None, bool]:
        """登記配方與功法，回傳（這個配方的功法, 是不是首創），原子判斷。三種結果：
        - 配方已經有人登記 → 回傳登記在案的那一門與 False（配方的結果全服共享，無限煉製設計 §十二 第 1 點）。
        - 配方還沒人登記、art.name 也還沒被占用 → 登記，回傳 (art, True)。
        - 配方還沒人登記、但 art.name 已經被別人的自創功法或別的配方占用 → 回傳 (None, False)，
          呼叫端換一個名字再試（取名自創仍然是獨佔的）。"""
        ...

    # ── 同伴性情漂移 ──
    def record_companion_tag(self, companion_id: str, tag: str) -> None: ...

    def get_companion_drift_note(self, companion_id: str) -> str: ...

    def set_companion_drift_note(self, companion_id: str, note: str) -> None: ...

    def tag_counts_since_last_drift(self, companion_id: str) -> int:
        """自上次語意化以來，全服玩家又新累積了幾次交遊 tag（用總次數而非時間排程：誰的這次互動剛好跨過門檻就由誰觸發）。"""
        ...

    def record_drift_synthesis(self, companion_id: str, note: str) -> None:
        """語意化完成後，把新的一句話性情跟「這次是在累積到多少次時算的」一起寫回（同一筆交易裡讀當下總數）。"""
        ...

    # ── 江湖大事潤色（全服共用一次）──
    def get_event_flavor(self, fire_id: str) -> str: ...

    def set_event_flavor(self, fire_id: str, text: str) -> None:
        """只在這個江湖大事還沒有人潤色過時才寫入：全服永遠只看到同一份。"""
        ...

    # ── 傳國玉璽碎片（跨季）──
    def record_jade_seal_fragment(self, finder: str, season_name: str, text: str) -> JadeSealFragment | None:
        """記錄一塊新找到的碎片（編號在交易裡決定，不會重複或漏編）；七塊都找完之後回傳 None。"""
        ...

    def get_jade_seal_fragments(self) -> list[JadeSealFragment]: ...

    def jade_seal_summary(self) -> str: ...

    # ── 共享賽季 ──
    def get_season(self) -> WorldState:
        """目前這一季，連同這一季全部的傳聞與江湖史（給畫面看）。read()／mutate()／mutate_season()
        給出的賽季不讀傳聞與江湖史，兩個清單是空的，往裡面加的照樣會寫進去。"""
        ...

    def chronicle_before(self, season_number: int) -> list[tuple[int, list[Rumor]]]:
        """season_number 以前每一季的江湖史，新的一季在前（線上架構設計 3.2：江湖史跨季保留）。"""
        ...

    def get_season_number(self) -> int: ...

    def mutate_season(self, fn: Callable[[WorldState], None]) -> WorldState:
        """讀取共用賽季→套用 fn(season)→寫回，同一筆交易。"""
        ...

    def save_season(self, season: WorldState) -> None:
        """寫回共用賽季：呼叫端（engine.py）把 state.world 指向 get_season() 讀回的那一份、就地修改過，這裡寫回。"""
        ...

    def season_phase(self) -> SeasonPhase: ...

    def seed_first_season(self, content: Content) -> WorldState:
        """全服第一次開局：照劇本種出第 1 季。預設停在籌備中等管理者開季；內容設定 auto_open_first_season
        時直接開季。已經種過就原封不動回傳。"""
        ...

    def open_season(self, now: float) -> bool:
        """管理者開季：籌備中 → 進行中，賽季時鐘從 now 起算。還沒種、或已經開過，回傳 False。"""
        ...

    def next_season(self, content: Content, now: float) -> bool:
        """管理者開下一季：只在休季時有效。換上全新的一季、賽季編號 +1、直接開季，賽季時鐘從 now 起算；
        同伴、自創武學名字、煉製配方、投靠名冊、沒打完的決戰都清掉，天機 +1；玉璽碎片不動。
        舊的一季整份留著（線上架構設計 3.2：換季不刪資料）。"""
        ...

    def catch_up_season(self, content: Content, now: float, rng: random.Random) -> list[str]:
        """被動的現實時間追趕：把共用賽季依「距離上次有人追趕過了多久現實時間」往前推進，世界的時間
        永遠只走一份。時鐘只會往前：拿比上次對過的還早的時間來追趕，不推進、也不把時鐘撥回去。"""
        ...

    # ── 投靠名冊 ──
    def record_faction(self, name: str, faction_id: str) -> None: ...

    def faction_counts(self) -> dict[str, int]:
        """這一季各陣營投靠了幾人（只列有人的陣營）。"""
        ...

    # ── 全服即時多人戰鬥 ──
    def get_battle(self) -> BattleInstance | None: ...

    def mutate_battle(self, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        """讀取目前這場戰鬥→套用 fn(battle)→寫回；沒有戰鬥時 fn 不會被呼叫，直接回傳 None。"""
        ...

    def start_battle(self, definition: BattleDef, now: float) -> BattleInstance:
        """開一場新戰鬥；已經有一場還沒結束的戰鬥時，原封不動回傳那一場。"""
        ...

    def clear_battle(self) -> None: ...

    # ── 同伴進度與招募 ──
    def get_companion(self, companion_id: str) -> CompanionProgress:
        """讀目前進度；還沒有人動過這位人物時回傳一份預設值（不寫回）。"""
        ...

    def try_recruit(self, companion_id: str, player_name: str) -> bool:
        """把 owner 設成 player_name；已經有主的話失敗（設計文件四.4：唯一、可搶）。"""
        ...

    def release_companion(self, companion_id: str) -> None:
        """放走同伴：只清 owner，等級/武學等進度原封不動。"""
        ...

    def update_companion(
        self, companion_id: str, fn: Callable[[CompanionProgress], None],
    ) -> CompanionProgress: ...
